#!/usr/bin/env python3
"""Black-box check of the access rules (spec §8) and of the public routes of a running Site Health server.

    python3 tools/check_access.py https://health.example.co.il [--no-share] [--no-quiet] [--limiter]

It only sends requests and reads answers, so it checks any server that implements the spec, in
whatever language, and the live address as well as a local one. Standard library only.

Secrets come from the environment, never from the command line, and are never printed. The names
are the ones the reference server reads, so one set of variables serves the server and this check:

    SH_PASS_VENDOR_CHECK         the password of a read-only vendor. Required.
    SH_SHARE_TOKEN               the token of the share link. Required, unless --no-share.
    SH_PASS_VENDOR_CHECK_QUIET   the password of a vendor who must see no alerts (on the reference:
                                 SH_VENDOR_NOALERTS=CHECK_QUIET). Required, unless --no-quiet.
    SH_PASS_OWNER                optional. With it the check also reads what the owner gets, to see
                                 the filter at work. It never changes anything as the owner.

A server whose sign-in is not the form of spec §8 takes ready cookies instead, each as "name=value":
SH_COOKIE_VENDOR, SH_COOKIE_QUIET, SH_COOKIE_OWNER.

On the live address use the throwaway vendor password that the owner set for the check (OWNER-STEPS.md,
step 6), and leave out what you do not hold:    python3 tools/check_access.py https://<address> --no-share --no-quiet
With --no-share the check still proves that a made-up token opens nothing.

What it does to the server: nothing that stays. It marks no alert (as an outsider it must be
refused), and the beacons it posts are ones the server must drop. It does fail on purpose: one
wrong password, and one wrong share token on four requests (the reference server counts a wrong
token once per value). A server blocks an address after 8 failures within ten minutes, so run the
check at most twice in ten minutes. --limiter adds nine wrong passwords, each with another made-up
X-Forwarded-For entry, and expects the address to be blocked all the same; after that this address
cannot sign in for ten minutes, so it runs last and only when asked for.

Each line is one check: "ok" or "FAIL". Exit code 0 = every check passed, 1 = at least one failed,
2 = the check could not run (a variable is missing, the server does not answer, a sign-in failed).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE_KINDS = {"down", "slow", "silent", "cert"}              # the only alerts an outsider may see
PARTS = ("availability", "availability_series", "speed", "speed_series", "alerts_open", "alerts_recent", "health",
         "product_issues", "cert")
HEADERS = {"x-robots-tag": "noindex", "referrer-policy": "no-referrer", "x-frame-options": "DENY",
           "x-content-type-options": "nosniff"}
NO_SUCH_ID = 9007199254740991                                # an alert id that does not exist: nothing can be marked
VENDOR_DAYS = 30
TIMEOUT = 30

passed, failed, notes = 0, 0, []


class CannotRun(Exception):
    pass


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("ok    " + name)
    else:
        failed += 1
        print("FAIL  " + name + ("  -> " + str(detail)[:200] if detail != "" else ""))


class Answer:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body
        self.text = body.decode("utf-8", "replace")

    def header(self, name):
        return self.headers.get(name) or ""

    @property
    def location(self):
        """Where a redirect points, as a path."""
        return urllib.parse.urlsplit(self.header("Location")).path

    @property
    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return None

    def cookie(self):
        """The first cookie this answer sets, as ("name=value", its attributes in lower case), or (None, set())."""
        for line in self.headers.get_all("Set-Cookie") or []:
            pair, *attributes = [part.strip() for part in line.split(";")]
            if "=" in pair and pair.split("=", 1)[1].strip('"'):
                return pair, {attribute.lower() for attribute in attributes}
        return None, set()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None                                          # a redirect is an answer to look at, not to follow


class Server:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.local = (urllib.parse.urlsplit(self.base).hostname or "") in ("127.0.0.1", "localhost", "::1")
        handlers = [NoRedirect()]
        if self.local:
            handlers.append(urllib.request.ProxyHandler({}))         # a local server is never behind this machine's proxy
        self.opener = urllib.request.build_opener(*handlers)

    def __call__(self, method, path, cookie=None, body=None, kind=None, headers=None):
        """One request. body: bytes, or a dict/list sent as JSON. kind: the Content-Type of the body."""
        if isinstance(body, (dict, list)):
            body, kind = json.dumps(body).encode("utf-8"), kind or "application/json"
        head = dict(headers or {}, **({"Cookie": cookie} if cookie else {}), **({"Content-Type": kind} if kind else {}))
        head.setdefault("User-Agent", "site-health-check-access")
        if method != "GET" and body is None:
            body = b""
        request = urllib.request.Request(self.base + path, data=body, headers=head, method=method)
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                return Answer(response.status, response.headers, response.read(4 << 20))
        except urllib.error.HTTPError as e:                  # every status that is not 2xx arrives here
            return Answer(e.code, e.headers, e.read(4 << 20))
        except (OSError, ValueError) as e:
            reason = getattr(e, "reason", e)
            raise CannotRun("the server does not answer at %s (%s)" % (self.base, type(reason).__name__)) from None


def refused(answer, status):
    return answer.status == status and answer.json == {"error": "auth"}


def alert_rows(site):
    """Every alert of a main answer. A part that failed is {"error": ...}: no rows."""
    lists = [site.get(key) for key in ("alerts_open", "alerts_recent")] if isinstance(site, dict) else []
    return [row for rows in lists if isinstance(rows, list) for row in rows if isinstance(row, dict)]


def kinds_of(site):
    """(the kinds, the ids) of every alert of a main answer."""
    rows = alert_rows(site)
    return {row.get("kind") for row in rows}, {row.get("id") for row in rows if isinstance(row.get("id"), int)}


def injected(page):
    """(SH_CONFIG, SH_ROLE) as the server wrote them into the page, or (None, None)."""
    found = re.search(r"window\.SH_CONFIG=(.*?);window\.SH_ROLE=(.*?);</script>", page, re.S)
    try:
        return (json.loads(found.group(1)), json.loads(found.group(2))) if found else (None, None)
    except ValueError:
        return None, None


def no_menu(who, config):
    """An outsider's page carries no menu (nav) and no extra buttons (links): they hold the addresses of the
    owner's other screens, and hiding them on the screen does not keep them out of the page source."""
    check("%s: the page carries no nav and no links (the owner's other screens)" % who,
          isinstance(config, dict) and not config.get("nav") and not config.get("links"),
          "nav %r, links %r" % ((config or {}).get("nav"), (config or {}).get("links")) if isinstance(config, dict)
          else "no SH_CONFIG in the page")


