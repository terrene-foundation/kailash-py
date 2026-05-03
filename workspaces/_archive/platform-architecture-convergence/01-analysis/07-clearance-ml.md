# ML Clearance Run Analysis (Issues #342-#348)

## Summary

Seven ML feature requests span three complexity tiers: two quick wins (#342, #347) that extend existing infrastructure with ~10 lines each; two medium features (#343, #346) that add methods to existing engines; and three new engines (#344, #345, #348) that require full engine files following the EnsembleEngine pattern. No inter-issue dependencies exist -- all seven can be implemented in parallel. Total estimate: 1 session for all seven, parallelized across two agents (quick-wins + medium on one, new engines on another).

Cross-SDK note: kailash-rs already has `kailash-ml-cluster`, `kailash-ml-decomposition`, and `kailash-ml-text` crates. Issues #344, #345, #346 achieve Python SDK parity.

---

## #342 -- Add log_loss, brier_score, average_precision to compute_metrics_by_name

**Priority:** P0 | **Complexity:** Trivial (~10 LOC) | **Estimate:** <0.1 session

**What:** Add 3 entries to `_shared.py:compute_metrics_by_name()`. These metrics require probability predictions (`predict_proba`), not class labels -- same pattern as the existing `auc` branch.

**Implementation:**

- File: `packages/kailash-ml/src/kailash_ml/engines/_shared.py`
- Add `log_loss`, `brier_score`, `average_precision` branches after the `auc` branch
- All three need `model.predict_proba(X_test)` -- guard with same `model is not None and X_test is not None` check
- `brier_score_loss` is binary-only; guard with `y_prob.shape[1] == 2`
- `average_precision_score` uses `y_prob[:, 1]` for binary

**Pattern to follow:** Existing `auc` branch at line 142-157.

**Tests needed:**

- Unit: `test_compute_metrics_log_loss`, `test_compute_metrics_brier_score`, `test_compute_metrics_average_precision` in a new or existing test file
- Verify graceful handling when model lacks `predict_proba`

**Dependencies:** None. Unblocks #343 and #347 (they can use the new metrics).

---

## #343 -- TrainingPipeline.cross_validate() returning per-fold score arrays

**Priority:** P0 | **Complexity:** Medium (~80 LOC) | **Estimate:** 0.2 session

**What:** Add `cross_validate()` method to `TrainingPipeline` that returns per-fold scores, mean, and std -- the kailash-ml equivalent of `sklearn.model_selection.cross_val_score`.

**Implementation:**

- File: `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py`
- New `CrossValidateResult` dataclass with `fold_scores: dict[str, list[float]]`, `mean_scores: dict[str, float]`, `std_scores: dict[str, float]`
- New `cross_validate()` method using `sklearn.model_selection.KFold` / `StratifiedKFold`
- For each fold: split data, train model via `model_spec.instantiate()`, evaluate with `_compute_metrics`, collect per-fold results
- Return aggregated result

**Pattern to follow:** Existing `_kfold_first_fold()` (line 675-683) for fold mechanics, `_train_sklearn()` for model fitting, `_evaluate()` for metrics.

**Key decisions:**

- Method should be synchronous (no registry/tracker interaction needed)
- Accept `data: pl.DataFrame` directly (no FeatureStore dependency)
- Use `to_sklearn_input` at the boundary per fold

**Tests needed:**

- Unit: `test_cross_validate_returns_per_fold_scores`, `test_cross_validate_stratified`, `test_cross_validate_multiple_metrics`
- Verify fold count matches `cv` parameter
- Verify mean/std are correct aggregations of fold_scores

**Dependencies:** Benefits from #342 (can test with `log_loss`, `average_precision`), but not blocked.

---

## #344 -- Clustering Engine (KMeans, DBSCAN, GMM, Spectral)

**Priority:** P1 | **Complexity:** New engine (~300 LOC) | **Estimate:** 0.3 session

**What:** New `cluster_engine.py` providing a unified clustering API with built-in evaluation metrics (silhouette, Calinski-Harabasz, Davies-Bouldin) and elbow/k-range analysis.

**Implementation:**

- New file: `packages/kailash-ml/src/kailash_ml/engines/cluster_engine.py`
- `ClusterSpec` dataclass: `algorithm`, `n_clusters`, `params`
- `ClusterResult` dataclass: `labels` (pl.Series), `centers` (optional), `metrics`, `inertia`
- `ClusterEngine` class with:
  - `fit(data, feature_columns, cluster_spec)` -- fit and return labels + metrics
  - `evaluate_k_range(data, feature_columns, algorithm, k_range, metrics)` -- sweep k values
  - `predict(data, feature_columns)` -- assign new points (KMeans/GMM only)

**Algorithms:** Map algorithm strings to sklearn classes:

- `"kmeans"` -> `sklearn.cluster.KMeans`
- `"dbscan"` -> `sklearn.cluster.DBSCAN`
- `"gmm"` -> `sklearn.mixture.GaussianMixture`
- `"spectral"` -> `sklearn.cluster.SpectralClustering`
- `"agglomerative"` -> `sklearn.cluster.AgglomerativeClustering`
- `"hdbscan"` -> optional extra `[cluster]` with loud failure

**Pattern to follow:** `EnsembleEngine` -- stateless class, polars input, numpy at sklearn boundary via `to_sklearn_input`, frozen result dataclasses with `to_dict()`/`from_dict()`.

**Tests needed:**

- Unit: `test_kmeans_fit`, `test_dbscan_fit`, `test_gmm_fit`, `test_evaluate_k_range`, `test_cluster_metrics_computed`
- Verify labels are pl.Series with correct length
- Verify silhouette score is in [-1, 1]

**Dependencies:** None. Independent of all other issues.

---

## #345 -- Dimensionality Reduction Engine (PCA, NMF, t-SNE, UMAP)

**Priority:** P1 | **Complexity:** New engine (~250 LOC) | **Estimate:** 0.3 session

**What:** New `reduction_engine.py` providing a unified dimensionality reduction API with variance analysis and reconstruction error.

**Implementation:**

- New file: `packages/kailash-ml/src/kailash_ml/engines/reduction_engine.py`
- `ReductionSpec` dataclass: `algorithm`, `n_components`, `params`
- `ReductionResult` dataclass: `transformed` (pl.DataFrame), `explained_variance_ratio` (optional), `components` (optional), `reconstruction_error` (optional)
- `ReductionEngine` class with:
  - `fit_transform(data, feature_columns, spec)` -- fit and transform
  - `transform(data, feature_columns)` -- transform new data (PCA/NMF only)
  - `inverse_transform(transformed)` -- reconstruct (PCA/NMF only)

**Algorithms:**

- `"pca"` -> `sklearn.decomposition.PCA`
- `"nmf"` -> `sklearn.decomposition.NMF`
- `"truncated_svd"` -> `sklearn.decomposition.TruncatedSVD`
- `"tsne"` -> `sklearn.manifold.TSNE`
- `"umap"` -> optional extra `[umap]` with loud failure
- `"lda"` -> `sklearn.decomposition.LatentDirichletAllocation`

**Pattern to follow:** Same as ClusterEngine -- `EnsembleEngine` pattern with polars-native I/O.

**Key decisions:**

- `transformed` output should be a polars DataFrame with columns `component_0`, `component_1`, etc.
- t-SNE/UMAP only support `fit_transform`, not `transform` on new data -- raise clear error
- Preprocessing note in `preprocessing.py` already has PCA at line 378 -- this engine is the standalone version

**Tests needed:**

- Unit: `test_pca_fit_transform`, `test_pca_explained_variance`, `test_nmf_non_negative`, `test_tsne_no_transform_error`
- Verify output DataFrame shape is (n_rows, n_components)

**Dependencies:** None.

---

## #346 -- Text Feature Extraction (TfidfVectorizer, CountVectorizer)

**Priority:** P1 | **Complexity:** New engine (~200 LOC) | **Estimate:** 0.2 session

**What:** New `text_engine.py` (not FeatureStore -- keeps FeatureStore focused on tabular data) providing text vectorization that returns polars DataFrames.

**Implementation:**

- New file: `packages/kailash-ml/src/kailash_ml/engines/text_engine.py`
- `TextVectorizerSpec` dataclass: `method` ("tfidf" | "count" | "hashing"), `max_features`, `ngram_range`, `min_df`, `max_df`
- `TextVectorizerResult` dataclass: `matrix` (pl.DataFrame -- sparse-to-dense for polars), `vocabulary`, `feature_names`, `idf_weights` (tfidf only)
- `TextEngine` class with:
  - `fit_transform(data, text_column, spec)` -- fit vectorizer and transform
  - `transform(data, text_column)` -- transform new text with fitted vectorizer
  - `get_top_terms(n)` -- top N terms by IDF or frequency

**Key decisions:**

- Output as dense polars DataFrame (not scipy sparse) -- aligns with polars-native principle
- For large vocabularies, `max_features` caps the output width
- Store fitted vectorizer in `self._vectorizer` for `transform()` calls

**Pattern to follow:** `EnsembleEngine` for structure. sklearn vectorizers are used at the boundary.

**Tests needed:**

- Unit: `test_tfidf_fit_transform`, `test_count_vectorizer`, `test_transform_new_text`, `test_vocabulary_returned`
- Verify output DataFrame has `max_features` columns

**Dependencies:** Used by #345's LDA (topic modeling needs count vectors), but not blocked.

---

## #347 -- classification_report Equivalent

**Priority:** P2 | **Complexity:** Trivial (~60 LOC) | **Estimate:** <0.1 session

**What:** A `classification_report()` function that produces a formatted text table and dict output -- pure Python, no sklearn dependency for the formatting.

**Implementation:**

- File: `packages/kailash-ml/src/kailash_ml/engines/_shared.py` (add alongside `compute_metrics_by_name`)
- Function `classification_report(y_true, y_pred, *, target_names=None, output_format="text")`:
  - Compute per-class precision, recall, f1, support using sklearn metrics
  - Format as aligned text table (matching sklearn's format)
  - When `output_format="dict"`, return nested dict
- Export from `kailash_ml.__init__` as `from kailash_ml import classification_report`

**Pattern to follow:** `compute_metrics_by_name` for the metric computation; formatting is custom.

**Tests needed:**

- Unit: `test_classification_report_text_format`, `test_classification_report_dict_format`, `test_classification_report_with_target_names`
- Verify output text matches expected alignment
- Verify dict has per-class and aggregate keys

**Dependencies:** None.

---

## #348 -- Anomaly Detection Engine (IsolationForest, LOF, OneClassSVM)

**Priority:** P2 | **Complexity:** New engine (~250 LOC) | **Estimate:** 0.3 session

**What:** New `anomaly_engine.py` providing unified anomaly detection with scoring, ensemble detection, and threshold tuning.

**Implementation:**

- New file: `packages/kailash-ml/src/kailash_ml/engines/anomaly_engine.py`
- `AnomalySpec` dataclass: `algorithm`, `contamination`, `params`
- `AnomalyResult` dataclass: `scores` (pl.Series), `labels` (pl.Series), `threshold` (float), `contamination_actual` (float)
- `AnomalyEngine` class with:
  - `detect(data, feature_columns, spec)` -- fit detector and score
  - `ensemble_detect(data, feature_columns, detectors, combination)` -- run multiple detectors, combine scores
  - `score(data, feature_columns)` -- score new data with fitted detector

**Algorithms:**

- `"isolation_forest"` -> `sklearn.ensemble.IsolationForest`
- `"local_outlier_factor"` -> `sklearn.neighbors.LocalOutlierFactor`
- `"one_class_svm"` -> `sklearn.svm.OneClassSVM`
- `"elliptic_envelope"` -> `sklearn.covariance.EllipticEnvelope`

**Ensemble combination methods:** `"average"` (mean scores), `"voting"` (majority vote on labels), `"max"` (max anomaly score).

**Pattern to follow:** `ClusterEngine` pattern -- similar shape (unsupervised, returns labels + scores).

**Key decisions:**

- LOF's `novelty=True` for `score()` on new data (default `novelty=False` only fits)
- Normalize scores to [0, 1] range for ensemble combination
- Labels follow sklearn convention: -1 = anomaly, 1 = normal

**Tests needed:**

- Unit: `test_isolation_forest_detect`, `test_lof_detect`, `test_ensemble_detect_average`, `test_ensemble_detect_voting`
- Verify anomaly count roughly matches contamination parameter
- Verify scores are pl.Series with correct length

**Dependencies:** None.

---

## Execution Plan

| Phase        | Issues           | Estimate    | Notes                                     |
| ------------ | ---------------- | ----------- | ----------------------------------------- |
| 1 (parallel) | #342, #347       | 0.1 session | Quick wins in `_shared.py`                |
| 2 (parallel) | #343, #346       | 0.3 session | Medium: new methods on existing/new files |
| 3 (parallel) | #344, #345, #348 | 0.4 session | New engines, all independent              |

**Total:** ~0.5 session (parallelized). All 7 issues are independent and can run simultaneously.

## Files to Create/Modify

| File                                  | Action                         | Issues                       |
| ------------------------------------- | ------------------------------ | ---------------------------- |
| `engines/_shared.py`                  | Modify                         | #342, #347                   |
| `engines/training_pipeline.py`        | Modify                         | #343                         |
| `engines/cluster_engine.py`           | Create                         | #344                         |
| `engines/reduction_engine.py`         | Create                         | #345                         |
| `engines/text_engine.py`              | Create                         | #346                         |
| `engines/anomaly_engine.py`           | Create                         | #348                         |
| `__init__.py`                         | Modify (lazy-load new engines) | #344, #345, #346, #347, #348 |
| `tests/unit/test_cluster_engine.py`   | Create                         | #344                         |
| `tests/unit/test_reduction_engine.py` | Create                         | #345                         |
| `tests/unit/test_text_engine.py`      | Create                         | #346                         |
| `tests/unit/test_anomaly_engine.py`   | Create                         | #348                         |
| `tests/unit/test_shared_metrics.py`   | Create or extend               | #342, #347                   |
| `tests/unit/test_cross_validate.py`   | Create                         | #343                         |
