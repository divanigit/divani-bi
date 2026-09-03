# -*- coding: utf-8 -*-
"""דוח אקסל: מכירות דגמי הספות בשנה נתונה, דגם אחד לשורה, מהנמכר ביותר ומטה.

הבקשה, 3.9.2026: "תן לי אקסל של המכירות של דגמי הספות ב-2026 לפי שם דגם,
ממוין מהדגם הנמכר ביותר ומטה".

למה לא מסך המוצרים + כפתור האקסל: שם מסננים קטגוריה אחת בכל פעם, והספות
מפוזרות על כמה משפחות בפריוריטי (פינתיות, תלת-מושביות, משפחות "מחולל
מק׳טים"...). כאן אוספים את כולן לקובץ אחד, ומצרפים גיליון שאומר במפורש
איזו קטגוריה נכנסה ואיזו לא — כדי שאף אחד לא יצטרך לנחש מה יש בתוך המספר.

המספרים מגיעים מאותה שאילתה שמאחורי מסך המוצרים (bi_products ברמת דגם),
כך שהקובץ והמסך לעולם לא יסתרו זה את זה.

הרצה מהמחשב (עם משתני הסביבה של השרת):
    SUPABASE_URL=... SUPABASE_SECRET_KEY=... python sofa_report.py --year 2026
    python sofa_report.py --list-fams          # רק להדפיס את הקטגוריות שקיימות
    python sofa_report.py --fam-re 'ספ|פינת'   # לבחור קטגוריות אחרת
מהדשבורד: /api/sofas.xlsx?year=2026 (מחובר בלבד).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request

import xlsx

# קטגוריה של ספות: ספה/ספות, פינתי/ת, ומשפחות מחולל המק"טים שהסטים עברו
# אליהן במהלך 2025–2026 (index.html מזהיר על זה בהשוואה השנתית).
# ריפודים שאינם ספה — הדום, כורסה, כיסא, מזרן — מוחרגים במפורש גם אם
# הקטגוריה שלהם מכילה את המילה "ספה" (למשל "הדומים לספות").
DEFAULT_FAM_RE = r"ספ(ה|ות)|פינת|מחולל"
EXCLUDE_FAM_RE = r"הדו[מם]|כורס|כיסא|כסא|מזר[ןנ]|שולח|מיט(ה|ות)\b|ארון|שיד|מראה|בד(ים)?\b|כרית"

MONEY, NUM, PCT, TXT, HEAD, TITLE = "m", "n", "p", "s", "h", "t"


def year_range(year, today=None):
    """1.1 של השנה עד היום (או 31.12 אם השנה כבר נגמרה)."""
    today = today or dt.date.today()
    f = dt.date(year, 1, 1)
    t = dt.date(year, 12, 31)
    if today < t:
        t = max(f, today)
    return f, t


def split_families(families, fam_re=DEFAULT_FAM_RE, ex_re=EXCLUDE_FAM_RE):
    """מחלק את רשימת הקטגוריות לספות / לא ספות."""
    inc, exc = re.compile(fam_re), re.compile(ex_re) if ex_re else None
    sofa, other = [], []
    for f in families or []:
        f = str(f or "")
        if inc.search(f) and not (exc and exc.search(f)):
            sofa.append(f)
        else:
            other.append(f)
    return sofa, other


def is_sofa_row(row, sofa_fams):
    return str(row.get("fam") or "") in sofa_fams


def paid_units(r):
    q = float(r.get("q") or 0)
    q0 = float(r.get("q0") or 0)
    return max(0.0, q - q0)


def sort_rows(rows):
    """מהנמכר ביותר ומטה: יחידות בחיוב, אחר כך כל היחידות, אחר כך מחזור."""
    return sorted(rows, key=lambda r: (-paid_units(r), -float(r.get("q") or 0),
                                       -float(r.get("s") or 0),
                                       str(r.get("lbl") or r.get("k") or "")))


def fetch_products(rpc, d_from, d_to, fam=None, limit=2000):
    """bi_products ברמת דגם — אותה קריאה שמסך המוצרים עושה."""
    return rpc("bi_products", {"p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
                               "p_level": "model", "p_q": None,
                               "p_fam": fam, "p_model": None,
                               "p_sort": "q", "p_limit": limit}) or {}


def collect(rpc, year, fam_re=DEFAULT_FAM_RE, ex_re=EXCLUDE_FAM_RE, today=None):
    """מחזיר (שורות ממוינות, קטגוריות שנכללו, קטגוריות שלא, מ-תאריך, עד-תאריך).

    קריאה אחת בלי סינון נותנת את רשימת הקטגוריות; אחר כך קריאה לכל קטגוריית
    ספות בנפרד, כדי שתקרת השורות של השאילתה לא תבלע דגם שנמכר מעט.
    דגם שמופיע בשתי קטגוריות (נמכר גם כספה וגם כהדום, למשל) נספר פעם אחת,
    תחת הקטגוריה שבה יש לו הכי הרבה כסף — כמו במסך.
    """
    f, t = year_range(year, today)
    first = fetch_products(rpc, f, t)
    fams = first.get("families") or sorted({str(r.get("fam") or "")
                                             for r in (first.get("rows") or [])})
    sofa_fams, other = split_families(fams, fam_re, ex_re)
    sofa_set = set(sofa_fams)
    by_key = {}
    for fam in sofa_fams:
        for r in (fetch_products(rpc, f, t, fam=fam).get("rows") or []):
            if not is_sofa_row(r, sofa_set):
                continue
            k = str(r.get("k") or r.get("lbl") or "")
            if k not in by_key or float(r.get("s") or 0) > float(by_key[k].get("s") or 0):
                by_key[k] = r
    # רשת ביטחון: דגם ספה שהקריאה הראשונה ראתה ושום קריאה-לפי-קטגוריה לא החזירה.
    for r in (first.get("rows") or []):
        k = str(r.get("k") or r.get("lbl") or "")
        if is_sofa_row(r, sofa_set) and k not in by_key:
            by_key[k] = r
    return sort_rows(by_key.values()), sofa_fams, other, f, t


def build_workbook(rows, sofa_fams, other_fams, d_from, d_to, profit=True, stamp=None):
    """הקובץ עצמו. profit=False משמיט את עמודות הרווח (למשתמש ללא רווח)."""
    stamp = stamp or dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    year = d_from.year
    title = "מכירות דגמי ספות %d" % year
    sub = ("%s–%s · לפי שם דגם · ממוין מהנמכר ביותר ומטה (יחידות בחיוב) · הופק %s"
           % (d_from.strftime("%d.%m.%Y"), d_to.strftime("%d.%m.%Y"), stamp))

    head = ["#", "דגם", "קטגוריה", 'מק"טים', "יחידות בחיוב", "כל היחידות",
            "מהן ללא חיוב", "מחזור ₪"]
    if profit:
        head += ["רווח גולמי ₪", "אחוז רווח"]
    head += ["מחיר ליחידה ₪", "הזמנות", "לקוחות", "נתח מהיחידות"]

    tot_paid = sum(paid_units(r) for r in rows) or 0.0
    body = []
    T = {"skus": 0, "paid": 0.0, "q": 0.0, "q0": 0.0, "s": 0.0, "p": 0.0, "n": 0, "c": 0}
    for i, r in enumerate(rows, 1):
        s, p = float(r.get("s") or 0), float(r.get("p") or 0)
        paid = paid_units(r)
        pm = (p / s) if s > 0 else None
        unit = r.get("unit")
        if unit is None and paid > 0 and s > 0:
            unit = s / paid
        line = [(i, NUM), (str(r.get("lbl") or r.get("k") or ""), TXT),
                (str(r.get("fam") or ""), TXT), (r.get("skus") or 0, NUM),
                (paid, NUM), (r.get("q") or 0, NUM), (r.get("q0") or 0, NUM), (s, MONEY)]
        if profit:
            line += [(p, MONEY), (pm, PCT) if pm is not None else ("—", TXT)]
        line += [((unit, MONEY) if unit is not None else ("—", TXT)),
                 (r.get("n") or 0, NUM), (r.get("c") or 0, NUM),
                 ((paid / tot_paid) if tot_paid else 0.0, PCT)]
        body.append(line)
        T["skus"] += int(r.get("skus") or 0); T["paid"] += paid
        T["q"] += float(r.get("q") or 0); T["q0"] += float(r.get("q0") or 0)
        T["s"] += s; T["p"] += p; T["n"] += int(r.get("n") or 0); T["c"] += int(r.get("c") or 0)

    total = [("", TXT), ("סך הכול", HEAD), ("%d דגמים" % len(rows), TXT), (T["skus"], NUM),
             (T["paid"], NUM), (T["q"], NUM), (T["q0"], NUM), (T["s"], MONEY)]
    if profit:
        total += [(T["p"], MONEY), (T["p"] / T["s"], PCT) if T["s"] > 0 else ("—", TXT)]
    total += [(T["s"] / T["paid"], MONEY) if T["paid"] > 0 else ("—", TXT),
              (T["n"], NUM), (T["c"], NUM), (1.0 if tot_paid else 0.0, PCT)]

    sheet1 = [[(title, TITLE)], [(sub, TXT)], [],
              [(h, HEAD) for h in head]] + body + [[], total]
    if not rows:
        sheet1.append([("לא נמצאו דגמי ספות בתקופה. בדוק את גיליון הקטגוריות.", TXT)])
    sheet1.append([])
    sheet1.append([("יחידות בחיוב = כל היחידות פחות שורות במחיר אפס (בדים, תוספות, "
                    "פריטי חבילה שמחירם מגולם במוצר). מחיר ליחידה מחושב על היחידות שחויבו בלבד. "
                    "הזמנות ולקוחות בשורת הסיכום הם סכום השורות, ולכן הזמנה עם שני דגמים נספרת פעמיים.", TXT)])
    w1 = [5, 30, 22, 9, 13, 12, 13, 15] + ([15, 11] if profit else []) + [15, 10, 10, 13]

    sheet2 = [[("איזו קטגוריה נכנסה לדוח", TITLE)],
              [("קטגוריה = משפחת המוצר בפריוריטי. דגם שנמכר בכמה קטגוריות מוצג תחת זו שבה יש לו הכי הרבה כסף.", TXT)],
              [], [("קטגוריה", HEAD), ("בדוח?", HEAD)]]
    for f in sofa_fams:
        sheet2.append([(f, TXT), ("כן", TXT)])
    for f in other_fams:
        sheet2.append([(f, TXT), ("לא", TXT)])
    return xlsx.build([("דגמי ספות %d" % year, sheet1, w1),
                       ("קטגוריות", sheet2, [34, 9])])


def file_name(year, stamp=None):
    stamp = stamp or dt.datetime.now().strftime("%d.%m.%Y")
    return "מכירות דגמי ספות %d %s.xlsx" % (year, stamp)


# ---------- הרצה מהמחשב ----------

def _env_rpc():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        sys.exit("חסרים SUPABASE_URL / SUPABASE_SECRET_KEY בסביבה.")

    def rpc(fn, params):
        req = urllib.request.Request(
            f"{url}/rest/v1/rpc/{fn}", data=json.dumps(params).encode("utf-8"),
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = r.read()
        return json.loads(out.decode("utf-8")) if out else None
    return rpc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", type=int, default=dt.date.today().year)
    ap.add_argument("--out", default="", help="נתיב הקובץ (ברירת מחדל: שם בעברית בתיקייה הנוכחית)")
    ap.add_argument("--fam-re", default=DEFAULT_FAM_RE, help="ביטוי רגולרי לקטגוריות של ספות")
    ap.add_argument("--exclude-re", default=EXCLUDE_FAM_RE, help="ביטוי רגולרי לקטגוריות שמוחרגות")
    ap.add_argument("--no-profit", action="store_true", help="בלי עמודות רווח")
    ap.add_argument("--list-fams", action="store_true", help="רק להדפיס את הקטגוריות ולצאת")
    a = ap.parse_args(argv)

    rpc = _env_rpc()
    rows, sofa_fams, other, f, t = collect(rpc, a.year, a.fam_re, a.exclude_re)
    if a.list_fams:
        print("נכנסות לדוח:"); [print("  +", x) for x in sofa_fams]
        print("לא נכנסות:");  [print("  -", x) for x in other]
        return 0
    blob = build_workbook(rows, sofa_fams, other, f, t, profit=not a.no_profit)
    out = a.out or file_name(a.year)
    with open(out, "wb") as fh:
        fh.write(blob)
    print(f"{len(rows)} דגמים, {len(sofa_fams)} קטגוריות -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
