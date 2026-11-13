# Site Health: the reference backend

A working, tested implementation of spec §7 and §8: the database, the server, the collectors.
Use it as it is, adapt it, or read it as the worked example while building on another stack.
Section numbers (§) point into the files of `../spec/`.

## What each file is

| File | What it is |
|---|---|
| `schema.sql` | the tables, indexes and privileges. Apply it first. Safe to run again. |
| `functions.sql` | every `sh_*` SQL function: the only way the server and the collectors touch the database. Apply it second. Safe to run again. |
| `db.py` | `rpc(fn, params)`: one call of one `sh_*` function, over HTTPS (Supabase) or over a Postgres connection. |
| `server.py` | sign-in, roles, the screen and its data calls (§5, §8), the real-user ingest `POST /m`, `GET /health`. Starts the collectors unless `COLLECTORS=0`. |
| `collectors.py` | everything that measures (§7.5-§7.9): probe, lab speed, sitemap, catalogue, certificate, alert tick and pushes, morning message, cleanup, and the scheduler that runs them. `python3 collectors.py` runs it as a separate worker. |
| `manage.py` | a small command line for deploying: `init-db`, `setup`, `check`, `run-once`, `test-push`, `new-secret`. |
| `deadman.sql` | the independent "the measuring stopped" check for Supabase (§7.10, option 1). Optional. **Not executed by the tests.** |
| `rum/site-health-rum.js`, `rum/site-health-rum.php` | the real-user script and its one-file WordPress plugin (§7.7). |
| `site_health.config.example.json` | the site's configuration: copy, edit, load with `manage.py setup`. No secrets in it. |
| `requirements.txt` | the pinned packages. The collectors and `manage.py` need only the standard library, plus `psycopg` when `DATABASE_URL` is used. |
| `tests/conftest.py` | pytest fixtures: a scratch database with `schema.sql` and `functions.sql` applied. |
| `tests/sim.py` | fills a database with believable measurements through the write functions. |
| `tests/fake_site.py` | a local website that plays the monitored site, its sitemap, a WooCommerce and a Shopify catalogue, PageSpeed, ntfy and a heartbeat service. Used by the tests; also runs by hand. |
| `tests/fixtures/` | two small PageSpeed answers (Lighthouse 13.6.0 and 12.8.2): Lighthouse's own sample results, cut down to the keys the collector reads. |
| `tests/test_sql.py`, `tests/test_server.py`, `tests/test_collectors.py` | the tests of the three layers. |
| `tests/test_rum_snippet.js` | the test of the real-user script in a real browser (node + Playwright; not part of pytest). |

## Environment variables

Secrets live only here, in the host's environment settings. Nothing else is configured by
environment: everything about the site (pages, time zone, platform, alert rule) is in the database,
loaded once with `manage.py setup <config.json>`.

