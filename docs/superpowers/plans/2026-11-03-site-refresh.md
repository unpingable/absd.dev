# Paired Site Refresh Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement the tasks.

**Goal:** Give Home/About clearer copy and the static site a subtle graph-paper identity.

**Architecture:** Retain the existing generator, release records and publishing path. Independent CSS and prose lanes share an isolated branch; the parent handles combined verification and release-contract reference changes.

**Tech Stack:** Static HTML, CSS, Python generator/checks, existing headless Chrome.

**Spec:** ../specs/2026-11-03-site-refresh-design.md, approved by the owner on 2026-11-03.

## Global Constraints

- Preserve system fonts, single column, automatic themes, no JavaScript, external resources or animation.
- Keep text, code and evidence tables on plain backgrounds; suppress grid in print and forced colors.
- Preserve exact release/source identities, sealed records, meaningful limitations, evidence links and AI/no-human-audit disclosure.
- No push or publication. Owner approval follows the concrete reviewed result.
- User requested two paired lanes; use concurrent CSS/prose work on disjoint files, then one combined independent review.

## Review Focus

- At narrow widths, header framing must wrap without document overflow.
- In dark mode, foreground and label colors must remain readable.
- Printing and forced colors must remove decoration without hiding content.
- Current RC1 must remain distinct from historical captures and ongoing development.
- Source-only fixture output must retain useful instructions when no binary release is selected.

### Task 1: Visual lane

**Files:** src/static/style.css.

- [x] Add cool, theme-specific CSS graph-paper margins and a framed wordmark; retain opaque reading surfaces.
- [x] Suppress decoration for print and forced colors; preserve focus indication.
- [x] Verify generated output at 360/768/1280 widths in light/dark; inspect print and forced colors separately.

### Task 2: Editorial lane

**Files:** src/pages/index.html, src/pages/about/index.html.

- [x] Lead with useful capabilities, the existing try path and limits; shorten history into precise links.
- [x] Preserve anchors, exact capture provenance, source placeholders, licensing and review disclosures.
- [x] Correct About's obsolete image availability statement. Distinguish published releases from development.

### Task 3: Integration and evidence

**Files:** build.py only if needed for release-aware entry copy; scripts/testdata/schema1-rendering-v1.json only for reviewed rendering refresh; README.md/PUBLISHING.md where changed operator workflow needs explanation.

- [x] Run generation and existing checks. For intentional template/CSS changes, refresh only the changed source-only fixture hashes and preserve the record and file set; document exact differences.
- [x] Capture before/after screenshots with the existing helper; inspect focus, print, forced colors and all-page overflow.
- [x] Independently review copy, CSS, screenshots and fixture delta. No new unit tests for reversible visual/prose changes; existing behavioral release checks remain binding.
- [x] Commit the reviewed change and record immutable lane completion, branch, evidence and publication status. Keep a runnable client-accessible review artifact through existing SSH/SFTP; do not advertise a crow-local URL.

## Result

Implemented and independently reviewed. Generation, 30-page validation, content
checks and 39 tests passed. Browser checks passed at 360/768/1280 in both
themes, including keyboard navigation and disclosure, print and forced colors.
Before/after Home and Design screenshots received a separate readability review.
Release records, sealed inputs, captures and generator logic are unchanged.
The rendering reference changed only for Home, About and the stylesheet.
Publication remains pending the owner decision.
