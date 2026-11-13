/* Site Health — real-user speed. One anonymous beacon per page view: how long until the main
   content was painted (LCP). No cookies, no identifiers, no query strings.

   Configure before this script runs:
     window.SiteHealthRum = { endpoint: 'https://<dashboard>/rum', liveHost: 'example.co.il' };

   `site` is sent as the literal "live" on the production host (with or without www) and as the
   host name anywhere else, so measurements from a staging copy are visible as such.
   Add ?sh_test=1 to a page address to send a measurement flagged as a test. */
(function () {
  var cfg = window.SiteHealthRum;
  if (!cfg || !cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
  var types = PerformanceObserver.supportedEntryTypes || [];
  if (types.indexOf('largest-contentful-paint') < 0) return;        // browser cannot measure it: send nothing
  if (document.visibilityState !== 'visible') return;               // opened in a background tab: the number would be meaningless

  var lcp = 0, hiddenAt = Infinity, sent = false;
  var po = new PerformanceObserver(function (list) {
    var all = list.getEntries(), e = all[all.length - 1];
    if (e && e.startTime < hiddenAt) lcp = e.startTime;             // only paints that happened while the page was visible
  });
  try { po.observe({ type: 'largest-contentful-paint', buffered: true }); } catch (err) { return; }

  function send() {
    if (sent) return;
    var rest = po.takeRecords();
    if (rest.length && rest[rest.length - 1].startTime < hiddenAt) lcp = rest[rest.length - 1].startTime;
    if (!lcp) return;
    sent = true;
    po.disconnect();
    var host = location.hostname.replace(/^www\./, '');
    var live = String(cfg.liveHost || '').replace(/^www\./, '');
    navigator.sendBeacon(cfg.endpoint, JSON.stringify({
      site: host === live ? 'live' : location.hostname,
      path: location.pathname,
      lcp: Math.round(lcp),
      test: /[?&]sh_test=1(&|$)/.test(location.search)
    }));                                                             // a string body is sent as text/plain: no CORS preflight
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') { hiddenAt = Math.min(hiddenAt, performance.now()); send(); }
  }, true);
  window.addEventListener('pagehide', send, true);
})();
