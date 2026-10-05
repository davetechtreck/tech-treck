#!/usr/bin/env python3
"""
Daily tech brief for Tech Treck.

Pulls headlines from a few free RSS feeds, asks Claude (cheap Haiku model,
ONE short call) to pick the top stories and suggest an angle + products,
then saves briefs/YYYY-MM-DD.md with Amazon affiliate search links.

Pure standard library. Needs env var ANTHROPIC_API_KEY.
Optional env vars: AMAZON_TAG, AMAZON_DOMAIN (default amazon.com), FORCE=true.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

TIMEZONE = "America/Toronto"
MODEL = "claude-haiku-4-5-20251001"
FEEDS = [
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
]
MAX_PER_FEED = 12
MAX_AGE_HOURS = 36
STORIES = 6

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIEFS_DIR = os.path.join(ROOT, "briefs")


def local_now():
    return datetime.now(ZoneInfo(TIMEZONE))


def in_send_window(now):
    # 7:00-8:29 local time. The workflow has two cron times (one for summer
    # time, one for winter time); this check lets only the right one through.
    return now.hour == 7 or (now.hour == 8 and now.minute < 30)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TechTreckBrief/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def clean(text, limit):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def parse_feed(xml_bytes, source):
    root = ET.fromstring(xml_bytes)
    items = []
    for el in root.iter():
        if strip_ns(el.tag) not in ("item", "entry"):
            continue
        f = {}
        for child in el:
            name = strip_ns(child.tag)
            if name == "link":
                f["link"] = child.get("href") or (child.text or "").strip()
            elif name in ("title", "description", "summary", "pubDate", "published", "updated"):
                f.setdefault(name, child.text or "")
        items.append({
            "source": source,
            "title": clean(f.get("title"), 200),
            "link": f.get("link", ""),
            "desc": clean(f.get("description") or f.get("summary"), 220),
            "date": parse_date(f.get("pubDate") or f.get("published") or f.get("updated")),
        })
    return items


def collect_items():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    out = []
    for source, url in FEEDS:
        try:
            items = parse_feed(fetch(url), source)
        except Exception as e:  # one broken feed shouldn't stop the brief
            print(f"Skipping {source}: {e}")
            continue
        recent = [i for i in items if i["title"] and (i["date"] is None or i["date"] >= cutoff)]
        out.extend(recent[:MAX_PER_FEED])
    return out


SYSTEM = (
    "You are the research editor for a consumer-tech blog (phones, laptops, "
    "wearables, headphones, smart home, gaming hardware, cameras). From the "
    "headlines provided, pick the {n} most significant or interesting stories "
    "for everyday readers and merge duplicates. Reply with ONLY valid JSON, no "
    "markdown fences, shaped as: "
    '{{"stories":[{{"headline":"...","summary":"two sentences in your own words",'
    '"source_name":"...","source_url":"...","angle":"one sentence: an angle the '
    'blogger could take","products":["brand + model", "..."]}}]}}. '
    "Rules: use only facts present in the provided text; never state a price, "
    "spec or date that is not in it; products must be 0-3 real, specific "
    "consumer products closely tied to the story (used as Amazon search terms), "
    "never invented models."
)


def call_claude(items):
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. [{it['source']}] {it['title']} | {it['desc']} | {it['link']}")
    body = {
        "model": MODEL,
        "max_tokens": 1800,
        "system": SYSTEM.format(n=STORIES),
        "messages": [{"role": "user", "content": "\n".join(lines)}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


def parse_stories(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)["stories"]


def affiliate_link(term):
    domain = os.environ.get("AMAZON_DOMAIN", "").strip() or "amazon.com"
    tag = os.environ.get("AMAZON_TAG", "").strip()
    url = f"https://www.{domain}/s?k={quote_plus(term)}"
    if tag:
        url += f"&tag={quote_plus(tag)}"
    return url


def render(stories, now):
    day = f"{now.strftime('%A, %B')} {now.day}, {now.year}"
    out = [f"# Tech brief: {day}", ""]
    if not os.environ.get("AMAZON_TAG", "").strip():
        out += ["> AMAZON_TAG isn't set, so the product links below are NOT affiliate links yet.", ""]
    for n, s in enumerate(stories, 1):
        out += [
            f"## {n}. {s['headline']}",
            "",
            s["summary"],
            "",
            f"**Source:** [{s.get('source_name', 'link')}]({s.get('source_url', '')})",
            "",
            f"**Your angle:** {s.get('angle', '')}",
            "",
        ]
        products = s.get("products") or []
        if products:
            out.append("**Products (affiliate links):**")
            out += [f"- [{p}]({affiliate_link(p)})" for p in products]
            out.append("")
    out += ["---", "Verify specs and prices at the source before publishing, and "
            "disclose affiliate links in the post."]
    return "\n".join(out) + "\n"


def main():
    now = local_now()
    force = os.environ.get("FORCE", "").lower() == "true"
    if not force and not in_send_window(now):
        print(f"Local time is {now:%H:%M}; outside the 7:00-8:30 window. Skipping.")
        return
    os.makedirs(BRIEFS_DIR, exist_ok=True)
    path = os.path.join(BRIEFS_DIR, f"{now:%Y-%m-%d}.md")
    if os.path.exists(path) and not force:
        print("Today's brief already exists. Skipping.")
        return
    items = collect_items()
    if not items:
        print("No headlines found. Skipping.")
        return
    stories = parse_stories(call_claude(items))
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(stories, now))
    print(f"Wrote {path} with {len(stories)} stories.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Brief failed: {e}")
        sys.exit(1)
