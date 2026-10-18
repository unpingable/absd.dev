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

import datetime
import json
import hashlib
import html
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
import binary_preview
import release_docs

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "site"
BASE = "https://absd.dev"
SITE = "ABSD"

MILESTONE = "milestone/general-usability-qemu-20260927"
MILESTONE_DATE = "2026-09-27"
KERNEL = "1983172"
PLATFORM = "ff025b1"

# Current public source release; historical qualification stays in page bodies.
RELEASE_PATH = ROOT / "content" / "release.json"
UNFILLED = "FILL-AT-DEPLOY"


def load_release(path, check_documentation=True):
    record = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "repository", "licence", "release_id", "release_commit",
                "kernel_commit", "platform_commit", "release_date", "qualification",
                "kernel_suite_result", "core_profile_result", "qualification_record",
                "editorial_updated", "standing", "demonstrated", "limitations", "evidence",
                "preview_summary", "preview_details"}
    # Schema 1 is a source release with no binary preview; schema 2 adds the
    # `binary_preview` object. A record without a binary preview stays schema
    # 1, so its bytes (and release-source.sha256) are unchanged by this field.
    version = record.get("schema_version")
    if type(version) is not int or (version, set(record)) not in ((1, expected), (2, expected | {"binary_preview"})):
        raise ValueError("release record: expected schema version 1 (no binary preview) or 2 (with one) "
                         "and its exact fields")
    if version == 2 and record["binary_preview"] is None:
        raise ValueError("release record: schema 2 requires a binary preview; use schema 1 without one")
    record.setdefault("binary_preview", None)
    for name in expected - {"schema_version", "kernel_suite_result", "core_profile_result", "qualification_record", "demonstrated", "limitations", "evidence"}:
        if not isinstance(record[name], str) or not record[name].strip() or UNFILLED in record[name]:
            raise ValueError(f"release record: missing {name}")
    for name in ("release_commit", "kernel_commit", "platform_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", record[name]):
            raise ValueError(f"release record: malformed {name}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", record["release_id"]) or "staging" in record["release_id"].lower():
        raise ValueError("release record: malformed release_id")
    datetime.date.fromisoformat(record["release_date"])
    datetime.date.fromisoformat(record["editorial_updated"])
    for name in ("demonstrated", "limitations"):
        if not isinstance(record[name], list) or not record[name] or any(not isinstance(v, str) or not v.strip() for v in record[name]):
            raise ValueError(f"release record: {name} requires a nonempty list of statements")
    if not isinstance(record["evidence"], list) or not record["evidence"]:
        raise ValueError("release record: evidence links required")
    for link in record["evidence"]:
        if not isinstance(link, dict) or set(link) != {"label", "url"} or not all(isinstance(v, str) and v.strip() for v in link.values()):
            raise ValueError("release record: malformed evidence link")
        if not (link["url"].startswith("https://") or (link["url"].startswith("/") and not link["url"].startswith("//"))):
            raise ValueError("release record: evidence link requires HTTPS or a site path")
    if record["repository"] != "https://github.com/unpingable/absd" or record["licence"] != "Apache-2.0":
        raise ValueError("release record: repository and licence must match the public source")
    if record["qualification"] not in ("preview", "qualified"):
        raise ValueError("release record: qualification must be preview or qualified")
    for name in ("kernel_suite_result", "core_profile_result", "qualification_record"):
        value = record[name]
        if record["qualification"] == "preview":
            if value is not None:
                raise ValueError(f"release record: preview requires null {name}")
        elif not isinstance(value, str) or not value.strip() or UNFILLED in value:
            raise ValueError(f"release record: qualified requires {name}")
    load_binary_preview(record)
    if record["binary_preview"] is not None and check_documentation:
        release_docs.load(record, ROOT)
    return record


