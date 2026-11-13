# Site Health kit: the steps only the owner can do

Part of the Site Health kit (entry point `START-HERE.md`): phases 8 and 9 of §9 and the money
question of the intake. Read it completely.

**START-HERE rule 5: you never hold a production secret.** The owner opens every account and types
every secret where it is needed. You prepare a file or the values, send one short message, and
confirm from the outside (`/health`, the screen through a throwaway read-only password, what the
owner sees). Nothing the owner reports back is a secret.

- Send each message as written, every `<…>` filled in: **one message, one step**; wait for the
  answer. Messages are referred to by their labels (`2b`, `4c`, …).
- **Other services' menus and buttons were not checked.** Look them up if you can, or keep the
  wording, which promises no label; if the owner does not find something, ask what they see.
- **Never quote a price.** "Normally free" and "normally paid monthly" say what is usual.
- **Files for the owner:** `install.sql`, `site-health-rum.zip` (generated, git-ignored, no secret)
  and `site-health/deadman.sql`. On the owner's computer, name the folder (in the messages
  `ששלחתי` becomes `שנמצא בתיקייה <folder> במחשב שלך`). In a cloud sandbox,
  attach the file, or else commit it once (`git add -f <file>`) and remove it after the step.

`<address>`: the dashboard's public address (step 4). `<host>`: the owner's hosting provider.
`<site>`: the monitored site. `<repository name>`: the repository of step 3.

---

## Step 1. What it takes, and what is paid (before the owner chooses anything)

**Who:** you, during the intake (row 9), before any account is opened.

Facts for you: Supabase settles around 200 MB plus the real-user rows (§7.2); a free project holds
500 MB and may be paused when idle (read the current terms). Any host that keeps one small Python
process running **all the time** will do; none was tried from here. If the repository already has
a remote the owner controls, drop item 2 and write "חמישה דברים".

```text
כדי שהמסך יעבוד צריך שישה דברים, כולם על השם שלך:

1. מקום לשמירת המדידות (מסד נתונים). פותחים בשבילו חשבון.
2. מקום לקוד שאני כותב (מאגר ב-GitHub). פותחים שם חשבון, אם אין לך. למאגר פרטי זה בדרך כלל בחינם.
3. שרת קטן שעובד כל הזמן, בודק את האתר כל דקה ומציג את המסך. גם בשבילו פותחים חשבון.
4. מפתח של גוגל למדידת המהירות. הוא בחינם.
5. האפליקציה ntfy בכל טלפון שמקבל הודעות. היא בחינם, ולא צריך לפתוח בה חשבון.
6. תוסף קטן באתר, שמודד כמה מהר העמודים נטענים אצל הגולשים.

מה עולה כסף: השרת הקטן, בדרך כלל בתשלום חודשי. הוא חייב לעבוד בלי הפסקה, ולכן תוכנית חינמית ש"נרדמת" כשאין תנועה לא מתאימה. למסד הנתונים מספיקה בדרך כלל תוכנית חינמית. את המחירים רואים באתרים של הספקים. אם בהמשך יצטרך עוד שירות או חשבון, אשאל אותך לפני.

ההצעה: Supabase למסד הנתונים, GitHub לקוד ו-<host> לשרת הקטן. אפשר להחליף ספק גם אחר כך, אבל זו עבודה נוספת.

מה עושים עכשיו: לכתוב לי אם ההצעה מתאימה, או אם כבר יש לך שרת או מסד נתונים שעדיף להשתמש בהם.
```

**Confirm:** the owner's choice is written in `PROGRESS.md`.

## Step 2. The database: one project, one file pasted once

**Who:** the owner. **Prepare**, in `site-health/`, from the finished `site_health.config.json`:

```bash
python3 manage.py install-sql --config site_health.config.json --out install.sql
DATABASE_URL=<a scratch database> python3 manage.py init-db --file install.sql     # the rehearsal: run it twice
```

`install.sql` (schema, functions, the `sh_setup` call; no secret) is safe to run again and deletes
no measurement. It ran on PostgreSQL 16, never in Supabase's editor, which may ask to confirm its
delete statements (the nightly cleanup). **After every change of the configuration, write it again
and send 2b again**: that is how pages and settings change.

**2a**, the project:

```text
מתחילים במקום שבו יישמרו המדידות.

1. נכנסים לאתר supabase.com ופותחים חשבון. כשנשאלים איזו תוכנית, בוחרים בתוכנית החינמית (Free).
2. יוצרים פרויקט חדש. בשם כותבים site-health, ובאזור בוחרים את הקרוב ביותר ל<המדינה של הגולשים>.
3. כשמבקשים סיסמה למסד הנתונים, נותנים לדפדפן להציע אחת ושומרים אותה אצלך. לא שולחים אותה אליי.

מה עושים עכשיו: לכתוב לי "הפרויקט מוכן" כשהוא נפתח. זה לוקח דקה או שתיים.
```

