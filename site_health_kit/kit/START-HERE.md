# Site Health kit — start here

You are going to build the **Site Health screen ("בריאות האתר")** for a website: one phone-first
page that shows whether the site is up, how fast it is, what is broken and which alerts fired,
plus the measuring machinery behind it. It is a port of a screen that runs in production; the
screen and its data contract are fixed, the machinery behind it is a tested reference you adapt.

This file is the entry point and the single source of truth for **how to work**. If files
disagree: the owner's message wins, then this file, then `spec/`, then comments in code.

## 1. Read before you build

Read these files **completely**, in this order, before writing code. Read at most 150 lines per
command (`sed -n '1,150p' FILE`, then `'151,300p'`, …); a file counts as read only when you have
seen its last line, which is always `<!-- EOF <path> -->`. If a tool prints
`Warning: truncated output`, read that range again in smaller pieces.

| # | File | What it gives you |
|---|---|---|
| 1 | `START-HERE.md` | this file: rules, the owner, intake, phases, done |
| 2 | `spec/03-system.md` | what is measured, cadences, thresholds, definitions, per-site configuration (§3, §4) |
| 3 | `spec/05-api-contract.md` | the JSON the screen reads, field by field (§5) — binding |
| 4 | `spec/06-screen.md` | the screen: layout, texts, interactions, what you may change (§6) — binding |
| 5 | `spec/07-backend.md` | tables, functions, collectors, alert rules, pushes (§7) — reference design |
| 6 | `spec/08-access.md` | sign-in, roles, vendors, the share link (§8) |
| 7 | `spec/09-build-and-checks.md` | build phases with their checks, the go-live checklist, lessons already paid for (§9–§11) |

Section numbers (§5.2, §7.8, …) are the same everywhere in the kit, including in code comments.

Working files (do not read them top to bottom; use them):

| File | What it is |
|---|---|
| `site_health.html` | **the screen.** One HTML file, no build step, no libraries. Copy it; never retype it |
| `mock_server.py` | a fake backend with realistic data (standard library only): the contract by example |
| `check_screen.js` | the acceptance test of the screen (Playwright) |
| `tools/check_template.py` | proves a deployed screen file is still the kit's screen |
| `reference/` | a tested reference backend: SQL, server, collectors, real-user script, tests. `reference/README.md` explains it |
| `AGENTS-snippet.md` | the short block to put at the top of the target repository's `AGENTS.md` |
| `MANIFEST.json` | every file of the kit with its size, line count and checksum |

## 2. Rules

1. **The screen is `site_health.html`. Copy it with `cp`; change it only with small patches**, and
   only what `spec/06-screen.md` §6.9 allows (per-site values go into `SH_CONFIG`). Never
   regenerate it from memory. `python3 tools/check_template.py <your copy>` must pass.
2. **Hebrew text is product text.** Keep every Hebrew string byte for byte, in UTF-8. Do not
   translate, transliterate or escape it (`\uXXXX`, HTML entities). Pages stay `dir="rtl"`.
3. **The JSON contract of §5 is binding**: field names, types, the literal Hebrew values, the
   order of rows. `mock_server.py` returns exactly those shapes.
4. **Never invent a number.** Every figure on the screen comes from a stored measurement. A
   collector that has not run yet shows as the card's empty state. No sample rows in production.
5. **Secrets live only in environment variables or the host's secret store.** Never in the
   repository, the HTML, a log or a chat message. Name the variable; never print its value
   (no `env`, no `cat .env`). If a key is needed, tell the owner where to paste it.
6. **No customer data.** No names, emails, phones, order numbers or visitor IP addresses are
   stored. URLs are stored without query strings.
7. **Be a polite client of the monitored site**: one probe round a minute, hard timeouts, a
   distinct User-Agent. Never load-test it.
8. **Outsiders get an allow-list** (vendors, share link): deny by default (§8).
9. **Work in the phases of §9, in order, and run each phase's checks.** A phase is done when its
   checks pass on the real thing. Report a failed check as failed.
