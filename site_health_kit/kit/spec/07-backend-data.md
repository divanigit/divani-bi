# Site Health kit — spec: the backend: shape, tables, functions (§7.1–§7.4, reference design)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 7. The backend (reference design)

The production original keeps its measurements in Supabase (Postgres) and serves them through a
small Python server. The SQL of the original is not part of this kit. What follows is a reference
design that reproduces every contract of §5 and every promise of §3, and `reference/` implements
it and tests it. The default is to use `reference/` as it is, in a copy you adapt (`START-HERE.md`
section E); a project whose backend is on another stack runs that copy as its own small service
next to it. Rebuilding it on another stack is the exception: the reference's tests cannot test
such a port (§9). Whatever you choose:

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
  (`COLLECTORS=0` turns it off; `python collectors.py` runs it as a separate process). §7.11
  sketches running them inside the database platform instead; the reference holds no code for that.
- The server must run on an **always-on** instance. A plan that sleeps when idle stops the
  measuring.

### 7.2 Tables

All tables are private: on Supabase enable row level security on each (no policies) and revoke the
`anon` and `authenticated` roles from tables, identity sequences and functions; only the secret
(service) key reads them. Tables created by SQL do not get row level security on their own, and
every new function is executable by everybody by default: the revokes are not optional.

The grants are explicit as well, because a Supabase project does not always hand out table grants
by itself. `schema.sql` ends with `grant select, insert, update, delete on table <each sh_* table>
to service_role`, and `functions.sql` with `grant execute on function <each sh_* function> to
service_role` (both only where the role exists). The functions run with the caller's rights, so
without the table grant every call fails with `42501 permission denied`, even with the secret
key. On a plain Postgres the owner of the tables is the only role that gets in. `sh_deadman` and
its table (§7.10) are left out of the grants: only the database's own job uses them.