**2b**, the file:

```text
עכשיו מכינים את מסד הנתונים: מדביקים קובץ אחד ומריצים אותו.

1. פותחים את הקובץ install.sql ששלחתי: לחיצה ימנית עליו, "פתח באמצעות" (Open With), ובוחרים פנקס רשימות (Notepad) ב-Windows או TextEdit במק.
2. מסמנים את כל הטקסט (Ctrl+A, ובמק Cmd+A) ומעתיקים.
3. ב-Supabase מחפשים בתפריט את המקום שבו מריצים SQL (בדרך כלל SQL Editor) ופותחים בו דף חדש.
4. מדביקים ולוחצים על כפתור ההרצה (Run). אם נשאלים אם להריץ בכל זאת, מאשרים: הקובץ לא מוחק שום מדידה.
5. בתוצאה אמורה להופיע שורה שמתחילה במילים Site Health is installed for.

מה עושים עכשיו: להעתיק לי את השורה הזאת, או את השגיאה אם הופיעה שגיאה.
```

**Confirm:** the line reads `Site Health is installed for <site>`. An error holds no secret: fix the
configuration and write the file again. The real proof is `"db": "ok"` in step 4. Another Postgres
(15 or newer): the same file in its SQL console, and `DATABASE_URL` for the two Supabase variables.

## Step 3. The code: a private repository the host can read

**Who:** the owner opens the account and the repository and lets you in; you push. **Skip it** when
`git remote -v` already names a repository the owner controls and the host can read.

Facts for you: the host builds from a Git repository, by default a **private** GitHub one (any Git
hosting it can read will do). No token ever passes through the chat or into a remote address. On
the owner's computer sign in through the browser: `gh auth login --web` (it prints a short one-time
code; give it to the owner), or Git Credential Manager when `git config credential.helper` names
`manager`; never let a password prompt reach the terminal. In a cloud workspace connected to
GitHub, the owner grants that connection the repository. The owner's answer is the repository's
address: `git remote add origin <it>.git`. Before the first push run the secret check of §10 item
7; that answer is the owner's request to push (START-HERE rule 12).

```text
עכשיו פותחים מקום לקוד שאני כותב. השרת הקטן ייקח את הקוד משם.

1. נכנסים ל-github.com. אם אין לך חשבון, פותחים חשבון בתוכנית החינמית (Free). אפשר לשמור בה מאגר פרטי.
2. יוצרים מאגר חדש (New repository). בשם כותבים <repository name> ובוחרים פרטי (Private). את שאר השדות משאירים כמו שהם.
3. <במחשב שלך: כשאעלה את הקוד בפעם הראשונה, ייפתח בדפדפן חלון כניסה של GitHub. נכנסים שם ומאשרים. אם מתבקש קוד קצר, אכתוב לך אותו. | בענן: בהגדרות של קודקס, בחיבור ל-GitHub, נותנים גישה למאגר <repository name>.>
4. לא שולחים לי סיסמה או מפתח של GitHub. נכנסים רק בחלון של GitHub עצמו.

מה עושים עכשיו: להעתיק לי את הכתובת של המאגר מהדפדפן (מתחילה ב-https://github.com/). היא לא סודית. אחרי זה אעלה אליו את הקוד.
```

Keep the variant of item 3 that fits where you run. **Confirm:** the push succeeds, and an anonymous
`curl -s -o /dev/null -w '%{http_code}\n' <the address>` answers 404 (private).

## Step 4. The host: the small server

**Who:** the owner. **Prepare:** the code pushed (step 3). 4a holds the values (Python 3.10 or
newer, tested with 3.13; a host that reads the version from a variable or a file gets it there:
name it in 4b, or commit the file). **Exactly one instance, always on**: no sleep when idle, no
scaling (every copy would measure and alert). Region: near the site's visitors (§7.5). The owner
types every variable's value (all of them are in `reference/README.md`).

**4a**, the service:

```text
עכשיו מקימים את השרת הקטן.

1. נכנסים לאתר של <host> ופותחים חשבון.
2. יוצרים שירות חדש מהסוג שמריץ אתר (בדרך כלל Web Service) ומחברים אותו ל-GitHub. כשנשאלים לאילו מאגרים לתת גישה, בוחרים רק את <repository name>.
3. ממלאים את השדות האלה, כל ערך בדיוק כמו שהוא:
   - תיקיית הבסיס (Root Directory): site-health
   - פקודת הבנייה (Build Command): pip install -r requirements.txt
   - פקודת ההפעלה (Start Command): uvicorn server:app --host 0.0.0.0 --port $PORT --no-access-log
   - כתובת לבדיקת תקינות (Health Check Path): /health
4. אם יש מקום לבחור גרסה של Python, בוחרים 3.13.
5. בוחרים תוכנית שבה השרת עובד כל הזמן ולא נרדם (בדרך כלל התוכנית בתשלום), ואזור קרוב ל<המדינה של הגולשים>.

מה עושים עכשיו: לכתוב לי את הכתובת שהשירות קיבל (מתחילה ב-https://). היא לא סודית.
```

**4b**, the database settings:

```text
עכשיו מחברים את השרת למסד הנתונים. מעתיקים שני ערכים מ-Supabase להגדרות של השרת. הם לא עוברים דרכי.

1. ב-Supabase פותחים את הגדרות הפרויקט ומחפשים את העמוד של מפתחות ה-API.
2. ב-<host> פותחים את השירות ומחפשים את העמוד של משתני הסביבה (בדרך כלל Environment).
3. מוסיפים שם שלושה משתנים:
   - שם: SUPABASE_URL. ערך: כתובת הפרויקט. היא מתחילה ב-https:// ונגמרת ב-supabase.co
   - שם: SUPABASE_SECRET_KEY. ערך: המפתח הסודי (Secret key). הוא מתחיל ב-sb_secret_. לא המפתח הציבורי.
   - שם: DASHBOARD_URL. ערך: <address>
4. שומרים. השרת מופעל מחדש לבד.

מה עושים עכשיו: לכתוב לי "שמרתי". את המפתח עצמו לא שולחים לי.
```

**4c**, a line of the service's log (`<word>`: what it contains; the server never logs a secret).

```text
צריך שורה אחת מהיומן של השרת. אין בה שום סוד.

1. ב-<host> פותחים את השירות ומחפשים את היומן שלו (בדרך כלל Logs).
2. מחפשים בו את המילה <word>: בשדה החיפוש של היומן, ואם אין כזה, בחיפוש של הדפדפן (Ctrl+F, ובמק Cmd+F).
3. מסמנים בעכבר את השורה האחרונה שיש בה <word>, מעתיקים ומדביקים לי.

מה עושים עכשיו: להדביק לי את השורה. אם אין שורה כזאת, לכתוב לי "אין".
```

**Confirm**, about two minutes after the save: `curl -s <address>/health` answers
`{"ok": true, "db": "ok", "screen": "ok", "last_probe_age_sec": <under 90>}`.

- `"screen": "missing"`: the root directory is not `site-health`, or `site_health.html` is not committed there.
- `"db"` is a text saying what is wrong, never the key: the address must start with `https://`;
  HTTP 401 is the wrong key (the secret one; on an older project `service_role`). Have the two
  values pasted again.
- `"last_probe_age_sec": null`: step 2 did not run, or the service is not one always-on instance.
- No answer: the build or the start failed: 4c with `Error` (or `Traceback`). A Python older than
  3.10 fails at the start.

**Then the first real round** (once step 6 gave you a check cookie): every row of `pages` in
`<address>/api/site/now` has `"ok": true`. Pages that open in a browser but fail there (403, 503,
a timeout): the site's firewall refuses the prober. Do not go on to step 7; send this:

```text
המערכת מנסה לבדוק את האתר כל דקה, אבל האתר חוסם אותה (חומת אש או הגנה מפני רובוטים).

מי שמנהל את האתר או את האחסון שלו צריך לאשר את הבודק: הוא מזדהה בשם SiteHealthProbe/1.0 ופונה מהשרת <address>.

עד שזה מאושר, המסך מראה שהאתר לא עונה גם כשהוא תקין, ולכן עוד לא מחברים את ההודעות לטלפון.

מה עושים עכשיו: להעביר את ההודעה הזאת למי שמנהל את האתר, ולכתוב לי כשזה אושר.
```

## Step 5. The Google key

**Who:** the owner. The key is free, needs no billing account (§7.6), and is required: the core
speed flow cannot be switched off and stays `אין נתון` without it (§10 item 2).

```text
עכשיו יוצרים מפתח של גוגל, שאיתו המערכת מודדת כמה מהר האתר נטען. המפתח בחינם.

1. נכנסים ל-console.cloud.google.com עם חשבון גוגל, ויוצרים פרויקט חדש או בוחרים פרויקט קיים. אם מוצע ניסיון חינם או מבקשים כרטיס אשראי, מדלגים: המפתח לא צריך את זה.
2. מחפשים בשורת החיפוש שלמעלה PageSpeed Insights API, נכנסים אליו ומפעילים אותו (Enable).
3. בעמוד של פרטי הגישה (Credentials) יוצרים מפתח חדש מהסוג API key.
4. בהגדרות של המפתח מגבילים אותו כך שיעבוד רק עם PageSpeed Insights API. לא מגבילים אותו לפי כתובת אתר.
5. מעתיקים את המפתח. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם PAGESPEED_KEY והמפתח הוא הערך. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי". את המפתח עצמו לא שולחים לי.
```

