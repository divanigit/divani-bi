# -*- coding: utf-8 -*-
"""
app.py — Divani BI server (Render web service)
==============================================
Mobile-first agents-performance dashboard over Priority ERP data.

- Serves index.html behind a branded /login page (signed session cookie).
- /api/meta   — data coverage (min/max dates) + last sync time.
- /api/range  — order data for a date range (line-level up to ~3 months,
                agent-level aggregates beyond), queried from Supabase.
- /api/refresh — manual "refresh now" (rate-limited), pulls today+yesterday
                from Priority OData into Supabase.
- Background thread: every REFRESH_MINUTES pulls today+yesterday;
  nightly (~03:10 Israel) re-pulls the last 120 days to catch
  retroactive edits/cancellations, plus one older 90-day slice per night
  (deep_rotate) so a cancellation entered long after the order date is
  not lost to אחוז ביטולים, which buckets by order date.
  The same thread also takes ONE website price snapshot a day at 04:00 Israel
  (bi_web_prices) — the expected price that price control compares orders against.

Env (set in Render, never committed):
    DASH_PASS, SUPABASE_URL, SUPABASE_SECRET_KEY,
    PRI_USER, PRI_PASS, PRI_BASE, REFRESH_MINUTES (optional, default 15)
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
IL = ZoneInfo("Asia/Jerusalem")

DASH_PASS = os.environ.get("DASH_PASS", "")
DASH_PASS_ADMIN = os.environ.get("DASH_PASS_ADMIN", "")  # Doron's personal password
DASH_PASS_ASK2 = os.environ.get("DASH_PASS_ASK2", "")  # Haim: ask-enabled personal password
DASH_PASS_DOV = os.environ.get("DASH_PASS_DOV", "")  # Dov (operations mgr): own credential, regular view access
DASH_PASS_SHARON = os.environ.get("DASH_PASS_SHARON", "")  # Sharon: own credential, regular view access
DASH_PASS_ITAMAR = os.environ.get("DASH_PASS_ITAMAR", "")  # Itamar: own credential, regular view access
DASH_PASS_IDO = os.environ.get("DASH_PASS_IDO", "")  # עידו אהרון: regular view, without any profit figure
SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
PRI_USER = os.environ.get("PRI_USER", "")
PRI_PASS = os.environ.get("PRI_PASS", "")
PRI_BASE = os.environ.get("PRI_BASE", "").rstrip("/")
REFRESH_MINUTES = max(5, int(os.environ.get("REFRESH_MINUTES", "15") or 15))

COOKIE_NAME = "dvbi_session"
MAX_LINE_SPAN_DAYS = 92

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ASK_MODEL = os.environ.get("ASK_MODEL", "claude-sonnet-5")
# pricing for the live cost indicator (USD per million tokens; override via env
# if the model/pricing changes) + USD->ILS rate
ASK_PRICE_IN = float(os.environ.get("ASK_PRICE_IN", "3.0"))
ASK_PRICE_OUT = float(os.environ.get("ASK_PRICE_OUT", "15.0"))
ASK_USD_ILS = float(os.environ.get("ASK_USD_ILS", "3.7"))

app = FastAPI(title="Divani BI", docs_url=None, redoc_url=None, openapi_url=None)

_state = {"last_sync": None, "last_rc": None, "last_manual": 0.0, "minmax": None,
          "minmax_at": 0.0, "pending": [], "pending_at": None, "ocr_cache": {},
          "last_web": None, "last_prices": None}


# ---------- auth ----------

def _session_token() -> str:
    return hmac.new(DASH_PASS.encode("utf-8"), b"divani-bi-session-v1", hashlib.sha256).hexdigest()


def _admin_token() -> str:
    # keyed on the ADMIN password: the code is public, so a manager knowing the
    # shared password must not be able to derive this cookie value
    return hmac.new(DASH_PASS_ADMIN.encode("utf-8"), b"divani-bi-admin-v1", hashlib.sha256).hexdigest()


def _ask2_token() -> str:
    return hmac.new(DASH_PASS_ASK2.encode("utf-8"), b"divani-bi-ask2-v1", hashlib.sha256).hexdigest()


def _ido_token() -> str:
    # keyed on his own password, so the shared password cannot produce this cookie
    return hmac.new(DASH_PASS_IDO.encode("utf-8"), b"divani-bi-ido-v1", hashlib.sha256).hexdigest()


def _is_noprofit(request: Request) -> bool:
    if not DASH_PASS_IDO:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _ido_token())


def _is_ask2(request: Request) -> bool:
    if not DASH_PASS_ASK2:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _ask2_token())


def _can_ask(request: Request) -> bool:
    return _is_admin(request) or _is_ask2(request)


def _is_admin(request: Request) -> bool:
    if not DASH_PASS_ADMIN:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _admin_token())


def _logged_in(request: Request) -> bool:
    if not DASH_PASS:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return (hmac.compare_digest(tok, _session_token()) or _is_admin(request)
            or _is_ask2(request) or _is_noprofit(request))


def _match(p: str, expected: str) -> bool:
    # case-insensitive + trimmed (Likey lesson: mobile auto-capitalize lockouts)
    return bool(expected) and p.strip().casefold() == expected.strip().casefold()


def _pass_ok(p: str) -> bool:
    return (_match(p, DASH_PASS) or _match(p, DASH_PASS_ADMIN)
            or _match(p, DASH_PASS_ASK2) or _match(p, DASH_PASS_DOV)
            or _match(p, DASH_PASS_SHARON) or _match(p, DASH_PASS_ITAMAR)
            or _match(p, DASH_PASS_IDO))


_ALL_PASS = (("DASH_PASS", "המשותפת"), ("DASH_PASS_ADMIN", "דורון"),
             ("DASH_PASS_ASK2", "חיים"), ("DASH_PASS_DOV", "דב"),
             ("DASH_PASS_SHARON", "שרון"), ("DASH_PASS_ITAMAR", "איתמר"),
             ("DASH_PASS_IDO", "עידו"))


def _pass_collisions():
    """Env vars that hold the same password. Two people then share one identity."""
    seen, bad = {}, []
    for var, name in _ALL_PASS:
        val = globals().get(var, "")
        if not val:
            continue
        key = val.strip().casefold()          # exactly the comparison _match uses
        if key in seen:
            bad.append((seen[key], name))
        else:
            seen[key] = name
    return bad


def _identity(p: str):
    """(label for the login log, cookie value) for a password that already passed _pass_ok.

    Ordered least-privileged-first on purpose. Nothing guarantees the seven env values
    are distinct, and the old order checked ADMIN/ASK2 before IDO: an Ido password that
    happened to equal Doron's or Haim's handed Ido their cookie, profit figures included.
    Now a collision can only ever take rights away, never grant them. The label is decided
    in the same place as the cookie, so /logins can no longer name one person while the
    browser is holding someone else's session.
    """
    if _match(p, DASH_PASS_IDO):
        return "עידו", _ido_token()
    if _match(p, DASH_PASS_DOV):
        return "דב", _session_token()
    if _match(p, DASH_PASS_SHARON):
        return "שרון", _session_token()
    if _match(p, DASH_PASS_ITAMAR):
        return "איתמר", _session_token()
    if _match(p, DASH_PASS):
        return "משותף", _session_token()
    if _match(p, DASH_PASS_ASK2):
        return "חיים", _ask2_token()
    if _match(p, DASH_PASS_ADMIN):
        return "אדמין", _admin_token()
    return "?", ""


def _who(p: str) -> str:
    return _identity(p)[0]


# ---------- the no-profit role (עידו) ----------
# One gate for every /api/ answer, and it denies by default: an endpoint that is not
# listed here returns "בפיתוח" instead of leaking a number nobody checked.
# A blacklist would fail open the day someone adds an endpoint and forgets this table.

def _np_range(d):
    # lines mode: every item is [pdes, partname, qprice, qprofit] — profit is index 3, unnamed
    if d.get("mode") == "lines":
        for r in d.get("rows") or []:
            k = r.get("k")
            if isinstance(k, list):
                r["k"] = [(t[:3] if isinstance(t, list) else t) for t in k]
        return d
    agg = d.get("agg") or {}
    for g in agg.get("agents") or []:
        g.pop("p", None)
    for g in agg.get("branches") or []:
        g.pop("p", None)
        g.pop("pp", None)      # the phone slice of the branch profit
    return d


def _np_dimtree(d):
    agg = d.get("agg") or {}
    agg.pop("total_p", None)
    for g in agg.get("rows") or []:
        g.pop("p", None)
    rest = agg.get("rest")
    if isinstance(rest, dict):
        rest.pop("p", None)
    return d


def _np_agentreport(d):
    for b in d.get("branches") or []:
        b.pop("margin", None)
        for r in b.get("reps") or []:
            r.pop("margin", None)
    return d


def _np_compensation(d):
    # /api/moneydown is blocked for the no-profit user, and the compensation payload
    # carries the same numbers in miniature: the period money-down total, the part of it
    # that is not linked to a fault report, and the negative money broken down per
    # catalog description. Without this the block on the other endpoint means nothing.
    agg = d.get("agg")
    if not isinstance(agg, dict):
        return d
    meta = agg.get("meta")
    if isinstance(meta, dict):
        for k in ("money_down_total", "money_down_orders",
                  "money_down_sales", "money_down_sales_orders"):
            meta.pop(k, None)
    agg.pop("unlinked", None)
    amb = agg.get("ambiguity")
    if isinstance(amb, dict):
        amb.pop("rows", None)      # per-description negative money = the money-down drill
    return d


_NP_STRIP = {
    "/api/meta": None,
    "/api/range": _np_range,
    "/api/dim": _np_dimtree,
    "/api/tree": _np_dimtree,
    "/api/segdrill": _np_dimtree,
    "/api/agentreport": _np_agentreport,
    "/api/panel": None,
    "/api/pareto": None,
    "/api/baskets": None,
    "/api/branchsrc": None,
    "/api/cancels": None,
    "/api/cancelorders": None,
    "/api/series": None,
    "/api/cancelcase": None,
    "/api/compensation": _np_compensation,
    "/api/dow": None,
    "/api/collect": None,
    "/api/cash": None,
    "/api/pending": None,
    "/api/refresh": None,
}
_NP_BLOCK = {"/api/moneydown", "/api/flags", "/api/flag", "/api/ask"}

# key names that can only mean profit — a second net under the per-endpoint strippers.
# "p" is deliberately absent: in the agent report it is a mix percentage, not profit.
_NP_KEYS = ("profit", "qprofit", "gross_profit", "gp", "total_p", "profit_pct",
            "margin", "margin_pct", "pm", "net_p", "net_p_m")


def _np_scrub(x):
    if isinstance(x, dict):
        for k in _NP_KEYS:
            x.pop(k, None)
        for v in x.values():
            _np_scrub(v)
    elif isinstance(x, list):
        for v in x:
            _np_scrub(v)
    return x


@app.middleware("http")
async def _np_gate(request: Request, call_next):
    path = request.url.path
    if not (path.startswith("/api/") and _is_noprofit(request)):
        return await call_next(request)        # everybody else: nothing changes
    if path in _NP_BLOCK or path not in _NP_STRIP:
        return JSONResponse({"dev": True})
    resp = await call_next(request)
    # Deny by default on the way out too: EVERY json answer is scrubbed, whatever its
    # status code. Gating on 200 used to hand any non-200 body back untouched, so a future
    # 206/207/500 that carries data would have shipped profit straight to the no-profit user.
    ctype = (resp.headers.get("content-type") or "").lower()
    if (not hasattr(resp, "body_iterator") or "json" not in ctype
            or resp.status_code in (204, 304)):
        return resp           # redirect / html / empty — never a data payload of ours
    body = b"".join([chunk async for chunk in resp.body_iterator])
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return JSONResponse({"dev": True}, status_code=resp.status_code)
    fn = _NP_STRIP[path]
    if fn is not None and isinstance(payload, dict):
        payload = fn(payload)
    return JSONResponse(_np_scrub(payload), status_code=resp.status_code)


def _login_html(err: str = "") -> str:
    e = '<div class="err">' + err + "</div>" if err else ""
    return ("""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>דיוואני — כניסה</title><style>
