#!/usr/bin/env python3
"""Build the absd.dev static site into site/.

    python3 build.py

Inputs:
  src/pages/**/index.html   page bodies, with a metadata comment on top
  src/static/               copied as is
  man/NAME.S                mdoc sources, rendered with groff at build time
  captures/                 recorded transcripts, inserted verbatim

Nothing is fetched. The only external program is groff (GNU groff 1.23.0,
the version the ABSD image build pins), run with the same arguments the
image build uses, so /man/ shows the bytes an ABSD session prints.
"""

import hashlib
import html
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "site"
BASE = "https://absd.dev"
SITE = "ABSD"

MILESTONE = "milestone/general-usability-qemu-20260927"
MILESTONE_DATE = "2026-09-27"
KERNEL = "1983172"
PLATFORM = "ff025b1"

# ---------------------------------------------------------------------------
# RELEASE SWITCH: the public source release this site describes.
#
# This is the only place these values are set. Every one that still says
# FILL-AT-DEPLOY must be replaced, at deploy time, from the published
# repository's SOURCE-MANIFEST.toml and its release commit. While any is
# unfilled the build still renders (so the pages can be previewed) but
# scripts/check.py fails, and scripts/stage-pages.sh therefore refuses to
# stage the site.
#
# SOURCE_REPO is the canonical public repository. Do not deploy before it
# exists and carries the release named here.
SOURCE_REPO = "https://github.com/unpingable/absd"
SOURCE_LICENCE = "Apache-2.0"
UNFILLED = "FILL-AT-DEPLOY"
SOURCE_RELEASE_ID = "absd-preview-20261010"        # [release] id in the manifest; also the tag name
SOURCE_RELEASE_COMMIT = "6ed4934ae9baf210b5514c931f0dd9343f74277d"    # 40 hex: the release commit on the public main
SOURCE_KERNEL_COMMIT = "260b4a20755a70db2ec8aa4556b9c576285fe284"     # 40 hex: [[component]] kernel, commit
SOURCE_PLATFORM_COMMIT = "65cf80f9440f8bba018f5993aa70744e4e0d5b64"   # 40 hex: [[component]] platform, commit
SOURCE_RELEASE_DATE = "2026-10-10"      # YYYY-MM-DD: [release] date
# Which of the two prepared statements below is true of that release:
#   "preview"    the release commit itself was built, booted and smoke-tested
#                from a clean clone, and neither suite has run on it;
#   "qualified"  the kernel suite and the platform gate's core profile have
#                both passed on it. Needs the three fill-ins that follow.
SOURCE_QUALIFICATION = "preview"
# Used only by "qualified". Take them from the runs' own output; never
# estimate them.
SOURCE_KERNEL_SUITE_RESULT = UNFILLED   # e.g. the suite's own last line
SOURCE_CORE_PROFILE_RESULT = UNFILLED   # the gate's last line, with extended=NOT_RUN
SOURCE_QUALIFICATION_RECORD = UNFILLED  # date of the runs and where the receipt is

# The two wordings. "preview" names a date: once the seven-day observation
# has ended (2026-10-17) and the suites have run, switch to "qualified"
# rather than leaving "scheduled after" on the site.
SOURCE_STATEMENTS = {
    "preview": (
        "l-exp", "EXPERIMENTAL-INTEGRATION",
        "Preview: built, booted and smoke-tested from a clean clone; the qualification suites "
        "have not yet been run on these revisions and are scheduled after 2026-10-17.",
        "From a fresh clone in a stock Ubuntu 24.04 container, the release fetched its dependencies, "
        "built the kernel, the platform and the operator image offline, booted under QEMU's software "
        "emulation and served an SSH session. Neither the kernel suite nor the platform gate has been "
        "run on these exact revisions; both are scheduled for after the seven-day observation ends on "
        "2026-10-17. Until then nothing on this site labelled qualified or validated is a statement "
        "about the source release."),
    "qualified": (
        "l-val", "VALIDATED",
        "The kernel suite and the core profile of the platform gate have passed on these revisions; "
        "the extended integration profile cannot be run from the public tree.",
        "On these exact revisions, built from a clean clone: the kernel suite passed "
        "({SOURCE_KERNEL_SUITE_RESULT}) and the platform gate passed in its core profile "
        "({SOURCE_CORE_PROFILE_RESULT}). Recorded {SOURCE_QUALIFICATION_RECORD}. The extended "
        "integration profile is not part of this statement: it does not run from the public tree, "
        "and its steps print NOT_RUN there. No independent person has examined these "
        "runs."),
}

