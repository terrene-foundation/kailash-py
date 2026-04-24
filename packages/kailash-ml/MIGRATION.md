# kailash-ml Migration Guide: 0.x -> 1.0.0

This guide documents every breaking change between the 0.x primitive-heavy API
(0.9.x -- 0.17.x) and the 1.0.0 Engine-first API. Every breaking change below
has a before/after code sample; follow the sequence top-to-bottom for a safe
upgrade.

See `CHANGELOG.md` for the release-specific version bump and release notes.

## Deprecation timeline

| Version | Status of legacy `kailash_ml.legacy.*` namespace                                |
| ------- | ------------------------------------------------------------------------------- |
| 1.0.0   | Legacy primitives re-exported under `kailash_ml.legacy.*`, no warning on import |
| 2.x     | Legacy imports emit `DeprecationWarning` on first use (per module)              |
| 3.0     | Legacy namespace **removed**. All imports MUST use the Engine-first API         |

You have the full 2.x line to migrate. Every deprecation warning names the
1.0.0 Engine-first replacement in its message, so the minimum friction path
is: upgrade to 2.x, run the test suite, address each warning at its first
call site, and you land cleanly on 3.0 without touching the migration again.

## Install and verify

```bash
pip install --upgrade "kailash-ml>=1.0.0"
python -c "import kailash_ml as km; print(km.__version__)"
```

The Quick Start in `README.md` is the canonical smoke-test for a working
install. It runs end-to-end against real infrastructure on every CI matrix
job (see `tests/regression/test_readme_quickstart_executes.py`).

## Breaking change 1 -- Zero-arg construction replaces manual plumbing

The 0.x API required the caller to construct `ConnectionManager`,
`LocalFileArtifactStore`, `FeatureStore`, `ModelRegistry`, and
`ExperimentTracker` before any training call. The 1.0.0 Engine owns this
plumbing. **Do NOT construct these primitives in application code.** The
Engine caches a tenant-scoped default instance per process.

```python
# 0.x -- six-import plumbing
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore
from kailash_ml.engines.model_registry import ModelRegistry
from kailash_ml.engines.experiment_tracker import ExperimentTracker
from kailash_ml.engines.training_pipeline import TrainingPipeline
from kailash_ml.artifacts import LocalFileArtifactStore

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
fs = FeatureStore(conn)
await fs.initialize()
registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()
tracker = ExperimentTracker(conn)
await tracker.initialize()
pipeline = TrainingPipeline(feature_store=fs, model_registry=registry, experiment_tracker=tracker)

result = await pipeline.train(schema=..., model_spec=..., eval_spec=...)
```

```python
# 1.0.0 -- zero-arg Engine
import kailash_ml as km

async with km.track("demo") as run:
    result = await km.train(df, target="y")
    registered = await km.register(result, name="demo")
server = await km.serve("demo@production")
```

**Why the change:** Every competitor shipped a zero-ceremony quick start; the
0.x six-import form discouraged newcomers and leaked infrastructure concerns
into application code. The Engine owns the lifecycle; override the store
location via `KAILASH_ML_STORE_URL` and artifact root via
`KAILASH_ML_ARTIFACT_ROOT` if the defaults don't suit your deployment.

## Breaking change 2 -- `km.*` wrappers replace direct primitive methods

The 1.0.0 public surface is the `km.*` wrapper set. Every wrapper dispatches
into the cached default Engine for the current tenant. You may still import
the underlying Engine classes for advanced cases, but the wrappers are the
supported API.

| 0.x entry point                   | 1.0.0 replacement                          |
| --------------------------------- | ------------------------------------------ |
| `pipeline.train(...)`             | `await km.train(df, target=...)`           |
| `tracker.run(...)`                | `async with km.track(name):`               |
| `registry.register_version(...)`  | `await km.register(result, ...)`           |
| `server.start(...)`               | `await km.serve(model_uri)`                |
| `monitor.check_drift(...)`        | `await km.watch(...)`                      |
| `explorer.profile(...)`           | `await km.diagnose(df)`                    |
| `tracker.log_metric(...)` (auto)  | `await km.autolog(...)`                    |
| manual seeding                    | `km.seed(...)`                             |
| manual re-run from a prior run_id | `await km.reproduce(run_id)`               |
| manual checkpoint reload          | `await km.resume(run_id)`                  |
| RL `trainer.train(...)`           | `await km.rl_train(...)`                   |
| discover engines in-process       | `km.engine_info(...)`, `km.list_engines()` |

```python
# 0.x -- explicit training pipeline call
result = await pipeline.train(
    schema=FeatureSchema(name="churn", features=[...], target=...),
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)

# 1.0.0 -- km.train infers family + metrics from the DataFrame target dtype
result = await km.train(df, target="churned")
```