def sign_in(call, password, who):
    answer = call("POST", "/login", body=urllib.parse.urlencode({"p": password}).encode("utf-8"),
                  kind="application/x-www-form-urlencoded")
    if answer.status == 429:
        raise CannotRun("this address is blocked after too many failed attempts: wait ten minutes and run again")
    cookie, attributes = answer.cookie()
    if answer.status != 303 or not cookie:
        raise CannotRun("the sign-in of the %s failed (status %d): check its variable" % (who, answer.status))
    return cookie, attributes


def session(call, password_name, cookie_name, who):
    """(cookie, attributes of a fresh sign-in or None) for one of the people of the check."""
    if os.environ.get(cookie_name, "").strip():
        return os.environ[cookie_name].strip(), None
    password = os.environ.get(password_name, "")
    if not password.strip():
        return None, None
    return sign_in(call, password, who)


def see_site(call, who, cookie="", k=""):
    """The three data calls as one viewer; returns the main answer (a dict) or None."""
    query = ("&k=" + urllib.parse.quote(k)) if k else ""
    site = call("GET", "/api/site?h=168" + query, cookie)
    data = site.json if isinstance(site.json, dict) else {}
    check("%s: GET /api/site answers 200 with its nine parts" % who,
          site.status == 200 and all(part in data for part in PARTS), "status %d" % site.status)
    check("%s: data answers are not cached (Cache-Control: no-store)" % who, site.header("Cache-Control") == "no-store")
    kinds, _ = kinds_of(data)
    check("%s: only alerts of the four site kinds" % who, kinds <= SITE_KINDS, sorted(map(str, kinds - SITE_KINDS)))
    for attempt in (1, 2):                                   # an alert may open between the two reads: once more
        now = call("GET", "/api/site/now" + ("?" + query[1:] if query else ""), cookie)
        count = (now.json or {}).get("alerts_open") if isinstance(now.json, dict) else None
        listed = data.get("alerts_open")
        if now.status != 200 or not isinstance(listed, list) or count == len(listed) or attempt == 2:
            break
        data = call("GET", "/api/site?h=168" + query, cookie).json or {}
    check("%s: GET /api/site/now answers 200, and its count of open alerts is the count of the list this viewer gets"
          % who, now.status == 200 and isinstance(listed, list) and count == len(listed),
          "status %d, count %r, list %r" % (now.status, count, len(listed) if isinstance(listed, list) else listed))
    drill = call("GET", "/api/site/drill?what=fails" + query, cookie)
    check("%s: GET /api/site/drill answers 200 with rows" % who,
          drill.status == 200 and isinstance((drill.json or {}).get("rows"), list), "status %d" % drill.status)
    return data


