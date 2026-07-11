---
type: DECISION
date: 2026-07-11
author: agent
project: sdk-backlog
topic: /codify — surface third-pass redteam Gate-1 follow-ups into the BUILD→loom proposal
phase: codify
relates_to: 0016-DECISION-redteam-thirdpass-convergence-postv2480
tags: [codify, gate-1, proposal, cross-sdk-inspection, loom-pickup]
---

# DECISION — /codify third-pass Gate-1 follow-up (BUILD→loom)

**Repo class:** BUILD (kailash-py) → Step 7a BUILD→loom via `.claude/.proposals/latest.yaml`.
**Posture:** L5_DELEGATED (un-enrolled solo). **Anchor:** advanced `last_codified` 2026-07-10T17:15Z
→ 2026-07-11T07:36Z.

## Backlog delta (since anchor)

`codify-backlog.mjs`: 34 observations (28 `test_pattern` telemetry — non-actionable; 3 session_*),
1 advisory violation, 11 artifact-commits (all today's redteam/codify work, already captured in
journals + the proposal), 1 pending journal stub. **Net new cascade-valuable item:** the third-pass
redteam (journal/0016) surfaced Gate-1 follow-ups NOT yet in the proposal.

## Action (surfacing-only — no rule/agent/skill edit)

Appended a **GATE-1 FOLLOW-UP** to the cross-sdk-inspection Rule 4d `changes[]` entry (entry 23) in
`latest.yaml` so loom Gate-1 picks it up per-artifact:

1. **cross-sdk-inspection.md 306-line no-named-length-rationale** — real fix = depth-extract the
   DO/DO-NOT examples to the already-referenced guide (restores <200); interim = named rationale at
   Origin (as security.md/git.md do). priority:10/path-scoped → no baseline cost; a BUILD-side
   band-aid is NOT warranted (loom-durable-home decision).
2. **Process consideration (non-blocking)** — journal/0011 showed a cross-repo grant scoped to
   "verify rs#1714 + file the BH5 mirror" led to incidental reads of sibling trackers (rs#1713/1729);
   future cross-repo grants should enumerate the exact trackers (repo-scope-discipline condition-5).

Append-never-overwrite verified: 25 changes[] intact, only entry-23 context extended (strict), status
`pending_review` unchanged, `esperie-enterprise` count unchanged (9). No new rule authored → Trust
Posture Wiring (Step 6b) N/A; no self-referential-codify allowlist file touched (proposal edit only,
Step 6 gate not triggered).

## Advisory violation disposition

`git/commit-message-claim-accuracy` (advisory, 2026-07-11T01:35, prior commit "codify: apply redteam
fixes to handoff-comp…") — NO ACTION: false-positive lexical match; the commit body accurately
described its diff. Documented here per the anchor-advance.

## Why surfacing-only

The two rules were CLEAN across all six third-pass rounds — nothing to fix BUILD-side. Their durable
home is loom (Gate-1). The only loom-actionable residual is the length-rationale, which is a Gate-1
depth-extraction call, not a BUILD edit. Codify's job here is to make sure loom SEES it — done via the
proposal entry, since workspace journals do not cascade to loom.
