# kailash-ml Changelog

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

### Test counts

- 943 passed / 1 skipped / 0 warnings in the unit suite.
- 6 passed / 4 skipped in the new Tier 2 backend matrix on darwin-arm (XGBoost / LightGBM segfault on darwin-arm + py3.13 — Tier 2 ships on Linux CI; SCIPY_ARRAY_API=1 precondition skip when env-var unset).

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
