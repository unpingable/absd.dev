# absd.dev

Source of the static site at https://absd.dev/, the public description of
ABSD, an experimental operating system.

ABSD's published Developer Preview 3 is a deliberately narrow,
single-operator QEMU environment; that is not the project's intended
ceiling. The long-term ambition is a genuinely usable general-purpose
operating system with native authority and failure semantics, not a
promise of production readiness, physical hardware support, or general
Linux/BSD binary compatibility today. Development-only physical boots
and experiments are not hardware qualification. The site's About,
Hardware, Status and release pages distinguish these claims.

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

## Updating and publishing

Follow [PUBLISHING.md](PUBLISHING.md) for the single update, generate, check,
preview and publish procedure. Current source-release metadata lives in
`content/release.json`; existing page templates render it through `build.py`.

Layout: `src/pages/**/index.html` contains page bodies and metadata comments;
`src/static/` is copied as is; `man/` contains the milestone's vendored mdoc
sources (see `man/SOURCE`); `captures/` contains recorded transcripts.
Nothing is fetched at build time; the site uses no JavaScript or third-party
resources. GNU groff 1.23.0 renders the manuals.

`scripts/check.py` also reads optional, untracked
`scripts/private-patterns.local` (`regex<TAB>description` per line).
