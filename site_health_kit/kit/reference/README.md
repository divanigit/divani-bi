# Site Health: the reference backend

A working, tested implementation of spec §7 and §8: the database, the server, the collectors.
In a target repository this folder is copied once (`cp -r site-health-kit/reference site-health`,
`START-HERE.md` section E) and the copy is what you adapt and deploy; every command below runs in
that copy. Section numbers (§) point into the kit's `spec/` files. Read this file completely.

## What each file is

| File | What it is |
|---|---|
| `schema.sql` | the tables, indexes and privileges. Apply it first. Safe to run again. |
| `functions.sql` | every `sh_*` SQL function: the only way the server and the collectors touch the database. Apply it second. Safe to run again. |
| `db.py` | `rpc(fn, params)`: one call of one `sh_*` function, over HTTPS (Supabase) or over a Postgres connection. |
| `server.py` | sign-in, roles, the screen and its data calls (§5, §8), the real-user ingest `POST /m`, `GET /health`. Starts the collectors unless `COLLECTORS=0`. |
| `collectors.py` | everything that measures (§7.5–§7.9): probe, lab speed, sitemap, catalogue, certificate, alert tick and pushes, morning message, cleanup, and the scheduler. `python3 collectors.py` runs it as a separate worker. |
| `manage.py` | the command line (table below). |
| `watchdog.py` | the independent "the measuring stopped" check for any host (§7.10, option 3). One file, standard library only. |
| `deadman.sql` | the same check inside a Supabase database (§7.10, option 1). The tests run its logic against stand-ins for pg_cron, pg_net and Vault; real scheduling and sending are not tested. |
| `rum/site-health-rum.js` | the real-user script (§7.7). `rum/site-health-rum.php` is its WordPress plugin, packed by `manage.py rum-plugin`; `rum/site-health-rum.liquid` is the same script as a Shopify theme snippet (never run in a real shop). |
| `site_health.config.example.json` | the site's configuration with every key. Copy it to `site_health.config.json` and edit it. No secret in it. **The keys are explained in one place: spec §7.4.** |
| `requirements.txt`, `requirements-dev.txt` | the pinned packages of the service (Python 3.10 or newer), and those of the tests. The collectors, `manage.py` and `watchdog.py` need only the standard library, plus `psycopg` when `DATABASE_URL` is used. |
| `tests/conftest.py` | finds the kit, and gives the tests a scratch database with `schema.sql` and `functions.sql` applied. |
| `tests/sim.py` | fills a database with believable measurements through the write functions. |
| `tests/fake_site.py` | a local stand-in for every outside party: the monitored site (a WooCommerce shop, or a Shopify one with `--platform shopify`), its sitemap and catalogue, PageSpeed, ntfy, a heartbeat service, a dashboard's `/health`. Used by the tests; also runs by hand. |
| `tests/fixtures/` | two small PageSpeed answers (Lighthouse 13.6.0 and 12.8.2): Lighthouse's own sample results, cut down to the keys the collector reads. |
| `tests/test_sql.py`, `tests/test_server.py`, `tests/test_collectors.py` | the tests of the three layers (the last one also tests `manage.py` and `watchdog.py`). |
| `tests/test_rum_snippet.js` | the real-user script, the plugin and the snippet in a real browser (node + Playwright; not part of pytest). |

Next to this folder, in the kit: `tools/check_access.py` (black-box check of §8 against a running
server), `check_screen.js` and `tools/check_template.py`.

## Environment variables

Secrets live only here, in the settings of the host. **On a live service the owner types them;
you never see their values** (`OWNER-STEPS.md`). Everything about the site itself is in
`site_health.config.json`, never in a variable.

