# kailash-ml — Gap Analysis against Vision

**Audit date:** 2026-04-16
**Package:** `packages/kailash-ml` (version 0.9.0, README claims 0.7.0 — version drift already)
**Analyst scope:** product-level redesign direction, not bug-by-bug fixes.

---

## 1. Current state inventory

### 1.1 Surface area (from `src/kailash_ml/__init__.py` + filesystem)

Sixteen public "engines" are exposed, each as a stand-alone class the user constructs and wires manually:

| Group | Engines | File |
| --- | --- | --- |
| Storage/registry | `FeatureStore`, `ModelRegistry`, `LocalFileArtifactStore` | `engines/feature_store.py`, `engines/model_registry.py` |
| Training | `TrainingPipeline` (sklearn / LightGBM / Lightning branches), `PreprocessingPipeline` | `engines/training_pipeline.py`, `engines/preprocessing.py` |
| Search | `HyperparameterSearch`, `AutoMLEngine`, `EnsembleEngine` | `engines/hyperparameter_search.py`, `engines/automl_engine.py`, `engines/ensemble.py` |
| Serving | `InferenceServer` | `engines/inference_server.py` |
| Monitoring | `DriftMonitor`, `ExperimentTracker` | `engines/drift_monitor.py`, `engines/experiment_tracker.py` |
| Unsupervised | `ClusteringEngine`, `AnomalyDetectionEngine`, `DimReductionEngine` | `engines/clustering.py`, `engines/anomaly_detection.py`, `engines/dim_reduction.py` |
| Exploration | `DataExplorer`, `FeatureEngineer`, `ModelVisualizer`, `ModelExplainer` | `engines/data_explorer.py`, `engines/feature_engineer.py`, `engines/model_visualizer.py`, `engines/model_explainer.py` |
| Interop | `OnnxBridge`, `MlflowFormatReader`, `MlflowFormatWriter` | `bridge/onnx_bridge.py`, `compat/mlflow_format.py` |
| UI | `MLDashboard` (Starlette + uvicorn) | `dashboard/` |
| RL (optional extra) | `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry` | `rl/trainer.py`, `rl/env_registry.py`, `rl/policy_registry.py` |
| CLI entry points | `kailash-ml-dashboard`, `kailash-ml-gpu-setup` | `_gpu_setup.py`, `dashboard/__init__.py` |

### 1.2 The actual user workflow today

Looking at `README.md` Quick Start (lines 56–121) and `TrainingPipeline.train()` (`engines/training_pipeline.py:203`) the user must, in sequence:

1. Import `ConnectionManager` from `kailash.db.connection` and choose/create a SQLite path or Postgres URL.
2. `await conn.initialize()`.
3. Instantiate `FeatureStore(conn)` and `await .initialize()`.
4. Instantiate `LocalFileArtifactStore("./artifacts")`.
5. Instantiate `ModelRegistry(conn, artifact_store=...)` and `await .initialize()`.
6. Instantiate `TrainingPipeline(feature_store=fs, model_registry=registry)`.
7. Hand-build a `FeatureSchema(FeatureField(...), entity_id_column=...)` — required even for one-off prototyping.
8. Call `pipeline.train(data, schema, ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier", ...), EvalSpec(...), experiment_name="…")`.
9. Separately instantiate `InferenceServer(model_registry=registry)` to serve.
10. To track experiments: either share the `conn` and instantiate `ExperimentTracker` too, or use `ExperimentTracker.create(...)` which builds its *own* ConnectionManager (parallel state — see `rules/facade-manager-detection.md`).

That is **10 manual wiring steps before a single `fit()`**. PyCaret's equivalent is `setup(data, target)` + `compare_models()`. The gap is structural, not cosmetic.

### 1.3 What doesn't exist

Grep-equivalent inspection of `src/kailash_ml/` shows no file named `engine.py`, no `kailash_ml.Engine` / `MLEngine` / `DLEngine` / `RLEngine` class, no unified entry point. `ml.train(...)` / `ml.predict(...)` / `ml.tune(...)` module-level functions do not exist. The RL module (`rl/trainer.py:RLTrainer`) has its own `RLTrainingConfig` and `RLTrainingResult` that do not share types with `TrainingPipeline.ModelSpec` / `TrainingResult`.

---

## 2. Vision vs current gap matrix

