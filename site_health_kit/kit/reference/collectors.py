"""Site Health collectors: everything that measures the site and hands rows to the database (spec §7.4-§7.10).

One function per collector, each taking its inputs explicitly, and a scheduler that runs them:

    import collectors; collectors.start()     # daemon threads inside the server (server.py does this)
    python3 collectors.py                     # the same loop as a separate worker process

The database is reached only through db.rpc() and the sh_* write functions. The site's own configuration
comes from sh_config() and is re-read every few minutes. The environment holds secrets only:

    PAGESPEED_KEY    Google PageSpeed Insights key; without it the two speed collectors do not run
    NTFY_TOPIC       the ntfy topic alerts are pushed to; without it messages are logged as not sent
    NTFY_URL         the ntfy server (default https://ntfy.sh)
    NTFY_TOKEN       optional access token of a reserved topic or a self-hosted server
    DASHBOARD_URL    this dashboard's public address: named in the User-Agent, opened by a tap on a push
    HEARTBEAT_URL    optional: requested after every full probe round, for an outside dead-man switch

Nothing here logs a key, a token, the topic or the heartbeat address.
"""
import html
import http.client
import json
import logging
import math
import os
import queue
import re
import socket
import ssl
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ElementTree
import zlib
from collections import deque
from datetime import datetime, time as clock_time, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

import db

log = logging.getLogger("site_health.collectors")

CONFIG_TTL = 300                 # seconds between two reads of sh_config(): a changed page list needs no restart
FAILURE_PAUSE = 1                # seconds a loop rests after a step that raised, at the least
REDIRECTS = 5                    # followed per request; the response after that is taken as it is

# The availability probe (§7.5)
FULL_TIMEOUT, LIGHT_TIMEOUT = 10, 5              # seconds for the whole check, redirects included
STUCK_GRACE = 2                                  # seconds a round waits beyond that for a check that does not return
EXPECT_BYTES = 200_000                           # how much of a page is searched for its "expect" text

# Lab speed (§7.6)
PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_CONNECT, PSI_READ = 10, 120                  # seconds; one call takes 10-60
PSI_BYTES = 30_000_000                           # an answer is 0.5-2 MB (it embeds screenshots)
PSI_WAITS = (5, 10)                              # seconds before the second and the third try of one call
OPPS = 6                                         # reasons kept per run: what the screen shows
ROTATION_PAGES = 2                               # per 5 minutes = 576 pages a day; up to 6 for a larger site (§7.7)
QUOTA_ZONE = ZoneInfo("America/Los_Angeles")     # Google's daily quotas start again at midnight Pacific time
# Audits that are the measurement itself, not a reason for it. "largest-contentful-paint-element"
# (Lighthouse 10-12) reports the whole distance between the LCP and its target as a "saving".
METRIC_AUDITS = {"first-contentful-paint", "largest-contentful-paint", "first-meaningful-paint", "speed-index",
                 "total-blocking-time", "max-potential-fid", "cumulative-layout-shift", "interactive",
                 "interaction-to-next-paint", "largest-contentful-paint-element"}

# Sitemap and catalogue (§7.7)
SITEMAP_FILES, SITEMAP_BYTES = 500, 50 * 1024 * 1024
SITEMAP_PAGES = 50_000                           # one call hands the whole list to the database
SITEMAP_GUESSES = ("/sitemap_index.xml", "/wp-sitemap.xml", "/sitemap.xml")
# First path segments that are never a page to measure. Shop slugs are often translated: the site's
# real ones are added from the configuration ("private_paths").
PRIVATE_PATHS = {"cart", "checkout", "checkouts", "my-account", "account", "search", "feed", "tag", "product-tag",
                 "author", "wp-admin", "wp-json", "wp-login.php"}
NOT_A_PAGE = re.compile(
    r"\.(xml|gz|pdf|jpe?g|png|gif|webp|avif|svg|ico|css|js|json|txt|csv|zip|mp[34]|webm|docx?|xlsx?)$")
PAGINATED = re.compile(r"/page/\d+/?$")
CATALOGUE_BYTES = 30_000_000                     # one page of the catalogue (100 products with descriptions)
CATALOGUE_PAGES = 1000
SHOPIFY_PAUSE = 0.5                              # seconds between two pages: the storefront throttles

# Pushes (§7.9)
PUSH_TIMEOUT = 10
PUSHES_PER_HOUR = 30
PUSH_SECONDS = 45                # no push starts later than this after its round: well inside the two-minute claim
TITLE_MAX, MESSAGE_MAX = 199, 1499               # characters; ntfy counts bytes and a Hebrew letter takes two

# Daily jobs: the local time from which each is owed. The morning message has its time in the configuration.
DAILY_TIMES = {"sitemap": (3, 0), "cleanup": (3, 30), "catalogue": (4, 0), "cert": (4, 0)}   # the screen says the certificate is first checked at 04:00
DAILY_RETRY = timedelta(minutes=10)              # a failed daily job waits this long before its next try

_TLS = ssl.create_default_context()              # normal verification, everywhere


class CollectorError(Exception):
    """A collector could not do its work. The text is for the log."""


class SpeedStopped(Exception):
    """PageSpeed refuses every call: the daily quota is used up (daily), or the key is not accepted."""

    def __init__(self, reason, daily):
        super().__init__(reason)
        self.daily = daily


def _brief(error):
    """An exception in one short line."""
    return ("%s: %s" % (type(error).__name__, error))[:300].replace("\n", " ")


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- the site's configuration