| Name | Read by | Needed? | What it is |
|---|---|---|---|
| `SUPABASE_URL` + `SUPABASE_SECRET_KEY` | server, collectors, manage | one of the two database choices | the project address (`https://<ref>.supabase.co`; plain http only for 127.0.0.1) and its secret key (`sb_secret_…`). The database is reached over HTTPS. If both choices are set, this one wins. |
| `DATABASE_URL` | server, collectors, manage | the other choice | a Postgres connection string. Needs `psycopg`. |
| `SH_PASS_OWNER` | server | yes | the owner's password. Without it nobody can sign in. |
| `SH_PASS_STAFF` | server | no | one password for staff (sees everything). |
| `SH_PASS_VENDOR_<NAME>` | server | no | one password per outside vendor (read-only). `<NAME>` is the name in the login log. `SH_PASS_VENDOR_CHECK` (and `…_CHECK_<something>`) is the throwaway of a deployment check: the server warns at every start while it is set. |
| `SH_VENDOR_NOALERTS` | server | no | vendor names, comma-separated, who see no alerts at all. Matched against `<NAME>` without case, spaces and hyphens read as `_`. **An entry that matches no vendor variable switches alerts off for every vendor** until it is corrected, and logs an error at start-up. |
| `SH_SHARE_TOKEN` | server | no | the token of the share link `/status?k=<token>`. Empty or shorter than 20 characters: no share link. |
| `SH_PROXY_HOPS` | server | no (default `1`) | how many proxies of the host stand in front of the server; decides which `X-Forwarded-For` entry is the client (§8.2). `0`: no proxy, the header is ignored. |
| `SH_SCREEN` | server | no | path of the screen file. Without it: `site_health.html` next to `server.py`, else `../site_health.html`. |
| `SH_RUM_PER_MINUTE`, `SH_RUM_PER_DAY` | server | no (defaults `300`, `20000`) | how many real-user rows are stored a minute and a day, for all visitors together (§7.7). Beyond it rows are dropped. |
| `COLLECTORS` | server | no (default on) | `0`: this server process measures nothing (the collectors run elsewhere). |
| `PAGESPEED_KEY` | collectors | no | Google PageSpeed Insights API key (§7.6). Without it the two speed collectors do not run and the speed cards stay empty. |
| `NTFY_TOPIC` | collectors, watchdog | no | the ntfy topic alerts are pushed to (§7.9). Without it alerts still open and show on the screen; every message is logged as not sent. On a live service it is set last. |
| `NTFY_URL`, `NTFY_TOKEN` | collectors, watchdog | no | the ntfy server (default `https://ntfy.sh`), and the access token of a reserved topic or a self-hosted server. |
| `DASHBOARD_URL` | collectors, watchdog | no, recommended | this dashboard's public address. It is named in the probe's `User-Agent` (`SiteHealthProbe/1.0 (+<address>)`, so a firewall can allow it) and opened by a tap on a push. |
| `HEARTBEAT_URL` | collectors | no | the ping address of an outside heartbeat service; requested after every full probe round (§7.10, option 2). |
| `PAGESPEED_URL` | collectors | no | another address for the PageSpeed API, for a rehearsal against `tests/fake_site.py`. |
| `SH_ALLOW_PRIVATE` | collectors | no | `1`: requests to the monitored site may go to private and local addresses. Needed for `tests/fake_site.py` and for a site on a private network; without it such a request is refused (§7.5). |
| `SH_SITEMAP_MB` | collectors | no (default `10`) | the largest sitemap file that is read, in MB after decompression; at most 50. |
| `SH_TEST_ADMIN_URL` | tests | no | a Postgres where the tests may create and drop a scratch database. Default: `postgresql://postgres:shtest@127.0.0.1:5432/postgres`. |
| `SH_KIT_DIR` | tests | no | the folder of the unpacked kit, when it is not `../site-health-kit` and not the parent folder. |

`python3 manage.py check` lists which of these are set: names only, never a value. Neither the
server nor the collectors log a key, a password, a token, the topic or the heartbeat address.
The database variables are trimmed; a wrong one shows as a short text in `/health` (`"db"`),
never with the key: `SUPABASE_URL must start with https://`, `the database address or key is
malformed`, `HTTP 401…`, `database call failed (…): check DATABASE_URL`.

