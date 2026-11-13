# Site Health screen — build specification

This document tells a coding agent how to build the **"בריאות האתר" (Site Health)** screen for any
website: a phone-first page that shows, at a glance, whether the site is up, how fast it is, what is
broken, and what alerts fired, plus the measuring machinery behind it.

It is a port of a screen that runs in production at a furniture retailer. Everything about the
screen itself (layout, texts, thresholds, interactions, the JSON it reads) is taken from that
production code and is **binding**. The measuring machinery behind it is described as a reference
design that you may adapt to the target project's stack, as long as the contracts in §5 hold.

Files in this kit:

| File | What it is | Status |
|---|---|---|
| `SPEC.md` | this document | read all of it before writing code |
| `AGENTS.md` | standing rules for the target repository | copy to the target repo root (merge if one exists) |
| `site_health.html` | the screen: one HTML file, no build step, no libraries | **use it as is**; change only `SH_CONFIG` values and texts listed in §6.9 |
| `mock_server.py` | fake backend that answers every data call with realistic data (stdlib only) | run it to see the screen; it is the contract by example |
| `check_screen.js` | acceptance test of the screen (Playwright) | must pass before you call the screen done |
| `reference/` | tested reference backend: SQL schema and functions, server, collectors, tests | adapt to the target stack or use as is |

Do not retype `site_health.html` from memory or "improve" it. Copy the file.

Paths in this document are relative to the kit folder (`site_health_kit/` after unpacking).

---

## 1. How to work on this task

1. **Unpack and look first.** Run `python3 mock_server.py` and open `http://localhost:8787/site` at a
   phone width (390 px). That is the finished screen. Then run `node check_screen.js` (needs
   Playwright; if it is not available, say so and continue).
2. **Ask the owner the intake questions in §2 before building the backend.** Do not guess the site's
   pages, who gets alerts, or where the system will be hosted.
3. **Build in the phases of §9, in order.** Each phase ends with checks that you run and report.
   Do not start a phase while the previous phase's checks fail.
4. **Never invent a number.** Every figure on the screen comes from a stored measurement. If a
   collector has not run yet, the card shows its empty state (the screen already handles this).
   No placeholder data in production, no "sample" rows left in the database.
5. **Secrets live in environment variables / the platform's secret store only.** Never in the
   repository, never in the HTML, never in a chat message. If you need a key, tell the owner
   where to paste it; do not ask them to send it to you.
6. **No customer data.** This system stores no names, emails, phone numbers, order numbers or IP
   addresses of the site's visitors. URLs are stored without query strings. Account, checkout
   and order pages are never measured by the real-user collector (§7.7).
7. **Be a polite client of the monitored site.** One probe round per minute, a distinct
   `User-Agent`, hard timeouts, no parallel load beyond what §7 defines. Never run load tests.
8. **When something external blocks you** (a key is missing, an API refuses, a host is not
   reachable from your sandbox), stop that item, say exactly what is missing and who can
   provide it, and continue with the parts that do not depend on it.

### How to talk to the owner

The owner is not a developer. Unless they tell you otherwise:

- Write to them in **Hebrew**, in short messages and plain words. No technical terms; if one is
  unavoidable, explain it in half a sentence.
- **One decision per message.** A question states what happens if the answer is yes, what happens
  if it is no, and whether it can be changed later.
- Every time you introduce something new, say three things: what it is, what they need to do with
  it, and what they get out of it.
- End every message with one line: what the owner needs to do now (or "אתה לא צריך לעשות כלום").
- Report results honestly: if a check failed, say so and show which one.

---

## 2. Intake: what to find out before building

Find the answers yourself where you can (open the site, read its sitemap, detect the platform),
then confirm with the owner in one short message per topic. Record the answers in
`site_health.config.json` in the target repo (no secrets in it).

| # | Topic | What you need | How to find it / default |
|---|---|---|---|
| 1 | The site | Public address, e.g. `https://example.co.il` | Ask. Check that `www` and non-`www` resolve and which one is canonical. |
| 2 | Platform | WordPress + WooCommerce, Shopify, other | `/wp-json/` answers → WordPress; `/wp-json/wc/store/v1/products?per_page=1` answers → WooCommerce; `/products.json?limit=1` answers → Shopify. |
| 3 | Probe pages (default 4) | The pages checked every minute, each with a short Hebrew name | Default for a shop: home (`בית`), one category, one product, the cart. For a non-shop: home plus the 3 pages that earn the most. Pick pages that exercise different parts of the server (cached and uncached). The home page must be one of them and its name goes into `SH_CONFIG.homePage`. |
| 4 | Core pages (default 5) | The pages whose speed is measured every 15 minutes | Default: the probe pages plus one more important page (for a shop: checkout or a second category). Only pages that are reachable without logging in or filling a cart. |
| 5 | Who gets alerts | The people who should get a push on their phone | Each installs the ntfy app and subscribes to one topic (§7.9). Ask who. |
| 6 | Who may view | Owner; staff; outside vendors (read-only); a share link | Default: owner only. Offer the vendor role when the owner mentions an agency or a developer. |
| 7 | Hosting | Where the database and the small server will run | Default: Supabase (database) + one small always-on web service (for example Render). If the owner already has a dashboard project on some stack, the screen is added to it. |
| 8 | Alert rule for "down" | Alert on the first failed check, or only after 2 in a row | Production default is 1 (the owner wanted to know about every blip). Explain the trade-off: 1 = more noise, nothing missed. |
| 9 | Google key | A PageSpeed Insights API key (free) | The owner creates it in Google Cloud and pastes it into the host's environment settings. Without it the speed cards stay in their empty state. |

Do not ask the owner about thresholds, colors, wording, cadences or anything else defined in this
document. Those are decided.

---

## 3. What the system does

```
 monitored website  <──── probes, speed tests, catalogue + sitemap reads, certificate check ────  collectors
        │                                                                                              │ write
        └── visitors' browsers send one tiny speed measurement per page view ──────► ingest ──►   database
                                                                                                       │
                              alert rules (every minute) ──► push to phones (ntfy) ◄──────────────────┤
                                                                                                       │ read functions
                                                                              small server: login, roles, JSON
                                                                                                       │
                                                                                         the screen (one HTML file)
```

