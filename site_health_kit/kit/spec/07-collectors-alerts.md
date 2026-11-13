# Site Health kit — spec: the backend: collectors, alert rules, pushes, the watchdog (§7.5–§7.11, reference design)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

---

## 7. The backend, continued: collectors, alerts, pushes

### 7.5 Collector: availability probe (`בודק זמינות האתר`)

- **Full round** at the top of every minute: request every probe page concurrently. `GET`, a fresh
  connection, follow up to 5 redirects, timeout **10 seconds**, `User-Agent: SiteHealthProbe/1.0
  (+<dashboard address>)`, `Cache-Control: no-cache`.
- A check is **ok** when the final status is exactly 200 within the timeout (a 204 or a 206 is not
  the page) and, if the page has an `expect` text, the first 200 KB of the body contain it.
  Otherwise `fail` is `timeout`, `http` (with the status), `connect` (DNS, TLS, reset) or `content`.
- `ms` = time from sending the request until the response headers of the final response arrive
  (what a new visitor's first request waits for). Read the body only when `expect` is set.
- **Light round** at second 30 of every minute: the same requests with a 5-second timeout,
  stored with `kind = 'light'` and `ms = null`. It feeds the "now" tile and gives the alert rule
  a second sample each minute (with `down_after` = 2 an alert can open after one minute instead
  of two). Never count it in availability or response-time statistics.
- All rows of a round share one `round_at` (the scheduled second, not the completion time).
- **Where a request to the site may go.** What a site answers must never choose which machine
  the collectors talk to. Two rules hold for every request to the monitored site (the probe,
  `robots.txt`, sitemap files, the catalogue, the certificate check):
  1. A redirect is followed only to the host the request started on (with or without `www.`, on
     http or https) or to a host listed in the configuration's `extra_hosts` (a shop whose cart
     lives on another domain). Any other redirect is not followed: the check fails with `fail`
     `http`, the redirect's status and `err` `redirected to another host`.
  2. The name is resolved once and the connection goes to the address that was checked. An
     address that is not a public one (loopback, private ranges, link-local, the cloud metadata
     address) is refused before a packet leaves: `fail` `connect`, `err` `NotPublic: …`. The
     switch `SH_ALLOW_PRIVATE=1` in the worker's environment turns this second rule off; it is
     for a rehearsal against `reference/tests/fake_site.py` and for a site that really lives on
     a private network. The first rule has no switch.
