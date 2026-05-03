---
type: DECISION
date: 2026-04-20
created_at: 2026-04-20T07:56:32.459Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: MLEngine.register() — 6-framework ONNX export with tenant-aware audit rows (shard-A)
phase: implement
tags:
  [
    auto-generated,
    kailash-ml,
    mlengine,
    register,
    onnx,
    tenant-isolation,
    audit,
    shard-a,
  ]
related_journal: []
---

# DECISION — MLEngine.register() — 6-framework ONNX export (shard-A)

## Commit

`9fcf2dad7fb5` — feat(ml): implement MLEngine.register() — 6-framework ONNX export (shard-A)

## Body

Un-stubs `MLEngine.register()` per `specs/ml-engines.md` §2.1 MUST 9, §4.2 MUST 4, §5.1 MUST 4, §5.2, §6.1 MUST 1-5.

`register()` is the contract point where "train in Python, serve in Rust/C++/browser" actually takes effect. A pickle-default or silent-ONNX-failure `register()` ships users a Python-only pickle artifact and they discover it only at cross-language serving time — the v0.9.x failure pattern the §6.1 MUST 4 clause exists to prevent. Routing every call through the existing `OnnxBridge` 6-framework matrix (sklearn / xgboost / lightgbm / catboost / torch / lightning) puts all format dispatch in one place; raising `OnnxExportError` on `format="onnx"` failure (vs silent pickle fallback) makes the failure loud at deployment time rather than at Rust-side inference time.

**Tenant-aware** per §5.1 MUST 4: the auxiliary `_kml_engine_versions` table persists `tenant_id` as part of the primary key scope (`tenant_id`, `name`, `version`) — a post-incident "which models did tenant X promote last month" query is now a single indexed lookup instead of a full-table scan.

**Audit-row** per §5.2: every `register()` call writes one `_kml_engine_audit` row with `operation="register"`, `duration_ms`, `outcome`, `tenant_id` (indexed). Writes fire in a `try/finally` so failures still land an `outcome="failure"` row for forensics, and the audit write is wrapped in its own `try` so audit-pipeline failure never masks the primary exception.

Also adds 5 internal helpers: `_synthesise_model_name` (stable hash-based fallback), `_resolve_onnx_framework` (bridge key from family alias or model module), `_acquire_connection` (lazy `ConnectionManager` init), `_resolve_artifact_store` (DI override + `LocalFileArtifactStore` default), `_export_and_save_onnx` (typed-error-raising ONNX dispatch per §6.1 MUST 5).

Primitive-table DDL routes through the dedicated `_engine_sql` helper module (zero raw SQL in `engine.py` per the `FeatureStore` precedent and `rules/dataflow-identifier-safety.md`). Every identifier is routed through `_validate_identifier` at the call site.

Still to land: (a) Tier 2 tests for setup idempotency + tenant propagation + register-ONNX matrix + register-tenant-row + register-ONNX-failure, (b) deferral-test sweep at `tests/unit/test_mlengine_construction.py:70-77` per `rules/orphan-detection.md` §4a.

## For Discussion

1. **Counterfactual**: The commit explicitly chooses to raise `OnnxExportError` on ONNX failure instead of silently falling back to pickle. If the silent-pickle-fallback behavior had shipped (the v0.9.x pattern), at what point in a typical ML deployment pipeline would the failure have been discovered — and what would the user's debugging experience have looked like when Rust-side inference attempted to load a pickle artifact?

2. **Data-referenced**: The commit notes that "Still to land: (a) Tier 2 tests..." — the register() implementation ships without its Tier 2 integration tests in this commit. Per `rules/orphan-detection.md` §2 and `rules/zero-tolerance.md` Rule 6, this is a deferred test gap. The deferral is acknowledged in the commit body. How many additional commits elapsed before the Tier 2 tests for `register()` landed, and did those tests find any bugs not caught by the unit tests?

3. **Design**: The `_kml_engine_audit` table persists `outcome="failure"` rows even when the primary exception propagates. This means a caller who catches `OnnxExportError` and retries will see two audit rows for what they consider one logical operation (failed attempt + successful retry). Should the audit table include a `retry_of` foreign key or `attempt_number` column to distinguish first-attempt failures from retried-to-success flows?
