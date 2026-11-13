"""Tests of schema.sql and functions.sql: the rules of spec §7.2, §7.3, §7.4 and §7.8, with exact values.
And of deadman.sql, against stand-ins for the three Supabase extensions it needs.

    cd reference && python3 -m pytest -q tests/test_sql.py

The kit's fake backend (mock_server.py) is imported for its shapes: see _kit_dir() below for
where it is looked for, and set SH_KIT_DIR when the tests run in a copy of reference/.

Time. Tests of the window functions use fixed moments in the past: T0 is 09:00 in Jerusalem,
the time zone of the example configuration. Tests of the "now" functions place their rows
relative to db.now(), which stands still inside a test (see conftest.db).
"""
import datetime as dt
import decimal
import math
import os
import pathlib
import re
import sys
import threading
import time
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.types.json import Jsonb

import sim
from conftest import REFERENCE, TIMINGS, apply_sql, example_config



def _kit_dir():
    """The folder of the unpacked kit, where mock_server.py lives: $SH_KIT_DIR; else the parent of
    reference/ (the tests run inside the kit); else site-health-kit next to a copy of reference/."""
    named = os.environ.get("SH_KIT_DIR")
    places = [pathlib.Path(named)] if named else [REFERENCE.parent, REFERENCE.parent / "site-health-kit"]
    for place in places:
        if (place / "mock_server.py").is_file():
            return place
    raise RuntimeError("the kit's mock_server.py was not found in %s: set SH_KIT_DIR to the folder of the"
                       " unpacked kit (site-health-kit)" % " or ".join(str(place) for place in places))


sys.path.insert(0, str(_kit_dir()))
import mock_server as mock  # noqa: E402  (the kit's fake backend: the contract by example)

UTC = dt.timezone.utc
TZ = ZoneInfo("Asia/Jerusalem")
T0 = dt.datetime(2024, 11, 12, 7, 0, tzinfo=UTC)          # 12.11 09:00 in Jerusalem
SITE = "https://example.co.il"
URL = {"בית": SITE + "/", "קטגוריה": SITE + "/product-category/sofas/", "מוצר": SITE + "/product/sample-sofa/",
       "סל": SITE + "/cart/", "אודות": SITE + "/about/"}
PROBE = ["בית", "קטגוריה", "מוצר", "סל"]
DEAD = dict.fromkeys(PROBE, "timeout")
# The seven flows: name and cadence as the mock shows them, warn and late minutes as spec §7.3 lists them.
LATE = [(5, 15), (45, 90), (20, 60), (1560, 2880), (1560, 2880), (1560, 2880), (360, 1440)]
FLOWS = [(name, cadence, warn, late) for (name, cadence, *_), (warn, late) in zip(mock.FLOWS, LATE, strict=True)]
PROBE_FLOW, CORE_FLOW, ROTATION_FLOW, SITEMAP_FLOW, CERT_FLOW, CATALOGUE_FLOW, RUM_FLOW = (f[0] for f in FLOWS)


def mins(n):
    return dt.timedelta(minutes=n)


def secs(n):
    return dt.timedelta(seconds=n)


def il(at):
    return at.astimezone(TZ).strftime("%d.%m %H:%M")


def section(rows, name):
    return [r for r in rows if r["section"] == name]


def flow(db, name):
    return next(r for r in db.rpc("sh_health") if r["flow_name"] == name)


def fails_with(db, error, match, fn, **params):
    """The call must raise; the savepoint keeps the test's transaction usable afterwards."""
    with pytest.raises(error, match=match):
        with db.conn.transaction():
            db.rpc(fn, **params)


