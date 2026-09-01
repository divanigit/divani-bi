# -*- coding: utf-8 -*-
"""כותב קובץ אקסל אמיתי, בלי שום ספרייה חיצונית.

דורון, 2.9.2026: "תעשה לי כפתור הדפסת נתונים לאקסל מכל מסך ב-OWL בנוסף ל-PDF".

למה קובץ אמיתי ולא CSV: הנקודה כולה היא להמשיך לעבוד עם המספרים. ב-CSV
"1,558,025 ש"ח" מגיע כטקסט, ואקסל בעברית מפרש מפרידים לפי הגדרות המחשב —
כלומר אותו קובץ נפתח אחרת אצל שני אנשים. כאן כל מספר נשלח כמספר עם פורמט
תצוגה, והסכומים מסתכמים בלי לגעת בכלום.

xlsx הוא ZIP של קובצי XML, ו-zipfile היא ספריית תקן — לכן אין כאן תלות
חדשה שצריך לפרוס. המחרוזות נשלחות inline ולא בטבלת מחרוזות משותפת: פחות
קוד, ואותה תוצאה בקובץ שנפתח פעם אחת ולא נערך.
"""
import io, re, zipfile

# פורמטים. הקודים 164 ומעלה שמורים לפורמטים מותאמים; מתחתם הם מובנים
# באקסל ומשתנים לפי שפת ההתקנה.
FMT_MONEY, FMT_PCT, FMT_NUM = 164, 165, 166

_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}
_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def esc(s):
    s = _BAD.sub("", str(s))
    return "".join(_ESC.get(c, c) for c in s)


def col_name(i):
    """0 -> A, 25 -> Z, 26 -> AA."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# שם גיליון: אקסל אוסר חמישה תווים, אוסר גרשיים בקצוות, וקוצב לשלושים ואחד.
_SHEET_BAD = re.compile(r"[\[\]\*/\\\?:]")


def sheet_name(s, used):
    s = _SHEET_BAD.sub(" ", str(s or "גיליון")).strip().strip("'")
    s = (s or "גיליון")[:31]
    base, n = s, 2
    while s.casefold() in used:
        suf = " (%d)" % n
        s = base[:31 - len(suf)] + suf
        n += 1
    used.add(s.casefold())
    return s


def _cell(ref, val, kind):
    """תא אחד. kind: n מספר · m כסף · p אחוז · s טקסט · h כותרת · t כותרת ראשית."""
    if kind in ("n", "m", "p"):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, esc(val))
        st = {"m": 2, "p": 3, "n": 4}[kind]
        # אינסוף ו-NaN אינם מספרים חוקיים ב-XML של אקסל, והם פותחים קובץ פגום.
        if v != v or v in (float("inf"), float("-inf")):
            return '<c r="%s" t="inlineStr"><is><t>—</t></is></c>' % ref
        return '<c r="%s" s="%d"><v>%.10g</v></c>' % (ref, st, v)
    st = {"h": 5, "t": 1}.get(kind, 0)
    return ('<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (ref, (' s="%d"' % st) if st else "", esc(val)))


def _sheet(rows, widths):
    """rows: רשימת שורות, כל שורה רשימת (ערך, סוג)."""
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           # הגיליון עצמו מימין לשמאל, אחרת עמודה א\' נוחתת בשמאל והטבלה
           # נקראת הפוך ממה שהיא במסך.
           '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>',
           '<sheetFormatPr defaultRowHeight="15"/>']
    if widths:
        out.append("<cols>")
        for i, w in enumerate(widths):
            out.append('<col min="%d" max="%d" width="%.1f" customWidth="1"/>'
                       % (i + 1, i + 1, w))
        out.append("</cols>")
    out.append("<sheetData>")
    for r, row in enumerate(rows, 1):
        out.append('<row r="%d">' % r)
        for c, cell in enumerate(row):
            val, kind = cell
            if val is None or val == "":
                continue
            out.append(_cell(col_name(c) + str(r), val, kind))
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3">
<numFmt numFmtId="%d" formatCode="#,##0&quot; ₪&quot;"/>
<numFmt numFmtId="%d" formatCode="0.0%%"/>
<numFmt numFmtId="%d" formatCode="#,##0"/>
</numFmts>
<fonts count="3">
<font><sz val="11"/><name val="Arial"/></font>
<font><b/><sz val="13"/><name val="Arial"/></font>
<font><b/><sz val="11"/><name val="Arial"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F3EC"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="%d" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="%d" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="%d" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>""" % (FMT_MONEY, FMT_PCT, FMT_NUM, FMT_MONEY, FMT_PCT, FMT_NUM)


def build(sheets):
    """sheets: [(name, rows, widths)] -> bytes של קובץ xlsx.

    שמות הגיליונות מנוקים כאן ולא באחריות הקורא. שם עם / או [ ], או ארוך
    מ-31 תווים, פותח "הקובץ פגום" בלי שום רמז מאיפה — וזו תקלה שקל מדי
    להכניס פעם אחת ולא למצוא.
    """
    if not sheets:
        sheets = [("גיליון", [[("אין נתונים", "s")]], None)]
    used = set()
    sheets = [(sheet_name(nm, used), rows, w) for nm, rows, w in sheets]
    n = len(sheets)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(1, n + 1):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
    ct.append("</Types>")

    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
          "<sheets>"]
    for i, (name, _rows, _w) in enumerate(sheets, 1):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (esc(name), i, i))
    wb.append("</sheets></workbook>")

    rel = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, n + 1):
        rel.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>'
                   % (i, i))
    rel.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
               'officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (n + 1))
    rel.append("</Relationships>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rel))
        z.writestr("xl/styles.xml", STYLES)
        for i, (_name, rows, widths) in enumerate(sheets, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, _sheet(rows, widths))
    return buf.getvalue()