:root{--bd:#0d9668;--bg:#ffffff;--surface:#f4f8f6;--line2:#cdd8d2;--tx:#18241f;--tx3:#8a978f;--dfg:#a3271f}
@media (prefers-color-scheme:dark){:root{--bd:#2fbf8f;--bg:#0f1512;--surface:#19211d;--line2:#35423b;--tx:#e9efeb;--tx3:#6f7d76;--dfg:#f0968f}}
html,body{background:var(--bg);color:var(--tx);margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Hebrew",Arial,sans-serif}
.wrap{min-height:100svh;display:flex;align-items:center;justify-content:center;padding:24px}
.card{width:100%;max-width:330px;text-align:center}
.bd{font-size:13px;font-weight:500;letter-spacing:.16em;color:var(--bd);text-transform:uppercase}
h1{font-size:21px;font-weight:500;margin:8px 0 4px}p{font-size:13px;color:var(--tx3);margin:0 0 18px}
input{width:100%;height:46px;border:1px solid var(--line2);border-radius:10px;background:var(--surface);color:var(--tx);font-family:inherit;font-size:16px;text-align:center;box-sizing:border-box}
button{width:100%;height:46px;margin-top:10px;border:0;border-radius:10px;background:var(--bd);color:#fff;font-family:inherit;font-size:15px;font-weight:500;cursor:pointer}
.err{color:var(--dfg);font-size:13px;margin-top:10px;min-height:18px}
</style></head><body><div class="wrap"><form class="card" method="post" action="/login" autocomplete="off">
<div class="bd">דיוואני</div><h1>דוחות ביצועים</h1><p>הזן סיסמה כדי להיכנס — למנהלים בלבד</p>
<input name="p" type="password" placeholder="סיסמה" autocapitalize="off" autocorrect="off" spellcheck="false">
<button type="submit">כניסה</button>__ERR__</form></div></body></html>""").replace("__ERR__", e)


# ---------- supabase / priority helpers ----------

def _http(url, headers, data=None, timeout=180, method=None):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sb_rpc(fn: str, params: dict):
    body = json.dumps(params).encode("utf-8")
    out = _http(f"{SB_URL}/rest/v1/rpc/{fn}",
                {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
                 "Content-Type": "application/json"}, data=body, timeout=120)
    return json.loads(out.decode("utf-8")) if out else None


def sb_insert(table: str, row: dict):
    body = json.dumps(row).encode("utf-8")
    _http(f"{SB_URL}/rest/v1/{table}",
          {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
           "Content-Type": "application/json", "Prefer": "return=minimal"},
          data=body, timeout=60)


def sb_upsert(path: str, rows: list):
    # path = "table?on_conflict=col_a,col_b" (PostgREST bulk upsert).
    # merge-duplicates = a row that already exists is overwritten, not duplicated.
    body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    _http(f"{SB_URL}/rest/v1/{path}",
          {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
           "Content-Type": "application/json",
           "Prefer": "resolution=merge-duplicates,return=minimal"},
          data=body, timeout=120)


def sb_select(path: str):
    # path = "table?select=...&order=...&limit=..." (PostgREST GET)
    out = _http(f"{SB_URL}/rest/v1/{path}",
                {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY},
                timeout=30)
    return json.loads(out.decode("utf-8")) if out else []


PRI_SEL = ("$select=ORDNAME,CURDATE,ORDSTATUSDES,AGENTNAME,CUSTNAME,CDES,BRANCHNAME,TYPEDES"
           "&$expand=ORDERITEMS_SUBFORM($select=PARTNAME,PDES,QPRICE,QPROFIT,TQUANT)")


def priority_pull(d_from: dt.date, d_to: dt.date):
    """Pull orders whose CURDATE date-string is within [d_from, d_to]."""
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    lo = (d_from - dt.timedelta(days=1)).isoformat() + "T00:00:00%2B02:00"
    hi = (d_to + dt.timedelta(days=2)).isoformat() + "T00:00:00%2B02:00"
    url = f"{PRI_BASE}/ORDERS?$filter=CURDATE%20ge%20{lo}%20and%20CURDATE%20lt%20{hi}&{PRI_SEL}"
    orders, guard = [], 0
    while url and guard < 100:
        guard += 1
        j = json.loads(_http(url, {"Authorization": auth, "Accept": "application/json"},
                             timeout=180).decode("utf-8"))
        orders += j.get("value", [])
        url = j.get("@odata.nextLink")
    rows, n_orders = [], 0
    lo_s, hi_s = d_from.isoformat(), d_to.isoformat()
    for o in orders:
        d = (o.get("CURDATE") or "")[:10]
        if not (lo_s <= d <= hi_s):
            continue
        lines = o.get("ORDERITEMS_SUBFORM") or []
        if not lines:
            continue
        n_orders += 1
        for i, ln in enumerate(lines):
            rows.append({"o": o.get("ORDNAME") or "", "d": d,
                         "a": o.get("AGENTNAME") or "", "cn": o.get("CUSTNAME") or "",
                         "c": o.get("CDES") or "", "b": o.get("BRANCHNAME") or "",
                         "st": o.get("ORDSTATUSDES") or "",
                         "t": o.get("TYPEDES") or "",
                         "pn": ln.get("PARTNAME") or "", "pd": ln.get("PDES") or "",
                         "s": round(float(ln.get("QPRICE") or 0), 2),
                         "p": round(float(ln.get("QPROFIT") or 0), 2),
                         "q": (None if ln.get("TQUANT") is None
                               else round(float(ln.get("TQUANT") or 0), 3)),
                         "ln": i})
    return n_orders, rows


def sync_window(kind: str, d_from: dt.date, d_to: dt.date, skip_if_empty: bool = False):
    t0 = time.time()
    n_orders, rows = priority_pull(d_from, d_to)
    # skip_if_empty guards the OLD windows: bi_replace_window deletes the window first,
    # so an empty pull (a Priority hiccup) would blank real history.
    if skip_if_empty and not rows:
        return
    sb_rpc("bi_replace_window", {"p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
                                 "p_rows": rows})
    took = int((time.time() - t0) * 1000)
    # A sale can use a SKU created minutes earlier (the generator mints them per order).
    # Until the catalog knows it, the line has no family and falls into the unclassified
    # bucket — that is how a single day once showed 41% of sales as "אחר".
    try:
        if sb_rpc("bi_unknown_parts", {"p_from": d_from.isoformat(), "p_to": d_to.isoformat()}):
            sync_parts()
    except Exception:
        pass
    try:
        sb_insert("bi_sync_log", {"kind": kind, "d_from": d_from.isoformat(),
                                  "d_to": d_to.isoformat(), "orders": n_orders,
                                  "lines": len(rows), "took_ms": took})
    except Exception:
        pass
    _state["last_sync"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")
    _state["minmax"] = None  # bust cache


# ---------- deep rotation: older windows, one slice a night ----------
# The nightly window is the last 120 days. An order cancelled MORE than four months
# after it was written (Priority allows it) would otherwise never be re-read, and
# אחוז ביטולים buckets cancellations by ORDER date — so an old month's rate would be
# understated forever. One older slice per night keeps the whole rotation fresh
# without pulling years of orders in a single request.
DEEP_DAYS = 730        # how far back the rotation reaches
DEEP_CHUNK = 90        # days re-pulled per night
_deep_i = 0


def deep_rotate(today: dt.date):
    global _deep_i
    span = DEEP_DAYS - 120
    n = max(1, -(-span // DEEP_CHUNK))     # ceil
    i = _deep_i % n
    _deep_i = i + 1
    hi = today - dt.timedelta(days=121 + i * DEEP_CHUNK)
    lo = hi - dt.timedelta(days=DEEP_CHUNK - 1)
    floor = today - dt.timedelta(days=DEEP_DAYS)
    if lo < floor:
        lo = floor
    if hi < lo:
        return
    sync_window("deep", lo, hi, skip_if_empty=True)


# ---------- receipts (קבלות) → cash indicator ----------

PAY_CARD_WORDS = ("ישראכרט", "ויזה", "אמריקן", "מאסטר", "דיינרס", "אשראי")


def _pay_kind(name: str) -> str:
    n = name or ""
    if "ביט" in n:
        return "bit"
    if "העברה" in n:
        return "transfer"
    if any(w in n for w in PAY_CARD_WORDS):
        return "card"
    return "other"


def priority_pull_receipts(d_from: dt.date, d_to: dt.date):
    """Pull receipts (TINVOICES) whose IVDATE date-string is within [d_from, d_to],
    flattened to one row per payment component. $select is NOT combinable with
    $expand on TINVOICES (server returns empty rows) — pull full headers."""
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    lo = (d_from - dt.timedelta(days=1)).isoformat() + "T00:00:00%2B02:00"
    hi = (d_to + dt.timedelta(days=2)).isoformat() + "T00:00:00%2B02:00"
    url = (f"{PRI_BASE}/TINVOICES?$filter=IVDATE%20ge%20{lo}%20and%20IVDATE%20lt%20{hi}"
           "&$expand=TPAYMENT_SUBFORM,TPAYMENT2_SUBFORM")
    recs, guard = [], 0
    while url and guard < 100:
        guard += 1
        j = json.loads(_http(url, {"Authorization": auth, "Accept": "application/json"},
                             timeout=180).decode("utf-8"))
        recs += j.get("value", [])
        url = j.get("@odata.nextLink")
    rows, n_receipts = [], 0
    lo_s, hi_s = d_from.isoformat(), d_to.isoformat()
    for r in recs:
        d = (r.get("IVDATE") or "")[:10]
        if not (lo_s <= d <= hi_s):
            continue
        comps = []
        cash = float(r.get("CASHPAYMENT") or 0)
        if cash:
            comps.append(("cash", "מזומן", cash, None))
        for ln in (r.get("TPAYMENT_SUBFORM") or []):
            amt = float(ln.get("QPRICE") or 0)
            if amt:
                comps.append(("check", ("שיק " + (ln.get("BANKNAME") or "")).strip(),
                              amt, (ln.get("PAYDATE") or "")[:10] or None))
        for ln in (r.get("TPAYMENT2_SUBFORM") or []):
            amt = float(ln.get("QPRICE") or 0)
            nm = ln.get("PAYMENTNAME") or ""
            if amt:
                comps.append((_pay_kind(nm), nm, amt, (ln.get("PAYDATE") or "")[:10] or None))
        if not comps:
            continue
        n_receipts += 1
        base = {"iv": r.get("IVNUM") or "", "d": d, "b": r.get("BRANCHNAME") or "",
                "a": r.get("AGENTNAME") or "", "cn": r.get("CUSTNAME") or "",
                "c": r.get("CDES") or "", "o": r.get("ORDNAME") or "",
                "st": r.get("STATDES") or ""}
        for k, m, s, pd in comps:
            row = dict(base)
            row.update({"k": k, "m": m, "s": round(s, 2), "pd": pd or ""})
            rows.append(row)
    return n_receipts, rows


def sync_receipts_window(kind: str, d_from: dt.date, d_to: dt.date):
    t0 = time.time()
    n_receipts, rows = priority_pull_receipts(d_from, d_to)
    sb_rpc("bi_replace_rc_window", {"p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
                                    "p_rows": rows})
    took = int((time.time() - t0) * 1000)
    try:
        sb_insert("bi_sync_log", {"kind": "rc-" + kind, "d_from": d_from.isoformat(),
                                  "d_to": d_to.isoformat(), "orders": n_receipts,
                                  "lines": len(rows), "took_ms": took})
    except Exception:
        pass
    _state["last_rc"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")


# ---------- customer attributes + product catalog sync (פילוח) ----------

def _pri_pages(url: str, auth: str, guard_max: int = 200):
    """Yield rows across OData pages. A guard exhaustion with pages left is a
    truncated pull — raise so callers never mistake it for a complete sync."""
    guard = 0
    while url and guard < guard_max:
        guard += 1
        j = json.loads(_http(url, {"Authorization": auth, "Accept": "application/json"},
                             timeout=180).decode("utf-8"))
        for r in j.get("value", []):
            yield r
        url = j.get("@odata.nextLink")
    if url:
        raise RuntimeError(f"pagination guard exhausted ({guard_max} pages), pull truncated")


def sync_customers_window(days_back: int):
    """Upsert minimal customer attributes (city/sector/source only — privacy
    minimization) for customers created in the last `days_back` days."""
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    lo = (dt.datetime.now(IL).date() - dt.timedelta(days=days_back)).isoformat()
    url = (f"{PRI_BASE}/CUSTOMERS?$filter=CREATEDDATE%20ge%20{lo}T00:00:00%2B02:00"
           "&$select=CUSTNAME,CITYNAME,RONY_SUGCUSTDES,SPEC4,CREATEDDATE")
    rows = [{"cn": r.get("CUSTNAME") or "", "ct": r.get("CITYNAME") or "",
             "sc": r.get("RONY_SUGCUSTDES") or "", "sr": r.get("SPEC4") or "",
             "cr": (r.get("CREATEDDATE") or "")[:10]}
            for r in _pri_pages(url, auth)]
    if rows:
        for i in range(0, len(rows), 2000):
            sb_rpc("bi_upsert_customers", {"p_rows": rows[i:i + 2000]})
    return len(rows)


# descriptor words that are never a model name (parser guard)
_NOT_MODEL = ("בד", "עור", "צבע", "גודל", "רגלי", "רגל", "מבצע", "קיזוז", "מספר",
              "ימין", "שמאל", "פינה", "אוכל", "נפתח", "סלון", "זכוכית", "עץ")


def parse_model_version(pdes: str):
    """Model + version from a part description.
    Grammar: 'X-דגם-<model>-<version...>' or '<type>-<model>-<version...>'."""
    toks = [t.strip() for t in pdes.replace("+", "-").split("-") if t.strip()]
    if not toks:
        return "", ""
    if "דגם" in toks:
        i = toks.index("דגם")
        if i + 1 < len(toks):
            m = toks[i + 1]
            if m.isdigit() or m in _NOT_MODEL:   # 'ידית דגם 31', 'השוואת דגם'
                return "", ""
            return m, "-".join(toks[i + 2:])
        return "", ""
    # chair-style grammar: type-model-version...
    if len(toks) >= 2 and not toks[1].isdigit() and toks[1] not in _NOT_MODEL:
        return toks[1], "-".join(toks[2:])
    return "", ""


def sync_parts():
    """Upsert the full part catalog (part -> family + parsed model/version)."""
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    url = f"{PRI_BASE}/LOGPART?$select=PARTNAME,PARTDES,FAMILYDES"
    rows = []
    for r in _pri_pages(url, auth, guard_max=400):
        d = r.get("PARTDES") or ""
        m, v = parse_model_version(d)
        rows.append({"pn": r.get("PARTNAME") or "", "f": r.get("FAMILYDES") or "",
                     "d": d, "m": m, "v": v})
    if rows:
        for i in range(0, len(rows), 2000):
            sb_rpc("bi_upsert_parts", {"p_rows": rows[i:i + 2000]})
    return len(rows)


SN_SEL = ("$select=CUSTNOTE,TODOREFA,CURDATE,STIME,CUSTNAME,CUSTDES,AGENTNAME,BRANCHNAME,"
          "STATDES,CLOSED,CLOSEDATE,ESTR_MALFCODE,ESTR_MALFDES,ESTR_ACCOUNTDES,"
          "RSOL_PARTNAME,RSOL_PARTDES,SUBJECT,REMARK,IVDES,TOPICDES,USERLOGIN,OUSERLOGIN")


def sync_service_notes_window(days_back: int):
    """Upsert the service/activity log (CUSTNOTESA) for records OPENED in the last
    `days_back` days. Window is on CURDATE (opening date, immutable) — a note is
    closed and its fault reason filled in days or months after it opens, so the
    nightly call uses a wide window to pick those later edits up."""
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    lo = (dt.datetime.now(IL).date() - dt.timedelta(days=days_back)).isoformat()
    url = (f"{PRI_BASE}/CUSTNOTESA?$filter=CURDATE%20ge%20{lo}T00:00:00%2B02:00"
           f"&{SN_SEL}")
    rows = [{"id": r.get("CUSTNOTE"), "o": (r.get("TODOREFA") or "").strip(),
             "d": (r.get("CURDATE") or "")[:10], "t": r.get("STIME") or "",
             "cn": r.get("CUSTNAME") or "", "cd": r.get("CUSTDES") or "",
             "a": r.get("AGENTNAME") or "", "b": r.get("BRANCHNAME") or "",
             "st": r.get("STATDES") or "", "cl": r.get("CLOSED") or "",
             "cld": (r.get("CLOSEDATE") or "")[:10],
             "mc": r.get("ESTR_MALFCODE") or "", "md": r.get("ESTR_MALFDES") or "",
             "ad": r.get("ESTR_ACCOUNTDES") or "",
             "pn": r.get("RSOL_PARTNAME") or "", "pd": r.get("RSOL_PARTDES") or "",
             "sb": r.get("SUBJECT") or "", "rm": r.get("REMARK") or "",
             "iv": r.get("IVDES") or "", "tp": r.get("TOPICDES") or "",
             "u": r.get("USERLOGIN") or "", "ou": r.get("OUSERLOGIN") or ""}
            for r in _pri_pages(url, auth) if r.get("CUSTNOTE") is not None]
    if rows:
        for i in range(0, len(rows), 1000):
            sb_rpc("bi_upsert_service_notes", {"p_rows": rows[i:i + 1000]})
    return len(rows)


# ---------- website price snapshot (vdivani.co.il) → bi_web_prices ----------
# Price control compares every order line to the website price of that day. The site
# keeps NO price history: a day that was not captured can never be reconstructed
# afterwards. That is why the capture runs here, on the server, and not on a person's
# PC where a forgotten task or a shut-down laptop silently ends the whole record.
#
# Source: the public WooCommerce Store API. Site prices INCLUDE VAT and are stored as
# shown; bi_order_lines is before VAT, so any comparison must convert first.
# One row per product per day (PK snap_date+product_id) — a re-run overwrites the
# day's rows instead of duplicating them.
# Manual/local twin of this code: C:\Users\doron\divani_bi\cloud\capture_web_prices.py
# (keep the two in step — same API, same columns, same VAT rule).

WEB_API = "https://vdivani.co.il/wp-json/wc/store/v1/products"
WEB_PER_PAGE = 100
WEB_HOUR = 4          # 04:00 Israel — quiet on the site, and clear of the 03:00 nightly block


def _web_money(raw, minor_unit):
    """WooCommerce price string -> shekels. currency_minor_unit is 0 on this site,
    but the division stays generic so the code survives that changing."""
    if raw is None or raw == "":
        return None
    try:
        return round(int(raw) / (10 ** int(minor_unit or 0)), 2)
    except (TypeError, ValueError):
        return None


def web_fetch_catalogue():
    """The whole public catalogue, verified against the x-wp-total header.
    A partial read is NOT stored — it would look exactly like products that
    disappeared from the site, and price control would flag phantom variances.
    Uses urllib directly (not _http) because paging needs the response headers."""
    rows, page, total, pages = [], 1, None, 1
    while True:
        req = urllib.request.Request(
            f"{WEB_API}?per_page={WEB_PER_PAGE}&page={page}",
            headers={"User-Agent": "divani-bi-price-capture/1.0",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
            hdr = {k.lower(): v for k, v in dict(r.headers).items()}
        if total is None:
            total = int(hdr.get("x-wp-total") or 0)
            pages = int(hdr.get("x-wp-totalpages") or 1)
        if not data:
            break
        rows += data
        if page >= pages:
            break
        page += 1
    ids = {r["id"] for r in rows}
    if total and len(rows) != total:
        raise RuntimeError(f"site declared {total} products but {len(rows)} were read — "
                           f"snapshot aborted rather than storing a partial day")
    if len(ids) != len(rows):
        raise RuntimeError(f"duplicate product ids ({len(rows)} rows, {len(ids)} ids)")
    return rows, total


def sync_web_prices():
    t0 = time.time()
    snap = dt.datetime.now(IL).date().isoformat()
    products, declared = web_fetch_catalogue()
    rows, ranged = [], 0
    for p in products:
        pr = p.get("prices") or {}
        mu = pr.get("currency_minor_unit", 0)
        # A price_range product means its variations differ and `price` is only the
        # cheapest one — half a truth that would raise a variance that is not real.
        # None exist today (16.8.26); if one appears it must be seen in the log.
        if pr.get("price_range"):
            ranged += 1
        on_sale = bool(p.get("on_sale"))
        rows.append({
            "snap_date":     snap,
            "product_id":    p["id"],
            "name":          p.get("name"),
            "slug":          p.get("slug"),
            "url":           p.get("permalink"),
            "sku":           (p.get("sku") or None),
            "product_type":  p.get("type"),
            "regular_price": _web_money(pr.get("regular_price"), mu),
            # WooCommerce echoes the catalogue price into sale_price even with no sale.
            # NULL when not on sale, so no discount is invented.
            "sale_price":    _web_money(pr.get("sale_price"), mu) if on_sale else None,
            "price":         _web_money(pr.get("price"), mu),
            "on_sale":       on_sale,
            "in_stock":      bool(p.get("is_in_stock")),
            "currency":      pr.get("currency_code"),
        })
    for i in range(0, len(rows), 200):
        sb_upsert("bi_web_prices?on_conflict=snap_date,product_id", rows[i:i + 200])
    took = int((time.time() - t0) * 1000)
    # Written LAST and only on success: bi_health measures this flow by the log row,
    # so a failed capture leaves no proof of life and is reported as a silent feed.
    sb_insert("bi_sync_log", {"kind": "web_prices", "d_from": snap, "d_to": snap,
                              "lines": len(rows), "took_ms": took})
    _state["last_web"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")
    print(f"web-prices {snap}: {len(rows)} products (site declared {declared}), "
          f"{took} ms", flush=True)
    if ranged:
        print(f"web-prices WARNING: {ranged} product(s) have a price range — "
              f"only the lowest price was stored", flush=True)
    return len(rows)


# ---------- Priority price list snapshot (LOGPART) → bi_part_prices ----------
# The other half of price control. Priority holds TODAY's list price and nothing
# else: LOGPART is overwritten in place, so a price that changed this morning has
# erased what it was yesterday. Without a daily copy, "was this line sold at the
# list price of that day?" is unanswerable for every day not captured — which is
# why July 2026 shows 0 lines checked and 345 lines "no list price for the order
# date". Same rule as the website capture: a missed day is gone forever.
#
# BASEPLPRICE is before VAT and is the one to compare with; qprice is also before
# VAT. VATPRICE is stored alongside only because Priority publishes it — note that
# it still carries 17% on old rows, so it must never be used for a 2025+ figure.

PRICE_HOUR = 4          # alongside the website capture, before the working day
PRICE_FLOOR = 0.80      # see the guard below


def sync_part_prices():
    t0 = time.time()
    snap = dt.datetime.now(IL).date().isoformat()
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    url = (f"{PRI_BASE}/LOGPART?$select=PARTNAME,PARTDES,FAMILYDES,"
           "BASEPLPRICE,VATPRICE,STATDES")

    rows, seen = [], set()
    for r in _pri_pages(url, auth, guard_max=400):
        pn = (r.get("PARTNAME") or "").strip()
        if not pn or pn in seen:
            continue
        seen.add(pn)
        rows.append({
            "snap_date":   snap,
            "partname":    pn,
            "pdes":        r.get("PARTDES") or "",
            "family":      r.get("FAMILYDES") or "",
            "base_price":  r.get("BASEPLPRICE") or 0,
            "vat_price":   r.get("VATPRICE") or 0,
            "part_status": r.get("STATDES") or "",
        })

    # A short read must never be stored. It looks exactly like parts that were
    # deleted from the catalogue, and every order line for a missing part would be
    # reported as "no list price" — a silent hole in the audit rather than an error.
    # The floor is 80% of the last snapshot: the catalogue moves by a handful of
    # parts a day, never by a fifth. Adjustable — this is an operational guard,
    # not a business rule.
    # Counted by RPC, not by selecting rows: PostgREST caps a plain select at 1,000
    # rows whatever limit is asked for, so counting client-side would report 1,000
    # for a 9,600-part snapshot and quietly disable the floor below.
    prev = 0
    try:
        r = sb_rpc("bi_part_prices_last", {"p_before": snap})
        if r:
            prev = int(r[0]["n"])
    except Exception as e:
        # No previous snapshot, or Supabase unreachable for the count: fall through
        # with prev=0 so the floor can never block the very first capture.
        print("part-prices: previous count unavailable:", repr(e)[:200], flush=True)
    if prev and len(rows) < prev * PRICE_FLOOR:
        raise RuntimeError(f"read {len(rows)} parts but the last snapshot had {prev} — "
                           f"below the {int(PRICE_FLOOR*100)}% floor, snapshot aborted "
                           f"rather than storing a partial day")
    if not rows:
        raise RuntimeError("LOGPART returned no rows — snapshot aborted")

    for i in range(0, len(rows), 500):
        sb_upsert("bi_part_prices?on_conflict=snap_date,partname", rows[i:i + 500])
    took = int((time.time() - t0) * 1000)
    # Written LAST and only on success — bi_health proves this flow by the log row.
    sb_insert("bi_sync_log", {"kind": "part_prices", "d_from": snap, "d_to": snap,
                              "lines": len(rows), "took_ms": took})
    _state["last_prices"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")
    print(f"part-prices {snap}: {len(rows)} parts (previous snapshot {prev}), "
          f"{took} ms", flush=True)
    return len(rows)


def _refresher():
    last_nightly = None
    last_web = None
    last_prices = None
    while True:
        try:
            now = dt.datetime.now(IL)
            today = now.date()
            # Website price snapshot — once a day, 04:00 Israel time (quiet on the
            # site, clear of the 03:00 nightly block).
            # Placed FIRST on purpose, and not inside the nightly block: sync_window
            # below is unguarded, so a Priority failure aborts the whole cycle, and
            # the nightly block is skipped entirely until its own pull succeeds.
            # A day of Priority data can be re-pulled later; a missed day of website
            # prices is gone forever — the site keeps no history.
            # On failure last_web is left alone, so the next cycle (15 min) retries
            # until the day is captured.
            if now.hour >= WEB_HOUR and last_web != today:
                try:
                    sync_web_prices()
                    last_web = today
                except Exception as e:
                    print("web-prices capture failed:", repr(e)[:300], flush=True)
            # Priority list price snapshot — the other half of price control, and
            # equally unrecoverable after the fact. Its own guard and its own marker
            # so a failure on one side never costs the other side its day.
            if now.hour >= PRICE_HOUR and last_prices != today:
                try:
                    sync_part_prices()
                    last_prices = today
                except Exception as e:
                    print("part-prices capture failed:", repr(e)[:300], flush=True)
            sync_window("auto", today - dt.timedelta(days=1), today)
            try:
                sync_receipts_window("auto", today - dt.timedelta(days=1), today)
            except Exception as e:
                print("receipts auto-sync failed:", repr(e)[:300], flush=True)
            try:
                sync_customers_window(3)   # fresh dims for today's new customers
            except Exception as e:
                print("customers auto-sync failed:", repr(e)[:300], flush=True)
            try:
                sync_service_notes_window(3)   # today's service/activity records
            except Exception as e:
                print("service-notes auto-sync failed:", repr(e)[:300], flush=True)
            if ANTHROPIC_KEY:  # without vision there are no slip amounts — nothing to show
                try:
                    _scan_pending_transfers()
                except Exception as e:
                    print("pending-transfers scan failed:", repr(e)[:300], flush=True)
            if now.hour >= 3 and last_nightly != today:
                sync_window("nightly", today - dt.timedelta(days=120), today)
                try:
                    sync_receipts_window("nightly", today - dt.timedelta(days=120), today)
                except Exception as e:
                    print("receipts nightly-sync failed:", repr(e)[:300], flush=True)
                # wide window: sector tags are edited on RETURNING customers'
                # cards, so re-pull ~3 years of customer creations nightly
                try:
                    sync_customers_window(1100)
                except Exception as e:
                    print("customers nightly-sync failed:", repr(e)[:300], flush=True)
                try:
                    sync_parts()                # catalog families
                except Exception as e:
                    print("parts nightly-sync failed:", repr(e)[:300], flush=True)
                # wide window: a note opened months ago gets CLOSED and gets its
                # fault reason typed in later, and the window is on the opening
                # date — so the whole rotation has to be re-read to catch that
                try:
                    sync_service_notes_window(DEEP_DAYS)
                except Exception as e:
                    print("service-notes nightly-sync failed:", repr(e)[:300], flush=True)
                try:
                    sb_rpc("bi_refresh_firsts", {})  # first-purchase table
                except Exception as e:
                    print("firsts nightly-refresh failed:", repr(e)[:300], flush=True)
                try:
                    deep_rotate(today)   # one older window a night — late cancellations
                except Exception as e:
                    print("deep-rotate sync failed:", repr(e)[:300], flush=True)
                last_nightly = today
        except Exception:
            pass
        time.sleep(REFRESH_MINUTES * 60)


def _configured() -> bool:
    return bool(DASH_PASS and SB_URL and SB_KEY and PRI_USER and PRI_PASS and PRI_BASE)


# A password collision or a missing DASH_PASS_IDO used to be completely silent.
# Not added to _configured(): that gates the background refresher, and a missing
# personal password must never stop the data from syncing.
for _a, _b in _pass_collisions():
    print("WARNING: הסיסמה של %s זהה לזו של %s — אחד מהם מקבל את הזהות של השני" % (_a, _b),
          flush=True)
if not DASH_PASS_IDO:
    print("WARNING: DASH_PASS_IDO לא מוגדר — עידו לא יכול להתחבר והתפקיד ללא רווח מושבת", flush=True)

# DISABLE_REFRESH=1 stops the background writer (local test runs must not
# compete with production's refresher on the same Supabase windows)
if _configured() and os.environ.get("DISABLE_REFRESH") != "1":
    threading.Thread(target=_refresher, daemon=True).start()


# ---------- routes ----------

@app.get("/health")
def health():
    return JSONResponse({"ok": True, "configured": _configured(),
                         "last_sync": _state["last_sync"],
                         "last_web": _state["last_web"],
                         "last_prices": _state["last_prices"]})


@app.get("/login")
def login_get(request: Request):
    if _logged_in(request):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(_login_html())


def _is_https(request: Request) -> bool:
    return (request.headers.get("x-forwarded-proto", request.url.scheme) == "https")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


# brute-force guard: per-IP failed-attempt window (privacy-law hardening)
_fails = {}  # ip -> [timestamps]


def _too_many_fails(ip: str) -> bool:
    now = time.time()
    lst = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = lst
    return len(lst) >= 8


def _note_fail(ip: str):
    _fails.setdefault(ip, []).append(time.time())


def _log_login(request: Request, ok: bool, who: str = ""):
    try:
        sb_insert("bi_login_log", {"ip": _client_ip(request), "ok": ok, "who": who,
                                   "ua": request.headers.get("user-agent", "")[:200]})
    except Exception:
        pass


@app.post("/login")
async def login_post(request: Request):
    ip = _client_ip(request)
    if _too_many_fails(ip):
        return HTMLResponse(_login_html("יותר מדי ניסיונות — נסה שוב בעוד עשר דקות"),
                            status_code=429)
    body = (await request.body()).decode("utf-8", "replace")
    form = urllib.parse.parse_qs(body)
    p = form.get("p", [""])[0]
    if not _pass_ok(p):
        _note_fail(ip)
        _log_login(request, False, _who(p))
        return HTMLResponse(_login_html("סיסמה שגויה"), status_code=401)
    who, tok = _identity(p)          # one decision: the log and the cookie cannot disagree
    _log_login(request, True, who)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, tok, max_age=60 * 60 * 24 * 30,
                    httponly=True, secure=_is_https(request), samesite="lax")
    return resp


@app.get("/agent-report")
def agent_report(request: Request):
    # In-development preview of the agent-performance methodology (demo data) — open to all logged-in users
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    try:
        with open(os.path.join(HERE, "agent_report_demo.html"), encoding="utf-8") as f:
            body = f.read()
    except Exception:
        return HTMLResponse("<div dir='rtl' style='font-family:sans-serif;padding:40px'>הדמו לא נמצא.</div>",
                            status_code=404)
    head = ('<!DOCTYPE html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n')
    return HTMLResponse(head + body)


@app.get("/nav-preview")
def nav_preview(request: Request):
    # temporary: 4 candidate navigation designs for the owner to try and choose.
    # PUBLIC on purpose — dummy data only, no real numbers, so no login is needed to open the link.
    try:
        with open(os.path.join(HERE, "nav_preview.html"), encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except Exception:
        return HTMLResponse("<div dir='rtl' style='font-family:sans-serif;padding:40px'>הדף לא נמצא.</div>",
                            status_code=404)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


def _esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


@app.get("/logins")
def logins_view(request: Request):
    # admin-only: who logged in and when (personal credentials, e.g. דב, are labelled)
    if not _is_admin(request):
        return RedirectResponse("/login", status_code=303)
    try:
        rows = sb_select("bi_login_log?select=at,who,ok,ip&order=at.desc&limit=150")
    except Exception:
        rows = []

    def fmt(iso):
        try:
            d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(IL)
            return d.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return _esc(iso)

    trs = []
    for r in rows:
        badge = ('<span class="ok">כניסה</span>' if r.get("ok")
                 else '<span class="bad">נכשל</span>')
        trs.append('<tr><td class="t">' + fmt(r.get("at")) + '</td><td class="w">'
                   + _esc(r.get("who") or "?") + '</td><td>' + badge
                   + '</td><td class="ip">' + _esc(r.get("ip")) + '</td></tr>')
    body = "".join(trs) or '<tr><td colspan="4" class="empty">אין רישומים עדיין</td></tr>'
    # owner-only warnings — a shared password silently hands one person another's view
    warn = []
    for a, b in _pass_collisions():
        warn.append("הסיסמה של " + _esc(a) + " זהה לזו של " + _esc(b)
                    + " — אחד מהם מקבל את הזהות של השני. צריך לשנות אחת מהן.")
    if not DASH_PASS_IDO:
        warn.append("הסיסמה של עידו לא מוגדרת בשרת — הוא לא יכול להתחבר.")
    warnhtml = ("".join('<div class="warn">' + w + "</div>" for w in warn)) if warn else ""
    html = ("""<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>יומן כניסות — Divani BI</title>
<style>
:root{--bg:#f4f8f6;--card:#fff;--ink:#12201b;--ink2:#53635c;--line:#e2e9e5;--bd:#0d9668;--ok:#0b6e4f;--okbg:#e3f3ec;--bad:#a3271f;--badbg:#fbe6e4}
@media(prefers-color-scheme:dark){:root{--bg:#0f1512;--card:#19211d;--ink:#e9efeb;--ink2:#a2b0a9;--line:#26302b;--bd:#2fbf8f;--ok:#63d3a6;--okbg:#12312765;--bad:#f0968f;--badbg:#2e161465}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,'Segoe UI',Arial;padding:16px}
.wrap{max-width:640px;margin:0 auto}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:4px}
h1{font-size:1.2rem;margin:0;font-weight:800}
.back{font-size:.85rem;color:var(--bd);text-decoration:none;font-weight:700;border:1px solid var(--line);padding:8px 14px;border-radius:999px;min-height:40px;display:inline-flex;align-items:center}
.sub{font-size:.8rem;color:var(--ink2);margin:0 0 14px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
th,td{text-align:right;padding:10px 12px;font-size:.85rem;border-bottom:1px solid var(--line)}
th{font-size:.72rem;color:var(--ink2);font-weight:700;background:transparent}
tr:last-child td{border-bottom:none}
td.t{font-variant-numeric:tabular-nums;color:var(--ink2);white-space:nowrap}
td.w{font-weight:800}
td.ip{font-variant-numeric:tabular-nums;color:var(--ink2);direction:ltr;text-align:right;font-size:.78rem}
.ok{background:var(--okbg);color:var(--ok);font-size:.72rem;font-weight:700;padding:3px 9px;border-radius:6px}
.bad{background:var(--badbg);color:var(--bad);font-size:.72rem;font-weight:700;padding:3px 9px;border-radius:6px}
.empty{text-align:center;color:var(--ink2);padding:24px}
.warn{background:var(--badbg);color:var(--bad);border:1px solid var(--bad);border-radius:12px;padding:10px 12px;font-size:.82rem;font-weight:700;margin-bottom:10px}
</style></head><body><div class="wrap">
<div class="top"><h1>יומן כניסות</h1><a class="back" href="/">חזרה ללוח</a></div>
<p class="sub">מאה חמישים הכניסות האחרונות. עמודת "מי" מזהה את בעל הסיסמה.</p>
{WARN}<table><thead><tr><th>מתי</th><th>מי</th><th>תוצאה</th><th>כתובת</th></tr></thead><tbody>{ROWS}</tbody></table>
</div></body></html>""").replace("{ROWS}", body).replace("{WARN}", warnhtml)
    return HTMLResponse(html)


@app.get("/")
def index(request: Request):
    if not _logged_in(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(INDEX, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache, must-revalidate"})


def _parse_date(s: str):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


@app.get("/api/meta")
def api_meta(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if not _state["minmax"] or time.time() - _state["minmax_at"] > 600:
        _state["minmax"] = sb_rpc("bi_minmax", {})
        _state["minmax_at"] = time.time()
    mm = _state["minmax"] or {}
    today = dt.datetime.now(IL).date().isoformat()
    # the window always reaches today: the refresher keeps today synced,
    # so an empty "today" is truthful (no orders yet), not missing data
    mx = mm.get("max")
    if mx and mx < today:
        mx = today
    return JSONResponse({"min": mm.get("min"), "max": mx,
                         "today": today,
                         "last_sync": _state["last_sync"],
                         "last_rc": _state["last_rc"],
                         "refresh_minutes": REFRESH_MINUTES,
                         "line_span_days": MAX_LINE_SPAN_DAYS,
                         "admin": _can_ask(request),
                         "owner": _is_admin(request),
                         "noprofit": _is_noprofit(request)})


@app.get("/api/range")
def api_range(request: Request, d_from: str = "", d_to: str = "", by: str = "a"):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if (t - f).days <= MAX_LINE_SPAN_DAYS:
        fn = "bi_range_lines_svc" if by == "s" else "bi_range_lines"
        rows = sb_rpc(fn, {"p_from": f.isoformat(), "p_to": t.isoformat()})
        return JSONResponse({"mode": "lines", "rows": rows or []})
    if by == "s":
        agg = sb_rpc("bi_range_agents_svc", {"p_from": f.isoformat(), "p_to": t.isoformat()})
        return JSONResponse({"mode": "agents", "agg": agg or {}})
    if by == "b":
        agg = sb_rpc("bi_range_branches", {"p_from": f.isoformat(), "p_to": t.isoformat()})
        return JSONResponse({"mode": "branches", "agg": agg or {}})
    agg = sb_rpc("bi_range_agents", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "agents", "agg": agg or {}})


_DIMS = {"fam", "part", "city", "sector", "source"}

# insights panels: name -> (rpc, needs_dates, allowed dims or None)
_PANELS = {
    "pareto":    ("bi_pareto",     True,  None),
    "channels":  ("bi_channel_series", True, None),
    "contrib":   ("bi_branch_contribution", False, None),
    "trend":     ("bi_dim_series", True,  {"fam", "city", "sector", "source", "branch"}),
    "newret":    ("bi_new_ret",    True,  {"all", "sector", "source", "city"}),
    "basket":    ("bi_basket",     True,  {"all", "sector", "source", "city"}),
    "pairs":     ("bi_pairs",      True,  None),
    "pairdrill": ("bi_pair_drill", True,  None),
    "geo":       ("bi_geo_pen",    True,  None),
    "roi":       ("bi_source_roi", True,  None),
    "alerts":    ("bi_alerts",     False, None),
    "selfcheck": ("bi_selfcheck",  False, None),
}


@app.get("/api/panel")
def api_panel(request: Request, name: str = "", d_from: str = "", d_to: str = "",
              dim: str = "", a: str = "", b: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    spec = _PANELS.get(name)
    if not spec:
        return JSONResponse({"error": "bad panel"}, status_code=400)
    rpc, needs_dates, dims = spec
    if name == "contrib" and not _is_admin(request):
        return JSONResponse({"dev": True})  # owner-only feature; others get "בפיתוח"
    params = {}
    if needs_dates:
        f, t = _parse_date(d_from), _parse_date(d_to)
        if not f or not t:
            return JSONResponse({"error": "bad dates"}, status_code=400)
        if f > t:
            f, t = t, f
        params = {"p_from": f.isoformat(), "p_to": t.isoformat()}
    if dims is not None:
        if dim not in dims:
            return JSONResponse({"error": "bad dim"}, status_code=400)
        params["p_dim"] = dim
    if name == "pairdrill":
        if not (0 < len(a) <= 80 and 0 < len(b) <= 80):
            return JSONResponse({"error": "bad pair"}, status_code=400)
        params["p_anchor"], params["p_addon"] = a, b
    agg = sb_rpc(rpc, params)
    return JSONResponse({"mode": "panel", "panel": name, "agg": agg or {}})


@app.get("/api/pareto")
def api_pareto(request: Request, d_from: str = "", d_to: str = "", list_n: int = 25):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_pareto", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                               "p_list": max(1, min(list_n, 800))})
    return JSONResponse({"mode": "panel", "panel": "pareto", "agg": agg or {}})


@app.get("/api/tree")
def api_tree(request: Request, d_from: str = "", d_to: str = "",
             grp: str = "", fam: str = "", model: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if max(len(grp), len(fam), len(model)) > 120:
        return JSONResponse({"error": "bad key"}, status_code=400)
    agg = sb_rpc("bi_cat_tree", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                 "p_grp": grp or None, "p_fam": fam or None,
                                 "p_model": model or None})
    return JSONResponse({"mode": "tree", "agg": agg or {}})


@app.get("/api/segdrill")
def api_segdrill(request: Request, d_from: str = "", d_to: str = "",
                 seg: str = "", key: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if seg not in ("city", "sector", "source") or not (0 < len(key) <= 120):
        return JSONResponse({"error": "bad seg"}, status_code=400)
    agg = sb_rpc("bi_seg_drill", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                  "p_seg": seg, "p_key": key})
    return JSONResponse({"mode": "segdrill", "seg": seg, "key": key, "agg": agg or {}})


@app.get("/api/dim")
def api_dim(request: Request, d_from: str = "", d_to: str = "", dim: str = "fam",
            rank: str = "s", lim: int = 80):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if dim not in _DIMS or rank not in ("s", "q") or not (1 <= lim <= 500):
        return JSONResponse({"error": "bad dim"}, status_code=400)
    agg = sb_rpc("bi_range_dim", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                  "p_dim": dim, "p_rank": rank, "p_limit": lim})
    return JSONResponse({"mode": "dim", "dim": dim, "rank": rank, "agg": agg or {}})


@app.get("/api/flags")
def api_flags(request: Request, d_from: str = "", d_to: str = "", pct: float = 5.0):
    """Rows that need a human eye: out-of-proportion discounts, and money paid above the order."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if not _is_admin(request):
        return JSONResponse({"dev": True})   # management review — owner only
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    return JSONResponse(sb_rpc("bi_flags", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                            "p_disc_pct": pct}) or {})


@app.post("/api/flag")
async def api_flag(request: Request):
    """Approve a flagged row (with the reason) or take the approval back."""
    if not _logged_in(request) or not _is_admin(request):
        return JSONResponse({"error": "admin_only"}, status_code=403)
    body = await request.json()
    kind = (body.get("kind") or "").strip()
    ord_ = (body.get("ord") or "").strip()
    if kind not in ("disc", "overpaid") or not ord_:
        return JSONResponse({"error": "bad request"}, status_code=400)
    if body.get("undo"):
        sb_rpc("bi_flag_unapprove", {"p_kind": kind, "p_ord": ord_})
        return JSONResponse({"ok": True, "approved": False})
    note = (body.get("note") or "").strip()
    if not note:
        return JSONResponse({"error": "need_note"}, status_code=400)   # the reason is the point
    sb_rpc("bi_flag_approve", {"p_kind": kind, "p_ord": ord_, "p_note": note, "p_by": "דורון"})
    return JSONResponse({"ok": True, "approved": True})


@app.get("/api/branchsrc")
def api_branchsrc(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_branch_sources", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "branchsrc", "agg": agg or []})


@app.get("/api/moneydown")
def api_moneydown(request: Request, d_from: str = "", d_to: str = "",
                  des: str = "", scope: str = "sales"):
    """כל שורה בהזמנה שסכומה שלילי — כסף שיורד. הקיבוץ הוא לפי תיאור הפריט בקטלוג,
    והצלילה מחזירה את השורות עצמן עם הסיבה שנרשמה (אם נרשמה)."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if scope not in ("sales", "all"):
        scope = "sales"
    agg = sb_rpc("bi_money_down", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                   "p_des": des or None, "p_scope": scope})
    return JSONResponse({"mode": "moneydown", "agg": agg or {}})


@app.get("/api/cancels")
def api_cancels(request: Request, d_from: str = "", d_to: str = ""):
    """אחוז ביטולים — הזמנות שבוטלו מול הזמנות פעילות, לפי סניף ולפי נציג.
    כל חוקי הברזל בתוקף חוץ מסינון הסטטוס — הוא עצמו הנמדד."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_cancel_rate", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "cancels", "agg": agg or {}})


# ---------- one number, over time (the drill-down chart) ----------
# Every screen opens the SAME panel, so the series has to come out of one place.
# bi_series carries the iron rules and derives the bucket from the length of the
# period; this endpoint only decides who may ask and what may be asked for.
# The allow-list is here and not in the RPC on purpose: an unknown measure has to
# come back 400, not a 500 out of a raise inside plpgsql.

_SERIES_MEASURES = {
    "sales", "profit", "orders", "customers",
    "svc_sales", "svc_orders", "svc_customers",
    "cash_mz", "cash_hv", "cash_sk", "cash_ot", "cash_tot", "cash_receipts",
    "collect_net", "collect_gross", "collect_paid", "collect_disc",
    "collect_ratio", "collect_discpct",
    "dim_sales", "dim_profit", "dim_qty", "dim_orders", "dim_customers",
    "md_total", "md_orders", "md_lines", "md_noreason",
    "md_total_all", "md_orders_all", "md_lines_all", "md_noreason_all",
    "cx_written", "cx_orders", "cx_live", "cx_money", "cx_sales",
    "cx_customers", "cx_pct", "cx_mpct",
}
# What the no-profit role may not ask this endpoint for. Refused here, before the RPC
# runs: the response stripper downstream only knows key NAMES, and in this payload the
# numbers sit in "total"/"rows"/"rows_sum" like every other measure's.
#   profit / dim_profit — the profit itself.
#   md_*                — the money-down family. /api/moneydown is in _NP_BLOCK and
#                         _np_compensation strips the same figures out of a second
#                         endpoint; without them here /api/series is a third door to
#                         the identical numbers, including the per-description drill.
_SERIES_NP_BLOCK = {"profit", "dim_profit",
                    "md_total", "md_orders", "md_lines", "md_noreason",
                    "md_total_all", "md_orders_all", "md_lines_all", "md_noreason_all"}
_SERIES_DIMS = {"agent", "branch", "branchp", "fam", "grp", "part",
                "city", "sector", "source", "des"}


@app.get("/api/series")
def api_series(request: Request, d_from: str = "", d_to: str = "",
               measure: str = "", dim: str = "", key: str = "",
               bucket: str = ""):
    """סדרה בזמן של מדד אחד — הבסיס של הצלילה מכל מספר.
    הדלי (יום / שבוע / חודש) נגזר מאורך התקופה בתוך ה-RPC,
    ושם גם חלים כל חוקי הברזל. כאן רק העברה."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    m = (measure or "").strip()
    if m not in _SERIES_MEASURES:
        return JSONResponse({"error": "bad measure"}, status_code=400)
    if m in _SERIES_NP_BLOCK and _is_noprofit(request):
        return JSONResponse({"dev": True})
    d = (dim or "").strip() or None
    if d is not None and d not in _SERIES_DIMS:
        return JSONResponse({"error": "bad dim"}, status_code=400)
    if len(key or "") > 120:
        return JSONResponse({"error": "bad key"}, status_code=400)
    b = (bucket or "").strip().lower() or None
    if b is not None and b not in ("d", "w", "m"):
        return JSONResponse({"error": "bad bucket"}, status_code=400)
    agg = sb_rpc("bi_series", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                               "p_measure": m, "p_dim": d,
                               "p_key": (key if d else None), "p_bucket": b})
    return JSONResponse({"mode": "series", "agg": agg or {}})


@app.get("/api/cancelorders")
def api_cancelorders(request: Request, d_from: str = "", d_to: str = "",
                     by: str = "", key: str = ""):
    """ההזמנות שבוטלו בתקופה — הכול, או רק של סניף אחד / נציג אחד.
    by=branch/agent + key. key ריק הוא ערך אמיתי (דלי "ללא שיוך סניף"), ולכן מה שקובע
    אם מסננים הוא by ולא השאלה אם key ריק — אחרת לחיצה על אותו דלי הייתה מחזירה הכול."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_cancel_orders", {
        "p_from": f.isoformat(), "p_to": t.isoformat(),
        "p_branch": key if by == "branch" else None,
        "p_agent": key if by == "agent" else None})
    return JSONResponse({"mode": "cancelorders", "agg": agg or {}})


@app.get("/api/cancelcase")
def api_cancelcase(request: Request, ord: str = ""):
    """תיק הזמנה מבוטלת אחת — כותרת, שורות ההזמנה, ורשומות יומן הפעילות שלה."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    o = (ord or "").strip()
    if not o:
        return JSONResponse({"error": "bad request"}, status_code=400)
    agg = sb_rpc("bi_cancel_case", {"p_ord": o})
    return JSONResponse({"mode": "cancelcase", "agg": agg or {}})


@app.get("/api/compensation")
def api_compensation(request: Request, d_from: str = "", d_to: str = "",
                     reason: str = ""):
    """פיצויים ללקוחות — הכסף השלילי שרשום על מסמכים שיש עליהם דיווח תקלה,
    מול שווי אותם מסמכים. reason פותח את ההזמנות של סיבת תקלה אחת."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_compensation", {"p_from": f.isoformat(), "p_to": t.isoformat(),
                                     "p_reason": reason or None})
    return JSONResponse({"mode": "compensation", "agg": agg or {}})


@app.get("/api/dow")
def api_dow(request: Request, d_from: str = "", d_to: str = ""):
    """מחזור ומספר הזמנות לפי יום בשבוע (0=ראשון)."""
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_dow", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "dow", "agg": agg or {}})


@app.get("/api/agentreport")
def api_agentreport(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    branches = sb_rpc("bi_agent_report", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    baskets = sb_rpc("bi_agent_baskets", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"branches": branches or [], "baskets": baskets or []})


@app.get("/api/baskets")
def api_baskets(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_agent_baskets", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "baskets", "agg": agg or []})


@app.get("/api/collect")
def api_collect(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    agg = sb_rpc("bi_range_collect", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "collect", "agg": agg or {}})


@app.get("/api/cash")
def api_cash(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    pend = {"pending": _state.get("pending") or [],
            "pending_at": _state.get("pending_at")}
    if (t - f).days <= MAX_LINE_SPAN_DAYS:
        rows = sb_rpc("bi_cash_lines", {"p_from": f.isoformat(), "p_to": t.isoformat()})
        return JSONResponse({"mode": "cashlines", "rows": rows or [], **pend})
    agg = sb_rpc("bi_cash_agg", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "cashagg", "agg": agg or {}, **pend})


@app.get("/api/pending")
def api_pending(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    return JSONResponse({"pending": _state.get("pending") or [],
                         "pending_at": _state.get("pending_at")})


# ---------- pending bank transfers (העברות בהמתנה לקבלה) ----------
# A transfer is visible 1-2 days before its receipt: the confirmation screenshot
# is uploaded to the ORDER's attachments. Detection: attachment description
# matches TR_DESC_RE + the order still has an open collection balance.
# Dedup is structural: issuing the receipt zeroes PRIO_BALANCE, so the item
# leaves this list exactly when the transfer enters the cash report.
# PRIVACY (hard rule): only amount + customer name are kept; images are read
# in memory for amount extraction only and never stored.

TR_DESC_RE = re.compile("העבר|אסמכ|אמסכתא")
PENDING_SCAN_DAYS = 14


def _pri_get(path: str, timeout=90):
    auth = "Basic " + base64.b64encode(f"{PRI_USER}:{PRI_PASS}".encode("utf-8")).decode("ascii")
    out = _http(f"{PRI_BASE}/{path}", {"Authorization": auth, "Accept": "application/json"},
                timeout=timeout)
    return json.loads(out.decode("utf-8"))


def _ocr_transfer_amount(ordname: str):
    """Fetch the order's transfer attachments and read the amount via Claude
    vision. Returns float or None. Nothing but the amount leaves this function."""
    j = _pri_get(f"ORDERS?$filter=ORDNAME%20eq%20'{ordname}'&$expand=EXTFILES_SUBFORM")
    rows = j.get("value", [])
    if not rows:
        return None
    for f in (rows[0].get("EXTFILES_SUBFORM") or []):
        if not TR_DESC_RE.search(f.get("EXTFILEDES") or ""):
            continue
        name = f.get("EXTFILENAME") or ""
        data = None
        try:
            if name.startswith("http"):
                data = _http(name, {"Accept": "*/*"}, timeout=60)
            else:
                m = re.match(r"^data:[^;]+;base64,(.*)$", name, re.S)
                b64 = m.group(1) if m else name
                data = base64.b64decode(b64 + "=" * (-len(b64) % 4), validate=False)
        except Exception:
            continue
        if not data or len(data) > 5_000_000:
            continue
        if data[:3] == b"\xff\xd8\xff":
            media = "image/jpeg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            media = "image/png"
        else:
            continue  # PDFs and other types: fall back to balance estimate
        body = json.dumps({"model": ASK_MODEL, "max_tokens": 200, "messages": [{
            "role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media,
                                             "data": base64.b64encode(data).decode("ascii")}},
                {"type": "text", "text":
                    'זהו צילום אסמכתה של העברה בנקאית. החזר JSON בלבד, בלי שום טקסט נוסף: '
                    '{"amount": הסכום שהועבר בשקלים כמספר או null, '
                    '"order": "מספר ההזמנה אם כתוב בתיאור ההעברה, אחרת null"}'}]}]}).encode("utf-8")
        try:
            r = json.loads(_http("https://api.anthropic.com/v1/messages",
                                 {"x-api-key": ANTHROPIC_KEY,
                                  "anthropic-version": "2023-06-01",
                                  "Content-Type": "application/json"},
                                 data=body, timeout=90).decode("utf-8"))
            text = "".join(b.get("text", "") for b in (r.get("content") or [])
                           if b.get("type") == "text")
            m = re.search(r"\{.*\}", text, re.S)
            if not m:
                continue
            parsed = json.loads(m.group(0))
            amt = parsed.get("amount")
            ref = parsed.get("order")
            if amt is None:
                continue
            # safety: if the slip names a DIFFERENT order, skip this image
            if ref and ordname not in str(ref).replace(" ", ""):
                continue
            return round(float(amt), 2)
        except Exception as e:
            print("transfer OCR failed:", ordname, repr(e)[:150], flush=True)
    return None


def _scan_pending_transfers():
    today = dt.datetime.now(IL).date()
    pending = []
    for d in range(PENDING_SCAN_DAYS):
        day = (today - dt.timedelta(days=d)).isoformat()
        nxt = (today - dt.timedelta(days=d - 1)).isoformat()
        path = (f"ORDERS?$filter=CURDATE%20ge%20{day}T00:00:00%2B03:00"
                f"%20and%20CURDATE%20lt%20{nxt}T00:00:00%2B03:00"
                "&$select=ORDNAME,CDES,CURDATE,BRANCHNAME,TOTPRICE,PRIO_BALANCE"
                "&$expand=EXTFILES_SUBFORM($select=EXTFILEDES,UDATE)")
        try:
            rows = _pri_get(path).get("value", [])
        except Exception as e:
            print("pending scan day failed:", day, repr(e)[:120], flush=True)
            continue
        for o in rows:
            try:
                bal = float(o.get("PRIO_BALANCE") or 0)
            except (TypeError, ValueError):
                continue
            if bal < 1:  # skip zero and agorot rounding leftovers
                continue
            atts = [f for f in (o.get("EXTFILES_SUBFORM") or [])
                    if TR_DESC_RE.search(f.get("EXTFILEDES") or "")]
            if not atts:
                continue
            up = max((f.get("UDATE") or "") for f in atts)[:10]
            pending.append({"o": o.get("ORDNAME") or "", "c": o.get("CDES") or "",
                            "b": o.get("BRANCHNAME") or "", "bal": round(bal, 2),
                            "d": up})
    if ANTHROPIC_KEY:
        for item in pending:
            key = item["o"]
            if key not in _state["ocr_cache"]:
                amt = None
                try:
                    amt = _ocr_transfer_amount(key)
                except Exception as e:
                    print("pending OCR error:", key, repr(e)[:120], flush=True)
                _state["ocr_cache"][key] = amt
            item["amt"] = _state["ocr_cache"][key]
    for item in pending:
        ocr = item.get("amt")
        if ocr:
            # never show more than the open balance (partial receipts already
            # moved the rest into the cash report — no double counting)
            item["show"] = round(min(ocr, item["bal"]), 2)
        item.pop("amt", None)
    # Doron's rule: a transfer amount comes ONLY from reading the slip photo —
    # the open balance is NOT evidence (may be a pay-on-delivery remainder).
    # No amount read -> the item is not shown at all.
    _state["pending"] = [i for i in pending if i.get("show")]
    _state["pending_at"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")


# ---------- free-form questions (Ask) ----------

ASK_SYSTEM = """אתה עוזר נתונים של ויטוריו דיוואני (רשת רהיטים). ענה על שאלות חופשיות של מנהלים
על נתוני המכירות והתקבולים באמצעות שאילתות SQL (PostgreSQL) דרך הכלי run_sql.

הטבלאות (סכמה public):
1. bi_order_lines — שורת פריט בהזמנה. עמודות: ordname, ord_date (date), agent (שם סוכן),
   custname (מס' לקוח), cdes (שם לקוח), branch (קוד סניף), status, otype (סוג מסמך),
   partname (מק"ט), pdes (תיאור פריט), qprice (מכירה בש"ח לפני מע"מ), qprofit (רווח גולמי), line_no.
   כללי ברזל אלא אם נאמר אחרת: לסנן status <> 'מבוטלת' וגם cdes <> 'משמש לתחזית מכירות'.
   דוחות מכירה רגילים מחריגים גם אנשי שירות: agent not in (select agent from bi_service_agents).
   קודי סניף: 101 נתניה · 102 ראשל"צ · 103 אתר דיוואני · 105 חיפה · 106 ירושלים · 107 בית שמש ·
   '' = ללא שיוך (לפני 2024 + הזמנות שירות). otype: מכיל 'טלפוני' = ערוץ טלפוני (מוצג כסניף נפרד);
   ערכים כמו 'תיקון במקום'/'שירות החלפה'/'איסוף לתיקון' = פעולות שירות; ערכים היסטוריים כמו
   'גרופון'/'וואלה שופס'/'ערוץ הקניות' = שוקי-משנה ישנים. הזמנה = distinct ordname.
2. bi_receipt_pays — רכיב תשלום בקבלה. עמודות: ivnum, iv_date (date), branch, agent, custname,
   cdes, ordname, status, kind, means, amount, pay_date. לספור רק status = 'סופית'.
   kind: cash מזומן · transfer העברה · bit ביט · check שיק (pay_date=פירעון; שיק מזומן כאשר
   pay_date <= iv_date או ריק) · card אשראי · other. הגדרת "מזומן" של ההנהלה = cash+transfer+bit+שיק מזומן.
3. bi_service_agents — רשימת אנשי השירות (עמודה: agent).
הנתונים: מסוף 2014 ועד היום, מתעדכנים כל רבע שעה מפריוריטי.

כללים: ענה בעברית, תמציתי וישר לעניין. סכומים בש"ח עם הפרדת אלפים. ציין תמיד לאיזו תקופה
הנתון מתייחס. אם השאלה דו-משמעית — בחר פרשנות סבירה וציין אותה במשפט. תוצאת שאילתה מוגבלת
ל-200 שורות — השתמש ב-GROUP BY וסכימות, אל תשלוף שורות גולמיות. לחיפוש שם השתמש ב-ILIKE עם %.
התאריך של היום מופיע בשאלת המשתמש. אל תמציא נתונים — כל מספר חייב להגיע משאילתה."""

ASK_TOOLS = [{
    "name": "run_sql",
    "description": "מריץ שאילתת SELECT יחידה על בסיס הנתונים ומחזיר עד 200 שורות כ-JSON.",
    "input_schema": {"type": "object", "required": ["sql"],
                     "properties": {"sql": {"type": "string",
                                            "description": "שאילתת SELECT אחת, בלי נקודה-פסיק"}}},
}]


def _anthropic_call(messages):
    body = json.dumps({"model": ASK_MODEL, "max_tokens": 1500, "system": ASK_SYSTEM,
                       "messages": messages, "tools": ASK_TOOLS}).encode("utf-8")
    out = _http("https://api.anthropic.com/v1/messages",
                {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"}, data=body, timeout=120)
    return json.loads(out.decode("utf-8"))


@app.post("/api/ask")
async def api_ask(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if not _can_ask(request):
        return JSONResponse({"error": "admin_only"}, status_code=403)
    if not ANTHROPIC_KEY:
        return JSONResponse({"error": "no_key"})
    try:
        body = json.loads((await request.body()).decode("utf-8", "replace") or "{}")
    except ValueError:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    q = (body.get("q") or "").strip()[:800]
    if not q:
        return JSONResponse({"error": "empty"}, status_code=400)
    if time.time() - _state.get("last_ask", 0) < 5:
        return JSONResponse({"error": "rate"}, status_code=429)
    _state["last_ask"] = time.time()
    t0 = time.time()
    today = dt.datetime.now(IL).date().isoformat()
    messages = [{"role": "user", "content": f"התאריך היום: {today}.\nשאלה: {q}"}]
    sqls = []
    tok_in, tok_out = 0, 0
    try:
        for _ in range(8):
            r = _anthropic_call(messages)
            if r.get("type") == "error" or r.get("error"):
                detail = str(r.get("error", {}).get("message", ""))[:200]
                return JSONResponse({"error": "api", "detail": detail})
            u = r.get("usage") or {}
            tok_in += int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0) \
                + int(u.get("cache_read_input_tokens") or 0)
            tok_out += int(u.get("output_tokens") or 0)
            content = r.get("content") or []
            if r.get("stop_reason") == "tool_use":
                messages.append({"role": "assistant", "content": content})
                results = []
                for blk in content:
                    if blk.get("type") == "tool_use":
                        sql = str((blk.get("input") or {}).get("sql", ""))
                        sqls.append(sql)
                        try:
                            out = sb_rpc("bi_ask_sql", {"p_sql": sql})
                        except Exception as e:
                            out = {"error": repr(e)[:200]}
                        results.append({"type": "tool_result", "tool_use_id": blk.get("id"),
                                        "content": json.dumps(out, ensure_ascii=False)[:30000]})
                messages.append({"role": "user", "content": results})
                continue
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            ms = int((time.time() - t0) * 1000)
            cost_ils = round((tok_in * ASK_PRICE_IN + tok_out * ASK_PRICE_OUT) / 1e6 * ASK_USD_ILS, 4)
            try:
                sb_insert("bi_ask_log", {"q": q, "ok": True, "ms": ms, "sqls": sqls,
                                         "tok_in": tok_in, "tok_out": tok_out,
                                         "cost_ils": cost_ils})
            except Exception:
                pass
            return JSONResponse({"answer": text or "לא התקבלה תשובה.", "sqls": sqls,
                                 "cost_ils": cost_ils, "tok_in": tok_in,
                                 "tok_out": tok_out, "ms": ms})
        return JSONResponse({"error": "loop"})
    except Exception as e:
        try:
            sb_insert("bi_ask_log", {"q": q, "ok": False,
                                     "ms": int((time.time() - t0) * 1000), "sqls": sqls})
        except Exception:
            pass
        return JSONResponse({"error": "api", "detail": repr(e)[:200]})


@app.post("/api/refresh")
def api_refresh(request: Request):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    if time.time() - _state["last_manual"] < 60:
        return JSONResponse({"ok": False, "reason": "rate"}, status_code=429)
    _state["last_manual"] = time.time()
    today = dt.datetime.now(IL).date()
    try:
        sync_window("manual", today - dt.timedelta(days=1), today)
        rc_ok = True
        try:
            sync_receipts_window("manual", today - dt.timedelta(days=1), today)
        except Exception as e:
            rc_ok = False
            print("receipts manual-sync failed:", repr(e)[:300], flush=True)
        if ANTHROPIC_KEY:
            try:
                _scan_pending_transfers()
            except Exception as e:
                print("pending-transfers manual scan failed:", repr(e)[:300], flush=True)
        return JSONResponse({"ok": True, "last_sync": _state["last_sync"],
                             "receipts_ok": rc_ok})
    except Exception as e:
        return JSONResponse({"ok": False, "reason": repr(e)[:200]}, status_code=502)
