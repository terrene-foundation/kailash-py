# kailash-ml Overview Brief

## What This Is

kailash-ml is a NEW Python package built from scratch. It is the 7th Kailash framework (with kailash-align as the 8th). It provides the classical and deep learning lifecycle for the Kailash ecosystem: train models, store features, serve predictions, monitor drift, and optionally augment with AI agents.

**Install**: `pip install kailash-ml` (base, ~195MB) | `pip install kailash-ml[dl]` (deep learning) | `pip install kailash-ml[full]` (everything)

**Package location**: `packages/kailash-ml/` in the kailash-py monorepo, alongside `packages/kailash-ml-protocols/` (thin interface package).

## The 8 Kailash Frameworks

| Framework | Package            | Purpose                                     |
| --------- | ------------------ | ------------------------------------------- |
| Core SDK  | `kailash`          | Workflow orchestration, 140+ nodes          |
| DataFlow  | `kailash-dataflow` | Zero-config database operations             |
| Nexus     | `kailash-nexus`    | Multi-channel deployment (API+CLI+MCP)      |
| Kaizen    | `kailash-kaizen`   | LLM agent framework                         |
| PACT      | `kailash-pact`     | Organizational governance (D/T/R)           |
| Trust     | `kailash[trust]`   | EATP protocol + trust-plane                 |
| **ML**    | **`kailash-ml`**   | **Classical + deep learning lifecycle**     |
| Align     | `kailash-align`    | LLM fine-tuning/alignment + on-prem serving |

## Key Architectural Decisions

These decisions are final (converged across 3 red team rounds, 10 journal entries, ~200K chars of analysis).

### 1. polars-only with interop module

kailash-ml NEVER converts to/from pandas internally. All engines accept and return `pl.DataFrame` or `pl.LazyFrame`. When a base package requires numpy arrays (sklearn, LightGBM), conversion happens at the boundary via a centralized `kailash_ml.interop` module.

**Why**: Arrow-native enables Rust interop and is 10-100x faster for data operations. The polars ecosystem friction is mitigated by providing optimized, benchmarked converters.

**Interop module provides**: `to_sklearn_input()`, `from_sklearn_output()`, `to_lgb_dataset()`, `to_hf_dataset()`, `polars_to_arrow()`. Each converter handles categorical types, null values, and dtype preservation correctly.

### 2. sklearn + LightGBM in base (~195MB)

The base install (`pip install kailash-ml`) includes scikit-learn and LightGBM. This means a user who runs `pip install kailash-ml` can train and serve a model within 5 minutes, without any extras. A base install that cannot train or serve a model would be a framework with no content.

PyTorch and deep learning libraries are in the `[dl]` extra. Classical RL (SB3, Gymnasium) is in `[rl]`. LLM alignment (TRL, PEFT) is NOT in kailash-ml at all -- it lives in kailash-align.

### 3. Lightning for deep learning training

PyTorch deep learning uses Lightning (`lightning.Trainer`) internally. Lightning eliminates boilerplate for distributed training, mixed precision, checkpointing, and logging. The alternative (reimplementing all of this) would be worse than the debugging complexity of an extra abstraction layer. An escape hatch (`TrainingPipeline(lightning=False)`) is provided for users who want raw PyTorch training loops.

### 4. 5 mandatory agent guardrails

All agent-augmented engines (AutoML, DataExplorer, FeatureEngineer) MUST implement these 5 guardrails:

1. **Confidence scores**: Every agent recommendation includes a confidence score (0-1)
2. **Cost budget**: `max_llm_cost_usd` parameter, default $1.00 per invocation
3. **Human approval gate**: `auto_approve=False` default -- agent proposes, human confirms
4. **Baseline comparison**: Pure algorithmic recommendation shown alongside agent recommendation
5. **Audit trail**: All agent decisions logged to DataFlow `MLAgentAuditLog`

Agent infusion is explicitly optional: double opt-in required (`pip install kailash-ml[agents]` AND `agent=True` at call site). Pure algorithmic mode is the default and is fully functional.

### 5. ModelRegistry with MLflow format v1 compatibility

ModelRegistry is focused on model lifecycle management (staging, shadow, production, archive), not experiment tracking. It does NOT try to replace MLflow/W&B.

- v1 exports/imports MLflow MLmodel format only. "Compatible" means metadata round-trips through MLflow without data loss.
- W&B, Neptune, ClearML compatibility planned for v1.1.
- `onnx_status` field tracks ONNX export success/failure per model version. ONNX export failure is NOT fatal -- the model falls back to native Python inference.

### 6. Circular dependency resolution

kailash-ml uses Kaizen agents for AutoML; Kaizen agents use kailash-ml predictions via MCP tools. This is a hard circular dependency.

**Resolution**: A thin interface package `kailash-ml-protocols` (~50KB) breaks the cycle.

```
kailash-ml-protocols   (NEW, ~50KB)
    - MLToolProtocol         (predict, get_metrics, trigger_retrain)
    - AgentInfusionProtocol  (suggest_features, select_model, interpret_results)
    - FeatureSchema, ModelSignature, MetricSpec

kailash-ml
    +-- kailash-ml-protocols  (import contracts)
    # Implements MLToolProtocol
    # OPTIONALLY consumes AgentInfusionProtocol at runtime

kailash-kaizen
    +-- kailash-ml-protocols  (import contracts)
    # OPTIONALLY implements AgentInfusionProtocol
    # OPTIONALLY consumes MLToolProtocol via MCP tools
```

