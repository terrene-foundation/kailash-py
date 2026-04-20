# Kailash ML Diagnostics — Training-Loop + Evaluation Diagnostics Adapters

Version: 0.17.0
Package: `kailash-ml`
Parent domain: ML Lifecycle (`ml-engines.md` covers training; `ml-tracking.md` covers run history; `ml-backends.md` covers device resolution). This spec covers the polars-native, Protocol-backed diagnostic adapters that instrument training loops AND retrieval-augmented-generation evaluation.
Scope authority: `kailash_ml.diagnostics.DLDiagnostics`, `kailash_ml.diagnostics.RAGDiagnostics` and their module-level helpers; the conformance contract against `kailash.diagnostics.protocols.Diagnostic`; the extras-gating contract for plotting surfaces and RAG backends.

Status: LIVE — `DLDiagnostics` landed in 0.16.0, `RAGDiagnostics` in 0.17.0 (both 2026-04-20). PR#1–PR#2 of 7 for the MLFP diagnostics donation plan tracked in kailash-py issue #567. See `workspaces/issue-567-mlfp-diagnostics/02-plans/SYNTHESIS-proposal.md` for the full 7-PR sequence.

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

| Version | Date       | Change                                                                                                                        |
| ------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 0.16.0  | 2026-04-20 | Spec authored alongside the `DLDiagnostics` port from MLFP. First Diagnostic adapter lands in kailash-ml.                     |
| 0.17.0  | 2026-04-20 | `RAGDiagnostics` section added (§11) alongside the MLFP Lens 3 port. Second Diagnostic adapter lands. `[rag]` optional extra. |

---

## 11. `RAGDiagnostics` Public API (0.17.0+)

### 11.1 Scope

`kailash_ml.diagnostics.RAGDiagnostics` is the retrieval-augmented-generation evaluation adapter. It scores a batch of `(query, retrieved_contexts, answer, retrieved_ids, ground_truth_ids)` tuples using:

- **IR metrics** — `recall@k`, `precision@k`, `reciprocal_rank` (MRR), `ndcg@k`. Pure-Python, deterministic, no LLM cost.
- **Faithfulness** — how grounded the answer is in the retrieved context. Sourced from `ragas` when installed, otherwise from a caller-supplied `JudgeCallable`, otherwise from a deterministic token-overlap heuristic.
- **Context utilisation** — fraction of answer tokens traceable to retrieved context. Token-overlap heuristic (fast, local, deterministic).
- **Retriever leaderboards** — side-by-side comparison of N retrievers on the same eval set.

### 11.2 Protocol Conformance Contract (same as §2)

`RAGDiagnostics` satisfies `kailash.diagnostics.protocols.Diagnostic` at runtime — `isinstance(rag, Diagnostic)` returns `True`. The Tier 2 wiring test (`tests/integration/test_rag_diagnostics_wiring.py::test_rag_diagnostics_satisfies_diagnostic_protocol`) asserts this explicitly.

### 11.3 Construction

```python
from kailash_ml.diagnostics import RAGDiagnostics

RAGDiagnostics(
    *,
    judge: Optional[JudgeCallable] = None,    # see kailash.diagnostics.protocols.JudgeCallable
    max_history: int = 1024,                   # deque(maxlen=N) — bounded memory
    max_leaderboard_history: int = 256,
    sensitive: bool = False,                   # redact query bodies in metrics_df
    run_id: Optional[str] = None,              # UUID4 hex if omitted
)
```

**Raises:**

- `ValueError` if `max_history < 1`, `max_leaderboard_history < 1`, or `run_id == ""`.
- `TypeError` if `judge` is not `None` and does not conform to `JudgeCallable` at runtime.

### 11.4 Core Methods