**Confirm:** within 20 minutes the flow `מדידת מהירות — עמודי ליבה` is `תקין` (the flow list of
step 6) and the speed tiles show a figure. Still `אין נתון`: the key is refused or the API is off;
4c with the word `speed:` (the line that contains it) says which, without the key. After a repair
the collector asks Google again within the hour.

## Step 6. The passwords, and the one you may hold for a check

**Who:** the owner makes every password up (16 characters or more; compared without case) and types
it into the host's settings. One variable per person (§8.1).

**6a**, the owner's password and `SH_PASS_VENDOR_CHECK`, a throwaway read-only vendor: the only
secret-like value between you and the owner (a new one later: item 4 alone, with the first and
last line).

```bash
python3 -c "import secrets; print('SH_PASS_VENDOR_CHECK=' + secrets.token_urlsafe(18))" > .env.check   # git-ignored
# only with SH_VENDOR_NOALERTS (6b item 3), for 6e:
python3 -c "import secrets; print('SH_PASS_VENDOR_CHECK_QUIET=' + secrets.token_urlsafe(18))" >> .env.check
```

```text
עכשיו קובעים את הסיסמה שלך למסך, ומוסיפים סיסמה זמנית שבה אבדוק את המסך.

1. ממציאים סיסמה ארוכה, 16 תווים לפחות. הכי פשוט: לתת לדפדפן או לטלפון להציע סיסמה. אפשר גם ארבע מילים שלא קשורות זו לזו ואחריהן שש ספרות.
2. שומרים אותה אצלך, עם שאר הסיסמאות שלך.
3. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם SH_PASS_OWNER והסיסמה היא הערך.
4. מוסיפים שם עוד משתנה בשם SH_PASS_VENDOR_CHECK, ובערך מדביקים: <the value from .env.check>. זו הסיסמה הזמנית, לצפייה בלבד. נמחק אותה מיד אחרי הבדיקה.
5. שומרים, ופותחים בטלפון את הכתובת <address>/site עם הסיסמה שלך.

מה עושים עכשיו: לכתוב לי אם המסך נפתח בטלפון. את הסיסמה שלך לא שולחים לי.
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

The last command is the flow list: every flow must read `תקין` (§10 item 2). With
`SH_VENDOR_NOALERTS`, send 6e and drop `--no-quiet`. Keep the check passwords through the §10
checklist (steps 7 and 8 included), then send 6d the same day; if the work takes days, delete them
now and make new ones later.

**6b**, another person (intake row 8). `<VARIABLE>`: `SH_PASS_STAFF` (everything; one password for
all staff) or `SH_PASS_VENDOR_<NAME>` (read-only; `<NAME>`: capitals, digits, `_`). Item 3 only for
a vendor who must not see alerts. A name there that matches no vendor hides the alerts from every
vendor (§8.1): 4c with the word `SH_VENDOR_NOALERTS` must find no line.

```text
עכשיו נותנים ל<שם> גישה <למסך כולו | למסך, לצפייה בלבד>.

1. ממציאים סיסמה חדשה רק ל<שם>, כמו שעשית עם הסיסמה שלך.
2. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם <VARIABLE> והסיסמה היא הערך. שומרים.
3. באותו מקום מוסיפים משתנה בשם SH_VENDOR_NOALERTS וכותבים בו <NAME>. אם הוא כבר קיים, מוסיפים בסופו פסיק ואת השם. שומרים. כך ההתראות לא יוצגו ל<שם>.
4. שולחים ל<שם> את הכתובת <address>/site ואת הסיסמה בהודעה פרטית, לא דרכי.

מה עושים עכשיו: לכתוב לי "שמרתי". את הסיסמה לא שולחים לי.
```

**6c**, the share link, only if the owner wants one. `SH_SHARE_TOKEN`: 20 or more letters, digits
and hyphens. The owner sends the link, never through you; you confirm with the made-up token of
§10 item 5.

```text
קישור צפייה פותח את המסך בלי סיסמה, לצפייה בלבד. כל מי שמחזיק בו רואה את המסך, ולכן שולחים אותו רק למי שצריך.

