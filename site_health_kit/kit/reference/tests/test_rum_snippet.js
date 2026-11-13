const { chromium } = require('playwright');
const http = require('http'), fs = require('fs');
const SNIP = fs.readFileSync('' + require('path').join(__dirname, '..', 'rum', 'site-health-rum.js') + '', 'utf8');
const beacons = [];
const srv = http.createServer((req, res) => {
  if (req.url.startsWith("/m")) {
    let b = ''; req.on('data', (c) => b += c); req.on('end', () => { beacons.push({ ct: req.headers['content-type'], origin: req.headers.origin, method: req.method, body: b }); res.writeHead(204); res.end(); });
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end('<!doctype html><html><body><h1 style="font-size:60px">שלום עולם, זה התוכן הראשי של העמוד</h1><p>next: <a id="n" href="/other">other</a></p>'
    + '<script>window.SiteHealthRum={endpoint:"http://127.0.0.1:8801/m",liveHost:"localhost"};</script><script>' + SNIP + '</script></body></html>');
});
srv.listen(8801, async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext();
  const p = await ctx.newPage();
  // 1) page on the "live" host (localhost), leave by navigation
  await p.goto('http://localhost:8801/product/abc/?utm_source=x&email=a@b.co');
  await p.waitForTimeout(700);
  await p.click('#n'); await p.waitForTimeout(700);
  // 2) page on another host name (127.0.0.1 = "staging"), flagged as test, leave by closing
  await p.goto('http://127.0.0.1:8801/cart/'); await p.waitForTimeout(500);
  await p.goto('http://127.0.0.1:8801/category/sofas/?sh_test=1');
  await p.waitForTimeout(700);
  await p.close(); await new Promise((r) => setTimeout(r, 700));
  console.log(JSON.stringify(beacons, null, 1));
  const ok = beacons.length >= 2
    && beacons.every((x) => x.method === 'POST' && /^text\/plain/.test(x.ct))
    && JSON.parse(beacons[0].body).site === 'live' && JSON.parse(beacons[0].body).path === '/product/abc/' && JSON.parse(beacons[0].body).lcp > 0 && JSON.parse(beacons[0].body).test === false
    && beacons.some((x) => { const j = JSON.parse(x.body); return j.site === '127.0.0.1' && j.test === true && j.path === '/category/sofas/'; })
    && !beacons.some((x) => /cart/.test(x.body))
    && beacons.every((x) => !/utm_source|email/.test(x.body));
  console.log(ok ? 'RUM SNIPPET OK' : 'RUM SNIPPET FAILED');
  await b.close(); srv.close();
});
