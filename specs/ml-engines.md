# Kailash ML Engines Specification (v2.0 Draft)

Parent domain: ML Lifecycle (`kailash-ml`). Companion files (drafted in parallel, referenced by name):

- `ml-backends.md` — device/accelerator/precision resolution, Trainable protocol device contract, `detect_backend()` semantics, per-backend tensor conversion, GPU memory estimation.
- `ml-tracking.md` — `ExperimentTracker` async-context contract, run hierarchy, metrics registry, MLflow format interop, dashboard state injection.
- `ml-serving.md` — `InferenceServer`, `engine.serve()` REST/MCP/gRPC channels, ONNX runtime selection, cache eviction.
- `ml-feature-store.md` — `FeatureStore` schema versioning, `evolve()` helpers, tenant-scoped cache keys, point-in-time correctness.
- `ml-drift.md` — `DriftMonitor`, PSI/KS thresholds, scheduled monitoring, alert routing.
- `ml-rl.md` — `kailash_ml.rl.Engine`, Lightning-composed RL trainers, reward registry.

Package: `kailash-ml` v2.0.0
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
    tracker=ExperimentTracker(conn),
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
tracker = ExperimentTracker(conn)
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
# engine._tracker = ExperimentTracker(conn); custom_tracker ignored
```

**Why:** Enterprise users regularly need to plug in existing MLflow tracking servers, shared feature stores, or custom artifact backends. A silent "we know better" substitution converts the override into dead code and makes the Engine untrustworthy for power users.

#### 4. Every `MLEngine` Method MUST Return A Named Dataclass — Never A Raw Dict Or Tuple

Every public method on `MLEngine` MUST declare a typed dataclass return (`TrainingResult`, `ComparisonResult`, `PredictionResult`, `ServeResult`, `RegisterResult`, `EvaluationResult`, `SetupResult`, `FinalizeResult`). Returning a raw `dict`, `tuple`, or unnamed polars DataFrame is BLOCKED.

```python
# DO — typed dataclass return
result: TrainingResult = await engine.fit(data, target="churned")
print(result.metrics["accuracy"], result.device_used)

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
# All five return TrainingResult with device_used populated

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
        tracker: ExperimentTracker | None = None,
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

| Condition                                                   | Exception                                |
| ----------------------------------------------------------- | ---------------------------------------- |
| `fit()` called before `setup()`                             | `EngineNotSetUpError`                    |
| `family=` and `trainable=` both supplied                    | `ConflictingArgumentsError`              |
| Target column missing from data                             | `TargetNotFoundError(column=, columns=)` |
| Target column included in features                          | `TargetInFeaturesError(column=)`         |
| Requested `accelerator="cuda"` but no CUDA device available | `AcceleratorUnavailableError`            |
| `tenant_id` missing for multi-tenant model                  | `TenantRequiredError` (see §5)           |
| Registered model not found                                  | `ModelNotFoundError(name=, version=)`    |
| ONNX export failure when `format="onnx"` and not `"both"`   | `OnnxExportError(framework=, cause=)`    |
| Schema drift between `setup()` and `fit()`                  | `SchemaDriftError(before=, after=)`      |

---

## 3. `Trainable` Protocol

Every model family that can be fitted by `MLEngine.fit()` MUST implement the `Trainable` protocol. This protocol is the single place where the Lightning-core invariant is enforced.

### 3.0 Phase 1 Family Roster (kailash-ml ≥ 0.12.0)

The Phase 1 GPU-first roster is fixed at seven public Trainable family adapters, all exported from `kailash_ml.trainable` and listed in `kailash_ml.__all__`:

| Family    | Class                | Backend support                                                         | Notes                                           |
| --------- | -------------------- | ----------------------------------------------------------------------- | ----------------------------------------------- |
| sklearn   | `SklearnTrainable`   | CPU + Array API allowlist on non-CPU backends                           | See ml-backends.md §5.1                         |
| xgboost   | `XGBoostTrainable`   | CPU + CUDA, OOM single-retry to CPU                                     | See ml-backends.md §5.2                         |
| lightgbm  | `LightGBMTrainable`  | CPU + CUDA/ROCm, OOM single-retry to CPU                                | See ml-backends.md §5.3                         |
| torch     | `TorchTrainable`     | All 6 (cuda/mps/rocm/xpu/tpu/cpu)                                       | DL spine; native multi-backend                  |
| lightning | `LightningTrainable` | All 6 (cuda/mps/rocm/xpu/tpu/cpu)                                       | DL spine; native multi-backend                  |
| umap      | `UMAPTrainable`      | CPU only (Phase 1) — non-CPU requests log `cuml_eviction` and fall back | See ml-backends.md §5.7. Phase 2 → torch-native |
| hdbscan   | `HDBSCANTrainable`   | CPU only (Phase 1) — non-CPU requests log `cuml_eviction` and fall back | See ml-backends.md §5.8. Phase 3 → torch-native |

Adding a new family is a spec amendment to this table AND a `tests/regression/test_trainable_device_report_invariant.py` AST update to enumerate the new class.

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

#### 1. Every Non-Torch Family MUST Be Wrapped As A LightningModule At The Engine Boundary

`to_lightning_module()` is mandatory on every `Trainable`. Non-torch families (sklearn, xgboost, lightgbm, catboost) MUST provide a LightningModule adapter (`SklearnLightningAdapter`, `XGBoostLightningAdapter`, `LightGBMLightningAdapter`, `CatBoostLightningAdapter`) that wraps a single-epoch fit in a LightningModule's `training_step`.

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

**Why:** A Trainable that bypasses `L.Trainer` also bypasses the accelerator contract — see §2.1 MUST 7. The adapter is the architectural enforcement of "Lightning as spine."

#### 2. Custom Training Loops That Bypass Lightning Are BLOCKED

A `Trainable` MUST NOT implement its own training loop (`for epoch in range(...)`, custom optimizer stepping, custom gradient accumulation) inside `fit()`. Custom logic lives inside the `LightningModule`'s `training_step` / `validation_step` — `L.Trainer` drives the outer loop.

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

# DO NOT — custom training loop in fit()
class MyTrainable:
    def fit(self, data, *, hyperparameters, context):
        model = MyModel()
        opt = torch.optim.Adam(model.parameters())
        for epoch in range(hyperparameters["epochs"]):   # BLOCKED
            for batch in data_loader:
                loss = model(batch)
                loss.backward()
                opt.step()
```

**BLOCKED rationalizations:**

- "My model has unusual scheduling Lightning can't express"
- "L.Trainer adds overhead I don't need"
- "This is research code, we'll Lightning-ify later"
- "The custom loop is just for initialization"

**Why:** Every custom loop is a new device-management surface. The v0.9.x audit showed that even a single branch that bypassed `L.Trainer` (the lightgbm branch at `training_pipeline.py:501`) had its own partial device story, and that story was wrong (GPU-only via string flag, no MPS/ROCm). One trainer, one enforcement point.

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

#### 4. `TrainingContext` MUST Carry Accelerator / Precision / Tenant / Tracker Through To The Trainable

`fit(data, *, hyperparameters, context)` receives a `TrainingContext` dataclass with the Engine's resolved accelerator, precision, devices, tenant_id, tracker run_id, and trial number. Trainables MUST NOT re-resolve the device themselves (e.g. calling `torch.cuda.is_available()` inside `fit()` is BLOCKED).

**Why:** Device resolution belongs to `ml-backends.md::detect_backend()`. Trainables that re-resolve can disagree with the Engine (e.g. Engine picked MPS, Trainable re-resolved to CPU because it only checked CUDA), causing split-brain behaviour where the TrainingResult reports one device but the tensors ran on another.

---

## 4. `TrainingResult` Dataclass

`TrainingResult` is the single envelope every training path produces. Its fields are frozen contract; adding, renaming, or reordering fields is a spec amendment.

### 4.1 Definition

```python
@dataclass(frozen=True)
class TrainingResult:
    # Required fields — every path MUST populate these
    model_uri: str                        # registry-relative URI, e.g. "models://User/v3"
    metrics: dict[str, float]             # {"accuracy": 0.92, "f1": 0.87, "auc": 0.94}
    device_used: str                      # "cuda:0", "mps", "cpu", "rocm:1", "xpu:0", "xla:0"
    accelerator: str                      # "cuda", "mps", "rocm", "xpu", "tpu", "cpu"
    precision: str                        # "bf16-mixed", "fp16-mixed", "fp32", "64-true"
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

    # GPU-first Phase 1 transparency contract (kailash-ml ≥ 0.12.0)
    device: DeviceReport | None = None    # per-call evidence; populated by every Phase 1 family
