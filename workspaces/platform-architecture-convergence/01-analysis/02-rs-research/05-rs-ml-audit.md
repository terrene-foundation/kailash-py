# kailash-rs ML Crate Ecosystem Audit — 2026-04-07

## Inventory: 18+ ML Crates

| Crate                        | Purpose                                                                                                  | Python Equivalent                  |
| ---------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **kailash-ml**               | Meta-crate umbrella, re-exports via feature flags                                                        | `kailash_ml` package               |
| **kailash-ml-core**          | `Fit`, `Predict`, `Transform`, `Score`, `DynEstimator` traits + `DataSet` + `MlError`                    | N/A (foundation)                   |
| **kailash-ml-linalg**        | Linear algebra (faer default, BLAS optional)                                                             | `numpy`                            |
| **kailash-ml-linear**        | OLS, Ridge, Lasso, ElasticNet, LogisticRegression, SGD, GLM, Bayesian, Robust (40+ estimators)           | `sklearn.linear_model`             |
| **kailash-ml-tree**          | CART classifier/regressor, ExtraTree                                                                     | `sklearn.tree`                     |
| **kailash-ml-ensemble**      | RandomForest, Bagging, Voting, Stacking, AdaBoost, IsolationForest                                       | `sklearn.ensemble`                 |
| **kailash-ml-boost**         | GBDT, histogram-based (LightGBM perf goal)                                                               | `xgboost`, `lightgbm`, `catboost`  |
| **kailash-ml-svm**           | SVC, SVR, LinearSVC, NuSVC                                                                               | `sklearn.svm`                      |
| **kailash-ml-neighbors**     | KNN, RadiusNeighbors, NearestCentroid, KdTree                                                            | `sklearn.neighbors`                |
| **kailash-ml-cluster**       | KMeans, DBSCAN, AgglomerativeClustering, SpectralClustering                                              | `sklearn.cluster`                  |
| **kailash-ml-decomposition** | PCA, TruncatedSVD, NMF, ICA, FactorAnalysis                                                              | `sklearn.decomposition`            |
| **kailash-ml-preprocessing** | StandardScaler, MinMaxScaler, OneHotEncoder, Imputer, label transforms                                   | `sklearn.preprocessing`            |
| **kailash-ml-metrics**       | accuracy, precision, recall, F1, ROC-AUC, MSE, R², silhouette, ranking                                   | `sklearn.metrics`                  |
| **kailash-ml-pipeline**      | Pipeline, ColumnTransformer, FeatureUnion, make_pipeline                                                 | `sklearn.pipeline`                 |
| **kailash-ml-selection**     | GridSearchCV, RandomizedSearchCV, train_test_split, KFold, StratifiedKFold                               | `sklearn.model_selection`          |
| **kailash-ml-text**          | TfidfVectorizer, CountVectorizer, HashingVectorizer                                                      | `sklearn.feature_extraction.text`  |
| **kailash-ml-misc**          | GaussianNB, MultinomialNB, GaussianProcess, Manifold, IsotonicRegression                                 | `sklearn.naive_bayes`, etc.        |
| **kailash-ml-explorer**      | DataExplorer: stats, correlations, outliers, alerts, HTML profiling reports                              | Python's `data_explorer.py`        |
| **kailash-ml-nodes**         | Workflow node integration: EstimatorFitNode, PredictNode, TransformNode, CrossValidateNode, PipelineNode | N/A                                |
| **kailash-ml-python**        | PyO3 bindings (skeleton only, lib.rs is empty)                                                           | N/A                                |
| **kailash-rl**               | Tabular Q-learning, epsilon-greedy, Thompson sampling, UCB1, environments                                | `stable-baselines3`, `gymnasium`   |
| **kailash-align-serving**    | GGUF model serving with LoRA hot-swap; llama.cpp backend; Nexus HTTP handlers                            | Python's `kailash-align` (serving) |

## Architecture: Meta-Crate with Feature Flags

`kailash-ml` is NOT a primary implementation — it's an orchestration layer:

1. **Re-exports algorithm crates via feature flags**
2. **Provides the ML Engine** (`engine::mod`):
   - `registry.rs` — EstimatorRegistry + model versioning (InMemory, FileSystem)
   - `tracker.rs` — ExperimentTracker with run telemetry
   - `automl.rs` — AutoML with GridSearchCV-like search
   - `builder.rs` — MlEngine builder composing registry + tracker
3. **Re-exports core traits**: `Fit`, `Predict`, `Transform`, `Score`, `DynEstimator`

**Default features**: linear, tree, ensemble, preprocessing, metrics, pipeline, selection

**Optional features**: boost, svm, neighbors, cluster, decomposition, text, misc, explorer

## 4-Layer Architecture