| Method                                                                                                | Purpose                                                                                                                                                               |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `evaluate(queries, retrieved_contexts, answers, *, ground_truth_ids, retrieved_ids, k=5, sub_run_id)` | Score a batch end-to-end. Returns polars DataFrame with one row per query and columns `idx, recall_at_k, precision_at_k, context_utilisation, faithfulness, k, mode`. |
| `compare_retrievers(retrievers, eval_set, *, k=5, sub_run_id)`                                        | Leaderboard over multiple retrievers. Returns polars DataFrame sorted by MRR descending.                                                                              |
| `recall_at_k(retrieved_ids, relevant_ids, *, k=5)`                                                    | Standalone IR metric: `\|retrieved ∩ relevant\| / \|relevant\|`.                                                                                                      |
| `precision_at_k(retrieved_ids, relevant_ids, *, k=5)`                                                 | Standalone IR metric: `\|retrieved ∩ relevant\| / \|retrieved\|`.                                                                                                     |
| `reciprocal_rank(retrieved_ids, relevant_ids)`                                                        | Standalone IR metric: `1/rank` of first relevant doc, `0` if none.                                                                                                    |
| `ndcg_at_k(retrieved_ids, relevant_ids, *, k=5)`                                                      | Standalone IR metric: binary-relevance normalised DCG.                                                                                                                |
| `context_utilisation(answer, contexts)`                                                               | Token-overlap heuristic, deterministic.                                                                                                                               |
| `ragas_scores(queries, retrieved_contexts, answers, *, ground_truth_ids)`                             | Run full RAGAS evaluation. **Requires `[rag]` extra**; raises `ImportError` when absent.                                                                              |
| `trulens_scores(queries, retrieved_contexts, answers)`                                                | Run trulens-eval auxiliary metrics. **Requires `[rag]` extra**; raises `ImportError` when absent.                                                                     |

### 11.5 Evaluation Mode Selection

`RAGDiagnostics.evaluate()` chooses its faithfulness backend automatically:

1. **`ragas`** — if installed (via `[rag]`), its `faithfulness` + `context_precision` metrics are used. Mode flag: `"ragas"`.
2. **`JudgeCallable`** — if `ragas` is absent AND the constructor received a `judge=...`, faithfulness routes through `JudgeCallable.__call__`. Mode flag: `"judge"` on success, `"judge_error"` on fallback to the heuristic.
3. **Metrics-only** — if `ragas` is absent AND no judge is configured, faithfulness defaults to the context-utilisation heuristic. Mode flag: `"metrics_only"`.

Every fallback is logged at WARN per `rules/dependencies.md` "Optional Extras with Loud Failure" so operators can see which backend produced each score.

### 11.6 DataFrame Accessors (polars-native)

| Method             | Columns (ordered)                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------- |
| `metrics_df()`     | `query_preview, recall_at_k, precision_at_k, context_utilisation, faithfulness, k, mode` |
| `leaderboard_df()` | `retriever, recall_at_k, precision_at_k, mrr, ndcg_at_k, n, k`                           |

Empty-state DataFrames have the correct schema with zero rows — safe to pass to downstream consumers that branch on `df.height`. `query_preview` is `"<redacted>"` when the session was constructed with `sensitive=True`.

### 11.7 `report()` — Diagnostic Protocol Contract

Returns a dict with this exact structure:

```python
{
    "run_id": str,
    "evaluations": int,                # count of evaluate() samples captured
    "retriever_comparisons": int,       # count of compare_retrievers() aggregates
    "retrieval": {"severity": Severity, "message": str,
                  "mean_recall_at_k": float, "mean_precision_at_k": float},
    "faithfulness": {"severity": Severity, "message": str, "mean_faithfulness": float},
    "context_utilisation": {"severity": Severity, "message": str, "mean_context_utilisation": float},
    "retriever_leaderboard": {"severity": Severity, "top": str | None,
                              "top_mrr": float, "top_ndcg_at_k": float, "message": str},
}
```

Where `Severity = Literal["HEALTHY", "WARNING", "CRITICAL", "UNKNOWN"]`. `UNKNOWN` is returned when the relevant history is empty.

Severity thresholds:

- **`retrieval = CRITICAL`** — mean recall@k < 0.3.
- **`retrieval = WARNING`** — 0.3 <= mean recall@k < 0.5.
- **`faithfulness = CRITICAL`** — mean faithfulness < 0.5.
- **`faithfulness = WARNING`** — 0.5 <= mean faithfulness < 0.7.
- **`context_utilisation = WARNING`** — mean utilisation < 0.3.

### 11.8 Plotting Methods (require `kailash-ml[dl]`)

| Method                         | Purpose                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------- |
| `plot_recall_curve()`          | Recall@k per query across captured evaluations.                                         |
| `plot_faithfulness_scatter()`  | Faithfulness vs context-utilisation scatter.                                            |
| `plot_retriever_leaderboard()` | Bar chart of retriever MRR + nDCG@k across compared retrievers.                         |
| `plot_rag_dashboard()`         | 2×2 subplot dashboard: recall curve, context-util histogram, faithfulness scatter, MRR. |

All route through `_require_plotly()` → `ImportError("pip install kailash-ml[dl]")` when plotly is absent.

