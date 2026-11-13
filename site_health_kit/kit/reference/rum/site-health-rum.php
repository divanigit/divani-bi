<?php
/**
 * Plugin Name: Site Health RUM
 * Description: Sends one anonymous speed measurement per page view (time to main content) to the site-health dashboard. No cookies, no personal data.
 * Version: 1.0.0
 *
 * Install: set the two constants below, upload this file together with site-health-rum.js
 * to wp-content/plugins/site-health-rum/ and activate it (or drop both into wp-content/mu-plugins/).
 */
if (!defined('ABSPATH')) { exit; }

if (!defined('SITE_HEALTH_RUM_ENDPOINT')) { define('SITE_HEALTH_RUM_ENDPOINT', 'https://CHANGE-ME.example.com/rum'); }   // the dashboard's /rum address
if (!defined('SITE_HEALTH_RUM_LIVE_HOST')) { define('SITE_HEALTH_RUM_LIVE_HOST', 'example.co.il'); }                      // the production host, without www

add_action('wp_enqueue_scripts', function () {
    if (strpos(SITE_HEALTH_RUM_ENDPOINT, 'CHANGE-ME') !== false) { return; }          // not configured yet
    if (is_user_logged_in() && current_user_can('edit_posts')) { return; }            // staff browsing the site are not visitors
    if (function_exists('is_checkout') && (is_checkout() || is_account_page())) { return; }   // never on checkout / account pages
    wp_enqueue_script('site-health-rum', plugins_url('site-health-rum.js', __FILE__), array(), '1.0.0',
        array('in_footer' => true, 'strategy' => 'defer'));
    wp_add_inline_script('site-health-rum', 'window.SiteHealthRum=' . wp_json_encode(array(
        'endpoint' => SITE_HEALTH_RUM_ENDPOINT,
        'liveHost' => SITE_HEALTH_RUM_LIVE_HOST,
    )) . ';', 'before');
});
