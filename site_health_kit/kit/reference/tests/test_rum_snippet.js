#!/usr/bin/env node
/* Test of the real-user script (rum/site-health-rum.js) in a real browser (Playwright, headless Chromium).

     node tests/test_rum_snippet.js

   A tiny local site serves pages that include the script; a local collector records what
   arrives. Exit code 0 = every check passed. */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const SNIPPET = fs.readFileSync(path.join(__dirname, '..', 'rum', 'site-health-rum.js'), 'utf8');
const PORT = 8801;
const beacons = [];
let failed = 0;
function check(name, cond, extra) { if (!cond) failed++; console.log((cond ? 'ok    ' : 'FAIL  ') + name + (!cond && extra ? '  → ' + extra : '')); }

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

  // 1. a page on the live host, left by clicking a link
  await page.goto('http://localhost:' + PORT + '/product/abc/?utm_source=x&email=a@b.co');
  await wait(600);
  await page.click('#next');
  await wait(600);
  // 2. a private page: nothing may be sent
  await page.goto('http://127.0.0.1:' + PORT + '/cart/');
  await wait(400);
  // 3. a page on another host name (stands for a staging copy), flagged as a test, left by closing the tab
  await page.goto('http://127.0.0.1:' + PORT + '/category/sofas/?sh_test=1');
  await wait(600);
  await page.close();
  await wait(600);

  const rows = beacons.map((b) => JSON.parse(b.body));
  const first = rows[0] || {};
  check('a beacon is sent when the visitor leaves the page', rows.length >= 2, JSON.stringify(rows));
  check('it is a POST with a text/plain body (no CORS preflight)', beacons.every((b) => b.method === 'POST' && /^text\/plain/.test(b.type || '')));
  check('the production host is reported as "live"', first.site === 'live', first.site);
  check('the path is sent without query string', first.path === '/product/abc/' && beacons.every((b) => !/utm_source|email/.test(b.body)), first.path);
  check('LCP is a positive number of milliseconds', Number.isInteger(first.lcp) && first.lcp > 0, String(first.lcp));
  check('an ordinary view is not flagged as a test', first.test === false);
  check('exactly one beacon per page view', rows.filter((r) => r.path === '/product/abc/').length === 1);
  check('nothing is sent from a cart page', !rows.some((r) => /cart/.test(r.path)));
  const staging = rows.find((r) => r.path === '/category/sofas/') || {};
  check('another host is reported by its name, not as "live"', staging.site === '127.0.0.1', staging.site);
  check('?sh_test=1 flags the measurement as a test', staging.test === true);

  await browser.close();
  server.close();
  console.log('\n' + (failed ? failed + ' failed' : 'all passed'));
  process.exit(failed ? 1 : 0);
});
