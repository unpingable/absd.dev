#!/usr/bin/env python3
"""Check the built site (site/) before anyone publishes it.

    python3 scripts/check.py [--screenshots DIR]

Checks: internal links and fragments; basic accessibility (lang, unique
titles, one h1, heading order, alt text, landmarks, colour contrast of the
theme tokens in light and dark); responsive basics (viewport meta, no fixed
widths); both colour schemes define every token; canonical and og:url
metadata; no private paths, hosts, repository names, e-mail addresses, or
internal vocabulary; the source-release values in content/release.json are all filled
and well formed, and statements the source release made false are gone. With --screenshots, renders every page at 360, 768,
and 1280 px wide in both colour schemes with a local headless Chromium and
fails if a page scrolls horizontally.

Exit status 0 only when every check passes.
"""

import argparse
import html
import hashlib
import html.parser
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BASE = "https://absd.dev"

failures = []


def fail(page, message):
    failures.append(f"{page}: {message}")


class Page(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ""
        self.in_title = False
        self.headings = []
        self.ids = set()
        self.links = []
        self.imgs_without_alt = 0
        self.tags = set()
        self.roles = set()
        self.meta = {}
        self.canonical = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.add(tag)
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "title":
            self.in_title = True
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if "id" in a:
            if a["id"] in self.ids:
                self.links.append(("dup-id", a["id"]))
            self.ids.add(a["id"])
        if "role" in a:
            self.roles.add(a["role"])
        for attr in ("href", "src"):
            if attr in a and a[attr] is not None:
                self.links.append((attr, a[attr]))
        if tag == "img" and not a.get("alt"):
            self.imgs_without_alt += 1
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        self.text.append(data)


def url_of(path):
    rel = path.relative_to(SITE).parent.as_posix()
    return "/" if rel == "." else f"/{rel}/"


def resolve(url):
    path = SITE / url.lstrip("/")
    if url.endswith("/") or path.is_dir():
        path = path / "index.html"
    return path


def parse_all():
    pages = {}
    for path in sorted(SITE.rglob("index.html")):
        p = Page()
        p.feed(path.read_text(encoding="utf-8"))
        pages[url_of(path)] = p
    return pages


def check_links(pages):
    for url, p in pages.items():
        for kind, target in p.links:
            if kind == "dup-id":
                fail(url, f"duplicate id {target}")
                continue
            parsed = urllib.parse.urlparse(target)
            if parsed.scheme in ("http", "https", "mailto"):
                if parsed.scheme == "http":
                    fail(url, f"insecure link {target}")
                continue
            if parsed.scheme:
                fail(url, f"unexpected link scheme {target}")
                continue
            dest = urllib.parse.urljoin(url, parsed.path) if parsed.path else url
            if not dest.startswith("/"):
                fail(url, f"unresolvable link {target}")
                continue
            file = resolve(dest)
            if not file.exists():
                fail(url, f"broken link {target}")
                continue
            if parsed.fragment:
                if file.name == "index.html":
                    target_page = pages.get(url_of(file))
                    if target_page is None or parsed.fragment not in target_page.ids:
                        fail(url, f"missing fragment {target}")


def check_a11y_and_meta(pages):
    titles = {}
    for url, p in pages.items():
        if p.lang != "en":
            fail(url, "html lang is not 'en'")
        if not p.title.strip():
            fail(url, "empty <title>")
        titles.setdefault(p.title.strip(), []).append(url)
        if p.headings.count(1) != 1:
            fail(url, f"{p.headings.count(1)} h1 elements")
        if p.headings and p.headings[0] != 1:
            fail(url, "first heading is not h1")
        for prev, cur in zip(p.headings, p.headings[1:]):
            if cur > prev + 1:
                fail(url, f"heading level jumps from h{prev} to h{cur}")
        if p.imgs_without_alt:
            fail(url, f"{p.imgs_without_alt} img without alt")
        for tag in ("header", "nav", "main", "footer"):
            if tag not in p.tags:
                fail(url, f"no <{tag}> landmark")
        for role in ("banner", "main", "contentinfo"):
            if role not in p.roles:
                fail(url, f"no role={role}")
        if "viewport" not in p.meta or "width=device-width" not in p.meta["viewport"]:
            fail(url, "no responsive viewport meta")
        if not p.meta.get("description"):
            fail(url, "no meta description")
        if p.canonical != BASE + url:
            fail(url, f"canonical is {p.canonical}, want {BASE + url}")
        if p.meta.get("og:url") != BASE + url:
            fail(url, "og:url does not match canonical")
    for title, urls in titles.items():
        if len(urls) > 1:
            fail(",".join(urls), f"duplicate title {title!r}")


def tokens(css):
    light = re.search(r":root\s*\{(.*?)\n\}", css, re.S).group(1)
    dark_block = re.search(r"prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\}", css, re.S)
    if not dark_block:
        return None, None
    parse = lambda s: dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", s))
    return parse(light), parse(dark_block.group(1))


def luminance(hexcolor):
    rgb = [int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check_css():
    css = (SITE / "style.css").read_text()
    light, dark = tokens(css)
    if dark is None:
        fail("style.css", "no prefers-color-scheme: dark block")
        return
    missing = sorted(set(light) - set(dark))
    if missing:
        fail("style.css", f"dark scheme does not redefine {missing}")
    text_tokens = ["--fg", "--fg-muted", "--accent", "--accent-hover", "--l-mq", "--l-cq",
                   "--l-exp", "--l-planned", "--l-unsupported"]
    for scheme, t in (("light", light), ("dark", dark)):
        for fg in text_tokens:
            for bg in ("--bg", "--bg-inset"):
                ratio = contrast(t[fg], t[bg])
                if ratio < 4.5:
                    fail("style.css", f"{scheme}: {fg} on {bg} contrast {ratio:.2f} < 4.5")
    if not re.search(r"body\s*\{[^}]*background:\s*var\(--bg\)", css):
        fail("style.css", "body has no explicit background")
    for m in re.finditer(r"(?<![-\w])(width|min-width):\s*(\d+)px", css):
        if int(m.group(2)) > 320:
            fail("style.css", f"fixed {m.group(1)} {m.group(2)}px")


PRIVATE = [
    (r"/home/(?!operator\b)[a-z]", "private path"),
    (r"[\w.+-]+@[A-Za-z][\w-]*(\.[\w-]+)*\.[A-Za-z]{2,}", "e-mail address"),
    (r"(?i)revolutionary|secure by design|formally verified|next-generation|AI-native", "promotional wording"),
    (r"(?i)BEGIN [A-Z ]*PRIVATE KEY|ssh-ed25519 AAAA[0-9A-Za-z+/]{20,}", "key material"),
]
# Names that must not appear but are themselves private (hosts, repositories,
# paths) live in an untracked file, one "regex<TAB>description" per line.
LOCAL_PATTERNS = ROOT / "scripts" / "private-patterns.local"
if LOCAL_PATTERNS.exists():
    for line in LOCAL_PATTERNS.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            regex, _, what = line.partition("\t")
            PRIVATE.append((regex, what or "private name"))


def check_leaks():
    roots = [SITE]
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_dir() or path.suffix not in (".html", ".css", ".svg", ".txt", ".xml"):
                continue
            text = path.read_text(encoding="utf-8")
            where = str(path.relative_to(ROOT))
            for pattern, what in PRIVATE:
                for m in re.finditer(pattern, text):
                    fail(where, f"{what}: {m.group(0)!r}")
            if "Constellation" in text and not re.match(r"site/(research|status)/", where):
                fail(where, "names Constellation outside /research/ and /status/")


def check_constellation_status():
    text = (SITE / "status" / "index.html").read_text()
    lines = [l for l in text.splitlines() if "Constellation" in l]
    if len(lines) > 1:
        fail("/status/", f"Constellation named on {len(lines)} lines (at most one)")


def check_withheld():
    """Statements the evidence does not support must not appear."""
    all_text = " ".join((p.read_text() for p in SITE.rglob("*.html")))
    for phrase in ("x86-64 PCs supported", "qualified x86-64 hardware", "runs on real hardware",
                   "/download", "/source/"):
        if phrase in all_text:
            fail("site", f"withheld claim or page present: {phrase!r}")
    # True until the source release; false after it.
    for phrase in ("developed privately", "no public source", "is not public", "No license has been chosen",
                   "contributions are not being accepted", "in private sources"):
        if phrase.lower() in all_text.lower():
            fail("site", f"statement the source release made false: {phrase!r}")
    if "Physical hardware qualification: not yet established" not in (SITE / "status" / "index.html").read_text():
        fail("/status/", "missing the physical hardware statement")
    if "Physical hardware qualification: not yet established" not in (SITE / "hardware" / "index.html").read_text():
        fail("/hardware/", "missing the physical hardware statement")


def check_source_release():
    """The release record in content/release.json must be filled before the site can be
    staged, and nothing unfilled may have reached a page."""
    sys.path.insert(0, str(ROOT))
    import build
    stamp = SITE / "release-source.sha256"
    expected_stamp = hashlib.sha256(build.RELEASE_PATH.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip() != expected_stamp:
        fail("content/release.json", "built release metadata is stale; run python3 build.py")
    values = build.source_values()
    for template in sorted((ROOT / "src/pages").rglob("index.html")):
        output = SITE / template.relative_to(ROOT / "src/pages")
        rendered = output.read_text()
        for line in template.read_text().splitlines():
            if "{{SOURCE_" not in line:
                continue
            expected = line
            for name, value in values.items():
                expected = expected.replace("{{" + name + "}}", value)
            chunks = re.split(r"\{\{[A-Z_]+\}\}", expected)
            if any(chunk not in rendered for chunk in chunks if chunk.strip()):
                fail(str(output.relative_to(ROOT)), "source-release snippet differs from record/template")
    hex40 = r"[0-9a-f]{40}"
    fields = [("SOURCE_RELEASE_ID", r"[A-Za-z0-9][A-Za-z0-9._-]*"),
              ("SOURCE_RELEASE_COMMIT", hex40),
              ("SOURCE_KERNEL_COMMIT", hex40),
              ("SOURCE_PLATFORM_COMMIT", hex40),
              ("SOURCE_RELEASE_DATE", r"20\d\d-[01]\d-[0-3]\d")]
    if build.SOURCE_QUALIFICATION == "qualified":
        fields += [(name, r".*\S.*") for name in (
            "SOURCE_KERNEL_SUITE_RESULT", "SOURCE_CORE_PROFILE_RESULT", "SOURCE_QUALIFICATION_RECORD")]
    for name, pattern in fields:
        value = getattr(build, name)
        if value == build.UNFILLED:
            fail("build.py", f"{name} is unfilled")
        elif not re.fullmatch(pattern, value):
            fail("build.py", f"{name} is malformed: {value!r}")
    if build.SOURCE_QUALIFICATION == build.UNFILLED:
        fail("build.py", "SOURCE_QUALIFICATION is unfilled")
    elif build.SOURCE_QUALIFICATION not in build.SOURCE_STATEMENTS:
        fail("build.py", f"SOURCE_QUALIFICATION must be one of {sorted(build.SOURCE_STATEMENTS)}")
    if re.search(r"(?i)staging", build.SOURCE_RELEASE_ID):
        fail("build.py", "SOURCE_RELEASE_ID names a staging assembly, not a release")
    for path in sorted(SITE.rglob("*")):
        if path.is_file() and path.suffix in (".html", ".txt", ".xml"):
            count = path.read_text(encoding="utf-8").count(build.UNFILLED)
            if count:
                fail(str(path.relative_to(ROOT)), f"{count} unfilled source-release value(s)")
    status = (SITE / "status" / "index.html").read_text()
    needed = ['id="source"', "Byte-identical builds on different machines: not claimed"]
    if build.SOURCE_QUALIFICATION in build.SOURCE_STATEMENTS:
        needed.append(html.escape(build.SOURCE_STATEMENTS[build.SOURCE_QUALIFICATION][2]))
    for text in needed:
        if text not in status:
            fail("/status/", f"missing source-release statement: {text!r}")


def browser():
    # A snap-packaged Chromium writes screenshots into its private /tmp,
    # so prefer a browser installed outside snap.
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found and not os.path.realpath(found).startswith("/snap/"):
            return found
    return None


def chrome(exe, profile, width, height, extra):
    return [exe, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--allow-file-access-from-files", f"--user-data-dir={profile}",
            f"--window-size={width},{height}"] + extra


def relativize(root):
    """Rewrite root-absolute links in a copy of the site so it works from
    file:// (headless Chrome here takes ~25 s to start loading any http URL,
    and loads files at once)."""
    for path in root.rglob("*.html"):
        depth = len(path.relative_to(root).parts) - 1
        up = "../" * depth or "./"

        def fix(m):
            target = m.group(2)
            if target.startswith("//"):
                return m.group(0)
            rel = up + target.lstrip("/")
            if rel.endswith("/"):
                rel += "index.html"
            elif "#" in rel and rel.split("#")[0].endswith("/"):
                base, frag = rel.split("#", 1)
                rel = base + "index.html#" + frag
            return f'{m.group(1)}="{rel}"'

        text = re.sub(r'(href|src)="(/[^"]*)"', fix, path.read_text(encoding="utf-8"))
        path.write_text(text, encoding="utf-8")


def screenshots(pages, out):
    exe = browser()
    if not exe:
        print("check: no local Chrome outside snap; screenshots and overflow probe skipped")
        return
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "site"
        shutil.copytree(SITE, root)
        relativize(root)
        files = {u: (root / u.lstrip("/") / "index.html").as_uri() for u in pages}
        # Loads each page in an iframe of each width and records how far the
        # document is wider than the frame.
        (root / "__probe.html").write_text("""<!DOCTYPE html><html><body><pre id="out"></pre><script>
const pages = %s, widths = [360, 768, 1280];
const out = document.getElementById('out');
(async () => {
  for (const [u, file] of pages) for (const w of widths) {
    const f = document.createElement('iframe');
    f.style.width = w + 'px'; f.style.height = '900px'; f.style.border = '0';
    await new Promise(r => { f.onload = r; f.src = file; document.body.appendChild(f); });
    const d = f.contentDocument.documentElement;
    out.textContent += 'OVERFLOW ' + u + ' ' + w + ' ' + (d.scrollWidth - d.clientWidth) + '\\n';
    f.remove();
  }
  out.textContent += 'PROBE DONE\\n';
})();
</script></body></html>""" % json.dumps(sorted(files.items())))
        with tempfile.TemporaryDirectory() as profile:
            r = subprocess.run(chrome(exe, profile, 1400, 900, ["--virtual-time-budget=120000", "--dump-dom",
                                                               (root / "__probe.html").as_uri()]),
                               capture_output=True, text=True, timeout=300)
        results = re.findall(r"OVERFLOW (\S+) (\d+) (-?\d+)$", r.stdout, re.M)
        if "PROBE DONE" not in r.stdout or len(results) != 3 * len(pages):
            fail("overflow", f"probe returned {len(results)} of {3 * len(pages)} results")
        for url, width, extra in results:
            if int(extra) > 0:
                fail(url, f"scrolls horizontally by {extra}px at {width}px")
        # Headless Chrome will not make a window narrower than about 500 px,
        # so each page is shot inside an iframe of the exact width, then
        # cropped to it when Pillow is present.
        (root / "__frame.html").write_text(
            '<!DOCTYPE html><html><body style="margin:0"><iframe id="f" style="border:0;height:1400px">'
            '</iframe><script>const q=new URLSearchParams(location.search);const f=document.getElementById("f");'
            'f.style.width=q.get("w")+"px";f.src=q.get("u");</script></body></html>')
        try:
            from PIL import Image
        except ImportError:
            Image = None
        shots = [u for u in pages if not u.startswith("/man/")] + ["/man/afterboot.8/"]
        for url in shots:
            for width in (360, 768, 1280):
                for scheme, value in (("light", 1), ("dark", 0)):
                    name = (url.strip("/").replace("/", "_") or "home") + f"-{width}-{scheme}.png"
                    query = urllib.parse.urlencode({"w": width, "u": files[url]})
                    with tempfile.TemporaryDirectory() as profile:
                        r = subprocess.run(chrome(exe, profile, max(width, 800), 1400, [
                            f"--blink-settings=preferredColorScheme={value}", "--virtual-time-budget=3000",
                            f"--screenshot={out / name}", (root / "__frame.html").as_uri() + "?" + query]),
                            capture_output=True, text=True, timeout=60)
                    if not (out / name).exists():
                        fail(url, f"screenshot {name} failed: {r.stderr.strip()[-200:]}")
                    elif Image is not None and width < 800:
                        with Image.open(out / name) as im:
                            im.crop((0, 0, width, im.height)).save(out / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=pathlib.Path)
    args = parser.parse_args()
    if not SITE.exists():
        print("check: site/ does not exist; run python3 build.py", file=sys.stderr)
        return 1
    pages = parse_all()
    check_links(pages)
    check_a11y_and_meta(pages)
    check_css()
    check_leaks()
    check_constellation_status()
    check_withheld()
    check_source_release()
    if args.screenshots:
        screenshots(pages, args.screenshots)
    for f in failures:
        print(f"FAIL {f}")
    print(f"check: {len(pages)} pages, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
