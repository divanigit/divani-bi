"""Site Health server: sign-in, roles, the screen and its data calls (spec §5 and §8).

No business logic lives here. Every figure comes from an sh_* SQL function through db.rpc();
this file decides who may see what and turns failures into the statuses of spec §5.7.

    uvicorn server:app --host 0.0.0.0 --port 8000 --no-access-log     # one worker: each would start its own collectors

The share token travels in the query string (spec §8.2), hence --no-access-log. If the flag is forgotten,
this file still keeps query strings out of uvicorn's access log, an encoded "?" (%3F) included. Never run
a live service with --log-level trace: uvicorn then prints every request whole, outside the access log.
Under another server program, turn its access log off.

Environment: SH_PASS_OWNER (without it nobody can sign in), SH_PASS_STAFF, SH_PASS_VENDOR_<NAME>,
SH_VENDOR_NOALERTS, SH_SHARE_TOKEN, SH_PROXY_HOPS, SH_SCREEN, SH_RUM_PER_MINUTE, SH_RUM_PER_DAY,
COLLECTORS, and the database variables of db.py. Everything about the site itself comes from sh_config().
"""
import asyncio
import hashlib
import hmac
import html
import ipaddress
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
SESSION_LABEL = b"site-health-session-v2"
VENDOR_PREFIX = "SH_PASS_VENDOR_"
PASSWORD_MIN, SHARE_TOKEN_MIN = 12, 20                       # shorter: a password is warned about, a token is off
HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = "<!--SH_INJECT-->"
# Sent with every answer (spec §8.2): no search engine, no address of this screen in a Referer header
# (in share mode it holds the token), no page that frames the screen, no guessing of content types.
SECURITY_HEADERS = {"X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                    "X-Content-Type-Options": "nosniff"}

# Access (spec §8.2). An outsider (vendor, share link) gets an allow-list, so a route added later is closed to them.
OPEN_PATHS = {"/login", "/logout", "/health", "/m"}          # answered before any role check
DATA_PATHS = {"/api/site", "/api/site/now", "/api/site/drill"}
OUTSIDER_PATHS = DATA_PATHS | {"/site", "/status"}           # all an outsider may GET; nothing else, no other method
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}        # the only alerts an outsider sees
# Keys of SH_CONFIG that an outsider's page never carries: the menu and the extra buttons hold the
# addresses of the owner's other screens, and the page source is the outsider's to read.
OWNER_ONLY = ("nav", "links")

MAX_FAILURES, FAILURE_WINDOW = 8, 600                        # wrong passwords and share tokens of one address, in seconds
PROBE_FLOW = "בודק זמינות האתר"                              # the flow whose last run is "the last check"

RUM_MAX_BYTES, RUM_MAX_PATH, RUM_PER_ADDRESS, RUM_BATCH, RUM_QUEUE = 1024, 120, 60, 50, 1000
RUM_PER_MINUTE, RUM_PER_DAY = 300, 20000                     # rows stored for all addresses together, unless
                                                             # SH_RUM_PER_MINUTE / SH_RUM_PER_DAY say otherwise
# Path segments that name an account, checkout, order or admin page: such a view is never stored.
# A site adds its own (translated slugs) with "private_paths" in its configuration.
RUM_PRIVATE = {"account", "my-account", "checkout", "checkouts", "order", "orders", "order-received", "order-pay",
               "view-order", "lost-password", "admin", "wp-admin", "wp-login.php"}
RUM_SITE = re.compile(r"[a-z0-9.-]{1,100}")                  # "live" or a host name
# A path that may name a person is never stored: an "@" (an e-mail address), or something that looks like a
# token. The token rule is narrow on purpose, so that ordinary slugs survive: a UUID; or, among the runs of
# letters, digits and "_" (a hyphen ends a run), one of 16 or more hexadecimal characters, or one of 24 or
# more characters that mixes letters and digits.
RUM_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
RUM_RUN = re.compile(r"[A-Za-z0-9_]+")
RUM_HEX = re.compile(r"[0-9A-Fa-f]{16,}")
RUM_UUID = re.compile(r"[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
# A longer path is cut at RUM_MAX_PATH characters (a Hebrew slug, percent-encoded, is six characters a
# letter). Then the end of the cut loses half an escape ("%D" or "%"), and the escapes of a character
# whose UTF-8 bytes were cut off (a lead byte without all of its continuation bytes).
RUM_ASCII = "".join(map(chr, range(0x21, 0x7f)))             # what a path keeps as it is; the rest is encoded
RUM_HALF_ESCAPE = re.compile(r"%[0-9A-Fa-f]?\Z")
RUM_HALF_CHARACTER = re.compile(r"(%[CDcd][0-9A-Fa-f]|%[Ee][0-9A-Fa-f](%[89ABab][0-9A-Fa-f])?"
                                r"|%[Ff][0-7](%[89ABab][0-9A-Fa-f]){0,2})\Z")
BUCKET = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}( [0-9]{2}:00)?")       # a day or an hour, as the charts name them

