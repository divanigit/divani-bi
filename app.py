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
  retroactive edits/cancellations.

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
SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
PRI_USER = os.environ.get("PRI_USER", "")
PRI_PASS = os.environ.get("PRI_PASS", "")
PRI_BASE = os.environ.get("PRI_BASE", "").rstrip("/")
REFRESH_MINUTES = max(5, int(os.environ.get("REFRESH_MINUTES", "15") or 15))

COOKIE_NAME = "dvbi_session"
MAX_LINE_SPAN_DAYS = 92

app = FastAPI(title="Divani BI", docs_url=None, redoc_url=None, openapi_url=None)

_state = {"last_sync": None, "last_rc": None, "last_manual": 0.0, "minmax": None, "minmax_at": 0.0}


# ---------- auth ----------

def _session_token() -> str:
    return hmac.new(DASH_PASS.encode("utf-8"), b"divani-bi-session-v1", hashlib.sha256).hexdigest()


def _logged_in(request: Request) -> bool:
    if not DASH_PASS:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _session_token())


def _pass_ok(p: str) -> bool:
    # case-insensitive + trimmed (Likey lesson: mobile auto-capitalize lockouts)
    return bool(DASH_PASS) and p.strip().casefold() == DASH_PASS.strip().casefold()


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


PRI_SEL = ("$select=ORDNAME,CURDATE,ORDSTATUSDES,AGENTNAME,CUSTNAME,CDES,BRANCHNAME"
           "&$expand=ORDERITEMS_SUBFORM($select=PARTNAME,PDES,QPRICE,QPROFIT)")


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
                         "pn": ln.get("PARTNAME") or "", "pd": ln.get("PDES") or "",
                         "s": round(float(ln.get("QPRICE") or 0), 2),
                         "p": round(float(ln.get("QPROFIT") or 0), 2), "ln": i})
    return n_orders, rows


def sync_window(kind: str, d_from: dt.date, d_to: dt.date):
    t0 = time.time()
    n_orders, rows = priority_pull(d_from, d_to)
    sb_rpc("bi_replace_window", {"p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
                                 "p_rows": rows})
    took = int((time.time() - t0) * 1000)
    try:
        sb_insert("bi_sync_log", {"kind": kind, "d_from": d_from.isoformat(),
                                  "d_to": d_to.isoformat(), "orders": n_orders,
                                  "lines": len(rows), "took_ms": took})
    except Exception:
        pass
    _state["last_sync"] = dt.datetime.now(IL).strftime("%d.%m.%Y %H:%M")
    _state["minmax"] = None  # bust cache


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


def _refresher():
    last_nightly = None
    while True:
        try:
            now = dt.datetime.now(IL)
            today = now.date()
            sync_window("auto", today - dt.timedelta(days=1), today)
            try:
                sync_receipts_window("auto", today - dt.timedelta(days=1), today)
            except Exception as e:
                print("receipts auto-sync failed:", repr(e)[:300], flush=True)
            if now.hour >= 3 and last_nightly != today:
                sync_window("nightly", today - dt.timedelta(days=120), today)
                try:
                    sync_receipts_window("nightly", today - dt.timedelta(days=120), today)
                except Exception as e:
                    print("receipts nightly-sync failed:", repr(e)[:300], flush=True)
                last_nightly = today
        except Exception:
            pass
        time.sleep(REFRESH_MINUTES * 60)


def _configured() -> bool:
    return bool(DASH_PASS and SB_URL and SB_KEY and PRI_USER and PRI_PASS and PRI_BASE)


# DISABLE_REFRESH=1 stops the background writer (local test runs must not
# compete with production's refresher on the same Supabase windows)
if _configured() and os.environ.get("DISABLE_REFRESH") != "1":
    threading.Thread(target=_refresher, daemon=True).start()


# ---------- routes ----------

@app.get("/health")
def health():
    return JSONResponse({"ok": True, "configured": _configured(),
                         "last_sync": _state["last_sync"]})


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


def _log_login(request: Request, ok: bool):
    try:
        sb_insert("bi_login_log", {"ip": _client_ip(request), "ok": ok,
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
    if not _pass_ok(form.get("p", [""])[0]):
        _note_fail(ip)
        _log_login(request, False)
        return HTMLResponse(_login_html("סיסמה שגויה"), status_code=401)
    _log_login(request, True)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, _session_token(), max_age=60 * 60 * 24 * 30,
                    httponly=True, secure=_is_https(request), samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


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
                         "line_span_days": MAX_LINE_SPAN_DAYS})


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


@app.get("/api/cash")
def api_cash(request: Request, d_from: str = "", d_to: str = ""):
    if not _logged_in(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    f, t = _parse_date(d_from), _parse_date(d_to)
    if not f or not t:
        return JSONResponse({"error": "bad dates"}, status_code=400)
    if f > t:
        f, t = t, f
    if (t - f).days <= MAX_LINE_SPAN_DAYS:
        rows = sb_rpc("bi_cash_lines", {"p_from": f.isoformat(), "p_to": t.isoformat()})
        return JSONResponse({"mode": "cashlines", "rows": rows or []})
    agg = sb_rpc("bi_cash_agg", {"p_from": f.isoformat(), "p_to": t.isoformat()})
    return JSONResponse({"mode": "cashagg", "agg": agg or {}})


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
        return JSONResponse({"ok": True, "last_sync": _state["last_sync"],
                             "receipts_ok": rc_ok})
    except Exception as e:
        return JSONResponse({"ok": False, "reason": repr(e)[:200]}, status_code=502)
