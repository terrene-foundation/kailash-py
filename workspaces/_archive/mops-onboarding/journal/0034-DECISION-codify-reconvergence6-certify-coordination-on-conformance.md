---
type: DECISION
date: 2026-07-09
slug: codify-reconvergence6-certify-coordination-on-conformance
relates_to: 0033-DECISION-codify-command-skill-parity-rule
---

# DECISION — /codify re-convergence #6: land certify coordination-ON write-surface conformance + BUILD→loom proposal

Re-convergence #6 (`/autonomize` + `/redteam`, 10 rounds, ~30 parallel adversarial agents; converged
0 CRIT/0 HIGH/0 MED across 2 consecutive clean rounds R9+R10) is codified and landed. Full report:
`workspaces/mops-onboarding/04-validate/redteam-2026-07-09-reconvergence6.md`.

## What was landed (9 artifact files, this codify branch `codify/esperie-2026-07-09`)

`commands/{certify,claim,ecosystem-init,onboard,posture}.md` +
`skills/{41-onboard,42-certify,43-ecosystem-init,45-genesis-bootstrap}/SKILL.md`.

**The headline — a PRE-EXISTING gap #1–#5 all missed.** kailash-py ships coordination-OFF, so
`integrity-guard` / `journal-write-guard` / `codify-lease` passthrough. Every prior convergence
validated `/certify` in that passthrough regime and never exercised the **coordination-ON (enrolled)
substrate the artifact ships into**. Walking the certify write surface end-to-end (R5–R8) found +
fixed, to source-verified full coverage of all 8 certify writes:

- Pass + deferral `journal/` entries now acquire/release a covering **codify-lease** on a
  `codify/<id>-<date>` branch (skill Steps 1.5/5), scope `["journal/"]` (DIRECTORY scope load-bearing:
  `findCoveringLease` matches trailing-slash-dir prefix; a bare filename does not; `MANDATORY_SCOPE`
  excludes `journal/`).
- Deferral entry type `DEFER`→`DECISION` + `topic: certify-defer-<id>` (`DEFER` ∉
  `journal-reserve.js::VALID_TYPES` → old contract failed the reservation closed).
- Brief `.pending/` receipts moved OUT of `journal/` → `workspaces/_certify/.pending/`
  (`integrity-guard` watches `^workspaces/<name>/journal/`).
- Entry gate corrected to the code-accurate model (`resolveIdentity` reads the WORKING-TREE roster →
  certify runs on the enrollment branch OR after merge; registration precedes certification;
  certification gates `/claim`). An R3 over-constraint ("await merge, branch not enough") was reversed
  in R4 with source evidence.

Plus R1–R4 command↔skill + lifecycle fixes: certify Phase-0 (`validate-cert-bank.mjs` + consent STOP)
added to the skill (a security-scan drop on the skill-followed path); claim.md SAME-conflict dead-end
(nonexistent `/lease-override` + a `/release-claim` invocation its own bind-check rejects) →
sibling-self-release/reap; onboard + certify just-enrolled PR-pending branch; genesis double-run
idempotency; posture.md self-contradiction; claim.md phantom test citation.

## Routing (COC-artifact change → BUILD→loom, NOT cross-SDK issue)

Per `artifact-flow.md` + the #5 precedent (journal/0031): these are COC-artifact changes → the
BUILD→loom proposal (`latest.yaml`, entry `onboarding-suite-certify-coordination-on-conformance`,
flagged security-relevant + highest cross-SDK priority) IS the propagation path. loom Gate-1 +
`/sync-to-use` redistribute the corrected suite to the Rust SDK + downstream. Do NOT file a
cross-SDK BUILD issue (wrong lane).

## Deliberately NOT fixed (out of scope — next session, per user directive)

- `enrollment-operations.md` MUST-3 categorical wording vs certify Step-2 safe-inline `node -e`
  (the fix is to tighten MUST-3 to "…on the command line…" — a self-referential rule refinement).
- `claim`/`release-claim`/`claims` M1-era coordination-log writes cite `coc-sign`+transport not
  `coc-append`/`coc-emit` (helper-naming drift, substantively MUST-1-compliant).

## Distributable invariant — re-verified GREEN (committed HEAD + after every edit)

roster PLACEHOLDER-owner/0000000/gen 0 · 0/6 coordination-enforcement hooks in committed
settings.json · probe-phase-guard=1 · 0 esperie tokens in committed roster · disclosure exit 0
(1559 files). The 9 edits are all prose in `commands/` + `skills/`; none touch settings.json, roster,
or posture. The repo continues to ship un-enrolled, distributable-safe.
