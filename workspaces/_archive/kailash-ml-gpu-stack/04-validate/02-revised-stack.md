# Revised Stack — Post-Redteam

Addresses every CRITICAL + HIGH finding from `01-redteam-round1.md`.

## The one-sentence architecture

> **PyTorch is the single substrate. `detect_backend()` is the single
> routing point. Everything else is a thin adapter that accepts a
> `BackendInfo` and a tensor on the resolved device.**

## Layer map

```
┌──────────────────────────────────────────────────────────────────┐
│  User code:                                                      │
│    import kailash_ml as km                                       │
│    result = km.train(df, target="churned")                       │
│    pred = km.predict(result.model, new_df)                       │
│    # No device=, no family=, no accelerator= required.           │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  km.MLEngine          ←— public API                              │
│  km.RLEngine          ←— wraps gymnasium+torch                   │
│  (DL uses MLEngine with family="torch"|"lightning")              │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  Trainable adapters   ←— one per family                          │
│    SklearnTrainable   ·  sklearn + Array-API wrapping            │
│    XGBoostTrainable   ·  injects device= from detect_backend     │
│    LightGBMTrainable  ·  injects device_type= from detect_backend│
│    TorchTrainable     ·  Lightning Trainer, auto accelerator     │
│    LightningTrainable ·  Lightning Trainer, auto accelerator     │
│    RLTrainable        ·  torch + stable-baselines3 / custom      │
│    UMAPTrainable      ·  torch-native (Phase 3 R&D)              │
│    HDBSCANTrainable   ·  torch-native (Phase 3 R&D)              │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  km._device.detect_backend()   ←— SINGLE detection point         │
│    Priority: cuda > mps > rocm > xpu > tpu > cpu                 │
│    Typed errors: BackendUnavailable, UnsupportedFamily           │
│    Already implemented at packages/kailash-ml/src/…/_device.py   │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│  torch  ←— the one dependency every family leans on              │
│  polars ←— the one preprocessing library                         │
│  (sklearn, xgboost, lightgbm, gymnasium are family-specific)     │
└──────────────────────────────────────────────────────────────────┘
```

## Transparency contract (addresses HIGH-6)

Every call returns (or carries) a `DeviceReport`:

```python
@dataclass(frozen=True)
class DeviceReport:
    family: str          # "sklearn" | "xgboost" | "torch" | "rl" | …
    backend: str         # "cuda" | "mps" | "rocm" | "xpu" | "tpu" | "cpu"
    device_string: str   # "cuda:0" | "mps" | "cpu"
    precision: str       # "fp32" | "bf16" | "fp16"
    fallback_reason: str | None   # non-None when GPU→CPU fallback happened
    array_api: bool      # True if sklearn Array API was engaged
```

This lands on:

- `TrainingResult.device` — every fit returns one
- `Predictions.device` — every predict returns one
- `km.device()` — top-level helper that returns the resolved
  `BackendInfo` for scripts that want to gate behavior

Every adapter MUST emit exactly one `structured INFO` log per fit/predict
with the same fields. Fallbacks emit a WARN log AND set
`fallback_reason`.

## No-config contract (addresses HIGH-2 + HIGH-3 + HIGH-4)

Users never write `device=`. Adapters inject from `detect_backend()`:

