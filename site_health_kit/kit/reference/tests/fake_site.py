"""A small local website for the collector tests, and for trying the kit by hand.

One HTTP server on 127.0.0.1 that plays every outside party the collectors talk to:

    /, /product-category/sofas/, /product/sample-sofa/, /cart/, /checkout/     the monitored pages
    /robots.txt, /sitemap_index.xml and its children                           the sitemap
    /wp-json/wc/store/v1/products                                              a WooCommerce catalogue
    /products.json                                                             a Shopify catalogue
    /pagespeedonline/v5/runPagespeed                                           Google PageSpeed Insights
    /ntfy/                                                                     ntfy (NTFY_URL = <address>/ntfy)
    /hb                                                                        a heartbeat service (HEARTBEAT_URL)

Tests switch behaviour through the attributes of FakeSite. By hand:

    python3 tests/fake_site.py [port [config.json]]     # prints its addresses and how to break a page,
                                                        # and writes a configuration for manage.py setup
"""
import gzip
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PAGES = {"/": "בית", "/product-category/sofas/": "קטגוריה", "/product/sample-sofa/": "מוצר", "/cart/": "סל",
         "/checkout/": "קופה"}
SITEMAP_NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
IMAGE_NS = 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'

# The bodies Google really sends (read live for the two quota / key answers; the Lighthouse failure
# and the backend failure are the documented shapes).
PSI_ERRORS = {
    "quota_day": (429, "RESOURCE_EXHAUSTED",
                  "Quota exceeded for quota metric 'Queries' and limit 'Queries per day' of service "
                  "'pagespeedonline.googleapis.com' for consumer 'project_number:583797351490'."),
    "quota_minute": (429, "RESOURCE_EXHAUSTED",
                     "Quota exceeded for quota metric 'Queries' and limit 'Queries per minute' of service "
                     "'pagespeedonline.googleapis.com' for consumer 'project_number:583797351490'."),
    "bad_key": (400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."),
    "lighthouse_error": (500, None,
                         "Lighthouse returned error: ERRORED_DOCUMENT_REQUEST. Lighthouse was unable to reliably "
                         "load the page you requested. Make sure you are testing the correct URL and that the "
                         "server is properly responding to all requests. (Status code: 403)"),
    "http500": (500, "INTERNAL", "Unable to process request. Please wait a while and try again."),
}


def woo_products(site):
    """A WooCommerce Store API catalogue: one product for each issue label of spec §7.7, the tricky
    cases, and enough healthy products to need a second page (107 in all)."""
    def product(pid, name, **changes):
        base = {"id": pid, "name": name, "type": "simple", "permalink": "%s/product/p-%d/" % (site, pid),
                "prices": {"price": "349000", "regular_price": "349000", "currency_code": "ILS",
                           "currency_minor_unit": 2},
                "images": [{"id": pid * 10, "src": "%s/img/%d.jpg" % (site, pid)}],
                "is_in_stock": True, "is_purchasable": True}
        base.update(changes)
        return base

    no_price = {"price": "0", "regular_price": "0", "currency_code": "ILS", "currency_minor_unit": 2}
    return [
        product(101, "ספה תלת מושבית"),
        product(102, "שולחן בלי מחיר", prices=no_price, is_purchasable=False),          # "0", not empty
        product(103, "מדריך חינם", prices=no_price),                                     # free, and purchasable
        product(104, "כורסה בלי תמונה", images=[]),
        product(105, "שידה שאזלה", is_in_stock=False),
        product(106, "מיטה נעולה", is_purchasable=False),
        product(107, "מוצר שותפים", type="external", is_purchasable=False),              # never purchasable, by design
        product(108, "סט מקובץ", type="grouped", is_purchasable=False),
        product(109, "שולחן &#8211; 160&#215;90 &amp; כיסאות", images=[]),               # HTML entities in the name
        product(110, "ארון בלי תמונה שאזל", images=[], is_in_stock=False),               # two labels
        product(111, "מזנון נעול שאזל", is_in_stock=False, is_purchasable=False),        # out of stock explains it
        product(112, "מדף בלי מחיר", prices=dict(no_price, price=""), is_purchasable=False),
    ] + [product(1000 + i, "מוצר תקין %d" % i) for i in range(1, 96)]


def shopify_products():
    """A Shopify /products.json catalogue: 305 products, so the read needs three requests."""
    def product(pid, title, images=1, **variants):
        variants = variants or {"a": ("129.00", True)}
        return {"id": pid, "title": title, "handle": "p-%d" % pid,
                "images": [{"id": pid * 10 + i, "src": "https://cdn.example/%d-%d.jpg" % (pid, i)}
                           for i in range(images)],
                "variants": [{"id": pid * 100 + i, "title": name, "price": price, "available": available}
                             for i, (name, (price, available)) in enumerate(variants.items())]}

    return [
        product(1, "Sofa"),
        product(2, "Sold out chair", a=("99.00", False), b=("109.00", False)),
        product(3, "Table without a picture", images=0),
        product(4, "Shelf without a price", a=("0.00", True), b=("", True)),
        product(5, "Lamp, one size left", a=("59.00", False), b=("59.00", True)),
    ] + [product(1000 + i, "Product %d" % i) for i in range(1, 301)]


class FakeSite:
    """The server and its switches. Every attribute below may be changed while it runs."""

    def __init__(self, port=0):
        fake = self

        class Handler(_Handler):
            site = fake

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.reset()

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def reset(self):
        # How a path misbehaves: {path: {...}} with any of
        #   status: 502          answer with this status
        #   delay: 2.0           seconds before the headers
        #   body_delay: 2.0      headers at once, the body this much later
        #   hang: 30.0           hold the connection this long and never answer
        #   drop: True           close the connection without a word
        #   redirects: 3         this many redirects before the page
        #   body: "<html>…"      another body
        self.broken = {}
        self.hits = []                    # (method, path with query string, headers) of every request
        self.pushes = []                  # every POST under /ntfy: {"path", "type", "auth", "json"}
        self.ntfy_status = 200            # what the fake ntfy answers
        self.psi = "lighthouse13"         # the PageSpeed answer: lighthouse13 | lighthouse12 | origin_fallback |
        self.psi_calls = []               # no_field_data | runtime_error | a key of PSI_ERRORS; or a list, one per call
        self.catalogue = "ok"             # ok | count_mismatch | no_total | duplicate | html
        self.products = woo_products(self.url)
        self.shopify = shopify_products()
        self.files = self._files()        # robots.txt and the sitemaps: {path, with its query string: (type, bytes)}

    def config(self, **changes):
        """A site_health.config.json for this site."""
        config = {"site": self.url, "label": "fake.example", "time_zone": "Asia/Jerusalem", "platform": "woocommerce",
                  "down_after": 1, "morning": "07:30",
                  "pages": [{"name": name, "url": self.url + path, "home": path == "/", "probe": path != "/checkout/",
                             "core": True, **({"expect": "הוספה לסל"} if name == "מוצר" else {})}
                            for path, name in PAGES.items()]}
        config.update(changes)
        return config

    def _files(self):
        site = self.url
        products = urlset(site, "/product/sample-sofa/", "/product/armchair/", "/product-category/sofas/")
        return {
            "/robots.txt": ("text/plain", ("User-agent: *\nDisallow: /cart/\n\nSitemap: %s/sitemap_index.xml\n"
                                           % site).encode("utf-8")),
            "/sitemap_index.xml": sitemap_index(site, "/page-sitemap.xml", "/product-sitemap.xml",
                                                "/extra-sitemap.xml?from=1&to=9"),
            "/page-sitemap.xml": urlset(
                site, "/", "/about/", "/%D7%A6%D7%95%D7%A8-%D7%A7%D7%A9%D7%A8/",
                "/cart/", "/checkout/", "/my-account/", "/search/", "/feed/", "/tag/sale/", "/author/dana/",
                "/page/2/", "/blog/page/3/", "/%D7%A2%D7%92%D7%9C%D7%94/",        # the last one: a translated cart slug
                "/product/sample-sofa/?utm_source=x", "/about/#team", "/files/catalogue.pdf",
                "https://other.example/landing/"),
            # gzip by content, not by name
            "/product-sitemap.xml": ("application/xml", gzip.compress(products[1])),
            # served only with its query string, as Shopify's child sitemaps are
            "/extra-sitemap.xml?from=1&to=9": urlset(site, "/landing/"),
            # what the collector falls back to when robots.txt names no sitemap
            "/wp-sitemap.xml": sitemap_index(site, "/wp-sitemap-posts-page-1.xml"),
            "/wp-sitemap-posts-page-1.xml": urlset(site, "/", "/wp-page/"),
            "/sitemap.xml": urlset(site, "/plain-page/"),
        }


def urlset(site, *paths):
    """A sitemap file as the SEO plugins write it: (content type, bytes). Every <url> also carries
    the address of a picture, which is not a page."""
    urls = "".join("<url><loc>%s</loc><lastmod>2026-11-01T08:00:00+00:00</lastmod>"
                   "<image:image><image:loc>%s/media/picture/</image:loc></image:image></url>"
                   % (path if "://" in path else site + path, site) for path in paths)
    return ("application/xml", ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset %s %s>%s</urlset>'
                                % (SITEMAP_NS, IMAGE_NS, urls)).encode("utf-8"))


