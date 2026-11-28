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

## Visual and editorial updates

Home and About can be updated independently of operating-system development.
Keep the selected release, its limits and its evidence distinct from newer
development. The homepage keeps the older source-preview record in an
expandable section; the full record remains on Status. The stylesheet adds
graph-paper decoration outside the reading surfaces, with print and
forced-colors overrides. Inspect desktop and narrow layouts in both themes.

The source-only rendering reference also pins page and stylesheet bytes.
After an intentional template or CSS edit, review its changed hashes in
`scripts/testdata/schema1-rendering-v1.json` separately from release claims.
Keep the fixture's `release_json` and file set unchanged, name the source
commit used to render it, and explain every changed file. Do not update
reference hashes to conceal an unexplained failure. Run the full checks
after the reviewed refresh. Publication still follows the procedure above.

## Claims vocabulary

Design informs documentation; evidence determines what documentation may
claim. Every public statement about ABSD is one of three kinds and uses that
kind's words. This section is the canonical wording for the site, the source
README and the kernel and platform documentation; other guidance points here.

- **Release support:** `supported`, `release-qualified`. Only for a named
  published release in a named environment, within the scope and evidence of
  that release's own record. `release-qualified` additionally requires that
  record's qualification runs. A developer preview whose record says
  `preview` or `published` is supported on its documented path and is not
  release-qualified.
- **Development evidence:** `observed`, `demonstrated in development`. Name
  the build, the test and the host, what happened, what was not tried, and
  whether the record is public. Give an exact count only when a public
  record carries it; otherwise state the shape of the result. A development
  result never implies that a release ships or supports it.
- **Research and ambition:** `aims to`, `intended`. Never phrased as a
  capability. Where a reader could take the aim for the current release, add
  one present-tense limit. One sentence of each is enough.

These kinds sit above the site's labels and do not merge them. The labels
keep the definitions on the Status page (`/status/#labels`):
`RELEASE-QUALIFIED` is release support for one exact kernel and platform
pair. `MILESTONE-QUALIFIED` is the recorded milestone run; it is not a
release claim and is never restated as `supported` or `release-qualified`.
`VALIDATED` and `EXPERIMENTAL-INTEGRATION` are development evidence.
`PLANNED` is direction. `UNSUPPORTED` means not provided. Historical
records keep the label and wording they were recorded with.

Hardware statements also name one evidence tier from the Hardware page
(emulator-qualified, exact-hardware-qualified,
machine-configuration-qualified, hardware-family-supported). A physical
boot or device test of a development build is development evidence under
"Physical observations" and holds no tier.

Architecture: native ABSD mechanisms, with their authority and failure
semantics, are the specification. Unix-style behaviour is a personality
implemented in userspace above the native interface, not the substrate;
ABSD is not built on Unix or Linux. Linux or other foreign binary
compatibility is direction: a separate personality that would not become
the native specification, claimed by no release.

## Binary preview (absd-coord #31, #32)

`content/release.json` remains the single current editorial record. Schema 1
has no binary preview; the live record remains schema 1. The unpublished
schema-2 preparation contract adds `binary_preview`, with its pinned tag,
assets (name, tagged GitHub URL, SHA-256, bytes), copied SHA256SUMS, manifest
and quickstart URLs, signature disposition, QEMU profile, host tiers,
qualification, evidence, limitations and `documentation {state,
manual_sha256, source_manifest_sha256}`. The v0 path is explicitly unsigned
by owner decision. With an unchanged schema-1 record, this mechanism leaves
the source-only site's generated bytes unchanged; a stored before/after
reference checks that property.
`content-check` builds its isolated source-only case from that stored record;
the selected live record is validated separately by generation and `check.py`.
An intentional change to the reference record or public templates needs a
reviewed reference refresh. A refresh never reclassifies an earlier failed run.

