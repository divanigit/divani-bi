#!/usr/bin/env python3
"""Packs the kit folder into one self-extracting Markdown file, SITE_HEALTH_KIT.md.

    python3 build_kit.py            # writes SITE_HEALTH_KIT.md next to this script
    python3 build_kit.py --check    # unpacks the result into a temp folder and compares every file

The single file exists because one file is the easiest thing to hand to a coding agent.
The folder `kit/` is the source of truth; never edit SITE_HEALTH_KIT.md by hand.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "kit")
OUT = os.path.join(HERE, "SITE_HEALTH_KIT.md")
DEST = "site_health_kit"          # folder the files are unpacked into, relative to where the agent runs the command
FENCE = "~~~~~~~~"
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", "shots"}
SKIP_EXT = {".pyc", ".png", ".log"}
ORDER = ["SPEC.md", "AGENTS.md", "site_health.html", "mock_server.py", "check_screen.js"]   # the rest follows alphabetically

UNPACK = r'''python3 - <<'PY'
import hashlib, os, re
s = open('SITE_HEALTH_KIT.md', encoding='utf-8').read()
n = 0
for m in re.finditer(r'<!-- FILE: (\S+) sha256=([0-9a-f]{64}) -->\n~~~~~~~~[^\n]*\n(.*?\n)~~~~~~~~\n<!-- END FILE -->', s, re.S):
    path, digest, body = m.groups()
    assert not os.path.isabs(path) and '..' not in path.split('/'), 'bad path: ' + path
    assert hashlib.sha256(body.encode('utf-8')).hexdigest() == digest, 'damaged copy of ' + path + ' (get the file again)'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    open(path, 'w', encoding='utf-8', newline='\n').write(body)
    n += 1
print('unpacked', n, 'files into site_health_kit/')
PY'''

HEAD = '''# ערכת "בריאות האתר" — קובץ אחד לקודקס

**לדורון, בקצרה**

- **מה זה:** כל מה שקודקס צריך כדי לבנות את מסך "בריאות האתר" לאתר אחר: ההוראות, המסך עצמו, ובדיקות.
- **מה עושים איתו:** שמים את הקובץ הזה בתיקיית הפרויקט של האתר החדש, ואומרים לקודקס את המשפט שלמטה.
- **מה יוצא:** קודקס שואל אותך כמה שאלות קצרות על האתר (כתובת, אילו עמודים לבדוק, מי מקבל התראות) ואז בונה.

המשפט לקודקס (להעתיק כמו שהוא):

> בתיקייה יש קובץ SITE_HEALTH_KIT.md. תריץ את פקודת הפריסה שכתובה בראשו, תקרא את site_health_kit/SPEC.md מההתחלה עד הסוף, ותבנה לפיו את מסך בריאות האתר לאתר שלי. תכתוב לי בעברית, קצר ופשוט, ושאלה אחת בכל פעם.

---

# For the coding agent

This single file is a container. It holds a specification and working files for building the
**Site Health screen ("בריאות האתר")** for a website.

**Step 1 — unpack.** Do not read past the line `FILES BELOW` (it is ~__SIZE__ KB of embedded
files). From the directory that contains this file, run:

```bash
__UNPACK__
```

It writes the folder `site_health_kit/` and verifies every file's checksum. If Python is not
available, extract each block between `<!-- FILE: path … -->` and `<!-- END FILE -->` by other
means; do **not** retype file contents from memory.

**Step 2 — read `site_health_kit/SPEC.md` from start to end.** It is the specification; everything
else in the folder is referenced from it. Read it in full before writing any code (it is about
__SPEC_LINES__ lines; read it in chunks if your tools truncate long files).

**Step 3 — follow SPEC.md §1.** In short: see the screen run on fake data
(`python3 site_health_kit/mock_server.py`), ask the owner the intake questions of §2, then build in
the phases of §9 and run the checks of each phase.

Contents:

__TOC__

---

FILES BELOW

'''


def files():
    out = []
    for root, dirs, names in os.walk(SRC):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            if os.path.splitext(n)[1] in SKIP_EXT:
                continue
            out.append(os.path.relpath(os.path.join(root, n), SRC).replace(os.sep, "/"))
    first = [f for f in ORDER if f in out]
    return first + [f for f in out if f not in first]


def read(rel):
    body = open(os.path.join(SRC, rel), encoding="utf-8").read().replace("\r\n", "\n")
    if not body.endswith("\n"):
        body += "\n"
    if re.search(r"^%s" % FENCE, body, re.M):
        raise SystemExit("%s contains the fence %s at the start of a line" % (rel, FENCE))
    if "<!-- END FILE -->" in body or "<!-- FILE: " in body:
        raise SystemExit("%s contains a kit marker" % rel)
    return body


def build():
    names = files()
    blocks, toc = [], []
    for rel in names:
        body = read(rel)
        lang = {".md": "markdown", ".html": "html", ".py": "python", ".js": "javascript", ".sql": "sql",
                ".json": "json", ".php": "php", ".txt": "text", ".sh": "bash"}.get(os.path.splitext(rel)[1], "text")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        blocks.append("<!-- FILE: %s/%s sha256=%s -->\n%s%s\n%s%s\n<!-- END FILE -->\n" % (DEST, rel, digest, FENCE, lang, body, FENCE))
        toc.append("- `%s/%s` (%d lines)" % (DEST, rel, body.count("\n")))
    payload = "\n".join(blocks)
    spec_lines = read("SPEC.md").count("\n")
    head = (HEAD.replace("__UNPACK__", UNPACK).replace("__TOC__", "\n".join(toc))
            .replace("__SIZE__", str(len(payload.encode("utf-8")) // 1024)).replace("__SPEC_LINES__", str(spec_lines)))
    open(OUT, "w", encoding="utf-8", newline="\n").write(head + payload)
    print("wrote %s: %d files, %d KB" % (os.path.relpath(OUT, HERE), len(names), os.path.getsize(OUT) // 1024))
    return names


def check(names):
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "SITE_HEALTH_KIT.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(open(OUT, encoding="utf-8").read())
        r = subprocess.run(["bash", "-c", UNPACK], cwd=tmp, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("unpack failed:\n" + r.stdout + r.stderr)
        bad = [n for n in names if open(os.path.join(tmp, DEST, n), encoding="utf-8").read() != read(n)]
        got = sorted(os.path.relpath(os.path.join(root, n), os.path.join(tmp, DEST)).replace(os.sep, "/")
                     for root, _, ns in os.walk(os.path.join(tmp, DEST)) for n in ns)
        if bad or got != sorted(names):
            raise SystemExit("round trip differs: %s / extra or missing: %s" % (bad, set(got) ^ set(names)))
    print("round trip ok: %d files identical after unpacking" % len(names))


if __name__ == "__main__":
    n = build()
    if "--check" in sys.argv:
        check(n)
