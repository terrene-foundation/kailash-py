# kailash-ml Changelog

## [0.15.2] - 2026-04-20 — bundled audit-finding hotfix (log hygiene + identifier safety)

Resolves four deferred audit findings from the 2026-04-20 late-session `/redteam` that were intentionally held over for next-session disposition per `workspaces/kailash-ml-gpu-stack/.session-notes`. All four live in `kailash-ml/` and ship in this one bundled patch.

### Fixed

- **M1 — `engine.py:2787-2794` WARN log leaked raw onnx-export `cause` string** (post-release security-reviewer MED-1): the WARN-level log emitted the full chained exception message verbatim, which could contain ONNX framework internals and schema-revealing strings. Per `rules/observability.md` §8 (schema-revealing field names at DEBUG or hashed), the raw `cause` now logs at DEBUG and the WARN emits a 4-hex fingerprint (`fingerprint(cause) & 0xFFFF:04x`) suitable for correlation without leaking content. Regression: `tests/regression/test_issue_m1_onnx_cause_hygiene.py`.
- **M2 — `model_name` at WARN across 6 `engine.py` log sites** (post-release security-reviewer MED-2): the `model_name` field (a schema-revealing identifier) appeared unhashed at WARN in six log sites. Each site now hashes `model_name` via `fingerprint(model_name) & 0xFFFF:04x` before emitting at WARN; DEBUG-level diagnostics retain the raw value for authorized investigation windows. Regression: `tests/regression/test_issue_m2_model_name_hygiene.py`.
- **L1 — `engines/_feature_sql.py` used `_validate_identifier` instead of canonical `quote_identifier` at 5 DDL sites** (post-release gold-standards LOW-1): per `rules/dataflow-identifier-safety.md` MUST Rule 1, every dynamic DDL identifier MUST route through `dialect.quote_identifier()` (which BOTH validates AND quotes), not `_validate_identifier()` (which validates only). Migrated five sites: `create_feature_table` (CREATE TABLE + CREATE INDEX), `get_features_latest` (SELECT + ROW_NUMBER), `get_features_as_of`, `get_features_range`, and `upsert_batch`. Regression: `tests/regression/test_issue_l1_feature_sql_quote_identifier.py`.
- **L2 — `tracking/sqlite_backend.py:150` ALTER TABLE hardcoded list missing `_validate_identifier`** (post-release gold-standards LOW-2): the `_COLUMNS_ADDED_IN_0_14` hardcoded list was interpolated into `f"ALTER TABLE experiment_runs ADD COLUMN {name} {sql_type}"` without routing through `_validate_identifier`. Per `rules/dataflow-identifier-safety.md` MUST Rule 5 (Hardcoded Identifier Lists MUST Still Validate), "the list is hardcoded" is BLOCKED as a rationalization — the validation call is a permanent marker of intent that survives any future refactor that makes the list dynamic. The loop now calls `_validate_identifier(name)` before interpolation. Regression: `tests/regression/test_issue_l2_sqlite_backend_alter_table_validation.py`.

## [0.15.1] - 2026-04-20 — post-release audit hotfix (tenant-isolation + spec sync)

Post-release `/redteam` audit of 0.15.0 (security-reviewer + reviewer + gold-standards-validator) surfaced one HIGH security finding and one HIGH spec-staleness finding. Both fixed in this patch.

### Fixed

- **Cross-tenant bypass in `_check_tenant_match`** (security-reviewer HIGH-1): `MLEngine._check_tenant_match` silently permitted an unscoped engine (`tenant_id=None`) to load a tenant-scoped model. Per `specs/ml-engines.md §5.1 MUST 3` and `rules/tenant-isolation.md` Rule 2 ("Missing tenant_id Is a Typed Error"), the unscoped-engine branch against a tenant-scoped model MUST raise `TenantRequiredError`, not pass silently. Fix: the check now raises with an actionable message naming `MLEngine(tenant_id=...)` as the fix. Regression test at `tests/regression/test_tenant_isolation_unscoped_engine.py` (5 cases) locks all four combinations of (engine tenant ∈ {None, "acme"}) × (model tenant ∈ {None, "acme"}).

### Changed

- **`specs/ml-engines.md §12.1` updated** (reviewer HIGH-1 / gold-standards MED-1): Phase status table now reflects shipped state — header bumped to "kailash-ml 0.15.0", 7-row Phase 3/4/5 table replaced with the 2 remaining intentional deferrals (non-holdout split strategies + grpc extras-guard). §12.2 2.0.0 gate items now marked `[x]` for the five satisfied by 0.15.0 (8-method surface, typed dataclass returns, TrainingResult 10-field contract, cache-key "default" forbidden, OnnxExportError on failure).