def no_push_list(call, who, site, cookie="", k=""):
    ids = sorted(kinds_of(site)[1])
    if not ids:
        notes.append("%s: no alert in the last 7 days, so the alert sheet could not be looked at" % who)
        return
    query = ("&k=" + urllib.parse.quote(k)) if k else ""
    rows = (call("GET", "/api/site/drill?what=alert&id=%d%s" % (ids[-1], query), cookie).json or {}).get("rows")
    check("%s: the alert sheet does not say who was pushed (sent is empty)" % who,
          isinstance(rows, list) and len(rows) == 1 and rows[0].get("sent") == [], "rows: %r" % (
              [row.get("sent") for row in rows] if isinstance(rows, list) else rows))


def nobody(call, cookie_name):
    health = call("GET", "/health")
    body = health.json if isinstance(health.json, dict) else {}
    check("nobody: GET /health answers 200 with ok, db and last_probe_age_sec",
          health.status == 200 and isinstance(body.get("ok"), bool) and "db" in body and "last_probe_age_sec" in body,
          "status %d, keys %s" % (health.status, sorted(body)))
    if health.status == 200 and body.get("ok") is not True:
        notes.append("/health says ok=false (db: %s%s): the access rules were checked all the same"
                     % (str(body.get("db"))[:80], ", screen: %s" % body["screen"] if "screen" in body else ""))
    answers = {"GET /health": health}
    for text in (b"not a beacon", b"{}"):
        beacon = call("POST", "/m", body=text, kind="text/plain;charset=UTF-8", cookie=cookie_name + "=made-up")
        check("nobody: POST /m answers 204 with an empty body (%s)" % text.decode(),
              beacon.status == 204 and not beacon.body, "status %d" % beacon.status)
    answers["POST /m"] = beacon
    check("nobody: GET /m is not a page", call("GET", "/m").status in (404, 405))
    for path in ("/", "/site", "/anything-else"):
        page = call("GET", path)
        check("nobody: GET %s goes to the sign-in page" % path, page.status == 303 and page.location == "/login",
              "status %d" % page.status)
    answers["GET /site"] = page
    login = call("GET", "/login")
    check("nobody: GET /login answers 200", login.status == 200, "status %d" % login.status)
    answers["GET /login"] = login
    for path in ("/api/site", "/api/site/now", "/api/site/drill?what=fails", "/api/messages", "/api/anything-else"):
        data = call("GET", path)
        check("nobody: GET %s answers 401 {\"error\": \"auth\"}" % path.split("?")[0], refused(data, 401),
              "status %d" % data.status)
    answers["GET /api/site"] = data
    check("nobody: POST /api/alerts/ack answers 401",
          refused(call("POST", "/api/alerts/ack", body={"ids": [NO_SUCH_ID]}), 401))
    forged = cookie_name + "=1999999999." + "0" * 64
    check("nobody: a made-up session cookie opens nothing",
          refused(call("GET", "/api/site", forged), 401) and call("GET", "/site", forged).location == "/login")
    wrong = call("POST", "/login", body=b"p=not-the-password-of-anybody", kind="application/x-www-form-urlencoded")
    if wrong.status == 429:
        raise CannotRun("this address is blocked after too many failed attempts: wait ten minutes and run again")
    check("nobody: a wrong password answers 401 and sets no cookie", wrong.status == 401 and wrong.cookie()[0] is None,
          "status %d" % wrong.status)
    answers["POST /login"] = wrong
    for name, answer in answers.items():
        missing = [header for header, value in HEADERS.items() if answer.header(header) != value]
        check("headers: %s carries X-Robots-Tag, Referrer-Policy, X-Frame-Options and X-Content-Type-Options" % name,
              not missing, "missing or different: " + ", ".join(missing))


