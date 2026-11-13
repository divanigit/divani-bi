"""Site Health server: sign-in, roles, the screen and its data calls (spec §5 and §8).

No business logic lives here. Every figure comes from an sh_* SQL function through db.rpc();
this file decides who may see what and turns failures into the statuses of spec §5.7.

    uvicorn server:app --host 0.0.0.0 --port 8000        # one worker: each worker would start its own collectors

Environment: SH_PASS_OWNER (without it nobody can sign in), SH_PASS_STAFF, SH_PASS_VENDOR_<NAME>,
SH_VENDOR_NOALERTS, SH_SHARE_TOKEN, SH_PROXY_HOPS, SH_SCREEN, COLLECTORS, and the database variables
of db.py. Everything about the site itself comes from sh_config().
"""
import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import time
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

import db

log = logging.getLogger("uvicorn.error")     # the logger uvicorn prints; one of our own is silent below WARNING

COOKIE = "sh_session"
SESSION_LABEL = b"site-health-session-v1"
VENDOR_PREFIX = "SH_PASS_VENDOR_"
DEFAULT_SCREEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "site_health.html")
MARKER = "<!--SH_INJECT-->"

# Access (spec §8.2). An outsider (vendor, share link) gets an allow-list, so a route added later is closed to them.
OPEN_PATHS = {"/login", "/logout", "/health", "/m"}          # answered before any role check
DATA_PATHS = {"/api/site", "/api/site/now", "/api/site/drill"}
OUTSIDER_PATHS = DATA_PATHS | {"/site", "/status"}           # all an outsider may GET; nothing else, no other method
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}        # the only alerts an outsider sees

MAX_FAILURES, FAILURE_WINDOW = 8, 600                        # failed sign-ins from one address, within seconds
PROBE_FLOW = "בודק זמינות האתר"                              # the flow whose last run is "the last check"

RUM_MAX_BYTES, RUM_MAX_PATH, RUM_PER_MINUTE, RUM_BATCH, RUM_QUEUE = 1024, 300, 60, 50, 1000
# Path segments that name an account, checkout, order or admin page: such a view is never stored.
# A site adds its own (translated slugs) with "private_paths" in its configuration.
RUM_PRIVATE = {"account", "my-account", "checkout", "checkouts", "order", "orders", "order-received", "order-pay",
               "view-order", "lost-password", "admin", "wp-admin", "wp-login.php"}
RUM_SITE = re.compile(r"[a-z0-9.-]{1,100}")                  # "live" or a host name
BUCKET = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}( [0-9]{2}:00)?")       # a day or an hour, as the charts name them

TEXT_WRONG = "סיסמה שגויה"
TEXT_BLOCKED = "יותר מדי ניסיונות. נסו שוב בעוד עשר דקות."
TEXT_BAD_LINK = "הקישור אינו תקין או שפג."
TEXT_NO_DATA = "אין כרגע חיבור לנתונים. נסו שוב בעוד רגע."

PAGE_SHELL = """<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>בריאות האתר</title><style>
:root{--brand:#0d9668;--bg:#ffffff;--surface:#f4f8f6;--line2:#cdd8d2;--tx:#18241f;--dfg:#a3271f}
@media (prefers-color-scheme:dark){:root{--brand:#2fbf8f;--bg:#0f1512;--surface:#19211d;--line2:#35423b;--tx:#e9efeb;--dfg:#f0968f}}
html,body{background:var(--bg);color:var(--tx);margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Hebrew",Arial,sans-serif}
.wrap{min-height:100svh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
.card{width:100%;max-width:330px;text-align:center}
.site{font-size:13px;letter-spacing:.06em;color:var(--brand);min-height:18px}
h1{font-size:21px;font-weight:500;margin:8px 0 18px}
input,button{width:100%;height:46px;border-radius:10px;font-family:inherit;box-sizing:border-box}
input{border:1px solid var(--line2);background:var(--surface);color:var(--tx);font-size:16px;text-align:center}
button{margin-top:10px;border:0;background:var(--brand);color:var(--bg);font-size:15px;font-weight:600;cursor:pointer}
.err{color:var(--dfg);font-size:13px;margin-top:10px;min-height:18px}
</style></head><body><div class="wrap">__BODY__</div></body></html>"""
LOGIN_FORM = """<form class="card" method="post" action="/login">
<div class="site" dir="ltr">__SITE__</div><h1>בריאות האתר</h1>
<input name="p" type="password" placeholder="סיסמה" aria-label="סיסמה" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus>
<button type="submit">כניסה</button><div class="err" role="alert">__ERROR__</div></form>"""