The record consumes the preview producer's `absd-preview-manifest/1`
MANIFEST.toml. The installed-release reconstruction manifests `/1` and `/2`
are different inputs and are refused here. The preview manifest binds the
release id/tag, source/kernel/platform commits, qualification at sealing,
original limits, and every asset except itself. Every actual asset must
match both it and SHA256SUMS. URLs use the exact source tag in
`https://github.com/unpingable/absd/releases/download/<tag>/<file>`;
`releases/latest`, assets of 2 GiB or more and contradictory identities are
refused. The quickstart source URL is QUICKSTART.md at that tag.

The current helper profile is QEMU 8.2 TCG on Linux x86-64, one CPU, 256 MiB
minimum, SeaBIOS, e1000 and a primary IDE disk. The manifest's QEMU table is
`cpu_tcg="max,vendor=GenuineIntel,+rdrand"`, `memory_mib=256`, `smp=1`,
`nic="e1000"`, `disk="ide"`, `firmware="SeaBIOS"`. Other profiles require
an implemented launcher and a separate rehearsal.
The shared release id/tag is limited to the helper's `[a-z0-9.-]{1,64}`
domain; a source-only tag outside that domain cannot name this binary profile.

### Prepare, verify, select

Work on local branches with a separate DRAFT.json and an owned asset staging
directory. The producer supplies actual digests and byte counts, never values
typed from memory. These steps do not push or publish.

1. Before sealing the guide's digest, run:
   `python3 scripts/release-docs.py render --record DRAFT.json --manifest ASSETS/MANIFEST.toml --out DOCS`.
   This renders QUICKSTART.md and README-download.md. Rendering is preparation,
   not asset verification. A draft source commit may be a placeholder shared
   with the draft manifest until assembly establishes the real commit.
2. Add `--release-docs SITE_CHECKOUT DRAFT.json ASSETS/MANIFEST.toml` to the
   distribution tool's `assemble.py build` invocation. It checks release and
   component pins, fills the README download section without changing the
   build-from-source guide, adds QUICKSTART.md, and records their hashes and
   generator revision in SOURCE-MANIFEST.toml. Neither generated document
   embeds its own hash or its enclosing Git commit. Record the assembled
   source commit in the preview manifest/record, then seal the actual assets
   and SHA256SUMS, including the quickstart and manifest.
3. Run:
   `python3 scripts/release-docs.py stage --record DRAFT.json --assets ASSETS --source PUBLIC_SOURCE_CHECKOUT`.
   It verifies actual asset bytes and the README/guide/source manifest at
   the exact source commit, then imports metadata and that commit's manual
   into `content/releases/<id>/`. It copies no image or runtime identity into
   the site. Replacing an existing release's input bytes is refused.
4. Run `python3 scripts/release-docs.py select --record DRAFT.json`, then
   `scripts/site.sh generate` and `scripts/site.sh check`. Selection archives
   the previous binary record. Current and archived releases get pinned
   pages at `/releases/<id>/`, with their manual and guide; `/try/` uses the
   selected record. The milestone manual keeps its original URLs/provenance.
   Checks compare the full generated instructions and manuals with the record.
5. Review the diff and local preview. The release owner and docs owner inspect
   the staged-file rehearsal: fresh key, documented TCG profile, native
   commands, shutdown and a write/read across reboot. Synthetic metadata
   controls do not establish boot, SSH or persistence. Independent review
   precedes a publication proposal. The owner still decides release and
   publication; GRUB corresponding source and binary notices remain required.
6. After owner-authorized publication, mark documentation state `published`
   and run:
   `python3 scripts/release-docs.py reachable --record content/release.json --out UNIQUE-RECEIPT.json`.
   This streams the exact public URLs, compares sizes/hashes and SHA256SUMS,
   and writes a separate receipt. It changes no state and proves neither
   authenticity nor boot. The independent outsider rehearsal still follows
   the actual published files/instructions.

### Later results, release changes and withdrawal

`documentation.state` is `draft`, `staged`, `published` or `withdrawn`.
Reachability is observed separately. A draft/staged record does not make an
artifact public; a site push is not a deployment or download receipt.

The manifest's qualification and original limits stay fixed. Later evidence
and additional limits can update the site's editorial standing without
rewriting the source tag's instructions. Original limits cannot disappear;
a record cannot claim less than its manifest while presenting it as the
same artifact. Evidence links still require independent inspection.