# The downloadable binary preview (absd-coord #31/#32). Absent (null) until an
# owner-approved GitHub Release of the source tag carries binary assets.
PREVIEW_LADDER = ("built", "offline-boot-tested", "qualified", "release-authorized", "published", "outsider-passed")
PREVIEW_FIELDS = {"tag", "assets", "manifest_url", "sums_url", "sums", "signature", "qemu_profile",
                  "host_tiers", "qualification", "evidence", "quickstart_url", "limitations", "documentation"}
ASSET_BASE = "https://github.com/unpingable/absd/releases/download/"
HARDWARE_LIMIT = "Physical hardware qualification is not yet established."


def ladder(level):
    """The standing and the stages still ahead. Earlier stages are named, not
    counted as established: the evidence entries say what is."""
    ahead = ", ".join(PREVIEW_LADDER[PREVIEW_LADDER.index(level) + 1:]) or "none"
    return (f"Standing: <strong>{html.escape(level)}</strong>. Not yet reached: {html.escape(ahead)}. "
            f"Stages, in order: {', '.join(PREVIEW_LADDER)}.")


def load_binary_preview(record):
    """Validates record["binary_preview"]. Nothing is fetched: every URL must
    be the exact tagged asset address, every asset digest must equal the
    record's own copy of SHA256SUMS, and the qualification level must be
    named by an evidence entry of that same level."""
    preview = record["binary_preview"]
    if preview is None:
        return None
    if not isinstance(preview, dict) or set(preview) != PREVIEW_FIELDS:
        raise ValueError("binary preview: expected its exact fields")
    if "releases/latest" in json.dumps(preview):
        raise ValueError("binary preview: releases/latest is never a canonical address")
    tag = preview["tag"]
    if tag != record["release_id"]:
        raise ValueError("binary preview: tag differs from release_id")
    base = ASSET_BASE + tag + "/"
    signature = preview["signature"]
    if signature != "unsigned" and not (isinstance(signature, str) and signature.startswith("ssh-keygen -Y verify ")):
        raise ValueError("binary preview: signature must be unsigned or an ssh-keygen -Y verify command")
    sums = {}
    if not isinstance(preview["sums"], list) or not preview["sums"]:
        raise ValueError("binary preview: sums requires the SHA256SUMS lines")
    for line in preview["sums"]:
        m = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line) if isinstance(line, str) else None
        if not m or m.group(2) in (".", ".."):
            raise ValueError(f"binary preview: malformed sums line {line!r}")
        if m.group(2) in sums:
            raise ValueError(f"binary preview: SHA256SUMS lists {m.group(2)} twice")
        sums[m.group(2)] = m.group(1)
    if not isinstance(preview["assets"], list) or not preview["assets"]:
        raise ValueError("binary preview: assets required")
    if len(preview["assets"]) > 1000:
        raise ValueError("binary preview: at most 1000 assets per release")
    names = set()
    signed = preview["signature"] != "unsigned"
    for asset in preview["assets"]:
        if not isinstance(asset, dict) or set(asset) != {"name", "url", "sha256", "bytes"}:
            raise ValueError("binary preview: malformed asset")
        name = asset["name"]
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in (".", "..")
                or name == "SHA256SUMS"):
            raise ValueError(f"binary preview: malformed asset name {name!r}")
        if name in names:
            raise ValueError(f"binary preview: asset {name} listed twice")
        if asset["url"] != base + name:
            raise ValueError(f"binary preview: {name} is not at its tagged release address")
        if not isinstance(asset["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            raise ValueError(f"binary preview: malformed sha256 for {name}")
        if name == "SHA256SUMS.sig":
            # The signature signs SHA256SUMS, so SHA256SUMS cannot list it.
            if not signed:
                raise ValueError("binary preview: SHA256SUMS.sig listed but the record says unsigned")
            if type(asset["bytes"]) is not int or asset["bytes"] <= 0:
                raise ValueError(f"binary preview: malformed bytes for {name}")
            names.add(name)
            continue
        if sums.get(name) != asset["sha256"]:
            raise ValueError(f"binary preview: {name} digest differs from the record's SHA256SUMS")
        if type(asset["bytes"]) is not int or asset["bytes"] <= 0:
            raise ValueError(f"binary preview: malformed bytes for {name}")
        if asset["bytes"] >= 2**31:
            raise ValueError(f"binary preview: {name} must be under 2 GiB")
        names.add(name)
    if signed and "SHA256SUMS.sig" not in names:
        raise ValueError("binary preview: a signed record must list SHA256SUMS.sig")
    if set(sums) != names - {"SHA256SUMS.sig"}:
        raise ValueError("binary preview: SHA256SUMS lists files that are not assets")
    if preview["sums_url"] != base + "SHA256SUMS":
        raise ValueError("binary preview: sums_url is not the tagged SHA256SUMS")
    if preview["manifest_url"] not in {base + n for n in names}:
        raise ValueError("binary preview: manifest_url is not one of the listed assets")
    # The quickstart is the source repository's file at the tag (design #31 §8);
    # a release asset copy may exist, but the site links the tagged source.
    if preview["quickstart_url"] != f"{record['repository']}/blob/{tag}/QUICKSTART.md":
        raise ValueError("binary preview: quickstart_url is not QUICKSTART.md at the tag in the source repository")
    if not isinstance(preview["qemu_profile"], str) or not preview["qemu_profile"].strip():
        raise ValueError("binary preview: qemu_profile required")
    for field in ("host_tiers", "limitations"):
        if not isinstance(preview[field], list) or not preview[field] or any(
                not isinstance(v, str) or not v.strip() for v in preview[field]):
            raise ValueError(f"binary preview: {field} requires a nonempty list of statements")
    if HARDWARE_LIMIT not in preview["limitations"]:
        raise ValueError("binary preview: the physical hardware limitation must remain")
    level = preview["qualification"]
    if level not in PREVIEW_LADDER:
        raise ValueError(f"binary preview: qualification must be one of {', '.join(PREVIEW_LADDER)}")
    evidence = preview["evidence"]
    if not isinstance(evidence, list) or any(
            not isinstance(e, dict) or set(e) != {"level", "label", "url"}
            or e["level"] not in PREVIEW_LADDER or not all(isinstance(v, str) and v.strip() for v in e.values())
            or not (e["url"].startswith("https://") or (e["url"].startswith("/") and not e["url"].startswith("//")))
            for e in evidence):
        raise ValueError("binary preview: malformed evidence entry")
    # Every level above `built` must be named by an evidence entry of that
    # level: a record cannot claim a step it does not cite.
    if level != "built" and level not in {e["level"] for e in evidence}:
        raise ValueError(f"binary preview: qualification {level} has no evidence entry of that level")
    return preview


RELEASE = load_release(RELEASE_PATH)
# A binary-only preview (no source release) is a separate record; the source
# record above and its validation are unchanged by it.
BINARY = binary_preview.load(ROOT, RELEASE["release_id"])
if BINARY and RELEASE["binary_preview"]:
    raise ValueError("binary-only preview: the source record already selects a binary preview")
SOURCE_REPO = RELEASE["repository"]
SOURCE_LICENCE = RELEASE["licence"]
for field in ("release_id", "release_commit", "kernel_commit", "platform_commit", "release_date",
              "qualification", "kernel_suite_result", "core_profile_result", "qualification_record"):
    globals()["SOURCE_" + field.upper()] = RELEASE[field] or UNFILLED

# Qualification labels remain bounded; preview evidence wording belongs to the record.
SOURCE_STATEMENTS = {
    "preview": (
        "l-exp", "EXPERIMENTAL-INTEGRATION",
        RELEASE["preview_summary"], RELEASE["preview_details"]),
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
    *([("/try/", "Try")] if RELEASE["binary_preview"] or BINARY else []),
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
    notice = '<aside class="note" aria-label="Current public source standing">\n'
    standing = (f'Source release {html.escape(RELEASE["release_id"])} standing' if BINARY else 'Current public standing')
    notice += f'<p><strong>{standing}:</strong> {html.escape(RELEASE["standing"])} Editorial update: {RELEASE["editorial_updated"]}.</p>\n'
    for name, title in (("demonstrated", "Demonstrated"), ("limitations", "Limits")):
        notice += f'<p><strong>{title}:</strong></p><ul>' + ''.join(f'<li>{html.escape(v)}</li>' for v in RELEASE[name]) + '</ul>\n'
    notice += '<p>Evidence: ' + ' · '.join(f'<a href="{html.escape(v["url"], quote=True)}">{html.escape(v["label"])}</a>' for v in RELEASE["evidence"]) + '</p>\n</aside>'
    values.update({
        "SOURCE_NOTICE": notice,
        "SOURCE_REPO": SOURCE_REPO,
        "SOURCE_LICENCE": SOURCE_LICENCE,
        # Files are linked at the release tag, so a link shows the text this
        # site was checked against.
        "SOURCE_FILE": f"{SOURCE_REPO}/blob/{urllib.parse.quote(shown('SOURCE_RELEASE_ID'), safe='')}",
        "SOURCE_LABEL": f'<span class="label {css}">{label}</span>',
        "SOURCE_QUALIFICATION_SHORT": html.escape(short),
        "SOURCE_QUALIFICATION": html.escape(full),
        "SOURCE_GET_STARTED": (
            f'The selected developer preview <code>{html.escape(RELEASE["release_id"])}</code> has been withdrawn. '
            '<a href="/try/">Read the withdrawal notice</a> before using any retained files.'
            if RELEASE["binary_preview"] and RELEASE["binary_preview"]["documentation"]["state"] == "withdrawn" else
            f'The binary developer preview <code>{html.escape(RELEASE["release_id"])}</code> has '
            f'documentation state <strong>{html.escape(RELEASE["binary_preview"]["documentation"]["state"])}</strong>. '
            '<a href="/try/">Download and try ABSD</a> describes its exact files, QEMU profile, '
            'verification and first run. Read that state before using the files; a staged record is not a published release.'
            if RELEASE["binary_preview"] else
            binary_get_started() if BINARY else
            'On an Ubuntu 24.04 x86-64 host: clone the source, build the operator image, boot it under QEMU, '
            'and log in over SSH. The build and the smoke test need no KVM. Follow the '
            f'<a href="{SOURCE_REPO}/blob/{RELEASE["release_id"]}/README.md#build-boot-test">repository\'s README</a>; '
            '<a href="/status/#source">status</a> says what that does and does not show.'),
        "SOURCE_RELEASE_MANUAL": (
            f'\n\n<p>The <a href="/releases/{RELEASE["release_id"]}/manual/">manual for binary preview '
            f'{html.escape(RELEASE["release_id"])}</a> is pinned to platform '
            f'<code>{RELEASE["platform_commit"]}</code>. The milestone pages below retain their earlier provenance.</p>'
            if RELEASE["binary_preview"] else ''),
        "BINARY_STATUS": binary_status(),
        "BINARY_NOTICE": binary_notice(),
    })
    return values


def binary_get_started():
    record = BINARY[0]
    esc = html.escape
    if record["state"] == "withdrawn":
        return (f'The binary developer preview <code>{esc(record["tag"])}</code> has been withdrawn. '
                '<a href="/try/">Read the withdrawal notice</a> before using any retained files.')
    return (f'Binary developer preview <code>{esc(record["tag"])}</code> (state <strong>{esc(record["state"])}</strong>): '
            '<a href="/try/">what works, what does not, and how to try it</a> on a Linux x86-64 host with QEMU, '
            'with no build tools. To build from source instead, follow the source release\'s '
            f'<a href="{SOURCE_REPO}/blob/{RELEASE["release_id"]}/README.md#build-boot-test">README</a>; '
            '<a href="/status/#source">status</a> says what each does and does not show.')


def binary_notice():
    """The home page's lead for the selected binary-only preview, ahead of the
    source release's standing. Empty, with no trailing text, when absent."""
    if not BINARY:
        return ""
    record = BINARY[0]
    esc = html.escape
    tag = record["tag"]
    if record["state"] == "withdrawn":
        body = (f'Binary developer preview <code>{esc(tag)}</code> has been withdrawn. '
                '<a href="/try/">Read the withdrawal notice</a>.')
    else:
        evidence = "".join(f' · <a href="{esc(e["url"], quote=True)}">{esc(e["label"])}</a>'
                           for e in record["evidence"] if e["level"] == "published")
        body = (f'Binary developer preview <code>{esc(tag)}</code>, state <strong>{esc(record["state"])}</strong>. '
                f'{ladder(record["qualification"])} For QEMU on a Linux x86-64 host, with no build tools: '
                f'<a href="/try/">what works, what does not, and how to try it</a> · '
                f'<a href="/releases/{esc(tag)}/">release page</a>{evidence}.')
    return (f'<aside class="note" aria-label="Current binary preview">\n<p><strong>Current release:</strong> {body}</p>\n'
            '<p>The source release below is a separate, earlier publication.</p>\n</aside>\n\n')


def binary_source_note(record):
    esc = html.escape
    attached = [a["name"] for a in record["assets"]
                if a["name"].endswith(("-corresponding-source.tar", "-notices.tar.gz"))]
    names = " and ".join(f"<code>{esc(n)}</code>" for n in attached)
    return (f'<p>No first-party ABSD source release accompanies <code>{esc(record["tag"])}</code>: its kernel '
            f'<code>{record["kernel_commit"]}</code> and platform <code>{record["platform_commit"]}</code> are not published as source. '
            + (f'Its download set does include {names}: the exact GRUB and GNU Unifont corresponding-source '
               'packages for the boot components, and the third-party notices. The release\'s NOTICES.md says how to '
               'extract and check them. ' if attached else '')
            + f'The earlier public source release <code>{esc(RELEASE["release_id"])}</code> remains available '
            '(<a href="/status/#source">source release</a>).</p>')


def binary_status():
    """The status page's section for the selected binary-only preview."""
    if not BINARY:
        return ""
    record = BINARY[0]
    esc = html.escape
    items = "".join(f"<li>{esc(s)}</li>" for s in record["not_in_preview"])
    works = "".join(f"<li>{esc(s)}</li>" for s in record["works"])
    return (f'<section class="facts" aria-labelledby="binary-preview">\n<h2 id="binary-preview">Binary developer preview</h2>\n<dl>\n'
            f'<dt>Tag</dt><dd><code>{esc(record["tag"])}</code>; media release id <code>{esc(record["release_id"])}</code></dd>\n'
            f'<dt>Kernel</dt><dd><code>{record["kernel_commit"]}</code></dd>\n'
            f'<dt>Platform</dt><dd><code>{record["platform_commit"]}</code></dd>\n'
            f'<dt>State</dt><dd>{esc(record["state"])}. {ladder(record["qualification"])} '
            '(<a href="/try/">files and limits</a>)</dd>\n</dl>\n</section>\n'
            f'<p>This describes the preview image as released, not the development line. In the image:</p>\n<ul>{works}</ul>\n'
            f'<p>Not in this preview:</p>\n<ul>{items}</ul>\n' + binary_source_note(record))


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


def try_page(record=None):
    """The Download / Try page, built only when the record has a binary
    preview: the pinned asset addresses and digests, nothing discovered."""
    selected = record is None
    record = RELEASE if selected else record
    preview = record["binary_preview"]
    esc = html.escape
    if selected and preview['documentation']['state'] == 'withdrawn':
        return (f'<h1>ABSD preview withdrawn</h1><p>Developer preview <code>{esc(record["release_id"])}</code> '
                'is withdrawn. There is no current binary download recommendation.</p><ul>'
                + ''.join(f'<li>{esc(s)}</li>' for s in preview['limitations'])
                + f'</ul><p><a href="/releases/{record["release_id"]}/">Retained release record</a>; '
                'the archived files and instructions remain for history, not a new installation.</p>')
    rows = "".join(
        f'<tr><td><a href="{esc(a["url"], quote=True)}"><code>{esc(a["name"])}</code></a></td>'
        f'<td><code class="digest">{a["sha256"]}</code></td><td>{a["bytes"]}</td></tr>\n'
        for a in preview["assets"])
    evidence = "".join(f'<li>{esc(e["level"])}: <a href="{esc(e["url"], quote=True)}">{esc(e["label"])}</a></li>'
                       for e in preview["evidence"]) or "<li>None recorded.</li>"
    signature = ("These files are not signed. The checksums guard against corruption, not against a compromised account."
                 if preview["signature"] == "unsigned" else
                 f'Verify the signature on the checksums with <code>{esc(preview["signature"])}</code>.')
    return f"""<h1>Try ABSD</h1>
<p>Developer preview <code>{esc(preview["tag"])}</code>, the binary build of source release
<code>{esc(record["release_id"])}</code>. Documentation state:
<strong>{esc(preview['documentation']['state'])}</strong>. Draft/staged records do not establish public availability;
withdrawn records are retained for history and must not be used for a new installation.
It runs under QEMU on the hosts listed below. {ladder(preview["qualification"])}
<a href="/status/#source">What the source release establishes</a>.</p>
<h2 id="files">Files</h2>
<p>Every address is the tagged release asset; nothing here follows a moving pointer.</p>
<table>
<thead><tr><th>File</th><th>SHA-256</th><th>Bytes</th></tr></thead>
<tbody>
{rows}</tbody>
</table>
<p><a href="{esc(preview["sums_url"], quote=True)}">SHA256SUMS</a> ·
<a href="{esc(preview["manifest_url"], quote=True)}">manifest</a> ·
<a href="{esc(preview["quickstart_url"], quote=True)}">quickstart</a></p>
<h2 id="verify">Verify</h2>
<p>Download every file and <code>SHA256SUMS</code> into one directory, then run <code>sha256sum -c SHA256SUMS</code>.
{signature}</p>
<h2 id="hosts">Hosts and QEMU</h2>
<p>QEMU profile: {esc(preview["qemu_profile"])}</p>
<ul>{"".join(f"<li>{esc(t)}</li>" for t in preview["host_tiers"])}</ul>
<h2 id="limits">Limits</h2>
<ul>{"".join(f"<li>{esc(t)}</li>" for t in preview["limitations"])}</ul>
<h2 id="evidence">Evidence</h2>
<ul>{evidence}</ul>
"""


def binary_page():
    """The release page and /try/ for the selected binary-only preview. Every
    value is the record's, which was verified against the sealed inputs."""
    record, _ = BINARY
    esc = html.escape
    tag = record["tag"]
    prefix = f"/releases/{tag}/"
    limits = "".join(f"<li>{esc(t)}</li>" for t in record["limitations"])
    quoted = tomllib.loads(BINARY[1]["MANIFEST.toml"].decode())["limitations"]
    sealed = "".join(f"<li>{esc(t)}</li>" for t in quoted)
    later = [t for t in record["limitations"] if t not in quoted]
    added = (f'<p>Added on this site:</p>\n<ul>{"".join(f"<li>{esc(t)}</li>" for t in later)}</ul>' if later else "")
    sealed_note = ("These limitations are quoted from the release's MANIFEST.toml, written before publication; "
                   f"the release was published on {record['release_date']}." if record["state"] == "published" else
                   "These limitations are quoted from the release's MANIFEST.toml, as sealed.")
    if record["state"] == "withdrawn":
        return (f'<h1>ABSD preview withdrawn</h1><p>Developer preview <code>{esc(tag)}</code> is withdrawn. '
                f'There is no current binary download recommendation.</p><ul>{limits}</ul>'
                f'<p>The <a href="{prefix}QUICKSTART.md">sealed QUICKSTART.md</a> is retained for history, not a new installation.</p>')
    quick = binary_preview.base(record) + "QUICKSTART.md"
    state = ("" if record["state"] == "published" else
             f'<p class="note"><strong>State: {esc(record["state"])}.</strong> A draft record does not make these files '
             'public; the addresses below work only once the release is published.</p>\n')
    rows = "".join(
        f'<tr><td><a href="{esc(a["url"], quote=True)}"><code>{esc(a["name"])}</code></a></td>'
        f'<td><code class="digest">{a["sha256"]}</code></td><td>{a["bytes"]}</td></tr>\n'
        for a in record["assets"])
    evidence = "".join(f'<li>{esc(e["level"])}: <a href="{esc(e["url"], quote=True)}">{esc(e["label"])}</a></li>'
                       for e in record["evidence"]) or "<li>None recorded.</li>"
    return f"""<h1>Try ABSD {esc(tag)}</h1>
{state}<p>A binary developer preview for QEMU on a Linux x86-64 host: kernel <code>{record["kernel_commit"][:12]}</code>,
platform <code>{record["platform_commit"][:12]}</code>. Unsigned.
{ladder(record["qualification"])}</p>
<h2 id="works">What works</h2>
<ul>{"".join(f"<li>{esc(s)}</li>" for s in record["works"])}</ul>
<h2 id="not-in-preview">What is not in this preview</h2>
<ul>{"".join(f"<li>{esc(s)}</li>" for s in record["not_in_preview"])}</ul>
<h2 id="how">How to try it</h2>
<p>Follow <a href="{esc(quick, quote=True)}">QUICKSTART.md</a> from the release (the same bytes, as sealed:
<a href="{prefix}QUICKSTART.md">copy on this site</a>). In a new empty directory: download the files below and
<code>SHA256SUMS</code>, run <code>sha256sum -c SHA256SUMS</code> and <code>python3 absd-try.py verify .</code>, create a machine
with your own new key, boot it, and log in over SSH. Stop if either verification fails.</p>
{binary_source_note(record)}
<h2 id="files">Files</h2>
<p>Every address is the tagged release asset; nothing here follows a moving pointer.</p>
<table>
<thead><tr><th>File</th><th>SHA-256</th><th>Bytes</th></tr></thead>
<tbody>
{rows}</tbody>
</table>
<p><a href="{esc(binary_preview.base(record) + "SHA256SUMS", quote=True)}">SHA256SUMS</a>
(sha256 <code class="digest">{record["sums_sha256"]}</code>) · <a href="{prefix}MANIFEST.toml">manifest</a> ·
<a href="{prefix}SHA256SUMS">checksums</a> (copies on this site)</p>
<h2 id="limits">Limits</h2>
<p>{sealed_note}</p>
<ul>{sealed}</ul>
{added}
<h2 id="evidence">Evidence</h2>
<ul>{evidence}</ul>
"""


def binary_outputs():
    """Site-relative path -> bytes for the binary-only preview."""
    if not BINARY:
        return {}
    record, files = BINARY
    tag = record["tag"]
    description = ("Withdrawn ABSD developer preview: read the release notice." if record["state"] == "withdrawn"
                   else f"What works, what does not, and how to try ABSD {tag} under QEMU.")
    page = binary_page()
    outputs = {"try/index.html": layout("/try/", "Try ABSD", description, page),
               f"releases/{tag}/index.html": layout(f"/releases/{tag}/", f"ABSD {tag}", description, page)}
    outputs = {k: v.encode("utf-8") for k, v in outputs.items()}
    # The sealed inputs, byte for byte; QUICKSTART.md is never re-rendered.
    outputs.update({f"releases/{tag}/{name}": data for name, data in files.items()})
    return outputs


def documentation_records():
    records = {}
    for path in sorted((ROOT / "content/releases").glob("*/release.json")):
        record = load_release(path)
        if path.parent != release_docs.release_dir(ROOT, record):
            raise ValueError("documentation: archive path disagrees with release id")
        records[record["release_id"]] = record
    if RELEASE["binary_preview"]:
        old = records.get(RELEASE["release_id"])
        if old is not None and old != RELEASE:
            raise ValueError("documentation: archived and selected release disagree")
        records[RELEASE["release_id"]] = RELEASE
    return list(records.values())


def try_description():
    if RELEASE['binary_preview']['documentation']['state'] == 'withdrawn':
        return 'Withdrawn ABSD developer preview: read the release notice.'
    return 'Download and verify the ABSD developer preview for QEMU.'


def documentation_outputs(record, version):
    """All release-specific output is a deterministic view of one verified
    record. The dated milestone manual remains at its original URLs."""
    doc = release_docs.load(record, ROOT)
    tag = record["release_id"]
    prefix = f"/releases/{tag}/"
    title = f"ABSD {tag}"
    body = try_page(record) + f'<p><a href="{prefix}QUICKSTART.md">Release quickstart</a> · <a href="{prefix}manual/">Release manual</a></p>'
    outputs = {f"releases/{tag}/index.html": layout(prefix, title, f"Files and documentation for ABSD {tag}.", body)}
    outputs.update({f"releases/{tag}/{name}": text for name, text in release_docs.exports(record, doc).items()})
    directory = release_docs.release_dir(ROOT, record) / "manual"
    pages = sorted(p for p in directory.iterdir() if re.fullmatch(r"[a-z0-9.-]+\.[1-9]", p.name))
    known = {(p.stem, p.suffix[1:]) for p in pages}
    links = []
    for page in pages:
        name, sec = page.stem, page.suffix[1:]
        url = prefix + f"man/{name}.{sec}/"
        text = man_html(render_man(page), known).replace('href="/man/', f'href="{prefix}man/')
        provenance = (f'<p>Release <code>{html.escape(tag)}</code>; platform <code>{record["platform_commit"]}</code>. '
                      f'Rendered from the exact source release\'s mdoc with {html.escape(version)}. '
                      'These pages describe that revision; their presence is not a qualification result.</p>')
        body = (f'<h1>{name}({sec})</h1>{provenance}<pre class="man" tabindex="0" '
                f'aria-label="{name}({sec}) manual page">{text}</pre><p><a href="{prefix}manual/">Release manual index</a></p>')
        outputs[f"releases/{tag}/man/{name}.{sec}/index.html"] = layout(url, f"{name}({sec}) — {tag}",
                    f"{name}({sec}): {description_of(page)}. Release {tag}.", body)
        links.append(f'<li><a href="{url}">{name}({sec})</a>: {html.escape(description_of(page))}</li>')
    body = (f'<h1>Manual for {html.escape(tag)}</h1><p>Platform <code>{record["platform_commit"]}</code>; '
            f'<a href="{prefix}">release files and standing</a>. '
            '<a href="/manual/">Historical milestone manual</a>.</p><ul>' + ''.join(links) + '</ul>')
    outputs[f"releases/{tag}/manual/index.html"] = layout(prefix + "manual/", f"Manual — {tag}",
                                                         f"Operator manual for release {tag}.", body)
    return outputs


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

    (OUT / "release-source.sha256").write_text(hashlib.sha256(RELEASE_PATH.read_bytes()).hexdigest() + "\n")

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
    if RELEASE["binary_preview"]:
        write("/try/", layout("/try/", "Try ABSD", try_description(), try_page()))
        pages += 1
    for relative, data in binary_outputs().items():
        path = OUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        pages += relative.endswith(".html")
    for record in documentation_records():
        for relative, text in documentation_outputs(record, version).items():
            path = OUT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
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
