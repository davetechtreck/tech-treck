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
NUM_POSTS = 1
MODEL = "claude-sonnet-4-5"  # update if you want a different model
TAGLINE = "field notes on Tech"
MAX_SEARCHES = 1  # hard cap on web searches per run — search itself costs
                   # $0.01/search, and each result adds input tokens on top,
                   # so this is the main cost lever. Raise it if posts feel
                   # thin on facts; lower it to cut cost further.

# ---- Frontmatter format ------------------------------------------------
# Matched to the real build.py parser:
#   - parse_frontmatter() does NOT strip quotes from values, so fields must
#     be written WITHOUT surrounding quotes (a quoted title would render
#     with literal quote marks on the live page).
#   - the preview-text field is called "snippet", not "summary".
#   - tags are parsed as a plain comma-separated string
#     (meta["tags"].split(",")), not a bracketed/quoted list.
#   - "slug" is optional; build.py derives it from the title if omitted,
#     so we don't need to set it ourselves.

FRONTMATTER_TEMPLATE = """---
title: {title}
date: {date}
tags: {tags}
snippet: {snippet}
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
        # At 3 runs/day, 75 posts is ~25 days of history — enough to
        # catch same-week and recent repeats without the prompt growing huge.
        for f in sorted(POSTS_DIR.glob("*.md"))[-75:]:
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

    if NUM_POSTS == 1:
        count_instruction = "write exactly one blog post about one story"
    else:
        count_instruction = (
            f"write exactly {NUM_POSTS} blog posts, each about a different "
            f"story (never cover the same story twice)"
        )
    search_plural = "" if MAX_SEARCHES == 1 else "es"
    return f"""You write for "Tech Trek" (tagline: "{TAGLINE}"), a tech blog with a
sharp, NYT-meets-tech voice: confident, clear, a little opinionated, no fluff,
no "in today's fast-paced digital world" filler.

Use web search to find real, current tech news from the last few hours.
You have a strict budget of {MAX_SEARCHES} search{search_plural} total, so
pick one specific, well-targeted query rather than searching broadly —
don't search again "just to double check." Then {count_instruction}.
Prefer stories that feel fresh rather than something every other outlet
already covered hours ago.

{avoid_block}Each post should be:
- 350-500 words, written in Markdown (no title heading inside body, the
  title lives in frontmatter)
- Grounded in the specific facts you found via search (name the company,
  product, numbers, dates)
- Written as an actual opinionated blog post, not a press-release summary

Do not use "---" on its own line anywhere in the body (no Markdown
horizontal rules) — the site's frontmatter parser treats a lone "---" line
as end-of-metadata, so one inside a post body would corrupt the page.

Write the body as plain Markdown prose only. Do NOT include citation
markup, footnote markers, <cite> tags, source-index brackets like [1], or
any inline attribution syntax — state facts directly in your own words with
no annotation, the way a published blog post reads.

You will do your research and reasoning first, then give your final answer.
Put ONLY the JSON in your very last message content — no narration, notes,
or commentary before or after it, and no markdown code fences around it.

Return a list of exactly {NUM_POSTS} object{'' if NUM_POSTS == 1 else 's'}, each with keys:
  "title": string (punchy, specific, under 70 chars, single line, no
     line breaks)
  "snippet": string (one sentence, under 160 chars, single line, for
     meta/preview use)
  "tags": list of 2-4 short lowercase tag strings
  "body": string (the full Markdown body, using \\n for newlines)
"""


def _extract_json(text: str) -> str:
    """Pull the JSON payload out of Claude's raw text output. With
    web_search enabled, Claude often narrates its research process before
    (and sometimes after) the actual answer, so a simple strip of leading/
    trailing fences isn't enough — this searches for the JSON wherever it
    lands."""
    # Prefer a fenced code block, wherever it appears in the text.
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # No fence found — fall back to the outermost [...] or {...}, trimming
    # any narration before/after it.
    start_candidates = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not start_candidates:
        return text.strip()
    start = min(start_candidates)
    end_char = "]" if text[start] == "[" else "}"
    end = text.rfind(end_char)
    if end == -1 or end < start:
        return text.strip()
    return text[start : end + 1].strip()


def _strip_citation_tags(text: str) -> str:
    """Claude's web-search-enabled responses sometimes embed inline
    <cite index="...">...</cite> markup around sourced claims. build.py's
    Markdown converter has no idea what to do with that and would render
    the raw tags as visible text on the live page, so strip the tags and
    keep the text they wrap."""
    text = re.sub(r"<cite[^>]*>", "", text)
    text = re.sub(r"</cite>", "", text)
    return text


def call_claude(prompt: str) -> list[dict]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,  # ceiling for a ~350-500 word post + minimal
                           # reasoning; keeps a worst-case run bounded
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Anthropic may return multiple text blocks interleaved with tool-use/
    # tool-result blocks when web_search is used. Concatenate all text blocks.
    text = "".join(block.text for block in response.content if block.type == "text")

    json_text = _extract_json(text)

    try:
        posts = json.loads(json_text)
    except json.JSONDecodeError as e:
        print("Failed to parse model output as JSON. Raw output was:\n", text, file=sys.stderr)
        raise e

    if not isinstance(posts, list) or len(posts) == 0:
        raise ValueError(f"Expected a non-empty list of posts, got: {posts!r}")

    return posts


def _single_line(text: str) -> str:
    """Frontmatter fields must be one line — build.py's parser reads
    metadata with splitlines(), so a literal newline would truncate or
    corrupt the field."""
    return " ".join(text.split())


def write_post(post: dict, today: date, index: int) -> Path:
    slug = slugify(post["title"])
    filename = f"{today.isoformat()}-{slug}.md"
    path = POSTS_DIR / filename

    # Plain comma-separated tags, no brackets/quotes: build.py reads this
    # field with meta["tags"].split(","), so anything fancier here would
    # leave stray punctuation baked into each tag.
    tags = ", ".join(t.strip() for t in post.get("tags", []) if t.strip())

    content = FRONTMATTER_TEMPLATE.format(
        title=_single_line(_strip_citation_tags(post["title"])),
        date=today.isoformat(),
        tags=tags,
        snippet=_single_line(_strip_citation_tags(post.get("snippet", ""))),
        body=_strip_citation_tags(post["body"]),
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
