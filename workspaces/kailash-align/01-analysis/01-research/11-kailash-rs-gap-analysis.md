# kailash-rs Gap Analysis: Alignment, RL & ML Training (CORRECTED)

**Corrected**: 2026-04-01 — Previous version was superficial. This version is based on full source code audit.

## Executive Summary

kailash-rs v3.6.4 is **inference + feature engineering only** — no training capability exists in code today. However, a **179-todo roadmap for full native Rust training** (17 crates, 455+ sklearn algorithms, gradient boosting engines) has been architecturally approved and red-team verified. The previous analysis incorrectly characterized kailash-rs as permanently inference-only.

The correct framing:
- **Classical ML training**: Will be native Rust (kailash-ml v1.0 roadmap). NOT "train in Python."
- **LLM alignment (SFT/DPO/GRPO)**: Stays in Python (kailash-align). Rust handles serving only (kailash-align-serving).
- **Classical RL (SB3/gymnasium)**: Python only for now. Rust RL is out of scope.

## 1. Current State (v3.6.4) — Source Code Verified

### What EXISTS in code today

| Component | Status | Detail |
|-----------|--------|--------|
| **Feature Engineering** | Production | StandardScaler, OneHotEncoder, FeaturePipeline (pure Rust, polars) |
| **Inference Backends** | Production | TractBackend (always), OrtBackend (default), CandleBackend (optional) |
| **Model Registry** | Production | In-memory metadata + SHA-256 checksums |
| **Data Interop** | Production | Value ↔ DataFrame ↔ ndarray conversions (713 lines) |
| **Training** | ZERO | No optimizers, no loss functions, no gradient descent |
| **Classical ML algorithms** | ZERO | Only 2 transformers (scaler, encoder). No regressors, classifiers, clusterers |
| **LLM alignment** | ZERO | No DPO, GRPO, SFT, RLHF |

### Dependencies (Cargo.toml verified)

```toml
# Inference
tract-onnx = "0.22"             # Always available
ort = "2.0.0-rc.12"             # Optional, default enabled
candle-core = "0.9"             # Optional

# Data
polars = "0.53"                 # Feature engineering
ndarray = "0.16"                # Tensor operations

# Future (optional, not yet used)
linfa = "0.8"                   # Optional feature flag, zero usage in code
ndarray-linalg = "0.16"         # Optional, for future linear algebra
```

**Zero Python interop**: No PyO3, no scikit-learn FFI, no Python bridge. 100% pure Rust.

## 2. Planned State: Full Native Rust ML Engine

### 2.1 Architecture (8 locked decisions, red-team verified)

From `workspaces/kailash-ml-crate/briefs/01-architecture-decisions.md`:

| Decision | Choice |
|----------|--------|
| D1 | Standalone library, zero Kailash dependency |
| D2 | Type-state traits (Fit → Predict) with erasure layer |
| D3 | DataSet enum (Dense/Sparse/Tabular) |
| D4 | FitOpts struct + PartialFit trait for online learning |
| D5 | Native Rust pipeline (zero serialization overhead) |
| D6 | **17-crate workspace** (core, linear, tree, ensemble, gb, svm, neighbors, cluster, decomp, etc.) |
| D7 | faer primary (pure Rust), BLAS optional |
| D8 | Gradient boosting performance targets (0.5-0.7x LightGBM V1, 0.8-0.95x V2) |

### 2.2 Roadmap (179 todos, 16 milestones)

