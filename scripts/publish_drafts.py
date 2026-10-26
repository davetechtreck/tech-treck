#!/usr/bin/env python3
"""
Publish your edited drafts.

The daily generator writes each new post into drafts/. You open it, add your
own take (and photos, corrections, whatever makes it better), and at 9:00am
this script moves it into posts/, where the site builder picks it up.

A draft is NOT published while it still contains the "[[ADD YOUR TAKE" line
that the generator puts at the end. Delete that line (after writing your take)
and the draft goes live at the next 9:00am run.

Set REQUIRE_EDIT=false in the workflow to publish drafts even if you haven't
edited them.

Standard library only.
"""

import os
import re
import shutil
import sys
from pathlib import Path

DRAFTS_DIR = Path("drafts")
POSTS_DIR = Path("posts")
MARKER = "[[ADD YOUR TAKE"
REQUIRE_EDIT = os.environ.get("REQUIRE_EDIT", "true").strip().lower() != "false"


def has_frontmatter(text: str) -> bool:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return bool(m and re.search(r"^title:", m.group(1), re.M) and re.search(r"^date:", m.group(1), re.M))


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
        if REQUIRE_EDIT and MARKER in text:
            held += 1
            print(f"[HELD] {f.name}: still has the 'ADD YOUR TAKE' line. Edit it and delete that line to publish.")
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
        shutil.move(str(f), str(target))
        published += 1
        print(f"[PUBLISHED] {f.name} -> posts/{f.name}")

    print(f"Done. Published {published}, held {held}.")


if __name__ == "__main__":
    main()
