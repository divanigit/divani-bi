"""Site Health: a small command line for whoever deploys the reference.

    python3 manage.py init-db                 apply schema.sql, then functions.sql (over DATABASE_URL)
    python3 manage.py setup <config.json>     load the site's configuration (sh_setup); safe to repeat
    python3 manage.py check                   the database, the configuration, every flow, which keys are set
    python3 manage.py run-once <collector>    one run of one collector, printing what it stored
    python3 manage.py test-push               one push to the real topic that says it is a test
    python3 manage.py new-secret              a fresh ntfy topic name and a fresh share token

It reads the same environment as the server and the collectors, and never prints a value of it.
"""
import argparse
import json
import os
import pathlib
import secrets
import string
import sys
from datetime import datetime, timezone

import collectors
import db

HERE = pathlib.Path(__file__).resolve().parent
ENVIRONMENT = (
    ("the database", ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATABASE_URL")),
    ("the collectors", ("PAGESPEED_KEY", "NTFY_TOPIC", "NTFY_URL", "NTFY_TOKEN", "DASHBOARD_URL", "HEARTBEAT_URL")),
    ("the server", ("SH_PASS_OWNER", "SH_PASS_STAFF", "SH_SHARE_TOKEN", "SH_VENDOR_NOALERTS", "SH_PROXY_HOPS",
                    "SH_SCREEN", "COLLECTORS")),
)
TEST_PUSH = ("בדיקה: בריאות האתר", "זו הודעת בדיקה של מערכת בריאות האתר. אין שום תקלה, ואין צורך לעשות דבר.")


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=1, default=str))


def init_db(args):
    if not os.environ.get("DATABASE_URL"):
        if os.environ.get("SUPABASE_URL"):
            sys.exit("Only SUPABASE_URL is set, and the REST interface cannot create tables.\n"
                     "Open the project's SQL editor and run the two files, in this order:\n"
                     "  1. %s\n  2. %s\n"
                     "(or set DATABASE_URL to the project's connection string and run init-db again)"
                     % (HERE / "schema.sql", HERE / "functions.sql"))
        sys.exit("DATABASE_URL is not set: nothing to apply the SQL files to.")
    import psycopg                              # only this command and db.py's Postgres transport need the driver

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        for name in ("schema.sql", "functions.sql"):            # each file is one command of many statements
            connection.execute((HERE / name).read_text(encoding="utf-8"))
            print("applied", name)
    print("Next: python3 manage.py setup site_health.config.json")


def setup(args):
    with open(args.config, encoding="utf-8") as f:
        config = db.rpc("sh_setup", {"p_config": json.load(f)})
    print("%s is set up: time zone %s, platform %s, %d probe pages, %d core pages" % (
        config["site"], config["time_zone"], config["platform"],
        sum(1 for page in config["pages"] if page["probe"]), sum(1 for page in config["pages"] if page["core"])))


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
    print("flows:")
    for flow in flows:
        print("  %-8s %s (last run: %s)" % (flow["status"], flow["flow_name"], flow["last_at"] or "never"))


def run_once(args):
    config = collectors.read_config()
    if config is None:
        sys.exit("The site is not configured. Load a configuration first: python3 manage.py setup <config.json>")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    key = os.environ.get("PAGESPEED_KEY", "").strip()
    if args.collector.startswith("speed") and not key:
        sys.exit("PAGESPEED_KEY is not set: the speed collectors cannot run.")
    runs = {
        "probe": lambda: collectors.probe_round(config.probe, "full", now),
        "probe-light": lambda: collectors.probe_round(config.probe, "light", now),
        "alerts": lambda: collectors.alert_tick(collectors.Pusher()),
        "speed-core": lambda: collectors.speed_core(config.core, "mobile", now, key),
        "speed-desktop": lambda: collectors.speed_core(config.core, "desktop", now, key),
        "speed-rotation": lambda: collectors.speed_rotation(collectors.ROTATION_PAGES, now, key),
        "sitemap": lambda: collectors.sitemap_job(config, now),
        "catalogue": lambda: collectors.catalogue_job(config, now),
        "cert": lambda: collectors.cert_job(config, now),
        "morning": lambda: collectors.morning_job(config, now),
        "cleanup": lambda: collectors.cleanup_job(config, now),
    }
    try:
        _print(runs[args.collector]())
    except (collectors.CollectorError, collectors.SpeedStopped, db.DbError, OSError) as e:
        sys.exit("%s failed: %s" % (args.collector, e))


def test_push(args):
    if not os.environ.get("NTFY_TOPIC", "").strip():
        sys.exit("NTFY_TOPIC is not set: there is nowhere to push to.")
    status = collectors.Pusher().publish(*TEST_PUSH, priority=3, tags=["bell"])      # straight to ntfy: no row stored
    print("ntfy answered %d: %s" % (status, "accepted. That is not yet proof that a phone showed it: look at the phone."
                                    if status == 200 else "NOT accepted."))
    sys.exit(0 if status == 200 else 1)


def new_secret(args):
    letters = string.ascii_letters + string.digits
    print("NTFY_TOPIC=sh-%s" % "".join(secrets.choice(letters) for _ in range(24)))
    print("SH_SHARE_TOKEN=%s" % secrets.token_urlsafe(24))
    print("Paste them into the host's environment settings. They are secrets: never into the repository or a chat.",
          file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db").set_defaults(run=init_db)
    commands.add_parser("setup").set_defaults(run=setup)
    commands.choices["setup"].add_argument("config", help="the site's site_health.config.json")
    commands.add_parser("check").set_defaults(run=check)
    commands.add_parser("run-once").set_defaults(run=run_once)
    commands.choices["run-once"].add_argument("collector", choices=[
        "probe", "probe-light", "alerts", "speed-core", "speed-desktop", "speed-rotation", "sitemap", "catalogue",
        "cert", "morning", "cleanup"])
    commands.add_parser("test-push").set_defaults(run=test_push)
    commands.add_parser("new-secret").set_defaults(run=new_secret)
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except db.DbError as e:
        sys.exit("database: %s" % e)


if __name__ == "__main__":
    main()
