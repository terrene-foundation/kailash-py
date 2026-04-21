# Kailash ML Autolog — Framework Auto-Instrumentation Entry Point

Version: 1.0.0 (draft)
Package: `kailash-ml`
Status: DRAFT at `workspaces/kailash-ml-audit/specs-draft/ml-autolog-draft.md`. Promotes to `specs/ml-autolog.md` after round-2 /redteam convergence.
Parent domain: ML Lifecycle.
Sibling specs: `ml-tracking.md` (source of truth for the `ExperimentRun` surface autolog emits to), `ml-diagnostics.md`, `ml-engines.md`.

Origin: Round-1 `round-1-industry-competitive.md` finding H-5 — "No `autolog()` equivalent (MLflow, Neptune, Comet, ClearML, W&B all have it)". Round-1 Table C row #3: MISSING. Round-1 synthesis T7 (industry parity sub-MLflow-1.0-2018) flags `km.autolog()` as the single largest table-stakes gap.

---

## 1. Scope

### 1.1 In Scope

- `km.autolog()` as an async context manager AND as a decorator that auto-logs metrics, params, artifacts, and models from popular ML / DL frameworks into the ambient `km.track()` run.
- Per-framework dispatch (Lightning, sklearn, transformers Trainer, xgboost, lightgbm, statsmodels, polars schema fingerprint).
- Opt-out per framework (`disable=[...]`).
- Loud failure when called outside `km.track()` (no silent no-op).
- Per-framework Tier-2 wiring tests that fit a toy model under `with km.track(): km.autolog(): fit()` and assert ≥3 metrics + 1 artifact.

### 1.2 Out of Scope

- The tracker itself (`ml-tracking.md`).
- DL diagnostic computation (gradient norms, dead-neuron detection) — `ml-diagnostics.md` owns that; autolog only hooks Lightning's public callback surface.
- RL autolog — `ml-rl.md` owns RL-specific auto-instrumentation; this spec covers classical ML + DL + transformers.
- Raw model inference — `ml-serving.md`.

### 1.3 Non-Goals

- **Not a monkey-patcher.** The 1.x approach of patching `sklearn.base.BaseEstimator.fit` globally is BLOCKED. Hooks attach within the scope of the `km.autolog()` block and detach on exit. Global patches leak across tests and produce cross-contamination failures.
- **Not a universal logger.** Frameworks without an explicit callback / hook API (e.g. fastai pre-v2) are not in scope for 2.0. User calls `run.log_metric(...)` manually.
- **No silent fallback.** If Lightning is imported but autolog cannot attach (version mismatch, missing callback hook), `AutologError` is raised — silent skip is BLOCKED.

---

## 2. Public API

### 2.1 Context Manager (Primary)

```python
@asynccontextmanager
async def autolog(
    *frameworks: str,
    disable: Optional[Sequence[str]] = None,
    log_models: bool = True,
    log_datasets: bool = True,
    log_figures: bool = True,
    log_system_metrics: bool = False,
    sample_rate_steps: int = 1,
) -> AsyncIterator[AutologHandle]: ...
```

**Positional arguments**: Names of frameworks to enable explicitly. Empty tuple (default) means "auto-detect every supported framework whose module is already imported in `sys.modules`".

**Keyword arguments**:

- `disable` — names to skip even if detected/enabled.
- `log_models` — emit `log_model()` calls for fitted models on `fit` exit.
- `log_datasets` — emit schema fingerprint for training data.
- `log_figures` — emit figures (confusion matrix, classification report) via `log_figure`.
- `log_system_metrics` — emit CPU/GPU util / memory per step (requires `psutil`; off by default to avoid cost).
- `sample_rate_steps` — only emit per-step metrics every Nth step (default 1 = every step).

```python
# DO — nested under km.track, zero user boilerplate
async with km.track("my-exp") as run:
    async with km.autolog():
        trainer = pl.Trainer(max_epochs=3)
        trainer.fit(model, datamodule)
# Metrics (loss, val_loss, learning_rate) + params (max_epochs, ...) +
# model artifact auto-emitted to `run`.

# DO — explicit framework selection
async with km.track("my-exp") as run:
    async with km.autolog("lightning", "sklearn"):
        ...

# DO — disable one framework
async with km.track("my-exp") as run:
    async with km.autolog(disable=["sklearn"]):
        ...

# DO NOT — call outside km.track()
async with km.autolog():   # raises AutologNoAmbientRunError
    ...
```

**MUST**: `autolog()` MUST raise `AutologNoAmbientRunError` (see §7) when called outside a `km.track()` block. Silent no-op is BLOCKED.

