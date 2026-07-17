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
          "minmax_at": 0.0, "pending": [], "pending_at": None, "ocr_cache": {}}


# ---------- auth ----------

def _session_token() -> str:
    return hmac.new(DASH_PASS.encode("utf-8"), b"divani-bi-session-v1", hashlib.sha256).hexdigest()


def _admin_token() -> str:
    # keyed on the ADMIN password: the code is public, so a manager knowing the
    # shared password must not be able to derive this cookie value
    return hmac.new(DASH_PASS_ADMIN.encode("utf-8"), b"divani-bi-admin-v1", hashlib.sha256).hexdigest()


def _is_admin(request: Request) -> bool:
    if not DASH_PASS_ADMIN:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _admin_token())


def _logged_in(request: Request) -> bool:
    if not DASH_PASS:
        return False
    tok = request.cookies.get(COOKIE_NAME, "")
    return hmac.compare_digest(tok, _session_token()) or _is_admin(request)


def _match(p: str, expected: str) -> bool:
    # case-insensitive + trimmed (Likey lesson: mobile auto-capitalize lockouts)
    return bool(expected) and p.strip().casefold() == expected.strip().casefold()


def _pass_ok(p: str) -> bool:
    return _match(p, DASH_PASS) or _match(p, DASH_PASS_ADMIN)


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


PRI_SEL = ("$select=ORDNAME,CURDATE,ORDSTATUSDES,AGENTNAME,CUSTNAME,CDES,BRANCHNAME,TYPEDES"
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
                         "t": o.get("TYPEDES") or "",
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
    p = form.get("p", [""])[0]
    if not _pass_ok(p):
        _note_fail(ip)
        _log_login(request, False)
        return HTMLResponse(_login_html("סיסמה שגויה"), status_code=401)
    _log_login(request, True)
    resp = RedirectResponse("/", status_code=303)
    tok = _admin_token() if _match(p, DASH_PASS_ADMIN) else _session_token()
    resp.set_cookie(COOKIE_NAME, tok, max_age=60 * 60 * 24 * 30,
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
                         "line_span_days": MAX_LINE_SPAN_DAYS,
                         "admin": _is_admin(request)})


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


# ---------- pending bank transfers (העברות בהמתנה לקבלה) ----------
# A transfer is visible 1-2 days before its receipt: the confirmation screenshot
# is uploaded to the ORDER's attachments. Detection: attachment description
# matches TR_DESC_RE + the order still has an open collection balance.
# Dedup is structural: issuing the receipt zeroes PRIO_BALANCE, so the item
# leaves this list exactly when the transfer enters the cash report.
# PRIVACY (hard rule): only amount + customer name are kept; images are read
# in memory for amount extraction only and never stored.

TR_DESC_RE = re.compile("העבר|אסמכ|אמסכתא")
PENDING_SCAN_DAYS = 10


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
    if not _is_admin(request):
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
