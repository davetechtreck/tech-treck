#!/usr/bin/env python3
"""
Draft writer for Tech Trek.

You write a few lines of YOUR take in notes/today.md. This script reads
them (plus today's brief in briefs/, if there is one), does one targeted web
search to confirm the facts, and drafts ONE post around your opinion.

The draft is saved to drafts/ for you to read and fix. To publish it, move
it into posts/ (on GitHub: open the file, click the pencil, and change the
path from drafts/... to posts/...). Nothing goes live until you do that,
unless you set PUBLISH_DIRECT = True below.

No notes file = no post. Nothing is written without your input.

Run by .github/workflows/daily-blog-post.yml whenever you commit
notes/today.md (or by hand with "Run workflow").
Requires the ANTHROPIC_API_KEY environment variable (a GitHub secret).
"""

import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import anthropic

# ---- Config ----------------------------------------------------------------

POSTS_DIR = Path("posts")
DRAFTS_DIR = Path("drafts")
BRIEFS_DIR = Path("briefs")
NOTES_FILE = Path("notes/today.md")

PUBLISH_DIRECT = False  # True = write straight to posts/ (skips your review)
TIMEZONE = "America/Toronto"
MODEL = "claude-sonnet-4-5"
TAGLINE = "field notes on Tech"
MAX_SEARCHES = 1  # one targeted search to confirm facts; each search costs
                  # about $0.01 plus the tokens of its results

# Uses the AMAZON_TAG / AMAZON_DOMAIN repo variables if set, otherwise the
# tag below. Set the tag to "" and leave the variable unset to skip links.
AMAZON_AFFILIATE_TAG = os.environ.get("AMAZON_TAG", "").strip() or "techtreck02-20"
AMAZON_DOMAIN = os.environ.get("AMAZON_DOMAIN", "").strip() or "amazon.com"

AFFILIATE_DISCLOSURE = (
    "\n\n*As an Amazon Associate I earn from qualifying purchases. Tech Trek "
    "is a participant in the Amazon Services LLC Associates Program. Some "
    "links in this post may be affiliate links; if you buy something through "
    "them, we may earn a small commission at no extra cost to you.*"
)

# ---- Frontmatter format (matches build.py's parser) --------------------
# Values are written WITHOUT quotes, tags are a plain comma-separated string,
# and the preview field is called "snippet".

FRONTMATTER_TEMPLATE = """---
title: {title}
date: {date}
tags: {tags}
snippet: {snippet}
---

{body}
"""

# ---- The structured tool Claude calls to hand back its draft ---------------

SUBMIT_POST_TOOL = {
    "name": "submit_post",
    "description": (
        "Submit the finished draft once research and writing are complete. "
        "Call this exactly once, as your final action."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Specific, under 70 chars, single line, no line breaks.",
            },
            "snippet": {
                "type": "string",
                "description": "One sentence, under 160 chars, single line, for preview use.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 short lowercase tag strings.",
            },
            "body": {
                "type": "string",
                "description": "The full Markdown body of the post.",
            },
            "product_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exact names of real, currently-purchasable products named in "
                    "the body, written character-for-character as in the body "
                    "(e.g. 'Sony WH-1000XM6'). Empty list if none."
                ),
            },
            "sources": {
                "type": "array",
                "description": "The pages the facts in the post came from.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Site name, e.g. 'The Verge'."},
                        "url": {"type": "string", "description": "Full https URL of the page."},
                    },
                    "required": ["name", "url"],
                },
            },
        },
        "required": ["title", "snippet", "tags", "body", "product_mentions", "sources"],
    },
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def today_local():
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def existing_titles() -> list[str]:
    """Titles of recent posts and drafts, so a topic isn't repeated."""
    titles = []
    for folder in (POSTS_DIR, DRAFTS_DIR):
        if not folder.exists():
            continue
        for f in sorted(folder.glob("*.md"))[-40:]:
            text = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.MULTILINE)
            if m:
                titles.append(m.group(1))
    return titles


def read_notes():
    if not NOTES_FILE.exists():
        return ""
    return NOTES_FILE.read_text(encoding="utf-8", errors="ignore").strip()


def read_brief(day):
    path = BRIEFS_DIR / f"{day.isoformat()}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()[:6000]


