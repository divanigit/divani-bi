# Site Health kit: the steps only the owner can do

Part of the Site Health kit; `START-HERE.md` is the entry point. This file covers phase 8 (deploy)
and phase 9 (hand-over) of §9, and the money question of the intake. Read it completely.

**The rule behind every step (START-HERE rule 5): you never hold a production secret.** The owner
opens the accounts in their own name and types every secret into the place that needs it. You
prepare a file or the exact values, send one short message, and confirm from the outside: the
public `/health`, the screen seen through a throwaway read-only password, or what the owner tells
you they see. Nothing the owner reports back is a secret: a result line, "saved", what the phone shows.

How to use the messages:

- Send them as written, with every `<…>` filled in. **One message, one step**; wait for the answer
  before the next. Each ends with what the owner does now. They are worded to fit a man or a woman.
- **The labels of other services (menus, buttons) could not be checked from where this kit was
  written.** Before sending a message, look the current labels up if you can. If you cannot,
  keep the wording below: it says what to look for ("the place where SQL is run, usually called
  SQL Editor") and never promises an exact label. If the owner does not find something, ask them
  what they see and go from there.
- **Never quote a price.** Plans and prices change; the owner reads them on the providers' pages.
- **Files for the owner** (`install.sql`, `site-health-rum.zip`) are git-ignored: generated, and
  free of secrets. If the owner works on the computer you run on, name the folder. If you run in
  a cloud sandbox, attach the file to your message; if you cannot, commit it once
  (`git add -f <file>`) so the owner can download it, and remove it again when the step is done.

`<address>` below is the public address of the dashboard (the web service of step 3), `<host>` the
hosting provider the owner chose, `<site>` the monitored site.

---

## Step 1. What it takes, and what is paid (before the owner chooses anything)

**Who:** you send it during the intake (row 9), before any account is opened. **Prepare:** nothing.

Facts for you. The system needs: a Postgres database (default: a Supabase project), one small
web service that runs **all the time** (it probes every minute; a plan that sleeps when idle
stops the measuring), a Google key (free), the ntfy app on every phone that gets alerts, and a
small add-on on the site. The limits that matter: the database settles around 200 MB plus the
real-user rows (§7.2), and a free Supabase project holds 500 MB; the web service must be a single
always-on instance. An always-on service is normally a paid monthly plan. A free database plan may
pause a project it considers idle: read the provider's current terms. Any host that keeps one
small Python process running will do; none was tried from where this kit was written. The host
takes the code from a Git hosting account: if the repository has no remote yet, that is one more
account for the owner, and you ask before pushing (rule 12).

```text
כדי שהמסך יעבוד צריך חמישה דברים. כולם נפתחים על השם שלך ונשארים בשליטתך:

1. מקום שבו נשמרות המדידות (מסד נתונים). פותחים בשבילו חשבון.
2. שרת קטן שעובד כל הזמן. הוא בודק את האתר כל דקה ומציג את המסך. גם בשבילו פותחים חשבון.
3. מפתח של גוגל למדידת המהירות. הוא בחינם.
4. האפליקציה ntfy בכל טלפון שצריך לקבל הודעות.
5. תוסף קטן באתר, שמודד כמה מהר העמודים נטענים אצל הגולשים.

מה עולה כסף: השרת הקטן הוא בדרך כלל בתשלום חודשי, כי הוא חייב לעבוד בלי הפסקה. תוכנית חינמית ש"נרדמת" כשאין תנועה לא מתאימה: כשהשרת ישן, אף אחד לא בודק את האתר. מסד הנתונים מתחיל בדרך כלל בתוכנית חינמית, והמדידות אמורות להיכנס בה. מחירים לא כתובים כאן כי הם משתנים. רואים אותם באתרים של הספקים.

ההצעה: Supabase למסד הנתונים, ו-<host> לשרת הקטן. אפשר להחליף ספק גם בהמשך, אבל זו עבודה נוספת.

מה עושים עכשיו: לכתוב לי אם ההצעה מתאימה, או אם כבר יש לך שרת או מסד נתונים שעדיף להשתמש בהם.
```

**Confirm:** the owner's choice is written in `PROGRESS.md`.

## Step 2. The database: one project, one file pasted once

**Who:** the owner opens the account and the project and runs one file.
**Prepare:** the finished `site-health/site_health.config.json`, then, in `site-health/`:

```bash
python3 manage.py install-sql --config site_health.config.json --out install.sql
DATABASE_URL=<a scratch database> python3 manage.py init-db --file install.sql     # the rehearsal: run it twice
```

`install.sql` is schema, functions and the `sh_setup` call in one file, with no secret in it. It is
safe to run again and deletes no measurement. It was run on PostgreSQL 16, never in Supabase's
own editor; that editor may ask for a confirmation because the file holds statements that delete
(old rows, at the nightly cleanup). **After every change of the configuration file, write the file
again and have the owner run it again** (message 2b): that is how pages and settings change.

```text
מתחילים במקום שבו יישמרו המדידות.

1. נכנסים לאתר supabase.com ופותחים חשבון.
2. יוצרים פרויקט חדש. בשם כותבים site-health, ובאזור בוחרים את הקרוב ביותר ל<המדינה של הגולשים>.
3. כשמבקשים סיסמה למסד הנתונים, נותנים לדפדפן להציע אחת ושומרים אותה אצלך. לא שולחים אותה אליי.

מה עושים עכשיו: לכתוב לי "הפרויקט מוכן" כשהוא נפתח. זה לוקח דקה או שתיים.
```

```text
עכשיו מכינים את מסד הנתונים. זה צעד אחד: מדביקים קובץ ולוחצים על כפתור.

1. פותחים את הקובץ install.sql ששלחתי, מסמנים את כולו ומעתיקים. אין בו שום סיסמה.
2. בפרויקט ב-Supabase מחפשים בתפריט את המקום שבו מריצים SQL (בדרך כלל SQL Editor) ופותחים בו דף חדש.
3. מדביקים ולוחצים על כפתור ההרצה (Run). אם מופיעה שאלה אם להריץ בכל זאת, מאשרים: הקובץ לא מוחק שום מדידה.
4. בתוצאה אמורה להופיע שורה שמתחילה במילים Site Health is installed for.

מה עושים עכשיו: להעתיק לי את השורה שהופיעה בתוצאה. אם הופיעה שגיאה, להעתיק לי אותה כמו שהיא.
```

**Confirm:** the line reads `Site Health is installed for <site>`. An error text holds no secret:
read it, fix the configuration, write the file again. The real proof comes in step 3: `"db": "ok"`.
Another Postgres (15 or newer): the same file in whatever SQL console it has, and `DATABASE_URL`
instead of the two Supabase variables.

## Step 3. The host: the small server

**Who:** the owner opens the account, creates the service and types the settings.
**Prepare:** the repository where the host can read it (ask before pushing), and these values:

| Setting | Value |
|---|---|
| Root directory | `site-health` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn server:app --host 0.0.0.0 --port $PORT --no-access-log` |
| Python | 3.10 or newer (tested with 3.13). If the host's default is older, set its Python version setting; how depends on the host |
| Health-check path | `/health` |
| Instances | exactly one, always on. No sleep when idle, no scaling to several: every copy would measure and alert |
| Region | near the site's visitors (§7.5) |

Environment variables, by name. The owner types every value; you only name them.

| Name | When | What the owner puts there |
|---|---|---|
| `SUPABASE_URL` | now | the project's address, `https://….supabase.co` |
| `SUPABASE_SECRET_KEY` | now | the project's **secret** key (`sb_secret_…`; on an older project the key named `service_role`), never the public one |
| `DASHBOARD_URL` | now | `<address>`, the service's own public address (not a secret: you give the value) |
| `SH_PASS_OWNER` | step 5 | the owner's password |
| `PAGESPEED_KEY` | step 4 | the Google key |
| `SH_PASS_VENDOR_CHECK` | step 5 | the throwaway check password; deleted after the check |
| `NTFY_TOPIC` | step 6, **last** | the alert topic |
| optional | when needed | `SH_PASS_STAFF`, `SH_PASS_VENDOR_<NAME>`, `SH_VENDOR_NOALERTS`, `SH_SHARE_TOKEN` (step 5), `HEARTBEAT_URL` (step 7). `reference/README.md` lists every variable |

```text
עכשיו מקימים את השרת הקטן שבודק את האתר ומציג את המסך.

1. נכנסים לאתר של <host> ופותחים חשבון.
2. יוצרים שירות חדש מהסוג שמריץ אתר (בדרך כלל Web Service), ומחברים אותו למאגר הקוד <repository>.
3. ממלאים את השדות האלה. מעתיקים כל ערך בדיוק כמו שהוא:
   - תיקיית הבסיס (Root Directory): site-health
   - פקודת הבנייה (Build Command): pip install -r requirements.txt
   - פקודת ההפעלה (Start Command): uvicorn server:app --host 0.0.0.0 --port $PORT --no-access-log
   - כתובת לבדיקת תקינות (Health Check Path): /health
4. בוחרים תוכנית שבה השרת עובד כל הזמן ולא נרדם, ואזור קרוב ל<המדינה של הגולשים>.

מה עושים עכשיו: לכתוב לי את הכתובת שהשירות קיבל (מתחילה ב-https://). היא לא סודית.
```

```text
עכשיו מחברים את השרת למסד הנתונים. מעתיקים שני ערכים מ-Supabase אל ההגדרות של השרת. הם לא עוברים דרכי.

1. ב-Supabase פותחים את הגדרות הפרויקט ומחפשים את העמוד של מפתחות ה-API.
2. ב-<host> פותחים את השירות ומחפשים את העמוד של משתני הסביבה (בדרך כלל Environment).
3. מוסיפים שם שלושה משתנים:
   - שם: SUPABASE_URL. ערך: כתובת הפרויקט. היא מתחילה ב-https:// ונגמרת ב-supabase.co
   - שם: SUPABASE_SECRET_KEY. ערך: המפתח הסודי (Secret key). הוא מתחיל ב-sb_secret_. לא המפתח הציבורי.
   - שם: DASHBOARD_URL. ערך: <address>
4. שומרים. השרת מופעל מחדש לבד.

מה עושים עכשיו: לכתוב לי "שמרתי". את המפתח עצמו לא שולחים לי.
```

**Confirm**, about two minutes after the save: `curl -s <address>/health` answers
`{"ok": true, "db": "ok", "screen": "ok", "last_probe_age_sec": <under 90>}`.

- `"screen": "missing"`: the root directory is not `site-health`, or `site_health.html` is not committed there.
- `"db"` is a text: it says what is wrong (the address must start with `https://`; an HTTP 401
  means the wrong key) and never holds the key. Ask the owner to paste the two values again.
- `"last_probe_age_sec": null`: nothing was measured yet. Step 2 did not run, or the service is
  not the single always-on instance.

**Then look at the first real round** (after step 5 gave you a check cookie): in
`<address>/api/site/now` every row of `pages` has `"ok": true`. If pages that open in a browser
fail there (a 403, a 503, a timeout), the site's firewall refuses the prober. Do not go on to
step 6; send this, and wait:

```text
המערכת מנסה לבדוק את האתר כל דקה, אבל האתר חוסם אותה. זה קורה כשלאתר יש חומת אש או הגנה מפני רובוטים.

מי שמנהל את האתר או את האחסון שלו צריך לאשר את הבודק. הוא מזדהה בשם SiteHealthProbe/1.0 ופונה מהשרת <address>.

עד שזה מאושר, המסך מראה שהאתר לא עונה גם כשהוא תקין. לכן עדיין לא מחברים את ההודעות לטלפון.

מה עושים עכשיו: להעביר את ההודעה הזאת למי שמנהל את האתר, ולכתוב לי כשזה אושר.
```

## Step 4. The Google key

**Who:** the owner. **Prepare:** nothing. The key is free and needs no billing account (§7.6).

```text
עכשיו יוצרים מפתח של גוגל. איתו המערכת מודדת כמה מהר האתר נטען. המפתח בחינם.

1. נכנסים ל-console.cloud.google.com עם חשבון גוגל.
2. יוצרים פרויקט חדש, או בוחרים פרויקט קיים.
3. מחפשים בשורת החיפוש שלמעלה PageSpeed Insights API, נכנסים אליו ומפעילים אותו (Enable).
4. בעמוד של פרטי הגישה (Credentials) יוצרים מפתח חדש מהסוג API key.
5. בהגדרות של המפתח מגבילים אותו כך שיעבוד רק עם PageSpeed Insights API. לא מגבילים אותו לפי כתובת אתר.
6. מעתיקים את המפתח. ב-<host>, בעמוד של משתני הסביבה, מוסיפים משתנה בשם PAGESPEED_KEY והמפתח הוא הערך. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי". את המפתח עצמו לא שולחים לי.
```

**Confirm:** within 20 minutes the flow `מדידת מהירות — עמודי ליבה` is `תקין` (the flow list of
step 5) and the screen's speed tiles show a figure. Still `אין נתון`: the key is refused or the
API is not enabled. The service's log says which, without the key; ask the owner to copy the line
that starts with `speed:`. After a repair the collector asks Google again within the hour.

## Step 5. The passwords, and the one you may hold for a check

**Who:** the owner makes every password up and types it into the host's settings.
**The recipe:** the password generator of the owner's browser or phone, 16 characters or more;
where there is none, four unrelated words and six digits. Passwords are compared without case.
One variable per person: `SH_PASS_OWNER`, `SH_PASS_STAFF`, `SH_PASS_VENDOR_<NAME>` (§8.1).
**The share link** (only if the owner wants one): `SH_SHARE_TOKEN`, at least 20 characters of
letters, digits and hyphens (four words and six digits with hyphens between them do). The link is
`<address>/status?k=<the token>`; the owner builds it and sends it, never through you.

```text
עכשיו קובעים את הסיסמה שלך למסך.

1. ממציאים סיסמה ארוכה, 16 תווים לפחות. הכי פשוט: לתת לדפדפן או לטלפון להציע סיסמה. אפשר גם ארבע מילים שלא קשורות זו לזו ואחריהן שש ספרות.
2. שומרים אותה אצלך, במקום שבו שמורות הסיסמאות שלך.
3. ב-<host>, בעמוד של משתני הסביבה, מוסיפים משתנה בשם SH_PASS_OWNER והסיסמה היא הערך. שומרים.
4. פותחים בטלפון את הכתובת <address>/site ונכנסים עם הסיסמה.

מה עושים עכשיו: לכתוב לי אם המסך נפתח בטלפון. את הסיסמה לא שולחים לי.
```

**The check password.** To see the deployed screen you sign in as a throwaway read-only vendor,
`SH_PASS_VENDOR_CHECK`. It is the only secret-like value that passes between you and the owner:
you make it up, it opens the vendor's view and nothing else, and it is deleted right after the
check. The server logs a warning at every start for as long as it is set.

```bash
python3 -c "import secrets; print('SH_PASS_VENDOR_CHECK=' + secrets.token_urlsafe(18))" > .env.check   # git-ignored
```

```text
כדי לבדוק שהמסך עובד כמו שצריך, צריך סיסמה זמנית לבדיקה. היא מאפשרת צפייה בלבד, ומוחקים אותה מיד אחרי הבדיקה.

1. ב-<host>, בעמוד של משתני הסביבה, מוסיפים משתנה בשם SH_PASS_VENDOR_CHECK.
2. בערך מדביקים את זה: <the value from .env.check>
3. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי". אכתוב לך כשהבדיקה נגמרת ואפשר למחוק.
```

The checks, from the root of the repository (`check_access.py`: at most twice in ten minutes):

```bash
set -a; . ./.env.check; set +a; BASE=<address>
COOKIE=$(curl -s -o /dev/null -D - --data-urlencode "p=$SH_PASS_VENDOR_CHECK" "$BASE/login" \
         | tr -d '\r' | sed -n 's/^[Ss]et-[Cc]ookie: \(sh_session=[^;]*\).*/\1/p')
node site-health-kit/check_screen.js "$BASE" --basic --cookie "$COOKIE"
python3 site-health-kit/tools/check_access.py "$BASE" --no-share --no-quiet
curl -s -H "Cookie: $COOKIE" "$BASE/api/site?h=24" | python3 -c "import json,sys
for f in json.load(sys.stdin)['health']: print(f['status'], '|', f['flow_name'], '|', f['silent_txt'] or '')"
```

The last command is the flow list: every flow must read `תקין` (go-live checklist, item 2). A
site that uses `SH_VENDOR_NOALERTS` gets a second throwaway, `SH_PASS_VENDOR_CHECK_QUIET`, with
`CHECK_QUIET` added to that list, and `--no-quiet` is dropped. Keep the check password while the
checklist of §10 runs (steps 6 and 7 fall inside it) and have it deleted the same day; if the
work stretches over days, delete it now and make a new one later. When the checks are done:

```text
הבדיקה הסתיימה. עכשיו מוחקים את הסיסמה הזמנית.

1. ב-<host>, בעמוד של משתני הסביבה, מוחקים את המשתנה SH_PASS_VENDOR_CHECK.
2. שומרים.

מה עושים עכשיו: לכתוב לי "מחקתי".
```

**Confirm:** the same sign-in now answers 401
(`curl -s -o /dev/null -w '%{http_code}\n' --data-urlencode "p=$SH_PASS_VENDOR_CHECK" "$BASE/login"`),
then `rm .env.check`. The owner's own sign-in is confirmed by the owner: "the screen opened on my phone".

## Step 6. The alert topic: last, and never through you

**When:** only after the first round of step 3 was clean and no alert is open that the owner does
not expect. Until `NTFY_TOPIC` is set nothing is pushed (alerts still open and show on the
screen); from the moment it is set, every alert reaches the phones. Tell the owner both.
**Who:** the owner makes the topic name up and types it in three places: the ntfy app of every
phone, the host's settings, and the watchdog of step 7. Its name is its only protection: whoever
knows it can read the alerts. It never appears in a chat, in the repository or in your terminal.

```text
עכשיו מחברים את ההודעות לטלפון. הן מגיעות דרך אפליקציה בשם ntfy, לערוץ שרק מי שיודע את השם שלו יכול לקרוא.

1. במחשב פותחים את ntfy.sh/app ולוחצים על הוספת ערוץ (Subscribe to topic).
2. בוחרים שם לערוץ. אם יש שם כפתור שמציע שם אקראי, לוחצים עליו. אם אין, ממציאים: ארבע מילים באנגלית שלא קשורות זו לזו ואחריהן שש ספרות, עם מקף בין החלקים ובלי רווחים.
3. שומרים את השם אצלך, ולא שולחים אותו אליי או בצ'אט: מי שיודע אותו יכול לקרוא את ההודעות.
4. בטלפון מתקינים את האפליקציה ntfy מחנות האפליקציות, לוחצים בה על הפלוס, מקלידים את שם הערוץ בדיוק ומאשרים. כשהטלפון שואל אם לאפשר התראות, מאשרים.

מה עושים עכשיו: לכתוב לי "הערוץ מוכן".
```

```text
עכשיו מגדירים לשרת לאיזה ערוץ לשלוח.

1. ב-<host>, בעמוד של משתני הסביבה, מוסיפים משתנה בשם NTFY_TOPIC ושם הערוץ הוא הערך. שומרים.
2. מעכשיו כל התראה מגיעה לטלפון. בכל בוקר מגיעה גם הודעת "בוקר טוב" עם סיכום קצר. ביום הראשון היא עוד לא נשלחת.

מה עושים עכשיו: לכתוב לי "שמרתי".
```

Every other person of intake row 7 gets the name from the owner, privately, and does item 4.

**Confirm that a phone shows a push.** You cannot send one: the topic is not yours. In this order:

1. If the host gives the owner a command screen for the service, they run one line there
   (message below). It prints `ntfy answered 200` and no secret.
2. The planned stop of step 7 produces two real pushes.
3. The first morning message, the day after. Until one of the three happened, the item stays open.

```text
שולחים הודעת בדיקה לטלפון.

1. ב-<host> פותחים את השירות ומחפשים מסך להקלדת פקודות (בדרך כלל Shell או Console).
2. מדביקים שם את השורה הזאת ולוחצים Enter:   python3 manage.py test-push
3. בטלפון אמורה להגיע הודעה בשם "בדיקה: בריאות האתר".

מה עושים עכשיו: לכתוב לי אם ההודעה הגיעה לטלפון.
```

## Step 7. Who watches the watcher

If the small server stops, nothing inside it can say so (§7.10). Pick one independent check:

| Option | For | What the owner does |
|---|---|---|
| 1. `site-health/deadman.sql` | a Supabase database | switches on two extensions, adds two secrets to the database's secret store, pastes one more file (message below). No further account. Never run on a real project: if its test does not pass, take option 2 |
| 2. a heartbeat service | any host | opens an account at such a service, creates a check that expects a ping every minute and alarms after about 10 silent minutes, and puts the check's ping address into the host's settings as `HEARTBEAT_URL`. The alarm comes through that service (usually e-mail), in its own words |
| 3. `site-health/watchdog.py` | any host | runs this one file somewhere that does not stop with the host (a second small always-on service with `--loop`, or a cron job every 5 minutes), with `NTFY_TOPIC` typed into that place's settings. A second always-on service is normally paid as well |

```text
עוד צעד אחד ב-Supabase: שומר שבודק שהמדידה עצמה לא נעצרה. אם השרת הקטן מפסיק לעבוד, השומר הוא ששולח לך הודעה.

1. ב-Supabase מחפשים את העמוד של התוספים למסד הנתונים (Integrations או Extensions) ומפעילים שניים: Cron ו-pg_net.
2. מחפשים את הכספת (Vault) ומוסיפים בה שני סודות:
   - שם: sh_ntfy_topic. ערך: שם הערוץ מהאפליקציה ntfy.
   - שם: sh_dashboard_url. ערך: <address>
3. פותחים את הקובץ deadman.sql ששלחתי, מעתיקים את כולו, מדביקים במקום שבו מריצים SQL ולוחצים על כפתור ההרצה.

מה עושים עכשיו: לכתוב לי אם ההרצה הסתיימה בלי שגיאה. אם הופיעה שגיאה, להעתיק לי אותה כמו שהיא.
```

**The test** (go-live checklist, item 3). Only the owner can stop the service. Announce it first:

```text
בדיקה אחרונה: עוצרים את השרת בכוונה ל-16 דקות, כדי לראות שמגיעה הודעה כשהמדידה נעצרת. בזמן הזה המסך לא נפתח. זה מתוכנן.

1. ב-<host> עוצרים את השירות (בדרך כלל Suspend או Stop).
2. מחכים 16 דקות. בטלפון אמורה להגיע ההודעה "המדידה נעצרה: בודק זמינות האתר".
3. מפעילים את השירות מחדש. תוך כמה דקות אמורה להגיע ההודעה "חזר לתקין: בודק זמינות האתר".

מה עושים עכשיו: לכתוב לי אילו הודעות הגיעו לטלפון, ובאיזו שעה.
```

**Confirm:** what the owner reports (with option 2: the heartbeat service's own alarm and its own
"up again"; change the message accordingly); from the outside, `/health` stops answering and,
after the start, shows a `last_probe_age_sec` under 90. With option 1 the alert is also in the
screen's list of the period's alerts, and its recovery push comes from the server itself: that
push proves the topic in the host's settings as well.

## Step 8. The add-on on the site

It measures how fast pages load for real visitors (§7.7). **Who:** whoever can install a plugin on
the site or paste a snippet into its theme (intake row 12); the owner forwards your message.

- **WordPress.** In `site-health/`: `python3 manage.py rum-plugin --endpoint <address>/m --out site-health-rum.zip`
  (the live host comes from the configuration). Send the ZIP with the message below.
- **Shopify.** Copy `site-health/rum/site-health-rum.liquid`, fill its two `assign` lines
  (`<address>/m`, and the shop's public host without `www`), and send the copy with the second
  message below. It has never run in a real shop: the message says so.
- **Any other site.** Its developer adds one line and the script (§7.7, Delivery).

```text
הצעד האחרון הוא באתר עצמו: תוסף קטן שמודד כמה מהר העמודים נטענים אצל הגולשים. אם מישהו אחר מנהל את האתר, מעבירים לו את ההודעה הזאת ואת הקובץ.

1. שומרים במחשב את הקובץ site-health-rum.zip ששלחתי. לא פותחים אותו.
2. בניהול האתר (וורדפרס) נכנסים לתוספים, בוחרים להוסיף תוסף חדש, ואז להעלות תוסף.
3. בוחרים את הקובץ, מתקינים ומפעילים.
4. אם באתר יש תוסף מטמון (cache), מנקים את המטמון.
5. פותחים עמוד כלשהו באתר, מוסיפים בסוף הכתובת ?sh_test=1, מחכים שהעמוד ייטען וסוגרים אותו.

מה עושים עכשיו: לפתוח את המסך ולכתוב לי מה כתוב בריבוע "מהירות אצל לקוחות, שעה אחרונה".
```

```text
הצעד האחרון הוא בחנות עצמה: קטע קוד קטן שמודד כמה מהר העמודים נטענים אצל הגולשים. הוא עוד לא נוסה בחנות אמיתית של Shopify, ולכן בסוף בודקים יחד שהוא עובד.

1. בניהול החנות נכנסים לחנות המקוונת (Online Store) ומשם לערכות העיצוב (Themes).
2. ליד ערכת העיצוב הפעילה פותחים את התפריט (שלוש נקודות) ובוחרים לשכפל אותה (Duplicate). זה עותק לגיבוי.
3. באותו תפריט בוחרים לערוך את הקוד (Edit code), ופותחים את הקובץ theme.liquid שבתיקייה layout.
4. קרוב לסוף הקובץ מחפשים את השורה </body>. בשורה שמעליה מדביקים את כל התוכן של הקובץ site-health-rum.liquid ששלחתי, ושומרים.
5. פותחים עמוד כלשהו בחנות, מוסיפים בסוף הכתובת ?sh_test=1, מחכים שהעמוד ייטען וסוגרים אותו.

מה עושים עכשיו: לפתוח את המסך ולכתוב לי מה כתוב בריבוע "מהירות אצל לקוחות, שעה אחרונה".
```

**Confirm:** from the outside, `curl -s <site>/ | grep -c 'site-health-rum'` prints 1 or more (the
script is on the page); the owner reads the tile: a count, and "מתוכן מדידת בדיקה אחת". Nothing
arrives within a minute: `curl -sI <site>/ | grep -i content-security-policy`. If the site sends
that header, its developer must allow `<address>` in `connect-src` and the inline script in
`script-src`; otherwise the page cache was not purged, or a "delay JavaScript" optimization holds
the script back (§7.7).

Then tell the owner what the add-on sends. Whether the site's privacy policy needs the sentence
is their decision; they can only make it when told.

```text
דבר אחד שכדאי לדעת על התוסף. מעכשיו, בכל פעם שגולש פותח עמוד באתר, הדפדפן שלו שולח למסך בריאות האתר שני דברים: איזה עמוד נפתח, וכמה זמן לקח לו להיטען. לא נשלח ולא נשמר שום פרט שמזהה את הגולש.

אם לאתר יש מדיניות פרטיות, אפשר להוסיף לה את המשפט הזה:
"האתר מודד את מהירות הטעינה של העמודים. בכל צפייה בעמוד נשלחים לשירות המדידה של האתר כתובת העמוד וזמן הטעינה שלו, בלי שום פרט שמזהה את הגולש."

ההחלטה אם להוסיף אותו היא שלך, או של מי שמייעץ לך בנושא.

מה עושים עכשיו: אין צורך לעשות דבר, אלא אם מחליטים להוסיף את המשפט.
```

## Step 9. The hand-over note

**Who:** you write it, when the go-live checklist of §10 is green. Fill every `<…>`, leave out the
lines that do not apply (no certificate check, no watchdog push with option 2), and keep it one note.

```text
המסך "בריאות האתר" מוכן. כדאי לשמור את ההודעה הזאת.

הכתובת: <address>/site. נכנסים עם הסיסמה שקבעת.

הצבעים: ירוק זה תקין. צהוב זה לשים לב. אדום זה תקלה. אפור זה שעדיין אין נתון.

ההודעות לטלפון מגיעות באפליקציה ntfy. כדי לצרף עוד טלפון: מתקינים בו את האפליקציה, לוחצים על הפלוס ומקלידים את שם הערוץ. האפליקציה שומרת הודעות 12 שעות; במסך, בכרטיס "הודעות שנשלחו לטלפון", הן נשארות. באייפון הודעה מגיעה לפעמים באיחור.

מה עושים כשמגיעה הודעה:
- "האתר לא עונה": פותחים את העמוד בטלפון. אם הוא לא נפתח, פונים למי שמאחסן את האתר. כשכל האתר נופל מגיעה הודעה נפרדת על כל עמוד שנבדק, <N> הודעות. זו תקלה אחת, לא <N>.
- "עמוד איטי": לא דחוף. אם זה חוזר, מעבירים למי שמתחזק את האתר.
- "תעודת האבטחה פגה בעוד…": מעבירים באותו יום למי שמאחסן את האתר. כשהתעודה פגה, הגולשים רואים אזהרה במקום את האתר.
- "המדידה נעצרה": האתר עצמו כנראה תקין, אבל הבודק הפסיק לעבוד, וייתכן שגם המסך לא נפתח. נכנסים ל-<host> ובודקים שהשירות פועל. אם לא ברור מה קרה, כותבים לקודקס: "בריאות האתר: הגיעה הודעה שהמדידה נעצרה".
- "חזר לתקין": התקלה נגמרה. אין צורך לעשות דבר.
- "בוקר טוב": סיכום יומי. הוא גם הסימן שההודעות עובדות: אם בוקר אחד הוא לא מגיע, משהו נעצר.

אי אפשר להשתיק את ההודעות מתוך המסך. לפני עבודה מתוכננת על האתר אפשר להשתיק את הערוץ באפליקציה לכמה שעות.

החשבונות שנפתחו, כולם על השם שלך:
- Supabase: שם נשמרות המדידות.
- <host>: השרת הקטן. זה החשבון שבתשלום חודשי. שם שמורים גם הסיסמאות, המפתח של גוגל ושם הערוץ, בעמוד של משתני הסביבה.
- גוגל: המפתח למדידת המהירות.
כדי להחליף סיסמה, משנים את הערך שלה ב-<host> ושומרים. מי שנכנס עם הסיסמה הישנה יתבקש להיכנס מחדש.

כדי לשנות משהו, כותבים לקודקס בתיקייה של הפרויקט. למשל:
- "בריאות האתר: להוסיף עמוד לבדיקה, <כתובת>"
- "בריאות האתר: מחקתי מהאתר את העמוד <שם>, להפסיק לבדוק אותו"
- "בריאות האתר: לתת גישת צפייה ל<שם>"
חשוב: אם מוחקים מהאתר עמוד שנבדק, או משנים את הכתובת שלו, מגיעה הודעה "האתר לא עונה" עד שמעדכנים את קודקס.

מה עושים עכשיו: לשמור את ההודעה הזאת.
```

For you, when such a request comes later: read `START-HERE.md` and `PROGRESS.md` first. A change
of pages or settings is a change of `site_health.config.json`, a new `install.sql` and message 2b
again; the collectors pick a new page list up within five minutes. A change of people is a
variable the owner adds or deletes in the host's settings (step 5). There is no pause for alerts.

<!-- EOF OWNER-STEPS.md -->
