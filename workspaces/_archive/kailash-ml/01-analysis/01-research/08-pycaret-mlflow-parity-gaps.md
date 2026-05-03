# PyCaret & MLflow Parity Gap Analysis

## Context

kailash-ml reimplements PyCaret and MLflow functionality natively (polars-first, DataFlow-backed, Kaizen-augmented). This analysis identifies features where parity is incomplete.

## Classification

- **MISSING**: Feature does not exist at all
- **STUB**: API accepts the option but silently falls back (zero-tolerance Rule 2 violation)
- **PARTIAL**: Feature exists but covers only a subset of what PyCaret/MLflow provides

---

## PyCaret Parity Gaps

### 1. Class Imbalance Handling (SMOTE) — MISSING

**PyCaret**: `fix_imbalance=True` in `setup()` applies SMOTE via `imbalanced-learn`.

**kailash-ml**: `DataExplorer` detects imbalance (`imbalance_ratio_threshold` in `data_explorer.py:241`), `DataScientistAgent` mentions it in risk assessment. Detection only — no correction.

**Required**: Add `fix_imbalance: bool` and `imbalance_method: str` to `PreprocessingPipeline.setup()`. Methods: `"smote"`, `"adasyn"`, `"class_weight"` (no new dep).

**New dependency**: `imbalanced-learn>=0.12` as optional extra `[imbalance]`.

### 2. SHAP Explainability — MISSING

**PyCaret**: `interpret_model()` provides SHAP summary, dependence, and reason plots.

**kailash-ml**: `ModelVisualizer.feature_importance()` uses sklearn builtins (global importance only). `interop.py:300` mentions SHAP as anticipated use case.

**Required**: Add `ModelExplainer` engine with SHAP summary plots, dependence plots, and per-prediction explanations.

**New dependency**: `shap>=0.44` as optional extra `[explain]`.

### 3. Model Calibration — MISSING

**PyCaret**: `calibrate_model()` wraps model in `CalibratedClassifierCV`.

**kailash-ml**: `ModelVisualizer.calibration_curve()` (line 479-534) plots calibration — visualization only. No way to actually calibrate a model.

**Required**: Add `calibrate()` method to `TrainingPipeline` or `EnsembleEngine`. Wrap model in `CalibratedClassifierCV` with Platt scaling or isotonic regression.

**No new dependency** — `sklearn.calibration.CalibratedClassifierCV` exists.

### 4. Additional Normalization Methods — PARTIAL

**PyCaret**: `normalize_method` supports `"zscore"`, `"minmax"`, `"maxabs"`, `"robust"`.

**kailash-ml**: `preprocessing.py:721-739` — only `StandardScaler`. `setup()` has `normalize: bool` (line 144) — no method selection.

**Required**: Add `normalize_method: str` parameter. Support all four sklearn scalers.

**No new dependency**.

### 5. Advanced Imputation — PARTIAL

**PyCaret**: Supports KNN imputation, iterative imputation in addition to simple strategies.

**kailash-ml**: `preprocessing.py:389-444` — only `"mean"`, `"median"`, `"mode"`, `"drop"` (validated at line 208).

**Required**: Add `"knn"` and `"iterative"` strategies using `sklearn.impute.KNNImputer` and `sklearn.impute.IterativeImputer`.

**No new dependency**.

### 6. Multicollinearity Removal — MISSING

**PyCaret**: `remove_multicollinearity=True` with configurable threshold.

**kailash-ml**: `FeatureEngineer.select()` ranks features by target relevance. `DataExplorer` computes correlation matrices. No automated feature-feature collinearity removal.

**Required**: Add `remove_multicollinear()` to `FeatureEngineer` or `PreprocessingPipeline`. Two approaches: correlation-based (no dep) or VIF-based (needs `statsmodels`, already optional extra `[stats]`).

### 7. Stratified K-Fold — STUB (zero-tolerance)

**PyCaret**: Uses `StratifiedKFold` for classification tasks by default.

