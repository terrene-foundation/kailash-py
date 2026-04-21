# Kailash ML Engines Specification (v1.0 Draft)

Version: 1.0.0 (draft)

Parent domain: ML Lifecycle (`kailash-ml`). Companion files (drafted in parallel, referenced by name):

- `ml-backends.md` — device/accelerator/precision resolution, Trainable protocol device contract, `detect_backend()` semantics, per-backend tensor conversion, GPU memory estimation.
- `ml-tracking.md` — `ExperimentTracker` async-context contract, run hierarchy, metrics registry, MLflow format interop, dashboard state injection.
- `ml-serving.md` — `InferenceServer`, `engine.serve()` REST/MCP/gRPC channels, ONNX runtime selection, cache eviction.
- `ml-feature-store.md` — `FeatureStore` schema versioning, `evolve()` helpers, tenant-scoped cache keys, point-in-time correctness.
- `ml-drift.md` — `DriftMonitor`, PSI/KS thresholds, scheduled monitoring, alert routing.
- `ml-rl.md` — `kailash_ml.rl.Engine`, Lightning-composed RL trainers, reward registry.

Package: `kailash-ml` v1.0.0
License: Apache-2.0
Python: >=3.11
Owner: Terrene Foundation (Singapore CLG)

This file is the domain truth for the **`MLEngine`** single-point entry and the cross-cutting contracts every kailash-ml primitive MUST honour: the `Trainable` protocol, the `TrainingResult` dataclass, multi-tenancy, ONNX-default artifacts, the layered hierarchy, and the cross-SDK alignment with kailash-rs. Engine-specific primitive details live in the companion files above.

Origin: `workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md` (5-agent audit 2026-04-17). Supersedes v0.9.x `ml-engines.md` and `ml-integration.md`.

---

## 1. Scope and Non-Goals

### 1.1 What kailash-ml IS

`kailash-ml` is the **enterprise ML/DL/RL lifecycle framework** of the Kailash platform. It owns the full journey from raw data to served model:

1. Feature versioning and point-in-time retrieval (`FeatureStore`).
2. Training orchestration across classical ML, deep learning, and reinforcement learning (`MLEngine`, `rl.Engine`).
3. Experiment tracking and metric history (`ExperimentTracker`).
4. Model registry and artifact storage (`ModelRegistry`).
5. Multi-channel inference serving (`InferenceServer` via `engine.serve()`).
6. Drift and performance-degradation monitoring (`DriftMonitor`).

The framework value is **orchestration, reproducibility, and lifecycle management** built on a shared execution substrate:

- **Lightning core** — PyTorch Lightning is the training spine for every family.
- **GPU-first** — any supported accelerator is used without configuration.
- **Polars-native** — polars DataFrames are the internal data currency.
- **ONNX-default** — every registered model ships an ONNX artifact.
- **Multi-tenant** — every store/registry/tracker/monitor is tenant-scoped.
- **Unified surface** — classical ML, deep learning, and RL flow through the same `MLEngine` contract.

### 1.2 What kailash-ml IS NOT

kailash-ml MUST NOT be positioned, designed, or documented as any of the following:

- **A standalone training library.** It composes sklearn, xgboost, lightgbm, torch, lightning — it does not reimplement them.
- **A model zoo.** It ships no pretrained weights. Users bring their own models.
- **A data preparation tool.** Schema definition, ETL, and bulk ingestion live in DataFlow. kailash-ml consumes polars DataFrames; it does not produce them from raw sources.
- **A tracking-server daemon.** `ExperimentTracker` is an in-process primitive with pluggable backends. There is no long-running tracking server process.
- **A reward-model service.** RL reward functions are in-process registered callables. A reward model as a remote endpoint is out of scope for this spec (see `ml-rl.md` for the boundary).

### 1.3 Non-Goals as MUST NOT Clauses

### 1.3 MUST NOT

#### 1. MUST NOT Ship Pretrained Weights In The Package

`kailash-ml` distributions (wheels, sdist) MUST NOT include any pretrained model weights, tokenizers, or reference datasets.

```python
# DO — user loads their own base weights
from transformers import AutoModelForSequenceClassification
base = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased")

# DO NOT — bundle weights as package data
# package_data = {"kailash_ml": ["weights/bert-base.bin"]}
```

**Why:** Bundled weights balloon the wheel to hundreds of megabytes, create licensing ambiguity for every contributor, and force users of other base models to pay the download cost of a model they don't use.

#### 2. MUST NOT Reimplement sklearn / xgboost / lightgbm / torch Internals

kailash-ml MUST wrap upstream libraries and call their documented APIs. Custom fit loops, custom gradient steps, or custom tree-growth logic are BLOCKED.

**Why:** Reimplementing upstream internals forks the semantics; the first user bug report becomes impossible to reproduce against the canonical library, and every upstream release requires a parallel port of the fix.

---

## 2. `MLEngine` — The Single-Point Engine

`kailash_ml.Engine` (aliased as `MLEngine` for explicit imports) is the canonical user-facing entry. Every documented workflow, every example, every README path MUST start here. Primitives remain accessible under `kailash_ml.primitives.*` for power users who want to bypass the Engine contract — but they are not the default surface.

### 2.1 MUST Rules

#### 1. `kailash_ml.Engine` MUST Support Zero-Argument Construction With Production Defaults

Constructing the Engine without arguments MUST succeed and produce a working instance on any supported platform.

```python
# DO — zero-arg construction works
import kailash_ml as km
engine = km.Engine()
# Uses: SQLite store at ~/.kailash_ml/ml.db (created on first use),
#       accelerator="auto", precision="auto", tenant_id=None,
#       in-process ExperimentTracker, LocalFileArtifactStore.

# DO NOT — require construction arguments for the happy path
engine = km.Engine(
    store=ConnectionManager(...),
    registry=ModelRegistry(conn, store),
    tracker=await ExperimentTracker.create(...),   # canonical factory per ml-tracking §2.5
    trainer=LightningTrainer(accelerator="auto"),
    artifact_store=LocalFileArtifactStore(...),
    feature_store=FeatureStore(conn),
)
```

**Why:** The v0.9.x audit identified the "six-constructor ceremony" (FeatureStore + ModelRegistry + TrainingPipeline + ExperimentTracker + ConnectionManager + ArtifactStore) as the #1 DX failure. A zero-arg default means new users reach their first trained model in the three-line hello world, not in forty lines of plumbing.

**BLOCKED rationalizations:**

- "Users should always construct their own infrastructure"
- "Hiding the ConnectionManager hides important lifecycle details"
- "The defaults might not be right for every deployment"
- "SQLite as the default is a toy"

#### 1b. Store-Path Env-Var Authority Chain (MUST)

Every engine — `MLEngine` and every primitive it constructs (`ExperimentTracker`, `ModelRegistry`, `FeatureStore`, `InferenceServer`, `DriftMonitor`, `AutoMLEngine`, `HyperparameterSearch`, every support engine in the §E1.1 matrix) — MUST resolve its backing-store path via the SAME authority chain, in this exact precedence:

1. **Explicit kwarg** — `store=` / `store_url=` passed to the engine constructor. Honoured verbatim (per MUST 3 dependency-injection contract).
2. **`KAILASH_ML_STORE_URL` env var** — the SINGLE canonical env var for store-path override across the entire ML lifecycle. Read via `os.environ.get("KAILASH_ML_STORE_URL")` exactly once at construction time; never re-read after.
3. **Default** — `sqlite:///~/.kailash_ml/ml.db` (single canonical path per `approved-decisions.md §Implications summary`).

```python
# DO — single canonical env var, one precedence chain
def _resolve_store_url(explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit
    env = os.environ.get("KAILASH_ML_STORE_URL")
    if env is not None:
        return env
    return _DEFAULT_STORE_URL    # sqlite:///~/.kailash_ml/ml.db

# DO NOT — per-primitive env var proliferation
store = os.environ.get("KAILASH_ML_TRACKER_DB")      # legacy tracker-only var
or os.environ.get("KAILASH_ML_REGISTRY_URL")          # hypothetical registry-only var
or os.environ.get("KAILASH_ML_FEATURE_STORE_URL")     # hypothetical feature-store-only var
# ↑ N env vars = N precedence surfaces = N silent drifts between engines
```

**Legacy `KAILASH_ML_TRACKER_DB` bridge.** The v0.9.x spec exposed `KAILASH_ML_TRACKER_DB` for the experiment tracker's SQLite path. kailash-ml 1.x MUST honour it WHEN `KAILASH_ML_STORE_URL` is unset, logging ONE `kailash_ml.env.tracker_db_legacy` DEBUG line on first resolution pointing at the canonical env var. At kailash-ml 2.0, `KAILASH_ML_TRACKER_DB` is REMOVED — resolution raises `EnvVarDeprecatedError` with the migration instruction. No other legacy store-path env vars are accepted.

**Cross-engine consistency.** Every engine MUST use `kailash_ml._env.resolve_store_url(explicit=...)` (single shared helper) — hand-rolled `os.environ.get(...)` at engine-construction sites is BLOCKED per `rules/security.md` § "Multi-Site Kwarg Plumbing" (the authority-chain contract is security-relevant because a divergent engine can silently write to a different store than the tracker reads from, breaking lineage and audit).

**Why:** The v0.9.x code surface exposed `KAILASH_ML_TRACKER_DB` for the tracker AND implicit file-path defaults for every other engine, so `ExperimentTracker` and `ModelRegistry` running in the same process could write to different SQLite files. A single canonical env var + single resolver collapses the surface to one enforcement point; the legacy bridge honours the year-old env var without silently dropping it. The `kailash_ml._env` helper is the single-site plumbing point any auditor can grep for per `rules/observability.md`.

#### 2. `MLEngine` MUST Own Construction Of The Six Primitives

When the Engine is constructed without explicit overrides, it MUST construct the six primitives (FeatureStore, ModelRegistry, TrainingPipeline, ExperimentTracker, ConnectionManager, ArtifactStore) and inject them into itself. The user MUST NOT be required to construct any primitive directly for the default path.

```python
# DO — Engine owns the composition
engine = km.Engine(store="postgresql://...")
# engine._conn, engine._registry, engine._tracker, engine._feature_store,
# engine._trainer, engine._artifact_store are all constructed internally
# from the single `store=` URL.

# DO NOT — user manually wires the six primitives and passes them in
conn = ConnectionManager(url)
registry = ModelRegistry(conn)
tracker = await ExperimentTracker.create(store_url=url)   # canonical factory (ml-tracking §2.5)
fs = FeatureStore(conn)
trainer = TrainingPipeline(fs, registry)
artifacts = LocalFileArtifactStore(".kailash_ml/artifacts")
engine = km.Engine(
    store=conn, registry=registry, tracker=tracker,
    feature_store=fs, trainer=trainer, artifact_store=artifacts,
)
```

**Why:** The composition contract is the Engine's job. Forcing users to repeat it at every call site is exactly the "disjointed, devs hunt for API" pattern the audit flagged.

#### 3. `MLEngine` MUST Accept Dependency Injection For Every Primitive

The Engine MUST accept a full set of override keyword arguments so advanced users can substitute any primitive. Overrides MUST be honoured without falling back to the default for that slot.

```python
# DO — selective override, Engine uses the injected primitive
custom_tracker = MyMlflowBackedTracker(mlflow_uri="http://tracking.local")
engine = km.Engine(store="postgresql://...", tracker=custom_tracker)
# engine._tracker IS custom_tracker; the Engine constructs no default tracker.

# DO NOT — silently wrap or duplicate the override
engine = km.Engine(store="postgresql://...", tracker=custom_tracker)
# engine._tracker = await ExperimentTracker.create(conn); custom_tracker ignored
```

**Why:** Enterprise users regularly need to plug in existing MLflow tracking servers, shared feature stores, or custom artifact backends. A silent "we know better" substitution converts the override into dead code and makes the Engine untrustworthy for power users.

#### 4. Every `MLEngine` Method MUST Return A Named Dataclass — Never A Raw Dict Or Tuple

Every public method on `MLEngine` MUST declare a typed dataclass return (`TrainingResult`, `ComparisonResult`, `PredictionResult`, `ServeResult`, `RegisterResult`, `EvaluationResult`, `SetupResult`, `FinalizeResult`). Returning a raw `dict`, `tuple`, or unnamed polars DataFrame is BLOCKED.

```python
# DO — typed dataclass return
result: TrainingResult = await engine.fit(data, target="churned")
print(result.metrics["accuracy"], result.device.backend_name)  # canonical read
print(result.device_used)                                       # 1.x mirror, still works

# DO NOT — dict return
result = await engine.fit(data, target="churned")  # -> dict
print(result["metrics"]["accuracy"], result.get("device_used"))  # fragile
```

**Why:** Dict returns have no schema guarantees; v0.9.x audit found `TrainingResult`-shaped dicts that drifted in field names between code paths. Named dataclasses give static analysis, IDE auto-completion, and a single place to evolve the contract when fields are added.

#### 5. `MLEngine` Method Set MUST Be Exactly The Documented Eight

The Engine's public method surface MUST be: `setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`. Adding a ninth public method requires a spec amendment; private helpers are unconstrained.

| Method       | Return Type        | Purpose                                                                |
| ------------ | ------------------ | ---------------------------------------------------------------------- |
| `setup()`    | `SetupResult`      | Profile data, infer schema, detect task type, split train/test         |
| `compare()`  | `ComparisonResult` | Train & rank candidate families (AutoML sweep)                         |
| `fit()`      | `TrainingResult`   | Train a single family with optional HP search                          |
| `predict()`  | `PredictionResult` | Serve a prediction (single record or batch, direct or via endpoint)    |
| `finalize()` | `FinalizeResult`   | Retrain top candidate on full training + holdout data                  |
| `evaluate()` | `EvaluationResult` | Evaluate a registered model on new data (holdout / shadow / live)      |
| `register()` | `RegisterResult`   | Register a trained model in the registry (stage, version, artifacts)   |
| `serve()`    | `ServeResult`      | Bind the model to inference channels (REST, MCP, gRPC) and return URIs |

**Why:** Users learn the Engine once. An ad-hoc method grew from eight to eighteen in v0.9.x by accretion; that drift is the proximate cause of the "engines, engines, engines" confusion. A fixed surface forces deliberate design when a new capability is proposed.

#### 6. `setup()` MUST Be Safe To Call Multiple Times With Identical Inputs

`engine.setup(df, target=...)` MUST be idempotent for the same `(df_fingerprint, target, ignore, feature_store_name)` tuple. Re-running with identical inputs MUST NOT create a duplicate run, duplicate schema registration, or duplicate split.

```python
# DO — idempotent setup
setup1 = await engine.setup(df, target="revenue")
setup2 = await engine.setup(df, target="revenue")  # same DataFrame content
assert setup1.schema_hash == setup2.schema_hash
assert setup1.split_seed == setup2.split_seed

# DO NOT — every setup() creates a new schema version
# FeatureSchema(name="User", version=1) -> v2 -> v3 -> ... on repeat calls
```

**Why:** `setup()` is typically called from notebooks; users re-run the cell multiple times while iterating. Non-idempotent `setup()` floods the feature store with phantom schema versions and makes every subsequent `fit()` ambiguous about which version it trained against.

#### 7. `compare()` MUST Route Every Family Through The Lightning Trainer

Every family in the compare sweep — sklearn, xgboost, lightgbm, catboost, torch, lightning — MUST be trained via `lightning.pytorch.Trainer`. Non-torch families are wrapped as LightningModule adapters at the family boundary (see §3 `Trainable`).

```python
# DO — every family goes through Lightning
leaderboard = await engine.compare(
    families=["logreg", "random_forest", "xgboost", "lightgbm", "lightning_mlp"],
)
# All five families fitted via L.Trainer(accelerator="auto", ...)
# All five return TrainingResult with device: DeviceReport populated

# DO NOT — family-specific dispatch that bypasses Lightning
if family == "xgboost":
    model.fit(X, y, tree_method="gpu_hist")   # bypasses Engine's accelerator contract
elif family == "lightgbm":
    model.fit(X, y, device="gpu")             # separate device story
elif family == "lightning":
    trainer = L.Trainer(accelerator="auto")   # only Lightning uses the accelerator
```

**Why:** v0.9.x `training_pipeline.py` had three dispatch branches (sklearn, lightgbm, lightning); the Lightning branch forgot `accelerator=` and silently ran CPU-only on every Apple Silicon / H100 / ROCm machine. Routing every family through the Trainer closes the "some families ignore GPU" failure mode by construction.

#### 8. `fit()` MUST Accept Either A Family Name Or A `Trainable` Instance

`fit()` MUST accept `family="lightgbm"` for registered families, AND MUST accept a user-constructed `Trainable` instance for power users.

```python
# DO — registered family by name
result = await engine.fit(family="lightgbm", hyperparameters={"n_estimators": 500})

# DO — custom Trainable
from my_app.models import MyTransformerTrainable
result = await engine.fit(trainable=MyTransformerTrainable(hidden=768))

# DO NOT — only accept family strings (blocks custom models)
result = await engine.fit(family="lightgbm")  # fine
result = await engine.fit(family=MyTransformerTrainable(...))  # TypeError
```

**Why:** Enterprise users bring custom architectures (in-house transformers, domain-specific CNNs). Restricting `fit()` to registered family strings converts every custom model into a fork of kailash-ml.

#### 9. `register()` MUST Default To ONNX Export

`engine.register(model)` MUST attempt ONNX export by default. The registered `RegisterResult.artifact_uris` dict MUST contain an `"onnx"` key on success. See §6 for the full ONNX contract.

**Why:** ONNX is the only format that enables "train in Python, serve in Rust, serve in C++, serve in a browser." Pickle-default registration is the MLflow-default failure mode; it locks users into Python-only serving and out of cross-language deployments.

#### 10. `serve()` MUST Support `channels=["rest", "mcp", "grpc"]` As A Single Call

`engine.serve(model, channels=["rest", "mcp", "grpc"])` MUST bring up all three channels from one call and return a `ServeResult` with per-channel URIs.

```python
# DO — multi-channel from one call
result = await engine.serve(model, channels=["rest", "mcp"])
assert result.uris["rest"].endswith("/predict/User")
assert result.uris["mcp"].startswith("mcp+stdio://")

# DO NOT — require three separate calls for three channels
rest = await engine.serve_rest(model)
mcp = await engine.serve_mcp(model)
grpc = await engine.serve_grpc(model)
```

**Why:** The "MLflow-better" value proposition in §7 rests on multi-channel serving from a single Engine call; decomposing into per-channel methods recreates the ad-hoc surface the Engine is meant to eliminate.

### 2.2 Canonical Engine Signatures

All methods are async (the Engine is async-first). Synchronous variants under `kailash_ml.sync.Engine` delegate to the async Engine via a managed event loop (see `ml-backends.md` § Event Loop Contract).

