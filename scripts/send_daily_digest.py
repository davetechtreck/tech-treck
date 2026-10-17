#!/usr/bin/env python3
"""
Tech Trek: daily newsletter digest, sent through Kit.

Once a day (when the workflow runs, right after the daily post is written):
  1. finds posts in posts/ dated today (exits quietly if there are none),
  2. skips if today's digest was already created in Kit,
  3. creates a Kit broadcast to ALL your subscribers, scheduled to send
     15 minutes from now so the site has time to finish deploying.

The time of day is controlled by the cron lines in the workflow, not here.

NEW in this version
  - Branded email layout (masthead, serif headlines, mono metadata) that
    follows the subscriber's light/dark setting automatically.
  - Optional "view in browser" web version of each digest, with a real
    light/dark toggle button (set WEB_VERSION=true, see notes below).
  - PREVIEW=true builds two local HTML files so you can look at the design
    without touching Kit.

Standard library only. Environment variables:
  KIT_API_KEY            Your Kit V4 API key (GitHub secret)   [required, except PREVIEW]
  SITE_URL               default "https://techtreck.tech"
  DRY_RUN                "true" = check the key and print the email, send nothing
  FORCE                  "true" = ignore the duplicate check
  DIGEST_DATE            override "today" for testing (YYYY-MM-DD)
  PREVIEW                "true" = only write digest-preview-email.html and
                         digest-preview-web.html, then exit (no API calls)
  WEB_VERSION            "true" = also write digest/<date>.html and add a
                         "View in browser" link to the email. Your site build
                         must publish the digest/ folder at SITE_URL/digest/
                         or that link will 404.
  KIT_EMAIL_TEMPLATE_ID  optional Kit email template id. Use this to pick a
                         template with the badge turned off (paid plans).
"""

import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.kit.com/v4"
TIMEZONE = "America/Toronto"
SEND_DELAY_MINUTES = 15
SITE_URL = (os.environ.get("SITE_URL", "").strip() or "https://techtreck.tech").rstrip("/")
KIT_API_KEY = os.environ.get("KIT_API_KEY", "").strip()
DRY_RUN = os.environ.get("DRY_RUN", "").lower() == "true"
FORCE = os.environ.get("FORCE", "").lower() == "true"
PREVIEW = os.environ.get("PREVIEW", "").lower() == "true"
WEB_VERSION = os.environ.get("WEB_VERSION", "").lower() == "true"
EMAIL_TEMPLATE_ID = os.environ.get("KIT_EMAIL_TEMPLATE_ID", "").strip()
POSTS_DIR = Path("posts")
WEB_OUT_DIR = Path("digest")

NOW_LOCAL = datetime.now(ZoneInfo(TIMEZONE))
TODAY = os.environ.get("DIGEST_DATE", "").strip() or NOW_LOCAL.strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Design settings. Edit these to match the site exactly.
# ---------------------------------------------------------------------------
TAGLINE = "field notes on tech"

# Fill in your real profile URLs. Empty ones are left out of the email.
SOCIAL_LINKS = [
    ("Instagram", "https://www.instagram.com/techtrec3k?stkn=dnh6djY3eHQ5a3dq&utm_source=qr"),
    ("x", "https://x.com/techtre3k"),
    ("Youtube", " https://www.youtube.com/@TechTrecck"),
    ("tiktok" , "https://www.tiktok.com/@tech.tre3k?is_from_webapp=1&sender_device=pc "),
]

# Email clients ignore most web fonts, so these are safe system stacks.
SERIF = "Georgia,'Times New Roman',serif"
MONO = "'SFMono-Regular',Menlo,Consolas,'Courier New',monospace"
SANS = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"

