# Site Health kit — spec: build phases, go-live checklist, lessons (§9–§11)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 9. Build order and checks

Report after each phase: what was built, which checks ran, their result.

| Phase | Build | Done when |
|---|---|---|
| 0. Look | unpack; run the mock; open the screen | you have seen all 11 cards, opened a drill-down, pressed `הסברים` |
| 1. Intake | `START-HERE.md` §4 | `site_health.config.json` exists and the owner confirmed it |
| 2. Database | tables and `sh_*` functions | `reference/tests/test_sql.py` passes against a scratch database (or your equivalent tests of the rules in §7.3 and §7.8) |
| 3. Server | login, roles, the routes of §5 | `reference/tests/test_server.py` passes; `node check_screen.js <server> --basic --cookie "sh_session=…"` passes; `python3 tools/check_template.py <the deployed screen file>` prints `SCREEN OK` |
| 4. Probe + alerts | §7.5, §7.8, §7.9 | `reference/tests/test_collectors.py` passes; then against a throwaway local site (`reference/tests/fake_site.py`): a page that starts failing opens an alert within 2 minutes, a push is logged, the alert closes when the page recovers; 3 dead minutes show as one outage |
| 5. Speed | §7.6, sitemap | one real PageSpeed call stored for the home page; the screen's speed tiles show it |
| 6. Daily jobs | catalogue, certificate, cleanup, morning message | each ran once and its flow shows `תקין` |
| 7. Real users | §7.7 | `node reference/tests/test_rum_snippet.js` passes; a page view of the real site with `?sh_test=1` appears in "מהירות אצל לקוחות" within a minute, counted as a test measurement |
| 8. Deploy | host, environment, schedules, the independent check of §7.10 | the checklist of §10 is green on the live address |
| 9. Hand-over | a short Hebrew note for the owner | they know the address, how to subscribe to alerts, and what each color means |

Rules for the whole build:

- Run the real thing. A phase is not done because the code looks right.
- Use a scratch database for tests. Never run tests that write against the live database.
- Do not leave test alerts, test pushes or fake rows in the live database. A test push to the
  real topic must say it is a test.

---

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
    `down_after` to 2.
14. **Outsiders get an allow-list, never a block-list.** A block-list fails open the day someone
    adds a route.
15. **Each part of the main answer fails alone.** One slow or broken query must not blank the screen.

<!-- EOF spec/09-build-and-checks.md -->