def percentile(values, p):
    """percentile_cont, written out again: the tests do not trust the database's own arithmetic."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p
    return v[math.floor(k)] + (v[math.ceil(k)] - v[math.floor(k)]) * (k - math.floor(k))


def half_up(x):
    """Rounding as SQL rounds a numeric: halves away from zero."""
    return None if x is None else int(decimal.Decimal("%.15g" % x).quantize(decimal.Decimal(1), decimal.ROUND_HALF_UP))


# ================================================================ configuration (spec §7.4)

def test_setup_loads_the_example_configuration(db):
    config = db.setup()
    assert config == db.rpc("sh_config")
    assert {k: v for k, v in config.items() if k not in ("pages", "screen")} == {
        "site": SITE, "host": "example.co.il", "label": "example.co.il", "brand": "",
        "time_zone": "Asia/Jerusalem", "platform": "woocommerce", "down_after": 1, "morning": "07:30",
        "path_labels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
        "bucket_note": "", "live_hosts": ["live"], "keep_days": 100, "rum_hosts": [], "private_paths": [],
        "off": [], "extra_hosts": [], "hide": [], "nav": [], "links": []}
    assert set(config) - {"host", "screen"} == set(example_config())      # every key of the file, as it was loaded
    assert config["pages"] == [
        {"name": "בית", "url": URL["בית"], "probe": True, "core": True, "home": True, "expect": "ברוכים הבאים"},
        {"name": "קטגוריה", "url": URL["קטגוריה"], "probe": True, "core": True, "home": False, "expect": None},
        {"name": "מוצר", "url": URL["מוצר"], "probe": True, "core": True, "home": False, "expect": "הוספה לסל"},
        {"name": "סל", "url": URL["סל"], "probe": True, "core": True, "home": False, "expect": None},
        {"name": "אודות", "url": URL["אודות"], "probe": False, "core": True, "home": False, "expect": None}]
    assert config["screen"] == {
        "siteLabel": "example.co.il", "brand": "", "homePage": "בית", "probeCount": 4, "coreCount": 5, "downAfter": 1,
        "liveHosts": ["live"], "pathLabels": [["/product-category/", "קטגוריה: "], ["/product/", "מוצר: "]],
        "bucketNote": "", "hide": [], "nav": [], "links": []}
    # the example uses the pages of the mock backend
    assert [(p["name"], p["url"]) for p in config["pages"] if p["probe"]] == [(n, SITE + path) for n, path in mock.PROBE]
    assert [(p["name"], p["url"]) for p in config["pages"] if p["core"]] == [(n, SITE + path) for n, path in mock.CORE]


def test_setup_fills_in_defaults_and_follows_the_platform(db):
    minimal = {"site": "https://www.Shop.example/", "time_zone": "Europe/London",       # the least a file may hold
               "pages": [{"name": "ראשי", "url": "https://www.shop.example/", "home": True, "probe": True, "core": True}]}
    config = db.rpc("sh_setup", p_config=minimal)
    assert {k: v for k, v in config.items() if k not in ("pages", "screen")} == {
        "site": "https://www.Shop.example", "host": "www.shop.example", "label": "shop.example", "brand": "",
        "time_zone": "Europe/London", "platform": "other", "down_after": 1, "morning": "07:30",
        "path_labels": [], "bucket_note": "", "live_hosts": ["live"], "keep_days": 100, "rum_hosts": [],
        "private_paths": [], "off": ["catalogue"], "extra_hosts": [], "hide": [], "nav": [], "links": []}
    # no catalogue: the screen hides the products card and the catalogue flow is not listed
    assert config["screen"] == {"siteLabel": "shop.example", "brand": "", "homePage": "ראשי", "probeCount": 1,
                                "coreCount": 1, "downAfter": 1, "liveHosts": ["live"], "pathLabels": [],
                                "bucketNote": "", "hide": ["issuesCard"], "nav": [], "links": []}
    assert [r["flow_name"] for r in db.rpc("sh_health")] == [f[0] for f in FLOWS if f[0] != CATALOGUE_FLOW]

    config = db.rpc("sh_setup", p_config=dict(minimal, platform="shopify", bucket_note="הערה", brand="DEMO",
                                              live_hosts=["live", "shop.example"]))
    assert config["screen"]["pathLabels"] == [["/collections/", "קטגוריה: "], ["/products/", "מוצר: "]]
    assert config["screen"]["hide"] == [] and config["screen"]["bucketNote"] == "הערה" and config["off"] == []
    assert config["screen"]["brand"] == "DEMO" and config["screen"]["liveHosts"] == ["live", "shop.example"]
    assert [r["flow_name"] for r in db.rpc("sh_health")] == [f[0] for f in FLOWS]


def _enabled(db):
    return [name for (name,) in db.sql("select flow_name from sh_flows where enabled order by sort")]


def test_setup_switches_off_the_parts_that_do_not_apply_to_the_site(db):
    """The "off" list of the configuration (decision D3): each entry disables its flows and hides its card."""
    everything = [f[0] for f in FLOWS]
    assert db.setup()["off"] == [] and _enabled(db) == everything

    db.rpc("sh_sitemap_set", p_urls=[SITE + "/a/", SITE + "/b/"])
    config = db.setup(off=["real_users", "sitemap"])                      # answered in a fixed order
    # without real-user measurements the "עכשיו" row has no tile for them: nothing reads "no data" for good
    assert config["off"] == ["sitemap", "real_users"] and config["screen"]["hide"] == ["slowCard", "nowRum"]
    assert _enabled(db) == [PROBE_FLOW, CORE_FLOW, CERT_FLOW, CATALOGUE_FLOW]
    assert [r["flow_name"] for r in db.rpc("sh_health")] == _enabled(db)   # the screen lists what is measured
    assert db.rpc("sh_rotation_next", p_n=5) == []                         # and no page takes a turn in the rotation

    config = db.setup(off=["catalogue", "cert"])
    assert config["off"] == ["catalogue", "cert"] and config["screen"]["hide"] == ["issuesCard", "certCard"]
    assert _enabled(db) == [PROBE_FLOW, CORE_FLOW, ROTATION_FLOW, SITEMAP_FLOW, RUM_FLOW]

    # what follows from the site itself needs no entry: no catalogue on "other", no certificate on http://
    plain = example_config(site="http://example.co.il", platform="other", off=["sitemap"])
    plain["pages"] = [dict(p, url=p["url"].replace("https://", "http://")) for p in plain["pages"]]
    config = db.rpc("sh_setup", p_config=plain)
    assert config["off"] == ["sitemap", "catalogue", "cert"]
    assert config["screen"]["hide"] == ["slowCard", "issuesCard", "certCard"]
    assert _enabled(db) == [PROBE_FLOW, CORE_FLOW, RUM_FLOW]
    config = db.rpc("sh_setup", p_config=dict(plain, off=["sitemap", "real_users"], hide=["nowRum", "myCard"]))
    assert config["screen"]["hide"] == ["nowRum", "myCard", "slowCard", "issuesCard", "certCard"]      # each card once
    assert _enabled(db) == [PROBE_FLOW, CORE_FLOW]
    config = db.rpc("sh_setup", p_config=plain)
    assert db.rpc("sh_config") == config

    assert db.setup()["off"] == [] and _enabled(db) == everything          # the entry left the file: on again
    assert db.rpc("sh_rotation_next", p_n=5) == [SITE + "/a/", SITE + "/b/"]


def test_every_setup_decides_again_which_flows_run_so_none_is_switched_by_hand(db):
    db.setup(off=["sitemap"])
    db.sql("update sh_flows set enabled = (flow_name in (%s, %s))", [ROTATION_FLOW, SITEMAP_FLOW])       # by hand
    db.setup(off=["sitemap"])
    assert _enabled(db) == [PROBE_FLOW, CORE_FLOW, CERT_FLOW, CATALOGUE_FLOW, RUM_FLOW]
    # a flow that is switched off forgets its last run: switched on again it has "no data", not an old silence
    db.ran(SITEMAP_FLOW, days=40)
    db.ran(PROBE_FLOW, minutes=1)
    db.setup(off=["sitemap"])
    assert db.sql("select last_at is null from sh_flows where flow_name = %s", [SITEMAP_FLOW]) == [(True,)]
    db.setup()
    assert (flow(db, SITEMAP_FLOW)["status"], flow(db, PROBE_FLOW)["status"]) == ("אין נתון", "תקין")
    assert db.rpc("sh_alerts_check") == []                                 # and no "המדידה נעצרה" about 40 days ago


def test_setup_hands_the_screen_its_own_settings(db):
    nav = [["בריאות האתר", "/site"], ["מכירות", "/sales"]]
    links = [{"href": "/export", "label": "ייצוא", "title": "הורדת הנתונים"}]
    config = db.setup(down_after=2, hide=["certCard", "myCard"], nav=nav, links=links, off=["cert", "sitemap"],
                      extra_hosts=["shop.example.co.il", "checkout.example.com"])
    assert (config["hide"], config["nav"], config["links"]) == (["certCard", "myCard"], nav, links)       # as the file has them
    assert config["extra_hosts"] == ["shop.example.co.il", "checkout.example.com"]
    screen = config["screen"]
    assert (screen["downAfter"], screen["nav"], screen["links"]) == (2, nav, links)
    assert screen["hide"] == ["certCard", "myCard", "slowCard"]            # the file's cards, then those of "off", each once
    assert "extra_hosts" not in screen and "off" not in screen
    config = db.setup()                                                    # they left the file: back at the defaults
    assert (config["hide"], config["nav"], config["links"], config["extra_hosts"]) == ([], [], [], [])
    assert (config["screen"]["hide"], config["screen"]["downAfter"]) == ([], 1)


def test_a_database_that_was_set_up_before_the_newer_settings_answers_with_their_defaults(db):
    db.setup(platform="other")
    db.sql("delete from sh_settings where key in ('off', 'extra_hosts', 'hide', 'nav', 'links')")
    config = db.rpc("sh_config")
    assert (config["off"], config["extra_hosts"], config["hide"], config["nav"], config["links"]) == (
        ["catalogue"], [], [], [], [])                                     # "off" still follows the platform
    assert config["screen"]["hide"] == ["issuesCard"] and config["screen"]["downAfter"] == 1
    assert "nav" not in config["screen"] and "links" not in config["screen"]      # the screen keeps its own default


def test_page_addresses_are_stored_in_one_spelling(db):
    """A core page must be the same page as its line in the sitemap, however each side spells it."""
    contact = "/%D7%A6%D7%95%D7%A8-%D7%A7%D7%A9%D7%A8/"
    typed = example_config()
    typed["pages"] = [
        {"name": "בית", "url": "https://Example.co.il", "home": True, "probe": True, "core": True},      # no "/", a capital
        {"name": "צור קשר", "url": SITE + "/צור-קשר/", "probe": True, "core": True},                      # typed in Hebrew
        {"name": "מבצע", "url": SITE + "/sale 50%/?utm=x", "core": True}]
    config = db.rpc("sh_setup", p_config=typed)
    assert [p["url"] for p in config["pages"]] == [SITE + "/", SITE + contact, SITE + "/sale%2050%/?utm=x"]
    # the sitemap of a WordPress site writes the same Hebrew slug in lower-case escapes
    assert db.rpc("sh_sitemap_set", p_urls=[SITE + "/", SITE + contact.lower(), SITE + contact, SITE + "/about/",
                                            "https://EXAMPLE.co.il/about/", SITE + "/בלוג/", "not an address"]) == {"n": 4}
    assert _site_pages(db) == [(SITE + "/", True), (SITE + "/%D7%91%D7%9C%D7%95%D7%92/", True), (SITE + contact, True),
                               (SITE + "/about/", True)]
    rotation = [SITE + "/%D7%91%D7%9C%D7%95%D7%92/", SITE + "/about/"]
    assert db.rpc("sh_rotation_next", p_n=10) == rotation                  # neither core page takes a turn
    db.run(T0, SITE + contact, 9000, source="rotation")
    db.run(T0, rotation[0], 3000, source="rotation")
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(1))
    assert [r["url"] for r in section(rows, "האיטיים באתר")] == [rotation[0]]
    assert section(rows, "כיסוי") == [{"section": "כיסוי", "checks": 1, "slow_runs": 2}]
    # the next load, spelled differently again, is the same list
    assert db.rpc("sh_sitemap_set", p_urls=["https://example.co.il", SITE + "/צור-קשר/", SITE + "/about/"]) == {"n": 3}
    assert [url for url, active in _site_pages(db) if not active] == [SITE + "/%D7%91%D7%9C%D7%95%D7%92/"]


@pytest.mark.parametrize("address, stored", [
    ("https://example.co.il", "https://example.co.il/"),
    ("https://example.co.il/", "https://example.co.il/"),
    ("  HTTPS://WWW.Example.CO.IL/Cart/  ", "https://www.example.co.il/Cart/"),      # the path keeps its capitals
    ("https://example.co.il?ref=1", "https://example.co.il/?ref=1"),
    ("https://example.co.il/מוצר/ספה אפורה/", "https://example.co.il/%D7%9E%D7%95%D7%A6%D7%A8/"
                                              "%D7%A1%D7%A4%D7%94%20%D7%90%D7%A4%D7%95%D7%A8%D7%94/"),
    ("https://example.co.il/%d7%9e%D7%95/x%2fy", "https://example.co.il/%D7%9E%D7%95/x%2Fy"),
    ("https://example.co.il/a%zz/100%", "https://example.co.il/a%zz/100%"),          # not an escape: left alone
    ("https://example.co.il/p/€5", "https://example.co.il/p/%E2%82%AC5"),
    ("http://127.0.0.1:8080/x", "http://127.0.0.1:8080/x"),
    ("/cart/", None), ("example.co.il/cart/", None), ("", None), (None, None),
])
def test_sh_url(db, address, stored):
    assert db.sql("select sh_url(%s)", [address]) == [(stored,)]
    assert db.sql("select sh_url(sh_url(%s))", [address]) == [(stored,)]              # and it stays that way


def test_setup_takes_the_retention_and_the_real_user_settings(db):
    config = db.setup(keep_days=45, rum_hosts=["staging.example.co.il", "dev.example.co.il"],
                      private_paths=["קופה", "עגלת-קניות", "my-cart"])
    assert (config["keep_days"], config["rum_hosts"], config["private_paths"]) == (
        45, ["staging.example.co.il", "dev.example.co.il"], ["קופה", "עגלת-קניות", "my-cart"])
    assert db.rpc("sh_config") == config
    assert "keep_days" not in config["screen"]                 # none of the three is the screen's business
    for days in (30, 400, "90"):                               # the bounds; and a number that arrives as text
        assert db.setup(keep_days=days)["keep_days"] == int(days)
    stripped = {k: v for k, v in example_config().items() if k not in ("keep_days", "rum_hosts", "private_paths")}
    config = db.rpc("sh_setup", p_config=stripped)             # a setting that left the file is back at its default
    assert (config["keep_days"], config["rum_hosts"], config["private_paths"]) == (100, [], [])


def test_setup_again_changes_nothing_and_a_removed_page_keeps_its_history(db):
    first = db.setup()
    db.probe(T0, fail={"סל": 502})
    health = db.rpc("sh_health")
    assert db.setup() == first
    assert db.rpc("sh_health") == health                      # the proof of life survived

    smaller = example_config()
    smaller["pages"] = [p for p in smaller["pages"] if p["name"] != "סל"]
    config = db.rpc("sh_setup", p_config=smaller)
    assert [p["name"] for p in config["pages"]] == ["בית", "קטגוריה", "מוצר", "אודות"]
    assert (config["screen"]["probeCount"], config["screen"]["coreCount"]) == (3, 4)
    rows = db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1))
    assert [(r["page"], r["checks"], r["failed"]) for r in rows] == [
        ("בית", 1, 0), ("קטגוריה", 1, 0), ("מוצר", 1, 0), ("סל", 1, 1)]      # its history, after the configured pages


def _page(name="בית", url=SITE + "/", **flags):
    return dict(name=name, url=url, **flags)


HOME = _page(home=True, probe=True, core=True)


SETUP_REFUSALS = [
    ({"site": "example.co.il"}, '"site" must be an absolute http\\(s\\) address, got example.co.il'),
    ({"site": None}, '"site" must be an absolute http\\(s\\) address, got nothing'),
    ({"time_zone": "Mars/Olympus"}, 'unknown "time_zone" Mars/Olympus'),
    ({"time_zone": None}, '"time_zone" is required: the time zone of the site\'s customers, such as Asia/Jerusalem'),
    ({"time_zone": ""}, '"time_zone" is required'),
    ({"platform": "wix"}, '"platform" must be woocommerce, shopify or other, got wix'),
    ({"down_after": 0}, '"down_after" must be 1 or more, got 0'),
    ({"morning": "7:30"}, '"morning" must be a time such as 07:30, got 7:30'),
    ({"live_hosts": "live"}, '"live_hosts" and "path_labels" must be lists'),
    ({"keep_days": 29}, '"keep_days" must be a whole number of days from 30 to 400, got 29'),
    ({"keep_days": 401}, '"keep_days" must be a whole number of days from 30 to 400, got 401'),
    ({"keep_days": 99.5}, '"keep_days" must be a whole number of days from 30 to 400, got 99.5'),
    ({"keep_days": -100}, '"keep_days" must be a whole number of days from 30 to 400, got -100'),
    ({"keep_days": "forever"}, '"keep_days" must be a whole number of days from 30 to 400, got forever'),
    ({"keep_days": True}, '"keep_days" must be a whole number of days from 30 to 400, got true'),
    ({"rum_hosts": "staging.example.co.il"}, '"rum_hosts" and "private_paths" must be lists'),
    ({"private_paths": {"cart": "קופה"}}, '"rum_hosts" and "private_paths" must be lists'),
    ({"rum_hosts": ["https://staging.example.co.il"]}, '"rum_hosts" takes host names in lower case, .* got \\["https://'),
    ({"rum_hosts": ["staging.example.co.il/shop"]}, '"rum_hosts" takes host names in lower case'),
    ({"rum_hosts": ["Staging.Example.co.il"]}, '"rum_hosts" takes host names in lower case'),
    ({"rum_hosts": ["staging.example.co.il", 7]}, '"rum_hosts" takes host names in lower case'),
    ({"rum_hosts": [""]}, '"rum_hosts" takes host names in lower case'),
    ({"private_paths": ["/קופה/"]}, '"private_paths" takes single path segments, .* got \\["/קופה/"\\]'),
    ({"private_paths": ["shop/cart"]}, '"private_paths" takes single path segments'),
    ({"private_paths": ["cart?x=1"]}, '"private_paths" takes single path segments'),
    ({"private_paths": ["my cart"]}, '"private_paths" takes single path segments'),
    ({"private_paths": ["cart", None]}, '"private_paths" takes single path segments'),
    ({"private_paths": [""]}, '"private_paths" takes single path segments'),
    ({"off": "sitemap"}, '"extra_hosts", "off", "hide", "nav" and "links" must be lists'),
    ({"extra_hosts": "shop.example.co.il"}, '"extra_hosts", "off", "hide", "nav" and "links" must be lists'),
    ({"hide": "slowCard"}, '"extra_hosts", "off", "hide", "nav" and "links" must be lists'),
    ({"nav": {"/site": "בריאות האתר"}}, '"extra_hosts", "off", "hide", "nav" and "links" must be lists'),
    ({"links": "/export"}, '"extra_hosts", "off", "hide", "nav" and "links" must be lists'),
    ({"off": ["rum"]}, '"off" takes sitemap, real_users, catalogue or cert, got \\["rum"\\]'),
    ({"off": ["sitemap", "Cert"]}, '"off" takes sitemap, real_users, catalogue or cert'),
    ({"off": [None]}, '"off" takes sitemap, real_users, catalogue or cert'),
    ({"extra_hosts": ["https://shop.example.co.il"]}, '"extra_hosts" takes host names in lower case, .* got \\["https://'),
    ({"extra_hosts": ["Shop.example.co.il"]}, '"extra_hosts" takes host names in lower case'),
    ({"extra_hosts": ["shop.example.co.il", 7]}, '"extra_hosts" takes host names in lower case'),
    ({"hide": ["slowCard", 7]}, '"hide" takes the ids of cards of the screen, such as slowCard, got \\["slowCard", 7\\]'),
    ({"pages": None}, '"pages" must be a list of pages'),
    ({"pages": []}, 'exactly one page must have "home": true, found 0'),
    ({"pages": [_page(probe=True, core=True)]}, 'exactly one page must have "home": true, found 0'),
    ({"pages": [HOME, _page("ב", home=True)]}, 'exactly one page must have "home": true, found 2'),
    ({"pages": [_page(home=True, core=True)]}, 'at least one page must have "probe": true'),
    ({"pages": [_page(home=True, core=True), _page("ב", probe=True)]}, "the home page must be a probe page"),
    ({"pages": [_page(home=True, probe=True), _page("ב", probe=True, core=True)]}, "the home page must be a core page"),
    ({"pages": [_page(home=True, probe=True, core=False)]}, "the home page must be a core page"),
    ({"pages": [HOME, _page(probe=True)]}, "page names must be unique"),
    ({"pages": [HOME, _page("")]}, 'every page needs a "name"'),
    ({"pages": [HOME, {"url": SITE + "/x/"}]}, 'every page needs a "name"'),
    ({"pages": [HOME, _page("ב", url="/cart/")]}, "absolute http\\(s\\) address: ב"),
    ({"pages": [HOME, _page("ב", url="ftp://example.co.il/")]}, "absolute http\\(s\\) address: ב"),
    ({"pages": [HOME, {"name": "ב"}]}, "absolute http\\(s\\) address: ב"),
]


@pytest.mark.parametrize("change, message", SETUP_REFUSALS)
def test_setup_refuses_a_bad_configuration_and_keeps_the_old_one(db, change, message):
    before = db.setup()
    fails_with(db, psycopg.errors.RaiseException, "sh_setup: .*" + message, "sh_setup", p_config=example_config(**change))
    assert db.rpc("sh_config") == before


# More configurations whose fate is not plain: a value that Postgres must convert first (it refuses some with
# its own words, before sh_setup's checks), the spellings of true and false it accepts, null where a list goes.
LOOKS_ODD = [
    {"down_after": "2.5"}, {"down_after": 2.0}, {"down_after": True}, {"down_after": [2]},
    {"down_after": "99999999999"}, {"down_after": " 2 "}, {"down_after": "+3"}, {"down_after": "2", "site": None},
    {"site": 5}, {"site": ""}, {"site": "HTTPS://example.co.il"}, {"site": ["https://example.co.il"]},
    {"site": "https://example.co.il///"}, {"site": "https://:80/"},
    {"time_zone": 7}, {"time_zone": ["Asia/Jerusalem"]}, {"time_zone": "asia/jerusalem"}, {"time_zone": "UTC"},
    {"platform": ""}, {"platform": None}, {"morning": "07:30\n"}, {"morning": None}, {"morning": "23:59"},
    {"keep_days": "100 "}, {"keep_days": None}, {"keep_days": "030"}, {"keep_days": 400},
    {"live_hosts": None}, {"path_labels": None}, {"rum_hosts": None}, {"private_paths": None},
    {"extra_hosts": None}, {"off": None}, {"hide": None}, {"nav": None}, {"links": None},
    {"rum_hosts": ["a b"]}, {"private_paths": ["a\tb"]}, {"off": ["sitemap", 5]}, {"hide": [None]},
    {"extra_hosts": ["shop.example.co.il", {"b": 1, "aa": [2, "x"], "ccc": None}]},
    {"pages": [dict(HOME, probe="yes", core="ON", home=" t ")]}, {"pages": [dict(HOME, home=1)]},
    {"pages": [dict(HOME, core="maybe")]}, {"pages": [dict(HOME, probe="o")]}, {"pages": [dict(HOME, home="of")]},
    {"pages": [dict(HOME, home=1.0)]}, {"pages": [dict(HOME, probe="")]}, {"pages": [dict(HOME, core=[True])]},
    {"pages": [HOME, 7]}, {"pages": [HOME, ["x"]]}, {"pages": [dict(HOME, name=5)]},
    {"pages": [HOME, _page("ב", url="https://?x")]}, {"pages": [HOME, _page("ב", url=" https://example.co.il/x")]},
    {"pages": [HOME, _page("ב", url="https:// x")]}, {"pages": [HOME, _page("ב", url="https://example.co.il/ב")]},
    {"pages": [HOME, _page("ב", probe=True), _page("ג", url=5)]},
    {"pages": [_page(home=True, core=True), _page("ב", home=False, probe="false")]},
]


@pytest.mark.parametrize("change", [change for change, _ in SETUP_REFUSALS] + LOOKS_ODD)
def test_install_sql_refuses_with_the_words_of_the_database(db, change):
    """manage.py install-sql checks a configuration before it writes the file: whatever sh_setup refuses, it
    refuses with the very message the database gives, and what sh_setup takes it takes."""
    if str(REFERENCE) not in sys.path:
        sys.path.insert(0, str(REFERENCE))
    import manage

    config = example_config(**change)
    try:
        with db.conn.transaction():
            db.rpc("sh_setup", p_config=config)
        said = None
    except psycopg.Error as e:
        said = e.diag.message_primary
    assert manage._config_problem(config) == said


# ================================================================ availability (spec §7.3)

def _ten_rounds(db):
    """Ten full rounds, one a minute from T0. סל fails twice; a light round fails everywhere."""
    for i in range(10):
        db.probe(T0 + mins(i), ms={"בית": 100 + 10 * i, "קטגוריה": 600, "מוצר": 300 + i,
                                    "סל": 800 if i == 3 else 10000 if i == 7 else 500 + i},
              fail={"סל": 502} if i == 3 else {"סל": "timeout"} if i == 7 else None)
        db.probe(T0 + mins(i) + secs(30), "light", fail=DEAD, ms=None)


def test_availability_per_page(db):
    db.setup()
    _ten_rounds(db)
    assert db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(10)) == [
        {"section": "לפי עמוד", "page": "בית", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 145, "p95_ms": 186, "last_fail_il": None},              # 185.5 rounds up
        {"section": "לפי עמוד", "page": "קטגוריה", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 600, "p95_ms": 600, "last_fail_il": None},
        {"section": "לפי עמוד", "page": "מוצר", "checks": 10, "failed": 0, "fail_pct": "0.00",
         "p50_ms": 305, "p95_ms": 309, "last_fail_il": None},
        # the percentiles are over the 8 checks that answered: 500 501 502 504 505 506 508 509
        {"section": "לפי עמוד", "page": "סל", "checks": 10, "failed": 2, "fail_pct": "20.00",
         "p50_ms": 505, "p95_ms": 509, "last_fail_il": "12.11 09:07"}]
    # the 38 answers of all pages together; the ten light rounds, dead on every page, changed nothing
    assert db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(10)) == [
        {"bucket": "2024-11-12 09:00", "checks": 40, "failed": 2, "ms_p50": 309, "ms_p95": 600}]


def test_availability_window_is_from_inclusive_to_exclusive(db):
    db.setup()
    _ten_rounds(db)
    cart = db.rpc("sh_availability", p_from=T0 + mins(3), p_to=T0 + mins(6))[3]       # rounds 3, 4, 5
    assert (cart["checks"], cart["failed"], cart["fail_pct"], cart["last_fail_il"]) == (3, 1, "33.33", "12.11 09:03")
    cart = db.rpc("sh_availability", p_from=T0 + mins(4), p_to=T0 + mins(7))[3]       # rounds 4, 5, 6
    assert (cart["checks"], cart["failed"], cart["fail_pct"], cart["last_fail_il"]) == (3, 0, "0.00", None)
    assert db.rpc("sh_availability", p_from=T0 + mins(10), p_to=T0 + mins(20)) == []
    # only light rounds in the window: they are not availability
    assert db.rpc("sh_availability", p_from=T0 + secs(30), p_to=T0 + secs(31)) == []
    assert db.rpc("sh_availability_series", p_from=T0 + secs(30), p_to=T0 + secs(31)) == []


def test_local_time_follows_the_configured_time_zone(db):
    db.setup(time_zone="America/New_York")
    _ten_rounds(db)
    assert db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(10))[3]["last_fail_il"] == "12.11 02:07"
    assert [r["bucket"] for r in db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(10))] == ["2024-11-12 02:00"]
    days = db.rpc("sh_availability_series", p_from=T0 - mins(60 * 100), p_to=T0 + mins(10))
    assert [r["bucket"] for r in days] == ["2024-11-12"]


def test_outages(db):
    db.setup()
    three_fail = {"קטגוריה": 502, "מוצר": 502, "סל": 502}
    plan = {1: DEAD, 2: DEAD,                               # two dead rounds: not an outage
            4: three_fail, 5: three_fail, 6: three_fail,    # some pages answered: not an outage
            8: DEAD, 9: DEAD, 10: DEAD,                     # three dead rounds: an outage
            43: DEAD, 44: DEAD, 45: DEAD, 46: DEAD}         # dead until the end of the window
    for i in list(range(12)) + list(range(42, 47)):         # minutes 12-41: the prober did not run at all
        db.probe(T0 + mins(i), fail=plan.get(i))
    outage = {"section": "נפילות", "outage_minutes": 3, "outage_start_il": "12.11 09:08", "outage_end_il": "12.11 09:11"}
    assert section(db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(47)), "נפילות") == [
        outage,
        # no round after the last dead one: it ends with the window
        {"section": "נפילות", "outage_minutes": 4, "outage_start_il": "12.11 09:43", "outage_end_il": "12.11 09:47"}]
    # the rows of the pages still come first
    assert [r["section"] for r in db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(47))] == ["לפי עמוד"] * 4 + ["נפילות"] * 2
    # only the rounds inside the window count
    assert section(db.rpc("sh_availability", p_from=T0 + mins(8), p_to=T0 + mins(12)), "נפילות") == [outage]
    assert section(db.rpc("sh_availability", p_from=T0 + mins(9), p_to=T0 + mins(12)), "נפילות") == []
    assert section(db.rpc("sh_availability", p_from=T0 + mins(12), p_to=T0 + mins(43)), "נפילות") == []


def test_an_outage_that_is_still_going_on_ends_now(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(4))
    for i in (3, 2, 1):
        db.probe(now - mins(i), fail=DEAD)
    assert section(db.rpc("sh_availability", p_from=now - mins(60), p_to=now + mins(1)), "נפילות") == [
        {"section": "נפילות", "outage_minutes": 3, "outage_start_il": il(now - mins(3)), "outage_end_il": il(now)}]


def test_an_outage_counts_dead_rounds_not_the_minutes_without_rounds(db):
    """Spec §7.3 reads the rounds in order: two dead rounds, a pause of the prober, one more dead
    round are three consecutive dead rounds. The pause adds nothing to outage_minutes."""
    db.setup()
    for i, fail in [(0, DEAD), (1, DEAD), (30, DEAD), (31, None)]:
        db.probe(T0 + mins(i), fail=fail)
    assert section(db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(60)), "נפילות") == [
        {"section": "נפילות", "outage_minutes": 3, "outage_start_il": "12.11 09:00", "outage_end_il": "12.11 09:31"}]


def _two_hours(db):
    """09:00-09:59: three rounds. 10:00-10:59: two rounds, one with a failure. Then the two
    rounds around local midnight."""
    db.probe(T0, ms=100)
    db.probe(T0 + mins(1), ms=200)
    db.probe(T0 + mins(59), ms=300)
    db.probe(T0 + mins(60), ms=400)
    db.probe(T0 + mins(61), ms={"בית": 520, "קטגוריה": 540, "מוצר": 560, "סל": 9999}, fail={"סל": 502})
    db.probe(dt.datetime(2024, 11, 12, 21, 59, tzinfo=UTC), ms=300)      # 23:59 in Jerusalem
    db.probe(dt.datetime(2024, 11, 12, 22, 0, tzinfo=UTC), ms=300)       # 00:00 the next day


def test_availability_series_hourly_and_daily(db):
    db.setup()
    _two_hours(db)
    assert db.rpc("sh_availability_series", p_from=T0, p_to=T0 + mins(120)) == [
        {"bucket": "2024-11-12 09:00", "checks": 12, "failed": 0, "ms_p50": 200, "ms_p95": 300},
        # the answers: 400 400 400 400 520 540 560; p95 = 540 + 0.7 * 20
        {"bucket": "2024-11-12 10:00", "checks": 8, "failed": 1, "ms_p50": 400, "ms_p95": 554}]
    assert db.rpc("sh_availability_series", p_from=T0 - mins(4 * 1440), p_to=T0 + mins(1440)) == [
        # the answers: 100x4 200x4 300x8 400x4 520 540 560; p95 = 520 + 0.9 * 20
        {"bucket": "2024-11-12", "checks": 24, "failed": 1, "ms_p50": 300, "ms_p95": 538},
        {"bucket": "2024-11-13", "checks": 4, "failed": 0, "ms_p50": 300, "ms_p95": 300}]


@pytest.mark.parametrize("window, bucket", [
    (mins(72 * 60), "2024-11-12 09:00"),
    (mins(72 * 60 + 1), "2024-11-12 09:00"),     # "h=72" as the server sends it: to = now + 1 minute
    (mins(72 * 60 + 59), "2024-11-12 09:00"),
    (mins(73 * 60), "2024-11-12"),
    (mins(168 * 60 + 1), "2024-11-12"),
])
def test_buckets_turn_daily_after_72_whole_hours(db, window, bucket):
    db.setup()
    db.probe(T0)
    db.run(T0)
    end = T0 + mins(1)
    assert [r["bucket"] for r in db.rpc("sh_availability_series", p_from=end - window, p_to=end)] == [bucket]
    assert [r["bucket"] for r in db.rpc("sh_speed_series", p_from=end - window, p_to=end, p_strategy="mobile")] == [bucket]


def test_the_hour_that_happens_twice_is_one_bucket_everywhere(db):
    """27.10.2024, Jerusalem: at 02:00 the clocks went back to 01:00."""
    db.setup()
    first, second = dt.datetime(2024, 10, 26, 22, 30, tzinfo=UTC), dt.datetime(2024, 10, 26, 23, 30, tzinfo=UTC)
    db.probe(dt.datetime(2024, 10, 26, 21, 0, tzinfo=UTC))              # 00:00 on the 27th
    db.probe(first)                                                      # 01:30, summer time
    db.probe(second, fail={"סל": 502})                                   # 01:30 again, winter time
    db.probe(dt.datetime(2024, 10, 27, 21, 59, tzinfo=UTC))             # 23:59 on the 27th
    db.probe(dt.datetime(2024, 10, 27, 22, 0, tzinfo=UTC))              # 00:00 on the 28th
    start = dt.datetime(2024, 10, 26, 20, 0, tzinfo=UTC)
    hourly = db.rpc("sh_availability_series", p_from=start, p_to=start + mins(30 * 60))
    assert [(r["bucket"], r["checks"], r["failed"]) for r in hourly] == [
        ("2024-10-27 00:00", 4, 0), ("2024-10-27 01:00", 8, 1), ("2024-10-27 23:00", 4, 0), ("2024-10-28 00:00", 4, 0)]
    assert [(r["page"], r["checks"], r["failed"]) for r in db.rpc("sh_drill_bucket", p_bucket="2024-10-27 01:00")] == [
        ("בית", 2, 0), ("קטגוריה", 2, 0), ("מוצר", 2, 0), ("סל", 2, 1)]
    assert [r["checks"] for r in db.rpc("sh_drill_bucket", p_bucket="2024-10-27")] == [4, 4, 4, 4]       # a day of 25 hours
    window = dict(p_from=start, p_to=start + mins(30 * 60))
    assert [r["at_il"] for r in db.rpc("sh_drill_fails", p_bucket="2024-10-27 01:00", **window)] == ["27.10 01:30"]
    assert db.rpc("sh_drill_fails", p_bucket="2024-10-27 00:00", **window) == []


# ================================================================ speed (spec §7.3)

def _speed_runs(db):
    for k, (lcp, score, cls, ttfb) in enumerate([(2000, 70, 0.01, 300), (2200, 66, 0.02, 310), (2400, 62, 0.03, 320),
                                                 (4100, 30, 0.04, 330), (5000, 20, 0.05, 340)]):
        newest = k == 4
        db.run(T0 + mins(15 * k), "בית", lcp, score=score, cls=cls, ttfb_ms=ttfb,
            crux_category="AVERAGE" if newest else "FAST", crux_lcp_ms=3100 if newest else 2000)
    db.run(T0 + mins(80), "בית", None, err="Lighthouse returned error: NO_FCP")       # failed: never counted
    db.run(T0, "בית", 1000, "desktop", score=90, cls=0, ttfb_ms=100)
    db.run(T0 + mins(60), "בית", 1200, "desktop", score=95, cls=0.01, ttfb_ms=121)
    db.run(T0, "קטגוריה", 3300, score=45, cls=0.1, ttfb_ms=500)
    db.run(T0 + mins(100), "קטגוריה", 3300)                                            # outside the window


def test_speed_core_pages_and_bottom_line(db):
    db.setup()
    _speed_runs(db)
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))
    assert [r["section"] for r in rows] == ["שורה תחתונה", "ליבה", "ליבה", "ליבה", "כיסוי"]
    assert section(rows, "שורה תחתונה") == [
        {"section": "שורה תחתונה", "page": "בית", "url": URL["בית"], "lcp_p50": 2400, "checks": 5, "verdict": "מהיר"}]
    assert section(rows, "ליבה") == [
        {"section": "ליבה", "strategy": "mobile", "page": "בית", "url": URL["בית"],
         "lcp_p50": 2400, "lcp_p95": 4820, "score_med": 62, "cls_med": 0.03, "ttfb_p50": 320,
         "slow_runs": 2, "checks": 5, "crux_category": "AVERAGE", "crux_lcp": 3100},       # crux: the newest run
        {"section": "ליבה", "strategy": "mobile", "page": "קטגוריה", "url": URL["קטגוריה"],
         "lcp_p50": 3300, "lcp_p95": 3300, "score_med": 45, "cls_med": 0.1, "ttfb_p50": 500,
         "slow_runs": 0, "checks": 1, "crux_category": None, "crux_lcp": None},
        {"section": "ליבה", "strategy": "desktop", "page": "בית", "url": URL["בית"],
         "lcp_p50": 1100, "lcp_p95": 1190, "score_med": 93, "cls_med": 0.005, "ttfb_p50": 111,
         "slow_runs": 0, "checks": 2, "crux_category": None, "crux_lcp": None}]


def test_core_speed_counts_core_runs_only_and_slow_is_above_4_seconds(db):
    db.setup()
    for i, lcp in enumerate([3999, 4000, 4001, 4002]):
        db.run(T0 + mins(15 * i), "סל", lcp)
    db.run(T0 + mins(5), URL["סל"], 9000, source="rotation")              # from before it became a core page
    (row,) = section(db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90)), "ליבה")
    assert (row["page"], row["checks"], row["slow_runs"], row["lcp_p50"]) == ("סל", 4, 2, 4001)      # 4000 is not slow


def test_speed_without_runs_still_has_its_bottom_line_and_coverage(db):
    db.setup()
    db.run(T0, "בית", None, err="timeout")
    assert db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90)) == [
        {"section": "שורה תחתונה", "page": "בית", "url": URL["בית"], "lcp_p50": None, "checks": 0, "verdict": None},
        {"section": "כיסוי", "checks": 0, "slow_runs": 0}]


@pytest.mark.parametrize("lcp, verdict", [(2000, "מצוין"), (2001, "מהיר"), (2500, "מהיר"), (2501, "בינוני"),
                                          (4000, "בינוני"), (4001, "איטי")])
def test_verdict_thresholds(db, lcp, verdict):
    db.setup()
    db.run(T0, "בית", lcp)
    db.run(T0 + mins(1), "בית", 9000, "desktop")           # the bottom line is the phone, always
    assert db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))[0]["verdict"] == verdict


def test_speed_heaviest_pages_and_coverage(db):
    db.setup()
    pages = [SITE + "/product/item-%02d/" % i for i in range(1, 13)]
    core = [URL["בית"], URL["קטגוריה"]]                       # in the sitemap too, and not the rotation's business
    db.rpc("sh_sitemap_set", p_urls=pages + core + [SITE + "/faq/", SITE + "/contact/", SITE + "/blog/"])
    db.run(T0 + mins(40), URL["קטגוריה"], 50000, source="rotation")              # from before it became a core page
    for i, url in enumerate(pages, start=1):
        db.run(T0 + mins(i), url, 1000 * i, source="rotation", score=100 - 5 * i)
    db.run(T0 + mins(30), pages[11], 13000, source="rotation", score=20)        # a second run of the heaviest
    db.run(T0 + mins(31), pages[0], None, source="rotation", err="timeout")     # failed: not counted
    db.run(T0 + mins(32), pages[0], 99000, "desktop", source="rotation")        # not a phone run
    db.run(T0 + mins(33), "בית", 99000)                                          # a core run, not the rotation
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))
    heavy = section(rows, "האיטיים באתר")
    assert heavy[0] == {"section": "האיטיים באתר", "page": pages[11], "url": pages[11], "lcp_p50": 12500,
                        "score_med": 30, "checks": 2, "last_il": "12.11 09:30"}
    assert [(r["url"], r["lcp_p50"], r["score_med"], r["checks"], r["last_il"]) for r in heavy[1:]] == [
        (pages[i - 1], 1000 * i, 100 - 5 * i, 1, il(T0 + mins(i))) for i in range(11, 2, -1)]      # ten rows in all
    assert section(rows, "כיסוי") == [{"section": "כיסוי", "checks": 12, "slow_runs": 15}]
    # a page that left the sitemap is neither "a page of the site" nor "measured"
    db.rpc("sh_sitemap_set", p_urls=pages[1:] + core + [SITE + "/faq/"])
    assert section(db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90)), "כיסוי") == [
        {"section": "כיסוי", "checks": 11, "slow_runs": 12}]
    # and a page that is no longer a core page is the rotation's again, with the run it has
    fewer = example_config()
    fewer["pages"] = [dict(p, core=p["name"] != "קטגוריה") for p in fewer["pages"]]
    db.rpc("sh_setup", p_config=fewer)
    rows = db.rpc("sh_speed", p_from=T0, p_to=T0 + mins(90))
    assert section(rows, "כיסוי") == [{"section": "כיסוי", "checks": 12, "slow_runs": 13}]
    assert section(rows, "האיטיים באתר")[0]["url"] == URL["קטגוריה"]


def test_speed_series(db):
    db.setup()
    db.run(T0, "בית", 2000)
    db.run(T0 + mins(15), "בית", 2400)
    db.run(T0 + mins(30), "בית", None, err="timeout")
    db.run(T0 + mins(60), "בית", 3000)
    db.run(T0, "קטגוריה", 3300)
    db.run(T0, "בית", 900, "desktop")
    db.run(T0 + mins(1), "בית", 8000, source="rotation")    # the rotation is not part of the core series
    home, category = {"page": "בית", "url": URL["בית"]}, {"page": "קטגוריה", "url": URL["קטגוריה"]}
    hours = dict(p_from=T0, p_to=T0 + mins(120))
    assert db.rpc("sh_speed_series", p_strategy="mobile", **hours) == [
        dict(home, bucket="2024-11-12 09:00", lcp_p50=2200), dict(home, bucket="2024-11-12 10:00", lcp_p50=3000),
        dict(category, bucket="2024-11-12 09:00", lcp_p50=3300)]
    assert db.rpc("sh_speed_series", p_strategy="desktop", **hours) == [dict(home, bucket="2024-11-12 09:00", lcp_p50=900)]
    assert db.rpc("sh_speed_series", p_from=T0 - mins(4 * 1440), p_to=T0 + mins(120), p_strategy="mobile") == [
        dict(home, bucket="2024-11-12", lcp_p50=2400), dict(category, bucket="2024-11-12", lcp_p50=3300)]


# ================================================================ health of the measuring (spec §7.3)

def test_health_lists_the_flows_of_the_spec_before_any_ran(db):
    db.setup()
    assert db.rpc("sh_health") == [
        {"flow_name": name, "status": "אין נתון", "cadence": cadence, "silent_txt": None, "last_at": None,
         "warn_minutes": warn, "late_minutes": late, "note": None} for name, cadence, warn, late in FLOWS]
    assert [(r["flow_name"], r["warn_minutes"], r["late_minutes"]) for r in db.rpc("sh_health")][6] == (
        "מהירות אצל לקוחות", 360, 1440)


@pytest.mark.parametrize("name, ago, status, text", [
    (PROBE_FLOW, dict(minutes=5), "תקין", None),                                   # warn 5, late 15
    (PROBE_FLOW, dict(minutes=5, seconds=1), "מתעכב", "מאחר בדקה"),                # a started minute counts
    (PROBE_FLOW, dict(minutes=6, seconds=30), "מתעכב", "מאחר בשתי דקות"),
    (PROBE_FLOW, dict(minutes=15), "מתעכב", "מאחר ב-10 דקות"),
    (PROBE_FLOW, dict(minutes=15, seconds=1), "שקט", "שקט כבר 15 דקות"),
    (RUM_FLOW, dict(minutes=360), "תקין", None),                                   # warn 360, late 1440
    (RUM_FLOW, dict(minutes=400), "מתעכב", "מאחר ב-40 דקות"),
    (RUM_FLOW, dict(minutes=420), "מתעכב", "מאחר בשעה"),
    (RUM_FLOW, dict(minutes=360 + 119), "מתעכב", "מאחר ב-119 דקות"),               # minutes under two hours
    (RUM_FLOW, dict(minutes=360 + 120), "מתעכב", "מאחר בשעתיים"),
    (RUM_FLOW, dict(minutes=1440), "מתעכב", "מאחר ב-18 שעות"),
    (RUM_FLOW, dict(minutes=1441), "שקט", "שקט כבר 24 שעות"),
    (CERT_FLOW, dict(minutes=1560 + 180), "מתעכב", "מאחר ב-3 שעות"),               # warn 1560, late 2880
    (CERT_FLOW, dict(minutes=2881), "שקט", "שקט כבר יומיים"),
    (CERT_FLOW, dict(days=3, hours=5), "שקט", "שקט כבר 3 ימים"),
])
def test_health_status_by_the_age_of_the_last_run(db, name, ago, status, text):
    db.setup()
    db.ran(name, **ago)
    row = flow(db, name)
    assert (row["status"], row["silent_txt"]) == (status, text)
    assert dt.datetime.fromisoformat(row["last_at"]) == db.now() - dt.timedelta(**ago)


@pytest.mark.parametrize("minutes, text", [
    (0, "דקה"), (0.4, "דקה"), (1, "דקה"), (1.49, "דקה"), (1.5, "שתי דקות"), (2, "שתי דקות"), (3, "3 דקות"),
    (59, "59 דקות"), (60, "שעה"), (61, "61 דקות"), (119, "119 דקות"),              # minutes under two hours
    (120, "שעתיים"), (179, "שעתיים"), (180, "3 שעות"), (1439, "23 שעות"), (1440, "יום"), (1441, "24 שעות"),
    (2879, "47 שעות"),                                                             # whole hours under two days
    (2880, "יומיים"), (4319, "יומיים"), (4320, "3 ימים"), (144000, "100 ימים"),
])
def test_a_length_of_time_is_said_as_a_person_says_it(db, minutes, text):
    assert db.sql("select sh_span(%s::numeric)", [minutes]) == [(text,)]


def test_the_mock_says_a_length_of_time_and_a_recovery_as_the_database_does(db, monkeypatch):
    spans = dict(db.sql("select m, sh_span(m) from generate_series(1, 6000) m"))
    assert [m for m in spans if mock.span_he(m) != spans[m]] == []
    halves = [0, 0.4, 0.5, 1.49, 1.5, 2.5, 59.5, 119.5, 179.5, 1439.5, 2879.5, 4319.5]
    assert [mock.span_he(m) for m in halves] == [db.sql("select sh_span(%s::numeric)", [m])[0][0] for m in halves]
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    opened = {a["title"]: a for a in mock.alerts()}
    back = [row for row in mock.api_messages({})["rows"] if row["kind"] == "חזר לתקין"]
    assert back and all(row["title"].startswith("חזר לתקין: ") for row in back)
    for row in back:                                  # as sh_alerts_check stores it: the alert's title, then how long
        title, _, lasted = row["msg"].partition("\n")
        assert title in opened and row["title"] == "חזר לתקין: " + opened[title]["name"]
        assert lasted == "נמשך " + mock.span_he(opened[title]["minutes"])


# ================================================================ sh_now (spec §5.3)

def test_now_on_a_fresh_install(db, monkeypatch):
    db.setup()
    assert db.rpc("sh_now") == {
        "pages": [], "latest": [], "light": False, "all_ok": False, "any_ok": False, "age_sec": None,
        "rum": {"n": 0, "p75_ms": None}, "speed": {}, "alerts_open": 0, "rum_src": None}
    monkeypatch.setitem(mock.STATE, "scenario", "empty")
    assert db.rpc("sh_now") == mock.api_now("owner")                      # to the letter what the mock answers


def test_now_pages_come_from_the_full_round_and_the_state_from_the_latest_round(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(132), fail=DEAD)                                             # an older round: ignored
    db.probe(now - secs(72), ms={"בית": 240, "קטגוריה": 690, "מוצר": 310, "סל": 1700}, fail={"מוצר": 503})
    db.probe(now - secs(12), "light", ms=None, fail={"סל": "timeout"})
    state = db.rpc("sh_now")
    assert state["pages"] == [
        {"page": "בית", "url": URL["בית"], "ok": True, "status": 200, "ms": 240},
        {"page": "קטגוריה", "url": URL["קטגוריה"], "ok": True, "status": 200, "ms": 690},
        {"page": "מוצר", "url": URL["מוצר"], "ok": False, "status": 503, "ms": None},       # it did not answer: no time
        {"page": "סל", "url": URL["סל"], "ok": True, "status": 200, "ms": 1700}]
    assert state["latest"] == [{"page": "בית", "ok": True}, {"page": "קטגוריה", "ok": True},
                               {"page": "מוצר", "ok": True}, {"page": "סל", "ok": False}]
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (True, False, True, 12)

    db.probe(now - secs(2), fail=DEAD)                                               # a full round is now the latest
    state = db.rpc("sh_now")
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (False, False, False, 2)
    assert [p["ok"] for p in state["pages"]] == [False] * 4

    db.probe(now, "light", ms=None)
    state = db.rpc("sh_now")
    assert (state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (True, True, True, 0)


def test_now_forgets_rounds_older_than_15_minutes(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(15))
    db.probe(now - mins(14), "light", ms=None)
    state = db.rpc("sh_now")
    assert (len(state["pages"]), len(state["latest"]), state["light"], state["age_sec"]) == (4, 4, True, 840)
    db.sql("update sh_probe set round_at = round_at - interval '1 second'")           # 15:01 and 14:01 old
    state = db.rpc("sh_now")
    assert (state["pages"], len(state["latest"]), state["light"], state["age_sec"]) == ([], 4, True, 841)
    db.sql("update sh_probe set round_at = round_at - interval '1 minute'")           # both too old
    state = db.rpc("sh_now")
    assert (state["pages"], state["latest"], state["light"], state["all_ok"], state["any_ok"], state["age_sec"]) == (
        [], [], False, False, False, None)


def test_now_real_users(db):
    db.setup()
    views = [{"site": "live", "path": "/", "lcp_ms": lcp, "is_test": False} for lcp in (1000, 2000, 3000)]
    views += [{"site": "live", "path": "/", "lcp_ms": 60000, "is_test": True},
              {"site": "staging.example.co.il", "path": "/", "lcp_ms": 50000, "is_test": False}]
    assert db.rpc("sh_rum_add", p_rows=views) == {"n": 5}
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) values"
           " (now() - interval '60 minutes', 'live', '/', 4000), (now() - interval '61 minutes', 'live', '/', 55000)")
    state = db.rpc("sh_now")
    assert state["rum"] == {"n": 4, "p75_ms": 3250}           # 1000 2000 3000 4000: the last hour, live, not test
    assert state["rum_src"] == {"n": 7, "hosts": [{"host": "live", "n": 6}, {"host": "staging.example.co.il", "n": 1}],
                                "cols": ["created_at", "is_test", "lcp_ms", "path", "site"], "test": 1}

    db.setup(live_hosts=["live", "staging.example.co.il"])
    assert db.rpc("sh_now")["rum"] == {"n": 5, "p75_ms": 4000}
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms)"
           " select now() - interval '2 hours', 'old.example.co.il', '/', 1000 from generate_series(1, 1200)")
    assert db.rpc("sh_now")["rum_src"]["n"] == 1000           # where the newest 1000 came from
    assert db.rpc("sh_now")["rum_src"]["hosts"][0] == {"host": "old.example.co.il", "n": 993}


def test_now_names_the_five_largest_sources_only(db):
    """The ingest is open to the internet: a flood of made-up site names must not fill the screen."""
    db.setup()
    sites = {"live": 9, "staging.example.co.il": 6, "b.example": 3, "a.example": 3, "c.example": 2, "d.example": 2,
             "e.example": 1}
    for site, n in sites.items():
        db.sql("insert into sh_rum (site, path, lcp_ms) select %s, '/', 1000 from generate_series(1, %s)", [site, n])
    db.sql("insert into sh_rum (site, path, lcp_ms) select 'flood-' || g || '.example', '/', 1000 from generate_series(1, 400) g")
    source = db.rpc("sh_now")["rum_src"]
    assert source["hosts"] == [{"host": "live", "n": 9}, {"host": "staging.example.co.il", "n": 6},
                               {"host": "a.example", "n": 3}, {"host": "b.example", "n": 3}, {"host": "c.example", "n": 2}]
    assert source["n"] == 426                                  # all the rows that were looked at


def test_now_lab_speed_and_open_alerts(db):
    db.setup()
    now = db.now()
    db.run(now - mins(40), "בית", 2500, score=63)
    db.run(now - mins(25), "בית", 2700, score=60)
    db.run(now - mins(10), "בית", None, err="timeout")
    db.run(now - mins(5), "בית", 900, "desktop", score=99)
    db.run(now - mins(1), "קטגוריה", 3300, score=40)
    state = db.rpc("sh_now")
    assert state["speed"]["lcp_ms"] == 2700 and state["speed"]["score"] == 60
    assert dt.datetime.fromisoformat(state["speed"]["checked_at"]) == now - mins(25)
    assert set(state["speed"]) == {"lcp_ms", "score", "checked_at"}

    db.probe(now - secs(5), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")
    assert db.rpc("sh_now")["alerts_open"] == 2


# ================================================================ drill-downs (spec §5.4)

def test_drill_fails(db):
    db.setup()
    db.probe(T0, fail={"סל": 502}, ms={"סל": 812})
    db.probe(T0 + secs(30), "light", fail=DEAD, ms=None)                # a light round is not listed
    db.probe(T0 + mins(1), fail={"בית": "timeout"}, ms={"בית": 10000})
    db.rpc("sh_probe_add", p_round_at=T0 + mins(2), p_kind="full", p_rows=[
        {"page": "קטגוריה", "url": URL["קטגוריה"], "ok": False, "fail": "connect", "err": "connection reset by peer"},
        {"page": "מוצר", "url": URL["מוצר"], "ok": False, "status": 200, "ms": 420, "fail": "content"}])
    db.probe(T0 + mins(61), fail={"סל": 500}, ms={"סל": 95})
    everything = [
        {"at_il": "12.11 10:01", "page": "סל", "kind": "קוד 500", "err": None, "ms": 95},
        {"at_il": "12.11 09:02", "page": "מוצר", "kind": "תוכן לא צפוי", "err": None, "ms": 420},
        {"at_il": "12.11 09:02", "page": "קטגוריה", "kind": "שגיאת חיבור", "err": "connection reset by peer", "ms": None},
        {"at_il": "12.11 09:01", "page": "בית", "kind": "לא ענה בזמן", "err": None, "ms": 10000},
        {"at_il": "12.11 09:00", "page": "סל", "kind": "קוד 502", "err": None, "ms": 812}]
    window = dict(p_from=T0, p_to=T0 + mins(120))
    assert db.rpc("sh_drill_fails", **window) == everything
    assert db.rpc("sh_drill_fails", p_page="", p_bucket="", **window) == everything       # as the screen sends them
    assert db.rpc("sh_drill_fails", p_page="סל", **window) == [everything[0], everything[4]]
    assert db.rpc("sh_drill_fails", p_bucket="2024-11-12 09:00", **window) == everything[1:]
    assert db.rpc("sh_drill_fails", p_bucket="2024-11-12", **window) == everything
    assert db.rpc("sh_drill_fails", p_page="סל", p_bucket="2024-11-12 10:00", **window) == [everything[0]]
    assert db.rpc("sh_drill_fails", p_from=T0 + mins(1), p_to=T0 + mins(2)) == [everything[3]]


def test_drill_fails_returns_the_newest_500(db):
    db.setup()
    db.sql("insert into sh_probe (round_at, kind, page, url, ok, status, fail)"
           " select %s + n * interval '1 minute', 'full', 'סל', 'u', false, 502, 'http' from generate_series(1, 510) n", [T0])
    rows = db.rpc("sh_drill_fails", p_from=T0, p_to=T0 + mins(600))
    assert len(rows) == 500
    assert (rows[0]["at_il"], rows[-1]["at_il"]) == (il(T0 + mins(510)), il(T0 + mins(11)))


def test_drill_bucket(db):
    db.setup()
    db.probe(T0, ms={"בית": 100, "סל": 500, "קטגוריה": 400, "מוצר": 400})
    db.probe(T0 + mins(17), ms={"בית": 1900, "סל": 520, "קטגוריה": 400, "מוצר": 400})
    db.probe(T0 + mins(30), ms={"בית": 290, "סל": 5000, "קטגוריה": 400, "מוצר": 400}, fail={"סל": 502})
    db.probe(T0 + mins(30) + secs(30), "light", fail=DEAD, ms=None)
    db.probe(T0 + mins(60), ms=700, fail={"סל": "timeout"})
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 09:00") == [
        {"page": "בית", "checks": 3, "failed": 0, "ms_p50": 290, "ms_max": 1900, "worst_il": "12.11 09:17"},
        {"page": "קטגוריה", "checks": 3, "failed": 0, "ms_p50": 400, "ms_max": 400, "worst_il": "12.11 09:00"},
        {"page": "מוצר", "checks": 3, "failed": 0, "ms_p50": 400, "ms_max": 400, "worst_il": "12.11 09:00"},
        # the failed check took 5000 ms, and that is not a response time
        {"page": "סל", "checks": 3, "failed": 1, "ms_p50": 510, "ms_max": 520, "worst_il": "12.11 09:17"}]
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 10:00")[3] == {
        "page": "סל", "checks": 1, "failed": 1, "ms_p50": None, "ms_max": None, "worst_il": None}
    assert [(r["page"], r["checks"], r["failed"], r["ms_max"]) for r in db.rpc("sh_drill_bucket", p_bucket="2024-11-12")] == [
        ("בית", 4, 0, 1900), ("קטגוריה", 4, 0, 700), ("מוצר", 4, 0, 700), ("סל", 4, 2, 520)]
    assert db.rpc("sh_drill_bucket", p_bucket="2024-11-12 11:00") == []


def test_drill_runs(db):
    db.setup()
    opps = [{"id": "render-blocking-resources", "title": "Eliminate render-blocking resources", "ms": 600}]
    db.run(T0, "בית", 2400, score=64, ttfb_ms=410, bytes=3400000, cls=0.03, crux_category="FAST", crux_lcp_ms=2100, opps=opps)
    db.run(T0 + mins(15), "בית", None, err="Lighthouse returned error: NO_FCP")
    db.run(T0 + mins(60), "בית", 2600)
    db.run(T0, "בית", 900, "desktop")
    db.run(T0, "קטגוריה", 3300)
    first = {"ok": True, "err": None, "at_il": "12.11 09:00", "lcp_ms": 2400, "score": 64, "ttfb_ms": 410,
             "bytes": 3400000, "cls": 0.03, "crux_category": "FAST", "crux_lcp_ms": 2100, "opps": opps}
    failed = {"ok": False, "err": "Lighthouse returned error: NO_FCP", "at_il": "12.11 09:15"}
    last = {"ok": True, "err": None, "at_il": "12.11 10:00", "lcp_ms": 2600, "score": None, "ttfb_ms": None,
            "bytes": None, "cls": None, "crux_category": None, "crux_lcp_ms": None, "opps": []}
    window = dict(p_from=T0, p_to=T0 + mins(120), p_url=URL["בית"])
    assert db.rpc("sh_drill_runs", **window) == [last, failed, first]                       # phone unless told otherwise
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="", **window) == [last, failed, first]
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="2024-11-12 09:00", **window) == [failed, first]
    assert db.rpc("sh_drill_runs", p_strategy="mobile", p_bucket="2024-11-12", **window) == [last, failed, first]
    assert [r["lcp_ms"] for r in db.rpc("sh_drill_runs", p_strategy="desktop", **window)] == [900]
    assert db.rpc("sh_drill_runs", p_from=T0 + mins(1), p_to=T0 + mins(60), p_url=URL["בית"]) == [failed]
    assert db.rpc("sh_drill_runs", p_from=T0, p_to=T0 + mins(120), p_url=SITE + "/nothing/") == []


def test_drill_runs_carry_the_reasons_of_the_newest_100_successful_runs_only(db):
    db.setup()
    reasons = [{"id": "image-delivery-insight", "title": "שיפור הצגת התמונות", "ms": 900}]
    yesterday = T0 - mins(1440)
    db.rpc("sh_speed_add", p_rows=(
        # yesterday 130 runs, every tenth failed (117 good ones); today 25 good ones
        [{"at": (yesterday + mins(k)).isoformat(), "url": URL["בית"], "page": "בית", "strategy": "mobile", "source": "core",
          "ok": k % 10 != 0, "err": "timeout" if k % 10 == 0 else None, "lcp_ms": 2000 + k, "opps": reasons}
         for k in range(130)]
        + [{"at": (T0 + mins(k)).isoformat(), "url": URL["בית"], "page": "בית", "strategy": "mobile", "source": "core",
            "ok": True, "lcp_ms": 3000 + k, "opps": reasons} for k in range(25)]))

    rows = db.rpc("sh_drill_runs", p_from=yesterday, p_to=T0 + mins(60), p_url=URL["בית"])
    assert len(rows) == 155 and [r["ok"] for r in rows].count(True) == 142               # every run, newest first
    assert rows[0]["lcp_ms"] == 3024 and rows[-1] == {"ok": False, "err": "timeout", "at_il": il(yesterday)}
    good = [r for r in rows if r["ok"]]
    assert [r["opps"] for r in good] == [reasons] * 100 + [[]] * 42
    assert (good[99]["lcp_ms"], good[100]["lcp_ms"]) == (2047, 2046)                      # 25 of today, 75 of yesterday
    assert all(set(r) == {"ok", "err", "at_il"} for r in rows if not r["ok"])
    # the 100 are counted inside the answer: yesterday alone is 117 good runs
    day = db.rpc("sh_drill_runs", p_from=yesterday, p_to=T0 + mins(60), p_url=URL["בית"], p_bucket="2024-11-11")
    assert len(day) == 130 and [r["opps"] for r in day if r["ok"]] == [reasons] * 100 + [[]] * 17
    hour = db.rpc("sh_drill_runs", p_from=yesterday, p_to=T0 + mins(60), p_url=URL["בית"], p_bucket="2024-11-11 09:00")
    assert len(hour) == 60 and all(r["opps"] == reasons for r in hour if r["ok"])


def test_drill_alert(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(10), fail={"סל": 500})                         # an earlier blip, answered since
    db.probe(now - mins(5))
    db.probe(now - mins(4), fail={"סל": 502, "מוצר": 502})
    pushes = db.rpc("sh_alerts_check")
    # as if the check had run right after that round, not at the frozen "now" of this test
    db.sql("update sh_alerts set opened_at = now() - interval '3 minutes 50 seconds'")
    db.probe(now - mins(4) + secs(30), "light", fail={"סל": "timeout", "מוצר": 502}, ms=None)
    db.probe(now - mins(3), fail={"סל": 502, "מוצר": 502})
    db.probe(now - mins(2), fail={"מוצר": 502})
    pushes += db.rpc("sh_alerts_check")
    assert [m["event"] for m in pushes] == ["open", "open", "close"]
    for message in pushes:
        db.rpc("sh_message_sent", p_id=message["id"], p_status=200)
    cart, product = sorted(db.rpc("sh_alerts_range", p_from=now - mins(60), p_to=now + mins(1)), key=lambda a: a["open"])
    assert (cart["title"], cart["open"], product["title"], product["open"]) == (
        "האתר לא עונה: סל", False, "האתר לא עונה: מוצר", True)

    assert db.rpc("sh_drill_alert", p_id=cart["id"]) == [dict(
        cart,
        fails=[{"at": il(now - mins(4)), "page": "סל", "status": 502, "err": None},
               {"at": il(now - mins(4) + secs(30)), "page": "סל", "status": None, "err": "לא ענה בזמן"},
               {"at": il(now - mins(3)), "page": "סל", "status": 502, "err": None}],
        sent=[{"event": "open", "status": 200, "at": il(now)}, {"event": "close", "status": 200, "at": il(now)}])]
    assert cart == {"id": cart["id"], "kind": "down", "title": "האתר לא עונה: סל", "body": "קוד 502\n" + URL["סל"],
                    "open": False, "opened_il": il(now - secs(230)), "closed_il": il(now), "minutes": 4}
    detail = db.rpc("sh_drill_alert", p_id=product["id"])[0]
    assert len(detail["fails"]) == 4 and detail["sent"] == [{"event": "open", "status": 200, "at": il(now)}]
    assert db.rpc("sh_drill_alert", p_id=cart["id"] + 1000) == []

    db.ran(CORE_FLOW, minutes=95)                                      # an alert of another kind has no failed checks
    db.rpc("sh_alerts_check")
    silent = db.rpc("sh_alerts_open")[0]
    assert silent["kind"] == "silent"
    detail = db.rpc("sh_drill_alert", p_id=silent["id"])[0]
    assert (detail["fails"], detail["sent"]) == ([], [])                # its push is still owed


# ================================================================ alert rules (spec §7.8)

def _open(db):
    return [(a["kind"], a["title"]) for a in db.rpc("sh_alerts_open")]


def _pushes(db):
    """What one call of sh_alerts_check hands out, without the ids: the pushes that are owed and
    that no earlier call claimed in the last two minutes."""
    return [{k: v for k, v in m.items() if k != "id"} for m in db.rpc("sh_alerts_check")]


def _two_minutes_pass(db):
    """The claims of the calls so far lapse. (The clock of a test stands still, so the claims move.)"""
    db.sql("update sh_messages set claimed_at = claimed_at - interval '2 minutes'")


def test_down_alert_opens_on_the_first_failed_check_and_closes_on_the_next_answer(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(60))
    assert db.rpc("sh_alerts_check") == [] and db.rpc("sh_alerts_open") == []

    db.probe(now - secs(30), "light", fail={"סל": 502}, ms=None)                 # a light round is enough
    opening = {"title": "האתר לא עונה: סל", "msg": "קוד 502\n" + URL["סל"], "priority": 4, "click": None,
               "kind": "התראה", "event": "open"}
    assert _pushes(db) == [opening]
    alert = db.rpc("sh_alerts_open")
    assert alert == [{"id": alert[0]["id"], "kind": "down", "title": "האתר לא עונה: סל",
                      "body": "קוד 502\n" + URL["סל"], "opened_il": il(now), "acked": False}]

    db.probe(now - secs(20), fail={"סל": "timeout"})                             # still down: nothing new
    assert _pushes(db) == []
    assert db.rpc("sh_alerts_open") == alert
    assert db.sql("select count(*) from sh_alerts") == [(1,)] and db.sql("select count(*) from sh_messages") == [(1,)]

    db.sql("update sh_alerts set opened_at = now() - interval '7 minutes 20 seconds'")
    db.probe(now - secs(10), "light", ms=None)                                   # it answered
    # the recovery names the page, not the alert: never "חזר לתקין: האתר לא עונה: סל"
    assert _pushes(db) == [{"title": "חזר לתקין: סל", "msg": "האתר לא עונה: סל\nנמשך 7 דקות", "priority": 2,
                            "click": None, "kind": "חזר לתקין", "event": "close"}]
    assert db.rpc("sh_alerts_open") == []
    assert db.sql("select count(*) from sh_alerts where closed_at = now()") == [(1,)]
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1))[0] == {       # the message log shows what was pushed
        "kind": "חזר לתקין", "title": "חזר לתקין: סל", "msg": "האתר לא עונה: סל\nנמשך 7 דקות", "at_il": il(now),
        "sent": False}

    db.rpc("sh_alerts_check")                                                     # nothing to close twice
    assert db.sql("select count(*) from sh_messages") == [(2,)]


@pytest.mark.parametrize("lasted, minutes, text", [
    ("0 seconds", 1, "נמשך דקה"),                              # never "0 דקות"
    ("20 seconds", 1, "נמשך דקה"),
    ("1 minute 59.997 seconds", 2, "נמשך שתי דקות"),           # two rounds: the closing tick was 3 ms quicker
    ("2 minutes 59.994 seconds", 3, "נמשך 3 דקות"),            # the outage row beside it says 3 minutes too
    ("3 minutes 0.004 seconds", 3, "נמשך 3 דקות"),
    ("7 minutes 30 seconds", 8, "נמשך 8 דקות"),
    ("1 hour", 60, "נמשך שעה"),
    ("2 hours 5 minutes", 125, "נמשך שעתיים"),
    ("49 hours", 2940, "נמשך יומיים"),
])
def test_an_alert_lasted_the_nearest_whole_minute_on_the_phone_and_on_the_screen(db, lasted, minutes, text):
    db.setup()
    now = db.now()
    db.probe(now - secs(40), fail={"סל": 502})
    db.rpc("sh_alerts_check")
    db.sql("update sh_alerts set opened_at = now() - %s::interval", [lasted])
    db.probe(now - secs(10))
    (push,) = db.rpc("sh_alerts_check")
    assert (push["event"], push["title"], push["msg"]) == ("close", "חזר לתקין: סל", "האתר לא עונה: סל\n" + text)
    (alert,) = db.rpc("sh_alerts_range", p_from=now - mins(60 * 72), p_to=now + mins(1))
    assert alert["minutes"] == minutes
    assert db.rpc("sh_drill_alert", p_id=alert["id"])[0]["minutes"] == minutes


def test_an_alert_of_another_kind_is_left_alone(db):
    """Spec §7.8: other parts of the owner's system may keep alerts of their own kinds in sh_alerts."""
    db.setup()
    now = db.now()
    db.sql("insert into sh_alerts (key, kind, title, body, opened_at) values"
           " ('ops:backup', 'ops', 'הגיבוי נכשל', 'גוף', now() - interval '3 hours'),"
           " ('sale:כיסא', 'sale', 'מבצע הסתיים', null, now() - interval '5 minutes')")
    db.probe(now - secs(30))
    for _ in range(3):
        assert db.rpc("sh_alerts_check") == []                 # nothing to push: no false "חזר לתקין"
    assert sorted(_open(db)) == [("ops", "הגיבוי נכשל"), ("sale", "מבצע הסתיים")]
    assert db.sql("select count(*) from sh_messages") == [(0,)]
    assert db.sql("select count(*) from sh_alerts where closed_at is not null") == [(0,)]


