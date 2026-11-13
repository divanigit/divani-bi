# ערכת "בריאות האתר" — קובץ אחד לקודקס

**לדורון, בקצרה**

- **מה זה:** כל מה שקודקס צריך כדי לבנות את מסך "בריאות האתר" לאתר אחר: ההוראות, המסך עצמו, ובדיקות.
- **מה עושים איתו:** שמים את הקובץ הזה בתיקיית הפרויקט של האתר החדש, ואומרים לקודקס את המשפט שלמטה.
- **מה יוצא:** קודקס שואל אותך כמה שאלות קצרות על האתר (כתובת, אילו עמודים לבדוק, מי מקבל התראות) ואז בונה.

המשפט לקודקס (להעתיק כמו שהוא):

> בתיקייה יש קובץ SITE_HEALTH_KIT.md. תריץ את פקודת הפריסה שכתובה בראשו, תקרא את site_health_kit/SPEC.md מההתחלה עד הסוף, ותבנה לפיו את מסך בריאות האתר לאתר שלי. תכתוב לי בעברית, קצר ופשוט, ושאלה אחת בכל פעם.

---

# For the coding agent

This single file is a container. It holds a specification and working files for building the
**Site Health screen ("בריאות האתר")** for a website.

**Step 1 — unpack.** Do not read past the line `FILES BELOW` (it is ~198 KB of embedded
files). From the directory that contains this file, run:

```bash
python3 - <<'PY'
import hashlib, os, re
s = open('SITE_HEALTH_KIT.md', encoding='utf-8').read()
n = 0
for m in re.finditer(r'<!-- FILE: (\S+) sha256=([0-9a-f]{64}) -->\n~~~~~~~~[^\n]*\n(.*?\n)~~~~~~~~\n<!-- END FILE -->', s, re.S):
    path, digest, body = m.groups()
    assert not os.path.isabs(path) and '..' not in path.split('/'), 'bad path: ' + path
    assert hashlib.sha256(body.encode('utf-8')).hexdigest() == digest, 'damaged copy of ' + path + ' (get the file again)'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    open(path, 'w', encoding='utf-8', newline='\n').write(body)
    n += 1
print('unpacked', n, 'files into site_health_kit/')
PY
```

It writes the folder `site_health_kit/` and verifies every file's checksum. If Python is not
available, extract each block between `<!-- FILE: path … -->` and `<!-- END FILE -->` by other
means; do **not** retype file contents from memory.

**Step 2 — read `site_health_kit/SPEC.md` from start to end.** It is the specification; everything
else in the folder is referenced from it. Read it in full before writing any code (it is about
902 lines; read it in chunks if your tools truncate long files).

**Step 3 — follow SPEC.md §1.** In short: see the screen run on fake data
(`python3 site_health_kit/mock_server.py`), ask the owner the intake questions of §2, then build in
the phases of §9 and run the checks of each phase.

Contents:

- `site_health_kit/SPEC.md` (902 lines)
- `site_health_kit/AGENTS.md` (47 lines)
- `site_health_kit/site_health.html` (943 lines)
- `site_health_kit/mock_server.py` (482 lines)
- `site_health_kit/check_screen.js` (197 lines)
- `site_health_kit/reference/rum/site-health-rum.js` (44 lines)
- `site_health_kit/reference/rum/site-health-rum.php` (25 lines)

---

FILES BELOW

<!-- FILE: site_health_kit/SPEC.md sha256=7835255f8756657bf79656d9280f63e959214b4a3386aee5d22b8726f26c40dd -->
~~~~~~~~markdown
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

The screen calls five endpoints. Field names, types and the literal Hebrew values below are what
`site_health.html` reads; `mock_server.py` returns exactly these shapes. Your server must return
the same.

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

- With `f`: window = `[f 00:00 local, (t + 1 day) 00:00 local)`. Without `t`: until now. If the end
  is not after the start: end = start + 1 day. Invalid dates: fall back to `h`.
- Without `f`: `h` is clamped to `1 … 9600` (400 days), default 24; window = `[now − h hours, now + 1 minute)`.

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

  "product_issues": [                   // from the latest catalogue snapshot only; sort: by issue, then name
    { "issue": "לא במלאי",              // "לא במלאי" (literal, shown yellow); any other text is shown red
      "name": "ספה תלת מושבית", "url": "https://example.co.il/product/…/", "snap_date": "2026-11-13" }
  ],

  "cert": { "host": "example.co.il", "issuer": "Let's Encrypt R11", "not_after": "<ISO 8601>",
            "days_left": 23, "ok": true, "err": null, "checked_at": "<ISO 8601>" }   // or null before the first check
}
```

**Each part fails alone.** The eight list parts are computed independently and in parallel; if one
fails, its key holds `{"error": "<text>"}` instead of a list, and the rest of the answer is still
returned with status 200. The screen treats a non-list as empty.

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

### 5.4 `GET /api/site/drill?what=…&(h | f,t)` → drill-downs; always `{"rows": [...]}`

| `what` | extra parameters | each row |
|---|---|---|
| `fails` | `page` (optional), `bucket` (optional) | `{ "at_il": "13.11 09:41", "page": "סל", "kind": "קוד 502", "err": "<technical text or null>", "ms": 812 }` — the failed checks, newest first, **at most 500**. `kind` is a short Hebrew reason: `לא ענה בזמן`, `קוד <status>`, `שגיאת חיבור`, `תוכן לא צפוי`. `ms` = time until the failure, or null. |
| `bucket` | `bucket` (required) | `{ "page": "בית", "checks": 60, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "13.11 09:17" }` — one row per probe page for that hour/day. |
| `runs` | `url` (required), `strategy`, `bucket` (optional) | `{ "ok": true, "err": null, "at_il": "13.11 10:45", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410, "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": [ { "id": "render-blocking-resources", "title": "…", "ms": 600 } ] }` — the individual lab runs of one page, **newest first**; failed runs have `ok: false` and `err`. `opps` = what slows the page, with the estimated saving in ms. |
| `alert` | `id` (required) | one row: the `alerts_recent` fields plus `"fails": [ { "at": "13.11 11:02", "page": "סל", "status": 502, "err": null } ]` (the failed checks behind a `down` alert) and `"sent": [ { "event": "open", "status": 200, "at": "13.11 11:02" } ]` (pushes sent; `event` is `open` or `close`; `status` 200 = delivered to the push service). |

Unknown `what`: status 400 `{"error": "what?"}`. Backend failure: status 502 `{"error": "<text>"}`.

### 5.5 `GET /api/messages?(h | f,t)` → the push log; `{"rows": [...]}`, newest first

`{ "kind": "התראה", "title": "…", "msg": "…", "at_il": "13.11 11:02", "sent": true }` — `kind` is
`התראה` (shown red), `חזר לתקין` (green) or any other label such as `בוקר` (grey). `sent: false`
adds "לא נשלחה".

### 5.6 `POST /api/alerts/ack` → "ראיתי"

Body `{"ids": [41, 40]}` (up to 200) or `{"id": 41}`. Marks each open alert as seen by the current
user. Answer `{"ok": true, "n": 2}`; bad body → 400 `{"error": "bad request"}`.
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
- **Server:** one small process: login, roles, the six routes of §5 and the page itself. No
  business logic; it calls `sh_*` functions and filters by role.
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

Retention (a nightly cleanup): full-round probes 400 days, light-round probes 7 days, speed runs
400 days, real-user rows 30 days, messages and alerts forever, login log 400 days.

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
| `sh_login_log_add(p_ip, p_ok, p_who, p_ua)` | — | login |
| `sh_rum_add(p_rows)` | `{"n": <rows stored>}` | real-user ingest |
| `sh_ping()` | `"ok"` | `/health` |

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
| `sh_config()` | returns settings + the page lists, so collectors need no second copy of the configuration |
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

**Sitemap (`טעינת מפת האתר`)**, nightly. Find the sitemap from `robots.txt` (`Sitemap:` lines), else
try `/sitemap.xml`, `/sitemap_index.xml`, `/wp-sitemap.xml`. Follow sitemap index files, accept
gzip. Keep URLs of the site's own host, drop query strings and fragments, and drop cart, checkout,
account, search, feed and tag pages. Hand the list to `sh_sitemap_set`. An empty or failed read
changes nothing.

**Broken products (`בדיקת מוצרים שבורים`)**, daily at 04:00, shops only.

- WooCommerce: page through `GET <site>/wp-json/wc/store/v1/products?per_page=100&page=N` (public,
  no key). The total is in the `X-WP-Total` header. Rules per product: `prices.price` empty or 0
  → `בלי מחיר`; `images` empty → `בלי תמונה`; `is_in_stock` false → `לא במלאי`; `is_purchasable`
  false (and in stock, and priced) → `אי אפשר להוסיף לסל`. A product can have more than one issue.
- Shopify: `GET <site>/products.json?limit=250&page=N` until an empty page. No variant with
  `available` → `לא במלאי`; no `images` → `בלי תמונה`; every variant priced 0 or empty → `בלי מחיר`.
- Other platforms: disable the flow and hide the card (`SH_CONFIG.hide = ['issuesCard']`).
- **Never store a partial snapshot.** If the number of products read differs from the declared
  total, or ids repeat, abort and keep yesterday's data. A partial read looks exactly like
  products that vanished.
- "Out of stock" is not always a fault, but a visitor who sees it leaves; that is why it is listed
  in yellow.

**Certificate (`בדיקת תעודת האבטחה`)**, daily. Open a TLS connection to `<host>:443` with normal
verification, read `notBefore` / `notAfter` / issuer, store `days_left`. A failed check stores
`ok = false` with the error and does not beat the flow.

**Real users (`מהירות אצל לקוחות`)**. A small script on the site (`reference/rum/`) measures LCP
with the browser's `PerformanceObserver` and sends one beacon per page view when the page is
hidden or left: `{site, path, lcp, test}` as `text/plain` with `navigator.sendBeacon` (no CORS
preflight). `site` is the literal `live` on the production site and the host name anywhere else,
so staging traffic is visible as such on the screen. The ingest endpoint `POST /rum`:

- accepts only bodies up to 1 KB whose `Origin` (or `Referer`) host is the site's;
- stores `path` without query string (at most 300 characters), `lcp` only when between 1 and
  60,000 ms, `site` only when it matches `^[a-z0-9.-]{1,100}$` (anyone can post to this endpoint;
  treat every field as hostile);
- drops paths of account, checkout, order and admin pages;
- stores no IP address, no cookie, no user agent; limits each IP to 60 beacons a minute in memory;
- always answers 204, also when it drops the row.

Browsers that do not report LCP (older Safari) simply send nothing; the tile's count shows how
many page views were measured. On WordPress the script is delivered by a tiny plugin
(`reference/rum/site-health-rum.php`); on Shopify paste the script into the theme; elsewhere add
one script tag. Do not load it for logged-in administrators.

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

- Publish with a JSON body to the server root, which avoids every header-encoding problem with Hebrew:
  `POST https://ntfy.sh/` with `{"topic": "<topic>", "title": "<title>", "message": "<body>", "priority": 4, "tags": ["rotating_light"], "click": "<dashboard>/site"}`.
- Priorities: `down` and `silent` open → 4; `slow` and `cert` open → 3; "חזר לתקין" and the
  morning message → 2.
- The topic name is the only secret of a free ntfy topic: anyone who knows it can read and write.
  Generate a long random name (`sh-` + 24 random characters), keep it in the environment
  (`NTFY_TOPIC`), never in the repository or on the screen.
- Record the HTTP status of every publish with `sh_message_sent`. A publish that fails is retried
  on the next minute, up to 5 times; after that it stays in the log as "לא נשלחה".
- Without `NTFY_TOPIC` messages are logged with status 0 and nothing is sent.

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

Also expose `GET /health` on the server: always status 200 with `{"ok": <bool>, "db": "<state>",
"last_probe_age_sec": <n>}`. Keep it 200 even when the database is down; hosts restart a service
whose health check fails, and a restart loop helps nobody.

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
  redirects to `/site` (pages). `POST` is always refused for them.
- Vendor filtering of data: `alerts_open` / `alerts_recent` keep only kinds `down`, `slow`,
  `silent`, `cert`; `sh_now().alerts_open` is recounted after filtering; the alert drill returns
  the alert only if its kind is allowed, with `sent` emptied; with `noAlerts` all alert lists are
  empty, the count is 0 and the alert drill returns no rows.
- The share token is compared in constant time, is accepted **only** on `/status` and the three
  data calls, and never counts as "logged in" anywhere else. An empty configured token disables
  the link. Wrong token: the page answers 403 with a one-line Hebrew message; data calls answer 401.
- **Passwords** come from environment variables, one per person (`SH_PASS_OWNER`,
  `SH_PASS_STAFF`, `SH_PASS_VENDOR_<NAME>`). An unset variable never matches. Compare trimmed and
  case-insensitively (phone keyboards capitalize), in constant time.
- **Session cookie** = HMAC-SHA256 of a fixed label keyed with that person's password. So
  changing or deleting a password in the host's settings signs that person out at once, with no
  session table. `HttpOnly`, `Secure` on HTTPS, `SameSite=Lax`. Lifetime 365 days for owner and
  staff, 30 days for vendors.
- When two variables hold the same password, resolve to the **least privileged** role, and log a
  warning at startup. A collision may take rights away, never grant them.
- **Brute force:** 8 failed attempts from one IP within 10 minutes → 429 for that IP until the
  window passes. Log every attempt (`sh_login_log`: time, IP, success, who, user agent).
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
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/AGENTS.md sha256=aa385ee4bcb7c63870d701b68265df2ce9736c58f26139938964d6a0d3641836 -->
~~~~~~~~markdown
# AGENTS.md — Site Health build

This repository builds the **Site Health screen ("בריאות האתר")** for a website: is the site up, how
fast is it, what is broken, which alerts fired.

The full specification is **`site_health_kit/SPEC.md`**. This file is only the short list of rules
that apply to every change. Read SPEC.md from start to end before your first change, and again
whenever you are unsure; do not work from this summary.

## Rules

1. **The screen is `site_health_kit/site_health.html`. Use it as it is.** Per-site values go into
   `SH_CONFIG`; the only other edits allowed are listed in SPEC.md §6.9. Never retype or "tidy" it.
2. **The JSON contract of SPEC.md §5 is binding**: field names, types, the literal Hebrew values,
   the order of rows. `mock_server.py` is the contract by example.
3. **Never invent a number.** Every figure on the screen comes from a stored measurement. No
   placeholder or sample data in production.
4. **Secrets only in environment variables or the host's secret store.** Not in the repository,
   not in the HTML, not in chat. If a key is needed, tell the owner where to paste it.
5. **No customer data.** No names, emails, phones, order numbers or visitor IP addresses are
   stored. URLs are stored without query strings.
6. **Be a polite client of the monitored site.** One probe round per minute, hard timeouts, a
   distinct User-Agent. Never load-test it.
7. **Outsiders get an allow-list.** Vendor and share-link access is deny-by-default (SPEC.md §8).
8. **Work in the phases of SPEC.md §9 and run each phase's checks.** A phase is done when its
   checks pass on the real thing, not when the code looks right. Report failures as failures.
9. **Tests never write to the live database.** Use a scratch database.

## Talking to the owner

The owner is not a developer. Write to them in **Hebrew**, short and in plain words. One decision
per message; a question says what happens on yes, on no, and whether it can be undone. End every
message with one line: what they need to do now (or "אתה לא צריך לעשות כלום").

## Commands

```bash
python3 site_health_kit/mock_server.py                    # the screen on fake data → http://localhost:8787/site
node site_health_kit/check_screen.js                      # acceptance test of the screen (against the mock)
node site_health_kit/check_screen.js <url> --basic --cookie "<name>=<value>"   # against a real server
cd site_health_kit/reference && python3 -m pytest -q      # backend tests (need a scratch Postgres)
```

## Definition of done

The go-live checklist of SPEC.md §10 passes on the live address, and the owner has received one
test push and has seen the screen on their phone.
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/site_health.html sha256=35aa2ea6f3c976d6680e04eddbca6a115ed083e3ac6d0b2810f12c9809b093db -->
~~~~~~~~html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>בריאות האתר</title>
<!--
  SITE HEALTH SCREEN — reference template (single file, no build step, no libraries).
  Per-site settings live in SH_CONFIG at the top of the script block at the end of this file.
  The server may override any of them, and set the viewer role, by injecting one inline script
  tag (window.SH_CONFIG = {...}; window.SH_ROLE = {...}) at the marker comment below.
  Everything else is data-driven: see the kit's SPEC.md, section "API contract".
-->
<style>
:root{
  --font: system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Hebrew",Arial,sans-serif;
  --bg:#ffffff; --surface:#f4f8f6; --line:#e2e9e5; --line2:#cdd8d2;
  --tx:#18241f; --tx2:#53635c; --tx3:#8a978f;
  --brand:#0d9668; --brandSoft:rgba(13,150,104,.10);
  --sys:#4a3aa7; --sysSoft:rgba(74,58,167,.07);
  --okbg:#e3f3ec; --okfg:#0b6e4f; --wbg:#fbf0da; --wfg:#8f5f08; --dbg:#fbe6e4; --dfg:#a3271f;
  --down:#a3271f;
  --shadow:0 1px 2px rgba(16,24,32,.05),0 6px 18px rgba(16,24,32,.05);
  --r:14px;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0f1512; --surface:#19211d; --line:#26302b; --line2:#35423b;
    --tx:#e9efeb; --tx2:#a2b0a9; --tx3:#6f7d76;
    --brand:#2fbf8f; --brandSoft:rgba(47,191,143,.16);
    --sys:#9085e9; --sysSoft:rgba(144,133,233,.10);
    --okbg:#12312765; --okfg:#63d3a6; --wbg:#2e241065; --wfg:#e0b25a; --dbg:#3a1a1765; --dfg:#f0968f;
    --down:#f0968f;
    --shadow:0 1px 2px rgba(0,0,0,.5),0 6px 18px rgba(0,0,0,.35);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:var(--font);-webkit-text-size-adjust:100%;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:12px 12px 40px}