10. **Tests never write to the live database.** Use a scratch database.
11. **Keep `PROGRESS.md`** at the root of the target repository: the phase checklist, decisions
    you made, the owner's answers, what is blocked. Update it at the end of every phase. After a
    context compaction, read `START-HERE.md` and `PROGRESS.md` again before continuing.
12. **Commit at the end of every phase** (the owner asks for this by giving you this kit), with a
    one-line message naming the phase. Do not push or deploy unless the owner asked.
13. When something external blocks you (a missing key, a refused API, no network in your
    sandbox), stop that item, say exactly what is missing and who can provide it, and continue
    with what does not depend on it. The kit's own tests need no network.

## 3. The owner

The owner is not a developer. Unless they tell you otherwise:

- Write to them in **Hebrew**, short messages, plain words. No technical terms; when one is
  unavoidable, explain it in half a sentence.
- **One decision per message.** A question says what happens on yes, what happens on no, and
  whether it can be changed later.
- Introducing something new, say three things: what it is, what they do with it, what they get.
- End every message with one line: what the owner needs to do now, or "אתה לא צריך לעשות כלום".
- At the end of every phase send two or three lines: what now works, what you checked, what is next.

## 4. Intake: find out before building the backend

Find what you can yourself (open the site, read its sitemap, detect the platform), then confirm
with the owner, one short message per topic. Record the answers in `site_health.config.json`
(format: `reference/site_health.config.example.json`; no secrets in it) and in `PROGRESS.md`.

| # | Topic | What you need | How to find it / default |
|---|---|---|---|
| 1 | The site | its public address | Ask. Check which of `www` / no-`www` is the real one. |
| 2 | Platform | WooCommerce, Shopify, other | `/wp-json/wc/store/v1/products?per_page=1` answers → WooCommerce; `/products.json?limit=1` answers → Shopify; else other. |
| 3 | Probe pages (default 4) | the pages checked every minute, each with a short Hebrew name | A shop: home (`בית`), one category, one product, the cart. Otherwise: home plus the three pages that matter most. Pick pages that exercise different parts of the server. The home page must be one of them. |
| 4 | Core pages (default 5) | the pages whose speed is measured every 15 minutes | The probe pages plus one more. Only pages that open without signing in or filling a cart. |
| 5 | Who gets alerts | the people who get a push on their phone | Each installs the ntfy app and subscribes to one topic (§7.9). Ask who. |
| 6 | Who may view | owner; staff; outside vendors (read-only); a share link | Default: owner only. Offer the vendor role when the owner mentions an agency or a developer. |
| 7 | Hosting | where the database and the small server run | Default: Supabase + one small always-on web service. If the owner already has a dashboard, the screen joins it. |
| 8 | "Down" rule | alert on the first failed check, or only after two in a row | Production default: the first (nothing missed, more noise). Offer two when the owner dislikes noise. |
| 9 | Google key | a PageSpeed Insights API key (free) | The owner creates it (§7.6 has the steps) and pastes it into the host's settings. Without it the speed cards stay empty. |

Do not ask the owner about thresholds, colors, wording or cadences. Those are decided.

**If you cannot ask** (a run with nobody watching): take the defaults above, choose the pages
from the sitemap and the site's menu, mark every such choice in `PROGRESS.md` under
"הנחות שצריך לאשר", and list them in your final message. Do not send test pushes or deploy
without the owner.

## 5. First hour

1. `python3 mock_server.py` → open `http://localhost:8787/site` at phone width. That is the
   finished screen, on fake data. Open a drill-down, press `הסברים`, try `?role=vendor`.
2. `node check_screen.js` (needs Playwright; if it is missing, say so and go on).
3. `cd reference && python3 -m pytest -q` (needs a scratch Postgres; see `reference/README.md`).
4. Read the spec files, then start the intake.

## 6. Done

The go-live checklist of §10 passes on the live address; `PROGRESS.md` is complete; the owner
received one test push, saw the screen on their phone, and got a short Hebrew note with the
address, how to subscribe to alerts, and what each color means. Paste the output of the final
checks into your last message.

<!-- EOF START-HERE.md -->
