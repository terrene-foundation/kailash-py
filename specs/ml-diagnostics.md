# Kailash ML Diagnostics — Training-Loop Diagnostics Adapters

Version: 0.16.0
Package: `kailash-ml`
Parent domain: ML Lifecycle (`ml-engines.md` covers training; `ml-tracking.md` covers run history; `ml-backends.md` covers device resolution). This spec covers the polars-native, Protocol-backed diagnostic adapters that instrument training loops.
Scope authority: `kailash_ml.diagnostics.DLDiagnostics` and its module-level helpers; the conformance contract against `kailash.diagnostics.protocols.Diagnostic`; the extras-gating contract for plotting surfaces.

Status: LIVE — landed in kailash-ml 0.16.0 (2026-04-20). PR#1 of 7 for the MLFP diagnostics donation plan tracked in kailash-py issue #567. See `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md` for the full 7-PR sequence.

Origin: Originally contributed from MLFP module `mlfp05/diagnostics.py` (Apache-2.0). Re-authored for the Kailash ecosystem with medical metaphors stripped, plotly moved to the `[dl]` extra, and device resolution routed through the `kailash_ml._device` single-point resolver.

---

## 1. Scope

### 1.1 In Scope

This spec is authoritative for:

- **`DLDiagnostics` adapter** — context-manager session that installs forward/backward hooks on a user-supplied `torch.nn.Module` and records per-batch/per-epoch training signals.
- **Diagnostic Protocol conformance** — `kailash_ml.diagnostics.DLDiagnostics` MUST satisfy the `@runtime_checkable` Protocol at `kailash.diagnostics.protocols.Diagnostic` (`run_id` + `__enter__` + `__exit__` + `report()`).
- **Polars-native DataFrame accessors** — `gradients_df`, `activations_df`, `dead_neurons_df`, `batches_df`, `epochs_df` all return `polars.DataFrame` with stable column schemas.
- **Plotly extras-gating** — `plot_*()` methods + the interactive training dashboard require `pip install kailash-ml[dl]`. `report()` and DataFrame accessors work on the base install.
- **LR range test** — `DLDiagnostics.lr_range_test` static method (Leslie Smith sweep + fastai-style EMA smoothing + safe_lr recommendation).
- **Grad-CAM** — `DLDiagnostics.grad_cam` heatmap for classifier prediction attribution.
- **Module-level helpers** — `run_diagnostic_checkpoint`, `diagnose_classifier`, `diagnose_regressor` (one-shot read-only diagnostic passes on trained models).
- **Cross-SDK contract** — how the Python `DLDiagnostics` correlates with the cross-SDK `kailash.diagnostics.protocols` surface.

### 1.2 Out of Scope