```

`DeviceReport` is defined in `kailash_ml._device_report` and carries the post-resolution evidence of what backend / precision / fallback ACTUALLY ran (vs `device_used` which is only the device string). Fields:

- `family: str` — `"sklearn"`, `"xgboost"`, `"torch"`, etc.
- `backend: str` — concrete value from `_device.KNOWN_BACKENDS` (never `"auto"`)
- `device_string: str` — torch device string actually used
- `precision: str` — concrete precision string (never `"auto"`)
- `fallback_reason: str | None` — `"oom"`, `"cuml_eviction"`, `"array_api_offlist"`, `"array_api_runtime_unavailable"`, `"driver_missing"`, `"unsupported_family"`, or `None`
- `array_api: bool` — `True` iff sklearn's `config_context(array_api_dispatch=True)` engaged for this call

### 4.2 MUST Rules

#### 1. Every Training Path MUST Populate All Required Fields

Every code path that produces a `TrainingResult` MUST populate all ten required fields. Leaving a required field as `None` is BLOCKED; the path MUST raise rather than return a partially-populated result.

```python
# DO — raise when a required field cannot be populated
result = trainable.fit(data, hyperparameters=hp, context=ctx)
if result.device_used is None:
    raise IncompleteTrainingResultError(
        "device_used not populated — Trainable must resolve device from context.accelerator"
    )

# DO NOT — emit a half-populated TrainingResult and continue
return TrainingResult(
    model_uri=uri, metrics=metrics,
    device_used=None,          # BLOCKED — downstream assumes this is populated
    accelerator="auto", precision="auto",
    elapsed_seconds=t, tracker_run_id=None, tenant_id=None,
    artifact_uris={}, lightning_trainer_config={},
)
```

**Why:** `device_used` being None silently turns `km.train(df)` into a debugging ordeal: the user sees training completed but cannot tell whether their GPU was actually used. The v0.9.x release shipped without this field entirely, which is exactly the bug class this rule prevents.

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

#### 5. Every Phase 1 Family Adapter MUST Populate `device`

Every `Trainable.fit()` implementation MUST construct and attach a `DeviceReport` to the returned `TrainingResult.device` field. The adapter MUST set `fallback_reason` to a machine-parseable string when a non-CPU request was downgraded:

| Family    | Standard `fallback_reason` codes                         |
| --------- | -------------------------------------------------------- |
| sklearn   | `"array_api_offlist"`, `"array_api_runtime_unavailable"` |
| xgboost   | `"oom"`                                                  |
| lightgbm  | `"oom"`                                                  |
| torch     | (none — native multi-backend; no fallback path)          |
| lightning | (none — native multi-backend; no fallback path)          |
| umap      | `"cuml_eviction"`                                        |
| hdbscan   | `"cuml_eviction"`                                        |

```python
# DO — populate device on every return path
return TrainingResult(
    ..., device=DeviceReport(
        family=self.family_name,
        backend=resolved_backend,
        device_string=resolved_device_string,
        precision=resolved_precision,
        fallback_reason=fallback_reason,  # None when no downgrade
        array_api=array_api_engaged,
    ),
)