def test_a_problem_that_comes_back_is_a_new_alert_that_nobody_has_seen(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(50), fail={"סל": "connect"})
    db.rpc("sh_alerts_check")
    first = db.rpc("sh_alerts_open")[0]
    assert first["body"] == "שגיאת חיבור\n" + URL["סל"]
    assert db.rpc("sh_alert_ack", p_ids=[first["id"]], p_who="owner") == {"n": 1}
    assert db.rpc("sh_alerts_open")[0]["acked"] is True
    db.probe(now - secs(40))
    db.rpc("sh_alerts_check")
    db.probe(now - secs(30), fail={"סל": "content"})
    db.rpc("sh_alerts_check")
    second = db.rpc("sh_alerts_open")
    assert len(second) == 1 and second[0]["id"] != first["id"]
    assert (second[0]["acked"], second[0]["body"]) == (False, "תוכן לא צפוי\n" + URL["סל"])
    assert db.sql("select event from sh_messages order by id") == [("open",), ("close",), ("open",)]


def test_down_after_2_waits_for_two_failed_rounds_in_a_row(db):
    db.setup(down_after=2)
    now = db.now()
    db.probe(now - secs(120), fail={"סל": 502})                  # the only round so far
    assert db.rpc("sh_alerts_check") == []
    db.probe(now - secs(90), "light", ms=None)
    db.probe(now - secs(60), fail={"סל": 502})                   # failed, answered, failed: not in a row
    assert db.rpc("sh_alerts_check") == []
    db.probe(now - secs(30), "light", fail={"סל": "timeout"}, ms=None)
    assert _pushes(db) == [{"title": "האתר לא עונה: סל", "msg": "לא ענה בזמן\n" + URL["סל"], "priority": 4,
                            "click": None, "kind": "התראה", "event": "open"}]
    db.probe(now - secs(20), fail={"סל": 502})
    assert db.rpc("sh_alerts_check") == [] and _open(db) == [("down", "האתר לא עונה: סל")]
    db.probe(now - secs(10), "light", ms=None)                   # one answer closes it
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["close"] and _open(db) == []


