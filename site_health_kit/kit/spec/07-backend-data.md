# Site Health kit — spec: the backend: shape, tables, functions (§7.1–§7.4, reference design)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

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
`anon` and `authenticated` roles from tables and functions; only the secret (service) key reads
them. Tables created by SQL do not get row level security on their own, and every new function is
executable by everybody by default: the revokes are not optional.

| Table | One row is | Key columns |
|---|---|---|
| `sh_settings` | one setting | `key`, `value` (json): site, host, label, time zone, platform, `down_after`, morning time, `keep_days`, `rum_hosts`, `private_paths`, … |
| `sh_pages` | a configured page | `name` (Hebrew), `url`, `is_probe`, `is_core`, `is_home`, `sort`, `expect` (optional text the page must contain) |
| `sh_probe` | one availability check | `round_at`, `kind` (`full`/`light`), `page`, `url`, `ok`, `status`, `ms`, `fail` (`timeout`/`http`/`connect`/`content`; required on a failed row, with a `status` when it is `http`), `err`; primary key (`round_at`, `kind`, `page`) |
| `sh_speed` | one lab speed run | `at`, `url`, `page` (null for rotation pages), `strategy`, `source` (`core`/`rotation`), `ok`, `err`, `score`, `lcp_ms`, `cls`, `ttfb_ms`, `bytes`, `crux_category`, `crux_lcp_ms`, `opps` (json, at most 6 entries), `lh_version`; primary key (`url`, `strategy`, `at`) |
| `sh_site_pages` | a page of the site, from the sitemap | `url`, `active`, `first_seen`, `last_seen`, `last_measured_at` |
| `sh_rum` | one real-user page view | `created_at`, `site`, `path`, `lcp_ms`, `is_test` — nothing that identifies a person |
| `sh_cert` | the certificate state | `host`, `issuer`, `not_before`, `not_after`, `days_left`, `ok`, `err`, `checked_at` (a failed check updates only `ok`, `err`, `checked_at`) |
| `sh_product_issues` | a broken product in a snapshot | `snap_date`, `product_id`, `issue`, `name`, `url` |
| `sh_alerts` | an alert | `id`, `key`, `kind`, `title`, `body`, `opened_at`, `closed_at`, `acked_at`, `acked_by`; **partial unique index on `key` where `closed_at is null`** (at most one open alert per key) |
| `sh_messages` | a push that was (or should be) sent | `id`, `at`, `alert_id`, `event` (`open`/`close`/`morning`), `kind` (Hebrew label), `title`, `msg`, `priority`, `status` (final HTTP status of the push; null = still owed), `attempts`, `claimed_at` |
| `sh_flows` | a measurement flow | `flow_name`, `sort`, `cadence`, `warn_minutes`, `late_minutes`, `note`, `enabled`, `alerts` (whether its silence pushes an alert), `last_at` |
| `sh_jobs` | "this daily job is done for this day" | `job`, `day` |
| `sh_login_log` | a login attempt | `at`, `ip`, `ok`, `who`, `ua` |

Retention (a nightly cleanup), sized so that the whole database settles around 200 MB (a free
Supabase project holds 500 MB): full-round probes and core speed runs `keep_days` days (default
**100**, which covers the screen's longest preset of 90 days; four pages cost about 1 MB of
probes a day), rotation speed runs 45 days, light-round probes 7 days, real-user rows 30 days,
product snapshots 30 days, login log and job markers 400 days, alerts and messages forever.
A speed run is about 1 KB, nearly all of it `opps`. Windows longer than the retention simply
show what is left.

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
- **`האיטיים באתר`:** over successful phone runs with `source = 'rotation'`, grouped by URL: top 10
  by median LCP. Core pages are not part of the rotation (they are measured every 15 minutes
  already), so they never appear here. **`כיסוי`:** `checks` = distinct active site pages with a
  successful rotation run in the window; `slow_runs` = active site pages in the rotation.
- **Health:** `אין נתון` when the flow never ran; otherwise by the age of `last_at`: up to
  `warn_minutes` → `תקין`, up to `late_minutes` → `מתעכב`, beyond → `שקט`. `last_at` is written
  **last and only when a run succeeded**, so a failing collector leaves no proof of life and
  surfaces as `מתעכב`/`שקט`. Disabled flows (for example the catalogue check on a site that sells
  nothing) are not returned. `silent_txt`: `מאחר ב-<span>` while late (the time beyond
  `warn_minutes`), `שקט כבר <span>` when silent (the whole age), where span is `N דקות` under two
  hours, `N שעות` under two days, else `N ימים`.
  Thresholds (warn / late minutes): probe 5 / 15; core speed 45 / 90; rotation 20 / 60; sitemap,
  certificate, catalogue 1,560 / 2,880; real users 360 / 1,440.
