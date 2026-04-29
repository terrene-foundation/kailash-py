# Architecture Plan — kailash-ml 1.5.x Followup

Three ADRs, one per issue. Brief corrections from analyst deep-dives folded in. All decisions assume autonomous execution per `rules/autonomous-execution.md` (no human-team framing).

## Brief corrections (recorded for traceability)

The original brief at `briefs/01-context.md` had three inaccuracies surfaced during analysis. They are corrected here and in the corresponding journal entries; the brief itself is left untouched as a historical artifact (per `rules/specs-authority.md` brief vs spec separation).

1. **#699 root-cause framing** — brief said the fork was "ExperimentTracker (tenant-aware) vs ModelRegistry (un-tenanted)". Actual: `ExperimentTracker` does NOT directly create `_kml_model_versions`. The canonical creator is **numbered migration `src/kailash/tracking/migrations/0002_kml_prefix_tenant_audit.py:253`** (tenant-aware DDL via `TableSpec`). `ModelRegistry._create_registry_tables` (`packages/kailash-ml/src/kailash_ml/engines/model_registry.py:204`) ships its own inline `CREATE TABLE IF NOT EXISTS` with an un-tenanted schema. When the migration runs first, the IF-NOT-EXISTS becomes a no-op, and ModelRegistry's queries (`SELECT name = ?`, lines 232/239/249/478/494/507/731/908) target columns the migration didn't create. The fork is **migration-vs-application-code**, not engine-vs-engine. This makes the fix sharper and invokes `rules/schema-migration.md` Rule 1 directly: DDL in application code outside migrations is BLOCKED.
2. **#700 file location** — brief said `engines/inference_server.py`. Actual location: `packages/kailash-ml/src/kailash_ml/serving/server.py:254`. The old path (`engines/inference_server.py`) was deleted by W6-004 without a deprecation shim, per analyst finding.
3. **#701 silent-drop scope** — brief said the 1.1.x kwargs (`title`, `n_batches`, `train_losses`, `val_losses`, `forward_returns_tuple`) were silently dropped. Actual: those kwargs raise `TypeError` (signature is fixed-arity, not `**kwargs`). The silent drop is ONLY on `data=` when `kind="dl"`. Bonus finding: `_wrappers.py:474–485` accepts FOUR additional `kind` literals (`clustering`, `alignment`, `llm`, `agent`) that have NO branch handler and silently fall through to `DLDiagnostics` — same Rule 3 (silent fallback) violation class; in scope per `rules/autonomous-execution.md` § 4 "Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget".

## ADR-1 — Issue #699 — Schema Convergence on Migration 0002 (REVISED 2026-04-29 post-redteam)

> **REVISION NOTE (Round-1 redteam, 04-validate/01-redteam-mechanical-sweep.md):** Original ADR-1 underestimated scope by treating the fork as 2-way (migration vs inline DDL). Mechanical sweep revealed **3-way drift** with 6 inline-DDL columns READ at `model_registry.py:148-272` — they are load-bearing for the version-row hydration helper, not just write-only. Code-only fix is BLOCKED. **Migration 0005 is mandatory** to add the 6 missing data columns to migration 0002's table.

### Decision

Three-part convergence:

1. **Migration 0005 (`0005_kml_model_versions_data_columns.py`)** — ADD COLUMN to `_kml_model_versions` for the 6 inline-DDL columns the registry's read path depends on: `metrics_json TEXT NOT NULL DEFAULT '[]'`, `signature_json TEXT`, `onnx_status TEXT NOT NULL DEFAULT 'pending'`, `onnx_error TEXT`, `artifact_path TEXT NOT NULL DEFAULT ''`, `model_uuid TEXT NOT NULL DEFAULT ''`. Reversible downgrade (`DROP COLUMN`) per `rules/schema-migration.md` Rule 3; destructive — requires `force_downgrade=True` per Rule 7.
2. **ModelRegistry inline DDL DELETED** — `model_registry.py:204-217` `CREATE TABLE IF NOT EXISTS _kml_model_versions ...` removed. Per `rules/schema-migration.md` Rule 1, the inline DDL was always a violation; deleting it is structural compliance, not a workaround.
3. **ModelRegistry queries reconciled to migration 0002 column names** (Option B from redteam sweep). Every `WHERE name = ?` becomes `WHERE tenant_id = ? AND model_name = ?` (matching migration 0002's `model_name` column). INSERT writes `model_name` not `name`. Pragmatic compromise: spec §5A.2 uses `name`; migration 0002 uses `model_name`; migration is canonical for established users; spec amended per `rules/specs-authority.md` Rule 5 (spec follows code when code is the canonical reality).

### Rationale

- **Migration 0002 is on-disk for every 1.5.0/1.5.1 user** — adding columns via 0005 is backwards-compatible (defaults supplied); renaming `model_name` → `name` would require a 3-way data migration with rollback risk.
- **Spec §5A.2 declares 15 columns** as the long-term canonical (`id` UUID PK, `format`, `artifact_uri`, `artifact_sha256`, `lineage_*`, `is_golden`, `onnx_unsupported_ops`, `onnx_opset_imports`, `ort_extensions`, `actor_id`). 1.5.2 patch ships ONLY the 6 columns required to unblock `register_model()`. The remaining 9 spec columns are tracked as a separate sibling workstream for 1.6.0 / 1.7.0.
- Per `rules/schema-migration.md` Rule 1, application-code DDL is BLOCKED. Inline DDL deletion is structural compliance.
- Per `rules/zero-tolerance.md` Rule 4, the bug is in ModelRegistry's source — fix it directly.
- Per `rules/specs-authority.md` Rule 5b, the spec edit triggers full sibling re-derivation across `ml-*.md` (16 specs). Captured in cross-cutting plan section.

### Out of scope (explicit)

The remaining spec §5A.2 columns NOT added by this 1.5.2 patch (`id` UUID PK, `format`, `artifact_uri`, `artifact_sha256`, `lineage_run_id`, `lineage_dataset_hash`, `lineage_code_sha`, `is_golden`, `onnx_unsupported_ops`, `onnx_opset_imports`, `ort_extensions`, `actor_id`) are a separate sibling workstream. They require new producer code (lineage tracker integration, sha256 computation, format detection) that doesn't exist in 1.5.x. PK promotion to UUID `id` is also out-of-scope — would require regenerating every existing row's identity. Tracked for 1.6.0 / 1.7.0 minor cycles.

### Implementation shape

**Files touched:**

| File                                                                                           | Change                                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **NEW** `src/kailash/tracking/migrations/0005_kml_model_versions_data_columns.py`              | ADD COLUMN x6: `metrics_json`, `signature_json`, `onnx_status`, `onnx_error`, `artifact_path`, `model_uuid` — all with defaults. Reversible downgrade (`DROP COLUMN`); destructive (down_sql contains DROP) → orchestrator requires `force_downgrade=True` per `rules/schema-migration.md` Rule 7.                                 |
| `packages/kailash-ml/src/kailash_ml/engines/model_registry.py`                                 | DELETE inline `CREATE TABLE IF NOT EXISTS _kml_model_versions ...` at L204-217. Migrate every `WHERE name = ?` → `WHERE tenant_id = ? AND model_name = ?` at L232/239/249/478/494/507/731/908/925. INSERT (L508-522) writes `model_name` (not `name`) + the 6 added cols. Hydration helper L257-272 reads from updated column set. |
| `packages/kailash-ml/src/kailash_ml/engines/lineage.py`                                        | L286, L295: `SELECT * FROM _kml_model_versions WHERE name = ?` → `WHERE tenant_id = ? AND model_name = ?`. Lineage walker already passes tenant_id; plumb to query.                                                                                                                                                                |
| `packages/kailash-ml/src/kailash_ml/engines/_engine_sql.py:14`                                 | Update docstring; "registry-wide \_kml_model_versions without a tenant column" comment is wrong.                                                                                                                                                                                                                                   |
| `packages/kailash-ml/src/kailash_ml/tracking/registry.py:1586`                                 | Hydration helper — verify column-name mapping matches migration 0002 + 0005.                                                                                                                                                                                                                                                       |
| `specs/ml-registry.md §5A.2`                                                                   | Amend column-naming note: "SQLite/migration-0002 reality uses `model_name`; spec uses `name` for the long-term canonical Postgres DDL". Add §5A.2.x noting the staged delivery (0005 patch + 1.6.0 expansion).                                                                                                                     |
| `specs/ml-tracking.md`, `specs/ml-engines-v2.md`, `specs/ml-engines-v2-addendum.md`, etc.      | Sibling re-derivation per `rules/specs-authority.md` Rule 5b — grep for `_kml_model_versions`, `model_name`, `name` references in ml-\*.md and reconcile.                                                                                                                                                                          |
| Existing tests asserting un-tenanted shape                                                     | Sweep + port to tenant-aware + new column writes. Per `rules/orphan-detection.md` Rule 4, do NOT defer.                                                                                                                                                                                                                            |
| **NEW** `packages/kailash-ml/tests/regression/test_issue_699_tracker_registry_shared_store.py` | Tier-2 DOCS-EXACT pipeline: ExperimentTracker.create + ModelRegistry on same SQLite store + register_model + read-back.                                                                                                                                                                                                            |

**Public API impact:**

- `ModelRegistry.register_model(name, ...)` → `register_model(name, ..., *, tenant_id: str = "default")`. Default keeps single-tenant ergonomics; multi-tenant deployments pass explicit tenant_id. Per `rules/tenant-isolation.md` MUST Rule 2, missing tenant_id on a multi-tenant model raises `TenantRequiredError` — but ModelRegistry isn't multi-tenant-flagged at the model level, so the tenant_id="default" fallback is acceptable for the registry surface (the default lands in the `tenant_id` column). Spec §5A.2 confirms this.
- `ModelRegistry.get_model(name, version, *, tenant_id="default")`, `set_stage(name, version, stage, *, tenant_id="default")`, `list_versions(name, *, tenant_id="default")` — all gain optional tenant_id kwargs.

**Tier-2 regression test (canonical):**

```python
# packages/kailash-ml/tests/regression/test_issue_699_tracker_registry_shared_store.py
import pytest, asyncio
from pathlib import Path
from kailash.db import ConnectionManager
from kailash_ml import ExperimentTracker, ModelRegistry
from kailash_ml.types import MetricSpec

@pytest.mark.regression
@pytest.mark.integration
async def test_tracker_and_registry_share_kml_model_versions_table(tmp_path):
    """DOCS-EXACT: tracker + registry on one SQLite store; register + get round-trip."""
    db = f"sqlite:///{tmp_path}/repro.db"
    tracker = await ExperimentTracker.create(store_url=db)            # triggers migration 0002
    conn = ConnectionManager(db)
    await conn.initialize()
    reg = ModelRegistry(conn)
    res = await reg.register_model(
        "demo_model",
        artifact=b"\x00\x01",
        metrics=[MetricSpec(name="acc", value=0.95)],
    )                                                                  # writes via migration's column shape
    got = await reg.get_model("demo_model", version=res.version)
    assert got.name == "demo_model" and got.version == res.version
```

### Migration risk for existing users

Existing 1.5.0 / 1.5.1 users have migration 0002's 8-column table on disk. `ModelRegistry.register_model()` is BROKEN for them today — the IF-NOT-EXISTS no-ops, the INSERT fails on `name` column missing. This fix unblocks them. **Migration 0005 is mandatory** (not conditional) — it adds the 6 data columns (`metrics_json`, `signature_json`, `onnx_status`, `onnx_error`, `artifact_path`, `model_uuid`) the registry's read path requires.

**Migration 0005 backwards-compatibility:** all 6 columns added with defaults; any existing rows (none, since `register_model()` was broken) get the defaults. Forward-compatible with PG and SQLite. Reversible via `DROP COLUMN` (destructive — requires `force_downgrade=True` per `rules/schema-migration.md` Rule 7).

**For users still on kailash-ml ≤1.4.x** (predating migration 0002 in 1.5.0): they have a totally different un-tenanted shape on disk. CHANGELOG must direct them to upgrade through 1.5.0 first (which runs migration 0002 to convert). If telemetry confirms anyone is on ≤1.4.x, ship migration 0006 in 1.5.3 to bridge.

### Risk register

- **Risk**: `tenant_id="default"` silently masks a multi-tenant deployment misconfiguring the registry. **Mitigation**: emit DEBUG log per `rules/observability.md` Rule 3 every time the default is applied; add metric counter; at 1.6.0 consider raising at construction time when `enable_multi_tenant=True` env or config is set.
- **Risk**: migration 0005 ALTER TABLE on a busy production DB locks the table. **Mitigation**: SQLite ALTER ADD COLUMN is non-blocking; PG ALTER ADD COLUMN with DEFAULT is also non-blocking on PG ≥ 11 (default stored in metadata, not rewritten). Document in CHANGELOG that PG <11 users may see brief table-lock during upgrade.
- **Risk**: column-name reconciliation (Option B: queries → `model_name`) creates `name` ↔ `model_name` ambiguity for users reading `specs/ml-registry.md §5A.2` literally. **Mitigation**: spec amendment per `rules/specs-authority.md` Rule 5; add §5A.2.x section explicitly noting "SQLite/migration-0002 reality uses `model_name` for backwards compat; long-term canonical is `name` per the Postgres DDL block; alignment scheduled for 1.7.0".
- **Risk**: existing tests assert `name = ?` query shape. **Mitigation**: sweep+port in same shard per `rules/orphan-detection.md` Rule 4. `pytest --collect-only` MUST exit 0 before merge.
- **Risk**: lineage walker drift — `_kml_lineage` PK is `(tenant_id, model_name, version)` (verified migration 0004); the walker already passes tenant_id but the join in `lineage.py:295` doesn't. **Mitigation**: covered by Tier-2 wiring test at `test_lineage_graph_wiring.py` (exists per 1.5.0); extend assertion to confirm tenant-aware join.
- **Risk** (NEW from redteam): the 6 added columns leave 9 spec §5A.2 columns still missing. Future code that depends on `artifact_uri`, `format`, `is_golden`, etc., will hit the same class of bug. **Mitigation**: codify candidate § 6 — sibling workstream tracked for 1.7.0 ml-registry full §5A.2 alignment.

## ADR-2 — Issue #700 — InferenceServer Multi-Model Deprecation Adapter

### Decision

Ship a **separate `MultiModelAdapter` class** that accepts the 1.1.x signature `(registry=, cache_size=)` + `warm_cache([names])` + `load_model(name, model)` and lazy-constructs one `InferenceServer.from_registry(name, registry=)` per model. `InferenceServer.__new__` routes 1.1.x kwargs to it with `DeprecationWarning`. Add additive `InferenceServer.from_registry_many(names, registry=) -> dict[str, InferenceServer]` for the canonical multi-model use case.

### Rationale

- Per `specs/ml-serving.md §1.1, §2.1, §2.3`, the spec-canonical direction IS one-server-per-model. The 1.5.x removal was intentional, not regression.
- Adapter is therefore a **back-compat shim AROUND the spec**, not a spec-violating restoration.
- In-class branching is BLOCKED because `InferenceServerConfig` is `frozen=True, slots=True` — cannot toggle multi-model state via attribute assignment without breaking the dataclass contract.
- `__new__` routing pattern (return `MultiModelAdapter` when 1.1.x kwargs detected) is the cleanest single-entry-point migration. Pyright will need explicit `Union[InferenceServer, MultiModelAdapter]` return type or callers will see a single type — accept this as an explicit migration cost.
- Per `rules/zero-tolerance.md` Rule 6, restoration is "implement fully" — the adapter MUST handle warm_cache, load_model, AND the predict() call (routing to the right per-model server).

### Out of scope

- `load_model(name, user_bytes)` — the 1.1.x form accepted user-supplied bytes/dict for the model object. The 1.5.x architecture has registry as authoritative source of truth. Adapter MUST raise `TypeError("load_model with user-supplied bytes is removed; register the model first via ModelRegistry, then call warm_cache or rely on lazy load_from_registry")`. This is a spec-aligned hard break with a migration hint, not a silent drop.

### Implementation shape

**Files touched:**

| File                                                                        | Change                                                                                                   |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **NEW** `packages/kailash-ml/src/kailash_ml/serving/multi_model_adapter.py` | New `MultiModelAdapter` class. ~150 LOC. Holds `dict[str, InferenceServer]`, predict dispatches by name. |
| `packages/kailash-ml/src/kailash_ml/serving/server.py`                      | `InferenceServer.__new__` routes 1.1.x kwargs to adapter; emits `DeprecationWarning`.                    |
| `packages/kailash-ml/src/kailash_ml/serving/server.py`                      | NEW classmethod `from_registry_many(names, registry, **config_kwargs) -> dict[str, InferenceServer]`.    |
| `packages/kailash-ml/src/kailash_ml/__init__.py`                            | Re-export `MultiModelAdapter` (additive); update `__all__` per `rules/orphan-detection.md` Rule 6.       |
| `packages/kailash-ml/CHANGELOG.md`                                          | Document architectural shift + migration steps.                                                          |
| **NEW** `packages/kailash-ml/tests/regression/test_issue_700_*.py`          | TWO Tier-2 regressions: legacy adapter path AND canonical from_registry_many path.                       |

**Tier-2 regression tests (signatures):**

```python
@pytest.mark.regression
@pytest.mark.integration
async def test_inference_server_legacy_multi_model_adapter_predicts(tmp_path):
    """1.1.x DOCS-EXACT: InferenceServer(registry=, cache_size=) + warm_cache + predict."""
    # Build registry with two models, exercise legacy surface, assert predict works,
    # assert DeprecationWarning emitted.

@pytest.mark.regression
@pytest.mark.integration
async def test_inference_server_canonical_per_model_predicts(tmp_path):
    """1.5.x DOCS-EXACT: InferenceServer.from_registry(name, registry=).predict()."""
    # Single-model canonical path, no warning.
```

### Risk register

- **Risk**: `__new__` returning a subtype confuses static analysis (pyright reports `InferenceServer`, runtime returns `MultiModelAdapter`). **Mitigation**: explicit `Union[InferenceServer, MultiModelAdapter]` return annotation; add a type-checking assertion test.
- **Risk**: adapter caching diverges from per-model `InferenceConfig.cache_ttl_secs`. **Mitigation**: adapter takes `cache_size` and routes to per-model config; document cache-eviction semantics in CHANGELOG.
- **Risk**: thread-safety drift between adapter and per-model servers. **Mitigation**: adapter holds a `dict[str, InferenceServer]` keyed by name; constructor populates lazily via `warm_cache`; per-model server already has its own thread-safety. No shared mutable state introduced.

### Release classification

**1.6.0 minor** (NOT 1.5.2 patch). The deprecation adapter is additive but signals an architectural acknowledgment that the 1.1.x signature is supported again. Spec direction is one-per-model; the adapter is a temporary restoration window pending 1.7.0 final removal (with another DeprecationWarning).

## ADR-3 — Issue #701 — diagnose() data= wiring + kind= aliases + unhandled-literal sweep

### Decision

Path A (additive). Three coordinated fixes:

1. **`kind="dl"` consumes `data=`** end-to-end — pass DataLoader through to `DLDiagnostics(subject, data=, tracker=)`; expose `DLDiagnostics.report(data=loader)` returning the diagnostic. Spec §5 amended to add the `data=` parameter to the constructor.
2. **`kind="classifier"` / `kind="regressor"` aliases** — both map to `classical_classifier` / `classical_regressor` respectively; common in user code, low-cost to add.
3. **Unhandled-literal sweep** (bonus finding) — `_wrappers.py:474–485` currently accepts `clustering`, `alignment`, `llm`, `agent` as valid `kind` literals but has no dispatch branches. Fix: either (a) add the dispatch branches if the engines exist, or (b) raise `ValueError(f"diagnose(kind={kind!r}) — engine not yet implemented")` with explicit message. Per `rules/zero-tolerance.md` Rule 6 (Implement Fully), if the engines exist, dispatch them; if they don't, refuse.
4. **Unknown kwargs raise** — `diagnose(model, kind=..., data=..., **kwargs)` with kwargs outside the documented set MUST raise `TypeError(f"diagnose() got unexpected kwargs: {sorted(kwargs)}; the 1.1.x kwargs (title, n_batches, train_losses, val_losses, forward_returns_tuple) were removed in 1.5.0 — see CHANGELOG migration section")`. Hint includes the 1.1.x kwargs explicitly so the migration path is in the error.

### Rationale

- Path B (remove `data=` from signature) is BLOCKED by `rules/zero-tolerance.md` Rule 3: the silent-drop bug is the canonical "kwarg accepted with zero effect" — Rule 3 says fix the silent fallback, don't paper over by removing the surface.
- Aliases are 4 lines; refusing them is a paper-cut migration tax for no benefit.
- The unhandled-literal sweep is the same bug class as the `data=` silent drop. Per `rules/autonomous-execution.md` § 4 "Fix-Immediately When Review Surfaces A Same-Class Gap Within Shard Budget" — same shard, same fix.
- Spec §3.1 already declares DataLoader in the `data=` type union; the bug is that the dispatch ignores it. Fix is spec-aligned.
- Spec §5 (DLDiagnostics surface) needs a `data=` constructor parameter and a `.report(data=...)` method. Per `rules/specs-authority.md` §5b, this triggers full sibling re-derivation across `ml-*.md` (16 specs).

### Implementation shape

**Files touched:**

| File                                                               | Change                                                                                                                                              |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `packages/kailash-ml/src/kailash_ml/_wrappers.py:449–565`          | Wire `data=` to DLDiagnostics; add aliases; raise on unknown kwargs; dispatch the 4 unhandled literals OR raise `ValueError` with explicit message. |
| `packages/kailash-ml/src/kailash_ml/diagnostics/dl.py:251–322`     | Add `data: DataLoader \| None = None` constructor param; add `.report(data=loader)` method.                                                         |
| `specs/ml-diagnostics.md`                                          | §3 add aliases, §5 add data= surface; trigger sibling re-derivation across ml-\*.md.                                                                |
| **NEW** `packages/kailash-ml/tests/regression/test_issue_701_*.py` | Tier-2: PyTorch nn.Linear + DataLoader through diagnose(kind="dl", data=); aliases; unknown-kwargs TypeError.                                       |

**Tier-2 regression test (canonical):**

```python
@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_dl_pytorch_dataloader_end_to_end():
    """DOCS-EXACT: diagnose(model, kind='dl', data=loader) actually consumes the loader."""
    import torch
    from torch.utils.data import DataLoader, TensorDataset
    from kailash_ml import diagnose

    model = torch.nn.Linear(10, 2)
    X = torch.randn(64, 10); y = torch.randint(0, 2, (64,))
    loader = DataLoader(TensorDataset(X, y), batch_size=8)

    diag = diagnose(model, kind="dl", data=loader)
    report = diag.report(data=loader)              # consumes the loader
    assert report.n_batches > 0                    # proves consumption
    assert report.n_samples == 64                  # full dataset traversed
```

### Risk register

- **Risk**: spec §5 amendment triggers full sibling re-derivation across 16 ml-\*.md specs. **Mitigation**: planned cost; codify candidate in `02-plans/03-codify-candidates.md`.
- **Risk**: revived 1.1.x kwargs surfaces (title, n_batches, train_losses, val_losses, forward_returns_tuple) — should we add them back as accepted kwargs? **Decision**: NO — message in TypeError is the migration path. Reviving them silently re-creates the silent-drop bug class.
- **Risk**: the 4 unhandled `kind` literals (`clustering`, `alignment`, `llm`, `agent`) — do the diagnostic classes exist? **Investigation needed at `/todos`**: grep `class.*Diagnostic` in diagnostics/. If yes, dispatch them. If no, raise with explicit "not yet implemented" message AND remove from the accepted-literals list — accepting a literal you can't dispatch is `rules/zero-tolerance.md` Rule 2 (stub/half-implementation).

### Release classification

**Split:** `data=` wiring is regression-class → **1.5.2 patch**. Aliases + unhandled-literal sweep are additive/restorative → **1.6.0 minor** (rides with #700's deprecation adapter).

## Cross-cutting plan elements

### Spec authority impact (per `rules/specs-authority.md` §5b)

This workstream edits 4 ml-_.md specs (`ml-tracking.md`, `ml-registry.md`, `ml-serving.md`, `ml-diagnostics.md`). Per §5b, every edit triggers full sibling re-derivation across the ml-_.md family (16 files). At `/redteam` we MUST run the sibling sweep:

```bash
ls specs/ml-*.md                                  # enumerate full sibling set
grep -l "_kml_model_versions" specs/ml-*.md        # ADR-1 references
grep -l "InferenceServer\|InferenceServerConfig" specs/ml-*.md   # ADR-2 references
grep -l "diagnose\|DLDiagnostics" specs/ml-*.md   # ADR-3 references
# Re-derive assertions for EACH matching sibling
```

### Release strategy

- **1.5.2 patch** (regression-class): #699 schema convergence (code-only), #701 `data=` wiring + unknown-kwargs TypeError + unhandled-literal sweep (if engines exist).
- **1.6.0 minor**: #700 MultiModelAdapter + from_registry_many, #701 aliases (`classifier`/`regressor`).
- **1.5.3 patch (conditional)**: migration 0005 for ≤1.4.x users IFF reported.

### Tier-2 regression coverage (per `rules/testing.md` § "End-to-End Pipeline Regression")

Three new DOCS-EXACT regression tests, one per ADR. Each name encodes the issue + canonical pipeline shape per Rule "test name MUST encode the constraint":

- `test_issue_699_tracker_registry_shared_store.py::test_tracker_and_registry_share_kml_model_versions_table`
- `test_issue_700_inference_server_legacy_adapter.py::test_inference_server_legacy_multi_model_adapter_predicts`
- `test_issue_700_inference_server_canonical.py::test_inference_server_canonical_per_model_predicts`
- `test_issue_701_diagnose_dl_dataloader.py::test_diagnose_dl_pytorch_dataloader_end_to_end`

### Cross-SDK posture (per `rules/cross-sdk-inspection.md` MUST Rule 1 + 3a)

All three issues verified ABSENT in `esperie/kailash-rs` (`01-analysis/cross-sdk-rs-audit.md`). **No issues to file at kailash-rs.** Per Rule 3a (Structural API-Divergence Disposition), each closure comment MUST link the cross-SDK audit AND record the structural reason kailash-rs is immune (trait-object backends, multi-model DashMap, no string-dispatched diagnose). Closure comments will land at `/release` time.

### Codify candidates

Captured in `02-plans/03-codify-candidates.md` for promotion at `/codify` after `/redteam` confirms the learnings hold:

1. **API deprecation cycle discipline** (#700 origin)
2. **Inline DDL outside migrations** as zero-tolerance Rule 1 violation (#699 origin)
3. **Brief-claim verification protocol** (3 brief inaccuracies in this workstream alone — pattern, not coincidence)
4. **Silent-drop kwargs as zero-tolerance Rule 3 instance** (#701 origin)
5. **Accepted-literals-without-dispatch as zero-tolerance Rule 2 instance** (#701 bonus finding)
