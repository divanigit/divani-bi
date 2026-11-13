# Site Health kit — spec: what is measured, and per-site configuration (§3, §4)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

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
| `טעינת מפת האתר` | reads the sitemap so the rotation knows every page | once a night, from 03:00 |
| `בדיקת תעודת האבטחה` | reads the TLS certificate's expiry | once a day, from 04:00 |
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
- **Alert opens** when: one availability check fails (or two in a row, intake question 8); a core page is
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

<!-- EOF spec/03-system.md -->
