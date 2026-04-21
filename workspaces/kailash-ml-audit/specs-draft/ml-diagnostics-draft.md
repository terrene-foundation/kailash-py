# Kailash ML Diagnostics — Training-Loop + Evaluation Diagnostics Adapters (v1)

Version: 1.0.0 (draft)
Package: `kailash-ml`
Parent domain: ML Lifecycle (`ml-engines.md` covers training; `ml-tracking.md` covers run history; `ml-backends.md` covers device resolution).
Scope authority: `kailash_ml.diagnostics.*` adapters, the module-level `km.diagnose` engine entry point, tracker-wiring contract, Lightning + transformers + accelerate callback integrations, classical-ML diagnosers, the `report()` Protocol shape, and industry-parity claims.

Status: DRAFT — authored at `workspaces/kailash-ml-audit/specs-draft/ml-diagnostics-draft.md`. Becomes `specs/ml-diagnostics.md` after human review. Supersedes the v0.17.0 spec in full. Closes Round-1 DL-researcher findings DL-1, DL-2, DL-7, DL-8, DL-9, DL-10, DL-11, DL-12; Newbie-UX findings F-DIAGNOSTICS-NO-DASHBOARD-SINK, F-DL-NO-AUTO-WIRE, F-DIAGNOSE-NO-TOPLEVEL; and Industry-parity table-stakes #3, #5, #7 (system metrics), #17 (distributed training).

Origin: Round-2 Phase-A authoring cycle, 2026-04-21. Pre-requisites: `ml-tracking.md` v2.0.0-draft (single canonical store, `ExperimentRun.log_metric`) MUST land first so tracker-wiring has a single target.

---

## THE engine entry is `km.diagnose`

`km.diagnose(subject, *, kind="auto", data=None, tracker=None, show=True, sensitive=False) -> Diagnostic` is the single one-line entry point for every diagnostic path in kailash-ml. Full spec at §3 below. Every READER of this file — whether drafting an implementation PR, auditing compliance, or integrating a new adapter — MUST use `km.diagnose(...)` as the canonical user-facing entry. Direct adapter imports (`DLDiagnostics(...)`, `diagnose_classifier(...)`) remain available as the underlying primitives and MAY be imported by power users, but the top-level surface is `km.diagnose`.

```python
import kailash_ml as km

# DO — one-line dispatch across every subject type (auto-detects adapter)
diag = km.diagnose(training_result)                               # -> Diagnostic
diag = km.diagnose(sklearn_model, data=(X_test, y_test))           # classical classifier/regressor
diag = km.diagnose(lightning_module, kind="dl")                   # forced dispatch
report = diag.report()                                             # frozen DiagnosticReport

# DO NOT — reach for adapters directly in user-facing documentation
from kailash_ml.diagnostics import DLDiagnostics
diag = DLDiagnostics(lightning_module)   # power-user path, NOT the default surface
```

Why this sits above §1: the Round-1 newbie-UX finding F-DIAGNOSE-NO-TOPLEVEL was P0 — a user typing `kailash_ml.diagnose(...)` into a notebook got `AttributeError`. Placing `km.diagnose` prominently at the top of this spec ensures every implementation PR sees it first.

Consolidation note: `km.diagnose` is the SOLE diagnostic entry point at package top-level. There is no `kailash_ml.diagnose_dl`, no `kailash_ml.explain`, no `kailash_ml.profile` — one verb, one argument, one dispatch table (§3.2). Every adapter's constructor remains available under `kailash_ml.diagnostics.*` for power users.

---

## 1. Scope

### 1.1 In Scope

- **DLDiagnostics (torch / Lightning)** — forward/backward hooks, tracker wiring, Lightning callback, transformers Trainer callback, DDP/FSDP rank awareness, mixed-precision safety, checkpoint/resume.
- **Classical-ML diagnosers** — `diagnose_classifier`, `diagnose_regressor`, `diagnose_clustering` on sklearn-compatible models.
- **RAGDiagnostics** — retained from v0.17.0; see §12 for the unchanged contract.
- **Engine-layer entry point** — `km.diagnose(run_or_result, *, kind="auto")` one-line dispatcher.
- **Module-level helpers** — `track_gradients`, `track_activations`, `track_dead_neurons` standalone.
- **Protocol conformance** — every adapter satisfies `kailash.diagnostics.protocols.Diagnostic`.
- **Industry parity matrix** — what kailash-ml delivers as engine-layer (auto) vs primitive-layer (opt-in) vs deferred.
- **Extras gating** — `[dl]`, `[rag]`, `[interpret]` with loud ImportError messages naming the extra.

### 1.2 Out of Scope

- **Training itself** — `ml-engines.md` owns `MLEngine`, `Trainable`, Lightning spine.
- **Tracker store, schema, `ExperimentRun` surface** — `ml-tracking.md` owns those.
- **Dashboard** — `ml-dashboard.md` owns the web UI and CLI.
- **RL diagnostics** — `ml-rl.md` owns `RLDiagnostics`; this spec only cross-references.
- **AlignmentDiagnostics, LLMDiagnostics, AgentDiagnostics, InterpretabilityDiagnostics** — sibling specs `alignment-diagnostics.md`, `kaizen-observability.md`, `kaizen-interpretability.md`, `kaizen-judges.md`.
- **The `Diagnostic` Protocol definition** — defined in `src/kailash/diagnostics/protocols.py` (PR#0 of issue #567); this spec references it as a dependency.

---

## 2. Protocol Conformance Contract

### 2.1 Diagnostic Protocol Shape

```python
@runtime_checkable
class Diagnostic(Protocol):
    run_id: str
    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]: ...
    def report(self) -> dict[str, Any]: ...
```

### 2.2 MUST Conformance Contract (every adapter)

1. `run_id: str` populated in `__init__` (UUID4 hex default, caller override verbatim).
2. `__enter__` returns `self`; `__exit__` never raises; `detach()` runs in `__exit__` for hook-installing adapters.
3. `report() -> DiagnosticReport` is callable on an empty session; MUST NOT raise; return shape is the frozen `DiagnosticReport` dataclass below.
4. `isinstance(obj, Diagnostic)` returns `True`. Tier 2 wiring test MUST assert this. **Because** `@runtime_checkable` on a Protocol with `__enter__`/`__exit__` will accept ANY class with those methods, every adapter MUST also expose a unique class-variable `adapter: ClassVar[str]` (values: `"dl"`, `"classical_classifier"`, `"classical_regressor"`, `"clustering"`, `"rl"`, `"rag"`, `"alignment"`, `"interpretability"`, `"llm"`, `"agent"`, `"fairness"`); `km.diagnose` MUST route on `obj.adapter` NOT `isinstance`.
5. Cross-SDK fingerprint stability — when `report()` output is serialized via the canonical `json.dumps(report.to_dict(), sort_keys=True, separators=(',', ':'))` shape and hashed with SHA-256, Python and Rust (when a Rust sibling exists) produce identical fingerprints for identical observations. The canonical serialisation pins float format at `f"{value:.17g}"` (IEEE 754 round-trippable shortest form), datetimes at `strftime("%Y-%m-%dT%H:%M:%S.%fZ")`, enum values as their string names. See §11 "Cross-SDK fingerprint parity" below.

### 2.3 Frozen `DiagnosticReport` Shape

Every adapter's `.report()` MUST return an instance of the shared dataclass below. Per-domain fields live under `summary` (free-form dict for that adapter's metrics) and `rollup` (adapter-specific severity rollups), with the five top-level keys fixed.

```python
from typing import Literal, ClassVar
from dataclasses import dataclass

Severity = Literal["ok", "warning", "critical"]

@dataclass(frozen=True)
class DiagnosticReport:
    schema_version: str              # "1.0" at v1.0.0; bumped for shape changes
    adapter: str                     # matches Diagnostic.adapter ClassVar
    run_id: str | None               # tracker run_id if bound, else None
    timestamp_iso: str               # strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    severity: Severity
    summary: dict[str, Any]          # adapter-specific metrics
    events: list[dict[str, Any]]     # time-ordered observations
    rollup: dict[str, Any]           # adapter-specific aggregate summary
    tracker_metrics: list[str]       # keys already emitted to ExperimentTracker

    def to_dict(self) -> dict[str, Any]:
        """Canonical fingerprint form. Float fields via `f'{x:.17g}'`; dict keys
        sorted; enums to their string name; datetime to the ISO-Z string above."""
        ...
```

**Why:** Downstream consumers (MLDashboard, W&B bridge, cross-SDK fingerprint parity) need a single index-able shape. Three different report shapes across adapters (DLDiagnostics emits `{grad_norm_mean,...}`, RLDiagnostics emits `{run_id, algo,...}`, ClassifierReport is a frozen dataclass) broke the generic telemetry pipeline. Fingerprint stability is the forensic-correlation contract from `rules/event-payload-classification.md` applied to diagnostic payloads.

