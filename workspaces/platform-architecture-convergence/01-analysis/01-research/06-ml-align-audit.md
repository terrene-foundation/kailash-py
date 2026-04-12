# kailash-ml + kailash-align Audit — 2026-04-07

**Audit scope**: Verify whether ML and Align frameworks repeat the kaizen/MCP fragmentation pattern or learned from it.

## Verdict: HEALTHY — No Fragmentation

Both kailash-ml and kailash-align are architecturally clean. They learned from the kaizen mistakes: no circular dependencies, no code duplication, no trust/PACT/DataFlow coupling, agents properly decoupled.

## kailash-ml — Primitive Layer

**Location**: `packages/kailash-ml/src/kailash_ml/engines/`

| Primitive               | File                   | LOC  |
| ----------------------- | ---------------------- | ---- |
| `FeatureStore`          | `feature_store.py`     | 440  |
| `ModelRegistry`         | `model_registry.py`    | 920  |
| `TrainingPipeline`      | `training_pipeline.py` | 757  |
| `PreprocessingPipeline` | `preprocessing.py`     | 1307 |

**Shared infrastructure**:

- `_shared.py` — common validation
- `_guardrails.py` — framework guardrails
- `_feature_sql.py` — single auditable SQL touchpoint (uses Core SDK's ConnectionManager + QueryDialect)

## kailash-ml — Engine Layer

| Engine                 | File                       | LOC  | Composes                                     |
| ---------------------- | -------------------------- | ---- | -------------------------------------------- |
| `AutoMLEngine`         | `automl_engine.py`         | 587  | **TrainingPipeline + HyperparameterSearch**  |
| `InferenceServer`      | `inference_server.py`      | 630  | **ModelRegistry** (delegates lookup/serving) |
| `DriftMonitor`         | `drift_monitor.py`         | 875  | FeatureStore + optional agents               |
| `DataExplorer`         | `data_explorer.py`         | 1042 | Optional agent augmentation                  |
| `ExperimentTracker`    | `experiment_tracker.py`    | 1316 | MLflow-compatible                            |
| `HyperparameterSearch` | `hyperparameter_search.py` | 808  | Optuna/sklearn wrapper                       |
| `FeatureEngineer`      | `feature_engineer.py`      | 461  | Optional agents                              |
| `EnsembleEngine`       | `ensemble.py`              | 611  | Ensemble composition                         |
| `ModelVisualizer`      | `model_visualizer.py`      | 745  | SHAP + feature importance                    |
| `ModelExplainer`       | `model_explainer.py`       | 468  | LIME + SHAP                                  |

**Total**: 4 primitives + 10 engines = 14 components, cleanly separated.

## kailash-ml — Composition Verdict: CLEAN

- **AutoMLEngine explicitly takes** `pipeline: TrainingPipeline` and `search: HyperparameterSearch` as constructor args
- **InferenceServer takes** `registry: ModelRegistry` and delegates model lookup/serving
- **Zero primitive logic duplicated** in engines
- **Agents are optional, opt-in**: `agent=True` flag or `pip install kailash-ml[agents]` extra

## kailash-ml — Cross-Framework Dependencies

**Imports** (minimal, only Core SDK):

```python
from kailash.db.connection import ConnectionManager
from kailash.db.dialect import _validate_identifier
```

**Does NOT import**:

- `kailash.trust.*`
- `kailash_pact`
- `kailash_dataflow` (only Core SDK's ConnectionManager)
- `kailash.mcp_server.*`
- `kaizen` at module level (lazy-imported in agents only)

**Protocols** (defined locally in `kailash_ml/types.py`):

- `MLToolProtocol` — interface for Kaizen agents to call ML services via MCP
- `AgentInfusionProtocol` — interface for ML engines to call Kaizen agents optionally

**These are inbound/outbound protocols, not hard dependencies.** The `kailash-ml-protocols` package was eliminated per commit "feat: complete outstanding items — protocols elimination" — protocols now live in `kailash_ml/types.py`, circular dependency broken.

## kailash-ml — Agents (6 total)

**Location**: `packages/kailash-ml/src/kailash_ml/agents/`

1. DataScientistAgent (`data_scientist.py`)
2. FeatureEngineerAgent (`feature_engineer.py`)
3. ModelSelectorAgent (`model_selector.py`)
4. ExperimentInterpreterAgent (`experiment_interpreter.py`)
5. DriftAnalystAgent (`drift_analyst.py`)
6. RetrainingDecisionAgent (`retraining_decision.py`)

**Base class**: All extend `kaizen.core.BaseAgent` via lazy import `_import_kaizen()`.

**Architecture**: LLM-first, Signature-based, dumb tools. Lazy-loaded via `from kailash_ml.agents import ...` to avoid requiring `kailash-kaizen` unless `pip install kailash-ml[agents]`.

**Integration**: Engines call agents via the AgentInfusionProtocol, e.g., `AutoMLEngine.run()` calls `_call_kaizen_agents(...)` if `config.agent=True`.

**Critical observation**: ML agents WILL INHERIT the broken BaseAgent MCP if they ever need MCP tools. Currently they don't (they use dumb data tools) so the breakage is latent. After the kaizen refactor, ML agents will automatically benefit.

## kailash-align — Primitive Layer

**Location**: `packages/kailash-align/src/kailash_align/`

**Primitives**:

- `AlignmentConfig` + subconfigs (LoRA, SFT, DPO, KTO, ORPO, GRPO, RLOO, Online DPO)
- `AlignmentPipeline` — registry-driven training orchestration (acts as primitive)

**Support modules**:

- `AdapterRegistry` — tracks trained adapters
- `MethodRegistry` — registry of training methods
- `RewardRegistry` — reward function registry
- `AlignmentEvaluator` — evaluation engine
- `AlignmentServing` — vLLM/HF serving

## kailash-align — Engine Layer (Implicit, Registry-Based)

- `AlignmentPipeline.train()` — dispatches to MethodRegistry + RewardRegistry + AdapterRegistry
- `AlignmentEvaluator.evaluate()` — evaluation orchestration
- `AlignmentServing` — model serving (vLLM or HF)
- `AdapterMerger.merge()` — LoRA merging
- `KaizenModelBridge` — bridge for Kaizen agents to use aligned models

## kailash-align — Composition Verdict: PARTIAL

Uses **registry pattern** rather than explicit primitive/engine split. Less pedagogical than ML's explicit composition, but still clean — no duplication, no circular deps, extensible.

## kailash-align — Cross-Framework Dependencies

**Imports**: ONLY internal (`from kailash_align...`).

**Does NOT import**: Any kailash framework (Core, Kaizen, DataFlow, PACT, Trust).

**Why isolated**: Align is LLM-specific (fine-tuning/alignment). Orthogonal to Core SDK's workflow execution model.

## kailash-align — Agents (4 total)

1. AlignmentStrategistAgent — recommend training method
2. DataCurationAgent — data curation
3. TrainingConfigAgent — configure training
4. EvalInterpreterAgent — interpret evaluation results

All extend `kaizen.core.BaseAgent` via lazy import. Same LLM-first architecture as ML agents.

## Architectural Health Comparison

| Dimension                     | kailash-ml                            | kailash-align              |
| ----------------------------- | ------------------------------------- | -------------------------- |
| Primitive/engine split        | Explicit (4+10)                       | Implicit (config+registry) |
| Composition pattern           | Explicit constructor injection        | Registry dispatch          |
| Cross-framework imports       | Core SDK only (ConnectionManager)     | None                       |
| Agents                        | 6 BaseAgent subclasses                | 4 BaseAgent subclasses     |
| Protocols instead of deps     | MLToolProtocol, AgentInfusionProtocol | None (isolated)            |
| Code duplication              | None                                  | None                       |
| Trust/PACT/DataFlow coupling  | None                                  | None                       |
| Circular package dependencies | Eliminated                            | None                       |
| Same mistake as kaizen?       | **NO**                                | **NO**                     |

## What These Frameworks Do Right (That Kaizen Should Copy)

1. **Protocols in types.py, not a separate package**: `kailash-ml-protocols` was eliminated when protocols moved inline. This broke the circular dependency without requiring a phantom package. **Kaizen should apply the same pattern** instead of perpetuating `kailash-ml-protocols`-like crutches.

2. **Lazy agent loading**: Both frameworks avoid hard dependencies on kaizen by lazy-importing agents only when `[agents]` extra is installed. **Clean opt-in pattern.**

3. **Engines compose primitives via constructor injection**: `AutoMLEngine(pipeline, search, registry)` is the template. **Kaizen's Delegate should do the same with `Delegate(agent, governance, budget, ...)`.**

4. **Single auditable SQL touchpoint**: `_feature_sql.py` consolidates all dynamic SQL. **Security-conscious pattern that others should adopt.**

5. **Double opt-in for expensive features**: Agents require BOTH `pip install kailash-ml[agents]` AND `agent=True` at call site. **Prevents accidental agent invocation, makes cost explicit.**

## Recommendations

### ✅ No refactor needed for ML or Align.

Three minor improvements (not architectural):

1. **Document primitive/engine split in ML README** — make explicit that FeatureStore/ModelRegistry/TrainingPipeline/PreprocessingPipeline are primitives, AutoMLEngine/InferenceServer/DriftMonitor are engines.

2. **Document Align registry pattern in README** — explain how methods dispatch via MethodRegistry, show how to register custom methods.

3. **After kaizen refactor, verify ML/Align agents still work** — both frameworks use BaseAgent; the kaizen refactor should preserve their public API and fix their latent MCP issue as a side-effect.

## What This Means For Convergence Scope

**ML and Align are out of scope for architectural refactor.** They will benefit from the kaizen refactor (via BaseAgent) without any changes on their side.

This reduces the total refactor scope significantly: the 9 frameworks becomes 3-4 areas of active work (Kaizen, Nexus auth/audit/PACT, MCP extraction, Core SDK cleanup) rather than a full platform rewrite.