- **The Diagnostic Protocol itself** — defined in `src/kailash/diagnostics/protocols.py` and is cross-SDK canonical. This spec references it as a dependency but does not define it.
- **Other Diagnostic adapters** — `RAGDiagnostics` (PR#2), `AlignmentDiagnostics` (PR#3), `InterpretabilityDiagnostics` (PR#4), `LLMDiagnostics` (PR#5), `AgentDiagnostics` (PR#6), and `GovernanceEngine` extensions (PR#7) each land in their own package with their own spec. See `SYNTHESIS-proposal.md` for the per-package binding.
- **Training itself** — `ml-engines.md` owns the `MLEngine`, `Trainable` protocol, and Lightning spine. `DLDiagnostics` is a read-only instrument that observes a training loop written elsewhere.
- **Drift detection** — `DriftMonitor` in `ml-engines.md §InferenceServer` owns PSI/KS on production data. `DLDiagnostics` observes training-time pathologies (vanishing gradients, dead neurons, overfitting), not post-deployment drift.
- **Experiment run records** — `ml-tracking.md` owns `ExperimentTracker.log_metric` / `log_artifact`. `DLDiagnostics.report()` returns a dict the caller MAY serialise into an ExperimentTracker run, but this spec does not define that integration.

---

## 2. Protocol Conformance Contract

### 2.1 Diagnostic Protocol Shape

The `Diagnostic` Protocol lives in `src/kailash/diagnostics/protocols.py`:

```python
@runtime_checkable
class Diagnostic(Protocol):
    run_id: str
    def __enter__(self) -> "Diagnostic": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]: ...
    def report(self) -> dict[str, Any]: ...
```

### 2.2 MUST Conformance Contract

Every adapter in `kailash_ml.diagnostics` MUST:

1. Expose `run_id: str` as a public instance attribute populated in `__init__`. Defaulted to `uuid.uuid4().hex` when the caller omits it; honored verbatim when the caller supplies a non-empty string.
2. `__enter__` returns `self` (not a subclass of `contextlib.ExitStack`, not a wrapper).
3. `__exit__` returns `Optional[bool]` — never raises from `__exit__`; always runs `detach()` to remove hook handles.
4. `report() -> dict[str, Any]` is callable at any time (including on an empty session with no `track_*()` calls) and never raises.
5. `isinstance(obj, Diagnostic)` returns `True` at runtime — the Protocol is `@runtime_checkable` and Tier 2 wiring tests MUST assert this (see `tests/integration/test_dl_diagnostics_wiring.py::test_dl_diagnostics_satisfies_diagnostic_protocol`).

**Why:** Downstream consumers use `isinstance(obj, Diagnostic)` for type-safe Protocol dispatch (e.g., a generic `record_diagnostic(d: Diagnostic)` sink in a telemetry pipeline). If conformance breaks, every downstream consumer silently skips the adapter.

### 2.3 `report()` Return Shape

`DLDiagnostics.report()` returns a dict with this exact structure:

```python
{
    "run_id": str,                     # echoes self.run_id
    "batches": int,                    # count of record_batch() calls
    "epochs": int,                     # count of record_epoch() calls
    "gradient_flow": {"severity": Severity, "message": str},
    "dead_neurons": {"severity": Severity, "message": str},
    "loss_trend": {"severity": Severity, "message": str},
}
```

Where `Severity = Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]`.

`UNKNOWN` severity MUST be returned when the relevant `track_*()` has not been called (no gradient hooks → gradient_flow is UNKNOWN; no activation hooks → dead_neurons is UNKNOWN). A caller iterating over findings for alerting logic MAY treat UNKNOWN as "not enough data" rather than as a failure signal.

---

## 3. `DLDiagnostics` Public API

### 3.1 Construction

```python
from kailash_ml.diagnostics import DLDiagnostics

DLDiagnostics(
    model: torch.nn.Module,
    *,
    dead_neuron_threshold: float = 0.5,   # (0, 1) exclusive
    window: int = 64,                      # >= 1
    run_id: Optional[str] = None,          # UUID4 hex if omitted
)
```

**Raises:**

- `TypeError` if `model` is not an `nn.Module`.
- `ValueError` if `dead_neuron_threshold` is outside `(0, 1)`, `window < 1`, or `run_id == ""`.
- `ImportError` from the lazy `_require_torch()` helper if torch is genuinely absent (should not happen; torch is a base dep as of 0.13.0 per `ml-engines.md §3 MUST 2`).

**Device resolution** routes through `kailash_ml._device.detect_backend()` — the canonical single-point backend resolver per `ml-backends.md §2`. A partially-broken probe falls back to CPU rather than crashing session construction.

### 3.2 Hook Registration Methods

All three return `self` for chaining and are idempotent (calling twice installs hooks once). All three log at INFO with `dl_hooks_registered` count and `dl_run_id` correlation.

| Method                 | Hooks installed on                                                                                                                                                          | Records per batch                                                                                                  |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `track_gradients()`    | Every trainable parameter tensor (via `param.register_hook`).                                                                                                               | `grad_norm` (L2), `grad_rms` (scale-invariant), `update_ratio` (`‖∇W‖ / ‖W‖`).                                     |
| `track_activations()`  | `nn.Linear`, `nn.Conv{1,2,3}d`, `nn.ReLU` / `LeakyReLU` / `GELU` / `ELU` / `SiLU` / `Tanh` / `Sigmoid`, `nn.BatchNorm{1,2}d`, `nn.LayerNorm` (via `register_forward_hook`). | `act_kind` (`relu`/`tanh`/`sigmoid`/`other`), `mean`, `std`, `min`, `max`, `dead_fraction`, `inactivity_fraction`. |
| `track_dead_neurons()` | ReLU-family modules (`nn.ReLU` / `LeakyReLU` / `GELU` / `ELU` / `SiLU`).                                                                                                    | Per-channel firing counts (memory-bounded via `window`).                                                           |

### 3.3 Recording Methods

```python
diag.record_batch(*, loss: float, lr: Optional[float] = None) -> None
diag.record_epoch(*, val_loss: Optional[float] = None,
                  train_loss: Optional[float] = None,
                  **extra: float) -> None
```

`record_epoch(train_loss=None)` auto-computes the per-epoch mean of the current epoch's batches. `**extra` metrics are coerced to float and persisted in `epochs_df()`.

Non-finite losses (`NaN`, `±inf`) are recorded (preserved in the DataFrame) AND logged at WARN with the batch index so post-mortem analysis can locate the divergence.

### 3.4 DataFrame Accessors (polars-native)

All return `polars.DataFrame` with stable column schemas (documented inline). Empty-state DataFrames have the correct schema with zero rows — safe to pass to downstream consumers that branch on `df.height`.

| Method              | Columns (ordered)                                                                 |
| ------------------- | --------------------------------------------------------------------------------- |
| `gradients_df()`    | `batch, layer, grad_norm, grad_rms, update_ratio` (all floats except batch/layer) |
| `activations_df()`  | `batch, layer, act_kind, mean, std, min, max, dead_fraction, inactivity_fraction` |
| `dead_neurons_df()` | `layer, n_neurons, n_dead, dead_fraction`                                         |
| `batches_df()`      | `batch, epoch, loss, lr`                                                          |
| `epochs_df()`       | `epoch, train_loss, val_loss, ...` (any extras passed to `record_epoch`)          |

### 3.5 `report()` — Diagnostic Protocol Contract

See §2.3 above. Severity thresholds:

- **`gradient_flow = CRITICAL`** — vanishing (`min grad_rms < 1e-5` OR `min update_ratio < 1e-4`) or exploding (`max grad_rms > 1e-2` OR `max update_ratio > 0.1`).
- **`gradient_flow = WARNING`** — RMS spread across layers > 1e3 (deep layers learning unevenly).
- **`dead_neurons = WARNING`** — worst-layer `mean_inactive > dead_neuron_threshold` (default 0.5).
- **`loss_trend = WARNING`** — overfitting (val loss rising while train falls, detected by `_detect_overfit_epoch`) OR underfitting (train slope > -1e-4 with ≥5 epochs).

Every finding carries an actionable `message` with the diagnosed layer name (when applicable) and a suggested fix.

### 3.6 Plotting Methods (require `kailash-ml[dl]`)

All return `plotly.graph_objects.Figure`. On a base install without the `[dl]` extra, each method raises `ImportError` naming `pip install kailash-ml[dl]`.

| Method                        | Purpose                                                                             |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| `plot_loss_curves()`          | Train (per batch + per epoch mean) vs val with overfitting-epoch vline callout.     |
| `plot_gradient_flow()`        | Per-layer gradient L2 norm over time (log y-axis, one trace per parameter).         |
| `plot_activation_stats()`     | Per-layer activation mean over time with std as hover-customdata.                   |
| `plot_dead_neurons()`         | Bar chart of dead-neuron fraction per ReLU-family layer with alert threshold hline. |
| `plot_training_dashboard()`   | 2×2 subplot grid: loss, gradient flow, activation mean, learning rate.              |
| `plot_lr_vs_loss()`           | LR vs loss (useful after `lr_range_test`).                                          |
| `plot_weight_distributions()` | Weight-value histogram per parameter tensor.                                        |
| `plot_gradient_norms()`       | Bar chart of mean gradient norm per layer across the run.                           |

### 3.7 `grad_cam(input_tensor, target_class, layer_name)`

Classification-only. Computes a Grad-CAM heatmap attributing `target_class` to the spatial activations of `layer_name`. Preserves the model's train/eval state across the call. Raises:

- `ValueError` if `layer_name` is not found in `model.named_modules()` (error message lists first 10 available names).
- `ValueError` if `model(input_tensor)` returns non-2D logits (Grad-CAM requires classifier-shape output).
- `RuntimeError` if the forward hook never fires (the target layer is unreachable from the forward path).

### 3.8 `lr_range_test(model, dataloader, *, loss_fn, ...)` (static method)

Leslie Smith LR range test. MUST parameters:

- `loss_fn` is REQUIRED — no silent default. Pass `nn.CrossEntropyLoss()` for classification or `nn.MSELoss()` for regression.
- `steps >= 2`.
- `0 < lr_min < lr_max`.

Model weights are saved via `state_dict` deepcopy before the sweep and restored in the `finally` block, so calling the test does NOT corrupt the model.

Returns a dict with:

```python
{
    "safe_lr": float,         # RECOMMENDED — pass to your optimizer
    "min_loss_lr": float,     # steepest descent (edge of instability)
    "divergence_lr": float,   # first LR where smoothed loss > 4× min
    "suggested_lr": float,    # backwards-compat alias of safe_lr
    "lrs": list[float],
    "losses": list[float],
    "losses_smooth": list[float],  # EMA β=0.98 + bias correction
    "figure": plotly.graph_objects.Figure,  # requires [dl]
}
```

Divergence detection: the loop early-exits when `cur_loss > 10 * running_min` (O(1) running min, not O(n)) — a single bad batch late in the sweep cannot poison the result.

### 3.9 Module-Level Helpers

```python
run_diagnostic_checkpoint(model, dataloader, loss_fn, *,
    title="Model", n_batches=8,
    train_losses=None, val_losses=None,
    show=True, batch_adapter=None) -> (DLDiagnostics, dict)

diagnose_classifier(model, dataloader, *,  # built-in F.cross_entropy
    title="Classifier", n_batches=8,
    train_losses=None, val_losses=None,
    show=True, forward_returns_tuple=False) -> (DLDiagnostics, dict)

diagnose_regressor(model, dataloader, *,   # built-in F.mse_loss
    title="Regressor", n_batches=8,
    train_losses=None, val_losses=None,
    show=True, forward_returns_tuple=False) -> (DLDiagnostics, dict)
```

Attach every instrument, run `n_batches` read-only forward-backward passes (no `optimizer.step()`), replay any pre-captured epoch history, and return the session + findings. `show=True` calls `fig.show()` on the training dashboard when plotly is available; silently skips (logs INFO) when plotly is absent.

---

## 4. Extras Gating

### 4.1 What Works on the Base Install

`pip install kailash-ml` gives the caller:

- `DLDiagnostics.__init__` and all hook registration methods.
- `record_batch` / `record_epoch`.
- All `*_df()` DataFrame accessors.
- `report()` — the canonical Diagnostic contract.
- `grad_cam()` — pure torch + numpy, no plotly needed.

### 4.2 What Requires `kailash-ml[dl]`

- All `plot_*()` methods.
- `plot_training_dashboard()` interactive 2×2 dashboard.
- `lr_range_test()`'s `"figure"` return value (the method itself runs without plotly; only the figure construction requires it).

The contract is enforced via a single helper:

```python
def _require_plotly() -> Any:
    try:
        import plotly.graph_objects as go
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install the deep-learning extras: "
            "pip install kailash-ml[dl]"
        ) from exc
    return go
```

Every `plot_*` method routes through this helper on its first line so a missing-extra failure is a single grep and a single fix site.

### 4.3 Why `[dl]` Instead of a New `[plot]` Extra

The SYNTHESIS proposal (§ "Plotly blast radius") originally considered a dedicated `[plot]` extra. Decision: plotly lives under `[dl]` because every realistic DL user already needs torch / lightning (the rest of `[dl]`) and will install the same extra. A separate `[plot]` would add an install step with no practical benefit and force `pip install kailash-ml[dl,plot]` on every user.

**Note — plotly currently lives in base too.** `packages/kailash-ml/pyproject.toml` has `plotly>=5.18` as a base dep because other engines (`ModelVisualizer`, `DataExplorer`) use it. The `[dl]` pin is redundant today but makes this module's extras contract survive if plotly is ever demoted from base.

---

## 5. Observability

Every `DLDiagnostics` method emits structured logs with the `dl_run_id` correlation field. Structured-field kwargs carry a `dl_` prefix to avoid `LogRecord` reserved-name collisions per `rules/observability.md` MUST Rule 9.

| Event                                       | Level | When                                                            |
| ------------------------------------------- | ----- | --------------------------------------------------------------- |
| `dldiagnostics.init`                        | INFO  | Session constructor completes.                                  |
| `dldiagnostics.track_gradients`             | INFO  | Gradient hooks registered.                                      |
| `dldiagnostics.track_activations`           | INFO  | Activation hooks registered.                                    |
| `dldiagnostics.track_dead_neurons`          | INFO  | Dead-neuron hooks registered.                                   |
| `dldiagnostics.record_batch.nonfinite_loss` | WARN  | NaN/Inf loss recorded.                                          |
| `dldiagnostics.report`                      | INFO  | `report()` completes, summary of severities.                    |
| `dldiagnostics.grad_hook.error`             | WARN  | Gradient hook raised (defensive, rare).                         |
| `dldiagnostics.act_hook.nonfinite`          | WARN  | Activation mean/std non-finite (BF16/FP16 overflow).            |
| `dldiagnostics.lr_range_test.diverged`      | INFO  | LR sweep early-exited on divergence.                            |
| `dldiagnostics.lr_range_test.ok`            | INFO  | LR sweep completed with safe_lr / min_loss_lr.                  |
| `dldiagnostics.checkpoint.batch_skipped`    | WARN  | `run_diagnostic_checkpoint` skipped a batch on user-loop error. |
| `dldiagnostics.checkpoint.plotly_missing`   | INFO  | Checkpoint dashboard skipped because `[dl]` extra is absent.    |

No field name in any log site duplicates a `LogRecord` reserved attribute (`module`, `args`, `msg`, `pathname`, `filename`, `name`, `levelname`, `levelno`, `lineno`, `funcName`, `created`, `msecs`, `relativeCreated`, `thread`, `threadName`, `processName`, `process`).

---

## 6. Test Contract

### 6.1 Tier 1 (Unit)

`packages/kailash-ml/tests/unit/test_dl_diagnostics_unit.py` covers:

- `__init__` validation (non-module type, threshold out-of-range, window floor, empty `run_id`).
- `run_id` auto-generation uniqueness.
- `run_id` kwarg honored verbatim.
- `plot_*()` raises `ImportError` naming `[dl]` when plotly is absent (simulated via monkeypatch).
- Empty-state `report()` + DataFrame accessors.
- `lr_range_test` input validation (missing loss_fn, steps < 2, inverted LR range).

### 6.2 Tier 2 (Integration) — Required per orphan-detection

`packages/kailash-ml/tests/integration/test_dl_diagnostics_wiring.py`:

- Imports through the `kailash_ml.diagnostics` facade, NOT the concrete module path (per `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md` Rule 2).
- `isinstance(diag, Diagnostic)` holds at runtime (Protocol conformance).
- Real 3-batch training step records gradient + activation + loss data.
- `run_id` propagates from constructor → `report()['run_id']`.
- Empty session `report()` returns `UNKNOWN` for every finding without raising.

---

## 7. Attribution

The original MLFP implementation (`shared/mlfp05/diagnostics.py`, 1,679 LOC) was contributed under Apache 2.0. The Kailash port:

- Strips medical metaphors from every user-visible surface (docstrings, method names, plot titles, log events).
- Re-authors docstrings around ML-domain terms (`loss curve`, `gradient flow`, `activation statistics`, `dead neurons`) rather than clinical metaphors.
- Replaces the `shared.kailash_helpers.get_device()` import with `kailash_ml._device.detect_backend()` so diagnostic sessions see the same backend the rest of the package uses.
- Adds `run_id` to the public API for Diagnostic Protocol conformance.
- Lazy-imports plotly so the base install does not require 50 MB of plotting dependencies for `report()` and DataFrame accessors.

Attribution is carried in each file's copyright header + module docstring + this spec. The root `NOTICE` file is updated in the Session-1 blocker B4 (see `SYNTHESIS-proposal.md` § Pre-implementation blockers).

---

## 8. Cross-SDK Alignment

- **Python surface**: `kailash_ml.diagnostics.DLDiagnostics` — lands in kailash-ml 0.16.0.
- **Rust surface**: No planned kailash-rs equivalent. DL diagnostics depend on PyTorch's forward/backward hook API, which has no stable Rust binding. The cross-SDK agreement is at the Protocol level (`kailash.diagnostics.protocols.Diagnostic` + `schemas/trace-event.v1.json`), not at this concrete adapter.
- **Other Python adapters** (future PRs #2–#7) each ship their own spec in `specs/` and register in `specs/_index.md`.

---

## 9. Related Specs

- `src/kailash/diagnostics/protocols.py` — the `Diagnostic` / `TraceEvent` / `JudgeCallable` Protocol definitions consumed here.
- `specs/ml-engines.md` — `MLEngine`, `Trainable`, Lightning spine; training itself.
- `specs/ml-backends.md` — `detect_backend()` + `BackendInfo` used for device resolution in `DLDiagnostics`.
- `specs/ml-tracking.md` — `ExperimentTracker` + `ModelRegistry` (downstream consumer of `report()` output).
- `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md` — approved 7-PR architecture (Option E).

---

## 10. Change Log

| Version | Date       | Change                                                                                                    |
| ------- | ---------- | --------------------------------------------------------------------------------------------------------- |
| 0.16.0  | 2026-04-20 | Spec authored alongside the `DLDiagnostics` port from MLFP. First Diagnostic adapter lands in kailash-ml. |