The release owner selects or withdraws the default. The docs owner updates
the record, generates/checks and corrects claims. For withdrawal, set state
`withdrawn`, record the reason in limits/evidence and retain the pinned pages.
Never retarget earlier assets, silently overwrite their metadata or relabel
an old manual. A later release gets a new identity. Historical captures,
source-only previews and milestone results keep their own scope.

Unmodified upstream licence notices remain in the release manual. The email
check recognizes their public author addresses only on the corresponding
generated manual pages and only for the exact source hashes listed in
`scripts/check.py`. A changed source, another page, another address or an
explicit local rule does not receive that exception.

## Binary-only preview (no source release)

A later corresponding first-party source publication uses the existing
`first_party_source` field: null keeps the original binary-only rendering;
an object names the separate source tag, commit, tree, source-manifest
SHA-256 and original kernel/platform component commits. Component commits
must agree with the sealed binary record. This association does not edit
the original manifest, checksums, quickstart or binary tag, and does not
claim byte-for-byte independent reproduction. Before applying such an
object or the accompanying source-link prose, the steward verifies that
the exact source tag/tree and manifest are public and that source review,
clean-environment build, provenance, licensing and private-material gates
passed. The offline site validator checks structure and local consistency;
it does not prove that the remote source tag exists or that source matches
the released binaries. Those remain publication receipts.

A preview whose release set has no first-party source release, and whose
public tag may differ from the media's release id, uses a separate record:
`content/binary-preview.json` (`absd-binary-preview/1`), with the sealed
`MANIFEST.toml`, `SHA256SUMS` and `QUICKSTART.md` copied byte for byte into
`content/binary-preview/<tag>/`. `content/release.json` stays the
source-release record; its schema and validation are unchanged, and it must
not also select a binary preview.

`binary_preview.py` checks the record against those three files without
re-rendering anything: the SHA256SUMS bytes against `sums_sha256`, every
asset against SHA256SUMS, the manifest (no `source_commit`; id, tag, commits,
signature, qualification, QEMU profile, roles and every asset bound) against
the record, every sealed limitation kept, and QUICKSTART.md's digest against
all three. The guide is only checked to download this record's files from
this tag and to verify them; sections appended before sealing are served as
shipped. The build serves the three files under `/releases/<tag>/` and
renders `/try/`, that page and the status section from the record. The
record's `works` and `not_in_preview` describe the released image, not the
development line. `scripts/test_binary_preview.py` runs the committed inputs
and the refusals.
# Later RC1 notice correction

The optional `notices_correction` metadata names the one reviewed additive
RC1 notices archive. It is separate from `assets`, MANIFEST.toml and
SHA256SUMS; none of those sealed inputs is regenerated. Leave the field
absent or null until the correction is authorized, attached to the binary
release and downloaded with the exact recorded size and digest. The offline
validator checks identity, not remote existence or publication authority.

Source-present pages keep the GRUB/Unifont source and original notices
pointers and the earlier source release. Their about-page wording points
to the source release's actual clean-environment results instead of
inferring that included check scripts passed. Bind the final reviewed
source identity and release text before publishing this metadata; a failed
or superseded source candidate is not a publication input.

## Developer Preview 1 and Developer Preview 2

The human names are `ABSD Developer Preview 1` and `ABSD Developer Preview 2`.
Their immutable tags remain `absd-preview-rc1` and `absd-preview-2`. Set the
optional `display_name` on binary records; known tags must use these exact
names. Headings and the primary Download / Try action use the human name.
Technical tags remain in release URLs, manifests and verification material.
The primary action points to `/releases/<tag>/`, so a saved link retains its
release identity when the selected preview changes.

Retain earlier binary records at `content/binary-preview/<tag>.json` and
keep their three sealed inputs in `content/binary-preview/<tag>/` unchanged.
The loader verifies each retained record with the same manifest, checksum
and guide checks as the selected record. Retained pages are generated at
their original pinned URLs. An identical selected/archive duplicate is
ignored; a conflicting record refuses. Drafts are not historical releases.
Selecting a new preview must never rerender or overwrite an earlier sealed
guide, manifest or checksum file.

