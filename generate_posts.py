#!/usr/bin/env python3
"""
Daily auto-poster for Tech Trek.

Uses the Anthropic API (with the built-in web_search tool) to research
today's tech news and write 3 original blog posts, then writes them as
Markdown files into posts/ in the format your build.py expects.

Run by .github/workflows/daily-blog-post.yml on a daily schedule.
Requires the ANTHROPIC_API_KEY environment variable (set as a GitHub secret).
"""

import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

import anthropic

# ---- Config ----------------------------------------------------------------

POSTS_DIR = Path("posts")
NUM_POSTS = 3
MODEL = "claude-sonnet-4-5"  # update if you want a different model
TAGLINE = "field notes on Tech"

# ---- Frontmatter format ------------------------------------------------
# NOTE: I don't have your build.py, so this guesses a common frontmatter
# shape (title / date / tags / summary). Open build.py, find where it
# parses each post's frontmatter, and adjust FRONTMATTER_TEMPLATE below
# (and the fields requested in PROMPT) to match exactly. If field names
# don't match what build.py expects, posts will exist on disk but won't
# render correctly on the site.

FRONTMATTER_TEMPLATE = """---
title: "{title}"
date: {date}
tags: [{tags}]
summary: "{summary}"
---

{body}
"""


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def existing_titles() -> list[str]:
    """Pull titles of existing posts so we don't repeat a topic."""
    titles = []
    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md"))[-40:]:  # last 40 is plenty of context
            text = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.MULTILINE)
            if m:
                titles.append(m.group(1))
    return titles


def build_prompt(avoid_titles: list[str]) -> str:
    avoid_block = ""
    if avoid_titles:
        avoid_block = (
            "Do NOT write about these topics again — the blog already covered them:\n"
            + "\n".join(f"- {t}" for t in avoid_titles[-30:])
            + "\n\n"
        )

    return f"""You write for "Tech Trek" (tagline: "{TAGLINE}"), a tech blog with a
sharp, NYT-meets-tech voice: confident, clear, a little opinionated, no fluff,
no "in today's fast-paced digital world" filler.

Use web search to find real, current tech news from the last 24-48 hours.
Then write exactly {NUM_POSTS} distinct blog posts about 3 DIFFERENT stories
(don't cover the same story twice). Mix it up across categories where
possible: e.g. one on a product/company launch, one on AI/software, one on
a broader industry or policy story.

{avoid_block}Each post should be:
- 400-700 words, written in Markdown (no title heading inside body, the
  title lives in frontmatter)
- Grounded in the specific facts you found via search (name the company,
  product, numbers, dates)
- Written as an actual opinionated blog post, not a press-release summary

Return ONLY valid JSON (no markdown fences, no commentary) as a list of
exactly {NUM_POSTS} objects, each with keys:
  "title": string (punchy, specific, under 70 chars)
  "summary": string (one sentence, under 160 chars, for meta/preview use)
  "tags": list of 2-4 short lowercase tag strings
  "body": string (the full Markdown body, using \\n for newlines)
"""


def call_claude(prompt: str) -> list[dict]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Anthropic may return multiple text blocks interleaved with tool-use/
    # tool-result blocks when web_search is used. Concatenate all text blocks.
    text = "".join(block.text for block in response.content if block.type == "text")

    # Strip stray code fences if the model added them despite instructions.
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        posts = json.loads(text)
    except json.JSONDecodeError as e:
        print("Failed to parse model output as JSON. Raw output was:\n", text, file=sys.stderr)
        raise e

    if not isinstance(posts, list) or len(posts) == 0:
        raise ValueError(f"Expected a non-empty list of posts, got: {posts!r}")

    return posts


def write_post(post: dict, today: date, index: int) -> Path:
    slug = slugify(post["title"])
    filename = f"{today.isoformat()}-{slug}.md"
    path = POSTS_DIR / filename

    tags = ", ".join(f'"{t}"' for t in post.get("tags", []))
    content = FRONTMATTER_TEMPLATE.format(
        title=post["title"].replace('"', "'"),
        date=today.isoformat(),
        tags=tags,
        summary=post.get("summary", "").replace('"', "'"),
        body=post["body"],
    )
    path.write_text(content, encoding="utf-8")
    return path


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()

    print(f"[{datetime.now().isoformat()}] Generating {NUM_POSTS} posts...")
    avoid = existing_titles()
    prompt = build_prompt(avoid)
    posts = call_claude(prompt)

    written = []
    for i, post in enumerate(posts[:NUM_POSTS]):
        path = write_post(post, today, i)
        written.append(path)
        print(f"  wrote {path}")

    if len(written) < NUM_POSTS:
        print(f"WARNING: only {len(written)}/{NUM_POSTS} posts were written.", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
