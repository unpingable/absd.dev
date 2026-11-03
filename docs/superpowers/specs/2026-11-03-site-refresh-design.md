# Paired site refresh

Design proposal for absd.dev #2 and the public-facing portion of
absd-coord #75, through #32's existing publication workflow.

## Intent

Help a first-time reader understand what ABSD does, try the published RC1
preview, and find its limits. Give the existing static site a restrained
1980s console packaging identity. This work can ship independently of
ongoing operating-system engineering, after the existing publication review.

## Approach

Recommended: CSS-only graph-paper margins, a small geometric wordmark frame,
and a focused Home/About rewrite. Warm paper and cool blue-gray lines in
light mode; charcoal and quiet cool lines in dark mode. Keep the text column,
code, evidence tables and labels on opaque plain backgrounds. Suppress grid
decoration in print and forced colors. Preserve system fonts, the single
column, automatic theme choice, keyboard navigation and no animation,
JavaScript or external resources.

A header-only grid would be smaller but less visible on desktop. A broader
layout redesign would take longer and work against the requested text-first
site. The recommended approach is a proposal pending owner response.

## Editorial lane

Lead Home with concrete capabilities, the existing /try/ path and material
limitations. Put detailed historical qualification summaries behind their
existing status/evidence links. Retain source/release identities, labels,
evidence links and captured transcript provenance. Keep all existing anchors
when practical. On About, correct the obsolete claim that images are not
offered and explain current release versus ongoing development in plain
language. Preserve AI authorship/review disclosure, the absence of independent
human audit, licensing details and consequential cautions.

Do not edit sealed manifests, quickstarts, historical records, accepted
results or the selected release. Do not claim newer private development is
part of RC1. The full source-backed architecture reference and internal
handoff/roadmap rewrite in #75 are outside this first public-site delivery.

## Verification and delivery

Use the existing generator and site checks. Capture before/after Home and
Design at desktop and narrow widths in light and dark modes. Inspect wrapping,
horizontal scrolling, focus, contrast, print and theme behavior. A separate
reader reviews final copy and screenshots for readability and truthful claims.
Record source identities and verification limits beside the screenshots.

Work in lane/absd-site-refresh-20261103, based on public main e013ce7, in the
existing workspace worktree convention. The old absd.dev checkout points to
private history and is not the source baseline. No push, publication or
release nomination is part of implementation approval; prepare the reviewed
update first and request the owner's publication decision on the concrete result.

The responsible owner for this worktree and its small evidence set is this
Codex lane. Retire disposable renders after review/publication evidence is
retained; preserve unique source commits and replay instructions. No VM or
large build is required. Initial storage observation: root 178,611,929,088
bytes free; /data 399,148,912,640 bytes free; inodes ample on both.
