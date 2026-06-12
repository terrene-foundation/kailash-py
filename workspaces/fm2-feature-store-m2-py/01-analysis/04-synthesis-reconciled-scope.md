# 04 — Synthesis: Reconciled Scope (3-agent cross-check)

Three parallel analysis agents ran. Two reached the central question from different
directions and **disagreed**; the disagreement resolves in favor of the ground-truth source
read.

## The disagreement and its resolution

- **Agent 03 (scope reconciliation)** inferred from `ml-feature-store.md §11.2` ("deferred until
  DataFlow ships a materialisation primitive") + the `(draft)` status of `dataflow-ml-integration.md`
  that `@feature`/`materialize` are blocked, and recommended re-scoping #1302 to "graduate the spec
  - ADR everything" (~1 session).
- **Agent 01 (DataFlow dependency, source check)** read actual kailash-dataflow 2.11.3 source and
  found `dataflow.transform` / `ml_feature_source` / `hash` **all ship** (at `dataflow/ml/_*.py`, not
  the stale flat paths the specs cite). `@feature` + `materialize()` are **buildable now** — pure
  kailash-ml authoring work; the compute+persist logic is the caller's concern via `@db.model`/`express`.
- **Agent 02 (surface design, ml-specialist)** independently confirmed agent 01: only **Surface G
  (DB-side windowed as-of)** is DataFlow-gated; surfaces A–F are buildable now.

**Resolution:** agent 03's premise was the **stale `§11.2` disposition**. The source read wins.
`ml-feature-store.md §11.2` is itself a spec-accuracy defect (claims a DataFlow primitive is
unshipped when it shipped by 2.11.3). This is the "stale state-claim" trap — a primitive that
already landed, invalidating a deferral premise. → see `journal/0001`.

Agent 03 retains TWO valid points: (1) the spec-correction/graduation work IS needed (the specs
are stale + `(draft)`), as part of the workstream not a substitute for it; (2) §11.1 FeatureGroup
"only if a downstream Engine surfaces a need" is a genuine judgment condition — **now met**, because
the M2 authoring surface (`@feature`/`materialize`) itself needs a public `FeatureGroup` as its
authoring object (agent 02 designed it as exactly that).

## Reconciled surface inventory (agent 02 design + agent 01 gating)

| Surface                                                                                                   | Inv         | Buildable now?                                   | Disposition                                                                                                                        |
| --------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| D. M2 typed exceptions (with raise-sites; reuse existing `ErasureRefusedError`/`CrossTenantLineageError`) | 3           | YES                                              | BUILD (lands with surfaces)                                                                                                        |
| A. `@feature` decorator + public `FeatureGroup`                                                           | 6           | YES (`dataflow.transform` ships)                 | BUILD                                                                                                                              |
| E. `FeatureRegistry` + version immutability (`UNIQUE(tenant,name,version)` via `@db.model`)               | 6           | YES                                              | BUILD                                                                                                                              |
| B. `FeatureStore.materialize()` write-through (lineage via `dataflow.hash`)                               | 7 (ceiling) | YES                                              | BUILD (own shard)                                                                                                                  |
| F. FeatureStore-layer GDPR `erase_tenant` (mirrors `tracking/erasure.py`)                                 | 5           | YES                                              | BUILD                                                                                                                              |
| C. online-store adapter                                                                                   | 5           | YES (feasible)                                   | **JUDGMENT: build now vs ADR-defer** (§11.4 "defer"; issue pre-hedged "or ADR")                                                    |
| G. DB-side windowed as-of                                                                                 | 4           | NO — needs DataFlow window/aggregation primitive | **DEFER** (perf optimization; correctness already works in polars per §4 MUST-5)                                                   |
| —                                                                                                         | —           | —                                                | Spec graduation: correct stale §11.2; graduate `dataflow-ml-integration.md`, fix citation paths, correct §2.5/§3 → **closes #693** |

## Recommended scope

**Build 5 core surfaces (D, A, E, B, F) + spec graduation; ADR-defer C (online-store) and G
(DB-side as-of).** Rationale:

- D/A/E/B/F are the authoring/registry/governance core; all buildable on shipped primitives; each
  lands with its typed exceptions + Tier-2 tests (no orphan stubs).
- **C (online-store): ADR-defer.** §11.4 explicitly says "defer"; the issue author pre-hedged "or an
  explicit ADR"; an online (Redis/serving) adapter pairs with a registry-backed online surface that is
  genuinely M2+ and adds a runtime dependency. Building it speculatively now risks an unused surface.
- **G (DB-side as-of): defer.** It is a **performance optimization**, not a correctness requirement —
  point-in-time as-of already works (DataFlow filters the window, polars computes the as-of, §4 MUST-5).
  Gated on an unshipped DataFlow aggregation primitive; building against raw SQL = `zero-tolerance.md`
  Rule 4 violation.

## Sharding (per `autonomous-execution.md` capacity budget — B at 7 inv, E at 6 are ceiling-level)

- S1: D (typed-exception base + raise-site skeleton) — small, lands first
- S2: A (`@feature` + public `FeatureGroup`) — 6 inv
- S3: E (`FeatureRegistry` + version immutability) — 6 inv, standalone
- S4: B (`FeatureStore.materialize()`) — 7 inv, own shard
- S5: F (GDPR `erase_tenant`) — 5 inv
- S6: spec graduation + `_index.md` + close #693
- Deferred (value-anchored): C (online-store, ADR), G (DB-side as-of, perf, DataFlow-gated)

This is a genuine **multi-session implementation workstream** (5 build shards at/near invariant
ceiling + spec graduation), not the ~1-session spec patch agent 03 first proposed.

## Brief-correction record (per `agents.md` parallel brief-verification gate)

- Issue #1302 brief is **accurate** (it correctly states the M2 author surfaces are absent and the
  read binding ships).
- `ml-feature-store.md §11.2` is **stale** (claims DataFlow materialisation primitive unshipped;
  it ships in 2.11.3) — correct during S6.
- `dataflow-ml-integration.md` cites **stale flat paths** (`dataflow/transforms.py`, `ml_integration.py`,
  `lineage.py`) — real paths are `dataflow/ml/_*.py` — correct during S6.

## DECISION (user-ratified at /analyze→/todos gate, 2026-06-12)

User chose **"Include online-store in this workstream too."** Final scope:
- **BUILD (6 surfaces):** D (typed exceptions), A (`@feature`+`FeatureGroup`), E (registry+immutability),
  B (`materialize()`), F (GDPR `erase_tenant`), **C (online-store adapter)** — overrides §11.4 "defer";
  user-anchored override at this gate.
- **+ spec graduation** (correct stale §11.2 + citation paths; graduate `dataflow-ml-integration.md`) → closes #693.
- **DEFER:** G (DB-side windowed as-of) — perf optimization, genuinely DataFlow-gated; value-anchored deferral.

Online-store adds a runtime dependency (Redis/serving); it lands with `OnlineStoreUnavailableError`
and its own Tier-2 tests per surface. §11.4 disposition to be corrected during S6 to reflect the build.
