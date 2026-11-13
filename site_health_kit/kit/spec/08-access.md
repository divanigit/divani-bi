# Site Health kit — spec: sign-in, roles, vendors, the share link (§8)

Part of the Site Health kit. The entry point and the rules of the work are in `START-HERE.md`. Section numbers are the same across all spec files; paths are relative to the kit folder.

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
  `X-Forwarded-For`, counted from the right (the left-most entry is whatever the client sent and
  lets an attacker dodge the limits). The reference takes the number of proxies in front of the
  server from `SH_PROXY_HOPS` (default 1); check the host's documentation and verify on the live
  address that the login log shows real, different addresses.
- **Keep secrets out of the access log.** The share token travels in the query string
  (`/status?k=…`): turn the server's access log off or strip query strings from it.
- Hebrew texts of the pages around the screen: sign-in button `כניסה`, placeholder `סיסמה`,
  wrong password `סיסמה שגויה`, too many attempts `יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.`,
  bad share link `הקישור אינו תקין או שפג.`, database unreachable
  `אין כרגע חיבור לנתונים. נסו שוב בעוד רגע.`
- The page is served with the role injected at `<!--SH_INJECT-->`:
  `<script>window.SH_CONFIG={…};window.SH_ROLE={…};</script>`. Build it with a JSON encoder; never
  concatenate user input into it.
- `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer` on every answer; the page carries
  both as meta tags too. The screen links out to pages of the monitored site, and in share mode
  the screen's own address contains the token: it must never travel in a `Referer` header.

### 8.3 Optional: "view as vendor" for the owner

A link for the owner that shows the screen exactly as a vendor gets it (a second cookie that the
server honors only together with a valid owner session, and that makes every check above treat
the request as the vendor). Useful before sending a vendor their password. Build it only if asked.

<!-- EOF spec/08-access.md -->
