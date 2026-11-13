"""Tests of collectors.py, manage.py and watchdog.py.

Everything runs against a local fake website (fake_site.py: pages, sitemaps, a WooCommerce or a
Shopify catalogue, a PageSpeed endpoint, an ntfy server, a heartbeat service) and a scratch database
with schema.sql and functions.sql applied for real (conftest.py). The collectors reach that database
through db.rpc and DATABASE_URL, exactly as in production. No test talks to anything outside this
machine. The fake site lives on 127.0.0.1, so the fixtures set SH_ALLOW_PRIVATE=1; the tests of
that very rule take it away again.

    cd reference && python3 -m pytest -q tests/test_collectors.py
"""
import gzip
import http.server
import json
import logging
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REFERENCE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REFERENCE), str(REFERENCE / "tests")]

import collectors  # noqa: E402
import conftest  # noqa: E402
import db  # noqa: E402
import manage  # noqa: E402
import watchdog  # noqa: E402
from fake_site import PAGES, PSI_ERRORS, SHOPIFY_PAGES, FakeSite, sitemap_index, urlset  # noqa: E402

UTC = timezone.utc
ZONE = ZoneInfo("Asia/Jerusalem")                 # the time zone of the fake site's configuration
ENVIRONMENT = ("PAGESPEED_KEY", "PAGESPEED_URL", "NTFY_TOPIC", "NTFY_URL", "NTFY_TOKEN", "DASHBOARD_URL",
               "HEARTBEAT_URL", "SH_ALLOW_PRIVATE", "SH_SITEMAP_MB", "SUPABASE_URL", "SUPABASE_SECRET_KEY",
               "DATABASE_URL")
TOPIC = "sh-TestTopic0123456789abcd"
KEY = "AIzaTestKey-not-a-real-one"
PROBE_FLOW, CORE_FLOW, ROTATION_FLOW = "בודק זמינות האתר", "מדידת מהירות — עמודי ליבה", "מדידת מהירות — סבב כל האתר"
SITEMAP_FLOW, CERT_FLOW, CATALOGUE_FLOW = "טעינת מפת האתר", "בדיקת תעודת האבטחה", "בדיקת מוצרים שבורים"
T0 = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)    # a fixed moment for everything that takes its time as an input


# ---------------------------------------------------------------- fixtures and helpers

@pytest.fixture(scope="module")
def server():
    fake = FakeSite().start()
    yield fake
    fake.stop()


@pytest.fixture
def site(server, monkeypatch):
    """The fake site, repaired, and an environment without any key, topic or database of this machine."""
    server.reset()
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SH_ALLOW_PRIVATE", "1")                           # the site under test is on 127.0.0.1
    monkeypatch.setenv("PAGESPEED_URL", server.url + "/pagespeedonline/v5/runPagespeed")
    monkeypatch.setattr(collectors, "PSI_WAITS", (0.01, 0.01))
    monkeypatch.setattr(collectors, "SHOPIFY_PAUSE", 0)
    return server


@pytest.fixture
def sql(site, database, committed, monkeypatch):
    """The scratch database, set up for the fake site. The collectors reach it through db.rpc;
    the test looks at the tables through the returned Db."""
    monkeypatch.setenv("DATABASE_URL", database)
    monkeypatch.setattr(db, "_thread", threading.local())
    look = committed()
    look.rpc("sh_setup", p_config=site.config())
    yield look
    connection = getattr(db._thread, "conn", None)
    if connection is not None:
        connection.close()


@pytest.fixture
def phone(site, monkeypatch):
    """Pushing is configured: the fake ntfy, a topic, the dashboard's address."""
    monkeypatch.setenv("NTFY_URL", site.url + "/ntfy")
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("DASHBOARD_URL", "https://dash.example/")


@pytest.fixture
def scheduler(monkeypatch):
    """A scheduler of its own for one test: fresh state, stopped at the end."""
    stop = threading.Event()
    monkeypatch.setattr(collectors, "_stop", stop)
    monkeypatch.setattr(collectors, "_threads", [])
    monkeypatch.setattr(collectors, "_site", {"config": None, "read_at": None, "said": None})
    yield stop
    stop.set()
    for thread in collectors._threads:
        thread.join(5)


def page(site, path, **more):
    return {"name": PAGES[path], "url": site.url + path, **more}


@pytest.fixture
def inner():
    """A second server on this machine: it stands for a service inside the dashboard host's own
    network, which no answer of the monitored site may ever make the collectors talk to."""
    service = FakeSite().start()
    yield service
    service.stop()


def elsewhere(service, path="/admin/secret-panel"):
    """An address of that service under another host name than the site's (which is 127.0.0.1)."""
    return "http://localhost:%s%s" % (service.url.rsplit(":", 1)[1], path)


def this_minute():
    return datetime.now(UTC).replace(second=0, microsecond=0)


def minutes(n):
    return timedelta(minutes=n)


def il(at):
    """A moment as the SQL functions print it: local time, DD.MM HH:MM."""
    return at.astimezone(ZONE).strftime("%d.%m %H:%M")


def closed_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def last_run(sql, flow):
    return sql.sql("select last_at from sh_flows where flow_name = %s", [flow])[0][0]


def lapse_claims(sql):
    """Two minutes later: sh_alerts_check offers the pushes that are still owed again."""
    sql.sql("update sh_messages set claimed_at = claimed_at - interval '2 minutes' where status is null")


def owe(sql, n, first=1):
    """Queue n messages that nobody sent yet (test data: the write functions queue one per alert)."""
    sql.sql("insert into sh_messages (event, kind, title, msg, priority)"
            " select 'open', 'התראה', 'הודעה ' || i, 'גוף', 3 from generate_series(%s::int, %s::int) i", [first, first + n - 1])


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


def fixture(name):
    return json.loads((REFERENCE / "tests" / "fixtures" / name).read_text(encoding="utf-8"))


# ================================================================ 1. the availability probe (§7.5)

def test_a_page_that_answers_200_is_ok(site, monkeypatch):
    monkeypatch.setenv("DASHBOARD_URL", "https://dash.example")
    row = collectors.probe_check(page(site, "/"), 2)
    ms = row.pop("ms")
    assert row == {"page": "בית", "url": site.url + "/", "ok": True, "status": 200, "fail": None, "err": None}
    assert type(ms) is int and 0 <= ms < 500
    method, path, headers = site.hits[-1]
    assert (method, path) == ("GET", "/")
    assert headers["User-Agent"] == "SiteHealthProbe/1.0 (+https://dash.example)"
    assert headers["Cache-Control"] == "no-cache" and headers["Connection"] == "close"


@pytest.mark.parametrize("broken, fail, status, err", [
    ({"status": 502}, "http", 502, None),
    ({"status": 404}, "http", 404, None),
    ({"status": 204}, "http", 204, None),                                 # 200 and nothing else: not any 2xx
    ({"status": 206}, "http", 206, None),
    ({"hang": 3}, "timeout", None, "no answer within 0.4 seconds"),
    ({"drop": True}, "connect", None, "RemoteDisconnected: Remote end closed connection without response"),
    ({"body": "<html><body>עמוד אחר לגמרי</body></html>"}, "content", 200, "the expected text is not on the page"),
    ({"redirects": 6}, "http", 302, "redirected more than 5 times, or to nowhere"),
])
def test_a_failed_check_and_its_code(site, broken, fail, status, err):
    site.broken["/product/sample-sofa/"] = broken
    row = collectors.probe_check(page(site, "/product/sample-sofa/", expect="הוספה לסל"), 0.4)
    assert (row["ok"], row["fail"], row["status"], row["err"]) == (False, fail, status, err)
    assert type(row["ms"]) is int                                         # the time until the failure
    if fail == "timeout":
        assert 400 <= row["ms"] < 900


def test_a_host_that_refuses_the_connection_or_does_not_exist_is_a_connect_failure(site):
    refused = collectors.probe_check({"name": "x", "url": "http://127.0.0.1:%d/" % closed_port()}, 2)
    assert (refused["ok"], refused["fail"], refused["status"]) == (False, "connect", None)
    assert refused["err"].startswith("ConnectionRefusedError")
    unknown = collectors.probe_check({"name": "x", "url": "http://no-such-host.invalid/"}, 2)
    assert (unknown["fail"], unknown["status"]) == ("connect", None) and unknown["err"].startswith("gaierror")
    not_http = collectors.probe_check({"name": "x", "url": "ftp://example.co.il/"}, 2)
    assert (not_http["fail"], not_http["err"]) == ("connect", "ValueError: not an http(s) address")


def test_redirects_are_followed_up_to_five_each_on_a_fresh_connection(site):
    site.broken["/cart/"] = {"redirects": 5}
    row = collectors.probe_check(page(site, "/cart/"), 2)
    assert (row["ok"], row["status"]) == (True, 200)
    assert [path for _, path, _ in site.hits] == ["/cart/"] + ["/cart/?hop=%d" % hop for hop in range(1, 6)]
    assert all(headers["Connection"] == "close" for _, _, headers in site.hits)


def test_ms_is_the_time_until_the_headers_not_the_body(site):
    site.broken["/"] = {"body_delay": 0.6}                                # the headers at once, the body later
    started = time.monotonic()
    row = collectors.probe_check(page(site, "/"), 2)
    assert row["ok"] and row["ms"] < 300 and time.monotonic() - started < 0.3     # the body was never waited for

    site.broken["/product/sample-sofa/"] = {"body_delay": 0.6}
    started = time.monotonic()
    row = collectors.probe_check(page(site, "/product/sample-sofa/", expect="הוספה לסל"), 2)
    assert row["ok"] and row["ms"] < 300 and time.monotonic() - started >= 0.6    # read for the text, not timed

    site.broken["/"] = {"delay": 0.3}                                     # a slow server
    row = collectors.probe_check(page(site, "/"), 2)
    assert row["ok"] and 300 <= row["ms"] < 600


def test_the_expected_text_is_looked_for_in_the_first_200_kb(site):
    padding = "<!-- %s -->" % ("x" * 199_000)
    site.broken["/product/sample-sofa/"] = {"body": "<html><body>%s<button>הוספה לסל</button></body></html>" % padding}
    assert collectors.probe_check(page(site, "/product/sample-sofa/", expect="הוספה לסל"), 5)["ok"] is True
    site.broken["/product/sample-sofa/"] = {"body": "<html><body>%s%s<button>הוספה לסל</button></body></html>"
                                                    % (padding, "y" * 2000)}
    row = collectors.probe_check(page(site, "/product/sample-sofa/", expect="הוספה לסל"), 5)
    assert (row["ok"], row["fail"]) == (False, "content")                 # it is there, beyond what is read


def test_a_body_that_does_not_arrive_in_time_is_a_timeout(site):
    site.broken["/product/sample-sofa/"] = {"body_delay": 2}
    row = collectors.probe_check(page(site, "/product/sample-sofa/", expect="הוספה לסל"), 0.4)
    assert (row["ok"], row["fail"]) == (False, "timeout") and 400 <= row["ms"] < 900


def test_a_compressed_page_is_still_searched_for_its_text(site):
    answer = collectors.Answer(200, _headers({"Content-Encoding": "gzip", "Content-Type": "text/html; charset=utf-8"}),
                               gzip.compress("<p>הוספה לסל</p>".encode("utf-8")), 0.1)
    assert "הוספה לסל" in collectors._page_text(answer)
    hebrew = collectors.Answer(200, _headers({"Content-Type": "text/html; charset=windows-1255"}),
                               "הוספה לסל".encode("windows-1255"), 0.1)
    assert collectors._page_text(hebrew) == "הוספה לסל"


def _headers(values):
    import http.client
    message = http.client.HTTPMessage()
    for name, value in values.items():
        message[name] = value
    return message


def test_rounds_are_stored_with_their_kind_under_one_scheduled_moment(sql, site):
    config = collectors.read_config()
    assert [p["name"] for p in config.probe] == ["בית", "קטגוריה", "מוצר", "סל"]         # the fifth core page is not probed
    at = this_minute() - minutes(2)
    site.broken["/cart/"] = {"status": 502}

    full = collectors.probe_round(config.probe, "full", at)
    assert full["stored"] == 4 and [row["page"] for row in full["rows"]] == ["בית", "קטגוריה", "מוצר", "סל"]
    assert sql.sql("select round_at, kind, page, ok, status, fail, ms is not null from sh_probe order by page") == [
        (at, "full", "בית", True, 200, None, True), (at, "full", "מוצר", True, 200, None, True),
        (at, "full", "סל", False, 502, "http", True), (at, "full", "קטגוריה", True, 200, None, True)]
    assert last_run(sql, PROBE_FLOW) == at                                # the flow's proof of life

    half = at + timedelta(seconds=30)
    light = collectors.probe_round(config.probe, "light", half)
    assert light["stored"] == 4
    assert sql.sql("select distinct round_at, kind, ms from sh_probe where kind = 'light'") == [(half, "light", None)]
    assert sql.sql("select page, ok, status from sh_probe where kind = 'light' and not ok") == [("סל", False, 502)]
    assert last_run(sql, PROBE_FLOW) == at                                # a light round is no proof of life

    again = collectors.probe_round(config.probe, "full", at)             # the same round from a second worker
    assert again["stored"] == 0
    assert sql.sql("select kind, count(*) from sh_probe group by kind order by kind") == [("full", 4), ("light", 4)]


def test_every_kind_of_failure_is_stored_with_its_code(sql, site):
    config, at = collectors.read_config(), this_minute() - minutes(1)
    site.broken = {"/": {"hang": 2}, "/product-category/sofas/": {"drop": True},
                   "/product/sample-sofa/": {"body": "<html><body>אזל מהמלאי</body></html>"}, "/cart/": {"status": 503}}
    assert collectors.probe_round(config.probe, "full", at, timeout=0.4)["stored"] == 4
    assert sql.sql("select page, ok, fail, status, ms is not null from sh_probe order by fail") == [
        ("קטגוריה", False, "connect", None, True), ("מוצר", False, "content", 200, True),
        ("סל", False, "http", 503, True), ("בית", False, "timeout", None, True)]
    fails = sql.rpc("sh_drill_fails", p_from=at - minutes(1), p_to=at + minutes(1))
    assert {row["page"]: row["kind"] for row in fails} == {
        "בית": "לא ענה בזמן", "קטגוריה": "שגיאת חיבור", "מוצר": "תוכן לא צפוי", "סל": "קוד 503"}
    assert last_run(sql, PROBE_FLOW) == at                                # a round of failures is still a round


def test_the_two_timeouts_of_a_round(site, monkeypatch):
    seen = []
    monkeypatch.setattr(collectors, "probe_check", lambda page, timeout, hosts=(): seen.append(timeout) or {"ms": 1})
    monkeypatch.setattr(db, "rpc", lambda fn, params: {"n": 1})
    collectors.probe_round([page(site, "/")], "full", T0)
    collectors.probe_round([page(site, "/")], "light", T0)
    assert seen == [10, 5]


def test_a_round_ends_even_when_a_check_never_returns(sql, site, monkeypatch):
    real = collectors.probe_check
    monkeypatch.setattr(collectors, "STUCK_GRACE", 0.2)
    monkeypatch.setattr(collectors, "probe_check", lambda page, timeout, hosts=():
                        time.sleep(5) if page["name"] == "סל" else real(page, timeout, hosts))
    started = time.monotonic()
    result = collectors.probe_round(collectors.read_config().probe, "full", this_minute(), timeout=0.3)
    assert time.monotonic() - started < 2
    assert [(row["page"], row["ok"], row["fail"]) for row in result["rows"]] == [
        ("בית", True, None), ("קטגוריה", True, None), ("מוצר", True, None), ("סל", False, "timeout")]
    assert sql.sql("select fail, ms, err from sh_probe where page = 'סל'") == [("timeout", 300, "no answer within 0.3 seconds")]


# ================================================================ 2. probe, alerts and pushes, through the real SQL

def test_a_failing_page_opens_one_alert_and_one_push_and_its_recovery_closes_it(sql, site, phone):
    config, pusher, now = collectors.read_config(), collectors.Pusher(), this_minute()
    cart = site.url + "/cart/"
    collectors.probe_round(config.probe, "full", now - minutes(3))
    assert collectors.alert_tick(pusher) == [] and site.pushes == [] and sql.rpc("sh_alerts_open") == []

    site.broken["/cart/"] = {"status": 502}                               # the page starts failing
    collectors.probe_round(config.probe, "full", now - minutes(2))
    done = collectors.alert_tick(pusher)
    alerts = sql.rpc("sh_alerts_open")
    assert [(a["kind"], a["title"], a["body"], a["acked"]) for a in alerts] == [
        ("down", "האתר לא עונה: סל", "קוד 502\n" + cart, False)]
    assert [(d["title"], d["status"]) for d in done] == [("האתר לא עונה: סל", 200)]
    assert site.pushes == [{                                              # JSON, to the root of the ntfy server
        "path": "/ntfy/", "type": "application/json", "auth": None, "accepted": True,
        "json": {"topic": TOPIC, "title": "האתר לא עונה: סל", "message": "קוד 502\n" + cart, "priority": 4,
                 "tags": ["rotating_light"], "click": "https://dash.example/site"}}]
    assert sql.sql("select event, kind, status, attempts from sh_messages") == [("open", "התראה", 200, 1)]

    collectors.probe_round(config.probe, "full", now - minutes(1))       # still down: no second alert, no second push
    assert collectors.alert_tick(pusher) == [] and len(site.pushes) == 1
    assert sql.sql("select count(*) from sh_alerts") == [(1,)]

    site.broken = {}                                                      # the page recovers
    collectors.probe_round(config.probe, "full", now)
    done = collectors.alert_tick(pusher)
    assert sql.rpc("sh_alerts_open") == []
    assert sql.sql("select count(*) from sh_alerts where closed_at is not null") == [(1,)]
    assert [(d["title"], d["status"]) for d in done] == [("חזר לתקין: סל", 200)]
    assert site.pushes[1]["json"] == {                                    # title and text as the database wrote them
        "topic": TOPIC, "title": "חזר לתקין: סל", "message": "האתר לא עונה: סל\nנמשך דקה", "priority": 2,
        "tags": ["white_check_mark"], "click": "https://dash.example/site"}
    window = {"p_from": now - minutes(5), "p_to": now + minutes(2)}
    assert [(m["kind"], m["title"], m["sent"]) for m in sql.rpc("sh_messages", **window)] == [
        ("חזר לתקין", "חזר לתקין: סל", True), ("התראה", "האתר לא עונה: סל", True)]
    drill = sql.rpc("sh_drill_alert", p_id=alerts[0]["id"])[0]
    assert [(s["event"], s["status"]) for s in drill["sent"]] == [("open", 200), ("close", 200)]


def test_a_light_round_alerts_too(sql, site, phone):
    config, now = collectors.read_config(), this_minute()
    collectors.probe_round(config.probe, "full", now - minutes(1))
    site.broken["/"] = {"hang": 2}
    collectors.probe_round(config.probe, "light", now - timedelta(seconds=30), timeout=0.3)
    collectors.alert_tick(collectors.Pusher())
    assert [push["json"]["title"] for push in site.pushes] == ["האתר לא עונה: בית"]
    assert site.pushes[0]["json"]["message"] == "לא ענה בזמן\n" + site.url + "/"


def test_with_down_after_2_a_single_failure_opens_nothing(sql, site, phone):
    sql.rpc("sh_setup", p_config=site.config(down_after=2))
    config, pusher, now = collectors.read_config(), collectors.Pusher(), this_minute()
    collectors.probe_round(config.probe, "full", now - minutes(3))
    site.broken["/cart/"] = {"status": 500}
    collectors.probe_round(config.probe, "full", now - minutes(2))       # one failure: network noise, perhaps
    assert collectors.alert_tick(pusher) == [] and sql.rpc("sh_alerts_open") == [] and site.pushes == []
    site.broken = {}
    collectors.probe_round(config.probe, "full", now - minutes(1))       # and it answered again
    assert collectors.alert_tick(pusher) == [] and sql.rpc("sh_alerts_open") == []

    site.broken["/cart/"] = {"status": 500}
    collectors.probe_round(config.probe, "light", now - timedelta(seconds=30))
    assert collectors.alert_tick(pusher) == []
    collectors.probe_round(config.probe, "full", now)                    # the second failure in a row
    assert [d["title"] for d in collectors.alert_tick(pusher)] == ["האתר לא עונה: סל"]
    assert [push["json"]["title"] for push in site.pushes] == ["האתר לא עונה: סל"]


