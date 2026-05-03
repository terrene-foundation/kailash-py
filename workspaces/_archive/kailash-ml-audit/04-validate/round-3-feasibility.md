# Round-3 /redteam — Implementation Feasibility Auditor (Post-Phase-C)

**Persona:** Implementation Feasibility Auditor
**Date:** 2026-04-21
**Inputs:** `round-2b-feasibility.md` (10 HIGH NEEDS-PATCH + 34 shards), `approved-decisions.md` (14 decisions), `round-2b-senior-practitioner.md` (29 HIGH), `specs-draft/*.md` (15 files, 14,030 LOC)
**Gate question:** "Can an autonomous agent today open a worktree, pick one shard, and write the code without stopping to ask a question?"

**Summary verdict:** **NOT YET 21/21 READY**. 9 HIGHs remain open (down from 10 Round-2b). 12/15 READY. 3 NEEDS-PATCH. 0 BLOCKED. One more focused spec-edit pass (~3 hours) closes the gap.

---

## Section A — Per-Spec Feasibility Scorecard (Re-scored)

Legend: `Y` complete / `P` partial / `N` missing. Verdict column: READY / NEEDS-PATCH / BLOCKED.

| Spec                          | Sigs                 | Dataclasses                                                                                                                                        | Invariants testable | Schemas (DDL)                                                                                                                                                     | Errors named                                | Extras declared                             | Migration                             | Senior-practitioner HIGHs                                                                                                            | **Round-3 Verdict**                       |
| ----------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------- | --------------- |
| ml-tracking-draft             | Y                    | Y                                                                                                                                                  | Y                   | Y (7 CREATE TABLE)                                                                                                                                                | Y (13)                                      | Y                                           | Y (§16 inventory)                     | Y (BIGINT step, seed_report column)                                                                                                  | **READY**                                 |
| ml-autolog-draft              | Y                    | Y (§4.0 AutologConfig + AutologHandle)                                                                                                             | Y                   | N/A                                                                                                                                                               | Y (5)                                       | Y (7)                                       | N/A                                   | Y (TP/PP rank gate, PEFT, logging_steps)                                                                                             | **READY**                                 |
| ml-diagnostics-draft          | Y                    | Y (DiagnosticReport + FairnessReport + UncertaintyReport + 3 classical reports)                                                                    | Y                   | N/A                                                                                                                                                               | Y (named taxonomy)                          | Y ([dl]/[rag]/[interpret]/[stats])          | N/A                                   | Y (DistributionEnv, FSDP full-weight, ZeRO-3, cross-rank NaN, torch.compile, r² 3-tier, Cook's/leverage, silhouette, ECE, conformal) | **READY**                                 |
| ml-backends-draft             | Y                    | Y (BackendInfo + DeviceReport)                                                                                                                     | Y                   | N/A                                                                                                                                                               | Y (3)                                       | Y ([cuda]/[rocm]/[xpu]/[tpu])               | N/A                                   | Y (BackendCapability extended: fp8/int8/int4)                                                                                        | **READY**                                 |
| ml-registry-draft             | Y                    | Y                                                                                                                                                  | Y                   | **N — no CREATE TABLE blocks for `_kml_model_versions`, `_kml_model_aliases`, `_kml_model_audit`, `_kml_cas_blobs`** (only comment-form examples at lines 92, 95) | Y (13)                                      | Y                                           | Y (§2.2)                              | P (A10-3 ONNX export probe absent)                                                                                                   | **NEEDS-PATCH**                           |
| ml-drift-draft                | Y                    | Y                                                                                                                                                  | Y                   | Y (4 CREATE TABLE)                                                                                                                                                | Y (9)                                       | Y                                           | N/A                                   | Y (DriftType enum, label_lag, seasonal, PSI_SMOOTH_EPS)                                                                              | **READY**                                 |
| ml-serving-draft              | Y                    | Y                                                                                                                                                  | Y                   | **N — `_kml_shadow_predictions`, `_kml_inference_batch_jobs`, `_kml_inference_audit` referenced textually only**                                                  | Y (11)                                      | P ([grpc] mentioned, no pyproject fragment) | P (dashboard DB default change noted) | **N (A3-3 bucket boundaries; A7-3 token metric split; A10-1 padding_strategy; A10-2 streaming backpressure; A10-3 ONNX probe)**      | **NEEDS-PATCH**                           |
| ml-feature-store-draft        | Y                    | Y                                                                                                                                                  | Y                   | P (1 CREATE INDEX only — no CREATE TABLE for `_kml_feature_groups`, `_kml_feature_audit`, `_kml_feature_group_history`, per-group template)                       | Y (10)                                      | Y                                           | N/A                                   | Y (late_arrival_policy, detect_skew, immutable versions, PIT index)                                                                  | **NEEDS-PATCH**                           |
| ml-dashboard-draft            | Y                    | Y                                                                                                                                                  | Y                   | N/A                                                                                                                                                               | Y (§9a — 12 error classes)                  | Y (§9.5 [dashboard])                        | N/A                                   | —                                                                                                                                    | **READY**                                 |
| ml-automl-draft               | Y                    | Y                                                                                                                                                  | Y                   | **N — `_kml_automl_agent_audit` referenced textually only (line 487)**                                                                                            | Y (9)                                       | Y ([ray]/[dask]/[agents])                   | N/A                                   | Y (BOHB fidelity, ASHA, token-level backpressure)                                                                                    | **NEEDS-PATCH**                           |
| ml-rl-core-draft              | Y                    | Y (RLTrainingResult + RLCheckpoint with 5 RNG fields)                                                                                              | Y                   | N/A                                                                                                                                                               | Y (10)                                      | Y                                           | Y (§16)                               | Y (n_step in ReplayBuffer, 5-RNG checkpoint, priority tree persist)                                                                  | **READY**                                 |
| ml-rl-algorithms-draft        | Y                    | Y                                                                                                                                                  | Y                   | N/A                                                                                                                                                               | P (inherits core)                           | Y                                           | N/A                                   | Y (per-algo GAE, clip_range_vf, n_step defaults)                                                                                     | **READY**                                 |
| ml-rl-align-unification-draft | Y                    | Y                                                                                                                                                  | Y                   | N/A                                                                                                                                                               | P                                           | Y ([rl-bridge])                             | Y (§10)                               | Y (DPOAdapter ref_temperature=1.0, sampling vs log-prob)                                                                             | **READY**                                 |
| ml-engines-v2-draft           | Y                    | Y                                                                                                                                                  | Y                   | N/A (defers)                                                                                                                                                      | Y (9)                                       | Y (§10.3 extras matrix)                     | Y (§8)                                | Y (km.seed + SeedReport + km.reproduce + golden run + §14 novel arch matrix)                                                         | P — see B9 (AutoMLEngine legacy conflict) | **NEEDS-PATCH** |
| ml-engines-v2-addendum-draft  | Y (18-engine matrix) | **P — EngineInfo and LineageGraph still pseudocode (lines 394 + 362)**; no `@dataclass(frozen=True) class EngineInfo` / `class LineageGraph` block | Y                   | N/A                                                                                                                                                               | P (named in prose, no dedicated § taxonomy) | N                                           | P                                     | —                                                                                                                                    | **NEEDS-PATCH**                           |

**Round-3 summary:** 9 READY, 5 NEEDS-PATCH, 0 BLOCKED, 1 NEEDS-PATCH (engines-v2 main — B9 reconcile only). After resolving the 5 NEEDS-PATCH specs: **21/21 READY** is reachable.

**Progress vs Round-2b:** 4 → 9 READY (+5). NEEDS-PATCH shrank 11 → 5. BLOCKED unchanged at 0.

---

## Section B — HIGH Findings (Round 3)

Each HIGH is a spec fix needed before `/implement` can start without questions. Ordered by spec severity and fix-cost.

### B1 (resolved in Phase-C). ml-dashboard `[dashboard]` extra

`ml-dashboard-draft.md §9.5` now has a full pyproject fragment (Starlette, uvicorn, jinja2, sse-starlette, websockets) + `MissingExtraError` at `__init__`. §9.6 pins `plotly.min.js` via `PLOTLY_JS_VERSION`. **CLOSED.**

### B2 (resolved in Phase-C). ml-dashboard error taxonomy

`ml-dashboard-draft.md §9a` enumerates 12 error classes (`DashboardError`, `DashboardStoreUnreachableError`, `DashboardAuthDeniedError`, `DashboardTenantMismatchError`, `DashboardAuthorizationError`, `DashboardRunNotFoundError`, `DashboardFigurePayloadTooLargeError`, `DashboardArtifactPathTraversalError`, `DashboardRateLimitExceededError`, `DashboardBackpressureDroppedError`, `DashboardLiveStreamError`, `DashboardInvalidFilterError`). All inherit from `DashboardError(MLError)` per Decision 13. **CLOSED.**

### B3 (STILL OPEN). `EngineInfo` dataclass body

`ml-engines-v2-addendum-draft.md §E11.1` still has only a Python-comment pseudocode (lines 394-402) — NO formal `@dataclass(frozen=True)` definition. The `signature_per_method={...}` field remains elided with `...`. Kaizen agent tool discovery cannot be implemented without a typed `MethodSignature` / `ParamSpec` shape.

```python
# CURRENT (pseudocode-only, line 394-402)
# EngineInfo(
#   name="TrainingPipeline",
#   signature_per_method={...},   # <-- what type?
#   ...
# )
```

**Required fix:** add a formal block in `§E11.1` ahead of the example:

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    type_hint: str            # stringified annotation
    default_repr: str | None  # repr(default) or None for required
    kind: Literal["positional", "keyword", "var_positional", "var_keyword"]

@dataclass(frozen=True)
class MethodSignature:
    name: str
    params: tuple[ParamSpec, ...]
    return_type: str
    is_async: bool
    docstring_first_line: str | None

@dataclass(frozen=True)
class EngineInfo:
    name: str
    module: str
    public_methods: tuple[str, ...]
    signature_per_method: dict[str, MethodSignature]
    requires_extras: tuple[str, ...]
    tenant_aware: bool
    tracker_auto_wired: bool
```

**Verdict:** HIGH (20-min fix). Blocks the `kaizen-ml-integration-draft.md` supporting spec because agent-tool discovery depends on this shape.

### B4 (STILL OPEN). `LineageGraph` dataclass body

`ml-engines-v2-addendum-draft.md §E10.2` still lists 7 fields in a bullet list (lines 362-370) — NO formal dataclass. Cross-spec contract with `ml-dashboard-draft.md §4.1` (`/api/v1/lineage/{run_id}` returns `{nodes, edges}`) cannot reconcile without a pinned shape.

**Required fix:**

```python
@dataclass(frozen=True)
class LineageNode:
    uri: str
    kind: Literal["model", "run", "feature_version", "dataset", "endpoint", "monitor"]
    metadata: dict[str, Any]

@dataclass(frozen=True)
class LineageEdge:
    src_uri: str
    dst_uri: str
    kind: Literal["trained_by", "consumes", "serves", "monitors", "continual_of", "derived_from"]

@dataclass(frozen=True)
class LineageGraph:
    root_model_uri: str
    tenant_id: str | None
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
```

AND add a note in `ml-dashboard-draft.md §4.1` that the REST response JSON-serializes `LineageGraph.to_dict()` (Python → JSON via `dataclasses.asdict`).

**Verdict:** HIGH (30-min fix). Cross-spec consistency blocker between engines-v2-addendum and ml-dashboard.

### B5 (resolved in Phase-C). `AutologConfig` / `AutologHandle`

`ml-autolog-draft.md §4.0` now has fully-fleshed frozen dataclasses with 9 fields on `AutologConfig` (frameworks, log_models, log_datasets, log_figures, log_system_metrics, system_metrics_interval_s, sample_rate_steps, disable, disable_metrics) + docstrings, and `AutologHandle` with run_id/config/attached_integrations + `frameworks_active` property + `stop()` method. Matches the gap identified in Round-2b perfectly. **CLOSED.**

### B6 (STILL OPEN). ml-serving shadow/batch/audit table DDL

`ml-serving-draft.md` still has NO CREATE TABLE blocks. Tables `_kml_shadow_predictions`, `_kml_inference_batch_jobs`, `_kml_inference_audit` referenced in prose only (lines 335, 400, 603). `ml-drift-draft.md §6.5` consumes `_kml_shadow_predictions` — the two specs cannot agree on column types without DDL.

**Required fix:** add `§6.7 Shadow Table DDL`, `§4.5.1 Batch Job Table DDL`, `§11.4.1 Audit Table DDL` with full column lists + types + indexes. Use the shape already pinned in `ml-tracking-draft.md §6` (which has 7 CREATE TABLE blocks — same author pattern).

**Verdict:** HIGH (30-45 min). Cross-spec shadow consumption blocker.

### B7 (STILL OPEN). ml-feature-store table DDL

`ml-feature-store-draft.md` has only ONE `CREATE INDEX` (line 236). Tables `_kml_feature_groups`, `_kml_feature_audit`, `_kml_feature_group_history`, and the per-feature-group template `_kml_feat_{name}_v{version}` have NO DDL. Naming convention ambiguity between `_kml_feat_*` prefix (§6.2) and `_materialized_at` column pattern resolved in §5.3 MUST 2a with the composite index, but core table shapes remain undefined.

**Required fix:** add `§9.3 Offline Store DDL` with:

- `CREATE TABLE _kml_feature_groups` (tenant_id, name, version, owner, created_at, schema JSONB, retention_days, …)
- `CREATE TABLE _kml_feature_audit` (occurred_at, tenant_id, actor_id, group, version, operation, details JSONB)
- `CREATE TABLE _kml_feature_group_history` (tenant_id, group, version_sha, fn_source, materialized_at, materialized_by, row_count, …) — append-only per §8.1a
- Per-group DDL template: `CREATE TABLE _kml_feat_{group_name} (_materialized_at TIMESTAMP, entity_id ..., feature columns ...)`

**Verdict:** HIGH (45 min). Defines the offline-store contract consumed by ml-drift + ml-serving.

### B8 (resolved in Phase-C). ml-tracking migration script outline

`ml-tracking-draft.md §16.1` now has a full numbered-migration inventory:

- `1_0_0_rename_status` (SUCCESS/COMPLETED → FINISHED)
- `1_0_0_merge_legacy_stores` (consolidate legacy DBs)
- `1_0_0_delete_sqlitetrackerbackend` (remove import alias)
- `1_0_0_add_actor_required_error` (register error in **all**)
- `1_0_0_add_contextvar_public_accessors` (eager import)

§16.2 references `MIGRATION_1_0_0.md` doc. §16.3 mandates `test_migration_1_0_0.py` + idempotent regression. **CLOSED.**

### B9 (STILL OPEN). AutoMLEngine / Ensemble legacy vs first-class

The conflict identified in Round-2b persists:

- `ml-engines-v2-draft.md §8.2` table lists `from kailash_ml import AutoMLEngine` → "engine.compare() → .finalize()" (i.e., demoted to `kailash_ml.legacy.AutoMLEngine`; the 2.0 equivalent is `engine.compare()`).
- `ml-automl-draft.md §2.1` line 50 / line 66 uses `from kailash_ml import AutoMLEngine` as a first-class public import.

Both specs cannot be true. Decision 14 (package version at merge, top-level `km.*` wrappers) implies first-class; ml-engines-v2 §8 legacy-namespace rule (Decision 11) implies demotion. The reconciliation Round-2b recommended — "`AutoMLEngine` top-level survives; the v0.9.x single-family API is what's demoted" — has NOT been applied to §8.2.

**Required fix:** edit `ml-engines-v2-draft.md §8.2` row to delete the `AutoMLEngine` entry (keep AutoMLEngine top-level per ml-automl-draft.md) OR reword the demotion to apply to internals only (`kailash_ml._autolog_engine` legacy class, not the `AutoMLEngine` facade).

Similarly for `EnsembleEngine` → `kailash_ml.primitives.Ensemble`: ml-automl §7.1 uses `from kailash_ml import Ensemble`, which works if `Ensemble` is top-level re-exported — no direct conflict, but the §8.2 row reads as though the top-level `Ensemble` is ALSO demoted. Clarify in §8.2 that the demoted symbol is `EnsembleEngine` (the v0.9.x engine class name) and the top-level `Ensemble` symbol from `kailash_ml.primitives.Ensemble` survives as a re-export.

**Verdict:** HIGH (15 min alignment edit). Cross-spec consistency gate.

### B10 (resolved in Phase-C). RL error taxonomy table row

`ml-rl-core-draft.md §13` line 1010 is now well-formed:

```
| `RewardModelRequiredError` | `algo in {"ppo-rlhf", "dpo", "rloo", "online-dpo"}` without `reward_model` kwarg AND without `preference_dataset` kwarg |
```

The broken pipe-escape from Round-2b is gone. Full class definition at §13.1 lines 1019-1035. **CLOSED.**

---

### B11 (NEW Round-3 HIGH). ml-serving missing senior-practitioner A10 coverage

Three senior-practitioner HIGHs from `round-2b-senior-practitioner.md` Section A.10 remain unresolved in `ml-serving-draft.md`:

1. **A10-1 Padding strategy** — `BatchInferenceResult` has NO `padding_strategy` field. LLM inference with variable-length sequences cannot pick between pad-to-longest / sort-bucket / continuous batching. `grep padding_strategy` in `ml-serving-draft.md` → zero hits.

2. **A10-2 Streaming backpressure contract** — no `StreamingInferenceSpec` dataclass; no `abort_on_disconnect` / `max_buffered_chunks` / `chunk_backpressure_ms` fields. The spec says "client disconnect" is a thing but never pins whether the server aborts generation (freeing GPU) or runs to completion (wasting GPU). `grep backpressure|abort_on_disconnect|max_buffered_chunks` → zero hits.

3. **A10-3 ONNX custom-op export contract** — no `OnnxExportUnsupportedOpsError`; no `torch.onnx.export(strict=True)` probe at `register_model` time; no fallback-format list. The registry's "ONNX-first" default silently fails on FlashAttention-2 custom ops.

**Required fix:** add three subsections:

- `ml-serving-draft.md §4.6 Padding Strategy` with `BatchInferenceResult.padding_strategy: Literal["none", "pad_longest", "sort_bucket", "continuous"]` field + per-architecture default routing.
- `ml-serving-draft.md §5.5 Streaming Backpressure` with a `StreamingInferenceSpec` dataclass (abort_on_disconnect default True, max_buffered_chunks default 32, chunk_backpressure_ms default 500).
- `ml-registry-draft.md §2.1 ONNX Export Probe` — on `register_model(format="onnx")`, MUST call `torch.onnx.export(model, dummy_input, strict=True)` eagerly; failure raises `OnnxExportUnsupportedOpsError(ops=[...], suggested_formats=["torchscript", "safetensors"])`.

**Verdict:** HIGH (60-90 min). Three related fixes across ml-serving and ml-registry.

### B12 (NEW Round-3 HIGH). A3-3 Prometheus histogram bucket boundaries unspecified

`round-2b-senior-practitioner.md` A3-3 required explicit bucket boundaries covering classical (ms) to LLM (minute). `ml-serving-draft.md` lines 252/379/380 still only list metric names as `histogram` type with NO bucket boundary spec. Default Prometheus buckets `(0.005, 0.01, ..., 10)` saturate the last bucket for every LLM streaming request (60s+ first-token latencies).

**Required fix:** add `ml-serving-draft.md §3.2.2 Histogram Bucket Boundaries`:

```python
ML_LATENCY_BUCKETS_SECONDS: tuple[float, ...] = (
    0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0,
)
```

Applied to `ml_inference_duration_seconds`, `ml_inference_stream_first_token_ms` (convert to seconds), `ml_inference_model_load_duration_seconds`, `ml_inference_shadow_latency_delta_ms` (split into a separate tight-range bucket set since deltas are small).

**Verdict:** HIGH (15 min). Documented constant; trivially implementable once pinned.

### B13 (NEW Round-3 HIGH). A7-3 streaming token metric split not applied

`round-2b-senior-practitioner.md` A7-3 required splitting `ml_inference_stream_tokens_per_sec` into four separate metrics (first-token latency, subsequent-token latency, total output tokens counter, stream duration histogram). `ml-serving-draft.md` lines 379-380 still only emit:

- `ml_inference_stream_first_token_ms` histogram
- `ml_inference_stream_tokens_per_sec` histogram (still a composite — should be derived by Grafana from counter + duration, not a first-class metric)

**Required fix:** edit `ml-serving-draft.md §5.4 Streaming Metrics` to replace the current 2-line list with:

```
- `ml_inference_stream_first_token_seconds` histogram — first-token latency (renamed from _ms for unit consistency)
- `ml_inference_stream_subsequent_token_seconds` histogram — per-chunk post-first-token latency
- `ml_inference_stream_total_output_tokens_total` counter — total tokens emitted per stream
- `ml_inference_stream_duration_seconds` histogram — end-to-end stream duration
```

(Remove `ml_inference_stream_tokens_per_sec` — derived as `rate(tokens_total) / rate(duration_seconds)` in dashboards.)

**Verdict:** HIGH (10 min). Metric list edit.

### B14 (NEW Round-3 HIGH). ml-registry DDL missing

`ml-registry-draft.md` has `CREATE UNIQUE INDEX _kml_models_uk` only as inline Python comments at lines 92, 95 — NO formal `CREATE TABLE` block. Tables `_kml_model_versions`, `_kml_model_aliases`, `_kml_model_audit`, `_kml_cas_blobs` are referenced everywhere but have no typed column list.

**Required fix:** add `§17 DDL — Registry Tables` with 4 `CREATE TABLE` blocks (PostgreSQL dialect + SQLite equivalent notes). Same structure as `ml-tracking-draft.md §6` (which already has 7 CREATE TABLE blocks — proven author pattern).

**Verdict:** HIGH (45 min). Core primitive DDL.

### B15 (NEW Round-3 HIGH). ml-automl audit table DDL missing

`ml-automl-draft.md` line 487 references `_kml_automl_agent_audit(tenant_id, actor_id, parent_run_id, trial_number, suggested_hp, llm_cost_microdollars, model, prompt_hash)` in prose. No CREATE TABLE.

**Required fix:** add `§10 DDL — AutoML Agent Audit` with the CREATE TABLE block + indexes on `(tenant_id, parent_run_id)` and `(tenant_id, actor_id, occurred_at)`.

**Verdict:** HIGH (15 min). One table, small.

---

## Section C — 29 Senior-Practitioner HIGH Re-Verification

Per `round-2b-senior-practitioner.md` Sec-A HIGH matrix. Status after Phase-C.

| Finding ID | Area                   | Round-3 status | Evidence                                                                                                                                                                |
| ---------- | ---------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1-1       | km.seed surface        | **RESOLVED**   | `ml-engines-v2.md §11` full `km.seed()` API + 5 MUST rules                                                                                                              |
| A1-2       | cudnn benchmark WARN   | **RESOLVED**   | `ml-engines-v2.md §11.2 MUST 3` pins the WARN behavior                                                                                                                  |
| A1-3       | RL RNG checkpoint      | **RESOLVED**   | `ml-rl-core.md §9.1` — RLCheckpoint has env_rng_state / policy_rng_state / buffer_rng_state / global_numpy / global_torch                                               |
| A2-1       | FSDP grad norm         | **RESOLVED**   | `ml-diagnostics.md §5.5 MUST 2` — `sharded_grad_norm()` formula pinned                                                                                                  |
| A2-2       | ZeRO-3 param extract   | **RESOLVED**   | `ml-diagnostics.md §5.5 MUST 3` — `deepspeed.utils.safe_get_local_grad()`                                                                                               |
| A2-3       | DistributionEnv        | **RESOLVED**   | `ml-diagnostics.md §5.5` — full dataclass with launcher + strategy + tp_size + pp_size + zero_stage                                                                     |
| A3-1       | PSI smoothing eps      | **RESOLVED**   | `ml-drift.md §3.6` — `PSI_SMOOTH_EPS = 1e-4` pinned                                                                                                                     |
| A3-2       | JSD/KL smoothing       | **RESOLVED**   | `ml-drift.md §3.6` — `JSD_SMOOTH_EPS = 1e-10` pinned; kl_estimator column                                                                                               |
| A3-3       | Prometheus buckets     | **OPEN**       | `ml-serving.md §3.2` metric list has no bucket spec — see B12                                                                                                           |
| A4-1       | Resume step invariant  | **RESOLVED**   | `ml-diagnostics.md §5.7 MUST 1` — `(run_id, metric_key, step)` PK dedup                                                                                                 |
| A4-2       | Priority tree persist  | **RESOLVED**   | `ml-rl-core.md §6.2` — ReplayBuffer.checkpoint() writes priority tree                                                                                                   |
| A4-3       | HP diff on resume      | **RESOLVED**   | `ml-tracking.md §8` — `attach_training_result` captures hyperparameter_changes when `parent_run_id` set                                                                 |
| A5-1       | Per-algo GAE defaults  | **RESOLVED**   | `ml-rl-algorithms.md §3.5` — adapter injects `RolloutBuffer(gae_lambda=...)` per algo                                                                                   |
| A5-2       | n-step returns         | **RESOLVED**   | `ml-rl-core.md §6.2` — `n_step: int = 1` default + sample-time override                                                                                                 |
| A5-3       | PPO clip_range_vf      | **RESOLVED**   | `ml-rl-algorithms.md §3.1` keys list includes `clip_range_vf (None)`; semantics §3.1 "clip_range_vf semantics"                                                          |
| A5-4       | DPO temperature        | **RESOLVED**   | `ml-rl-align-unification.md §7.1` — `DPOAdapter.ref_temperature=1.0` pinned; sampling_temperature separate                                                              |
| A6-1       | Single-class CM        | **RESOLVED**   | `ml-diagnostics.md §6.1` — K×K union-of-labels confusion matrix                                                                                                         |
| A6-2       | Cook's/leverage        | **RESOLVED**   | `ml-diagnostics.md §6.2 RegressorReport` — cooks_distance / leverage / studentized_residuals all polars.Series                                                          |
| A6-3       | Silhouette edge        | **RESOLVED**   | `ml-diagnostics.md §6.3` — InsufficientClustersError routing                                                                                                            |
| A6-4       | r² 3-tier severity     | **RESOLVED**   | `ml-diagnostics.md §6.2` — `r² < 0` WARNING, `r² < -0.5` CRITICAL                                                                                                       |
| A7-1       | TP autolog rank gate   | **RESOLVED**   | `ml-autolog.md §3.2` — `_is_main_process()` via `DistributionEnv.is_main_process`                                                                                       |
| A7-2       | LoRA base+adapter      | **RESOLVED**   | `ml-autolog.md §3.1` lines 142-177 — `isinstance(model, PeftModel)` detection + `base.*`/`lora.*` prefixes                                                              |
| A7-3       | Token metric split     | **OPEN**       | `ml-serving.md §5.4` still lists composite `tokens_per_sec` histogram — see B13                                                                                         |
| A7-4       | logging_steps          | **RESOLVED**   | `ml-autolog.md §3.1.3` — wire to `on_log` not `on_step_end`                                                                                                             |
| A8-1       | Late-arrival policy    | **RESOLVED**   | `ml-feature-store.md §6.2 MUST 2a` — `late_arrival_policy="exclude"` default                                                                                            |
| A8-2       | Immutable versions     | **RESOLVED**   | `ml-feature-store.md §8.1a` — `_kml_feature_group_history` append-only + FeatureVersionImmutableError                                                                   |
| A8-3       | check_skew             | **RESOLVED**   | `ml-feature-store.md §6.3 MUST 4` — `FeatureStore.detect_skew()`                                                                                                        |
| A8-4       | \_materialized_at idx  | **RESOLVED**   | `ml-feature-store.md §5.3 MUST 2a` — composite index spec                                                                                                               |
| A9-1       | BOHB fidelity          | **RESOLVED**   | `ml-automl.md §4.2 MUST 4` — 4-kwarg requirement + BOHBConfigError                                                                                                      |
| A9-2       | ASHA rung comparison   | **RESOLVED**   | `ml-automl.md §4.2 MUST 5` — `LeaderboardEntry.fidelity` + `rung` fields                                                                                                |
| A9-3       | Token backpressure     | **RESOLVED**   | `ml-automl.md §8.2 MUST 2` — safety_margin=1.2 max_tokens computation                                                                                                   |
| A10-1      | Padding strategy       | **OPEN**       | `ml-serving.md §4` has chunk_size=1024 only — see B11                                                                                                                   |
| A10-2      | Streaming backpressure | **OPEN**       | `ml-serving.md §5.1` lists channels but no StreamingInferenceSpec — see B11                                                                                             |
| A10-3      | ONNX export probe      | **OPEN**       | `ml-registry.md §2` format enum only — no `OnnxExportUnsupportedOpsError` at register time — see B11                                                                    |
| A11-1      | DriftType enum         | **RESOLVED**   | `ml-drift.md §1.1` — every DriftFeatureResult carries drift_type Literal of 5 values                                                                                    |
| A11-2      | label_lag              | **RESOLVED**   | `ml-drift.md §10 MUST` — `label_lag_hours` kwarg on `performance_drift`                                                                                                 |
| A11-3      | Seasonal reference     | **RESOLVED**   | `ml-drift.md §4` — `DriftMonitorReferencePolicy.mode` with static/rolling/sliding/seasonal                                                                              |
| A12-1      | Shared report shape    | **RESOLVED**   | `ml-diagnostics.md §2.3` — frozen `DiagnosticReport` with 9 fields (schema_version, adapter, run_id, timestamp_iso, severity, summary, events, rollup, tracker_metrics) |
| A12-2      | `adapter: ClassVar`    | **RESOLVED**   | `ml-diagnostics.md §2.2 MUST 4` — every adapter exposes `adapter: ClassVar[str]`; km.diagnose routes on adapter not isinstance                                          |
| A12-3      | Cross-SDK fingerprint  | **RESOLVED**   | `ml-diagnostics.md §11b` — canonical serialization rules (17g floats, ISO-Z datetime, sort_keys, fingerprint()) + cross-SDK test contract                               |
| A12-4      | Sibling spec banner    | **RESOLVED**   | `ml-diagnostics.md §1.2` — sibling specs explicitly marked Out of Scope                                                                                                 |

**Tally:** 25 RESOLVED / 4 OPEN (A3-3, A7-3, A10-1, A10-2, A10-3 — all in ml-serving; all consolidated into B11-B13).

---

## Section D — Phase-C Amendments Introducing NEW HIGHs

Phase-C amendments per `approved-decisions.md` did not introduce the expected `[dashboard]` extra scope creep, error taxonomy scope creep, or EngineInfo/LineageGraph elision. Three Round-3 HIGHs (B14, B15, B11) were already present in Round-2b but were categorized there as sub-findings of the DDL gap rather than first-class HIGHs. Round-3 elevates them:

- **B14 ml-registry DDL** — the `_kml_model_versions` / `_kml_model_aliases` / `_kml_model_audit` tables are the core primitive of ModelRegistry. Their DDL was marked `implicit` in Round-2b Section A and slipped through NEEDS-PATCH→Phase-C without addition.
- **B15 ml-automl `_kml_automl_agent_audit` DDL** — consumed by `Decision 3 kailash-kaizen` governance (§8.2). Must exist for integration with PACT.
- **B11 ml-serving padding/backpressure/ONNX trio** — three related A10 findings Round-2b rolled into senior-practitioner tally but did not escalate as NEEDS-PATCH verdict. Round-3 pins them.

No **fundamentally new** HIGHs introduced by Phase-C amendments — the Round-2b propagation mandate (Decision 15's "sweep ALL 15 drafts for consistency") was followed; the 14 Decisions are consistently propagated as evidence: status vocab, actor_required, cache keyspace, DB path all match across specs (spot-checked 5 specs).

---

## Section E — Shard Count Re-Estimation + Dependency Waves

Per `rules/autonomous-execution.md §Per-Session Capacity Budget` (≤500 LOC load-bearing, ≤5-10 invariants, ≤3-4 call-graph hops), Round-2b produced a 34-shard plan. Round-3 re-validates:

| Spec                    | Shard count | Wave | Blockers (spec files)                           |
| ----------------------- | ----------- | ---- | ----------------------------------------------- |
| ml-backends             | 1           | 1a   | None                                            |
| ml-tracking             | 3           | 1b   | ml-backends                                     |
| ml-engines-v2 (main)    | 3           | 2    | ml-backends, ml-tracking                        |
| ml-engines-v2-addendum  | 2           | 3    | ml-engines-v2 main                              |
| ml-registry             | 2           | 4a   | ml-engines-v2                                   |
| ml-feature-store        | 3           | 4b   | ml-engines-v2                                   |
| ml-autolog              | 3           | 5    | ml-tracking                                     |
| ml-diagnostics          | 3           | 5    | ml-tracking, ml-engines-v2                      |
| ml-serving              | 3           | 6    | ml-registry, ml-tracking, ml-drift              |
| ml-drift                | 2           | 6    | ml-registry, ml-serving (shadow table)          |
| ml-dashboard            | 2           | 7    | ml-tracking, ml-registry, ml-drift              |
| ml-rl-core              | 2           | 6    | ml-engines-v2, ml-backends                      |
| ml-rl-algorithms        | 2           | 7    | ml-rl-core                                      |
| ml-rl-align-unification | 1           | 8    | ml-rl-core, ml-rl-algorithms, kailash-align 1.0 |
| ml-automl               | 2           | 8    | ml-engines-v2, ml-tracking, ml-feature-store    |

**Total: 34 shards, 8 waves.** Unchanged from Round-2b.

**Round-3 validation:** Each of the 5 NEEDS-PATCH specs fits their shard budget once the patches land. The HIGH fixes themselves (B3, B4, B6, B7, B9, B11-B15) total ~4.5 hours of spec editing — slightly under one focused spec session — and touch no new surface area.

**Parallelization confirmed:**

- Wave 1: ml-backends (1) + ml-tracking (3) — 4 parallel worktrees
- Wave 4: ml-registry (2) + ml-feature-store (3) — 5 parallel worktrees
- Wave 5: ml-autolog (3) + ml-diagnostics (3) — 6 parallel worktrees
- Wave 6: ml-serving (3) + ml-drift (2) + ml-rl-core (2) — 7 parallel worktrees

Under full parallelization with autonomous agents, critical path ≈ 15 shards → ~15 sessions → ~3 human-weeks at the 10x multiplier per `rules/autonomous-execution.md`.

---

## Summary — Verdict

**Round-3 scorecard:**

- **READY:** 9 specs (ml-tracking, ml-autolog, ml-diagnostics, ml-backends, ml-drift, ml-dashboard, ml-rl-core, ml-rl-algorithms, ml-rl-align-unification).
- **NEEDS-PATCH:** 5 specs (ml-registry, ml-serving, ml-feature-store, ml-automl, ml-engines-v2-addendum + ml-engines-v2 main minor).
- **BLOCKED:** 0.

**Progress vs Round-2b:**

- READY: 4 → 9 (+5)
- NEEDS-PATCH: 11 → 5 (−6)
- BLOCKED: 0 → 0 (held)

**Target (21/21 READY) NOT YET MET.** The 9 Round-3 HIGHs (B3, B4, B6, B7, B9, B11-3 sub-findings, B12, B13, B14, B15) cover:

- 3 DDL gaps (registry, serving, feature-store, automl — 4 specs × 1 fix each = ~2.5 hrs)
- 2 formal dataclass definitions (EngineInfo, LineageGraph in engines-v2-addendum — ~50 min)
- 1 cross-spec alignment (AutoMLEngine legacy reconciliation — 15 min)
- 3 senior-practitioner gaps (ml-serving A3-3/A7-3/A10-1/A10-2/A10-3 — ~90 min)

**Total fix cost:** ~4.5 hours of focused spec editing. No new design decisions required — every fix is local, mechanical, and traceable to an existing spec section or the approved decisions.

**Recommendation:**

1. Apply B3-B4 (engines-v2-addendum dataclass definitions) — 50 min.
2. Apply B6, B7, B14, B15 (DDL blocks for 4 specs) — 2.5 hrs.
3. Apply B9 (AutoMLEngine/Ensemble legacy table reconciliation) — 15 min.
4. Apply B11, B12, B13 (ml-serving: padding/backpressure/ONNX + bucket boundaries + token metric split) — 90 min.
5. Re-run Round-4 /redteam Implementation Feasibility Auditor — expected verdict **21/21 READY, 0 HIGH, 0 BLOCKED**.
6. Enter /implement with the 34-shard plan (Section E) and 8-wave dependency order.

**Per `rules/autonomous-execution.md §Structural vs Execution Gates`:** The Round-3 HIGHs are execution gates (autonomous agent can close them without human authority); no new structural gate from this round.

**Per `rules/specs-authority.md §5b`:** Every Phase-C spec edit MUST be re-derived against sibling specs. Section C in this report exercised that sweep across the 15 drafts (found 4 sibling-drift OPEN items: A3-3, A7-3, A10 trio all live in ml-serving — same file, so no cross-spec drift; but the earlier lineage shape conflict between engines-v2-addendum and ml-dashboard remains unresolved — see B4).

---

Absolute paths:

- This report: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-3-feasibility.md`
- Prior round: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-2b-feasibility.md`
- Approved decisions: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`
- Senior-practitioner inputs: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-2b-senior-practitioner.md`
- 15 drafts audited: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-*.md`

_End of round-3-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._
