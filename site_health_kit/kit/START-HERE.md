# Site Health kit: start here

Kit version 1.0. Write the version, and the build id from `MANIFEST.json`, into `PROGRESS.md`.

You are going to build the **Site Health screen ("בריאות האתר")** for a website: one phone-first
page that shows whether the site is up, how fast it is, what is broken and which alerts fired,
plus the measuring behind it. The screen and its data contract are fixed (they run in production
elsewhere); the machinery behind them is a tested reference that you adapt.

This file is the entry point and the single source of truth for **how to work**. If files
disagree: the owner's message wins, then this file, then `spec/`, then comments in code.

## A. Read before you build

Read these files **completely**, in this order. Read at most 150 lines per command
(`sed -n '1,150p' FILE`, then `'151,300p'`, …); a file of this table counts as read only when you
have seen its last line, which is always `<!-- EOF <path> -->`. If a tool prints
`Warning: truncated output`, read that range again in smaller pieces.

| # | File | What it gives you |
|---|---|---|
| 1 | `START-HERE.md` | this file: rules, the owner, intake, layout, done |
| 2 | `spec/03-system.md` | what is measured, cadences, thresholds, definitions, the screen's configuration (§3, §4) |
| 3 | `spec/05-api-contract.md` | the JSON the screen reads, field by field (§5): binding |
| 4 | `spec/06-screen.md` | the screen: layout, texts, interactions, what you may change (§6): binding |
| 5 | `spec/07-backend-data.md` | the backend's shape, tables, functions, every key of the configuration file (§7.1–§7.4) |
| 6 | `spec/07-collectors-alerts.md` | the collectors, alert rules, pushes, the watchdog (§7.5–§7.11) |
| 7 | `spec/08-access.md` | sign-in, roles, vendors, the share link (§8) |
| 8 | `spec/09-build-and-checks.md` | build phases with their checks, the go-live checklist, lessons already paid for (§9–§11) |
| 9 | `OWNER-STEPS.md` | everything only the owner can do (accounts, keys, passwords, the alert channel, the add-on on the site): a ready Hebrew message for each step, and how you confirm it without seeing a secret |
| 10 | `reference/README.md` | the reference backend: its files, environment variables, commands, the local rehearsal, what its tests do not cover |

Files 1 to 8 before any code; 9 before the first message about accounts or money; 10 before
phase 2. Section numbers (§3–§11) belong to `spec/` and are the same everywhere in the kit;
the sections of this file have letters.

Working files (do not read them top to bottom; use them):

| File | What it is |
|---|---|
| `site_health.html` | **the screen.** One HTML file, no build step, no libraries. Copy it; never retype it |
| `mock_server.py` | a fake backend with realistic data: the contract by example |
| `check_screen.js` | the acceptance test of the screen (node + Playwright) |
| `tools/check_template.py` | proves a deployed screen file is still the kit's screen |
| `tools/check_access.py` | black-box check of the access rules of §8 against any running server |
| `reference/` | the tested reference backend: SQL, server, collectors, watchdog, real-user script, tests |
| `AGENTS-snippet.md` | the short block to put at the top of the target repository's `AGENTS.md` |
| `MANIFEST.json` | the kit's version and build id, and every file with its size and checksum |

## B. Rules

1. **The screen is `site_health.html`. Copy it with `cp`; change the copy only with small
   patches**, and only what §6.9 allows (per-site values come from the configuration). Never
   regenerate it from memory. `python3 site-health-kit/tools/check_template.py site-health/site_health.html` must pass.
   **Nothing inside `site-health-kit/` is ever edited** (section E).
2. **Hebrew text is product text.** Keep every Hebrew string byte for byte, in UTF-8. Do not
   translate, transliterate or escape it (`\uXXXX`, HTML entities). Pages stay `dir="rtl"`.
3. **The JSON contract of §5 is binding**: field names, types, the literal Hebrew values, the
   order of rows. `mock_server.py` returns exactly those shapes.
4. **Never invent a number.** Every figure on the screen comes from a stored measurement. A
   collector that has not run yet shows as the card's empty state. No sample rows in production.
5. **You never hold a production secret**: not the database key, not a person's password, not the
   alert topic, not the share token. Secrets live only in the host's settings; the owner types
   each one there (`OWNER-STEPS.md`) and you confirm from the outside. Never ask for one, never
   print one (no `env`, no `cat .env`), never put one in the repository, a log or a chat message.
   The only exception: the throwaway check passwords of `OWNER-STEPS.md` step 6: read-only,
   and deleted right after the check.