def vendor(call, cookie, attributes, https):
    if attributes is not None:
        age = next((int(a.split("=")[1]) for a in attributes if re.fullmatch(r"max-age=[0-9]+", a)), None)
        check("vendor: the session cookie is HttpOnly, SameSite=Lax%s and lasts at most %d days"
              % (", Secure" if https else "", VENDOR_DAYS),
              "httponly" in attributes and "samesite=lax" in attributes and (not https or "secure" in attributes)
              and age is not None and age <= VENDOR_DAYS * 86400,
              sorted(a for a in attributes if not a.startswith("expires")))
    page = call("GET", "/site", cookie)
    config, role = injected(page.text)
    role = role or {}
    check("vendor: GET /site answers 200 and the page says read-only",
          page.status == 200 and role.get("readonly") is True and not role.get("share"),
          "status %d, role %r" % (page.status, role))
    no_menu("vendor", config)
    site = see_site(call, "vendor", cookie)
    no_push_list(call, "vendor", site, cookie)
    check("vendor: GET /api/messages answers 403 {\"error\": \"auth\"}",
          refused(call("GET", "/api/messages", cookie), 403))
    check("vendor: POST /api/alerts/ack answers 403 {\"error\": \"auth\"}",
          refused(call("POST", "/api/alerts/ack", cookie, body={"ids": [NO_SUCH_ID]}), 403))
    for method, path in (("POST", "/api/site"), ("POST", "/api/site/now"), ("DELETE", "/api/alerts/ack"),
                         ("GET", "/api/anything-else")):
        check("vendor: %s %s answers 403" % (method, path), refused(call(method, path, cookie), 403))
    for method, path in (("GET", "/anything-else"), ("POST", "/site")):
        page = call(method, path, cookie)
        check("vendor: %s %s goes back to /site" % (method, path), page.status == 303 and page.location == "/site",
              "status %d" % page.status)
    check("vendor: the share page without a token answers 403, also to somebody who is signed in",
          call("GET", "/status", cookie).status == 403)
    return site


def quiet(call, cookie, known_ids):
    config, role = injected(call("GET", "/site", cookie).text)
    role = role or {}
    check("vendor without alerts: the page says so (noAlerts)",
          role.get("noAlerts") is True and role.get("readonly") is True, "role %r" % role)
    no_menu("vendor without alerts", config)
    site = call("GET", "/api/site?h=168", cookie).json or {}
    check("vendor without alerts: both alert lists are empty",
          site.get("alerts_open") == [] and site.get("alerts_recent") == [],
          "open %r, recent %r" % (site.get("alerts_open"), site.get("alerts_recent")))
    now = call("GET", "/api/site/now", cookie).json or {}
    check("vendor without alerts: the count of open alerts is 0", now.get("alerts_open") == 0,
          repr(now.get("alerts_open")))
    for alert in sorted(known_ids)[-2:] or [1]:
        rows = (call("GET", "/api/site/drill?what=alert&id=%d" % alert, cookie).json or {}).get("rows")
        check("vendor without alerts: the alert sheet of alert %d has no rows" % alert, rows == [],
              "rows: %r" % (rows if rows is None else len(rows)))
    check("vendor without alerts: GET /api/messages answers 403", refused(call("GET", "/api/messages", cookie), 403))


