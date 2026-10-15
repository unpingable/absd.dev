# Publishing absd.dev

The public site is generated from `main`; GitHub Pages serves the root of
`gh-pages` at https://absd.dev. Use this one procedure:

1. Update `content/release.json` from the public release's tag, commit and
   `SOURCE-MANIFEST.toml` at https://github.com/unpingable/absd. It is the sole
   current source-release record. `preview` requires null result fields;
   `qualified` requires the kernel suite result, core-profile result and
   qualification receipt from the exact revisions' runs. Publication alone
   does not establish qualification. Confirm the named release is public.
2. For routine status updates, edit `editorial_updated`, `standing`,
   `demonstrated`, `limitations`, `evidence`, `preview_summary` and
   `preview_details` in that same record. They
   generate the shared home/status notice. Keep the standing consistent with
   the qualification enum and its prepared evidence wording. Do not promote
   a claim without the named run or evidence. For broader changes, edit the relevant `src/pages/**/index.html` prose when claims change.
   Keep earlier milestone/release records distinct from the current source,
   QEMU qualification distinct from hardware, and experiments labelled.
   Historical milestone constants, manual provenance and captures are not
   the current source-release record; update them only with their own evidence.
3. Run `scripts/site.sh generate`, then `scripts/site.sh check`. The checker
   refuses malformed release records and release metadata changed after the
   build. The content cases exercise a hypothetical update in a temporary
   copy and discard it. Nothing is fetched. GNU groff 1.23.0 is required.
4. Run `scripts/site.sh preview`, inspect http://127.0.0.1:8765/, then stop
   the server. Optional layout checks: `python3 scripts/check.py --screenshots DIR`.
5. Review `git diff` and the generated home/status preview, commit it on `main`, and run `scripts/site.sh publish`.
   This builds and checks again, stages a clean tree to local `gh-pages`
   through `scripts/stage-pages.sh`, pushes `main`, then pushes `gh-pages`.
   The Pages commit records the source commit. Inspect the Pages deployment
   and the public home/status pages; a successful push is not a deployment
   receipt. To stage without publishing, run `scripts/stage-pages.sh` alone.

## Binary preview (absd-coord #31, #32)

`content/release.json` (schema version 2) carries `binary_preview`. It stays
`null` until an owner-approved GitHub Release of the source tag carries the
preview's binary assets. With `null`, the build makes no `/try/` page and no
navigation link, and the checker refuses any download address.

The object's fields are `tag`, `assets[] {name, url, sha256, bytes}`,
`manifest_url`, `sums_url`, `sums` (the release's `SHA256SUMS` lines, copied),
`signature` (`unsigned` or an `ssh-keygen -Y verify …` command),
`qemu_profile`, `host_tiers`, `qualification`, `evidence[] {level, label,
url}`, `quickstart_url` and `limitations`. The build refuses a record where:

- `tag` differs from `release_id`;
- an address is not `https://github.com/unpingable/absd/releases/download/<tag>/<name>`;
- any address uses `releases/latest`;
- an asset digest is absent from, or different from, the copied `SHA256SUMS`;
- `SHA256SUMS` lists a file that is not an asset;
- a digest is malformed;
- `qualification` is not on the ladder built → offline-boot-tested →
  qualified → release-authorized → published → outsider-passed;
- `qualification` is above `built` and no `evidence` entry has that same
  `level`;
- the physical hardware limitation is missing.

Nothing is fetched.

The stages are kept distinct:

1. **Draft.** The record is prepared on a branch and built locally. The
   content cases exercise a synthetic record the same way.
2. **Staged.** The GitHub Release exists as a draft with its assets. Copy
   its `SHA256SUMS` lines and each file's byte count into the record; do
   not type them.
3. **Published.** This needs the owner's release and publication decision,
   then the ordinary publish step above. `qualification` names only the
   highest level whose evidence the record cites.
4. **Reachable.** After publication, fetch every asset URL, compare each
   digest and byte count with the record, and keep that receipt separately.
   It is not part of the site build, and a site push is not that receipt.

A later preview gets a new tag and a new record. Do not edit an earlier
release's assets or point an earlier page at newer files.

Templates use the existing `{{SOURCE_*}}` replacements. Their HTML is generated
in `site/`, which is disposable and must not be edited. `release-source.sha256`
is a local build freshness check, not a qualification or provenance receipt.
The structured record does not replace human review of evidence or prose.
