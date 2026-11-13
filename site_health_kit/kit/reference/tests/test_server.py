"""Tests of server.py: access rules (spec §8), the data contract (spec §5), the page, the real-user
ingest (POST /m, spec §7.7) and /health; of db.py; of tools/check_access.py; and of conftest.py.

No database is needed for the server: db.rpc is replaced by a fake that records every call and
answers with the payloads of the kit's mock_server.py. db.py is tested against a stand-in for
Supabase (its HTTPS transport) and against a scratch database when one can be made (its Postgres
transport; skipped otherwise). The kit's own files are found as conftest.py says.

    cd reference && python3 -m pytest -q tests/test_server.py
"""
import contextlib
import copy
import hmac
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import conftest

REFERENCE = Path(__file__).resolve().parent.parent
KIT = conftest.kit_dir()                                      # mock_server.py and site_health.html; it is on sys.path
sys.path.insert(0, str(REFERENCE))                            # server.py and db.py

import db  # noqa: E402
import mock_server  # noqa: E402
import server  # noqa: E402

REAL_RPC = db.rpc                                             # the tests of the server replace db.rpc
OUTER_ENV = dict(os.environ)                                  # for child processes: the fixture below cleans os.environ
SCREEN = KIT / "site_health.html"
CHECK_ACCESS = KIT / "tools" / "check_access.py"
TOKEN = "share-token-9f3a-for-the-tests"
PASSWORDS = {"owner": "Owner Pass-1", "staff": "staff-pass-02", "vendor": "agency-pass-03",
             "noalerts": "developer-pass-04"}
ENV = {"SH_PASS_OWNER": PASSWORDS["owner"], "SH_PASS_STAFF": PASSWORDS["staff"],
       "SH_PASS_VENDOR_AGENCY": PASSWORDS["vendor"], "SH_PASS_VENDOR_DEVELOPER": PASSWORDS["noalerts"],
       "SH_VENDOR_NOALERTS": " developer ,", "SH_SHARE_TOKEN": TOKEN, "COLLECTORS": "0", "SH_SCREEN": str(SCREEN)}
ROLES = ("owner", "staff", "vendor", "noalerts", "share", None)             # None = nobody
SCREEN_ROLE = {"owner": {}, "staff": {}, "vendor": {"readonly": True},
               "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}
# sh_config() after sh_setup of site_health.config.example.json (the page list is shortened)
SCREEN_CONFIG = {"siteLabel": "example.co.il", "brand": "", "homePage": "בית", "probeCount": 4, "coreCount": 5,
                 "downAfter": 1, "liveHosts": ["live"],
                 "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]], "bucketNote": "",
                 "hide": [], "nav": [], "links": []}
# What an outsider's page carries: no menu and no extra buttons, which hold the addresses of the owner's other screens
OUTSIDER_SCREEN = {key: value for key, value in SCREEN_CONFIG.items() if key not in ("nav", "links")}
MENU = {"nav": [["g", "פנימי"], ["a", "https://intranet.example.co.il/sales-secret-dashboard", "מכירות"]],
        "links": [{"href": "https://intranet.example.co.il/reports", "label": "דוחות", "title": "הורדת דוחות"}]}
CONFIG = {"site": "https://example.co.il", "host": "example.co.il", "label": "example.co.il", "brand": "",
          "time_zone": "Asia/Jerusalem", "platform": "woocommerce", "down_after": 1, "morning": "07:30",
          "keep_days": 100, "off": [], "hide": [], "nav": [], "links": [], "extra_hosts": [], "rum_hosts": [],
          "private_paths": [], "live_hosts": ["live"], "bucket_note": "",
          "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
          "pages": [{"name": "בית", "url": "https://example.co.il/", "probe": True, "core": True, "home": True,
                     "expect": None}],
          "screen": SCREEN_CONFIG}
NOT_SET_UP = {"keep_days": 100, "rum_hosts": [], "private_paths": [], "extra_hosts": [], "off": [], "hide": [],
              "nav": [], "links": [], "pages": [],                          # sh_config() before sh_setup
              "screen": {"hide": [], "coreCount": 0, "probeCount": 0}}
SAFE = {"x-robots-tag": "noindex", "referrer-policy": "no-referrer", "x-frame-options": "DENY",
        "x-content-type-options": "nosniff"}                  # the headers of every answer (spec §8.2)
NOW = datetime(2026, 11, 13, 8, 15, 30, tzinfo=timezone.utc)                # 10:15:30 in Jerusalem (UTC+2)
SITE_PARTS = {"availability": "sh_availability", "availability_series": "sh_availability_series",
              "speed": "sh_speed", "speed_series": "sh_speed_series", "alerts_open": "sh_alerts_open",
              "alerts_recent": "sh_alerts_range", "health": "sh_health", "product_issues": "sh_product_issues",
              "cert": "sh_cert"}
BEACON = {"site": "live", "path": "/product/sofa/", "lcp": 2345, "test": False}
ORIGIN = {"Origin": "https://example.co.il"}


class FakeDb:
    """Stands in for db.rpc: records (function, parameters) and answers like the SQL functions would.
    The answers are unfiltered, as a database's are; filtering by role is the server's job."""

    def __init__(self):
        self.calls, self.answered, self.failing, self.barrier, self.lock = [], {}, set(), None, threading.Lock()
        site = mock_server.api_site({"h": "168"}, "owner")
        self.answers = {fn: site[key] for key, fn in SITE_PARTS.items()}
        self.answers.update(sh_config=CONFIG, sh_now=mock_server.api_now("owner"), sh_ping="ok",
                            sh_messages=mock_server.api_messages({})["rows"], sh_login_log_add=None)

    def __call__(self, fn, params=None):
        with self.lock:
            self.calls.append((fn, params))
        if self.barrier and fn in SITE_PARTS.values():
            self.barrier.wait()                                # passes only when all nine wait at the same time
        if fn in self.failing:
            raise db.DbError("boom: " + fn)
        if fn == "sh_rum_add" and any("refused" in row["path"] for row in params["p_rows"]):
            raise db.DbError("unsupported Unicode escape sequence", answered=True)     # the data's fault
        self.answered[fn] = self.answer(fn, params)
        return copy.deepcopy(self.answered[fn])                # the server may not change what the tests compare with

    def answer(self, fn, params):
        if fn in self.answers:
            return self.answers[fn]
        if fn == "sh_drill_alert":
            return mock_server.api_drill({"what": "alert", "id": str(params["p_id"])}, "owner")["rows"]
        if fn.startswith("sh_drill_"):
            return mock_server.api_drill({"what": fn[len("sh_drill_"):]}, "owner")["rows"]
        if fn == "sh_alert_ack":
            return {"n": len(params["p_ids"])}
        if fn == "sh_rum_add":
            return {"n": len(params["p_rows"])}
        raise AssertionError("the server called an unknown function: " + fn)

    def names(self):
        return [fn for fn, _ in self.calls]

    def params(self, fn):
        found = [params for name, params in self.calls if name == fn]
        assert len(found) == 1, "%s was called %d times" % (fn, len(found))
        return found[0]


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    for name in [name for name in os.environ if name.startswith("SH_")]:
        monkeypatch.delenv(name)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    fake = FakeDb()
    monkeypatch.setattr(db, "rpc", fake)
    monkeypatch.setattr(server, "_now", lambda: NOW)
    monkeypatch.setattr(server, "_site_cache", {"at": 0.0, "site": None})
    monkeypatch.setattr(server, "_rum_minute", {"minute": None, "seen": {}})
    monkeypatch.setattr(server, "_rum_budget", {"minute": None, "in_minute": 0, "day": None, "in_day": 0, "said": None})
    monkeypatch.setattr(server, "_rum_busy", False)
    monkeypatch.setattr(server, "_screen_cache", {"key": None, "parts": None})
    server._failures.clear()
    server._rum_queue.clear()
    return fake


@pytest.fixture
def clock(monkeypatch):
    """The server's monotonic clock, movable. Only server.time is replaced, not the event loop's clock."""
    clock = types.SimpleNamespace(t=1000.0)
    clock.monotonic = lambda: clock.t
    monkeypatch.setattr(server, "time", clock)
    return clock


def sign_in(client, password, **headers):
    return client.post("/login", data={"p": password}, headers=headers)


@pytest.fixture
def visit(fake):
    """visit(role) -> a client signed in as that role (no session for "share" and None)."""
    def visit(role=None, **options):
        client = TestClient(server.app, follow_redirects=False, **options)
        if role in PASSWORDS:
            assert sign_in(client, PASSWORDS[role]).status_code == 303
        fake.calls.clear()
        return client
    return visit


def send(visit, role, method, path, **options):
    """One request as `role`. The share link has no session: its token rides on every request."""
    path, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query), **options.pop("params", {}))
    if role == "share":
        params["k"] = TOKEN
    return visit(role).request(method, path, params=params, **options)


def cookie_of(response):
    """The session cookie a sign-in set, as (value, attributes in lower case)."""
    value, *attributes = response.headers["set-cookie"].split("; ")
    assert value.startswith(server.COOKIE + "=")
    return value.split("=", 1)[1], {a.lower() for a in attributes}


def expiry(days):
    """The expiry inside a cookie that was made at NOW for that many days."""
    return int(NOW.timestamp()) + days * 86400


def safe(response):
    """Whether an answer carries the four headers of spec §8.2."""
    return {name: response.headers.get(name) for name in SAFE} == SAFE


class Scripts(HTMLParser):
    """The text of every <script> element, as a browser's tokenizer would cut them."""

    def __init__(self, page):
        super().__init__()
        self.found, self.inside = [], False
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True
            self.found.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.found[-1] += data


def injected(page):
    """(SH_CONFIG, SH_ROLE) as written into the page, read back from its first script."""
    config, role = re.fullmatch(r"window\.SH_CONFIG=(.*);window\.SH_ROLE=(.*);", Scripts(page).found[0], re.S).groups()
    return json.loads(config), json.loads(role)


# ================================================================ routes and access (spec §8.2)

def test_the_app_exposes_exactly_the_specified_routes():
    routes = {(method, route.path) for route in server.app.routes for method in route.methods}
    assert routes == {("GET", "/"), ("GET", "/site"), ("GET", "/status"), ("GET", "/login"), ("POST", "/login"),
                      ("GET", "/logout"), ("GET", "/health"), ("GET", "/api/site"), ("GET", "/api/site/now"),
                      ("GET", "/api/site/drill"), ("GET", "/api/messages"), ("POST", "/api/alerts/ack"),
                      ("POST", "/m")}


