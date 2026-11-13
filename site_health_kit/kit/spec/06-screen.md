# Site Health kit — spec: the screen (§6, binding)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 6. The screen (binding)

`site_health.html` implements all of this. The section exists so you can review a change against
it, and so you know what must stay true if the target project forces you to move the screen into
another framework. In that case port it one to one and make `check_screen.js` pass: its group B
feeds the page canned answers and checks the rules below one by one, against any server.

### 6.1 Layout, top to bottom

1. Header row: brand text (start side), "יציאה" link (end side).
2. Top bar: menu button (only when `nav` is not empty), the name "בריאות האתר", then buttons:
   extra `links`, `הסברים`, `רענון`, `ייצא PDF`.
3. **Red alert bar** — only when there are open alerts nobody marked as seen (§6.4).
4. Title "בריאות האתר" and subtitle `<siteLabel> · הבדיקה האחרונה HH:MM · <period>`.
5. Card **עכשיו** — four tiles (three on a site that does not measure real users) and a row of chips (§6.2).
6. Card with the **controls**: period `24 שעות | 7 ימים | 30 יום | 90 יום`, strategy `טלפון | מחשב`,
   a custom date range (`מתאריך`, `עד`, `הצג`), and the line `מוצג: <period>`.
7. Card **שורה תחתונה** — four tiles: `מהירות עמוד הבית בטלפון`, `זמינות`, `נפילות`, `התראות פתוחות`.
8. Card **זמינות** — per-page table, list of outages, chart (red bars = failed checks, green line = median response time).
9. Card **מהירות לאורך זמן** — legend of pages (tap to hide/show a line), line chart of median LCP per bucket with dashed reference lines at 2.5 s and 4 s.
10. Card **העמודים העיקריים** — table of the core pages for the chosen strategy.
11. Card **העמודים הכבדים באתר** — coverage line + the 10 heaviest pages.
12. Card **מוצרים שבורים באתר** — counts per issue + table (the first 60 on the screen, all of them in print).
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
When `/api/site/now` fails, the tiles are replaced by one grey tile `הנתון לא זמין כרגע`.

A site that does not measure real users (`real_users` is off, §7.4) gets `nowRum` in
`SH_CONFIG.hide`. The tile `מהירות אצל לקוחות, שעה אחרונה` is then not rendered at all, also
before the first round (three tiles, never one that reads `אין מדידות` for good), and the sentence
about it in the card's explanation (`<span id="nowRumTxt">`) is hidden. Without `nowRum` the card
is exactly as above.

A count of one is written in singular Hebrew everywhere on the screen (`מדידה אחת`, `כשל אחד`,
`התראה פתוחה אחת`, `יום אחד`, `נבדק לפני שנייה`), never "1 מדידות".

### 6.3 Interactions

Everything that shows a number is clickable and opens a **sheet** (bottom sheet on a phone, a
centered 720 px panel from 720 px width; closes with ✕, a click outside, or Escape). The sheet
opens on the click itself, reading `טוען…` until its data call answers:

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
then the top 6 reasons by average estimated saving (the mean over the runs that report the reason,
highest first, never more than 6), then the table of runs (first 100). The median is said in words:
`מהיר מצוין` up to 2000 ms, `מהיר` up to 2500, `בינוני` up to 4000, `איטי` above; the tag of each run
reads `מצוין` / `מהיר` / `בינוני` / `איטי` on the same thresholds. When no run of the answer
succeeded: `אין מדידות תקינות (N ניסיונות נכשלו: <err of the newest run>).` (`ניסיון אחד נכשל`
for one), and `אין מדידות תקינות.` when the answer has no run at all.

The main screen reloads every 60 seconds, **except while a sheet is open**. A reload that returns
after a newer one started is discarded (sequence guard). While loading, a thin progress bar and a
pill "טוען נתונים…" show, and the cards dim.

**A failed read is never shown as good news.** When `/api/site` fails (any status that is not 2xx
except 401, or no answer), or one of its parts is `{"error": …}` (§5.2), every tile and card that
depends on the missing data says `הנתון לא זמין כרגע` instead of 0, "אין התראות" or "עדיין לא
נבדק"; the numbers of the previous load are removed; the red bar is left as it was. The empty-state
texts ("אין התראות בתקופה. זה טוב.") appear only for data that arrived and is empty. After a failed
read the screen (and likewise the "עכשיו" card) tries once more 5 seconds later, for a phone that
woke up before its network did, and then goes back to the 60-second rhythm.

