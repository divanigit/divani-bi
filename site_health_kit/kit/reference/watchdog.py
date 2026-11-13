#!/usr/bin/env python3
"""Site Health: who watches the watcher, on any host (spec §7.10, option 3).

If the worker that probes the site dies, nothing inside it can say so. This small program stands
outside. It reads the dashboard's public /health and pushes to the same ntfy topic as the worker:

    "המדידה נעצרה: בודק זמינות האתר"    when the last full probe round is more than 10 minutes old, or
                                        when /health has given no usable answer for 10 minutes
    "חזר לתקין: בודק זמינות האתר"       when probe rounds arrive again

It needs the Python standard library only: no database, no package, no other file of the kit. Copy
this one file to a machine that does not stop when the dashboard's host stops, and run it there:

    python3 watchdog.py --dashboard https://dash.example.co.il            one look (cron: every 5 minutes)
    python3 watchdog.py --dashboard https://dash.example.co.il --loop     a look every minute, until stopped

The topic comes from the environment and from nowhere else, and is never printed:

    NTFY_TOPIC       the topic, the same value as the worker's (required)
    NTFY_URL         the ntfy server (default https://ntfy.sh)
    NTFY_TOKEN       optional access token of a reserved topic or a self-hosted server
    DASHBOARD_URL    may stand in for --dashboard

Between two looks it remembers whether its alert is open, and since when, in one small JSON file
that holds no secret: --state FILE (default: site-health-watchdog.json in the system's temporary
folder). With --loop that is kept in memory, unless --state names a file.

Exit code of one look: 0 when all is well or a push went out, 1 when a push was owed and ntfy did
not accept it (the next look tries again), 2 for a wrong command line or a missing topic. A look
prints one line only when something is not as it should be; --verbose prints one for every look.

Its two pushes are not in the screen's message log: this program never touches the database.
"""
import argparse
import http.client
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

FLOW = "בודק זמינות האתר"            # the flow whose silence this is about, as the screen names it
LIMIT = 600                          # seconds without a full probe round, or without an answer of /health
TRIES, TRY_PAUSE = 3, 5              # one look asks /health up to three times, five seconds apart
TIMEOUT = 15                         # seconds for one request
LOOP_EVERY = 60                      # seconds between two looks of --loop
STATE_NAME = "site-health-watchdog.json"
BLIND = {"silent": "המסך של בריאות האתר לא עונה כבר ",        # /health did not answer
         "no data": "אין חיבור לנתונים כבר "}                  # it answered, and its database did not


