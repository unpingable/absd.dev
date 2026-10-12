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

Templates use the existing `{{SOURCE_*}}` replacements. Their HTML is generated
in `site/`, which is disposable and must not be edited. `release-source.sha256`
is a local build freshness check, not a qualification or provenance receipt.
The structured record does not replace human review of evidence or prose.
