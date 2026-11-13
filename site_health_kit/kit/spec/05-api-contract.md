# Site Health kit — spec: the JSON the screen reads (§5, binding)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 5. API contract (binding)

The screen calls five data endpoints (§5.2–§5.6). Field names, types and the literal Hebrew
values below are what `site_health.html` reads; `mock_server.py` returns exactly these shapes.
Your server must return the same.

Conventions:

- All `*_il` fields and `at` strings are **preformatted in the site's local time zone** by the
  backend, as `DD.MM HH:MM` (24-hour). The screen prints them unchanged.
- The ISO 8601 fields (`from`, `to`, `last_at`, `not_after`, `checked_at`) must carry a UTC offset
  (`+02:00` or `Z`). The screen shows them in the **viewer's** local time, so a viewer in another
  country reads these few times on his own clock and the `*_il` times on the site's clock.
- `bucket` is a local-time string: `YYYY-MM-DD HH:00` for hourly buckets, `YYYY-MM-DD` for daily
  buckets. Rule: a window of at most 72 whole hours (`to − from < 73 hours`, which covers the extra
  minute of §5.1) uses hourly buckets, a longer one daily buckets. The screen tells them apart by
  length (`> 10` = hourly) and reads characters 5–7 (month), 8–10 (day), 11–16 (time).
- Durations are integers in **milliseconds** unless stated. `null` means "no value" and is
  tolerated wherever a field is marked nullable below; the screen prints `—`. Never null: `checks`,
  `failed`, `minutes`, `outage_minutes`, `warn_minutes`, `late_minutes` (the screen would print
  the word "null").
- Rows are displayed in the order the server sends them. Sort on the server as stated per list.
- Counts, ids, durations and scores are JSON **numbers**; so are the HTTP `status` of a page or of
  a push, `cls` / `cls_med` and `days_left`. The screen escapes every text field but writes
  numeric fields into the page as they are, so a numeric field must never carry text that came
  from outside (a visitor's beacon, a page of the site).
- Every `url` is an absolute `http://` or `https://` address. The screen makes a link only of
  such an address; anything else is shown as plain text.
- The Hebrew literals marked *(literal)* are compared by the screen character for character.

### 5.1 The time window (shared by all calls)

Query parameters: either `h=<hours>` (integer; the screen sends 24, 168, 720 or 2160) or
`f=<YYYY-MM-DD>&t=<YYYY-MM-DD>` (local dates, `t` inclusive: the window ends at the end of day `t`).
Rules (`window()` in `reference/server.py`):

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
    { "bucket": "2026-11-13 09:00", "checks": 240, "failed": 1,
      "ms_p50": 310, "ms_p95": 900 }    // null when no check of the bucket answered
  ],

  "speed": [
    // exactly one "bottom line" row: the home page on a phone, whatever `strategy` is
    { "section": "שורה תחתונה",          // (literal)
      "page": "בית", "url": "https://example.co.il/", "lcp_p50": 2310, "checks": 96,
      "verdict": "מהיר" },              // מצוין | מהיר | בינוני | איטי, by the LCP thresholds of §3; null without runs
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
      "minutes": 7 }                    // so far (open) or total (closed): nearest minute, at least 1
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
of the answer is still returned with status 200. The text is the database's own message for a
database error and only the error's type name for anything else (§8.2). **A part that did not arrive is never shown as
"nothing":** every tile and card that depends on it says `הנתון לא זמין כרגע` (the product card:
`הבדיקה לא זמינה.`) instead of 0, "אין התראות" or "עדיין לא נבדק", and the red bar stays as it
was. An empty list (`[]`) and `"cert": null` are the real "nothing" and get the empty-state texts.
Error texts must not contain host names, user names or keys.

Issue labels of the reference collectors: `בלי מחיר`, `בלי תמונה`, `לא במלאי`, `אי אפשר להוסיף לסל`.
A collector may use other labels; the screen escapes them like any text.

### 5.3 `GET /api/site/now` → the "עכשיו" card (refreshed every 60 s)

```jsonc
{
  "pages":  [ { "page": "בית", "url": "https://example.co.il/", "ok": true, "status": 200, "ms": 240 } ],
            // the last FULL round, one row per probe page; ms is null when the page did not answer.
            // Empty when there was no full round in the last 15 minutes.
  "latest": [ { "page": "בית", "ok": true } ],   // the most recent round of any kind (full or light); at least page + ok.
                           // Also empty when that round is older than 15 minutes: stale data must not read "פעיל"
  "light": false,          // true when `latest` is a light round
  "all_ok": true,          // every page of `latest` answered (false when `latest` is empty)
  "any_ok": true,          // at least one page of `latest` answered
  "age_sec": 12,           // integer seconds since `latest`; null when older than 15 minutes
  "rum":   { "n": 143, "p75_ms": 3120 },          // real-user LCP, last hour, live site only, test rows excluded; n = 0 → "no data"
  "speed": { "lcp_ms": 2500, "score": 63, "checked_at": "<ISO 8601>" },   // latest successful lab run, home page, phone; {} if none
  "alerts_open": 3,        // count of open alerts, seen ones included (after role filtering)
  "rum_src": { "n": 1000,                           // the last 1000 real-user rows: where they came from
               "hosts": [ { "host": "live", "n": 964 }, { "host": "staging.example.co.il", "n": 36 } ],   // largest first, at most 5
               "cols": ["created_at", "is_test", "lcp_ms", "path", "site"],   // diagnostic only
               "test": 12 }                         // how many of them are flagged as test. null when unavailable
}
```

