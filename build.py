#!/usr/bin/env python3
"""
Publish your edited drafts.

The daily generator writes each new post into drafts/. You open it, add your
own photo and your own take, and at 9:00am this script moves it into posts/,
where the site builder picks it up.

Every draft starts with an "[[ADD YOUR PHOTO ...]]" line and ends with a
"My take" section holding an "[[ADD YOUR TAKE ...]]" line. A draft is NOT
published while either line is still there. Replace the photo line with your
photo (or delete it if you have none), write your take and delete that line,
and the draft goes live at the next 9:00am run.

Set REQUIRE_EDIT=false in the workflow to publish drafts even if you haven't
edited them. In that case the placeholder lines are removed automatically, so
they never show up on the site.

Standard library only.
"""

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DRAFTS_DIR = Path("drafts")
POSTS_DIR = Path("posts")
REQUIRE_EDIT = os.environ.get("REQUIRE_EDIT", "true").strip().lower() != "false"

# Any "[[ADD YOUR SOMETHING: ... ]]" placeholder the generator wrote.
MARKER_RE = re.compile(r"\[\[ADD YOUR [A-Z ]+:.*?\]\]", re.DOTALL)
TAKE_BLOCK_RE = re.compile(r"\n*## My take\s*\n+\[\[ADD YOUR TAKE:.*?\]\]", re.DOTALL)


def has_frontmatter(text: str) -> bool:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return bool(m and re.search(r"^title:", m.group(1), re.M) and re.search(r"^date:", m.group(1), re.M))


def stamp_published(text: str) -> str:
    """Add the exact publish time (Toronto) to the top section, so Google sees when it went live."""
    m = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not m or re.search(r"^published:", m.group(2), re.M):
        return text
    now = datetime.now(ZoneInfo("America/Toronto")).replace(microsecond=0).isoformat()
    return m.group(1) + m.group(2) + f"\npublished: {now}" + m.group(3) + text[m.end():]


def placeholder_names(text: str) -> list[str]:
    return sorted({m.group(0)[2:].split(":")[0] for m in MARKER_RE.finditer(text)})


def strip_placeholders(text: str) -> str:
    text = TAKE_BLOCK_RE.sub("", text)
    text = MARKER_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def main():
    if not DRAFTS_DIR.is_dir():
        print("No drafts/ folder yet. Nothing to publish.")
        return
    drafts = sorted(DRAFTS_DIR.glob("*.md"))
    if not drafts:
        print("No drafts waiting. Nothing to publish.")
        return

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    published = held = 0
    for f in drafts:
        text = f.read_text(encoding="utf-8", errors="ignore")
        names = placeholder_names(text)
        if REQUIRE_EDIT and names:
            held += 1
            print(f"[HELD] {f.name}: still has the {' and '.join(repr(n.title()) for n in names)} line. "
                  "Replace or delete it to publish.")
            continue
        if not has_frontmatter(text):
            held += 1
            print(f"[HELD] {f.name}: the top of the file (title and date between --- lines) looks broken.")
            continue
        target = POSTS_DIR / f.name
        if target.exists():
            held += 1
            print(f"[HELD] {f.name}: posts/{f.name} already exists.")
            continue
        if names:
            text = strip_placeholders(text)  # only reached when REQUIRE_EDIT is false
        text = stamp_published(text)
        target.write_text(text, encoding="utf-8")
        f.unlink()
        published += 1
        print(f"[PUBLISHED] {f.name} -> posts/{f.name}")

    print(f"Done. Published {published}, held {held}.")


if __name__ == "__main__":
    main()
