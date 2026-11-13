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

Who exists is decided by environment variables in the host's settings, never by a file in the
repository:

| Variable | Meaning |
|---|---|
| `SH_PASS_OWNER` | the owner's password. Without it nobody can sign in |
| `SH_PASS_STAFF` | optional: one password for staff |
| `SH_PASS_VENDOR_<NAME>` | one variable per vendor. `<NAME>` is the name in the login log |
| `SH_VENDOR_NOALERTS` | vendor names, comma-separated: these vendors see no alerts at all (`noAlerts`) |
| `SH_SHARE_TOKEN` | the token of the share link. Unset, empty or shorter than 20 characters: no share link |

`SH_VENDOR_NOALERTS` is matched against the `<NAME>` parts without case, with spaces and hyphens
read as `_` (`web agency`, `Web-Agency` and `WEB_AGENCY` all name `SH_PASS_VENDOR_WEB_AGENCY`).
It **fails closed**: while the list holds a name that matches no vendor variable (a typing
mistake), **no vendor sees alerts**, on every request, and the server logs an error at start-up
that names the unmatched entry. A mistake must never show a vendor the alerts he was meant not to see.

### 8.2 Rules (all enforced by the server; the screen's hiding is cosmetic)

**Who gets where**

- **Deny by default for outsiders.** For vendor and share-link requests use an allow-list: pages
  `/site` (or `/status`), `/login`, `/logout`; data calls `GET /api/site`, `GET /api/site/now`,
  `GET /api/site/drill`. Anything else, including any route added later, answers 403 (data) or
  redirects to `/site` (pages). Every request of theirs that is not a `GET` is refused, except
  the sign-in form.
- **Public routes**, answered before any role check: `GET /health`, `POST /m` (real-user ingest),
  `GET` and `POST /login`, `GET /logout`. `POST /m` ignores cookies entirely.
- **Judge the path the router matches.** Compare the allow-lists with the decoded path that the
  framework routes by (in the reference: `request.scope["path"]`), not with a path parsed again
  from a rebuilt address: such a parse stops at an encoded `?` or `#`, so `/login%3Fx` would pass
  the gate as the public `/login` and then reach whatever route matches `/login?x`.
- Vendor filtering of data: `alerts_open` / `alerts_recent` keep only kinds `down`, `slow`,
  `silent`, `cert`; `sh_now().alerts_open` is recounted after filtering; the alert drill returns
  the alert only if its kind is allowed, with `sent` emptied; with `noAlerts` all alert lists are
  empty, the count is 0 and the alert drill returns no rows.
- `POST /api/alerts/ack` accepts only a body whose `Content-Type` is `application/json` (a
  parameter such as `; charset=utf-8` is fine); anything else answers 400 `{"error": "bad request"}`
  before the body is read. `SameSite=Lax` does not stop a page of the same site, and the monitored
  site is one when the screen lives on a sibling subdomain. Such a page can make the owner's
  browser post text or a form with his cookie, but not JSON: that needs a preflight, and nothing
  answers it. An id above 2^63 − 1 (a signed 64-bit integer) is not an id and is left out, so
  the caller never gets an error text of the database for it.

**The share link**

- The share token is compared in constant time, is accepted **only** on `/status` and the three
  data calls, and never counts as "logged in" anywhere else. On those four routes, when `k` is
  present **only the token counts**: a valid one gives the share role even to a signed-in owner, a
  wrong one is refused even with a valid cookie (`/status`: 403 with the line
  `הקישור אינו תקין או שפג תוקפו.`; data calls: 401). On every other route `k` is ignored, so a share
  link alone gets 401 from `/api/messages` and `/api/alerts/ack`.
- **No token, no link; a short token, no link.** An empty configured token disables the link. So
  does one shorter than 20 characters (after trimming): the server logs a warning at start-up
  (without the token) and answers every `k` as wrong. The owner makes the token up
  (`OWNER-STEPS.md` step 6).
- **A wrong token is a failed attempt**, counted in the same per-address limit as a wrong password
  (below). One wrong value counts once within the ten minutes: a tab left open on an old link asks
  again every minute and must not lock its address out, while somebody who guesses sends a new
  value each time. Keep only a digest of the wrong value in memory. While an address is blocked,
  every request from it that carries `k` (a data call, or `/status?k=…`) answers 429 without the
  token being looked at: `/status` with the line `יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.`, a data call
  with `{"error": "too many attempts"}`. `/status` without any `k` is no attempt (403).