- **Look at the first real round before the topic is set.** A firewall, a bot filter or a
  country block that refuses the dashboard's host fails every round, and the owner's phone would
  get `האתר לא עונה` from the first minute while the site is fine. Run one round from the real
  host with `NTFY_TOPIC` still unset; if a page is refused, stop and give whoever runs the
  site's firewall the User-Agent to allow: `SiteHealthProbe/1.0` (followed by `(+<dashboard
  address>)` when `DASHBOARD_URL` is set). The other direction: a challenge or maintenance page
  that answers 200 counts as up unless the page has an `expect` text, so give the home page one,
  copied from the real page.
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
- Errors: 429 whose message mentions "per day" → stop until the quota resets (midnight Pacific
  time); other 429, other 5xx and network errors → up to three calls in all, waiting 5 and then
  10 seconds; 400 "API key not valid" or 403 (the API is not enabled, or the key is restricted) →
  a configuration error: do not retry the call, log it clearly without the key, measure nothing
  and ask again with one call an hour later (so enabling the API in Google's console needs no
  restart; a new key value does). The flow goes `שקט` meanwhile.
  A failure of the test itself (HTTP 500 "Lighthouse returned error: …",
  `lighthouseResult.runtimeError` on a 200, or a 200 without an LCP value) is stored as a run with
  `ok = false` and the error text, without retrying. Failed runs never count in medians.
- A run's `at` is the start of its slot (the quarter hour, the hour, the five minutes), not the
  second it finished: a round that is repeated is then stored once, and one slot can never look
  like "twice in a row" to the slow alert.
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
| `opps` | up to 6 reasons with an estimated time saving, largest first: `[{id, title, ms}]` (rule below; the screen shows six) |

- **Real-user data is optional.** A page with little traffic has no `loadingExperience.metrics`.
  When `loadingExperience.origin_fallback` is true the numbers describe the whole site, not this
  page: store null for both `crux_*` columns in that case. The screen then says "אין מספיק תנועה".
- **`opps` rule** (works for old and new Lighthouse versions). For every audit in
  `lighthouseResult.audits`, except the metric audits themselves (`first-contentful-paint`,
  `largest-contentful-paint`, `largest-contentful-paint-element`, `first-meaningful-paint`,
  `total-blocking-time`, `cumulative-layout-shift`, `speed-index`, `interactive`,
  `max-potential-fid`, `interaction-to-next-paint`):
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
  `strategy=desktop`. **Rotation:** every 5 minutes, 2 pages from `sh_rotation_next(2)`, phone only;
  none where the sitemap is switched off. With 5 core pages that is up to about 1,200 calls a day.
- Without `PAGESPEED_KEY` the collector does not run and says so in its log once; the speed cards
  show their empty states and the flows stay `אין נתון`.
- A rehearsal on one machine: the optional `PAGESPEED_URL` names another address for the API.
  `reference/tests/fake_site.py` prints the value to use, with a made-up key; its fake answers
  every page with the same sample result, so it proves the plumbing and no speed.
- What the numbers mean (the screen says this too): the phone test simulates a mid-range phone on
  a slow 4G connection, measured from a Google data center, so it is harsher than what most
  visitors see and single runs are noisy. Verdicts and alerts therefore use medians and
  "twice in a row", never one run. A site behind bot protection may block Google's test; that
  shows up as failed runs with a 403 in the error text.

### 7.7 Collectors: sitemap, catalogue, certificate, real users

Rules shared by the sitemap and the catalogue reads: **read everything, prove it is complete, and
only then replace what is stored**; a firewall page is not data (require a real sitemap root tag
/ a JSON content type, otherwise the run failed); and every request obeys the two rules of §7.5
(no redirect to another host, no private address). **A part that does not apply is switched off
in the configuration** (`off`, §7.4): it never runs, by schedule or by hand (`manage.py run-once`
answers `skipped: …`), its flow is disabled and its card, if it has one, hidden. A daily job
that fails is tried again 10 minutes later, three more times at the most, and then waits for the
next day; a fault that lasts shows as a late flow, not as requests all day.

**Sitemap (`טעינת מפת האתר`)**, nightly. Off with `"off": ["sitemap"]` (a site without one); the
rotation and the card `slowCard` ("העמודים הכבדים באתר") go with it.

1. Find it: every `Sitemap:` line of `/robots.txt`; if there is none try `/sitemap_index.xml`,
   `/wp-sitemap.xml`, `/sitemap.xml`, and take the first that parses as `<sitemapindex>` or `<urlset>`.
2. Follow index files (at most 500 files; 10 MB each after decompression, `SH_SITEMAP_MB` in
   the worker's environment raises that up to 50). Decide gzip by the first two bytes (`1f 8b`),
   not by the file name. Refuse a document that is not UTF-8, holds a NUL byte (UTF-16 without
   its mark) or contains `<!ENTITY`.
3. From each `<url>` take only its **direct child** `<loc>` (SEO plugins nest `<image:loc>` inside;
   those are pictures, not pages). Child sitemap addresses are followed exactly as written,
   including their query strings.
4. Keep page URLs on the site's own host (with or without `www`); drop any page URL that has a
   query string or a fragment; drop non-HTML files; drop cart, checkout, account, search, feed,
   tag, author and paginated pages by their **first path segment** after decoding (shop slugs are
   often translated: put the site's real slugs into `private_paths`). Always include the home page.
5. If any file fails to load or parse, abort the whole load and keep yesterday's list. Refuse a
   load in which the sitemap files list no usable page (the home page that is always added does
   not count), a list of more than 50,000 pages (such a site needs `"off": ["sitemap"]` or a
   larger limit in the code), and a list smaller than half of the number of active pages (almost
   always a fetch problem). Then hand the full list to `sh_sitemap_set` in one call. Sitemap
   files are fetched only from the site's own host: a `Sitemap:` line that names another host
   is ignored, an index that lists a file on another host aborts the load, and a redirect is
   followed only as rule 1 of §7.5 allows.

The rotation measures 2 pages every 5 minutes: up to 576 pages a day (a slot that passes while a
slow call is still running is not made up for). When the site has more pages, raise it up to 6
per round (up to 1,728 a day); beyond that tell the owner and reword the sentence "כל האתר בערך
פעם ביום" on the screen. The coverage line shows the truth either way.

**Broken products (`בדיקת מוצרים שבורים`)**, daily at 04:00, shops only. Off with `"platform":
"other"` or `"off": ["catalogue"]`.

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

  A product can have more than one label; `בלי מחיר`, `בלי תמונה` and `לא במלאי` apply to every
  product type. Names arrive with HTML entities: unescape them before storing. If the shop hides out-of-stock products from its catalogue, they are not in the answer
  and `לא במלאי` never appears; that is the shop's setting, not a fault of the check.
- Shopify: `GET <site>/products.json?limit=250&page=N` until an empty page (an unofficial but
  public endpoint: no total, so cross-check the count against the number of `/products/` addresses
  in the sitemap and abort when they differ by more than 2%, or 3 products). No variant
  with `available` → `לא במלאי`; no `images` → `בלי תמונה`; every variant priced 0 or empty → `בלי מחיר`.
  **The Shopify branch has never run against a real shop**: it is tested only against the kit's
  fake (`fake_site.py --platform shopify`). Say so to the owner of a Shopify shop, and look at
  the first real read together with them.
- **Never store a partial snapshot.** Abort and keep yesterday's data when the number of products
  read differs from the declared total, when the total header is missing, when ids repeat, or
  when the catalogue comes back with no products at all. A partial read looks exactly like
  products that vanished. (A complete read that finds no broken product is a good snapshot.)
- The catalogue is held in memory until it is proven complete, inside the process that also
  serves the screen: keep of each product only the fields the rules read, and stop a read at 10
  MB for one page or 300 MB for all of them.
- Rows are returned with the real faults first and `לא במלאי` last, because the screen shows only
  the first 60. "Out of stock" is not always a fault, but a visitor who sees it leaves; that is
  why it is listed, in yellow.

**Certificate (`בדיקת תעודת האבטחה`)**, daily. Open a TLS connection to `<host>:443` with normal
verification, read `notBefore` / `notAfter` / issuer, store `days_left`. A failed check stores
`ok = false` with the error and does not beat the flow. Off, and never run, for a site whose
address is `http://`, or with `"off": ["cert"]`.