```python
class Engine:
    def __init__(
        self,
        store: str | ConnectionManager | None = None,   # URL or ConnectionManager
        *,
        accelerator: str = "auto",                      # "auto" | "cuda" | "mps" | "rocm" | "xpu" | "tpu" | "cpu"
        precision: str = "auto",                        # "auto" | "bf16-mixed" | "fp16-mixed" | "fp32"
        devices: str | int | list[int] = "auto",
        tenant_id: str | None = None,
        # DI overrides (any combination accepted)
        feature_store: FeatureStore | None = None,
        registry: ModelRegistry | None = None,
        tracker: Optional[ExperimentRun] = None,        # user-visible handle (ml-tracking §2.4); HIGH-8 — NOT Optional[ExperimentTracker]
        trainer: LightningTrainerAdapter | None = None,
        artifact_store: ArtifactStore | None = None,
        connection_manager: ConnectionManager | None = None,
    ) -> None: ...

    async def setup(
        self,
        data: pl.DataFrame | pl.LazyFrame,
        *,
        target: str,
        ignore: list[str] | None = None,
        feature_store: FeatureStore | str | None = None,
        test_size: float = 0.2,
        split_strategy: str = "holdout",      # "holdout" | "kfold" | "stratified_kfold" | "walk_forward"
        seed: int = 42,
    ) -> SetupResult: ...

    async def compare(
        self,
        *,
        families: list[str | Trainable] | None = None,   # None -> sensible default set per task_type
        n_trials: int = 0,                               # 0 -> single default-HP fit per family
        hp_search: str = "none",                         # "none" | "grid" | "random" | "bayesian" | "halving"
        metric: str | None = None,                       # None -> primary metric from SetupResult
        early_stopping: Patience | None = None,
        timeout_seconds: float | None = None,
    ) -> ComparisonResult: ...

    async def fit(
        self,
        *,
        family: str | None = None,
        trainable: Trainable | None = None,              # mutually exclusive with `family`
        hyperparameters: dict | None = None,
        hp_search: str = "none",
        n_trials: int = 0,
        metric: str | None = None,
        # --- Lightning distribution passthrough (§3.2 MUST 6) ---
        strategy: str | "L.pytorch.strategies.Strategy" | None = None,
                                                         # None | "ddp" | "fsdp" | "deepspeed"
                                                         # | explicit Lightning Strategy instance.
                                                         # When set, diagnostics/autolog emit
                                                         # rank-0-only per Decision 4.
        devices: int | str | list[int] = "auto",
        num_nodes: int = 1,
        # --- Lightning checkpoint + LR discovery passthrough (§3.2 MUST 7 / MUST 8) ---
        enable_checkpointing: bool = True,               # default True; MUST 7 auto-appends
                                                         # ModelCheckpoint (last.ckpt + epoch=...)
                                                         # rooted at ambient run artifact path.
        auto_find_lr: bool = False,                      # opt-in; runs Trainer.lr_find() then
                                                         # overrides the user's LR, emits the
                                                         # lr_range_test figure to tracker.
        callbacks: list["L.pytorch.callbacks.Callback"] | None = None,
                                                         # user callbacks; engine appends
                                                         # DLDiagnostics.as_lightning_callback()
                                                         # and ModelCheckpoint (non-overridable).
    ) -> TrainingResult: ...

    async def predict(
        self,
        model: str | ModelVersion,
        features: dict | list[dict] | pl.DataFrame,
        *,
        version: int | None = None,
        channel: str = "direct",                         # "direct" | "rest" | "mcp"
        options: dict | None = None,
    ) -> PredictionResult: ...

    async def finalize(
        self,
        candidate: str | TrainingResult,
        *,
        full_fit: bool = True,                           # refit on train+holdout
    ) -> FinalizeResult: ...

    async def evaluate(
        self,
        model: str | ModelVersion,
        data: pl.DataFrame,
        *,
        metrics: list[str] | None = None,
        mode: str = "holdout",                           # "holdout" | "shadow" | "live"
    ) -> EvaluationResult: ...

    async def register(
        self,
        result: TrainingResult,
        *,
        name: str | None = None,
        stage: str = "staging",                          # "staging" | "shadow" | "production"
        format: str = "onnx",                            # "onnx" | "pickle" | "both"
        alias: str | None = None,
    ) -> RegisterResult: ...

    async def serve(
        self,
        model: str | RegisterResult,
        *,
        channels: list[str],                             # subset of ["rest", "mcp", "grpc"]
        version: int | None = None,
        autoscale: bool = False,
        options: dict | None = None,
    ) -> ServeResult: ...
```

### 2.3 Key Error Cases

Every method on `MLEngine` MUST raise a typed exception from `kailash_ml.exceptions.*`. Generic `Exception`, `RuntimeError`, or `ValueError` with no message context is BLOCKED.

| Condition                                                   | Exception                                                             |
| ----------------------------------------------------------- | --------------------------------------------------------------------- |
| `fit()` called before `setup()`                             | `EngineNotSetUpError`                                                 |
| `family=` and `trainable=` both supplied                    | `ConflictingArgumentsError`                                           |
| Target column missing from data                             | `TargetNotFoundError(column=, columns=)`                              |
| Target column included in features                          | `TargetInFeaturesError(column=)`                                      |
| Requested `accelerator="cuda"` but no CUDA device available | `AcceleratorUnavailableError`                                         |
| `tenant_id` missing for multi-tenant model                  | `TenantRequiredError` (see §5)                                        |
| Registered model not found                                  | `ModelNotFoundError(name=, version=)`                                 |
| ONNX export failure when `format="onnx"` and not `"both"`   | `OnnxExportError(framework=, cause=)`                                 |
| Schema drift between `setup()` and `fit()`                  | `SchemaDriftError(before=, after=)`                                   |
| Raw training loop detected (bypasses L.Trainer)             | `UnsupportedTrainerError(family=, reason=)` (§3.2 MUST 2; Decision 8) |
| Hyperparameter numeric value is NaN or ±Inf                 | `ParamValueError(param=, value=)` (§3.2 MUST 3a; ml-tracking §9.1)    |

---

## 3. `Trainable` Protocol

Every model family that can be fitted by `MLEngine.fit()` MUST implement the `Trainable` protocol. This protocol is the single place where the Lightning-core invariant is enforced.

### 3.1 Protocol Definition

```python
from typing import Protocol, runtime_checkable
import polars as pl
import lightning.pytorch as pl_trainer
import torch

@runtime_checkable
class Trainable(Protocol):
    family_name: str                              # registry key e.g. "lightgbm", "lightning_mlp"

    def fit(
        self,
        data: pl.DataFrame,
        *,
        hyperparameters: dict,
        context: TrainingContext,
    ) -> TrainingResult: ...

    def predict(self, X: pl.DataFrame) -> Predictions: ...

    def to_lightning_module(self) -> pl_trainer.LightningModule: ...

    def get_param_distribution(self) -> HyperparameterSpace: ...
```

### 3.2 MUST Rules

**Lightning Hard Lock-In (Decision 8 — pinned).** Per approved decision 8 (2026-04-21), Lightning is THE training protocol for ALL non-RL DL families in kailash-ml 1.0.0. No escape hatch. No research opt-out. No `RawTrainer` primitive. Non-Torch families (sklearn, xgboost, lightgbm, catboost) MUST be wrapped as `LightningModule` adapters at the engine boundary (§3.2 MUST 1). Raw training loops MUST raise `UnsupportedTrainerError(MLError)` (§3.2 MUST 2). `UnsupportedTrainerError` is declared in `kailash_ml.errors` as a direct `MLError` child (cross-cutting — not under any domain family) per `ml-tracking-draft.md §9.1` canonical hierarchy. Open-question 2 from §10.4 is RESOLVED: BLOCKED with no exception.

#### 1. Every Non-RL DL Family MUST Be Wrapped As A LightningModule At The Engine Boundary (Decision 8)

`to_lightning_module()` is mandatory on every `Trainable` in the non-RL path. Non-torch families (sklearn, xgboost, lightgbm, catboost) MUST provide a LightningModule adapter (`SklearnLightningAdapter`, `XGBoostLightningAdapter`, `LightGBMLightningAdapter`, `CatBoostLightningAdapter`) that wraps a single-epoch fit in a LightningModule's `training_step`. RL adapters use `stable_baselines3.BaseAlgorithm` as the substrate (a separate but architecturally-analogous spine — see `ml-rl-core-draft.md §2.3`); the Lightning lock-in does NOT apply to the RL path because SB3 subsumes the same concerns (device resolution, callback pipeline, checkpoint strategy).

```python
# DO — lightgbm wrapped as a LightningModule
class LightGBMLightningAdapter(pl.LightningModule):
    def __init__(self, inner_model):
        super().__init__()
        self._inner = inner_model

    def training_step(self, batch, batch_idx):
        X, y = batch
        self._inner.fit(X, y, eval_set=[(X, y)])
        return torch.zeros(1, requires_grad=True)   # bookkeeping only

# DO NOT — lightgbm fitted directly with its own trainer
model = LGBMClassifier(**hp)
model.fit(X, y, eval_set=[(X_val, y_val)])       # bypasses L.Trainer, bypasses accelerator
```

**Why (reinforced by Decision 8):** A Trainable that bypasses `L.Trainer` also bypasses the accelerator contract — see §2.1 MUST 7. The adapter is the architectural enforcement of "Lightning as spine." Decision 8 made the lock-in HARD because every escape hatch in v0.9.x became a production bypass: the lightgbm branch at `training_pipeline.py:501` was meant as a "temporary optimization" and became the permanent path that skipped every accelerator-resolution invariant.

#### 2. Custom (Raw) Training Loops MUST Raise `UnsupportedTrainerError` (Decision 8 — hard lock-in)

A `Trainable` MUST NOT implement its own training loop (`for epoch in range(...)`, custom optimizer stepping, custom gradient accumulation) inside `fit()`. Custom logic lives inside the `LightningModule`'s `training_step` / `validation_step` — `L.Trainer` drives the outer loop. The Engine MUST detect raw-loop attempts at `fit()` dispatch time (by verifying `trainable.to_lightning_module()` returns a `LightningModule` subclass AND the trainable's `fit()` calls `L.Trainer(...).fit(module, ...)` as its terminal step) and raise `UnsupportedTrainerError`:

```python
# kailash_ml/errors.py  (canonical — see ml-tracking-draft.md §9.1; also re-exported
#                        at kailash_ml.errors.UnsupportedTrainerError and
#                        kailash.ml.errors.UnsupportedTrainerError per
#                        supporting-specs-draft/kailash-core-ml-integration-draft.md §3.5)

class UnsupportedTrainerError(MLError):
    """Raised when a Trainable's fit() bypasses L.Trainer (Decision 8).

    Per ml-engines-v2-draft.md §3.2 MUST 2 (Lightning hard lock-in):
    every non-RL DL Trainable MUST wrap its family as a LightningModule
    and drive training via L.Trainer(**context_kwargs).fit(module, ...).
    Custom training loops bypass the accelerator contract and are
    structurally BLOCKED. No escape hatch; no RawTrainer primitive.

    Inheritance note: `UnsupportedTrainerError(MLError)` — direct child of
    MLError, NOT a subclass of any domain family. Cross-cutting because
    raw-loop detection can trigger during engine dispatch, AutoML trial
    dispatch, or sibling-adapter composition — unifying under MLError
    (not EngineError, not AutoMLError) keeps `except MLError` ergonomics.
    """

    def __init__(self, family: str, reason: str):
        self.family = family
        self.reason = reason
        super().__init__(
            f"Trainable family={family!r} bypasses L.Trainer: {reason}. "
            f"Wrap your model as a LightningModule per ml-engines-v2-draft.md §3.2 MUST 1. "
            f"RL users: see ml-rl-core-draft.md §2.3 (SB3 substrate applies to RL only)."
        )
```

```python
# DO — L.Trainer drives the loop, LightningModule implements the step
class MyTrainable:
    def fit(self, data, *, hyperparameters, context):
        module = self.to_lightning_module()
        trainer = L.Trainer(
            accelerator=context.accelerator,
            precision=context.precision,
            max_epochs=hyperparameters["epochs"],
        )
        trainer.fit(module, data_loader)

# DO NOT — custom training loop in fit() → raises UnsupportedTrainerError
class MyTrainable:
    def fit(self, data, *, hyperparameters, context):
        model = MyModel()
        opt = torch.optim.Adam(model.parameters())
        for epoch in range(hyperparameters["epochs"]):   # BLOCKED by Engine guard
            for batch in data_loader:
                loss = model(batch)
                loss.backward()
                opt.step()
        # Engine raises UnsupportedTrainerError(family="MyTrainable",
        #   reason="fit() did not invoke L.Trainer.fit; raw loop detected")
```

**BLOCKED rationalizations (Decision 8 — all rejected):**

- "My model has unusual scheduling Lightning can't express" — write a `LightningModule` with custom `training_step`; L.Trainer's outer loop is agnostic to what happens inside a step.
- "L.Trainer adds overhead I don't need" — overhead is < 1% for realistic batch sizes; one enforcement point is worth it.
- "This is research code, we'll Lightning-ify later" — "later" is how orphans ship.
- "The custom loop is just for initialization" — move initialization to `configure_optimizers()`.
- "Give us a `RawTrainer` escape hatch with a warning" — Decision 8 explicitly rejects this. A warning gated on `escape_hatch=True` is read by zero users and becomes the default path for every "just-this-once" case.

**Why (Decision 8 — hard-lock-in rationale):** Every custom loop is a new device-management surface. The v0.9.x audit showed that even a single branch that bypassed `L.Trainer` (the lightgbm branch at `training_pipeline.py:501`) had its own partial device story, and that story was wrong (GPU-only via string flag, no MPS/ROCm). Decision 8 closes this class of bug structurally: one trainer, one enforcement point, zero exceptions.

#### 3. `get_param_distribution()` MUST Return A `HyperparameterSpace` Even If The Family Has No Tunable Params

Every Trainable MUST return a valid `HyperparameterSpace` — empty is acceptable, `None` is not. This is what allows `MLEngine.compare(n_trials=N)` to sweep any family uniformly.

```python
# DO — empty space returned for a no-tunable family
def get_param_distribution(self) -> HyperparameterSpace:
    return HyperparameterSpace(params=[])

# DO NOT — None or raise
def get_param_distribution(self):
    return None
```

**Why:** Downstream dispatch tests `isinstance(space, HyperparameterSpace)`; `None` returns force every call site to branch, which is exactly the kind of ad-hoc dispatch the Engine eliminates.

#### 3a. Hyperparameter Values MUST Pass Finite-Check On Numeric Types (`ParamValueError`)

When the Engine materializes a sampled hyperparameter set from a `HyperparameterSpace` (either user-supplied `hyperparameters=` on `fit()`, a `compare(n_trials=N)` trial, or an HPO outer loop), every numeric value MUST pass `math.isfinite()` before being passed into `Trainable.fit()`. NaN / ±Inf values MUST raise `kailash_ml.errors.ParamValueError` (multi-inherits `ValueError` per ml-tracking §9.1 Decision 4 pattern) — silent coercion to `None` / `0.0` / `str(value)` is BLOCKED.

```python
# DO — reject malformed hyperparameters at dispatch
# (symmetry with ml-tracking §4.1 param-path finite-check)
await engine.fit(family="lightgbm", hyperparameters={"learning_rate": float("nan")})
# raises ParamValueError("param 'learning_rate' value=nan is not finite")

# DO NOT — silent coerce
# engine passes nan through, LightGBM trains with broken optimizer, downstream metrics are NaN
```

**Why:** Hyperparameter NaN is the leading indicator of a broken sweep — an HPO strategy that emits NaN for a trial means the strategy itself is broken (bad prior, divide-by-zero in the proposal). Catching at dispatch gives the operator one actionable stack trace; letting NaN through produces N failed trials that look like a model bug.

Cross-reference: same error class is raised by `ExperimentRun.log_param` / `log_params` per `ml-tracking-draft.md §4.1`. Both paths share the same finite-check rule AND the same typed exception so callers may write `except ParamValueError` uniformly.

#### 4. `TrainingContext` MUST Carry Accelerator / Precision / Tenant / Tracker Through To The Trainable

`fit(data, *, hyperparameters, context)` receives a `TrainingContext` dataclass with the Engine's resolved accelerator, precision, devices, tenant_id, tracker run_id, and trial number. Trainables MUST NOT re-resolve the device themselves (e.g. calling `torch.cuda.is_available()` inside `fit()` is BLOCKED).

**Why:** Device resolution belongs to `ml-backends.md::detect_backend()`. Trainables that re-resolve can disagree with the Engine (e.g. Engine picked MPS, Trainable re-resolved to CPU because it only checked CUDA), causing split-brain behaviour where the TrainingResult reports one device but the tensors ran on another.

#### 5. `TrainingPipeline._train_lightning` MUST Auto-Append `DLDiagnostics.as_lightning_callback()` When Diagnostics + Tracker Are Ambient

The engine-boundary Lightning dispatch (internal `TrainingPipeline._train_lightning`, invoked by `MLEngine.fit(family=..., strategy=...)` for every DL family including `SklearnLightningAdapter` / `XGBoostLightningAdapter` / `LightGBMLightningAdapter` / `CatBoostLightningAdapter` / `HuggingFaceTrainable` / user-supplied `Trainable`) MUST auto-append a `DLDiagnostics.as_lightning_callback()` instance to the `L.Trainer` callback list whenever BOTH conditions hold:

1. `DLDiagnostics.is_available()` returns `True` (i.e. the `[dl]` extra is installed — see Decision 13).
2. `kailash_ml.tracking.get_current_run()` returns a non-None `ExperimentRun` (the dispatch is running inside an ambient `km.track(...)` / `km.autolog(...)` scope — see `ml-tracking-draft.md §2.4`).

Attachment is NON-OVERRIDABLE — users who pass `callbacks=[my_cb]` receive `[my_cb, <DLDiagnostics callback>, <ModelCheckpoint>]` in final order. A user-supplied `DLDiagnostics.as_lightning_callback()` instance MUST be de-duplicated by `isinstance` check (only one diagnostics callback ever fires per `L.Trainer.fit()` invocation; the engine-appended instance wins).