Neither package depends on the other at install time. Runtime discovery via `try/except ImportError`.

### 7. ONNX bridge with defined fallback

The ONNX bridge enables "train in Python, serve in Rust." Every model registered in ModelRegistry includes a `model_metadata.json` with input/output schemas, Arrow schema, and ONNX artifacts.

**ONNX export failures are expected for some model types.** When export fails:
- Native artifact is stored (Python inference works)
- `onnx_status` set to `"failed"` with error message
- InferenceServer serves via native Python path
- Rust consumers get clear error: "Model X is not ONNX-compatible. Serve from Python."

v1 ONNX guarantees: sklearn (all), LightGBM, XGBoost, CatBoost, PyTorch feedforward. Best effort: custom PyTorch architectures, timm models, HuggingFace models.

## 9 Engines

| Engine | Purpose | Depends On |
|--------|---------|------------|
| TrainingPipeline | Full training lifecycle orchestration | FeatureStore, ModelRegistry |
| FeatureStore | Compute, version, store, serve features (DataFlow-backed) | DataFlow, polars |
| ModelRegistry | Model lifecycle: staging -> shadow -> production -> archived | DataFlow, ArtifactStore |
| InferenceServer | Load, cache, serve predictions; auto-expose via Nexus | ModelRegistry, Nexus (optional) |
| DriftMonitor | Feature drift + performance degradation detection (PSI, KS) | InferenceServer, FeatureStore |
| AutoMLEngine | Automated model selection + hyperparameter optimization | TrainingPipeline, AgentInfusionProtocol (optional) |
| DataExplorer | Statistical profiling + visualizations + narrative | polars, plotly, AgentInfusionProtocol (optional) |
| HyperparameterSearch | Grid, random, Bayesian, successive halving | TrainingPipeline |
| FeatureEngineer | Automated feature generation + selection | FeatureStore, AgentInfusionProtocol (optional) |

## 6 Kaizen Agents

| Agent | Purpose | Key Signature Outputs |
|-------|---------|----------------------|
| DataScientistAgent | High-level data analysis + ML strategy | data_assessment, recommended_approach, risks |
| FeatureEngineerAgent | Feature design, evaluation, pruning | proposed_features, feature_interactions, features_to_drop |
| ModelSelectorAgent | Model family + config recommendation | candidate_models, expected_performance, experiment_plan |
| ExperimentInterpreterAgent | Trial result analysis + next steps | interpretation, patterns, failure_analysis, recommendations |
| DriftAnalystAgent | Drift report interpretation + action decision | assessment, root_cause, impact, recommendation, urgency |
| RetrainingDecisionAgent | Retrain/monitor/rollback decision | decision, rationale, retrain_spec, fallback_plan |

All agents emit `confidence: float` (Guardrail 1), use Kaizen `Delegate` pattern (not raw LLM calls), and have tools that are dumb data endpoints (rules/agent-reasoning.md).

## Dependency Graph

```
                    kailash (core SDK)
                   /        |         \
        kailash-dataflow  kailash-nexus  kailash-kaizen
              |              |              |
              +--------------+--------------+
              |                             |
         kailash-ml-protocols    kailash-ml-protocols
              |                             |
         kailash-ml                    kailash-kaizen
         (implements MLToolProtocol)   (implements AgentInfusionProtocol)
              |                             |
              +---- runtime discovery ------+
```

## Testing Strategy (5-Tier)

| Tier | Focus | Speed | When |
|------|-------|-------|------|
| Tier 0: Regression | Bug reproduction | <1s each | Every commit |
| Tier 1: Unit | Engine logic, schema validation, serialization | <5s each | Every commit |
| Tier 2: Integration | Engine-to-engine flows, DataFlow, Nexus | <30s each | Every PR |
| Tier 3: ML Validation | Model quality, training convergence, ONNX fidelity | <5min each | Nightly/release |
| Tier 4: GPU | CUDA training, mixed precision, distributed | <10min each | Weekly/pre-release |

## Red Team Findings Incorporated

All findings from 3 red team rounds are resolved in the architecture:

- **RT1-Finding1** (polars tax): `kailash_ml.interop` module with benchmarked converters, 15% overhead threshold
- **RT1-Finding2** (base install useless): sklearn + LightGBM in base, not optional
- **RT1-Finding3** (agent infusion unvalidated): 5 guardrails, double opt-in, pure algorithmic default
- **RT1-Finding4** (ONNX bridge failures): Defined fallback, compatibility matrix, `onnx_status` field
- **RT1-Finding5** (TRL/RLHF scope creep): Split to kailash-align; classical RL stays as `kailash-ml[rl]`
- **RT1-Finding6** (ModelRegistry not MLflow): MLflow format compatibility, not replacement
- **RT1-Finding7** (triple framework dependency): Pin versions, insulate via protocols
- **RT1-Finding8** (Lightning complexity): Accept trade-off, provide escape hatch
- **RT2-01** (kailash-align split): kailash-align is separate package; `kailash-ml[rl]` has SB3+Gymnasium only (no TRL)
- **RT2-03** (ModelRegistry format): MLflow MLmodel format v1 compatibility
- **RT2-04** (agent guardrails): All 5 guardrails are v1 requirements
