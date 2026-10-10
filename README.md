# absd.dev

Source of the static site at https://absd.dev/, the public description of
ABSD, an experimental operating system.

This repository holds the site only: its pages, the manual sources they
render, and the build and check scripts. It does not contain the operating
system. ABSD's kernel and platform are developed privately; there is no
public source, download, or release, and no license has been chosen for
them. No license is granted for this repository's content either; it is
published to be read.

Corrections are welcome as issues. A claim on the site that its record does
not support is a bug.

## Building

    python3 build.py                 # renders site/ (needs GNU groff 1.23.0)
    python3 scripts/check.py         # links, accessibility, metadata, leaks
    python3 scripts/check.py --screenshots DIR   # plus 360/768/1280 px, light
                                                 # and dark, with local Chrome
    python3 -m http.server -d site 8765          # preview at http://127.0.0.1:8765/

Nothing is fetched at build time and the site uses no JavaScript, fonts, or
other third-party resources.

Layout: `src/pages/**/index.html` are page bodies (metadata comments on
top, `{{PLACEHOLDERS}}` filled by build.py); `src/static/` is copied as
is; `man/` holds the mdoc sources vendored from the platform at the
milestone tag (see `man/SOURCE`), rendered at build time; `captures/`
holds recorded transcripts inserted verbatim.

Every factual statement carries one of the labels defined on /status/.
When the milestone changes, update `MILESTONE*`, `KERNEL`, `PLATFORM` in
build.py, resync `man/` with `scripts/sync-man.sh`, recapture the
session, and revise /status/ and /evidence/ by hand.

`scripts/check.py` also reads an optional, untracked
`scripts/private-patterns.local` (one `regex<TAB>description` per line) for
names that must not appear on the site.

## Deploying

    scripts/stage-pages.sh           # build, check, commit site/ to local gh-pages
    git push origin gh-pages         # publish

GitHub Pages serves the `gh-pages` branch root with the custom domain in
`site/CNAME` (from `src/static/CNAME`). Each commit on `gh-pages` names the
`main` commit it was built from.
