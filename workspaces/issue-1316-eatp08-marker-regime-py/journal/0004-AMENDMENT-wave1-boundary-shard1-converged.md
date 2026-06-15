---
type: AMENDMENT
date: 2026-06-15
author: agent
project: issue-1316-eatp08-marker-regime-py
topic: Wave-1 boundary — Shard 1 (D2c signed-marker) converged + merged; inter-wave gate G1-G4
phase: implement
tags: [eatp-08, wave-loop, shard-1, convergence, d2c]
relates_to: 0003-DECISION-todos-scope-and-redteam-revisions
---

# 0004 — AMENDMENT: Wave-1 boundary (Shard 1 converged)

Wave-loop inter-wave gate (`wave-loop.md` MUST-2) for Wave 1 = Shard 1. Durable receipts:

- **G1 — redteam to convergence.** The `/implement` MUST gate ran reviewer +
  security-reviewer as two independent adversarial agents on the merged diff. Both APPROVE,
  zero CRIT/HIGH/MED. security-reviewer verified fail-closed across all 5 checks +
  the V6(iii) backdating defence + constant-time Ed25519 + tz-safe expiry + complete
  multi-site plumbing. reviewer: 6/6 mechanical sweeps green, 66 regression tests pass.
  For a single-shard wave this two-agent clean verdict IS the convergence evidence.
- **Receipts:** PR #1324 (merge commit `167e8c473`, base `686696be8`); CI 29/29 green;
  admin-merged per owner workflow.

## Claimed-vs-found delta (G2 learning)

The plan's brief-correction #5 estimated "the 5 wire-decode consumers only FORWARD `witness=`
unchanged; behavioral change contained in 2 functions." Reality at /implement: making the
marker signed-not-remembered required **threading a new `verifier_keys` kwarg through all 4
D2dWitness consumers** (`crl`, `timestamping` ×2 from_dict, `messaging/envelope`,
`pact/envelopes`) per `security.md` Multi-Site Kwarg Plumbing — the verifier key MUST reach
the gate, and a sibling left on the unqualified signature would ship the exact downgrade the
shard closes. Not a scope error in the plan (the gate logic stayed ~80 LOC, well within
budget) — but the consumer surface was 4 files, not "unchanged forwarding." Wave-2 shards
inherit the now-threaded signature.

`vault/backup.py` was correctly EXCLUDED — its `witness` is a `CeremonyWitness` (EATP-12),
a different concept, not a D2dWitness consumer.

## G3 — spec + CHANGELOG (first-instance update)

- `specs/trust-crypto.md` §32.3 rewritten from the old trusted-witness gate to the D2c
  signed-marker contract (5 checks, D2dVerifierKeys, signed core {principal, first_seen});
  §32.4 notes verifier_keys threading. All citations re-pinned to current line numbers
  (D2dVerifierKeys:172, D2dWitness:213, gate:316, is_pre_registry_form:486) — resolve
  against main per `spec-accuracy.md` Rule 1.
- `CHANGELOG.md` [Unreleased] § Added — the public-surface change (G3-pub).

## G4 — re-validation

Wave-2 value-anchor (EATP-08 §4 conformance) holds. Scope decision (3 §5.3 codes OUT) holds
— no new evidence. Wave-2 shards (4, 2, 3A, 3B, 5) branch from updated main.