1. ממציאים מפתח לקישור: ארבע מילים באנגלית שלא קשורות זו לזו ואחריהן שש ספרות, עם מקף בין החלקים ובלי רווחים.
2. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם SH_SHARE_TOKEN והמפתח הוא הערך. שומרים.
3. הקישור הוא <address>/status?k= ומיד אחריו המפתח, בלי רווח. שומרים אותו אצלך ופותחים אותו בטלפון.
4. כדי לבטל את הקישור מוחקים את המשתנה ושומרים.

מה עושים עכשיו: לכתוב לי אם המסך נפתח מהקישור. את הקישור לא שולחים לי.
```

**6d**, when the checks are done:

```text
הבדיקה הסתיימה. עכשיו מוחקים את הסיסמה הזמנית.

1. ב-<host>, במשתני הסביבה, מוחקים את המשתנה SH_PASS_VENDOR_CHECK.
2. <only after 6e:> מוחקים גם את SH_PASS_VENDOR_CHECK_QUIET. במשתנה SH_VENDOR_NOALERTS מוחקים את הפסיק ואת CHECK_QUIET (אם זו המילה היחידה בו, מוחקים את כל המשתנה).
3. שומרים.

מה עושים עכשיו: לכתוב לי "מחקתי".
```

**Confirm:** the same sign-in now answers 401 (`curl -s -o /dev/null -w '%{http_code}\n'
--data-urlencode "p=$SH_PASS_VENDOR_CHECK" "$BASE/login"`), and so does `$SH_PASS_VENDOR_CHECK_QUIET`
after 6e; 4c with the word `SH_VENDOR_NOALERTS` finds no line (`אין`); then `rm .env.check`.

**6e**, only with `SH_VENDOR_NOALERTS`, before the checks: the second throwaway password, a vendor
without alerts (`check_access.py` then runs without `--no-quiet`).

```text
עוד סיסמה זמנית אחת, כדי לבדוק שמי שלא אמור לראות התראות באמת לא רואה אותן.

1. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם SH_PASS_VENDOR_CHECK_QUIET, ובערך מדביקים: <the second value from .env.check>. נמחק אותה מיד אחרי הבדיקה.
2. במשתנה SH_VENDOR_NOALERTS מוסיפים בסופו פסיק ואת המילה CHECK_QUIET, בלי רווח.
3. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי".
```

**6f**, only when the limiter check of §10 item 4 fails. `<n>`: how many proxies the host puts in
front of the service (its documentation; §8.2). Run the check again ten minutes later.

```text
צריך לתקן הגדרה אחת בשרת. היא לא סודית.

1. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם SH_PROXY_HOPS ובערך כותבים <n>. אם הוא כבר קיים, משנים את הערך ל-<n>.
2. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי".
```

## Step 7. The alert topic: after a clean first round, and never through you

**When:** after a clean first round (step 4), with no alert open that the owner does not expect.
Until `NTFY_TOPIC` is set nothing is pushed (alerts still show on the screen); from then on every
alert reaches the phones: tell the owner both. The name, made up by the owner, is the topic's
only protection: it never appears in a chat, the repository or your terminal.

**7a**:

```text
עכשיו מחברים את ההודעות לטלפון, דרך האפליקציה ntfy. היא בחינם, ולא צריך לפתוח בה חשבון. ההודעות נשלחות לערוץ שרק מי שיודע את השם שלו יכול לקרוא.

1. במחשב פותחים את ntfy.sh/app ולוחצים על הוספת ערוץ (Subscribe to topic). אם מוצעת הרשמה או תוכנית בתשלום, מדלגים.
2. בוחרים שם לערוץ. אם יש כפתור שמציע שם אקראי, לוחצים עליו. אם אין, ממציאים ארבע מילים באנגלית שלא קשורות זו לזו ואחריהן שש ספרות, עם מקף בין החלקים ובלי רווחים.
3. שומרים את השם אצלך. לא שולחים אותו אליי ולא כותבים אותו בצ'אט.
4. בטלפון מתקינים את ntfy מחנות האפליקציות, לוחצים בה על הפלוס, מקלידים את שם הערוץ בדיוק ומאשרים. כשהטלפון שואל אם לאפשר התראות, מאשרים.
5. ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם NTFY_TOPIC ושם הערוץ הוא הערך. שומרים. מעכשיו כל התראה מגיעה לטלפון, ומהבוקר הבא בכל בוקר גם סיכום קצר בשם "בוקר טוב".

מה עושים עכשיו: לכתוב לי "שמרתי".
```

Every other person of intake row 7 gets the name from the owner, privately, and does item 4.

**Confirm that a phone shows a push.** You cannot send one (the topic is not yours). The first of:
(1) 7b, if the host offers a command screen (it prints `ntfy answered 200`, no secret); (2) the two
pushes of the planned stop in step 8; (3) the first morning message. Until then the item is open.

**7b**:

```text
שולחים הודעת בדיקה לטלפון.