# Slightly off-white / off-black so Gmail's automatic dark-mode inversion
# does not turn pure white into a harsh result.
LIGHT = {
    "outer": "#eeeeea", "card": "#fcfcfa", "ink": "#1b1b1b", "body": "#3d3d3d",
    "muted": "#6b6b66", "rule": "#1b1b1b", "hair": "#dcdcd5", "link": "#2F49FF",
    "btn_bg": "#1b1b1b", "btn_ink": "#fcfcfa",
}
DARK = {
    "outer": "#0e0e10", "card": "#18181b", "ink": "#f1efe9", "body": "#c9c6be",
    "muted": "#8f8c84", "rule": "#f1efe9", "hair": "#2d2d32", "link": "#9aacff",
    "btn_bg": "#f1efe9", "btn_ink": "#18181b",
}


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def kit(path, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("X-Kit-Api-Key", KIT_API_KEY)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-")


def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip().strip('"').strip("'")
    return fm, m.group(2)


def find_todays_posts():
    posts = []
    if not POSTS_DIR.exists():
        fail(f"posts folder not found (cwd: {os.getcwd()})")
    for f in sorted(POSTS_DIR.glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm.get("date", "")[:10] != TODAY:
            continue
        title = fm.get("title") or f.stem
        slug = fm.get("slug") or slugify(title)
        excerpt = fm.get("snippet") or fm.get("excerpt") or ""
        if not excerpt:
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    excerpt = line[:180] + ("…" if len(line) > 180 else "")
                    break
        posts.append({"title": title, "url": f"{SITE_URL}/posts/{slug}.html", "excerpt": excerpt})
    return posts


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------
def _fmt_date(d):
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt:%A, %B} {dt.day}, {dt.year}"
    except ValueError:
        return d


def _important(decl):
    return ";".join(p.strip() + " !important" for p in decl.split(";") if p.strip())


def _dark_rules(prefix=""):
    """CSS that swaps every themed class to the dark palette."""
    d = DARK
    rules = {
        ".tt-outer": f"background-color:{d['outer']}",
        ".tt-card": f"background-color:{d['card']};border-color:{d['hair']}",
        ".tt-ink": f"color:{d['ink']}",
        ".tt-body": f"color:{d['body']}",
        ".tt-muted": f"color:{d['muted']}",
        ".tt-rule": f"border-color:{d['rule']}",
        ".tt-hair": f"border-color:{d['hair']}",
        ".tt-link": f"color:{d['link']}",
        ".tt-btn": f"background-color:{d['btn_bg']};color:{d['btn_ink']}",
    }
    return "".join(f"{prefix}{sel}{{{_important(decl)}}}" for sel, decl in rules.items())


# Mobile tweaks, shared by the email and the web page.
BASE_CSS = (
    "@media (max-width:620px){"
    ".tt-pad{padding-left:20px !important;padding-right:20px !important}"
    ".tt-h1{font-size:32px !important}"
    ".tt-title{font-size:20px !important}"
    "}"
)

# Email: follow the reader's device setting. The [data-ogsc] copy covers Outlook.com.
EMAIL_CSS = (
    ":root{color-scheme:light dark;supported-color-schemes:light dark}"
    + BASE_CSS
    + "@media (prefers-color-scheme:dark){" + _dark_rules() + "}"
    + _dark_rules("[data-ogsc] ")
)

# Web page: follow the toggle (html[data-theme]), which defaults to the device setting.
WEB_CSS = (
    "body{margin:0}"
    + BASE_CSS
    + _dark_rules('html[data-theme="dark"] ')
    + f"#tt-toggle{{position:fixed;top:14px;right:14px;z-index:10;cursor:pointer;"
      f"font:13px {MONO};padding:8px 12px;border-radius:2px;"
      f"border:1px solid {LIGHT['rule']};background:{LIGHT['card']};color:{LIGHT['ink']}}}"
    + f"html[data-theme=\"dark\"] #tt-toggle{{border-color:{DARK['rule']};"
      f"background:{DARK['card']};color:{DARK['ink']}}}"
    + "#tt-toggle:focus-visible{outline:2px solid #2F49FF;outline-offset:2px}"
)

WEB_SCRIPT = """
(function () {
  var root = document.documentElement, btn = document.getElementById('tt-toggle');
  function label() { btn.textContent = root.getAttribute('data-theme') === 'dark' ? 'Light mode' : 'Dark mode'; }
  btn.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('tt-theme', next); } catch (e) {}
    label();
  });
  label();
})();
"""

WEB_HEAD_SCRIPT = """
(function () {
  var t = null;
  try { t = localStorage.getItem('tt-theme'); } catch (e) {}
  if (t !== 'dark' && t !== 'light') {
    t = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', t);
})();
"""


def _markup(posts, web_url=None):
    L = LIGHT
    e = html.escape
    rows = []

    # Masthead
    rows.append(
        f'<tr><td class="tt-pad" style="padding:30px 36px 18px">'
        f'<div class="tt-muted" style="font-family:{MONO};font-size:12px;color:{L["muted"]}">{e(TAGLINE)}</div>'
        f'<div class="tt-ink tt-h1" style="font-family:{SERIF};font-size:38px;line-height:1.1;'
        f'font-weight:700;color:{L["ink"]};margin-top:6px">Tech Trek</div>'
        f'<div class="tt-muted" style="font-family:{MONO};font-size:12px;color:{L["muted"]};'
        f'margin-top:10px">{e(_fmt_date(TODAY))}</div>'
        f'</td></tr>'
    )
    rows.append(
        f'<tr><td class="tt-rule" style="padding:0;height:0;font-size:0;line-height:0;'
        f'border-top:3px solid {L["rule"]}">&nbsp;</td></tr>'
    )

    if web_url:
        rows.append(
            f'<tr><td class="tt-pad tt-hair" style="padding:12px 36px;border-bottom:1px solid {L["hair"]};'
            f'font-family:{MONO};font-size:12px;color:{L["muted"]}">'
            f'<span class="tt-muted" style="color:{L["muted"]}">Trouble reading this? </span>'
            f'<a class="tt-link" href="{e(web_url)}" style="color:{L["link"]}">View in browser</a>'
            f'</td></tr>'
        )

    # Stories
    for p in posts:
        rows.append(
            f'<tr><td class="tt-pad tt-hair" style="padding:26px 36px;border-bottom:1px solid {L["hair"]}">'
            f'<a class="tt-ink tt-title" href="{e(p["url"])}" style="font-family:{SERIF};font-size:23px;'
            f'line-height:1.25;font-weight:700;color:{L["ink"]};text-decoration:none">{e(p["title"])}</a>'
            f'<p class="tt-body" style="margin:10px 0 16px;font-family:{SERIF};font-size:16px;'
            f'line-height:1.6;color:{L["body"]}">{e(p["excerpt"])}</p>'
            f'<a class="tt-btn" href="{e(p["url"])}" style="display:inline-block;padding:10px 18px;'
            f'font-family:{SANS};font-size:14px;font-weight:600;text-decoration:none;border-radius:2px;'
            f'background-color:{L["btn_bg"]};color:{L["btn_ink"]}">Read the full post</a>'
            f'</td></tr>'
        )

    # Footer
    socials = "".join(
        f'<a class="tt-link" href="{e(url)}" style="font-family:{MONO};font-size:12px;'
        f'color:{L["link"]};margin-right:16px;text-decoration:none">{e(name)}</a>'
        for name, url in SOCIAL_LINKS.items() if url
    )
    domain = SITE_URL.replace("https://", "").replace("http://", "")
    rows.append(
        f'<tr><td class="tt-pad" style="padding:22px 36px 28px">'
        + (f'<div style="margin-bottom:14px">{socials}</div>' if socials else "")
        + f'<div class="tt-muted" style="font-family:{MONO};font-size:12px;line-height:1.6;'
        f'color:{L["muted"]}">You are getting this because you subscribed at {e(domain)}.</div>'
        f'</td></tr>'
    )

    return (
        f'<table role="presentation" class="tt-outer" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background-color:{L["outer"]}"><tr><td align="center" style="padding:24px 12px">'
        f'<table role="presentation" class="tt-card" width="600" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;max-width:600px;background-color:{L["card"]};border:1px solid {L["hair"]}">'
        + "".join(rows)
        + '</table></td></tr></table>'
    )


def build_html(posts, web_url=None):
    """Email body for Kit. A fragment: Kit wraps it in its own template."""
    return f"<style>{EMAIL_CSS}</style>" + _markup(posts, web_url)


def build_email_preview(posts, web_url=None):
    """The email fragment wrapped in a minimal page, for local preview only."""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>Email preview</title></head><body style=\"margin:0\">{build_html(posts, web_url)}</body></html>"
    )