TEXT_WRONG = "סיסמה שגויה"
TEXT_BLOCKED = "יותר מדי ניסיונות. נסו שוב בעוד עשר דקות."
TEXT_BAD_LINK = "הקישור אינו תקין או שפג תוקפו."
TEXT_NO_DATA = "אין כרגע חיבור לנתונים. נסו שוב בעוד רגע."
TEXT_FAULT = "משהו השתבש. נסו שוב בעוד כמה דקות."

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
    def session_seconds(self):
        """How long a sign-in lasts: 30 days for a vendor, 365 for the owner and staff."""
        return 86400 * (30 if self.role == "vendor" else 365)

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


def _token(password, expires):
    """The session cookie: "<expiry>.<HMAC-SHA256 in hex>". The expiry is in whole seconds since 1970, and
    the HMAC, keyed with the person's (normalized) password, covers a fixed label and that expiry. So the
    server itself ends a session when its time is up, and changing or deleting the password in the host's
    settings signs that person out at once; there is no session table."""
    signed = SESSION_LABEL + b"." + str(expires).encode("ascii")
    return "%d.%s" % (expires, hmac.new(password.encode("utf-8"), signed, hashlib.sha256).hexdigest())


def _vendor_key(name):
    """A vendor's name as it is compared: without case, spaces and hyphens read as "_" (the way the name
    of an environment variable has to spell them)."""
    return re.sub(r"[\s-]+", "_", name.strip()).casefold()


def _vendor_names(env):
    return [variable.removeprefix(VENDOR_PREFIX) for variable in sorted(env)
            if variable.startswith(VENDOR_PREFIX) and variable != VENDOR_PREFIX]


def _unknown_quiet(env):
    """The names in SH_VENDOR_NOALERTS that match no SH_PASS_VENDOR_<NAME> variable."""
    known = {_vendor_key(name) for name in _vendor_names(env)}
    return [name.strip() for name in env.get("SH_VENDOR_NOALERTS", "").split(",")
            if name.strip() and _vendor_key(name) not in known]


def _accounts():
    """Everyone who can sign in, as (normalized password, Viewer), least privileged first.

    The order is the collision rule. Two people with one password have one cookie, and both lookups
    below stop at the first match, so a shared password can take rights away but never grant them.
    Read from the environment on every call; an unset or blank password never matches.

    SH_VENDOR_NOALERTS fails closed: while it holds a name that matches no vendor (a typing mistake
    would otherwise show that vendor the alerts), no vendor sees alerts."""
    env = os.environ
    if not _norm(env.get("SH_PASS_OWNER")):
        return []
    quiet = {_vendor_key(name) for name in env.get("SH_VENDOR_NOALERTS", "").split(",") if name.strip()}
    all_quiet = bool(_unknown_quiet(env))
    vendors = [(env[VENDOR_PREFIX + name], Viewer("vendor", name, all_quiet or _vendor_key(name) in quiet))
               for name in _vendor_names(env)]
    vendors.sort(key=lambda account: not account[1].no_alerts)          # stable: those without alerts first
    people = vendors + [(env.get("SH_PASS_STAFF"), Viewer("staff", "staff")),
                        (env["SH_PASS_OWNER"], Viewer("owner", "owner"))]
    return [(_norm(password), viewer) for password, viewer in people if _norm(password)]


def _by_password(password):
    """(Viewer, that person's normalized password) for a typed password, or None."""
    typed = _norm(password)
    for known, viewer in _accounts():
        if _same(typed, known):
            return viewer, known
    return None


