#!/usr/bin/env python3
"""
Tech Trek — daily newsletter digest.

Stdlib only, matching build.py's no-dependency style.

What it does, once a day (run via GitHub Actions cron):
  1. Scans posts/*.md for posts dated today.
  2. If there are none, exits quietly (no email sent, no API calls wasted).
  3. Pulls the current subscriber list from Netlify Forms.
  4. Sends everyone one digest email (via the Resend API) listing today's posts.

Required environment variables (set as GitHub Actions secrets):
  NETLIFY_ACCESS_TOKEN   Personal access token from Netlify (User settings > Applications)
  NETLIFY_SITE_ID        Your site's API ID (Site settings > General > Site details)
  RESEND_API_KEY         API key from resend.com
  FROM_EMAIL             e.g. "Tech Trek <digest@yourdomain.com>" (domain must be verified in Resend)
  SITE_URL               e.g. "https://techtrek.example.com" (no trailing slash)

Optional:
  POSTS_DIR              default "posts"
  FORM_NAME              default "newsletter" (must match the <form name="..."> in popup-signup.html)
  DIGEST_DATE            override "today" for testing, format YYYY-MM-DD
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NETLIFY_TOKEN = os.environ.get("NETLIFY_ACCESS_TOKEN")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
POSTS_DIR = os.environ.get("POSTS_DIR", "posts")
FORM_NAME = os.environ.get("FORM_NAME", "newsletter")
TODAY = os.environ.get("DIGEST_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def http_json(url, method="GET", headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} -> {e.code}: {e.read().decode('utf-8', 'ignore')}")


def parse_frontmatter(text):
    """Very small '---\\nkey: value\\n---' frontmatter parser."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    raw_fm, body = m.group(1), m.group(2)
    fm = {}
    for line in raw_fm.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip().lower()] = val.strip().strip('"').strip("'")
    return fm, body


def find_todays_posts():
    posts = []
    posts_dir = Path(POSTS_DIR)
    if not posts_dir.exists():
        fail(f"posts directory '{POSTS_DIR}' not found (cwd: {os.getcwd()})")

    for md_file in sorted(posts_dir.glob("*.md")):
        fm, body = parse_frontmatter(md_file.read_text(encoding="utf-8"))
        date = fm.get("date", "")[:10]  # tolerate a trailing time component
        if date != TODAY:
            continue
        title = fm.get("title", md_file.stem)
        slug = fm.get("slug", md_file.stem)
        excerpt = fm.get("excerpt") or fm.get("description") or ""
        if not excerpt:
            # fall back to the first non-empty line of the body
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    excerpt = (line[:180] + "…") if len(line) > 180 else line
                    break
        posts.append({"title": title, "slug": slug, "excerpt": excerpt})
    return posts


def get_form_id():
    forms = http_json(
        f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/forms",
        headers={"Authorization": f"Bearer {NETLIFY_TOKEN}"},
    )
    for f in forms:
        if f.get("name") == FORM_NAME:
            return f["id"]
    fail(
        f"No Netlify form named '{FORM_NAME}' found yet. "
        "It only appears after your site has been deployed at least once "
        "with popup-signup.html's <form> in the built HTML."
    )


def get_subscribers(form_id):
    submissions = http_json(
        f"https://api.netlify.com/api/v1/forms/{form_id}/submissions",
        headers={"Authorization": f"Bearer {NETLIFY_TOKEN}"},
    )
    emails = set()
    for s in submissions:
        email = (s.get("data") or {}).get("email")
        if email:
            emails.add(email.strip().lower())
    return sorted(emails)


def build_digest_html(posts):
    items = []
    for p in posts:
        url = f"{SITE_URL}/{p['slug']}" if SITE_URL else p["slug"]
        items.append(
            f"<li style='margin-bottom:18px'>"
            f"<a href='{url}' style='font-size:17px;font-weight:600;text-decoration:none;color:#111'>{p['title']}</a>"
            f"<p style='margin:4px 0 0;color:#555;font-size:14px'>{p['excerpt']}</p>"
            f"</li>"
        )
    return (
        "<div style='font-family:Georgia,serif;max-width:560px;margin:0 auto'>"
        f"<h2 style='font-family:monospace;font-size:14px;letter-spacing:1px;color:#888;text-transform:uppercase'>Tech Trek · {TODAY}</h2>"
        f"<ul style='list-style:none;padding:0'>{''.join(items)}</ul>"
        "<p style='font-size:12px;color:#999;margin-top:32px'>You're receiving this because you subscribed at Tech Trek.</p>"
        "</div>"
    )


def send_email(to_email, html):
    http_json(
        "https://api.resend.com/emails",
        method="POST",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        body={
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": f"Tech Trek daily digest — {TODAY}",
            "html": html,
        },
    )


def main():
    for var, val in [
        ("NETLIFY_ACCESS_TOKEN", NETLIFY_TOKEN),
        ("NETLIFY_SITE_ID", NETLIFY_SITE_ID),
        ("RESEND_API_KEY", RESEND_API_KEY),
        ("FROM_EMAIL", FROM_EMAIL),
    ]:
        if not val:
            fail(f"missing required env var {var}")

    posts = find_todays_posts()
    if not posts:
        print(f"No posts dated {TODAY} — nothing to send.")
        return

    form_id = get_form_id()
    subscribers = get_subscribers(form_id)
    if not subscribers:
        print("No subscribers yet — skipping send.")
        return

    html = build_digest_html(posts)
    sent, errors = 0, 0
    for email in subscribers:
        try:
            send_email(email, html)
            sent += 1
        except Exception as e:
            errors += 1
            print(f"Failed to send to {email}: {e}", file=sys.stderr)
        time.sleep(0.3)  # gentle pacing against rate limits

    print(f"Done. {len(posts)} post(s), sent to {sent} subscriber(s), {errors} failure(s).")


if __name__ == "__main__":
    main()