def test_three_dead_rounds_in_a_row_are_one_outage(sql, site):
    config, now = collectors.read_config(), this_minute()
    collectors.probe_round(config.probe, "full", now - minutes(5))
    site.broken = {path: {"status": 503} for path in PAGES}              # nothing answers
    for back in (4, 3, 2):
        collectors.probe_round(config.probe, "full", now - minutes(back))
    site.broken = {}
    collectors.probe_round(config.probe, "full", now - minutes(1))
    rows = sql.rpc("sh_availability", p_from=now - minutes(10), p_to=now + minutes(1))
    assert [row for row in rows if row["section"] != "לפי עמוד"] == [{
        "section": "נפילות", "outage_minutes": 3,
        "outage_start_il": il(now - minutes(4)), "outage_end_il": il(now - minutes(1))}]
    assert [(row["page"], row["checks"], row["failed"]) for row in rows if row["section"] == "לפי עמוד"] == [
        ("בית", 5, 3), ("קטגוריה", 5, 3), ("מוצר", 5, 3), ("סל", 5, 3)]


def test_a_failed_push_stays_owed_is_tried_again_and_is_given_up_after_five(sql, site, phone):
    config, pusher, now = collectors.read_config(), collectors.Pusher(), this_minute()
    site.broken["/cart/"] = {"status": 502}
    collectors.probe_round(config.probe, "full", now)
    site.ntfy_status = 500                                                # the push service is down
    window = {"p_from": now - minutes(5), "p_to": now + minutes(5)}

    assert [d["status"] for d in collectors.alert_tick(pusher)] == [500]
    assert sql.sql("select status, attempts from sh_messages") == [(None, 1)]         # still owed
    assert [m["sent"] for m in sql.rpc("sh_messages", **window)] == [False]
    assert collectors.alert_tick(pusher) == [] and len(site.pushes) == 1  # claimed: not offered again at once

    for attempt in (2, 3, 4):
        lapse_claims(sql)
        assert [d["status"] for d in collectors.alert_tick(pusher)] == [500]
        assert sql.sql("select status, attempts from sh_messages") == [(None, attempt)]
    lapse_claims(sql)
    assert [d["status"] for d in collectors.alert_tick(pusher)] == [500]              # the fifth and last
    assert sql.sql("select status, attempts from sh_messages") == [(500, 5)]

    site.ntfy_status = 200                                                # too late: it is not sent after all
    lapse_claims(sql)
    assert collectors.alert_tick(pusher) == []
    assert len(site.pushes) == 5 and not any(push["accepted"] for push in site.pushes)
    assert [(m["title"], m["sent"]) for m in sql.rpc("sh_messages", **window)] == [("האתר לא עונה: סל", False)]
    alert = sql.rpc("sh_alerts_open")[0]["id"]
    assert [(s["event"], s["status"]) for s in sql.rpc("sh_drill_alert", p_id=alert)[0]["sent"]] == [("open", 500)]


def test_a_push_that_fails_once_is_sent_on_the_next_try(sql, site, phone):
    owe(sql, 1)
    pusher = collectors.Pusher()
    site.ntfy_status = 429
    assert [d["status"] for d in collectors.alert_tick(pusher)] == [429]
    site.ntfy_status = 200
    lapse_claims(sql)
    assert [d["status"] for d in collectors.alert_tick(pusher)] == [200]
    assert sql.sql("select status, attempts from sh_messages") == [(200, 2)]
    assert [push["accepted"] for push in site.pushes] == [False, True]


def test_an_unreachable_push_service_is_a_failed_attempt_and_the_topic_is_never_logged(sql, site, phone, monkeypatch, caplog):
    monkeypatch.setenv("NTFY_URL", "http://127.0.0.1:%d" % closed_port())
    owe(sql, 1)
    assert [d["status"] for d in collectors.alert_tick(collectors.Pusher())] == [599]
    assert sql.sql("select status, attempts from sh_messages") == [(None, 1)]
    assert "push: ntfy could not be reached (ConnectionRefusedError)" in caplog.text and TOPIC not in caplog.text


def test_a_refused_push_is_logged_with_its_status_and_never_with_the_topic(sql, site, phone, caplog):
    owe(sql, 2)
    pusher = collectors.Pusher()
    site.ntfy_status = 403
    assert [d["status"] for d in collectors.alert_tick(pusher)] == [403, 403]
    assert caplog.text.count("push: ntfy refused the push (HTTP 403: the fake ntfy was told to refuse)") == 2
    assert [record.levelname for record in caplog.records if "refused the push" in record.message] == ["WARNING"] * 2
    site.ntfy_status, site.ntfy_error = 429, "topic %s: too many requests" % TOPIC      # an answer that names the topic
    lapse_claims(sql)
    collectors.alert_tick(pusher)
    assert "push: ntfy refused the push (HTTP 429: topic (topic): too many requests)" in caplog.text
    assert TOPIC not in caplog.text
    site.ntfy_status = 200                                                # an accepted push says nothing
    lapse_claims(sql)
    before = len(caplog.records)
    assert [d["status"] for d in collectors.alert_tick(pusher)] == [200, 200] and len(caplog.records) == before