## Commands

| Command | Needs | What it does |
|---|---|---|
| `python3 manage.py install-sql --config site_health.config.json --out install.sql` | nothing | writes **one SQL file**: `schema.sql`, `functions.sql` and the `sh_setup` call with the configuration. The owner pastes it into the database's SQL editor (`OWNER-STEPS.md` step 2). It refuses a configuration that is plainly wrong; `sh_setup` checks the rest when the file runs, so rehearse it. Write it again after every change of the configuration. |
| `python3 manage.py init-db --file install.sql` | `DATABASE_URL` | applies that file: the rehearsal on a scratch database (run it twice). Plain `init-db` applies `schema.sql` and `functions.sql`. |
| `python3 manage.py setup site_health.config.json` | the database | loads the configuration (`sh_setup`) where you hold the database variables: a rehearsal. Safe to repeat. |
| `python3 manage.py check` | the database | the variables that are set, the configuration, what is switched off, every flow. |
| `python3 manage.py run-once <collector>` | the service's environment | one run of one collector, printing what it stored (table further down). A part that is off answers `skipped: …`. |
| `python3 manage.py test-push` | `NTFY_TOPIC` | one push that says it is a test; leaves no row in the database. |
| `python3 manage.py rum-plugin --endpoint https://<dashboard>/m --out site-health-rum.zip` | nothing | the WordPress plugin as a ZIP with its two values filled in (the live host comes from `site_health.config.json`, or `--live-host`). The owner uploads it (`OWNER-STEPS.md` step 8). |
| `python3 manage.py new-secret --out <file>` | nothing | writes a random topic name and share token into a new file and prints neither. For an owner who runs Python on their own computer; an agent never reads that file. |
| `python3 watchdog.py --dashboard https://<dashboard> [--loop]` | `NTFY_TOPIC` | one look at `/health` (for cron, every 5 minutes), or a look every minute with `--loop`. Pushes `המדידה נעצרה: בודק זמינות האתר` and `חזר לתקין: …`. Exit code 0, 1 (a push was owed and not accepted) or 2. |

## Local quick start: the whole system on one machine

Three terminals, all in this folder. None of the values below is a secret.

```bash
pip install -r requirements.txt

# terminal 1: a site to watch, and every outside service (it prints its export lines and stays running)
python3 tests/fake_site.py 8900 /tmp/site_health.config.json

# terminal 2: a database of its own (any PostgreSQL 15+), then the server with the collectors inside it
psql postgresql://postgres:<password>@127.0.0.1:5432/postgres -c 'create database site_health'
export DATABASE_URL=postgresql://postgres:<password>@127.0.0.1:5432/site_health
python3 manage.py install-sql --config /tmp/site_health.config.json --out /tmp/install.sql
python3 manage.py init-db --file /tmp/install.sql        # twice, to see that it may run again
export SH_ALLOW_PRIVATE=1 SH_PROXY_HOPS=0 DASHBOARD_URL=http://127.0.0.1:8000
export NTFY_URL=http://127.0.0.1:8900/ntfy NTFY_TOPIC=sh-local-test HEARTBEAT_URL=http://127.0.0.1:8900/hb
export PAGESPEED_URL=http://127.0.0.1:8900/pagespeedonline/v5/runPagespeed PAGESPEED_KEY=local-rehearsal-key
export SH_PASS_OWNER=local-owner-password SH_PASS_VENDOR_CHECK=local-check-password
export SH_PASS_VENDOR_CHECK_QUIET=local-quiet-password SH_VENDOR_NOALERTS=CHECK_QUIET
export SH_SHARE_TOKEN=local-share-token-0123456789
uvicorn server:app --port 8000 --no-access-log           # http://127.0.0.1:8000/site ; it stays running

# terminal 3: the same exports as terminal 2, then
python3 manage.py check                                  # the database, the configuration, every flow
```

