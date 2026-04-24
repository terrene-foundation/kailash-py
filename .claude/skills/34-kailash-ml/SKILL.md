---
name: kailash-ml
description: "Kailash ML 1.0.0 — MANDATORY for ALL ML training/inference/feature/drift/AutoML/RL work. Engine-first km.* surface (train/register/serve/track/diagnose/watch/dashboard/seed/reproduce/resume/lineage/rl_train/engine_info/list_engines/autolog) + 18 engines. Raw sklearn / pytorch / numpy training loops BLOCKED."
---

# Kailash ML 1.0.0 — Classical / Deep Learning / RL Lifecycle

Production ML lifecycle framework built on Kailash Core SDK — engine-first `km.*` verb surface, 18-engine discovery registry, polars-native, ONNX-default serialisation, Agent Tool Discovery for Kaizen integration, wave-released with 6 sibling packages.

## 1.0.0 Engine-First Surface (Canonical)

Single entry: `import kailash_ml as km`. Zero-arg construction. 14 lifecycle verbs + 2 discovery verbs grouped in `__all__`:

```python
import kailash_ml as km

async with km.track("demo") as run:                        # Group 1 lifecycle
    result = await km.train(df, target="y")                # Group 1 lifecycle
    registered = await km.register(result, name="demo")    # Group 1 lifecycle
server = await km.serve("demo@production")                 # Group 1 lifecycle
# $ kailash-ml-dashboard  (separate shell)                 # Group 1 lifecycle

km.diagnose(model)                                         # Group 1 — DLDiagnostics / RAGDiagnostics / RLDiagnostics
km.watch(model, reference_df)                              # Group 1 — DriftMonitor
km.seed(42); await km.reproduce(run_id)                    # Group 1 — reproducibility
await km.resume(run_id)                                    # Group 1 — checkpoint resume
graph = await km.lineage("demo@v1", tenant_id=None)        # Group 1 — LineageGraph; ambient tenant via get_current_tenant_id()
await km.rl_train(env, policy)                             # Group 1 — RL
km.autolog()                                               # Group 1 — sklearn/lgb/Lightning/torch auto-logging

info = km.engine_info("TrainingPipeline")                  # Group 6 Engine Discovery (agents MUST use this, not imports)
engines = km.list_engines()                                # Group 6 — 18-engine catalog per §E1.1
```

**Quick Start fingerprint** (pinned, regression-tested via `ml-engines-v2 §16.3`):
`c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00`

## 21 Canonical Specs

Authoritative domain truth lives in `specs/`. Read the spec before touching the code:

### Engine Core (4)