def span(seconds, down=False):
    """A length of time in everyday Hebrew, the same words as the worker's alerts (sh_span): whole
    minutes, the nearest one or (down) the last full one, and never less than one."""
    m = max(int(seconds // 60 if down else seconds / 60 + 0.5), 1)
    if m == 1:
        return "דקה"
    if m == 2:
        return "שתי דקות"
    if m == 60:
        return "שעה"
    if m < 120:
        return "%d דקות" % m
    if m < 180:
        return "שעתיים"
    if m == 1440:
        return "יום"
    if m < 2880:
        return "%d שעות" % (m // 60)
    if m < 4320:
        return "יומיים"
    return "%d ימים" % (m // 1440)


def rest(seconds):
    time.sleep(seconds)


def read_health(dashboard, tries=None, pause=None):
    """What /health says: ("age", seconds since the last full probe round), ("new", None) when no
    round was ever stored, ("silent", why) when it gave no answer, ("no data", why) when it
    answered and its database did not. Asked up to `tries` times: one lost request is not a fault."""
    found = ("silent", "no answer")
    for attempt in range(TRIES if tries is None else tries):
        if attempt:
            rest(TRY_PAUSE if pause is None else pause)
        request = urllib.request.Request(dashboard.rstrip("/") + "/health", headers={
            "User-Agent": "SiteHealthWatchdog/1.0", "Accept": "application/json", "Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                health = json.loads(response.read(100_000))
        except urllib.error.HTTPError as e:
            found = ("silent", "HTTP %d" % e.code)
            continue
        except (OSError, ValueError, http.client.HTTPException) as e:      # no route, TLS, timeout, not JSON
            found = ("silent", type(getattr(e, "reason", None) or e).__name__)
            continue
        if not isinstance(health, dict) or "last_probe_age_sec" not in health:
            found = ("silent", "the answer is not the one of /health")
            continue
        if health.get("db") != "ok":
            found = ("no data", "the dashboard's database does not answer")
            continue
        age = health["last_probe_age_sec"]
        if age is None:
            return "new", None
        if isinstance(age, (int, float)) and not isinstance(age, bool):
            return "age", age
        found = ("silent", "the answer is not the one of /health")
    return found


def decide(health, state, now):
    """What one look comes to: (the state to remember, the push that is owed or None, a line for the log).
    state is {"open": is the alert open, "since": when the measuring stopped, "blind": since when
    /health gives no usable answer}; times are epoch seconds. A push is {"title", "message", "priority", "tags"}."""
    kind, value = health
    was_open, since, blind = bool(state.get("open")), state.get("since"), state.get("blind")
    stopped = "המדידה נעצרה: %s" % FLOW
    if kind == "new":
        return {"open": was_open, "since": since, "blind": None}, None, "no probe round was stored yet"
    if kind == "age" and value <= LIMIT:
        if not was_open:
            return {"open": False, "since": None, "blind": None}, None, "the last probe round is %d seconds old" % value
        push = {"title": "חזר לתקין: %s" % FLOW, "message": "%s\nנמשך %s" % (stopped, span(now - (since or now))),
                "priority": 2, "tags": ["white_check_mark"]}
        return {"open": False, "since": None, "blind": None}, push, "probe rounds arrive again"
    if kind == "age":
        said = "the last probe round is %d seconds old" % value
        if was_open:
            return {"open": True, "since": since, "blind": None}, None, said + " (the alert is open)"
        push = {"title": stopped, "message": "אין מדידה כבר " + span(value, down=True), "priority": 4,
                "tags": ["rotating_light"]}
        return {"open": True, "since": now - value, "blind": None}, push, said
    # "silent" or "no data": an alarm only when it lasts, counted from the first look that met it
    blind = blind or now
    said = "/health gives no usable answer (%s) for %d seconds" % (value, now - blind)
    if was_open or now - blind < LIMIT:
        return {"open": was_open, "since": since, "blind": blind}, None, said
    push = {"title": stopped, "message": BLIND[kind] + span(now - blind, down=True), "priority": 4,
            "tags": ["rotating_light"]}
    return {"open": True, "since": blind, "blind": blind}, push, said


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect of the push is not followed: urllib would repeat it as a GET, without the message,
    and the page it then gets would look like "accepted"."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                             # urllib then raises the 3xx as an HTTPError


def publish(push, dashboard):
    """One push to the topic of the environment: True when ntfy accepted it. JSON to the server's
    root, as the worker sends it. Neither the topic nor the token is ever printed."""
    env = os.environ
    body = dict(push, topic=env["NTFY_TOPIC"].strip(), click=dashboard.rstrip("/") + "/site")
    headers = {"Content-Type": "application/json", "User-Agent": "SiteHealthWatchdog/1.0"}
    if env.get("NTFY_TOKEN", "").strip():
        headers["Authorization"] = "Bearer " + env["NTFY_TOKEN"].strip()
    request = urllib.request.Request((env.get("NTFY_URL", "").strip() or "https://ntfy.sh").rstrip("/") + "/",
                                     data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            response.read(2000)
            return True
    except urllib.error.HTTPError as e:
        print("watchdog: ntfy refused the push (HTTP %d)" % e.code, file=sys.stderr)
    except (OSError, ValueError, http.client.HTTPException) as e:
        print("watchdog: ntfy could not be reached (%s)" % type(getattr(e, "reason", None) or e).__name__,
              file=sys.stderr)
    return False


class State:
    """What is remembered between two looks: in a file, or (path None) in memory."""

    def __init__(self, path):
        self.path, self.value = path, {}

    def read(self):
        if self.path:
            try:
                with open(self.path, encoding="utf-8") as f:
                    value = json.load(f)
                self.value = value if isinstance(value, dict) else {}
            except (OSError, ValueError):       # no file yet, or a damaged one: start anew
                self.value = {}
        return self.value

    def write(self, value):
        self.value = value
        if self.path:
            scratch = self.path + ".new"
            with open(scratch, "w", encoding="utf-8") as f:
                json.dump(value, f)
            os.replace(scratch, self.path)      # whole, or not at all


def look(dashboard, state, now=None, tries=None, pause=None, verbose=False):
    """One look: read /health, decide, push what is owed, remember. Returns 0, or 1 when a push
    was owed and did not go out. It prints one line when something is not as it should be (cron
    mails whatever a job prints), and always with `verbose`."""
    health = read_health(dashboard, tries, pause)
    before = state.read()
    after, push, said = decide(health, before, time.time() if now is None else now)
    sent = True
    if push:
        sent = publish(push, dashboard)
        if not sent:                            # still owed: the next look decides the same again
            after["open"], after["since"] = bool(before.get("open")), before.get("since")
    state.write(after)
    if verbose or push or after["open"] or after["blind"]:
        print("watchdog: %s%s" % (said, "; pushed \"%s\": %s" % (push["title"], "yes" if sent else "NO") if push else ""),
              flush=True)
    return 0 if sent else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dashboard", default=os.environ.get("DASHBOARD_URL", "").strip(),
                        help="the dashboard's public address, such as https://dash.example.co.il")
    parser.add_argument("--state", help="the file that remembers an open alert between two looks")
    parser.add_argument("--loop", nargs="?", type=int, const=LOOP_EVERY, metavar="SECONDS",
                        help="keep looking, this many seconds apart (default %d)" % LOOP_EVERY)
    parser.add_argument("--verbose", action="store_true", help="print a line for every look, also when all is well")
    args = parser.parse_args(argv)
    if not args.dashboard.startswith(("https://", "http://")):
        parser.error("name the dashboard: --dashboard https://<its address> (or DASHBOARD_URL)")
    if not os.environ.get("NTFY_TOPIC", "").strip():
        parser.error("NTFY_TOPIC is not set: there is nowhere to push to")
    if args.loop is None:
        return look(args.dashboard, State(args.state or os.path.join(tempfile.gettempdir(), STATE_NAME)),
                    verbose=args.verbose)
    state = State(args.state)
    try:
        while True:
            look(args.dashboard, state, verbose=args.verbose)
            rest(max(args.loop, 10))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