TO_LOGIN, TO_SITE = (303, "/login"), (303, "/site")
ACCESS = [
    # method, path, body                      owner+staff   vendors    share link  nobody
    ("GET", "/", None,                        TO_SITE,      TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("GET", "/site", None,                    200,          200,       TO_LOGIN,   TO_LOGIN),
    ("GET", "/status", None,                  403,          403,       200,        403),     # only the token counts
    ("GET", "/login", None,                   (303, "/"),   (303, "/"), 200,       200),
    ("GET", "/logout", None,                  TO_LOGIN,     TO_LOGIN,  TO_LOGIN,   TO_LOGIN),
    ("GET", "/health", None,                  200,          200,       200,        200),
    ("POST", "/m", None,                      204,          204,       204,        204),
    ("GET", "/m", None,                       405,          405,       405,        405),
    ("POST", "/rum", None,                    404,          TO_SITE,   TO_LOGIN,   TO_LOGIN),   # the old name: no alias
    ("GET", "/api/site", None,                200,          200,       200,        401),
    ("GET", "/api/site/now", None,            200,          200,       200,        401),
    ("GET", "/api/site/drill?what=fails", None, 200,        200,       200,        401),
    ("GET", "/api/messages", None,            200,          403,       401,        401),
    ("POST", "/api/alerts/ack", {"ids": [41]}, 200,         403,       401,        401),
    # POST is refused for outsiders even on the paths they may read
    ("POST", "/api/site", None,               405,          403,       403,        401),
    ("POST", "/api/site/now", None,           405,          403,       403,        401),
    ("POST", "/api/site/drill", None,         405,          403,       403,        401),
    ("POST", "/site", None,                   405,          TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("POST", "/status", None,                 403,          403,       TO_SITE,    403),
    ("DELETE", "/api/alerts/ack", None,       405,          403,       401,        401),
    # paths that are on no list
    ("GET", "/api/anything", None,            404,          403,       401,        401),
    ("GET", "/anything", None,                404,          TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("GET", "/site/", None,                   (307, "http://testserver/site"), TO_SITE, TO_LOGIN, TO_LOGIN),
]
COLUMN = {"owner": 3, "staff": 3, "vendor": 4, "noalerts": 4, "share": 5, None: 6}


@pytest.mark.parametrize("role", ROLES, ids=str)
@pytest.mark.parametrize("row", ACCESS, ids=lambda row: "%s %s" % row[:2])
def test_access(row, role, fake, visit):
    method, path, body = row[:3]
    expected = row[COLUMN[role]]
    response = send(visit, role, method, path, json=body)
    status, location = expected if isinstance(expected, tuple) else (expected, None)
    assert (response.status_code, response.headers.get("location")) == (status, location)
    assert safe(response)                                      # on every answer: pages, data, redirects, refusals
    if status in (401, 403) and path.startswith("/api/"):
        assert response.json() == {"error": "auth"}
        assert response.headers["cache-control"] == "no-store"
        assert fake.calls == []                                # refused before anything is read
    if status == 303:
        assert fake.calls == []


@pytest.fixture
def later_routes():
    """Two routes "added later" by somebody who forgot about roles."""
    before = list(server.app.router.routes)
    server.app.add_api_route("/api/later", lambda: {"secret": 1}, methods=["GET"])
    server.app.add_api_route("/later", lambda: {"secret": 1}, methods=["GET"])
    yield
    server.app.router.routes[:] = before


@pytest.mark.parametrize("role, data, page", [
    ("owner", 200, 200), ("staff", 200, 200), ("vendor", 403, 303), ("noalerts", 403, 303),
    ("share", 401, 303), (None, 401, 303)], ids=str)
def test_a_route_added_later_is_closed_to_outsiders(role, data, page, visit, later_routes):
    assert send(visit, role, "GET", "/api/later").status_code == data
    response = send(visit, role, "GET", "/later")
    assert response.status_code == page
    if page == 303:
        assert response.headers["location"] == ("/site" if role in ("vendor", "noalerts") else "/login")
        assert "secret" not in response.text


def test_a_refusal_has_the_shape_the_screen_expects(visit):
    nobody = visit(None).get("/api/site")
    assert (nobody.status_code, nobody.json()) == (401, {"error": "auth"})
    vendor = visit("vendor").get("/api/messages")
    assert (vendor.status_code, vendor.json()) == (403, {"error": "auth"})
    link = visit(None).get("/status", params={"k": "wrong"})
    assert link.status_code == 403 and server.TEXT_BAD_LINK in link.text and "\n" not in server.TEXT_BAD_LINK


def test_the_hebrew_texts_are_those_of_the_spec(visit):
    assert (server.TEXT_WRONG, server.TEXT_BLOCKED, server.TEXT_BAD_LINK, server.TEXT_NO_DATA, server.TEXT_FAULT) == (
        "סיסמה שגויה", "יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.", "הקישור אינו תקין או שפג תוקפו.",
        "אין כרגע חיבור לנתונים. נסו שוב בעוד רגע.", "משהו השתבש. נסו שוב בעוד כמה דקות.")
    form = visit(None).get("/login").text
    assert '<button type="submit">כניסה</button>' in form and 'placeholder="סיסמה"' in form
    assert server.COOKIE == "sh_session"


@pytest.mark.parametrize("method, path, status", [("GET", "/health", 200), ("POST", "/m", 204), ("GET", "/login", 200),
                                                  ("POST", "/login", 401), ("GET", "/logout", 303)])
def test_the_public_routes_answer_before_any_role_check(method, path, status, monkeypatch, visit):
    def no_roles(request):
        raise AssertionError("a public route asked who the viewer is")

    monkeypatch.setattr(server, "_viewer", no_roles)
    client = visit(None)
    response = client.request(method, path, headers={"Cookie": server.COOKIE + "=forged"})
    assert response.status_code == status
    with pytest.raises(AssertionError, match="asked who the viewer is"):
        client.get("/site")                                    # every other route does ask


@pytest.fixture
def parameter_route():
    """A route "added later" that matches any single path segment."""
    before = list(server.app.router.routes)
    server.app.add_api_route("/{page}", lambda page: {"secret": page}, methods=["GET"])
    yield
    server.app.router.routes[:] = before


@pytest.mark.parametrize("role, path, to", [
    # an encoded "?" or "#" belongs to the path; the gate must not read "/login%3Fx" as the public "/login"
    (None, "/login%3Fx", "/login"), (None, "/health%23x", "/login"), (None, "/m%3F", "/login"),
    (None, "/logout%3Fnext", "/login"), ("share", "/status%3Fx", "/login"),
    ("vendor", "/site%3Fx", "/site"), ("vendor", "/login%3Fx", "/site"), ("noalerts", "/health%23", "/site"),
])
def test_the_gate_judges_the_path_that_the_router_matches(role, path, to, visit, parameter_route):
    response = send(visit, role, "GET", path)
    assert (response.status_code, response.headers.get("location")) == (303, to)
    assert "secret" not in response.text
    assert visit("owner").get(path).json() == {"secret": urllib.parse.unquote(path)[1:]}     # the route is there


def test_an_unforeseen_failure_is_a_500_that_says_nothing(monkeypatch, tmp_path, visit):
    monkeypatch.setenv("SH_SCREEN", str(tmp_path / "no-such-screen.html"))
    client = visit("owner", raise_server_exceptions=False)
    page = client.get("/site")
    assert page.status_code == 500 and server.TEXT_FAULT in page.text and safe(page)
    assert "no-such-screen" not in page.text and "Traceback" not in page.text and "Error" not in page.text

    def crash(request):
        raise RuntimeError("the detail of a bug")

    monkeypatch.setattr(server, "_strategy", crash)
    data = client.get("/api/site")
    assert (data.status_code, data.json()) == (500, {"error": "server error"}) and safe(data)
    assert data.headers["cache-control"] == "no-store"
    with pytest.raises(RuntimeError, match="the detail of a bug"):
        visit("owner").get("/api/site")                        # the server program still gets it, for its log


# ---------------------------------------------------------------- what an outsider gets back

def ids(rows):
    return [row["id"] for row in rows]


def test_the_fixture_holds_what_the_filter_tests_need(fake):
    assert {row["kind"] for row in fake.answers["sh_alerts_open"]} == {"down", "slow", "ops"}
    assert ids(fake.answers["sh_alerts_open"]) == [41, 40, 39]
    assert ids(fake.answers["sh_alerts_range"]) == [41, 40, 39, 38, 37, 36]
    assert fake.answers["sh_now"]["alerts_open"] == 3


@pytest.mark.parametrize("role", ["owner", "staff"])
def test_insiders_get_every_alert(role, fake, visit):
    client = visit(role)
    site = client.get("/api/site", params={"h": 168}).json()
    assert site["alerts_open"] == fake.answers["sh_alerts_open"]
    assert site["alerts_recent"] == fake.answers["sh_alerts_range"]
    fake.calls.clear()
    assert client.get("/api/site/now").json() == fake.answers["sh_now"]
    assert fake.names() == ["sh_now"]
    row, = client.get("/api/site/drill", params={"what": "alert", "id": 39}).json()["rows"]      # an "ops" alert
    assert row["kind"] == "ops" and [push["event"] for push in row["sent"]] == ["open"]
    row, = client.get("/api/site/drill", params={"what": "alert", "id": 38}).json()["rows"]
    assert [push["event"] for push in row["sent"]] == ["open", "close"] and len(row["fails"]) == 3


@pytest.mark.parametrize("role", ["vendor", "share"])
def test_outsiders_get_only_the_four_site_kinds(role, fake, visit):
    site = send(visit, role, "GET", "/api/site", params={"h": 168}).json()
    assert ids(site["alerts_open"]) == [41, 40]
    assert site["alerts_open"] == [row for row in fake.answers["sh_alerts_open"] if row["kind"] != "ops"]
    assert ids(site["alerts_recent"]) == [41, 40, 38, 37, 36]
    assert {row["kind"] for row in site["alerts_recent"]} == {"down", "slow", "silent", "cert"}
    assert server.SITE_ALERT_KINDS == {"down", "slow", "silent", "cert"}
    for key, fn in SITE_PARTS.items():                         # nothing else is touched
        if not key.startswith("alerts_"):
            assert site[key] == fake.answers[fn]

    now = send(visit, role, "GET", "/api/site/now").json()
    assert now == dict(fake.answers["sh_now"], alerts_open=2)   # recounted after filtering
    assert fake.names() == ["sh_now", "sh_alerts_open"]
    assert send(visit, role, "GET", "/api/site/drill", params={"what": "alert", "id": 39}).json() == {"rows": []}
    row, = send(visit, role, "GET", "/api/site/drill", params={"what": "alert", "id": 38}).json()["rows"]
    assert row == dict(fake.answered["sh_drill_alert"][0], sent=[])         # who was pushed is the owner's business
    assert row["id"] == 38 and len(row["fails"]) == 3 and len(fake.answered["sh_drill_alert"][0]["sent"]) == 2


def test_a_vendor_without_alerts_gets_none(fake, visit):
    client = visit("noalerts")
    site = client.get("/api/site", params={"h": 168}).json()
    assert site["alerts_open"] == [] and site["alerts_recent"] == []
    assert site["availability"] == fake.answers["sh_availability"]
    fake.calls.clear()
    assert client.get("/api/site/now").json() == dict(fake.answers["sh_now"], alerts_open=0)
    assert client.get("/api/site/drill", params={"what": "alert", "id": 41}).json() == {"rows": []}
    assert fake.names() == ["sh_now"]                          # the alerts were not even read

    fake.failing.add("sh_alerts_open")                         # a failed part must not leak through as an error
    assert client.get("/api/site").json()["alerts_open"] == []


@pytest.mark.parametrize("role", ["vendor", "noalerts"])
def test_outsiders_cannot_read_the_push_log_or_mark_alerts(role, fake, visit):
    client = visit(role)
    assert client.get("/api/messages").status_code == 403
    assert client.post("/api/alerts/ack", json={"ids": [41]}).status_code == 403
    assert client.post("/api/alerts/ack", json={"id": 41}).status_code == 403
    assert fake.calls == []


def test_a_failed_recount_is_an_error_not_a_zero(fake, visit):
    fake.failing.add("sh_alerts_open")
    response = visit("vendor").get("/api/site/now")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_alerts_open"})


# ---------------------------------------------------------------- the share link

def test_the_share_page_is_served_for_the_right_token_only(visit):
    client = visit(None)
    page = client.get("/status", params={"k": TOKEN})
    assert page.status_code == 200 and "set-cookie" not in page.headers
    assert injected(page.text) == (dict(OUTSIDER_SCREEN, shareKey=TOKEN), {"share": True})
    for k in ("wrong", TOKEN + "x", TOKEN[:-1], TOKEN.upper(), ""):
        refused = client.get("/status", params={"k": k})
        assert refused.status_code == 403 and server.TEXT_BAD_LINK in refused.text and "SH_CONFIG" not in refused.text
    assert client.get("/status").status_code == 403


def test_the_share_token_opens_the_three_data_calls_and_nothing_else(fake, visit):
    client = visit(None)
    for path in ("/api/site", "/api/site/now", "/api/site/drill"):
        assert client.get(path, params={"what": "fails", "k": TOKEN}).status_code == 200
        assert client.get(path, params={"what": "fails", "k": "wrong"}).status_code == 401
        assert client.get(path, params={"what": "fails"}).status_code == 401
    fake.calls.clear()
    assert client.get("/api/messages", params={"k": TOKEN}).status_code == 401
    assert client.post("/api/alerts/ack", params={"k": TOKEN}, json={"ids": [41]}).status_code == 401
    assert client.get("/site", params={"k": TOKEN}).headers["location"] == "/login"
    assert client.get("/", params={"k": TOKEN}).headers["location"] == "/login"
    assert client.get("/login", params={"k": TOKEN}).status_code == 200          # not "already signed in"
    assert fake.calls == []                                    # nothing was read for any of them
    assert sign_in(client, TOKEN).status_code == 401           # and the token is not a password
    assert client.cookies.get(server.COOKIE) is None


def test_on_a_share_call_only_the_token_counts(visit):
    owner = visit("owner")
    assert owner.get("/status", params={"k": "wrong"}).status_code == 403
    assert owner.get("/api/site", params={"k": "wrong"}).status_code == 401
    shared = owner.get("/api/site", params={"k": TOKEN, "h": 168}).json()
    assert ids(shared["alerts_open"]) == [41, 40]              # what the link shows, not what the owner may see
    assert ids(owner.get("/api/site", params={"h": 168}).json()["alerts_open"]) == [41, 40, 39]
    assert owner.get("/api/messages", params={"k": "wrong"}).status_code == 200   # k is not read elsewhere


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_an_empty_share_token_switches_the_link_off(configured, monkeypatch, visit):
    monkeypatch.delenv("SH_SHARE_TOKEN")
    if configured is not None:
        monkeypatch.setenv("SH_SHARE_TOKEN", configured)
    client = visit(None)
    for k in ("", "   ", "anything", TOKEN):
        assert client.get("/status", params={"k": k}).status_code == 403
        assert client.get("/api/site", params={"k": k}).status_code == 401
    assert client.get("/status").status_code == 403


@pytest.mark.parametrize("configured", ["x", "share-token-9f3a", "1234567890123456789"])
def test_a_share_token_shorter_than_20_characters_switches_the_link_off(configured, monkeypatch, caplog, visit):
    monkeypatch.setenv("SH_SHARE_TOKEN", configured)
    client = visit(None)
    assert client.get("/status", params={"k": configured}).status_code == 403
    assert client.get("/api/site", params={"k": configured}).status_code == 401
    assert startup_log(caplog) == [("WARNING", "SH_SHARE_TOKEN is shorter than 20 characters: the share link is "
                                               "switched off (OWNER-STEPS.md has the recipe for a good one)")]
    assert configured not in caplog.text or configured == "x"  # the warning does not repeat the token


def test_a_share_token_of_20_characters_is_enough(monkeypatch, caplog, visit):
    monkeypatch.setenv("SH_SHARE_TOKEN", " 12345678901234567890\n")           # as pasted: the spaces do not count
    assert visit(None).get("/status", params={"k": "12345678901234567890"}).status_code == 200
    assert startup_log(caplog) == []


def test_wrong_share_tokens_count_like_wrong_passwords(fake, clock, visit):
    client = visit(None)
    guesser, other = {"X-Forwarded-For": "198.51.100.7"}, {"X-Forwarded-For": "198.51.100.8"}
    for attempt in range(4):
        assert client.get("/status", params={"k": "guess-%d" % attempt}, headers=guesser).status_code == 403
        assert client.get("/api/site", params={"k": "another-guess-%d" % attempt}, headers=guesser).status_code == 401
    fake.calls.clear()
    page = client.get("/status", params={"k": TOKEN}, headers=guesser)      # the right token: it is not even looked at
    assert page.status_code == 429 and server.TEXT_BLOCKED in page.text and "SH_CONFIG" not in page.text and safe(page)
    data = client.get("/api/site/now", params={"k": TOKEN}, headers=guesser)
    assert (data.status_code, data.json()) == (429, {"error": "too many attempts"})
    assert data.headers["cache-control"] == "no-store" and fake.calls == []
    assert sign_in(client, PASSWORDS["owner"], **guesser).status_code == 429          # one limiter for both secrets
    assert client.get("/status", params={"k": TOKEN}, headers=other).status_code == 200
    assert visit("owner").get("/api/site", headers=guesser).status_code == 200        # a session is not an attempt
    clock.t += 599
    assert client.get("/status", params={"k": TOKEN}, headers=guesser).status_code == 429
    clock.t += 1
    assert client.get("/status", params={"k": TOKEN}, headers=guesser).status_code == 200


def test_wrong_passwords_close_the_share_link_to_that_address_too(clock, visit):
    client = visit(None)
    for attempt in range(8):
        assert sign_in(client, "guess %d" % attempt).status_code == 401
    assert client.get("/status", params={"k": TOKEN}).status_code == 429
    assert client.get("/status").status_code == 403            # nothing to judge: not an attempt, not a 429


def test_an_old_link_left_open_does_not_lock_its_address_out(clock, visit):
    client, old = visit(None), {"k": "the-token-of-last-month-0123"}
    for minute in range(30):                                   # the screen asks again every minute, with the old token
        clock.t += 60
        assert client.get("/api/site/now", params=old).status_code == 401
        assert client.get("/api/site", params=old).status_code == 401
        assert client.get("/status").status_code == 403        # and a page without any token is no attempt
    assert len(server._failures) == 1                          # one wrong value counts once in ten minutes
    assert old["k"] not in repr(server._failures)              # and only a digest of it is kept
    assert client.get("/status", params={"k": TOKEN}).status_code == 200
    assert sign_in(client, PASSWORDS["owner"]).status_code == 303


def test_secrets_are_compared_in_constant_time(monkeypatch, visit):
    seen, real = [], hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(server.hmac, "compare_digest", spy)
    client = visit(None)
    sign_in(client, "a guess")
    assert (b"a guess", b"owner pass-1") in seen and (b"a guess", b"agency-pass-03") in seen
    forged = "%d.%s" % (expiry(1), "0" * 64)
    client.get("/site", headers={"Cookie": "%s=%s" % (server.COOKIE, forged)})
    assert (forged.encode(), server._token("owner pass-1", expiry(1)).encode()) in seen
    client.get("/status", params={"k": "a-guess"})
    client.get("/api/site", params={"k": "b-guess"})
    assert (b"a-guess", TOKEN.encode()) in seen and (b"b-guess", TOKEN.encode()) in seen

    # and nothing else decides: with that comparison answering "no", no secret opens anything
    owner = visit("owner")
    monkeypatch.setattr(server.hmac, "compare_digest", lambda a, b: False)
    assert sign_in(visit(None), PASSWORDS["owner"]).status_code == 401
    assert owner.get("/site").headers["location"] == "/login"
    assert owner.get("/api/site").status_code == 401
    assert owner.get("/status", params={"k": TOKEN}).status_code == 403
    assert owner.get("/api/site", params={"k": TOKEN}).status_code == 401


# ================================================================ sign-in and the session cookie

@pytest.mark.parametrize("role, max_age", [("owner", 365), ("staff", 365), ("vendor", 30), ("noalerts", 30)])
def test_the_cookie_attributes(role, max_age, visit):
    response = sign_in(visit(None), PASSWORDS[role])
    assert (response.status_code, response.headers["location"]) == (303, "/")
    value, attributes = cookie_of(response)
    assert re.fullmatch(r"%d\.[0-9a-f]{64}" % expiry(max_age), value)      # "<when it ends>.<HMAC>"
    assert attributes == {"httponly", "samesite=lax", "path=/", "max-age=%d" % (max_age * 86400)}    # http: no "secure"


def test_the_cookie_is_secure_on_https_only(visit):
    def attributes(client, **headers):
        return cookie_of(sign_in(client, PASSWORDS["owner"], **headers))[1]

    assert "secure" not in attributes(visit(None))
    assert "secure" in attributes(visit(None, base_url="https://testserver"))
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https"})            # behind the host's proxy
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https, http"})
    assert "secure" not in attributes(visit(None, base_url="https://testserver"), **{"X-Forwarded-Proto": "http"})


def test_a_session_ends_on_the_server_when_its_time_is_up(monkeypatch, visit):
    owner, vendor = visit("owner"), visit("vendor")

    def after(days, seconds=0):
        monkeypatch.setattr(server, "_now", lambda: NOW + timedelta(days=days, seconds=seconds))

    after(30, -1)
    assert vendor.get("/site").status_code == 200 and vendor.get("/api/site").status_code == 200
    after(30)                                                  # 30 days: over, whatever the browser still sends
    assert vendor.get("/site").headers["location"] == "/login" and vendor.get("/api/site").status_code == 401
    assert vendor.get("/login").status_code == 200             # not "already signed in"
    after(365, -1)
    assert owner.get("/site").status_code == 200 and owner.get("/api/messages").status_code == 200
    after(365)
    assert owner.get("/site").headers["location"] == "/login" and owner.get("/api/messages").status_code == 401
    assert sign_in(owner, PASSWORDS["owner"]).status_code == 303 and owner.get("/site").status_code == 200


def test_the_end_of_a_session_cannot_be_moved(visit):
    value = visit("vendor").cookies[server.COOKIE]
    when, mac = value.split(".")

    def opens(cookie):
        return visit(None).get("/site", headers={"Cookie": "%s=%s" % (server.COOKIE, cookie)}).status_code == 200

    assert opens(value)
    for forged in ("%d.%s" % (int(when) + 86400 * 365, mac), "%d.%s" % (int(when) + 1, mac), "0%s.%s" % (when, mac),
                   mac, "." + mac, when + ".", when, "9" * 13 + "." + mac, "-1." + mac, when + "." + mac + "0",
                   when + "." + mac.upper(), when + "x." + mac, "%s.%s.%s" % (when, when, mac)):
        assert not opens(forged), forged
    for odd in ("١٢٣." + mac, "１２３." + mac, "1e9." + mac, " " + value):
        assert server._by_cookie(types.SimpleNamespace(cookies={server.COOKIE: odd})) is None, odd
    owner = visit("owner").cookies[server.COOKIE]              # the same moment, another person: another signature
    assert owner.split(".")[0] != when and not opens(when + "." + owner.split(".")[1])


def test_changing_a_password_ends_the_session(monkeypatch, visit):
    owner, vendor = visit("owner"), visit("vendor")
    old = owner.cookies[server.COOKIE]
    assert owner.get("/site").status_code == 200 and vendor.get("/site").status_code == 200

    monkeypatch.setenv("SH_PASS_OWNER", "a new password")
    assert owner.get("/site").headers["location"] == "/login"
    assert owner.get("/api/site").status_code == 401
    assert sign_in(visit(None), PASSWORDS["owner"]).status_code == 401
    new = cookie_of(sign_in(visit(None), "a new password"))[0]
    assert new != old and new == server._token("a new password", expiry(365))

    monkeypatch.delenv("SH_PASS_VENDOR_AGENCY")                # deleting it signs the person out at once
    assert vendor.get("/site").headers["location"] == "/login"
    assert vendor.get("/api/site").status_code == 401


@pytest.mark.parametrize("typed", ["Owner Pass-1", "owner pass-1", "OWNER PASS-1", "  Owner Pass-1 ",
                                   "\tOWNER pass-1\n"])
def test_passwords_match_trimmed_and_without_case(typed, monkeypatch, visit):
    monkeypatch.setenv("SH_PASS_OWNER", "  Owner Pass-1  ")
    response = sign_in(visit(None), typed)
    assert response.status_code == 303
    assert cookie_of(response)[0] == server._token("owner pass-1", expiry(365))      # one cookie however it was typed


@pytest.mark.parametrize("typed", ["", " ", "Owner Pass-1x", "OwnerPass-1", "Owner  Pass-1", "staff", TOKEN])
def test_a_wrong_password_is_refused(typed, visit):
    response = sign_in(visit(None), typed)
    assert response.status_code == 401 and server.TEXT_WRONG in response.text
    assert "set-cookie" not in response.headers


def test_unset_and_blank_passwords_never_match(monkeypatch, visit):
    monkeypatch.delenv("SH_PASS_STAFF")
    monkeypatch.setenv("SH_PASS_VENDOR_AGENCY", "   ")
    monkeypatch.setenv("SH_PASS_VENDOR_", "no-name")           # a variable without a name is nobody
    assert [viewer.who for _, viewer in server._accounts()] == ["DEVELOPER", "owner"]
    for typed in ("", "   ", "None", "no-name"):
        assert sign_in(visit(None), typed).status_code == 401
    for forged in (server._token("", expiry(1)), ""):          # the digest an empty key would give; an empty cookie
        response = visit(None).get("/site", headers={"Cookie": "%s=%s" % (server.COOKIE, forged)})
        assert response.headers["location"] == "/login"


def test_without_an_owner_password_nobody_signs_in(monkeypatch, visit):
    staff = visit("staff")
    monkeypatch.delenv("SH_PASS_OWNER")
    assert server._accounts() == []
    assert staff.get("/site").headers["location"] == "/login"
    for role in ("staff", "vendor", "noalerts"):
        assert sign_in(visit(None), PASSWORDS[role]).status_code == 401


@pytest.mark.parametrize("env, typed, who, role, max_age", [
    ({"SH_PASS_VENDOR_AGENCY": " OWNER pass-1 "}, "Owner Pass-1", "AGENCY", "vendor", 30),
    ({"SH_PASS_STAFF": "owner PASS-1"}, "Owner Pass-1", "staff", "staff", 365),
    ({"SH_PASS_VENDOR_AGENCY": "staff-pass-02", "SH_PASS_OWNER": "STAFF-PASS-02"}, "staff-pass-02", "AGENCY", "vendor", 30),
    # DEVELOPER is the one without alerts: it wins over a vendor with alerts, whatever the alphabet says
    ({"SH_PASS_VENDOR_AGENCY": "developer-pass-04"}, "developer-pass-04", "DEVELOPER", "vendor", 30),
    ({"SH_PASS_VENDOR_A_FIRST": "developer-pass-04"}, "developer-pass-04", "DEVELOPER", "vendor", 30),
])
def test_a_shared_password_resolves_to_the_least_privileged(env, typed, who, role, max_age, monkeypatch, fake, visit):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client = visit(None)
    response = sign_in(client, typed)
    assert "max-age=%d" % (max_age * 86400) in cookie_of(response)[1]
    assert fake.params("sh_login_log_add")["p_who"] == who     # the log and the cookie name the same person
    assert server._by_cookie(types.SimpleNamespace(cookies=client.cookies)).who == who
    assert client.get("/api/messages").status_code == (200 if role == "staff" else 403)
    if who == "DEVELOPER":
        assert injected(client.get("/site").text)[1] == {"readonly": True, "noAlerts": True}


def startup_log(caplog):
    """What the server says when it starts, as (level, message)."""
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"), TestClient(server.app):
        pass
    return [(record.levelname, record.getMessage()) for record in caplog.records]


def test_a_sound_configuration_is_started_without_a_word(caplog):
    assert startup_log(caplog) == []


def test_a_shared_password_is_reported_at_startup(monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_AGENCY", PASSWORDS["owner"].upper())
    assert startup_log(caplog) == [
        ("WARNING", "AGENCY and owner have the same password: both sign in as AGENCY (vendor)")]


def test_a_short_password_is_reported_at_startup(monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_STAFF", "short-one")
    monkeypatch.setenv("SH_PASS_VENDOR_AGENCY", "  elevenchars  ")             # 11 once trimmed
    assert startup_log(caplog) == [
        ("WARNING", "the password of AGENCY is shorter than 12 characters: use a generated one of 16 or more"),
        ("WARNING", "the password of staff is shorter than 12 characters: use a generated one of 16 or more")]
    assert "short-one" not in caplog.text and "elevenchars" not in caplog.text


def test_without_an_owner_password_the_start_says_so(monkeypatch, caplog):
    monkeypatch.delenv("SH_PASS_OWNER")
    assert startup_log(caplog) == [("WARNING", "SH_PASS_OWNER is not set: nobody can sign in")]


@pytest.mark.parametrize("name", ["CHECK", "CHECK_QUIET", "check"])
def test_the_password_of_a_deployment_check_is_reported_at_startup(name, monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_" + name, "a-throwaway-password-0123")
    assert startup_log(caplog) == [("WARNING", "SH_PASS_VENDOR_%s is set: it is the throwaway password of a "
                                               "deployment check; delete it when the check is done" % name)]
    assert sign_in(TestClient(server.app, follow_redirects=False), "a-throwaway-password-0123").status_code == 303


def test_a_vendor_whose_name_only_begins_like_a_check_is_not_reported(monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_CHECKOUT_TEAM", "a-lasting-password-0123")
    assert startup_log(caplog) == []


BOTH = ["AGENCY", "DEVELOPER"]


@pytest.mark.parametrize("setting, quiet", [
    ("developer", ["DEVELOPER"]), (" Developer ,", ["DEVELOPER"]), ("DEVELOPER,agency", BOTH), ("", []), (" , ", []),
    # a name that matches no vendor: a typing mistake must not show anybody the alerts, so nobody gets them
    ("developr", BOTH), ("developer.", BOTH), ("developer,someone-else", BOTH), ("agency;developer", BOTH),
    ("SH_PASS_VENDOR_DEVELOPER", BOTH), ("owner", BOTH),
])
def test_who_gets_no_alerts(setting, quiet, monkeypatch):
    monkeypatch.setenv("SH_VENDOR_NOALERTS", setting)
    assert sorted(viewer.who for _, viewer in server._accounts() if viewer.no_alerts) == quiet


@pytest.mark.parametrize("spelled", ["web agency 2", "Web-Agency-2", "WEB_AGENCY_2", "  web  agency-2 ", "web_agency 2"])
def test_vendor_names_are_compared_without_case_spaces_and_hyphens(spelled, monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_WEB_AGENCY_2", "web-agency-pass-05")
    monkeypatch.setenv("SH_VENDOR_NOALERTS", spelled)
    vendors = {viewer.who: viewer.no_alerts for _, viewer in server._accounts() if viewer.role == "vendor"}
    assert vendors == {"AGENCY": False, "DEVELOPER": False, "WEB_AGENCY_2": True}
    assert startup_log(caplog) == []


def test_a_name_without_a_vendor_hides_the_alerts_from_every_vendor(monkeypatch, caplog, fake, visit):
    monkeypatch.setenv("SH_VENDOR_NOALERTS", "developer, web agency")
    client = visit("vendor")                                   # AGENCY, who is not on the list
    site = client.get("/api/site", params={"h": 168}).json()
    assert site["alerts_open"] == [] and site["alerts_recent"] == []
    assert client.get("/api/site/now").json()["alerts_open"] == 0
    assert injected(client.get("/site").text)[1] == {"readonly": True, "noAlerts": True}
    assert ids(visit("owner").get("/api/site", params={"h": 168}).json()["alerts_open"]) == [41, 40, 39]
    assert ids(send(visit, "share", "GET", "/api/site", params={"h": 168}).json()["alerts_open"]) == [41, 40]
    assert startup_log(caplog) == [
        ("ERROR", "SH_VENDOR_NOALERTS names web agency, and no SH_PASS_VENDOR_<NAME> variable has that name: "
                  "until this is corrected NO vendor sees alerts")]


def test_every_attempt_is_logged(fake, visit):
    client = visit(None)
    # the right-most entry is the one the host's proxy added; what stands left of it came from the client
    headers = {"X-Forwarded-For": "10.0.0.1, 203.0.113.9", "User-Agent": "Phone/1.0 " + "x" * 300}
    sign_in(client, "a guess", **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": False, "p_who": "?",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(client, PASSWORDS["vendor"], **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": True, "p_who": "AGENCY",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(visit(None), PASSWORDS["owner"])                   # the test client's peer is the text "testclient"
    assert fake.params("sh_login_log_add") == {"p_ip": "?", "p_ok": True, "p_who": "owner", "p_ua": "testclient"}


@pytest.mark.parametrize("hops, forwarded, address", [
    (None, "198.51.100.7", "198.51.100.7"),
    (None, "6.6.6.6, 198.51.100.7", "198.51.100.7"),           # one proxy (the default): the last entry is its own
    (None, " 6.6.6.6 ,, 198.51.100.7 , ", "198.51.100.7"),
    ("1", "6.6.6.6, 7.7.7.7, 198.51.100.7", "198.51.100.7"),
    ("2", "6.6.6.6, 198.51.100.7, 172.70.1.1", "198.51.100.7"),          # two proxies: the last but one
    ("2", "198.51.100.7", "198.51.100.7"),                     # fewer entries than proxies: the oldest there is
    ("0", "6.6.6.6, 198.51.100.7", "?"),                       # no proxy: the header is the client's word, not used
    ("", "6.6.6.6, 198.51.100.7", "198.51.100.7"), ("many", "6.6.6.6, 198.51.100.7", "198.51.100.7"),
    ("-1", "6.6.6.6, 198.51.100.7", "198.51.100.7"),           # not a count: the default
    (None, "", "?"), (None, None, "?"),
    # the entry must be an address; anything else is not believed, and the socket peer is used. The peer
    # of the test client is the text "testclient", no address either: "?", never the text
    (None, "6.6.6.6, not-an-address", "?"), (None, "198.51.100.7.evil", "?"),
    (None, "9.9.9.9, " + "B" * 6000 + "<script>alert(1)</script>", "?"),
    (None, "203.0.113.9:4711", "203.0.113.9"), (None, "[2001:DB8::1]:443", "2001:db8::1"),      # some hosts add the port
    (None, "2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),                           # one spelling per address
    (None, "::ffff:203.0.113.9", "203.0.113.9"), (None, "fe80::1%eth0", "fe80::1"),
])
def test_the_client_address_is_the_entry_the_host_added(hops, forwarded, address, monkeypatch, fake, visit):
    if hops is not None:
        monkeypatch.setenv("SH_PROXY_HOPS", hops)
    sign_in(visit(None), "a guess", **({} if forwarded is None else {"X-Forwarded-For": forwarded}))
    assert fake.params("sh_login_log_add")["p_ip"] == address


def test_a_forged_forwarded_address_does_not_dodge_the_limit(fake, visit):
    client = visit(None)
    for attempt in range(8):                                   # a new made-up address on every guess
        forged = {"X-Forwarded-For": "6.6.6.%d, 198.51.100.7" % attempt}
        assert sign_in(client, "guess %d" % attempt, **forged).status_code == 401
    assert sign_in(client, PASSWORDS["owner"], **{"X-Forwarded-For": "9.9.9.9, 198.51.100.7"}).status_code == 429
    assert sign_in(visit(None), PASSWORDS["owner"], **{"X-Forwarded-For": "198.51.100.7, 198.51.100.8"}).status_code == 303


def test_the_address_in_the_login_log_is_never_longer_than_45_characters():
    def request(peer, forwarded=""):
        return types.SimpleNamespace(headers={"x-forwarded-for": forwarded}, client=types.SimpleNamespace(host=peer))

    assert server._client_ip(request("unix-socket-" + "x" * 100)) == "?"          # a peer that is no address
    assert server._client_ip(request("10.0.0.1", "y" * 5000)) == "10.0.0.1"
    # what uvicorn makes of a request from 127.0.0.1: the peer is the header's last entry, whatever it holds
    garbage = "B" * 6000 + "<script>alert(1)</script>"
    assert server._client_ip(request(garbage, "9.9.9.9, " + garbage)) == "?"
    assert server._client_ip(request("", "")) == "?" and server._client_ip(request(None, "")) == "?"
    longest = "0123:4567:89ab:cdef:0123:4567:89ab:cdef"
    assert server._client_ip(request("10.0.0.1", longest)) == "123:4567:89ab:cdef:123:4567:89ab:cdef"
    assert server._client_ip(types.SimpleNamespace(headers={}, client=None)) == "?"


def test_the_addresses_of_one_ipv6_network_count_as_one(fake, visit):
    client = visit(None)
    for attempt in range(8):                                   # one customer's /64: as many addresses as he likes
        forged = {"X-Forwarded-For": "2001:db8:1:2::%x" % (attempt + 1)}
        assert sign_in(client, "guess %d" % attempt, **forged).status_code == 401
    assert sign_in(client, PASSWORDS["owner"], **{"X-Forwarded-For": "2001:db8:1:2:ffff::9"}).status_code == 429
    logged = [params["p_ip"] for fn, params in fake.calls if fn == "sh_login_log_add"]
    assert logged[:3] == ["2001:db8:1:2::1", "2001:db8:1:2::2", "2001:db8:1:2::3"]      # the log keeps the address itself
    assert sign_in(visit(None), PASSWORDS["owner"], **{"X-Forwarded-For": "2001:db8:1:3::1"}).status_code == 303
    assert server._counted_as("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert server._counted_as("198.51.100.7") == "198.51.100.7" and server._counted_as("?") == "?"


def test_signing_in_works_while_the_database_is_down(fake, visit):
    fake.failing.update(["sh_login_log_add", "sh_config"])
    client = visit(None)
    assert client.get("/login").status_code == 200
    assert sign_in(client, "a guess").status_code == 401
    assert sign_in(client, PASSWORDS["owner"]).status_code == 303
    assert client.get("/").headers["location"] == "/site"


def test_eight_failures_block_an_address_for_ten_minutes(fake, clock, visit):
    client = visit(None)
    attacker, other = {"X-Forwarded-For": "198.51.100.7"}, {"X-Forwarded-For": "198.51.100.8"}
    for attempt in range(8):
        clock.t += 60                                          # 8 failures spread over 8 minutes
        assert sign_in(client, "guess %d" % attempt, **attacker).status_code == 401
    assert fake.names().count("sh_login_log_add") == 8
    fake.calls.clear()

    blocked = sign_in(client, PASSWORDS["owner"], **attacker)  # even the right password
    assert blocked.status_code == 429 and server.TEXT_BLOCKED in blocked.text and "set-cookie" not in blocked.headers
    assert "sh_login_log_add" not in fake.names()              # not examined, so not an attempt
    assert sign_in(visit(None), PASSWORDS["owner"], **other).status_code == 303          # another address is free

    clock.t += 179                                             # 9:59 after the first failure
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 429
    clock.t += 1                                               # the first failure is 10 minutes old
    assert sign_in(client, "one more guess", **attacker).status_code == 401
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 429            # 8 again within the window
    clock.t += 600
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 303


def test_the_login_page(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen={"siteLabel": 'shop"><script>alert(1)</script>.co.il'})
    page = visit(None).get("/login")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "no-cache, must-revalidate"
    text = page.text
    assert '<html lang="he" dir="rtl">' in text and 'name="viewport"' in text and "prefers-color-scheme:dark" in text
    assert '<form class="card" method="post" action="/login">' in text
    assert '<input name="p" type="password"' in text and '<button type="submit">כניסה</button>' in text
    assert '<div class="err" role="alert"></div>' in text
    assert "shop&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;.co.il" in text and Scripts(text).found == []
    assert not re.search(r"https?:|//|src=|<link|@import|url\(", text)          # nothing is fetched from anywhere

    wrong = sign_in(visit(None), "a guess")
    assert '<div class="err" role="alert">%s</div>' % server.TEXT_WRONG in wrong.text
    assert visit("vendor").get("/login").headers["location"] == "/"


def test_a_password_in_another_alphabet(monkeypatch, visit):
    monkeypatch.setenv("SH_PASS_VENDOR_AGENCY", "סיסמה חזקה")
    assert sign_in(visit(None), " סיסמה חזקה").status_code == 303
    assert sign_in(visit(None), "סיסמה חלשה").status_code == 401


def test_the_sign_in_form_is_open_to_a_signed_in_vendor(visit):
    client = visit("vendor")                                   # it is how a person changes identity
    assert client.get("/api/messages").status_code == 403
    assert sign_in(client, PASSWORDS["owner"]).status_code == 303
    assert client.get("/api/messages").status_code == 200


def test_logout_removes_the_cookie(visit):
    client = visit("owner")
    response = client.get("/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/login")
    value, attributes = cookie_of(response)
    assert value in ("", '""') and "max-age=0" in attributes
    assert client.get("/site").headers["location"] == "/login"


# ================================================================ the time window (spec §5.1)

def window_of(fake):
    params = fake.params("sh_availability")
    return params["p_from"], params["p_to"]


def at(text):
    return datetime.fromisoformat(text)


@pytest.mark.parametrize("query, hours", [
    ({}, 24), ({"h": ""}, 24), ({"h": "abc"}, 24), ({"h": "2.5"}, 24), ({"h": "24"}, 24), ({"h": "168"}, 168),
    ({"h": "2160"}, 2160), ({"h": "0"}, 1), ({"h": "-7"}, 1), ({"h": "9600"}, 9600), ({"h": "9601"}, 9600),
    ({"h": "99999999999"}, 9600), ({"h": "48", "t": "2026-11-01"}, 48),                    # t without f means nothing
    ({"h": "48", "f": "2026-13-45", "t": "2026-11-12"}, 48), ({"h": "48", "f": "yesterday"}, 48),
    ({"h": "48", "f": "2026-11-10", "t": "2026-02-30"}, 48), ({"f": "2026-11-31"}, 24),    # invalid dates: back to h
])
def test_a_window_of_hours(query, hours, fake, visit):
    answer = visit("owner").get("/api/site", params=query).json()
    p_from, p_to = window_of(fake)
    assert at(p_from) == NOW - timedelta(hours=hours) and at(p_to) == NOW + timedelta(minutes=1)
    assert p_to == "2026-11-13T10:16:30+02:00"                 # written in the site's zone
    assert (answer["from"], answer["to"], answer["hours"]) == (p_from, p_to, hours)


@pytest.mark.parametrize("query, p_from, p_to, hours", [
    # t is inclusive: the window ends when day t ends
    ({"f": "2026-11-01", "t": "2026-11-03"}, "2026-11-01T00:00:00+02:00", "2026-11-04T00:00:00+02:00", 72),
    ({"f": "2026-11-12", "t": "2026-11-12", "h": "720"}, "2026-11-12T00:00:00+02:00", "2026-11-13T00:00:00+02:00", 24),
    ({"f": "2026-11-13", "t": "2026-11-20"}, "2026-11-13T00:00:00+02:00", "2026-11-21T00:00:00+02:00", 192),
    # without t: until now (not until now + 1 minute)
    ({"f": "2026-11-12"}, "2026-11-12T00:00:00+02:00", "2026-11-13T10:15:30+02:00", 34),
    ({"f": "2026-11-13", "t": ""}, "2026-11-13T00:00:00+02:00", "2026-11-13T10:15:30+02:00", 10),
    # an end that is not after the start: one day from the start
    ({"f": "2026-11-10", "t": "2026-11-05"}, "2026-11-10T00:00:00+02:00", "2026-11-11T00:00:00+02:00", 24),
    ({"f": "2026-11-10", "t": "2026-11-09"}, "2026-11-10T00:00:00+02:00", "2026-11-11T00:00:00+02:00", 24),
    ({"f": "2026-12-01"}, "2026-12-01T00:00:00+02:00", "2026-12-02T00:00:00+02:00", 24),
    # the clocks change (Israel 2026: forward on 27.3 at 02:00, back on 25.10 at 02:00): local days of 23 and 25 hours
    ({"f": "2026-03-27", "t": "2026-03-27"}, "2026-03-27T00:00:00+02:00", "2026-03-28T00:00:00+03:00", 23),
    ({"f": "2026-10-25", "t": "2026-10-25"}, "2026-10-25T00:00:00+03:00", "2026-10-26T00:00:00+02:00", 25),
    ({"f": "2026-03-26", "t": "2026-03-28"}, "2026-03-26T00:00:00+02:00", "2026-03-29T00:00:00+03:00", 71),
])
def test_a_window_of_dates(query, p_from, p_to, hours, fake, visit):
    answer = visit("owner").get("/api/site", params=query).json()
    assert window_of(fake) == (p_from, p_to)
    assert (answer["from"], answer["to"], answer["hours"]) == (p_from, p_to, hours)


@pytest.mark.parametrize("now, h, p_from, p_to", [
    # across the change the window is h real hours, so its local start moves by an hour
    ("2026-03-27T12:00:00+03:00", 24, "2026-03-26T11:00:00+02:00", "2026-03-27T12:01:00+03:00"),
    ("2026-10-25T12:00:00+02:00", 24, "2026-10-24T13:00:00+03:00", "2026-10-25T12:01:00+02:00"),
    ("2026-10-25T01:30:00+02:00", 1, "2026-10-25T01:30:00+03:00", "2026-10-25T01:31:00+02:00"),   # the repeated hour
])
def test_a_window_of_hours_across_a_clock_change(now, h, p_from, p_to, monkeypatch, fake, visit):
    monkeypatch.setattr(server, "_now", lambda: at(now).astimezone(timezone.utc))
    visit("owner").get("/api/site", params={"h": h})
    assert window_of(fake) == (p_from, p_to)
    assert at(p_to) - at(p_from) == timedelta(hours=h, minutes=1)


def test_the_window_uses_the_zone_of_the_configuration(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, time_zone="America/New_York")      # the US clocks go back on 1.11.2026
    visit("owner").get("/api/site", params={"f": "2026-11-01", "t": "2026-11-01"})
    assert window_of(fake) == ("2026-11-01T00:00:00-04:00", "2026-11-02T00:00:00-05:00")


def test_every_call_gets_the_same_window(fake, visit):
    client, span = visit("owner"), {"p_from": "2026-11-01T00:00:00+02:00", "p_to": "2026-11-04T00:00:00+02:00"}
    query = {"f": "2026-11-01", "t": "2026-11-03"}
    client.get("/api/site", params=query)
    for fn in ("sh_availability", "sh_availability_series", "sh_speed", "sh_alerts_range"):
        assert fake.params(fn) == span
    assert fake.params("sh_speed_series") == dict(span, p_strategy="mobile")
    for fn in ("sh_alerts_open", "sh_health", "sh_product_issues", "sh_cert"):
        assert fake.params(fn) is None
    client.get("/api/site/drill", params=dict(query, what="fails"))
    assert fake.params("sh_drill_fails") == dict(span, p_page=None, p_bucket=None)
    client.get("/api/site/drill", params=dict(query, what="runs", url="https://example.co.il/"))
    assert fake.params("sh_drill_runs") == dict(span, p_url="https://example.co.il/", p_strategy="mobile",
                                                p_bucket=None)
    client.get("/api/messages", params=query)
    assert fake.params("sh_messages") == span


# ================================================================ the data calls (spec §5.2 – §5.7)

def test_api_site_puts_the_parts_together(fake, visit):
    response = visit("owner").get("/api/site", params={"h": 168, "strategy": "desktop"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    expected = {"hours": 168, "from": "2026-11-06T10:15:30+02:00", "to": "2026-11-13T10:16:30+02:00",
                "strategy": "desktop"}
    expected.update({key: fake.answers[fn] for key, fn in SITE_PARTS.items()})
    assert response.json() == expected
    assert sorted(fake.names()) == sorted(["sh_config", *SITE_PARTS.values()])       # each function once
    assert fake.params("sh_speed_series")["p_strategy"] == "desktop"


@pytest.mark.parametrize("strategy", ["mobile", "", "tablet", "DESKTOP", None])
def test_any_strategy_but_desktop_is_mobile(strategy, fake, visit):
    answer = visit("owner").get("/api/site", params={} if strategy is None else {"strategy": strategy}).json()
    assert answer["strategy"] == "mobile" and fake.params("sh_speed_series")["p_strategy"] == "mobile"


@pytest.mark.parametrize("broken", SITE_PARTS)
def test_each_part_fails_alone(broken, fake, visit):
    fake.failing.add(SITE_PARTS[broken])
    response = visit("owner").get("/api/site")
    assert response.status_code == 200
    answer = response.json()
    assert answer[broken] == {"error": "boom: " + SITE_PARTS[broken]}
    for key, fn in SITE_PARTS.items():
        if key != broken:
            assert answer[key] == fake.answers[fn]


def test_a_part_fails_alone_whatever_the_failure(fake, monkeypatch, visit):
    def broken(fn, params=None):
        if fn == "sh_speed":
            raise ZeroDivisionError("not a DbError")
        return fake(fn, params)

    monkeypatch.setattr(db, "rpc", broken)
    answer = visit("owner").get("/api/site").json()
    # only a DbError's text is written for a viewer; of any other error the viewer gets the type alone
    assert answer["speed"] == {"error": "ZeroDivisionError"} and answer["availability"] == fake.answers["sh_availability"]

    fake.failing.update(SITE_PARTS.values())                   # everything down: still an answer, part by part
    response = visit("owner").get("/api/site")
    assert response.status_code == 200
    assert all(response.json()[key] == {"error": "boom: " + fn} for key, fn in SITE_PARTS.items() if key != "speed")


def test_an_empty_part_is_a_list_and_an_unchecked_certificate_is_null(fake, visit):
    for fn in SITE_PARTS.values():
        fake.answers[fn] = None
    answer = visit("owner").get("/api/site").json()
    assert all(answer[key] == [] for key in SITE_PARTS if key != "cert") and answer["cert"] is None


def test_the_parts_are_read_in_parallel(fake, visit):
    client = visit("owner")
    fake.barrier = threading.Barrier(len(SITE_PARTS), timeout=10)      # released only by nine simultaneous calls
    answer = client.get("/api/site").json()
    assert not fake.barrier.broken
    assert all(answer[key] == fake.answers[fn] for key, fn in SITE_PARTS.items())


def test_without_the_configuration_a_data_call_is_a_502(fake, visit):
    fake.failing.add("sh_config")
    for path in ("/api/site", "/api/site/drill?what=fails", "/api/messages"):
        response = visit("owner").get(path)
        assert (response.status_code, response.json()) == (502, {"error": "boom: sh_config"})
        assert response.headers["cache-control"] == "no-store"
    fake.failing.clear()
    for incomplete in (NOT_SET_UP, None, dict(CONFIG, time_zone="Mars/Olympus"), {"time_zone": "UTC", "host": "x.com"}):
        fake.answers["sh_config"] = incomplete
        response = visit("owner").get("/api/site")
        assert response.status_code == 502 and "sh_setup" in response.json()["error"]
        assert visit("owner").get("/site").status_code == 502


def test_api_now(fake, visit):
    client = visit("owner")
    response = client.get("/api/site/now")
    assert (response.status_code, response.json()) == (200, fake.answers["sh_now"])
    assert response.headers["cache-control"] == "no-store" and fake.calls == [("sh_now", None)]
    fake.failing.add("sh_now")
    response = client.get("/api/site/now")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_now"})
    assert response.headers["cache-control"] == "no-store"


def test_drill_passes_the_parameters_through(fake, visit):
    client = visit("owner")
    span = {"p_from": "2026-11-12T10:15:30+02:00", "p_to": "2026-11-13T10:16:30+02:00"}
    response = client.get("/api/site/drill", params={"what": "fails", "page": "סל", "bucket": "2026-11-13 09:00"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"rows": fake.answered["sh_drill_fails"]} and len(response.json()["rows"]) == 23
    assert fake.params("sh_drill_fails") == dict(span, p_page="סל", p_bucket="2026-11-13 09:00")

    response = client.get("/api/site/drill", params={"what": "bucket", "bucket": "2026-11-12"})
    assert response.json() == {"rows": fake.answered["sh_drill_bucket"]} and len(response.json()["rows"]) == 4
    assert fake.params("sh_drill_bucket") == {"p_bucket": "2026-11-12"}

    fake.calls.clear()
    query = {"what": "runs", "url": "https://example.co.il/cart/", "strategy": "desktop", "bucket": "2026-11-13 09:00"}
    response = client.get("/api/site/drill", params=query)
    assert response.json() == {"rows": fake.answered["sh_drill_runs"]} and response.json()["rows"][0]["ok"] is True
    assert fake.params("sh_drill_runs") == dict(span, p_url="https://example.co.il/cart/", p_strategy="desktop",
                                                p_bucket="2026-11-13 09:00")

    response = client.get("/api/site/drill", params={"what": "alert", "id": "41"})
    assert response.json() == {"rows": fake.answered["sh_drill_alert"]} and ids(response.json()["rows"]) == [41]
    assert fake.params("sh_drill_alert") == {"p_id": 41}


@pytest.mark.parametrize("query", [
    {"what": "alert"}, {"what": "alert", "id": ""}, {"what": "alert", "id": "abc"}, {"what": "alert", "id": "-41"},
    {"what": "alert", "id": "41;drop"}, {"what": "alert", "id": "4.1"}, {"what": "alert", "id": " 41"},
    {"what": "alert", "id": "٤١"}, {"what": "alert", "id": "9" * 19},                 # digits, but no id is that long
    {"what": "runs"}, {"what": "runs", "url": ""}, {"what": "runs", "strategy": "desktop", "bucket": "2026-11-13"},
    {"what": "runs", "url": "https://example.co.il/", "bucket": "13.11.2026"},
    {"what": "bucket"}, {"what": "bucket", "bucket": ""}, {"what": "bucket", "bucket": "yesterday"},
    {"what": "bucket", "bucket": "2026-11-13 09:30"}, {"what": "bucket", "bucket": "2026-11-13 9:00"},
    {"what": "bucket", "bucket": "2026-11-13T09:00"}, {"what": "bucket", "bucket": "2026-11-13 09:00:00"},
    {"what": "bucket", "bucket": "2026-11-13 24:00"}, {"what": "bucket", "bucket": "2026-13-01"},
    {"what": "bucket", "bucket": "2026-02-30"}, {"what": "bucket", "bucket": "2026-1-5"},
    {"what": "bucket", "bucket": " 2026-11-13"}, {"what": "bucket", "bucket": "2026-11-13\n"},
    {"what": "bucket", "bucket": "٢٠٢٦-١١-١٣"}, {"what": "bucket", "bucket": "0000-01-01"},
    {"what": "bucket", "bucket": "2026-11-13'; drop table sh_probe; --"},
    {"what": "fails", "bucket": "last hour"}, {"what": "fails", "page": "סל", "bucket": "2026-11-13 09"},
    # a page or an address with a control character: a NUL the database could not even take as a parameter
    {"what": "fails", "page": "\x00"}, {"what": "fails", "page": "סל\x00"}, {"what": "fails", "page": "סל\n"},
    {"what": "fails", "page": "\x7f", "bucket": "2026-11-13"},
    {"what": "runs", "url": "https://example.co.il/\x00"}, {"what": "runs", "url": "https://example.co.il/\t"},
])
def test_drill_with_a_missing_or_malformed_parameter_has_no_rows_and_asks_nothing(query, fake, visit):
    fake.failing.update(["sh_config", "sh_drill_fails", "sh_drill_bucket", "sh_drill_runs", "sh_drill_alert"])
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (200, {"rows": []}) and fake.calls == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("query, fn, p_bucket", [
    ({"what": "bucket", "bucket": "2026-11-13"}, "sh_drill_bucket", "2026-11-13"),
    ({"what": "bucket", "bucket": "2026-11-13 00:00"}, "sh_drill_bucket", "2026-11-13 00:00"),
    ({"what": "bucket", "bucket": "2024-02-29 23:00"}, "sh_drill_bucket", "2024-02-29 23:00"),
    ({"what": "fails", "bucket": "2026-11-13 09:00"}, "sh_drill_fails", "2026-11-13 09:00"),
    ({"what": "fails", "bucket": ""}, "sh_drill_fails", None),              # as the screen sends "no bucket"
    ({"what": "fails"}, "sh_drill_fails", None),
    ({"what": "runs", "url": "https://example.co.il/", "bucket": ""}, "sh_drill_runs", None),
    ({"what": "runs", "url": "https://example.co.il/", "bucket": "2026-11-13"}, "sh_drill_runs", "2026-11-13"),
])
def test_drill_passes_a_well_formed_bucket_on(query, fn, p_bucket, fake, visit):
    visit("owner").get("/api/site/drill", params=query)
    assert fake.params(fn)["p_bucket"] == p_bucket


def test_the_alert_drill_ignores_a_bucket(fake, visit):
    visit("owner").get("/api/site/drill", params={"what": "alert", "id": "41", "bucket": "nonsense"})
    assert fake.params("sh_drill_alert") == {"p_id": 41}


@pytest.mark.parametrize("query", [{}, {"what": ""}, {"what": "everything"}, {"what": "FAILS"}])
def test_drill_of_an_unknown_kind_is_a_400(query, fake, visit):
    fake.failing.add("sh_config")                              # decided before the database is asked
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (400, {"error": "what?"})
    assert response.headers["cache-control"] == "no-store" and fake.calls == []


@pytest.mark.parametrize("what, fn", [("fails", "sh_drill_fails"), ("bucket", "sh_drill_bucket"),
                                      ("runs", "sh_drill_runs"), ("alert", "sh_drill_alert")])
def test_drill_failure_and_empty_result(what, fn, fake, visit):
    client, query = visit("owner"), {"what": what, "id": 41, "url": "https://example.co.il/", "bucket": "2026-11-13"}
    fake.answers[fn] = None
    assert client.get("/api/site/drill", params=query).json() == {"rows": []}
    fake.failing.add(fn)
    response = client.get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (502, {"error": "boom: " + fn})


def test_messages(fake, visit):
    client = visit("staff")
    response = client.get("/api/messages", params={"h": 720})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"rows": fake.answers["sh_messages"]} and len(response.json()["rows"]) == 10
    assert fake.params("sh_messages") == {"p_from": "2026-10-14T11:15:30+03:00", "p_to": "2026-11-13T10:16:30+02:00"}
    fake.answers["sh_messages"] = None
    assert client.get("/api/messages").json() == {"rows": []}
    fake.failing.add("sh_messages")
    response = client.get("/api/messages")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_messages"})


@pytest.mark.parametrize("body, p_ids", [
    ({"ids": [41, 40]}, [41, 40]),
    ({"id": 41}, [41]),
    ({"ids": ["41", 40, "40", 41]}, [41, 40]),                 # the screen sends what it read from the page; no repeats
    ({"ids": [41], "id": 7}, [41]),
    ({"ids": ["x", -1, 0, 1.5, True, None, [3], {"id": 4}, " 5", "٦", 6]}, [6]),
    ({"ids": list(range(1, 201))}, list(range(1, 201))),
    ({"ids": list(range(1, 251))}, list(range(1, 201))),       # up to 200: the rest stay open and show again
    # an id fits a bigint; a larger one is no id (the database would answer with an error of its own)
    ({"ids": [2 ** 63, 10 ** 30, "9" * 19, "9" * 400, 2 ** 63 - 1, str(2 ** 63 - 2)]}, [2 ** 63 - 1, 2 ** 63 - 2]),
])
def test_ack_marks_the_listed_alerts(body, p_ids, fake, visit):
    response = visit("owner").post("/api/alerts/ack", json=body)
    assert (response.status_code, response.json()) == (200, {"ok": True, "n": len(p_ids)})
    assert response.headers["cache-control"] == "no-store"
    assert fake.calls == [("sh_alert_ack", {"p_ids": p_ids, "p_who": "owner"})]


@pytest.mark.parametrize("body", [b"", b"not json", b"[41]", b"41", b"null", b'"41"', b"{}", b'{"ids": []}',
                                  b'{"ids": "41"}', b'{"ids": ["x", 0, -3, true]}', b'{"id": "abc"}', b'{"id": null}',
                                  b'{"id": [41]}', b'{"ids": {"0": 41}}', b'{"ids": [99999999999999999999999999]}',
                                  b'{"id": 9223372036854775808}',
                                  b'{"ids": [41], "pad": "' + b"x" * 20000 + b'"}'])
def test_ack_refuses_a_bad_body(body, fake, visit):
    response = visit("owner").post("/api/alerts/ack", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, response.json()) == (400, {"error": "bad request"}) and fake.calls == []


@pytest.mark.parametrize("kind", ["text/plain", "text/plain;charset=UTF-8", "application/x-www-form-urlencoded",
                                  "multipart/form-data; boundary=x", "application/jsonp", "text/json", "", None])
def test_ack_takes_a_body_that_says_it_is_json(kind, fake, visit):
    # what a page of another site can make the owner's browser send without asking first
    headers = {} if kind is None else {"Content-Type": kind}
    response = visit("owner").post("/api/alerts/ack", content=b'{"ids": [41]}', headers=headers)
    assert (response.status_code, response.json()) == (400, {"error": "bad request"}) and fake.calls == []


@pytest.mark.parametrize("kind", ["application/json", "application/json; charset=utf-8", "Application/JSON ;x=1"])
def test_ack_takes_json_however_the_type_is_spelled(kind, fake, visit):
    response = visit("owner").post("/api/alerts/ack", content=b'{"ids": [41]}', headers={"Content-Type": kind})
    assert (response.status_code, response.json()) == (200, {"ok": True, "n": 1})


def test_ack_reports_who_and_how_many(fake, visit):
    visit("staff").post("/api/alerts/ack", json={"ids": [41]})
    assert fake.params("sh_alert_ack")["p_who"] == "staff"     # the label of the signed-in user
    fake.answers["sh_alert_ack"] = {"n": 1}                    # one of the two had closed meanwhile
    assert visit("owner").post("/api/alerts/ack", json={"ids": [41, 38]}).json() == {"ok": True, "n": 1}
    fake.failing.add("sh_alert_ack")
    response = visit("owner").post("/api/alerts/ack", json={"ids": [41]})
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_alert_ack"})


# ================================================================ the page

def test_the_marker_is_replaced_exactly_once(visit):
    source = SCREEN.read_text(encoding="utf-8")
    assert source.count(server.MARKER) == 1
    response = visit("owner").get("/site")
    assert response.status_code == 200 and response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    script = ('<script>window.SH_CONFIG={"siteLabel": "example.co.il", "brand": "", "homePage": "בית", '
              '"probeCount": 4, "coreCount": 5, "downAfter": 1, "liveHosts": ["live"], "pathLabels": '
              '[["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]], "bucketNote": "", "hide": [], '
              '"nav": [], "links": []};window.SH_ROLE={};</script>')
    assert response.text == source.replace(server.MARKER, script)          # the rest of the file is untouched
    assert response.text.count("window.SH_CONFIG=") == 1 and server.MARKER not in response.text


@pytest.mark.parametrize("role", ["owner", "staff", "vendor", "noalerts", "share"])
def test_the_page_carries_the_role_of_the_viewer(role, visit):
    path = "/status" if role == "share" else "/site"
    config, screen_role = injected(send(visit, role, "GET", path).text)
    assert screen_role == SCREEN_ROLE[role]
    assert config == (dict(OUTSIDER_SCREEN, shareKey=TOKEN) if role == "share" else
                      OUTSIDER_SCREEN if role in ("vendor", "noalerts") else SCREEN_CONFIG)


@pytest.mark.parametrize("role", ["owner", "staff", "vendor", "noalerts", "share"])
def test_the_owners_other_screens_never_reach_an_outsiders_page(role, fake, visit):
    """The screen hides the menu from an outsider, but hiding is not enough: the page source is theirs to read."""
    fake.answers["sh_config"] = dict(CONFIG, screen=dict(SCREEN_CONFIG, **MENU))
    page = send(visit, role, "GET", "/status" if role == "share" else "/site").text
    config, _ = injected(page)
    if role in ("owner", "staff"):
        assert (config["nav"], config["links"]) == (MENU["nav"], MENU["links"])
    else:
        assert "nav" not in config and "links" not in config
        assert "intranet.example.co.il" not in page and "sales-secret-dashboard" not in page and "דוחות" not in page
        assert {key: value for key, value in config.items() if key != "shareKey"} == OUTSIDER_SCREEN       # the rest is all there


HOSTILE = {"siteLabel": 'x</script><script>alert("1")</script>', "brand": "a'b\"c\\d</SCRIPT >",
           "bucketNote": "<!--<script>\u2028\u2029-->", "homePage": "בית & </",
           "nav": [["a", "/x", "]]>;window.SH_ROLE={};"]]}


# the owner's page carries the hostile menu entry too; a vendor's carries everything but the menu
HOSTILE_SEEN = {"owner": (HOSTILE, {}),
                "vendor": ({key: value for key, value in HOSTILE.items() if key != "nav"}, {"readonly": True})}


@pytest.mark.parametrize("role", HOSTILE_SEEN)
def test_a_hostile_configuration_value_cannot_leave_the_script(role, fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    plain = Scripts(SCREEN.read_text(encoding="utf-8")).found
    page = visit(role).get("/site").text
    scripts = Scripts(page).found
    assert len(scripts) == len(plain) + 1 and scripts[1:] == plain          # one script more, the screen's own intact
    assert not re.search("[<\u2028\u2029]", scripts[0])                     # nothing that can end or break the script
    assert injected(page) == HOSTILE_SEEN[role]                             # and the values arrive unchanged
    assert "<script>alert" not in page and page.count("</script>") == len(plain) + 1


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
@pytest.mark.parametrize("role", HOSTILE_SEEN)
def test_the_injected_script_is_javascript_that_yields_the_same_values(role, fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    script = Scripts(visit(role).get("/site").text).found[0]
    program = "var window = {};%s;process.stdout.write(JSON.stringify([window.SH_CONFIG, window.SH_ROLE]))" % script
    done = subprocess.run(["node", "-e", program], capture_output=True, encoding="utf-8", timeout=60, check=True)
    assert json.loads(done.stdout) == list(HOSTILE_SEEN[role])


def test_the_configuration_is_read_once_a_minute(fake, clock, visit):
    client = visit("owner")
    for _ in range(3):
        client.get("/site")
        client.get("/api/site")
    assert fake.names().count("sh_config") == 1
    clock.t += 59
    client.get("/site")
    assert fake.names().count("sh_config") == 1
    fake.answers["sh_config"] = dict(CONFIG, screen=dict(SCREEN_CONFIG, siteLabel="other.co.il"))
    clock.t += 1
    assert injected(client.get("/site").text)[0]["siteLabel"] == "other.co.il"
    assert fake.names().count("sh_config") == 2


def test_the_page_without_the_configuration_says_so(fake, visit):
    fake.failing.add("sh_config")
    for role, path in (("owner", "/site"), ("share", "/status")):
        response = send(visit, role, "GET", path)
        assert response.status_code == 502 and server.TEXT_NO_DATA in response.text and "boom" not in response.text
        assert safe(response)
    fake.failing.clear()                                       # a failure is not remembered
    assert visit("owner").get("/site").status_code == 200


def test_another_screen_file(monkeypatch, tmp_path, visit):
    screen = tmp_path / "screen.html"
    screen.write_text("<head><!--SH_INJECT--></head>ported screen", encoding="utf-8")
    monkeypatch.setenv("SH_SCREEN", str(screen))
    assert visit("owner").get("/site").text.endswith("window.SH_ROLE={};</script></head>ported screen")
    screen.write_text("<head></head>no marker", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SH_INJECT"):
        visit("owner").get("/site")                            # never a page that silently lost its role


def test_where_the_screen_file_is_looked_for(monkeypatch, tmp_path):
    backend = tmp_path / "site-health"
    backend.mkdir()
    monkeypatch.delenv("SH_SCREEN")
    monkeypatch.setattr(server, "HERE", str(backend))
    assert server._screen_state() == "missing"
    (tmp_path / "site_health.html").write_text("<head><!--SH_INJECT--></head>inside the kit", encoding="utf-8")
    assert server._screen_parts() == ("<head>", "</head>inside the kit")         # one folder up: reference/ in the kit
    (backend / "site_health.html").write_text("<head><!--SH_INJECT--></head>deployed", encoding="utf-8")
    assert server._screen_parts() == ("<head>", "</head>deployed")               # next to server.py: that one first
    named = tmp_path / "named.html"
    named.write_text("<!--SH_INJECT-->named", encoding="utf-8")
    monkeypatch.setenv("SH_SCREEN", str(named))
    assert server._screen_parts() == ("", "named")                               # SH_SCREEN before both
    assert server.HERE != str(REFERENCE) and os.path.samefile(server.__file__, REFERENCE / "server.py")


def test_a_changed_screen_file_is_served_without_a_restart(monkeypatch, tmp_path, visit):
    screen = tmp_path / "screen.html"
    monkeypatch.setenv("SH_SCREEN", str(screen))
    client = visit("owner")
    for version in ("first", "second version", "third"):
        screen.write_text("<!--SH_INJECT-->" + version, encoding="utf-8")
        assert client.get("/site").text.endswith("</script>" + version)


# ================================================================ real-user beacons (spec §7.7)

def beacon(client, body=BEACON, **headers):
    content = body if isinstance(body, (bytes, str)) else json.dumps(body)
    response = client.post("/m", content=content, headers={"Content-Type": "text/plain;charset=UTF-8", **headers})
    assert (response.status_code, response.content) == (204, b"")           # always, stored or not
    assert safe(response)


def stored(fake):
    return [row for fn, params in fake.calls if fn == "sh_rum_add" for row in params["p_rows"]]


def test_a_beacon_is_stored_without_anything_about_the_visitor(fake, visit):
    client = visit("vendor")                                   # even with a session cookie on the request
    body = dict(BEACON, path="/product/sofa/?utm_source=mail&email=someone@example.com#reviews", ua="x", ip="y",
                v=1, ttfb=180, nav="navigate")                 # what the script sends besides, and what it does not
    beacon(client, body, **ORIGIN, **{"X-Forwarded-For": "203.0.113.77", "User-Agent": "Mozilla/5.0 (secret-agent)",
                                      "Cookie": "customer_session=abc123",
                                      "Referer": "https://example.co.il/product/sofa/?token=t0k"})
    assert fake.calls == [("sh_config", None), ("sh_rum_add", {"p_rows": [
        {"site": "live", "path": "/product/sofa/", "lcp_ms": 2345, "is_test": False}]})]
    recorded = json.dumps(fake.calls)
    secrets = ("203.0.113.77", "secret-agent", "abc123", client.cookies[server.COOKIE], "utm", "someone", "t0k", "reviews")
    assert not [secret for secret in secrets if secret in recorded]


@pytest.mark.parametrize("headers, kept", [
    ({"Origin": "https://example.co.il"}, True),
    ({"Origin": "https://www.example.co.il"}, True),
    ({"Origin": "https://WWW.Example.co.il:8443"}, True),
    ({"Referer": "https://www.example.co.il/product/sofa/?a=1"}, True),       # no Origin: the Referer decides
    ({"Origin": "https://example.co.il", "Referer": "https://elsewhere.com/"}, True),
    ({}, True),                                                # a browser that names no source at all
    ({"Origin": "null"}, True),                                # a site with a strict referrer policy
    ({"Origin": "null", "Referer": "https://elsewhere.com/"}, True),
    ({"Origin": "https://staging.example.co.il"}, False),      # not one of this site's rum_hosts
    ({"Origin": "https://example.co.il.evil.com"}, False),
    ({"Origin": "https://evilexample.co.il"}, False),
    ({"Origin": "https://elsewhere.com", "Referer": "https://example.co.il/"}, False),
    ({"Referer": "https://elsewhere.com/?https://example.co.il/"}, False),
    ({"Origin": "example.co.il"}, False), ({"Origin": "https://[example.co.il"}, False),      # present, and no host in it
    ({"Referer": "null"}, False),                              # only an Origin says "null"
])
def test_a_beacon_that_names_its_source_must_name_the_site(headers, kept, fake, visit):
    beacon(visit(None), **headers)
    assert len(stored(fake)) == kept


def test_the_extra_hosts_of_the_configuration_may_send_beacons(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, rum_hosts=["staging.example.co.il", "www.dev.example.co.il"])
    client = visit(None)
    for source in ("https://staging.example.co.il", "https://www.staging.example.co.il:8443",
                   "https://dev.example.co.il", "https://example.co.il"):
        beacon(client, dict(BEACON, site="staging.example.co.il"), Origin=source)
        beacon(client, dict(BEACON, site="staging.example.co.il"), Referer=source + "/product/sofa/")
    assert len(stored(fake)) == 8
    beacon(client, Origin="https://test.example.co.il")
    beacon(client, Referer="https://staging.example.co.il.evil.com/")
    assert len(stored(fake)) == 8


def test_a_beacon_may_call_its_site_by_a_configured_name_only(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, rum_hosts=["staging.example.co.il"], live_hosts=["live", "shop"])
    client = visit(None)
    for name in ("live", "shop", "staging.example.co.il", "www.staging.example.co.il", "example.co.il"):
        beacon(client, dict(BEACON, site=name), **ORIGIN)
    assert [row["site"] for row in stored(fake)] == ["live", "shop", "staging.example.co.il",
                                                     "www.staging.example.co.il", "example.co.il"]
    for name in ("dev.example.co.il", "shop.example.co.il", "liv", "staging"):
        beacon(client, dict(BEACON, site=name), **ORIGIN)
    assert len(stored(fake)) == 5


def test_a_site_without_real_user_measurements_stores_no_beacon(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, off=["catalogue", "real_users"])
    beacon(visit(None), **ORIGIN)
    assert stored(fake) == []
    fake.answers["sh_config"] = {key: value for key, value in CONFIG.items() if key != "off"}      # an older database
    server._site_cache.update(site=None)
    beacon(visit(None), **ORIGIN)
    assert len(stored(fake)) == 1


def test_a_flood_of_made_up_site_names_stores_nothing(fake, visit):
    client = visit(None)
    for i in range(300):                                       # no Origin, another address and another name each time
        beacon(client, dict(BEACON, site="flood-%04d.attacker-chosen-text.example" % i),
               **{"X-Forwarded-For": "198.51.%d.%d" % (i // 250, i % 250)})
    assert stored(fake) == [] and "sh_rum_add" not in fake.names()


def test_the_configured_host_may_be_written_with_www(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, host="WWW.example.co.il")
    client = visit(None)
    beacon(client, **ORIGIN)
    beacon(client, Origin="https://www.example.co.il")
    assert len(stored(fake)) == 2


@pytest.mark.parametrize("change, row", [
    ({"path": "/"}, {"path": "/"}),
    ({"path": "/product/%D7%A1%D7%A4%D7%94/?x=1"}, {"path": "/product/%D7%A1%D7%A4%D7%94/"}),
    ({"path": "/cart/#top"}, {"path": "/cart/"}),
    ({"path": "/product/order-of-the-phoenix-poster/"}, {"path": "/product/order-of-the-phoenix-poster/"}),
    ({"lcp": 1}, {"lcp_ms": 1}), ({"lcp": 60000}, {"lcp_ms": 60000}), ({"lcp": 1234.6}, {"lcp_ms": 1235}),
    ({"test": True}, {"is_test": True}), ({"test": "yes"}, {"is_test": False}),
    ({"site": "example.co.il"}, {"site": "example.co.il"}),                              # the site's host by its name
    ({"site": "www.example.co.il"}, {"site": "www.example.co.il"}),
    ({"path": "/" + "x" * 119}, {"path": "/" + "x" * 119}),                              # 120 characters: whole
    ({"path": "/" + "x" * 299}, {"path": "/" + "x" * 119}),                              # longer: cut at 120
    ({"path": "/" + "x" * 299 + "?utm_source=" + "y" * 200}, {"path": "/" + "x" * 119}), # the query string does not count
    # a cut never ends inside an escape, nor inside a character whose escapes were cut off
    ({"path": "/" + "x" * 117 + "%D7%A1"}, {"path": "/" + "x" * 117}),                   # "%D" would be left: not kept
    ({"path": "/" + "x" * 118 + "%2F"}, {"path": "/" + "x" * 118}),                      # "%"
    ({"path": "/" + "x" * 116 + "%D7%A1%D7%A4"}, {"path": "/" + "x" * 116}),             # "%D7": half a Hebrew letter
    ({"path": "/" + "x" * 113 + "%E2%80%99abc"}, {"path": "/" + "x" * 113}),             # two thirds of a character
    ({"path": "/" + "x" * 110 + "%F0%9F%98%80" + "z" * 20}, {"path": "/" + "x" * 110}),  # three quarters of one
    ({"path": "/" + "x" * 113 + "%D7%A1zz"}, {"path": "/" + "x" * 113 + "%D7%A1"}),      # a whole one stays
    ({"path": "/product/" + "%D7%A1%D7%A4%D7%94-" * 10},                                 # a long Hebrew slug, as sent
     {"path": "/product/" + "%D7%A1%D7%A4%D7%94-" * 5 + "%D7%A1%D7%A4"}),
    # stored in the form a browser sends: never more bytes than characters
    ({"path": "/ספה/"}, {"path": "/%D7%A1%D7%A4%D7%94/"}), ({"path": "/a b/"}, {"path": "/a%20b/"}),
    ({"path": "/" + "ס" * 100 + "x" * 199}, {"path": "/" + "%D7%A1" * 19}),
    ({"path": "/" + "\U0001D400" * 50}, {"path": "/" + "%F0%9D%90%80" * 9}),            # 201 bytes: 109 characters
    ({"path": "/%D7%A7%D7%95%D7%A4%D7%94/"}, {"path": "/%D7%A7%D7%95%D7%A4%D7%94/"}),    # private only where configured
    ({"v": 1, "ttfb": 180, "nav": "navigate", "anything": {"else": [1]}}, {}),            # unknown fields are ignored
    # ordinary addresses that only look a little like an identifier
    ({"path": "/product/sofa-3-seater-grey-fabric-2024/"}, {"path": "/product/sofa-3-seater-grey-fabric-2024/"}),
    ({"path": "/blog/2026/11/13/how-to-choose-a-sofa/"}, {"path": "/blog/2026/11/13/how-to-choose-a-sofa/"}),
    ({"path": "/product/1234567890123/"}, {"path": "/product/1234567890123/"}),            # a barcode: 13 digits
    ({"path": "/p/abcdef1234/"}, {"path": "/p/abcdef1234/"}),                              # 10 hexadecimal characters
    ({"path": "/category/abcdefghijklmnopqrstuvwxyz/"}, {"path": "/category/abcdefghijklmnopqrstuvwxyz/"}),
    ({"path": "/product/%D7%A1%D7%A4%D7%94-%D7%AA%D7%9C%D7%AA-%D7%9E%D7%95%D7%A9%D7%91%D7%99%D7%AA-2024/"},
     {"path": "/product/%D7%A1%D7%A4%D7%94-%D7%AA%D7%9C%D7%AA-%D7%9E%D7%95%D7%A9%D7%91%D7%99%D7%AA-2024/"}),
])
def test_what_is_stored(change, row, fake, visit):
    beacon(visit(None), dict(BEACON, **change), **ORIGIN)
    assert stored(fake) == [dict({"site": "live", "path": "/product/sofa/", "lcp_ms": 2345, "is_test": False}, **row)]


@pytest.mark.parametrize("change", [
    {"path": "/my-account/"}, {"path": "/my-account/orders/"}, {"path": "/account/login"}, {"path": "/checkout/"},
    {"path": "/he/Checkout/"}, {"path": "/checkout/order-received/1234/?key=wc_order_abc"},
    {"path": "/checkouts/c/abc"},
    {"path": "/checkout/order-pay/77/"}, {"path": "/my-account/view-order/77/"}, {"path": "/12345/orders/abcdef"},
    {"path": "/wp-admin/index.php"}, {"path": "/admin"}, {"path": "/wp-login.php"},
    {"path": "/my-account/lost-password/"}, {"path": "/%63heckout/"}, {"path": "/shop/CHECKOUT%2Fpay"},
    {"path": "product/sofa/"}, {"path": "https://example.co.il/x"}, {"path": ""}, {"path": None}, {"path": 7},
    {"lcp": 0}, {"lcp": 0.4}, {"lcp": 60001}, {"lcp": -5}, {"lcp": "2345"}, {"lcp": None}, {"lcp": True}, {"lcp": [1]},
    {"site": ""}, {"site": None}, {"site": "Live Site"}, {"site": "a" * 101}, {"site": "live\n"}, {"site": ["live"]},
    # a name that the configuration does not know: it would be shown on the screen as the sender wrote it
    {"site": "staging.example.co.il"}, {"site": "a" * 100}, {"site": "your-site-is-hacked.example.com"},
    {"site": "example.co.il.attacker.example"}, {"site": "live.example.co.il"}, {"site": "wwwexample.co.il"},
    # a path that may name a person: an "@", or something that looks like a token
    {"path": "/unsubscribe/someone@example.com/"}, {"path": "/unsubscribe/someone%40example.com/token-abc123"},
    {"path": "/reset/5f2a9c1e7b3d4a6f/"},                                                # 16 hexadecimal characters
    {"path": "/track/order-5F2A9C1E7B3D4A6F8E0C/"}, {"path": "/o/1234567890123456/"},    # also after a hyphen; 16 digits
    {"path": "/r/550e8400-e29b-41d4-a716-446655440000/"},                                # a UUID
    {"path": "/t/aB3dE5gH7jK9mN1pQ3sT5vW7/"},                                            # 24 letters and digits
    {"path": "/t/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.abc/"},
    {"path": "/t/%61B3dE5gH7jK9mN1pQ3sT5vW7/"},                                          # the same, partly encoded
    # judged whole: what lies beyond the 120 characters that would be kept counts all the same
    {"path": "/" + "x" * 130 + "/someone@example.com/"}, {"path": "/" + "x" * 125 + "/checkout/"},
    {"path": "/" + "x" * 125 + "/5f2a9c1e7b3d4a6f/"},
    # a path the database could not store, or that is no address of a page
    {"path": "/batch/1\x00"}, {"path": "/a\nb/"}, {"path": "/a\x7fb/"}, {"path": "/a\x1fb/"}, {"path": "/a%00b/"},
    {"path": "/half/\ud83d/"},                                                          # half a surrogate pair
])
def test_what_is_dropped(change, fake, visit):
    beacon(visit(None), dict(BEACON, **change), **ORIGIN)
    assert stored(fake) == []


@pytest.mark.parametrize("path, kept", [
    ("/%D7%A7%D7%95%D7%A4%D7%94/", False),                     # /קופה/ as a browser sends it
    ("/קופה/", False), ("/he/%d7%a7%d7%95%d7%a4%d7%94/step-2", False),
    ("/My-Cart", False), ("/shop/my-cart/", False),
    ("/checkout/", False),                                     # the built-in names still count
    ("/קופה-חדשה/", True), ("/my-cart-guide/", True), ("/product/sofa/", True),
])
def test_the_private_paths_of_the_configuration_are_never_stored(path, kept, fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, private_paths=["קופה", "My-Cart"])
    beacon(visit(None), dict(BEACON, path=path), **ORIGIN)
    assert [row["path"] for row in stored(fake)] == [urllib.parse.quote(path)] * kept     # stored as a browser sends it


@pytest.mark.parametrize("body", [b"", b"not json", b"[1]", b"null", b'"x"', b'{"site":"live","path":"/","lcp":NaN}',
                                  b'{"site":"live","path":"/","lcp":1e999}', b"\xff\xfe", b"[" * 1024,
                                  b'{"a":' * 200 + b"1" + b"}" * 200])
def test_a_garbage_beacon_is_dropped(body, fake, visit):
    beacon(visit(None), body, **ORIGIN)
    assert stored(fake) == []


def test_a_beacon_larger_than_1_kb_is_dropped(fake, visit):
    def sized(size):
        body = json.dumps(dict(BEACON, pad=""))
        return body.replace('"pad": ""', '"pad": "%s"' % ("x" * (size - len(body))))

    client = visit(None)
    assert len(sized(1024)) == 1024 and len(sized(1025)) == 1025
    beacon(client, sized(1024), **ORIGIN)
    assert len(stored(fake)) == 1
    beacon(client, sized(1025), **ORIGIN)
    beacon(client, sized(500000), **ORIGIN)
    assert len(stored(fake)) == 1


def test_sixty_beacons_a_minute_per_address(fake, clock, visit):
    client, one, two = visit(None), {"X-Forwarded-For": "203.0.113.1"}, {"X-Forwarded-For": "203.0.113.2"}
    for _ in range(60):
        beacon(client, **ORIGIN, **one)
    assert len(stored(fake)) == 60
    beacon(client, **ORIGIN, **one)                            # the 61st: answered, not stored
    beacon(client, {"garbage": 1}, **ORIGIN, **two)            # a dropped beacon counts as well
    assert len(stored(fake)) == 60
    beacon(client, **ORIGIN, **two)                            # another address has its own count
    assert len(stored(fake)) == 61
    clock.t += 60                                              # the next minute
    beacon(client, **ORIGIN, **one)
    assert len(stored(fake)) == 62
    assert json.dumps(fake.calls).count("203.0.113") == 0


def test_the_beacons_of_one_ipv6_network_count_as_one_address(fake, visit):
    client = visit(None)
    for i in range(70):
        beacon(client, dict(BEACON, path="/p/%d/" % i), **ORIGIN, **{"X-Forwarded-For": "2001:db8:1:2::%x" % (i + 1)})
    assert len(stored(fake)) == 60


def flood(client, count, start=0):
    """`count` good beacons, each from another address, so only the overall budget can stop them."""
    for i in range(start, start + count):
        beacon(client, dict(BEACON, path="/p/%d/" % i), **ORIGIN,
               **{"X-Forwarded-For": "198.51.%d.%d" % (i // 250, i % 250)})


def test_all_addresses_together_store_300_rows_a_minute(fake, clock, visit):
    client = visit(None)
    flood(client, 320)
    assert len(stored(fake)) == 300 == server.RUM_PER_MINUTE   # the other 20 were answered 204 like the rest
    assert [row["path"] for row in stored(fake)][-1] == "/p/299/"
    clock.t += 60
    flood(client, 5, start=320)
    assert len(stored(fake)) == 305


def test_the_budget_counts_only_rows_that_would_be_stored(fake, clock, monkeypatch, visit):
    monkeypatch.setenv("SH_RUM_PER_MINUTE", "3")
    client = visit(None)
    for change in ({"lcp": 0}, {"site": "made-up.example"}, {"path": "/checkout/"}, {"path": "/r/5f2a9c1e7b3d4a6f/"}):
        beacon(client, dict(BEACON, **change), **ORIGIN)
    flood(client, 5)
    assert [row["path"] for row in stored(fake)] == ["/p/0/", "/p/1/", "/p/2/"]


@pytest.mark.parametrize("setting", ["", "many", "-5", "3.5"])
def test_a_budget_that_is_not_a_number_is_the_default(setting, fake, clock, monkeypatch, visit):
    monkeypatch.setenv("SH_RUM_PER_MINUTE", setting)
    flood(visit(None), 301)
    assert len(stored(fake)) == 300


def test_all_addresses_together_store_a_fixed_number_of_rows_a_day(fake, clock, monkeypatch, caplog, visit):
    monkeypatch.setenv("SH_RUM_PER_MINUTE", "4")
    monkeypatch.setenv("SH_RUM_PER_DAY", "10")
    client, kept = visit(None), []
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        for minute in range(5):
            flood(client, 6, start=minute * 6)
            kept.append(len(stored(fake)))
            clock.t += 60
    assert kept == [4, 8, 10, 10, 10]
    said = [record.getMessage() for record in caplog.records]
    assert said == ["real-user measurements: the 10 rows of SH_RUM_PER_DAY are used up; further ones are dropped "
                    "for up to 24 hours"]                      # once, not once per beacon
    clock.t += 86400
    flood(client, 6, start=100)
    assert len(stored(fake)) == 14
    assert server.RUM_PER_DAY == 20000 and "SH_RUM_PER_DAY" not in ENV       # the default, when nothing is set


def test_beacons_are_answered_while_the_database_is_down(fake, visit):
    client = visit(None)
    fake.failing.add("sh_rum_add")
    beacon(client, **ORIGIN)
    assert fake.names() == ["sh_config", "sh_rum_add"] and server._rum_queue == [] and server._rum_busy is False
    fake.failing.add("sh_config")
    server._site_cache.update(site=None)
    beacon(client, **ORIGIN)                                   # the site's host is unknown: dropped
    assert fake.names() == ["sh_config", "sh_rum_add", "sh_config"]


def test_waiting_rows_go_out_in_small_batches(fake, visit):
    client = visit(None)
    waiting = [{"site": "live", "path": "/p/%d/" % i, "lcp_ms": 2000, "is_test": False} for i in range(120)]
    server._rum_queue.extend(waiting)                        # what piles up while the database is slow
    beacon(client, **ORIGIN)
    sizes = [len(params["p_rows"]) for fn, params in fake.calls if fn == "sh_rum_add"]
    assert sizes == [50, 50, 21] and stored(fake)[:120] == waiting and server._rum_queue == []

    server._rum_queue.extend(waiting * 9)                    # 1,080 waiting: over the limit, the newcomer is dropped
    fake.calls.clear()
    beacon(client, dict(BEACON, path="/newcomer/"), **ORIGIN)
    assert len(stored(fake)) == 1080 and all(row["path"] != "/newcomer/" for row in stored(fake))


def test_a_row_the_database_refuses_does_not_cost_the_rows_of_its_batch(fake, caplog, visit):
    honest = [{"site": "live", "path": "/p/%d/" % i, "lcp_ms": 2000, "is_test": False} for i in range(60)]
    bad = dict(honest[0], path="/refused/")
    server._rum_queue.extend(honest[:20] + [bad] + honest[20:])        # the bad row sits in the first batch of 50
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        beacon(visit(None), **ORIGIN)
    batches = [params["p_rows"] for fn, params in fake.calls if fn == "sh_rum_add"]
    accepted = [row for batch in batches if bad not in batch for row in batch]
    assert accepted == honest[:20] + honest[20:49] + honest[49:] + [dict(honest[0], path="/product/sofa/", lcp_ms=2345)]
    assert [len(batch) for batch in batches] == [50] + [1] * 50 + [12]       # the batch again, row by row, in order
    assert [record.getMessage() for record in caplog.records] == [
        "real-user rows lost: 1 (unsupported Unicode escape sequence)"]


def test_a_batch_is_not_sent_row_by_row_when_the_database_is_down(fake, visit):
    server._rum_queue.extend({"site": "live", "path": "/p/%d/" % i, "lcp_ms": 2000, "is_test": False} for i in range(49))
    fake.failing.add("sh_rum_add")                           # a DbError that is not about the data
    beacon(visit(None), **ORIGIN)
    assert fake.names().count("sh_rum_add") == 1 and server._rum_queue == []


# ================================================================ /health (spec §7.10) and start-up

def test_health(fake):
    client = TestClient(server.app)                            # no session
    for flow in fake.answers["sh_health"]:
        flow["last_at"] = (NOW - timedelta(hours=3)).isoformat()
    fake.answers["sh_health"][0].update(flow_name=server.PROBE_FLOW, last_at="2026-11-13T10:14:48.5+02:00")   # 41.5 s
    response = client.get("/health")
    assert (response.status_code, response.json()) == (
        200, {"ok": True, "db": "ok", "screen": "ok", "last_probe_age_sec": 41})
    assert response.headers["cache-control"] == "no-store" and safe(response)
    assert fake.names() == ["sh_ping", "sh_health"]

    fake.answers["sh_health"][0]["last_at"] = None             # installed, the prober has not run yet
    assert client.get("/health").json() == {"ok": True, "db": "ok", "screen": "ok", "last_probe_age_sec": None}
    fake.answers["sh_health"] = None
    assert client.get("/health").json() == {"ok": True, "db": "ok", "screen": "ok", "last_probe_age_sec": None}


def test_health_stays_200_when_the_database_is_down(fake, monkeypatch):
    client = TestClient(server.app)
    fake.failing.add("sh_ping")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "boom: sh_ping", "screen": "ok", "last_probe_age_sec": None}
    fake.failing = {"sh_health"}
    assert client.get("/health").json() == {"ok": False, "db": "boom: sh_health", "screen": "ok",
                                            "last_probe_age_sec": None}

    def crash(fn, params=None):
        raise RuntimeError("Invalid header value b'sb_secret_REALKEY'")

    monkeypatch.setattr(db, "rpc", crash)                      # whatever goes wrong: its type, never its text
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "RuntimeError", "screen": "ok", "last_probe_age_sec": None}
    assert "REALKEY" not in response.text


def test_health_and_the_start_report_a_screen_file_that_cannot_be_served(fake, monkeypatch, tmp_path, caplog):
    screen = tmp_path / "site_health.html"
    monkeypatch.setenv("SH_SCREEN", str(screen))
    client = TestClient(server.app)

    def health():
        answer = client.get("/health")
        assert answer.status_code == 200 and str(tmp_path) not in answer.text      # the route is public: no path
        return answer.json()["ok"], answer.json()["db"], answer.json()["screen"]

    assert health() == (False, "ok", "missing")                # the host shipped the backend without the screen
    screen.write_text("<html>a page without the marker</html>", encoding="utf-8")
    assert health() == (False, "ok", "no marker")
    screen.write_bytes(b"\xff\xfe<!--SH_INJECT-->")
    assert health() == (False, "ok", "not UTF-8")
    assert startup_log(caplog) == [("ERROR", "the screen file is not usable (not UTF-8: %s): /site cannot be served. "
                                             "Copy site_health.html next to server.py, or name it in SH_SCREEN" % screen)]
    screen.write_text("<html><!--SH_INJECT--></html>", encoding="utf-8")
    assert health() == (True, "ok", "ok")
    fake.failing.add("sh_ping")
    assert health() == (False, "boom: sh_ping", "ok")


def collectors_module(monkeypatch, start):
    module = types.ModuleType("collectors")
    module.start = start
    monkeypatch.setitem(sys.modules, "collectors", module)


@pytest.mark.parametrize("setting, started", [(None, 1), ("1", 1), ("0", 0)])
def test_the_collectors_start_with_the_server(setting, started, monkeypatch):
    starts = []
    collectors_module(monkeypatch, lambda: starts.append(1))
    monkeypatch.delenv("COLLECTORS")
    if setting is not None:
        monkeypatch.setenv("COLLECTORS", setting)
    assert starts == []                                        # importing the server starts nothing
    with TestClient(server.app) as client:
        assert client.get("/health").status_code == 200
    assert len(starts) == started


@pytest.mark.parametrize("problem", ["missing", "broken"])
def test_the_server_comes_up_without_working_collectors(problem, monkeypatch, caplog):
    def start():
        raise OSError("no network")

    collectors_module(monkeypatch, start)
    if problem == "missing":
        monkeypatch.setitem(sys.modules, "collectors", None)   # "import collectors" now fails: no such module
    monkeypatch.setenv("COLLECTORS", "1")
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"), TestClient(server.app) as client:
        assert client.get("/login").status_code == 200
    message, = [record.getMessage() for record in caplog.records]
    assert message.startswith("collectors: NOT started")
    assert ("no network" if problem == "broken" else "collectors") in message


# ================================================================ db.py

class Supabase(BaseHTTPRequestHandler):
    """A stand-in for Supabase's REST interface: answers POST /rest/v1/rpc/<fn> and keeps the requests."""
    seen = []
    answers = {
        "sh_ping": (200, b'"ok"'),
        "sh_login_log_add": (204, b""),                        # a function that returns nothing
        "sh_missing": (404, b'{"code": "PGRST202", "details": "searched in the schema", "hint": null, '
                            b'"message": "Could not find the function public.sh_missing in the schema cache"}'),
        "sh_gateway": (502, b"<html>bad gateway</html>"),
        "sh_html": (200, b"<html>not json</html>"),
        "sh_bad_data": (400, b'{"code": "22P05", "details": null, "hint": null, '
                             b'"message": "unsupported Unicode escape sequence"}'),
        "sh_conflict": (409, b'{"code": "23505", "message": "duplicate key value violates unique constraint"}'),
    }
    redirects = {"sh_moved": 301, "sh_found": 302, "sh_see_other": 303, "sh_temporary": 307, "sh_permanent": 308}
    elsewhere = ""                                             # where those functions redirect to

    def log_message(self, *args):
        pass

    def do_GET(self):                                          # what a followed redirect of a POST turns into
        self.seen.append((self.path, {name.lower(): value for name, value in self.headers.items()}, None))
        self.send_response(200)
        self.send_header("Content-Length", "4")
        self.end_headers()
        self.wfile.write(b'"ok"')

    def do_POST(self):
        params = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, {name.lower(): value for name, value in self.headers.items()}, params))
        fn = self.path.rsplit("/", 1)[-1]
        status, body = self.answers.get(fn, (200, json.dumps({"got": params}).encode()))
        if fn in self.redirects:
            status, body = self.redirects[fn], b""
        self.send_response(status)
        if fn in self.redirects:
            self.send_header("Location", self.elsewhere)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def supabase(monkeypatch):
    """SUPABASE_URL + SUPABASE_SECRET_KEY pointing at the stand-in; yields the requests it received."""
    Supabase.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Supabase)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:%d/" % httpd.server_address[1])
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_for_tests")
    monkeypatch.setenv("DATABASE_URL", "postgresql://not-used.invalid/x")     # the Supabase pair comes first
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setitem(sys.modules, "psycopg", None)          # importing the driver on this path would now fail
    yield Supabase.seen
    httpd.shutdown()
    httpd.server_close()


def test_db_over_https(supabase):
    assert REAL_RPC("sh_ping") == "ok"
    params = {"p_from": "2026-11-12T00:00:00+02:00", "p_page": None, "p_ok": True, "p_rows": [{"path": "/סל/"}]}
    assert REAL_RPC("sh_anything", params) == {"got": params}
    assert REAL_RPC("sh_login_log_add", {"p_who": "owner"}) is None
    path, headers, sent = supabase[1]
    assert (path, sent) == ("/rest/v1/rpc/sh_anything", params) and supabase[0][2] == {}
    assert (headers["apikey"], headers["authorization"]) == ("sb_secret_for_tests", "Bearer sb_secret_for_tests")
    assert headers["content-type"] == "application/json"


@pytest.mark.parametrize("fn, message", [
    ("sh_missing", "HTTP 404: Could not find the function public.sh_missing in the schema cache"),  # PostgREST's words
    ("sh_gateway", "HTTP 502: Bad Gateway"),
    ("sh_html", "the database API did not answer with JSON"),
])
def test_db_over_https_reports_failures(fn, message, supabase):
    with pytest.raises(db.DbError) as error:
        REAL_RPC(fn)
    assert str(error.value) == message


def test_db_says_whether_the_database_refused_the_data(supabase):
    refusals = {}
    for fn in ("sh_bad_data", "sh_conflict", "sh_missing", "sh_gateway", "sh_html", "sh_Not_A_Name"):
        with pytest.raises(db.DbError) as error:
            REAL_RPC(fn)
        refusals[fn] = error.value.answered
    # only an SQL error about the data of the call itself; not a missing function, a gateway, a refusal of this file
    assert refusals == {"sh_bad_data": True, "sh_conflict": True, "sh_missing": False, "sh_gateway": False,
                        "sh_html": False, "sh_Not_A_Name": False}
    assert db.DbError("anything").answered is False


def test_a_key_pasted_with_spaces_and_a_newline_works(supabase, monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "  sb_secret_for_tests\n")
    monkeypatch.setenv("SUPABASE_URL", " %s \n" % os.environ["SUPABASE_URL"])
    assert REAL_RPC("sh_ping") == "ok"
    assert supabase[0][0] == "/rest/v1/rpc/sh_ping" and supabase[0][1]["apikey"] == "sb_secret_for_tests"


@pytest.mark.parametrize("key", ["sb_secret_REAL\nKEY_abcdef123456", "sb_secret_REAL\rKEY", "sb_secret_REALKEY_\u05d0"])
def test_a_key_that_cannot_be_sent_is_never_quoted(key, supabase, monkeypatch, caplog, fake):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", key)
    with caplog.at_level(logging.DEBUG), pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "the database address or key is malformed" and supabase == []
    monkeypatch.setattr(db, "rpc", REAL_RPC)                   # and through the server, on its public route
    health = TestClient(server.app).get("/health")
    assert health.json()["db"] == "the database address or key is malformed"
    assert "REAL" not in health.text and "REAL" not in caplog.text


@pytest.mark.parametrize("url", ["secretref.supabase.co", "http://secretref.supabase.co", "//secretref.supabase.co",
                                 "ftp://secretref.supabase.co", "http://127.0.0.1.attacker.example:8000",
                                 "http://localhost.attacker.example", "http://localhost@attacker.example"])
def test_the_key_is_sent_over_https_only(url, supabase, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", url)
    with pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "SUPABASE_URL must start with https://" and supabase == []
    assert db._LOCAL_HTTP.fullmatch("http://localhost:54321") and db._LOCAL_HTTP.fullmatch("http://127.0.0.1")


@pytest.mark.parametrize("fn, status", Supabase.redirects.items())
def test_a_redirect_is_never_followed(fn, status, supabase, monkeypatch):
    other = ThreadingHTTPServer(("127.0.0.1", 0), Supabase)    # where the key must not arrive
    threading.Thread(target=other.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    monkeypatch.setattr(Supabase, "elsewhere", "http://localhost:%d/elsewhere" % other.server_address[1])
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    try:
        with pytest.raises(db.DbError) as error:
            REAL_RPC(fn)
    finally:
        other.shutdown()
        other.server_close()
    assert str(error.value) == "HTTP %d: the database address answers with a redirect; check SUPABASE_URL" % status
    assert [path for path, _, _ in supabase] == ["/rest/v1/rpc/" + fn]       # one request: the first


@pytest.mark.parametrize("dsn", ["postgresql://postgres:My%Secret Pw@127.0.0.1:9/postgres",
                                 '"postgresql://postgres:Secr3tPw99@127.0.0.1:9/postgres"'])
def test_a_connection_string_that_cannot_be_read_is_never_quoted(dsn, monkeypatch, caplog, fake):
    pytest.importorskip("psycopg")
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setattr(db, "_thread", threading.local())
    with caplog.at_level(logging.DEBUG), pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "database call failed (ProgrammingError): check DATABASE_URL"
    monkeypatch.setattr(db, "rpc", REAL_RPC)                   # and through the server: /health, and a part of /api/site
    health = TestClient(server.app).get("/health")
    assert health.json()["db"] == "database call failed (ProgrammingError): check DATABASE_URL"
    for secret in ("ecret", "Secr3t", "Pw", "postgres:"):
        assert secret not in health.text and secret not in caplog.text and secret not in str(error.value)


def test_db_over_https_when_nothing_answers(supabase, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")   # nothing listens there
    with pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "database unreachable (ConnectionRefusedError)"       # no address, no key
    assert supabase == []


@pytest.mark.parametrize("fn, params", [
    ("sh_ping; drop table sh_alerts", None), ("sh_ping\n", None), ("sh_Ping", None), ("pg_sleep", None), ("sh_", None),
    ("sh_x/../../auth/v1/admin/users", None), ("", None),
    ("sh_alert_ack", {"p_ids) or (true": [1]}), ("sh_alert_ack", {"ids": [1]}), ("sh_alert_ack", {"p_ids\n": [1]}),
])
def test_db_refuses_names_that_are_not_sh_functions_and_p_parameters(fn, params, supabase):
    with pytest.raises(db.DbError, match="bad function or parameter name"):
        REAL_RPC(fn, params)
    assert supabase == []                                      # refused before anything is sent


def test_db_without_configuration(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "no database configured: set SUPABASE_URL and SUPABASE_SECRET_KEY, or DATABASE_URL"
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")        # half a pair is not a configuration
    with pytest.raises(db.DbError, match="no database configured"):
        REAL_RPC("sh_ping")


def test_db_over_a_postgres_connection(request, monkeypatch, caplog):
    try:
        url = request.getfixturevalue("database")              # conftest.py: a scratch database with the kit's SQL
    except (Exception, pytest.exit.Exception) as e:            # this file alone needs no Postgres: skip, do not stop
        pytest.skip("no scratch Postgres database: %s" % e)
    import psycopg

    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", " %s\n" % url)          # as pasted into a host's settings
    monkeypatch.setattr(db, "_thread", threading.local())
    try:
        assert REAL_RPC("sh_ping") == "ok"
        conn = db._thread.conn
        assert conn.autocommit and conn.prepare_threshold is None          # what a transaction pooler needs
        config = json.loads((REFERENCE / "site_health.config.example.json").read_text(encoding="utf-8"))
        assert REAL_RPC("sh_setup", {"p_config": config})["time_zone"] == "Asia/Jerusalem"       # a dict goes as jsonb
        assert REAL_RPC("sh_config")["screen"]["homePage"] == "בית"
        span = {"p_from": "2026-11-12T00:00:00+02:00", "p_to": "2026-11-13T00:00:00+02:00"}      # times as text
        assert REAL_RPC("sh_drill_fails", dict(span, p_page=None, p_bucket=None)) == []
        assert REAL_RPC("sh_alert_ack", {"p_ids": [1, 2], "p_who": "owner"}) == {"n": 0}          # a list goes as jsonb
        assert db._thread.conn is conn                                     # one connection, kept

        with pytest.raises(db.DbError, match="does not exist") as error:
            REAL_RPC("sh_no_such_function")
        assert error.value.answered is False                               # no call would get further
        assert REAL_RPC("sh_ping") == "ok" and db._thread.conn is conn     # an SQL error does not cost the connection
        with pytest.raises(db.DbError) as error:                           # a NUL: the database refuses this data
            REAL_RPC("sh_rum_add", {"p_rows": [{"site": "live", "path": "/a\x00", "lcp_ms": 5, "is_test": False}]})
        assert error.value.answered is True and "\x00" not in str(error.value)
        with caplog.at_level(logging.DEBUG), pytest.raises(db.DbError) as error:      # a NUL in a plain parameter:
            REAL_RPC("sh_drill_fails", dict(span, p_page="סל\x00", p_bucket=None))     # the driver refuses to send it
        assert str(error.value) == ("database call failed (DataError): the call carried a value the database cannot "
                                    "store") and error.value.answered is True
        assert "DATABASE_URL" not in str(error.value) and "DATABASE_URL" not in caplog.text       # not the address's fault
        assert REAL_RPC("sh_ping") == "ok" and db._thread.conn is conn     # nor the connection's

        class Dropped:                                                     # a kept connection the server has closed
            closed = False

            def execute(self, sql, values):
                self.closed = True
                raise psycopg.OperationalError("server closed the connection unexpectedly")

        db._thread.conn = Dropped()
        assert REAL_RPC("sh_ping") == "ok" and isinstance(db._thread.conn, psycopg.Connection)   # reconnected, once

        seen = []
        worker = threading.Thread(target=lambda: seen.append((REAL_RPC("sh_ping"), db._thread.conn)))
        worker.start()
        worker.join()
        assert seen[0][0] == "ok" and seen[0][1] is not db._thread.conn    # a connection per thread
        seen[0][1].close()

        monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@127.0.0.1:9/nothing")
        db._thread.conn.close()
        with pytest.raises(db.DbError) as error:
            REAL_RPC("sh_ping")
        assert str(error.value) == "database unreachable"                  # the host and the user stay in the log
    finally:
        if getattr(db._thread, "conn", None) is not None:
            db._thread.conn.close()


# ================================================================ the access log (spec §8.2)

def child_env(**changes):
    """The environment for a child process: this machine's own (not the cleaned one of the tests), without
    any setting of a real installation, plus `changes`."""
    env = {name: value for name, value in OUTER_ENV.items()
           if not name.startswith(("SH_", "SUPABASE_", "DATABASE_")) or name in ("SH_TEST_ADMIN_URL", "SH_KIT_DIR")}
    env.update(NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    env.update(changes)
    return env


def status_of(url):
    """The status of one GET, without following a redirect and without this machine's proxy."""
    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None

    try:
        with urllib.request.build_opener(Stay(), urllib.request.ProxyHandler({})).open(url, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code


def test_the_access_log_never_holds_a_query_string():
    access, records = logging.getLogger("uvicorn.access"), []
    handler = logging.Handler()
    handler.emit = records.append
    level = access.level
    access.addHandler(handler)
    access.setLevel(logging.INFO)
    try:                                                       # the records as uvicorn makes them
        access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.9:4711", "GET", "/status?k=" + TOKEN, "1.1", 200)
        access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.9:4711", "GET", "/api/site/now?h=24&k=%s&x=?" % TOKEN, "1.1", 200)
        access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.9:4711", "GET", "/site", "1.1", 303)
        # "/status%3Fk=..." is the path "/status?k=..." to the router, and uvicorn prints it encoded again
        access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.9:4711", "GET", "/status%3Fk%3D" + TOKEN, "1.1", 303)
        access.info('%s - "%s %s HTTP/%s" %d', "203.0.113.9:4711", "GET", "/status%3fk%3d" + TOKEN, "1.1", 303)
    finally:
        access.removeHandler(handler)
        access.setLevel(level)
    assert [record.getMessage() for record in records] == [
        '203.0.113.9:4711 - "GET /status HTTP/1.1" 200', '203.0.113.9:4711 - "GET /api/site/now HTTP/1.1" 200',
        '203.0.113.9:4711 - "GET /site HTTP/1.1" 303', '203.0.113.9:4711 - "GET /status HTTP/1.1" 303',
        '203.0.113.9:4711 - "GET /status HTTP/1.1" 303']
    assert len([f for f in access.filters if isinstance(f, server._NoQueryStrings)]) == 1
    with TestClient(server.app):                               # starting the server does not add it twice
        pass
    assert len([f for f in access.filters if isinstance(f, server._NoQueryStrings)]) == 1


def test_the_plain_start_command_keeps_the_share_token_out_of_the_log(tmp_path):
    """The real server program, started the way the README says, with its access log on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base, log_file = "http://127.0.0.1:%d" % port, tmp_path / "server.log"
    env = child_env(**{name: value for name, value in ENV.items() if name != "SH_VENDOR_NOALERTS"})
    with open(log_file, "wb") as out:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
                                    "--port", str(port)], cwd=REFERENCE, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            deadline = time.time() + 30
            while True:
                try:
                    assert status_of(base + "/health") == 200
                    break
                except OSError:
                    assert process.poll() is None and time.time() < deadline, "the server did not start"
                    time.sleep(0.1)
            seen = [status_of(base + path) for path in (
                "/status?k=" + TOKEN, "/api/site/now?h=24&k=" + TOKEN, "/site?k=" + TOKEN, "/status?k=wrong-" + TOKEN,
                "/status%3Fk=" + TOKEN, "/status%3fk%3d" + TOKEN)]          # an encoded "?": no route, and no token in the log
        finally:
            process.terminate()
            process.wait(30)
    log = log_file.read_text(encoding="utf-8", errors="replace")
    assert seen == [502, 502, 303, 403, 303, 303]              # no database here: the right token gets as far as that
    assert '"GET /status HTTP/1.1" 502' in log and '"GET /api/site/now HTTP/1.1" 502' in log     # the log is on,
    assert '"GET /site HTTP/1.1" 303' in log and '"GET /status HTTP/1.1" 403' in log
    assert TOKEN not in log and "k=" not in log                                                  # without the token
    assert not [line for line in log.splitlines() if '"GET ' in line and "?" in line]            # or any query string
    for secret in PASSWORDS.values():
        assert secret not in log


# ================================================================ tools/check_access.py

CHECK_ENV = {"SH_PASS_VENDOR_CHECK": PASSWORDS["vendor"], "SH_PASS_VENDOR_CHECK_QUIET": PASSWORDS["noalerts"],
             "SH_SHARE_TOKEN": TOKEN, "SH_PASS_OWNER": PASSWORDS["owner"]}


@contextlib.contextmanager
def serving(**options):
    """The reference server on a real socket, inside this process: its database is the fake of these tests.
    Yields its address. `options`: settings of uvicorn.Config."""
    import uvicorn

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    running = uvicorn.Server(uvicorn.Config(server.app, log_config=None, access_log=False, lifespan="off", **options))
    thread = threading.Thread(target=running.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 30
        while not running.started:
            assert time.time() < deadline and thread.is_alive(), "the server did not start"
            time.sleep(0.01)
        yield "http://127.0.0.1:%d" % listener.getsockname()[1]
    finally:
        running.should_exit = True
        thread.join(30)
        listener.close()


@pytest.fixture
def live(fake):
    # proxy_headers off: for a client on 127.0.0.1 uvicorn would otherwise take the client's address from
    # X-Forwarded-For by itself, and "no proxy in front" could not be told from "one proxy in front"
    with serving(proxy_headers=False) as address:
        yield address


def test_an_entry_that_uvicorn_believes_is_never_stored_as_an_address(fake):
    """uvicorn's default start believes X-Forwarded-For from 127.0.0.1 (a proxy on the same machine): the
    peer the server sees is then the header's last entry, whatever it holds. The login log gets "?"."""
    garbage = "B" * 6000 + "<script>alert(1)</script>"
    with serving() as base:
        request = urllib.request.Request(base + "/login", data=b"p=a-guess", headers={
            "X-Forwarded-For": "9.9.9.9, " + garbage, "Content-Type": "application/x-www-form-urlencoded"})
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=20)
    assert refused.value.code == 401
    assert [params["p_ip"] for fn, params in fake.calls if fn == "sh_login_log_add"] == ["?"]


def check_access(base, *flags, **env):
    done = subprocess.run([sys.executable, str(CHECK_ACCESS), base, *flags], env=child_env(**env), capture_output=True,
                          encoding="utf-8", timeout=120)
    return done.returncode, done.stdout + done.stderr


def failures(output):
    return [line[6:] for line in output.splitlines() if line.startswith("FAIL  ")]


def replace_route(path, handler, monkeypatch):
    """Swap the handler of one GET route for a broken copy, for the length of a test."""
    routes = server.app.router.routes
    monkeypatch.setattr(server.app.router, "routes", [route for route in routes if getattr(route, "path", "") != path])
    server.app.add_api_route(path, handler, methods=["GET"])


def test_check_access_passes_against_the_reference_server(live, fake):
    assert fake.answer("sh_drill_alert", {"p_id": 41})[0]["sent"]          # there is something to hide
    fake.answers["sh_config"] = dict(CONFIG, screen=dict(SCREEN_CONFIG, **MENU))      # and a menu of other screens
    code, output = check_access(live, **CHECK_ENV)
    assert code == 0, output
    assert failures(output) == [] and re.search(r"\n\d\d passed, 0 failed\n", output)
    for line in ("ok    nobody: GET /health answers 200 with ok, db and last_probe_age_sec",
                 "ok    nobody: POST /m answers 204 with an empty body (not a beacon)",
                 "ok    nobody: GET /api/messages answers 401 {\"error\": \"auth\"}",
                 "ok    headers: GET /login carries X-Robots-Tag, Referrer-Policy, X-Frame-Options and "
                 "X-Content-Type-Options",
                 "ok    vendor: only alerts of the four site kinds",
                 "ok    vendor: the alert sheet does not say who was pushed (sent is empty)",
                 "ok    vendor: POST /api/alerts/ack answers 403 {\"error\": \"auth\"}",
                 "ok    vendor: GET /anything-else goes back to /site",
                 "ok    share link: GET /api/messages answers 401",
                 "ok    share link: a wrong token answers 403 and shows nothing",
                 "ok    vendor without alerts: both alert lists are empty",
                 "ok    vendor: sees none of the alerts of other kinds that the owner sees",
                 "ok    share link: with the token even the owner gets what the link shows, not more",
                 "ok    vendor: the page carries no nav and no links (the owner's other screens)",
                 "ok    vendor without alerts: the page carries no nav and no links (the owner's other screens)",
                 "ok    share link: the page carries no nav and no links (the owner's other screens)"):
        assert line in output.splitlines(), line
    assert "note  the owner's page has no menu" not in output              # the check was seen at work
    assert "sh_alert_ack" not in fake.names() and "sh_rum_add" not in fake.names()       # it changed nothing
    assert len(server._failures) == 2                          # one wrong password, one wrong token
    for secret in (*PASSWORDS.values(), TOKEN, TOKEN[:-1], "sh_session=", server._token("agency-pass-03", expiry(30))):
        assert secret not in output


def test_check_access_with_only_what_a_live_check_holds(live):
    code, output = check_access(live, "--no-share", "--no-quiet", SH_PASS_VENDOR_CHECK=PASSWORDS["vendor"])
    assert code == 0, output
    assert "share link: a wrong token answers 403 and shows nothing" in output          # a made-up one, still tried
    assert "vendor without alerts" not in output and "owner:" not in output


def test_check_access_takes_ready_cookies(live, visit):
    people = (("SH_COOKIE_VENDOR", "vendor"), ("SH_COOKIE_QUIET", "noalerts"), ("SH_COOKIE_OWNER", "owner"))
    cookies = {name: "%s=%s" % (server.COOKIE, visit(role).cookies[server.COOKIE]) for name, role in people}
    code, output = check_access(live, SH_SHARE_TOKEN=TOKEN, **cookies)
    assert code == 0, output
    assert "the session cookie is HttpOnly" not in output      # no sign-in was seen, so there is nothing to say of it
    assert ("note  the owner's page has no menu (nav) and no extra buttons (links) either, so \"carries no nav and no "
            "links\" could not be seen at work") in output.splitlines()     # this site has no other screens


@pytest.mark.parametrize("flags, env, said", [
    ((), {}, "COULD NOT RUN: set SH_PASS_VENDOR_CHECK (or SH_COOKIE_VENDOR); SH_SHARE_TOKEN (or pass --no-share); "
             "SH_PASS_VENDOR_CHECK_QUIET or SH_COOKIE_QUIET (or pass --no-quiet)"),
    (("--no-quiet",), {"SH_PASS_VENDOR_CHECK": PASSWORDS["vendor"]},
     "COULD NOT RUN: set SH_SHARE_TOKEN (or pass --no-share)"),
    (("--no-share", "--no-quiet"), {"SH_PASS_VENDOR_CHECK": "not-the-password"},
     "COULD NOT RUN: the sign-in of the vendor failed (status 401): check its variable"),
])
def test_check_access_that_cannot_run_says_why(flags, env, said, live):
    code, output = check_access(live, *flags, **env)
    assert (code, output.strip()) == (2, said)


def test_check_access_against_nothing(live):
    code, output = check_access("http://127.0.0.1:9", "--no-share", "--no-quiet", SH_PASS_VENDOR_CHECK="x")
    assert (code, output.strip()) == (
        2, "COULD NOT RUN: the server does not answer at http://127.0.0.1:9 (ConnectionRefusedError)")
    code, output = check_access(live + "/site?k=" + TOKEN, **CHECK_ENV)
    assert code == 2 and "the address must look like" in output and TOKEN not in output


async def now_not_recounted():
    return server._json(await server.rpc("sh_now"))


async def drill_that_tells_who_was_pushed(request: server.Request):
    q = request.query_params
    if q.get("what") != "alert":
        return server._json({"rows": []})
    rows = await server.rpc("sh_drill_alert", {"p_id": int(q["id"])})
    return server._json({"rows": server._alerts_for(request.state.viewer, rows)})


BROKEN = {
    # name: (what is broken in the copy, a check that must fail)
    "no filter": (lambda m: m.setattr(server, "_alerts_for", lambda viewer, rows: rows),
                  "vendor: only alerts of the four site kinds"),
    "a fifth kind": (lambda m: m.setattr(server, "SITE_ALERT_KINDS", server.SITE_ALERT_KINDS | {"ops"}),
                     "share link: only alerts of the four site kinds"),
    "the push log is on the outsiders' list": (
        lambda m: m.setattr(server, "OUTSIDER_PATHS", server.OUTSIDER_PATHS | {"/api/messages"}),
        "vendor: GET /api/messages answers 403 {\"error\": \"auth\"}"),
    "a vendor is treated as staff": (lambda m: m.setattr(server.Viewer, "outsider", property(lambda viewer: False)),
                                     "vendor: POST /api/alerts/ack answers 403 {\"error\": \"auth\"}"),
    "the token is read on another route": (
        lambda m: (m.setattr(server, "DATA_PATHS", server.DATA_PATHS | {"/api/messages"}),
                   m.setattr(server, "OUTSIDER_PATHS", server.OUTSIDER_PATHS | {"/api/messages"})),
        "share link: GET /api/messages answers 401"),
    "any token opens the link": (lambda m: m.setattr(server, "_share_ok", lambda k: bool(k)),
                                 "share link: a wrong token answers 403 and shows nothing"),
    "the count is not recounted": (lambda m: replace_route("/api/site/now", now_not_recounted, m),
                                   "vendor: GET /api/site/now answers 200, and its count of open alerts is the count "
                                   "of the list this viewer gets"),
    "the alert sheet tells who was pushed": (
        lambda m: replace_route("/api/site/drill", drill_that_tells_who_was_pushed, m),
        "vendor: the alert sheet does not say who was pushed (sent is empty)"),
    "nobody is without alerts": (lambda m: m.setenv("SH_VENDOR_NOALERTS", ""),
                                 "vendor without alerts: both alert lists are empty"),
    "any cookie is a session": (
        lambda m: m.setattr(server, "_by_cookie", lambda request: server.Viewer("vendor", "anybody")
                            if request.cookies.get(server.COOKIE) else None),
        "nobody: a made-up session cookie opens nothing"),
    "a vendor's session lasts a year": (
        lambda m: m.setattr(server.Viewer, "session_seconds", property(lambda viewer: 86400 * 365)),
        "vendor: the session cookie is HttpOnly, SameSite=Lax and lasts at most 30 days"),
    "the ingest asks for a session": (lambda m: m.setattr(server, "OPEN_PATHS", server.OPEN_PATHS - {"/m"}),
                                      "nobody: POST /m answers 204 with an empty body (not a beacon)"),
    "/health asks for a session": (lambda m: m.setattr(server, "OPEN_PATHS", server.OPEN_PATHS - {"/health"}),
                                   "nobody: GET /health answers 200 with ok, db and last_probe_age_sec"),
    "outsiders get the owner's menu": (
        lambda m: (m.setattr(server, "OWNER_ONLY", ()),
                   m.setitem(db.rpc.answers, "sh_config", dict(CONFIG, screen=dict(SCREEN_CONFIG, **MENU)))),
        "vendor: the page carries no nav and no links (the owner's other screens)"),
    "an answer without the headers": (
        lambda m: m.setattr(server, "SECURITY_HEADERS", {"X-Robots-Tag": "noindex"}),
        "headers: GET /api/site carries X-Robots-Tag, Referrer-Policy, X-Frame-Options and X-Content-Type-Options"),
}


@pytest.mark.parametrize("name", BROKEN)
def test_check_access_fails_against_a_broken_copy(name, live, monkeypatch):
    break_it, expected = BROKEN[name]
    break_it(monkeypatch)
    code, output = check_access(live, **CHECK_ENV)
    assert code == 1, output
    assert any(line.startswith(expected) for line in failures(output)), output
    for secret in (*PASSWORDS.values(), TOKEN, "sh_session="):
        assert secret not in output


def test_check_access_can_prove_that_a_made_up_address_does_not_dodge_the_limit(live, monkeypatch, fake):
    monkeypatch.setenv("SH_PROXY_HOPS", "0")                   # the truth here: no proxy in front of this server
    code, output = check_access(live, "--limiter", **CHECK_ENV)
    assert code == 0, output
    assert ("ok    limiter: wrong passwords with made-up X-Forwarded-For entries still get this address blocked (429)"
            in output)
    assert "note  --limiter: this address is now refused at sign-in for ten minutes" in output
    logged = {params["p_ip"] for fn, params in fake.calls if fn == "sh_login_log_add"}
    assert logged == {"127.0.0.1"}                             # the login log shows the tester's real address


def test_check_access_shows_a_server_that_believes_a_made_up_address(live, monkeypatch):
    monkeypatch.delenv("SH_PROXY_HOPS", raising=False)         # the default says "one proxy", and there is none
    code, output = check_access(live, "--limiter", **CHECK_ENV)
    assert code == 1 and failures(output) == [
        "limiter: wrong passwords with made-up X-Forwarded-For entries still get this address blocked (429)"
        "  -> [401, 401, 401, 401, 401, 401, 401, 401, 401]"], output


def test_check_access_needs_only_the_standard_library():
    source = CHECK_ACCESS.read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:import|from) ([a-z_.]+)", source, re.M))
    assert imported == {"argparse", "json", "os", "re", "sys", "urllib.error", "urllib.parse", "urllib.request"}
    assert "print(" in source and not re.search(r"print\([^)]*(password|token|cookie)\b", source)


# ================================================================ conftest.py: where the kit is, and no Postgres

def run_pytest(folder, *arguments, **env):
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arguments], cwd=folder,
                          env=child_env(**env), capture_output=True, encoding="utf-8", timeout=600)
    return done.returncode, done.stdout + done.stderr


@pytest.fixture(scope="module")
def repository(tmp_path_factory):
    """The layout of a target repository: site-health/ is a copy of reference/, and the kit's own two files
    are in site-health-kit/ next to it."""
    root = tmp_path_factory.mktemp("repository")
    shutil.copytree(REFERENCE, root / "site-health", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (root / "site-health-kit").mkdir()
    for name in ("mock_server.py", "site_health.html"):
        shutil.copy(KIT / name, root / "site-health-kit" / name)
    return root


SOME_TESTS = ("test_the_marker_is_replaced_exactly_once or test_a_hostile_configuration_value_cannot_leave_the_script "
              "or test_api_site_puts_the_parts_together or test_health")


def test_the_tests_run_in_a_copy_of_the_backend_next_to_the_kit(repository):
    backend = repository / "site-health"
    code, output = run_pytest(backend, "--collect-only", SH_KIT_DIR="")                 # every file can be imported
    assert code == 0 and re.search(r"\n\d+ tests collected in ", output), output[-2000:]
    for name in ("tests/test_server.py::", "tests/test_sql.py::", "tests/test_collectors.py::"):
        assert name in output
    code, output = run_pytest(backend, "tests/test_server.py", "-k", SOME_TESTS, SH_KIT_DIR="")
    assert code == 0 and re.search(r"\n\d+ passed, \d+ deselected", output), output[-2000:]
    # with the deployed screen in its place, the server of that copy serves it without any setting
    shutil.copy(KIT / "site_health.html", backend / "site_health.html")
    try:
        program = "import server; print(server._screen_file()); print(server._screen_state())"
        done = subprocess.run([sys.executable, "-c", program], cwd=backend, env=child_env(), capture_output=True,
                              encoding="utf-8", timeout=60)
        assert done.stdout.split() == [str(backend / "site_health.html"), "ok"], done.stdout + done.stderr
    finally:
        (backend / "site_health.html").unlink()


def test_the_kit_can_be_anywhere_when_sh_kit_dir_names_it(repository, tmp_path):
    kit = shutil.copytree(repository / "site-health-kit", tmp_path / "unpacked somewhere else")
    backend = shutil.copytree(repository / "site-health", tmp_path / "backend")
    code, output = run_pytest(backend, "tests/test_server.py", "-k", SOME_TESTS, SH_KIT_DIR=str(kit))
    assert code == 0 and re.search(r"\n\d+ passed, \d+ deselected", output), output[-2000:]


def test_without_the_kit_the_run_ends_with_one_line_that_names_sh_kit_dir(repository, tmp_path):
    backend = shutil.copytree(repository / "site-health", tmp_path / "backend")
    for arguments in ((), ("tests/test_server.py",)):
        code, output = run_pytest(backend, *arguments, SH_KIT_DIR="")
        assert code == 2 and "Traceback" not in output and len(output.strip().splitlines()) <= 3, output[-2000:]
        assert ("The kit's own files (mock_server.py, site_health.html) were not found in %s or %s. Set SH_KIT_DIR to "
                "the folder of the unpacked kit (site-health-kit) and run again." % (tmp_path, tmp_path / "site-health-kit")
                ) in output
    code, output = run_pytest(backend, "tests/test_server.py", SH_KIT_DIR=str(tmp_path / "nowhere"))
    assert code == 2 and "were not found in %s. Set SH_KIT_DIR" % (tmp_path / "nowhere") in output


def _refused_by_the_scratch_server(**changes):
    """SH_TEST_ADMIN_URL with `changes` (a wrong password, a database that is not there), when the server of
    these tests answers and refuses it; else None (no server here, or one that lets anybody in)."""
    from psycopg.conninfo import make_conninfo
    import psycopg

    address = make_conninfo(conftest.ADMIN_URL, **changes)
    try:
        psycopg.connect(conftest.ADMIN_URL, connect_timeout=5).close()
    except psycopg.Error:
        return None
    try:
        psycopg.connect(address, connect_timeout=5).close()
    except psycopg.Error:
        return address
    return None


@pytest.mark.parametrize("address, where", [
    ("postgresql://postgres:TopSecretPw@127.0.0.1:9/postgres", "127.0.0.1:9"),
    ("postgresql://postgres:TopSecretPw@127.0.0.1:9/postgres?connect_timeout=2", "127.0.0.1:9"),
    ("postgresql://postgres:My%TopSecretPw@127.0.0.1:9/postgres", "an address that is not a connection string"),
    # a server answers there, and refuses: the same one line
    (lambda: _refused_by_the_scratch_server(password="TopSecretPw-wrong"), None),
    (lambda: _refused_by_the_scratch_server(dbname="sh_no_such_database"), None),
])
def test_without_a_postgres_the_run_ends_with_one_line_and_no_password(address, where):
    if callable(address):
        address, where = address(), conftest._where(conftest.ADMIN_URL)
        if address is None:
            pytest.skip("no scratch Postgres here that refuses a wrong password")
    code, output = run_pytest(REFERENCE, "tests/test_sql.py", SH_TEST_ADMIN_URL=address)
    assert code == 2, output[-2000:]
    assert ("No usable Postgres at SH_TEST_ADMIN_URL (%s): no answer, or the sign-in was refused. Start one, or set "
            "SH_TEST_ADMIN_URL to a server where the tests may create and drop a scratch database; see \"Running the "
            "tests\" in reference/README.md." % where) in output
    assert "TopSecretPw" not in output and "Traceback" not in output and "password" not in output
    assert len(output.strip().splitlines()) <= 3               # not one traceback per test


def test_the_server_tests_alone_need_no_postgres():
    code, output = run_pytest(REFERENCE, "tests/test_server.py", "-k", "test_db_over_a_postgres_connection or test_health",
                              "-rs", SH_TEST_ADMIN_URL="postgresql://postgres:TopSecretPw@127.0.0.1:9/postgres")
    assert code == 0 and re.search(r"\n\d+ passed, 1 skipped", output), output[-2000:]
    assert "no scratch Postgres database: No usable Postgres at SH_TEST_ADMIN_URL (127.0.0.1:9)" in output
    assert "TopSecretPw" not in output
