#!/usr/bin/env python3
"""Packs the kit folder into one self-extracting Markdown file, SITE_HEALTH_KIT.md.

    python3 build_kit.py            # writes kit/MANIFEST.json and SITE_HEALTH_KIT.md
    python3 build_kit.py --check    # also unpacks the result into a temp folder and compares every file

One file is the easiest thing to hand to a coding agent. The folder `kit/` is the source of
truth; never edit SITE_HEALTH_KIT.md or kit/MANIFEST.json by hand.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "kit")
OUT = os.path.join(HERE, "SITE_HEALTH_KIT.md")
DEST = "site-health-kit"          # folder the files are unpacked into (also a valid skill folder name)
FENCE = "~~~~~~~~"
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", "shots"}
SKIP_EXT = {".pyc", ".png", ".log"}
FIRST = ["START-HERE.md", "SKILL.md", "AGENTS-snippet.md", "MANIFEST.json"]       # then spec/, then the rest
MUST_END_WITH_EOF = re.compile(r"^(START-HERE\.md|SKILL\.md|spec/.*\.md)$")       # files the agent must read to the last line
MAX_READ_BYTES = 36_000           # a spec file above this cannot be read in a few 150-line chunks

UNPACK = r'''# --- unpack ---
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
assert n == __COUNT__, 'expected __COUNT__ files, found %d (the file is cut; get it again)' % n
print('KIT OK: unpacked', n, 'files into site-health-kit/')
# --- end unpack ---'''

ONE_LINER = ('''python3 -c "import re;exec(re.search(r'(?s)# --- unpack ---\\n(.*?)# --- end unpack ---','''
             '''open('SITE_HEALTH_KIT.md',encoding='utf-8').read()).group(1))"''')

HEAD = '''# ערכת "בריאות האתר" — קובץ אחד לקודקס

**לדורון, בקצרה**

- **מה זה:** כל מה שקודקס צריך כדי לבנות את מסך "בריאות האתר" לאתר אחר: ההוראות, המסך עצמו, ובדיקות.
- **מה עושים איתו:** שמים את הקובץ הזה בתיקיית הפרויקט של האתר החדש, ושולחים לקודקס את ההודעה שלמטה.
- **מה יוצא:** קודקס שואל אותך כמה שאלות קצרות (כתובת האתר, אילו עמודים לבדוק, מי מקבל התראות) ואז בונה, שלב אחרי שלב.

ההודעה לקודקס (להעתיק, ולהשלים את כתובת האתר):

> בתיקייה יש קובץ SITE_HEALTH_KIT.md. אל תקרא את כולו. תריץ את פקודת הפריסה שכתובה בראש הקובץ, תקרא את site-health-kit/START-HERE.md עד השורה האחרונה, ותעבוד לפיו. אני רוצה את מסך בריאות האתר לאתר: ________. תכתוב לי בעברית, קצר ופשוט, ושאלה אחת בכל פעם.

---

# For the coding agent

This file is a container: __COUNT__ files (about __SIZE__ KB) are embedded below the line
`FILES BELOW`. **Do not read or print the part below that line.** Unpack it instead.

**Step 1 — unpack.** From the directory that contains this file, run this one command:

```bash
__ONE_LINER__
```

It writes the folder `site-health-kit/`, verifies the checksum of every file, and prints
`KIT OK`. If it fails, stop and tell the owner the file arrived damaged. Never recreate a file
of the kit from memory.

**Step 2 — read `site-health-kit/START-HERE.md`** completely, to its last line
(`<!-- EOF START-HERE.md -->`), at most 150 lines per command. It tells you what else to read
and how to work.

The command above runs this script, which is the only part of this file you need to trust:

```python
__UNPACK__
```

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
    first = [f for f in FIRST if f in out]
    spec = sorted(f for f in out if f.startswith("spec/"))
    return first + spec + [f for f in out if f not in first and f not in spec]


def read(rel):
    body = open(os.path.join(SRC, rel), encoding="utf-8").read().replace("\r\n", "\n")
    if not body.endswith("\n"):
        body += "\n"
    if re.search(r"^%s" % FENCE, body, re.M):
        raise SystemExit("%s contains the fence %s at the start of a line" % (rel, FENCE))
    if "<!-- END FILE -->" in body or "<!-- FILE: " in body:
        raise SystemExit("%s contains a kit marker" % rel)
    return body


def lint(names):
    """The rules that make the kit readable by an agent whose tool output is capped."""
    bad = []
    for rel in names:
        if not MUST_END_WITH_EOF.match(rel):
            continue
        body = read(rel)
        if body.rstrip("\n").split("\n")[-1] != "<!-- EOF %s -->" % rel:
            bad.append("%s must end with the line <!-- EOF %s -->" % (rel, rel))
        if rel.startswith("spec/") and len(body.encode("utf-8")) > MAX_READ_BYTES:
            bad.append("%s is %d bytes; split it (limit %d)" % (rel, len(body.encode("utf-8")), MAX_READ_BYTES))
    if bad:
        raise SystemExit("kit lint failed:\n- " + "\n- ".join(bad))


def manifest(names):
    rows = []
    for rel in names:
        if rel == "MANIFEST.json":
            continue
        body = read(rel).encode("utf-8")
        rows.append({"path": rel, "bytes": len(body), "lines": body.count(b"\n"), "sha256": hashlib.sha256(body).hexdigest()})
    with open(os.path.join(SRC, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"kit": "site-health-kit", "files": rows}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def build():
    names = files()
    lint(names)
    manifest(names)
    names = files()                                   # now with MANIFEST.json
    blocks, toc = [], []
    for rel in names:
        body = read(rel)
        lang = {".md": "markdown", ".html": "html", ".py": "python", ".js": "javascript", ".sql": "sql",
                ".json": "json", ".php": "php", ".txt": "text", ".sh": "bash"}.get(os.path.splitext(rel)[1], "text")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        blocks.append("<!-- FILE: %s/%s sha256=%s -->\n%s%s\n%s%s\n<!-- END FILE -->\n" % (DEST, rel, digest, FENCE, lang, body, FENCE))
        toc.append("- `%s/%s` (%d lines)" % (DEST, rel, body.count("\n")))
    payload = "\n".join(blocks)
    unpack = UNPACK.replace("__COUNT__", str(len(names)))
    head = (HEAD.replace("__UNPACK__", unpack).replace("__ONE_LINER__", ONE_LINER).replace("__TOC__", "\n".join(toc))
            .replace("__SIZE__", str(len(payload.encode("utf-8")) // 1024)).replace("__COUNT__", str(len(names))))
    open(OUT, "w", encoding="utf-8", newline="\n").write(head + payload)
    print("wrote %s: %d files, %d KB" % (os.path.relpath(OUT, HERE), len(names), os.path.getsize(OUT) // 1024))
    return names


def check(names):
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "SITE_HEALTH_KIT.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(open(OUT, encoding="utf-8").read())
        r = subprocess.run(["bash", "-c", ONE_LINER], cwd=tmp, capture_output=True, text=True)
        if r.returncode or "KIT OK" not in r.stdout:
            raise SystemExit("unpack failed:\n" + r.stdout + r.stderr)
        bad = [n for n in names if open(os.path.join(tmp, DEST, n), encoding="utf-8").read() != read(n)]
        got = sorted(os.path.relpath(os.path.join(root, n), os.path.join(tmp, DEST)).replace(os.sep, "/")
                     for root, _, ns in os.walk(os.path.join(tmp, DEST)) for n in ns)
        if bad or got != sorted(names):
            raise SystemExit("round trip differs: %s / extra or missing: %s" % (bad, set(got) ^ set(names)))
        # a file cut in the middle (a partial download or paste) must be refused, not half-unpacked
        whole = open(OUT, encoding="utf-8").read()
        with open(os.path.join(tmp, "SITE_HEALTH_KIT.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(whole[: len(whole) * 2 // 3])
        r = subprocess.run(["bash", "-c", ONE_LINER], cwd=tmp, capture_output=True, text=True)
        if r.returncode == 0:
            raise SystemExit("a truncated kit file was accepted by the unpacker")
    print("round trip ok: %d files identical after unpacking; a truncated file is refused" % len(names))


if __name__ == "__main__":
    n = build()
    if "--check" in sys.argv:
        check(n)