| Milestone | Scope | Crates |
|-----------|-------|--------|
| M0 | Foundation: workspace, traits, DataSet, testing | kailash-ml-core |
| M1 | Preprocessing + all metrics | kailash-ml-core |
| M2 | Linear models (OLS, Ridge, Lasso, LogReg, SGD, GLMs) | kailash-ml-linear |
| M3 | Trees (CART, DecisionTree, ExtraTree, pruning) | kailash-ml-tree |
| M4 | Ensembles (RandomForest, Bagging, AdaBoost, Voting, Stacking) | kailash-ml-ensemble |
| M5 | **Gradient Boosting** (histogram binning, GOSS, EFB, DART, TreeSHAP) | kailash-ml-gb |
| M6 | SVM (SMO solver, SVC/SVR, NuSVM) | kailash-ml-svm |
| M7 | Neighbors + Clustering (KNN, KMeans, DBSCAN, Spectral) | kailash-ml-neighbors, kailash-ml-cluster |
| M8 | Decomposition (PCA, NMF, ICA, TruncatedSVD) | kailash-ml-decomp |
| M9 | Model Selection (GridSearchCV, cross_val_score) | kailash-ml-selection |
| M10 | Remaining (NaiveBayes, LDA, MLP, GaussianProcess, GMM) | various |
| M11 | Text Features (CountVectorizer, TfidfVectorizer) | kailash-ml-core |
| M12 | Engine Layer (ModelRegistry, ExperimentTracker, AutoML) | kailash-ml |
| M13 | Kailash Integration (EstimatorNode, macro generation) | kailash-ml-nodes |
| M14 | **Python Bindings** (PyO3, sklearn compatibility layer) | kailash-ml-python |
| M15 | Performance (SIMD, arena allocators, benchmarks) | all |
| M16 | Docs + Release (crates.io, PyPI via maturin) | all |

### 2.3 Training Primitives (Planned, NOT built)

- Gradient descent: SGD, Mini-batch, Momentum, Adam, RMSProp
- Solvers: Coordinate Descent, L-BFGS, Newton-CG, SAGA
- Loss functions: MSE, log-loss, hinge, poisson, tweedie
- Regularization: L1/L2/ElasticNet, early stopping
- Online learning: PartialFit trait

## 3. Gap Analysis: What's ACTUALLY Missing

### 3.1 Classical ML Training → Native Rust (PLANNED, not built)

**Previous analysis said**: "train in Python, serve in Rust"
**Correction**: Classical ML training will be **native Rust** when kailash-ml v1.0 ships. NOT Python.

### 3.2 LLM Alignment → Python training, Rust serving

This IS correct. LLM fine-tuning (SFT, DPO, GRPO) requires PyTorch + TRL, which don't have Rust equivalents. The cross-SDK workflow:

```
kailash-align (Python)              kailash-align-serving (Rust)
  fine-tune (SFT/DPO/GRPO/KTO)       load GGUF
  evaluate (lm-eval)                   serve via kailash-nexus
  export GGUF                          hot-swap LoRA adapters
  ↓                                    ↑
  GGUF file ───────────────────────────┘
```

### 3.3 Classical RL → Python only (no Rust equivalent planned)

Stable-baselines3 + gymnasium are Python-only. No Rust equivalent is planned. RL-for-LLMs (GRPO etc.) is in kailash-align (Python).

### 3.4 kailash-align-serving → Workspace created, not yet implemented

**Status**: Brief written at `kailash-rs/workspaces/kailash-align-serving/briefs/00-overview.md`
**Scope**: GGUF loading (llama-cpp-rs or candle), ModelRegistry integration, Nexus API exposure
**NOT needed for**: Classical ML (will train natively in Rust via kailash-ml v1.0)

## 4. Implications for kailash-py

### 4.1 kailash-ml (Python) vs kailash-ml (Rust)

Both SDKs implement independently (EATP D6), but the Rust roadmap is more ambitious:
- **Python**: 9 engines (FeatureStore, TrainingPipeline, ModelRegistry, etc.), polars-native, wrapping sklearn/lightgbm
- **Rust**: 17 crates, native implementations (no wrappers), faer linear algebra, 455+ algorithms

The Python SDK wraps existing libraries. The Rust SDK implements from scratch.

### 4.2 kailash-align exists only in Python

Correct and intentional. LLM alignment requires PyTorch ecosystem. Rust gets serving only.

### 4.3 kailash-ml[rl] exists only in Python

Classical RL (SB3, gymnasium) has no Rust equivalent. This is the correct boundary.

## 5. Cross-References

- kailash-rs ML crate source: `~/repos/loom/kailash-rs/crates/kailash-ml/`
- kailash-rs ML workspace: `~/repos/loom/kailash-rs/workspaces/kailash-ml-crate/`
- kailash-rs align serving workspace: `~/repos/loom/kailash-rs/workspaces/kailash-align-serving/`
- kailash-py align workspace: `~/repos/loom/kailash-py/workspaces/kailash-align/`
