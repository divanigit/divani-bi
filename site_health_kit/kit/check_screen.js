#!/usr/bin/env node
/* Acceptance test of the site-health screen (Playwright, headless Chromium).

     node check_screen.js                                # against the mock:  http://127.0.0.1:8787
     node check_screen.js http://127.0.0.1:8000 --cookie "name=value"
                                                         # your real server; the session cookie of the throwaway
                                                         # check vendor (OWNER-STEPS.md step 6), never the owner's
     node check_screen.js <url> --path "/status?k=<token>"
                                                         # another page than /site, for example the share link
                                                         # of a real server (it needs no cookie)
     node check_screen.js <url> --shots ./shots          # also save screenshots (phone, desktop, dark)
     node check_screen.js <url> --basic                  # leave out group C, also when <url> is the mock

   Three groups of checks. Each line is one check: "ok" or "FAIL".
     A. The page as the server gives it: structure, numbers against the data, sheets.     Any server.
     B. The rules of spec §6, against canned answers that this test feeds the page itself
        (it intercepts the data calls in the browser, so the server's data does not matter):
        failed reads, the sequence guard, both timers, the alert bar, every click, the date
        range, colours against the thresholds, print, roles, the menu button, downAfter,
        texts with markup in them.                                                         Any server.
     C. Scenarios, roles, sessions and ?hide= of the mock (incident, ok, empty, error, hostile). Mock only.

   The test only reads from the server: groups A and C send GET calls (C also deletes alerts, in
   the mock), and every call of group B is answered inside the browser and never reaches the server.
   A check that breaks (a click that cannot happen, a sheet that does not close) is one FAIL line,
   and the run goes on to its summary "N passed, M failed". A screen that does not finish loading
   the canned answers of group B stops that group with one FAIL line that says why.
   Needs Playwright 1.45 or newer. Exit code 0 = every check passed, 1 = at least one failed,
   2 = the test could not run. */
'use strict';
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i < 0 ? null : (args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true); };
const GIVEN = !!(args[0] && !args[0].startsWith('--'));
const BASE = (GIVEN ? args[0] : 'http://127.0.0.1:8787').replace(/\/$/, '');
const SHOTS = flag('--shots'), COOKIE = flag('--cookie'), BASIC = !!flag('--basic');
const PAGE_PATH = typeof flag('--path') === 'string' ? flag('--path') : '/site';
const PHONE = { width: 390, height: 844 }, DESK = { width: 1280, height: 900 };
const NA = 'הנתון לא זמין כרגע';
/* what the test needs to know about the screen's configuration; read from the page in group A */
const CFG = { api: '/api', loginPath: '/login', homePage: 'בית', here: '/site' };

let failed = 0, passed = 0;
let s = null, p = null, sh = null;        // the page under test (each group opens its own), the last sheet read
function check(name, cond, extra) { if (cond) { passed++; console.log('ok    ' + name); } else { failed++; console.log('FAIL  ' + name + (extra != null && extra !== '' ? '  → ' + String(extra).slice(0, 300) : '')); } }
const firstLine = (e) => String(e && e.message || e).split('\n')[0];
/* one group of checks; a crash inside it is one failed check, its page is closed, and the other groups still run */
async function block(name, fn) {
  try { await fn(); } catch (e) { check(name + ': ran to its end', false, firstLine(e) + '  (the rest of this group did not run)'); }
  if (s) await s.ctx.close().catch(() => {});
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, ms = 5000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await fn()) return true; await sleep(25); } return false; };

/* ---------- reading the page ---------- */
/* a missing element reads as a text that no check expects, so the check fails instead of the run */
const txt = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent : '(no element ' + s + ')'; }, sel);
const texts = (page, sel) => page.evaluate((s) => Array.prototype.map.call(document.querySelectorAll(s), (e) => e.textContent), sel);
const count = (page, sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel);
const visible = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }, sel);
const shown = (page, sel) => page.evaluate((s) => Array.prototype.filter.call(document.querySelectorAll(s), (e) => { const r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }).length, sel);
const css = (page, sel, prop) => page.evaluate(([s, k]) => { const e = document.querySelector(s); return e ? getComputedStyle(e)[k] : null; }, [sel, prop]);
/* the screen sets overflow-x:hidden on html and body, so the root never scrolls: an element that
   is too wide shows only in the body's own scroll width */
const rgbSum = (c) => { const m = String(c).match(/\d+/g); return m ? +m[0] + +m[1] + +m[2] : -1; };
const noOverflow = (page) => page.evaluate(() => document.body.scrollWidth <= window.innerWidth + 1);
/* waits until the screen has drawn its answers; true when it did */
const settle = (page) => page.waitForFunction(() => !document.body.classList.contains('loading') && document.querySelectorAll('#verdict .vbox').length === 4 && !/טוען…/.test(document.getElementById('now').textContent), null, { timeout: 15000 }).then(() => true, () => false);
/* why a page did not settle: the marks it still shows, and the errors of the page */
const notSettled = async (s) => 'the screen did not finish loading the canned answers in 15 s (' + await s.page.evaluate(() => {
  const why = [], n = document.querySelectorAll('#verdict .vbox').length, now = document.getElementById('now');
  if (document.body.classList.contains('loading')) why.push('still loading');
  if (n !== 4) why.push(n + ' tiles in "שורה תחתונה", not 4');
  if (!now || /טוען…/.test(now.textContent)) why.push('"עכשיו" still reads טוען…');
  return why.join(', ');
}).catch(() => '?') + ')' + (s.errors.length ? '; ' + s.errors.slice(0, 3).join(' | ') : '');
const sheetOn = (page) => page.evaluate(() => document.getElementById('dov').classList.contains('on')).catch(() => false);
/* the sheet opens on the click itself, reading "טוען…" (spec §6.3); only its content waits for the server.
   A click that opened nothing costs 2 seconds, not 5. */
const sheetReady = async (page) => {
  if (!(await page.waitForFunction(() => document.getElementById('dov').classList.contains('on'), null, { timeout: 2000 }).then(() => true, () => false))) return;
  await page.waitForFunction(() => document.getElementById('dov').classList.contains('on') && !/טוען…/.test(document.getElementById('dbody').textContent), null, { timeout: 5000 }).catch(() => {});
};
/* closes the sheet without the page's help: after a failed check, so that the next steps still run */
const shut = (page) => page.evaluate(() => { document.getElementById('dov').classList.remove('on'); document.body.style.overflow = ''; }).catch(() => {});
const escapeFailed = new WeakSet();
const closeSheet = async (page) => {
  if (!(await sheetOn(page))) return;
  await page.keyboard.press('Escape');
  if (!(await sheetOn(page))) return;
  if (!escapeFailed.has(page)) { escapeFailed.add(page); check('Escape closes the sheet (between two steps)', false, 'it stayed open; the test closed it itself and goes on'); }
  await shut(page);
};
/* before a click: a sheet or the menu that is still open (a close that failed) would swallow the click.
   It is one failed check, and the test closes it so that the click can still happen. */
async function unblock(page, sel) {
  const left = await page.evaluate((q) => {
    let t = null; try { t = document.querySelector(q); } catch (e) { /* not a CSS selector */ }
    const out = [];
    [['dov', 'a sheet'], ['shov', 'the menu']].forEach(([id, what]) => {
      const o = document.getElementById(id);
      if (o && o.classList.contains('on') && !(t && o.contains(t))) { o.classList.remove('on'); document.body.style.overflow = ''; out.push(what); }
    });
    return out;
  }, sel).catch(() => []);
  if (left.length) check('nothing is left open before the click on ' + sel, false, left.join(' and ') + ' was still open; the test closed it');
}
/* what the open sheet shows; a closed sheet reads as empty, so a click that opened nothing cannot pass on old content */
const sheet = (page) => page.evaluate(() => document.getElementById('dov').classList.contains('on') ? { title: document.getElementById('dttl').textContent, body: document.getElementById('dbody').textContent, rows: document.querySelectorAll('#dbody tbody tr').length, items: document.querySelectorAll('#dbody li').length } : { title: '', body: '', rows: 0, items: 0 });
/* a tile that is not there reads as an empty tile, so a check of t[3] fails instead of crashing */
const NOTILE = Object.freeze({ k: '', v: '', m: '', dot: '' });
const padded = (a) => new Proxy(a, { get: (o, k) => (typeof k === 'string' && /^\d+$/.test(k) && !(k in o) ? NOTILE : o[k]) });
const tiles = (page, sel) => page.evaluate((s) => Array.prototype.map.call(document.querySelectorAll(s), (b) => { const g = (c) => { const e = b.querySelector(c); return e ? e.textContent : ''; }; const d = b.querySelector('.dot'); return { k: g('.k'), v: g('.v'), m: g('.m'), dot: d ? d.className.replace('dot ', '') : '' }; }), sel).then(padded);
async function scenario(name) { const r = await fetch(BASE + '/__scenario?name=' + name).catch(() => null); if (!r || !r.ok) return false; const j = await r.json().catch(() => null); return !!(j && j.mock === 'site-health-kit'); }

/* ---------- canned answers (group B): the test plays the backend ---------- */
const U = 'https://shop.test';
/* every text field of an answer, with markup in it; every url, a javascript: address.
   The mock's "hostile" scenario does the same to its own answers. */