def test_without_ntfy_url_the_push_goes_to_ntfy_sh(monkeypatch):
    for name in ("NTFY_URL", "NTFY_TOKEN", "DASHBOARD_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    asked = []
    monkeypatch.setattr(collectors, "fetch", lambda url, **how: asked.append((url, how))
                        or collectors.Answer(200, _headers({}), b"{}", 0.1))
    assert collectors.Pusher().publish("כותרת", "גוף") == 200
    url, how = asked[0]
    assert url == "https://ntfy.sh/" and how["method"] == "POST" and how["redirects"] == 0
    assert not how.get("public") and not how.get("hosts")                 # a service of the environment, not the site
    assert json.loads(how["data"]) == {"topic": TOPIC, "title": "כותרת", "message": "גוף", "priority": 3, "tags": []}


def test_without_a_topic_nothing_is_sent_and_every_message_is_settled_as_not_sent(sql, site, monkeypatch):
    monkeypatch.setenv("NTFY_URL", site.url + "/ntfy")                    # a server, and no topic
    config, now = collectors.read_config(), this_minute()
    site.broken["/cart/"] = {"status": 502}
    collectors.probe_round(config.probe, "full", now)
    assert [(d["title"], d["status"]) for d in collectors.alert_tick(collectors.Pusher())] == [("האתר לא עונה: סל", 0)]
    assert site.pushes == []
    assert sql.sql("select status from sh_messages") == [(0,)]
    assert [m["sent"] for m in sql.rpc("sh_messages", p_from=now - minutes(5), p_to=now + minutes(5))] == [False]
    assert len(sql.rpc("sh_alerts_open")) == 1                            # the alert itself is on the screen


def test_the_token_goes_in_the_authorization_header_and_the_link_needs_a_dashboard(sql, site, monkeypatch):
    monkeypatch.setenv("NTFY_URL", site.url + "/ntfy/")
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("NTFY_TOKEN", "tk_test_token")
    assert collectors.Pusher().publish("כותרת " + "א" * 300, "ב" * 2000, 9, ["bell"]) == 200
    sent = site.pushes[0]
    assert (sent["path"], sent["auth"], sent["type"]) == ("/ntfy/", "Bearer tk_test_token", "application/json")
    assert sorted(sent["json"]) == ["message", "priority", "tags", "title", "topic"]              # no click link
    assert len(sent["json"]["title"]) == 199 and len(sent["json"]["message"]) == 1499             # ntfy's limits
    assert sent["json"]["priority"] == 3 and sent["json"]["tags"] == ["bell"]                     # 9 is no priority


def test_the_push_of_each_kind_of_message():
    def as_push(event, kind, priority):
        return collectors._as_push({"title": "כותרת", "msg": "גוף", "priority": priority, "kind": kind, "event": event})

    assert as_push("open", "התראה", 4) == ("כותרת", "גוף", 4, ["rotating_light"])        # down, silent
    assert as_push("open", "התראה", 3) == ("כותרת", "גוף", 3, ["warning"])               # slow, certificate
    assert as_push("close", "חזר לתקין", 2) == ("כותרת", "גוף", 2, ["white_check_mark"])     # no label is added
    assert as_push("morning", "בוקר", 2) == ("כותרת", "גוף", 2, ["sunrise"])
    assert collectors._as_push({"title": "כותרת", "msg": None, "priority": 3, "event": "open"})[1] == "כותרת"


def test_at_most_30_pushes_an_hour_and_a_message_that_waited_an_hour_is_not_sent(sql, site, phone):
    clock = Clock(1000.0)
    pusher = collectors.Pusher(clock)
    owe(sql, 35)
    done = collectors.alert_tick(pusher)
    assert len(done) == 30 and all(d["status"] == 200 for d in done)
    assert [push["json"]["title"] for push in site.pushes] == ["הודעה %d" % i for i in range(1, 31)]      # oldest first
    assert sql.sql("select count(*) filter (where status = 200), count(*) filter (where status is null)"
                   " from sh_messages") == [(30, 5)]

    lapse_claims(sql)
    clock.at += 600                                                       # ten minutes later the hour is still full
    assert collectors.alert_tick(pusher) == [] and len(site.pushes) == 30

    owe(sql, 1, first=36)                                                 # a worker that just started has no memory,
    lapse_claims(sql)                                                     # but the message log has
    assert collectors.alert_tick(collectors.Pusher()) == [] and len(site.pushes) == 30

    # An hour and a minute after the first tick. (The log's clock is moved by hand.)
    clock.at += 3060
    sql.sql("update sh_messages set at = at - interval '61 minutes', claimed_at = null")
    owe(sql, 1, first=37)
    done = collectors.alert_tick(pusher)
    assert sorted((d["title"], d["status"]) for d in done) == sorted(
        [("הודעה %d" % i, 0) for i in (31, 32, 33, 34, 35)]              # they waited more than an hour
        + [("הודעה 36", 200), ("הודעה 37", 200)])                        # and the hour has room again
    assert [push["json"]["title"] for push in site.pushes[30:]] == ["הודעה 36", "הודעה 37"]
    assert sql.sql("select status, count(*) from sh_messages group by status order by status") == [(0, 5), (200, 32)]


def test_nothing_is_pushed_after_the_deadline_of_a_tick(sql, site, phone):
    owe(sql, 2)
    pusher = collectors.Pusher()
    assert collectors.alert_tick(pusher, deadline=time.time() - 1) == [] and site.pushes == []
    assert sql.sql("select count(*) from sh_messages where status is null and attempts = 0") == [(2,)]
    lapse_claims(sql)
    assert len(collectors.alert_tick(pusher, deadline=time.time() + 30)) == 2 and len(site.pushes) == 2


def test_two_workers_that_overlap_store_the_round_once_and_push_once(sql, site, phone):
    config, at = collectors.read_config(), this_minute()
    site.broken["/cart/"] = {"status": 502}
    together, results = threading.Barrier(2), []

    def worker():
        pusher = collectors.Pusher()
        together.wait()
        stored = collectors.probe_round(config.probe, "full", at)["stored"]
        results.append((stored, len(collectors.alert_tick(pusher))))

    workers = [threading.Thread(target=worker) for _ in range(2)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    assert sorted(stored for stored, _ in results) == [0, 4]              # the round was stored by one of them
    assert sorted(pushed for _, pushed in results) == [0, 1]              # and the message handed to one of them
    assert [push["json"]["title"] for push in site.pushes] == ["האתר לא עונה: סל"]
    assert sql.sql("select count(*) from sh_probe") == [(4,)]
    assert sql.sql("select count(*) from sh_alerts") == [(1,)]
    assert sql.sql("select status, attempts from sh_messages") == [(200, 1)]


def test_the_heartbeat_is_one_request_and_its_address_is_never_logged(site, monkeypatch, caplog):
    collectors.heartbeat()                                                # not configured: nothing happens
    assert site.hits == []
    monkeypatch.setenv("HEARTBEAT_URL", site.url + "/hb")
    collectors.heartbeat()
    assert [(method, path) for method, path, _ in site.hits] == [("GET", "/hb")]
    monkeypatch.setenv("HEARTBEAT_URL", "http://127.0.0.1:%d/ping/secret-uuid" % closed_port())
    collectors.heartbeat()                                                # a dead service costs a log line, no more
    assert "heartbeat: the ping did not get through (ConnectionRefusedError)" in caplog.text
    assert "secret-uuid" not in caplog.text


# ================================================================ 3. lab speed (§7.6)

def test_the_stored_columns_of_a_lighthouse_13_answer():
    assert collectors.speed_row(fixture("psi_lighthouse13.json")) == {
        "ok": True, "err": None, "score": 32, "lcp_ms": 10885, "cls": 0.1, "ttfb_ms": 8, "bytes": 1871037,
        "crux_category": "FAST", "crux_lcp_ms": 2140, "lh_version": "13.6.0",
        "opps": [{"id": "cache-insight", "title": "Use efficient cache lifetimes", "ms": 3600},        # insight audits:
                 {"id": "image-delivery-insight", "title": "Improve image delivery", "ms": 1200},     # metricSavings
                 {"id": "mainthread-work-breakdown", "title": "Minimize main-thread work", "ms": 1050},
                 {"id": "render-blocking-insight", "title": "Render-blocking requests", "ms": 850},
                 {"id": "unminified-javascript", "title": "Minify JavaScript", "ms": 580},           # classic:
                 {"id": "unused-javascript", "title": "Reduce unused JavaScript", "ms": 580}]}       # overallSavingsMs
    # the seventh, legacy-javascript-insight (300 ms), is cut: six reasons are kept


def test_the_stored_columns_of_a_lighthouse_12_answer():
    assert collectors.speed_row(fixture("psi_lighthouse12.json")) == {
        "ok": True, "err": None, "score": 32, "lcp_ms": 10894, "cls": 0.1, "ttfb_ms": 4, "bytes": 1871037,
        "crux_category": "FAST", "crux_lcp_ms": 2140, "lh_version": "12.8.2",
        "opps": [{"id": "cache-insight", "title": "Use efficient cache lifetimes", "ms": 3250},
                 {"id": "uses-responsive-images", "title": "Properly size images", "ms": 2100},
                 {"id": "image-delivery-insight", "title": "Improve image delivery", "ms": 1950},
                 {"id": "modern-image-formats", "title": "Serve images in next-gen formats", "ms": 1650},
                 {"id": "uses-text-compression", "title": "Enable text compression", "ms": 1140},
                 {"id": "mainthread-work-breakdown", "title": "Minimize main-thread work", "ms": 1000}]}
    # cut: unused-javascript (690), unminified-javascript (540), legacy-javascript (240)


@pytest.mark.parametrize("name", ["psi_lighthouse13.json", "psi_lighthouse12.json"])
def test_passed_audits_and_the_metrics_themselves_are_not_reasons(name):
    answer = fixture(name)
    audits = answer["lighthouseResult"]["audits"]
    # Lighthouse's own sample: these passed (score 1) and still carry a time that the rule would take
    assert audits["bootup-time"]["score"] == 1 and audits["bootup-time"]["metricSavings"]["TBT"] >= 1000
    assert audits["long-tasks"]["score"] == 1 and audits["long-tasks"]["metricSavings"]["TBT"] >= 1000
    assert audits["network-server-latency"]["score"] == 1 and audits["network-server-latency"]["numericValue"] > 500
    assert audits["metrics"]["score"] == 1 and audits["metrics"]["numericUnit"] == "millisecond"
    # and these failed, with a time, and are the measurement itself
    assert audits["max-potential-fid"]["score"] == 0 and audits["interactive"]["score"] < 0.9
    listed = {opp["id"] for opp in collectors.speed_row(answer)["opps"]}
    assert not listed & {"bootup-time", "long-tasks", "network-server-latency", "metrics", "server-response-time",
                         "redirects", "max-potential-fid", "interactive", "largest-contentful-paint",
                         "first-contentful-paint", "speed-index", "total-blocking-time",
                         "largest-contentful-paint-element", "inp-breakdown-insight", "document-latency-insight"}


def test_the_rule_for_what_slows_a_page():
    def audit(score=0, mode="metricSavings", **more):
        return {"title": "כותרת", "score": score, "scoreDisplayMode": mode, **more}

    audits = {
        "overall-first": audit(details={"overallSavingsMs": 300.4}, metricSavings={"LCP": 900}),
        "largest-metric": audit(score=0.5, metricSavings={"LCP": 100, "FCP": 450, "CLS": 9999}),      # CLS is no time
        "numeric-ms": audit(score=0.89, numericValue=120.6, numericUnit="millisecond"),
        "numeric-bytes": audit(numericValue=50000, numericUnit="byte"),
        "passed": audit(score=0.9, details={"overallSavingsMs": 700}),
        "no-score": audit(score=None, numericValue=800, numericUnit="millisecond"),
        "not-applicable": audit(mode="notApplicable", details={"overallSavingsMs": 700}),
        "manual": audit(mode="manual", details={"overallSavingsMs": 700}),
        "error": audit(mode="error", details={"overallSavingsMs": 700}),
        "zero-saving": audit(metricSavings={"LCP": 0}, numericValue=500, numericUnit="millisecond"),
        "largest-contentful-paint": audit(numericValue=5000, numericUnit="millisecond"),
        # hostile shapes
        "not-an-audit": "text", "text-score": audit(score="0", details={"overallSavingsMs": 700}),
        "text-saving": audit(details={"overallSavingsMs": "700"}), "details-list": audit(details=[1], metricSavings=7),
        "no-title": {"score": 0, "details": {"overallSavingsMs": 50}},
    }
    assert collectors._opps(audits) == [
        {"id": "largest-metric", "title": "כותרת", "ms": 450}, {"id": "overall-first", "title": "כותרת", "ms": 300},
        {"id": "numeric-ms", "title": "כותרת", "ms": 121}, {"id": "no-title", "title": None, "ms": 50}]
    many = {"audit-%02d" % i: audit(details={"overallSavingsMs": 100 + i}) for i in range(12)}
    assert [opp["ms"] for opp in collectors._opps(many)] == [111, 110, 109, 108, 107, 106]      # the six largest


def test_field_data_is_optional_and_whole_site_numbers_are_not_the_pages():
    answer = fixture("psi_lighthouse13.json")
    answer["loadingExperience"]["origin_fallback"] = True                 # too little traffic on this page
    row = collectors.speed_row(answer)
    assert (row["ok"], row["crux_category"], row["crux_lcp_ms"], row["lcp_ms"]) == (True, None, None, 10885)
    answer["loadingExperience"] = {"initial_url": "https://example.co.il/"}
    row = collectors.speed_row(answer)
    assert (row["ok"], row["crux_category"], row["crux_lcp_ms"]) == (True, None, None)
    answer["loadingExperience"] = {"metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"category": "<b>", "percentile": "9"}}}
    row = collectors.speed_row(answer)
    assert (row["crux_category"], row["crux_lcp_ms"]) == (None, None)     # only the three known words, only numbers


def test_a_missing_value_is_stored_as_null_never_as_zero():
    audits = {"largest-contentful-paint": {"numericValue": 2412.6}}
    assert collectors.speed_row({"lighthouseResult": {"audits": audits}}) == {
        "ok": True, "err": None, "score": None, "lcp_ms": 2413, "cls": None, "ttfb_ms": None, "bytes": None,
        "crux_category": None, "crux_lcp_ms": None, "opps": [], "lh_version": None}
    audits["metrics"] = {"details": {"items": [{"timeToFirstByte": 431.2}]}}          # the fallback of ttfb_ms
    assert collectors.speed_row({"lighthouseResult": {"audits": audits}})["ttfb_ms"] == 431
    assert collectors.speed_row({"lighthouseResult": {"audits": audits, "categories": {"performance": {"score": 0}}}})["score"] == 0


@pytest.mark.parametrize("answer, err", [
    ({"lighthouseResult": {"runtimeError": {"code": "NO_FCP", "message": "The page did not paint any content."},
                           "audits": {"largest-contentful-paint": {"numericValue": 2400}}}},
     "NO_FCP: The page did not paint any content."),
    ({"lighthouseResult": {"runtimeError": {"code": "NO_ERROR"}, "audits": {}}}, "the answer has no Largest Contentful Paint"),
    ({"lighthouseResult": []}, "the answer has no Largest Contentful Paint"),
    ({}, "the answer has no Largest Contentful Paint"),
])
def test_a_test_that_failed_is_a_failed_run(answer, err):
    assert collectors.speed_row(answer) == {"ok": False, "err": err}


def test_one_call_asks_for_the_phone_test_of_one_page_in_hebrew(site):
    row = collectors.speed_measure("https://example.co.il/product/x/", "mobile", KEY)
    assert row["ok"] and row["lcp_ms"] == 10885
    assert site.psi_calls == [{"url": "https://example.co.il/product/x/", "strategy": "mobile",
                               "category": "performance", "locale": "he", "key": KEY}]


def test_pagespeed_is_asked_at_google_unless_the_environment_names_another_address(site, monkeypatch):
    assert collectors.psi_url() == site.url + "/pagespeedonline/v5/runPagespeed"       # what the fixture set
    monkeypatch.setenv("PAGESPEED_URL", "  ")
    assert collectors.psi_url() == "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    monkeypatch.delenv("PAGESPEED_URL")
    assert collectors.psi_url() == "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def test_a_lighthouse_failure_is_stored_as_a_failed_run_without_a_second_try(site):
    site.psi = "lighthouse_error"
    row = collectors.speed_measure("https://example.co.il/", "mobile", KEY)
    assert row == {"ok": False, "err": "Lighthouse returned error: ERRORED_DOCUMENT_REQUEST. Lighthouse was unable to "
                                       "reliably load the page you requested. Make sure you are testing the correct URL "
                                       "and that the server is properly responding to all requests. (Status code: 403)"}
    assert len(site.psi_calls) == 1
    site.psi = "runtime_error"                                            # the same failure, on a 200
    assert collectors.speed_measure("https://example.co.il/", "mobile", KEY) == {
        "ok": False, "err": "NO_FCP: The page did not paint any content. Please ensure you keep the browser window "
                            "in the foreground during the load and try again. (NO_FCP)"}
    assert len(site.psi_calls) == 2


@pytest.mark.parametrize("mode, err", [
    ("http500", "HTTP 500: Unable to process request. Please wait a while and try again."),
    ("quota_minute", "HTTP 429: Quota exceeded for quota metric 'Queries' and limit 'Queries per minute' of service "
                     "'pagespeedonline.googleapis.com' for consumer 'project_number:583797351490'."),
])
def test_a_refusal_that_may_pass_is_tried_three_times_and_then_stored_as_a_failed_run(site, mode, err):
    site.psi = mode
    assert collectors.speed_measure("https://example.co.il/", "mobile", KEY) == {"ok": False, "err": err}
    assert len(site.psi_calls) == 3
    site.psi, site.psi_calls = ["http500", "lighthouse13"], []           # the second try succeeds
    assert collectors.speed_measure("https://example.co.il/", "mobile", KEY)["ok"] is True
    assert len(site.psi_calls) == 2


def test_when_pagespeed_cannot_be_reached_the_run_fails_and_the_key_is_not_in_its_error(site, monkeypatch):
    monkeypatch.setenv("PAGESPEED_URL", "http://127.0.0.1:%d/run" % closed_port())
    row = collectors.speed_measure("https://example.co.il/", "mobile", KEY)
    assert row["ok"] is False and row["err"].startswith("ConnectionRefusedError") and KEY not in row["err"]


def test_the_daily_quota_and_a_refused_key_stop_the_collector_without_a_second_try(site):
    site.psi = "quota_day"
    with pytest.raises(collectors.SpeedStopped) as stopped:
        collectors.speed_measure("https://example.co.il/", "mobile", KEY)
    assert stopped.value.daily is True and "Queries per day" in str(stopped.value) and len(site.psi_calls) == 1
    site.psi = "bad_key"
    with pytest.raises(collectors.SpeedStopped) as stopped:
        collectors.speed_measure("https://example.co.il/", "mobile", KEY)
    assert stopped.value.daily is False and str(stopped.value) == "API key not valid. Please pass a valid API key."
    assert len(site.psi_calls) == 2
    site.psi = "api_disabled"                                             # a 403: the API is not enabled for the key
    with pytest.raises(collectors.SpeedStopped) as stopped:
        collectors.speed_measure("https://example.co.il/", "mobile", KEY)
    assert PSI_ERRORS["api_disabled"][0] == 403 and stopped.value.daily is False
    assert "has not been used in project" in str(stopped.value) and len(site.psi_calls) == 3      # one call, no retry


def test_a_core_round_stores_one_run_per_core_page_under_the_rounds_time(sql, site):
    config = collectors.read_config()
    rows = collectors.speed_core(config.core, "mobile", T0, KEY)
    assert len(rows) == 5 and [call["url"] for call in site.psi_calls] == [site.url + path for path in PAGES]
    assert sorted(sql.sql("select page, url, at, strategy, source, ok, score, lcp_ms, cls::float, ttfb_ms, bytes,"
                          " crux_category, crux_lcp_ms, lh_version, jsonb_array_length(opps) from sh_speed")) == sorted(
        (name, site.url + path, T0, "mobile", "core", True, 32, 10885, 0.1, 8, 1871037, "FAST", 2140, "13.6.0", 6)
        for path, name in PAGES.items())
    assert sql.sql("select opps -> 0 from sh_speed limit 1") == [
        ({"id": "cache-insight", "title": "Use efficient cache lifetimes", "ms": 3600},)]
    assert last_run(sql, CORE_FLOW) == T0 and last_run(sql, ROTATION_FLOW) is None

    collectors.speed_core(config.core, "mobile", T0, KEY)                # the same round from a second worker
    assert sql.sql("select count(*) from sh_speed") == [(5,)]
    collectors.speed_core(config.core[:1], "desktop", T0, KEY)
    assert sql.sql("select strategy, count(*) from sh_speed group by strategy order by strategy") == [
        ("desktop", 1), ("mobile", 5)]
    assert site.psi_calls[-1]["strategy"] == "desktop"


def test_failed_runs_are_stored_and_are_no_proof_of_life(sql, site):
    site.psi = "lighthouse_error"
    rows = collectors.speed_core(collectors.read_config().core[:2], "mobile", T0, KEY)
    assert [row["ok"] for row in rows] == [False, False]
    assert sql.sql("select page, ok, lcp_ms, left(err, 25) from sh_speed order by page") == [
        ("בית", False, None, "Lighthouse returned error"), ("קטגוריה", False, None, "Lighthouse returned error")]
    assert last_run(sql, CORE_FLOW) is None
    runs = sql.rpc("sh_drill_runs", p_from=T0 - minutes(1), p_to=T0 + minutes(1), p_url=site.url + "/")
    assert [(run["ok"], run["err"][:25]) for run in runs] == [(False, "Lighthouse returned error")]


def test_the_rotation_measures_the_pages_that_waited_longest_on_a_phone(sql, site):
    pages = ["%s/product/item-%d/" % (site.url, i) for i in range(1, 6)]
    sql.rpc("sh_sitemap_set", p_urls=pages + [site.url + "/"])           # the home page is a core page: no turn
    first = collectors.speed_rotation(2, T0, KEY)
    second = collectors.speed_rotation(2, T0 + minutes(5), KEY)
    third = collectors.speed_rotation(2, T0 + minutes(10), KEY)
    assert [[row["url"] for row in rows] for rows in (first, second)] == [pages[0:2], pages[2:4]]
    assert [row["url"] for row in third] == [pages[0], pages[4]]         # the last one, and around again
    assert sql.sql("select distinct page, strategy, source, ok from sh_speed") == [(None, "mobile", "rotation", True)]
    assert sql.sql("select at, count(*) from sh_speed group by at order by at") == [
        (T0, 2), (T0 + minutes(5), 2), (T0 + minutes(10), 2)]
    assert all(call["strategy"] == "mobile" for call in site.psi_calls)
    assert last_run(sql, ROTATION_FLOW) == T0 + minutes(10) and last_run(sql, CORE_FLOW) is None
    cover = [row for row in sql.rpc("sh_speed", p_from=T0 - minutes(1), p_to=T0 + minutes(11)) if row["section"] == "כיסוי"]
    assert (cover[0]["checks"], cover[0]["slow_runs"]) == (5, 5)


def test_the_schedule_phone_every_15_minutes_desktop_every_hour_rotation_every_5(sql, site):
    sql.rpc("sh_sitemap_set", p_urls=["%s/product/item-%d/" % (site.url, i) for i in range(1, 9)])
    config, clock = collectors.read_config(), Clock(T0 + timedelta(seconds=40))
    speed = collectors.SpeedSchedule(KEY, clock)

    def calls():
        made, site.psi_calls = [(call["strategy"], call["url"].replace(site.url, "")) for call in site.psi_calls], []
        return made

    core = list(PAGES)
    assert speed.step(config) == ["core pages, phone", "core pages, desktop", "rotation"]
    assert calls() == ([("mobile", path) for path in core] + [("desktop", path) for path in core]
                       + [("mobile", "/product/item-1/"), ("mobile", "/product/item-2/")])
    assert speed.step(config) == [] and calls() == []                    # the same slots: nothing is owed
    clock.at = T0 + minutes(4)
    assert speed.step(config) == []
    clock.at = T0 + minutes(5)
    assert speed.step(config) == ["rotation"]
    assert calls() == [("mobile", "/product/item-3/"), ("mobile", "/product/item-4/")]
    clock.at = T0 + minutes(15) + timedelta(seconds=7)
    assert speed.step(config) == ["core pages, phone", "rotation"]
    assert calls()[:5] == [("mobile", path) for path in core]
    clock.at = T0 + minutes(59)
    assert speed.step(config) == ["core pages, phone", "rotation"]       # the slots of :45 and :55
    clock.at = T0 + minutes(60)
    assert speed.step(config) == ["core pages, phone", "core pages, desktop", "rotation"]

    # every run carries the start of its slot
    assert sql.sql("select source, strategy, at, count(*) from sh_speed group by 1, 2, 3 order by 3, 1, 2") == [
        ("core", "desktop", T0, 5), ("core", "mobile", T0, 5), ("rotation", "mobile", T0, 2),
        ("rotation", "mobile", T0 + minutes(5), 2),
        ("core", "mobile", T0 + minutes(15), 5), ("rotation", "mobile", T0 + minutes(15), 2),
        ("core", "mobile", T0 + minutes(45), 5), ("rotation", "mobile", T0 + minutes(55), 2),
        ("core", "desktop", T0 + minutes(60), 5), ("core", "mobile", T0 + minutes(60), 5),
        ("rotation", "mobile", T0 + minutes(60), 2)]
    assert sql.sql("select count(*) from sh_speed where source = 'core' and page is null"
                   " or source = 'rotation' and page is not null") == [(0,)]


def test_a_used_up_daily_quota_stops_the_measuring_until_the_quota_starts_again(sql, site, caplog):
    config, clock = collectors.read_config(), Clock(T0)                  # 02:00 in California
    speed = collectors.SpeedSchedule(KEY, clock)
    site.psi = "quota_day"
    assert speed.step(config) == [] and len(site.psi_calls) == 1         # one refusal, and no round after it
    assert "the daily PageSpeed quota is used up, measuring again after 2026-11-14 08:00 UTC" in caplog.text
    site.psi = "lighthouse13"
    for later in (minutes(15), timedelta(hours=12), timedelta(hours=21, minutes=59)):
        clock.at = T0 + later
        assert speed.step(config) == []
    assert len(site.psi_calls) == 1 and sql.sql("select count(*) from sh_speed") == [(0,)]
    clock.at = T0 + timedelta(hours=22)                                  # midnight in California
    assert speed.step(config) == ["core pages, phone", "core pages, desktop", "rotation"]
    assert sql.sql("select count(*) from sh_speed where ok") == [(10,)]


@pytest.mark.parametrize("refusal", ["bad_key", "api_disabled"])
def test_a_refused_key_is_asked_about_once_an_hour_and_is_never_logged(sql, site, caplog, refusal):
    config, clock = collectors.read_config(), Clock(T0)
    speed = collectors.SpeedSchedule(KEY, clock)
    site.psi = refusal
    assert speed.step(config) == [] and len(site.psi_calls) == 1         # one refusal, and no round after it
    for later in (minutes(5), minutes(15), minutes(59)):
        clock.at = T0 + later
        assert speed.step(config) == []
    assert len(site.psi_calls) == 1                                       # nothing is asked within the hour
    clock.at = T0 + minutes(60)
    assert speed.step(config) == [] and len(site.psi_calls) == 2         # one call an hour asks again
    clock.at = T0 + minutes(119)
    assert speed.step(config) == [] and len(site.psi_calls) == 2
    assert sql.sql("select count(*) from sh_speed") == [(0,)]
    assert caplog.text.count("PageSpeed does not accept the key") == 2 and KEY not in caplog.text
    assert {record.levelname for record in caplog.records if "PageSpeed" in record.message} == {"ERROR"}

    site.psi = "lighthouse13"                                            # the API was enabled in Google's console:
    clock.at = T0 + minutes(120)                                         # the measuring comes back by itself
    assert speed.step(config) == ["core pages, phone", "core pages, desktop", "rotation"]
    assert sql.sql("select count(*) from sh_speed where ok") == [(10,)]


def test_one_failing_round_does_not_cost_the_others(sql, site, monkeypatch, caplog):
    sql.rpc("sh_sitemap_set", p_urls=[site.url + "/product/item-1/"])
    speed = collectors.SpeedSchedule(KEY, Clock(T0))
    monkeypatch.setattr(collectors, "speed_core", lambda *args: 1 / 0)
    assert speed.step(collectors.read_config()) == ["rotation"]
    assert caplog.text.count("speed: core pages, phone failed: ZeroDivisionError") == 1


# ================================================================ 4. the sitemap (§7.7)

def paths(site, pages):
    return [url.replace(site.url, "") for url in pages]


def test_the_sitemap_is_found_through_robots_txt_and_read_whole(site):
    assert paths(site, collectors.sitemap_load(site.url)) == [
        "/", "/about/", "/%D7%A6%D7%95%D7%A8-%D7%A7%D7%A9%D7%A8/", "/%D7%A2%D7%92%D7%9C%D7%94/",   # page-sitemap.xml
        "/product/sample-sofa/", "/product/armchair/", "/product-category/sofas/",                 # the gzipped child
        "/landing/"]                                                                               # the child with a query
    # Not there: the cart, the checkout, the account, search, feed, tag, author and paginated pages,
    # the address with a query string, the one with a fragment, the PDF, the page of another host,
    # and the pictures inside every <url>.
    assert [path for _, path, _ in site.hits] == [
        "/robots.txt", "/sitemap_index.xml", "/page-sitemap.xml", "/product-sitemap.xml",
        "/extra-sitemap.xml?from=1&to=9"]                                 # the child's address exactly as written
    assert site.files["/product-sitemap.xml"][1][:2] == b"\x1f\x8b"      # gzip, though its name does not say so


def test_the_sites_own_private_slugs_are_dropped_too(sql, site):
    sql.rpc("sh_setup", p_config=site.config(private_paths=["עגלה", "About"]))
    config = collectors.read_config()
    assert {"עגלה", "about", "cart", "checkout", "my-account"} <= config.private
    assert paths(site, collectors.sitemap_load(site.url, config.private)) == [
        "/", "/%D7%A6%D7%95%D7%A8-%D7%A7%D7%A9%D7%A8/", "/product/sample-sofa/", "/product/armchair/",
        "/product-category/sofas/", "/landing/"]


def test_without_a_sitemap_line_the_usual_addresses_are_tried_in_order(site):
    site.files["/robots.txt"] = ("text/plain", b"User-agent: *\nDisallow: /cart/\n")
    assert len(collectors.sitemap_load(site.url)) == 8                    # /sitemap_index.xml
    site.files["/sitemap_index.xml"] = ("text/html", b"<html><body>Just a moment...</body></html>")   # a firewall
    assert paths(site, collectors.sitemap_load(site.url)) == ["/", "/wp-page/"]                       # /wp-sitemap.xml
    del site.files["/wp-sitemap.xml"]
    del site.files["/robots.txt"]                                         # no robots.txt at all
    assert paths(site, collectors.sitemap_load(site.url)) == ["/", "/plain-page/"]     # /sitemap.xml; home is added
    del site.files["/sitemap.xml"]
    with pytest.raises(collectors.CollectorError, match="no sitemap"):
        collectors.sitemap_load(site.url)


def test_several_sitemap_lines_and_a_line_for_another_host(site):
    site.files["/robots.txt"] = ("text/plain", (
        "sitemap: %s/sitemap.xml\nSITEMAP:/wp-sitemap.xml\nSitemap: https://other.example/sitemap.xml\n" % site.url).encode())
    assert paths(site, collectors.sitemap_load(site.url)) == ["/", "/plain-page/", "/wp-page/"]
    assert "other.example" not in str(site.hits)


@pytest.mark.parametrize("break_it, message", [
    (lambda site: site.broken.update({"/product-sitemap.xml": {"status": 500}}), "HTTP 500 for"),
    (lambda site: site.files.pop("/extra-sitemap.xml?from=1&to=9"), "HTTP 404 for"),
    (lambda site: site.files.update({"/page-sitemap.xml": ("application/xml", b"<urlset><url><loc>x</loc>")}), "not XML"),
    (lambda site: site.files.update({"/page-sitemap.xml": ("text/html", b"<html><body>blocked</body></html>")}),
     "not a sitemap"),
    (lambda site: site.files.update({"/page-sitemap.xml": (
        "application/xml", b'<!DOCTYPE urlset [<!ENTITY a "aaaa">]><urlset><url><loc>&a;</loc></url></urlset>')}),
     "declares entities"),
    (lambda site: site.files.update({"/page-sitemap.xml": ("application/xml", "<urlset/>".encode("utf-16"))}),
     "not UTF-8"),
    # UTF-16 without its byte-order mark is valid UTF-8 (with a NUL in every pair), and the bytes
    # "<!ENTITY" are not in it: only the NUL test refuses this entity bomb before the parser sees it
    (lambda site: site.files.update({"/page-sitemap.xml": ("application/xml", (
        '<?xml version="1.0" encoding="UTF-16LE"?><!DOCTYPE urlset [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        '<urlset><url><loc>&b;</loc></url></urlset>').encode("utf-16-le"))}), "not UTF-8"),
    (lambda site: site.files.update({"/product-sitemap.xml": ("application/xml", b"\x1f\x8b\x08 not gzip")}),
     "gzip file that cannot be opened"),
    (lambda site: site.files.update({"/sitemap_index.xml": sitemap_index(
        site.url, "/page-sitemap.xml", "http://169.254.169.254/latest/meta-data/")}), "a sitemap on another host"),
])
def test_one_file_that_fails_aborts_the_whole_load(sql, site, break_it, message):
    known = [site.url + "/", site.url + "/old-page/"]
    sql.rpc("sh_sitemap_set", p_urls=known)
    sql.sql("update sh_flows set last_at = null")
    break_it(site)
    with pytest.raises(collectors.CollectorError, match=message):
        collectors.sitemap_job(collectors.read_config(), T0)
    assert sql.sql("select url from sh_site_pages where active order by url") == [(url,) for url in sorted(known)]
    assert last_run(sql, SITEMAP_FLOW) is None                            # yesterday's list, and no proof of life


def test_a_file_larger_than_the_limit_is_refused(site, monkeypatch):
    monkeypatch.setattr(collectors, "SITEMAP_BYTES", 2000)
    bomb = urlset(site.url, *("/page-%d/" % i for i in range(200)))[1]
    assert len(gzip.compress(bomb)) < 2000 < len(bomb)                    # small on the wire, large when opened
    site.files["/product-sitemap.xml"] = ("application/xml", gzip.compress(bomb))
    with pytest.raises(collectors.CollectorError, match=r"a sitemap file of more than 2000 bytes \(SH_SITEMAP_MB"):
        collectors.sitemap_load(site.url)


def test_a_sitemap_without_pages_is_refused(sql, site):
    site.files["/robots.txt"] = ("text/plain", ("Sitemap: %s/sitemap.xml\n" % site.url).encode())
    site.files["/sitemap.xml"] = urlset(site.url, "/cart/", "/checkout/?x=1")
    with pytest.raises(collectors.CollectorError, match="the sitemap lists no pages"):
        collectors.sitemap_job(collectors.read_config(), T0)
    assert sql.sql("select count(*) from sh_site_pages") == [(0,)]


def test_a_list_under_half_of_the_known_one_is_refused(sql, site):
    known = ["%s/known-%d/" % (site.url, i) for i in range(17)]
    sql.rpc("sh_sitemap_set", p_urls=known)
    with pytest.raises(collectors.CollectorError, match="the sitemap lists 8 pages and 17 are known"):
        collectors.sitemap_job(collectors.read_config(), T0)
    assert sql.sql("select count(*) from sh_site_pages where active") == [(17,)]
    sql.rpc("sh_sitemap_set", p_urls=known[:16])                          # 8 of 16 is half: accepted
    assert collectors.sitemap_job(collectors.read_config(), T0)["pages"] == 8
    assert sql.sql("select count(*) from sh_site_pages where active") == [(8,)]


def test_the_sitemap_job_stores_the_list_in_one_call(sql, site):
    result = collectors.sitemap_job(collectors.read_config(), T0)
    assert result == {"n": 8, "pages": 8}
    assert sql.sql("select count(*) from sh_site_pages where active") == [(8,)]
    assert last_run(sql, SITEMAP_FLOW) is not None


@pytest.mark.parametrize("address, kept", [
    ("https://example.co.il/about/", "https://example.co.il/about/"),
    ("https://www.example.co.il/about/", "https://example.co.il/about/"),         # with www: the same site
    ("http://EXAMPLE.co.il/about", "https://example.co.il/about"),                # on the site's own scheme
    ("https://example.co.il", "https://example.co.il/"),
    ("https://example.co.il/%D7%9E%D7%95%D7%A6%D7%A8/", "https://example.co.il/%D7%9E%D7%95%D7%A6%D7%A8/"),
    ("https://example.co.il/product/sofa-2.5m/", "https://example.co.il/product/sofa-2.5m/"),
    ("https://example.co.il/blog/my-cart/", "https://example.co.il/blog/my-cart/"),       # only the first segment counts
    ("https://shop.example.co.il/about/", None), ("https://example.co.il.evil.example/", None),
    ("https://example.co.il/about/?utm=1", None), ("https://example.co.il/about/#top", None),
    ("https://example.co.il/Cart/", None), ("https://example.co.il/checkout/order-received/", None),
    ("https://example.co.il/checkouts/c1/", None), ("https://example.co.il/account/login", None),     # Shopify's names
    ("https://example.co.il/my-account/orders/", None), ("https://example.co.il/search/", None),
    ("https://example.co.il/feed/", None), ("https://example.co.il/tag/sale/", None),
    ("https://example.co.il/author/dana/", None), ("https://example.co.il/page/2/", None),
    ("https://example.co.il/category/sofas/page/12", None),
    ("https://example.co.il/%D7%A2%D7%92%D7%9C%D7%94/", None),                    # "עגלה": a translated cart
    ("https://example.co.il/files/price-list.PDF", None), ("https://example.co.il/image.jpg", None),
    ("ftp://example.co.il/about/", None), ("javascript:alert(1)", None), ("/about/", None),
])
def test_which_addresses_of_a_sitemap_are_pages_to_measure(address, kept):
    home = urllib.parse.urlsplit("https://example.co.il")
    assert collectors._page_url(home, address, collectors.PRIVATE_PATHS | {"עגלה"}) == kept


# ================================================================ 5. broken products (§7.7)

def issues(rows):
    return sorted((row["product_id"], row["issue"]) for row in rows)


def test_the_woocommerce_catalogue_is_read_whole_and_every_fault_gets_its_label(site):
    rows = collectors.catalogue_woocommerce(site.url)
    assert issues(rows) == [
        ("102", "בלי מחיר"),                          # the price is "0" and it cannot be bought
        ("104", "בלי תמונה"),
        ("105", "לא במלאי"),
        ("106", "אי אפשר להוסיף לסל"),                # in stock, priced, and still not purchasable
        ("109", "בלי תמונה"),
        ("110", "בלי תמונה"), ("110", "לא במלאי"),    # one product, two labels
        ("111", "לא במלאי"),                          # not purchasable, but being out of stock explains it
        ("112", "בלי מחיר")]                          # an empty price
    # No label for: 103 (free, and purchasable), 107 (external) and 108 (grouped): never purchasable, by design.
    by_id = {row["product_id"]: row for row in rows}
    assert by_id["109"] == {"product_id": "109", "issue": "בלי תמונה", "name": "שולחן – 160×90 & כיסאות",
                            "url": site.url + "/product/p-109/"}         # the name without its HTML entities
    assert [path for _, path, _ in site.hits] == [
        "/wp-json/wc/store/v1/products?per_page=100&page=%d&orderby=id&order=asc" % n for n in (1, 2)]
    assert all(headers["User-Agent"].startswith("SiteHealthProbe/1.0") for _, _, headers in site.hits)


@pytest.mark.parametrize("mode, message", [
    ("count_mismatch", "the shop declared 108 products and 107 were read"),
    ("no_total", "declares no total"),
    ("duplicate", "a product was read twice"),
    ("html", "did not answer with JSON"),
])
def test_a_catalogue_that_cannot_be_proven_complete_is_not_stored(sql, site, mode, message):
    config = collectors.read_config()
    yesterday = T0 - timedelta(days=1)
    collectors.catalogue_job(config, yesterday)                           # a good snapshot, the day before
    sql.sql("update sh_flows set last_at = null")
    site.catalogue = mode
    with pytest.raises(collectors.CollectorError, match=message):
        collectors.catalogue_job(config, T0)
    assert sql.sql("select distinct snap_date from sh_product_issues") == [(yesterday.date(),)]
    assert {row["snap_date"] for row in sql.rpc("sh_product_issues")} == {yesterday.date().isoformat()}
    assert last_run(sql, CATALOGUE_FLOW) is None


@pytest.mark.parametrize("break_it, message", [
    (lambda site: site.broken.update({"/wp-json/wc/store/v1/products": {"status": 403}}), "HTTP 403 from the catalogue"),
    (lambda site: setattr(site, "products", []), "the catalogue lists no products"),
    (lambda site: setattr(site, "products", [{"name": "בלי מזהה"}]), "the catalogue lists no products"),
])
def test_a_blocked_or_empty_catalogue_is_a_failed_read(site, break_it, message):
    break_it(site)
    with pytest.raises(collectors.CollectorError, match=message):
        collectors.catalogue_woocommerce(site.url)


def test_hostile_product_fields_do_not_break_the_read(site):
    site.products = [
        {"id": 1, "name": None, "permalink": "javascript:alert(1)", "prices": "x", "images": None, "is_in_stock": False},
        {"id": "2", "name": "א" * 500, "permalink": site.url + "/product/p-2/?add-to-cart=2#top", "prices": {"price": None},
         "images": [], "is_purchasable": False, "type": "simple"}]
    rows = collectors.catalogue_woocommerce(site.url)
    assert rows == [
        {"product_id": "1", "issue": "לא במלאי", "name": "", "url": None},
        {"product_id": "2", "issue": "בלי מחיר", "name": "א" * 300, "url": site.url + "/product/p-2/"},
        {"product_id": "2", "issue": "בלי תמונה", "name": "א" * 300, "url": site.url + "/product/p-2/"}]


def test_the_screen_reads_only_the_latest_snapshot(sql, site):
    config = collectors.read_config()
    first = collectors.catalogue_job(config, T0 - timedelta(days=1))
    assert first == {"n": 9, "snap_date": "2026-11-12"}
    assert len(sql.rpc("sh_product_issues")) == 9 and last_run(sql, CATALOGUE_FLOW) is not None

    site.products = [p for p in site.products if p["id"] in (101, 104, 105) or p["id"] > 1000]       # the shop was tidied
    second = collectors.catalogue_job(config, T0)
    assert second == {"n": 2, "snap_date": "2026-11-13"}
    assert [(row["issue"], row["name"], row["url"], row["snap_date"]) for row in sql.rpc("sh_product_issues")] == [
        ("בלי תמונה", "כורסה בלי תמונה", site.url + "/product/p-104/", "2026-11-13"),
        ("לא במלאי", "שידה שאזלה", site.url + "/product/p-105/", "2026-11-13")]
    assert sql.sql("select snap_date, count(*) from sh_product_issues group by 1 order by 1") == [
        (date(2026, 11, 12), 9), (date(2026, 11, 13), 2)]

    site.products = [p for p in site.products if p["id"] > 1000]         # and then nothing is broken
    assert collectors.catalogue_job(config, T0 + timedelta(days=1)) == {"n": 0, "snap_date": "2026-11-14"}
    assert sql.rpc("sh_product_issues") == []


def test_the_snapshot_carries_the_local_date(sql, site):
    late = datetime(2026, 11, 13, 22, 30, tzinfo=UTC)                     # 00:30 on the 14th in Jerusalem
    assert collectors.catalogue_job(collectors.read_config(), late)["snap_date"] == "2026-11-14"


def test_the_shopify_catalogue_and_its_labels(site):
    site.use("shopify")
    rows = collectors.catalogue_shopify(site.url, 305)
    assert rows == [
        {"product_id": "2", "issue": "לא במלאי", "name": "Sold out chair", "url": site.url + "/products/p-2"},
        {"product_id": "3", "issue": "בלי תמונה", "name": "Table without a picture", "url": site.url + "/products/p-3"},
        {"product_id": "4", "issue": "בלי מחיר", "name": "Shelf without a price", "url": site.url + "/products/p-4"}]
    assert [path for _, path, _ in site.hits] == ["/products.json?limit=250&page=%d" % n for n in (1, 2, 3)]


def test_a_shopify_read_is_checked_against_the_sitemap(sql, site):
    site.use("shopify")
    assert len(collectors.catalogue_shopify(site.url, 300)) == 3          # within 2% of the sitemap's count
    with pytest.raises(collectors.CollectorError, match="305 products were read and the sitemap lists 400"):
        collectors.catalogue_shopify(site.url, 400)
    # the tolerance: 2% of the sitemap's count, and never less than 3 products
    assert len(collectors.catalogue_shopify(site.url, 311)) == 3          # 311 // 50 = 6 may be missing
    with pytest.raises(collectors.CollectorError, match="the sitemap lists 312"):
        collectors.catalogue_shopify(site.url, 312)
    with pytest.raises(collectors.CollectorError, match="the sitemap lists 298"):
        collectors.catalogue_shopify(site.url, 298)                       # 298 // 50 = 5, and 7 are too many
    whole, site.shopify = site.shopify, site.shopify[:10]                # a small shop: 3 products of slack
    assert len(collectors.catalogue_shopify(site.url, 13)) == 3
    with pytest.raises(collectors.CollectorError, match="10 products were read and the sitemap lists 14"):
        collectors.catalogue_shopify(site.url, 14)
    site.shopify = whole
    site.shopify.append(dict(site.shopify[0]))
    with pytest.raises(collectors.CollectorError, match="a product was read twice"):
        collectors.catalogue_shopify(site.url, 306)
    site.catalogue = "html"                                               # a shop behind its password page
    with pytest.raises(collectors.CollectorError, match="did not answer with JSON"):
        collectors.catalogue_shopify(site.url, 305)


def test_the_shopify_job_counts_the_products_of_the_sitemap(sql, site):
    site.use("shopify")                                                   # the fake as a Shopify shop: its sitemap
    sql.rpc("sh_setup", p_config=site.config())                           # lists /products/ and /collections/
    config = collectors.read_config()
    assert config.platform == "shopify" and [p["url"].replace(site.url, "") for p in config.core] == list(SHOPIFY_PAGES)
    pages = collectors.sitemap_load(site.url, config.private, config.hosts)
    assert sum("/products/" in url for url in pages) == 305 and sum("/collections/" in url for url in pages) == 2
    assert [path for _, path, _ in site.hits] == [
        "/robots.txt", "/sitemap.xml", "/sitemap_products_1.xml?from=1&to=1300", "/sitemap_collections_1.xml",
        "/sitemap_pages_1.xml"]
    assert collectors.catalogue_job(collectors.read_config(), T0) == {"n": 3, "snap_date": "2026-11-13"}
    assert [row["issue"] for row in sql.rpc("sh_product_issues")] == ["בלי מחיר", "בלי תמונה", "לא במלאי"]

    site.shopify = site.shopify[:200]                                     # a read that lost a third of the shop
    with pytest.raises(collectors.CollectorError, match="200 products were read and the sitemap lists 305"):
        collectors.catalogue_job(collectors.read_config(), T0 + timedelta(days=1))
    assert len(sql.rpc("sh_product_issues")) == 3


# ================================================================ 6. the certificate (§7.7)

CERTIFICATE = {                                   # as ssl.getpeercert() returns it
    "subject": ((("commonName", "example.co.il"),),),
    "issuer": ((("countryName", "US"),), (("organizationName", "Let's Encrypt"),), (("commonName", "R11"),)),
    "version": 3, "serialNumber": "04A1B2C3",
    "notBefore": "Sep 14 08:00:00 2026 GMT", "notAfter": "Dec 13 08:00:00 2026 GMT",
    "subjectAltName": (("DNS", "example.co.il"), ("DNS", "www.example.co.il")),
}


def test_a_certificate_becomes_its_stored_row(sql, site):
    now = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    row = collectors.cert_row("example.co.il", CERTIFICATE, now)
    assert row == {"host": "example.co.il", "issuer": "Let's Encrypt R11", "not_before": "2026-09-14T08:00:00+00:00",
                   "not_after": "2026-12-13T08:00:00+00:00", "days_left": 29,     # 29 days and 23 hours
                   "ok": True, "err": None, "checked_at": "2026-11-13T09:00:00+00:00"}
    assert collectors.cert_row("x", CERTIFICATE, datetime(2026, 12, 13, 7, 59, tzinfo=UTC))["days_left"] == 0
    assert collectors.cert_row("x", dict(CERTIFICATE, issuer=()), now)["issuer"] == ""

    sql.sql("update sh_settings set value = '\"example.co.il\"' where key = 'host'")
    sql.rpc("sh_cert_set", p_row=row)
    stored = sql.rpc("sh_cert")
    assert (stored["host"], stored["issuer"], stored["days_left"], stored["ok"], stored["err"]) == (
        "example.co.il", "Let's Encrypt R11", 29, True, None)
    assert datetime.fromisoformat(stored["not_after"]) == datetime(2026, 12, 13, 8, 0, tzinfo=UTC)
    assert last_run(sql, CERT_FLOW) == now


def test_a_failed_check_is_stored_as_failed_and_is_no_proof_of_life(sql, site, monkeypatch):
    config, now = collectors.read_config(), datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
    good = collectors.cert_row(config.host, CERTIFICATE, now)
    sql.rpc("sh_cert_set", p_row=good)
    assert last_run(sql, CERT_FLOW) == now

    port = int(site.url.rsplit(":", 1)[1])                                # the fake site speaks no TLS
    failed = collectors.cert_check(config.host, now + timedelta(days=1), port=port)
    assert failed["ok"] is False and "SSL" in failed["err"] and failed["host"] == "127.0.0.1"
    assert sorted(failed) == ["checked_at", "err", "host", "ok"]
    refused = collectors.cert_check(config.host, now, port=closed_port())
    assert refused["ok"] is False and refused["err"].startswith("ConnectionRefusedError")

    real = collectors.cert_check
    monkeypatch.setattr(collectors, "cert_check", lambda host, when: real(host, when, port=port))
    with pytest.raises(collectors.CollectorError, match="the certificate of 127.0.0.1 could not be read"):
        collectors.cert_job(config, now + timedelta(days=1))              # stored, and reported as a failure
    stored = sql.rpc("sh_cert")
    assert stored["ok"] is False and "SSL" in stored["err"]
    assert (stored["days_left"], stored["issuer"]) == (29, "Let's Encrypt R11")   # what the last good check found
    assert last_run(sql, CERT_FLOW) == now                                # the heartbeat did not move


# ================================================================ 7. daily jobs

def local(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=ZONE).astimezone(UTC)


def utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def markers(sql):
    return sql.sql("select job, day from sh_jobs order by job, day")


def counting(calls, result=None):
    return lambda config, now: calls.append(now) or result or {"n": 1}


def test_a_daily_job_runs_once_per_local_day_from_its_hour(sql, site):
    calls, config = [], collectors.read_config()
    jobs = (("sitemap", counting(calls)),)                                # owed from 03:00
    daily = collectors.DailySchedule(jobs)
    assert daily.step(config, local(2026, 11, 13, 2, 59)) == []
    assert daily.step(config, local(2026, 11, 13, 3, 0)) == ["sitemap"]
    for later in (local(2026, 11, 13, 3, 1), local(2026, 11, 13, 12), local(2026, 11, 13, 23, 59)):
        assert daily.step(config, later) == []
    assert len(calls) == 1 and markers(sql) == [("sitemap", date(2026, 11, 13))]

    # A restart: a new schedule that remembers nothing. The marker is in the database.
    restarted = collectors.DailySchedule(jobs)
    assert restarted.step(config, local(2026, 11, 13, 9)) == [] and len(calls) == 1

    assert restarted.step(config, local(2026, 11, 14, 0, 30)) == []       # the next day, before its hour
    assert restarted.step(config, local(2026, 11, 14, 3, 5)) == ["sitemap"]
    assert daily.step(config, local(2026, 11, 14, 3, 6)) == []            # the worker that was replaced asks, too
    assert len(calls) == 2 and markers(sql) == [("sitemap", date(2026, 11, 13)), ("sitemap", date(2026, 11, 14))]


def test_a_job_that_started_late_still_runs_that_day(sql, site):
    calls = []
    daily = collectors.DailySchedule((("cleanup", counting(calls)),))
    assert daily.step(collectors.read_config(), local(2026, 11, 13, 17, 45)) == ["cleanup"] and len(calls) == 1


def test_a_failed_job_is_not_marked_and_is_tried_again_and_does_not_starve_the_others(sql, site, caplog):
    calls, state = [], {"fail": True}

    def flaky(config, now):
        calls.append(now)
        if state["fail"]:
            raise collectors.CollectorError("the site did not answer")
        return {"n": 1}

    others = []
    daily = collectors.DailySchedule((("sitemap", flaky), ("cleanup", counting(others))))
    config, start = collectors.read_config(), local(2026, 11, 13, 4)
    assert daily.step(config, start) == ["cleanup"]                       # the failure costs only its own job
    assert markers(sql) == [("cleanup", date(2026, 11, 13))]
    assert "daily job sitemap failed and will be tried again: CollectorError: the site did not answer" in caplog.text
    assert daily.step(config, start + minutes(1)) == [] and len(calls) == 1          # not every minute
    assert daily.step(config, start + minutes(10)) == [] and len(calls) == 2         # ten minutes later: again
    state["fail"] = False
    assert daily.step(config, start + minutes(20)) == ["sitemap"] and len(calls) == 3
    assert daily.step(config, start + minutes(30)) == [] and len(calls) == 3 and len(others) == 1
    assert markers(sql) == [("cleanup", date(2026, 11, 13)), ("sitemap", date(2026, 11, 13))]


def test_a_database_that_does_not_answer_is_a_failure_like_any_other(sql, site, monkeypatch):
    calls = []
    daily = collectors.DailySchedule((("sitemap", counting(calls)),))
    config = collectors.read_config()
    real = db.rpc
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: (_ for _ in ()).throw(db.DbError("database unreachable")))
    assert daily.step(config, local(2026, 11, 13, 3)) == [] and calls == []
    monkeypatch.setattr(db, "rpc", real)
    assert daily.step(config, local(2026, 11, 13, 3, 10)) == ["sitemap"]


def test_the_local_hour_is_kept_when_the_clocks_change(sql, site):
    """Jerusalem 2026: clocks go forward on 27 March (02:00 becomes 03:00) and back on 25 October
    (02:00 becomes 01:00). The sitemap job is owed from 03:00 local."""
    calls, config = [], collectors.read_config()
    daily = collectors.DailySchedule((("sitemap", counting(calls)),))
    # 24 October, summer time (UTC+3): 03:00 local is 00:00 UTC
    assert daily.step(config, utc("2026-10-23T23:59")) == []
    assert daily.step(config, utc("2026-10-24T00:00")) == ["sitemap"]
    # 25 October, winter time (UTC+2): 00:00 UTC is only 02:00 local; 03:00 local is 01:00 UTC
    assert daily.step(config, utc("2026-10-25T00:00")) == []
    assert daily.step(config, utc("2026-10-25T00:59")) == []
    assert daily.step(config, utc("2026-10-25T01:00")) == ["sitemap"]
    # 26 March, winter time: 01:00 UTC. 27 March, the day the clocks go forward: 00:00 UTC
    assert daily.step(config, utc("2026-03-26T00:59")) == []
    assert daily.step(config, utc("2026-03-26T01:00")) == ["sitemap"]
    assert daily.step(config, utc("2026-03-26T23:59")) == []              # 01:59 local on the 27th
    assert daily.step(config, utc("2026-03-27T00:00")) == ["sitemap"]     # 03:00 local, one minute later
    assert [day for _, day in markers(sql)] == [date(2026, 3, 26), date(2026, 3, 27), date(2026, 10, 24), date(2026, 10, 25)]


def test_the_hour_that_happens_twice_and_the_hour_that_never_happens(sql, site):
    calls = []
    daily = collectors.DailySchedule((("morning", counting(calls)),))
    twice = collectors.read_config()._replace(morning=(1, 30))           # 01:30 comes twice on 25 October
    assert daily.step(twice, utc("2026-10-24T22:29")) == []
    assert daily.step(twice, utc("2026-10-24T22:30")) == ["morning"]      # 01:30 summer time
    assert daily.step(twice, utc("2026-10-24T23:30")) == []               # 01:30 again, winter time
    never = twice._replace(morning=(2, 30))                               # 02:30 does not exist on 27 March
    assert daily.step(never, utc("2026-03-26T23:59")) == []               # 01:59
    assert daily.step(never, utc("2026-03-27T00:00")) == ["morning"]      # 03:00: the first minute after it
    assert len(calls) == 2


def test_which_jobs_a_site_has_use_for(sql, site):
    jobs = [job for job, _ in collectors.DAILY_JOBS]
    assert jobs == ["sitemap", "cleanup", "catalogue", "cert", "morning"]
    config = collectors.read_config()
    assert config.morning == (7, 30) and config.zone == ZONE and config.site == site.url
    assert config.off == {"cert"}                                         # the fake site is http: sh_config says so
    assert [collectors.daily_time(job, config) for job in jobs] == [(3, 0), (3, 30), (4, 0), None, (7, 30)]

    # "off" in the configuration, and what the platform implies: all of it arrives through sh_config()
    sql.rpc("sh_setup", p_config=site.config(platform="other", off=["sitemap"], morning="06:15"))
    plain = collectors.read_config()
    assert plain.off == {"sitemap", "catalogue", "cert"}
    assert [collectors.daily_time(job, plain) for job in jobs] == [None, (3, 30), None, None, (6, 15)]
    assert [collectors.job_off(job, plain) for job in ("sitemap", "speed-rotation", "catalogue", "cert")] == [
        'the configuration switches it off ("off": ["sitemap"])', 'the configuration switches it off ("off": ["sitemap"])',
        'the platform is "other": there is no catalogue to check', "the site is not https: there is no certificate to check"]
    assert [collectors.job_off(job, plain) for job in ("probe", "alerts", "speed-core", "morning", "cleanup")] == [None] * 5

    # an https shop with nothing switched off has use for all five
    shop = plain._replace(site="https://example.co.il", platform="woocommerce", off=frozenset())
    assert [collectors.daily_time(job, shop) for job in jobs] == [(3, 0), (3, 30), (4, 0), (4, 0), (6, 15)]
    # each entry of "off" alone
    for part, gone in (("sitemap", "sitemap"), ("catalogue", "catalogue"), ("cert", "cert"), ("real_users", None)):
        times = {job: collectors.daily_time(job, shop._replace(off=frozenset({part}))) for job in jobs}
        assert [job for job in jobs if times[job] is None] == ([gone] if gone else [])
    # and a configuration that was stored before "off" existed still gets the two implied rules
    assert collectors.daily_time("cert", shop._replace(site="http://example.co.il")) is None
    assert collectors.daily_time("catalogue", shop._replace(platform="other")) is None


def test_the_real_daily_jobs_run_once_and_leave_their_proof_of_life(sql, site, phone):
    config, pusher = collectors.read_config(), collectors.Pusher()
    collectors.probe_round(config.probe, "full", this_minute() - timedelta(hours=7))     # not a new installation
    collectors.probe_round(config.probe, "full", this_minute())
    daily = collectors.DailySchedule()
    now = datetime.now(UTC)
    evening = datetime.combine(now.astimezone(ZONE).date(), datetime.min.time(), ZONE).replace(hour=23, minute=50)
    assert daily.step(config, evening.astimezone(UTC)) == ["sitemap", "cleanup", "catalogue", "morning"]
    assert collectors.DailySchedule().step(config, evening.astimezone(UTC) + minutes(5)) == []     # also after a restart
    today = evening.date()
    assert markers(sql) == [("catalogue", today), ("cleanup", today), ("issues_snapshot", today), ("morning", today),
                            ("sitemap", today)]
    assert last_run(sql, SITEMAP_FLOW) is not None and last_run(sql, CATALOGUE_FLOW) is not None
    assert sql.sql("select count(*) from sh_site_pages where active") == [(8,)]
    assert len(sql.rpc("sh_product_issues")) == 9

    # the morning message was queued; the next alert tick pushes it, silently
    assert [(d["title"], d["status"]) for d in collectors.alert_tick(pusher)] == [("בוקר טוב: האתר תקין", 200)]
    sent = site.pushes[0]["json"]
    assert (sent["title"], sent["priority"], sent["tags"]) == ("בוקר טוב: האתר תקין", 2, ["sunrise"])
    assert sent["message"].startswith("זמינות 100.0% ב-24 שעות")
    assert sql.sql("select event, kind, status from sh_messages") == [("morning", "בוקר", 200)]


def test_a_new_installation_gets_no_morning_message_and_the_day_still_counts_as_done(sql, site, phone, caplog):
    caplog.set_level(logging.INFO)
    config, pusher = collectors.read_config()._replace(morning=(0, 0)), collectors.Pusher()
    collectors.probe_round(config.probe, "full", this_minute())           # the first round ever, a moment ago
    jobs = (("morning", collectors.morning_job),)
    daily, now = collectors.DailySchedule(jobs), datetime.now(UTC)
    assert daily.step(config, now) == ["morning"]                         # it ran, and decided to say nothing
    assert ('daily job morning: skipped today ({"n": 0, "skipped": "the oldest probe round is less than 6 hours old"})'
            in caplog.text)
    assert sql.sql("select count(*) from sh_messages") == [(0,)]
    assert collectors.alert_tick(pusher) == [] and site.pushes == []      # the owner's phone stays quiet
    assert markers(sql) == [("morning", now.astimezone(ZONE).date())]     # done for today, in the database
    assert daily.step(config, now) == [] and collectors.DailySchedule(jobs).step(config, now) == []      # also after a restart

    sql.sql("update sh_probe set round_at = round_at - interval '7 hours'")           # the next morning
    assert daily.step(config, now + timedelta(days=1)) == ["morning"]
    assert [d["title"] for d in collectors.alert_tick(pusher)] == ["בוקר טוב: האתר תקין"]
    assert 'daily job morning: done ({"n": 1})' in caplog.text


def test_a_job_that_keeps_failing_is_tried_four_times_and_then_waits_for_the_next_day(sql, site, caplog):
    calls, state = [], {"fail": True}

    def lasting(config, now):
        calls.append(now)
        if state["fail"]:
            raise collectors.CollectorError("no sitemap")
        return {"n": 1}

    daily = collectors.DailySchedule((("sitemap", lasting),))
    config, start = collectors.read_config(), local(2026, 11, 13, 3)
    for minute in range(21 * 60):                                         # every minute until midnight, as the loop asks
        assert daily.step(config, start + minutes(minute)) == []
    assert calls == [start + minutes(wait) for wait in (0, 10, 20, 30)]   # the first try and three more, 10 minutes apart
    assert markers(sql) == []
    assert caplog.text.count("daily job sitemap failed and will be tried again: CollectorError: no sitemap") == 3
    assert caplog.text.count("daily job sitemap failed 4 times today and waits for tomorrow: CollectorError: no sitemap") == 1

    assert daily.step(config, local(2026, 11, 14, 2, 59)) == [] and len(calls) == 4   # the next day, before its hour
    assert daily.step(config, local(2026, 11, 14, 3)) == [] and len(calls) == 5       # owed again, with a new count
    assert daily.step(config, local(2026, 11, 14, 3, 10)) == [] and len(calls) == 6
    state["fail"] = False
    assert daily.step(config, local(2026, 11, 14, 3, 20)) == ["sitemap"] and len(calls) == 7
    assert markers(sql) == [("sitemap", date(2026, 11, 14))]


def test_a_database_that_cannot_be_asked_does_not_use_up_the_tries_of_the_day(sql, site, monkeypatch, caplog):
    calls = []
    daily = collectors.DailySchedule((("sitemap", counting(calls)),))
    config, start = collectors.read_config(), local(2026, 11, 13, 3)
    real = db.rpc
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: (_ for _ in ()).throw(db.DbError("database unreachable")))
    for wait in range(0, 90, 10):                                         # an hour and a half without a database
        assert daily.step(config, start + minutes(wait)) == []
    assert calls == [] and caplog.text.count("the database could not be asked, trying again later") == 9
    monkeypatch.setattr(db, "rpc", real)
    assert daily.step(config, start + minutes(90)) == ["sitemap"] and len(calls) == 1


def test_a_part_that_is_switched_off_is_never_run(sql, site):
    sql.rpc("sh_setup", p_config=site.config(off=["sitemap", "catalogue"]))
    config = collectors.read_config()
    assert config.off == {"sitemap", "catalogue", "cert"}                 # the certificate: the fake site is http
    now = datetime.now(UTC)
    evening = datetime.combine(now.astimezone(ZONE).date(), datetime.min.time(), ZONE).replace(hour=23, minute=50)
    assert collectors.DailySchedule().step(config, evening.astimezone(UTC)) == ["cleanup", "morning"]
    assert site.hits == []                                                # the site was not asked for anything
    assert [job for job, _ in markers(sql)] == ["cleanup", "morning"]
    assert sql.sql("select count(*) from sh_site_pages") == [(0,)] and sql.sql("select count(*) from sh_cert") == [(0,)]
    assert sql.sql("select flow_name from sh_flows where not enabled order by sort") == [
        (ROTATION_FLOW,), (SITEMAP_FLOW,), (CERT_FLOW,), (CATALOGUE_FLOW,)]


def test_no_rotation_where_the_sitemap_is_switched_off(sql, site):
    sql.rpc("sh_sitemap_set", p_urls=["%s/product/item-%d/" % (site.url, i) for i in range(1, 4)])    # known from before
    sql.rpc("sh_setup", p_config=site.config(off=["sitemap"]))
    speed = collectors.SpeedSchedule(KEY, Clock(T0))
    assert speed.step(collectors.read_config()) == ["core pages, phone", "core pages, desktop"]
    assert sql.sql("select distinct source from sh_speed") == [("core",)] and len(site.psi_calls) == 10


# ================================================================ 8. the scheduler

def test_start_returns_at_once_and_its_threads_are_daemons(site, scheduler, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: gate.wait(20) and None)    # a database that does not answer
    monkeypatch.setenv("PAGESPEED_KEY", KEY)
    started = time.monotonic()
    threads = collectors.start()
    assert time.monotonic() - started < 0.5
    assert sorted(thread.name for thread in threads) == ["sh-alerts", "sh-daily-jobs", "sh-probe", "sh-speed"]
    assert all(thread.daemon and thread.is_alive() for thread in threads)
    assert collectors.start() is threads and len(threads) == 4            # a second call starts nothing
    scheduler.set()
    gate.set()
    for thread in threads:
        thread.join(5)
    assert not any(thread.is_alive() for thread in threads)


def test_a_missing_key_switches_off_only_its_collector_with_one_line(site, scheduler, monkeypatch, caplog):
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: None)
    caplog.set_level(logging.INFO)
    threads = collectors.start()
    assert sorted(thread.name for thread in threads) == ["sh-alerts", "sh-daily-jobs", "sh-probe"]
    assert [record.message for record in caplog.records if "is not set" in record.message] == [
        "collectors: PAGESPEED_KEY is not set, the speed collectors do not run",
        "collectors: NTFY_TOPIC is not set, alerts are logged and nothing is pushed"]
    assert "collectors: probe, alerts, daily jobs are running (heartbeat ping: off)" in caplog.text


def test_a_step_that_raises_costs_one_log_line_and_not_the_loop(scheduler, monkeypatch, caplog):
    monkeypatch.setattr(collectors, "FAILURE_PAUSE", 0.01)
    calls, enough = [], threading.Event()

    def step():
        calls.append(1)
        if len(calls) >= 6:
            enough.set()
        if len(calls) % 2:
            raise RuntimeError("the site exploded (%d)" % len(calls))

    thread = threading.Thread(target=collectors._loop, args=("probe", step, 0), daemon=True)
    thread.start()
    assert enough.wait(5)                                                 # it went on after three failures
    scheduler.set()
    thread.join(5)
    assert not thread.is_alive()
    lines = [record.message for record in caplog.records if record.name == "site_health.collectors"]
    assert lines[:3] == ["probe failed: RuntimeError: the site exploded (%d)" % n for n in (1, 3, 5)]


def test_the_next_round_full_at_second_0_and_light_at_second_30():
    minute = 1794600000                                                   # a whole minute
    assert minute % 60 == 0
    assert collectors.next_round(minute + 12.5) == (minute + 30, "light")
    assert collectors.next_round(minute + 29.999) == (minute + 30, "light")
    assert collectors.next_round(minute + 30) == (minute + 60, "full")    # strictly after now
    assert collectors.next_round(minute + 59.2) == (minute + 60, "full")
    assert collectors.next_round(minute) == (minute + 30, "light")


def test_a_full_round_is_followed_by_the_alert_tick_and_the_heartbeat(sql, site, phone, scheduler, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_URL", site.url + "/hb")
    site.broken["/cart/"] = {"status": 502}
    ticks, pusher, at = queue.Queue(), collectors.Pusher(), float(int(time.time()))

    monkeypatch.setattr(collectors, "next_round", lambda now: (at - 30, "light"))
    collectors._probe_step(ticks)
    assert ticks.empty()                                                  # a light round: no tick
    assert sql.sql("select distinct kind, round_at from sh_probe") == [("light", datetime.fromtimestamp(at - 30, UTC))]

    monkeypatch.setattr(collectors, "next_round", lambda now: (at, "full"))
    collectors._probe_step(ticks)
    assert ticks.qsize() == 1
    assert sql.sql("select distinct round_at from sh_probe where kind = 'full'") == [(datetime.fromtimestamp(at, UTC),)]
    assert site.pushes == [] and not any(path == "/hb" for _, path, _ in site.hits)

    collectors._alert_step(ticks, pusher)
    assert [push["json"]["title"] for push in site.pushes] == ["האתר לא עונה: סל"]
    assert [path for _, path, _ in site.hits].count("/hb") == 1

    owe(sql, 1)
    ticks.put(time.time() - 60)                                           # a tick that waited a minute is dropped:
    collectors._alert_step(ticks, pusher)                                 # the next round has its own
    assert len(site.pushes) == 1 and [path for _, path, _ in site.hits].count("/hb") == 2
    collectors._alert_step(ticks, pusher)                                 # nothing waits: nothing happens
    assert [path for _, path, _ in site.hits].count("/hb") == 2


def test_a_failed_alert_tick_still_pings_the_heartbeat(site, scheduler, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_URL", site.url + "/hb")
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: (_ for _ in ()).throw(db.DbError("database unreachable")))
    ticks = queue.Queue()
    ticks.put(time.time())
    with pytest.raises(db.DbError):
        collectors._alert_step(ticks, collectors.Pusher())
    assert [path for _, path, _ in site.hits] == ["/hb"]


def test_the_configuration_is_read_again_and_survives_a_database_that_does_not_answer(sql, site, scheduler, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    assert [p["name"] for p in collectors._config().probe] == ["בית", "קטגוריה", "מוצר", "סל"]
    changed = site.config()
    changed["pages"] = changed["pages"][:2]
    sql.rpc("sh_setup", p_config=changed)
    assert len(collectors._config().probe) == 4                           # not before its time
    monkeypatch.setattr(collectors, "CONFIG_TTL", 0)
    assert [p["name"] for p in collectors._config().probe] == ["בית", "קטגוריה"]          # no restart was needed

    real = db.rpc
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: (_ for _ in ()).throw(db.DbError("database unreachable")))
    for _ in range(3):
        assert [p["name"] for p in collectors._config().probe] == ["בית", "קטגוריה"]      # the last good one
    assert caplog.text.count("the configuration could not be read") == 1  # said once
    monkeypatch.setattr(db, "rpc", real)
    assert len(collectors._config().probe) == 2
    assert caplog.text.count("collectors: the configuration is loaded") == 1          # said when it came back


def test_before_the_site_is_set_up_the_collectors_idle(sql, site, scheduler, caplog):
    sql.sql("delete from sh_settings")
    sql.sql("delete from sh_pages")
    assert collectors.read_config() is None and collectors._config() is None
    ticks = queue.Queue()
    monkeypatch_next = collectors.next_round
    try:
        collectors.next_round = lambda now: (time.time(), "full")
        collectors._probe_step(ticks)
    finally:
        collectors.next_round = monkeypatch_next
    assert ticks.empty() and sql.sql("select count(*) from sh_probe") == [(0,)]
    assert caplog.text.count("the site is not configured: load its configuration with manage.py setup") == 1


# ================================================================ manage.py

def run_manage(*argv):
    """manage.py with these arguments: its exit code or message (None when it simply returned)."""
    try:
        manage.main(list(argv))
    except SystemExit as stop:
        return stop.code


def test_new_secret_writes_two_fresh_secrets_to_a_file_and_prints_neither(tmp_path, capsys):
    message = run_manage("new-secret")                                    # without a file: nothing is made up
    assert "--out <file>" in message and "never prints them" in message
    assert capsys.readouterr().out == ""

    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    assert run_manage("new-secret", "--out", str(first)) is None
    lines = first.read_text(encoding="utf-8").splitlines()
    assert re.fullmatch(r"NTFY_TOPIC=sh-[A-Za-z0-9]{24}", lines[0])
    assert re.fullmatch(r"SH_SHARE_TOKEN=[A-Za-z0-9_-]{32}", lines[1]) and len(lines) == 2
    assert first.stat().st_mode & 0o777 == 0o600                         # for its owner's eyes only
    printed = capsys.readouterr()
    values = [line.split("=", 1)[1] for line in lines]
    assert not any(value in printed.out + printed.err for value in values)             # a terminal is a transcript
    assert "NTFY_TOPIC and SH_SHARE_TOKEN" in printed.out and str(first) in printed.out
    assert "inside a git repository" not in printed.out

    assert run_manage("new-secret", "--out", str(second)) is None
    assert second.read_text(encoding="utf-8").splitlines() != lines       # fresh each time
    assert "is not overwritten" in run_manage("new-secret", "--out", str(first))
    assert first.read_text(encoding="utf-8").splitlines() == lines

    (tmp_path / ".git").mkdir()                                           # a file that could be committed by mistake
    capsys.readouterr()
    assert run_manage("new-secret", "--out", str(tmp_path / "third.txt")) is None
    assert "WARNING: that file is inside a git repository" in capsys.readouterr().out


def test_setup_loads_a_configuration_file_and_check_reports_names_not_values(sql, site, tmp_path, monkeypatch, capsys):
    sql.sql("delete from sh_settings")
    path = tmp_path / "site_health.config.json"
    path.write_text(json.dumps(site.config(), ensure_ascii=False), encoding="utf-8")
    assert run_manage("setup", str(path)) is None
    assert capsys.readouterr().out == ("%s is set up: time zone Asia/Jerusalem, platform woocommerce, 4 probe pages, "
                                       "5 core pages, switched off: cert\n" % site.url)       # an http site

    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("PAGESPEED_KEY", KEY)
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", "dana-password")
    collectors.probe_round(collectors.read_config().probe, "full", this_minute())
    assert run_manage("check") is None
    out = capsys.readouterr().out
    assert "NTFY_TOPIC is set" in out and "PAGESPEED_KEY is set" in out and "SH_PASS_VENDOR_DANA is set" in out
    assert "HEARTBEAT_URL is NOT set" in out and "DATABASE_URL is set" in out and "SUPABASE_URL is NOT set" in out
    assert TOPIC not in out and KEY not in out and "dana-password" not in out and "postgresql://" not in out
    assert "database: reachable" in out and "time zone Asia/Jerusalem, platform woocommerce, morning message at 07:30" in out
    assert "probe pages (every minute): בית, קטגוריה, מוצר, סל" in out
    assert "core pages (speed): בית, קטגוריה, מוצר, סל, אודות" in out and "switched off: cert" in out
    assert "SH_ALLOW_PRIVATE is set" in out and "PAGESPEED_URL is set" in out and "SH_RUM_PER_DAY is NOT set" in out
    assert re.search(r"תקין\s+בודק זמינות האתר \(last run: 20", out)
    assert re.search(r"אין נתון\s+טעינת מפת האתר \(last run: never\)", out)


def test_check_says_when_the_database_or_the_configuration_is_missing(sql, site, monkeypatch, capsys):
    sql.sql("delete from sh_settings")
    assert run_manage("check") == "configuration: none yet. Load one: python3 manage.py setup site_health.config.json"
    monkeypatch.delenv("DATABASE_URL")
    assert run_manage("check") == ("database: NOT reachable (no database configured: set SUPABASE_URL and "
                                   "SUPABASE_SECRET_KEY, or DATABASE_URL)")
    assert run_manage("run-once", "probe").startswith("database: no database configured")


def test_run_once_runs_one_collector_and_prints_what_it_stored(sql, site, phone, capsys):
    site.broken["/cart/"] = {"status": 502}
    assert run_manage("run-once", "probe") is None
    printed = json.loads(capsys.readouterr().out)
    assert printed["stored"] == 4 and [(row["page"], row["ok"]) for row in printed["rows"]] == [
        ("בית", True), ("קטגוריה", True), ("מוצר", True), ("סל", False)]
    assert sql.sql("select kind, count(*) from sh_probe group by kind") == [("full", 4)]

    assert run_manage("run-once", "alerts") is None
    assert [(d["title"], d["status"]) for d in json.loads(capsys.readouterr().out)] == [("האתר לא עונה: סל", 200)]
    assert len(site.pushes) == 1

    assert run_manage("run-once", "sitemap") is None
    assert json.loads(capsys.readouterr().out) == {"n": 8, "pages": 8}
    assert run_manage("run-once", "catalogue") is None
    assert json.loads(capsys.readouterr().out)["n"] == 9
    assert run_manage("run-once", "cleanup") is None
    assert json.loads(capsys.readouterr().out)["probe"] == 0
    # a new installation: the oldest round is a minute old, and "nothing was measured" is no morning message
    assert run_manage("run-once", "morning") is None
    assert json.loads(capsys.readouterr().out) == {"n": 0, "skipped": "the oldest probe round is less than 6 hours old"}
    assert sql.sql("select count(*) from sh_messages where event = 'morning'") == [(0,)]
    assert markers(sql) == [("issues_snapshot", datetime.now(ZONE).date()), ("morning", datetime.now(ZONE).date())]
    # the day after, with rounds that are old enough
    sql.sql("update sh_probe set round_at = round_at - interval '7 hours'")
    sql.sql("delete from sh_jobs where job = 'morning'")
    assert run_manage("run-once", "morning") is None
    assert json.loads(capsys.readouterr().out) == {"n": 1}
    assert sql.sql("select count(*) from sh_messages where event = 'morning'") == [(1,)]

    assert run_manage("run-once", "speed-core") == "PAGESPEED_KEY is not set: the speed collectors cannot run."
    site.catalogue = "html"
    assert run_manage("run-once", "catalogue").startswith("catalogue failed: the catalogue did not answer with JSON")


def test_run_once_speed_uses_the_key(sql, site, monkeypatch, capsys):
    monkeypatch.setenv("PAGESPEED_KEY", KEY)
    assert run_manage("run-once", "speed-desktop") is None
    printed = json.loads(capsys.readouterr().out)
    assert len(printed) == 5 and {row["strategy"] for row in printed} == {"desktop"} and KEY not in json.dumps(printed)
    assert sql.sql("select strategy, source, count(*) from sh_speed group by 1, 2") == [("desktop", "core", 5)]
    site.psi = "bad_key"
    assert run_manage("run-once", "speed-core") == "speed-core failed: API key not valid. Please pass a valid API key."


def test_the_test_push_says_in_hebrew_that_it_is_a_test_and_leaves_no_row(sql, site, phone, capsys):
    assert run_manage("test-push") == 0
    assert site.pushes[0]["json"] == {
        "topic": TOPIC, "title": "בדיקה: בריאות האתר",
        "message": "זו הודעת בדיקה של מערכת בריאות האתר. אין שום תקלה, ואין צורך לעשות דבר.",
        "priority": 3, "tags": ["bell"], "click": "https://dash.example/site"}
    assert "ntfy answered 200: accepted" in capsys.readouterr().out
    assert sql.sql("select count(*) from sh_messages") == [(0,)] and sql.sql("select count(*) from sh_alerts") == [(0,)]
    site.ntfy_status = 403
    assert run_manage("test-push") == 1 and "ntfy answered 403: NOT accepted." in capsys.readouterr().out


def test_the_test_push_needs_a_topic(site):
    assert run_manage("test-push") == "NTFY_TOPIC is not set: there is nowhere to push to."


def test_init_db_applies_both_files_or_explains_what_to_do(sql, site, monkeypatch, capsys):
    before = sql.sql("select count(*) from sh_pages")
    assert run_manage("init-db") is None                                  # on a database that has them: harmless
    assert capsys.readouterr().out.splitlines()[:2] == ["applied schema.sql", "applied functions.sql"]
    assert sql.sql("select count(*) from sh_pages") == before and sql.rpc("sh_ping") == "ok"

    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@127.0.0.1:%d/nothing" % closed_port())
    assert run_manage("init-db").startswith("init-db failed: ")           # one line, no traceback
    monkeypatch.delenv("DATABASE_URL")
    assert run_manage("init-db") == "DATABASE_URL is not set: nothing to apply the SQL files to."
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    message = run_manage("init-db")
    assert "SQL editor" in message and message.index("schema.sql") < message.index("functions.sql")


def test_run_once_of_a_part_that_is_off_says_skipped_and_stores_nothing(sql, site, capsys):
    assert run_manage("run-once", "cert") is None                         # the fake site is http
    assert capsys.readouterr().out == "skipped: the site is not https: there is no certificate to check\n"
    assert sql.sql("select count(*) from sh_cert") == [(0,)]              # no failed check for the card to show

    sql.rpc("sh_setup", p_config=site.config(off=["sitemap", "catalogue"]))
    for collector in ("sitemap", "speed-rotation", "catalogue"):          # speed-rotation: also without a key
        assert run_manage("run-once", collector) is None
        part = "catalogue" if collector == "catalogue" else "sitemap"
        assert capsys.readouterr().out == 'skipped: the configuration switches it off ("off": ["%s"])\n' % part
    sql.rpc("sh_setup", p_config=site.config(platform="other"))
    assert run_manage("run-once", "catalogue") is None
    assert capsys.readouterr().out == 'skipped: the platform is "other": there is no catalogue to check\n'
    assert site.hits == [] and sql.sql("select count(*) from sh_site_pages") == [(0,)]
    assert sql.sql("select count(*) from sh_product_issues") == [(0,)]


# ================================================================ 9. where a request to the site may go (§7.5, §7.7)

def test_a_redirect_to_another_host_is_not_followed(site, inner):
    site.broken["/cart/"] = {"to": elsewhere(inner)}
    row = collectors.probe_check(page(site, "/cart/"), 2)
    assert (row["ok"], row["fail"], row["status"], row["err"]) == (False, "http", 302, "redirected to another host")
    assert type(row["ms"]) is int and inner.hits == []                    # the other machine never heard of it
    assert "localhost" not in json.dumps(row)                             # and its address is not stored or shown


def test_a_host_of_extra_hosts_may_be_redirected_to(sql, site, inner):
    site.broken["/cart/"] = {"to": elsewhere(inner, "/cart/")}
    config = collectors.read_config()
    assert config.hosts == {"127.0.0.1"}
    rows = collectors.probe_round(config.probe, "full", this_minute(), hosts=config.hosts)["rows"]
    assert [(row["ok"], row["err"]) for row in rows][3] == (False, "redirected to another host") and inner.hits == []

    sql.rpc("sh_setup", p_config=site.config(extra_hosts=["localhost", "www.pay.example.co.il"]))
    config = collectors.read_config()
    assert config.hosts == {"127.0.0.1", "localhost", "pay.example.co.il"}
    rows = collectors.probe_round(config.probe, "light", this_minute(), hosts=config.hosts)["rows"]
    assert [row["ok"] for row in rows] == [True] * 4 and [path for _, path, _ in inner.hits] == ["/cart/"]


def test_the_scheduled_round_and_the_round_by_hand_use_the_configured_hosts(sql, site, inner, scheduler, monkeypatch, capsys):
    sql.rpc("sh_setup", p_config=site.config(extra_hosts=["localhost"]))
    site.broken["/cart/"] = {"to": elsewhere(inner, "/cart/")}
    at = float(int(time.time())) - 120
    monkeypatch.setattr(collectors, "next_round", lambda now: (at, "full"))
    collectors._probe_step(queue.Queue())
    assert sql.sql("select ok from sh_probe where page = 'סל'") == [(True,)]
    assert run_manage("run-once", "probe") is None
    assert [row["ok"] for row in json.loads(capsys.readouterr().out)["rows"]] == [True] * 4
    assert [path for _, path, _ in inner.hits] == ["/cart/", "/cart/"]


def everywhere(monkeypatch, site):
    """Every host name leads to the fake site: a resolver of the test's own."""
    port = int(site.url.rsplit(":", 1)[1])
    monkeypatch.setattr(collectors, "_open",
                        lambda host, wanted, timeout, public: socket.create_connection(("127.0.0.1", port), timeout))


@pytest.mark.parametrize("start, target, hosts, followed", [
    ("http://example.co.il/cart/", "/about/", (), True),
    ("http://example.co.il/cart/", "http://www.example.co.il/about/", (), True),             # with www: the same site
    ("http://www.example.co.il/cart/", "http://example.co.il/about/", (), True),
    ("http://EXAMPLE.co.il/cart/", "http://example.co.il./about/", (), True),
    ("http://example.co.il/cart/", "http://example.co.il:8080/about/", (), True),            # the host is what counts
    ("http://example.co.il/cart/", "http://someone@example.co.il/about/", (), True),
    ("http://example.co.il/cart/", "http://shop.example.co.il/about/", (), False),           # a host of its own
    ("http://example.co.il/cart/", "http://shop.example.co.il/about/", ("shop.example.co.il",), True),
    ("http://example.co.il/cart/", "http://shop.example.co.il/about/", ("WWW.shop.example.co.il",), True),
    ("http://example.co.il/cart/", "http://example.co.il.evil.example/about/", (), False),
    ("http://example.co.il/cart/", "http://example.co.il@evil.example/about/", (), False),
    ("http://example.co.il/cart/", "//evil.example/about/", (), False),
    ("http://example.co.il/cart/", "http://169.254.169.254/latest/meta-data/", (), False),
    ("http://example.co.il/cart/", "http://localhost/about/", ("shop.example.co.il",), False),
    ("http://example.co.il/cart/", "javascript:alert(1)", (), False),
])
def test_which_redirects_are_followed(site, monkeypatch, start, target, hosts, followed):
    everywhere(monkeypatch, site)
    site.broken["/cart/"] = {"to": target}
    answer = collectors.fetch(start, timeout=2, hosts=hosts, public=True)
    assert (answer.status, answer.elsewhere) == ((200, False) if followed else (302, True))
    assert [path for _, path, _ in site.hits] == (["/cart/", "/about/"] if followed else ["/cart/"])


def test_a_redirect_from_http_to_https_of_the_same_host_is_followed(site, monkeypatch):
    everywhere(monkeypatch, site)
    site.broken["/cart/"] = {"to": "https://www.example.co.il/cart/"}
    with pytest.raises(ssl.SSLError):                                     # it went there: the fake speaks no TLS
        collectors.fetch("http://example.co.il/cart/", timeout=2, public=True)


@pytest.mark.parametrize("address, public", [
    ("8.8.8.8", True), ("2606:4700:4700::1111", True), ("::ffff:8.8.8.8", True),
    ("127.0.0.1", False), ("127.8.9.10", False), ("10.1.2.3", False), ("172.16.0.9", False), ("192.168.1.1", False),
    ("169.254.169.254", False),                                           # where clouds keep their credentials
    ("100.64.0.1", False), ("0.0.0.0", False), ("224.0.0.1", False), ("::1", False), ("::", False),
    ("::ffff:127.0.0.1", False), ("::ffff:10.0.0.1", False), ("fe80::1%eth0", False), ("fd00::1", False),
    ("not an address", False), ("", False),
])
def test_which_addresses_are_public(address, public):
    assert collectors._is_public(address) is public


def test_without_the_switch_nothing_connects_to_a_private_address(site, monkeypatch):
    monkeypatch.delenv("SH_ALLOW_PRIVATE")
    refusal = "NotPublic: not a public address (a private or local network; SH_ALLOW_PRIVATE=1 allows it)"
    row = collectors.probe_check(page(site, "/"), 2)
    assert (row["ok"], row["fail"], row["status"], row["err"]) == (False, "connect", None, refusal)
    port = site.url.rsplit(":", 1)[1]
    for address in ("http://localhost:%s/" % port, "http://[::1]:%s/" % port, "http://0.0.0.0:%s/" % port,
                    "http://169.254.169.254/latest/meta-data/", "http://10.0.0.1/", "http://192.168.0.1/"):
        started = time.monotonic()
        row = collectors.probe_check({"name": "x", "url": address}, 2)
        assert (row["fail"], row["err"]) == ("connect", refusal), address
        assert time.monotonic() - started < 1                             # refused here, before a packet left
    collectors.probe_check({"name": "x", "url": "http://2130706433:%s/" % port}, 2)    # 127.0.0.1, written as one number
    assert site.hits == []
    for value in ("0", "true", "yes", "11"):                              # the switch is the word 1, and nothing else
        monkeypatch.setenv("SH_ALLOW_PRIVATE", value)
        assert collectors.probe_check(page(site, "/"), 2)["err"] == refusal
    monkeypatch.setenv("SH_ALLOW_PRIVATE", " 1 ")
    assert collectors.probe_check(page(site, "/"), 2)["ok"] is True


def test_the_connection_goes_to_the_address_that_was_checked(monkeypatch):
    monkeypatch.delenv("SH_ALLOW_PRIVATE", raising=False)
    answers = {"rebind.example": ["127.0.0.1"], "mixed.example": ["10.0.0.7", "93.184.216.34", "127.0.0.1"]}
    asked, tried = [], []

    def lookup(host, port, *args, **kwargs):
        asked.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in answers[host]]

    class Link:                                                           # a socket that goes nowhere, and says where
        def __init__(self, *args):
            pass

        def settimeout(self, seconds):
            pass

        def connect(self, address):
            tried.append(address)
            raise ConnectionRefusedError("refused")

        def close(self):
            pass

    with monkeypatch.context() as patch:
        patch.setattr(socket, "getaddrinfo", lookup)
        patch.setattr(socket, "socket", Link)
        hidden = collectors.probe_check({"name": "x", "url": "http://rebind.example:8080/"}, 2)
        mixed = collectors.probe_check({"name": "x", "url": "http://mixed.example/"}, 2)
    assert hidden["err"].startswith("NotPublic") and mixed["err"].startswith("ConnectionRefusedError")
    assert tried == [("93.184.216.34", 80)]                               # the public one, and no other
    assert asked == ["rebind.example", "mixed.example"]                   # one lookup each: no second answer to fall for


def test_a_sitemap_file_that_redirects_to_another_host_is_refused_and_never_fetched(sql, site, inner):
    inner.files["/internal/sitemap.xml"] = urlset(site.url, "/INTERNAL-ONLY-PATH/")
    site.files["/robots.txt"] = ("text/plain", ("Sitemap: %s/sitemap-b.xml\n" % site.url).encode())
    site.broken["/sitemap-b.xml"] = {"to": elsewhere(inner, "/internal/sitemap.xml")}
    known = [site.url + "/", site.url + "/old-page/"]
    sql.rpc("sh_sitemap_set", p_urls=known)
    with pytest.raises(collectors.CollectorError, match="redirected to another host: %s/sitemap-b.xml" % site.url):
        collectors.sitemap_job(collectors.read_config(), T0)
    assert inner.hits == []
    assert sql.sql("select url from sh_site_pages where active order by url") == [(url,) for url in sorted(known)]

    # robots.txt itself sent elsewhere: its lines are not read there, and the usual addresses are tried here
    inner.files["/robots.txt"] = ("text/plain", b"Sitemap: http://localhost/evil.xml\n")
    site.reset()
    site.broken["/robots.txt"] = {"to": elsewhere(inner, "/robots.txt")}
    assert len(collectors.sitemap_load(site.url)) == 8 and inner.hits == []
    assert [path for _, path, _ in site.hits][:2] == ["/robots.txt", "/sitemap_index.xml"]


def test_a_catalogue_that_redirects_to_another_host_is_a_failed_read(site, inner):
    site.broken["/wp-json/wc/store/v1/products"] = {"to": elsewhere(inner, "/wp-json/wc/store/v1/products")}
    with pytest.raises(collectors.CollectorError, match="the catalogue redirects to another host"):
        collectors.catalogue_woocommerce(site.url)
    site.use("shopify")
    site.broken["/products.json"] = {"to": elsewhere(inner, "/products.json")}
    with pytest.raises(collectors.CollectorError, match="the catalogue redirects to another host"):
        collectors.catalogue_shopify(site.url, 305)
    assert inner.hits == []


def test_the_daily_jobs_follow_a_redirect_to_a_host_of_extra_hosts(sql, site, inner):
    sql.rpc("sh_setup", p_config=site.config(extra_hosts=["localhost"]))
    config = collectors.read_config()
    inner.files["/product-sitemap.xml"] = urlset(site.url, "/product/from-the-other-host/")
    site.broken["/product-sitemap.xml"] = {"to": elsewhere(inner, "/product-sitemap.xml")}
    assert collectors.sitemap_job(config, T0) == {"n": 6, "pages": 6}
    assert sql.sql("select count(*) from sh_site_pages where url like '%%/product/from-the-other-host/'") == [(1,)]
    site.broken = {"/wp-json/wc/store/v1/products": {"to": elsewhere(inner, "/wp-json/wc/store/v1/products")}}
    site.hits.clear()
    assert collectors.catalogue_job(config, T0)["n"] == 9                 # the same catalogue, read from the other host
    assert len(site.hits) == 2 and len([hit for hit in inner.hits if "/wp-json/" in hit[1]]) == 2


def test_a_site_on_a_private_address_is_said_plainly(sql, site, monkeypatch, capsys):
    monkeypatch.delenv("SH_ALLOW_PRIVATE")
    refusal = "not a public address (a private or local network; SH_ALLOW_PRIVATE=1 allows it)"
    assert run_manage("run-once", "sitemap") == "sitemap failed: " + refusal          # not "no sitemap"
    assert run_manage("run-once", "catalogue") == "catalogue failed: " + refusal
    row = collectors.cert_check("127.0.0.1", T0, port=int(site.url.rsplit(":", 1)[1]))
    assert (row["ok"], row["err"]) == (False, "NotPublic: " + refusal)
    assert run_manage("run-once", "probe") is None
    assert {row["err"] for row in json.loads(capsys.readouterr().out)["rows"]} == {"NotPublic: " + refusal}
    with pytest.raises(collectors.NotPublic):                             # each request of the load on its own
        collectors._sitemap_read(site.url + "/sitemap.xml")
    monkeypatch.setattr(collectors, "_robots_sitemaps", lambda address, hosts=(): [])
    with pytest.raises(collectors.NotPublic):                             # the guessed addresses: refused, not "no sitemap"
        collectors.sitemap_load(site.url)
    assert site.hits == []


def test_the_services_named_in_the_environment_are_not_held_to_the_public_rule(site, phone, inner, monkeypatch):
    monkeypatch.delenv("SH_ALLOW_PRIVATE")
    monkeypatch.setenv("HEARTBEAT_URL", site.url + "/hb")
    assert collectors.speed_measure("https://example.co.il/", "mobile", KEY)["ok"] is True
    assert collectors.Pusher().publish("כותרת", "גוף") == 200
    collectors.heartbeat()
    assert len(site.pings) == 1
    site.broken["/hb"] = {"to": elsewhere(inner, "/hb")}                  # but none of them is followed to another host
    collectors.heartbeat()
    assert len(site.pings) == 1 and inner.hits == [] and inner.pings == []


def test_the_worker_says_at_its_start_that_private_addresses_are_allowed(site, scheduler, monkeypatch, caplog):
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: None)
    collectors.start()
    assert caplog.text.count("collectors: SH_ALLOW_PRIVATE=1, requests to the site may go to private and local") == 1


def test_the_worker_says_nothing_about_private_addresses_when_the_switch_is_off(site, scheduler, monkeypatch, caplog):
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: None)
    monkeypatch.delenv("SH_ALLOW_PRIVATE")
    collectors.start()
    assert "SH_ALLOW_PRIVATE" not in caplog.text


@pytest.fixture
def https_site(tmp_path):
    """One page over https on this machine, with a certificate that nobody vouches for."""
    if not shutil.which("openssl"):
        pytest.skip("the openssl command is needed to make a certificate")
    key, certificate = tmp_path / "key.pem", tmp_path / "cert.pem"
    made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out",
                           str(certificate), "-days", "2", "-subj", "/O=Site Health test/CN=localhost",
                           "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], capture_output=True)
    if made.returncode:
        pytest.skip("this openssl cannot make the certificate (it needs OpenSSL 1.1.1 or newer)")

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = "<html><body><button>הוספה לסל</button></body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    class Quiet(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):                  # a client that only read the certificate
            pass

    server = Quiet(("127.0.0.1", 0), Page)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], certificate
    server.shutdown()
    server.server_close()


def test_a_page_over_https_is_checked_against_its_certificate(site, https_site, monkeypatch):
    port, certificate = https_site
    home = {"name": "בית", "url": "https://127.0.0.1:%d/" % port, "expect": "הוספה לסל"}
    row = collectors.probe_check(home, 5)                                 # normal verification: nobody signed this one
    assert (row["ok"], row["fail"], row["status"]) == (False, "connect", None)
    assert "CERTIFICATE_VERIFY_FAILED" in row["err"]
    failed = collectors.cert_check("127.0.0.1", T0, port=port)
    assert failed["ok"] is False and "CERTIFICATE_VERIFY_FAILED" in failed["err"]

    monkeypatch.setattr(collectors, "_TLS", ssl.create_default_context(cafile=str(certificate)))      # now somebody does
    row = collectors.probe_check(home, 5)
    assert (row["ok"], row["status"], row["fail"]) == (True, 200, None)
    now = datetime.now(UTC)
    read = collectors.cert_check("127.0.0.1", now, port=port)
    assert (read["ok"], read["host"], read["issuer"], read["days_left"]) == (True, "127.0.0.1", "Site Health test localhost", 1)
    # the name is part of the check: the same server under a name its certificate does not carry
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, wanted, *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", wanted))])
    other = collectors.probe_check(dict(home, url="https://shop.example:%d/" % port), 5)
    assert other["fail"] == "connect" and "CERTIFICATE_VERIFY_FAILED" in other["err"]


def test_the_numbers_the_spec_names():
    megabyte = 1024 * 1024
    assert (collectors.FULL_TIMEOUT, collectors.LIGHT_TIMEOUT, collectors.REDIRECTS, collectors.EXPECT_BYTES) == (
        10, 5, 5, 200_000)                                                # §7.5
    assert (collectors.PSI_CONNECT, collectors.PSI_READ, collectors.PSI_WAITS, collectors.OPPS) == (10, 120, (5, 10), 6)
    assert collectors.ROTATION_PAGES == 2 and collectors.KEY_RETRY == timedelta(hours=1)          # §7.6
    assert (collectors.SITEMAP_FILES, collectors.SITEMAP_PAGES) == (500, 50_000)                  # §7.7
    assert (collectors.SITEMAP_BYTES, collectors.SITEMAP_BYTES_MAX) == (10 * megabyte, 50 * megabyte)
    assert (collectors.CATALOGUE_BYTES, collectors.CATALOGUE_JOB_BYTES) == (10 * megabyte, 300 * megabyte)
    assert [collectors._size(count) for count in (10 * megabyte, 300 * megabyte, 2000)] == ["10 MB", "300 MB", "2000 bytes"]
    assert (collectors.PUSHES_PER_HOUR, collectors.TITLE_MAX, collectors.MESSAGE_MAX) == (30, 199, 1499)      # §7.9
    assert collectors.DAILY_TIMES == {"sitemap": (3, 0), "cleanup": (3, 30), "catalogue": (4, 0), "cert": (4, 0)}
    assert (collectors.DAILY_RETRY, collectors.DAILY_RETRIES) == (timedelta(minutes=10), 3)


def test_the_morning_message_is_at_half_past_seven_unless_the_configuration_says_otherwise(monkeypatch):
    stored = {"site": "https://example.co.il", "host": "example.co.il", "time_zone": "Asia/Jerusalem", "pages": []}
    monkeypatch.setattr(db, "rpc", lambda fn, params=None: stored)
    config = collectors.read_config()
    assert (config.morning, config.platform, config.hosts, config.off) == ((7, 30), "other", {"example.co.il"}, frozenset())
    stored.update(morning="06:05", host="www.Example.co.il", extra_hosts=["pay.example.co.il"], off=["cert"])
    config = collectors.read_config()
    assert (config.morning, config.hosts, config.off) == ((6, 5), {"example.co.il", "pay.example.co.il"}, {"cert"})


# ================================================================ 10. what one read may take (§7.7)

def test_only_what_the_rules_read_is_kept_of_a_product():
    product = {"id": 7, "name": "ספה", "permalink": "https://example.co.il/product/sofa/", "type": "simple",
               "description": "x" * 100_000, "short_description": "y" * 10_000, "prices": {"price": "100"},
               "images": [{"src": "z" * 5000}], "is_in_stock": True, "is_purchasable": True, "attributes": [1] * 1000}
    slim = collectors._woo_slim(product)
    assert slim == {"id": "7", "name": "ספה", "url": "https://example.co.il/product/sofa/", "priced": True,
                    "pictured": True, "in_stock": True, "buyable": True, "by_design": False}
    assert len(json.dumps(slim)) < 250
    assert collectors._woo_slim({"name": "בלי מזהה"}) is None and collectors._woo_slim("text") is None
    assert len(collectors._woo_slim({"id": "9" * 500, "name": "א" * 5000})["name"]) == 2000

    shop = collectors._shopify_slim({"id": 7, "title": "Sofa", "handle": "sofa", "body_html": "x" * 100_000,
                                     "images": [{"src": "z"}], "variants": [{"price": "0.00", "available": False},
                                                                            {"price": "99.00", "available": True}]})
    assert shop == {"id": "7", "name": "Sofa", "handle": "sofa", "priced": True, "pictured": True, "in_stock": True}
    hostile = collectors._shopify_slim({"id": 8, "title": 5, "handle": None, "images": "x", "variants": 5})
    assert hostile == {"id": "8", "name": None, "handle": "", "priced": False, "pictured": True, "in_stock": False}


def test_a_catalogue_is_read_within_a_budget_per_page_and_per_read(site, monkeypatch):
    page_one = len(collectors.fetch(site.url + "/wp-json/wc/store/v1/products?per_page=100&page=1&orderby=id&order=asc",
                                    timeout=5, read=10_000_000).body)
    assert page_one > 50_000                                              # the fake's products carry a description
    site.hits.clear()
    monkeypatch.setattr(collectors, "CATALOGUE_JOB_BYTES", page_one + 10)             # room for one page, not for two
    with pytest.raises(collectors.CollectorError, match="the catalogue is larger than %d bytes" % (page_one + 10)):
        collectors.catalogue_woocommerce(site.url)
    assert len(site.hits) == 2                                            # stopped at the page that went over
    monkeypatch.setattr(collectors, "CATALOGUE_JOB_BYTES", 300 * 1024 * 1024)
    monkeypatch.setattr(collectors, "CATALOGUE_BYTES", page_one - 1)
    with pytest.raises(collectors.CollectorError, match="a catalogue page of more than %d bytes" % (page_one - 1)):
        collectors.catalogue_woocommerce(site.url)

    site.use("shopify")
    monkeypatch.setattr(collectors, "CATALOGUE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(collectors, "CATALOGUE_JOB_BYTES", 1000)
    with pytest.raises(collectors.CollectorError, match="the catalogue is larger than 1000 bytes: the read was stopped"):
        collectors.catalogue_shopify(site.url, 305)


def test_the_largest_sitemap_file_is_10_mb_unless_the_environment_says_otherwise(site, monkeypatch):
    megabyte = 1024 * 1024
    assert collectors.sitemap_bytes() == 10 * megabyte
    for text, limit in (("25", 25), ("1", 1), ("50", 50), ("80", 50), ("0", 10), ("-3", 10), ("many", 10), (" 20 ", 20)):
        monkeypatch.setenv("SH_SITEMAP_MB", text)
        assert collectors.sitemap_bytes() == limit * megabyte, text
    monkeypatch.delenv("SH_SITEMAP_MB")
    monkeypatch.setattr(collectors, "SITEMAP_BYTES", 2000)                # the limit, lowered for the test
    site.files["/product-sitemap.xml"] = urlset(site.url, *("/page-%d/" % i for i in range(200)))
    with pytest.raises(collectors.CollectorError, match="of more than 2000 bytes"):
        collectors.sitemap_load(site.url)
    monkeypatch.setenv("SH_SITEMAP_MB", "1")                              # raised by whoever runs the worker
    assert len(collectors.sitemap_load(site.url)) == 205


def test_more_files_or_more_pages_than_the_limit_abort_the_load(site, monkeypatch):
    monkeypatch.setattr(collectors, "SITEMAP_FILES", 4)                   # the index and its three children
    assert len(collectors.sitemap_load(site.url)) == 8
    monkeypatch.setattr(collectors, "SITEMAP_FILES", 3)
    with pytest.raises(collectors.CollectorError, match="more than 3 sitemap files"):
        collectors.sitemap_load(site.url)
    monkeypatch.setattr(collectors, "SITEMAP_FILES", 500)
    monkeypatch.setattr(collectors, "SITEMAP_PAGES", 8)
    assert len(collectors.sitemap_load(site.url)) == 8
    monkeypatch.setattr(collectors, "SITEMAP_PAGES", 7)
    with pytest.raises(collectors.CollectorError, match="more than 7 pages in the sitemap"):
        collectors.sitemap_load(site.url)


# ================================================================ 11. the fake site, by hand

def fake(site, query=""):
    """What a look at /__fake shows."""
    return json.loads(collectors.fetch(site.url + "/__fake" + query, timeout=5, read=1_000_000).body)


def test_only_the_catalogue_of_the_sites_own_platform_answers(site):
    def status(path):
        return collectors.fetch(site.url + path, timeout=5).status

    assert status("/wp-json/wc/store/v1/products?per_page=1") == 200      # the intake's look, exactly as it is written
    assert status("/products.json?limit=1") == 404
    assert status("/wp-json/wc/store/v1/products?per_page=100&page=2") == 400         # a paged read names its order
    assert status("/about/") == 200 and status("/product/p-101/") == 200              # pages of the sitemap and the shop
    answer = collectors.fetch(site.url + "/checkout/", timeout=5, redirects=0)
    assert (answer.status, answer.headers["Location"]) == (302, "/cart/")             # an empty checkout is no page
    site.use("shopify")
    assert status("/products.json?limit=1") == 200 and status("/wp-json/wc/store/v1/products?per_page=1") == 404
    assert [status(path) for path in SHOPIFY_PAGES] == [200] * 5 and status("/product/sample-sofa/") == 404


def test_the_fake_as_a_shopify_shop_passes_every_collector(sql, site, capsys):
    site.use("shopify")
    sql.rpc("sh_setup", p_config=site.config())
    assert run_manage("run-once", "probe") is None
    assert [(row["page"], row["ok"]) for row in json.loads(capsys.readouterr().out)["rows"]] == [
        ("בית", True), ("קטגוריה", True), ("מוצר", True), ("סל", True)]
    assert run_manage("run-once", "sitemap") is None
    assert json.loads(capsys.readouterr().out) == {"n": 310, "pages": 310}            # home, 305 products, 2 + 2 others
    assert run_manage("run-once", "catalogue") is None                    # the count of the sitemap is its proof
    assert json.loads(capsys.readouterr().out)["n"] == 3
    assert [row["url"] for row in sql.rpc("sh_product_issues")] == [site.url + "/products/p-%d" % n for n in (4, 3, 2)]


def test_the_fake_shows_what_arrived_and_never_a_topic(site, phone, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_URL", site.url + "/hb")
    monkeypatch.setenv("NTFY_TOKEN", "tk_secret_token")
    collectors.heartbeat()
    collectors.heartbeat()
    assert collectors.Pusher().publish("כותרת", "גוף") == 200
    shown = fake(site)
    assert shown["heartbeat_pings"] == 2 and shown["last_heartbeat"].startswith("20")             # the pings are counted
    assert [(push["json"]["title"], push["json"]["topic"], push["auth"], push["accepted"]) for push in shown["pushes"]] == [
        ("כותרת", "(topic)", "(token)", True)]
    assert TOPIC not in json.dumps(shown) and "tk_secret_token" not in json.dumps(shown)
    assert site.pushes[0]["json"]["topic"] == TOPIC                       # the tests themselves see what was sent

    # by hand: break a page, look, repair. What arrived is still there to be looked at.
    assert fake(site, "?path=/cart/&status=502")["broken"] == {"/cart/": {"status": 502}}
    shown = fake(site, "?reset=1")
    assert shown["broken"] == {} and len(shown["pushes"]) == 1 and shown["heartbeat_pings"] == 2
    shown = fake(site, "?clear=1")
    assert shown["pushes"] == [] and shown["heartbeat_pings"] == 0 and shown["last_heartbeat"] is None
    # the stand-in for a dashboard's /health
    assert fake(site, "?health_age=700")["health"]["last_probe_age_sec"] == 700
    assert fake(site, "?health_age=none&health_db=down")["health"] == {
        "ok": False, "db": "down", "screen": "ok", "last_probe_age_sec": None}


def test_the_fake_site_by_hand_prints_the_environment_of_a_rehearsal(tmp_path):
    config = tmp_path / "site_health.config.json"
    process = subprocess.Popen([sys.executable, str(REFERENCE / "tests" / "fake_site.py"), "0", str(config),
                                "--platform", "shopify"], stdout=subprocess.PIPE, text=True, encoding="utf-8",
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        printed = ""
        for line in process.stdout:                                       # up to the last line of its help
            printed += line
            if "how many heartbeat pings arrived" in line:
                break
        address = re.search(r"A fake Shopify shop is listening on (http://127\.0\.0\.1:\d+)", printed).group(1)
        assert "export SH_ALLOW_PRIVATE=1" in printed
        assert "export NTFY_URL=%s/ntfy NTFY_TOPIC=sh-local-test" % address in printed
        assert ("export PAGESPEED_URL=%s/pagespeedonline/v5/runPagespeed PAGESPEED_KEY=local-rehearsal-key" % address
                in printed)
        assert "curl '%s/__fake?path=/cart&status=502'" % address in printed
        written = json.loads(config.read_text(encoding="utf-8"))
        assert written["platform"] == "shopify" and written["site"] == address
        assert [(p["name"], p["url"].replace(address, ""), p["probe"], p["core"]) for p in written["pages"]] == [
            ("בית", "/", True, True), ("קטגוריה", "/collections/sofas", True, True),
            ("מוצר", "/products/sample-sofa", True, True), ("סל", "/cart", True, True), ("אודות", "/pages/about", False, True)]
        with urllib.request.urlopen(address + "/products.json?limit=1", timeout=5) as answer:
            assert len(json.loads(answer.read())["products"]) == 1
    finally:
        process.terminate()
        process.wait(10)


def test_the_configuration_of_the_fake_has_a_public_fifth_page(site):
    pages = site.config()["pages"]
    assert [(p["name"], p["url"].replace(site.url, ""), p["probe"], p["core"]) for p in pages] == [
        ("בית", "/", True, True), ("קטגוריה", "/product-category/sofas/", True, True),
        ("מוצר", "/product/sample-sofa/", True, True), ("סל", "/cart/", True, True), ("אודות", "/about/", False, True)]
    assert all(collectors.probe_check(p, 2)["ok"] for p in pages)         # every one of them opens for anybody


# ================================================================ 12. manage.py: the files for the owner

def scratch_database():
    """A database with nothing in it: its connection string, and the name to drop it by."""
    from psycopg.conninfo import make_conninfo
    name = "sh_install_" + os.urandom(6).hex()
    with conftest.connect(conftest.ADMIN_URL, autocommit=True) as admin:
        admin.execute('create database "%s"' % name)
    return make_conninfo(conftest.ADMIN_URL, dbname=name), name


def test_install_sql_writes_one_file_that_installs_an_empty_database_and_runs_twice(site, tmp_path, capsys, monkeypatch):
    brand = "חנות $sh_config$ \"מרכאות\" 'גרש' \\ %s"                       # whatever a configuration may hold
    source, out = tmp_path / "site_health.config.json", tmp_path / "install.sql"
    source.write_text(json.dumps(site.config(brand=brand), ensure_ascii=False), encoding="utf-8")
    assert run_manage("install-sql", "--config", str(source), "--out", str(out)) is None      # no database is set
    printed = capsys.readouterr().out
    assert "wrote %s" % out in printed and "no secret in it" in printed and "init-db --file" in printed
    text = out.read_text(encoding="utf-8")
    schema, functions = ((REFERENCE / name).read_text(encoding="utf-8").rstrip("\n")
                         for name in ("schema.sql", "functions.sql"))
    assert schema in text and functions in text                           # whole, and in the order they depend on
    assert text.index(schema) < text.index(functions) < text.index("select 'Site Health is installed")

    url, name = scratch_database()
    try:
        result = None
        for attempt in (1, 2):                                            # pasted and run, and then once more
            with conftest.connect(url, autocommit=True) as connection:
                cursor = connection.execute(text)                         # one command of many statements, as an editor sends it
                while True:
                    if cursor.description:
                        result = cursor.fetchall()
                    if not cursor.nextset():
                        break
                assert result == [("Site Health is installed for %s" % site.url,)]
                stored = connection.execute("select sh_config()").fetchone()[0]
                assert (stored["site"], stored["brand"], len(stored["pages"]), stored["off"]) == (site.url, brand, 5, ["cert"])
                if attempt == 1:                                          # something measured between the two runs
                    connection.execute("insert into sh_messages (event, kind, title, msg, priority)"
                                       " values ('open', 'התראה', 'כותרת', 'גוף', 3)")
                else:
                    assert connection.execute("select count(*) from sh_messages").fetchone() == (1,)
        if shutil.which("psql"):                                          # and the way a person would run a file
            ran = subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(out)], capture_output=True, text=True)
            assert ran.returncode == 0 and "Site Health is installed for %s" % site.url in ran.stdout, ran.stderr
        monkeypatch.setenv("DATABASE_URL", url)                           # the rehearsal the command itself names
        assert run_manage("init-db", "--file", str(out)) is None
        assert capsys.readouterr().out == "applied install.sql\n"
        assert run_manage("init-db", "--file", str(tmp_path / "missing.sql")).startswith("init-db failed: ")
    finally:
        with conftest.connect(conftest.ADMIN_URL, autocommit=True) as admin:
            admin.execute('drop database if exists "%s" with (force)' % name)


@pytest.mark.parametrize("change, message", [
    ({"time_zone": None}, '"time_zone" is required: the time zone of the site\'s customers, such as Asia/Jerusalem'),
    ({"time_zone": "Mars/Olympus"}, 'unknown "time_zone" Mars/Olympus'),
    ({"site": "example.co.il"}, '"site" must be an absolute http(s) address'),
    ({"pages": "all of them"}, '"pages" must be a list of pages'),
    ({"pages": []}, 'exactly one page must have "home": true, found 0'),
    ({"pages": [{"name": "בית", "url": "https://example.co.il/", "home": True, "probe": True}]},
     "the home page must be a probe page and a core page"),
])
def test_install_sql_refuses_a_configuration_the_database_would_refuse(site, tmp_path, change, message):
    source, out = tmp_path / "site_health.config.json", tmp_path / "install.sql"
    source.write_text(json.dumps(site.config(**change), ensure_ascii=False), encoding="utf-8")
    assert run_manage("install-sql", "--config", str(source), "--out", str(out)) == "%s: %s" % (source, message)
    assert not out.exists()


def test_install_sql_says_what_is_wrong_with_the_file_itself(tmp_path):
    source = tmp_path / "site_health.config.json"
    assert "cannot be read" in run_manage("install-sql", "--config", str(source))
    source.write_text("{not json", encoding="utf-8")
    assert "is not valid JSON" in run_manage("install-sql", "--config", str(source))
    source.write_text("[1, 2]", encoding="utf-8")
    assert "must hold one JSON object" in run_manage("install-sql", "--config", str(source))
    assert "cannot be read" in run_manage("setup", str(tmp_path / "other.json"))      # the same reading, for setup


PHP_STUBS = """<?php
define('ABSPATH', '/');
$GLOBALS['hooks'] = array();
function add_action($name, $fn, $priority = 10) { $GLOBALS['hooks'][$name] = $fn; }
function is_admin() { return false; }
function is_preview() { return false; }
function is_customize_preview() { return false; }
function is_user_logged_in() { return getenv('SH_STAFF') === '1'; }
function current_user_can($what) { return true; }
function wp_json_encode($value) { return json_encode($value); }
function wp_print_inline_script_tag($js, $attributes) { echo '<script id="' . $attributes['id'] . '">' . $js . '</script>'; }
require $argv[1];
$GLOBALS['hooks']['wp_footer']();
"""


def test_rum_plugin_writes_a_wordpress_plugin_zip_with_its_two_values_filled_in(tmp_path, capsys, monkeypatch):
    out = tmp_path / "site-health-rum.zip"
    assert run_manage("rum-plugin", "--endpoint", "https://dash.example.co.il/m", "--live-host", "www.Example.co.il",
                      "--out", str(out)) is None
    printed = capsys.readouterr().out
    assert "sending to https://dash.example.co.il/m, live host example.co.il" in printed
    assert "Plugins > Add new > Upload plugin" in printed and "Nobody edits wp-config.php" in printed
    with zipfile.ZipFile(out) as archive:                                 # what the admin's upload screen takes
        assert archive.namelist() == ["site-health-rum/site-health-rum.php"]
        php = archive.read("site-health-rum/site-health-rum.php").decode("utf-8")
    assert php.startswith("<?php\n/**\n * Plugin Name: Site Health RUM\n")
    assert "define('SITE_HEALTH_RUM_ENDPOINT', 'https://dash.example.co.il/m');" in php
    assert "define('SITE_HEALTH_RUM_LIVE_HOST', 'example.co.il');" in php
    shipped = (REFERENCE / "rum" / "site-health-rum.php").read_text(encoding="utf-8")
    assert php.replace("'https://dash.example.co.il/m');", "'');").replace("'example.co.il');", "'');") == shipped

    if shutil.which("php"):                                               # the plugin itself, in a stand-in WordPress
        plugin, stubs = tmp_path / "site-health-rum.php", tmp_path / "wordpress.php"
        plugin.write_text(php, encoding="utf-8")
        stubs.write_text(PHP_STUBS, encoding="utf-8")
        assert subprocess.run(["php", "-l", str(plugin)], capture_output=True).returncode == 0
        page = subprocess.run(["php", str(stubs), str(plugin)], capture_output=True, text=True, encoding="utf-8").stdout
        head, rest = page.split(";", 1)
        assert head.startswith('<script id="site-health-rum">window.SiteHealthRum=')
        assert json.loads(head.split("=", 2)[2]) == {"endpoint": "https://dash.example.co.il/m",
                                                     "liveHost": "example.co.il", "sample": 1}
        assert rest.startswith("(function () {\nvar cfg = window.SiteHealthRum || {};")
        assert "navigator.sendBeacon(cfg.endpoint, body)" in page and page.endswith("})();</script>")
        staff = subprocess.run(["php", str(stubs), str(plugin)], capture_output=True, text=True,
                               env=dict(os.environ, SH_STAFF="1")).stdout
        assert staff == ""                                                # signed-in staff are not visitors
        plugin.write_text(shipped, encoding="utf-8")                      # and as it ships, without an address: silent
        assert subprocess.run(["php", str(stubs), str(plugin)], capture_output=True, text=True).stdout == ""

    # the live host from the site's configuration, and "/m" added to a bare dashboard address
    config = tmp_path / "site_health.config.json"
    config.write_text(json.dumps({"site": "https://www.shop.example/"}), encoding="utf-8")
    assert run_manage("rum-plugin", "--endpoint", "https://dash.example.co.il", "--config", str(config),
                      "--out", str(out)) is None
    assert "sending to https://dash.example.co.il/m, live host shop.example" in capsys.readouterr().out
    monkeypatch.chdir(tmp_path)                                           # the command exactly as the kit writes it
    (tmp_path / "site-health-rum.zip").unlink()
    assert run_manage("rum-plugin", "--endpoint", "https://dash.example.co.il/m") is None
    assert zipfile.ZipFile(tmp_path / "site-health-rum.zip").namelist() == ["site-health-rum/site-health-rum.php"]


@pytest.mark.parametrize("arguments, message", [
    (["--endpoint", "http://dash.example.co.il/m", "--live-host", "example.co.il"], "--endpoint must be the https address"),
    (["--endpoint", "https://dash.example.co.il/m'); evil(); //", "--live-host", "example.co.il"], "--endpoint must be"),
    (["--endpoint", "dash.example.co.il/m", "--live-host", "example.co.il"], "--endpoint must be"),
    (["--endpoint", "https://dash.example.co.il/m", "--live-host", "exa'mple"], "the live host must be a host name"),
    (["--endpoint", "https://dash.example.co.il/m"], "Which site is the live one?"),
])
def test_rum_plugin_refuses_what_it_cannot_write_into_a_php_file(tmp_path, monkeypatch, arguments, message):
    monkeypatch.chdir(tmp_path)                                           # no configuration file here
    assert run_manage("rum-plugin", *arguments, "--out", str(tmp_path / "plugin.zip")).startswith(message)
    assert not (tmp_path / "plugin.zip").exists()


# ================================================================ 13. watchdog.py: who watches the watcher (§7.10)

STOPPED, BACK = "המדידה נעצרה: בודק זמינות האתר", "חזר לתקין: בודק זמינות האתר"


@pytest.fixture
def guard(site, monkeypatch, tmp_path):
    """The watchdog's surroundings: the fake ntfy, a topic, no waiting, and a state file of this test."""
    monkeypatch.setenv("NTFY_URL", site.url + "/ntfy")
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setattr(watchdog, "TRY_PAUSE", 0.01)
    monkeypatch.setattr(watchdog.tempfile, "tempdir", str(tmp_path))      # where a state file goes by default
    return str(tmp_path / "watchdog-state.json")


def titles(site):
    return [push["json"]["title"] for push in site.pushes]


def test_the_watchdog_speaks_the_same_hebrew_as_the_database(sql):
    spans = dict(sql.sql("select m, sh_span(m) from generate_series(1, 6000) m"))
    assert all(watchdog.span(m * 60) == spans[m] for m in spans)
    assert [watchdog.span(seconds) for seconds in (0, 20, 89, 90, 150, 3600, 7200, 86400, 2 * 86400, 3 * 86400)] == [
        "דקה", "דקה", "דקה", "שתי דקות", "3 דקות", "שעה", "שעתיים", "יום", "יומיים", "3 ימים"]
    assert [watchdog.span(seconds, down=True) for seconds in (119, 659, 660)] == ["דקה", "10 דקות", "11 דקות"]
    assert watchdog.FLOW == PROBE_FLOW and watchdog.LIMIT == 600


def test_the_watchdog_pushes_once_when_the_measuring_stops_and_once_when_it_is_back(site, guard, capsys):
    look = lambda now: watchdog.look(site.url, watchdog.State(guard), now=now)       # each look a new process, as under cron
    start = 1_800_000_000
    assert look(start) == 0 and site.pushes == []                         # the last round is 20 seconds old
    site.health["last_probe_age_sec"] = 600
    assert look(start + 60) == 0 and site.pushes == []                    # ten minutes exactly: not yet
    site.health["last_probe_age_sec"] = 730
    assert look(start + 120) == 0
    assert site.pushes[0]["json"] == {
        "topic": TOPIC, "title": STOPPED, "message": "אין מדידה כבר 12 דקות", "priority": 4, "tags": ["rotating_light"],
        "click": site.url + "/site"}
    assert (site.pushes[0]["path"], site.pushes[0]["type"]) == ("/ntfy/", "application/json")      # as the worker sends
    site.health["last_probe_age_sec"] = 1030
    assert look(start + 420) == 0 and len(site.pushes) == 1               # still stopped: nothing new to say
    site.health["last_probe_age_sec"] = 12
    assert look(start + 480) == 0
    assert site.pushes[1]["json"] == {
        "topic": TOPIC, "title": BACK, "message": STOPPED + "\nנמשך 18 דקות", "priority": 2,
        "tags": ["white_check_mark"], "click": site.url + "/site"}       # 610 seconds before the alarm, 480 after
    assert look(start + 540) == 0 and len(site.pushes) == 2
    printed = capsys.readouterr()
    assert TOPIC not in printed.out + printed.err
    assert printed.out.count("watchdog:") == 3                            # the alarm, the look while it was open, the recovery


def test_a_dashboard_that_gives_no_answer_is_an_alarm_only_when_it_lasts(site, guard):
    look = lambda now: watchdog.look(site.url, watchdog.State(guard), now=now)
    start = 1_800_000_000
    site.broken["/health"] = {"status": 502}
    assert look(start) == 0 and site.pushes == []                         # one look without an answer is no alarm
    assert [path for _, path, _ in site.hits].count("/health") == 3       # it asked three times before saying so
    assert look(start + 300) == 0 and site.pushes == []
    site.broken = {}
    assert look(start + 400) == 0                                         # it answered in between: the count starts anew
    site.health = None                                                    # a page that is not the answer of /health
    assert look(start + 500) == 0 and look(start + 1099) == 0 and site.pushes == []
    assert look(start + 1100) == 0
    assert site.pushes[0]["json"]["title"] == STOPPED
    assert site.pushes[0]["json"]["message"] == "המסך של בריאות האתר לא עונה כבר 10 דקות"
    assert look(start + 1400) == 0 and len(site.pushes) == 1
    site.health = {"ok": True, "db": "ok", "screen": "ok", "last_probe_age_sec": 30}
    assert look(start + 1700) == 0
    assert site.pushes[1]["json"]["message"] == STOPPED + "\nנמשך 20 דקות"            # from the first silent look


def test_a_dashboard_without_its_database_is_an_alarm_of_its_own_words(site, guard):
    look = lambda now: watchdog.look(site.url, watchdog.State(guard), now=now)
    site.health = {"ok": False, "db": "database unreachable (ConnectionRefusedError)", "screen": "ok",
                   "last_probe_age_sec": None}
    assert look(1_800_000_000) == 0 and look(1_800_000_599) == 0 and site.pushes == []
    assert look(1_800_000_725) == 0
    assert (site.pushes[0]["json"]["title"], site.pushes[0]["json"]["message"]) == (STOPPED, "אין חיבור לנתונים כבר 12 דקות")


def test_a_site_that_was_never_measured_is_not_an_alarm(site, guard):
    site.health["last_probe_age_sec"] = None                              # set up a moment ago: no round yet
    for later in (0, 3600, 86400):
        assert watchdog.look(site.url, watchdog.State(guard), now=1_800_000_000 + later) == 0
    assert site.pushes == []


def test_a_push_that_ntfy_refused_is_owed_until_it_goes_out(site, guard, capsys):
    look = lambda now: watchdog.look(site.url, watchdog.State(guard), now=now)
    site.health["last_probe_age_sec"] = 700
    site.ntfy_status = 500
    assert look(1_800_000_000) == 1                                       # the exit code tells cron
    assert "watchdog: ntfy refused the push (HTTP 500)" in capsys.readouterr().err
    site.ntfy_status = 200
    assert look(1_800_000_300) == 0 and look(1_800_000_600) == 0
    assert [(push["json"]["title"], push["accepted"]) for push in site.pushes] == [(STOPPED, False), (STOPPED, True)]
    site.health["last_probe_age_sec"] = 5                                 # and the same for the recovery
    site.ntfy_status = 403
    assert look(1_800_000_900) == 1
    site.ntfy_status = 200
    site.broken["/ntfy/"] = {"to": site.url + "/"}                        # a server that sends the push elsewhere:
    assert look(1_800_001_000) == 1                                       # a page that answers 200 there is no "accepted"
    assert "watchdog: ntfy refused the push (HTTP 302)" in capsys.readouterr().err
    site.broken = {}
    assert look(1_800_001_200) == 0 and look(1_800_001_500) == 0
    assert [(push["json"]["title"], push["accepted"]) for push in site.pushes[2:]] == [(BACK, False), (BACK, True)]


def test_the_watchdog_as_a_command_under_cron_and_as_a_loop(site, guard, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NTFY_TOKEN", "tk_test_token")
    command = ["--dashboard", site.url + "/"]
    assert watchdog.main(command) == 0 and site.pushes == []
    default = tmp_path / "site-health-watchdog.json"                      # in the system's temporary folder
    assert json.loads(default.read_text(encoding="utf-8")) == {"open": False, "since": None, "blind": None}
    assert capsys.readouterr().out == ""                                  # all is well: cron has nothing to mail
    assert watchdog.main(command + ["--verbose"]) == 0
    assert capsys.readouterr().out == "watchdog: the last probe round is 20 seconds old\n"
    site.health["last_probe_age_sec"] = 900
    assert watchdog.main(command) == 0 and watchdog.main(command) == 0
    assert titles(site) == [STOPPED] and site.pushes[0]["auth"] == "Bearer tk_test_token"
    assert json.loads(default.read_text(encoding="utf-8"))["open"] is True
    assert 'pushed "%s": yes' % STOPPED in capsys.readouterr().out
    site.health["last_probe_age_sec"] = 3
    assert watchdog.main(command + ["--state", guard]) == 0               # another file knows of no alarm
    assert watchdog.main(command) == 0 and titles(site) == [STOPPED, BACK]

    # --loop: the same looks, a minute apart, remembered in memory
    default.unlink()
    script = [lambda: site.health.update(last_probe_age_sec=700), lambda: None, lambda: site.health.update(last_probe_age_sec=4)]
    rests = []

    def rest(seconds):
        rests.append(seconds)
        if not script:
            raise KeyboardInterrupt
        script.pop(0)()

    monkeypatch.setattr(watchdog, "rest", rest)
    monkeypatch.setenv("DASHBOARD_URL", site.url)                         # may stand in for --dashboard
    assert watchdog.main(["--loop"]) == 0
    assert titles(site)[2:] == [STOPPED, BACK] and rests == [60, 60, 60, 60] and not default.exists()
    printed = capsys.readouterr()
    assert TOPIC not in printed.out + printed.err and "tk_test_token" not in printed.out + printed.err


@pytest.mark.parametrize("arguments, topic, message", [
    ([], TOPIC, "name the dashboard"),
    (["--dashboard", "dash.example.co.il"], TOPIC, "name the dashboard"),
    (["--dashboard", "https://dash.example.co.il"], "", "NTFY_TOPIC is not set"),
])
def test_the_watchdog_needs_a_dashboard_and_a_topic(site, monkeypatch, capsys, arguments, topic, message):
    monkeypatch.setenv("NTFY_TOPIC", topic)
    with pytest.raises(SystemExit) as stop:
        watchdog.main(arguments)
    assert stop.value.code == 2 and message in capsys.readouterr().err


def test_what_one_look_decides():
    now = 1_800_000_000
    idle = {"open": False, "since": None, "blind": None}
    alarm = {"open": True, "since": now - 900, "blind": None}
    assert watchdog.decide(("age", 600), idle, now)[:2] == (idle, None)
    state, push, said = watchdog.decide(("age", 601), idle, now)
    assert (state, push["title"], push["message"], push["priority"]) == (
        {"open": True, "since": now - 601, "blind": None}, STOPPED, "אין מדידה כבר 10 דקות", 4)
    assert watchdog.decide(("age", 5000), alarm, now)[:2] == (alarm, None)
    state, push, said = watchdog.decide(("age", 59), alarm, now)
    assert (state, push["title"], push["message"], push["priority"]) == (idle, BACK, STOPPED + "\nנמשך 15 דקות", 2)
    assert watchdog.decide(("new", None), idle, now)[:2] == (idle, None)
    assert watchdog.decide(("new", None), alarm, now)[:2] == (alarm, None)            # nothing to judge by: left as it is
    blind = {"open": False, "since": None, "blind": now}
    assert watchdog.decide(("silent", "HTTP 502"), idle, now)[:2] == (blind, None)
    assert watchdog.decide(("silent", "HTTP 502"), blind, now + 599)[:2] == (blind, None)
    state, push, said = watchdog.decide(("silent", "HTTP 502"), blind, now + 600)
    assert state == {"open": True, "since": now, "blind": now} and push["message"] == "המסך של בריאות האתר לא עונה כבר 10 דקות"
    state, push, said = watchdog.decide(("no data", "x"), blind, now + 7200)
    assert push["message"] == "אין חיבור לנתונים כבר שעתיים"
    assert watchdog.decide(("age", 30), blind, now + 300)[:2] == (idle, None)         # it answered again: forgotten


@pytest.fixture
def dashboard(sql, database, site):
    """The reference server itself, on a port of its own and on the scratch database, measuring nothing."""
    port = closed_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=str(REFERENCE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, DATABASE_URL=database, COLLECTORS="0", SH_PASS_OWNER="a-password-of-this-test"))
    address = "http://127.0.0.1:%d" % port
    try:
        for _ in range(100):                                              # until it answers
            try:
                with urllib.request.urlopen(address + "/health", timeout=2) as answer:
                    if answer.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("the reference server did not come up on %s" % address)
        yield address, process
    finally:
        process.terminate()
        process.wait(10)


def test_the_watchdog_against_the_reference_server(sql, site, dashboard, guard):
    address, process = dashboard
    config = collectors.read_config()
    run = lambda: watchdog.main(["--dashboard", address, "--state", guard])
    assert run() == 0 and site.pushes == []                               # set up, and never measured: no alarm
    collectors.probe_round(config.probe, "full", this_minute() - minutes(1))
    assert run() == 0 and site.pushes == []                               # the worker measures

    # the worker stops: eleven minutes later the newest full round is that old
    sql.sql("update sh_flows set last_at = now() - interval '11 minutes' where flow_name = %s", [PROBE_FLOW])
    assert run() == 0 and run() == 0
    assert titles(site) == [STOPPED] and site.pushes[0]["json"]["message"] == "אין מדידה כבר 11 דקות"
    assert site.pushes[0]["json"]["click"] == address + "/site"

    collectors.probe_round(config.probe, "full", this_minute())           # the worker is started again
    assert run() == 0 and run() == 0
    assert titles(site) == [STOPPED, BACK]
    assert re.fullmatch(STOPPED + "\nנמשך 1[12] דקות", site.pushes[1]["json"]["message"])

    process.terminate()                                                   # and then the whole dashboard goes away
    process.wait(10)
    assert run() == 0 and len(site.pushes) == 2                           # the first silent look
    state = json.loads(Path(guard).read_text(encoding="utf-8"))
    assert state["open"] is False and state["blind"] is not None
    Path(guard).write_text(json.dumps(dict(state, blind=state["blind"] - 601)), encoding="utf-8")     # ten minutes later
    assert run() == 0
    assert titles(site)[2:] == [STOPPED] and site.pushes[2]["json"]["message"] == "המסך של בריאות האתר לא עונה כבר 10 דקות"
