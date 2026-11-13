"""A small data simulator: fills a database with believable measurements, through the write
functions the collectors use (sh_probe_add, sh_speed_add, sh_sitemap_set, sh_rotation_next, ...).

`rpc` is any callable rpc(fn, **params) that runs one sh_* function and returns its JSON
(in the SQL tests: Db.rpc). Times are sent as ISO 8601 strings, so the same calls work over HTTPS.
Everything is deterministic: the same arguments always store the same rows.
"""
import datetime as dt
import zlib

MINUTE = dt.timedelta(minutes=1)
RESPONSE_MS = [240, 620, 300, 540]             # typical server response per probe page
LCP_MS = [2300, 3300, 2800, 2100, 2500]        # typical phone LCP per core page
OPPS = [{"id": "uses-responsive-images", "title": "Properly size images", "ms": 900},
        {"id": "render-blocking-resources", "title": "Eliminate render-blocking resources", "ms": 400}]


def simulate(rpc, start, days, *, fail_hour=None, dead=None, slow=None, light=True, site_pages=40):
    """Store `days` days of measurements, beginning at `start` (an aware datetime, on a full minute).

    Every minute a full probe round (and, with `light`, a light round at the half minute); every
    15 minutes a phone run of each core page, every hour a desktop run; every 5 minutes two pages
    of the whole-site rotation. The sitemap lists `site_pages` product pages and, as a real one
    does, the configured pages too; the core pages among them take no turn in the rotation.
    The scenario knobs:

      fail_hour = (page, hour_start, n)   n full-round checks of that page, spread over the hour
                                          that begins at hour_start, fail with HTTP 502
      dead      = (begin, minutes)        no page answers for that many minutes (an outage)
      slow      = (page, begin, runs)     that many phone runs in a row of that core page, from
                                          `begin` on, take more than 5 seconds

    Returns {"probe": [...], "speed": [...]}: the rows as they were sent, with "round_at" / "at"
    as datetimes, so a caller can work out by itself what the read functions must answer.
    """
    config = rpc("sh_config")
    probe = [p for p in config["pages"] if p["probe"]]
    core = [p for p in config["pages"] if p["core"]]
    rpc("sh_sitemap_set", p_urls=[p["url"] for p in config["pages"]]
        + ["%s/product/item-%d/" % (config["site"], i + 1) for i in range(site_pages)])
    failing = set()
    if fail_hour:
        page, hour_start, n = fail_hour
        failing = {(page, hour_start + k * (60 // n) * MINUTE) for k in range(n)}
    stored = {"probe": [], "speed": []}

    for minute in range(days * 1440):
        at = start + minute * MINUTE
        rounds = [("full", at), ("light", at + dt.timedelta(seconds=30))]
        for kind, round_at in rounds if light else rounds[:1]:
            down = dead is not None and dead[0] <= round_at < dead[0] + dead[1] * MINUTE
            rows = [_check(p, i, minute, kind, down, (p["name"], round_at) in failing) for i, p in enumerate(probe)]
            rpc("sh_probe_add", p_round_at=round_at.isoformat(), p_kind=kind, p_rows=rows)
            stored["probe"] += [dict(r, round_at=round_at, kind=kind) for r in rows]

        runs = []
        if minute % 15 == 0:
            for i, p in enumerate(core):
                nth = (at - slow[1]) // (15 * MINUTE) if slow and p["name"] == slow[0] else -1
                lcp = 5200 + 100 * nth if 0 <= nth < slow[2] else LCP_MS[i % 5] + (minute * 53 + i * 17) % 400
                failed = minute % 750 == 0 and i == 1          # a lab run fails now and then
                runs.append(_run(p["url"], p["name"], "mobile", "core", None if failed else lcp, minute + i))
                if minute % 60 == 0:
                    runs.append(_run(p["url"], p["name"], "desktop", "core", int(lcp * 0.45), minute + i))
        if minute % 5 == 0:
            for url in rpc("sh_rotation_next", p_n=2):
                runs.append(_run(url, None, "mobile", "rotation", 1500 + zlib.crc32(url.encode()) % 6000, minute))
        if runs:
            rpc("sh_speed_add", p_rows=[dict(r, at=at.isoformat()) for r in runs])
            stored["speed"] += [dict(r, at=at) for r in runs]
    return stored


def snapshot(rpc, day, cert_days=23):
    """Store the once-a-day measurements for `day` (a date): the certificate, the catalogue's
    broken products, and a handful of real-user page views (40 live, 2 from a staging copy, 1 test)."""
    config = rpc("sh_config")
    noon = dt.datetime.combine(day, dt.time(12), dt.timezone.utc)
    rpc("sh_cert_set", p_row={
        "host": config["host"], "issuer": "Let's Encrypt R11", "ok": True, "err": None, "days_left": cert_days,
        "not_before": (noon - dt.timedelta(days=90 - cert_days)).isoformat(),
        "not_after": (noon + dt.timedelta(days=cert_days)).isoformat()})
    product = config["site"] + "/product/%s/"
    rpc("sh_issues_set", p_snap_date=day.isoformat(), p_rows=[
        {"product_id": "101", "issue": "בלי מחיר", "name": "שולחן אוכל נפתח 160", "url": product % "table-160"},
        {"product_id": "102", "issue": "בלי תמונה", "name": "כורסת טלוויזיה אפורה", "url": product % "armchair-grey"},
        {"product_id": "103", "issue": "לא במלאי", "name": "ספה תלת מושבית", "url": product % "sofa-3"},
        {"product_id": "104", "issue": "אי אפשר להוסיף לסל", "name": "שידת לילה אלון", "url": product % "nightstand-oak"}])
    rpc("sh_rum_add", p_rows=(
        [{"site": "live", "path": "/product/item-%d/" % (k % 7), "lcp_ms": 1200 + (k * 137) % 3000, "is_test": False}
         for k in range(40)]
        + [{"site": "staging." + config["host"], "path": "/", "lcp_ms": 2000 + k, "is_test": False} for k in range(2)]
        + [{"site": "live", "path": "/", "lcp_ms": 1500, "is_test": True}]))


def _check(page, i, minute, kind, down, fails):
    """One row of a probe round, in the shape sh_probe_add takes."""
    row = {"page": page["name"], "url": page["url"], "ok": True, "status": 200, "fail": None, "err": None,
           "ms": RESPONSE_MS[i % 4] + (minute * 37 + i * 101) % 200}
    if down:
        row.update(ok=False, status=None, fail="timeout", err="timed out", ms=10000)
    elif fails:
        row.update(ok=False, status=502, fail="http", ms=800)
    if kind == "light":
        row["ms"] = None        # a light round records only whether the page answered
    return row


def _run(url, page, strategy, source, lcp, salt):
    """One lab run, in the shape sh_speed_add takes. lcp None = the run failed."""
    run = {"url": url, "page": page, "strategy": strategy, "source": source, "ok": lcp is not None,
           "err": None if lcp is not None else "Lighthouse returned error: NO_FCP"}
    if lcp is not None:
        run.update(lcp_ms=lcp, score=max(18, min(99, 118 - lcp // 45)), cls=round(0.02 + (salt % 5) * 0.02, 3),
                   ttfb_ms=300 + (salt * 29) % 300, bytes=3000000 + (salt % 8) * 250000,
                   crux_category="FAST" if lcp <= 3125 else "AVERAGE" if lcp <= 5000 else "SLOW",
                   crux_lcp_ms=int(lcp * 0.8), opps=OPPS, lh_version="13.0.1")
    return run