def _by_cookie(request):
    """The Viewer a session cookie belongs to, or None: also when its time is up."""
    cookie = request.cookies.get(COOKIE, "")
    expires = cookie.partition(".")[0]
    if not (expires.isascii() and expires.isdigit() and len(expires) <= 12) or int(expires) <= _now().timestamp():
        return None
    for known, viewer in _accounts():
        if _same(cookie, _token(known, int(expires))):
            return viewer
    return None


def _share_token():
    """The configured share token, or "" when the link is switched off: no token, or one too short to be a secret."""
    token = os.environ.get("SH_SHARE_TOKEN", "").strip()
    return token if len(token) >= SHARE_TOKEN_MIN else ""


def _share_ok(k):
    token = _share_token()
    return bool(token and k) and _same(k, token)


def _link_k(request):
    """The k of a request that only the share token decides: any request for the share page, and a data
    call that carries k. None for every other request; nowhere else is k read."""
    path, k = request.scope["path"], request.query_params.get("k", "")
    return k if path == "/status" or (k and path in DATA_PATHS) else None


def _viewer(request):
    """Who this request is, or None. On the share page, and on a data call that carries k, only the
    share token counts: the link shows what the link shows, whoever opens it."""
    k = _link_k(request)
    if k is not None:
        return SHARE_LINK if _share_ok(k) else None
    return _by_cookie(request)


def _address(text):
    """An IP address in its plain form, or None when the text is not one. A port and brackets are cut
    off ("203.0.113.9:4711", "[2001:db8::1]:443"); an IPv4 address written as IPv6 is read as IPv4."""
    text = text.strip()
    if text.startswith("["):
        text = text[1:].partition("]")[0]
    elif text.count(":") == 1:
        text = text.partition(":")[0]
    try:
        ip = ipaddress.ip_address(text.partition("%")[0])
    except ValueError:
        return None
    return str(ip.ipv4_mapped or ip) if ip.version == 6 else str(ip)


def _client_ip(request):
    """The client's address, for the limits and the login log (spec §8.2). Behind the host's proxy the
    socket peer is the proxy, and each proxy appends the address it saw to X-Forwarded-For. So the client
    is SH_PROXY_HOPS entries from the right: 1 (the default) for one proxy, 2 where the host has two (its
    documentation says), 0 for no proxy at all, which uses the socket peer. Entries further left are
    whatever the client sent; counting by them would let anybody dodge the limits. An entry that is not
    an IP address is not believed either: the socket peer is used. When the peer is no IP address
    either (a Unix socket; or uvicorn, which takes the peer from X-Forwarded-For when the request comes
    from 127.0.0.1), the answer is "?": the text of a header is never stored or counted by."""
    hops = os.environ.get("SH_PROXY_HOPS", "1").strip()
    hops = int(hops) if hops.isascii() and hops.isdigit() else 1
    forwarded = [entry.strip() for entry in request.headers.get("x-forwarded-for", "").split(",") if entry.strip()]
    if hops and forwarded:
        address = _address(forwarded[-min(hops, len(forwarded))])
        if address:
            return address
    return _address(request.client.host if request.client and request.client.host else "") or "?"