- **Keep the token out of the access log.** It travels in the query string (`/status?k=…`, and
  `k=` on every data call of an open share page). The reference removes the query string from
  every line of uvicorn's access log by itself (a filter on the logger `uvicorn.access`, installed
  when `server.py` is imported), whatever the start command is. Under another server program turn
  its access log off or strip query strings from it, and check: after opening the share link, the
  host's log holds no `k=`.

**Passwords and sessions**

- **Passwords** come from environment variables, one per person (§8.1). An unset or blank variable
  never matches. Compare trimmed and case-insensitively (phone keyboards capitalize), in constant
  time. Passwords are **generated**, 16 characters or more: by the password generator of the
  owner's browser or phone, or four unrelated words and six digits (`OWNER-STEPS.md` step 6). The
  owner types them into the host's settings; the builder never sees one. The reference warns at
  start-up about a password shorter than 12 characters (by name, never the password).
- **Session cookie** `sh_session` = `<expiry>.<signature>`: `expiry` is the moment the session
  ends, in whole seconds since 1970 (decimal digits); `signature` is the HMAC-SHA256, in hex, of a
  fixed label + `.` + that expiry, keyed with the person's password as it is compared (trimmed,
  case-folded). On every request the server refuses a cookie whose expiry has passed and one whose
  signature does not fit (constant-time comparison), so the lifetime holds **on the server**, not
  only in the browser: **365 days for owner and staff, 30 days for vendors** (`Max-Age` is the
  same). Changing or deleting a password in the host's settings signs that person out at once.
  There is no session table, so signing out (`/logout`) only removes the cookie from that browser;
  a copy of the value stays good until its expiry or until the password changes. To end every
  session of a person, change the password. `HttpOnly`, `Secure` on HTTPS (trust
  `X-Forwarded-Proto` from the host's proxy), `SameSite=Lax`.
- When two variables hold the same password they produce the same cookie: resolve it, at sign-in
  and on every request, to the **least privileged** role (vendor without alerts, vendor, staff,
  owner), and log a warning at startup. A collision may take rights away, never grant them.
  Without an owner password nobody can sign in.
- **Brute force:** 8 failed attempts (wrong passwords and wrong share tokens together) from one
  address within 10 minutes → 429 for that address until the window passes, for the sign-in form
  and for the share link alike; the password or token is not even looked at. A valid session
  cookie keeps working. Log every sign-in attempt that was examined (`sh_login_log`: time,
  address, success, who, user agent; `who` is `?` for a wrong password); requests refused with 429
  are not logged, so a flood cannot fill the table. A logging failure never blocks sign-in.
- **The client address** behind the host's proxy: use the entry the host itself adds to
  `X-Forwarded-For`, counted from the right (the left-most entry is whatever the client sent and
  lets an attacker dodge the limits). The reference takes the number of proxies in front of the
  server from `SH_PROXY_HOPS` (default 1; 0 = no proxy: the socket peer is used and the header
  ignored). Further rules of the reference:
  - the chosen entry counts only if it **is an IP address** (a port or brackets are cut off:
    `203.0.113.9:4711`, `[2001:db8::1]:443`); anything else is not believed and the socket peer
    is used instead;
  - the address is stored in its shortest spelling and **never longer than 45 characters**; when
    neither the chosen entry nor the socket peer is an IP address (a Unix socket, or a peer that
    uvicorn rewrote from the header, below), the address is `?`: the login log stores `?`, the
    limits count all such requests as one address, and no header text is ever stored;
  - the limits (sign-in, share token, real-user beacons) count an **IPv6 address by its /64**: one
    customer of an internet provider holds a whole /64. The login log still stores the address itself;
  - uvicorn itself replaces the peer's address from `X-Forwarded-For` when the connection comes
    from 127.0.0.1 (its default `--forwarded-allow-ips`). Leave that default alone.
  Check the host's documentation, and verify on the live address: nine wrong passwords, each sent
  with another made-up `X-Forwarded-For`, must end in 429, and the login log must show the
  tester's real address (`tools/check_access.py <address> --limiter` sends the nine and expects
  the 429; look at the login log yourself).