const PAYLOAD = '\'"><img class="xss" src="x" onerror="window.__xss=1"><b class="xss">x</b>&lt;';
function hostile(v, key) {
  if (Array.isArray(v)) return v.map((x) => hostile(x, key));
  if (v && typeof v === 'object') { const o = {}; Object.keys(v).forEach((k) => { o[k] = hostile(v[k], k); }); return o; }
  if (['section', 'bucket', 'strategy', 'from', 'to'].indexOf(key) >= 0) return v;      // what the screen sorts rows by
  if (key === 'url') return 'javascript:window.__xss=1//' + PAYLOAD;
  if (typeof v === 'string') return v + PAYLOAD;
  if (v === null && ['note', 'silent_txt', 'err'].indexOf(key) >= 0) return PAYLOAD;     // text fields that are usually null
  return v;
}
/* opens every sheet of a page whose data is hostile, and reports what the texts turned into */
async function hostileWalk(s, who) {
  const p = s.page, worst = { ran: 0, built: 0, js: 0 }, seen = [];
  const look = async () => {
    const x = await p.evaluate(() => ({ ran: window.__xss ? 1 : 0, built: document.querySelectorAll('.xss').length, js: Array.prototype.filter.call(document.querySelectorAll('a[href]'), (a) => /^\s*javascript:/i.test(a.getAttribute('href'))).length }));
    Object.keys(worst).forEach((k) => { worst[k] = Math.max(worst[k], x[k]); });
  };
  await p.click('#explbtn');
  await p.click('#alertbar .ahead', { quiet: true }).catch(() => {});
  for (const h of ['#alertsCard .foldhead', '#msgCard .foldhead']) if (await visible(p, h)) await p.click(h);
  await look();
  for (const sel of ['#verdict .vbox[data-drill="home"]', '#verdict .vbox[data-drill="fails"]', '#verdict .vbox[data-drill="outages"]', '#verdict .vbox[data-drill="alerts"]', '#availTbl tr.rowbtn', '#outages li.rowbtn',
    '#availChart rect.bar', '#availChart circle.hit', '#speedChart circle.pt', '#coreTbl tr.rowbtn', '#slowTbl tr.rowbtn', '#alertsList li.rowbtn', '#alertsList li.rowbtn:nth-child(4)', '#healthTbl li.rowbtn', '#healthTbl li.rowbtn:nth-child(3)', '#alertbar .arow .at']) {
    const el = p.locator(sel).first();
    if (!(await el.count())) continue;
    await el.click({ force: true, timeout: 2000 }).catch(() => {});      // force: chart points may lie on top of each other
    await sheetReady(p);
    if (await sheetOn(p)) seen.push(sel);
    await sleep(60); await look();
    await closeSheet(p);
  }
  await sleep(400); await look();
  check('hostile texts (' + who + '): long texts do not widen the page', await noOverflow(p), 'body is ' + await p.evaluate(() => document.body.scrollWidth) + 'px wide');
  check('hostile texts (' + who + '): the sheets opened', seen.length >= 12, seen.length + ' sheets');
  check('hostile texts (' + who + '): no text field became an element', worst.built === 0, worst.built + ' elements');
  check('hostile texts (' + who + '): no script ran', worst.ran === 0);
  check('hostile texts (' + who + '): a javascript: address never becomes a link', worst.js === 0, worst.js + ' links');
  check('hostile texts (' + who + '): the markup is shown as text, and nothing breaks', /<img class="xss"/.test(await txt(p, '.wrap')) && s.errors.length === 0, s.errors.join(' | '));
}
function fakeBackend(home, api) {
  const pad = (n) => ('0' + n).slice(-2);
  const F = { log: [], acked: new Set(), over: {}, HOME: home || CFG.homePage, api: api || CFG.api };
  F.PAGES = [[F.HOME, U + '/'], ['קטגוריה', U + '/product-category/sofas/'], ['מוצר', U + '/product/sample-sofa/'], ['סל', U + '/cart/']];
  F.ALERTS = [
    { id: 41, kind: 'down', title: 'האתר לא עונה: סל', body: 'האתר לא עונה: סל\nקוד 502\n' + U + '/cart/', open: true, opened_il: '12.11 11:02', closed_il: null, minutes: 14 },
    { id: 40, kind: 'slow', title: 'עמוד איטי: קטגוריה', body: '4.6 שניות עד התוכן, פעמיים ברצף\n' + U + '/product-category/sofas/', open: true, opened_il: '12.11 09:10', closed_il: null, minutes: 125 },
    { id: 39, kind: 'silent', title: 'המדידה נעצרה: טעינת מפת האתר', body: 'אין מדידה כבר 3 ימים', open: true, opened_il: '11.11 02:00', closed_il: null, minutes: 2000 },
    { id: 38, kind: 'down', title: 'האתר לא עונה: ' + F.HOME, body: 'לא ענה בזמן', open: false, opened_il: '12.11 01:20', closed_il: '12.11 01:21', minutes: 1 }];
  F.FLOWS = [['בודק זמינות האתר', 'תקין', null], ['מדידת מהירות — עמודי ליבה', 'מתעכב', null], ['טעינת מפת האתר', 'שקט', null], ['בדיקת תעודת האבטחה', 'אין נתון', null], ['מדידה שהמסך לא מכיר', 'תקין', 'הסבר שהשרת שלח']];
  F.hours = (q) => q.f ? Math.round((Date.parse(q.t) - Date.parse(q.f)) / 36e5) + 24 : +(q.h || 24);
  F.buckets = (q) => {             // hourly up to 72 hours, daily beyond; a day more than the window, as a real backend has
    const hours = F.hours(q), out = [];
    if (hours <= 72) for (let i = 0; i < 24; i++) out.push('2026-11-12 ' + pad(i) + ':00');
    else for (let i = 0, n = hours / 24 + (q.f ? 0 : 1); i < n; i++) out.push(new Date(Date.UTC(2025, 9, 10) + i * 864e5).toISOString().slice(0, 10));
    return out;
  };
  F.site = (q) => {
    const B = F.buckets(q), hours = F.hours(q), strategy = q.strategy === 'desktop' ? 'desktop' : 'mobile';
    const core = (s) => F.PAGES.map(([p, u], i) => ({ section: 'ליבה', strategy: s, page: p, url: u, lcp_p50: [2000, 2500, 4000, 4001][i] - (s === 'desktop' ? 900 : 0), lcp_p95: 5200, score_med: 64, cls_med: 0.03, ttfb_p50: 420, slow_runs: i, checks: 96, crux_category: ['FAST', 'AVERAGE', 'SLOW', null][i], crux_lcp: i < 3 ? 2100 : null }));
    return {
      hours, from: '2026-11-11T12:00:00+02:00', to: '2026-11-12T12:01:00+02:00', strategy,
      /* the first row's checks follow the window, so a check can tell which answer is on the screen */
      availability: F.PAGES.map(([p], i) => ({ section: 'לפי עמוד', page: p, checks: hours * 60, failed: i === 3 ? 2 : 0, fail_pct: i === 3 ? '0.14' : '0.00', p50_ms: 280 + 40 * i, p95_ms: 900, last_fail_il: i === 3 ? '12.11 03:12' : null }))
        .concat([{ section: 'נפילות', outage_minutes: 7, outage_start_il: '12.11 03:12', outage_end_il: '12.11 03:19' }]),
      availability_series: B.map((b, i) => ({ bucket: b, checks: 240, failed: i === 3 ? 2 : 0, ms_p50: 300 + (i % 3), ms_p95: 900 })),
      speed: [{ section: 'שורה תחתונה', page: F.HOME, url: U + '/', lcp_p50: 2310, checks: 96, verdict: 'מהיר' }].concat(core('mobile'), core('desktop'),
        Array.from({ length: 10 }, (_, i) => ({ section: 'האיטיים באתר', page: U + '/product/heavy-' + i + '/', url: U + '/product/heavy-' + i + '/', lcp_p50: 7000 - 300 * i, score_med: 20 + i, checks: 2, last_il: '12.11 08:10' })),
        [{ section: 'כיסוי', checks: 288, slow_runs: 412 }]),
      speed_series: F.PAGES.slice(0, 3).reduce((a, [p, u], i) => a.concat(B.map((b, k) => ({ page: p, url: u, bucket: b, lcp_p50: 2000 + 700 * i + (k % 3) }))), []),
      alerts_open: F.ALERTS.filter((a) => a.open).map((a) => ({ id: a.id, kind: a.kind, title: a.title, body: a.body, opened_il: a.opened_il, acked: F.acked.has(a.id) })),
      alerts_recent: F.ALERTS.map((a) => ({ id: a.id, kind: a.kind, title: a.title, body: a.body, open: a.open, opened_il: a.opened_il, closed_il: a.closed_il, minutes: a.minutes })),
      health: F.FLOWS.map(([f, st, note]) => ({ flow_name: f, status: st, cadence: 'כל דקה', silent_txt: st === 'שקט' ? 'שקט כבר 3 ימים' : null, last_at: st === 'אין נתון' ? null : '2026-11-12T15:35:00+02:00', warn_minutes: 5, late_minutes: 15, note })),
      product_issues: Array.from({ length: 70 }, (_, i) => ({ issue: i < 20 ? 'בלי מחיר' : 'לא במלאי', name: 'מוצר ' + (i + 1), url: U + '/product/' + i + '/', snap_date: '2026-11-12' })),
      cert: { host: 'shop.test', issuer: 'Test CA', not_after: '2026-12-05T10:00:00+02:00', days_left: 23, ok: true, err: null, checked_at: '2026-11-12T04:03:00+02:00' },
    };
  };
  F.now = () => ({
    pages: F.PAGES.map(([p, u], i) => ({ page: p, url: u, ok: true, status: 200, ms: [240, 310, 690, 1700][i] })),
    latest: F.PAGES.map(([p]) => ({ page: p, ok: true })), light: false, all_ok: true, any_ok: true, age_sec: 12,
    rum: { n: 143, p75_ms: 3120 }, speed: { lcp_ms: 2500, score: 63, checked_at: '2026-11-12T15:30:00+02:00' }, alerts_open: 3,
    rum_src: { n: 1000, hosts: [{ host: 'live', n: 1000 }], cols: ['created_at'], test: 0 },
  });
  F.drill = (q) => {
    if (q.what === 'fails') return { rows: [{ at_il: '12.11 03:14', page: 'סל', kind: 'קוד 502', err: null, ms: 812 }, { at_il: '12.11 03:13', page: 'סל', kind: 'שגיאת חיבור', err: 'connection reset by peer', ms: null }] };
    if (q.what === 'bucket') return { rows: F.PAGES.map(([p]) => ({ page: p, checks: 60, failed: 0, ms_p50: 290, ms_max: 1900, worst_il: '12.11 09:17' })) };
    if (q.what === 'runs') {
      return { rows: Array.from({ length: 121 }, (_, i) => i === 5 ? { ok: false, err: 'NO_FCP', at_il: '12.11 10:00' } : {
        ok: true, err: null, at_il: '12.11 ' + pad(i % 24) + ':15', lcp_ms: 2400 + i, score: 64, ttfb_ms: 410, bytes: 3400000, cls: 0.03, crux_category: 'FAST', crux_lcp_ms: 2100,
        opps: i < 100 ? [{ id: 'uses-responsive-images', title: 'Properly size images', ms: 900 }, { id: 'an-audit-without-translation', title: 'סיבה שאין לה תרגום במסך', ms: 300 }] : [] }) };
    }
    if (q.what === 'alert') {
      const a = F.ALERTS.filter((x) => x.id === +q.id)[0];
      return { rows: a ? [Object.assign({}, a, { fails: a.kind === 'down' ? [{ at: '12.11 11:02', page: 'סל', status: 502, err: null }, { at: '12.11 11:03', page: 'סל', err: 'timeout' }] : [], sent: [{ event: 'open', status: 200, at: a.opened_il }].concat(a.open ? [] : [{ event: 'close', status: 500, at: a.closed_il }]) })] : [] };
    }
    return null;
  };
  F.messages = () => ({ rows: [{ kind: 'התראה', title: 'האתר לא עונה: סל', msg: 'קוד 502\n' + U + '/cart/', at_il: '12.11 11:02', sent: true }, { kind: 'חזר לתקין', title: 'חזר לתקין: ' + F.HOME, msg: 'האתר לא עונה: ' + F.HOME + '\nנמשך דקה', at_il: '12.11 01:21', sent: false }, { kind: 'בוקר', title: 'בוקר טוב: האתר תקין', msg: 'זמינות 99.9%', at_il: '12.11 07:30', sent: true }] });
  F.n = (path, method) => F.log.filter((e) => e.path === path && (!method || e.method === method)).length;
  F.last = (path) => F.log.filter((e) => e.path === path).slice(-1)[0] || { q: {} };
  F.handle = async (route) => {
    const req = route.request(), u = new URL(req.url()), path = u.pathname.slice(F.api.length), q = {};
    u.searchParams.forEach((v, k) => { q[k] = v; });
    const e = { method: req.method(), path, q, body: req.postData() }; F.log.push(e);
    let a = F.over[path] ? F.over[path](q, e) : null;
    if (!a) {
      if (path === '/alerts/ack' && e.method === 'POST') { let ids = []; try { ids = JSON.parse(e.body).ids || []; } catch (x) { /* answered as a bad request below */ } ids.forEach((i) => F.acked.add(+i)); a = ids.length ? { body: { ok: true, n: ids.length } } : { status: 400, body: { error: 'bad request' } }; }
      else a = { body: path === '/site' ? F.site(q) : path === '/site/now' ? F.now() : path === '/site/drill' ? F.drill(q) : path === '/messages' ? F.messages(q) : null };
    }
    if (a.delay) await sleep(a.delay);
    const body = a.body == null ? { error: 'not found' } : F.hostile ? hostile(a.body) : a.body;
    await route.fulfill({ status: a.status || (a.body == null ? 404 : 200), contentType: 'application/json; charset=utf-8', body: JSON.stringify(body) }).catch(() => {});
  };
  return F;
}
const fail502 = () => ({ status: 502, body: { error: 'connection refused' } });

/* ---------- opening a page ---------- */
/* o.fake: canned answers (group B). o.role / o.cfg: SH_ROLE and SH_CONFIG values written after the
   server's own injection. o.clock: a fixed time, with the page's timers under the test's control. */
async function open(browser, path, vp, o = {}) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, locale: 'he-IL', timezoneId: 'Asia/Jerusalem', colorScheme: o.dark ? 'dark' : 'light' });
  if (COOKIE && typeof COOKIE === 'string') {
    const [n, ...v] = COOKIE.split('='); const u = new URL(BASE);
    await ctx.addCookies([{ name: n, value: v.join('='), domain: u.hostname, path: '/' }]);
  }
  const page = await ctx.newPage();
  page.setDefaultTimeout(5000);
  const s = { ctx, page, errors: [], status: 0, site: null, F: null };
  /* A click that cannot happen is one failed check, not the end of the run ({quiet: true}: the caller
     handles it). The reads of one element answer null when the element is not there. */
  const click0 = page.click.bind(page);
  page.click = async (sel, opt) => {
    const { quiet, ...o } = opt || {};
    await unblock(page, sel);
    try { return await click0(sel, o); } catch (e) { if (quiet || page.isClosed()) throw e; check('the test can click ' + sel, false, firstLine(e)); }
  };
  for (const m of ['getAttribute', 'isChecked', 'isDisabled', 'inputValue']) {
    const f = page[m].bind(page);
    page[m] = (...a) => f(...a).catch((e) => { if (page.isClosed()) throw e; return null; });
  }
  page.on('pageerror', (e) => s.errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) s.errors.push('console: ' + m.text()); });
  page.on('response', (r) => { try { if (new URL(r.url()).pathname === CFG.api + '/site' && r.status() === 200) r.json().then((j) => { s.site = j; }).catch(() => {}); } catch (e) { /* not a URL the test cares about */ } });
  if (o.clock) await page.clock.install({ time: new Date(o.clock) });
  if (o.fake) {
    const cfg = Object.assign({ hide: [], nav: [], links: [], shareKey: '', downAfter: 1, liveHosts: ['live'], bucketNote: '', here: CFG.here, homePage: CFG.homePage, api: CFG.api }, o.cfg || {});
    s.F = fakeBackend(cfg.homePage, cfg.api); Object.assign(s.F.over, o.over || {}); s.F.hostile = !!o.hostile;
    await page.route((u) => u.pathname.indexOf(cfg.api + '/') === 0, s.F.handle);
    const patch = '<script>window.SH_CONFIG=Object.assign(window.SH_CONFIG||{},' + JSON.stringify(cfg) + ');window.SH_ROLE=' + JSON.stringify(o.role || {}) + ';</script>';
    await page.route((u) => u.pathname.indexOf(cfg.api + '/') !== 0, async (route) => {
      /* a page that is closed, or that leaves, while this answer is on its way must not end the whole test */
      try {
        if (route.request().resourceType() !== 'document') return await route.continue();
        const r = await route.fetch();
        await route.fulfill({ response: r, body: (await r.text()).replace('</head>', patch + '</head>') });
      } catch (e) { await route.abort().catch(() => {}); }
    });
  }
  const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  s.status = resp ? resp.status() : 0;
  if (s.status === 200 && !o.noWait && !(await settle(page)) && o.fake) {
    /* canned answers come at once: a screen that has not drawn them by now is broken, and each
       check of the group would only wait for it in turn. The group stops here with one FAIL line. */
    const why = await notSettled(s);
    await ctx.close().catch(() => {});
    throw new Error(why);
  }
  return s;
}
const fake = (browser, o = {}) => open(browser, PAGE_PATH, o.vp || PHONE, Object.assign({ fake: true }, o));
/* a new answer for /site (a change of the canned one), then "רענון" */
async function reload(s, change) {
  if (change) s.F.over['/site'] = (q) => { const d = s.F.site(q); change(d); return { body: d }; };
  await s.page.click('#refbtn'); await settle(s.page);
}

