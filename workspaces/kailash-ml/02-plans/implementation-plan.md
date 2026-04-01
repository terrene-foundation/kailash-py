# kailash-ml Implementation Plan

## Phase Overview

| Phase                         | Components                                                                                                              | Sessions  | Milestone                                  |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------------------ |
| Phase 1: Bootstrap            | C1 (package bootstrap) + C12 (polars interop)                                                                           | 1-2       | M7-ML-Bootstrap                            |
| Phase 2: Data Layer           | C3 (FeatureStore) + C4 (ModelRegistry)                                                                                  | 2-4       | M8-ML-Data-Layer                           |
| Phase 3: Training + Inference | C2 (TrainingPipeline) + C5 (InferenceServer)                                                                            | 3-4       | M9-ML-Training-Inference                   |
| Phase 4: Monitoring + Agents  | C6 (DriftMonitor) + C7 (AutoML) + C8 (DataExplorer) + C9 (HyperparameterSearch) + C10 (FeatureEngineer) + Kaizen agents | 4-6       | M10-ML-Monitoring-Agents / M11-ML-Advanced |
| Phase 5: Classical RL         | C11b (kailash-ml[rl])                                                                                                   | 1-2       | M11-ML-Advanced                            |
| **Total**                     |                                                                                                                         | **11-18** |                                            |

## Phase 1: Bootstrap (M7-ML-Bootstrap)

**Goal**: Standing package that installs, imports, and has the protocol package + interop module working.

### Session 1

**TSG-300: Package bootstrap** (P0, blocks everything)

- Create `packages/kailash-ml/` and `packages/kailash-ml-protocols/`
- Full `pyproject.toml` with all tier extras
- `kailash-ml-protocols`: MLToolProtocol, AgentInfusionProtocol, FeatureSchema, ModelSignature, MetricSpec
- `kailash_ml/__init__.py` with lazy imports
- `kailash_ml/interop.py` skeleton (completed in TSG-312)
- `kailash-ml-gpu-setup` CLI script
- Unit tests: protocol conformance, package import

**TSG-312: polars interop module** (P0, blocks FeatureStore + TrainingPipeline)

- Full implementations of all 6 conversion functions
- `to_sklearn_input()` with categorical handling
- `to_lgb_dataset()` preserving LightGBM native categorical
- `to_hf_dataset()` via Arrow (conditional import)
- Benchmark harness: 100K rows x 50 cols
- Acceptance: conversion overhead < 15% of LightGBM train time
- `CONVERSION_OVERHEAD_NOTE.md` documenting zero-copy vs allocating conversions

**Exit criteria**: `pip install kailash-ml` succeeds, `import kailash_ml` works, `import kailash_ml_protocols` works, all unit tests pass.

## Phase 2: Data Layer (M8-ML-Data-Layer)

**Goal**: FeatureStore and ModelRegistry operational with DataFlow backend.

**Prerequisite**: Phase 1 complete.

### Session 2-3

**TSG-301: FeatureStore** (P0, 1-2 sessions)

- FeatureSchema and FeatureDefinition types
- `register_features()` creates DataFlow tables (idempotent)
- `compute()` applies polars expressions
- `get_features()` with point-in-time correctness
- `get_training_set()` for time-windowed retrieval
- `get_features_lazy()` for streaming
- Bulk write path (Arrow, not to_dicts for >10K rows)
- `_feature_metadata` DataFlow model
- Integration tests: compute + store + retrieve, point-in-time accuracy

**TSG-302: ModelRegistry** (P0, 1-2 sessions)

- ModelRegistry CRUD: register, promote, load, compare, list
- ModelSerializer: native + ONNX export with graceful fallback
- DataFlow models: MLModel, MLModelVersion, MLModelTransition
- `model_metadata.json` written alongside every artifact
- MLflow MLmodel format export/import (no mlflow import)
- `onnx_status` field tracking
- ArtifactStore protocol + LocalFileArtifactStore
- Integration tests: register -> load round-trip, MLflow export round-trip, ONNX failure handling

**Exit criteria**: Features can be computed, stored, retrieved (point-in-time correct). Models can be registered, promoted, loaded, compared. MLflow format round-trips.

## Phase 3: Training + Inference (M9-ML-Training-Inference)

**Goal**: Full train-evaluate-register-serve cycle works end to end.

**Prerequisite**: Phase 2 complete (FeatureStore + ModelRegistry exist).

### Session 4-5

**TSG-303: TrainingPipeline** (P0, 2 sessions)

- Classical path: interop.to_lgb_dataset() / to_sklearn_input() at boundary
- DL path (conditional on [dl]): Lightning Trainer wrapper with lazy import
- ModelSpec, EvalSpec, TrainingResult dataclasses
- `train()` full pipeline: features -> train -> evaluate -> register
- `evaluate()` standalone (shadow mode)
- `retrain()` with registered feature_schema
- Walk-forward CV for time series
- Auto-register on evaluation success at STAGING stage
- Nexus integration (POST /api/pipelines/{name}/train)
- AgentInfusionProtocol injection point
- Integration tests: full LightGBM train -> register cycle, retrain with new data, threshold failure does not register