class Config(NamedTuple):
    site: str               # https://example.co.il, no trailing slash
    host: str
    zone: ZoneInfo          # daily jobs go by the local hour of this zone
    platform: str           # woocommerce | shopify | other
    morning: tuple          # (hour, minute) of the morning message
    probe: list             # the pages checked every minute: [{name, url, expect}]
    core: list              # the pages whose speed is measured every 15 minutes
    private: frozenset      # first path segments the sitemap load drops


def read_config():
    """The site as sh_config() describes it, or None while sh_setup has not run."""
    config = db.rpc("sh_config") or {}
    if not config.get("time_zone"):
        return None
    hour, minute = str(config.get("morning") or "07:30").split(":")
    extra = config.get("private_paths")
    return Config(
        site=config["site"].rstrip("/"), host=config["host"], zone=ZoneInfo(config["time_zone"]),
        platform=config.get("platform") or "other", morning=(int(hour), int(minute)),
        probe=[page for page in config["pages"] if page.get("probe")],
        core=[page for page in config["pages"] if page.get("core")],
        private=frozenset(PRIVATE_PATHS | {str(slug).strip("/").lower() for slug in extra or []}))


# ---------------------------------------------------------------- one HTTP exchange

class Answer(NamedTuple):
    status: int
    headers: http.client.HTTPMessage
    body: bytes             # at most the bytes that were asked for
    waited: float           # seconds from the start until the headers of the final response arrived


def user_agent():
    dashboard = os.environ.get("DASHBOARD_URL", "").strip()
    return "SiteHealthProbe/1.0 (+%s)" % dashboard if dashboard else "SiteHealthProbe/1.0"