Collectors and their cadence (all times are the site's local time zone):

| Flow name (exact Hebrew, used on the screen) | What it does | Cadence |
|---|---|---|
| `בודק זמינות האתר` | requests every probe page, records ok / HTTP status / time to response | full round every minute; light round at the half minute |
| `מדידת מהירות — עמודי ליבה` | lab speed test (Google PageSpeed Insights) of each core page | phone: every 15 minutes; desktop: every hour |
| `מדידת מהירות — סבב כל האתר` | lab speed test of every page of the site, in rotation | 2 pages every 5 minutes (phone) |
| `טעינת מפת האתר` | reads the sitemap so the rotation knows every page | once a night |
| `בדיקת תעודת האבטחה` | reads the TLS certificate's expiry | once a day |
| `בדיקת מוצרים שבורים` | reads the public catalogue; flags products without price / image / stock / add-to-cart | once a day at 04:00 (shops only) |
| `מהירות אצל לקוחות` | real visitors' browsers report time to main content | every page view |
| alert rules | open / close alerts, send pushes, keep the message log | every minute |

The thresholds below are used everywhere (screen, alerts, texts). Do not change them.

| Measure | Green | Yellow | Red |
|---|---|---|---|
| Server response of a probe ("now" tiles) | ≤ 500 ms | ≤ 1500 ms | > 1500 ms, or the page did not answer |
| Time to main content, LCP (lab and real users) | ≤ 2000 ms "מצוין", ≤ 2500 ms "מהיר" | ≤ 4000 ms "בינוני" | > 4000 ms "איטי" |
| Certificate days left | ≥ 30 | 14–29 | < 14, or the check failed |
| Measurement flow | `תקין` | `מתעכב` | `שקט` (grey: `אין נתון`) |

Definitions that the texts on the screen promise (keep them true):

- **Availability** = share of full-round checks that answered correctly. Light rounds are not counted.
- **Outage (נפילה)** = 3 or more consecutive minutes in which **no** probe page answered.
- **Alert opens** when: one availability check fails (or N in a row, intake #8); a core page is
  slower than 4 seconds twice in a row; a measurement flow stops; the certificate has fewer than
  14 days left. **It closes by itself** when the condition clears.
- **"ראיתי" (✕)** hides an open alert from the red bar for everybody until that alert closes. It
  does not close it. If the problem comes back later, that is a new alert and it shows again.

---

## 4. Per-site configuration

Everything site-specific sits in two places.

**4.1 The screen: `SH_CONFIG`** (defaults are at the top of the script in `site_health.html`; the
server overrides them by injecting one inline script at the `<!--SH_INJECT-->` marker in `<head>`):

| Key | Meaning | Default |
|---|---|---|
| `siteLabel` | shown under the title and in the tab title | `'example.co.il'` |
| `brand` | small text at the top (business or system name); empty = none | `''` |
| `homePage` | the value of `page` for the home page, exactly as the data returns it | `'בית'` |
| `probeCount` | number of probe pages (used in explanation texts only) | `4` |
| `coreCount` | number of core pages (used in explanation texts only) | `5` |
| `liveHosts` | values of the real-user source that mean "the live site" | `['live', siteLabel, 'www.' + siteLabel]` |
| `pathLabels` | URL path prefixes turned into readable Hebrew labels | WooCommerce: `[['/product-category/','קטגוריה: '],['/product/','מוצר: ']]`; Shopify: `[['/collections/','קטגוריה: '],['/products/','מוצר: ']]` |
| `bucketNote` | a note under the "server response per page" drill-down; empty = none | `''` |
| `nav` | menu entries to other screens of the same system; empty = no menu button | `[]` |
| `here` | this screen's path in `nav` | `'/site'` |
| `links` | extra buttons in the top bar | `[]` |
| `api` | base path of the data calls | `'/api'` |
| `loginPath`, `logoutPath` | | `'/login'`, `'/logout'` |
| `shareKey` | share-link token; when set it is appended to every data call as `k=` | `''` |
| `hide` | ids of cards that do not apply to this site: `'issuesCard'` (a site that sells nothing), `'slowCard'` (no sitemap rotation) | `[]` |

and the viewer's role, `SH_ROLE` (§8): `{}` for owner and staff, `{readonly: true}` for a vendor,
`{readonly: true, noAlerts: true}` for a vendor who must not see alerts, `{share: true}` for the
share link. The role object only hides controls; **the server enforces the same rules itself**.

**4.2 The backend:** probe pages, core pages, time zone, alert rule, ntfy topic, PageSpeed key,
passwords. In the reference implementation these are rows in `sh_pages` plus environment
variables (`reference/README.md` lists them).

---

## 5. API contract (binding)

The screen calls five data endpoints (§5.2–§5.6). Field names, types and the literal Hebrew
values below are what `site_health.html` reads; `mock_server.py` returns exactly these shapes.
Your server must return the same.

Conventions:

- All `*_il` fields and `at` strings are **preformatted in the site's local time zone** by the
  backend, as `DD.MM HH:MM` (24-hour). The screen prints them unchanged.
- `bucket` is a local-time string: `YYYY-MM-DD HH:00` for hourly buckets, `YYYY-MM-DD` for daily
  buckets. Rule: windows up to 72 hours use hourly buckets, longer windows use daily buckets. The
  screen tells them apart by length (`> 10` = hourly) and reads characters 5–7 (month), 8–10
  (day), 11–16 (time).
- Durations are integers in **milliseconds** unless stated. `null` means "no value" and is always
  tolerated; the screen prints `—`.
- Rows are displayed in the order the server sends them. Sort on the server as stated per list.
- Counts, ids, durations and scores are JSON **numbers**. The screen escapes every text field but
  writes numeric fields into the page as they are, so a numeric field must never carry text that
  came from outside (a visitor's beacon, a page of the site).
- The Hebrew literals marked *(literal)* are compared by the screen character for character.

### 5.1 The time window (shared by all calls)

Query parameters: either `h=<hours>` (integer; the screen sends 24, 168, 720 or 2160) or
`f=<YYYY-MM-DD>&t=<YYYY-MM-DD>` (local dates, `t` inclusive: the window ends at the end of day `t`).
Rules (`_range_args` in the production server):

- With `f`: window = `[f 00:00 local, (t + 1 day) 00:00 local)`, by calendar days in the site's
  time zone (a day with a clock change is 23 or 25 hours long). Without `t`: until now. If the end
  is not after the start: end = start + 1 day. Invalid dates: fall back to `h`. `t` without `f` is ignored.
- Without `f`: `h` is clamped to `1 … 9600` (400 days); missing or not a number → 24; zero or
  negative → 1. Window = `[now − h hours, now + 1 minute)` in real elapsed hours.
- `hours` in the answer is the real length of the window in whole hours.

### 5.2 `GET /api/site?strategy=mobile|desktop&(h | f,t)` → everything the screen needs

```jsonc
{
  "hours": 24, "from": "<ISO 8601>", "to": "<ISO 8601>", "strategy": "mobile",

  "availability": [
    // one row per probe page; sort: the order of the probe pages in the configuration
    { "section": "לפי עמוד",            // (literal)
      "page": "בית", "checks": 1440, "failed": 2,
      "fail_pct": "0.14",               // number or string, already rounded to 2 decimals; printed + "%"
      "p50_ms": 284, "p95_ms": 870,     // percentiles of response time over the checks that answered
      "last_fail_il": "13.11 09:41" },  // null if no failure in the window
    // then one row per outage; any section value other than "לפי עמוד" marks an outage. Sort: oldest first
    { "section": "נפילות", "outage_minutes": 7, "outage_start_il": "13.11 03:12", "outage_end_il": "13.11 03:19" }
  ],

  "availability_series": [              // one row per bucket that has checks; sort: bucket ascending
    { "bucket": "2026-11-13 09:00", "checks": 240, "failed": 1, "ms_p50": 310, "ms_p95": 900 }
  ],

  "speed": [
    // exactly one "bottom line" row: the home page on a phone, whatever `strategy` is
    { "section": "שורה תחתונה",          // (literal)
      "url": "https://example.co.il/", "lcp_p50": 2310, "checks": 96,
      "verdict": "מהיר" },              // מצוין | מהיר | בינוני | איטי, by the LCP thresholds of §3
    // one row per core page AND per strategy (send both strategies; the screen filters)
    { "section": "ליבה",                // (literal)
      "strategy": "mobile", "page": "בית", "url": "https://example.co.il/",
      "lcp_p50": 2310, "lcp_p95": 3900, "score_med": 64, "cls_med": 0.03, "ttfb_p50": 420,
      "slow_runs": 3,                   // successful runs with LCP > 4000 ms
      "checks": 96,                     // successful runs in the window
      "crux_category": "FAST",          // FAST | AVERAGE | SLOW | null — Google's real-user verdict from the latest run
      "crux_lcp": 2100 },               // ms, or null
    // up to 10 rows: the heaviest pages of the whole-site rotation; sort: lcp_p50 descending
    { "section": "האיטיים באתר",         // (literal)
      "page": "https://example.co.il/product/x/",   // the URL again; the screen shortens it for display
      "url":  "https://example.co.il/product/x/",
      "lcp_p50": 7100, "score_med": 21, "checks": 2, "last_il": "13.11 08:10" },
    // exactly one coverage row (column names are reused, this is not a typo)
    { "section": "כיסוי",               // (literal)
      "checks": 288,                    // distinct pages measured by the rotation in the window
      "slow_runs": 412 }                // number of pages the rotation knows (from the sitemap)
  ],

  "speed_series": [                     // for the requested strategy only; one row per core page per bucket
    { "page": "בית", "url": "https://example.co.il/", "bucket": "2026-11-13 09:00", "lcp_p50": 2400 }
  ],

  "alerts_open": [                      // every alert that is open now; sort: newest first
    { "id": 41, "kind": "down", "title": "האתר לא עונה: סל",
      "body": "קוד 502\nhttps://example.co.il/cart/",   // plain text; a URL in it becomes the "open the page" link
      "opened_il": "13.11 11:02",
      "acked": false }                  // true = someone pressed ✕; hidden from the red bar, still counted as open
  ],
  "alerts_recent": [                    // alerts that were open at any time inside the window; sort: newest first
    { "id": 38, "kind": "down", "title": "…", "body": "…", "open": false,
      "opened_il": "13.11 01:20", "closed_il": "13.11 01:27",   // closed_il null while open
      "minutes": 7 }                    // duration so far (open) or total (closed)
  ],

  "health": [                           // one row per measurement flow of §3; sort: the order of §3
    { "flow_name": "בודק זמינות האתר",   // (literal for this one: the subtitle shows its last_at)
      "status": "תקין",                 // תקין | מתעכב | שקט | אין נתון  (literals)
      "cadence": "כל דקה",              // free text
      "silent_txt": null,               // short text when not ok, e.g. "שקט כבר 6 שעות"
      "last_at": "<ISO 8601>",          // last successful run; null if never
      "warn_minutes": 5, "late_minutes": 15,   // age above warn = מתעכב, above late = שקט
      "note": null }                    // shown in the drill-down when the screen has no built-in text for flow_name
  ],

  "product_issues": [                   // from the latest catalogue snapshot only; sort: "לא במלאי" last, then by issue, then name
    { "issue": "לא במלאי",              // "לא במלאי" (literal, shown yellow); any other text is shown red
      "name": "ספה תלת מושבית", "url": "https://example.co.il/product/…/", "snap_date": "2026-11-13" }
  ],

  "cert": { "host": "example.co.il", "issuer": "Let's Encrypt R11", "not_after": "<ISO 8601>",
            "days_left": 23, "ok": true, "err": null, "checked_at": "<ISO 8601>" }   // or null before the first check
}
```

**Each part fails alone.** The eight lists and `cert` are nine parts, computed independently and
in parallel; if one fails, its key holds `{"error": "<text>"}` instead of its value, and the rest
of the answer is still returned with status 200. The screen treats a non-list as empty. Error
texts must not contain host names, user names or keys.

Issue labels used in production: `בלי מחיר`, `בלי תמונה`, `לא במלאי`, `אי אפשר להוסיף לסל`.

### 5.3 `GET /api/site/now` → the "עכשיו" card (refreshed every 60 s)

```jsonc
{
  "pages":  [ { "page": "בית", "url": "https://example.co.il/", "ok": true, "status": 200, "ms": 240 } ],
            // the last FULL round, one row per probe page; ms is null when the page did not answer.
            // Empty when there was no full round in the last 15 minutes.
  "latest": [ { "page": "בית", "ok": true } ],   // the most recent round of any kind (full or light)
  "light": false,          // true when `latest` is a light round
  "all_ok": true,          // every page of `latest` answered
  "any_ok": true,          // at least one page of `latest` answered
  "age_sec": 12,           // integer seconds since `latest`; null when older than 15 minutes
  "rum":   { "n": 143, "p75_ms": 3120 },          // real-user LCP, last hour, live site only, test rows excluded; n = 0 → "no data"
  "speed": { "lcp_ms": 2500, "score": 63, "checked_at": "<ISO 8601>" },   // latest successful lab run, home page, phone; {} if none
  "alerts_open": 3,        // count of open alerts (after role filtering)
  "rum_src": { "n": 1000,                           // the last 1000 real-user rows: where they came from
               "hosts": [ { "host": "live", "n": 964 }, { "host": "staging.example.co.il", "n": 36 } ],
               "cols": ["created_at", "is_test", "lcp_ms", "path", "site"],   // diagnostic only
               "test": 12 }                         // how many of them are flagged as test. null when unavailable
}
```

On failure: status 502 with `{"error": "<text>"}`; the screen writes "לא הצלחתי לטעון את "עכשיו"".
For a vendor or a share link `alerts_open` is recounted from the filtered list of open alerts
(§8.2); if that second read fails the answer is 502, never a false 0.

### 5.4 `GET /api/site/drill?what=…&(h | f,t)` → drill-downs; always `{"rows": [...]}`

| `what` | extra parameters | each row |
|---|---|---|
| `fails` | `page` (optional), `bucket` (optional) | `{ "at_il": "13.11 09:41", "page": "סל", "kind": "קוד 502", "err": "<technical text or null>", "ms": 812 }` — the failed checks, newest first, **at most 500**. `kind` is a short Hebrew reason: `לא ענה בזמן`, `קוד <status>`, `שגיאת חיבור`, `תוכן לא צפוי`. `ms` = time until the failure, or null. |
| `bucket` | `bucket` (required) | `{ "page": "בית", "checks": 60, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "13.11 09:17" }` — one row per probe page for that hour/day. |
| `runs` | `url` (required), `strategy`, `bucket` (optional) | `{ "ok": true, "err": null, "at_il": "13.11 10:45", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410, "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": [ { "id": "render-blocking-resources", "title": "…", "ms": 600 } ] }` — the individual lab runs of one page, **newest first**; failed runs have `ok: false` and `err`. `opps` = what slows the page, with the estimated saving in ms. |
| `alert` | `id` (required) | one row: the `alerts_recent` fields plus `"fails": [ { "at": "13.11 11:02", "page": "סל", "status": 502, "err": null } ]` (the failed checks behind a `down` alert) and `"sent": [ { "event": "open", "status": 200, "at": "13.11 11:02" } ]` (pushes sent; `event` is `open` or `close`; `status` 200 = delivered to the push service). |

Unknown `what`: status 400 `{"error": "what?"}`. A missing or malformed required parameter (`id`
not a number, `url` empty, `bucket` not in one of the two bucket formats): `{"rows": []}`.
Backend failure: status 502 `{"error": "<text>"}`.

### 5.5 `GET /api/messages?(h | f,t)` → the push log; `{"rows": [...]}`, newest first

`{ "kind": "התראה", "title": "…", "msg": "…", "at_il": "13.11 11:02", "sent": true }` — `kind` is
`התראה` (shown red), `חזר לתקין` (green) or any other label such as `בוקר` (grey). `sent: false`
adds "לא נשלחה".

### 5.6 `POST /api/alerts/ack` → "ראיתי"

Body `{"ids": [41, 40]}` or `{"id": 41}`. Ids may arrive as numbers or as digit strings; only the
first 200 are processed. Marks each open, not yet seen alert as seen by the current user (the
user's label is stored). Answer `{"ok": true, "n": <alerts actually marked>}`; a body without a
usable id → 400 `{"error": "bad request"}`.
The screen removes the rows at once and only reloads if the call fails.

### 5.7 Errors and caching

- Not logged in (and no valid share token): **401** `{"error": "auth"}` on every data call. The
  screen then goes to `loginPath` (or shows a message in share mode).
- Role not allowed: **403** `{"error": "auth"}`.
- Data answers: `Cache-Control: no-store`. The HTML page: `Cache-Control: no-cache, must-revalidate`.

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

---

## 7. The backend (reference design)

The production original keeps its measurements in Supabase (Postgres) and serves them through a
small Python server. The SQL of the original is not part of this kit. What follows is a reference
design that reproduces every contract of §5 and every promise of §3, and `reference/` implements
it and tests it. You may use `reference/` as is, adapt it, or rebuild it on the target project's
stack. Whatever you choose:

- the answers of §5 must be identical in shape and meaning;
- the definitions of §3 must hold;
- the **independence rule** must hold: the thing that notices "the measuring stopped" must not be
  the thing that stopped (§7.10).

### 7.1 Shape

- **Database: Postgres.** All logic that turns raw measurements into the answers of §5 lives in
  SQL functions named `sh_*` that return JSON. The server and the collectors touch the database
  **only** through these functions. That keeps one definition of every number, makes the logic
  testable with plain SQL, and lets the same code talk to Supabase over HTTPS (`/rest/v1/rpc/<fn>`
  with the secret key) or to any Postgres over a normal connection.
- **Server:** one small process: login, roles, the data routes of §5, the real-user ingest and
  the page itself. No business logic; it calls `sh_*` functions and filters by role. Run it as a
  **single process** (one worker): the login and ingest limits live in memory and the collectors
  must run once.
- **Collectors:** small scheduled jobs that fetch something and hand rows to an `sh_*` function.
  In the reference they are threads of a worker loop that starts with the server
  (`COLLECTORS=0` turns it off; `python collectors.py` runs it as a separate process). They can
  equally be scheduled functions of the database platform (§7.11).
- The server must run on an **always-on** instance. A plan that sleeps when idle stops the
  measuring.

### 7.2 Tables

All tables are private: on Supabase enable row level security on each (no policies) and revoke the
`anon` and `authenticated` roles from tables and functions; only the secret (service) key reads them.

| Table | One row is | Key columns |
|---|---|---|
| `sh_settings` | one setting | `key`, `value` (json): time zone, site host, `down_after`, morning hour |
| `sh_pages` | a configured page | `name` (Hebrew), `url`, `is_probe`, `is_core`, `sort`, `expect` (optional text the page must contain) |
| `sh_probe` | one availability check | `round_at`, `kind` (`full`/`light`), `page`, `url`, `ok`, `status`, `ms`, `fail` (`timeout`/`http`/`connect`/`content`), `err`; unique (`round_at`, `kind`, `page`) |
| `sh_speed` | one lab speed run | `at`, `url`, `page` (null for rotation pages), `strategy`, `source` (`core`/`rotation`), `ok`, `err`, `score`, `lcp_ms`, `cls`, `ttfb_ms`, `bytes`, `crux_category`, `crux_lcp_ms`, `opps` (json), `lh_version` |
| `sh_site_pages` | a page of the site, from the sitemap | `url`, `active`, `first_seen`, `last_seen`, `last_measured_at` |
| `sh_rum` | one real-user page view | `created_at`, `site`, `path`, `lcp_ms`, `is_test` — nothing that identifies a person |
| `sh_cert` | the certificate state | `host`, `issuer`, `not_before`, `not_after`, `days_left`, `ok`, `err`, `checked_at` |
| `sh_product_issues` | a broken product in a snapshot | `snap_date`, `product_id`, `issue`, `name`, `url` |
| `sh_alerts` | an alert | `id`, `key`, `kind`, `title`, `body`, `opened_at`, `closed_at`, `acked_at`, `acked_by`; **partial unique index on `key` where `closed_at is null`** (at most one open alert per key) |
| `sh_messages` | a push that was (or should be) sent | `id`, `at`, `alert_id`, `event` (`open`/`close`/`morning`), `kind` (Hebrew label), `title`, `msg`, `priority`, `click`, `status` (HTTP status of the push; null = pending) |
| `sh_flows` | a measurement flow | `flow_name`, `sort`, `cadence`, `warn_minutes`, `late_minutes`, `note`, `enabled`, `last_at` |
| `sh_jobs` | "this daily job is done for this day" | `job`, `day` |
| `sh_login_log` | a login attempt | `at`, `ip`, `ok`, `who`, `ua` |

Retention (a nightly cleanup): full-round probes 120 days (setting `keep_days`; four pages cost
about 0.7 MB a day, and a free Supabase project holds 500 MB), light-round probes 7 days, speed
runs 400 days, real-user rows 30 days, messages and alerts forever, login log 400 days. Windows
longer than the retention simply show what is left.

### 7.3 Functions the server calls (read side)

| Function | Returns | Used by |
|---|---|---|
| `sh_availability(p_from, p_to)` | §5.2 `availability` | `/api/site` |
| `sh_availability_series(p_from, p_to)` | §5.2 `availability_series` | `/api/site` |
| `sh_speed(p_from, p_to)` | §5.2 `speed` | `/api/site` |
| `sh_speed_series(p_from, p_to, p_strategy)` | §5.2 `speed_series` | `/api/site` |
| `sh_alerts_open()` | §5.2 `alerts_open` | `/api/site`, `/api/site/now` |
| `sh_alerts_range(p_from, p_to)` | §5.2 `alerts_recent` | `/api/site` |
| `sh_health()` | §5.2 `health` | `/api/site` |
| `sh_product_issues()` | §5.2 `product_issues` | `/api/site` |
| `sh_cert()` | §5.2 `cert` | `/api/site` |
| `sh_now()` | §5.3 without role filtering | `/api/site/now` |
| `sh_drill_fails(p_from, p_to, p_page, p_bucket)` | §5.4 | `/api/site/drill` |
| `sh_drill_bucket(p_bucket)` | §5.4 | `/api/site/drill` |
| `sh_drill_runs(p_from, p_to, p_url, p_strategy, p_bucket)` | §5.4 | `/api/site/drill` |
| `sh_drill_alert(p_id)` | §5.4 | `/api/site/drill` |
| `sh_messages(p_from, p_to)` | §5.5 | `/api/messages` |
| `sh_alert_ack(p_ids, p_who)` | `{"n": <rows marked>}` | `/api/alerts/ack` |
| `sh_login_log_add(p_ip, p_ok, p_who, p_ua)` | `{"n": 1}` | login |
| `sh_rum_add(p_rows)` | `{"n": <rows stored>}` | real-user ingest |
| `sh_ping()` | the JSON string `"ok"` | `/health` |
| `sh_config()` | the configuration (below) | page injection, time window, ingest |

Exact rules (these are the definitions the screen's texts promise):

- **Per page** (`availability`, section `לפי עמוד`): over **full** rounds in the window. `checks` =
  rows; `failed` = rows with `ok = false`; `fail_pct` = `round(100.0 * failed / checks, 2)`;
  `p50_ms` / `p95_ms` = `percentile_cont` over `ms` of the rows that answered, rounded to integers;
  `last_fail_il` = local time of the newest failed row.
- **Outages:** take the full rounds of the window in time order; a round is "dead" when none of
  its pages answered; every run of **3 or more consecutive dead rounds** is one outage.
  `outage_minutes` = number of rounds in the run; start = the first dead round; end = the round
  after the last dead one (or now). Minutes in which the prober itself did not run are not an
  outage; that is the `שקט` state of the flow.
- **Buckets:** `to_char(round_at at time zone <tz>, …)` with the format of §5; hourly when
  `p_to − p_from ≤ 72 hours`, daily otherwise. Percentiles per bucket over all pages together.
- **Speed, section `ליבה`:** per core page and strategy over successful runs with `source = 'core'`:
  medians of `lcp_ms`, `score`, `cls`, `ttfb_ms`; `lcp_p95`; `slow_runs` = runs with `lcp_ms > 4000`;
  `checks` = run count; `crux_*` from the newest run.
- **`שורה תחתונה`:** the `ליבה` figures of the home page with `strategy = 'mobile'`, plus `verdict`.
  When there is no successful run in the window the row is still returned with `lcp_p50: null`.
- **`האיטיים באתר`:** over successful phone runs with `source = 'rotation'`, grouped by URL: top 10 by median LCP.
- **Health:** `אין נתון` when the flow never ran; otherwise by the age of `last_at`: up to
  `warn_minutes` → `תקין`, up to `late_minutes` → `מתעכב`, beyond → `שקט`. `last_at` is written
  **last and only when a run succeeded**, so a failing collector leaves no proof of life and
  surfaces as `מתעכב`/`שקט`. Disabled flows (for example the catalogue check on a site that sells
  nothing) are not returned.
- **`sh_now`:** `pages` = the newest full round if it is at most 15 minutes old; `latest` = the
  newest round of either kind; `rum` over the last 60 minutes where `site` is a live value and
  `is_test` is false, `p75_ms` = `percentile_cont(0.75)`; `rum_src` over the newest 1000 rows.

### 7.4 Functions the collectors call (write side)

| Function | What it does |
|---|---|
| `sh_config()` | returns the configuration as one object: every setting loaded by `sh_setup` (`site`, `host`, `label`, `time_zone`, `platform`, `down_after`, `morning`, `keep_days`, `rum_hosts`, `private_paths`, …), `pages` (`[{name, url, probe, core, home, expect}]` in display order) and `screen` (the object the server injects as `SH_CONFIG`, §4.1). Before `sh_setup` ran there is no `time_zone`; the server then answers 502 "the site is not configured" instead of guessing |
| `sh_setup(p_config)` | loads `site_health.config.json` into `sh_settings` / `sh_pages` / `sh_flows` (idempotent) |
| `sh_probe_add(p_round_at, p_kind, p_rows)` | stores one probe round (duplicates ignored) and beats `בודק זמינות האתר` on a full round |
| `sh_speed_add(p_rows)` | stores lab runs; beats the core or rotation flow when at least one run succeeded |
| `sh_rotation_next(p_n)` | claims the `p_n` active site pages measured longest ago and returns their URLs |
| `sh_sitemap_set(p_urls)` | replaces the list of site pages (new ones added, missing ones deactivated); refuses an empty list; beats the sitemap flow |
| `sh_cert_set(p_row)` | stores the certificate state; beats the flow only when the check succeeded |
| `sh_issues_set(p_snap_date, p_rows)` | stores the day's broken products (replacing that day); beats the flow |
| `sh_job_due(p_job, p_day)` / `sh_job_mark(p_job, p_day)` | daily jobs: "is today's run still owed?" / "done" |
| `sh_alerts_check()` | evaluates the alert rules (§7.8), opens and closes alerts, queues messages; returns the messages waiting to be pushed |
| `sh_message_sent(p_id, p_status)` | records the HTTP status of a push |
| `sh_morning(p_day)` | queues the daily morning message (once per day) |
| `sh_cleanup()` | applies the retention rules |

### 7.5 Collector: availability probe (`בודק זמינות האתר`)

- **Full round** at the top of every minute: request every probe page concurrently. `GET`, a fresh
  connection, follow up to 5 redirects, timeout **10 seconds**, `User-Agent: SiteHealthProbe/1.0
  (+<dashboard address>)`, `Cache-Control: no-cache`.
- A check is **ok** when the final status is 200 within the timeout (and, if the page has an
  `expect` text, the first 200 KB of the body contain it). Otherwise `fail` is `timeout`, `http`
  (with the status), `connect` (DNS, TLS, reset) or `content`.
- `ms` = time from sending the request until the response headers of the final response arrive
  (what a new visitor's first request waits for). Read the body only when `expect` is set.
- **Light round** at second 30 of every minute: the same requests with a 5-second timeout,
  stored with `kind = 'light'` and `ms = null`. It feeds only the "now" tile and faster alerting.
  Never count it in availability or response-time statistics.
- All rows of a round share one `round_at` (the scheduled second, not the completion time).
- Run the prober from a region near the site's visitors; the server-response thresholds of §3
  assume it (a prober on another continent will paint everything yellow).
- The probe is one client in a data center. It tells you the server answers, not how fast the
  page loads for a visitor. The screen says so; do not present it as more.

### 7.6 Collector: lab speed (`מדידת מהירות`)

Google PageSpeed Insights API v5, one call per page per strategy:

`GET https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=<page>&strategy=mobile|desktop&category=performance&locale=he&key=<PAGESPEED_KEY>`

- **A key is required.** Calls without a key are refused (HTTP 429, daily limit 0). The key is
  free and needs no billing account. The owner creates it: Google Cloud Console → pick or create
  a project → APIs & Services → Library → "PageSpeed Insights API" → Enable → Credentials → Create
  credentials → API key; then restrict the key to that API only. Do not set an HTTP-referrer
  restriction (a server sends no referrer). Default quota: 25,000 calls a day and 240 a minute per
  project; the project's Quotas page is the authority.
- **Always send `strategy`** (the API's default is desktop) and `category=performance` (other
  categories only make the call slower).
- A call takes 10–60 seconds. Connect timeout 10 s, read timeout 120 s, one call at a time, and
  never let this collector block the probe (separate thread / job).
- Errors: 429 whose message mentions "per day" → stop until tomorrow; other 429 and 5xx → retry
  after 5, 10, 20 seconds, at most 3 tries; 400 "API key not valid" → a configuration error: do
  not retry, log it clearly, and let the flow go `שקט`. A failure of the test itself (HTTP 500
  "Lighthouse returned error: …", or `lighthouseResult.runtimeError` on a 200) is stored as a run
  with `ok = false` and the error text. Failed runs never count in medians.
- Store per run (a missing value is null, never 0; do not store the raw answer, it is huge):

| Column | From the answer |
|---|---|
| `score` | `lighthouseResult.categories.performance.score × 100`, rounded (the score can be null) |
| `lcp_ms` | `lighthouseResult.audits["largest-contentful-paint"].numericValue`, rounded |
| `cls` | `lighthouseResult.audits["cumulative-layout-shift"].numericValue`, 3 decimals |
| `ttfb_ms` | `lighthouseResult.audits["server-response-time"].numericValue`, rounded (fallback: `audits.metrics.details.items[0].timeToFirstByte`) |
| `bytes` | `lighthouseResult.audits["total-byte-weight"].numericValue` |
| `crux_category` | `loadingExperience.metrics.LARGEST_CONTENTFUL_PAINT_MS.category` (`FAST` / `AVERAGE` / `SLOW`) |
| `crux_lcp_ms` | `loadingExperience.metrics.LARGEST_CONTENTFUL_PAINT_MS.percentile` (75th percentile, ms) |
| `lh_version` | `lighthouseResult.lighthouseVersion` (for diagnosing a sudden change in the numbers) |
| `opps` | up to 8 reasons with an estimated time saving, largest first: `[{id, title, ms}]` (rule below) |

- **Real-user data is optional.** A page with little traffic has no `loadingExperience.metrics`.
  When `loadingExperience.origin_fallback` is true the numbers describe the whole site, not this
  page: store null for both `crux_*` columns in that case. The screen then says "אין מספיק תנועה".
- **`opps` rule** (works for old and new Lighthouse versions). For every audit in
  `lighthouseResult.audits`, except the metric audits themselves:
  1. skip it when `scoreDisplayMode` is `notApplicable`, `manual` or `error`, or when `score` is
     null or ≥ 0.9 (it passed; note that `server-response-time` reports a "saving" even when it passes);
  2. its saving in ms = `details.overallSavingsMs` if present; otherwise the largest of
     `metricSavings.LCP`, `.FCP`, `.TBT`, `.INP`; otherwise `numericValue` when `numericUnit` is `millisecond`;
  3. keep it when the saving is > 0. `title` is the audit's `title` (Hebrew, because of `locale=he`).

  Since Lighthouse 13 (in PageSpeed from October 2025) most classic audits (`modern-image-formats`,
  `render-blocking-resources`, …) no longer exist; they were replaced by `…-insight` audits
  (`image-delivery-insight`, `render-blocking-insight`, …) that have no `overallSavingsMs`. A
  collector that only looks for `details.type == "opportunity"` silently loses images, caching,
  fonts and render blocking. The screen's `OPP` table knows both generations and shows the stored
  `title` for any id it does not know.
- **Core pages:** every 15 minutes all core pages with `strategy=mobile`; once an hour with
  `strategy=desktop`. **Rotation:** every 5 minutes, 2 pages from `sh_rotation_next(2)`, phone only.
  With 5 core pages that is about 1,200 calls a day.
- Without `PAGESPEED_KEY` the collector does not run and says so in its log once; the speed cards
  show their empty states and the flows stay `אין נתון`.
- What the numbers mean (the screen says this too): the phone test simulates a mid-range phone on
  a slow 4G connection, measured from a Google data center, so it is harsher than what most
  visitors see and single runs are noisy. Verdicts and alerts therefore use medians and
  "twice in a row", never one run. A site behind bot protection may block Google's test; that
  shows up as failed runs with a 403 in the error text.

### 7.7 Collectors: sitemap, catalogue, certificate, real users

Two rules are shared by the sitemap and the catalogue reads: **read everything, prove it is
complete, and only then replace what is stored**; and a firewall page is not data (require a real
sitemap root tag / a JSON content type, otherwise the run failed).

**Sitemap (`טעינת מפת האתר`)**, nightly.

1. Find it: every `Sitemap:` line of `/robots.txt`; if there is none try `/sitemap_index.xml`,
   `/wp-sitemap.xml`, `/sitemap.xml`, and take the first that parses as `<sitemapindex>` or `<urlset>`.
2. Follow index files (at most 500 files, 50 MB each after decompression). Decide gzip by the
   first two bytes (`1f 8b`), not by the file name. Refuse documents that contain `<!ENTITY`.
3. From each `<url>` take only its **direct child** `<loc>` (SEO plugins nest `<image:loc>` inside;
   those are pictures, not pages). Child sitemap addresses are followed exactly as written,
   including their query strings.
4. Keep page URLs on the site's own host (with or without `www`); drop any page URL that has a
   query string or a fragment; drop non-HTML files; drop cart, checkout, account, search, feed,
   tag, author and paginated pages by their **first path segment** after decoding (shop slugs are
   often translated: take the real slugs from the site, not only the English words). Always
   include the home page.
5. If any file fails to load or parse, abort the whole load and keep yesterday's list. Refuse an
   empty list, and refuse a list smaller than half of the current one (that is almost always a
   fetch problem). Then hand the full list to `sh_sitemap_set` in one call.

The rotation measures 2 pages every 5 minutes = 576 pages a day. When the site has more pages,
raise it up to 6 per round (1,728 a day); beyond that tell the owner and reword the sentence
"כל האתר בערך פעם ביום" on the screen. The coverage line shows the truth either way.

**Broken products (`בדיקת מוצרים שבורים`)**, daily at 04:00, shops only.

- WooCommerce: page through
  `GET <site>/wp-json/wc/store/v1/products?per_page=100&page=N&orderby=id&order=asc` (public, no
  key; 100 is the maximum; the fixed order keeps pages stable while the shop changes). The total
  is in the `X-WP-Total` header. Per product:

  | Label | Condition |
  |---|---|
  | `בלי מחיר` | `prices.price` is empty or `"0"` **and** `is_purchasable` is false (a product without a price comes back as `"0"`, not empty; a free product stays purchasable) |
  | `בלי תמונה` | `images` is an empty list |
  | `לא במלאי` | `is_in_stock` is false |
  | `אי אפשר להוסיף לסל` | `is_purchasable` is false while the product is in stock and has a price; never for `type` `external` or `grouped` (they are never purchasable, by design) |

  A product can have more than one label. Names arrive with HTML entities: unescape them before
  storing. If the shop hides out-of-stock products from its catalogue, they are not in the answer
  and `לא במלאי` never appears; that is the shop's setting, not a fault of the check.
- Shopify: `GET <site>/products.json?limit=250&page=N` until an empty page (an unofficial but
  public endpoint: no total, so cross-check the count against the product sitemap). No variant
  with `available` → `לא במלאי`; no `images` → `בלי תמונה`; every variant priced 0 or empty → `בלי מחיר`.
- Other platforms: disable the flow and hide the card (`SH_CONFIG.hide = ['issuesCard']`).
- **Never store a partial snapshot.** Abort and keep yesterday's data when the number of products
  read differs from the declared total, when the total header is missing, or when ids repeat. A
  partial read looks exactly like products that vanished.
- Rows are returned with the real faults first and `לא במלאי` last, because the screen shows only
  the first 60. "Out of stock" is not always a fault, but a visitor who sees it leaves; that is
  why it is listed, in yellow.

**Certificate (`בדיקת תעודת האבטחה`)**, daily. Open a TLS connection to `<host>:443` with normal
verification, read `notBefore` / `notAfter` / issuer, store `days_left`. A failed check stores
`ok = false` with the error and does not beat the flow.

**Real users (`מהירות אצל לקוחות`)**. A small script on the site (`reference/rum/site-health-rum.js`)
measures LCP with the browser's `PerformanceObserver` and sends one beacon per page view when
the page is hidden or left: a JSON **string** through `navigator.sendBeacon`, which goes out as
`text/plain` and therefore needs no CORS preflight and no CORS headers (never send it as
`application/json`: Chrome refuses, other browsers preflight). Fields: `site`, `path`, `lcp`
(ms), `test`, plus `ttfb` and `nav`, which the reference does not store. `site` is the literal
`live` on the production host and the host name anywhere else, so traffic from a staging copy is
visible as such on the screen.

The ingest endpoint is **`POST /m`** (a neutral name: content blockers drop paths called "rum" or
"beacon"). It is public, so every field is hostile:

- read the raw body (it is `text/plain`; a JSON body parser will not see it), at most 1 KB;
- if an `Origin` or `Referer` header is present, its host must be the site's host (with or
  without `www`) or one of the extra hosts in the configuration (`rum_hosts`, for a staging copy);
  when both are absent, or `Origin` is the string `null` (sites with a strict referrer policy),
  accept the beacon. This is a noise filter, not security: anyone can forge a header;
- keep the row only when `lcp` is between 1 and 60,000 ms, `site` matches `^[a-z0-9.-]{1,100}$`,
  and `path` (query string removed, at most 300 characters) has no segment that names an account,
  checkout, order or admin page; otherwise drop the whole beacon;
- store no IP address, no cookie, no user agent, and ignore any cookie that arrives; limit each
  address to 60 beacons a minute, in memory only;
- always answer 204, also when the beacon is dropped; store after answering, in small batches.

What the tile's count means: page views that were *measured*. Nothing arrives from browsers
without LCP support (Safari and every iPhone browser before iOS 26.2, December 2025), from tabs
opened in the background, or from visitors with content blockers. It is not a traffic counter.
A p75 over a handful of views is noise; the screen shows it anyway, with the count next to it.

Delivery: on WordPress, the one-file plugin `reference/rum/site-health-rum.php` (it prints the
script inline in the footer; copy it to `wp-content/mu-plugins/` or install it as a plugin, set
the two constants, then purge the page cache and exclude the script from "delay JavaScript"
optimizations, or only visitors who interact get measured). On Shopify, paste the script into
the theme layout. Elsewhere, one configuration line and one script tag at the end of the page body. The
script is never loaded for signed-in staff, nor on cart, checkout and account pages.

### 7.8 Alert rules (`sh_alerts_check`, every minute, right after the full probe round)

| Kind | Key | Opens when | Closes when | Title · body |
|---|---|---|---|---|
| `down` | `down:<page>` | the newest `down_after` rounds (full or light) of a probe page all failed. `down_after` = 1 unless the owner chose 2 | the newest round of that page answered | `האתר לא עונה: <page>` · `<reason>\n<url>` |
| `slow` | `slow:<page>` | the two newest successful phone runs of a core page both have LCP > 4000 ms | the newest successful run is ≤ 4000 ms | `עמוד איטי: <page>` · `<x.x> שניות עד התוכן, פעמיים ברצף\n<url>` |
| `silent` | `silent:<flow>` | an enabled flow that has run before is older than its `late_minutes` | it ran again | `המדידה נעצרה: <flow>` · `אין מדידה כבר <N> דקות` |
| `cert` | `cert:<host>` | the last successful check shows fewer than 14 days | 14 days or more | `תעודת האבטחה פגה בעוד <N> ימים` · `<host>` |

- Opening inserts an alert row and a message (`kind` `התראה`, `event` `open`). Closing sets
  `closed_at` and inserts a message (`kind` `חזר לתקין`, `event` `close`, text `נמשך <N> דקות`).
- **Insert, do not upsert.** The unique index on `key` is partial (open alerts only), and an
  upsert with `on conflict (key)` fails against a partial index on the REST interface. Look for an
  open row; insert when there is none.
- Other parts of the owner's system may add their own alert kinds to the same table. The vendor
  role sees only the four kinds above (§8).
- **Morning message**, daily at 07:30: `kind` `בוקר`, one push summarizing the last 24 hours
  (availability %, outages, home page speed verdict, open alerts). Besides being useful, it is the
  owner's daily proof that the channel works.

### 7.9 Push notifications (ntfy)

Alerts go to phones through [ntfy](https://ntfy.sh): each person installs the ntfy app and
subscribes to one topic; the system publishes to that topic.

- Publish with a **JSON body to the server root** (not to `/<topic>`), which avoids every
  header-encoding problem with Hebrew:
  `POST https://ntfy.sh/` with `Content-Type: application/json` and
  `{"topic": "<topic>", "title": "<title>", "message": "<body>", "priority": 4, "tags": ["rotating_light"], "click": "<dashboard>/site"}`.
  `priority` is an integer 1–5 and `tags` a list of strings. Keep the title under 200 characters
  and the message under 1,500 (the limits are in bytes and Hebrew letters take two).
- Priorities: `down` and `silent` open → 4; `slow` and `cert` open → 3; "חזר לתקין" and the
  morning message → 2 (no sound on the phone; that is intended).
- Environment: `NTFY_TOPIC`, `NTFY_URL` (default `https://ntfy.sh`), optional `NTFY_TOKEN` (sent as
  `Authorization: Bearer …`, for a reserved topic on a paid plan or a self-hosted server).
- The topic name is the only secret of a free ntfy topic: anyone who knows it can read the last
  12 hours of alerts and publish fake ones. Generate a long random name (`sh-` + 24 random letters
  and digits), keep it in the environment only; never in the repository, on the screen or in logs.
- HTTP 200 means ntfy accepted the message, not that a phone showed it; there is no delivery
  receipt. Record the status of every publish with `sh_message_sent`. A failed publish is retried
  on the next minute, up to 5 attempts; after that it stays in the log as "לא נשלחה".
- **Send at most 30 pushes per rolling hour.** The free server allows 250 a day per sending
  address, and a flapping page with `down_after = 1` can produce two messages a minute. Messages
  that wait longer than an hour are marked as not sent instead of arriving late in a burst.
- Without `NTFY_TOPIC` messages are logged with status 0 and nothing is sent.
- Tell the owner two things at hand-over: ntfy keeps messages for 12 hours, so a phone that was
  off longer never gets them (the screen's message log is the permanent record); and iPhones
  deliver ntfy pushes less reliably than Android. If alerts matter and the owner uses an iPhone,
  offer a Telegram bot as the channel instead; the message log and rules stay the same.

### 7.10 Who watches the watcher

If the worker loop dies, nobody evaluates `silent`. Add one independent check; pick the first that
the platform supports:

1. **Database scheduler** (Supabase: `pg_cron` + `pg_net`): every 5 minutes a job runs
   `sh_deadman()`, which, when the newest probe round is older than 10 minutes and no
   `silent:בודק זמינות האתר` alert is open, opens it and publishes straight to ntfy with
   `net.http_post`. `reference/deadman.sql` holds the job; it needs the topic stored in the
   database's secret store.
2. **An external heartbeat service** (for example healthchecks.io): the worker requests the
   service's ping URL after every full round; the service alerts when pings stop.

Also expose `GET /health` on the server, without login: always status 200 with
`{"ok": <the database answered>, "db": "ok" | "<error text without host or key>",
"last_probe_age_sec": <seconds since the last full probe round, or null if there never was one>}`.
Keep it 200 even when the database is down; hosts restart a service whose health check fails,
and a restart loop helps nobody.

### 7.11 Running the collectors inside the database platform instead

On Supabase the collectors can run as scheduled Edge Functions (`pg_cron` calling the function URL
through `pg_net`), which is how the production original keeps measuring even while its dashboard
server restarts. Same functions, same rows, same cadences. If you choose this, keep the worker
loop off (`COLLECTORS=0`), and note that §7.10 then needs option 2 or a second scheduler.

---

## 8. Access

### 8.1 Roles

| Role | How they sign in | Sees | May do |
|---|---|---|---|
| owner | personal password | everything | mark alerts as seen; view the push log |
| staff (optional) | shared or personal password | everything | same as owner on this screen |
| vendor (agency, developer) | a personal password per person | the screen without the push log, alerts of the four site kinds only (or none: `noAlerts`), no list of pushes inside an alert | nothing: read-only |
| share link | `/status?k=<token>` | as vendor | nothing |

### 8.2 Rules (all enforced by the server; the screen's hiding is cosmetic)

- **Deny by default for outsiders.** For vendor and share-link requests use an allow-list: pages
  `/site` (or `/status`), `/login`, `/logout`; data calls `GET /api/site`, `GET /api/site/now`,
  `GET /api/site/drill`. Anything else, including any route added later, answers 403 (data) or
  redirects to `/site` (pages). Every request of theirs that is not a `GET` is refused, except
  the sign-in form.
- **Public routes**, answered before any role check: `GET /health`, `POST /m` (real-user ingest),
  `GET` and `POST /login`, `GET /logout`. `POST /m` ignores cookies entirely.
- Vendor filtering of data: `alerts_open` / `alerts_recent` keep only kinds `down`, `slow`,
  `silent`, `cert`; `sh_now().alerts_open` is recounted after filtering; the alert drill returns
  the alert only if its kind is allowed, with `sent` emptied; with `noAlerts` all alert lists are
  empty, the count is 0 and the alert drill returns no rows.
- The share token is compared in constant time, is accepted **only** on `/status` and the three
  data calls, and never counts as "logged in" anywhere else. An empty configured token disables
  the link. On those four routes, when `k` is present **only the token counts**: a valid one gives
  the share role even to a signed-in owner, a wrong one is refused even with a valid cookie
  (`/status`: 403 with the line `הקישור אינו תקין או שפג.`; data calls: 401). On every other
  route `k` is ignored, so a share link alone gets 401 from `/api/messages` and `/api/alerts/ack`.
- **Passwords** come from environment variables, one per person (`SH_PASS_OWNER`,
  `SH_PASS_STAFF`, `SH_PASS_VENDOR_<NAME>`). An unset variable never matches. Compare trimmed and
  case-insensitively (phone keyboards capitalize), in constant time.
- **Session cookie** (`sh_session`) = HMAC-SHA256 of one fixed label, keyed with that person's
  password as it is compared (trimmed, case-folded). So changing or deleting a password in the
  host's settings signs that person out at once, with no session table. `HttpOnly`, `Secure` on
  HTTPS (trust `X-Forwarded-Proto` from the host's proxy), `SameSite=Lax`. Lifetime 365 days for
  owner and staff, 30 days for vendors.
- When two variables hold the same password they produce the same cookie: resolve it, at sign-in
  and on every request, to the **least privileged** role (vendor without alerts, vendor, staff,
  owner), and log a warning at startup. A collision may take rights away, never grant them.
  Without an owner password nobody can sign in.
- **Brute force:** 8 failed attempts from one address within 10 minutes → 429 for that address
  until the window passes. Log every attempt that was examined (`sh_login_log`: time, address,
  success, who, user agent; `who` is `?` for a wrong password); requests refused with 429 are not
  logged, so a flood cannot fill the table. A logging failure never blocks sign-in.
- **The client address** behind the host's proxy: use the entry the host itself adds to
  `X-Forwarded-For` (check the host's documentation; on a host that appends, the left-most entry
  is whatever the client sent and lets an attacker dodge the limits).
- Hebrew texts of the pages around the screen: sign-in button `כניסה`, placeholder `סיסמה`,
  wrong password `סיסמה שגויה`, too many attempts `יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.`,
  bad share link `הקישור אינו תקין או שפג.`, database unreachable
  `אין כרגע חיבור לנתונים. נסו שוב בעוד רגע.`
- The page is served with the role injected at `<!--SH_INJECT-->`:
  `<script>window.SH_CONFIG={…};window.SH_ROLE={…};</script>`. Build it with a JSON encoder; never
  concatenate user input into it.
- `X-Robots-Tag: noindex` on every answer; the page already carries the meta tag.

### 8.3 Optional: "view as vendor" for the owner

A link for the owner that shows the screen exactly as a vendor gets it (a second cookie that the
server honors only together with a valid owner session, and that makes every check above treat
the request as the vendor). Useful before sending a vendor their password. Build it only if asked.

---

## 9. Build order and checks

Report after each phase: what was built, which checks ran, their result.

| Phase | Build | Done when |
|---|---|---|
| 0. Look | unpack; run the mock; open the screen | you have seen all 11 cards, opened a drill-down, pressed `הסברים` |
| 1. Intake | §2 | `site_health.config.json` exists and the owner confirmed it |
| 2. Database | tables and `sh_*` functions | `reference/tests/test_sql.py` passes against a scratch database (or your equivalent tests of the rules in §7.3 and §7.8) |
| 3. Server | login, roles, the routes of §5 | `reference/tests/test_server.py` passes; `node check_screen.js <server> --basic --cookie …` passes |
| 4. Probe + alerts | §7.5, §7.8, §7.9 | against a throwaway local site: a page that starts failing opens an alert within 2 minutes, a push is logged, the alert closes when the page recovers; 3 dead minutes show as one outage |
| 5. Speed | §7.6, sitemap | one real PageSpeed call stored for the home page; the screen's speed tiles show it |
| 6. Daily jobs | catalogue, certificate, cleanup, morning message | each ran once and its flow shows `תקין` |
| 7. Real users | §7.7 | a test page view on the site appears in "מהירות אצל לקוחות" within a minute, flagged as test |
| 8. Deploy | host, environment, schedules, the independent check of §7.10 | the checklist of §10 is green on the live address |
| 9. Hand-over | a short Hebrew note for the owner | they know the address, how to subscribe to alerts, and what each color means |

Rules for the whole build:

- Run the real thing. A phase is not done because the code looks right.
- Use a scratch database for tests. Never run tests that write against the live database.
- Do not leave test alerts, test pushes or fake rows in the live database. A test push to the
  real topic must say it is a test.

## 10. Go-live checklist

1. `check_screen.js --basic` passes against the live address at 390 px and 1280 px.
2. Every flow in `המדידה עצמה` is `תקין` (or intentionally disabled).
3. Stop the worker for 12 minutes on purpose: the independent check of §7.10 pushes "המדידה
   נעצרה". Start it again: "חזר לתקין".
4. A vendor password: sees no push log and no ✕; `POST /api/alerts/ack` answers 403; any other
   path redirects to `/site`.
5. The share link works; with one character changed it answers 403.
6. The explanation texts match the real schedule and the real number of pages.
7. No secret in the repository (`git grep` for the topic, the token, the keys, the passwords).
8. The owner received one test push and saw the screen on their phone.

## 11. Lessons already paid for

Each of these was a real problem in the production original. Do not rediscover them.

1. **A CSS class on `<body>` must not share a name with a hiding rule.** The explanations toggle
   once put the class `explain` on `<body>`, and `.explain{display:none}` then hid the whole
   page. The template uses `explain-on`.
2. **Deleting several alerts must not reload the screen.** Each ✕ used to reload everything and
   fold the list; clearing 11 alerts took minutes. Remove the row locally, send the request in
   the background, restore on failure.
3. **The alert bar is collapsed by default**, even for one alert, and remembers that it was opened.
4. **Daily jobs keep their "done today" marker in the database, not in memory.** With the marker in
   memory every restart ran the daily jobs again.
5. **Write the proof of life last, and only on success.** Then a failing collector looks silent,
   which is the truth.
6. **Never store a partial catalogue read.**
7. **`/health` stays 200 when the database is down.**
8. **A partial unique index cannot be the target of an upsert through the REST interface.**
9. **Passwords are compared case-insensitively and trimmed.** Phones capitalize the first letter
   and people got locked out.
10. **Resolve password collisions to the least privileged identity.**
11. **Check where real-user measurements come from.** The owner once asked whether the numbers were
    from the live site or from a development copy; nobody could tell. Hence the `site` field, the
    source line under the tile, and the count of test rows.
12. **Encoded URLs are unreadable on a phone.** Alert bodies and tables show a readable page name
    (`short()` and `niceBody()` in the screen); the raw URL stays in the data.
13. **One failed check is usually network noise; two or three in a row are a fault.** The screen
    says this in the failures sheet. If the owner finds single-blip alerts tiring, set
    `down_after` to 2.
14. **Outsiders get an allow-list, never a block-list.** A block-list fails open the day someone
    adds a route.
15. **Each part of the main answer fails alone.** One slow or broken query must not blank the screen.