- `specs/ml-engines-v2.md` — MLEngine 1.0.0, 8-method MLEngine surface (per Decision 8 Lightning lock-in), `TrainingResult` + `DeviceReport`, `km.*` wrappers, canonical README Quick Start (§16 fingerprint contract).
- `specs/ml-engines-v2-addendum.md` — 18-engine catalog (§E1.1), classical-ML surface, `EngineInfo` / `MethodSignature` / `ParamSpec` / `ClearanceRequirement` frozen dataclasses (§E11.1), `LineageGraph` + `LineageNode` + `LineageEdge` (§E10), Pydantic-to-DataFrame adapter.
- `specs/ml-backends.md` — 6 first-class backends (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto, Lightning integration, hardware-gated CI, `backend-compat-matrix.yaml` data.
- `specs/ml-diagnostics.md` — DLDiagnostics cross-SDK Diagnostic Protocol, torch-hook instrumentation, plotly gated by `[dl]` extra.

### Experiment / Registry / Serving (4)

- `specs/ml-tracking.md` — ExperimentTracker async-context ambient-run scope, nested runs, auto-logging, GDPR erasure, MLflow import bridge, `ExperimentTracker.create()` factory, `get_current_run()` contextvar accessor.
- `specs/ml-registry.md` — ModelRegistry lifecycle (staging → shadow → production → archived), `RegisterResult.artifact_uris: dict[str, str]` (§7.1 canonical), §7.1.1 v1.x `@property` back-compat shim, §7.1.2 Single-Format-Per-Row DDL Invariant, §5.6 ONNX export probe.
- `specs/ml-serving.md` — InferenceServer + ServeHandle, REST + MCP channels, §4.1 batch padding, §5.2 streaming backpressure, §2.5.3 pickle-fallback gate.
- `specs/ml-autolog.md` — sklearn / lightgbm / PyTorch Lightning / torch loop auto-logging, DDP rank-0-only (Decision 4), metric namespace discipline.

### AutoML / Drift / Feature Store / Dashboard (4)

- `specs/ml-automl.md` — AutoMLEngine agent-infused (grid/random/bayesian/successive-halving) + cost budget + human-approval gate + PACT envelope.
- `specs/ml-drift.md` — DriftMonitor (KS / chi2 / PSI / Jensen-Shannon), scheduled monitoring, retraining hooks.
- `specs/ml-feature-store.md` — Polars-native FeatureStore on ConnectionManager, point-in-time queries, schema enforcement.
- `specs/ml-dashboard.md` — MLDashboard CLI + `km.dashboard()` launcher + Streamlit panels.

### Reinforcement Learning (3)

- `specs/ml-rl-core.md` — RLTrainer + registries + `km.rl_train()` (Stable-Baselines3 + Gymnasium).
- `specs/ml-rl-algorithms.md` — PPO / SAC / DQN / A2C / TD3 / DDPG / MaskablePPO / Decision Transformer catalog.
- `specs/ml-rl-align-unification.md` — kailash-ml.rl ↔ kailash-align trajectory bridge (GRPO / RLOO / PPO-LM).

### Integrations (6)

- `specs/kailash-core-ml-integration.md`, `specs/dataflow-ml-integration.md`, `specs/nexus-ml-integration.md`, `specs/kaizen-ml-integration.md`, `specs/align-ml-integration.md`, `specs/pact-ml-integration.md`.

## 14 Approved Decisions (pinned 2026-04-21)

1. Status vocabulary — `FINISHED` only; hard-migrate legacy SUCCESS/COMPLETED at install.
2. GDPR erasure — audit rows IMMUTABLE with sha256 fingerprints.
3. Cross-SDK Rust enum parity — `{RUNNING, FINISHED, FAILED, KILLED}` byte-identical.
4. DDP/FSDP/DeepSpeed — rank-0-only hardcoded via `torch.distributed.get_rank() == 0`.
5. XPU dual-path — `torch.xpu` native-first + `intel_extension_for_pytorch` fallback.
6. GPU architecture cutoff — `backend-compat-matrix.yaml` as data; `km.doctor` reads it.
7. CI runner — CPU + MPS BLOCKING now; CUDA BLOCKING when self-hosted lands.
8. Lightning hard lock-in — raw loops raise `UnsupportedTrainerError`; no escape hatch.
9. Rust ExperimentTracker — explicit `start_run()`/`end_run()` (AsyncDrop not stable).
10. Single canonical spec per domain; Rust overlays via `loom/.claude/variants/rs/`.
11. Legacy namespace sunset — at 3.0; 2.x DeprecationWarning; 1.x back-compat shim.
12. Cross-tenant admin export — `MultiTenantOpError` in 1.0.0; PACT-gated post-1.0.
13. Extras naming — hyphens across all specs (`[rl-offline]`, `[autolog-lightning]`, `[feature-store]`).
14. Package version at merge — kailash-ml 1.0.0 MAJOR (breaking-change list in spec body).

## 1.0.0 Wave Release (7 packages atomic)

- `kailash 2.9.0` (ml extras alias) + `kailash-pact 0.10.0` (ml_context + ClearanceRequirement) + `kailash-nexus 2.2.0` (ml-endpoints mount) + `kailash-kaizen 2.12.0` (§2.4 Agent Tool Discovery + SQLiteSink) + `kailash-align 0.6.0` (ml-unification + rl_bridge) + `kailash-dataflow 2.1.0` (TrainingContext + lineage_dataset_hash) + `kailash-ml 1.0.0`.

**M1 release-wave patterns** — see [m1-release-wave](m1-release-wave.md) for:

- Canonical 48-symbol `__all__` (41 §15.9 + erase_subject + 7 Phase-1 adapters)
- km.train + km.register canonical async-await pipeline (commit `fdd3040e`)
- TrainingResult.trainable back-reference (commit `15033fa6`)
- Release-blocking README Quick Start regression (SHA-256 fingerprint end-to-end)
- MIGRATION.md sunset contract (W33b)
- 7 integration surfaces (kailash.ml / kailash.observability.ml / dataflow.ml / nexus.ml / kaizen.ml / align.ml / pact.ml)
- 8 institutional patterns from session 2026-04-23

---

**Legacy v0.x material below retained as internal-implementation reference only. The canonical user surface is the engine-first `km.*` verbs above; the spec files under `specs/ml-*.md` are the authority.**

## Install Matrix

```
pip install kailash-ml            # Core: polars, numpy, scipy, sklearn, lightgbm, xgboost, plotly, onnx
pip install kailash-ml[dl]        # + PyTorch, Lightning, transformers, timm
pip install kailash-ml[dl-gpu]    # + onnxruntime-gpu
pip install kailash-ml[rl]        # + Stable-Baselines3, Gymnasium
pip install kailash-ml[agents]    # + kailash-kaizen (agent integration)
# NOTE: [xgb] is a no-op alias — xgboost is now a base dep (xgboost>=2.0 ships
# with CUDA built in and auto-detects GPU at runtime, CPU fallback otherwise).
pip install kailash-ml[catboost]  # + CatBoost
pip install kailash-ml[explain]   # + SHAP (model explainability)
pip install kailash-ml[imbalance] # + imbalanced-learn (SMOTE, ADASYN)
pip install kailash-ml[stats]     # + statsmodels
pip install kailash-ml[full]      # Everything (CPU)
pip install kailash-ml[all-gpu]   # Everything (GPU)
```

## 13 Engines (by Priority)

| #   | Engine                | Priority | Purpose                                                            | Key Dependency                     |
| --- | --------------------- | -------- | ------------------------------------------------------------------ | ---------------------------------- |
| 1   | FeatureStore          | P0       | Polars-native feature versioning, point-in-time queries            | ConnectionManager                  |
| 2   | ModelRegistry         | P0       | Model versioning (staging/shadow/production/archived), ONNX export | ConnectionManager, ArtifactStore   |
| 3   | TrainingPipeline      | P0       | sklearn/LightGBM/Lightning training with FeatureSchema             | FeatureStore, ModelRegistry        |
| 4   | InferenceServer       | P0       | REST serving via kailash-nexus, response caching, batch            | ModelRegistry, kailash-nexus       |
| 5   | DriftMonitor          | P0       | KS/chi2/PSI/Jensen-Shannon drift detection, scheduled checks       | ConnectionManager                  |
| 6   | ExperimentTracker     | P0       | MLflow-compatible run tracking, metric comparison, audit           | ConnectionManager                  |
| 7   | HyperparameterSearch  | P1       | Grid/random/Bayesian/successive halving optimization               | TrainingPipeline                   |
| 8   | AutoMLEngine          | P1       | Multi-family model search, optional agent augmentation             | HyperparameterSearch, FeatureStore |
| 9   | EnsembleEngine        | P1       | Blend/stack/bag/boost ensemble creation                            | TrainingPipeline                   |
| 10  | PreprocessingPipeline | P1       | Auto-setup from FeatureSchema, imputation, encoding                | FeatureSchema                      |
| 11  | DataExplorer          | P2       | Statistical profiling, plotly visualization, comparison            | polars, plotly                     |
| 12  | FeatureEngineer       | P2       | Auto-generation, selection, importance ranking                     | polars                             |
| 13  | ModelExplainer        | P2       | SHAP-based global/local/dependence explanations                    | SHAP (requires [explain])          |

**Additional modules**: OnnxBridge, MlflowFormatReader/Writer, MLDashboard (all lazy-loaded).

## Quick Start

### Feature Ingestion

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore
from kailash_ml.types import FeatureSchema, FeatureField
import polars as pl

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
    ],
    target=FeatureField(name="churned", dtype="int"),
)

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()

