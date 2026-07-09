---
type: AMENDMENT
slug: reconvergence11-claim-predicate-token-phantom
date: 2026-07-09
workspace: mops-onboarding
phase: 05-codify
verified_id: unenrolled-solo
person_id: jack-hong
display_id: jack-hong
---

# Re-convergence #11 — `/claim` SAME-predicate display-token phantom (`axis-3`) + `glob`/`phase` omissions

## What

Fresh 3-agent parallel adversarial `/redteam` of the #10 state MERGED on main (PRs #1630/#1631).
Surfaced ONE new in-scope MED and dispositioned the out-of-scope adversarial breadth. **CONVERGED**
(R3 + R4 = 2 consecutive clean, 0 CRIT / 0 HIGH).

## The finding (MED, FIXED)

`.claude/commands/claim.md:27` (Step 6 SAME-dispatch) printed the matched predicate as
`(exact / dir-contains / workspace / commit-cohort / axis-3)`. Wired ground truth
`.claude/hooks/lib/adjacency.js::sameReason` returns `predicate: pred` (lines 271/371) where `pred` ∈
`{exact(172), glob(173), dir-contains(183), workspace(186), commit-cohort(202), phase(217-218),
composed-axis-3(235)}`. Three defects: **`axis-3` is a PHANTOM** (code emits `composed-axis-3`, never
bare `axis-3` — the #10 DEFER class), **`glob` OMITTED**, **`phase` OMITTED**. MED — teaches
false/incomplete vocabulary, but resolution paths are predicate-agnostic so no guard dropped / no
misroute. `claim.md` has NO backing skill → single-command drift, no parity pair.

## Fix

Replaced the enumeration with the full wired set + an inline `adjacency.js::sameReason` `predicate`
anchor so future edits re-derive from the wired source. Each literal grep-verified. Routed to loom via
`latest.yaml` (GLOBAL — the coordination suite is loom-synced; every downstream copy carries the
phantom). NOT on the `self-referential-codify.md` Rule 2 allowlist → no mandatory multi-agent gate.

## Out-of-scope dispositions (verified, non-blocking)

- **B-1 `Edit|Write|NotebookEdit` matcher in `multi-operator-coordination-substrate.md`** — BY-DESIGN,
  NOT a defect. The skill describes loom-canonical wiring (confirmed by `artifact-flow.md` in-repo);
  this repo's `settings.json` is the deliberately-stripped un-enrolled subset. Editing it would corrupt
  the loom-canonical description.
- **D1–D4 dangling refs** — pre-existing loom→BUILD-subset artifacts OUTSIDE the onboarding suite;
  targets resolve in loom-canonical (D1/D2/D4) or are a genuine loom-side stale self-ref in a
  deployment-git skill (D3). Surfaced to user as a loom-forest item, not this convergence.
- **LOW** — real operator display-name `jack-hong` in a PUBLIC-shipped skill + tracked journal; a
  scrub-to-`<operator-display-id>` candidate at loom. Surfaced.
- **journal/0038 git-history residual** — standing user-gated history-scrub decision, unchanged.

## Institutional lesson

The "citation must match the wired mechanism" class has now recurred across THREE artifact kinds — a
guard SYMBOL (#9), a canonical journal-TYPE (#10), and a SAME-predicate DISPLAY-TOKEN set (#11). The
durable fix each time: cite the wired source inline as the anchor so the next editor re-derives. An
enumeration drifts in BOTH directions (one phantom ADDED + two literals OMITTED here) — the discipline
is "documented set MUST equal wired return set", not spot-checking listed tokens.

## Receipt

`workspaces/mops-onboarding/04-validate/redteam-2026-07-09-reconvergence11.md` (4 rounds + evidence).
Fix: `.claude/commands/claim.md:27`. Routed: `.claude/.proposals/latest.yaml` (change #18, GLOBAL).
