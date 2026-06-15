---
type: DECISION
date: 2026-06-15
author: agent
project: issue-1316-eatp08-marker-regime-py
topic: /todos scope decision (3 §5.3 codes out of scope) + red-team-driven revisions
phase: todos
tags: [eatp-08, scope, redteam, todos, conformance]
relates_to: 0001-DISCOVERY-brief-corrections-from-parallel-verification
---

# 0003 — DECISION: /todos scope + red-team revisions

`/todos` produced `todos/active/00-todos.md` from the converged `/analyze` plan. Two
decisions made at this gate, both recorded here before the human-approval STOP.

## Decision 1 — three §5.3 error codes are OUT of #1316 scope

A launch-time grep (`specs-authority.md` Rule 5c) showed FOUR §5.3 codes are NEW (0 files),
not the 2 the plan flagged. `monotonic-upgrade-violation` IS in scope (V6 sub-case i, Shard
3A). The other three — `pre-registry-form-after-sunset` (D2d 2030 sunset),
`chain-ref-canonical-form-mismatch`, `alg-id-strip-detected` (registry-lookup-miss) — are
declared OUT of scope.

**Rationale (spec-anchored):** the required conformance vectors are V1–V7 (Conformant), V7
(Complete), V9 per `02-spec-locked-facts.md` §6; issue #1316 acceptance is "V4–V7 + V9 pass."
None of the three is exercised by any required vector (verified: the canonical vector file has
no such vector, and V6's "alg-id-strip-attack" name maps to monotonic/missing/witness-failure
sub-cases, NOT the `alg-id-strip-detected` code). Per `spec-accuracy.md`, adding enforcers +
vectors for codes with no triggering vector in this issue's scope is speculative.

**Alternative considered:** expand #1316 to enforce the full §5.3 set now (+~1 session: 3
enforcers + 3 vectors). Rejected as default — it delivers no #1316 acceptance criterion. Left
as an explicit gate item for the user to override.

## Decision 2 — Shard 3 split into 3A/3B + 2 added shards (red-team-driven)

An analyst red-team of the todo list returned REVISE (2 HIGH + 3 MED). All findings sound;
all closed in-gate per `autonomous-execution.md` Rule 4 (fix same-class gaps immediately):

- **H1** → Shard 2e: V4/V5/V9 have no named vector (file is `registry`/`non_conformant`-keyed);
  added a coverage-map todo (map-or-author with `--collect-only` receipt).
- **H2** → Shard 5: committed end-to-end resolver-dispatch pipeline regression (the manual T3
  walk is not a CI test); catches the frozen-`D2dWitness`-None-`marker_sig` fake-integration risk.
- **M1** → Shard 2 annotated: only 2a + 2b(ii) parallel with Shard 4; 2c + 2b(iii) gated on 1c.
- **M2** → Shard 3A-d: added the §4.1.3 D2a trust-store-no-prior-v2 test (separate state dim).
- **M3** → Shard 3 split: write-path spans 5 wire-decode consumer modules (`crl`,
  `timestamping`, `messaging/envelope`, `pact/envelopes`, `vault/backup`), so 3B carries its
  own budget and pins the chokepoint at shard start (not deferred to `/implement`).
- **L3** → G3-pub: public-surface shape (3 new `D2dWitness` fields + new code constant + CHANGELOG).

Result: 6 implementation shards (1, 4, 2, 3A, 3B, 5) across 2 waves, ~2 sessions. Scope
decisions L1 (the 3 OUT-of-scope codes) and L2 (build/wire split) confirmed sound by the red-team.

## For Discussion

1. **Counterfactual:** if a future EATP-08 erratum adds a required vector for
   `alg-id-strip-detected`, does the OUT-of-scope call here create a silent gap, or does the
   vector-driven conformance model (a new vector → a new shard) catch it by construction?
2. **Data:** the write-path chokepoint (3B-a) is unproven to be a single site — the 5
   consumers all DECODE; the v2-first-emission RECORD site may be one verify chokepoint or
   distributed. Is splitting 3B with a "pin-or-re-shard" gate the right hedge, or should the
   chokepoint be grep-pinned before approval rather than at shard start?
3. **Scope:** is "V4–V7 + V9" the complete acceptance bar, or does cross-SDK byte-parity with
   kailash-rs ISS-33 implicitly require any of the three OUT-of-scope codes that rs may enforce?