def sitemap_index(site, *paths):
    items = "".join("<sitemap><loc>%s</loc></sitemap>" % (path if "://" in path else site + path).replace("&", "&amp;")
                    for path in paths)
    return ("application/xml", ('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex %s>%s</sitemapindex>'
                                % (SITEMAP_NS, items)).encode("utf-8"))


class _Handler(BaseHTTPRequestHandler):
    site = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")

    def _serve(self, method):
        site, url = self.site, urllib.parse.urlsplit(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        site.hits.append((method, self.path, dict(self.headers)))
        if path == "/__fake":
            return self._control(query)

        broken = site.broken.get(path, {})
        if broken.get("hang"):
            time.sleep(broken["hang"])
            return self._drop()
        if broken.get("drop"):
            return self._drop()
        time.sleep(broken.get("delay", 0))
        if "status" in broken:
            return self._send(broken["status"], "text/html", b"<html><body>broken</body></html>")
        hop = int(query.get("hop", ["0"])[0])
        if hop < broken.get("redirects", 0):
            return self._send(302, "text/html", b"", {"Location": "%s?hop=%d" % (path, hop + 1)})    # a relative one

        if path.startswith("/ntfy") and method == "POST":
            return self._ntfy(path, body)
        if path == "/pagespeedonline/v5/runPagespeed":
            return self._pagespeed(query)
        if path == "/wp-json/wc/store/v1/products":
            return self._woocommerce(query)
        if path == "/products.json":
            return self._shopify(query)
        if path == "/hb":
            return self._send(200, "text/plain", b"OK")
        if self.path in site.files or path in site.files:
            return self._send(200, *site.files.get(self.path) or site.files[path])
        if path in PAGES:
            html = broken.get("body") or (
                '<!DOCTYPE html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>%s</title></head>'
                "<body><h1>%s</h1><button>הוספה לסל</button></body></html>" % (PAGES[path], PAGES[path]))
            return self._send(200, "text/html; charset=utf-8", html.encode("utf-8"), wait=broken.get("body_delay", 0))
        self._send(404, "text/html", b"<html><body>not found</body></html>")

    def _send(self, status, content_type, body, headers=None, wait=0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.flush()
        time.sleep(wait)
        self.wfile.write(body)
        self.close_connection = True

    def _json(self, status, value, headers=None):
        self._send(status, "application/json; charset=utf-8", json.dumps(value, ensure_ascii=False).encode("utf-8"),
                   headers)

    def _drop(self):
        self.close_connection = True

    def _ntfy(self, path, body):
        site = self.site
        try:
            message = json.loads(body)
        except ValueError:
            message = None
        site.pushes.append({"path": path, "type": self.headers.get("Content-Type"),
                            "auth": self.headers.get("Authorization"), "json": message,
                            "accepted": site.ntfy_status == 200})
        if site.ntfy_status != 200:
            return self._json(site.ntfy_status, {"code": site.ntfy_status * 100 + 1, "http": site.ntfy_status,
                                                 "error": "the fake ntfy was told to refuse"})
        self._json(200, {"id": "fake%d" % len(site.pushes), "time": int(time.time()), "event": "message",
                         "topic": (message or {}).get("topic"), "message": (message or {}).get("message")})

    def _pagespeed(self, query):
        site = self.site
        call = {name: query.get(name, [None])[0] for name in ("url", "strategy", "category", "locale", "key")}
        site.psi_calls.append(call)
        mode = site.psi
        if isinstance(mode, list):                              # one answer per call; the last one stays
            mode = mode.pop(0) if len(mode) > 1 else mode[0]
        if mode in PSI_ERRORS:
            code, status, message = PSI_ERRORS[mode]
            error = {"code": code, "message": message, "errors": [{"message": message, "domain": "global"}]}
            if status:
                error["status"] = status
            return self._json(code, {"error": error})
        name = "psi_lighthouse12.json" if mode == "lighthouse12" else "psi_lighthouse13.json"
        answer = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        answer["id"] = answer["lighthouseResult"]["requestedUrl"] = call["url"]
        if mode == "origin_fallback":                           # too little traffic on the page: the site's numbers
            answer["loadingExperience"]["origin_fallback"] = True
        elif mode == "no_field_data":
            answer["loadingExperience"] = {"initial_url": call["url"]}
        elif mode == "runtime_error":                           # status 200, and the test itself failed
            answer["lighthouseResult"]["runtimeError"] = {
                "code": "NO_FCP", "message": "The page did not paint any content. Please ensure you keep the "
                                             "browser window in the foreground during the load and try again. (NO_FCP)"}
            answer["lighthouseResult"]["categories"]["performance"]["score"] = None
            for audit in answer["lighthouseResult"]["audits"].values():
                audit.pop("numericValue", None)
                audit["score"] = None
        self._json(200, answer)

    def _woocommerce(self, query):
        site = self.site
        if site.catalogue == "html":                            # a firewall's challenge page
            return self._send(200, "text/html", b"<html><body>Just a moment...</body></html>")
        per_page, page = int(query.get("per_page", ["10"])[0]), int(query.get("page", ["1"])[0])
        if per_page > 100 or query.get("orderby") != ["id"] or query.get("order") != ["asc"]:
            return self._json(400, {"code": "rest_invalid_param", "message": "per_page <= 100, orderby=id, order=asc"})
        products = sorted(site.products, key=lambda p: int(p.get("id", 0)))
        first = (page - 1) * per_page
        rows = products[first: first + per_page]
        if site.catalogue == "duplicate" and page > 1:          # the shop changed between two requests:
            rows = products[first - 1: first - 1 + len(rows)]    # one product comes twice, one is never seen
        total = len(products) + (1 if site.catalogue == "count_mismatch" else 0)
        headers = {} if site.catalogue == "no_total" else {
            "X-WP-Total": str(total), "X-WP-TotalPages": str(-(-total // per_page))}
        self._json(200, rows, headers)

    def _shopify(self, query):
        site = self.site
        if site.catalogue == "html":                            # a password-protected shop answers with a page
            return self._send(200, "text/html", b"<html><body>Opening soon</body></html>")
        limit, page = min(int(query.get("limit", ["30"])[0]), 250), int(query.get("page", ["1"])[0])
        self._json(200, {"products": site.shopify[(page - 1) * limit: page * limit]})

    def _control(self, query):
        """By hand: /__fake?path=/cart/&status=502 breaks a page, /__fake?reset=1 repairs everything,
        /__fake alone shows the switches and what was pushed."""
        site = self.site
        first = {name: values[0] for name, values in query.items()}
        if "reset" in first:
            site.reset()
        if "path" in first:
            how = {name: float(first[name]) for name in ("delay", "body_delay", "hang") if name in first}
            how.update({name: int(first[name]) for name in ("status", "redirects") if name in first})
            if "drop" in first:
                how["drop"] = True
            site.broken[first["path"]] = how
        if "ntfy" in first:
            site.ntfy_status = int(first["ntfy"])
        if "catalogue" in first:
            site.catalogue = first["catalogue"]
        if "psi" in first:
            site.psi = first["psi"]
        self._json(200, {"broken": site.broken, "ntfy_status": site.ntfy_status, "catalogue": site.catalogue,
                         "psi": site.psi, "pushes": site.pushes})


def main():
    site = FakeSite(int(sys.argv[1]) if len(sys.argv) > 1 else 8900)
    config = json.dumps(site.config(), ensure_ascii=False, indent=2)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(config + "\n", encoding="utf-8")
    print("""A fake website is listening on %(url)s  (Ctrl+C stops it)

Its configuration%(saved)s. Load it with:  python3 manage.py setup <that file>

%(config)s

For the collectors:   NTFY_URL=%(url)s/ntfy   NTFY_TOPIC=sh-local-test   HEARTBEAT_URL=%(url)s/hb
(PageSpeed cannot measure a local address: leave PAGESPEED_KEY unset here.)

Break and repair it from another terminal:
  curl '%(url)s/__fake?path=/cart/&status=502'      the cart answers 502
  curl '%(url)s/__fake?path=/cart/&hang=30'         the cart does not answer
  curl '%(url)s/__fake?path=/&delay=2'              the home page answers after 2 seconds
  curl '%(url)s/__fake?ntfy=500'                    the push service refuses
  curl '%(url)s/__fake?reset=1'                     everything works again
  curl '%(url)s/__fake'                             the switches, and every push that was published
""" % {"url": site.url, "config": config,
       "saved": " was written to " + sys.argv[2] if len(sys.argv) > 2 else " (save it as site_health.config.json)"})
    try:
        site.server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
