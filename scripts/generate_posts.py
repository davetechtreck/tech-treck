#!/usr/bin/env python3
"""
Daily auto-poster for Tech Trek.

Uses the Anthropic API (with the built-in web_search tool) to research
today's tech news and write blog posts, then writes them as Markdown
files into posts/ in the format your build.py expects.

Run by .github/workflows/daily-blog-post.yml on a daily schedule.
Requires the ANTHROPIC_API_KEY environment variable (set as a GitHub secret).

NOTE ON THE JSON FIX (2026-09-13):
Earlier versions asked Claude to type out a JSON blob as plain text and
then ran json.loads() on it. That's fragile — if the post body happens to
contain a quotation mark, Claude sometimes forgets to escape it and the
whole parse breaks (this happened in production on 2026-09-13).
This version instead defines a `submit_posts` TOOL and lets Claude call it
with structured arguments. The Anthropic API itself guarantees that a tool
call's arguments are valid, correctly-escaped JSON — there is no longer any
free-text JSON for us to parse or for a stray quote to corrupt.
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

# ---- The structured tool Claude must call to hand back its work ------------
# Defining this as a tool (rather than asking for JSON as plain text) means
# the Anthropic API parses and validates the arguments for us — a quotation
# mark or newline inside "body" can never again produce a JSONDecodeError.
SUBMIT_POSTS_TOOL = {
    "name": "submit_posts",
    "description": (
        "Submit the finished blog post(s) once research and writing are complete. "
        "Call this exactly once, as your final action."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Punchy, specific, under 70 chars, single line, no line breaks.",
                        },
                        "snippet": {
                            "type": "string",
                            "description": "One sentence, under 160 chars, single line, for meta/preview use.",
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
                    },
                    "required": ["title", "snippet", "tags", "body"],
                },
            }
        },
        "required": ["posts"],
    },
}


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
- Free to use normal punctuation, including quotation marks, within the
  text — you don't need to avoid them or write around them

Do not use "---" on its own line anywhere in the body (no Markdown
horizontal rules) — the site's frontmatter parser treats a lone "---" line
as end-of-metadata, so one inside a post body would corrupt the page.

Write the body as plain Markdown prose only. Do NOT include citation
markup, footnote markers, <cite> tags, source-index brackets like [1], or
any inline attribution syntax — state facts directly in your own words with
no annotation, the way a published blog post reads.

Do your research first. Once you're done writing, call the submit_posts
tool exactly once with your finished post(s) as its arguments — that's how
you deliver your final answer, not as a message to me.
"""


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
        max_tokens=4000,  # a bit of headroom over the old 3000: tool-call
                           # arguments carry a small amount of schema
                           # overhead on top of the post content itself
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES},
            SUBMIT_POSTS_TOOL,
        ],
        messages=[{"role": "user", "content": prompt}],
    )

    # Find the submit_posts tool call. The SDK has already parsed its
    # arguments into a Python dict — there is no text-JSON step left to fail.
    tool_call = next(
        (block for block in response.content if block.type == "tool_use" and block.name == "submit_posts"),
        None,
    )

    if tool_call is None:
        # Claude didn't call the tool — surface whatever it said instead,
        # so a failure here is easy to diagnose from the Action logs.
        text = "".join(block.text for block in response.content if block.type == "text")
        raise RuntimeError(
            "Claude finished without calling submit_posts. "
            f"stop_reason={response.stop_reason!r}. Text output was:\n{text}"
        )

    posts = tool_call.input.get("posts")
    if not isinstance(posts, list) or len(posts) == 0:
        raise ValueError(f"submit_posts was called with no usable 'posts' list: {tool_call.input!r}")

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
