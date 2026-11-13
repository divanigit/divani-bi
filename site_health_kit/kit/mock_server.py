#!/usr/bin/env python3
"""Mock backend for the site-health screen. Standard library only.

It serves the screen and answers every data call with realistic, deterministic fake data,
in exactly the shapes described in spec/05-api-contract.md. Use it to:
  * see the screen working before any real backend exists;
  * compare your real backend's answers with these, field by field;
  * run check_screen.js (the acceptance test of the screen).

    python3 mock_server.py                      # http://localhost:8787/site
    python3 mock_server.py --port 9000 --scenario empty
    python3 mock_server.py --html /path/to/another_site_health.html

Roles (what the real server injects):  /site  owner ·  /site?role=vendor  read-only
  /site?role=noalerts  read-only without alerts ·  /status?k=demo-share-token  share link
Sessions: opening /site sets a mock session cookie. A data call without that cookie and without
  a valid k= answers 401, as a real server does (so a share page that forgets its token gets no data).
Scenarios: incident (default) · ok · empty (fresh install, no data) · error (data source down)
  · hostile (the incident data with HTML and a javascript: address in every text field: the screen
  must show it as text and never build an element, a link or a script from it).
Switch while running:  GET /__scenario?name=empty

This file is a test double. Nothing in it is a design for the real backend.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Jerusalem")          # the site's local time zone: every *_il string and every bucket uses it
SITE = "https://example.co.il"
SHARE_TOKEN = "demo-share-token"
PROBE = [("בית", "/"), ("קטגוריה", "/product-category/sofas/"), ("מוצר", "/product/sample-sofa/"), ("סל", "/cart/")]
CORE = PROBE + [("אודות", "/about/")]    # core pages open without signing in and without a filled cart
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}
SCENARIOS = ("incident", "ok", "empty", "error", "hostile")
STATE = {"scenario": "incident", "acked": set(), "html": os.path.join(HERE, "site_health.html")}
ERR = {"error": "HTTP Error 503: Service Unavailable"}
BUCKET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:00)?$")


def incident():
    """The 'hostile' scenario is the incident data, wrapped on its way out (see hostile())."""
    return STATE["scenario"] in ("incident", "hostile")


def rnd(*key):
    """Deterministic pseudo-random number in [0, 1) for a key: the same hour always looks the same."""
    return int(hashlib.md5("|".join(str(k) for k in key).encode()).hexdigest()[:8], 16) / 0x100000000


def now():
    return dt.datetime.now(TZ)


def il(d, year=False):
    return d.astimezone(TZ).strftime("%d.%m.%Y %H:%M" if year else "%d.%m %H:%M")


def window(q):
    """Same rule as the real server: f/t are local dates (t inclusive); otherwise h hours back from now."""
    n = now()
    f, t = q.get("f", ""), q.get("t", "")
    if f:
        try:
            d0 = dt.datetime.strptime(f, "%Y-%m-%d").replace(tzinfo=TZ)
            d1 = (dt.datetime.strptime(t, "%Y-%m-%d").replace(tzinfo=TZ) + dt.timedelta(days=1)) if t else n
            if d1 <= d0:
                d1 = d0 + dt.timedelta(days=1)
            return d0, min(d1, n), max(1, int((d1 - d0).total_seconds() // 3600))
        except ValueError:
            pass
    try:
        h = max(1, min(int(q.get("h") or 24), 24 * 400))
    except ValueError:
        h = 24
    return n - dt.timedelta(hours=h), n, h


def buckets(d0, d1, hours):
    """Hourly buckets ('YYYY-MM-DD HH:00') up to 72 hours, daily ('YYYY-MM-DD') beyond. Local time."""
    out = []
    if hours <= 72:
        b = d0.replace(minute=0, second=0, microsecond=0)
        while b < d1:
            out.append((b.strftime("%Y-%m-%d %H:00"), b, min(b + dt.timedelta(hours=1), d1)))
            b += dt.timedelta(hours=1)
    else:
        b = d0.replace(hour=0, minute=0, second=0, microsecond=0)
        while b < d1:
            out.append((b.strftime("%Y-%m-%d"), b, min(b + dt.timedelta(days=1), d1)))
            b += dt.timedelta(days=1)
    return out


def bad_hour(b):
    """In the 'incident' scenario a few hours are bad: that is where failures and slow pages cluster."""
    return incident() and rnd("bad", b.strftime("%Y-%m-%d %H")) < 0.06


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))] if vals else None


def lcp_for(page, when, strategy):
    base = {"בית": 2300, "קטגוריה": 3300, "מוצר": 2800, "סל": 2100, "אודות": 2500}.get(page, 3000)
    if strategy == "desktop":
        base *= 0.45
    v = base * (0.85 + 0.4 * rnd("lcp", page, strategy, when.strftime("%Y-%m-%d %H")))
    if bad_hour(when) and page in ("קטגוריה", "מוצר"):
        v *= 1.7
    return int(v)


def verdict(ms):
    return "מצוין" if ms <= 2000 else "מהיר" if ms <= 2500 else "בינוני" if ms <= 4000 else "איטי"


def crux(ms):
    return "FAST" if ms <= 2500 else "AVERAGE" if ms <= 4000 else "SLOW"


# ---------------------------------------------------------------- alerts

def span_he(minutes):
    """A length of time in the words a person would say, by the rule of sh_span in reference/functions.sql
    (spec §7.3): the nearest minute, never less than one; minutes under two hours, whole hours under two
    days, whole days from there on: דקה, שתי דקות, 5 דקות, שעה, שעתיים, 7 שעות, יום, יומיים, 4 ימים."""
    m = max(1, int(minutes + 0.5))
    if m in (1, 2, 60, 1440):
        return {1: "דקה", 2: "שתי דקות", 60: "שעה", 1440: "יום"}[m]
    if m < 120:
        return "%d דקות" % m
    if m < 180:
        return "שעתיים"
    if m < 2880:
        return "%d שעות" % (m // 60)
    return "יומיים" if m < 4320 else "%d ימים" % (m // 1440)


def alerts():
    if not incident():
        return []
    n = now()
    rows = [   # name = the page or the flow the alert is about; the recovery push is titled "חזר לתקין: <name>"
        dict(id=41, kind="down", title="האתר לא עונה: סל", name="סל", body="קוד 502\n%s/cart/" % SITE,
             opened=n - dt.timedelta(minutes=14), closed=None),
        dict(id=40, kind="slow", title="עמוד איטי: קטגוריה", name="קטגוריה",
             body="4.6 שניות עד התוכן, פעמיים ברצף\n%s/product-category/sofas/" % SITE,
             opened=n - dt.timedelta(hours=2, minutes=5), closed=None),
        dict(id=39, kind="ops", title="רשימת הבוקר", name="רשימת הבוקר", body="3 הזמנות חסרות",
             opened=n - dt.timedelta(hours=5), closed=None),
        dict(id=38, kind="down", title="האתר לא עונה: בית", name="בית", body="לא ענה בזמן\n%s/" % SITE,
             opened=n - dt.timedelta(hours=9, minutes=40), closed=n - dt.timedelta(hours=9, minutes=33)),
        dict(id=37, kind="cert", title="תעודת האבטחה פגה בעוד 13 ימים", name="תעודת האבטחה", body="example.co.il",
             opened=n - dt.timedelta(days=2, hours=3), closed=n - dt.timedelta(days=1, hours=20)),
        dict(id=36, kind="silent", title="המדידה נעצרה: מדידת מהירות — עמודי ליבה", name="מדידת מהירות — עמודי ליבה",
             body="אין מדידה כבר 95 דקות", opened=n - dt.timedelta(days=3, hours=1), closed=n - dt.timedelta(days=3)),
    ]
    for a in rows:
        end = a["closed"] or n
        a.update(open=a["closed"] is None, opened_il=il(a["opened"]), closed_il=il(a["closed"]) if a["closed"] else None,
                 minutes=max(1, int(round((end - a["opened"]).total_seconds() / 60))),   # nearest minute, at least 1
                 acked=a["id"] in STATE["acked"])
    return rows


def pub(a, keep=("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes", "acked")):
    return {k: a[k] for k in keep}


def filter_role(rows, role):
    if role == "noalerts":
        return []
    if role in ("vendor", "share"):
        return [r for r in rows if r.get("kind") in SITE_ALERT_KINDS]
    return rows


# ---------------------------------------------------------------- /api/site

def api_site(q, role):
    d0, d1, hours = window(q)
    strategy = "desktop" if q.get("strategy") == "desktop" else "mobile"
    out = {"hours": hours, "from": d0.isoformat(), "to": d1.isoformat(), "strategy": strategy}
    sc = STATE["scenario"]
    if sc == "error":       # each of the nine parts failed alone: its key holds {"error": ...}, the answer is still 200
        out.update({k: dict(ERR) for k in ("availability", "availability_series", "speed", "speed_series", "alerts_open",
                                           "alerts_recent", "health", "product_issues", "cert")})
        return out
    if sc == "empty":       # a fresh install: the bottom-line row and the coverage row exist even before the first run
        out.update(availability=[], availability_series=[], speed_series=[], alerts_open=[], alerts_recent=[],
                   speed=[dict(section="שורה תחתונה", page="בית", url=SITE + "/", lcp_p50=None, checks=0, verdict=None),
                          dict(section="כיסוי", checks=0, slow_runs=0)],
                   product_issues=[], cert=None,
                   health=[dict(flow_name=f, status="אין נתון", cadence=c, silent_txt=None,
                                last_at=None, warn_minutes=w, late_minutes=l, note=None) for f, c, w, l in FLOWS])
        return out
    bks = buckets(d0, d1, hours)
    # --- availability
    series, per = [], {p: dict(checks=0, failed=0, ms=[], last=None) for p, _ in PROBE}
    for name, b0, b1 in bks:
        minutes = max(1, int((b1 - b0).total_seconds() // 60))
        ch = fl = 0
        ms = []
        for p, _ in PROBE:
            f = 0
            hrs = max(1, minutes // 60)
            for i in range(hrs):
                hb = b0 + dt.timedelta(hours=i)
                if bad_hour(hb):
                    f += 2 + int(6 * rnd("f", p, hb.isoformat()))
                    per[p]["last"] = hb + dt.timedelta(minutes=int(50 * rnd("fm", p, hb.isoformat())))
                elif rnd("noise", p, hb.isoformat()) < 0.01:
                    f += 1
                    per[p]["last"] = hb + dt.timedelta(minutes=int(50 * rnd("fm", p, hb.isoformat())))
            m = int({"בית": 260, "מוצר": 300, "קטגוריה": 620, "סל": 540}[p] * (0.8 + 0.5 * rnd("ms", p, name)) * (2.2 if bad_hour(b0) else 1))
            ch += minutes
            fl += f
            ms += [m] * 3
            per[p]["checks"] += minutes
            per[p]["failed"] += f
            per[p]["ms"].append(m)
        series.append(dict(bucket=name, checks=ch, failed=fl, ms_p50=pct(ms, .5), ms_p95=int(pct(ms, .95) * 1.6)))
    av = [dict(section="לפי עמוד", page=p, checks=v["checks"], failed=v["failed"],
               fail_pct="%.2f" % (100.0 * v["failed"] / v["checks"]) if v["checks"] else "0.00",
               p50_ms=pct(v["ms"], .5), p95_ms=int(pct(v["ms"], .95) * 1.5) if v["ms"] else None,
               last_fail_il=il(v["last"]) if v["last"] else None) for p, v in per.items()]
    if incident() and hours >= 12:
        s = now() - dt.timedelta(hours=9, minutes=40)
        if s > d0:
            av.append(dict(section="נפילות", outage_minutes=7, outage_start_il=il(s), outage_end_il=il(s + dt.timedelta(minutes=7))))
    out["availability"] = av
    out["availability_series"] = series
    # --- speed
    sp, ss = [], []
    for strat in ("mobile", "desktop"):
        for p, path in CORE:
            vals = [lcp_for(p, b0, strat) for _, b0, _ in bks]
            med = pct(vals, .5)
            sp.append(dict(section="ליבה", strategy=strat, page=p, url=SITE + path, lcp_p50=med, lcp_p95=pct(vals, .95),
                           score_med=max(18, min(99, int(118 - med / 45))), cls_med=round(0.02 + 0.1 * rnd("cls", p), 2),
                           ttfb_p50=int(240 + 500 * rnd("ttfb", p)), slow_runs=sum(1 for v in vals if v > 4000) * 4,
                           checks=len(vals) * 4, crux_category=crux(int(med * 0.8)) if p != "אודות" else None,
                           crux_lcp=int(med * 0.8) if p != "אודות" else None))   # a page with too little traffic
            if strat == strategy:
                ss += [dict(page=p, url=SITE + path, bucket=name, lcp_p50=lcp_for(p, b0, strat)) for name, b0, _ in bks]
    home = [r for r in sp if r["page"] == "בית" and r["strategy"] == "mobile"][0]
    sp.append(dict(section="שורה תחתונה", page="בית", url=home["url"], lcp_p50=home["lcp_p50"], checks=home["checks"],
                   verdict=verdict(home["lcp_p50"])))
    for i in range(10):
        u = "%s/product/%s-%d/" % (SITE, urllib.parse.quote("ספה-פינתית"), i + 1)
        m = int(7200 - 380 * i + 300 * rnd("slow", i))
        sp.append(dict(section="האיטיים באתר", page=u, url=u, lcp_p50=m, score_med=max(9, 48 - 3 * (10 - i)),
                       checks=1 + i % 3, last_il=il(now() - dt.timedelta(hours=1 + 2 * i))))
    sp.append(dict(section="כיסוי", checks=min(412, 24 * hours), slow_runs=412))
    out["speed"] = sp
    out["speed_series"] = ss
    # --- alerts
    al = alerts()
    out["alerts_open"] = [pub(a, ("id", "kind", "title", "body", "opened_il", "acked")) for a in filter_role(al, role) if a["open"]]
    out["alerts_recent"] = [pub(a, ("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes"))
                            for a in filter_role(al, role) if (a["closed"] or now()) >= d0]
    # --- health of the measurement itself
    n = now()
    stat = {"מדידת מהירות — סבב כל האתר": ("מתעכב", 22, "מאחר ב-2 דקות"), "טעינת מפת האתר": ("שקט", 4320, "שקט כבר 3 ימים"),
            "מהירות אצל לקוחות": ("מתעכב", 400, "מאחר ב-40 דקות")} if incident() else {}
    out["health"] = [dict(flow_name=f, status=stat.get(f, ("תקין",))[0], cadence=c,
                          silent_txt=stat[f][2] if f in stat else None,
                          last_at=(n - dt.timedelta(minutes=stat[f][1] if f in stat else int(1 + w * 0.3))).isoformat(),
                          warn_minutes=w, late_minutes=l, note=None) for f, c, w, l in FLOWS]
    # --- broken products
    snap = n.strftime("%Y-%m-%d")
    issues = [] if sc == "ok" else [
        dict(issue="בלי מחיר", name="שולחן אוכל נפתח 160", url=SITE + "/product/table-160/", snap_date=snap),
        dict(issue="בלי תמונה", name="כורסת טלוויזיה אפורה", url=SITE + "/product/armchair-grey/", snap_date=snap),
        dict(issue="לא במלאי", name="ספה תלת מושבית בז'", url=SITE + "/product/sofa-3-beige/", snap_date=snap),
        dict(issue="לא במלאי", name="מיטה זוגית 160 עם ארגז", url=SITE + "/product/bed-160/", snap_date=snap),
        dict(issue="אי אפשר להוסיף לסל", name="שידת לילה אלון", url=SITE + "/product/nightstand-oak/", snap_date=snap),
    ]
    # the order of spec §5.2: "לא במלאי" last, then by issue, then by name
    out["product_issues"] = sorted(issues, key=lambda r: (r["issue"] == "לא במלאי", r["issue"], r["name"]))
    days = 23 if incident() else 71
    out["cert"] = dict(host="example.co.il", issuer="Let's Encrypt R11", not_after=(n + dt.timedelta(days=days, hours=5)).isoformat(),
                       days_left=days, ok=True, err=None, checked_at=n.replace(hour=4, minute=3).isoformat())
    return out


FLOWS = [  # flow_name, cadence, warn_minutes, late_minutes
    ("בודק זמינות האתר", "כל דקה", 5, 15),
    ("מדידת מהירות — עמודי ליבה", "כל רבע שעה", 45, 90),
    ("מדידת מהירות — סבב כל האתר", "כל 5 דקות", 20, 60),
    ("טעינת מפת האתר", "פעם ביום", 1560, 2880),
    ("בדיקת תעודת האבטחה", "פעם ביום", 1560, 2880),
    ("בדיקת מוצרים שבורים", "פעם ביום", 1560, 2880),
    ("מהירות אצל לקוחות", "כל צפייה בעמוד", 360, 1440),
]


# ---------------------------------------------------------------- /api/site/now

def api_now(role):
    sc = STATE["scenario"]
    if sc == "error":
        return {"error": "HTTP Error 503: Service Unavailable"}
    if sc == "empty":
        return dict(pages=[], latest=[], light=False, all_ok=False, any_ok=False, age_sec=None, rum={"n": 0, "p75_ms": None},
                    speed={}, alerts_open=0, rum_src=None)
    n = now()
    pages = []
    for p, path in PROBE:
        ok = not (incident() and p == "סל")
        pages.append(dict(page=p, url=SITE + path, ok=ok, status=200 if ok else 502,
                          ms=int({"בית": 240, "מוצר": 310, "קטגוריה": 690, "סל": 1700}[p] * (0.9 + 0.3 * rnd("now", p, n.strftime("%H:%M")))) if ok else None))
    oks = [p["ok"] for p in pages]
    lcp = lcp_for("בית", n, "mobile")
    return dict(
        pages=pages, latest=pages, light=n.second >= 30, all_ok=all(oks), any_ok=any(oks), age_sec=n.second % 30 + 4,
        rum=dict(n=143, p75_ms=2380 if sc == "ok" else 3120),
        speed=dict(lcp_ms=lcp, score=max(18, min(99, int(118 - lcp / 45))), checked_at=(n - dt.timedelta(minutes=n.minute % 15)).isoformat()),
        alerts_open=len([a for a in filter_role(alerts(), role) if a["open"]]),
        rum_src=dict(n=1000, hosts=[{"host": "live", "n": 1000}] if sc == "ok" else [{"host": "live", "n": 964}, {"host": "staging.example.co.il", "n": 36}],
                     cols=["created_at", "is_test", "lcp_ms", "path", "site"], test=0 if sc == "ok" else 12))


# ---------------------------------------------------------------- /api/site/drill

def drill_request_ok(q):
    """Spec §5.4: a missing or malformed parameter answers {"rows": []}. An empty value means "absent"."""
    what, bucket = q.get("what"), q.get("bucket") or ""
    if bucket and not BUCKET_RE.match(bucket):
        return False
    if what == "bucket":
        return bool(bucket)
    if what == "runs":
        return bool(q.get("url"))
    if what == "alert":
        return (q.get("id") or "").isdigit()
    return True


def api_drill(q, role):
    """The rows of one drill-down. The checks of the request itself (drill_request_ok, the error
    scenario) are done by the HTTP handler, as a real server does them before it reads any data."""
    what = q.get("what", "")
    d0, d1, hours = window(q)
    n = now()
    if STATE["scenario"] in ("empty", "error") and what != "alert":
        return {"rows": []}
    if what == "fails":
        rows = []
        for i in range(23):
            p = PROBE[int(4 * rnd("fp", i))][0]
            if q.get("page") and p != q["page"]:
                continue
            k = ["לא ענה בזמן", "קוד 502", "קוד 500", "שגיאת חיבור"][int(4 * rnd("fk", i))]
            rows.append(dict(at_il=il(n - dt.timedelta(minutes=14 + 31 * i)), page=p, kind=k,
                             err="upstream connect error or disconnect/reset before headers" if k == "שגיאת חיבור" else None,
                             ms=10000 if k == "לא ענה בזמן" else int(300 + 900 * rnd("fms", i))))
        return {"rows": rows}
    if what == "bucket":
        return {"rows": [dict(page=p, checks=60, failed=int(3 * rnd("bf", p, q.get("bucket"))), ms_p50=int(250 + 500 * rnd("bm", p)),
                              ms_max=int(900 + 2500 * rnd("bx", p)), worst_il=il(n - dt.timedelta(minutes=int(600 * rnd("bw", p)))))
                         for p, _ in PROBE]}
    if what == "runs":
        strat = "desktop" if q.get("strategy") == "desktop" else "mobile"
        page = next((p for p, path in CORE if SITE + path == q.get("url")), "מוצר")
        rows = []
        for i in range(36 if not q.get("bucket") else 4):
            t = n - dt.timedelta(minutes=15 * i + 3)
            if i == 5:
                rows.append(dict(ok=False, err="Lighthouse returned error: NO_FCP", at_il=il(t)))
                continue
            lcp = lcp_for(page, t, strat)
            rows.append(dict(ok=True, err=None, at_il=il(t), lcp_ms=lcp, score=max(18, min(99, int(118 - lcp / 45))),
                             ttfb_ms=int(260 + 420 * rnd("rt", i)), bytes=int(3.1e6 + 2.4e6 * rnd("rb", i)), cls=round(0.01 + 0.12 * rnd("rc", i), 3),
                             crux_category=crux(int(lcp * 0.8)), crux_lcp_ms=int(lcp * 0.8),
                             opps=[dict(id="uses-responsive-images", title="Properly size images", ms=int(900 + 700 * rnd("o1", i))),
                                   dict(id="modern-image-formats", title="Serve images in next-gen formats", ms=int(500 + 400 * rnd("o2", i))),
                                   dict(id="render-blocking-resources", title="Eliminate render-blocking resources", ms=int(300 + 300 * rnd("o3", i))),
                                   dict(id="some-new-audit", title="A reason the screen has no translation for", ms=120)]))
        return {"rows": rows}
    if what == "alert":
        try:
            aid = int(q.get("id") or 0)
        except ValueError:
            aid = 0
        rows = [a for a in filter_role(alerts(), role) if a["id"] == aid]
        out = []
        for a in rows:
            r = pub(a, ("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes"))
            r["fails"] = [dict(at=il(a["opened"] + dt.timedelta(minutes=i)), page=a["title"].split(": ")[-1], status=502 if i else None,
                               err=None if i else "timeout") for i in range(3)] if a["kind"] == "down" else []
            sent = [dict(event="open", status=200, at=il(a["opened"]))]
            if a["closed"]:
                sent.append(dict(event="close", status=200, at=il(a["closed"])))
            r["sent"] = [] if role in ("vendor", "share") else sent
            out.append(r)
        return {"rows": out}
    return None


def api_messages(q):
    if not incident():
        return {"rows": []}
    rows = []
    for a in alerts():
        rows.append(dict(kind="התראה", title=a["title"], msg=a["body"], at_il=il(a["opened"]), sent=True, _t=a["opened"]))
        if a["closed"]:
            rows.append(dict(kind="חזר לתקין", title="חזר לתקין: " + a["name"],
                             msg=a["title"] + "\nנמשך " + span_he(a["minutes"]),
                             at_il=il(a["closed"]), sent=a["id"] != 37, _t=a["closed"]))
    n = now()
    rows.append(dict(kind="בוקר", title="בוקר טוב: האתר תקין", msg="זמינות 99.9% ב-24 שעות\nמהירות עמוד הבית: מהיר",
                     at_il=il(n.replace(hour=7, minute=30)), sent=True, _t=n.replace(hour=7, minute=30)))
    rows.sort(key=lambda r: r["_t"], reverse=True)
    return {"rows": [{k: v for k, v in r.items() if k != "_t"} for r in rows]}


# ---------------------------------------------------------------- the "hostile" scenario

PAYLOAD = '\'"><img class="xss" src="x" onerror="window.__xss=1"><b class="xss">x</b>&lt;'
HOSTILE_URL = "javascript:window.__xss=1//" + PAYLOAD
HOSTILE_KEEP = {"section", "bucket", "strategy", "from", "to"}     # what the screen sorts rows by; never shown
HOSTILE_FILL = {"note", "silent_txt", "err"}                       # text fields that are usually null


def hostile(v, key=None):
    """Every text field of an answer, with markup in it. A screen that escapes its texts shows the
    markup as text; one that does not builds an element with class "xss" and sets window.__xss."""
    if isinstance(v, dict):
        return {k: hostile(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [hostile(x, key) for x in v]
    if key in HOSTILE_KEEP:
        return v
    if key == "url":
        return HOSTILE_URL
    if isinstance(v, str):
        return v + PAYLOAD
    if v is None and key in HOSTILE_FILL:
        return PAYLOAD
    return v


# ---------------------------------------------------------------- http

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        """One Cache-Control per answer (spec §5.7): no-store for data, no-cache for the HTML page."""
        page = ctype.startswith("text/html")
        if not page and not isinstance(body, (bytes, str)) and STATE["scenario"] == "hostile" and self.path.startswith("/api/"):
            body = hostile(body)
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, must-revalidate" if page else "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _role(self, q):
        """owner | vendor | noalerts | share, or None = not signed in (the answer is then 401).
        The real server derives it from the session cookie or from the share token."""
        if q.get("k"):
            return "share" if q["k"] == SHARE_TOKEN else None
        m = re.search(r"mock_role=(owner|vendor|noalerts)\b", self.headers.get("Cookie", ""))
        return m.group(1) if m else None

    def _page(self, role, share_key=""):
        html = open(STATE["html"], encoding="utf-8").read()
        if "<!--SH_INJECT-->" not in html:
            return None
        cfg = {"siteLabel": "example.co.il", "brand": "DEMO", "shareKey": share_key, "downAfter": 1,
               "bucketNote": "עמוד הסל וקטגוריה תמיד איטיים יותר: הם לא נשמרים בזיכרון המטמון של האתר ונבנים מחדש בכל כניסה."}
        if role == "owner":
            cfg["links"] = [{"href": "#", "label": "מסך נוסף", "title": "דוגמה לכפתור נוסף"}]
            cfg["nav"] = [["g", "האתר"], ["a", "/site", "בריאות האתר"], ["a", "#", "מסך נוסף"]]
        r = {"owner": {}, "vendor": {"readonly": True}, "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}[role]
        inject = "<script>window.SH_CONFIG=%s;window.SH_ROLE=%s;</script>" % (json.dumps(cfg, ensure_ascii=False), json.dumps(r))
        return html.replace("<!--SH_INJECT-->", inject, 1)

    def _send_page(self, role, share_key="", cookie=None):
        html = self._page(role, share_key)
        if html is None:
            return self._send(500, "the screen file has no <!--SH_INJECT--> marker in its <head>: %s" % STATE["html"],
                              "text/plain; charset=utf-8")
        return self._send(200, html, "text/html; charset=utf-8", {"Set-Cookie": cookie} if cookie else None)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        path = u.path
        if path in ("/", "/site"):
            role = q.get("role", "owner")
            if role not in ("owner", "vendor", "noalerts"):
                role = "owner"
            return self._send_page(role, cookie="mock_role=%s; Path=/; SameSite=Lax" % role)     # the mock's session
        if path == "/status":
            if q.get("k") != SHARE_TOKEN:
                return self._send(403, "<div dir='rtl' style='font-family:system-ui;padding:48px;text-align:center'>הקישור אינו תקין או שפג תוקפו.</div>", "text/html; charset=utf-8")
            # a share page has no session: it lives on its token alone, so an earlier session is dropped here
            return self._send_page("share", SHARE_TOKEN, cookie="mock_role=; Path=/; Max-Age=0; SameSite=Lax")
        if path == "/__scenario":
            if q.get("name") in SCENARIOS:
                STATE["scenario"] = q["name"]
                STATE["acked"] = set()
            return self._send(200, {"mock": "site-health-kit", "scenario": STATE["scenario"]})
        if path in ("/login", "/logout"):
            return self._send(200, "<div dir='rtl' style='font-family:system-ui;padding:48px'>דף הכניסה (דמה). <a href='/site'>חזרה</a></div>", "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        role = self._role(q)
        if role is None:
            return self._send(401, {"error": "auth"})
        if path == "/api/site":
            return self._send(200, api_site(q, role))
        if path == "/api/site/now":
            d = api_now(role)
            return self._send(502 if "error" in d else 200, d)
        if path == "/api/site/drill":
            if q.get("what") not in ("fails", "bucket", "runs", "alert"):
                return self._send(400, {"error": "what?"})
            if STATE["scenario"] == "error":
                return self._send(502, dict(ERR))
            if not drill_request_ok(q):
                return self._send(200, {"rows": []})
            return self._send(200, api_drill(q, role))
        if path == "/api/messages":
            if q.get("k"):                     # the share token counts only on /status and the three data calls
                return self._send(401, {"error": "auth"})
            if role != "owner":
                return self._send(403, {"error": "auth"})
            if STATE["scenario"] == "error":
                return self._send(502, dict(ERR))
            return self._send(200, api_messages(q))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path != "/api/alerts/ack":
            return self._send(404, {"error": "not found"})
        role = self._role(q)
        if q.get("k") or role is None:
            return self._send(401, {"error": "auth"})
        if role != "owner":
            return self._send(403, {"error": "auth"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            raw = body.get("ids") if isinstance(body.get("ids"), list) else [body.get("id")]
            ids = sorted({int(x) for x in raw[:200] if str(x).lstrip("-").isdigit() and int(x) > 0})
        except Exception:
            ids = []
        if not ids:
            return self._send(400, {"error": "bad request"})
        STATE["acked"].update(ids)
        return self._send(200, {"ok": True, "n": len(ids)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--scenario", default="incident", choices=SCENARIOS)
    ap.add_argument("--html", default=STATE["html"], help="the screen file to serve (default: site_health.html next to this script)")
    a = ap.parse_args()
    STATE["scenario"], STATE["html"] = a.scenario, a.html
    try:                                    # bind first: the address is printed only once it is really ours
        httpd = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as e:
        print("port %d cannot be opened (%s). Another program is using it: try  python3 mock_server.py --port %d"
              % (a.port, e.strerror or e, a.port + 1), file=sys.stderr)
        sys.exit(1)
    print("mock site-health backend: http://localhost:%d/site   (scenario: %s)" % (a.port, a.scenario), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