On failure: status 502 with `{"error": "<text>"}`; the screen writes "לא הצלחתי לטעון את "עכשיו""
and replaces the tiles with one grey tile `הנתון לא זמין כרגע` (a "פעיל" of a minute ago does not stay).
For a vendor or a share link `alerts_open` is recounted from the filtered list of open alerts
(§8.2); if that second read fails the answer is 502, never a false 0.

### 5.4 `GET /api/site/drill?what=…&(h | f,t)` → drill-downs; always `{"rows": [...]}`

| `what` | extra parameters | each row |
|---|---|---|
| `fails` | `page` (optional), `bucket` (optional) | `{ "at_il": "13.11 09:41", "page": "סל", "kind": "קוד 502", "err": "<technical text or null>", "ms": 812 }` — the failed checks of full rounds (the same checks the availability numbers count), newest first, **at most 500**. `kind` is a short Hebrew reason: `לא ענה בזמן`, `קוד <status>`, `שגיאת חיבור`, `תוכן לא צפוי`. `ms` = time until the failure, or null. |
| `bucket` | `bucket` (required) | `{ "page": "בית", "checks": 60, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "13.11 09:17" }` — one row per probe page for that hour/day. |
| `runs` | `url` (required), `strategy`, `bucket` (optional) | `{ "ok": true, "err": null, "at_il": "13.11 10:45", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410, "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": [ { "id": "render-blocking-resources", "title": "…", "ms": 600 } ] }` — the individual lab runs of one page (every run of that URL and strategy in the window), **newest first**; a failed run is `{ok: false, err, at_il}`. `opps` = what slows the page, with the estimated saving in ms; it is filled only on the newest 100 successful runs and is `[]` on older ones (it is nine tenths of a run's size, and the sheet's "what slows the page" should describe the page as it is now). |
| `alert` | `id` (required) | one row: the `alerts_recent` fields plus `"fails": [ { "at": "13.11 11:02", "page": "סל", "status": 502, "err": null } ]` (the failed checks behind a `down` alert, oldest first, at most 500; `status` is present only when the failure was an HTTP status, because the sheet prints "קוד <status>" whenever it is there; otherwise `err` carries the reason) and `"sent": [ { "event": "open", "status": 200, "at": "13.11 11:02" } ]` (pushes with a final result; `event` is `open` or `close`; `status` 200 = accepted by the push service). |

The screen sends `page` and `bucket` on every `fails` call and `bucket` on every `runs` call,
also when it has nothing to say: `what=fails&page=&bucket=&h=24`. **An empty value means the
parameter is absent** (all pages, the whole window), not a malformed one.

Unknown `what`: status 400 `{"error": "what?"}`. A missing or malformed parameter (`id` not a
number of at most 18 digits, `url` empty, a required `bucket` missing or empty, a non-empty
`bucket` that is not in one of the two bucket formats or names no real day or hour, such as
`2026-13-45` or `2026-11-12 24:00`, a `page` or `url` that holds a control character, U+0000 to
U+001F or U+007F, or is not valid UTF-8): `{"rows": []}`, without touching the database. `alert`
ignores `bucket`.
Backend failure: status 502 `{"error": "<text>"}`; the sheet then says "לא הצלחתי לטעון".

### 5.5 `GET /api/messages?(h | f,t)` → the push log; `{"rows": [...]}`, newest first

`{ "kind": "התראה", "title": "…", "msg": "…", "at_il": "13.11 11:02", "sent": true }` — `kind` is
`התראה` (shown red), `חזר לתקין` (green) or any other label such as `בוקר` (grey). `sent: false`
adds "לא נשלחה". A recovery row reads, for example, title `חזר לתקין: סל` and the two-line msg
`האתר לא עונה: סל\nנמשך 7 דקות` (the alert's title, then how long it lasted; §7.8).
Backend failure: status 502 `{"error": "<text>"}`; the card then says "לא הצלחתי לטעון את ההודעות",
never "לא נשלחו הודעות בתקופה".

### 5.6 `POST /api/alerts/ack` → "ראיתי"

Body `{"ids": [41, 40]}` or `{"id": 41}`, sent with `Content-Type: application/json` (the screen
does; any other type answers 400, §8.2). Ids may arrive as numbers or as digit strings; only the
first 200 are processed, and a number above 2^63 − 1 is ignored like any unusable id. Marks each open, not yet seen alert as seen by the current user (the
user's label is stored). Answer `{"ok": true, "n": <alerts actually marked>}`; a body without a
usable id → 400 `{"error": "bad request"}`.
The screen removes the rows at once and only reloads if the call fails.

### 5.7 Errors and caching

- Not logged in (and no valid share token): **401** `{"error": "auth"}` on every data call. The
  screen then goes to `loginPath` (or shows a message in share mode).
- Role not allowed: **403** `{"error": "auth"}`.
- A share-link call (`k=`) from an address that is blocked after too many wrong tokens or
  passwords (§8.2): **429** `{"error": "too many attempts"}`. An unforeseen failure of the server:
  **500** `{"error": "server error"}`. The screen treats both as a failed read.
- Any other answer of `/api/site` that is not 2xx, or a 2xx answer that is `{"error": …}`, is a
  failed read: the subtitle says "לא הצלחתי לטעון את הנתונים" and every card says
  `הנתון לא זמין כרגע`. The numbers of the previous load do not stay on the screen.
- Data answers: `Cache-Control: no-store`. The HTML page: `Cache-Control: no-cache, must-revalidate`.

<!-- EOF spec/05-api-contract.md -->