def _counted_as(ip):
    """What the limits count an address by: itself, or for IPv6 its /64. One customer of an internet
    provider holds a whole /64, so counting each IPv6 address apart would be no limit at all."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    return str(ipaddress.ip_network((parsed, 64), strict=False)) if parsed.version == 6 else ip


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


def _screen_file():
    """Where the screen is: $SH_SCREEN; else site_health.html next to this file (a deployed copy of the
    backend); else one folder up (this file running inside the kit)."""
    named = os.environ.get("SH_SCREEN", "").strip()
    if named:
        return named
    beside = os.path.join(HERE, "site_health.html")
    return beside if os.path.isfile(beside) else os.path.join(HERE, os.pardir, "site_health.html")


_screen_cache = {"key": None, "parts": None}


def _screen_parts():
    """The screen file as (text before the marker, text after it); read again when the file changes."""
    path = _screen_file()
    stat = os.stat(path)
    key = (path, stat.st_mtime_ns, stat.st_size)
    if _screen_cache["key"] != key:
        with open(path, encoding="utf-8") as f:
            head, marker, tail = f.read().partition(MARKER)
        if not marker:
            raise RuntimeError("the screen file has no %s marker" % MARKER)
        _screen_cache.update(key=key, parts=(head, tail))
    return _screen_cache["parts"]


def _screen_state():
    """"ok", or what is wrong with the screen file, in a word that /health may show to anybody."""
    try:
        _screen_parts()
    except OSError:
        return "missing"
    except RuntimeError:
        return "no marker"
    except ValueError:
        return "not UTF-8"
    return "ok"


def _screen(config, viewer):
    """The screen file, with this site's configuration and the viewer's role written in at the marker.
    An outsider's copy leaves out OWNER_ONLY: hiding the menu on the screen would not keep its
    addresses out of the page source."""
    if viewer.outsider:
        config = {key: value for key, value in config.items() if key not in OWNER_ONLY}
    head, tail = _screen_parts()
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
    names: frozenset    # what a beacon may call its site besides one of those hosts: "live" and "live_hosts"
    rum_off: bool       # the configuration switches real-user measurements off ("off": ["real_users"])
    private: frozenset  # path segments of pages whose views are never stored, in lower case
    screen: dict        # window.SH_CONFIG


_site_cache = {"at": 0.0, "site": None}


async def _site():
    """What sh_config() says about the site, re-read at most once a minute."""
    if _site_cache["site"] is None or time.monotonic() - _site_cache["at"] >= 60:
        config = await rpc("sh_config")
        try:
            hosts = [config["host"], *config["rum_hosts"]]
            names = ["live", *(config.get("live_hosts") or [])]
            private = {urllib.parse.unquote(name).lower() for name in config["private_paths"]}
            site = Site(ZoneInfo(config["time_zone"]), frozenset(map(_bare, hosts)), frozenset(map(str, names)),
                        "real_users" in (config.get("off") or []), frozenset(RUM_PRIVATE | private), config["screen"])
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


class _NoQueryStrings(logging.Filter):
    """Cuts the query string off the request line that uvicorn's access log prints. The share token
    travels in the query string (/status?k=...), and a secret does not belong in the host's log. The
    line is cut at an encoded "?" as well: uvicorn prints the path encoded again, so "/status%3Fk=..."
    (which the router reads as the path "/status?k=...") reaches the log as "/status%3Fk%3D...".
    This covers the access log only: uvicorn's --log-level trace prints every request whole."""
    QUERY = re.compile(r"\?|%3[Ff]")

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(self.QUERY.split(arg, 1)[0] if isinstance(arg, str) else arg for arg in record.args)
        return True


def _quiet_access_log():
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(existing, _NoQueryStrings) for existing in access.filters):
        access.addFilter(_NoQueryStrings())


_quiet_access_log()                              # on import, so it holds whatever the start command is


def _report_configuration():
    """Says at start-up what is wrong or weak in the environment. Names only: never a password or a token."""
    env = os.environ
    accounts, first = _accounts(), {}
    if not accounts:
        log.warning("SH_PASS_OWNER is not set: nobody can sign in")
    for password, viewer in accounts:
        if first.setdefault(password, viewer) is not viewer:
            log.warning("%s and %s have the same password: both sign in as %s (%s)",
                        first[password].who, viewer.who, first[password].who, first[password].role)
        elif len(password) < PASSWORD_MIN:
            log.warning("the password of %s is shorter than %d characters: use a generated one of 16 or more",
                        viewer.who, PASSWORD_MIN)
    unknown = _unknown_quiet(env)
    if unknown:
        log.error("SH_VENDOR_NOALERTS names %s, and no %s<NAME> variable has that name: until this is "
                  "corrected NO vendor sees alerts", ", ".join(unknown), VENDOR_PREFIX)
    for name in _vendor_names(env):
        if name.upper() == "CHECK" or name.upper().startswith("CHECK_"):
            log.warning("%s%s is set: it is the throwaway password of a deployment check; delete it when "
                        "the check is done", VENDOR_PREFIX, name)
    if env.get("SH_SHARE_TOKEN", "").strip() and not _share_token():
        log.warning("SH_SHARE_TOKEN is shorter than %d characters: the share link is switched off "
                    "(OWNER-STEPS.md has the recipe for a good one)", SHARE_TOKEN_MIN)
    if _screen_state() != "ok":
        log.error("the screen file is not usable (%s: %s): /site cannot be served. Copy site_health.html next "
                  "to server.py, or name it in SH_SCREEN", _screen_state(), _screen_file())


@asynccontextmanager
async def lifespan(app):
    _quiet_access_log()                          # again: the server program may have set its logging up since
    _report_configuration()
    _start_collectors()
    yield


