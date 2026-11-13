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