| Name | Read by | Required? | What it is |
|---|---|---|---|
| `SUPABASE_URL` + `SUPABASE_SECRET_KEY` | server, collectors, manage | one of the two database choices | the project address (`https://<ref>.supabase.co`) and its secret key (`sb_secret_…`). The database is then reached over HTTPS. If both choices are set, this one wins. |
| `DATABASE_URL` | server, collectors, manage | the other choice | a Postgres connection string. Needs `psycopg`. `manage.py init-db` works only with this one. |
| `SH_PASS_OWNER` | server | yes | the owner's password. Without it nobody can sign in. |
| `SH_PASS_STAFF` | server | no | a password for staff (sees everything). |
| `SH_PASS_VENDOR_<NAME>` | server | no | one password per outside vendor (read-only). `<NAME>` is the name in the login log. |
| `SH_VENDOR_NOALERTS` | server | no | vendor names, comma-separated, who must not see alerts at all. |
| `SH_SHARE_TOKEN` | server | no | the token of the share link `/status?k=<token>`. Empty: no share link. |
| `SH_PROXY_HOPS` | server | no (default `1`) | how many proxies of the host stand in front of the server; decides which `X-Forwarded-For` entry is the client (§8.2). `0`: no proxy. |
| `SH_SCREEN` | server | no | path of the screen file. Default: `../site_health.html`. |
| `COLLECTORS` | server | no (default on) | `0`: this server process measures nothing (the collectors run elsewhere). |
| `PAGESPEED_KEY` | collectors | no | Google PageSpeed Insights API key (§7.6). Without it the two speed collectors do not run and the speed cards stay empty. |
| `NTFY_TOPIC` | collectors | no | the ntfy topic alerts are pushed to (§7.9). Without it alerts still open and show on the screen; every message is logged as not sent. |
| `NTFY_URL` | collectors | no (default `https://ntfy.sh`) | the ntfy server. |
| `NTFY_TOKEN` | collectors | no | access token of a reserved topic or a self-hosted server; sent as `Authorization: Bearer …`. |
| `DASHBOARD_URL` | collectors | no, recommended | this dashboard's public address. It is named in the probe's `User-Agent` (so the site's firewall can allow it) and opened by a tap on a push (`<address>/site`). |
| `HEARTBEAT_URL` | collectors | no | a ping address of an outside heartbeat service; requested after every full probe round (§7.10, option 2). |
| `SH_TEST_ADMIN_URL` | tests | no | a Postgres where the tests may create and drop a scratch database. Default: `postgresql://postgres:shtest@127.0.0.1:5432/postgres`. |

`python3 manage.py new-secret` prints a fresh `NTFY_TOPIC` and a fresh `SH_SHARE_TOKEN`.
`python3 manage.py check` lists which of these variables are set: names only, never a value.
The collectors never log a key, a token, the topic or the heartbeat address.

**The session cookie** is called `sh_session` (HttpOnly; 365 days for owner and staff, 30 for
vendors). To get one for `check_screen.js`:

```bash
curl -si -d 'p=<the owner password>' http://127.0.0.1:8000/login | grep -i '^set-cookie'
node ../check_screen.js http://127.0.0.1:8000 --basic --cookie "sh_session=<value>"
```

## Local quick start

```bash
cd reference
pip install -r requirements.txt

# 1. a database of its own (any PostgreSQL 15+)
psql postgresql://postgres:<password>@127.0.0.1:5432/postgres -c 'create database site_health'
export DATABASE_URL=postgresql://postgres:<password>@127.0.0.1:5432/site_health
python3 manage.py init-db                               # applies schema.sql, then functions.sql

# 2. a site to watch. Either the fake one (another terminal; it writes its own configuration) ...
python3 tests/fake_site.py 8900 /tmp/site_health.config.json
python3 manage.py setup /tmp/site_health.config.json
export NTFY_URL=http://127.0.0.1:8900/ntfy NTFY_TOPIC=sh-local-test
# ... or a real one: copy site_health.config.example.json, edit it, and
#     python3 manage.py setup site_health.config.json

# 3. the server, with the collectors inside it
export SH_PASS_OWNER='<a password>' DASHBOARD_URL=http://127.0.0.1:8000
uvicorn server:app --port 8000                          # http://127.0.0.1:8000/site
python3 manage.py check                                 # the database, the configuration, every flow
```

Within a minute the "עכשיו" card shows the first round. With the fake site:
`curl 'http://127.0.0.1:8900/__fake?path=/cart/&status=502'` breaks the cart; at the next full minute
the alert "האתר לא עונה: סל" opens and is published to the fake ntfy (`curl http://127.0.0.1:8900/__fake`
shows it); `curl 'http://127.0.0.1:8900/__fake?reset=1'` repairs it, and "חזר לתקין" follows.
PageSpeed cannot measure a local address, so the speed cards stay empty here.

## Running the tests

```bash
cd reference
python3 -m pytest -q                    # all three layers; about half a minute
python3 -m pytest -q tests/test_collectors.py
node tests/test_rum_snippet.js          # the real-user script in a browser (needs Playwright)
```

They need `pytest`, `httpx` (for the server tests) and `psycopg`, and a PostgreSQL where they may
create a scratch database (`SH_TEST_ADMIN_URL`). The database gets a random name and is dropped at
the end; no other database is touched. No test talks to anything outside the machine: the
collectors are tested against `tests/fake_site.py`.

## Deploying: Supabase + one always-on web service

1. **The database.** In the Supabase project's SQL editor run `schema.sql`, then `functions.sql`
   (or run `manage.py init-db` with `DATABASE_URL`). Both make every table and function private:
   only the secret key gets in.
2. **How the server reaches it.** Two choices; both are tested.
   - `SUPABASE_URL` + `SUPABASE_SECRET_KEY`: plain HTTPS to `/rest/v1/rpc/<function>`, no driver,
     works from any host. The default choice. Know its limit: a call made with the secret key is
     cut off after **8 seconds** by default. The read functions answer well inside that (the tests
     hold them under 2 seconds on 90 days of data). If a call does hit it (the first `sh_cleanup`
     on a database that was never cleaned), raise it once in the SQL editor:
     `alter role service_role set statement_timeout = '30s'; notify pgrst, 'reload config';`
     After changing `functions.sql` the REST interface must re-read its list of functions; the
     file ends with the `notify` that tells it to.
   - `DATABASE_URL`: a normal Postgres connection. On Supabase take the **pooler** connection
     string from the project's "Connect" dialog ("Session pooler", port 5432, or "Transaction
     pooler", port 6543), not the direct one: the direct host answers over IPv6 only, and most
     small hosts (Render among them) have no IPv6 route. (This sentence is from experience, not
     from the kit's research: confirm it in the Connect dialog of the project.) `db.py` uses
     autocommit and no prepared statements, so both pooler modes work. The 8-second limit does
     not apply here.
3. **The web service.** Any host that keeps one small process running all the time; a plan that
   sleeps when idle stops the measuring. Put it in a region near the site's visitors (§7.5).
   - Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`.
   - **One worker process only.** No `--workers 2`, no process manager with several workers:
     every worker would start its own collectors, and the sign-in limits live in memory.
   - Health-check path: `/health`. It always answers 200 (also when the database is down: a
     restart does not repair a database); `ok` and `last_probe_age_sec` say how things are.
   - Environment: the table above. Generate the topic and the share token with
     `manage.py new-secret` and paste them into the host's settings, never into the repository.
4. **The configuration.** `python3 manage.py setup site_health.config.json` (from any machine
   that has the database variables). Safe to repeat after every change of the file; the
   collectors pick a changed page list up within five minutes, without a restart.
5. **The collectors as a separate worker (optional).** Set `COLLECTORS=0` on the web service and
   run `python3 collectors.py` as a second always-on process with the database variables and the
   collectors' variables. Same code, same schedule.
6. **Who watches the watcher (§7.10).** On Supabase: follow the header of `deadman.sql`. Elsewhere,
   or in addition: a heartbeat service and `HEARTBEAT_URL`.
7. **Real users.** `rum/` and §7.7.

### What happens while two workers overlap (a deploy)

For a minute or two the old and the new process both run. Nothing is stored or pushed twice:

- **Probe rounds** are stored under their scheduled second, and `sh_probe_add` ignores a round
  that is already there. Both workers do request the pages in that minute.
- **Speed runs** are stored under the start of their slot (the quarter hour, the hour, the five
  minutes), and `sh_speed_add` ignores a run that is already there. The rotation hands every page
  to one caller only (`sh_rotation_next`).
- **Pushes**: `sh_alerts_check` hands an owed message to one caller and to nobody else for two
  minutes. A worker never publishes later than 45 seconds after its round (plus the 10-second
  publish timeout), so it is done long before its claim lapses.
- **Daily jobs** keep their "done today" marker in the database. Two workers that find a job owed
  in the same minute may both run it; the result is stored once (the day's snapshot is replaced,
  the morning message is queued once by `sh_morning` itself).

## Verify every collector once after the deploy

Run these where the service's environment is (on Render: the service's Shell). Each prints what it
measured and stored. `run-once` leaves the daily markers alone, so the scheduled run still happens.
A probe round or a speed round run by hand is stored under the same scheduled moment as the
scheduler's own (this minute, this quarter of an hour), so it never adds a second one: when the
scheduler has been there first, the answer shows the fresh measurement and `"stored": 0`.

| Command | What a good answer looks like |
|---|---|
| `python3 manage.py check` | `database: reachable`, the pages you configured, and after a minute `תקין` next to `בודק זמינות האתר` |
| `python3 manage.py run-once probe` | one row per probe page with `"ok": true` and a small `ms`. `"stored": 0` means the running scheduler already stored this minute's round, which is the proof that it runs |
| `python3 manage.py test-push` | `ntfy answered 200`, and the phone shows "בדיקה: בריאות האתר". The push says it is a test and leaves no row in the database |
| `python3 manage.py run-once alerts` | `[]` when nothing is wrong; otherwise the messages it pushed, with status 200 |
| `python3 manage.py run-once speed-core` | (1-5 minutes) one row per core page with `"ok": true` and an `lcp_ms`. `API key not valid`: the key is wrong. An `err` with `Status code: 403`: the site's firewall blocks Google's test |
| `python3 manage.py run-once sitemap` | `"pages"`: about the number of pages the site really has. Too many: add the site's private slugs to `private_paths` in the configuration |
| `python3 manage.py run-once speed-rotation` | two rows of two site pages (after the sitemap is loaded) |
| `python3 manage.py run-once catalogue` | `"n"`: the number of broken products, and today's `snap_date` (shops only) |
| `python3 manage.py run-once cert` | the issuer and `days_left` |
| `python3 manage.py run-once morning` | `{"n": 1}` the first time on a day; then `run-once alerts` pushes it. The scheduled one will not come again that day |
| `python3 manage.py run-once cleanup` | the number of rows deleted per table (zeros on a new database) |

Then walk through the go-live checklist of §10.

## The schedule

| What | When |
|---|---|
| full probe round | second 0 of every minute (10-second timeout) |
| light probe round | second 30 of every minute (5-second timeout, no response time stored) |
| alert tick, then the heartbeat ping | right after each full round, on its own thread |
| core pages on a phone / on a desktop | every 15 minutes / every hour, stored under the start of the slot |
| rotation | 2 pages every 5 minutes (`ROTATION_PAGES` in `collectors.py`; up to 6 for a larger site, §7.7) |
| sitemap, cleanup, catalogue, certificate | once a day from 03:00, 03:30, 04:00, 04:00 local time (`DAILY_TIMES`) |
| morning message | once a day from the configured `morning` time (default 07:30 local) |

A daily job that is behind (the worker was down at its hour) runs as soon as the worker is up
that day. A daily job that fails is tried again every ten minutes until it succeeds, and is marked
done only then. The certificate check is skipped for a site that is not https, the catalogue check
for `"platform": "other"`.

## What the tests do not cover

Be aware of these before trusting a green run.

- **Google PageSpeed.** No test calls the real API. The collector is tested against a fake that
  serves Lighthouse's own sample results (13.6.0 and 12.8.2), cut down, inside the documented
  PageSpeed envelope. The real-user part of the answer (`loadingExperience`) follows the API's
  documentation and was never seen live. Of the error answers, the daily-quota 429 and the
  invalid-key 400 are bodies that Google really sent; the "Lighthouse returned error" 500 and the
  per-minute 429 are the documented shapes. That the daily quota starts again at midnight Pacific
  time is Google's general rule for API quotas, not something that was observed here. Make one
  real call first: `manage.py run-once speed-core`.
- **ntfy.** The publish format (JSON to the server's root) is tested against a fake. Delivery to
  a phone is not: `manage.py test-push`.
- **Shops.** The WooCommerce catalogue is a fake built from the Store API's documented fields.
  The Shopify branch reads an unofficial endpoint whose shape is known from experience only; it
  has never run against a real shop.
- **TLS.** All test traffic is plain HTTP on 127.0.0.1. Requests over https, and the certificate
  check against a real host, are not exercised (the tests cover the parsing of a certificate and
  the two failure paths). `manage.py run-once cert`.
- **`deadman.sql`** is not executed by the tests at all: the test database has no pg_cron, pg_net
  or Vault. Its own header lists how to verify it on the project.
- **Supabase itself.** The collector tests reach the database through `DATABASE_URL`. The HTTPS
  transport of `db.py` is tested against a stand-in (`tests/test_server.py`), never against a
  real project; the 8-second limit is therefore not exercised either.
- **Real time.** The schedules are tested with clocks that the tests set, and the loop's survival
  with a step that raises. No test waits for a real minute: that a full round really happens at
  second 0 and a light one at second 30 is to be seen on the running service.
- **Limits that are tested lowered or not at all:** the 50 MB sitemap file (tested at 2 KB), the
  500 sitemap files, the 50,000 pages, the 30 MB catalogue page and PageSpeed answer.
- **A name lookup that hangs** is simulated by a check that sleeps; a compressed page body is
  tested on the decoding function only.
- **`tests/test_rum_snippet.js`** is a separate command and needs a browser.