**Real users (`מהירות אצל לקוחות`)**. Off with `"off": ["real_users"]`. A small script on the
site (`reference/rum/site-health-rum.js`) measures LCP with the browser's `PerformanceObserver`
and sends one beacon per page view when the page is hidden or left: a JSON **string** through
`navigator.sendBeacon`, which goes out as `text/plain` and therefore needs no CORS preflight and
no CORS headers (never send it as `application/json`: Chrome refuses, other browsers preflight).
Fields: `site`, `path`, `lcp` (ms), `test`, plus `ttfb` and `nav`, which the reference does not
store. `site` is the literal `live` on the production host and the host name anywhere else, so
traffic from a staging copy is visible as such on the screen.

**What the owner must be told:** on every page view the visitor's browser connects to the
dashboard's host and sends the page's path (no query string) and its loading time; no cookie and
no identifier, and the dashboard stores no address of the visitor. Whether the site's privacy
policy or consent banner needs a line about it is the owner's decision; they can only make it
when told.

The ingest endpoint is **`POST /m`** (a neutral name: content blockers drop paths called "rum" or
"beacon"). It is public, so every field is hostile:

- read the raw body (it is `text/plain`; a JSON body parser will not see it), at most 1 KB;
- if an `Origin` header is present it decides, otherwise the `Referer`: its host must be the
  site's host (with or without `www`) or one of the extra hosts in the configuration (`rum_hosts`,
  for a staging copy); when both are absent, or `Origin` is the string `null` (sites with a
  strict referrer policy), accept the beacon. This is a noise filter, not security: anyone can
  forge a header;