1. ב-<host> פותחים את השירות ומחפשים מסך להקלדת פקודות (בדרך כלל Shell או Console).
2. מדביקים שם את השורה הזאת ולוחצים Enter:   python3 manage.py test-push
3. בטלפון אמורה להגיע הודעה בשם "בדיקה: בריאות האתר".

מה עושים עכשיו: לכתוב לי אם ההודעה הגיעה לטלפון.
```

## Step 8. Who watches the watcher

If the small server stops, nothing inside it can say so (§7.10). Pick one independent check:

1. **`site-health/deadman.sql`** (8a), Supabase only, no cost: two extensions, two Vault secrets,
   one more file. It never ran on a real project: if the test below fails, take option 2.
2. **A heartbeat service** (8b; `<service>`, such as healthchecks.io), any host, normally free for
   one check: it e-mails its own alarm after about 10 minutes without the ping that
   `HEARTBEAT_URL` gets after every probe round.
3. **`site-health/watchdog.py`** (8c), a second always-on service (`<host 2>`, preferably another
   provider), normally paid monthly, with `NTFY_TOPIC` in its own settings; or a cron job every 5
   minutes.

Options 2 and 3 bring a new account, and option 3 a monthly cost: before 8b or 8c ask the owner
(one question: what it is for, that it is normally free or paid monthly, that it can be removed).

**8a**, option 1 (send `deadman.sql` with it):

```text
עוד צעד אחד ב-Supabase: שומר שבודק שהמדידה עצמה לא נעצרה. אם השרת הקטן מפסיק לעבוד, השומר שולח לך הודעה.

1. ב-Supabase מחפשים את העמוד של התוספים למסד הנתונים (Integrations או Extensions) ומפעילים שניים: Cron ו-pg_net.
2. מחפשים את הכספת (Vault) ומוסיפים בה שני סודות:
   - שם: sh_ntfy_topic. ערך: שם הערוץ מהאפליקציה ntfy.
   - שם: sh_dashboard_url. ערך: <address>
3. את הקובץ deadman.sql ששלחתי פותחים, מעתיקים ומריצים כמו את install.sql.

מה עושים עכשיו: לכתוב לי אם ההרצה הסתיימה בלי שגיאה, או להעתיק לי את השגיאה.
```

**8b**, option 2:

```text
עוד שמירה אחת: שירות בחוץ שמצפה לסימן חיים מהשרת הקטן כל דקה. אם הסימנים נעצרים, הוא שולח לך מייל.

1. נכנסים לאתר של <service> ופותחים חשבון. לבדיקה אחת התוכנית החינמית בדרך כלל מספיקה.
2. יוצרים בדיקה חדשה (Check): מרווח (Period) של דקה אחת, וזמן המתנה (Grace) של 10 דקות.
3. מעתיקים את הכתובת של הבדיקה (Ping URL). ב-<host>, במשתני הסביבה, מוסיפים משתנה בשם HEARTBEAT_URL והכתובת היא הערך. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי". את הכתובת לא שולחים לי.
```

**8c**, option 3:

```text
עוד שמירה אחת: שירות קטן נוסף שבודק כל דקה שהשרת הראשון עובד, ושולח לטלפון הודעה אם הוא נעצר. גם הוא עובד כל הזמן, ולכן גם הוא בדרך כלל בתשלום חודשי. עדיף ספק אחר, כדי שתקלה אצל <host> לא תעצור את שניהם.

1. ב-<host 2> יוצרים שירות חדש שעובד ברקע (בדרך כלל Background Worker) ומחברים אותו למאגר <repository name>.
2. את תיקיית הבסיס ואת פקודת הבנייה ממלאים כמו בשרת הראשון. בפקודת ההפעלה (Start Command) כותבים: python3 watchdog.py --dashboard <address> --loop
3. במשתני הסביבה של השירות החדש מוסיפים משתנה בשם NTFY_TOPIC, ושם הערוץ מהאפליקציה ntfy הוא הערך. שומרים.

מה עושים עכשיו: לכתוב לי "שמרתי".
```

**The test** (go-live checklist, item 3). Only the owner can stop the service:

```text
בדיקה אחרונה: עוצרים את השרת בכוונה ל-16 דקות, כדי לראות שמגיעה הודעה כשהמדידה נעצרת. בזמן הזה המסך לא נפתח, וזה מתוכנן.