def share(call, token):
    k = "?k=" + urllib.parse.quote(token)
    page = call("GET", "/status" + k)
    config, role = injected(page.text)
    check("share link: /status?k=<token> answers 200, as a share page, and sets no cookie",
          page.status == 200 and (role or {}).get("share") is True and page.cookie()[0] is None,
          "status %d, role %r" % (page.status, role))
    check("share link: the page carries the token for its data calls (shareKey)",
          (config or {}).get("shareKey") == token)
    no_menu("share link", config)
    site = see_site(call, "share link", k=token)
    no_push_list(call, "share link", site, k=token)
    check("share link: GET /api/messages answers 401", refused(call("GET", "/api/messages" + k), 401))
    check("share link: POST /api/alerts/ack answers 401",
          refused(call("POST", "/api/alerts/ack" + k, body={"ids": [NO_SUCH_ID]}), 401))
    check("share link: POST /api/site is refused", call("POST", "/api/site" + k).status in (401, 403, 405))
    for path in ("/site", "/"):
        answer = call("GET", path + k)
        check("share link: the token is not a sign-in (GET %s goes to /login)" % path,
              answer.status == 303 and answer.location == "/login", "status %d" % answer.status)
    return site


def wrong_token(call, wrong, vendor_cookie):
    k = "?k=" + urllib.parse.quote(wrong)
    page = call("GET", "/status" + k)
    if page.status == 429:
        raise CannotRun("this address is blocked after too many failed attempts: wait ten minutes and run again")
    check("share link: a wrong token answers 403 and shows nothing", page.status == 403 and "SH_CONFIG" not in page.text,
          "status %d" % page.status)
    check("share link: a wrong token on a data call answers 401", refused(call("GET", "/api/site" + k), 401))
    check("share link: a wrong token is refused even with a good session cookie",
          refused(call("GET", "/api/site" + k, vendor_cookie), 401)
          and call("GET", "/status" + k, vendor_cookie).status == 403)
    check("share link: /status without a token answers 403", call("GET", "/status").status == 403)


def owner(call, cookie, outsiders, token):
    config = injected(call("GET", "/site", cookie).text)[0] or {}
    if not (config.get("nav") or config.get("links")):
        notes.append("the owner's page has no menu (nav) and no extra buttons (links) either, so \"carries no nav and "
                     "no links\" could not be seen at work")
    messages = call("GET", "/api/messages", cookie)
    check("owner: GET /api/messages answers 200 with rows",
          messages.status == 200 and isinstance((messages.json or {}).get("rows"), list), "status %d" % messages.status)
    hidden = {row.get("id") for row in alert_rows(call("GET", "/api/site?h=168", cookie).json)
              if row.get("kind") not in SITE_KINDS}
    for who, seen in outsiders.items():
        check("%s: sees none of the alerts of other kinds that the owner sees" % who, not kinds_of(seen)[1] & hidden)
    if token:
        shared = call("GET", "/api/site?h=168&k=" + urllib.parse.quote(token), cookie)
        check("share link: with the token even the owner gets what the link shows, not more",
              shared.status == 200 and kinds_of(shared.json)[0] <= SITE_KINDS)
    if not hidden:
        notes.append("the owner has no alert of another kind in the last 7 days, so the filter could not be seen "
                     "at work")


