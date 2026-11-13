## Site Health kit ("בריאות האתר")

A build kit for the Site Health screen lives in `site-health-kit/`. For any work on it:

1. Read `site-health-kit/START-HERE.md` completely before editing anything, at most 150 lines per
   command. A file counts as read only after you saw its last line, `<!-- EOF ... -->`. It is the
   source of truth for how to work; the owner's message wins over it.
2. The screen is `site-health-kit/site_health.html`. Copy it with `cp` and change it only with
   small patches allowed by spec §6.9. Never regenerate it. Check:
   `python3 site-health-kit/tools/check_template.py <path to the deployed copy>`.
3. Hebrew strings are product text: keep them byte for byte in UTF-8, never translated or escaped.
4. The JSON contract (spec §5) is binding. Never invent a number; no sample data in production.
5. Secrets only in environment variables. Never print their values. No customer data is stored.
6. Tests never write to the live database.
7. Keep `PROGRESS.md` up to date; after a context compaction re-read `START-HERE.md` and
   `PROGRESS.md` first.
8. Write to the owner in Hebrew: short, plain words, one decision per message, and a last line
   saying what they need to do now.

Checks:

```bash
python3 site-health-kit/mock_server.py            # the screen on fake data → http://localhost:8787/site
node site-health-kit/check_screen.js              # acceptance test of the screen
cd site-health-kit/reference && python3 -m pytest -q
```