### Session 5-6

**TSG-304: InferenceServer** (P0, 1-2 sessions)

- predict() and predict_batch() with PredictionResult
- LRU model cache (configurable size)
- ONNX path preference (onnxruntime.InferenceSession when available)
- Native Python fallback (not an error)
- Nexus endpoint registration (POST /api/predict/{model_name})
- Input validation from model_metadata.json
- warm_cache() pre-loading
- Integration tests: register -> warm -> predict, Nexus HTTP roundtrip

**Exit criteria**: Can train a LightGBM model on synthetic data, register it, serve predictions via InferenceServer. Full cycle works in one test.

## Phase 4: Monitoring + Agents (M10-ML-Monitoring-Agents + M11-ML-Advanced)

**Goal**: DriftMonitor detects drift. AutoML finds good models automatically. All 6 agents work. All guardrails enforced.

**Prerequisite**: Phase 3 complete (InferenceServer + TrainingPipeline exist).

### Session 7

**TSG-305: DriftMonitor** (P1, 1 session)

- PSI and KS test implementations
- set_reference() stores per-feature statistics in DataFlow
- check_drift() computes PSI/KS against reference
- check_performance() compares predictions vs actuals
- schedule_monitoring() via asyncio background task (v1)
- MLDriftReport and MLDriftReference DataFlow models
- Integration tests: detect N(50,10) -> N(70,10) shift, stable distributions -> no alert

**TSG-308: HyperparameterSearch** (P1, 1 session)

- 4 strategies: grid, random, bayesian (GP surrogate + EI), halving
- SearchSpace with IntRange, FloatRange, Categorical, LogUniform
- Delegates to TrainingPipeline.evaluate() for each trial
- SearchResult with convergence_curve
- Integration test: tune LightGBM on synthetic data, best params beat defaults

### Session 8-9

**TSG-306: AutoML engine** (P1, 2 sessions)

- Pure algorithmic mode: profile -> candidates -> CV -> Bayesian optimization
- Agent-augmented mode with all 5 guardrails:
  - Guardrail 1: confidence scores on every recommendation
  - Guardrail 2: max_llm_cost_usd ($1.00 default), auto-fallback
  - Guardrail 3: auto_approve=False default, PendingApproval API
  - Guardrail 4: baseline comparison (LightGBM defaults always runs)
  - Guardrail 5: MLAgentAuditLog DataFlow model
- ExperimentSpec with guardrail fields
- LLMCostTracker for token-based cost tracking
- Integration test: full AutoML on 1000-row synthetic classification, accuracy > 0.75

**TSG-307: DataExplorer** (P1, 1-2 sessions)

- Pure statistical profiling: per-column stats, correlations, anomaly flags
- Plotly visualizations (histograms, correlation heatmap)
- 3 depth modes: quick/standard/deep
- Agent narrative (empty without Kaizen, natural language with)
- Same 5 guardrails via shared AgentGuardrailMixin
- Integration test: compare() detects deliberately skewed column

### Session 9-10

**TSG-309: FeatureEngineer** (P1, 1-2 sessions)

- Algorithmic transforms: rolling_mean, lag, diff, poly, log, sqrt, interaction, datetime_parts
- Selection: importance (LightGBM), mutual_info (sklearn), correlation
- 5 guardrails via AgentGuardrailMixin
- register_to_feature_store() convenience method
- Integration test: generate -> select -> register to FeatureStore

**TSG-310: Kaizen agent definitions** (P1, 1 session)

- All 6 agents with full Signatures (from architecture Section 5)
- All tool implementations in agents/tools.py
- Confidence output field on every Signature
- Delegate pattern (not raw LLM calls)
- Import guard: raises ImportError without kailash-kaizen
- Unit tests: Signature field validation, tool return types, import error message

**Exit criteria**: AutoML finds a good model on test data. DriftMonitor detects distribution shifts. All 6 agents instantiate with correct signatures.

## Phase 5: Classical RL (M11-ML-Advanced)

**Goal**: kailash-ml[rl] works as a thin SB3/Gymnasium wrapper.

**Prerequisite**: Phase 3 complete (TrainingPipeline exists for RLTrainer pattern).

### Session 11-12

**TSG-311: Classical RL extra** (P2, 1-2 sessions)

- RLTrainer wrapping SB3: PPO, SAC, DQN, A2C
- EnvironmentRegistry: register + make Gymnasium environments
- PolicyRegistry: extends ModelRegistry for .zip policy artifacts
- onnx_status = "not_applicable" for RL policies
- Import guards (try/except with install message)
- Integration test: PPO on CartPole-v1, 1000 timesteps, mean reward > 100