| Vision pillar | Current state | Gap | Classification |
| --- | --- | --- | --- |
| **Lightning as training spine** | `TrainingPipeline._train_lightning` exists (`training_pipeline.py:525`) — one of three parallel `_train_sklearn` / `_train_lightgbm` / `_train_lightning` branches. Lightning is a peer of sklearn, not a spine. sklearn trains via `model.fit(X, y)`; LightGBM via the same; Lightning via `L.Trainer(...).fit(module, dataloader)`. Three different call graphs, three different artifact formats (pickle for sklearn/LightGBM, a manually-constructed TensorDataset for Lightning). | No unified `Trainer` abstraction. Lightning does not drive the loop — `TrainingPipeline` dispatches on `framework` string. Classical models never see Lightning's `Trainer`, `LightningDataModule`, callbacks, or checkpoint system. | **Architectural mismatch** |
| **GPU-first out of the box** | `_cuda_available()` in `automl_engine.py:260` probes torch then `nvidia-smi`. Applied only to XGBoost device selection in AutoML. sklearn, LightGBM, Lightning get no automatic GPU wiring. `[dl]` extra is CPU-only; `[dl-gpu]` is a *separate extra* requiring a separate install command. `kailash-ml-gpu-setup` is a print-only helper — it tells the user what to `pip install` next; it does not actually install anything. | CUDA detection exists but is not wired into training. Users who `pip install kailash-ml[dl]` on a CUDA machine get CPU torch. No `accelerator="auto"` plumbed through. No ROCm story. | **Missing feature** |
| **Single-point engine** | None. The four required primitives (`FeatureStore`, `ModelRegistry`, `TrainingPipeline`, `InferenceServer`) must be wired by the user every single time. `ExperimentTracker.create()` builds a parallel ConnectionManager — a facade-manager anti-pattern documented in `rules/facade-manager-detection.md`. | No `Engine` / `MLContext` / `Session` class. No module-level `ml.fit(...)`. No default-config path. | **Architectural mismatch** |
| **Unified ML / DL / RL** | `TrainingPipeline` handles sklearn + LightGBM + Lightning. `RLTrainer` in `rl/trainer.py` is a completely separate class with its own config (`RLTrainingConfig`) and result (`RLTrainingResult`) — does not flow through `ModelRegistry`, does not emit `TrainingResult`, does not integrate with `ExperimentTracker`. | RL is a parallel universe. There is no common `train()` that routes to classical/DL/RL. | **Architectural mismatch** |
| **PyCaret-better DX** | `AutoMLEngine.run()` (`automl_engine.py:456`) requires pre-built `pipeline`, `search`, `config`, `eval_spec`, `experiment_name` — and is itself the product of five other primitives the user must have already wired. `PreprocessingPipeline.setup()` exists but is not coupled to `AutoMLEngine`. | No `compare_models()`, no `setup(data, target)`, no auto task-type detection at the session level (engine has `task_type` config, but user still names it). `_detect_target` in `training_pipeline.py:717` is "any column not in features" — brittle and documented as pain point #7. | **Missing feature** |
| **MLflow-better tracking** | `ExperimentTracker` is MLflow-format-compatible (reads/writes MLmodel v1) and has nested runs. BUT: it is opt-in (`tracker=` kwarg on every `pipeline.train()` call), not default. No `autolog()` equivalent. No UI for model comparison beyond `MLDashboard` (Starlette read-only). No model registry stage UI. | Tracking exists; defaults are wrong. Every training call silently produces no tracked run unless the user manually constructs and passes a tracker. | **Missing feature + default behavior** |
| **Enterprise-ready** | Model class allowlist (`engines/_shared.py::validate_model_class`) is solid. ONNX export is non-fatal. Artifact storage isolates name validation. BUT: pickle-based artifacts (`training_pipeline.py:285`, `:453`) require trust-the-artifact-source; schema-hash mismatch raises instead of offering migration path (pain #1); `ExperimentTracker.create()` opens a parallel ConnectionManager (facade-manager violation); SQLite file-path is required for most real workflows because `:memory:` doesn't survive the ExperimentTracker factory; `_detect_target` is a heuristic that will misclassify in production data with extra columns. | Reliability landmines throughout. "Observable" mostly means "has a logger" — there's no `model_registered` counter, no `drift_detected` signal, no health endpoint for `InferenceServer`. | **Mix of bugs + missing features** |

---

## 3. Concrete user pain points, traced to root cause

| # | Symptom | Root architectural cause |
| --- | --- | --- |
| 1 | Schema hash conflict raises on re-register | `FeatureStore.register_features` treats schema as immutable (`feature_store.py:106–110`). There is no migration path, no "add column" path, no versioning semantics beyond "bump the name." Root cause: **schema is treated as a content hash rather than an evolvable contract**. |
| 2 | Deep crash when `schema=None` is passed | Every engine assumes non-None schema; there is no runtime type guard and no "infer schema from DataFrame" fallback. Root cause: **schema is mandatory input everywhere, but the ergonomic path users expect is "I'll figure it out from the data."** The engines have no `infer_schema(df)` helper. |
| 3 | DB path fragility | `ConnectionManager("sqlite:///ml.db")` becomes a relative path resolved against CWD; tests that cd into tmpdirs break. Root cause: **kailash-ml has no concept of an ML home directory** (e.g. `~/.kailash_ml/` or `$KAILASH_ML_HOME`). Path resolution is pushed to the caller. |
| 4 | No graceful degradation | Missing optional deps raise `ImportError` mid-pipeline. `[dl]` vs `[dl-gpu]` forces a choice at install time. Root cause: **binary extras rather than a single dependency with runtime capability detection**. `_cuda_available` exists but only AutoML uses it. |
| 5 | GPU not default | `[dl]` installs CPU torch; `[dl-gpu]` requires manual selection with a CUDA index URL. Root cause: **the packaging model predates torch's CUDA-bundled wheels**. XGBoost (base dep) gets auto-GPU; Lightning (extra) does not. |
| 6 | No package-availability checks | Importing `FeatureEngineer` without `[explain]` fails at method-call time, not construction time, not setup time. Root cause: **no capability registry** — the engine doesn't declare its optional-dep requirements upfront, so the user discovers the gap halfway through a run. |
| 7 | Opaque `_detect_target` | `training_pipeline.py:717` — "first column not in features or entity_id or timestamp" — silently picks up any extra column as the target, including `customer_id_hash`, `load_timestamp`, or any audit column. Root cause: **target is inferred, not declared**. `FeatureSchema` has `entity_id_column` and `timestamp_column` fields, but no `target_column`. |
| 8 | File-backed SQLite requirement | `ExperimentTracker.create()` opens its own `ConnectionManager`; `:memory:` is not shared across connections; artifact root defaults to `./experiment_artifacts` CWD-relative. Root cause: **facade-manager anti-pattern** — `ExperimentTracker` builds its own infrastructure rather than taking an injected `MLContext`. Parallel to the Phase 5.11 trust-executor orphan mode. |

All 8 pain points share one underlying cause: **the package exposes primitives and forces the user to compose them**. There is no single-authority "session" object that owns the connection, the artifact store, the tracker, the schema, and the device selection. Every pain point is a consequence of missing that center.

---

## 4. Competitive positioning (≤300 words)

**PyCaret strengths to match.** `setup(data, target)` builds the whole pipeline in one call — task detection, preprocessing, CV split, fold strategy, GPU selection — and returns a session the user queries (`compare_models()`, `tune_model()`, `finalize_model()`, `predict_model()`). The user never sees `sklearn.pipeline.Pipeline`, `train_test_split`, or a `ColumnTransformer`. The session holds the state.

**PyCaret weaknesses to exploit.** Pandas-only, Jupyter-centric, weak at multi-tenant production serving, no polars, no async, weak lineage tracking, experimental MLOps story, no first-class RL, no first-class LLM fine-tune integration, "one global session" model breaks in parallel jobs.

**MLflow strengths to match.** Tracking ubiquity (every tool speaks MLmodel format), registry stages (staging/shadow/production/archived — we already match this), artifact store abstraction, autolog that hooks sklearn/LightGBM/XGBoost/Lightning without manual calls, and `mlflow.pyfunc` cross-format serving.

**MLflow weaknesses to exploit.** Requires a tracking server (we don't), requires object store for artifacts at scale, its "autolog" is monkey-patched at import time and fragile, model registry UI ships separately, SQLite-only store is single-writer and locks in multi-process training, no built-in drift monitoring, no built-in AutoML, no built-in RL, poor polars support. We can be "MLflow without the server" as a real product claim.

**Sweet spot.** Unify PyCaret's DX (session + one-shot AutoML) with MLflow's durability (tracking + registry) and add what both lack (polars-native, async-first, unified classical + DL + RL + LLM-fine-tune, first-class multi-tenant, first-class governance via PACT, GPU-first by default). The tech is there — the product surface is what's missing.

---

## 5. Requirements breakdown

Grouped by pillar. Each is one user-observable behavior with an acceptance criterion.

**Engine surface**
- **R-1: Single entry point.** `from kailash_ml import MLEngine; engine = MLEngine()` with zero required args succeeds; `engine.health()` returns a real dict showing {db, artifact_store, gpu, extras} status.
- **R-2: Infrastructure auto-wires.** `MLEngine()` resolves DB via (1) explicit arg, (2) `$KAILASH_ML_HOME`, (3) `~/.kailash_ml/ml.db`; creates all tables idempotently.
- **R-3: Module-level shortcuts.** `kailash_ml.fit(data, target="churned")` and `kailash_ml.predict(model_name, data)` work without constructing `MLEngine` explicitly (convenience wrapper).
- **R-4: One session, many jobs.** One `MLEngine` services concurrent `fit` / `predict` / `tune` calls; no global singletons; async-safe.

**Schema & data**
- **R-5: Schema inference.** `engine.fit(df, target="y")` infers `FeatureSchema` from the DataFrame; explicit schema remains supported.
- **R-6: Target declared, not detected.** `FeatureSchema` gains a `target_column` field; `_detect_target` is removed; missing target raises a typed `TargetNotDeclaredError` with actionable message.
- **R-7: Schema evolution.** Re-registering a schema with a compatible change (added nullable feature, broadened dtype) migrates; incompatible changes raise with diff output; explicit `force=True` overrides.
- **R-8: Schema-free prototyping.** `engine.fit(df, target="y")` succeeds without ever calling `register_features`; engine synthesizes a one-shot schema.

**Lightning spine**
- **R-9: Lightning is the training loop.** All models (sklearn, LightGBM, XGBoost, torch) are wrapped as `LightningModule`; the same `Trainer` drives CV, early stopping, checkpointing, and callbacks.
- **R-10: Callbacks are uniform.** A single `callbacks=[...]` list (metrics, early stop, drift, audit) works across classical, DL, and RL.
- **R-11: Classical CV runs through Lightning.** k-fold and stratified k-fold are Lightning-native, not ad-hoc (`training_pipeline.py:675` path is replaced).

**GPU-first**
- **R-12: GPU auto-detect default.** `MLEngine()` runs on GPU on a CUDA machine with zero config; falls back to CPU with a single INFO log.
- **R-13: One install, any hardware.** `pip install kailash-ml` picks the right torch wheel at install time (PEP 658 / dynamic metadata or a post-install hook); `[dl-gpu]` extra disappears or becomes a back-compat alias.
- **R-14: ROCm and MPS supported.** Device selection returns `"cuda" | "rocm" | "mps" | "cpu"`; Apple Silicon dev works.

**PyCaret-better**
- **R-15: `compare_models` equivalent.** `engine.compare(df, target="y")` returns a ranked leaderboard across ≥8 classical families plus a deep baseline, each with real CV metrics.
- **R-16: `tune_model` equivalent.** `engine.tune(model_name, strategy="bayesian", budget_seconds=60)` runs search with a wall-clock budget (not just trial count).
- **R-17: `finalize_model` equivalent.** `engine.finalize(model_name)` refits on full data, re-evaluates, promotes to `staging`.
- **R-18: Autodetect task type.** Task (classification / regression / ranking / clustering / anomaly / forecast) inferred from target dtype + cardinality; user override remains.
- **R-19: One-shot report.** `engine.report(model_name)` produces an HTML bundle with data profile, CV results, SHAP summary, drift status, and calibration curve.

**MLflow-better**
- **R-20: Autolog on by default.** Every `fit/tune/compare` call emits an experiment run unless explicitly disabled; run IDs flow through to `TrainingResult` (already present, but opt-in).
- **R-21: Model registry UI.** `MLDashboard` shows registry stages, promotion buttons, metric comparison, and lineage — not just experiment runs.
- **R-22: MLflow-format I/O stays.** `MlflowFormatReader/Writer` remain; format interop is a feature of the product, not the API.
- **R-23: No tracking server.** The DB is the tracking server; no separate service to run.

**Unified ML/DL/RL**
- **R-24: RL via the same surface.** `engine.fit_rl(env="CartPole-v1", algorithm="PPO")` returns a `TrainingResult` that lands in `ModelRegistry`.
- **R-25: RL policies are registered models.** `engine.predict(policy_name, obs)` works for a PPO policy the same way it works for a RandomForest.
- **R-26: LLM fine-tune is a training task.** `engine.fit_llm(base="meta-llama/Llama-3", data=..., method="lora")` delegates to kailash-align but returns the same `TrainingResult`.

**Enterprise**
- **R-27: Health endpoint is real.** `InferenceServer.health()` probes DB, artifact store, cache, and warms a sample prediction; returns structured status (not always-green).
- **R-28: Metrics are real.** `/metrics` exposes `ml_predictions_total{model,version}`, `ml_prediction_latency_seconds`, `ml_drift_severity{feature}`; bounded cardinality per `rules/tenant-isolation.md`.
- **R-29: Multi-tenancy first-class.** Every engine accepts `tenant_id`; registry artifacts and cache keys include tenant; invalidation is tenant-scoped.
- **R-30: Audit every promotion.** Stage transitions, model loads, and predictions write an audit row (tenant_id, agent_id, model_name, version, action).
- **R-31: No pickle in production path.** `ModelRegistry` supports ONNX-first load; pickle fallback is documented and warns with `mode=pickle` log field.
- **R-32: Capability registry.** `engine.capabilities()` returns `{torch: True, cuda: True, shap: False, rl: False}`; engines refuse to initialize methods whose capabilities are missing with a typed `MissingExtraError`.
- **R-33: ML home.** `$KAILASH_ML_HOME` resolves DB, artifacts, and cache paths; default is `~/.kailash_ml/`.
- **R-34: Per-call observability.** Every `fit / tune / predict` emits start/ok/error log with correlation ID and tenant_id per `rules/observability.md`.

---

## 6. Failure points of a redesign

| # | Failure mode | Mitigation |
| --- | --- | --- |
| 1 | **Scope creep — redesign becomes rewrite.** 16 engines + RL + dashboard + MLflow compat is too big to redo in one pass. | Freeze the primitive layer (current engines stay); add an `MLEngine` layer on top that composes them. Move API surface gradually. |
| 2 | **Lightning lock-in regret.** Committing the whole stack to Lightning means any Lightning release breakage cascades everywhere. | Define a thin `KailashTrainer` interface that Lightning implements as the default; keep the door open to Accelerate / DeepSpeed as alternate backends. |
| 3 | **Transaction boundaries across ML/DL/RL.** Registering a classical model is one SQL row; registering a 200GB LoRA adapter is another. Shared registry may bottleneck. | Registry abstraction at the artifact layer — classical → LocalFileArtifactStore; LoRA → object-store-backed artifact store; stage metadata always lives in DB. |
| 4 | **GPU fallback correctness.** Silent CPU fallback on a CUDA machine (driver mismatch, OOM during init) produces slow jobs no one debugs. | Startup banner logs the chosen device at WARN if it's CPU on a machine with visible GPU; `engine.health()` surfaces the fallback reason. |
| 5 | **Pickle → ONNX migration breaks existing artifacts.** 0.9.x users have pickle artifacts; an ONNX-only future strands them. | Registry loads both; `onnx_status` already tracked in `ModelRegistry`; add `pickle_status` with loud deprecation WARN when loading pickle in a fresh 1.0 install. |
| 6 | **Schema-inference silently picks wrong target.** "Last column" heuristic in a production CSV picks `load_timestamp`. | Inference requires explicit `target=` kwarg; schema-less `fit` takes `target: str | FeatureField`; absence raises. |
| 7 | **Parallel ExperimentTracker instances.** `ExperimentTracker.create()` builds its own conn today; redesign consolidates to `MLEngine`. Users with existing `tracker = ExperimentTracker.create(...)` code break silently. | Keep `.create()` as a thin `MLEngine()` wrapper during 1.0 with a DeprecationWarning; remove in 2.0. Per `rules/orphan-detection.md`, if we don't wire it we delete it. |
| 8 | **PyCaret-style session is a hidden global.** Users expect `setup()` then `compare_models()` with no arg passing. Globals break concurrency. | `MLEngine` is always explicit; convenience module-level `kailash_ml.fit` uses a lazy per-thread default; opt-in, not default. |
| 9 | **MLflow format drift.** MLmodel v1 is frozen; v2 exists. Compat promise erodes as users expect newer features. | Version-pin to v1 for kailash-ml 1.0; add v2 when MLflow community settles. Document "MLflow format compat" not "MLflow interop." |
| 10 | **Tests don't exercise the wired path.** `rules/facade-manager-detection.md` — an `MLEngine` orphan is the same failure as Phase 5.11. Unit tests against each engine still pass even if `MLEngine.fit` never actually calls them. | Every `MLEngine.*` method gets a Tier 2 integration test in `tests/integration/test_ml_engine_wiring.py` that asserts external side effects (row in `kml_model_versions`, row in `kml_runs`, cached model in InferenceServer LRU). |

---

## 7. ADR-001: kailash-ml redesign direction

### Status
Proposed.

### Context

The package ships 16 engines (`FeatureStore`, `ModelRegistry`, `TrainingPipeline`, `InferenceServer`, `DriftMonitor`, `ExperimentTracker`, `HyperparameterSearch`, `AutoMLEngine`, `EnsembleEngine`, `PreprocessingPipeline`, `DataExplorer`, `FeatureEngineer`, `ModelVisualizer`, `ModelExplainer`, `OnnxBridge`, `MLDashboard`) plus optional `RLTrainer`. The user has to wire 4–6 of them by hand before any `fit()` call; eight documented pain points all trace to the absence of a session/engine abstraction that owns infrastructure. Lightning exists inside `TrainingPipeline` as one branch of three, not as the spine. GPU is CPU-by-default in the `[dl]` extra. RL is a parallel universe with its own types. No module-level `fit/predict/tune`. Version drift between `pyproject.toml` (0.9.0) and `README.md` (0.7.0) signals the package is not being released atomically.

Three consumers depend on today's surface: `aegis`, `aether`, `kz-engage`. Breaking them silently is the single largest risk.

### Options

**Option A — Rebuild from scratch (greenfield `kailash-ml` 2.0)**
Ship a new package with one `MLEngine` and re-home every capability. Leave 0.9.x frozen for aegis/aether/kz-engage to depend on.

*Pros:* Clean architecture; no compatibility debt; can pick Lightning-as-spine without compromise.
*Cons:* Two packages to maintain; consumer migration is expensive; duplicate bug-fix load; `rules/facade-manager-detection.md` and `rules/orphan-detection.md` both discourage carrying orphans — a frozen 0.9.x is exactly an orphan.

**Option B — Incremental refactor (engine-at-a-time)**
Add `target_column` to `FeatureSchema`, fix pain #1 through #8 one by one, no new top-level surface. Status quo for API shape.

*Pros:* Low risk to consumers; every change is local; reviewer gate is tractable.
*Cons:* Does not address the structural problem (no single engine surface). User's vision of "single-point engine" is incompatible with keeping 16 entry points. After N sessions of incremental work we still do not have PyCaret-better DX.

**Option C — Hybrid: replace the core, keep the edges (RECOMMENDED)**
Add `MLEngine` as the new single entry point. It composes the existing 16 engines internally — `MLEngine.fit()` constructs the appropriate `TrainingPipeline`, `MLEngine.tune()` constructs `HyperparameterSearch`, `MLEngine.compare()` constructs `AutoMLEngine`. Existing engines become "primitives" in the `framework-first.md` Four-Layer Hierarchy. The `MLEngine` is the Engine layer, the current 16 classes are the Primitives, and Raw sklearn/torch is BLOCKED.

Simultaneously: (a) fix the eight pain points inside the primitives (schema evolution, target declaration, path resolution, capability registry); (b) wire Lightning as the default `Trainer` behind `MLEngine.fit()`; (c) collapse `[dl]` / `[dl-gpu]` into a runtime-detected single extra; (d) add `MLEngine.fit_rl()` and `MLEngine.fit_llm()` so RL and Align converge through the same surface.

aegis/aether/kz-engage continue to import `FeatureStore`, `ModelRegistry`, etc. directly during 1.x; 2.0 removes the direct-primitive imports from public surface (still importable from `kailash_ml.engines.*` for power users, same pattern as DataFlow primitives under `kailash_dataflow.primitives`).

### Evaluation matrix

| Criterion | A: Rebuild | B: Incremental | C: Hybrid |
| --- | --- | --- | --- |
| Time to first user value (autonomous cycles) | 6–8 | 10+ (never fully arrives) | 3–4 |
| Risk to aegis/aether/kz-engage | High (migration required) | Minimal | Low (existing imports preserved through 1.x) |
| Alignment with vision | High (greenfield freedom) | Low (structural gap remains) | High (engine layer is the vision) |
| Maintenance burden (12-month view) | 2x (two packages) | 1.2x (creeping complexity) | 1.0x (one surface, same internals) |
| Institutional knowledge reuse | Low (rewrite discards) | High | High |
| Risk of Phase-5.11-style orphan | Medium (new surface untested) | N/A (no new surface) | Mitigated by wiring-test rule (§6 #10) |

### Recommendation

**Option C, the hybrid.** Build `MLEngine` as the new Engine layer. Keep current 16 engine classes as primitives, fix their pain points in place. Wire Lightning as the default trainer. Collapse GPU extras. Unify RL + LLM-fine-tune under the same engine surface.

**What we are NOT doing.**
- NOT rewriting `FeatureStore`, `ModelRegistry`, or `ExperimentTracker` — they are mostly correct, just mis-surfaced.
- NOT removing MLflow format compat — it's a feature.
- NOT building a tracking server — DB is the tracking server.
- NOT shipping a second package — one package, two layers (Engine + Primitives).
- NOT breaking aegis/aether/kz-engage in 1.x — engine-level imports keep working.

### Implementation plan (phased — each phase is one autonomous session)

**Phase 1 (session 1) — Foundation**
Draft `MLEngine` class, `$KAILASH_ML_HOME` resolution, capability registry, health endpoint. Tier 2 wiring tests per `rules/facade-manager-detection.md`. No user-visible API changes yet.

**Phase 2 (session 2) — Schema & target**
Add `target_column` to `FeatureSchema`, remove `_detect_target`, add `infer_schema(df, target=...)`. Schema-evolution path.

**Phase 3 (session 3) — Lightning spine**
`KailashTrainer` interface; Lightning implementation; all classical models wrapped as `LightningModule`; unified callbacks.

**Phase 4 (session 4) — GPU-first & extras collapse**
Runtime device detection; torch wheel resolution; `[dl]`/`[dl-gpu]` merged with back-compat aliases.

**Phase 5 (session 5) — PyCaret-better DX**
`engine.compare()`, `engine.tune(budget_seconds=...)`, `engine.finalize()`, `engine.report()`; task auto-detection.

**Phase 6 (session 6) — Unified ML/DL/RL/LLM**
`engine.fit_rl()`, `engine.fit_llm()` (delegates to kailash-align) — all return `TrainingResult`, all land in `ModelRegistry`.

**Phase 7 (session 7) — Enterprise-ready**
Real `health()`, structured metrics, multi-tenant wiring, audit rows, ONNX-first load path.

---

## Success criteria

- [ ] `from kailash_ml import MLEngine; engine = MLEngine(); engine.fit(df, target="y")` runs on a fresh CUDA machine with GPU, on a Mac with MPS fallback, and on a CPU-only CI runner — zero extra config.
- [ ] aegis, aether, kz-engage import paths continue to resolve on kailash-ml 1.x with zero source changes.
- [ ] PyCaret-equivalent one-liner (`engine.compare(df, target="y")`) returns a leaderboard in under 2 minutes on the UCI `adult` dataset.
- [ ] Every `MLEngine.*` method has a Tier 2 integration test that asserts an external side effect (row written, cache populated, prediction served).
- [ ] `engine.health()` returns a structured status that distinguishes DB, artifact store, GPU, and extras independently.
- [ ] Version locations (`pyproject.toml`, `src/kailash_ml/_version.py`, `README.md`) are updated atomically on every release.
- [ ] `rules/orphan-detection.md` protocol runs clean: every `MLEngine.*_executor` / `*_store` / `*_registry` attribute has a production call site in the same commit.