df = pl.read_csv("data.csv")
await fs.ingest("user_features", schema, df)

# Point-in-time retrieval
features = await fs.get_features("user_features", entity_ids=["u1", "u2"])
```

### Training

```python
from kailash_ml import TrainingPipeline, ModelRegistry, ModelSpec, EvalSpec
from kailash_ml.engines import LocalFileArtifactStore

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

pipeline = TrainingPipeline(feature_store=fs, model_registry=registry)
result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)
```

### Drift Monitoring

```python
from kailash_ml import DriftMonitor

# W26.e: tenant_id is REQUIRED at construction. One monitor per tenant.
monitor = DriftMonitor(conn, tenant_id="acme")
await monitor.initialize()
await monitor.set_reference("model_v1", reference_df)
report = await monitor.check_drift("model_v1", current_df)
# report.overall_drift, report.feature_results, report.recommendations
```

### Model Explainability (requires `[explain]`)

```python
from kailash_ml import ModelExplainer

explainer = ModelExplainer(model=fitted_model, X=train_df, feature_names=schema.feature_names)
global_report = explainer.explain_global(max_display=10)
local_report = explainer.explain_local(X=test_df, index=0)
fig = explainer.to_plotly("summary")  # "summary", "beeswarm", "dependence"
```

### AutoML with Agent Augmentation

```python
from kailash_ml import AutoMLEngine
from kailash_ml.engines.automl_engine import AutoMLConfig

