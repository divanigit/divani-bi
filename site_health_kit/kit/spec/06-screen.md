# Site Health kit — spec: the screen (§6, binding)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 6. The screen (binding)

`site_health.html` implements all of this. The section exists so you can review a change against
it, and so you know what must stay true if the target project forces you to move the screen into
another framework. In that case port it one to one and make `check_screen.js` pass.

### 6.1 Layout, top to bottom

1. Header row: brand text (start side), "יציאה" link (end side).
2. Top bar: menu button (only when `nav` is not empty), the name "בריאות האתר", then buttons:
   extra `links`, `הסברים`, `רענון`, `ייצא PDF`.
3. **Red alert bar** — only when there are open alerts nobody marked as seen (§6.4).
4. Title "בריאות האתר" and subtitle `<siteLabel> · הבדיקה האחרונה HH:MM · <period>`.
5. Card **עכשיו** — four tiles and a row of chips (§6.2).
6. Card with the **controls**: period `24 שעות | 7 ימים | 30 יום | 90 יום`, strategy `טלפון | מחשב`,
   a custom date range (`מתאריך`, `עד`, `הצג`), and the line `מוצג: <period>`.
7. Card **שורה תחתונה** — four tiles: `מהירות עמוד הבית בטלפון`, `זמינות`, `נפילות`, `התראות פתוחות`.
8. Card **זמינות** — per-page table, list of outages, chart (red bars = failed checks, green line = median response time).
9. Card **מהירות לאורך זמן** — legend of pages (tap to hide/show a line), line chart of median LCP per bucket with dashed reference lines at 2.5 s and 4 s.
10. Card **העמודים העיקריים** — table of the core pages for the chosen strategy.
11. Card **העמודים הכבדים באתר** — coverage line + the 10 heaviest pages.
12. Card **מוצרים שבורים באתר** — counts per issue + table (first 60).
13. Card **תעודת האבטחה (המנעול)** — days left + state.
14. Card **התראות** — folded by default; the alerts of the period.
15. Card **הודעות שנשלחו לטלפון** — folded by default; the push log.
16. Card **המדידה עצמה** — one line per measurement flow with its state.

Every card has a hidden explanation paragraph; the `הסברים` button shows them all. Keep each
explanation true: if you change a cadence or a rule, change its sentence.

### 6.2 The "עכשיו" card

| Tile | Value | Color | Small line |
|---|---|---|---|
| `האתר עכשיו` | `פעיל` / `חלקי` / `נפל` / `אין נתון` | green if `all_ok`, yellow if only `any_ok`, red if none, grey without data | `נבדק לפני N שניות` (or `N דקות` from 90 s) `· בדיקה קלה` when `light` `· X מתוך Y עמודים עונים` |
| `תגובת שרת עכשיו` | home page `ms` as seconds (`0.24 שנ'`), `לא עונה` when it failed, `—` when there is no round at all | §3 thresholds; grey without data | `דף הבית · הכי איטי כרגע: <page> <time>` |
| `מהירות אצל לקוחות, שעה אחרונה` | `rum.p75_ms` as seconds, or `—` | LCP thresholds | `N צפיות בשעה האחרונה · אחוזון 75` + the source line: `מקור: האתר החי · כל N המדידות האחרונות`, or in warning color the list of sources when any row came from somewhere else; `· מתוכן N מדידות בדיקה` when there are test rows |
| `מעבדה, מדידה אחרונה` | `speed.lcp_ms` as seconds | green ≤ 2.5 s, yellow ≤ 4 s, red above | `דף הבית בטלפון, HH:MM · ציון N · יעד 2.5` |

Below: one chip per probe page (`<page> <time>` or `<page> לא עונה (status)`), colored by the
server-response thresholds; then `עודכן HH:MM:SS · רענון אוטומטי כל 60 שניות · N התראות פתוחות`.
The card reloads every 60 seconds on its own timer, also while a drill-down is open.

### 6.3 Interactions

Everything that shows a number is clickable and opens a **sheet** (bottom sheet on a phone, a
centered 720 px panel from 720 px width; closes with ✕, a click outside, or Escape):