Without `SH_ALLOW_PRIVATE=1` every check of the fake site is refused (it is on 127.0.0.1), and
`SH_PROXY_HOPS=0` is right here because no proxy stands in front. Within a minute the "עכשיו"
card shows the first round. `curl 'http://127.0.0.1:8900/__fake?path=/cart/&status=502'` breaks
the cart: at the next full minute the alert "האתר לא עונה: סל" opens and is published to the fake
ntfy (`curl http://127.0.0.1:8900/__fake` lists the pushes, with the topic shown as `(topic)`).
`curl 'http://127.0.0.1:8900/__fake?reset=1'` repairs the site and keeps that list; "חזר לתקין: סל"
follows. `?clear=1` empties the list; the fake's own start-up text lists every other switch.

What the fake cannot show: its PageSpeed answers every page with one sample result (the speed
cards fill; it proves the plumbing, not a speed; the sample's LCP is 10.9 seconds, so after the
second speed round `עמוד איטי` opens for every core page, which is expected here); it is plain
http, so the certificate check is off and its card hidden; the morning message is skipped while the oldest probe round is younger
than 6 hours; real users stay `אין נתון`. For a Shopify rehearsal start the fake with
`--platform shopify`. For a real site: copy `site_health.config.example.json`, edit it, and use
it in place of the fake's file (without `SH_ALLOW_PRIVATE` and `PAGESPEED_URL`).

## Checking a running server

In terminal 3 of the quick start (the kit is in `../site-health-kit`; when you run in the kit
itself, in `..`):

```bash
KIT=../site-health-kit; BASE=http://127.0.0.1:8000
python3 $KIT/tools/check_access.py $BASE                 # the access rules of §8, from the outside
COOKIE=$(curl -s -o /dev/null -D - --data-urlencode "p=$SH_PASS_VENDOR_CHECK" "$BASE/login" \
         | tr -d '\r' | sed -n 's/^[Ss]et-[Cc]ookie: \(sh_session=[^;]*\).*/\1/p')
node $KIT/check_screen.js $BASE --basic --cookie "$COOKIE"                  # the screen, signed in
node $KIT/check_screen.js $BASE --basic --path "/status?k=$SH_SHARE_TOKEN"  # the screen through the share link
python3 $KIT/tools/check_template.py site_health.html                       # SCREEN OK
```

`check_access.py` fails on purpose once with a wrong password and once with a wrong token: run it
at most twice in ten minutes. Its `--limiter` check is for the live address; against 127.0.0.1 it
fails unless the server is started with `--no-proxy-headers` (uvicorn itself believes
`X-Forwarded-For` from 127.0.0.1). On a live address the same commands run with the throwaway
check password that the owner sets and deletes (`OWNER-STEPS.md` step 5); the share-link line is
then the owner's to try, because the token is not yours.

## Running the tests

```bash
pip install -r requirements-dev.txt     # the service's packages, pytest and httpx
python3 -m pytest -q                    # all three layers: about 1,100 tests, about a minute
python3 -m pytest -q tests/test_server.py    # this file alone needs no PostgreSQL
node tests/test_rum_snippet.js          # the real-user script in a browser (needs Playwright)
```

- **A scratch PostgreSQL (15 or newer)** where the tests may create and drop a database:
  `SH_TEST_ADMIN_URL`. To get one: `docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=shtest postgres:16`,
  or, where PostgreSQL 16 is installed, `pg_ctlcluster 16 main start`. The database gets a random
  name and is dropped at the end; no other database is touched. When none answers, the run ends
  with one line that starts `No Postgres answers at SH_TEST_ADMIN_URL` (return code 2), without
  a password in it.
- **The kit.** The tests use the kit's `mock_server.py` and `site_health.html`. They look in
  `$SH_KIT_DIR`, then in the parent folder, then in `../site-health-kit`; when none holds them
  the run ends with one line that names `SH_KIT_DIR`.