```python
# 0.x -- manual run scoping
run = await tracker.start_run(experiment="demo")
await tracker.log_metric(run.run_id, "accuracy", 0.95)
await tracker.finish_run(run.run_id)

# 1.0.0 -- ambient run via async context manager
async with km.track("demo") as run:
    await run.log_metric("accuracy", 0.95)
# finalisation is automatic on context exit
```

## Breaking change 3 -- `TrainingResult.device` is now a required field

The `TrainingResult` dataclass gained a required `device: DeviceReport` field
in the 0.11.0 line; the 0.9.x back-compat mirrors (`device_used`,
`accelerator`, `precision`) remain in 1.0.0 but are computed from
`TrainingResult.device`, not stored separately.

```python
# 0.x -- read the string mirror
print(result.device_used)  # "cpu" / "cuda:0" / "mps"

# 1.0.0 -- read the structured DeviceReport
print(result.device.backend)   # "cuda", "mps", "cpu", "rocm", "xpu", "tpu"
print(result.device.device_ids)  # ["cuda:0"]
print(result.device.capabilities)  # ["fp16", "fp8_e4m3", ...]

# 1.0.0 back-compat mirrors still work (drop in 3.0)
print(result.device_used)  # same value, computed from result.device
```

**Why the change:** The GPU-first Phase 1 transparency contract requires
every fit to report resolved backend + device ids + capabilities so the
caller can audit "did my training actually use the GPU I expected?". The
0.x string was insufficient (no capability list, no device ids).

## Breaking change 4 -- ONNX is the default `register()` format

`km.register(result, name=...)` serialises to ONNX by default. Call sites
that relied on the 0.x native-format default (`joblib` / `torch.save`) MUST
pass `format=` explicitly.

```python
# 0.x -- native format default
registered = await registry.register_version(result, name="demo")
# registered.artifact_uris["native"] is set; "onnx" is not

# 1.0.0 -- ONNX default
registered = await km.register(result, name="demo")
# registered.artifact_uris["onnx"] is set; native sidecar emitted when supported

# 1.0.0 -- opt back into native-only for export-incompatible families
registered = await km.register(result, name="demo", format="native")
```

**Why the change:** Cross-SDK interop. ONNX is the format kailash-rs loads;
shipping native-only 0.x artefacts locks downstream Rust consumers out.
Families that cannot export to ONNX raise `OnnxExportError` rather than
silently falling back to pickle -- see `ml-serving.md` for the failure
contract.

## Breaking change 5 -- Cache keys include `tenant_id` for multi-tenant models

Any model that sets `multi_tenant=True` in its feature schema now requires a
`tenant_id` argument on every read. Omitting the tenant raises
`TenantRequiredError` rather than silently sharing cache slots.

```python
# 0.x -- omitted tenant merged every read into a shared slot
rows = await db.express.list("Document")

# 1.0.0 -- tenant required on multi-tenant models
rows = await db.express.list("Document", tenant_id="acme-corp")

# 1.0.0 -- single-tenant models unchanged
rows = await db.express.list("BuildArtifact")  # no tenant_id required
```

See `rules/tenant-isolation.md` for the full multi-tenant contract.

## Breaking change 6 -- `km.seed` / `km.reproduce` / `km.resume` / `km.lineage` are module-level functions

Seeding, reproduction, resumption, and lineage queries are `km.*` module-level
functions, not methods on any engine class. They replace the 0.x pattern of
constructing a `RunnerContext` or passing `seed=` through every call.

```python
# 0.x -- seed threaded through every call
ctx = RunnerContext(seed=42)
result = await pipeline.train(schema=..., model_spec=..., ctx=ctx)

# 1.0.0 -- seed set once per process, read by every km.train / km.rl_train
km.seed(42)
result = await km.train(df, target="y")
```

```python
# 0.x -- manual reproduction by re-running the exact call
result = await pipeline.train(schema=..., model_spec=..., ctx=RunnerContext(seed=42))

# 1.0.0 -- km.reproduce reads the seed + hyperparameters from the prior run
previous = await km.reproduce(run_id="run-abc123")
# previous.metrics should match the original run within tolerance
```

```python
# 0.x -- manual checkpoint reload
ckpt = torch.load("artifacts/run-abc123/last.ckpt")
module = MyModule.load_from_checkpoint(ckpt)

# 1.0.0 -- km.resume reloads state and lineage-links the child run
continued = await km.resume("run-abc123", tolerance=1e-3, verify=True)
```

```python
# 1.0.0 -- lineage queries (no 0.x equivalent)
graph = await km.lineage(run_id="run-abc123")
# graph.parents, graph.children, graph.edges
```

## Breaking change 7 -- `km.engine_info` / `km.list_engines` replace ad-hoc discovery

The 0.x pattern of "import the class I need" is replaced by registry-based
discovery. This makes engine availability observable and testable.

