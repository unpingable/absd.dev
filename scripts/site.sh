#!/bin/sh
# Thin entry point for the existing builder, checker and gh-pages procedure.
set -eu
cd "$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
case "${1:-}" in
    generate) python3 build.py ;;
    check) python3 scripts/check.py; python3 scripts/content-check.py; python3 -B scripts/test_release_docs.py; python3 -B scripts/test_binary_preview.py ;;
    preview) python3 -m http.server --bind 127.0.0.1 -d site 8765 ;;
    publish)
        test "$(git branch --show-current)" = main || { echo 'site: publish from main' >&2; exit 1; }
        python3 scripts/content-check.py
        git diff origin/main HEAD -- README.md PUBLISHING.md content build.py release_docs.py binary_preview.py scripts src
        scripts/stage-pages.sh
        git push origin main
        git push origin gh-pages
        ;;
    *) echo 'usage: scripts/site.sh generate|check|preview|publish' >&2; exit 2 ;;
esac