### 11.9 Extras Gating

| Surface                                        | Base install | `[dl]` | `[rag]` |
| ---------------------------------------------- | :----------: | :----: | :-----: |
| `RAGDiagnostics.__init__`                      |      ✅      |   ✅   |   ✅    |
| IR metric helpers + `context_utilisation`      |      ✅      |   ✅   |   ✅    |
| `evaluate()` (metrics-only mode, no judge)     |      ✅      |   ✅   |   ✅    |
| `evaluate()` (with `JudgeCallable`)            |      ✅      |   ✅   |   ✅    |
| `evaluate()` (ragas-backed faithfulness)       |      ❌      |   ❌   |   ✅    |
| `metrics_df()`, `leaderboard_df()`, `report()` |      ✅      |   ✅   |   ✅    |
| `ragas_scores()`                               |      ❌      |   ❌   |   ✅    |
| `trulens_scores()`                             |      ❌      |   ❌   |   ✅    |
| `plot_*()`                                     |      ❌      |   ✅   |   ❌    |
| `plot_rag_dashboard()`                         |      ❌      |   ✅   |   ❌    |

The `[rag]` extra pins `ragas>=0.1`, `trulens-eval>=0.20`, `datasets>=2.0`. `[rag]` and `[dl]` compose orthogonally — a caller wanting ragas-backed scoring plus plotting installs `pip install kailash-ml[dl,rag]`.

### 11.10 Security Threats

| Threat                                                    | Mitigation                                                                                                                                                                                                                  |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Raw PII in query_preview column**                       | `sensitive=True` replaces query body with `"<redacted>"` in `metrics_df()`. Raw query fingerprinted via `sha256:<8-hex>` per `rules/event-payload-classification.md` §2.                                                    |
| **Unbounded memory growth on streaming eval loops**       | `deque(maxlen=max_history)` + `deque(maxlen=max_leaderboard_history)`. Both bounds validated at `__init__` (must be `>= 1`).                                                                                                |
| **Raw `openai.*` LLM call bypassing cost governance**     | All judge calls route through `kailash.diagnostics.protocols.JudgeCallable`. Caller supplies a cost-aware implementation. Raw OpenAI calls are `rules/framework-first.md` violations.                                       |
| **Silent fallback masks backend degradation**             | Every fallback path (`ragas_unavailable`, `ragas_error`, `judge_error`, `trulens_unavailable`, `trulens_no_provider`) emits a WARN log per `rules/dependencies.md`. Mode flag in `metrics_df` surfaces per-row degradation. |
| **JudgeCallable raises uncontrolled exception mid-batch** | `_judge_faithfulness()` catches `Exception`, logs at WARN, and falls back to the deterministic heuristic with `mode="judge_error"`. The batch continues; the row preserves a numeric score.                                 |
| **Non-finite judge score corrupts DataFrame**             | `_judge_faithfulness()` guards `not math.isfinite(score)` → WARN + heuristic fallback, same as exception path.                                                                                                              |

### 11.11 Observability

Every `RAGDiagnostics` method emits structured logs with the `rag_run_id` correlation field. Structured-field kwargs carry a `rag_` prefix to avoid `LogRecord` reserved-name collisions per `rules/observability.md` MUST Rule 9.

| Event                                     | Level | When                                                             |
| ----------------------------------------- | ----- | ---------------------------------------------------------------- |
| `ragdiagnostics.init`                     | INFO  | Session constructor completes.                                   |
| `ragdiagnostics.exit`                     | INFO  | Context-manager `__exit__` runs.                                 |
| `ragdiagnostics.evaluate.start`           | INFO  | `evaluate()` begins.                                             |
| `ragdiagnostics.evaluate.ok`              | INFO  | `evaluate()` completes with mean metrics.                        |
| `ragdiagnostics.compare_retrievers.start` | INFO  | `compare_retrievers()` begins.                                   |
| `ragdiagnostics.compare_retrievers.ok`    | INFO  | Leaderboard built with top retriever name.                       |
| `ragdiagnostics.report`                   | INFO  | `report()` completes with summary of severities.                 |
| `ragdiagnostics.ragas_unavailable`        | WARN  | `ragas` import failed; adapter falls back to judge/heuristic.    |
| `ragdiagnostics.ragas_error`              | WARN  | `ragas` internal error during evaluate.                          |
| `ragdiagnostics.trulens_unavailable`      | WARN  | `trulens-eval` import failed.                                    |
| `ragdiagnostics.trulens_no_provider`      | WARN  | trulens installed but no Provider configured.                    |
| `ragdiagnostics.judge_error`              | WARN  | JudgeCallable raised; fallback to heuristic.                     |
| `ragdiagnostics.judge_nonfinite_score`    | WARN  | Judge returned `None` / `NaN` / `Inf`; fallback to heuristic.    |
| `ragdiagnostics.judge_ok`                 | INFO  | Judge returned a finite score; includes `rag_cost_microdollars`. |

