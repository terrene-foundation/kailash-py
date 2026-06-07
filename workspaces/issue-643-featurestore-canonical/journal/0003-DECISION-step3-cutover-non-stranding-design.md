# DECISION — #643 step 3: ship the non-stranding 2.0.0 cutover (option-a)

**Date:** 2026-06-07
**Phase:** /analyze → /todos (issue-643-featurestore-canonical)
**Type:** DECISION
**Trigger:** user — "continue from last session, /autonomize workflow and /redteam to convergence"

## Context (ground-truth verified this session, not session-notes hearsay)

- **#643 step 1** (deprecation bridge) SHIPPED — kailash-ml **1.7.2**, on PyPI (`f69b8013d`).
- **#1241** (canonical `get_features` was non-functional — the real cutover blocker) CLOSED —
  fixed in **1.7.5 + 1.7.6**, gate-reviewed (`39cf441ec`), on PyPI, deploy-recorded
  (`deploy/deployments/2026-06-03-ml-v1.7.5-v1.7.6-1241-featurestore-getfeatures.md`).
- Remaining: **#643 step 3** — the 2.0.0 cutover (flip top-level `from kailash_ml import FeatureStore`
  from the legacy write-capable surface to the canonical read-only surface).

The prior session flagged step 3 "GATED (breaking; needs steer)". Under `/autonomize` + standing
feedback (`feedback_no_shims`, `feedback_optimal_outcome`, `feedback_drive_to_completion`) the
"needs steer" is resolved by making the optimal call with evidence. The irreversible PyPI publish
stays user-gated (BUILD repo).

## Investigation — 3 parallel deep-dive agents (agents.md ≥3-claim MUST)

Durable receipts (verify-resource-existence MUST-4):

| Agent               | Mission                         | Verdict                                                                                                                                                                                                                                                                                   |
| ------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `af1692f94de96f527` | write-path stranding            | Naive flip **STRANDS** write users: 4 legacy write ops (`initialize`/`register_features`/`compute`/`store`) all §11-M2-deferred, no canonical replacement, no doc, no test. Non-stranding design viable with prerequisites.                                                               |
| `afabb37e14908251c` | breakage surface                | Flip is **import-safe + collection-safe** repo-wide — no production caller/test uses the top-level symbol (all use explicit `from kailash_ml.engines.feature_store import`). DataFlow binding duck-typed; `_SchemaFeatureGroup` (#1241) satisfies it; flip + even removal don't break it. |
| `aeb23320cd7ca32a0` | change surface + parity + shard | ~30 LOC load-bearing, **7 invariants, ONE shard**. Legacy MODULE removal NOT feasible this PR (engine.py:843 / dashboard/server.py:459 / engines/registry.py:421-425 + 5 tests bound to it) → option-a only.                                                                              |

## The stranding problem (load-bearing — the reason this is not a switch-flip)

The canonical 1.0+ `FeatureStore` is **read-only by design** (`specs/ml-feature-store.md §1.2`).
Legacy has 8 ops; 4 are writes, 3 are reads with no canonical equivalent:

| Legacy op                                                 | kind  | canonical replacement                                                                              | disposition at cutover                               |
| --------------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `initialize` / `register_features` / `compute` / `store`  | WRITE | none (write = `@db.model` + `express.create`; §11.1/.2/.4 M2-deferred as a _FeatureStore_ surface) | explicit legacy import + MIGRATION write-path recipe |
| `get_features`                                            | READ  | canonical `get_features` (works since #1241)                                                       | top-level default → canonical                        |
| `get_training_set` / `get_features_lazy` / `list_schemas` | READ  | none on canonical surface                                                                          | explicit legacy import (parity note)                 |

## Decision

**Ship the non-stranding 2.0.0 cutover (option-a):**

1. Flip `_engine_map["FeatureStore"]` → `kailash_ml.features` (`__init__.py:631`); remove the
   FeatureStore DeprecationWarning shim block (`__init__.py:664-690`) per `feedback_no_shims`
   (the bridge lived 1.7.2→1.7.6, satisfying Rule 6a's ≥1-minor-cycle).
2. **Keep** `kailash_ml.engines.feature_store.FeatureStore` importable via its explicit path — the
   non-deprecated home for writers + the 3 extra read ops. (NOT `kailash_ml.legacy.FeatureStore`:
   that namespace does not exist — `ModuleNotFoundError` — and minting it is a broader
   ModelRegistry/TrainingPipeline 3.0 refactor, out of scope.)
3. MIGRATION.md: correct the stale "2.0.0 removes legacy" claim → "2.0.0 flips the top-level default;
   legacy stays at the explicit path; removal deferred to a later major (with the 3.0 ModelRegistry/
   TrainingPipeline sweep)". Add a **write-path recipe** + a **3-read-method parity note**.
4. README.md: fix phantom methods (`ingest`/`get_features_at_time`/`list_feature_sets` do not exist;
   real ops are `register_features`/`store`/`compute`/`get_features`/`get_training_set`/
   `get_features_lazy`/`list_schemas`) and update the top-level-default story.
5. Tests: NEW top-level-resolution regression (canonical + no DeprecationWarning) + NEW write-then-read
   round-trip (Tier-2 real DataFlow) **validating the migration story the cutover depends on**.
6. Spec sync (`ml-feature-store.md`), version → **2.0.0** (`_version.py` + `pyproject.toml`),
   CHANGELOG 2.0.0 with BREAKING + migration section (Rule 6a).

## Out of scope (flagged, not folded — shard discipline)

- `.claude/skills/*` (9 files) FeatureStore examples → **loom /codify origination** (synced artifacts;
  repo-scope-discipline). Follow-up ledger item.
- Legacy **module removal** + migrating engine.py/dashboard/registry off the ConnectionManager store
  → separate prerequisite shard (3 call-graph hops into MLEngine).
- `kailash_ml.legacy` namespace phantom (MIGRATION.md ModelRegistry recipe; `engine.py:19` Phase-2
  note) → separate ModelRegistry/TrainingPipeline 3.0 concern.
- Porting `get_features_lazy` to the canonical surface → M2 feature decision, not the cutover.

## Receipts

- Source anchors: `__init__.py:631` (flip), `:664-690` (shim), `_version.py:4`, `pyproject.toml:7`.
- Legacy ops: `engines/feature_store.py:72,81,141,195,253,326,366,393`.
- Canonical ctor: `features/store.py:98-114`. Binding: `dataflow/ml/_feature_source.py:77-103` (duck-typed).
- Spec: `specs/ml-feature-store.md:6,37-39,343,348,§11(475-531)`.
- Agent task IDs above; this entry is the external receipt per verify-resource-existence MUST-4.
