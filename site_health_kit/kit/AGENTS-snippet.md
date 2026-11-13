## Site Health kit ("בריאות האתר")

The kit that this repository's Site Health screen is built from is unpacked in `site-health-kit/`
(read-only: nothing in it is edited). The backend that is deployed is `site-health/`, a copy of
`site-health-kit/reference/`; the deployed screen is `site-health/site_health.html` and the
site's configuration is `site-health/site_health.config.json`. For any work on it:

1. Read `site-health-kit/START-HERE.md` completely before editing anything, at most 150 lines per
   command. Each file of its reading table counts as read only after you saw its last line,
   `<!-- EOF <path> -->`. It is the source of truth for how to work; the owner's message wins over it.
2. The screen is a `cp` of `site-health-kit/site_health.html`, changed only with the small
   patches that spec §6.9 allows. Never regenerate it. Check:
   `python3 site-health-kit/tools/check_template.py site-health/site_health.html`.
3. Hebrew strings are product text: keep them byte for byte in UTF-8, never translated or escaped.
4. The JSON contract (spec §5) is binding. Never invent a number; no sample data in production.
5. You never hold a production secret. The owner types secrets into the host's settings
   (`site-health-kit/OWNER-STEPS.md`); never ask for one, never print one. No customer data is stored.
6. Tests never write to the live database.
7. Keep `PROGRESS.md` up to date; after a context compaction re-read `START-HERE.md` and
   `PROGRESS.md` first.
8. Write to the owner in Hebrew: short, plain words, one decision per message, and a last line
   saying what they do now.

Checks. Each is one command; run them from the root of the repository:

```bash
python3 site-health-kit/tools/check_template.py site-health/site_health.html    # prints SCREEN OK
(cd site-health && python3 -m pytest -q)       # the backend; needs a scratch PostgreSQL (site-health/README.md)
(cd site-health && node tests/test_rum_snippet.js)                              # needs Playwright
```

The acceptance test of the screen needs the mock running, so it takes two terminals:
`python3 site-health-kit/mock_server.py` in one (it stays running), `node site-health-kit/check_screen.js`
in the other (needs Playwright). It takes about 30 seconds, and up to 10 minutes on a broken screen:
never cut it short.
