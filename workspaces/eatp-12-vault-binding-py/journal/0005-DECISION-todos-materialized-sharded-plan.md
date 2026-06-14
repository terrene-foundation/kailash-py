---
type: DECISION
slug: todos-materialized-sharded-plan
created: 2026-06-14T08:15:00Z
---

# /todos — sharded plan materialized (17 todos across 6 waves + cross-SDK gate)

`/todos` materialized the revised, must-fix-folded plan (`02-plans/01-architecture-and-waves.md` §4/§8) into `todos/active/00-plan.md`. The plan was already converged through Round-1 `/redteam` (all 9 must-fixes resolved per journal/0004), so the todos are a faithful 1:1 materialization of the converged plan + the verified 54-ID conformance matrix.

## Structure

- **17 implementation/test/spec todos** in 6 dependency-ordered, value-ranked waves (W1-F1/F2/FT/C1/T1 · W2-D1/D2/I1 · W3-C2a/C2b/C3 · W4-B1/B2 · W5-R1/X1 · W6-T2/S1) + **3 cross-SDK gate todos** (XSDK-1/2/3).
- Each todo cites its spec § + the conformance IDs it owns (from `03-conformance-id-matrix.md`), its invariant count (all ≤10), dependencies, and Tier-1/2 tests.
- Build/wire separation honored: D1+D2 (Wave 2) are the audit **producer**; the Wave-3 crypto shards **wire into** the audit chain; the cross-SDK parity gate is the final integration wiring.

## Completeness gate (the redteam)

Mechanical cross-check: all **54 real conformance IDs** are cited in a todo (verified via `grep | comm`). The only two matrix IDs absent from the todos (`N12-CL-06`, `N12-SG-04`) are the documented **non-existent** IDs the matrix flags as numbering gaps — not orphans. The 4 Complete-optional IDs (CL-03, CL-03(c), CL-05, SH-02) are isolated in W5-X1 behind a conformance-level flag.

## Value-anchor

Primary anchor for every shard: **(e) the EATP-12 v1.0 Published normative spec** (user-approved 2026-06-14). The post-Wave-6 cross-SDK gate's anchor: **(d) the user's verbatim 2026-06-14 directive "ensure kailash-rs is on parity with this as well"** (journal/0003).

## Gate

`/todos` is a **structural human gate** (plan approval — what + why, not how + when). STOP for the user to approve the 17-todo sharded plan before `/implement`. The wave-loop inter-wave gates then run autonomously between waves.
