---
type: DISCOVERY
date: 2026-07-09
slug: validate-write-surface-against-coordination-on-substrate
relates_to: 0034-DECISION-codify-reconvergence6-certify-coordination-on-conformance
---

# DISCOVERY — validate a command's write surface against the coordination-ON substrate it ships into

Three institutional patterns surfaced in re-convergence #6 that the next session (and any `/redteam`
of a command that writes state) should inherit.

## 1. A passthrough regime hides a whole conformance class

kailash-py ships coordination-OFF: `integrity-guard`, `journal-write-guard`, `signing-mutation-guard`,
and the `codify-lease` gate ALL early-`passthrough()` when `!isCoordinationEnabled`. `/certify` was
validated FIVE times in that regime and every gate its journal writes must clear was dormant — so a
whole class of defects (writes that halt under the enrolled substrate) was structurally invisible.
The suite is DISTRIBUTED into enrolled (coordination-ON) repos, where those gates fire.

**Lesson:** when a command WRITES state and is distributed to repos that may run coordination-ON, the
`/redteam` MUST enumerate **every filesystem/state write × every guard, under coordination-ON**, not
only the passthrough mode the authoring repo happens to run. Verify against the actual hook source
(`integrity-guard.js` watched-subtrees + `findCoveringLease`, `journal-reserve.js::VALID_TYPES`,
`codify-lease.js::MANDATORY_SCOPE`, `validate-bash-command.js::STATE_PATH_RX`). Produce the full
per-write coverage table and run it to COMPLETION each round — the "one sibling gap surfaced per
round" pattern (4 straight rounds here) is the tell that the enumeration was PARTIAL.

## 2. A fix on one execution path implies its sibling paths

Every certify fix had a sibling the first pass missed: pass-path lease → abandon-path lease;
pass-entry type validity → brief-receipt path + deferral type; entry-gate message → failure-mode
message. This is `command-skill-parity` + `security.md` multi-site-kwarg-plumbing generalized to
**"same-surface writes get the same treatment."** When you harden one write, grep for every sibling
write on the same surface and harden all of them in the same shard.

## 3. The code is the authority for a lifecycle claim

The R3→R4 entry-gate error over-constrained certify ("await your enrollment PR merge; staying on your
branch is not enough"). It was corrected only by reading `operator-id.js::resolveIdentity` —
`_readJsonSafe(rosterPath)` reads the WORKING-TREE roster, so the roster row IS visible on the
enrollment branch and certify CAN run there. An artifact that claims you cannot do what the code
permits is a `spec-accuracy` defect. When a lifecycle/ordering claim is uncertain, the enforcement
code — not the artifact's prior prose, not a plausible mental model — is the authority.

## Method note (for the /redteam that finds this class)

The lens that finally closed it (R9) was a dedicated agent producing the EXHAUSTIVE per-write ×
per-guard coverage table with source citations, prompted explicitly to "not stop at the first gap —
enumerate ALL of them." Partial enumeration is why it took 4 rounds; the complete table is what
broke the pattern.
