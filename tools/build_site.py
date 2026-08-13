"""Build the single-page course site from the markdown docs.

Run:  python tools/build_site.py
Out:  site/course.html   (self-contained, no external requests)

Kept in the repo so the published page can be regenerated from the docs rather
than hand-maintained in two places.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = ROOT / "site" / "course.html"

# (source file, section id, rail label, eyebrow)
SECTIONS = [
    (ROOT / "README.md", "overview", "Overview", "Start here"),
    (DOCS / "00-curriculum.md", "mod-00", "How to study", "Module 00"),
    (DOCS / "01-pytest-foundations.md", "mod-01", "pytest foundations", "Module 01 · Week 1"),
    (DOCS / "02-architecture.md", "mod-02", "Architecture", "Module 02 · Week 2"),
    (DOCS / "03-services.md", "mod-03", "Services / API", "Module 03 · Week 3"),
    (DOCS / "04-web.md", "mod-04", "Web UI", "Module 04 · Week 4"),
    (DOCS / "05-mobile.md", "mod-05", "Mobile", "Module 05 · Week 5"),
    (DOCS / "06-test-data.md", "mod-06", "Test data", "Module 06 · Week 6"),
    (DOCS / "07-ci-reporting.md", "mod-07", "CI & reporting", "Module 07 · Week 7"),
    (DOCS / "08-flakiness.md", "mod-08", "Flakiness", "Module 08 · Week 6"),
    (DOCS / "09-strategy.md", "mod-09", "Strategy & metrics", "Module 09 · Week 8"),
    (DOCS / "10-exercises.md", "mod-10", "Exercises", "Module 10 · Throughout"),
    (DOCS / "cheatsheet.md", "cheatsheet", "Cheat sheet", "Reference"),
]

MODULE_ID = {"00": "mod-00", "01": "mod-01", "02": "mod-02", "03": "mod-03", "04": "mod-04",
             "05": "mod-05", "06": "mod-06", "07": "mod-07", "08": "mod-08", "09": "mod-09",
             "10": "mod-10"}


def rewrite_links(text: str) -> str:
    """Turn repo-relative markdown links into in-page anchors or inline code.

    The published page is standalone, so a link to `../framework/config.py` has
    nowhere to go. Rendering it as code keeps the pointer meaningful without
    producing a dead link.
    """
    # 1. Cross-module links -> in-page anchors.
    text = re.sub(
        r"\[([^\]]*)\]\((?:\.\./)?(?:docs/)?(\d{2})-[a-z0-9-]+\.md(?:#[a-z0-9-]+)?\)",
        lambda m: f"[{m.group(1)}](#{MODULE_ID[m.group(2)]})",
        text,
    )
    # 2. Cheat sheet.
    text = re.sub(
        r"\[([^\]]*)\]\((?:\.\./)?(?:docs/)?cheatsheet\.md\)", r"[\1](#cheatsheet)", text
    )
    # 3. Repo files referenced from docs/ (../path) -> inline code.
    text = re.sub(r"\[[^\]]*\]\(\.\./([^)#]+)\)", r"`\1`", text)
    # 4. Repo files referenced from the README (bare relative path) -> inline code.
    text = re.sub(
        r"\[[^\]]*\]\(((?!https?://|#)[A-Za-z0-9_][A-Za-z0-9_./-]*\.[a-z]{2,5})\)", r"`\1`", text
    )
    return text


def convert(path: Path) -> tuple[str, str]:
    """Return (title, body_html). The H1 is lifted out to become the section head."""
    raw = path.read_text(encoding="utf-8")
    raw = rewrite_links(raw)

    lines = raw.splitlines()
    title = ""
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            del lines[i]
            break
    body = "\n".join(lines)

    md = markdown.Markdown(
        extensions=["extra", "codehilite", "sane_lists", "attr_list"],
        extension_configs={"codehilite": {"guess_lang": False, "linenums": False}},
    )
    return title, md.convert(body)


STYLE = """
/* ---------------------------------------------------------------------------
   Palette — cool-slate neutrals, deep teal accent, rust for defect findings.
   Semantic pass/fail/warn are kept separate from the accent on purpose.
   Light is the base; both dark paths redefine only tokens.
   --------------------------------------------------------------------------- */