The click area of a chart point is never wider than the distance to its neighbour, so in a long
period (90 days, a 400-day range) a click on a point opens that day and not the next one.

The uptime tile reads `100%` only when no check failed; otherwise two decimals, at most `99.99%`.

### 6.4 The red alert bar

- Shown only for open alerts with `acked == false`. Text: `⚠ N התראות פעילות` (or `התראה פעילה`).
- **Collapsed by default, even for one alert.** Once opened it stays open across refreshes.
- Each row: checkbox, title, body (URLs replaced by readable page names, lines that repeat the
  title dropped) + `· מאז <opened_il>`, a link `לפתוח את העמוד ↗` when the body contains a URL, and ✕.
- Above the list: `לסמן הכול` and `מחק מסומנות (N)`.
- ✕ or bulk delete removes the rows **immediately**, without reloading the screen and without
  folding the list; one request for all the marked rows is sent in the background; on failure the
  rows come back.

### 6.5 Controls

- A period button sets `h` and clears the custom dates. `הצג` needs a start date; an empty end
  date means today (the date on the viewer's own calendar, not the UTC date); reversed dates are
  swapped.
- `טלפון` / `מחשב` changes only the speed figures. Availability is the same for both.
- `ייצא PDF` calls the browser's print. The print stylesheet (A4 landscape) hides the controls
  and the "יציאה" link and unfolds everything: all alerts, all table rows (also the broken
  products beyond the first 60), folded cards open. It always prints dark text and the light
  status colours on white, also from a device in dark mode.

### 6.6 Look

- Hebrew, right to left. Numbers in tables are left-aligned, LTR, tabular figures.
- Phone first: max width 900 px, cards with 14 px radius. The period, strategy and date controls
  are 44 px high; the other buttons are 30 to 38 px high.
- Light and dark by `prefers-color-scheme`; the colors are CSS variables at the top of the file.
- No element may cause horizontal scrolling on a phone; wide tables scroll inside their card.
- System font stack. No web fonts, no external requests at all.

### 6.7 Roles on the screen

| `SH_ROLE` | Effect |
|---|---|
| `{}` | everything |
| `{readonly: true}` | no ✕, no checkboxes, no bulk delete, no message-log card (and no call to `/api/messages`), no menu button, no extra links |
| `{readonly: true, noAlerts: true}` | also no red bar, no alerts card, no `התראות פתוחות` tile |
| `{share: true}` | as read-only, and no "יציאה" link |

Hiding the menu and the extra links is not enough for an outsider: the server leaves `nav` and
`links` out of their `SH_CONFIG` entirely (§8.2), so the owner's other screens are not even in the
page source. The screen then draws no menu button and no extra buttons, as for an empty list.

### 6.8 Translations of "what slows the page"

The runs sheet translates PageSpeed audit ids to plain Hebrew through the `OPP` table in the
script. An id that is not in the table falls back to the `title` the backend stored. Request
PageSpeed results with `locale=he` so that fallback is Hebrew too (§7.6).

### 6.9 What you may change in `site_health.html`

- Values of `SH_CONFIG` (or inject them from the server).
- Explanation sentences, when a cadence or rule really differs on this site. Two things need no
  edit, because they follow the configuration: the number of probe pages (`probeCount`), and the
  rule of the "down" alert, both in the explanation of the alerts card and in the alert sheet
  (`downAfter`: 1 = "כל כשל בודד מתריע", 2 = "רק אחרי שתי בדיקות רצופות שנכשלו"). When you edit
  an explanation sentence, keep its `<span data-txt="…">` parts: the script fills them.
- Entries of the `OPP` table and of the flow explanations in `drillHealth`.
- The color variables, if the owner asks for their brand color (`--brand`).

A card that does not apply to the site is hidden with `SH_CONFIG.hide` (§4.1), never by deleting
its markup: the script expects every card to exist. The same list takes `nowRum`, the real-user
tile of "עכשיו" (§6.2); the backend adds it when `real_users` is off. When you edit the explanation
of "עכשיו", keep `<span id="nowRumTxt">` around the sentence about that tile.

Anything else: do not change. If you believe something must change, ask the owner first.

<!-- EOF spec/06-screen.md -->
