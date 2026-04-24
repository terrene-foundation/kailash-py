# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PyTorch Lightning autolog integration (W23.e).

Implements ``specs/ml-autolog.md §3.1`` row 1 + §3.3:

- Wraps :meth:`lightning.pytorch.Trainer.__init__` at the class level,
  scoped to the ``km.autolog()`` block via the ABC's :meth:`detach`
  contract (§3.2). Global / persistent monkey-patching is BLOCKED per
  §1.3; the class-level wrap restores in the CM's ``finally:`` even
  on exception.
- Each Trainer instance created inside the block gets our
  :class:`_KailashAutologCallback` appended to its ``callbacks`` list,
  and its init kwargs captured onto the callback for later param
  emission.
- The callback fires on Lightning's public callback hooks
  (``setup``, ``on_train_batch_end``, ``on_train_epoch_end``,
  ``on_validation_epoch_end``, ``on_train_end``). Every hook is gated
  by :func:`kailash_ml.autolog._distribution.is_main_process` per §3.3 +
  Decision 4 — multi-axis rank-0 gate (DP × TP × PP × Accelerate) so
  DDP / FSDP / DeepSpeed / tensor-parallel launchers all emit exactly
  once.
- Captured signals:
    * **Metrics** (gated by step / epoch cadence):
      - ``train_loss_step``, user's ``self.log(..., on_step=True)``
        payloads — per-step via ``on_train_batch_end``
      - ``train_loss_epoch``, user's ``self.log(..., on_epoch=True)``
        payloads — per-epoch via ``on_train_epoch_end``
      - ``val_loss_epoch``, user's val ``self.log`` payloads —
        per-epoch via ``on_validation_epoch_end``
      - ``lr-<i>`` for each optimizer — per-step LR snapshot
    * **Params**: ``Trainer.__init__`` kwargs (``max_epochs``,
      ``accumulate_grad_batches``, ``gradient_clip_val``, etc.) under
      ``trainer.*`` prefix; LR-scheduler class name under
      ``trainer.lr_scheduler_class``.
    * **Artifacts**: best checkpoint + ``last.ckpt`` on train-end
      (gated by ``log_models``). Paths come from
      ``trainer.checkpoint_callback`` when Lightning's built-in
      ``ModelCheckpoint`` is active; otherwise skipped.

Per ``rules/orphan-detection.md`` §1, this module's registration site
is ``kailash_ml/autolog/__init__.py`` which eagerly imports this
module — the :func:`register_integration` decorator fires at import
time. The production call site for the instantiated class is the
:func:`kailash_ml.autolog.autolog` context manager, which reads
:data:`_REGISTERED_INTEGRATIONS` during auto-detect (§4.1) and
explicit-name resolution (§4.2).

Framework imports (``lightning``, ``pytorch_lightning``) are deferred
to :meth:`attach` so importing this module does NOT pull Lightning
into ``sys.modules``. The auto-detect path is preserved for users
who never ``import lightning``.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from kailash_ml.autolog._distribution import is_main_process
from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = ["LightningIntegration"]


logger = logging.getLogger(__name__)