```
Core (kailash-ml-core, kailash-ml-linalg)
  ↓
Algorithms (linear, tree, ensemble, boost, svm, neighbors, cluster, decomposition, misc, text)
  ↓
Infrastructure (preprocessing, metrics, pipeline, selection, explorer)
  ↓
Engine (kailash-ml::engine: MlEngine, AutoMl, ModelRegistry, ExperimentTracker)
```

## Consistent Pattern Across All Crates

- Depend on `kailash-ml-core` (traits) + `kailash-ml-linalg` (linear algebra)
- Use `ndarray` for 2D arrays, `sprs` for sparse matrices
- Use `rayon` for parallelism where applicable
- Serialize via `serde` + `bincode`
- Register estimators via `inventory` crate (auto-registration without manual registry updates)

## Cross-SDK ML Engine Parity

| Python Engine        | Rust Equivalent                                        | Status |
| -------------------- | ------------------------------------------------------ | ------ |
| FeatureStore         | kailash-ml-pipeline (ColumnTransformer/FeatureUnion)   | ✓      |
| ModelRegistry        | engine::registry::ModelRegistry                        | ✓      |
| TrainingPipeline     | engine::automl::AutoMl + kailash-ml-pipeline::Pipeline | ✓      |
| InferenceServer      | kailash-align-serving                                  | ✓      |
| **DriftMonitor**     | **MISSING in Rust**                                    | ❌     |
| HyperparameterSearch | engine::automl::AutoMl                                 | ✓      |
| AutoMLEngine         | engine::automl::AutoMl                                 | ✓      |
| DataExplorer         | kailash-ml-explorer                                    | ✓      |
| **FeatureEngineer**  | **MISSING in Rust**                                    | ❌     |
| EnsembleEngine       | kailash-ml-ensemble                                    | ✓      |

**Gap**: Rust lacks DriftMonitor and FeatureEngineer.

## ML Agents Parity

| Python Agent               | Rust Equivalent |
| -------------------------- | --------------- |
| DataScientistAgent         | ❌ MISSING      |
| FeatureEngineerAgent       | ❌ MISSING      |
| ModelSelectorAgent         | ❌ MISSING      |
| ExperimentInterpreterAgent | ❌ MISSING      |
| DriftAnalystAgent          | ❌ MISSING      |
| RetrainingDecisionAgent    | ❌ MISSING      |

**Gap**: Rust has the **agent framework** (kailash-kaizen) but NOT the **ML domain agents**. Rust needs a new `kailash-ml-agents` crate.

## kailash-ml-python (PyO3) Status

**Lib.rs is essentially empty** — contains only a doc comment. No actual PyO3 exports.

Cargo.toml:

```toml
name = "_kailash_ml"
crate-type = ["cdylib", "lib"]
```

Intended but **not implemented**. If completed, it would enable:

- Rust-backed sklearn-compatible estimators in Python
- Zero-copy numpy ↔ ndarray interop (via `numpy` crate v0.24)
- Performance gains for compute-heavy algorithms

**Current state**: Python's kailash-ml does NOT use Rust-backed implementations. It's pure Python via sklearn/XGBoost/LightGBM/etc.

## kailash-rl Scope

**Rust-native RL** (not a wrapper around SB3/Gymnasium):

- **Bandit**: Epsilon-Greedy, Thompson Sampling, UCB1
- **Tabular**: Q-Learning with epsilon schedules
- **Environments**: FrozenLake (built-in)
- **Buffers**: ReplayBuffer, RolloutBuffer, TrajectoryBuffer
- **Training**: `train_tabular`, `run_tabular_episode`, stats aggregation

**Missing**: Deep RL (DQN, PPO, A3C, SAC, TD3). Only tabular/simple algorithms.

Python's `kailash-ml[rl]` extra = SB3 + Gymnasium wrappers. Different approach.

## kailash-align-serving

```rust
InferenceRequest → InferenceEngine (owns backend)
                      ↓
                  ServingBackend trait
                  /              \
            llama-cpp           candle (future)
               ↓
        Generate text + stream tokens
        Load LoRA adapters (hot-swap)
        Return InferenceResponse + timing
```

**Features**:

- Backend-agnostic interface (`ServingBackend` trait)
- LoRA adapter hot-swapping via `DefaultAdapterManager`
- Streaming inference (`StreamToken`, `DrainGuard`)
- Nexus HTTP handlers (optional `nexus` feature)
- Async-first API

**Parity with Python kailash-align**:

| Python                                                         | Rust                        | Status                 |
| -------------------------------------------------------------- | --------------------------- | ---------------------- |
| AlignmentPipeline (SFT, DPO, KTO, ORPO, GRPO, RLOO, OnlineDPO) | (none — serving only)       | ❌ Missing fine-tuning |
| AlignmentServing + VLLMBackend                                 | InferenceEngine + llama-cpp | ✓                      |
| AdapterRegistry + AdapterMerger                                | DefaultAdapterManager       | ✓                      |
| AlignmentEvaluator                                             | (none)                      | ❌                     |
| OnPremConfig                                                   | (none)                      | ❌                     |