def test_down_alert_needs_a_recent_round_and_a_configured_page(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(1441), fail={"סל": 502})
    db.rpc("sh_alerts_check")
    # a failure from before yesterday says nothing about the page now; what is wrong now is the prober
    assert _open(db) == [("silent", "המדידה נעצרה: " + PROBE_FLOW)]
    db.sql("update sh_alerts set opened_at = now() - interval '1 minute'")       # the test's clock stands still
    db.probe(now - secs(30), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")
    assert sorted(_open(db)) == [("down", "האתר לא עונה: מוצר"), ("down", "האתר לא עונה: סל")]
    db.sql("update sh_probe set round_at = round_at - interval '2 days'")
    db.rpc("sh_alerts_check")                                     # no round since: no news, both stay open
    assert sorted(_open(db)) == [("down", "האתר לא עונה: מוצר"), ("down", "האתר לא עונה: סל")]
    smaller = example_config()
    smaller["pages"] = [p for p in smaller["pages"] if p["name"] != "סל"]
    db.rpc("sh_setup", p_config=smaller)
    db.rpc("sh_alerts_check")                                     # a page that is no longer probed can never answer
    assert _open(db) == [("down", "האתר לא עונה: מוצר")]


def test_slow_alert(db):
    db.setup()
    now = db.now()
    db.run(now - mins(30), "קטגוריה", 4100)
    assert db.rpc("sh_alerts_check") == []                        # once is not twice in a row
    db.run(now - mins(15), "קטגוריה", 4600)
    db.run(now - mins(30), "מוצר", 5000)                         # slow, then fast enough
    db.run(now - mins(15), "מוצר", 3900)
    db.run(now - mins(30), "סל", 4000)                           # 4000 is not above 4000
    db.run(now - mins(15), "סל", 4000)
    db.run(now - mins(30), "בית", 9000, "desktop")               # the rule is about the phone
    db.run(now - mins(15), "בית", 9000, "desktop")
    db.run(now - mins(30), "אודות", 3000)
    db.run(now - mins(15), "אודות", 5000)                        # only the newest is slow
    assert _pushes(db) == [{"title": "עמוד איטי: קטגוריה", "msg": "4.6 שניות עד התוכן, פעמיים ברצף\n" + URL["קטגוריה"],
                            "priority": 3, "click": None, "kind": "התראה", "event": "open"}]
    assert _open(db) == [("slow", "עמוד איטי: קטגוריה")]

    db.run(now - mins(10), "קטגוריה", None, err="timeout")       # a failed run is not a measurement
    db.run(now - mins(9), "קטגוריה", 1000, "desktop")
    db.rpc("sh_alerts_check")
    assert _open(db) == [("slow", "עמוד איטי: קטגוריה")]
    db.run(now - mins(5), "אודות", 5100)                         # now twice in a row
    db.run(now - mins(5), "קטגוריה", 4000)                       # and this one recovered
    assert sorted((m["event"], m["title"], m["msg"], m["priority"]) for m in db.rpc("sh_alerts_check")) == [
        ("close", "חזר לתקין: קטגוריה", "עמוד איטי: קטגוריה\nנמשך דקה", 2),
        ("open", "עמוד איטי: אודות", "5.1 שניות עד התוכן, פעמיים ברצף\n" + URL["אודות"], 3)]
    assert db.rpc("sh_alerts_open")[0]["body"] == "5.1 שניות עד התוכן, פעמיים ברצף\n" + URL["אודות"]


def test_silent_alert(db):
    db.setup()
    db.ran(PROBE_FLOW, minutes=15)                               # exactly its late_minutes: not yet silent
    db.ran(ROTATION_FLOW, minutes=59)
    assert db.rpc("sh_alerts_check") == [] and db.rpc("sh_alerts_open") == []      # the other flows never ran
    db.ran(CORE_FLOW, minutes=95, seconds=30)
    assert _pushes(db) == [{"title": "המדידה נעצרה: " + CORE_FLOW, "msg": "אין מדידה כבר 95 דקות", "priority": 4,
                            "click": None, "kind": "התראה", "event": "open"}]
    assert _open(db) == [("silent", "המדידה נעצרה: " + CORE_FLOW)]
    assert flow(db, CORE_FLOW)["status"] == "שקט"                 # the screen and the alert agree

    db.run(db.now(), "בית", 2400)                                # it ran again
    assert _pushes(db) == [{"title": "חזר לתקין: " + CORE_FLOW, "msg": "המדידה נעצרה: " + CORE_FLOW + "\nנמשך דקה", "priority": 2,
                            "click": None, "kind": "חזר לתקין", "event": "close"}]
    assert _open(db) == []


@pytest.mark.parametrize("ago, text", [
    (dict(minutes=60, seconds=59), "אין מדידה כבר שעה"),                  # whole minutes, as the flow's row says
    (dict(minutes=119, seconds=59), "אין מדידה כבר 119 דקות"),
    (dict(hours=2, minutes=30), "אין מדידה כבר שעתיים"),
    (dict(hours=30), "אין מדידה כבר 30 שעות"),
    (dict(minutes=2940), "אין מדידה כבר יומיים"),                         # a daily flow: never "2940 דקות"
    (dict(days=5, hours=3), "אין מדידה כבר 5 ימים"),
])
def test_silent_alert_tells_the_silence_in_hours_and_days(db, ago, text):
    db.setup()
    db.sql("update sh_flows set late_minutes = 60 where flow_name = %s", [SITEMAP_FLOW])
    db.ran(SITEMAP_FLOW, **ago)
    (push,) = db.rpc("sh_alerts_check")
    assert (push["title"], push["msg"]) == ("המדידה נעצרה: " + SITEMAP_FLOW, text)
    assert flow(db, SITEMAP_FLOW)["silent_txt"] == text.replace("אין מדידה", "שקט")


def test_the_real_user_flow_shows_its_silence_and_opens_no_alert(db):
    db.setup()
    assert db.sql("select flow_name, alerts from sh_flows order by sort") == [(f[0], f[0] != RUM_FLOW) for f in FLOWS]
    db.ran(RUM_FLOW, days=3)                                     # a small site: no visitors since the weekend
    assert db.rpc("sh_alerts_check") == [] and db.rpc("sh_alerts_open") == []
    assert (flow(db, RUM_FLOW)["status"], flow(db, RUM_FLOW)["silent_txt"]) == ("שקט", "שקט כבר 3 ימים")

    # the flag is the rule, and whoever sets it by hand keeps it: sh_setup seeds it and never resets it
    db.sql("update sh_flows set alerts = (flow_name = %s)", [RUM_FLOW])
    db.ran(SITEMAP_FLOW, days=3)
    db.setup()
    assert db.sql("select flow_name, alerts from sh_flows order by sort") == [(f[0], f[0] == RUM_FLOW) for f in FLOWS]
    assert [m["title"] for m in db.rpc("sh_alerts_check")] == ["המדידה נעצרה: " + RUM_FLOW]
    db.sql("update sh_flows set alerts = false")                 # the flag goes off: nothing could clear the alert
    assert [(m["event"], m["title"]) for m in db.rpc("sh_alerts_check")] == [("close", "חזר לתקין: " + RUM_FLOW)]
    assert db.rpc("sh_alerts_open") == []


def test_silent_alert_ignores_a_disabled_flow_and_closes_when_its_flow_is_disabled(db):
    db.setup()
    db.ran(CATALOGUE_FLOW, days=3)
    db.rpc("sh_alerts_check")
    assert _open(db) == [("silent", "המדידה נעצרה: " + CATALOGUE_FLOW)]
    db.setup(platform="other")                                    # no catalogue any more
    assert [m["event"] for m in db.rpc("sh_alerts_check")] == ["close"] and _open(db) == []
    db.rpc("sh_alerts_check")
    assert db.sql("select count(*) from sh_alerts") == [(1,)]

    db.setup()                                                    # the same through the "off" list
    db.ran(CERT_FLOW, days=3)
    db.ran(SITEMAP_FLOW, days=3)
    assert sorted(m["title"] for m in db.rpc("sh_alerts_check")) == sorted(
        "המדידה נעצרה: " + name for name in (CERT_FLOW, SITEMAP_FLOW))
    db.setup(off=["cert", "sitemap"])
    assert sorted((m["event"], m["title"]) for m in db.rpc("sh_alerts_check")) == sorted(
        ("close", "חזר לתקין: " + name) for name in (CERT_FLOW, SITEMAP_FLOW))
    assert _open(db) == []


def test_silent_alert_opened_early_by_the_independent_check_stays_until_the_flow_runs_again(db):
    """Spec §7.10: sh_deadman opens this alert when the newest round is 10 minutes old, before
    the flow's own 15 minutes."""
    db.setup()
    now = db.now()
    db.probe(now - mins(11))
    db.sql("insert into sh_alerts (key, kind, title, body, opened_at) values (%s, 'silent', %s, 'אין מדידה כבר 10 דקות', %s)",
           ["silent:" + PROBE_FLOW, "המדידה נעצרה: " + PROBE_FLOW, now - mins(1)])
    assert db.rpc("sh_alerts_check") == [] and len(_open(db)) == 1          # 11 minutes: not closed, not opened twice
    db.sql("update sh_flows set last_at = now() - interval '16 minutes' where flow_name = %s", [PROBE_FLOW])
    assert db.rpc("sh_alerts_check") == [] and len(_open(db)) == 1          # 16 minutes: still the same alert
    db.probe(now - secs(30))
    assert [(m["event"], m["title"], m["msg"]) for m in db.rpc("sh_alerts_check")] == [
        ("close", "חזר לתקין: " + PROBE_FLOW, "המדידה נעצרה: " + PROBE_FLOW + "\nנמשך דקה")]
    assert _open(db) == []


def _cert(db, days, ok=True, err=None):
    return db.rpc("sh_cert_set", p_row={"host": "example.co.il", "issuer": "Let's Encrypt R11", "ok": ok, "err": err,
                                        "days_left": days, "not_before": "2024-09-01T00:00:00Z",
                                        "not_after": "2024-11-30T00:00:00Z"})


def test_cert_alert(db):
    db.setup()
    _cert(db, 14)
    assert db.rpc("sh_alerts_check") == []
    _cert(db, 13)
    assert _pushes(db) == [{"title": "תעודת האבטחה פגה בעוד 13 ימים", "msg": "example.co.il", "priority": 3,
                            "click": None, "kind": "התראה", "event": "open"}]
    _cert(db, None, ok=False, err="handshake failed")             # a failed check proves nothing either way
    db.rpc("sh_alerts_check")
    assert _open(db) == [("cert", "תעודת האבטחה פגה בעוד 13 ימים")]
    db.rpc("sh_cert_set", p_row={"host": "other.example", "ok": True, "days_left": 3})      # not the configured host
    db.rpc("sh_alerts_check")
    assert len(_open(db)) == 1
    _cert(db, 89)
    db.sql("update sh_alerts set opened_at = now() - interval '3 days 2 hours'")
    assert _pushes(db) == [{"title": "חזר לתקין: תעודת האבטחה", "msg": "תעודת האבטחה פגה בעוד 13 ימים\nנמשך 3 ימים", "priority": 2,
                            "click": None, "kind": "חזר לתקין", "event": "close"}]
    assert _open(db) == []


def test_cert_alert_is_not_judged_while_the_certificate_check_is_off(db):
    db.setup()
    _cert(db, 5)
    db.rpc("sh_alerts_check")
    assert _open(db) == [("cert", "תעודת האבטחה פגה בעוד 5 ימים")]
    db.setup(off=["cert"])                                        # nothing could ever clear it: it closes
    assert [(m["event"], m["title"]) for m in db.rpc("sh_alerts_check")] == [("close", "חזר לתקין: תעודת האבטחה")]
    assert db.rpc("sh_alerts_check") == [] and _open(db) == []    # and the old row opens no new one
    db.setup()
    assert [m["title"] for m in db.rpc("sh_alerts_check")] == ["תעודת האבטחה פגה בעוד 5 ימים"]


@pytest.mark.parametrize("days, title", [
    (13, "תעודת האבטחה פגה בעוד 13 ימים"), (3, "תעודת האבטחה פגה בעוד 3 ימים"), (2, "תעודת האבטחה פגה בעוד יומיים"),
    (1, "תעודת האבטחה פגה בעוד יום"), (0, "תעודת האבטחה פגה בעוד פחות מיום"), (-1, "תוקף תעודת האבטחה פג"),
])
def test_cert_alert_counts_the_days_as_a_person_does(db, days, title):
    db.setup()
    _cert(db, days)
    assert [m["title"] for m in db.rpc("sh_alerts_check")] == [title]


def test_ack_marks_only_open_alerts_that_nobody_marked(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(50), fail={"סל": 502, "מוצר": 502, "בית": 502})
    db.rpc("sh_alerts_check")
    db.probe(now - secs(40), fail={"סל": 502, "מוצר": 502})
    db.rpc("sh_alerts_check")                                     # the alert of בית is closed now
    ids = {title: i for i, title in db.sql("select id, title from sh_alerts")}
    home, cart, product = ids["האתר לא עונה: בית"], ids["האתר לא עונה: סל"], ids["האתר לא עונה: מוצר"]

    assert db.rpc("sh_alert_ack", p_ids=[cart, home, 999999], p_who="owner") == {"n": 1}
    assert {a["id"]: a["acked"] for a in db.rpc("sh_alerts_open")} == {cart: True, product: False}
    assert db.rpc("sh_alert_ack", p_ids=[cart, product], p_who="staff") == {"n": 1}       # סל keeps its first mark
    assert db.sql("select id, acked_by, acked_at = now() from sh_alerts where acked_at is not null order by id") == sorted(
        [(cart, "owner", True), (product, "staff", True)])
    assert db.rpc("sh_alert_ack", p_ids=[], p_who="owner") == {"n": 0}
    assert len(db.rpc("sh_alerts_open")) == 2 and db.rpc("sh_now")["alerts_open"] == 2    # marked is not closed


def test_alerts_range_lists_what_was_open_inside_the_window(db):
    db.setup()
    now = db.now()
    db.sql("insert into sh_alerts (key, kind, title, body, opened_at, closed_at) values"
           " ('down:סל', 'down', 'א', 'גוף', %s, %s), ('ops:x', 'ops', 'ב', null, %s, null),"
           " ('down:סל', 'down', 'ג', '', %s, %s)",
           [T0, T0 + mins(10), T0 + mins(30), T0 + mins(100), T0 + mins(101) + secs(59)])

    def titles(start, end):
        return [a["title"] for a in db.rpc("sh_alerts_range", p_from=T0 + mins(start), p_to=T0 + mins(end))]

    assert titles(-60, 200) == ["ג", "ב", "א"]                    # newest first
    assert titles(10, 30) == ["א"]                                # closed at the first instant of the window
    assert titles(11, 30) == []
    assert titles(11, 31) == ["ב"]
    assert titles(150, 200) == ["ב"]                              # still open
    first, second = db.rpc("sh_alerts_range", p_from=T0, p_to=T0 + mins(50))[::-1]
    assert first == {"id": first["id"], "kind": "down", "title": "א", "body": "גוף", "open": False,
                     "opened_il": "12.11 09:00", "closed_il": "12.11 09:10", "minutes": 10}
    assert second == {"id": second["id"], "kind": "ops", "title": "ב", "body": None, "open": True,
                      "opened_il": "12.11 09:30", "closed_il": None,
                      "minutes": half_up((now - T0 - mins(30)).total_seconds() / 60)}
    assert db.rpc("sh_alerts_range", p_from=T0 + mins(100), p_to=T0 + mins(101))[0]["minutes"] == 2      # 1:59


def test_an_owed_push_is_handed_out_once_in_two_minutes(db):
    db.setup()
    db.probe(db.now() - secs(30), fail={"סל": 502})
    (push,) = db.rpc("sh_alerts_check")
    assert db.sql("select claimed_at = now(), status, attempts from sh_messages") == [(True, None, 0)]
    assert db.rpc("sh_alerts_check") == []                                        # claimed by the first call
    db.sql("update sh_messages set claimed_at = now() - interval '1 minute 59 seconds'")
    assert db.rpc("sh_alerts_check") == []
    db.sql("update sh_messages set claimed_at = now() - interval '2 minutes'")
    assert db.rpc("sh_alerts_check") == [push]                                    # the sender never reported: again
    assert db.sql("select claimed_at = now() from sh_messages") == [(True,)]      # and claimed again
    assert db.rpc("sh_alerts_check") == []

    assert db.rpc("sh_message_sent", p_id=push["id"], p_status=200) == {"n": 1}
    _two_minutes_pass(db)
    assert db.rpc("sh_alerts_check") == []                                        # settled: never again


def test_a_push_result_settles_the_push_or_counts_as_a_failed_attempt(db):
    db.setup()
    now = db.now()
    db.probe(now - secs(30), fail={"בית": 502, "סל": 502, "מוצר": 502})
    owed = {m["title"]: m["id"] for m in db.rpc("sh_alerts_check")}
    home, cart, product = owed["האתר לא עונה: בית"], owed["האתר לא עונה: סל"], owed["האתר לא עונה: מוצר"]
    alert = dict(db.sql("select m.id, m.alert_id from sh_messages m"))

    def state(message):
        return db.sql("select status, attempts from sh_messages where id = %s", [message])[0]

    def pushes_of(message):
        return db.rpc("sh_drill_alert", p_id=alert[message])[0]["sent"]

    assert db.rpc("sh_message_sent", p_id=cart, p_status=204) == {"n": 1}         # any 2xx: sent
    assert db.rpc("sh_message_sent", p_id=cart, p_status=500) == {"n": 0}         # settled: nothing more to record
    assert state(cart) == (204, 1)
    assert db.rpc("sh_message_sent", p_id=home, p_status=0) == {"n": 1}           # pushing is not configured:
    assert state(home) == (0, 1)                                                  # settled at once, not sent
    assert db.rpc("sh_message_sent", p_id=home, p_status=200) == {"n": 0}

    for attempt, status in enumerate([503, 599, None, 500], start=1):             # four failed attempts
        assert db.rpc("sh_message_sent", p_id=product, p_status=status) == {"n": 1}
        assert state(product) == (None, attempt) and pushes_of(product) == []     # still owed: not in the alert's list
        assert db.rpc("sh_alerts_check") == []                                    # and its claim still stands
        _two_minutes_pass(db)
        assert [m["id"] for m in db.rpc("sh_alerts_check")] == [product]          # offered again, only this one
    assert db.rpc("sh_message_sent", p_id=product, p_status=429) == {"n": 1}      # the fifth failure is the last
    assert state(product) == (429, 5)
    _two_minutes_pass(db)
    assert db.rpc("sh_alerts_check") == []
    assert db.rpc("sh_message_sent", p_id=product, p_status=200) == {"n": 0}

    assert {m["title"]: m["sent"] for m in db.rpc("sh_messages", p_from=now, p_to=now + mins(1))} == {
        "האתר לא עונה: בית": False, "האתר לא עונה: סל": True, "האתר לא עונה: מוצר": False}
    assert [pushes_of(m) for m in (cart, home, product)] == [
        [{"event": "open", "status": status, "at": il(now)}] for status in (204, 0, 429)]
    assert db.rpc("sh_message_sent", p_id=home + cart + product, p_status=200) == {"n": 0}      # no such message


def test_a_fifth_attempt_without_a_status_settles_as_a_network_error(db):
    db.setup()
    db.probe(db.now() - secs(30), fail={"סל": 502})
    (push,) = db.rpc("sh_alerts_check")
    for _ in range(5):
        assert db.rpc("sh_message_sent", p_id=push["id"], p_status=None) == {"n": 1}
    assert db.sql("select status, attempts from sh_messages") == [(599, 5)]


def test_messages_log_is_newest_first_and_inside_the_window(db):
    db.setup()
    db.sql("insert into sh_messages (at, event, kind, title, msg, priority, status) values"
           " (%s, 'open', 'התראה', 'א', 'גוף', 4, 200), (%s, 'close', 'חזר לתקין', 'א', 'נמשך 7 דקות', 2, null),"
           " (%s, 'morning', 'בוקר', 'ב', null, 2, 500)", [T0, T0 + mins(7), T0 + mins(60)])
    assert db.rpc("sh_messages", p_from=T0, p_to=T0 + mins(61)) == [
        {"kind": "בוקר", "title": "ב", "msg": None, "at_il": "12.11 10:00", "sent": False},
        {"kind": "חזר לתקין", "title": "א", "msg": "נמשך 7 דקות", "at_il": "12.11 09:07", "sent": False},
        {"kind": "התראה", "title": "א", "msg": "גוף", "at_il": "12.11 09:00", "sent": True}]
    assert [m["at_il"] for m in db.rpc("sh_messages", p_from=T0 + mins(1), p_to=T0 + mins(60))] == ["12.11 09:07"]


def test_morning_message_is_queued_once_a_day(db):
    db.setup()
    now = db.now()
    db.probe(now - mins(2 * 1440))                              # the site has been measured for two days
    for i in range(10, 0, -1):
        db.probe(now - mins(i), fail={"סל": 502} if i == 6 else None)
    db.run(now - mins(20), "בית", 2300)
    today = now.astimezone(TZ).date()
    assert db.rpc("sh_morning", p_day=today) == {"n": 1}
    assert db.rpc("sh_morning", p_day=today) == {"n": 0}
    assert db.rpc("sh_job_due", p_job="morning", p_day=today) is False
    assert _pushes(db) == [{"title": "בוקר טוב: האתר תקין", "msg": "זמינות 97.50% ב-24 שעות\nמהירות עמוד הבית: מהיר",
                            "priority": 2, "click": None, "kind": "בוקר", "event": "morning"}]
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1)) == [
        {"kind": "בוקר", "title": "בוקר טוב: האתר תקין", "msg": "זמינות 97.50% ב-24 שעות\nמהירות עמוד הבית: מהיר",
         "at_il": il(now), "sent": False}]
    assert db.rpc("sh_morning", p_day=today + dt.timedelta(days=1)) == {"n": 1}
    assert db.sql("select count(*) from sh_messages where event = 'morning'") == [(2,)]