def _truncate_repr(value: Any, limit: int = 500) -> str:
    """Param values get stringified-then-truncated so the tracker's
    param table doesn't blow up on Trainer kwargs that nest complex
    objects (e.g. a plugins list).
    """
    rendered = repr(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...[truncated]"


def _capture_trainer_init_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Trainer init kwargs into a plain dict for param emission.

    Per spec §3.1 row 1: capture every non-default attribute. We emit
    everything the user passed — Lightning's own default filtering
    happens on the receiving side (the tracker's param table
    understands string reprs).
    """
    return {k: v for k, v in kwargs.items() if not k.startswith("_")}


@register_integration
class LightningIntegration(FrameworkIntegration):
    """Autolog for PyTorch Lightning ``Trainer`` fits.

    See module docstring for the full design. Attach replaces
    :meth:`Trainer.__init__` with a wrapper that injects our callback
    + captures init kwargs; detach restores the original. Buffers
    post-hook closures in ``self._events`` during the block; drains
    in :meth:`flush` where ``await`` is valid.
    """

    name = "lightning"

    def __init__(self) -> None:
        super().__init__()
        self._trainer_cls: Optional[type] = None
        self._original_init: Optional[Callable[..., None]] = None
        self._events: List[Callable[["ExperimentRun"], Awaitable[None]]] = []
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None
        # Params emitted exactly once per Trainer instance — the
        # `setup()` hook fires once per (trainer, stage) pair, so we
        # guard with a set to avoid duplicate emission on val-after-
        # train transitions.
        self._params_emitted: set[int] = set()

    @classmethod
    def is_available(cls) -> bool:
        # §4.1 — sys.modules check only; surprise-importing lightning is
        # BLOCKED per the "zero overhead when unused" contract.
        return "lightning" in sys.modules or "pytorch_lightning" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config

        # Local import — only fires when the user has explicitly
        # chosen "lightning" (§4.2) or is_available returned True.
        # Prefer the post-1.9 `lightning.pytorch` namespace; fall back
        # to the legacy `pytorch_lightning` name.
        try:
            from lightning.pytorch import Trainer as _Trainer  # noqa: PLC0415
        except ImportError:
            from pytorch_lightning import Trainer as _Trainer  # noqa: PLC0415

        self._trainer_cls = _Trainer
        self._original_init = _Trainer.__init__

        integ = self
        original_init = self._original_init

        def wrapped_init(self_trainer: Any, *args: Any, **kwargs: Any) -> None:
            # Capture init kwargs BEFORE init — `_Trainer.__init__`
            # may transform / consume them internally (callbacks get
            # moved into trainer.callbacks, etc.).
            captured = _capture_trainer_init_kwargs(kwargs)

            # Build our callback and append to the user's callbacks
            # list. Lightning accepts a single Callback or a list;
            # normalise to list-of-callbacks so we never overwrite.
            our_cb = _KailashAutologCallback(integ, captured)
            user_cbs = kwargs.get("callbacks")
            if user_cbs is None:
                kwargs["callbacks"] = [our_cb]
            elif isinstance(user_cbs, list):
                kwargs["callbacks"] = list(user_cbs) + [our_cb]
            else:
                # Single-callback input — wrap + append.
                kwargs["callbacks"] = [user_cbs, our_cb]

            original_init(self_trainer, *args, **kwargs)

        try:
            _Trainer.__init__ = wrapped_init  # type: ignore[method-assign]
        except (AttributeError, TypeError):
            # Class-level attr on Trainer should always be writable,
            # but guard for parity with sibling integrations.
            logger.debug("autolog.lightning.patch_skipped")
            self._original_init = None

        logger.info(
            "autolog.lightning.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        if self._trainer_cls is not None and self._original_init is not None:
            try:
                self._trainer_cls.__init__ = self._original_init  # type: ignore[method-assign]
            except (AttributeError, TypeError):
                logger.exception("autolog.lightning.unpatch_failed")
        self._events.clear()
        self._params_emitted.clear()
        self._trainer_cls = None
        self._original_init = None
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        """Drain buffered Lightning-callback events to the tracker.

        Per ``rules/zero-tolerance.md`` Rule 3, the first event failure
        is re-raised so the CM's finally block surfaces it via
        :class:`AutologDetachError`. Subsequent event failures are
        logged but don't shadow the first.
        """
        flush_errors: List[BaseException] = []
        for event in self._events:
            try:
                await event(run)
            except Exception as exc:  # noqa: BLE001
                flush_errors.append(exc)
                logger.exception("autolog.lightning.event_failed")
        self._events.clear()
        if flush_errors:
            raise flush_errors[0]

    # ------------------------------------------------------------------
    # Internal — called by the Lightning callback
    # ------------------------------------------------------------------

    def _enqueue_params(self, trainer: Any, init_kwargs: Dict[str, Any]) -> None:
        trainer_id = id(trainer)
        if trainer_id in self._params_emitted:
            return
        self._params_emitted.add(trainer_id)

        # Extract LR-scheduler class name if a scheduler is configured.
        # Lightning exposes `trainer.lr_scheduler_configs` post-setup.
        lr_scheduler_class: Optional[str] = None
        try:
            configs = getattr(trainer, "lr_scheduler_configs", None) or []
            if configs:
                first = configs[0]
                scheduler = getattr(first, "scheduler", None)
                if scheduler is not None:
                    lr_scheduler_class = type(scheduler).__name__
        except Exception:
            logger.debug("autolog.lightning.lr_scheduler_probe_failed")

        params: Dict[str, str] = {
            f"trainer.{k}": _truncate_repr(v) for k, v in init_kwargs.items()
        }
        if lr_scheduler_class is not None:
            params["trainer.lr_scheduler_class"] = lr_scheduler_class

        async def event(run: "ExperimentRun") -> None:
            if params:
                await run.log_params(params)

        self._events.append(event)

    def _enqueue_metrics(
        self,
        metrics: Dict[str, float],
        *,
        step: Optional[int] = None,
    ) -> None:
        if not metrics:
            return
        snapshot = dict(metrics)  # copy — callback_metrics mutates

        async def event(run: "ExperimentRun") -> None:
            try:
                await run.log_metrics(snapshot, step=step)
            except Exception:
                logger.debug(
                    "autolog.lightning.metrics_emit_failed",
                    extra={"keys": sorted(snapshot.keys())[:5], "step": step},
                )

        self._events.append(event)

    def _enqueue_checkpoints(self, trainer: Any) -> None:
        if not (self._config.log_models if self._config else True):
            return

        # Paths surface only if Lightning's ModelCheckpoint is active.
        best_path: Optional[str] = None
        last_path: Optional[str] = None
        try:
            cp = getattr(trainer, "checkpoint_callback", None)
            if cp is not None:
                best_attr = getattr(cp, "best_model_path", "") or ""
                last_attr = getattr(cp, "last_model_path", "") or ""
                best_path = best_attr if best_attr else None
                last_path = last_attr if last_attr else None
        except Exception:
            logger.debug("autolog.lightning.checkpoint_probe_failed")

        async def event(run: "ExperimentRun") -> None:
            for name, path in (("best", best_path), ("last", last_path)):
                if not path:
                    continue
                if not os.path.exists(path):
                    logger.debug(
                        "autolog.lightning.checkpoint_missing",
                        extra={"name": name, "path": path},
                    )
                    continue
                try:
                    await run.log_artifact(
                        Path(path),
                        f"lightning.{name}_checkpoint.ckpt",
                        content_type="application/octet-stream",
                    )
                except Exception:
                    logger.exception(
                        "autolog.lightning.log_checkpoint_failed",
                        extra={"name": name, "path": path},
                    )

        self._events.append(event)


def _extract_callback_metrics(trainer: Any) -> Dict[str, float]:
    """Pull the live ``trainer.callback_metrics`` into a plain
    ``Dict[str, float]`` for emission.

    Lightning populates ``callback_metrics`` with torch tensors /
    MetricCollection entries. We coerce to float via ``.item()``
    (tensor) or ``float()`` (scalar) and drop entries that can't be
    coerced — a non-finite metric value would raise downstream in
    the runner's ``_validate_metric_value`` gate anyway.
    """
    raw = getattr(trainer, "callback_metrics", None) or {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        try:
            if hasattr(v, "item"):
                scalar = float(v.item())
            else:
                scalar = float(v)
        except Exception:
            continue
        # Drop NaN / Inf silently here — the runner would raise, and
        # raising from inside Lightning's callback-hook sync path
        # tears down the training run.
        import math  # noqa: PLC0415

        if not math.isfinite(scalar):
            continue
        out[str(k)] = scalar
    return out


def _extract_optimizer_lrs(trainer: Any) -> Dict[str, float]:
    """Snapshot ``lr-{i}`` from ``trainer.optimizers[i].param_groups[0]['lr']``.

    Per spec §3.1 row 1, LR-per-optimizer is a first-class signal.
    Lightning allows multiple optimizers; we emit one metric per.
    """
    optimizers = getattr(trainer, "optimizers", None) or []
    out: Dict[str, float] = {}
    for idx, opt in enumerate(optimizers):
        try:
            pg = opt.param_groups[0]
            out[f"lr-{idx}"] = float(pg["lr"])
        except Exception:
            logger.debug(
                "autolog.lightning.lr_probe_failed",
                extra={"optimizer_idx": idx},
            )
    return out


def _kailash_autolog_callback_base() -> Any:
    """Lazily resolve Lightning's ``Callback`` base class at first use.

    Deferred import so the module-level import of this file does NOT
    pull lightning into ``sys.modules`` — preserves the auto-detect
    path (§4.1).
    """
    try:
        from lightning.pytorch.callbacks import Callback  # noqa: PLC0415
    except ImportError:
        from pytorch_lightning.callbacks import Callback  # noqa: PLC0415
    return Callback


class _KailashAutologCallback:
    """Placeholder — real class builds dynamically at first attach.

    We defer constructing the real ``pl.Callback`` subclass until
    :meth:`LightningIntegration.attach` fires, because subclassing
    ``pl.Callback`` at module-import time would require
    ``lightning`` to be installed even for users who never use
    autolog. See :func:`_build_callback_class`.
    """

    def __new__(  # type: ignore[misc]
        cls,
        integ: "LightningIntegration",
        trainer_init_kwargs: Dict[str, Any],
    ) -> Any:
        real_cls = _build_callback_class()
        return real_cls(integ, trainer_init_kwargs)


def _build_callback_class() -> type:
    """Build the real ``pl.Callback`` subclass at first call.

    Cached on the module so repeat attaches reuse the class (attach /
    detach cycles don't rebuild it).
    """
    cached = getattr(_build_callback_class, "_cached", None)
    if cached is not None:
        return cached

    _Callback = _kailash_autolog_callback_base()

    class KailashAutologCallback(_Callback):
        """Lightning callback that buffers autolog events on the
        integration. Rank-0-gated per §3.3 — all emit paths short-
        circuit on non-main workers.

        All hooks are SYNC (Lightning's contract). They enqueue
        closures onto the integration's ``_events`` list; the
        integration's :meth:`flush` drains them async on CM exit.
        """

        def __init__(
            self,
            integ: "LightningIntegration",
            trainer_init_kwargs: Dict[str, Any],
        ) -> None:
            super().__init__()
            self._integ = integ
            self._trainer_init_kwargs = trainer_init_kwargs

        # Lightning hook — fires once per (trainer, stage). We emit
        # params on the first setup call (param emission is dedup'd
        # by trainer-id on the integration).
        def setup(self, trainer: Any, pl_module: Any, stage: str) -> None:
            if not is_main_process():
                return
            self._integ._enqueue_params(trainer, self._trainer_init_kwargs)

        def on_train_batch_end(
            self,
            trainer: Any,
            pl_module: Any,
            outputs: Any,
            batch: Any,
            batch_idx: int,
        ) -> None:
            if not is_main_process():
                return
            metrics = _extract_callback_metrics(trainer)
            metrics.update(_extract_optimizer_lrs(trainer))
            step = int(getattr(trainer, "global_step", 0))
            self._integ._enqueue_metrics(metrics, step=step)

        def on_train_epoch_end(self, trainer: Any, pl_module: Any) -> None:
            if not is_main_process():
                return
            metrics = _extract_callback_metrics(trainer)
            epoch = int(getattr(trainer, "current_epoch", 0))
            self._integ._enqueue_metrics(metrics, step=epoch)

        def on_validation_epoch_end(self, trainer: Any, pl_module: Any) -> None:
            if not is_main_process():
                return
            metrics = _extract_callback_metrics(trainer)
            epoch = int(getattr(trainer, "current_epoch", 0))
            self._integ._enqueue_metrics(metrics, step=epoch)

        def on_train_end(self, trainer: Any, pl_module: Any) -> None:
            if not is_main_process():
                return
            self._integ._enqueue_checkpoints(trainer)

    _build_callback_class._cached = KailashAutologCallback  # type: ignore[attr-defined]
    return KailashAutologCallback