# ---------------------------------------------------------------- who is asking

class Viewer(NamedTuple):
    role: str                   # owner | staff | vendor | share
    who: str                    # the name in the login log and on "seen by"
    no_alerts: bool = False     # a vendor who must not see alerts

    @property
    def outsider(self):
        return self.role in ("vendor", "share")

    @property
    def screen_role(self):
        """window.SH_ROLE (spec §6.7). It only hides controls; the rules themselves are enforced in this file."""
        if self.role == "share":
            return {"share": True}
        if self.role == "vendor":
            return {"readonly": True, "noAlerts": True} if self.no_alerts else {"readonly": True}
        return {}


SHARE_LINK = Viewer("share", "share")


def _norm(password):
    """Passwords are compared trimmed and case-insensitively: phone keyboards capitalize the first letter."""
    return (password or "").strip().casefold()


def _same(a, b):
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _token(password):
    """The session cookie: an HMAC keyed with the person's (normalized) password. Changing or deleting
    the password in the host's settings signs that person out at once; there is no session table."""
    return hmac.new(password.encode("utf-8"), SESSION_LABEL, hashlib.sha256).hexdigest()


def _accounts():
    """Everyone who can sign in, as (normalized password, Viewer), least privileged first.

    The order is the collision rule. Two people with one password have one cookie, and both lookups
    below stop at the first match, so a shared password can take rights away but never grant them.
    Read from the environment on every call; an unset or blank password never matches."""
    env = os.environ
    if not _norm(env.get("SH_PASS_OWNER")):
        return []
    quiet = {name.strip().casefold() for name in env.get("SH_VENDOR_NOALERTS", "").split(",")}
    vendors = []
    for variable in sorted(env):
        name = variable.removeprefix(VENDOR_PREFIX)
        if variable.startswith(VENDOR_PREFIX) and name:
            vendors.append((env[variable], Viewer("vendor", name, name.casefold() in quiet)))
    vendors.sort(key=lambda account: not account[1].no_alerts)          # stable: those without alerts first
    people = vendors + [(env.get("SH_PASS_STAFF"), Viewer("staff", "staff")),
                        (env["SH_PASS_OWNER"], Viewer("owner", "owner"))]
    return [(_norm(password), viewer) for password, viewer in people if _norm(password)]


def _by_password(password):
    """(Viewer, cookie value) for a typed password, or None."""
    typed = _norm(password)
    for known, viewer in _accounts():
        if _same(typed, known):
            return viewer, _token(known)
    return None


def _by_cookie(request):
    cookie = request.cookies.get(COOKIE, "")
    for known, viewer in _accounts():
        if _same(cookie, _token(known)):
            return viewer
    return None


def _share_ok(k):
    token = os.environ.get("SH_SHARE_TOKEN", "").strip()     # blank: the share link is switched off
    return bool(token and k) and _same(k, token)


def _viewer(request):
    """Who this request is, or None. On the share page, and on a data call that carries k, only the
    share token counts: the link shows what the link shows, whoever opens it. Nowhere else is k read."""
    path, k = request.url.path, request.query_params.get("k", "")
    if path == "/status" or (k and path in DATA_PATHS):
        return SHARE_LINK if _share_ok(k) else None
    return _by_cookie(request)


def _client_ip(request):
    """The address the sign-in and beacon limits count by (spec §8.2). Behind the host's proxy the socket
    peer is the proxy, and each proxy appends the address it saw to X-Forwarded-For. So the client is
    SH_PROXY_HOPS entries from the right: 1 (the default) for one proxy, 2 where the host has two (its
    documentation says), 0 for no proxy at all, which uses the socket peer. Entries further left are
    whatever the client sent; counting by them would let anybody dodge the limits."""
    hops = os.environ.get("SH_PROXY_HOPS", "1").strip()
    hops = int(hops) if hops.isascii() and hops.isdigit() else 1
    forwarded = [entry.strip() for entry in request.headers.get("x-forwarded-for", "").split(",") if entry.strip()]
    if hops and forwarded:
        return forwarded[-min(hops, len(forwarded))]
    return request.client.host if request.client else "?"


def _is_https(request):
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


# ---------------------------------------------------------------- answers

def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def _html(page, status=200):
    return HTMLResponse(page, status_code=status, headers={"Cache-Control": "no-cache, must-revalidate"})


