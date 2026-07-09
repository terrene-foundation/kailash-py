---
type: AMENDMENT
date: 2026-07-09
slug: reconvergence7-must3-readwrite-accuracy-f2-refutation
relates_to: 0034-DECISION-codify-reconvergence6-certify-coordination-on-conformance
---

# AMENDMENT — re-convergence #7 closes the #6 outstanding ledger (F1 fixed, F2 refuted)

Re-convergence #6 (journal/0034) deferred two items as non-blocking LOWs "noted for the owner /
a future sweep." This session (`/autonomize` + `/redteam`, 7 rounds, 18 adversarial agent-passes)
took both to disposition. Full report:
`workspaces/mops-onboarding/04-validate/redteam-2026-07-09-reconvergence7.md`.

## F1 — `enrollment-operations.md` MUST-3 wording (FIXED)

MUST-3 read categorically ("no inline `node -e` for watched-state mutation"), which falsely
flagged `/certify` Step 2's SAFE inline `reserveJournalSlotSigned(...)` call. Ground-truth
verification of the guard (`detectStateFileMutation` + `STATE_PATH_RX`) established the real
invariant: the guard fires ONLY on a `STATE_PATH_RX` literal on the command line, and it is
**read/write-AGNOSTIC (a path-presence detector, not mutation-aware)**. MUST-3 now states that
precisely: script-by-path for authored mutations; a delegated **signed-emit** helper
(`reserveJournalSlotSigned` / `emitSignedRecord`, routing through `coc-emit.js::emitSignedRecord`
per `multi-operator-coordination.md` MUST-1) permitted inline; a raw-`fs` wrapper / concat-path /
arg-supplied `appendStamped` all BLOCKED. The same read/write-agnostic accuracy was propagated to
the cross-referenced depth-file `skills/45-genesis-bootstrap/SKILL.md` (four write-only-framing
instances corrected) and a phantom whoami.md cross-reference was corrected.

## F2 — claim/release-claim/claims helper citations (REFUTED — no edit)

The proposed "align to `coc-emit`/`coc-append`" is refuted by the runtime: `emitSignedRecord`
serves no claim/release/reap record; the actual claim-writer `adjacency-leasecheck.js::autoClaim`

- `reap-ceremony.js` still use `coc-sign.js::sign` + `transport-filesystem.js`; `coc-append.js` is
  the observations/violations helper. The commands are ACCURATE to the code; editing them would
  introduce a NEW command↔code divergence (`spec-accuracy` per journal/0035 §3). Disposition: leave.

## State + receipts

- 2 working-tree files edited (`rules/enrollment-operations.md`, `skills/45-genesis-bootstrap/SKILL.md`),
  uncommitted — BUILD-repo commit gate; awaiting `/codify` landing (`codify/esperie-2026-07-09` →
  PR → admin-merge) + a BUILD→loom proposal for cross-SDK distribution.
- Convergence: clean R5 (3 agents) + clean R7 (reviewer + security), bracketing a single fixed LOW
  at R6; every guard-mechanics claim + cross-reference ground-truth-verified.
- Distributable invariant GREEN throughout (committed roster PLACEHOLDER / 0 enforcement hooks in
  committed settings.json / probe-phase-guard present / disclosure scan exit 0).

## Accepted non-blocking (carried)

- MUST-3 over-density — the SAFE-helper qualification depth is a candidate for extraction to
  `skills/45-genesis-bootstrap` in the canonical loom pass; path-scoped rule → no baseline cost.
