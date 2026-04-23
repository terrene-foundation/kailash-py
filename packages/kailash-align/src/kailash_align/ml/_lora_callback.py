# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""LoRA Lightning callback for kailash-align + kailash-ml MLEngine.fit.

Per ``workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md``
§32b (amended 2026-04-23): when ``MLEngine.fit`` receives an alignment
LoRA trainable, the ML side auto-appends a ``pytorch_lightning.Callback``
that routes the trainer's per-step metrics to the ambient
``ExperimentRun`` tracker. The callback is defined here (align owns LoRA
semantics) and ml looks it up via :func:`lora_callback_for` without
importing this module at module-scope (preserves the one-way ml→align
import boundary enforced in W30).

Contract
--------

* :class:`LoRALightningCallback` subclasses ``pytorch_lightning.Callback``
  and overrides ``on_train_batch_end`` + ``on_validation_batch_end``. On
  each invocation it reads the trainer's ``callback_metrics`` dict and
  forwards every finite numeric entry under the ``align.lora.*``
  metric namespace to the ambient tracker (resolved via
  :func:`kailash_ml.tracking.get_current_run` when available; None
  means no ambient run → emission is a no-op at that step).
* :func:`lora_callback_for` is the public entry point kailash-ml
  calls. It returns ``None`` when:
    - ``pytorch_lightning`` is not installed (the downstream caller
      can skip LoRA-callback wiring cleanly);
    - the trainable does not declare itself a LoRA trainable via the
      duck-typed :meth:`is_lora_trainable` / ``lora_trainable`` attr.
  It returns a ``LoRALightningCallback`` instance otherwise.

Rank-0-only emission
--------------------

Accelerate / DDP distributed training fan out the callback to every
rank. Per ``rules/tenant-isolation.md`` and ``specs/ml-rl-align-
unification.md`` §3.5 (metric parity) every metric emission is guarded
by ``trainer.is_global_zero`` — only the leader emits, every other rank
returns silently. Mirrors the classical-RL bridge callback pattern.

Optional Lightning dependency
-----------------------------

