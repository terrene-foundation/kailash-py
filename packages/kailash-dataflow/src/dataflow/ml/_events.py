# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML-lifecycle event subscriber — ``on_train_start`` / ``on_train_end``.

kailash-ml publishes two training-lifecycle event types through the
DataFlow event bus:

* ``kailash_ml.train.start`` — emitted when a training run begins.
  Payload carries the :class:`TrainingContext` (``run_id``,
  ``tenant_id``, ``dataset_hash``, ``actor_id``) plus operational
  metadata (model name, engine, start timestamp).
* ``kailash_ml.train.end``   — emitted when a training run completes.
  Payload carries the same ``TrainingContext`` plus outcome
  (``status``, ``duration_seconds``, optional ``error``).

The subscriber lives in DataFlow so every DataFlow consumer gets the
hook surface automatically — kailash-ml does not ship a second event
bus. Events share the same ``DomainEvent`` shape as DataFlow's write
events (per ``rules/event-payload-classification.md`` § 1): subscribers
iterate ``event.event_type`` and ``event.payload``.

Event-payload classification: ``TrainingContext`` fields are
intentionally safe to emit.

* ``run_id`` and ``actor_id`` are opaque identifiers.
* ``tenant_id`` is operational metadata (per ``rules/tenant-isolation.md``
  § 4 — metric labels may carry it, bounded).
* ``dataset_hash`` is already a ``sha256:<64hex>`` fingerprint from
  :func:`dataflow.ml.hash`, not a raw PK value.

No subscriber path ever echoes a classified PK back to the bus.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from dataflow.ml._context import TrainingContext

logger = logging.getLogger(__name__)

__all__ = [
    "ML_TRAIN_START_EVENT",
    "ML_TRAIN_END_EVENT",
    "emit_train_start",
    "emit_train_end",
    "on_train_start",
    "on_train_end",
]


ML_TRAIN_START_EVENT = "kailash_ml.train.start"
ML_TRAIN_END_EVENT = "kailash_ml.train.end"


def _require_event_bus(db: "Any") -> "Any":
    """Return ``db.event_bus`` or raise a descriptive error."""
    bus = getattr(db, "event_bus", None)
    if bus is None:
        raise RuntimeError(
            "DataFlow instance has no event_bus — "
            "call db.initialize() or ensure the Core SDK EventBus backend "
            "is installed."
        )
    return bus


def _record_id_fingerprint(context: TrainingContext) -> str:
    """Return a record_id suitable for event payloads.

    We use the ``dataset_hash`` as the payload's record_id because it
    is already a stable fingerprint. The routing goes through
    :func:`dataflow.classification.event_payload.format_record_id_for_event`
    in :func:`emit_train_start` / :func:`emit_train_end` to keep the
    event-payload classification path uniform with DataFlow's write-event
    path (per ``rules/event-payload-classification.md`` § 1).
    """
    return context.dataset_hash


def _build_train_payload(
    *,
    db: "Any",
    event_type: str,
    context: TrainingContext,
    extra: "Optional[dict]" = None,
) -> dict:
    """Construct a safe ``DomainEvent.payload`` for ML train events.

    Every caller path routes through here so the payload shape is
    identical across start / end, and so the classification path lives
    in one place.
    """
    from dataflow.classification.event_payload import format_record_id_for_event

    policy = getattr(db, "_classification_policy", None)
    safe_record_id = format_record_id_for_event(
        policy=policy,
        model_name="TrainingRun",
        record_id=_record_id_fingerprint(context),
    )

    payload = {
        "event": event_type,
        "run_id": context.run_id,
        "tenant_id": context.tenant_id,
        "dataset_hash": context.dataset_hash,
        "actor_id": context.actor_id,
        "record_id": safe_record_id,
    }
    if extra:
        # Shallow-merge caller-supplied operational metadata. Caller is
        # responsible for ensuring `extra` does NOT contain classified
        # PKs or raw classified values (per
        # `rules/event-payload-classification.md` MUST NOT).
        payload.update(extra)
    return payload