config = AutoMLConfig(
    task_type="classification",
    metric_to_optimize="f1",
    search_strategy="bayesian",
    search_n_trials=50,
    agent=True,            # LLM augmentation (requires kailash-ml[agents])
    auto_approve=False,    # Human approval gate
    max_llm_cost_usd=5.0,
)
engine = AutoMLEngine(feature_store=fs, model_registry=registry, config=config)
result = await engine.run(schema=schema, data=df)
```

### Model Registry Lifecycle

```python
# Stage transitions: staging → shadow → production → archived
await registry.promote("model_v1", version_id, target_stage="production")

# Valid transitions:
# staging    → shadow, production, archived
# shadow     → production, archived, staging
# production → archived, shadow
# archived   → staging
```

### Preprocessing Pipeline

```python
from kailash_ml.engines import PreprocessingPipeline

pipeline = PreprocessingPipeline()
result = pipeline.setup(
    data=df, target="churned",
    normalize=True, normalize_method="zscore",       # zscore, minmax, robust, maxabs
    imputation="knn", impute_n_neighbors=5,           # knn, iterative, default
    remove_multicollinearity=True, multicollinearity_threshold=0.9,
    fix_imbalance=True, imbalance_method="smote",     # smote, adasyn ([imbalance])
)
```

### Nested Runs & Auto-Logging

```python
from kailash_ml import ExperimentTracker

tracker = ExperimentTracker(conn)
await tracker.initialize()

async with tracker.run("hyperopt-sweep") as parent:
    for params in param_grid:
        async with tracker.run("trial", parent_run_id=parent.run_id) as child:
            await child.log_params(params)
```

## Decision Tree: kailash-ml vs kailash-align vs kailash-kaizen

| You Want To...                        | Use                                                 |
| ------------------------------------- | --------------------------------------------------- |
| Train sklearn/LightGBM/XGBoost models | **kailash-ml**                                      |
| Manage feature pipelines              | **kailash-ml**                                      |
| Monitor model drift                   | **kailash-ml**                                      |
| Export models to ONNX                 | **kailash-ml**                                      |
| Fine-tune an LLM (LoRA, DPO, RLHF)    | **kailash-align**                                   |
| Serve a fine-tuned LLM via Ollama     | **kailash-align**                                   |
| Build an AI agent with tools          | **kailash-kaizen**                                  |
| Add agent intelligence to ML engines  | **kailash-ml[agents]** (uses Kaizen under the hood) |
| Train RL policies (Gymnasium)         | **kailash-ml[rl]**                                  |

## Polars-Native Rule (ABSOLUTE)

Every engine accepts and returns `polars.DataFrame`. Conversion to numpy/pandas/LightGBM Dataset happens ONLY in `interop.py` at sklearn/framework boundaries.

```python
# DO: Work in polars throughout
df = pl.read_csv("data.csv")
await fs.ingest("features", schema, df)

