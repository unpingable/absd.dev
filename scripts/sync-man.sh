#!/bin/sh
# Refresh man/ from a platform git checkout at a tag:
#   scripts/sync-man.sh PLATFORM_CHECKOUT TAG
# Copies man/*.[1-9] from the tagged commit (git show; the checkout's
# working tree is not read) and rewrites man/SHA256SUMS. Edit man/SOURCE
# and MILESTONE in build.py by hand afterwards.
set -eu
repo=${1:?usage: sync-man.sh PLATFORM_CHECKOUT TAG}
tag=${2:?usage: sync-man.sh PLATFORM_CHECKOUT TAG}
here=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
commit=$(git -C "$repo" rev-parse "$tag^{commit}")
rm -f "$here"/man/*.[1-9]
git -C "$repo" ls-tree --name-only "$commit" man/ | grep '\.[1-9]$' | while read -r path; do
    git -C "$repo" show "$commit:$path" >"$here/$path"
done
(cd "$here/man" && sha256sum *.[1-9] >SHA256SUMS)
echo "synced man/ from $tag ($commit)"