:root {
  --paper:      #fcfcfd;
  --paper-sunk: #f2f3f6;
  --paper-rail: #f7f8fa;
  --ink:        #14191e;
  --ink-soft:   #4d565f;
  --ink-faint:  #79838d;
  --rule:       #dfe3e9;
  --rule-soft:  #ebeef2;
  --accent:     #0d6a63;
  --accent-소:  #0d6a63;
  --accent-bg:  #e4f1ef;
  --rust:       #9a4a26;
  --rust-bg:    #f8ece5;
  --pass:       #2c6e3f;
  --fail:       #a52a20;
  --warn:       #7d5a06;
  --code-bg:    #f4f6f8;
  --code-ink:   #22303a;
  --shadow:     0 1px 2px rgba(20,25,30,.06), 0 8px 24px -12px rgba(20,25,30,.14);

  /* syntax */
  --t-kw:  #8a3a86;
  --t-str: #1f6b45;
  --t-num: #9a4a26;
  --t-com: #79838d;
  --t-fn:  #1d5c93;
  --t-op:  #4d565f;

  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua",
           "Source Serif 4", Georgia, serif;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "SFMono-Regular", "Cascadia Mono", "JetBrains Mono", Consolas,
          "Liberation Mono", monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper:      #0f1316;
    --paper-sunk: #161c21;
    --paper-rail: #12171b;
    --ink:        #e4e9ed;
    --ink-soft:   #a3aeb7;
    --ink-faint:  #78838d;
    --rule:       #262e35;
    --rule-soft:  #1d242a;
    --accent:     #5bc4b8;
    --accent-bg:  #13312e;
    --rust:       #dd9166;
    --rust-bg:    #2e1d13;
    --pass:       #6cc98a;
    --fail:       #f08d84;
    --warn:       #d9b45e;
    --code-bg:    #151b20;
    --code-ink:   #d3dbe1;
    --shadow:     0 1px 2px rgba(0,0,0,.5), 0 10px 30px -14px rgba(0,0,0,.7);
    --t-kw:  #d79fd3;
    --t-str: #8fd3a8;
    --t-num: #e0a273;
    --t-com: #6f7a83;
    --t-fn:  #86b9e8;
    --t-op:  #a3aeb7;
  }
}

:root[data-theme="dark"] {
  --paper:      #0f1316;
  --paper-sunk: #161c21;
  --paper-rail: #12171b;
  --ink:        #e4e9ed;
  --ink-soft:   #a3aeb7;
  --ink-faint:  #78838d;
  --rule:       #262e35;
  --rule-soft:  #1d242a;
  --accent:     #5bc4b8;
  --accent-bg:  #13312e;
  --rust:       #dd9166;
  --rust-bg:    #2e1d13;
  --pass:       #6cc98a;
  --fail:       #f08d84;
  --warn:       #d9b45e;
  --code-bg:    #151b20;
  --code-ink:   #d3dbe1;
  --shadow:     0 1px 2px rgba(0,0,0,.5), 0 10px 30px -14px rgba(0,0,0,.7);
  --t-kw:  #d79fd3;
  --t-str: #8fd3a8;
  --t-num: #e0a273;
  --t-com: #6f7a83;
  --t-fn:  #86b9e8;
  --t-op:  #a3aeb7;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}

.shell { display: grid; grid-template-columns: 268px minmax(0, 1fr); align-items: start; }

/* ---------------- rail ---------------- */
.rail {
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  border-right: 1px solid var(--rule);
  background: var(--paper-rail);
  padding: 28px 20px 40px;
  font-family: var(--sans);
  display: flex; flex-direction: column; gap: 22px;
}
.brand { display: flex; flex-direction: column; gap: 4px; }
.brand b { font-size: 15px; font-weight: 650; letter-spacing: -.01em; }
.brand span { font-size: 12.5px; color: var(--ink-faint); }

.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.stat {
  border: 1px solid var(--rule); border-radius: 7px; padding: 7px 9px;
  background: var(--paper); display: flex; flex-direction: column;
}
.stat b { font-size: 15px; font-variant-numeric: tabular-nums; line-height: 1.2; }
.stat span { font-size: 10.5px; color: var(--ink-faint); text-transform: uppercase; letter-spacing: .07em; }

nav ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
nav a {
  display: grid; grid-template-columns: 26px 1fr; align-items: baseline; gap: 8px;
  padding: 6px 8px; border-radius: 6px; text-decoration: none;
  color: var(--ink-soft); font-size: 13.5px; line-height: 1.35;
  border-left: 2px solid transparent;
}
nav a:hover { background: var(--paper-sunk); color: var(--ink); }
nav a.on { color: var(--accent); background: var(--accent-bg); border-left-color: var(--accent); font-weight: 600; }
nav .n {
  font-size: 11px; font-variant-numeric: tabular-nums; color: var(--ink-faint);
  letter-spacing: .04em;
}
nav a.on .n { color: var(--accent); }
.railnote { font-size: 12px; color: var(--ink-faint); line-height: 1.5; border-top: 1px solid var(--rule); padding-top: 14px; }

.themer {
  align-self: flex-start; font: inherit; font-size: 12px; font-family: var(--sans);
  background: var(--paper); color: var(--ink-soft);
  border: 1px solid var(--rule); border-radius: 6px; padding: 5px 10px; cursor: pointer;
}
.themer:hover { color: var(--ink); border-color: var(--ink-faint); }

/* ---------------- main ---------------- */
main { padding: 0 0 120px; min-width: 0; }
.wrap { max-width: 74ch; margin: 0 auto; padding: 0 40px; }

.masthead { border-bottom: 1px solid var(--rule); padding: 64px 0 40px; margin-bottom: 8px; }
.masthead .kicker {
  font-family: var(--sans); font-size: 11.5px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 14px;
}
.masthead h1 {
  font-size: clamp(34px, 5vw, 52px); line-height: 1.06; letter-spacing: -.02em;
  margin: 0 0 16px; text-wrap: balance; font-weight: 600;
}
.masthead p { margin: 0; color: var(--ink-soft); font-size: 19px; max-width: 60ch; }

section { padding-top: 56px; scroll-margin-top: 12px; }
section + section { border-top: 1px solid var(--rule-soft); }
.eyebrow {
  font-family: var(--sans); font-size: 11px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--ink-faint); margin-bottom: 10px;
}
section > .wrap > h2.sec {
  font-size: clamp(26px, 3.4vw, 34px); line-height: 1.15; letter-spacing: -.018em;
  margin: 0 0 28px; font-weight: 600; text-wrap: balance;
}