```python
# kailash-ml/src/kailash_ml/engines/training_pipeline.py
# ml-engines-v2 §3.2 MUST 5 — auto-attach DLDiagnostics callback at engine boundary

def _train_lightning(
    self,
    module: L.LightningModule,
    data_loader,
    *,
    hyperparameters: dict,
    context: TrainingContext,
    user_callbacks: list[L.pytorch.callbacks.Callback] | None = None,
    strategy: str | L.pytorch.strategies.Strategy | None = None,
    num_nodes: int = 1,
    enable_checkpointing: bool = True,
    auto_find_lr: bool = False,
) -> TrainingResult:
    callbacks: list[L.pytorch.callbacks.Callback] = list(user_callbacks or [])

    # MUST 5 — diagnostics auto-attach
    if DLDiagnostics.is_available() and get_current_run() is not None:
        # De-dup: user may have already passed one; engine-appended instance wins
        callbacks = [cb for cb in callbacks if not _is_dldiag_callback(cb)]
        diag = DLDiagnostics.from_context(context)  # binds to ambient run
        callbacks.append(diag.as_lightning_callback())

    # MUST 7 — default ModelCheckpoint (only when checkpointing enabled)
    if enable_checkpointing:
        callbacks.append(_default_model_checkpoint(run=get_current_run()))

    trainer_kwargs = {
        "accelerator": context.accelerator,
        "precision": context.precision,
        "devices": context.devices,
        "max_epochs": hyperparameters.get("epochs", 1),
        "callbacks": callbacks,
        "enable_checkpointing": enable_checkpointing,
        "num_nodes": num_nodes,
    }
    if strategy is not None:
        trainer_kwargs["strategy"] = strategy   # MUST 6

    trainer = L.Trainer(**trainer_kwargs)

    # MUST 8 — opt-in LR range test (disabled by default)
    if auto_find_lr:
        tuner_result = trainer.tuner.lr_find(module, data_loader)
        new_lr = tuner_result.suggestion()
        module.hparams.lr = new_lr
        if (run := get_current_run()) is not None:
            run.log_figure("lr_range_test", tuner_result.plot(suggest=True))
            run.log_param("auto_find_lr.suggested_lr", new_lr)

    trainer.fit(module, data_loader)
    return _make_training_result(trainer, module, context)
```

**Why:** The Round-3 audit found that `DLDiagnostics` was declared as a first-class callback surface (`ml-diagnostics-draft.md §5.3`) but NOT wired at the engine boundary — users had to manually append `diag.as_lightning_callback()` to their `L.Trainer` to receive per-batch gradient-norm / epoch val-loss capture. Auto-attach at `TrainingPipeline._train_lightning` closes the orphan: a user writing `async with km.track("exp"): await engine.fit(family="lightning_mlp")` automatically gets DLDiagnostics without a second import. The non-overridable contract matches `ml-autolog-draft.md §3.2` (rank-0-only emission); diagnostics is a framework invariant, not a user preference.

**Regression test (release-blocking):** `tests/integration/test_lightning_auto_attach_diagnostics_callback.py` MUST:

1. Define a toy `L.LightningModule` (MLP, 2 epochs, 10 batches).
2. Fit inside `async with km.track("test-auto-attach") as run:` with an ephemeral tracker DB.
3. Assert `DLDiagnostics` emitted per-batch `loss` + per-epoch `val_loss` metrics to the ambient `ExperimentRun` (via `run.query_metrics("loss")` count ≥ 20).
4. Assert `ModelCheckpoint` wrote `last.ckpt` under the run's artifact path (via `registry.get_run(run.run_id).artifact_paths["checkpoint"]` + `Path(...).exists()`).
5. Assert the engine-supplied callbacks list contains exactly one instance of each callback class.

Skip conditions: `pytest.importorskip("lightning.pytorch")`; `pytest.importorskip("torch")`. Runs on CPU-only CI (Decision 7 — blocking tier) per `ml-backends-draft.md §6.3`.

#### 6. `MLEngine.fit(..., strategy=None)` MUST Accept Lightning `strategy=` Kwarg Passthrough

`MLEngine.fit()` MUST accept a `strategy=` kwarg whose type is `str | lightning.pytorch.strategies.Strategy | None`. Accepted string values: `"ddp"`, `"fsdp"`, `"deepspeed"`. An explicit Strategy instance (e.g. `L.pytorch.strategies.DDPStrategy(process_group_backend="nccl")`) is also accepted. `None` leaves Lightning's default (single-device) behaviour unchanged.

When `strategy` is non-None, `TrainingPipeline._train_lightning` MUST:

1. Pass the value verbatim as `L.Trainer(strategy=strategy)`.
2. Propagate `num_nodes: int` (default 1) and `devices: int | str | list[int]` (default `"auto"`) from `MLEngine.fit(num_nodes=..., devices=...)` kwargs into the Trainer constructor.
3. Gate DLDiagnostics emission AND autolog emission to rank 0 only — see `ml-autolog-draft.md §3.2 MUST 2` and `ml-diagnostics-draft.md §5.5` Decision 4 rank-0 rule. The rank-0 check uses `torch.distributed.get_rank() == 0` (when dist is initialized) OR `DistributionEnv.detect().is_main_process` (when accelerate is the launcher).

```python
# DO — user enables FSDP for a 70B model
result = await engine.fit(
    family="lightning_mlp",      # any DL family; strategy is transport, not family
    hyperparameters={"width": 8192, "depth": 96},
    strategy="fsdp",
    devices=8,
    num_nodes=4,
)
# result.lightning_trainer_config == {
#   "accelerator": "cuda", "precision": "bf16-mixed", "devices": 8,
#   "strategy": "fsdp", "num_nodes": 4, "max_epochs": ..., "callbacks": [...]
# }

# DO — explicit Strategy instance for advanced configuration
from lightning.pytorch.strategies import DeepSpeedStrategy
result = await engine.fit(
    family="huggingface",
    hyperparameters={"model_name_or_path": "meta-llama/Llama-3.1-8B", "task": "causal_lm"},
    strategy=DeepSpeedStrategy(stage=3, offload_optimizer=True),
    devices=8,
    num_nodes=2,
)

# DO NOT — raw torch DDP init inside a custom Trainable's fit()
class MyTrainable:
    def fit(self, data, *, hyperparameters, context):
        torch.distributed.init_process_group(backend="nccl")   # BLOCKED — bypasses Trainer
        ...
# Engine raises UnsupportedTrainerError (§3.2 MUST 2) because fit() did not terminate in L.Trainer.fit
```

**Extras dependency (Decision 13 addendum):**

- `strategy="ddp"` — requires `[dl]` extra (torch + lightning). Works across CUDA / MPS / CPU / ROCm / XPU per `ml-backends-draft.md §3`.
- `strategy="fsdp"` — requires `[dl]` extra AND `torch >= 2.3` (FSDP2 / `ShardedTensor` stabilised at 2.3). Startup probe asserts `torch.__version__ >= 2.3` and raises `BackendUnavailableError("FSDP requires torch>=2.3; detected <version>")` otherwise.
- `strategy="deepspeed"` — requires a NEW extra `[dl-deepspeed]` that pins `deepspeed>=0.14.0` + `pydantic>=2.0`. `[dl-deepspeed]` is declared in `pyproject.toml` alongside the existing DL extras:

```toml
# packages/kailash-ml/pyproject.toml
[project.optional-dependencies]
dl = [
    "torch>=2.3",
    "lightning>=2.2",
    "transformers>=4.30",
    "peft>=0.10.0",              # PEFT / LoRA / QLoRA (HuggingFaceTrainable §9)
]
dl-deepspeed = [
    "kailash-ml[dl]",             # composes with dl
    "deepspeed>=0.14.0",
    "pydantic>=2.0",
]
dl-fsdp = ["kailash-ml[dl]"]      # alias: FSDP already covered by [dl] + torch>=2.3
```

Both `[dl-deepspeed]` and `[dl-fsdp]` MUST be added to the canonical extras catalog in `ml-backends-draft.md §6.2` and referenced in `Decision 13` propagation (this file is the authoritative declaration point for `[dl-deepspeed]`; `[dl-fsdp]` is an alias).

**Why:** Distributed training is the single-biggest source of silent production breakage in DL frameworks that ship "supports DDP" without an engine-level passthrough — every user ends up rolling their own `torch.distributed.init_process_group` which bypasses Lightning's rank-0 gating AND disagrees with the autolog rank-0 rule (Decision 4). Engine-level passthrough keeps the entire distribution surface under the single `L.Trainer` enforcement point that §3.2 MUST 1-2 already guards.

**Regression test (release-blocking):** `tests/integration/test_fit_ddp_strategy_rank0_emission.py` MUST:

1. Use `lightning.pytorch.Trainer(strategy="ddp", devices=2, accelerator="cpu")` (CPU-DDP is deterministic for CI).
2. Fit a toy module via `engine.fit(..., strategy="ddp", devices=2)` inside `km.track("ddp-test")`.
3. Assert the tracker run has exactly ONE copy of each metric (no rank-1 duplicates) — `len(run.query_metrics("loss")) == N_batches`, not `2 * N_batches`.
4. Assert `result.lightning_trainer_config["strategy"] == "ddp"` and `result.lightning_trainer_config["num_nodes"] == 1`.
5. Skip when `torch.distributed` not compiled in OR fewer than 2 logical CPUs available.

A companion Tier-1 mocked-distributed test (`test_ddp_rank1_skips_emission.py`) MUST patch `torch.distributed.get_rank()` to `1` and assert zero `log_metric` calls fire.

#### 7. `ModelCheckpoint` Default + `km.resume()` Top-Level — `enable_checkpointing` Default Flips To `True`

`TrainingPipeline._train_lightning` MUST auto-append a `lightning.pytorch.callbacks.ModelCheckpoint` instance to the `L.Trainer` callbacks list (in addition to the `DLDiagnostics` callback from MUST 5) whenever `enable_checkpointing=True` (the new default). The ModelCheckpoint instance MUST be constructed with:

```python
# kailash-ml/src/kailash_ml/engines/training_pipeline.py  (MUST 7 helper)
from pathlib import Path
from lightning.pytorch.callbacks import ModelCheckpoint

def _default_model_checkpoint(run: ExperimentRun | None) -> ModelCheckpoint:
    """MUST 7 — canonical checkpoint callback.

    When `run` is None (no ambient tracker), write to a deterministic temp
    root so the checkpoint is still produced for `km.resume()` to read
    post-hoc via `result.artifact_uris["checkpoint"]`.
    """
    if run is not None:
        dirpath = Path(run.artifact_path)          # per ml-tracking-draft.md §2.4
    else:
        dirpath = Path.home() / ".kailash_ml" / "checkpoints" / _uuid()
    dirpath.mkdir(parents=True, exist_ok=True)
    return ModelCheckpoint(
        dirpath=str(dirpath),
        filename="epoch={epoch}-step={step}",     # Lightning expands vars
        save_last=True,                            # emits `last.ckpt` sidecar
        save_top_k=1,
        monitor="val_loss",
        mode="min",
        auto_insert_metric_name=False,
    )
```

Previously, `enable_checkpointing=False` was the default in v0.9.x TrainingPipeline. Starting at 1.0.0, the default MUST flip to `enable_checkpointing=True`. Users who explicitly pass `enable_checkpointing=False` still disable both the appended `ModelCheckpoint` AND Lightning's internal checkpointing.

**`km.resume(run_id)` module-level function** (§12A — declared in `kailash_ml/__init__.py`; listed in `__all__` Group 1 between `"reproduce"` and `"rl_train"`):

```python
# In kailash_ml/__init__.py — §12A resume entry point

async def resume(
    run_id: str,
    *,
    tenant_id: str | None = None,
    tolerance: dict[str, float] | None = None,
    verify: bool = False,
    data: pl.DataFrame | None = None,
) -> TrainingResult:
    """Resume training from a run's last checkpoint.

    Reads the tracker run's `artifact_path`, locates `last.ckpt`, and
    dispatches to a cached default `Engine()` with `resume_from_checkpoint`
    pinned to that path. Returns a new `TrainingResult` whose lineage
    points to the original `run_id`.

    Args:
        run_id: Tracker run to resume. MUST exist in the ambient
            ExperimentTracker and MUST have a last.ckpt artifact.
        tenant_id: Required when the original run's model is multi-tenant.
        tolerance: Optional per-metric max divergence ({"val_loss": 0.01}).
            When set AND `verify=True`, resumed run's final metrics are
            compared to the parent's; raises `ResumeDivergenceError` on
            any metric that drifts beyond tolerance. Default `None`
            (no post-resume verification).
        verify: When True + `tolerance` set, perform the divergence check.
        data: Optional override training data; when None, re-loads the
            parent run's recorded feature-store snapshot.

    Raises:
        ResumeArtifactNotFoundError: No `last.ckpt` present at the run's
            artifact path. The error message includes the expected path.
        ModelNotFoundError: run_id does not exist in the tracker.
        ResumeDivergenceError: `verify=True` + any metric beyond `tolerance`.

    Returns:
        TrainingResult from the continued fit; `TrainingResult.family`
        and `TrainingResult.hyperparameters` mirror the parent run; a new
        `tracker_run_id` is created with `parent_run_id=<original>` and
        `run_type="resume"`.
    """
```

`ResumeArtifactNotFoundError` MUST inherit from `ModelRegistryError(MLError)` (per `ml-tracking-draft.md §9.1` canonical hierarchy — registry/artifact failures live under ModelRegistryError):

```python
# In kailash_ml/errors.py
class ResumeArtifactNotFoundError(ModelRegistryError):
    """Raised when km.resume() cannot locate last.ckpt for the run.

    Inherits ModelRegistryError (not a cross-cutting MLError child) because
    the failure mode is artifact-storage-absent, matching other
    ModelRegistryError children (ModelNotFoundError, ArtifactCorruptedError).
    """

    def __init__(self, run_id: str, expected_path: str):
        self.run_id = run_id
        self.expected_path = expected_path
        super().__init__(
            f"km.resume(run_id={run_id!r}) — no last.ckpt found at "
            f"{expected_path!r}. Checkpointing was likely disabled "
            f"(enable_checkpointing=False) on the original run. See "
            f"ml-engines-v2-draft.md §3.2 MUST 7 (default enable_checkpointing=True)."
        )
```

`ResumeDivergenceError` lives alongside and inherits `MLError` (cross-cutting — can fire during tracker metric read, registry metric diff, or evaluator compare).

**BLOCKED rationalizations:**

- "Checkpointing at every epoch wastes disk — keep the v0.9.x default." — The default-False was the bug Round-3 surfaced; default-True is the release-gate fix. Operators who want no checkpoints pass `enable_checkpointing=False` explicitly.
- "km.resume lives on MLEngine, not the module." — No: the convention is the module-level surface (per §15 `km.*` wrappers) routing through a cached default Engine. Adding a `resume` method on MLEngine violates §2.1 MUST 5 (eight-method surface).
- "Tolerance should be required, not optional." — No: default `tolerance=None` is "re-run without verification"; explicit tolerance is "re-run and prove equivalence." Both use-cases are first-class.

**Why:** Round-3 found that Lightning's checkpoint path was advertised in `ml-engines-v2-draft.md §3.2 MUST 1-2` ("L.Trainer drives the loop") but the engine-level wrapper left `enable_checkpointing=False` from v0.9.x — users who expected "Lightning's default is save-and-resume" instead got "no checkpoint, no resume." The default flip + top-level `km.resume()` closes the gap; `ResumeArtifactNotFoundError` makes the silent-disable failure mode loud at resume time.

**Regression tests (release-blocking):**

- `tests/integration/test_default_checkpointing_enabled.py` — fits a toy module inside `km.track(...)`, asserts `last.ckpt` + at least one `epoch=*.ckpt` exist under the run's artifact path.
- `tests/integration/test_km_resume_roundtrip.py` — fits run A for 2 epochs, calls `km.resume(A.run_id, tolerance={"val_loss": 0.01}, verify=True, data=<fresh_batch>)`, asserts the resumed run `B.parent_run_id == A.run_id` AND `B.metrics["val_loss"] <= A.metrics["val_loss"] + 0.01`.
- `tests/integration/test_km_resume_missing_checkpoint_raises.py` — fits run A with `enable_checkpointing=False`, calls `km.resume(A.run_id)`, asserts `ResumeArtifactNotFoundError` with the expected-path substring in the message.

#### 8. `MLEngine.fit(..., auto_find_lr=False)` — LR Range Test Is Opt-In, Default Off

`MLEngine.fit()` MUST accept an `auto_find_lr: bool = False` kwarg. Default is **OFF** — no automatic LR modification occurs. When `auto_find_lr=True`, the dispatch MUST:

1. Call `trainer.tuner.lr_find(module, data_loader)` before `trainer.fit(...)`.
2. Extract the suggested LR via `tuner_result.suggestion()`.
3. Override the module's LR by assigning `module.hparams.lr = suggested_lr` (the canonical Lightning LR storage convention).
4. Emit the lr_range_test plot to the ambient `ExperimentRun` via `run.log_figure("lr_range_test", tuner_result.plot(suggest=True))` — skipped if no ambient run.
5. Emit `run.log_param("auto_find_lr.suggested_lr", suggested_lr)` for traceability.
6. Proceed with `trainer.fit(...)` at the new LR.

The `auto_find_lr=True` path requires the `[dl]` extra (torch + lightning). If lightning is unavailable, raise `BackendUnavailableError("auto_find_lr=True requires kailash-ml[dl]")`.

```python
# DO — explicit opt-in when the user wants the LR scan
result = await engine.fit(
    family="lightning_mlp",
    hyperparameters={"lr": 1e-3, "epochs": 20},   # 1e-3 is the user's guess
    auto_find_lr=True,                            # will override lr with scan result
)
# result.hyperparameters["lr"] == suggested value; original 1e-3 captured in
# log_param("auto_find_lr.user_lr", 1e-3) for the audit trail

# DO NOT — default-on for LR scanning
# (would silently replace the user's LR on every fit; breaks reproducibility because
#  lr_find is seed-sensitive and varies with batch ordering)
```

**BLOCKED rationalizations:**

- "Default-on saves users from bad LRs." — No: it silently overrides a user-supplied hyperparameter, which is the exact drift rule `autonomous-execution.md` prohibits. The user's `lr=1e-3` is a deliberate choice.
- "Emit a WARN if default-on overrides the user's lr." — No: WARN-gated behaviour change IS the drift; users don't read WARN lines (see `rules/zero-tolerance.md` Rule 1 — warnings are errors).
- "Gate default-on behind a package-level config." — No: per-call kwarg is the minimal scope and the one that shows up in `result.hyperparameters` audit trail.

**Why:** PyTorch Lightning's `lr_find` is a genuinely useful tool but is **seed-sensitive and batch-order-sensitive** — running it twice can return different suggested LRs. Making it default-on means every `engine.fit(...)` is non-reproducible unless the user explicitly re-seeds before each fit. Default-off preserves the reproducibility contract (§11-§12); opt-in is the only safe default.

**Regression test:** `tests/integration/test_auto_find_lr_opt_in.py`:

1. With `auto_find_lr=False` (default): the user's `hyperparameters["lr"]=1e-3` is preserved verbatim in `result.hyperparameters`; no `lr_range_test` figure exists on the run.
2. With `auto_find_lr=True`: `result.hyperparameters["lr"]` differs from the user's input; `run.list_figures()` contains exactly one `lr_range_test` entry; `run.get_param("auto_find_lr.suggested_lr")` is a finite float.

#### 9. `HuggingFaceTrainable` — First-Class `LightningModule` Adapter For `transformers.Trainer`

kailash-ml 1.0.0 MUST ship `HuggingFaceTrainable` as a first-class `Trainable` implementation (§3.1) that wraps `transformers.Trainer` under Lightning's `LightningModule` contract. This preserves HF-native features (PEFT / LoRA / `compute_metrics` / `TrainerCallback` event stream / ModelCard emission) while conforming to the engine's eight-method surface (§2.1 MUST 5) AND the Lightning lock-in (Decision 8 / §3.2 MUST 1-2).

