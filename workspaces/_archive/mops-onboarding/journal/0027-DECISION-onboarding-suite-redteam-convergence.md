---
type: DECISION
date: 2026-07-08
slug: onboarding-suite-redteam-convergence
---

# DECISION — Phase-1 onboarding suite re-validated to redteam convergence

## What

Ran `/redteam` to convergence on the current on-disk **Phase-1 onboarding COC
artifact suite** (agent `coc-onboarding-specialist` + rule `enrollment-operations`

- skills `41-onboard`/`43-ecosystem-init`/`44-enroll`/`45-genesis-bootstrap` +
  commands `ecosystem-init`/`enroll`/`onboard`/`whoami`).

## Why now

The suite was built + redteam-converged 2026-06-24 (commit `17e01f901`,
journal/0001), then **modified by the 2026-07-04 loom Gate-2 sync**
(commit `093737b90`: rule +42 lines, skill +18, agent +2). The synced state had
not been adversarially re-validated in-repo. Highest user-anchored in-scope value
per `00-PROGRAM.md` ("teams are seriously struggling" with genesis onboarding).

## Method

Self-referential-codify multi-agent redteam (reviewer + security-reviewer +
cc-architect), posture L5_DELEGATED, each round verifying every claim against
ground-truth guard/helper source (not prose). Four rounds:

| Round | reviewer    | security | cc-architect | Action                              |
| ----- | ----------- | -------- | ------------ | ----------------------------------- |
| R1    | 0C/0H/1M/4L | 0/0/0/2L | 0/0/3M/4L    | fixed accuracy findings             |
| R2    | 0/0/1M/2L   | CLEAN    | CLEAN        | fixed (incl. same-class gap)        |
| R3    | CLEAN       | CLEAN    | 0/0/0/1L     | fixed self-introduced polish        |
| R4    | CLEAN       | CLEAN    | CLEAN        | **2 consecutive clean → converged** |

The convergence gate (0 CRIT / 0 HIGH) held from R1. The highest-risk claim —
the `detectStateFileMutation` inline-interpreter blocking scope — verified
accurate and undisturbed throughout.

## GAP — the loom-synced suite carried accuracy drift

Findings were behavioral-accuracy drift (mislead the exact struggling-operator
audience the suite serves), fixed as working-tree edits:

- **Wrong roster path** — `onboard.md` failure-mode checked
  `.claude/learning/operators.roster.json`; real path is `.claude/operators.roster.json`
  (`operator-id.js::ROSTER_REL`).
- **False `permissions.deny` claim** — `enrollment-operations.md` MUST-1 asserted the
  roster's Edit/Write path is `permissions.deny`'d; it is not (only `posture.json` +
  `violations.jsonl` are). Enforcement is `integrity-guard.js` codify-branch/lease gate
  - `validate-bash-command.js` STATE_PATH_RX.
- **Inaccurate guard framing** — `whoami.md` described the lexical guard as recognizing a
  "licensed canonical writer"; the guard has no writer allowlist — it scans the command
  STRING, and `node <file>` passes only because the path is off the scanned line.
- **Missing `operators.roster.README.md`** — referenced by 4 load-bearing files
  (whoami.md, the schema, roster-schema-validate.js, fold-genesis-anchor.js) but absent.
  Created from ground truth (`PLACEHOLDER-` convention + `isUnenrolled` predicate).
- **Same-class latent gap (surfaced by the fix, fixed in-session per autonomous-execution
  MUST-4):** `multi-operator-coordination.md:78` carried the identical false
  `permissions.deny` claim for `coordination-log.jsonl` + `operators.roster.json`.
- Plus LOW polish: garbled backtick span, `main`→`origin/main` base consistency,
  `resolveIdentity` return-shape, `keyType` citation drift, phantom `/doctor`, stale
  self-cited line count, gate-2 passthrough caveat.

## Disposition

11 fixes landed as **working-tree edits** (BUILD repo — commits stay with the owner).
The multi-agent redteam-to-convergence satisfies the `self-referential-codify.md`
gate for these allowlisted surfaces (rule + skills + coordination rule). Recommended
next step: commit + `/codify` to propose the accuracy corrections upstream to loom
(BUILD→loom→sync-back), so every downstream consumer of the synced suite gets the
corrected mechanics.

## Known-dispositioned (not a defect)

`whoami.md` is 152 lines (>150 `cc-artifacts.md` Rule 3 cap) — pre-existing,
procedural-exception-eligible (4-ceremony runbook); the named-rationale is recorded
in the codify receipt that lands the change.