h2, h3, h4 { text-wrap: balance; font-weight: 600; letter-spacing: -.012em; }
h2 { font-size: 25px; margin: 44px 0 14px; line-height: 1.25; }
h3 { font-size: 20px; margin: 32px 0 10px; line-height: 1.3; }
h4 { font-size: 17px; margin: 26px 0 8px; font-family: var(--sans); }
p { margin: 0 0 16px; }
ul, ol { margin: 0 0 16px; padding-left: 24px; }
li { margin: 5px 0; }
li > ul, li > ol { margin: 5px 0; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 40px 0; }
strong { font-weight: 650; }

a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { text-decoration-thickness: 2px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }

blockquote {
  margin: 24px 0; padding: 2px 0 2px 20px; border-left: 3px solid var(--accent);
  color: var(--ink-soft); font-size: 18px;
}
blockquote p:last-child { margin-bottom: 0; }

/* ---------------- code ---------------- */
code {
  font-family: var(--mono); font-size: .855em;
  background: var(--code-bg); color: var(--code-ink);
  padding: .12em .38em; border-radius: 4px;
  border: 1px solid var(--rule-soft);
  word-break: break-word;
}
pre {
  margin: 0 0 20px; padding: 15px 17px; overflow-x: auto;
  background: var(--code-bg); border: 1px solid var(--rule); border-radius: 9px;
  line-height: 1.55;
}
pre code {
  background: none; border: 0; padding: 0; font-size: 13.5px;
  color: var(--code-ink); word-break: normal; white-space: pre;
}
.codehilite { margin: 0 0 20px; }
.codehilite pre { margin: 0; }

.codehilite .k, .codehilite .kn, .codehilite .kd, .codehilite .kc, .codehilite .ow { color: var(--t-kw); }
.codehilite .s, .codehilite .s1, .codehilite .s2, .codehilite .sb, .codehilite .sd, .codehilite .se { color: var(--t-str); }
.codehilite .mi, .codehilite .mf, .codehilite .m { color: var(--t-num); }
.codehilite .c, .codehilite .c1, .codehilite .cm, .codehilite .ch { color: var(--t-com); font-style: italic; }
.codehilite .nf, .codehilite .nd, .codehilite .nc { color: var(--t-fn); }
.codehilite .o, .codehilite .p, .codehilite .nb { color: var(--t-op); }
.codehilite .err { color: inherit; background: none; }

