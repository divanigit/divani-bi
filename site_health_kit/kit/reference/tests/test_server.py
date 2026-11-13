"""Tests of server.py: access rules (SPEC.md §8), the data contract (§5), the page, /rum and /health.

No database is needed: db.rpc is replaced by a fake that records every call and answers with the
payloads of the kit's mock_server.py. The last section tests db.py itself: its HTTPS transport
against a stand-in for Supabase, and its Postgres transport when a scratch database can be made
(conftest.py; skipped otherwise).

    cd reference && python3 -m pytest -q tests/test_server.py
"""
import copy
import hmac
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import types
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REFERENCE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REFERENCE), str(REFERENCE.parent)]        # server.py and db.py; the kit's mock_server.py

import db  # noqa: E402
import mock_server  # noqa: E402
import server  # noqa: E402

REAL_RPC = db.rpc                                             # the tests of the server replace db.rpc
TOKEN = "share-token-9f3a"
PASSWORDS = {"owner": "Owner Pass-1", "staff": "staff-pass", "vendor": "dana-pass", "noalerts": "keren-pass"}
ENV = {"SH_PASS_OWNER": PASSWORDS["owner"], "SH_PASS_STAFF": PASSWORDS["staff"],
       "SH_PASS_VENDOR_DANA": PASSWORDS["vendor"], "SH_PASS_VENDOR_KEREN": PASSWORDS["noalerts"],
       "SH_VENDOR_NOALERTS": " keren ,someone-else", "SH_SHARE_TOKEN": TOKEN, "COLLECTORS": "0"}
