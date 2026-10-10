#!/bin/sh
# Build and check the site, then commit site/ as the whole tree of the local
# gh-pages branch, which GitHub Pages serves (Settings > Pages > Deploy from
# a branch: gh-pages, / (root)). Nothing is pushed; publishing is
#   git push origin gh-pages
# run by the owner. The commit names the main commit it was built from.
set -eu
here=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$here"
if [ -n "$(git status --porcelain)" ]; then
    echo "stage-pages: working tree not clean; commit first" >&2
    exit 1
fi
python3 build.py
python3 scripts/check.py
test -f site/CNAME
: >site/.nojekyll
source_commit=$(git rev-parse HEAD)
tmp=$(mktemp -d)
trap 'git -C "$here" worktree remove --force "$tmp/w" 2>/dev/null; rm -rf "$tmp"' EXIT
if git show-ref --verify --quiet refs/heads/gh-pages; then
    git worktree add --quiet "$tmp/w" gh-pages
else
    git worktree add --quiet --detach "$tmp/w"
    git -C "$tmp/w" checkout --quiet --orphan gh-pages
fi
git -C "$tmp/w" rm -r --quiet --force --ignore-unmatch .
cp -R site/. "$tmp/w/"
git -C "$tmp/w" add -A
if git -C "$tmp/w" diff --cached --quiet; then
    echo "stage-pages: gh-pages already matches $source_commit"
else
    git -C "$tmp/w" commit --quiet -m "Build site from $source_commit"
    echo "stage-pages: gh-pages at $(git rev-parse --short gh-pages), built from $source_commit"
fi
