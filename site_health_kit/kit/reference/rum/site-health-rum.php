<?php
/**
 * Plugin Name: Site Health RUM
 * Description: Measures how fast the pages load for real visitors. On every page view the visitor's browser sends the page's path and its loading time to the Site Health dashboard of this site. No cookies, and nothing that identifies the visitor is stored.
 * Version: 1.2.0
 *
 * Install. Nobody edits wp-config.php, and nobody copies files onto the server:
 *   1. python3 manage.py rum-plugin --endpoint https://<the dashboard>/m --out site-health-rum.zip
 *      puts this file into a ZIP, with the two values below filled in.
 *   2. In the site's admin: Plugins > Add new > Upload plugin > choose the ZIP > Install now > Activate.
 *   3. Purge the page cache / CDN so that cached pages pick the script up, and exclude the script
 *      "site-health-rum" from any "delay JavaScript" optimisation (or only visitors who interact are measured).
 *   4. Open a page of the site with ?sh_test=1 at the end of its address, leave the page, and look at
 *      "מהירות אצל לקוחות" on the Site Health screen within a minute.
 * If nothing arrives: a site that sends a Content-Security-Policy header must allow the dashboard's
 * host in connect-src and this inline script in script-src; otherwise the browser sends nothing.
 * A site that defines the two constants in wp-config.php already keeps its own values.
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
    // The code of site-health-rum.js, without its comments. Change the three copies together.
    $js = <<<'JS'
(function () {
var cfg = window.SiteHealthRum || {};
if (!cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
if ((PerformanceObserver.supportedEntryTypes || []).indexOf('largest-contentful-paint') < 0) return;
var skip = cfg.skip || /\/(checkout|cart|my-account|account|orders?|order-received|wp-admin|wp-login\.php)(\/|$)/i;
function named(path) {
var p = path, runs, i;
try { p = decodeURIComponent(path); } catch (err) {}
if (/[@\x00-\x1f\x7f]/.test(p) || /[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}/i.test(p)) return true;
runs = p.match(/[A-Za-z0-9_]+/g) || [];
for (i = 0; i < runs.length; i++) {
if (/^[0-9a-f]{16,}$/i.test(runs[i])) return true;
if (runs[i].length >= 24 && /[A-Za-z]/.test(runs[i]) && /[0-9]/.test(runs[i])) return true;
}
return false;
}
if (skip.test(location.pathname) || named(location.pathname)) return;
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