NAV = [
    ("/status/", "Status"),
    ("/design/", "Design"),
    ("/manual/", "Manual"),
    ("/hardware/", "Hardware"),
    ("/compatibility/", "Compatibility"),
    ("/research/", "Research"),
    ("/evidence/", "Evidence"),
    ("/about/", "About"),
]

SECTIONS = {
    "1": "General commands",
    "4": "Kernel interfaces (drivers)",
    "5": "File formats",
    "7": "Miscellaneous information",
    "8": "System administration",
}

GROFF = ["/usr/bin/groff"]
GROFF_ARGS = ["-mdoc", "-Tascii", "-P-cbou", "-rHY=0", "-dAD=l"]


def fail(message):
    print(f"build: {message}", file=sys.stderr)
    sys.exit(1)


def parse_page(path):
    text = path.read_text(encoding="utf-8")
    meta = {}
    while True:
        m = re.match(r"\s*<!--\s*(\w+):\s*(.*?)\s*-->\n", text)
        if not m:
            break
        meta[m.group(1)] = m.group(2)
        text = text[m.end():]
    for key in ("title", "description"):
        if key not in meta:
            fail(f"{path}: missing {key}")
    return meta, text


def source_values():
    """The {{SOURCE_*}} replacements. An unfilled value renders as a visible
    marker that scripts/check.py refuses."""
    def shown(name):
        value = globals()[name]
        return f"{UNFILLED}:{name}" if value == UNFILLED else value

    names = ["SOURCE_RELEASE_ID", "SOURCE_RELEASE_COMMIT", "SOURCE_KERNEL_COMMIT",
             "SOURCE_PLATFORM_COMMIT", "SOURCE_RELEASE_DATE"]
    values = {name: shown(name) for name in names}
    if SOURCE_QUALIFICATION in SOURCE_STATEMENTS:
        css, label, short, full = SOURCE_STATEMENTS[SOURCE_QUALIFICATION]
        full = full.format(**{n: shown(n) for n in (
            "SOURCE_KERNEL_SUITE_RESULT", "SOURCE_CORE_PROFILE_RESULT", "SOURCE_QUALIFICATION_RECORD")})
    else:
        css, label = "l-exp", "EXPERIMENTAL-INTEGRATION"
        short = full = f"{UNFILLED}:SOURCE_QUALIFICATION"
    values = {k: html.escape(v) for k, v in values.items()}
    values.update({
        "SOURCE_REPO": SOURCE_REPO,
        "SOURCE_LICENCE": SOURCE_LICENCE,
        # Files are linked at the release tag, so a link shows the text this
        # site was checked against.
        "SOURCE_FILE": f"{SOURCE_REPO}/blob/{urllib.parse.quote(shown('SOURCE_RELEASE_ID'), safe='')}",
        "SOURCE_LABEL": f'<span class="label {css}">{label}</span>',
        "SOURCE_QUALIFICATION_SHORT": html.escape(short),
        "SOURCE_QUALIFICATION": html.escape(full),
    })
    return values