app = FastAPI(title="Site Health", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def gate(request: Request, call_next):
    response = await _admit(request, call_next)
    response.headers.update(SECURITY_HEADERS)
    return response


async def _admit(request, call_next):
    """Every rule that depends on the path and the method (spec §8.2). The handlers only filter what they return."""
    # The path as the router matches it. request.url.path is parsed again from a rebuilt address and stops
    # at an encoded "?" or "#", so "/login%3Fx" would pass here as "/login" and reach another route there.
    path = request.scope["path"]
    is_data = path.startswith("/api/")
    if path in OPEN_PATHS:
        return await call_next(request)
    k = _link_k(request)
    address = _counted_as(_client_ip(request)) if k else None
    if k and _recent_failures(address) >= MAX_FAILURES:      # as at sign-in: the token is not even looked at
        return _json({"error": "too many attempts"}, 429) if is_data else _message_page(TEXT_BLOCKED, 429)
    viewer = request.state.viewer = _viewer(request)
    if viewer is None:
        if k:
            _note_failure(address, wrong_k=k)
        if path == "/status":
            return _message_page(TEXT_BAD_LINK, 403)
        return _json({"error": "auth"}, 401) if is_data else RedirectResponse("/login", status_code=303)
    if not viewer.outsider or (request.method == "GET" and path in OUTSIDER_PATHS):
        return await call_next(request)
    return _json({"error": "auth"}, 403) if is_data else RedirectResponse("/site", status_code=303)


@app.exception_handler(db.DbError)
async def database_failed(request: Request, error: db.DbError):
    path = request.scope["path"]
    log.warning("%s: %s", path, error)
    if path.startswith("/api/"):
        return _json({"error": str(error)}, 502)
    return _message_page(TEXT_NO_DATA, 502)


@app.exception_handler(Exception)
async def server_failed(request: Request, error: Exception):
    """Anything unforeseen (a missing screen file, a bug). The server program logs it with its traceback;
    the answer says nothing of it, and carries the headers of every other answer."""
    if request.scope["path"].startswith("/api/"):
        response = _json({"error": "server error"}, 500)
    else:
        response = _message_page(TEXT_FAULT, 500)
    response.headers.update(SECURITY_HEADERS)
    return response


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


# (time, address as _counted_as gives it, mark) of wrong passwords and wrong share tokens, oldest first;
# bounded on purpose
_failures = deque(maxlen=5000)


def _recent_failures(address):
    now = time.monotonic()
    while _failures and now - _failures[0][0] >= FAILURE_WINDOW:
        _failures.popleft()
    return sum(1 for failure in _failures if failure[1] == address)


def _note_failure(address, wrong_k=None):
    """One more failure of this address. A wrong share token counts once per value within the window: an
    old link left open in a tab asks again every minute and must not lock its address out, while somebody
    who guesses sends another value each time. Only a digest of the value is kept."""
    mark = hashlib.sha256(wrong_k.encode("utf-8", "replace")).hexdigest()[:16] if wrong_k else None
    if mark is None or not any(failure[1:] == (address, mark) for failure in _failures):
        _failures.append((time.monotonic(), address, mark))


@app.post("/login")
async def login(request: Request):
    ip = _client_ip(request)
    counted = _counted_as(ip)
    if _recent_failures(counted) >= MAX_FAILURES:            # the password is not even looked at
        return _login_page(await _site_label(), TEXT_BLOCKED, 429)
    form = urllib.parse.parse_qs((await _body(request, 4096)).decode("utf-8", "replace"))
    found = _by_password(form.get("p", [""])[0])
    try:
        await rpc("sh_login_log_add", {"p_ip": ip, "p_ok": found is not None, "p_who": found[0].who if found else "?",
                                       "p_ua": request.headers.get("user-agent", "")[:200]})
    except db.DbError as e:
        log.warning("sign-in not logged: %s", e)             # the log is a record, not a gate
    if found is None:
        _note_failure(counted)
        return _login_page(await _site_label(), TEXT_WRONG, 401)
    viewer, password = found
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE, _token(password, int(_now().timestamp()) + viewer.session_seconds),
                        max_age=viewer.session_seconds, httponly=True, secure=_is_https(request), samesite="lax")
    return response


