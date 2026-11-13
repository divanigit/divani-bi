/* Site Health RUM: one beacon per page view, from the visitor's browser to the Site Health dashboard.
   What is sent: the page's path (never the query string; at most 300 characters, of which the dashboard
   keeps the first 120), the time until its main content was painted (LCP),
   the time until the first byte, how the page was opened, and whether the address carried ?sh_test=1.
   Where to: cfg.endpoint, and nowhere else. No cookie and no id; the dashboard stores no address of the visitor.
   Nothing is sent from cart, checkout, account and order pages, nor from a path that holds an "@" or
   something that looks like a token (an unsubscribe link, an order-tracking page).
   Configure BEFORE this script: window.SiteHealthRum = { endpoint: 'https://dashboard.example.com/m', liveHost: 'example.com' };
   Optional: sample (0..1, default 1), skip (RegExp of paths never measured). Add ?sh_test=1 to a URL to flag a test row.
   The same code is embedded in site-health-rum.php and site-health-rum.liquid: change all three together
   (tests/test_rum_snippet.js compares them). */
(function () {
  var cfg = window.SiteHealthRum || {};
  if (!cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
  if ((PerformanceObserver.supportedEntryTypes || []).indexOf('largest-contentful-paint') < 0) return; // Safari < 26.2, Firefox < 122
  var skip = cfg.skip || /\/(checkout|cart|my-account|account|orders?|order-received|wp-admin|wp-login\.php)(\/|$)/i;
  function named(path) {                                                        // may the path name a person? (the server asks the same)
    var p = path, runs, i;
    try { p = decodeURIComponent(path); } catch (err) {}
    if (/[@\x00-\x1f\x7f]/.test(p) || /[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}/i.test(p)) return true;   // an e-mail address, a UUID
    runs = p.match(/[A-Za-z0-9_]+/g) || [];                                     // a hyphen ends a run: ordinary slugs survive
    for (i = 0; i < runs.length; i++) {
      if (/^[0-9a-f]{16,}$/i.test(runs[i])) return true;                        // 16 or more hexadecimal characters
      if (runs[i].length >= 24 && /[A-Za-z]/.test(runs[i]) && /[0-9]/.test(runs[i])) return true;   // 24 or more, letters and digits mixed
    }
    return false;
  }
  if (skip.test(location.pathname) || named(location.pathname)) return;
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