(async () => {
  const browser = await chromium.launch();
  const isMock = await scenario('incident');
  if (!GIVEN && !isMock) {
    console.error('No address was given, and ' + BASE + ' does not answer as the kit\'s mock.\nStart the mock (python3 mock_server.py) or give the address of your server:  node check_screen.js http://127.0.0.1:8000');
    process.exit(2);
  }
  const runC = isMock && !BASIC;

  /* ================= A. the page as the server gives it ================= */
  s = await open(browser, PAGE_PATH, PHONE).catch((e) => {
    console.error('Nothing answers at ' + BASE + PAGE_PATH + ' (' + firstLine(e).replace(/^page\.goto: /, '') + ').\nStart your server, or the kit\'s mock (python3 mock_server.py), and give its address:  node check_screen.js http://127.0.0.1:<port>');
    process.exit(2);
  });
  p = s.page;
  const isScreen = s.status === 200 && await p.evaluate(() => !!(document.getElementById('verdict') && document.getElementById('now') && document.getElementById('dov')));
  check('the page loads (200) and is the site-health screen', isScreen, 'status ' + s.status + ', address ' + p.url());
  if (!isScreen) {
    console.error('\n' + BASE + PAGE_PATH + ' did not give the screen, so nothing else can be checked.\nFor a real server pass the session cookie of the throwaway check vendor (OWNER-STEPS.md step 6: --cookie "name=value"), never the owner\'s, or test the share link (--path "/status?k=<token>").');
    process.exit(2);
  }
  Object.assign(CFG, await p.evaluate(() => { const c = window.CFG || {}, o = {}; ['api', 'loginPath', 'homePage', 'here'].forEach((k) => { if (typeof c[k] === 'string' && c[k]) o[k] = c[k]; }); if (Array.isArray(c.hide)) o.hide = c.hide.slice(); return o; }));

  await block('A1 the page on a phone', async () => {
    check('no horizontal scroll at 390px', await noOverflow(p));
    check('html is rtl + hebrew', await p.evaluate(() => document.documentElement.dir === 'rtl' && document.documentElement.lang === 'he'));
    /* the server hides the real-user tile (hide: nowRum) on a site that does not measure real users */
    const nowN = (CFG.hide || []).indexOf('nowRum') >= 0 ? 3 : 4;
    check('"now" card shows ' + nowN + ' tiles' + (nowN === 3 ? ' (hide has nowRum)' : ''), await count(p, '#now .nbox') === nowN, String(await count(p, '#now .nbox')));
    check('bottom line shows 4 tiles', await count(p, '#verdict .vbox') === 4);
    const cards = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.wrap > section.card h2'), (h) => h.firstChild.textContent.trim()));
    const WANT = ['עכשיו', 'שורה תחתונה', 'זמינות', 'מהירות לאורך זמן', 'העמודים העיקריים', 'העמודים הכבדים באתר', 'מוצרים שבורים באתר', 'תעודת האבטחה (המנעול)', 'התראות', 'הודעות שנשלחו לטלפון', 'המדידה עצמה'];
    check('cards appear in the specified order', JSON.stringify(cards) === JSON.stringify(WANT), JSON.stringify(cards));
    check('subtitle shows the last check time and the period', /הבדיקה האחרונה .* · 24 השעות האחרונות/.test(await txt(p, '#sub')), await txt(p, '#sub'));
    check('alerts card and messages card start folded', await p.evaluate(() => document.getElementById('alertsList').parentElement.classList.contains('collapsed') && document.getElementById('msgList').parentElement.classList.contains('collapsed')));
    check('explanations hidden until asked', !(await visible(p, 'p.explain')));
    await p.click('#explbtn');
    check('"הסברים" shows the explanations, and the page stays', await visible(p, 'p.explain') && (await p.getAttribute('#explbtn', 'aria-pressed')) === 'true' && await visible(p, '#verdictCard'));
    await p.evaluate(() => document.getElementById('explbtn').click());     // back, through the script: also when the button hid the page
    check('the screen asks nothing from another host', await p.evaluate(() => performance.getEntriesByType('resource').every((e) => new URL(e.name).host === location.host)));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone.png', fullPage: true });

    /* numbers against the data the server sent */
    const data = s.site || {};
    const per = (Array.isArray(data.availability) ? data.availability : []).filter((r) => r.section === 'לפי עמוד');
    const checksN = per.reduce((a, r) => a + (+r.checks || 0), 0), failN = per.reduce((a, r) => a + (+r.failed || 0), 0);
    const upTile = await txt(p, '#verdict .vbox[data-drill="fails"] .v');
    if (checksN) {
      const up = 100 - 100 * failN / checksN;
      check('uptime tile = 100 − failed/checks, and "100%" only without a single failure', failN === 0 ? upTile === '100%' : /^\d{1,2}\.\d\d%$/.test(upTile) && Math.abs(parseFloat(upTile) - Math.min(up, 99.99)) < 0.0051, upTile + ' for ' + failN + '/' + checksN);
      check('availability table: one row per probed page', await count(p, '#availTbl tbody tr') === per.length);
    } else if (Array.isArray(data.availability)) check('no availability data → empty state text', /אין בדיקות זמינות בתקופה/.test(await txt(p, '#availTbl')));
    const core = (Array.isArray(data.speed) ? data.speed : []).filter((r) => r.section === 'ליבה' && r.strategy === 'mobile');
    if (Array.isArray(data.speed)) check('core pages table: one row per core page (mobile)', core.length ? await count(p, '#coreTbl tbody tr') === core.length : /אין מדידות טלפון בתקופה/.test(await txt(p, '#coreTbl')));
    check('heavy pages table: at most 10 rows', await count(p, '#slowTbl tbody tr') <= 10);

    /* sheets */
    await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
    sh = await sheet(p);
    check('click on uptime opens the failures sheet', sh.title === 'כל הכשלים' && /הבדיקות שנכשלו/.test(sh.body), sh.title);
    if (failN > 0) check('the failures sheet lists the failed checks (an empty page= and bucket= mean "all")', sh.rows >= 1, sh.rows + ' rows for ' + failN + ' failures');
    check('sheet is a bottom sheet on a phone', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs(r.bottom - window.innerHeight) < 2 && r.width >= window.innerWidth - 2; }));
    await p.keyboard.press('Escape');
    check('Escape closes the sheet', !(await sheetOn(p)));
    escapeFailed.add(p); await shut(p);                        // when it stayed open, the test closes it and goes on
    if (core.length) {
      await p.click('#coreTbl tbody tr');
      await p.waitForFunction(() => /המדידות|אין מדידות תקינות/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
      sh = await sheet(p);
      check('click on a core page opens its measurements', /^מהירות: /.test(sh.title), sh.title);
      if (+core[0].checks > 0) check('the measurements sheet lists the runs of that page (an empty bucket= means "the whole period")', sh.rows >= 1, sh.rows + ' rows for ' + core[0].checks + ' runs');
      await p.click('#dx');
    }
    check('no JavaScript errors (phone)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
  });

  await block('A2 desktop and dark', async () => {
    s = await open(browser, PAGE_PATH, DESK); p = s.page;
    check('no horizontal scroll at 1280px', await noOverflow(p));
    await p.click('#verdict .vbox[data-drill="outages"]');
    check('sheet is centered on desktop', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2 && r.width === 720; }));
    await p.click('#dx');
    await p.click('#segH button[data-h="168"]');
    await until(() => s.site && s.site.hours === 168, 15000); await settle(p);
    check('"7 ימים" reloads with a 168-hour window', !!s.site && s.site.hours === 168 && /7 הימים האחרונים/.test(await txt(p, '#rangeTxt')));
    await p.click('#segS button[data-s="desktop"]');
    await until(() => s.site && s.site.strategy === 'desktop', 15000); await settle(p);
    check('"מחשב" reloads with strategy=desktop', !!s.site && s.site.strategy === 'desktop');
    if (SHOTS) await p.screenshot({ path: SHOTS + '/desktop.png', fullPage: true });
    check('no JavaScript errors (desktop)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
    s = await open(browser, PAGE_PATH, PHONE, { dark: true }); p = s.page;
    check('dark mode: dark background, light text', rgbSum(await css(p, 'body', 'backgroundColor')) < 150 && rgbSum(await css(p, 'h1', 'color')) > 500 && rgbSum(await css(p, '#verdict .vbox .v', 'color')) > 500, (await css(p, 'body', 'backgroundColor')) + ' / ' + (await css(p, 'h1', 'color')));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-dark.png', fullPage: true });
    await s.ctx.close();
  });

  /* ================= B. the rules of the screen, against canned answers ================= */

  await block('B1 the cards', async () => {
    s = await fake(browser); p = s.page;
    for (const w of [390, 360, 320]) { await p.setViewportSize({ width: w, height: 800 }); check('no horizontal scroll at ' + w + 'px with every card full', await noOverflow(p), 'body is ' + await p.evaluate(() => document.body.scrollWidth) + 'px wide'); }
    const where = [];
    for (const w of [719, 720]) {
      await p.setViewportSize({ width: w, height: 800 });
      await p.click('#verdict .vbox[data-drill="outages"]');
      where.push(w + ':' + await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs(r.bottom - window.innerHeight) < 2 && r.width >= window.innerWidth - 2 ? 'bottom' : r.width === 720 && r.top > 0 && Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2 ? 'centered' : 'other ' + Math.round(r.top) + '/' + Math.round(r.width); }));
      await closeSheet(p);
    }
    check('the sheet is a bottom sheet up to 719 px and a centered 720 px panel from 720 px', where.join() === '719:bottom,720:centered', where.join());
    await p.setViewportSize(PHONE);
    check('subtitle: site label · last check of the availability flow (viewer\'s clock) · period', / · הבדיקה האחרונה 15:35 · 24 השעות האחרונות$/.test(await txt(p, '#sub')), await txt(p, '#sub'));
    const v = await tiles(p, '#verdict .vbox');
    check('bottom line: the home page verdict comes from the "שורה תחתונה" row', v[0].v === 'מהיר' && v[0].m === '2.3 שניות עד התוכן · 96 מדידות', JSON.stringify(v[0]));
    check('bottom line: uptime with two decimals and the counts', v[1].v === '99.97%' && v[1].m === '2 כשלים מתוך 5,760 בדיקות', JSON.stringify(v[1]));
    check('bottom line: outages and their minutes', v[2].v === '1' && v[2].m === 'סה"כ 7 דקות', JSON.stringify(v[2]));
    check('bottom line: open alerts and the alerts of the period', v[3].v === '3' && v[3].m === '4 בתקופה', JSON.stringify(v[3]));
    check('availability card: a row per page, the outage, red bars and the green line', await count(p, '#availTbl tbody tr') === 4 && await count(p, '#outages li') === 1 && await count(p, '#availChart rect.bar') === 1 && await count(p, '#availChart circle.hit') === 24 && await count(p, '#availChart path.ms') === 1);
    check('speed chart: a legend button and a line per page, a point per bucket', await count(p, '#legend button') === 3 && await count(p, '#speedChart path.ln') === 3 && await count(p, '#speedChart circle.pt') === 72 && await visible(p, '#speedHint'));
    const tags = await texts(p, '#coreTbl tbody tr td:nth-child(2) .tag'), tagCls = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#coreTbl tbody tr td:nth-child(2) .tag'), (e) => e.className));
    check('core pages: LCP 2000 / 2500 / 4000 / 4001 ms read מצוין / מהיר / בינוני / איטי', tags.join() === 'מצוין,מהיר,בינוני,איטי' && tagCls.join() === 'tag ok,tag ok,tag w,tag d', tags.join() + ' ' + tagCls.join());
    const cr = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#coreTbl tbody tr td:last-child .tag'), (e) => e.className + ':' + e.textContent));
    check('core pages: Google\'s real-user verdict FAST / AVERAGE / SLOW / none', cr.join() === 'tag ok:מהיר,tag w:בינוני,tag d:איטי,tag n:אין מספיק תנועה', cr.join());
    check('heavy pages: the coverage line (the "כיסוי" row) and ten rows (the "האיטיים באתר" rows)', (await txt(p, '#coverage')) === 'נדגמו 288 מתוך 412 עמודי האתר בתקופה.' && await count(p, '#slowTbl tbody tr') === 10 && /heavy 0/.test(await txt(p, '#slowTbl tbody tr td')), await txt(p, '#coverage'));
    check('broken products: counts per issue, 60 of 70 rows on the screen, the note', /^בלי מחיר: 20 · לא במלאי: 50 · לפי צילום 2026-11-12$/.test(await txt(p, '#issuesTbl p.muted')) && await shown(p, '#issuesTbl tbody tr') === 60 && /מוצגים 60 מתוך 70\./.test(await txt(p, '#issuesTbl')), await txt(p, '#issuesTbl p.muted'));
    check('broken products: "לא במלאי" yellow, any other issue red; the name links to the product', (await p.getAttribute('#issuesTbl tbody tr:nth-child(1) .tag', 'class')) === 'tag d' && (await p.getAttribute('#issuesTbl tbody tr:nth-child(21) .tag', 'class')) === 'tag w' && (await p.getAttribute('#issuesTbl tbody tr:nth-child(1) a', 'href')) === U + '/product/0/');
    const ce = await tiles(p, '#certBox .vbox');
    check('certificate: days left, expiry date, issuer, state', ce.length === 2 && ce[0].v === '23 ימים' && /Test CA/.test(ce[0].m) && /5\.12\.2026/.test(ce[0].m) && ce[1].v === 'לשים לב' && /נבדק 12\.11, 04:03/.test(ce[1].m), JSON.stringify(ce));
    check('alerts card: folded, with the number of alerts in its title; four rows inside', /התראות · 4/.test(await txt(p, '#alertsCard h2')) && await count(p, '#alertsList li') === 4 && !(await visible(p, '#alertsList')));
    await p.click('#alertsCard .foldhead');
    check('a tap on the title unfolds the alerts card', await visible(p, '#alertsList') && /נסגרה/.test(await txt(p, '#alertsList li:nth-child(4)')) && /12\.11 01:20 → 12\.11 01:21 · 1 דק'/.test(await txt(p, '#alertsList li:nth-child(4)')));
    await p.click('#msgCard .foldhead');
    const mt = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#msgList li .tag'), (e) => e.className + ':' + e.textContent));
    check('message log: התראה red, חזר לתקין green, any other kind grey; "לא נשלחה" on a failed push', mt.join() === 'tag d:התראה,tag ok:חזר לתקין,tag n:בוקר' && /לא נשלחה/.test(await txt(p, '#msgList li:nth-child(2)')) && !/לא נשלחה/.test(await txt(p, '#msgList li:nth-child(1)')) && /הודעות שנשלחו לטלפון · 3/.test(await txt(p, '#msgCard h2')), mt.join());
    const ht = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#healthTbl li .tag'), (e) => e.className + ':' + e.textContent));
    check('measurement flows: תקין green, מתעכב yellow, שקט red, אין נתון grey', ht.join() === 'tag ok:תקין,tag w:מתעכב,tag d:שקט,tag n:אין נתון,tag ok:תקין' && /שקט כבר 3 ימים/.test(await txt(p, '#healthTbl li:nth-child(3)')), ht.join());
    check('numbers in tables: left-aligned, left to right, tabular figures', (await css(p, '#availTbl td.num', 'direction')) === 'ltr' && (await css(p, '#availTbl td.num', 'textAlign')) === 'left' && /tabular-nums/.test(await css(p, '#availTbl td.num', 'fontVariantNumeric')));
    check('the period, strategy and date controls are at least 44 px high', await p.evaluate(() => Array.prototype.every.call(document.querySelectorAll('#segH button, #segS button, .dates input, #dGo'), (e) => e.getBoundingClientRect().height >= 44)));
    check('a wide table scrolls inside its card', (await css(p, '#coreTbl .tblwrap', 'overflowX')) === 'auto' && await p.evaluate(() => { const w = document.querySelector('#coreTbl .tblwrap'); return w.scrollWidth > w.clientWidth && w.getBoundingClientRect().right <= window.innerWidth; }));
    check('no JavaScript errors (canned data)', s.errors.length === 0, s.errors.join(' | '));
    await p.click('#segS button[data-s="desktop"]'); await settle(p);
    check('"מחשב" shows the desktop rows of the core pages; the bottom line stays the phone\'s', (await texts(p, '#coreTbl tbody tr td:nth-child(2) .tag')).join() === 'מצוין,מצוין,בינוני,בינוני' && (await tiles(p, '#verdict .vbox'))[0].v === 'מהיר', (await texts(p, '#coreTbl tbody tr td:nth-child(2) .tag')).join());
    await p.click('#segS button[data-s="mobile"]'); await settle(p);

    /* other values of the same parts */
    await reload(s, (d) => { d.availability.forEach((r) => { r.failed = 0; }); d.availability.pop(); d.cert.days_left = 30; d.speed[0].checks = 1; d.speed[d.speed.length - 1].checks = 1; d.alerts_recent = []; d.alerts_open = []; });
    let t = await tiles(p, '#verdict .vbox');
    check('uptime reads "100%" when no check failed', t[1].v === '100%' && t[1].m === '0 כשלים מתוך 5,760 בדיקות', JSON.stringify(t[1]));
    check('no outage, no alert: the tiles say so in words', t[2].v === '0' && t[2].m === 'האתר לא נפל בתקופה' && t[3].v === '0' && t[3].m === 'אין התראות בתקופה' && /אין התראות בתקופה\. זה טוב\./.test(await txt(p, '#alertsList')));
    check('one measurement, one sampled page: singular Hebrew', t[0].m === '2.3 שניות עד התוכן · מדידה אחת' && (await txt(p, '#coverage')) === 'נדגם עמוד אחד מתוך 412 עמודי האתר בתקופה.', t[0].m + ' | ' + await txt(p, '#coverage'));
    check('certificate with 30 days: תקין (green)', (await txt(p, '#certBox .tag')) === 'תקין' && (await p.getAttribute('#certBox .tag', 'class')) === 'tag ok');
    await reload(s, (d) => { d.availability[3].failed = 1; d.availability[0].checks = 100000 - 180 * 24; d.cert.days_left = 29; d.speed[1].lcp_p50 = 2001; d.speed[2].lcp_p50 = 2501; });
    check('core pages: 2001 ms is no longer מצוין, 2501 ms is no longer מהיר', (await texts(p, '#coreTbl tbody tr td:nth-child(2) .tag')).join() === 'מהיר,בינוני,בינוני,איטי', (await texts(p, '#coreTbl tbody tr td:nth-child(2) .tag')).join());
    t = await tiles(p, '#verdict .vbox');
    check('one failure in 100,000 checks is not "100%": the text stops at 99.99%', t[1].v === '99.99%' && t[1].m === 'כשל אחד מתוך 100,000 בדיקות', JSON.stringify(t[1]));
    check('certificate with 29 days: לשים לב (yellow)', (await txt(p, '#certBox .tag')) === 'לשים לב' && (await p.getAttribute('#certBox .tag', 'class')) === 'tag w');
    await reload(s, (d) => { d.cert.days_left = 14; d.availability[3].failed = 51; d.availability[0].checks = 100000 - 180 * 24; });
    check('51 failures in 100,000 checks: 99.95%', (await tiles(p, '#verdict .vbox'))[1].v === '99.95%');
    check('certificate with 14 days: still yellow', (await p.getAttribute('#certBox .tag', 'class')) === 'tag w');
    await reload(s, (d) => { d.cert.days_left = 13; });
    check('certificate with 13 days: לחדש עכשיו (red)', (await txt(p, '#certBox .tag')) === 'לחדש עכשיו' && (await p.getAttribute('#certBox .tag', 'class')) === 'tag d');
    await reload(s, (d) => { d.cert.days_left = 1; });
    check('certificate with one day left: "יום אחד"', (await tiles(p, '#certBox .vbox'))[0].v === 'יום אחד', (await tiles(p, '#certBox .vbox'))[0].v);
    await reload(s, (d) => { d.cert = { host: 'shop.test', issuer: null, not_after: null, days_left: null, ok: false, err: 'handshake failed', checked_at: '2026-11-12T04:03:00+02:00' }; });
    t = await tiles(p, '#certBox .vbox');
    check('certificate check failed: said in words, red, with the reason', t[0].v === 'הבדיקה נכשלה' && t[0].m === 'handshake failed' && t[1].v === 'לא ידוע' && (await p.getAttribute('#certBox .tag', 'class')) === 'tag d', JSON.stringify(t));
    await reload(s, (d) => { d.cert = null; d.speed = [{ section: 'שורה תחתונה', page: s.F.HOME, url: U + '/', lcp_p50: null, checks: 0, verdict: null }, { section: 'כיסוי', checks: 0, slow_runs: 0 }]; d.speed_series = []; d.product_issues = []; d.availability = []; d.availability_series = []; d.health = []; });
    t = await tiles(p, '#verdict .vbox');
    const wrap = await txt(p, '.wrap');
    check('before the first measurement every card has its own empty text', t[0].v === 'אין נתונים' && t[0].m === 'מדידת המהירות עדיין לא התחילה' && t[1].v === '—' && t[1].m === 'אין בדיקות בתקופה'
      && /אין בדיקות זמינות בתקופה\./.test(wrap) && /מדידת המהירות עדיין לא התחילה\./.test(wrap) && /אין מדידות טלפון בתקופה\./.test(wrap) && /הסבב על כל האתר עדיין לא התחיל\./.test(wrap)
      && /לא נמצאו מוצרים שבורים בצילום האחרון\./.test(wrap) && /עדיין לא נבדק/.test(wrap) && /אין נתוני מדידה\./.test(wrap) && (await txt(p, '#coverage')) === '' && !wrap.includes(NA), JSON.stringify(t.slice(0, 2)));
    await s.ctx.close();
  });

  await block('B2 a failed read is never good news', async () => {
    s = await fake(browser, { clock: '2026-11-12T16:00:00+02:00', over: { '/site': () => ({ status: 502, body: { detail: 'Bad Gateway' } }), '/site/now': fail502, '/messages': fail502 } }); p = s.page;
    const partsNA = async () => {
      const t = await tiles(p, '#verdict .vbox'), ids = ['availTbl', 'speedChart', 'coreTbl', 'slowTbl', 'certBox', 'alertsList', 'healthTbl'];
      const bad = [];
      t.forEach((x) => { if (x.v !== '—' || x.m !== NA) bad.push(x.k + '=' + x.v + '/' + x.m); });
      for (const id of ids) if (!(await txt(p, '#' + id)).includes(NA)) bad.push(id + '=' + await txt(p, '#' + id));
      if (!/הבדיקה לא זמינה\./.test(await txt(p, '#issuesTbl'))) bad.push('issuesTbl=' + await txt(p, '#issuesTbl'));
      const w = await txt(p, '.wrap');
      const good = w.match(/זה טוב|האתר לא נפל|אין התראות בתקופה|עדיין לא נבדק|לא נמצאו מוצרים|לא נשלחו הודעות|אין נתוני מדידה|אין בדיקות|עדיין לא התחיל/);
      if (good) bad.push('reads as good news: ' + good[0]);
      return bad;
    };
    let bad = await partsNA();
    check('the read failed (502): four tiles and every card say "' + NA + '"; no 0, no "that\'s good"', bad.length === 0 && (await count(p, '#verdict .vbox')) === 4, bad.join(' | '));
    check('the read failed (502): the subtitle says so', /לא הצלחתי לטעון את הנתונים/.test(await txt(p, '#sub')), await txt(p, '#sub'));
    check('the read failed (502): the message log does not say "nothing was sent"', (await txt(p, '#msgList')).includes(NA), await txt(p, '#msgList'));
    let nw = await tiles(p, '#now .nbox');
    check('"עכשיו" failed: one grey tile instead of "טוען…"', nw.length === 1 && nw[0].v === '—' && nw[0].m === NA && nw[0].dot === 'n' && /לא הצלחתי לטעון את "עכשיו"/.test(await txt(p, '#nowtick')), JSON.stringify(nw));
    await p.click('#verdict .vbox[data-drill="alerts"]');
    check('a tile without data opens a sheet that says so (not "אין התראה פתוחה")', (await sheet(p)).body.includes(NA) && !/אין התראה פתוחה/.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    check('no JavaScript errors after a failed read', s.errors.length === 0, s.errors.join(' | '));
    const tries = () => s.F.n('/site') + '/' + s.F.n('/site/now');
    check('a failed read is not repeated at once', tries() === '1/1', tries());
    await p.clock.runFor(5000);
    check('…the screen and the "עכשיו" card try once more after 5 seconds', await until(() => tries() === '2/2', 2000), tries());
    await sleep(200); await p.clock.runFor(20000); await sleep(200);
    check('…and then wait for the regular 60-second reload', tries() === '2/2', tries());

    s.F.over = {};                                             // the backend is back
    await p.clock.runFor(60000); await until(async () => (await count(p, '#now .nbox')) === 4); await settle(p);
    check('the next reload brings the numbers back', (await tiles(p, '#verdict .vbox'))[1].v === '99.97%' && (await tiles(p, '#now .nbox'))[0].v === 'פעיל' && await visible(p, '#alertbar'));
    await p.click('#msgCard .foldhead');

    const errPart = { error: 'statement timeout' };            // each part fails alone, the answer is 200
    s.F.over['/site'] = (q) => ({ body: Object.assign(s.F.site(q), { availability: errPart, availability_series: errPart, speed: errPart, speed_series: errPart, alerts_open: errPart, alerts_recent: errPart, health: errPart, product_issues: errPart, cert: errPart }) });
    s.F.over['/site/now'] = fail502;
    s.F.over['/messages'] = () => ({ body: { error: 'statement timeout' } });
    const tick = await txt(p, '#nowtick');
    await p.clock.runFor(60000); await until(async () => (await txt(p, '#nowtick')) !== tick); await settle(p);
    bad = await partsNA();
    check('every part is {"error"} (status 200): the numbers of a minute ago do not stay on the screen', bad.length === 0, bad.join(' | '));
    check('…the message log says it could not be read', /לא הצלחתי לטעון את ההודעות\./.test(await txt(p, '#msgList')) && !/· \d/.test(await txt(p, '#msgCard h2')), await txt(p, '#msgList'));
    nw = await tiles(p, '#now .nbox');
    check('…"עכשיו" drops the "פעיל" of a minute ago', nw.length === 1 && nw[0].v === '—' && (await count(p, '#nowpages .tag')) === 0, JSON.stringify(nw));
    check('…the red bar stays: a list of alerts that did not arrive is not "no alerts"', await visible(p, '#alertbar') && (await count(p, '#alertbar .arow')) === 3);

    s.F.over['/site'] = (q) => ({ body: Object.assign(s.F.site(q), { cert: errPart, alerts_recent: errPart }) });   // only two parts
    s.F.over['/site/now'] = null; s.F.over['/messages'] = null;
    await reload(s);
    const t = await tiles(p, '#verdict .vbox');
    check('one failed part marks only its own cards', (await txt(p, '#certBox')).includes(NA) && (await txt(p, '#alertsList')).includes(NA) && t[3].v === '3' && t[3].m === NA && t[1].v === '99.97%' && (await count(p, '#availTbl tbody tr')) === 4 && (await count(p, '#healthTbl li')) === 5, JSON.stringify(t));
    await s.ctx.close();
  });

  await block('B3 reloads', async () => {
    s = await fake(browser, { clock: '2026-11-12T16:00:00+02:00' }); p = s.page;
    const n0 = [s.F.n('/site'), s.F.n('/site/now')];
    await p.clock.runFor(59000); await sleep(150);
    check('nothing reloads before 60 seconds pass', s.F.n('/site') === n0[0] && s.F.n('/site/now') === n0[1], s.F.n('/site') + '/' + s.F.n('/site/now'));
    await p.clock.runFor(1000);
    check('after 60 seconds the screen and the "עכשיו" card reload by themselves', await until(() => s.F.n('/site') === n0[0] + 1 && s.F.n('/site/now') === n0[1] + 1, 3000), s.F.n('/site') + '/' + s.F.n('/site/now'));
    await settle(p);
    await p.click('#verdict .vbox[data-drill="outages"]');
    await p.clock.runFor(60000);
    check('while a sheet is open the "עכשיו" card still reloads…', await until(() => s.F.n('/site/now') === n0[1] + 2, 3000));
    await sleep(150);
    check('…and the screen behind the sheet does not', s.F.n('/site') === n0[0] + 1 && await sheetOn(p), String(s.F.n('/site')));
    await closeSheet(p);
    await p.clock.runFor(60000);
    check('with the sheet closed the screen reloads again', await until(() => s.F.n('/site') === n0[0] + 2, 3000));
    await settle(p);

    /* a slow answer that arrives after a newer one */
    s.F.over['/site'] = (q) => q.h === '168' ? { delay: 900, body: s.F.site(q) } : null;
    await p.click('#segH button[data-h="168"]'); await sleep(350);
    check('while loading: the pill "טוען נתונים…" shows and the cards dim', await visible(p, '.loadpill') && /טוען נתונים…/.test(await txt(p, '.loadpill')) && +(await css(p, '#verdictCard', 'opacity')) < 1, await css(p, '#verdictCard', 'opacity'));
    await p.click('#segH button[data-h="720"]');
    await until(async () => (await txt(p, '#availTbl tbody td.num')) === '43,200'); await sleep(1200);
    check('an answer that arrives after a newer request started is thrown away', (await txt(p, '#availTbl tbody td.num')) === '43,200' && /30 הימים האחרונים/.test(await txt(p, '#sub')) && (await txt(p, '#rangeTxt')) === 'מוצג: 30 הימים האחרונים', (await txt(p, '#availTbl tbody td.num')) + ' | ' + await txt(p, '#sub'));
    check('…and the loading marks are gone', !(await visible(p, '.loadpill')) && (await css(p, '#verdictCard', 'opacity')) === '1');
    check('a period button shows which period is on', (await p.getAttribute('#segH button[data-h="720"]', 'aria-pressed')) === 'true' && (await p.getAttribute('#segH button[data-h="168"]', 'aria-pressed')) === 'false');
    await s.ctx.close();
  });

  await block('B4 the red alert bar', async () => {
    s = await fake(browser); p = s.page;
    check('the bar counts the open alerts nobody marked as seen', (await txt(p, '#alertbar .acount')) === '⚠ 3 התראות פעילות', await txt(p, '#alertbar .acount'));
    check('the bar starts collapsed', await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed')) && !(await visible(p, '#alertbar .alist')));
    await p.click('#alertbar .ahead');
    check('a tap opens the list', await shown(p, '#alertbar .arow') === 3 && await visible(p, '#alertbar .abulk'));
    const sub = await txt(p, '#alertbar .arow[data-id="41"] .sub');
    check('a row: the body without the line that repeats the title, a readable page name instead of the address, then "מאז <time>"', sub === 'קוד 502 · /cart · מאז 12.11 11:02', sub);
    check('a row with an address in its body gets the link "לפתוח את העמוד ↗"; a row without one does not', (await count(p, '#alertbar .alink')) === 2 && (await p.getAttribute('#alertbar .arow[data-id="41"] .alink', 'href')) === U + '/cart/' && (await count(p, '#alertbar .arow[data-id="39"] .alink')) === 0);
    await p.evaluate(() => { const a = document.querySelector('#alertbar .alink'); a.addEventListener('click', (e) => e.preventDefault()); a.click(); });
    check('a tap on the link does not open the alert as well', !(await sheetOn(p)) && (await p.getAttribute('#alertbar .alink', 'target')) === '_blank');
    await reload(s);
    check('once opened, the bar stays open across a reload', !(await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed'))));
    await p.evaluate(() => { window.__dim = 0; new MutationObserver(() => { if (document.body.classList.contains('loading')) window.__dim++; }).observe(document.body, { attributes: true, attributeFilter: ['class'] }); });
    const sites = s.F.n('/site');
    const quiet = async () => (await p.evaluate(() => window.__dim)) === 0 && s.F.n('/site') === sites && !(await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed')));
    await p.click('#alertbar .arow[data-id="40"] .acb input');
    check('a checkbox selects its row and does not open the alert', (await txt(p, '#abDel')) === 'מחק מסומנות (1)' && !(await p.isChecked('#abAll')) && !(await sheetOn(p)), await txt(p, '#abDel'));
    await p.click('#alertbar .arow[data-id="40"] .acb input');
    check('nothing selected: "מחק מסומנות" is off', await p.isDisabled('#abDel') && (await txt(p, '#abDel')) === 'מחק מסומנות');
    await p.click('#alertbar .arow[data-id="41"] .ax');
    check('✕ removes the row at once', (await count(p, '#alertbar .arow')) === 2 && (await txt(p, '#alertbar .acount')) === '⚠ 2 התראות פעילות' && !(await sheetOn(p)), await txt(p, '#alertbar .acount'));
    await until(() => s.F.n('/alerts/ack') === 1, 2000); await sleep(200);
    check('✕ sends one POST {"ids":[41]} to /alerts/ack', s.F.n('/alerts/ack', 'POST') === 1 && s.F.last('/alerts/ack').body === '{"ids":[41]}', s.F.last('/alerts/ack').body);
    check('✕ does not reload the screen and does not fold the list', await quiet(), 'dimmed ' + await p.evaluate(() => window.__dim) + ' times, ' + (s.F.n('/site') - sites) + ' reloads');
    await p.click('#abAll');
    check('"לסמן הכול" selects every row', (await p.evaluate(() => Array.prototype.every.call(document.querySelectorAll('#alertbar .acb input'), (c) => c.checked))) && (await txt(p, '#abDel')) === 'מחק מסומנות (2)', await txt(p, '#abDel'));
    await p.click('#abDel');
    check('"מחק מסומנות" clears the bar at once', !(await visible(p, '#alertbar')));
    await until(() => s.F.n('/alerts/ack') === 2, 2000); await sleep(200);
    check('a bulk delete is one POST with all the ids', s.F.n('/alerts/ack', 'POST') === 2 && s.F.last('/alerts/ack').body === '{"ids":[39,40]}', s.F.last('/alerts/ack').body);
    check('a bulk delete does not reload the screen', (await p.evaluate(() => window.__dim)) === 0 && s.F.n('/site') === sites, 'dimmed ' + await p.evaluate(() => window.__dim) + ' times, ' + (s.F.n('/site') - sites) + ' reloads');
    await reload(s);
    check('alerts marked as seen stay out of the bar after a reload, and still count as open', !(await visible(p, '#alertbar')) && (await tiles(p, '#verdict .vbox'))[3].v === '3');

    s.F.acked.clear(); s.F.ALERTS = s.F.ALERTS.slice(0, 1);
    await reload(s);
    check('one alert: "⚠ 1 התראה פעילה"', (await txt(p, '#alertbar .acount')) === '⚠ 1 התראה פעילה', await txt(p, '#alertbar .acount'));
    s.F.over['/alerts/ack'] = () => ({ status: 500, body: { error: 'boom' } });
    const before = s.F.n('/site');
    await p.click('#alertbar .arow .ax');
    check('a delete that the server refused brings the row back', await until(async () => s.F.n('/site') > before && (await count(p, '#alertbar .arow')) === 1 && await visible(p, '#alertbar'), 4000), (await count(p, '#alertbar .arow')) + ' rows, ' + (s.F.n('/site') - before) + ' reloads');
    await settle(p);
    await p.click('#alertbar .arow .at'); await sheetReady(p);
    check('a tap on a row of the bar opens that alert', (await sheet(p)).title === 'האתר לא עונה: סל' && s.F.last('/site/drill').q.what === 'alert' && s.F.last('/site/drill').q.id === '41');
    check('no JavaScript errors (alert bar)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
  });

  await block('B5 every click opens its sheet', async () => {
    s = await fake(browser); p = s.page;
    const dq = () => s.F.last('/site/drill').q;
    const drills = () => s.F.n('/site/drill');
    await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
    sh = await sheet(p);
    check('tile "זמינות" → all failed checks: what=fails with page= and bucket= empty, and the period', sh.title === 'כל הכשלים' && dq().what === 'fails' && dq().page === '' && dq().bucket === '' && dq().h === '24', JSON.stringify(dq()));
    check('…the sheet: the sum, what happened, the split per page, the table', sh.rows === 2 && /2 בדיקות נכשלו מתוך 5,760/.test(sh.body) && /מה קרה: קוד 502 × 1 · שגיאת חיבור × 1/.test(sh.body) && sh.items === 4 && /connection reset by peer/.test(sh.body), sh.body.slice(0, 200));
    await p.mouse.click(8, 8);
    check('a click outside the sheet closes it', !(await sheetOn(p)));
    await p.click('#availTbl tbody tr:nth-child(4)'); await sheetReady(p);
    check('a row of the availability table → that page\'s failed checks (what=fails&page=)', (await sheet(p)).title === 'הכשלים של עמוד סל' && dq().what === 'fails' && dq().page === 'סל' && dq().bucket === '', JSON.stringify(dq()));
    await p.click('#dx');
    check('✕ closes the sheet', !(await sheetOn(p)));
    await p.click('#availChart rect.bar'); await sheetReady(p);
    check('a red bar → the failed checks of that hour (what=fails&bucket=)', (await sheet(p)).title === 'הכשלים ב-12.11 בשעה 03:00' && dq().what === 'fails' && dq().bucket === '2026-11-12 03:00' && dq().page === '', (await sheet(p)).title + ' ' + JSON.stringify(dq()));
    await closeSheet(p);
    await p.locator('#availChart circle.hit').nth(5).click(); await sheetReady(p);
    sh = await sheet(p);
    check('a point on the green line → response time per page (what=bucket&bucket=)', sh.title === 'זמן תגובת השרת ב-12.11 בשעה 05:00' && dq().what === 'bucket' && dq().bucket === '2026-11-12 05:00' && sh.rows === 4 && /חציון זמן התגובה: 302 ms/.test(sh.body), sh.title + ' ' + JSON.stringify(dq()));
    await closeSheet(p);
    await p.locator('#speedChart circle.pt').nth(2).click(); await sheetReady(p);
    sh = await sheet(p);
    check('a point of the speed chart → that page\'s runs in that hour (what=runs&url=&strategy=&bucket=)', sh.title === 'מהירות: ' + s.F.HOME + ' ב-12.11 בשעה 02:00' && dq().what === 'runs' && dq().url === U + '/' && dq().strategy === 'mobile' && dq().bucket === '2026-11-12 02:00', sh.title + ' ' + JSON.stringify(dq()));
    check('the runs sheet: count, median, slowest, fastest, Google\'s real-user verdict', /120 מדידות בטלפון\. חציון 2\.5 שניות עד התוכן העיקרי: מהיר\. הכי איטית 2\.5 ש' \(.*\), הכי מהירה 2\.4 ש' \(.*\)\. אצל גולשים אמיתיים גוגל מודדת: מהיר \(2\.1 ש'\)\./.test(sh.body), sh.body.slice(0, 220));
    const why = await texts(p, '#dbody ul.list li');
    check('the runs sheet: "מה מאט את העמוד" in plain Hebrew; an unknown reason keeps the title the server sent', why.length === 2 && why[0] === '0.9 ש\' תמונות גדולות מדי לגודל שבו הן מוצגות' && why[1] === '0.3 ש\' סיבה שאין לה תרגום במסך', why.join(' | '));
    check('the runs sheet: the first 100 runs, the note, the link to the page', sh.rows === 100 && /מוצגות 100 מתוך 120\./.test(sh.body) && (await p.getAttribute('#dbody p.more a', 'href')) === U + '/');
    await closeSheet(p);
    const pts = await count(p, '#speedChart circle.pt');
    await p.click('#legend button:nth-child(2)');
    check('a legend button hides its line', (await p.getAttribute('#legend button:nth-child(2)', 'aria-pressed')) === 'false' && (await count(p, '#speedChart circle.pt')) === pts - 24 && (await count(p, '#speedChart path.ln')) === 2);
    await p.click('#legend button:nth-child(2)');
    check('…and brings it back', (await count(p, '#speedChart circle.pt')) === pts && (await p.getAttribute('#legend button:nth-child(2)', 'aria-pressed')) === 'true');
    await p.click('#coreTbl tbody tr:nth-child(2)'); await sheetReady(p);
    check('a row of the core pages → its runs (what=runs&url=, bucket empty)', (await sheet(p)).title === 'מהירות: קטגוריה' && dq().url === U + '/product-category/sofas/' && dq().bucket === '' && dq().strategy === 'mobile', JSON.stringify(dq()));
    await closeSheet(p);
    await p.click('#slowTbl tbody tr:nth-child(3)'); await sheetReady(p);
    check('a row of the heavy pages → its runs, titled with the readable name', (await sheet(p)).title === 'מהירות: מוצר: heavy 2' && dq().url === U + '/product/heavy-2/', (await sheet(p)).title);
    await closeSheet(p);
    await p.click('#verdict .vbox[data-drill="home"]'); await sheetReady(p);
    check('tile "מהירות עמוד הבית בטלפון" → the home page\'s runs (the url of the bottom-line row)', (await sheet(p)).title === 'מהירות: ' + s.F.HOME && dq().what === 'runs' && dq().url === U + '/', (await sheet(p)).title);
    await closeSheet(p);
    let n = drills();
    await p.click('#verdict .vbox[data-drill="outages"]');
    sh = await sheet(p);
    check('tile "נפילות" → the outages, without a data call', sh.title === 'נפילות' && /^נפילה אחת בתקופה\./.test(sh.body) && /סך הכל 7 דקות/.test(sh.body) && sh.items === 1 && drills() === n, sh.body.slice(0, 80));
    await closeSheet(p);
    await p.click('#outages li');
    check('a row of the outage list → that outage', (await sheet(p)).title === 'נפילות' && /12\.11 03:12 → 12\.11 03:19/.test((await sheet(p)).body));
    await closeSheet(p);
    await p.click('#verdict .vbox[data-drill="alerts"]');
    sh = await sheet(p);
    check('tile "התראות פתוחות" → the alerts of the period', sh.title === 'התראות' && /^3 התראות פתוחות עכשיו\. 4 התראות בתקופה\./.test(sh.body) && sh.items === 4, sh.body.slice(0, 80));
    await p.click('#dbody li:nth-child(1)'); await sheetReady(p);
    sh = await sheet(p);
    check('…a row there → the alert (what=alert&id=)', sh.title === 'האתר לא עונה: סל' && dq().what === 'alert' && dq().id === '41', sh.title + ' ' + JSON.stringify(dq()));
    check('the alert sheet: timing, body, the rule, the failed checks, the pushes', /^עדיין פתוחה, נפתחה ב-12\.11 11:02, סך הכל 14 דקות\./.test(sh.body) && /הכלל: כל כשל בודד מתריע, גם של שנייה\./.test(sh.body) && sh.rows === 2 && /קוד 502/.test(sh.body) && /timeout/.test(sh.body) && /נשלחהפתיחה/.test(sh.body), sh.body.slice(0, 200));
    await closeSheet(p);
    await p.click('#alertsCard .foldhead'); await p.click('#alertsList li:nth-child(4)'); await sheetReady(p);
    sh = await sheet(p);
    check('a row of the alerts card → the alert; a closed one-minute alert reads "דקה אחת"; a push the service refused reads "נכשלה"', dq().id === '38' && /^נסגרה\. נפתחה ב-12\.11 01:20, נסגרה ב-12\.11 01:21, סך הכל דקה אחת\./.test(sh.body) && /נכשלהחזר לתקין/.test(sh.body), sh.body.slice(0, 120));
    await closeSheet(p);
    await p.click('#alertsList li:nth-child(2)'); await sheetReady(p);
    check('a "slow" alert explains the slow rule', /עמוד עיקרי נמדד איטי \(מעל 4 שניות עד התוכן\) פעמיים ברצף/.test((await sheet(p)).body));
    await closeSheet(p);
    n = drills();
    await p.click('#healthTbl li:nth-child(3)');
    sh = await sheet(p);
    check('a row of "המדידה עצמה" → what the flow measures and its state, without a data call', sh.title === 'טעינת מפת האתר' && /^שקט: נעצר\. המספרים שתלויים בו ישנים\. הריצה האחרונה: 12\.11, 15:35\./.test(sh.body) && /פעם בלילה נטענת רשימת כל העמודים באתר/.test(sh.body) && /סף איחור: 5 דק' · סף שתיקה: 15 דק'/.test(sh.body) && drills() === n, sh.body.slice(0, 160));
    await closeSheet(p);
    await p.click('#healthTbl li:nth-child(5)');
    check('a flow the screen has no text for shows the note the server sent', /הסבר שהשרת שלח/.test((await sheet(p)).body) && /^תקין: רץ כמו שצריך\./.test((await sheet(p)).body));
    await closeSheet(p);
    await p.click('#healthTbl li:nth-child(4)');
    check('a flow that never ran says so', /^אין נתון: עדיין לא רץ אף פעם\./.test((await sheet(p)).body) && !/הריצה האחרונה/.test((await sheet(p)).body));
    await closeSheet(p);

    /* the period and the strategy travel with every call */
    await p.click('#segH button[data-h="168"]'); await settle(p);
    await p.click('#segS button[data-s="desktop"]'); await settle(p);
    check('"מחשב": the screen asks for strategy=desktop and says so', s.F.last('/site').q.strategy === 'desktop' && s.F.last('/site').q.h === '168' && (await p.getAttribute('#segS button[data-s="desktop"]', 'aria-pressed')) === 'true' && (await p.getAttribute('#segS button[data-s="mobile"]', 'aria-pressed')) === 'false', JSON.stringify(s.F.last('/site').q));
    check('the message log is asked for the same period', s.F.last('/messages').q.h === '168' && !('f' in s.F.last('/messages').q), JSON.stringify(s.F.last('/messages').q));
    await p.click('#coreTbl tbody tr:nth-child(1)'); await sheetReady(p);
    check('a sheet asks for the same period and strategy as the screen', dq().h === '168' && dq().strategy === 'desktop' && /מדידות במחשב/.test((await sheet(p)).body), JSON.stringify(dq()));
    await closeSheet(p);
    s.F.over['/site/drill'] = fail502;
    await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
    check('a sheet whose data call failed says so', /לא הצלחתי לטעון\./.test((await sheet(p)).body) && !/אין כשלים/.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    check('no JavaScript errors (sheets)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
  });

  await block('B6 the date range', async () => {
    s = await fake(browser, { clock: '2026-11-14T00:30:00+02:00' }); p = s.page;       // half an hour after midnight, local time
    let n = s.F.n('/site');
    await p.click('#dGo'); await sleep(150);
    check('"הצג" without a start date asks nothing and puts the cursor in "מתאריך"', s.F.n('/site') === n && await p.evaluate(() => document.activeElement.id === 'dFrom'));
    await p.fill('#dFrom', '2026-11-05'); await p.fill('#dTo', '2026-11-01'); await p.click('#dGo'); await settle(p);
    let q = s.F.last('/site').q;
    check('"הצג" sends f and t (reversed dates are swapped) and no h', q.f === '2026-11-01' && q.t === '2026-11-05' && !('h' in q) && s.F.n('/site') === n + 1, JSON.stringify(q));
    check('…the line under the controls and the subtitle show the range; no period button is on', (await txt(p, '#rangeTxt')) === 'מוצג: מ-01.11.2026 עד 05.11.2026' && /מ-01\.11\.2026 עד 05\.11\.2026$/.test(await txt(p, '#sub')) && (await count(p, '#segH button[aria-pressed="true"]')) === 0, await txt(p, '#rangeTxt'));
    check('…the message log is asked for the same range', s.F.last('/messages').q.f === '2026-11-01' && s.F.last('/messages').q.t === '2026-11-05' && !('h' in s.F.last('/messages').q), JSON.stringify(s.F.last('/messages').q));
    await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
    q = s.F.last('/site/drill').q;
    check('…and so is a sheet', q.f === '2026-11-01' && q.t === '2026-11-05' && !('h' in q), JSON.stringify(q));
    await closeSheet(p);
    await p.fill('#dFrom', '2026-11-10'); await p.fill('#dTo', ''); await p.click('#dGo'); await settle(p);
    q = s.F.last('/site').q;
    check('an empty end date means today', q.f === '2026-11-10' && q.t === '2026-11-14' && (await p.inputValue('#dTo')) === '2026-11-14', JSON.stringify(q));
    await p.fill('#dFrom', '2026-11-14'); await p.fill('#dTo', ''); await p.click('#dGo'); await settle(p);
    q = s.F.last('/site').q;
    check('…today on the viewer\'s calendar (00:30 local time is already the new day)', q.f === '2026-11-14' && q.t === '2026-11-14' && (await p.inputValue('#dTo')) === '2026-11-14', JSON.stringify(q));
    await p.click('#segH button[data-h="24"]'); await settle(p);
    q = s.F.last('/site').q;
    check('a period button sends h and clears the dates', q.h === '24' && !('f' in q) && (await p.inputValue('#dFrom')) === '' && (await p.inputValue('#dTo')) === '' && (await txt(p, '#rangeTxt')) === 'מוצג: 24 השעות האחרונות', JSON.stringify(q));
    await s.ctx.close();
  });

  await block('B7 the "עכשיו" card against the thresholds', async () => {
    s = await fake(browser, { clock: '2026-11-12T16:00:00+02:00' }); p = s.page;
    const H = s.F.HOME;
    const now = async (change) => {
      s.F.over['/site/now'] = () => { const d = s.F.now(); change(d); return { body: d }; };
      const before = await txt(p, '#nowtick');
      await p.clock.runFor(60000); await until(async () => (await txt(p, '#nowtick')) !== before, 3000);
      return tiles(p, '#now .nbox');
    };
    const chips = () => p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#nowpages .tag'), (e) => e.className + ':' + e.textContent));
    let t = await tiles(p, '#now .nbox');
    check('every page answers: "פעיל", green', t[0].k === 'האתר עכשיו' && t[0].v === 'פעיל' && t[0].dot === 'ok' && t[0].m === 'נבדק לפני 12 שניות · 4 מתוך 4 עמודים עונים', JSON.stringify(t[0]));
    check('server response: the home page, 0.24 s is green; the slowest page is named', t[1].v === '0.24 שנ\'' && t[1].dot === 'ok' && t[1].m === 'דף הבית · הכי איטי כרגע: סל 1.7 שנ\'', JSON.stringify(t[1]));
    /* whether the source line of the real-user tile is in another colour than the rest of its small text */
    const srcWarn = () => p.evaluate(() => { const m = document.querySelectorAll('#now .nbox')[2].querySelector('.m'), e = Array.prototype.filter.call(m.querySelectorAll('*'), (x) => /^מקור:/.test(x.textContent))[0]; return !!e && getComputedStyle(e).color !== getComputedStyle(m).color; });
    check('real users: 3.1 s is yellow; the views and the source line', t[2].v === '3.1 שנ\'' && t[2].dot === 'w' && t[2].m === '143 צפיות בשעה האחרונה · אחוזון 75מקור: האתר החי · כל 1000 המדידות האחרונות' && !(await srcWarn()), JSON.stringify(t[2]));
    check('lab: 2.5 s is green; time, score, target', t[3].v === '2.5 שנ\'' && t[3].dot === 'ok' && t[3].m === 'דף הבית בטלפון, 15:30 · ציון 63 · יעד 2.5', JSON.stringify(t[3]));
    check('a chip per page, coloured by the server-response thresholds (0.5 s, 1.5 s)', (await chips()).join() === 'tag ok:' + H + ' 0.24 שנ\',tag ok:קטגוריה 0.31 שנ\',tag w:מוצר 0.69 שנ\',tag d:סל 1.7 שנ\'', (await chips()).join());
    check('the line under the chips: time, the 60-second refresh, the open alerts', /^עודכן \d\d:\d\d:\d\d · רענון אוטומטי כל 60 שניות · 3 התראות פתוחות$/.test(await txt(p, '#nowtick')), await txt(p, '#nowtick'));

    t = await now((d) => { d.all_ok = false; d.light = true; d.age_sec = 95; d.pages[3] = { page: 'סל', url: U + '/cart/', ok: false, status: 502, ms: null }; d.latest[3].ok = false; d.pages[0].ms = 501; d.rum.p75_ms = 2500; d.speed.lcp_ms = 4000; d.alerts_open = 1; });
    check('some pages answer: "חלקי", yellow; a light round and minutes are said', t[0].v === 'חלקי' && t[0].dot === 'w' && t[0].m === 'נבדק לפני 2 דקות · בדיקה קלה · 3 מתוך 4 עונים', JSON.stringify(t[0]));
    check('thresholds: server 0.50 s yellow, real users 2.5 s green, lab 4.0 s yellow', t[1].dot === 'w' && t[1].v === '0.50 שנ\'' && t[2].dot === 'ok' && t[3].dot === 'w' && t[3].v === '4.0 שנ\'', JSON.stringify(t.slice(1)));
    check('a page that failed: a red chip with its status', (await chips())[3] === 'tag d:סל לא עונה (502)', (await chips()).join());
    check('one open alert: "התראה פתוחה אחת"', / · התראה פתוחה אחת$/.test(await txt(p, '#nowtick')), await txt(p, '#nowtick'));

    t = await now((d) => { d.all_ok = false; d.any_ok = false; d.pages.forEach((x) => { x.ok = false; x.ms = null; x.status = 0; }); d.latest.forEach((x) => { x.ok = false; }); d.rum.p75_ms = 4001; d.speed.lcp_ms = 4001; });
    check('no page answers: "נפל", red; the home page "לא עונה"', t[0].v === 'נפל' && t[0].dot === 'd' && / · אף עמוד לא עונה$/.test(t[0].m) && t[1].v === 'לא עונה' && t[1].dot === 'd', JSON.stringify(t.slice(0, 2)));
    check('thresholds: real users above 4 s red, lab above 4 s red', t[2].dot === 'd' && t[3].dot === 'd', JSON.stringify(t.slice(2)));
    t = await now((d) => { d.pages[0].ms = 1500; d.rum.p75_ms = 2501; d.speed.lcp_ms = 2501; });
    check('thresholds: server 1.5 s yellow, real users 2.501 s yellow, lab 2.501 s yellow', t[1].dot === 'w' && t[2].dot === 'w' && t[3].dot === 'w', JSON.stringify(t.slice(1)));
    t = await now((d) => { d.pages[0].ms = 1501; d.pages[3].ms = 100; });
    check('thresholds: server 1.501 s red', t[1].dot === 'd' && t[1].v === '1.5 שנ\'' && t[1].m === 'דף הבית', JSON.stringify(t[1]));
    t = await now((d) => { d.age_sec = 89; });
    const at89 = t[0].m;
    t = await now((d) => { d.age_sec = 90; });
    check('the age of the round: seconds up to 89, minutes from 90', /^נבדק לפני 89 שניות · /.test(at89) && /^נבדק לפני 2 דקות · /.test(t[0].m), at89 + ' | ' + t[0].m);
    t = await now((d) => { d.age_sec = 1; d.rum.n = 1; d.rum_src = { n: 1, hosts: [{ host: 'live', n: 1 }], cols: [], test: 1 }; });
    check('counts of one in singular Hebrew: second, view, measurement', t[0].m === 'נבדק לפני שנייה · 4 מתוך 4 עמודים עונים' && t[2].m === 'צפייה אחת בשעה האחרונה · אחוזון 75מקור: האתר החי · מדידה אחת · מתוכן מדידת בדיקה אחת', t[0].m + ' | ' + t[2].m);
    t = await now((d) => { d.rum_src = { n: 1000, hosts: [{ host: 'live', n: 964 }, { host: 'staging.shop.test', n: 36 }], cols: [], test: 12 }; });
    check('measurements from another site are listed by source, in warning colour', t[2].m === '143 צפיות בשעה האחרונה · אחוזון 75מקור: live 964 · staging.shop.test 36 (מתוך 1000 המדידות האחרונות) · מתוכן 12 מדידות בדיקה' && await srcWarn(), t[2].m);
    t = await now((d) => { Object.assign(d, { pages: [], latest: [], light: false, all_ok: false, any_ok: false, age_sec: null, rum: { n: 0, p75_ms: null }, speed: {}, alerts_open: 0, rum_src: null }); });
    check('no round in the last 15 minutes: four grey tiles, "אין נתון" and not "פעיל" or "נפל"', t.length === 4 && t.every((x) => x.dot === 'n') && t[0].v === 'אין נתון' && t[0].m === 'אין בדיקה ב-15 הדקות האחרונות' && t[1].v === '—' && t[1].m === 'אין נתון' && t[2].m === 'אין מדידות בשעה האחרונה' && t[3].m === 'אין מדידה' && (await chips()).length === 0, JSON.stringify(t));
    await s.ctx.close();
  });

  await block('B8 a long period: every point of a chart opens its own day', async () => {
    s = await fake(browser, { vp: DESK }); p = s.page;
    await p.click('#segH button[data-h="2160"]'); await settle(p);
    const hit = async (sel, i, title) => {
      const c = p.locator(sel).nth(i); await c.scrollIntoViewIfNeeded();
      const b = await c.getAttribute('data-bucket'), box = await c.boundingBox();
      await p.mouse.click(box.x + box.width / 2, box.y + box.height / 2); await sheetReady(p);
      const got = (await sheet(p)).title, want = title + ' ב-' + b.slice(8, 10) + '.' + b.slice(5, 7);
      await closeSheet(p);
      return got === want ? '' : i + ': ' + got + ' ≠ ' + want;
    };
    check('90 days are 91 daily points', (await count(p, '#availChart circle.hit')) === 91 && (await count(p, '#speedChart circle.pt')) === 273);
    let wrong = [];
    for (const i of [7, 40, 41, 76]) wrong.push(await hit('#availChart circle.hit', i, 'זמן תגובת השרת'));
    check('availability chart, 90 days: a click on the middle of a point opens that day, not its neighbour', wrong.every((x) => !x), wrong.filter(Boolean).join(' | '));
    wrong = [];
    for (const i of [7, 40, 41, 76]) wrong.push(await hit('#speedChart circle.pt', i, 'מהירות: ' + s.F.HOME));
    check('speed chart, 90 days: a click on the middle of a point opens that day, not its neighbour', wrong.every((x) => !x), wrong.filter(Boolean).join(' | '));
    check('the page is at most 900 px wide on a desktop', (await p.evaluate(() => document.querySelector('.wrap').getBoundingClientRect().width)) <= 900);
    await p.fill('#dFrom', '2025-10-10'); await p.fill('#dTo', '2026-11-13'); await p.click('#dGo'); await settle(p);
    check('a 400-day range is 400 daily points', (await count(p, '#availChart circle.hit')) === 400 && (await count(p, '#speedChart circle.pt')) === 1200, (await count(p, '#availChart circle.hit')) + ' / ' + await count(p, '#speedChart circle.pt'));
    wrong = [];
    for (const i of [3, 200, 201, 397]) wrong.push(await hit('#availChart circle.hit', i, 'זמן תגובת השרת'));
    for (const i of [3, 200, 201, 397]) wrong.push(await hit('#speedChart circle.pt', i, 'מהירות: ' + s.F.HOME));
    check('both charts, 400 days: a click on the middle of a point still opens that day', wrong.every((x) => !x), wrong.filter(Boolean).join(' | '));
    await s.ctx.close();
  });

  await block('B9 print (ייצא PDF)', async () => {
    s = await fake(browser, { dark: true }); p = s.page;
    await p.evaluate(() => { window.__printed = 0; window.print = () => { window.__printed++; }; });
    await p.click('#pdfbtn');
    check('"ייצא PDF" calls the browser\'s print', (await p.evaluate(() => window.__printed)) === 1);
    check('on the screen: 60 product rows, the note, a folded bar and folded cards', await shown(p, '#issuesTbl tbody tr') === 60 && await visible(p, '#issuesTbl p.scronly') && !(await visible(p, '#alertbar .alist')) && !(await visible(p, '#alertsList')));
    await p.emulateMedia({ media: 'print', colorScheme: 'dark' });
    const gone = [];
    for (const sel of ['.shbar', '#ctlCard', '#outLink', '#alertbar .ax', '#alertbar .acb', '#alertbar .abulk', '.foldchev', 'p.explain', '#issuesTbl p.scronly']) if (await visible(p, sel)) gone.push(sel);
    check('print hides the controls: top bar, period card, "יציאה", ✕, checkboxes, bulk row, chevrons', gone.length === 0, gone.join(' '));
    check('print unfolds everything: all alerts of the bar, the alerts card, the message log', await shown(p, '#alertbar .arow') === 3 && await visible(p, '#alertsList') && await visible(p, '#msgList') && (await css(p, '#alertbar .alist', 'maxHeight')) === 'none');
    check('print shows every table row: all 70 products', await shown(p, '#issuesTbl tbody tr') === 70, String(await shown(p, '#issuesTbl tbody tr')));
    const size = await p.evaluate(() => { const out = []; const walk = (rules) => Array.prototype.forEach.call(rules, (r) => { if (r.type === 6) out.push(r.style.getPropertyValue('size')); else if (r.cssRules) walk(r.cssRules); }); Array.prototype.forEach.call(document.styleSheets, (x) => walk(x.cssRules)); return out.join(' | '); });
    check('print on A4 landscape', /^a4 landscape$/i.test(size.trim()), size);
    check('print from a device in dark mode: white page, dark text, the light status colours', (await css(p, 'body', 'backgroundColor')) === 'rgb(255, 255, 255)' && (await css(p, '#verdictCard', 'backgroundColor')) === 'rgb(255, 255, 255)' && (await css(p, '#verdict .vbox', 'backgroundColor')) === 'rgb(255, 255, 255)' && rgbSum(await css(p, 'h1', 'color')) < 150 && (await css(p, '#alertbar', 'color')) === 'rgb(163, 39, 31)' && (await css(p, '#healthTbl .tag.ok', 'color')) === 'rgb(11, 110, 79)' && (await css(p, '#healthTbl .tag.w', 'color')) === 'rgb(143, 95, 8)', (await css(p, '#alertbar', 'color')) + ' / ' + (await css(p, '#healthTbl .tag.ok', 'color')));
    await s.ctx.close();
  });

  await block('B10 roles, menu, configuration', async () => {
    const NAV = [['g', 'האתר'], ['a', CFG.here, 'בריאות האתר'], ['a', '/another', 'מסך אחר']], LINKS = [{ href: '/another', label: 'מסך אחר', title: 'כפתור נוסף' }];
    s = await fake(browser, { cfg: { nav: NAV, links: LINKS } }); p = s.page;
    check('owner with other screens: the menu button shows', await visible(p, '#shham') && (await count(p, '#xlinks a')) === 1);
    await p.click('#shham');
    check('…and opens the menu: group title, entries, this screen marked', await visible(p, '#shov') && (await count(p, '#shlist a')) === 2 && (await txt(p, '#shlist .shg')) === 'האתר' && (await txt(p, '#shlist a.shcur')) === 'בריאות האתר' && (await p.getAttribute('#shlist a:not(.shcur)', 'href')) === '/another');
    await p.keyboard.press('Escape');
    check('…Escape closes it', !(await visible(p, '#shov')));
    check('owner: the message log is asked for', await until(() => s.F.n('/messages') === 1, 3000) && await visible(p, '#msgCard'));
    await s.ctx.close();

    s = await fake(browser); p = s.page;                       // nav: []
    check('no other screens (nav empty): no menu button', !(await visible(p, '#shham')) && (await count(p, '#xlinks a')) === 0);
    check('…and the top bar fits a phone: the name is whole, the buttons are one line high', await p.evaluate(() => { const v = document.querySelector('.shnow .v'); return v.scrollWidth <= v.clientWidth && document.getElementById('pdfbtn').offsetHeight <= 40; }));
    await p.click('#explbtn');
    check('downAfter 1 (the default): the explanation says one failed check opens an alert', (await txt(p, '#alertsCard [data-txt="downRule"]')) === 'ברגע שבדיקת זמינות אחת נכשלת' && /^התראה נפתחת ברגע שבדיקת זמינות אחת נכשלת, /.test(await txt(p, '#alertsCard p.explain')));
    await s.ctx.close();

    s = await fake(browser, { cfg: { downAfter: 2, hide: ['issuesCard', 'slowCard', 'certCard'] } }); p = s.page;
    await p.click('#explbtn');
    check('downAfter 2: the explanation says two failed checks in a row', (await txt(p, '#alertsCard [data-txt="downRule"]')) === 'כששתי בדיקות זמינות נכשלות ברצף', await txt(p, '#alertsCard [data-txt="downRule"]'));
    await p.click('#alertbar .ahead'); await p.click('#alertbar .arow[data-id="41"] .at'); await sheetReady(p);
    check('downAfter 2: the alert sheet states the two-in-a-row rule, not "כל כשל בודד מתריע"', /בדיקת זמינות נכשלה פעמיים ברצף\. הכלל: התראה נשלחת רק אחרי שתי בדיקות רצופות שנכשלו\./.test((await sheet(p)).body) && !/כל כשל בודד מתריע/.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    check('SH_CONFIG.hide hides the named cards, and only them', !(await visible(p, '#issuesCard')) && !(await visible(p, '#slowCard')) && !(await visible(p, '#certCard')) && await visible(p, '#coreCard') && await visible(p, '#healthCard'));
    await s.ctx.close();

    s = await fake(browser, { role: { readonly: true }, cfg: { nav: NAV, links: LINKS } }); p = s.page;
    await p.click('#alertbar .ahead');
    check('read-only: the bar lists the alerts, without ✕, checkboxes or the bulk row', await shown(p, '#alertbar .arow') === 3 && !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#alertbar .acb')) && !(await visible(p, '#alertbar .abulk')));
    check('read-only: no message-log card, and the log is never asked for', !(await visible(p, '#msgCard')) && s.F.n('/messages') === 0);
    check('read-only: no menu button and no extra links, also when nav is not empty', !(await visible(p, '#shham')) && (await count(p, '#xlinks a')) === 0);
    check('read-only: "יציאה" stays', await visible(p, '#outLink'));
    await p.click('#alertbar .arow[data-id="41"] .at'); await sheetReady(p);
    check('read-only: an alert still opens', (await sheet(p)).title === 'האתר לא עונה: סל');
    await s.ctx.close();

    s = await fake(browser, { role: { readonly: true, noAlerts: true } }); p = s.page;
    check('no-alerts role: no bar, no alerts card, no "התראות פתוחות" tile', !(await visible(p, '#alertbar')) && !(await visible(p, '#alertsCard')) && !(await visible(p, '#verdict .vbox[data-drill="alerts"]')) && await shown(p, '#verdict .vbox') === 3);
    await s.ctx.close();

    s = await fake(browser, { role: { share: true }, cfg: { shareKey: 'tok-1', nav: NAV } }); p = s.page;
    await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p); await closeSheet(p);
    check('share link: read-only, and no "יציאה"', !(await visible(p, '#outLink')) && !(await visible(p, '#msgCard')) && !(await visible(p, '#shham')) && !(await visible(p, '#alertbar .ax')));
    const noKey = s.F.log.filter((e) => e.q.k !== 'tok-1').map((e) => e.path);
    check('share link: every data call carries the token as k=', s.F.n('/site') >= 1 && s.F.n('/site/now') >= 1 && s.F.n('/site/drill') === 1 && noKey.length === 0 && s.F.n('/messages') === 0, 'without k: ' + noKey.join(' '));
    s.F.over['/site'] = () => ({ status: 401, body: { error: 'auth' } });
    await p.click('#refbtn'); await settle(p);
    check('share link with a token that is no longer valid (401): a message, and the page stays', /הקישור אינו תקין או שפג תוקפו\./.test(await txt(p, '#sub')) && new URL(p.url()).pathname !== CFG.loginPath, await txt(p, '#sub'));
    await s.ctx.close();

    s = await fake(browser); p = s.page;
    s.F.over['/site'] = () => ({ status: 401, body: { error: 'auth' } });
    await p.click('#refbtn');
    check('signed out (401): the screen goes to the login page', await until(() => new URL(p.url()).pathname === CFG.loginPath, 5000), p.url());
    await s.ctx.close();
  });

  await block('B11 SH_CONFIG', async () => {
    s = await fake(browser, { cfg: { siteLabel: 'shop.test', brand: 'DEMO-B', homePage: 'ראשי', probeCount: 1, coreCount: 1, api: '/data', loginPath: '/signin', logoutPath: '/bye',
      pathLabels: [['/product/', 'פריט: ']], bucketNote: 'הערה על עמוד הסל', liveHosts: ['www.shop.test'] } }); p = s.page;
    check('api: every data call goes to that base', await until(() => s.F.n('/site') === 1 && s.F.n('/site/now') === 1 && s.F.n('/messages') === 1, 3000), s.F.log.map((e) => e.path).join(' '));
    check('siteLabel and brand: tab title, subtitle, the small text at the top', (await p.title()) === 'בריאות האתר — shop.test' && /^shop\.test · /.test(await txt(p, '#sub')) && (await txt(p, '#brandTxt')) === 'DEMO-B', await p.title());
    check('logoutPath: the address of "יציאה"', (await p.getAttribute('#outLink', 'href')) === '/bye');
    const t = await tiles(p, '#now .nbox');
    check('homePage: the page whose name it is feeds "תגובת שרת עכשיו"', t[1].v === '0.24 שנ\'' && (await sheetOn(p)) === false, JSON.stringify(t[1]));
    check('liveHosts: a source that is not listed is shown as another site', /מקור: live 1000 \(מתוך 1000 המדידות האחרונות\)/.test(t[2].m), t[2].m);
    check('pathLabels: an address becomes a readable name', /^פריט: heavy 0$/.test(await txt(p, '#slowTbl tbody tr td')), await txt(p, '#slowTbl tbody tr td'));
    check('probeCount 1: the explanations say "עמוד אחד"', (await texts(p, '[data-txt="pages"]')).join() === 'עמוד אחד,עמוד אחד' && (await txt(p, '[data-txt="probed"]')) === 'נבדק עמוד אחד');
    await p.click('#verdict .vbox[data-drill="outages"]');
    check('probeCount 1: the outage sheet speaks of one page', /נפילה = 3 דקות רצופות שבהן העמוד לא ענה\./.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    await p.click('#healthTbl li:nth-child(1)');
    check('probeCount 1: the availability flow speaks of one page', /כל דקה הבודק פונה לעמוד אחד באתר ורושם אם ענה ותוך כמה זמן\./.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    await p.click('#healthTbl li:nth-child(2)');
    check('coreCount 1: the speed flow speaks of one page', /גוגל מודדת עבורנו את העמוד העיקרי בטלפון/.test((await sheet(p)).body), (await sheet(p)).body);
    await closeSheet(p);
    await p.locator('#availChart circle.hit').nth(5).click(); await sheetReady(p);
    check('bucketNote: shown under the response-time sheet', /הערה על עמוד הסל$/.test((await sheet(p)).body));
    await closeSheet(p);
    s.F.over['/site'] = () => ({ status: 401, body: { error: 'auth' } });
    await p.click('#refbtn');
    check('loginPath: where a signed-out viewer is sent', await until(() => new URL(p.url()).pathname === '/signin', 5000), p.url());
    await s.ctx.close();
    s = await fake(browser, { cfg: { probeCount: 7, coreCount: 3 } }); p = s.page;
    check('probeCount 7: the explanations say "7 עמודים"', (await texts(p, '[data-txt="pages"]')).join() === '7 עמודים,7 עמודים' && (await txt(p, '[data-txt="probed"]')) === 'נבדקים 7 עמודים');
    await p.click('#healthTbl li:nth-child(1)');
    check('probeCount 7: the availability flow says so', /כל דקה הבודק פונה ל-7 עמודים באתר ורושם אם ענו ותוך כמה זמן\./.test((await sheet(p)).body), (await sheet(p)).body);
    await s.ctx.close();
  });

  await block('B12 texts with markup in them', async () => {
    s = await fake(browser, { hostile: true });
    await hostileWalk(s, 'owner');
    await s.ctx.close();
    s = await fake(browser, { hostile: true, role: { share: true }, cfg: { shareKey: 'tok-1' } });
    await hostileWalk(s, 'share link');
    await s.ctx.close();
  });

  await block('B13 the runs sheet: what slows the page, failed runs, the median in words', async () => {
    let rows = [];
    s = await fake(browser, { over: { '/site/drill': (q) => (q.what === 'runs' ? { body: { rows } } : null) } }); p = s.page;
    /* opens the runs sheet of the first core page with these rows, reads it and closes it */
    const runs = async (r) => {
      rows = r;
      await p.click('#coreTbl tbody tr:nth-child(1)'); await sheetReady(p);
      const x = await p.evaluate(() => {
        const on = document.getElementById('dov').classList.contains('on'), t = document.querySelector('#dbody tbody tr td:nth-child(2) .tag');
        return { body: on ? document.getElementById('dbody').textContent : '', why: on ? Array.prototype.map.call(document.querySelectorAll('#dbody ul.list li'), (e) => e.textContent) : [], tag: on && t ? t.className + ':' + t.textContent : '' };
      });
      await closeSheet(p);
      return x;
    };
    const ok = (lcp, opps) => ({ ok: true, err: null, at_il: '12.11 10:15', lcp_ms: lcp, score: 64, ttfb_ms: 410, bytes: 3400000, cls: 0.03, crux_category: null, crux_lcp_ms: null, opps: opps || [] });
    const o = (id, ms) => ({ id, title: 'title of ' + id, ms });
    /* eight reasons. By the average saving: A 1.5, B 1.2, C 1.1, D 0.9, E 0.8, F 0.73, G 0.6, H 0.5 s.
       By total, F (2.2 s) and H (2.0 s) come second and third; by the largest single value F is first. */
    const [A, B, C, D, E, F, G, H] = ['render-blocking-resources', 'unused-javascript', 'modern-image-formats', 'offscreen-images', 'server-response-time', 'uses-optimized-images', 'uses-text-compression', 'redirects'];
    let x = await runs([ok(2400, [o(A, 1500), o(B, 1400), o(C, 1100), o(D, 900), o(E, 800), o(F, 2000), o(G, 600), o(H, 500)]), ok(2500, [o(B, 1000), o(E, 800), o(F, 100), o(H, 500)]), ok(2600, [o(F, 100), o(H, 500)]), ok(2700, [o(H, 500)])]);
    const OPPS = await p.evaluate(() => (typeof OPP === 'object' && OPP) || {});      // the page's own translations (§6.8 lets a site edit them)
    const want = [[A, '1.5'], [B, '1.2'], [C, '1.1'], [D, '0.9'], [E, '0.8'], [F, '0.7']].map(([id, v]) => v + ' ש\' ' + (OPPS[id] || 'title of ' + id));
    check('runs sheet with 8 reasons: exactly the top 6 by average saving, highest first (not by total, peak or count)', JSON.stringify(x.why) === JSON.stringify(want), x.why.join(' | '));

    const bad = (err) => ({ ok: false, err, at_il: '12.11 10:00' });
    x = await runs([bad('NO_FCP'), bad('NO_LCP'), bad('TIMEOUT')]);
    check('only failed runs: "אין מדידות תקינות (3 ניסיונות נכשלו: <reason of the newest>)"', x.body === 'אין מדידות תקינות (3 ניסיונות נכשלו: NO_FCP).', x.body);
    x = await runs([bad('ERRORED_DOCUMENT_REQUEST')]);
    check('one failed run: "ניסיון אחד נכשל" with its reason', x.body === 'אין מדידות תקינות (ניסיון אחד נכשל: ERRORED_DOCUMENT_REQUEST).', x.body);
    x = await runs([]);
    check('no run at all: "אין מדידות תקינות."', x.body === 'אין מדידות תקינות.', x.body);

    const wrong = [];
    for (const [ms, word, tag] of [[1999, 'מהיר מצוין', 'tag ok:מצוין'], [2000, 'מהיר מצוין', 'tag ok:מצוין'], [2001, 'מהיר', 'tag ok:מהיר'], [2500, 'מהיר', 'tag ok:מהיר'],
      [2501, 'בינוני', 'tag w:בינוני'], [4000, 'בינוני', 'tag w:בינוני'], [4001, 'איטי', 'tag d:איטי']]) {
      x = await runs([ok(ms)]);
      const m = x.body.match(/עד התוכן העיקרי: (.+?)\. הכי איטית/), got = (m ? m[1] : '?') + ' / ' + x.tag;
      if (got !== word + ' / ' + tag) wrong.push(ms + ' ms: ' + got);
    }
    check('the median in words: "מהיר מצוין" up to 2000 ms, "מהיר" up to 2500, "בינוני" up to 4000, "איטי" above (1999 / 2000 / 2001 / 2500 / 2501 / 4000 / 4001); the run\'s tag agrees', wrong.length === 0, wrong.join(' | '));
    check('no JavaScript errors (runs sheet)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
  });

  await block('B14 a site that does not measure real users (SH_CONFIG.hide: nowRum)', async () => {
    s = await fake(browser, { clock: '2026-11-12T16:00:00+02:00', cfg: { hide: ['nowRum'] } }); p = s.page;
    let t = await tiles(p, '#now .nbox');
    check('hide nowRum: "עכשיו" has three tiles, without "מהירות אצל לקוחות"; the others as always', t.length === 3 && t.map((x) => x.k).join('|') === 'האתר עכשיו|תגובת שרת עכשיו|מעבדה, מדידה אחרונה'
      && t[0].v === 'פעיל' && t[1].v === '0.24 שנ\'' && t[2].v === '2.5 שנ\'' && t[2].m === 'דף הבית בטלפון, 15:30 · ציון 63 · יעד 2.5', JSON.stringify(t));
    await p.click('#explbtn');
    const ex = await p.evaluate(() => document.querySelector('#nowcard p.explain').innerText);
    check('…and the explanation of "עכשיו" says nothing about real users; the rest of it stays', !/מהירות אצל לקוחות/.test(ex) && /תגובת שרת/.test(ex) && /מתרענן לבד כל 60 שניות/.test(ex), ex);
    check('…every card is still there', await visible(p, '#verdictCard') && await visible(p, '#coreCard') && await visible(p, '#slowCard') && await visible(p, '#issuesCard') && await visible(p, '#certCard') && await visible(p, '#healthCard'));
    s.F.over['/site/now'] = () => ({ body: Object.assign(s.F.now(), { pages: [], latest: [], all_ok: false, any_ok: false, age_sec: null, rum: { n: 0, p75_ms: null }, speed: {}, rum_src: null }) });
    const tick = await txt(p, '#nowtick');
    await p.clock.runFor(60000); await until(async () => (await txt(p, '#nowtick')) !== tick, 3000);
    t = await tiles(p, '#now .nbox');
    check('hide nowRum, no round yet: three grey tiles, none of them about real users', t.length === 3 && t.every((x) => x.dot === 'n') && !t.some((x) => /לקוחות/.test(x.k) || /אין מדידות בשעה האחרונה/.test(x.m)), JSON.stringify(t));
    check('no JavaScript errors (hide nowRum)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
  });

  /* ================= C. scenarios, roles and sessions of the mock ================= */
  if (runC) {
    await block('C1 incident, owner', async () => {
      await scenario('incident');
      s = await open(browser, PAGE_PATH, PHONE); p = s.page;
      const d = s.site, openAlerts = d.alerts_open.filter((a) => !a.acked).length;
      check('mock: the alert bar shows the number of open alerts', new RegExp('⚠ ' + openAlerts + ' התראות פעילות').test(await txt(p, '#alertbar .acount')), await txt(p, '#alertbar .acount'));
      const t = await tiles(p, '#verdict .vbox');
      check('mock: the four bottom-line tiles carry numbers', /^(מצוין|מהיר|בינוני|איטי)$/.test(t[0].v) && /שניות עד התוכן · \d+ מדידות/.test(t[0].m) && /^\d\d\.\d\d%$/.test(t[1].v) && t[2].v === '1' && t[2].m === 'סה"כ 7 דקות' && t[3].v === '3' && t[3].m === d.alerts_recent.length + ' בתקופה', JSON.stringify(t));
      check('mock: availability card has rows, the outage, bars and the line', (await count(p, '#availTbl tbody tr')) === 4 && (await count(p, '#outages li')) === 1 && (await count(p, '#availChart rect.bar')) >= 1 && (await count(p, '#availChart circle.hit')) >= 24);
      check('mock: speed chart has a line per core page', (await count(p, '#legend button')) === 5 && (await count(p, '#speedChart path.ln')) === 5 && (await count(p, '#speedChart circle.pt')) >= 120);
      check('mock: five core pages, ten heavy pages, the coverage line', (await count(p, '#coreTbl tbody tr')) === 5 && (await count(p, '#slowTbl tbody tr')) === 10 && /^נדגמו \d+ מתוך 412 עמודי האתר בתקופה\.$/.test(await txt(p, '#coverage')), await txt(p, '#coverage'));
      const iss = await texts(p, '#issuesTbl tbody .tag');
      check('mock: broken products in the order of the contract ("לא במלאי" last)', iss.join() === 'אי אפשר להוסיף לסל,בלי מחיר,בלי תמונה,לא במלאי,לא במלאי', iss.join());
      check('mock: certificate with 23 days: "לשים לב"', (await tiles(p, '#certBox .vbox'))[0].v === '23 ימים' && (await txt(p, '#certBox .tag')) === 'לשים לב');
      check('mock: alerts card and the seven measurement flows', (await count(p, '#alertsList li')) === d.alerts_recent.length && (await count(p, '#healthTbl li')) === 7 && (await count(p, '#healthTbl .tag.d')) === 1 && (await count(p, '#healthTbl .tag.w')) === 2);
      check('mock: "עכשיו": the cart is down, so the site is "חלקי"', (await tiles(p, '#now .nbox'))[0].v === 'חלקי' && (await count(p, '#nowpages .tag.d')) === 1);
      await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
      check('mock: the failures sheet has rows (page= and bucket= empty)', (await sheet(p)).rows >= 1, String((await sheet(p)).rows));
      await closeSheet(p);
      await p.click('#availTbl tbody tr:nth-child(4)'); await sheetReady(p);
      check('mock: the failures of one page have rows', (await sheet(p)).rows >= 1 && (await sheet(p)).title === 'הכשלים של עמוד סל');
      await closeSheet(p);
      await p.click('#coreTbl tbody tr:nth-child(5)'); await sheetReady(p);
      check('mock: the runs of a core page have rows and "מה מאט את העמוד"', (await sheet(p)).rows >= 1 && /מה מאט את העמוד/.test((await sheet(p)).body) && (await sheet(p)).title === 'מהירות: אודות', (await sheet(p)).title);
      await closeSheet(p);
      await p.click('#availChart rect.bar'); await sheetReady(p);
      check('mock: a red bar opens the failures of its hour', /^הכשלים ב-\d\d\.\d\d בשעה \d\d:00$/.test((await sheet(p)).title), (await sheet(p)).title);
      await closeSheet(p);
      await p.click('#alertbar .ahead');
      check('mock: each alert with a URL in its body has an "open the page" link', await count(p, '#alertbar .alink') >= 1);
      const posts = [];
      p.on('request', (r) => { if (r.method() === 'POST') posts.push(new URL(r.url()).pathname + ' ' + r.postData()); });
      await p.click('#alertbar .arow .ax');
      check('mock: ✕ removes the alert at once, without reloading the screen', await count(p, '#alertbar .arow') === openAlerts - 1 && !(await p.evaluate(() => document.body.classList.contains('loading'))));
      await until(() => posts.length === 1, 2000);
      check('mock: ✕ posts {"ids":[id]} to /api/alerts/ack', posts.length === 1 && /^\/api\/alerts\/ack \{"ids":\[\d+\]\}$/.test(posts[0]), posts.join(','));
      await p.click('#abAll'); await p.click('#abDel');
      check('mock: "לסמן הכול" + "מחק מסומנות" clears the bar', !(await visible(p, '#alertbar')));
      await until(() => posts.length === 2, 2000);
      await p.click('#refbtn'); await settle(p);
      check('mock: acknowledged alerts stay hidden after a reload, and still count as open', !(await visible(p, '#alertbar')) && (await tiles(p, '#verdict .vbox'))[3].v === String(openAlerts));
      await p.click('#msgCard .foldhead');
      check('mock: the message log lists what was sent to the phone', await count(p, '#msgList li') >= 3 && /חזר לתקין: בית/.test(await txt(p, '#msgList')) && /נמשך 7 דקות/.test(await txt(p, '#msgList')));
      check('no JavaScript errors (owner, incident)', s.errors.length === 0, s.errors.join(' | '));
      await s.ctx.close();
    });

    await block('C2 roles and sessions', async () => {
      await scenario('incident');
      s = await open(browser, PAGE_PATH + '?role=vendor', PHONE); p = s.page;
      const asked = []; p.on('request', (r) => asked.push(r.method() + ' ' + new URL(r.url()).pathname));
      await p.click('#alertbar .ahead', { quiet: true }).catch(() => {});
      check('vendor: no delete controls on alerts, no menu button', !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#alertbar .abulk')) && !(await visible(p, '#shham')));
      check('vendor: no message log', !(await visible(p, '#msgCard')));
      check('vendor: sees only site alerts (no internal kinds)', s.site.alerts_open.length === 2 && s.site.alerts_open.every((a) => ['down', 'slow', 'silent', 'cert'].indexOf(a.kind) >= 0));
      await p.click('#refbtn'); await settle(p);
      check('vendor: the screen never asks for the message log', asked.some((a) => a === 'GET /api/site') && !asked.some((a) => /messages|ack/.test(a)), asked.join(' '));
      check('vendor: server refuses a delete', await p.evaluate(() => fetch('/api/alerts/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"ids":[41]}' }).then((r) => r.status)) === 403);
      check('vendor: server refuses the message log', await p.evaluate(() => fetch('/api/messages?h=24').then((r) => r.status)) === 403);
      check('no JavaScript errors (vendor)', s.errors.length === 0, s.errors.join(' | '));
      await s.ctx.close();

      s = await open(browser, PAGE_PATH + '?role=noalerts', PHONE); p = s.page;
      check('no-alerts role: no bar, no alerts card, no open-alerts tile', !(await visible(p, '#alertbar')) && !(await visible(p, '#alertsCard')) && !(await visible(p, '#verdict .vbox[data-drill="alerts"]')));
      check('no-alerts role: the server sends no alerts', s.site.alerts_open.length === 0 && s.site.alerts_recent.length === 0);
      await s.ctx.close();

      s = await open(browser, '/status?k=demo-share-token', PHONE); p = s.page;
      check('share link: the screen loads with data (every data call carried the token)', s.status === 200 && /^\d\d\.\d\d%$/.test((await tiles(p, '#verdict .vbox'))[1].v) && (await count(p, '#now .nbox')) === 4, JSON.stringify((await tiles(p, '#verdict .vbox'))[1]));
      check('share link: no logout link, no delete controls, no message log, no menu button', !(await visible(p, '#outLink')) && !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#msgCard')) && !(await visible(p, '#shham')));
      await p.click('#verdict .vbox[data-drill="fails"]'); await sheetReady(p);
      check('share link: a sheet loads too', (await sheet(p)).rows >= 1, (await sheet(p)).body.slice(0, 80));
      check('no JavaScript errors (share link)', s.errors.length === 0, s.errors.join(' | '));
      await s.ctx.close();
      s = await open(browser, '/status?k=wrong', PHONE, { noWait: true });
      check('share link with a wrong token is refused (403)', s.status === 403);
      await s.ctx.close();
      check('data call with a wrong token is refused (401)', (await fetch(BASE + '/api/site?k=wrong')).status === 401);
      check('data call without a session and without a token is refused (401)', (await fetch(BASE + '/api/site?h=24')).status === 401 && (await fetch(BASE + '/api/site/now')).status === 401 && (await fetch(BASE + '/api/site/drill?what=fails&h=24')).status === 401);
      const one = async (path) => { const r = await fetch(BASE + path, { headers: { Cookie: 'mock_role=owner' } }); return { status: r.status, cache: r.headers.get('cache-control'), body: await r.json().catch(() => null) }; };
      let r = await one('/api/site/drill?what=bucket&h=24');
      check('mock: a drill-down with a missing or malformed parameter answers {"rows": []}', r.status === 200 && r.body.rows.length === 0 && (await one('/api/site/drill?what=bucket&bucket=garbage')).body.rows.length === 0 && (await one('/api/site/drill?what=runs&url=')).body.rows.length === 0 && (await one('/api/site/drill?what=alert&id=x')).body.rows.length === 0);
      check('mock: an unknown what answers 400; data answers are no-store', (await one('/api/site/drill?what=nope')).status === 400 && r.cache === 'no-store');
      const rowsOf = async (path) => { const x = await one(path); return x.body && Array.isArray(x.body.rows) ? x.body.rows.length : -1; };
      const hour = encodeURIComponent('2026-11-12 03:00'), badHour = encodeURIComponent('2026-11-12 24:00');
      const got = [await rowsOf('/api/site/drill?what=fails&page=&bucket=' + hour + '&h=24'), await rowsOf('/api/site/drill?what=fails&page=&bucket=2026-13-45&h=24'), await rowsOf('/api/site/drill?what=fails&page=&bucket=' + badHour + '&h=24'),
        await rowsOf('/api/site/drill?what=runs&url=' + encodeURIComponent('https://example.co.il/') + '&bucket=2026-02-30&h=24'), await rowsOf('/api/site/drill?what=bucket&bucket=2026-02-30'),
        await rowsOf('/api/site/drill?what=alert&id=41&bucket=garbage'), await rowsOf('/api/site/drill?what=alert&id=0000000000000000041')];
      check('mock, as the reference server: a bucket in the right shape that is no real day or hour (2026-13-45, 24:00, 30.2) answers {"rows": []}; an alert ignores bucket; an id of 19 digits is malformed', got[0] > 0 && got.slice(1, 5).every((x) => x === 0) && got[5] === 1 && got[6] === 0, got.join(','));
      const home = 'https://example.co.il/', ctl = [await rowsOf('/api/site/drill?what=runs&url=' + encodeURIComponent(home) + '&bucket=&h=24'),
        await rowsOf('/api/site/drill?what=runs&url=' + encodeURIComponent(home + '\t') + '&bucket=&h=24'), await rowsOf('/api/site/drill?what=runs&url=' + encodeURIComponent(home + '\x7f') + '&h=24'),
        await rowsOf('/api/site/drill?what=fails&page=' + encodeURIComponent('סל') + '&bucket=&h=24'), await rowsOf('/api/site/drill?what=fails&page=' + encodeURIComponent('סל\n') + '&bucket=&h=24')];
      check('mock, as the reference server: a page or url with a control character (U+0000 to U+001F, U+007F) answers {"rows": []}', ctl[0] > 0 && ctl[1] === 0 && ctl[2] === 0 && ctl[3] > 0 && ctl[4] === 0, ctl.join(','));
    });

    await block('C7 the server hides what the site does not measure', async () => {
      await scenario('incident');
      s = await open(browser, PAGE_PATH + '?hide=nowRum,certCard', PHONE); p = s.page;
      const t = await tiles(p, '#now .nbox');
      check('mock ?hide=nowRum,certCard: "עכשיו" without the real-user tile, no certificate card, the other cards stay', t.length === 3 && !t.some((x) => /לקוחות/.test(x.k)) && !(await visible(p, '#certCard')) && await visible(p, '#slowCard') && await visible(p, '#healthCard'), JSON.stringify(t.map((x) => x.k)));
      await s.ctx.close();
    });

    await block('C3 fresh install', async () => {
      await scenario('empty');
      s = await open(browser, PAGE_PATH, PHONE); p = s.page;
      const body = await txt(p, '.wrap');
      check('fresh install: every card shows its empty state, nothing breaks',
        /אין בדיקות זמינות בתקופה/.test(body) && /מדידת המהירות עדיין לא התחילה/.test(body) && /הסבב על כל האתר עדיין לא התחיל/.test(body)
        && /עדיין לא נבדק/.test(body) && /אין התראות בתקופה/.test(body) && /אין בדיקה ב-15 הדקות האחרונות/.test(body) && !body.includes(NA) && s.errors.length === 0, s.errors.join(' | '));
      check('fresh install: seven flows wait for their first run', (await count(p, '#healthTbl .tag.n')) === 7);
      if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-empty.png', fullPage: true });
      await s.ctx.close();
    });

    await block('C4 data source down', async () => {
      await scenario('error');
      s = await open(browser, PAGE_PATH, PHONE); p = s.page;
      const t = await tiles(p, '#verdict .vbox');
      check('data source down: the screen still renders, no JavaScript errors', t.length === 4 && s.errors.length === 0, s.errors.join(' | '));
      check('data source down: no tile shows a number, no card reads as good news', t.every((x) => x.v === '—' && x.m === NA) && !/זה טוב|האתר לא נפל|עדיין לא נבדק/.test(await txt(p, '.wrap')), JSON.stringify(t));
      check('data source down: "now" says it could not load', /לא הצלחתי לטעון את "עכשיו"/.test(await txt(p, '#nowtick')) && (await tiles(p, '#now .nbox'))[0].m === NA, await txt(p, '#nowtick'));
      await p.click('#msgCard .foldhead');
      check('data source down: the message log says it could not load', /לא הצלחתי לטעון את ההודעות/.test(await txt(p, '#msgList')), await txt(p, '#msgList'));
      await s.ctx.close();
    });

    await block('C5 all good', async () => {
      await scenario('ok');
      s = await open(browser, PAGE_PATH, PHONE); p = s.page;
      check('all good: no alert bar, site "פעיל"', !(await visible(p, '#alertbar')) && /פעיל/.test(await txt(p, '#now .nbox .v')));
      if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-ok.png', fullPage: true });
      await s.ctx.close();
    });

    await block('C6 hostile texts', async () => {
      await scenario('hostile');
      for (const [who, path] of [['owner', PAGE_PATH], ['vendor', PAGE_PATH + '?role=vendor'], ['share link', '/status?k=demo-share-token']]) {
        s = await open(browser, path, PHONE);
        await hostileWalk(s, 'mock, ' + who);
        await s.ctx.close();
      }
    });
    await scenario('incident');
  }

  await browser.close();
  console.log('\n' + passed + ' passed, ' + failed + ' failed' + (runC ? '' : isMock ? '  (groups A and B; --basic leaves out group C)' : '  (groups A and B; group C needs the kit\'s mock)'));
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  /* only what no group catches ends up here, such as a browser that cannot start */
  console.error('test crashed: ' + String(e && e.stack || e).split('\n').slice(0, 3).join('\n'));
  console.log('\n' + passed + ' passed, ' + failed + ' failed  (the test could not run to its end)');
  process.exit(2);
});