1. ב-<host> עוצרים את השירות (בדרך כלל Suspend או Stop).
2. מחכים 16 דקות. בטלפון אמורה להגיע ההודעה "המדידה נעצרה: בודק זמינות האתר".
3. מפעילים את השירות מחדש. תוך כמה דקות מההפעלה אמורה להגיע ההודעה "חזר לתקין: בודק זמינות האתר".

מה עושים עכשיו: לכתוב לי אילו הודעות הגיעו לטלפון, ובאיזו שעה.
```

**Confirm:** what the owner reports (option 2: that service's own alarm and "up again"; adapt the
message); `/health` stops answering, then shows a `last_probe_age_sec` under 90 within a few
minutes of the start. With option 1 the recovery push comes from the server: proof of its topic too.

## Step 9. The add-on on the site

**Who:** whoever can install a plugin on the site or paste a snippet into its theme (intake row 12,
§7.7); the owner forwards your message.

- **WordPress.** In `site-health/`: `python3 manage.py rum-plugin --endpoint <address>/m --out site-health-rum.zip`
  (the live host comes from the configuration). Send the ZIP with 9a.
- **Shopify.** Copy `site-health/rum/site-health-rum.liquid`, fill its two `assign` lines
  (`<address>/m`, the shop's public host without `www`), send the copy with 9b. It never ran in a
  real shop: the message says so.
- **Any other site.** Its developer adds one line and the script (§7.7, Delivery).

**9a**, WordPress:

```text
הצעד האחרון הוא באתר עצמו: תוסף קטן שמודד כמה מהר העמודים נטענים אצל הגולשים. אם מישהו אחר מנהל את האתר, מעבירים לו את ההודעה ואת הקובץ.

1. שומרים במחשב את הקובץ site-health-rum.zip ששלחתי, בלי לפתוח אותו.
2. בניהול האתר (וורדפרס) נכנסים לתוספים, בוחרים להוסיף תוסף חדש ואז להעלות תוסף. בוחרים את הקובץ, מתקינים ומפעילים.
3. אם באתר יש תוסף מטמון (cache), מנקים את המטמון. אם יש תוסף או הגדרה שמשהים טעינה של JavaScript (Delay JavaScript), מוסיפים לרשימת החריגים שלהם את site-health-rum.
4. התוסף לא מודד את מי שמחובר לניהול האתר. לכן פותחים חלון גלישה בסתר (או טלפון שלא מחובר לניהול), נכנסים לעמוד רגיל באתר (לא הסל ולא הקופה), מוסיפים בסוף הכתובת ?sh_test=1, מחכים שהעמוד ייטען וסוגרים אותו.

מה עושים עכשיו: לפתוח את המסך ולכתוב לי מה כתוב בריבוע "מהירות אצל לקוחות, שעה אחרונה".
```

**9b**, Shopify:

```text
הצעד האחרון הוא בחנות עצמה: קטע קוד קטן שמודד כמה מהר העמודים נטענים אצל הגולשים. הוא עוד לא נוסה בחנות אמיתית, ולכן בסוף בודקים יחד שהוא עובד.

1. בניהול החנות נכנסים לחנות המקוונת (Online Store) ואז לערכות העיצוב (Themes). ליד הערכה הפעילה פותחים את התפריט (שלוש נקודות) ובוחרים לשכפל אותה (Duplicate), לגיבוי.
2. באותו תפריט בוחרים לערוך את הקוד (Edit code) ופותחים את הקובץ theme.liquid שבתיקייה layout.
3. קרוב לסוף הקובץ מחפשים את השורה </body>. בשורה שמעליה מדביקים את כל התוכן של הקובץ site-health-rum.liquid ששלחתי, ושומרים.
4. פותחים את החנות עצמה בחלון חדש (לא מתוך עורך העיצוב), נכנסים לעמוד רגיל (לא הסל ולא הקופה), מוסיפים בסוף הכתובת ?sh_test=1, מחכים שהעמוד ייטען וסוגרים אותו.

מה עושים עכשיו: לפתוח את המסך ולכתוב לי מה כתוב בריבוע "מהירות אצל לקוחות, שעה אחרונה".
```

**Confirm:** `curl -s <site>/ | grep -c 'site-health-rum'` prints 1 or more, and the owner reads the
tile: a count, and "מתוכן מדידת בדיקה אחת". Nothing within a minute, most likely first (§7.7): (1)
the tester was signed in to the site's admin (WordPress leaves the script out for editors) or used
the theme editor (Shopify): the last item again, in a private window or on a phone that is not
signed in; (2) a Content-Security-Policy header (`curl -sI <site>/`) must allow `<address>` in
`connect-src` and the inline script in `script-src`; (3) the page cache was not purged, or a "delay
JavaScript" optimisation holds the script back.

Then **9c**, what the add-on sends: whether the privacy policy needs the sentence is the owner's call.

```text
כדאי לדעת: מעכשיו, בכל פעם שגולש פותח עמוד באתר, הדפדפן שלו שולח למסך בריאות האתר שני דברים: איזה עמוד נפתח וכמה זמן לקח לו להיטען. שום פרט שמזהה את הגולש לא נשלח ולא נשמר.