**Checks sign in as a throwaway vendor**

- A check of a deployed server never uses the owner's password, and the builder never holds a
  production secret. For the time of the check the owner adds `SH_PASS_VENDOR_CHECK` (a generated
  throwaway that the builder made up for this one check; read-only like every vendor) to the
  host's settings and deletes it right after (`OWNER-STEPS.md` step 6 has the messages);
  deleting it ends its sessions at once. The reference warns at start-up for as long as a vendor
  variable named `CHECK` or `CHECK_<something>` is set.
- The cookie for `check_screen.js` comes from a sign-in with that password, without printing it:

  ```bash
  COOKIE=$(curl -s -o /dev/null -D - --data-urlencode "p=$SH_PASS_VENDOR_CHECK" "$BASE/login" \
           | tr -d '\r' | sed -n 's/^[Ss]et-[Cc]ookie: \(sh_session=[^;]*\).*/\1/p')
  node check_screen.js "$BASE" --basic --cookie "$COOKIE"
  ```
- **`tools/check_access.py`** is the black-box check of this section, for any implementation in
  any language: `python3 tools/check_access.py <address> [--no-share] [--no-quiet] [--limiter]`.
  Standard library only. It reads its secrets from the environment and never prints them:
  `SH_PASS_VENDOR_CHECK` (required), `SH_SHARE_TOKEN` (required unless `--no-share`),
  `SH_PASS_VENDOR_CHECK_QUIET` (a vendor listed in `SH_VENDOR_NOALERTS`; required unless
  `--no-quiet`), `SH_PASS_OWNER` (optional, read-only use); or ready cookies `SH_COOKIE_VENDOR`,
  `SH_COOKIE_QUIET`, `SH_COOKIE_OWNER` (`name=value`) for a server with another kind of sign-in.
  It covers the outsider allow-list, the scope of the share token, vendor filtering, the vendor
  without alerts, outsiders' pages without `nav` and `links` (with a note when the owner's own
  page has neither, so the check could not be seen at work), `POST /api/alerts/ack` refused for
  outsiders, `POST /m`, `/health` and the headers below. It changes nothing on the server. Exit code 0 only when every check passed
  (1 = a check failed, 2 = it could not run). On the live address:
  `python3 tools/check_access.py https://<address> --no-share --no-quiet`.

**Pages and answers**

- Hebrew texts of the pages around the screen: sign-in button `כניסה`, placeholder `סיסמה`,
  wrong password `סיסמה שגויה`, too many attempts `יותר מדי ניסיונות. נסו שוב בעוד עשר דקות.`,
  bad share link `הקישור אינו תקין או שפג תוקפו.`, database unreachable
  `אין כרגע חיבור לנתונים. נסו שוב בעוד רגע.`, any unforeseen failure (status 500)
  `משהו השתבש. נסו שוב בעוד כמה דקות.`
- The page is served with the role injected at `<!--SH_INJECT-->`:
  `<script>window.SH_CONFIG={…};window.SH_ROLE={…};</script>`. Build it with a JSON encoder; never
  concatenate user input into it. For an outsider (vendor, vendor without alerts, share link) the
  injected `SH_CONFIG` has **no `nav` and no `links` keys at all**: the addresses and labels of
  the owner's other screens never reach their page source, not even hidden. Owner and staff get both.
- **Four headers on every answer** (pages, data, redirects, refusals, 404, 500):
  `X-Robots-Tag: noindex`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`. The page carries the first two as meta tags too. The screen
  links out to pages of the monitored site, and in share mode the screen's own address contains
  the token: it must never travel in a `Referer` header, and no other page may frame the screen.
- **An error never tells a secret.** The text of a failed part (§5.2), of a 502 and of the public
  `/health` is either a sentence the server wrote itself or the message the database sent; of any
  other failure only the type's name is shown (`RuntimeError`). An unforeseen failure answers 500
  with `{"error": "server error"}` (data) or the Hebrew line above (pages), nothing else.

### 8.3 Optional: "view as vendor" for the owner

**Not in the reference, untested; build only if the owner asks.**

A link for the owner that shows the screen exactly as a vendor gets it (a second cookie that the
server honors only together with a valid owner session, and that makes every check above treat
the request as the vendor). Useful before sending a vendor their password.

<!-- EOF spec/08-access.md -->