- keep the row only when `lcp` is between 1 and 60,000 ms; `site` is `live` (or a name of
  `live_hosts`) or one of those configured hosts, never the sender's own text; and `path` (query
  string removed) is at most 300 characters, has no control character, and has no segment,
  decoded and lower-cased, that names an account, checkout, order or admin page (the built-in
  English names plus the site's own slugs from `private_paths`);
- drop a path that may name a person: one that holds an `@`, a UUID, a run of 16 or more
  hexadecimal characters, or a run of 24 or more letters, digits and `_` that mixes letters and
  digits (a hyphen ends a run, so ordinary product slugs survive). The script applies the same
  rule before sending. It is a narrow rule, not a promise: paths that carry identifiers in
  another shape belong in `private_paths`;
- store no IP address, no cookie, no user agent, and ignore any cookie that arrives; limit each
  address to 60 beacons a minute and all addresses together to 300 rows a minute and 20,000 a
  day (`SH_RUM_PER_MINUTE`, `SH_RUM_PER_DAY`), in memory only; `sh_rum_add` itself stores nothing
  once the last 24 hours hold 30,000 rows (§7.2);
- always answer 204, also when the beacon is dropped; store after answering, in small batches.

What the tile's count means: page views that were *measured*. Nothing arrives from browsers
without LCP support (Safari and every iPhone browser before iOS 26.2, December 2025), from tabs
opened in the background, or from visitors with content blockers. It is not a traffic counter.
A p75 over a handful of views is noise; the screen shows it anyway, with the count next to it.

Delivery. Nobody edits a site's configuration files by hand.

- **WordPress:** `python3 manage.py rum-plugin --endpoint https://<dashboard>/m --out
  site-health-rum.zip` (run in the backend folder; no database, no secret) writes the plugin
  `reference/rum/site-health-rum.php` into a ZIP with its two values filled in: the ingest
  address, and the live host, taken from `site_health.config.json` in that folder (or
  `--live-host`). The owner uploads it: Plugins → Add new → Upload plugin → the ZIP →
  Install → Activate; then purges the page cache and excludes the script `site-health-rum` from
  "delay JavaScript" optimizations (or only visitors who interact get measured). The plugin
  prints nothing for signed-in staff, nor on cart, checkout and account pages.
- **Shopify:** `reference/rum/site-health-rum.liquid`: set its two `assign` lines, and the owner
  pastes the file above `</body>` in `layout/theme.liquid` (its header lists the clicks). Never
  run in a real shop; it skips the theme editor but cannot tell staff from visitors.
- **Elsewhere:** one line `window.SiteHealthRum = {endpoint, liveHost}` and the script at the end
  of the page body.
- **When the `?sh_test=1` view does not arrive** within a minute: look at the site's response
  headers for a `Content-Security-Policy`. If there is one, the browser sends nothing until the
  site's developer allows the dashboard's host in `connect-src` (and the inline script in
  `script-src`). Then: the page cache was not purged, or a "delay JavaScript" plugin holds the
  script back.

### 7.8 Alert rules (`sh_alerts_check`, every minute, right after the full probe round)

| Kind | Key | Opens when | Closes when | Title · body |
|---|---|---|---|---|
| `down` | `down:<page>` | the newest `down_after` rounds (full or light, not older than 24 hours) of a probe page all failed. `down_after` = 1 unless the owner chose 2 | the newest round of that page answered | `האתר לא עונה: <page>` · `<reason>\n<url>` |
| `slow` | `slow:<page>` | the two newest successful phone runs of a core page both have LCP > 4000 ms | the newest successful run is ≤ 4000 ms | `עמוד איטי: <page>` · `<x.x> שניות עד התוכן, פעמיים ברצף\n<url>` |
| `silent` | `silent:<flow>` | an enabled flow whose `alerts` flag is on, that has run before, is older than its `late_minutes` | it ran again: a successful run newer than the alert | `המדידה נעצרה: <flow>` · `אין מדידה כבר <span>` |
| `cert` | `cert:<host>` | the last successful check shows fewer than 14 days | 14 days or more | `תעודת האבטחה פגה בעוד <N> ימים` (2: `יומיים`, 1: `יום`, 0: `פחות מיום`; past: `תוקף תעודת האבטחה פג`) · `<host>` |

- Opening inserts an alert row and a message (`kind` `התראה`, `event` `open`). Closing sets
  `closed_at` and inserts a message (`kind` `חזר לתקין`, `event` `close`) titled `חזר לתקין:
  <page>`, `חזר לתקין: <flow>` or `חזר לתקין: תעודת האבטחה`, with the text `<the alert's
  title>\nנמשך <span>`. Title and text are stored as the phone shows them; the sender adds nothing.
- `<span>` comes from one helper (`sh_span`): whole minutes, never less than one, in natural
  Hebrew (`דקה`, `שתי דקות`, `5 דקות`, `שעה`, `שעתיים`, `3 שעות`, `יום`, `יומיים`, `3 ימים`). The
  length of an alert is rounded to the nearest minute; the age of a silent flow is rounded down.
- **One alert per page.** When the whole site is down, each probe page opens its own alert and
  its own push. That is intended (the alerts say which pages answer again, and when); the
  hand-over note tells the owner to expect one push per probe page, not one in all.
- **The real-user flow never pushes a `silent` alert** (`alerts` off): a small site has no
  visitors for hours every night, and that is not a fault. Its state still shows on the screen.
- An open alert whose subject is gone (the page left the configuration, the flow was disabled,
  the host changed) is closed like any other; otherwise it could never close.
- **Insert, do not upsert.** The unique index on `key` is partial (open alerts only), and an
  upsert with `on conflict (key)` fails against a partial index on the REST interface. Look for an
  open row; insert when there is none.
- Other parts of the owner's system may add their own alert kinds to the same table; this
  function never touches them. The vendor role sees only the four kinds above (§8).
- **Morning message**, once a day when the configured time (default 07:30 local) has passed (if
  the worker was down at that minute it is still sent later that day):
  `kind` `בוקר`, priority 2. Title `בוקר טוב: האתר תקין`, or `בוקר טוב: התראה פתוחה אחת` /
  `בוקר טוב: <N> התראות פתוחות`, or `בוקר טוב: אין מדידות` when there was no check in the last 24
  hours and nothing is open (nothing measured is not "fine"). Lines: `זמינות <P>% ב-24 שעות` (or `אין בדיקות זמינות ב-24 שעות`),
  `נפילות: <N> (<M> דקות)` only when there were outages, `מהירות עמוד הבית: <verdict>` only when
  measured. The figures come from the same functions the screen uses. Besides being useful, it is
  the owner's daily proof that the channel works. **None on a new installation:** until the
  oldest stored probe round is 6 hours old `sh_morning` queues nothing and the day still counts
  as done, so the first push an owner ever gets is not "nothing was measured".

### 7.9 Push notifications (ntfy)

Alerts go to phones through [ntfy](https://ntfy.sh): each person installs the ntfy app and
subscribes to one topic; the system publishes to that topic.

- **The topic never passes through the agent.** Its name is the only secret of a free ntfy
  topic: anyone who knows it can read the last 12 hours of alerts and publish fake ones. The
  owner makes it up and types it in three places only: the ntfy app of every phone, the host's
  settings (`NTFY_TOPIC`), and the watchdog of §7.10 (the database's secret store, or the
  environment of `watchdog.py`). Never in the repository, on the screen, in a log, a chat
  message or the agent's terminal. `OWNER-STEPS.md` step 6 has the recipe for the name, the
  owner's steps for each phone as a ready message, and the three ways to see that a phone
  really shows a push (the agent cannot send one). (`manage.py new-secret --out <file>` writes a
  random topic and share token to a file without printing them: for an owner who runs Python on
  their own computer.) The topic is set **last**, after a first clean round (§7.5).
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
- HTTP 200 means ntfy accepted the message, not that a phone showed it; there is no delivery
  receipt. Record the result of every attempt with `sh_message_sent(id, status)`: a 2xx status
  settles the message as sent; **0 means "pushing is not configured"** and settles it at once as
  not sent; any other status (use 599 for a network error or a timeout) is a failed attempt, and
  the message is offered again once its two-minute claim has lapsed, until 5 attempts have failed
  (about ten minutes in all). Then it stays in the log as "לא נשלחה". Log every refusal with its
  HTTP status, never with the topic. The click link (`<dashboard>/site`) is added by the sender;
  the database does not know the dashboard's address.
- **Send at most 30 pushes per rolling hour** (publish attempts are what is counted). The free
  server allows 250 a day per sending address, and a flapping page with `down_after = 1` can
  produce two messages a minute. A message that has waited more than an hour since the sender
  first received it is settled as not sent instead of arriving late in a burst.
- Tags: `rotating_light` for priority 4, `warning` for priority 3, `white_check_mark` for a
  recovery, `sunrise` for the morning message.
- Without `NTFY_TOPIC` nothing is sent and every message is settled with status 0.
- Tell the owner two things at hand-over: ntfy keeps messages for 12 hours, so a phone that was
  off longer never gets them (the screen's message log is the permanent record); and iPhones
  deliver ntfy pushes less reliably than Android. The reference has no other channel.

### 7.10 Who watches the watcher

If the worker loop dies, nobody evaluates `silent`. Add one independent check; pick by what the
platform has. Options 1 and 3 push `המדידה נעצרה: בודק זמינות האתר` to the owner's topic once the
newest full probe round is more than 10 minutes old, and `חזר לתקין: בודק זמינות האתר` when rounds
arrive again; option 2 speaks through a channel of its own.

1. **Database scheduler** (Supabase: `pg_cron` + `pg_net` + Vault): `reference/deadman.sql`. Every
   5 minutes a job runs `sh_deadman()`, which opens the alert `silent:בודק זמינות האתר` and
   publishes straight to ntfy with `net.http_post`; it reads the topic from the database's secret
   store, never offers its own message to the returning worker, learns ntfy's answer one run
   later (pg_net is asynchronous), and pushes the recovery when probes resume. The kit's tests
   run its logic against stand-ins for the three extensions only; that anything is really
   scheduled and sent must be seen on the real project, as its header says. It cannot see a
   database that is itself down.
2. **An external heartbeat service** (for example healthchecks.io): the worker requests the
   service's ping address (`HEARTBEAT_URL`) after every full round; the service alerts when pings
   stop, through its own channel and in its own words. `fake_site.py` counts the pings it gets
   (`/__fake`), which proves the pinging and nothing more.
3. **`reference/watchdog.py`**, for any host: one file, standard library only, no database. It
   reads the dashboard's public `/health` and pushes the two messages to the same topic (it also
   alarms when `/health` gives no usable answer for 10 minutes). `python3 watchdog.py --dashboard
   https://<dashboard>` is one look, for a cron job every 5 minutes; `--loop` looks every minute
   as a second small always-on service. The topic comes from its environment only
   (`NTFY_TOPIC`; optional `NTFY_URL`, `NTFY_TOKEN`). Run it somewhere that does not stop when the
   dashboard's host stops. Its pushes are not in the screen's message log.

**What a pass looks like** (go-live checklist, item 3: stop the worker for 16 minutes, then start
it). Option 1: the phone gets `המדידה נעצרה` 10 to 15 minutes after the stop and the screen shows
the alert; after the start, `חזר לתקין` within a minute. It cannot be tried on a local Postgres.
Option 2: the heartbeat service's own notification, and its own "up again". Option 3: the two
pushes, at the watchdog's next look after minute 10 and after the start; it can be rehearsed
locally: the reference server with `COLLECTORS=0`, `python3 collectors.py` as the worker that
is stopped and started, and `fake_site.py` as the site and as ntfy.

Also expose `GET /health` on the server, without login: always status 200 with
`{"ok": …, "db": "ok" | "<error text without host or key>", "screen": "ok" | "missing" | "no
marker" | "not UTF-8", "last_probe_age_sec": <seconds since the last full probe round, or null if
there never was one>}`. `ok` is true only when `db` and `screen` are both `"ok"`; `screen` says
whether the server can serve the screen file (a host that got the backend folder without
`site_health.html` answers `missing`, and `/site` then answers a plain 500 page). Keep the
status 200 even when the database is down; hosts restart a service whose health check fails, and
a restart loop helps nobody.

### 7.11 Running the collectors inside the database platform instead

**Not in the reference, and untested: build it only if the owner asks, and say so.** On Supabase
the collectors could run as scheduled Edge Functions (`pg_cron` calling the function URL through
`pg_net`), so that measuring goes on while the dashboard server restarts: the same functions,
rows and cadences as §7.5–§7.9, written anew for that runtime. The kit holds no code for it. If
you build it, keep the worker loop off (`COLLECTORS=0`), and §7.10 then needs option 2 or 3.

<!-- EOF spec/07-collectors-alerts.md -->
