#!/usr/bin/env python3
"""Proves that a deployed screen file is still the kit's screen and not a rewrite.

    python3 tools/check_template.py path/to/deployed/site_health.html

Passes when the file keeps the kit's structure and almost all of its lines. The edits that
spec §6.9 allows (SH_CONFIG values, explanation sentences, OPP entries, color variables)
change a few dozen lines at most. Prints SCREEN OK, or what is wrong. Exit code 0 / 1.
"""
import os
import re
import sys

KIT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site_health.html")
MIN_KEPT = 0.93          # share of the kit's lines that must appear unchanged in the deployed file


def lines(text):
    return [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]


def main(path):
    kit = open(KIT, encoding="utf-8").read()
    try:
        raw = open(path, "rb").read()
        got = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["the file is not valid UTF-8 (Hebrew text was damaged)"]
    bad = []
    if got.count("<!--SH_INJECT-->") != 1:
        bad.append("the marker <!--SH_INJECT--> must appear exactly once (the server injects SH_CONFIG / SH_ROLE there)")
    if not re.search(r'<html[^>]*\blang="he"[^>]*\bdir="rtl"|<html[^>]*\bdir="rtl"[^>]*\blang="he"', got):
        bad.append('the <html> tag must keep lang="he" dir="rtl"')
    if re.search(r'<(script|link|img|iframe)\b[^>]*\b(src|href)\s*=\s*["\']?(https?:)?//', got, re.I):
        bad.append("the screen must not load anything from another host (no external scripts, styles, fonts or images)")
    if "classList.toggle('explain')" in got or 'classList.toggle("explain")' in got:
        bad.append("the explanations toggle must use the class explain-on (class explain on <body> hides the whole page)")
    if re.search(r"\\u05[0-9a-fA-F]{2}|&#x?5[0-9a-fA-F]{2,3};", got):
        bad.append("Hebrew text was escaped (\\u05.. or &#...;): keep it as plain UTF-8")
    have = set(lines(got))
    want = lines(kit)
    kept = sum(1 for l in want if l in have) / len(want)
    if kept < MIN_KEPT:
        missing = [l for l in want if l not in have][:5]
        bad.append("only %.0f%% of the kit's lines are unchanged (need %.0f%%): this looks like a rewrite, not a copy. "
                   "First missing lines: %s" % (100 * kept, 100 * MIN_KEPT, " | ".join(m[:70] for m in missing)))
    for needle, why in (("window.SH_CONFIG", "the SH_CONFIG block"), ("function render(d)", "the render function"),
                        ("function drillRuns(", "the drill-down sheets"), ("@media print", "the print stylesheet"),
                        ("prefers-color-scheme:dark", "dark mode")):
        if needle not in got:
            bad.append("missing " + why)
    return bad


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    problems = main(sys.argv[1])
    if problems:
        print("SCREEN CHECK FAILED\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("SCREEN OK")
