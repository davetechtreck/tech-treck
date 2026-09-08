#!/usr/bin/env python3
"""
Tech Trek static site builder.

Reads Markdown posts from posts/*.md and generates a static site into dist/.
Pure Python standard library — no dependencies to install, ever.

Usage:
    python3 build.py

Then either:
  - drag the dist/ folder onto https://app.netlify.com/drop, or
  - push this whole project to GitHub and point Netlify at it with
    build command `python3 build.py` and publish directory `dist`.
"""
import re
import os
import shutil
import html
from datetime import datetime

SITE_TITLE = "Tech Treck"
SITE_TAGLINE = "field notes on Tech"

# Add or remove entries here — each is (label, url). Shows up in the footer
# on every page. Leave the list empty ( [] ) to show no social links at all.
SOCIAL_LINKS = [
    ("Instagram", "https://www.instagram.com/techtrec3k?stkn=dnh6djY3eHQ5a3dq&utm_source=qr"),
    ("x", "https://x.com/techtre3k"),
    ("Youtube", " https://www.youtube.com/@TechTrecck"),
    ("tiktok" , "https://www.tiktok.com/@tech.tre3k?is_from_webapp=1&sender_device=pc "),
]

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(ROOT, "posts")
DIST_DIR = os.path.join(ROOT, "dist")



<meta name="google-site-verification" content="rqQ61LFUiuVpSxe5tE5XCKxoUCfLE-sS56rFkxEk-Ks" />
# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(text, filename):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
    if not m:
        raise ValueError(
            f"{filename}: missing '---' frontmatter block at the top of the file"
        )
    meta_block, body = m.groups()
    meta = {}
    for line in meta_block.splitlines():
        if not line.strip() or ':' not in line:
            continue
        key, _, value = line.partition(':')
        meta[key.strip()] = value.strip()

    for required in ("title", "date"):
        if required not in meta:
            raise ValueError(f"{filename}: frontmatter is missing '{required}:'")

    try:
        meta["_date_obj"] = datetime.strptime(meta["date"], "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"{filename}: date '{meta['date']}' isn't in YYYY-MM-DD format"
        )

    meta.setdefault("tags", "")
    meta.setdefault("snippet", "")
    return meta, body


# ---------------------------------------------------------------------------
# Minimal Markdown -> HTML (headers, bold, italic, code, links, lists, quotes)
# ---------------------------------------------------------------------------

def inline_md(text):
    text = html.escape(text, quote=False)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


BLOCK_START = re.compile(r'^(#{2,3})\s+|^[-*]\s+|^>|^```')


