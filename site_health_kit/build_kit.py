#!/usr/bin/env python3
"""Packs the kit folder into one self-extracting Markdown file, SITE_HEALTH_KIT.md.

    python3 build_kit.py            # writes kit/MANIFEST.json and SITE_HEALTH_KIT.md
    python3 build_kit.py --check    # also proves the result: unpacks it into a temp folder, compares every
                                    # file, and feeds the unpacker damaged, cut, renamed and older copies

One file is the easiest thing to hand to a coding agent. The folder `kit/` is the source of
truth; never edit SITE_HEALTH_KIT.md or kit/MANIFEST.json by hand.

KIT_VERSION names the kit. Raise it whenever a change of kit/ goes out to somebody: the unpacker
refuses to write over an unpacked kit of another version, and kit/START-HERE.md must name the same
version (the build stops when it does not).
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
NAME = "SITE_HEALTH_KIT.md"       # the name the unpack command looks for
DEST = "site-health-kit"          # folder the files are unpacked into (also a valid skill folder name)
KIT_VERSION = "1.0"
FENCE = "~~~~~~~~"
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", "shots"}
SKIP_EXT = {".pyc", ".png", ".log", ".zip"}
FIRST = ["START-HERE.md", "OWNER-STEPS.md", "SKILL.md", "AGENTS-snippet.md", "MANIFEST.json"]   # then spec/, then the rest
# the files of the reading table: the agent must read them to the last line, a few 150-line chunks each
MUST_END_WITH_EOF = re.compile(r"^(START-HERE\.md|OWNER-STEPS\.md|SKILL\.md|spec/.*\.md|reference/README\.md)$")
MAX_READ_BYTES = 36_000           # a file above this cannot be read in a few 150-line chunks

# The unpacker. It verifies everything first and writes only afterwards, so a damaged or cut copy
# leaves nothing on disk. Every refusal is one line that starts with KIT NOT UNPACKED.
UNPACK = r'''# --- unpack ---
import hashlib, json, os, re, sys
NAME, DEST, VERSION, COUNT = 'SITE_HEALTH_KIT.md', 'site-health-kit', '__VERSION__', __COUNT__
def stop(why):
    sys.exit('KIT NOT UNPACKED: ' + why)
if not os.path.isfile(NAME):
    stop('no file named ' + NAME + ' in this folder. Run the command in the folder that holds it; a copy with another name must be renamed to ' + NAME)
text = open(NAME, encoding='utf-8', errors='replace').read()
found = []
for m in re.finditer(r'<!-- FILE: (\S+) sha256=([0-9a-f]{64}) -->\n~~~~~~~~[^\n]*\n(.*?\n)~~~~~~~~\n<!-- END FILE -->', text, re.S):
    path, digest, body = m.groups()
    if os.path.isabs(path) or '..' in path.split('/') or '\\' in path or not path.startswith(DEST + '/'):
        stop('a file inside ' + NAME + ' has a path that is not allowed: ' + path)
    if hashlib.sha256(body.encode('utf-8')).hexdigest() != digest:
        stop(NAME + ' is damaged (the copy of ' + path + ' inside it does not match its checksum). Get the file again.')
    found.append((path, body))
if len(found) != COUNT:
    stop(NAME + ' is cut short: it should hold %d files and holds %d. Get the file again.' % (COUNT, len(found)))
if os.path.lexists(DEST):
    try:
        have = json.load(open(os.path.join(DEST, 'MANIFEST.json'), encoding='utf-8')).get('version')
    except (OSError, ValueError, AttributeError):
        have = None
    if have != VERSION:
        stop('the folder ' + DEST + '/ already holds another kit (version ' + str(have or 'unknown') + '), and this file is version '
             + VERSION + '. Nothing was written. To change kits, rename or remove that folder first and run the command again; '
             'the backend you built from it (site-health/) is not touched by this.')
for path, body in found:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body)
print('KIT OK: unpacked %d files into %s/ (kit version %s, build __BUILD__)' % (len(found), DEST, VERSION))
# --- end unpack ---'''

# One line, as the head prints it. It finds the script above inside the file and runs it; a missing
# or cut file is told in one line instead of a traceback. No "!" and no "$" in it: it is pasted
# into interactive shells inside double quotes.
ONE_LINER = ('''python3 -c "import os,re,sys;n='SITE_HEALTH_KIT.md';os.path.isfile(n) or sys.exit('KIT NOT UNPACKED: no file named '+n+'''
             '''' in this folder. Run the command in the folder that holds it; a copy with another name must be renamed to '+n);'''
             '''m=re.search(r'(?s)# --- unpack ---\\n(.*?)# --- end unpack ---',open(n,encoding='utf-8',errors='replace').read());'''
             '''exec(m.group(1)) if m else sys.exit('KIT NOT UNPACKED: '+n+' is cut short. Get the file again.')"''')

HEAD = '''# ערכת "בריאות האתר": קובץ אחד לקודקס

**לבעל האתר, בקצרה**

- **מה זה:** כל מה שקודקס צריך כדי לבנות לאתר שלך את המסך "בריאות האתר": ההוראות, המסך עצמו והבדיקות. המסך מראה אם האתר עובד, כמה הוא מהיר ומה שבור בו, ושולח הודעה לטלפון כשמשהו מפסיק לעבוד.
- **מה עושים איתו:** שמים את הקובץ הזה בתיקייה שקודקס עובד בה. אם אין תיקייה כזאת, פותחים תיקייה חדשה וריקה ושמים אותו בה. אחר כך שולחים לקודקס את ההודעה שלמטה.
- **מה יוצא:** קודקס שואל כמה שאלות קצרות, בונה שלב אחרי שלב, ובכל שלב כותב מה עושים עכשיו.

**מה נדרש ממך בדרך.** קודקס מסביר כל צעד כשמגיעים אליו, ואף פעם לא מבקש לראות סיסמה:

1. לפתוח שני חשבונות: אחד למקום שבו נשמרות המדידות, ואחד לשרת קטן שעובד כל הזמן ובודק את האתר.
2. ליצור מפתח של גוגל למדידת המהירות. המפתח בחינם.
3. להתקין אפליקציה בטלפון. דרכה מגיעות ההודעות.
4. להוסיף לאתר תוסף קטן, שמודד כמה מהר העמודים נטענים אצל הגולשים.

חלק מזה עולה בדרך כלל תשלום חודשי, בעיקר השרת הקטן. קודקס כותב מה בתשלום לפני שבוחרים, ואת המחירים בודקים באתרים של הספקים.

ההודעה לקודקס (להעתיק ולהשלים את כתובת האתר):

> בתיקייה יש קובץ SITE_HEALTH_KIT.md. אל תקרא את כולו. תריץ את הפקודה שכתובה בראש הקובץ (Step 1). היא פותחת את הקובץ לתיקייה. אחר כך תקרא את site-health-kit/START-HERE.md עד השורה האחרונה ותעבוד לפיו. אני רוצה את מסך בריאות האתר לאתר: ________. תכתוב לי בעברית, קצר ופשוט, ושאלה אחת בכל פעם.

---

# For the coding agent

This file is a container: kit version __VERSION__ (build __BUILD__), __COUNT__ files (about __SIZE__ KB), embedded
below the line `FILES BELOW`. **Do not read or print the part below that line.** Unpack it instead.

**Step 1: unpack.** From the directory that contains this file, run this one command:

```bash
__ONE_LINER__
```

It checks every embedded file first and writes only afterwards, so the folder `site-health-kit/`
appears complete or not at all. Success is one line that starts with `KIT OK`. A refusal is one
line that starts with `KIT NOT UNPACKED` and says why:

- *no file named SITE_HEALTH_KIT.md*: you are in another folder, or the file was renamed on the
  way (a browser adds ` (1)`). Go to the right folder or rename the file, and run the command again.
- *damaged* or *cut short*: stop and tell the owner that the file arrived damaged and has to be
  sent again. Never recreate a file of the kit from memory.
- *already holds another kit*: an older or newer kit is unpacked here. Do not remove it on your
  own: tell the owner which two versions there are and ask which one to work with.

**Step 2: read `site-health-kit/START-HERE.md`** completely, to its last line
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
        if len(body.encode("utf-8")) > MAX_READ_BYTES:
            bad.append("%s is %d bytes; split it (limit %d)" % (rel, len(body.encode("utf-8")), MAX_READ_BYTES))
    for rel in sorted(set(FIRST) - set(names) - {"MANIFEST.json"}):
        bad.append("%s is missing from kit/" % rel)
    if "START-HERE.md" in names and "Kit version %s." % KIT_VERSION not in read("START-HERE.md"):
        bad.append("START-HERE.md must name the kit's version as: Kit version %s." % KIT_VERSION)
    if bad:
        raise SystemExit("kit lint failed:\n- " + "\n- ".join(bad))


def manifest(names):
    """Writes kit/MANIFEST.json and returns the build id: a short digest of every file's checksum."""
    rows = []
    for rel in names:
        if rel == "MANIFEST.json":
            continue
        body = read(rel).encode("utf-8")
        rows.append({"path": rel, "bytes": len(body), "lines": body.count(b"\n"), "sha256": hashlib.sha256(body).hexdigest()})
    build_id = hashlib.sha256("\n".join("%s %s" % (r["sha256"], r["path"]) for r in rows).encode("utf-8")).hexdigest()[:12]
    with open(os.path.join(SRC, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"kit": "site-health-kit", "version": KIT_VERSION, "build": build_id, "files": rows}, f,
                  ensure_ascii=False, indent=1)
        f.write("\n")
    return build_id