- No test talks to anything outside the machine: the collectors are tested against
  `tests/fake_site.py`. Parts that need `openssl`, `php` or `psql` are skipped where the machine
  has none. Playwright (1.45 or newer): `npm install playwright && npx playwright install chromium`
  at the root of the repository.

## Deploying: who does what

**The owner opens the accounts and types every secret; you prepare files and values and confirm
from the outside.** The steps, the ready messages and the confirmations are in `OWNER-STEPS.md`.
What follows is what you need to know behind them.

1. **The database.** One file, `install.sql`, pasted once into the SQL editor (or any SQL
   console). It makes every table and function private; the grants to Supabase's `service_role`
   are written out in `schema.sql`, so a project without automatic table grants works too.
2. **How the server reaches it.** Two choices; both are tested.
   - `SUPABASE_URL` + `SUPABASE_SECRET_KEY`: plain HTTPS to `/rest/v1/rpc/<function>`, no driver,
     works from any host. The default choice. Know its limit: a call made with the secret key is
     cut off after **8 seconds** by default. The read functions answer well inside that (the tests
     hold them under 2 seconds on 90 days of data). If a call does hit it (the first `sh_cleanup`
     on a database that was never cleaned), the owner raises it once in the SQL editor:
     `alter role service_role set statement_timeout = '30s'; notify pgrst, 'reload config';`
     After a change of `functions.sql` the REST interface must re-read its list of functions; the
     file ends with the `notify` that tells it to.
   - `DATABASE_URL`: a normal Postgres connection. On Supabase take the **pooler** connection
     string from the project's "Connect" dialog (session or transaction pooler), not the direct
     one: the direct host answers over IPv6 only, and many small hosts have no IPv6 route. (This
     sentence is from experience, not checked from here: confirm it in that dialog.) `db.py` uses
     autocommit and no prepared statements, so both pooler modes work. The 8-second limit does
     not apply here.