```python
# 0.x -- import directly
from kailash_ml.engines.automl_engine import AutoMLEngine

# 1.0.0 -- discover what is available
for name in km.list_engines():
    info = km.engine_info(name)
    print(name, info.stability, info.import_path)
```

Direct imports still work for backwards compatibility; the registry is the
recommended surface for runtime engine selection.

## Breaking change 8 -- Legacy primitives live under `kailash_ml.legacy.*`

Every v0.9.x public symbol that was demoted in the 1.0.0 cut is re-exported
under `kailash_ml.legacy.*`. Imports from the old locations raise
`ImportError` at 1.0.0 (or emit `DeprecationWarning` if the old import path
was kept for one minor). At 3.0 the entire `kailash_ml.legacy.*` namespace is
removed; imports fail hard.

```python
# 0.x -- top-level primitive imports
from kailash_ml import FeatureStore, ModelRegistry, TrainingPipeline

# 1.0.0 -- primitives still re-exported at top level for 1.x compatibility
from kailash_ml import FeatureStore, ModelRegistry, TrainingPipeline  # works

# 2.x -- same imports emit DeprecationWarning pointing at km.* replacements
# DeprecationWarning: `FeatureStore` is moving to `kailash_ml.legacy.FeatureStore`.
# Use `km.train(...)` for the replacement Engine-first API. This import will be
# removed in kailash-ml 3.0.

# 3.0 -- imports removed; use the legacy namespace explicitly if you still need them
from kailash_ml.legacy import FeatureStore  # explicit opt-in; no DeprecationWarning
```

The migration sequence is deterministic:

1. Upgrade to 1.0.0 first -- nothing breaks, the primitives are still at the
   top level, and you can start using `km.*` where it helps.
2. Upgrade to 2.x when your test suite is clean on 1.0.0. Each
   `DeprecationWarning` names the replacement `km.*` entry point in its
   message; fix them at their first call site.
3. Upgrade to 3.0 when your codebase has zero deprecation warnings. If you
   still need a 0.x primitive, import from `kailash_ml.legacy.*` explicitly.

## Breaking change 9 -- Model class allowlist

Dynamic model imports (via `model_class` strings) are restricted to an
allowlist: `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `torch.`,
`lightning.`, `kailash_ml.`. Everything else raises `ValueError` at
`validate_model_class()` time.

```python
# 0.x -- arbitrary classes accepted
model_spec = ModelSpec(model_class="myapp.models.CustomRegressor")

# 1.0.0 -- not on the allowlist, raises at register-time
model_spec = ModelSpec(model_class="myapp.models.CustomRegressor")
# ValueError: model class 'myapp.models.CustomRegressor' not in allowlist

# 1.0.0 -- register your custom estimator explicitly
from kailash_ml import register_estimator
register_estimator("myapp.models.CustomRegressor", MyCustomRegressor)
model_spec = ModelSpec(model_class="myapp.models.CustomRegressor")  # now allowed
```

**Why the change:** Prevents arbitrary code execution via model class
strings supplied by an untrusted caller. The registry is the explicit
opt-in path for application-specific estimators.

## Breaking change 10 -- Financial / budget fields reject NaN and Inf

`AutoMLConfig.max_llm_cost_usd`, `GuardrailConfig.max_llm_cost_usd`, and
`GuardrailConfig.min_confidence` now run `math.isfinite()` on the supplied
value and raise `ValueError` on NaN / Inf.

```python
# 0.x -- NaN / Inf accepted, bypassed every budget check
config = AutoMLConfig(max_llm_cost_usd=float("nan"))

# 1.0.0 -- NaN / Inf rejected at construction time
config = AutoMLConfig(max_llm_cost_usd=float("nan"))
# ValueError: max_llm_cost_usd must be a finite float; got nan
```

**Why the change:** NaN bypasses all numeric comparisons; Inf defeats
upper-bound checks. Both silently disabled the cost budget.

## Cross-references

- `README.md` -- canonical Quick Start (fingerprinted against the spec).
- `CHANGELOG.md` -- release notes for each bump.
- `specs/ml-engines-v2.md` -- full 1.0.0 Engine contract.
- `specs/ml-backends.md` -- `DeviceReport` field semantics.
- `specs/ml-tracking.md` -- `ExperimentRun` + `km.track` contract.
- `specs/ml-serving.md` -- `km.serve` multi-channel contract.
- `rules/tenant-isolation.md` -- multi-tenant `tenant_id` discipline.
- `rules/orphan-detection.md` -- production-call-site requirement for `km.*`
  wrappers.

## Reporting migration gaps

If a 0.x pattern you rely on does not have a 1.0.0 replacement here, open an
issue at `https://github.com/terrene-foundation/kailash-py/issues` with the
`kailash-ml` + `migration` labels. The migration guide is append-only and
every reported gap lands a new § Breaking change entry before the next
release.
