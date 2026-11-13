<?php
/**
 * Plugin Name: Site Health RUM
 * Description: Sends one anonymous speed measurement per page view (time until the main content is painted) to the site-health dashboard. No cookies, no personal data.
 * Version: 1.1.0
 *
 * Install: copy this ONE file to wp-content/mu-plugins/ (always on) or to wp-content/plugins/ and activate it.
 * Then add to wp-config.php:
 *   define('SITE_HEALTH_RUM_ENDPOINT', 'https://collector.example.com/m');
 *   define('SITE_HEALTH_RUM_LIVE_HOST', 'example.com');   // production host, without www
 * and purge the page cache / CDN so cached pages pick the script up.
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
    $js = <<<'JS'
(function () {
var cfg = window.SiteHealthRum || {};
if (!cfg.endpoint || !window.PerformanceObserver || !navigator.sendBeacon) return;
if ((PerformanceObserver.supportedEntryTypes || []).indexOf('largest-contentful-paint') < 0) return; // Safari < 26.2, Firefox < 122
var skip = cfg.skip || /\/(checkout|cart|my-account|account|orders?|order-received|wp-admin|wp-login\.php)(\/|$)/i;
if (skip.test(location.pathname)) return;
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