/* ---------------- tables ---------------- */
.tablewrap { overflow-x: auto; margin: 0 0 22px; }
table {
  border-collapse: collapse; width: 100%; font-family: var(--sans); font-size: 14px;
  font-variant-numeric: tabular-nums;
}
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--rule-soft); vertical-align: top; }
th {
  font-size: 11px; letter-spacing: .09em; text-transform: uppercase;
  color: var(--ink-faint); font-weight: 600; border-bottom: 1px solid var(--rule);
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
td code, th code { font-size: 12.5px; }

/* ---------------- callouts ---------------- */
.findings th:first-child { width: 34%; }
.pill {
  font-family: var(--sans); font-size: 11px; font-weight: 600; letter-spacing: .04em;
  padding: 2px 8px; border-radius: 999px; white-space: nowrap;
  border: 1px solid currentColor;
}
.pill.pass { color: var(--pass); }
.pill.fail { color: var(--fail); }
.pill.warn { color: var(--warn); }

@media (max-width: 1000px) {
  .shell { grid-template-columns: 1fr; }
  .rail {
    position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--rule);
    flex-direction: column;
  }
  nav ol { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 2px; }
  .wrap { padding: 0 22px; }
  body { font-size: 16.5px; }
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
html { scroll-behavior: smooth; }
"""

SCRIPT = """
(function () {
  var root = document.documentElement;
  var btn = document.getElementById('themer');
  function label() {
    var t = root.getAttribute('data-theme');
    btn.textContent = t === 'dark' ? 'Light theme' : 'Dark theme';
  }
  function current() {
    var t = root.getAttribute('data-theme');
    if (t) return t;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  btn.addEventListener('click', function () {
    root.setAttribute('data-theme', current() === 'dark' ? 'light' : 'dark');
    label();
  });
  label();

  // Highlight the section currently in view.
  var links = Array.prototype.slice.call(document.querySelectorAll('nav a'));
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
  var obs = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      links.forEach(function (a) { a.classList.remove('on'); });
      var a = byId[e.target.id];
      if (a) { a.classList.add('on'); }
    });
  }, { rootMargin: '-10% 0px -80% 0px', threshold: 0 });
  document.querySelectorAll('section[id]').forEach(function (s) { obs.observe(s); });
})();
"""


def wrap_tables(body: str) -> str:
    """Tables get their own horizontal scroll container so the page never
    scrolls sideways on a phone."""
    return body.replace("<table>", '<div class="tablewrap"><table>').replace(
        "</table>", "</table></div>"
    )


def build() -> Path:
    nav_items = []
    sections = []

    for index, (path, sid, label, eyebrow) in enumerate(SECTIONS):
        title, body = convert(path)
        body = wrap_tables(body)
        if sid == "overview":
            number = "—"
        elif sid == "cheatsheet":
            number = "ref"
        else:
            number = f"{index - 1:02d}"

        nav_items.append(
            f'<li><a href="#{sid}"><span class="n">{number}</span>'
            f"<span>{html.escape(label)}</span></a></li>"
        )

        heading = "" if sid == "overview" else (
            f'<div class="eyebrow">{html.escape(eyebrow)}</div>'
            f'<h2 class="sec">{html.escape(title)}</h2>'
        )
        sections.append(
            f'<section id="{sid}">\n<div class="wrap">\n{heading}\n{body}\n</div>\n</section>'
        )

    page = f"""<title>Test Automation in Python — Web, Mobile &amp; Services</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{STYLE}</style>

<div class="shell">
  <aside class="rail">
    <div class="brand">
      <b>Test Automation in Python</b>
      <span>Web · Mobile · Services — a course and a framework</span>
    </div>

    <div class="stats">
      <div class="stat"><b>170</b><span>tests</span></div>
      <div class="stat"><b>3</b><span>layers</span></div>
      <div class="stat"><b>36s</b><span>on 4 cores</span></div>
      <div class="stat"><b>6</b><span>real defects</span></div>
    </div>

    <nav aria-label="Course modules">
      <ol>
        {"".join(nav_items)}
      </ol>
    </nav>

    <button class="themer" id="themer" type="button">Dark theme</button>

    <p class="railnote">Every example runs against a demo app bundled in the
    repository — no third-party site to go down, no network required.</p>
  </aside>

  <main>
    <header class="masthead">
      <div class="wrap">
        <div class="kicker">Eight weeks · Eleven modules · Thirty exercises</div>
        <h1>Test automation for web, mobile and services</h1>
        <p>A complete course built around a working Python framework — and around
        the six real defects the framework found while it was being written.</p>
      </div>
    </header>

    {"".join(sections)}
  </main>
</div>

<script>{SCRIPT}</script>
"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