@pytest.mark.parametrize("dead_rounds, failing_now, title, lines", [
    (0, [], "בוקר טוב: האתר תקין", ["זמינות 100.0% ב-24 שעות"]),
    (3, ["סל"], "בוקר טוב: התראה פתוחה אחת", ["זמינות 76.92% ב-24 שעות", "נפילות: 1 (3 דקות)"]),
    (4, ["סל", "מוצר"], "בוקר טוב: 2 התראות פתוחות", ["זמינות 71.43% ב-24 שעות", "נפילות: 1 (4 דקות)"]),
])
def test_morning_message_text(db, dead_rounds, failing_now, title, lines):
    db.setup()
    now = db.now()
    db.probe(now - mins(2 * 1440))
    for i in range(10 + dead_rounds, 10, -1):
        db.probe(now - mins(i), fail=DEAD)
    for i in range(10, 0, -1):
        db.probe(now - mins(i))
    if failing_now:
        db.probe(now - secs(30), "light", fail=dict.fromkeys(failing_now, 502), ms=None)
        db.rpc("sh_alerts_check")
    db.rpc("sh_morning", p_day=now.date())
    assert db.sql("select title, msg from sh_messages where event = 'morning'") == [(title, "\n".join(lines))]


def test_morning_message_without_any_measurement(db):
    db.setup()
    db.probe(db.now() - mins(2 * 1440))                         # measured once, and the prober has been dead since
    assert db.rpc("sh_morning", p_day=db.now().date()) == {"n": 1}
    assert db.sql("select title, msg, priority, kind from sh_messages") == [
        ("בוקר טוב: אין מדידות", "אין בדיקות זמינות ב-24 שעות", 2, "בוקר")]


def test_a_new_installation_gets_no_morning_message_until_it_has_measured_for_six_hours(db):
    """The first push an owner ever gets must not be "good morning, nothing was measured" on the
    afternoon of the installation (decision D4)."""
    db.setup()
    now = db.now()
    days = [now.date() + dt.timedelta(days=n) for n in range(4)]
    skipped = {"n": 0, "skipped": "the oldest probe round is less than 6 hours old"}
    assert db.rpc("sh_morning", p_day=days[0]) == skipped                  # nothing was ever measured
    assert db.rpc("sh_job_due", p_job="morning", p_day=days[0]) is False   # and the day's job is done all the same
    assert db.rpc("sh_morning", p_day=days[0]) == {"n": 0}
    for i in range(359, 0, -1):
        db.probe(now - mins(i))
    db.probe(now - mins(359) - secs(59), "light", ms=None)                 # the oldest round: 5:59:59
    assert db.rpc("sh_morning", p_day=days[1]) == skipped
    assert db.sql("select count(*) from sh_messages") == [(0,)] and db.rpc("sh_alerts_check") == []
    db.probe(now - mins(360), "light", ms=None)                            # six hours, of either kind of round
    assert db.rpc("sh_morning", p_day=days[2]) == {"n": 1}
    assert db.sql("select title from sh_messages") == [("בוקר טוב: האתר תקין",)]
    assert db.rpc("sh_job_due", p_job="morning", p_day=days[3]) is True


def _all_at_once(sessions, fn):
    """Call fn(session) from every session at the same moment; the answers, in no particular order."""
    start, answers = threading.Barrier(len(sessions)), []

    def call(session):
        start.wait()
        answers.append(fn(session))

    threads = [threading.Thread(target=call, args=(s,)) for s in sessions]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(answers) == len(sessions)
    return answers


def test_alerts_check_from_many_sessions_at_once_opens_each_alert_once_and_hands_each_push_to_one(committed):
    db = committed()
    db.setup()
    db.probe(db.now() - secs(5), fail=DEAD)
    answers = _all_at_once([committed() for _ in range(8)], lambda session: session.rpc("sh_alerts_check"))
    assert db.sql("select key, count(*) from sh_alerts group by key order by key") == sorted(
        ("down:" + page, 1) for page in PROBE)
    assert db.sql("select count(*), count(distinct alert_id) from sh_messages") == [(4, 4)]
    handed_out = sorted(m["id"] for answer in answers for m in answer)
    assert handed_out == [i for (i,) in db.sql("select id from sh_messages order by id")]      # each push once
    with pytest.raises(psycopg.errors.UniqueViolation):                  # and the index itself forbids a second open alert
        db.sql("insert into sh_alerts (key, kind, title) values ('down:סל', 'down', 'x')")