# DO NOT: Convert to pandas first
df_pd = pd.read_csv("data.csv")  # WRONG — polars is the native format
```

## Interop Conversion Table

All conversions live in `interop.py`. Import from there only.

| Function                   | From             | To                                   | Use When                    |
| -------------------------- | ---------------- | ------------------------------------ | --------------------------- |
| `to_sklearn_input()`       | polars DataFrame | (X: ndarray, y: ndarray, info: dict) | Training with sklearn       |
| `from_sklearn_output()`    | ndarray          | polars DataFrame                     | Converting predictions back |
| `to_lgb_dataset()`         | polars DataFrame | lightgbm.Dataset                     | Training with LightGBM      |
| `to_hf_dataset()`          | polars DataFrame | datasets.Dataset                     | HuggingFace integration     |
| `polars_to_arrow()`        | polars DataFrame | pyarrow.Table                        | Arrow IPC / Parquet         |
| `from_arrow()`             | pyarrow.Table    | polars DataFrame                     | Ingesting Arrow data        |
| `to_pandas()`              | polars DataFrame | pandas.DataFrame                     | Legacy pandas interop       |
| `from_pandas()`            | pandas.DataFrame | polars DataFrame                     | Ingesting pandas data       |
| `polars_to_dict_records()` | polars DataFrame | list[dict]                           | JSON serialization          |
| `dict_records_to_polars()` | list[dict]       | polars DataFrame                     | JSON deserialization        |

## Architecture

```
kailash-ml/
  engines/
    _shared.py              ← Numeric dtypes, model class validation
    _feature_sql.py         ← ALL raw SQL (zero SQL in engine files)
    _guardrails.py          ← AgentGuardrailMixin (5 mandatory guardrails)
    feature_store.py        ← FeatureStore (ConnectionManager, polars-native)
    model_registry.py       ← ModelRegistry (lifecycle, SHA256 integrity)
    training_pipeline.py    ← TrainingPipeline (schema-driven)
    inference_server.py     ← InferenceServer (Nexus, ONNX, caching)
    drift_monitor.py        ← DriftMonitor (KS/chi2/PSI/JS)
    model_explainer.py      ← ModelExplainer (SHAP, [explain])
    experiment_tracker.py   ← MLflow-compatible tracking (nested runs)
    hyperparameter_search.py ← Grid/random/bayesian/successive halving
    automl_engine.py        ← Agent-infused AutoML
    ensemble.py             ← Blend/stack/bag/boost
    preprocessing.py        ← Auto-setup from FeatureSchema
  agents/                   ← 6 Kaizen agents ([agents])
    tools.py                ← Dumb data endpoints (LLM-first)
  rl/                       ← RLTrainer, EnvironmentRegistry, PolicyRegistry
  interop.py                ← SOLE conversion point
  bridge/                   ← OnnxBridge (export + verification)
```

### Internal Module Guide

| Module            | Purpose                                                                                   | When to Touch                          |
| ----------------- | ----------------------------------------------------------------------------------------- | -------------------------------------- |
| `_shared.py`      | NUMERIC_DTYPES, ALLOWED_MODEL_PREFIXES, validate_model_class(), compute_metrics_by_name() | Adding new model frameworks or metrics |
| `_feature_sql.py` | ALL raw SQL for FeatureStore (zero SQL elsewhere)                                         | Any FeatureStore schema/query change   |
| `_guardrails.py`  | AgentGuardrailMixin (cost budget, audit trail, approval gate)                             | Adding agent integration to any engine |
| `interop.py`      | SOLE conversion point: polars ↔ sklearn/lgb/arrow/pandas/hf                               | Adding new framework interop           |

## 6 ML Agents (kailash-ml[agents])

Agents require both `agent=True` AND the agents extra installed. All follow LLM-first rule.

| Agent                      | Purpose                        |
| -------------------------- | ------------------------------ |
| DataScientistAgent         | Data profiling recommendations |
| FeatureEngineerAgent       | Feature generation guidance    |
| ModelSelectorAgent         | Model selection reasoning      |
| ExperimentInterpreterAgent | Trial result analysis          |
| DriftAnalystAgent          | Drift report interpretation    |
| RetrainingDecisionAgent    | Retrain/rollback decisions     |

See [ml-agent-guardrails](ml-agent-guardrails.md) for the 5 mandatory guardrails.

## RL Module (kailash-ml[rl])

```python
from kailash_ml.rl import RLTrainer, EnvironmentRegistry, PolicyRegistry

