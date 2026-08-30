# Tech Trek — static site

A tiny, dependency-free static blog. No CMS, no dashboard, no black box —
just Markdown files and one Python script that turns them into your site.

## Writing a new post

1. Create a new file in `posts/`, named like `YYYY-MM-DD-a-short-slug.md`
2. Copy this format:

   ```
   ---
   title: Your Post Title
   date: 2026-09-01
   tags: tooling, systems
   snippet: One sentence that shows up on the homepage preview.
   ---

   Your post content goes here, in Markdown.

   ## A subheading

   **Bold**, *italic*, `inline code`, [links](https://example.com),
   bullet lists, and code blocks (```) all work.
   ```

3. Run the build:

   ```
   python3 build.py
   ```

4. Check `dist/` — that's your entire site, ready to deploy.

The date must be `YYYY-MM-DD`. `tags` and `snippet` are optional but
recommended (snippet shows on the homepage).

## Deploying to Netlify

**Easiest way (no GitHub needed):**

1. Run `python3 build.py`
2. Go to **https://app.netlify.com/drop**
3. Drag the `dist` folder onto the page
4. Done — you get a live URL immediately

Every time you add a post, repeat: run the build, drag `dist` again.

**Automated way (recommended once you're comfortable with Git):**

1. Push this whole folder (including `posts/`, excluding `dist/`) to a GitHub repo
2. In Netlify: **Add new site → Import an existing project → connect the repo**
3. Set:
   - Build command: `python3 build.py`
   - Publish directory: `dist`
4. Now every `git push` automatically rebuilds and redeploys the site —
   just write a new `.md` file, commit, and push.

## Why this instead of Blogger

Every post here is a plain text file you control. If a post doesn't show
up, it's because the file isn't there or the build script errored (and it
will tell you exactly why, with the filename) — never a silent "the
platform decided not to show it" mystery.

## Files

```
build.py           the entire site generator (no dependencies)
posts/*.md         your posts — this is the only folder you'll touch day-to-day
dist/               generated output — don't edit by hand, it gets wiped on every build
```