---

## 3. `km.diagnose` Engine Entry Point

### 3.1 Signature

```python
import kailash_ml as km

km.diagnose(
    subject: Union[TrainingResult, Trainable, "lightning.LightningModule",
                   "torch.nn.Module", "sklearn.base.BaseEstimator", RunId, ExperimentRun],
    *,
    kind: Literal["auto", "dl", "classical_classifier", "classical_regressor",
                  "clustering", "rag", "rl", "alignment", "llm", "agent"] = "auto",
    data: Optional[Union["polars.DataFrame", tuple, "torch.utils.data.DataLoader"]] = None,
    tracker: Optional[ExperimentRun] = None,
    show: bool = True,
    sensitive: bool = False,
) -> Diagnostic
```

Returns the appropriate `Diagnostic` adapter, already run (for one-shot diagnosers) or opened as a context manager (for streaming ones). Caller accesses `.report()` / DataFrame accessors / `plot_*` from the return value.

### 3.2 Dispatch Table

`kind="auto"` inspects `subject` and data to select the adapter:

| `subject` type                                                      | `data`   | Dispatched adapter                                                   |
| ------------------------------------------------------------------- | -------- | -------------------------------------------------------------------- |
| `TrainingResult` with `framework in {"lightning", "torch"}`         | optional | `DLDiagnostics.from_training_result(subject, tracker=tracker)`       |
| `TrainingResult` with `framework == "sklearn"` and classifier model | `(X, y)` | `diagnose_classifier(subject.model, X, y, tracker=tracker)`          |
| `TrainingResult` with `framework == "sklearn"` and regressor model  | `(X, y)` | `diagnose_regressor(subject.model, X, y, tracker=tracker)`           |
| `TrainingResult` with `framework == "sklearn"` and clustering model | `X`      | `diagnose_clustering(subject.model, X, tracker=tracker)`             |
| `TrainingResult` with `framework == "rl"`                           | optional | `kailash_ml.rl.RLDiagnostics.from_training_result(...)` (cross-ref)  |
| `Trainable` / `torch.nn.Module` / `lightning.LightningModule`       | required | `DLDiagnostics(subject, tracker=tracker)` context manager            |
| `sklearn.base.ClassifierMixin`                                      | `(X, y)` | `diagnose_classifier(subject, X, y, tracker=tracker)`                |
| `sklearn.base.RegressorMixin`                                       | `(X, y)` | `diagnose_regressor(subject, X, y, tracker=tracker)`                 |
| `sklearn.base.ClusterMixin`                                         | `X`      | `diagnose_clustering(subject, X, tracker=tracker)`                   |
| `RunId` (string) or `ExperimentRun`                                 | optional | Re-hydrate adapter kind from run's `diagnostic_kind` metadata column |

`kind="dl"` / `"classical_classifier"` / ... forces the dispatch, bypassing inspection.

### 3.3 Rendering Contract

When `show=True` (default):

1. The adapter's canonical dashboard (`plot_training_dashboard` for DL; `plot_classifier_dashboard` for classical; etc.) is rendered inline via `fig.show()` if plotly is present.
2. Every metric the adapter captures is emitted to `tracker` via `tracker.log_metric(...)` if `tracker` is not None (§4 contract).
3. Every figure is emitted to `tracker` via `tracker.log_figure(name, fig)` if `tracker` is not None.
4. `tracker` defaults: if `tracker is None`, `km.diagnose` reads the ambient `km.track()` via the public accessor `kailash_ml.tracking.get_current_run()` per `ml-tracking.md §10.1` (CRIT-4); if that is also `None`, metrics are retained in-memory only and the adapter's log events emit a single INFO `ml_diagnose.no_tracker` (not WARN — untracked use is legitimate for ad-hoc notebook work). Direct access to `kailash_ml.tracking.runner._current_run` is BLOCKED for library callers.

### 3.4 Errors

- `TypeError` when `subject` is not a dispatchable type — error message lists the accepted types.
- `ValueError` when `kind="classical_classifier"` and the dispatched model is not a classifier (likewise for regressor / clustering).
- `ImportError` (from adapters) when the diagnostic kind requires an extra that is not installed — error message names the extra.

### 3.5 Why One Entry Point

The newbie-UX audit's single most-severe finding was F-DIAGNOSE-NO-TOPLEVEL (grep for `km.diagnose` returned zero). Every competitor product ships a one-line diagnostic entry (`mlflow.sklearn.log_model` with `signature=infer_signature(...)`, `wandb.sklearn.plot_classifier`, `comet.Experiment().log_confusion_matrix`). `km.diagnose` is the kailash-ml equivalent, kept at the top level of the package.

---

## 4. Tracker Wiring Contract

### 4.1 Construction

Every diagnostic adapter MUST accept `tracker: Optional[ExperimentRun] = None` as a keyword-only constructor argument. When omitted, the adapter resolves the ambient tracker from `kailash_ml.tracking.get_current_run()` (the contextvar set by `km.track()`). When the resolved tracker is `None`, the adapter runs in **no-tracker mode** (metrics + figures retained in-memory only).

```python
# DO — explicit tracker
async with km.track("my-exp") as run:
    diag = DLDiagnostics(model, tracker=run)

# DO — ambient tracker (contextvar)
async with km.track("my-exp") as run:
    diag = DLDiagnostics(model)   # auto-wires to run via get_current_run()

# DO — no tracker (notebook / ad-hoc)
diag = DLDiagnostics(model)   # metrics in-memory only; INFO log on first record_batch
```

**BLOCKED rationalizations:**

- "The user can just call `log_metric` manually after `record_batch`."
- "Auto-wiring from the contextvar is magical; explicit-tracker only is cleaner."
- "If the tracker is `None`, we should raise — users should always have one."

**Why:** Adapter constructors cannot require a tracker because notebook workflows legitimately have none. Auto-wiring from the contextvar is the `PyTorch Lightning Trainer(logger=...)` ergonomic equivalent — one kwarg (`async with km.track(): DLDiagnostics(model)`) gives full auto-log. Requiring an explicit `tracker=` breaks parity with Lightning's one-kwarg story.

### 4.2 Emission Contract

Every `record_batch` / `record_epoch` / `record_step` / one-shot diagnosis call MUST, when `tracker is not None`:

1. Call `await tracker.log_metric(name, value, step=step)` for every numeric signal captured in that record call.
2. Call `await tracker.log_figure(name, fig)` for every plotly figure the adapter generates during that record call (only if `plot_*` is invoked explicitly — `record_batch` itself MUST NOT emit figures, to keep the hot path cheap).
3. Emit at INFO: `ml_diagnose.emit` with `dl_run_id`, `dl_metric_count`, `dl_step` — once per `record_epoch` or equivalent epoch boundary; not per `record_batch` (too noisy).

### 4.3 Metric Name Contract

Metric names emitted by `DLDiagnostics` MUST follow this exact schema — downstream dashboards and alerting keys depend on stability:

| Capture source                                                      | Metric name (exact)                                                              | Step index source     |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------- |
| `record_batch(loss=...)`                                            | `loss`                                                                           | batch index (0-based) |
| `record_batch(lr=...)`                                              | `lr`                                                                             | batch index           |
| `record_batch` (per-param grad norm, via `track_gradients`)         | `grad_norm.{param_name}`                                                         | batch index           |
| `record_batch` (per-layer activation mean, via `track_activations`) | `activation_mean.{layer_name}`                                                   | batch index           |
| `record_batch` (per-layer activation std, via `track_activations`)  | `activation_std.{layer_name}`                                                    | batch index           |
| `record_batch` (dead-neuron ratio, via `track_dead_neurons`)        | `dead_neuron_ratio`                                                              | batch index           |
| `record_epoch(train_loss=...)`                                      | `train_loss`                                                                     | epoch index (0-based) |
| `record_epoch(val_loss=...)`                                        | `val_loss`                                                                       | epoch index           |
| `record_epoch(**extra)` with `extra={"accuracy": ...}`              | `val_accuracy` (prefixed `val_` by default)                                      | epoch index           |
| `diagnose_classifier(...)`                                          | `accuracy`, `f1_macro`, `precision_macro`, `recall_macro`, `roc_auc` (if binary) | run terminus (step=0) |
| `diagnose_regressor(...)`                                           | `mae`, `mse`, `rmse`, `r2`                                                       | run terminus (step=0) |
| `diagnose_clustering(...)`                                          | `silhouette_score`, `calinski_harabasz_score`, `davies_bouldin_score`            | run terminus (step=0) |

**Step indexing contract:**

- `record_batch` increments a monotonic batch counter starting at `0` on the first call of the session. Across epoch boundaries the counter does NOT reset — the tracker sees a monotonically-increasing `step` across the whole run.
- `record_epoch` uses a separate epoch counter starting at `0`.
- The two counters are orthogonal: `loss` uses batch index, `train_loss`/`val_loss` use epoch index. Downstream dashboards distinguish them by the tuple `(metric_name, step)` — the tracker does not need to know which counter was used.

