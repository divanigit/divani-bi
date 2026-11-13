#!/usr/bin/env node
/* Test of the real-user script (rum/site-health-rum.js) in a real browser (Playwright, headless Chromium).

     node tests/test_rum_snippet.js

   A tiny local site serves pages that include the script; a local collector records what
   arrives. It also checks that the two carriers of the script (the WordPress plugin and the Shopify
   snippet) hold the very same code. Exit code 0 = every check passed. */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const RUM = path.join(__dirname, '..', 'rum');
const SNIPPET = fs.readFileSync(path.join(RUM, 'site-health-rum.js'), 'utf8');
const PORT = 8801;
const beacons = [];
let failed = 0;
function check(name, cond, extra) { if (!cond) failed++; console.log((cond ? 'ok    ' : 'FAIL  ') + name + (!cond && extra ? '  → ' + extra : '')); }

// The code of a copy of the script: no comments, no indentation, no empty lines.
function code(text) {
  return text.split('\n').map((line) => line.replace(/\s*\/\/\s.*$/, '').trim()).filter(Boolean).join('\n');
}
const own = code(SNIPPET.slice(SNIPPET.indexOf('*/') + 2));
const php = fs.readFileSync(path.join(RUM, 'site-health-rum.php'), 'utf8');
const liquid = fs.readFileSync(path.join(RUM, 'site-health-rum.liquid'), 'utf8');
const inPhp = (php.match(/<<<'JS'\n([\s\S]*?)\nJS;/) || [])[1] || '';
const inLiquid = (liquid.match(/\{% raw %\}\n([\s\S]*?)\n\{% endraw %\}/) || [])[1] || '';
check('the WordPress plugin carries the same code as the script', code(inPhp) === own && own.length > 1000);
check('the Shopify snippet carries the same code as the script', code(inLiquid) === own);
check('the plugin ships without an address: manage.py rum-plugin fills it in',
  php.includes("define('SITE_HEALTH_RUM_ENDPOINT', '');") && php.includes("define('SITE_HEALTH_RUM_LIVE_HOST', '');"));
check('the Shopify snippet prints nothing in the theme editor or without an address',
  liquid.includes('{%- unless request.design_mode or sh_endpoint == blank -%}'));

const server = http.createServer((req, res) => {
  if (req.url === '/m') {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => { beacons.push({ method: req.method, type: req.headers['content-type'], origin: req.headers.origin, body }); res.writeHead(204); res.end(); });
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end('<!doctype html><html><body><h1 style="font-size:60px">התוכן הראשי של העמוד</h1><a id="next" href="/other">הלאה</a>'
    + '<script>window.SiteHealthRum={endpoint:"http://127.0.0.1:' + PORT + '/m",liveHost:"localhost"};</script>'
    + '<script>' + SNIPPET + '</script></body></html>');
});

server.listen(PORT, async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext()).newPage();
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const visit = async (address) => { await page.goto(address); await wait(500); };
  const live = 'http://localhost:' + PORT;

  // 1. a page on the live host, left by clicking a link
  await visit(live + '/product/abc/?utm_source=x&email=a@b.co');
  await page.click('#next');
  await wait(600);
  // 2. a private page: nothing may be sent
  await visit('http://127.0.0.1:' + PORT + '/cart/');
  // 3. paths that may name a person: an e-mail address, a token, a UUID. Nothing may be sent.
  await visit(live + '/unsubscribe/someone@example.com/token-abc123');
  await visit(live + '/unsubscribe/someone%40example.com/');
  await visit(live + '/track/3f9a8b7c6d5e4f3a/');                               // 16 hexadecimal characters
  await visit(live + '/reset/AbCdEfGhIjKlMnOpQrStUvWx0123/');                   // 28 letters and digits
  await visit(live + '/order-status/550e8400-e29b-41d4-a716-446655440000/');    // a UUID
  // 4. ordinary long slugs, in English and in Hebrew: these are pages like any other
  await visit(live + '/product/modern-three-seat-corner-sofa-with-storage-grey-2026/');
  await visit(live + '/product/ספה-פינתית-תלת-מושבית-עם-ארגז-מצעים-אפור-2026/');
  // 5. a page on another host name (stands for a staging copy), flagged as a test, left by closing the tab
  await visit('http://127.0.0.1:' + PORT + '/category/sofas/?sh_test=1');
  await page.close();
  await wait(600);

  const rows = beacons.map((b) => JSON.parse(b.body));
  const first = rows[0] || {};
  const paths = rows.map((r) => decodeURIComponent(r.path));
  check('a beacon is sent when the visitor leaves the page', rows.length >= 2, JSON.stringify(rows));
  check('it is a POST with a text/plain body (no CORS preflight)', beacons.every((b) => b.method === 'POST' && /^text\/plain/.test(b.type || '')));
  check('the production host is reported as "live"', first.site === 'live', first.site);
  check('the path is sent without query string', first.path === '/product/abc/' && beacons.every((b) => !/utm_source|email/.test(b.body)), first.path);
  check('LCP is a positive number of milliseconds', Number.isInteger(first.lcp) && first.lcp > 0, String(first.lcp));
  check('an ordinary view is not flagged as a test', first.test === false);
  check('exactly one beacon per page view', rows.filter((r) => r.path === '/product/abc/').length === 1);
  check('nothing is sent from a cart page', !rows.some((r) => /cart/.test(r.path)));
  check('nothing is sent from a path with an e-mail address', !paths.some((p) => /unsubscribe/.test(p)), paths.join(' '));
  check('nothing is sent from a path with a token or a UUID', !paths.some((p) => /track|reset|order-status/.test(p)), paths.join(' '));
  check('a long ordinary slug is measured', paths.includes('/product/modern-three-seat-corner-sofa-with-storage-grey-2026/'), paths.join(' '));
  check('a long Hebrew slug is measured', paths.includes('/product/ספה-פינתית-תלת-מושבית-עם-ארגז-מצעים-אפור-2026/'), paths.join(' '));
  check('only what the checks above expect was sent', rows.length === 5, String(rows.length));
  const staging = rows.find((r) => r.path === '/category/sofas/') || {};
  check('another host is reported by its name, not as "live"', staging.site === '127.0.0.1', staging.site);
  check('?sh_test=1 flags the measurement as a test', staging.test === true);

  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
});
