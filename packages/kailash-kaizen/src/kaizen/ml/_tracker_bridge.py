# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Ambient-tracker bridge — Kaizen diagnostics ↔ ``km.track()``.

Per ``specs/kaizen-ml-integration.md`` §1.1 items 1–2:

    1. Every Kaizen diagnostic adapter (``AgentDiagnostics``,
       ``LLMDiagnostics``, ``InterpretabilityDiagnostics``) accepts an
       optional ``tracker=Optional[ExperimentRun]`` kwarg.
    2. When an ambient tracker is present, every ``record_*`` / ``track_*``
       method MUST auto-emit to the tracker via ``log_metric`` /
       ``log_param`` / ``log_artifact`` as appropriate. There is NO
       opt-in flag — if a tracker is there, metrics flow.

The tracker's logging surface is a duck-typed contract here — Kaizen
does NOT hard-import ``kailash_ml.tracking.ExperimentRun`` at module
scope, because:

  a) ``rules/dependencies.md`` § Declared = Imported — kailash-ml is NOT
     a hard dependency of kailash-kaizen (per the framework hierarchy,
     Kaizen is peer to ML, not downstream). A module-scope import would
     violate the declared-imported contract.
  b) ``rules/independence.md`` — the tracker protocol is an Optional
     integration; failure to install kailash-ml MUST NOT break Kaizen.
  c) Spec §2.1 types the kwarg as ``Optional[ExperimentRun]`` for the
     user-facing annotation; runtime behavior uses ``log_metric`` /
     ``log_param`` / ``log_artifact`` attribute presence, so any class
     satisfying the contract (e.g. a test double) works.

The ``get_current_run`` ambient lookup is lazy: agents may construct
``AgentDiagnostics`` BEFORE entering ``async with km.track(...)`` and
the same adapter should bind to whichever run is active at emission
time. Caching the ambient run at construction time would bind to the
parent of a sweep, not the trial actually running — the failure mode
``specs/kaizen-ml-integration.md §2.2`` explicitly warns against.

Rank-0-only emission (spec §2.5, approved-decisions.md Decision 4):
distributed-training adapters emit only when
``torch.distributed.get_rank() == 0``. In a non-distributed context the
rule trivially holds. This module exposes ``is_emit_rank_0()`` so every
auto-emit call site applies the guard uniformly.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Optional