אם לאתר יש מדיניות פרטיות, אפשר להוסיף לה את המשפט הזה:
"האתר מודד את מהירות הטעינה של העמודים. בכל צפייה בעמוד נשלחים לשירות המדידה של האתר כתובת העמוד וזמן הטעינה שלו, בלי שום פרט שמזהה את הגולש."

ההחלטה אם להוסיף אותו היא שלך.

מה עושים עכשיו: אין צורך לעשות דבר, אלא אם מחליטים להוסיף את המשפט.
```

## Step 10. The hand-over note

**Who:** you, when the §10 checklist is green. Fill every `<…>`, leave out what does not apply (no
certificate check, no watchdog push with option 2), and keep it one note.

```text
המסך "בריאות האתר" מוכן. כדאי לשמור את ההודעה הזאת.

הכתובת: <address>/site. נכנסים עם הסיסמה שקבעת.

הצבעים: ירוק זה תקין. צהוב זה לשים לב. אדום זה תקלה. אפור זה שעדיין אין נתון.

ההודעות מגיעות באפליקציה ntfy. כדי לצרף טלפון: מתקינים בו את האפליקציה, לוחצים על הפלוס ומקלידים את שם הערוץ. הודעה מחכה לטלפון 12 שעות: טלפון שהיה כבוי יותר מזה לא יקבל אותה. כל ההודעות נשמרות גם במסך, בכרטיס "הודעות שנשלחו לטלפון". באייפון הודעה מגיעה לפעמים באיחור.

מה עושים כשמגיעה הודעה:
- "האתר לא עונה": פותחים את העמוד בטלפון. אם הוא לא נפתח, פונים למי שמאחסן את האתר. כשכל האתר נופל מגיעה הודעה על כל עמוד שנבדק, <N> הודעות, אבל זו תקלה אחת.
- "עמוד איטי": לא דחוף. אם זה חוזר, מעבירים למי שמתחזק את האתר.
- "תעודת האבטחה פגה בעוד…": מעבירים באותו יום למי שמאחסן את האתר. כשהתעודה פגה, הגולשים רואים אזהרה במקום את האתר.
- "המדידה נעצרה": האתר כנראה תקין, אבל הבודק הפסיק לעבוד, וייתכן שגם המסך לא נפתח. בודקים ב-<host> שהשירות פועל, ואם לא ברור מה קרה, כותבים לקודקס: "בריאות האתר: המדידה נעצרה".
- "חזר לתקין": התקלה נגמרה. אין צורך לעשות דבר.
- "בוקר טוב": סיכום יומי. הוא גם הסימן שההודעות עובדות: אם בוקר אחד הוא לא מגיע, משהו נעצר.

אי אפשר להשתיק את ההודעות מתוך המסך. לפני עבודה מתוכננת על האתר אפשר להשתיק את הערוץ באפליקציה לכמה שעות.

החשבונות שנפתחו, כולם על השם שלך:
- Supabase: המדידות.
- GitHub: הקוד, במאגר פרטי.
- <host>: השרת הקטן, בתשלום חודשי. במשתני הסביבה שלו שמורים הסיסמאות, המפתח של גוגל ושם הערוץ.
- גוגל: המפתח למדידת המהירות.
- <Supabase, בכספת (Vault) | <service> | <host 2>>: השומר שבודק שהשרת עובד<. גם שם שמור שם הערוץ>.
כדי להחליף סיסמה, משנים את הערך שלה ב-<host> ושומרים. מי שנכנס עם הסיסמה הישנה יתבקש להיכנס מחדש.

כדי לשנות משהו, כותבים לקודקס בתיקייה של הפרויקט, למשל: "בריאות האתר: להוסיף עמוד לבדיקה, <כתובת>". חשוב: אם מוחקים מהאתר עמוד שנבדק או משנים את הכתובת שלו, מגיעה הודעה "האתר לא עונה" עד שכותבים על זה לקודקס.

מה עושים עכשיו: לשמור את ההודעה הזאת.
```

Later requests: read `START-HERE.md` and `PROGRESS.md` first. Pages or settings: change
`site_health.config.json`, write `install.sql`, send 2b (a new page list is picked up within five
minutes). People: 6b, or a variable the owner deletes. There is no pause for alerts.

<!-- EOF OWNER-STEPS.md -->