def test_owed_pushes_are_claimed_by_exactly_one_of_many_sessions(committed):
    """Sixty pushes are owed and eight workers ask at once, three times over: each time every
    push goes to exactly one of them, whoever it is."""
    db = committed()
    db.setup()
    db.sql("insert into sh_messages (event, kind, title, msg) select 'open', 'התראה', 'הודעה ' || n, 'גוף'"
           " from generate_series(1, 60) n")
    ids = [i for (i,) in db.sql("select id from sh_messages order by id")]
    sessions = [committed() for _ in range(8)]
    for round_ in range(3):
        answers = _all_at_once(sessions, lambda session: session.rpc("sh_alerts_check"))
        assert sorted(m["id"] for answer in answers for m in answer) == ids
        assert _all_at_once(sessions, lambda session: session.rpc("sh_alerts_check")) == [[]] * 8     # within two minutes
        db.sql("update sh_messages set claimed_at = claimed_at - interval '2 minutes'")
    # a sender that reports while others ask: a settled push is never handed out again
    for i in ids[:30]:
        db.rpc("sh_message_sent", p_id=i, p_status=200)
    answers = _all_at_once(sessions, lambda session: session.rpc("sh_alerts_check"))
    assert sorted(m["id"] for answer in answers for m in answer) == ids[30:]


# ================================================================ write functions (spec §7.4)

def test_probe_add_ignores_a_repeated_round_and_beats_on_full_rounds_only(db):
    db.setup()
    assert db.probe(T0 + secs(30), "light", ms=None) == {"n": 4}
    assert flow(db, PROBE_FLOW)["status"] == "אין נתון"                   # a light round is no proof of life
    assert db.probe(T0, fail=DEAD) == {"n": 4}                           # a round of failures still proves the prober ran
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == T0
    assert db.probe(T0, ms=999) == {"n": 0}
    assert db.sql("select count(*), count(*) filter (where ok), max(ms) from sh_probe where kind = 'full'") == [(4, 0, 300)]
    db.probe(T0 - mins(5))                                               # an older round arriving late
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == T0
    assert db.sql("select ms from sh_probe where kind = 'light'") == [(None,)] * 4


def test_probe_add_refuses_rows_that_break_the_contract(db):
    db.setup()
    row = {"page": "סל", "url": URL["סל"], "ok": False, "status": 502}
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="full", p_rows=[row])
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="full",
               p_rows=[dict(row, status=None, fail="http")])              # an HTTP failure has a status
    fails_with(db, psycopg.errors.CheckViolation, "sh_probe", "sh_probe_add", p_round_at=T0, p_kind="quick",
               p_rows=[dict(row, fail="http")])
    assert db.sql("select count(*) from sh_probe") == [(0,)]


def test_speed_add_ignores_a_repeated_run_and_beats_the_flow_of_a_successful_run(db):
    db.setup()
    assert db.run(T0, "בית", None, err="timeout") == {"n": 1}
    assert db.run(T0, SITE + "/a/", None, source="rotation", err="timeout") == {"n": 1}
    assert (flow(db, CORE_FLOW)["status"], flow(db, ROTATION_FLOW)["status"]) == ("אין נתון", "אין נתון")
    assert db.run(T0 + mins(15), "בית", 2399.6, score=63.4, bytes=3400000.0, cls=0.0349, lh_version="13.0.1") == {"n": 1}
    assert db.run(T0 + mins(15), "בית", 9999) == {"n": 0}
    assert db.sql("select lcp_ms, score, bytes, cls from sh_speed where ok") == [(2400, 63, 3400000, decimal.Decimal("0.035"))]
    # the Lighthouse version is kept with the run; a run that came without one has none
    assert db.sql("select ok, lh_version from sh_speed order by ok, url") == [(False, None), (False, None), (True, "13.0.1")]
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == T0 + mins(15)
    assert flow(db, ROTATION_FLOW)["last_at"] is None
    db.run(T0 + mins(20), SITE + "/a/", 3000, source="rotation")
    assert dt.datetime.fromisoformat(flow(db, ROTATION_FLOW)["last_at"]) == T0 + mins(20)
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == T0 + mins(15)


def _site_pages(db):
    return db.sql("select url, active from sh_site_pages order by url")


def test_sitemap_set(db):
    db.setup()
    a, b, c, d = (SITE + "/%s/" % x for x in "abcd")
    assert db.rpc("sh_sitemap_set", p_urls=[a, b, c, a]) == {"n": 3}
    assert _site_pages(db) == [(a, True), (b, True), (c, True)]
    assert flow(db, SITEMAP_FLOW)["status"] == "תקין"

    db.sql("update sh_flows set last_at = null")
    for empty in ([], None):
        fails_with(db, psycopg.errors.RaiseException, "an empty list is refused", "sh_sitemap_set", p_urls=empty)
    assert _site_pages(db) == [(a, True), (b, True), (c, True)]
    assert flow(db, SITEMAP_FLOW)["status"] == "אין נתון"                 # a refused read is no proof of life

    db.rpc("sh_sitemap_set", p_urls=[a, b, d])
    assert _site_pages(db) == [(a, True), (b, True), (c, False), (d, True)]
    db.rpc("sh_sitemap_set", p_urls=[c])
    assert _site_pages(db) == [(a, False), (b, False), (c, True), (d, False)]


def test_rotation_takes_turns(db):
    db.setup()
    pages = [SITE + "/%s/" % x for x in "abcdef"]
    db.rpc("sh_sitemap_set", p_urls=pages + [SITE + "/gone/"])
    db.rpc("sh_sitemap_set", p_urls=pages)                                # /gone/ is no longer on the site
    a, b, c, d, e, f = pages
    assert [db.rpc("sh_rotation_next", p_n=2) for _ in range(6)] == [[a, b], [c, d], [e, f]] * 2
    assert db.rpc("sh_rotation_next", p_n=4) == [a, b, c, d]              # always the ones measured longest ago
    new = SITE + "/new/"
    db.rpc("sh_sitemap_set", p_urls=pages + [new])
    assert db.rpc("sh_rotation_next", p_n=3) == [e, f, new]               # a page never measured goes first
    assert db.rpc("sh_rotation_next", p_n=10) == sorted(pages + [new])
    assert db.rpc("sh_rotation_next", p_n=0) == []
    assert db.sql("select last_measured_at from sh_site_pages where not active") == [(None,)]


def test_rotation_never_takes_a_core_page(db):
    db.setup()
    others = [SITE + "/blog/", SITE + "/contact/"]
    db.rpc("sh_sitemap_set", p_urls=list(URL.values()) + others)          # a sitemap lists the core pages as well
    assert [db.rpc("sh_rotation_next", p_n=3) for _ in range(2)] == [others, others]
    assert db.rpc("sh_rotation_next", p_n=100) == others
    assert db.sql("select count(*) from sh_site_pages where last_measured_at is not null") == [(2,)]
    fewer = example_config()                                              # סל is no longer a core page: it takes turns
    fewer["pages"] = [dict(p, core=p["name"] != "סל") for p in fewer["pages"]]
    db.rpc("sh_setup", p_config=fewer)
    assert db.rpc("sh_rotation_next", p_n=1) == [URL["סל"]]               # never measured: first
    assert db.rpc("sh_rotation_next", p_n=100) == sorted(others + [URL["סל"]])


def test_rotation_skips_pages_another_worker_is_claiming(committed):
    first, second = committed(), committed()
    first.setup()
    pages = [SITE + "/%s/" % x for x in "abcd"]
    first.rpc("sh_sitemap_set", p_urls=pages)
    with first.conn.transaction():                                        # a claim that has not been committed yet
        assert first.rpc("sh_rotation_next", p_n=2) == pages[:2]
        assert second.rpc("sh_rotation_next", p_n=3) == pages[2:]         # no waiting, and not the same pages


def test_issues_set_replaces_the_day_and_the_screen_reads_the_latest_snapshot(db):
    db.setup()
    monday, tuesday = dt.date(2024, 11, 11), dt.date(2024, 11, 12)
    sofa = {"product_id": "7", "issue": "לא במלאי", "name": "ספה", "url": SITE + "/product/sofa/"}
    bed = {"product_id": "8", "issue": "בלי מחיר", "name": "מיטה", "url": SITE + "/product/bed/"}
    assert db.rpc("sh_issues_set", p_snap_date=monday, p_rows=[sofa, bed, dict(sofa, issue="בלי תמונה")]) == {"n": 3}
    again = [sofa, dict(bed, issue="לא במלאי"), dict(sofa, issue="בלי תמונה")]
    assert db.rpc("sh_issues_set", p_snap_date=monday, p_rows=again) == {"n": 3}
    listed = {"issue": "לא במלאי", "name": "ספה", "url": SITE + "/product/sofa/", "snap_date": "2024-11-11"}
    assert db.rpc("sh_product_issues") == [                               # by issue, then by name
        dict(listed, issue="בלי תמונה"), dict(listed, name="מיטה", url=SITE + "/product/bed/"), listed]
    assert flow(db, CATALOGUE_FLOW)["status"] == "תקין"

    assert db.rpc("sh_issues_set", p_snap_date=tuesday, p_rows=[bed]) == {"n": 1}
    assert db.rpc("sh_product_issues") == [
        {"issue": "בלי מחיר", "name": "מיטה", "url": SITE + "/product/bed/", "snap_date": "2024-11-12"}]
    assert db.sql("select count(*) from sh_product_issues") == [(4,)]     # Monday's snapshot is kept, not shown
    assert db.rpc("sh_issues_set", p_snap_date=tuesday, p_rows=[]) == {"n": 0}
    assert db.rpc("sh_product_issues") == []                              # nothing is broken any more


def test_product_issues_list_the_real_faults_first_and_out_of_stock_last(db):
    db.setup()
    rows = [("1", "לא במלאי", "ארון"), ("2", "תמונה שבורה", "כיסא"), ("3", "בלי מחיר", "שולחן"), ("4", "לא במלאי", "Zebra rug"),
            ("5", "בלי מחיר", "apple chair"), ("6", "אי אפשר להוסיף לסל", "מיטה"), ("7", "בלי מחיר", "Zebra rug"),
            ("8", "בלי תמונה", "ספה"), ("9", "לא במלאי", "apple chair"), ("10", "בלי מחיר", "ארון")]
    db.rpc("sh_issues_set", p_snap_date=dt.date(2024, 11, 12),
           p_rows=[{"product_id": i, "issue": issue, "name": name, "url": SITE + "/p/" + i} for i, issue, name in rows])
    # A database whose own order of text is a dictionary's (apple before Zebra) must answer the same.
    if db.sql("select 1 from pg_collation where collname = 'und-x-icu'"):
        db.sql('alter table sh_product_issues alter column issue type text collate "und-x-icu",'
               ' alter column name type text collate "und-x-icu"')
    assert [(r["issue"], r["name"]) for r in db.rpc("sh_product_issues")] == [
        ("אי אפשר להוסיף לסל", "מיטה"),
        ("בלי מחיר", "Zebra rug"), ("בלי מחיר", "apple chair"), ("בלי מחיר", "ארון"), ("בלי מחיר", "שולחן"),
        ("בלי תמונה", "ספה"),
        ("תמונה שבורה", "כיסא"),                                          # after "לא במלאי" in the alphabet, before it here
        ("לא במלאי", "Zebra rug"), ("לא במלאי", "apple chair"), ("לא במלאי", "ארון")]


def test_job_markers(db):
    monday, tuesday = dt.date(2024, 11, 11), dt.date(2024, 11, 12)
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=monday) is True
    assert db.rpc("sh_job_mark", p_job="catalogue", p_day=monday) is True
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=monday) is False
    assert db.rpc("sh_job_mark", p_job="catalogue", p_day=monday) is False       # someone else was first
    assert db.rpc("sh_job_due", p_job="catalogue", p_day=tuesday) is True
    assert db.rpc("sh_job_due", p_job="sitemap", p_day="2024-11-11") is True     # a date may arrive as text


def _ages(db, table, column, label="null::text"):
    """The age of every row of a table in whole days, each with a label, youngest first."""
    return db.sql("select %s, round(extract(epoch from now() - %s) / 86400)::int from %s order by 2, 1" % (label, column, table))


def _aged_rows(db, keep):
    """Rows on both sides of every retention rule, placed in days before now()."""
    db.sql("insert into sh_probe (round_at, kind, page, url, ok) select now() - d * interval '1 day', kind, 'בית', 'u', true"
           " from (values (%s, 'full'), (%s, 'full'), (%s, 'full'), (6, 'light'), (7, 'light'), (8, 'light'), (%s, 'light'))"
           " as v(d, kind)", [keep - 1, keep, keep + 1, keep - 1])
    db.sql("insert into sh_speed (at, url, strategy, source, ok) select now() - d * interval '1 day', 'u', 'mobile', source, true"
           " from (values (%s, 'core'), (%s, 'core'), (%s, 'core'), (44, 'rotation'), (45, 'rotation'), (46, 'rotation'),"
           " (200, 'rotation')) as v(d, source)", [keep - 1, keep, keep + 1])
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) select now() - d * interval '1 day', 'live', '/', 1000"
           " from (values (29), (30), (31), (32)) as v(d)")
    db.sql("insert into sh_login_log (at, ok) select now() - d * interval '1 day', true from (values (399), (400), (401)) as v(d)")


@pytest.mark.parametrize("keep", [100, 30, 400])
def test_cleanup_keeps_what_the_retention_rules_keep(db, keep):
    db.setup() if keep == 100 else db.setup(keep_days=keep)               # 100 is the default
    _aged_rows(db, keep)
    today = db.now().astimezone(TZ).date()
    for age in (29, 30, 31, 45):                                          # catalogue snapshots; the newest is the latest
        db.rpc("sh_issues_set", p_snap_date=today - dt.timedelta(days=age), p_rows=[
            {"product_id": "1", "issue": "בלי מחיר"}, {"product_id": "2", "issue": "לא במלאי"}])
    db.sql("insert into sh_jobs (job, day) select job, %s - d from (values ('morning', 399), ('morning', 400),"
           " ('morning', 401), ('morning', 800), ('sitemap', 900)) as v(job, d)", [today])
    db.sql("insert into sh_alerts (key, kind, title, opened_at, closed_at)"
           " values ('k', 'down', 't', now() - interval '900 days', now() - interval '899 days')")
    db.sql("insert into sh_messages (at, event, kind, title) values (now() - interval '900 days', 'open', 'התראה', 't')")

    assert db.rpc("sh_cleanup") == {"probe": 1, "probe_light": 2, "speed": 3, "rum": 2, "product_issues": 4, "jobs": 2,
                                    "login_log": 1}
    # full rounds and the runs of core pages: keep_days. Light rounds: 7 days. Rotation runs: 45 days.
    assert _ages(db, "sh_probe", "round_at", "kind") == [("light", 6), ("light", 7), ("full", keep - 1), ("full", keep)]
    assert sorted(_ages(db, "sh_speed", "at", "source")) == sorted(
        [("rotation", 44), ("rotation", 45), ("core", keep - 1), ("core", keep)])
    assert _ages(db, "sh_rum", "created_at") == [(None, 29), (None, 30)]
    assert _ages(db, "sh_login_log", "at") == [(None, 399), (None, 400)]
    assert db.sql("select %s - snap_date, count(*) from sh_product_issues group by 1 order by 1", [today]) == [(29, 2), (30, 2)]
    # markers: 400 days, and the newest marker of a job whatever its age; the snapshots' own markers are young
    assert db.sql("select job, %s - day from sh_jobs where job <> 'issues_snapshot' order by 1, 2", [today]) == [
        ("morning", 399), ("morning", 400), ("sitemap", 900)]
    assert [db.sql("select count(*) from " + t)[0][0] for t in ("sh_alerts", "sh_messages")] == [1, 1]      # for good
    assert db.rpc("sh_cleanup") == {"probe": 0, "probe_light": 0, "speed": 0, "rum": 0, "product_issues": 0, "jobs": 0,
                                    "login_log": 0}


def test_cleanup_never_deletes_the_latest_catalogue_snapshot(db):
    db.setup()
    long_ago = [dt.date(2020, 1, 1), dt.date(2020, 1, 2)]
    for day in long_ago:
        db.rpc("sh_issues_set", p_snap_date=day, p_rows=[{"product_id": "1", "issue": "בלי מחיר", "name": "מיטה"}])
    shown = db.rpc("sh_product_issues")
    assert [r["snap_date"] for r in shown] == ["2020-01-02"]
    assert db.rpc("sh_cleanup") == {"probe": 0, "probe_light": 0, "speed": 0, "rum": 0, "product_issues": 1, "jobs": 1,
                                    "login_log": 0}
    assert db.rpc("sh_product_issues") == shown                           # the screen still shows it, with its date
    assert db.sql("select job, day from sh_jobs") == [("issues_snapshot", long_ago[1])]


def test_cleanup_before_the_site_is_set_up_uses_the_default(db):
    assert db.rpc("sh_config")["keep_days"] == 100                        # also a database set up before the setting
    _aged_rows(db, 100)
    assert db.rpc("sh_cleanup") == {"probe": 1, "probe_light": 2, "speed": 3, "rum": 2, "product_issues": 0, "jobs": 0,
                                    "login_log": 1}


def test_rum_add_drops_what_is_outside_the_limits_of_the_ingest(db):
    db.setup()
    long = "/" + "x" * 299
    assert db.rpc("sh_rum_add", p_rows=[{"site": "live", "path": "/", "lcp_ms": 0},
                                        {"site": "live", "path": "/", "lcp_ms": 60001},
                                        {"path": "/", "lcp_ms": 1000}, {"site": "live", "lcp_ms": 1000},
                                        {"site": "Live Site", "path": "/", "lcp_ms": 1000},
                                        {"site": "", "path": "/", "lcp_ms": 1000},
                                        {"site": "a" * 101, "path": "/", "lcp_ms": 1000},
                                        {"site": "live\n", "path": "/", "lcp_ms": 1000},
                                        # more than 120 bytes, also once cut: not sent as a browser sends it
                                        {"site": "live", "path": "/" + "ס" * 60, "lcp_ms": 1000},
                                        {"site": "live", "path": "/" + "\U0001D400" * 300, "lcp_ms": 1000}]) == {"n": 0}
    assert flow(db, RUM_FLOW)["status"] == "אין נתון"
    assert db.rpc("sh_rum_add", p_rows=[
        {"site": "live", "path": "/product/sofa/?email=a@b.co&utm=x#top", "lcp_ms": 1, "is_test": True},
        {"site": "dev.example.co.il", "path": "/cart/", "lcp_ms": 60000},
        {"site": "a" * 100, "path": long + "?" + "q" * 500, "lcp_ms": 300},      # cut at 120; the query string goes first
        {"site": "live", "path": "/" + "ס" * 59, "lcp_ms": 301},                # 119 bytes: kept as it came
        {"site": "live", "path": "/", "lcp_ms": 2400.4}]) == {"n": 5}
    assert db.sql("select site, path, lcp_ms, is_test, created_at = now() from sh_rum order by lcp_ms") == [
        ("live", "/product/sofa/", 1, True, True), ("a" * 100, "/" + "x" * 119, 300, False, True),
        ("live", "/" + "ס" * 59, 301, False, True),
        ("live", "/", 2400, False, True), ("dev.example.co.il", "/cart/", 60000, False, True)]
    assert flow(db, RUM_FLOW)["status"] == "תקין"


# Paths of more than 120 characters, cut by sh_rum_add as the server cuts them before it sends them
CUTS = ["/" + "x" * 119, "/" + "x" * 299, "/" + "x" * 117 + "%D7%A1", "/" + "x" * 118 + "%2F", "/" + "x" * 119 + "%2",
        "/" + "x" * 116 + "%D7%A1%D7%A4", "/" + "x" * 116 + "%d7%a1%d7%a4", "/" + "x" * 113 + "%E2%80%99abc",
        "/" + "x" * 110 + "%F0%9F%98%80" + "z" * 20, "/" + "x" * 111 + "%F0%9F%98%80", "/" + "x" * 113 + "%D7%A1zz",
        "/product/" + "%D7%A1%D7%A4%D7%94-" * 10, "/" + "%D7%A1" * 30 + "?q=" + "y" * 200, "/" + "x" * 118 + "%"]


def test_rum_add_cuts_a_long_path_exactly_as_the_server_does(db):
    if str(REFERENCE) not in sys.path:
        sys.path.insert(0, str(REFERENCE))
    import server

    db.setup()
    rows = [{"site": "live", "path": path, "lcp_ms": n + 1} for n, path in enumerate(CUTS)]
    assert db.rpc("sh_rum_add", p_rows=rows) == {"n": len(CUTS)}
    stored = [path for (path,) in db.sql("select path from sh_rum order by lcp_ms")]
    assert stored == [server._cut_path(re.split("[?#]", path, maxsplit=1)[0]) for path in CUTS]
    assert all(len(path) <= 120 for path in stored) and stored[:4] == [
        "/" + "x" * 119, "/" + "x" * 119, "/" + "x" * 117, "/" + "x" * 118]