6. **No customer data.** The backend stores no names, emails, phones, order numbers or visitor
   addresses, and URLs without their query strings. A page path can still carry an identifier;
   the intake lists such paths so they are never stored (row 6).
7. **Be a polite client of the monitored site**: one full probe round a minute plus the light
   look at the half minute (§7.5), hard timeouts, a distinct User-Agent. Never load-test it.
8. **Outsiders get an allow-list** (vendors, share link): deny by default (§8).
9. **Work in the phases of §9, in order, and run each phase's checks.** A phase is done when its
   checks pass on the real thing. Report a failed check as failed and an open one as open.
10. **Tests never write to the live database.** Use a scratch database.
11. **Keep `PROGRESS.md`** at the root of the target repository: the kit's version, the phase
    checklist, your decisions, the owner's answers, what is blocked, what is open. Update it at
    the end of every phase. After a context compaction, read `START-HERE.md` and `PROGRESS.md` again.
12. **Commit at the end of every phase** (giving you this kit is the owner asking for it), with a
    one-line message naming the phase. Do not push or deploy unless the owner asked.
13. When something external blocks you (a missing key, a refused API, no network in your
    sandbox), stop that item, say exactly what is missing and who can provide it, and go on
    with the rest. The kit's own tests need no network.

## C. The owner

The owner is not a developer. Unless they tell you otherwise:

- Write to them in **Hebrew**, short messages, plain words. No technical terms; when one is
  unavoidable, explain it in half a sentence. Write so that it fits a man or a woman
  (`פותחים`, `לוחצים`, `אצלך`), not `אתה צריך`.
- **One decision per message.** A question says what happens on yes, what happens on no, and
  whether it can be changed later.
- Introducing something new, say three things: what it is, what they do with it, what they get.
- End every message with one line: what the owner does now, or "אין צורך לעשות דבר".
- After every phase send two or three lines: what now works, what you checked, what is next.
- For what the owner must do in another service, send the ready message of `OWNER-STEPS.md`.

## D. Intake: find out before building the backend

Find what you can yourself (open the site, read its sitemap, detect the platform), then confirm
with the owner, one message per topic. Record the answers in
`site-health/site_health.config.json` (every key: §7.4; no secrets in it) and in `PROGRESS.md`.

| # | Topic | What you need | How to find it / default |
|---|---|---|---|
| 1 | The site | its public address | Ask. Check which of `www` / no-`www` is the real one. |
| 2 | Time zone | the zone of the site's customers (`time_zone`, required) | Take it from the site's country (Israel: `Asia/Jerusalem`) and say so. |
| 3 | Platform | WooCommerce, Shopify, other | Test WooCommerce first: `<site>/wp-json/wc/store/v1/products?per_page=1` answers 200 with JSON → WooCommerce, even if the next test answers too. Else `<site>/products.json?limit=1` answers → Shopify. Else `other`. **The Shopify branch has never run against a real shop** (§7.7): tell the owner of a Shopify shop so, and look at the first real read together. |
| 4 | Probe pages (default 4) | the pages checked every minute, each with a short Hebrew name | A shop: home (`בית`), one category, one product, the cart. Otherwise home plus the three pages that matter most. Prefer pages that will not be deleted (a category rather than one product where possible). Give the home page an `expect` text copied from the real page (§7.5). A cart or checkout that redirects to another domain needs that domain in `extra_hosts`. |
| 5 | Core pages (default 5) | the pages whose speed is measured every 15 minutes | The probe pages plus one more public page, such as `אודות`. Only pages that open without signing in or filling a cart. The home page is always one of them. |
| 6 | Private pages | the path segments never stored from real users or the sitemap (`private_paths`, single names such as `עגלה` or `track`) | The site's own names for cart, checkout and account pages (often translated), and the first segment of every path that carries an identifier: order tracking, unsubscribe and password-reset links, profiles. Read the sitemap and the menus. |
| 7 | Who gets alerts | the people who get a push on their phone | Ask who. Each installs the ntfy app (`OWNER-STEPS.md` step 7). |
| 8 | Who may view | owner; staff; outside vendors (read-only); a share link | Default: owner only. Offer the vendor role when the owner mentions an agency or a developer. |
| 9 | Money and accounts | where the database, the code and the small server live (an account each, in the owner's name) | **Before the owner chooses anything, send the message of `OWNER-STEPS.md` step 1** (what is needed, what is normally paid monthly). Default: Supabase + a private GitHub repository (normally free; skip it if the repository has the owner's remote) + one small always-on web service. A project that already has a backend, in any language: run the reference as its own small service next to it and link the two (`nav`, `links`); do not port it (§9). |
| 10 | "Down" rule | alert on the first failed check, or only after two in a row (`down_after`) | Default 1 (nothing missed, more noise). Offer 2 when the owner dislikes noise. The screen's sentences follow by themselves. |
| 11 | Google key | a PageSpeed Insights API key (free) | The owner creates it (`OWNER-STEPS.md` step 5). **Required for go-live:** without it the two speed flows stay `אין נתון` (§10 item 2). |
| 12 | The add-on on the site | who can install a plugin on the site, or paste a snippet into its theme | Ask. If it is a developer or an agency, the owner forwards them the message of `OWNER-STEPS.md` step 9. |
| 13 | Parts that do not apply | the `off` list (§7.4) | No sitemap → `sitemap`; nobody can add the add-on → `real_users`; a shop with no public catalogue → `catalogue`. A site that sells nothing is platform `other`. |