**Exit criteria**: `pip install kailash-ml[rl]` adds SB3+Gymnasium. PPO trains on CartPole successfully.

---

## Dependency Graph Between Todos

```
TSG-300 (bootstrap)
    |
    +-- TSG-312 (interop) ---- blocks --> TSG-301, TSG-303, TSG-309
    |
    +-- TSG-301 (FeatureStore) -- blocks --> TSG-302, TSG-310
    |
    +-- TSG-302 (ModelRegistry) -- blocks --> TSG-303, TSG-304, TSG-305, TSG-306, TSG-307
    |
    +-- TSG-303 (TrainingPipeline) -- blocks --> TSG-306, TSG-307, TSG-308, TSG-309, TSG-310, TSG-311
    |
    +-- TSG-304 (InferenceServer) -- blocks --> TSG-305, TSG-311
    |
    +-- TSG-305 (DriftMonitor)
    +-- TSG-306 (AutoML)
    +-- TSG-307 (DataExplorer)
    +-- TSG-308 (HyperparameterSearch) -- blocks --> TSG-306
    +-- TSG-309 (FeatureEngineer)
    +-- TSG-310 (Kaizen agents)
    +-- TSG-311 (Classical RL)
```

## Quality Tiering (from /analyze Red Team RT-R1-07)

| Tier                         | Engines                                                                      | Quality Guarantee                                                    |
| ---------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| P0 (production)              | TrainingPipeline, FeatureStore, ModelRegistry, InferenceServer, DriftMonitor | Full test coverage, integration tested, documented, production-ready |
| P1 (production with caveats) | HyperparameterSearch, AutoMLEngine                                           | Full test coverage, edge cases documented as known limitations       |
| P2 (experimental)            | DataExplorer, FeatureEngineer                                                | Core functionality tested, marked `@experimental` in API             |

P0 engines are the core lifecycle (features -> train -> register -> serve -> monitor). These must be production-quality before release. P2 engines ship but are explicitly marked experimental. If any P2 engine is not ready, it can be deferred without blocking the release.

## Interop Module Updates (from /analyze Research)

TSG-312 (polars interop) should include these additional conversions:

- `to_pandas()`: For users who need third-party library integration (SHAP, yellowbrick, etc.)
- `from_pandas()`: For users onboarding from pandas-based workflows
- `polars_to_dict_records()`: For DataFlow Express API integration
- `dict_records_to_polars()`: For DataFlow Express API response handling

These are in addition to the 6 ML-specific converters already specified.

## Red Team Mitigations (from /analyze Round 1)

| Finding                         | Mitigation                                                             | Applied To       |
| ------------------------------- | ---------------------------------------------------------------------- | ---------------- |
| RT-R1-01 (polars friction)      | Add `to_pandas()`/`from_pandas()` to interop module                    | TSG-312          |
| RT-R1-04 (guardrail confidence) | Rename to `self_assessed_confidence`; configurable cost-per-token      | TSG-306, TSG-310 |
| RT-R1-05 (ONNX UX)              | Add pre-flight compatibility check + post-export validation pass       | TSG-302          |
| RT-R1-06 (MLflow scope)         | Explicit scope limit: metadata round-trip only, no experiment tracking | TSG-302          |
| RT-R1-07 (scope risk)           | Quality tiering (P0/P1/P2)                                             | All              |
| RT-R1-09 (no polars patterns)   | Centralize DataFlow <-> polars conversion in interop module            | TSG-312, TSG-301 |

## Success Criteria

| Criterion                    | Measurement                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------- |
| Base install under 200MB     | `pip install kailash-ml` measured                                             |
| Full install under 3GB (CPU) | `pip install kailash-ml[full]` measured                                       |
| No circular import           | `python -c "import kailash_ml; import kailash_kaizen"` succeeds               |
| ONNX fidelity                | All models pass validate_onnx() with tolerance 1e-5                           |
| ModelRegistry CRUD           | Create, promote, load, compare all pass integration tests                     |
| FeatureStore roundtrip       | Compute, store, retrieve features match within tolerance                      |
| DriftMonitor sensitivity     | Detects PSI > 0.2 shift with 95% reliability                                  |
| InferenceServer latency      | Single prediction < 10ms for tabular models                                   |
| Agent Signatures valid       | All 6 agent signatures instantiate with required fields                       |
| polars-only                  | Zero pandas imports in kailash_ml source tree (except interop.to_lgb_dataset) |
| Interop overhead             | < 15% of LightGBM train time on 100K rows                                     |
| ONNX pre-flight              | Pre-flight check warns for unsupported model types before export attempt      |
| Pandas interop               | `to_pandas()` and `from_pandas()` available in interop module                 |