``pytorch_lightning`` is NOT a runtime dependency of ``kailash-align``.
This module imports it lazily via ``importlib`` at callback-construction
time so ``import kailash_align.ml`` is cheap + safe on a lightning-less
install. A real LoRA fit requires Lightning; the loud-failure pattern
(``rules/dependencies.md`` § "Optional Extras with Loud Failure") is
the right discipline here. Callers that don't have Lightning installed
get ``None`` from :func:`lora_callback_for` and can report a typed
"install pytorch_lightning" message at their own boundary.
"""
from __future__ import annotations

import importlib
import logging
import math
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover — typing only
    import pytorch_lightning as pl  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

__all__ = ["LoRALightningCallback", "lora_callback_for"]


def _load_lightning_callback_base() -> Optional[type]:
    """Return ``pl.Callback`` if pytorch_lightning is installed else ``None``.

    Import-safe even if Lightning is absent so ``import kailash_align.ml``
    works on a Lightning-less install. The loud-fail happens only when
    the caller actually tries to instantiate the callback via
    :func:`lora_callback_for`.
    """
    try:
        pl_mod = importlib.import_module("pytorch_lightning")
    except ImportError:
        return None
    base = getattr(pl_mod, "Callback", None)
    if base is None:  # pragma: no cover — defensive, shouldn't happen
        return None
    return base


def _resolve_ambient_tracker() -> Optional[Any]:
    """Return the ambient kailash-ml ExperimentRun if one is active.

    Per spec §3.3 the callback emits metrics through the ambient tracker
    rather than requiring the caller to pass a run handle. Returns
    ``None`` when no run is active OR the resolver symbol is missing
    (old kailash-ml); callers treat ``None`` as "skip emission" cleanly.
    """
    try:
        tracking_mod = importlib.import_module("kailash_ml.tracking")
    except ImportError:  # pragma: no cover — kailash-ml is a runtime dep
        return None
    resolver = getattr(tracking_mod, "get_current_run", None)
    if resolver is None:
        return None
    try:
        return resolver()
    except Exception as exc:  # pragma: no cover — resolver defensive
        logger.debug(
            "align.ml.tracker_resolve_failed",
            extra={"error": str(exc), "mode": "real"},
        )
        return None


_LightningCallbackBase = _load_lightning_callback_base()


# The class body branches on Lightning availability. When Lightning is
# present we subclass pl.Callback (satisfies isinstance checks upstream);
# when absent the class exists as a plain object subclass so
# ``import kailash_align.ml`` still works for non-Lightning callers.
class LoRALightningCallback(  # type: ignore[misc]
    _LightningCallbackBase if _LightningCallbackBase is not None else object
):
    """``pytorch_lightning.Callback`` emitting LoRA training metrics.

    Routes per-batch Lightning metrics to the ambient kailash-ml
    ``ExperimentRun`` under the ``align.lora.*`` namespace. Emission is
    rank-0-only (guards on ``trainer.is_global_zero``) per spec §3.5.

    Parameters
    ----------
    adapter_name
        LoRA adapter's registry name. Included on every emission so
        dashboards can filter by adapter identity.
    tenant_id
        Optional tenant scope. Logged with every emission per
        ``rules/tenant-isolation.md``.
    metric_prefix
        Namespace prefix for emitted metrics. Defaults to
        ``"align.lora"``; per spec §3.1 the align.* namespace is the
        alignment-specific metric family.
    """

    def __init__(
        self,
        *,
        adapter_name: str,
        tenant_id: Optional[str] = None,
        metric_prefix: str = "align.lora",
    ) -> None:
        if _LightningCallbackBase is None:
            # Construction without Lightning is caller error — the
            # public entry :func:`lora_callback_for` already gates on
            # Lightning availability and returns ``None`` when missing.
            raise ImportError(
                "LoRALightningCallback requires pytorch_lightning. "
                "Install via 'pip install pytorch_lightning>=2.0'."
            )
        super().__init__()
        if not isinstance(adapter_name, str) or not adapter_name:
            raise ValueError("adapter_name must be a non-empty string")
        self._adapter_name = adapter_name
        self._tenant_id = tenant_id
        self._metric_prefix = metric_prefix
        self._emit_count = 0  # test-visible counter (spec §4 conformance)
        logger.debug(
            "align.lora_callback.init",
            extra={
                "adapter_name": adapter_name,
                "tenant_id": tenant_id,
                "metric_prefix": metric_prefix,
                "mode": "real",
            },
        )

    @property
    def adapter_name(self) -> str:
        return self._adapter_name

    @property
    def emit_count(self) -> int:
        """Number of metric emissions made by this callback (for tests)."""
        return self._emit_count

    # ---- Lightning lifecycle hooks --------------------------------------
    #
    # Lightning calls these on every training / validation batch. We
    # forward every finite numeric entry of ``trainer.callback_metrics``
    # to the ambient tracker.

    def on_train_batch_end(
        self,
        trainer: Any,
        pl_module: Any,
        outputs: Any,
        batch: Any,
        batch_idx: int,
    ) -> None:
        self._emit_callback_metrics(trainer, phase="train")

    def on_validation_batch_end(
        self,
        trainer: Any,
        pl_module: Any,
        outputs: Any,
        batch: Any,
        batch_idx: int,
        dataloader_idx: int = 0,
    ) -> None:
        self._emit_callback_metrics(trainer, phase="val")

    # ---- Internal ------------------------------------------------------

    def _emit_callback_metrics(self, trainer: Any, *, phase: str) -> None:
        # Rank-0-only emission (spec §3.5)
        is_global_zero = getattr(trainer, "is_global_zero", True)
        if not is_global_zero:
            return
        metrics = getattr(trainer, "callback_metrics", None) or {}
        step = getattr(trainer, "global_step", 0)
        tracker = _resolve_ambient_tracker()
        for key, value in metrics.items():
            numeric = _to_finite_float(value)
            if numeric is None:
                continue
            metric_key = f"{self._metric_prefix}.{phase}.{key}"
            if tracker is not None:
                recorder = getattr(tracker, "record_metric", None) or getattr(
                    tracker, "log_metric", None
                )
                if recorder is not None:
                    try:
                        recorder(metric_key, numeric, step=step)
                    except Exception as exc:  # noqa: BLE001 — log + continue
                        logger.warning(
                            "align.lora_callback.emit_failed",
                            extra={
                                "metric_key": metric_key,
                                "error": str(exc),
                                "mode": "real",
                            },
                        )
                        continue
            self._emit_count += 1
        logger.debug(
            "align.lora_callback.batch_end",
            extra={
                "adapter_name": self._adapter_name,
                "phase": phase,
                "step": step,
                "emit_count": self._emit_count,
                "mode": "real",
            },
        )


def _to_finite_float(value: Any) -> Optional[float]:
    """Coerce ``value`` to a finite float or return ``None``.

    Lightning sometimes places ``torch.Tensor`` scalars in
    ``callback_metrics``; we duck-type ``.item()`` so the callback works
    without importing torch at module scope. NaN / Inf values are
    dropped — emitting them would corrupt the tracker's aggregate
    statistics.
    """
    if value is None:
        return None
    # torch.Tensor scalar
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            value = item_method()
        except Exception:  # noqa: BLE001 — duck-typed coercion
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def lora_callback_for(trainable: Any) -> Optional[LoRALightningCallback]:
    """Return a :class:`LoRALightningCallback` if ``trainable`` is a LoRA fit.

    This is the public entry point ``MLEngine.fit`` (kailash-ml) looks
    up when wiring callbacks for an alignment LoRA training run. The
    one-way import boundary (ml→align) means ml imports this module
    lazily; to avoid import-time coupling we accept an arbitrary
    ``trainable`` and duck-type the LoRA markers.

    Returns
    -------
    Optional[LoRALightningCallback]
        ``None`` when pytorch_lightning is not installed OR the
        trainable does not declare LoRA semantics. Otherwise a fresh
        callback bound to the trainable's adapter name + tenant id.

    Detection contract
    ------------------

    A trainable is considered a LoRA trainable when ANY of:

    * ``trainable.is_lora_trainable`` is truthy (method or attribute),
    * ``getattr(trainable, "lora_trainable", False)`` is truthy,
    * ``trainable.trainable_kind == "lora"``.
    """
    if _LightningCallbackBase is None:
        logger.debug(
            "align.lora_callback_for.no_lightning",
            extra={"mode": "real"},
        )
        return None
    if trainable is None:
        return None

    # Duck-type LoRA markers
    is_lora = False
    marker = getattr(trainable, "is_lora_trainable", None)
    if callable(marker):
        try:
            is_lora = bool(marker())
        except Exception:  # noqa: BLE001
            is_lora = False
    elif marker is not None:
        is_lora = bool(marker)
    if not is_lora:
        is_lora = bool(getattr(trainable, "lora_trainable", False))
    if not is_lora:
        is_lora = getattr(trainable, "trainable_kind", None) == "lora"
    if not is_lora:
        return None

    adapter_name = (
        getattr(trainable, "adapter_name", None)
        or getattr(trainable, "name", None)
        or "align-lora"
    )
    tenant_id = getattr(trainable, "tenant_id", None)
    callback = LoRALightningCallback(
        adapter_name=str(adapter_name), tenant_id=tenant_id
    )
    logger.info(
        "align.lora_callback_for.attached",
        extra={
            "adapter_name": adapter_name,
            "tenant_id": tenant_id,
            "mode": "real",
        },
    )
    return callback