| Table | One row is | Key columns |
|---|---|---|
| `sh_settings` | one setting | `key`, `value` (json): `host` and the keys of the configuration file (§7.4), as `sh_setup` loaded them |
| `sh_pages` | a configured page | `name` (Hebrew), `url`, `is_probe`, `is_core`, `is_home`, `sort`, `expect` (optional text the page must contain) |
| `sh_probe` | one availability check | `round_at`, `kind` (`full`/`light`), `page`, `url`, `ok`, `status`, `ms`, `fail` (`timeout`/`http`/`connect`/`content`; required on a failed row, with a `status` when it is `http`), `err`; primary key (`round_at`, `kind`, `page`) |
| `sh_speed` | one lab speed run | `at`, `url`, `page` (null for rotation pages), `strategy`, `source` (`core`/`rotation`), `ok`, `err`, `score`, `lcp_ms`, `cls`, `ttfb_ms`, `bytes`, `crux_category`, `crux_lcp_ms`, `opps` (json, at most 6 entries), `lh_version`; primary key (`url`, `strategy`, `at`) |
| `sh_site_pages` | a page of the site, from the sitemap | `url`, `active`, `first_seen`, `last_seen`, `last_measured_at` |
| `sh_rum` | one real-user page view | `created_at`, `site`, `path`, `lcp_ms`, `is_test`: no IP, no cookie, no user agent, no query string (§7.7 lists what the ingest drops) |
| `sh_cert` | the certificate state | `host`, `issuer`, `not_before`, `not_after`, `days_left`, `ok`, `err`, `checked_at` (a failed check updates only `ok`, `err`, `checked_at`) |
| `sh_product_issues` | a broken product in a snapshot | `snap_date`, `product_id`, `issue`, `name`, `url` |
| `sh_alerts` | an alert | `id`, `key`, `kind`, `title`, `body`, `opened_at`, `closed_at`, `acked_at`, `acked_by`; **partial unique index on `key` where `closed_at is null`** (at most one open alert per key) |
| `sh_messages` | a push that was (or should be) sent | `id`, `at`, `alert_id`, `event` (`open`/`close`/`morning`), `kind` (Hebrew label), `title`, `msg` (title and text exactly as the phone shows them), `priority`, `click` (reserved, always null: the sender builds the tap address itself), `status` (final HTTP status of the push; null = still owed), `attempts`, `claimed_at` |
| `sh_flows` | a measurement flow | `flow_name`, `sort`, `cadence`, `warn_minutes`, `late_minutes`, `note`, `enabled` (set by `sh_setup` from the configuration's `off`, §7.4), `alerts` (whether its silence pushes an alert), `last_at` |
| `sh_jobs` | "this daily job is done for this day" | `job`, `day` |
| `sh_login_log` | a login attempt | `at`, `ip`, `ok`, `who`, `ua` |

Retention (a nightly cleanup), sized so that the whole database settles around 200 MB (a free
Supabase project holds 500 MB): full-round probes and core speed runs `keep_days` days (default
**100**, which covers the screen's longest preset of 90 days; four pages cost about 1 MB of
probes a day), rotation speed runs 45 days, light-round probes 7 days, real-user rows 30 days,
product snapshots 30 days, login log and job markers 400 days, alerts and messages forever.
A speed run is about 1 KB, nearly all of it `opps`. Windows longer than the retention simply
show what is left.

Real-user rows come on top of that estimate. Measured on PostgreSQL 16 (table and index
together): about 116 bytes a row with a 40-character path, 197 bytes with a path of 120 bytes
(the longest that is stored, §7.7), and 296 bytes in the worst case (a 100-character host name
in `site` as well). So 10,000 measured views a day are about 35 MB over the 30 days kept (about
59 MB with 120-byte paths). The ingest is open to the internet, so the database also protects
itself: `sh_rum_add` stores nothing while the last 24 hours already hold **30,000 rows**. The
nightly cleanup leaves up to 31 days, so a flood kept up for a month at that cap reaches about
275 MB of worst-case rows, about 475 MB with the rest of the database; at the server's own,
lower budget of 20,000 rows a day (§7.7), about 183 MB, about 385 MB in all. Both stay under the
500 MB of a free project.

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
  after the last dead one, or the end of the window (never later than now) when the run reaches
  it. Minutes in which the prober itself did not run add nothing and are not an outage; that is
  the `שקט` state of the flow.
- **Per page rows:** one row per page that has full-round checks in the window, in configuration
  order; a page that was removed from the configuration keeps its history and is listed last.
- **Buckets:** `to_char(round_at at time zone <tz>, …)` with the format of §5; hourly when
  `p_to − p_from < 73 hours`, daily otherwise. Percentiles per bucket over all pages together.
  The hour that happens twice when clocks go back is one bucket, in the chart and in the drill.
- **Speed, section `ליבה`:** per core page and strategy over successful runs with `source = 'core'`:
  medians of `lcp_ms`, `score`, `cls`, `ttfb_ms`; `lcp_p95`; `slow_runs` = runs with `lcp_ms > 4000`;
  `checks` = run count; `crux_*` from the newest run.
- **`שורה תחתונה`:** the `ליבה` figures of the home page with `strategy = 'mobile'`, plus `verdict`.
  When there is no successful run in the window the row is still returned with `lcp_p50: null`.
  (This is why `sh_setup` insists that the home page is a core page.)
- **`האיטיים באתר`:** over successful phone runs with `source = 'rotation'`, grouped by URL: top 10
  by median LCP. Core pages are not part of the rotation (they are measured every 15 minutes
  already), so they never appear here. **`כיסוי`:** `checks` = distinct active site pages with a
  successful rotation run in the window; `slow_runs` = active site pages in the rotation.
- **One spelling of an address.** A core page is recognised by its address, so both sides are
  stored in one spelling: `sh_setup` (the configured pages) and `sh_sitemap_set` (the site's
  pages) pass every address through `sh_url`: scheme and host in lower case, a bare host gets
  its `/`, and the rest is percent-encoded as UTF-8 with capital hex digits (`/צור-קשר/` and
  `/%d7%a6…/` both become `/%D7%A6…/`). The configuration may therefore spell a page as a person
  types it.
- **Health:** `אין נתון` when the flow never ran; otherwise by the age of `last_at`: up to
  `warn_minutes` → `תקין`, up to `late_minutes` → `מתעכב`, beyond → `שקט`. `last_at` is written
  **last and only when a run succeeded**, so a failing collector leaves no proof of life and
  surfaces as `מתעכב`/`שקט`. Disabled flows (the parts listed under `off`, §7.4) are not
  returned. `silent_txt`: `מאחר ב-<span>` while late (the time beyond `warn_minutes`, a started
  minute counts), `שקט כבר <span>` when silent (the whole age in whole minutes).
  Thresholds (warn / late minutes): probe 5 / 15; core speed 45 / 90; rotation 20 / 60; sitemap,
  certificate, catalogue 1,560 / 2,880; real users 360 / 1,440.
- **A span** (`sh_span`, the one helper behind every text that names a length of time): the
  minutes rounded to the nearest, never less than one; told in minutes under two hours, in whole
  hours under two days, in whole days from there on; one and two have their own words: `דקה`,
  `שתי דקות`, `5 דקות`, `שעה` (exactly 60 minutes), `שעתיים`, `5 שעות`, `יום` (exactly 24
  hours), `יומיים`, `5 ימים`. After `מאחר ב` a number takes a hyphen (`מאחר ב-10 דקות`) and a
  word does not (`מאחר בדקה`, `מאחר בשעתיים`).
- **How long an alert lasted** (`minutes` in `alerts_recent` and in the alert drill, and the
  recovery text): from `opened_at` to `closed_at` (or to now), rounded to the **nearest**
  minute and never 0. Alerts open and close a few milliseconds after the minute, so rounding
  down would call three rounds "2 minutes".
- **`sh_now`:** `pages` = the newest full round if it is at most 15 minutes old; `latest` = the
  newest round of either kind, under the same 15-minute rule; `rum` over the last 60 minutes
  where `site` is a live value and `is_test` is false, `p75_ms` = `percentile_cont(0.75)` rounded
  (null with `n` = 0 when there are no rows; never 0, which would paint green; with `real_users`
  off the screen draws no tile for it: `nowRum`, §7.4); `rum_src` over the
  newest 1000 rows (null when there are none), its `hosts` holding the **5 largest** sources
  only, largest first (`n` and `test` still count all the rows); `speed` = the newest successful
  phone run of the home page.

### 7.4 Functions the collectors call (write side)

| Function | What it does | Returns |
|---|---|---|
| `sh_config()` | the configuration as one object: every key of the file as it was loaded (table below), plus `host`, `off` as it took effect, `pages` (`[{name, url, probe, core, home, expect}]` in display order) and `screen` (the object the server injects as `SH_CONFIG`, §4.1) | the object (example below). Before `sh_setup` ran it has no `site`, `host` or `time_zone`, only `keep_days`, `rum_hosts`, `private_paths`, `extra_hosts`, `off`, `hide`, `nav`, `links` at their defaults, `pages: []` and `screen: {hide: [], probeCount: 0, coreCount: 0}`; the server then answers 502 "the site is not configured" |
| `sh_setup(p_config)` | loads `site_health.config.json` (idempotent; a file that is refused changes nothing). Validates what the table below states. Replaces the page list (history stays), seeds the seven flows and decides again which of them are enabled | `sh_config()` |
| `sh_probe_add(p_round_at, p_kind, p_rows)` | stores one probe round; rows `{page, url, ok, status, ms, fail, err}`; a round that was already stored is ignored; beats `בודק זמינות האתר` on a full round | `{"n": rows stored}` |
| `sh_speed_add(p_rows)` | stores lab runs; rows `{at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms, bytes, crux_category, crux_lcp_ms, opps, lh_version}`; the same (`url`, `strategy`, `at`) twice is stored once; beats the core or rotation flow when at least one run succeeded | `{"n"}` |
| `sh_rotation_next(p_n)` | claims the `p_n` active site pages measured longest ago (never a core page; none while `sitemap` is switched off) | `["url", …]` |
| `sh_sitemap_set(p_urls)` | replaces the list of site pages (new ones added, missing ones deactivated), each address in the spelling of `sh_url` (§7.3); raises on an empty list; beats the sitemap flow | `{"n"}` |
| `sh_cert_set(p_row)` | stores `{host, issuer, not_before, not_after, days_left, ok, err, checked_at}`; beats the flow only when `ok` | `{"n": 1}` |
| `sh_issues_set(p_snap_date, p_rows)` | stores the day's broken products `{product_id, issue, name, url}`, replacing that day (an empty list is a valid, good snapshot); beats the flow | `{"n"}` |
| `sh_rum_add(p_rows)` | stores real-user rows `{site, path, lcp_ms, is_test}`; drops rows outside the limits of §7.7 again, as the last line of defence: cuts `path` at 120 characters exactly as the server does, then drops a row whose path is still longer than 120 bytes; stores nothing while the last 24 hours hold 30,000 rows (§7.2); beats the flow only when a row was stored | `{"n"}` |
| `sh_job_due(p_job, p_day)` / `sh_job_mark(p_job, p_day)` | daily jobs: "is this day's run still owed?" / "done" | `true`/`false`; `true` when this call set the marker |
| `sh_alerts_check()` | evaluates the alert rules (§7.8), opens and closes alerts, queues messages, and **claims** the messages that are owed. Alerts of any other `kind` are never touched | `[{id, title, msg, priority, click, kind, event}]`, oldest first. `title` and `msg` are the push as the phone shows it, the sender adds nothing; `click` is always null |
| `sh_message_sent(p_id, p_status)` | records the result of one push attempt (§7.9) | `{"n": 0 or 1}` |
| `sh_morning(p_day)` | queues the morning message for that day, once. It does not look at the clock: the caller calls it when the configured `morning` time has passed. On a new installation it queues nothing until the oldest stored probe round is 6 hours old, and the day still counts as done | `{"n": 1}`; `{"n": 0}` when the day was already done; `{"n": 0, "skipped": "the oldest probe round is less than 6 hours old"}` |
| `sh_cleanup()` | applies the retention rules; the newest marker of each job and the latest product snapshot are never deleted | `{probe, probe_light, speed, rum, product_issues, jobs, login_log}`: rows deleted |

"Beats the flow" means: sets the flow's `last_at`, its proof of life (§7.3, Health).

`sh_alerts_check` must be safe when two workers overlap for a minute during a deploy: no alert
and no message is created twice, and a message returned to one caller is not returned to another
for the next two minutes (the claim). It assumes the default `READ COMMITTED` isolation.

**The configuration file, `site_health.config.json`.** This table is the one reference for its
keys; `reference/site_health.config.example.json` holds every one of them. `sh_setup` refuses a
file that breaks a rule of the table, with a message that names the key.

| Key | Type | Default | What it does |
|---|---|---|---|
| `site` | text | required | The site's address, `http(s)://host` (a trailing `/` is dropped). Its host is "this site" for the certificate check, the sitemap and the real-user ingest. An `http://` address switches the certificate check off |
| `time_zone` | text | required | An IANA name such as `Asia/Jerusalem`: the zone of the site's customers. Every time the screen prints, every bucket, every day boundary and every daily job follows it. There is no default: ask the owner, or take the site's country and say so |
| `pages` | list | required | `[{name, url, home, probe, core, expect}]` in display order. `name`: the Hebrew label, unique. `url`: absolute http(s), stored in the spelling of `sh_url`. `probe: true`: checked every minute (at least one page). `core: true`: lab speed every 15 minutes. `home: true`: exactly one page, and it must be a probe page and a core page. `expect`: optional text the page must contain |
| `label` | text | the host without `www.` | Screen `siteLabel` |
| `brand` | text | `""` | Screen `brand` |
| `platform` | `woocommerce`, `shopify` or `other` | `other` | Which public catalogue the broken-products check reads, and the default `path_labels`. `other` switches that check off |
| `down_after` | whole number, 1 or more | `1` | Failed rounds in a row before `האתר לא עונה` opens (§7.8). Screen `downAfter`, for the sentences that explain the rule |
| `morning` | `HH:MM` | `07:30` | Local time from which the morning message goes out |
| `keep_days` | whole number, 30 to 400 | `100` | Days that full-round probes and core speed runs are kept (§7.2) |
| `off` | list out of `sitemap`, `real_users`, `catalogue`, `cert` | `[]` | The parts of the measuring that do not apply to this site (next table) |
| `hide` | list of card ids | `[]` | Cards of the screen to hide, on top of those that `off` hides |
| `nav`, `links` | lists | `[]` | Passed to the screen as they are (§4.1), for owner and staff only: an outsider's page gets neither (§8.2) |
| `extra_hosts` | list of host names, lower case | `[]` | Other hosts a probed page may redirect to (§7.5) |
| `rum_hosts` | list of host names, lower case | `[]` | Other hosts whose real-user beacons are accepted, for example a staging copy (§7.7) |
| `private_paths` | list of single path segments | `[]` | The site's own names for private pages (a translated cart, checkout or account slug), on top of the built-in ones: the ingest and the sitemap loader skip such pages (§7.7) |
| `live_hosts` | list | `["live"]` | The values of a beacon's `site` that count as the live site in `sh_now().rum`. Screen `liveHosts` |
| `path_labels` | list of `[prefix, label]` | by `platform`: WooCommerce and Shopify as in §4.1, `other` `[]` | Screen `pathLabels` |
| `bucket_note` | text | `""` | Screen `bucketNote` |

What `off` switches. Every `sh_setup` call decides again, from the file alone, which flows are
enabled: a flow that was switched by hand in `sh_flows` is put back, so the file is the only
switch. A flow that is switched off forgets its `last_at`, its open `silent` alert closes at the
next alert tick, and `sh_health` does not return it.

| `off` entry | Flows disabled | Card hidden | Also in effect when |
|---|---|---|---|
| `sitemap` | `טעינת מפת האתר`, `מדידת מהירות — סבב כל האתר` | `slowCard` | |
| `real_users` | `מהירות אצל לקוחות` | `nowRum` (the real-user tile of "עכשיו", §6.2) | |
| `catalogue` | `בדיקת מוצרים שבורים` | `issuesCard` | `platform` is `other` |
| `cert` | `בדיקת תעודת האבטחה` (and the `cert` alert rule) | `certCard` | `site` is `http://` |

`בודק זמינות האתר` and `מדידת מהירות — עמודי ליבה` cannot be switched off. The speed test needs
the Google key (`PAGESPEED_KEY`, §7.6): without it the core flow, and the rotation unless
`sitemap` is off, stay `אין נתון`, so the key is required for go-live (§10 item 2).

`sh_config()` after loading the example file (`pages` shortened):

```json
{ "site": "https://example.co.il", "host": "example.co.il", "label": "example.co.il", "brand": "",
  "time_zone": "Asia/Jerusalem", "platform": "woocommerce", "down_after": 1, "morning": "07:30",
  "keep_days": 100, "off": [], "hide": [], "nav": [], "links": [], "extra_hosts": [],
  "rum_hosts": [], "private_paths": [], "live_hosts": ["live"], "bucket_note": "",
  "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
  "pages": [{"name": "בית", "url": "https://example.co.il/", "probe": true, "core": true,
             "home": true, "expect": "ברוכים הבאים"}],
  "screen": {"siteLabel": "example.co.il", "brand": "", "homePage": "בית", "probeCount": 4,
             "coreCount": 5, "downAfter": 1, "liveHosts": ["live"], "bucketNote": "",
             "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
             "hide": [], "nav": [], "links": []} }
```

`off` is the list as it took effect: the file's entries plus the two that follow from the site,
always in the order `sitemap`, `real_users`, `catalogue`, `cert`. `hide`, `nav` and `links` at the
top are the file's own; `screen.hide` is the file's `hide` followed by the card of each part
that is off, each card once, in this order: `sitemap` → `slowCard`, `catalogue` → `issuesCard`,
`cert` → `certCard`, `real_users` → `nowRum`. So `"off": ["real_users"]` hides the real-user
tile of "עכשיו". A database that was set up before a key existed answers with that key's
default until `sh_setup` runs again (and leaves `nav` and `links` out of `screen`).

<!-- EOF spec/07-backend-data.md -->
