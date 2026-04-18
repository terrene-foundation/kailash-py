# kailash-ml — Architecture Assessment

**Scope.** Product-level audit of `packages/kailash-ml/` against the stated vision: Lightning-core, GPU-first, single-Engine, unified ML/DL/RL, MLflow/PyCaret replacement. Ground-truth sources cited by absolute path. No source edits.

**Verdict.** The user's read is correct. `kailash-ml` today is a **library of 18 loosely-federated primitive engines**, not a product. There is no top-level `Engine`. Lightning is present only as a `framework="lightning"` string in `TrainingPipeline._train_lightning`. GPU auto-detection exists for XGBoost inside `AutoMLEngine` only — LightGBM, Lightning, sklearn, and inference all run CPU-only. The 13-engine count in `.claude/skills/34-kailash-ml/SKILL.md:28` is already stale: the package ships 18 engines.

---

## 1. Engine surface audit

The package exposes **18 top-level engine/support classes** via lazy-load in `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/__init__.py:29-58`. None of them compose through a common parent. Each has its own input/output contract and its own construction ceremony.

| Engine (class) | LOC | Constructor dependencies | Primary entry method | In/out contract |
|---|---|---|---|---|
| `FeatureStore` | 440 | `ConnectionManager`, `table_prefix` | `ingest / get_features` | `pl.DataFrame` in, `pl.DataFrame` out |
| `ModelRegistry` | 920 | `ConnectionManager`, `ArtifactStore` | `register_model / load_model` | bytes artifact + `FeatureSchema` |
| `TrainingPipeline` | 757 | `feature_store`, `registry` | `train(data, schema, model_spec, eval_spec, experiment_name)` | `pl.DataFrame` in, `TrainingResult` out |
| `InferenceServer` | 630 | `registry` | `predict / predict_batch` | `pl.DataFrame` in, `PredictionResult` out |
| `DriftMonitor` | 894 | `ConnectionManager` | `set_reference_data / check_drift` | `pl.DataFrame`, `DriftReport` |
| `ExperimentTracker` | 1316 | `ConnectionManager` or `.create(url)` | `run(exp, run_name) / log_*` | MLflow-shaped rows |
| `HyperparameterSearch` | 808 | `pipeline` | `search(data, schema, space, config, ...)` | `SearchResult` |
| `AutoMLEngine` | 716 | `pipeline`, `search`, `registry?` | `run(data, schema, config, eval_spec, experiment_name)` | `AutoMLResult` |
| `EnsembleEngine` | 611 | `pipeline` | `blend / stack / bag / boost` | 4 result types |
| `PreprocessingPipeline` | 1307 | none (stateful) | `setup(data, target) / transform` | `pl.DataFrame`, `SetupResult` |
| `DataExplorer` | 1042 | `AlertConfig?` | `profile / visualize / to_html / compare` | `DataProfile` |
| `FeatureEngineer` | 461 | none | generate/select/rank | mixed |
| `ModelExplainer` | 468 | `model`, `X`, `feature_names` | `explain_global / explain_local / explain_dependence` | dict, `plotly.Figure` |
| `ModelVisualizer` | 745 | none | `histogram / scatter / confusion_matrix / roc_curve` | `plotly.Figure` |
| `ClusteringEngine` | 419 | none | `fit(data, algorithm, k)` | `ClusterResult` |
| `AnomalyDetectionEngine` | 488 | none | `detect` | `AnomalyResult` |
| `DimReductionEngine` | 406 | none | `reduce` | `DimReductionResult` |
| `RLTrainer` | 275 | `env_registry`, `policy_registry` | `train(env_id, algorithm, total_timesteps)` | `RLTrainingResult` |

**Composition reality.** There is no `Engine` class and no `Engine` protocol. The "workflow" a user must type is:

```python
# 6-object ceremony to get one trained model (distilled from SKILL.md + source)
conn = ConnectionManager("sqlite:///ml.db"); await conn.initialize()
fs = FeatureStore(conn, table_prefix="kml_"); await fs.initialize()
registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts")); await registry.initialize()
pipeline = TrainingPipeline(feature_store=fs, registry=registry)
tracker = await ExperimentTracker.create("sqlite:///ml.db")  # optional, different URL form
result = await pipeline.train(data, schema, ModelSpec("sklearn.ensemble.RandomForestClassifier"),
                              EvalSpec(metrics=["accuracy"]), experiment_name="run1", tracker=tracker)
```

This is the "disjointed" symptom. Six constructors, two initialization protocols (`await x.initialize()` vs `await X.create(url)` vs zero-init), two URL conventions, and the user hand-wires a `FeatureSchema` + `ModelSpec` + `EvalSpec` per call. Zero of the 18 engines inherit from a common base. No engine has a `fit(data, target=...)` method.

---

## 2. Lightning integration assessment

**Present but vestigial.** Lightning appears only as:

- `training_pipeline.py:255` — `if model_spec.framework == "lightning":` branch
- `training_pipeline.py:525-594` — `_train_lightning()`: dynamically imports `lightning as L`, wraps numpy tensors in a `TensorDataset`, constructs `L.Trainer(**trainer_kwargs)`, calls `trainer.fit(module, dataloader)`, returns the `LightningModule`.
- `training_pipeline.py:623` — `_predict_lightning()` for inference.

That is the entire integration. There is:

- **No `LightningDataModule`** — every call reconstructs a `TensorDataset` from numpy tensors from `to_sklearn_input()` (`interop.py:44`). For large/streaming data this OOMs.
- **No persistent `Trainer`** — `L.Trainer` is constructed per call with hardcoded `max_epochs=10`, `enable_progress_bar=False`. No callbacks, no strategies, no `accelerator`/`devices`.
- **No Kailash `LightningModule` base class** — users must supply a fully-qualified path like `"lightning.pytorch.demos.boring_classes.BoringModel"` (`training_pipeline.py:538`). No scaffold for common supervised tasks.
- **No DL engine** in the 18-engine surface. Lightning is a string flag, not a peer to `TrainingPipeline`.
- **Classical ML does not share the Lightning contract.** `_train_sklearn` and `_train_lightgbm` are parallel private methods with no common trainer abstraction.

**What Lightning should replace/wrap.** If Lightning becomes the spine:
- `TrainingPipeline._train_*` → single `Trainer.fit(module, datamodule)` dispatch, with `SklearnLightningModule` / `LightGBMLightningModule` wrappers for classical models.
- `HyperparameterSearch._*_search` → Lightning's `Tuner` + callbacks (`EarlyStopping`, `ModelCheckpoint`), driven by Optuna.
- `EnsembleEngine.bag / boost` → Lightning loops with `MultiOptimizer`.
- `InferenceServer._CachedModel` → `Trainer.predict` with `TorchScript` / ONNX export.
- `DriftMonitor` drift checks → Lightning `Callback` hook, not an out-of-band scheduler.
- `RLTrainer` → Stable-Baselines3 already wraps torch; could emit Lightning-compatible metrics without rewriting SB3.

---

## 3. GPU-first gap analysis

**Status today: CPU by default, one exception.**

| Path | GPU aware? | Evidence |
|---|---|---|
| XGBoost (AutoMLEngine only) | Yes | `automl_engine.py:292-307` `_select_xgboost_device()` probes `nvidia-smi`, returns `"cuda"` or `"cpu"`, logs `automl.xgboost_backend_selected`. Only wired into the default candidate lists at L317/354 — a user calling `TrainingPipeline.train(..., ModelSpec("xgboost.XGBClassifier"))` directly gets no device injection. |
| LightGBM | **No** | `training_pipeline.py:501-523` never touches `device` or `gpu_platform_id`. |
| PyTorch / Lightning | **No** | `training_pipeline.py:591` `L.Trainer(**trainer_kwargs)` — no default `accelerator="auto"`, no `devices="auto"`. User must supply `trainer_accelerator` hyperparameter. |
| sklearn | N/A | sklearn is CPU-only — but the `_CUDA_INDEX_MAP` in `_gpu_setup.py:20` implies the project wants GPU paths for everything it reaches. |
| InferenceServer | **No** | 630 LOC, zero mention of `device`, `cuda`, `onnxruntime-gpu`. The `[dl-gpu]` extra installs `onnxruntime-gpu` (`pyproject.toml:63`) but nothing in `inference_server.py` selects the CUDA execution provider. |
| RL | Partial | Stable-Baselines3 auto-detects torch's device; `rl/trainer.py` does not force CPU but also does not expose `device` as a config field. |
| `kailash-ml-gpu-setup` CLI | Yes (advisory) | `_gpu_setup.py:132` prints an install command with `--extra-index-url`. This is a **doc-generation tool**, not a runtime check — nothing in the package consumes `detect_cuda_version()` at import or train time. |