def _message_page(text, status):
    return _html(PAGE_SHELL.replace("__BODY__", '<p class="card">%s</p>' % html.escape(text)), status)


def _login_page(site_label, error="", status=200):
    form = LOGIN_FORM.replace("__SITE__", html.escape(site_label)).replace("__ERROR__", html.escape(error))
    return _html(PAGE_SHELL.replace("__BODY__", form), status)


def _inline_json(value):
    """JSON that cannot end or derail the inline script it is written into: no "<" (so no "</script>"
    and no "<!--") and no raw U+2028 / U+2029."""
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _screen(config, viewer):
    """The screen file, with this site's configuration and the viewer's role written in at the marker."""
    with open(os.environ.get("SH_SCREEN") or DEFAULT_SCREEN, encoding="utf-8") as f:
        head, marker, tail = f.read().partition(MARKER)
    if not marker:
        raise RuntimeError("the screen file has no %s marker" % MARKER)
    script = "<script>window.SH_CONFIG=%s;window.SH_ROLE=%s;</script>" % (
        _inline_json(config), _inline_json(viewer.screen_role))
    return _html(head + script + tail)


async def _body(request, limit):
    """The request body, or b"" when it is longer than `limit` bytes; it is never buffered beyond that."""
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            return b""
    return data


# ---------------------------------------------------------------- the database and the site's configuration

# One small pool runs every database call. It gives /api/site its parallel parts, and it caps the number
# of Postgres connections, because db.py keeps one per thread.
_pool = ThreadPoolExecutor(max_workers=9, thread_name_prefix="sh-db")


async def rpc(fn, params=None):
    return await asyncio.get_running_loop().run_in_executor(_pool, db.rpc, fn, params)


def _now():
    return datetime.now(timezone.utc)


class Site(NamedTuple):
    tz: ZoneInfo        # the local dates of spec §5.1 are dates in this zone
    hosts: frozenset    # who may send real-user beacons: the site's host and "rum_hosts", without "www."
    private: frozenset  # path segments of pages whose views are never stored, in lower case
    screen: dict        # window.SH_CONFIG


_site_cache = {"at": 0.0, "site": None}


async def _site():
    """What sh_config() says about the site, re-read at most once a minute."""
    if _site_cache["site"] is None or time.monotonic() - _site_cache["at"] >= 60:
        config = await rpc("sh_config")
        try:
            hosts = [config["host"], *config["rum_hosts"]]
            private = {urllib.parse.unquote(name).lower() for name in config["private_paths"]}
            site = Site(ZoneInfo(config["time_zone"]), frozenset(map(_bare, hosts)), frozenset(RUM_PRIVATE | private),
                        config["screen"])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise db.DbError("the site is not configured (%s): load its configuration with sh_setup" % e) from None
        _site_cache.update(site=site, at=time.monotonic())
    return _site_cache["site"]


def _bare(host):
    return host.lower().removeprefix("www.")


def _midnight(day, tz, days=0):
    """00:00 of a local date (plus whole days) as an exact instant. The days are added on the local
    calendar: the day on which the clocks change is 23 or 25 hours long."""
    local = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=days)
    return local.replace(tzinfo=tz).astimezone(timezone.utc)


