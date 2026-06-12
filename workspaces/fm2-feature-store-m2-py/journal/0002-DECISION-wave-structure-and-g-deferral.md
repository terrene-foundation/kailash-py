# DECISION — FM2 wave structure (3 waves, 6 build shards) + Surface G deferral

**Date:** 2026-06-12
**Phase:** /todos
**Type:** DECISION

## Decision

Decompose the user-ratified 6-surface scope into **3 dependency-ordered waves** (`wave-loop.md` MUST-1
explicit declaration), inter-wave gate after Waves 1 and 2:

- **Wave 1 (HIGH):** Shard A (`@feature` + public `FeatureGroup`) → Shard E (`FeatureRegistry` +
  version immutability). Union ~12 invariants.
- **Wave 2 (HIGH):** Shard B (`FeatureStore.materialize()`, 7 inv — ceiling) → Shard F (GDPR
  `erase_tenant`). Union ~12 invariants.
- **Wave 3 (MED-HIGH):** Shard C (online-store adapter) → Shard S6 (spec graduation, closes #693).

One surface per shard (each at/near the per-shard invariant ceiling per
`autonomous-execution.md`); shards serial within a wave (dependency-chained, not parallel).

## Rationale

- The surfaces form a dependency chain (A→E→B→{F,C}→spec), so a single parallel wave is impossible;
  grouping by dependency layer keeps each wave's cumulative invariant surface ≤12 (under `wave-loop.md`
  bound-B with the live pytest harness).
- Each surface lands its typed exceptions WITH raise-sites (no orphan stubs); build + wire are separate
  todos per surface (`commands/todos.md`).

## Surface G (DB-side windowed as-of) — DEFERRED with state-anchored value-anchor

G is a **performance optimization**, not correctness — point-in-time as-of already ships (polars
computes the as-of). It is genuinely gated: no DataFlow window/aggregation primitive is exposed without
raw SQL as of **kailash-dataflow 2.11.3** (`01-dataflow-dependency-verification.md` Q4=FALSE, verified
2026-06-12). Re-validate via `git log` on `dataflow/ml/` when DataFlow ships that primitive; building on
raw SQL now = `zero-tolerance.md` Rule 4 violation.

## Risk

- **Cross-package contract drift:** the public `FeatureGroup.materialize()` MUST keep 5-kwarg parity with
  the shipped `ml_feature_source` binding; a signature drift fails the binding at runtime. Mitigated by
  the Shard-A acceptance criterion + the internal `SchemaFeatureGroup` parity reference.
- **Online-store runtime dependency** (Wave 3) — must land in extras + pytest marker same commit.