Shipping in 1.0.0 (NOT deferred to 1.1) because `transformers` is the dominant DL family in production (per industry-parity audit Round-3) — deferring `HuggingFaceTrainable` would force every HF user onto a raw `transformers.Trainer` path that bypasses MUST 5-7 / Decision 4 rank-0 gating / §5 tenant isolation.

```python
# kailash-ml/src/kailash_ml/trainables/huggingface.py

from typing import Literal
import lightning.pytorch as L
import transformers
from transformers import AutoTokenizer

class HuggingFaceTrainable(L.LightningModule):
    """Bridges `transformers.Trainer` under Lightning.

    Preserves HF ergonomics (PEFT, LoRA, compute_metrics, TrainerCallback)
    while conforming to the engine's 8-method surface. Exposes:

    - `to_lightning_module()` returns self (it IS the LightningModule)
    - `fit()` is invoked by `MLEngine.fit(..., family="huggingface", ...)`
      and terminates in `L.Trainer(...).fit(self, ...)` (Decision 8 compliant)
    - `configure_optimizers()` builds the AdamW + linear-warmup HF default
    - `training_step` / `validation_step` route through the underlying
      transformers model's forward + loss
    - `compute_metrics` hook emits to the ambient ExperimentRun via
      `run.log_metric(...)` per `ml-autolog-draft.md §3.1`

    Auto-logs via the autolog-transformers integration (`autolog-transformers`
    extra, Decision 13). Enables PEFT / LoRA when `peft_config=` is passed.
    """

    family_name: str = "huggingface"

    def __init__(
        self,
        model_name_or_path: str,
        task: Literal[
            "classification", "regression", "causal_lm", "seq2seq", "token_classification"
        ],
        *,
        peft_config: "peft.PeftConfig | None" = None,
        tokenizer_name: str | None = None,
        compute_metrics: callable | None = None,
        **hf_training_kwargs,
    ) -> None:
        super().__init__()
        self.save_hyperparameters(ignore=["peft_config", "compute_metrics"])
        self._model = self._load_hf_model(model_name_or_path, task, peft_config)
        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_name or model_name_or_path)
        self._compute_metrics = compute_metrics
        self._hf_kwargs = hf_training_kwargs

    # --- Lightning contract ---
    def forward(self, **batch):
        return self._model(**batch)

    def training_step(self, batch, batch_idx):
        out = self._model(**batch)
        self.log("train_loss", out.loss, prog_bar=True)
        return out.loss

    def validation_step(self, batch, batch_idx):
        out = self._model(**batch)
        self.log("val_loss", out.loss, prog_bar=True)
        if self._compute_metrics is not None:
            metrics = self._compute_metrics(out.logits, batch["labels"])
            for name, value in metrics.items():
                self.log(f"val_{name}", value)
        return out.loss

    def configure_optimizers(self):
        # AdamW + linear warmup per HF default — user overrides via hf_training_kwargs
        from transformers.optimization import AdamW, get_linear_schedule_with_warmup
        optimizer = AdamW(
            self._model.parameters(),
            lr=self._hf_kwargs.get("learning_rate", 5e-5),
            weight_decay=self._hf_kwargs.get("weight_decay", 0.01),
        )
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=self._hf_kwargs.get("warmup_steps", 0),
            num_training_steps=self._hf_kwargs.get("max_steps", 1000),
        )
        return {"optimizer": optimizer, "lr_scheduler": scheduler}

    # --- Trainable contract ---
    def to_lightning_module(self) -> L.LightningModule:
        return self  # Already IS a LightningModule

    def get_param_distribution(self) -> "HyperparameterSpace":
        # Default HF hyperparameter space — overridable via family registration
        from kailash_ml.hpo import HyperparameterSpace, Float, Int
        return HyperparameterSpace(params=[
            Float("learning_rate", low=1e-6, high=1e-3, log=True),
            Int("warmup_steps", low=0, high=1000),
            Float("weight_decay", low=0.0, high=0.1),
        ])

    @staticmethod
    def _load_hf_model(name_or_path, task, peft_config):
        task_to_autoclass = {
            "classification": transformers.AutoModelForSequenceClassification,
            "regression": transformers.AutoModelForSequenceClassification,
            "causal_lm": transformers.AutoModelForCausalLM,
            "seq2seq": transformers.AutoModelForSeq2SeqLM,
            "token_classification": transformers.AutoModelForTokenClassification,
        }
        model = task_to_autoclass[task].from_pretrained(name_or_path)
        if peft_config is not None:
            from peft import get_peft_model
            model = get_peft_model(model, peft_config)
        return model
```

Extras requirement: `[dl]` (torch + lightning + transformers + peft) — already declared above in MUST 6 extras block. `HuggingFaceTrainable` relies on the `peft>=0.10.0` pin inside `[dl]` for LoRA / QLoRA.

**BLOCKED rationalizations:**

- "Defer `HuggingFaceTrainable` to 1.1." — No: Round-3 industry-parity identified HF as a CRIT path for 1.0. Deferral would force every HF user onto raw `transformers.Trainer` (bypassing the engine contract) OR onto a third-party shim (bypassing the support contract).
- "Just document `transformers.Trainer` passthrough and skip the adapter." — No: passthrough bypasses MUST 5 (diagnostics auto-attach), MUST 6 (strategy passthrough), MUST 7 (checkpoint default), the tenant contract §5, and the tracker wiring in `ml-autolog-draft.md §3.1`. The adapter IS the contract.

**Why:** The v0.9.x audit found that 40%+ of DL production users run transformers-family models. A 1.0.0 release that ships without a first-class HF adapter ships a broken contract for half its intended audience. Shipping `HuggingFaceTrainable` in 1.0.0 is non-negotiable per Round-3 industry-parity + the Lightning lock-in (Decision 8).

**Regression test (release-blocking):** `tests/integration/test_huggingface_trainable_wiring.py`:

1. Instantiate `HuggingFaceTrainable(model_name_or_path="distilbert-base-uncased", task="classification")`.
2. `assert isinstance(hf, Trainable)` (runtime Protocol check).
3. `assert isinstance(hf.to_lightning_module(), L.LightningModule)` (Decision 8 compliance).
4. `isinstance(hf.get_param_distribution(), HyperparameterSpace)` (§3.2 MUST 3).
5. Fit on a toy classification dataset (10 rows, 1 epoch, CPU) inside `km.track("hf-test")` via `engine.fit(trainable=hf, hyperparameters={"max_steps": 2})`.
6. Assert the resulting `TrainingResult.family == "huggingface"` AND `result.lightning_trainer_config["callbacks"]` contains both a DLDiagnostics callback and a ModelCheckpoint callback (MUST 5 + MUST 7 auto-attach verified end-to-end).
7. Assert HF-native `compute_metrics` returned values were logged to the run (via `run.query_metrics("val_*")`).

Skip via `pytest.importorskip("transformers")` + `pytest.importorskip("lightning.pytorch")`.

---

## 4. `TrainingResult` Dataclass

`TrainingResult` is the single envelope every training path produces. Its fields are frozen contract; adding, renaming, or reordering fields is a spec amendment.

### 4.1 Definition

```python
from kailash_ml._device_report import DeviceReport

@dataclass(frozen=True)
class TrainingResult:
    # Required fields — every path MUST populate these
    model_uri: str                        # registry-relative URI, e.g. "models://User/v3"
    metrics: dict[str, float]             # {"accuracy": 0.92, "f1": 0.87, "auc": 0.94}
    device: DeviceReport                  # canonical source-of-truth for the device the run ran on
    elapsed_seconds: float                # wall-clock seconds for fit()
    tracker_run_id: str | None            # set when an ExperimentTracker was bound
    tenant_id: str | None                 # propagated from Engine; None in single-tenant mode
    artifact_uris: dict[str, str]         # {"onnx": "file://...", "pickle": "...", "weights": "..."}
    lightning_trainer_config: dict[str, Any]   # the L.Trainer kwargs that actually ran

    # Optional but recommended fields
    family: str | None = None             # "lightgbm", "lightning_mlp", etc.
    hyperparameters: dict | None = None   # actually-used HPs after HP search resolution
    split_info: SplitInfo | None = None   # which split strategy, seed, sizes
    calibration: CalibrationInfo | None = None
    feature_importance: dict[str, float] | None = None
    seed_report: SeedReport | None = None  # from km.seed() — see §11.2 MUST 2

    # BACK-COMPAT mirrors — populated automatically from `device`. Introduced 1.0.0;
    # REMOVED at 2.0.0. New code MUST read from `self.device`.
    device_used: str = field(init=False)   # == device.backend_name, e.g. "cuda:0", "mps", "cpu"
    accelerator: str = field(init=False)   # == device.family, e.g. "cuda", "mps", "cpu"
    precision: str = field(init=False)     # == device.precision, e.g. "bf16-mixed", "fp32"

    def __post_init__(self) -> None:
        # `frozen=True` blocks normal assignment; object.__setattr__ is the documented escape.
        object.__setattr__(self, "device_used", self.device.backend_name)
        object.__setattr__(self, "accelerator", self.device.family)
        object.__setattr__(self, "precision", self.device.precision)
```

**Why this shape:** Earlier drafts declared `device_used: str`, `accelerator: str`, and `precision: str` as three independent top-level string fields. Round-3 cross-spec sweep found that `ml-rl-core.md`, `ml-rl-algorithms.md`, `ml-tracking.md §4.6`, and `ml-rl-align-unification.md` already treat `result.device: DeviceReport` as the source of truth. The canonical shape unifies both worlds: `device: DeviceReport` is the new source of truth; `device_used` / `accelerator` / `precision` are automatically-populated read-only mirrors for 1.x back-compat and are removed at 2.0.0. Every path that returned `TrainingResult(..., device_used="cuda:0", accelerator="cuda", precision="bf16-mixed")` pre-round-3 MUST be updated to `TrainingResult(..., device=DeviceReport(backend_name="cuda:0", family="cuda", precision="bf16-mixed", ...))`. Reads of `result.device_used` continue to work unchanged across 1.x.

### 4.2 MUST Rules

#### 1. Every Training Path MUST Populate All Required Fields

Every code path that produces a `TrainingResult` MUST populate all eight required fields (`model_uri`, `metrics`, `device`, `elapsed_seconds`, `tracker_run_id`, `tenant_id`, `artifact_uris`, `lightning_trainer_config`). Leaving a required field as `None` is BLOCKED; the path MUST raise rather than return a partially-populated result. The back-compat mirrors (`device_used` / `accelerator` / `precision`) populate themselves from `device` via `__post_init__` and do NOT require explicit initialization.

```python
# DO — raise when a required field cannot be populated
result = trainable.fit(data, hyperparameters=hp, context=ctx)
if result.device is None:
    raise IncompleteTrainingResultError(
        "device not populated — Trainable must resolve DeviceReport from context.accelerator"
    )

# DO — supply DeviceReport; mirrors auto-populate
return TrainingResult(
    model_uri=uri, metrics=metrics,
    device=DeviceReport(
        backend_name="cuda:0", family="cuda", precision="bf16-mixed",
        vram_bytes=24 * 1024**3, compute_capability=(9, 0),
    ),
    elapsed_seconds=t, tracker_run_id=run_id, tenant_id=tenant_id,
    artifact_uris={"onnx": "...", "weights": "..."},
    lightning_trainer_config={...},
)
# ↑ Reading result.device_used / result.accelerator / result.precision is free.

# DO NOT — emit a half-populated TrainingResult and continue
return TrainingResult(
    model_uri=uri, metrics=metrics,
    device=None,               # BLOCKED — downstream assumes this is populated
    elapsed_seconds=t, tracker_run_id=None, tenant_id=None,
    artifact_uris={}, lightning_trainer_config={},
)
```

**Why:** `device` being None silently turns `km.train(df)` into a debugging ordeal: the user sees training completed but cannot tell whether their GPU was actually used. The v0.9.x release shipped without this field entirely, which is exactly the bug class this rule prevents. The `DeviceReport`-as-source-of-truth shape ensures `backend_name`, `family`, and `precision` cannot drift apart (previously three independent string fields could disagree).

#### 2. `lightning_trainer_config` MUST Be The Literal `L.Trainer` Kwargs That Ran

The `lightning_trainer_config` dict MUST capture the exact keyword arguments passed to `lightning.pytorch.Trainer(...)` for this run — not the Engine's resolved-but-not-yet-passed config, not the user's request, but the actual kwargs.

```python
# DO — capture what L.Trainer received
trainer_kwargs = {
    "accelerator": resolved_accelerator,  # e.g. "cuda"
    "devices": resolved_devices,          # e.g. [0]
    "precision": resolved_precision,      # e.g. "bf16-mixed"
    "max_epochs": 20,
    "callbacks": [...],
}
trainer = L.Trainer(**trainer_kwargs)
trainer.fit(module, loader)
return TrainingResult(..., lightning_trainer_config=trainer_kwargs)

# DO NOT — store the user's request, which may differ from what ran
return TrainingResult(..., lightning_trainer_config={"accelerator": "auto"})
```

**Why:** Reproducibility. "Why did my training take 4h on this machine but 40min on the reference?" requires the exact Trainer kwargs — not the user's `auto` intent.

#### 3. `tenant_id` MUST Echo The Engine's Tenant Context

`TrainingResult.tenant_id` MUST equal `engine.tenant_id` at the moment `fit()` was called. It MUST NOT be `None` when `engine.tenant_id` is set, and MUST NOT be a literal string when `engine.tenant_id` is None.

**Why:** Post-hoc audit queries rely on `tenant_id` on every TrainingResult to filter per-tenant training history. A missing or wrong `tenant_id` orphans the audit row (see `rules/tenant-isolation.md` Rule 5).

#### 4. `artifact_uris["onnx"]` MUST Be Present After Successful `register(format="onnx" | "both")`

When the Engine's `register()` is called with `format="onnx"` (default) or `format="both"`, the returned `RegisterResult.artifact_uris` MUST contain `"onnx"`. If ONNX export failed, `register()` MUST raise `OnnxExportError` — silently returning without ONNX is BLOCKED.

**Why:** See §6. "ONNX export failed, falling back to pickle" without a raised error is the v0.9.x bug pattern where the compatibility matrix claimed xgboost support but the code had no xgboost branch.

---

## 5. Multi-Tenancy

Every store, registry, tracker, and monitor in kailash-ml MUST be tenant-aware. This clause is the ML-specific form of `rules/tenant-isolation.md` and inherits its full contract.

### 5.1 MUST Rules

#### 1. Every Primitive Constructor MUST Accept `tenant_id`

`FeatureStore`, `ModelRegistry`, `ExperimentTracker`, `DriftMonitor`, and `InferenceServer` MUST all accept `tenant_id: str | None` as a constructor kwarg. The Engine MUST propagate its `tenant_id` into every primitive it constructs.

```python
# DO — tenant propagated through the Engine
engine = km.Engine(store=url, tenant_id="acme")
# engine._registry.tenant_id == "acme"
# engine._feature_store.tenant_id == "acme"
# engine._tracker.tenant_id == "acme"

# DO NOT — primitive without tenant awareness
fs = FeatureStore(conn)  # no tenant_id accepted
```

**Why:** A primitive without a tenant dimension leaks across tenants the moment two customers share an ID (see `rules/tenant-isolation.md` Rule 1). Constructor-time acceptance is the simplest enforcement: if the kwarg doesn't exist, the bug shows up at import time.

#### 2. Cache Key Shape MUST Be `kailash_ml:v1:{tenant_id}:{resource}:{id}`

Every cache key (feature cache, model cache, inference cache, tracker cache) MUST use the literal shape:

```
kailash_ml:v1:{tenant_id}:{resource}:{id}
```

where `{tenant_id}` is either the resolved tenant string or the literal `"_single"` for single-tenant mode per `ml-tracking.md §7.2`. The strings `"default"` and `"global"` are BLOCKED.

```python
# DO — "_single" for the unambiguous single-tenant namespace (canonical across all engines)
key = f"kailash_ml:v1:_single:model:User:v3"

# DO NOT — "default" (silent cross-tenant merge per rules/tenant-isolation.md)
key = f"kailash_ml:v1:default:model:User:v3"

# DO NOT — "global" (cross-spec drift; ml-tracking.md is authority)
key = f"kailash_ml:v1:global:model:User:v3"
```

**Why:** `rules/tenant-isolation.md` MUST Rule 2 blocks "default" as a silent fallback. `"_single"` is the canonical sentinel per `ml-tracking.md §7.2` — using `"global"` here and `"_single"` there would break cross-engine JOINs on `tenant_id` for every single-tenant user.

#### 3. Missing `tenant_id` On A Multi-Tenant Primitive MUST Raise `TenantRequiredError`