env_reg = EnvironmentRegistry()
env_reg.register("CartPole-v1")

trainer = RLTrainer(env_registry=env_reg, policy_registry=PolicyRegistry())
result = await trainer.train(env_id="CartPole-v1", algorithm="PPO", total_timesteps=100_000)
```

## Security Checklist

When writing or reviewing kailash-ml engine code, verify:

- [ ] **SQL identifiers**: All interpolated identifiers pass through `_validate_identifier()` (from `kailash.db.dialect`)
- [ ] **SQL types**: Column types validated via `_validate_sql_type()` allowlist (INTEGER, REAL, TEXT, BLOB, NUMERIC)
- [ ] **SQL placement**: Zero raw SQL outside `_feature_sql.py` — all queries go through that module
- [ ] **Model classes**: Dynamic model imports validated via `validate_model_class()` against ALLOWED_MODEL_PREFIXES (`sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.`)
- [ ] **Financial fields**: `math.isfinite()` on all cost/budget fields (NaN/Inf bypass comparisons)
- [ ] **Table prefix**: Regex-validated in constructor (`^[a-zA-Z_][a-zA-Z0-9_]*$`)
- [ ] **Bounded collections**: Audit trails, cost logs, trial history use `deque(maxlen=N)`
- [ ] **Agent guardrails**: Engines with agent integration inherit `AgentGuardrailMixin` (cost budget + approval gate)
- [ ] **Interop boundary**: Conversions happen ONLY in `interop.py`, nowhere else

## Skill Files

- [ml-feature-pipelines](ml-feature-pipelines.md) — FeatureStore, polars-only engineering, schema-driven ingestion
- [ml-model-registry](ml-model-registry.md) — ModelRegistry CRUD, lifecycle stages, MLflow compatibility
- [ml-training-pipeline](ml-training-pipeline.md) — TrainingPipeline, hyperparameter search, experiment tracking
- [ml-inference-server](ml-inference-server.md) — InferenceServer, Nexus exposure, ONNX serving, batch inference
- [ml-agent-guardrails](ml-agent-guardrails.md) — 5 mandatory guardrails, AutoML, agent integration
- [ml-onnx-export](ml-onnx-export.md) — PyTorch/sklearn to ONNX, verification, cross-language serving
- [ml-drift-monitoring](ml-drift-monitoring.md) — DriftMonitor, statistical tests, alert thresholds, retraining triggers

## Critical Rules

- All engines are polars-native — no pandas/numpy in pipeline code
- sklearn interop only at boundary via `interop.py`
- FeatureStore uses ConnectionManager, not Express (needs window functions)
- Zero raw SQL outside `_feature_sql.py`
- Agent-augmented engines require double opt-in (`agent=True` + extras installed)
- All agents follow LLM-first rule — tools are dumb data endpoints

## Related Skills

- [01-core-sdk](../01-core-sdk/SKILL.md) — Core workflow patterns
- [02-dataflow](../02-dataflow/SKILL.md) — Database integration (ConnectionManager)
- [03-nexus](../03-nexus/SKILL.md) — Multi-channel deployment (InferenceServer)
- [04-kaizen](../04-kaizen/SKILL.md) — AI agent framework (ML agents)
- [35-kailash-align](../35-kailash-align/SKILL.md) — LLM fine-tuning and alignment
  </content>
  </invoke>
