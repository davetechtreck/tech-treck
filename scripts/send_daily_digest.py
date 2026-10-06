#!/usr/bin/env python3
"""
Tech Trek: daily newsletter digest, sent through Kit.

Replaces the old Netlify Forms + Resend version. Kit now holds your
subscribers, sends the email, and adds the unsubscribe link.

Once a day (8:00-9:30pm Toronto time, right after the daily post is written):
  1. finds posts in posts/ dated today (exits quietly if there are none),
  2. skips if today's digest was already created in Kit,
  3. creates a Kit broadcast to ALL your subscribers, scheduled to send
     15 minutes from now so the site has time to finish deploying.

Standard library only. Environment variables:
  KIT_API_KEY   Your Kit V4 API key (GitHub secret)   [required]
  SITE_URL      default "https://techtreck.tech"
  DRY_RUN       "true" = check the key and print the email, send nothing
  FORCE         "true" = ignore the time window and the duplicate check
  DIGEST_DATE   override "today" for testing (YYYY-MM-DD)
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
POSTS_DIR = Path("posts")

NOW_LOCAL = datetime.now(ZoneInfo(TIMEZONE))
TODAY = os.environ.get("DIGEST_DATE", "").strip() or NOW_LOCAL.strftime("%Y-%m-%d")


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


def in_send_window(now):
    mins = now.hour * 60 + now.minute
    return 20 * 60 <= mins < 20 * 60 + 90


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


def build_html(posts):
    items = []
    for p in posts:
        items.append(
            "<div style='margin-bottom:22px'>"
            f"<a href='{html.escape(p['url'])}' style='font-size:19px;font-weight:700;"
            f"text-decoration:none;color:#111'>{html.escape(p['title'])}</a>"
            f"<p style='margin:6px 0 8px;color:#444;font-size:15px;line-height:1.5'>{html.escape(p['excerpt'])}</p>"
            f"<a href='{html.escape(p['url'])}' style='font-size:14px;color:#2F49FF'>Read the full post &rarr;</a>"
            "</div>"
        )
    return (
        "<div style='font-family:Georgia,serif;max-width:560px;margin:0 auto'>"
        f"<p style='font-family:monospace;font-size:12px;letter-spacing:1px;color:#888;"
        f"text-transform:uppercase'>Tech Trek &middot; {TODAY}</p>"
        + "".join(items)
        + "</div>"
    )


def already_created(subject):
    data = kit("/broadcasts?per_page=50")
    return any((b or {}).get("subject") == subject for b in data.get("broadcasts", []))


def main():
    if not KIT_API_KEY:
        fail("KIT_API_KEY is not set.")

    if not FORCE and not in_send_window(NOW_LOCAL):
        print(f"Local time is {NOW_LOCAL:%H:%M}, outside the 8:00-9:30pm window. Skipping.")
        return

    posts = find_todays_posts()
    if not posts:
        print(f"No posts dated {TODAY}. Nothing to send.")
        return

    subject = f"Tech Trek daily digest: {TODAY}"
    preview = posts[0]["title"][:140]
    send_at = (datetime.now(timezone.utc) + timedelta(minutes=SEND_DELAY_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")

    if DRY_RUN:
        acct = kit("/account")  # proves the API key works
        print(f"DRY RUN: Kit key OK ({json.dumps(acct)[:120]}).")
        print(f"Would send '{subject}' with {len(posts)} post(s) at {send_at}:")
        for p in posts:
            print(f"  - {p['title']}  {p['url']}")
        return

    if not FORCE and already_created(subject):
        print("Today's digest was already created. Skipping.")
        return

    result = kit("/broadcasts", method="POST", body={
        "subject": subject,
        "preview_text": preview,
        "content": build_html(posts),
        "description": f"Daily digest {TODAY}",
        "public": False,
        "send_at": send_at,
    })
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