# DO NOT — return TrainingResult without device=
return TrainingResult(...)  # silently leaves device=None — orphan
```

**Why:** A `TrainingResult.device == None` from a family that the spec covers means callers cannot distinguish actual-CUDA-execution from silent-CPU-fallback. The orphan failure mode of `rules/orphan-detection.md` §1 applies at the field level: the public `DeviceReport` symbol must be wired into the production hot path of every Trainable family. `tests/regression/test_trainable_device_report_invariant.py` enforces this at AST level — every `TrainingResult(...)` constructor in `trainable.py` MUST carry `device=`. Origin: round-3 redteam (2026-04-19) caught TorchTrainable + LightningTrainable returning `TrainingResult` without `device=` even though the Phase 1 punch list assumed they were already wired.

#### 6. `Predictions.device` — Deferred to 0.12.1

The `Predictions` class shipped in 0.12.0 does NOT carry a `device` field. The spec mandate "every predict returns one" applies to the post-fit predict surface and is scheduled for kailash-ml 0.12.1. Callers in 0.12.0 MUST inspect the prior `TrainingResult.device` to determine the device the model was trained on; this is sufficient for the immediate-after-fit case but insufficient for serialized-then-restored model scenarios. Tracked in `workspaces/kailash-ml-gpu-stack/journal/0005-GAP-predictions-device-field-missing.md`.

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

where `{tenant_id}` is either the resolved tenant string or the literal `"global"` for single-tenant mode. The string `"default"` is BLOCKED.

```python
# DO — "global" for the unambiguous single-tenant namespace
key = f"kailash_ml:v1:global:model:User:v3"