Do not ask the owner about thresholds, colors, wording or cadences. Those are decided.

**If you cannot ask** (a run with nobody watching): take the defaults, choose the pages
from the sitemap and the site's menu, and write every such choice into `PROGRESS.md` under
"הנחות שצריך לאשר". Mark phase 1 "waiting for confirmation" and go on through phase 7 on
stand-ins (the mock, `tests/fake_site.py`, a scratch database). Phases 8 and 9 need the owner:
do not deploy and do not send a push without them. Your final message lists the assumptions for
information and asks one question only, the first.

## E. Layout of the target repository, and the first hour

```
<repository>/
  SITE_HEALTH_KIT.md          the container (committed)
  site-health-kit/            the unpacked kit: read-only, committed, never edited
  site-health/                the backend that is deployed: a copy of site-health-kit/reference/
    site_health.html          the deployed screen, copied from the kit
    site_health.config.json   the site's configuration
  PROGRESS.md  AGENTS.md  .gitignore
```

0. **The repository.** If the folder is not a git repository: `git init`. Write `.gitignore`:
   `.env`, `.env.*`, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `shots/`, `install.sql`,
   `*.zip`, and any file that holds a secret. Put the block of `site-health-kit/AGENTS-snippet.md`
   at the top of `AGENTS.md`, start `PROGRESS.md`, and commit the container and the unpacked kit.
1. `python3 site-health-kit/mock_server.py` (it keeps running: use another terminal for the
   rest) → open `http://localhost:8787/site` at phone width. That is the finished screen, on fake
   data. Open a drill-down, press `הסברים`, try `?role=vendor`, `?hide=nowRum,certCard` (as a
   server hides parts that are off) and `--scenario empty`.
2. `node site-health-kit/check_screen.js`; with `--shots ./shots` it also saves the screen at
   phone and desktop width: look at them. It needs node and Playwright 1.45 or newer; at the
   root of the repository: `npm install playwright && npx playwright install chromium`. If that
   cannot be installed, say so and go on: the checks that use `check_screen.js` (phases 0 and 3,
   checklist item 1) and `tests/test_rum_snippet.js` (phase 7) stay **open, not passed**.
3. Make the backend, once, and run its tests (they need a scratch PostgreSQL; without one they
   stop with one line that says what to start, see `reference/README.md`):

   ```bash
   cp -r site-health-kit/reference site-health
   cp site-health-kit/site_health.html site-health/site_health.html
   cd site-health && pip install -r requirements-dev.txt && python3 -m pytest -q
   ```
4. Read the rest of table A, then start the intake.

Everything you adapt lives in `site-health/`, which is also the host's root directory. The tests
find the kit in `../site-health-kit` (or in `$SH_KIT_DIR`). Another version of the kit never
unpacks over this one: the unpack command refuses, and says what to do. The same version again
restores the kit's files, and a second line `not part of the kit: …` names files to remove.

## F. Done

The go-live checklist of §10 passes on the live address; `PROGRESS.md` is complete; the owner saw
the screen on their phone, saw one push arrive, and got the hand-over note of `OWNER-STEPS.md`
step 10. Paste the output of the final checks into your last message.

<!-- EOF START-HERE.md -->
