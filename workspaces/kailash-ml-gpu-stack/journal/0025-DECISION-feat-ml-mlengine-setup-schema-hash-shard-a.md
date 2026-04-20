---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.459Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: MLEngine.setup() — schema hash + idempotency via sha256 fingerprint (shard-A)
phase: implement
tags:
  [
    auto-generated,
    kailash-ml,
    mlengine,
    setup,
    idempotency,
    schema-hash,
    shard-a,
  ]
related_journal: []
---

# DECISION — MLEngine.setup() — schema hash + idempotency (shard-A)

## Commit

`2087e29ef41b` — feat(ml): implement MLEngine.setup() — schema hash + idempotency (shard-A)

## Body

Un-stubs `MLEngine.setup()` per `specs/ml-engines.md` §2.1 MUST 6.

`setup()` is the idempotent entry point notebooks call repeatedly while iterating. A non-idempotent `setup()` floods the feature store with phantom schema versions and makes every subsequent `fit()` ambiguous about which split it trained against. Canonicalising the `(df_fingerprint, target, ignore, feature_store_name)` tuple into a stable `schema_hash` (sha256 prefix, 16 hex chars) lets `setup()` return the cached `SetupResult` when called twice with the same inputs and lets downstream `fit()` / `compare()` / `finalize()` key off a single identifier.

Also adds 6 internal helpers needed by `setup()` (and by `register()` in the follow-up commit):

- `_to_polars_dataframe` — polars-native boundary per §7.1 MUST 2
- `_resolve_feature_store_name` — stable fs identifier
- `_compute_schema_hash` — deterministic hash
- `_infer_task_type` — classification vs regression from target dtype
- `_build_schema_info` — extended profile per `SetupResult.schema_info`
- `_infer_entity_id_column` — FeatureStore row key

Phase 3 scope: holdout split strategy; kfold / stratified_kfold / walk_forward raise typed `NotImplementedError` naming Phase 3.1 so a future session can complete them without reading the body.

Still to land: (a) `register()` 6-framework ONNX export, (b) paired Tier 2 tests for setup idempotency + tenant propagation + register matrix, (c) deferral-test sweep at `tests/unit/test_mlengine_construction.py:70-77` per `rules/orphan-detection.md` §4a.

## For Discussion

1. **Counterfactual**: The `schema_hash` is computed from `(df_fingerprint, target, ignore, feature_store_name)`. If `setup()` had been non-idempotent (no hash, every call creates a new schema version), what would the feature store look like after a typical iterative notebook session where a data scientist calls `engine.setup(df, "label")` five times while adjusting feature columns? Would the phantom schema versions be detectable, or would they silently accumulate until a storage quota was hit?

2. **Data-referenced**: kfold / stratified_kfold / walk_forward raise typed `NotImplementedError` "naming Phase 3.1 so a future session can complete them without reading the body." This is an acknowledged stub per `rules/zero-tolerance.md` Rule 2 but permitted as an "iterative TODO when actively tracked." Is Phase 3.1 tracked in the workspace todos, and what is the current status — was it completed in a subsequent session or still outstanding?

3. **Design**: `_infer_task_type` classifies as classification vs regression from target dtype. Clustering is a third task type but is not inferred — it must be passed explicitly. The `compare()` default family set for clustering is `(sklearn,)` only. Is the dtype-based inference approach sufficient for the two-way classification/regression split, or are there common cases where a numeric target should be treated as classification (e.g., binary 0/1 encoded as int) that dtype alone cannot distinguish?