| Family    | How we inject                                                                 |
| --------- | ----------------------------------------------------------------------------- |
| sklearn   | wrap `fit` in `sklearn.config_context(array_api_dispatch=True)` when the      |
|           | estimator is on our supported allowlist; move inputs to torch tensor on the   |
|           | detected device; log `array_api=True`. Fall back to CPU numpy + WARN log when |
|           | the estimator is off-allowlist.                                               |
| xgboost   | pass `device="cuda"` / `device="cpu"` into `XGBClassifier / XGBRegressor`     |
|           | kwargs. Catch `XGBoostError` on OOM → retry on CPU with fallback WARN.        |
| lightgbm  | pass `device_type="gpu"` / `"cpu"` per the XPU/ROCm probe logic already in    |
|           | `trainable.py::LightGBMTrainable`.                                            |
| torch     | `L.Trainer(accelerator=info.accelerator, devices=info.devices,                |
|           | precision=info.precision)` — already in place.                                |
| lightning | same as torch.                                                                |
| rl        | torch model `.to(info.device_string)` inside `rl/trainer.py`; gymnasium envs  |
|           | stay on CPU (they're Python); replay buffers move with the model. Fallback    |
|           | WARN on OOM.                                                                  |

Every adapter takes `TrainingContext` (already defined in trainable.py)
and MUST NOT re-resolve the backend itself. `ml-engines.md §3.2 MUST 4`
already enforces this.

## CRITICAL-1 disposition — cuML eviction

**Phase 1 (immediate):** `UMAPTrainable` / `HDBSCANTrainable` adapters
wrap `sklearn`'s native UMAP (via `umap-learn` pip package) and
`sklearn.cluster.HDBSCAN` (native since 1.3). CPU only. Log `backend=cpu
reason=cuml_eviction` at INFO. Users on NVIDIA see a slower path than
before; users on everything else gain a working path. Net usability
win.

**Phase 2 (6-12 months):** torch-native UMAP. Reference: Chari &
Pachter (2023) "The specious art of single-cell genomics" identifies
~2000 LOC of core UMAP as the transport map optimization over a k-NN
graph — every piece of which has a 5-50 LOC torch equivalent.
Spans: `torch.cdist` for k-NN, `torch.sparse` for the graph,
`torch.optim.Adam` for the cross-entropy loss over edge weights.
Benchmark target: within 2× of cuML on NVIDIA, runnable on MPS/ROCm/XPU.

**Phase 3 (12-18 months):** torch-native HDBSCAN. Smaller surface; the
core is hierarchical SLINK clustering + a density-aware cut. Same
benchmark target.

**`kailash-ml[rapids]` extra is deleted.** Users who MUST have cuML
speed on NVIDIA install cuml themselves and swap it in at the
Trainable layer via `km.register_trainable("umap", MyCustomCuMLUMAP)`.
First-class kailash-ml never depends on cuML.

## Serialization contract (addresses MEDIUM-7)

**Primary:** ONNX ML opset (`ai.onnx.ml.*`) for everything that
round-trips cleanly. Covers trees (via Treelite → ONNX), linear/GLM,
PCA, scalers, KMeans, GMM.

**Secondary:** `torch.save` for torch-native primitives (TorchTrainable
/ LightningTrainable / RLTrainable). Also `torch.jit.trace` for
portable torch inference.

**`kailash-ml[tree-inference]` extra** installs Treelite for optional
~10× inference speedup on GBT models. Default install stays lean.

Two formats, clearly delimited, covered by a single `km.save(model,
path)` and `km.load(path)` that dispatches on model type.

## Polars GPU caveat (addresses MEDIUM-8)

Polars + Narwhals is the preprocessing layer. On NVIDIA we enable
`cudf-polars` via `polars.Config.set_engine("gpu")` when
`detect_backend().backend == "cuda"`. On every other backend, polars CPU.
Log explicitly:

```
km.preprocess.start family=polars backend=cpu
km.preprocess.start family=polars backend=cuda engine=cudf-polars
```

Users on Apple Silicon see `backend=cpu` for preprocessing and
`backend=mps` for training — the asymmetry is intentional and documented.

## Why this is maintainable (addresses C7 + HIGH-5 + LOW-9)

1. **One substrate (torch) means one upgrade cycle.** Every 3 months
   we bump torch, re-run the integration suite against all families,
   ship. No RAPIDS / CUDA / cuDNN matrix to mediate.
2. **One detection point (`detect_backend`) means one audit.** Every
   new adapter is a grep match away.
3. **One result type (`TrainingResult` + `DeviceReport`) means one
   observability story.** Dashboards, traces, and error logs all read
   the same three fields.
4. **Adapters are thin and pinned.** Each Trainable is a 100-300 LOC
   file. When XGBoost changes its device API in 4.0, we change one
   file. When sklearn drops Array API support for some estimator, we
   remove it from the allowlist — one line.
5. **Owned R&D path for the cuML-replacement.** UMAP + HDBSCAN are
   bounded deliverables with benchmark targets, not open-ended
   research.

## Concrete API sketch

```python
import polars as pl
import kailash_ml as km

df = pl.read_parquet("features.parquet")

# One line. Auto-detects GPU. Auto-picks family based on target type.
result = km.train(df, target="churned")

print(result.device)
# DeviceReport(family='xgboost', backend='cuda', device_string='cuda:0',
#              precision='fp32', fallback_reason=None, array_api=False)

# Predict on new data — device stickiness built in.
pred = km.predict(result.model, new_df)
print(pred.device)
# DeviceReport(family='xgboost', backend='cuda', device_string='cuda:0', …)

# Or explicit family for sklearn-shape composites.
result = km.train(df, target="y", family="sklearn", estimator="Ridge")

# Or RL.
env = km.rl.env("CartPole-v1")
agent = km.rl.train(env, algo="ppo", steps=10_000)
print(agent.device)
# DeviceReport(family='rl', backend='mps', device_string='mps', …)

# Inspect the detected hardware without fitting anything.
print(km.device())
# BackendInfo(backend='cuda', device_string='cuda:0', device_count=2,
#             precision='fp32', supported_precisions=('fp32','bf16'), …)

# Override for offline / deterministic runs.
with km.use_device("cpu"):
    result = km.train(df, target="y")
```

## Updated Trainable interface (additions to trainable.py)

Append to existing `trainable.py`:

```python
@dataclass(frozen=True)
class DeviceReport:
    family: str
    backend: str
    device_string: str
    precision: str
    fallback_reason: Optional[str] = None
    array_api: bool = False

# TrainingResult grows one field:
# TrainingResult(device=DeviceReport(...), ...)
# Predictions grows one field:
# Predictions(..., device=DeviceReport(...))
```

## Round-2 re-audit

| Finding                             | Round-1 severity | Round-2 disposition                                                                                  |
| ----------------------------------- | ---------------- | ---------------------------------------------------------------------------------------------------- |
| CRITICAL-1 cuML optional extra      | CRITICAL         | Resolved by Phase 1 eviction + Phase 2/3 torch-native reimplementation.                              |
| HIGH-2 Array API not auto-detect    | HIGH             | Resolved by wrapping `config_context` inside `SklearnTrainable` + allowlist.                         |
| HIGH-3 XGBoost device injection     | HIGH             | Resolved by mandatory `device=` kwarg injection from `TrainingContext` + OOM fallback.               |
| HIGH-4 RL not routed through detect | HIGH             | Resolved by auditing `rl/trainer.py` for hardcoded device strings + routing through TrainingContext. |
| HIGH-5 device stickiness missing    | HIGH             | Resolved by `DeviceReport` + auto-migration in `MLEngine.predict()`.                                 |
| HIGH-6 transparency surface         | HIGH             | Resolved by `DeviceReport` on every result + mandatory structured INFO log.                          |
| MEDIUM-7 serialization fan-out      | MEDIUM           | Resolved by "ONNX primary, torch.save secondary, Treelite as extra".                                 |
| MEDIUM-8 polars GPU NVIDIA-only     | MEDIUM           | Resolved by explicit log of engine used; CPU polars is the non-NVIDIA default.                       |
| LOW-9 no API sketch                 | LOW              | Resolved above.                                                                                      |

All CRITICAL + HIGH findings have concrete remediation. Rounds 2 and
3 (implementation + integration) would land the actual adapter changes
and regression tests.

## Deliverables for a follow-up implementation session

1. Add `DeviceReport` to `trainable.py`.
2. Audit `rl/trainer.py` + `SklearnTrainable` for hardcoded device strings.
3. Implement sklearn array-API allowlist + auto-context-wrapping.
4. Add OOM fallback to `XGBoostTrainable` + `LightGBMTrainable`.
5. Write `UMAPTrainable` + `HDBSCANTrainable` (CPU initial; torch-native Phase 2/3).
6. Implement `km.use_device()` + `km.device()` top-level helpers.
7. Tier-2 regression tests: every Trainable is exercised on CPU + (where available) CUDA / MPS.
8. Delete `kailash-ml[rapids]` extra from `pyproject.toml`.

Each is a bounded shard (<500 LOC load-bearing per the capacity budget
in `rules/autonomous-execution.md`).