def test_rum_add_stores_nothing_once_a_day_holds_30000_rows(db):
    """The ingest is open to the internet; a full database would stop storing probes and alerts too."""
    db.setup()
    views = [{"site": "live", "path": "/", "lcp_ms": 1000}] * 3
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) select now() - interval '23 hours 59 minutes', 'live', '/', 1000"
           " from generate_series(1, 29999)")
    db.sql("insert into sh_rum (created_at, site, path, lcp_ms) select now() - interval '24 hours', 'live', '/', 1000"
           " from generate_series(1, 5000)")                              # yesterday's do not count
    assert db.rpc("sh_rum_add", p_rows=views) == {"n": 3}                 # the last batch that still found room
    db.sql("update sh_flows set last_at = null")
    assert db.rpc("sh_rum_add", p_rows=views) == {"n": 0}
    assert db.sql("select count(*) from sh_rum where created_at > now() - interval '24 hours'") == [(30002,)]
    assert flow(db, RUM_FLOW)["status"] == "אין נתון"                     # a refused batch is no proof of life
    db.sql("update sh_rum set created_at = created_at - interval '2 minutes'")       # the oldest leave the last 24 hours
    assert db.rpc("sh_rum_add", p_rows=views) == {"n": 3}
    assert flow(db, RUM_FLOW)["status"] == "תקין"


def test_cert_set_and_read(db):
    db.setup()
    assert db.rpc("sh_cert") is None
    now = db.now()
    assert _cert(db, 23) == {"n": 1}
    cert = db.rpc("sh_cert")
    assert {k: v for k, v in cert.items() if k not in ("not_after", "checked_at")} == {
        "host": "example.co.il", "issuer": "Let's Encrypt R11", "days_left": 23, "ok": True, "err": None}
    assert dt.datetime.fromisoformat(cert["not_after"]) == dt.datetime(2024, 11, 30, tzinfo=UTC)
    assert dt.datetime.fromisoformat(cert["checked_at"]) == now
    assert flow(db, CERT_FLOW)["status"] == "תקין"

    db.sql("update sh_flows set last_at = null")
    _cert(db, None, ok=False, err="certificate verify failed")
    cert = db.rpc("sh_cert")
    assert (cert["ok"], cert["err"], cert["days_left"], cert["issuer"]) == (
        False, "certificate verify failed", 23, "Let's Encrypt R11")
    assert flow(db, CERT_FLOW)["status"] == "אין נתון"                    # a failed check is no proof of life
    db.rpc("sh_cert_set", p_row={"host": "example.co.il", "ok": True, "days_left": 80, "checked_at": "2024-11-12T07:00:00Z"})
    cert = db.rpc("sh_cert")
    assert (cert["ok"], cert["err"], cert["days_left"]) == (True, None, 80)
    assert dt.datetime.fromisoformat(cert["checked_at"]) == T0


def test_login_log_and_ping(db):
    assert db.rpc("sh_ping") == "ok"
    assert db.rpc("sh_login_log_add", p_ip="203.0.113.7", p_ok=False, p_who=None, p_ua="Mozilla/5.0") == {"n": 1}
    assert db.rpc("sh_login_log_add", p_ip="203.0.113.7", p_ok=True, p_who="owner", p_ua="Mozilla/5.0") == {"n": 1}
    assert db.sql("select ip, ok, who, ua, at = now() from sh_login_log order by ok") == [
        ("203.0.113.7", False, None, "Mozilla/5.0", True), ("203.0.113.7", True, "owner", "Mozilla/5.0", True)]


# ================================================================ the simulator against an independent calculation

def test_a_simulated_day_matches_an_independent_calculation(db):
    db.setup()
    start = T0 - mins(120)                                                # 07:00 local: the day crosses local midnight
    data = sim.simulate(db.rpc, start, 1, fail_hour=("קטגוריה", T0, 6), dead=(T0 + mins(200), 7),
                        slow=("מוצר", T0 + mins(300), 5))
    window = dict(p_from=start, p_to=start + mins(1440))
    full = [r for r in data["probe"] if r["kind"] == "full"]
    assert len(full) == 4 * 1440 and len(data["probe"]) == 8 * 1440

    rows = db.rpc("sh_availability", **window)
    for page, row in zip(PROBE, rows):
        mine = [r for r in full if r["page"] == page]
        answered = [r["ms"] for r in mine if r["ok"]]
        failed = [r for r in mine if not r["ok"]]
        assert row == {"section": "לפי עמוד", "page": page, "checks": 1440, "failed": len(failed),
                       "fail_pct": "%.2f" % (100 * len(failed) / 1440),
                       "p50_ms": half_up(percentile(answered, 0.5)), "p95_ms": half_up(percentile(answered, 0.95)),
                       "last_fail_il": il(max(r["round_at"] for r in failed))}
    assert [r["failed"] for r in rows[:4]] == [7, 13, 7, 7]               # the outage, and six more for קטגוריה
    assert rows[4:] == [{"section": "נפילות", "outage_minutes": 7, "outage_start_il": il(T0 + mins(200)),
                         "outage_end_il": il(T0 + mins(207))}]

    series = db.rpc("sh_availability_series", **window)
    assert len(series) == 24
    for row in series:
        mine = [r for r in full if r["round_at"].astimezone(TZ).strftime("%Y-%m-%d %H:00") == row["bucket"]]
        answered = [r["ms"] for r in mine if r["ok"]]
        assert row == {"bucket": row["bucket"], "checks": 240, "failed": sum(not r["ok"] for r in mine),
                       "ms_p50": half_up(percentile(answered, 0.5)), "ms_p95": half_up(percentile(answered, 0.95))}
    assert sum(r["failed"] for r in series) == 34

    speed = db.rpc("sh_speed", **window)
    good = [r for r in data["speed"] if r["ok"]]
    core = section(speed, "ליבה")
    assert [(r["strategy"], r["page"]) for r in core] == [(s, p) for s in ("mobile", "desktop") for p in URL]
    for row in core:
        mine = [r for r in good if r["page"] == row["page"] and r["strategy"] == row["strategy"]]
        newest = max(mine, key=lambda r: r["at"])
        assert row == {"section": "ליבה", "strategy": row["strategy"], "page": row["page"], "url": URL[row["page"]],
                       "lcp_p50": half_up(percentile([r["lcp_ms"] for r in mine], 0.5)),
                       "lcp_p95": half_up(percentile([r["lcp_ms"] for r in mine], 0.95)),
                       "score_med": half_up(percentile([r["score"] for r in mine], 0.5)),
                       "cls_med": round(percentile([r["cls"] for r in mine], 0.5), 3),
                       "ttfb_p50": half_up(percentile([r["ttfb_ms"] for r in mine], 0.5)),
                       "slow_runs": sum(r["lcp_ms"] > 4000 for r in mine), "checks": len(mine),
                       "crux_category": newest["crux_category"], "crux_lcp": newest["crux_lcp_ms"]}
    by_page = {(r["strategy"], r["page"]): r for r in core}
    assert (by_page["mobile", "מוצר"]["slow_runs"], by_page["mobile", "קטגוריה"]["checks"]) == (5, 94)   # 2 of 96 runs failed
    home = by_page["mobile", "בית"]
    assert section(speed, "שורה תחתונה") == [{"section": "שורה תחתונה", "page": "בית", "url": URL["בית"],
                                              "lcp_p50": home["lcp_p50"], "checks": 96,
                                              "verdict": mock.verdict(home["lcp_p50"])}]
    rotation = {}
    for r in good:
        if r["source"] == "rotation":
            rotation.setdefault(r["url"], []).append(r)
    heaviest = sorted(rotation, key=lambda u: (-percentile([r["lcp_ms"] for r in rotation[u]], 0.5), u))[:10]
    assert [(r["url"], r["lcp_p50"], r["checks"], r["last_il"]) for r in section(speed, "האיטיים באתר")] == [
        (u, half_up(percentile([r["lcp_ms"] for r in rotation[u]], 0.5)), len(rotation[u]),
         il(max(r["at"] for r in rotation[u]))) for u in heaviest]
    assert all(len(runs) in (14, 15) for runs in rotation.values())      # 576 runs over 40 pages, in turns
    assert section(speed, "כיסוי") == [{"section": "כיסוי", "checks": 40, "slow_runs": 40}]

    series = db.rpc("sh_speed_series", p_strategy="mobile", **window)
    assert len(series) == 5 * 24
    for row in series:
        mine = [r["lcp_ms"] for r in good if r["page"] == row["page"] and r["strategy"] == "mobile"
                and r["at"].astimezone(TZ).strftime("%Y-%m-%d %H:00") == row["bucket"]]
        assert row["lcp_p50"] == half_up(percentile(mine, 0.5))

    # the flows the simulator fed are alive up to its last measurement
    assert dt.datetime.fromisoformat(flow(db, PROBE_FLOW)["last_at"]) == start + mins(1439)
    assert dt.datetime.fromisoformat(flow(db, CORE_FLOW)["last_at"]) == start + mins(1425)
    assert dt.datetime.fromisoformat(flow(db, ROTATION_FLOW)["last_at"]) == start + mins(1435)


# ================================================================ the same shapes as the mock backend (spec §5)

def _shape(row):
    """The keys of a row and the kind of each value that is not null."""
    kinds = {bool: "bool", int: "number", float: "number", str: "text", list: "list", dict: "object"}
    return {k: kinds[type(v)] for k, v in row.items() if v is not None}


def _same_shape(mine, theirs):
    """Same keys; and where both have a value, the same kind of value."""
    assert set(mine) == set(theirs), (sorted(mine), sorted(theirs))
    a, b = _shape(mine), _shape(theirs)
    assert {k: a[k] for k in a if k in b} == {k: b[k] for k in a if k in b}


@pytest.fixture
def busy(db):
    """A database with something in every part of the screen: a simulated day that ends now,
    an alert that opened and closed, one that is still open, and the daily snapshots."""
    db.setup()
    now = db.now()
    minute = now.replace(second=0, microsecond=0)
    sim.simulate(db.rpc, minute - mins(1440), 1, light=False,
                 dead=(minute - mins(600), 7), fail_hour=("סל", minute - mins(180), 3))
    sim.snapshot(db.rpc, now.date())
    db.probe(now - secs(3), fail={"סל": 502})
    pushes = db.rpc("sh_alerts_check")
    db.sql("update sh_alerts set opened_at = now() - interval '9 minutes'")
    db.probe(now - secs(2))
    for message in pushes + db.rpc("sh_alerts_check"):
        db.rpc("sh_message_sent", p_id=message["id"], p_status=200)
    db.probe(now - secs(1), fail={"מוצר": 502})
    db.rpc("sh_alerts_check")
    return db


def test_site_parts_have_the_shapes_of_the_mock(busy, monkeypatch):
    db, now = busy, busy.now()
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    theirs = mock.api_site({"h": "24", "strategy": "mobile"}, "owner")
    window = dict(p_from=now - mins(1440), p_to=now + mins(1))

    mine = db.rpc("sh_availability", **window)
    for name in ("לפי עמוד", "נפילות"):
        assert section(mine, name) and section(theirs["availability"], name)
        _same_shape(section(mine, name)[0], section(theirs["availability"], name)[0])
    _same_shape(db.rpc("sh_availability_series", **window)[0], theirs["availability_series"][0])
    mine = db.rpc("sh_speed", **window)
    for name in ("שורה תחתונה", "ליבה", "האיטיים באתר", "כיסוי"):
        _same_shape(section(mine, name)[0], section(theirs["speed"], name)[0])
    _same_shape(db.rpc("sh_speed_series", p_strategy="mobile", **window)[0], theirs["speed_series"][0])
    _same_shape(db.rpc("sh_alerts_open")[0], theirs["alerts_open"][0])
    recent = db.rpc("sh_alerts_range", **window)
    assert [a["open"] for a in recent] == [True, False]
    _same_shape(recent[0], next(a for a in theirs["alerts_recent"] if a["open"]))
    _same_shape(recent[1], next(a for a in theirs["alerts_recent"] if not a["open"]))
    health = db.rpc("sh_health")
    assert [r["flow_name"] for r in health] == [r["flow_name"] for r in theirs["health"]]
    for a, b in zip(health, theirs["health"]):
        _same_shape(a, b)
    _same_shape(db.rpc("sh_product_issues")[0], theirs["product_issues"][0])
    _same_shape(db.rpc("sh_cert"), theirs["cert"])


def test_now_has_the_shape_of_the_mock(busy, monkeypatch):
    db = busy
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    theirs, mine = mock.api_now("owner"), db.rpc("sh_now")
    _same_shape(mine, theirs)
    _same_shape(mine["pages"][0], theirs["pages"][0])
    # the mock hands its "pages" rows out again as "latest"; spec §5.3 defines {page, ok} and the
    # screen reads nothing else from them
    assert set(mine["latest"][0]) == {"page", "ok"} <= set(theirs["latest"][0])
    for part in ("rum", "speed", "rum_src"):
        _same_shape(mine[part], theirs[part])
    _same_shape(mine["rum_src"]["hosts"][0], theirs["rum_src"]["hosts"][0])


def test_drills_and_messages_have_the_shapes_of_the_mock(busy, monkeypatch):
    db, now = busy, busy.now()
    monkeypatch.setitem(mock.STATE, "scenario", "incident")
    window = dict(p_from=now - mins(1440), p_to=now + mins(1))

    def theirs(what, **q):
        return mock.api_drill(dict(q, what=what, h="24"), "owner")["rows"]

    fails = db.rpc("sh_drill_fails", **window)
    for kind in {r["kind"] for r in fails}:
        _same_shape(next(r for r in fails if r["kind"] == kind), theirs("fails")[0])
    bucket = db.rpc("sh_availability_series", **window)[5]["bucket"]
    _same_shape(db.rpc("sh_drill_bucket", p_bucket=bucket)[0], theirs("bucket", bucket=bucket)[0])
    runs, their_runs = db.rpc("sh_drill_runs", p_url=URL["קטגוריה"], **window), theirs("runs", url=URL["קטגוריה"])
    for ok in (True, False):
        _same_shape(next(r for r in runs if r["ok"] is ok), next(r for r in their_runs if r["ok"] is ok))
    _same_shape(runs[0]["opps"][0], their_runs[0]["opps"][0])
    closed = next(a for a in db.rpc("sh_alerts_range", **window) if not a["open"])
    mine, their = db.rpc("sh_drill_alert", p_id=closed["id"])[0], theirs("alert", id="38")[0]
    _same_shape(mine, their)
    _same_shape(mine["fails"][0], their["fails"][1])
    assert [s["event"] for s in mine["sent"]] == ["open", "close"] == [s["event"] for s in their["sent"]]
    _same_shape(mine["sent"][0], their["sent"][0])
    messages = db.rpc("sh_messages", **window)
    assert [(m["kind"], m["sent"]) for m in messages] == [("התראה", False), ("חזר לתקין", True), ("התראה", True)]
    for row in messages:
        _same_shape(row, mock.api_messages({})["rows"][0])


# ================================================================ the SQL files themselves

READ = ["sh_availability", "sh_availability_series", "sh_speed", "sh_speed_series", "sh_alerts_open", "sh_alerts_range",
        "sh_health", "sh_product_issues", "sh_cert", "sh_now", "sh_drill_fails", "sh_drill_bucket", "sh_drill_runs",
        "sh_drill_alert", "sh_messages", "sh_ping", "sh_config", "sh_job_due"]
WRITE = ["sh_alert_ack", "sh_login_log_add", "sh_rum_add", "sh_setup", "sh_probe_add", "sh_speed_add", "sh_rotation_next",
         "sh_sitemap_set", "sh_cert_set", "sh_issues_set", "sh_job_mark", "sh_alerts_check", "sh_message_sent",
         "sh_morning", "sh_cleanup"]
API = READ + WRITE                                                        # the 33 functions of spec §7.3 and §7.4
HELPERS = ["sh_tz", "sh_il", "sh_bucket_fmt", "sh_fail_kind", "sh_span", "sh_minutes", "sh_url", "sh_off", "sh_verdict",
           "sh_alert_row"]


def test_every_function_of_the_spec_exists_with_the_agreed_form(db):
    found = {name: rest for name, *rest in db.sql(
        r"select proname::text, prorettype::regtype::text, provolatile::text, proconfig, coalesce(proargnames, '{}')"
        r" from pg_proc where pronamespace = 'public'::regnamespace and proname like 'sh\_%'")}
    assert set(found) == set(API) | set(HELPERS)
    for name, (returns, volatility, settings, parameters) in found.items():
        assert settings == ["search_path=public"], name
        assert all(p.startswith("p_") for p in parameters), name
        if name in API:
            assert returns == "jsonb", name
            assert (volatility == "s") == (name in READ), name


def test_schema_and_functions_can_be_applied_again(committed):
    db = committed()
    db.setup()
    db.probe(T0, fail={"סל": 502})
    db.run(T0, "בית", 2400)
    before = (db.rpc("sh_config"), db.rpc("sh_health"), db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1)))
    apply_sql(db.conn)
    apply_sql(db.conn)
    assert (db.rpc("sh_config"), db.rpc("sh_health"), db.rpc("sh_availability", p_from=T0, p_to=T0 + mins(1))) == before


def test_schema_upgrades_a_database_of_the_first_version_and_keeps_its_data(db):
    """The tables as the first version made them (the columns added since are dropped again),
    with data in them and a site set up by that version; then both files are applied."""
    db.setup()
    now = db.now()
    db.probe(now - secs(30), fail={"סל": 502})
    db.run(now - mins(5), "בית", 2400, score=64)
    db.sql("insert into sh_alerts (key, kind, title, opened_at) values (%s, 'silent', 'המדידה נעצרה', now() - interval '1 hour')",
           ["silent:" + RUM_FLOW])                                        # the first version alerted on quiet nights
    db.sql("insert into sh_messages (event, kind, title, msg) values ('open', 'התראה', 'הודעה ישנה', 'גוף')")
    db.ran(RUM_FLOW, hours=7)
    db.ran(SITEMAP_FLOW, hours=3)
    db.sql("alter table sh_speed drop column lh_version")
    db.sql("alter table sh_messages drop column claimed_at")
    db.sql("alter table sh_flows drop column alerts")
    db.sql("update sh_flows set warn_minutes = 120, late_minutes = 360 where flow_name = %s", [RUM_FLOW])
    db.sql("delete from sh_settings where key in ('keep_days', 'rum_hosts', 'private_paths', 'off', 'extra_hosts',"
           " 'hide', 'nav', 'links')")
    before = (db.sql("select * from sh_probe order by page"), db.sql("select at, url, lcp_ms, score from sh_speed"),
              db.sql("select id, title from sh_messages"), db.sql("select flow_name, last_at from sh_flows order by sort"),
              db.rpc("sh_availability", p_from=now - mins(60), p_to=now))

    apply_sql(db.conn)

    assert db.sql("""select table_name::text, column_name::text, data_type::text, is_nullable::text, column_default::text
                     from information_schema.columns
                     where table_schema = 'public' and column_name in ('lh_version', 'claimed_at', 'alerts') order by 1""") == [
        ("sh_flows", "alerts", "boolean", "NO", "true"), ("sh_messages", "claimed_at", "timestamp with time zone", "YES", None),
        ("sh_speed", "lh_version", "text", "YES", None)]
    assert before == (db.sql("select * from sh_probe order by page"), db.sql("select at, url, lcp_ms, score from sh_speed"),
                      db.sql("select id, title from sh_messages"), db.sql("select flow_name, last_at from sh_flows order by sort"),
                      db.rpc("sh_availability", p_from=now - mins(60), p_to=now))               # nothing was lost
    assert db.sql("select lh_version from sh_speed") == [(None,)] and db.sql("select claimed_at from sh_messages") == [(None,)]
    # the real-user flow as the current version seeds it; the other flows untouched
    assert db.sql("select flow_name, alerts, warn_minutes, late_minutes from sh_flows order by sort") == [
        (name, name != RUM_FLOW, warn, late) for name, _, warn, late in FLOWS]
    config = db.rpc("sh_config")                                          # the new settings read as their defaults
    assert (config["keep_days"], config["rum_hosts"], config["private_paths"], config["time_zone"]) == (
        100, [], [], "Asia/Jerusalem")
    assert (config["off"], config["extra_hosts"], config["hide"], config["nav"], config["links"]) == ([], [], [], [], [])
    # and the functions work on it: the old push is handed out, the real-user alert closes, the page's alert opens
    assert sorted((m["event"], m["title"]) for m in db.rpc("sh_alerts_check")) == [
        ("close", "חזר לתקין: " + RUM_FLOW), ("open", "האתר לא עונה: סל"), ("open", "הודעה ישנה")]
    assert flow(db, RUM_FLOW)["status"] == "מתעכב" and db.rpc("sh_cleanup")["probe"] == 0
    db.run(now, "בית", 2500, lh_version="13.0.1")
    assert db.sql("select lh_version from sh_speed order by at") == [(None,), ("13.0.1",)]

    # the change of the real-user flow is made once: a later choice by hand survives the next upgrade
    db.sql("update sh_flows set alerts = true, late_minutes = 720 where flow_name = %s", [RUM_FLOW])
    apply_sql(db.conn)
    assert db.sql("select alerts, late_minutes from sh_flows where flow_name = %s", [RUM_FLOW]) == [(True, 720)]


