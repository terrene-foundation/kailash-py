---
type: DECISION
slug: plan-revision-must-fix-fold
created: 2026-06-14T07:30:00Z
---

# Plan Revision — Round-1 redteam must-fix fold (the /todos gate)

Closes the fresh-session gate recorded in `.session-notes` and `04-validate/01-redteam-analysis-plan.md`: the 5 remaining Round-1 must-fixes (CRIT-2, CRIT-3, HIGH-2, HIGH-3, HIGH-5) are folded into the plan. All were plan-structure fixes — no external blockers, no code, autonomous execution-gate work per `rules/autonomous-execution.md` (analysis/plan quality is an execution gate; `/todos` plan-approval is the next structural human gate).

## What changed

1. **CRIT-2 — error-taxonomy foundation shard.** Added shard **FT** to Wave 1: a closed `N12FT01Error` enum (the ~25 typed codes, single source of truth), the wrapper-exception→typed-code map, and FT-02 (8-step restore gate order) + FT-03 (write-path gate order) as pure-function **skeletons**. C3 wires FT-02; C2b/R1 wire FT-03. No later shard re-defines codes.

2. **CRIT-3 — C2 split.** C2 → **C2a** (commitment registry + recompute-under-recorded-alg + 3-way code discrimination + CB-03 foreign-shard) and **C2b** (recommit additive + retire + FT-03 wiring + EATP-08 sunset). Each now ≤10 invariants.

3. **HIGH-2 — dependency inversion fixed.** The audit substrate (**D1 dispatcher adapter + D2 envelope schema**) moved from Wave 4 to **Wave 2**, ahead of the Wave-3 crypto shards that consume the audit chain (CB-03 sources `shard_commitments` from the distribution anchor; C3 derives current-gen from the audited chain). Also surfaced + closed a latent edge HIGH-2's logic implied: D2's anchor _schema_ is needed by every anchor-writing crypto shard, so landing the full audit substrate (D1+D2) in Wave 2 closes it. **RT-05 (restore→D6 trigger) reassigned from R1 (rotation) to C3 (restore path)** — it fires on restore, not rotation, which lets CL-04 (Wave 4 cooling-off) cleanly consume the Wave-3 trigger.

4. **HIGH-3 — non-ASCII sentinel deferred.** Wave 1 (C1 + T1) authors **ASCII byte-pins only**. The non-ASCII sentinel (`ensure_ascii=False` per CRIT-1) moves to the post-Wave-6 cross-SDK gate — it is calendar-bound on kailash-rs reconciliation, value-anchored on the user's 2026-06-14 "ensure kailash-rs parity" directive.

5. **HIGH-5 — per-N12-ID matrix.** New file `02-plans/03-conformance-id-matrix.md`: 54 rows, one per conformance ID + sub-clause (range-notation BLOCKED). All **50 Conformant-mandatory** IDs have a primary owner shard; the **4 Complete-optional** (CL-03, CL-03(c), CL-05, SH-02) → X1. The redteam's named orphans (CRY-PIN, TH-01, CRY-SC, IN-03, PP-01, RT-01/02, CL-04) are all closed. A producer-before-consumer dependency-edge audit accompanies the matrix.

## Evidence / method

- Per-ID glosses + conformance levels re-derived directly from `briefs/eatp-12-v1.0-spec.md` (read-only extraction; the 4 Complete-optional IDs each carry explicit "OPTIONAL at Conformant / REQUIRED at Complete" spec text and are exercised only by V8).
- ID namespace enumerated mechanically: 54 unique `N12-*` IDs incl. lettered sub-clauses. Verified gaps: no `N12-SG-04`, no `N12-CL-06`.

## Disposition

CRIT-1/HIGH-1/HIGH-6 (resolved at redteam time) + CRIT-2/3 + HIGH-2/3/5 (folded here) = all 9 must-fix items closed. **`/todos` is unblocked.** Should-fix items (HIGH-4 unpinned cross-SDK hash domains, MED-1..5) land at `/todos` per the redteam disposition; HIGH-4 joins the post-Wave-6 parity gate alongside the non-ASCII sentinel.

Artifacts: `02-plans/01-architecture-and-waves.md` §4 (revised waves) + §8 (this fold) + `02-plans/03-conformance-id-matrix.md`.
