#!/usr/bin/env python3
"""
One-time patch: makes build.py work on GitHub Pages.

  - fixes SITE_URL trailing slash (was causing // in RSS + Apple News links)
  - replaces Netlify Forms with a form endpoint you choose (NEWSLETTER_ENDPOINT)
  - hides the newsletter popup/band until an endpoint is set, so it never
    shows a fake "You're in" message

Usage:  python3 patch_build.py      (run in the same folder as build.py)
A backup is saved as build.py.bak first.
"""
import shutil, sys

PATH = "build.py"
src = open(PATH, encoding="utf-8").read()

# (old, new, expected_count)
EDITS = [
    (
        'SITE_URL = "https://techtreck.tech/"  # NEW: replace with your real domain, no trailing slash',
        'SITE_URL = "https://techtreck.tech"  # no trailing slash\n\n'
        '# Newsletter signup endpoint, e.g. "https://formspree.io/f/xxxxxxxx".\n'
        '# Leave "" and the signup popup + bottom band are hidden.\n'
        'NEWSLETTER_ENDPOINT = ""',
        1,
    ),
    (' method="POST" data-netlify="true" netlify-honeypot="nl-bot-field-popup">', ' method="POST">', 1),
    (' method="POST" data-netlify="true" netlify-honeypot="nl-bot-field-inline">', ' method="POST">', 1),
    ('      <input type="hidden" name="form-name" value="newsletter" />\n', '', 2),
    ('name="nl-bot-field-popup"', 'name="_gotcha"', 1),
    ('name="nl-bot-field-inline"', 'name="_gotcha"', 1),
    ("var data = new URLSearchParams(new FormData(form)).toString();", "", 1),
    (
        "fetch('/', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:data})",
        "fetch('__NL_ENDPOINT__', {method:'POST', headers:{'Accept':'application/json'}, body:new FormData(form)})",
        1,
    ),
    (".then(function(){", ".then(function(r){ if(!r.ok){ throw new Error('failed'); }", 1),
    (
        'POPUP_HTML = NEWSLETTER_STYLE + """',
        'NEWSLETTER_SCRIPT = NEWSLETTER_SCRIPT.replace("__NL_ENDPOINT__", NEWSLETTER_ENDPOINT)\n\n'
        'POPUP_HTML = NEWSLETTER_STYLE + """',
        1,
    ),
    (
        'ABOUT_MARKDOWN = """',
        'if not NEWSLETTER_ENDPOINT:\n    POPUP_HTML = ""\n    INLINE_SIGNUP_HTML = ""\n\n'
        'ABOUT_MARKDOWN = """',
        1,
    ),
    (
        "your email address is stored via Netlify Forms and used only",
        "your email address is stored with our newsletter form provider and used only",
        1,
    ),
]

problems = []
for old, new, expected in EDITS:
    found = src.count(old)
    if found != expected:
        problems.append((old[:70], expected, found))

if problems:
    print("Nothing changed. These edits didn't match your build.py as expected:")
    for snippet, exp, got in problems:
        print(f"  - expected {exp}x, found {got}x: {snippet}...")
    sys.exit(1)

shutil.copyfile(PATH, PATH + ".bak")
for old, new, _ in EDITS:
    src = src.replace(old, new)
open(PATH, "w", encoding="utf-8").write(src)
print("Done. build.py patched (backup saved as build.py.bak).")
