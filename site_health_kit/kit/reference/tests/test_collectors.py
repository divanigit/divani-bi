"""Tests of collectors.py and manage.py.

Everything runs against a local fake website (fake_site.py: pages, sitemaps, a WooCommerce and a
Shopify catalogue, a PageSpeed endpoint, an ntfy server) and a scratch database with schema.sql and
functions.sql applied for real (conftest.py). The collectors reach that database through db.rpc and
DATABASE_URL, exactly as in production. No test talks to anything outside this machine.

    cd reference && python3 -m pytest -q tests/test_collectors.py
"""
import gzip
import json
import logging
import queue
import re
import socket
import sys
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REFERENCE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REFERENCE), str(REFERENCE / "tests")]

import collectors  # noqa: E402
import db  # noqa: E402
import manage  # noqa: E402
from fake_site import PAGES, FakeSite, sitemap_index, urlset  # noqa: E402

UTC = timezone.utc
ZONE = ZoneInfo("Asia/Jerusalem")                 # the time zone of the fake site's configuration
ENVIRONMENT = ("PAGESPEED_KEY", "NTFY_TOPIC", "NTFY_URL", "NTFY_TOKEN", "DASHBOARD_URL", "HEARTBEAT_URL",
               "SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATABASE_URL")
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
    monkeypatch.setattr(collectors, "PSI_URL", server.url + "/pagespeedonline/v5/runPagespeed")
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
    assert [p["name"] for p in config.probe] == ["בית", "קטגוריה", "מוצר", "סל"]         # the checkout is not probed
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
    monkeypatch.setattr(collectors, "probe_check", lambda page, timeout: seen.append(timeout) or {"ms": 1})
    monkeypatch.setattr(db, "rpc", lambda fn, params: {"n": 1})
    collectors.probe_round([page(site, "/")], "full", T0)
    collectors.probe_round([page(site, "/")], "light", T0)
    assert seen == [10, 5]


def test_a_round_ends_even_when_a_check_never_returns(sql, site, monkeypatch):
    real = collectors.probe_check
    monkeypatch.setattr(collectors, "STUCK_GRACE", 0.2)
    monkeypatch.setattr(collectors, "probe_check",
                        lambda page, timeout: time.sleep(5) if page["name"] == "סל" else real(page, timeout))
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
    assert [(d["title"], d["status"]) for d in done] == [("האתר לא עונה: סל", 200)]
    assert site.pushes[1]["json"] == {
        "topic": TOPIC, "title": "חזר לתקין: האתר לא עונה: סל", "message": "נמשך 0 דקות", "priority": 2,
        "tags": ["white_check_mark"], "click": "https://dash.example/site"}
    window = {"p_from": now - minutes(5), "p_to": now + minutes(2)}
    assert [(m["kind"], m["title"], m["sent"]) for m in sql.rpc("sh_messages", **window)] == [
        ("חזר לתקין", "האתר לא עונה: סל", True), ("התראה", "האתר לא עונה: סל", True)]
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
    assert as_push("close", "חזר לתקין", 2) == ("חזר לתקין: כותרת", "גוף", 2, ["white_check_mark"])
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
    monkeypatch.setattr(collectors, "PSI_URL", "http://127.0.0.1:%d/run" % closed_port())
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


def test_a_refused_key_is_not_tried_again_and_is_never_logged(sql, site, caplog):
    config, clock = collectors.read_config(), Clock(T0)
    speed = collectors.SpeedSchedule(KEY, clock)
    site.psi = "bad_key"
    assert speed.step(config) == [] and len(site.psi_calls) == 1
    site.psi = "lighthouse13"                                            # even a repaired key needs a restart
    for later in (minutes(15), timedelta(days=1), timedelta(days=30)):
        clock.at = T0 + later
        assert speed.step(config) == []
    assert len(site.psi_calls) == 1 and sql.sql("select count(*) from sh_speed") == [(0,)]
    assert caplog.text.count("PageSpeed does not accept the key") == 1 and KEY not in caplog.text
    assert [record.levelname for record in caplog.records if "PageSpeed" in record.message] == ["ERROR"]


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
    with pytest.raises(collectors.CollectorError, match="more than 50 MB"):
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
    rows = collectors.catalogue_shopify(site.url, 305)
    assert rows == [
        {"product_id": "2", "issue": "לא במלאי", "name": "Sold out chair", "url": site.url + "/products/p-2"},
        {"product_id": "3", "issue": "בלי תמונה", "name": "Table without a picture", "url": site.url + "/products/p-3"},
        {"product_id": "4", "issue": "בלי מחיר", "name": "Shelf without a price", "url": site.url + "/products/p-4"}]
    assert [path for _, path, _ in site.hits] == ["/products.json?limit=250&page=%d" % n for n in (1, 2, 3)]