# DO NOT — "default" (silent cross-tenant merge per rules/tenant-isolation.md)
key = f"kailash_ml:v1:default:model:User:v3"
```

**Why:** `rules/tenant-isolation.md` MUST Rule 2 blocks "default" as a silent fallback. `"global"` is the explicit, auditable opt-out for single-tenant deployments.

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

**Implementation status (verified 2026-04-17 — redteam):** Phase 3 wires sklearn / xgboost / lightgbm / torch / lightning families through the Lightning Trainer with the resolver (§3 MUST 2 holds). **RL is not yet wired — HIGH finding**: `kailash_ml.rl.RLTrainer` does NOT consult `detect_backend()`, does NOT flow through `MLEngine`/`ModelRegistry`/`ExperimentTracker`, and returns `RLTrainingResult` rather than the unified `TrainingResult` (§4 contract). The orphan state is pinned by `tests/regression/test_rl_orphan_guard.py` until Phase 6 (redesign proposal §9) wires `km.rl.Engine` and flips the guard tests into wiring assertions per `rules/facade-manager-detection.md` § 1. Same finding applies to `kailash_ml.agents.*` — zero production call sites inside `engines/*`.

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

kailash-ml 2.0 replaces the v0.9.x 18-class public surface. Existing consumers (aegis, aether, kz-engage) depend on direct primitive imports. This section defines the deprecation contract.

### 8.1 MUST Rules

#### 1. `kailash_ml.legacy.*` MUST Exist For Every Removed Top-Level Public Symbol

Every v0.9.x public symbol that is demoted or removed in 2.0 MUST remain importable from `kailash_ml.legacy.*` for the entire 2.x series (removable at 3.0).

```python
# DO — v1.x callers still work against 2.0
from kailash_ml.legacy import AutoMLEngine, FeatureStore, ModelRegistry  # 1.x shape

# DO — v2.0 canonical imports
from kailash_ml import Engine, FeatureStore, ModelRegistry  # 2.0 shape

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

| v0.9.x import                                   | v2.0 equivalent                    |
| ----------------------------------------------- | ---------------------------------- |
| `from kailash_ml import AutoMLEngine`           | `engine.compare() → .finalize()`   |
| `from kailash_ml import TrainingPipeline`       | `engine.fit()`                     |
| `from kailash_ml import HyperparameterSearch`   | `engine.compare(hp_search="...")`  |
| `from kailash_ml import EnsembleEngine`         | `kailash_ml.primitives.Ensemble`   |
| `from kailash_ml import ClusteringEngine`       | `kailash_ml.primitives.Transform`  |
| `from kailash_ml import AnomalyDetectionEngine` | `kailash_ml.primitives.Transform`  |
| `from kailash_ml import DimReductionEngine`     | `kailash_ml.primitives.Transform`  |
| `from kailash_ml import PreprocessingPipeline`  | `engine.setup()`                   |
| `from kailash_ml import DataExplorer`           | `kailash_ml.primitives.Explorer`   |
| `from kailash_ml import ModelVisualizer`        | `kailash_ml.primitives.Visualizer` |
| `from kailash_ml import ModelExplainer`         | `kailash_ml.primitives.Explainer`  |
| `from kailash_ml import FeatureEngineer`        | `kailash_ml.primitives.FeatureGen` |

### 8.3 Preserved Symbols

These v0.9.x symbols remain public at the top level (no `legacy.` prefix needed):

- `FeatureStore`, `ModelRegistry`, `ExperimentTracker`, `InferenceServer`, `DriftMonitor` — all retained as Primitives that the Engine owns but are still importable.
- `FeatureSchema`, `FeatureField`, `ModelSignature`, `MetricSpec` — shared type contracts.
- `rl.Engine` — new in 2.0.

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

### 10.4 OPEN QUESTIONS — Decisions Needed From Human

The audit proposal §10 flagged six decisions. The following open questions remain in this spec and MUST be resolved before implementation begins:

1. **Default backend priority order.** This spec uses `cuda → mps → rocm → xpu → tpu → cpu`. If different shops prefer TPU-first, the constant MUST move to `kailash_ml/_backend_order.py` and be user-configurable via env var. DECIDE: lock the order, or make it configurable?
2. **Lightning hard lock-in.** §3 MUST 2 blocks custom training loops. Research users may need an escape hatch. DECIDE: BLOCKED with no exception (clean), or `kailash_ml.primitives.escape_hatch.RawTrainer` with an explicit warning?
3. **`ExperimentTracker` protocol surface in Rust.** Rust's async story diverges (tokio vs asyncio); does the Python async-context-manager map to `impl AsyncDrop` or to explicit `start_run` / `end_run`? DECIDE at the kailash-rs mirror spec.
4. **`engine.serve(channels=["grpc"])` scope.** Does gRPC-serving require a Nexus integration, or does it live as a standalone gRPC server inside `InferenceServer`? DECIDE: defer to `ml-serving.md` draft.
5. **Single-spec vs split-spec for cross-SDK.** This document is currently single-spec-with-§10. Alternative: `specs/ml-engines.md` (shared) + `specs/ml-engines-python.md` (this spec without §10.2) + `specs/ml-engines-rust.md`. DECIDE at loom/ classification time.
6. **Legacy namespace sunset.** §8 MUST 3 locks removal to 3.0. If downstream migration finishes in 2.1, can 2.2 drop the legacy namespace early with a 2.1→2.2 MINOR bump? DECIDE: lock to 3.0, or allow earlier if all three in-repo consumers migrate?

---

## 11. Cross-References

Every reference below points to another spec or rule that this spec depends on but does not duplicate.

- **`ml-backends.md`** — device resolution, `detect_backend()`, per-backend tensor conversion, GPU memory estimation. This spec's §2 `accelerator=`, §3 `TrainingContext`, and §4 `TrainingResult.device_used` / `accelerator` / `precision` all delegate to `ml-backends.md` for resolution semantics.
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

## 12. Spec Conformance Checklist

This checklist is the structural gate for kailash-ml 2.0.0 release. Every item MUST pass before tagging.

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

---

_End of ml-engines-v2-draft.md_