def build_prompt(notes: str, brief: str, avoid_titles: list[str]) -> str:
    avoid_block = ""
    if avoid_titles:
        avoid_block = (
            "Do NOT repeat these topics, the blog already covered them:\n"
            + "\n".join(f"- {t}" for t in avoid_titles[-30:])
            + "\n\n"
        )
    brief_block = ""
    if brief:
        brief_block = f"TODAY'S NEWS BRIEF (background and source links):\n<brief>\n{brief}\n</brief>\n\n"

    search_plural = "" if MAX_SEARCHES == 1 else "es"
    return f"""You are drafting one post for "Tech Trek" (tagline: "{TAGLINE}"), a
consumer tech and gadgets blog. The post is the author's own: it is built
around THE AUTHOR'S NOTES below, which say which story to cover and what
the author thinks about it.

AUTHOR'S NOTES:
<notes>
{notes}
</notes>

{brief_block}{avoid_block}How to write it:
- Make the author's take the spine of the post. Express their stated
  opinions as theirs, in a confident, clear, conversational voice. No fluff,
  no "in today's fast-paced digital world" openers, no "in conclusion"
  endings, no stock phrases like "game-changer".
- NEVER invent opinions, hands-on testing, ownership, or personal
  experience. If the notes don't say the author used something, don't imply
  they did.
- Vary the structure from post to post. Don't default to the same
  intro / three points / verdict template. Open with the most interesting
  specific thing, not a throat-clear.
- 350-500 words, Markdown, no title heading inside the body (the title lives
  in frontmatter), no "---" on its own line, no citation markup, no
  footnote markers, no <cite> tags.

Facts: you have {MAX_SEARCHES} search{search_plural}. Use it to confirm the
specific facts for the story the notes point to (exact model name, price,
specs, dates). State only facts you found in the brief or in search results.
If a price or spec isn't confirmed by a source, leave it out or say it isn't
confirmed yet. Do not search again once your budget is used.

Name each real, purchasable product exactly the same way in the body and in
product_mentions (e.g. "Sony WH-1000XM6", not "the new headphones"), and
re-read your body for named products before finishing. In sources, list the
pages your facts came from (name and full URL).

Do your research first, then call the submit_post tool exactly once with
the finished draft. That is how you deliver your answer, not as a message.
"""


def _strip_citation_tags(text: str) -> str:
    """Web-search responses sometimes wrap claims in <cite ...> tags. build.py
    would show them as raw text, so remove the tags and keep the text."""
    text = re.sub(r"<cite[^>]*>", "", text)
    return re.sub(r"</cite>", "", text)


def call_claude(prompt: str) -> dict:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES},
            SUBMIT_POST_TOOL,
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    tool_call = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_post"),
        None,
    )
    if tool_call is None:
        text = "".join(b.text for b in response.content if b.type == "text")
        raise RuntimeError(
            "Claude finished without calling submit_post. "
            f"stop_reason={response.stop_reason!r}. Text output was:\n{text}"
        )

    post = tool_call.input
    for key in ("title", "snippet", "body"):
        if not isinstance(post.get(key), str) or not post[key].strip():
            raise ValueError(f"submit_post is missing '{key}': {post!r}")
    return post


def _amazon_search_url(product_name: str) -> str:
    url = f"https://www.{AMAZON_DOMAIN}/s?k={quote_plus(product_name)}"
    if AMAZON_AFFILIATE_TAG:
        url += f"&tag={quote_plus(AMAZON_AFFILIATE_TAG)}"
    return url


def _add_affiliate_links(body: str, product_mentions: list[str]):
    """Link the first mention of each named product to an Amazon search
    (searches don't go stale like a fixed product link can).
    Returns (body, whether_any_link_was_added)."""
    if not AMAZON_AFFILIATE_TAG or not product_mentions:
        return body, False

    linked_any = False
    for product in product_mentions:
        product = product.strip()
        if not product or f"]({_amazon_search_url(product)})" in body:
            continue
        pattern = re.compile(re.escape(product))
        if pattern.search(body):
            body = pattern.sub(
                lambda m: f"[{m.group(0)}]({_amazon_search_url(product)})",
                body,
                count=1,
            )
            linked_any = True
    return body, linked_any


def _sources_line(sources) -> str:
    items = []
    for s in sources or []:
        url = str(s.get("url", "")).strip()
        name = re.sub(r"[\[\]]", "", " ".join(str(s.get("name", "source")).split()))
        if url.startswith("http"):
            items.append(f"[{name}]({url})")
    return ("\n\n**Sources:** " + ", ".join(items)) if items else ""


def _single_line(text: str) -> str:
    """Frontmatter fields must be one line (build.py reads them line by line)."""
    return " ".join(text.split())


def write_post(post: dict, today) -> Path:
    out_dir = POSTS_DIR if PUBLISH_DIRECT else DRAFTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    title = _single_line(_strip_citation_tags(post["title"]))
    path = out_dir / f"{today.isoformat()}-{slugify(title)}.md"

    tags = ", ".join(t.strip() for t in post.get("tags", []) if t.strip())

    body = _strip_citation_tags(post["body"])
    body = re.sub(r"(?m)^\s*---+\s*$", "", body)  # no horizontal rules
    body, linked_any = _add_affiliate_links(body, post.get("product_mentions", []))
    body = body.rstrip() + _sources_line(post.get("sources"))
    if linked_any:
        body += AFFILIATE_DISCLOSURE

    content = FRONTMATTER_TEMPLATE.format(
        title=title,
        date=today.isoformat(),
        tags=tags,
        snippet=_single_line(_strip_citation_tags(post.get("snippet", ""))),
        body=body,
    )
    path.write_text(content, encoding="utf-8")
    return path


def main():
    notes = read_notes()
    if len(notes) < 20:
        print("No notes found in notes/today.md (or too short). Nothing to draft.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    today = today_local()
    print(f"[{datetime.now().isoformat()}] Drafting one post from your notes...")
    prompt = build_prompt(notes, read_brief(today), existing_titles())
    post = call_claude(prompt)

    path = write_post(post, today)
    print(f"  wrote {path}")
    print(f"  product_mentions from model: {post.get('product_mentions', [])!r}")
    if not PUBLISH_DIRECT:
        print("  Review it, then move it into posts/ to publish.")
    print("Done.")


if __name__ == "__main__":
    main()