@app.get("/logout")
async def logout():
    """Removes the cookie from this browser. A copy of it somewhere else stays good until its time is up
    or the password changes: there is no session table to strike it from."""
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
            log.warning("/api/site: %s failed: %s: %s", key, type(e).__name__, e)
            # only a DbError's text is made for a viewer; any other error is named by its type alone
            return {"error": str(e) if isinstance(e, db.DbError) else type(e).__name__}
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
    # A page or an address with a control character names nothing either, and the database could not
    # even take it as a parameter (a NUL).
    page = q.get("page") or None
    usable = {"fails": page is None or _storable(page), "bucket": bucket is not None,
              "runs": bool(url) and _storable(url),
              "alert": alert_id.isascii() and alert_id.isdigit() and len(alert_id) <= 18}[what]
    if not usable or (bucket and what != "alert" and not _is_bucket(bucket)):
        return _json({"rows": []})
    if what == "fails":
        p_from, p_to, _ = await _window(request)
        rows = await rpc("sh_drill_fails", {"p_from": p_from, "p_to": p_to, "p_page": page, "p_bucket": bucket})
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
    # Only a JSON body, said to be one. A page of another origin (the monitored site itself, when the screen
    # lives on a sibling subdomain) can make the owner's browser post text or a form here with his cookie,
    # but not JSON: that needs a preflight, which nothing here answers.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return _json({"error": "bad request"}, 400)
    try:
        body = json.loads(await _body(request, 16384))
        listed = body["ids"] if isinstance(body.get("ids"), list) else [body.get("id")]
    except (ValueError, AttributeError):
        listed = []
    ids = []
    for item in listed[:200]:
        if isinstance(item, str) and item.isascii() and item.isdigit() and len(item) <= 19:
            item = int(item)                                 # the screen sends ids as it read them from the page
        if type(item) is int and 0 < item <= 2 ** 63 - 1 and item not in ids:        # an id fits a bigint
            ids.append(item)
    if not ids:
        return _json({"error": "bad request"}, 400)
    marked = await rpc("sh_alert_ack", {"p_ids": ids, "p_who": request.state.viewer.who})
    return _json({"ok": True, "n": marked["n"]})


# ---------------------------------------------------------------- real-user beacons (spec §7.7)

_rum_minute = {"minute": None, "seen": {}}       # beacons per address in the current minute; memory only
_rum_budget = {"minute": None, "in_minute": 0, "day": None, "in_day": 0, "said": None}       # rows of all addresses
_rum_queue = []                                  # rows on their way to the database
_rum_busy = False