**Name-sanitization:** Param names and layer names containing `.` are preserved verbatim (e.g. `grad_norm.encoder.layer.0.attention.self.query`). The tracker MUST accept `.`-separated dotted names; `ml-tracking.md §2.5` confirms this.

### 4.4 Figure Emission Contract

`log_figure(name, fig)` emission key schema:

| Producing method                | Figure name                         |
| ------------------------------- | ----------------------------------- |
| `plot_loss_curves()`            | `loss_curves`                       |
| `plot_gradient_flow()`          | `gradient_flow`                     |
| `plot_activation_stats()`       | `activation_stats`                  |
| `plot_dead_neurons()`           | `dead_neurons`                      |
| `plot_training_dashboard()`     | `training_dashboard`                |
| `plot_lr_vs_loss()`             | `lr_vs_loss`                        |
| `plot_weight_distributions()`   | `weight_distributions`              |
| `plot_gradient_norms()`         | `gradient_norms`                    |
| `diagnose_classifier` dashboard | `classifier_dashboard`              |
| `diagnose_regressor` dashboard  | `regressor_dashboard`               |
| `diagnose_clustering` dashboard | `clustering_dashboard`              |
| `grad_cam()`                    | `grad_cam.{layer_name}.{class_idx}` |

### 4.5 DDP / FSDP / DeepSpeed Rank-0-Only Emission (Decision 4)

**MUST**: Every `record_batch` / `record_epoch` / `record_step` / diagnosis call on `DLDiagnostics` (and `RLDiagnostics` per `ml-rl-core §8`) MUST emit to the tracker ONLY when `torch.distributed.get_rank() == 0` OR the distributed API is unavailable. Rank-0 is HARDCODED, NOT configurable via `DLDiagnostics(rank=...)` or any other kwarg. The `rank` kwarg in §5.1 auto-detects from `torch.distributed`; if the user passes it manually, the gate still applies — user-supplied `rank != 0` emits nothing.

```python
# DO — rank-0 gate inside every record_* method
def _is_rank_zero(rank_hint: Optional[int]) -> bool:
    if rank_hint is not None:
        return rank_hint == 0
    try:
        import torch.distributed as dist
        if dist.is_available() and dist.is_initialized():
            return dist.get_rank() == 0
    except (ImportError, RuntimeError):
        pass
    return True

class DLDiagnostics:
    def record_batch(self, **metrics):
        if not _is_rank_zero(self._rank):
            return  # silent no-op on non-rank-0 workers
        # ... tracker.log_metric(...) calls
```

**Why:** DDP spawns N processes; without the gate every batch metric is written N times. Rank-0-only is industry convention (W&B, MLflow). Decision 4 (approved 2026-04-21) locks this as a MUST clause — NOT an opt-in — because every prior "make it configurable" proposal ended in the N-duplicate failure mode. Cross-references: `ml-tracking §10.3`, `ml-autolog §3.3`, `ml-rl-core §8` (mirrored clause).

**Tier 2 test**: `tests/integration/test_diagnostics_ddp_rank0_only_emission.py` MUST mock `torch.distributed.get_rank()` to return 1, call `diag.record_batch(loss=0.5)`, assert NO row in `_kml_metric`. Rank-0 companion MUST assert emission. `rank=1` passed manually MUST produce the same no-op.

Origin: Decision 4 (approved 2026-04-21).

---

## 5. `DLDiagnostics` Public API (updated)

### 5.1 Construction

```python
DLDiagnostics(
    model: "torch.nn.Module",
    *,
    tracker: Optional[ExperimentRun] = None,   # NEW (v0.18.0) — see §4.1
    auto: bool = True,                          # NEW — auto-wire via contextvar when tracker=None
    dead_neuron_threshold: float = 0.5,
    window: int = 64,
    run_id: Optional[str] = None,
    log_every_n_steps: int = 50,                # NEW — flush to tracker every N record_batch calls
    rank: Optional[int] = None,                 # NEW — DDP rank; auto-detected via torch.distributed when None
    sensitive: bool = False,                    # NEW — redact layer/param names in emitted events per event-payload-classification.md
)
```

**Raises:**

- `TypeError` if `model` is not `nn.Module`.
- `ValueError` if `dead_neuron_threshold` ∉ (0, 1), `window < 1`, `run_id == ""`, or `log_every_n_steps < 1`.
- `ImportError` from `_require_torch()` if torch is absent.

### 5.2 Alternate Constructor: `from_training_result`

```python
@classmethod
def from_training_result(
    cls,
    result: TrainingResult,
    *,
    tracker: Optional[ExperimentRun] = None,
) -> "DLDiagnostics": ...
```

Re-hydrates a `DLDiagnostics` session from a completed `TrainingResult`. Used by `km.diagnose(TrainingResult, kind="dl")` post-training path. Does NOT install hooks (the training loop is finished); reads captured DataFrames from the TrainingResult's `diagnostic_snapshot` field when populated.

### 5.3 Lightning Callback

```python
def as_lightning_callback(self) -> "lightning.pytorch.Callback": ...
```

Returns a `lightning.Callback` instance wired to:

- `on_train_batch_end(trainer, pl_module, outputs, batch, batch_idx)` → `self.record_batch(loss=outputs["loss"].item(), lr=_resolve_lr(trainer))`
- `on_validation_epoch_end(trainer, pl_module)` → `self.record_epoch(val_loss=trainer.callback_metrics.get("val_loss"), **_extract_val_metrics(trainer))`
- `on_train_epoch_end(trainer, pl_module)` → flushes the epoch's batch aggregations to `tracker` even if `log_every_n_steps` hasn't fired.
- `on_fit_end(trainer, pl_module)` → calls `self.report()` and persists the dict via `tracker.log_params({"dl_diagnostic_summary": json.dumps(...)})`.

