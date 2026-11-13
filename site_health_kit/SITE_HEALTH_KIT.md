# ערכת "בריאות האתר" — קובץ אחד לקודקס

**לדורון, בקצרה**

- **מה זה:** כל מה שקודקס צריך כדי לבנות את מסך "בריאות האתר" לאתר אחר: ההוראות, המסך עצמו, ובדיקות.
- **מה עושים איתו:** שמים את הקובץ הזה בתיקיית הפרויקט של האתר החדש, ושולחים לקודקס את ההודעה שלמטה.
- **מה יוצא:** קודקס שואל אותך כמה שאלות קצרות (כתובת האתר, אילו עמודים לבדוק, מי מקבל התראות) ואז בונה, שלב אחרי שלב.

ההודעה לקודקס (להעתיק, ולהשלים את כתובת האתר):

> בתיקייה יש קובץ SITE_HEALTH_KIT.md. אל תקרא את כולו. תריץ את פקודת הפריסה שכתובה בראש הקובץ, תקרא את site-health-kit/START-HERE.md עד השורה האחרונה, ותעבוד לפיו. אני רוצה את מסך בריאות האתר לאתר: ________. תכתוב לי בעברית, קצר ופשוט, ושאלה אחת בכל פעם.

---

# For the coding agent

This file is a container: 23 files (about 501 KB) are embedded below the line
`FILES BELOW`. **Do not read or print the part below that line.** Unpack it instead.

**Step 1 — unpack.** From the directory that contains this file, run this one command:

```bash
python3 -c "import re;exec(re.search(r'(?s)# --- unpack ---\n(.*?)# --- end unpack ---',open('SITE_HEALTH_KIT.md',encoding='utf-8').read()).group(1))"
```

It writes the folder `site-health-kit/`, verifies the checksum of every file, and prints
`KIT OK`. If it fails, stop and tell the owner the file arrived damaged. Never recreate a file
of the kit from memory.

**Step 2 — read `site-health-kit/START-HERE.md`** completely, to its last line
(`<!-- EOF START-HERE.md -->`), at most 150 lines per command. It tells you what else to read
and how to work.

The command above runs this script, which is the only part of this file you need to trust:

```python
# --- unpack ---
import hashlib, os, re
s = open('SITE_HEALTH_KIT.md', encoding='utf-8').read()
n = 0
for m in re.finditer(r'<!-- FILE: (\S+) sha256=([0-9a-f]{64}) -->\n~~~~~~~~[^\n]*\n(.*?\n)~~~~~~~~\n<!-- END FILE -->', s, re.S):
    path, digest, body = m.groups()
    assert not os.path.isabs(path) and '..' not in path.split('/'), 'bad path: ' + path
    assert hashlib.sha256(body.encode('utf-8')).hexdigest() == digest, 'damaged copy of ' + path + ' (get the file again)'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    open(path, 'w', encoding='utf-8', newline='\n').write(body)
    n += 1
assert n == 23, 'expected 23 files, found %d (the file is cut; get it again)' % n
print('KIT OK: unpacked', n, 'files into site-health-kit/')
# --- end unpack ---
```

Contents:

- `site-health-kit/START-HERE.md` (125 lines)
- `site-health-kit/SKILL.md` (15 lines)
- `site-health-kit/AGENTS-snippet.md` (26 lines)
- `site-health-kit/MANIFEST.json` (137 lines)
- `site-health-kit/AGENTS.md` (47 lines)
- `site-health-kit/SPEC.md` (1036 lines)
- `site-health-kit/check_screen.js` (197 lines)
- `site-health-kit/mock_server.py` (486 lines)
- `site-health-kit/site_health.html` (943 lines)
- `site-health-kit/reference/db.py` (98 lines)
- `site-health-kit/reference/functions.sql` (997 lines)
- `site-health-kit/reference/requirements.txt` (8 lines)
- `site-health-kit/reference/schema.sql` (180 lines)
- `site-health-kit/reference/server.py` (631 lines)
- `site-health-kit/reference/site_health.config.example.json` (19 lines)
- `site-health-kit/reference/rum/site-health-rum.js` (50 lines)
- `site-health-kit/reference/rum/site-health-rum.php` (83 lines)
- `site-health-kit/reference/tests/conftest.py` (161 lines)
- `site-health-kit/reference/tests/sim.py` (115 lines)
- `site-health-kit/reference/tests/test_rum_snippet.js` (69 lines)
- `site-health-kit/reference/tests/test_server.py` (1349 lines)
- `site-health-kit/reference/tests/test_sql.py` (1534 lines)
- `site-health-kit/tools/check_template.py` (62 lines)

---

FILES BELOW

<!-- FILE: site-health-kit/START-HERE.md sha256=6a57a7e639ad01397cc4b4b2b2ee9810d8411607148468056cdf144a3ecc7e79 -->
~~~~~~~~markdown
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
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/SKILL.md sha256=5eb84c7fed1a09201d9add870a0facdfc4d0cc194efb9bd82be671c9b9a34dc4 -->
~~~~~~~~markdown
---
name: site-health-kit
description: Build the Site Health screen ("בריאות האתר") for a website (uptime, speed, broken products, certificate, alerts to the phone) from a fixed screen template and a tested reference backend. Use when asked to build, port, deploy or change a site health / בריאות האתר screen.
---

# Site Health kit

Everything is in this folder. Read `START-HERE.md` completely, to its last line
(`<!-- EOF START-HERE.md -->`), before doing anything else, and follow it. It lists the other
files to read and the rules of the work.

Never retype `site_health.html`; copy it. Run the scripts and tests in this folder instead of
rewriting them.

<!-- EOF SKILL.md -->
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/AGENTS-snippet.md sha256=420c1b013b227ba4b569f150ed5416c811d5c1c88f19c260996579745c2b1bc9 -->
~~~~~~~~markdown
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
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/MANIFEST.json sha256=03d44bb81506b04e1abb653f3785154e71cef6390af46d8d13b9656a73254a42 -->
~~~~~~~~json
{
 "kit": "site-health-kit",
 "files": [
  {
   "path": "START-HERE.md",
   "bytes": 8891,
   "lines": 125,
   "sha256": "6a57a7e639ad01397cc4b4b2b2ee9810d8411607148468056cdf144a3ecc7e79"
  },
  {
   "path": "SKILL.md",
   "bytes": 703,
   "lines": 15,
   "sha256": "5eb84c7fed1a09201d9add870a0facdfc4d0cc194efb9bd82be671c9b9a34dc4"
  },
  {
   "path": "AGENTS-snippet.md",
   "bytes": 1489,
   "lines": 26,
   "sha256": "420c1b013b227ba4b569f150ed5416c811d5c1c88f19c260996579745c2b1bc9"
  },
  {
   "path": "AGENTS.md",
   "bytes": 2724,
   "lines": 47,
   "sha256": "aa385ee4bcb7c63870d701b68265df2ce9736c58f26139938964d6a0d3641836"
  },
  {
   "path": "SPEC.md",
   "bytes": 78157,
   "lines": 1036,
   "sha256": "fdd9f79709014250cd8877b429bf9563401f0b15b1f2232143ad076321e3bc49"
  },
  {
   "path": "check_screen.js",
   "bytes": 16279,
   "lines": 197,
   "sha256": "80662c26880462f998b18b56a41ef2fd8d14d46a19c4b52e1aaa602e78ee20d7"
  },
  {
   "path": "mock_server.py",
   "bytes": 26508,
   "lines": 486,
   "sha256": "545850f6a7feb0bb86c3b2fbe6ca126be465fe7b5b556a02b7f1c5779317f56c"
  },
  {
   "path": "site_health.html",
   "bytes": 88930,
   "lines": 943,
   "sha256": "35aa2ea6f3c976d6680e04eddbca6a115ed083e3ac6d0b2810f12c9809b093db"
  },
  {
   "path": "reference/db.py",
   "bytes": 4483,
   "lines": 98,
   "sha256": "b5c6d4a1b76c40b373d94a12e3590d02f8209e2a8fedf8d5a3830f9b9e6bf281"
  },
  {
   "path": "reference/functions.sql",
   "bytes": 50361,
   "lines": 997,
   "sha256": "d98a3938c1ce4263f6d9f00c9d54c32b4c2c8e2057434c06be00509c5fb474d7"
  },
  {
   "path": "reference/requirements.txt",
   "bytes": 360,
   "lines": 8,
   "sha256": "2dc54db937dacc2e56b3da4fcf7ad7fdab35c58996123333188157733f3552c1"
  },
  {
   "path": "reference/schema.sql",
   "bytes": 6463,
   "lines": 180,
   "sha256": "fb58b7f32b56e452066b5e093a8909d52cf569a9aae2d0632ce00212dff22ab1"
  },
  {
   "path": "reference/server.py",
   "bytes": 26641,
   "lines": 631,
   "sha256": "1c403fc6a1d72caac4855c9c721ddd3de77543d9ee5d0061417a58dbeb4cae3e"
  },
  {
   "path": "reference/site_health.config.example.json",
   "bytes": 867,
   "lines": 19,
   "sha256": "32391a8b4a5113440d0b5cb209677227c5fed4537da28b1b718667de0dc721a8"
  },
  {
   "path": "reference/rum/site-health-rum.js",
   "bytes": 3519,
   "lines": 50,
   "sha256": "b9d8eced011b36c1d5874a513f3345babb0646c28b1aa4666bd0278ea2cd3eac"
  },
  {
   "path": "reference/rum/site-health-rum.php",
   "bytes": 4163,
   "lines": 83,
   "sha256": "3be175709953cae5428ae51eefea7431f63013a671b04c2b487bdc985d595a23"
  },
  {
   "path": "reference/tests/conftest.py",
   "bytes": 6568,
   "lines": 161,
   "sha256": "0a7b07642e0b35ea1937743219420883cb4e0f0673a0bc4f47edaeb3ebea8f3c"
  },
  {
   "path": "reference/tests/sim.py",
   "bytes": 7028,
   "lines": 115,
   "sha256": "0226390c5945f267230039e2df58c924341619fc281a789b095417f757de5ad4"
  },
  {
   "path": "reference/tests/test_rum_snippet.js",
   "bytes": 3609,
   "lines": 69,
   "sha256": "e4b9c42e39296c9e3d84ebc75a760977651132ad79ff5c3273475dc95bf1000b"
  },
  {
   "path": "reference/tests/test_server.py",
   "bytes": 71803,
   "lines": 1349,
   "sha256": "d9a933aba5d1a38eca13f9c9875800b7648072692f20958d3e3f6af9ccbc4eee"
  },
  {
   "path": "reference/tests/test_sql.py",
   "bytes": 93048,
   "lines": 1534,
   "sha256": "565e1134e7deef4e4e06c3f25a7b1d06e7b14bb9859ff212a53e6bad81826362"
  },
  {
   "path": "tools/check_template.py",
   "bytes": 3026,
   "lines": 62,
   "sha256": "e0aa3f9bad6a81fc12dd917c6b07fbc697bd0607583838eedcee91bece8ec522"
  }
 ]
}
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/AGENTS.md sha256=aa385ee4bcb7c63870d701b68265df2ce9736c58f26139938964d6a0d3641836 -->
~~~~~~~~markdown
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
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/SPEC.md sha256=fdd9f79709014250cd8877b429bf9563401f0b15b1f2232143ad076321e3bc49 -->
~~~~~~~~markdown
# Site Health screen — build specification

This document tells a coding agent how to build the **"בריאות האתר" (Site Health)** screen for any
website: a phone-first page that shows, at a glance, whether the site is up, how fast it is, what is
broken, and what alerts fired, plus the measuring machinery behind it.

It is a port of a screen that runs in production at a furniture retailer. Everything about the
screen itself (layout, texts, thresholds, interactions, the JSON it reads) is taken from that
production code and is **binding**. The measuring machinery behind it is described as a reference
design that you may adapt to the target project's stack, as long as the contracts in §5 hold.

Files in this kit:

| File | What it is | Status |
|---|---|---|
| `SPEC.md` | this document | read all of it before writing code |
| `AGENTS.md` | standing rules for the target repository | copy to the target repo root (merge if one exists) |
| `site_health.html` | the screen: one HTML file, no build step, no libraries | **use it as is**; change only `SH_CONFIG` values and texts listed in §6.9 |
| `mock_server.py` | fake backend that answers every data call with realistic data (stdlib only) | run it to see the screen; it is the contract by example |
| `check_screen.js` | acceptance test of the screen (Playwright) | must pass before you call the screen done |
| `reference/` | tested reference backend: SQL schema and functions, server, collectors, tests | adapt to the target stack or use as is |

Do not retype `site_health.html` from memory or "improve" it. Copy the file.

Paths in this document are relative to the kit folder (`site_health_kit/` after unpacking).

---

## 1. How to work on this task

1. **Unpack and look first.** Run `python3 mock_server.py` and open `http://localhost:8787/site` at a
   phone width (390 px). That is the finished screen. Then run `node check_screen.js` (needs
   Playwright; if it is not available, say so and continue).
2. **Ask the owner the intake questions in §2 before building the backend.** Do not guess the site's
   pages, who gets alerts, or where the system will be hosted.
3. **Build in the phases of §9, in order.** Each phase ends with checks that you run and report.
   Do not start a phase while the previous phase's checks fail.
4. **Never invent a number.** Every figure on the screen comes from a stored measurement. If a
   collector has not run yet, the card shows its empty state (the screen already handles this).
   No placeholder data in production, no "sample" rows left in the database.
5. **Secrets live in environment variables / the platform's secret store only.** Never in the
   repository, never in the HTML, never in a chat message. If you need a key, tell the owner
   where to paste it; do not ask them to send it to you.
6. **No customer data.** This system stores no names, emails, phone numbers, order numbers or IP
   addresses of the site's visitors. URLs are stored without query strings. Account, checkout
   and order pages are never measured by the real-user collector (§7.7).
7. **Be a polite client of the monitored site.** One probe round per minute, a distinct
   `User-Agent`, hard timeouts, no parallel load beyond what §7 defines. Never run load tests.
8. **When something external blocks you** (a key is missing, an API refuses, a host is not
   reachable from your sandbox), stop that item, say exactly what is missing and who can
   provide it, and continue with the parts that do not depend on it.

### How to talk to the owner

The owner is not a developer. Unless they tell you otherwise:

- Write to them in **Hebrew**, in short messages and plain words. No technical terms; if one is
  unavoidable, explain it in half a sentence.
- **One decision per message.** A question states what happens if the answer is yes, what happens
  if it is no, and whether it can be changed later.
- Every time you introduce something new, say three things: what it is, what they need to do with
  it, and what they get out of it.
- End every message with one line: what the owner needs to do now (or "אתה לא צריך לעשות כלום").
- Report results honestly: if a check failed, say so and show which one.

---

## 2. Intake: what to find out before building

Find the answers yourself where you can (open the site, read its sitemap, detect the platform),
then confirm with the owner in one short message per topic. Record the answers in
`site_health.config.json` in the target repo (no secrets in it).

| # | Topic | What you need | How to find it / default |
|---|---|---|---|
| 1 | The site | Public address, e.g. `https://example.co.il` | Ask. Check that `www` and non-`www` resolve and which one is canonical. |
| 2 | Platform | WordPress + WooCommerce, Shopify, other | `/wp-json/` answers → WordPress; `/wp-json/wc/store/v1/products?per_page=1` answers → WooCommerce; `/products.json?limit=1` answers → Shopify. |
| 3 | Probe pages (default 4) | The pages checked every minute, each with a short Hebrew name | Default for a shop: home (`בית`), one category, one product, the cart. For a non-shop: home plus the 3 pages that earn the most. Pick pages that exercise different parts of the server (cached and uncached). The home page must be one of them and its name goes into `SH_CONFIG.homePage`. |
| 4 | Core pages (default 5) | The pages whose speed is measured every 15 minutes | Default: the probe pages plus one more important page (for a shop: checkout or a second category). Only pages that are reachable without logging in or filling a cart. |
| 5 | Who gets alerts | The people who should get a push on their phone | Each installs the ntfy app and subscribes to one topic (§7.9). Ask who. |
| 6 | Who may view | Owner; staff; outside vendors (read-only); a share link | Default: owner only. Offer the vendor role when the owner mentions an agency or a developer. |
| 7 | Hosting | Where the database and the small server will run | Default: Supabase (database) + one small always-on web service (for example Render). If the owner already has a dashboard project on some stack, the screen is added to it. |
| 8 | Alert rule for "down" | Alert on the first failed check, or only after 2 in a row | Production default is 1 (the owner wanted to know about every blip). Explain the trade-off: 1 = more noise, nothing missed. |
| 9 | Google key | A PageSpeed Insights API key (free) | The owner creates it in Google Cloud and pastes it into the host's environment settings. Without it the speed cards stay in their empty state. |

Do not ask the owner about thresholds, colors, wording, cadences or anything else defined in this
document. Those are decided.

---

## 3. What the system does

```
 monitored website  <──── probes, speed tests, catalogue + sitemap reads, certificate check ────  collectors
        │                                                                                              │ write
        └── visitors' browsers send one tiny speed measurement per page view ──────► ingest ──►   database
                                                                                                       │
                              alert rules (every minute) ──► push to phones (ntfy) ◄──────────────────┤
                                                                                                       │ read functions
                                                                              small server: login, roles, JSON
                                                                                                       │
                                                                                         the screen (one HTML file)
```

Collectors and their cadence (all times are the site's local time zone):

| Flow name (exact Hebrew, used on the screen) | What it does | Cadence |
|---|---|---|
| `בודק זמינות האתר` | requests every probe page, records ok / HTTP status / time to response | full round every minute; light round at the half minute |
| `מדידת מהירות — עמודי ליבה` | lab speed test (Google PageSpeed Insights) of each core page | phone: every 15 minutes; desktop: every hour |
| `מדידת מהירות — סבב כל האתר` | lab speed test of every page of the site, in rotation | 2 pages every 5 minutes (phone) |
| `טעינת מפת האתר` | reads the sitemap so the rotation knows every page | once a night |
| `בדיקת תעודת האבטחה` | reads the TLS certificate's expiry | once a day |
| `בדיקת מוצרים שבורים` | reads the public catalogue; flags products without price / image / stock / add-to-cart | once a day at 04:00 (shops only) |
| `מהירות אצל לקוחות` | real visitors' browsers report time to main content | every page view |
| alert rules | open / close alerts, send pushes, keep the message log | every minute |

The thresholds below are used everywhere (screen, alerts, texts). Do not change them.

| Measure | Green | Yellow | Red |
|---|---|---|---|
| Server response of a probe ("now" tiles) | ≤ 500 ms | ≤ 1500 ms | > 1500 ms, or the page did not answer |
| Time to main content, LCP (lab and real users) | ≤ 2000 ms "מצוין", ≤ 2500 ms "מהיר" | ≤ 4000 ms "בינוני" | > 4000 ms "איטי" |
| Certificate days left | ≥ 30 | 14–29 | < 14, or the check failed |
| Measurement flow | `תקין` | `מתעכב` | `שקט` (grey: `אין נתון`) |

Definitions that the texts on the screen promise (keep them true):

- **Availability** = share of full-round checks that answered correctly. Light rounds are not counted.
- **Outage (נפילה)** = 3 or more consecutive minutes in which **no** probe page answered.
- **Alert opens** when: one availability check fails (or N in a row, intake #8); a core page is
  slower than 4 seconds twice in a row; a measurement flow stops; the certificate has fewer than
  14 days left. **It closes by itself** when the condition clears.
- **"ראיתי" (✕)** hides an open alert from the red bar for everybody until that alert closes. It
  does not close it. If the problem comes back later, that is a new alert and it shows again.

---

## 4. Per-site configuration

Everything site-specific sits in two places.

**4.1 The screen: `SH_CONFIG`** (defaults are at the top of the script in `site_health.html`; the
server overrides them by injecting one inline script at the `<!--SH_INJECT-->` marker in `<head>`):

| Key | Meaning | Default |
|---|---|---|
| `siteLabel` | shown under the title and in the tab title | `'example.co.il'` |
| `brand` | small text at the top (business or system name); empty = none | `''` |
| `homePage` | the value of `page` for the home page, exactly as the data returns it | `'בית'` |
| `probeCount` | number of probe pages (used in explanation texts only) | `4` |
| `coreCount` | number of core pages (used in explanation texts only) | `5` |
| `liveHosts` | values of the real-user source that mean "the live site" | `['live', siteLabel, 'www.' + siteLabel]` |
| `pathLabels` | URL path prefixes turned into readable Hebrew labels | WooCommerce: `[['/product-category/','קטגוריה: '],['/product/','מוצר: ']]`; Shopify: `[['/collections/','קטגוריה: '],['/products/','מוצר: ']]` |
| `bucketNote` | a note under the "server response per page" drill-down; empty = none | `''` |
| `nav` | menu entries to other screens of the same system; empty = no menu button | `[]` |
| `here` | this screen's path in `nav` | `'/site'` |
| `links` | extra buttons in the top bar | `[]` |
| `api` | base path of the data calls | `'/api'` |
| `loginPath`, `logoutPath` | | `'/login'`, `'/logout'` |
| `shareKey` | share-link token; when set it is appended to every data call as `k=` | `''` |
| `hide` | ids of cards that do not apply to this site: `'issuesCard'` (a site that sells nothing), `'slowCard'` (no sitemap rotation) | `[]` |

and the viewer's role, `SH_ROLE` (§8): `{}` for owner and staff, `{readonly: true}` for a vendor,
`{readonly: true, noAlerts: true}` for a vendor who must not see alerts, `{share: true}` for the
share link. The role object only hides controls; **the server enforces the same rules itself**.

**4.2 The backend:** probe pages, core pages, time zone, alert rule, ntfy topic, PageSpeed key,
passwords. In the reference implementation these are rows in `sh_pages` plus environment
variables (`reference/README.md` lists them).

---

## 5. API contract (binding)

The screen calls five data endpoints (§5.2–§5.6). Field names, types and the literal Hebrew
values below are what `site_health.html` reads; `mock_server.py` returns exactly these shapes.
Your server must return the same.

Conventions:

- All `*_il` fields and `at` strings are **preformatted in the site's local time zone** by the
  backend, as `DD.MM HH:MM` (24-hour). The screen prints them unchanged.
- `bucket` is a local-time string: `YYYY-MM-DD HH:00` for hourly buckets, `YYYY-MM-DD` for daily
  buckets. Rule: a window of at most 72 whole hours (`to − from < 73 hours`, which covers the extra
  minute of §5.1) uses hourly buckets, a longer one daily buckets. The screen tells them apart by
  length (`> 10` = hourly) and reads characters 5–7 (month), 8–10 (day), 11–16 (time).
- Durations are integers in **milliseconds** unless stated. `null` means "no value" and is always
  tolerated; the screen prints `—`.
- Rows are displayed in the order the server sends them. Sort on the server as stated per list.
- Counts, ids, durations and scores are JSON **numbers**. The screen escapes every text field but
  writes numeric fields into the page as they are, so a numeric field must never carry text that
  came from outside (a visitor's beacon, a page of the site).
- The Hebrew literals marked *(literal)* are compared by the screen character for character.

### 5.1 The time window (shared by all calls)

Query parameters: either `h=<hours>` (integer; the screen sends 24, 168, 720 or 2160) or
`f=<YYYY-MM-DD>&t=<YYYY-MM-DD>` (local dates, `t` inclusive: the window ends at the end of day `t`).
Rules (`_range_args` in the production server):

- With `f`: window = `[f 00:00 local, (t + 1 day) 00:00 local)`, by calendar days in the site's
  time zone (a day with a clock change is 23 or 25 hours long). Without `t`: until now. If the end
  is not after the start: end = start + 1 day. Invalid dates: fall back to `h`. `t` without `f` is ignored.
- Without `f`: `h` is clamped to `1 … 9600` (400 days); missing or not a number → 24; zero or
  negative → 1. Window = `[now − h hours, now + 1 minute)` in real elapsed hours.
- `hours` in the answer is the real length of the window in whole hours.

### 5.2 `GET /api/site?strategy=mobile|desktop&(h | f,t)` → everything the screen needs

```jsonc
{
  "hours": 24, "from": "<ISO 8601>", "to": "<ISO 8601>", "strategy": "mobile",

  "availability": [
    // one row per probe page; sort: the order of the probe pages in the configuration
    { "section": "לפי עמוד",            // (literal)
      "page": "בית", "checks": 1440, "failed": 2,
      "fail_pct": "0.14",               // number or string, already rounded to 2 decimals; printed + "%"
      "p50_ms": 284, "p95_ms": 870,     // percentiles of response time over the checks that answered
      "last_fail_il": "13.11 09:41" },  // null if no failure in the window
    // then one row per outage; any section value other than "לפי עמוד" marks an outage. Sort: oldest first
    { "section": "נפילות", "outage_minutes": 7, "outage_start_il": "13.11 03:12", "outage_end_il": "13.11 03:19" }
  ],

  "availability_series": [              // one row per bucket that has checks; sort: bucket ascending
    { "bucket": "2026-11-13 09:00", "checks": 240, "failed": 1, "ms_p50": 310, "ms_p95": 900 }
  ],

  "speed": [
    // exactly one "bottom line" row: the home page on a phone, whatever `strategy` is
    { "section": "שורה תחתונה",          // (literal)
      "page": "בית", "url": "https://example.co.il/", "lcp_p50": 2310, "checks": 96,
      "verdict": "מהיר" },              // מצוין | מהיר | בינוני | איטי, by the LCP thresholds of §3; null without runs
    // one row per core page AND per strategy (send both strategies; the screen filters)
    { "section": "ליבה",                // (literal)
      "strategy": "mobile", "page": "בית", "url": "https://example.co.il/",
      "lcp_p50": 2310, "lcp_p95": 3900, "score_med": 64, "cls_med": 0.03, "ttfb_p50": 420,
      "slow_runs": 3,                   // successful runs with LCP > 4000 ms
      "checks": 96,                     // successful runs in the window
      "crux_category": "FAST",          // FAST | AVERAGE | SLOW | null — Google's real-user verdict from the latest run
      "crux_lcp": 2100 },               // ms, or null
    // up to 10 rows: the heaviest pages of the whole-site rotation; sort: lcp_p50 descending
    { "section": "האיטיים באתר",         // (literal)
      "page": "https://example.co.il/product/x/",   // the URL again; the screen shortens it for display
      "url":  "https://example.co.il/product/x/",
      "lcp_p50": 7100, "score_med": 21, "checks": 2, "last_il": "13.11 08:10" },
    // exactly one coverage row (column names are reused, this is not a typo)
    { "section": "כיסוי",               // (literal)
      "checks": 288,                    // distinct pages measured by the rotation in the window
      "slow_runs": 412 }                // number of pages the rotation knows (from the sitemap)
  ],

  "speed_series": [                     // for the requested strategy only; one row per core page per bucket
    { "page": "בית", "url": "https://example.co.il/", "bucket": "2026-11-13 09:00", "lcp_p50": 2400 }
  ],

  "alerts_open": [                      // every alert that is open now; sort: newest first
    { "id": 41, "kind": "down", "title": "האתר לא עונה: סל",
      "body": "קוד 502\nhttps://example.co.il/cart/",   // plain text; a URL in it becomes the "open the page" link
      "opened_il": "13.11 11:02",
      "acked": false }                  // true = someone pressed ✕; hidden from the red bar, still counted as open
  ],
  "alerts_recent": [                    // alerts that were open at any time inside the window; sort: newest first
    { "id": 38, "kind": "down", "title": "…", "body": "…", "open": false,
      "opened_il": "13.11 01:20", "closed_il": "13.11 01:27",   // closed_il null while open
      "minutes": 7 }                    // duration so far (open) or total (closed)
  ],

  "health": [                           // one row per measurement flow of §3; sort: the order of §3
    { "flow_name": "בודק זמינות האתר",   // (literal for this one: the subtitle shows its last_at)
      "status": "תקין",                 // תקין | מתעכב | שקט | אין נתון  (literals)
      "cadence": "כל דקה",              // free text
      "silent_txt": null,               // short text when not ok, e.g. "שקט כבר 6 שעות"
      "last_at": "<ISO 8601>",          // last successful run; null if never
      "warn_minutes": 5, "late_minutes": 15,   // age above warn = מתעכב, above late = שקט
      "note": null }                    // shown in the drill-down when the screen has no built-in text for flow_name
  ],

  "product_issues": [                   // from the latest catalogue snapshot only; sort: "לא במלאי" last, then by issue, then name
    { "issue": "לא במלאי",              // "לא במלאי" (literal, shown yellow); any other text is shown red
      "name": "ספה תלת מושבית", "url": "https://example.co.il/product/…/", "snap_date": "2026-11-13" }
  ],

  "cert": { "host": "example.co.il", "issuer": "Let's Encrypt R11", "not_after": "<ISO 8601>",
            "days_left": 23, "ok": true, "err": null, "checked_at": "<ISO 8601>" }   // or null before the first check
}
```

**Each part fails alone.** The eight lists and `cert` are nine parts, computed independently and
in parallel; if one fails, its key holds `{"error": "<text>"}` instead of its value, and the rest
of the answer is still returned with status 200. The screen treats a non-list as empty. Error
texts must not contain host names, user names or keys.

Issue labels used in production: `בלי מחיר`, `בלי תמונה`, `לא במלאי`, `אי אפשר להוסיף לסל`.

### 5.3 `GET /api/site/now` → the "עכשיו" card (refreshed every 60 s)

```jsonc
{
  "pages":  [ { "page": "בית", "url": "https://example.co.il/", "ok": true, "status": 200, "ms": 240 } ],
            // the last FULL round, one row per probe page; ms is null when the page did not answer.
            // Empty when there was no full round in the last 15 minutes.
  "latest": [ { "page": "בית", "ok": true } ],   // the most recent round of any kind (full or light); at least page + ok.
                           // Also empty when that round is older than 15 minutes: stale data must not read "פעיל"
  "light": false,          // true when `latest` is a light round
  "all_ok": true,          // every page of `latest` answered (false when `latest` is empty)
  "any_ok": true,          // at least one page of `latest` answered
  "age_sec": 12,           // integer seconds since `latest`; null when older than 15 minutes
  "rum":   { "n": 143, "p75_ms": 3120 },          // real-user LCP, last hour, live site only, test rows excluded; n = 0 → "no data"
  "speed": { "lcp_ms": 2500, "score": 63, "checked_at": "<ISO 8601>" },   // latest successful lab run, home page, phone; {} if none
  "alerts_open": 3,        // count of open alerts, seen ones included (after role filtering)
  "rum_src": { "n": 1000,                           // the last 1000 real-user rows: where they came from
               "hosts": [ { "host": "live", "n": 964 }, { "host": "staging.example.co.il", "n": 36 } ],
               "cols": ["created_at", "is_test", "lcp_ms", "path", "site"],   // diagnostic only
               "test": 12 }                         // how many of them are flagged as test. null when unavailable
}
```

On failure: status 502 with `{"error": "<text>"}`; the screen writes "לא הצלחתי לטעון את "עכשיו"".
For a vendor or a share link `alerts_open` is recounted from the filtered list of open alerts
(§8.2); if that second read fails the answer is 502, never a false 0.

### 5.4 `GET /api/site/drill?what=…&(h | f,t)` → drill-downs; always `{"rows": [...]}`

| `what` | extra parameters | each row |
|---|---|---|
| `fails` | `page` (optional), `bucket` (optional) | `{ "at_il": "13.11 09:41", "page": "סל", "kind": "קוד 502", "err": "<technical text or null>", "ms": 812 }` — the failed checks of full rounds (the same checks the availability numbers count), newest first, **at most 500**. `kind` is a short Hebrew reason: `לא ענה בזמן`, `קוד <status>`, `שגיאת חיבור`, `תוכן לא צפוי`. `ms` = time until the failure, or null. |
| `bucket` | `bucket` (required) | `{ "page": "בית", "checks": 60, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "13.11 09:17" }` — one row per probe page for that hour/day. |
| `runs` | `url` (required), `strategy`, `bucket` (optional) | `{ "ok": true, "err": null, "at_il": "13.11 10:45", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410, "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": [ { "id": "render-blocking-resources", "title": "…", "ms": 600 } ] }` — the individual lab runs of one page (every run of that URL and strategy in the window), **newest first**; a failed run is `{ok: false, err, at_il}`. `opps` = what slows the page, with the estimated saving in ms; it is filled only on the newest 100 successful runs and is `[]` on older ones (it is nine tenths of a run's size, and the sheet's "what slows the page" should describe the page as it is now). |
| `alert` | `id` (required) | one row: the `alerts_recent` fields plus `"fails": [ { "at": "13.11 11:02", "page": "סל", "status": 502, "err": null } ]` (the failed checks behind a `down` alert, oldest first, at most 500; `status` is present only when the failure was an HTTP status, because the sheet prints "קוד <status>" whenever it is there; otherwise `err` carries the reason) and `"sent": [ { "event": "open", "status": 200, "at": "13.11 11:02" } ]` (pushes with a final result; `event` is `open` or `close`; `status` 200 = accepted by the push service). |

Unknown `what`: status 400 `{"error": "what?"}`. A missing or malformed required parameter (`id`
not a number, `url` empty, `bucket` not in one of the two bucket formats): `{"rows": []}`.
Backend failure: status 502 `{"error": "<text>"}`.

### 5.5 `GET /api/messages?(h | f,t)` → the push log; `{"rows": [...]}`, newest first

`{ "kind": "התראה", "title": "…", "msg": "…", "at_il": "13.11 11:02", "sent": true }` — `kind` is
`התראה` (shown red), `חזר לתקין` (green) or any other label such as `בוקר` (grey). `sent: false`
adds "לא נשלחה".

### 5.6 `POST /api/alerts/ack` → "ראיתי"

Body `{"ids": [41, 40]}` or `{"id": 41}`. Ids may arrive as numbers or as digit strings; only the
first 200 are processed. Marks each open, not yet seen alert as seen by the current user (the
user's label is stored). Answer `{"ok": true, "n": <alerts actually marked>}`; a body without a
usable id → 400 `{"error": "bad request"}`.
The screen removes the rows at once and only reloads if the call fails.

### 5.7 Errors and caching

- Not logged in (and no valid share token): **401** `{"error": "auth"}` on every data call. The
  screen then goes to `loginPath` (or shows a message in share mode).
- Role not allowed: **403** `{"error": "auth"}`.
- Data answers: `Cache-Control: no-store`. The HTML page: `Cache-Control: no-cache, must-revalidate`.

---

## 6. The screen (binding)

`site_health.html` implements all of this. The section exists so you can review a change against
it, and so you know what must stay true if the target project forces you to move the screen into
another framework. In that case port it one to one and make `check_screen.js` pass.

### 6.1 Layout, top to bottom

1. Header row: brand text (start side), "יציאה" link (end side).
2. Top bar: menu button (only when `nav` is not empty), the name "בריאות האתר", then buttons:
   extra `links`, `הסברים`, `רענון`, `ייצא PDF`.
3. **Red alert bar** — only when there are open alerts nobody marked as seen (§6.4).
4. Title "בריאות האתר" and subtitle `<siteLabel> · הבדיקה האחרונה HH:MM · <period>`.
5. Card **עכשיו** — four tiles and a row of chips (§6.2).
6. Card with the **controls**: period `24 שעות | 7 ימים | 30 יום | 90 יום`, strategy `טלפון | מחשב`,
   a custom date range (`מתאריך`, `עד`, `הצג`), and the line `מוצג: <period>`.
7. Card **שורה תחתונה** — four tiles: `מהירות עמוד הבית בטלפון`, `זמינות`, `נפילות`, `התראות פתוחות`.
8. Card **זמינות** — per-page table, list of outages, chart (red bars = failed checks, green line = median response time).
9. Card **מהירות לאורך זמן** — legend of pages (tap to hide/show a line), line chart of median LCP per bucket with dashed reference lines at 2.5 s and 4 s.
10. Card **העמודים העיקריים** — table of the core pages for the chosen strategy.
11. Card **העמודים הכבדים באתר** — coverage line + the 10 heaviest pages.
12. Card **מוצרים שבורים באתר** — counts per issue + table (first 60).
13. Card **תעודת האבטחה (המנעול)** — days left + state.
14. Card **התראות** — folded by default; the alerts of the period.
15. Card **הודעות שנשלחו לטלפון** — folded by default; the push log.
16. Card **המדידה עצמה** — one line per measurement flow with its state.

Every card has a hidden explanation paragraph; the `הסברים` button shows them all. Keep each
explanation true: if you change a cadence or a rule, change its sentence.

### 6.2 The "עכשיו" card

| Tile | Value | Color | Small line |
|---|---|---|---|
| `האתר עכשיו` | `פעיל` / `חלקי` / `נפל` / `אין נתון` | green if `all_ok`, yellow if only `any_ok`, red if none, grey without data | `נבדק לפני N שניות` (or `N דקות` from 90 s) `· בדיקה קלה` when `light` `· X מתוך Y עמודים עונים` |
| `תגובת שרת עכשיו` | home page `ms` as seconds (`0.24 שנ'`), `לא עונה` when it failed, `—` when there is no round at all | §3 thresholds; grey without data | `דף הבית · הכי איטי כרגע: <page> <time>` |
| `מהירות אצל לקוחות, שעה אחרונה` | `rum.p75_ms` as seconds, or `—` | LCP thresholds | `N צפיות בשעה האחרונה · אחוזון 75` + the source line: `מקור: האתר החי · כל N המדידות האחרונות`, or in warning color the list of sources when any row came from somewhere else; `· מתוכן N מדידות בדיקה` when there are test rows |
| `מעבדה, מדידה אחרונה` | `speed.lcp_ms` as seconds | green ≤ 2.5 s, yellow ≤ 4 s, red above | `דף הבית בטלפון, HH:MM · ציון N · יעד 2.5` |

Below: one chip per probe page (`<page> <time>` or `<page> לא עונה (status)`), colored by the
server-response thresholds; then `עודכן HH:MM:SS · רענון אוטומטי כל 60 שניות · N התראות פתוחות`.
The card reloads every 60 seconds on its own timer, also while a drill-down is open.

### 6.3 Interactions

Everything that shows a number is clickable and opens a **sheet** (bottom sheet on a phone, a
centered 720 px panel from 720 px width; closes with ✕, a click outside, or Escape):

| Click on | Opens | Data call |
|---|---|---|
| tile `מהירות עמוד הבית בטלפון` | the home page's lab runs | `what=runs&url=<bottom.url>` |
| tile `זמינות` | all failed checks + split per page | `what=fails` |
| tile `נפילות` | the outages of the period | none |
| tile `התראות פתוחות` | list of the period's alerts; each opens its detail | `what=alert&id=` |
| a row of the availability table | that page's failed checks | `what=fails&page=` |
| a red bar of the availability chart | the failed checks of that hour/day | `what=fails&bucket=` |
| a point on the green line | response time per page in that hour/day | `what=bucket&bucket=` |
| a point of the speed chart | that page's runs in that hour/day | `what=runs&url=&bucket=` |
| a row of the core / heavy tables | that page's runs + "מה מאט את העמוד" | `what=runs&url=` |
| an alert (bar, card, list) | the alert: timing, what it means, failed checks, pushes sent | `what=alert&id=` |
| a row of `המדידה עצמה` | what the flow measures and what to do | none |

The runs sheet shows: count, median, slowest, fastest, Google's real-user verdict when present,
then the top 6 reasons by average estimated saving, then the table of runs (first 100).

The main screen reloads every 60 seconds, **except while a sheet is open**. A reload that returns
after a newer one started is discarded (sequence guard). While loading, a thin progress bar and a
pill "טוען נתונים…" show, and the cards dim.

### 6.4 The red alert bar

- Shown only for open alerts with `acked == false`. Text: `⚠ N התראות פעילות` (or `התראה פעילה`).
- **Collapsed by default, even for one alert.** Once opened it stays open across refreshes.
- Each row: checkbox, title, body (URLs replaced by readable page names, lines that repeat the
  title dropped) + `· מאז <opened_il>`, a link `לפתוח את העמוד ↗` when the body contains a URL, and ✕.
- Above the list: `לסמן הכול` and `מחק מסומנות (N)`.
- ✕ or bulk delete removes the rows **immediately**, without reloading the screen and without
  folding the list; the request is sent in the background; on failure the rows come back.

### 6.5 Controls

- A period button sets `h` and clears the custom dates. `הצג` needs a start date; an empty end
  date means today; reversed dates are swapped.
- `טלפון` / `מחשב` changes only the speed figures. Availability is the same for both.
- `ייצא PDF` calls the browser's print. The print stylesheet (A4 landscape) hides the controls
  and unfolds everything: all alerts, all table rows, folded cards open.

### 6.6 Look

- Hebrew, right to left. Numbers in tables are left-aligned, LTR, tabular figures.
- Phone first: max width 900 px, cards with 14 px radius, touch targets at least 44 px high.
- Light and dark by `prefers-color-scheme`; the colors are CSS variables at the top of the file.
- No element may cause horizontal scrolling on a phone; wide tables scroll inside their card.
- System font stack. No web fonts, no external requests at all.

### 6.7 Roles on the screen

| `SH_ROLE` | Effect |
|---|---|
| `{}` | everything |
| `{readonly: true}` | no ✕, no checkboxes, no bulk delete, no message-log card, no menu, no extra links |
| `{readonly: true, noAlerts: true}` | also no red bar, no alerts card, no `התראות פתוחות` tile |
| `{share: true}` | as read-only, and no "יציאה" link |

### 6.8 Translations of "what slows the page"

The runs sheet translates PageSpeed audit ids to plain Hebrew through the `OPP` table in the
script. An id that is not in the table falls back to the `title` the backend stored. Request
PageSpeed results with `locale=he` so that fallback is Hebrew too (§7.6).

### 6.9 What you may change in `site_health.html`

- Values of `SH_CONFIG` (or inject them from the server).
- Explanation sentences, when a cadence or rule really differs on this site.
- Entries of the `OPP` table and of the flow explanations in `drillHealth`.
- The color variables, if the owner asks for their brand color (`--brand`).

A card that does not apply to the site is hidden with `SH_CONFIG.hide` (§4.1), never by deleting
its markup: the script expects every card to exist.

Anything else: do not change. If you believe something must change, ask the owner first.

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
**100**, which covers the screen's longest preset of 90 days; four pages cost about 0.8 MB of
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
  nothing) are not returned. `silent_txt`: `מאחר ב-<span>` while late, `שקט כבר <span>` when silent,
  where span is `N דקות` under two hours, `N שעות` under two days, else `N ימים`.
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
| `sh_config()` | the configuration as one object: every setting loaded by `sh_setup` (`site`, `host`, `label`, `time_zone`, `platform`, `down_after`, `morning`, `keep_days`, `rum_hosts`, `private_paths`, …), `pages` (`[{name, url, probe, core, home, expect}]` in display order) and `screen` (the object the server injects as `SH_CONFIG`, §4.1) | the object. Before `sh_setup` ran it has no `time_zone`; the server then answers 502 "the site is not configured" |
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
| `sh_cleanup()` | applies the retention rules | rows deleted per table |

`sh_alerts_check` must be safe when two workers overlap for a minute during a deploy: no alert
and no message is created twice, and a message returned to one caller is not returned to another
for the next two minutes (the claim). It assumes the default `READ COMMITTED` isolation.

### 7.5 Collector: availability probe (`בודק זמינות האתר`)

- **Full round** at the top of every minute: request every probe page concurrently. `GET`, a fresh
  connection, follow up to 5 redirects, timeout **10 seconds**, `User-Agent: SiteHealthProbe/1.0
  (+<dashboard address>)`, `Cache-Control: no-cache`.
- A check is **ok** when the final status is 200 within the timeout (and, if the page has an
  `expect` text, the first 200 KB of the body contain it). Otherwise `fail` is `timeout`, `http`
  (with the status), `connect` (DNS, TLS, reset) or `content`.
- `ms` = time from sending the request until the response headers of the final response arrive
  (what a new visitor's first request waits for). Read the body only when `expect` is set.
- **Light round** at second 30 of every minute: the same requests with a 5-second timeout,
  stored with `kind = 'light'` and `ms = null`. It feeds only the "now" tile and faster alerting.
  Never count it in availability or response-time statistics.
- All rows of a round share one `round_at` (the scheduled second, not the completion time).
- Run the prober from a region near the site's visitors; the server-response thresholds of §3
  assume it (a prober on another continent will paint everything yellow).
- The probe is one client in a data center. It tells you the server answers, not how fast the
  page loads for a visitor. The screen says so; do not present it as more.

### 7.6 Collector: lab speed (`מדידת מהירות`)

Google PageSpeed Insights API v5, one call per page per strategy:

`GET https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=<page>&strategy=mobile|desktop&category=performance&locale=he&key=<PAGESPEED_KEY>`

- **A key is required.** Calls without a key are refused (HTTP 429, daily limit 0). The key is
  free and needs no billing account. The owner creates it: Google Cloud Console → pick or create
  a project → APIs & Services → Library → "PageSpeed Insights API" → Enable → Credentials → Create
  credentials → API key; then restrict the key to that API only. Do not set an HTTP-referrer
  restriction (a server sends no referrer). Default quota: 25,000 calls a day and 240 a minute per
  project; the project's Quotas page is the authority.
- **Always send `strategy`** (the API's default is desktop) and `category=performance` (other
  categories only make the call slower).
- A call takes 10–60 seconds. Connect timeout 10 s, read timeout 120 s, one call at a time, and
  never let this collector block the probe (separate thread / job).
- Errors: 429 whose message mentions "per day" → stop until tomorrow; other 429 and 5xx → retry
  after 5, 10, 20 seconds, at most 3 tries; 400 "API key not valid" → a configuration error: do
  not retry, log it clearly, and let the flow go `שקט`. A failure of the test itself (HTTP 500
  "Lighthouse returned error: …", or `lighthouseResult.runtimeError` on a 200) is stored as a run
  with `ok = false` and the error text. Failed runs never count in medians.
- Store per run (a missing value is null, never 0; do not store the raw answer, it is huge):

| Column | From the answer |
|---|---|
| `score` | `lighthouseResult.categories.performance.score × 100`, rounded (the score can be null) |
| `lcp_ms` | `lighthouseResult.audits["largest-contentful-paint"].numericValue`, rounded |
| `cls` | `lighthouseResult.audits["cumulative-layout-shift"].numericValue`, 3 decimals |
| `ttfb_ms` | `lighthouseResult.audits["server-response-time"].numericValue`, rounded (fallback: `audits.metrics.details.items[0].timeToFirstByte`) |
| `bytes` | `lighthouseResult.audits["total-byte-weight"].numericValue` |
| `crux_category` | `loadingExperience.metrics.LARGEST_CONTENTFUL_PAINT_MS.category` (`FAST` / `AVERAGE` / `SLOW`) |
| `crux_lcp_ms` | `loadingExperience.metrics.LARGEST_CONTENTFUL_PAINT_MS.percentile` (75th percentile, ms) |
| `lh_version` | `lighthouseResult.lighthouseVersion` (for diagnosing a sudden change in the numbers) |
| `opps` | up to 8 reasons with an estimated time saving, largest first: `[{id, title, ms}]` (rule below) |

- **Real-user data is optional.** A page with little traffic has no `loadingExperience.metrics`.
  When `loadingExperience.origin_fallback` is true the numbers describe the whole site, not this
  page: store null for both `crux_*` columns in that case. The screen then says "אין מספיק תנועה".
- **`opps` rule** (works for old and new Lighthouse versions). For every audit in
  `lighthouseResult.audits`, except the metric audits themselves:
  1. skip it when `scoreDisplayMode` is `notApplicable`, `manual` or `error`, or when `score` is
     null or ≥ 0.9 (it passed; note that `server-response-time` reports a "saving" even when it passes);
  2. its saving in ms = `details.overallSavingsMs` if present; otherwise the largest of
     `metricSavings.LCP`, `.FCP`, `.TBT`, `.INP`; otherwise `numericValue` when `numericUnit` is `millisecond`;
  3. keep it when the saving is > 0. `title` is the audit's `title` (Hebrew, because of `locale=he`).

  Since Lighthouse 13 (in PageSpeed from October 2025) most classic audits (`modern-image-formats`,
  `render-blocking-resources`, …) no longer exist; they were replaced by `…-insight` audits
  (`image-delivery-insight`, `render-blocking-insight`, …) that have no `overallSavingsMs`. A
  collector that only looks for `details.type == "opportunity"` silently loses images, caching,
  fonts and render blocking. The screen's `OPP` table knows both generations and shows the stored
  `title` for any id it does not know.
- **Core pages:** every 15 minutes all core pages with `strategy=mobile`; once an hour with
  `strategy=desktop`. **Rotation:** every 5 minutes, 2 pages from `sh_rotation_next(2)`, phone only.
  With 5 core pages that is about 1,200 calls a day.
- Without `PAGESPEED_KEY` the collector does not run and says so in its log once; the speed cards
  show their empty states and the flows stay `אין נתון`.
- What the numbers mean (the screen says this too): the phone test simulates a mid-range phone on
  a slow 4G connection, measured from a Google data center, so it is harsher than what most
  visitors see and single runs are noisy. Verdicts and alerts therefore use medians and
  "twice in a row", never one run. A site behind bot protection may block Google's test; that
  shows up as failed runs with a 403 in the error text.

### 7.7 Collectors: sitemap, catalogue, certificate, real users

Two rules are shared by the sitemap and the catalogue reads: **read everything, prove it is
complete, and only then replace what is stored**; and a firewall page is not data (require a real
sitemap root tag / a JSON content type, otherwise the run failed).

**Sitemap (`טעינת מפת האתר`)**, nightly.

1. Find it: every `Sitemap:` line of `/robots.txt`; if there is none try `/sitemap_index.xml`,
   `/wp-sitemap.xml`, `/sitemap.xml`, and take the first that parses as `<sitemapindex>` or `<urlset>`.
2. Follow index files (at most 500 files, 50 MB each after decompression). Decide gzip by the
   first two bytes (`1f 8b`), not by the file name. Refuse documents that contain `<!ENTITY`.
3. From each `<url>` take only its **direct child** `<loc>` (SEO plugins nest `<image:loc>` inside;
   those are pictures, not pages). Child sitemap addresses are followed exactly as written,
   including their query strings.
4. Keep page URLs on the site's own host (with or without `www`); drop any page URL that has a
   query string or a fragment; drop non-HTML files; drop cart, checkout, account, search, feed,
   tag, author and paginated pages by their **first path segment** after decoding (shop slugs are
   often translated: take the real slugs from the site, not only the English words). Always
   include the home page.
5. If any file fails to load or parse, abort the whole load and keep yesterday's list. Refuse an
   empty list, and refuse a list smaller than half of the current one (that is almost always a
   fetch problem). Then hand the full list to `sh_sitemap_set` in one call.

The rotation measures 2 pages every 5 minutes = 576 pages a day. When the site has more pages,
raise it up to 6 per round (1,728 a day); beyond that tell the owner and reword the sentence
"כל האתר בערך פעם ביום" on the screen. The coverage line shows the truth either way.

**Broken products (`בדיקת מוצרים שבורים`)**, daily at 04:00, shops only.

- WooCommerce: page through
  `GET <site>/wp-json/wc/store/v1/products?per_page=100&page=N&orderby=id&order=asc` (public, no
  key; 100 is the maximum; the fixed order keeps pages stable while the shop changes). The total
  is in the `X-WP-Total` header. Per product:

  | Label | Condition |
  |---|---|
  | `בלי מחיר` | `prices.price` is empty or `"0"` **and** `is_purchasable` is false (a product without a price comes back as `"0"`, not empty; a free product stays purchasable) |
  | `בלי תמונה` | `images` is an empty list |
  | `לא במלאי` | `is_in_stock` is false |
  | `אי אפשר להוסיף לסל` | `is_purchasable` is false while the product is in stock and has a price; never for `type` `external` or `grouped` (they are never purchasable, by design) |

  A product can have more than one label. Names arrive with HTML entities: unescape them before
  storing. If the shop hides out-of-stock products from its catalogue, they are not in the answer
  and `לא במלאי` never appears; that is the shop's setting, not a fault of the check.
- Shopify: `GET <site>/products.json?limit=250&page=N` until an empty page (an unofficial but
  public endpoint: no total, so cross-check the count against the product sitemap). No variant
  with `available` → `לא במלאי`; no `images` → `בלי תמונה`; every variant priced 0 or empty → `בלי מחיר`.
- Other platforms: disable the flow and hide the card (`SH_CONFIG.hide = ['issuesCard']`).
- **Never store a partial snapshot.** Abort and keep yesterday's data when the number of products
  read differs from the declared total, when the total header is missing, or when ids repeat. A
  partial read looks exactly like products that vanished.
- Rows are returned with the real faults first and `לא במלאי` last, because the screen shows only
  the first 60. "Out of stock" is not always a fault, but a visitor who sees it leaves; that is
  why it is listed, in yellow.

**Certificate (`בדיקת תעודת האבטחה`)**, daily. Open a TLS connection to `<host>:443` with normal
verification, read `notBefore` / `notAfter` / issuer, store `days_left`. A failed check stores
`ok = false` with the error and does not beat the flow.

**Real users (`מהירות אצל לקוחות`)**. A small script on the site (`reference/rum/site-health-rum.js`)
measures LCP with the browser's `PerformanceObserver` and sends one beacon per page view when
the page is hidden or left: a JSON **string** through `navigator.sendBeacon`, which goes out as
`text/plain` and therefore needs no CORS preflight and no CORS headers (never send it as
`application/json`: Chrome refuses, other browsers preflight). Fields: `site`, `path`, `lcp`
(ms), `test`, plus `ttfb` and `nav`, which the reference does not store. `site` is the literal
`live` on the production host and the host name anywhere else, so traffic from a staging copy is
visible as such on the screen.

The ingest endpoint is **`POST /m`** (a neutral name: content blockers drop paths called "rum" or
"beacon"). It is public, so every field is hostile:

- read the raw body (it is `text/plain`; a JSON body parser will not see it), at most 1 KB;
- if an `Origin` or `Referer` header is present, its host must be the site's host (with or
  without `www`) or one of the extra hosts in the configuration (`rum_hosts`, for a staging copy);
  when both are absent, or `Origin` is the string `null` (sites with a strict referrer policy),
  accept the beacon. This is a noise filter, not security: anyone can forge a header;
- keep the row only when `lcp` is between 1 and 60,000 ms, `site` matches `^[a-z0-9.-]{1,100}$`,
  and `path` (query string removed, at most 300 characters) has no segment that names an account,
  checkout, order or admin page; otherwise drop the whole beacon;
- store no IP address, no cookie, no user agent, and ignore any cookie that arrives; limit each
  address to 60 beacons a minute, in memory only;
- always answer 204, also when the beacon is dropped; store after answering, in small batches.

What the tile's count means: page views that were *measured*. Nothing arrives from browsers
without LCP support (Safari and every iPhone browser before iOS 26.2, December 2025), from tabs
opened in the background, or from visitors with content blockers. It is not a traffic counter.
A p75 over a handful of views is noise; the screen shows it anyway, with the count next to it.

Delivery: on WordPress, the one-file plugin `reference/rum/site-health-rum.php` (it prints the
script inline in the footer; copy it to `wp-content/mu-plugins/` or install it as a plugin, set
the two constants, then purge the page cache and exclude the script from "delay JavaScript"
optimizations, or only visitors who interact get measured). On Shopify, paste the script into
the theme layout. Elsewhere, one configuration line and one script tag at the end of the page body. The
script is never loaded for signed-in staff, nor on cart, checkout and account pages.

### 7.8 Alert rules (`sh_alerts_check`, every minute, right after the full probe round)

| Kind | Key | Opens when | Closes when | Title · body |
|---|---|---|---|---|
| `down` | `down:<page>` | the newest `down_after` rounds (full or light, not older than 24 hours) of a probe page all failed. `down_after` = 1 unless the owner chose 2 | the newest round of that page answered | `האתר לא עונה: <page>` · `<reason>\n<url>` |
| `slow` | `slow:<page>` | the two newest successful phone runs of a core page both have LCP > 4000 ms | the newest successful run is ≤ 4000 ms | `עמוד איטי: <page>` · `<x.x> שניות עד התוכן, פעמיים ברצף\n<url>` |
| `silent` | `silent:<flow>` | an enabled flow whose `alerts` flag is on, that has run before, is older than its `late_minutes` | it ran again: a successful run newer than the alert | `המדידה נעצרה: <flow>` · `אין מדידה כבר <N> דקות` |
| `cert` | `cert:<host>` | the last successful check shows fewer than 14 days | 14 days or more | `תעודת האבטחה פגה בעוד <N> ימים` · `<host>` |

- Opening inserts an alert row and a message (`kind` `התראה`, `event` `open`). Closing sets
  `closed_at` and inserts a message (`kind` `חזר לתקין`, `event` `close`, text `נמשך <N> דקות`).
- **The real-user flow never pushes a `silent` alert** (`alerts` off): a small site has no
  visitors for hours every night, and that is not a fault. Its state still shows on the screen.
- An open alert whose subject is gone (the page left the configuration, the flow was disabled,
  the host changed) is closed like any other; otherwise it could never close.
- **Insert, do not upsert.** The unique index on `key` is partial (open alerts only), and an
  upsert with `on conflict (key)` fails against a partial index on the REST interface. Look for an
  open row; insert when there is none.
- Other parts of the owner's system may add their own alert kinds to the same table. The vendor
  role sees only the four kinds above (§8).
- **Morning message**, once a day when the configured time (default 07:30 local) has passed:
  `kind` `בוקר`, priority 2. Title `בוקר טוב: האתר תקין`, or `בוקר טוב: התראה פתוחה אחת` /
  `בוקר טוב: <N> התראות פתוחות`. Lines: `זמינות <P>% ב-24 שעות` (or `אין בדיקות זמינות ב-24 שעות`),
  `נפילות: <N> (<M> דקות)` only when there were outages, `מהירות עמוד הבית: <verdict>` only when
  measured. The figures come from the same functions the screen uses. Besides being useful, it is
  the owner's daily proof that the channel works.

### 7.9 Push notifications (ntfy)

Alerts go to phones through [ntfy](https://ntfy.sh): each person installs the ntfy app and
subscribes to one topic; the system publishes to that topic.

- Publish with a **JSON body to the server root** (not to `/<topic>`), which avoids every
  header-encoding problem with Hebrew:
  `POST https://ntfy.sh/` with `Content-Type: application/json` and
  `{"topic": "<topic>", "title": "<title>", "message": "<body>", "priority": 4, "tags": ["rotating_light"], "click": "<dashboard>/site"}`.
  `priority` is an integer 1–5 and `tags` a list of strings. Keep the title under 200 characters
  and the message under 1,500 (the limits are in bytes and Hebrew letters take two).
- Priorities: `down` and `silent` open → 4; `slow` and `cert` open → 3; "חזר לתקין" and the
  morning message → 2 (no sound on the phone; that is intended).
- Environment: `NTFY_TOPIC`, `NTFY_URL` (default `https://ntfy.sh`), optional `NTFY_TOKEN` (sent as
  `Authorization: Bearer …`, for a reserved topic on a paid plan or a self-hosted server).
- The topic name is the only secret of a free ntfy topic: anyone who knows it can read the last
  12 hours of alerts and publish fake ones. Generate a long random name (`sh-` + 24 random letters
  and digits), keep it in the environment only; never in the repository, on the screen or in logs.
- HTTP 200 means ntfy accepted the message, not that a phone showed it; there is no delivery
  receipt. Record the result of every attempt with `sh_message_sent(id, status)`: a 2xx status
  settles the message as sent; **0 means "pushing is not configured"** and settles it at once as
  not sent; any other status (use 599 for a network error or a timeout) is a failed attempt, and
  the message is offered again on a later minute until 5 attempts have failed. Then it stays in
  the log as "לא נשלחה". The click link (`<dashboard>/site`) is added by the sender; the database
  does not know the dashboard's address.
- **Send at most 30 pushes per rolling hour.** The free server allows 250 a day per sending
  address, and a flapping page with `down_after = 1` can produce two messages a minute. Messages
  that wait longer than an hour are marked as not sent instead of arriving late in a burst.
- Without `NTFY_TOPIC` nothing is sent and every message is settled with status 0.
- Tell the owner two things at hand-over: ntfy keeps messages for 12 hours, so a phone that was
  off longer never gets them (the screen's message log is the permanent record); and iPhones
  deliver ntfy pushes less reliably than Android. If alerts matter and the owner uses an iPhone,
  offer a Telegram bot as the channel instead; the message log and rules stay the same.

### 7.10 Who watches the watcher

If the worker loop dies, nobody evaluates `silent`. Add one independent check; pick the first that
the platform supports:

1. **Database scheduler** (Supabase: `pg_cron` + `pg_net`): every 5 minutes a job runs
   `sh_deadman()`, which, when the newest probe round is older than 10 minutes and no
   `silent:בודק זמינות האתר` alert is open, opens it and publishes straight to ntfy with
   `net.http_post`. `reference/deadman.sql` holds the job; it needs the topic stored in the
   database's secret store.
2. **An external heartbeat service** (for example healthchecks.io): the worker requests the
   service's ping URL after every full round; the service alerts when pings stop.

Also expose `GET /health` on the server, without login: always status 200 with
`{"ok": <the database answered>, "db": "ok" | "<error text without host or key>",
"last_probe_age_sec": <seconds since the last full probe round, or null if there never was one>}`.
Keep it 200 even when the database is down; hosts restart a service whose health check fails,
and a restart loop helps nobody.

### 7.11 Running the collectors inside the database platform instead

On Supabase the collectors can run as scheduled Edge Functions (`pg_cron` calling the function URL
through `pg_net`), which is how the production original keeps measuring even while its dashboard
server restarts. Same functions, same rows, same cadences. If you choose this, keep the worker
loop off (`COLLECTORS=0`), and note that §7.10 then needs option 2 or a second scheduler.

---

## 8. Access

### 8.1 Roles

| Role | How they sign in | Sees | May do |
|---|---|---|---|
| owner | personal password | everything | mark alerts as seen; view the push log |
| staff (optional) | shared or personal password | everything | same as owner on this screen |
| vendor (agency, developer) | a personal password per person | the screen without the push log, alerts of the four site kinds only (or none: `noAlerts`), no list of pushes inside an alert | nothing: read-only |
| share link | `/status?k=<token>` | as vendor | nothing |

### 8.2 Rules (all enforced by the server; the screen's hiding is cosmetic)

- **Deny by default for outsiders.** For vendor and share-link requests use an allow-list: pages
  `/site` (or `/status`), `/login`, `/logout`; data calls `GET /api/site`, `GET /api/site/now`,
  `GET /api/site/drill`. Anything else, including any route added later, answers 403 (data) or
  redirects to `/site` (pages). Every request of theirs that is not a `GET` is refused, except
  the sign-in form.
- **Public routes**, answered before any role check: `GET /health`, `POST /m` (real-user ingest),
  `GET` and `POST /login`, `GET /logout`. `POST /m` ignores cookies entirely.
- Vendor filtering of data: `alerts_open` / `alerts_recent` keep only kinds `down`, `slow`,
  `silent`, `cert`; `sh_now().alerts_open` is recounted after filtering; the alert drill returns
  the alert only if its kind is allowed, with `sent` emptied; with `noAlerts` all alert lists are
  empty, the count is 0 and the alert drill returns no rows.
- The share token is compared in constant time, is accepted **only** on `/status` and the three
  data calls, and never counts as "logged in" anywhere else. An empty configured token disables
  the link. On those four routes, when `k` is present **only the token counts**: a valid one gives
  the share role even to a signed-in owner, a wrong one is refused even with a valid cookie
  (`/status`: 403 with the line `הקישור אינו תקין או שפג.`; data calls: 401). On every other
  route `k` is ignored, so a share link alone gets 401 from `/api/messages` and `/api/alerts/ack`.
- **Passwords** come from environment variables, one per person (`SH_PASS_OWNER`,
  `SH_PASS_STAFF`, `SH_PASS_VENDOR_<NAME>`). An unset variable never matches. Compare trimmed and
  case-insensitively (phone keyboards capitalize), in constant time.
- **Session cookie** (`sh_session`) = HMAC-SHA256 of one fixed label, keyed with that person's
  password as it is compared (trimmed, case-folded). So changing or deleting a password in the
  host's settings signs that person out at once, with no session table. `HttpOnly`, `Secure` on
  HTTPS (trust `X-Forwarded-Proto` from the host's proxy), `SameSite=Lax`. Lifetime 365 days for
  owner and staff, 30 days for vendors.
- When two variables hold the same password they produce the same cookie: resolve it, at sign-in
  and on every request, to the **least privileged** role (vendor without alerts, vendor, staff,
  owner), and log a warning at startup. A collision may take rights away, never grant them.
  Without an owner password nobody can sign in.
- **Brute force:** 8 failed attempts from one address within 10 minutes → 429 for that address
  until the window passes. Log every attempt that was examined (`sh_login_log`: time, address,
  success, who, user agent; `who` is `?` for a wrong password); requests refused with 429 are not
  logged, so a flood cannot fill the table. A logging failure never blocks sign-in.
- **The client address** behind the host's proxy: use the entry the host itself adds to
  `X-Forwarded-For` (check the host's documentation; on a host that appends, the left-most entry
  is whatever the client sent and lets an attacker dodge the limits).
- Hebrew texts of the pages around the screen: sign-in button `כניסה`, placeholder `סיסמה`,
  wrong password `סיסמה שגויה`, too many attempts `יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.`,
  bad share link `הקישור אינו תקין או שפג.`, database unreachable
  `אין כרגע חיבור לנתונים. נסו שוב בעוד רגע.`
- The page is served with the role injected at `<!--SH_INJECT-->`:
  `<script>window.SH_CONFIG={…};window.SH_ROLE={…};</script>`. Build it with a JSON encoder; never
  concatenate user input into it.
- `X-Robots-Tag: noindex` on every answer; the page already carries the meta tag.

### 8.3 Optional: "view as vendor" for the owner

A link for the owner that shows the screen exactly as a vendor gets it (a second cookie that the
server honors only together with a valid owner session, and that makes every check above treat
the request as the vendor). Useful before sending a vendor their password. Build it only if asked.

---

## 9. Build order and checks

Report after each phase: what was built, which checks ran, their result.

| Phase | Build | Done when |
|---|---|---|
| 0. Look | unpack; run the mock; open the screen | you have seen all 11 cards, opened a drill-down, pressed `הסברים` |
| 1. Intake | §2 | `site_health.config.json` exists and the owner confirmed it |
| 2. Database | tables and `sh_*` functions | `reference/tests/test_sql.py` passes against a scratch database (or your equivalent tests of the rules in §7.3 and §7.8) |
| 3. Server | login, roles, the routes of §5 | `reference/tests/test_server.py` passes; `node check_screen.js <server> --basic --cookie …` passes |
| 4. Probe + alerts | §7.5, §7.8, §7.9 | against a throwaway local site: a page that starts failing opens an alert within 2 minutes, a push is logged, the alert closes when the page recovers; 3 dead minutes show as one outage |
| 5. Speed | §7.6, sitemap | one real PageSpeed call stored for the home page; the screen's speed tiles show it |
| 6. Daily jobs | catalogue, certificate, cleanup, morning message | each ran once and its flow shows `תקין` |
| 7. Real users | §7.7 | a test page view on the site appears in "מהירות אצל לקוחות" within a minute, flagged as test |
| 8. Deploy | host, environment, schedules, the independent check of §7.10 | the checklist of §10 is green on the live address |
| 9. Hand-over | a short Hebrew note for the owner | they know the address, how to subscribe to alerts, and what each color means |

Rules for the whole build:

- Run the real thing. A phase is not done because the code looks right.
- Use a scratch database for tests. Never run tests that write against the live database.
- Do not leave test alerts, test pushes or fake rows in the live database. A test push to the
  real topic must say it is a test.

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
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/check_screen.js sha256=80662c26880462f998b18b56a41ef2fd8d14d46a19c4b52e1aaa602e78ee20d7 -->
~~~~~~~~javascript
#!/usr/bin/env node
/* Acceptance test of the site-health screen (Playwright, headless Chromium).

     node check_screen.js                          # against the mock:  http://127.0.0.1:8787
     node check_screen.js http://127.0.0.1:8000    # against your real server (logged-in session needed, see --cookie)
     node check_screen.js <url> --cookie "name=value"   # session cookie for a real server
     node check_screen.js <url> --shots ./shots    # also save screenshots (phone + desktop)
     node check_screen.js <url> --basic            # only the checks that hold for any data

   Against the mock it also switches scenarios (incident / ok / empty / error) and roles.
   Exit code 0 = every check passed. Each line is one check: "ok" or "FAIL". */
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i < 0 ? null : (args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true); };
const BASE = (args[0] && !args[0].startsWith('--') ? args[0] : 'http://127.0.0.1:8787').replace(/\/$/, '');
const SHOTS = flag('--shots'), COOKIE = flag('--cookie'), BASIC = !!flag('--basic');
const PAGE_PATH = flag('--path') || '/site';

let failed = 0, passed = 0;
function check(name, cond, extra) { if (cond) { passed++; console.log('ok    ' + name); } else { failed++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); } }

async function open(browser, path, vp, opts = {}) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, locale: 'he-IL', colorScheme: opts.dark ? 'dark' : 'light' });
  if (COOKIE && typeof COOKIE === 'string') {
    const [n, ...v] = COOKIE.split('='); const u = new URL(BASE);
    await ctx.addCookies([{ name: n, value: v.join('='), domain: u.hostname, path: '/' }]);
  }
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
  const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  if (resp && resp.status() === 200 && !opts.noWait) {
    await page.waitForFunction(() => !document.body.classList.contains('loading') && document.querySelectorAll('#verdict .vbox').length === 4, null, { timeout: 20000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelectorAll('#now .nbox').length >= 1 && !/טוען/.test(document.getElementById('now').textContent), null, { timeout: 20000 }).catch(() => {});
  }
  return { ctx, page, errors, status: resp ? resp.status() : 0 };
}
const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
const txt = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent : null; }, sel);
const count = (page, sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel);
const visible = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }, sel);
async function scenario(name) { const r = await fetch(BASE + '/__scenario?name=' + name).catch(() => null); return !!(r && r.ok); }

(async () => {
  const browser = await chromium.launch();
  const isMock = !BASIC && await scenario('incident');
  const PHONE = { width: 390, height: 844 }, DESK = { width: 1280, height: 900 };

  /* ---------- 1. structure, on a phone ---------- */
  let s = await open(browser, PAGE_PATH, PHONE);
  let p = s.page;
  check('page loads (200)', s.status === 200, 'status ' + s.status);
  check('no horizontal scroll at 390px', await noOverflow(p));
  check('html is rtl + hebrew', await p.evaluate(() => document.documentElement.dir === 'rtl' && document.documentElement.lang === 'he'));
  check('"now" card shows 4 tiles', await count(p, '#now .nbox') === 4, String(await count(p, '#now .nbox')));
  check('bottom line shows 4 tiles', await count(p, '#verdict .vbox') === 4);
  const cards = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.wrap > section.card h2'), (h) => h.firstChild.textContent.trim()));
  const WANT = ['עכשיו', 'שורה תחתונה', 'זמינות', 'מהירות לאורך זמן', 'העמודים העיקריים', 'העמודים הכבדים באתר', 'מוצרים שבורים באתר', 'תעודת האבטחה (המנעול)', 'התראות', 'הודעות שנשלחו לטלפון', 'המדידה עצמה'];
  check('cards appear in the specified order', JSON.stringify(cards) === JSON.stringify(WANT), JSON.stringify(cards));
  check('subtitle shows the last check time and the period', /הבדיקה האחרונה .* · 24 השעות האחרונות/.test(await txt(p, '#sub')), await txt(p, '#sub'));
  check('alerts card and messages card start folded', await p.evaluate(() => document.getElementById('alertsList').parentElement.classList.contains('collapsed') && document.getElementById('msgList').parentElement.classList.contains('collapsed')));
  check('explanations hidden until asked', !(await visible(p, 'p.explain')));
  await p.click('#explbtn');
  check('"הסברים" shows the explanations', await visible(p, 'p.explain') && (await p.getAttribute('#explbtn', 'aria-pressed')) === 'true');
  await p.click('#explbtn');
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone.png', fullPage: true });

  /* ---------- 2. numbers match the data ---------- */
  const data = await p.evaluate(() => state.data);
  const per = (Array.isArray(data.availability) ? data.availability : []).filter((r) => r.section === 'לפי עמוד');
  const checksN = per.reduce((a, r) => a + (+r.checks || 0), 0), failN = per.reduce((a, r) => a + (+r.failed || 0), 0);
  if (checksN) {
    const up = 100 - 100 * failN / checksN, want = up.toFixed(up < 99.95 ? 2 : 1) + '%';
    check('uptime tile = 100 − failed/checks', (await txt(p, '#verdict .vbox[data-drill="fails"] .v')) === want, want + ' vs ' + await txt(p, '#verdict .vbox[data-drill="fails"] .v'));
    check('availability table: one row per probed page', await count(p, '#availTbl tbody tr') === per.length);
  } else check('no availability data → empty state text', /אין בדיקות זמינות בתקופה/.test(await txt(p, '#availTbl')));
  const core = (Array.isArray(data.speed) ? data.speed : []).filter((r) => r.section === 'ליבה' && r.strategy === 'mobile');
  check('core pages table: one row per core page (mobile)', core.length ? await count(p, '#coreTbl tbody tr') === core.length : /אין מדידות טלפון בתקופה/.test(await txt(p, '#coreTbl')));
  check('heavy pages table: at most 10 rows', await count(p, '#slowTbl tbody tr') <= 10);

  /* ---------- 3. drill-downs ---------- */
  await p.click('#verdict .vbox[data-drill="fails"]');
  await p.waitForFunction(() => document.getElementById('dov').classList.contains('on') && !/טוען…/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
  check('click on uptime opens the failures sheet', (await txt(p, '#dttl')) === 'כל הכשלים' && /הבדיקות שנכשלו/.test(await txt(p, '#dbody')), await txt(p, '#dttl'));
  check('sheet is a bottom sheet on a phone', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs(r.bottom - window.innerHeight) < 2 && r.width >= window.innerWidth - 2; }));
  await p.keyboard.press('Escape');
  check('Escape closes the sheet', !(await p.evaluate(() => document.getElementById('dov').classList.contains('on'))));
  if (core.length) {
    await p.click('#coreTbl tbody tr');
    await p.waitForFunction(() => /המדידות|אין מדידות תקינות/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
    check('click on a core page opens its measurements', /^מהירות: /.test(await txt(p, '#dttl')), await txt(p, '#dttl'));
    await p.click('#dx');
  }
  check('no JavaScript errors (phone)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();

  /* ---------- 4. desktop + dark ---------- */
  s = await open(browser, PAGE_PATH, DESK); p = s.page;
  check('no horizontal scroll at 1280px', await noOverflow(p));
  await p.click('#verdict .vbox[data-drill="outages"]');
  check('sheet is centered on desktop', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2 && r.width === 720; }));
  await p.click('#dx');
  await p.click('#segH button[data-h="168"]');
  await p.waitForFunction(() => state.data && state.data.hours === 168 && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"7 ימים" reloads with a 168-hour window', await p.evaluate(() => state.data.hours === 168) && /7 הימים האחרונים/.test(await txt(p, '#rangeTxt')));
  await p.click('#segS button[data-s="desktop"]');
  await p.waitForFunction(() => state.data && state.data.strategy === 'desktop' && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"מחשב" reloads with strategy=desktop', await p.evaluate(() => state.data.strategy === 'desktop'));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/desktop.png', fullPage: true });
  check('no JavaScript errors (desktop)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();
  s = await open(browser, PAGE_PATH, PHONE, { dark: true }); p = s.page;
  check('dark mode: page background is dark', await p.evaluate(() => { const m = getComputedStyle(document.body).backgroundColor.match(/\d+/g); return m && (+m[0] + +m[1] + +m[2]) < 150; }));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-dark.png', fullPage: true });
  await s.ctx.close();

  /* ---------- 5. mock only: alert bar, roles, scenarios ---------- */
  if (isMock) {
    await scenario('incident');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const openAlerts = (await p.evaluate(() => state.data.alerts_open)).filter((a) => !a.acked).length;
    check('alert bar shows the number of open alerts', new RegExp('⚠ ' + openAlerts + ' התראות פעילות').test(await txt(p, '#alertbar .acount')), await txt(p, '#alertbar .acount'));
    check('alert bar starts collapsed', await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed')));
    await p.click('#alertbar .ahead');
    check('each alert with a URL in its body has an "open the page" link', await count(p, '#alertbar .alink') >= 1);
    const posts = [];
    p.on('request', (r) => { if (r.method() === 'POST') posts.push(r.url() + ' ' + r.postData()); });
    await p.click('#alertbar .arow .ax');
    check('✕ removes the alert at once, without reloading the screen', await count(p, '#alertbar .arow') === openAlerts - 1 && !(await p.evaluate(() => document.body.classList.contains('loading'))));
    check('✕ posts {"ids":[id]} to /api/alerts/ack', posts.length === 1 && /\/api\/alerts\/ack \{"ids":\[\d+\]\}/.test(posts[0]), posts.join(','));
    check('the bar stays open after a delete', !(await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed'))));
    await p.click('#abAll'); await p.click('#abDel');
    check('"לסמן הכול" + "מחק מסומנות" clears the bar', !(await visible(p, '#alertbar')));
    await p.click('#refbtn');
    await p.waitForFunction(() => !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
    check('acknowledged alerts stay hidden after refresh', !(await visible(p, '#alertbar')));
    check('…but still count as open in the bottom line', (await txt(p, '#verdict .vbox[data-drill="alerts"] .v')) === String(openAlerts));
    await p.click('#msgCard .foldhead');
    check('message log lists what was sent to the phone', await count(p, '#msgList li') >= 3);
    check('no JavaScript errors (owner, incident)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    await scenario('incident');
    s = await open(browser, PAGE_PATH + '?role=vendor', PHONE); p = s.page;
    await p.click('#alertbar .ahead').catch(() => {});
    check('vendor: no delete controls on alerts', !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#alertbar .abulk')));
    check('vendor: no message log', !(await visible(p, '#msgCard')));
    check('vendor: sees only site alerts (no internal kinds)', await p.evaluate(() => state.data.alerts_open.every((a) => ['down', 'slow', 'silent', 'cert'].indexOf(a.kind) >= 0)));
    check('vendor: server refuses a delete', await p.evaluate(() => fetch('/api/alerts/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"ids":[41]}' }).then((r) => r.status)) === 403);
    check('vendor: server refuses the message log', await p.evaluate(() => fetch('/api/messages?h=24').then((r) => r.status)) === 403);
    check('no JavaScript errors (vendor)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    s = await open(browser, PAGE_PATH + '?role=noalerts', PHONE); p = s.page;
    check('no-alerts role: no bar, no alerts card, no open-alerts tile', !(await visible(p, '#alertbar')) && !(await visible(p, '#alertsCard')) && !(await visible(p, '#verdict .vbox[data-drill="alerts"]')));
    await s.ctx.close();

    s = await open(browser, '/status?k=demo-share-token', PHONE); p = s.page;
    check('share link: screen loads with data', s.status === 200 && await count(p, '#verdict .vbox') === 4);
    check('share link: no logout link, no delete controls, no message log', !(await visible(p, '#outLink')) && !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#msgCard')));
    check('no JavaScript errors (share link)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
    s = await open(browser, '/status?k=wrong', PHONE, { noWait: true });
    check('share link with a wrong token is refused (403)', s.status === 403);
    await s.ctx.close();
    const r401 = await fetch(BASE + '/api/site?k=wrong');
    check('data call with a wrong token is refused (401)', r401.status === 401);

    await scenario('empty');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const body = await txt(p, '.wrap');
    check('fresh install: every card shows its empty state, nothing breaks',
      /אין בדיקות זמינות בתקופה/.test(body) && /מדידת המהירות עדיין לא התחילה/.test(body) && /הסבב על כל האתר עדיין לא התחיל/.test(body)
      && /עדיין לא נבדק/.test(body) && /אין התראות בתקופה/.test(body) && /אין בדיקה ב־15 הדקות האחרונות/.test(body) && s.errors.length === 0, s.errors.join(' | '));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-empty.png', fullPage: true });
    await s.ctx.close();

    await scenario('error');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('data source down: the screen still renders, no JavaScript errors', await count(p, '#verdict .vbox') === 4 && s.errors.length === 0, s.errors.join(' | '));
    check('data source down: "now" says it could not load', /לא הצלחתי לטעון את "עכשיו"/.test(await txt(p, '#nowtick')), await txt(p, '#nowtick'));
    await s.ctx.close();

    await scenario('ok');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('all good: no alert bar, site "פעיל"', !(await visible(p, '#alertbar')) && /פעיל/.test(await txt(p, '#now .nbox .v')));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-ok.png', fullPage: true });
    await s.ctx.close();
    await scenario('incident');
  }

  await browser.close();
  console.log('\n' + passed + ' passed, ' + failed + ' failed' + (isMock ? '' : '  (basic checks only — scenario and role checks need the mock)'));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('test crashed: ' + e.stack); process.exit(2); });
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/mock_server.py sha256=545850f6a7feb0bb86c3b2fbe6ca126be465fe7b5b556a02b7f1c5779317f56c -->
~~~~~~~~python
#!/usr/bin/env python3
"""Mock backend for the site-health screen. Standard library only.

It serves the screen and answers every data call with realistic, deterministic fake data,
in exactly the shapes described in SPEC.md ("API contract"). Use it to:
  * see the screen working before any real backend exists;
  * compare your real backend's answers with these, field by field;
  * run check_screen.js (the acceptance test of the screen).

    python3 mock_server.py                      # http://localhost:8787/site
    python3 mock_server.py --port 9000 --scenario empty
    python3 mock_server.py --html /path/to/another_site_health.html

Roles (what the real server injects):  /site  owner ·  /site?role=vendor  read-only
  /site?role=noalerts  read-only without alerts ·  /status?k=demo-share-token  share link
Scenarios: incident (default) · ok · empty (fresh install, no data) · error (data source down).
Switch while running:  GET /__scenario?name=empty

This file is a test double. Nothing in it is a design for the real backend.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Asia/Jerusalem")          # the site's local time zone: every *_il string and every bucket uses it
SITE = "https://example.co.il"
SHARE_TOKEN = "demo-share-token"
PROBE = [("בית", "/"), ("קטגוריה", "/product-category/sofas/"), ("מוצר", "/product/sample-sofa/"), ("סל", "/cart/")]
CORE = PROBE + [("קופה", "/checkout/")]
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}
STATE = {"scenario": "incident", "acked": set(), "html": os.path.join(HERE, "site_health.html")}


def rnd(*key):
    """Deterministic pseudo-random number in [0, 1) for a key: the same hour always looks the same."""
    return int(hashlib.md5("|".join(str(k) for k in key).encode()).hexdigest()[:8], 16) / 0x100000000


def now():
    return dt.datetime.now(TZ)


def il(d, year=False):
    return d.astimezone(TZ).strftime("%d.%m.%Y %H:%M" if year else "%d.%m %H:%M")


def window(q):
    """Same rule as the real server: f/t are local dates (t inclusive); otherwise h hours back from now."""
    n = now()
    f, t = q.get("f", ""), q.get("t", "")
    if f:
        try:
            d0 = dt.datetime.strptime(f, "%Y-%m-%d").replace(tzinfo=TZ)
            d1 = (dt.datetime.strptime(t, "%Y-%m-%d").replace(tzinfo=TZ) + dt.timedelta(days=1)) if t else n
            if d1 <= d0:
                d1 = d0 + dt.timedelta(days=1)
            return d0, min(d1, n), max(1, int((d1 - d0).total_seconds() // 3600))
        except ValueError:
            pass
    try:
        h = max(1, min(int(q.get("h") or 24), 24 * 400))
    except ValueError:
        h = 24
    return n - dt.timedelta(hours=h), n, h


def buckets(d0, d1, hours):
    """Hourly buckets ('YYYY-MM-DD HH:00') up to 72 hours, daily ('YYYY-MM-DD') beyond. Local time."""
    out = []
    if hours <= 72:
        b = d0.replace(minute=0, second=0, microsecond=0)
        while b < d1:
            out.append((b.strftime("%Y-%m-%d %H:00"), b, min(b + dt.timedelta(hours=1), d1)))
            b += dt.timedelta(hours=1)
    else:
        b = d0.replace(hour=0, minute=0, second=0, microsecond=0)
        while b < d1:
            out.append((b.strftime("%Y-%m-%d"), b, min(b + dt.timedelta(days=1), d1)))
            b += dt.timedelta(days=1)
    return out


def bad_hour(b):
    """In the 'incident' scenario a few hours are bad: that is where failures and slow pages cluster."""
    return STATE["scenario"] == "incident" and rnd("bad", b.strftime("%Y-%m-%d %H")) < 0.06


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))] if vals else None


def lcp_for(page, when, strategy):
    base = {"בית": 2300, "קטגוריה": 3300, "מוצר": 2800, "סל": 2100, "קופה": 2500}.get(page, 3000)
    if strategy == "desktop":
        base *= 0.45
    v = base * (0.85 + 0.4 * rnd("lcp", page, strategy, when.strftime("%Y-%m-%d %H")))
    if bad_hour(when) and page in ("קטגוריה", "מוצר"):
        v *= 1.7
    return int(v)


def verdict(ms):
    return "מצוין" if ms <= 2000 else "מהיר" if ms <= 2500 else "בינוני" if ms <= 4000 else "איטי"


def crux(ms):
    return "FAST" if ms <= 2500 else "AVERAGE" if ms <= 4000 else "SLOW"


# ---------------------------------------------------------------- alerts

def alerts():
    if STATE["scenario"] in ("ok", "empty", "error"):
        return []
    n = now()
    rows = [
        dict(id=41, kind="down", title="האתר לא עונה: סל", body="קוד 502\n%s/cart/" % SITE,
             opened=n - dt.timedelta(minutes=14), closed=None),
        dict(id=40, kind="slow", title="עמוד איטי: קטגוריה", body="4.6 שניות עד התוכן, פעמיים ברצף\n%s/product-category/sofas/" % SITE,
             opened=n - dt.timedelta(hours=2, minutes=5), closed=None),
        dict(id=39, kind="ops", title="רשימת הבוקר", body="3 הזמנות חסרות", opened=n - dt.timedelta(hours=5), closed=None),
        dict(id=38, kind="down", title="האתר לא עונה: בית", body="לא ענה בזמן\n%s/" % SITE,
             opened=n - dt.timedelta(hours=9, minutes=40), closed=n - dt.timedelta(hours=9, minutes=33)),
        dict(id=37, kind="cert", title="תעודת האבטחה פגה בעוד 13 ימים", body="example.co.il",
             opened=n - dt.timedelta(days=2, hours=3), closed=n - dt.timedelta(days=1, hours=20)),
        dict(id=36, kind="silent", title="המדידה נעצרה: מדידת מהירות — עמודי ליבה", body="אין מדידה כבר 95 דקות",
             opened=n - dt.timedelta(days=3, hours=1), closed=n - dt.timedelta(days=3)),
    ]
    for a in rows:
        end = a["closed"] or n
        a.update(open=a["closed"] is None, opened_il=il(a["opened"]), closed_il=il(a["closed"]) if a["closed"] else None,
                 minutes=int((end - a["opened"]).total_seconds() // 60), acked=a["id"] in STATE["acked"])
    return rows


def pub(a, keep=("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes", "acked")):
    return {k: a[k] for k in keep}


def filter_role(rows, role):
    if role == "noalerts":
        return []
    if role in ("vendor", "share"):
        return [r for r in rows if r.get("kind") in SITE_ALERT_KINDS]
    return rows


# ---------------------------------------------------------------- /api/site

def api_site(q, role):
    d0, d1, hours = window(q)
    strategy = "desktop" if q.get("strategy") == "desktop" else "mobile"
    out = {"hours": hours, "from": d0.isoformat(), "to": d1.isoformat(), "strategy": strategy}
    sc = STATE["scenario"]
    if sc == "error":
        err = {"error": "HTTP Error 503: Service Unavailable"}
        out.update({k: err for k in ("availability", "availability_series", "speed", "speed_series", "alerts_open",
                                     "alerts_recent", "health", "product_issues")})
        out["cert"] = err
        return out
    if sc == "empty":
        out.update(availability=[], availability_series=[], speed=[], speed_series=[], alerts_open=[], alerts_recent=[],
                   product_issues=[], cert=None,
                   health=[dict(flow_name=f, status="אין נתון", cadence=c, silent_txt=None,
                                last_at=None, warn_minutes=w, late_minutes=l, note=None) for f, c, w, l in FLOWS])
        return out
    bks = buckets(d0, d1, hours)
    # --- availability
    series, per = [], {p: dict(checks=0, failed=0, ms=[], last=None) for p, _ in PROBE}
    for name, b0, b1 in bks:
        minutes = max(1, int((b1 - b0).total_seconds() // 60))
        ch = fl = 0
        ms = []
        for p, _ in PROBE:
            f = 0
            hrs = max(1, minutes // 60)
            for i in range(hrs):
                hb = b0 + dt.timedelta(hours=i)
                if bad_hour(hb):
                    f += 2 + int(6 * rnd("f", p, hb.isoformat()))
                    per[p]["last"] = hb + dt.timedelta(minutes=int(50 * rnd("fm", p, hb.isoformat())))
                elif rnd("noise", p, hb.isoformat()) < 0.01:
                    f += 1
                    per[p]["last"] = hb + dt.timedelta(minutes=int(50 * rnd("fm", p, hb.isoformat())))
            m = int({"בית": 260, "מוצר": 300, "קטגוריה": 620, "סל": 540}[p] * (0.8 + 0.5 * rnd("ms", p, name)) * (2.2 if bad_hour(b0) else 1))
            ch += minutes
            fl += f
            ms += [m] * 3
            per[p]["checks"] += minutes
            per[p]["failed"] += f
            per[p]["ms"].append(m)
        series.append(dict(bucket=name, checks=ch, failed=fl, ms_p50=pct(ms, .5), ms_p95=int(pct(ms, .95) * 1.6)))
    av = [dict(section="לפי עמוד", page=p, checks=v["checks"], failed=v["failed"],
               fail_pct="%.2f" % (100.0 * v["failed"] / v["checks"]) if v["checks"] else "0.00",
               p50_ms=pct(v["ms"], .5), p95_ms=int(pct(v["ms"], .95) * 1.5) if v["ms"] else None,
               last_fail_il=il(v["last"]) if v["last"] else None) for p, v in per.items()]
    if sc == "incident" and hours >= 12:
        s = now() - dt.timedelta(hours=9, minutes=40)
        if s > d0:
            av.append(dict(section="נפילות", outage_minutes=7, outage_start_il=il(s), outage_end_il=il(s + dt.timedelta(minutes=7))))
    out["availability"] = av
    out["availability_series"] = series
    # --- speed
    sp, ss = [], []
    for strat in ("mobile", "desktop"):
        for p, path in CORE:
            vals = [lcp_for(p, b0, strat) for _, b0, _ in bks]
            med = pct(vals, .5)
            sp.append(dict(section="ליבה", strategy=strat, page=p, url=SITE + path, lcp_p50=med, lcp_p95=pct(vals, .95),
                           score_med=max(18, min(99, int(118 - med / 45))), cls_med=round(0.02 + 0.1 * rnd("cls", p), 2),
                           ttfb_p50=int(240 + 500 * rnd("ttfb", p)), slow_runs=sum(1 for v in vals if v > 4000) * 4,
                           checks=len(vals) * 4, crux_category=crux(int(med * 0.8)) if p != "קופה" else None,
                           crux_lcp=int(med * 0.8) if p != "קופה" else None))
            if strat == strategy:
                ss += [dict(page=p, url=SITE + path, bucket=name, lcp_p50=lcp_for(p, b0, strat)) for name, b0, _ in bks]
    home = [r for r in sp if r["page"] == "בית" and r["strategy"] == "mobile"][0]
    sp.append(dict(section="שורה תחתונה", page="בית", url=home["url"], lcp_p50=home["lcp_p50"], checks=home["checks"],
                   verdict=verdict(home["lcp_p50"])))
    for i in range(10):
        u = "%s/product/%s-%d/" % (SITE, urllib.parse.quote("ספה-פינתית"), i + 1)
        m = int(7200 - 380 * i + 300 * rnd("slow", i))
        sp.append(dict(section="האיטיים באתר", page=u, url=u, lcp_p50=m, score_med=max(9, 48 - 3 * (10 - i)),
                       checks=1 + i % 3, last_il=il(now() - dt.timedelta(hours=1 + 2 * i))))
    sp.append(dict(section="כיסוי", checks=min(412, 24 * hours), slow_runs=412))
    out["speed"] = sp
    out["speed_series"] = ss
    # --- alerts
    al = alerts()
    out["alerts_open"] = [pub(a, ("id", "kind", "title", "body", "opened_il", "acked")) for a in filter_role(al, role) if a["open"]]
    out["alerts_recent"] = [pub(a, ("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes"))
                            for a in filter_role(al, role) if (a["closed"] or now()) >= d0]
    # --- health of the measurement itself
    n = now()
    stat = {"מדידת מהירות — סבב כל האתר": ("מתעכב", 22, "מאחר ב-12 דקות"), "מהירות אצל לקוחות": ("שקט", 400, "שקט כבר 6 שעות")} if sc == "incident" else {}
    out["health"] = [dict(flow_name=f, status=stat.get(f, ("תקין",))[0], cadence=c,
                          silent_txt=stat[f][2] if f in stat else None,
                          last_at=(n - dt.timedelta(minutes=stat[f][1] if f in stat else int(1 + w * 0.3))).isoformat(),
                          warn_minutes=w, late_minutes=l, note=None) for f, c, w, l in FLOWS]
    # --- broken products
    snap = n.strftime("%Y-%m-%d")
    out["product_issues"] = [] if sc == "ok" else [
        dict(issue="בלי מחיר", name="שולחן אוכל נפתח 160", url=SITE + "/product/table-160/", snap_date=snap),
        dict(issue="בלי תמונה", name="כורסת טלוויזיה אפורה", url=SITE + "/product/armchair-grey/", snap_date=snap),
        dict(issue="לא במלאי", name="ספה תלת מושבית בז'", url=SITE + "/product/sofa-3-beige/", snap_date=snap),
        dict(issue="לא במלאי", name="מיטה זוגית 160 עם ארגז", url=SITE + "/product/bed-160/", snap_date=snap),
        dict(issue="אי אפשר להוסיף לסל", name="שידת לילה אלון", url=SITE + "/product/nightstand-oak/", snap_date=snap),
    ]
    days = 23 if sc == "incident" else 71
    out["cert"] = dict(host="example.co.il", issuer="Let's Encrypt R11", not_after=(n + dt.timedelta(days=days, hours=5)).isoformat(),
                       days_left=days, ok=True, err=None, checked_at=n.replace(hour=4, minute=3).isoformat())
    return out


FLOWS = [  # flow_name, cadence, warn_minutes, late_minutes
    ("בודק זמינות האתר", "כל דקה", 5, 15),
    ("מדידת מהירות — עמודי ליבה", "כל רבע שעה", 45, 90),
    ("מדידת מהירות — סבב כל האתר", "כל 5 דקות", 20, 60),
    ("טעינת מפת האתר", "פעם ביום", 1560, 2880),
    ("בדיקת תעודת האבטחה", "פעם ביום", 1560, 2880),
    ("בדיקת מוצרים שבורים", "פעם ביום", 1560, 2880),
    ("מהירות אצל לקוחות", "כל צפייה בעמוד", 120, 360),
]


# ---------------------------------------------------------------- /api/site/now

def api_now(role):
    sc = STATE["scenario"]
    if sc == "error":
        return {"error": "HTTP Error 503: Service Unavailable"}
    if sc == "empty":
        return dict(pages=[], latest=[], light=False, all_ok=False, any_ok=False, age_sec=None, rum={"n": 0, "p75_ms": None},
                    speed={}, alerts_open=0, rum_src=None)
    n = now()
    pages = []
    for p, path in PROBE:
        ok = not (sc == "incident" and p == "סל")
        pages.append(dict(page=p, url=SITE + path, ok=ok, status=200 if ok else 502,
                          ms=int({"בית": 240, "מוצר": 310, "קטגוריה": 690, "סל": 1700}[p] * (0.9 + 0.3 * rnd("now", p, n.strftime("%H:%M")))) if ok else None))
    oks = [p["ok"] for p in pages]
    lcp = lcp_for("בית", n, "mobile")
    return dict(
        pages=pages, latest=pages, light=n.second >= 30, all_ok=all(oks), any_ok=any(oks), age_sec=n.second % 30 + 4,
        rum=dict(n=143, p75_ms=2380 if sc == "ok" else 3120),
        speed=dict(lcp_ms=lcp, score=max(18, min(99, int(118 - lcp / 45))), checked_at=(n - dt.timedelta(minutes=n.minute % 15)).isoformat()),
        alerts_open=len([a for a in filter_role(alerts(), role) if a["open"]]),
        rum_src=dict(n=1000, hosts=[{"host": "live", "n": 1000}] if sc == "ok" else [{"host": "live", "n": 964}, {"host": "staging.example.co.il", "n": 36}],
                     cols=["created_at", "is_test", "lcp_ms", "path", "site"], test=0 if sc == "ok" else 12))


# ---------------------------------------------------------------- /api/site/drill

def api_drill(q, role):
    what = q.get("what", "")
    d0, d1, hours = window(q)
    n = now()
    if STATE["scenario"] in ("empty", "error") and what != "alert":
        return {"rows": []}
    if what == "fails":
        rows = []
        for i in range(23):
            p = PROBE[int(4 * rnd("fp", i))][0]
            if q.get("page") and p != q["page"]:
                continue
            k = ["לא ענה בזמן", "קוד 502", "קוד 500", "שגיאת חיבור"][int(4 * rnd("fk", i))]
            rows.append(dict(at_il=il(n - dt.timedelta(minutes=14 + 31 * i)), page=p, kind=k,
                             err="upstream connect error or disconnect/reset before headers" if k == "שגיאת חיבור" else None,
                             ms=10000 if k == "לא ענה בזמן" else int(300 + 900 * rnd("fms", i))))
        return {"rows": rows}
    if what == "bucket":
        return {"rows": [dict(page=p, checks=60, failed=int(3 * rnd("bf", p, q.get("bucket"))), ms_p50=int(250 + 500 * rnd("bm", p)),
                              ms_max=int(900 + 2500 * rnd("bx", p)), worst_il=il(n - dt.timedelta(minutes=int(600 * rnd("bw", p)))))
                         for p, _ in PROBE]}
    if what == "runs":
        strat = "desktop" if q.get("strategy") == "desktop" else "mobile"
        page = next((p for p, path in CORE if SITE + path == q.get("url")), "מוצר")
        rows = []
        for i in range(36 if not q.get("bucket") else 4):
            t = n - dt.timedelta(minutes=15 * i + 3)
            if i == 5:
                rows.append(dict(ok=False, err="Lighthouse returned error: NO_FCP", at_il=il(t)))
                continue
            lcp = lcp_for(page, t, strat)
            rows.append(dict(ok=True, err=None, at_il=il(t), lcp_ms=lcp, score=max(18, min(99, int(118 - lcp / 45))),
                             ttfb_ms=int(260 + 420 * rnd("rt", i)), bytes=int(3.1e6 + 2.4e6 * rnd("rb", i)), cls=round(0.01 + 0.12 * rnd("rc", i), 3),
                             crux_category=crux(int(lcp * 0.8)), crux_lcp_ms=int(lcp * 0.8),
                             opps=[dict(id="uses-responsive-images", title="Properly size images", ms=int(900 + 700 * rnd("o1", i))),
                                   dict(id="modern-image-formats", title="Serve images in next-gen formats", ms=int(500 + 400 * rnd("o2", i))),
                                   dict(id="render-blocking-resources", title="Eliminate render-blocking resources", ms=int(300 + 300 * rnd("o3", i))),
                                   dict(id="some-new-audit", title="A reason the screen has no translation for", ms=120)]))
        return {"rows": rows}
    if what == "alert":
        try:
            aid = int(q.get("id") or 0)
        except ValueError:
            aid = 0
        rows = [a for a in filter_role(alerts(), role) if a["id"] == aid]
        out = []
        for a in rows:
            r = pub(a, ("id", "kind", "title", "body", "open", "opened_il", "closed_il", "minutes"))
            r["fails"] = [dict(at=il(a["opened"] + dt.timedelta(minutes=i)), page=a["title"].split(": ")[-1], status=502 if i else None,
                               err=None if i else "timeout") for i in range(3)] if a["kind"] == "down" else []
            sent = [dict(event="open", status=200, at=il(a["opened"]))]
            if a["closed"]:
                sent.append(dict(event="close", status=200, at=il(a["closed"])))
            r["sent"] = [] if role in ("vendor", "share") else sent
            out.append(r)
        return {"rows": out}
    return None


def api_messages(q):
    if STATE["scenario"] in ("empty", "error", "ok"):
        return {"rows": []}
    rows = []
    for a in alerts():
        rows.append(dict(kind="התראה", title=a["title"], msg=a["body"], at_il=il(a["opened"]), sent=True, _t=a["opened"]))
        if a["closed"]:
            rows.append(dict(kind="חזר לתקין", title=a["title"], msg="נמשך %d דקות" % a["minutes"], at_il=il(a["closed"]), sent=a["id"] != 37, _t=a["closed"]))
    n = now()
    rows.append(dict(kind="בוקר", title="בוקר טוב: האתר תקין", msg="זמינות 99.9% ב-24 שעות\nמהירות עמוד הבית: מהיר",
                     at_il=il(n.replace(hour=7, minute=30)), sent=True, _t=n.replace(hour=7, minute=30)))
    rows.sort(key=lambda r: r["_t"], reverse=True)
    return {"rows": [{k: v for k, v in r.items() if k != "_t"} for r in rows]}


# ---------------------------------------------------------------- http

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _role(self, q):
        """owner | vendor | noalerts | share. The real server derives it from the session cookie / share token."""
        if q.get("k"):
            return "share" if q["k"] == SHARE_TOKEN else None
        m = re.search(r"mock_role=(\w+)", self.headers.get("Cookie", ""))
        return m.group(1) if m else "owner"

    def _page(self, role, share_key=""):
        html = open(STATE["html"], encoding="utf-8").read()
        cfg = {"siteLabel": "example.co.il", "brand": "DEMO", "shareKey": share_key,
               "bucketNote": "עמוד הסל וקטגוריה תמיד איטיים יותר: הם לא נשמרים בזיכרון המטמון של האתר ונבנים מחדש בכל כניסה."}
        if role == "owner":
            cfg["links"] = [{"href": "#", "label": "מסך נוסף", "title": "דוגמה לכפתור נוסף"}]
            cfg["nav"] = [["g", "האתר"], ["a", "/site", "בריאות האתר"], ["a", "#", "מסך נוסף"]]
        r = {"owner": {}, "vendor": {"readonly": True}, "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}[role]
        inject = "<script>window.SH_CONFIG=%s;window.SH_ROLE=%s;</script>" % (json.dumps(cfg, ensure_ascii=False), json.dumps(r))
        if "<!--SH_INJECT-->" in html:
            html = html.replace("<!--SH_INJECT-->", inject, 1)
        else:   # a screen without the marker (for example the original it was derived from): old-style flags
            old = "<script>window.OWL_ROLE={};%s</script>" % ("window.OWL_SHARE=1;" if role != "owner" else "")
            html = html.replace("</head>", old + "</head>", 1)
        return html

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        path = u.path
        if path in ("/", "/site"):
            role = q.get("role", "owner")
            if role not in ("owner", "vendor", "noalerts"):
                role = "owner"
            return self._send(200, self._page(role), "text/html; charset=utf-8",
                              {"Set-Cookie": "mock_role=%s; Path=/; SameSite=Lax" % role, "Cache-Control": "no-cache, must-revalidate"})
        if path == "/status":
            if q.get("k") != SHARE_TOKEN:
                return self._send(403, "<div dir='rtl' style='font-family:system-ui;padding:48px;text-align:center'>הקישור אינו תקין או שפג.</div>", "text/html; charset=utf-8")
            return self._send(200, self._page("share", SHARE_TOKEN), "text/html; charset=utf-8")
        if path == "/__scenario":
            if q.get("name") in ("incident", "ok", "empty", "error"):
                STATE["scenario"] = q["name"]
                STATE["acked"] = set()
            return self._send(200, {"scenario": STATE["scenario"]})
        if path in ("/login", "/logout"):
            return self._send(200, "<div dir='rtl' style='font-family:system-ui;padding:48px'>דף הכניסה (דמה). <a href='/site'>חזרה</a></div>", "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        role = self._role(q)
        if role is None:
            return self._send(401, {"error": "auth"})
        if path == "/api/site":
            return self._send(200, api_site(q, role))
        if path == "/api/site/now":
            d = api_now(role)
            return self._send(502 if "error" in d else 200, d)
        if path == "/api/site/drill":
            d = api_drill(q, role)
            return self._send(200, d) if d is not None else self._send(400, {"error": "what?"})
        if path == "/api/messages":
            if q.get("k"):                     # the share token counts only on /status and the three data calls
                return self._send(401, {"error": "auth"})
            if role != "owner":
                return self._send(403, {"error": "auth"})
            return self._send(200, api_messages(q))
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path != "/api/alerts/ack":
            return self._send(404, {"error": "not found"})
        if q.get("k"):
            return self._send(401, {"error": "auth"})
        if self._role(q) != "owner":
            return self._send(403, {"error": "auth"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            raw = body.get("ids") if isinstance(body.get("ids"), list) else [body.get("id")]
            ids = sorted({int(x) for x in raw[:200] if str(x).lstrip("-").isdigit() and int(x) > 0})
        except Exception:
            ids = []
        if not ids:
            return self._send(400, {"error": "bad request"})
        STATE["acked"].update(ids)
        return self._send(200, {"ok": True, "n": len(ids)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--scenario", default="incident", choices=["incident", "ok", "empty", "error"])
    ap.add_argument("--html", default=STATE["html"], help="the screen file to serve (default: site_health.html next to this script)")
    a = ap.parse_args()
    STATE["scenario"], STATE["html"] = a.scenario, a.html
    print("mock site-health backend: http://localhost:%d/site   (scenario: %s)" % (a.port, a.scenario), flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/site_health.html sha256=35aa2ea6f3c976d6680e04eddbca6a115ed083e3ac6d0b2810f12c9809b093db -->
~~~~~~~~html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>בריאות האתר</title>
<!--
  SITE HEALTH SCREEN — reference template (single file, no build step, no libraries).
  Per-site settings live in SH_CONFIG at the top of the script block at the end of this file.
  The server may override any of them, and set the viewer role, by injecting one inline script
  tag (window.SH_CONFIG = {...}; window.SH_ROLE = {...}) at the marker comment below.
  Everything else is data-driven: see the kit's SPEC.md, section "API contract".
-->
<style>
:root{
  --font: system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Hebrew",Arial,sans-serif;
  --bg:#ffffff; --surface:#f4f8f6; --line:#e2e9e5; --line2:#cdd8d2;
  --tx:#18241f; --tx2:#53635c; --tx3:#8a978f;
  --brand:#0d9668; --brandSoft:rgba(13,150,104,.10);
  --sys:#4a3aa7; --sysSoft:rgba(74,58,167,.07);
  --okbg:#e3f3ec; --okfg:#0b6e4f; --wbg:#fbf0da; --wfg:#8f5f08; --dbg:#fbe6e4; --dfg:#a3271f;
  --down:#a3271f;
  --shadow:0 1px 2px rgba(16,24,32,.05),0 6px 18px rgba(16,24,32,.05);
  --r:14px;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0f1512; --surface:#19211d; --line:#26302b; --line2:#35423b;
    --tx:#e9efeb; --tx2:#a2b0a9; --tx3:#6f7d76;
    --brand:#2fbf8f; --brandSoft:rgba(47,191,143,.16);
    --sys:#9085e9; --sysSoft:rgba(144,133,233,.10);
    --okbg:#12312765; --okfg:#63d3a6; --wbg:#2e241065; --wfg:#e0b25a; --dbg:#3a1a1765; --dfg:#f0968f;
    --down:#f0968f;
    --shadow:0 1px 2px rgba(0,0,0,.5),0 6px 18px rgba(0,0,0,.35);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:var(--font);-webkit-text-size-adjust:100%;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:12px 12px 40px}

/* ---------- זהות ---------- */
.hdr{display:flex;align-items:flex-start;justify-content:space-between;margin:0 0 6px}
.hdr .out{font-size:11.5px;color:var(--tx3);text-decoration:none;padding:6px 2px}
.shbrand{display:flex;align-items:flex-start;gap:7px;flex:none;min-height:18px}
.shword{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-weight:700;font-size:15px;letter-spacing:.04em;color:var(--tx);line-height:1;margin-top:4px;unicode-bidi:isolate}
.brandcol{display:flex;flex-direction:column;align-items:flex-end;gap:2px;line-height:1}

/* ---------- שורת התפריט ---------- */
.shbar{display:flex;align-items:center;gap:11px;margin:0 0 12px}
.shham{width:46px;height:46px;flex:none;border:1px solid var(--line);border-radius:13px;background:var(--surface);color:var(--tx);display:grid;place-items:center;cursor:pointer}
.shham svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round}
.shnow{min-width:0;display:flex;flex-direction:column;line-height:1.25}
.shnow .v{font-size:18px;font-weight:700;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.shacts{margin-inline-start:auto;display:flex;align-items:center;gap:6px}
.shxls{display:inline-flex;align-items:center;gap:6px;font-family:inherit;font-size:12.5px;border:1px solid var(--line2);background:var(--bg);color:var(--tx2);padding:7px 12px;min-height:38px;border-radius:999px;cursor:pointer}
.shxls[aria-pressed="true"]{background:var(--sysSoft);border-color:var(--sys);color:var(--sys);font-weight:700}
.shov{position:fixed;inset:0;background:rgba(10,18,14,.45);z-index:120;display:none}
.shov.on{display:block}
.shsheet{position:absolute;inset-block:0;inset-inline-end:0;width:min(330px,88vw);background:var(--bg);border-inline-start:1px solid var(--line);padding:14px;overflow:auto}
.shhead{display:flex;align-items:center;justify-content:space-between;margin:0 0 10px}
.shhead b{font-size:17px}
.shx{width:38px;height:38px;border:0;background:transparent;color:var(--tx);cursor:pointer;border-radius:10px;display:grid;place-items:center}
.shx svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round}
.shg{font-size:10.5px;font-weight:700;letter-spacing:.09em;color:var(--tx3);margin:12px 4px 5px}
.shsheet a,.shcur{display:flex;align-items:center;gap:9px;min-height:44px;padding:9px 11px;border-radius:11px;text-decoration:none;color:var(--tx);font-size:15px;border:1px solid transparent}
.shsheet a:hover{background:var(--surface);border-color:var(--line)}
.shcur,.shsheet a.shcur{background:#111;color:#fff;font-weight:700;border-color:#111;cursor:default}
/* ---------- תפקידים: צפייה בלבד / קישור שיתוף / בלי התראות ---------- */
.ro .alertbar .ax,.ro .alertbar .acb,.ro .abulk,.ro #msgCard{display:none!important}
.share #outLink{display:none!important}
.noalerts #alertbar,.noalerts #alertsCard,.noalerts .vbox[data-drill="alerts"]{display:none!important}
@media (prefers-color-scheme:dark){.shcur,.shsheet a.shcur{background:#e9efeb;color:#0f1512;border-color:#e9efeb}}

/* ---------- פס התראה ---------- */
.alertbar{display:none;background:var(--dbg);color:var(--dfg);border:1px solid var(--dfg);border-radius:12px;padding:10px 13px;margin:0 0 12px;font-weight:700;font-size:14.5px}
.alertbar.on{display:block}
.alertbar .sub{display:block;font-weight:400;font-size:12.5px;margin-top:2px;white-space:normal;overflow:hidden;text-overflow:ellipsis}
/* מקופל כברירת מחדל: שורת סיכום אחת, והרשימה נפתחת בהקשה. */
.ahead{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.ahead .chev{margin-inline-start:auto;transition:transform .2s;font-size:13px}
.alertbar.collapsed .chev{transform:rotate(-90deg)}
.alertbar.collapsed .alist{display:none}
.alist{margin-top:10px;max-height:48vh;overflow:auto}
.alertbar .arow{display:flex;gap:8px;align-items:flex-start}
.alertbar .arow+.arow{margin-top:8px;padding-top:8px;border-top:1px solid var(--dfg)}
.alertbar .arow>div{flex:1;min-width:0}
.alertbar .arow .at{font-size:13.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.alertbar .ax{flex:none;width:30px;height:30px;border:1px solid var(--dfg);border-radius:8px;background:transparent;color:var(--dfg);font:inherit;font-weight:700;cursor:pointer;line-height:1}
/* מחיקה קבוצתית (12.11.2026): תיבת סימון בכל שורה, ושורת פעולה מעל הרשימה שלא נגללת איתה */
.alertbar .acb{flex:none;display:flex;align-items:center;justify-content:center;width:30px;height:30px;cursor:pointer}
.alertbar input[type=checkbox]{width:20px;height:20px;margin:0;accent-color:var(--dfg);cursor:pointer}
.abulk{display:flex;align-items:center;gap:10px;margin-top:10px;padding-bottom:10px;border-bottom:1px solid var(--dfg);font-weight:400;font-size:13.5px}
.abulk label{display:flex;align-items:center;gap:8px;min-height:36px;padding-inline-start:5px;cursor:pointer}
.abulk .adel{margin-inline-start:auto;min-height:36px;padding:0 14px;border:1px solid var(--dfg);border-radius:8px;background:var(--dfg);color:var(--bg);font:inherit;font-weight:700;cursor:pointer}
.abulk .adel:disabled{background:transparent;color:var(--dfg);opacity:.55;cursor:default}
.alertbar.collapsed .abulk{display:none}
.alertbar .alink{display:inline-flex;align-items:center;min-height:30px;margin-top:4px;font-size:13px;font-weight:700;color:var(--dfg);text-decoration:underline;text-underline-offset:3px}

/* ---------- כותרת ---------- */
h1{font-size:clamp(23px,5.4vw,31px);font-weight:800;margin:4px 0 2px;letter-spacing:-.01em}
.sub{font-size:13.5px;color:var(--tx2);margin:0 0 14px}
h2{font-size:16px;font-weight:800;margin:0 0 4px}
/* קיפול כרטיס — אותה תבנית כמו פס ההתראות: כותרת + מספר + חץ, לחיצה פותחת. מקופל כברירת מחדל. */
.foldhead{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.foldhead .foldn{font-size:13px;font-weight:600;color:var(--tx3)}
.foldhead .foldchev{margin-inline-start:auto;font-size:13px;color:var(--tx3);transition:transform .2s}
.foldcard.collapsed .foldchev{transform:rotate(-90deg)}
.foldcard.collapsed .foldbody{display:none}
.foldcard.collapsed{padding-bottom:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:14px;margin:0 0 12px;box-shadow:var(--shadow)}
.eyebrow{font-size:12.5px;font-weight:700;color:var(--tx2);margin:0 0 8px;line-height:1.35}
.ctlrow{display:flex;flex-wrap:wrap;gap:9px;align-items:center}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:11px;overflow:hidden;background:var(--bg)}
.seg button{font:inherit;font-size:14px;font-weight:600;min-height:44px;padding:0 13px;border:0;background:transparent;color:var(--tx2);cursor:pointer}
.seg button+button{border-inline-start:1px solid var(--line2)}
.seg button[aria-pressed="true"]{background:#111;color:#fff}
@media (prefers-color-scheme:dark){.seg button[aria-pressed="true"]{background:#e9efeb;color:#0f1512}}
.dates{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:9px}
.dates label{font-size:13px;color:var(--tx2);display:flex;align-items:center;gap:6px}
.dates input{font:inherit;font-size:14px;min-height:44px;padding:0 10px;border:1px solid var(--line2);border-radius:11px;background:var(--bg);color:var(--tx)}
.dates .go{font:inherit;font-size:14px;font-weight:700;min-height:44px;padding:0 16px;border:0;border-radius:11px;background:var(--brand);color:#fff;cursor:pointer}
.hint{font-size:12.5px;color:var(--tx3);margin:6px 0 0}
.explain{display:none;font-size:13px;color:var(--tx2);background:var(--bg);border:1px dashed var(--line2);border-radius:10px;padding:9px 11px;margin:8px 0 0;line-height:1.6}
body.explain-on .explain{display:block}

/* ---------- עכשיו (דורון 18.9.2026, שאלות 44–47) ---------- */
.now{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.nbox{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 13px;min-height:84px}
.nbox .k{font-size:12px;color:var(--tx2);margin:0 0 4px}
.nbox .v{font-size:24px;font-weight:800;line-height:1.1;display:flex;align-items:center;gap:8px}
.nbox .m{font-size:12px;color:var(--tx3);margin-top:4px}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;flex:none}
.dot.ok{background:var(--okfg)}.dot.w{background:var(--wfg)}.dot.d{background:var(--dfg)}.dot.n{background:var(--tx3)}
.npages{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.nowtick{font-size:12px;color:var(--tx3);margin-top:8px}

/* ---------- שורה תחתונה ---------- */
.verdict{display:flex;flex-wrap:wrap;gap:10px}
.vbox{flex:1 1 150px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 13px;min-height:84px;cursor:pointer;text-align:start;font:inherit;color:var(--tx)}
.vbox:hover{border-color:var(--line2)}
.vbox .k{font-size:12px;color:var(--tx2);margin:0 0 4px}
.vbox .v{font-size:26px;font-weight:800;line-height:1.1;letter-spacing:-.01em}
.vbox .m{font-size:12px;color:var(--tx3);margin-top:4px}
.tag{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px;border:1px solid transparent}
.tag.ok{background:var(--okbg);color:var(--okfg);border-color:var(--okfg)}
.tag.w{background:var(--wbg);color:var(--wfg);border-color:var(--wfg)}
.tag.d{background:var(--dbg);color:var(--dfg);border-color:var(--dfg)}
.tag.n{background:var(--bg);color:var(--tx3);border-color:var(--line2)}
.est{color:var(--tx3)}

/* ---------- טבלאות ---------- */
.tblwrap{overflow-x:auto;margin:0 -2px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:right;padding:8px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--tx2);font-weight:700}
td.num,th.num{direction:ltr;text-align:left;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
tr.rowbtn{cursor:pointer}
tr.rowbtn:hover td{background:var(--bg)}
td a{color:var(--tx);text-decoration:none;border-bottom:1px dotted var(--tx3)}
.muted{color:var(--tx3);font-size:13px;overflow-wrap:anywhere;word-break:break-word}
.empty{color:var(--tx2);font-size:13.5px;padding:8px 0}
.more{font-size:12px;color:var(--tx3);margin:6px 0 0}

/* ---------- גרפים ---------- */
.chart{width:100%;height:auto;display:block;margin-top:6px}
.chart text{font-family:var(--font);fill:var(--tx2);font-size:11px}
.chart .grid{stroke:var(--line);stroke-width:1}
.chart .ref{stroke:var(--tx3);stroke-width:1;stroke-dasharray:3 4}
.chart .reft{fill:var(--tx3);font-size:10px}
.chart .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart .bar{fill:var(--down);cursor:pointer}
.chart .bar:hover{opacity:.75}
.chart .ms{fill:none;stroke:var(--brand);stroke-width:2}
.chart .hit{fill:transparent;cursor:pointer}
.chart .pt{cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 0}
.legend button{font:inherit;font-size:12.5px;min-height:34px;padding:0 11px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--tx2);cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.legend button i{width:10px;height:10px;border-radius:50%;display:inline-block}
.legend button[aria-pressed="false"]{opacity:.45}
.list{margin:0;padding:0;list-style:none}
.list li{padding:8px 0;border-bottom:1px solid var(--line);font-size:13.5px;display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}
.list li>*{min-width:0;max-width:100%}
.list li.rowbtn{cursor:pointer}
.list li:last-child{border-bottom:0}
.list li>*{min-width:0;overflow-wrap:anywhere}/*long-url*/
.list .when{color:var(--tx3);font-size:12px;direction:ltr}

/* ---------- חלון העומק (דריל) ---------- */
.dov{position:fixed;inset:0;background:rgba(10,18,14,.5);z-index:130;display:none}
.dov.on{display:block}
.dsheet{position:absolute;inset-inline:0;bottom:0;max-height:88vh;overflow:auto;background:var(--bg);border-radius:18px 18px 0 0;border:1px solid var(--line);border-bottom:0;box-shadow:var(--shadow);padding:14px 14px 28px}
@media (min-width:720px){.dsheet{inset-inline:auto;left:50%;transform:translateX(-50%);width:720px;bottom:auto;top:6vh;border-radius:18px;border-bottom:1px solid var(--line)}}
.dhd{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 8px;padding-bottom:9px;border-bottom:1px solid var(--line)}
.dhd b{font-size:17px}
.dsum{font-size:14.5px;line-height:1.6;margin:0 0 10px}
.dsum b{font-weight:800}
.dwhat{font-size:13px;color:var(--tx2);background:var(--surface);border-radius:10px;padding:9px 11px;margin:0 0 12px;line-height:1.6}
.dsheet h3{font-size:13.5px;font-weight:800;margin:14px 0 6px;color:var(--tx2)}

/* ---------- חיווי טעינה ---------- */
.loadbar{position:fixed;top:0;left:0;right:0;height:3px;background:var(--brand);transform:scaleX(0);transform-origin:right;transition:transform .4s;z-index:200}
body.loading .loadbar{animation:lb 1.2s ease-in-out infinite}
@keyframes lb{0%{transform:scaleX(0);transform-origin:right}50%{transform:scaleX(1);transform-origin:right}51%{transform-origin:left}100%{transform:scaleX(0);transform-origin:left}}
.loadpill{position:fixed;top:12px;left:50%;transform:translateX(-50%);background:#111;color:#fff;font-size:13px;font-weight:700;padding:8px 14px;border-radius:999px;display:none;z-index:200;box-shadow:var(--shadow)}
body.loading .loadpill{display:flex;align-items:center;gap:8px}
.loadpill i{width:12px;height:12px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .8s linear infinite;display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
body.loading .card{opacity:.55;transition:opacity .2s}
.stale{font-size:12px;color:var(--wfg);background:var(--wbg);border-radius:8px;padding:4px 9px;display:none;margin:0 0 8px}
body.loading .stale{display:inline-block}

/* ---------- טלפון: קיבוע למסך וריווח נקי ---------- */
@media (max-width:640px){
  .wrap{padding:10px 11px 40px}
  .card{padding:13px 12px;margin:0 0 11px}
  h1{margin-top:2px}
  .sub{margin-bottom:12px}
  /* טבלאות רחבות נשארות בתוך הכרטיס וגוללות אופקית בלבד — לא חותכות את העמוד */
  .tblwrap{-webkit-overflow-scrolling:touch;scrollbar-width:thin}
  th,td{padding:8px 7px}
  /* גוף ההתראה/ההודעה: שורה שלמה, נשבר יפה, לא דוחף לרוחב */
  .list li>.muted,.list li>.when{flex-basis:100%}
}
/* רשת ביטחון: שום אלמנט לא יגלוש את רוחב המסך בטלפון */
html,body{overflow-x:hidden}

/* ---------- ייצוא PDF: הדפסה נקייה עם כל הנתונים פרושים ---------- */
@media print{
  @page{size:A4 landscape;margin:10mm}
  :root{--bg:#fff!important;--surface:#fff!important;--line:#cfcfcf!important;--line2:#bcbcbc!important;
        --tx:#111!important;--tx2:#3a3a3a!important;--tx3:#6a6a6a!important;--shadow:none!important}
  body{background:#fff!important;color:#111!important}
  .shbar,.loadbar,.loadpill,.stale,.explain{display:none!important}
  #ctlCard{display:none!important}
  .seg,.dates,.foldchev,.ahead .chev,.alertbar .ax,.alertbar .acb,.abulk{display:none!important}
  .shov,.dov{display:none!important}
  .foldcard.collapsed .foldbody{display:block!important}
  .alertbar.collapsed .alist{display:block!important}
  /* בלי שום חיתוך — כל האירועים וכל שורות הטבלה נכנסים ל-PDF */
  .alist,.list,.foldbody,.tblwrap,.alertbar{max-height:none!important;overflow:visible!important}
  .card{box-shadow:none!important;border:1px solid #cfcfcf!important;break-inside:avoid;margin-bottom:9px}
  table{font-size:9.5px;width:100%}
  th,td{padding:5px 6px!important;white-space:normal!important}
  a{color:#111!important;text-decoration:none}
  h1{font-size:22px}
  .chart{max-height:200px}
}
</style>
<!--SH_INJECT-->
</head>
<body>
<div class="loadbar" aria-hidden="true"></div>
<div class="loadpill" role="status"><i></i><span id="loadtxt">טוען נתונים…</span></div>
<div class="wrap">

  <div class="hdr">
    <div class="shbrand"><span class="shword" id="brandTxt"></span></div>
    <div class="brandcol"><a class="out" id="outLink" href="/logout">יציאה</a></div>
  </div>

  <div class="shbar">
    <button type="button" class="shham" id="shham" aria-label="תפריט" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 7h17"/><path d="M3.5 12h17"/><path d="M3.5 17h17"/></svg>
    </button>
    <div class="shnow"><span class="v">בריאות האתר</span></div>
    <div class="shacts">
      <span id="xlinks" style="display:contents"></span>
      <button type="button" class="shxls" id="explbtn" aria-pressed="false" title="הסבר פשוט לכל מספר">הסברים</button>
      <button type="button" class="shxls" id="refbtn" title="רענון">רענון</button>
      <button type="button" class="shxls" id="pdfbtn" title="ייצוא כל הדוח כ-PDF לשליחה">ייצא PDF</button>
    </div>
  </div>

  <div class="alertbar" id="alertbar" title="לחיצה: פרטים"></div>

  <h1>בריאות האתר</h1>
  <p class="sub" id="sub">טוען…</p>

  <section class="card" id="nowcard">
    <h2>עכשיו</h2>
    <div class="now" id="now"><div class="nbox"><div class="k">האתר עכשיו</div><div class="v"><span class="dot n"></span>טוען…</div></div></div>
    <div class="npages" id="nowpages"></div>
    <p class="nowtick" id="nowtick"></p>
    <p class="explain">"עכשיו" = סבב הבדיקה האחרון של המערכת, כל דקה, <span data-cfg="probeCount">4</span> עמודים. "תגובת שרת" = כמה זמן עובר מהבקשה עד שהשרת מתחיל לענות: ירוק עד 0.5 שנ', צהוב עד 1.5, אדום מעל או כשעמוד לא עונה. "מהירות אצל לקוחות" = מה שגולשים אמיתיים חוו בשעה האחרונה, זמן עד תוכן ראשי, אחוזון 75, נמדד בדפדפן של הגולש על ידי קוד מדידה קטן שמותקן באתר. מתחת למספר כתוב מאיזה אתר הגיעו המדידות. מתרענן לבד כל 60 שניות.</p>
  </section>

  <section class="card" id="ctlCard">
    <div class="ctlrow">
      <div class="seg" id="segH">
        <button type="button" data-h="24" aria-pressed="true">24 שעות</button>
        <button type="button" data-h="168" aria-pressed="false">7 ימים</button>
        <button type="button" data-h="720" aria-pressed="false">30 יום</button>
        <button type="button" data-h="2160" aria-pressed="false">90 יום</button>
      </div>
      <div class="seg" id="segS">
        <button type="button" data-s="mobile" aria-pressed="true">טלפון</button>
        <button type="button" data-s="desktop" aria-pressed="false">מחשב</button>
      </div>
    </div>
    <div class="dates">
      <label>מתאריך <input type="date" id="dFrom"></label>
      <label>עד <input type="date" id="dTo"></label>
      <button type="button" class="go" id="dGo">הצג</button>
    </div>
    <p class="hint" id="rangeTxt"></p>
    <p class="explain">התקופה קובעת את כל המסך. "טלפון" ו"מחשב" משנים רק את מדדי המהירות; הזמינות זהה לשניהם. כל מספר, שורה ונקודה בגרף לחיצים: לחיצה פותחת את הפירוט מאחוריהם.</p>
  </section>

  <section class="card" id="verdictCard">
    <h2>שורה תחתונה</h2>
    <div class="verdict" id="verdict"></div>
    <p class="explain">"מהירות" = כמה זמן עד שהתוכן העיקרי בעמוד הבית מוצג בטלפון. עד 2 שניות: מצוין. עד 2.5: מהיר (הסף של גוגל). עד 4: בינוני. מעל 4: איטי. "זמינות" = כמה מהבדיקות (כל דקה, <span data-cfg="probeCount">4</span> עמודים) ענו תקין.</p>
  </section>

  <section class="card" id="availCard">
    <h2>זמינות</h2>
    <div id="availTbl"></div>
    <div id="outages"></div>
    <div id="availChart"></div>
    <p class="hint">לחיצה על שורה: הכשלים של העמוד. לחיצה על עמודה אדומה: הכשלים באותה שעה/יום. לחיצה על הקו הירוק: זמן התגובה לפי עמוד.</p>
    <p class="explain">כל דקה נבדקים <span data-cfg="probeCount">4</span> עמודים. "נפילה" = 3 דקות רצופות שבהן אף עמוד לא ענה. בגרף: עמודות אדומות = בדיקות שנכשלו; קו ירוק = זמן תגובת השרת החציוני. הבודק הוא לקוח בודד מהענן: הוא רואה שהשרת עונה, לא כמה מהר האתר נטען אצל לקוח.</p>
  </section>

  <section class="card" id="speedCard">
    <h2>מהירות לאורך זמן</h2>
    <div class="legend" id="legend"></div>
    <div id="speedChart"></div>
    <p class="hint" id="speedHint" hidden>לחיצה על נקודה: המדידות של אותו עמוד באותה שעה/יום, ומה האט אותו.</p>
    <p class="explain">כל נקודה = חציון המדידות באותה שעה (או יום, בתקופות ארוכות) של הזמן עד הצגת התוכן העיקרי, בשניות. הקווים המקווקווים: 2.5 = הסף של גוגל ל"מהיר", 4 = מכאן "איטי". המדידה מדמה טלפון ממוצע ברשת סלולרית איטית, ולכן קשוחה מהמציאות אצל רוב הלקוחות. היא נועדה לראות מגמה, לא לפסוק.</p>
  </section>

  <section class="card" id="coreCard">
    <h2>העמודים העיקריים</h2>
    <div id="coreTbl"></div>
    <p class="explain">ציון = ציון הביצועים של גוגל (0–100, 90 ומעלה מצוין). LCP = זמן עד הצגת התוכן העיקרי. p50 = חציון, p95 = הגרוע מבין 95 אחוז מהמדידות. קפיצות = כמה העמוד "קופץ" בזמן טעינה (עד 0.1 טוב). שרת = זמן עד הבייט הראשון. "גולשים אמיתיים" = מה שגוגל מודדת אצל מבקרים אמיתיים בכרום (יש רק כשיש מספיק תנועה). לחיצה על שורה: כל המדידות ומה מאט את העמוד.</p>
  </section>

  <section class="card" id="slowCard">
    <h2>העמודים הכבדים באתר</h2>
    <p class="muted" id="coverage"></p>
    <div id="slowTbl"></div>
    <p class="explain">כל עמוד באתר (מוצרים, קטגוריות, עמודים) נמדד בסבב: 2 עמודים כל 5 דקות, כל האתר בערך פעם ביום. כאן 10 הכבדים ביותר בתקופה. עמוד כבד כמעט תמיד אומר תמונות גדולות מדי. לחיצה על שורה: מה בדיוק מאט אותו.</p>
  </section>

  <section class="card" id="issuesCard">
    <h2>מוצרים שבורים באתר</h2>
    <div id="issuesTbl"></div>
    <p class="explain">נבדק פעם ביום (04:00) על כל הקטלוג הציבורי: מוצר בלי מחיר, בלי תמונה, לא במלאי, או שאי אפשר להוסיף לסל. "לא במלאי" אינו בהכרח תקלה, אבל לקוח שרואה את זה עוזב.</p>
  </section>

  <section class="card" id="certCard">
    <h2>תעודת האבטחה (המנעול)</h2>
    <div id="certBox"></div>
    <p class="explain">התעודה היא מה שנותן לאתר את המנעול בדפדפן. כשהיא פגה, הדפדפן מציג ללקוח אזהרה אדומה במקום האתר. נבדקת פעם ביום; התראה מתחת ל-14 יום.</p>
  </section>

  <section class="card foldcard collapsed" id="alertsCard">
    <h2 class="foldhead">התראות<span class="foldn" id="alertsN"></span><span class="foldchev">▾</span></h2>
    <div id="alertsList" class="foldbody"></div>
    <p class="explain">התראה נפתחת ברגע שבדיקת זמינות אחת נכשלת, כשעמוד עיקרי איטי (מעל 4 שניות) פעמיים ברצף, כשהמדידה עצמה נעצרה, או כשתעודת האבטחה עומדת לפוג. נסגרת לבד כשהמצב חוזר לתקין. ההודעות מגיעות לטלפון של כל מי שמנוי לערוץ. לחיצה: מה בדיוק קרה. ✕ בפס האדום = "ראיתי": מסתיר לכולם עד שההתראה תיסגר ותיפתח מחדש. בטלפון, הודעות ישנות נמחקות מתוך אפליקציית ntfy (החלקה או "נקה הכל").</p>
  </section>

  <section class="card foldcard collapsed" id="msgCard">
    <h2 class="foldhead">הודעות שנשלחו לטלפון<span class="foldn" id="msgN"></span><span class="foldchev">▾</span></h2>
    <div id="msgList" class="foldbody"></div>
    <p class="explain">כל מה שהמערכת שלחה לערוץ ההתראות בתקופה שנבחרה: התראות, "חזר לתקין", והודעות הבוקר. גם אם נמחקו מהטלפון, הן כאן.</p>
  </section>
  <section class="card" id="healthCard">
    <h2>המדידה עצמה</h2>
    <div id="healthTbl"></div>
    <p class="explain">אם שורה כאן "שקטה", המספרים למעלה ישנים, לא רעים. קודם מתקנים את המדידה, אחר כך קוראים מספרים. לחיצה: מה השורה מודדת ומה עושים.</p>
  </section>

</div>

<div class="shov" id="shov">
  <div class="shsheet" role="dialog" aria-modal="true" aria-label="תפריט">
    <div class="shhead"><b>תפריט</b>
      <button type="button" class="shx" id="shx" aria-label="סגירה">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"/><path d="M18 6L6 18"/></svg>
      </button>
    </div>
    <div id="shlist"></div>
  </div>
</div>

<div class="dov" id="dov">
  <div class="dsheet" id="dsheet" role="dialog" aria-modal="true" aria-labelledby="dttl">
    <div class="dhd"><b id="dttl"></b>
      <button type="button" class="shx" id="dx" aria-label="סגירה">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12"/><path d="M18 6L6 18"/></svg>
      </button>
    </div>
    <div id="dbody"></div>
  </div>
</div>

<script>
/* ---------- הגדרות האתר (SH_CONFIG) ----------
   כל מה שמשתנה מאתר לאתר נמצא כאן. השרת יכול לדרוס כל שדה: הוא מזריק לפני סוף ה-head
   תגית סקריפט שקובעת  window.SH_CONFIG = {siteLabel: 'my-site.co.il', ...}  */
var CFG = (function(){
  var d = {
    siteLabel: 'example.co.il',  // מוצג מתחת לכותרת ובכותרת הלשונית
    brand: '',                   // טקסט קטן בראש המסך (שם העסק או המערכת). ריק = בלי
    homePage: 'בית',             // הערך של השדה page בעמוד הבית, בדיוק כפי שהשרת מחזיר אותו
    probeCount: 4,               // כמה עמודים בודק הזמינות (לטקסטי ההסבר בלבד)
    coreCount: 5,                // כמה עמודי ליבה נמדדים במהירות (לטקסטי ההסבר בלבד)
    liveHosts: [],               // ערכי המקור שנחשבים "האתר החי" במדידות אצל לקוחות. ריק = ['live', siteLabel, 'www.' + siteLabel]
    pathLabels: [['/product-category/', 'קטגוריה: '], ['/product/', 'מוצר: ']],  // קיצור כתובת לשם קריא
    bucketNote: '',              // הערה בתחתית חלון "זמן תגובת השרת". ריק = בלי
    nav: [],                     // תפריט: [['g','כותרת קבוצה'], ['a','/path','שם מסך'], ...]. ריק = בלי כפתור תפריט
    here: '/site',               // הכתובת של המסך הזה בתפריט
    links: [],                   // כפתורים נוספים בשורה העליונה: [{href:'/x', label:'שם', title:'הסבר'}]
    api: '/api',                 // בסיס כתובות הנתונים
    loginPath: '/login',
    logoutPath: '/logout',
    shareKey: '',                // טוקן של קישור שיתוף; מצורף לכל קריאת נתונים כ-k=
    hide: []                     // כרטיסים שלא רלוונטיים לאתר הזה, לפי מזהה: 'issuesCard' (אתר בלי חנות), 'slowCard'
  };
  var o = window.SH_CONFIG || {};
  Object.keys(o).forEach(function(k){ d[k] = o[k]; });
  if (!d.liveHosts || !d.liveHosts.length) d.liveHosts = ['live', d.siteLabel, 'www.' + d.siteLabel];
  return d;
})();
/* תפקיד הצופה. השרת מזריק באותה תגית:  window.SH_ROLE = {readonly: true}
   readonly = בלי מחיקת התראות ובלי יומן ההודעות · share = קישור שיתוף (גם בלי "יציאה") · noAlerts = בלי התראות בכלל.
   זה רק מסתיר על המסך. את אותם כללים בדיוק השרת חייב לאכוף בעצמו. */
var ROLE = window.SH_ROLE || {};
if (ROLE.share) ROLE.readonly = true;
(function(){
  var esc0 = function(v){ return String(v == null ? '' : v).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); };
  var root = document.documentElement;
  if (ROLE.readonly) root.classList.add('ro');
  if (ROLE.share) root.classList.add('share');
  if (ROLE.noAlerts) root.classList.add('noalerts');
  (CFG.hide || []).forEach(function(id){ var el = document.getElementById(id); if (el) el.style.display = 'none'; });
  document.title = 'בריאות האתר — ' + CFG.siteLabel;
  document.getElementById('brandTxt').textContent = CFG.brand || '';
  document.getElementById('outLink').setAttribute('href', CFG.logoutPath);
  Array.prototype.forEach.call(document.querySelectorAll('[data-cfg]'), function(el){ var v = CFG[el.getAttribute('data-cfg')]; if (v != null) el.textContent = v; });
  document.getElementById('xlinks').innerHTML = (ROLE.readonly ? [] : CFG.links).map(function(l){ return '<a class="shxls" href="' + esc0(l.href) + '" title="' + esc0(l.title || '') + '" style="text-decoration:none">' + esc0(l.label) + '</a>'; }).join('');
  /* תפריט: רק כשיש מסכים נוספים, ורק למי שאינו צופה חיצוני */
  var nav = ROLE.readonly ? [] : CFG.nav, h = '', pend = null;
  nav.forEach(function(it){
    if (it[0] === 'g') { pend = it[1]; return; }
    if (pend) { h += '<div class="shg">' + esc0(pend) + '</div>'; pend = null; }
    h += it[1] === CFG.here
      ? '<a href="' + esc0(it[1]) + '" class="shcur" aria-current="page">' + esc0(it[2]) + '</a>'
      : '<a href="' + esc0(it[1]) + '">' + esc0(it[2]) + '</a>';
  });
  document.getElementById('shlist').innerHTML = h;
  var ham = document.getElementById('shham'), ov = document.getElementById('shov');
  ham.hidden = !h;
  function open(){ ov.classList.add('on'); document.body.style.overflow = 'hidden'; }
  function close(){ ov.classList.remove('on'); document.body.style.overflow = ''; }
  ham.addEventListener('click', open);
  document.getElementById('shx').addEventListener('click', close);
  ov.addEventListener('click', function(e){ if (e.target === ov) close(); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && ov.classList.contains('on')) close(); });
})();
/* כתובת נתונים: בסיס מההגדרות, ובקישור שיתוף גם הטוקן */
function api(path){ var u = CFG.api + path; if (CFG.shareKey) u += (u.indexOf('?') < 0 ? '?' : '&') + 'k=' + encodeURIComponent(CFG.shareKey); return u; }

/* ---------- עזרים ---------- */
var $ = function(id){ return document.getElementById(id); };
var state = { h: 24, f: '', t: '', s: 'mobile', hidden: {}, seq: 0, data: null };
var COLORS = ['#0d9668', '#4a3aa7', '#c2410c', '#0369a1', '#7c3aed', '#be185d'];
var NF = new Intl.NumberFormat('he-IL');
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function sec(ms){ return ms == null ? '—' : (ms / 1000).toFixed(1); }
function n(v){ return v == null ? '—' : NF.format(v); }
function lcpTag(ms){
  if (ms == null) return '<span class="tag n">אין</span>';
  if (ms <= 2000) return '<span class="tag ok">מצוין</span>';
  if (ms <= 2500) return '<span class="tag ok">מהיר</span>';
  if (ms <= 4000) return '<span class="tag w">בינוני</span>';
  return '<span class="tag d">איטי</span>';
}
function lcpWord(ms){ return ms == null ? 'אין נתונים' : ms <= 2000 ? 'מהיר מצוין' : ms <= 2500 ? 'מהיר' : ms <= 4000 ? 'בינוני' : 'איטי'; }
function cruxTag(c){
  if (!c) return '<span class="tag n">אין מספיק תנועה</span>';
  return c === 'FAST' ? '<span class="tag ok">מהיר</span>' : c === 'AVERAGE' ? '<span class="tag w">בינוני</span>' : '<span class="tag d">איטי</span>';
}
function short(u){ try { var p = decodeURIComponent(new URL(u).pathname), i, x; for (i = 0; i < CFG.pathLabels.length; i++) { x = CFG.pathLabels[i]; if (p.indexOf(x[0]) === 0) { p = x[1] + p.slice(x[0].length); break; } } return p.replace(/\/$/, '').replace(/-/g, ' ') || CFG.homePage; } catch (e) { return u; } }
/* כתובת מקודדת בגוף ההתראה (product-category/%d7%…) נראית כג'יבריש בטלפון.
   מחליפים כל כתובת בשם עמוד קריא, ומוותרים עליה כשהיא רק חוזרת על הכותרת. */
function niceBody(t, title){
  var s = String(t || '').replace(/https?:\/\/[^\s]+/g, function(u){ return short(u); });
  if (title) { s = s.split('\n').filter(function(l){ return l.trim() && ('· ' + l.trim()).indexOf(String(title).trim()) < 0; }).join(' · '); }
  return s.replace(/\s*·\s*·\s*/g, ' · ').trim();
}
function qs(){ return state.f ? '&f=' + state.f + '&t=' + state.t : '&h=' + state.h; }
function periodTxt(){ return state.f ? 'מ-' + state.f.split('-').reverse().join('.') + ' עד ' + state.t.split('-').reverse().join('.') : state.h === 24 ? '24 השעות האחרונות' : state.h / 24 + ' הימים האחרונים'; }
function bucketTxt(b){ return b.length > 10 ? 'ב-' + b.slice(8, 10) + '.' + b.slice(5, 7) + ' בשעה ' + b.slice(11, 16) : 'ב-' + b.slice(8, 10) + '.' + b.slice(5, 7); }
/* תרגום "מה מאט את העמוד" (Lighthouse) לעברית פשוטה */
var OPP = {
  'render-blocking-resources': 'קבצים שחוסמים את הציור הראשון (סקריפטים וסגנון בראש העמוד)',
  'unused-css-rules': 'סגנון (CSS) שלא בשימוש נטען בכל זאת',
  'unused-javascript': 'קוד (JavaScript) שלא בשימוש נטען בכל זאת',
  'modern-image-formats': 'תמונות בפורמט ישן (JPG/PNG) במקום WebP/AVIF',
  'uses-optimized-images': 'תמונות לא דחוסות מספיק',
  'uses-responsive-images': 'תמונות גדולות מדי לגודל שבו הן מוצגות',
  'offscreen-images': 'תמונות מחוץ למסך נטענות מיד במקום בגלילה',
  'server-response-time': 'השרת עונה לאט (זמן עד הבייט הראשון)',
  'uses-text-compression': 'קבצי טקסט נשלחים בלי דחיסה',
  'uses-rel-preconnect': 'חיבור מוקדם לשרתים חיצוניים חסר',
  'redirects': 'הפניות (redirect) לפני שהעמוד נטען',
  'uses-long-cache-ttl': 'קבצים לא נשמרים בזיכרון הדפדפן לזמן ארוך',
  'efficient-animated-content': 'אנימציות GIF במקום וידאו',
  'duplicated-javascript': 'קוד כפול',
  'legacy-javascript': 'קוד ישן שנשלח גם לדפדפנים חדשים',
  'prioritize-lcp-image': 'התמונה הראשית לא נטענת בעדיפות',
  'total-byte-weight': 'העמוד כבד מאוד בסך הכל',
  'dom-size': 'העמוד מורכב מיותר מדי אלמנטים',
  'third-party-summary': 'קוד של צד שלישי (פיקסלים, צ\'אט, אנליטיקס) מאט',
  'bootup-time': 'הדפדפן עסוק בהרצת קוד',
  'mainthread-work-breakdown': 'הדפדפן עסוק מדי בזמן הטעינה',
  'font-display': 'הטקסט מחכה לגופן שייטען',
  'unminified-css': 'קובצי סגנון (CSS) לא מכווצים',
  'unminified-javascript': 'קובצי קוד (JavaScript) לא מכווצים',
  /* מ-Lighthouse 13 (אוקטובר 2025) רוב הסיבות הישנות הוחלפו ב"תובנות" (insight) */
  'render-blocking-insight': 'קבצים שחוסמים את הציור הראשון (סקריפטים וסגנון בראש העמוד)',
  'image-delivery-insight': 'תמונות כבדות מדי: לדחוס, להקטין לגודל התצוגה, לעבור ל-WebP/AVIF',
  'document-latency-insight': 'העמוד עצמו מגיע לאט מהשרת (תגובה איטית, הפניות, או בלי דחיסה)',
  'network-dependency-tree-insight': 'שרשרת ארוכה של קבצים שמחכים זה לזה',
  'cache-insight': 'קבצים לא נשמרים בזיכרון הדפדפן לזמן ארוך',
  'duplicated-javascript-insight': 'קוד כפול',
  'legacy-javascript-insight': 'קוד ישן שנשלח גם לדפדפנים חדשים',
  'lcp-discovery-insight': 'התמונה הראשית מתגלה מאוחר או לא נטענת בעדיפות',
  'lcp-breakdown-insight': 'התוכן העיקרי מתעכב (פירוט השלבים בדוח של גוגל)',
  'dom-size-insight': 'העמוד מורכב מיותר מדי אלמנטים',
  'third-parties-insight': 'קוד של צד שלישי (פיקסלים, צ\'אט, אנליטיקס) מאט',
  'font-display-insight': 'הטקסט מחכה לגופן שייטען',
  'forced-reflow-insight': 'קוד שמכריח את הדפדפן לחשב מחדש את פריסת העמוד',
  'cls-culprits-insight': 'אלמנטים שגורמים לעמוד לקפוץ בזמן הטעינה',
  'inp-breakdown-insight': 'העמוד מגיב לאט ללחיצות',
  'viewport-insight': 'העמוד לא מוגדר נכון לרוחב של טלפון',
  'modern-http-insight': 'קבצים נשלחים בפרוטוקול ישן (HTTP/1.1)'
};
function oppName(o){ return OPP[o.id] || o.title || o.id; }

/* ---------- טעינה ---------- */
function load(){
  var seq = ++state.seq; document.body.classList.add('loading'); var lt = $('loadtxt'); if (lt) lt.textContent = 'טוען נתונים…';
  $('sub').textContent = CFG.siteLabel + ' · טוען…';
  $('rangeTxt').textContent = 'מוצג: ' + periodTxt();
  fetch(api('/site?strategy=' + state.s + qs()), { cache: 'no-store' })
    .then(function(r){ if (r.status === 401) { if (ROLE.share) throw new Error('הקישור אינו תקין או שפג.'); location.href = CFG.loginPath; throw new Error('auth'); } return r.json(); })
    .then(function(d){ if (seq !== state.seq) return; state.data = d; render(d); document.body.classList.remove('loading'); loadMessages(); })
    .catch(function(e){ if (seq === state.seq) { document.body.classList.remove('loading'); $('sub').textContent = 'לא הצלחתי לטעון את הנתונים. ' + e; } });
}

function render(d){
  var av = Array.isArray(d.availability) ? d.availability : [];
  var perPage = av.filter(function(r){ return r.section === 'לפי עמוד'; });
  var outages = av.filter(function(r){ return r.section !== 'לפי עמוד'; });
  var sp = Array.isArray(d.speed) ? d.speed : [];
  var bottom = sp.filter(function(r){ return r.section === 'שורה תחתונה'; })[0];
  var core = sp.filter(function(r){ return r.section === 'ליבה' && r.strategy === state.s; });
  var slow = sp.filter(function(r){ return r.section === 'האיטיים באתר'; });
  var cover = sp.filter(function(r){ return r.section === 'כיסוי'; })[0];
  var open = Array.isArray(d.alerts_open) ? d.alerts_open : [];
  var recent = Array.isArray(d.alerts_recent) ? d.alerts_recent : [];
  var health = Array.isArray(d.health) ? d.health : [];

  /* פס אדום */
  var ab = $('alertbar');
  /* מ-12.11.2026 (הבקשה): תיבת סימון בכל התראה + "לסמן הכול" + "מחק מסומנות", וגם ה-✕ הבודד.
     המחיקה מיידית על המסך: השורה נעלמת בלי לטעון את כל הדף מחדש, והרשימה נשארת פתוחה.
     קודם כל ✕ טען את כל המסך מחדש וקיפל את הרשימה, ולכן מחיקה של 11 התראות לקחה דקות. */
  var AB = window.__shAb || (window.__shAb = { open: false, sel: {} });
  var vis = open.filter(function(a){ return !a.acked; });
  if (vis.length) {
    var live = {}; vis.forEach(function(a){ live[a.id] = 1; });
    // קישור לעמוד שההתראה מדברת עליו (הבקשה, 12.11.2026). הכתובת יושבת בגוף ההתראה; התראה בלי כתובת — בלי קישור.
    var abLink = function(a){ var m = String(a.body || '').match(/https?:\/\/[^\s"'<>]+/); return m ? '<a class="alink" href="' + esc(m[0]) + '" target="_blank" rel="noopener">לפתוח את העמוד ↗</a>' : ''; };
    Object.keys(AB.sel).forEach(function(k){ if (!live[k]) delete AB.sel[k]; });
    var rows = vis.map(function(a){ return '<div class="arow" data-id="' + a.id + '"><label class="acb" title="לסמן למחיקה"><input type="checkbox" data-id="' + a.id + '"' + (AB.sel[a.id] ? ' checked' : '') + ' aria-label="לסמן למחיקה: ' + esc(a.title) + '"></label><div><span class="at">' + esc(a.title) + '</span><span class="sub">' + esc(niceBody(a.body || '', a.title)) + ' · מאז ' + esc(a.opened_il) + '</span>' + abLink(a) + '</div><button type="button" class="ax" data-id="' + a.id + '" title="למחוק את ההתראה הזו מהרשימה (תחזור אם הבעיה תיפתח מחדש)">✕</button></div>'; }).join('');
    // מקופל כברירת מחדל (שאלה 97, 19.9.2026) — גם התראה אחת. אחרי שנפתח בהקשה הוא נשאר פתוח גם ברענון.
    var abWord = function(n){ return '⚠ ' + n + ' ' + (n === 1 ? 'התראה פעילה' : 'התראות פעילות'); };
    ab.innerHTML = '<div class="ahead"><span class="acount">' + abWord(vis.length) + '</span><span class="chev">▾</span></div>'
      + '<div class="abulk"><label><input type="checkbox" id="abAll"> לסמן הכול</label><button type="button" class="adel" id="abDel" disabled>מחק מסומנות</button></div>'
      + '<div class="alist">' + rows + '</div>';
    ab.classList.add('on'); ab.classList.toggle('collapsed', !AB.open);
    ab.querySelector('.ahead').addEventListener('click', function(){ AB.open = !AB.open; ab.classList.toggle('collapsed', !AB.open); });
    var abSync = function(){
      var n = Object.keys(AB.sel).length, total = ab.querySelectorAll('.arow').length;
      var del = $('abDel'), all = $('abAll'); if (!del || !all) return;
      del.disabled = !n; del.textContent = n ? 'מחק מסומנות (' + n + ')' : 'מחק מסומנות';
      all.checked = !!n && n === total;
    };
    var abAck = function(ids){
      if (!ids.length || ROLE.readonly) return;
      var hit = {}; ids.forEach(function(id){ hit[id] = 1; delete AB.sel[id]; var r = ab.querySelector('.arow[data-id="' + id + '"]'); if (r) r.parentNode.removeChild(r); });
      open.forEach(function(a){ if (hit[a.id]) a.acked = true; });   // גם בנתונים שבזיכרון, כדי שציור מחדש לא יחזיר אותן
      var left = ab.querySelectorAll('.arow').length;
      if (!left) { ab.classList.remove('on'); ab.innerHTML = ''; }
      else { ab.querySelector('.acount').textContent = abWord(left); abSync(); }
      fetch(api('/alerts/ack'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: ids }) })
        .then(function(r){ if (!r.ok) throw new Error('ack ' + r.status); })
        .catch(function(){ open.forEach(function(a){ if (hit[a.id]) a.acked = false; }); load(); });   // נכשל: מחזירים ומרעננים
    };
    Array.prototype.forEach.call(ab.querySelectorAll('.arow'), function(r){ r.addEventListener('click', function(){ drillAlert(+r.getAttribute('data-id')); }); });
    Array.prototype.forEach.call(ab.querySelectorAll('.alink'), function(l){ l.addEventListener('click', function(e){ e.stopPropagation(); }); });
    Array.prototype.forEach.call(ab.querySelectorAll('.acb'), function(l){
      l.addEventListener('click', function(e){ e.stopPropagation(); });
      l.querySelector('input').addEventListener('change', function(){ var id = +this.getAttribute('data-id'); if (this.checked) AB.sel[id] = 1; else delete AB.sel[id]; abSync(); });
    });
    $('abAll').addEventListener('change', function(){
      var on = this.checked; AB.sel = {};
      Array.prototype.forEach.call(ab.querySelectorAll('.acb input'), function(c){ c.checked = on; if (on) AB.sel[+c.getAttribute('data-id')] = 1; });
      abSync();
    });
    $('abDel').addEventListener('click', function(){ abAck(Object.keys(AB.sel).map(Number)); });
    Array.prototype.forEach.call(ab.querySelectorAll('.ax'), function(b){ b.addEventListener('click', function(e){ e.stopPropagation(); abAck([+b.getAttribute('data-id')]); }); });
    abSync();
  } else { ab.classList.remove('on'); ab.innerHTML = ''; }

  /* כותרת */
  var lastProbe = health.filter(function(r){ return r.flow_name === 'בודק זמינות האתר'; })[0];
  var lastIl = lastProbe && lastProbe.last_at ? new Date(lastProbe.last_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : '—';
  $('sub').textContent = CFG.siteLabel + ' · הבדיקה האחרונה ' + lastIl + ' · ' + periodTxt();

  /* שורה תחתונה */
  var checks = perPage.reduce(function(a, r){ return a + (+r.checks || 0); }, 0);
  var failed = perPage.reduce(function(a, r){ return a + (+r.failed || 0); }, 0);
  var upPct = checks ? (100 - 100 * failed / checks) : null;
  var outMin = outages.reduce(function(a, r){ return a + (+r.outage_minutes || 0); }, 0);
  var vh = '';
  vh += '<button type="button" class="vbox" data-drill="home"><div class="k">מהירות עמוד הבית בטלפון</div><div class="v">' + (bottom && bottom.lcp_p50 != null ? esc(bottom.verdict) : '<span class="est">אין נתונים</span>') + '</div><div class="m">' + (bottom && bottom.lcp_p50 != null ? sec(bottom.lcp_p50) + ' שניות עד התוכן · ' + bottom.checks + ' מדידות' : 'מדידת המהירות עדיין לא התחילה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="fails"><div class="k">זמינות</div><div class="v">' + (upPct == null ? '<span class="est">—</span>' : upPct.toFixed(upPct < 99.95 ? 2 : 1) + '%') + '</div><div class="m">' + (checks ? n(failed) + ' כשלים מתוך ' + n(checks) + ' בדיקות' : 'אין בדיקות בתקופה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="outages"><div class="k">נפילות</div><div class="v">' + (outages.length ? '<span style="color:var(--dfg)">' + outages.length + '</span>' : '0') + '</div><div class="m">' + (outages.length ? 'סה"כ ' + outMin + ' דקות' : 'האתר לא נפל בתקופה') + '</div></button>';
  vh += '<button type="button" class="vbox" data-drill="alerts"><div class="k">התראות פתוחות</div><div class="v">' + (open.length ? '<span style="color:var(--dfg)">' + open.length + '</span>' : '0') + '</div><div class="m">' + (recent.length ? recent.length + ' בתקופה' : 'אין התראות בתקופה') + '</div></button>';
  $('verdict').innerHTML = vh;
  Array.prototype.forEach.call($('verdict').querySelectorAll('.vbox'), function(b){ b.addEventListener('click', function(){
    var w = b.getAttribute('data-drill');
    if (w === 'home') { if (bottom && bottom.url) drillRuns(bottom.url, CFG.homePage, null); else openSheet('מהירות עמוד הבית', '<p class="dsum">מדידת המהירות עדיין לא התחילה. היא מחכה למפתח מגוגל. ברגע שהוא יוכנס, כאן יופיעו המדידות של עמוד הבית כל רבע שעה.</p>'); }
    else if (w === 'fails') drillFails(null, null, checks, failed, perPage);
    else if (w === 'outages') drillOutages(outages);
    else drillAlerts(recent, open);
  }); });

  /* זמינות */
  if (perPage.length) {
    var t = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th class="num">בדיקות</th><th class="num">כשלים</th><th class="num">אחוז</th><th class="num">שרת p50</th><th class="num">שרת p95</th><th>כשל אחרון</th></tr></thead><tbody>';
    perPage.forEach(function(r, i){
      t += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(r.page) + '</td><td class="num">' + n(+r.checks) + '</td><td class="num">' + (r.failed > 0 ? '<b style="color:var(--dfg)">' + r.failed + '</b>' : '0') + '</td><td class="num">' + esc(r.fail_pct) + '%</td><td class="num">' + (r.p50_ms == null ? '—' : r.p50_ms + ' ms') + '</td><td class="num">' + (r.p95_ms == null ? '—' : r.p95_ms + ' ms') + '</td><td>' + esc(r.last_fail_il || '—') + '</td></tr>';
    });
    $('availTbl').innerHTML = t + '</tbody></table></div>';
    Array.prototype.forEach.call($('availTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = perPage[+tr.getAttribute('data-i')]; drillFails(r.page, null, +r.checks, +r.failed, [r]); }); });
  } else $('availTbl').innerHTML = '<p class="empty">אין בדיקות זמינות בתקופה.</p>';
  $('outages').innerHTML = outages.length
    ? '<p class="eyebrow" style="margin-top:12px">נפילות (3 דקות ומעלה שאף עמוד לא ענה)</p><ul class="list">' + outages.map(function(o, i){ return '<li class="rowbtn" data-i="' + i + '"><span class="tag d">' + o.outage_minutes + ' דק\'</span><span class="when">' + esc(o.outage_start_il) + ' → ' + esc(o.outage_end_il) + '</span></li>'; }).join('') + '</ul>'
    : '';
  Array.prototype.forEach.call($('outages').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillOutages([outages[+li.getAttribute('data-i')]]); }); });
  var pser = Array.isArray(d.availability_series) ? d.availability_series : [];
  $('availChart').innerHTML = availChart(pser);
  Array.prototype.forEach.call($('availChart').querySelectorAll('[data-bucket]'), function(el){ el.addEventListener('click', function(){
    var b = el.getAttribute('data-bucket'), row = pser.filter(function(r){ return r.bucket === b; })[0];
    if (el.classList.contains('bar')) drillFails(null, b, +row.checks, +row.failed, null); else drillBucket(b, row);
  }); });

  /* מהירות לאורך זמן */
  var series = Array.isArray(d.speed_series) ? d.speed_series : [];
  $('legend').innerHTML = '';
  $('speedHint').hidden = !series.length;
  if (series.length) {
    var pages = []; series.forEach(function(r){ if (pages.indexOf(r.page) < 0) pages.push(r.page); });
    $('legend').innerHTML = pages.map(function(p, i){ return '<button type="button" data-p="' + esc(p) + '" aria-pressed="' + (state.hidden[p] ? 'false' : 'true') + '"><i style="background:' + COLORS[i % COLORS.length] + '"></i>' + esc(p) + '</button>'; }).join('');
    Array.prototype.forEach.call($('legend').querySelectorAll('button'), function(b){ b.addEventListener('click', function(){ var p = b.getAttribute('data-p'); state.hidden[p] = !state.hidden[p]; b.setAttribute('aria-pressed', state.hidden[p] ? 'false' : 'true'); drawSpeed(series, pages); }); });
    drawSpeed(series, pages);
  } else $('speedChart').innerHTML = '<p class="empty">' + (state.s === 'desktop' ? 'אין עדיין מדידות מחשב בתקופה (נמדד פעם בשעה).' : 'מדידת המהירות עדיין לא התחילה.') + '</p>';

  /* עמודי ליבה */
  if (core.length) {
    var c = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th>מצב</th><th class="num">ציון</th><th class="num">LCP p50</th><th class="num">LCP p95</th><th class="num">קפיצות</th><th class="num">שרת</th><th class="num">איטי</th><th>גולשים אמיתיים</th></tr></thead><tbody>';
    core.forEach(function(r, i){
      c += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(r.page) + '</td><td>' + lcpTag(r.lcp_p50) + '</td><td class="num">' + (r.score_med == null ? '—' : r.score_med) + '</td><td class="num">' + sec(r.lcp_p50) + ' ש\'</td><td class="num">' + sec(r.lcp_p95) + ' ש\'</td><td class="num">' + (r.cls_med == null ? '—' : r.cls_med) + '</td><td class="num">' + (r.ttfb_p50 == null ? '—' : r.ttfb_p50 + ' ms') + '</td><td class="num">' + r.slow_runs + '/' + r.checks + '</td><td>' + cruxTag(r.crux_category) + (r.crux_lcp ? ' <span class="muted">' + sec(r.crux_lcp) + ' ש\'</span>' : '') + '</td></tr>';
    });
    $('coreTbl').innerHTML = c + '</tbody></table></div>';
    Array.prototype.forEach.call($('coreTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = core[+tr.getAttribute('data-i')]; drillRuns(r.url, r.page, null); }); });
  } else $('coreTbl').innerHTML = '<p class="empty">אין מדידות ' + (state.s === 'desktop' ? 'מחשב' : 'טלפון') + ' בתקופה.</p>';

  /* הכבדים */
  $('coverage').textContent = cover ? 'נדגמו ' + cover.checks + ' מתוך ' + cover.slow_runs + ' עמודי האתר בתקופה.' : '';
  if (slow.length) {
    var s = '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th>מצב</th><th class="num">LCP p50</th><th class="num">ציון</th><th class="num">מדידות</th><th>אחרונה</th></tr></thead><tbody>';
    slow.forEach(function(r, i){
      s += '<tr class="rowbtn" data-i="' + i + '"><td>' + esc(short(r.page)) + '</td><td>' + lcpTag(r.lcp_p50) + '</td><td class="num">' + sec(r.lcp_p50) + ' ש\'</td><td class="num">' + (r.score_med == null ? '—' : r.score_med) + '</td><td class="num">' + r.checks + '</td><td>' + esc(r.last_il) + '</td></tr>';
    });
    $('slowTbl').innerHTML = s + '</tbody></table></div>';
    Array.prototype.forEach.call($('slowTbl').querySelectorAll('tr.rowbtn'), function(tr){ tr.addEventListener('click', function(){ var r = slow[+tr.getAttribute('data-i')]; drillRuns(r.url, short(r.url), null); }); });
  } else $('slowTbl').innerHTML = '<p class="empty">הסבב על כל האתר עדיין לא התחיל.</p>';

  /* מוצרים שבורים */
  var iss = Array.isArray(d.product_issues) ? d.product_issues : [];
  if (iss.length) {
    var byI = {}; iss.forEach(function(r){ (byI[r.issue] = byI[r.issue] || []).push(r); });
    var ih = '<p class="muted">' + Object.keys(byI).map(function(k){ return k + ': ' + byI[k].length; }).join(' · ') + ' · לפי צילום ' + esc(iss[0].snap_date) + '</p>';
    ih += '<div class="tblwrap"><table><thead><tr><th>מה</th><th>מוצר</th></tr></thead><tbody>';
    iss.slice(0, 60).forEach(function(r){ ih += '<tr><td><span class="tag ' + (r.issue === 'לא במלאי' ? 'w' : 'd') + '">' + esc(r.issue) + '</span></td><td><a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.name) + '</a></td></tr>'; });
    $('issuesTbl').innerHTML = ih + '</tbody></table></div>' + (iss.length > 60 ? '<p class="muted">מוצגים 60 מתוך ' + iss.length + '.</p>' : '');
  } else $('issuesTbl').innerHTML = '<p class="empty">' + (d.product_issues && d.product_issues.error ? 'הבדיקה לא זמינה.' : 'לא נמצאו מוצרים שבורים בצילום האחרון.') + '</p>';

  /* תעודה */
  var ce = d.cert;
  if (ce && ce.host) {
    var dl = ce.days_left, cls = !ce.ok ? 'd' : dl < 14 ? 'd' : dl < 30 ? 'w' : 'ok';
    $('certBox').innerHTML = '<div class="verdict"><div class="vbox" style="cursor:default"><div class="k">תוקף</div><div class="v">' + (ce.ok ? dl + ' ימים' : 'הבדיקה נכשלה') + '</div><div class="m">' + (ce.ok ? 'עד ' + new Date(ce.not_after).toLocaleDateString('he-IL') + ' · ' + esc(ce.issuer || '') : esc(ce.err || '')) + '</div></div><div class="vbox" style="cursor:default"><div class="k">מצב</div><div class="v"><span class="tag ' + cls + '">' + (!ce.ok ? 'לא ידוע' : dl < 14 ? 'לחדש עכשיו' : dl < 30 ? 'לשים לב' : 'תקין') + '</span></div><div class="m">נבדק ' + new Date(ce.checked_at).toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '</div></div></div>';
  } else $('certBox').innerHTML = '<p class="empty">עדיין לא נבדק (הבדיקה הראשונה ב-04:00).</p>';

  /* התראות */
  $('alertsList').innerHTML = recent.length
    ? '<ul class="list">' + recent.map(function(a){ return '<li class="rowbtn" data-id="' + a.id + '"><span class="tag ' + (a.open ? 'd' : 'n') + '">' + (a.open ? 'פתוחה' : 'נסגרה') + '</span><b>' + esc(a.title) + '</b><span class="muted">' + esc(niceBody(a.body || '', a.title)) + '</span><span class="when">' + esc(a.opened_il) + (a.closed_il ? ' → ' + esc(a.closed_il) : '') + ' · ' + a.minutes + ' דק\'</span></li>'; }).join('') + '</ul>'
    : '<p class="empty">אין התראות בתקופה. זה טוב.</p>';
  var _an = $('alertsN'); if (_an) _an.textContent = ' · ' + recent.length;
  Array.prototype.forEach.call($('alertsList').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillAlert(+li.getAttribute('data-id')); }); });

  /* המדידה עצמה */
  $('healthTbl').innerHTML = health.length
    ? '<ul class="list">' + health.map(function(r, i){ var cls = r.status === 'תקין' ? 'ok' : r.status === 'מתעכב' ? 'w' : r.status === 'שקט' ? 'd' : 'n'; return '<li class="rowbtn" data-i="' + i + '"><span class="tag ' + cls + '">' + esc(r.status) + '</span>' + esc(r.flow_name) + '<span class="muted">' + esc(r.cadence || '') + (r.silent_txt ? ' · ' + esc(r.silent_txt) : '') + '</span></li>'; }).join('') + '</ul>'
    : '<p class="empty">אין נתוני מדידה.</p>';
  Array.prototype.forEach.call($('healthTbl').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillHealth(health[+li.getAttribute('data-i')]); }); });
}

/* ---------- גרפים (SVG בלי ספרייה) ---------- */
function xlabel(b){ return b.length > 10 ? b.slice(11, 16) : b.slice(8, 10) + '.' + b.slice(5, 7); }
function drawSpeed(series, pages){
  $('speedChart').innerHTML = speedChart(series, pages);
  Array.prototype.forEach.call($('speedChart').querySelectorAll('.pt'), function(el){ el.addEventListener('click', function(){ drillRuns(el.getAttribute('data-url'), el.getAttribute('data-page'), el.getAttribute('data-bucket')); }); });
}
function speedChart(series, pages){
  var W = 720, H = 240, L = 34, R = 8, T = 12, B = 28;
  var buckets = []; series.forEach(function(r){ if (buckets.indexOf(r.bucket) < 0) buckets.push(r.bucket); }); buckets.sort();
  var vis = pages.filter(function(p){ return !state.hidden[p]; });
  var maxV = 5000; series.forEach(function(r){ if (vis.indexOf(r.page) >= 0 && r.lcp_p50 > maxV) maxV = r.lcp_p50; }); maxV = Math.ceil(maxV / 1000) * 1000;
  var x = function(i){ return buckets.length < 2 ? (L + (W - L - R) / 2) : L + (W - L - R) * i / (buckets.length - 1); };
  var y = function(v){ return T + (H - T - B) * (1 - v / maxV); };
  var s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="מהירות לאורך זמן">';
  for (var g = 0; g <= maxV; g += 1000) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(g) + '" y2="' + y(g) + '"/><text x="' + (L - 4) + '" y="' + (y(g) + 4) + '" text-anchor="end">' + (g / 1000) + '</text>';
  [[2500, 'גוגל 2.5'], [4000, 'איטי 4']].forEach(function(rf){ if (rf[0] <= maxV) s += '<line class="ref" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(rf[0]) + '" y2="' + y(rf[0]) + '"/><text class="reft" x="' + (W - R - 2) + '" y="' + (y(rf[0]) - 3) + '" text-anchor="end">' + rf[1] + '</text>'; });
  var step = Math.max(1, Math.ceil(buckets.length / 8));
  buckets.forEach(function(b, i){ if (i % step === 0 || i === buckets.length - 1) s += '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + xlabel(b) + '</text>'; });
  pages.forEach(function(p, pi){
    if (state.hidden[p]) return;
    var pts = [], url = '';
    buckets.forEach(function(b, i){ var r = series.filter(function(q){ return q.page === p && q.bucket === b; })[0]; if (r && r.lcp_p50 != null) { url = r.url; pts.push([x(i), y(Math.min(r.lcp_p50, maxV)), b, r]); } });
    if (!pts.length) return;
    s += '<path class="ln" stroke="' + COLORS[pi % COLORS.length] + '" d="M' + pts.map(function(q){ return q[0].toFixed(1) + ' ' + q[1].toFixed(1); }).join(' L') + '"/>';
    pts.forEach(function(q){ s += '<circle class="pt" data-url="' + esc(url) + '" data-page="' + esc(p) + '" data-bucket="' + esc(q[2]) + '" cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="7" fill="' + COLORS[pi % COLORS.length] + '" fill-opacity="0.15"><title>' + esc(p) + ' ' + xlabel(q[2]) + ': ' + sec(q[3].lcp_p50) + ' ש\'</title></circle><circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="2.6" fill="' + COLORS[pi % COLORS.length] + '" pointer-events="none"/>'; });
  });
  return s + '</svg>';
}
function availChart(rows){
  if (!rows.length) return '';
  var W = 720, H = 160, L = 34, R = 40, T = 12, B = 28;
  var maxF = 1; rows.forEach(function(r){ if (+r.failed > maxF) maxF = +r.failed; });
  var maxMs = 500; rows.forEach(function(r){ if (+r.ms_p50 > maxMs) maxMs = +r.ms_p50; }); maxMs = Math.ceil(maxMs / 250) * 250;
  var n = rows.length, bw = Math.max(3, (W - L - R) / n - 2);
  var x = function(i){ return L + (W - L - R) * (i + 0.5) / n; };
  var yf = function(v){ return T + (H - T - B) * (1 - v / maxF); };
  var ym = function(v){ return T + (H - T - B) * (1 - v / maxMs); };
  var s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="זמינות לאורך זמן">';
  s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + (H - B) + '" y2="' + (H - B) + '"/>';
  s += '<text x="' + (L - 4) + '" y="' + (T + 4) + '" text-anchor="end">' + maxF + '</text><text x="' + (L - 4) + '" y="' + (H - B + 4) + '" text-anchor="end">0</text>';
  s += '<text x="' + (W - R + 4) + '" y="' + (T + 4) + '">' + maxMs + 'ms</text>';
  var step = Math.max(1, Math.ceil(n / 8));
  rows.forEach(function(r, i){
    if (+r.failed > 0) s += '<rect class="bar" data-bucket="' + esc(r.bucket) + '" x="' + (x(i) - bw / 2) + '" y="' + yf(+r.failed) + '" width="' + bw + '" height="' + (H - B - yf(+r.failed)) + '"><title>' + esc(r.bucket) + ': ' + r.failed + ' כשלים מתוך ' + r.checks + '</title></rect>';
    if (i % step === 0 || i === n - 1) s += '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + xlabel(r.bucket) + '</text>';
  });
  var pts = rows.map(function(r, i){ return r.ms_p50 == null ? null : x(i).toFixed(1) + ' ' + ym(+r.ms_p50).toFixed(1); }).filter(Boolean);
  if (pts.length > 1) s += '<path class="ms" d="M' + pts.join(' L') + '"/>';
  rows.forEach(function(r, i){ if (r.ms_p50 != null) s += '<circle class="hit" data-bucket="' + esc(r.bucket) + '" cx="' + x(i).toFixed(1) + '" cy="' + ym(+r.ms_p50).toFixed(1) + '" r="9"><title>' + esc(r.bucket) + ': שרת ' + r.ms_p50 + ' ms</title></circle>'; });
  return s + '</svg>';
}

/* ---------- חלון העומק ---------- */
var dov = $('dov');
function openSheet(title, html){ $('dttl').textContent = title; $('dbody').innerHTML = html; dov.classList.add('on'); document.body.style.overflow = 'hidden'; $('dsheet').scrollTo(0, 0); }
function closeSheet(){ dov.classList.remove('on'); document.body.style.overflow = ''; }
$('dx').addEventListener('click', closeSheet);
dov.addEventListener('click', function(e){ if (e.target === dov) closeSheet(); });
document.addEventListener('keydown', function(e){ if (e.key === 'Escape' && dov.classList.contains('on')) closeSheet(); });
function drill(params){ return fetch(api('/site/drill?' + params + qs()), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){ if (d.error) throw new Error(d.error); return d.rows || []; }); }
function loading(title){ openSheet(title, '<p class="empty"><i style="display:inline-block;width:12px;height:12px;border:2px solid var(--tx3);border-top-color:transparent;border-radius:50%;animation:sp .8s linear infinite;vertical-align:middle;margin-inline-end:6px"></i>טוען…</p>'); }
function fail(e){ $('dbody').innerHTML = '<p class="empty">לא הצלחתי לטעון. ' + esc(e) + '</p>'; }

function drillFails(page, bucket, checks, failed, perPage){
  var title = page ? 'הכשלים של עמוד ' + page : bucket ? 'הכשלים ' + bucketTxt(bucket) : 'כל הכשלים';
  loading(title);
  drill('what=fails&page=' + encodeURIComponent(page || '') + '&bucket=' + encodeURIComponent(bucket || '')).then(function(rows){
    var h = '';
    if (checks) h += '<p class="dsum"><b>' + n(failed) + '</b> בדיקות נכשלו מתוך <b>' + n(checks) + '</b> (' + (100 * failed / checks).toFixed(2) + ' אחוז). ' + (failed === 0 ? 'הכל ענה.' : failed <= 3 ? 'כשל בודד פה ושם הוא רעש רגיל של רשת, לא תקלה.' : 'זה מעבר לרעש רגיל. כדאי לראות אם הכשלים מקובצים בשעה אחת (אירוע) או מפוזרים (עומס).') + '</p>';
    var kinds = {}; rows.forEach(function(r){ kinds[r.kind] = (kinds[r.kind] || 0) + 1; });
    if (rows.length) h += '<div class="dwhat">מה קרה: ' + Object.keys(kinds).map(function(k){ return esc(k) + ' × ' + kinds[k]; }).join(' · ') + '</div>';
    if (!page && perPage && perPage.length > 1) h += '<h3>לפי עמוד</h3><ul class="list">' + perPage.map(function(r){ return '<li><b>' + esc(r.page) + '</b> ' + r.failed + ' מתוך ' + n(+r.checks) + '</li>'; }).join('') + '</ul>';
    h += '<h3>הבדיקות שנכשלו' + (rows.length >= 500 ? ' (500 האחרונות)' : '') + '</h3>';
    h += rows.length ? '<div class="tblwrap"><table><thead><tr><th>מתי</th><th>עמוד</th><th>מה קרה</th><th class="num">אחרי</th></tr></thead><tbody>' + rows.map(function(r){ return '<tr><td>' + esc(r.at_il) + '</td><td>' + esc(r.page) + '</td><td>' + esc(r.kind) + (r.err ? ' <span class="muted">' + esc(r.err.slice(0, 60)) + '</span>' : '') + '</td><td class="num">' + (r.ms == null ? '—' : (r.ms / 1000).toFixed(1) + ' ש\'') + '</td></tr>'; }).join('') + '</tbody></table></div>' : '<p class="empty">אין כשלים.</p>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillBucket(b, row){
  loading('זמן תגובת השרת ' + bucketTxt(b));
  drill('what=bucket&bucket=' + encodeURIComponent(b)).then(function(rows){
    var h = '<p class="dsum">חציון זמן התגובה: <b>' + row.ms_p50 + ' ms</b>. הכי איטי (95 אחוז): <b>' + row.ms_p95 + ' ms</b>. ' + (row.ms_p50 <= 800 ? 'השרת ענה מהר (הסף של גוגל: 800).' : row.ms_p50 <= 1500 ? 'השרת ענה לאט מהרצוי. אם זה חוזר בשעות מסוימות, זה עומס.' : 'השרת ענה לאט מאוד. זה לפני שהעמוד בכלל מתחיל להיטען אצל הלקוח.') + '</p>';
    h += '<div class="tblwrap"><table><thead><tr><th>עמוד</th><th class="num">בדיקות</th><th class="num">כשלים</th><th class="num">חציון</th><th class="num">הכי איטי</th><th>מתי</th></tr></thead><tbody>' + rows.map(function(r){ return '<tr><td>' + esc(r.page) + '</td><td class="num">' + r.checks + '</td><td class="num">' + r.failed + '</td><td class="num">' + (r.ms_p50 == null ? '—' : r.ms_p50 + ' ms') + '</td><td class="num">' + (r.ms_max == null ? '—' : r.ms_max + ' ms') + '</td><td>' + esc(r.worst_il || '') + '</td></tr>'; }).join('') + '</tbody></table></div>';
    if (CFG.bucketNote) h += '<div class="dwhat">' + esc(CFG.bucketNote) + '</div>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillOutages(list){
  var h = list.length ? '<p class="dsum">' + (list.length === 1 ? 'נפילה אחת' : list.length + ' נפילות') + ' בתקופה. נפילה = 3 דקות רצופות שבהן אף אחד מ-' + CFG.probeCount + ' העמודים לא ענה. סך הכל <b>' + list.reduce(function(a, r){ return a + (+r.outage_minutes || 0); }, 0) + ' דקות</b> שבהן לקוח לא יכול היה להיכנס.</p><ul class="list">' + list.map(function(o){ return '<li><span class="tag d">' + o.outage_minutes + ' דק\'</span><span class="when">' + esc(o.outage_start_il) + ' → ' + esc(o.outage_end_il) + '</span></li>'; }).join('') + '</ul><div class="dwhat">לראות מה קרה בדיוק: לחיצה על העמודה האדומה של אותה שעה בגרף הזמינות.</div>' : '<p class="dsum">האתר לא נפל בתקופה. כשל של דקה אחת בעמוד אחד נספר בזמינות, לא כאן.</p>';
  openSheet('נפילות', h);
}
function drillAlerts(recent, open){
  var h = '<p class="dsum">' + (open.length ? '<b>' + open.length + '</b> התראות פתוחות עכשיו.' : 'אין התראה פתוחה עכשיו.') + ' ' + (recent.length ? recent.length + ' התראות בתקופה.' : 'לא היו התראות בתקופה.') + '</p>';
  h += recent.length ? '<ul class="list">' + recent.map(function(a){ return '<li class="rowbtn" data-id="' + a.id + '"><span class="tag ' + (a.open ? 'd' : 'n') + '">' + (a.open ? 'פתוחה' : 'נסגרה') + '</span><b>' + esc(a.title) + '</b><span class="when">' + esc(a.opened_il) + ' · ' + a.minutes + ' דק\'</span></li>'; }).join('') + '</ul>' : '';
  openSheet('התראות', h);
  Array.prototype.forEach.call($('dbody').querySelectorAll('li.rowbtn'), function(li){ li.addEventListener('click', function(){ drillAlert(+li.getAttribute('data-id')); }); });
}
function drillAlert(id){
  loading('התראה');
  drill('what=alert&id=' + id).then(function(rows){
    var a = rows[0]; if (!a) { $('dbody').innerHTML = '<p class="empty">לא נמצאה.</p>'; return; }
    $('dttl').textContent = a.title;
    var h = '<p class="dsum">' + (a.open ? 'עדיין פתוחה, ' : 'נסגרה. ') + 'נפתחה ב-<b>' + esc(a.opened_il) + '</b>' + (a.closed_il ? ', נסגרה ב-<b>' + esc(a.closed_il) + '</b>' : '') + ', סך הכל <b>' + a.minutes + ' דקות</b>.<br>' + esc(niceBody(a.body || '', a.title)) + '</p>';
    var what = { down: 'בדיקת זמינות נכשלה. הכלל: כל כשל בודד מתריע, גם של שנייה. כשל אחד ויחיד הוא לרוב רעש רשת; שניים-שלושה ברצף הם תקלה אמיתית.', slow: 'עמוד עיקרי נמדד איטי (מעל 4 שניות עד התוכן) פעמיים ברצף. אם זה קורה בשעות עומס בלבד, זה השרת. אם תמיד, זה העמוד עצמו (תמונות, תוספים).', silent: 'הבודק עצמו הפסיק לרוץ. עד שהוא חוזר, המספרים במסך ישנים.', cert: 'תעודת האבטחה עומדת לפוג. צריך לחדש אצל חברת האחסון או להפעיל חידוש אוטומטי.' };
    h += '<div class="dwhat">' + (what[a.kind] || '') + '</div>';
    if (a.fails && a.fails.length) h += '<h3>הבדיקות שנכשלו מאחורי ההתראה</h3><div class="tblwrap"><table><thead><tr><th>מתי</th><th>עמוד</th><th>מה</th></tr></thead><tbody>' + a.fails.map(function(f){ return '<tr><td>' + esc(f.at) + '</td><td>' + esc(f.page) + '</td><td>' + esc(f.status ? 'קוד ' + f.status : (f.err || '')) + '</td></tr>'; }).join('') + '</tbody></table></div>';
    if (a.sent && a.sent.length) h += '<h3>הודעות שנשלחו לטלפון</h3><ul class="list">' + a.sent.map(function(s){ return '<li><span class="tag ' + (s.status === 200 ? 'ok' : 'd') + '">' + (s.status === 200 ? 'נשלחה' : 'נכשלה') + '</span>' + (s.event === 'open' ? 'פתיחה' : s.event === 'close' ? 'חזר לתקין' : esc(s.event)) + '<span class="when">' + esc(s.at) + '</span></li>'; }).join('') + '</ul>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillRuns(url, page, bucket){
  var title = 'מהירות: ' + page + (bucket ? ' ' + bucketTxt(bucket) : '');
  loading(title);
  drill('what=runs&url=' + encodeURIComponent(url) + '&strategy=' + state.s + '&bucket=' + encodeURIComponent(bucket || '')).then(function(rows){
    var ok = rows.filter(function(r){ return r.ok; });
    if (!ok.length) { $('dbody').innerHTML = '<p class="empty">אין מדידות תקינות' + (rows.length ? ' (' + rows.length + ' ניסיונות נכשלו: ' + esc(rows[0].err || '') + ')' : '') + '.</p>'; return; }
    var lcps = ok.map(function(r){ return r.lcp_ms; }).filter(function(v){ return v != null; }).sort(function(a, b){ return a - b; });
    var med = lcps[Math.floor(lcps.length / 2)], worst = ok.reduce(function(a, r){ return (r.lcp_ms || 0) > (a.lcp_ms || 0) ? r : a; }, ok[0]), best = ok.reduce(function(a, r){ return (r.lcp_ms || 1e9) < (a.lcp_ms || 1e9) ? r : a; }, ok[0]);
    var h = '<p class="dsum"><b>' + ok.length + '</b> מדידות ב' + (state.s === 'desktop' ? 'מחשב' : 'טלפון') + '. חציון <b>' + sec(med) + ' שניות</b> עד התוכן העיקרי: <b>' + lcpWord(med) + '</b>. הכי איטית ' + sec(worst.lcp_ms) + ' ש\' (' + esc(worst.at_il) + '), הכי מהירה ' + sec(best.lcp_ms) + ' ש\' (' + esc(best.at_il) + ').' + (ok[0].crux_category ? ' אצל גולשים אמיתיים גוגל מודדת: <b>' + (ok[0].crux_category === 'FAST' ? 'מהיר' : ok[0].crux_category === 'AVERAGE' ? 'בינוני' : 'איטי') + '</b>' + (ok[0].crux_lcp_ms ? ' (' + sec(ok[0].crux_lcp_ms) + ' ש\')' : '') + '.' : '') + '</p>';
    /* מה מאט: ממוצע החיסכון לכל סיבה על פני המדידות */
    var agg = {}; ok.forEach(function(r){ (r.opps || []).forEach(function(o){ var k = o.id; agg[k] = agg[k] || { id: k, title: o.title, sum: 0, cnt: 0 }; agg[k].sum += +o.ms || 0; agg[k].cnt++; }); });
    var opps = Object.keys(agg).map(function(k){ return agg[k]; }).sort(function(a, b){ return b.sum / b.cnt - a.sum / a.cnt; }).slice(0, 6);
    if (opps.length) h += '<h3>מה מאט את העמוד (לפי גוגל)</h3><ul class="list">' + opps.map(function(o){ return '<li><b>' + sec(o.sum / o.cnt) + ' ש\'</b> ' + esc(oppName(o)) + '</li>'; }).join('') + '</ul><div class="dwhat">המספר = כמה זמן אפשר לחסוך אם מטפלים בסיבה הזאת, לפי ההערכה של גוגל. הסיבות הראשונות הן כמעט תמיד תמונות: לדחוס, להקטין לגודל התצוגה, ולטעון רק כשגוללים.</div>';
    h += '<h3>המדידות</h3><div class="tblwrap"><table><thead><tr><th>מתי</th><th>מצב</th><th class="num">ציון</th><th class="num">תוכן (LCP)</th><th class="num">שרת</th><th class="num">משקל</th><th class="num">קפיצות</th></tr></thead><tbody>' + ok.slice(0, 100).map(function(r){ return '<tr><td>' + esc(r.at_il) + '</td><td>' + lcpTag(r.lcp_ms) + '</td><td class="num">' + (r.score == null ? '—' : r.score) + '</td><td class="num">' + sec(r.lcp_ms) + ' ש\'</td><td class="num">' + (r.ttfb_ms == null ? '—' : r.ttfb_ms + ' ms') + '</td><td class="num">' + (r.bytes == null ? '—' : (r.bytes / 1048576).toFixed(1) + ' MB') + '</td><td class="num">' + (r.cls == null ? '—' : r.cls) + '</td></tr>'; }).join('') + '</tbody></table></div>' + (ok.length > 100 ? '<p class="more">מוצגות 100 מתוך ' + ok.length + '.</p>' : '');
    h += '<p class="more"><a href="' + esc(url) + '" target="_blank" rel="noopener">לפתוח את העמוד באתר</a></p>';
    $('dbody').innerHTML = h;
  }).catch(fail);
}
function drillHealth(r){
  /* הסבר לכל שורה. שורה שאין לה הסבר כאן מציגה את השדה note שהשרת שולח. */
  var what = {
    'בודק זמינות האתר': 'כל דקה הבודק פונה ל-' + CFG.probeCount + ' עמודים באתר ורושם אם ענו ותוך כמה זמן. אם השורה הזאת שקטה, הבודק עצמו נעצר ואף אחד לא בודק את האתר.',
    'מדידת מהירות — עמודי ליבה': 'כל רבע שעה גוגל מודדת עבורנו את ' + CFG.coreCount + ' העמודים העיקריים בטלפון (ופעם בשעה במחשב). דורש מפתח מגוגל. אם השורה שקטה, המדידה נעצרה או שהמפתח חסר.',
    'מדידת מהירות — סבב כל האתר': 'כל 5 דקות נמדדים 2 עמודים מכל האתר, כך שכל עמוד נמדד בערך פעם ביום.',
    'טעינת מפת האתר': 'פעם בלילה נטענת רשימת כל העמודים באתר (מוצרים, קטגוריות) כדי שהסבב יכיר עמודים חדשים.',
    'בדיקת תעודת האבטחה': 'פעם ביום נבדק מתי תעודת האבטחה של האתר פגה.',
    'בדיקת מוצרים שבורים': 'פעם ביום ב-04:00 נקרא כל הקטלוג הציבורי של האתר ונבדק אם יש מוצר בלי מחיר, בלי תמונה, לא במלאי או שאי אפשר להוסיף לסל.',
    'מהירות אצל לקוחות': 'קוד מדידה קטן באתר שולח מכל צפייה בעמוד כמה זמן לקח עד שהתוכן העיקרי הוצג. אם השורה שקטה, הקוד הוסר מהאתר או שהמדידות לא מגיעות.'
  };
  var status = r.status === 'תקין' ? 'רץ כמו שצריך.' : r.status === 'מתעכב' ? 'מאחר. אם זה לא חוזר לתקין תוך שעה, יש בעיה.' : r.status === 'שקט' ? 'נעצר. המספרים שתלויים בו ישנים.' : r.status === 'אין נתון' ? 'עדיין לא רץ אף פעם.' : r.status;
  openSheet(r.flow_name, '<p class="dsum"><b>' + esc(r.status) + '</b>: ' + status + (r.last_at ? ' הריצה האחרונה: ' + new Date(r.last_at).toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + '.' : '') + '</p><div class="dwhat">' + (what[r.flow_name] || esc(r.note || '')) + '</div><p class="muted">קצב: ' + esc(r.cadence || '') + ' · סף איחור: ' + r.warn_minutes + ' דק\' · סף שתיקה: ' + r.late_minutes + ' דק\'</p>');
}

/* ---------- פקדים ---------- */
function setPreset(h){ state.h = h; state.f = ''; state.t = ''; $('dFrom').value = ''; $('dTo').value = ''; Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(o){ o.setAttribute('aria-pressed', +o.getAttribute('data-h') === h ? 'true' : 'false'); }); load(); }
Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(b){ b.addEventListener('click', function(){ setPreset(+b.getAttribute('data-h')); }); });
Array.prototype.forEach.call(document.querySelectorAll('#segS button'), function(b){ b.addEventListener('click', function(){ state.s = b.getAttribute('data-s'); Array.prototype.forEach.call(document.querySelectorAll('#segS button'), function(o){ o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); }); load(); }); });
$('dGo').addEventListener('click', function(){
  var f = $('dFrom').value, t = $('dTo').value || new Date().toISOString().slice(0, 10);
  if (!f) { $('dFrom').focus(); return; }
  if (t < f) { var x = f; f = t; t = x; }
  state.f = f; state.t = t; $('dTo').value = t;
  Array.prototype.forEach.call(document.querySelectorAll('#segH button'), function(o){ o.setAttribute('aria-pressed', 'false'); });
  load();
});
$('refbtn').addEventListener('click', load);
$('explbtn').addEventListener('click', function(){ var on = document.body.classList.toggle('explain-on'); $('explbtn').setAttribute('aria-pressed', on ? 'true' : 'false'); });
$('pdfbtn') && $('pdfbtn').addEventListener('click', function(){ window.print(); });
load();
setInterval(function(){ if (!dov.classList.contains('on')) load(); }, 60000);

/* ---------- עכשיו: סבב הבדיקה האחרון, מתרענן כל 60 שניות גם כשגיליון פתוח ---------- */
function nowColorMs(ms){ if (ms == null) return 'n'; return ms <= 500 ? 'ok' : ms <= 1500 ? 'w' : 'd'; }
function nowSec(ms){ return ms == null ? '—' : (ms / 1000).toFixed(ms < 1000 ? 2 : 1) + ' שנ\''; }
/* מאיזה אתר הגיעו המדידות של "מהירות אצל לקוחות": האתר החי או משהו אחר (פיתוח) */
function rumSrc(s){
  if (!s || !s.n || !s.hosts || !s.hosts.length) return '';
  /* קוד המדידה כותב site = 'live' באתר החי; כל ערך אחר (סביבת פיתוח) מוצג בצבע אזהרה */
  var live = function(h){ return CFG.liveHosts.indexOf(h) >= 0; };
  var other = s.hosts.filter(function(x){ return !live(x.host); });
  var t = s.test ? ' · מתוכן ' + s.test + ' מדידות בדיקה' : '';
  if (!other.length) return '<br>מקור: האתר החי · כל ' + s.n + ' המדידות האחרונות' + t;
  return '<br><span style="color:var(--warn,#b26a00)">מקור: ' + s.hosts.map(function(x){ return esc(x.host) + ' ' + x.n; }).join(' · ') + ' (מתוך ' + s.n + ' המדידות האחרונות)' + t + '</span>';
}
function renderNow(d){
  var pages = Array.isArray(d.pages) ? d.pages : [];
  var age = d.age_sec == null ? null : Math.max(0, d.age_sec);
  var ageTxt = age == null ? 'אין בדיקה ב־15 הדקות האחרונות' : ('נבדק לפני ' + (age < 90 ? age + ' שניות' : Math.round(age / 60) + ' דקות'));
  var okN = pages.filter(function(p){ return p.ok; }).length;
  /* זמינות: מהסבב האחרון מכל סוג (מלא כל דקה, קל כל 30 שניות). תגובת שרת: מהסבב המלא האחרון בלבד. */
  var latest = Array.isArray(d.latest) ? d.latest : pages; var okL = latest.filter(function(p){ return p.ok; }).length;
  var lightTxt = d.light ? ' · בדיקה קלה' : '';
  var site = !latest.length ? ['n', 'אין נתון', ageTxt] : d.all_ok ? ['ok', 'פעיל', ageTxt + lightTxt + ' · ' + okL + ' מתוך ' + latest.length + ' עמודים עונים'] : d.any_ok ? ['w', 'חלקי', ageTxt + lightTxt + ' · ' + okL + ' מתוך ' + latest.length + ' עונים'] : ['d', 'נפל', ageTxt + lightTxt + ' · אף עמוד לא עונה'];
  var home = pages.filter(function(p){ return p.page === CFG.homePage; })[0];
  var slowest = pages.slice().sort(function(a, b){ return (b.ms || 0) - (a.ms || 0); })[0];
  var srv = home && home.ok ? ['' + nowColorMs(home.ms), nowSec(home.ms), 'דף הבית' + (slowest && slowest.page !== CFG.homePage ? ' · הכי איטי כרגע: ' + esc(slowest.page) + ' ' + nowSec(slowest.ms) : '')] : home ? ['d', 'לא עונה', 'דף הבית'] : ['n', '—', 'אין נתון'];   /* בלי סבב בדיקה בכלל: "אין נתון", לא "לא עונה" */
  var rum = d.rum || {}; var rumBox = rum.n ? [nowColorMs(rum.p75_ms <= 2500 ? 400 : rum.p75_ms <= 4000 ? 1000 : 2000), nowSec(rum.p75_ms), rum.n + ' צפיות בשעה האחרונה · אחוזון 75' + rumSrc(d.rum_src)] : ['n', '—', 'אין מדידות בשעה האחרונה' + rumSrc(d.rum_src)];
  var sp = d.speed || {}; var spT = sp.checked_at ? new Date(sp.checked_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : '—';
  var lab = sp.lcp_ms ? [sp.lcp_ms <= 2500 ? 'ok' : sp.lcp_ms <= 4000 ? 'w' : 'd', (sp.lcp_ms / 1000).toFixed(1) + ' שנ\'', 'דף הבית בטלפון, ' + spT + ' · ציון ' + (sp.score == null ? '—' : sp.score) + ' · יעד 2.5'] : ['n', '—', 'אין מדידה'];
  function box(k, c){ return '<div class="nbox"><div class="k">' + k + '</div><div class="v"><span class="dot ' + c[0] + '"></span>' + c[1] + '</div><div class="m">' + c[2] + '</div></div>'; }
  $('now').innerHTML = box('האתר עכשיו', site) + box('תגובת שרת עכשיו', srv) + box('מהירות אצל לקוחות, שעה אחרונה', rumBox) + box('מעבדה, מדידה אחרונה', lab);
  $('nowpages').innerHTML = pages.map(function(p){ var c = p.ok ? nowColorMs(p.ms) : 'd'; return '<span class="tag ' + (c === 'ok' ? 'ok' : c === 'w' ? 'w' : 'd') + '" title="' + esc(p.url || '') + '">' + esc(p.page) + ' ' + (p.ok ? nowSec(p.ms) : 'לא עונה' + (p.status ? ' (' + p.status + ')' : '')) + '</span>'; }).join('');
  var al = +d.alerts_open || 0;
  $('nowtick').textContent = 'עודכן ' + new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' · רענון אוטומטי כל 60 שניות' + (al ? ' · ' + al + ' התראות פתוחות' : '');
}
function loadNow(){
  fetch(api('/site/now'), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){ if (!d || d.error) throw new Error(d && d.error || 'no data'); renderNow(d); })
    .catch(function(e){ $('nowtick').textContent = 'לא הצלחתי לטעון את "עכשיו": ' + e; });
}
loadNow(); setInterval(loadNow, 60000);

/* קיפול כרטיסים: לחיצה על כותרת עם .foldhead פותחת/סוגרת את גוף הכרטיס */
document.addEventListener('click', function(e){ var h = e.target.closest && e.target.closest('.foldhead'); if (h && h.parentElement && h.parentElement.classList.contains('foldcard')) h.parentElement.classList.toggle('collapsed'); });

/* ---------- יומן הודעות ---------- */
function loadMessages(){
  var el = $('msgList'); if (!el || ROLE.readonly) return;
  fetch(api('/messages?' + qs().replace(/^&/, '')), { cache: 'no-store' }).then(function(r){ return r.json(); }).then(function(d){
    var rows = Array.isArray(d.rows) ? d.rows : [];
    el.innerHTML = rows.length ? '<ul class="list">' + rows.map(function(m){ return '<li><span class="tag ' + (m.kind === 'התראה' ? 'd' : m.kind === 'חזר לתקין' ? 'ok' : 'n') + '">' + esc(m.kind) + '</span><b>' + esc(m.title || '') + '</b><span class="muted" style="white-space:pre-line;flex-basis:100%">' + esc(niceBody(m.msg || '', m.title)) + '</span><span class="when">' + esc(m.at_il) + (m.sent ? '' : ' · לא נשלחה') + '</span></li>'; }).join('') + '</ul>' : '<p class="empty">לא נשלחו הודעות בתקופה.</p>';
    var _mn = $('msgN'); if (_mn) _mn.textContent = ' · ' + rows.length;
  }).catch(function(){ el.innerHTML = '<p class="empty">לא הצלחתי לטעון את ההודעות.</p>'; });
}
</script>
</body>
</html>
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/db.py sha256=b5c6d4a1b76c40b373d94a12e3590d02f8209e2a8fedf8d5a3830f9b9e6bf281 -->
~~~~~~~~python
"""Database access for the site-health server and collectors.

Everything goes through rpc(): one call of one sh_* SQL function, returning its JSON result.
The transport is chosen by the environment:

    SUPABASE_URL + SUPABASE_SECRET_KEY    HTTPS: POST {SUPABASE_URL}/rest/v1/rpc/<fn>
    DATABASE_URL                          a normal Postgres connection (psycopg 3)

Parameter values must be JSON values (send times as ISO 8601 strings), so both transports
accept exactly the same calls.
"""
import http.client
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request

TIMEOUT = 30                                  # seconds
_FUNCTION = re.compile(r"sh_[a-z_]+")         # names go into a URL or into SQL text: nothing else may pass
_PARAMETER = re.compile(r"p_[a-z_]+")
_thread = threading.local()                   # the Postgres transport keeps one connection per thread
log = logging.getLogger("site_health.db")


class DbError(Exception):
    """A database call failed. The text names no host, user or key, so it may be shown to a viewer;
    connection details go to the log."""


def rpc(fn, params=None):
    """Call the SQL function `fn` with named parameters and return its (JSON) result."""
    params = params or {}
    if not _FUNCTION.fullmatch(fn) or not all(_PARAMETER.fullmatch(name) for name in params):
        raise DbError("bad function or parameter name in a call of %r" % (fn,))
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SECRET_KEY", "")
    if url and key:
        return _rpc_https(url, key, fn, params)
    dsn = os.environ.get("DATABASE_URL", "")
    if dsn:
        return _rpc_postgres(dsn, fn, params)
    raise DbError("no database configured: set SUPABASE_URL and SUPABASE_SECRET_KEY, or DATABASE_URL")


def _rpc_https(url, key, fn, params):
    request = urllib.request.Request(
        "%s/rest/v1/rpc/%s" % (url.rstrip("/"), fn), data=json.dumps(params).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read())["message"]          # PostgREST explains itself in the body
        except (ValueError, KeyError, TypeError, OSError):
            message = None
        raise DbError("HTTP %d: %s" % (e.code, message or e.reason)) from None
    except (OSError, http.client.HTTPException) as e:          # no route, TLS, timeout, broken answer
        log.warning("database call %s failed: %r", fn, e)
        cause = getattr(e, "reason", e)                        # URLError wraps the real failure
        name = type(cause if isinstance(cause, Exception) else e).__name__
        raise DbError("database unreachable (%s)" % name) from None
    try:
        return json.loads(body) if body else None
    except ValueError:
        raise DbError("the database API did not answer with JSON") from None


def _rpc_postgres(dsn, fn, params):
    import psycopg                                             # only this transport needs the driver
    from psycopg.types.json import Jsonb

    sql = "select %s(%s)" % (fn, ", ".join(name + " => %s" for name in params))
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params.values()]

    def connect():
        # autocommit and no server-side prepared statements: works behind a transaction pooler
        _thread.conn = psycopg.connect(dsn, autocommit=True, prepare_threshold=None, connect_timeout=TIMEOUT)
        return _thread.conn

    try:
        conn = getattr(_thread, "conn", None)
        reused = conn is not None and not conn.closed
        if not reused:
            conn = connect()
        try:
            return conn.execute(sql, values).fetchone()[0]
        except psycopg.OperationalError:
            if not (reused and conn.closed):
                raise
            return connect().execute(sql, values).fetchone()[0]    # an idle connection was dropped: once more
    except psycopg.OperationalError as e:
        log.warning("database call %s failed: %s", fn, e)       # the full text (host, user) stays in the log
        raise DbError(e.diag.message_primary or "database unreachable") from None
    except psycopg.Error as e:
        raise DbError(e.diag.message_primary or str(e)) from None
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/functions.sql sha256=d98a3938c1ce4263f6d9f00c9d54c32b4c2c8e2057434c06be00509c5fb474d7 -->
~~~~~~~~sql
-- Site Health: every sh_* function. Apply after schema.sql. Safe to run again.
--
-- Conventions
--   * The server and the collectors call these functions and nothing else. Each returns jsonb;
--     a list is never null (an empty list is '[]'). The few helpers at the top return text.
--   * Parameters are named p_*. Lists of rows and of ids arrive as jsonb and times as
--     timestamptz, so one call works over PostgREST (/rest/v1/rpc/<fn>) and over a connection.
--   * now() is the start of the transaction: all figures of one call are taken at one instant.
--   * Local time (every *_il string, every bucket, every day boundary) is the time zone stored
--     in sh_settings under 'time_zone'.

-- ---------------------------------------------------------------- helpers

create or replace function sh_tz() returns text
language sql stable set search_path = public as $$
  select coalesce((select value #>> '{}' from sh_settings where key = 'time_zone'), 'UTC')
$$;

-- A moment as the screen prints it: local time, DD.MM HH:MM.
create or replace function sh_il(p_at timestamptz) returns text
language sql stable set search_path = public as $$
  select to_char(p_at at time zone sh_tz(), 'DD.MM HH24:MI')
$$;

-- The to_char format of a bucket. The screen tells the two apart by their length.
create or replace function sh_bucket_fmt(p_hourly boolean) returns text
language sql immutable set search_path = public as $$
  select case when p_hourly then 'YYYY-MM-DD HH24:00' else 'YYYY-MM-DD' end
$$;

-- Why a check failed, in the words of the failures sheet and of the alert body.
create or replace function sh_fail_kind(p_fail text, p_status int) returns text
language sql immutable set search_path = public as $$
  select case p_fail
           when 'timeout' then 'לא ענה בזמן'
           when 'http'    then 'קוד ' || p_status
           when 'connect' then 'שגיאת חיבור'
           when 'content' then 'תוכן לא צפוי'
         end
$$;

-- A number of minutes in the unit a person would use.
create or replace function sh_span(p_minutes numeric) returns text
language sql immutable set search_path = public as $$
  select case when p_minutes < 120  then p_minutes::int || ' דקות'
              when p_minutes < 2880 then floor(p_minutes / 60)::int || ' שעות'
              else floor(p_minutes / 1440)::int || ' ימים'
         end
$$;

-- The LCP thresholds, the same ones the screen colors by.
create or replace function sh_verdict(p_lcp_ms int) returns text
language sql immutable set search_path = public as $$
  select case when p_lcp_ms <= 2000 then 'מצוין'
              when p_lcp_ms <= 2500 then 'מהיר'
              when p_lcp_ms <= 4000 then 'בינוני'
              when p_lcp_ms >  4000 then 'איטי'
         end
$$;

-- An alert as the alerts card and the alert sheet show it.
create or replace function sh_alert_row(p_alert sh_alerts) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', p_alert.id, 'kind', p_alert.kind, 'title', p_alert.title, 'body', p_alert.body,
    'open', p_alert.closed_at is null,
    'opened_il', sh_il(p_alert.opened_at), 'closed_il', sh_il(p_alert.closed_at),
    'minutes', floor(extract(epoch from coalesce(p_alert.closed_at, now()) - p_alert.opened_at) / 60)::int)
$$;

-- ---------------------------------------------------------------- configuration

-- The configuration as it was loaded (the keys of site_health.config.json, defaults filled in),
-- the pages in their order, and "screen": the values the server injects into SH_CONFIG.
create or replace function sh_config() returns jsonb
language sql stable set search_path = public as $$
  with s as (
    select coalesce(jsonb_object_agg(key, value), '{}') as v from sh_settings
  ), p as (
    select coalesce(jsonb_agg(jsonb_build_object(
             'name', name, 'url', url, 'probe', is_probe, 'core', is_core, 'home', is_home, 'expect', expect)
             order by sort), '[]') as v,
           count(*) filter (where is_probe) as probes,
           count(*) filter (where is_core) as cores,
           max(name) filter (where is_home) as home
    from sh_pages
  )
  select s.v || jsonb_build_object(
    'pages', p.v,
    -- a key that is not configured is left out, so the screen keeps its own default
    'screen', jsonb_strip_nulls(jsonb_build_object(
      'siteLabel', s.v -> 'label', 'brand', s.v -> 'brand', 'homePage', p.home,
      'probeCount', p.probes, 'coreCount', p.cores,
      'liveHosts', s.v -> 'live_hosts', 'pathLabels', s.v -> 'path_labels', 'bucketNote', s.v -> 'bucket_note',
      -- a site without a catalogue has no broken-products card
      'hide', case when s.v ->> 'platform' = 'other' then '["issuesCard"]'::jsonb else '[]'::jsonb end)))
  from s, p
$$;

-- Loads site_health.config.json. Running it again with the same file changes nothing; a page
-- that left the file is no longer probed or measured, and its history stays.
create or replace function sh_setup(p_config jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_site       text := rtrim(p_config ->> 'site', '/');
  v_host       text := lower(substring(v_site from '^https?://([^/:\s]+)'));
  v_zone       text := coalesce(p_config ->> 'time_zone', 'UTC');
  v_platform   text := coalesce(p_config ->> 'platform', 'other');
  v_down_after int  := coalesce((p_config ->> 'down_after')::int, 1);
  v_morning    text := coalesce(p_config ->> 'morning', '07:30');
  v_live       jsonb := coalesce(p_config -> 'live_hosts', '["live"]');
  v_labels     jsonb := coalesce(p_config -> 'path_labels', case v_platform
                          when 'woocommerce' then '[["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]'
                          when 'shopify'     then '[["/collections/", "קטגוריה: "], ["/products/", "מוצר: "]]'
                          else '[]' end::jsonb);
  v_pages int; v_named int; v_names int; v_homes int; v_probes int; v_home_probes int;
  v_bad_urls text;
begin
  if v_host is null then
    raise exception 'sh_setup: "site" must be an absolute http(s) address, got %', coalesce(p_config ->> 'site', 'nothing');
  end if;
  if not exists (select 1 from pg_timezone_names where name = v_zone) then
    raise exception 'sh_setup: unknown "time_zone" %', v_zone;
  end if;
  if v_platform not in ('woocommerce', 'shopify', 'other') then
    raise exception 'sh_setup: "platform" must be woocommerce, shopify or other, got %', v_platform;
  end if;
  if v_down_after < 1 then
    raise exception 'sh_setup: "down_after" must be 1 or more, got %', v_down_after;
  end if;
  if v_morning !~ '^([01]\d|2[0-3]):[0-5]\d$' then
    raise exception 'sh_setup: "morning" must be a time such as 07:30, got %', v_morning;
  end if;
  if jsonb_typeof(v_live) <> 'array' or jsonb_typeof(v_labels) <> 'array' then
    raise exception 'sh_setup: "live_hosts" and "path_labels" must be lists';
  end if;
  if jsonb_typeof(p_config -> 'pages') is distinct from 'array' then
    raise exception 'sh_setup: "pages" must be a list of pages';
  end if;

  select count(*), count(*) filter (where name <> ''), count(distinct name),
         count(*) filter (where home), count(*) filter (where probe), count(*) filter (where home and probe),
         string_agg(name, ', ') filter (where url is null or url !~ '^https?://[^/\s]+')
    into v_pages, v_named, v_names, v_homes, v_probes, v_home_probes, v_bad_urls
  from (select page ->> 'name' as name, page ->> 'url' as url,
               coalesce((page ->> 'probe')::boolean, false) as probe,
               coalesce((page ->> 'home')::boolean, false) as home
        from jsonb_array_elements(p_config -> 'pages') as page) p;
  if v_named < v_pages then
    raise exception 'sh_setup: every page needs a "name"';
  end if;
  if v_names < v_pages then
    raise exception 'sh_setup: page names must be unique';
  end if;
  if v_bad_urls is not null then
    raise exception 'sh_setup: the "url" of a page must be an absolute http(s) address: %', v_bad_urls;
  end if;
  if v_homes <> 1 then
    raise exception 'sh_setup: exactly one page must have "home": true, found %', v_homes;
  end if;
  if v_probes < 1 then
    raise exception 'sh_setup: at least one page must have "probe": true';
  end if;
  if v_home_probes < 1 then
    raise exception 'sh_setup: the home page must be a probe page';
  end if;

  insert into sh_settings (key, value)
  select key, value from jsonb_each(jsonb_build_object(
    'site', v_site, 'host', v_host,
    'label', coalesce(p_config ->> 'label', regexp_replace(v_host, '^www\.', '')),
    'brand', coalesce(p_config ->> 'brand', ''),
    'time_zone', v_zone, 'platform', v_platform, 'down_after', v_down_after, 'morning', v_morning,
    'live_hosts', v_live, 'path_labels', v_labels,
    'bucket_note', coalesce(p_config ->> 'bucket_note', '')))
  on conflict (key) do update set value = excluded.value;

  delete from sh_pages;
  insert into sh_pages (name, url, is_probe, is_core, is_home, sort, expect)
  select page ->> 'name', page ->> 'url',
         coalesce((page ->> 'probe')::boolean, false), coalesce((page ->> 'core')::boolean, false),
         coalesce((page ->> 'home')::boolean, false), sort, nullif(page ->> 'expect', '')
  from jsonb_array_elements(p_config -> 'pages') with ordinality as p(page, sort);

  -- The measurement flows of the screen's last card. last_at and note are never touched here.
  insert into sh_flows (flow_name, sort, cadence, warn_minutes, late_minutes, enabled) values
    ('בודק זמינות האתר',           1, 'כל דקה',          5,    15,   true),
    ('מדידת מהירות — עמודי ליבה',   2, 'כל רבע שעה',      45,   90,   true),
    ('מדידת מהירות — סבב כל האתר',  3, 'כל 5 דקות',       20,   60,   true),
    ('טעינת מפת האתר',             4, 'פעם ביום',        1560, 2880, true),
    ('בדיקת תעודת האבטחה',         5, 'פעם ביום',        1560, 2880, true),
    ('בדיקת מוצרים שבורים',        6, 'פעם ביום',        1560, 2880, v_platform <> 'other'),
    ('מהירות אצל לקוחות',          7, 'כל צפייה בעמוד',  120,  360,  true)
  on conflict (flow_name) do update
    set sort = excluded.sort, cadence = excluded.cadence, warn_minutes = excluded.warn_minutes,
        late_minutes = excluded.late_minutes, enabled = excluded.enabled;

  return sh_config();
end $$;

-- ---------------------------------------------------------------- read side: /api/site

-- Per page over the full rounds of the window, then the outages.
create or replace function sh_availability(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  with per_page as (
    select page, count(*) as checks, count(*) filter (where not ok) as failed,
           percentile_cont(array[0.5, 0.95]) within group (order by ms) filter (where ok) as pct,
           max(round_at) filter (where not ok) as last_fail
    from sh_probe
    where kind = 'full' and round_at >= p_from and round_at < p_to
    group by page
  ), rounds as (
    -- a round is dead when none of its pages answered
    select round_at, bool_or(ok) as alive
    from sh_probe
    where kind = 'full' and round_at >= p_from and round_at < p_to
    group by round_at
  ), numbered as (
    -- dead rounds with no answering round between them share a run number
    select round_at, alive,
           count(*) filter (where alive) over (order by round_at) as run,
           lead(round_at) over (order by round_at) as next_at
    from rounds
  ), outages as (
    select min(round_at) as start_at, count(*) as minutes,
           -- it ends at the round after the last dead one; a run that reaches the end of the
           -- window has none, and ends where the window does (which is now for a live window)
           case when count(next_at) = count(*) then max(next_at) else least(p_to, now()) end as end_at
    from numbered
    where not alive
    group by run
    having count(*) >= 3
  )
  select coalesce((
           select jsonb_agg(jsonb_build_object(
                    'section', 'לפי עמוד', 'page', a.page, 'checks', a.checks, 'failed', a.failed,
                    'fail_pct', round(100.0 * a.failed / a.checks, 2)::text,
                    'p50_ms', round(a.pct[1]::numeric)::int, 'p95_ms', round(a.pct[2]::numeric)::int,
                    'last_fail_il', sh_il(a.last_fail))
                    -- the order of the configuration; a page that left it keeps its history, last
                    order by p.sort nulls last, a.page)
           from per_page a left join sh_pages p on p.name = a.page), '[]')
      || coalesce((
           select jsonb_agg(jsonb_build_object(
                    'section', 'נפילות', 'outage_minutes', minutes,
                    'outage_start_il', sh_il(start_at), 'outage_end_il', sh_il(end_at))
                    order by start_at)
           from outages), '[]')
$$;

-- One row per hour (windows of up to 72 whole hours) or per day, all pages together.
create or replace function sh_availability_series(p_from timestamptz, p_to timestamptz) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  -- hourly up to 72 whole hours: "h=72" arrives as 72 hours and a minute (to = now + 1 minute)
  v_fmt text := sh_bucket_fmt(p_to - p_from < interval '73 hours');
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'bucket', bucket, 'checks', checks, 'failed', failed,
             'ms_p50', round(pct[1]::numeric)::int, 'ms_p95', round(pct[2]::numeric)::int)
             order by bucket), '[]')
    from (
      select to_char(round_at at time zone v_tz, v_fmt) as bucket,
             count(*) as checks, count(*) filter (where not ok) as failed,
             percentile_cont(array[0.5, 0.95]) within group (order by ms) filter (where ok) as pct
      from sh_probe
      where kind = 'full' and round_at >= p_from and round_at < p_to
      group by 1
    ) b);
end $$;

-- The four sections of the speed answer, over the successful runs of the window.
create or replace function sh_speed(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  with runs as materialized (
    select url, strategy, source, at, lcp_ms, score, cls, ttfb_ms, crux_category, crux_lcp_ms
    from sh_speed
    where ok and at >= p_from and at < p_to
  ), core as (
    select p.name as page, p.url, p.sort, r.strategy,
           percentile_cont(array[0.5, 0.95]) within group (order by r.lcp_ms) as lcp,
           percentile_cont(0.5) within group (order by r.score) as score,
           percentile_cont(0.5) within group (order by r.cls) as cls,
           percentile_cont(0.5) within group (order by r.ttfb_ms) as ttfb,
           count(*) filter (where r.lcp_ms > 4000) as slow_runs, count(*) as checks,
           (array_agg(r.crux_category order by r.at desc))[1] as crux_category,
           (array_agg(r.crux_lcp_ms order by r.at desc))[1] as crux_lcp
    from sh_pages p join runs r on r.url = p.url
    where p.is_core and r.source = 'core'
    group by p.name, p.url, p.sort, r.strategy
  ), heavy as (
    select url, percentile_cont(0.5) within group (order by lcp_ms) as lcp,
           percentile_cont(0.5) within group (order by score) as score,
           count(*) as checks, max(at) as last_at
    from runs
    where source = 'rotation' and strategy = 'mobile' and lcp_ms is not null
    group by url
    order by lcp desc, url
    limit 10
  )
  select
    -- the bottom line: the home page on a phone; the row exists even before the first run
    coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'שורה תחתונה', 'page', h.name, 'url', h.url,
               'lcp_p50', round(c.lcp[1]::numeric)::int, 'checks', coalesce(c.checks, 0),
               'verdict', sh_verdict(round(c.lcp[1]::numeric)::int)))
      from sh_pages h left join core c on c.page = h.name and c.strategy = 'mobile'
      where h.is_home), '[]')
    || coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'ליבה', 'strategy', strategy, 'page', page, 'url', url,
               'lcp_p50', round(lcp[1]::numeric)::int, 'lcp_p95', round(lcp[2]::numeric)::int,
               'score_med', round(score::numeric)::int, 'cls_med', round(cls::numeric, 3),
               'ttfb_p50', round(ttfb::numeric)::int, 'slow_runs', slow_runs, 'checks', checks,
               'crux_category', crux_category, 'crux_lcp', crux_lcp)
               order by strategy desc, sort)   -- phone first
      from core), '[]')
    || coalesce((
      select jsonb_agg(jsonb_build_object(
               'section', 'האיטיים באתר', 'page', url, 'url', url,
               'lcp_p50', round(lcp::numeric)::int, 'score_med', round(score::numeric)::int,
               'checks', checks, 'last_il', sh_il(last_at))
               order by lcp desc, url)
      from heavy), '[]')
    -- coverage, in the column names the screen reads: checks = pages of today's sitemap that the
    -- rotation measured in the window, slow_runs = pages in today's sitemap
    || jsonb_build_object(
         'section', 'כיסוי',
         'checks', (select count(distinct r.url) from runs r join sh_site_pages s on s.url = r.url
                    where r.source = 'rotation' and s.active),
         'slow_runs', (select count(*) from sh_site_pages where active))
$$;

-- Median LCP per core page per bucket, for one strategy.
create or replace function sh_speed_series(p_from timestamptz, p_to timestamptz, p_strategy text) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(p_to - p_from < interval '73 hours');
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'page', page, 'url', url, 'bucket', bucket, 'lcp_p50', round(lcp::numeric)::int)
             order by sort, bucket), '[]')
    from (
      select p.name as page, p.url, p.sort, to_char(s.at at time zone v_tz, v_fmt) as bucket,
             percentile_cont(0.5) within group (order by s.lcp_ms) as lcp
      from sh_pages p join sh_speed s on s.url = p.url
      where p.is_core and s.source = 'core' and s.strategy = p_strategy and s.ok
        and s.at >= p_from and s.at < p_to
      group by p.name, p.url, p.sort, 4
    ) b);
end $$;

create or replace function sh_alerts_open() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', id, 'kind', kind, 'title', title, 'body', body,
           'opened_il', sh_il(opened_at), 'acked', acked_at is not null)
           order by opened_at desc, id desc), '[]')
  from sh_alerts
  where closed_at is null
$$;

-- Alerts that were open at any time inside the window.
create or replace function sh_alerts_range(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(sh_alert_row(a) order by a.opened_at desc, a.id desc), '[]')
  from sh_alerts a
  where a.opened_at < p_to and (a.closed_at is null or a.closed_at >= p_from)
$$;

-- The state of each measurement flow, by the age of its last successful run.
create or replace function sh_health() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'flow_name', flow_name,
           'status', case when age is null then 'אין נתון'
                          when age <= warn_minutes then 'תקין'
                          when age <= late_minutes then 'מתעכב'
                          else 'שקט' end,
           'cadence', cadence,
           'silent_txt', case when age > late_minutes then 'שקט כבר ' || sh_span(floor(age))
                              when age > warn_minutes then 'מאחר ב-' || sh_span(ceil(age - warn_minutes)) end,
           'last_at', last_at, 'warn_minutes', warn_minutes, 'late_minutes', late_minutes, 'note', note)
           order by sort), '[]')
  from (select *, extract(epoch from now() - last_at) / 60 as age from sh_flows where enabled) f
$$;

-- The broken products of the latest snapshot. sh_issues_set records the day of every snapshot,
-- so a snapshot without broken products empties the list.
create or replace function sh_product_issues() returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'issue', issue, 'name', name, 'url', url, 'snap_date', snap_date)
           order by issue, name, product_id), '[]')
  from sh_product_issues
  where snap_date = (select max(day) from sh_jobs where job = 'issues_snapshot')
$$;

-- The certificate of the configured host; JSON null before the first check.
create or replace function sh_cert() returns jsonb
language sql stable set search_path = public as $$
  select coalesce((
    select jsonb_build_object(
             'host', host, 'issuer', issuer, 'not_after', not_after, 'days_left', days_left,
             'ok', ok, 'err', err, 'checked_at', checked_at)
    from sh_cert
    where host = (select value #>> '{}' from sh_settings where key = 'host')), 'null')
$$;

-- ---------------------------------------------------------------- read side: /api/site/now

create or replace function sh_now() returns jsonb
language sql stable set search_path = public as $$
  with recent as (
    -- a round older than 15 minutes says nothing about now
    select x.round_at, x.kind, x.page, x.url, x.ok, x.status, x.ms, p.sort
    from sh_probe x left join sh_pages p on p.name = x.page
    where x.round_at >= now() - interval '15 minutes'
  ), last_full as (
    select max(round_at) as at from recent where kind = 'full'
  ), last_any as (
    select round_at as at, kind from recent order by round_at desc, kind limit 1
  ), latest as (
    select r.page, r.ok, r.sort from recent r join last_any l on r.round_at = l.at and r.kind = l.kind
  ), rum as (
    select count(*) as n, round(percentile_cont(0.75) within group (order by lcp_ms)::numeric)::int as p75
    from sh_rum
    where created_at >= now() - interval '60 minutes' and not is_test
      and site in (select jsonb_array_elements_text(value) from sh_settings where key = 'live_hosts')
  ), src as (
    select site, is_test from sh_rum order by created_at desc limit 1000
  )
  select jsonb_build_object(
    'pages', coalesce((
      select jsonb_agg(jsonb_build_object(
               'page', r.page, 'url', r.url, 'ok', r.ok, 'status', r.status,
               'ms', case when r.ok then r.ms end)
               order by r.sort nulls last, r.page)
      from recent r join last_full f on r.round_at = f.at
      where r.kind = 'full'), '[]'),
    'latest', coalesce((
      select jsonb_agg(jsonb_build_object('page', page, 'ok', ok) order by sort nulls last, page)
      from latest), '[]'),
    'light', coalesce((select kind = 'light' from last_any), false),
    'all_ok', coalesce((select bool_and(ok) from latest), false),
    'any_ok', coalesce((select bool_or(ok) from latest), false),
    'age_sec', (select floor(extract(epoch from now() - at))::int from last_any),
    'rum', (select jsonb_build_object('n', n, 'p75_ms', p75) from rum),
    'speed', coalesce((
      select jsonb_build_object('lcp_ms', s.lcp_ms, 'score', s.score, 'checked_at', s.at)
      from sh_pages p join sh_speed s on s.url = p.url
      where p.is_home and s.strategy = 'mobile' and s.ok and s.lcp_ms is not null
      order by s.at desc
      limit 1), '{}'),
    'alerts_open', (select count(*) from sh_alerts where closed_at is null),
    'rum_src', (
      select case when count(*) = 0 then 'null'::jsonb else jsonb_build_object(
               'n', count(*),
               'hosts', (select jsonb_agg(jsonb_build_object('host', site, 'n', n) order by n desc, site)
                         from (select site, count(*) as n from src group by site) h),
               'cols', '["created_at", "is_test", "lcp_ms", "path", "site"]'::jsonb,
               'test', count(*) filter (where is_test)) end
      from src))
$$;

-- ---------------------------------------------------------------- read side: drill-downs

-- The failed checks of the full rounds, newest first, at most 500.
create or replace function sh_drill_fails(
  p_from timestamptz, p_to timestamptz, p_page text default null, p_bucket text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(length(p_bucket) > 10);
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'at_il', sh_il(round_at), 'page', page, 'kind', sh_fail_kind(fail, status), 'err', err, 'ms', ms)
             order by round_at desc, page), '[]')
    from (
      select round_at, page, fail, status, err, ms
      from sh_probe
      where kind = 'full' and not ok and round_at >= p_from and round_at < p_to
        and (coalesce(p_page, '') = '' or page = p_page)
        and (coalesce(p_bucket, '') = '' or to_char(round_at at time zone v_tz, v_fmt) = p_bucket)
      order by round_at desc, page
      limit 500
    ) f);
end $$;

-- Response time per page inside one bucket of the availability chart.
create or replace function sh_drill_bucket(p_bucket text) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz    text := sh_tz();
  v_fmt   text := sh_bucket_fmt(length(p_bucket) > 10);
  v_start timestamp := p_bucket::timestamp;
  v_end   timestamp := v_start + case when length(p_bucket) > 10 then interval '1 hour' else interval '1 day' end;
begin
  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'page', b.page, 'checks', b.checks, 'failed', b.failed,
             'ms_p50', round(b.p50::numeric)::int, 'ms_max', b.ms_max, 'worst_il', sh_il(b.worst_at))
             order by p.sort nulls last, b.page), '[]')
    from (
      select page, count(*) as checks, count(*) filter (where not ok) as failed,
             percentile_cont(0.5) within group (order by ms) filter (where ok) as p50,
             max(ms) filter (where ok) as ms_max,
             (array_agg(round_at order by ms desc nulls last, round_at) filter (where ok))[1] as worst_at
      from sh_probe
      where kind = 'full'
        -- An hour more on each side, then the bucket's own text: on the night the clocks go
        -- back one local hour happens twice, and the chart counted both in this bucket.
        and round_at >= (v_start at time zone v_tz) - interval '1 hour'
        and round_at <  (v_end at time zone v_tz) + interval '1 hour'
        and to_char(round_at at time zone v_tz, v_fmt) = p_bucket
      group by page
    ) b left join sh_pages p on p.name = b.page);
end $$;

-- The lab runs of one page, newest first. A failed run carries only its error.
create or replace function sh_drill_runs(
  p_from timestamptz, p_to timestamptz, p_url text, p_strategy text default 'mobile',
  p_bucket text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_tz  text := sh_tz();
  v_fmt text := sh_bucket_fmt(length(p_bucket) > 10);
begin
  return (
    select coalesce(jsonb_agg(
             case when ok then jsonb_build_object(
                    'ok', true, 'err', null, 'at_il', sh_il(at), 'lcp_ms', lcp_ms, 'score', score,
                    'ttfb_ms', ttfb_ms, 'bytes', bytes, 'cls', cls, 'crux_category', crux_category,
                    'crux_lcp_ms', crux_lcp_ms, 'opps', coalesce(opps, '[]'))
                  else jsonb_build_object('ok', false, 'err', err, 'at_il', sh_il(at)) end
             order by at desc), '[]')
    from sh_speed
    where url = p_url and strategy = p_strategy and at >= p_from and at < p_to
      and (coalesce(p_bucket, '') = '' or to_char(at at time zone v_tz, v_fmt) = p_bucket));
end $$;

-- One alert: its row, the failed checks behind a "down" alert, and the pushes that were sent.
create or replace function sh_drill_alert(p_id bigint) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(sh_alert_row(a) || jsonb_build_object(
    'fails', coalesce((
      -- the sheet prints "קוד <status>" when there is a status and err otherwise, so the status
      -- goes out only when the status was the failure, and every other failure gets words
      select jsonb_agg(jsonb_build_object(
               'at', sh_il(f.round_at), 'page', f.page,
               'status', case when f.fail = 'http' then f.status end,
               'err', case when f.fail <> 'http' then coalesce(f.err, sh_fail_kind(f.fail, f.status)) end)
               order by f.round_at)
      from (
        -- The failed checks (full and light) from the last answer before the alert opened until
        -- it closed. An alert opens within a minute or two of the first failure, so a day back
        -- is far enough to look for that last answer.
        select x.round_at, x.page, x.status, x.err, x.fail
        from sh_probe x
        where a.kind = 'down' and x.page = substr(a.key, 6) and not x.ok
          and x.round_at <= coalesce(a.closed_at, now())
          and x.round_at > coalesce((
                select max(o.round_at) from sh_probe o
                where o.page = substr(a.key, 6) and o.ok
                  and o.round_at <= a.opened_at and o.round_at > a.opened_at - interval '1 day'),
                a.opened_at - interval '1 day')
        order by x.round_at
        limit 500
      ) f), '[]'),
    -- a push appears once its fate is known: delivered, or given up after the last retry
    'sent', coalesce((
      select jsonb_agg(jsonb_build_object('event', m.event, 'status', m.status, 'at', sh_il(m.at))
               order by m.at, m.id)
      from sh_messages m
      where m.alert_id = a.id and m.status is not null), '[]'))), '[]')
  from sh_alerts a
  where a.id = p_id
$$;

-- ---------------------------------------------------------------- read side: the rest

-- The push log, newest first. sent = the push service accepted it.
create or replace function sh_messages(p_from timestamptz, p_to timestamptz) returns jsonb
language sql stable set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
           'kind', kind, 'title', title, 'msg', msg, 'at_il', sh_il(at),
           'sent', coalesce(status between 200 and 299, false))
           order by at desc, id desc), '[]')
  from sh_messages
  where at >= p_from and at < p_to
$$;

-- "ראיתי": hides open alerts from the red bar. It does not close them, and an alert that is
-- closed or already marked is left as it is.
create or replace function sh_alert_ack(p_ids jsonb, p_who text) returns jsonb
language sql set search_path = public as $$
  with marked as (
    update sh_alerts set acked_at = now(), acked_by = p_who
    where id in (select value::bigint from jsonb_array_elements_text(p_ids))
      and closed_at is null and acked_at is null
    returning 1
  )
  select jsonb_build_object('n', count(*)) from marked
$$;

create or replace function sh_login_log_add(p_ip text, p_ok boolean, p_who text, p_ua text) returns jsonb
language sql set search_path = public as $$
  with added as (
    insert into sh_login_log (ip, ok, who, ua) values (p_ip, p_ok, p_who, p_ua) returning 1
  )
  select jsonb_build_object('n', count(*)) from added
$$;

-- Real-user page views: [{site, path, lcp_ms, is_test}]. The last line of defence for two
-- promises of the ingest: no query strings are stored, and no impossible timings.
create or replace function sh_rum_add(p_rows jsonb) returns jsonb
language sql set search_path = public as $$
  with added as (
    insert into sh_rum (site, path, lcp_ms, is_test)
    select r.site, regexp_replace(r.path, '[?#].*$', ''), r.lcp_ms, coalesce(r.is_test, false)
    from jsonb_to_recordset(p_rows) as r(site text, path text, lcp_ms numeric, is_test boolean)
    where r.site is not null and r.path is not null and r.lcp_ms between 1 and 60000
    returning 1
  ), beat as (
    update sh_flows set last_at = now()
    where flow_name = 'מהירות אצל לקוחות' and exists (select 1 from added)
  )
  select jsonb_build_object('n', count(*)) from added
$$;

create or replace function sh_ping() returns jsonb
language sql stable set search_path = public as $$
  select '"ok"'::jsonb
$$;

-- ---------------------------------------------------------------- write side: collectors
-- Every collector function writes its flow's proof of life (sh_flows.last_at) last, and only
-- when the run succeeded: a collector that fails leaves no trace and shows up as late or silent.

-- One probe round: [{page, url, ok, status, ms, fail, err}]. A round that is sent twice is
-- stored once.
create or replace function sh_probe_add(p_round_at timestamptz, p_kind text, p_rows jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_n int;
begin
  insert into sh_probe (round_at, kind, page, url, ok, status, ms, fail, err)
  select p_round_at, p_kind, r.page, r.url, r.ok, r.status, r.ms, nullif(r.fail, ''), nullif(r.err, '')
  from jsonb_to_recordset(p_rows)
       as r(page text, url text, ok boolean, status numeric, ms numeric, fail text, err text)
  on conflict do nothing;
  get diagnostics v_n = row_count;
  -- A full round proves the prober ran, also when every page failed. A light round does not
  -- count: the flow is "a full round every minute".
  if p_kind = 'full' and v_n > 0 then
    update sh_flows set last_at = greatest(last_at, p_round_at) where flow_name = 'בודק זמינות האתר';
  end if;
  return jsonb_build_object('n', v_n);
end $$;

-- Lab runs: [{at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms, bytes,
-- crux_category, crux_lcp_ms, opps}]. A run that is sent twice is stored once.
create or replace function sh_speed_add(p_rows jsonb) returns jsonb
language sql set search_path = public as $$
  with added as (
    insert into sh_speed (at, url, page, strategy, source, ok, err, score, lcp_ms, cls, ttfb_ms,
                          bytes, crux_category, crux_lcp_ms, opps)
    select coalesce(r.at, now()), r.url, r.page, r.strategy, r.source, r.ok, r.err, r.score, r.lcp_ms,
           r.cls, r.ttfb_ms, r.bytes, r.crux_category, r.crux_lcp_ms, r.opps
    from jsonb_to_recordset(p_rows)
         as r(at timestamptz, url text, page text, strategy text, source text, ok boolean, err text,
              score numeric, lcp_ms numeric, cls numeric, ttfb_ms numeric, bytes numeric,
              crux_category text, crux_lcp_ms numeric, opps jsonb)
    on conflict do nothing
    returning at, source, ok
  ), beat as (
    -- each of the two speed flows is alive when one of its runs succeeded
    update sh_flows f set last_at = greatest(f.last_at, a.at)
    from (select source, max(at) as at from added where ok group by source) a
    where f.flow_name = case a.source when 'core' then 'מדידת מהירות — עמודי ליבה'
                                      else 'מדידת מהירות — סבב כל האתר' end
  )
  select jsonb_build_object('n', count(*)) from added
$$;

-- Claims the p_n site pages that were measured longest ago (never measured first) and returns
-- their addresses. A page is claimed whether or not its measurement then succeeds.
create or replace function sh_rotation_next(p_n int) returns jsonb
language sql set search_path = public as $$
  with stamp as materialized (
    -- the clock, not now(): two claims inside one transaction must still take turns
    select clock_timestamp() as at
  ), pick as (
    select url from sh_site_pages
    where active
    order by last_measured_at nulls first, url
    limit p_n
    for update skip locked
  ), claimed as (
    update sh_site_pages s set last_measured_at = stamp.at
    from pick, stamp
    where s.url = pick.url
    returning s.url
  )
  select coalesce(jsonb_agg(url order by url), '[]') from claimed
$$;

-- The pages of the site, from its sitemap: ["https://…", …].
create or replace function sh_sitemap_set(p_urls jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_n int;
begin
  -- an empty read looks exactly like a site whose pages all vanished
  if coalesce(jsonb_array_length(p_urls), 0) = 0 then
    raise exception 'sh_sitemap_set: an empty list is refused';
  end if;
  insert into sh_site_pages (url)
  select distinct url from jsonb_array_elements_text(p_urls) as url
  on conflict (url) do update set active = true, last_seen = now();
  get diagnostics v_n = row_count;
  update sh_site_pages set active = false where active and not p_urls ? url;
  update sh_flows set last_at = now() where flow_name = 'טעינת מפת האתר';
  return jsonb_build_object('n', v_n);
end $$;

-- The certificate check: {host, issuer, not_before, not_after, days_left, ok, err, checked_at}.
create or replace function sh_cert_set(p_row jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  r record;
begin
  select x.host, x.issuer, x.not_before, x.not_after, x.days_left, x.ok, x.err,
         coalesce(x.checked_at, now()) as checked_at
    into r
  from jsonb_to_record(p_row) as x(host text, issuer text, not_before timestamptz, not_after timestamptz,
                                   days_left numeric, ok boolean, err text, checked_at timestamptz);
  if r.ok then
    insert into sh_cert (host, issuer, not_before, not_after, days_left, ok, err, checked_at)
    values (r.host, r.issuer, r.not_before, r.not_after, r.days_left, true, null, r.checked_at)
    on conflict (host) do update
      set issuer = excluded.issuer, not_before = excluded.not_before, not_after = excluded.not_after,
          days_left = excluded.days_left, ok = true, err = null, checked_at = excluded.checked_at;
    update sh_flows set last_at = greatest(last_at, r.checked_at) where flow_name = 'בדיקת תעודת האבטחה';
  else
    -- a failed check keeps what the last successful one found: the alert rule reads it
    insert into sh_cert (host, ok, err, checked_at) values (r.host, false, r.err, r.checked_at)
    on conflict (host) do update set ok = false, err = excluded.err, checked_at = excluded.checked_at;
  end if;
  return jsonb_build_object('n', 1);
end $$;

-- The broken products of one day's catalogue snapshot, replacing that day:
-- [{product_id, issue, name, url}]. Call it only with a complete read, also when it is empty.
create or replace function sh_issues_set(p_snap_date date, p_rows jsonb) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_n int;
begin
  delete from sh_product_issues where snap_date = p_snap_date;
  insert into sh_product_issues (snap_date, product_id, issue, name, url)
  select p_snap_date, r.product_id, r.issue, r.name, r.url
  from jsonb_to_recordset(p_rows) as r(product_id text, issue text, name text, url text);
  get diagnostics v_n = row_count;
  -- the day itself is remembered: a snapshot without broken products must still become "the latest"
  insert into sh_jobs (job, day) values ('issues_snapshot', p_snap_date) on conflict do nothing;
  update sh_flows set last_at = now() where flow_name = 'בדיקת מוצרים שבורים';
  return jsonb_build_object('n', v_n);
end $$;

-- Daily jobs keep their "done for this day" marker here, not in the worker's memory.
create or replace function sh_job_due(p_job text, p_day date) returns jsonb
language sql stable set search_path = public as $$
  select to_jsonb(not exists (select 1 from sh_jobs where job = p_job and day = p_day))
$$;

-- true when this call set the marker, false when the day was already marked.
create or replace function sh_job_mark(p_job text, p_day date) returns jsonb
language sql set search_path = public as $$
  with marked as (
    insert into sh_jobs (job, day) values (p_job, p_day) on conflict do nothing returning 1
  )
  select to_jsonb(exists (select 1 from marked))
$$;

-- ---------------------------------------------------------------- alerts and pushes

-- Evaluates the four alert rules, opens and closes alerts, queues their pushes, and returns
-- every push that is still owed, oldest first. Call it every minute, after the full probe round.
create or replace function sh_alerts_check() returns jsonb
language plpgsql set search_path = public as $$
declare
  v_down_after int := coalesce((select (value #>> '{}')::int from sh_settings where key = 'down_after'), 1);
begin
  -- One evaluation at a time: a second caller waits here and then, under read committed (the
  -- default), sees what the first one did. Under any stricter level the unique index on open
  -- alerts still forbids a duplicate, and the second caller gets an error instead.
  perform pg_advisory_xact_lock(hashtext('sh_alerts_check'));

  with state as materialized (
    -- One row per thing that can be judged right now. bad = the alert should be open,
    -- good = it should be closed; neither = no news (for example: no check since).

    -- down: the newest down_after rounds of a probe page, full or light, all failed
    select 'down:' || p.name as key, 'down' as kind, 'האתר לא עונה: ' || p.name as title,
           sh_fail_kind(r.fail, r.status) || E'\n' || r.url as body,
           r.n = v_down_after and not r.any_ok as bad, coalesce(r.ok, false) as good
    from sh_pages p
    cross join lateral (
      select count(*) as n, bool_or(t.ok) as any_ok,
             (array_agg(t.ok order by t.round_at desc, t.kind))[1] as ok,
             (array_agg(t.fail order by t.round_at desc, t.kind))[1] as fail,
             (array_agg(t.status order by t.round_at desc, t.kind))[1] as status,
             (array_agg(t.url order by t.round_at desc, t.kind))[1] as url
      from (select x.round_at, x.kind, x.ok, x.fail, x.status, x.url
            from sh_probe x
            -- a round from before yesterday is no evidence about now, and without this bound a
            -- page that was never probed would cost a walk through the whole history
            where x.page = p.name and x.round_at > now() - interval '1 day'
            order by x.round_at desc, x.kind
            limit v_down_after) t
    ) r
    where p.is_probe

    union all
    -- slow: the two newest successful phone runs of a core page are both above 4 seconds
    select 'slow:' || p.name, 'slow', 'עמוד איטי: ' || p.name,
           to_char(r.newest / 1000.0, 'FM990.0') || ' שניות עד התוכן, פעמיים ברצף' || E'\n' || p.url,
           r.n = 2 and r.fastest > 4000, coalesce(r.newest <= 4000, false)
    from sh_pages p
    cross join lateral (
      select count(*) as n, min(t.lcp_ms) as fastest, (array_agg(t.lcp_ms order by t.at desc))[1] as newest
      from (select s.at, s.lcp_ms
            from sh_speed s
            where s.url = p.url and s.strategy = 'mobile' and s.ok and s.lcp_ms is not null
            order by s.at desc
            limit 2) t
    ) r
    where p.is_core

    union all
    -- silent: a flow that has run before is older than its late_minutes. It clears when the flow
    -- "ran again": a run that is not older than the alert. (Not "is young enough again": the
    -- independent check of SPEC 7.10 opens this alert earlier than late_minutes, and must not
    -- see it closed a minute later.)
    select 'silent:' || f.flow_name, 'silent', 'המדידה נעצרה: ' || f.flow_name,
           'אין מדידה כבר ' || floor(f.age) || ' דקות',
           f.age > f.late_minutes,
           coalesce(f.last_at >= (select a.opened_at from sh_alerts a
                                  where a.key = 'silent:' || f.flow_name and a.closed_at is null), false)
    from (select *, extract(epoch from now() - last_at) / 60 as age from sh_flows) f
    where f.enabled and f.last_at is not null

    union all
    -- cert: the last successful check found fewer than 14 days
    select 'cert:' || c.host, 'cert', 'תעודת האבטחה פגה בעוד ' || c.days_left || ' ימים', c.host,
           c.days_left < 14, c.days_left >= 14
    from sh_cert c
    where c.host = (select value #>> '{}' from sh_settings where key = 'host') and c.days_left is not null
  ), opened as (
    -- insert, never upsert: the unique index on key covers open alerts only
    insert into sh_alerts (key, kind, title, body)
    select s.key, s.kind, s.title, s.body
    from state s
    where s.bad and not exists (select 1 from sh_alerts a where a.key = s.key and a.closed_at is null)
    returning id, kind, title, body
  ), closed as (
    -- also closes an alert whose subject is gone (a page that left the configuration, a flow
    -- that was disabled): nothing could ever clear it
    update sh_alerts a set closed_at = now()
    where a.closed_at is null and a.kind in ('down', 'slow', 'silent', 'cert')
      and coalesce((select s.good from state s where s.key = a.key), true)
    returning a.id, a.title, a.opened_at
  )
  insert into sh_messages (alert_id, event, kind, title, msg, priority)
  select id, 'open', 'התראה', title, body, case when kind in ('down', 'silent') then 4 else 3 end
  from opened
  union all
  select id, 'close', 'חזר לתקין', title,
         'נמשך ' || floor(extract(epoch from now() - opened_at) / 60) || ' דקות', 2
  from closed;

  return (
    select coalesce(jsonb_agg(jsonb_build_object(
             'id', id, 'title', title, 'msg', msg, 'priority', priority, 'click', click,
             'kind', kind, 'event', event)
             order by at, id), '[]')
    from sh_messages
    where status is null and attempts < 5);
end $$;

-- Records one attempt to push a message. A 2xx status settles it as sent; a fifth failed
-- attempt settles it as not sent; until then it stays owed and sh_alerts_check returns it again.
create or replace function sh_message_sent(p_id bigint, p_status int) returns jsonb
language sql set search_path = public as $$
  with tried as (
    update sh_messages
    set attempts = attempts + 1,
        status = case when p_status between 200 and 299 or attempts >= 4 then p_status end
    where id = p_id and status is null
    returning 1
  )
  select jsonb_build_object('n', count(*)) from tried
$$;

-- Queues the morning summary of the last 24 hours, once per day: the day's marker is set first,
-- so a second call (or a second worker) queues nothing.
create or replace function sh_morning(p_day date) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_checks  numeric;
  v_failed  numeric;
  v_outages int;
  v_minutes int;
  v_up      numeric;
  v_verdict text;
  v_open    int;
begin
  insert into sh_jobs (job, day) values ('morning', p_day) on conflict do nothing;
  if not found then
    return jsonb_build_object('n', 0);
  end if;

  -- the same figures the screen shows for "24 שעות", from the same functions
  select sum((r ->> 'checks')::int), sum((r ->> 'failed')::int),
         count(*) filter (where r ? 'outage_minutes'), sum((r ->> 'outage_minutes')::int)
    into v_checks, v_failed, v_outages, v_minutes
  from jsonb_array_elements(sh_availability(now() - interval '24 hours', now())) r;
  v_up := 100 - 100 * v_failed / nullif(v_checks, 0);
  select r ->> 'verdict' into v_verdict
  from jsonb_array_elements(sh_speed(now() - interval '24 hours', now())) r
  where r ->> 'section' = 'שורה תחתונה';
  select count(*) into v_open from sh_alerts where closed_at is null;

  insert into sh_messages (event, kind, title, msg, priority)
  values ('morning', 'בוקר',
          case v_open when 0 then 'בוקר טוב: האתר תקין'
                      when 1 then 'בוקר טוב: התראה פתוחה אחת'
                      else 'בוקר טוב: ' || v_open || ' התראות פתוחות' end,
          -- a line without a value is left out
          concat_ws(E'\n',
            coalesce('זמינות ' || to_char(v_up, case when v_up < 99.95 then 'FM990.00' else 'FM990.0' end) || '% ב-24 שעות',
                     'אין בדיקות זמינות ב-24 שעות'),
            case when v_outages > 0 then 'נפילות: ' || v_outages || ' (' || v_minutes || ' דקות)' end,
            'מהירות עמוד הבית: ' || v_verdict),
          2);
  return jsonb_build_object('n', 1);
end $$;

-- The retention rules. Alerts, messages and catalogue snapshots are kept.
create or replace function sh_cleanup() returns jsonb
language plpgsql set search_path = public as $$
declare
  v_probe int; v_light int; v_speed int; v_rum int; v_logins int;
begin
  delete from sh_probe where round_at < now() - interval '400 days';
  get diagnostics v_probe = row_count;
  delete from sh_probe where kind = 'light' and round_at < now() - interval '7 days';
  get diagnostics v_light = row_count;
  delete from sh_speed where at < now() - interval '400 days';
  get diagnostics v_speed = row_count;
  delete from sh_rum where created_at < now() - interval '30 days';
  get diagnostics v_rum = row_count;
  delete from sh_login_log where at < now() - interval '400 days';
  get diagnostics v_logins = row_count;
  return jsonb_build_object('probe', v_probe, 'probe_light', v_light, 'speed', v_speed,
                            'rum', v_rum, 'login_log', v_logins);
end $$;

-- ---------------------------------------------------------------- privileges
-- Only the owner of these functions may run them. On Supabase the service role (the secret
-- key) may too, and the two public API roles lose the grant they get by default.
do $$
declare
  f regprocedure;
  r text;
begin
  for f in select p.oid::regprocedure from pg_proc p
           where p.pronamespace = 'public'::regnamespace and p.proname like 'sh\_%' loop
    execute format('revoke all on function %s from public', f);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on function %s from %I', f, r);
      end if;
    end loop;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f);
    end if;
  end loop;
end $$;
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/requirements.txt sha256=2dc54db937dacc2e56b3da4fcf7ad7fdab35c58996123333188157733f3552c1 -->
~~~~~~~~text
# The server. Tested with Python 3.13.
fastapi==0.162.5
uvicorn==0.54.0
# Needed only with DATABASE_URL. With SUPABASE_URL + SUPABASE_SECRET_KEY, db.py uses the standard library.
psycopg[binary]==3.3.9

# Time zones come from the operating system. Where it has none (Windows, Alpine images), add: tzdata
# For tests/test_server.py: pytest==9.2.0 httpx==0.28.1
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/schema.sql sha256=fb58b7f32b56e452066b5e093a8909d52cf569a9aae2d0632ce00212dff22ab1 -->
~~~~~~~~sql
-- Site Health: tables, indexes, privileges.
-- Plain PostgreSQL 15+, no extensions. Safe to run again: nothing here drops or rewrites data.
-- Apply this file first, then functions.sql. Nothing but the sh_* functions touches these tables.

create table if not exists sh_settings (
  key   text primary key,
  value jsonb not null
);

-- The configured pages, replaced as a whole by sh_setup. History in sh_probe / sh_speed
-- carries its own page name and url, so it survives a page leaving the configuration.
create table if not exists sh_pages (
  name     text primary key,
  url      text not null,
  is_probe boolean not null default false,
  is_core  boolean not null default false,
  is_home  boolean not null default false,
  sort     int not null,
  expect   text
);

-- One availability check. About 1,440 full rounds a day per probe page: 2.3 million rows
-- (some 340 MB, index included) for 4 pages over the 400 days that are kept. The primary key
-- serves every time-window read (rows arrive in time order), so there is no second full-size index.
create table if not exists sh_probe (
  round_at timestamptz not null,
  kind     text not null check (kind in ('full', 'light')),
  page     text not null,
  url      text not null,
  ok       boolean not null,
  status   int,
  ms       int,
  fail     text check (fail in ('timeout', 'http', 'connect', 'content')),
  err      text,
  primary key (round_at, kind, page),
  check (ok = (fail is null)),
  check (fail <> 'http' or status is not null)
);
-- Two small partial indexes. Failed checks are rare, and the drill-downs read only them.
-- Light rounds live for a week, and the nightly cleanup must find the old ones without reading
-- 400 days of full rounds.
create index if not exists sh_probe_failed on sh_probe (round_at) where not ok;
create index if not exists sh_probe_light on sh_probe (round_at) where kind = 'light';

-- One lab speed run. About 1,200 a day: half a million rows over 400 days, and up to 700 MB,
-- nearly all of it the opps lists (about 1 KB when a run carries eight of them).
-- The primary key makes a repeated insert harmless and serves "the runs of one page".
create table if not exists sh_speed (
  at            timestamptz not null default now(),
  url           text not null,
  page          text,
  strategy      text not null check (strategy in ('mobile', 'desktop')),
  source        text not null check (source in ('core', 'rotation')),
  ok            boolean not null,
  err           text,
  score         int,
  lcp_ms        int,
  cls           numeric(6, 3),
  ttfb_ms       int,
  bytes         bigint,
  crux_category text,
  crux_lcp_ms   int,
  opps          jsonb,
  primary key (url, strategy, at)
);
create index if not exists sh_speed_at on sh_speed (at);

create table if not exists sh_site_pages (
  url              text primary key,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now(),
  last_measured_at timestamptz
);

-- One real-user page view. Nothing here may identify a person: no IP, no cookie, no user agent.
create table if not exists sh_rum (
  created_at timestamptz not null default now(),
  site       text not null,
  path       text not null,
  lcp_ms     int not null,
  is_test    boolean not null default false
);
create index if not exists sh_rum_created_at on sh_rum (created_at);

-- The certificate fields hold the last successful check; ok / err / checked_at the last check.
create table if not exists sh_cert (
  host       text primary key,
  issuer     text,
  not_before timestamptz,
  not_after  timestamptz,
  days_left  int,
  ok         boolean not null,
  err        text,
  checked_at timestamptz not null
);

create table if not exists sh_product_issues (
  snap_date  date not null,
  product_id text not null,
  issue      text not null,
  name       text,
  url        text,
  primary key (snap_date, product_id, issue)
);

-- kind is free text: other parts of the owner's system may add their own alert kinds.
create table if not exists sh_alerts (
  id        bigint generated always as identity primary key,
  key       text not null,
  kind      text not null,
  title     text not null,
  body      text,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  acked_at  timestamptz,
  acked_by  text
);
-- At most one open alert per key. Partial, so it cannot be the target of an upsert over REST:
-- sh_alerts_check looks for an open row and inserts when there is none.
create unique index if not exists sh_alerts_open_key on sh_alerts (key) where closed_at is null;

-- status: the HTTP status of the push once it is final; null while the push is still owed.
create table if not exists sh_messages (
  id       bigint generated always as identity primary key,
  at       timestamptz not null default now(),
  alert_id bigint references sh_alerts (id),
  event    text not null,
  kind     text not null,
  title    text not null,
  msg      text,
  priority int not null default 3,
  click    text,
  status   int,
  attempts int not null default 0
);
create index if not exists sh_messages_at on sh_messages (at);

create table if not exists sh_flows (
  flow_name    text primary key,
  sort         int not null,
  cadence      text not null,
  warn_minutes int not null,
  late_minutes int not null,
  note         text,
  enabled      boolean not null default true,
  last_at      timestamptz
);

create table if not exists sh_jobs (
  job text not null,
  day date not null,
  primary key (job, day)
);

create table if not exists sh_login_log (
  at  timestamptz not null default now(),
  ip  text,
  ok  boolean not null,
  who text,
  ua  text
);

-- Private tables: row level security without policies shuts out every role but the owner of
-- the tables and roles that bypass it (on Supabase: the service role), and on Supabase the two
-- public API roles lose their default grants as well.
do $$
declare
  t text;
  r text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' and tablename like 'sh\_%' loop
    execute format('alter table public.%I enable row level security', t);
    foreach r in array array['anon', 'authenticated'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('revoke all on table public.%I from %I', t, r);
      end if;
    end loop;
  end loop;
end $$;
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/server.py sha256=1c403fc6a1d72caac4855c9c721ddd3de77543d9ee5d0061417a58dbeb4cae3e -->
~~~~~~~~python
"""Site Health server: sign-in, roles, the screen and its data calls (SPEC.md §5 and §8).

No business logic lives here. Every figure comes from an sh_* SQL function through db.rpc();
this file decides who may see what and turns failures into the statuses of §5.7.

    uvicorn server:app --host 0.0.0.0 --port 8000        # one worker: each worker would start its own collectors

Environment: SH_PASS_OWNER (without it nobody can sign in), SH_PASS_STAFF, SH_PASS_VENDOR_<NAME>,
SH_VENDOR_NOALERTS, SH_SHARE_TOKEN, SH_SCREEN, COLLECTORS, and the database variables of db.py.
Everything about the site itself comes from sh_config().
"""
import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import time
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

import db

log = logging.getLogger("uvicorn.error")     # the logger uvicorn prints; one of our own is silent below WARNING

COOKIE = "sh_session"
SESSION_LABEL = b"site-health-session-v1"
VENDOR_PREFIX = "SH_PASS_VENDOR_"
DEFAULT_SCREEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "site_health.html")
MARKER = "<!--SH_INJECT-->"

# Access (§8.2). An outsider (vendor, share link) gets an allow-list, so a route added later is closed to them.
OPEN_PATHS = {"/login", "/logout", "/health", "/rum"}        # answered without a session
DATA_PATHS = {"/api/site", "/api/site/now", "/api/site/drill"}
OUTSIDER_PATHS = DATA_PATHS | {"/site", "/status"}           # all an outsider may GET; nothing else, no other method
SITE_ALERT_KINDS = {"down", "slow", "silent", "cert"}        # the only alerts an outsider sees

MAX_FAILURES, FAILURE_WINDOW = 8, 600                        # failed sign-ins from one address, within seconds
PROBE_FLOW = "בודק זמינות האתר"                              # the flow whose last run is "the last check"

RUM_MAX_BYTES, RUM_PER_MINUTE, RUM_BATCH, RUM_QUEUE = 1024, 60, 50, 1000
RUM_PRIVATE = {"account", "my-account", "checkout", "checkouts", "order", "orders", "order-received", "order-pay",
               "view-order", "lost-password", "admin", "wp-admin", "wp-login.php"}     # path segments never stored
RUM_SITE = re.compile(r"[a-z0-9.-]{1,253}")                  # "live" or a host name

TEXT_WRONG = "סיסמה שגויה"
TEXT_BLOCKED = "יותר מדי ניסיונות. נסו שוב בעוד עשר דקות."
TEXT_BAD_LINK = "הקישור אינו תקין או שפג."
TEXT_NO_DATA = "אין כרגע חיבור לנתונים. נסו שוב בעוד רגע."

PAGE_SHELL = """<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>בריאות האתר</title><style>
:root{--brand:#0d9668;--bg:#ffffff;--surface:#f4f8f6;--line2:#cdd8d2;--tx:#18241f;--dfg:#a3271f}
@media (prefers-color-scheme:dark){:root{--brand:#2fbf8f;--bg:#0f1512;--surface:#19211d;--line2:#35423b;--tx:#e9efeb;--dfg:#f0968f}}
html,body{background:var(--bg);color:var(--tx);margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Hebrew",Arial,sans-serif}
.wrap{min-height:100svh;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
.card{width:100%;max-width:330px;text-align:center}
.site{font-size:13px;letter-spacing:.06em;color:var(--brand);min-height:18px}
h1{font-size:21px;font-weight:500;margin:8px 0 18px}
input,button{width:100%;height:46px;border-radius:10px;font-family:inherit;box-sizing:border-box}
input{border:1px solid var(--line2);background:var(--surface);color:var(--tx);font-size:16px;text-align:center}
button{margin-top:10px;border:0;background:var(--brand);color:var(--bg);font-size:15px;font-weight:600;cursor:pointer}
.err{color:var(--dfg);font-size:13px;margin-top:10px;min-height:18px}
</style></head><body><div class="wrap">__BODY__</div></body></html>"""
LOGIN_FORM = """<form class="card" method="post" action="/login">
<div class="site" dir="ltr">__SITE__</div><h1>בריאות האתר</h1>
<input name="p" type="password" placeholder="סיסמה" aria-label="סיסמה" autocomplete="current-password" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus>
<button type="submit">כניסה</button><div class="err" role="alert">__ERROR__</div></form>"""


# ---------------------------------------------------------------- who is asking

class Viewer(NamedTuple):
    role: str                   # owner | staff | vendor | share
    who: str                    # the name in the login log and on "seen by"
    no_alerts: bool = False     # a vendor who must not see alerts

    @property
    def outsider(self):
        return self.role in ("vendor", "share")

    @property
    def screen_role(self):
        """window.SH_ROLE (§6.7). It only hides controls; the rules themselves are enforced in this file."""
        if self.role == "share":
            return {"share": True}
        if self.role == "vendor":
            return {"readonly": True, "noAlerts": True} if self.no_alerts else {"readonly": True}
        return {}


SHARE_LINK = Viewer("share", "share")


def _norm(password):
    """Passwords are compared trimmed and case-insensitively: phone keyboards capitalize the first letter."""
    return (password or "").strip().casefold()


def _same(a, b):
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _token(password):
    """The session cookie: an HMAC keyed with the person's (normalized) password. Changing or deleting
    the password in the host's settings signs that person out at once; there is no session table."""
    return hmac.new(password.encode("utf-8"), SESSION_LABEL, hashlib.sha256).hexdigest()


def _accounts():
    """Everyone who can sign in, as (normalized password, Viewer), least privileged first.

    The order is the collision rule. Two people with one password have one cookie, and both lookups
    below stop at the first match, so a shared password can take rights away but never grant them.
    Read from the environment on every call; an unset or blank password never matches."""
    env = os.environ
    if not _norm(env.get("SH_PASS_OWNER")):
        return []
    quiet = {name.strip().casefold() for name in env.get("SH_VENDOR_NOALERTS", "").split(",")}
    vendors = []
    for variable in sorted(env):
        name = variable.removeprefix(VENDOR_PREFIX)
        if variable.startswith(VENDOR_PREFIX) and name:
            vendors.append((env[variable], Viewer("vendor", name, name.casefold() in quiet)))
    vendors.sort(key=lambda account: not account[1].no_alerts)          # stable: those without alerts first
    people = vendors + [(env.get("SH_PASS_STAFF"), Viewer("staff", "staff")),
                        (env["SH_PASS_OWNER"], Viewer("owner", "owner"))]
    return [(_norm(password), viewer) for password, viewer in people if _norm(password)]


def _by_password(password):
    """(Viewer, cookie value) for a typed password, or None."""
    typed = _norm(password)
    for known, viewer in _accounts():
        if _same(typed, known):
            return viewer, _token(known)
    return None


def _by_cookie(request):
    cookie = request.cookies.get(COOKIE, "")
    for known, viewer in _accounts():
        if _same(cookie, _token(known)):
            return viewer
    return None


def _share_ok(k):
    token = os.environ.get("SH_SHARE_TOKEN", "").strip()     # blank: the share link is switched off
    return bool(token and k) and _same(k, token)


def _viewer(request):
    """Who this request is, or None. On the share page, and on a data call that carries k, only the
    share token counts: the link shows what the link shows, whoever opens it. Nowhere else is k read."""
    path, k = request.url.path, request.query_params.get("k", "")
    if path == "/status" or (k and path in DATA_PATHS):
        return SHARE_LINK if _share_ok(k) else None
    return _by_cookie(request)


def _client_ip(request):
    # Behind a host's proxy (Render and the like) the socket peer is the proxy, so the forwarded address
    # is used. Where no proxy overwrites this header a client can forge it: the per-address limits slow
    # guessing down, they do not replace good passwords.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _is_https(request):
    return request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip() == "https"


# ---------------------------------------------------------------- answers

def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def _html(page, status=200):
    return HTMLResponse(page, status_code=status, headers={"Cache-Control": "no-cache, must-revalidate"})


def _message_page(text, status):
    return _html(PAGE_SHELL.replace("__BODY__", '<p class="card">%s</p>' % html.escape(text)), status)


def _login_page(site_label, error="", status=200):
    form = LOGIN_FORM.replace("__SITE__", html.escape(site_label)).replace("__ERROR__", html.escape(error))
    return _html(PAGE_SHELL.replace("__BODY__", form), status)


def _inline_json(value):
    """JSON that cannot end or derail the inline script it is written into: no "<" (so no "</script>"
    and no "<!--") and no raw U+2028 / U+2029."""
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _screen(config, viewer):
    """The screen file, with this site's configuration and the viewer's role written in at the marker."""
    with open(os.environ.get("SH_SCREEN") or DEFAULT_SCREEN, encoding="utf-8") as f:
        head, marker, tail = f.read().partition(MARKER)
    if not marker:
        raise RuntimeError("the screen file has no %s marker" % MARKER)
    script = "<script>window.SH_CONFIG=%s;window.SH_ROLE=%s;</script>" % (
        _inline_json(config), _inline_json(viewer.screen_role))
    return _html(head + script + tail)


async def _body(request, limit):
    """The request body, or b"" when it is longer than `limit` bytes; it is never buffered beyond that."""
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            return b""
    return data


# ---------------------------------------------------------------- the database and the site's configuration

# One small pool runs every database call. It gives /api/site its parallel parts, and it caps the number
# of Postgres connections, because db.py keeps one per thread.
_pool = ThreadPoolExecutor(max_workers=9, thread_name_prefix="sh-db")


async def rpc(fn, params=None):
    return await asyncio.get_running_loop().run_in_executor(_pool, db.rpc, fn, params)


def _now():
    return datetime.now(timezone.utc)


class Site(NamedTuple):
    tz: ZoneInfo        # the local dates of §5.1 are dates in this zone
    host: str           # without "www."
    screen: dict        # window.SH_CONFIG


_site_cache = {"at": 0.0, "site": None}


async def _site():
    """What sh_config() says about the site, re-read at most once a minute."""
    if _site_cache["site"] is None or time.monotonic() - _site_cache["at"] >= 60:
        config = await rpc("sh_config")
        try:
            site = Site(ZoneInfo(config["time_zone"]), _bare(config["host"]), config["screen"])
        except (KeyError, TypeError, ValueError) as e:
            raise db.DbError("the site is not configured (%s): load its configuration with sh_setup" % e) from None
        _site_cache.update(site=site, at=time.monotonic())
    return _site_cache["site"]


def _bare(host):
    return host.lower().removeprefix("www.")


def _midnight(day, tz, days=0):
    """00:00 of a local date (plus whole days) as an exact instant. The days are added on the local
    calendar: the day on which the clocks change is 23 or 25 hours long."""
    local = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=days)
    return local.replace(tzinfo=tz).astimezone(timezone.utc)


def window(tz, h=None, f=None, t=None):
    """The time window of a data call (§5.1): (from, to, hours), from and to as ISO 8601 in the site's zone."""
    now, start = _now(), None
    if f:
        try:
            start = _midnight(f, tz)
            end = _midnight(t, tz, days=1) if t else now
            if end <= start:
                end = _midnight(f, tz, days=1)
            hours = max(1, int((end - start).total_seconds() // 3600))
        except (ValueError, OverflowError):
            start = None                                     # invalid dates: fall back to h
    if start is None:
        try:
            hours = min(max(int(h), 1), 9600)
        except (TypeError, ValueError):
            hours = 24
        start, end = now - timedelta(hours=hours), now + timedelta(minutes=1)
    return start.astimezone(tz).isoformat(), end.astimezone(tz).isoformat(), hours


async def _window(request):
    q = request.query_params
    return window((await _site()).tz, q.get("h"), q.get("f"), q.get("t"))


def _strategy(request):
    return "desktop" if request.query_params.get("strategy") == "desktop" else "mobile"


def _alerts_for(viewer, rows):
    """A list of alerts as this viewer may see it (§8.2)."""
    if viewer.no_alerts:
        return []
    if not viewer.outsider or not isinstance(rows, list):    # a failed part stays {"error": ...}
        return rows
    return [row for row in rows if row.get("kind") in SITE_ALERT_KINDS]


# ---------------------------------------------------------------- the app and its gate

def _start_collectors():
    if os.environ.get("COLLECTORS", "1") == "0":
        log.info("collectors: off (COLLECTORS=0), this process measures nothing")
        return
    try:
        import collectors
        collectors.start()
        log.info("collectors: started")
    except Exception as e:                                   # the screen must come up without them
        log.error("collectors: NOT started, this process measures nothing (%s: %s)", type(e).__name__, e)


@asynccontextmanager
async def lifespan(app):
    accounts, first = _accounts(), {}
    if not accounts:
        log.warning("SH_PASS_OWNER is not set: nobody can sign in")
    for password, viewer in accounts:
        if first.setdefault(password, viewer) is not viewer:
            log.warning("%s and %s have the same password: both sign in as %s (%s)",
                        first[password].who, viewer.who, first[password].who, first[password].role)
    _start_collectors()
    yield


app = FastAPI(title="Site Health", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def gate(request: Request, call_next):
    response = await _admit(request, call_next)
    response.headers["X-Robots-Tag"] = "noindex"
    return response


async def _admit(request, call_next):
    """Every rule that depends on the path and the method (§8.2). The handlers only filter what they return."""
    path = request.url.path
    is_data = path.startswith("/api/")
    if path in OPEN_PATHS:
        return await call_next(request)
    viewer = request.state.viewer = _viewer(request)
    if viewer is None:
        if path == "/status":
            return _message_page(TEXT_BAD_LINK, 403)
        return _json({"error": "auth"}, 401) if is_data else RedirectResponse("/login", status_code=303)
    if not viewer.outsider or (request.method == "GET" and path in OUTSIDER_PATHS):
        return await call_next(request)
    return _json({"error": "auth"}, 403) if is_data else RedirectResponse("/site", status_code=303)


@app.exception_handler(db.DbError)
async def database_failed(request: Request, error: db.DbError):
    log.warning("%s: %s", request.url.path, error)
    if request.url.path.startswith("/api/"):
        return _json({"error": str(error)}, 502)
    return _message_page(TEXT_NO_DATA, 502)


# ---------------------------------------------------------------- pages and sign-in

@app.get("/")
async def home():
    return RedirectResponse("/site", status_code=303)


@app.get("/site")
async def site_page(request: Request):
    return _screen((await _site()).screen, request.state.viewer)


@app.get("/status")
async def share_page(request: Request):
    config = dict((await _site()).screen, shareKey=request.query_params["k"])
    return _screen(config, request.state.viewer)


async def _site_label():
    try:
        return (await _site()).screen.get("siteLabel", "")
    except db.DbError:
        return ""                                            # signing in does not depend on the database


@app.get("/login")
async def login_page(request: Request):
    if _by_cookie(request):
        return RedirectResponse("/", status_code=303)
    return _login_page(await _site_label())


_failures = deque(maxlen=5000)       # (time, address) of failed sign-ins, oldest first; bounded on purpose


def _recent_failures(ip):
    now = time.monotonic()
    while _failures and now - _failures[0][0] >= FAILURE_WINDOW:
        _failures.popleft()
    return sum(1 for _, address in _failures if address == ip)


@app.post("/login")
async def login(request: Request):
    ip = _client_ip(request)
    if _recent_failures(ip) >= MAX_FAILURES:                 # the password is not even looked at
        return _login_page(await _site_label(), TEXT_BLOCKED, 429)
    form = urllib.parse.parse_qs((await _body(request, 4096)).decode("utf-8", "replace"))
    found = _by_password(form.get("p", [""])[0])
    try:
        await rpc("sh_login_log_add", {"p_ip": ip, "p_ok": found is not None, "p_who": found[0].who if found else "?",
                                       "p_ua": request.headers.get("user-agent", "")[:200]})
    except db.DbError as e:
        log.warning("sign-in not logged: %s", e)             # the log is a record, not a gate
    if found is None:
        _failures.append((time.monotonic(), ip))
        return _login_page(await _site_label(), TEXT_WRONG, 401)
    viewer, token = found
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE, token, max_age=86400 * (30 if viewer.role == "vendor" else 365),
                        httponly=True, secure=_is_https(request), samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    return response


# ---------------------------------------------------------------- data calls (§5)

@app.get("/api/site")
async def api_site(request: Request):
    p_from, p_to, hours = await _window(request)
    strategy = _strategy(request)
    span = {"p_from": p_from, "p_to": p_to}
    parts = {
        "availability": ("sh_availability", span),
        "availability_series": ("sh_availability_series", span),
        "speed": ("sh_speed", span),
        "speed_series": ("sh_speed_series", dict(span, p_strategy=strategy)),
        "alerts_open": ("sh_alerts_open", None),
        "alerts_recent": ("sh_alerts_range", span),
        "health": ("sh_health", None),
        "product_issues": ("sh_product_issues", None),
        "cert": ("sh_cert", None),
    }

    async def part(key, fn, params):
        try:
            value = await rpc(fn, params)
        except Exception as e:                               # each part fails alone, whatever the failure (§5.2)
            log.warning("/api/site: %s failed: %s", key, e)
            return {"error": str(e)}
        return value if key == "cert" else value or []

    values = await asyncio.gather(*(part(key, fn, params) for key, (fn, params) in parts.items()))
    out = {"hours": hours, "from": p_from, "to": p_to, "strategy": strategy, **dict(zip(parts, values))}
    for key in ("alerts_open", "alerts_recent"):
        out[key] = _alerts_for(request.state.viewer, out[key])
    return _json(out)


@app.get("/api/site/now")
async def api_now(request: Request):
    viewer = request.state.viewer
    now = await rpc("sh_now")
    if viewer.outsider:                                      # the count must match the lists this viewer gets
        visible = [] if viewer.no_alerts else _alerts_for(viewer, await rpc("sh_alerts_open") or [])
        now["alerts_open"] = len(visible)
    return _json(now)


@app.get("/api/site/drill")
async def api_drill(request: Request):
    viewer, q = request.state.viewer, request.query_params
    what, bucket = q.get("what"), q.get("bucket") or None
    if what == "fails":
        p_from, p_to, _ = await _window(request)
        rows = await rpc("sh_drill_fails", {"p_from": p_from, "p_to": p_to, "p_page": q.get("page") or None,
                                            "p_bucket": bucket})
    elif what == "bucket":
        rows = await rpc("sh_drill_bucket", {"p_bucket": bucket})
    elif what == "runs":
        p_from, p_to, _ = await _window(request)
        rows = await rpc("sh_drill_runs", {"p_from": p_from, "p_to": p_to, "p_url": q.get("url"),
                                           "p_strategy": _strategy(request), "p_bucket": bucket})
    elif what == "alert":
        alert_id, rows = q.get("id", ""), []
        if alert_id.isascii() and alert_id.isdigit() and not viewer.no_alerts:
            rows = _alerts_for(viewer, await rpc("sh_drill_alert", {"p_id": int(alert_id)}) or [])
        if viewer.outsider:
            rows = [dict(row, sent=[]) for row in rows]      # who was pushed is the owner's business
    else:
        return _json({"error": "what?"}, 400)
    return _json({"rows": rows or []})


@app.get("/api/messages")
async def api_messages(request: Request):
    p_from, p_to, _ = await _window(request)
    return _json({"rows": await rpc("sh_messages", {"p_from": p_from, "p_to": p_to}) or []})


@app.post("/api/alerts/ack")
async def api_ack(request: Request):
    try:
        body = json.loads(await _body(request, 16384))
        listed = body["ids"] if isinstance(body.get("ids"), list) else [body.get("id")]
    except (ValueError, AttributeError):
        listed = []
    ids = []
    for item in listed[:200]:
        if isinstance(item, str) and item.isascii() and item.isdigit():
            item = int(item)                                 # the screen sends ids as it read them from the page
        if type(item) is int and item > 0 and item not in ids:
            ids.append(item)
    if not ids:
        return _json({"error": "bad request"}, 400)
    marked = await rpc("sh_alert_ack", {"p_ids": ids, "p_who": request.state.viewer.who})
    return _json({"ok": True, "n": marked["n"]})


# ---------------------------------------------------------------- real-user beacons (§7.7)

_rum_minute = {"minute": None, "seen": {}}       # beacons per address in the current minute; memory only
_rum_queue = []                                  # rows on their way to the database
_rum_busy = False


def _rum_within_rate(ip):
    minute = int(time.monotonic() // 60)
    if _rum_minute["minute"] != minute:
        _rum_minute.update(minute=minute, seen={})
    seen = _rum_minute["seen"]
    seen[ip] = seen.get(ip, 0) + 1
    return seen[ip] <= RUM_PER_MINUTE


async def _rum_row(request):
    """The row to store for one beacon, or None to drop it. Nothing about the visitor is kept:
    no address, no cookie, no user agent, no query string."""
    if not _rum_within_rate(_client_ip(request)):
        return None
    source = urllib.parse.urlsplit(request.headers.get("origin") or request.headers.get("referer") or "").hostname
    try:
        if not source or _bare(source) != (await _site()).host:
            return None
        beacon = json.loads(await _body(request, RUM_MAX_BYTES))
    except (db.DbError, ValueError):
        return None
    if not isinstance(beacon, dict):
        return None
    site, path, lcp = beacon.get("site"), beacon.get("path"), beacon.get("lcp")
    if not (isinstance(site, str) and RUM_SITE.fullmatch(site) and isinstance(path, str) and path.startswith("/")):
        return None
    path = re.split("[?#]", path, maxsplit=1)[0]
    if RUM_PRIVATE.intersection(path.lower().split("/")):
        return None
    if type(lcp) not in (int, float) or not 1 <= lcp <= 60000:      # a view without a measurement is not a row
        return None
    return {"site": site, "path": path, "lcp_ms": round(lcp), "is_test": beacon.get("test") is True}


async def _rum_store(row):
    """Hands rows over in small batches, one database call at a time: a burst of beacons or a slow
    database must not take the workers the screen needs. Beyond RUM_QUEUE waiting rows, new ones are dropped."""
    global _rum_busy
    if len(_rum_queue) < RUM_QUEUE:
        _rum_queue.append(row)
    if _rum_busy:
        return
    _rum_busy = True
    try:
        while _rum_queue:
            batch = _rum_queue[:RUM_BATCH]
            del _rum_queue[:RUM_BATCH]
            try:
                await rpc("sh_rum_add", {"p_rows": batch})
            except db.DbError as e:
                log.warning("%d real-user rows lost: %s", len(batch), e)
    finally:
        _rum_busy = False


@app.post("/rum")
async def rum(request: Request):
    row = await _rum_row(request)
    # Always 204, also for a dropped beacon. The row is stored after the answer has gone out.
    return Response(status_code=204, background=BackgroundTask(_rum_store, row) if row else None)


# ---------------------------------------------------------------- /health (§7.10)

@app.get("/health")
async def health():
    """Always 200. A host restarts a service whose health check fails, and restarting this server
    does not repair a database."""
    state, age = "ok", None
    try:
        await rpc("sh_ping")
        last = next((flow.get("last_at") for flow in await rpc("sh_health") or []
                     if flow.get("flow_name") == PROBE_FLOW), None)
        if last:
            age = int((_now() - datetime.fromisoformat(last)).total_seconds())
    except Exception as e:
        state = str(e) or type(e).__name__
    return _json({"ok": state == "ok", "db": state, "last_probe_age_sec": age})
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/site_health.config.example.json sha256=32391a8b4a5113440d0b5cb209677227c5fed4537da28b1b718667de0dc721a8 -->
~~~~~~~~json
{
  "site": "https://example.co.il",
  "label": "example.co.il",
  "brand": "",
  "time_zone": "Asia/Jerusalem",
  "platform": "woocommerce",
  "down_after": 1,
  "morning": "07:30",
  "pages": [
    {"name": "בית", "url": "https://example.co.il/", "home": true, "probe": true, "core": true},
    {"name": "קטגוריה", "url": "https://example.co.il/product-category/sofas/", "probe": true, "core": true},
    {"name": "מוצר", "url": "https://example.co.il/product/sample-sofa/", "probe": true, "core": true, "expect": "הוספה לסל"},
    {"name": "סל", "url": "https://example.co.il/cart/", "probe": true, "core": true},
    {"name": "קופה", "url": "https://example.co.il/checkout/", "core": true}
  ],
  "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
  "bucket_note": "",
  "live_hosts": ["live"]
}
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/rum/site-health-rum.js sha256=b9d8eced011b36c1d5874a513f3345babb0646c28b1aa4666bd0278ea2cd3eac -->
~~~~~~~~javascript
/* Site Health RUM: one anonymous beacon per page view (LCP + TTFB). No cookies, no ids, no query strings.
   Configure BEFORE this script: window.SiteHealthRum = { endpoint: 'https://collector.example.com/m', liveHost: 'example.com' };
   Optional: sample (0..1, default 1), skip (RegExp of paths never measured). Add ?sh_test=1 to a URL to flag a test row. */
(function () {
  var cfg = window.SiteHealthRum || {};
  if (!cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
  if ((PerformanceObserver.supportedEntryTypes || []).indexOf('largest-contentful-paint') < 0) return; // Safari < 26.2, Firefox < 122
  var skip = cfg.skip || /\/(checkout|cart|my-account|account|orders?|order-received|wp-admin|wp-login\.php)(\/|$)/i;
  if (skip.test(location.pathname)) return;
  if (Math.random() >= (cfg.sample == null ? 1 : +cfg.sample)) return;          // sampling decided once per page view

  function start() {
    if (document.visibilityState === 'hidden') return;                          // loaded in a background tab: LCP is meaningless
    var nav = (performance.getEntriesByType('navigation') || [])[0] || {};
    var act = nav.activationStart || 0;                                         // prerendered page: measure from activation
    var lcp = -1, hiddenAt = Infinity, sent = false;
    function take(list) {
      var e = list[list.length - 1];                                            // the last candidate is the LCP
      if (e && e.startTime < hiddenAt) lcp = Math.max(e.startTime - act, 0);    // ignore paints after the page was hidden
    }
    var po = new PerformanceObserver(function (l) { take(l.getEntries()); });
    try { po.observe({ type: 'largest-contentful-paint', buffered: true }); } catch (err) { return; }

    function send() {
      if (sent) return;
      take(po.takeRecords());
      if (lcp < 0) return;                                                      // nothing painted while visible: send nothing
      sent = true; po.disconnect();
      var host = location.hostname.replace(/^www\./, ''), live = String(cfg.liveHost || '').replace(/^www\./, '');
      var body = JSON.stringify({
        v: 1,
        site: host === live ? 'live' : location.hostname,                       // 'live' on production, the host name anywhere else
        path: location.pathname.slice(0, 300),                                  // never location.href / location.search
        lcp: Math.round(lcp),
        ttfb: nav.responseStart > 0 ? Math.round(Math.max(nav.responseStart - act, 0)) : null,
        nav: nav.type || null,                                                  // navigate | reload | back_forward | prerender
        test: /[?&]sh_test=1(&|$)/.test(location.search)
      });
      // A string body goes out as text/plain;charset=UTF-8 => "no-cors" request, no preflight, no CORS headers needed.
      if (!navigator.sendBeacon(cfg.endpoint, body)) {
        try { fetch(cfg.endpoint, { method: 'POST', body: body, keepalive: true, mode: 'no-cors', credentials: 'omit' }); } catch (err) {}
      }
    }
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') { hiddenAt = Math.min(hiddenAt, performance.now()); send(); }
    }, true);
    addEventListener('pagehide', send, true);                                   // fallback where visibilitychange does not fire
  }
  if (document.prerendering) document.addEventListener('prerenderingchange', start, { once: true }); else start();
})();
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/rum/site-health-rum.php sha256=3be175709953cae5428ae51eefea7431f63013a671b04c2b487bdc985d595a23 -->
~~~~~~~~php
<?php
/**
 * Plugin Name: Site Health RUM
 * Description: Sends one anonymous speed measurement per page view (time until the main content is painted) to the site-health dashboard. No cookies, no personal data.
 * Version: 1.1.0
 *
 * Install: copy this ONE file to wp-content/mu-plugins/ (always on) or to wp-content/plugins/ and activate it.
 * Then add to wp-config.php:
 *   define('SITE_HEALTH_RUM_ENDPOINT', 'https://collector.example.com/m');
 *   define('SITE_HEALTH_RUM_LIVE_HOST', 'example.com');   // production host, without www
 * and purge the page cache / CDN so cached pages pick the script up.
 */
if (!defined('ABSPATH')) { exit; }

if (!defined('SITE_HEALTH_RUM_ENDPOINT'))  { define('SITE_HEALTH_RUM_ENDPOINT', ''); }
if (!defined('SITE_HEALTH_RUM_LIVE_HOST')) { define('SITE_HEALTH_RUM_LIVE_HOST', ''); }
if (!defined('SITE_HEALTH_RUM_SAMPLE'))    { define('SITE_HEALTH_RUM_SAMPLE', 1); }   // 1 = every page view, 0.25 = one in four

function site_health_rum_should_run() {
    if (!SITE_HEALTH_RUM_ENDPOINT) { return false; }                                          // not configured yet
    if (is_admin() || is_preview() || is_customize_preview()) { return false; }
    if (is_user_logged_in() && current_user_can('edit_posts')) { return false; }             // staff are not visitors
    if (function_exists('is_checkout') && (is_checkout() || is_cart() || is_account_page())) { return false; }   // WooCommerce: never on cart / checkout / account
    return true;
}

add_action('wp_footer', function () {
    if (!site_health_rum_should_run()) { return; }
    $cfg = wp_json_encode(array(
        'endpoint' => SITE_HEALTH_RUM_ENDPOINT,
        'liveHost' => SITE_HEALTH_RUM_LIVE_HOST,
        'sample'   => (float) SITE_HEALTH_RUM_SAMPLE,
    ));
    $js = <<<'JS'
(function () {
var cfg = window.SiteHealthRum || {};
if (!cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
if ((PerformanceObserver.supportedEntryTypes || []).indexOf('largest-contentful-paint') < 0) return; // Safari < 26.2, Firefox < 122
var skip = cfg.skip || /\/(checkout|cart|my-account|account|orders?|order-received|wp-admin|wp-login\.php)(\/|$)/i;
if (skip.test(location.pathname)) return;
if (Math.random() >= (cfg.sample == null ? 1 : +cfg.sample)) return;
function start() {
if (document.visibilityState === 'hidden') return;
var nav = (performance.getEntriesByType('navigation') || [])[0] || {};
var act = nav.activationStart || 0;
var lcp = -1, hiddenAt = Infinity, sent = false;
function take(list) {
var e = list[list.length - 1];
if (e && e.startTime < hiddenAt) lcp = Math.max(e.startTime - act, 0);
}
var po = new PerformanceObserver(function (l) { take(l.getEntries()); });
try { po.observe({ type: 'largest-contentful-paint', buffered: true }); } catch (err) { return; }
function send() {
if (sent) return;
take(po.takeRecords());
if (lcp < 0) return;
sent = true; po.disconnect();
var host = location.hostname.replace(/^www\./, ''), live = String(cfg.liveHost || '').replace(/^www\./, '');
var body = JSON.stringify({
v: 1,
site: host === live ? 'live' : location.hostname,
path: location.pathname.slice(0, 300),
lcp: Math.round(lcp),
ttfb: nav.responseStart > 0 ? Math.round(Math.max(nav.responseStart - act, 0)) : null,
nav: nav.type || null,
test: /[?&]sh_test=1(&|$)/.test(location.search)
});
if (!navigator.sendBeacon(cfg.endpoint, body)) {
try { fetch(cfg.endpoint, { method: 'POST', body: body, keepalive: true, mode: 'no-cors', credentials: 'omit' }); } catch (err) {}
}
}
document.addEventListener('visibilitychange', function () {
if (document.visibilityState === 'hidden') { hiddenAt = Math.min(hiddenAt, performance.now()); send(); }
}, true);
addEventListener('pagehide', send, true);
}
if (document.prerendering) document.addEventListener('prerenderingchange', start, { once: true }); else start();
})();
JS;
    // data-no-optimize / data-cfasync ask LiteSpeed Cache and Cloudflare Rocket Loader to leave the script alone.
    wp_print_inline_script_tag('window.SiteHealthRum=' . $cfg . ';' . $js,
        array('id' => 'site-health-rum', 'data-no-optimize' => '1', 'data-cfasync' => 'false'));
}, 99);
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/tests/conftest.py sha256=0a7b07642e0b35ea1937743219420883cb4e0f0673a0bc4f47edaeb3ebea8f3c -->
~~~~~~~~python
"""Fixtures for the SQL tests: a scratch database with schema.sql and functions.sql applied.

The admin connection comes from SH_TEST_ADMIN_URL (default: the local server). The scratch
database gets a random name and is dropped at the end; no other database is touched.
"""
import datetime as dt
import json
import os
import pathlib
import secrets

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

REFERENCE = pathlib.Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("SH_TEST_ADMIN_URL", "postgresql://postgres:shtest@127.0.0.1:5432/postgres")
TIMINGS = []          # (label, seconds), filled by the performance test and printed in the summary


def apply_sql(conn):
    """schema.sql, then functions.sql, each sent as one command of many statements."""
    for name in ("schema.sql", "functions.sql"):
        conn.execute((REFERENCE / name).read_text(encoding="utf-8"))


def empty(conn):
    """Delete every row of every sh_* table."""
    tables = conn.execute(r"select format('%I', tablename) from pg_tables"
                          r" where schemaname = 'public' and tablename like 'sh\_%'"
                          r" order by tablename = 'sh_alerts'").fetchall()      # last: sh_messages points at it
    for (table,) in tables:
        conn.execute("delete from " + table)


def example_config(**changes):
    config = json.loads((REFERENCE / "site_health.config.example.json").read_text(encoding="utf-8"))
    config.update(changes)
    return config


PAGES = example_config()["pages"]


class Db:
    """One connection to the scratch database."""

    def __init__(self, conn):
        self.conn = conn

    def rpc(self, fn, **params):
        """Call one sh_* function with named parameters and return its JSON, parsed.
        Lists and dicts go as jsonb; times may be datetimes or ISO 8601 strings."""
        sql = "select %s(%s)" % (fn, ", ".join(name + " => %s" for name in params))
        values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params.values()]
        return self.conn.execute(sql, values).fetchone()[0]

    def sql(self, query, params=None):
        """Plain SQL, for test data the write functions cannot produce (rows in the past)."""
        cur = self.conn.execute(query, params)
        return cur.fetchall() if cur.description else None

    def now(self):
        """The database's now(), in UTC so that "90 days earlier" is exact whatever the session's
        time zone. Inside the `db` fixture it stands still for the whole test."""
        return self.sql("select now()")[0][0].astimezone(dt.timezone.utc)

    def setup(self, **changes):
        """Load the example configuration, with top-level keys replaced by `changes`."""
        return self.rpc("sh_setup", p_config=example_config(**changes))

    # Test data, through the write functions. Every moment is given by the caller (a fixed
    # date, or an offset from self.now()), so nothing depends on when the test happens to run.

    def probe(self, at, kind="full", fail=None, ms=300):
        """Store one round of the example configuration's probe pages.
        fail: {page: an HTTP status, or a fail code}. ms: one value, or {page: value} (default 300)."""
        rows = []
        for page in PAGES:
            if not page.get("probe"):
                continue
            why = (fail or {}).get(page["name"])
            row = {"page": page["name"], "url": page["url"], "ok": why is None, "status": 200, "fail": None,
                   "err": None, "ms": ms.get(page["name"], 300) if isinstance(ms, dict) else ms}
            if isinstance(why, int):
                row.update(status=why, fail="http")
            elif why:
                row.update(status=None, fail=why)
            rows.append(row)
        return self.rpc("sh_probe_add", p_round_at=at, p_kind=kind, p_rows=rows)

    def run(self, at, page="בית", lcp=2400, strategy="mobile", source="core", **more):
        """Store one lab run. `page` is the name of a configured page, or the address of any
        other page (a rotation run). lcp None stores a failed run."""
        urls = {p["name"]: p["url"] for p in PAGES}
        return self.rpc("sh_speed_add", p_rows=[{
            "at": at.isoformat(), "url": urls.get(page, page), "page": page if page in urls else None,
            "strategy": strategy, "source": source, "ok": lcp is not None, "lcp_ms": lcp, **more}])

    def ran(self, flow, **ago):
        """Say that a flow's last successful run was this long ago (timedelta arguments)."""
        self.sql("update sh_flows set last_at = now() - %s where flow_name = %s", [dt.timedelta(**ago), flow])


@pytest.fixture(scope="session")
def database():
    """The connection string of a fresh scratch database."""
    name = "sh_test_" + secrets.token_hex(6)
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute('create database "%s"' % name)
    url = make_conninfo(ADMIN_URL, dbname=name)
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            apply_sql(conn)
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute('drop database if exists "%s" with (force)' % name)


@pytest.fixture
def db(database):
    """A Db inside one transaction that is rolled back at the end.

    Every test starts with empty tables, and now() is the same instant for the whole test:
    a row written "ten minutes ago" is exactly ten minutes old when the test reads it back.
    """
    conn = psycopg.connect(database)
    try:
        empty(conn)               # also what another test committed; the rollback gives it back
        yield Db(conn)
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def committed(database):
    """A factory of Db objects that commit, for tests that need several sessions at once.
    The tables are emptied before and after."""
    conns = [psycopg.connect(database, autocommit=True)]
    empty(conns[0])

    def connect():
        conns.append(psycopg.connect(database, autocommit=True))
        return Db(conns[-1])

    try:
        yield connect
    finally:
        empty(conns[0])
        for conn in conns:
            conn.close()


def pytest_terminal_summary(terminalreporter):
    if TIMINGS:
        terminalreporter.write_sep("-", "read functions over 90 days of history")
        for label, seconds in TIMINGS:
            terminalreporter.write_line("%-58s %6.0f ms" % (label, seconds * 1000))
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/tests/sim.py sha256=0226390c5945f267230039e2df58c924341619fc281a789b095417f757de5ad4 -->
~~~~~~~~python
"""A small data simulator: fills a database with believable measurements, through the write
functions the collectors use (sh_probe_add, sh_speed_add, sh_sitemap_set, sh_rotation_next, ...).

`rpc` is any callable rpc(fn, **params) that runs one sh_* function and returns its JSON
(in the SQL tests: Db.rpc). Times are sent as ISO 8601 strings, so the same calls work over HTTPS.
Everything is deterministic: the same arguments always store the same rows.
"""
import datetime as dt
import zlib

MINUTE = dt.timedelta(minutes=1)
RESPONSE_MS = [240, 620, 300, 540]             # typical server response per probe page
LCP_MS = [2300, 3300, 2800, 2100, 2500]        # typical phone LCP per core page
OPPS = [{"id": "uses-responsive-images", "title": "Properly size images", "ms": 900},
        {"id": "render-blocking-resources", "title": "Eliminate render-blocking resources", "ms": 400}]


def simulate(rpc, start, days, *, fail_hour=None, dead=None, slow=None, light=True, site_pages=40):
    """Store `days` days of measurements, beginning at `start` (an aware datetime, on a full minute).

    Every minute a full probe round (and, with `light`, a light round at the half minute); every
    15 minutes a phone run of each core page, every hour a desktop run; every 5 minutes two pages
    of the whole-site rotation. The scenario knobs:

      fail_hour = (page, hour_start, n)   n full-round checks of that page, spread over the hour
                                          that begins at hour_start, fail with HTTP 502
      dead      = (begin, minutes)        no page answers for that many minutes (an outage)
      slow      = (page, begin, runs)     that many phone runs in a row of that core page, from
                                          `begin` on, take more than 5 seconds

    Returns {"probe": [...], "speed": [...]}: the rows as they were sent, with "round_at" / "at"
    as datetimes, so a caller can work out by itself what the read functions must answer.
    """
    config = rpc("sh_config")
    probe = [p for p in config["pages"] if p["probe"]]
    core = [p for p in config["pages"] if p["core"]]
    rpc("sh_sitemap_set", p_urls=["%s/product/item-%d/" % (config["site"], i + 1) for i in range(site_pages)])
    failing = set()
    if fail_hour:
        page, hour_start, n = fail_hour
        failing = {(page, hour_start + k * (60 // n) * MINUTE) for k in range(n)}
    stored = {"probe": [], "speed": []}

    for minute in range(days * 1440):
        at = start + minute * MINUTE
        rounds = [("full", at), ("light", at + dt.timedelta(seconds=30))]
        for kind, round_at in rounds if light else rounds[:1]:
            down = dead is not None and dead[0] <= round_at < dead[0] + dead[1] * MINUTE
            rows = [_check(p, i, minute, kind, down, (p["name"], round_at) in failing) for i, p in enumerate(probe)]
            rpc("sh_probe_add", p_round_at=round_at.isoformat(), p_kind=kind, p_rows=rows)
            stored["probe"] += [dict(r, round_at=round_at, kind=kind) for r in rows]

        runs = []
        if minute % 15 == 0:
            for i, p in enumerate(core):
                nth = (at - slow[1]) // (15 * MINUTE) if slow and p["name"] == slow[0] else -1
                lcp = 5200 + 100 * nth if 0 <= nth < slow[2] else LCP_MS[i % 5] + (minute * 53 + i * 17) % 400
                failed = minute % 750 == 0 and i == 1          # a lab run fails now and then
                runs.append(_run(p["url"], p["name"], "mobile", "core", None if failed else lcp, minute + i))
                if minute % 60 == 0:
                    runs.append(_run(p["url"], p["name"], "desktop", "core", int(lcp * 0.45), minute + i))
        if minute % 5 == 0:
            for url in rpc("sh_rotation_next", p_n=2):
                runs.append(_run(url, None, "mobile", "rotation", 1500 + zlib.crc32(url.encode()) % 6000, minute))
        if runs:
            rpc("sh_speed_add", p_rows=[dict(r, at=at.isoformat()) for r in runs])
            stored["speed"] += [dict(r, at=at) for r in runs]
    return stored


def snapshot(rpc, day, cert_days=23):
    """Store the once-a-day measurements for `day` (a date): the certificate, the catalogue's
    broken products, and a handful of real-user page views (40 live, 2 from a staging copy, 1 test)."""
    config = rpc("sh_config")
    noon = dt.datetime.combine(day, dt.time(12), dt.timezone.utc)
    rpc("sh_cert_set", p_row={
        "host": config["host"], "issuer": "Let's Encrypt R11", "ok": True, "err": None, "days_left": cert_days,
        "not_before": (noon - dt.timedelta(days=90 - cert_days)).isoformat(),
        "not_after": (noon + dt.timedelta(days=cert_days)).isoformat()})
    product = config["site"] + "/product/%s/"
    rpc("sh_issues_set", p_snap_date=day.isoformat(), p_rows=[
        {"product_id": "101", "issue": "בלי מחיר", "name": "שולחן אוכל נפתח 160", "url": product % "table-160"},
        {"product_id": "102", "issue": "בלי תמונה", "name": "כורסת טלוויזיה אפורה", "url": product % "armchair-grey"},
        {"product_id": "103", "issue": "לא במלאי", "name": "ספה תלת מושבית", "url": product % "sofa-3"},
        {"product_id": "104", "issue": "אי אפשר להוסיף לסל", "name": "שידת לילה אלון", "url": product % "nightstand-oak"}])
    rpc("sh_rum_add", p_rows=(
        [{"site": "live", "path": "/product/item-%d/" % (k % 7), "lcp_ms": 1200 + (k * 137) % 3000, "is_test": False}
         for k in range(40)]
        + [{"site": "staging." + config["host"], "path": "/", "lcp_ms": 2000 + k, "is_test": False} for k in range(2)]
        + [{"site": "live", "path": "/", "lcp_ms": 1500, "is_test": True}]))


def _check(page, i, minute, kind, down, fails):
    """One row of a probe round, in the shape sh_probe_add takes."""
    row = {"page": page["name"], "url": page["url"], "ok": True, "status": 200, "fail": None, "err": None,
           "ms": RESPONSE_MS[i % 4] + (minute * 37 + i * 101) % 200}
    if down:
        row.update(ok=False, status=None, fail="timeout", err="timed out", ms=10000)
    elif fails:
        row.update(ok=False, status=502, fail="http", ms=800)
    if kind == "light":
        row["ms"] = None        # a light round records only whether the page answered
    return row


def _run(url, page, strategy, source, lcp, salt):
    """One lab run, in the shape sh_speed_add takes. lcp None = the run failed."""
    run = {"url": url, "page": page, "strategy": strategy, "source": source, "ok": lcp is not None,
           "err": None if lcp is not None else "Lighthouse returned error: NO_FCP"}
    if lcp is not None:
        run.update(lcp_ms=lcp, score=max(18, min(99, 118 - lcp // 45)), cls=round(0.02 + (salt % 5) * 0.02, 3),
                   ttfb_ms=300 + (salt * 29) % 300, bytes=3000000 + (salt % 8) * 250000,
                   crux_category="FAST" if lcp <= 3125 else "AVERAGE" if lcp <= 5000 else "SLOW",
                   crux_lcp_ms=int(lcp * 0.8), opps=OPPS)
    return run
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/tests/test_rum_snippet.js sha256=e4b9c42e39296c9e3d84ebc75a760977651132ad79ff5c3273475dc95bf1000b -->
~~~~~~~~javascript
#!/usr/bin/env node
/* Test of the real-user script (rum/site-health-rum.js) in a real browser (Playwright, headless Chromium).

     node tests/test_rum_snippet.js

   A tiny local site serves pages that include the script; a local collector records what
   arrives. Exit code 0 = every check passed. */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const SNIPPET = fs.readFileSync(path.join(__dirname, '..', 'rum', 'site-health-rum.js'), 'utf8');
const PORT = 8801;
const beacons = [];
let failed = 0;
function check(name, cond, extra) { if (!cond) failed++; console.log((cond ? 'ok    ' : 'FAIL  ') + name + (!cond && extra ? '  → ' + extra : '')); }

const server = http.createServer((req, res) => {
  if (req.url === '/m') {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => { beacons.push({ method: req.method, type: req.headers['content-type'], origin: req.headers.origin, body }); res.writeHead(204); res.end(); });
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end('<!doctype html><html><body><h1 style="font-size:60px">התוכן הראשי של העמוד</h1><a id="next" href="/other">הלאה</a>'
    + '<script>window.SiteHealthRum={endpoint:"http://127.0.0.1:' + PORT + '/m",liveHost:"localhost"};</script>'
    + '<script>' + SNIPPET + '</script></body></html>');
});

server.listen(PORT, async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext()).newPage();
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  // 1. a page on the live host, left by clicking a link
  await page.goto('http://localhost:' + PORT + '/product/abc/?utm_source=x&email=a@b.co');
  await wait(600);
  await page.click('#next');
  await wait(600);
  // 2. a private page: nothing may be sent
  await page.goto('http://127.0.0.1:' + PORT + '/cart/');
  await wait(400);
  // 3. a page on another host name (stands for a staging copy), flagged as a test, left by closing the tab
  await page.goto('http://127.0.0.1:' + PORT + '/category/sofas/?sh_test=1');
  await wait(600);
  await page.close();
  await wait(600);

  const rows = beacons.map((b) => JSON.parse(b.body));
  const first = rows[0] || {};
  check('a beacon is sent when the visitor leaves the page', rows.length >= 2, JSON.stringify(rows));
  check('it is a POST with a text/plain body (no CORS preflight)', beacons.every((b) => b.method === 'POST' && /^text\/plain/.test(b.type || '')));
  check('the production host is reported as "live"', first.site === 'live', first.site);
  check('the path is sent without query string', first.path === '/product/abc/' && beacons.every((b) => !/utm_source|email/.test(b.body)), first.path);
  check('LCP is a positive number of milliseconds', Number.isInteger(first.lcp) && first.lcp > 0, String(first.lcp));
  check('an ordinary view is not flagged as a test', first.test === false);
  check('exactly one beacon per page view', rows.filter((r) => r.path === '/product/abc/').length === 1);
  check('nothing is sent from a cart page', !rows.some((r) => /cart/.test(r.path)));
  const staging = rows.find((r) => r.path === '/category/sofas/') || {};
  check('another host is reported by its name, not as "live"', staging.site === '127.0.0.1', staging.site);
  check('?sh_test=1 flags the measurement as a test', staging.test === true);

  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
});
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/tests/test_server.py sha256=d9a933aba5d1a38eca13f9c9875800b7648072692f20958d3e3f6af9ccbc4eee -->
~~~~~~~~python
"""Tests of server.py: access rules (SPEC.md §8), the data contract (§5), the page, /rum and /health.

No database is needed: db.rpc is replaced by a fake that records every call and answers with the
payloads of the kit's mock_server.py. The last section tests db.py itself: its HTTPS transport
against a stand-in for Supabase, and its Postgres transport when a scratch database can be made
(conftest.py; skipped otherwise).

    cd reference && python3 -m pytest -q tests/test_server.py
"""
import copy
import hmac
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import types
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REFERENCE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REFERENCE), str(REFERENCE.parent)]        # server.py and db.py; the kit's mock_server.py

import db  # noqa: E402
import mock_server  # noqa: E402
import server  # noqa: E402

REAL_RPC = db.rpc                                             # the tests of the server replace db.rpc
TOKEN = "share-token-9f3a"
PASSWORDS = {"owner": "Owner Pass-1", "staff": "staff-pass", "vendor": "dana-pass", "noalerts": "keren-pass"}
ENV = {"SH_PASS_OWNER": PASSWORDS["owner"], "SH_PASS_STAFF": PASSWORDS["staff"],
       "SH_PASS_VENDOR_DANA": PASSWORDS["vendor"], "SH_PASS_VENDOR_KEREN": PASSWORDS["noalerts"],
       "SH_VENDOR_NOALERTS": " keren ,someone-else", "SH_SHARE_TOKEN": TOKEN, "COLLECTORS": "0"}
ROLES = ("owner", "staff", "vendor", "noalerts", "share", None)             # None = nobody
SCREEN_ROLE = {"owner": {}, "staff": {}, "vendor": {"readonly": True},
               "noalerts": {"readonly": True, "noAlerts": True}, "share": {"share": True}}
# sh_config() after sh_setup of site_health.config.example.json (the page list is shortened)
SCREEN_CONFIG = {"hide": [], "brand": "", "homePage": "בית", "coreCount": 5, "liveHosts": ["live"],
                 "siteLabel": "example.co.il", "bucketNote": "", "probeCount": 4,
                 "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]}
CONFIG = {"host": "example.co.il", "site": "https://example.co.il", "brand": "", "label": "example.co.il",
          "pages": [{"url": "https://example.co.il/", "core": True, "home": True, "name": "בית", "probe": True,
                     "expect": None}],
          "screen": SCREEN_CONFIG, "morning": "07:30", "platform": "woocommerce", "time_zone": "Asia/Jerusalem",
          "down_after": 1, "live_hosts": ["live"], "bucket_note": "",
          "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]}
NOT_SET_UP = {"pages": [], "screen": {"hide": [], "coreCount": 0, "probeCount": 0}}       # sh_config() before sh_setup
NOW = datetime(2026, 11, 13, 8, 15, 30, tzinfo=timezone.utc)                # 10:15:30 in Jerusalem (UTC+2)
SITE_PARTS = {"availability": "sh_availability", "availability_series": "sh_availability_series",
              "speed": "sh_speed", "speed_series": "sh_speed_series", "alerts_open": "sh_alerts_open",
              "alerts_recent": "sh_alerts_range", "health": "sh_health", "product_issues": "sh_product_issues",
              "cert": "sh_cert"}
BEACON = {"site": "live", "path": "/product/sofa/", "lcp": 2345, "test": False}
ORIGIN = {"Origin": "https://example.co.il"}


class FakeDb:
    """Stands in for db.rpc: records (function, parameters) and answers like the SQL functions would.
    The answers are unfiltered, as a database's are; filtering by role is the server's job."""

    def __init__(self):
        self.calls, self.answered, self.failing, self.barrier, self.lock = [], {}, set(), None, threading.Lock()
        site = mock_server.api_site({"h": "168"}, "owner")
        self.answers = {fn: site[key] for key, fn in SITE_PARTS.items()}
        self.answers.update(sh_config=CONFIG, sh_now=mock_server.api_now("owner"), sh_ping="ok",
                            sh_messages=mock_server.api_messages({})["rows"], sh_login_log_add=None)

    def __call__(self, fn, params=None):
        with self.lock:
            self.calls.append((fn, params))
        if self.barrier and fn in SITE_PARTS.values():
            self.barrier.wait()                                # passes only when all nine wait at the same time
        if fn in self.failing:
            raise db.DbError("boom: " + fn)
        self.answered[fn] = self.answer(fn, params)
        return copy.deepcopy(self.answered[fn])                # the server may not change what the tests compare with

    def answer(self, fn, params):
        if fn in self.answers:
            return self.answers[fn]
        if fn == "sh_drill_alert":
            return mock_server.api_drill({"what": "alert", "id": str(params["p_id"])}, "owner")["rows"]
        if fn.startswith("sh_drill_"):
            return mock_server.api_drill({"what": fn[len("sh_drill_"):]}, "owner")["rows"]
        if fn == "sh_alert_ack":
            return {"n": len(params["p_ids"])}
        if fn == "sh_rum_add":
            return {"n": len(params["p_rows"])}
        raise AssertionError("the server called an unknown function: " + fn)

    def names(self):
        return [fn for fn, _ in self.calls]

    def params(self, fn):
        found = [params for name, params in self.calls if name == fn]
        assert len(found) == 1, "%s was called %d times" % (fn, len(found))
        return found[0]


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    for name in [name for name in os.environ if name.startswith("SH_")]:
        monkeypatch.delenv(name)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    fake = FakeDb()
    monkeypatch.setattr(db, "rpc", fake)
    monkeypatch.setattr(server, "_now", lambda: NOW)
    monkeypatch.setattr(server, "_site_cache", {"at": 0.0, "site": None})
    monkeypatch.setattr(server, "_rum_minute", {"minute": None, "seen": {}})
    monkeypatch.setattr(server, "_rum_busy", False)
    server._failures.clear()
    server._rum_queue.clear()
    return fake


@pytest.fixture
def clock(monkeypatch):
    """The server's monotonic clock, movable. Only server.time is replaced, not the event loop's clock."""
    clock = types.SimpleNamespace(t=1000.0)
    clock.monotonic = lambda: clock.t
    monkeypatch.setattr(server, "time", clock)
    return clock


def sign_in(client, password, **headers):
    return client.post("/login", data={"p": password}, headers=headers)


@pytest.fixture
def visit(fake):
    """visit(role) -> a client signed in as that role (no session for "share" and None)."""
    def visit(role=None, **options):
        client = TestClient(server.app, follow_redirects=False, **options)
        if role in PASSWORDS:
            assert sign_in(client, PASSWORDS[role]).status_code == 303
        fake.calls.clear()
        return client
    return visit


def send(visit, role, method, path, **options):
    """One request as `role`. The share link has no session: its token rides on every request."""
    path, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query), **options.pop("params", {}))
    if role == "share":
        params["k"] = TOKEN
    return visit(role).request(method, path, params=params, **options)


def cookie_of(response):
    """The session cookie a sign-in set, as (value, attributes in lower case)."""
    value, *attributes = response.headers["set-cookie"].split("; ")
    assert value.startswith(server.COOKIE + "=")
    return value.split("=", 1)[1], {a.lower() for a in attributes}


class Scripts(HTMLParser):
    """The text of every <script> element, as a browser's tokenizer would cut them."""

    def __init__(self, page):
        super().__init__()
        self.found, self.inside = [], False
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True
            self.found.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.found[-1] += data


def injected(page):
    """(SH_CONFIG, SH_ROLE) as written into the page, read back from its first script."""
    config, role = re.fullmatch(r"window\.SH_CONFIG=(.*);window\.SH_ROLE=(.*);", Scripts(page).found[0], re.S).groups()
    return json.loads(config), json.loads(role)


# ================================================================ routes and access (§8.2)

def test_the_app_exposes_exactly_the_specified_routes():
    routes = {(method, route.path) for route in server.app.routes for method in route.methods}
    assert routes == {("GET", "/"), ("GET", "/site"), ("GET", "/status"), ("GET", "/login"), ("POST", "/login"),
                      ("GET", "/logout"), ("GET", "/health"), ("GET", "/api/site"), ("GET", "/api/site/now"),
                      ("GET", "/api/site/drill"), ("GET", "/api/messages"), ("POST", "/api/alerts/ack"),
                      ("POST", "/rum")}


TO_LOGIN, TO_SITE = (303, "/login"), (303, "/site")
ACCESS = [
    # method, path, body                      owner+staff   vendors    share link  nobody
    ("GET", "/", None,                        TO_SITE,      TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("GET", "/site", None,                    200,          200,       TO_LOGIN,   TO_LOGIN),
    ("GET", "/status", None,                  403,          403,       200,        403),     # only the token counts
    ("GET", "/login", None,                   (303, "/"),   (303, "/"), 200,       200),
    ("GET", "/logout", None,                  TO_LOGIN,     TO_LOGIN,  TO_LOGIN,   TO_LOGIN),
    ("GET", "/health", None,                  200,          200,       200,        200),
    ("POST", "/rum", None,                    204,          204,       204,        204),
    ("GET", "/api/site", None,                200,          200,       200,        401),
    ("GET", "/api/site/now", None,            200,          200,       200,        401),
    ("GET", "/api/site/drill?what=fails", None, 200,        200,       200,        401),
    ("GET", "/api/messages", None,            200,          403,       401,        401),
    ("POST", "/api/alerts/ack", {"ids": [41]}, 200,         403,       401,        401),
    # POST is refused for outsiders even on the paths they may read
    ("POST", "/api/site", None,               405,          403,       403,        401),
    ("POST", "/api/site/now", None,           405,          403,       403,        401),
    ("POST", "/api/site/drill", None,         405,          403,       403,        401),
    ("POST", "/site", None,                   405,          TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("POST", "/status", None,                 403,          403,       TO_SITE,    403),
    ("DELETE", "/api/alerts/ack", None,       405,          403,       401,        401),
    # paths that are on no list
    ("GET", "/api/anything", None,            404,          403,       401,        401),
    ("GET", "/anything", None,                404,          TO_SITE,   TO_LOGIN,   TO_LOGIN),
    ("GET", "/site/", None,                   (307, "http://testserver/site"), TO_SITE, TO_LOGIN, TO_LOGIN),
]
COLUMN = {"owner": 3, "staff": 3, "vendor": 4, "noalerts": 4, "share": 5, None: 6}


@pytest.mark.parametrize("role", ROLES, ids=str)
@pytest.mark.parametrize("row", ACCESS, ids=lambda row: "%s %s" % row[:2])
def test_access(row, role, fake, visit):
    method, path, body = row[:3]
    expected = row[COLUMN[role]]
    response = send(visit, role, method, path, json=body)
    status, location = expected if isinstance(expected, tuple) else (expected, None)
    assert (response.status_code, response.headers.get("location")) == (status, location)
    assert response.headers["x-robots-tag"] == "noindex"
    if status in (401, 403) and path.startswith("/api/"):
        assert response.json() == {"error": "auth"}
        assert response.headers["cache-control"] == "no-store"
        assert fake.calls == []                                # refused before anything is read
    if status == 303:
        assert fake.calls == []


@pytest.fixture
def later_routes():
    """Two routes "added later" by somebody who forgot about roles."""
    before = list(server.app.router.routes)
    server.app.add_api_route("/api/later", lambda: {"secret": 1}, methods=["GET"])
    server.app.add_api_route("/later", lambda: {"secret": 1}, methods=["GET"])
    yield
    server.app.router.routes[:] = before


@pytest.mark.parametrize("role, data, page", [
    ("owner", 200, 200), ("staff", 200, 200), ("vendor", 403, 303), ("noalerts", 403, 303),
    ("share", 401, 303), (None, 401, 303)], ids=str)
def test_a_route_added_later_is_closed_to_outsiders(role, data, page, visit, later_routes):
    assert send(visit, role, "GET", "/api/later").status_code == data
    response = send(visit, role, "GET", "/later")
    assert response.status_code == page
    if page == 303:
        assert response.headers["location"] == ("/site" if role in ("vendor", "noalerts") else "/login")
        assert "secret" not in response.text


def test_a_refusal_has_the_shape_the_screen_expects(visit):
    nobody = visit(None).get("/api/site")
    assert (nobody.status_code, nobody.json()) == (401, {"error": "auth"})
    vendor = visit("vendor").get("/api/messages")
    assert (vendor.status_code, vendor.json()) == (403, {"error": "auth"})
    link = visit(None).get("/status", params={"k": "wrong"})
    assert link.status_code == 403 and server.TEXT_BAD_LINK in link.text and "\n" not in server.TEXT_BAD_LINK


# ---------------------------------------------------------------- what an outsider gets back

def ids(rows):
    return [row["id"] for row in rows]


def test_the_fixture_holds_what_the_filter_tests_need(fake):
    assert {row["kind"] for row in fake.answers["sh_alerts_open"]} == {"down", "slow", "ops"}
    assert ids(fake.answers["sh_alerts_open"]) == [41, 40, 39]
    assert ids(fake.answers["sh_alerts_range"]) == [41, 40, 39, 38, 37, 36]
    assert fake.answers["sh_now"]["alerts_open"] == 3


@pytest.mark.parametrize("role", ["owner", "staff"])
def test_insiders_get_every_alert(role, fake, visit):
    client = visit(role)
    site = client.get("/api/site", params={"h": 168}).json()
    assert site["alerts_open"] == fake.answers["sh_alerts_open"]
    assert site["alerts_recent"] == fake.answers["sh_alerts_range"]
    fake.calls.clear()
    assert client.get("/api/site/now").json() == fake.answers["sh_now"]
    assert fake.names() == ["sh_now"]
    row, = client.get("/api/site/drill", params={"what": "alert", "id": 39}).json()["rows"]      # an "ops" alert
    assert row["kind"] == "ops" and [push["event"] for push in row["sent"]] == ["open"]
    row, = client.get("/api/site/drill", params={"what": "alert", "id": 38}).json()["rows"]
    assert [push["event"] for push in row["sent"]] == ["open", "close"] and len(row["fails"]) == 3


@pytest.mark.parametrize("role", ["vendor", "share"])
def test_outsiders_get_only_the_four_site_kinds(role, fake, visit):
    site = send(visit, role, "GET", "/api/site", params={"h": 168}).json()
    assert ids(site["alerts_open"]) == [41, 40]
    assert site["alerts_open"] == [row for row in fake.answers["sh_alerts_open"] if row["kind"] != "ops"]
    assert ids(site["alerts_recent"]) == [41, 40, 38, 37, 36]
    assert {row["kind"] for row in site["alerts_recent"]} == {"down", "slow", "silent", "cert"}
    assert server.SITE_ALERT_KINDS == {"down", "slow", "silent", "cert"}
    for key, fn in SITE_PARTS.items():                         # nothing else is touched
        if not key.startswith("alerts_"):
            assert site[key] == fake.answers[fn]

    now = send(visit, role, "GET", "/api/site/now").json()
    assert now == dict(fake.answers["sh_now"], alerts_open=2)   # recounted after filtering
    assert fake.names() == ["sh_now", "sh_alerts_open"]
    assert send(visit, role, "GET", "/api/site/drill", params={"what": "alert", "id": 39}).json() == {"rows": []}
    row, = send(visit, role, "GET", "/api/site/drill", params={"what": "alert", "id": 38}).json()["rows"]
    assert row == dict(fake.answered["sh_drill_alert"][0], sent=[])         # who was pushed is the owner's business
    assert row["id"] == 38 and len(row["fails"]) == 3 and len(fake.answered["sh_drill_alert"][0]["sent"]) == 2


def test_a_vendor_without_alerts_gets_none(fake, visit):
    client = visit("noalerts")
    site = client.get("/api/site", params={"h": 168}).json()
    assert site["alerts_open"] == [] and site["alerts_recent"] == []
    assert site["availability"] == fake.answers["sh_availability"]
    fake.calls.clear()
    assert client.get("/api/site/now").json() == dict(fake.answers["sh_now"], alerts_open=0)
    assert client.get("/api/site/drill", params={"what": "alert", "id": 41}).json() == {"rows": []}
    assert fake.names() == ["sh_now"]                          # the alerts were not even read

    fake.failing.add("sh_alerts_open")                         # a failed part must not leak through as an error
    assert client.get("/api/site").json()["alerts_open"] == []


@pytest.mark.parametrize("role", ["vendor", "noalerts"])
def test_outsiders_cannot_read_the_push_log_or_mark_alerts(role, fake, visit):
    client = visit(role)
    assert client.get("/api/messages").status_code == 403
    assert client.post("/api/alerts/ack", json={"ids": [41]}).status_code == 403
    assert client.post("/api/alerts/ack", json={"id": 41}).status_code == 403
    assert fake.calls == []


def test_a_failed_recount_is_an_error_not_a_zero(fake, visit):
    fake.failing.add("sh_alerts_open")
    response = visit("vendor").get("/api/site/now")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_alerts_open"})


# ---------------------------------------------------------------- the share link

def test_the_share_page_is_served_for_the_right_token_only(visit):
    client = visit(None)
    page = client.get("/status", params={"k": TOKEN})
    assert page.status_code == 200 and "set-cookie" not in page.headers
    assert injected(page.text) == (dict(SCREEN_CONFIG, shareKey=TOKEN), {"share": True})
    for k in ("wrong", TOKEN + "x", TOKEN[:-1], TOKEN.upper(), ""):
        refused = client.get("/status", params={"k": k})
        assert refused.status_code == 403 and server.TEXT_BAD_LINK in refused.text and "SH_CONFIG" not in refused.text
    assert client.get("/status").status_code == 403


def test_the_share_token_opens_the_three_data_calls_and_nothing_else(fake, visit):
    client = visit(None)
    for path in ("/api/site", "/api/site/now", "/api/site/drill"):
        assert client.get(path, params={"what": "fails", "k": TOKEN}).status_code == 200
        assert client.get(path, params={"what": "fails", "k": "wrong"}).status_code == 401
        assert client.get(path, params={"what": "fails"}).status_code == 401
    fake.calls.clear()
    assert client.get("/api/messages", params={"k": TOKEN}).status_code == 401
    assert client.post("/api/alerts/ack", params={"k": TOKEN}, json={"ids": [41]}).status_code == 401
    assert client.get("/site", params={"k": TOKEN}).headers["location"] == "/login"
    assert client.get("/", params={"k": TOKEN}).headers["location"] == "/login"
    assert client.get("/login", params={"k": TOKEN}).status_code == 200          # not "already signed in"
    assert fake.calls == []                                    # nothing was read for any of them
    assert sign_in(client, TOKEN).status_code == 401           # and the token is not a password
    assert client.cookies.get(server.COOKIE) is None


def test_on_a_share_call_only_the_token_counts(visit):
    owner = visit("owner")
    assert owner.get("/status", params={"k": "wrong"}).status_code == 403
    assert owner.get("/api/site", params={"k": "wrong"}).status_code == 401
    shared = owner.get("/api/site", params={"k": TOKEN, "h": 168}).json()
    assert ids(shared["alerts_open"]) == [41, 40]              # what the link shows, not what the owner may see
    assert ids(owner.get("/api/site", params={"h": 168}).json()["alerts_open"]) == [41, 40, 39]
    assert owner.get("/api/messages", params={"k": "wrong"}).status_code == 200   # k is not read elsewhere


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_an_empty_share_token_switches_the_link_off(configured, monkeypatch, visit):
    monkeypatch.delenv("SH_SHARE_TOKEN")
    if configured is not None:
        monkeypatch.setenv("SH_SHARE_TOKEN", configured)
    client = visit(None)
    for k in ("", "   ", "anything", TOKEN):
        assert client.get("/status", params={"k": k}).status_code == 403
        assert client.get("/api/site", params={"k": k}).status_code == 401
    assert client.get("/status").status_code == 403


def test_secrets_are_compared_in_constant_time(monkeypatch, visit):
    seen, real = [], hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(server.hmac, "compare_digest", spy)
    client = visit(None)
    sign_in(client, "a guess")
    assert (b"a guess", b"owner pass-1") in seen and (b"a guess", b"dana-pass") in seen
    client.get("/site", headers={"Cookie": server.COOKIE + "=forged"})
    assert (b"forged", server._token("owner pass-1").encode()) in seen
    client.get("/status", params={"k": "a-guess"})
    client.get("/api/site", params={"k": "b-guess"})
    assert (b"a-guess", TOKEN.encode()) in seen and (b"b-guess", TOKEN.encode()) in seen

    # and nothing else decides: with that comparison answering "no", no secret opens anything
    owner = visit("owner")
    monkeypatch.setattr(server.hmac, "compare_digest", lambda a, b: False)
    assert sign_in(visit(None), PASSWORDS["owner"]).status_code == 401
    assert owner.get("/site").headers["location"] == "/login"
    assert owner.get("/api/site").status_code == 401
    assert owner.get("/status", params={"k": TOKEN}).status_code == 403
    assert owner.get("/api/site", params={"k": TOKEN}).status_code == 401


# ================================================================ sign-in and the session cookie

@pytest.mark.parametrize("role, max_age", [("owner", 365), ("staff", 365), ("vendor", 30), ("noalerts", 30)])
def test_the_cookie_attributes(role, max_age, visit):
    response = sign_in(visit(None), PASSWORDS[role])
    assert (response.status_code, response.headers["location"]) == (303, "/")
    value, attributes = cookie_of(response)
    assert re.fullmatch("[0-9a-f]{64}", value)
    assert attributes == {"httponly", "samesite=lax", "path=/", "max-age=%d" % (max_age * 86400)}    # http: no "secure"


def test_the_cookie_is_secure_on_https_only(visit):
    def attributes(client, **headers):
        return cookie_of(sign_in(client, PASSWORDS["owner"], **headers))[1]

    assert "secure" not in attributes(visit(None))
    assert "secure" in attributes(visit(None, base_url="https://testserver"))
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https"})            # behind the host's proxy
    assert "secure" in attributes(visit(None), **{"X-Forwarded-Proto": "https, http"})
    assert "secure" not in attributes(visit(None, base_url="https://testserver"), **{"X-Forwarded-Proto": "http"})


def test_changing_a_password_ends_the_session(monkeypatch, visit):
    owner, vendor = visit("owner"), visit("vendor")
    old = owner.cookies[server.COOKIE]
    assert owner.get("/site").status_code == 200 and vendor.get("/site").status_code == 200

    monkeypatch.setenv("SH_PASS_OWNER", "a new password")
    assert owner.get("/site").headers["location"] == "/login"
    assert owner.get("/api/site").status_code == 401
    assert sign_in(visit(None), PASSWORDS["owner"]).status_code == 401
    new = cookie_of(sign_in(visit(None), "a new password"))[0]
    assert new != old and new == server._token("a new password")

    monkeypatch.delenv("SH_PASS_VENDOR_DANA")                  # deleting it signs the person out at once
    assert vendor.get("/site").headers["location"] == "/login"
    assert vendor.get("/api/site").status_code == 401


@pytest.mark.parametrize("typed", ["Owner Pass-1", "owner pass-1", "OWNER PASS-1", "  Owner Pass-1 ",
                                   "\tOWNER pass-1\n"])
def test_passwords_match_trimmed_and_without_case(typed, monkeypatch, visit):
    monkeypatch.setenv("SH_PASS_OWNER", "  Owner Pass-1  ")
    response = sign_in(visit(None), typed)
    assert response.status_code == 303
    assert cookie_of(response)[0] == server._token("owner pass-1")       # one cookie however it was typed


@pytest.mark.parametrize("typed", ["", " ", "Owner Pass-1x", "OwnerPass-1", "Owner  Pass-1", "staff", TOKEN])
def test_a_wrong_password_is_refused(typed, visit):
    response = sign_in(visit(None), typed)
    assert response.status_code == 401 and server.TEXT_WRONG in response.text
    assert "set-cookie" not in response.headers


def test_unset_and_blank_passwords_never_match(monkeypatch, visit):
    monkeypatch.delenv("SH_PASS_STAFF")
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", "   ")
    monkeypatch.setenv("SH_PASS_VENDOR_", "no-name")           # a variable without a name is nobody
    assert [viewer.who for _, viewer in server._accounts()] == ["KEREN", "owner"]
    for typed in ("", "   ", "None", "no-name"):
        assert sign_in(visit(None), typed).status_code == 401
    for forged in (server._token(""), ""):                     # the digest an empty key would give; an empty cookie
        response = visit(None).get("/site", headers={"Cookie": "%s=%s" % (server.COOKIE, forged)})
        assert response.headers["location"] == "/login"


def test_without_an_owner_password_nobody_signs_in(monkeypatch, visit):
    staff = visit("staff")
    monkeypatch.delenv("SH_PASS_OWNER")
    assert server._accounts() == []
    assert staff.get("/site").headers["location"] == "/login"
    for role in ("staff", "vendor", "noalerts"):
        assert sign_in(visit(None), PASSWORDS[role]).status_code == 401


@pytest.mark.parametrize("env, typed, who, role, max_age", [
    ({"SH_PASS_VENDOR_DANA": " OWNER pass-1 "}, "Owner Pass-1", "DANA", "vendor", 30),
    ({"SH_PASS_STAFF": "owner PASS-1"}, "Owner Pass-1", "staff", "staff", 365),
    ({"SH_PASS_VENDOR_DANA": "staff-pass", "SH_PASS_OWNER": "STAFF-PASS"}, "staff-pass", "DANA", "vendor", 30),
    ({"SH_PASS_VENDOR_DANA": "keren-pass"}, "keren-pass", "KEREN", "vendor", 30),       # KEREN is the noAlerts one
    ({"SH_PASS_VENDOR_AARON": "keren-pass"}, "keren-pass", "KEREN", "vendor", 30),      # not the alphabet: the rights
])
def test_a_shared_password_resolves_to_the_least_privileged(env, typed, who, role, max_age, monkeypatch, fake, visit):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    client = visit(None)
    response = sign_in(client, typed)
    assert "max-age=%d" % (max_age * 86400) in cookie_of(response)[1]
    assert fake.params("sh_login_log_add")["p_who"] == who     # the log and the cookie name the same person
    assert server._by_cookie(types.SimpleNamespace(cookies=client.cookies)).who == who
    assert client.get("/api/messages").status_code == (200 if role == "staff" else 403)
    if who == "KEREN":
        assert injected(client.get("/site").text)[1] == {"readonly": True, "noAlerts": True}


def test_a_shared_password_is_reported_at_startup(monkeypatch, caplog):
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", PASSWORDS["owner"].upper())
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"), TestClient(server.app):
        pass
    assert [record.getMessage() for record in caplog.records] == [
        "DANA and owner have the same password: both sign in as DANA (vendor)"]


def test_every_attempt_is_logged(fake, visit):
    client = visit(None)
    headers = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1", "User-Agent": "Phone/1.0 " + "x" * 300}
    sign_in(client, "a guess", **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": False, "p_who": "?",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(client, PASSWORDS["vendor"], **headers)
    assert fake.params("sh_login_log_add") == {"p_ip": "203.0.113.9", "p_ok": True, "p_who": "DANA",
                                               "p_ua": ("Phone/1.0 " + "x" * 300)[:200]}
    fake.calls.clear()
    sign_in(visit(None), PASSWORDS["owner"])
    assert fake.params("sh_login_log_add") == {"p_ip": "testclient", "p_ok": True, "p_who": "owner",
                                               "p_ua": "testclient"}


def test_signing_in_works_while_the_database_is_down(fake, visit):
    fake.failing.update(["sh_login_log_add", "sh_config"])
    client = visit(None)
    assert client.get("/login").status_code == 200
    assert sign_in(client, "a guess").status_code == 401
    assert sign_in(client, PASSWORDS["owner"]).status_code == 303
    assert client.get("/").headers["location"] == "/site"


def test_eight_failures_block_an_address_for_ten_minutes(fake, clock, visit):
    client = visit(None)
    attacker, other = {"X-Forwarded-For": "198.51.100.7"}, {"X-Forwarded-For": "198.51.100.8"}
    for attempt in range(8):
        clock.t += 60                                          # 8 failures spread over 8 minutes
        assert sign_in(client, "guess %d" % attempt, **attacker).status_code == 401
    assert fake.names().count("sh_login_log_add") == 8
    fake.calls.clear()

    blocked = sign_in(client, PASSWORDS["owner"], **attacker)  # even the right password
    assert blocked.status_code == 429 and server.TEXT_BLOCKED in blocked.text and "set-cookie" not in blocked.headers
    assert "sh_login_log_add" not in fake.names()              # not examined, so not an attempt
    assert sign_in(visit(None), PASSWORDS["owner"], **other).status_code == 303          # another address is free

    clock.t += 179                                             # 9:59 after the first failure
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 429
    clock.t += 1                                               # the first failure is 10 minutes old
    assert sign_in(client, "one more guess", **attacker).status_code == 401
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 429            # 8 again within the window
    clock.t += 600
    assert sign_in(client, PASSWORDS["owner"], **attacker).status_code == 303


def test_the_login_page(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen={"siteLabel": 'shop"><script>alert(1)</script>.co.il'})
    page = visit(None).get("/login")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "no-cache, must-revalidate"
    text = page.text
    assert '<html lang="he" dir="rtl">' in text and 'name="viewport"' in text and "prefers-color-scheme:dark" in text
    assert '<form class="card" method="post" action="/login">' in text
    assert '<input name="p" type="password"' in text and '<button type="submit">כניסה</button>' in text
    assert '<div class="err" role="alert"></div>' in text
    assert "shop&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;.co.il" in text and Scripts(text).found == []
    assert not re.search(r"https?:|//|src=|<link|@import|url\(", text)          # nothing is fetched from anywhere

    wrong = sign_in(visit(None), "a guess")
    assert '<div class="err" role="alert">%s</div>' % server.TEXT_WRONG in wrong.text
    assert visit("vendor").get("/login").headers["location"] == "/"


def test_a_password_in_another_alphabet(monkeypatch, visit):
    monkeypatch.setenv("SH_PASS_VENDOR_DANA", "סיסמה חזקה")
    assert sign_in(visit(None), " סיסמה חזקה").status_code == 303
    assert sign_in(visit(None), "סיסמה חלשה").status_code == 401


def test_the_sign_in_form_is_open_to_a_signed_in_vendor(visit):
    client = visit("vendor")                                   # it is how a person changes identity
    assert client.get("/api/messages").status_code == 403
    assert sign_in(client, PASSWORDS["owner"]).status_code == 303
    assert client.get("/api/messages").status_code == 200


def test_logout_removes_the_cookie(visit):
    client = visit("owner")
    response = client.get("/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/login")
    value, attributes = cookie_of(response)
    assert value in ("", '""') and "max-age=0" in attributes
    assert client.get("/site").headers["location"] == "/login"


# ================================================================ the time window (§5.1)

def window_of(fake):
    params = fake.params("sh_availability")
    return params["p_from"], params["p_to"]


def at(text):
    return datetime.fromisoformat(text)


@pytest.mark.parametrize("query, hours", [
    ({}, 24), ({"h": ""}, 24), ({"h": "abc"}, 24), ({"h": "2.5"}, 24), ({"h": "24"}, 24), ({"h": "168"}, 168),
    ({"h": "2160"}, 2160), ({"h": "0"}, 1), ({"h": "-7"}, 1), ({"h": "9600"}, 9600), ({"h": "9601"}, 9600),
    ({"h": "99999999999"}, 9600), ({"h": "48", "t": "2026-11-01"}, 48),                    # t without f means nothing
    ({"h": "48", "f": "2026-13-45", "t": "2026-11-12"}, 48), ({"h": "48", "f": "yesterday"}, 48),
    ({"h": "48", "f": "2026-11-10", "t": "2026-02-30"}, 48), ({"f": "2026-11-31"}, 24),    # invalid dates: back to h
])
def test_a_window_of_hours(query, hours, fake, visit):
    answer = visit("owner").get("/api/site", params=query).json()
    p_from, p_to = window_of(fake)
    assert at(p_from) == NOW - timedelta(hours=hours) and at(p_to) == NOW + timedelta(minutes=1)
    assert p_to == "2026-11-13T10:16:30+02:00"                 # written in the site's zone
    assert (answer["from"], answer["to"], answer["hours"]) == (p_from, p_to, hours)


@pytest.mark.parametrize("query, p_from, p_to, hours", [
    # t is inclusive: the window ends when day t ends
    ({"f": "2026-11-01", "t": "2026-11-03"}, "2026-11-01T00:00:00+02:00", "2026-11-04T00:00:00+02:00", 72),
    ({"f": "2026-11-12", "t": "2026-11-12", "h": "720"}, "2026-11-12T00:00:00+02:00", "2026-11-13T00:00:00+02:00", 24),
    ({"f": "2026-11-13", "t": "2026-11-20"}, "2026-11-13T00:00:00+02:00", "2026-11-21T00:00:00+02:00", 192),
    # without t: until now (not until now + 1 minute)
    ({"f": "2026-11-12"}, "2026-11-12T00:00:00+02:00", "2026-11-13T10:15:30+02:00", 34),
    ({"f": "2026-11-13", "t": ""}, "2026-11-13T00:00:00+02:00", "2026-11-13T10:15:30+02:00", 10),
    # an end that is not after the start: one day from the start
    ({"f": "2026-11-10", "t": "2026-11-05"}, "2026-11-10T00:00:00+02:00", "2026-11-11T00:00:00+02:00", 24),
    ({"f": "2026-11-10", "t": "2026-11-09"}, "2026-11-10T00:00:00+02:00", "2026-11-11T00:00:00+02:00", 24),
    ({"f": "2026-12-01"}, "2026-12-01T00:00:00+02:00", "2026-12-02T00:00:00+02:00", 24),
    # the clocks change (Israel 2026: forward on 27.3 at 02:00, back on 25.10 at 02:00): local days of 23 and 25 hours
    ({"f": "2026-03-27", "t": "2026-03-27"}, "2026-03-27T00:00:00+02:00", "2026-03-28T00:00:00+03:00", 23),
    ({"f": "2026-10-25", "t": "2026-10-25"}, "2026-10-25T00:00:00+03:00", "2026-10-26T00:00:00+02:00", 25),
    ({"f": "2026-03-26", "t": "2026-03-28"}, "2026-03-26T00:00:00+02:00", "2026-03-29T00:00:00+03:00", 71),
])
def test_a_window_of_dates(query, p_from, p_to, hours, fake, visit):
    answer = visit("owner").get("/api/site", params=query).json()
    assert window_of(fake) == (p_from, p_to)
    assert (answer["from"], answer["to"], answer["hours"]) == (p_from, p_to, hours)


@pytest.mark.parametrize("now, h, p_from, p_to", [
    # across the change the window is h real hours, so its local start moves by an hour
    ("2026-03-27T12:00:00+03:00", 24, "2026-03-26T11:00:00+02:00", "2026-03-27T12:01:00+03:00"),
    ("2026-10-25T12:00:00+02:00", 24, "2026-10-24T13:00:00+03:00", "2026-10-25T12:01:00+02:00"),
    ("2026-10-25T01:30:00+02:00", 1, "2026-10-25T01:30:00+03:00", "2026-10-25T01:31:00+02:00"),   # the repeated hour
])
def test_a_window_of_hours_across_a_clock_change(now, h, p_from, p_to, monkeypatch, fake, visit):
    monkeypatch.setattr(server, "_now", lambda: at(now).astimezone(timezone.utc))
    visit("owner").get("/api/site", params={"h": h})
    assert window_of(fake) == (p_from, p_to)
    assert at(p_to) - at(p_from) == timedelta(hours=h, minutes=1)


def test_the_window_uses_the_zone_of_the_configuration(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, time_zone="America/New_York")      # the US clocks go back on 1.11.2026
    visit("owner").get("/api/site", params={"f": "2026-11-01", "t": "2026-11-01"})
    assert window_of(fake) == ("2026-11-01T00:00:00-04:00", "2026-11-02T00:00:00-05:00")


def test_every_call_gets_the_same_window(fake, visit):
    client, span = visit("owner"), {"p_from": "2026-11-01T00:00:00+02:00", "p_to": "2026-11-04T00:00:00+02:00"}
    query = {"f": "2026-11-01", "t": "2026-11-03"}
    client.get("/api/site", params=query)
    for fn in ("sh_availability", "sh_availability_series", "sh_speed", "sh_alerts_range"):
        assert fake.params(fn) == span
    assert fake.params("sh_speed_series") == dict(span, p_strategy="mobile")
    for fn in ("sh_alerts_open", "sh_health", "sh_product_issues", "sh_cert"):
        assert fake.params(fn) is None
    client.get("/api/site/drill", params=dict(query, what="fails"))
    assert fake.params("sh_drill_fails") == dict(span, p_page=None, p_bucket=None)
    client.get("/api/site/drill", params=dict(query, what="runs", url="https://example.co.il/"))
    assert fake.params("sh_drill_runs") == dict(span, p_url="https://example.co.il/", p_strategy="mobile",
                                                p_bucket=None)
    client.get("/api/messages", params=query)
    assert fake.params("sh_messages") == span


# ================================================================ the data calls (§5.2 – §5.7)

def test_api_site_puts_the_parts_together(fake, visit):
    response = visit("owner").get("/api/site", params={"h": 168, "strategy": "desktop"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    expected = {"hours": 168, "from": "2026-11-06T10:15:30+02:00", "to": "2026-11-13T10:16:30+02:00",
                "strategy": "desktop"}
    expected.update({key: fake.answers[fn] for key, fn in SITE_PARTS.items()})
    assert response.json() == expected
    assert sorted(fake.names()) == sorted(["sh_config", *SITE_PARTS.values()])       # each function once
    assert fake.params("sh_speed_series")["p_strategy"] == "desktop"


@pytest.mark.parametrize("strategy", ["mobile", "", "tablet", "DESKTOP", None])
def test_any_strategy_but_desktop_is_mobile(strategy, fake, visit):
    answer = visit("owner").get("/api/site", params={} if strategy is None else {"strategy": strategy}).json()
    assert answer["strategy"] == "mobile" and fake.params("sh_speed_series")["p_strategy"] == "mobile"


@pytest.mark.parametrize("broken", SITE_PARTS)
def test_each_part_fails_alone(broken, fake, visit):
    fake.failing.add(SITE_PARTS[broken])
    response = visit("owner").get("/api/site")
    assert response.status_code == 200
    answer = response.json()
    assert answer[broken] == {"error": "boom: " + SITE_PARTS[broken]}
    for key, fn in SITE_PARTS.items():
        if key != broken:
            assert answer[key] == fake.answers[fn]


def test_a_part_fails_alone_whatever_the_failure(fake, monkeypatch, visit):
    def broken(fn, params=None):
        if fn == "sh_speed":
            raise ZeroDivisionError("not a DbError")
        return fake(fn, params)

    monkeypatch.setattr(db, "rpc", broken)
    answer = visit("owner").get("/api/site").json()
    assert answer["speed"] == {"error": "not a DbError"} and answer["availability"] == fake.answers["sh_availability"]

    fake.failing.update(SITE_PARTS.values())                   # everything down: still an answer, part by part
    response = visit("owner").get("/api/site")
    assert response.status_code == 200
    assert all(response.json()[key] == {"error": "boom: " + fn} for key, fn in SITE_PARTS.items() if key != "speed")


def test_an_empty_part_is_a_list_and_an_unchecked_certificate_is_null(fake, visit):
    for fn in SITE_PARTS.values():
        fake.answers[fn] = None
    answer = visit("owner").get("/api/site").json()
    assert all(answer[key] == [] for key in SITE_PARTS if key != "cert") and answer["cert"] is None


def test_the_parts_are_read_in_parallel(fake, visit):
    client = visit("owner")
    fake.barrier = threading.Barrier(len(SITE_PARTS), timeout=10)      # released only by nine simultaneous calls
    answer = client.get("/api/site").json()
    assert not fake.barrier.broken
    assert all(answer[key] == fake.answers[fn] for key, fn in SITE_PARTS.items())


def test_without_the_configuration_a_data_call_is_a_502(fake, visit):
    fake.failing.add("sh_config")
    for path in ("/api/site", "/api/site/drill?what=fails", "/api/messages"):
        response = visit("owner").get(path)
        assert (response.status_code, response.json()) == (502, {"error": "boom: sh_config"})
        assert response.headers["cache-control"] == "no-store"
    fake.failing.clear()
    for incomplete in (NOT_SET_UP, None, dict(CONFIG, time_zone="Mars/Olympus"), {"time_zone": "UTC", "host": "x.com"}):
        fake.answers["sh_config"] = incomplete
        response = visit("owner").get("/api/site")
        assert response.status_code == 502 and "sh_setup" in response.json()["error"]
        assert visit("owner").get("/site").status_code == 502


def test_api_now(fake, visit):
    client = visit("owner")
    response = client.get("/api/site/now")
    assert (response.status_code, response.json()) == (200, fake.answers["sh_now"])
    assert response.headers["cache-control"] == "no-store" and fake.calls == [("sh_now", None)]
    fake.failing.add("sh_now")
    response = client.get("/api/site/now")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_now"})
    assert response.headers["cache-control"] == "no-store"


def test_drill_passes_the_parameters_through(fake, visit):
    client = visit("owner")
    span = {"p_from": "2026-11-12T10:15:30+02:00", "p_to": "2026-11-13T10:16:30+02:00"}
    response = client.get("/api/site/drill", params={"what": "fails", "page": "סל", "bucket": "2026-11-13 09:00"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"rows": fake.answered["sh_drill_fails"]} and len(response.json()["rows"]) == 23
    assert fake.params("sh_drill_fails") == dict(span, p_page="סל", p_bucket="2026-11-13 09:00")

    response = client.get("/api/site/drill", params={"what": "bucket", "bucket": "2026-11-12"})
    assert response.json() == {"rows": fake.answered["sh_drill_bucket"]} and len(response.json()["rows"]) == 4
    assert fake.params("sh_drill_bucket") == {"p_bucket": "2026-11-12"}

    fake.calls.clear()
    query = {"what": "runs", "url": "https://example.co.il/cart/", "strategy": "desktop", "bucket": "2026-11-13 09:00"}
    response = client.get("/api/site/drill", params=query)
    assert response.json() == {"rows": fake.answered["sh_drill_runs"]} and response.json()["rows"][0]["ok"] is True
    assert fake.params("sh_drill_runs") == dict(span, p_url="https://example.co.il/cart/", p_strategy="desktop",
                                                p_bucket="2026-11-13 09:00")

    response = client.get("/api/site/drill", params={"what": "alert", "id": "41"})
    assert response.json() == {"rows": fake.answered["sh_drill_alert"]} and ids(response.json()["rows"]) == [41]
    assert fake.params("sh_drill_alert") == {"p_id": 41}


@pytest.mark.parametrize("query", [{"what": "alert"}, {"what": "alert", "id": ""}, {"what": "alert", "id": "abc"},
                                   {"what": "alert", "id": "-41"}, {"what": "alert", "id": "41;drop"}])
def test_drill_of_an_alert_without_a_usable_id_has_no_rows(query, fake, visit):
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (200, {"rows": []}) and fake.calls == []


@pytest.mark.parametrize("query", [{}, {"what": ""}, {"what": "everything"}, {"what": "FAILS"}])
def test_drill_of_an_unknown_kind_is_a_400(query, fake, visit):
    fake.failing.add("sh_config")                              # decided before the database is asked
    response = visit("owner").get("/api/site/drill", params=query)
    assert (response.status_code, response.json()) == (400, {"error": "what?"})
    assert response.headers["cache-control"] == "no-store" and fake.calls == []


@pytest.mark.parametrize("what, fn", [("fails", "sh_drill_fails"), ("bucket", "sh_drill_bucket"),
                                      ("runs", "sh_drill_runs"), ("alert", "sh_drill_alert")])
def test_drill_failure_and_empty_result(what, fn, fake, visit):
    client = visit("owner")
    fake.answers[fn] = None
    assert client.get("/api/site/drill", params={"what": what, "id": 41}).json() == {"rows": []}
    fake.failing.add(fn)
    response = client.get("/api/site/drill", params={"what": what, "id": 41})
    assert (response.status_code, response.json()) == (502, {"error": "boom: " + fn})


def test_messages(fake, visit):
    client = visit("staff")
    response = client.get("/api/messages", params={"h": 720})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"rows": fake.answers["sh_messages"]} and len(response.json()["rows"]) == 10
    assert fake.params("sh_messages") == {"p_from": "2026-10-14T11:15:30+03:00", "p_to": "2026-11-13T10:16:30+02:00"}
    fake.answers["sh_messages"] = None
    assert client.get("/api/messages").json() == {"rows": []}
    fake.failing.add("sh_messages")
    response = client.get("/api/messages")
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_messages"})


@pytest.mark.parametrize("body, p_ids", [
    ({"ids": [41, 40]}, [41, 40]),
    ({"id": 41}, [41]),
    ({"ids": ["41", 40, "40", 41]}, [41, 40]),                 # the screen sends what it read from the page; no repeats
    ({"ids": [41], "id": 7}, [41]),
    ({"ids": ["x", -1, 0, 1.5, True, None, [3], {"id": 4}, " 5", "٦", 6]}, [6]),
    ({"ids": list(range(1, 201))}, list(range(1, 201))),
    ({"ids": list(range(1, 251))}, list(range(1, 201))),       # up to 200: the rest stay open and show again
])
def test_ack_marks_the_listed_alerts(body, p_ids, fake, visit):
    response = visit("owner").post("/api/alerts/ack", json=body)
    assert (response.status_code, response.json()) == (200, {"ok": True, "n": len(p_ids)})
    assert response.headers["cache-control"] == "no-store"
    assert fake.calls == [("sh_alert_ack", {"p_ids": p_ids, "p_who": "owner"})]


@pytest.mark.parametrize("body", [b"", b"not json", b"[41]", b"41", b"null", b'"41"', b"{}", b'{"ids": []}',
                                  b'{"ids": "41"}', b'{"ids": ["x", 0, -3, true]}', b'{"id": "abc"}', b'{"id": null}',
                                  b'{"id": [41]}', b'{"ids": {"0": 41}}',
                                  b'{"ids": [41], "pad": "' + b"x" * 20000 + b'"}'])
def test_ack_refuses_a_bad_body(body, fake, visit):
    response = visit("owner").post("/api/alerts/ack", content=body, headers={"Content-Type": "application/json"})
    assert (response.status_code, response.json()) == (400, {"error": "bad request"}) and fake.calls == []


def test_ack_reports_who_and_how_many(fake, visit):
    visit("staff").post("/api/alerts/ack", json={"ids": [41]})
    assert fake.params("sh_alert_ack")["p_who"] == "staff"     # the label of the signed-in user
    fake.answers["sh_alert_ack"] = {"n": 1}                    # one of the two had closed meanwhile
    assert visit("owner").post("/api/alerts/ack", json={"ids": [41, 38]}).json() == {"ok": True, "n": 1}
    fake.failing.add("sh_alert_ack")
    response = visit("owner").post("/api/alerts/ack", json={"ids": [41]})
    assert (response.status_code, response.json()) == (502, {"error": "boom: sh_alert_ack"})


# ================================================================ the page

def test_the_marker_is_replaced_exactly_once(visit):
    source = (REFERENCE.parent / "site_health.html").read_text(encoding="utf-8")
    assert source.count(server.MARKER) == 1
    response = visit("owner").get("/site")
    assert response.status_code == 200 and response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    script = ('<script>window.SH_CONFIG={"hide": [], "brand": "", "homePage": "בית", "coreCount": 5, '
              '"liveHosts": ["live"], "siteLabel": "example.co.il", "bucketNote": "", "probeCount": 4, "pathLabels": '
              '[["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]]};window.SH_ROLE={};</script>')
    assert response.text == source.replace(server.MARKER, script)          # the rest of the file is untouched
    assert response.text.count("window.SH_CONFIG=") == 1 and server.MARKER not in response.text


@pytest.mark.parametrize("role", ["owner", "staff", "vendor", "noalerts", "share"])
def test_the_page_carries_the_role_of_the_viewer(role, visit):
    path = "/status" if role == "share" else "/site"
    config, screen_role = injected(send(visit, role, "GET", path).text)
    assert screen_role == SCREEN_ROLE[role]
    assert config == (dict(SCREEN_CONFIG, shareKey=TOKEN) if role == "share" else SCREEN_CONFIG)


HOSTILE = {"siteLabel": 'x</script><script>alert("1")</script>', "brand": "a'b\"c\\d</SCRIPT >",
           "bucketNote": "<!--<script>\u2028\u2029-->", "homePage": "בית & </",
           "nav": [["a", "/x", "]]>;window.SH_ROLE={};"]]}


def test_a_hostile_configuration_value_cannot_leave_the_script(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    plain = Scripts((REFERENCE.parent / "site_health.html").read_text(encoding="utf-8")).found
    page = visit("vendor").get("/site").text
    scripts = Scripts(page).found
    assert len(scripts) == len(plain) + 1 and scripts[1:] == plain          # one script more, the screen's own intact
    assert not re.search("[<\u2028\u2029]", scripts[0])                     # nothing that can end or break the script
    assert injected(page) == (HOSTILE, {"readonly": True})                  # and the values arrive unchanged
    assert "<script>alert" not in page and page.count("</script>") == len(plain) + 1


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_injected_script_is_javascript_that_yields_the_same_values(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, screen=HOSTILE)
    script = Scripts(visit("vendor").get("/site").text).found[0]
    program = "var window = {};%s;process.stdout.write(JSON.stringify([window.SH_CONFIG, window.SH_ROLE]))" % script
    done = subprocess.run(["node", "-e", program], capture_output=True, encoding="utf-8", timeout=60, check=True)
    assert json.loads(done.stdout) == [HOSTILE, {"readonly": True}]


def test_the_configuration_is_read_once_a_minute(fake, clock, visit):
    client = visit("owner")
    for _ in range(3):
        client.get("/site")
        client.get("/api/site")
    assert fake.names().count("sh_config") == 1
    clock.t += 59
    client.get("/site")
    assert fake.names().count("sh_config") == 1
    fake.answers["sh_config"] = dict(CONFIG, screen=dict(SCREEN_CONFIG, siteLabel="other.co.il"))
    clock.t += 1
    assert injected(client.get("/site").text)[0]["siteLabel"] == "other.co.il"
    assert fake.names().count("sh_config") == 2


def test_the_page_without_the_configuration_says_so(fake, visit):
    fake.failing.add("sh_config")
    for role, path in (("owner", "/site"), ("share", "/status")):
        response = send(visit, role, "GET", path)
        assert response.status_code == 502 and server.TEXT_NO_DATA in response.text and "boom" not in response.text
        assert response.headers["x-robots-tag"] == "noindex"
    fake.failing.clear()                                       # a failure is not remembered
    assert visit("owner").get("/site").status_code == 200


def test_another_screen_file(monkeypatch, tmp_path, visit):
    screen = tmp_path / "screen.html"
    screen.write_text("<head><!--SH_INJECT--></head>ported screen", encoding="utf-8")
    monkeypatch.setenv("SH_SCREEN", str(screen))
    assert visit("owner").get("/site").text.endswith("window.SH_ROLE={};</script></head>ported screen")
    screen.write_text("<head></head>no marker", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SH_INJECT"):
        visit("owner").get("/site")                            # never a page that silently lost its role


# ================================================================ real-user beacons (§7.7)

def beacon(client, body=BEACON, **headers):
    content = body if isinstance(body, (bytes, str)) else json.dumps(body)
    response = client.post("/rum", content=content, headers={"Content-Type": "text/plain;charset=UTF-8", **headers})
    assert (response.status_code, response.content) == (204, b"")           # always, stored or not
    assert response.headers["x-robots-tag"] == "noindex"


def stored(fake):
    return [row for fn, params in fake.calls if fn == "sh_rum_add" for row in params["p_rows"]]


def test_a_beacon_is_stored_without_anything_about_the_visitor(fake, visit):
    client = visit("vendor")                                   # even with a session cookie on the request
    body = dict(BEACON, path="/product/sofa/?utm_source=mail&email=dana@example.com#reviews", ua="x", ip="y")
    beacon(client, body, **ORIGIN, **{"X-Forwarded-For": "203.0.113.77", "User-Agent": "Mozilla/5.0 (secret-agent)",
                                      "Cookie": "customer_session=abc123",
                                      "Referer": "https://example.co.il/product/sofa/?token=t0k"})
    assert fake.calls == [("sh_config", None), ("sh_rum_add", {"p_rows": [
        {"site": "live", "path": "/product/sofa/", "lcp_ms": 2345, "is_test": False}]})]
    recorded = json.dumps(fake.calls)
    secrets = ("203.0.113.77", "secret-agent", "abc123", client.cookies[server.COOKIE], "utm", "dana", "t0k", "reviews")
    assert not [secret for secret in secrets if secret in recorded]


@pytest.mark.parametrize("headers, kept", [
    ({"Origin": "https://example.co.il"}, True),
    ({"Origin": "https://www.example.co.il"}, True),
    ({"Origin": "https://WWW.Example.co.il:8443"}, True),
    ({"Referer": "https://www.example.co.il/product/sofa/?a=1"}, True),       # no Origin: the Referer decides
    ({"Origin": "https://example.co.il", "Referer": "https://elsewhere.com/"}, True),
    ({}, False),
    ({"Origin": "null"}, False),
    ({"Origin": "https://staging.example.co.il"}, False),
    ({"Origin": "https://example.co.il.evil.com"}, False),
    ({"Origin": "https://evilexample.co.il"}, False),
    ({"Origin": "https://elsewhere.com", "Referer": "https://example.co.il/"}, False),
    ({"Referer": "https://elsewhere.com/?https://example.co.il/"}, False),
])
def test_only_the_site_itself_may_send_beacons(headers, kept, fake, visit):
    beacon(visit(None), **headers)
    assert len(stored(fake)) == kept


def test_the_configured_host_may_be_written_with_www(fake, visit):
    fake.answers["sh_config"] = dict(CONFIG, host="WWW.example.co.il")
    client = visit(None)
    beacon(client, **ORIGIN)
    beacon(client, Origin="https://www.example.co.il")
    assert len(stored(fake)) == 2


@pytest.mark.parametrize("change, row", [
    ({"path": "/"}, {"path": "/"}),
    ({"path": "/product/%D7%A1%D7%A4%D7%94/?x=1"}, {"path": "/product/%D7%A1%D7%A4%D7%94/"}),
    ({"path": "/cart/#top"}, {"path": "/cart/"}),
    ({"path": "/product/order-of-the-phoenix-poster/"}, {"path": "/product/order-of-the-phoenix-poster/"}),
    ({"lcp": 1}, {"lcp_ms": 1}), ({"lcp": 60000}, {"lcp_ms": 60000}), ({"lcp": 1234.6}, {"lcp_ms": 1235}),
    ({"test": True}, {"is_test": True}), ({"test": "yes"}, {"is_test": False}),
    ({"site": "staging.example.co.il"}, {"site": "staging.example.co.il"}),
])
def test_what_is_stored(change, row, fake, visit):
    beacon(visit(None), dict(BEACON, **change), **ORIGIN)
    assert stored(fake) == [dict({"site": "live", "path": "/product/sofa/", "lcp_ms": 2345, "is_test": False}, **row)]


@pytest.mark.parametrize("change", [
    {"path": "/my-account/"}, {"path": "/my-account/orders/"}, {"path": "/account/login"}, {"path": "/checkout/"},
    {"path": "/he/Checkout/"}, {"path": "/checkout/order-received/1234/?key=wc_order_abc"},
    {"path": "/checkouts/c/abc"},
    {"path": "/checkout/order-pay/77/"}, {"path": "/my-account/view-order/77/"}, {"path": "/12345/orders/abcdef"},
    {"path": "/wp-admin/index.php"}, {"path": "/admin"}, {"path": "/wp-login.php"},
    {"path": "/my-account/lost-password/"},
    {"path": "product/sofa/"}, {"path": "https://example.co.il/x"}, {"path": ""}, {"path": None}, {"path": 7},
    {"lcp": 0}, {"lcp": 0.4}, {"lcp": 60001}, {"lcp": -5}, {"lcp": "2345"}, {"lcp": None}, {"lcp": True}, {"lcp": [1]},
    {"site": ""}, {"site": None}, {"site": "Live Site"}, {"site": "a" * 300},
])
def test_what_is_dropped(change, fake, visit):
    beacon(visit(None), dict(BEACON, **change), **ORIGIN)
    assert stored(fake) == []


@pytest.mark.parametrize("body", [b"", b"not json", b"[1]", b"null", b'"x"', b'{"site":"live","path":"/","lcp":NaN}',
                                  b'{"site":"live","path":"/","lcp":1e999}', b"\xff\xfe"])
def test_a_garbage_beacon_is_dropped(body, fake, visit):
    beacon(visit(None), body, **ORIGIN)
    assert stored(fake) == []


def test_a_beacon_larger_than_1_kb_is_dropped(fake, visit):
    def sized(size):
        body = json.dumps(dict(BEACON, pad=""))
        return body.replace('"pad": ""', '"pad": "%s"' % ("x" * (size - len(body))))

    client = visit(None)
    assert len(sized(1024)) == 1024 and len(sized(1025)) == 1025
    beacon(client, sized(1024), **ORIGIN)
    assert len(stored(fake)) == 1
    beacon(client, sized(1025), **ORIGIN)
    beacon(client, sized(500000), **ORIGIN)
    assert len(stored(fake)) == 1


def test_sixty_beacons_a_minute_per_address(fake, clock, visit):
    client, one, two = visit(None), {"X-Forwarded-For": "203.0.113.1"}, {"X-Forwarded-For": "203.0.113.2"}
    for _ in range(60):
        beacon(client, **ORIGIN, **one)
    assert len(stored(fake)) == 60
    beacon(client, **ORIGIN, **one)                            # the 61st: answered, not stored
    beacon(client, {"garbage": 1}, **ORIGIN, **two)            # a dropped beacon counts as well
    assert len(stored(fake)) == 60
    beacon(client, **ORIGIN, **two)                            # another address has its own count
    assert len(stored(fake)) == 61
    clock.t += 60                                              # the next minute
    beacon(client, **ORIGIN, **one)
    assert len(stored(fake)) == 62
    assert json.dumps(fake.calls).count("203.0.113") == 0


def test_beacons_are_answered_while_the_database_is_down(fake, visit):
    client = visit(None)
    fake.failing.add("sh_rum_add")
    beacon(client, **ORIGIN)
    assert fake.names() == ["sh_config", "sh_rum_add"] and server._rum_queue == [] and server._rum_busy is False
    fake.failing.add("sh_config")
    server._site_cache.update(site=None)
    beacon(client, **ORIGIN)                                   # the site's host is unknown: dropped
    assert fake.names() == ["sh_config", "sh_rum_add", "sh_config"]


def test_waiting_rows_go_out_in_small_batches(fake, visit):
    client = visit(None)
    waiting = [{"site": "live", "path": "/p/%d/" % i, "lcp_ms": 2000, "is_test": False} for i in range(120)]
    server._rum_queue.extend(waiting)                        # what piles up while the database is slow
    beacon(client, **ORIGIN)
    sizes = [len(params["p_rows"]) for fn, params in fake.calls if fn == "sh_rum_add"]
    assert sizes == [50, 50, 21] and stored(fake)[:120] == waiting and server._rum_queue == []

    server._rum_queue.extend(waiting * 9)                    # 1,080 waiting: over the limit, the newcomer is dropped
    fake.calls.clear()
    beacon(client, dict(BEACON, path="/newcomer/"), **ORIGIN)
    assert len(stored(fake)) == 1080 and all(row["path"] != "/newcomer/" for row in stored(fake))


# ================================================================ /health (§7.10) and start-up

def test_health(fake):
    client = TestClient(server.app)                            # no session
    for flow in fake.answers["sh_health"]:
        flow["last_at"] = (NOW - timedelta(hours=3)).isoformat()
    fake.answers["sh_health"][0].update(flow_name=server.PROBE_FLOW, last_at="2026-11-13T10:14:48.5+02:00")   # 41.5 s
    response = client.get("/health")
    assert (response.status_code, response.json()) == (200, {"ok": True, "db": "ok", "last_probe_age_sec": 41})
    assert response.headers["cache-control"] == "no-store" and response.headers["x-robots-tag"] == "noindex"
    assert fake.names() == ["sh_ping", "sh_health"]

    fake.answers["sh_health"][0]["last_at"] = None             # installed, the prober has not run yet
    assert client.get("/health").json() == {"ok": True, "db": "ok", "last_probe_age_sec": None}
    fake.answers["sh_health"] = None
    assert client.get("/health").json() == {"ok": True, "db": "ok", "last_probe_age_sec": None}


def test_health_stays_200_when_the_database_is_down(fake, monkeypatch):
    client = TestClient(server.app)
    fake.failing.add("sh_ping")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "boom: sh_ping", "last_probe_age_sec": None}
    fake.failing = {"sh_health"}
    assert client.get("/health").json() == {"ok": False, "db": "boom: sh_health", "last_probe_age_sec": None}

    def crash(fn, params=None):
        raise RuntimeError()

    monkeypatch.setattr(db, "rpc", crash)                      # whatever goes wrong
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "db": "RuntimeError", "last_probe_age_sec": None}


def collectors_module(monkeypatch, start):
    module = types.ModuleType("collectors")
    module.start = start
    monkeypatch.setitem(sys.modules, "collectors", module)


@pytest.mark.parametrize("setting, started", [(None, 1), ("1", 1), ("0", 0)])
def test_the_collectors_start_with_the_server(setting, started, monkeypatch):
    starts = []
    collectors_module(monkeypatch, lambda: starts.append(1))
    monkeypatch.delenv("COLLECTORS")
    if setting is not None:
        monkeypatch.setenv("COLLECTORS", setting)
    assert starts == []                                        # importing the server starts nothing
    with TestClient(server.app) as client:
        assert client.get("/health").status_code == 200
    assert len(starts) == started


@pytest.mark.parametrize("problem", ["missing", "broken"])
def test_the_server_comes_up_without_working_collectors(problem, monkeypatch, caplog):
    def start():
        raise OSError("no network")

    collectors_module(monkeypatch, start)
    if problem == "missing":
        monkeypatch.setitem(sys.modules, "collectors", None)   # "import collectors" now fails: no such module
    monkeypatch.setenv("COLLECTORS", "1")
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"), TestClient(server.app) as client:
        assert client.get("/login").status_code == 200
    message, = [record.getMessage() for record in caplog.records]
    assert message.startswith("collectors: NOT started")
    assert ("no network" if problem == "broken" else "collectors") in message


# ================================================================ db.py

class Supabase(BaseHTTPRequestHandler):
    """A stand-in for Supabase's REST interface: answers POST /rest/v1/rpc/<fn> and keeps the requests."""
    seen = []
    answers = {
        "sh_ping": (200, b'"ok"'),
        "sh_login_log_add": (204, b""),                        # a function that returns nothing
        "sh_missing": (404, b'{"code": "PGRST202", "details": "searched in the schema", "hint": null, '
                            b'"message": "Could not find the function public.sh_missing in the schema cache"}'),
        "sh_gateway": (502, b"<html>bad gateway</html>"),
        "sh_html": (200, b"<html>not json</html>"),
    }

    def log_message(self, *args):
        pass

    def do_POST(self):
        params = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.seen.append((self.path, {name.lower(): value for name, value in self.headers.items()}, params))
        status, body = self.answers.get(self.path.rsplit("/", 1)[-1], (200, json.dumps({"got": params}).encode()))
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def supabase(monkeypatch):
    """SUPABASE_URL + SUPABASE_SECRET_KEY pointing at the stand-in; yields the requests it received."""
    Supabase.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Supabase)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:%d/" % httpd.server_address[1])
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_for_tests")
    monkeypatch.setenv("DATABASE_URL", "postgresql://not-used.invalid/x")     # the Supabase pair comes first
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setitem(sys.modules, "psycopg", None)          # importing the driver on this path would now fail
    yield Supabase.seen
    httpd.shutdown()
    httpd.server_close()


def test_db_over_https(supabase):
    assert REAL_RPC("sh_ping") == "ok"
    params = {"p_from": "2026-11-12T00:00:00+02:00", "p_page": None, "p_ok": True, "p_rows": [{"path": "/סל/"}]}
    assert REAL_RPC("sh_anything", params) == {"got": params}
    assert REAL_RPC("sh_login_log_add", {"p_who": "owner"}) is None
    path, headers, sent = supabase[1]
    assert (path, sent) == ("/rest/v1/rpc/sh_anything", params) and supabase[0][2] == {}
    assert (headers["apikey"], headers["authorization"]) == ("sb_secret_for_tests", "Bearer sb_secret_for_tests")
    assert headers["content-type"] == "application/json"


@pytest.mark.parametrize("fn, message", [
    ("sh_missing", "HTTP 404: Could not find the function public.sh_missing in the schema cache"),  # PostgREST's words
    ("sh_gateway", "HTTP 502: Bad Gateway"),
    ("sh_html", "the database API did not answer with JSON"),
])
def test_db_over_https_reports_failures(fn, message, supabase):
    with pytest.raises(db.DbError) as error:
        REAL_RPC(fn)
    assert str(error.value) == message


def test_db_over_https_when_nothing_answers(supabase, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")   # nothing listens there
    with pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "database unreachable (ConnectionRefusedError)"       # no address, no key
    assert supabase == []


@pytest.mark.parametrize("fn, params", [
    ("sh_ping; drop table sh_alerts", None), ("sh_ping\n", None), ("sh_Ping", None), ("pg_sleep", None), ("sh_", None),
    ("sh_x/../../auth/v1/admin/users", None), ("", None),
    ("sh_alert_ack", {"p_ids) or (true": [1]}), ("sh_alert_ack", {"ids": [1]}), ("sh_alert_ack", {"p_ids\n": [1]}),
])
def test_db_refuses_names_that_are_not_sh_functions_and_p_parameters(fn, params, supabase):
    with pytest.raises(db.DbError, match="bad function or parameter name"):
        REAL_RPC(fn, params)
    assert supabase == []                                      # refused before anything is sent


def test_db_without_configuration(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(db.DbError) as error:
        REAL_RPC("sh_ping")
    assert str(error.value) == "no database configured: set SUPABASE_URL and SUPABASE_SECRET_KEY, or DATABASE_URL"
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")        # half a pair is not a configuration
    with pytest.raises(db.DbError, match="no database configured"):
        REAL_RPC("sh_ping")


def test_db_over_a_postgres_connection(request, monkeypatch):
    try:
        url = request.getfixturevalue("database")              # conftest.py: a scratch database with the kit's SQL
    except Exception as e:
        pytest.skip("no scratch Postgres database: %s" % e)
    import psycopg

    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(db, "_thread", threading.local())
    try:
        assert REAL_RPC("sh_ping") == "ok"
        conn = db._thread.conn
        assert conn.autocommit and conn.prepare_threshold is None          # what a transaction pooler needs
        config = json.loads((REFERENCE / "site_health.config.example.json").read_text(encoding="utf-8"))
        assert REAL_RPC("sh_setup", {"p_config": config})["time_zone"] == "Asia/Jerusalem"       # a dict goes as jsonb
        assert REAL_RPC("sh_config")["screen"]["homePage"] == "בית"
        span = {"p_from": "2026-11-12T00:00:00+02:00", "p_to": "2026-11-13T00:00:00+02:00"}      # times as text
        assert REAL_RPC("sh_drill_fails", dict(span, p_page=None, p_bucket=None)) == []
        assert REAL_RPC("sh_alert_ack", {"p_ids": [1, 2], "p_who": "owner"}) == {"n": 0}          # a list goes as jsonb
        assert db._thread.conn is conn                                     # one connection, kept

        with pytest.raises(db.DbError, match="does not exist"):
            REAL_RPC("sh_no_such_function")
        assert REAL_RPC("sh_ping") == "ok" and db._thread.conn is conn     # an SQL error does not cost the connection

        class Dropped:                                                     # a kept connection the server has closed
            closed = False

            def execute(self, sql, values):
                self.closed = True
                raise psycopg.OperationalError("server closed the connection unexpectedly")

        db._thread.conn = Dropped()
        assert REAL_RPC("sh_ping") == "ok" and isinstance(db._thread.conn, psycopg.Connection)   # reconnected, once

        seen = []
        worker = threading.Thread(target=lambda: seen.append((REAL_RPC("sh_ping"), db._thread.conn)))
        worker.start()
        worker.join()
        assert seen[0][0] == "ok" and seen[0][1] is not db._thread.conn    # a connection per thread
        seen[0][1].close()

        monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@127.0.0.1:9/nothing")
        db._thread.conn.close()
        with pytest.raises(db.DbError) as error:
            REAL_RPC("sh_ping")
        assert str(error.value) == "database unreachable"                  # the host and the user stay in the log
    finally:
        if getattr(db._thread, "conn", None) is not None:
            db._thread.conn.close()
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/reference/tests/test_sql.py sha256=565e1134e7deef4e4e06c3f25a7b1d06e7b14bb9859ff212a53e6bad81826362 -->
~~~~~~~~python
"""Tests of schema.sql and functions.sql: the rules of SPEC §7.3, §7.4 and §7.8, with exact values.

    cd reference && python3 -m pytest -q tests/test_sql.py

Time. Tests of the window functions use fixed moments in the past: T0 is 09:00 in Jerusalem,
the time zone of the example configuration. Tests of the "now" functions place their rows
relative to db.now(), which stands still inside a test (see conftest.db).
"""
import datetime as dt
import decimal
import math
import pathlib
import sys
import threading
import time
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.types.json import Jsonb

import sim
from conftest import TIMINGS, apply_sql, example_config

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import mock_server as mock  # noqa: E402  (the kit's fake backend: the contract by example)

UTC = dt.timezone.utc
TZ = ZoneInfo("Asia/Jerusalem")
T0 = dt.datetime(2024, 11, 12, 7, 0, tzinfo=UTC)          # 12.11 09:00 in Jerusalem
SITE = "https://example.co.il"
URL = {"בית": SITE + "/", "קטגוריה": SITE + "/product-category/sofas/", "מוצר": SITE + "/product/sample-sofa/",
       "סל": SITE + "/cart/", "קופה": SITE + "/checkout/"}
PROBE = ["בית", "קטגוריה", "מוצר", "סל"]
DEAD = dict.fromkeys(PROBE, "timeout")
PROBE_FLOW, CORE_FLOW, ROTATION_FLOW, SITEMAP_FLOW, CERT_FLOW, CATALOGUE_FLOW, RUM_FLOW = (f[0] for f in mock.FLOWS)


def mins(n):
    return dt.timedelta(minutes=n)


def secs(n):
    return dt.timedelta(seconds=n)


def il(at):
    return at.astimezone(TZ).strftime("%d.%m %H:%M")


def section(rows, name):
    return [r for r in rows if r["section"] == name]


def flow(db, name):
    return next(r for r in db.rpc("sh_health") if r["flow_name"] == name)


def fails_with(db, error, match, fn, **params):
    """The call must raise; the savepoint keeps the test's transaction usable afterwards."""
    with pytest.raises(error, match=match):
        with db.conn.transaction():
            db.rpc(fn, **params)


def percentile(values, p):
    """percentile_cont, written out again: the tests do not trust the database's own arithmetic."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p
    return v[math.floor(k)] + (v[math.ceil(k)] - v[math.floor(k)]) * (k - math.floor(k))


def half_up(x):
    """Rounding as SQL rounds a numeric: halves away from zero."""
    return None if x is None else int(decimal.Decimal("%.15g" % x).quantize(decimal.Decimal(1), decimal.ROUND_HALF_UP))


# ================================================================ configuration (§7.4)

def test_setup_loads_the_example_configuration(db):
    config = db.setup()
    assert config == db.rpc("sh_config")
    assert {k: v for k, v in config.items() if k not in ("pages", "screen")} == {
        "site": SITE, "host": "example.co.il", "label": "example.co.il", "brand": "",
        "time_zone": "Asia/Jerusalem", "platform": "woocommerce", "down_after": 1, "morning": "07:30",
        "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
        "bucket_note": "", "live_hosts": ["live"]}
    assert config["pages"] == [
        {"name": "בית", "url": URL["בית"], "probe": True, "core": True, "home": True, "expect": None},
        {"name": "קטגוריה", "url": URL["קטגוריה"], "probe": True, "core": True, "home": False, "expect": None},
        {"name": "מוצר", "url": URL["מוצר"], "probe": True, "core": True, "home": False, "expect": "הוספה לסל"},
        {"name": "סל", "url": URL["סל"], "probe": True, "core": True, "home": False, "expect": None},
        {"name": "קופה", "url": URL["קופה"], "probe": False, "core": True, "home": False, "expect": None}]
    assert config["screen"] == {
        "siteLabel": "example.co.il", "brand": "", "homePage": "בית", "probeCount": 4, "coreCount": 5,
        "liveHosts": ["live"], "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
        "bucketNote": "", "hide": []}
    # the example uses the pages of the mock backend
    assert [(p["name"], p["url"]) for p in config["pages"] if p["probe"]] == [(n, SITE + path) for n, path in mock.PROBE]
    assert [(p["name"], p["url"]) for p in config["pages"] if p["core"]] == [(n, SITE + path) for n, path in mock.CORE]


def test_setup_fills_in_defaults_and_follows_the_platform(db):
    minimal = {"site": "https://www.Shop.example/", "pages": [{"name": "ראשי", "url": "https://www.shop.example/",
                                                               "home": True, "probe": True}]}
    config = db.rpc("sh_setup", p_config=minimal)
    assert {k: v for k, v in config.items() if k not in ("pages", "screen")} == {
        "site": "https://www.Shop.example", "host": "www.shop.example", "label": "shop.example", "brand": "",
        "time_zone": "UTC", "platform": "other", "down_after": 1, "morning": "07:30",
        "path_labels": [], "bucket_note": "", "live_hosts": ["live"]}
    # no catalogue: the screen hides the products card and the catalogue flow is not listed
    assert config["screen"] == {"siteLabel": "shop.example", "brand": "", "homePage": "ראשי", "probeCount": 1,
                                "coreCount": 0, "liveHosts": ["live"], "pathLabels": [], "bucketNote": "",
                                "hide": ["issuesCard"]}
    assert [r["flow_name"] for r in db.rpc("sh_health")] == [f[0] for f in mock.FLOWS if f[0] != CATALOGUE_FLOW]

    config = db.rpc("sh_setup", p_config=dict(minimal, platform="shopify", bucket_note="הערה", brand="DEMO",
                                              live_hosts=["live", "shop.example"]))
    assert config["screen"]["pathLabels"] == [["/collections/", "קטגוריה: "], ["/products/", "מוצר: "]]
    assert config["screen"]["hide"] == [] and config["screen"]["bucketNote"] == "הערה"
    assert config["screen"]["brand"] == "DEMO" and config["screen"]["liveHosts"] == ["live", "shop.example"]
    assert [r["flow_name"] for r in db.rpc("sh_health")] == [f[0] for f in mock.FLOWS]


def test_setup_again_changes_nothing_and_a_removed_page_keeps_its_history(db):
    first = db.setup()
    db.probe(T0, fail={"סל": 502})
    health = db.rpc("sh_health")
    assert db.setup() == first
    assert db.rpc("sh_health") == health                      # the proof of life survived

    smaller = example_config()
    smaller["pages"] = [p for p in smaller["pages"] if p["name"] != "סל"]
    config = db.rpc("sh_setup", p_config=smaller)
    assert [p["name"] for p in config["pages"]] == ["בית", "קטגוריה", "מוצר", "קופה"]
    assert (config["screen"]["probeCount"], config["screen"]["coreCount"]) == (3, 4)
    rows = db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1))
    assert [(r["page"], r["checks"], r["failed"]) for r in rows] == [
        ("בית", 1, 0), ("קטגוריה", 1, 0), ("מוצר", 1, 0), ("סל", 1, 1)]      # its history, after the configured pages


def _page(name="בית", url=SITE + "/", **flags):
    return dict(name=name, url=url, **flags)


@pytest.mark.parametrize("change, message", [
    ({"site": "example.co.il"}, '"site" must be an absolute http\\(s\\) address, got example.co.il'),
    ({"site": None}, '"site" must be an absolute http\\(s\\) address, got nothing'),
    ({"time_zone": "Mars/Olympus"}, 'unknown "time_zone" Mars/Olympus'),
    ({"platform": "wix"}, '"platform" must be woocommerce, shopify or other, got wix'),
    ({"down_after": 0}, '"down_after" must be 1 or more, got 0'),
    ({"morning": "7:30"}, '"morning" must be a time such as 07:30, got 7:30'),
    ({"live_hosts": "live"}, '"live_hosts" and "path_labels" must be lists'),
    ({"pages": None}, '"pages" must be a list of pages'),
    ({"pages": []}, 'exactly one page must have "home": true, found 0'),
    ({"pages": [_page(probe=True)]}, 'exactly one page must have "home": true, found 0'),
    ({"pages": [_page(home=True, probe=True), _page("ב", home=True)]}, 'exactly one page must have "home": true, found 2'),
    ({"pages": [_page(home=True)]}, 'at least one page must have "probe": true'),
    ({"pages": [_page(home=True), _page("ב", probe=True)]}, "the home page must be a probe page"),
    ({"pages": [_page(home=True, probe=True), _page(probe=True)]}, "page names must be unique"),
    ({"pages": [_page(home=True, probe=True), _page("")]}, 'every page needs a "name"'),
    ({"pages": [_page(home=True, probe=True), {"url": SITE + "/x/"}]}, 'every page needs a "name"'),
    ({"pages": [_page(home=True, probe=True), _page("ב", url="/cart/")]}, "absolute http\\(s\\) address: ב"),
    ({"pages": [_page(home=True, probe=True), _page("ב", url="ftp://example.co.il/")]}, "absolute http\\(s\\) address: ב"),
    ({"pages": [_page(home=True, probe=True), {"name": "ב"}]}, "absolute http\\(s\\) address: ב"),
])
def test_setup_refuses_a_bad_configuration_and_keeps_the_old_one(db, change, message):
    before = db.setup()
    fails_with(db, psycopg.errors.RaiseException, "sh_setup: .*" + message, "sh_setup", p_config=example_config(**change))
    assert db.rpc("sh_config") == before


# ================================================================ availability (§7.3)

def _ten_rounds(db):
    """Ten full rounds, one a minute from T0. סל fails twice; a light round fails everywhere."""
    for i in range(10):
        db.probe(T0 + mins(i), ms={"בית": 100 + 10 * i, "קטגוריה": 600, "מוצר": 300 + i,
                                    "סל": 800 if i == 3 else 10000 if i == 7 else 500 + i},
              fail={"סל": 502} if i == 3 else {"סל": "timeout"} if i == 7 else None)
        db.probe(T0 + mins(i) + secs(30), "light", fail=DEAD, ms=None)


def test_availability_per_page(db):
    db.setup()
    _ten_rounds(db)
    assert db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(10)) == [
        {"section": "לפי עמוד", "page": "בית", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 145, "p95_ms": 186, "last_fail_il": None},              # 185.5 rounds up
        {"section": "לפי עמוד", "page": "קטגוריה", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 600, "p95_ms": 600, "last_fail_il": None},
        {"section": "לפי עמוד", "page": "מוצר", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 305, "p95_ms": 309, "last_fail_il": None},
        # the percentiles are over the 8 checks that answered: 500 501 502 504 505 506 508 509
        {"section": "לפי עמוד", "page": "סל", "checks": 10, "failed": 2, "fail_pct": "20.00",
         "p50_ms": 505, "p95_ms": 509, "last_fail_il": "12.11 09:07"}]
    # the 38 answers of all pages together; the ten light rounds, dead on every page, changed nothing
    assert db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(10)) == [
        {"bucket": "2024-11-12 09:00", "checks": 40, "failed": 2, "ms_p50": 309, "ms_p95": 600}]


def test_availability_window_is_from_inclusive_to_exclusive(db):
    db.setup()
    _ten_rounds(db)
    cart = db.rpc("sh_availability", p_from=T0 + mins(3), p_to=T0 + mins(6))[3]       # rounds 3, 4, 5
    assert (cart["checks"], cart["failed"], cart["fail_pct"], cart["last_fail_il"]) == (3, 1, "33.33", "12.11 09:03")
    cart = db.rpc("sh_availability", p_from=T0 + mins(4), p_to=T0 + mins(7))[3]       # rounds 4, 5, 6
    assert (cart["checks"], cart["failed"], cart["fail_pct"], cart["last_fail_il"]) == (3, 0, "0.00", None)
    assert db.rpc("sh_availability", p_from=T0 + mins(10), p_to=T0 + mins(20)) == []
    # only light rounds in the window: they are not availability
    assert db.rpc("sh_availability", p_from=T0 + secs(30), p_to=T0 + secs(31)) == []
    assert db.rpc("sh_availability_series", p_from=T0 + secs(30), p_to=T0 + secs(31)) == []


def test_local_time_follows_the_configured_time_zone(db):
    db.setup(time_zone="America/New_York")
    _ten_rounds(db)
    assert db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(10))[3]["last_fail_il"] == "12.11 02:07"
    assert [r["bucket"] for r in db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(10))] == ["2024-11-12 02:00"]
    days = db.rpc("sh_availability_series", p_from=T0 - mins(60 * 100), p_to=T0 + mins(10))
    assert [r["bucket"] for r in days] == ["2024-11-12"]


def test_outages(db):
    db.setup()
    three_fail = {"קטגוריה": 502, "מוצר": 502, "סל": 502}
    plan = {1: DEAD, 2: DEAD,                               # two dead rounds: not an outage
            4: three_fail, 5: three_fail, 6: three_fail,    # some pages answered: not an outage
            8: DEAD, 9: DEAD, 10: DEAD,                     # three dead rounds: an outage
            43: DEAD, 44: DEAD, 45: DEAD, 46: DEAD}         # dead until the end of the window
    for i in list(range(12)) + list(range(42, 47)):         # minutes 12-41: the prober did not run at all
        db.probe(T0 + mins(i), fail=plan.get(i))
    outage = {"section": "נפילות", "outage_minutes": 3, "outage_start_il": "12.11 09:08", "outage_end_il": "12.11 09:11"}
    assert section(db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(47)), "נפילות") == [
        outage,
        # no round after the last dead one: it ends with the window
        {"section": "נפילות", "outage_minutes": 4, "outage_start_il": "12.11 09:43", "outage_end_il": "12.11 09:47"}]
    # the rows of the pages still come first
    assert [r["section"] for r in db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(47))] == ["לפי עמוד"] * 4 + ["נפילות"] * 2
    # only the rounds inside the window count
    assert section(db.rpc("sh_availability", p_from=T0 + mins(8), p_to=T0 + mins(12)), "נפילות") == [outage]
    assert section(db.rpc("sh_availability", p_from=T0 + mins(9), p_to=T0 + mins(12)), "נפילות") == []
    assert section(db.rpc("sh_availability", p_from=T0 + mins(12), p_to=T0 + mins(43)), "נפילות") == []


def test_an_outage_that_is_still_going_on_ends_now(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(4))
    for i in (3, 2, 1):
        db.probe(now - mins(i), fail=DEAD)
    assert section(db.rpc("sh_availability", p_from=now - mins(60), p_to=now + mins(1)), "נפילות") == [
        {"section": "נפילות", "outage_minutes": 3, "outage_start_il": il(now - mins(3)), "outage_end_il": il(now)}]


def test_an_outage_counts_dead_rounds_not_the_minutes_without_rounds(db):
    """SPEC §7.3 reads the rounds in order: two dead rounds, a pause of the prober, one more dead
    round are three consecutive dead rounds. The pause adds nothing to outage_minutes."""
    db.setup()
    for i, fail in [(0, DEAD), (1, DEAD), (30, DEAD), (31, None)]:
        db.probe(T0 + mins(i), fail=fail)
    assert section(db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(60)), "נפילות") == [
        {"section": "נפילות", "outage_minutes": 3, "outage_start_il": "12.11 09:00", "outage_end_il": "12.11 09:31"}]


def _two_hours(db):
    """09:00-09:59: three rounds. 10:00-10:59: two rounds, one with a failure. Then the two
    rounds around local midnight."""
    db.probe(T0, ms=100)
    db.probe(T0 + mins(1), ms=200)
    db.probe(T0 + mins(59), ms=300)
    db.probe(T0 + mins(60), ms=400)
    db.probe(T0 + mins(61), ms={"בית": 520, "קטגוריה": 540, "מוצר": 560, "סל": 9999}, fail={"סל": 502})
    db.probe(dt.datetime(2024, 11, 12, 21, 59, tzinfo=UTC), ms=300)      # 23:59 in Jerusalem
    db.probe(dt.datetime(2024, 11, 12, 22, 0, tzinfo=UTC), ms=300)       # 00:00 the next day


def test_availability_series_hourly_and_daily(db):
    db.setup()
    _two_hours(db)
    assert db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(120)) == [
        {"bucket": "2024-11-12 09:00", "checks": 12, "failed": 0, "ms_p50": 200, "ms_p95": 300},
        # the answers: 400 400 400 400 520 540 560; p95 = 540 + 0.7 * 20
        {"bucket": "2024-11-12 10:00", "checks": 8, "failed": 1, "ms_p50": 400, "ms_p95": 554}]
    assert db.rpc("sh_availability_series", p_from=T0 - mins(4 * 1440), p_to=T0 + mins(1440)) == [
        # the answers: 100x4 200x4 300x8 400x4 520 540 560; p95 = 520 + 0.9 * 20
        {"bucket": "2024-11-12", "checks": 24, "failed": 1, "ms_p50": 300, "ms_p95": 538},
        {"bucket": "2024-11-13", "checks": 4, "failed": 0, "ms_p50": 300, "ms_p95": 300}]


@pytest.mark.parametrize("window, bucket", [
    (mins(72 * 60), "2024-11-12 09:00"),
    (mins(72 * 60 + 1), "2024-11-12 09:00"),     # "h=72" as the server sends it: to = now + 1 minute
    (mins(72 * 60 + 59), "2024-11-12 09:00"),
    (mins(73 * 60), "2024-11-12"),
    (mins(168 * 60 + 1), "2024-11-12"),
])
def test_buckets_turn_daily_after_72_whole_hours(db, window, bucket):
    db.setup()
    db.probe(T0)
    db.run(T0)
    end = T0 + mins(1)
    assert [r["bucket"] for r in db.rpc("sh_availability_series", p_from=end - window, p_to=end)] == [bucket]
    assert [r["bucket"] for r in db.rpc("sh_speed_series", p_from=end - window, p_to=end, p_strategy="mobile")] == [bucket]


def test_the_hour_that_happens_twice_is_one_bucket_everywhere(db):
    """27.10.2024, Jerusalem: at 02:00 the clocks went back to 01:00."""
    db.setup()
    first, second = dt.datetime(2024, 10, 26, 22, 30, tzinfo=UTC), dt.datetime(2024, 10, 26, 23, 30, tzinfo=UTC)
    db.probe(dt.datetime(2024, 10, 26, 21, 0, tzinfo=UTC))              # 00:00 on the 27th
    db.probe(first)                                                      # 01:30, summer time
    db.probe(second, fail={"סל": 502})                                   # 01:30 again, winter time
    db.probe(dt.datetime(2024, 10, 27, 21, 59, tzinfo=UTC))             # 23:59 on the 27th
    db.probe(dt.datetime(2024, 10, 27, 22, 0, tzinfo=UTC))              # 00:00 on the 28th
    start = dt.datetime(2024, 10, 26, 20, 0, tzinfo=UTC)
    hourly = db.rpc("sh_availability_series", p_from=start, p_to=start + mins(30 * 60))
    assert [(r["bucket"], r["checks"], r["failed"]) for r in hourly] == [
        ("2024-10-27 00:00", 4, 0), ("2024-10-27 01:00", 8, 1), ("2024-10-27 23:00", 4, 0), ("2024-10-28 00:00", 4, 0)]
    assert [(r["page"], r["checks"], r["failed"]) for r in db.rpc("sh_drill_bucket", p_bucket="2024-10-27 01:00")] == [
        ("בית", 2, 0), ("קטגוריה", 2, 0), ("מוצר", 2, 0), ("סל", 2, 1)]
    assert [r["checks"] for r in db.rpc("sh_drill_bucket", p_bucket="2024-10-27")] == [4, 4, 4, 4]       # a day of 25 hours
    window = dict(p_from=start, p_to=start + mins(30 * 60))
    assert [r["at_il"] for r in db.rpc("sh_drill_fails", p_bucket="2024-10-27 01:00", **window)] == ["27.10 01:30"]
    assert db.rpc("sh_drill_fails", p_bucket="2024-10-27 00:00", **window) == []


# ================================================================ speed (§7.3)

def _speed_runs(db):
    for k, (lcp, score, cls, ttfb) in enumerate([(2000, 70, 0.01, 300), (2200, 66, 0.02, 310), (2400, 62, 0.03, 320),
                                                 (4100, 30, 0.04, 330), (5000, 20, 0.05, 340)]):
        newest = k == 4
        db.run(T0 + mins(15 * k), "בית", lcp, score=score, cls=cls, ttfb_ms=ttfb,
            crux_category="AVERAGE" if newest else "FAST", crux_lcp_ms=3100 if newest else 2000)
    db.run(T0 + mins(80), "בית", None, err="Lighthouse returned error: NO_FCP")       # failed: never counted
    db.run(T0, "בית", 1000, "desktop", score=90, cls=0, ttfb_ms=100)
    db.run(T0 + mins(60), "בית", 1200, "desktop", score=95, cls=0.01, ttfb_ms=121)
    db.run(T0, "קטגוריה", 3300, score=45, cls=0.1, ttfb_ms=500)
    db.run(T0 + mins(100), "קטגוריה", 3300)                                            # outside the window


def test_speed_core_pages_and_bottom_line(db):
    db.setup()
    _speed_runs(db)
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))
    assert [r["section"] for r in rows] == ["שורה תחתונה", "ליבה", "ליבה", "ליבה", "כיסוי"]
    assert section(rows, "שורה תחתונה") == [
        {"section": "שורה תחתונה", "page": "בית", "url": URL["בית"], "lcp_p50": 2400, "checks": 5, "verdict": "מהיר"}]
    assert section(rows, "ליבה") == [
        {"section": "ליבה", "strategy": "mobile", "page": "בית", "url": URL["בית"],
         "lcp_p50": 2400, "lcp_p95": 4820, "score_med": 62, "cls_med": 0.03, "ttfb_p50": 320,
         "slow_runs": 2, "checks": 5, "crux_category": "AVERAGE", "crux_lcp": 3100},       # crux: the newest run
        {"section": "ליבה", "strategy": "mobile", "page": "קטגוריה", "url": URL["קטגוריה"],
         "lcp_p50": 3300, "lcp_p95": 3300, "score_med": 45, "cls_med": 0.1, "ttfb_p50": 500,
         "slow_runs": 0, "checks": 1, "crux_category": None, "crux_lcp": None},
        {"section": "ליבה", "strategy": "desktop", "page": "בית", "url": URL["בית"],
         "lcp_p50": 1100, "lcp_p95": 1190, "score_med": 93, "cls_med": 0.005, "ttfb_p50": 111,
         "slow_runs": 0, "checks": 2, "crux_category": None, "crux_lcp": None}]


def test_speed_without_runs_still_has_its_bottom_line_and_coverage(db):
    db.setup()
    db.run(T0, "בית", None, err="timeout")
    assert db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90)) == [
        {"section": "שורה תחתונה", "page": "בית", "url": URL["בית"], "lcp_p50": None, "checks": 0, "verdict": None},
        {"section": "כיסוי", "checks": 0, "slow_runs": 0}]


@pytest.mark.parametrize("lcp, verdict", [(2000, "מצוין"), (2001, "מהיר"), (2500, "מהיר"), (2501, "בינוני"),
                                          (4000, "בינוני"), (4001, "איטי")])
def test_verdict_thresholds(db, lcp, verdict):
    db.setup()
    db.run(T0, "בית", lcp)
    db.run(T0 + mins(1), "בית", 9000, "desktop")           # the bottom line is the phone, always
    assert db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))[0]["verdict"] == verdict


def test_speed_heaviest_pages_and_coverage(db):
    db.setup()
    pages = [SITE + "/product/item-%02d/" % i for i in range(1, 13)]
    db.rpc("sh_sitemap_set", p_urls=pages + [SITE + "/about/", SITE + "/contact/", SITE + "/blog/"])
    for i, url in enumerate(pages, start=1):
        db.run(T0 + mins(i), url, 1000 * i, source="rotation", score=100 - 5 * i)
    db.run(T0 + mins(30), pages[11], 13000, source="rotation", score=20)        # a second run of the heaviest
    db.run(T0 + mins(31), pages[0], None, source="rotation", err="timeout")     # failed: not counted
    db.run(T0 + mins(32), pages[0], 99000, "desktop", source="rotation")        # not a phone run
    db.run(T0 + mins(33), "בית", 99000)                                          # a core run, not the rotation
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))
    heavy = section(rows, "האיטיים באתר")
    assert heavy[0] == {"section": "האיטיים באתר", "page": pages[11], "url": pages[11], "lcp_p50": 12500,
                        "score_med": 30, "checks": 2, "last_il": "12.11 09:30"}
    assert [(r["url"], r["lcp_p50"], r["score_med"], r["checks"], r["last_il"]) for r in heavy[1:]] == [
        (pages[i - 1], 1000 * i, 100 - 5 * i, 1, il(T0 + mins(i))) for i in range(11, 2, -1)]      # ten rows in all
    assert section(rows, "כיסוי") == [{"section": "כיסוי", "checks": 12, "slow_runs": 15}]
    # a page that left the sitemap is neither "a page of the site" nor "measured"
    db.rpc("sh_sitemap_set", p_urls=pages[1:] + [SITE + "/about/"])
    assert section(db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90)), "כיסוי") == [
        {"section": "כיסוי", "checks": 11, "slow_runs": 12}]


def test_speed_series(db):
    db.setup()
    db.run(T0, "בית", 2000)
    db.run(T0 + mins(15), "בית", 2400)
    db.run(T0 + mins(30), "בית", None, err="timeout")
    db.run(T0 + mins(60), "בית", 3000)
    db.run(T0, "קטגוריה", 3300)
    db.run(T0, "בית", 900, "desktop")
    db.run(T0 + mins(1), "בית", 8000, source="rotation")    # the rotation is not part of the core series
    home, category = {"page": "בית", "url": URL["בית"]}, {"page": "קטגוריה", "url": URL["קטגוריה"]}
    hours = dict(p_from=T0, p_to=T0 + mins(120))
    assert db.rpc("sh_speed_series", p_strategy="mobile", **hours) == [
        dict(home, bucket="2024-11-12 09:00", lcp_p50=2200), dict(home, bucket="2024-11-12 10:00", lcp_p50=3000),
        dict(category, bucket="2024-11-12 09:00", lcp_p50=3300)]
    assert db.rpc("sh_speed_series", p_strategy="desktop", **hours) == [dict(home, bucket="2024-11-12 09:00", lcp_p50=900)]
    assert db.rpc("sh_speed_series", p_from=T0 - mins(4 * 1440), p_to=T0 + mins(120), p_strategy="mobile") == [
        dict(home, bucket="2024-11-12", lcp_p50=2400), dict(category, bucket="2024-11-12", lcp_p50=3300)]


# ================================================================ health of the measuring (§7.3)

def test_health_lists_the_flows_of_the_spec_before_any_ran(db):
    db.setup()
    assert db.rpc("sh_health") == [
        {"flow_name": name, "status": "אין נתון", "cadence": cadence, "silent_txt": None, "last_at": None,
         "warn_minutes": warn, "late_minutes": late, "note": None} for name, cadence, warn, late in mock.FLOWS]


@pytest.mark.parametrize("name, ago, status, text", [
    (PROBE_FLOW, dict(minutes=5), "תקין", None),                                   # warn 5, late 15
    (PROBE_FLOW, dict(minutes=5, seconds=1), "מתעכב", "מאחר ב-1 דקות"),
    (PROBE_FLOW, dict(minutes=15), "מתעכב", "מאחר ב-10 דקות"),
    (PROBE_FLOW, dict(minutes=15, seconds=1), "שקט", "שקט כבר 15 דקות"),
    (RUM_FLOW, dict(minutes=400), "שקט", "שקט כבר 6 שעות"),                        # warn 120, late 360
    (CERT_FLOW, dict(minutes=1560 + 180), "מתעכב", "מאחר ב-3 שעות"),               # warn 1560, late 2880
    (CERT_FLOW, dict(days=3, hours=5), "שקט", "שקט כבר 3 ימים"),
])
def test_health_status_by_the_age_of_the_last_run(db, name, ago, status, text):
    db.setup()
    db.ran(name, **ago)
    row = flow(db, name)
    assert (row["status"], row["silent_txt"]) == (status, text)
    assert dt.datetime.fromisoformat(row["last_at"]) == db.now() - dt.timedelta(**ago)


# ================================================================ sh_now (§5.3)

def test_now_on_a_fresh_install(db, monkeypatch):
    db.setup()
    assert db.rpc("sh_now") == {
        "pages": [], "latest": [], "light": False, "all_ok": False, "any_ok": False, "age_sec": None,
        "rum": {"n": 0, "p75_ms": None}, "speed": {}, "alerts_open": 0, "rum_src": None}
    monkeypatch.setitem(mock.STATE, "scenario", "empty")
    assert db.rpc("sh_now") == mock.api_now("owner")                      # to the letter what the mock answers


def test_now_pages_come_from_the_full_round_and_the_state_from_the_latest_round(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(132), fail=DEAD)                                             # an older round: ignored
    db.probe(now - secs(72), ms={"בית": 240, "קטגוריה": 690, "מוצר": 310, "סל": 1700}, fail={"מוצר": 503})
    db.probe(now - secs(12), "light", ms=None, fail={"סל": "timeout"})
    state = db.rpc("sh_now")
    assert state["pages"] == [
        {"page": "בית", "url": URL["בית"], "ok": True, "status": 200, "ms": 240},
        {"page": "קטגוריה", "url": URL["קטגוריה"], "ok": True, "status": 200, "ms": 690},
        {"page": "מוצר", "url": URL["מוצר"], "ok": False, "status": 503, "ms": None},       # it did not answer: no time
        {"page": "סל", "url": URL["סל"], "ok": True, "status": 200, "ms": 1700}]
    assert state["latest"] == [{"page": "בית", "ok": True}, {"page": "קטגוריה", "ok": True},
                               {"page": "מוצר", "ok": True}, {"page": "סל", "ok": False}]
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (True, False, True, 12)

    db.probe(now - secs(2), fail=DEAD)                                               # a full round is now the latest
    state = db.rpc("sh_now")
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (False, False, False, 2)
    assert [p["ok"] for p in state["pages"]] == [False] * 4

    db.probe(now, "light", ms=None)
    state = db.rpc("sh_now")
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (True, True, True, 0)


def test_now_forgets_rounds_older_than_15_minutes(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(15))
    db.probe(now - mins(14), "light", ms=None)
    state = db.rpc("sh_now")
    assert (len(state["pages"]), len(state["latest"]), state["light"], state["age_sec"]) == (4, 4, True, 840)
    db.sql("update sh_probe set round_at = round_at - interval '1 second'")           # 15:01 and 14:01 old
    state = db.rpc("sh_now")
    assert (state["pages"], len(state["latest"]), state["light"], state["age_sec"]) == ([], 4, True, 841)
    db.sql("update sh_probe set round_at = round_at - interval '1 minute'")           # both too old
    state = db.rpc("sh_now")
    assert (state["pages"], state["latest"], state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (
        [], [], False, False, False, None)


def test_now_real_users(db):
    db.setup()
    views = [{"site": "live", "path": "/", "lcp_ms": lcp, "is_test": False} for lcp in (1000, 2000, 3000)]
    views += [{"site": "live", "path": "/", "lcp_ms": 60000, "is_test": True},
              {"site": "staging.example.co.il", "path": "/", "lcp_ms": 50000, "is_test": False}]
    assert db.rpc("sh_rum_add", p_rows=views) == {"n": 5}
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) values"
           " (now() - interval '60 minutes', 'live', '/', 4000), (now() - interval '61 minutes', 'live', '/', 55000)")
    state = db.rpc("sh_now")
    assert state["rum"] == {"n": 4, "p75_ms": 3250}           # 1000 2000 3000 4000: the last hour, live, not test
    assert state["rum_src"] == {"n": 7, "hosts": [{"host": "live", "n": 6}, {"host": "staging.example.co.il", "n": 1}],
                                "cols": ["created_at", "is_test", "lcp_ms", "path", "site"], "test": 1}

    db.setup(live_hosts=["live", "staging.example.co.il"])
    assert db.rpc("sh_now")["rum"] == {"n": 5, "p75_ms": 4000}
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms)"
           " select now() - interval '2 hours', 'old.example.co.il', '/', 1000 from generate_series(1, 1200)")
    assert db.rpc("sh_now")["rum_src"]["n"] == 1000           # where the newest 1000 came from
    assert db.rpc("sh_now")["rum_src"]["hosts"][0] == {"host": "old.example.co.il", "n": 993}


def test_now_lab_speed_and_open_alerts(db):
    db.setup()
    now = db.now()
    db.run(now - mins(40), "בית", 2500, score=63)
    db.run(now - mins(25), "בית", 2700, score=60)
    db.run(now - mins(10), "בית", None, err="timeout")
    db.run(now - mins(5), "בית", 900, "desktop", score=99)
    db.run(now - mins(1), "קטגוריה", 3300, score=40)
    state = db.rpc("sh_now")
    assert state["speed"]["lcp_ms"] == 2700 and state["speed"]["score"] == 60
    assert dt.datetime.fromisoformat(state["speed"]["checked_at"]) == now - mins(25)
    assert set(state["speed"]) == {"lcp_ms", "score", "checked_at"}

    db.probe(now - secs(5), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")
    assert db.rpc("sh_now")["alerts_open"] == 2


# ================================================================ drill-downs (§5.4)

def test_drill_fails(db):
    db.setup()
    db.probe(T0, fail={"סל": 502}, ms={"סל": 812})
    db.probe(T0 + secs(30), "light", fail=DEAD, ms=None)                # a light round is not listed
    db.probe(T0 + mins(1), fail={"בית": "timeout"}, ms={"בית": 10000})
    db.rpc("sh_probe_add", p_round_at=T0 + mins(2), p_kind="full", p_rows=[
        {"page": "קטגוריה", "url": URL["קטגוריה"], "ok": False, "fail": "connect", "err": "connection reset by peer"},
        {"page": "מוצר", "url": URL["מוצר"], "ok": False, "status": 200, "ms": 420, "fail": "content"}])
    db.probe(T0 + mins(61), fail={"סל": 500}, ms={"סל": 95})
    everything = [
        {"at_il": "12.11 10:01", "page": "סל", "kind": "קוד 500", "err": None, "ms": 95},
        {"at_il": "12.11 09:02", "page": "מוצר", "kind": "תוכן לא צפוי", "err": None, "ms": 420},
        {"at_il": "12.11 09:02", "page": "קטגוריה", "kind": "שגיאת חיבור", "err": "connection reset by peer", "ms": None},
        {"at_il": "12.11 09:01", "page": "בית", "kind": "לא ענה בזמן", "err": None, "ms": 10000},
        {"at_il": "12.11 09:00", "page": "סל", "kind": "קוד 502", "err": None, "ms": 812}]
    window = dict(p_from=T0, p_to=T0 + mins(120))
    assert db.rpc("sh_drill_fails", **window) == everything
    assert db.rpc("sh_drill_fails", p_page="", p_bucket="", **window) == everything       # as the screen sends them
    assert db.rpc("sh_drill_fails", p_page="סל", **window) == [everything[0], everything[4]]
    assert db.rpc("sh_drill_fails", p_bucket="2024-11-12 09:00", **window) == everything[1:]
    assert db.rpc("sh_drill_fails", p_bucket="2024-11-12", **window) == everything
    assert db.rpc("sh_drill_fails", p_page="סל", p_bucket="2024-11-12 10:00", **window) == [everything[0]]
    assert db.rpc("sh_drill_fails", p_from=T0 + mins(1), p_to=T0 + mins(2)) == [everything[3]]


def test_drill_fails_returns_the_newest_500(db):
    db.setup()
    db.sql("insert into sh_probe (round_at, kind, page, url, ok, status, fail)"
           " select %s + n * interval '1 minute', 'full', 'סל', 'u', false, 502, 'http' from generate_series(1, 510) n", [T0])
    rows = db.rpc("sh_drill_fails", p_from=T0, p_to=T0 + mins(600))
    assert len(rows) == 500
    assert (rows[0]["at_il"], rows[-1]["at_il"]) == (il(T0 + mins(510)), il(T0 + mins(11)))


def test_drill_bucket(db):
    db.setup()
    db.probe(T0, ms={"בית": 100, "סל": 500, "קטגוריה": 400, "מוצר": 400})
    db.probe(T0 + mins(17), ms={"בית": 1900, "סל": 520, "קטגוריה": 400, "מוצר": 400})
    db.probe(T0 + mins(30), ms={"בית": 290, "סל": 5000, "קטגוריה": 400, "מוצר": 400}, fail={"סל": 502})
    db.probe(T0 + mins(30) + secs(30), "light", fail=DEAD, ms=None)
    db.probe(T0 + mins(60), ms=700, fail={"סל": "timeout"})
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 09:00") == [
        {"page": "בית", "checks": 3, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "12.11 09:17"},
        {"page": "קטגוריה", "checks": 3, "failed": 0, "ms_p50": 400, "ms_max": 400, "worst_il": "12.11 09:00"},
        {"page": "מוצר", "checks": 3, "failed": 0, "ms_p50": 400, "ms_max": 400, "worst_il": "12.11 09:00"},
        # the failed check took 5000 ms, and that is not a response time
        {"page": "סל", "checks": 3, "failed": 1, "ms_p50": 510, "ms_max": 520, "worst_il": "12.11 09:17"}]
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 10:00")[3] == {
        "page": "סל", "checks": 1, "failed": 1, "ms_p50": None, "ms_max": None, "worst_il": None}
    assert [(r["page"], r["checks"], r["failed"], r["ms_max"]) for r in db.rpc("sh_drill_bucket", p_bucket="2024-11-12")] == [
        ("בית", 4, 0, 1900), ("קטגוריה", 4, 0, 700), ("מוצר", 4, 0, 700), ("סל", 4, 2, 520)]
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 11:00") == []


def test_drill_runs(db):
    db.setup()
    opps = [{"id": "render-blocking-resources", "title": "Eliminate render-blocking resources", "ms": 600}]
    db.run(T0, "בית", 2400, score=64, ttfb_ms=410, bytes=3400000, cls=0.03, crux_category="FAST", crux_lcp_ms=2100, opps=opps)
    db.run(T0 + mins(15), "בית", None, err="Lighthouse returned error: NO_FCP")
    db.run(T0 + mins(60), "בית", 2600)
    db.run(T0, "בית", 900, "desktop")
    db.run(T0, "קטגוריה", 3300)
    first = {"ok": True, "err": None, "at_il": "12.11 09:00", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410,
             "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": opps}
    failed = {"ok": False, "err": "Lighthouse returned error: NO_FCP", "at_il": "12.11 09:15"}
    last = {"ok": True, "err": None, "at_il": "12.11 10:00", "lcp_ms": 2600, "score": None, "ttfb_ms": None,
            "bytes": None, "cls": None, "crux_category": None, "crux_lcp_ms": None, "opps": []}
    window = dict(p_from=T0, p_to=T0 + mins(120), p_url=URL["בית"])
    assert db.rpc("sh_drill_runs", **window) == [last, failed, first]                       # phone unless told otherwise
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="", **window) == [last, failed, first]
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="2024-11-12 09:00", **window) == [failed, first]
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="2024-11-12", **window) == [last, failed, first]
    assert [r["lcp_ms"] for r in db.rpc("sh_drill_runs", p_strategy="desktop", **window)] == [900]
    assert db.rpc("sh_drill_runs", p_from=T0 + mins(1), p_to=T0 + mins(60), p_url=URL["בית"]) == [failed]
    assert db.rpc("sh_drill_runs", p_from=T0, p_to=T0 + mins(120), p_url=SITE + "/nothing/") == []


def test_drill_alert(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(10), fail={"סל": 500})                         # an earlier blip, answered since
    db.probe(now - mins(5))
    db.probe(now - mins(4), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")
    # as if the check had run right after that round, not at the frozen "now" of this test
    db.sql("update sh_alerts set opened_at = now() - interval '3 minutes 50 seconds'")
    db.probe(now - mins(4) + secs(30), "light", fail={"סל": "timeout", "מוצר": 502}, ms=None)
    db.probe(now - mins(3), fail={"סל": 502, "מוצר": 502})
    db.probe(now - mins(2), fail={"מוצר": 502})
    for message in db.rpc("sh_alerts_check"):
        db.rpc("sh_message_sent", p_id=message["id"], p_status=200)
    cart, product = sorted(db.rpc("sh_alerts_range", p_from=now - mins(60), p_to=now + mins(1)), key=lambda a: a["open"])
    assert (cart["title"], cart["open"], product["title"], product["open"]) == (
        "האתר לא עונה: סל", False, "האתר לא עונה: מוצר", True)

    assert db.rpc("sh_drill_alert", p_id=cart["id"]) == [dict(
        cart,
        fails=[{"at": il(now - mins(4)), "page": "סל", "status": 502, "err": None},
               {"at": il(now - mins(4) + secs(30)), "page": "סל", "status": None, "err": "לא ענה בזמן"},
               {"at": il(now - mins(3)), "page": "סל", "status": 502, "err": None}],
        sent=[{"event": "open", "status": 200, "at": il(now)}, {"event": "close", "status": 200, "at": il(now)}])]
    assert cart == {"id": cart["id"], "kind": "down", "title": "האתר לא עונה: סל", "body": "קוד 502\n" + URL["סל"],
                    "open": False, "opened_il": il(now - secs(230)), "closed_il": il(now), "minutes": 3}
    detail = db.rpc("sh_drill_alert", p_id=product["id"])[0]
    assert len(detail["fails"]) == 4 and detail["sent"] == [{"event": "open", "status": 200, "at": il(now)}]
    assert db.rpc("sh_drill_alert", p_id=cart["id"] + 1000) == []

    db.ran(CORE_FLOW, minutes=95)                                      # an alert of another kind has no failed checks
    db.rpc("sh_alerts_check")
    silent = db.rpc("sh_alerts_open")[0]
    assert silent["kind"] == "silent"
    detail = db.rpc("sh_drill_alert", p_id=silent["id"])[0]
    assert (detail["fails"], detail["sent"]) == ([], [])                # its push is still owed


# ================================================================ alert rules (§7.8)

def _open(db):
    return [(a["kind"], a["title"]) for a in db.rpc("sh_alerts_open")]


def _pushes(db):
    """The owed pushes, without their ids."""
    return [{k: v for k, v in m.items() if k != "id"} for m in db.rpc("sh_alerts_check")]


def test_down_alert_opens_on_the_first_failed_check_and_closes_on_the_next_answer(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(60))
    assert db.rpc("sh_alerts_check") == [] and db.rpc("sh_alerts_open") == []

    db.probe(now - secs(30), "light", fail={"סל": 502}, ms=None)                 # a light round is enough
    opening = {"title": "האתר לא עונה: סל", "msg": "קוד 502\n" + URL["סל"], "priority": 4, "click": None,
               "kind": "התראה", "event": "open"}
    assert _pushes(db) == [opening]
    alert = db.rpc("sh_alerts_open")
    assert alert == [{"id": alert[0]["id"], "kind": "down", "title": "האתר לא עונה: סל",
                      "body": "קוד 502\n" + URL["סל"], "opened_il": il(now), "acked": False}]

    db.probe(now - secs(20), fail={"סל": "timeout"})                             # still down: nothing new
    assert _pushes(db) == [opening]
    assert db.rpc("sh_alerts_open") == alert
    assert db.sql("select count(*) from sh_alerts") == [(1,)] and db.sql("select count(*) from sh_messages") == [(1,)]

    db.sql("update sh_alerts set opened_at = now() - interval '7 minutes 30 seconds'")
    db.probe(now - secs(10), "light", ms=None)                                   # it answered
    assert _pushes(db) == [opening, {"title": "האתר לא עונה: סל", "msg": "נמשך 7 דקות", "priority": 2,
                                     "click": None, "kind": "חזר לתקין", "event": "close"}]
    assert db.rpc("sh_alerts_open") == []
    assert db.sql("select count(*) from sh_alerts where closed_at = now()") == [(1,)]

    db.rpc("sh_alerts_check")                                                     # nothing to close twice
    assert db.sql("select count(*) from sh_messages") == [(2,)]


def test_a_problem_that_comes_back_is_a_new_alert_that_nobody_has_seen(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(50), fail={"סל": "connect"})
    db.rpc("sh_alerts_check")
    first = db.rpc("sh_alerts_open")[0]
    assert first["body"] == "שגיאת חיבור\n" + URL["סל"]
    assert db.rpc("sh_alert_ack", p_ids=[first["id"]], p_who="owner") == {"n": 1}
    assert db.rpc("sh_alerts_open")[0]["acked"] is True
    db.probe(now - secs(40))
    db.rpc("sh_alerts_check")
    db.probe(now - secs(30), fail={"סל": "content"})
    db.rpc("sh_alerts_check")
    second = db.rpc("sh_alerts_open")
    assert len(second) == 1 and second[0]["id"] != first["id"]
    assert (second[0]["acked"], second[0]["body"]) == (False, "תוכן לא צפוי\n" + URL["סל"])
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["open", "close", "open"]


def test_down_after_2_waits_for_two_failed_rounds_in_a_row(db):
    db.setup(down_after=2)
    now = db.now()
    db.probe(now - secs(120), fail={"סל": 502})                  # the only round so far
    assert db.rpc("sh_alerts_check") == []
    db.probe(now - secs(90), "light", ms=None)
    db.probe(now - secs(60), fail={"סל": 502})                   # failed, answered, failed: not in a row
    assert db.rpc("sh_alerts_check") == []
    db.probe(now - secs(30), "light", fail={"סל": "timeout"}, ms=None)
    assert _pushes(db) == [{"title": "האתר לא עונה: סל", "msg": "לא ענה בזמן\n" + URL["סל"], "priority": 4,
                            "click": None, "kind": "התראה", "event": "open"}]
    db.probe(now - secs(20), fail={"סל": 502})
    assert _open(db) == [("down", "האתר לא עונה: סל")] and len(db.rpc("sh_alerts_check")) == 1
    db.probe(now - secs(10), "light", ms=None)                   # one answer closes it
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["open", "close"] and _open(db) == []


def test_down_alert_needs_a_recent_round_and_a_configured_page(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(1441), fail={"סל": 502})
    db.rpc("sh_alerts_check")
    # a failure from before yesterday says nothing about the page now; what is wrong now is the prober
    assert _open(db) == [("silent", "המדידה נעצרה: " + PROBE_FLOW)]
    db.sql("update sh_alerts set opened_at = now() - interval '1 minute'")       # the test's clock stands still
    db.probe(now - secs(30), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")
    assert sorted(_open(db)) == [("down", "האתר לא עונה: מוצר"), ("down", "האתר לא עונה: סל")]
    db.sql("update sh_probe set round_at = round_at - interval '2 days'")
    db.rpc("sh_alerts_check")                                     # no round since: no news, both stay open
    assert sorted(_open(db)) == [("down", "האתר לא עונה: מוצר"), ("down", "האתר לא עונה: סל")]
    smaller = example_config()
    smaller["pages"] = [p for p in smaller["pages"] if p["name"] != "סל"]
    db.rpc("sh_setup", p_config=smaller)
    db.rpc("sh_alerts_check")                                     # a page that is no longer probed can never answer
    assert _open(db) == [("down", "האתר לא עונה: מוצר")]


def test_slow_alert(db):
    db.setup()
    now = db.now()
    db.run(now - mins(30), "קטגוריה", 4100)
    assert db.rpc("sh_alerts_check") == []                        # once is not twice in a row
    db.run(now - mins(15), "קטגוריה", 4600)
    db.run(now - mins(30), "מוצר", 5000)                         # slow, then fast enough
    db.run(now - mins(15), "מוצר", 3900)
    db.run(now - mins(30), "סל", 4000)                           # 4000 is not above 4000
    db.run(now - mins(15), "סל", 4000)
    db.run(now - mins(30), "בית", 9000, "desktop")               # the rule is about the phone
    db.run(now - mins(15), "בית", 9000, "desktop")
    db.run(now - mins(30), "קופה", 3000)
    db.run(now - mins(15), "קופה", 5000)                         # only the newest is slow
    assert _pushes(db) == [{"title": "עמוד איטי: קטגוריה", "msg": "4.6 שניות עד התוכן, פעמיים ברצף\n" + URL["קטגוריה"],
                            "priority": 3, "click": None, "kind": "התראה", "event": "open"}]
    assert _open(db) == [("slow", "עמוד איטי: קטגוריה")]

    db.run(now - mins(10), "קטגוריה", None, err="timeout")       # a failed run is not a measurement
    db.run(now - mins(9), "קטגוריה", 1000, "desktop")
    db.rpc("sh_alerts_check")
    assert _open(db) == [("slow", "עמוד איטי: קטגוריה")]
    db.run(now - mins(5), "קופה", 5100)                          # now twice in a row
    db.run(now - mins(5), "קטגוריה", 4000)                       # and this one recovered
    assert sorted((m["event"], m["title"], m["priority"]) for m in db.rpc("sh_alerts_check")) == [
        ("close", "עמוד איטי: קטגוריה", 2), ("open", "עמוד איטי: קופה", 3), ("open", "עמוד איטי: קטגוריה", 3)]
    assert db.rpc("sh_alerts_open")[0]["body"] == "5.1 שניות עד התוכן, פעמיים ברצף\n" + URL["קופה"]


def test_silent_alert(db):
    db.setup()
    db.ran(PROBE_FLOW, minutes=15)                               # exactly its late_minutes: not yet silent
    db.ran(ROTATION_FLOW, minutes=59)
    assert db.rpc("sh_alerts_check") == [] and db.rpc("sh_alerts_open") == []      # the other flows never ran
    db.ran(CORE_FLOW, minutes=95, seconds=30)
    assert _pushes(db) == [{"title": "המדידה נעצרה: " + CORE_FLOW, "msg": "אין מדידה כבר 95 דקות", "priority": 4,
                            "click": None, "kind": "התראה", "event": "open"}]
    assert _open(db) == [("silent", "המדידה נעצרה: " + CORE_FLOW)]
    assert flow(db, CORE_FLOW)["status"] == "שקט"                 # the screen and the alert agree

    db.run(db.now(), "בית", 2400)                                # it ran again
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["open", "close"] and _open(db) == []


def test_silent_alert_ignores_a_disabled_flow_and_closes_when_its_flow_is_disabled(db):
    db.setup()
    db.ran(CATALOGUE_FLOW, days=3)
    db.rpc("sh_alerts_check")
    assert _open(db) == [("silent", "המדידה נעצרה: " + CATALOGUE_FLOW)]
    db.setup(platform="other")                                    # no catalogue any more
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["open", "close"] and _open(db) == []
    db.rpc("sh_alerts_check")
    assert db.sql("select count(*) from sh_alerts") == [(1,)]


def test_silent_alert_opened_early_by_the_independent_check_stays_until_the_flow_runs_again(db):
    """SPEC §7.10: sh_deadman opens this alert when the newest round is 10 minutes old, before
    the flow's own 15 minutes."""
    db.setup()
    now = db.now()
    db.probe(now - mins(11))
    db.sql("insert into sh_alerts (key, kind, title, body, opened_at) values (%s, 'silent', %s, 'אין מדידה כבר 10 דקות', %s)",
           ["silent:" + PROBE_FLOW, "המדידה נעצרה: " + PROBE_FLOW, now - mins(1)])
    assert db.rpc("sh_alerts_check") == [] and len(_open(db)) == 1          # 11 minutes: not closed, not opened twice
    db.sql("update sh_flows set last_at = now() - interval '16 minutes' where flow_name = %s", [PROBE_FLOW])
    assert db.rpc("sh_alerts_check") == [] and len(_open(db)) == 1          # 16 minutes: still the same alert
    db.probe(now - secs(30))
    assert [(m["event"], m["msg"]) for m in db.rpc("sh_alerts_check")] == [("close", "נמשך 1 דקות")]
    assert _open(db) == []


def _cert(db, days, ok=True, err=None):
    return db.rpc("sh_cert_set", p_row={"host": "example.co.il", "issuer": "Let's Encrypt R11", "ok": ok, "err": err,
                                        "days_left": days, "not_before": "2024-09-01T00:00:00Z",
                                        "not_after": "2024-11-30T00:00:00Z"})


def test_cert_alert(db):
    db.setup()
    _cert(db, 14)
    assert db.rpc("sh_alerts_check") == []
    _cert(db, 13)
    assert _pushes(db) == [{"title": "תעודת האבטחה פגה בעוד 13 ימים", "msg": "example.co.il", "priority": 3,
                            "click": None, "kind": "התראה", "event": "open"}]
    _cert(db, None, ok=False, err="handshake failed")             # a failed check proves nothing either way
    db.rpc("sh_alerts_check")
    assert _open(db) == [("cert", "תעודת האבטחה פגה בעוד 13 ימים")]
    db.rpc("sh_cert_set", p_row={"host": "other.example", "ok": True, "days_left": 3})      # not the configured host
    db.rpc("sh_alerts_check")
    assert len(_open(db)) == 1
    _cert(db, 89)
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["open", "close"] and _open(db) == []


def test_ack_marks_only_open_alerts_that_nobody_marked(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(50), fail={"סל": 502, "מוצר": 502, "בית": 502})
    db.rpc("sh_alerts_check")
    db.probe(now - secs(40), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")                                     # the alert of בית is closed now
    ids = {title: i for i, title in db.sql("select id, title from sh_alerts")}
    home, cart, product = ids["האתר לא עונה: בית"], ids["האתר לא עונה: סל"], ids["האתר לא עונה: מוצר"]

    assert db.rpc("sh_alert_ack", p_ids=[cart, home, 999999], p_who="owner") == {"n": 1}
    assert {a["id"]: a["acked"] for a in db.rpc("sh_alerts_open")} == {cart: True, product: False}
    assert db.rpc("sh_alert_ack", p_ids=[cart, product], p_who="staff") == {"n": 1}       # סל keeps its first mark
    assert db.sql("select id, acked_by, acked_at = now() from sh_alerts where acked_at is not null order by id") == sorted(
        [(cart, "owner", True), (product, "staff", True)])
    assert db.rpc("sh_alert_ack", p_ids=[], p_who="owner") == {"n": 0}
    assert len(db.rpc("sh_alerts_open")) == 2 and db.rpc("sh_now")["alerts_open"] == 2    # marked is not closed


def test_alerts_range_lists_what_was_open_inside_the_window(db):
    db.setup()
    now = db.now()
    db.sql("insert into sh_alerts (key, kind, title, body, opened_at, closed_at) values"
           " ('down:סל', 'down', 'א', 'גוף', %s, %s), ('ops:x', 'ops', 'ב', null, %s, null),"
           " ('down:סל', 'down', 'ג', '', %s, %s)",
           [T0, T0 + mins(10), T0 + mins(30), T0 + mins(100), T0 + mins(101) + secs(59)])

    def titles(start, end):
        return [a["title"] for a in db.rpc("sh_alerts_range", p_from=T0 + mins(start), p_to=T0 + mins(end))]

    assert titles(-60, 200) == ["ג", "ב", "א"]                    # newest first
    assert titles(10, 30) == ["א"]                                # closed at the first instant of the window
    assert titles(11, 30) == []
    assert titles(11, 31) == ["ב"]
    assert titles(150, 200) == ["ב"]                              # still open
    first, second = db.rpc("sh_alerts_range", p_from=T0, p_to=T0 + mins(50))[::-1]
    assert first == {"id": first["id"], "kind": "down", "title": "א", "body": "גוף", "open": False,
                     "opened_il": "12.11 09:00", "closed_il": "12.11 09:10", "minutes": 10}
    assert second == {"id": second["id"], "kind": "ops", "title": "ב", "body": None, "open": True,
                      "opened_il": "12.11 09:30", "closed_il": None,
                      "minutes": int((now - T0 - mins(30)).total_seconds() // 60)}
    assert db.rpc("sh_alerts_range", p_from=T0 + mins(100), p_to=T0 + mins(101))[0]["minutes"] == 1


def test_a_push_is_retried_five_times_and_then_given_up(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(30), fail={"סל": 502, "מוצר": 502})
    owed = {m["title"]: m["id"] for m in db.rpc("sh_alerts_check")}
    cart, product = owed["האתר לא עונה: סל"], owed["האתר לא עונה: מוצר"]

    assert db.rpc("sh_message_sent", p_id=cart, p_status=204) == {"n": 1}         # any 2xx is "sent"
    assert db.rpc("sh_message_sent", p_id=cart, p_status=500) == {"n": 0}         # settled: nothing more to record
    for attempt in range(1, 5):
        assert db.rpc("sh_message_sent", p_id=product, p_status=0 if attempt == 1 else 503) == {"n": 1}
        assert [m["id"] for m in db.rpc("sh_alerts_check")] == [product]          # still owed
        assert db.sql("select status, attempts from sh_messages where id = %s", [product]) == [(None, attempt)]
    assert db.rpc("sh_message_sent", p_id=product, p_status=429) == {"n": 1}      # the fifth failure is the last
    assert db.rpc("sh_alerts_check") == []
    assert db.sql("select id, status, attempts from sh_messages order by id") == sorted([(cart, 204, 1), (product, 429, 5)])
    assert {m["title"]: m["sent"] for m in db.rpc("sh_messages", p_from=now, p_to=now + mins(1))} == {
        "האתר לא עונה: סל": True, "האתר לא עונה: מוצר": False}
    assert db.rpc("sh_message_sent", p_id=cart + product, p_status=200) == {"n": 0}       # no such message


def test_messages_log_is_newest_first_and_inside_the_window(db):
    db.setup()
    db.sql("insert into sh_messages (at, event, kind, title, msg, priority, status) values"
           " (%s, 'open', 'התראה', 'א', 'גוף', 4, 200), (%s, 'close', 'חזר לתקין', 'א', 'נמשך 7 דקות', 2, null),"
           " (%s, 'morning', 'בוקר', 'ב', null, 2, 500)", [T0, T0 + mins(7), T0 + mins(60)])
    assert db.rpc("sh_messages", p_from=T0, p_to=T0 + mins(61)) == [
        {"kind": "בוקר", "title": "ב", "msg": None, "at_il": "12.11 10:00", "sent": False},
        {"kind": "חזר לתקין", "title": "א", "msg": "נמשך 7 דקות", "at_il": "12.11 09:07", "sent": False},
        {"kind": "התראה", "title": "א", "msg": "גוף", "at_il": "12.11 09:00", "sent": True}]
    assert [m["at_il"] for m in db.rpc("sh_messages", p_from=T0 + mins(1), p_to=T0 + mins(60))] == ["12.11 09:07"]


def test_morning_message_is_queued_once_a_day(db):
    db.setup()
    now = db.now()
    for i in range(10, 0, -1):
        db.probe(now - mins(i), fail={"סל": 502} if i == 6 else None)
    db.run(now - mins(20), "בית", 2300)
    today = now.astimezone(TZ).date()
    assert db.rpc("sh_morning", p_day=today) == {"n": 1}
    assert db.rpc("sh_morning", p_day=today) == {"n": 0}
    assert db.rpc("sh_job_due", p_job="morning", p_day=today) is False
    assert _pushes(db) == [{"title": "בוקר טוב: האתר תקין", "msg": "זמינות 97.50% ב-24 שעות\nמהירות עמוד הבית: מהיר",
                            "priority": 2, "click": None, "kind": "בוקר", "event": "morning"}]
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1)) == [
        {"kind": "בוקר", "title": "בוקר טוב: האתר תקין", "msg": "זמינות 97.50% ב-24 שעות\nמהירות עמוד הבית: מהיר",
         "at_il": il(now), "sent": False}]
    assert db.rpc("sh_morning", p_day=today + dt.timedelta(days=1)) == {"n": 1}
    assert db.sql("select count(*) from sh_messages where event = 'morning'") == [(2,)]


@pytest.mark.parametrize("dead_rounds, failing_now, title, lines", [
    (0, [], "בוקר טוב: האתר תקין", ["זמינות 100.0% ב-24 שעות"]),
    (3, ["סל"], "בוקר טוב: התראה פתוחה אחת", ["זמינות 76.92% ב-24 שעות", "נפילות: 1 (3 דקות)"]),
    (4, ["סל", "מוצר"], "בוקר טוב: 2 התראות פתוחות", ["זמינות 71.43% ב-24 שעות", "נפילות: 1 (4 דקות)"]),
])
def test_morning_message_text(db, dead_rounds, failing_now, title, lines):
    db.setup()
    now = db.now()
    for i in range(10 + dead_rounds, 10, -1):
        db.probe(now - mins(i), fail=DEAD)
    for i in range(10, 0, -1):
        db.probe(now - mins(i))
    if failing_now:
        db.probe(now - secs(30), "light", fail=dict.fromkeys(failing_now, 502), ms=None)
        db.rpc("sh_alerts_check")
    db.rpc("sh_morning", p_day=now.date())
    assert db.sql("select title, msg from sh_messages where event = 'morning'") == [(title, "\n".join(lines))]


def test_morning_message_without_any_measurement(db):
    db.setup()
    db.rpc("sh_morning", p_day=db.now().date())
    assert db.sql("select title, msg, priority, kind from sh_messages") == [
        ("בוקר טוב: האתר תקין", "אין בדיקות זמינות ב-24 שעות", 2, "בוקר")]


def test_alerts_check_from_many_sessions_at_once_opens_each_alert_once(committed):
    db = committed()
    db.setup()
    db.probe(db.now() - secs(5), fail=DEAD)
    sessions = [committed() for _ in range(8)]
    start = threading.Barrier(len(sessions))
    answers = []

    def check(session):
        start.wait()
        answers.append(session.rpc("sh_alerts_check"))

    threads = [threading.Thread(target=check, args=(s,)) for s in sessions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(answers) == 8 and all(len(a) == 4 for a in answers)       # everyone is told about the same four pushes
    assert db.sql("select key, count(*) from sh_alerts group by key order by key") == sorted(
        ("down:" + page, 1) for page in PROBE)
    assert db.sql("select count(*), count(distinct alert_id) from sh_messages") == [(4, 4)]
    with pytest.raises(psycopg.errors.UniqueViolation):                  # and the index itself forbids a second open alert
        db.sql("insert into sh_alerts (key, kind, title) values ('down:סל', 'down', 'x')")


# ================================================================ write functions (§7.4)

def test_probe_add_ignores_a_repeated_round_and_beats_on_full_rounds_only(db):
    db.setup()
    assert db.probe(T0 + secs(30), "light", ms=None) == {"n": 4}
    assert flow(db, PROBE_FLOW)["status"] == "אין נתון"                   # a light round is no proof of life
    assert db.probe(T0, fail=DEAD) == {"n": 4}                           # a round of failures still proves the prober ran
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == T0
    assert db.probe(T0, ms=999) == {"n": 0}
    assert db.sql("select count(*), count(*) filter (where ok), max(ms) from sh_probe where kind = 'full'") == [(4, 0, 300)]
    db.probe(T0 - mins(5))                                               # an older round arriving late
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == T0
    assert db.sql("select ms from sh_probe where kind = 'light'") == [(None,)] * 4


def test_probe_add_refuses_rows_that_break_the_contract(db):
    db.setup()
    row = {"page": "סל", "url": URL["סל"], "ok": False, "status": 502}
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="full", p_rows=[row])
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="full",
               p_rows=[dict(row, status=None, fail="http")])              # an HTTP failure has a status
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="quick",
               p_rows=[dict(row, fail="http")])
    assert db.sql("select count(*) from sh_probe") == [(0,)]


def test_speed_add_ignores_a_repeated_run_and_beats_the_flow_of_a_successful_run(db):
    db.setup()
    assert db.run(T0, "בית", None, err="timeout") == {"n": 1}
    assert db.run(T0, SITE + "/a/", None, source="rotation", err="timeout") == {"n": 1}
    assert (flow(db, CORE_FLOW)["status"], flow(db, ROTATION_FLOW)["status"]) == ("אין נתון", "אין נתון")
    assert db.run(T0 + mins(15), "בית", 2399.6, score=63.4, bytes=3400000.0, cls=0.0349) == {"n": 1}
    assert db.run(T0 + mins(15), "בית", 9999) == {"n": 0}
    assert db.sql("select lcp_ms, score, bytes, cls from sh_speed where ok") == [(2400, 63, 3400000, decimal.Decimal("0.035"))]
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == T0 + mins(15)
    assert flow(db, ROTATION_FLOW)["last_at"] is None
    db.run(T0 + mins(20), SITE + "/a/", 3000, source="rotation")
    assert dt.datetime.fromisoformat(flow(db, ROTATION_FLOW)["last_at"]) == T0 + mins(20)
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == T0 + mins(15)


def _site_pages(db):
    return db.sql("select url, active from sh_site_pages order by url")


def test_sitemap_set(db):
    db.setup()
    a, b, c, d = (SITE + "/%s/" % x for x in "abcd")
    assert db.rpc("sh_sitemap_set", p_urls=[a, b, c, a]) == {"n": 3}
    assert _site_pages(db) == [(a, True), (b, True), (c, True)]
    assert flow(db, SITEMAP_FLOW)["status"] == "תקין"

    db.sql("update sh_flows set last_at = null")
    for empty in ([], None):
        fails_with(db, psycopg.errors.RaiseException, "an empty list is refused", "sh_sitemap_set", p_urls=empty)
    assert _site_pages(db) == [(a, True), (b, True), (c, True)]
    assert flow(db, SITEMAP_FLOW)["status"] == "אין נתון"                 # a refused read is no proof of life

    db.rpc("sh_sitemap_set", p_urls=[a, b, d])
    assert _site_pages(db) == [(a, True), (b, True), (c, False), (d, True)]
    db.rpc("sh_sitemap_set", p_urls=[c])
    assert _site_pages(db) == [(a, False), (b, False), (c, True), (d, False)]


def test_rotation_takes_turns(db):
    db.setup()
    pages = [SITE + "/%s/" % x for x in "abcdef"]
    db.rpc("sh_sitemap_set", p_urls=pages + [SITE + "/gone/"])
    db.rpc("sh_sitemap_set", p_urls=pages)                                # /gone/ is no longer on the site
    a, b, c, d, e, f = pages
    assert [db.rpc("sh_rotation_next", p_n=2) for _ in range(6)] == [[a, b], [c, d], [e, f]] * 2
    assert db.rpc("sh_rotation_next", p_n=4) == [a, b, c, d]              # always the ones measured longest ago
    new = SITE + "/new/"
    db.rpc("sh_sitemap_set", p_urls=pages + [new])
    assert db.rpc("sh_rotation_next", p_n=3) == [e, f, new]               # a page never measured goes first
    assert db.rpc("sh_rotation_next", p_n=10) == sorted(pages + [new])
    assert db.rpc("sh_rotation_next", p_n=0) == []
    assert db.sql("select last_measured_at from sh_site_pages where not active") == [(None,)]


def test_rotation_skips_pages_another_worker_is_claiming(committed):
    first, second = committed(), committed()
    first.setup()
    pages = [SITE + "/%s/" % x for x in "abcd"]
    first.rpc("sh_sitemap_set", p_urls=pages)
    with first.conn.transaction():                                        # a claim that has not been committed yet
        assert first.rpc("sh_rotation_next", p_n=2) == pages[:2]
        assert second.rpc("sh_rotation_next", p_n=3) == pages[2:]         # no waiting, and not the same pages


def test_issues_set_replaces_the_day_and_the_screen_reads_the_latest_snapshot(db):
    db.setup()
    monday, tuesday = dt.date(2024, 11, 11), dt.date(2024, 11, 12)
    sofa = {"product_id": "7", "issue": "לא במלאי", "name": "ספה", "url": SITE + "/product/sofa/"}
    bed = {"product_id": "8", "issue": "בלי מחיר", "name": "מיטה", "url": SITE + "/product/bed/"}
    assert db.rpc("sh_issues_set", p_snap_date=monday, p_rows=[sofa, bed, dict(sofa, issue="בלי תמונה")]) == {"n": 3}
    again = [sofa, dict(bed, issue="לא במלאי"), dict(sofa, issue="בלי תמונה")]
    assert db.rpc("sh_issues_set", p_snap_date=monday, p_rows=again) == {"n": 3}
    listed = {"issue": "לא במלאי", "name": "ספה", "url": SITE + "/product/sofa/", "snap_date": "2024-11-11"}
    assert db.rpc("sh_product_issues") == [                               # by issue, then by name
        dict(listed, issue="בלי תמונה"), dict(listed, name="מיטה", url=SITE + "/product/bed/"), listed]
    assert flow(db, CATALOGUE_FLOW)["status"] == "תקין"

    assert db.rpc("sh_issues_set", p_snap_date=tuesday, p_rows=[bed]) == {"n": 1}
    assert db.rpc("sh_product_issues") == [
        {"issue": "בלי מחיר", "name": "מיטה", "url": SITE + "/product/bed/", "snap_date": "2024-11-12"}]
    assert db.sql("select count(*) from sh_product_issues") == [(4,)]     # Monday's snapshot is kept, not shown
    assert db.rpc("sh_issues_set", p_snap_date=tuesday, p_rows=[]) == {"n": 0}
    assert db.rpc("sh_product_issues") == []                              # nothing is broken any more


def test_job_markers(db):
    monday, tuesday = dt.date(2024, 11, 11), dt.date(2024, 11, 12)
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=monday) is True
    assert db.rpc("sh_job_mark", p_job="catalogue", p_day=monday) is True
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=monday) is False
    assert db.rpc("sh_job_mark", p_job="catalogue", p_day=monday) is False       # someone else was first
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=tuesday) is True
    assert db.rpc("sh_job_due", p_job="sitemap", p_day="2024-11-11") is True     # a date may arrive as text


def test_cleanup_keeps_what_the_retention_rules_keep(db):
    db.setup()
    db.sql("insert into sh_probe (round_at, kind, page, url, ok) select now() - d * interval '1 day', kind, 'בית', 'u', true"
           " from (values (399, 'full'), (401, 'full'), (6, 'light'), (8, 'light'), (402, 'light')) as v(d, kind)")
    db.sql("insert into sh_speed (at, url, strategy, source, ok)"
           " select now() - d * interval '1 day', 'u', 'mobile', 'core', true from (values (399), (401)) as v(d)")
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) select now() - d * interval '1 day', 'live', '/', 1000"
           " from (values (29), (31), (32)) as v(d)")
    db.sql("insert into sh_login_log (at, ok) select now() - d * interval '1 day', true from (values (399), (401)) as v(d)")
    db.sql("insert into sh_alerts (key, kind, title, opened_at, closed_at)"
           " values ('k', 'down', 't', now() - interval '900 days', now() - interval '899 days')")
    db.sql("insert into sh_messages (at, event, kind, title) values (now() - interval '900 days', 'open', 'התראה', 't')")
    db.rpc("sh_issues_set", p_snap_date=dt.date(2020, 1, 1), p_rows=[{"product_id": "1", "issue": "בלי מחיר"}])
    assert db.rpc("sh_cleanup") == {"probe": 2, "probe_light": 1, "speed": 1, "rum": 2, "login_log": 1}
    assert db.sql("select kind, round(extract(epoch from now() - round_at) / 86400)::int from sh_probe order by 2") == [
        ("light", 6), ("full", 399)]
    assert [db.sql("select count(*) from " + t)[0][0] for t in
            ("sh_speed", "sh_rum", "sh_login_log", "sh_alerts", "sh_messages", "sh_product_issues")] == [1, 1, 1, 1, 1, 1]
    assert db.rpc("sh_cleanup") == {"probe": 0, "probe_light": 0, "speed": 0, "rum": 0, "login_log": 0}


def test_rum_add_stores_no_query_string_and_no_impossible_timing(db):
    db.setup()
    assert db.rpc("sh_rum_add", p_rows=[{"site": "live", "path": "/", "lcp_ms": 0},
                                        {"site": "live", "path": "/", "lcp_ms": 60001},
                                        {"path": "/", "lcp_ms": 1000}, {"site": "live", "lcp_ms": 1000}]) == {"n": 0}
    assert flow(db, RUM_FLOW)["status"] == "אין נתון"
    assert db.rpc("sh_rum_add", p_rows=[
        {"site": "live", "path": "/product/sofa/?email=a@b.co&utm=x#top", "lcp_ms": 1, "is_test": True},
        {"site": "dev.example.co.il", "path": "/cart/", "lcp_ms": 60000},
        {"site": "live", "path": "/", "lcp_ms": 2400.4}]) == {"n": 3}
    assert db.sql("select site, path, lcp_ms, is_test, created_at = now() from sh_rum order by lcp_ms") == [
        ("live", "/product/sofa/", 1, True, True), ("live", "/", 2400, False, True),
        ("dev.example.co.il", "/cart/", 60000, False, True)]
    assert flow(db, RUM_FLOW)["status"] == "תקין"


def test_cert_set_and_read(db):
    db.setup()
    assert db.rpc("sh_cert") is None
    now = db.now()
    assert _cert(db, 23) == {"n": 1}
    cert = db.rpc("sh_cert")
    assert {k: v for k, v in cert.items() if k not in ("not_after", "checked_at")} == {
        "host": "example.co.il", "issuer": "Let's Encrypt R11", "days_left": 23, "ok": True, "err": None}
    assert dt.datetime.fromisoformat(cert["not_after"]) == dt.datetime(2024, 11, 30, tzinfo=UTC)
    assert dt.datetime.fromisoformat(cert["checked_at"]) == now
    assert flow(db, CERT_FLOW)["status"] == "תקין"

    db.sql("update sh_flows set last_at = null")
    _cert(db, None, ok=False, err="certificate verify failed")
    cert = db.rpc("sh_cert")
    assert (cert["ok"], cert["err"], cert["days_left"], cert["issuer"]) == (
        False, "certificate verify failed", 23, "Let's Encrypt R11")
    assert flow(db, CERT_FLOW)["status"] == "אין נתון"                    # a failed check is no proof of life
    db.rpc("sh_cert_set", p_row={"host": "example.co.il", "ok": True, "days_left": 80, "checked_at": "2024-11-12T07:00:00Z"})
    cert = db.rpc("sh_cert")
    assert (cert["ok"], cert["err"], cert["days_left"]) == (True, None, 80)
    assert dt.datetime.fromisoformat(cert["checked_at"]) == T0


def test_login_log_and_ping(db):
    assert db.rpc("sh_ping") == "ok"
    assert db.rpc("sh_login_log_add", p_ip="203.0.113.7", p_ok=False, p_who=None, p_ua="Mozilla/5.0") == {"n": 1}
    assert db.rpc("sh_login_log_add", p_ip="203.0.113.7", p_ok=True, p_who="owner", p_ua="Mozilla/5.0") == {"n": 1}
    assert db.sql("select ip, ok, who, ua, at = now() from sh_login_log order by ok") == [
        ("203.0.113.7", False, None, "Mozilla/5.0", True), ("203.0.113.7", True, "owner", "Mozilla/5.0", True)]


# ================================================================ the simulator against an independent calculation

def test_a_simulated_day_matches_an_independent_calculation(db):
    db.setup()
    start = T0 - mins(120)                                                # 07:00 local: the day crosses local midnight
    data = sim.simulate(db.rpc, start, 1, fail_hour=("קטגוריה", T0, 6), dead=(T0 + mins(200), 7),
                        slow=("מוצר", T0 + mins(300), 5))
    window = dict(p_from=start, p_to=start + mins(1440))
    full = [r for r in data["probe"] if r["kind"] == "full"]
    assert len(full) == 4 * 1440 and len(data["probe"]) == 8 * 1440

    rows = db.rpc("sh_availability", **window)
    for page, row in zip(PROBE, rows):
        mine = [r for r in full if r["page"] == page]
        answered = [r["ms"] for r in mine if r["ok"]]
        failed = [r for r in mine if not r["ok"]]
        assert row == {"section": "לפי עמוד", "page": page, "checks": 1440, "failed": len(failed),
                       "fail_pct": "%.2f" % (100 * len(failed) / 1440),
                       "p50_ms": half_up(percentile(answered, 0.5)), "p95_ms": half_up(percentile(answered, 0.95)),
                       "last_fail_il": il(max(r["round_at"] for r in failed))}
    assert [r["failed"] for r in rows[:4]] == [7, 13, 7, 7]               # the outage, and six more for קטגוריה
    assert rows[4:] == [{"section": "נפילות", "outage_minutes": 7, "outage_start_il": il(T0 + mins(200)),
                         "outage_end_il": il(T0 + mins(207))}]

    series = db.rpc("sh_availability_series", **window)
    assert len(series) == 24
    for row in series:
        mine = [r for r in full if r["round_at"].astimezone(TZ).strftime("%Y-%m-%d %H:00") == row["bucket"]]
        answered = [r["ms"] for r in mine if r["ok"]]
        assert row == {"bucket": row["bucket"], "checks": 240, "failed": sum(not r["ok"] for r in mine),
                       "ms_p50": half_up(percentile(answered, 0.5)), "ms_p95": half_up(percentile(answered, 0.95))}
    assert sum(r["failed"] for r in series) == 34

    speed = db.rpc("sh_speed", **window)
    good = [r for r in data["speed"] if r["ok"]]
    core = section(speed, "ליבה")
    assert [(r["strategy"], r["page"]) for r in core] == [(s, p) for s in ("mobile", "desktop") for p in URL]
    for row in core:
        mine = [r for r in good if r["page"] == row["page"] and r["strategy"] == row["strategy"]]
        newest = max(mine, key=lambda r: r["at"])
        assert row == {"section": "ליבה", "strategy": row["strategy"], "page": row["page"], "url": URL[row["page"]],
                       "lcp_p50": half_up(percentile([r["lcp_ms"] for r in mine], 0.5)),
                       "lcp_p95": half_up(percentile([r["lcp_ms"] for r in mine], 0.95)),
                       "score_med": half_up(percentile([r["score"] for r in mine], 0.5)),
                       "cls_med": round(percentile([r["cls"] for r in mine], 0.5), 3),
                       "ttfb_p50": half_up(percentile([r["ttfb_ms"] for r in mine], 0.5)),
                       "slow_runs": sum(r["lcp_ms"] > 4000 for r in mine), "checks": len(mine),
                       "crux_category": newest["crux_category"], "crux_lcp": newest["crux_lcp_ms"]}
    by_page = {(r["strategy"], r["page"]): r for r in core}
    assert (by_page["mobile", "מוצר"]["slow_runs"], by_page["mobile", "קטגוריה"]["checks"]) == (5, 94)   # 2 of 96 runs failed
    home = by_page["mobile", "בית"]
    assert section(speed, "שורה תחתונה") == [{"section": "שורה תחתונה", "page": "בית", "url": URL["בית"],
                                              "lcp_p50": home["lcp_p50"], "checks": 96,
                                              "verdict": mock.verdict(home["lcp_p50"])}]
    rotation = {}
    for r in good:
        if r["source"] == "rotation":
            rotation.setdefault(r["url"], []).append(r)
    heaviest = sorted(rotation, key=lambda u: (-percentile([r["lcp_ms"] for r in rotation[u]], 0.5), u))[:10]
    assert [(r["url"], r["lcp_p50"], r["checks"], r["last_il"]) for r in section(speed, "האיטיים באתר")] == [
        (u, half_up(percentile([r["lcp_ms"] for r in rotation[u]], 0.5)), len(rotation[u]),
         il(max(r["at"] for r in rotation[u]))) for u in heaviest]
    assert all(len(runs) in (14, 15) for runs in rotation.values())      # 576 runs over 40 pages, in turns
    assert section(speed, "כיסוי") == [{"section": "כיסוי", "checks": 40, "slow_runs": 40}]

    series = db.rpc("sh_speed_series", p_strategy="mobile", **window)
    assert len(series) == 5 * 24
    for row in series:
        mine = [r["lcp_ms"] for r in good if r["page"] == row["page"] and r["strategy"] == "mobile"
                and r["at"].astimezone(TZ).strftime("%Y-%m-%d %H:00") == row["bucket"]]
        assert row["lcp_p50"] == half_up(percentile(mine, 0.5))

    # the flows the simulator fed are alive up to its last measurement
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == start + mins(1439)
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == start + mins(1425)
    assert dt.datetime.fromisoformat(flow(db, ROTATION_FLOW)["last_at"]) == start + mins(1435)


# ================================================================ the same shapes as the mock backend (§5)

def _shape(row):
    """The keys of a row and the kind of each value that is not null."""
    kinds = {bool: "bool", int: "number", float: "number", str: "text", list: "list", dict: "object"}
    return {k: kinds[type(v)] for k, v in row.items() if v is not None}


def _same_shape(mine, theirs, mock_only=()):
    """Same keys; and where both have a value, the same kind of value."""
    assert set(mine) == set(theirs) - set(mock_only), (sorted(mine), sorted(theirs))
    a, b = _shape(mine), _shape(theirs)
    assert {k: a[k] for k in a if k in b} == {k: b[k] for k in a if k in b}


@pytest.fixture
def busy(db):
    """A database with something in every part of the screen: a simulated day that ends now,
    an alert that opened and closed, one that is still open, and the daily snapshots."""
    db.setup()
    now = db.now()
    minute = now.replace(second=0, microsecond=0)
    sim.simulate(db.rpc, minute - mins(1440), 1, light=False,
                 dead=(minute - mins(600), 7), fail_hour=("סל", minute - mins(180), 3))
    sim.snapshot(db.rpc, now.date())
    db.probe(now - secs(3), fail={"סל": 502})
    db.rpc("sh_alerts_check")
    db.sql("update sh_alerts set opened_at = now() - interval '9 minutes'")
    db.probe(now - secs(2))
    for message in db.rpc("sh_alerts_check"):
        db.rpc("sh_message_sent", p_id=message["id"], p_status=200)
    db.probe(now - secs(1), fail={"מוצר": 502})
    db.rpc("sh_alerts_check")
    return db


def test_site_parts_have_the_shapes_of_the_mock(busy, monkeypatch):
    db, now = busy, busy.now()
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    theirs = mock.api_site({"h": "24", "strategy": "mobile"}, "owner")
    window = dict(p_from=now - mins(1440), p_to=now + mins(1))

    mine = db.rpc("sh_availability", **window)
    for name in ("לפי עמוד", "נפילות"):
        assert section(mine, name) and section(theirs["availability"], name)
        _same_shape(section(mine, name)[0], section(theirs["availability"], name)[0])
    _same_shape(db.rpc("sh_availability_series", **window)[0], theirs["availability_series"][0])
    mine = db.rpc("sh_speed", **window)
    for name in ("שורה תחתונה", "ליבה", "האיטיים באתר", "כיסוי"):
        _same_shape(section(mine, name)[0], section(theirs["speed"], name)[0])
    _same_shape(db.rpc("sh_speed_series", p_strategy="mobile", **window)[0], theirs["speed_series"][0])
    _same_shape(db.rpc("sh_alerts_open")[0], theirs["alerts_open"][0])
    recent = db.rpc("sh_alerts_range", **window)
    assert [a["open"] for a in recent] == [True, False]
    _same_shape(recent[0], next(a for a in theirs["alerts_recent"] if a["open"]))
    _same_shape(recent[1], next(a for a in theirs["alerts_recent"] if not a["open"]))
    health = db.rpc("sh_health")
    assert [r["flow_name"] for r in health] == [r["flow_name"] for r in theirs["health"]]
    for a, b in zip(health, theirs["health"]):
        # flow_group is a leftover of the system the screen was taken from: SPEC §5.2 does not
        # list it and site_health.html never reads it
        _same_shape(a, b, mock_only=["flow_group"])
    _same_shape(db.rpc("sh_product_issues")[0], theirs["product_issues"][0])
    _same_shape(db.rpc("sh_cert"), theirs["cert"])


def test_now_has_the_shape_of_the_mock(busy, monkeypatch):
    db = busy
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    theirs, mine = mock.api_now("owner"), db.rpc("sh_now")
    _same_shape(mine, theirs)
    _same_shape(mine["pages"][0], theirs["pages"][0])
    # the mock hands its "pages" rows out again as "latest"; SPEC §5.3 defines {page, ok} and the
    # screen reads nothing else from them
    assert set(mine["latest"][0]) == {"page", "ok"} <= set(theirs["latest"][0])
    for part in ("rum", "speed", "rum_src"):
        _same_shape(mine[part], theirs[part])
    _same_shape(mine["rum_src"]["hosts"][0], theirs["rum_src"]["hosts"][0])


def test_drills_and_messages_have_the_shapes_of_the_mock(busy, monkeypatch):
    db, now = busy, busy.now()
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    window = dict(p_from=now - mins(1440), p_to=now + mins(1))

    def theirs(what, **q):
        return mock.api_drill(dict(q, what=what, h="24"), "owner")["rows"]

    fails = db.rpc("sh_drill_fails", **window)
    for kind in {r["kind"] for r in fails}:
        _same_shape(next(r for r in fails if r["kind"] == kind), theirs("fails")[0])
    bucket = db.rpc("sh_availability_series", **window)[5]["bucket"]
    _same_shape(db.rpc("sh_drill_bucket", p_bucket=bucket)[0], theirs("bucket", bucket=bucket)[0])
    runs, their_runs = db.rpc("sh_drill_runs", p_url=URL["קטגוריה"], **window), theirs("runs", url=URL["קטגוריה"])
    for ok in (True, False):
        _same_shape(next(r for r in runs if r["ok"] is ok), next(r for r in their_runs if r["ok"] is ok))
    _same_shape(runs[0]["opps"][0], their_runs[0]["opps"][0])
    closed = next(a for a in db.rpc("sh_alerts_range", **window) if not a["open"])
    mine, their = db.rpc("sh_drill_alert", p_id=closed["id"])[0], theirs("alert", id="38")[0]
    _same_shape(mine, their)
    _same_shape(mine["fails"][0], their["fails"][1])
    assert [s["event"] for s in mine["sent"]] == ["open", "close"] == [s["event"] for s in their["sent"]]
    _same_shape(mine["sent"][0], their["sent"][0])
    messages = db.rpc("sh_messages", **window)
    assert [(m["kind"], m["sent"]) for m in messages] == [("התראה", False), ("חזר לתקין", True), ("התראה", True)]
    for row in messages:
        _same_shape(row, mock.api_messages({})["rows"][0])


# ================================================================ the SQL files themselves

READ = ["sh_availability", "sh_availability_series", "sh_speed", "sh_speed_series", "sh_alerts_open", "sh_alerts_range",
        "sh_health", "sh_product_issues", "sh_cert", "sh_now", "sh_drill_fails", "sh_drill_bucket", "sh_drill_runs",
        "sh_drill_alert", "sh_messages", "sh_ping", "sh_config", "sh_job_due"]
WRITE = ["sh_alert_ack", "sh_login_log_add", "sh_rum_add", "sh_setup", "sh_probe_add", "sh_speed_add", "sh_rotation_next",
         "sh_sitemap_set", "sh_cert_set", "sh_issues_set", "sh_job_mark", "sh_alerts_check", "sh_message_sent",
         "sh_morning", "sh_cleanup"]
API = READ + WRITE                                                        # the 33 functions of SPEC §7.3 and §7.4


def test_every_function_of_the_spec_exists_with_the_agreed_form(db):
    found = {name: rest for name, *rest in db.sql(
        r"select proname::text, prorettype::regtype::text, provolatile::text, proconfig, coalesce(proargnames, '{}')"
        r" from pg_proc where pronamespace = 'public'::regnamespace and proname like 'sh\_%'")}
    assert set(API) <= set(found) and len(found) == len(API) + 7           # and seven helpers
    for name, (returns, volatility, settings, parameters) in found.items():
        assert settings == ["search_path=public"], name
        assert all(p.startswith("p_") for p in parameters), name
        if name in API:
            assert returns == "jsonb", name
            assert (volatility == "s") == (name in READ), name


def test_schema_and_functions_can_be_applied_again(committed):
    db = committed()
    db.setup()
    db.probe(T0, fail={"סל": 502})
    db.run(T0, "בית", 2400)
    before = (db.rpc("sh_config"), db.rpc("sh_health"), db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1)))
    apply_sql(db.conn)
    apply_sql(db.conn)
    assert (db.rpc("sh_config"), db.rpc("sh_health"), db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1))) == before


def test_tables_and_functions_are_private(db):
    assert db.sql(r"select count(*), count(*) filter (where relrowsecurity) from pg_class"
                  r" where relnamespace = 'public'::regnamespace and relkind = 'r' and relname like 'sh\_%'") == [(13, 13)]
    assert db.sql("select count(*) from pg_policies where schemaname = 'public'") == [(0,)]
    db.sql("create role sh_test_visitor")                                 # rolled back with the test
    db.sql("set local role sh_test_visitor")
    for call in ("select sh_ping()", "select sh_now()", "select sh_tz()", "select * from sh_probe"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.conn.transaction():
                db.sql(call)


def test_on_supabase_only_the_service_role_gets_in(db):
    """The three roles exist (or change) only inside this test's transaction: nothing is left on the server."""
    roles = ("anon", "authenticated", "service_role")
    for role in roles:
        if not db.sql("select 1 from pg_roles where rolname = %s", [role]):
            db.sql("create role %s" % role)
    db.sql("alter role service_role bypassrls")                           # as on Supabase
    # what Supabase's default privileges hand out when a table or a function is created
    db.sql("grant all on all tables in schema public to anon, authenticated, service_role")
    db.sql("grant execute on all functions in schema public to anon, authenticated, service_role")
    apply_sql(db.conn)

    def may(role):
        """How many of the sh_* functions the role may run, and how many of the tables it may read."""
        return db.sql(r"""
            select (select count(*) from pg_proc
                    where pronamespace = 'public'::regnamespace and proname like 'sh\_%%'
                      and has_function_privilege(%(role)s, oid, 'execute')),
                   (select count(*) from pg_class
                    where relnamespace = 'public'::regnamespace and relkind = 'r' and relname like 'sh\_%%'
                      and has_table_privilege(%(role)s, oid, 'select'))""", {"role": role})[0]

    assert [may(role) for role in roles] == [(0, 0), (0, 0), (len(API) + 7, 13)]

    db.sql("set local role service_role")                                 # and the service role can do its whole job
    db.setup()
    db.probe(db.now() - secs(30), fail={"סל": 502})
    assert [m["title"] for m in db.rpc("sh_alerts_check")] == ["האתר לא עונה: סל"]
    assert db.rpc("sh_now")["alerts_open"] == 1 and len(db.rpc("sh_health")) == 7
    db.sql("set local role anon")
    for call in ("select sh_now()", "select * from sh_alerts"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.conn.transaction():
                db.sql(call)


# ================================================================ performance

def test_reads_over_90_days_take_less_than_2_seconds(db):
    """90 days of probe history for 4 pages (518,400 rows), of lab runs (54,000 core and 51,840
    rotation runs), 30 days of real-user rows and a few hundred alerts, generated in bulk."""
    db.setup()
    db.sql("""
        insert into sh_probe (round_at, kind, page, url, ok, status, ms, fail)
        select date_trunc('minute', now()) - n * interval '1 minute', 'full', p.name, p.url, x.ok,
               case when x.ok then 200 else 502 end,
               case when x.ok then 150 + 90 * p.sort + mod(n * 37 + p.sort * 101, 400) else 900 end,
               case when not x.ok then 'http' end
        from generate_series(0, 129599) n
        cross join sh_pages p
        cross join lateral (select not (mod(n * 7 + p.sort, 997) = 0 or n between 50000 and 50006) as ok) x
        where p.is_probe""")
    opps = Jsonb([{"id": "audit-%d" % i, "title": "תמונות גדולות מדי לגודל שבו הן מוצגות באתר", "ms": 900 - 100 * i}
                                     for i in range(8)])
    db.sql("""
        insert into sh_speed (at, url, page, strategy, source, ok, score, lcp_ms, cls, ttfb_ms, bytes,
                              crux_category, crux_lcp_ms, opps)
        select date_trunc('minute', now()) - n * interval '15 minutes', p.url, p.name, s.strategy, 'core', true,
               60, 1800 + mod(n * 53 + p.sort * 17, 3000), 0.03, 400, 3400000, 'FAST', 2100, %s
        from generate_series(0, 8639) n
        cross join sh_pages p
        cross join (values ('mobile', 1), ('desktop', 4)) as s(strategy, every)
        where p.is_core and mod(n, s.every) = 0""", [opps])
    db.sql("insert into sh_site_pages (url) select %s || '/product/item-' || g || '/' from generate_series(0, 399) g", [SITE])
    db.sql("""
        insert into sh_speed (at, url, strategy, source, ok, score, lcp_ms, cls, ttfb_ms, bytes, opps)
        select date_trunc('minute', now()) - (n / 2) * interval '5 minutes', %s || '/product/item-' || mod(n, 400) || '/',
               'mobile', 'rotation', true, 50, 1500 + mod(n * 7919, 6000), 0.05, 500, 4000000, %s
        from generate_series(0, 51839) n""", [SITE, opps])
    db.sql("""
        insert into sh_rum (created_at, site, path, lcp_ms)
        select now() - n * interval '2 minutes', 'live', '/product/item-' || mod(n, 400) || '/', 1000 + mod(n * 131, 4000)
        from generate_series(0, 21599) n""")
    db.sql("""
        insert into sh_alerts (key, kind, title, body, opened_at, closed_at)
        select 'down:סל', 'down', 'האתר לא עונה: סל', 'קוד 502', t, t + interval '7 minutes'
        from generate_series(1, 400) n cross join lateral (select now() - n * interval '5 hours' as t) x""")
    db.sql("""
        insert into sh_messages (at, alert_id, event, kind, title, msg, priority, status)
        select opened_at, id, 'open', 'התראה', title, body, 4, 200 from sh_alerts""")
    sim.snapshot(db.rpc, db.now().date())
    db.sql("analyze")
    assert db.sql("select count(*) from sh_probe") == [(518400,)]
    assert db.sql("select count(*), count(*) filter (where source = 'core') from sh_speed") == [(105840, 54000)]

    now = db.now()
    window = dict(p_from=now - dt.timedelta(days=90), p_to=now + mins(1))
    site = [("sh_availability", window), ("sh_availability_series", window), ("sh_speed", window),
            ("sh_speed_series", dict(window, p_strategy="mobile")), ("sh_alerts_open", {}),
            ("sh_alerts_range", window), ("sh_health", {}), ("sh_product_issues", {}), ("sh_cert", {})]
    today = now.astimezone(TZ).date()
    others = [("sh_now", {}), ("sh_drill_fails", window), ("sh_drill_bucket", dict(p_bucket=today.isoformat())),
              ("sh_drill_runs", dict(window, p_url=URL["בית"])), ("sh_messages", window), ("sh_alerts_check", {}),
              ("sh_morning", dict(p_day=today)), ("sh_cleanup", {})]
    answers = {}
    for fn, params in site + others:
        slowest = 0
        for _ in range(2):                                               # the first call also plans the query
            started = time.perf_counter()
            answers[fn] = db.rpc(fn, **params)
            slowest = max(slowest, time.perf_counter() - started)
        TIMINGS.append((fn + ("  (/api/site)" if (fn, params) in site else ""), slowest))
        assert slowest < 2, fn

    # and the answers are about all of it
    rows, minute = answers["sh_availability"], now.replace(second=0, microsecond=0)
    assert [r["checks"] for r in rows[:4]] == [129600] * 4
    assert rows[4:] == [{"section": "נפילות", "outage_minutes": 7, "outage_start_il": il(minute - mins(50006)),
                         "outage_end_il": il(minute - mins(49999))}]
    days = answers["sh_availability_series"]
    assert len(days) in (91, 92) and sum(r["checks"] for r in days) == 518400
    assert [r["checks"] for r in section(answers["sh_speed"], "ליבה")] == [8640] * 5 + [2160] * 5
    assert section(answers["sh_speed"], "כיסוי") == [{"section": "כיסוי", "checks": 400, "slow_runs": 400}]
    assert len(answers["sh_drill_runs"]) == 8640 and len(answers["sh_drill_fails"]) == 500
~~~~~~~~
<!-- END FILE -->

<!-- FILE: site-health-kit/tools/check_template.py sha256=e0aa3f9bad6a81fc12dd917c6b07fbc697bd0607583838eedcee91bece8ec522 -->
~~~~~~~~python
#!/usr/bin/env python3
"""Proves that a deployed screen file is still the kit's screen and not a rewrite.

    python3 tools/check_template.py path/to/deployed/site_health.html

Passes when the file keeps the kit's structure and almost all of its lines. The edits that
spec §6.9 allows (SH_CONFIG values, explanation sentences, OPP entries, color variables)
change a few dozen lines at most. Prints SCREEN OK, or what is wrong. Exit code 0 / 1.
"""
import os
import re
import sys

KIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site_health.html")
MIN_KEPT = 0.93          # share of the kit's lines that must appear unchanged in the deployed file


def lines(text):
    return [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]


def main(path):
    kit = open(KIT, encoding="utf-8").read()
    try:
        raw = open(path, "rb").read()
        got = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["the file is not valid UTF-8 (Hebrew text was damaged)"]
    bad = []
    if got.count("<!--SH_INJECT-->") != 1:
        bad.append("the marker <!--SH_INJECT--> must appear exactly once (the server injects SH_CONFIG / SH_ROLE there)")
    if not re.search(r'<html[^>]*\blang="he"[^>]*\bdir="rtl"|<html[^>]*\bdir="rtl"[^>]*\blang="he"', got):
        bad.append('the <html> tag must keep lang="he" dir="rtl"')
    if re.search(r'<(script|link|img|iframe)\b[^>]*\b(src|href)\s*=\s*["\']?(https?:)?//', got, re.I):
        bad.append("the screen must not load anything from another host (no external scripts, styles, fonts or images)")
    if "classList.toggle('explain')" in got or 'classList.toggle("explain")' in got:
        bad.append("the explanations toggle must use the class explain-on (class explain on <body> hides the whole page)")
    if re.search(r"\\u05[0-9a-fA-F]{2}|&#x?5[0-9a-fA-F]{2,3};", got):
        bad.append("Hebrew text was escaped (\\u05.. or &#...;): keep it as plain UTF-8")
    have = set(lines(got))
    want = lines(kit)
    kept = sum(1 for l in want if l in have) / len(want)
    if kept < MIN_KEPT:
        missing = [l for l in want if l not in have][:5]
        bad.append("only %.0f%% of the kit's lines are unchanged (need %.0f%%): this looks like a rewrite, not a copy. "
                   "First missing lines: %s" % (100 * kept, 100 * MIN_KEPT, " | ".join(m[:70] for m in missing)))
    for needle, why in (("window.SH_CONFIG", "the SH_CONFIG block"), ("function render(d)", "the render function"),
                        ("function drillRuns(", "the drill-down sheets"), ("@media print", "the print stylesheet"),
                        ("prefers-color-scheme:dark", "dark mode")):
        if needle not in got:
            bad.append("missing " + why)
    return bad


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    problems = main(sys.argv[1])
    if problems:
        print("SCREEN CHECK FAILED\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("SCREEN OK")
~~~~~~~~
<!-- END FILE -->