def build_web_page(posts):
    """Standalone web version of the digest, with a light/dark toggle button."""
    title = f"Tech Trek daily digest: {TODAY}"
    return (
        '<!DOCTYPE html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>{html.escape(title)}</title>"
        f"<style>{WEB_CSS}</style><script>{WEB_HEAD_SCRIPT}</script></head>"
        f'<body class="tt-outer" style="background-color:{LIGHT["outer"]}">'
        '<button id="tt-toggle" type="button">Dark mode</button>'
        + _markup(posts)
        + f"<script>{WEB_SCRIPT}</script></body></html>"
    )


def already_created(subject):
    data = kit("/broadcasts?per_page=50")
    return any((b or {}).get("subject") == subject for b in data.get("broadcasts", []))


def main():
    posts = find_todays_posts()

    if PREVIEW:
        if not posts:
            fail(f"No posts dated {TODAY}. Set DIGEST_DATE to a date that has a post.")
        web_url = f"{SITE_URL}/digest/{TODAY}.html"
        Path("digest-preview-email.html").write_text(build_email_preview(posts, web_url), encoding="utf-8")
        Path("digest-preview-web.html").write_text(build_web_page(posts), encoding="utf-8")
        print("Wrote digest-preview-email.html and digest-preview-web.html. Open them in a browser.")
        return

    if not KIT_API_KEY:
        fail("KIT_API_KEY is not set.")

    if not posts:
        print(f"No posts dated {TODAY}. Nothing to send.")
        return

    subject = f"Tech Trek daily digest: {TODAY}"
    preview = posts[0]["title"][:140]
    send_at = (datetime.now(timezone.utc) + timedelta(minutes=SEND_DELAY_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    web_url = f"{SITE_URL}/digest/{TODAY}.html" if WEB_VERSION else None

    if DRY_RUN:
        acct = kit("/account")  # proves the API key works
        print(f"DRY RUN: Kit key OK ({json.dumps(acct)[:120]}).")
        print(f"Would send '{subject}' with {len(posts)} post(s) at {send_at}:")
        for p in posts:
            print(f"  - {p['title']}  {p['url']}")
        if web_url:
            print(f"Web version would be at {web_url}")
        return

    if not FORCE and already_created(subject):
        print("Today's digest was already created. Skipping.")
        return

    if WEB_VERSION:
        WEB_OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = WEB_OUT_DIR / f"{TODAY}.html"
        out.write_text(build_web_page(posts), encoding="utf-8")
        print(f"Wrote web version to {out}")

    body = {
        "subject": subject,
        "preview_text": preview,
        "content": build_html(posts, web_url),
        "description": f"Daily digest {TODAY}",
        "public": False,
        "send_at": send_at,
    }
    if EMAIL_TEMPLATE_ID:
        body["email_template_id"] = int(EMAIL_TEMPLATE_ID)

    result = kit("/broadcasts", method="POST", body=body)
    bid = (result.get("broadcast") or {}).get("id")
    print(f"Created Kit broadcast {bid}: '{subject}', {len(posts)} post(s), scheduled for {send_at}.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"Digest failed: {e}", file=sys.stderr)
        sys.exit(1)
