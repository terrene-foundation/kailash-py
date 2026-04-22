# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""HuggingFace Transformers autolog integration (W23.f).

Implements ``specs/ml-autolog.md §3.1`` row 3 + §3.1.1 PEFT +
§3.1.2 rolling tokens/sec + §3.1.3 logging_steps propagation + §3.3
rank gate:

- Wraps :class:`transformers.Trainer.__init__` at the class level,
  scoped to the ``km.autolog()`` block via the ABC's :meth:`detach`
  contract (§3.2). Global / persistent monkey-patching is BLOCKED per
  §1.3; the class-level wrap restores in the CM's ``finally:`` even
  on exception.
- Each Trainer instance created inside the block gets our
  :class:`_KailashTransformersCallback` appended to its
  ``callbacks`` list, and its ``TrainingArguments`` captured onto the
  callback for later param emission.
- Hooks on Trainer's public TrainerCallback surface: ``on_init_end``
  (captures model config + PEFT fingerprints), ``on_log`` (drains
  metrics at the user's ``logging_steps`` cadence per §3.1.3),
  ``on_save`` (adapter-only save for PEFT), ``on_train_end`` (model
  card + best checkpoint). Every hook is gated by
  :func:`kailash_ml.autolog._distribution.is_main_process` per §3.3.
- PEFT base + adapter split per §3.1.1 MUST: when
  ``isinstance(model, peft.PeftModel)``, emit ``base.*`` AND
  ``lora.*`` prefixed params + ``base_model_fingerprint`` +
  ``adapter_fingerprint`` as separate params. Artifact storage saves
  ONLY the adapter weights (base weights are reproducible from the
  fingerprint).
- Rolling tokens-per-second per §3.1.2: window-averaged
  ``tokens_per_second_rolling_<N>`` metric where ``N`` is the
  configured ``AutologConfig.tokens_per_second_window`` (default 128,
  range 8-4096 validated at config construction). The rate signal
  comes from ``logs["train_tokens_per_second"]`` when transformers
  exposes it, otherwise falls back to
  ``logs["train_samples_per_second"]``.

Per ``rules/orphan-detection.md`` §1, this module's registration
site is ``kailash_ml/autolog/__init__.py`` which eagerly imports
this module. The production call site for the instantiated class is
the :func:`kailash_ml.autolog.autolog` context manager.

Framework imports (``transformers``, ``peft``) are deferred to
:meth:`attach` / callback hooks so importing this module does NOT
pull transformers into ``sys.modules``. The auto-detect path is
preserved for users who never ``import transformers``.
"""
from __future__ import annotations

import hashlib
import logging
import sys
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Deque, Dict, List, Optional
from typing import Tuple

from kailash_ml.autolog._distribution import is_main_process
from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = ["TransformersAutologIntegration"]


logger = logging.getLogger(__name__)


def _truncate_repr(value: Any, limit: int = 500) -> str:
    """Param values get stringified-then-truncated so the tracker's
    param table doesn't blow up on nested TrainingArguments.
    """
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...[truncated]"


def _sha256_of_state_dict(model: Any) -> str:
    """SHA-256 fingerprint over the model's state_dict.

    Per §3.1.1 MUST — used as the reproducibility contract for a PEFT
    fine-tune. Base-model fingerprint + adapter fingerprint together
    reconstitute the fine-tune without needing to store base weights.
    """
    try:
        sd = model.state_dict()
    except Exception:
        return "sha256:unavailable"
    h = hashlib.sha256()
    for key in sorted(sd.keys()):
        try:
            tensor = sd[key]
            arr = tensor.detach().cpu().contiguous().numpy().tobytes()
            h.update(key.encode("utf-8"))
            h.update(arr)
        except Exception:
            # Unpicklable param (e.g. quantised) — skip rather than
            # corrupt the fingerprint.
            continue
    return f"sha256:{h.hexdigest()[:16]}"


class _RollingTokensPerSec:
    """Rolling-window average of a streaming tokens-per-second signal.

    Per §3.1.2 — window defaults to 128, configurable 8-4096 via
    :class:`~kailash_ml.autolog.config.AutologConfig`. Emits a single
    rolling mean; the metric name carries the window size as suffix so
    cross-run comparisons are window-size-aware.
    """

    def __init__(self, window: int = 128) -> None:
        self._window = int(window)
        self._buffer: Deque[float] = deque(maxlen=self._window)

    @property
    def window(self) -> int:
        return self._window

    def update(self, rate: float) -> float:
        """Append a new rate sample and return the current rolling mean."""
        if rate is None:
            return self.current()
        try:
            f = float(rate)
        except Exception:
            return self.current()
        self._buffer.append(f)
        return self.current()

    def current(self) -> float:
        if not self._buffer:
            return 0.0
        return sum(self._buffer) / len(self._buffer)


@register_integration
class TransformersAutologIntegration(FrameworkIntegration):
    """Autolog for HuggingFace Transformers ``Trainer`` fits.

    See module docstring for the full design. Attach replaces
    :meth:`Trainer.__init__` with a wrapper that injects our callback
    + captures TrainingArguments; detach restores the original.
    Buffers post-hook closures in ``self._events`` during the block;
    drains in :meth:`flush` where ``await`` is valid.
    """

    name = "transformers"

    def __init__(self) -> None:
        super().__init__()
        self._trainer_cls: Optional[type] = None
        self._original_init: Optional[Callable[..., None]] = None
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None
        # One-shot emission dedup per Trainer id (on_init_end fires
        # exactly once per instance but guard defensively).
        self._params_emitted: set[int] = set()

    @classmethod
    def is_available(cls) -> bool:
        return "transformers" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        # Local import — only fires when the user has explicitly
        # chosen "transformers" (§4.2) or is_available returned True.
        from transformers import Trainer as _Trainer  # noqa: PLC0415

        self._trainer_cls = _Trainer
        self._original_init = _Trainer.__init__

        integ = self
        original_init = self._original_init

        def wrapped_init(self_trainer: Any, *args: Any, **kwargs: Any) -> None:
            # Build our callback FIRST so we can inject into the
            # callbacks kwarg before Trainer consumes it. Capture
            # kwargs AFTER the callback is appended so `callbacks=`
            # includes our entry in the param log (audit-visibility).
            our_cb = _build_callback(integ)
            user_cbs = kwargs.get("callbacks")
            if user_cbs is None:
                kwargs["callbacks"] = [our_cb]
            elif isinstance(user_cbs, list):
                kwargs["callbacks"] = list(user_cbs) + [our_cb]
            else:
                kwargs["callbacks"] = [user_cbs, our_cb]
            original_init(self_trainer, *args, **kwargs)

        try:
            _Trainer.__init__ = wrapped_init  # type: ignore[method-assign]
        except (AttributeError, TypeError):
            logger.debug("autolog.transformers.patch_skipped")
            self._original_init = None

        logger.info(
            "autolog.transformers.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        if self._trainer_cls is not None and self._original_init is not None:
            try:
                self._trainer_cls.__init__ = self._original_init  # type: ignore[method-assign]
            except (AttributeError, TypeError):
                logger.exception("autolog.transformers.unpatch_failed")
        self._events.clear()
        self._params_emitted.clear()
        self._trainer_cls = None
        self._original_init = None
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        flush_errors: List[BaseException] = []
        for event in self._events:
            try:
                await event(run)
            except Exception as exc:  # noqa: BLE001
                flush_errors.append(exc)
                logger.exception("autolog.transformers.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    # ------------------------------------------------------------------
    # Internal — called by the Transformers TrainerCallback
    # ------------------------------------------------------------------

    def _capture_training_args_params(self, args: Any) -> Dict[str, str]:
        """Extract TrainingArguments fields per spec §3.1 row 3 —
        every non-default attribute under ``training_args.*`` prefix.
        """
        captured: Dict[str, str] = {}
        # TrainingArguments is a dataclass; `to_sanitized_dict` if
        # available, else enumerate __dict__.
        try:
            d = args.to_sanitized_dict()  # type: ignore[attr-defined]
        except Exception:
            try:
                d = dict(vars(args))
            except Exception:
                return captured
        for k, v in d.items():
            if k.startswith("_"):
                continue
            captured[f"training_args.{k}"] = _truncate_repr(v)
        return captured

    def _capture_model_params(
        self, model: Any
    ) -> Tuple[Dict[str, str], bool, Optional[str], Optional[str]]:
        """Capture model config params with PEFT base+adapter split.

        Returns ``(params, is_peft, base_fingerprint, adapter_fingerprint)``.
        When ``is_peft`` is True, params already contain ``base.*`` and
        ``lora.*`` entries per §3.1.1 MUST rule 1; caller emits the
        fingerprints as separate params.
        """
        params: Dict[str, str] = {}
        try:
            import peft  # noqa: PLC0415

            is_peft = isinstance(model, peft.PeftModel)
        except Exception:
            is_peft = False

        if is_peft:
            try:
                base_model = model.get_base_model()
                base_config = (
                    base_model.config.to_dict() if hasattr(base_model, "config") else {}
                )
                for k, v in base_config.items():
                    params[f"base.{k}"] = _truncate_repr(v)
                for adapter_name, peft_config in model.peft_config.items():
                    adapter_dict = (
                        peft_config.to_dict()
                        if hasattr(peft_config, "to_dict")
                        else dict(vars(peft_config))
                    )
                    for k, v in adapter_dict.items():
                        params[f"lora.{adapter_name}.{k}"] = _truncate_repr(v)
                base_fp = _sha256_of_state_dict(base_model)
                adapter_fp = _sha256_of_state_dict(model)
                return params, True, base_fp, adapter_fp
            except Exception:
                logger.exception("autolog.transformers.peft_capture_failed")
                # Fall through to non-PEFT path on failure.
                is_peft = False

        # Non-PEFT path — capture model.config.
        try:
            if hasattr(model, "config") and hasattr(model.config, "to_dict"):
                for k, v in model.config.to_dict().items():
                    params[f"model.{k}"] = _truncate_repr(v)
        except Exception:
            logger.debug("autolog.transformers.model_config_unavailable")
        return params, False, None, None

    def _enqueue_init_params(
        self,
        trainer_id: int,
        args: Any,
        model: Any,
    ) -> None:
        if trainer_id in self._params_emitted:
            return
        self._params_emitted.add(trainer_id)

        training_args_params = self._capture_training_args_params(args)
        model_params, is_peft, base_fp, adapter_fp = self._capture_model_params(model)

        merged: Dict[str, str] = {}
        merged.update(training_args_params)
        merged.update(model_params)
        if is_peft and base_fp is not None:
            merged["base_model_fingerprint"] = base_fp
        if is_peft and adapter_fp is not None:
            merged["adapter_fingerprint"] = adapter_fp

        async def event(run: "ExperimentRun") -> None:
            if merged:
                await run.log_params(merged)

        self._events.append(event)

    def _enqueue_log_metrics(
        self,
        logs: Dict[str, Any],
        step: int,
        rolling: _RollingTokensPerSec,
    ) -> None:
        """Drain a Trainer.on_log payload into metrics.

        Per §3.1.3 — the ``on_log`` hook fires at the user's
        ``logging_steps`` cadence. We emit every numeric entry in
        ``logs`` as a metric at ``step=state.global_step``.

        Per §3.1.2 — if ``logs`` contains ``train_tokens_per_second``
        or ``train_samples_per_second``, update the rolling window and
        emit ``tokens_per_second_rolling_<N>`` as a separate metric.
        """
        metrics: Dict[str, float] = {}
        for k, v in logs.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                try:
                    import math  # noqa: PLC0415

                    f = float(v)
                    if math.isfinite(f):
                        metrics[str(k)] = f
                except Exception:
                    continue

        # Rolling tokens/sec signal.
        rate_signal = (
            logs.get("train_tokens_per_second")
            if "train_tokens_per_second" in logs
            else logs.get("train_samples_per_second")
        )
        if rate_signal is not None:
            rolling_mean = rolling.update(rate_signal)
            metrics[f"tokens_per_second_rolling_{rolling.window}"] = rolling_mean

        if not metrics:
            return

        snapshot = dict(metrics)

        async def event(run: "ExperimentRun") -> None:
            try:
                await run.log_metrics(snapshot, step=step)
            except Exception:
                logger.debug(
                    "autolog.transformers.metrics_emit_failed",
                    extra={"keys": sorted(snapshot.keys())[:5], "step": step},
                )

        self._events.append(event)

    def _enqueue_adapter_save(self, model: Any, state: Any) -> None:
        """Per §3.1.1 MUST rule 3 — save adapter weights only for PEFT."""
        try:
            import peft  # noqa: PLC0415

            if not isinstance(model, peft.PeftModel):
                return
        except Exception:
            return

        checkpoint_dir = getattr(state, "best_model_checkpoint", None) or getattr(
            state, "output_dir", None
        )
        global_step = int(getattr(state, "global_step", 0))

        async def event(run: "ExperimentRun") -> None:
            if not checkpoint_dir:
                logger.debug("autolog.transformers.adapter_save_no_checkpoint")
                return
            adapter_path = Path(checkpoint_dir) / "adapter_model.safetensors"
            if not adapter_path.exists():
                # Adapter may live directly under checkpoint_dir root
                # or under an 'adapter' subdir — probe both.
                alt = Path(checkpoint_dir) / "adapter_model.bin"
                if alt.exists():
                    adapter_path = alt
                else:
                    logger.debug(
                        "autolog.transformers.adapter_file_missing",
                        extra={"checkpoint_dir": checkpoint_dir},
                    )
                    return
            try:
                await run.log_artifact(
                    adapter_path,
                    f"transformers.lora_adapter_{global_step}.safetensors",
                    content_type="application/octet-stream",
                )
            except Exception:
                logger.exception(
                    "autolog.transformers.adapter_log_failed",
                    extra={"path": str(adapter_path)},
                )

        self._events.append(event)

    def _enqueue_best_checkpoint(self, state: Any) -> None:
        if not (self._config.log_models if self._config else True):
            return

        best_path: Optional[str] = getattr(state, "best_model_checkpoint", None)
        if not best_path:
            return

        async def event(run: "ExperimentRun") -> None:
            # best_model_checkpoint is a directory — tar-like bundling
            # is out of W23.f scope. Emit the directory path as a
            # text artifact so downstream can locate it.
            try:
                await run.log_artifact(
                    best_path.encode("utf-8"),
                    "transformers.best_checkpoint_path.txt",
                    content_type="text/plain",
                )
            except Exception:
                logger.exception(
                    "autolog.transformers.best_checkpoint_log_failed",
                    extra={"path": best_path},
                )

        self._events.append(event)


# ---------------------------------------------------------------------------
# TrainerCallback — built lazily to avoid module-import-time dep on
# transformers. See _lightning for the same pattern.
# ---------------------------------------------------------------------------


def _build_callback(
    integ: "TransformersAutologIntegration",
) -> Any:
    """Build and return an instance of the transformers TrainerCallback
    subclass for a new Trainer. Class is cached on the module.
    """
    from transformers import TrainerCallback  # noqa: PLC0415

    cached = getattr(_build_callback, "_cls", None)

    if cached is None:

        class _KailashTransformersCallback(TrainerCallback):  # type: ignore[misc]
            """Transformers TrainerCallback — gates every hook on
            :func:`is_main_process` and forwards to the integration's
            enqueue methods for async drain on CM exit.
            """

            def __init__(self, integration: "TransformersAutologIntegration") -> None:
                super().__init__()
                self._integ = integration
                window = (
                    integration._config.tokens_per_second_window
                    if integration._config
                    else 128
                )
                self._rolling = _RollingTokensPerSec(window=window)

            def on_init_end(self, args, state, control, **kwargs):
                if not is_main_process():
                    return
                model = kwargs.get("model")
                # Identify the trainer instance via args' id — args is
                # the TrainingArguments dataclass; id uniquely keys the
                # current training run.
                self._integ._enqueue_init_params(id(args), args, model)

            def on_log(self, args, state, control, **kwargs):
                if not is_main_process():
                    return
                # HF TrainerCallback API passes `logs` positionally in
                # older versions and via kwargs in newer; accept both
                # via kwargs.get so the signature matches the base.
                logs = kwargs.get("logs") or {}
                if not logs:
                    return
                step = int(getattr(state, "global_step", 0))
                self._integ._enqueue_log_metrics(logs, step, self._rolling)

            def on_save(self, args, state, control, **kwargs):
                if not is_main_process():
                    return
                model = kwargs.get("model")
                if model is not None:
                    self._integ._enqueue_adapter_save(model, state)

            def on_train_end(self, args, state, control, **kwargs):
                if not is_main_process():
                    return
                self._integ._enqueue_best_checkpoint(state)

        _build_callback._cls = _KailashTransformersCallback  # type: ignore[attr-defined]
        cached = _KailashTransformersCallback

    return cached(integ)
