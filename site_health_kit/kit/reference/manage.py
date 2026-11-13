"""Site Health: a small command line for whoever deploys the reference.

Commands that need no database and no secret (they only write a file):

    python3 manage.py install-sql --config site_health.config.json --out install.sql
                                              one SQL file: schema.sql, functions.sql and the site's
                                              configuration. The owner pastes it into the database's SQL
                                              editor and runs it once. Safe to run again.
    python3 manage.py rum-plugin --endpoint https://<dashboard>/m --out site-health-rum.zip
                                              the real-user script as a WordPress plugin, ready to upload
    python3 manage.py new-secret --out <file outside the repository>
                                              a fresh ntfy topic name and a fresh share token, written to
                                              that file and never printed. For the owner, not for an agent.

Commands that reach the database (the same environment as the server and the collectors):

    python3 manage.py init-db                 apply schema.sql, then functions.sql (over DATABASE_URL)
    python3 manage.py init-db --file install.sql      apply that one file instead: the rehearsal of install-sql
    python3 manage.py setup <config.json>     load the site's configuration (sh_setup); safe to repeat
    python3 manage.py check                   the database, the configuration, every flow, which keys are set
    python3 manage.py run-once <collector>    one run of one collector, printing what it measured and stored
    python3 manage.py test-push               one push to the real topic that says it is a test

No command prints the value of an environment variable, a topic or a token.
"""
import argparse
import json
import os
import pathlib
import re
import secrets
import string
import sys
import urllib.parse
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

import collectors
import db

HERE = pathlib.Path(__file__).resolve().parent
ENVIRONMENT = (
    ("the database", ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATABASE_URL")),
    ("the collectors", ("PAGESPEED_KEY", "NTFY_TOPIC", "NTFY_URL", "NTFY_TOKEN", "DASHBOARD_URL", "HEARTBEAT_URL",
                        "PAGESPEED_URL", "SH_ALLOW_PRIVATE", "SH_SITEMAP_MB")),
    ("the server", ("SH_PASS_OWNER", "SH_PASS_STAFF", "SH_SHARE_TOKEN", "SH_VENDOR_NOALERTS", "SH_PROXY_HOPS",
                    "SH_SCREEN", "SH_RUM_PER_MINUTE", "SH_RUM_PER_DAY", "COLLECTORS")),
)
TEST_PUSH = ("בדיקה: בריאות האתר", "זו הודעת בדיקה של מערכת בריאות האתר. אין שום תקלה, ואין צורך לעשות דבר.")
PLUGIN = "site-health-rum"                      # the plugin's folder and file inside the ZIP
PLUGIN_DEFAULTS = ("define('SITE_HEALTH_RUM_ENDPOINT', '');", "define('SITE_HEALTH_RUM_LIVE_HOST', '');")
URL_TEXT = re.compile(r"[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+")      # no quote, no backslash, no space
HOST_TEXT = re.compile(r"[a-z0-9.-]+")


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=1, default=str))


def _config_file(path):
    """The site's configuration file as a dict, or one line that says what is wrong with it."""
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except OSError as e:
        sys.exit("%s cannot be read: %s" % (path, e.strerror or e))
    except ValueError as e:
        sys.exit("%s is not valid JSON: %s" % (path, e))
    if not isinstance(config, dict):
        sys.exit("%s must hold one JSON object, the site's configuration" % path)
    return config


# ---------------------------------------------------------------- the database

def init_db(args):
    if not os.environ.get("DATABASE_URL"):
        if os.environ.get("SUPABASE_URL"):
            sys.exit("Only SUPABASE_URL is set, and the REST interface cannot create tables.\n"
                     "Write the one file for the project's SQL editor (schema.sql, then functions.sql, then the\n"
                     "site's configuration) and have the owner run it there:\n"
                     "  python3 manage.py install-sql --config site_health.config.json --out install.sql\n"
                     "(or set DATABASE_URL to the project's connection string and run init-db again)")
        sys.exit("DATABASE_URL is not set: nothing to apply the SQL files to.")
    import psycopg                              # only this command and db.py's Postgres transport need the driver

    files = [pathlib.Path(args.file)] if args.file else [HERE / "schema.sql", HERE / "functions.sql"]
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
            for path in files:                  # each file is one command of many statements
                connection.execute(path.read_text(encoding="utf-8"))
                print("applied", path.name)
    except OSError as e:
        sys.exit("init-db failed: %s cannot be read (%s)" % (args.file, e.strerror or e))
    except psycopg.Error as e:
        sys.exit("init-db failed: %s" % str(e).splitlines()[0])
    if not args.file:
        print("Next: python3 manage.py setup site_health.config.json")