When a primitive is constructed in multi-tenant mode (i.e. the Engine's `tenant_id` is set) and an operation is called without tenant context (e.g. a reader passes `tenant_id=None`), it MUST raise `TenantRequiredError`. Silent fallback is BLOCKED.

```python
# DO — strict typed error
async def read(self, model_name, record_id, *, tenant_id=None):
    if self._multi_tenant and tenant_id is None:
        raise TenantRequiredError(
            f"ModelRegistry is multi-tenant; tenant_id is required for read('{model_name}')"
        )

# DO NOT — silent fallback to engine default or "global"
async def read(self, model_name, record_id, *, tenant_id=None):
    tenant_id = tenant_id or self.default_tenant  # merges every multi-tenant read
```

**Why:** Defaulting to a tenant silently cross-contaminates the cache / the registry / the audit trail. The v0.9.x ModelRegistry had no tenant dimension at all; two DataFlow multi-tenant deployments that trained a "User" classifier would share the same ModelVersion table.

#### 4. `register()` MUST Persist `tenant_id` On The Model Version Row

`ModelRegistry.register_model()` MUST persist `tenant_id` as a column on the `_kml_model_versions` row and index it. `tenant_id` is part of the registry primary key scope: `(tenant_id, name, version)` is unique, not `(name, version)`.

**Why:** A post-incident query "which models did tenant X promote to production in the last 30 days" must be answerable without a full-table scan. See `rules/tenant-isolation.md` Rule 5.

#### 5. Invalidation MUST Accept Optional `tenant_id`

Every invalidation entry point — `feature_store.invalidate(schema_name)`, `registry.invalidate(model_name)`, `inference_server.invalidate(model_name)` — MUST accept `tenant_id: str | None` and restrict the invalidation to that tenant's keys.

```python
# DO — tenant-scoped invalidation
await engine.feature_store.invalidate("user_features", tenant_id="acme")
# Matches kailash_ml:v1:acme:feature:user_features:*
# Leaves kailash_ml:v1:bob:feature:user_features:* untouched

# DO NOT — invalidation that nukes every tenant
await engine.feature_store.invalidate("user_features")
# Matches kailash_ml:v1:*:feature:user_features:*
```

**Why:** Without tenant-scoped invalidation, one tenant's cache-bust event (password rotation, schema evolution, re-train) clears every other tenant's cache and forces a thundering-herd rebuild across the platform.

### 5.2 Audit Row Contract

Every audit row written by a kailash-ml primitive MUST include:

- `tenant_id` (indexed, nullable only when single-tenant)
- `actor_id` (user or agent id that invoked the op)
- `model_uri` (when applicable)
- `operation` ("train" | "register" | "promote" | "predict" | "drift_check")
- `occurred_at` (timestamp)
- `duration_ms`
- `outcome` ("success" | "failed")

---

## 6. ONNX-Default Artifacts

`MLEngine.register()` defaults to ONNX export. This clause defines the compatibility matrix, every matrix entry's implementation contract, and the round-trip regression test requirement.

### 6.1 MUST Rules

#### 1. `register()` Default Format MUST Be `"onnx"`

```python
# DO — the default
reg_result = await engine.register(training_result)
assert "onnx" in reg_result.artifact_uris

# DO NOT — pickle as default
reg_result = await engine.register(training_result, format="pickle")  # opt-in only
```

**Why:** Pickle-default locks the user into Python-only serving. ONNX-default opens kailash-rs, browser-based inference (onnxruntime-web), and edge deployment (onnxruntime-node) without a re-export step.

#### 2. ONNX Compatibility Matrix Keys MUST Each Have An Implemented Branch

Every key in the published compatibility matrix MUST have a branch in `kailash_ml.bridge.onnx_bridge.export()` that produces a valid ONNX artifact. Matrix keys without branches (documentation-only claims) are BLOCKED.

| Framework | Confidence  | Converter                  | Implemented Branch |
| --------- | ----------- | -------------------------- | ------------------ |
| sklearn   | guaranteed  | `skl2onnx`                 | REQUIRED           |
| xgboost   | guaranteed  | `onnxmltools`              | REQUIRED           |
| lightgbm  | guaranteed  | `onnxmltools`              | REQUIRED           |
| catboost  | guaranteed  | `catboost.save_model(...)` | REQUIRED           |
| torch     | best_effort | `torch.onnx.export`        | REQUIRED           |
| lightning | guaranteed  | via `to_torchscript` path  | REQUIRED           |

**Why:** The v0.9.x spec claimed `xgboost=guaranteed` but the code's xgboost branch raised `NotImplementedError`. Claims that the implementation doesn't back are worse than missing entries — they break user expectations silently at deployment time.

#### 3. Every Matrix Entry MUST Have A Tier 2 Round-Trip Regression Test

For each framework key, a Tier 2 integration test in `tests/integration/test_onnx_roundtrip_{framework}.py` MUST:

1. Train a minimal model on real infrastructure.
2. Export via `engine.register(format="onnx")`.
3. Load the ONNX artifact via `onnxruntime.InferenceSession`.
4. Run prediction on a held-out sample.
5. Assert `max_abs_diff` between native and ONNX predictions is `<= 1e-4`.

```python
@pytest.mark.integration
async def test_onnx_roundtrip_xgboost(test_suite):
    engine = km.Engine(store=test_suite.url)
    setup = await engine.setup(iris_df, target="species")
    train = await engine.fit(family="xgboost")
    reg = await engine.register(train, format="onnx")
    # Round-trip assertion
    session = onnxruntime.InferenceSession(reg.artifact_uris["onnx"])
    X_sample = test_suite.sample_features()
    onnx_pred = session.run(None, {"input": X_sample.astype(np.float32)})[0]
    native_pred = train.trainable.predict(X_sample)
    assert np.max(np.abs(onnx_pred - native_pred)) < 1e-4
```

**Why:** Documented compatibility without a test is a claim the next refactor will silently break. A regression test per matrix key converts the matrix into a truth contract.

#### 4. ONNX Export Failure On Default Path MUST Raise `OnnxExportError`

When `register(format="onnx")` (the default) fails, the Engine MUST raise `OnnxExportError` with framework and root cause. Silently falling back to pickle under the default is BLOCKED.

```python
# DO — raise on default-path failure
if format == "onnx" and export_result.status == "failed":
    raise OnnxExportError(
        framework=training_result.family,
        cause=export_result.error_message,
        hint="Pass format='pickle' to opt out of ONNX requirement.",
    )

# DO NOT — silent fallback to pickle
if export_result.status == "failed":
    return RegisterResult(..., artifact_uris={"pickle": pickle_uri})  # user doesn't know
```

**BLOCKED rationalizations:**

- "ONNX export is best-effort, fallback is polite"
- "The user can check `artifact_uris` if they care"
- "We don't want to break working workflows on upgrade"

**Why:** "Fell back to pickle" without loud failure is indistinguishable from "exported to ONNX" at the API surface, which is why users of v0.9.x ran deployments for months on pickle-only artifacts and discovered it only at Rust-side serving time.

#### 5. `format="both"` Accepts Partial ONNX Failure; `format="onnx"` Does Not

`register(format="both")` MAY return a `RegisterResult` with only a pickle artifact if ONNX export failed. `register(format="onnx")` (default) MUST raise on failure. `register(format="pickle")` MUST NOT attempt ONNX.

**Why:** `both` is the explicit "I want both or either." `onnx` is the explicit "ONNX is non-negotiable." `pickle` is the explicit opt-out. Each matches its literal name.

---

## 7. PyCaret/MLflow-Better Claims

Every capability in this section is a MUST clause backed by a named integration test. Claims without tests are BLOCKED.

### 7.1 MUST Rules

#### 1. `engine.serve()` MUST Support REST + MCP + gRPC From One Call

See §2.1 MUST 10 and `ml-serving.md` § Multi-Channel Serving. Integration test: `test_serve_rest_mcp_grpc_from_one_call`.

**Why (delta vs competitors):** MLflow offers REST model-serving via `mlflow models serve` but has no MCP channel; a user who wants to expose their model to LLM agents must write a separate FastMCP server. `engine.serve(channels=["rest", "mcp"])` collapses this into one call.

#### 2. Every User-Facing DataFrame Parameter MUST Accept `polars.DataFrame`

`setup(data=...)`, `fit(data=...)`, `predict(features=...)`, `evaluate(data=...)` MUST accept `pl.DataFrame` / `pl.LazyFrame` as the primary input. Pandas MUST be accepted via `interop.to_pandas_if_needed()` but converted at the boundary — no pandas survives into engine internals. Integration test: `test_polars_native_end_to_end`.

**Why (delta vs competitors):** MLflow and PyCaret default to `pandas.DataFrame`. Polars-native means zero-copy from DataFlow's native format, larger-than-memory lazy pipelines via `LazyFrame`, and 3-5x speedup on the typical feature-store read.

#### 3. ONNX Default Artifact Format

See §6. Integration tests: `test_onnx_roundtrip_{sklearn,xgboost,lightgbm,catboost,torch,lightning}`.

**Why (delta vs competitors):** MLflow's default is pickle via `mlflow.sklearn.log_model`. Recovering ONNX from an MLflow pickle run is a manual post-processing step that most deployments skip.

#### 4. Unified ML + DL + RL Surface

`MLEngine` MUST train every task type through the same eight-method contract (§2.1 MUST 5). Classification, regression, clustering, deep learning, and RL flow through `fit()` with different `family` arguments or `Trainable` adapters. Integration tests: `test_mlengine_trains_classical_via_lightgbm`, `test_mlengine_trains_dl_via_lightning_mlp`, `test_mlengine_trains_rl_via_grpo_adapter`.

**Why (delta vs competitors):** PyCaret has no DL primitive (requires a separate `pycaret.nlp` / `pycaret.classification` split). MLflow has no unified training surface (`mlflow.pyfunc` is a model wrapper, not a trainer).

#### 5. Async `ExperimentTracker`

`ExperimentTracker` MUST expose async-native entry points (`log_metric`, `log_params`, `run` context manager). See `ml-tracking.md` for the full contract. Integration test: `test_tracker_async_nested_runs`.

**Why (delta vs competitors):** MLflow's client is sync-only; every async training loop must wrap logging calls in `asyncio.to_thread` or serialize them through a single flush thread. PyCaret has no experiment-tracking primitive at all.

#### 6. Schema Evolution Helpers

`FeatureStore` MUST expose `evolve(name, add=[...], drop=[...], rename={...})` that produces a new schema version and emits a migration plan without requiring the user to hand-edit the schema. See `ml-feature-store.md` § Schema Evolution. Integration test: `test_feature_store_evolve_adds_column`.

**Why (delta vs competitors):** PyCaret has no feature store at all. MLflow's feature store integration (with Databricks) requires a full table rewrite for every schema change.

#### 7. MCP-Native Experiment Query

`ExperimentTracker` MUST register an MCP tool (`ml.experiments.search`, `ml.runs.get`, `ml.runs.compare`) when `engine.serve()` is called with `channels=["mcp"]`. Integration test: `test_mcp_tools_query_experiments`.

**Why (delta vs competitors):** MLflow surfaces experiments via REST and the MLflow UI. Exposing experiments as MCP tools lets Kaizen agents query their own training history without glue code.

### 7.2 Claim-to-Test Mapping

| Claim                       | Integration Test File                                                     |
| --------------------------- | ------------------------------------------------------------------------- |
| Multi-channel serve         | `tests/integration/test_serve_multichannel.py`                            |
| Polars-native pipelines     | `tests/integration/test_polars_native_pipeline.py`                        |
| ONNX-default artifacts      | `tests/integration/test_onnx_roundtrip_{sklearn,xgboost,lightgbm,...}.py` |
| Unified ML/DL/RL            | `tests/integration/test_unified_surface.py`                               |
| Async tracker               | `tests/integration/test_tracker_async.py`                                 |
| Schema evolution            | `tests/integration/test_feature_store_evolve.py`                          |
| MCP-native experiment query | `tests/integration/test_mcp_experiment_tools.py`                          |

---

## 8. Migration Compatibility

kailash-ml 1.0.0 replaces the v0.9.x 18-class public surface. Existing consumers (aegis, aether, kz-engage) depend on direct primitive imports. This section defines the deprecation contract.

### 8.1 MUST Rules

#### 1. `kailash_ml.legacy.*` MUST Exist For Every Removed Top-Level Public Symbol

Every v0.9.x public symbol that is demoted or removed in 2.0 MUST remain importable from `kailash_ml.legacy.*` for the entire 2.x series (removable at 3.0).

```python
# DO — v1.x callers still work against 2.0
from kailash_ml.legacy import EnsembleEngine, ClusteringEngine, PreprocessingPipeline  # 1.x shape (demoted names)

# DO — v2.0 canonical imports (demoted symbols renamed; first-class engines unchanged)
from kailash_ml import Engine, Ensemble, Clustering, Preprocessing  # 2.0 renames
from kailash_ml import AutoMLEngine, TrainingPipeline, HyperparameterSearch  # first-class, name unchanged

# DO NOT — delete v1.x symbols at 2.0 with no shim
# (aegis / aether / kz-engage break at pip install kailash-ml==2.0)
```

**Why:** Three in-repo consumers import the 1.x shape today. A hard break at 2.0 forces three parallel workspace migrations before any 2.0 bug can land. The legacy namespace is the wedge that lets 2.0 ship and migrations happen in parallel.

#### 2. Every `kailash_ml.legacy.*` Import MUST Emit A `DeprecationWarning` On First Use

```python
# DO — first-use deprecation
import warnings

class _LegacyFeatureStore(FeatureStore):
    _warned = False
    def __init__(self, *a, **kw):
        if not type(self)._warned:
            warnings.warn(
                "kailash_ml.legacy.FeatureStore is deprecated; migrate to "
                "kailash_ml.FeatureStore (2.0) or kailash_ml.Engine.feature_store. "
                "Legacy namespace will be removed in kailash-ml 3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            type(self)._warned = True
        super().__init__(*a, **kw)
```

**Why:** Silent re-exports are the v0.9.x "this works today, breaks on the next refactor" failure mode. A first-use `DeprecationWarning` both signals to downstream devs AND surfaces in CI as a warning that can be audited against `rules/zero-tolerance.md` Rule 1.

#### 3. `kailash_ml.legacy.*` Removal Is Gated On 3.0

The legacy namespace MUST NOT be removed in any 2.x release. Removal happens at 3.0 and MUST be announced one minor release in advance (2.N with removal planned for 3.0 MUST set `PendingDeprecationWarning` → `DeprecationWarning` at 2.N-1).

**Why:** Three-repo downstream migration cannot complete in one session; "next patch release we'll drop the legacy ns" is the kind of break that teaches users not to upgrade kailash-ml.

### 8.2 Demoted Symbols

The v0.9.x public symbols that are demoted to `kailash_ml.legacy.*` (and promoted callers MUST migrate to the 2.0 equivalents):

| v0.9.x import                                   | v2.0 equivalent               |
| ----------------------------------------------- | ----------------------------- |
| `from kailash_ml import EnsembleEngine`         | `kailash_ml.Ensemble`         |
| `from kailash_ml import ClusteringEngine`       | `kailash_ml.Clustering`       |
| `from kailash_ml import AnomalyDetectionEngine` | `kailash_ml.AnomalyDetection` |
| `from kailash_ml import DimReductionEngine`     | `kailash_ml.DimReduction`     |
| `from kailash_ml import PreprocessingPipeline`  | `kailash_ml.Preprocessing`    |
| `from kailash_ml import DataExplorer`           | `kailash_ml.DataExplorer`     |
| `from kailash_ml import ModelVisualizer`        | `kailash_ml.ModelVisualizer`  |
| `from kailash_ml import ModelExplainer`         | `kailash_ml.ModelExplainer`   |
| `from kailash_ml import FeatureEngineer`        | `kailash_ml.FeatureEngineer`  |

Note: The v0.9.x demotion is NAME-space only — these engines remain first-class citizens in the 1.0.0 engine matrix (per `ml-engines-v2-addendum §E1.1`). The old import path raises `DeprecationWarning` pointing at the new top-level symbol; no engine is dropped.

### 8.3 Preserved / First-Class Symbols

These symbols are first-class citizens at the top level (no `legacy.` prefix needed). Every engine below appears in the authoritative `ml-engines-v2-addendum §E1.1` Engine Coverage Matrix — the 18-engine set that defines the 1.0.0 API surface:

- **Core lifecycle engines:** `MLEngine` (facade), `TrainingPipeline`, `ExperimentTracker`, `ModelRegistry`, `FeatureStore`, `InferenceServer`, `DriftMonitor` — all retained as first-class engines.
- **AutoML / search engines (first-class in 1.0.0):** `AutoMLEngine`, `HyperparameterSearch`, `Ensemble` — per `ml-automl-draft.md §2.1` these are top-level primitives exposed through `MLEngine` AND directly constructible; they are NOT demoted.
- **Support engines (first-class in 1.0.0):** `Preprocessing`, `FeatureEngineer`, `ModelExplainer`, `DataExplorer`, `ModelVisualizer`, `Clustering`, `AnomalyDetection`, `DimReduction` — each surfaced as a top-level import AND wrapped by an `MLEngine` method.
- `FeatureSchema`, `FeatureField`, `ModelSignature`, `MetricSpec` — shared type contracts.
- `rl.Engine` — new in 1.0.0.

**Anti-contradiction clause:** Nothing in §8.2 demotes `AutoMLEngine`, `TrainingPipeline`, or `HyperparameterSearch` — those three were moved out of the demoted list in the 1.0.0 draft because they are first-class engines per the authoritative §E1.1 matrix. A future PR that attempts to re-add any of them to §8.2 is a spec violation.

---

## 9. Layered Hierarchy

Per `rules/framework-first.md`, kailash-ml in 2.0 fits the four-layer hierarchy as follows.

### 9.1 Layer Assignment

```
Entrypoints  →  aegis, aether, kz-engage, user scripts, notebooks
Engine       →  MLEngine (default path)
Primitives   →  FeatureStore, ModelRegistry, ExperimentTracker, InferenceServer,
                DriftMonitor, rl.Engine, Trainable implementations
Raw          →  direct sklearn/torch/lightning fit loops — BLOCKED in production
```

### 9.2 MUST Rules

#### 1. Production Code MUST Default To `MLEngine`; Primitives Require A Written Reason

User-facing documentation, README examples, and `/analyze` output templates MUST reach for `MLEngine` first. Dropping to a Primitive requires a comment referencing the specific Engine limitation:

```python
# DO — Engine by default
engine = km.Engine(store="postgresql://...")
result = await engine.fit(family="lightgbm")

# DO — Primitive with justification
# Engine path doesn't support custom cross-validation callbacks.
# See ml-engines.md §9.2 MUST 1 — dropping to TrainingPipeline intentionally.
tp = TrainingPipeline(feature_store, registry)
```

**Why:** Without this default, "primitives are easier" becomes the default answer and the Engine becomes dead code. v0.9.x had the primitives; it had no Engine layer at all. That's why the user described it as "devs hunt for API."

#### 2. Direct sklearn / torch / lightning Training Loops In Production Code Are BLOCKED

Production modules under `src/`, `packages/`, and `workspaces/*/` (except `workspaces/*/notebooks/`) MUST NOT contain:

- `model.fit(X, y)` against a raw sklearn model outside a `Trainable` implementation
- `for epoch in range(...)` with `torch.optim` stepping
- `L.Trainer(...).fit(...)` not wrapped in a `Trainable`

Notebook and research code (`workspaces/*/notebooks/`, `examples/research/`) is exempt.

**Why:** Raw loops reintroduce the device-management split-brain (§3 MUST 2). The Engine + Trainable contract is the single enforcement point for accelerator resolution; bypassing it re-opens the bug class `rules/orphan-detection.md` and `rules/facade-manager-detection.md` are meant to close.

---

## 10. Cross-SDK Alignment (Python + Rust)

This spec is implemented independently by kailash-py and kailash-rs per EATP D6 (independent implementations, matching semantics). Clauses below designate which parts are shared verbatim, which have language-specific translations, and which are Python-only.

### 10.1 Shared Clauses (Verbatim)

These clauses MUST be implemented identically in both SDKs:

- **§4 `TrainingResult` fields** — the dataclass fields are the wire contract; a Python-trained model registered from kailash-py MUST be loadable by a kailash-rs registry reader.
- **§5 Multi-tenancy** — cache key shape `kailash_ml:v1:{tenant_id}:{resource}:{id}` is a cross-SDK key, not a Python quoting quirk.
- **§6 ONNX compatibility matrix** — the ONNX artifact produced by the Python branch for `sklearn` / `xgboost` / `lightgbm` MUST be loadable by kailash-rs via `tract-onnx` or `ort`.
- **§8 Legacy namespace** — the Rust SDK inherits an analogous `kailash_ml::legacy` namespace for symbols demoted in its own 2.0.
- **§9 Layered hierarchy** — "Engine is default, Primitives are opt-out" is a cross-SDK architectural stance.

### 10.2 Language-Specific Translations

These clauses MUST be implemented with language-specific substitutions, semantics preserved:

| Clause                  | Python (kailash-py)                              | Rust (kailash-rs)                        |
| ----------------------- | ------------------------------------------------ | ---------------------------------------- |
| §2 Engine facade        | `kailash_ml.Engine`                              | `kailash_ml::Engine` struct              |
| §3 `Trainable` protocol | Python `Protocol` + `@runtime_checkable`         | Rust `trait Trainable`                   |
| Lightning Trainer spine | `lightning.pytorch.Trainer`                      | `burn::Trainer` or `tch::train::Trainer` |
| ONNX export             | `skl2onnx` / `onnxmltools` / `torch.onnx.export` | `tract-onnx` / `ort` export              |
| MCP server              | `fastmcp` (Python)                               | `mcp-rs` crate                           |
| Async runtime           | asyncio / async-context-managers                 | tokio / async-trait                      |

### 10.3 Python-Only Clauses

These clauses MUST exist only in the Python spec; Rust SDK does not carry them:

- **§7.1 MUST 2** — polars-native with pandas interop (Rust already owns polars via `polars-rs`; there's no pandas equivalent).
- **§7.1 MUST 4 — PyCaret-better DX** — the "PyCaret-better" delta is a Python-ecosystem claim; Rust has no equivalent target. The Rust SDK's §7 narrows to "MLflow-better tracking registry semantics from Rust" (per the audit §8 delta).

### 10.4 RESOLVED DECISIONS (from 2026-04-21 approval)

The audit proposal §10 flagged six decisions. All six are now RESOLVED per `workspaces/kailash-ml-audit/04-validate/approved-decisions.md`:

1. **Default backend priority order** — RESOLVED: lock the order. `cuda → mps → rocm → xpu → tpu → cpu`. XPU path accepts both `torch.xpu.is_available()` native AND `intel_extension_for_pytorch` fallback (Decision 5). Not user-configurable at 1.0.0.
2. **Lightning hard lock-in** — RESOLVED: **BLOCKED with no exception** (Decision 8). No `RawTrainer` escape hatch. Raw training loops raise `UnsupportedTrainerError(MLError)` at Engine dispatch time (§3.2 MUST 2). RL path uses SB3 as its analogous substrate and is not subject to the Lightning lock-in (see `ml-rl-core-draft.md §2.3`).
3. **`ExperimentTracker` protocol surface in Rust** — RESOLVED: Python uses `async with run:` context manager (idiomatic); Rust uses explicit `start_run()` / `end_run()` (AsyncDrop not stable). Same observable behavior; different syntactic surface per language idiom (Decision 9).
4. **`engine.serve(channels=["grpc"])` scope** — deferred to `ml-serving.md` draft (unchanged).
5. **Single-spec vs split-spec for cross-SDK** — RESOLVED: one canonical spec per domain. Rust-specific clauses (when divergent) live in `loom/.claude/variants/rs/specs/ml-*.md` overlay once `/sync` lands. Do NOT pre-split (Decision 10).
6. **Legacy namespace sunset** — RESOLVED: remove at `kailash-ml 3.0`. `kailash-ml 2.x` emits `DeprecationWarning`; `kailash-ml 1.x` keeps back-compat shim (Decision 11).

---

## 11. Reproducibility — `km.seed()` Global Surface

kailash-ml MUST expose a single call-site that seeds every source of non-determinism the framework touches. Local `seed=` kwargs on individual primitives (`TrainingPipeline.setup(seed=42)`, `RLTrainingConfig(seed=42)`, drift sub-sampling `seed=42`) remain — but they inherit from the global when not explicitly set.

### 11.1 API

`seed()` is a **module-level function** defined in `kailash_ml/__init__.py` (NOT a method on any class). Users access it via `km.seed(...)` when they import the package as `import kailash_ml as km` — the `km.seed` form is the idiomatic call site, but the canonical declaration is the module-level `kailash_ml.seed` function. Earlier drafts wrote `def km.seed(...)` which is syntactically invalid Python.

```python
# In kailash_ml/__init__.py
def seed(
    seed: int,
    *,
    torch: bool = True,
    numpy: bool = True,
    random: bool = True,
    cudnn_deterministic: bool = True,
    cudnn_benchmark: bool = False,
    use_deterministic_algorithms: bool = False,
) -> SeedReport:
    """Seed every RNG kailash-ml touches and return the report.

    Propagates through:
      * Python stdlib `random`
      * `numpy.random`
      * `torch.manual_seed` + `torch.cuda.manual_seed_all`
      * `torch.backends.cudnn.deterministic` + `.benchmark`
      * `torch.use_deterministic_algorithms` (when True)
      * `gymnasium` env-seed (via contextvar, consumed at env.reset)
      * HF `accelerate.utils.set_seed` if accelerate is installed
      * Kailash-ml contextvar `_current_seed` read by every primitive
        (FeatureStore.ingest sub-sample, DriftMonitor.set_reference
        sub-sample, TrainingPipeline split, RL env seed, AutoML trial
        seeding, ExperimentTracker.run_id salt).
    """

@dataclass(frozen=True)
class SeedReport:
    seed: int
    torch_seeded: bool
    numpy_seeded: bool
    random_seeded: bool
    cudnn_deterministic: bool
    cudnn_benchmark: bool
    use_deterministic_algorithms: bool
    platform_python: str                # sys.version
    platform_torch: str | None          # torch.__version__
    platform_numpy: str                 # numpy.__version__
    platform_polars: str                # polars.__version__
    platform_cuda: str | None           # torch.version.cuda
    platform_cudnn: int | None          # torch.backends.cudnn.version()
    blas_backend: str | None            # "openblas" | "mkl" | "accelerate" | None
```

### 11.2 MUST Rules

#### 1. Seed Propagation Uses A Contextvar

`km.seed()` MUST set a module-level `contextvars.ContextVar[int]("_current_seed")`. Every primitive that consumes a seed MUST read this contextvar as the default when no explicit `seed=` kwarg is passed.

**Why:** An import-time global mutates every concurrent caller; a contextvar isolates seed state per task / per request and still propagates transparently across `await` boundaries.

#### 2. `TrainingResult` MUST Carry `seed_report`

The `TrainingResult` dataclass (§4) gains `seed_report: SeedReport | None = None` (optional for back-compat but every primitive that consumed a seed MUST populate it). A training run that claims reproducibility without a `seed_report` is BLOCKED from promotion to `production` in ModelRegistry (see `ml-registry.md` §3).

**Why:** A reviewer asking "what seed ran this model" is answered in one lookup, not by grepping scattered HP dicts.

#### 3. `cudnn.benchmark=True` + Fixed Seed Emits WARN

When `km.seed(seed=42, cudnn_benchmark=True)` is called, kailash-ml MUST emit a WARN log: "cudnn.benchmark=True combined with fixed seed=42 — run-to-run variance IS expected from autotuner kernel selection; reproducibility is not bit-level". The combination is legal (benchmark=True often wins ~15% throughput) but the claim "I have a fixed seed therefore my run is reproducible" is not true under it.

**Why:** cuDNN's autotuner picks different kernels across runs at the same seed. Users who expect bit-reproducibility need both `deterministic=True` AND `benchmark=False`.

#### 4. `use_deterministic_algorithms=True` Documents The Cost

When `use_deterministic_algorithms=True`, kailash-ml MUST log at INFO: "torch.use_deterministic_algorithms(True) disables scatter-add / non-deterministic conv / upsample_bilinear2d backward — expect up to 20% slowdown and some ops to raise". This is opt-in only.

**Why:** Flipping this globally without opt-in silently breaks `nn.Embedding` scatter-add in recommender models.

#### 5. BLAS Backend Captured In SeedReport

`SeedReport.blas_backend` MUST be populated by probing `numpy.show_config()` for one of `"openblas"`, `"mkl"`, `"accelerate"`, or `None`. OpenBLAS vs MKL changes sum-of-product order and produces 1-ULP float drift on 1B-row aggregates — the seed alone is not enough.

**Why:** Reproducibility across dev machines (MKL-by-default Anaconda) and CI containers (OpenBLAS-by-default pip) drifts at the 1-ULP level without the BLAS axis.

### 11.3 Related Primitives

- Feature store hash MUST include `polars.__version__`, `numpy.__version__`, and the BLAS backend marker (see `ml-feature-store.md` §1).
- RL env + policy + replay-buffer RNG state checkpointed as `env_rng_state`, `policy_rng_state`, `buffer_rng_state` — see `ml-rl-core.md` §9 for the three-RNG contract.
- AutoML trial-seed derivation MUST be deterministic: `trial_seed_k = sha256(f"{global_seed}:{trial_index}").digest()[:8]` (int64).
- ExperimentTracker run_id salt derived from the global seed so "which run was seed=42" is answerable.

---

## 12. `km.reproduce(run_id)` — One-Command Reproduction

`reproduce()` is a **module-level async function** defined in `kailash_ml/__init__.py` (NOT a method on any class). Users access it via `km.reproduce(...)` when they import the package as `import kailash_ml as km` — the `km.reproduce` form is the idiomatic call site, but the canonical declaration is the module-level `kailash_ml.reproduce` function. Earlier drafts wrote `async def km.reproduce(...)` which is syntactically invalid Python.

```python
# In kailash_ml/__init__.py
async def reproduce(
    run_id: str,
    *,
    verify: bool = True,
    verify_rtol: float = 1e-4,
    verify_atol: float = 1e-6,
) -> TrainingResult:
    """Re-run a registered run end-to-end against the CURRENT code.

    Reads the original run's:
      * feature_versions from ModelVersion.lineage
      * dataset_hash / as_of for point-in-time retrieval
      * seed_report for RNG re-seeding (via km.seed())
      * hyperparameters dict
      * model_class + backend
    Then re-runs fit() against the CURRENT source tree.

    When verify=True, metrics of the reproduced run are compared to the
    original's metrics and the function raises `ReproducibilityError`
    if any metric drifts beyond rtol/atol. Metric-specific tolerance
    overrides can be passed through `verify_overrides`.
    """
```

### 12.1 MUST Rules

#### 1. `reproduce()` Uses `km.seed()` With The Original `SeedReport.seed`

The reproduction path MUST call `km.seed(run.seed_report.seed, ...)` before any other primitive. Attempting to reproduce a run with no `seed_report` MUST raise `ReproducibilityUnavailableError` with message pointing to the promotion rule (§11.2 MUST 2).

**Why:** "Reproduce" without the seed is just "re-run" — two different guarantees.

#### 2. `reproduce()` Pins Feature Versions + Dataset As-Of

Feature versions are looked up at the EXACT `feature_versions` SHA from the ModelVersion lineage; feature-store hash mismatch against the current source is raised as `FeatureVersionMismatchError` with the diff. The user MUST resolve it (either checkout the old feature code or accept non-reproduction).

**Why:** Reproducing a run against a different feature-fn version is not reproduction — it's a different experiment with a shared name.

#### 3. Golden-Run Contract

Every kailash-ml release MUST include a "golden" reference run registered at package-import-time with `is_golden=True`. CI MUST run `km.reproduce(golden_reference_id, verify=True)` as a release gate. Any numerical drift beyond the release-pinned rtol/atol BLOCKS the release.

**Why:** A reproducibility claim that is not verified every release decays silently. The golden run IS the canary for every upstream library bump (torch / lightning / lightgbm).

#### 4. Reproduction Creates A Child Run

`reproduce()` MUST create a new `tracker_run_id` with `parent_run_id=<original_run_id>` and label `{ "run_type": "reproduction" }`. The child run's `TrainingResult.metrics` are compared to the parent's; any diff is logged under `reproduction.metric_diff.{name}`.

**Why:** Reproductions are a first-class observation on the original run, not an orphan run.

### 12.2 Tier 3 Test

A Tier 3 E2E test MUST exist at `tests/e2e/test_km_reproduce_golden.py` that:

1. Loads the pinned golden reference_run_id from `kailash_ml._golden`.
2. Calls `km.reproduce(golden, verify=True)`.
3. Asserts every metric is within `rtol=1e-4, atol=1e-6` of the golden.

Passing the test MUST be a PyPI release gate.

---

## 12A. `km.resume(run_id)` — Checkpoint Resume (§3.2 MUST 7)

`resume()` is a **module-level async function** defined in `kailash_ml/__init__.py` (parallel declaration to §11.1 `seed()` / §12 `reproduce()`; NOT a method on any class). Users access it via `km.resume(...)` when they import the package as `import kailash_ml as km`. Listed in `__all__` Group 1 between `"reproduce"` and `"rl_train"` (§15.9).

`km.resume()` is the user-visible pair to §3.2 MUST 7's `ModelCheckpoint` auto-attach: every `engine.fit(...)` that runs under an ambient `km.track(...)` produces a `last.ckpt` at the run's artifact path; `km.resume(run_id)` reads that checkpoint and continues training from it.

Distinguish from §12 `km.reproduce()`:

- `km.reproduce(run_id)` — re-run from scratch against CURRENT code, verify metric-drift against the original. Use case: CI gate on upstream library bumps.
- `km.resume(run_id)` — continue training from a saved checkpoint, extend training beyond the original epochs. Use case: long-running training job that crashed or exhausted wall-clock.

```python
# In kailash_ml/__init__.py
async def resume(
    run_id: str,
    *,
    tenant_id: str | None = None,
    tolerance: dict[str, float] | None = None,
    verify: bool = False,
    data: "polars.DataFrame | None" = None,
) -> TrainingResult:
    """Resume training from a run's last checkpoint.

    See ml-engines-v2-draft.md §3.2 MUST 7 for the ModelCheckpoint auto-attach
    that writes the checkpoint this function reads.
    """
```

### 12A.1 MUST Rules

#### 1. Artifact Lookup Routes Through The Ambient Tracker

`resume()` MUST resolve `run_id` through the ambient `ExperimentTracker` (the same tracker used by §12 `reproduce`) and read the run's `artifact_path`. The expected checkpoint location is `{artifact_path}/last.ckpt`. Missing checkpoint raises `ResumeArtifactNotFoundError(run_id=, expected_path=)` per §3.2 MUST 7.

#### 2. Resume Dispatches Through The Cached Default Engine

Per §15.2 MUST 1, `km.resume()` MUST route through a tenant-scoped cached default `MLEngine()` instance. The engine's `fit()` call receives `resume_from_checkpoint=<path>` via the Lightning pass-through in `trainer_kwargs`, NOT via a new MLEngine method (MUST NOT add a ninth method — §2.1 MUST 5 / §15.10).

#### 3. Resume Creates A Child Run

Like §12.1 MUST 4 (reproduce), `resume()` MUST create a new `tracker_run_id` with `parent_run_id=<original_run_id>` and label `{ "run_type": "resume" }`. The child run's lineage is a first-class edge type `resume_of` in the ModelRegistry graph.

#### 4. Tolerance-Based Divergence Check Is Opt-In

`tolerance=None` (default) skips any divergence check — the resumed run completes regardless of metric values. `tolerance={"val_loss": 0.01, "accuracy": 0.005}` + `verify=True` invokes a post-fit comparison: if any listed metric in the resumed run drifts beyond the stated tolerance (absolute for deltas, relative via rtol semantics for comparatives — spec detail in `ml-tracking-draft.md §4.3`), `ResumeDivergenceError` is raised with the per-metric diff.

#### 5. Missing Checkpoint Is A Typed Error

`ResumeArtifactNotFoundError(ModelRegistryError)` MUST be raised when:

- The run exists but `enable_checkpointing=False` was set on the parent, OR
- The checkpoint directory was manually deleted, OR
- The tracker's artifact store is unreachable.

The error message MUST name the expected path verbatim AND MUST reference `§3.2 MUST 7` as the source of the default-True checkpointing contract. This turns a silent-no-op into a loud, actionable failure.

### 12A.2 Tier 3 Test

A Tier 3 E2E test MUST exist at `tests/e2e/test_km_resume_crash_recovery.py` that:

1. Fits a toy module for 2 epochs under `km.track("crash-parent")`, interrupts the run mid-epoch-3 via signal.
2. Calls `km.resume(parent_run_id, tolerance={"val_loss": 0.05}, verify=True)` with the ORIGINAL training data.
3. Asserts the resumed run's `val_loss` at epoch 5 is within 0.05 of the clean-sequential-5-epoch run's `val_loss` (established by a prior sidecar golden run).
4. Asserts the resumed run's `tracker_run_id` has `parent_run_id == parent_run_id` and `metadata["run_type"] == "resume"`.

Passing this test is a release gate alongside §12.2 (reproduce).

---

## 13. Continual Learning

### 13.1 API

```python
async def engine.continual_fit(
    data: pl.DataFrame,
    *,
    resume_from: str,                    # base run_id to warm-start from
    warm_start_strategy: Literal[
        "full_weights",          # load all weights + optimizer state
        "weights_only",          # load weights, fresh optimizer
        "ewc",                   # Elastic Weight Consolidation
        "replay_buffer",         # old-data replay per batch
    ] = "full_weights",
    replay_fraction: float = 0.1,        # for replay_buffer strategy
    freeze_layers: list[str] | None = None,
    learning_rate_multiplier: float = 0.1,   # new LR = parent LR * this
) -> TrainingResult:
    """Warm-start from a registered run and continue training on new data.

    Returns a new TrainingResult whose lineage points to resume_from.
    """
```

### 13.2 MUST Rules

#### 1. Parent Run Lineage

`continual_fit` MUST create a child run with `parent_run_id=resume_from` AND emit `run.lineage.warm_start_strategy = <strategy>`. The ModelRegistry lineage graph tracks the parent-child relationship as a first-class edge type `continual_of`.

#### 2. Feature Schema Compatibility Check

If the child run's `schema` differs from the parent's in a non-additive way (column removal, dtype change), the call MUST raise `ContinualSchemaIncompatibleError` BEFORE any training work. Additive changes (new columns) emit a WARN with "new columns initialized to zero-default".

#### 3. Replay Fraction Is Capped

`replay_fraction > 0.5` is BLOCKED — if the user wants to mix old and new data roughly equally, they MUST use `fit()` with combined data. This prevents accidental "continual" runs that are really full re-trains.

### 13.3 Related

- Pairs with Golden-run contract (§12.1 MUST 3) as the canonical continual-learning regression baseline.
- Integrates with `DriftMonitor` via `recommendation="continual_fit"` when concept drift is detected (see `ml-drift.md` §A11.1 drift-type taxonomy).

---

## 14. Future-Proofing (2026-27 Architecture Posture)

This section enumerates which 2026-27 architectures the kailash-ml 1.0 spine supports and at what level. Items below the "deferred" bar are roadmap, not omission — the spine's design explicitly accommodates them under a versioned extension point.

| Architecture                              | v1.0 support | Access pattern                                                                                                                                                                                                                                                                                  |
| ----------------------------------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **Flash-Attention 3** (H100/B200, fp8)    | PARTIAL      | via Lightning+transformers passthrough; `BackendCapability` extended to `{"fp16", "bf16", "fp8_e4m3", "fp8_e5m2", "int8", "int4"}`; `fa_version: int` added to `DeviceReport` (see `ml-backends.md` §3).                                                                                        |
| **Mamba / SSM** (State-Space Models)      | ADAPTER      | `Trainable` protocol accepts non-Transformer architectures at v1.0 via the generic Lightning adapter; `ModelSignature.architecture: Literal["transformer", "ssm", "hybrid", "moe", "rwkv", "none"]`; dedicated Mamba serving adapter deferred to v1.1.                                          |
| **MoE** (Mixture-of-Experts)              | PARTIAL      | Lightning callback receives per-expert load metrics via a new `ExpertRoutingCallback`; routing-entropy logs + load-balancing-loss capture live; full per-expert gradient shard reporting deferred to v1.1.                                                                                      |
| **Tensor-parallel (TP)**                  | SUPPORTED    | autolog + diagnostics rank-0 MUST rule covers TP (see `ml-autolog.md` §3.2); `DistributionEnv` dataclass captures `tp_size`, `pp_size`, `dp_size` explicitly; compatible with `accelerate launch --tp_size=N`.                                                                                  |
| **Pipeline-parallel (PP)**                | SUPPORTED    | same DistributionEnv path; `pp_size` tracked alongside TP; Lightning Fabric backend documented as the first-class PP route.                                                                                                                                                                     |
| **1M-context training**                   | PARTIAL      | `max_prefill_tokens` + `max_decode_tokens_per_chunk` added to streaming spec; first-token-latency budget differentiation in `ml-serving.md` §5.                                                                                                                                                 |
| **Multimodal (image + audio + video)**    | DEFERRED     | `FeatureType: Literal["scalar", "vector", "tensor", "image_ref", "audio_ref", "video_ref"]` adds reference types at v1.1; `log_image/log_audio/log_video` primitives on ExperimentTracker deferred to v1.1; multimodal DL trainable works today via Lightning passthrough with tensor features. |
| **RWKV / RetNet**                         | ADAPTER      | same as Mamba — `ModelSignature.architecture = "rwkv"` routes through generic Lightning adapter.                                                                                                                                                                                                |
| **Speculative decoding (draft + verify)** | DEFERRED     | `InferenceServerConfig.draft_model: ModelRef                                                                                                                                                                                                                                                    | None`+`spec_decode: bool`pinned for v1.1 (see`ml-serving.md` §6). |
| **PagedAttention / KV cache sharing**     | DEFERRED     | `PagedAttentionConfig(block_size, gpu_memory_utilization, swap_space_gb)` in `ml-serving.md` §7 for v1.1.                                                                                                                                                                                       |
| **LoRA / QLoRA hot-swap at inference**    | DEFERRED     | `ModelRegistry.load_lora_adapter(base_model_version, adapter_id)` primitive at v1.1; multi-adapter concurrent serving at v1.1; base_model + adapter separately tracked at train time in `ml-autolog.md` §3.1.                                                                                   |
| **DeepSpeed-Chat / NeMo-Aligner**         | N/A          | `ml-rl-align-unification.md` §6 enumerates DeepSpeed-specific losses (reward-model loss, critic loss, DPO loss, ORPO loss) that kailash-align surfaces.                                                                                                                                         |

The "DEFERRED" items are bound to milestone issues at `github.com/terrene-foundation/kailash-py` under label `kailash-ml/v1.1-roadmap`.

---

## 15. Top-Level Convenience Wrappers — `km.*`

The eight-method `MLEngine` surface (§2.1 MUST 5) is the contract. `MLEngine` method count is FROZEN at eight; §2.1 MUST 5 is NOT modified by this section. A ninth engine method would require a spec amendment.

In addition to the engine class, `kailash-ml` ships package-level convenience wrappers under `kailash_ml.*` (typically referenced as `km.*` via `import kailash_ml as km`). These wrappers are thin dispatchers to a tenant-scoped cached default `km.Engine()` — they exist to match the newbie-UX pattern every competitor (MLflow, W&B, Neptune, Comet, ClearML) ships and to deliver the canonical Quick Start in §16.

### 15.1 Scope

These wrappers MUST exist in `kailash_ml/__init__.py`:

| Wrapper        | Returns           | Dispatch Target                                                                                                                                           |
| -------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `km.train`     | `TrainingResult`  | `engine.setup(...)` then `engine.fit(...)` chained on the cached default engine                                                                           |
| `km.register`  | `RegisterResult`  | `engine.register(...)` on the cached default engine                                                                                                       |
| `km.serve`     | `ServeHandle`     | `engine.serve(...)` on the cached default engine                                                                                                          |
| `km.watch`     | `DriftMonitor`    | `engine.monitor(...)` on the cached default engine (see `ml-drift.md` §12)                                                                                |
| `km.dashboard` | `DashboardHandle` | Non-blocking launcher for `MLDashboard` (see `ml-dashboard.md` §8.6)                                                                                      |
| `km.diagnose`  | `Diagnostic`      | See `ml-diagnostics.md` §3 (owned there; listed here for discoverability)                                                                                 |
| `km.track`     | `ExperimentRun`   | See `ml-tracking.md` §2 (owned there; listed here for discoverability)                                                                                    |
| `km.autolog`   | `AutologHandle`   | See `ml-autolog.md` §2 (owned there; listed here for discoverability)                                                                                     |
| `km.rl_train`  | `TrainingResult`  | See `ml-rl.md` (owned there; listed here for discoverability)                                                                                             |
| `km.resume`    | `TrainingResult`  | §12A — reads `last.ckpt` from tracker run's artifact path, dispatches to cached default engine with `resume_from_checkpoint` pinned.                      |
| `km.lineage`   | `LineageGraph`    | `ml-engines-v2-addendum §E10.2` — tenant-scoped, depth-bounded cross-engine lineage graph (run + dataset + feature_version + model_version + deployment). |

### 15.2 MUST Rules

#### 1. Each Wrapper Routes Through A Tenant-Scoped Cached Default Engine

A module-level dict `_default_engines: dict[str | None, Engine]` MUST cache one default `Engine()` per `tenant_id`. Wrappers call a helper `_get_default_engine(tenant_id: str | None) -> Engine` that either returns the cached instance or constructs `km.Engine(tenant_id=tenant_id)` on first use and stores it.

```python
# DO — cached per-tenant default engine
_default_engines: dict[str | None, Engine] = {}

def _get_default_engine(tenant_id: str | None) -> Engine:
    if tenant_id not in _default_engines:
        _default_engines[tenant_id] = Engine(tenant_id=tenant_id)
    return _default_engines[tenant_id]

# DO NOT — construct a fresh Engine on every wrapper call
async def train(df, *, target, **kwargs):
    engine = Engine()  # BLOCKED — defeats the cache; new SQLite connection per call
    ...
```

**Why:** A per-call `Engine()` opens a fresh SQLite connection, re-constructs the six primitives, and discards them at function exit — the wrapper becomes 100× slower than the engine method it wraps. Caching per `tenant_id` preserves the "zero-config" feel while only paying the construction cost once per tenant per process.

#### 2. `km.*` Wrappers MUST NOT Be Added As `MLEngine` Methods

`km.*` wrappers are package-level functions ONLY. They MUST NOT appear as methods on the `MLEngine` class. §2.1 MUST 5 locks the engine surface at exactly eight methods — adding `km.train` as `engine.train()` would grow the class to nine.

```python
# DO — package-level function; engine method count unchanged at 8
# kailash_ml/__init__.py
async def train(df, *, target, family="auto", tenant_id=None, actor_id=None, tracker=None):
    engine = _get_default_engine(tenant_id)
    await engine.setup(df, target=target)
    return await engine.fit(family=family, actor_id=actor_id, tracker=tracker)

# DO NOT — add `train()` as a 9th engine method
class Engine:
    async def train(self, df, *, target, family="auto", ...):  # BLOCKED
        await self.setup(df, target=target)
        return await self.fit(family=family)
```

**BLOCKED rationalizations:**

- "Users would expect `engine.train()` as a method on the Engine class"
- "Having both a wrapper AND a method is fine — users pick whichever"
- "The eight-method limit in §2.1 MUST 5 is aspirational"
- "A ninth method is easier to document than a separate wrapper"

**Why:** The eight-method contract is the Engine's spec-level invariant — every code generator, `mypy --strict` stub, and auto-completion UI reads it as a closed set. Adding a ninth method in response to every "we need a wrapper" request is exactly the accretion path that produced v0.9.x's 18-class surface. Package-level wrappers are the opt-in convenience layer; the engine class stays at eight.

#### 3. Wrapper Return Types MUST Match The Engine Method They Wrap

Every wrapper MUST return the same dataclass type the wrapped engine method returns. Wrappers MUST NOT transform, flatten, or re-shape the wrapped method's return. A `TrainingResult` goes in, a `TrainingResult` comes out.

**Why:** Inconsistent return types between `km.train(df)` and `engine.fit(df)` would force users to remember two schemas for the same output. Identity return preserves downstream interop: `await km.register(await km.train(df, target="y"), name="x")` is indistinguishable from the engine-method chain.

#### 4. Wrappers MUST Accept And Propagate `tenant_id` + `actor_id` Unchanged

Every wrapper signature MUST accept `tenant_id: str | None = None` AND `actor_id: str | None = None` (where the wrapped engine method accepts them). The wrapper MUST propagate these verbatim through to the engine method — no defaults silently substituted.

```python
# DO — pass through tenant + actor unchanged
async def register(
    training_result: TrainingResult,
    *,
    name: str,
    alias: str | None = None,
    tenant_id: str | None = None,
    actor_id: str | None = None,
) -> RegisterResult:
    engine = _get_default_engine(tenant_id)
    return await engine.register(
        training_result, name=name, alias=alias, actor_id=actor_id,
    )

# DO NOT — swallow tenant/actor, silently default to "_single" / "global" / "default"
async def register(training_result, *, name):
    engine = _get_default_engine(None)              # ignores tenant_id
    return await engine.register(training_result, name=name, actor_id="anonymous")
```

**Why:** The multi-tenancy audit trail in §5 and `rules/tenant-isolation.md` depends on `tenant_id` + `actor_id` reaching the registry / tracker / monitor. A wrapper that silently swallows these args recreates the v0.9.x "no actor on mutations" failure that `ml-registry-draft.md` §2 closes.

### 15.3 `km.train` Signature

```python
async def train(
    df: pl.DataFrame | pl.LazyFrame,
    *,
    target: str,
    family: str = "auto",                             # "auto" runs compare() then picks best
    tenant_id: str | None = None,
    actor_id: str | None = None,
    tracker: "ExperimentRun | None" = None,           # ambient run read from contextvar if None
    ignore: list[str] | None = None,
    hyperparameters: dict | None = None,
    hp_search: str = "none",
    n_trials: int = 0,
    metric: str | None = None,
) -> TrainingResult: ...
```

Behaviour:

1. Resolve cached engine via `_get_default_engine(tenant_id)`.
2. `await engine.setup(df, target=target, ignore=ignore)`.
3. If `family == "auto"`, run `engine.compare()` with the task-appropriate default family set and pick the winner; otherwise run `engine.fit(family=family, hyperparameters=hyperparameters, hp_search=hp_search, n_trials=n_trials, metric=metric)`.
4. Return the resulting `TrainingResult` unchanged.

**BLOCKED:** `km.train` MUST NOT silently call `engine.register(...)` or `engine.serve(...)` — those are separate steps the user invokes explicitly.

### 15.4 `km.register` Signature

```python
async def register(
    training_result: TrainingResult,
    *,
    name: str,
    alias: str | None = None,
    tenant_id: str | None = None,
    actor_id: str | None = None,
    format: str = "onnx",                             # per §6 MUST 1
    stage: str = "staging",
    metadata: dict | None = None,
) -> RegisterResult: ...
```

Behaviour:

1. Validate the `training_result` is populated (all ten §4.1 required fields present — §4.2 MUST 1).
2. Resolve cached engine via `_get_default_engine(tenant_id)`.
3. Dispatch to `engine._model_registry.register_model(training_result=training_result, name=name, actor_id=actor_id, format=format, metadata=metadata, tenant_id=tenant_id or "_single", lineage=training_result.lineage, ...)`.
4. If `alias` is supplied, chain `engine._model_registry.set_alias(name, version, alias, actor_id=actor_id, reason=f"km.register alias={alias}")`.
5. Return the `RegisterResult` unchanged.

Full lineage (run_id, dataset_hash, code_sha) is auto-populated from `training_result.lineage` per `ml-registry-draft.md` §6. Missing lineage raises `LineageRequiredError` — no silent defaulting.

### 15.5 `km.serve` Signature

```python
async def serve(
    model_uri_or_result: "str | RegisterResult",
    *,
    alias: str | None = None,
    channels: tuple[str, ...] = ("rest",),            # subset of ("rest", "mcp", "grpc")
    tenant_id: str | None = None,
    version: int | None = None,
    autoscale: bool = False,
    options: dict | None = None,
) -> "ServeHandle": ...
```

See `ml-serving.md` §2.2 for the full dispatch behaviour. Contract: `km.serve("fraud@production")` resolves the model, brings up the requested channels, and returns a `ServeHandle` with `.url`, `.stop()`, `.status`. Process-local — each handle corresponds to an in-process inference server instance owned by the cached engine.

### 15.6 `km.watch` Signature

```python
async def watch(
    model_uri: str,
    *,
    reference: "pl.DataFrame | None" = None,
    axes: tuple[str, ...] = ("feature", "prediction", "performance"),
    alerts: "AlertConfig | None" = None,
    tenant_id: str | None = None,
    actor_id: str | None = None,
) -> "DriftMonitor": ...
```

See `ml-drift.md` §12 for full behaviour. Returns the `DriftMonitor` handle so the caller can invoke `.start()`, `.stop()`, `.inspect()` on it.

### 15.7 `km.dashboard` Signature

```python
def dashboard(
    *,
    db_url: str | None = None,                        # None = ~/.kailash_ml/ml.db
    port: int = 5000,
    bind: str = "127.0.0.1",
    auth: "NexusAuthPolicy | None" = None,
    tenant_id: str | None = None,
    title: str = "Kailash ML",
) -> "DashboardHandle": ...
```

Non-blocking Python launcher — returns a `DashboardHandle` exposing `.url`, `.stop()`. Starts `MLDashboard()` on a background event-loop thread (notebook-friendly). Complements the existing `kailash-ml-dashboard` CLI (`ml-dashboard.md` §8).

See `ml-dashboard.md` §8.6 for the full handle contract.

### 15.8 `km.diagnose`, `km.track`, `km.autolog`, `km.rl_train`, `km.resume`, `km.lineage`

These wrappers are specified in their owning spec files; listed here for discoverability:

- `km.diagnose` — specified in `ml-diagnostics.md` §3 (the section MUST be documented at the TOP of that spec as THE engine entry, not buried mid-file).
- `km.track` — specified in `ml-tracking.md` §2.
- `km.autolog` — specified in `ml-autolog.md` §2. Reuses the same contextvar accessor `kailash_ml.tracking.get_current_run()` as every other wrapper — no independent global; conflict with Shard C-A's contextvar accessor (Decision 4 rank-0) is impossible by construction.
- `km.rl_train` — specified in `ml-rl.md` (wraps `rl.Engine.train()`).
- `km.resume` — specified in §12A of this file (checkpoint-resume pair to §3.2 MUST 7's `ModelCheckpoint` auto-attach).
- `km.lineage` — specified in `ml-engines-v2-addendum-draft.md §E10.2`. Signature:

  ```python
  async def lineage(
      run_id_or_model_version_or_dataset_hash: str,
      *,
      tenant_id: str | None = None,     # resolved via get_current_tenant_id() when None
      max_depth: int = 10,
  ) -> LineageGraph: ...
  ```

  Per `ml-tracking.md §10.2`, `tenant_id=None` resolves to the ambient `get_current_tenant_id()` value; multi-tenant engines without ambient context raise `TenantRequiredError` per `rules/tenant-isolation.md`. This aligns `km.lineage` with every sibling `km.*` verb (`km.track`, `km.train`, `km.register`, `km.serve`, `km.watch`, `km.resume`, etc.) which all default `tenant_id: str | None = None` — preventing a `TypeError` for day-0 single-tenant users who never pass `tenant_id` explicitly.

  Returns the canonical `LineageGraph` dataclass (declared in `ml-engines-v2-addendum §E10.2`). Tenant-scoped per `rules/tenant-isolation.md` — cross-tenant reads raise `CrossTenantReadError`. Dispatches through the cached default engine per §15.2 MUST 1; `LineageGraph` import is eager per §15.9 MUST rule.

### 15.9 `kailash_ml.__all__` Canonical Ordering

The `kailash_ml/__init__.py::__all__` list MUST be ordered as follows — six named groups in this exact sequence (Group 6 added by Phase-F F5 per `ml-engines-v2-addendum §E11.2`):

```python
__all__ = [
    # Group 1 — Lifecycle verbs (action-first for discoverability)
    "track",
    "autolog",
    "train",
    "diagnose",
    "register",
    "serve",
    "watch",
    "dashboard",
    "seed",        # reproducibility entry (§11); module-level function in __init__.py
    "reproduce",   # reproducibility entry (§12); module-level async function in __init__.py
    "resume",      # checkpoint-resume entry (§12A); module-level async function in __init__.py
    "lineage",     # cross-engine lineage entry (ml-engines-v2-addendum §E10.2);
                   # module-level async function; returns LineageGraph dataclass
    "rl_train",

    # Group 2 — Engine primitives + MLError hierarchy
    "Engine",
    "Trainable",
    "TrainingResult",
    "MLError",
    "TrackingError",
    "AutologError",
    "RLError",
    "BackendError",
    "DriftMonitorError",
    "InferenceServerError",
    "ModelRegistryError",
    "FeatureStoreError",
    "AutoMLError",
    "DiagnosticsError",
    "DashboardError",

    # Group 3 — Diagnostic adapters + helpers
    "DLDiagnostics",
    "RAGDiagnostics",
    "RLDiagnostics",
    "diagnose_classifier",
    "diagnose_regressor",

    # Group 4 — Backend detection
    "detect_backend",
    "DeviceReport",

    # Group 5 — Tracker primitives
    "ExperimentTracker",
    "ExperimentRun",
    "ModelRegistry",

    # Group 6 — Engine Discovery (metadata introspection per ml-engines-v2-addendum §E11.2)
    "engine_info",
    "list_engines",
]
```

**Group 1 vs Group 6 distinction.** Group 1 holds the operational verbs users call in the run/train/serve lifecycle (`track`, `train`, `register`, `serve`, `watch`, ...). Group 6 holds the metadata verbs users (or Kaizen agents per `ml-engines-v2-addendum §E11.3 MUST 1`) call for introspection — `list_engines()` enumerates available engines, `engine_info(name)` returns the `EngineInfo` dataclass for a single engine. These are NOT lifecycle actions; they are discovery primitives and belong in their own group so Sphinx autodoc and `from kailash_ml import *` readers observe the separation.

#### MUST: Ordering Is Load-Bearing

The ordering above is load-bearing — `from kailash_ml import *` users observe verbs before primitives, and Sphinx autodoc emits the public surface in that sequence. Reordering within a group is permitted with spec amendment; moving a symbol across groups is a breaking-change signal and requires an amendment.

#### MUST: Every `__all__` Entry Is Eagerly Imported

Per `rules/zero-tolerance.md` Rule 1a (second instance — `py/modification-of-default-value` via lazy `__getattr__` in `__all__`), every symbol listed in `__all__` MUST be eagerly imported at module scope in `kailash_ml/__init__.py`. Lazy `__getattr__` resolution for `__all__` entries is BLOCKED — CodeQL flags it.

```python
# DO — eager import in __init__.py
from kailash_ml.tracking import track, autolog, ExperimentTracker, ExperimentRun
from kailash_ml._wrappers import train, register, serve, watch, dashboard, rl_train
from kailash_ml.diagnostics import diagnose, DLDiagnostics, RAGDiagnostics, RLDiagnostics
from kailash_ml.engines.lineage import LineageGraph  # eager import for km.lineage return type (§15.8)
from kailash_ml.engines.registry import engine_info, list_engines  # Group 6 Engine Discovery (ml-engines-v2-addendum §E11.2)
# seed() + reproduce() + resume() + lineage() are DECLARED at module scope in this file
# (see §11.1, §12, §12A, §15.8):
def seed(seed: int, *, torch: bool = True, ...) -> SeedReport: ...
async def reproduce(run_id: str, *, verify: bool = True, ...) -> TrainingResult: ...
async def resume(run_id: str, *, tenant_id: str | None = None,
                 tolerance: dict[str, float] | None = None) -> TrainingResult: ...
async def lineage(run_id_or_model_version_or_dataset_hash: str, *,
                  tenant_id: str | None = None,
                  max_depth: int = 10) -> LineageGraph: ...

# DO NOT — lazy resolution for __all__ entries
def __getattr__(name):
    if name == "train":
        from kailash_ml._wrappers import train
        return train
# ↑ CodeQL py/modification-of-default-value fires; `from kailash_ml import *` may drop entries.
```

**Why:** Eager imports close the `__all__`-drift failure mode permanently and ship a single canonical export set that every static-analysis tool reads consistently. The one-time import cost is paid once per process.

### 15.10 MLEngine Method-Set Preservation (Explicit Restatement)

This section is the explicit restatement of §2.1 MUST 5 for the benefit of readers scanning §15 for the `km.*` surface: the eight-method `MLEngine` public surface (`setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`) is UNCHANGED by every clause in §15. `km.*` wrappers are package-level convenience functions that dispatch into the existing eight methods — they do NOT add a ninth method to `MLEngine`, they do NOT rename any of the eight, and they do NOT change any existing method's signature. Any ML-specialist implementation PR that ships a ninth `MLEngine` method is REJECTED at review gate per §2.1 MUST 5.

---

## 16. Canonical README Quick Start

Closes round-2b G-README-QUICKSTART-MISSING. The `packages/kailash-ml/README.md` `## Quick Start` section MUST contain the LITERAL block below. The six-import primitive form from v0.9.x (FeatureStore + ModelRegistry + ExperimentTracker + TrainingPipeline + ConnectionManager + LocalFileArtifactStore) is REMOVED. The Tier-2 regression test in §16.3 parses the README's first ```python block and executes it end-to-end against real infrastructure; if the README drifts from this spec, CI fails and the release is BLOCKED.

### 16.1 Canonical Block (literal — MUST match README verbatim)

````markdown
```python
import kailash_ml as km
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
# $ kailash-ml-dashboard  (separate shell)
```
````

The text preceding the block in the README MUST read (verbatim):

> Install with `pip install kailash-ml`. The following block is executed by CI against a real DataFrame and is the canonical Quick Start for the 1.0.0 release. Every line is load-bearing — do NOT abbreviate it in copy-paste examples on external sites.

### 16.2 MUST Rules

#### 1. Quick Start Line Count

The executable Python portion of the Quick Start MUST be between 5 and 10 lines of non-blank content, inclusive. Under 5 hides the async-context-manager form; over 10 reintroduces the v0.9.x "forty lines of plumbing" failure mode the Engine was designed to eliminate. The canonical block in §16.1 is exactly 6 lines (including the dashboard comment line — which is a deliberate, user-facing callout that MUST remain).

#### 2. No Construction Ceremony

The Quick Start MUST NOT construct a `ConnectionManager`, `FeatureStore`, `ModelRegistry`, `ExperimentTracker`, `ArtifactStore`, or explicit `Engine()` in the user-visible code. Every one of those is owned by the `km.*` convenience wrappers per §15 and §2.1 MUST 1 (zero-arg construction). Violating this rule resurrects exactly the DX failure the 1.0.0 Engine was designed to eliminate.

**BLOCKED rationalizations:**

- "Showing the ConnectionManager teaches users about lifecycle"
- "Advanced users want to see the full plumbing"
- "Five lines is too terse for a real example"

**Why:** The Quick Start sets the mental model for every reader. If the canonical quick-start includes plumbing, every downstream blog post, every Stack Overflow answer, every `pip install; python -c '...'` one-liner copies the plumbing. The Engine's zero-arg contract (§2.1 MUST 1) is worthless if the canonical example doesn't demonstrate it.

### 16.3 Tier-2 Regression Test — `test_readme_quickstart_executes.py` (release-blocking)

`packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py` MUST:

1. Parse the first ```python code block out of `packages/kailash-ml/README.md` at test collection time.
2. Compare its SHA-256 fingerprint against the canonical block in §16.1 (stored as a constant in the test file). Any byte-level drift fails the test immediately with a diff. This is the structural defense against "the README drifted from the spec" — fix the README to match §16.1, OR amend §16.1 via a spec-change PR, never both in isolation.
3. Execute the parsed block against real infrastructure (SQLite tracker store at `tmp_path/ml.db`, LocalFileArtifactStore at `tmp_path/artifacts/`, a polars DataFrame `df = pl.DataFrame({"x": [1, 2, 3, 4], "y": [0, 1, 0, 1]})` injected into globals).
4. Assert:
   - `run.run_id` is non-empty after the async-context manager exits.
   - `result` is a `TrainingResult` with `device: DeviceReport` populated AND `metrics` non-empty. The back-compat mirror `result.device_used` also resolves as a non-empty string.
   - `registered.artifact_uris["onnx"]` starts with `"file://"` or `"cas://sha256:"`.
   - `server.uris["rest"]` is reachable via one HTTP probe (`GET /health → 200`).
   - The tracker's `list_runs()` returns a run named `"demo"`.
5. Run on every CI matrix job (CPU, MPS — blocking; CUDA — blocking once self-hosted runner lands per Decision 7 GPU CI runner policy).

````python
# packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py
import pytest
import re
import hashlib
import pathlib
import polars as pl

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CANONICAL_BLOCK = '''\
import kailash_ml as km
async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
# $ kailash-ml-dashboard  (separate shell)
'''
CANONICAL_SHA = hashlib.sha256(CANONICAL_BLOCK.encode()).hexdigest()

def _extract_first_python_block(readme_text: str) -> str:
    match = re.search(r"```python\n(.*?)\n```", readme_text, flags=re.DOTALL)
    if match is None:
        raise AssertionError("README has no ```python block — Quick Start missing")
    return match.group(1) + "\n"

@pytest.mark.regression
@pytest.mark.integration
async def test_readme_quickstart_fingerprint_matches_spec():
    """Structural drift guard: README Quick Start MUST match §16.1 verbatim."""
    readme = (REPO_ROOT / "packages/kailash-ml/README.md").read_text()
    code = _extract_first_python_block(readme)
    actual_sha = hashlib.sha256(code.encode()).hexdigest()
    assert actual_sha == CANONICAL_SHA, (
        f"README Quick Start drifted from ml-engines-v2-draft.md §16.1.\n"
        f"Expected SHA: {CANONICAL_SHA}\n"
        f"Actual   SHA: {actual_sha}\n"
        f"Fix the README to match §16.1, OR amend §16.1 via spec-change PR."
    )

@pytest.mark.regression
@pytest.mark.integration
async def test_readme_quickstart_executes_end_to_end(tmp_path, monkeypatch):
    """End-to-end execution of the README's Quick Start against real infrastructure."""
    import kailash_ml as km
    readme = (REPO_ROOT / "packages/kailash-ml/README.md").read_text()
    code = _extract_first_python_block(readme)

    # Redirect default store to tmp_path for test isolation
    monkeypatch.setenv("KAILASH_ML_STORE_URL", f"sqlite:///{tmp_path}/ml.db")
    monkeypatch.setenv("KAILASH_ML_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    df = pl.DataFrame({"x": [1, 2, 3, 4], "y": [0, 1, 0, 1]})
    globals_ns = {"df": df, "__name__": "__main__"}

    # Execute the code as an async block
    exec_wrapper = f"""
async def _quickstart():
{chr(10).join('    ' + line for line in code.splitlines())}
    return run, result, registered, server
"""
    exec(exec_wrapper, globals_ns)
    run, result, registered, server = await globals_ns["_quickstart"]()

    # Load-bearing assertions
    assert run.run_id, "run.run_id must be non-empty"
    assert result.metrics, "TrainingResult.metrics must be non-empty"
    assert result.device is not None, "TrainingResult.device: DeviceReport must be populated (§4.2 MUST 1)"
    assert result.device_used, "TrainingResult.device_used back-compat mirror must resolve (§4.1)"
    assert "onnx" in registered.artifact_uris, "register() must default to ONNX (§2.1 MUST 9)"
    assert registered.artifact_uris["onnx"].startswith(("file://", "cas://sha256:"))
    assert server.uris["rest"], "serve() must expose a REST channel"
````

### 16.4 Release Gate

This test is release-blocking. If it fails, the 1.0.0 release PR is BLOCKED until either:

(a) the README is edited to match §16.1 byte-for-byte (same text, same whitespace, same comment), OR
(b) the spec is amended in a separate PR that updates §16.1, bumps the `CANONICAL_SHA` constant in the test file, and re-runs the end-to-end execution check.

**Why this matters:** A Quick Start that doesn't execute is a lie. Every competitor (MLflow, Neptune, W&B) has shipped at least one release where their README's code block silently stopped working across a minor version bump — the regression guard makes that class of bug a CI failure at the PR that introduces it, not a user GitHub issue a month later. Pinning the README to §16.1 via SHA-256 also closes the "drift by example" failure mode where the README shows `km.train(df, target="y")` but the spec says `engine.fit(df, target="y")` — the two are reconciled in one file, not scattered across markdown.

---

## 17. Cross-References

Every reference below points to another spec or rule that this spec depends on but does not duplicate.

- **`ml-backends.md`** — device resolution, `detect_backend()`, per-backend tensor conversion, GPU memory estimation, `DeviceReport` dataclass. This spec's §2 `accelerator=`, §3 `TrainingContext`, and §4 `TrainingResult.device: DeviceReport` (plus the `device_used` / `accelerator` / `precision` 1.x back-compat mirrors) all delegate to `ml-backends.md` for resolution semantics.
- **`ml-tracking.md`** — `ExperimentTracker` contract, run hierarchy, metrics registry, MLflow format interop. This spec's §2.1 MUST 3 (DI for tracker), §7.1 MUST 5 (async tracker), §7.1 MUST 7 (MCP experiment query) all delegate.
- **`ml-serving.md`** — `engine.serve()` multi-channel implementation, `InferenceServer` cache, ONNX runtime selection, inference-path validation. This spec's §2.1 MUST 10 delegates.
- **`ml-feature-store.md`** — `FeatureStore` schema versioning, `evolve()` helpers, tenant-scoped keys, point-in-time correctness. This spec's §7.1 MUST 6 (schema evolution) delegates.
- **`ml-drift.md`** — `DriftMonitor` detection methods, scheduled monitoring. This spec's §5.1 MUST 1 (primitive tenant awareness) applies to DriftMonitor but field-level semantics live in `ml-drift.md`.
- **`ml-rl.md`** — `kailash_ml.rl.Engine`, RL-on-Lightning adapter, reward registry. This spec's §9.1 Primitives list includes `rl.Engine`; behavioural contract lives in `ml-rl.md`.
- **`core-runtime.md`** — runtime / event-loop contract that `kailash_ml.sync.Engine` delegates to.
- **`rules/tenant-isolation.md`** — the authoritative multi-tenancy rule; this spec's §5 is the ML-specific form.
- **`rules/orphan-detection.md` + `rules/facade-manager-detection.md`** — every Primitive on `MLEngine` MUST have a production call site inside the Engine and a Tier 2 integration test. The eight-method Engine contract (§2.1 MUST 5) is the hot-path that gives every Primitive a call site.
- **`rules/zero-tolerance.md`** — fake encryption / fake transactions / fake health / fake classification patterns are all BLOCKED. This spec's §4 MUST 1 (every TrainingResult field populated) closes the "partially-populated result" failure mode from the same class.
- **`rules/framework-first.md`** — the four-layer hierarchy this spec's §9 implements for kailash-ml.

---

## 18. Spec Conformance Checklist

This checklist is the structural gate for kailash-ml 1.0.0 release. Every item MUST pass before tagging.

- [ ] `kailash_ml.Engine()` constructs successfully with zero arguments on macOS (MPS), Linux (CUDA + CPU), and Windows (CPU)
- [ ] `MLEngine` public surface is exactly eight methods (`setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`)
- [ ] Every `MLEngine` method returns a named dataclass (no raw dicts)
- [ ] `Trainable` protocol has `LightningModule` adapters for sklearn, xgboost, lightgbm, catboost, torch, lightning
- [ ] `training_pipeline.py` has zero fit loops outside `L.Trainer(**ctx_kwargs).fit(module, loader)`
- [ ] `TrainingResult` dataclass has all ten required fields
- [ ] `rg '"default"' src/` returns zero matches in cache key construction
- [ ] Every Primitive constructor accepts `tenant_id`
- [ ] ONNX compatibility matrix entries all have round-trip tests passing
- [ ] `register(format="onnx")` raises `OnnxExportError` on failure (no silent pickle fallback)
- [ ] `kailash_ml.legacy.*` covers every demoted v0.9.x public symbol
- [ ] Every legacy import emits `DeprecationWarning` on first use
- [ ] Integration tests in §7.2 all pass on CPU; GPU-gated tests (`pytest.mark.gpu_*`) pass on CI GPU runners
- [ ] Cross-SDK: kailash-rs can load an ONNX artifact produced by kailash-py for at least one model per matrix key
- [ ] `rg 'raise NotImplementedError' src/kailash_ml/` returns zero matches
- [ ] `rg 'TODO|FIXME|XXX|HACK' src/kailash_ml/` returns zero matches
- [ ] Every `§7` competitive-delta claim has an integration test of the name listed in §7.2
- [ ] `km.seed()` seeds Python random + numpy + torch + cudnn + accelerate and returns a populated `SeedReport`
- [ ] `TrainingResult.seed_report` is populated on every run that consumed a seed
- [ ] `km.reproduce(golden_run_id)` CI gate passes on every release (Tier 3 test)
- [ ] Golden reference run is registered at package-import with `is_golden=True`
- [ ] `engine.continual_fit(resume_from=...)` emits lineage edge `continual_of`
- [ ] `cudnn.benchmark=True` combined with fixed seed emits a loud WARN
- [ ] `BackendCapability` enum extended to include `fp8_e4m3`, `fp8_e5m2` per §14
- [ ] Top-level `km.*` wrappers (`train`, `register`, `serve`, `watch`, `dashboard`, `diagnose`, `track`, `autolog`, `seed`, `reproduce`, `resume`, `rl_train`) are declared in `kailash_ml/__init__.py::__all__` AND eagerly imported. `seed`, `reproduce`, and `resume` are module-level functions (§11.1, §12, §12A) — not methods on any class.
- [ ] `kailash_ml/__init__.py::__all__` ordering matches §15.9 (verbs first, primitives + MLError hierarchy second, diagnostic adapters third, backends fourth, tracker primitives fifth)
- [ ] `MLEngine` method count is exactly eight (§2.1 MUST 5) — NO `km.*` wrapper is added as a ninth engine method
- [ ] `km.*` wrappers route through a `_default_engines: dict[str | None, Engine]` cache keyed by `tenant_id` — one cached instance per tenant per process
- [ ] `tests/integration/test_readme_quickstart_executes.py` parses and executes the literal `## Quick Start` block from `packages/kailash-ml/README.md` on every CI matrix job
- [ ] `tests/integration/test_lightning_auto_attach_diagnostics_callback.py` passes — `_train_lightning` auto-appends `DLDiagnostics.as_lightning_callback()` + `ModelCheckpoint` when tracker is ambient (§3.2 MUST 5)
- [ ] `tests/integration/test_fit_ddp_strategy_rank0_emission.py` passes — `strategy="ddp"` passthrough emits rank-0-only metrics per Decision 4 (§3.2 MUST 6)
- [ ] `tests/integration/test_default_checkpointing_enabled.py` passes — `enable_checkpointing=True` is the new default at 1.0.0 (§3.2 MUST 7)
- [ ] `tests/integration/test_km_resume_roundtrip.py` passes — `km.resume(run_id, tolerance=..., verify=True)` continues from `last.ckpt` and lineage-links child to parent (§12A.1 MUST 3)
- [ ] `tests/integration/test_km_resume_missing_checkpoint_raises.py` passes — `ResumeArtifactNotFoundError` with expected-path in message when checkpoint absent (§12A.1 MUST 5)
- [ ] `tests/integration/test_auto_find_lr_opt_in.py` passes — `auto_find_lr=False` default preserves user LR; `auto_find_lr=True` runs `lr_find` + logs figure (§3.2 MUST 8)
- [ ] `tests/integration/test_huggingface_trainable_wiring.py` passes — `HuggingFaceTrainable(model_name_or_path, task=...)` satisfies Trainable protocol, fits under Lightning, auto-attaches diagnostics + checkpoint (§3.2 MUST 9)
- [ ] `[dl-deepspeed]` extra is declared in `packages/kailash-ml/pyproject.toml` pinning `deepspeed>=0.14.0` + `pydantic>=2.0` (Decision 13 addendum, §3.2 MUST 6)
- [ ] `peft>=0.10.0` is pinned in the `[dl]` extra to support `HuggingFaceTrainable(peft_config=...)` (§3.2 MUST 9)
- [ ] `km.resume` is listed in `__all__` Group 1 between `"reproduce"` and `"rl_train"` AND eagerly imported at module scope (§15.9)
- [ ] `kailash_ml.__all__` Group 1 includes `"lineage"` per §15.9
- [ ] `from kailash_ml.engines.lineage import LineageGraph` is eagerly imported per §15.9 MUST: Eager Imports
- [ ] `ResumeArtifactNotFoundError` inherits `ModelRegistryError(MLError)` and is re-exported at `kailash_ml.errors.ResumeArtifactNotFoundError`
- [ ] `ResumeDivergenceError` inherits `MLError` (cross-cutting) and is re-exported at `kailash_ml.errors.ResumeDivergenceError`
- [ ] `engine_info`, `list_engines` listed in `__all__` Group 6 (§15.9) AND eagerly imported at module scope from `kailash_ml.engines.registry` per `ml-engines-v2-addendum §E11.2`

---

_End of ml-engines-v2-draft.md_
