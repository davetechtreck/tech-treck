#!/usr/bin/env python3
"""
One-time patch for build.py. Safe to run more than once.

Group 1: GitHub Pages fixes
  - fixes the SITE_URL trailing slash (it caused // in RSS + Apple News links)
  - removes Netlify Forms; the newsletter popup + bottom band stay hidden
    until you set NEWSLETTER_ENDPOINT in build.py (so nobody sees a fake
    "You're in" message)
  - hides the "Subscribe below" line on the About page while it's hidden
Group 2: adds a short "produced with the help of AI" paragraph to About

Group 3: points the signup popup + bottom band at your Kit signup page
         (the Subscribe button opens it in a new tab)

Each group is applied all-or-nothing, and skipped if it's already applied.
A backup is saved as build.py.bak.

Usage:  python3 patch_build.py      (run in the same folder as build.py)
"""
import re, shutil, sys

PATH = "build.py"
KIT_URL = "https://tech-trek-signup.kit.com/2780114860"
src = open(PATH, encoding="utf-8").read()

SUBSCRIBE_PARA = (
    "Want it without checking back constantly? Subscribe below for a once-daily "
    "digest \u2014 everything published that day, one email, no spam."
)

AI_PARA = (
    "Tech Trek is produced with the help of AI tools. Stories are researched and "
    "drafted with AI, and every post lists the sources its facts came from. If "
    "you spot a mistake, tell us through any of the social links below and we'll "
    "correct it."
)

# (old, new, expected_count)
GROUP_NEWSLETTER = [
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

GROUP_AI = [
    (
        "Some posts link to products through the Amazon Associates program.",
        AI_PARA + "\n\nSome posts link to products through the Amazon Associates program.",
        1,
    ),
]

GROUP_ABOUT_SUBSCRIBE = [
    (
        'PRIVACY_MARKDOWN = f"""',
        'if not NEWSLETTER_ENDPOINT:\n'
        '    ABOUT_MARKDOWN = ABOUT_MARKDOWN.replace(\n'
        f'        "{SUBSCRIBE_PARA}\\n\\n", ""\n'
        '    )\n\n'
        'PRIVACY_MARKDOWN = f"""',
        1,
    ),
]

GROUPS = [
    ("GitHub Pages / newsletter fixes", GROUP_NEWSLETTER, "NEWSLETTER_ENDPOINT"),
    ("Hide \"Subscribe below\" on About while signup is hidden", GROUP_ABOUT_SUBSCRIBE,
     "ABOUT_MARKDOWN = ABOUT_MARKDOWN.replace"),
    ("AI note on the About page", GROUP_AI, "produced with the help of AI tools"),
]

new_src = src
applied, skipped, failed = [], [], []
for name, edits, done_marker in GROUPS:
    if done_marker in new_src:
        skipped.append(name)
        continue
    bad = [(o[:60], exp, new_src.count(o)) for o, _, exp in edits if new_src.count(o) != exp]
    if bad:
        failed.append((name, bad))
        continue
    for old, new, _ in edits:
        new_src = new_src.replace(old, new)
    applied.append(name)


# ---- Group 3: Kit signup page (custom, uses a regex) -------------------------
BUTTON_STYLE = (
    "display:inline-block;padding:14px 24px;border-radius:8px;background:var(--accent);"
    "color:var(--accent-ink);font-weight:600;font-size:1rem;font-family:var(--font-sans);"
    "text-decoration:none;white-space:nowrap"
)
FORM_RE = re.compile(r'<form class="newsletter-form".*?</form>', re.DOTALL)
KIT_NAME = "Point signup at the Kit page"


def kit_button(extra=""):
    return (
        f'<div class="newsletter-form"><a href="__NL_URL__" target="_blank" '
        f'rel="noopener"{extra} style="{BUTTON_STYLE}">Subscribe</a></div>'
    )


if "__NL_URL__" in new_src:
    skipped.append(KIT_NAME)
else:
    set_old = 'NEWSLETTER_ENDPOINT = ""'
    hide_old = 'if not NEWSLETTER_ENDPOINT:\n    POPUP_HTML = ""'
    n_forms = len(FORM_RE.findall(new_src))
    problems = []
    if new_src.count(set_old) != 1:
        problems.append((set_old, 1, new_src.count(set_old)))
    if new_src.count(hide_old) != 1:
        problems.append((hide_old[:60], 1, new_src.count(hide_old)))
    if n_forms != 2:
        problems.append(("<form class=\"newsletter-form\" ... </form>", 2, n_forms))
    if problems:
        failed.append((KIT_NAME, problems))
    else:
        new_src = new_src.replace(set_old, f'NEWSLETTER_ENDPOINT = "{KIT_URL}"')
        buttons = iter([kit_button(" data-nl-close"), kit_button()])  # popup, then bottom band
        new_src = FORM_RE.sub(lambda m: next(buttons), new_src)
        new_src = new_src.replace(
            hide_old,
            'POPUP_HTML = POPUP_HTML.replace("__NL_URL__", NEWSLETTER_ENDPOINT)\n'
            'INLINE_SIGNUP_HTML = INLINE_SIGNUP_HTML.replace("__NL_URL__", NEWSLETTER_ENDPOINT)\n\n'
            + hide_old,
        )
        applied.append(KIT_NAME)

for name in skipped:
    print(f"Already applied, skipped: {name}")
for name in applied:
    print(f"Applied: {name}")
for name, bad in failed:
    print(f"COULD NOT APPLY: {name}. These lines didn't match your build.py:")
    for snippet, exp, got in bad:
        print(f"  - expected {exp}x, found {got}x: {snippet}...")

if applied:
    shutil.copyfile(PATH, PATH + ".bak")
    open(PATH, "w", encoding="utf-8").write(new_src)
    print("build.py updated (backup saved as build.py.bak).")
else:
    print("No changes made.")

sys.exit(1 if failed else 0)