def _config_problem(config):
    """What sh_setup would refuse and can be told without a database, or None. The database has the
    last word: rehearse the finished file on a scratch database (init-db --file)."""
    site = urllib.parse.urlsplit(str(config.get("site") or ""))
    if site.scheme not in ("http", "https") or not site.hostname:
        return '"site" must be an absolute http(s) address'
    zone = config.get("time_zone")
    if not isinstance(zone, str) or not zone:
        return '"time_zone" is required: the time zone of the site\'s customers, such as Asia/Jerusalem'
    try:
        ZoneInfo(zone)
    except (ValueError, OSError, KeyError):     # unknown; unless this machine knows no time zone at all
        if available_timezones():
            return 'unknown "time_zone" %s' % zone
    pages = config.get("pages")
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        return '"pages" must be a list of pages'
    homes = [page for page in pages if page.get("home") is True]
    if len(homes) != 1:
        return 'exactly one page must have "home": true, found %d' % len(homes)
    if not (homes[0].get("probe") is True and homes[0].get("core") is True):
        return "the home page must be a probe page and a core page"
    return None


def install_sql(args):
    """One file for the SQL editor of the database: nothing here connects anywhere or holds a secret."""
    config = _config_file(args.config)
    problem = _config_problem(config)
    if problem:
        sys.exit("%s: %s" % (args.config, problem))
    text = json.dumps(config, ensure_ascii=False, indent=1)
    quote = "$sh_config$"                       # dollar quoting: the JSON goes in as it is, whatever it holds
    while quote in text:
        quote = "$sh_config_%s$" % secrets.token_hex(4)
    parts = [
        "-- Site Health: everything the database needs, in one file.",
        "-- Written by: python3 manage.py install-sql   (do not edit it; write it again after a change)",
        "--",
        "-- It holds no secret. Paste ALL of it into the SQL editor of the database and run it once.",
        "-- The result ends with the line:  Site Health is installed for <the site's address>",
        "-- Running it again is harmless: nothing that was measured is deleted.",
        "",
        "-- ============================================================ 1 of 3: schema.sql",
        (HERE / "schema.sql").read_text(encoding="utf-8").rstrip("\n"),
        "",
        "-- ============================================================ 2 of 3: functions.sql",
        (HERE / "functions.sql").read_text(encoding="utf-8").rstrip("\n"),
        "",
        "-- ============================================================ 3 of 3: the site's configuration",
        "select 'Site Health is installed for ' || (sh_setup(%s%s%s::jsonb) ->> 'site') as result;" % (quote, text, quote),
        "",
    ]
    out = pathlib.Path(args.out)
    body = "\n".join(parts)
    out.write_text(body, encoding="utf-8")
    print("wrote %s: schema.sql, functions.sql and the configuration of %s (%d lines, %d KB, no secret in it)"
          % (out, config["site"], body.count("\n"), len(body.encode("utf-8")) // 1024 + 1))
    print("Rehearse it on a scratch database, twice:  DATABASE_URL=<a scratch database> python3 manage.py init-db "
          "--file %s" % out)
    print("Then the owner pastes all of it into the SQL editor of the real database and runs it. The result must "
          "end with:  Site Health is installed for %s" % config["site"])


def setup(args):
    config = db.rpc("sh_setup", {"p_config": _config_file(args.config)})
    off = config.get("off") or []
    print("%s is set up: time zone %s, platform %s, %d probe pages, %d core pages%s" % (
        config["site"], config["time_zone"], config["platform"],
        sum(1 for page in config["pages"] if page["probe"]), sum(1 for page in config["pages"] if page["core"]),
        ", switched off: %s" % ", ".join(off) if off else ""))


def check(args):
    for group, names in ENVIRONMENT:
        if group == "the server":               # one password variable per vendor
            names += tuple(sorted(name for name in os.environ if name.startswith("SH_PASS_VENDOR_")))
        print("%s: %s" % (group, ", ".join(
            "%s %s" % (name, "is set" if os.environ.get(name, "").strip() else "is NOT set") for name in names)))
    try:
        db.rpc("sh_ping")
        config = collectors.read_config()
        flows = db.rpc("sh_health") or []
    except db.DbError as e:
        sys.exit("database: NOT reachable (%s)" % e)
    print("database: reachable")
    if config is None:
        sys.exit("configuration: none yet. Load one: python3 manage.py setup site_health.config.json")
    print("configuration: %s, time zone %s, platform %s, morning message at %02d:%02d" % (
        config.site, config.zone.key, config.platform, *config.morning))
    print("  probe pages (every minute): %s" % ", ".join(page["name"] for page in config.probe))
    print("  core pages (speed): %s" % ", ".join(page["name"] for page in config.core))
    print("  switched off: %s" % (", ".join(sorted(config.off)) or "nothing"))
    print("flows:")
    for flow in flows:
        print("  %-8s %s (last run: %s)" % (flow["status"], flow["flow_name"], flow["last_at"] or "never"))


def run_once(args):
    config = collectors.read_config()
    if config is None:
        sys.exit("The site is not configured. Load a configuration first: python3 manage.py setup <config.json>")
    off = collectors.job_off(args.collector, config)
    if off:                                     # as the scheduler: a part that is off stores nothing, by hand either
        print("skipped: %s" % off)
        return
    now = datetime.now(timezone.utc)
    key = os.environ.get("PAGESPEED_KEY", "").strip()
    if args.collector.startswith("speed") and not key:
        sys.exit("PAGESPEED_KEY is not set: the speed collectors cannot run.")

    def slot(seconds):
        # A round by hand is stored under the same scheduled moment as the scheduler's own, so it
        # can never add a second round to a minute or a second run to a quarter of an hour.
        return datetime.fromtimestamp(now.timestamp() // seconds * seconds, timezone.utc)

    runs = {
        "probe": lambda: collectors.probe_round(config.probe, "full", slot(60), hosts=config.hosts),
        "alerts": lambda: collectors.alert_tick(collectors.Pusher()),
        "speed-core": lambda: collectors.speed_core(config.core, "mobile", slot(900), key),
        "speed-desktop": lambda: collectors.speed_core(config.core, "desktop", slot(3600), key),
        "speed-rotation": lambda: collectors.speed_rotation(collectors.ROTATION_PAGES, slot(300), key),
        "sitemap": lambda: collectors.sitemap_job(config, now),
        "catalogue": lambda: collectors.catalogue_job(config, now),
        "cert": lambda: collectors.cert_job(config, now),
        "morning": lambda: collectors.morning_job(config, now),
        "cleanup": lambda: collectors.cleanup_job(config, now),
    }
    try:
        _print(runs[args.collector]())
    except (collectors.CollectorError, collectors.SpeedStopped, db.DbError, OSError, ValueError) as e:
        sys.exit("%s failed: %s" % (args.collector, e))


def test_push(args):
    if not os.environ.get("NTFY_TOPIC", "").strip():
        sys.exit("NTFY_TOPIC is not set: there is nowhere to push to.")
    status = collectors.Pusher().publish(*TEST_PUSH, priority=3, tags=["bell"])      # straight to ntfy: no row stored
    print("ntfy answered %d: %s" % (status, "accepted. That is not yet proof that a phone showed it: look at the phone."
                                    if status == 200 else "NOT accepted."))
    sys.exit(0 if status == 200 else 1)


# ---------------------------------------------------------------- files for the owner

def new_secret(args):
    """Two fresh secrets into a file, never onto the terminal: a terminal is somebody's transcript."""
    if not args.out:
        sys.exit("new-secret writes two secrets, an ntfy topic name and a share token, and never prints them.\n"
                 "Name a file outside the repository for them:  python3 manage.py new-secret --out <file>\n"
                 "This is for the site's owner, on their own computer (spec §7.9): an agent never reads that file.")
    letters = string.ascii_letters + string.digits
    lines = ["NTFY_TOPIC=sh-%s" % "".join(secrets.choice(letters) for _ in range(24)),
             "SH_SHARE_TOKEN=%s" % secrets.token_urlsafe(24)]
    path = pathlib.Path(args.out)
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)        # for the owner's eyes only
    except FileExistsError:
        sys.exit("%s exists already and is not overwritten: name another file, or delete it first." % path)
    except OSError as e:
        sys.exit("%s cannot be written: %s" % (path, e.strerror or e))
    with os.fdopen(handle, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote NTFY_TOPIC and SH_SHARE_TOKEN to %s (their values are not shown here)" % path)
    print("The owner opens the file, pastes each value into the host's settings and the topic into the ntfy app "
          "of every phone, and then deletes the file. Never into the repository or a chat.")
    if any((folder / ".git").exists() for folder in path.resolve().parents):
        print("WARNING: that file is inside a git repository. Do not commit it: move it out, or delete it as soon "
              "as the values are pasted.")


def rum_plugin(args):
    """The real-user script as a WordPress plugin that is uploaded in the admin screen: the two values
    it needs are written into the plugin's own defaults, so nobody edits wp-config.php."""
    endpoint = urllib.parse.urlsplit(args.endpoint.strip())
    local = endpoint.scheme == "http" and endpoint.hostname in ("127.0.0.1", "localhost")
    if not URL_TEXT.fullmatch(args.endpoint.strip()) or not endpoint.hostname or not (endpoint.scheme == "https" or local):
        sys.exit("--endpoint must be the https address of the dashboard's ingest, such as https://dash.example.co.il/m")
    address = urllib.parse.urlunsplit(endpoint) if endpoint.path not in ("", "/") else "%s://%s/m" % (
        endpoint.scheme, endpoint.netloc)
    live = args.live_host
    if not live:
        source = args.config or "site_health.config.json"
        if not os.path.isfile(source):
            sys.exit("Which site is the live one? Name it with --live-host example.co.il, or point --config at the "
                     "site's site_health.config.json (%s was not found)." % source)
        live = urllib.parse.urlsplit(str(_config_file(source).get("site") or "")).hostname or ""
    live = live.strip().lower().removeprefix("www.")
    if not HOST_TEXT.fullmatch(live):
        sys.exit("the live host must be a host name such as example.co.il, got %r" % live)
    php = (HERE / "rum" / (PLUGIN + ".php")).read_text(encoding="utf-8")
    for default, value in zip(PLUGIN_DEFAULTS, (address, live)):
        if php.count(default) != 1:
            sys.exit("rum/%s.php no longer holds the line %s" % (PLUGIN, default))
        php = php.replace(default, default.replace("''", "'%s'" % value))
    entry = zipfile.ZipInfo("%s/%s.php" % (PLUGIN, PLUGIN), date_time=(2026, 1, 1, 0, 0, 0))
    entry.compress_type, entry.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
    with zipfile.ZipFile(args.out, "w") as archive:
        archive.writestr(entry, php)
    print("wrote %s: the WordPress plugin \"Site Health RUM\", sending to %s, live host %s" % (args.out, address, live))
    print("The owner installs it in the site's admin: Plugins > Add new > Upload plugin > this file > Install > "
          "Activate. Then they purge the page cache. Nobody edits wp-config.php.")
    print("To see it work: open a page of the site with ?sh_test=1 at the end of its address, leave the page, and "
          "look at \"מהירות אצל לקוחות\" on the screen within a minute.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db").set_defaults(run=init_db)
    commands.choices["init-db"].add_argument("--file", help="apply this one SQL file (the output of install-sql)")
    commands.add_parser("install-sql").set_defaults(run=install_sql)
    commands.choices["install-sql"].add_argument("--config", required=True, help="the site's site_health.config.json")
    commands.choices["install-sql"].add_argument("--out", default="install.sql", help="the file to write")
    commands.add_parser("setup").set_defaults(run=setup)
    commands.choices["setup"].add_argument("config", help="the site's site_health.config.json")
    commands.add_parser("check").set_defaults(run=check)
    commands.add_parser("run-once").set_defaults(run=run_once)
    commands.choices["run-once"].add_argument("collector", choices=[
        "probe", "alerts", "speed-core", "speed-desktop", "speed-rotation", "sitemap", "catalogue", "cert", "morning",
        "cleanup"])
    commands.add_parser("test-push").set_defaults(run=test_push)
    commands.add_parser("new-secret").set_defaults(run=new_secret)
    commands.choices["new-secret"].add_argument("--out", help="the file the two secrets are written to")
    commands.add_parser("rum-plugin").set_defaults(run=rum_plugin)
    commands.choices["rum-plugin"].add_argument("--endpoint", required=True, help="https://<the dashboard>/m")
    commands.choices["rum-plugin"].add_argument("--live-host", help="the production host, such as example.co.il")
    commands.choices["rum-plugin"].add_argument("--config", help="take the live host from this configuration file")
    commands.choices["rum-plugin"].add_argument("--out", default=PLUGIN + ".zip", help="the ZIP file to write")
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except db.DbError as e:
        sys.exit("database: %s" % e)


if __name__ == "__main__":
    main()