**What GPU-first means to deliver.**

1. A single `device_manager.py` module that: (a) probes CUDA + MPS + CPU at import, (b) exposes `get_accelerator()` returning `{"auto", "cuda", "mps", "cpu"}`, (c) memoizes for the process.
2. Default injection:
   - LightGBM → `device="gpu"` when CUDA present (and built with GPU support — probe at import).
   - XGBoost → `device="cuda"` + `tree_method="hist"` (already implemented, should be lifted out of `automl_engine.py` into the shared detector).
   - Lightning `Trainer` → `accelerator="auto", devices="auto"` by default.
   - InferenceServer → `onnxruntime.InferenceSession(providers=["CUDAExecutionProvider","CPUExecutionProvider"])`.
3. `pip install kailash-ml` detects CUDA at install time (PEP 517 hook or post-install hint) OR defers to runtime detection — today it does neither.
4. Observability: every device selection MUST emit an INFO log (pattern already in `automl_engine.py:303`) — extend to every engine.

---

## 4. ML / DL / RL unification analysis

**Today: three disjoint worlds.**

- **Classical ML** → `TrainingPipeline.train(model_spec, eval_spec, ...)` with `framework ∈ {"sklearn","lightgbm","lightning"}`. Returns `TrainingResult` with a `ModelVersion` registered to `ModelRegistry`.
- **Deep Learning** → string `framework="lightning"` inside the same pipeline; model_class points at an arbitrary `LightningModule`. Artifacts pickled, not TorchScript/ONNX.
- **RL** → `RLTrainer.train(env_id, algorithm, total_timesteps)` in `rl/trainer.py`, returns `RLTrainingResult`. **Does not touch `ModelRegistry`, `ExperimentTracker`, or `TrainingPipeline`.** Parallel universe.

Evidence: `rl/__init__.py` exports `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry` — zero overlap with the top-level `__init__.py` engine map.

**What unification looks like.**

The shared protocol should be a `Trainable` contract, not "everything inherits from `LightningModule`". Three cuts:

1. `Trainable` protocol — `fit(data) -> FittedArtifact`, `predict(X) -> Output`, `signature() -> ModelSignature`. sklearn wrappers, LightGBM wrappers, Lightning modules, and SB3 policies all satisfy this.
2. Unified `Trainer` (Lightning-driven) — accepts any `Trainable`, handles device placement, experiment tracking, checkpointing, and registry registration uniformly. Classical models use a `SklearnWrapper(LightningModule)` that runs one epoch of `.fit()` and logs metrics.
3. `TrainingPipeline` becomes a thin orchestrator over `Trainer`, not a switch on framework strings. RL joins by exposing SB3 policies through a `RLPolicyTrainable` wrapper.

This is a larger change than the user's current "no engine workflow" complaint but is the structural fix. Without it, the user pays the seam tax (three code paths, three registries, three experiment shapes) on every session.

---

## 5. MLflow feature parity matrix

MLflow has five product surfaces: Tracking, Projects, Models (packaging), Registry, UI. Plus Evaluate, Serving, Lineage.

