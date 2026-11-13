"""Database access for the site-health server and collectors.

Everything goes through rpc(): one call of one sh_* SQL function, returning its JSON result.
The transport is chosen by the environment:

    SUPABASE_URL + SUPABASE_SECRET_KEY    HTTPS: POST {SUPABASE_URL}/rest/v1/rpc/<fn>
    DATABASE_URL                          a normal Postgres connection (psycopg 3)

Parameter values must be JSON values (send times as ISO 8601 strings), so both transports
accept exactly the same calls.
"""
import http.client
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request

TIMEOUT = 30                                  # seconds
_FUNCTION = re.compile(r"sh_[a-z_]+")         # names go into a URL or into SQL text: nothing else may pass
_PARAMETER = re.compile(r"p_[a-z_]+")
_thread = threading.local()                   # the Postgres transport keeps one connection per thread
log = logging.getLogger("site_health.db")


class DbError(Exception):
    """A database call failed. The text names no host, user or key, so it may be shown to a viewer;
    connection details go to the log."""


def rpc(fn, params=None):
    """Call the SQL function `fn` with named parameters and return its (JSON) result."""
    params = params or {}
    if not _FUNCTION.fullmatch(fn) or not all(_PARAMETER.fullmatch(name) for name in params):
        raise DbError("bad function or parameter name in a call of %r" % (fn,))
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SECRET_KEY", "")
    if url and key:
        return _rpc_https(url, key, fn, params)
    dsn = os.environ.get("DATABASE_URL", "")
    if dsn:
        return _rpc_postgres(dsn, fn, params)
    raise DbError("no database configured: set SUPABASE_URL and SUPABASE_SECRET_KEY, or DATABASE_URL")


def _rpc_https(url, key, fn, params):
    request = urllib.request.Request(
        "%s/rest/v1/rpc/%s" % (url.rstrip("/"), fn), data=json.dumps(params).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read())["message"]          # PostgREST explains itself in the body
        except (ValueError, KeyError, TypeError, OSError):
            message = None
        raise DbError("HTTP %d: %s" % (e.code, message or e.reason)) from None
    except (OSError, http.client.HTTPException) as e:          # no route, TLS, timeout, broken answer
        log.warning("database call %s failed: %r", fn, e)
        cause = getattr(e, "reason", e)                        # URLError wraps the real failure
        name = type(cause if isinstance(cause, Exception) else e).__name__
        raise DbError("database unreachable (%s)" % name) from None
    try:
        return json.loads(body) if body else None
    except ValueError:
        raise DbError("the database API did not answer with JSON") from None


def _rpc_postgres(dsn, fn, params):
    import psycopg                                             # only this transport needs the driver
    from psycopg.types.json import Jsonb

    sql = "select %s(%s)" % (fn, ", ".join(name + " => %s" for name in params))
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params.values()]

    def connect():
        # autocommit and no server-side prepared statements: works behind a transaction pooler
        _thread.conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None, connect_timeout=TIMEOUT)
        return _thread.conn

    try:
        conn = getattr(_thread, "conn", None)
        reused = conn is not None and not conn.closed
        if not reused:
            conn = connect()
        try:
            return conn.execute(sql, values).fetchone()[0]
        except psycopg.OperationalError:
            if not (reused and conn.closed):
                raise
            return connect().execute(sql, values).fetchone()[0]    # an idle connection was dropped: once more
    except psycopg.OperationalError as e:
        log.warning("database call %s failed: %s", fn, e)       # the full text (host, user) stays in the log
        raise DbError(e.diag.message_primary or "database unreachable") from None
    except psycopg.Error as e:
        raise DbError(e.diag.message_primary or str(e)) from None