def layout(url, title, description, body, h1_in_body=True, unlisted=False):
    source = source_values()
    full_title = f"{SITE}" if url == "/" else f"{title} — {SITE}"
    robots = '\n<meta name="robots" content="noindex">' if unlisted else ""
    nav = []
    for href, label in NAV:
        current = ' aria-current="page"' if url.startswith(href) else ""
        nav.append(f'<li><a href="{href}"{current}>{label}</a></li>')
    nav.append(f'<li><a href="{SOURCE_REPO}">Source</a></li>')
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{BASE}{url}">{robots}
<meta name="color-scheme" content="light dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE}">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{BASE}{url}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site" role="banner">
<a class="wordmark" href="/">ABSD</a>
<nav aria-label="Site"><ul>{"".join(nav)}</ul></nav>
</header>
<main id="main" role="main">
{body.strip()}
</main>
<footer class="site" role="contentinfo">
<p>ABSD is an experimental operating system by James Beck, <a href="/about/#how">built largely by AI coding agents</a> under the author's direction and not independently audited. Its <a href="{SOURCE_REPO}">source</a> is public under {SOURCE_LICENCE} (source release <code>{source["SOURCE_RELEASE_ID"]}</code>, <a href="/status/#source">what that does and does not establish</a>); it runs under QEMU only, and no physical hardware is supported. <a href="https://github.com/unpingable/absd.dev">This site's source</a> is separate.</p>
<p>Facts on this site are stated as of <a href="/evidence/">{MILESTONE}</a> (kernel {KERNEL}, platform {PLATFORM}) unless labelled otherwise. Those revisions are earlier than the source release. <a href="/status/#labels">How statements are labelled</a>.</p>
</footer>
</body>
</html>
"""


def check_man_sources():
    sums = {}
    for line in (ROOT / "man" / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest
    pages = sorted(p for p in (ROOT / "man").iterdir() if re.fullmatch(r"[a-z0-9.-]+\.[1-9]", p.name))
    if sorted(sums) != [p.name for p in pages]:
        fail("man/SHA256SUMS does not list exactly the pages in man/")
    for p in pages:
        if hashlib.sha256(p.read_bytes()).hexdigest() != sums[p.name]:
            fail(f"man/{p.name} differs from man/SHA256SUMS (edit the source upstream, not here)")
    return pages


def groff_version():
    out = subprocess.run(GROFF + ["--version"], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=True).stdout
    return out.splitlines()[0]


def render_man(source):
    result = subprocess.run(GROFF + GROFF_ARGS + [str(source)], capture_output=True,
                            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False)
    if result.returncode != 0 or result.stderr:
        fail(f"groff failed on {source.name}: {result.stderr.decode(errors='replace')}")
    text = result.stdout.decode("ascii")
    if re.search(r"[^\x20-\x7e\n]", text):
        fail(f"{source.name}: rendered page has bytes other than printable ASCII")
    return text


def description_of(source):
    m = re.search(r"^\.Nd\s+(.*)$", source.read_text(), re.M)
    if not m:
        fail(f"{source.name}: no .Nd")
    return m.group(1).strip()


def man_html(text, known):
    """Escape the rendered page; link cross-references to pages that exist;
    give section headings anchors. The words are groff's, unchanged."""
    lines = []
    for line in html.escape(text, quote=False).split("\n"):
        if re.fullmatch(r"[A-Z][A-Z ]*[A-Z]", line):
            anchor = line.lower().replace(" ", "-")
            lines.append(f'<span class="sh" id="{anchor}">{line}</span>')
            continue

        def link(m):
            name, sec = m.group(1), m.group(2)
            if (name, sec) in known:
                return f'<a href="/man/{name}.{sec}/">{name}({sec})</a>'
            return m.group(0)

        lines.append(re.sub(r"\b([a-z][a-z0-9.-]*)\(([1-9])\)", link, line))
    return "\n".join(lines).rstrip() + "\n"


def build_manual(version):
    sources = check_man_sources()
    known = {(p.stem, p.suffix[1:]) for p in sources}
    entries = []
    for source in sources:
        name, sec = source.stem, source.suffix[1:]
        desc = description_of(source)
        entries.append((sec, name, desc))
        rendered = render_man(source)
        url = f"/man/{name}.{sec}/"
        body = f"""<article class="manpage">
<h1>{name}({sec})</h1>
<p class="provenance"><span class="label l-mq">MILESTONE-QUALIFIED</span>
Rendered from the page's mdoc source at <code>{MILESTONE}</code> (platform {PLATFORM})
with {html.escape(version)}, using the same command the image build uses; an ABSD session running
<code>man {sec} {name}</code> prints this text. It is dated {MILESTONE_DATE} and is the milestone's page, not the
<a href="/status/#source">source release</a>'s: the release carries a later manual under <code>platform/man/</code>, and
the build commands and repository files this page mentions are the milestone's. To build, follow the
<a href="{SOURCE_REPO}#readme">repository's README</a>. <a href="/status/#since">Later work</a> is not in this page.
<a href="/manual/">All pages</a>.</p>
<pre class="man" tabindex="0" aria-label="{name}({sec}) manual page">{man_html(rendered, known)}</pre>
<p class="note"><a href="/manual/">All manual pages</a></p>
</article>"""
        write(url, layout(url, f"{name}({sec})", f"{name}({sec}): {desc}. ABSD manual page.", body))
    rows = []
    for sec in sorted(SECTIONS):
        items = [e for e in sorted(entries) if e[0] == sec]
        if not items:
            continue
        rows.append(f'<h2 id="section-{sec}">Section {sec}: {SECTIONS[sec]}</h2>\n<dl class="manindex">')
        for _, name, desc in items:
            rows.append(f'<dt><a href="/man/{name}.{sec}/">{name}({sec})</a></dt><dd>{html.escape(desc)}</dd>')
        rows.append("</dl>")
    unknown = sorted({e[0] for e in entries} - set(SECTIONS))
    if unknown:
        fail(f"no section title for {unknown}")
    return "\n".join(rows), len(entries)