### 11.12 Test Contract

#### Tier 1 (Unit) — `tests/unit/test_rag_diagnostics_unit.py` (43 tests)

- `__init__` validation: empty `run_id`, zero `max_history`, zero `max_leaderboard_history`, non-`JudgeCallable` `judge`.
- Protocol conformance: `isinstance(rag, Diagnostic)`.
- IR metric math on known-answer fixtures (recall@k, precision@k, MRR, nDCG@k boundary cases).
- `evaluate()` input validation (empty queries, mismatched lengths, `k < 1`).
- Metrics-only mode end-to-end (no judge, no ragas).
- Bounded memory: `deque(maxlen=N)` FIFO eviction.
- `compare_retrievers()` input validation + leaderboard math.
- `report()` empty + CRITICAL severity paths.
- `metrics_df()` / `leaderboard_df()` empty-state schema.
- Plotly extras-gating loud-fail (`plot_recall_curve`, `plot_faithfulness_scatter`, `plot_retriever_leaderboard`, `plot_rag_dashboard`).
- ragas / trulens extras-gating loud-fail (`ragas_scores`, `trulens_scores`).
- Deterministic `context_utilisation` heuristic.
- JudgeCallable dispatch via a minimal in-process fake judge.
- Judge error fallback to heuristic with `mode="judge_error"`.

#### Tier 2 (Integration) — `tests/integration/test_rag_diagnostics_wiring.py` (13 tests)

Per `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md` Rule 2:

- Imports through `kailash_ml.diagnostics` facade (NOT the concrete module path).
- `isinstance(rag, Diagnostic)` holds at runtime.
- `_ScriptedJudge` (in-process real) satisfies `JudgeCallable` at runtime.
- End-to-end `evaluate()` with real Protocol dispatch across 3 queries.
- Metrics-only mode end-to-end (no judge).
- `run_id` propagates from constructor → `report()['run_id']`.
- `compare_retrievers()` produces MRR-sorted leaderboard across 3 retrievers.
- `sensitive=True` redacts `query_preview` AND keeps raw PII out of `repr(row)`.
- `__exit__` returns `None` and does not swallow exceptions.

### 11.13 Attribution

Originally contributed from MLFP `shared/mlfp06/diagnostics/retrieval.py` (Apache-2.0, 705 LOC). The Kailash port (`packages/kailash-ml/src/kailash_ml/diagnostics/rag.py`):

- Strips medical metaphors (no "Endoscope", no "Prescription Pad") from every docstring, method name, plot title, and log event.
- Routes all LLM-as-judge calls through `kailash.diagnostics.protocols.JudgeCallable` — no bespoke `JudgeCallable` wrapper around Kaizen `Delegate`; no raw `openai.*`.
- Replaces unbounded `list[dict]` storage with `collections.deque(maxlen=N)` for bounded memory on streaming eval loops.
- Adds `run_id` for Diagnostic Protocol conformance.
- `ragas` / `trulens-eval` / `datasets` imports wrapped with loud-fail contract per `rules/dependencies.md`.

Attribution is carried in each file's copyright header + module docstring + this spec. Cross-reference: kailash-py issue #567 (PR#2 of 7).

### 11.14 Cross-SDK Alignment

- **Python surface**: `kailash_ml.diagnostics.RAGDiagnostics` — lands in kailash-ml 0.17.0.
- **Rust surface**: No planned kailash-rs equivalent. RAG evaluation depends on `ragas` / `trulens-eval`, neither of which has a stable Rust binding. Cross-SDK agreement is at the Protocol level (`kailash.diagnostics.protocols.Diagnostic` + `JudgeCallable` + `schemas/trace-event.v1.json`), not at this concrete adapter.
- Future PRs #3–#7 (AlignmentDiagnostics, InterpretabilityDiagnostics, LLMDiagnostics, AgentDiagnostics, GovernanceEngine extensions) follow the same pattern: each adapter conforms to `Diagnostic`, each lives under a domain-specific optional extra, each ships with facade-import Tier 2 tests.