__all__ = [
    "resolve_active_tracker",
    "is_emit_rank_0",
    "emit_metric",
    "emit_param",
    "emit_artifact",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ambient tracker resolution
# ---------------------------------------------------------------------------


def _try_import_get_current_run() -> Optional[Any]:
    """Lazy import of ``kailash_ml.tracking.get_current_run``.

    Returns ``None`` when kailash-ml is not installed or does not yet
    expose the helper. Per ``rules/dependencies.md`` exception for
    optional extras: the import is inside a function body, returns
    ``None`` on ImportError, and the CALLER (every ``record_*``
    auto-emit site) fails loudly only when the user explicitly passed
    a tracker — silent degradation to ``None`` on missing-extra is
    CORRECT here because ``tracker=None`` is a valid contract state
    (spec §3.4: no tracker → skip emission silently at DEBUG).
    """
    try:
        from kailash_ml.tracking import get_current_run  # type: ignore[import]

        return get_current_run
    except ImportError:
        return None
    except AttributeError:  # kailash-ml present but pre-registry
        return None


def resolve_active_tracker(explicit: Optional[Any]) -> Optional[Any]:
    """Return the tracker adapters should emit to.

    Resolution order (spec §2.2):
        1. ``explicit`` — the ``tracker=`` kwarg passed at construction
           time. Wins over ambient.
        2. Ambient — ``kailash_ml.tracking.get_current_run()`` when
           installed.
        3. ``None`` — no tracker; adapters skip emission silently
           (spec §3.4 — BLOCKED to WARN on missing tracker).

    This resolver is called at EMISSION time, not at construction,
    so a single adapter instance can participate in multiple sequential
    runs (sweep parent + trial children) with the correct binding each
    time.
    """
    if explicit is not None:
        return explicit

    get_current_run = _try_import_get_current_run()
    if get_current_run is None:
        return None
    try:
        return get_current_run()
    except Exception as exc:  # defensive: never let ambient lookup crash emission
        logger.debug(
            "kaizen.ml.tracker.ambient_lookup_failed",
            extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )
        return None


# ---------------------------------------------------------------------------
# Rank-0 gate (distributed-training parity with DLDiagnostics)
# ---------------------------------------------------------------------------


def is_emit_rank_0() -> bool:
    """Return ``True`` when the current process is rank 0 (or non-distributed).

    Per spec §2.5 + approved-decisions.md Decision 4: autolog +
    ``DLDiagnostics`` emit ONLY when ``torch.distributed.get_rank() == 0``.
    LLMDiagnostics / AgentDiagnostics / InterpretabilityDiagnostics
    inherit the same rule. Non-distributed context = trivially rank 0 =
    always emits.

    The torch import is guarded so kailash-kaizen remains usable without
    a torch install — the helper defaults to ``True`` when torch is not
    importable, which is the correct single-node behavior.
    """
    try:
        import torch  # type: ignore[import]

        if not torch.distributed.is_available():
            return True
        if not torch.distributed.is_initialized():
            return True
        return torch.distributed.get_rank() == 0
    except Exception:
        # torch not installed, or distributed module not available —
        # treat as non-distributed (rank 0) and emit.
        return True


# ---------------------------------------------------------------------------
# Auto-emission helpers — invoked from every record_* / track_* method
# ---------------------------------------------------------------------------


def _run_coro(coro: Any) -> None:
    """Execute a coroutine from a sync auto-emit call site.

    ``ExperimentRun.log_metric`` is async. Auto-emission happens inside
    synchronous ``record_*`` methods (AgentDiagnostics.record,
    LLMDiagnostics judgement callbacks), so we need a sync bridge.

    If an event loop is running in the current thread, schedule the
    coroutine as a background task (fire-and-forget — emission loss is
    ACCEPTED per spec §3.4: tracker is optional; metrics flow best-
    effort). If no loop is running, run it via ``asyncio.run``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to run synchronously.
        try:
            asyncio.run(coro)
        except Exception as exc:
            logger.debug(
                "kaizen.ml.tracker.emit_failed",
                extra={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "mode": "real",
                },
            )
        return

    # Running loop — fire-and-forget task.
    try:
        task = loop.create_task(coro)
        # Silence "never awaited" warning on task reference drop;
        # exceptions surface through the loop's exception handler.
        task.add_done_callback(_log_emit_failure)
    except Exception as exc:
        logger.debug(
            "kaizen.ml.tracker.schedule_failed",
            extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )


def _log_emit_failure(task: Any) -> None:
    exc = task.exception()
    if exc is not None:
        logger.debug(
            "kaizen.ml.tracker.emit_background_failed",
            extra={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )


def emit_metric(
    tracker: Optional[Any],
    key: str,
    value: float,
    *,
    step: Optional[int] = None,
) -> None:
    """Emit a scalar metric to ``tracker.log_metric`` (best-effort).

    Silent no-op when ``tracker`` is ``None`` (spec §3.4). DEBUG log
    when a tracker is present but lacks ``log_metric`` — duck-typed
    callers (e.g. test doubles) may satisfy only a subset of the
    protocol; we don't force them to implement the full surface.

    NaN / Inf metric values are dropped at DEBUG (kailash-ml's
    ``log_metric`` rejects non-finite values; we apply the same gate
    here so the adapter doesn't raise when the underlying agent emits
    a ``float('nan')`` latency from a crashed call).
    """
    if tracker is None or not is_emit_rank_0():
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        logger.debug(
            "kaizen.ml.tracker.metric_skip_type",
            extra={"key": key, "value_type": type(value).__name__, "mode": "real"},
        )
        return
    if not math.isfinite(float(value)):
        logger.debug(
            "kaizen.ml.tracker.metric_skip_nonfinite",
            extra={"key": key, "mode": "real"},
        )
        return

    log_metric = getattr(tracker, "log_metric", None)
    if log_metric is None:
        logger.debug(
            "kaizen.ml.tracker.no_log_metric",
            extra={"key": key, "mode": "real"},
        )
        return

    try:
        result = log_metric(key, float(value), step=step)
        if asyncio.iscoroutine(result):
            _run_coro(result)
    except Exception as exc:
        logger.debug(
            "kaizen.ml.tracker.log_metric_failed",
            extra={
                "key": key,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )


def emit_param(tracker: Optional[Any], key: str, value: Any) -> None:
    """Emit a single param to ``tracker.log_param`` (best-effort)."""
    if tracker is None or not is_emit_rank_0():
        return
    log_param = getattr(tracker, "log_param", None)
    if log_param is None:
        logger.debug(
            "kaizen.ml.tracker.no_log_param",
            extra={"key": key, "mode": "real"},
        )
        return
    try:
        result = log_param(key, value)
        if asyncio.iscoroutine(result):
            _run_coro(result)
    except Exception as exc:
        logger.debug(
            "kaizen.ml.tracker.log_param_failed",
            extra={
                "key": key,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )


def emit_artifact(
    tracker: Optional[Any],
    path: str,
    *,
    name: Optional[str] = None,
) -> None:
    """Emit an artifact file reference to ``tracker.log_artifact`` (best-effort)."""
    if tracker is None or not is_emit_rank_0():
        return
    log_artifact = getattr(tracker, "log_artifact", None)
    if log_artifact is None:
        logger.debug(
            "kaizen.ml.tracker.no_log_artifact",
            extra={"path": path, "mode": "real"},
        )
        return
    try:
        result = log_artifact(path, artifact_path=name) if name else log_artifact(path)
        if asyncio.iscoroutine(result):
            _run_coro(result)
    except Exception as exc:
        logger.debug(
            "kaizen.ml.tracker.log_artifact_failed",
            extra={
                "path": path,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "mode": "real",
            },
        )
