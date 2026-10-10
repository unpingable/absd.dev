# absd.dev

Static site for https://absd.dev/. Not published.

    python3 build.py                 # renders site/ (needs GNU groff 1.23.0)
    python3 scripts/check.py         # links, accessibility, metadata, leaks
    python3 scripts/check.py --screenshots DIR   # plus 360/768/1280 px, light
                                                 # and dark, with local Chrome
    python3 -m http.server -d site 8765          # preview at http://127.0.0.1:8765/

Layout: `src/pages/**/index.html` are page bodies (metadata comments on
top, `{{PLACEHOLDERS}}` filled by build.py); `src/static/` is copied as
is; `man/` holds the mdoc sources vendored from the platform at the
milestone tag (see `man/SOURCE`), rendered at build time; `captures/`
holds recorded transcripts inserted verbatim; `drafts/` is never built.

Every factual statement carries one of the labels defined on /status/.
When the milestone changes, update `MILESTONE*`, `KERNEL`, `PLATFORM` in
build.py, resync `man/` with `scripts/sync-man.sh`, recapture the
session, and revise /status/ and /evidence/ by hand.

## Deploying

    scripts/stage-pages.sh           # build, check, commit site/ to local gh-pages
    git push origin gh-pages         # publish (owner only)

GitHub Pages serves the `gh-pages` branch root with the custom domain in
`site/CNAME` (from `src/static/CNAME`). DNS for absd.dev already points
at GitHub Pages (apex A/AAAA records, `www` CNAME to unpingable.github.io).

## Before publishing

Nothing here is deployed. Owner decisions still open:

1. Every claim on every page, read against its receipt (the 2026-10-08
   revision added /status/#since, the release record on /evidence/, and
   /hardware/#observations).
2. Whether full commit hashes and ISO digests of private repositories may
   be published (the release record adds more of them).
3. The /research/ links and the About line "not derived from BSD source".
4. This repository's visibility: Pages on a private repository needs a
   paid plan, and /about/ links to this repository's issues. Making it
   public publishes its history, whose earlier `scripts/check.py` named
   private repositories, a host, and paths (now moved to the untracked
   `scripts/private-patterns.local`); publish a fresh history instead if
   that matters.
5. Indexing: robots.txt allows it; there is no og:image.
6. `/research/program/` is an unpublished draft. `unlisted` keeps it out of
   the navigation and sitemap and adds noindex, which is not access control:
   stage gh-pages and any public source snapshot from `8f3dde9`, or remove
   the page first.
