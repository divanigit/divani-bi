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