`_resolve_lr(trainer)` pulls from `trainer.optimizers[0].param_groups[0]["lr"]` (or the AcceleratorStrategy's equivalent); returns `None` if the optimizer is not yet constructed.

**Why a method, not a class:** Lightning callbacks are registered per-Trainer. Returning a fresh callback instance bound to `self` keeps the DLDiagnostics session the canonical reference; the callback is a thin adapter. Users who want manual control of `record_batch` can still call it directly without the callback.

**Engine-boundary auto-attach (cross-reference):** `ml-engines-v2-draft.md §3.2 MUST 5` mandates that `TrainingPipeline._train_lightning` auto-append `DLDiagnostics.as_lightning_callback()` to the `L.Trainer` callback list whenever `DLDiagnostics.is_available()` AND `kailash_ml.tracking.get_current_run()` returns a non-None `ExperimentRun`. The attachment is non-overridable; user-supplied callbacks compose with (not replace) the engine-appended diagnostics callback. A user-supplied duplicate `DLDiagnostics.as_lightning_callback()` is de-duplicated by `isinstance` — the engine-appended instance wins. This closes the Round-3 orphan where the callback existed but the engine never attached it.

### 5.4 Transformers Trainer Callback

```python
def as_transformers_callback(self) -> "transformers.TrainerCallback": ...
```

Returns a `transformers.TrainerCallback` wired to:

- `on_log(args, state, control, logs, **kwargs)` → if `"loss" in logs`: `self.record_batch(loss=logs["loss"], lr=logs.get("learning_rate"))`
- `on_evaluate(args, state, control, metrics, **kwargs)` → `self.record_epoch(val_loss=metrics.get("eval_loss"), **{k: v for k, v in metrics.items() if k.startswith("eval_") and isinstance(v, (int, float))})`
- `on_train_end(args, state, control, **kwargs)` → `self.report()` persisted same as Lightning.

Requires `transformers>=4.30`. Raises `ImportError("pip install kailash-ml[dl]")` when transformers is absent (transformers is pinned under the `[dl]` extra per `ml-engines.md §4.2`).

### 5.5 accelerate / DDP / FSDP / DeepSpeed Safety

kailash-ml MUST detect the active distribution launcher and strategy through a single dataclass that every adapter reads.

```python
@dataclass(frozen=True)
class DistributionEnv:
    is_distributed: bool
    world_size: int                       # 1 when not distributed
    rank: int                             # 0 when not distributed
    local_rank: int                       # 0 when not distributed
    launcher: Literal[
        "torchrun", "accelerate", "deepspeed", "lightning", "none"
    ]
    strategy: Literal[
        "ddp", "fsdp", "fsdp2", "zero1", "zero2", "zero3",
        "tp", "pp", "tp_pp", "none"
    ]
    # Parallelism axes — authoritative TP + PP + DP counts
    tp_size: int = 1
    pp_size: int = 1
    dp_size: int = 1
    zero_stage: int | None = None         # 1/2/3 for DeepSpeed ZeRO
    fa_version: int | None = None         # 2 or 3 if Flash-Attention detected

    @classmethod
    def detect(cls) -> "DistributionEnv":
        """Probe torch.distributed, accelerate.PartialState, and
        deepspeed.comm to determine launcher + strategy."""
        ...

    @property
    def is_main_process(self) -> bool:
        """True on rank 0 of every parallelism axis (both torch.distributed
        AND accelerate.PartialState().is_main_process when both active)."""
        ...
```

**Detection order**: `DistributionEnv.detect()` MUST check:

1. `accelerate.PartialState()` first — an Accelerate-launched single-GPU-per-machine run has `torch.distributed.is_initialized() == False` but `PartialState().num_processes > 1` still applies.
2. `torch.distributed.is_initialized()` — for torchrun, deepspeed-launched, lightning-ddp.
3. `hasattr(module, "ds_id")` — DeepSpeed-wrapped models expose `ds_id` on every module; triggers `launcher="deepspeed"` and `zero_stage` probe via `deepspeed.zero.config.ZeroStageEnum`.
4. `isinstance(module, FullyShardedDataParallel)` — FSDP wrapping; `strategy="fsdp"` or `"fsdp2"`.
5. Tensor-parallel probe — `hasattr(module, "tp_group")` / `accelerate`'s `Accelerator.tp_config` when it lands.

#### MUST 1. Hooks Install On Every Rank; Emission Is Rank-0-Gated

Gradient / activation hooks install on every rank (parameter tensors are per-rank; skipping non-zero misses per-device pathologies). `record_batch` / `record_epoch` emit to `tracker` ONLY on `env.is_main_process`. Other ranks accumulate in-memory DataFrames but do not log.

**Why:** Without rank gating, a 64-GPU run produces 64 duplicate `loss` metrics per step, corrupting every aggregation query. `env.is_main_process` handles both torch.distributed AND accelerate (single-GPU-per-machine multi-node) correctly.

#### MUST 2. FSDP Full-Weight Gradient Norm Uses The Authoritative All-Reduce

When `env.strategy in {"fsdp", "fsdp2"}`, kailash-ml MUST emit TWO metric families:

- `grad_norm.shard_local.{param_name}` — per-rank shard-local L2 norm (visible on every rank).
- `grad_norm.full_weight.{param_name}` — cross-shard reduction computed as `sqrt( all_reduce( shard_norm_squared, SUM ) )`, emitted on rank 0 only.

The full-weight formula `sqrt(Σ_r shard_norm_r²)` is identical to the FSDP optimizer's own internal computation (see PyTorch FSDP docs: `FullyShardedDataParallel.sharded_grad_norm()`). Sum-of-squares-of-shard-L2-norms (NOT sum-of-shard-L2-norms) is the ONLY correct formula because non-uniform layer sizes make `shard_weight[r]` unequal; a severity threshold `grad_explosion = grad_rms > 100` on shard-local norms produces false positives on the rank holding a large shard AND false negatives on the rank holding a tiny shard.

```python
# DO — correct full-weight reduction
per_rank_sq = (shard.grad.norm(2) ** 2)
full_weight_sq = torch.zeros_like(per_rank_sq)
torch.distributed.all_reduce(per_rank_sq, op=torch.distributed.ReduceOp.SUM, async_op=False)
full_weight_norm = per_rank_sq.sqrt().item()

# DO NOT — averaging shard L2 norms (wrong formula)
# mean_rank_norm = (shard.grad.norm(2)).mean()  # silent underestimate
```

**Why:** Severity thresholds must see the full weight's norm, not a shard's. The PyTorch FSDP docs are the blessed source for the formula.

#### MUST 3. DeepSpeed ZeRO-3 Parameter Extraction

Under ZeRO-3, `module.parameters() [ p.grad ]` enumeration OUTSIDE `deepspeed_engine.backward()` sees `None` for non-owned parameters because the partition is released after the reduce-scatter. kailash-ml MUST detect `hasattr(module, "ds_id")` and route gradient extraction through `deepspeed.utils.safe_get_local_fp32_param(param)` / `deepspeed.utils.safe_get_local_grad(param)`.

The forward/backward hooks MUST be installed inside the `deepspeed_engine.backward()` scope (Lightning's callback hooks `on_before_optimizer_step` fires at the correct timing). Installing hooks outside this scope on ZeRO-3 silently sees `None` gradients and emits `grad_norm.{param}=0.0` — a false-negative on grad explosion.

**ZeRO stage** is captured in `DeviceReport.zero_stage` (see `ml-backends.md`).

#### MUST 4. Accelerate Dispatch — Both Checks Required

Accelerate-launched runs MUST check BOTH `torch.distributed.get_rank() == 0` AND `accelerator.is_main_process` (from `accelerate.PartialState`) before emitting. An Accelerate run with `num_processes > 1` on a single GPU per machine has `torch.distributed.is_initialized() == False` on each process — the torch check alone falsely reports "not distributed" and emits N-way duplicates.

```python
# DO — both checks, DistributionEnv handles it
env = DistributionEnv.detect()
if env.is_main_process:
    tracker.log_metric(...)

# DO NOT — torch check only misses accelerate single-GPU-per-node
if torch.distributed.is_initialized() and torch.distributed.get_rank() == 0:
    tracker.log_metric(...)  # emits on every Accelerate process
```

#### MUST 5. Report Aggregation Reduces Severity-Relevant Aggregates

`self.report()` runs `torch.distributed.all_reduce(...)` on severity-relevant aggregates (mean grad_rms, max grad_rms, dead-neuron fraction) so every rank sees the same summary. If `torch.distributed` is unavailable, the reduce is a no-op.

#### MUST 6. Cross-Rank NaN/Inf Detection (RankSafetyCallback)

A `RankSafetyCallback` MUST broadcast a `uint8` NaN-flag via `all_reduce(op=SUM)` every `record_batch`. If ANY rank detected grad-NaN/Inf, rank-0 emits a WARN `ml_diagnose.cross_rank.grad_nonfinite` to the tracker — converting silent cross-rank divergence into a loud, queryable signal.

**Why:** Rank-0 emission gating hides real failures on other ranks. A NaN gradient on rank 3 that rank-0 never sees is a silent training corruption; the cross-rank reduce is `O(4 bytes * world_size)` per batch — negligible — and catches the pathology.

### 5.6 Mixed-Precision + autocast Integration

1. **Gradient capture** runs **before** `GradScaler.unscale_(optimizer)` when GradScaler is active. The hook signature receives the unscaled gradient directly (via `param.register_hook` on the leaf tensor), so grad-norm values are finite and meaningful regardless of the loss scale. Under AMP, the reported `grad_norm.full_weight` MUST be divided by the active `GradScaler._scale.item()` before comparison across steps — `DLDiagnostics` MUST record `grad_scaler_value` per batch so grad norm trajectories are comparable step-to-step.
2. **Activation capture** under `torch.autocast(dtype=torch.bfloat16)` captures tensors in their autocast dtype. `mean`/`std`/`min`/`max` are computed with `.float()` upcast to avoid bf16 overflow for layers with large activation magnitudes (e.g. LayerNorm output at the end of a transformer block).
3. **Non-finite guard** — `ml_diagnose.nonfinite_activation` WARN emission when the upcast mean/std is still non-finite (indicates a real fp16/bf16 overflow, not a precision artefact).

### 5.6.1 `torch.compile` + Hook Invalidation

DLDiagnostics forward/backward hooks attached BEFORE `torch.compile(model)` are silently dropped at graph-capture time. Adapters MUST detect `hasattr(model, "_orig_mod")` (PyTorch 2.x compile marker) and, when True, install hooks on `model._orig_mod` AFTER compile. A WARN MUST be emitted if hooks were installed pre-compile and the model is later observed to be compiled.

### 5.7 Checkpoint + Resume

```python
def checkpoint_state(self) -> dict[str, Any]:
    """Serializable state for checkpoint integration."""

@classmethod
def from_checkpoint(
    cls,
    model: "torch.nn.Module",
    state: dict[str, Any],
    *,
    tracker: Optional[ExperimentRun] = None,
) -> "DLDiagnostics":
    """Restore a session from previously-captured state."""
```

`checkpoint_state()` returns the session's running aggregates (batch counter, epoch counter, rolling grad-norm stats, dead-neuron running counts, the DataFrame bodies) AND a `last_seen_global_step: int` field. The dict is JSON-serialisable for the Kailash tracker's `_kml_checkpoint_diagnostics` table (a Kailash-internal invariant). Lightning's `Trainer.save_checkpoint()` continues to pickle — the JSON-safety claim is scoped to Kailash's own checkpoint table, NOT to Lightning's `CheckpointIO`. The dict rides along inside Lightning's checkpoint dict via the `CheckpointIO` hook registered by the Lightning callback.

`from_checkpoint()` restores a fresh session at the correct batch / epoch / counter state so a resumed training run produces a continuous metric stream into the tracker.

**Why state + classmethod, not pickle:** Pickling a `DLDiagnostics` session serialises the hook handles, the model reference, and torch state — incompatible with resume across different device topologies. JSON state + rebind-to-model classmethod is the Lightning-idiomatic contract.

### 5.7.1 Partial-Epoch Resume MUST NOT Double-Count

`DLDiagnostics` running-window aggregates (grad-rms rolling mean, dead-neuron running count) are batch-indexed. A resume at `last_seen_global_step=5432` MUST NOT re-emit batches 5400–5432 to the tracker.

**MUST 1 — Dedupe via composite PK.** The tracker's `_kml_metric` table has a composite primary key `(run_id, metric_key, step)` (see `ml-tracking.md` §6) — inserts at a duplicate step are rejected by the DB. `DLDiagnostics.from_checkpoint()` MUST set `self._global_step = state["last_seen_global_step"]` and the FIRST `record_batch` after resume MUST emit `step = last_seen_global_step + 1`.

**MUST 2 — Skip-to-step contract.** A resumed Lightning Trainer that replays the partial epoch MUST call `DLDiagnostics.skip_batch()` for each replayed batch `step <= last_seen_global_step` so running-window aggregates advance past them without emitting a tracker insert.

**MUST 3 — Tier 2 regression test.** `tests/integration/test_dl_diagnostics_partial_epoch_resume.py` MUST:

1. Train 2.5 epochs of a small net.
2. `Trainer.save_checkpoint()` mid-batch.
3. Crash; resume from the checkpoint.
4. Assert `SELECT COUNT(DISTINCT step) FROM _kml_metric WHERE run_id = ? == step_at_termination` (no duplicate inserts).

**Why:** Double-counted metrics poison every downstream visualisation (MLDashboard, W&B export). The composite-PK is the DB-level guard; `skip_batch` + `last_seen_global_step` is the application-level guard.

### 5.8 Module-Level Helpers (standalone)

```python
from kailash_ml.diagnostics import track_gradients, track_activations, track_dead_neurons

# Can be used without a DLDiagnostics session
handles = track_gradients(model, on_record=my_callback)
try:
    # ... training loop
finally:
    for h in handles:
        h.remove()
```

Each returns a list of `RemovableHandle` objects. `on_record=callable(name, grad_norm, batch_idx)` is invoked per batch per param. No tracker wiring, no Protocol conformance, no DataFrame accumulation — for users who want the hook machinery without the session overhead. The DLDiagnostics class uses these helpers internally (no code duplication).

**Why expose them:** Closes Newbie-UX finding that diagnostic machinery is trapped behind the DLDiagnostics session class. Users who want to attach grad tracking to an arbitrary `torch.nn.Module` without a session call the helpers directly — 1 line, no context manager.

---

## 6. Classical-ML Diagnosers

### 6.1 `diagnose_classifier`

```python
def diagnose_classifier(
    model: "sklearn.base.ClassifierMixin",
    X: "polars.DataFrame",
    y: "polars.Series",
    *,
    tracker: Optional[ExperimentRun] = None,
    show: bool = True,
    sensitive: bool = False,
) -> ClassifierReport
```

Runs `model.predict` / `model.predict_proba` on `(X, y)`, computes:

- Confusion matrix (as polars DataFrame, square-shaped, labels on rows & cols)
- Per-class precision, recall, F1
- ROC-AUC (binary) / macro-ROC-AUC (multiclass)
- Precision-Recall curve points
- Calibration curve (prob-bin mean predicted vs actual fraction)
- Class-imbalance ratio

Returns a frozen dataclass:

```python
@dataclass(frozen=True)
class ClassifierReport:
    run_id: str
    model_class: str
    confusion_matrix: Optional["polars.DataFrame"]   # K×K, or None for single-class split
    metrics: dict[str, float]           # accuracy, f1_macro, precision_macro, recall_macro, roc_auc (binary)
    per_class: "polars.DataFrame"        # class, precision, recall, f1, support
    roc_curve: Optional["polars.DataFrame"]   # binary only
    pr_curve: Optional["polars.DataFrame"]
    calibration_curve: "polars.DataFrame"        # reliability diagram (§13)
    brier_score: float | None                    # §13 — binary classification only
    class_balance: "polars.DataFrame"
    severity: dict[str, Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]]
    reason: str | None = None                    # populated when confusion_matrix=None

    def report(self) -> dict[str, Any]: ...   # Protocol conformance
    def plot_dashboard(self) -> "plotly.graph_objects.Figure": ...   # requires [dl] for plotly
```

Severity thresholds:

- `accuracy = CRITICAL` when accuracy < majority-class-proportion (worse than guessing majority).
- `class_balance = WARNING` when worst-class/best-class ratio < 0.1 (highly imbalanced).
- `calibration = WARNING` when mean calibration error > 0.15.

#### Single-Class Split Edge Case

When `y_true` contains only one unique label (possible under extreme imbalance or small test folds), `diagnose_classifier` MUST return a VALID `ClassifierReport` with:

- `confusion_matrix = None`
- `reason = "single_class_in_split"`
- `severity = {"confusion": "UNKNOWN", "class_balance": "CRITICAL", ...}`
- `metrics` populated with `accuracy` only (others set to `None`)
- `per_class` contains the one observed class

Non-single-class paths MUST always emit a K×K `confusion_matrix` where `K = | set(y_true) ∪ set(y_pred) |`; missing class rows/columns are filled with zero. `sklearn.metrics.confusion_matrix([1,1,1], [1,1,0])` returning `[[0,0],[1,2]]` is translated into `[[TN=0, FP=0], [FN=1, TP=2]]` over the union-of-labels index.

A regression test MUST exist at `tests/integration/test_diagnose_classifier_single_class.py` that feeds `y_true=[1,1,1,1]` and asserts `report.confusion_matrix is None and report.reason == "single_class_in_split"`.

### 6.2 `diagnose_regressor`

```python
def diagnose_regressor(
    model: "sklearn.base.RegressorMixin",
    X: "polars.DataFrame",
    y: "polars.Series",
    *,
    tracker: Optional[ExperimentRun] = None,
    show: bool = True,
    sensitive: bool = False,
) -> RegressorReport
```

Computes:

- MAE, MSE, RMSE, R², explained variance
- Residuals DataFrame (one row per sample: `y_true`, `y_pred`, `residual`, `abs_residual`, `studentized_residual`, `leverage`, `cooks_distance`)
- Q-Q plot points (theoretical vs empirical quantile pairs)
- Heteroscedasticity indicator — `heteroscedasticity_pvalue: float | None` from Breusch-Pagan (requires `[stats]` extra; `None` when statsmodels is absent)
- Top-N largest-residual rows (for error-inspection)
- Influential points surfaced via Cook's distance

```python
@dataclass(frozen=True)
class RegressorReport:
    run_id: str
    model_class: str
    metrics: dict[str, float]            # mae, mse, rmse, r2, explained_variance
    residuals: "polars.DataFrame"         # y_true, y_pred, residual, abs_residual, studentized_residual, leverage, cooks_distance
    qq_points: "polars.DataFrame"
    heteroscedasticity_pvalue: float | None   # Breusch-Pagan p-value, None if statsmodels absent
    cooks_distance: "polars.Series"
    leverage: "polars.Series"
    studentized_residuals: "polars.Series"
    top_errors: "polars.DataFrame"
    severity: dict[str, Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]]

    def report(self) -> dict[str, Any]: ...
```

Severity thresholds:

- `fit_quality = CRITICAL` when R² < -0.5 (substantially worse than predicting the mean — common causes include training-test distribution mismatch).
- `fit_quality = WARNING` when R² < 0 OR R² ∈ [0, 0.3]. The two-tier severity distinguishes "r² = -0.01 on a difficult problem" (close to baseline) from "r² = -5.0" (pathologically worse than mean).
- `heteroscedasticity = WARNING` when `heteroscedasticity_pvalue < 0.05`.
- `influential_points_detected = WARNING` when any `cooks_distance > 4/N` (classic threshold).

**Why Cook's distance + leverage + studentized residuals:** Residual plots alone cannot surface "one row is dominating the fit". A senior practitioner diagnoses influential-point-driven overfitting exclusively from these three per-sample statistics; omitting them forces the user to implement them externally — the #1 request from the round-2b audit.

### 6.3 `diagnose_clustering`

```python
def diagnose_clustering(
    model: "sklearn.base.ClusterMixin",
    X: "polars.DataFrame",
    *,
    tracker: Optional[ExperimentRun] = None,
    show: bool = True,
    sensitive: bool = False,
) -> ClusteringReport
```

Computes:

- Silhouette score (overall + per-sample distribution as polars DataFrame)
- Calinski-Harabasz score
- Davies-Bouldin score
- Cluster size distribution
- Inertia (for KMeans-compatible estimators)

Severity thresholds:

- `separation = CRITICAL` when silhouette < 0 (clusters overlap worse than random).
- `separation = WARNING` when silhouette < 0.25.

#### k ∈ {1, n-1, n} Edge Case

`sklearn.metrics.silhouette_score` raises `ValueError: Number of labels is 2 but should be between 2 and n-1` when k is out of range. `diagnose_clustering` MUST NOT silently fall back to `None` for these cases — instead route through a typed `InsufficientClustersError(k=k, n_samples=n, min_k=2, max_k=n-1)` whose message identifies the exact cause. The `silhouette` field of the returned `ClusteringReport` is `None` only for structural reasons (degenerate cluster count), never for numeric reasons.

### 6.4 Tracker Integration

All three diagnosers emit metrics and a single figure via `tracker.log_metric` / `tracker.log_figure` when `tracker is not None` (§4.2 / §4.3). The emission is a single batch at step `0` — classical ML is a one-shot diagnostic, not streaming.

### 6.5 Why Frozen Dataclasses

The dataclass form is friendlier than a context manager for a one-shot diagnosis: callers write `report = diagnose_classifier(model, X, y)` and can access `report.metrics["accuracy"]` directly without entering a `with` block. The `.report()` method is preserved for Protocol conformance (isinstance(report, Diagnostic) holds because `ClassifierReport` also has a `__enter__`/`__exit__` that are no-ops — frozen dataclasses are cheap to adapt).

---

## 7. Industry Parity Matrix

Columns: **Auto** = emitted without user code (engine layer wiring). **Primitive** = available as a one-liner the user invokes. **Deferred** = documented gap (track via deferred-item ticket).

| Capability                                | kailash-ml (v0.18.0 target)                 | TensorBoard | W&B                     | MLflow               | ClearML               |
| ----------------------------------------- | ------------------------------------------- | ----------- | ----------------------- | -------------------- | --------------------- |
| Auto-log loss per step                    | Auto (§5.3)                                 | Auto\*      | Auto                    | Auto                 | Auto                  |
| Auto-log learning rate                    | Auto (§5.3)                                 | Auto\*      | Auto                    | Auto                 | Auto                  |
| Gradient flow visualisation               | Auto (§4.3 grad_norm.\*)                    | Histogram   | Histogram               | Metrics              | Metrics               |
| Activation histograms                     | Primitive (stats only, no histogram tensor) | Histogram   | Histogram               | No                   | No                    |
| Dead-neuron tracking                      | Auto (§4.3 dead_neuron_ratio)               | No          | No                      | No                   | No                    |
| LR finder                                 | Primitive (§5 + `lr_range_test`)            | No          | No                      | No                   | No                    |
| Confusion matrix (classification)         | Primitive (`diagnose_classifier`)           | No          | Auto via sklearn plugin | Via `log_figure`     | Auto                  |
| Residual plot (regression)                | Primitive (`diagnose_regressor`)            | No          | Auto                    | No                   | Auto                  |
| Calibration curve                         | Primitive (`diagnose_classifier`)           | No          | No                      | No                   | No                    |
| DDP / FSDP rank-0-only emission           | Auto (§5.5)                                 | Manual      | Auto                    | Manual               | Auto                  |
| Mixed-precision safe captures             | Auto (§5.6)                                 | Manual      | Manual                  | Manual               | Manual                |
| Checkpoint/resume state                   | Auto (§5.7 via Lightning callback)          | No          | No                      | No                   | No                    |
| Lightning callback one-liner              | Yes (`as_lightning_callback`)               | No          | Yes (`WandbLogger`)     | Yes (`MLFlowLogger`) | Yes (`ClearMLLogger`) |
| transformers Trainer callback one-liner   | Yes (`as_transformers_callback`)            | No          | Yes                     | Yes                  | Yes                   |
| System metrics (CPU / GPU / mem) per step | Deferred (v0.19)                            | No          | Auto                    | No                   | Auto                  |
| Grad-CAM                                  | Primitive (`grad_cam()`)                    | No          | No                      | No                   | No                    |

`*` = TensorBoard auto-logs only when the user writes to a `SummaryWriter`; kailash-ml considers "auto" to mean "zero user code inside the training loop."

**Differentiators kailash-ml leads on:**

- Dead-neuron tracking as a first-class metric (no competitor ships this as a named metric).
- DDP/FSDP rank-0-only emission with FSDP shard awareness baked into the default path.
- Mixed-precision safe captures (grad captured pre-unscale, activations upcast to fp32 for stats).
- Protocol-based diagnostic interop (`kailash.diagnostics.protocols.Diagnostic`) enabling a single adapter to satisfy the contract and be consumed by the W&B bridge, TensorBoard bridge, and MLDashboard simultaneously.

**Deferred capabilities (explicit):**

- **DL-GAP-1** — Distributed training strategy passthrough in `TrainingPipeline._train_lightning` (covered by `ml-engines.md §3` revision, not here).
- **DL-GAP-2** — Per-step system metrics (GPU util, mem, power). Requires a separate thread polling `nvidia-ml-py`; target v0.19.0.
- **DL-GAP-3** — Activation histogram tensor logging (W&B-style `wandb.Histogram(grad)`). Emitting per-layer tensor data every step is ~10-100× more bytes than the scalar stats kailash-ml emits today; deferred pending a "tensor-payload" extension to the tracker spec.

---

## 8. Extras Gating

### 8.1 Base Install (`pip install kailash-ml`)

- `DLDiagnostics.__init__`, hook installation, `record_batch`, `record_epoch`, DataFrame accessors, `report()`, `grad_cam()`, `checkpoint_state` / `from_checkpoint`, module-level helpers, `as_lightning_callback` / `as_transformers_callback` return value (the callback class).
- `diagnose_classifier` / `diagnose_regressor` / `diagnose_clustering` — the dataclass, metrics, report.
- `km.diagnose` engine entry point.

### 8.2 `[dl]` Extra

- All `plot_*` methods (across DLDiagnostics, ClassifierReport, RegressorReport, ClusteringReport).
- `lr_range_test`'s `"figure"` return value.
- Lightning + transformers + accelerate — required for the `as_*_callback` methods to actually be invoked during training (callbacks are cheap to construct without Lightning; they only fail when `Trainer.fit()` runs).
- `RAGDiagnostics.plot_*` (see §12).

### 8.3 `[rag]` Extra

- `RAGDiagnostics.ragas_scores`, `RAGDiagnostics.trulens_scores` (see §12).

### 8.4 `[interpret]` Extra

- `ModelExplainer` (SHAP-based) — defined in `ml-engines.md §ModelExplainer`; this spec references it as the interpretability companion surface.

### 8.5 Loud Failure Contract

Every method that requires an extra routes through the `_require_<name>()` helper pattern. Every helper raises an `ImportError` whose message names the exact extra:

```python
def _require_plotly():
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        raise ImportError(
            "Plotting requires plotly. Install: pip install kailash-ml[dl]"
        ) from exc
    return go
```

Per `rules/zero-tolerance.md` Rule 2, a silently no-op `plot_*` method is a stub. The import-error pattern makes the extras contract a single grep-able site per extra.

---

## 9. Observability

Every method emits structured logs with the `dl_run_id` correlation field (or `classical_run_id` / `cluster_run_id` for the classical diagnosers). All structured-field kwargs carry an adapter-specific prefix to avoid `LogRecord` reserved-name collisions per `rules/observability.md` MUST Rule 9.

Event inventory (additions to v0.17.0):

| Event                                             | Level | When                                                                      |
| ------------------------------------------------- | ----- | ------------------------------------------------------------------------- |
| `ml_diagnose.dispatch`                            | INFO  | `km.diagnose` selected an adapter kind.                                   |
| `ml_diagnose.no_tracker`                          | INFO  | Adapter resolved no tracker (contextvar `None`, explicit `None`).         |
| `ml_diagnose.emit`                                | INFO  | `record_epoch` boundary flushed N metrics to tracker.                     |
| `dldiagnostics.callback.install`                  | INFO  | `as_lightning_callback` / `as_transformers_callback` returned a callback. |
| `dldiagnostics.ddp_rank`                          | INFO  | DDP rank detected; emission gated to rank 0.                              |
| `dldiagnostics.fsdp_shard_detected`               | INFO  | FSDP wrap detected; grad-norm values are shard-local.                     |
| `dldiagnostics.nonfinite_activation`              | WARN  | bf16/fp16 overflow in activation stats.                                   |
| `dldiagnostics.checkpoint.saved`                  | INFO  | Checkpoint state persisted.                                               |
| `dldiagnostics.checkpoint.restored`               | INFO  | Session restored via `from_checkpoint`.                                   |
| `classical_diagnose.classifier.severity_critical` | WARN  | Classifier accuracy worse than majority-class guess.                      |
| `classical_diagnose.regressor.severity_critical`  | WARN  | Regressor R² < 0.                                                         |
| `classical_diagnose.clustering.severity_critical` | WARN  | Silhouette < 0.                                                           |

No field name duplicates a `LogRecord` reserved attribute. `sensitive=True` redacts layer / param / feature names via the SHA-256 fingerprint pattern from `rules/event-payload-classification.md §2` (`sha256:<8-hex>`).

---

## 10. Security Threats

| Threat                                                             | Mitigation                                                                                                                                                                                            |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Layer / param names leaking proprietary architecture               | `sensitive=True` replaces layer / param names with `sha256:<8-hex>` fingerprints in all emitted metric names + log events.                                                                            |
| Unbounded metric emission on a long training run                   | `log_every_n_steps` (default 50) flushes batch-level metrics at a bounded cadence; DataFrames retain everything in memory but are bounded by `window` for hook-ring-buffers (gradients, activations). |
| Rank-0 metric duplication in DDP                                   | §5.5 gates emission to rank 0; all_reduce runs at `report()` time.                                                                                                                                    |
| bf16 / fp16 activation overflow corrupting stats                   | §5.6 upcast to fp32 for stats + WARN on non-finite upcast result.                                                                                                                                     |
| User-supplied `grad_cam` target_class out of bounds                | Validated against `model(input_tensor).shape[-1]`; `ValueError` names the valid range.                                                                                                                |
| Checkpoint state deserialization executing code                    | `checkpoint_state()` returns JSON-serialisable dict; `from_checkpoint` accepts only primitives + lists + dicts. No pickle.                                                                            |
| `ClassifierReport` / `RegressorReport` leaking PII in `top_errors` | `sensitive=True` replaces row IDs with fingerprints and drops raw feature values (keeps only predictions + residuals).                                                                                |

---

## 11. Test Contract

### 11.1 Tier 1 (Unit)

`packages/kailash-ml/tests/unit/test_dl_diagnostics_unit.py` (existing, extended):

- `__init__` validation (tracker `None` accepted, `log_every_n_steps < 1` rejected, `rank < 0` rejected).
- `from_training_result` re-hydrates correctly.
- Metric-name contract — each `record_batch` / `record_epoch` call emits metrics with the exact names from §4.3.
- Step indexing — batch counter monotonic across epochs; epoch counter orthogonal.
- Extras gating — every `plot_*` raises `ImportError` naming `[dl]` when plotly absent.
- Lightning-callback + transformers-callback return type + hook method presence (no Trainer instantiation).
- Rank-0-only emission simulated via monkey-patched `torch.distributed`.
- `checkpoint_state` / `from_checkpoint` round-trip.
- Each `plot_*` method in a delegating-pair sense (separate test per public primitive, per `rules/testing.md § Delegating Primitives Need Direct Coverage`).

`packages/kailash-ml/tests/unit/test_classical_diagnose_unit.py` (NEW):

- `diagnose_classifier` / `diagnose_regressor` / `diagnose_clustering` on sklearn fixtures.
- Severity thresholds (accuracy below majority-class, R² < 0, silhouette < 0).
- `tracker=None` passes through cleanly.
- `sensitive=True` redacts feature names in `top_errors`.

`packages/kailash-ml/tests/unit/test_km_diagnose_unit.py` (NEW):

- Dispatch table (§3.2) — every row exercised with a fixture subject.
- `TypeError` for unsupported subject type.
- `ValueError` for kind/model mismatch.
- No-tracker mode (contextvar unset AND explicit None) emits INFO once, no crash.

### 11.2 Tier 2 (Integration / Wiring)

`packages/kailash-ml/tests/integration/test_dl_diagnostics_wiring.py`:

- **Full Lightning callback path** — construct a real `L.LightningModule`, run `Trainer.fit()` with `callbacks=[diag.as_lightning_callback()]`, assert the SHARED tracker store (`ExperimentTracker` per `ml-tracking.md`) contains the expected metrics: `loss` at every batch step, `val_loss` at every epoch step, `grad_norm.{layer}.{param}` at every batch step. NOT the in-isolation fixture — the actual SQLite/PostgreSQL store the dashboard reads.
- `isinstance(diag, Diagnostic)` at runtime.
- Ambient-tracker auto-wiring — `async with km.track(): DLDiagnostics(model)` reads the contextvar and resolves the tracker without explicit kwarg.
- `km.diagnose(training_result)` engine entry point — dispatches to DLDiagnostics for a Lightning `TrainingResult`, emits to tracker, shows a figure.
- `km.diagnose(sklearn_model, data=(X, y))` — dispatches to `diagnose_classifier`, emits confusion-matrix + metrics.
- `run_id` propagates from `km.track` → `DLDiagnostics.run_id` → `tracker.log_metric(..., run_id=run.run_id)`.

`packages/kailash-ml/tests/integration/test_ddp_diagnostics_wiring.py` (NEW, `@pytest.mark.gpu`):

- 2-rank DDP run — assert metrics emitted once per step, not twice.
- FSDP wrap — assert `grad_norm.{param}` present with shard-local values.

### 11.3 Tier 3 (E2E) — Round-trip

`packages/kailash-ml/tests/e2e/test_dl_diagnostics_roundtrip.py`:

- Construct `km.track` + `DLDiagnostics` + Lightning `Trainer`.
- Train 2 epochs on a small fixture model.
- Open the dashboard (`MLDashboard`) against the SAME store.
- Fetch the run via the dashboard's REST endpoint.
- Assert the dashboard's metric panel reports the same `train_loss` / `val_loss` / `grad_norm.*` series.

This closes the cross-spec contract: `ml-diagnostics` emits; `ml-tracking` stores; `ml-dashboard` reads. The Tier 3 test is the only structural guarantee that the three specs compose.

---

## 11b. Cross-SDK Fingerprint Parity

Every adapter MUST emit a deterministic SHA-256 fingerprint over its `DiagnosticReport.to_dict()` that Rust (when a Rust sibling exists) and Python compute identically given identical observations. The canonical serialisation is pinned below; drifting from it silently breaks cross-SDK forensic correlation.

### Canonical serialisation rules

| Field type        | Python rule                                                                  | Rust rule                                        |
| ----------------- | ---------------------------------------------------------------------------- | ------------------------------------------------ |
| float / f32 / f64 | `f"{value:.17g}"` (IEEE 754 round-trippable shortest form)                   | `format!("{:.17e}", v)` normalised to same shape |
| int               | `str(value)` — no `_` separators, no leading zeros                           | `value.to_string()`                              |
| bool              | `"true"` / `"false"`                                                         | same                                             |
| None / null       | `"null"`                                                                     | same                                             |
| datetime          | `strftime("%Y-%m-%dT%H:%M:%S.%fZ")` (UTC, microseconds, trailing Z)          | chrono `%Y-%m-%dT%H:%M:%S%.6fZ`                  |
| enum              | String name of the enum variant, not its integer value                       | same                                             |
| numpy scalar      | Cast to native Python `int` / `float` first, then apply float/int rule above | n/a                                              |
| dict              | `sort_keys=True`                                                             | `BTreeMap` or sorted insertion order             |
| list              | preserve insertion order (observations are time-ordered)                     | same                                             |

```python
def fingerprint(report: DiagnosticReport) -> str:
    """SHA-256 over the canonical form. Deterministic across Python + Rust."""
    canonical = json.dumps(
        report.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_default,  # applies the float/datetime/enum rules
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

### MUST 1. Regression Test In Every Release

`tests/integration/test_diagnostic_fingerprint_cross_sdk_parity.py` MUST exist and run against a CSV of pinned `(report_json, expected_sha256)` pairs. The CSV is co-owned by Python + Rust tests; both SDKs import it and assert identical fingerprints. CI failure BLOCKS release.

### MUST 2. `src/kailash/diagnostics/protocols.py::fingerprint()` Is The Canonical Helper

Every adapter's `.report()` routes through the SAME fingerprint helper — per-adapter copies of the float-format / dict-sort logic are BLOCKED (drift risk).

**Why:** Cross-SDK fingerprint parity is claimed but un-verified without a regression. The canonical-form helper in `protocols.py` is the single enforcement point; the CSV regression test is the gate.

---

## 12. Fairness Diagnostics

Regulatory environments (EU AI Act, NIST AI RMF) require fairness measurement alongside accuracy. kailash-ml ships a `diagnose_fairness` primitive.

### 12.1 API

```python
def diagnose_fairness(
    model: "sklearn.base.BaseEstimator" | "lightning.LightningModule",
    X: "polars.DataFrame",
    y: "polars.Series",
    protected_attrs: list[str],        # column names in X that are sensitive attributes
    *,
    favorable_outcome: Any = 1,         # positive class for demographic-parity calc
    tracker: Optional[ExperimentRun] = None,
    sensitive: bool = False,
) -> FairnessReport: ...

@dataclass(frozen=True)
class FairnessReport:
    adapter: ClassVar[str] = "fairness"
    run_id: str | None
    protected_attrs: list[str]
    demographic_parity: dict[str, float]    # per-attr disparate impact ratio (min(P_group) / max(P_group))
    equalized_odds: dict[str, float]        # per-attr max |TPR_g - TPR_g'| across groups
    predictive_parity: dict[str, float]     # per-attr PPV equality
    group_metrics: "polars.DataFrame"       # group, n, positive_rate, tpr, fpr, ppv
    severity: dict[str, Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]]

    def report(self) -> dict[str, Any]: ...
```

### 12.2 MUST Rules

- **Disparate-impact threshold** — `demographic_parity < 0.8` (the "80% rule" from EEOC) emits `severity="CRITICAL"`.
- **Equalized-odds threshold** — `max|TPR_diff| > 0.1` emits `severity="WARNING"`.
- **Protected-attr redaction** — when `sensitive=True`, protected-attribute VALUES are replaced with `sha256:<8>` in emitted payloads; the attribute NAME is preserved (this is regulatory-required context, not PII).
- **Tracker integration** — emits `fairness.{attr}.demographic_parity`, `.equalized_odds`, `.predictive_parity` metrics.
- **Minimum group size** — groups with `n < 30` raise `InsufficientGroupSizeError` (sample too small for meaningful fairness claim).

---

## 13. Calibration Diagnostics

Calibration is a first-class classification primitive alongside accuracy/F1. `ClassifierReport.calibration_curve` (already defined in §6.1) is the reliability diagram — this section pins its construction and severity.

### 13.1 Contract

- `calibration_curve` is a polars DataFrame with columns `(bin_lower, bin_upper, predicted_mean, observed_mean, count)`.
- Binning strategy: 10 equal-frequency bins by default (configurable via `calibration_n_bins: int = 10`).
- `brier_score` MUST be populated for binary classification: `brier = mean((p_pred - y_true)^2)`.
- Expected Calibration Error (ECE): `ece = Σ_b (n_b/N) * |predicted_mean_b - observed_mean_b|`. Stored on `ClassifierReport.metrics["ece"]`.
- Severity: `calibration = WARNING` when `ece > 0.1`; `CRITICAL` when `ece > 0.2`.

### 13.2 Ensemble / MC-Dropout Calibration

When the model exposes an uncertainty hook (see §14), `calibration_curve` computes the reliability diagram using the ensemble / MC-dropout predictive MEAN, not a single stochastic forward pass. The `calibration` severity MUST be suppressed (`UNKNOWN`) when uncertainty hooks are unavailable and the predicted distribution is a single sample.

---

## 14. Uncertainty Quantification Hooks

### 14.1 API

```python
def diagnose_uncertainty(
    model,
    X: "polars.DataFrame",
    *,
    method: Literal["ensemble", "mc_dropout", "conformal"],
    n_samples: int = 30,                  # MC passes OR ensemble members
    alpha: float = 0.1,                   # conformal miscoverage target (90% PI)
    calibration_data: tuple[pl.DataFrame, pl.Series] | None = None,
    tracker: Optional[ExperimentRun] = None,
) -> UncertaintyReport: ...

@dataclass(frozen=True)
class UncertaintyReport:
    adapter: ClassVar[str] = "uncertainty"
    method: str
    predictive_mean: "polars.Series"
    predictive_std: "polars.Series"
    coverage: float | None               # conformal only
    interval_width_mean: float | None    # conformal only
    severity: dict[str, Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]]