3. **The web service.** Any host that keeps one small process running all the time; a plan that
   sleeps when idle stops the measuring. A region near the site's visitors (§7.5).
   - Root directory: this folder (`site-health/`). Build: `pip install -r requirements.txt`.
     Python 3.10 or newer; set the version explicitly where the host's default is older.
   - Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT --no-access-log`. The share
     token travels in the query string; `server.py` also cuts query strings out of uvicorn's
     access log by itself, so a forgotten flag leaks nothing. Under another server program
     (gunicorn, hypercorn) turn its access log off.
   - **One worker process only.** No `--workers 2`, no scaling to several instances: every worker
     would start its own collectors, and the sign-in limits live in memory.
   - Health-check path: `/health`. Always status 200 (a restart does not repair a database):
     `{"ok", "db", "screen", "last_probe_age_sec"}`; `ok` is true only when `db` and `screen` are
     `"ok"`. `"screen": "missing"` means the host did not get `site_health.html`.
4. **A change of the configuration.** Edit the file, write `install.sql` again, the owner runs it
   again. The collectors pick a changed page list up within five minutes, without a restart.
5. **The collectors as a separate worker (optional).** `COLLECTORS=0` on the web service, and
   `python3 collectors.py` as a second always-on process with the database variables and the
   collectors' variables. Same code, same schedule.
6. **Who watches the watcher (§7.10).** `deadman.sql` on Supabase (follow its header), or a
   heartbeat service and `HEARTBEAT_URL`, or `watchdog.py` on a machine that does not stop with
   the host. `OWNER-STEPS.md` step 7.
7. **Real users.** `manage.py rum-plugin`, `rum/`, §7.7, `OWNER-STEPS.md` step 8.

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

## Verify every collector by hand

These need the service's environment (the database variables and the collectors' own). You have
it in the rehearsal above. On a live service you do not: there the proof is the flow list seen
from the outside (`OWNER-STEPS.md` step 5), and only the owner could run a command, in the host's
command screen. `run-once` leaves the daily markers alone, so the scheduled run still happens. A
probe round or a speed round run by hand is stored under the same scheduled moment as the
scheduler's own, so it never adds a second one: when the scheduler has been there first, the
answer shows the fresh measurement and `"stored": 0`.

| Command | What a good answer looks like |
|---|---|
| `python3 manage.py check` | `database: reachable`, the pages you configured, `switched off: …`, and after a minute `תקין` next to `בודק זמינות האתר` |
| `python3 manage.py run-once probe` | one row per probe page with `"ok": true` and a small `ms`. `"stored": 0`: the running scheduler already stored this minute's round, which proves that it runs |
| `python3 manage.py test-push` | `ntfy answered 200`, and the phone shows "בדיקה: בריאות האתר" |
| `python3 manage.py run-once alerts` | `[]` when nothing is wrong; otherwise the messages it pushed, with status 200 |
| `python3 manage.py run-once speed-core` | (1–5 minutes on the real API) one row per core page with `"ok": true` and an `lcp_ms`. `API key not valid`: the key is wrong. An `err` with `Status code: 403`: the site's firewall blocks Google's test |
| `python3 manage.py run-once speed-desktop` | the same for the desktop strategy |
| `python3 manage.py run-once sitemap` | `"pages"`: about the number of pages the site really has. Too many: add the site's private slugs to `private_paths` |
| `python3 manage.py run-once speed-rotation` | two rows of two site pages (after the sitemap is loaded) |
| `python3 manage.py run-once catalogue` | `"n"`: the number of broken products, and today's `snap_date` (shops only) |
| `python3 manage.py run-once cert` | the issuer and `days_left`; on an http site `skipped: the site is not https: there is no certificate to check` |
| `python3 manage.py run-once morning` | `{"n": 1}` the first time on a day, and `run-once alerts` then pushes it; `{"n": 0}` when the day is done; `{"n": 0, "skipped": "the oldest probe round is less than 6 hours old"}` on a new installation |
| `python3 manage.py run-once cleanup` | the number of rows deleted per table (zeros on a new database) |

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

A daily job that is behind (the worker was down at its hour, or was first started later that day)
runs as soon as the worker is up. A daily job that fails is tried again 10 minutes later, three
more times at the most, and then waits for the next day (the count is in memory: a restart
starts it again). A part that the configuration switches off (`off`, §7.4; also the certificate
of an `http://` site and the catalogue of platform `other`) never runs.

## Good to know

- **The first day.** No morning message goes out until the oldest stored probe round is 6 hours
  old. Until `NTFY_TOPIC` is set nothing is pushed at all, and messages from that time are never
  sent later.
- **A full outage is one alert per probe page**, and one recovery per page (§7.8): four pages,
  eight pushes. The hand-over note tells the owner.
- **A check is ok only for status 200.** A redirect to another host is not followed and fails
  the check (`redirected to another host`): a cart on another domain needs that domain in
  `extra_hosts`. A page that a firewall answers with a 200 challenge counts as up unless the
  page has an `expect` text.
- **A refused PageSpeed key** (`API key not valid`, or a 403): nothing is measured and the
  collector asks again once an hour, so enabling the API in Google's console needs no restart.
- **Real-user rows have three budgets**: 60 a minute per visitor address; 300 a minute and 20,000
  a day for all together (`SH_RUM_PER_MINUTE`, `SH_RUM_PER_DAY`, counted in memory); and the
  database stores nothing once the last 24 hours hold 30,000 rows. Beyond a budget rows are
  dropped and nothing breaks. A busier site raises `SH_RUM_PER_DAY`, or measures a share of its
  views (the `sample` value of the script; in your copy of the plugin, `SITE_HEALTH_RUM_SAMPLE`).
  A row is about 150 bytes: 10,000 measured views a day are about 45 MB over the 30 days kept.
- **Pages that real users never measure**: cart, checkout, account and order pages, the
  `private_paths` of the configuration, and any path that holds an `@`, a 16-digit number or a
  long code of letters and digits (§7.7).
- **Database connections.** With `DATABASE_URL` the server holds up to 9 and each collector
  thread one more: up to 13 in all (12 without a PageSpeed key); a separate `collectors.py`
  worker holds up to 4. With `SUPABASE_URL` there are no standing connections.