Preview 2's producer uses `operator.iso`, `enroll.iso` and `disk.img.xz`;
Preview 1 retains its release-id-prefixed filenames. Both paths retain
exact manifest role, digest, byte-count and SHA256SUMS checks. Preview 2
ships curated matching first-party source at its own binary tag. Its
`first_party_source` association may therefore use `absd-preview-2` too;
Preview 1 keeps its separate `absd-source-rc1` association. Component commits
must agree. A published Preview 2 record requires that matching source
association at its own release tag; a draft can leave it unbound.
This local check does not establish remote publication or
byte-identical reproduction.

The preparation branch selects Preview 2 as `draft` with no source
association. Publish neither that draft nor a staging source commit. After
all source/rehearsal/review gates pass, the steward binds the association to
the final public-history source commit, tree and manifest digest, verifies
the public tag/release and all asset bytes, records the actual publication
date/evidence and changes the record to `published`. Rebuild and rerun all
checks before the existing Pages procedure. Preview 1 and Preview 2 appear
together publicly only after Preview 2 is published. The earlier source
preview and milestone records remain separate.

## Developer Preview 3

The human name is `ABSD Developer Preview 3` and the tag is `absd-preview-3`.
`binary_preview.py` knows the name. Preview 3 is the selected record. Its
sealed inputs, listed below, are in `content/binary-preview/absd-preview-3/`,
copied byte for byte from the release set. Preview 2 is retained at
`content/binary-preview/absd-preview-2.json` with its three inputs unchanged.

Preview 3's download is a kit: the guide starts from four downloaded files,
`SHA256SUMS`, `SHA256SUMS.source`, `QUICKSTART.md` and the kit archive
`absd-preview-3-operator.tar.gz`. The manifest, the media and the helper are
inside the archive. A record describes such a release with a `kit` object:

```json
"kit": {"name": "absd-preview-3-operator.tar.gz", "sums_sha256": "<sha256 of the kit's own SHA256SUMS>"}
```

A kit record's `assets` are every release asset except `SHA256SUMS`: the
three files the outer `SHA256SUMS` lists and the source and notice files
`SHA256SUMS.source` lists. It commits five inputs, not three:

- `SHA256SUMS`, `SHA256SUMS.source` and `QUICKSTART.md`, as downloaded;
- `MANIFEST.toml`, copied out of the verified kit;
- `KIT.SHA256SUMS`, the kit's own `SHA256SUMS`, copied out under that name.

Add `utils_commit` to the record when the kit's manifest names one; the
manifest's release table must then match the record key for key.

The checks on a kit record are the flat release's checks moved to where the
files are. The two outer lists together must equal the record's assets. The
kit's list must contain the manifest, `NOTICES.md`, `absd-try.py` and the same
`QUICKSTART.md`, and the manifest must bind every other kit member. The guide
has no download lines; it must name the four files, check `SHA256SUMS`
against a separately obtained digest before it unpacks anything, and state
the `VERIFIED release=` line for this release. Same-tag source and plain
media names apply to `absd-preview-2` and `absd-preview-3`.

Committed inputs cannot show that the kit archive holds that manifest and
that list. Before selecting a kit record, download the kit and run:

```sh
python3 binary_preview.py kit --record RECORD.json \
    --inputs content/binary-preview/absd-preview-3 --kit absd-preview-3-operator.tar.gz
```

It must print `KIT ARCHIVE MATCHES RECORD AND INPUTS`. It reads the archive
and extracts nothing. Do not edit a sealed input to fit the validator.

The release page prints the digest of `SHA256SUMS` for a kit record, in the
file table and beside the instructions. That page and the release body are
the channel the guide's first command relies on, so publish both with the
same value, taken from the record.

The sequence is Preview 2's: Preview 3 is selected as `draft` with no source
association, and the source association, date and evidence are bound only
after the tag and release are public. Its source tree has no
`docs/PREVIEW2-SOURCE.md`; the release page links that tree's `README.md`
for the build instructions and limits.