def write(url, content):
    path = OUT / url.lstrip("/") / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for item in (SRC / "static").iterdir():
        shutil.copy2(item, OUT / item.name)

    version = groff_version()
    if version != "GNU groff version 1.23.0":
        fail(f"unexpected groff: {version} (the image build pins 1.23.0)")
    manindex, count = build_manual(version)

    transcript = (ROOT / "captures" / "operator-session.txt").read_text(encoding="utf-8")
    replacements = {
        "{{MANINDEX}}": manindex,
        "{{MANCOUNT}}": str(count),
        "{{TRANSCRIPT}}": html.escape(transcript.rstrip("\n"), quote=False),
        "{{MILESTONE}}": MILESTONE,
        "{{MILESTONE_DATE}}": MILESTONE_DATE,
        "{{KERNEL}}": KERNEL,
        "{{PLATFORM}}": PLATFORM,
        "{{GROFF}}": html.escape(version),
    }
    replacements.update({"{{" + k + "}}": v for k, v in source_values().items()})
    pages = 0
    hidden = set()
    for page in sorted((SRC / "pages").rglob("index.html")):
        rel = page.parent.relative_to(SRC / "pages")
        url = "/" if str(rel) == "." else f"/{rel.as_posix()}/"
        meta, body = parse_page(page)
        for key, value in replacements.items():
            body = body.replace(key, value)
        leftover = re.search(r"\{\{[A-Z_]+\}\}", body)
        if leftover:
            fail(f"{page}: unknown placeholder {leftover.group(0)}")
        unlisted = meta.get("unlisted") == "yes"
        if unlisted:
            hidden.add(url)
        write(url, layout(url, meta["title"], meta["description"], body, unlisted=unlisted))
        pages += 1
    # GitHub Pages serves /404.html for any path that does not exist.
    not_found = """<h1>Page not found</h1>
<p>There is no page at this address. The site is small; everything is one step from here:</p>
<ul>
<li><a href="/">Home</a></li>
<li><a href="/status/">Status</a>: what works and what has been qualified</li>
<li><a href="/manual/">Manual</a>: the operator's manual pages</li>
<li><a href="/about/">About</a>: what ABSD is and how to follow it</li>
<li><a href="/status/#source">Source</a>: where the source is and what can be run</li>
</ul>"""
    # /man/ is the natural parent of every manual page URL; the index is /manual/.
    write("/man/", layout("/man/", "Manual pages", "ABSD manual pages: the index is at /manual/.",
                          '<h1>Manual pages</h1>\n<p>The index of manual pages is the <a href="/manual/">manual</a>.</p>',
                          unlisted=True))
    hidden.add("/man/")
    (OUT / "404.html").write_text(
        layout("/404.html", "Page not found", "No page at this address on absd.dev.", not_found, unlisted=True),
        encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    urls = sorted(str(p.parent.relative_to(OUT)) for p in OUT.rglob("index.html"))
    # Unlisted pages are built and reachable by URL, but carry noindex and
    # stay out of the sitemap until a listed page links to them.
    urls = [u for u in urls if ("/" if u == "." else f"/{u}/") not in hidden]
    sitemap = "".join(f"<url><loc>{BASE}/{'' if u == '.' else u + '/'}</loc></url>\n" for u in urls)
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + sitemap + "</urlset>\n")
    print(f"build: {pages} pages, {count} manual pages -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
