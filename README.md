# absd.dev

Source of the static site at https://absd.dev/, the public description of
ABSD, an experimental operating system.

This repository holds the site only: its pages, the manual sources they
render, and the build and check scripts. It does not contain the operating
system. ABSD's source is published separately, as source releases, at
https://github.com/unpingable/absd under the Apache License 2.0; build
instructions, licensing detail and the contribution process are in that
repository and are linked from the site, not copied here. That licence
does not cover this repository: no license is granted for the site's
content, which is published to be read.

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

Claims on the status, design, hardware, and evidence pages carry one of the
labels defined on /status/.
When the milestone changes, update `MILESTONE*`, `KERNEL`, `PLATFORM` in
build.py, resync `man/` with `scripts/sync-man.sh`, recapture the
session, and revise /status/ and /evidence/ by hand.

### Source release switch

The public source release the site describes is set in one block of
build.py, marked `RELEASE SWITCH`: `SOURCE_RELEASE_ID`,
`SOURCE_RELEASE_COMMIT`, `SOURCE_KERNEL_COMMIT`, `SOURCE_PLATFORM_COMMIT`,
`SOURCE_RELEASE_DATE` (from the published `SOURCE-MANIFEST.toml` and the
release commit) and `SOURCE_QUALIFICATION`, which selects one of two
prepared statements: `preview` (built, booted and smoke-tested from a clean
clone; suites not yet run) or `qualified` (kernel suite and core profile
passed; also fill `SOURCE_KERNEL_SUITE_RESULT`, `SOURCE_CORE_PROFILE_RESULT`
and `SOURCE_QUALIFICATION_RECORD` from the runs' own output). Pages use them
as `{{SOURCE_*}}`. A value left at `FILL-AT-DEPLOY` still builds, for
preview, but `scripts/check.py` fails, so `scripts/stage-pages.sh` will not
stage the site. Do not deploy before the repository above is public and
carries that release.

`man/` is still the milestone's manual. The source release carries a later
one (`platform/man/`); to show it, resync with `scripts/sync-man.sh` against
the release's platform commit and revise the manual's provenance text.

`scripts/check.py` also reads an optional, untracked
`scripts/private-patterns.local` (one `regex<TAB>description` per line) for
names that must not appear on the site.

## Deploying

    scripts/stage-pages.sh           # build, check, commit site/ to local gh-pages
    git push origin gh-pages         # publish

GitHub Pages serves the `gh-pages` branch root with the custom domain in
`site/CNAME` (from `src/static/CNAME`). Each commit on `gh-pages` names the
`main` commit it was built from.
