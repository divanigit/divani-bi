"""Fixtures for the SQL tests: a scratch database with schema.sql and functions.sql applied.

The admin connection comes from SH_TEST_ADMIN_URL (default: the local server). The scratch
database gets a random name and is dropped at the end; no other database is touched.
"""
import datetime as dt
import json
import os
import pathlib
import secrets

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

REFERENCE = pathlib.Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("SH_TEST_ADMIN_URL", "postgresql://postgres:shtest@127.0.0.1:5432/postgres")
TIMINGS = []          # (label, seconds), filled by the performance test and printed in the summary


def apply_sql(conn):
    """schema.sql, then functions.sql, each sent as one command of many statements."""
    for name in ("schema.sql", "functions.sql"):
        conn.execute((REFERENCE / name).read_text(encoding="utf-8"))


def empty(conn):
    """Delete every row of every sh_* table."""
    tables = conn.execute(r"select format('%I', tablename) from pg_tables"
                          r" where schemaname = 'public' and tablename like 'sh\_%'"
                          r" order by tablename = 'sh_alerts'").fetchall()      # last: sh_messages points at it
    for (table,) in tables:
        conn.execute("delete from " + table)


def example_config(**changes):
    config = json.loads((REFERENCE / "site_health.config.example.json").read_text(encoding="utf-8"))
    config.update(changes)
    return config


PAGES = example_config()["pages"]


class Db:
    """One connection to the scratch database."""

    def __init__(self, conn):
        self.conn = conn

    def rpc(self, fn, **params):
        """Call one sh_* function with named parameters and return its JSON, parsed.
        Lists and dicts go as jsonb; times may be datetimes or ISO 8601 strings."""
        sql = "select %s(%s)" % (fn, ", ".join(name + " => %s" for name in params))
        values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params.values()]
        return self.conn.execute(sql, values).fetchone()[0]

    def sql(self, query, params=None):
        """Plain SQL, for test data the write functions cannot produce (rows in the past)."""
        cur = self.conn.execute(query, params)
        return cur.fetchall() if cur.description else None

    def now(self):
        """The database's now(), in UTC so that "90 days earlier" is exact whatever the session's
        time zone. Inside the `db` fixture it stands still for the whole test."""
        return self.sql("select now()")[0][0].astimezone(dt.timezone.utc)

    def setup(self, **changes):
        """Load the example configuration, with top-level keys replaced by `changes`."""
        return self.rpc("sh_setup", p_config=example_config(**changes))

    # Test data, through the write functions. Every moment is given by the caller (a fixed
    # date, or an offset from self.now()), so nothing depends on when the test happens to run.

    def probe(self, at, kind="full", fail=None, ms=300):
        """Store one round of the example configuration's probe pages.
        fail: {page: an HTTP status, or a fail code}. ms: one value, or {page: value} (default 300)."""
        rows = []
        for page in PAGES:
            if not page.get("probe"):
                continue
            why = (fail or {}).get(page["name"])
            row = {"page": page["name"], "url": page["url"], "ok": why is None, "status": 200, "fail": None,
                   "err": None, "ms": ms.get(page["name"], 300) if isinstance(ms, dict) else ms}
            if isinstance(why, int):
                row.update(status=why, fail="http")
            elif why:
                row.update(status=None, fail=why)
            rows.append(row)
        return self.rpc("sh_probe_add", p_round_at=at, p_kind=kind, p_rows=rows)

    def run(self, at, page="בית", lcp=2400, strategy="mobile", source="core", **more):
        """Store one lab run. `page` is the name of a configured page, or the address of any
        other page (a rotation run). lcp None stores a failed run."""
        urls = {p["name"]: p["url"] for p in PAGES}
        return self.rpc("sh_speed_add", p_rows=[{
            "at": at.isoformat(), "url": urls.get(page, page), "page": page if page in urls else None,
            "strategy": strategy, "source": source, "ok": lcp is not None, "lcp_ms": lcp, **more}])

    def ran(self, flow, **ago):
        """Say that a flow's last successful run was this long ago (timedelta arguments)."""
        self.sql("update sh_flows set last_at = now() - %s where flow_name = %s", [dt.timedelta(**ago), flow])


@pytest.fixture(scope="session")
def database():
    """The connection string of a fresh scratch database."""
    name = "sh_test_" + secrets.token_hex(6)
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute('create database "%s"' % name)
    url = make_conninfo(ADMIN_URL, dbname=name)
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            apply_sql(conn)
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute('drop database if exists "%s" with (force)' % name)


@pytest.fixture
def db(database):
    """A Db inside one transaction that is rolled back at the end.

    Every test starts with empty tables, and now() is the same instant for the whole test:
    a row written "ten minutes ago" is exactly ten minutes old when the test reads it back.
    """
    conn = psycopg.connect(database)
    try:
        empty(conn)               # also what another test committed; the rollback gives it back
        yield Db(conn)
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def committed(database):
    """A factory of Db objects that commit, for tests that need several sessions at once.
    The tables are emptied before and after."""
    conns = [psycopg.connect(database, autocommit=True)]
    empty(conns[0])

    def connect():
        conns.append(psycopg.connect(database, autocommit=True))
        return Db(conns[-1])

    try:
        yield connect
    finally:
        empty(conns[0])
        for conn in conns:
            conn.close()


def pytest_terminal_summary(terminalreporter):
    if TIMINGS:
        terminalreporter.write_sep("-", "read functions over 90 days of history")
        for label, seconds in TIMINGS:
            terminalreporter.write_line("%-58s %6.0f ms" % (label, seconds * 1000))