**kailash-ml**: `training_pipeline.py:540-544`:

```python
def _stratified_kfold_first_fold(self, data, n_splits):
    # Fallback to regular kfold for simplicity in v1
    return self._kfold_first_fold(data, n_splits)
```

API accepts `"stratified_kfold"` but silently does regular kfold. This is a stub.

**Required**: Use `sklearn.model_selection.StratifiedKFold` properly. No new dependency.

### 8. Successive Halving — STUB (zero-tolerance)

**PyCaret**: Supports successive halving via sklearn/optuna.

**kailash-ml**: `hyperparameter_search.py:550-571`:

```python
async def _successive_halving_search(self, ...):
    # delegate to random search with early stopping heuristic
    return await self._random_search(...)
```

API accepts `"successive_halving"` but silently does random search. This is a stub.

**Required**: Use `optuna.pruners.SuccessiveHalvingPruner` with existing Bayesian infrastructure. No new dependency (optuna already optional).

---

## MLflow Parity Gaps

### 9. Nested Runs — MISSING

**MLflow**: `mlflow.start_run(nested=True)` for parent/child run hierarchies.

**kailash-ml**: `experiment_tracker.py:211-221` — `kailash_runs` table has no `parent_run_id`. `RunContext` has no nesting. `Run` dataclass has no parent field.

**Required**: Add `parent_run_id` column, update `Run` dataclass, add `nested` parameter to `start_run()`, add `list_child_runs()`.

**No new dependency**.

### 10. Auto-Logging — MISSING

**MLflow**: `mlflow.autolog()` patches sklearn `.fit()` to auto-log params, metrics, artifacts.

**kailash-ml**: Zero `autolog` references. `TrainingPipeline` has no `ExperimentTracker` integration. `AutoMLEngine` doesn't log to tracker either.

**Required**: Wire `TrainingPipeline` and `AutoMLEngine` to optionally accept `ExperimentTracker`. Add auto-logging of params, metrics, and model artifacts after each `train()`. HPO trials should log as nested child runs.

**No new dependency**.

---

## Cross-SDK (kailash-rs) Assessment

kailash-rs has foundational ML (40+ native estimators, ModelRegistry, ExperimentTracker, AutoML) but no PyCaret/MLflow parity features. Key alignment gaps:

1. **ExperimentTracker API divergence** — Rust is in-memory with SVG charts; Python is DataFlow-backed with MLflow format. Need compatible Run/Metric interfaces.
2. **Nested runs** — Neither SDK has it; should be added to both.
3. **Feature Store** — Python has it; Rust does not (P3-7 roadmap).
4. **Drift Monitor** — Python has it; Rust explicitly deferred.

The PyCaret parity features (SMOTE, SHAP, calibration, normalization, imputation) are Python-only since they wrap Python ML libraries. Cross-SDK alignment issues focus on the MLflow parity items (nested runs, auto-logging, tracker API).

---

## Priority Ranking

| #   | Feature                   | Type     | Impact             | Effort |
| --- | ------------------------- | -------- | ------------------ | ------ |
| 7   | Stratified K-Fold         | STUB fix | High (correctness) | Low    |
| 8   | Successive Halving        | STUB fix | High (correctness) | Medium |
| 1   | Class Imbalance (SMOTE)   | MISSING  | High (parity)      | Medium |
| 2   | SHAP Explainability       | MISSING  | High (parity)      | Medium |
| 3   | Model Calibration         | MISSING  | Medium             | Low    |
| 4   | Normalization Methods     | PARTIAL  | Medium             | Low    |
| 5   | Advanced Imputation       | PARTIAL  | Medium             | Low    |
| 6   | Multicollinearity Removal | MISSING  | Medium             | Medium |
| 10  | Auto-Logging              | MISSING  | High (usability)   | Medium |
| 9   | Nested Runs               | MISSING  | Medium             | Medium |

Stubs (#7, #8) are highest priority — they violate zero-tolerance Rule 2 (accepting an API option and silently doing something else).