def build():
    names = files()
    lint(names)
    build_id = manifest(names)
    names = files()                                   # now with MANIFEST.json
    blocks, toc = [], []
    for rel in names:
        body = read(rel)
        lang = {".md": "markdown", ".html": "html", ".py": "python", ".js": "javascript", ".sql": "sql", ".json": "json",
                ".php": "php", ".liquid": "liquid", ".txt": "text", ".sh": "bash"}.get(os.path.splitext(rel)[1], "text")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        blocks.append("<!-- FILE: %s/%s sha256=%s -->\n%s%s\n%s%s\n<!-- END FILE -->\n" % (DEST, rel, digest, FENCE, lang, body, FENCE))
        toc.append("- `%s/%s` (%d lines)" % (DEST, rel, body.count("\n")))
    payload = "\n".join(blocks)
    unpack = UNPACK.replace("__COUNT__", str(len(names)))
    head = (HEAD.replace("__UNPACK__", unpack).replace("__ONE_LINER__", ONE_LINER).replace("__TOC__", "\n".join(toc))
            .replace("__SIZE__", str(len(payload.encode("utf-8")) // 1024)).replace("__COUNT__", str(len(names)))
            .replace("__VERSION__", KIT_VERSION).replace("__BUILD__", build_id))
    open(OUT, "w", encoding="utf-8", newline="\n").write(head + payload)
    print("wrote %s: kit version %s (build %s), %d files, %d KB" % (
        os.path.relpath(OUT, HERE), KIT_VERSION, build_id, len(names), os.path.getsize(OUT) // 1024))
    return names


def _unpack_in(folder, container=None, name=NAME):
    """Runs the one-line command, exactly as the head prints it, in a folder that holds `container`."""
    os.makedirs(folder, exist_ok=True)
    if container is not None:
        with open(os.path.join(folder, name), "wb") as f:
            f.write(container)
    return subprocess.run(["bash", "-c", ONE_LINER], cwd=folder, capture_output=True, text=True)


def _tree(folder):
    return sorted(os.path.relpath(os.path.join(root, n), folder).replace(os.sep, "/")
                  for root, _, ns in os.walk(folder) for n in ns)


def check(names):
    whole = open(OUT, "rb").read()
    with tempfile.TemporaryDirectory() as tmp:
        # 1. the round trip: every file comes out as it went in, and nothing else does
        good = os.path.join(tmp, "good")
        r = _unpack_in(good, whole)
        if r.returncode or not r.stdout.startswith("KIT OK"):
            raise SystemExit("unpack failed:\n" + r.stdout + r.stderr)
        bad = [n for n in names if open(os.path.join(good, DEST, n), encoding="utf-8").read() != read(n)]
        got = _tree(os.path.join(good, DEST))
        if bad or got != sorted(names):
            raise SystemExit("round trip differs: %s / extra or missing: %s" % (bad, set(got) ^ set(names)))

        # 2. the same version again is fine (it restores the kit's files); another version is refused untouched
        r = _unpack_in(good)
        if r.returncode or not r.stdout.startswith("KIT OK"):
            raise SystemExit("unpacking the same version a second time failed:\n" + r.stdout + r.stderr)
        for other in ('{"kit": "site-health-kit", "version": "0.9", "files": []}', '{"kit": "site-health-kit", "files": []}', "{"):
            with open(os.path.join(good, DEST, "MANIFEST.json"), "w", encoding="utf-8") as f:
                f.write(other)
            with open(os.path.join(good, DEST, "START-HERE.md"), "w", encoding="utf-8") as f:
                f.write("an older kit\n")
            r = _unpack_in(good)
            kept = open(os.path.join(good, DEST, "START-HERE.md"), encoding="utf-8").read() == "an older kit\n"
            if r.returncode != 1 or "already holds another kit" not in r.stderr or "Traceback" in r.stderr or not kept:
                raise SystemExit("an unpacked kit of another version (%s) was not refused untouched:\n%s%s" % (other, r.stdout, r.stderr))

        # 3. a container that is not whole is refused in one line, and leaves nothing on disk
        text = whole.decode("utf-8")
        files_at = text.index("\nFILES BELOW\n")                             # the marker line itself, not its mention in the head
        first = text.index("\n", text.index("\n" + FENCE, files_at) + 1) + 1    # the first character of the first embedded file
        last = text.rindex("\n" + FENCE + "\n<!-- END FILE -->")              # the end of the last embedded file
        hebrew = whole.index("בריאות".encode("utf-8"), whole.index(b"\nFILES BELOW\n"))
        script = whole.index(b"# --- unpack ---\n")                           # the script in the head (the command spells \n out)
        broken = {
            "a cut at two thirds": (whole[: len(whole) * 2 // 3], "cut short"),
            "a cut inside the last file": (whole[: len(whole) - 400], "cut short"),
            "a cut inside the unpack script": (whole[: script + 300], "cut short"),
            "a cut before the unpack script": (whole[: script - 300], "cut short"),
            "one letter changed in the last file": ((text[: last - 5] + ("#" if text[last - 5] != "#" else "=") + text[last - 4:]).encode("utf-8"), "damaged"),
            "one letter changed in the first file": ((text[:first] + ("X" if text[first] != "X" else "Y") + text[first + 1:]).encode("utf-8"), "damaged"),
            "a byte that is not UTF-8": (whole[:hebrew] + b"\xf3" + whole[hebrew + 1:], "damaged"),
            "no content at all": (b"", "cut short"),
        }
        for label, (container, word) in broken.items():
            folder = os.path.join(tmp, "broken-" + str(len(os.listdir(tmp))))
            r = _unpack_in(folder, container)
            left = [n for n in os.listdir(folder) if n != NAME]
            if (r.returncode != 1 or not r.stderr.startswith("KIT NOT UNPACKED") or word not in r.stderr
                    or "Traceback" in r.stderr or r.stdout or left):
                raise SystemExit("a kit file with %s was not refused cleanly (exit %d, left on disk: %s):\n%s%s"
                                 % (label, r.returncode, left, r.stdout, r.stderr))

        # 4. a file that got another name on the way: the message names the expected file
        renamed = os.path.join(tmp, "renamed")
        r = _unpack_in(renamed, whole, name="SITE_HEALTH_KIT (1).md")
        if (r.returncode != 1 or not r.stderr.startswith("KIT NOT UNPACKED: no file named " + NAME)
                or "Traceback" in r.stderr or os.listdir(renamed) != ["SITE_HEALTH_KIT (1).md"]):
            raise SystemExit("a renamed kit file is not explained:\n" + r.stdout + r.stderr)
    print("round trip ok: %d files identical after unpacking; a second unpack of the same version works; another "
          "version, %d damaged or cut copies and a renamed file are refused in one line and leave nothing behind"
          % (len(names), len(broken)))


if __name__ == "__main__":
    n = build()
    if "--check" in sys.argv:
        check(n)