def _rum_within_rate(address):
    minute = int(time.monotonic() // 60)
    if _rum_minute["minute"] != minute:
        _rum_minute.update(minute=minute, seen={})
    seen = _rum_minute["seen"]
    seen[address] = seen.get(address, 0) + 1
    return seen[address] <= RUM_PER_ADDRESS


def _count(name, default):
    text = os.environ.get(name, "").strip()
    return int(text) if text.isascii() and text.isdigit() else default


def _rum_within_budget():
    """Whether one more row may be stored. The limit per address stops one sender; this one stops many
    (a few machines, an IPv6 range, made-up addresses): all of them together store at most
    SH_RUM_PER_MINUTE rows a minute and SH_RUM_PER_DAY rows in 24 hours, so a flood cannot fill the
    database. Counted in memory, from the start of this process; sh_rum_add has its own, wider limit."""
    now, budget = time.monotonic(), _rum_budget
    minute, day = int(now // 60), int(now // 86400)
    if budget["minute"] != minute:
        budget.update(minute=minute, in_minute=0)
    if budget["day"] != day:
        budget.update(day=day, in_day=0)
    per_day = _count("SH_RUM_PER_DAY", RUM_PER_DAY)
    if budget["in_day"] >= per_day:
        if budget["said"] != day:                # once, not per beacon
            budget["said"] = day
            log.warning("real-user measurements: the %d rows of SH_RUM_PER_DAY are used up; "
                        "further ones are dropped for up to 24 hours", per_day)
        return False
    if budget["in_minute"] >= _count("SH_RUM_PER_MINUTE", RUM_PER_MINUTE):
        return False
    budget["in_minute"] += 1
    budget["in_day"] += 1
    return True


def _may_name_someone(decoded):
    """Whether a path (percent-decoded) holds an "@" or something that looks like a token (see RUM_UUID)."""
    if "@" in decoded or RUM_UUID.search(decoded):
        return True
    return any(RUM_HEX.fullmatch(run) or (len(run) >= 24 and re.search("[A-Za-z]", run) and re.search("[0-9]", run))
               for run in RUM_RUN.findall(decoded))


def _storable(text):
    """Whether the database can store the text, or take it as a parameter: no control character (a
    NUL fails the whole batch it travels in) and nothing that cannot be written as UTF-8 (half of a
    surrogate pair)."""
    try:
        text.encode("utf-8")
    except UnicodeError:
        return False
    return not RUM_CONTROL.search(text)


def _cut_path(path):
    """The path as it is stored: in the form a browser sends (a character outside printable ASCII
    percent-encoded, so a row's path is never more bytes than characters), and at most RUM_MAX_PATH
    characters. A cut never ends inside a "%XX" escape or inside a character that the escapes before
    it begin; sh_rum_add cuts the same way."""
    path = urllib.parse.quote(path, safe=RUM_ASCII)
    if len(path) <= RUM_MAX_PATH:
        return path
    return RUM_HALF_CHARACTER.sub("", RUM_HALF_ESCAPE.sub("", path[:RUM_MAX_PATH]))


async def _rum_row(request):
    """The row to store for one beacon, or None to drop it. The route is public, so every field is
    hostile. Nothing about the visitor is kept: no address, no cookie, no user agent, no query string."""
    if not _rum_within_rate(_counted_as(_client_ip(request))):
        return None
    try:
        site = await _site()
        if site.rum_off:                         # a part that is switched off stores nothing
            return None
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
    # The name is shown on the screen of every viewer ("מקור: ..."), so it is never the sender's own text:
    # "live" (and what the configuration lists in live_hosts), or one of the configured hosts.
    if name not in site.names and name.removeprefix("www.") not in site.hosts:
        return None
    path = re.split("[?#]", path, maxsplit=1)[0]
    if not _storable(path):
        return None
    # Judged whole, before the cut: what lies beyond the stored part may name a person or a private page.
    decoded = urllib.parse.unquote(path)         # compared decoded: a translated slug arrives percent-encoded
    if site.private.intersection(decoded.lower().split("/")) or not _storable(decoded) or _may_name_someone(decoded):
        return None
    if type(lcp) not in (int, float) or not 1 <= lcp <= 60000:      # a view without a measurement is not a row
        return None
    if not _rum_within_budget():                 # last: only a row that would be stored uses the budget up
        return None
    return {"site": name, "path": _cut_path(path), "lcp_ms": round(lcp), "is_test": beacon.get("test") is True}


async def _rum_store(row):
    """Hands rows over in small batches, one database call at a time: a burst of beacons or a slow
    database must not take the workers the screen needs. Beyond RUM_QUEUE waiting rows, new ones are dropped.
    A batch that the database refuses for its data is sent again row by row; one that fails because the
    database is not there is not."""
    global _rum_busy
    if len(_rum_queue) < RUM_QUEUE:
        _rum_queue.append(row)
    if _rum_busy:
        return
    _rum_busy = True
    try:
        alone = []                               # the rows of a batch the database refused, last one first
        while alone or _rum_queue:
            if alone:
                batch = [alone.pop()]
            else:
                batch = _rum_queue[:RUM_BATCH]
                del _rum_queue[:RUM_BATCH]
            try:
                await rpc("sh_rum_add", {"p_rows": batch})
            except db.DbError as e:
                if e.answered and len(batch) > 1:            # refused for its data: one bad row must not cost
                    alone = batch[::-1]                      # the others, so they go again one by one
                else:
                    log.warning("real-user rows lost: %d (%s)", len(batch), e)
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
    state, age, screen = "ok", None, _screen_state()
    try:
        await rpc("sh_ping")
        last = next((flow.get("last_at") for flow in await rpc("sh_health") or []
                     if flow.get("flow_name") == PROBE_FLOW), None)
        if last:
            age = int((_now() - datetime.fromisoformat(last)).total_seconds())
    except db.DbError as e:
        state = str(e) or "DbError"              # a DbError's text is made to be shown: no host, user or key
    except Exception as e:                       # this route is public: of any other error, its type alone
        state = type(e).__name__
    return _json({"ok": state == "ok" and screen == "ok", "db": state, "screen": screen, "last_probe_age_sec": age})
