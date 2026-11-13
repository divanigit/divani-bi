#!/usr/bin/env node
/* Acceptance test of the site-health screen (Playwright, headless Chromium).

     node check_screen.js                          # against the mock:  http://127.0.0.1:8787
     node check_screen.js http://127.0.0.1:8000    # against your real server (logged-in session needed, see --cookie)
     node check_screen.js <url> --cookie "name=value"   # session cookie for a real server
     node check_screen.js <url> --shots ./shots    # also save screenshots (phone + desktop)
     node check_screen.js <url> --basic            # only the checks that hold for any data

   Against the mock it also switches scenarios (incident / ok / empty / error) and roles.
   Exit code 0 = every check passed. Each line is one check: "ok" or "FAIL". */
const { chromium } = require('playwright');

const args = process.argv.slice(2);
const flag = (n) => { const i = args.indexOf(n); return i < 0 ? null : (args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : true); };
const BASE = (args[0] && !args[0].startsWith('--') ? args[0] : 'http://127.0.0.1:8787').replace(/\/$/, '');
const SHOTS = flag('--shots'), COOKIE = flag('--cookie'), BASIC = !!flag('--basic');
const PAGE_PATH = flag('--path') || '/site';

let failed = 0, passed = 0;
function check(name, cond, extra) { if (cond) { passed++; console.log('ok    ' + name); } else { failed++; console.log('FAIL  ' + name + (extra ? '  → ' + extra : '')); } }

async function open(browser, path, vp, opts = {}) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, locale: 'he-IL', colorScheme: opts.dark ? 'dark' : 'light' });
  if (COOKIE && typeof COOKIE === 'string') {
    const [n, ...v] = COOKIE.split('='); const u = new URL(BASE);
    await ctx.addCookies([{ name: n, value: v.join('='), domain: u.hostname, path: '/' }]);
  }
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text()); });
  const resp = await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  if (resp && resp.status() === 200 && !opts.noWait) {
    await page.waitForFunction(() => !document.body.classList.contains('loading') && document.querySelectorAll('#verdict .vbox').length === 4, null, { timeout: 20000 }).catch(() => {});
    await page.waitForFunction(() => document.querySelectorAll('#now .nbox').length >= 1 && !/טוען/.test(document.getElementById('now').textContent), null, { timeout: 20000 }).catch(() => {});
  }
  return { ctx, page, errors, status: resp ? resp.status() : 0 };
}
const noOverflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
const txt = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent : null; }, sel);
const count = (page, sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel);
const visible = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; }, sel);
async function scenario(name) { const r = await fetch(BASE + '/__scenario?name=' + name).catch(() => null); return !!(r && r.ok); }