- **`sh_now`:** `pages` = the newest full round if it is at most 15 minutes old; `latest` = the
  newest round of either kind, under the same 15-minute rule; `rum` over the last 60 minutes
  where `site` is a live value and `is_test` is false, `p75_ms` = `percentile_cont(0.75)` rounded
  (null with `n` = 0 when there are no rows; never 0, which would paint green); `rum_src` over the
  newest 1000 rows (null when there are none); `speed` = the newest successful phone run of the
  home page.

### 7.4 Functions the collectors call (write side)

| Function | What it does | Returns |
|---|---|---|
| `sh_config()` | the configuration as one object: every setting loaded by `sh_setup` (`site`, `host`, `label`, `time_zone`, `platform`, `down_after`, `morning`, `keep_days`, `rum_hosts`, `private_paths`, …), `pages` (`[{name, url, probe, core, home, expect}]` in display order) and `screen` (the object the server injects as `SH_CONFIG`, §4.1) | the object. Before `sh_setup` ran it has no `time_zone` (the other settings already carry their defaults); the server then answers 502 "the site is not configured" |
| `sh_setup(p_config)` | loads `site_health.config.json` (idempotent). Validates: exactly one home page and it is a probe page, at least one probe page, absolute http(s) URLs, unique names, a known time zone, a known platform. Replaces the page list (history stays) and seeds the seven flows | `sh_config()` |
| `sh_probe_add(p_round_at, p_kind, p_rows)` | stores one probe round; rows `{page, url, ok, status, ms, fail, err}`; a round that was already stored is ignored; beats `בודק זמינות האתר` on a full round | `{"n": rows stored}` |
| `sh_speed_add(p_rows)` | stores lab runs; rows `{at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms, bytes, crux_category, crux_lcp_ms, opps, lh_version}`; the same (`url`, `strategy`, `at`) twice is stored once; beats the core or rotation flow when at least one run succeeded | `{"n"}` |
| `sh_rotation_next(p_n)` | claims the `p_n` active site pages measured longest ago (never a core page) | `["url", …]` |
| `sh_sitemap_set(p_urls)` | replaces the list of site pages (new ones added, missing ones deactivated); raises on an empty list; beats the sitemap flow | `{"n"}` |
| `sh_cert_set(p_row)` | stores `{host, issuer, not_before, not_after, days_left, ok, err, checked_at}`; beats the flow only when `ok` | `{"n": 1}` |
| `sh_issues_set(p_snap_date, p_rows)` | stores the day's broken products `{product_id, issue, name, url}`, replacing that day (an empty list is a valid, good snapshot); beats the flow | `{"n"}` |
| `sh_rum_add(p_rows)` | stores real-user rows `{site, path, lcp_ms, is_test}`; drops rows outside the limits of §7.7 again, as the last line of defence | `{"n"}` |
| `sh_job_due(p_job, p_day)` / `sh_job_mark(p_job, p_day)` | daily jobs: "is this day's run still owed?" / "done" | `true`/`false`; `true` when this call set the marker |
| `sh_alerts_check()` | evaluates the alert rules (§7.8), opens and closes alerts, queues messages, and **claims** the messages that are owed | `[{id, title, msg, priority, kind, event}]`, oldest first |
| `sh_message_sent(p_id, p_status)` | records the result of one push attempt (§7.9) | `{"n": 0 or 1}` |
| `sh_morning(p_day)` | queues the morning message for that day, once. It does not look at the clock: the caller calls it when the configured `morning` time has passed | `{"n": 1 or 0}` |
| `sh_cleanup()` | applies the retention rules; the newest marker of each job and the latest product snapshot are never deleted | `{probe, probe_light, speed, rum, product_issues, jobs, login_log}`: rows deleted |

`sh_alerts_check` must be safe when two workers overlap for a minute during a deploy: no alert
and no message is created twice, and a message returned to one caller is not returned to another
for the next two minutes (the claim). It assumes the default `READ COMMITTED` isolation.

<!-- EOF spec/07-backend-data.md -->