```

### 14.2 Methods

- **ensemble** — `model` is expected to be a `kailash_ml.ensemble.BaseEnsemble`. Predictive std is inter-member disagreement.
- **mc_dropout** — requires `torch.nn.Module` with at least one `Dropout` layer; `model.train()` (NOT `.eval()`) for the forward passes. Predictive std is across N MC passes.
- **conformal** — split-conformal: calibration set produces non-conformity scores; `alpha=0.1` → 90% prediction-interval. `coverage` MUST be empirically validated against a held-out set.

### 14.3 MUST Rules

- `mc_dropout` on a model with no Dropout layers raises `UncertaintyUnavailableError("model has no Dropout layers — use ensemble or conformal")`.
- `conformal` without `calibration_data` raises `ValueError("conformal method requires calibration_data=(X_cal, y_cal)")`.
- Tracker integration — emits `uncertainty.predictive_std.mean`, `uncertainty.coverage` (conformal) per run.

---

## 15. `RAGDiagnostics` (unchanged from v0.17.0)

`RAGDiagnostics` retains the v0.17.0 contract verbatim — construction, `evaluate()`, `compare_retrievers()`, IR metrics, faithfulness, leaderboard, ragas / trulens extras — with one addition: the tracker-wiring contract of §4 applies to `RAGDiagnostics.evaluate()` as it does to `DLDiagnostics.record_batch()`. When `tracker is not None`:

- `evaluate(...)` emits `rag.recall_at_k`, `rag.precision_at_k`, `rag.ndcg_at_k`, `rag.faithfulness`, `rag.context_utilisation` as metrics at step = evaluation-batch-index.
- `compare_retrievers(...)` emits one metric per retriever per metric: `rag.retriever.{retriever_name}.mrr` etc.
- `plot_rag_dashboard()` emits the `rag_dashboard` figure via `log_figure`.

Full body preserved from v0.17.0 spec §§11.1–11.14.

---

## 16. Cross-SDK Alignment

- **Python surface**: `kailash_ml.diagnostics` lands all adapters in kailash-ml 1.0.0.
- **Rust surface**: Per v0.17.0 — no planned kailash-rs equivalent for torch-bound diagnostics (`DLDiagnostics` depends on PyTorch forward/backward hooks). Cross-SDK agreement is at the Protocol level (`kailash.diagnostics.protocols.Diagnostic` + `schemas/trace-event.v1.json`).
- **Other Python adapters** — AlignmentDiagnostics (kailash-align), LLMDiagnostics / AgentDiagnostics (kailash-kaizen), InterpretabilityDiagnostics (kailash-kaizen), and RLDiagnostics (kailash-ml, see `ml-rl.md`) all follow the same tracker-wiring contract from §4.

---

## 17. Related Specs

- `src/kailash/diagnostics/protocols.py` — `Diagnostic` / `TraceEvent` / `JudgeCallable` Protocol definitions consumed here.
- `specs/ml-engines.md` (v2 draft at `workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md`) — `MLEngine`, `Trainable`, Lightning spine.
- `specs/ml-backends.md` (draft) — `detect_backend()` + `BackendInfo`.
- `specs/ml-tracking.md` (v2 draft) — canonical `ExperimentRun.log_metric` + `log_figure` contract consumed in §4.
- `specs/ml-dashboard.md` (draft in same cycle) — downstream consumer of emitted metrics + figures.
- `specs/ml-rl.md` (draft) — `RLDiagnostics` cross-reference at §3.2.
- `specs/ml-autolog.md` (draft) — `km.autolog()` contextvar-based auto-instrumentation.
- `specs/alignment-diagnostics.md` — `AlignmentDiagnostics` sibling.
- `specs/kaizen-observability.md` — `AgentDiagnostics` sibling.
- `specs/kaizen-interpretability.md` — `InterpretabilityDiagnostics` sibling.
- `specs/kaizen-judges.md` — `JudgeCallable` Protocol + `LLMDiagnostics` companion.

---

## 18. Attribution

The original `DLDiagnostics` implementation was contributed from MLFP `shared/mlfp05/diagnostics.py` (Apache-2.0). `RAGDiagnostics` was contributed from MLFP `shared/mlfp06/diagnostics/retrieval.py` (Apache-2.0). The v2 (0.18.0) revisions — tracker wiring, Lightning + transformers callbacks, DDP/FSDP safety, checkpoint-resume, classical diagnosers, `km.diagnose` — are Kailash-native per Round-2 Phase-A authoring, 2026-04-21.

Attribution is carried in each source file's copyright header, each module docstring, and the root `NOTICE` file.

---

## 19. Change Log

| Version | Date       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.16.0  | 2026-04-20 | `DLDiagnostics` initial port from MLFP.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 0.17.0  | 2026-04-20 | `RAGDiagnostics` ported; `[rag]` extra introduced.                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| 0.18.0  | 2026-04-21 | **v2 — tracker wiring contract (§4), `km.diagnose` engine entry (§3), Lightning + transformers callbacks (§5.3 / §5.4), DDP/FSDP safety (§5.5), mixed-precision (§5.6), checkpoint/resume (§5.7), module-level helpers (§5.8), classical diagnosers (§6), industry parity matrix (§7), Tier 2 wiring + Tier 3 round-trip tests (§11).** Closes Round-1 DL-1, DL-2, DL-7, DL-8, DL-9, DL-10, DL-11, DL-12 + Newbie-UX F-DIAGNOSTICS-NO-DASHBOARD-SINK / F-DL-NO-AUTO-WIRE / F-DIAGNOSE-NO-TOPLEVEL + Industry #3 / #5 / #17. |