## [0.15.0] - 2026-04-20 — MLEngine Phase 3/4/5 complete (specs/ml-engines.md §12.1)

Closes the full Phase 3/4/5 punch list from `specs/ml-engines.md §12.1`. All eight documented `MLEngine` methods (`setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`) now have production implementations. Landed via four parallel worktree shards (PRs #561/#562/#563/#564) + prep commit (7 frozen result dataclasses in `_results.py`).

### Added — Phase 3 (`setup` + `compare` + `finalize`)

- **`MLEngine.setup()`** (PR #561): polars-native data profiling, `schema_hash` idempotency key per §2.1 MUST 6, task-type inference (classification/regression), deterministic holdout split, FeatureStore schema registration with tenant_id persistence. Phase 3.1 (kfold/stratified/walk_forward split strategies) deferred with a loud `NotImplementedError` naming the follow-up.
- **`MLEngine.compare()`** (PR #562): multi-family Lightning sweep. Every family routed through `self.fit()` so Lightning-as-spine holds by construction per §2.1 MUST 7. Default family set derived from task_type (sklearn/xgboost/lightgbm for classification/regression). Best-first leaderboard via `_HIGHER_IS_BETTER_METRICS` / `_LOWER_IS_BETTER_METRICS` sets. Partial-result on timeout + structured WARN log. `ComparisonResult.tenant_id` propagates from engine, every inner `TrainingResult` echoes tenant_id.
- **`MLEngine.finalize()`** (PR #562): retrain on train+holdout (`full_fit=True`) or re-wrap without retrain (`full_fit=False`). Accepts either a `TrainingResult` or a `models://name/v<N>` URI string.

### Added — Phase 4 (`predict` + `evaluate` + `register`)

- **`MLEngine.predict()`** (PR #563): registry hydration + three-channel dispatch (`direct` = in-process onnxruntime, `rest` = Nexus-bound endpoint, `mcp` = stdio transport). Typed `TenantRequiredError` when engine tenant_id does not match the registered model's tenant_id. `ModelNotFoundError` with actionable message when rest/mcp channels are requested without prior `serve()`. Structured entry/exit logs per `rules/observability.md`.
- **`MLEngine.evaluate()`** (PR #562): three modes (holdout/shadow/live). Holdout = offline scoring with default metric set from task_type. Shadow = score + audit as `shadow_evaluate` without drift-monitor update. Live = score + audit as `evaluate` AND update DriftMonitor. Typed `TargetNotFoundError` when target column missing from data.
- **`MLEngine.register()`** (PR #561): 6-framework ONNX-default export via existing `OnnxBridge` (sklearn/xgboost/lightgbm/catboost/torch/lightning). Typed `OnnxExportError` on default-path failure — silent pickle fallback BLOCKED per §4.2 MUST 4. Tenant-aware `(tenant_id, name, version)` primary key on `_kml_model_versions`. `§5.2` audit row written even on failure.

### Added — Phase 5 (`serve`)

- **`MLEngine.serve()`** (PR #563): REST + MCP + gRPC multi-channel bind from a single call per §2.1 MUST 10. REST channel via Nexus, MCP channel via kailash-mcp stdio transport. Per-channel URIs returned in `ServeResult.uris`. Partial-failure rollback — if MCP bind fails after REST bind succeeds, REST is shut down and a typed error is raised (no partial `ServeResult`). Tenant-id propagated to each channel's auth context. gRPC channel requires the `[grpc]` optional extra (loud-failure pattern per `rules/dependencies.md` § Exception).

### Added — new infrastructure

- **7 frozen result dataclasses** in `kailash_ml._results` (`SetupResult`, `ComparisonResult`, `PredictionResult`, `RegisterResult`, `EvaluationResult`, `ServeResult`, `FinalizeResult`). Field shapes are a contract — shards imported them rather than redefining, preventing the parallel-ownership race `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination" documents.
- **`kailash_ml.engines._engine_sql`** (PR #561): identifier-validated DDL helper module for MLEngine auxiliary tables (`_kml_engine_versions`, `_kml_engine_audit`) per `rules/dataflow-identifier-safety.md`.
- **22 new Tier 2 integration test files** across four shards, covering idempotency, tenant propagation, ONNX matrix, export-failure → typed-error path, multi-family compare, shadow/live evaluate modes, direct/rest/mcp predict channels, multi-channel serve, partial-failure rollback, REST tenant-isolation.

### Known deferrals (intentional)

- **`split_strategy != "holdout"` in `setup()`**: kfold / stratified_kfold / walk_forward raise `NotImplementedError` naming Phase 3.1 as the follow-up. Tracked at `workspaces/kailash-ml-gpu-stack/journal/.pending/`.
- **`serve(channels=["grpc"])`**: requires `pip install kailash-ml[grpc]`. Loud-failure `NotImplementedError` naming the extra per `rules/dependencies.md` § Exception.
- **`PredictionResult.device`**: nullable; populated in kailash-ml 0.12.1+ only after fit → immediate-predict. Restored-from-registry predictions carry `None` until 0.15.1 per `specs/ml-engines.md §4.2 MUST 6`.

### Changed

- `kailash_ml.__all__` now exports the 7 new result dataclasses (eager-imported per `rules/orphan-detection.md` §6).
- `MLEngine.engine.py` grew from 676 LOC → ~1800 LOC; helpers split across `_engine_sql.py` (267 LOC) + module-level serve/predict plumbing.

## [0.14.0] - 2026-04-20 — km.doctor + km.track spec completion (ml-backends.md §7, ml-tracking.md §2.4)

Closes the two HIGH findings from the 2026-04-20 /redteam audit: km.doctor shipped 4 of 14 spec items (§7) and km.track persisted 10 of 17 auto-capture fields (§2.4). Both surfaces now ship the full spec-mandated coverage.

### Added — `km.doctor` full §7.1 diagnostic surface (closes #547 follow-up)

- **XPU + TPU probes** — `km.doctor()` now probes all six first-class backends per `specs/ml-backends.md` §1 (adds `xpu` via native `torch.xpu` at torch ≥ 2.5, and `tpu` via `torch_xla`). Status `"missing"` on non-Intel / non-TPU hosts.
- **`precision_matrix`** — per-backend auto-selected precision via `kailash_ml._device.detect_backend` + `resolve_precision`. Matches the concrete precision strings the training pipeline would pass to `L.Trainer(precision=...)`.
- **`extras`** — installed status for `[cuda]`, `[rocm]`, `[xpu]`, `[tpu]`, `[dl]`, `[agents]`, `[explain]`, `[imbalance]` with per-module version probing so "why is this extra missing?" is answerable without shelling out to pip.
- **`family_probes`** — `torch`, `lightning`, `sklearn`, `xgboost`, `lightgbm`, `catboost`, `onnxruntime`, `onnxruntime-gpu` each report installed version or `"not installed"`. `onnxruntime-gpu` uses `importlib.metadata.version` so it distinguishes CPU vs GPU wheel.
- **`onnx_eps`** — enumerates `onnxruntime.get_available_providers()` (CoreML / CUDA / CPU / Azure EPs) when onnxruntime is importable.
- **`sqlite_path`** — default `~/.kailash_ml/ml.db` (or `KAILASH_ML_STORE` override) with writability probe via a throwaway `.km-doctor-probe.sqlite` file; never touches a live ml.db.
- **`cache_paths`** — data_root + cache directories with recursive byte size AND filesystem total/free via `shutil.disk_usage`.
- **`tenant_mode`** — single-tenant vs multi-tenant, derived from `KAILASH_ML_DEFAULT_TENANT` (primary) with `KAILASH_TENANT_ID` fallback.
- **`gotchas`** — `specs/ml-backends.md` §1.1 entries surfaced per detected `status=ok` backend so operators see backend-specific caveats (MPS CPU fallback, XLA 30s compile pause, CUDA_VISIBLE_DEVICES hint, etc.).
- **`selected_default`** — the backend `detect_backend(None)` would return, derived from priority walk over ok-status probes.
- **14 additional Tier 2 tests** at `tests/integration/test_km_doctor.py` verifying every new JSON section has the spec-required shape.

### Added — `km.track` auto-capture completes §2.4 17-field envelope (closes #548 follow-up)

- **7 new persisted columns** added to `experiment_runs`: `kailash_ml_version`, `lightning_version`, `torch_version`, `cuda_version`, `device_used`, `accelerator`, `precision`. Every `km.track()` run now persists the full reproducibility envelope `specs/ml-tracking.md` §2.4 mandates.
- **`_capture_versions()` helper** — probes `kailash_ml.__version__` (always), `torch.__version__` + `torch.version.cuda` (when importable), `lightning.__version__` (when importable). Each probe is wrapped separately so a partial stack still yields as many fields as possible.
- **`ExperimentRun.attach_training_result`** extended to mirror `TrainingResult.device_used` / `.accelerator` / `.precision` (top-level reproducibility fields) in addition to the existing `device.*` `DeviceReport` envelope. Never stores `"auto"` — fields pass through as concrete strings.
- **Additive schema migration** — `initialize()` now probes `PRAGMA table_info(experiment_runs)` and runs `ALTER TABLE ADD COLUMN` for each 0.14 column missing from pre-0.14 databases. Existing `~/.kailash_ml/ml.db` files keep working; historical rows carry SQL `NULL` for the new fields.
- **2 new Tier 2 tests** at `tests/integration/test_km_track.py`:
  - `test_km_track_all_17_auto_capture_fields_present` — mechanical whitelist check that every §2.4 field is a persisted column.
  - Extended trainable-integration test to assert `row["device_used"] == result.device_used`, `row["accelerator"] == result.accelerator`, `row["precision"] == result.precision` with the explicit "never `auto`" guard.

### Fixed

- **Partial-implementation orphans** — both km.doctor (`10/14` checks) and km.track (`10/17` fields) shipped as partial MVPs in 0.13.0. 0.14.0 closes each to the full spec-mandated surface; no deferred sub-items remain.

## [0.13.0] - 2026-04-20 — ONNX bridge matrix completion + km.track + km.doctor

Three spec-compliance issues resolved in one minor release: #546 (ONNX matrix), #547 (km.doctor), #548 (km.track Phase 6).

### Added — ONNX bridge matrix completion (closes #546)

- **`OnnxBridge._export_torch`** — torch.nn.Module -> ONNX via `torch.onnx.export` with opset 17 and `dynamic_axes` on the batch dimension. Accepts `np.ndarray`, `polars.DataFrame`, or `torch.Tensor` for `sample_input`.
- **`OnnxBridge._export_lightning`** — `LightningModule` -> ONNX. Routes through `model.to_onnx()` when available, with direct `torch.onnx.export` fallback. Same opset / dynamic_axes contract as torch.
- **`OnnxBridge._export_catboost`** — native `model.save_model(path, format="onnx")` branch. Uses `NamedTemporaryFile` round-trip when no `output_path` is supplied.
- **`OnnxBridge.export(sample_input=...)` kwarg** — required for torch / lightning exports (torch.onnx.export traces the forward pass with a concrete tensor). Tabular branches continue to use `n_features`.
- **6 Tier 2 ONNX round-trip regression tests** at `tests/integration/test_onnx_roundtrip_{sklearn,xgboost,lightgbm,catboost,torch,lightning}.py` — each trains a minimal model, exports via `OnnxBridge.export`, re-imports via `onnxruntime.InferenceSession`, asserts prediction parity within `np.allclose(rtol=1e-3, atol=1e-5)`. XGBoost / LightGBM skip on darwin-arm + py3.13 per pre-existing segfault pattern. CatBoost skips gracefully when the `[catboost]` extra is not installed. Torch additionally covers dynamic-batch-size inference. Resolves `specs/ml-engines.md` §6.1 MUST 3.
- **`_COMPAT_MATRIX` entries for `"torch"`, `"lightning"`, `"catboost"`**.

### Added — `km.track()` Phase 6 (closes #548)

- **`km.track(experiment, ...) -> AsyncContextManager[ExperimentRun]`** — replaces the previous `NotImplementedError` stub. Async-context entry point per `specs/ml-tracking.md §2.1`; on enter creates a run and auto-sets status `RUNNING`, on exit auto-sets `COMPLETED` / `FAILED` / `KILLED`.
- **16 auto-capture fields** per `specs/ml-tracking.md §2.4` — `host`, `python_version`, `git_sha`, `git_branch`, `git_dirty`, `wall_clock_start`, `wall_clock_end`, `duration_seconds`, `status`, `tenant_id`, `run_id`, `parent_run_id`, `device_family`, `device_backend`, `device_fallback_reason`, `device_array_api`. Git metadata captured via subprocess with graceful fallback on no-git environments. `tenant_id` resolves from explicit kwarg or `KAILASH_TENANT_ID` env. `parent_run_id` propagates via `contextvars` for nested `km.track()` calls. `device_*` fields populate from the most recent `TrainingResult.device` when a Trainable runs inside the context.
- **Run-status auto-set** per `specs/ml-tracking.md §2.2` — `COMPLETED` on clean exit, `FAILED` on exception (captures `exc_type.__name__` + traceback), `KILLED` on SIGINT/SIGTERM via `signal.signal` handler installed at `__aenter__` and restored at `__aexit__`.
- **`SQLiteTrackerBackend`** — default async SQLite backend at `~/.kailash_ml/ml.db` with WAL journal mode. 20-column `experiment_runs` schema. All SQL uses `?` placeholders; identifiers are fixed literals.
- **9 Tier 2 integration tests** at `tests/integration/test_km_track.py`.

### Added — `km.doctor()` backend diagnostic (closes #547)

- **`km.doctor(require=None, as_json=False) -> int`** — diagnostic probe per `specs/ml-backends.md §7`. Exit codes: `0` all-green, `1` warnings, `2` failures. Probes `cpu`, `cuda`, `mps`, `rocm`.
- **`--require=<backend>`** — fails-fast with exit 2 when the named backend is absent. CI-lane gate for training-job prerequisites.
- **`--json`** — structured report per spec §7.2 (`backend`, `status`, `version`, `devices`, `warnings`, `failures`).
- **`km-doctor` console script** — registered in `[project.scripts]` as `km-doctor = "kailash_ml.doctor:main"`. Operators run `km-doctor --require=cuda` to gate training jobs.
- **7 Tier 2 integration tests** at `tests/integration/test_km_doctor.py`.

### Fixed

- **ONNX compatibility matrix orphan** — prior to this release, `_COMPAT_MATRIX` advertised `pytorch` as exportable but `OnnxBridge.export()` fell through to the generic "Export not implemented" skip path for torch / lightning / catboost. Every framework key in the matrix now has an implemented export branch AND a Tier 2 round-trip regression test exercising that branch through `onnxruntime` (orphan guard per `rules/orphan-detection.md` §2a).
- **`km.track` / `km.doctor` NotImplementedError / missing-symbol orphans** — both spec-documented entry points now ship with real implementations, public-symbol exports in `__all__`, and Tier 2 coverage.

## [0.12.1] - 2026-04-20 — Predictions.device field + kailash>=2.8.9 floor bump

### Added

- **`Predictions.device: Optional[DeviceReport]` field** — Completes the predict-side half of the GPU-first Phase 1 transparency contract that 0.12.0 deferred. Every Phase 1 family adapter (`SklearnTrainable`, `XGBoostTrainable`, `LightGBMTrainable`, `TorchTrainable`, `LightningTrainable`, `UMAPTrainable`, `HDBSCANTrainable`) now caches the fit-time `DeviceReport` on `self._last_device_report` and stamps the same instance onto every `Predictions` returned until the next `fit()` call. Callers can now programmatically distinguish a CUDA-resolved predict from a CPU-fallback predict via `pred.device.backend` / `pred.device.fallback_reason` without inspecting the prior `TrainingResult`. Direct constructors that don't carry `device=` keep the backward-compat `None` default. Resolves `workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md`.
- **`tests/regression/test_predictions_device_invariant.py`** — 3 mechanical AST guards that fail loudly if a future refactor drops the `device=` kwarg from a `Predictions(...)` constructor inside `predict()`, fails to cache `self._last_device_report` in `fit()`, or removes the `_device` slot / `device` property on `Predictions`.
- **`tests/integration/test_predictions_device_matrix.py`** — 9 Tier 2 backend-matrix tests (7 pass on this host; 2 skipped per the darwin-arm XGBoost/LightGBM segfault pattern from 0.12.0) that exercise `fit → predict` end-to-end and assert `pred.device is result.device` (identity, not equality) for every family.

### Changed

- **`kailash>=2.8.9` floor bump** — Picks up the `app.router.startup()` / `.shutdown()` fix that shipped in kailash 2.8.9 via issue #538. Staggered adoption per issue #541 — each sibling package bumps its floor on its next natural minor release rather than a coordinated bundle. kailash-ml's floor bump lands here bundled with the `Predictions.device` work.

### Fixed

- **Removes the 0.12.0 Known Limitation for `Predictions.device`.** 0.12.0's changelog disclosed that the predict-side transparency contract was incomplete; 0.12.1 closes that gap.

## [0.12.0] - 2026-04-19 — GPU-first Phase 1 punch list: Trainable adapters + transparency

### Added

- **`SklearnTrainable` Array-API auto-dispatch** — When the caller passes a non-CPU `TrainingContext.backend` AND the wrapped estimator is on the Phase 1 allowlist (`Ridge`, `LogisticRegression`, `LinearRegression`, `LinearDiscriminantAnalysis`, `KMeans`, `PCA`, `StandardScaler`, `MinMaxScaler`), the inner Lightning fit runs inside `sklearn.config_context(array_api_dispatch=True)` with X/y moved to a torch tensor on the resolved device. Emits INFO `sklearn.array_api.engaged` log. Off-allowlist estimators on a non-CPU backend log WARN `sklearn.array_api.offlist` and proceed on CPU numpy. (Item 3 of revised-stack.md)
- **`SklearnTrainable` runtime fallback for scipy env-var gate** — `sklearn.config_context(array_api_dispatch=True)` requires `SCIPY_ARRAY_API=1` to be set BEFORE any sklearn/scipy import. When that precondition isn't met, the call raises at enter-time. The adapter now catches that and falls back to the CPU numpy path with WARN `sklearn.array_api.runtime_unavailable` so the deployment gap surfaces in log aggregators rather than as a hard failure.
- **`XGBoostTrainable` GPU OOM single-retry fallback** — A GPU OOM during `trainer.fit` is intercepted; the adapter logs WARN `xgboost.gpu.oom_fallback`, rebuilds on CPU, and returns a `TrainingResult` whose `device.fallback_reason="oom"` and `device.backend="cpu"`. Non-OOM exceptions re-raise unchanged. (Item 4)
- **`LightGBMTrainable` GPU OOM single-retry fallback** — Same pattern as XGBoost; logs WARN `lightgbm.gpu.oom_fallback` on the fallback path.
- **`UMAPTrainable` (CPU-only Phase 1)** — New `kailash_ml.UMAPTrainable` wraps `umap-learn` as a Trainable. Phase 1 is CPU-only per the cuML eviction decision (revised-stack.md CRITICAL-1). When called with a non-CPU `TrainingContext.backend`, logs INFO `umap.cuml_eviction` (not WARN — this is the documented Phase 1 design) and runs on CPU. The returned `DeviceReport.fallback_reason="cuml_eviction"` so callers can distinguish this from an OOM or driver-missing fallback. Phase 2 adds torch-native UMAP across MPS/ROCm/XPU. (Item 5)
- **`HDBSCANTrainable` (CPU-only Phase 1)** — New `kailash_ml.HDBSCANTrainable` wraps `sklearn.cluster.HDBSCAN` (sklearn 1.3+) as a Trainable. Same cuml_eviction logging contract as `UMAPTrainable`.
- **`TrainingResult.device: Optional[DeviceReport]` field** — Append-only optional field that every Phase 1 Trainable family adapter populates. Carries family / backend / device_string / precision / fallback_reason / array_api so callers can distinguish a CUDA execution from a silent CPU fallback. Required for the orphan-detection §6 contract — `DeviceReport` is now wired into the production hot path of every Phase 1 family.
- **Tier 2 backend-matrix tests** — `tests/integration/test_trainable_backend_matrix.py` exercises every Phase 1 Trainable across CPU + (where available) MPS / CUDA with real estimators, real Lightning Trainer, no mocking. (Item 7)

### Removed

- **`kailash-ml[rapids]` extra** — Verified absent. Phase 1 cuML eviction is complete; users who need cuML on NVIDIA install it themselves and swap it in via the Trainable layer. (Item 8)

### Fixed

- **`UMAPTrainable.__init__` warning hygiene** — Pre-set `n_jobs=1` so umap-learn's "n_jobs overridden by random_state" UserWarning doesn't fire.
- **`HDBSCANTrainable.__init__` warning hygiene** — Pre-set `copy=True` so sklearn 1.5+ FutureWarning about the `copy` default change to 1.10 doesn't fire.
- **`engines/dim_reduction.py::_reduce_umap` warning hygiene** — Same `n_jobs=1` preset (resolves a pre-existing warning that was outside the Phase 1 scope but caught under zero-tolerance Rule 1 ownership).

### Known Limitations

- **`Predictions.device` field not yet populated.** The spec's "Transparency contract" mandates that every `predict()` return carry a `DeviceReport`, but the `Predictions` class in 0.12.0 exposes only `raw` / `column` / `to_polars()`. Callers can inspect the FIT-time `TrainingResult.device` (wired across all 7 family adapters in this release) to identify the device that executed the model. Scheduled for 0.12.1 — requires an API addition to `Predictions` plus per-family `predict()` updates. See journal entry `0005-GAP-predictions-device-field-missing.md` for the 0.12.1 plan.

### Test counts

- 957 passed / 5 skipped / 0 warnings in the unit + regression + Tier 2 suites (943 unit + 6 Tier 2 + 2 new regression invariants + 6 new sklearn array-API).
- 4 Tier 2 skips on darwin-arm (XGBoost / LightGBM segfault on darwin-arm + py3.13 — Tier 2 ships on Linux CI; SCIPY_ARRAY_API=1 precondition skip when env-var unset).

## [0.11.0] - 2026-04-19 — GPU-first Phase 1: DeviceReport + km.device()/use_device() (#523)

### Added

- **`DeviceReport` dataclass (#523)**: `kailash_ml.DeviceReport` captures the full hardware inventory at import or call time — CUDA device list (name, memory, compute capability), MPS availability (Apple Silicon), CPU count, and a `best_device` recommendation (`"cuda:0"`, `"mps"`, or `"cpu"`). Constructed via `km.device()` or `DeviceReport.probe()`.
- **`km.device()` factory function (#523)**: `import kailash_ml as km; report = km.device()` probes and returns a `DeviceReport`. Zero-argument convenience wrapper over `DeviceReport.probe()`.
- **`km.use_device(device=None)` context manager (#523)**: Activates a PyTorch device context for the duration of the `with` block. Accepts a string device specifier (e.g. `"cuda:0"`, `"mps"`, `"cpu"`), a `torch.device`, or `None` (auto-selects `DeviceReport.probe().best_device`). Raises `DeviceNotAvailableError` if the requested device is not present.
- **`DeviceNotAvailableError` typed exception (#523)**: Raised by `km.use_device()` when the requested device is not present on the host. Carries `requested_device` and `available_devices` attributes for programmatic handling.

## [0.10.0] - 2026-04-19 — Pipeline, FeatureUnion, ColumnTransformer + register_estimator (#479 #488)

### Added

- **`Pipeline` + `FeatureUnion` + `ColumnTransformer` estimators (#479 #488, PR #506)**: Three sklearn-compatible compositing estimators now ship in `kailash_ml.estimators`. `Pipeline` chains ordered `(name, estimator)` steps where each step's `transform` output feeds the next step's input; the final step may be a classifier or regressor and exposes `fit`, `predict`, `predict_proba`. `FeatureUnion` runs multiple transformers in parallel and concatenates their outputs column-wise. `ColumnTransformer` applies per-column transformer lists and handles remainder columns via `passthrough` or `drop`. All three are registered with the `kailash_ml` estimator registry and exported from `kailash_ml.__init__`.
- **`register_estimator` / `unregister_estimator` public API (#488)**: `kailash_ml.register_estimator(name, cls)` and `unregister_estimator(name)` expose the estimator registry for user-defined or third-party sklearn-compatible estimators. Registered estimators are reachable by name inside `Pipeline` / `FeatureUnion` / `ColumnTransformer` step lists and via `AutoMLEngine` hyperparameter search. `register_estimator` raises `ValueError` on name collision unless `force=True` is passed.

## [0.7.0] - 2026-04-07

### Added

- **ModelExplainer engine** — SHAP-based model explainability with global, local, and dependence explanations; plotly visualizations; optional `[explain]` extra (`shap>=0.44`)
- **Model calibration** — `TrainingPipeline.calibrate()` wraps classifiers in `CalibratedClassifierCV` (Platt scaling, isotonic regression)
- **Auto-logging** — `TrainingPipeline.train(tracker=...)`, `HyperparameterSearch.search(tracker=...)`, and `AutoMLEngine.run(tracker=...)` automatically log params, metrics, and artifacts to ExperimentTracker
- **Nested experiment runs** — `ExperimentTracker.start_run(parent_run_id=...)` for hierarchical run organization; HPO trials log as children of the search run
- **Inference signature validation** — `InferenceServer.predict()` validates required features against model signature instead of silently defaulting missing features to 0.0
- **Preprocessing: 4 normalization methods** — `normalize_method` parameter: zscore, minmax, robust, maxabs
- **Preprocessing: KNN and iterative imputation** — `imputation_strategy="knn"` and `"iterative"` via sklearn imputers
- **Preprocessing: multicollinearity removal** — `remove_multicollinearity=True` drops highly correlated features using Pearson correlation
- **Preprocessing: class imbalance handling** — `fix_imbalance=True` with SMOTE, ADASYN (optional `[imbalance]` extra), or `class_weight` method
- **New optional extras** — `[imbalance]` (imbalanced-learn>=0.12), `[explain]` (shap>=0.44)

### Fixed

- **Stratified k-fold** — `split_strategy="stratified_kfold"` now uses `sklearn.model_selection.StratifiedKFold` instead of silently falling back to regular k-fold
- **Successive halving** — `strategy="successive_halving"` now uses Optuna's `SuccessiveHalvingPruner` with progressive resource allocation instead of silently falling back to random search
- **K-fold shuffling** — `_kfold_first_fold` now shuffles data via `sklearn.model_selection.KFold` instead of naively slicing
- Silent `except: pass` on `predict_proba` replaced with `logger.debug`
- Schema migration `except Exception: pass` narrowed to check for "duplicate column"
- `BaseException` catch in run context manager changed to `Exception`
- Path traversal guard added to `delete_run` artifact cleanup
- String target + multicollinearity no longer crashes (falls back to index-based dropping)
- AutoML deep search now passes `parent_run_id` to nested HPO search

### Changed

- **Breaking**: `scikit-learn>=1.5` (was >=1.4) — required for `FrozenEstimator` in calibration
- `asyncio.get_event_loop()` replaced with `asyncio.get_running_loop()` (Python 3.12+ deprecation fix)

### Security

- R1 red team converged: 0 CRITICAL, 0 HIGH findings after fixes
- Inference server no longer silently produces wrong predictions for missing features
- Experiment tracker artifact deletion has path containment validation
- 750 tests passing (677 unit + 60 integration + 13 examples), 0 regressions

## [0.6.0] - 2026-04-07

### Added

- **PreprocessingPipeline cardinality guard** — `max_cardinality=50` threshold with `exclude_columns` parameter; mixed one-hot + ordinal encoding for high-cardinality categoricals
- **ModelVisualizer EDA charts** — `histogram()`, `scatter()`, `box_plot()` methods accepting polars DataFrame
- **ExperimentTracker factory** — `ExperimentTracker.create()` convenience constructor
- **`training_history()` y_label parameter** — customizable y-axis label for training history plots

### Fixed

- Corrected HyperparameterSearch README example to match actual API
- Removed stale `tracker.initialize()` from README Engine Initialization section

## [0.2.0] - 2026-04-02

### Added

- **13 ML engines**: FeatureStore, ModelRegistry, TrainingPipeline, InferenceServer, DriftMonitor, HyperparameterSearch, AutoMLEngine, DataExplorer, FeatureEngineer, EnsembleEngine, ExperimentTracker, PreprocessingPipeline, ModelVisualizer
- **6 Kaizen agents**: DataScientistAgent, FeatureEngineerAgent, ModelSelectorAgent, ExperimentInterpreterAgent, DriftAnalystAgent, RetrainingDecisionAgent with LLM-first reasoning
- **RL module**: RLTrainer (SB3 wrapper), EnvironmentRegistry, PolicyRegistry
- **Agent guardrails**: AgentGuardrailMixin with LLM cost tracking, approval gates, audit trails
- **Interop module**: polars-native with sklearn, LightGBM, Arrow, pandas, HuggingFace converters
- **Shared utilities**: `_shared.py` (NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, compute_metrics_by_name)
- **SQL encapsulation**: `_feature_sql.py` — all raw SQL in one auditable module

### Fixed

- SQL type injection prevention via `_validate_sql_type()` allowlist
- FeatureStore `_table_prefix` validated in constructor
- `ModelRegistry.register_model()` no longer accesses private `_root` on ArtifactStore
- `AutoMLConfig.max_llm_cost_usd` validated with `math.isfinite()`
- `_compute_metrics` duplication eliminated via shared module
- Dead `_types.py` removed (duplicate ModelSpec/EvalSpec/TrainingResult)
- 29+ dataclasses now have `to_dict()`/`from_dict()` per EATP convention

### Security

- R1+R2+R3 red team converged: 0 CRITICAL, 0 HIGH findings
- NaN/Inf validation on all financial fields
- Bounded collections (deque maxlen) on all long-running stores
- Model class allowlist for dynamic imports
- 508 tests passing, 0 regressions

## [0.1.0] - 2026-03-30

### Added

- Initial release with package skeleton and interop module