def window(tz, h=None, f=None, t=None):
    """The time window of a data call (spec §5.1): (from, to, hours), from and to as ISO 8601 in the site's zone."""
    now, start = _now(), None
    if f:
        try:
            start = _midnight(f, tz)
            end = _midnight(t, tz, days=1) if t else now
            if end <= start:
                end = _midnight(f, tz, days=1)
            hours = max(1, int((end - start).total_seconds() // 3600))
        except (ValueError, OverflowError):
            start = None                                     # invalid dates: fall back to h
    if start is None:
        try:
            hours = min(max(int(h), 1), 9600)
        except (TypeError, ValueError):
            hours = 24
        start, end = now - timedelta(hours=hours), now + timedelta(minutes=1)
    return start.astimezone(tz).isoformat(), end.astimezone(tz).isoformat(), hours


async def _window(request):
    q = request.query_params
    return window((await _site()).tz, q.get("h"), q.get("f"), q.get("t"))


def _strategy(request):
    return "desktop" if request.query_params.get("strategy") == "desktop" else "mobile"


def _alerts_for(viewer, rows):
    """A list of alerts as this viewer may see it (spec §8.2)."""
    if viewer.no_alerts:
        return []
    if not viewer.outsider or not isinstance(rows, list):    # a failed part stays {"error": ...}
        return rows
    return [row for row in rows if row.get("kind") in SITE_ALERT_KINDS]


# ---------------------------------------------------------------- the app and its gate

def _start_collectors():
    if os.environ.get("COLLECTORS", "1") == "0":
        log.info("collectors: off (COLLECTORS=0), this process measures nothing")
        return
    try:
        import collectors
        collectors.start()
        log.info("collectors: started")
    except Exception as e:                                   # the screen must come up without them
        log.error("collectors: NOT started, this process measures nothing (%s: %s)", type(e).__name__, e)


@asynccontextmanager
async def lifespan(app):
    accounts, first = _accounts(), {}
    if not accounts:
        log.warning("SH_PASS_OWNER is not set: nobody can sign in")
    for password, viewer in accounts:
        if first.setdefault(password, viewer) is not viewer:
            log.warning("%s and %s have the same password: both sign in as %s (%s)",
                        first[password].who, viewer.who, first[password].who, first[password].role)
    _start_collectors()
    yield


app = FastAPI(title="Site Health", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def gate(request: Request, call_next):
    response = await _admit(request, call_next)
    response.headers["X-Robots-Tag"] = "noindex"
    return response


async def _admit(request, call_next):
    """Every rule that depends on the path and the method (spec §8.2). The handlers only filter what they return."""
    path = request.url.path
    is_data = path.startswith("/api/")
    if path in OPEN_PATHS:
        return await call_next(request)
    viewer = request.state.viewer = _viewer(request)
    if viewer is None:
        if path == "/status":
            return _message_page(TEXT_BAD_LINK, 403)
        return _json({"error": "auth"}, 401) if is_data else RedirectResponse("/login", status_code=303)
    if not viewer.outsider or (request.method == "GET" and path in OUTSIDER_PATHS):
        return await call_next(request)
    return _json({"error": "auth"}, 403) if is_data else RedirectResponse("/site", status_code=303)


@app.exception_handler(db.DbError)
async def database_failed(request: Request, error: db.DbError):
    log.warning("%s: %s", request.url.path, error)
    if request.url.path.startswith("/api/"):
        return _json({"error": str(error)}, 502)
    return _message_page(TEXT_NO_DATA, 502)


# ---------------------------------------------------------------- pages and sign-in

@app.get("/")
async def home():
    return RedirectResponse("/site", status_code=303)


@app.get("/site")
async def site_page(request: Request):
    return _screen((await _site()).screen, request.state.viewer)


@app.get("/status")
async def share_page(request: Request):
    config = dict((await _site()).screen, shareKey=request.query_params["k"])
    return _screen(config, request.state.viewer)


async def _site_label():
    try:
        return (await _site()).screen.get("siteLabel", "")
    except db.DbError:
        return ""                                            # signing in does not depend on the database


@app.get("/login")
async def login_page(request: Request):
    if _by_cookie(request):
        return RedirectResponse("/", status_code=303)
    return _login_page(await _site_label())


_failures = deque(maxlen=5000)       # (time, address) of failed sign-ins, oldest first; bounded on purpose


def _recent_failures(ip):
    now = time.monotonic()
    while _failures and now - _failures[0][0] >= FAILURE_WINDOW:
        _failures.popleft()
    return sum(1 for _, address in _failures if address == ip)


@app.post("/login")
async def login(request: Request):
    ip = _client_ip(request)
    if _recent_failures(ip) >= MAX_FAILURES:                 # the password is not even looked at
        return _login_page(await _site_label(), TEXT_BLOCKED, 429)
    form = urllib.parse.parse_qs((await _body(request, 4096)).decode("utf-8", "replace"))
    found = _by_password(form.get("p", [""])[0])
    try:
        await rpc("sh_login_log_add", {"p_ip": ip, "p_ok": found is not None, "p_who": found[0].who if found else "?",
                                       "p_ua": request.headers.get("user-agent", "")[:200]})
    except db.DbError as e:
        log.warning("sign-in not logged: %s", e)             # the log is a record, not a gate
    if found is None:
        _failures.append((time.monotonic(), ip))
        return _login_page(await _site_label(), TEXT_WRONG, 401)
    viewer, token = found
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE, token, max_age=86400 * (30 if viewer.role == "vendor" else 365),
                        httponly=True, secure=_is_https(request), samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    return response


# ---------------------------------------------------------------- data calls (spec §5)

@app.get("/api/site")
async def api_site(request: Request):
    p_from, p_to, hours = await _window(request)
    strategy = _strategy(request)
    span = {"p_from": p_from, "p_to": p_to}
    parts = {
        "availability": ("sh_availability", span),
        "availability_series": ("sh_availability_series", span),
        "speed": ("sh_speed", span),
        "speed_series": ("sh_speed_series", dict(span, p_strategy=strategy)),
        "alerts_open": ("sh_alerts_open", None),
        "alerts_recent": ("sh_alerts_range", span),
        "health": ("sh_health", None),
        "product_issues": ("sh_product_issues", None),
        "cert": ("sh_cert", None),
    }

    async def part(key, fn, params):
        try:
            value = await rpc(fn, params)
        except Exception as e:                               # each part fails alone, whatever the failure (spec §5.2)
            log.warning("/api/site: %s failed: %s", key, e)
            return {"error": str(e)}
        return value if key == "cert" else value or []

    values = await asyncio.gather(*(part(key, fn, params) for key, (fn, params) in parts.items()))
    out = {"hours": hours, "from": p_from, "to": p_to, "strategy": strategy, **dict(zip(parts, values))}
    for key in ("alerts_open", "alerts_recent"):
        out[key] = _alerts_for(request.state.viewer, out[key])
    return _json(out)


@app.get("/api/site/now")
async def api_now(request: Request):
    viewer = request.state.viewer
    now = await rpc("sh_now")
    if viewer.outsider:                                      # the count must match the lists this viewer gets
        visible = [] if viewer.no_alerts else _alerts_for(viewer, await rpc("sh_alerts_open") or [])
        now["alerts_open"] = len(visible)
    return _json(now)


def _is_bucket(text):
    """Whether the text is one of the two bucket formats of spec §5: a real day, or a real hour of one."""
    if not BUCKET.fullmatch(text):
        return False
    try:
        datetime.strptime(text, "%Y-%m-%d %H:00" if len(text) > 10 else "%Y-%m-%d")
    except ValueError:
        return False
    return True


@app.get("/api/site/drill")
async def api_drill(request: Request):
    viewer, q = request.state.viewer, request.query_params
    what, bucket, url, alert_id = q.get("what"), q.get("bucket") or None, q.get("url"), q.get("id", "")
    if what not in ("fails", "bucket", "runs", "alert"):
        return _json({"error": "what?"}, 400)
    # A required parameter that is missing or malformed, and a bucket that is not a bucket, match nothing
    # (spec §5.4): the answer is known without asking the database. An id is a number that fits a bigint.
    usable = {"fails": True, "bucket": bucket is not None, "runs": bool(url),
              "alert": alert_id.isascii() and alert_id.isdigit() and len(alert_id) <= 18}[what]
    if not usable or (bucket and what != "alert" and not _is_bucket(bucket)):
        return _json({"rows": []})
    if what == "fails":
        p_from, p_to, _ = await _window(request)
        rows = await rpc("sh_drill_fails", {"p_from": p_from, "p_to": p_to, "p_page": q.get("page") or None,
                                            "p_bucket": bucket})
    elif what == "bucket":
        rows = await rpc("sh_drill_bucket", {"p_bucket": bucket})
    elif what == "runs":
        p_from, p_to, _ = await _window(request)
        rows = await rpc("sh_drill_runs", {"p_from": p_from, "p_to": p_to, "p_url": url,
                                           "p_strategy": _strategy(request), "p_bucket": bucket})
    else:
        rows = []
        if not viewer.no_alerts:
            rows = _alerts_for(viewer, await rpc("sh_drill_alert", {"p_id": int(alert_id)}) or [])
        if viewer.outsider:
            rows = [dict(row, sent=[]) for row in rows]      # who was pushed is the owner's business
    return _json({"rows": rows or []})


@app.get("/api/messages")
async def api_messages(request: Request):
    p_from, p_to, _ = await _window(request)
    return _json({"rows": await rpc("sh_messages", {"p_from": p_from, "p_to": p_to}) or []})


@app.post("/api/alerts/ack")
async def api_ack(request: Request):
    try:
        body = json.loads(await _body(request, 16384))
        listed = body["ids"] if isinstance(body.get("ids"), list) else [body.get("id")]
    except (ValueError, AttributeError):
        listed = []
    ids = []
    for item in listed[:200]:
        if isinstance(item, str) and item.isascii() and item.isdigit():
            item = int(item)                                 # the screen sends ids as it read them from the page
        if type(item) is int and item > 0 and item not in ids:
            ids.append(item)
    if not ids:
        return _json({"error": "bad request"}, 400)
    marked = await rpc("sh_alert_ack", {"p_ids": ids, "p_who": request.state.viewer.who})
    return _json({"ok": True, "n": marked["n"]})


# ---------------------------------------------------------------- real-user beacons (spec §7.7)

_rum_minute = {"minute": None, "seen": {}}       # beacons per address in the current minute; memory only
_rum_queue = []                                  # rows on their way to the database
_rum_busy = False


def _rum_within_rate(ip):
    minute = int(time.monotonic() // 60)
    if _rum_minute["minute"] != minute:
        _rum_minute.update(minute=minute, seen={})
    seen = _rum_minute["seen"]
    seen[ip] = seen.get(ip, 0) + 1
    return seen[ip] <= RUM_PER_MINUTE


async def _rum_row(request):
    """The row to store for one beacon, or None to drop it. The route is public, so every field is
    hostile. Nothing about the visitor is kept: no address, no cookie, no user agent, no query string."""
    if not _rum_within_rate(_client_ip(request)):
        return None
    try:
        site = await _site()
        # A noise filter, not security (anyone can forge a header): a browser that names where the beacon
        # comes from must name this site. Origin decides, the Referer only without one. No header at all,
        # or the Origin "null" of a site with a strict referrer policy, is accepted.
        origin = request.headers.get("origin")
        source = origin or request.headers.get("referer")
        if source and origin != "null" and _bare(urllib.parse.urlsplit(source).hostname or "") not in site.hosts:
            return None
        beacon = json.loads(await _body(request, RUM_MAX_BYTES))
    except (db.DbError, ValueError, RecursionError):         # RecursionError: a body of a thousand brackets
        return None
    if not isinstance(beacon, dict):
        return None
    name, path, lcp = beacon.get("site"), beacon.get("path"), beacon.get("lcp")      # any other field is ignored
    if not (isinstance(name, str) and RUM_SITE.fullmatch(name) and isinstance(path, str) and path.startswith("/")):
        return None
    path = re.split("[?#]", path, maxsplit=1)[0]
    # the segments are compared decoded: a translated slug arrives percent-encoded
    if len(path) > RUM_MAX_PATH or site.private.intersection(urllib.parse.unquote(path).lower().split("/")):
        return None
    if type(lcp) not in (int, float) or not 1 <= lcp <= 60000:      # a view without a measurement is not a row
        return None
    return {"site": name, "path": path, "lcp_ms": round(lcp), "is_test": beacon.get("test") is True}


async def _rum_store(row):
    """Hands rows over in small batches, one database call at a time: a burst of beacons or a slow
    database must not take the workers the screen needs. Beyond RUM_QUEUE waiting rows, new ones are dropped."""
    global _rum_busy
    if len(_rum_queue) < RUM_QUEUE:
        _rum_queue.append(row)
    if _rum_busy:
        return
    _rum_busy = True
    try:
        while _rum_queue:
            batch = _rum_queue[:RUM_BATCH]
            del _rum_queue[:RUM_BATCH]
            try:
                await rpc("sh_rum_add", {"p_rows": batch})
            except db.DbError as e:
                log.warning("%d real-user rows lost: %s", len(batch), e)
    finally:
        _rum_busy = False


@app.post("/m")                                  # a neutral name: content blockers drop paths called "rum" or "beacon"
async def rum(request: Request):
    row = await _rum_row(request)
    # Always 204, also for a dropped beacon. The row is stored after the answer has gone out.
    return Response(status_code=204, background=BackgroundTask(_rum_store, row) if row else None)


# ---------------------------------------------------------------- /health (spec §7.10)

@app.get("/health")
async def health():
    """Always 200. A host restarts a service whose health check fails, and restarting this server
    does not repair a database."""
    state, age = "ok", None
    try:
        await rpc("sh_ping")
        last = next((flow.get("last_at") for flow in await rpc("sh_health") or []
                     if flow.get("flow_name") == PROBE_FLOW), None)
        if last:
            age = int((_now() - datetime.fromisoformat(last)).total_seconds())
    except Exception as e:
        state = str(e) or type(e).__name__
    return _json({"ok": state == "ok", "db": state, "last_probe_age_sec": age})