- **Limits.** A sitemap file of more than 10 MB is refused (`SH_SITEMAP_MB`, up to 50). A sitemap
  of more than 50,000 pages fails every night: such a site needs `"off": ["sitemap"]`, or a larger
  `SITEMAP_PAGES` in `collectors.py`. A catalogue page above 10 MB or a catalogue above 300 MB
  stops the read.
- **Sessions.** The session cookie carries its expiry (365 days, vendors 30) and the server
  enforces it. `/logout` only removes the cookie from that browser; changing a password in the
  host's settings ends every session of that person at once.
- **Every answer carries** `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`: the screen cannot be shown
  inside a frame of another page.
- **Start-up log.** A sound configuration starts without a warning. Warnings name what is wrong,
  never a value: no owner password, two people with the same password, a password shorter than
  12 characters, a short share token, an unknown name in `SH_VENDOR_NOALERTS`, a check password
  that is still set, a missing screen file.
- **Addresses are stored in one spelling** (`sh_url`, §7.3), so the configuration may spell a
  Hebrew address as a person types it.
- **A database set up by an older kit** takes the new `install.sql` as it is. Its configuration
  must now hold `time_zone` and a home page that is a core page; a page whose stored spelling
  changes starts its speed history anew; everybody signs in once more (the cookie changed).

## What the tests do not cover

Be aware of these before trusting a green run. From where this kit was written none of the real
services could be reached: not Google PageSpeed, not ntfy, not Supabase or its REST interface,
not pg_cron, pg_net or Vault, not a real shop.

- **Google PageSpeed.** The collector is tested against a fake that serves Lighthouse's own sample
  results (13.6.0 and 12.8.2), cut down, inside the documented PageSpeed envelope. The real-user
  part of the answer (`loadingExperience`) follows the API's documentation and was never seen
  live. Of the error answers, the daily-quota 429 and the invalid-key 400 are bodies that Google
  really sent; the others are documented or usual shapes. That the daily quota starts again at
  midnight Pacific time is Google's general rule, not something observed here.
- **ntfy.** The publish format (JSON to the server's root) is tested against a fake. Delivery to
  a phone is not.
- **Shops.** The WooCommerce catalogue is a fake built from the Store API's documented fields.
  The Shopify branch reads an unofficial endpoint whose shape is known from experience only; it
  has never run against a real shop. Neither has the Shopify snippet. The WordPress plugin was
  packed, linted and run in a stand-in for WordPress, never in a real one.
- **TLS.** One page over https and the certificate check run against a certificate made on the
  spot on 127.0.0.1 (where `openssl` is installed). Real hosts are not exercised.
- **The redirect and address rules** of §7.5 are tested between two local servers and with a
  made-up name resolver, not against real DNS.
- **`deadman.sql`** runs in the tests against stand-ins for pg_cron, pg_net and Vault: what it
  decides and hands over is tested, that anything is really scheduled or sent is not. Its header
  lists how to verify it on the project.
- **`watchdog.py`** is tested against the fake ntfy and the reference server. Cron, a second
  host and delivery to a phone are not.
- **Supabase itself.** The collector tests reach the database through `DATABASE_URL`. The HTTPS
  transport of `db.py` is tested against a stand-in, never against a real project; the 8-second
  limit is therefore not exercised either. `install.sql` ran on a local PostgreSQL 16, not in
  Supabase's SQL editor.
- **Real time.** The schedules are tested with clocks that the tests set. No test waits for a
  real minute: that a full round really happens at second 0 and a light one at second 30 is to
  be seen on the running service.
- **Limits that are tested lowered:** the size of a sitemap file, the 500 sitemap files, the
  50,000 pages, the two catalogue budgets.
- **A name lookup that hangs** is simulated by a check that sleeps; a compressed page body is
  tested on the decoding function only.

<!-- EOF reference/README.md -->
