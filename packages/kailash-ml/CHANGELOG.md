# kailash-ml Changelog

## [0.13.0] - 2026-04-20 — ONNX bridge matrix completion (torch / lightning / catboost)

### Added

- **`OnnxBridge._export_torch`** — torch.nn.Module -> ONNX via `torch.onnx.export` with opset 17 and `dynamic_axes` on the batch dimension. The exported graph accepts any batch size at `onnxruntime.InferenceSession.run` time. Accepts `np.ndarray`, `polars.DataFrame`, or `torch.Tensor` for `sample_input`; non-tensor inputs are converted to float32 tensors.
- **`OnnxBridge._export_lightning`** — `LightningModule` -> ONNX. Routes through `model.to_onnx()` (Lightning's wrapper around `torch.onnx.export`) when available, with a direct `torch.onnx.export` fallback. Same opset / dynamic_axes contract as the torch branch.
- **`OnnxBridge._export_catboost`** — native `model.save_model(path, format="onnx")` branch. Uses `NamedTemporaryFile` round-trip when no `output_path` is supplied (CatBoost has no in-memory buffer API).
- **`OnnxBridge.export(sample_input=...)` kwarg** — required for torch / lightning exports because `torch.onnx.export` traces the forward pass with a concrete tensor. Tabular branches (sklearn / lightgbm / xgboost / catboost) continue to use `n_features` and ignore this kwarg.
- **6 Tier 2 ONNX round-trip regression tests** — `tests/integration/test_onnx_roundtrip_{sklearn,xgboost,lightgbm,catboost,torch,lightning}.py`. Each trains a minimal model on a tiny synthetic dataset, exports to ONNX via `OnnxBridge.export`, re-imports via `onnxruntime.InferenceSession`, and asserts prediction parity within `np.allclose(rtol=1e-3, atol=1e-5)` against the native model. XGBoost / LightGBM tests are skipped on darwin-arm + py3.13 per the pre-existing segfault pattern. CatBoost is skipped gracefully when the optional `[catboost]` extra is not installed. The torch test additionally covers dynamic-batch-size inference (trace with batch=1, infer with batch=32). Resolves issue #546 and `specs/ml-engines.md` §6.1 MUST 3.
- **`_COMPAT_MATRIX` entries for `"torch"`, `"lightning"`, `"catboost"`** — the pre-flight `check_compatibility` call now returns structured compatibility metadata for every framework key that has an implemented export branch.

### Fixed

- **ONNX compatibility matrix orphan (closes spec-compliance gap)** — prior to this release, `_COMPAT_MATRIX` advertised `pytorch` as exportable but `OnnxBridge.export()` fell through to the generic "Export not implemented for framework" skip path for torch / lightning / catboost. The matrix made a promise the dispatch could not keep. Every framework key in the matrix now has an implemented export branch AND a Tier 2 round-trip regression test exercising that branch through `onnxruntime` (the orphan guard per `rules/orphan-detection.md` §2a — crypto-pair round-trip MUST be tested through the facade, generalized to `export` / `import` pairs).

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