| Click on | Opens | Data call |
|---|---|---|
| tile `מהירות עמוד הבית בטלפון` | the home page's lab runs | `what=runs&url=<bottom.url>` |
| tile `זמינות` | all failed checks + split per page | `what=fails` |
| tile `נפילות` | the outages of the period | none |
| tile `התראות פתוחות` | list of the period's alerts; each opens its detail | `what=alert&id=` |
| a row of the availability table | that page's failed checks | `what=fails&page=` |
| a red bar of the availability chart | the failed checks of that hour/day | `what=fails&bucket=` |
| a point on the green line | response time per page in that hour/day | `what=bucket&bucket=` |
| a point of the speed chart | that page's runs in that hour/day | `what=runs&url=&bucket=` |
| a row of the core / heavy tables | that page's runs + "מה מאט את העמוד" | `what=runs&url=` |
| an alert (bar, card, list) | the alert: timing, what it means, failed checks, pushes sent | `what=alert&id=` |
| a row of `המדידה עצמה` | what the flow measures and what to do | none |

The runs sheet shows: count, median, slowest, fastest, Google's real-user verdict when present,
then the top 6 reasons by average estimated saving, then the table of runs (first 100).

The main screen reloads every 60 seconds, **except while a sheet is open**. A reload that returns
after a newer one started is discarded (sequence guard). While loading, a thin progress bar and a
pill "טוען נתונים…" show, and the cards dim.

### 6.4 The red alert bar

- Shown only for open alerts with `acked == false`. Text: `⚠ N התראות פעילות` (or `התראה פעילה`).
- **Collapsed by default, even for one alert.** Once opened it stays open across refreshes.
- Each row: checkbox, title, body (URLs replaced by readable page names, lines that repeat the
  title dropped) + `· מאז <opened_il>`, a link `לפתוח את העמוד ↗` when the body contains a URL, and ✕.
- Above the list: `לסמן הכול` and `מחק מסומנות (N)`.
- ✕ or bulk delete removes the rows **immediately**, without reloading the screen and without
  folding the list; the request is sent in the background; on failure the rows come back.

### 6.5 Controls

- A period button sets `h` and clears the custom dates. `הצג` needs a start date; an empty end
  date means today; reversed dates are swapped.
- `טלפון` / `מחשב` changes only the speed figures. Availability is the same for both.
- `ייצא PDF` calls the browser's print. The print stylesheet (A4 landscape) hides the controls
  and unfolds everything: all alerts, all table rows, folded cards open.

### 6.6 Look

- Hebrew, right to left. Numbers in tables are left-aligned, LTR, tabular figures.
- Phone first: max width 900 px, cards with 14 px radius, touch targets at least 44 px high.
- Light and dark by `prefers-color-scheme`; the colors are CSS variables at the top of the file.
- No element may cause horizontal scrolling on a phone; wide tables scroll inside their card.
- System font stack. No web fonts, no external requests at all.

### 6.7 Roles on the screen

| `SH_ROLE` | Effect |
|---|---|
| `{}` | everything |
| `{readonly: true}` | no ✕, no checkboxes, no bulk delete, no message-log card, no menu, no extra links |
| `{readonly: true, noAlerts: true}` | also no red bar, no alerts card, no `התראות פתוחות` tile |
| `{share: true}` | as read-only, and no "יציאה" link |

### 6.8 Translations of "what slows the page"

The runs sheet translates PageSpeed audit ids to plain Hebrew through the `OPP` table in the
script. An id that is not in the table falls back to the `title` the backend stored. Request
PageSpeed results with `locale=he` so that fallback is Hebrew too (§7.6).

### 6.9 What you may change in `site_health.html`

- Values of `SH_CONFIG` (or inject them from the server).
- Explanation sentences, when a cadence or rule really differs on this site.
- Entries of the `OPP` table and of the flow explanations in `drillHealth`.
- The color variables, if the owner asks for their brand color (`--brand`).

A card that does not apply to the site is hidden with `SH_CONFIG.hide` (§4.1), never by deleting
its markup: the script expects every card to exist.

Anything else: do not change. If you believe something must change, ask the owner first.

<!-- EOF spec/06-screen.md -->
