# kailash-ml Changelog

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
