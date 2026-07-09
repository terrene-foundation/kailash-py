---
type: AMENDMENT
slug: reconvergence12-illustrative-enumeration-hedge
date: 2026-07-09
workspace: mops-onboarding
phase: 05-codify
verified_id: unenrolled-solo
person_id: jack-hong
display_id: jack-hong
relates_to: 0042-AMENDMENT-reconvergence11-claim-predicate-token-phantom
---

# Re-convergence #12 — illustrative-enumeration hedge (positive-allowlist) + first command↔skill-parity audit CLEAN

## What

Fresh 3-agent parallel adversarial `/redteam` of the #11 state MERGED on main (PRs #1632/#1633/#1634),
adding the first audit of the whole onboarding suite against the NEW `command-skill-parity.md` rule
(landed 2026-07-08, `882c68f92`), whose Origin IS this suite. **CONVERGED** (R3 + R4 = 2 consecutive
clean, 0 CRIT / 0 HIGH). Receipt: `04-validate/redteam-2026-07-09-reconvergence12.md`.

## Two clean confirmations + one hardening

1. **command↔skill parity (new rule) — CLEAN.** 5 pairs × 5 shared-step axes, 0 contradictions. The
   `/certify` `probe-phase-guard` lockfile lifecycle (the rule's Origin defect) HOLDS: `certify.md`
   § "Phase B — Probe" `rm` at "Probe exit (Phase C complete OR abandoned mid-gate)" byte-aligns with
   `42-certify/SKILL.md` "the lockfile PERSISTS through Phase C". Both Origin-cited sibling print-strings
   (enroll B3, ecosystem C5) are byte-identical. The #5 codify that authored the rule already generalized
   the fix across the suite.
2. **citation-vs-wired class (#9/#10/#11) — CLEAN, no phantoms.** Every completeness enumeration
   re-derives EXACT: `claim.md` SAME-predicate set vs `adjacency.js::sameReason` (7, #11 fix holds);
   `VALID_TYPES` vs `journal-reserve.js` (DEFER stays refuted, #10); `probe-phase-guard` matcher vs
   `settings.json` (#9). First round since #9 with zero phantom-added instances.
3. **3 LOW/MED illustrative-enumeration gaps HARDENED** (positive-allowlist per the #11 lesson): the
   OMISSION subclass in ILLUSTRATIVE (not completeness) lists — partial-and-unhedged where the wired set
   is larger.

## The fix (3 edits, source-verified, GLOBAL → routed to loom)

- `45-genesis-bootstrap/SKILL.md` watched-paths list → completed to `documented == wired` (the full
  `DIRECT` set at `integrity-guard.js::DIRECT` — 8 files + 3 subtree predicates) + inline
  "the wired `DIRECT` set … at `integrity-guard.js` is authoritative" anchor.
- `43-ecosystem-init/SKILL.md` `STATE_PATH_RX` list → added "(among others; the wired `STATE_PATH_RX`
  at `validate-bash-command.js` is authoritative)" — matching the ALREADY-HEDGED sibling at `45` (the
  genuine unhedged-vs-hedged-sibling inconsistency).
- `45-genesis-bootstrap/SKILL.md` `runEnrollmentCeremony` return → added `record?` (success path per
  `genesis-ceremony.js` `{ok:true, record} | {ok:false, error, reason, step}`).

`43`/`45` are NOT on the `self-referential-codify.md` Rule 2 allowlist (Skills allowlist enumerates
`spec-compliance`/`command-authoring`/`skill-authoring`/`hook-authoring`/`sweep`/`32-trust-posture`/
`30-claude-code-patterns`/`12-testing-strategies/probe-driven-verification`; `enrollment-operations.md`
explicitly OMITS `45-genesis-bootstrap` as a runbook) → no mandatory multi-agent gate. Loom-synced, so
routed to loom via `.claude/.proposals/latest.yaml` (GLOBAL) — every downstream copy carries the gaps.

## Lesson (extends 0037–0042 recurring-class chain)

The recurring "citation must match the wired mechanism" class has a subclass distinction that #12 makes
explicit: a COMPLETENESS claim MUST equal the wired set; an ILLUSTRATIVE list MUST either equal it OR
hedge ("e.g. … (among others)") — and BOTH dispositions end at the same durable fix: **cite the wired
source inline as authoritative so the next editor re-derives instead of trusting partial prose.** The
defect in #12 was never a phantom (every listed token was real); it was a partial list presented
UNHEDGED where a sibling already carried the "(among others)" convention. Positive-allowlist symmetry:
the fix propagates the sibling's convention to the drifted enumerations, plus the wired-source anchor.