def limiter(call):
    statuses = []
    for attempt in range(9):
        answer = call("POST", "/login", body=b"p=limiter-check-wrong-password",
                      kind="application/x-www-form-urlencoded",
                      headers={"X-Forwarded-For": "198.51.100.%d" % (attempt + 1)})
        statuses.append(answer.status)
    blocked = statuses.index(429) if 429 in statuses else None
    held = blocked is not None and set(statuses[:blocked]) <= {401} and set(statuses[blocked:]) == {429}
    check("limiter: wrong passwords with made-up X-Forwarded-For entries still get this address blocked (429)",
          held, statuses)
    if held:
        notes.append("--limiter: this address is now refused at sign-in for ten minutes")
    elif call.local:
        notes.append("--limiter against this machine itself: uvicorn believes X-Forwarded-For when the request comes "
                     "from 127.0.0.1, so this check says little here. Run it against the live address, or start the "
                     "local server with --no-proxy-headers and SH_PROXY_HOPS=0")


def main():
    parser = argparse.ArgumentParser(description="Black-box check of the access rules of a Site Health server.")
    parser.add_argument("base", help="the address of the server, such as https://health.example.co.il")
    parser.add_argument("--no-share", action="store_true", help="the share token is not at hand, or the link is off")
    parser.add_argument("--no-quiet", action="store_true", help="there is no vendor without alerts to check with")
    parser.add_argument("--limiter", action="store_true",
                        help="also check the sign-in limit (blocks this address for ten minutes)")
    args = parser.parse_args()
    if not re.fullmatch(r"https?://[^/?#]+/?", args.base):
        raise CannotRun("the address must look like https://health.example.co.il (no path, no query)")
    call = Server(args.base)
    token = "" if args.no_share else os.environ.get("SH_SHARE_TOKEN", "").strip()

    def unset(*names):
        return not any(os.environ.get(name, "").strip() for name in names)

    missing = []
    if unset("SH_PASS_VENDOR_CHECK", "SH_COOKIE_VENDOR"):
        missing.append("SH_PASS_VENDOR_CHECK (or SH_COOKIE_VENDOR)")
    if not args.no_share and not token:
        missing.append("SH_SHARE_TOKEN (or pass --no-share)")
    if not args.no_quiet and unset("SH_PASS_VENDOR_CHECK_QUIET", "SH_COOKIE_QUIET"):
        missing.append("SH_PASS_VENDOR_CHECK_QUIET or SH_COOKIE_QUIET (or pass --no-quiet)")
    if missing:
        raise CannotRun("set " + "; ".join(missing))

    vendor_cookie, attributes = session(call, "SH_PASS_VENDOR_CHECK", "SH_COOKIE_VENDOR", "vendor")
    nobody(call, vendor_cookie.split("=", 1)[0])
    seen = {"vendor": vendor(call, vendor_cookie, attributes, args.base.startswith("https://"))}
    if token:
        seen["share link"] = share(call, token)
        wrong_token(call, token[:-1] + ("a" if token[-1] != "a" else "b"), vendor_cookie)
    else:
        wrong_token(call, "made-up-token-0123456789-abcdefghij", vendor_cookie)
    known = {alert for site in seen.values() for alert in kinds_of(site)[1]}
    owner_cookie, _ = session(call, "SH_PASS_OWNER", "SH_COOKIE_OWNER", "owner")
    if owner_cookie:
        known |= kinds_of(call("GET", "/api/site?h=168", owner_cookie).json)[1]
    if not args.no_quiet:
        quiet_cookie, _ = session(call, "SH_PASS_VENDOR_CHECK_QUIET", "SH_COOKIE_QUIET", "vendor without alerts")
        quiet(call, quiet_cookie, known)
    if owner_cookie:
        owner(call, owner_cookie, seen, token)
    if args.limiter:
        limiter(call)


if __name__ == "__main__":
    try:
        main()
    except CannotRun as problem:
        print("COULD NOT RUN: %s" % problem)
        sys.exit(2)
    for note in notes:
        print("note  " + note)
    print("\n%d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