| MLflow feature | Kailash state | Evidence | "Beats MLflow" means |
|---|---|---|---|
| Experiment tracking (runs, metrics, params, artifacts) | **Have** | `experiment_tracker.py:388` — full CRUD, nested runs, compare, history, search. MLflow-compatible run shape (`Run`, `MetricEntry`). | Native polars dataframes in results; zero-config single-file SQLite backend; native async. |
| Projects (MLproject.yaml + conda/docker env spec) | **Missing** | No reproducible-run concept. | Replace with DataFlow-backed workflow manifests. |
| Models (pyfunc, flavors, signatures) | **Partial** | `types.py:ModelSignature`, `ModelRegistry.register_model` with artifact bytes + signature. No flavor plugin system — everything is pickled. | Lightning checkpoint + ONNX + GGUF as first-class flavors. |
| Model Registry (stages, aliases, tags) | **Have** | `model_registry.py:398` — `staging/shadow/production/archived` lifecycle, comparison. | Shadow-traffic routing built in (InferenceServer); MLflow leaves this to the user. |
| UI (web dashboard) | **Partial** | `dashboard/` module exists (`__init__.py:55`). Starlette-based. | Needs parity audit vs MLflow UI. |
| `mlflow.evaluate` | **Missing** | `TrainingPipeline.evaluate` computes metrics but no standardized evaluation artifact (no residual plots, SHAP pack, fairness metrics). | Out-of-the-box evaluation bundle: metrics + SHAP + calibration + drift baseline in one call. |
| Serving (`mlflow models serve`) | **Have (partial)** | `inference_server.py:127` via kailash-nexus. No `--port` CLI. | Nexus deployment path is the "beats" story — same artifact serves REST + CLI + MCP. |
| Lineage (data → model → deployment) | **Missing** | No link between `FeatureStore` snapshots and `ModelRegistry` versions. | A `ModelVersion.dataset_snapshot_id` FK into FeatureStore — instant lineage. |
| `mlflow.autolog()` | **Partial** | `TrainingPipeline` auto-logs when a tracker is passed (L302-314), but user must construct + pass the tracker. | True zero-config autolog: `engine.enable_tracking()` activates once per process. |
| MLflow-format import/export | **Have** | `compat/mlflow_format.py` — `MlflowFormatReader / Writer`. | One-command migration: `kailash-ml import-mlflow /path/to/mlruns`. |

**Bottom line.** Kailash has ~65% of MLflow's tracking/registry surface and approximately 0% of Projects/Evaluate/Lineage. The "beats" story lives in (a) polars-native throughout, (b) async-native, (c) Nexus deployment unification. These require a single Engine to surface; today they are spread across 5 engines and the user must wire them.

---

## 6. PyCaret feature parity matrix

PyCaret's contract is `setup → compare_models → tune_model → finalize_model → deploy_model`. One session, one DataFrame, zero config files.

| PyCaret feature | Kailash state | Evidence | "Beats PyCaret" means |
|---|---|---|---|
| `setup(data, target=)` (auto preprocessing, CV split, imbalance fix) | **Partial — primitive-level** | `preprocessing.py:150` `PreprocessingPipeline.setup(data, target, normalize=, imputation=, fix_imbalance=)`. Does not create a session object, does not auto-select CV, does not publish to any engine. | `engine.setup(data, target="y")` returns a session usable by `compare_models`, `fit`, `explain`. |
| `compare_models()` (N-model bakeoff with leaderboard) | **Partial** | `AutoMLEngine.run` does a bakeoff (`automl_engine.py:524`) but returns `AutoMLResult`, not a ranked leaderboard DataFrame. | A `polars.DataFrame` leaderboard with one row per model × CV fold, sortable, exportable. |
| `create_model(estimator)` | **Have** | `TrainingPipeline.train(data, schema, ModelSpec(...))`. Verbose; requires schema construction. | `engine.fit("xgboost")` shorthand. |
| `tune_model(model)` | **Have** | `HyperparameterSearch.search(...)`. Requires user to build `SearchSpace`. | Auto-spaces per model family. |
| `interpret_model(model)` | **Have** | `ModelExplainer.explain_global / local / dependence` (`model_explainer.py:67`). Requires `[explain]` extra. | Same API, always available (SHAP as base dep for classical models). |
| `ensemble_model` (bagging/boosting) | **Have** | `EnsembleEngine.bag / boost`. | Wire into the Engine's leaderboard. |
| `blend_models / stack_models` | **Have** | `EnsembleEngine.blend / stack`. | Same. |
| `save_model / load_model` | **Have** | `ModelRegistry.register_model / load_model`. | Same. |
| `deploy_model` | **Partial** | `InferenceServer.predict` + Nexus. No "one-line deploy to staging/prod." | `engine.deploy(model_version, stage="production")`. |
| `create_api / create_docker` | **Partial** | Nexus handles API; no docker recipe. | `engine.serve(port=8000)` boots REST + MCP. |
| Time-series support | **Missing** | No time-series CV splitter, no forecasting models. | Would require a `ForecastingEngine` or extension to `TrainingPipeline.eval_spec.split_strategy`. |
| Anomaly detection | **Have** | `AnomalyDetectionEngine.detect`. | Fold into Engine surface. |
| Clustering | **Have** | `ClusteringEngine.fit`. | Same. |
| NLP | **Missing** | No tokenizer / embedding integration. | Out of scope, or handoff to `kailash-align`. |