/* ---------- זהות ---------- */
.hdr{display:flex;align-items:flex-start;justify-content:space-between;margin:0 0 6px}
.hdr .out{font-size:11.5px;color:var(--tx3);text-decoration:none;padding:6px 2px}
.shbrand{display:flex;align-items:flex-start;gap:7px;flex:none;min-height:18px}
.shword{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-weight:700;font-size:15px;letter-spacing:.04em;color:var(--tx);line-height:1;margin-top:4px;unicode-bidi:isolate}
.brandcol{display:flex;flex-direction:column;align-items:flex-end;gap:2px;line-height:1}

/* ---------- שורת התפריט ---------- */
.shbar{display:flex;align-items:center;gap:11px;margin:0 0 12px}
.shham{width:46px;height:46px;flex:none;border:1px solid var(--line);border-radius:13px;background:var(--surface);color:var(--tx);display:grid;place-items:center;cursor:pointer}
.shham svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round}
.shnow{min-width:0;display:flex;flex-direction:column;line-height:1.25}
.shnow .v{font-size:18px;font-weight:700;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.shacts{margin-inline-start:auto;display:flex;align-items:center;gap:6px}
.shxls{display:inline-flex;align-items:center;gap:6px;font-family:inherit;font-size:12.5px;border:1px solid var(--line2);background:var(--bg);color:var(--tx2);padding:7px 12px;min-height:38px;border-radius:999px;cursor:pointer}
.shxls[aria-pressed="true"]{background:var(--sysSoft);border-color:var(--sys);color:var(--sys);font-weight:700}
.shov{position:fixed;inset:0;background:rgba(10,18,14,.45);z-index:120;display:none}
.shov.on{display:block}
.shsheet{position:absolute;inset-block:0;inset-inline-end:0;width:min(330px,88vw);background:var(--bg);border-inline-start:1px solid var(--line);padding:14px;overflow:auto}
.shhead{display:flex;align-items:center;justify-content:space-between;margin:0 0 10px}
.shhead b{font-size:17px}
.shx{width:38px;height:38px;border:0;background:transparent;color:var(--tx);cursor:pointer;border-radius:10px;display:grid;place-items:center}
.shx svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round}
.shg{font-size:10.5px;font-weight:700;letter-spacing:.09em;color:var(--tx3);margin:12px 4px 5px}
.shsheet a,.shcur{display:flex;align-items:center;gap:9px;min-height:44px;padding:9px 11px;border-radius:11px;text-decoration:none;color:var(--tx);font-size:15px;border:1px solid transparent}
.shsheet a:hover{background:var(--surface);border-color:var(--line)}
.shcur,.shsheet a.shcur{background:#111;color:#fff;font-weight:700;border-color:#111;cursor:default}
/* ---------- תפקידים: צפייה בלבד / קישור שיתוף / בלי התראות ---------- */
.ro .alertbar .ax,.ro .alertbar .acb,.ro .abulk,.ro #msgCard{display:none!important}
.share #outLink{display:none!important}
.noalerts #alertbar,.noalerts #alertsCard,.noalerts .vbox[data-drill="alerts"]{display:none!important}
@media (prefers-color-scheme:dark){.shcur,.shsheet a.shcur{background:#e9efeb;color:#0f1512;border-color:#e9efeb}}

/* ---------- פס התראה ---------- */
.alertbar{display:none;background:var(--dbg);color:var(--dfg);border:1px solid var(--dfg);border-radius:12px;padding:10px 13px;margin:0 0 12px;font-weight:700;font-size:14.5px}
.alertbar.on{display:block}
.alertbar .sub{display:block;font-weight:400;font-size:12.5px;margin-top:2px;white-space:normal;overflow:hidden;text-overflow:ellipsis}
/* מקופל כברירת מחדל: שורת סיכום אחת, והרשימה נפתחת בהקשה. */
.ahead{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.ahead .chev{margin-inline-start:auto;transition:transform .2s;font-size:13px}
.alertbar.collapsed .chev{transform:rotate(-90deg)}
.alertbar.collapsed .alist{display:none}
.alist{margin-top:10px;max-height:48vh;overflow:auto}
.alertbar .arow{display:flex;gap:8px;align-items:flex-start}
.alertbar .arow+.arow{margin-top:8px;padding-top:8px;border-top:1px solid var(--dfg)}
.alertbar .arow>div{flex:1;min-width:0}
.alertbar .arow .at{font-size:13.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.alertbar .ax{flex:none;width:30px;height:30px;border:1px solid var(--dfg);border-radius:8px;background:transparent;color:var(--dfg);font:inherit;font-weight:700;cursor:pointer;line-height:1}
/* מחיקה קבוצתית (12.11.2026): תיבת סימון בכל שורה, ושורת פעולה מעל הרשימה שלא נגללת איתה */
.alertbar .acb{flex:none;display:flex;align-items:center;justify-content:center;width:30px;height:30px;cursor:pointer}
.alertbar input[type=checkbox]{width:20px;height:20px;margin:0;accent-color:var(--dfg);cursor:pointer}
.abulk{display:flex;align-items:center;gap:10px;margin-top:10px;padding-bottom:10px;border-bottom:1px solid var(--dfg);font-weight:400;font-size:13.5px}
.abulk label{display:flex;align-items:center;gap:8px;min-height:36px;padding-inline-start:5px;cursor:pointer}
.abulk .adel{margin-inline-start:auto;min-height:36px;padding:0 14px;border:1px solid var(--dfg);border-radius:8px;background:var(--dfg);color:var(--bg);font:inherit;font-weight:700;cursor:pointer}
.abulk .adel:disabled{background:transparent;color:var(--dfg);opacity:.55;cursor:default}
.alertbar.collapsed .abulk{display:none}
.alertbar .alink{display:inline-flex;align-items:center;min-height:30px;margin-top:4px;font-size:13px;font-weight:700;color:var(--dfg);text-decoration:underline;text-underline-offset:3px}

/* ---------- כותרת ---------- */
h1{font-size:clamp(23px,5.4vw,31px);font-weight:800;margin:4px 0 2px;letter-spacing:-.01em}
.sub{font-size:13.5px;color:var(--tx2);margin:0 0 14px}
h2{font-size:16px;font-weight:800;margin:0 0 4px}
/* קיפול כרטיס — אותה תבנית כמו פס ההתראות: כותרת + מספר + חץ, לחיצה פותחת. מקופל כברירת מחדל. */
.foldhead{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.foldhead .foldn{font-size:13px;font-weight:600;color:var(--tx3)}
.foldhead .foldchev{margin-inline-start:auto;font-size:13px;color:var(--tx3);transition:transform .2s}
.foldcard.collapsed .foldchev{transform:rotate(-90deg)}
.foldcard.collapsed .foldbody{display:none}
.foldcard.collapsed{padding-bottom:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px;margin:0 0 12px;box-shadow:var(--shadow)}
.eyebrow{font-size:12.5px;font-weight:700;color:var(--tx2);margin:0 0 8px;line-height:1.35}
.ctlrow{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:11px;overflow:hidden;background:var(--bg)}
.seg button{font:inherit;font-size:14px;font-weight:600;min-height:44px;padding:0 13px;border:0;background:transparent;color:var(--tx2);cursor:pointer}
.seg button+button{border-inline-start:1px solid var(--line2)}
.seg button[aria-pressed="true"]{background:#111;color:#fff}
@media (prefers-color-scheme:dark){.seg button[aria-pressed="true"]{background:#e9efeb;color:#0f1512}}
.dates{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:9px}
.dates label{font-size:13px;color:var(--tx2);display:flex;align-items:center;gap:6px}
.dates input{font:inherit;font-size:14px;min-height:44px;padding:0 10px;border:1px solid var(--line2);border-radius:11px;background:var(--bg);color:var(--tx)}
.dates .go{font:inherit;font-size:14px;font-weight:700;min-height:44px;padding:0 16px;border:0;border-radius:11px;background:var(--brand);color:#fff;cursor:pointer}
.hint{font-size:12.5px;color:var(--tx3);margin:6px 0 0}
.explain{display:none;font-size:13px;color:var(--tx2);background:var(--bg);border:1px dashed var(--line2);border-radius:10px;padding:9px 11px;margin:8px 0 0;line-height:1.6}
body.explain-on .explain{display:block}

/* ---------- עכשיו (דורון 18.9.2026, שאלות 44–47) ---------- */
.now{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.nbox{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 13px;min-height:84px}
.nbox .k{font-size:12px;color:var(--tx2);margin:0 0 4px}
.nbox .v{font-size:24px;font-weight:800;line-height:1.1;display:flex;align-items:center;gap:8px}
.nbox .m{font-size:12px;color:var(--tx3);margin-top:4px}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;flex:none}
.dot.ok{background:var(--okfg)}.dot.w{background:var(--wfg)}.dot.d{background:var(--dfg)}.dot.n{background:var(--tx3)}
.npages{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.nowtick{font-size:12px;color:var(--tx3);margin-top:8px}

/* ---------- שורה תחתונה ---------- */
.verdict{display:flex;flex-wrap:wrap;gap:10px}
.vbox{flex:1 1 150px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 13px;min-height:84px;cursor:pointer;text-align:start;font:inherit;color:var(--tx)}
.vbox:hover{border-color:var(--line2)}
.vbox .k{font-size:12px;color:var(--tx2);margin:0 0 4px}
.vbox .v{font-size:26px;font-weight:800;line-height:1.1;letter-spacing:-.01em}
.vbox .m{font-size:12px;color:var(--tx3);margin-top:4px}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px;border:1px solid transparent}
.tag.ok{background:var(--okbg);color:var(--okfg);border-color:var(--okfg)}
.tag.w{background:var(--wbg);color:var(--wfg);border-color:var(--wfg)}
.tag.d{background:var(--dbg);color:var(--dfg);border-color:var(--dfg)}
.tag.n{background:var(--bg);color:var(--tx3);border-color:var(--line2)}
.est{color:var(--tx3)}

/* ---------- טבלאות ---------- */
.tblwrap{overflow-x:auto;margin:0 -2px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:right;padding:8px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--tx2);font-weight:700}
td.num,th.num{direction:ltr;text-align:left;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
tr.rowbtn{cursor:pointer}
tr.rowbtn:hover td{background:var(--bg)}
td a{color:var(--tx);text-decoration:none;border-bottom:1px dotted var(--tx3)}
.muted{color:var(--tx3);font-size:13px;overflow-wrap:anywhere;word-break:break-word}
.empty{color:var(--tx2);font-size:13.5px;padding:8px 0}
.more{font-size:12px;color:var(--tx3);margin:6px 0 0}

/* ---------- גרפים ---------- */
.chart{width:100%;height:auto;display:block;margin-top:6px}
.chart text{font-family:var(--font);fill:var(--tx2);font-size:11px}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .ref{stroke:var(--tx3);stroke-width:1;stroke-dasharray:3 4}
.chart .reft{fill:var(--tx3);font-size:10px}
.chart .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .bar{fill:var(--down);cursor:pointer}
.chart .bar:hover{opacity:.75}
.chart .ms{fill:none;stroke:var(--brand);stroke-width:2}
.chart .hit{fill:transparent;cursor:pointer}
.chart .pt{cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 0}
.legend button{font:inherit;font-size:12.5px;min-height:34px;padding:0 11px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--tx2);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.legend button i{width:10px;height:10px;border-radius:50%;display:inline-block}
.legend button[aria-pressed="false"]{opacity:.45}
.list{margin:0;padding:0;list-style:none}
.list li{padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px;display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}
.list li>*{min-width:0;max-width:100%}
.list li.rowbtn{cursor:pointer}
.list li:last-child{border-bottom:0}
.list li>*{min-width:0;overflow-wrap:anywhere}/*long-url*/
.list .when{color:var(--tx3);font-size:12px;direction:ltr}

/* ---------- חלון העומק (דריל) ---------- */
.dov{position:fixed;inset:0;background:rgba(10,18,14,.5);z-index:130;display:none}
.dov.on{display:block}
.dsheet{position:absolute;inset-inline:0;bottom:0;max-height:88vh;overflow:auto;background:var(--bg);border-radius:18px 18px 0 0;border:1px solid var(--line);border-bottom:0;box-shadow:var(--shadow);padding:14px 14px 28px}
@media (min-width:720px){.dsheet{inset-inline:auto;left:50%;transform:translateX(-50%);width:720px;bottom:auto;top:6vh;border-radius:18px;border-bottom:1px solid var(--line)}}
.dhd{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 8px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.dhd b{font-size:17px}
.dsum{font-size:14.5px;line-height:1.6;margin:0 0 10px}
.dsum b{font-weight:800}
.dwhat{font-size:13px;color:var(--tx2);background:var(--surface);border-radius:10px;padding:9px 11px;margin:0 0 12px;line-height:1.6}
.dsheet h3{font-size:13.5px;font-weight:800;margin:14px 0 6px;color:var(--tx2)}

/* ---------- חיווי טעינה ---------- */
.loadbar{position:fixed;top:0;left:0;right:0;height:3px;background:var(--brand);transform:scaleX(0);transform-origin:right;transition:transform .4s;z-index:200}
body.loading .loadbar{animation:lb 1.2s ease-in-out infinite}
@keyframes lb{0%{transform:scaleX(0);transform-origin:right}50%{transform:scaleX(1);transform-origin:right}51%{transform-origin:left}100%{transform:scaleX(0);transform-origin:left}}
.loadpill{position:fixed;top:12px;left:50%;transform:translateX(-50%);background:#111;color:#fff;font-size:13px;font-weight:700;padding:8px 14px;border-radius:999px;display:none;z-index:200;box-shadow:var(--shadow)}
body.loading .loadpill{display:flex;align-items:center;gap:8px}
.loadpill i{width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .8s linear infinite;display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
body.loading .card{opacity:.55;transition:opacity .2s}
.stale{font-size:12px;color:var(--wfg);background:var(--wbg);border-radius:8px;padding:4px 9px;display:none;margin:0 0 8px}
body.loading .stale{display:inline-block}

/* ---------- טלפון: קיבוע למסך וריווח נקי ---------- */
@media (max-width:640px){
  .wrap{padding:10px 11px 40px}
  .card{padding:13px 12px;margin:0 0 11px}
  h1{margin-top:2px}
  .sub{margin-bottom:12px}
  /* טבלאות רחבות נשארות בתוך הכרטיס וגוללות אופקית בלבד — לא חותכות את העמוד */
  .tblwrap{-webkit-overflow-scrolling:touch;scrollbar-width:thin}
  th,td{padding:8px 7px}
  /* גוף ההתראה/ההודעה: שורה שלמה, נשבר יפה, לא דוחף לרוחב */
  .list li>.muted,.list li>.when{flex-basis:100%}
}
/* רשת ביטחון: שום אלמנט לא יגלוש את רוחב המסך בטלפון */
html,body{overflow-x:hidden}

/* ---------- ייצוא PDF: הדפסה נקייה עם כל הנתונים פרושים ---------- */
@media print{
  @page{size:A4 landscape;margin:10mm}
  :root{--bg:#fff!important;--surface:#fff!important;--line:#cfcfcf!important;--line2:#bcbcbc!important;
        --tx:#111!important;--tx2:#3a3a3a!important;--tx3:#6a6a6a!important;--shadow:none!important}
  body{background:#fff!important;color:#111!important}
  .shbar,.loadbar,.loadpill,.stale,.explain{display:none!important}
  #ctlCard{display:none!important}
  .seg,.dates,.foldchev,.ahead .chev,.alertbar .ax,.alertbar .acb,.abulk{display:none!important}
  .shov,.dov{display:none!important}
  .foldcard.collapsed .foldbody{display:block!important}
  .alertbar.collapsed .alist{display:block!important}
  /* בלי שום חיתוך — כל האירועים וכל שורות הטבלה נכנסים ל-PDF */
  .alist,.list,.foldbody,.tblwrap,.alertbar{max-height:none!important;overflow:visible!important}
  .card{box-shadow:none!important;border:1px solid #cfcfcf!important;break-inside:avoid;margin-bottom:9px}
  table{font-size:9.5px;width:100%}
  th,td{padding:5px 6px!important;white-space:normal!important}
  a{color:#111!important;text-decoration:none}
  h1{font-size:22px}
  .chart{max-height:200px}
}
</style>
<!--SH_INJECT-->
</head>
<body>
<div class="loadbar" aria-hidden="true"></div>
<div class="loadpill" role="status"><i></i><span id="loadtxt">טוען נתונים…</span></div>
<div class="wrap">

  <div class="hdr">
    <div class="shbrand"><span class="shword" id="brandTxt"></span></div>
    <div class="brandcol"><a class="out" id="outLink" href="/logout">יציאה</a></div>
  </div>

  <div class="shbar">
    <button type="button" class="shham" id="shham" aria-label="תפריט" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 7h17"/><path d="M3.5 12h17"/><path d="M3.5 17h17"/></svg>
    </button>
    <div class="shnow"><span class="v">בריאות האתר</span></div>
    <div class="shacts">
      <span id="xlinks" style="display:contents"></span>
      <button type="button" class="shxls" id="explbtn" aria-pressed="false" title="הסבר פשוט לכל מספר">הסברים</button>
      <button type="button" class="shxls" id="refbtn" title="רענון">רענון</button>
      <button type="button" class="shxls" id="pdfbtn" title="ייצוא כל הדוח כ-PDF לשליחה">ייצא PDF</button>
    </div>
  </div>

  <div class="alertbar" id="alertbar" title="לחיצה: פרטים"></div>

  <h1>בריאות האתר</h1>
  <p class="sub" id="sub">טוען…</p>

  <section class="card" id="nowcard">
    <h2>עכשיו</h2>
    <div class="now" id="now"><div class="nbox"><div class="k">האתר עכשיו</div><div class="v"><span class="dot n"></span>טוען…</div></div></div>
    <div class="npages" id="nowpages"></div>
    <p class="nowtick" id="nowtick"></p>
    <p class="explain">"עכשיו" = סבב הבדיקה האחרון של המערכת, כל דקה, <span data-cfg="probeCount">4</span> עמודים. "תגובת שרת" = כמה זמן עובר מהבקשה עד שהשרת מתחיל לענות: ירוק עד 0.5 שנ', צהוב עד 1.5, אדום מעל או כשעמוד לא עונה. "מהירות אצל לקוחות" = מה שגולשים אמיתיים חוו בשעה האחרונה, זמן עד תוכן ראשי, אחוזון 75, נמדד בדפדפן של הגולש על ידי קוד מדידה קטן שמותקן באתר. מתחת למספר כתוב מאיזה אתר הגיעו המדידות. מתרענן לבד כל 60 שניות.</p>
  </section>

  <section class="card" id="ctlCard">
    <div class="ctlrow">
      <div class="seg" id="segH">
        <button type="button" data-h="24" aria-pressed="true">24 שעות</button>
        <button type="button" data-h="168" aria-pressed="false">7 ימים</button>
        <button type="button" data-h="720" aria-pressed="false">30 יום</button>
        <button type="button" data-h="2160" aria-pressed="false">90 יום</button>
      </div>
      <div class="seg" id="segS">
        <button type="button" data-s="mobile" aria-pressed="true">טלפון</button>
        <button type="button" data-s="desktop" aria-pressed="false">מחשב</button>
      </div>
    </div>
    <div class="dates">
      <label>מתאריך <input type="date" id="dFrom"></label>
      <label>עד <input type="date" id="dTo"></label>
      <button type="button" class="go" id="dGo">הצג</button>
    </div>
    <p class="hint" id="rangeTxt"></p>
    <p class="explain">התקופה קובעת את כל המסך. "טלפון" ו"מחשב" משנים רק את מדדי המהירות; הזמינות זהה לשניהם. כל מספר, שורה ונקודה בגרף לחיצים: לחיצה פותחת את הפירוט מאחוריהם.</p>
  </section>

  <section class="card" id="verdictCard">
    <h2>שורה תחתונה</h2>
    <div class="verdict" id="verdict"></div>
    <p class="explain">"מהירות" = כמה זמן עד שהתוכן העיקרי בעמוד הבית מוצג בטלפון. עד 2 שניות: מצוין. עד 2.5: מהיר (הסף של גוגל). עד 4: בינוני. מעל 4: איטי. "זמינות" = כמה מהבדיקות (כל דקה, <span data-cfg="probeCount">4</span> עמודים) ענו תקין.</p>
  </section>

  <section class="card" id="availCard">
    <h2>זמינות</h2>
    <div id="availTbl"></div>
    <div id="outages"></div>
    <div id="availChart"></div>
    <p class="hint">לחיצה על שורה: הכשלים של העמוד. לחיצה על עמודה אדומה: הכשלים באותה שעה/יום. לחיצה על הקו הירוק: זמן התגובה לפי עמוד.</p>
    <p class="explain">כל דקה נבדקים <span data-cfg="probeCount">4</span> עמודים. "נפילה" = 3 דקות רצופות שבהן אף עמוד לא ענה. בגרף: עמודות אדומות = בדיקות שנכשלו; קו ירוק = זמן תגובת השרת החציוני. הבודק הוא לקוח בודד מהענן: הוא רואה שהשרת עונה, לא כמה מהר האתר נטען אצל לקוח.</p>
  </section>

  <section class="card" id="speedCard">
    <h2>מהירות לאורך זמן</h2>
    <div class="legend" id="legend"></div>
    <div id="speedChart"></div>
    <p class="hint" id="speedHint" hidden>לחיצה על נקודה: המדידות של אותו עמוד באותה שעה/יום, ומה האט אותו.</p>
    <p class="explain">כל נקודה = חציון המדידות באותה שעה (או יום, בתקופות ארוכות) של הזמן עד הצגת התוכן העיקרי, בשניות. הקווים המקווקווים: 2.5 = הסף של גוגל ל"מהיר", 4 = מכאן "איטי". המדידה מדמה טלפון ממוצע ברשת סלולרית איטית, ולכן קשוחה מהמציאות אצל רוב הלקוחות. היא נועדה לראות מגמה, לא לפסוק.</p>
  </section>

  <section class="card" id="coreCard">
    <h2>העמודים העיקריים</h2>
    <div id="coreTbl"></div>
    <p class="explain">ציון = ציון הביצועים של גוגל (0–100, 90 ומעלה מצוין). LCP = זמן עד הצגת התוכן העיקרי. p50 = חציון, p95 = הגרוע מבין 95 אחוז מהמדידות. קפיצות = כמה העמוד "קופץ" בזמן טעינה (עד 0.1 טוב). שרת = זמן עד הבייט הראשון. "גולשים אמיתיים" = מה שגוגל מודדת אצל מבקרים אמיתיים בכרום (יש רק כשיש מספיק תנועה). לחיצה על שורה: כל המדידות ומה מאט את העמוד.</p>
  </section>

  <section class="card" id="slowCard">
    <h2>העמודים הכבדים באתר</h2>
    <p class="muted" id="coverage"></p>
    <div id="slowTbl"></div>
    <p class="explain">כל עמוד באתר (מוצרים, קטגוריות, עמודים) נמדד בסבב: 2 עמודים כל 5 דקות, כל האתר בערך פעם ביום. כאן 10 הכבדים ביותר בתקופה. עמוד כבד כמעט תמיד אומר תמונות גדולות מדי. לחיצה על שורה: מה בדיוק מאט אותו.</p>
  </section>

  <section class="card" id="issuesCard">
    <h2>מוצרים שבורים באתר</h2>
    <div id="issuesTbl"></div>
    <p class="explain">נבדק פעם ביום (04:00) על כל הקטלוג הציבורי: מוצר בלי מחיר, בלי תמונה, לא במלאי, או שאי אפשר להוסיף לסל. "לא במלאי" אינו בהכרח תקלה, אבל לקוח שרואה את זה עוזב.</p>
  </section>

  <section class="card" id="certCard">
    <h2>תעודת האבטחה (המנעול)</h2>
    <div id="certBox"></div>
    <p class="explain">התעודה היא מה שנותן לאתר את המנעול בדפדפן. כשהיא פגה, הדפדפן מציג ללקוח אזהרה אדומה במקום האתר. נבדקת פעם ביום; התראה מתחת ל-14 יום.</p>
  </section>

  <section class="card foldcard collapsed" id="alertsCard">
    <h2 class="foldhead">התראות<span class="foldn" id="alertsN"></span><span class="foldchev">▾</span></h2>
    <div id="alertsList" class="foldbody"></div>
    <p class="explain">התראה נפתחת ברגע שבדיקת זמינות אחת נכשלת, כשעמוד עיקרי איטי (מעל 4 שניות) פעמיים ברצף, כשהמדידה עצמה נעצרה, או כשתעודת האבטחה עומדת לפוג. נסגרת לבד כשהמצב חוזר לתקין. ההודעות מגיעות לטלפון של כל מי שמנוי לערוץ. לחיצה: מה בדיוק קרה. ✕ בפס האדום = "ראיתי": מסתיר לכולם עד שההתראה תיסגר ותיפתח מחדש. בטלפון, הודעות ישנות נמחקות מתוך אפליקציית ntfy (החלקה או "נקה הכל").</p>
  </section>

  <section class="card foldcard collapsed" id="msgCard">
    <h2 class="foldhead">הודעות שנשלחו לטלפון<span class="foldn" id="msgN"></span><span class="foldchev">▾</span></h2>
    <div id="msgList" class="foldbody"></div>
    <p class="explain">כל מה שהמערכת שלחה לערוץ ההתראות בתקופה שנבחרה: התראות, "חזר לתקין", והודעות הבוקר. גם אם נמחקו מהטלפון, הן כאן.</p>
  </section>
  <section class="card" id="healthCard">
    <h2>המדידה עצמה</h2>
    <div id="healthTbl"></div>
    <p class="explain">אם שורה כאן "שקטה", המספרים למעלה ישנים, לא רעים. קודם מתקנים את המדידה, אחר כך קוראים מספרים. לחיצה: מה השורה מודדת ומה עושים.</p>
  </section>

</div>

<div class="shov" id="shov">
  <div class="shsheet" role="dialog" aria-modal="true" aria-label="תפריט">
    <div class="shhead"><b>תפריט</b>
      <button type="button" class="shx" id="shx" aria-label="סגירה">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"/><path d="M18 6L6 18"/></svg>
      </button>
    </div>
    <div id="shlist"></div>
  </div>
</div>

<div class="dov" id="dov">
  <div class="dsheet" id="dsheet" role="dialog" aria-modal="true" aria-labelledby="dttl">
    <div class="dhd"><b id="dttl"></b>
      <button type="button" class="shx" id="dx" aria-label="סגירה">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"/><path d="M18 6L6 18"/></svg>
      </button>
    </div>
    <div id="dbody"></div>
  </div>
</div>

<script>
/* ---------- הגדרות האתר (SH_CONFIG) ----------
   כל מה שמשתנה מאתר לאתר נמצא כאן. השרת יכול לדרוס כל שדה: הוא מזריק לפני סוף ה-head
   תגית סקריפט שקובעת  window.SH_CONFIG = {siteLabel: 'my-site.co.il', ...}  */
var CFG = (function(){
  var d = {
    siteLabel: 'example.co.il',  // מוצג מתחת לכותרת ובכותרת הלשונית
    brand: '',                   // טקסט קטן בראש המסך (שם העסק או המערכת). ריק = בלי
    homePage: 'בית',             // הערך של השדה page בעמוד הבית, בדיוק כפי שהשרת מחזיר אותו
    probeCount: 4,               // כמה עמודים בודק הזמינות (לטקסטי ההסבר בלבד)
    coreCount: 5,                // כמה עמודי ליבה נמדדים במהירות (לטקסטי ההסבר בלבד)
    liveHosts: [],               // ערכי המקור שנחשבים "האתר החי" במדידות אצל לקוחות. ריק = ['live', siteLabel, 'www.' + siteLabel]
    pathLabels: [['/product-category/', 'קטגוריה: '], ['/product/', 'מוצר: ']],  // קיצור כתובת לשם קריא
    bucketNote: '',              // הערה בתחתית חלון "זמן תגובת השרת". ריק = בלי
    nav: [],                     // תפריט: [['g','כותרת קבוצה'], ['a','/path','שם מסך'], ...]. ריק = בלי כפתור תפריט
    here: '/site',               // הכתובת של המסך הזה בתפריט
    links: [],                   // כפתורים נוספים בשורה העליונה: [{href:'/x', label:'שם', title:'הסבר'}]
    api: '/api',                 // בסיס כתובות הנתונים
    loginPath: '/login',
    logoutPath: '/logout',
    shareKey: '',                // טוקן של קישור שיתוף; מצורף לכל קריאת נתונים כ-k=
    hide: []                     // כרטיסים שלא רלוונטיים לאתר הזה, לפי מזהה: 'issuesCard' (אתר בלי חנות), 'slowCard'
  };
  var o = window.SH_CONFIG || {};
  Object.keys(o).forEach(function(k){ d[k] = o[k]; });
  if (!d.liveHosts || !d.liveHosts.length) d.liveHosts = ['live', d.siteLabel, 'www.' + d.siteLabel];
  return d;
})();
/* תפקיד הצופה. השרת מזריק באותה תגית:  window.SH_ROLE = {readonly: true}
   readonly = בלי מחיקת התראות ובלי יומן ההודעות · share = קישור שיתוף (גם בלי "יציאה") · noAlerts = בלי התראות בכלל.
   זה רק מסתיר על המסך. את אותם כללים בדיוק השרת חייב לאכוף בעצמו. */
var ROLE = window.SH_ROLE || {};
if (ROLE.share) ROLE.readonly = true;
(function(){
  var esc0 = function(v){ return String(v == null ? '' : v).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  var root = document.documentElement;
  if (ROLE.readonly) root.classList.add('ro');
  if (ROLE.share) root.classList.add('share');
  if (ROLE.noAlerts) root.classList.add('noalerts');
  (CFG.hide || []).forEach(function(id){ var el = document.getElementById(id); if (el) el.style.display = 'none'; });
  document.title = 'בריאות האתר — ' + CFG.siteLabel;
  document.getElementById('brandTxt').textContent = CFG.brand || '';
  document.getElementById('outLink').setAttribute('href', CFG.logoutPath);
  Array.prototype.forEach.call(document.querySelectorAll('[data-cfg]'), function(el){ var v = CFG[el.getAttribute('data-cfg')]; if (v != null) el.textContent = v; });
  document.getElementById('xlinks').innerHTML = (ROLE.readonly ? [] : CFG.links).map(function(l){ return '<a class="shxls" href="' + esc0(l.href) + '" title="' + esc0(l.title || '') + '" style="text-decoration:none">' + esc0(l.label) + '</a>'; }).join('');
  /* תפריט: רק כשיש מסכים נוספים, ורק למי שאינו צופה חיצוני */
  var nav = ROLE.readonly ? [] : CFG.nav, h = '', pend = null;
  nav.forEach(function(it){
    if (it[0] === 'g') { pend = it[1]; return; }
    if (pend) { h += '<div class="shg">' + esc0(pend) + '</div>'; pend = null; }
    h += it[1] === CFG.here
      ? '<a href="' + esc0(it[1]) + '" class="shcur" aria-current="page">' + esc0(it[2]) + '</a>'
      : '<a href="' + esc0(it[1]) + '">' + esc0(it[2]) + '</a>';
  });
  document.getElementById('shlist').innerHTML = h;
  var ham = document.getElementById('shham'), ov = document.getElementById('shov');
  ham.hidden = !h;
  function open(){ ov.classList.add('on'); document.body.style.overflow = 'hidden'; }
  function close(){ ov.classList.remove('on'); document.body.style.overflow = ''; }
  ham.addEventListener('click', open);
  document.getElementById('shx').addEventListener('click', close);
  ov.addEventListener('click', function(e){ if (e.target === ov) close(); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && ov.classList.contains('on')) close(); });
})();
/* כתובת נתונים: בסיס מההגדרות, ובקישור שיתוף גם הטוקן */
function api(path){ var u = CFG.api + path; if (CFG.shareKey) u += (u.indexOf('?') < 0 ? '?' : '&') + 'k=' + encodeURIComponent(CFG.shareKey); return u; }

/* ---------- עזרים ---------- */
var $ = function(id){ return document.getElementById(id); };
var state = { h: 24, f: '', t: '', s: 'mobile', hidden: {}, seq: 0, data: null };
var COLORS = ['#0d9668', '#4a3aa7', '#c2410c', '#0369a1', '#7c3aed', '#be185d'];
var NF = new Intl.NumberFormat('he-IL');
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function sec(ms){ return ms == null ? '—' : (ms / 1000).toFixed(1); }
function n(v){ return v == null ? '—' : NF.format(v); }
function lcpTag(ms){
  if (ms == null) return '<span class="tag n">אין</span>';
  if (ms <= 2000) return '<span class="tag ok">מצוין</span>';
  if (ms <= 2500) return '<span class="tag ok">מהיר</span>';
  if (ms <= 4000) return '<span class="tag w">בינוני</span>';
  return '<span class="tag d">איטי</span>';
}
function lcpWord(ms){ return ms == null ? 'אין נתונים' : ms <= 2000 ? 'מהיר מצוין' : ms <= 2500 ? 'מהיר' : ms <= 4000 ? 'בינוני' : 'איטי'; }
function cruxTag(c){
  if (!c) return '<span class="tag n">אין מספיק תנועה</span>';
  return c === 'FAST' ? '<span class="tag ok">מהיר</span>' : c === 'AVERAGE' ? '<span class="tag w">בינוני</span>' : '<span class="tag d">איטי</span>';
}
function short(u){ try { var p = decodeURIComponent(new URL(u).pathname), i, x; for (i = 0; i < CFG.pathLabels.length; i++) { x = CFG.pathLabels[i]; if (p.indexOf(x[0]) === 0) { p = x[1] + p.slice(x[0].length); break; } } return p.replace(/\/$/, '').replace(/-/g, ' ') || CFG.homePage; } catch (e) { return u; } }
/* כתובת מקודדת בגוף ההתראה (product-category/%d7%…) נראית כג'יבריש בטלפון.
   מחליפים כל כתובת בשם עמוד קריא, ומוותרים עליה כשהיא רק חוזרת על הכותרת. */
function niceBody(t, title){
  var s = String(t || '').replace(/https?:\/\/[^\s]+/g, function(u){ return short(u); });
  if (title) { s = s.split('\n').filter(function(l){ return l.trim() && ('· ' + l.trim()).indexOf(String(title).trim()) < 0; }).join(' · '); }
  return s.replace(/\s*·\s*·\s*/g, ' · ').trim();
}
function qs(){ return state.f ? '&f=' + state.f + '&t=' + state.t : '&h=' + state.h; }
function periodTxt(){ return state.f ? 'מ-' + state.f.split('-').reverse().join('.') + ' עד ' + state.t.split('-').reverse().join('.') : state.h === 24 ? '24 השעות האחרונות' : state.h / 24 + ' הימים האחרונים'; }
function bucketTxt(b){ return b.length > 10 ? 'ב-' + b.slice(8, 10) + '.' + b.slice(5, 7) + ' בשעה ' + b.slice(11, 16) : 'ב-' + b.slice(8, 10) + '.' + b.slice(5, 7); }
/* תרגום "מה מאט את העמוד" (Lighthouse) לעברית פשוטה */
var OPP = {
  'render-blocking-resources': 'קבצים שחוסמים את הציור הראשון (סקריפטים וסגנון בראש העמוד)',
  'unused-css-rules': 'סגנון (CSS) שלא בשימוש נטען בכל זאת',
  'unused-javascript': 'קוד (JavaScript) שלא בשימוש נטען בכל זאת',
  'modern-image-formats': 'תמונות בפורמט ישן (JPG/PNG) במקום WebP/AVIF',
  'uses-optimized-images': 'תמונות לא דחוסות מספיק',
  'uses-responsive-images': 'תמונות גדולות מדי לגודל שבו הן מוצגות',
  'offscreen-images': 'תמונות מחוץ למסך נטענות מיד במקום בגלילה',
  'server-response-time': 'השרת עונה לאט (זמן עד הבייט הראשון)',
  'uses-text-compression': 'קבצי טקסט נשלחים בלי דחיסה',
  'uses-rel-preconnect': 'חיבור מוקדם לשרתים חיצוניים חסר',
  'redirects': 'הפניות (redirect) לפני שהעמוד נטען',
  'uses-long-cache-ttl': 'קבצים לא נשמרים בזיכרון הדפדפן לזמן ארוך',
  'efficient-animated-content': 'אנימציות GIF במקום וידאו',
  'duplicated-javascript': 'קוד כפול',
  'legacy-javascript': 'קוד ישן שנשלח גם לדפדפנים חדשים',
  'prioritize-lcp-image': 'התמונה הראשית לא נטענת בעדיפות',
  'total-byte-weight': 'העמוד כבד מאוד בסך הכל',
  'dom-size': 'העמוד מורכב מיותר מדי אלמנטים',
  'third-party-summary': 'קוד של צד שלישי (פיקסלים, צ\'אט, אנליטיקס) מאט',
  'bootup-time': 'הדפדפן עסוק בהרצת קוד',
  'mainthread-work-breakdown': 'הדפדפן עסוק מדי בזמן הטעינה',
  'font-display': 'הטקסט מחכה לגופן שייטען',
  'unminified-css': 'קובצי סגנון (CSS) לא מכווצים',
  'unminified-javascript': 'קובצי קוד (JavaScript) לא מכווצים',
  /* מ-Lighthouse 13 (אוקטובר 2025) רוב הסיבות הישנות הוחלפו ב"תובנות" (insight) */
  'render-blocking-insight': 'קבצים שחוסמים את הציור הראשון (סקריפטים וסגנון בראש העמוד)',
  'image-delivery-insight': 'תמונות כבדות מדי: לדחוס, להקטין לגודל התצוגה, לעבור ל-WebP/AVIF',
  'document-latency-insight': 'העמוד עצמו מגיע לאט מהשרת (תגובה איטית, הפניות, או בלי דחיסה)',
  'network-dependency-tree-insight': 'שרשרת ארוכה של קבצים שמחכים זה לזה',
  'cache-insight': 'קבצים לא נשמרים בזיכרון הדפדפן לזמן ארוך',
  'duplicated-javascript-insight': 'קוד כפול',
  'legacy-javascript-insight': 'קוד ישן שנשלח גם לדפדפנים חדשים',
  'lcp-discovery-insight': 'התמונה הראשית מתגלה מאוחר או לא נטענת בעדיפות',
  'lcp-breakdown-insight': 'התוכן העיקרי מתעכב (פירוט השלבים בדוח של גוגל)',
  'dom-size-insight': 'העמוד מורכב מיותר מדי אלמנטים',
  'third-parties-insight': 'קוד של צד שלישי (פיקסלים, צ\'אט, אנליטיקס) מאט',
  'font-display-insight': 'הטקסט מחכה לגופן שייטען',
  'forced-reflow-insight': 'קוד שמכריח את הדפדפן לחשב מחדש את פריסת העמוד',
  'cls-culprits-insight': 'אלמנטים שגורמים לעמוד לקפוץ בזמן הטעינה',
  'inp-breakdown-insight': 'העמוד מגיב לאט ללחיצות',
  'viewport-insight': 'העמוד לא מוגדר נכון לרוחב של טלפון',
  'modern-http-insight': 'קבצים נשלחים בפרוטוקול ישן (HTTP/1.1)'
};
function oppName(o){ return OPP[o.id] || o.title || o.id; }

/* ---------- טעינה ---------- */
function load(){
  var seq = ++state.seq; document.body.classList.add('loading'); var lt = $('loadtxt'); if (lt) lt.textContent = 'טוען נתונים…';
  $('sub').textContent = CFG.siteLabel + ' · טוען…';
  $('rangeTxt').textContent = 'מוצג: ' + periodTxt();
  fetch(api('/site?strategy=' + state.s + qs()), { cache: 'no-store' })
    .then(function(r){ if (r.status === 401) { if (ROLE.share) throw new Error('הקישור אינו תקין או שפג.'); location.href = CFG.loginPath; throw new Error('auth'); } return r.json(); })
    .then(function(d){ if (seq !== state.seq) return; state.data = d; render(d); document.body.classList.remove('loading'); loadMessages(); })
    .catch(function(e){ if (seq === state.seq) { document.body.classList.remove('loading'); $('sub').textContent = 'לא הצלחתי לטעון את הנתונים. ' + e; } });
}

function render(d){
  var av = Array.isArray(d.availability) ? d.availability : [];
  var perPage = av.filter(function(r){ return r.section === 'לפי עמוד'; });
  var outages = av.filter(function(r){ return r.section !== 'לפי עמוד'; });
  var sp = Array.isArray(d.speed) ? d.speed : [];
  var bottom = sp.filter(function(r){ return r.section === 'שורה תחתונה'; })[0];
  var core = sp.filter(function(r){ return r.section === 'ליבה' && r.strategy === state.s; });
  var slow = sp.filter(function(r){ return r.section === 'האיטיים באתר'; });
  var cover = sp.filter(function(r){ return r.section === 'כיסוי'; })[0];
  var open = Array.isArray(d.alerts_open) ? d.alerts_open : [];
  var recent = Array.isArray(d.alerts_recent) ? d.alerts_recent : [];
  var health = Array.isArray(d.health) ? d.health : [];

  /* פס אדום */
  var ab = $('alertbar');
  /* מ-12.11.2026 (הבקשה): תיבת סימון בכל התראה + "לסמן הכול" + "מחק מסומנות", וגם ה-✕ הבודד.
     המחיקה מיידית על המסך: השורה נעלמת בלי לטעון את כל הדף מחדש, והרשימה נשארת פתוחה.
     קודם כל ✕ טען את כל המסך מחדש וקיפל את הרשימה, ולכן מחיקה של 11 התראות לקחה דקות. */
  var AB = window.__shAb || (window.__shAb = { open: false, sel: {} });
  var vis = open.filter(function(a){ return !a.acked; });
  if (vis.length) {
    var live = {}; vis.forEach(function(a){ live[a.id] = 1; });
    // קישור לעמוד שההתראה מדברת עליו (הבקשה, 12.11.2026). הכתובת יושבת בגוף ההתראה; התראה בלי כתובת — בלי קישור.
    var abLink = function(a){ var m = String(a.body || '').match(/https?:\/\/[^\s"'<>]+/); return m ? '<a class="alink" href="' + esc(m[0]) + '" target="_blank" rel="noopener">לפתוח את העמוד ↗</a>' : ''; };
    Object.keys(AB.sel).forEach(function(k){ if (!live[k]) delete AB.sel[k]; });
    var rows = vis.map(function(a){ return '<div class="arow" data-id="' + a.id + '"><label class="acb" title="לסמן למחיקה"><input type="checkbox" data-id="' + a.id + '"' + (AB.sel[a.id] ? ' checked' : '') + ' aria-label="לסמן למחיקה: ' + esc(a.title) + '"></label><div><span class="at">' + esc(a.title) + '</span><span class="sub">' + esc(niceBody(a.body || '', a.title)) + ' · מאז ' + esc(a.opened_il) + '</span>' + abLink(a) + '</div><button type="button" class="ax" data-id="' + a.id + '" title="למחוק את ההתראה הזו מהרשימה (תחזור אם הבעיה תיפתח מחדש)">✕</button></div>'; }).join('');
    // מקופל כברירת מחדל (שאלה 97, 19.9.2026) — גם התראה אחת. אחרי שנפתח בהקשה הוא נשאר פתוח גם ברענון.
    var abWord = function(n){ return '⚠ ' + n + ' ' + (n === 1 ? 'התראה פעילה' : 'התראות פעילות'); };
    ab.innerHTML = '<div class="ahead"><span class="acount">' + abWord(vis.length) + '</span><span class="chev">▾</span></div>'
      + '<div class="abulk"><label><input type="checkbox" id="abAll"> לסמן הכול</label><button type="button" class="adel" id="abDel" disabled>מחק מסומנות</button></div>'
      + '<div class="alist">' + rows + '</div>';
    ab.classList.add('on'); ab.classList.toggle('collapsed', !AB.open);
    ab.querySelector('.ahead').addEventListener('click', function(){ AB.open = !AB.open; ab.classList.toggle('collapsed', !AB.open); });
    var abSync = function(){
      var n = Object.keys(AB.sel).length, total = ab.querySelectorAll('.arow').length;
      var del = $('abDel'), all = $('abAll'); if (!del || !all) return;
      del.disabled = !n; del.textContent = n ? 'מחק מסומנות (' + n + ')' : 'מחק מסומנות';
      all.checked = !!n && n === total;
    };
    var abAck = function(ids){
      if (!ids.length || ROLE.readonly) return;
      var hit = {}; ids.forEach(function(id){ hit[id] = 1; delete AB.sel[id]; var r = ab.querySelector('.arow[data-id="' + id + '"]'); if (r) r.parentNode.removeChild(r); });
      open.forEach(function(a){ if (hit[a.id]) a.acked = true; });   // גם בנתונים שבזיכרון, כדי שציור מחדש לא יחזיר אותן
      var left = ab.querySelectorAll('.arow').length;
      if (!left) { ab.classList.remove('on'); ab.innerHTML = ''; }
      else { ab.querySelector('.acount').textContent = abWord(left); abSync(); }
      fetch(api('/alerts/ack'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: ids }) })
        .then(function(r){ if (!r.ok) throw new Error('ack ' + r.status); })
        .catch(function(){ open.forEach(function(a){ if (hit[a.id]) a.acked = false; }); load(); });   // נכשל: מחזירים ומרעננים
    };
    Array.prototype.forEach.call(ab.querySelectorAll('.arow'), function(r){ r.addEventListener('click', function(){ drillAlert(+r.getAttribute('data-id')); }); });
    Array.prototype.forEach.call(ab.querySelectorAll('.alink'), function(l){ l.addEventListener('click', function(e){ e.stopPropagation(); }); });
    Array.prototype.forEach.call(ab.querySelectorAll('.acb'), function(l){
      l.addEventListener('click', function(e){ e.stopPropagation(); });
      l.querySelector('input').addEventListener('change', function(){ var id = +this.getAttribute('data-id'); if (this.checked) AB.sel[id] = 1; else delete AB.sel[id]; abSync(); });
    });
    $('abAll').addEventListener('change', function(){
      var on = this.checked; AB.sel = {};
      Array.prototype.forEach.call(ab.querySelectorAll('.acb input'), function(c){ c.checked = on; if (on) AB.sel[+c.getAttribute('data-id')] = 1; });
      abSync();
    });
    $('abDel').addEventListener('click', function(){ abAck(Object.keys(AB.sel).map(Number)); });
    Array.prototype.forEach.call(ab.querySelectorAll('.ax'), function(b){ b.addEventListener('click', function(e){ e.stopPropagation(); abAck([+b.getAttribute('data-id')]); }); });
    abSync();
  } else { ab.classList.remove('on'); ab.innerHTML = ''; }

  /* כותרת */
  var lastProbe = health.filter(function(r){ return r.flow_name === 'בודק זמינות האתר'; })[0];
  var lastIl = lastProbe && lastProbe.last_at ? new Date(lastProbe.last_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : '—';
  $('sub').textContent = CFG.siteLabel + ' · הבדיקה האחרונה ' + lastIl + ' · ' + periodTxt();

  /* שורה תחתונה */
  var checks = perPage.reduce(function(a, r){ return a + (+r.checks || 0); }, 0);
  var failed = perPage.reduce(function(a, r){ return a + (+r.failed || 0); }, 0);
  var upPct = checks ? (100 - 100 * failed / checks) : null;
  var outMin = outages.reduce(function(a, r){ return a + (+r.outage_minutes || 0); }, 0);
  var vh = '';
  vh += '<button type="button" class="vbox" data-drill="home"><div class="k">מהירות עמוד הבית בטלפון</div><div class="v">' + (bottom && bottom.lcp_p50 != null ? esc(bottom.verdict) : '<span class="est">אין נתונים</span>') + '</div><div class="m">' + (bottom && bottom.lcp_p50 != null ? sec(bottom.lcp_p50) + ' שניות עד התוכן · ' + bottom.checks + ' מדידות' : 'מדידת המהירות עדיין לא התחילה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="fails"><div class="k">זמינות</div><div class="v">' + (upPct == null ? '<span class="est">—</span>' : upPct.toFixed(upPct < 99.95 ? 2 : 1) + '%') + '</div><div class="m">' + (checks ? n(failed) + ' כשלים מתוך ' + n(checks) + ' בדיקות' : 'אין בדיקות בתקופה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="outages"><div class="k">נפילות</div><div class="v">' + (outages.length ? '<span style="color:var(--dfg)">' + outages.length + '</span>' : '0') + '</div><div class="m">' + (outages.length ? 'סה"כ ' + outMin + ' דקות' : 'האתר לא נפל בתקופה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="alerts"><div class="k">התראות פתוחות</div><div class="v">' + (open.length ? '<span style="color:var(--dfg)">' + open.length + '</span>' : '0') + '</div><div class="m">' + (recent.length ? recent.length + ' בתקופה' : 'אין התראות בתקופה') + '</div></button>';
  $('verdict').innerHTML = vh;
  Array.prototype.forEach.call($('verdict').querySelectorAll('.vbox'), function(b){ b.addEventListener('click', function(){
    var w = b.getAttribute('data-drill');
    if (w === 'home') { if (bottom && bottom.url) drillRuns(bottom.url, CFG.homePage, null); else openSheet('מהירות עמוד הבית', '<p class="dsum">מדידת המהירות עדיין לא התחילה. היא מחכה למפתח מגוגל. ברגע שהוא יוכנס, כאן יופיעו המדידות של עמוד הבית כל רבע שעה.</p>'); }
    else if (w === 'fails') drillFails(null, null, checks, failed, perPage);
    else if (w === 'outages') drillOutages(outages);
    else drillAlerts(recent, open);
  }); });

  /* זמינות */
  if (perPage.length) {
    var t = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th class="num">בדיקות</th><th class="num">כשלים</th><th class="num">אחוז</th><th class="num">שרת p50</th><th class="num">שרת p95</th><th>כשל אחרון</th></tr></thead><tbody>';
    perPage.forEach(function(r, i){
      t += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(r.page) + '</td><td class="num">' + n(+r.checks) + '</td><td class="num">' + (r.failed > 0 ? '<b style="color:var(--dfg)">' + r.failed + '</b>' : '0') + '</td><td class="num">' + esc(r.fail_pct) + '%</td><td class="num">' + (r.p50_ms == null ? '—' : r.p50_ms + ' ms') + '</td><td class="num">' + (r.p95_ms == null ? '—' : r.p95_ms + ' ms') + '</td><td>' + esc(r.last_fail_il || '—') + '</td></tr>';
    });
    $('availTbl').innerHTML = t + '</tbody></table></div>';
    Array.prototype.forEach.call($('availTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = perPage[+tr.getAttribute('data-i')]; drillFails(r.page, null, +r.checks, +r.failed, [r]); }); });
  } else $('availTbl').innerHTML = '<p class="empty">אין בדיקות זמינות בתקופה.</p>';
  $('outages').innerHTML = outages.length
    ? '<p class="eyebrow" style="margin-top:12px">נפילות (3 דקות ומעלה שאף עמוד לא ענה)</p><ul class="list">' + outages.map(function(o, i){ return '<li class="rowbtn" data-i="' + i + '"><span class="tag d">' + o.outage_minutes + ' דק\'</span><span class="when">' + esc(o.outage_start_il) + ' → ' + esc(o.outage_end_il) + '</span></li>'; }).join('') + '</ul>'
    : '';
  Array.prototype.forEach.call($('outages').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillOutages([outages[+li.getAttribute('data-i')]]); }); });
  var pser = Array.isArray(d.availability_series) ? d.availability_series : [];
  $('availChart').innerHTML = availChart(pser);
  Array.prototype.forEach.call($('availChart').querySelectorAll('[data-bucket]'), function(el){ el.addEventListener('click', function(){
    var b = el.getAttribute('data-bucket'), row = pser.filter(function(r){ return r.bucket === b; })[0];
    if (el.classList.contains('bar')) drillFails(null, b, +row.checks, +row.failed, null); else drillBucket(b, row);
  }); });

  /* מהירות לאורך זמן */
  var series = Array.isArray(d.speed_series) ? d.speed_series : [];
  $('legend').innerHTML = '';
  $('speedHint').hidden = !series.length;
  if (series.length) {
    var pages = []; series.forEach(function(r){ if (pages.indexOf(r.page) < 0) pages.push(r.page); });
    $('legend').innerHTML = pages.map(function(p, i){ return '<button type="button" data-p="' + esc(p) + '" aria-pressed="' + (state.hidden[p] ? 'false' : 'true') + '"><i style="background:' + COLORS[i % COLORS.length] + '"></i>' + esc(p) + '</button>'; }).join('');
    Array.prototype.forEach.call($('legend').querySelectorAll('button'), function(b){ b.addEventListener('click', function(){ var p = b.getAttribute('data-p'); state.hidden[p] = !state.hidden[p]; b.setAttribute('aria-pressed', state.hidden[p] ? 'false' : 'true'); drawSpeed(series, pages); }); });
    drawSpeed(series, pages);
  } else $('speedChart').innerHTML = '<p class="empty">' + (state.s === 'desktop' ? 'אין עדיין מדידות מחשב בתקופה (נמדד פעם בשעה).' : 'מדידת המהירות עדיין לא התחילה.') + '</p>';

  /* עמודי ליבה */
  if (core.length) {
    var c = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th>מצב</th><th class="num">ציון</th><th class="num">LCP p50</th><th class="num">LCP p95</th><th class="num">קפיצות</th><th class="num">שרת</th><th class="num">איטי</th><th>גולשים אמיתיים</th></tr></thead><tbody>';
    core.forEach(function(r, i){
      c += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(r.page) + '</td><td>' + lcpTag(r.lcp_p50) + '</td><td class="num">' + (r.score_med == null ? '—' : r.score_med) + '</td><td class="num">' + sec(r.lcp_p50) + ' ש\'</td><td class="num">' + sec(r.lcp_p95) + ' ש\'</td><td class="num">' + (r.cls_med == null ? '—' : r.cls_med) + '</td><td class="num">' + (r.ttfb_p50 == null ? '—' : r.ttfb_p50 + ' ms') + '</td><td class="num">' + r.slow_runs + '/' + r.checks + '</td><td>' + cruxTag(r.crux_category) + (r.crux_lcp ? ' <span class="muted">' + sec(r.crux_lcp) + ' ש\'</span>' : '') + '</td></tr>';
    });
    $('coreTbl').innerHTML = c + '</tbody></table></div>';
    Array.prototype.forEach.call($('coreTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = core[+tr.getAttribute('data-i')]; drillRuns(r.url, r.page, null); }); });
  } else $('coreTbl').innerHTML = '<p class="empty">אין מדידות ' + (state.s === 'desktop' ? 'מחשב' : 'טלפון') + ' בתקופה.</p>';

  /* הכבדים */
  $('coverage').textContent = cover ? 'נדגמו ' + cover.checks + ' מתוך ' + cover.slow_runs + ' עמודי האתר בתקופה.' : '';
  if (slow.length) {
    var s = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th>מצב</th><th class="num">LCP p50</th><th class="num">ציון</th><th class="num">מדידות</th><th>אחרונה</th></tr></thead><tbody>';
    slow.forEach(function(r, i){
      s += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(short(r.page)) + '</td><td>' + lcpTag(r.lcp_p50) + '</td><td class="num">' + sec(r.lcp_p50) + ' ש\'</td><td class="num">' + (r.score_med == null ? '—' : r.score_med) + '</td><td class="num">' + r.checks + '</td><td>' + esc(r.last_il) + '</td></tr>';
    });
    $('slowTbl').innerHTML = s + '</tbody></table></div>';
    Array.prototype.forEach.call($('slowTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = slow[+tr.getAttribute('data-i')]; drillRuns(r.url, short(r.url), null); }); });
  } else $('slowTbl').innerHTML = '<p class="empty">הסבב על כל האתר עדיין לא התחיל.</p>';

  /* מוצרים שבורים */
  var iss = Array.isArray(d.product_issues) ? d.product_issues : [];
  if (iss.length) {
    var byI = {}; iss.forEach(function(r){ (byI[r.issue] = byI[r.issue] || []).push(r); });
    var ih = '<p class="muted">' + Object.keys(byI).map(function(k){ return k + ': ' + byI[k].length; }).join(' · ') + ' · לפי צילום ' + esc(iss[0].snap_date) + '</p>';
    ih += '<div class="tblwrap"><table><thead><tr><th>מה</th><th>מוצר</th></tr></thead><tbody>';
    iss.slice(0, 60).forEach(function(r){ ih += '<tr><td><span class="tag ' + (r.issue === 'לא במלאי' ? 'w' : 'd') + '">' + esc(r.issue) + '</span></td><td><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.name) + '</a></td></tr>'; });
    $('issuesTbl').innerHTML = ih + '</tbody></table></div>' + (iss.length > 60 ? '<p class="muted">מוצגים 60 מתוך ' + iss.length + '.</p>' : '');
  } else $('issuesTbl').innerHTML = '<p class="empty">' + (d.product_issues && d.product_issues.error ? 'הבדיקה לא זמינה.' : 'לא נמצאו מוצרים שבורים בצילום האחרון.') + '</p>';

  /* תעודה */
  var ce = d.cert;
  if (ce && ce.host) {
    var dl = ce.days_left, cls = !ce.ok ? 'd' : dl < 14 ? 'd' : dl < 30 ? 'w' : 'ok';
    $('certBox').innerHTML = '<div class="verdict"><div class="vbox" style="cursor:default"><div class="k">תוקף</div><div class="v">' + (ce.ok ? dl + ' ימים' : 'הבדיקה נכשלה') + '</div><div class="m">' + (ce.ok ? 'עד ' + new Date(ce.not_after).toLocaleDateString('he-IL') + ' · ' + esc(ce.issuer || '') : esc(ce.err || '')) + '</div></div><div class="vbox" style="cursor:default"><div class="k">מצב</div><div class="v"><span class="tag ' + cls + '">' + (!ce.ok ? 'לא ידוע' : dl < 14 ? 'לחדש עכשיו' : dl < 30 ? 'לשים לב' : 'תקין') + '</span></div><div class="m">נבדק ' + new Date(ce.checked_at).toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '</div></div></div>';
  } else $('certBox').innerHTML = '<p class="empty">עדיין לא נבדק (הבדיקה הראשונה ב-04:00).</p>';

  /* התראות */
  $('alertsList').innerHTML = recent.length
    ? '<ul class="list">' + recent.map(function(a){ return '<li class="rowbtn" data-id="' + a.id + '"><span class="tag ' + (a.open ? 'd' : 'n') + '">' + (a.open ? 'פתוחה' : 'נסגרה') + '</span><b>' + esc(a.title) + '</b><span class="muted">' + esc(niceBody(a.body || '', a.title)) + '</span><span class="when">' + esc(a.opened_il) + (a.closed_il ? ' → ' + esc(a.closed_il) : '') + ' · ' + a.minutes + ' דק\'</span></li>'; }).join('') + '</ul>'
    : '<p class="empty">אין התראות בתקופה. זה טוב.</p>';
  var _an = $('alertsN'); if (_an) _an.textContent = ' · ' + recent.length;
  Array.prototype.forEach.call($('alertsList').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillAlert(+li.getAttribute('data-id')); }); });

  /* המדידה עצמה */
  $('healthTbl').innerHTML = health.length
    ? '<ul class="list">' + health.map(function(r, i){ var cls = r.status === 'תקין' ? 'ok' : r.status === 'מתעכב' ? 'w' : r.status === 'שקט' ? 'd' : 'n'; return '<li class="rowbtn" data-i="' + i + '"><span class="tag ' + cls + '">' + esc(r.status) + '</span>' + esc(r.flow_name) + '<span class="muted">' + esc(r.cadence || '') + (r.silent_txt ? ' · ' + esc(r.silent_txt) : '') + '</span></li>'; }).join('') + '</ul>'
    : '<p class="empty">אין נתוני מדידה.</p>';
  Array.prototype.forEach.call($('healthTbl').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillHealth(health[+li.getAttribute('data-i')]); }); });
}

/* ---------- גרפים (SVG בלי ספרייה) ---------- */
function xlabel(b){ return b.length > 10 ? b.slice(11, 16) : b.slice(8, 10) + '.' + b.slice(5, 7); }
function drawSpeed(series, pages){
  $('speedChart').innerHTML = speedChart(series, pages);
  Array.prototype.forEach.call($('speedChart').querySelectorAll('.pt'), function(el){ el.addEventListener('click', function(){ drillRuns(el.getAttribute('data-url'), el.getAttribute('data-page'), el.getAttribute('data-bucket')); }); });
}
function speedChart(series, pages){
  var W = 720, H = 240, L = 34, R = 8, T = 12, B = 28;
  var buckets = []; series.forEach(function(r){ if (buckets.indexOf(r.bucket) < 0) buckets.push(r.bucket); }); buckets.sort();
  var vis = pages.filter(function(p){ return !state.hidden[p]; });
  var maxV = 5000; series.forEach(function(r){ if (vis.indexOf(r.page) >= 0 && r.lcp_p50 > maxV) maxV = r.lcp_p50; }); maxV = Math.ceil(maxV / 1000) * 1000;
  var x = function(i){ return buckets.length < 2 ? (L + (W - L - R) / 2) : L + (W - L - R) * i / (buckets.length - 1); };
  var y = function(v){ return T + (H - T - B) * (1 - v / maxV); };
  var s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="מהירות לאורך זמן">';
  for (var g = 0; g <= maxV; g += 1000) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(g) + '" y2="' + y(g) + '"/><text x="' + (L - 4) + '" y="' + (y(g) + 4) + '" text-anchor="end">' + (g / 1000) + '</text>';
  [[2500, 'גוגל 2.5'], [4000, 'איטי 4']].forEach(function(rf){ if (rf[0] <= maxV) s += '<line class="ref" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(rf[0]) + '" y2="' + y(rf[0]) + '"/><text class="reft" x="' + (W - R - 2) + '" y="' + (y(rf[0]) - 3) + '" text-anchor="end">' + rf[1] + '</text>'; });
  var step = Math.max(1, Math.ceil(buckets.length / 8));
  buckets.forEach(function(b, i){ if (i % step === 0 || i === buckets.length - 1) s += '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + xlabel(b) + '</text>'; });
  pages.forEach(function(p, pi){
    if (state.hidden[p]) return;
    var pts = [], url = '';
    buckets.forEach(function(b, i){ var r = series.filter(function(q){ return q.page === p && q.bucket === b; })[0]; if (r && r.lcp_p50 != null) { url = r.url; pts.push([x(i), y(Math.min(r.lcp_p50, maxV)), b, r]); } });
    if (!pts.length) return;
    s += '<path class="ln" stroke="' + COLORS[pi % COLORS.length] + '" d="M' + pts.map(function(q){ return q[0].toFixed(1) + ' ' + q[1].toFixed(1); }).join(' L') + '"/>';
    pts.forEach(function(q){ s += '<circle class="pt" data-url="' + esc(url) + '" data-page="' + esc(p) + '" data-bucket="' + esc(q[2]) + '" cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="7" fill="' + COLORS[pi % COLORS.length] + '" fill-opacity="0.15"><title>' + esc(p) + ' ' + xlabel(q[2]) + ': ' + sec(q[3].lcp_p50) + ' ש\'</title></circle><circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="2.6" fill="' + COLORS[pi % COLORS.length] + '" pointer-events="none"/>'; });
  });
  return s + '</svg>';
}
function availChart(rows){
  if (!rows.length) return '';
  var W = 720, H = 160, L = 34, R = 40, T = 12, B = 28;
  var maxF = 1; rows.forEach(function(r){ if (+r.failed > maxF) maxF = +r.failed; });
  var maxMs = 500; rows.forEach(function(r){ if (+r.ms_p50 > maxMs) maxMs = +r.ms_p50; }); maxMs = Math.ceil(maxMs / 250) * 250;
  var n = rows.length, bw = Math.max(3, (W - L - R) / n - 2);
  var x = function(i){ return L + (W - L - R) * (i + 0.5) / n; };
  var yf = function(v){ return T + (H - T - B) * (1 - v / maxF); };
  var ym = function(v){ return T + (H - T - B) * (1 - v / maxMs); };
  var s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="זמינות לאורך זמן">';
  s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + (H - B) + '" y2="' + (H - B) + '"/>';
  s += '<text x="' + (L - 4) + '" y="' + (T + 4) + '" text-anchor="end">' + maxF + '</text><text x="' + (L - 4) + '" y="' + (H - B + 4) + '" text-anchor="end">0</text>';
  s += '<text x="' + (W - R + 4) + '" y="' + (T + 4) + '">' + maxMs + 'ms</text>';
  var step = Math.max(1, Math.ceil(n / 8));
  rows.forEach(function(r, i){
    if (+r.failed > 0) s += '<rect class="bar" data-bucket="' + esc(r.bucket) + '" x="' + (x(i) - bw / 2) + '" y="' + yf(+r.failed) + '" width="' + bw + '" height="' + (H - B - yf(+r.failed)) + '"><title>' + esc(r.bucket) + ': ' + r.failed + ' כשלים מתוך ' + r.checks + '</title></rect>';
    if (i % step === 0 || i === n - 1) s += '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + xlabel(r.bucket) + '</text>';
  });
  var pts = rows.map(function(r, i){ return r.ms_p50 == null ? null : x(i).toFixed(1) + ' ' + ym(+r.ms_p50).toFixed(1); }).filter(Boolean);
  if (pts.length > 1) s += '<path class="ms" d="M' + pts.join(' L') + '"/>';
  rows.forEach(function(r, i){ if (r.ms_p50 != null) s += '<circle class="hit" data-bucket="' + esc(r.bucket) + '" cx="' + x(i).toFixed(1) + '" cy="' + ym(+r.ms_p50).toFixed(1) + '" r="9"><title>' + esc(r.bucket) + ': שרת ' + r.ms_p50 + ' ms</title></circle>'; });
  return s + '</svg>';
}

/* ---------- חלון העומק ---------- */
var dov = $('dov');
function openSheet(title, html){ $('dttl').textContent = title; $('dbody').innerHTML = html; dov.classList.add('on'); document.body.style.overflow = 'hidden'; $('dsheet').scrollTo(0, 0); }
function closeSheet(){ dov.classList.remove('on'); document.body.style.overflow = ''; }
$('dx').addEventListener('click', closeSheet);
dov.addEventListener('click', function(e){ if (e.target === dov) closeSheet(); });
document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && dov.classList.contains('on')) closeSheet(); });
function drill(params){ return fetch(api('/site/drill?' + params + qs()), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){ if (d.error) throw new Error(d.error); return d.rows || []; }); }
function loading(title){ openSheet(title, '<p class="empty"><i style="display:inline-block;width:12px;height:12px;border:2px solid var(--tx3);border-top-color:transparent;border-radius:50%;animation:sp .8s linear infinite;vertical-align:middle;margin-inline-end:6px"></i>טוען…</p>'); }
function fail(e){ $('dbody').innerHTML = '<p class="empty">לא הצלחתי לטעון. ' + esc(e) + '</p>'; }

function drillFails(page, bucket, checks, failed, perPage){
  var title = page ? 'הכשלים של עמוד ' + page : bucket ? 'הכשלים ' + bucketTxt(bucket) : 'כל הכשלים';
  loading(title);
  drill('what=fails&page=' + encodeURIComponent(page || '') + '&bucket=' + encodeURIComponent(bucket || '')).then(function(rows){
    var h = '';
    if (checks) h += '<p class="dsum"><b>' + n(failed) + '</b> בדיקות נכשלו מתוך <b>' + n(checks) + '</b> (' + (100 * failed / checks).toFixed(2) + ' אחוז). ' + (failed === 0 ? 'הכל ענה.' : failed <= 3 ? 'כשל בודד פה ושם הוא רעש רגיל של רשת, לא תקלה.' : 'זה מעבר לרעש רגיל. כדאי לראות אם הכשלים מקובצים בשעה אחת (אירוע) או מפוזרים (עומס).') + '</p>';
    var kinds = {}; rows.forEach(function(r){ kinds[r.kind] = (kinds[r.kind] || 0) + 1; });
    if (rows.length) h += '<div class="dwhat">מה קרה: ' + Object.keys(kinds).map(function(k){ return esc(k) + ' × ' + kinds[k]; }).join(' · ') + '</div>';
    if (!page && perPage && perPage.length > 1) h += '<h3>לפי עמוד</h3><ul class="list">' + perPage.map(function(r){ return '<li><b>' + esc(r.page) + '</b> ' + r.failed + ' מתוך ' + n(+r.checks) + '</li>'; }).join('') + '</ul>';
    h += '<h3>הבדיקות שנכשלו' + (rows.length >= 500 ? ' (500 האחרונות)' : '') + '</h3>';
    h += rows.length ? '<div class="tblwrap"><table><thead><tr><th>מתי</th><th>עמוד</th><th>מה קרה</th><th class="num">אחרי</th></tr></thead><tbody>' + rows.map(function(r){ return '<tr><td>' + esc(r.at_il) + '</td><td>' + esc(r.page) + '</td><td>' + esc(r.kind) + (r.err ? ' <span class="muted">' + esc(r.err.slice(0, 60)) + '</span>' : '') + '</td><td class="num">' + (r.ms == null ? '—' : (r.ms / 1000).toFixed(1) + ' ש\'') + '</td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="empty">אין כשלים.</p>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillBucket(b, row){
  loading('זמן תגובת השרת ' + bucketTxt(b));
  drill('what=bucket&bucket=' + encodeURIComponent(b)).then(function(rows){
    var h = '<p class="dsum">חציון זמן התגובה: <b>' + row.ms_p50 + ' ms</b>. הכי איטי (95 אחוז): <b>' + row.ms_p95 + ' ms</b>. ' + (row.ms_p50 <= 800 ? 'השרת ענה מהר (הסף של גוגל: 800).' : row.ms_p50 <= 1500 ? 'השרת ענה לאט מהרצוי. אם זה חוזר בשעות מסוימות, זה עומס.' : 'השרת ענה לאט מאוד. זה לפני שהעמוד בכלל מתחיל להיטען אצל הלקוח.') + '</p>';
    h += '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th class="num">בדיקות</th><th class="num">כשלים</th><th class="num">חציון</th><th class="num">הכי איטי</th><th>מתי</th></tr></thead><tbody>' + rows.map(function(r){ return '<tr><td>' + esc(r.page) + '</td><td class="num">' + r.checks + '</td><td class="num">' + r.failed + '</td><td class="num">' + (r.ms_p50 == null ? '—' : r.ms_p50 + ' ms') + '</td><td class="num">' + (r.ms_max == null ? '—' : r.ms_max + ' ms') + '</td><td>' + esc(r.worst_il || '') + '</td></tr>'; }).join('') + '</tbody></table></div>';
    if (CFG.bucketNote) h += '<div class="dwhat">' + esc(CFG.bucketNote) + '</div>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillOutages(list){
  var h = list.length ? '<p class="dsum">' + (list.length === 1 ? 'נפילה אחת' : list.length + ' נפילות') + ' בתקופה. נפילה = 3 דקות רצופות שבהן אף אחד מ-' + CFG.probeCount + ' העמודים לא ענה. סך הכל <b>' + list.reduce(function(a, r){ return a + (+r.outage_minutes || 0); }, 0) + ' דקות</b> שבהן לקוח לא יכול היה להיכנס.</p><ul class="list">' + list.map(function(o){ return '<li><span class="tag d">' + o.outage_minutes + ' דק\'</span><span class="when">' + esc(o.outage_start_il) + ' → ' + esc(o.outage_end_il) + '</span></li>'; }).join('') + '</ul><div class="dwhat">לראות מה קרה בדיוק: לחיצה על העמודה האדומה של אותה שעה בגרף הזמינות.</div>' : '<p class="dsum">האתר לא נפל בתקופה. כשל של דקה אחת בעמוד אחד נספר בזמינות, לא כאן.</p>';
  openSheet('נפילות', h);
}
function drillAlerts(recent, open){
  var h = '<p class="dsum">' + (open.length ? '<b>' + open.length + '</b> התראות פתוחות עכשיו.' : 'אין התראה פתוחה עכשיו.') + ' ' + (recent.length ? recent.length + ' התראות בתקופה.' : 'לא היו התראות בתקופה.') + '</p>';
  h += recent.length ? '<ul class="list">' + recent.map(function(a){ return '<li class="rowbtn" data-id="' + a.id + '"><span class="tag ' + (a.open ? 'd' : 'n') + '">' + (a.open ? 'פתוחה' : 'נסגרה') + '</span><b>' + esc(a.title) + '</b><span class="when">' + esc(a.opened_il) + ' · ' + a.minutes + ' דק\'</span></li>'; }).join('') + '</ul>' : '';
  openSheet('התראות', h);
  Array.prototype.forEach.call($('dbody').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillAlert(+li.getAttribute('data-id')); }); });
}
function drillAlert(id){
  loading('התראה');
  drill('what=alert&id=' + id).then(function(rows){
    var a = rows[0]; if (!a) { $('dbody').innerHTML = '<p class="empty">לא נמצאה.</p>'; return; }
    $('dttl').textContent = a.title;
    var h = '<p class="dsum">' + (a.open ? 'עדיין פתוחה, ' : 'נסגרה. ') + 'נפתחה ב-<b>' + esc(a.opened_il) + '</b>' + (a.closed_il ? ', נסגרה ב-<b>' + esc(a.closed_il) + '</b>' : '') + ', סך הכל <b>' + a.minutes + ' דקות</b>.<br>' + esc(niceBody(a.body || '', a.title)) + '</p>';
    var what = { down: 'בדיקת זמינות נכשלה. הכלל: כל כשל בודד מתריע, גם של שנייה. כשל אחד ויחיד הוא לרוב רעש רשת; שניים-שלושה ברצף הם תקלה אמיתית.', slow: 'עמוד עיקרי נמדד איטי (מעל 4 שניות עד התוכן) פעמיים ברצף. אם זה קורה בשעות עומס בלבד, זה השרת. אם תמיד, זה העמוד עצמו (תמונות, תוספים).', silent: 'הבודק עצמו הפסיק לרוץ. עד שהוא חוזר, המספרים במסך ישנים.', cert: 'תעודת האבטחה עומדת לפוג. צריך לחדש אצל חברת האחסון או להפעיל חידוש אוטומטי.' };
    h += '<div class="dwhat">' + (what[a.kind] || '') + '</div>';
    if (a.fails && a.fails.length) h += '<h3>הבדיקות שנכשלו מאחורי ההתראה</h3><div class="tblwrap"><table><thead><tr><th>מתי</th><th>עמוד</th><th>מה</th></tr></thead><tbody>' + a.fails.map(function(f){ return '<tr><td>' + esc(f.at) + '</td><td>' + esc(f.page) + '</td><td>' + esc(f.status ? 'קוד ' + f.status : (f.err || '')) + '</td></tr>'; }).join('') + '</tbody></table></div>';
    if (a.sent && a.sent.length) h += '<h3>הודעות שנשלחו לטלפון</h3><ul class="list">' + a.sent.map(function(s){ return '<li><span class="tag ' + (s.status === 200 ? 'ok' : 'd') + '">' + (s.status === 200 ? 'נשלחה' : 'נכשלה') + '</span>' + (s.event === 'open' ? 'פתיחה' : s.event === 'close' ? 'חזר לתקין' : esc(s.event)) + '<span class="when">' + esc(s.at) + '</span></li>'; }).join('') + '</ul>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillRuns(url, page, bucket){
  var title = 'מהירות: ' + page + (bucket ? ' ' + bucketTxt(bucket) : '');
  loading(title);
  drill('what=runs&url=' + encodeURIComponent(url) + '&strategy=' + state.s + '&bucket=' + encodeURIComponent(bucket || '')).then(function(rows){
    var ok = rows.filter(function(r){ return r.ok; });
    if (!ok.length) { $('dbody').innerHTML = '<p class="empty">אין מדידות תקינות' + (rows.length ? ' (' + rows.length + ' ניסיונות נכשלו: ' + esc(rows[0].err || '') + ')' : '') + '.</p>'; return; }
    var lcps = ok.map(function(r){ return r.lcp_ms; }).filter(function(v){ return v != null; }).sort(function(a, b){ return a - b; });
    var med = lcps[Math.floor(lcps.length / 2)], worst = ok.reduce(function(a, r){ return (r.lcp_ms || 0) > (a.lcp_ms || 0) ? r : a; }, ok[0]), best = ok.reduce(function(a, r){ return (r.lcp_ms || 1e9) < (a.lcp_ms || 1e9) ? r : a; }, ok[0]);
    var h = '<p class="dsum"><b>' + ok.length + '</b> מדידות ב' + (state.s === 'desktop' ? 'מחשב' : 'טלפון') + '. חציון <b>' + sec(med) + ' שניות</b> עד התוכן העיקרי: <b>' + lcpWord(med) + '</b>. הכי איטית ' + sec(worst.lcp_ms) + ' ש\' (' + esc(worst.at_il) + '), הכי מהירה ' + sec(best.lcp_ms) + ' ש\' (' + esc(best.at_il) + ').' + (ok[0].crux_category ? ' אצל גולשים אמיתיים גוגל מודדת: <b>' + (ok[0].crux_category === 'FAST' ? 'מהיר' : ok[0].crux_category === 'AVERAGE' ? 'בינוני' : 'איטי') + '</b>' + (ok[0].crux_lcp_ms ? ' (' + sec(ok[0].crux_lcp_ms) + ' ש\')' : '') + '.' : '') + '</p>';
    /* מה מאט: ממוצע החיסכון לכל סיבה על פני המדידות */
    var agg = {}; ok.forEach(function(r){ (r.opps || []).forEach(function(o){ var k = o.id; agg[k] = agg[k] || { id: k, title: o.title, sum: 0, cnt: 0 }; agg[k].sum += +o.ms || 0; agg[k].cnt++; }); });
    var opps = Object.keys(agg).map(function(k){ return agg[k]; }).sort(function(a, b){ return b.sum / b.cnt - a.sum / a.cnt; }).slice(0, 6);
    if (opps.length) h += '<h3>מה מאט את העמוד (לפי גוגל)</h3><ul class="list">' + opps.map(function(o){ return '<li><b>' + sec(o.sum / o.cnt) + ' ש\'</b> ' + esc(oppName(o)) + '</li>'; }).join('') + '</ul><div class="dwhat">המספר = כמה זמן אפשר לחסוך אם מטפלים בסיבה הזאת, לפי ההערכה של גוגל. הסיבות הראשונות הן כמעט תמיד תמונות: לדחוס, להקטין לגודל התצוגה, ולטעון רק כשגוללים.</div>';
    h += '<h3>המדידות</h3><div class="tblwrap"><table><thead><tr><th>מתי</th><th>מצב</th><th class="num">ציון</th><th class="num">תוכן (LCP)</th><th class="num">שרת</th><th class="num">משקל</th><th class="num">קפיצות</th></tr></thead><tbody>' + ok.slice(0, 100).map(function(r){ return '<tr><td>' + esc(r.at_il) + '</td><td>' + lcpTag(r.lcp_ms) + '</td><td class="num">' + (r.score == null ? '—' : r.score) + '</td><td class="num">' + sec(r.lcp_ms) + ' ש\'</td><td class="num">' + (r.ttfb_ms == null ? '—' : r.ttfb_ms + ' ms') + '</td><td class="num">' + (r.bytes == null ? '—' : (r.bytes / 1048576).toFixed(1) + ' MB') + '</td><td class="num">' + (r.cls == null ? '—' : r.cls) + '</td></tr>'; }).join('') + '</tbody></table></div>' + (ok.length > 100 ? '<p class="more">מוצגות 100 מתוך ' + ok.length + '.</p>' : '');
    h += '<p class="more"><a href="' + esc(url) + '" target="_blank" rel="noopener">לפתוח את העמוד באתר</a></p>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillHealth(r){
  /* הסבר לכל שורה. שורה שאין לה הסבר כאן מציגה את השדה note שהשרת שולח. */
  var what = {
    'בודק זמינות האתר': 'כל דקה הבודק פונה ל-' + CFG.probeCount + ' עמודים באתר ורושם אם ענו ותוך כמה זמן. אם השורה הזאת שקטה, הבודק עצמו נעצר ואף אחד לא בודק את האתר.',
    'מדידת מהירות — עמודי ליבה': 'כל רבע שעה גוגל מודדת עבורנו את ' + CFG.coreCount + ' העמודים העיקריים בטלפון (ופעם בשעה במחשב). דורש מפתח מגוגל. אם השורה שקטה, המדידה נעצרה או שהמפתח חסר.',
    'מדידת מהירות — סבב כל האתר': 'כל 5 דקות נמדדים 2 עמודים מכל האתר, כך שכל עמוד נמדד בערך פעם ביום.',
    'טעינת מפת האתר': 'פעם בלילה נטענת רשימת כל העמודים באתר (מוצרים, קטגוריות) כדי שהסבב יכיר עמודים חדשים.',
    'בדיקת תעודת האבטחה': 'פעם ביום נבדק מתי תעודת האבטחה של האתר פגה.',
    'בדיקת מוצרים שבורים': 'פעם ביום ב-04:00 נקרא כל הקטלוג הציבורי של האתר ונבדק אם יש מוצר בלי מחיר, בלי תמונה, לא במלאי או שאי אפשר להוסיף לסל.',
    'מהירות אצל לקוחות': 'קוד מדידה קטן באתר שולח מכל צפייה בעמוד כמה זמן לקח עד שהתוכן העיקרי הוצג. אם השורה שקטה, הקוד הוסר מהאתר או שהמדידות לא מגיעות.'
  };
  var status = r.status === 'תקין' ? 'רץ כמו שצריך.' : r.status === 'מתעכב' ? 'מאחר. אם זה לא חוזר לתקין תוך שעה, יש בעיה.' : r.status === 'שקט' ? 'נעצר. המספרים שתלויים בו ישנים.' : r.status === 'אין נתון' ? 'עדיין לא רץ אף פעם.' : r.status;
  openSheet(r.flow_name, '<p class="dsum"><b>' + esc(r.status) + '</b>: ' + status + (r.last_at ? ' הריצה האחרונה: ' + new Date(r.last_at).toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '.' : '') + '</p><div class="dwhat">' + (what[r.flow_name] || esc(r.note || '')) + '</div><p class="muted">קצב: ' + esc(r.cadence || '') + ' · סף איחור: ' + r.warn_minutes + ' דק\' · סף שתיקה: ' + r.late_minutes + ' דק\'</p>');
}

/* ---------- פקדים ---------- */
function setPreset(h){ state.h = h; state.f = ''; state.t = ''; $('dFrom').value = ''; $('dTo').value = ''; Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(o){ o.setAttribute('aria-pressed', +o.getAttribute('data-h') === h ? 'true' : 'false'); }); load(); }
Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(b){ b.addEventListener('click', function(){ setPreset(+b.getAttribute('data-h')); }); });
Array.prototype.forEach.call(document.querySelectorAll('#segS button'), function(b){ b.addEventListener('click', function(){ state.s = b.getAttribute('data-s'); Array.prototype.forEach.call(document.querySelectorAll('#segS button'), function(o){ o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); }); load(); }); });
$('dGo').addEventListener('click', function(){
  var f = $('dFrom').value, t = $('dTo').value || new Date().toISOString().slice(0, 10);
  if (!f) { $('dFrom').focus(); return; }
  if (t < f) { var x = f; f = t; t = x; }
  state.f = f; state.t = t; $('dTo').value = t;
  Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(o){ o.setAttribute('aria-pressed', 'false'); });
  load();
});
$('refbtn').addEventListener('click', load);
$('explbtn').addEventListener('click', function(){ var on = document.body.classList.toggle('explain-on'); $('explbtn').setAttribute('aria-pressed', on ? 'true' : 'false'); });
$('pdfbtn') && $('pdfbtn').addEventListener('click', function(){ window.print(); });
load();
setInterval(function(){ if (!dov.classList.contains('on')) load(); }, 60000);

/* ---------- עכשיו: סבב הבדיקה האחרון, מתרענן כל 60 שניות גם כשגיליון פתוח ---------- */
function nowColorMs(ms){ if (ms == null) return 'n'; return ms <= 500 ? 'ok' : ms <= 1500 ? 'w' : 'd'; }
function nowSec(ms){ return ms == null ? '—' : (ms / 1000).toFixed(ms < 1000 ? 2 : 1) + ' שנ\''; }
/* מאיזה אתר הגיעו המדידות של "מהירות אצל לקוחות": האתר החי או משהו אחר (פיתוח) */
function rumSrc(s){
  if (!s || !s.n || !s.hosts || !s.hosts.length) return '';
  /* קוד המדידה כותב site = 'live' באתר החי; כל ערך אחר (סביבת פיתוח) מוצג בצבע אזהרה */
  var live = function(h){ return CFG.liveHosts.indexOf(h) >= 0; };
  var other = s.hosts.filter(function(x){ return !live(x.host); });
  var t = s.test ? ' · מתוכן ' + s.test + ' מדידות בדיקה' : '';
  if (!other.length) return '<br>מקור: האתר החי · כל ' + s.n + ' המדידות האחרונות' + t;
  return '<br><span style="color:var(--warn,#b26a00)">מקור: ' + s.hosts.map(function(x){ return esc(x.host) + ' ' + x.n; }).join(' · ') + ' (מתוך ' + s.n + ' המדידות האחרונות)' + t + '</span>';
}
function renderNow(d){
  var pages = Array.isArray(d.pages) ? d.pages : [];
  var age = d.age_sec == null ? null : Math.max(0, d.age_sec);
  var ageTxt = age == null ? 'אין בדיקה ב־15 הדקות האחרונות' : ('נבדק לפני ' + (age < 90 ? age + ' שניות' : Math.round(age / 60) + ' דקות'));
  var okN = pages.filter(function(p){ return p.ok; }).length;
  /* זמינות: מהסבב האחרון מכל סוג (מלא כל דקה, קל כל 30 שניות). תגובת שרת: מהסבב המלא האחרון בלבד. */
  var latest = Array.isArray(d.latest) ? d.latest : pages; var okL = latest.filter(function(p){ return p.ok; }).length;
  var lightTxt = d.light ? ' · בדיקה קלה' : '';
  var site = !latest.length ? ['n', 'אין נתון', ageTxt] : d.all_ok ? ['ok', 'פעיל', ageTxt + lightTxt + ' · ' + okL + ' מתוך ' + latest.length + ' עמודים עונים'] : d.any_ok ? ['w', 'חלקי', ageTxt + lightTxt + ' · ' + okL + ' מתוך ' + latest.length + ' עונים'] : ['d', 'נפל', ageTxt + lightTxt + ' · אף עמוד לא עונה'];
  var home = pages.filter(function(p){ return p.page === CFG.homePage; })[0];
  var slowest = pages.slice().sort(function(a, b){ return (b.ms || 0) - (a.ms || 0); })[0];
  var srv = home && home.ok ? ['' + nowColorMs(home.ms), nowSec(home.ms), 'דף הבית' + (slowest && slowest.page !== CFG.homePage ? ' · הכי איטי כרגע: ' + esc(slowest.page) + ' ' + nowSec(slowest.ms) : '')] : home ? ['d', 'לא עונה', 'דף הבית'] : ['n', '—', 'אין נתון'];   /* בלי סבב בדיקה בכלל: "אין נתון", לא "לא עונה" */
  var rum = d.rum || {}; var rumBox = rum.n ? [nowColorMs(rum.p75_ms <= 2500 ? 400 : rum.p75_ms <= 4000 ? 1000 : 2000), nowSec(rum.p75_ms), rum.n + ' צפיות בשעה האחרונה · אחוזון 75' + rumSrc(d.rum_src)] : ['n', '—', 'אין מדידות בשעה האחרונה' + rumSrc(d.rum_src)];
  var sp = d.speed || {}; var spT = sp.checked_at ? new Date(sp.checked_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : '—';
  var lab = sp.lcp_ms ? [sp.lcp_ms <= 2500 ? 'ok' : sp.lcp_ms <= 4000 ? 'w' : 'd', (sp.lcp_ms / 1000).toFixed(1) + ' שנ\'', 'דף הבית בטלפון, ' + spT + ' · ציון ' + (sp.score == null ? '—' : sp.score) + ' · יעד 2.5'] : ['n', '—', 'אין מדידה'];
  function box(k, c){ return '<div class="nbox"><div class="k">' + k + '</div><div class="v"><span class="dot ' + c[0] + '"></span>' + c[1] + '</div><div class="m">' + c[2] + '</div></div>'; }
  $('now').innerHTML = box('האתר עכשיו', site) + box('תגובת שרת עכשיו', srv) + box('מהירות אצל לקוחות, שעה אחרונה', rumBox) + box('מעבדה, מדידה אחרונה', lab);
  $('nowpages').innerHTML = pages.map(function(p){ var c = p.ok ? nowColorMs(p.ms) : 'd'; return '<span class="tag ' + (c === 'ok' ? 'ok' : c === 'w' ? 'w' : 'd') + '" title="' + esc(p.url || '') + '">' + esc(p.page) + ' ' + (p.ok ? nowSec(p.ms) : 'לא עונה' + (p.status ? ' (' + p.status + ')' : '')) + '</span>'; }).join('');
  var al = +d.alerts_open || 0;
  $('nowtick').textContent = 'עודכן ' + new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' · רענון אוטומטי כל 60 שניות' + (al ? ' · ' + al + ' התראות פתוחות' : '');
}
function loadNow(){
  fetch(api('/site/now'), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){ if (!d || d.error) throw new Error(d && d.error || 'no data'); renderNow(d); })
    .catch(function(e){ $('nowtick').textContent = 'לא הצלחתי לטעון את "עכשיו": ' + e; });
}
loadNow(); setInterval(loadNow, 60000);

/* קיפול כרטיסים: לחיצה על כותרת עם .foldhead פותחת/סוגרת את גוף הכרטיס */
document.addEventListener('click', function(e){ var h = e.target.closest && e.target.closest('.foldhead'); if (h && h.parentElement && h.parentElement.classList.contains('foldcard')) h.parentElement.classList.toggle('collapsed'); });

/* ---------- יומן הודעות ---------- */
function loadMessages(){
  var el = $('msgList'); if (!el || ROLE.readonly) return;
  fetch(api('/messages?' + qs().replace(/^&/, '')), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){
    var rows = Array.isArray(d.rows) ? d.rows : [];
    el.innerHTML = rows.length ? '<ul class="list">' + rows.map(function(m){ return '<li><span class="tag ' + (m.kind === 'התראה' ? 'd' : m.kind === 'חזר לתקין' ? 'ok' : 'n') + '">' + esc(m.kind) + '</span><b>' + esc(m.title || '') + '</b><span class="muted" style="white-space:pre-line;flex-basis:100%">' + esc(niceBody(m.msg || '', m.title)) + '</span><span class="when">' + esc(m.at_il) + (m.sent ? '' : ' · לא נשלחה') + '</span></li>'; }).join('') + '</ul>' : '<p class="empty">לא נשלחו הודעות בתקופה.</p>';
    var _mn = $('msgN'); if (_mn) _mn.textContent = ' · ' + rows.length;
  }).catch(function(){ el.innerHTML = '<p class="empty">לא הצלחתי לטעון את ההודעות.</p>'; });
}
</script>
</body>
</html>
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/mock_server.py sha256=8fe7c8b568fc5642d4e4e9f207df46b77c97346ee0bdeaa88cfe0fea30c938f8 -->
~~~~~~~~python
#!/usr/bin/env python3
"""Mock backend for the site-health screen. Standard library only.

It serves the screen and answers every data call with realistic, deterministic fake data,
in exactly the shapes described in SPEC.md ("API contract"). Use it to:
  * see the screen working before any real backend exists;
  * compare your real backend's answers with these, field by field;
  * run check_screen.js (the acceptance test of the screen).

    python3 mock_server.py                      # http://localhost:8787/site
    python3 mock_server.py --port 9000 --scenario empty
    python3 mock_server.py --html /path/to/another_site_health.html

Roles (what the real server injects):  /site  owner ·  /site?role=vendor  read-only
  /site?role=noalerts  read-only without alerts ·  /status?k=demo-share-token  share link
Scenarios: incident (default) · ok · empty (fresh install, no data) · error (data source down).
Switch while running:  GET /__scenario?name=empty

This file is a test double. Nothing in it is a design for the real backend.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Jerusalem")          # the site's local time zone: every *_il string and every bucket uses it
SITE = "https://example.co.il"
SHARE_TOKEN = "demo-share-token"
PROBE = [("בית", "/"), ("קטגוריה", "/product-category/sofas/"), ("מוצר", "/product/sample-sofa/"), ("סל", "/cart/")]
CORE = PROBE + [("קופה", "/checkout/")]
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}
STATE = {"scenario": "incident", "acked": set(), "html": os.path.join(HERE, "site_health.html")}


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
    return STATE["scenario"] == "incident" and rnd("bad", b.strftime("%Y-%m-%d %H")) < 0.06


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))] if vals else None


def lcp_for(page, when, strategy):
    base = {"בית": 2300, "קטגוריה": 3300, "מוצר": 2800, "סל": 2100, "קופה": 2500}.get(page, 3000)
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

def alerts():
    if STATE["scenario"] in ("ok", "empty", "error"):
        return []
    n = now()
    rows = [
        dict(id=41, kind="down", title="האתר לא עונה: סל", body="קוד 502\n%s/cart/" % SITE,
             opened=n - dt.timedelta(minutes=14), closed=None),
        dict(id=40, kind="slow", title="עמוד איטי: קטגוריה", body="4.6 שניות עד התוכן, פעמיים ברצף\n%s/product-category/sofas/" % SITE,
             opened=n - dt.timedelta(hours=2, minutes=5), closed=None),
        dict(id=39, kind="ops", title="רשימת הבוקר", body="3 הזמנות חסרות", opened=n - dt.timedelta(hours=5), closed=None),
        dict(id=38, kind="down", title="האתר לא עונה: בית", body="לא ענה בזמן\n%s/" % SITE,
             opened=n - dt.timedelta(hours=9, minutes=40), closed=n - dt.timedelta(hours=9, minutes=33)),
        dict(id=37, kind="cert", title="תעודת האבטחה פגה בעוד 13 ימים", body="example.co.il",
             opened=n - dt.timedelta(days=2, hours=3), closed=n - dt.timedelta(days=1, hours=20)),
        dict(id=36, kind="silent", title="המדידה נעצרה: מדידת מהירות — עמודי ליבה", body="אין מדידה כבר 95 דקות",
             opened=n - dt.timedelta(days=3, hours=1), closed=n - dt.timedelta(days=3)),
    ]
    for a in rows:
        end = a["closed"] or n
        a.update(open=a["closed"] is None, opened_il=il(a["opened"]), closed_il=il(a["closed"]) if a["closed"] else None,
                 minutes=int((end - a["opened"]).total_seconds() // 60), acked=a["id"] in STATE["acked"])
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
    if sc == "error":
        err = {"error": "HTTP Error 503: Service Unavailable"}
        out.update({k: err for k in ("availability", "availability_series", "speed", "speed_series", "alerts_open",
                                     "alerts_recent", "health", "product_issues")})
        out["cert"] = err
        return out
    if sc == "empty":
        out.update(availability=[], availability_series=[], speed=[], speed_series=[], alerts_open=[], alerts_recent=[],
                   product_issues=[], cert=None,
                   health=[dict(flow_group="אתר האינטרנט", flow_name=f, status="אין נתון", cadence=c, silent_txt=None,
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
    if sc == "incident" and hours >= 12:
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
                           checks=len(vals) * 4, crux_category=crux(int(med * 0.8)) if p != "קופה" else None,
                           crux_lcp=int(med * 0.8) if p != "קופה" else None))
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
    stat = {"מדידת מהירות — סבב כל האתר": ("מתעכב", 22, "מאחר ב-12 דקות"), "מהירות אצל לקוחות": ("שקט", 400, "שקט כבר 6 שעות")} if sc == "incident" else {}
    out["health"] = [dict(flow_group="אתר האינטרנט", flow_name=f, status=stat.get(f, ("תקין",))[0], cadence=c,
                          silent_txt=stat[f][2] if f in stat else None,
                          last_at=(n - dt.timedelta(minutes=stat[f][1] if f in stat else int(1 + w * 0.3))).isoformat(),
                          warn_minutes=w, late_minutes=l, note=None) for f, c, w, l in FLOWS]
    # --- broken products
    snap = n.strftime("%Y-%m-%d")
    out["product_issues"] = [] if sc == "ok" else [
        dict(issue="בלי מחיר", name="שולחן אוכל נפתח 160", url=SITE + "/product/table-160/", snap_date=snap),
        dict(issue="בלי תמונה", name="כורסת טלוויזיה אפורה", url=SITE + "/product/armchair-grey/", snap_date=snap),
        dict(issue="לא במלאי", name="ספה תלת מושבית בז'", url=SITE + "/product/sofa-3-beige/", snap_date=snap),
        dict(issue="לא במלאי", name="מיטה זוגית 160 עם ארגז", url=SITE + "/product/bed-160/", snap_date=snap),
        dict(issue="אי אפשר להוסיף לסל", name="שידת לילה אלון", url=SITE + "/product/nightstand-oak/", snap_date=snap),
    ]
    days = 23 if sc == "incident" else 71
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
    ("מהירות אצל לקוחות", "כל צפייה בעמוד", 120, 360),
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
        ok = not (sc == "incident" and p == "סל")
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

def api_drill(q, role):
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
    if STATE["scenario"] in ("empty", "error", "ok"):
        return {"rows": []}
    rows = []
    for a in alerts():
        rows.append(dict(kind="התראה", title=a["title"], msg=a["body"], at_il=il(a["opened"]), sent=True, _t=a["opened"]))
        if a["closed"]:
            rows.append(dict(kind="חזר לתקין", title=a["title"], msg="נמשך %d דקות" % a["minutes"], at_il=il(a["closed"]), sent=a["id"] != 37, _t=a["closed"]))
    n = now()
    rows.append(dict(kind="בוקר", title="בוקר טוב: האתר תקין", msg="זמינות 99.9% ב-24 שעות\nמהירות עמוד הבית: מהיר",
                     at_il=il(n.replace(hour=7, minute=30)), sent=True, _t=n.replace(hour=7, minute=30)))
    rows.sort(key=lambda r: r["_t"], reverse=True)
    return {"rows": [{k: v for k, v in r.items() if k != "_t"} for r in rows]}


# ---------------------------------------------------------------- http

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _role(self, q):
        """owner | vendor | noalerts | share. The real server derives it from the session cookie / share token."""
        if q.get("k"):
            return "share" if q["k"] == SHARE_TOKEN else None
        m = re.search(r"mock_role=(\w+)", self.headers.get("Cookie", ""))
        return m.group(1) if m else "owner"

    def _page(self, role, share_key=""):
        html = open(STATE["html"], encoding="utf-8").read()
        cfg = {"siteLabel": "example.co.il", "brand": "DEMO", "shareKey": share_key,
               "bucketNote": "עמוד הסל וקטגוריה תמיד איטיים יותר: הם לא נשמרים בזיכרון המטמון של האתר ונבנים מחדש בכל כניסה."}
        if role == "owner":
            cfg["links"] = [{"href": "#", "label": "מסך נוסף", "title": "דוגמה לכפתור נוסף"}]
            cfg["nav"] = [["g", "האתר"], ["a", "/site", "בריאות האתר"], ["a", "#", "מסך נוסף"]]
        r = {"owner": {}, "vendor": {"readonly": True}, "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}[role]
        inject = "<script>window.SH_CONFIG=%s;window.SH_ROLE=%s;</script>" % (json.dumps(cfg, ensure_ascii=False), json.dumps(r))
        if "<!--SH_INJECT-->" in html:
            html = html.replace("<!--SH_INJECT-->", inject, 1)
        else:   # a screen without the marker (for example the original it was derived from): old-style flags
            old = "<script>window.OWL_ROLE={};%s</script>" % ("window.OWL_SHARE=1;" if role != "owner" else "")
            html = html.replace("</head>", old + "</head>", 1)
        return html

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        path = u.path
        if path in ("/", "/site"):
            role = q.get("role", "owner")
            if role not in ("owner", "vendor", "noalerts"):
                role = "owner"
            return self._send(200, self._page(role), "text/html; charset=utf-8",
                              {"Set-Cookie": "mock_role=%s; Path=/; SameSite=Lax" % role, "Cache-Control": "no-cache, must-revalidate"})
        if path == "/status":
            if q.get("k") != SHARE_TOKEN:
                return self._send(403, "<div dir='rtl' style='font-family:system-ui;padding:48px;text-align:center'>הקישור אינו תקין או שפג.</div>", "text/html; charset=utf-8")
            return self._send(200, self._page("share", SHARE_TOKEN), "text/html; charset=utf-8")
        if path == "/__scenario":
            if q.get("name") in ("incident", "ok", "empty", "error"):
                STATE["scenario"] = q["name"]
                STATE["acked"] = set()
            return self._send(200, {"scenario": STATE["scenario"]})
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
            d = api_drill(q, role)
            return self._send(200, d) if d is not None else self._send(400, {"error": "what?"})
        if path == "/api/messages":
            if role != "owner":
                return self._send(403, {"error": "auth"})
            return self._send(200, api_messages(q))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path != "/api/alerts/ack":
            return self._send(404, {"error": "not found"})
        if self._role(q) != "owner":
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
    ap.add_argument("--scenario", default="incident", choices=["incident", "ok", "empty", "error"])
    ap.add_argument("--html", default=STATE["html"], help="the screen file to serve (default: site_health.html next to this script)")
    a = ap.parse_args()
    STATE["scenario"], STATE["html"] = a.scenario, a.html
    print("mock site-health backend: http://localhost:%d/site   (scenario: %s)" % (a.port, a.scenario), flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/check_screen.js sha256=80662c26880462f998b18b56a41ef2fd8d14d46a19c4b52e1aaa602e78ee20d7 -->
~~~~~~~~javascript
#!/usr/bin/env node
/* Acceptance test of the site-health screen (Playwright, headless Chromium).

     node check_screen.js                          # against the mock:  http://127.0.0.1:8787
     node check_screen.js http://127.0.0.1:8000    # against your real server (logged-in session needed, see --cookie)
     node check_screen.js <url> --cookie "name=value"   # session cookie for a real server
     node check_screen.js <url> --shots ./shots    # also save screenshots (phone + desktop)
     node check_screen.js <url> --basic            # only the checks that hold for any data

   Against the mock it also switches scenarios (incident / ok / empty / error) and roles.
   Exit code 0 = every check passed. Each line is one check: "ok" or "FAIL". */
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i < 0 ? null : (args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true); };
const BASE = (args[0] && !args[0].startsWith('--') ? args[0] : 'http://127.0.0.1:8787').replace(/\/$/, '');
const SHOTS = flag('--shots'), COOKIE = flag('--cookie'), BASIC = !!flag('--basic');
const PAGE_PATH = flag('--path') || '/site';

let failed = 0, passed = 0;
function check(name, cond, extra) { if (cond) { passed++; console.log('ok    ' + name); } else { failed++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); } }

async function open(browser, path, vp, opts = {}) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, locale: 'he-IL', colorScheme: opts.dark ? 'dark' : 'light' });
  if (COOKIE && typeof COOKIE === 'string') {
    const [n, ...v] = COOKIE.split('='); const u = new URL(BASE);
    await ctx.addCookies([{ name: n, value: v.join('='), domain: u.hostname, path: '/' }]);
  }
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
  const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  if (resp && resp.status() === 200 && !opts.noWait) {
    await page.waitForFunction(() => !document.body.classList.contains('loading') && document.querySelectorAll('#verdict .vbox').length === 4, null, { timeout: 20000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelectorAll('#now .nbox').length >= 1 && !/טוען/.test(document.getElementById('now').textContent), null, { timeout: 20000 }).catch(() => {});
  }
  return { ctx, page, errors, status: resp ? resp.status() : 0 };
}
const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
const txt = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent : null; }, sel);
const count = (page, sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel);
const visible = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }, sel);
async function scenario(name) { const r = await fetch(BASE + '/__scenario?name=' + name).catch(() => null); return !!(r && r.ok); }

(async () => {
  const browser = await chromium.launch();
  const isMock = !BASIC && await scenario('incident');
  const PHONE = { width: 390, height: 844 }, DESK = { width: 1280, height: 900 };

  /* ---------- 1. structure, on a phone ---------- */
  let s = await open(browser, PAGE_PATH, PHONE);
  let p = s.page;
  check('page loads (200)', s.status === 200, 'status ' + s.status);
  check('no horizontal scroll at 390px', await noOverflow(p));
  check('html is rtl + hebrew', await p.evaluate(() => document.documentElement.dir === 'rtl' && document.documentElement.lang === 'he'));
  check('"now" card shows 4 tiles', await count(p, '#now .nbox') === 4, String(await count(p, '#now .nbox')));
  check('bottom line shows 4 tiles', await count(p, '#verdict .vbox') === 4);
  const cards = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.wrap > section.card h2'), (h) => h.firstChild.textContent.trim()));
  const WANT = ['עכשיו', 'שורה תחתונה', 'זמינות', 'מהירות לאורך זמן', 'העמודים העיקריים', 'העמודים הכבדים באתר', 'מוצרים שבורים באתר', 'תעודת האבטחה (המנעול)', 'התראות', 'הודעות שנשלחו לטלפון', 'המדידה עצמה'];
  check('cards appear in the specified order', JSON.stringify(cards) === JSON.stringify(WANT), JSON.stringify(cards));
  check('subtitle shows the last check time and the period', /הבדיקה האחרונה .* · 24 השעות האחרונות/.test(await txt(p, '#sub')), await txt(p, '#sub'));
  check('alerts card and messages card start folded', await p.evaluate(() => document.getElementById('alertsList').parentElement.classList.contains('collapsed') && document.getElementById('msgList').parentElement.classList.contains('collapsed')));
  check('explanations hidden until asked', !(await visible(p, 'p.explain')));
  await p.click('#explbtn');
  check('"הסברים" shows the explanations', await visible(p, 'p.explain') && (await p.getAttribute('#explbtn', 'aria-pressed')) === 'true');
  await p.click('#explbtn');
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone.png', fullPage: true });

  /* ---------- 2. numbers match the data ---------- */
  const data = await p.evaluate(() => state.data);
  const per = (Array.isArray(data.availability) ? data.availability : []).filter((r) => r.section === 'לפי עמוד');
  const checksN = per.reduce((a, r) => a + (+r.checks || 0), 0), failN = per.reduce((a, r) => a + (+r.failed || 0), 0);
  if (checksN) {
    const up = 100 - 100 * failN / checksN, want = up.toFixed(up < 99.95 ? 2 : 1) + '%';
    check('uptime tile = 100 − failed/checks', (await txt(p, '#verdict .vbox[data-drill="fails"] .v')) === want, want + ' vs ' + await txt(p, '#verdict .vbox[data-drill="fails"] .v'));
    check('availability table: one row per probed page', await count(p, '#availTbl tbody tr') === per.length);
  } else check('no availability data → empty state text', /אין בדיקות זמינות בתקופה/.test(await txt(p, '#availTbl')));
  const core = (Array.isArray(data.speed) ? data.speed : []).filter((r) => r.section === 'ליבה' && r.strategy === 'mobile');
  check('core pages table: one row per core page (mobile)', core.length ? await count(p, '#coreTbl tbody tr') === core.length : /אין מדידות טלפון בתקופה/.test(await txt(p, '#coreTbl')));
  check('heavy pages table: at most 10 rows', await count(p, '#slowTbl tbody tr') <= 10);

  /* ---------- 3. drill-downs ---------- */
  await p.click('#verdict .vbox[data-drill="fails"]');
  await p.waitForFunction(() => document.getElementById('dov').classList.contains('on') && !/טוען…/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
  check('click on uptime opens the failures sheet', (await txt(p, '#dttl')) === 'כל הכשלים' && /הבדיקות שנכשלו/.test(await txt(p, '#dbody')), await txt(p, '#dttl'));
  check('sheet is a bottom sheet on a phone', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs(r.bottom - window.innerHeight) < 2 && r.width >= window.innerWidth - 2; }));
  await p.keyboard.press('Escape');
  check('Escape closes the sheet', !(await p.evaluate(() => document.getElementById('dov').classList.contains('on'))));
  if (core.length) {
    await p.click('#coreTbl tbody tr');
    await p.waitForFunction(() => /המדידות|אין מדידות תקינות/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
    check('click on a core page opens its measurements', /^מהירות: /.test(await txt(p, '#dttl')), await txt(p, '#dttl'));
    await p.click('#dx');
  }
  check('no JavaScript errors (phone)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();

  /* ---------- 4. desktop + dark ---------- */
  s = await open(browser, PAGE_PATH, DESK); p = s.page;
  check('no horizontal scroll at 1280px', await noOverflow(p));
  await p.click('#verdict .vbox[data-drill="outages"]');
  check('sheet is centered on desktop', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2 && r.width === 720; }));
  await p.click('#dx');
  await p.click('#segH button[data-h="168"]');
  await p.waitForFunction(() => state.data && state.data.hours === 168 && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"7 ימים" reloads with a 168-hour window', await p.evaluate(() => state.data.hours === 168) && /7 הימים האחרונים/.test(await txt(p, '#rangeTxt')));
  await p.click('#segS button[data-s="desktop"]');
  await p.waitForFunction(() => state.data && state.data.strategy === 'desktop' && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"מחשב" reloads with strategy=desktop', await p.evaluate(() => state.data.strategy === 'desktop'));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/desktop.png', fullPage: true });
  check('no JavaScript errors (desktop)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();
  s = await open(browser, PAGE_PATH, PHONE, { dark: true }); p = s.page;
  check('dark mode: page background is dark', await p.evaluate(() => { const m = getComputedStyle(document.body).backgroundColor.match(/\d+/g); return m && (+m[0] + +m[1] + +m[2]) < 150; }));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-dark.png', fullPage: true });
  await s.ctx.close();

  /* ---------- 5. mock only: alert bar, roles, scenarios ---------- */
  if (isMock) {
    await scenario('incident');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const openAlerts = (await p.evaluate(() => state.data.alerts_open)).filter((a) => !a.acked).length;
    check('alert bar shows the number of open alerts', new RegExp('⚠ ' + openAlerts + ' התראות פעילות').test(await txt(p, '#alertbar .acount')), await txt(p, '#alertbar .acount'));
    check('alert bar starts collapsed', await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed')));
    await p.click('#alertbar .ahead');
    check('each alert with a URL in its body has an "open the page" link', await count(p, '#alertbar .alink') >= 1);
    const posts = [];
    p.on('request', (r) => { if (r.method() === 'POST') posts.push(r.url() + ' ' + r.postData()); });
    await p.click('#alertbar .arow .ax');
    check('✕ removes the alert at once, without reloading the screen', await count(p, '#alertbar .arow') === openAlerts - 1 && !(await p.evaluate(() => document.body.classList.contains('loading'))));
    check('✕ posts {"ids":[id]} to /api/alerts/ack', posts.length === 1 && /\/api\/alerts\/ack \{"ids":\[\d+\]\}/.test(posts[0]), posts.join(','));
    check('the bar stays open after a delete', !(await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed'))));
    await p.click('#abAll'); await p.click('#abDel');
    check('"לסמן הכול" + "מחק מסומנות" clears the bar', !(await visible(p, '#alertbar')));
    await p.click('#refbtn');
    await p.waitForFunction(() => !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
    check('acknowledged alerts stay hidden after refresh', !(await visible(p, '#alertbar')));
    check('…but still count as open in the bottom line', (await txt(p, '#verdict .vbox[data-drill="alerts"] .v')) === String(openAlerts));
    await p.click('#msgCard .foldhead');
    check('message log lists what was sent to the phone', await count(p, '#msgList li') >= 3);
    check('no JavaScript errors (owner, incident)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    await scenario('incident');
    s = await open(browser, PAGE_PATH + '?role=vendor', PHONE); p = s.page;
    await p.click('#alertbar .ahead').catch(() => {});
    check('vendor: no delete controls on alerts', !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#alertbar .abulk')));
    check('vendor: no message log', !(await visible(p, '#msgCard')));
    check('vendor: sees only site alerts (no internal kinds)', await p.evaluate(() => state.data.alerts_open.every((a) => ['down', 'slow', 'silent', 'cert'].indexOf(a.kind) >= 0)));
    check('vendor: server refuses a delete', await p.evaluate(() => fetch('/api/alerts/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"ids":[41]}' }).then((r) => r.status)) === 403);
    check('vendor: server refuses the message log', await p.evaluate(() => fetch('/api/messages?h=24').then((r) => r.status)) === 403);
    check('no JavaScript errors (vendor)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    s = await open(browser, PAGE_PATH + '?role=noalerts', PHONE); p = s.page;
    check('no-alerts role: no bar, no alerts card, no open-alerts tile', !(await visible(p, '#alertbar')) && !(await visible(p, '#alertsCard')) && !(await visible(p, '#verdict .vbox[data-drill="alerts"]')));
    await s.ctx.close();

    s = await open(browser, '/status?k=demo-share-token', PHONE); p = s.page;
    check('share link: screen loads with data', s.status === 200 && await count(p, '#verdict .vbox') === 4);
    check('share link: no logout link, no delete controls, no message log', !(await visible(p, '#outLink')) && !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#msgCard')));
    check('no JavaScript errors (share link)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
    s = await open(browser, '/status?k=wrong', PHONE, { noWait: true });
    check('share link with a wrong token is refused (403)', s.status === 403);
    await s.ctx.close();
    const r401 = await fetch(BASE + '/api/site?k=wrong');
    check('data call with a wrong token is refused (401)', r401.status === 401);

    await scenario('empty');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const body = await txt(p, '.wrap');
    check('fresh install: every card shows its empty state, nothing breaks',
      /אין בדיקות זמינות בתקופה/.test(body) && /מדידת המהירות עדיין לא התחילה/.test(body) && /הסבב על כל האתר עדיין לא התחיל/.test(body)
      && /עדיין לא נבדק/.test(body) && /אין התראות בתקופה/.test(body) && /אין בדיקה ב־15 הדקות האחרונות/.test(body) && s.errors.length === 0, s.errors.join(' | '));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-empty.png', fullPage: true });
    await s.ctx.close();

    await scenario('error');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('data source down: the screen still renders, no JavaScript errors', await count(p, '#verdict .vbox') === 4 && s.errors.length === 0, s.errors.join(' | '));
    check('data source down: "now" says it could not load', /לא הצלחתי לטעון את "עכשיו"/.test(await txt(p, '#nowtick')), await txt(p, '#nowtick'));
    await s.ctx.close();

    await scenario('ok');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('all good: no alert bar, site "פעיל"', !(await visible(p, '#alertbar')) && /פעיל/.test(await txt(p, '#now .nbox .v')));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-ok.png', fullPage: true });
    await s.ctx.close();
    await scenario('incident');
  }

  await browser.close();
  console.log('\n' + passed + ' passed, ' + failed + ' failed' + (isMock ? '' : '  (basic checks only — scenario and role checks need the mock)'));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('test crashed: ' + e.stack); process.exit(2); });
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/reference/rum/site-health-rum.js sha256=849b4963aa37e7cac5923081f4cc8b08e0cba491d1bdd2392b07a6ab5663da4c -->
~~~~~~~~javascript
/* Site Health — real-user speed. One anonymous beacon per page view: how long until the main
   content was painted (LCP). No cookies, no identifiers, no query strings.

   Configure before this script runs:
     window.SiteHealthRum = { endpoint: 'https://<dashboard>/rum', liveHost: 'example.co.il' };

   `site` is sent as the literal "live" on the production host (with or without www) and as the
   host name anywhere else, so measurements from a staging copy are visible as such.
   Add ?sh_test=1 to a page address to send a measurement flagged as a test. */
(function () {
  var cfg = window.SiteHealthRum;
  if (!cfg || !cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
  var types = PerformanceObserver.supportedEntryTypes || [];
  if (types.indexOf('largest-contentful-paint') < 0) return;        // browser cannot measure it: send nothing
  if (document.visibilityState !== 'visible') return;               // opened in a background tab: the number would be meaningless

  var lcp = 0, hiddenAt = Infinity, sent = false;
  var po = new PerformanceObserver(function (list) {
    var all = list.getEntries(), e = all[all.length - 1];
    if (e && e.startTime < hiddenAt) lcp = e.startTime;             // only paints that happened while the page was visible
  });
  try { po.observe({ type: 'largest-contentful-paint', buffered: true }); } catch (err) { return; }

  function send() {
    if (sent) return;
    var rest = po.takeRecords();
    if (rest.length && rest[rest.length - 1].startTime < hiddenAt) lcp = rest[rest.length - 1].startTime;
    if (!lcp) return;
    sent = true;
    po.disconnect();
    var host = location.hostname.replace(/^www\./, '');
    var live = String(cfg.liveHost || '').replace(/^www\./, '');
    navigator.sendBeacon(cfg.endpoint, JSON.stringify({
      site: host === live ? 'live' : location.hostname,
      path: location.pathname,
      lcp: Math.round(lcp),
      test: /[?&]sh_test=1(&|$)/.test(location.search)
    }));                                                             // a string body is sent as text/plain: no CORS preflight
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') { hiddenAt = Math.min(hiddenAt, performance.now()); send(); }
  }, true);
  window.addEventListener('pagehide', send, true);
})();
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site_health_kit/reference/rum/site-health-rum.php sha256=b4812f8acc5ee1c917ca57dbf81e7980ed9bf3a1d707dba05186f28424f8637a -->
~~~~~~~~php
<?php
/**
 * Plugin Name: Site Health RUM
 * Description: Sends one anonymous speed measurement per page view (time to main content) to the site-health dashboard. No cookies, no personal data.
 * Version: 1.0.0
 *
 * Install: set the two constants below, upload this file together with site-health-rum.js
 * to wp-content/plugins/site-health-rum/ and activate it (or drop both into wp-content/mu-plugins/).
 */
if (!defined('ABSPATH')) { exit; }

if (!defined('SITE_HEALTH_RUM_ENDPOINT')) { define('SITE_HEALTH_RUM_ENDPOINT', 'https://CHANGE-ME.example.com/rum'); }   // the dashboard's /rum address
if (!defined('SITE_HEALTH_RUM_LIVE_HOST')) { define('SITE_HEALTH_RUM_LIVE_HOST', 'example.co.il'); }                      // the production host, without www

add_action('wp_enqueue_scripts', function () {
    if (strpos(SITE_HEALTH_RUM_ENDPOINT, 'CHANGE-ME') !== false) { return; }          // not configured yet
    if (is_user_logged_in() && current_user_can('edit_posts')) { return; }            // staff browsing the site are not visitors
    if (function_exists('is_checkout') && (is_checkout() || is_account_page())) { return; }   // never on checkout / account pages
    wp_enqueue_script('site-health-rum', plugins_url('site-health-rum.js', __FILE__), array(), '1.0.0',
        array('in_footer' => true, 'strategy' => 'defer'));
    wp_add_inline_script('site-health-rum', 'window.SiteHealthRum=' . wp_json_encode(array(
        'endpoint' => SITE_HEALTH_RUM_ENDPOINT,
        'liveHost' => SITE_HEALTH_RUM_LIVE_HOST,
    )) . ';', 'before');
});
~~~~~~~~
<!-- END FILE -->