def markdown_to_html(md):
    lines = md.replace('\r\n', '\n').split('\n')
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if line.strip().startswith('```'):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code = html.escape('\n'.join(code_lines))
            cls = f' class="language-{lang}"' if lang else ''
            out.append(f'<pre><code{cls}>{code}</code></pre>')
            continue

        m = re.match(r'^(#{2,3})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            out.append(f'<h{level}>{inline_md(m.group(2))}</h{level}>')
            i += 1
            continue

        if line.strip().startswith('>'):
            quote_lines = []
            while i < n and lines[i].strip().startswith('>'):
                quote_lines.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append(f'<blockquote>{inline_md(" ".join(quote_lines))}</blockquote>')
            continue

        if re.match(r'^[-*]\s+', line.strip()):
            items = []
            while i < n and re.match(r'^[-*]\s+', lines[i].strip()):
                item_text = re.sub(r'^[-*]\s+', '', lines[i].strip())
                items.append(f'<li>{inline_md(item_text)}</li>')
                i += 1
            out.append('<ul>' + ''.join(items) + '</ul>')
            continue

        if not line.strip():
            i += 1
            continue

        para_lines = [line]
        i += 1
        while i < n and lines[i].strip() and not BLOCK_START.match(lines[i].strip()):
            para_lines.append(lines[i])
            i += 1
        out.append(f'<p>{inline_md(" ".join(l.strip() for l in para_lines))}</p>')

    return '\n'.join(out)


def slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def fmt_date_human(d):
    return f"{d.strftime('%b')} {d.day}, {d.year}"


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

CSS = """
:root{
  --paper:#F7F7F5; --panel:#FFFFFF; --ink:#121212; --ink-soft:#3A3A3A;
  --muted:#767676; --faint:#A2A2A0; --accent:#2F49FF; --accent-ink:#FFFFFF;
  --rule:#E1E1DE; --rule-strong:#C9C9C6; --mono-bg:#EFEFF3;
  --font-serif:'Source Serif 4', Georgia, serif;
  --font-sans:'Space Grotesk', system-ui, sans-serif;
  --font-mono:'JetBrains Mono', ui-monospace, monospace;
}
html[data-theme="dark"]{
  --paper:#0E0F12; --panel:#16171B; --ink:#F2F2F0; --ink-soft:#C7C7C4;
  --muted:#8A8A87; --faint:#55565A; --accent:#6E8CFF; --accent-ink:#0E0F12;
  --rule:#26272C; --rule-strong:#34353A; --mono-bg:#1B1C21;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font-serif);
  font-size:17px;line-height:1.65;-webkit-font-smoothing:antialiased;
  transition:background .3s ease,color .3s ease;}
a{color:inherit;text-decoration:none;}
img{max-width:100%;display:block;}
.shell{max-width:1180px;margin:0 auto;padding:0 24px;}
#scroll-progress{position:fixed;top:0;left:0;height:3px;width:0%;background:var(--accent);z-index:999;}
.u-link{background-image:linear-gradient(var(--accent),var(--accent));background-position:0 100%;
  background-repeat:no-repeat;background-size:0% 2px;transition:background-size .35s cubic-bezier(.4,0,.2,1);padding-bottom:1px;}
.u-link:hover{background-size:100% 2px;}
.reveal{opacity:1;transform:none;transition:opacity .6s cubic-bezier(.16,1,.3,1),transform .6s cubic-bezier(.16,1,.3,1);}
.js .reveal{opacity:0;transform:translateY(18px);}
.js .reveal.in-view{opacity:1;transform:translateY(0);}
@media (prefers-reduced-motion:reduce){.js .reveal{opacity:1;transform:none;}}
header.site-head{position:sticky;top:0;z-index:50;padding:22px 0 0;border-bottom:2px solid var(--ink);background:var(--paper);}
.eyebrow-row{display:flex;justify-content:space-between;align-items:center;font-family:var(--font-mono);
  font-size:11px;letter-spacing:.06em;color:var(--muted);padding-bottom:14px;text-transform:uppercase;}
.eyebrow-row .accent-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);
  margin-right:6px;animation:pulse 1.8s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1);}50%{opacity:.4;transform:scale(1.3);}}
.masthead-row{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:16px;flex-wrap:wrap;gap:12px;}
.brand{font-family:var(--font-serif);font-weight:700;font-size:clamp(32px,6vw,54px);letter-spacing:-0.02em;line-height:1;}
.head-right{display:flex;align-items:center;gap:20px;}
nav.site-nav{display:flex;gap:20px;font-family:var(--font-sans);font-size:13px;font-weight:500;padding-bottom:8px;}
nav.site-nav a{color:var(--ink-soft);}
#theme-toggle{font-family:var(--font-mono);font-size:11px;letter-spacing:.04em;border:1px solid var(--rule-strong);
  background:none;color:var(--ink-soft);padding:6px 10px;border-radius:3px;cursor:pointer;margin-bottom:8px;
  transition:border-color .2s ease,color .2s ease;}
#theme-toggle:hover{border-color:var(--accent);color:var(--accent);}
.signal-bar{height:3px;width:100%;background:linear-gradient(90deg,var(--accent),var(--ink) 0%);
  transform-origin:left;animation:draw-in 1.1s cubic-bezier(.16,1,.3,1) both;}
@keyframes draw-in{from{transform:scaleX(0);}to{transform:scaleX(1);}}
main{padding:40px 0 90px;}
.section-label{font-family:var(--font-mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--rule-strong);padding-bottom:10px;margin-bottom:0;}
.featured{display:grid;grid-template-columns:1.3fr 1fr;gap:36px;padding:32px 0;border-bottom:1px solid var(--rule);align-items:start;}
.featured .post-meta{margin-bottom:14px;}
.featured .post-title{font-size:38px;line-height:1.12;margin:0 0 14px;}
.featured .post-snippet{font-size:17px;}
.featured-side{border-left:1px solid var(--rule);padding-left:32px;display:flex;flex-direction:column;gap:22px;}
.side-item{padding-bottom:18px;border-bottom:1px solid var(--rule);}
.side-item:last-child{border-bottom:none;padding-bottom:0;}
.side-item .post-meta{margin-bottom:6px;}
.side-item .post-title{font-size:17px;line-height:1.3;margin:0;}
.blog-posts{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));border-top:1px solid var(--rule);}
.post-card{padding:28px 24px 28px 0;border-bottom:1px solid var(--rule);border-right:1px solid var(--rule);transition:background .3s ease;}
.blog-posts .post-card:hover{background:var(--panel);}
.post-meta{font-family:var(--font-mono);font-size:11.5px;color:var(--faint);display:flex;gap:8px;align-items:center;
  flex-wrap:wrap;text-transform:uppercase;letter-spacing:.03em;}
.post-meta .dot{opacity:.5;}
.post-title{font-family:var(--font-serif);font-weight:700;font-size:23px;line-height:1.22;margin:10px 0;
  letter-spacing:-0.01em;transition:color .2s ease;}
.post-title a{color:var(--ink);}
.blog-posts .post-card:hover .post-title a,.featured:hover .post-title a{color:var(--accent);}
.post-snippet{color:var(--ink-soft);font-size:15.5px;margin:0 0 14px;line-height:1.6;}
.read-more{font-family:var(--font-sans);font-size:12.5px;font-weight:500;text-transform:uppercase;letter-spacing:.04em;
  display:inline-flex;align-items:center;gap:6px;color:var(--ink);}
.read-more .arrow{transition:transform .25s cubic-bezier(.4,0,.2,1);}
.post-card:hover .read-more .arrow,.featured:hover .read-more .arrow{transform:translateX(5px);}
.tags-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:22px;}
.tags-row a{font-family:var(--font-mono);font-size:11px;color:var(--ink-soft);background:var(--mono-bg);
  border:1px solid var(--rule);padding:4px 9px;border-radius:3px;transition:background .2s ease,color .2s ease;}
.tags-row a:hover{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);}
.post-full{padding:8px 0 40px;max-width:760px;}
.post-full .post-title{font-size:36px;line-height:1.15;margin:14px 0 24px;}
.post-body{font-size:18px;line-height:1.75;}
.post-body>p:first-of-type::first-letter{float:left;font-family:var(--font-serif);font-weight:700;font-size:64px;
  line-height:.8;padding:6px 8px 0 0;color:var(--accent);}
.post-body h2{font-family:var(--font-serif);font-weight:700;font-size:26px;margin:1.8em 0 .6em;}
.post-body h3{font-family:var(--font-serif);font-weight:600;font-size:21px;margin:1.6em 0 .6em;}
.post-body p{margin:0 0 1.3em;}
.post-body a{border-bottom:1px solid var(--accent);}
.post-body blockquote{margin:1.6em 0;padding:4px 0 4px 20px;border-left:3px solid var(--accent);font-style:italic;color:var(--ink-soft);}
.post-body pre{background:var(--mono-bg);border:1px solid var(--rule);border-radius:4px;padding:16px 18px;
  overflow-x:auto;font-family:var(--font-mono);font-size:13.5px;line-height:1.6;margin:1.5em 0;}
.post-body code{font-family:var(--font-mono);font-size:.82em;background:var(--mono-bg);padding:2px 5px;border-radius:3px;}
.post-body pre code{background:none;padding:0;}
.post-body ul{padding-left:1.3em;margin:0 0 1.3em;}
.back-link{font-family:var(--font-sans);font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:.03em;
  display:inline-block;margin-bottom:24px;}
footer.site-foot{border-top:2px solid var(--ink);padding:20px 0 44px;font-family:var(--font-mono);font-size:11.5px;
  color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;text-transform:uppercase;letter-spacing:.03em;}
.social-links{display:flex;gap:14px;}
.social-links a{color:var(--muted);}
.social-links a:hover{color:var(--accent);}
@media (max-width:800px){.featured{grid-template-columns:1fr;}
  .featured-side{border-left:none;padding-left:0;border-top:1px solid var(--rule);padding-top:24px;}}
@media (max-width:640px){.post-card{border-right:none;}}
"""

SCRIPT = """
document.documentElement.classList.add('js');
try{ if(localStorage.getItem('theme')==='dark'){ document.documentElement.setAttribute('data-theme','dark'); } }catch(e){}
var toggle = document.getElementById('theme-toggle');
function syncToggle(){ if(!toggle) return;
  var d = document.documentElement.getAttribute('data-theme')==='dark';
  toggle.textContent = d ? 'light' : 'dark'; }
syncToggle();
if(toggle){ toggle.addEventListener('click', function(){
  var d = document.documentElement.getAttribute('data-theme')==='dark';
  var next = d ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try{ localStorage.setItem('theme', next); }catch(e){}
  syncToggle();
});}
var bar = document.getElementById('scroll-progress');
var scroller = document.scrollingElement || document.documentElement;
function onScroll(){ var max = scroller.scrollHeight - scroller.clientHeight;
  var pct = max > 0 ? (scroller.scrollTop/max)*100 : 0;
  if(bar) bar.style.width = pct + '%'; }
document.addEventListener('scroll', onScroll, {passive:true});
onScroll();
var items = document.querySelectorAll('.reveal');
if('IntersectionObserver' in window){
  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in-view'); io.unobserve(e.target); } });
  }, {threshold:0.1, rootMargin:'0px 0px -30px 0px'});
  items.forEach(function(el){ io.observe(el); });
} else { items.forEach(function(el){ el.classList.add('in-view'); }); }
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<meta name="description" content="{description}"/>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500" rel="stylesheet"/>
<style>{css}</style>
</head>
<body>
<div id="scroll-progress"></div>
<div class="shell">
  <header class="site-head">
    <div class="eyebrow-row">
      <span><span class="accent-dot"></span>{site_title} &#8212; {site_tagline}</span>
    </div>
    <div class="masthead-row">
      <a class="brand" href="{home_href}">{site_title}</a>
      <div class="head-right">
        <nav class="site-nav">
          <a class="u-link" href="{home_href}">index</a>
        </nav>
        <button id="theme-toggle" aria-label="Toggle dark mode">dark</button>
      </div>
    </div>
    <div class="signal-bar"></div>
  </header>
  <main>
"""

FOOT = """
  </main>
  <footer class="site-foot">
    <span>&#169; {site_title}</span>
    <span class="social-links">{social_links}</span>
  </footer>
</div>
<script>{script}</script>
</body>
</html>
"""


def render_social_links():
    if not SOCIAL_LINKS:
        return ""
    return "".join(
        f'<a class="u-link" href="{html.escape(url)}">{html.escape(label)}</a>'
        for label, url in SOCIAL_LINKS
    )


def render_post_card(meta, href, featured=False):
    tags_html = ""
    tag_list = [t.strip() for t in meta["tags"].split(",") if t.strip()]
    if tag_list:
        first_tag = f'<a href="#">{html.escape(tag_list[0])}</a>'
        tags_html = f'<span class="dot">&#183;</span>{first_tag}'
    cls = "featured" if featured else "post-card reveal"
    title_tag = "h2" if not featured else "h2"
    return f"""
    <article class="{cls}">
      <p class="post-meta"><time>{fmt_date_human(meta['_date_obj'])}</time>{tags_html}</p>
      <{title_tag} class="post-title"><a href="{href}">{html.escape(meta['title'])}</a></{title_tag}>
      <p class="post-snippet">{html.escape(meta['snippet'])}</p>
      <a class="read-more" href="{href}">read <span class="arrow">&#8594;</span></a>
    </article>
    """


def render_side_item(meta, href):
    return f"""
    <div class="side-item">
      <p class="post-meta"><time>{fmt_date_human(meta['_date_obj'])}</time></p>
      <h3 class="post-title"><a href="{href}">{html.escape(meta['title'])}</a></h3>
    </div>
    """


def build():
    if os.path.isdir(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(os.path.join(DIST_DIR, "posts"), exist_ok=True)

    md_files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".md"))
    if not md_files:
        raise SystemExit("No .md files found in posts/ — nothing to build.")

    posts = []
    for fname in md_files:
        path = os.path.join(POSTS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        meta, body = parse_frontmatter(raw, fname)
        meta["slug"] = meta.get("slug") or slugify(meta["title"])
        meta["body_html"] = markdown_to_html(body)
        posts.append(meta)

    posts.sort(key=lambda m: m["_date_obj"], reverse=True)

    # ---- individual post pages ----
    for meta in posts:
        tag_list = [t.strip() for t in meta["tags"].split(",") if t.strip()]
        tags_html = ""
        if tag_list:
            links = "".join(f'<a href="../index.html">#{html.escape(t)}</a>' for t in tag_list)
            tags_html = f'<div class="tags-row">{links}</div>'

        page = HEAD.format(
            title=f"{meta['title']} &middot; {SITE_TITLE}",
            description=html.escape(meta["snippet"]),
            css=CSS,
            site_title=SITE_TITLE,
            site_tagline=SITE_TAGLINE,
            home_href="../index.html",
        )
        page += f"""
    <article class="post-full">
      <a class="back-link u-link" href="../index.html">&#8592; back to index</a>
      <p class="post-meta"><time>{fmt_date_human(meta['_date_obj'])}</time></p>
      <h1 class="post-title">{html.escape(meta['title'])}</h1>
      <div class="post-body">
        {meta['body_html']}
      </div>
      {tags_html}
    </article>
        """
        page += FOOT.format(site_title=SITE_TITLE, script=SCRIPT, social_links=render_social_links())

        out_path = os.path.join(DIST_DIR, "posts", f"{meta['slug']}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)

    # ---- homepage ----
    index = HEAD.format(
        title=f"{SITE_TITLE} &middot; {SITE_TAGLINE}",
        description=f"{SITE_TITLE} — {SITE_TAGLINE}",
        css=CSS,
        site_title=SITE_TITLE,
        site_tagline=SITE_TAGLINE,
        home_href="index.html",
    )
    index += '<p class="section-label">Latest</p>'

    if posts:
        lead = posts[0]
        side = posts[1:4]
        index += '<div class="featured-wrap" style="display:grid;">'
        index += f"""
        <div class="featured reveal" style="display:grid;grid-template-columns:1.3fr 1fr;gap:36px;padding:32px 0;border-bottom:1px solid var(--rule);align-items:start;">
          <div>
            <p class="post-meta"><time>{fmt_date_human(lead['_date_obj'])}</time></p>
            <h2 class="post-title">
              <a href="posts/{lead['slug']}.html">{html.escape(lead['title'])}</a>
            </h2>
            <p class="post-snippet">{html.escape(lead['snippet'])}</p>
            <a class="read-more" href="posts/{lead['slug']}.html">read <span class="arrow">&#8594;</span></a>
          </div>
          <div class="featured-side">
            {''.join(render_side_item(m, f"posts/{m['slug']}.html") for m in side)}
          </div>
        </div>
        """
        index += '</div>'

        rest = posts[4:]
        if rest:
            index += '<div class="blog-posts">'
            for m in rest:
                index += render_post_card(m, f"posts/{m['slug']}.html")
            index += '</div>'

    index += FOOT.format(site_title=SITE_TITLE, script=SCRIPT, social_links=render_social_links())
    with open(os.path.join(DIST_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)

    print(f"Built {len(posts)} post(s) into {DIST_DIR}/")


if __name__ == "__main__":
    build()