def test_a_shopify_read_is_checked_against_the_sitemap(sql, site):
    assert len(collectors.catalogue_shopify(site.url, 300)) == 3          # within 2% of the sitemap's count
    with pytest.raises(collectors.CollectorError, match="305 products were read and the sitemap lists 400"):
        collectors.catalogue_shopify(site.url, 400)
    site.shopify.append(dict(site.shopify[0]))
    with pytest.raises(collectors.CollectorError, match="a product was read twice"):
        collectors.catalogue_shopify(site.url, 306)
    site.catalogue = "html"                                               # a shop behind its password page
    with pytest.raises(collectors.CollectorError, match="did not answer with JSON"):
        collectors.catalogue_shopify(site.url, 305)


def test_the_shopify_job_counts_the_products_of_the_sitemap(sql, site):
    sql.rpc("sh_setup", p_config=site.config(platform="shopify"))
    site.files["/robots.txt"] = ("text/plain", ("Sitemap: %s/sitemap.xml\n" % site.url).encode())
    site.files["/sitemap.xml"] = sitemap_index(site.url, "/sitemap_products_1.xml?from=1&to=1300", "/sitemap_pages_1.xml")
    site.files["/sitemap_products_1.xml?from=1&to=1300"] = urlset(
        site.url, "/", *("/products/%s" % p["handle"] for p in site.shopify))
    site.files["/sitemap_pages_1.xml"] = urlset(site.url, "/pages/about")
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
    config = collectors.read_config()
    assert config.morning == (7, 30) and config.zone == ZONE and config.site == site.url
    assert [collectors.daily_time(job, config) for job, _ in collectors.DAILY_JOBS] == [
        (3, 0), (3, 30), (4, 0), None, (7, 30)]                           # no certificate on a site without https
    secure = config._replace(site="https://example.co.il", platform="other", morning=(6, 15))
    assert [collectors.daily_time(job, secure) for job, _ in collectors.DAILY_JOBS] == [
        (3, 0), (3, 30), None, (4, 0), (6, 15)]                           # and no catalogue on a site that sells nothing


def test_the_real_daily_jobs_run_once_and_leave_their_proof_of_life(sql, site, phone):
    config, pusher = collectors.read_config(), collectors.Pusher()
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


def test_new_secret_prints_a_fresh_topic_and_a_fresh_share_token(capsys):
    assert run_manage("new-secret") is None
    first = capsys.readouterr().out.splitlines()
    assert re.fullmatch(r"NTFY_TOPIC=sh-[A-Za-z0-9]{24}", first[0])
    assert re.fullmatch(r"SH_SHARE_TOKEN=[A-Za-z0-9_-]{32}", first[1]) and len(first) == 2
    run_manage("new-secret")
    assert capsys.readouterr().out.splitlines() != first


def test_setup_loads_a_configuration_file_and_check_reports_names_not_values(sql, site, tmp_path, monkeypatch, capsys):
    sql.sql("delete from sh_settings")
    path = tmp_path / "site_health.config.json"
    path.write_text(json.dumps(site.config(), ensure_ascii=False), encoding="utf-8")
    assert run_manage("setup", str(path)) is None
    assert capsys.readouterr().out == (
        "%s is set up: time zone Asia/Jerusalem, platform woocommerce, 4 probe pages, 5 core pages\n" % site.url)

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
    assert run_manage("run-once", "morning") is None
    assert json.loads(capsys.readouterr().out) == {"n": 1}
    assert markers(sql) == [("issues_snapshot", datetime.now(ZONE).date()), ("morning", datetime.now(ZONE).date())]

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