**Bottom line.** Kailash has ~80% of PyCaret's primitives but none of the DX: no one-line setup, no one-line compare, no session object that carries state between calls. Every PyCaret one-liner is currently a five-line Kailash ceremony.

---

## 7. Engine-workflow proposal

### One-liner

```python
from kailash_ml import Engine
model = Engine.fit(df, target="revenue")   # auto preprocess, auto bakeoff, auto tune, returns best ModelVersion
```

### Five-liner (configured but still readable)

```python
from kailash_ml import Engine
engine = Engine(store="sqlite:///ml.db", accelerator="auto")  # one URL, one device policy
engine.setup(df, target="revenue", ignore=["customer_id"])     # preprocessing session
leaderboard = engine.compare(families=["xgb","lgbm","torch"], n_trials=30)  # bakeoff + HPO
model = engine.finalize(leaderboard.top())                                    # register to production
endpoint = engine.serve(model, channels=["rest","mcp"])                       # Nexus deployment
```

Four behaviours this implies:

1. **`Engine` is a facade over the 18 current primitives.** Each primitive stays importable (`from kailash_ml import FeatureStore`) for power users. The Engine is the default path.
2. **One store URL.** `Engine(store=...)` constructs `ConnectionManager`, `FeatureStore`, `ModelRegistry`, `ExperimentTracker`, `DriftMonitor` against the same backend. Today each needs its own `await x.initialize()`.
3. **Session object.** `engine.setup()` returns nothing user-facing, but internally holds `(data, schema, preprocessing_fit, target)`. Subsequent calls (`compare`, `fit`, `explain`) read from session.
4. **Leaderboard as polars DataFrame.** `engine.compare()` returns a `pl.DataFrame` that sorts, filters, renders in notebooks, and has a `.top(k)` / `.select(family="xgb")` convenience.

---

## 8. 13-engine rationalization

The skill says 13; the code exports 18 engines. The right number is **5 user-facing engines** plus primitives.

| Proposed surface | Rolls up today's classes | Rationale |
|---|---|---|
| `Engine` | orchestrates all others | The missing single-entrypoint |
| `FeatureStore` | `FeatureStore` | Only engine that owns persisted features; distinct concern from training |
| `ModelRegistry` | `ModelRegistry` + `ModelVersion` lifecycle | Distinct concern from training; artifacts survive the Engine process |
| `ExperimentTracker` | `ExperimentTracker` + `Run` + `RunContext` | Distinct concern; MLflow replacement story |
| `InferenceServer` | `InferenceServer` + `OnnxBridge` | Distinct concern; Nexus deployment surface |

**Merge / demote into `Engine`:**

