# Site Health kit — spec: build phases, go-live checklist, lessons (§9–§11)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 9. Build order and checks

Report after each phase: what was built, which checks ran, their result. The commands below are
written for the layout of `START-HERE.md` section E: the kit in `site-health-kit/`, the backend in
`site-health/` (a copy of `reference/`), and phases 2 to 7 run **in `site-health/`**. Commands,
variables and the local rehearsal are spelled out in `reference/README.md`.

| Phase | Build | Done when |
|---|---|---|
| 0. Look | `START-HERE.md` section E: the repository, the mock, the screen | you have seen all 11 titled cards and the controls (without a browser window: the pictures of `check_screen.js --shots ./shots`), opened a drill-down, pressed `הסברים`; `node site-health-kit/check_screen.js` passes |
| 1. Intake | `START-HERE.md` section D | `site_health.config.json` exists, `python3 manage.py install-sql --config site_health.config.json` accepts it, and the owner confirmed it |
| 2. Database | tables and `sh_*` functions | `python3 -m pytest -q tests/test_sql.py` passes against a scratch database (or your equivalent tests of the rules in §7.3 and §7.8); `python3 manage.py init-db --file install.sql` runs twice on a scratch database |
| 3. Server | sign-in, roles, the routes of §5 | `python3 -m pytest -q tests/test_server.py` passes. Then, against the server running locally on a scratch database (README, "Checking a running server"): `python3 ../site-health-kit/tools/check_access.py http://127.0.0.1:8000` passes; `node ../site-health-kit/check_screen.js http://127.0.0.1:8000 --basic --cookie "$COOKIE"` passes, and once more with `--path "/status?k=$SH_SHARE_TOKEN"` in place of the cookie (the share link); `python3 ../site-health-kit/tools/check_template.py site_health.html` prints `SCREEN OK` |
| 4. Probe + alerts | §7.5, §7.8, §7.9 | `python3 -m pytest -q tests/test_collectors.py` passes. Then the local rehearsal against `tests/fake_site.py` (it needs `SH_ALLOW_PRIVATE=1`): a page that starts failing opens an alert within 2 minutes, the fake ntfy lists the push, the alert closes when the page recovers; 3 dead minutes show as one outage |
| 5. Speed | §7.6, sitemap | in the rehearsal, with `PAGESPEED_URL` pointing at the fake: `python3 manage.py run-once speed-core` stores one run per core page and the speed tiles show it. That proves the plumbing, not a speed: the first real PageSpeed result is seen in phase 8 (`OWNER-STEPS.md` step 5) |
| 6. Daily jobs | catalogue, certificate, cleanup, morning message | in the rehearsal each `run-once` of README's table gives its good answer and its flow shows `תקין`. What stays empty on the fake site, by design: it is plain http, so the certificate check is off and its card hidden (`skipped: …`); the morning message is skipped until the oldest probe round is 6 hours old; `מהירות אצל לקוחות` is `אין נתון` until a browser sends a measurement |
| 7. Real users | §7.7 | `node tests/test_rum_snippet.js` passes; the add-on is ready for the owner (`python3 manage.py rum-plugin …` wrote the ZIP, or the Shopify snippet is filled in). After phase 8: a page view of the real site with `?sh_test=1` appears in "מהירות אצל לקוחות" within a minute, counted as a test measurement (if not: the causes of §7.7, a tester signed in to the site's admin first), and the owner got the privacy message (`OWNER-STEPS.md` step 9) |
| 8. Deploy | `OWNER-STEPS.md` steps 2 to 9, in that order | the checklist of §10 is green on the live address |
| 9. Hand-over | `OWNER-STEPS.md` step 10 | the owner got the note |

Rules for the whole build:

- Run the real thing. A phase is not done because the code looks right.
- **A check that could not run is open, not passed.** Without Playwright the `check_screen.js` and
  `test_rum_snippet.js` checks stay open; without a scratch PostgreSQL the pytest checks do. Write
  it into `PROGRESS.md` and into your report, and say who can close it.
- An unattended run (nobody to ask): phase 1 is "waiting for confirmation", phases 2 to 7 go on
  against stand-ins, phases 8 and 9 wait for the owner (`START-HERE.md` section D).
- **Give `check_screen.js` 15 minutes and do not cut it short.** On a healthy screen it takes
  about 30 seconds; on a screen broken at its root (its script fails on every load) about 10
  minutes, and it still ends with `N passed, M failed` and exit code 1.
- Use a scratch database for tests. Never run tests that write against the live database.
- Do not leave test alerts, test pushes or fake rows in the live database. A test push to the
  real topic must say it is a test.
- **Phase 8: nothing is pushed before the topic is set, and the topic is the last of the
  settings, before the watchdog and the add-on** (`OWNER-STEPS.md` step 7, then 8 and 9). Until
  `NTFY_TOPIC` exists in the host's settings, alerts open and show on the screen and every
  message is logged as not sent. Set it only after a first clean round was seen from the real
  host (`OWNER-STEPS.md` step 4: a firewall that refuses the prober would otherwise fill the
  owner's phone with `האתר לא עונה`), and tell the owner that from then on every alert arrives.
- **A project that already has a backend, in any language:** run the reference as it is, as its
  own small service next to that backend, and link the two (the configuration's `nav` and
  `links`, and a link from the existing dashboard). Do not port it. If the owner insists on a
  port, say what can still be checked: `check_screen.js --basic` (§5 and §6 as the screen sees
  them) and `tools/check_access.py` (§8) work against any server; the pytest files test the
  Python reference only, so the rules of §7.3 and §7.8 need tests of your own.

---

## 10. Go-live checklist

On the live address, with the throwaway check password of `OWNER-STEPS.md` step 6 (`$COOKIE` is
its session cookie). You hold no other secret. The two check programs only read: they change
nothing on the live service.

1. `/health` answers `"ok": true` with `"db": "ok"` and `"screen": "ok"`, and
   `node site-health-kit/check_screen.js <address> --basic --cookie "$COOKIE"` passes (it looks
   at the screen at 390 px and at 1280 px).
2. Every flow in `המדידה עצמה` is `תקין` (the flow list of `OWNER-STEPS.md` step 6). **The Google
   key is required for go-live** (`OWNER-STEPS.md` step 5): core speed cannot be switched off,
   and without the key the two speed flows stay `אין נתון`. A part that does not apply to the
   site is in the configuration's `off` list (§7.4): its flow is gone and its card hidden (for
   `real_users`, the tile `מהירות אצל לקוחות, שעה אחרונה` of "עכשיו"), so nothing reads `אין נתון`
   or `אין מדידות` for good. Two flows may lag on the first day:
   `מהירות אצל לקוחות` until the add-on is installed, and the daily ones until their hour.
3. The service is stopped for **16 minutes** on purpose and started again (the owner does it,
   `OWNER-STEPS.md` step 8), and the independent check of §7.10 speaks. A pass: with
   `deadman.sql` or `watchdog.py`, the phone gets `המדידה נעצרה: בודק זמינות האתר` 10 to 15
   minutes after the stop and `חזר לתקין: בודק זמינות האתר` within a few minutes of the start; with a
   heartbeat service, that service's own alarm and its own "up again".
4. Access: `python3 site-health-kit/tools/check_access.py <address> --no-share --no-quiet` passes.
   Then, as the last check (it blocks your address for ten minutes), the same with `--limiter`:
   nine wrong passwords, each with a made-up `X-Forwarded-For`, must end in 429; if they do not,
   `SH_PROXY_HOPS` does not match the host (§8.2; `OWNER-STEPS.md` 6f). A site that uses `SH_VENDOR_NOALERTS` runs it
   without `--no-quiet`, with the second throwaway password (`OWNER-STEPS.md` 6e); a name in that list that matches no
   vendor hides the alerts from every vendor (§8.1), so see that an ordinary vendor still gets them.
5. The share link, if the owner wanted one: the owner opens it on a phone and sees the screen
   without signing in; a made-up token answers 403
   (`curl -s -o /dev/null -w '%{http_code}\n' "<address>/status?k=not-the-token-0000000000"`).
   (The share page itself was tested in phase 3: `check_screen.js --basic --path "/status?k=…"`.)
6. The explanation texts match the real schedule. The number of probe pages and the "down" rule
   follow the configuration by themselves; check the rest (§6.9, and the rotation sentence of §7.7).
7. No secret where it does not belong. `git ls-files | grep -i '\.env'` prints nothing;
   `git grep -nE 'sb_secret_[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]{30,}\.eyJ'`
   (the shapes of a database key and of a Google key) prints nothing; after the share link was opened, the host's log shows no `k=` (the start command
   carries `--no-access-log`); the throwaway check passwords are deleted from the host's settings,
   a sign-in with each answers 401, and your `.env.check` is gone.
8. The owner saw the screen on their phone and saw one push arrive (`OWNER-STEPS.md` step 7).

---

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
    `down_after` to 2 in the configuration; the screen's sentences follow.
14. **Outsiders get an allow-list, never a block-list.** A block-list fails open the day someone
    adds a route.
15. **Each part of the main answer fails alone.** One slow or broken query must not blank the screen.

<!-- EOF spec/09-build-and-checks.md -->