**Why:** Silent no-op is the failure mode of every competitor's autolog. Users think "I called autolog, metrics will appear" and then hours later discover the block ran before `start_run`. Loud failure at the entry is the only contract that delivers what the user asked for.

### 2.2 Decorator Form

```python
def autolog_fn(
    *frameworks: str,
    **kwargs,
) -> Callable[[Callable], Callable]: ...
```

**MUST**: The decorator form MUST wrap a callable with an internal `async with autolog(...)`. The wrapped callable MUST still run inside a `km.track()` context — the decorator does NOT auto-create a run.

```python
# DO — decorator inside a tracked function
@km.autolog_fn("lightning")
async def train(model, data):
    trainer = pl.Trainer(...)
    trainer.fit(model, data)

async with km.track("my-exp"):
    await train(model, data)  # autolog attaches for the duration of train()

# DO NOT — decorator without tracker
@km.autolog_fn("lightning")
async def train(...):
    ...
await train(...)  # raises AutologNoAmbientRunError
```

**Why:** A decorator that creates its own `km.track()` silently hides the run_id from the caller, which breaks `diff_runs`. The decorator is a scope helper, not a lifecycle helper.

---

## 3. Supported Frameworks

### 3.1 Matrix

| Framework                 | Identifier       | Hook mechanism                                                                                                  | Metrics auto-captured                                                                                                                     | Params auto-captured                                                                                  | Artifacts auto-captured                                                                                   |
| ------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| PyTorch Lightning         | `"lightning"`    | `pl.Callback` subclass attached to `Trainer`                                                                    | `train_loss_epoch`, `val_loss_epoch`, `train_loss_step`, `val_loss_step`, `lr-<optimizer_idx>`, user's `self.log`                         | `Trainer` init args, `max_epochs`, `accumulate_grad_batches`, `gradient_clip_val`, LR-scheduler class | Checkpoint at `trainer.checkpoint_callback.best_model_path`; `last.ckpt` on exit                          |
| scikit-learn              | `"sklearn"`      | Wrapper around `BaseEstimator.fit` via `functools.wraps` attached to the user's estimator instance (NOT global) | `score`, `best_score_` (for `GridSearchCV` / `RandomizedSearchCV`)                                                                        | `estimator.get_params(deep=True)`                                                                     | Fitted estimator via ONNX export; confusion matrix PNG for classifiers; `classification_report` as figure |
| HuggingFace Transformers  | `"transformers"` | `TrainerCallback` subclass attached to `Trainer`                                                                | `train_loss`, `eval_loss`, `eval_accuracy`, `learning_rate`, `train_runtime`, `train_samples_per_second`, `tokens_per_second_rolling_128` | `TrainingArguments` fields (every non-default attribute); for PEFT: `base.*` + `lora.*` split         | Best checkpoint directory; generated model card; adapter weights separately for PEFT                      |
| XGBoost                   | `"xgboost"`      | `xgb.callback.TrainingCallback` subclass                                                                        | `train-<metric>`, `eval-<metric>` per boosting round                                                                                      | `xgb_params` dict                                                                                     | Fitted booster saved via `booster.save_model`; feature importance as figure                               |
| LightGBM                  | `"lightgbm"`     | `lgb.callback.record_evaluation` hook                                                                           | `training_<metric>`, `valid_<metric>` per iteration                                                                                       | `lgb_params` dict                                                                                     | Fitted booster saved via `booster.save_model`; feature importance as figure                               |
| statsmodels               | `"statsmodels"`  | Wrapper around `Results.summary()`                                                                              | `rsquared`, `aic`, `bic`, `llf`, `f_pvalue`                                                                                               | `params` array serialized                                                                             | `summary().as_html()` as figure                                                                           |
| polars (data-fingerprint) | `"polars"`       | Passive — hooks `DataFrame.fit_transform` sites                                                                 | —                                                                                                                                         | `schema_fingerprint_sha256`, `row_count`, `column_count`                                              | —                                                                                                         |

### 3.1.1 PEFT / LoRA Fine-Tune — Base + Adapter Split Capture

The HF Transformers integration captures `model.config` to `run.log_params(...)` by default. When `isinstance(model, peft.PeftModel)` the integration MUST capture BOTH the base model config AND the PEFT adapter config under prefixed keys:

```python
# DO — base + lora captured separately
class TransformersAutologIntegration(FrameworkIntegration):
    def _on_init_end(self, args, state, control, model, **kwargs):
        import peft
        if isinstance(model, peft.PeftModel):
            base_model = model.get_base_model()
            base_config = base_model.config.to_dict()
            self._run.log_params({f"base.{k}": v for k, v in base_config.items()})

            # PEFT config — rank, alpha, dropout, target_modules, task_type
            for adapter_name, peft_config in model.peft_config.items():
                adapter_dict = peft_config.to_dict()
                self._run.log_params({
                    f"lora.{adapter_name}.{k}": v for k, v in adapter_dict.items()
                })

            # Fingerprint BOTH for reproducibility
            self._run.log_param("base_model_fingerprint", _sha256_of_state_dict(base_model))
            self._run.log_param("adapter_fingerprint", _sha256_of_state_dict(model))
        else:
            self._run.log_params(model.config.to_dict())

    def _on_save(self, args, state, control, **kwargs):
        # PEFT: save only the adapter weights, not the base weights
        import peft
        if isinstance(self._model, peft.PeftModel):
            adapter_path = self._model.save_pretrained(state.best_model_checkpoint, safe_serialization=True)
            self._run.log_artifact(adapter_path, name=f"lora_adapter_{state.global_step}.safetensors")
```

**MUST**:

1. When `isinstance(model, peft.PeftModel)`, `base.*` AND `lora.*` prefixed params are BOTH logged.
2. `base_model_fingerprint` (SHA-256 of the base model's state_dict) AND `adapter_fingerprint` (SHA-256 of the full PEFT state_dict) MUST be logged as SEPARATE params — the two fingerprints together form the reproducibility contract for the fine-tune.
3. Artifact storage MUST save the adapter-only weights via `model.save_pretrained(..., safe_serialization=True)` — NOT the base weights (which are already reproducible from the base model fingerprint).

**Why:** A PEFT LoRA fine-tune's `model.config` returns the BASE model config — losing the LoRA rank/alpha/target-modules/dropout which ARE the reproducibility contract. Base weights are reproducible from the base model reference; adapter weights are NOT reproducible without being stored. Saving both together is wasteful; saving only the adapter with the base fingerprint preserves full reproducibility.

### 3.1.2 Transformers Streaming Token-Per-Second — Rolling Window

`train_samples_per_second` and `tokens_per_second` emitted by HF Trainer are derived metrics that vary continuously during a stream. Per-step emission produces a volatile dashboard signal; lifetime emission conflates first-step burn-in with steady-state throughput.

```python
# MUST — rolling-window average, default 128 steps
class _RollingTokensPerSec:
    def __init__(self, window: int = 128):
        self._window = window
        self._buffer: deque[tuple[int, float]] = deque(maxlen=window)  # (tokens, elapsed_s)

    def update(self, tokens_this_step: int, elapsed_s: float) -> float:
        self._buffer.append((tokens_this_step, elapsed_s))
        total_tokens = sum(t for t, _ in self._buffer)
        total_elapsed = sum(e for _, e in self._buffer)
        return total_tokens / total_elapsed if total_elapsed > 0 else 0.0
```

**MUST**:

1. Emit `tokens_per_second_rolling_128` as a rolling-window-averaged metric (default window = 128 steps).
2. Window size is configurable via `AutologConfig.tokens_per_second_window: int = 128` but MUST NOT be < 8 (too volatile) or > 4096 (hides regressions).
3. The metric key includes the window size as suffix (`tokens_per_second_rolling_128`) so cross-run comparisons are window-size-aware.
4. The LIFETIME tokens-per-sec MAY be emitted as `tokens_per_second_lifetime` but MUST NOT replace the rolling metric as the primary signal.

**Why:** Per-step tokens/sec is noisy (first-token latency dwarfs subsequent tokens in decoding). Lifetime is biased by burn-in. A 128-step rolling window gives steady-state throughput that senior ML practitioners can compare across runs. 128 is empirically the smallest window where prefill artifacts wash out; 8192-token sequences converge within 2-3 windows.

### 3.1.3 HF Trainer `logging_steps` Propagation

When the user sets `TrainingArguments(logging_steps=N)`, HF Trainer emits every N steps. The Kailash autolog integration MUST propagate this cadence — autolog MUST wire to the `on_log` callback (which fires at `logging_steps` cadence) NOT `on_step_end` (which fires every step).

**Why:** Logging every step defeats the user's intent (and blows up the metric store); logging every 500 steps misses their data. Using the `on_log` callback respects the user's configured cadence exactly.

### 3.2 Framework Contract

**MUST**: Every framework integration MUST implement the `kailash_ml.autolog.FrameworkIntegration` abstract class:

```python
class FrameworkIntegration(ABC):
    name: ClassVar[str]

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True iff the framework is importable in the current process."""

    @abstractmethod
    def attach(self, run: "ExperimentRun", config: AutologConfig) -> None:
        """Install callbacks/hooks. Idempotent — double-attach is BLOCKED and raises."""

    @abstractmethod
    def detach(self) -> None:
        """Remove callbacks/hooks installed by attach(). Idempotent."""
```

**MUST**: `attach` is called on `__aenter__`, `detach` on `__aexit__` — even if the wrapped block raises. `detach` inside a `finally:` clause is mandatory.

**Why:** Leaving a Lightning callback attached after autolog exits means the next `Trainer.fit` in the same process logs to a stale `run_id` that no longer exists in the tracker. Dangling callbacks are the single biggest source of cross-test contamination.

### 3.3 DDP / FSDP / DeepSpeed / TP Rank-0-Only Emission (Decision 4)

**MUST**: Every framework integration MUST emit autolog events (metrics, params, models, figures, datasets) ONLY when the process is the global main process across ALL parallelism axes (DP rank-0 AND TP rank-0 AND PP rank-0). The gate MUST route through `DistributionEnv.is_main_process` (see `ml-diagnostics.md` §5.5) so Accelerate + DeepSpeed + tensor-parallel launchers are correctly detected.

```python
# DO — multi-axis rank gate routed through DistributionEnv
from kailash_ml.diagnostics.distribution import DistributionEnv

def _is_main_process() -> bool:
    """Returns True only on (DP rank 0) AND (TP rank 0) AND (PP rank 0)
    AND accelerator.is_main_process when Accelerate is active."""
    env = DistributionEnv.detect()
    return env.is_main_process

class TransformersAutologIntegration(FrameworkIntegration):
    def _on_log(self, args, state, control, logs, **kwargs):
        if not _is_main_process():
            return  # silent no-op on non-main-process workers
        self._run and self._run.log_metrics(logs, step=state.global_step)
```

**TP + PP coverage.** Under `accelerate launch --num_processes=8 --tp_size=2 --pp_size=2`, Trainer instantiates ONE Trainer per DP rank (4 DP ranks × 1 instance each). Without multi-axis gating, every DP rank emits autolog events → 4× duplicate metric rows. `DistributionEnv.is_main_process` returns True only on global rank 0 across ALL axes.

**Both-axis check required for Accelerate.** An Accelerate-launched run with `num_processes > 1` on a single GPU per machine has `torch.distributed.is_initialized() == False` on each process. The gate MUST check BOTH `torch.distributed.get_rank() == 0` AND `accelerate.PartialState().is_main_process` — single-check fallback fails on Accelerate.

**Why:** Lightning DDP, HF Trainer `deepspeed`/`fsdp`, accelerate launch, and tensor-parallel all spawn N processes. Without the multi-axis gate, every metric is written N times, producing duplicate rows in `_kml_metric` and corrupting every dashboard panel. Single-axis rank-0 gating (`torch.distributed.get_rank() == 0`) silently fails under Accelerate single-GPU-per-node AND under tensor-parallel. Decision 4 locks the multi-axis rule as a MUST clause, not an opt-in flag.

**Tier 2 tests**: `tests/integration/test_autolog_ddp_rank0_only_emission.py` MUST:

1. Mock `torch.distributed.get_rank()` → 1 on a worker process → assert NO metric row under run_id (DP rank gate).
2. Mock TP rank → 1 with DP rank → 0 → assert NO metric row (TP rank gate).
3. Mock Accelerate `PartialState().is_main_process` → False with torch.distributed unavailable → assert NO metric row (Accelerate single-GPU-per-node path).
4. Global main (all ranks 0, Accelerate.is_main_process True) → assert emission.
5. Rank-API-unavailable → treat as main, assert emission.

Origin: Decision 4 (approved 2026-04-21).

---

## 4. Dispatch

### 4.0 `AutologConfig` and `AutologHandle` dataclasses

The kwargs passed to `autolog()` (§2.1) MUST be captured in a frozen `AutologConfig` dataclass; the returned context value is `AutologHandle`. Both live at `kailash_ml.autolog.config`.

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class AutologConfig:
    """Immutable configuration snapshot for a single `km.autolog()` block.

    Constructed inside `autolog()` from the positional + keyword args the
    user supplied; passed to every FrameworkIntegration.attach() call so
    each integration reads from a consistent, non-mutating view.
    """

    frameworks: tuple[str, ...] = ("auto",)
    """Positional framework names, or ("auto",) for sys.modules-based detection."""

    log_models: bool = True
    """Emit log_model() calls for fitted models on fit-exit (§2.1)."""

    log_datasets: bool = True
    """Emit schema fingerprint for training data (§2.1)."""

    log_figures: bool = True
    """Emit figures (confusion matrix, classification report) via log_figure (§2.1)."""

    log_system_metrics: bool = False
    """Emit CPU/GPU util + memory per step (requires psutil; off by default)."""

    system_metrics_interval_s: int = 5
    """Seconds between system-metrics samples when log_system_metrics=True.
    Per Phase-B Round 2b §A.2 A-05 SAFE-DEFAULT (`system_metrics_interval_s=5`)."""

    sample_rate_steps: int = 1
    """Emit per-step metrics every Nth step. 1 = every step. Ignored by
    epoch-level metrics (§2.1)."""

    disable: tuple[str, ...] = ()
    """Framework names to skip even if detected. Unknown names raise
    AutologUnknownFrameworkError per §4.3."""

    disable_metrics: tuple[str, ...] = ()
    """Glob patterns for metric keys to drop at emit time (§5.2)."""


@dataclass(frozen=True)
class AutologHandle:
    """Runtime handle returned by `async with autolog() as handle:`.

    Exposes introspection on the live block; stop() deactivates attached
    integrations without waiting for __aexit__.
    """

    run_id: str
    """The ambient ExperimentRun.run_id captured at __aenter__ time."""

    config: AutologConfig
    """The frozen config this block is running under."""

    attached_integrations: tuple[str, ...]
    """Names of integrations that successfully attached (post auto-detect +
    disable filtering). Ordered by registration order."""

    @property
    def frameworks_active(self) -> list[str]:
        """Live names of frameworks whose callbacks are currently installed.
        Same as attached_integrations after successful attach; drops names
        whose detach was called via stop()."""
        ...

    def stop(self) -> None:
        """Early-detach every attached integration without exiting the
        context manager. Idempotent. After stop() the block still runs
        detach() on __aexit__, but the second pass is a no-op."""
        ...
```

**MUST:** `AutologConfig` is frozen. The `autolog()` context manager constructs it once at `__aenter__` and passes the same instance to every `FrameworkIntegration.attach(run, config)` call per §3.2.

**MUST:** `AutologHandle` is yielded by the async context manager; test code MAY introspect `handle.attached_integrations` to assert the expected set of frameworks attached (§8.2 Tier-2 tests).

### 4.1 Auto-Detection

**MUST**: When `autolog()` is called with no positional framework arguments, implementation MUST enumerate every registered `FrameworkIntegration` and call `is_available()`. Only integrations where `is_available()` returns True are attached.

```python
# DO — auto-detect
if not frameworks:
    frameworks = [
        integ.name for integ in _REGISTERED_INTEGRATIONS
        if integ.is_available()
    ]
```

**MUST**: `is_available()` MUST check the framework module in `sys.modules` — NOT by importing it. Auto-importing a framework the user did not import is BLOCKED (surprise-imports cost tens of seconds for torch/transformers).

```python
# DO — check sys.modules
@classmethod
def is_available(cls) -> bool:
    return "lightning" in sys.modules or "pytorch_lightning" in sys.modules

# DO NOT — import-test
@classmethod
def is_available(cls) -> bool:
    try:
        import lightning  # surprise-imports torch, transitively surprises many deps
        return True
    except ImportError:
        return False
```

### 4.2 Explicit Framework Selection

**MUST**: When `autolog("lightning", "sklearn")` is called with explicit names, EACH name MUST resolve to a registered integration. Unknown names raise `AutologUnknownFrameworkError` listing available names. Silent skip is BLOCKED.

### 4.3 `disable` Kwarg

**MUST**: `autolog(disable=["sklearn"])` removes sklearn from the attached set. `disable` names that do not resolve to registered integrations MUST raise `AutologUnknownFrameworkError` — silent accept of typos is BLOCKED.

### 4.4 Registration API

**MUST**: Third parties MAY register new integrations via:

```python
from kailash_ml.autolog import register_integration

@register_integration
class FastaiIntegration(FrameworkIntegration):
    name = "fastai"
    ...
```

The registry is process-local. Deregistration is supported via `unregister_integration(name)`.

---

## 5. Opt-Out

### 5.1 Per-Framework Disable

See §4.3. `disable=["sklearn"]` MUST be honored exactly once per `autolog()` block.

### 5.2 Per-Metric Disable

```python
async with km.autolog(disable_metrics=["train_loss_step"]):
    ...
```

**MUST**: `disable_metrics` MUST accept a list of glob patterns (`"train_loss_*"`, `"*_accuracy"`). Matching metrics are NOT emitted.

### 5.3 Total Disable

**MUST**: Setting env var `KAILASH_ML_AUTOLOG_DISABLED=1` short-circuits every `autolog()` call into a no-op context manager that still validates the ambient-run requirement (§2.1). This is the production "turn it all off without editing code" switch.

---

## 6. Ambient-Tracker Requirement

### 6.1 Loud Failure

**MUST**: `autolog()` MUST inspect `kailash_ml.tracking.get_current_run()` (the public accessor per `ml-tracking §10.1` — CRIT-4). If the return is `None`, raise `AutologNoAmbientRunError` with message:

```
autolog() called outside km.track() — metrics would have nowhere to go.
Wrap the call in `async with km.track("my-exp") as run: async with km.autolog(): ...`
```

Silent no-op is BLOCKED. Direct access to `kailash_ml.tracking.runner._current_run` is BLOCKED for library callers — the public accessor is the stable API.

```python
# DO — public accessor + raise loudly
from kailash_ml.tracking import get_current_run

async def __aenter__(self):
    run = get_current_run()
    if run is None:
        raise AutologNoAmbientRunError(
            "autolog() called outside km.track() — metrics have nowhere to go. "
            "Wrap in `async with km.track(name) as run: async with km.autolog(): ...`"
        )
    self._run = run
    for integ in self._integrations:
        integ.attach(run, self._config)

# DO NOT — reach into the internal ContextVar
from kailash_ml.tracking.runner import _current_run  # BLOCKED outside tracking package

# DO NOT — silent no-op
async def __aenter__(self):
    run = get_current_run()
    if run is None:
        return self   # silent no-op — hours of debugging for the user
```

**Why:** Round-1 `round-1-industry-competitive.md` H-5 — every competitor's autolog silently skips when no run is active. Users try it once, see nothing, and give up. Loud failure is the Foundation-layer differentiator for this feature.

### 6.2 Tenant Propagation

**MUST**: The ambient run's `tenant_id` (§7.2 in `ml-tracking-draft.md`) propagates to every metric / param / artifact emitted by autolog. No explicit `tenant_id=` is required on `autolog()` — the run carries it.

### 6.3 Actor Propagation

**MUST**: The ambient run's `actor_id` (§8.1 in `ml-tracking-draft.md`) propagates to every audit row written by autolog-emitted mutations. `autolog()` does NOT accept `actor_id=` — inherit from the run.

---

## 7. Errors

### 7.1 Typed Exceptions

All exceptions inherit from `AutologError(Exception)`:

| Exception                      | Raised when                                                                   |
| ------------------------------ | ----------------------------------------------------------------------------- |
| `AutologNoAmbientRunError`     | `autolog()` called outside `km.track()`                                       |
| `AutologUnknownFrameworkError` | Explicit positional name or `disable` name does not resolve to an integration |
| `AutologAttachError`           | A framework integration's `attach()` raised; wraps the inner exception        |
| `AutologDetachError`           | A framework integration's `detach()` raised on context-exit; wraps the inner  |
| `AutologDoubleAttachError`     | Framework integration's `attach` called twice without intervening `detach`    |

**MUST**: `AutologDetachError` MUST NOT swallow the original exception if the autolog block itself raised — it re-raises the user's exception while attaching the detach failure as `__context__`. Losing the user's stack is BLOCKED per `rules/zero-tolerance.md` Rule 3.

---

## 8. Test Matrix

### 8.1 Per-Framework Tier-2 Wiring Test

**MUST**: Each supported framework MUST have a Tier-2 wiring test at `packages/kailash-ml/tests/integration/autolog/test_<framework>_autolog_wiring.py`:

```python
# tests/integration/autolog/test_lightning_autolog_wiring.py
@pytest.mark.integration
async def test_lightning_autolog_emits_metrics_and_artifact(tmp_path):
    """Lightning autolog MUST emit ≥3 metrics + 1 artifact during fit()."""
    async with km.track("lightning-autolog-test", store=f"sqlite:///{tmp_path}/t.db") as run:
        async with km.autolog("lightning"):
            trainer = pl.Trainer(max_epochs=1, limit_train_batches=2, limit_val_batches=2)
            trainer.fit(ToyLightningModel(), ToyDataModule())

    # State-persistence verification (rules/testing.md § Tier 2)
    tracker = await km.open_tracker(f"sqlite:///{tmp_path}/t.db")
    metrics = await tracker.list_metrics(run.run_id)
    assert metrics.height >= 3, f"expected ≥3 metrics, got {metrics.height}"
    artifacts = await tracker.list_artifacts(run.run_id)
    assert artifacts.height >= 1, "expected ≥1 artifact (model checkpoint)"
    assert "train_loss_epoch" in metrics["key"].to_list()
```

**MUST**: The tests MUST fit a TOY model (small, CPU-only, ≤1 second). GPU / multi-node fixtures are out of scope for autolog tests.

**MUST**: Each test MUST use a file-backed SQLite (not in-memory) so `list_metrics` and `list_artifacts` exercise the full write/read round-trip — catches the two-tracker split class of bug the round-1 unification regression fixed.

**Required files**:

```
packages/kailash-ml/tests/integration/autolog/
  test_lightning_autolog_wiring.py
  test_sklearn_autolog_wiring.py
  test_transformers_autolog_wiring.py
  test_xgboost_autolog_wiring.py
  test_lightgbm_autolog_wiring.py
  test_statsmodels_autolog_wiring.py
  test_polars_autolog_wiring.py
```

### 8.2 Ambient-Run Regression

**MUST**: `tests/regression/test_autolog_requires_ambient_run.py` asserts `async with km.autolog(): ...` OUTSIDE a `km.track()` block raises `AutologNoAmbientRunError`. This test guards against a future "silent no-op" regression.

### 8.3 Disable / Dispatch Regressions

**MUST**: `tests/regression/test_autolog_unknown_framework.py` asserts `km.autolog("not_a_framework")` raises `AutologUnknownFrameworkError` with the message naming available integrations.

**MUST**: `tests/regression/test_autolog_disable.py` asserts `km.autolog("lightning", "sklearn", disable=["sklearn"])` attaches only lightning.

### 8.4 Double-Attach Regression

**MUST**: `tests/regression/test_autolog_double_attach.py` asserts that calling `attach()` twice on the same integration instance raises `AutologDoubleAttachError`. This guards against the "two `async with km.autolog()` blocks nested" failure mode.

### 8.5 Detach-On-Exception Regression

**MUST**: `tests/regression/test_autolog_detach_on_exception.py` asserts that when the inner `fit()` call raises, `detach()` still runs and the user's exception propagates with the original type/stack intact.

---

## 9. Industry Parity

### 9.1 What This Spec Closes

| Competitor | Autolog API                                              | Year shipped | kailash-ml 1.0.0 parity via this spec                                                |
| ---------- | -------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------ |
| MLflow     | `mlflow.autolog()`                                       | 2020         | YES — `km.autolog()` covers 6 of 7 MLflow-supported frameworks (no fastai, deferred) |
| ClearML    | `Task.init()` (auto)                                     | 2019         | YES — equivalent zero-config auto-capture when called inside `km.track()`            |
| Comet      | `Experiment()` (auto)                                    | 2019         | YES                                                                                  |
| Neptune    | `neptune.init_run()` auto-log integrations               | 2021         | YES                                                                                  |
| W&B        | `wandb.init()` + `wandb.config` + framework integrations | 2019         | YES                                                                                  |

### 9.2 What This Spec Explicitly Does NOT Match

| MLflow feature                         | Decision | Reason                                                                                                  |
| -------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------- |
| Global `mlflow.autolog()` monkey-patch | NO       | Scoped to `km.autolog()` block only — avoids the "mlflow forgot to patch itself on reload" class of bug |
| fastai integration                     | DEFERRED | fastai v2 callback stability is improving but not yet stable; defer to 2.1                              |
| PySpark ML autolog                     | NO       | DataFlow is the Foundation's data-layer path; PySpark autolog is out of scope                           |
| Keras standalone autolog               | NO       | Lightning covers PyTorch; tf.keras users can wire manual `log_metric` calls                             |

### 9.3 What This Spec Adds Beyond Competitors

- **Loud failure on no-ambient-run** (§6.1) — every competitor silently skips.
- **Tenant-scoped keyspace propagation** (§6.2) — no competitor models tenants first-class.
- **Actor audit trail** (§6.3) — no competitor emits audit rows per autolog-emitted mutation.
- **Opt-out via env var** (§5.3) — MLflow requires code edits; kailash-ml flips a flag.
- **Polars schema fingerprint** (§3.1 last row) — no competitor captures this.

---

## 10. Dependency Declaration

### 10.1 Optional Extras

**MUST**: Each framework integration is installed via an optional extra:

```toml
# packages/kailash-ml/pyproject.toml
[project.optional-dependencies]
autolog-lightning    = ["lightning>=2.0"]
autolog-sklearn      = ["scikit-learn>=1.3", "skl2onnx>=1.15"]
autolog-transformers = ["transformers>=4.35"]
autolog-xgboost      = ["xgboost>=2.0"]
autolog-lightgbm     = ["lightgbm>=4.0"]
autolog-statsmodels  = ["statsmodels>=0.14"]
autolog-all          = ["kailash-ml[autolog-lightning,autolog-sklearn,autolog-transformers,autolog-xgboost,autolog-lightgbm,autolog-statsmodels]"]
```

**MUST**: `FrameworkIntegration.is_available()` MUST gate cleanly — if the framework is not installed, `autolog()` skips attaching the integration (it simply is not in the enabled set). Raising `ImportError` from `is_available()` is BLOCKED.

Per `rules/dependencies.md` § Declared = Gated Consistently, every module that does `import lightning` etc. at module scope MUST be gated behind the matching extra. The pattern is:

```python
# src/kailash_ml/autolog/_lightning.py
try:
    import lightning.pytorch as pl
except ImportError:
    pl = None

class LightningIntegration(FrameworkIntegration):
    name = "lightning"

    @classmethod
    def is_available(cls) -> bool:
        return pl is not None and (
            "lightning" in sys.modules or "pytorch_lightning" in sys.modules
        )
```

---

## 11. Cross-SDK Parity

### 11.1 Rust Follow-Up

Per `rules/cross-sdk-inspection.md` §1, `km.autolog()` MUST have a cross-SDK parity tracker in kailash-rs. Rust targets:

- `tch-rs` / `candle` equivalents of Lightning's callback hooks.
- Rust-native XGBoost / LightGBM bindings if `xgboost-sys` matures.
- polars schema fingerprint (Rust polars already supports this).

The Rust issue is filed on the kailash-rs repo with label `cross-sdk` and a link to the merged kailash-py `ml-autolog.md` commit.

---

## 12. Changelog — 2.0.0

| Area                     | Change                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------ |
| `km.autolog()` added     | New async-context entry point                                                              |
| `km.autolog_fn()` added  | New decorator entry point                                                                  |
| 6 frameworks supported   | Lightning, sklearn, transformers, xgboost, lightgbm, statsmodels (plus polars fingerprint) |
| Loud no-ambient-run      | `AutologNoAmbientRunError` when called outside `km.track()`                                |
| Tenant + actor propagate | Automatic from ambient run                                                                 |
| Env var disable          | `KAILASH_ML_AUTOLOG_DISABLED=1` for prod off-switch                                        |
| Optional extras          | `autolog-<framework>` + `autolog-all`                                                      |

---

## Appendix A. RESOLVED — Prior Open Questions

All round-2 open questions are RESOLVED. Phase-B SAFE-DEFAULTs A-01..A-07 live in `workspaces/kailash-ml-audit/04-validate/round-2b-open-tbd-triage.md` § A (autolog). This appendix is retained for traceability.

| Original TBD                                                  | Disposition                                                                                                                                                           | Reference                             |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Transformers model-card emission                              | **PINNED** — auto-call `generate_model_card(model)` on fit-exit behind `log_models=True` (default True).                                                              | Phase-B SAFE-DEFAULT A-01             |
| Sklearn ONNX export failure disposition                       | **PINNED** — fall back to pickle with WARN log `autolog.sklearn.onnx_failed`; pickle artifacts flagged `onnx_status="legacy_pickle_only"` per `ml-tracking.md` §12.2. | Phase-B SAFE-DEFAULT A-02             |
| Per-batch vs per-epoch default (`sample_rate_steps`)          | **PINNED** — default 1 for epoch-level (emitted anyway); sampled 1-in-10 for step-level metrics on long runs.                                                         | Phase-B SAFE-DEFAULT A-03             |
| Polars fingerprint scope                                      | **PINNED** — hook only explicit user-supplied `train_data`; do NOT hook `DataFrame.to_torch()` / `.to_numpy()` sites.                                                 | Phase-B SAFE-DEFAULT A-04             |
| System-metrics sampling interval                              | **PINNED** — `system_metrics_interval_s=5` default when `log_system_metrics=True`. Configurable.                                                                      | Phase-B SAFE-DEFAULT A-05             |
| Thread-safety of attach/detach under DDP / joblib / DeepSpeed | **PINNED** — rank-0-only emission for autolog + DLDiagnostics. Hardcoded to `torch.distributed.get_rank() == 0` on distributed training; not configurable.            | Decision 4; Phase-B SAFE-DEFAULT A-06 |
| Cross-framework conflict (Lightning + transformers)           | **PINNED** — emit both integrations; the transformers integration captures tokens-per-second that Lightning does not. No de-duplication.                              | Phase-B SAFE-DEFAULT A-07             |

---

_End of spec. Authored per `rules/specs-authority.md` + `rules/rule-authoring.md` + `rules/facade-manager-detection.md` + `rules/dependencies.md` § Declared = Gated Consistently. Closes round-1 industry finding H-5 + synthesis theme T7. Complementary to `ml-tracking-draft.md` §10 (ambient contextvar propagation)._