**Gap**: Rust lacks the **fine-tuning pipeline**. Needs a separate `kailash-align-training` crate (or fold into `kailash-align-serving` with a feature flag).

## Modularization Trade-Off

| Python                     | Rust                    |
| -------------------------- | ----------------------- |
| 1 monolithic package       | 18+ fine-grained crates |
| Lazy-loaded engines/agents | Feature-flag modularity |

**Python approach** (CORRECT for dynamic/interpreted):

- Single import namespace
- Lazy loading hides cost
- Users prefer `pip install kailash-ml` + `from kailash_ml import ...`

**Rust approach** (CORRECT for compiled):

- Fine-grained dependency management (only include what you use)
- Faster compile times for minimal builds
- Users willing to manage 18 crates for faster builds

**Verdict**: Both approaches are correct for their language ecosystems. Neither should copy the other's modularization strategy.

**However**: Rust's 18-crate split should be documented (4-layer model, template for new algorithms) to reduce coordination overhead.

## Cross-SDK ML Interop (Not Yet Implemented)

- Python's kailash-ml uses Polars (Arrow-native)
- Rust ndarray is also Arrow-compatible (via potential `arrow` crate integration)
- kailash-ml-python PyO3 bindings are **skeleton only**

**Potential path**: Once bindings are complete, Python could opt into Rust-backed estimators for performance-critical paths.

## Convergence Recommendations

### Priority 1 (Rust gaps)

1. **Create `kailash-ml-agents` crate** — Rust equivalent of Python's 6 ML agents:
   - DataScientistAgent, FeatureEngineerAgent, ModelSelectorAgent
   - ExperimentInterpreterAgent, DriftAnalystAgent, RetrainingDecisionAgent
   - Each: `Signature`-based (LLM reasoning) + tool calls to kailash-ml engine

2. **Create `kailash-ml-drift` crate** — DriftMonitor equivalent:
   - Kolmogorov-Smirnov test (univariate shift)
   - Wasserstein distance (multivariate)
   - Covariate shift, label shift, concept drift

3. **Complete `kailash-ml-python` bindings** — expose core estimators to Python:
   - LinearRegression, RandomForest, KMeans (start with these)
   - numpy-compatible interop
   - Enable Python to fall back to Rust for compute-intensive tasks

4. **Create `kailash-align-training` crate** — Rust fine-tuning pipeline:
   - SFT, DPO, KTO, ORPO, GRPO, RLOO
   - Use Candle backend for compute (when stable)
   - Parallel to kailash-align-serving

### Priority 2 (Not blocking convergence)

5. **Document the 4-layer ML model** in both SDKs:

| Layer          | Purpose                                     | Python                            | Rust                                   |
| -------------- | ------------------------------------------- | --------------------------------- | -------------------------------------- |
| Core           | Foundational traits, errors, serialization  | `kailash_ml.types`                | kailash-ml-core                        |
| Algorithms     | 40+ estimators                              | sklearn + wrappers                | kailash-ml-{linear,tree,...}           |
| Infrastructure | Preprocessing, metrics, pipeline, selection | sklearn equivalents               | kailash-ml-{preprocessing,metrics,...} |
| Engine         | AutoML, registry, tracker, serving          | FeatureStore, ModelRegistry, etc. | engine::\*, kailash-ml-nodes           |
| Domain Agents  | LLM-driven ML workflows                     | kailash_ml.agents                 | kailash-ml-agents (TODO)               |

6. **Standardize model serialization**:
   - Python: MLflow format (.pkl, JSON metadata)
   - Rust: bincode (binary) + ModelArtifact
   - Recommend: Dual support (MLflow for portability, bincode for Rust speed)

### NOT Recommended

- ❌ **Don't consolidate Rust's 18 crates** — the split is correct for compiled languages
- ❌ **Don't split Python's monolithic package** — the lazy-loading approach is correct for Python
- ❌ **Don't force ML convergence now** — ML is healthy in both SDKs, just needs gap-filling on Rust

## Current Parity Score

**~75%** (Rust has core + engines but lacks domain agents, drift detection, fine-tuning, and PyO3 bindings).

Once the 4 Rust gap crates are added, parity reaches ~95%.

## ML Out of Scope for Convergence Workspace

ML is healthy in both SDKs and doesn't need architectural refactoring. The Rust gaps are feature additions, not architectural problems. They can be tracked as **separate `cross-sdk` issues** on the Rust repo and worked independently of the platform-architecture-convergence workspace.

**This workspace focuses on**: Kaizen + MCP + Providers + Nexus + Core SDK consolidation. ML stays in its own lane.