def fetch(url, *, timeout, read=0, method="GET", headers=None, data=None, redirects=REDIRECTS, connect=None):
    """One request, as a plain and polite client: a fresh connection for every hop, at most `redirects`
    redirects followed, and one deadline of `timeout` seconds for all of it, the body included.
    At most `read` bytes of the body are read; the rest is never downloaded.

    Raises TimeoutError when the deadline passes, another OSError or http.client.HTTPException when
    the connection fails (name resolution, TLS, reset), ValueError for an address that is not http(s)."""
    started = time.monotonic()
    deadline = started + timeout
    sent = {"User-Agent": user_agent(), "Accept-Encoding": "identity", "Connection": "close", **(headers or {})}
    for hop in range(redirects + 1):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("not an http(s) address")
        patience = min(_left(deadline), connect or timeout)
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=patience, context=_TLS)
        else:
            connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=patience)
        try:
            connection.connect()
            link = connection.sock              # kept: http.client lets go of it once the answer says "close"
            link.settimeout(_left(deadline))
            # a path may arrive unescaped (a Hebrew slug typed into the configuration)
            target = urllib.parse.quote(parts.path or "/", safe="/%:@!$&'()*+,;=~")
            if parts.query:
                target += "?" + urllib.parse.quote(parts.query, safe="/%:@!$&'()*+,;=~?")
            connection.request(method, target, body=data, headers=sent)
            response = connection.getresponse()
            waited = time.monotonic() - started
            location = response.getheader("Location")
            if response.status in (301, 302, 303, 307, 308) and location and hop < redirects:
                url = urllib.parse.urljoin(url, location)
                continue
            chunks, size = [], 0
            while size < read and not response.isclosed():      # closed: the whole body has been read
                link.settimeout(_left(deadline))
                chunk = response.read1(min(65536, read - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            return Answer(response.status, response.headers, b"".join(chunks), waited)
        finally:
            connection.close()


def _left(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("timed out")
    return left


def _unzip(raw, limit):
    """`raw` without its gzip wrapping, decided by its first two bytes and never by a name or a
    header, and cut at limit + 1 bytes so that a small file cannot unfold into a huge one."""
    for _ in range(2):                          # a .gz file may be compressed once more on the way
        if raw[:2] != b"\x1f\x8b":
            break
        try:
            raw = zlib.decompressobj(31).decompress(raw, limit + 1)
        except zlib.error as e:
            raise CollectorError("a gzip file that cannot be opened (%s)" % e) from None
    return raw


# ---------------------------------------------------------------- availability probe (§7.5)

def probe_check(page, timeout):
    """One check of one page: the row sh_probe_add stores. ms is the time until the headers of the
    final response, which is what a new visitor's first request waits for."""
    row = {"page": page["name"], "url": page["url"], "ok": False, "status": None, "ms": None, "fail": None, "err": None}
    expect = page.get("expect")
    started = time.monotonic()
    try:
        answer = fetch(page["url"], timeout=timeout, read=EXPECT_BYTES if expect else 0,
                       headers={"Accept": "text/html,*/*;q=0.8", "Cache-Control": "no-cache"})
    except TimeoutError:
        row.update(fail="timeout", err="no answer within %g seconds" % timeout)
    except (OSError, http.client.HTTPException, ValueError) as e:
        row.update(fail="connect", err=_brief(e))
    else:
        row.update(status=answer.status, ms=round(answer.waited * 1000))
        if answer.status != 200:
            row.update(fail="http", err="redirected more than %d times, or to nowhere" % REDIRECTS
                       if 300 <= answer.status < 400 else None)
        elif expect and expect not in _page_text(answer):
            row.update(fail="content", err="the expected text is not on the page")
        else:
            row["ok"] = True
    if row["ms"] is None:
        row["ms"] = round((time.monotonic() - started) * 1000)          # the time until the failure
    return row


def _page_text(answer):
    body = answer.body
    if (answer.headers.get("Content-Encoding") or "").lower() in ("gzip", "x-gzip", "deflate"):
        try:                                    # identity was asked for; some servers compress anyway
            body = zlib.decompressobj(47).decompress(body, EXPECT_BYTES)
        except zlib.error:
            pass
    try:
        return body.decode(answer.headers.get_content_charset() or "utf-8", "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def probe_round(pages, kind, at, timeout=None):
    """One round: every probe page at the same moment, stored under `at`, the scheduled second.
    kind is "full" (counted in availability) or "light" (the half-minute look: no response time).
    Returns {"rows", "stored"}; stored is 0 when another worker already stored this round."""
    timeout = timeout or (FULL_TIMEOUT if kind == "full" else LIGHT_TIMEOUT)
    rows = [None] * len(pages)

    def check(i):
        rows[i] = probe_check(pages[i], timeout)

    threads = [threading.Thread(target=check, args=(i,), daemon=True) for i in range(len(pages))]
    for thread in threads:
        thread.start()
    patience = time.monotonic() + timeout + STUCK_GRACE         # no socket timeout bounds a name lookup
    for thread in threads:
        thread.join(max(0.0, patience - time.monotonic()))
    for i, page in enumerate(pages):
        if rows[i] is None:
            rows[i] = {"page": page["name"], "url": page["url"], "ok": False, "status": None,
                       "ms": round(timeout * 1000), "fail": "timeout", "err": "no answer within %g seconds" % timeout}
        if kind == "light":
            rows[i]["ms"] = None
    stored = db.rpc("sh_probe_add", {"p_round_at": at.isoformat(), "p_kind": kind, "p_rows": rows})["n"]
    return {"rows": rows, "stored": stored}


def heartbeat():
    """The outside dead-man switch of §7.10: one request to HEARTBEAT_URL after a full round."""
    address = os.environ.get("HEARTBEAT_URL", "").strip()
    if not address:
        return
    try:
        fetch(address, timeout=10)
    except (OSError, http.client.HTTPException, ValueError) as e:
        log.warning("heartbeat: the ping did not get through (%s)", type(e).__name__)      # the address is a secret


# ---------------------------------------------------------------- lab speed (§7.6)

def _number(value):
    """A real number, or None: JSON may carry text, true, NaN or Infinity where a number belongs."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _rounded(value, digits=None):
    return None if value is None else round(value, digits)


def speed_row(answer):
    """The stored columns of one PageSpeed answer (the parsed JSON of a 200). A missing value is
    None, never 0. A run whose test failed, or that has no LCP, is a failed run: ok False and err."""
    lighthouse = _dict(answer.get("lighthouseResult"))
    audits = _dict(lighthouse.get("audits"))

    def value(audit):
        return _number(_dict(audits.get(audit)).get("numericValue"))

    error = _dict(lighthouse.get("runtimeError"))
    if error.get("code") not in (None, "NO_ERROR"):
        return _failed_run("%s: %s" % (error.get("code"), error.get("message")))
    lcp = value("largest-contentful-paint")
    if lcp is None:
        return _failed_run("the answer has no Largest Contentful Paint")
    score = _number(_dict(_dict(lighthouse.get("categories")).get("performance")).get("score"))
    ttfb = value("server-response-time")
    if ttfb is None:
        items = _dict(_dict(audits.get("metrics")).get("details")).get("items")
        ttfb = _number(_dict(items[0]).get("timeToFirstByte")) if isinstance(items, list) and items else None
    # Real-user data is optional, and on origin_fallback it describes the whole site, not this page.
    field = _dict(answer.get("loadingExperience"))
    field_lcp = _dict(_dict(field.get("metrics")).get("LARGEST_CONTENTFUL_PAINT_MS"))
    category = None if field.get("origin_fallback") else field_lcp.get("category")
    percentile = None if field.get("origin_fallback") else _number(field_lcp.get("percentile"))
    version = lighthouse.get("lighthouseVersion")
    return {
        "ok": True, "err": None,
        "score": _rounded(None if score is None else score * 100), "lcp_ms": round(lcp),
        "cls": _rounded(value("cumulative-layout-shift"), 3), "ttfb_ms": _rounded(ttfb),
        "bytes": _rounded(value("total-byte-weight")),
        "crux_category": category if category in ("FAST", "AVERAGE", "SLOW") else None,
        "crux_lcp_ms": _rounded(percentile),
        "opps": _opps(audits), "lh_version": version[:20] if isinstance(version, str) else None}


def _failed_run(reason):
    return {"ok": False, "err": str(reason)[:300]}


def _opps(audits):
    """What slows the page: the failed audits that carry an estimated saving in milliseconds,
    largest first. One rule for the classic opportunities (details.overallSavingsMs) and for the
    insight audits of Lighthouse 13 (metricSavings)."""
    found = []
    for audit_id, audit in audits.items():
        if audit_id in METRIC_AUDITS or not isinstance(audit, dict):
            continue
        score = _number(audit.get("score"))
        # a passed audit is no reason, even when it reports a saving (server-response-time does)
        if audit.get("scoreDisplayMode") in ("notApplicable", "manual", "error") or score is None or score >= 0.9:
            continue
        saving = _number(_dict(audit.get("details")).get("overallSavingsMs"))
        if saving is None:
            savings = _dict(audit.get("metricSavings"))
            saving = max((s for s in (_number(savings.get(metric)) for metric in ("LCP", "FCP", "TBT", "INP"))
                          if s is not None), default=None)
        if saving is None and audit.get("numericUnit") == "millisecond":        # other units are bytes or elements
            saving = _number(audit.get("numericValue"))
        if saving and saving > 0:
            title = audit.get("title")
            found.append({"id": str(audit_id)[:80], "title": title[:200] if isinstance(title, str) else None,
                          "ms": round(saving)})
    found.sort(key=lambda opp: (-opp["ms"], opp["id"]))
    return found[:OPPS]


def speed_measure(url, strategy, key):
    """One PageSpeed run of one page: the measured columns of its sh_speed row, also when the run
    failed. Raises SpeedStopped when no call can succeed for now (daily quota, refused key)."""
    query = urllib.parse.urlencode({"url": url, "strategy": strategy, "category": "performance", "locale": "he",
                                    "key": key})
    for wait in (*PSI_WAITS, None):
        status, message, answer = 0, "", None
        try:
            reply = fetch(PSI_URL + "?" + query, timeout=PSI_CONNECT + PSI_READ, connect=PSI_CONNECT,
                          read=PSI_BYTES, redirects=0, headers={"Accept": "application/json"})
            status = reply.status
            answer = json.loads(reply.body)
            message = str(_dict(_dict(answer).get("error")).get("message") or "")
        except ValueError:
            message = "the answer is not JSON"
        except (OSError, http.client.HTTPException) as e:
            message = _brief(e)
        message = message.replace(key, "(key)") if key else message
        if status == 200 and isinstance(answer, dict) and not message:
            return speed_row(answer)
        if status == 429 and "per day" in message:
            raise SpeedStopped(message, daily=True)
        if status == 403 or (status == 400 and "API key" in message):
            raise SpeedStopped(message, daily=False)
        if message.startswith("Lighthouse returned error"):     # the test ran and failed: that is the result
            return _failed_run(message)
        if (status == 429 or status >= 500 or status in (0, 200)) and wait is not None:
            time.sleep(wait)
            continue
        return _failed_run("HTTP %d: %s" % (status, message) if status else message)


def _speed_store(row, url, page, strategy, source, at):
    row = dict(row, at=at.isoformat(), url=url, page=page, strategy=strategy, source=source)
    db.rpc("sh_speed_add", {"p_rows": [row]})
    return row


def speed_core(pages, strategy, at, key):
    """Measures every core page, one call at a time, and stores each run as soon as it is back.
    `at` is the scheduled time of the round: a round that is repeated lands on the same rows."""
    return [_speed_store(speed_measure(page["url"], strategy, key), page["url"], page["name"], strategy, "core", at)
            for page in pages]


def speed_rotation(count, at, key):
    """Measures the `count` pages of the site that waited longest, on a phone."""
    return [_speed_store(speed_measure(url, "mobile", key), url, None, "mobile", "rotation", at)
            for url in db.rpc("sh_rotation_next", {"p_n": count}) or []]


# ---------------------------------------------------------------- sitemap (§7.7)

def sitemap_load(site, private=frozenset(PRIVATE_PATHS)):
    """Every page of the site, from its sitemap, the home page first. Any file that fails to load
    or to parse raises, and so does a sitemap without pages: a partial list is never stored."""
    home = urllib.parse.urlsplit(site)
    parsed = {}
    waiting = [address for address in _robots_sitemaps(site) if _same_host(address, home)]
    if not waiting:
        for guess in SITEMAP_GUESSES:           # the first one that really is a sitemap
            try:
                parsed[site + guess] = _sitemap_read(site + guess)
            except (CollectorError, OSError, http.client.HTTPException):
                continue
            waiting = [site + guess]
            break
        else:
            raise CollectorError("no sitemap: robots.txt names none, and none of %s is one"
                                 % ", ".join(SITEMAP_GUESSES))
    seen, pages = set(), {}
    while waiting:
        address = waiting.pop(0)
        if address in seen:
            continue
        seen.add(address)
        if len(seen) > SITEMAP_FILES:
            raise CollectorError("more than %d sitemap files" % SITEMAP_FILES)
        kind, addresses = parsed.pop(address, None) or _sitemap_read(address)
        if kind == "sitemapindex":
            foreign = [child for child in addresses if not _same_host(child, home)]
            if foreign:                         # fetching whatever a file points at is not ours to do
                raise CollectorError("a sitemap on another host: %s" % foreign[0][:200])
            waiting += addresses                # followed exactly as written, query string and all
        for listed in addresses if kind == "urlset" else ():
            page = _page_url(home, listed, private)
            if page:
                pages[page] = None
        if len(pages) > SITEMAP_PAGES:
            raise CollectorError("more than %d pages in the sitemap" % SITEMAP_PAGES)
    if not pages:                               # an empty read looks exactly like a site whose pages all vanished
        raise CollectorError("the sitemap lists no pages")
    pages.pop(site + "/", None)
    return [site + "/", *pages]                 # the home page is always measured, listed or not


def _same_host(address, home):
    parts = urllib.parse.urlsplit(address)
    return (parts.scheme in ("http", "https")
            and (parts.hostname or "").lower().removeprefix("www.") == home.hostname.lower().removeprefix("www."))


def _robots_sitemaps(site):
    """The address of every "Sitemap:" line of robots.txt; none when there is no robots.txt."""
    try:
        answer = fetch(site + "/robots.txt", timeout=15, read=500_000)
    except (OSError, http.client.HTTPException):
        return []
    if answer.status != 200:
        return []
    found = []
    for line in answer.body.decode("utf-8", "replace").splitlines():
        key, colon, value = line.partition(":")
        if colon and key.strip().lower() == "sitemap" and value.strip():
            found.append(urllib.parse.urljoin(site + "/", value.strip()))
    return found


def _sitemap_read(address):
    """One sitemap file: ("sitemapindex" | "urlset", the addresses it lists)."""
    answer = fetch(address, timeout=60, read=SITEMAP_BYTES + 1,
                   headers={"Accept": "application/xml,text/xml,*/*;q=0.8"})
    if answer.status != 200:
        raise CollectorError("HTTP %d for %s" % (answer.status, address[:200]))
    raw = _unzip(answer.body, SITEMAP_BYTES)
    if len(raw) > SITEMAP_BYTES:
        raise CollectorError("a sitemap file of more than 50 MB: %s" % address[:200])
    try:
        raw.decode("utf-8")                     # the protocol says UTF-8; it also keeps the next test honest
    except UnicodeDecodeError:
        raise CollectorError("a sitemap that is not UTF-8: %s" % address[:200]) from None
    if b"<!ENTITY" in raw:                      # the parser would expand them
        raise CollectorError("a sitemap that declares entities is refused: %s" % address[:200])
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as e:         # a firewall's page is not a sitemap
        raise CollectorError("not XML (%s): %s" % (e, address[:200])) from None
    space, brace, kind = root.tag.rpartition("}")          # "{namespace}urlset"
    if kind not in ("sitemapindex", "urlset"):
        raise CollectorError("not a sitemap (<%s>): %s" % (kind[:40], address[:200]))
    entry_tag = space + brace + ("sitemap" if kind == "sitemapindex" else "url")
    addresses = []
    for entry in root:
        if entry.tag != entry_tag:
            continue
        # only the direct child, in the sitemap's own namespace: SEO plugins nest <image:loc>
        # inside every <url>, and those are pictures
        text = next((child.text for child in entry if child.tag == space + brace + "loc"), None)
        if text and text.strip():
            addresses.append(text.strip())
    return kind, addresses


def _page_url(home, address, private):
    """A page address as the rotation stores it (on the site's own scheme and host), or None for
    what is not a page to measure: another host, a query string, a file, a private or paginated page."""
    parts = urllib.parse.urlsplit(address)
    if not _same_host(address, home) or parts.query or parts.fragment:
        return None
    path = parts.path or "/"
    readable = urllib.parse.unquote(path).lower()               # translated slugs arrive percent-encoded
    first = readable.strip("/").split("/")[0]
    if first in private or PAGINATED.search(readable) or NOT_A_PAGE.search(readable):
        return None
    return urllib.parse.urlunsplit((home.scheme, home.netloc, path, "", ""))


# ---------------------------------------------------------------- broken products (§7.7)

def _catalogue_page(address):
    """One page of a public catalogue: (parsed JSON, headers). Anything but a 200 with a JSON
    content type is a failed read: a firewall's challenge page must never count as "no products"."""
    answer = fetch(address, timeout=60, read=CATALOGUE_BYTES + 1, headers={"Accept": "application/json"})
    if answer.status != 200:
        raise CollectorError("HTTP %d from the catalogue" % answer.status)
    if "json" not in (answer.headers.get("Content-Type") or "").lower():
        raise CollectorError("the catalogue did not answer with JSON (a firewall or a login page?)")
    body = _unzip(answer.body, CATALOGUE_BYTES)
    if len(body) > CATALOGUE_BYTES:
        raise CollectorError("a catalogue page of more than %d bytes" % CATALOGUE_BYTES)
    try:
        return json.loads(body), answer.headers
    except ValueError:
        raise CollectorError("the catalogue's answer is not JSON") from None


def _complete(products, declared):
    """Never a partial snapshot: a read that lost products looks exactly like products that vanished."""
    if not products or not all(isinstance(product, dict) and "id" in product for product in products):
        raise CollectorError("the catalogue lists no products")
    if declared is not None and len(products) != declared:
        raise CollectorError("the shop declared %d products and %d were read" % (declared, len(products)))
    if len({str(product["id"]) for product in products}) != len(products):
        raise CollectorError("a product was read twice: the catalogue changed while it was read")


def _priced(amount):
    """False for no price: the Store API sends "0" for a product without one, not an empty string."""
    try:
        return float(amount) > 0
    except (TypeError, ValueError):
        return False


def _issue(product_id, issue, name, url):
    url = url if isinstance(url, str) and url.startswith(("http://", "https://")) else None
    return {"product_id": str(product_id)[:40], "issue": issue, "name": str(name or "")[:300],
            "url": url and url.split("?")[0].split("#")[0][:500]}


def catalogue_woocommerce(site):
    """The broken products of a WooCommerce shop, read from its public Store API: the rows of
    sh_issues_set. Raises unless the whole catalogue was read."""
    products, declared = [], None
    for page in range(1, CATALOGUE_PAGES + 1):
        # 100 is the API's maximum, and the fixed order keeps the pages stable while the shop changes
        batch, headers = _catalogue_page(
            "%s/wp-json/wc/store/v1/products?per_page=100&page=%d&orderby=id&order=asc" % (site, page))
        total = headers.get("X-WP-Total") or ""
        if not (total.isascii() and total.isdigit()) or not isinstance(batch, list):
            raise CollectorError("the catalogue declares no total (X-WP-Total): its completeness cannot be proven")
        if declared not in (None, int(total)):
            raise CollectorError("the catalogue changed while it was read")
        declared = int(total)
        products += batch
        if not batch or len(products) >= declared:
            break
    _complete(products, declared)
    rows = []
    for product in products:
        priced = _priced(_dict(product.get("prices")).get("price"))
        buyable, in_stock = product.get("is_purchasable") is not False, product.get("is_in_stock") is not False
        issues = [("בלי מחיר", not priced and not buyable),
                  ("בלי תמונה", product.get("images") == []),
                  ("לא במלאי", not in_stock),
                  # external and grouped products are never purchasable, by design
                  ("אי אפשר להוסיף לסל", not buyable and in_stock and priced
                   and product.get("type") not in ("external", "grouped"))]
        name = html.unescape(str(product.get("name") or ""))    # names arrive with HTML entities
        rows += [_issue(product["id"], issue, name, product.get("permalink")) for issue, found in issues if found]
    return rows


def catalogue_shopify(site, expected):
    """The broken products of a Shopify shop, from /products.json. That endpoint declares no total,
    so the count is checked against `expected`, the number of product pages in the sitemap."""
    products = []
    for page in range(1, CATALOGUE_PAGES + 1):
        answer, _ = _catalogue_page("%s/products.json?limit=250&page=%d" % (site, page))
        batch = _dict(answer).get("products")
        if not isinstance(batch, list):
            raise CollectorError("the catalogue's answer has no product list")
        if not batch:                           # only an empty page ends the read
            break
        products += batch
        time.sleep(SHOPIFY_PAUSE)
    _complete(products, None)
    if abs(len(products) - expected) > max(3, expected // 50):
        raise CollectorError("%d products were read and the sitemap lists %d" % (len(products), expected))
    rows = []
    for product in products:
        variants = [variant for variant in product.get("variants") or [] if isinstance(variant, dict)]
        issues = [("בלי מחיר", not any(_priced(variant.get("price")) for variant in variants)),
                  ("בלי תמונה", not product.get("images")),
                  ("לא במלאי", not any(variant.get("available") for variant in variants))]
        address = "%s/products/%s" % (site, urllib.parse.quote(str(product.get("handle") or "")))
        rows += [_issue(product["id"], issue, product.get("title"), address) for issue, found in issues if found]
    return rows


# ---------------------------------------------------------------- certificate (§7.7)

def cert_row(host, certificate, now):
    """The sh_cert row of a certificate as ssl.getpeercert() describes it."""
    not_before, not_after = (datetime.fromtimestamp(ssl.cert_time_to_seconds(certificate[field]), timezone.utc)
                             for field in ("notBefore", "notAfter"))
    issuer = " ".join(value for part in certificate.get("issuer", ()) for name, value in part
                      if name in ("organizationName", "commonName"))
    return {"host": host, "issuer": issuer[:120], "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(), "days_left": (not_after - now).days, "ok": True, "err": None,
            "checked_at": now.isoformat()}


def cert_check(host, now, port=443):
    """Opens a TLS connection with normal verification and reads the certificate. A failed check
    is a row too: ok False and the reason."""
    try:
        with socket.create_connection((host, port), timeout=20) as link:
            with _TLS.wrap_socket(link, server_hostname=host) as secure:
                return cert_row(host, secure.getpeercert(), now)
    except (OSError, ValueError, KeyError) as e:
        return {"host": host, "ok": False, "err": _brief(e), "checked_at": now.isoformat()}


# ---------------------------------------------------------------- alerts and pushes (§7.8, §7.9)

class Pusher:
    """Publishes the queued messages through ntfy and reports what became of each one.

    sh_alerts_check hands an owed message to one caller and to nobody else for the next two
    minutes (its claim), so two workers that overlap never publish the same message. A message
    that is left untouched here (the hourly cap, the deadline) is simply offered again later."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.published = deque()        # when this process published, for the hourly cap
        self.first_seen = {}            # message id -> when this process was first handed it

    def publish(self, title, message, priority=3, tags=()):
        """One push to the topic: the HTTP status of ntfy, 599 when it could not be reached.
        JSON to the server's root, never to /<topic>: that way no header has to carry Hebrew."""
        env = os.environ
        body = {"topic": env["NTFY_TOPIC"].strip(), "title": title[:TITLE_MAX], "message": message[:MESSAGE_MAX],
                "priority": priority if priority in (1, 2, 3, 4, 5) else 3, "tags": list(tags)}
        if env.get("DASHBOARD_URL", "").strip():
            body["click"] = env["DASHBOARD_URL"].strip().rstrip("/") + "/site"
        headers = {"Content-Type": "application/json"}
        if env.get("NTFY_TOKEN", "").strip():
            headers["Authorization"] = "Bearer " + env["NTFY_TOKEN"].strip()
        try:
            return fetch((env.get("NTFY_URL", "").strip() or "https://ntfy.sh").rstrip("/") + "/", timeout=PUSH_TIMEOUT,
                         method="POST", data=json.dumps(body).encode("utf-8"), headers=headers, redirects=0).status
        except (OSError, http.client.HTTPException, ValueError) as e:
            log.warning("push: ntfy could not be reached (%s)", type(e).__name__)
            return 599

    def push(self, owed, deadline):
        """Sends the messages sh_alerts_check handed over and reports every result with
        sh_message_sent. Nothing is published after `deadline` (a time.time() value): the claim
        must not be outlived. Returns [{id, title, status}] for the messages that were reported."""
        now = self.clock()
        while self.published and now - self.published[0] >= 3600:
            self.published.popleft()
        self.first_seen = {message: seen for message, seen in self.first_seen.items() if now - seen < 7200}
        configured = bool(os.environ.get("NTFY_TOPIC", "").strip())
        room, done = None, []
        for message in owed:
            waited = now - self.first_seen.setdefault(message["id"], now)
            if not configured or waited > 3600:
                # 0 settles a message at once as "not sent": pushing is not configured, or the
                # message waited for more than an hour and would arrive late, in a burst
                status = 0
            else:
                if room is None:
                    room = PUSHES_PER_HOUR - max(len(self.published), self._sent_last_hour())
                if room <= 0 or time.time() > deadline:
                    continue
                room -= 1
                self.published.append(self.clock())
                status = self.publish(*_as_push(message))
            db.rpc("sh_message_sent", {"p_id": message["id"], "p_status": status})
            if status == 0 or 200 <= status < 300:
                del self.first_seen[message["id"]]
            done.append({"id": message["id"], "title": message["title"], "status": status})
        return done

    def _sent_last_hour(self):
        """The pushes of the last hour as the message log has them: they include those of a
        worker that this one replaced a moment ago."""
        now = _now()
        rows = db.rpc("sh_messages", {"p_from": (now - timedelta(hours=1)).isoformat(),
                                      "p_to": (now + timedelta(minutes=1)).isoformat()}) or []
        return sum(1 for row in rows if row.get("sent"))


def _as_push(message):
    """(title, text, priority, tags) of a queued message. The phone must tell a recovery from an
    alarm at a glance, so a "close" carries its label in front of the alert's title."""
    title, event = str(message.get("title") or ""), message.get("event")
    if event == "close":
        title = "%s: %s" % (message.get("kind"), title)
    tag = {"close": "white_check_mark", "morning": "sunrise"}.get(
        event, "rotating_light" if message.get("priority") == 4 else "warning")
    return title, str(message.get("msg") or title), message.get("priority"), [tag]


def alert_tick(pusher, deadline=None):
    """Evaluates the alert rules, then pushes what is owed: until `deadline` (a time.time() value),
    or for PUSH_SECONDS from now."""
    return pusher.push(db.rpc("sh_alerts_check") or [], deadline or time.time() + PUSH_SECONDS)


# ---------------------------------------------------------------- daily jobs

def sitemap_job(config, now):
    pages = sitemap_load(config.site, config.private)
    moment = now.isoformat()
    coverage = [row for row in db.rpc("sh_speed", {"p_from": moment, "p_to": moment}) or []
                if row.get("section") == "כיסוי"]
    known = coverage[0]["slow_runs"] if coverage else 0
    if len(pages) * 2 < known:                  # almost always a fetch problem, not a site that shrank
        raise CollectorError("the sitemap lists %d pages and %d are known: the list is kept" % (len(pages), known))
    return dict(db.rpc("sh_sitemap_set", {"p_urls": pages}), pages=len(pages))


def catalogue_job(config, now):
    if config.platform == "shopify":
        listed = sum(1 for page in sitemap_load(config.site, config.private) if "/products/" in page)
        rows = catalogue_shopify(config.site, listed)
    else:
        rows = catalogue_woocommerce(config.site)
    day = now.astimezone(config.zone).date().isoformat()
    return dict(db.rpc("sh_issues_set", {"p_snap_date": day, "p_rows": rows}), snap_date=day)


def cert_job(config, now):
    row = cert_check(config.host, now)
    db.rpc("sh_cert_set", {"p_row": row})
    if not row["ok"]:                           # stored as a failed check, and tried again
        raise CollectorError("the certificate of %s could not be read: %s" % (config.host, row["err"]))
    return row


def morning_job(config, now):
    """Queues the morning message; the next alert tick pushes it."""
    return db.rpc("sh_morning", {"p_day": now.astimezone(config.zone).date().isoformat()})


def cleanup_job(config, now):
    return db.rpc("sh_cleanup")


DAILY_JOBS = (("sitemap", sitemap_job), ("cleanup", cleanup_job), ("catalogue", catalogue_job), ("cert", cert_job),
              ("morning", morning_job))


def daily_time(job, config):
    """The local (hour, minute) from which a daily job is owed, or None when this site has no use for it."""
    if job == "catalogue" and config.platform not in ("woocommerce", "shopify"):
        return None
    if job == "cert" and not config.site.startswith("https://"):
        return None
    return config.morning if job == "morning" else DAILY_TIMES[job]


class DailySchedule:
    """Runs each daily job once per local day, from its hour on. "Done for this day" lives in the
    database (sh_job_due / sh_job_mark), so a restart does not run a job again; it is marked only
    after the job succeeded, so a failure is tried again; and every job has its own guard."""

    def __init__(self, jobs=DAILY_JOBS):
        self.jobs = jobs
        self.done = {}                  # job -> the local day this process knows to be done: spares the database
        self.again = {}                 # job -> not before this moment, after a failure

    def step(self, config, now):
        """Runs what is owed at `now` (an aware datetime). Returns the names of the jobs that ran and succeeded."""
        local = now.astimezone(config.zone)
        today, ran = local.date(), []
        for job, run in self.jobs:
            start = daily_time(job, config)
            if (start is None or (local.hour, local.minute) < start or self.done.get(job) == today
                    or now < self.again.get(job, now)):
                continue
            try:
                marker = {"p_job": job, "p_day": today.isoformat()}
                if db.rpc("sh_job_due", marker):
                    result = run(config, now)
                    db.rpc("sh_job_mark", marker)
                    ran.append(job)
                    log.info("daily job %s: done (%s)", job, json.dumps(result, ensure_ascii=False, default=str)[:300])
                self.done[job] = today
            except Exception as e:
                self.again[job] = now + DAILY_RETRY
                log.error("daily job %s failed and will be tried again: %s", job, _brief(e))
        return ran


# ---------------------------------------------------------------- the speed schedule

class SpeedSchedule:
    """Phone runs of the core pages every 15 minutes, desktop runs every hour, two pages of the
    rotation every 5 minutes: one call at a time, the core pages first. Each round is stored under
    the start of its slot, so the same round measured twice (two workers during a deploy) is one set of rows."""

    ROUNDS = (("core pages, phone", 900, lambda config, at, key: speed_core(config.core, "mobile", at, key)),
              ("core pages, desktop", 3600, lambda config, at, key: speed_core(config.core, "desktop", at, key)),
              ("rotation", 300, lambda config, at, key: speed_rotation(ROTATION_PAGES, at, key)))

    def __init__(self, key, clock=_now):
        self.key, self.clock = key, clock
        self.done = {}                  # round -> the slot it last ran in
        self.resume = None              # after the daily quota ran out: not before this moment

    def step(self, config):
        """Runs the rounds whose slot has not been run yet. Returns their names."""
        ran = []
        for name, period, run in self.ROUNDS:
            now = self.clock()          # read again: the round before may have taken minutes
            if self.key is None or (self.resume and now < self.resume):
                break
            slot = now.timestamp() // period * period
            if self.done.get(name) == slot:
                continue
            self.done[name] = slot
            try:
                run(config, datetime.fromtimestamp(slot, timezone.utc), self.key)
                ran.append(name)
            except SpeedStopped as e:
                if e.daily:
                    local = now.astimezone(QUOTA_ZONE)
                    self.resume = datetime.combine(local.date() + timedelta(days=1), clock_time(0), QUOTA_ZONE)
                    log.warning("speed: the daily PageSpeed quota is used up, measuring again after %s (%s)",
                                self.resume.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), e)
                else:                   # a configuration error: asking again cannot help
                    self.key = None
                    log.error("speed: PageSpeed does not accept the key, the speed collectors are OFF until "
                              "PAGESPEED_KEY is fixed and the worker restarts (%s)", e)
            except Exception as e:
                log.error("speed: %s failed: %s", name, _brief(e))
        return ran


# ---------------------------------------------------------------- the scheduler

_threads = []
_stop = threading.Event()
_site = {"config": None, "read_at": None, "said": None}
_site_lock = threading.Lock()


def _config():
    """The configuration the loops work with: read again every CONFIG_TTL seconds, the last good
    one when the database does not answer, None while the site is not set up."""
    with _site_lock:
        if _site["read_at"] is None or time.monotonic() - _site["read_at"] >= (CONFIG_TTL if _site["config"] else 30):
            _site["read_at"] = time.monotonic()
            try:
                _site["config"] = read_config()
                problem = None if _site["config"] else (
                    "the site is not configured: load its configuration with manage.py setup")
            except Exception as e:
                problem = "the configuration could not be read (%s)" % _brief(e)
            if problem != _site["said"]:        # said once, not every half minute
                _site["said"] = problem
                if problem:
                    log.warning("collectors: %s", problem)
                else:
                    log.info("collectors: the configuration is loaded")
        return _site["config"]


def _loop(name, step, every):
    """Runs step() until the stop signal, `every` seconds apart. Whatever a step raises costs one
    log line and never the thread."""
    while not _stop.is_set():
        try:
            step()
            _stop.wait(every)
        except Exception as e:
            log.error("%s failed: %s", name, _brief(e))
            _stop.wait(max(every, FAILURE_PAUSE))


def next_round(now):
    """The first scheduled round after `now` (epoch seconds): (its second, "full" or "light").
    A full round at second 0 of every minute, a light one at second 30."""
    at = (now // 30 + 1) * 30
    return at, "light" if at % 60 else "full"


def _probe_step(ticks):
    """Waits for the next round and runs it. The round is stored under its scheduled second, so
    two workers that overlap store it once."""
    at, kind = next_round(time.time())
    if _stop.wait(at - time.time()):
        return
    config = _config()
    if config is None:
        return
    probe_round(config.probe, kind, datetime.fromtimestamp(at, timezone.utc))
    if kind == "full":
        ticks.put(at)


def _alert_step(ticks, pusher):
    """The alert tick, right after each full round, on its own thread: a slow push service must
    not delay the next probe."""
    try:
        at = ticks.get(timeout=1)
    except queue.Empty:
        return
    try:
        if time.time() < at + PUSH_SECONDS:     # a tick that waited too long is left to the next round
            alert_tick(pusher, at + PUSH_SECONDS)
    finally:
        heartbeat()


def _when_configured(step):
    def run():
        config = _config()
        if config is not None:
            step(config)
    return run


def start():
    """Launches the collectors as daemon threads and returns at once, without touching the
    database. A second call does nothing: two sets of collectors must never run in one process."""
    if _threads:
        return _threads
    _log_to_stderr()
    env = {name: bool(os.environ.get(name, "").strip()) for name in ("PAGESPEED_KEY", "NTFY_TOPIC", "HEARTBEAT_URL")}
    ticks, pusher, daily = queue.Queue(), Pusher(), DailySchedule()
    loops = [("probe", lambda: _probe_step(ticks), 0),
             ("alerts", lambda: _alert_step(ticks, pusher), 0),
             ("daily jobs", _when_configured(lambda config: daily.step(config, _now())), 60)]
    if env["PAGESPEED_KEY"]:
        speed = SpeedSchedule(os.environ["PAGESPEED_KEY"].strip())
        loops.append(("speed", _when_configured(speed.step), 20))
    else:
        log.warning("collectors: PAGESPEED_KEY is not set, the speed collectors do not run")
    if not env["NTFY_TOPIC"]:
        log.warning("collectors: NTFY_TOPIC is not set, alerts are logged and nothing is pushed")
    for name, step, every in loops:
        thread = threading.Thread(target=_loop, args=(name, step, every), name="sh-" + name.replace(" ", "-"),
                                  daemon=True)
        thread.start()
        _threads.append(thread)
    log.info("collectors: %s are running (heartbeat ping: %s)", ", ".join(name for name, _, _ in loops),
             "on" if env["HEARTBEAT_URL"] else "off")
    return _threads


def _log_to_stderr():
    """Inside the server nobody prints the "site_health" loggers below WARNING: give them a handler,
    unless the process has set up logging itself."""
    ours = logging.getLogger("site_health")
    if not ours.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        ours.addHandler(handler)
        ours.setLevel(logging.INFO)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