def emit_train_start(
    db: "Any",
    context: TrainingContext,
    *,
    model_name: Optional[str] = None,
    engine: Optional[str] = None,
) -> None:
    """Emit a ``kailash_ml.train.start`` event on ``db.event_bus``.

    kailash-ml training engines call this at the start of every run so
    subscribers (MLflow bridge, dashboard, audit trail) can record the
    run.

    Args:
        db: DataFlow instance.
        context: Immutable training context (provenance envelope).
        model_name: Optional name of the model being trained.
        engine: Optional training engine identifier (``"sklearn"``,
            ``"lightgbm"``, ``"pytorch-lightning"``, etc.).
    """
    bus = _require_event_bus(db)

    try:
        from kailash.middleware.communication.domain_event import DomainEvent
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "kailash.middleware.communication.domain_event is unavailable — "
            "ensure kailash>=2.8.9 is installed."
        ) from exc

    extra = {}
    if model_name is not None:
        extra["model_name"] = model_name
    if engine is not None:
        extra["engine"] = engine

    payload = _build_train_payload(
        db=db, event_type=ML_TRAIN_START_EVENT, context=context, extra=extra
    )

    logger.info(
        "dataflow.ml.train.start",
        extra={
            "run_id": context.run_id,
            "tenant_id": context.tenant_id,
            "model_name": model_name,
            "engine": engine,
            # dataset_hash is already a fingerprint, safe to log
            "dataset_hash": context.dataset_hash,
        },
    )

    try:
        bus.publish(DomainEvent(event_type=ML_TRAIN_START_EVENT, payload=payload))
    except Exception:
        # Fire-and-forget: event emission MUST NOT break a training run.
        # Still emit a WARN so operators see the bus failure.
        logger.warning(
            "dataflow.ml.train.start.publish_failed",
            extra={"run_id": context.run_id},
            exc_info=True,
        )


def emit_train_end(
    db: "Any",
    context: TrainingContext,
    *,
    status: str,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Emit a ``kailash_ml.train.end`` event on ``db.event_bus``.

    Args:
        db: DataFlow instance.
        context: Immutable training context.
        status: ``"success"`` / ``"failure"`` / ``"cancelled"``.
        duration_seconds: Wall-clock duration of the run.
        error: Error message if ``status="failure"``. Caller is
            responsible for ensuring error messages contain no
            classified values (per ``rules/security.md`` §
            "Multi-Site Kwarg Plumbing" — sanitize before emitting).
    """
    bus = _require_event_bus(db)

    try:
        from kailash.middleware.communication.domain_event import DomainEvent
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "kailash.middleware.communication.domain_event is unavailable — "
            "ensure kailash>=2.8.9 is installed."
        ) from exc

    extra = {"status": status}
    if duration_seconds is not None:
        extra["duration_seconds"] = duration_seconds
    if error is not None:
        extra["error"] = error

    payload = _build_train_payload(
        db=db, event_type=ML_TRAIN_END_EVENT, context=context, extra=extra
    )

    if status == "success":
        log_level = logger.info
    else:
        log_level = logger.warning

    log_level(
        "dataflow.ml.train.end",
        extra={
            "run_id": context.run_id,
            "tenant_id": context.tenant_id,
            "status": status,
            "duration_seconds": duration_seconds,
            "dataset_hash": context.dataset_hash,
        },
    )

    try:
        bus.publish(DomainEvent(event_type=ML_TRAIN_END_EVENT, payload=payload))
    except Exception:
        logger.warning(
            "dataflow.ml.train.end.publish_failed",
            extra={"run_id": context.run_id},
            exc_info=True,
        )


def on_train_start(db: "Any", handler: "Callable[[Any], None]") -> List[str]:
    """Subscribe ``handler`` to ``kailash_ml.train.start`` events.

    Args:
        db: DataFlow instance (must have ``event_bus``).
        handler: Callable invoked with a ``DomainEvent`` argument.

    Returns:
        ``[subscription_id]`` — single-element list matching the shape
        of ``DataFlow.on_model_change`` so callers can batch subscribe
        / unsubscribe uniformly.
    """
    bus = _require_event_bus(db)
    sub_id = bus.subscribe(ML_TRAIN_START_EVENT, handler)
    return [sub_id]


def on_train_end(db: "Any", handler: "Callable[[Any], None]") -> List[str]:
    """Subscribe ``handler`` to ``kailash_ml.train.end`` events.

    See :func:`on_train_start` for the return shape.
    """
    bus = _require_event_bus(db)
    sub_id = bus.subscribe(ML_TRAIN_END_EVENT, handler)
    return [sub_id]