(async () => {
  const browser = await chromium.launch();
  const isMock = !BASIC && await scenario('incident');
  const PHONE = { width: 390, height: 844 }, DESK = { width: 1280, height: 900 };

  /* ---------- 1. structure, on a phone ---------- */
  let s = await open(browser, PAGE_PATH, PHONE);
  let p = s.page;
  check('page loads (200)', s.status === 200, 'status ' + s.status);
  check('no horizontal scroll at 390px', await noOverflow(p));
  check('html is rtl + hebrew', await p.evaluate(() => document.documentElement.dir === 'rtl' && document.documentElement.lang === 'he'));
  check('"now" card shows 4 tiles', await count(p, '#now .nbox') === 4, String(await count(p, '#now .nbox')));
  check('bottom line shows 4 tiles', await count(p, '#verdict .vbox') === 4);
  const cards = await p.evaluate(() => Array.prototype.map.call(document.querySelectorAll('.wrap > section.card h2'), (h) => h.firstChild.textContent.trim()));
  const WANT = ['עכשיו', 'שורה תחתונה', 'זמינות', 'מהירות לאורך זמן', 'העמודים העיקריים', 'העמודים הכבדים באתר', 'מוצרים שבורים באתר', 'תעודת האבטחה (המנעול)', 'התראות', 'הודעות שנשלחו לטלפון', 'המדידה עצמה'];
  check('cards appear in the specified order', JSON.stringify(cards) === JSON.stringify(WANT), JSON.stringify(cards));
  check('subtitle shows the last check time and the period', /הבדיקה האחרונה .* · 24 השעות האחרונות/.test(await txt(p, '#sub')), await txt(p, '#sub'));
  check('alerts card and messages card start folded', await p.evaluate(() => document.getElementById('alertsList').parentElement.classList.contains('collapsed') && document.getElementById('msgList').parentElement.classList.contains('collapsed')));
  check('explanations hidden until asked', !(await visible(p, 'p.explain')));
  await p.click('#explbtn');
  check('"הסברים" shows the explanations', await visible(p, 'p.explain') && (await p.getAttribute('#explbtn', 'aria-pressed')) === 'true');
  await p.click('#explbtn');
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone.png', fullPage: true });

  /* ---------- 2. numbers match the data ---------- */
  const data = await p.evaluate(() => state.data);
  const per = (Array.isArray(data.availability) ? data.availability : []).filter((r) => r.section === 'לפי עמוד');
  const checksN = per.reduce((a, r) => a + (+r.checks || 0), 0), failN = per.reduce((a, r) => a + (+r.failed || 0), 0);
  if (checksN) {
    const up = 100 - 100 * failN / checksN, want = up.toFixed(up < 99.95 ? 2 : 1) + '%';
    check('uptime tile = 100 − failed/checks', (await txt(p, '#verdict .vbox[data-drill="fails"] .v')) === want, want + ' vs ' + await txt(p, '#verdict .vbox[data-drill="fails"] .v'));
    check('availability table: one row per probed page', await count(p, '#availTbl tbody tr') === per.length);
  } else check('no availability data → empty state text', /אין בדיקות זמינות בתקופה/.test(await txt(p, '#availTbl')));
  const core = (Array.isArray(data.speed) ? data.speed : []).filter((r) => r.section === 'ליבה' && r.strategy === 'mobile');
  check('core pages table: one row per core page (mobile)', core.length ? await count(p, '#coreTbl tbody tr') === core.length : /אין מדידות טלפון בתקופה/.test(await txt(p, '#coreTbl')));
  check('heavy pages table: at most 10 rows', await count(p, '#slowTbl tbody tr') <= 10);

  /* ---------- 3. drill-downs ---------- */
  await p.click('#verdict .vbox[data-drill="fails"]');
  await p.waitForFunction(() => document.getElementById('dov').classList.contains('on') && !/טוען…/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
  check('click on uptime opens the failures sheet', (await txt(p, '#dttl')) === 'כל הכשלים' && /הבדיקות שנכשלו/.test(await txt(p, '#dbody')), await txt(p, '#dttl'));
  check('sheet is a bottom sheet on a phone', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs(r.bottom - window.innerHeight) < 2 && r.width >= window.innerWidth - 2; }));
  await p.keyboard.press('Escape');
  check('Escape closes the sheet', !(await p.evaluate(() => document.getElementById('dov').classList.contains('on'))));
  if (core.length) {
    await p.click('#coreTbl tbody tr');
    await p.waitForFunction(() => /המדידות|אין מדידות תקינות/.test(document.getElementById('dbody').textContent), null, { timeout: 10000 }).catch(() => {});
    check('click on a core page opens its measurements', /^מהירות: /.test(await txt(p, '#dttl')), await txt(p, '#dttl'));
    await p.click('#dx');
  }
  check('no JavaScript errors (phone)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();

  /* ---------- 4. desktop + dark ---------- */
  s = await open(browser, PAGE_PATH, DESK); p = s.page;
  check('no horizontal scroll at 1280px', await noOverflow(p));
  await p.click('#verdict .vbox[data-drill="outages"]');
  check('sheet is centered on desktop', await p.evaluate(() => { const r = document.getElementById('dsheet').getBoundingClientRect(); return Math.abs((r.left + r.right) / 2 - window.innerWidth / 2) < 2 && r.width === 720; }));
  await p.click('#dx');
  await p.click('#segH button[data-h="168"]');
  await p.waitForFunction(() => state.data && state.data.hours === 168 && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"7 ימים" reloads with a 168-hour window', await p.evaluate(() => state.data.hours === 168) && /7 הימים האחרונים/.test(await txt(p, '#rangeTxt')));
  await p.click('#segS button[data-s="desktop"]');
  await p.waitForFunction(() => state.data && state.data.strategy === 'desktop' && !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
  check('"מחשב" reloads with strategy=desktop', await p.evaluate(() => state.data.strategy === 'desktop'));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/desktop.png', fullPage: true });
  check('no JavaScript errors (desktop)', s.errors.length === 0, s.errors.join(' | '));
  await s.ctx.close();
  s = await open(browser, PAGE_PATH, PHONE, { dark: true }); p = s.page;
  check('dark mode: page background is dark', await p.evaluate(() => { const m = getComputedStyle(document.body).backgroundColor.match(/\d+/g); return m && (+m[0] + +m[1] + +m[2]) < 150; }));
  if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-dark.png', fullPage: true });
  await s.ctx.close();

  /* ---------- 5. mock only: alert bar, roles, scenarios ---------- */
  if (isMock) {
    await scenario('incident');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const openAlerts = (await p.evaluate(() => state.data.alerts_open)).filter((a) => !a.acked).length;
    check('alert bar shows the number of open alerts', new RegExp('⚠ ' + openAlerts + ' התראות פעילות').test(await txt(p, '#alertbar .acount')), await txt(p, '#alertbar .acount'));
    check('alert bar starts collapsed', await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed')));
    await p.click('#alertbar .ahead');
    check('each alert with a URL in its body has an "open the page" link', await count(p, '#alertbar .alink') >= 1);
    const posts = [];
    p.on('request', (r) => { if (r.method() === 'POST') posts.push(r.url() + ' ' + r.postData()); });
    await p.click('#alertbar .arow .ax');
    check('✕ removes the alert at once, without reloading the screen', await count(p, '#alertbar .arow') === openAlerts - 1 && !(await p.evaluate(() => document.body.classList.contains('loading'))));
    check('✕ posts {"ids":[id]} to /api/alerts/ack', posts.length === 1 && /\/api\/alerts\/ack \{"ids":\[\d+\]\}/.test(posts[0]), posts.join(','));
    check('the bar stays open after a delete', !(await p.evaluate(() => document.getElementById('alertbar').classList.contains('collapsed'))));
    await p.click('#abAll'); await p.click('#abDel');
    check('"לסמן הכול" + "מחק מסומנות" clears the bar', !(await visible(p, '#alertbar')));
    await p.click('#refbtn');
    await p.waitForFunction(() => !document.body.classList.contains('loading'), null, { timeout: 20000 }).catch(() => {});
    check('acknowledged alerts stay hidden after refresh', !(await visible(p, '#alertbar')));
    check('…but still count as open in the bottom line', (await txt(p, '#verdict .vbox[data-drill="alerts"] .v')) === String(openAlerts));
    await p.click('#msgCard .foldhead');
    check('message log lists what was sent to the phone', await count(p, '#msgList li') >= 3);
    check('no JavaScript errors (owner, incident)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    await scenario('incident');
    s = await open(browser, PAGE_PATH + '?role=vendor', PHONE); p = s.page;
    await p.click('#alertbar .ahead').catch(() => {});
    check('vendor: no delete controls on alerts', !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#alertbar .abulk')));
    check('vendor: no message log', !(await visible(p, '#msgCard')));
    check('vendor: sees only site alerts (no internal kinds)', await p.evaluate(() => state.data.alerts_open.every((a) => ['down', 'slow', 'silent', 'cert'].indexOf(a.kind) >= 0)));
    check('vendor: server refuses a delete', await p.evaluate(() => fetch('/api/alerts/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"ids":[41]}' }).then((r) => r.status)) === 403);
    check('vendor: server refuses the message log', await p.evaluate(() => fetch('/api/messages?h=24').then((r) => r.status)) === 403);
    check('no JavaScript errors (vendor)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();

    s = await open(browser, PAGE_PATH + '?role=noalerts', PHONE); p = s.page;
    check('no-alerts role: no bar, no alerts card, no open-alerts tile', !(await visible(p, '#alertbar')) && !(await visible(p, '#alertsCard')) && !(await visible(p, '#verdict .vbox[data-drill="alerts"]')));
    await s.ctx.close();

    s = await open(browser, '/status?k=demo-share-token', PHONE); p = s.page;
    check('share link: screen loads with data', s.status === 200 && await count(p, '#verdict .vbox') === 4);
    check('share link: no logout link, no delete controls, no message log', !(await visible(p, '#outLink')) && !(await visible(p, '#alertbar .ax')) && !(await visible(p, '#msgCard')));
    check('no JavaScript errors (share link)', s.errors.length === 0, s.errors.join(' | '));
    await s.ctx.close();
    s = await open(browser, '/status?k=wrong', PHONE, { noWait: true });
    check('share link with a wrong token is refused (403)', s.status === 403);
    await s.ctx.close();
    const r401 = await fetch(BASE + '/api/site?k=wrong');
    check('data call with a wrong token is refused (401)', r401.status === 401);

    await scenario('empty');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    const body = await txt(p, '.wrap');
    check('fresh install: every card shows its empty state, nothing breaks',
      /אין בדיקות זמינות בתקופה/.test(body) && /מדידת המהירות עדיין לא התחילה/.test(body) && /הסבב על כל האתר עדיין לא התחיל/.test(body)
      && /עדיין לא נבדק/.test(body) && /אין התראות בתקופה/.test(body) && /אין בדיקה ב־15 הדקות האחרונות/.test(body) && s.errors.length === 0, s.errors.join(' | '));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-empty.png', fullPage: true });
    await s.ctx.close();

    await scenario('error');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('data source down: the screen still renders, no JavaScript errors', await count(p, '#verdict .vbox') === 4 && s.errors.length === 0, s.errors.join(' | '));
    check('data source down: "now" says it could not load', /לא הצלחתי לטעון את "עכשיו"/.test(await txt(p, '#nowtick')), await txt(p, '#nowtick'));
    await s.ctx.close();

    await scenario('ok');
    s = await open(browser, PAGE_PATH, PHONE); p = s.page;
    check('all good: no alert bar, site "פעיל"', !(await visible(p, '#alertbar')) && /פעיל/.test(await txt(p, '#now .nbox .v')));
    if (SHOTS) await p.screenshot({ path: SHOTS + '/phone-ok.png', fullPage: true });
    await s.ctx.close();
    await scenario('incident');
  }

  await browser.close();
  console.log('\n' + passed + ' passed, ' + failed + ' failed' + (isMock ? '' : '  (basic checks only — scenario and role checks need the mock)'));
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('test crashed: ' + e.stack); process.exit(2); });