ROLES = ("owner", "staff", "vendor", "noalerts", "share", None)             # None = nobody
SCREEN_ROLE = {"owner": {}, "staff": {}, "vendor": {"readonly": True},
               "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}
# sh_config() after sh_setup of site_health.config.example.json (the page list is shortened)
SCREEN_CONFIG = {"hide": [], "brand": "", "homePage": "בית", "coreCount": 5, "liveHosts": ["live"],
                 "siteLabel": "example.co.il", "bucketNote": "", "probeCount": 4,
                 "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]}
CONFIG = {"host": "example.co.il", "site": "https://example.co.il", "brand": "", "label": "example.co.il",
          "pages": [{"url": "https://example.co.il/", "core": True, "home": True, "name": "בית", "probe": True,
                     "expect": None}],
          "screen": SCREEN_CONFIG, "morning": "07:30", "platform": "woocommerce", "time_zone": "Asia/Jerusalem",
          "down_after": 1, "live_hosts": ["live"], "bucket_note": "",
          "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]}
NOT_SET_UP = {"pages": [], "screen": {"hide": [], "coreCount": 0, "probeCount": 0}}       # sh_config() before sh_setup
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
    monkeypatch.setattr(server, "_rum_busy", False)
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


# ================================================================ routes and access (§8.2)

def test_the_app_exposes_exactly_the_specified_routes():
    routes = {(method, route.path) for route in server.app.routes for method in route.methods}
    assert routes == {("GET", "/"), ("GET", "/site"), ("GET", "/status"), ("GET", "/login"), ("POST", "/login"),
                      ("GET", "/logout"), ("GET", "/health"), ("GET", "/api/site"), ("GET", "/api/site/now"),
                      ("GET", "/api/site/drill"), ("GET", "/api/messages"), ("POST", "/api/alerts/ack"),
                      ("POST", "/rum")}


TO_LOGIN, TO_SITE = (303, "/login"), (303, "/site")
ACCESS = [
    # method, path, body                      owner+staff   vendors    share link  nobody
    ("GET", "/", None,                        TO_SITE,      TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("GET", "/site", None,                    200,          200,       TO_LOGIN,   TO_LOGIN),
    ("GET", "/status", None,                  403,          403,       200,        403),     # only the token counts
    ("GET", "/login", None,                   (303, "/"),   (303, "/"), 200,       200),
    ("GET", "/logout", None,                  TO_LOGIN,     TO_LOGIN,  TO_LOGIN,   TO_LOGIN),
    ("GET", "/health", None,                  200,          200,       200,        200),
    ("POST", "/rum", None,                    204,          204,       204,        204),
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
    assert response.headers["x-robots-tag"] == "noindex"
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
    assert injected(page.text) == (dict(SCREEN_CONFIG, shareKey=TOKEN), {"share": True})
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


def test_secrets_are_compared_in_constant_time(monkeypatch, visit):
    seen, real = [], hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(server.hmac, "compare_digest", spy)
    client = visit(None)
    sign_in(client, "a guess")
    assert (b"a guess", b"owner pass-1") in seen and (b"a guess", b"dana-pass") in seen
    client.get("/site", headers={"Cookie": server.COOKIE + "=forged"})
    assert (b"forged", server._token("owner pass-1").encode()) in seen
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
    assert re.fullmatch("[0-9a-f]{64}", value)
    assert attributes == {"httponly", "samesite=lax", "path=/", "max-age=%d" % (max_age * 86400)}    # http: no "secure"


def test_the_cookie_is_secure_on_https_only(visit):
    def attributes(client, **headers):
        return cookie_of(sign_in(client, PASSWORDS["owner"], **headers))[1]

    assert "secure" not in attributes(visit(None))
    assert "secure" in attributes(visit(None, base_url="https://testserver"))
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https"})            # behind the host's proxy
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https, http"})
    assert "secure" not in attributes(visit(None, base_url="https://testserver"), **{"X-Forwarded-Proto": "http"})


def test_changing_a_password_ends_the_session(monkeypatch, visit):
    owner, vendor = visit("owner"), visit("vendor")
    old = owner.cookies[server.COOKIE]
    assert owner.get("/site").status_code == 200 and vendor.get("/site").status_code == 200

    monkeypatch.setenv("SH_PASS_OWNER", "a new password")
    assert owner.get("/site").headers["location"] == "/login"
    assert owner.get("/api/site").status_code == 401
    assert sign_in(visit(None), PASSWORDS["owner"]).status_code == 401
    new = cookie_of(sign_in(visit(None), "a new password"))[0]
    assert new != old and new == server._token("a new password")

    monkeypatch.delenv("SH_PASS_VENDOR_DANA")                  # deleting it signs the person out at once
    assert vendor.get("/site").headers["location"] == "/login"
    assert vendor.get("/api/site").status_code == 401


@pytest.mark.parametrize("typed", ["Owner Pass-1", "owner pass-1", "OWNER PASS-1", "  Owner Pass-1 ",
                                   "\tOWNER pass-1\n"])
def test_passwords_match_trimmed_and_without_case(typed, monkeypatch, visit):
    monkeypatch.setenv("SH_PASS_OWNER", "  Owner Pass-1  ")
    response = sign_in(visit(None), typed)
    assert response.status_code == 303
    assert cookie_of(response)[0] == server._token("owner pass-1")       # one cookie however it was typed


@pytest.mark.parametrize("typed", ["", " ", "Owner Pass-1x", "OwnerPass-1", "Owner  Pass-1", "staff", TOKEN])
def test_a_wrong_password_is_refused(typed, visit):
    response = sign_in(visit(None), typed)
    assert response.status_code == 401 and server.TEXT_WRONG in response.text
    assert "set-cookie" not in response.headers


def test_unset_and_blank_passwords_never_match(monkeypatch, visit):
    monkeypatch.delenv("SH_PASS_STAFF")
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", "   ")
    monkeypatch.setenv("SH_PASS_VENDOR_", "no-name")           # a variable without a name is nobody
    assert [viewer.who for _, viewer in server._accounts()] == ["KEREN", "owner"]
    for typed in ("", "   ", "None", "no-name"):
        assert sign_in(visit(None), typed).status_code == 401
    for forged in (server._token(""), ""):                     # the digest an empty key would give; an empty cookie
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
    ({"SH_PASS_VENDOR_DANA": " OWNER pass-1 "}, "Owner Pass-1", "DANA", "vendor", 30),
    ({"SH_PASS_STAFF": "owner PASS-1"}, "Owner Pass-1", "staff", "staff", 365),
    ({"SH_PASS_VENDOR_DANA": "staff-pass", "SH_PASS_OWNER": "STAFF-PASS"}, "staff-pass", "DANA", "vendor", 30),
    ({"SH_PASS_VENDOR_DANA": "keren-pass"}, "keren-pass", "KEREN", "vendor", 30),       # KEREN is the noAlerts one
    ({"SH_PASS_VENDOR_AARON": "keren-pass"}, "keren-pass", "KEREN", "vendor", 30),      # not the alphabet: the rights
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
    if who == "KEREN":
        assert injected(client.get("/site").text)[1] == {"readonly": True, "noAlerts": True}


def test_a_shared_password_is_reported_at_startup(monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", PASSWORDS["owner"].upper())
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"), TestClient(server.app):
        pass
    assert [record.getMessage() for record in caplog.records] == [
        "DANA and owner have the same password: both sign in as DANA (vendor)"]


def test_every_attempt_is_logged(fake, visit):
    client = visit(None)
    headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1", "User-Agent": "Phone/1.0 " + "x" * 300}
    sign_in(client, "a guess", **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": False, "p_who": "?",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(client, PASSWORDS["vendor"], **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": True, "p_who": "DANA",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(visit(None), PASSWORDS["owner"])
    assert fake.params("sh_login_log_add") == {"p_ip": "testclient", "p_ok": True, "p_who": "owner",
                                               "p_ua": "testclient"}


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
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", "סיסמה חזקה")
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


# ================================================================ the time window (§5.1)

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


# ================================================================ the data calls (§5.2 – §5.7)

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
    assert answer["speed"] == {"error": "not a DbError"} and answer["availability"] == fake.answers["sh_availability"]

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


@pytest.mark.parametrize("query", [{"what": "alert"}, {"what": "alert", "id": ""}, {"what": "alert", "id": "abc"},
                                   {"what": "alert", "id": "-41"}, {"what": "alert", "id": "41;drop"}])
def test_drill_of_an_alert_without_a_usable_id_has_no_rows(query, fake, visit):
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (200, {"rows": []}) and fake.calls == []


@pytest.mark.parametrize("query", [{}, {"what": ""}, {"what": "everything"}, {"what": "FAILS"}])
def test_drill_of_an_unknown_kind_is_a_400(query, fake, visit):
    fake.failing.add("sh_config")                              # decided before the database is asked
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (400, {"error": "what?"})
    assert response.headers["cache-control"] == "no-store" and fake.calls == []


@pytest.mark.parametrize("what, fn", [("fails", "sh_drill_fails"), ("bucket", "sh_drill_bucket"),
                                      ("runs", "sh_drill_runs"), ("alert", "sh_drill_alert")])
def test_drill_failure_and_empty_result(what, fn, fake, visit):
    client = visit("owner")
    fake.answers[fn] = None
    assert client.get("/api/site/drill", params={"what": what, "id": 41}).json() == {"rows": []}
    fake.failing.add(fn)
    response = client.get("/api/site/drill", params={"what": what, "id": 41})
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
])
def test_ack_marks_the_listed_alerts(body, p_ids, fake, visit):
    response = visit("owner").post("/api/alerts/ack", json=body)
    assert (response.status_code, response.json()) == (200, {"ok": True, "n": len(p_ids)})
    assert response.headers["cache-control"] == "no-store"
    assert fake.calls == [("sh_alert_ack", {"p_ids": p_ids, "p_who": "owner"})]


@pytest.mark.parametrize("body", [b"", b"not json", b"[41]", b"41", b"null", b'"41"', b"{}", b'{"ids": []}',
                                  b'{"ids": "41"}', b'{"ids": ["x", 0, -3, true]}', b'{"id": "abc"}', b'{"id": null}',
                                  b'{"id": [41]}', b'{"ids": {"0": 41}}',
                                  b'{"ids": [41], "pad": "' + b"x" * 20000 + b'"}'])
def test_ack_refuses_a_bad_body(body, fake, visit):
    response = visit("owner").post("/api/alerts/ack", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, response.json()) == (400, {"error": "bad request"}) and fake.calls == []


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
    source = (REFERENCE.parent / "site_health.html").read_text(encoding="utf-8")
    assert source.count(server.MARKER) == 1
    response = visit("owner").get("/site")
    assert response.status_code == 200 and response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    script = ('<script>window.SH_CONFIG={"hide": [], "brand": "", "homePage": "בית", "coreCount": 5, '
              '"liveHosts": ["live"], "siteLabel": "example.co.il", "bucketNote": "", "probeCount": 4, "pathLabels": '
              '[["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]};window.SH_ROLE={};</script>')
    assert response.text == source.replace(server.MARKER, script)          # the rest of the file is untouched
    assert response.text.count("window.SH_CONFIG=") == 1 and server.MARKER not in response.text


@pytest.mark.parametrize("role", ["owner", "staff", "vendor", "noalerts", "share"])
def test_the_page_carries_the_role_of_the_viewer(role, visit):
    path = "/status" if role == "share" else "/site"
    config, screen_role = injected(send(visit, role, "GET", path).text)
    assert screen_role == SCREEN_ROLE[role]
    assert config == (dict(SCREEN_CONFIG, shareKey=TOKEN) if role == "share" else SCREEN_CONFIG)


HOSTILE = {"siteLabel": 'x</script><script>alert("1")</script>', "brand": "a'b\"c\\d</SCRIPT >",
           "bucketNote": "<!--<script>\u2028\u2029-->", "homePage": "בית & </",
           "nav": [["a", "/x", "]]>;window.SH_ROLE={};"]]}


def test_a_hostile_configuration_value_cannot_leave_the_script(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    plain = Scripts((REFERENCE.parent / "site_health.html").read_text(encoding="utf-8")).found
    page = visit("vendor").get("/site").text
    scripts = Scripts(page).found
    assert len(scripts) == len(plain) + 1 and scripts[1:] == plain          # one script more, the screen's own intact
    assert not re.search("[<\u2028\u2029]", scripts[0])                     # nothing that can end or break the script
    assert injected(page) == (HOSTILE, {"readonly": True})                  # and the values arrive unchanged
    assert "<script>alert" not in page and page.count("</script>") == len(plain) + 1


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_injected_script_is_javascript_that_yields_the_same_values(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    script = Scripts(visit("vendor").get("/site").text).found[0]
    program = "var window = {};%s;process.stdout.write(JSON.stringify([window.SH_CONFIG, window.SH_ROLE]))" % script
    done = subprocess.run(["node", "-e", program], capture_output=True, encoding="utf-8", timeout=60, check=True)
    assert json.loads(done.stdout) == [HOSTILE, {"readonly": True}]


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
        assert response.headers["x-robots-tag"] == "noindex"
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


# ================================================================ real-user beacons (§7.7)

def beacon(client, body=BEACON, **headers):
    content = body if isinstance(body, (bytes, str)) else json.dumps(body)
    response = client.post("/rum", content=content, headers={"Content-Type": "text/plain;charset=UTF-8", **headers})
    assert (response.status_code, response.content) == (204, b"")           # always, stored or not
    assert response.headers["x-robots-tag"] == "noindex"


def stored(fake):
    return [row for fn, params in fake.calls if fn == "sh_rum_add" for row in params["p_rows"]]


def test_a_beacon_is_stored_without_anything_about_the_visitor(fake, visit):
    client = visit("vendor")                                   # even with a session cookie on the request
    body = dict(BEACON, path="/product/sofa/?utm_source=mail&email=dana@example.com#reviews", ua="x", ip="y")
    beacon(client, body, **ORIGIN, **{"X-Forwarded-For": "203.0.113.77", "User-Agent": "Mozilla/5.0 (secret-agent)",
                                      "Cookie": "customer_session=abc123",
                                      "Referer": "https://example.co.il/product/sofa/?token=t0k"})
    assert fake.calls == [("sh_config", None), ("sh_rum_add", {"p_rows": [
        {"site": "live", "path": "/product/sofa/", "lcp_ms": 2345, "is_test": False}]})]
    recorded = json.dumps(fake.calls)
    secrets = ("203.0.113.77", "secret-agent", "abc123", client.cookies[server.COOKIE], "utm", "dana", "t0k", "reviews")
    assert not [secret for secret in secrets if secret in recorded]


@pytest.mark.parametrize("headers, kept", [
    ({"Origin": "https://example.co.il"}, True),
    ({"Origin": "https://www.example.co.il"}, True),
    ({"Origin": "https://WWW.Example.co.il:8443"}, True),
    ({"Referer": "https://www.example.co.il/product/sofa/?a=1"}, True),       # no Origin: the Referer decides
    ({"Origin": "https://example.co.il", "Referer": "https://elsewhere.com/"}, True),
    ({}, False),
    ({"Origin": "null"}, False),
    ({"Origin": "https://staging.example.co.il"}, False),
    ({"Origin": "https://example.co.il.evil.com"}, False),
    ({"Origin": "https://evilexample.co.il"}, False),
    ({"Origin": "https://elsewhere.com", "Referer": "https://example.co.il/"}, False),
    ({"Referer": "https://elsewhere.com/?https://example.co.il/"}, False),
])
def test_only_the_site_itself_may_send_beacons(headers, kept, fake, visit):
    beacon(visit(None), **headers)
    assert len(stored(fake)) == kept


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
    ({"site": "staging.example.co.il"}, {"site": "staging.example.co.il"}),
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
    {"path": "/my-account/lost-password/"},
    {"path": "product/sofa/"}, {"path": "https://example.co.il/x"}, {"path": ""}, {"path": None}, {"path": 7},
    {"lcp": 0}, {"lcp": 0.4}, {"lcp": 60001}, {"lcp": -5}, {"lcp": "2345"}, {"lcp": None}, {"lcp": True}, {"lcp": [1]},
    {"site": ""}, {"site": None}, {"site": "Live Site"}, {"site": "a" * 300},
])
def test_what_is_dropped(change, fake, visit):
    beacon(visit(None), dict(BEACON, **change), **ORIGIN)
    assert stored(fake) == []


@pytest.mark.parametrize("body", [b"", b"not json", b"[1]", b"null", b'"x"', b'{"site":"live","path":"/","lcp":NaN}',
                                  b'{"site":"live","path":"/","lcp":1e999}', b"\xff\xfe"])
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


# ================================================================ /health (§7.10) and start-up

def test_health(fake):
    client = TestClient(server.app)                            # no session
    for flow in fake.answers["sh_health"]:
        flow["last_at"] = (NOW - timedelta(hours=3)).isoformat()
    fake.answers["sh_health"][0].update(flow_name=server.PROBE_FLOW, last_at="2026-11-13T10:14:48.5+02:00")   # 41.5 s
    response = client.get("/health")
    assert (response.status_code, response.json()) == (200, {"ok": True, "db": "ok", "last_probe_age_sec": 41})
    assert response.headers["cache-control"] == "no-store" and response.headers["x-robots-tag"] == "noindex"
    assert fake.names() == ["sh_ping", "sh_health"]

    fake.answers["sh_health"][0]["last_at"] = None             # installed, the prober has not run yet
    assert client.get("/health").json() == {"ok": True, "db": "ok", "last_probe_age_sec": None}
    fake.answers["sh_health"] = None
    assert client.get("/health").json() == {"ok": True, "db": "ok", "last_probe_age_sec": None}


def test_health_stays_200_when_the_database_is_down(fake, monkeypatch):
    client = TestClient(server.app)
    fake.failing.add("sh_ping")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "boom: sh_ping", "last_probe_age_sec": None}
    fake.failing = {"sh_health"}
    assert client.get("/health").json() == {"ok": False, "db": "boom: sh_health", "last_probe_age_sec": None}

    def crash(fn, params=None):
        raise RuntimeError()

    monkeypatch.setattr(db, "rpc", crash)                      # whatever goes wrong
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "RuntimeError", "last_probe_age_sec": None}


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
    }

    def log_message(self, *args):
        pass

    def do_POST(self):
        params = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, {name.lower(): value for name, value in self.headers.items()}, params))
        status, body = self.answers.get(self.path.rsplit("/", 1)[-1], (200, json.dumps({"got": params}).encode()))
        self.send_response(status)
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


def test_db_over_a_postgres_connection(request, monkeypatch):
    try:
        url = request.getfixturevalue("database")              # conftest.py: a scratch database with the kit's SQL
    except Exception as e:
        pytest.skip("no scratch Postgres database: %s" % e)
    import psycopg

    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", url)
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

        with pytest.raises(db.DbError, match="does not exist"):
            REAL_RPC("sh_no_such_function")
        assert REAL_RPC("sh_ping") == "ok" and db._thread.conn is conn     # an SQL error does not cost the connection

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