def test_functions_sql_ends_by_telling_postgrest_to_reload_its_list_of_functions(committed):
    functions = (REFERENCE / "functions.sql").read_text(encoding="utf-8")
    assert functions.rstrip().endswith("\nnotify pgrst, 'reload schema';")
    listener, sender = committed(), committed()
    listener.sql("listen pgrst")
    sender.conn.execute(functions)
    assert [(n.channel, n.payload) for n in listener.conn.notifies(timeout=10, stop_after=1)] == [("pgrst", "reload schema")]


def test_tables_and_functions_are_private(db):
    assert db.sql(r"select count(*), count(*) filter (where relrowsecurity) from pg_class"
                  r" where relnamespace = 'public'::regnamespace and relkind = 'r' and relname like 'sh\_%'") == [(13, 13)]
    assert db.sql("select count(*) from pg_policies where schemaname = 'public'") == [(0,)]
    db.sql("create role sh_test_visitor")                                 # rolled back with the test
    db.sql("set local role sh_test_visitor")
    for call in ("select sh_ping()", "select sh_now()", "select sh_tz()", "select * from sh_probe"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.conn.transaction():
                db.sql(call)


def _call_every_function(db):
    """One call of each function of the API, as the server and the collectors make them. The
    answers are checked elsewhere; here every call must get through."""
    now = db.now()
    window = dict(p_from=now - mins(60), p_to=now + mins(1))
    called = set()

    def call(fn, **params):
        called.add(fn)
        return db.rpc(fn, **params)

    call("sh_setup", p_config=example_config())
    call("sh_probe_add", p_round_at=now - mins(400), p_kind="full", p_rows=[
        {"page": "סל", "url": URL["סל"], "ok": True, "status": 200, "ms": 300}])
    call("sh_probe_add", p_round_at=now - secs(30), p_kind="full", p_rows=[
        {"page": "סל", "url": URL["סל"], "ok": False, "status": 502, "fail": "http", "ms": 300}])
    call("sh_speed_add", p_rows=[{"at": (now - mins(5)).isoformat(), "url": URL["בית"], "page": "בית", "strategy": "mobile",
                                  "source": "core", "ok": True, "lcp_ms": 2400}])
    call("sh_sitemap_set", p_urls=[SITE + "/a/", SITE + "/b/"])
    assert call("sh_rotation_next", p_n=1) == [SITE + "/a/"]
    call("sh_cert_set", p_row={"host": "example.co.il", "ok": True, "days_left": 80})
    call("sh_issues_set", p_snap_date=now.date(), p_rows=[{"product_id": "1", "issue": "בלי מחיר", "name": "מיטה"}])
    assert call("sh_rum_add", p_rows=[{"site": "live", "path": "/", "lcp_ms": 1800}]) == {"n": 1}
    assert call("sh_job_due", p_job="sitemap", p_day=now.date()) is True
    assert call("sh_job_mark", p_job="sitemap", p_day=now.date()) is True
    (push,) = call("sh_alerts_check")                                     # two identity columns: sh_alerts, sh_messages
    assert push["title"] == "האתר לא עונה: סל"
    assert call("sh_message_sent", p_id=push["id"], p_status=200) == {"n": 1}
    assert call("sh_morning", p_day=now.date()) == {"n": 1}
    (alert,) = call("sh_alerts_open")
    assert call("sh_alert_ack", p_ids=[alert["id"]], p_who="owner") == {"n": 1}
    assert call("sh_login_log_add", p_ip="203.0.113.7", p_ok=True, p_who="owner", p_ua="Mozilla/5.0") == {"n": 1}
    assert call("sh_now")["alerts_open"] == 1 and len(call("sh_health")) == 7
    for fn in ("sh_availability", "sh_availability_series", "sh_speed", "sh_alerts_range", "sh_drill_fails", "sh_messages"):
        assert call(fn, **window)
    assert call("sh_speed_series", p_strategy="mobile", **window)
    assert call("sh_drill_runs", p_url=URL["בית"], **window)
    assert call("sh_drill_bucket", p_bucket=now.astimezone(TZ).strftime("%Y-%m-%d"))
    assert call("sh_drill_alert", p_id=alert["id"])
    assert call("sh_product_issues") and call("sh_cert")["days_left"] == 80
    assert call("sh_config")["time_zone"] == "Asia/Jerusalem" and call("sh_ping") == "ok"
    assert set(call("sh_cleanup")) == {"probe", "probe_light", "speed", "rum", "product_issues", "jobs", "login_log"}
    assert called == set(API)


@pytest.mark.parametrize("default_grants", [True, False],
                         ids=["a project that hands out default grants", "a project that hands out none"])
def test_on_supabase_only_the_service_role_gets_in(db, default_grants):
    """A Supabase project used to grant every new table, sequence and function to its three API
    roles; a newer one grants no table by itself. The two files must end in the same place from
    both: nothing for anon and authenticated, everything the functions need for the service role.
    The three roles exist (or change) only inside this test's transaction: nothing is left on the server."""
    roles = ("anon", "authenticated", "service_role")
    for role in roles:
        if not db.sql("select 1 from pg_roles where rolname = %s", [role]):
            db.sql("create role %s" % role)
    db.sql("alter role service_role bypassrls")                           # as on Supabase
    for kind in ("tables", "sequences", "functions"):
        db.sql("revoke all on all %s in schema public from anon, authenticated, service_role" % kind)
        if default_grants:
            db.sql("grant all on all %s in schema public to anon, authenticated, service_role" % kind)
    apply_sql(db.conn)

    def may(role):
        """How many of the sh_* functions the role may run, of the tables it may read and write,
        and of the sequences it may use."""
        return db.sql(r"""
            select (select count(*) from pg_proc
                    where pronamespace = 'public'::regnamespace and proname like 'sh\_%%'
                      and has_function_privilege(%(role)s, oid, 'execute')),
                   (select count(*) from pg_class
                    where relnamespace = 'public'::regnamespace and relkind = 'r' and relname like 'sh\_%%'
                      and has_table_privilege(%(role)s, oid, 'select, insert, update, delete')),
                   (select count(*) from pg_sequences
                    where schemaname = 'public' and sequencename like 'sh\_%%'
                      and has_sequence_privilege(%(role)s, format('public.%%I', sequencename), 'usage, select, update'))""",
                      {"role": role})[0]

    assert db.sql(r"select count(*) from pg_sequences where schemaname = 'public' and sequencename like 'sh\_%'") == [(2,)]
    assert [may(role)[:2] for role in roles] == [(0, 0), (0, 0), (len(API) + len(HELPERS), 13)]
    assert [may(role)[2] for role in roles[:2]] == [0, 0]

    db.sql("set local role service_role")                                 # and the service role can do its whole job
    _call_every_function(db)
    db.sql("set local role anon")
    for call in ("select sh_now()", "select * from sh_alerts", "select nextval('sh_alerts_id_seq')",
                 "select last_value from sh_messages_id_seq"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with db.conn.transaction():
                db.sql(call)


# ================================================================ deadman.sql, against stand-ins

# pg_cron, pg_net and Vault as far as deadman.sql touches them: the same names and parameters,
# doing nothing but remembering what they were asked.
STAND_INS = """
create schema cron;
create schema net;
create schema vault;
create table cron.job (jobid bigserial primary key, jobname text unique, schedule text, command text,
                       active boolean not null default true);
create table cron.job_run_details (jobid bigint, end_time timestamptz);
create function cron.schedule(job_name text, schedule text, command text) returns bigint language sql as $$
  insert into cron.job (jobname, schedule, command) values (job_name, schedule, command)
  on conflict (jobname) do update set schedule = excluded.schedule, command = excluded.command
  returning jobid
$$;
create table net._http_response (id bigint primary key, status_code int, timed_out boolean, error_msg text,
                                 created timestamptz not null default now());
create table net.asked (id bigserial primary key, url text, body jsonb, headers jsonb, timeout_milliseconds int);
create function net.http_post(url text, body jsonb default '{}', params jsonb default '{}',
                              headers jsonb default '{}', timeout_milliseconds int default 5000)
returns bigint language sql as $$
  insert into net.asked (url, body, headers, timeout_milliseconds) values (url, body, headers, timeout_milliseconds)
  returning id
$$;
create table vault.decrypted_secrets (name text primary key, decrypted_secret text);
"""


def _apply_deadman(db):
    """deadman.sql on top of the stand-ins, without its two "create extension" lines."""
    text, extensions = re.subn(r"(?m)^create extension [^;]*;\n", "", (REFERENCE / "deadman.sql").read_text(encoding="utf-8"))
    assert extensions == 2
    db.conn.execute(STAND_INS)
    db.conn.execute(text)


def _asked(db):
    """What sh_deadman handed to pg_net, oldest first."""
    return db.sql("select url, body, headers, timeout_milliseconds from net.asked order by id")


def test_deadman_opens_the_alert_after_ten_silent_minutes_and_pushes_it_once(db):
    db.setup()
    _apply_deadman(db)
    assert db.sql("select jobname, schedule, command from cron.job order by jobid")[0] == (
        "sh-deadman", "*/5 * * * *", "select public.sh_deadman()")
    assert db.sql("select count(*) from cron.job") == [(2,)]              # and the job that trims pg_cron's own log
    db.sql("insert into vault.decrypted_secrets values ('sh_ntfy_topic', ' topic-x '), ('sh_dashboard_url', 'https://dash.example/')")
    quiet = {"opened": None, "closed": None, "published": 0}
    now = db.now()
    assert db.rpc("sh_deadman") == quiet                                  # the prober never ran: not judged
    db.probe(now - mins(10))
    assert db.rpc("sh_deadman") == quiet                                  # exactly ten minutes: not yet

    db.sql("update sh_flows set last_at = last_at - interval '30 seconds'")
    fired = db.rpc("sh_deadman")
    assert fired == {"opened": fired["opened"], "closed": None, "published": 1} and fired["opened"]
    push = {"topic": "topic-x", "title": "המדידה נעצרה: " + PROBE_FLOW, "message": "אין מדידה כבר 10 דקות", "priority": 4,
            "tags": ["rotating_light"], "click": "https://dash.example/site"}
    assert _asked(db) == [("https://ntfy.sh/", push, {"Content-Type": "application/json"}, 10000)]
    assert db.rpc("sh_alerts_open") == [{"id": fired["opened"], "kind": "silent", "title": "המדידה נעצרה: " + PROBE_FLOW,
                                         "body": "אין מדידה כבר 10 דקות", "opened_il": il(now), "acked": False}]
    # until ntfy's answer is read nobody sends it a second time: not the next run, not the worker
    assert db.rpc("sh_deadman") == quiet and db.rpc("sh_alerts_check") == []
    assert len(_asked(db)) == 1 and len(_open(db)) == 1
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1))[0]["sent"] is False

    # ntfy refused it: a failed attempt, and the push leaves again at once
    db.sql("insert into net._http_response (id, status_code) select request_id, 500 from sh_deadman_push")
    assert db.rpc("sh_deadman") == dict(quiet, published=1)
    assert [body for _, body, _, _ in _asked(db)] == [push, push]
    assert db.sql("select status, attempts from sh_messages") == [(None, 1)]
    # this time it was accepted: the log says sent, and nothing is left to do
    db.sql("insert into net._http_response (id, status_code) select request_id, 200 from sh_deadman_push")
    assert db.rpc("sh_deadman") == quiet
    assert db.sql("select status, attempts from sh_messages") == [(200, 2)]
    assert db.sql("select count(*) from sh_deadman_push") == [(0,)]
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1))[0]["sent"] is True

    # the worker is back: a full round newer than the alert closes it, and the recovery is pushed
    db.sql("update sh_alerts set opened_at = now() - interval '12 minutes'")
    db.probe(now - secs(30))
    assert db.rpc("sh_deadman") == {"opened": None, "closed": fired["opened"], "published": 1}
    assert _asked(db)[-1][1] == {"topic": "topic-x", "title": "חזר לתקין: " + PROBE_FLOW,
                                 "message": "המדידה נעצרה: " + PROBE_FLOW + "\nנמשך 12 דקות", "priority": 2,
                                 "tags": ["white_check_mark"], "click": "https://dash.example/site"}
    assert db.rpc("sh_alerts_open") == [] and db.rpc("sh_deadman") == quiet


def test_deadman_without_a_topic_still_opens_the_alert_and_logs_its_message_as_not_sent(db):
    db.setup()
    _apply_deadman(db)
    now = db.now()
    db.probe(now - mins(11))
    fired = db.rpc("sh_deadman")
    assert fired["opened"] and fired["published"] == 0 and _asked(db) == []
    assert _open(db) == [("silent", "המדידה נעצרה: " + PROBE_FLOW)]
    assert db.rpc("sh_messages", p_from=now, p_to=now + mins(1)) == [
        {"kind": "התראה", "title": "המדידה נעצרה: " + PROBE_FLOW, "msg": "אין מדידה כבר 11 דקות", "at_il": il(now), "sent": False}]
    assert db.sql("select status from sh_messages") == [(0,)]
    db.setup(off=[])                                                      # setting the site up again changes nothing here
    db.sql("update sh_flows set enabled = false where flow_name = %s", [PROBE_FLOW])
    db.sql("update sh_alerts set closed_at = now()")
    assert db.rpc("sh_deadman") == {"opened": None, "closed": None, "published": 0}       # a flow that is off is not judged


def test_deadman_stays_with_the_owner_in_whatever_order_the_files_are_applied(db):
    """Only the database's own job runs sh_deadman: the service role is not given it, also when
    functions.sql and schema.sql are applied again after deadman.sql (an upgrade)."""
    for role in ("anon", "authenticated", "service_role"):
        if not db.sql("select 1 from pg_roles where rolname = %s", [role]):
            db.sql("create role %s" % role)
    db.sql("alter default privileges in schema public grant all on tables to anon, authenticated, service_role")
    db.sql("alter default privileges in schema public grant all on functions to anon, authenticated, service_role")
    _apply_deadman(db)

    def may():
        return db.sql("select r, has_function_privilege(r, 'sh_deadman()', 'execute'),"
                      " has_table_privilege(r, 'sh_deadman_push', 'select, insert, update, delete')"
                      " from unnest(array['anon', 'authenticated', 'service_role']) r")

    nobody = [("anon", False, False), ("authenticated", False, False), ("service_role", False, False)]
    assert may() == nobody
    apply_sql(db.conn)
    assert may() == nobody
    assert db.sql("select has_function_privilege('service_role', 'sh_alerts_check()', 'execute'),"
                  " has_table_privilege('service_role', 'sh_alerts', 'select')") == [(True, True)]
    assert db.sql("select relrowsecurity from pg_class where relname = 'sh_deadman_push'") == [(True,)]


# ================================================================ performance

def test_reads_over_90_days_take_less_than_2_seconds(db):
    """90 days of probe history for 4 pages (518,400 rows), of lab runs (54,000 core and 51,840
    rotation runs), 30 days of real-user rows and a few hundred alerts, generated in bulk."""
    db.setup()
    db.sql("""
        insert into sh_probe (round_at, kind, page, url, ok, status, ms, fail)
        select date_trunc('minute', now()) - n * interval '1 minute', 'full', p.name, p.url, x.ok,
               case when x.ok then 200 else 502 end,
               case when x.ok then 150 + 90 * p.sort + mod(n * 37 + p.sort * 101, 400) else 900 end,
               case when not x.ok then 'http' end
        from generate_series(0, 129599) n
        cross join sh_pages p
        cross join lateral (select not (mod(n * 7 + p.sort, 997) = 0 or n between 50000 and 50006) as ok) x
        where p.is_probe""")
    opps = Jsonb([{"id": "audit-%d" % i, "title": "תמונות גדולות מדי לגודל שבו הן מוצגות באתר", "ms": 900 - 100 * i}
                                     for i in range(8)])
    db.sql("""
        insert into sh_speed (at, url, page, strategy, source, ok, score, lcp_ms, cls, ttfb_ms, bytes,
                              crux_category, crux_lcp_ms, opps)
        select date_trunc('minute', now()) - n * interval '15 minutes', p.url, p.name, s.strategy, 'core', true,
               60, 1800 + mod(n * 53 + p.sort * 17, 3000), 0.03, 400, 3400000, 'FAST', 2100, %s
        from generate_series(0, 8639) n
        cross join sh_pages p
        cross join (values ('mobile', 1), ('desktop', 4)) as s(strategy, every)
        where p.is_core and mod(n, s.every) = 0""", [opps])
    db.sql("insert into sh_site_pages (url) select %s || '/product/item-' || g || '/' from generate_series(0, 399) g", [SITE])
    db.sql("""
        insert into sh_speed (at, url, strategy, source, ok, score, lcp_ms, cls, ttfb_ms, bytes, opps)
        select date_trunc('minute', now()) - (n / 2) * interval '5 minutes', %s || '/product/item-' || mod(n, 400) || '/',
               'mobile', 'rotation', true, 50, 1500 + mod(n * 7919, 6000), 0.05, 500, 4000000, %s
        from generate_series(0, 51839) n""", [SITE, opps])
    db.sql("""
        insert into sh_rum (created_at, site, path, lcp_ms)
        select now() - n * interval '2 minutes', 'live', '/product/item-' || mod(n, 400) || '/', 1000 + mod(n * 131, 4000)
        from generate_series(0, 21599) n""")
    db.sql("""
        insert into sh_alerts (key, kind, title, body, opened_at, closed_at)
        select 'down:סל', 'down', 'האתר לא עונה: סל', 'קוד 502', t, t + interval '7 minutes'
        from generate_series(1, 400) n cross join lateral (select now() - n * interval '5 hours' as t) x""")
    db.sql("""
        insert into sh_messages (at, alert_id, event, kind, title, msg, priority, status)
        select opened_at, id, 'open', 'התראה', title, body, 4, 200 from sh_alerts""")
    sim.snapshot(db.rpc, db.now().date())
    db.sql("analyze")
    assert db.sql("select count(*) from sh_probe") == [(518400,)]
    assert db.sql("select count(*), count(*) filter (where source = 'core') from sh_speed") == [(105840, 54000)]

    now = db.now()
    window = dict(p_from=now - dt.timedelta(days=90), p_to=now + mins(1))
    site = [("sh_availability", window), ("sh_availability_series", window), ("sh_speed", window),
            ("sh_speed_series", dict(window, p_strategy="mobile")), ("sh_alerts_open", {}),
            ("sh_alerts_range", window), ("sh_health", {}), ("sh_product_issues", {}), ("sh_cert", {})]
    today = now.astimezone(TZ).date()
    others = [("sh_now", {}), ("sh_drill_fails", window), ("sh_drill_bucket", dict(p_bucket=today.isoformat())),
              ("sh_drill_runs", dict(window, p_url=URL["בית"])), ("sh_messages", window), ("sh_alerts_check", {}),
              ("sh_morning", dict(p_day=today)), ("sh_cleanup", {})]
    answers = {}
    for fn, params in site + others:
        slowest = 0
        for _ in range(2):                                               # the first call also plans the query
            started = time.perf_counter()
            answers[fn] = db.rpc(fn, **params)
            slowest = max(slowest, time.perf_counter() - started)
        TIMINGS.append((fn + ("  (/api/site)" if (fn, params) in site else ""), slowest))
        assert slowest < 2, fn

    # and the answers are about all of it
    rows, minute = answers["sh_availability"], now.replace(second=0, microsecond=0)
    assert [r["checks"] for r in rows[:4]] == [129600] * 4
    assert rows[4:] == [{"section": "נפילות", "outage_minutes": 7, "outage_start_il": il(minute - mins(50006)),
                         "outage_end_il": il(minute - mins(49999))}]
    days = answers["sh_availability_series"]
    # one row per local day, from the oldest round's to today's: 90, 91 or 92, as daylight saving time moves the oldest
    first = (minute - mins(129599)).astimezone(TZ).date()
    assert len(days) == (minute.astimezone(TZ).date() - first).days + 1
    assert sum(r["checks"] for r in days) == 518400
    assert [r["checks"] for r in section(answers["sh_speed"], "ליבה")] == [8640] * 5 + [2160] * 5
    assert section(answers["sh_speed"], "כיסוי") == [{"section": "כיסוי", "checks": 400, "slow_runs": 400}]
    assert len(answers["sh_drill_runs"]) == 8640 and len(answers["sh_drill_fails"]) == 500
    assert [len(r["opps"]) for r in answers["sh_drill_runs"]] == [8] * 100 + [0] * 8540
    assert answers["sh_cleanup"] == {"probe": 0, "probe_light": 0, "speed": 0, "rum": 0, "product_issues": 0, "jobs": 0,
                                     "login_log": 0}                     # 90 days: nothing is old enough to go