| Current engine | Disposition |
|---|---|
| `TrainingPipeline` | Private — `Engine._trainer`. No user constructs it directly. |
| `HyperparameterSearch` | Private — called via `Engine.tune()` / auto inside `Engine.compare()`. |
| `AutoMLEngine` | **Merge into `Engine`.** `Engine.compare()` + `Engine.fit()` ARE AutoML. Delete the class. |
| `EnsembleEngine` | Private — `Engine.ensemble(models, method="stack")`. |
| `PreprocessingPipeline` | Private — `Engine.setup()`. The 1307-LOC file is a smell (longest in the package). |
| `DriftMonitor` | Keep as a peer of `InferenceServer` OR surface as `Engine.monitor(model)`. Currently an orphan — a drift report has no link back to the model that produced it except by naming convention. |
| `DataExplorer` | Fold into `Engine.setup()` — setup should return a profile. Standalone use cases keep the class. |
| `FeatureEngineer` | Fold into `Engine.setup()` — auto-generation happens during setup. |
| `ModelExplainer` | `Engine.explain(model)`. Class stays for power users. |
| `ModelVisualizer` | Fold into `Engine.explain()` / `Engine.setup()` reports. Experimental status per source — appropriate to keep as internal utility. |
| `ClusteringEngine`, `AnomalyDetectionEngine`, `DimReductionEngine` | Three parallel 400–500 LOC files for **unsupervised tasks**. Merge into `UnsupervisedEngine` (one engine, `.cluster()`, `.detect_anomalies()`, `.reduce()`). Or surface via `Engine.fit(task="cluster", data=df, k=5)`. |
| `RLTrainer` + `rl/*` | Keep as `rl.Engine` (sibling facade) with same `fit/deploy` shape. Reuses ModelRegistry + ExperimentTracker. |

Net count: **5 user-facing engines** (Engine, FeatureStore, ModelRegistry, ExperimentTracker, InferenceServer) + 1 sibling (rl.Engine) + 1 observability peer (DriftMonitor). Everything else is a primitive.

---

## Top 3 architectural changes that must land

1. **Introduce a single `Engine` facade** (`src/kailash_ml/engine.py`) with `setup / compare / fit / tune / finalize / explain / serve / monitor`, backed by one `store=` URL that constructs all the plumbing. This is the "no engine workflow" fix and costs nothing at the primitive layer — keep all 18 exports.

2. **Promote Lightning from a `framework="lightning"` string to the training spine.** Introduce a `Trainable` protocol, wrap sklearn / LGBM / XGBoost / torch / SB3 behind `LightningModule` adapters, and route every training call through a single `Trainer` with `accelerator="auto"`. This fixes ML/DL/RL disunity AND GPU-first in one stroke.

3. **Centralize device selection** (`src/kailash_ml/_device.py`) and inject it everywhere. Today `_select_xgboost_device()` exists only in `automl_engine.py:292` — LightGBM, Lightning, InferenceServer, and direct-train XGBoost all ignore GPU. Move the detector to `_device.py`, emit `device.selected` INFO per engine, default `accelerator="auto"` in Lightning `Trainer`, `device="gpu"` in LightGBM, `CUDAExecutionProvider` in ONNX Runtime.

---

## File paths relevant to this assessment

- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/__init__.py` — lazy-load map (18 exports)
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/engines/` — all 18 engines + 4 `_*.py` internals
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py:180,255,501,525,591` — training dispatch, Lightning stub, GPU blind spot
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/engines/automl_engine.py:292-307,317,354` — the only GPU detector in the package
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/engines/inference_server.py` — zero GPU awareness in 630 LOC
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/_gpu_setup.py` — CLI doc-tool, not runtime
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/rl/trainer.py` — orphaned RL world
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/src/kailash_ml/interop.py` — sole polars↔numpy conversion boundary
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-align/src/kailash_align/pipeline.py:46-138` — cleaner sibling pattern to learn from (MethodRegistry dispatch vs string switch)
- `/Users/esperie/repos/loom/kailash-py/.claude/skills/34-kailash-ml/SKILL.md` — stale: says 13, code has 18
- `/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/pyproject.toml` — `[dl-gpu]` extra exists but no runtime consumer
