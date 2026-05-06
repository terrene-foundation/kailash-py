# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Durable execution primitives for LocalRuntime / AsyncLocalRuntime.

This module provides the building blocks that wire per-node checkpoint
emission and history-event subscription into the runtime's hot path
(``_execute_workflow_with_tracking`` at ``local.py:2505``):

* :class:`NodeCompletionEvent` — the canonical per-node event. Subscribers
  registered via ``runtime.on_node_complete(callback)`` receive one of
  these per node completion.
* :class:`WorkflowShapeDriftError` — raised when a caller resumes with an
  ``idempotency_key`` whose persisted checkpoint was captured against a
  different workflow fingerprint. Same structural-confirmation pattern as
  ``git reset --hard`` / ``force_drop`` / ``force_downgrade``: refuse by
  default, require ``force_resume_with_drift=True`` to override.
* :class:`NodeCompletionHookRegistry` — lightweight subscriber registry
  used by both LocalRuntime and AsyncLocalRuntime. Multi-subscriber
  dispatch supported; sync and async callbacks are both honored.
* :func:`compute_workflow_fingerprint` — deterministic SHA-256 over the
  workflow's node IDs + edges + node types, used to detect shape drift
  between a saved checkpoint and a resume call.
* :func:`build_checkpoint_key` — deterministic hash of
  ``(workflow.fingerprint, idempotency_key, parameters)`` per architecture
  plan §6 risk register. Stable across processes; safe as a primary key.
* :func:`_redact_event_for_persistence` — shared classification-aware
  redaction helper. Both this module's checkpoint persistence path AND the
  W2 history store path MUST route through this helper before persisting
  any payload that may carry classified PKs or field names. Per
  ``rules/event-payload-classification.md`` MUST Rules 1–3 and the
  cross-cutting invariant 3.1 in
  ``workspaces/runtime-integration-trio/01-analysis/04-cross-cutting-architecture.md``.

Per ``rules/specs-authority.md`` Rule 5 the spec describing this surface
(``specs/core-runtime.md``) lands AFTER the code.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple, Union

logger = logging.getLogger(__name__)

__all__ = [
    "NodeCompletionEvent",
    "NodeCompletionCallback",
    "NodeCompletionHookRegistry",
    "WorkflowShapeDriftError",
    "compute_workflow_fingerprint",
    "build_checkpoint_key",
    "redact_event_for_persistence",
    "encode_checkpoint_payload",
    "decode_checkpoint_payload",
    "check_shape_drift_or_raise",
    "resolve_tenant_id",
]


# ---------------------------------------------------------------------------
# Public dataclasses + exceptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeCompletionEvent:
    """A per-node completion event emitted by the runtime hot path.

    This is the canonical event shape that W2 (history store) and any
    other subscriber (metrics, audit, replication) consume. The event is
    frozen so subscribers cannot accidentally mutate it across handlers.

    Attributes
    ----------
    run_id:
        The runtime-assigned execution ID. ``None`` only when the runtime
        ran without a ``task_manager`` AND the AsyncLocalRuntime path
        skipped the wall-clock-derived ID — which is rare and always
        recoverable from ``idempotency_key`` if present.
    workflow_id:
        The workflow's stable ID (``Workflow.workflow_id``).
    workflow_fingerprint:
        SHA-256 hex digest of the workflow's structural shape (node IDs +
        edges + node types). Same fingerprint is used by
        :func:`build_checkpoint_key`. See :func:`compute_workflow_fingerprint`.
    node_id:
        The completed node's ID.
    node_type:
        The node's class name (``node_instance.__class__.__name__``).
    outputs:
        The node's output dict (already classification-redacted by the
        persistence path before being handed to subscribers — see
        :func:`redact_event_for_persistence`). Subscribers MUST NOT assume
        the raw output is present.
    started_at:
        UTC timestamp when the node started executing.
    ended_at:
        UTC timestamp when the node completed (success or recorded error).
    duration_ms:
        ``(ended_at - started_at)`` in milliseconds, rounded to int.
    tenant_id:
        Tenant scope from the runtime context. ``None`` when the runtime
        is single-tenant. History/checkpoint rows MUST partition on this
        per ``rules/tenant-isolation.md`` MUST Rule 5.
    idempotency_key:
        The caller-supplied resume key, if any.
    error:
        ``None`` on success; a string repr of the exception on failure.
        Subscribers see the event whether the node succeeded or failed,
        because both states are part of the durable history.
    metadata:
        Free-form dict for cross-cutting context (correlation IDs, agent
        IDs, classification policy snapshot). Already redacted.
    """

    run_id: Optional[str]
    workflow_id: str
    workflow_fingerprint: str
    node_id: str
    node_type: str
    outputs: Mapping[str, Any]
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    tenant_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    error: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict (per EATP rule)."""
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_fingerprint": self.workflow_fingerprint,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "outputs": dict(self.outputs),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "duration_ms": self.duration_ms,
            "tenant_id": self.tenant_id,
            "idempotency_key": self.idempotency_key,
            "error": self.error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NodeCompletionEvent":
        """Reconstruct from a dict produced by :meth:`to_dict`."""
        return cls(
            run_id=data.get("run_id"),
            workflow_id=data["workflow_id"],
            workflow_fingerprint=data["workflow_fingerprint"],
            node_id=data["node_id"],
            node_type=data["node_type"],
            outputs=dict(data.get("outputs", {})),
            started_at=_parse_iso(data["started_at"]),
            ended_at=_parse_iso(data["ended_at"]),
            duration_ms=int(data["duration_ms"]),
            tenant_id=data.get("tenant_id"),
            idempotency_key=data.get("idempotency_key"),
            error=data.get("error"),
            metadata=dict(data.get("metadata", {})),
        )


# A subscriber callback. Both sync (returns ``None``) and coroutine forms
# are supported — :meth:`NodeCompletionHookRegistry.dispatch` awaits the
# coroutine when one is returned.
NodeCompletionCallback = Callable[[NodeCompletionEvent], Union[None, Awaitable[None]]]


class WorkflowShapeDriftError(RuntimeError):
    """Raised when an idempotency-key resume targets a different workflow.

    The runtime persisted a checkpoint under ``idempotency_key=K`` for
    a workflow whose structural fingerprint was ``F1``. The caller is
    now resuming under the same ``idempotency_key=K`` but supplying a
    workflow whose fingerprint is ``F2 != F1``. The completed-node
    outputs in the checkpoint were produced by the OLD shape — replaying
    them under the new shape can corrupt downstream state and is the
    "fake transaction" failure mode class flagged by
    ``rules/zero-tolerance.md`` Rule 2.

    The default disposition is to refuse. Callers who explicitly want to
    discard the prior checkpoint and start fresh MUST pass
    ``force_resume_with_drift=True``. Same structural-confirmation pattern
    as ``git reset --hard`` (must verify clean tree) and
    ``MigrationManager.apply_downgrade`` (must pass ``force_downgrade=True``).
    """

    def __init__(
        self,
        idempotency_key: str,
        stored_fingerprint: str,
        current_fingerprint: str,
    ) -> None:
        self.idempotency_key = idempotency_key
        self.stored_fingerprint = stored_fingerprint
        self.current_fingerprint = current_fingerprint
        super().__init__(
            f"Resume refused — idempotency_key={idempotency_key!r} matches a "
            f"checkpoint captured against a different workflow shape "
            f"(stored fingerprint={stored_fingerprint[:12]}…, current "
            f"fingerprint={current_fingerprint[:12]}…). The cached node "
            "outputs were produced by the prior shape; replaying them under "
            "the new shape can corrupt downstream state. Pass "
            "force_resume_with_drift=True to discard the prior checkpoint "
            "and start fresh, OR change the idempotency_key to a fresh "
            "value to keep the prior checkpoint intact."
        )


# ---------------------------------------------------------------------------
# Helpers — fingerprint + checkpoint key + ISO parse
# ---------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime:
    """Parse an ISO-8601 string back to a tz-aware datetime."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError(
            f"NodeCompletionEvent timestamp expected str or datetime, got "
            f"{type(value).__name__}"
        )
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def compute_workflow_fingerprint(workflow: Any) -> str:
    """Deterministic SHA-256 over a workflow's structural shape.

    The fingerprint covers:

    * sorted node IDs
    * sorted (source, target) edge tuples
    * each node's class name (the type, not the config — config drift is
      handled by the parameters channel of :func:`build_checkpoint_key`)

    Node config / parameter values are NOT included — those drift via the
    ``parameters`` argument of :func:`build_checkpoint_key`. Including
    config here would make every parameter override invalidate every
    checkpoint, defeating the purpose of resume.

    Returns the hex digest as a string.
    """
    if workflow is None:
        raise ValueError(
            "compute_workflow_fingerprint(): workflow is None. Pass the "
            "Workflow instance returned by `WorkflowBuilder.build()`."
        )

    graph = getattr(workflow, "graph", None)
    if graph is None:
        raise ValueError(
            "compute_workflow_fingerprint(): workflow has no `.graph` "
            "attribute. Expected `kailash.workflow.graph.Workflow`."
        )

    # Node IDs + types — sorted for determinism
    node_entries: List[Tuple[str, str]] = []
    instances = getattr(workflow, "_node_instances", {}) or {}
    for node_id in sorted(graph.nodes()):
        node_instance = instances.get(node_id)
        node_type = (
            node_instance.__class__.__name__ if node_instance is not None else ""
        )
        node_entries.append((str(node_id), node_type))

    # Edges — sorted for determinism. Edge attributes (mappings) are
    # intentionally NOT included; an edge mapping change is treated as a
    # parameter-channel change.
    edges_iter = graph.edges()
    edge_entries: List[Tuple[str, str]] = sorted(
        (str(src), str(tgt)) for src, tgt in edges_iter
    )

    payload = {
        "nodes": node_entries,
        "edges": edge_entries,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_checkpoint_key(
    workflow_fingerprint: str,
    idempotency_key: str,
    parameters: Optional[Mapping[str, Any]] = None,
    *,
    tenant_id: Optional[str] = None,
) -> str:
    """Build a stable checkpoint key.

    The key is the SHA-256 hex digest of
    ``(tenant_id, workflow_fingerprint, idempotency_key, parameters)``.
    Stable across processes — two calls with the same inputs produce the
    same key. Per architecture plan §6 risk register.

    The ``tenant_id`` partition is mandatory per
    ``rules/tenant-isolation.md`` MUST Rule 5: a tenant MUST NOT be able
    to read another tenant's checkpoint by guessing or replaying the
    same ``idempotency_key``.

    Parameters that are not JSON-serialisable degrade gracefully via
    ``default=str`` — the key remains stable for stable inputs.
    """
    if not isinstance(workflow_fingerprint, str) or not workflow_fingerprint:
        raise ValueError(
            "build_checkpoint_key(): workflow_fingerprint must be a "
            "non-empty hex string from compute_workflow_fingerprint()."
        )
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError(
            "build_checkpoint_key(): idempotency_key must be a non-empty "
            "string supplied by the caller."
        )

    payload = {
        "tenant_id": tenant_id,
        "workflow_fingerprint": workflow_fingerprint,
        "idempotency_key": idempotency_key,
        "parameters": parameters or {},
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    # Prefix the digest with a stable namespace so operators reading the
    # checkpoint table can tell the row's purpose at a glance.
    return f"kailash.runtime.checkpoint.{digest}"


# ---------------------------------------------------------------------------
# Classification-aware event redaction
# ---------------------------------------------------------------------------


def redact_event_for_persistence(
    event: NodeCompletionEvent,
    *,
    classification_policy: Optional[Any] = None,
) -> NodeCompletionEvent:
    """Return a copy of ``event`` safe to persist to checkpoint / history.

    This is the shared redaction helper mandated by the cross-cutting
    invariant 3.1 in the architecture plan. Both
    :class:`~kailash.runtime.local.LocalRuntime` checkpoint emission AND
    the W2 history store path MUST route every event through this
    function before any ``store.save(...)`` / ``store.record(...)`` call.

    Behavior:

    * If ``classification_policy`` is ``None`` (no classification
      configured), the event is returned unchanged. This matches the
      runtime's default single-tenant single-classification posture.
    * If ``classification_policy`` is provided, this function consults
      the policy for each top-level field of ``event.outputs`` and:

      - drops any field tagged ``REDACT`` and replaces it with the
        sentinel ``"[REDACTED]"`` (NOT ``None`` — ``None`` is a valid
        unredacted value),
      - hashes any field tagged ``HASH_PK`` via
        ``format_record_id_for_event`` (a stable SHA-256-based digest),
      - leaves classification-free fields untouched.

    The function NEVER raises on a missing policy method — when the
    policy doesn't expose the expected duck-typed surface, it returns
    the event unchanged with a single DEBUG log line. Per
    ``rules/observability.md`` Rule 8 the schema-revealing field names
    (e.g. ``users.ssn``) ride at DEBUG, not WARN/INFO.

    The classified-field-name partition (per
    ``rules/event-payload-classification.md`` MUST Rule 3) lives in the
    event's ``metadata`` dict under
    ``metadata["classification_summary"]`` and contains:

    * ``unclassified_fields``: list[str] — names safe to log
    * ``classified_field_count``: int — count of redacted+hashed fields

    The classified field NAMES themselves are intentionally NOT in the
    summary — only the count is, so an operator-facing log line at INFO
    can report "3 classified fields redacted" without leaking the
    schema.

    The output is a NEW ``NodeCompletionEvent`` (frozen dataclass) — the
    caller's original event is never mutated.
    """
    if classification_policy is None:
        return event

    raw_outputs = dict(event.outputs)
    redacted_outputs: Dict[str, Any] = {}
    unclassified_fields: List[str] = []
    classified_count = 0

    for field_name, value in raw_outputs.items():
        try:
            tag = _get_classification_tag(
                classification_policy, event.node_id, field_name
            )
        except Exception as exc:  # pragma: no cover — defensive belt
            # Per rules/zero-tolerance.md Rule 3: do not silently swallow.
            # Log at DEBUG (schema name is in the message) and treat as
            # unclassified (fail-OPEN here is intentionally chosen — the
            # security gate is the policy itself; the redactor is the
            # display safety net).
            logger.debug(
                "durable.redact.policy_lookup_failed",
                extra={
                    "node_id": event.node_id,
                    "field_name_hash": _hash_short(field_name),
                    "error": type(exc).__name__,
                },
            )
            tag = None

        if tag == "REDACT":
            redacted_outputs[field_name] = "[REDACTED]"
            classified_count += 1
        elif tag == "HASH_PK":
            redacted_outputs[field_name] = _hash_pk(value)
            classified_count += 1
        else:
            redacted_outputs[field_name] = value
            unclassified_fields.append(field_name)

    # Merge classification summary into metadata.
    new_metadata = dict(event.metadata)
    new_metadata["classification_summary"] = {
        "unclassified_fields": unclassified_fields,
        "classified_field_count": classified_count,
    }

    return NodeCompletionEvent(
        run_id=event.run_id,
        workflow_id=event.workflow_id,
        workflow_fingerprint=event.workflow_fingerprint,
        node_id=event.node_id,
        node_type=event.node_type,
        outputs=redacted_outputs,
        started_at=event.started_at,
        ended_at=event.ended_at,
        duration_ms=event.duration_ms,
        tenant_id=event.tenant_id,
        idempotency_key=event.idempotency_key,
        error=event.error,
        metadata=new_metadata,
    )


# Internal-name alias kept for cross-architecture-plan citations
# (the plan references ``_redact_event_for_persistence`` as the helper
# name; the public re-export is the un-prefixed name).
_redact_event_for_persistence = redact_event_for_persistence


def _get_classification_tag(
    policy: Any, node_id: str, field_name: str
) -> Optional[str]:
    """Best-effort lookup of a classification tag for a node/field.

    Tries (in order) the duck-typed methods a classification policy may
    expose:

    1. ``policy.get_classification(node_id, field_name)`` returning a tag
    2. ``policy.classify(node_id, field_name)`` (alternate naming)
    3. ``policy.is_classified(node_id, field_name)`` -> truthy → REDACT

    Returns ``None`` if no method matches OR the result is unrecognised.
    """
    for attr in ("get_classification", "classify"):
        fn = getattr(policy, attr, None)
        if callable(fn):
            tag = fn(node_id, field_name)
            if tag in ("REDACT", "HASH_PK"):
                return tag
            if tag is None:
                return None
    is_classified = getattr(policy, "is_classified", None)
    if callable(is_classified) and is_classified(node_id, field_name):
        return "REDACT"
    return None


def _hash_pk(value: Any) -> str:
    """Hash a primary-key-shaped value for event persistence.

    Mirrors the contract of ``format_record_id_for_event`` in
    ``rules/event-payload-classification.md`` MUST Rule 1 — produces a
    stable, opaque, fixed-length identifier so cross-event correlation
    still works while the raw PK never lands in the event store.
    """
    if value is None:
        return "pk:null"
    coerced = str(value).encode("utf-8")
    digest = hashlib.sha256(coerced).hexdigest()[:16]
    return f"pk:{digest}"


def _hash_short(value: str) -> str:
    """Short SHA-256 hash for schema-revealing log fields (Rule 8)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------


class NodeCompletionHookRegistry:
    """Registry of per-node-completion subscribers.

    Used by both LocalRuntime and AsyncLocalRuntime to provide
    ``runtime.on_node_complete(callback)``. Multi-subscriber dispatch is
    supported (W2 history store, metrics, audit). Both sync and async
    callbacks are honored — the runtime calls
    :meth:`dispatch_async` from inside the per-node async path.

    The registry is intentionally thread-safe-without-locks for the
    common case (subscribers register once at runtime construction and
    are never mutated mid-run). Concurrent ``register()`` calls during a
    live run are not the design target; if a future use case needs them,
    add an :class:`asyncio.Lock` here — the existing tests will surface
    the race.
    """

    def __init__(self) -> None:
        self._callbacks: List[NodeCompletionCallback] = []

    # -- Registration -------------------------------------------------

    def register(self, callback: NodeCompletionCallback) -> Callable[[], None]:
        """Register ``callback``. Returns an unregister function."""
        if not callable(callback):
            raise TypeError(
                f"NodeCompletionHookRegistry.register(): callback must be "
                f"callable, got {type(callback).__name__}"
            )
        self._callbacks.append(callback)

        def _unregister() -> None:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

        return _unregister

    def clear(self) -> None:
        """Drop all subscribers (test helper)."""
        self._callbacks.clear()

    @property
    def subscriber_count(self) -> int:
        """Number of registered subscribers (test helper)."""
        return len(self._callbacks)

    # -- Dispatch -----------------------------------------------------

    async def dispatch_async(self, event: NodeCompletionEvent) -> None:
        """Dispatch ``event`` to all subscribers, awaiting any coroutines.

        Subscriber exceptions are logged at WARN (per
        ``rules/observability.md`` Rule 7 — partial failure across
        subscribers MUST emit a WARN line) and do NOT abort the runtime;
        a misbehaving metrics subscriber MUST NOT take down the workflow
        execution that the user cares about. Failed subscribers are
        counted and surfaced in the WARN log.

        Per ``rules/zero-tolerance.md`` Rule 3 we still raise
        ``CancelledError`` / ``KeyboardInterrupt`` / ``SystemExit``.
        """
        if not self._callbacks:
            return

        # Snapshot the callback list so an unregister() during dispatch
        # doesn't disturb iteration.
        callbacks = list(self._callbacks)
        failed: List[Tuple[str, str]] = []

        for cb in callbacks:
            try:
                result = cb(event)
                if inspect.isawaitable(result):
                    await result
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:  # noqa: BLE001 — see WARN below
                failed.append((_callback_name(cb), type(exc).__name__))
                logger.warning(
                    "durable.on_node_complete.subscriber_failed",
                    extra={
                        "callback": _callback_name(cb),
                        "error_type": type(exc).__name__,
                        "node_id_hash": _hash_short(event.node_id),
                        "run_id": event.run_id,
                    },
                )

        if failed:
            logger.warning(
                "durable.on_node_complete.partial_dispatch",
                extra={
                    "attempted": len(callbacks),
                    "failed": len(failed),
                    "first_failure": failed[0] if failed else None,
                },
            )


def _callback_name(cb: NodeCompletionCallback) -> str:
    """Best-effort label for a callback in WARN logs."""
    name = getattr(cb, "__qualname__", None) or getattr(cb, "__name__", None)
    if name:
        return name
    return repr(cb)


# ---------------------------------------------------------------------------
# Internals shared with the runtime — checkpoint header for shape-drift
# ---------------------------------------------------------------------------


def encode_checkpoint_payload(
    *,
    workflow_fingerprint: str,
    tracker_state: Mapping[str, Any],
    tenant_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> bytes:
    """Encode the checkpoint blob with a header that includes the fingerprint.

    The header is what :func:`decode_checkpoint_payload` reads to detect
    shape drift before re-using cached node outputs. UTF-8 JSON; deflated
    only by the underlying store if it chooses to.
    """
    payload = {
        "version": 1,
        "workflow_fingerprint": workflow_fingerprint,
        "tenant_id": tenant_id,
        "workflow_id": workflow_id,
        "idempotency_key": idempotency_key,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "tracker": dict(tracker_state),
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode_checkpoint_payload(blob: bytes) -> Dict[str, Any]:
    """Decode a blob produced by :func:`encode_checkpoint_payload`.

    Raises ``ValueError`` if the header is missing required fields. This
    is the runtime-layer typed-error gate per ``rules/zero-tolerance.md``
    Rule 3a — opaque ``KeyError`` from ``payload["workflow_fingerprint"]``
    is BLOCKED.
    """
    try:
        payload = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Checkpoint payload is not valid UTF-8 JSON. The store may "
            "have returned a corrupted row, or a non-Kailash producer "
            "wrote to the same key namespace. Investigate before "
            "force_resume_with_drift=True."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            "Checkpoint payload root is not a JSON object. Expected "
            "{version, workflow_fingerprint, tracker, ...}."
        )
    if "workflow_fingerprint" not in payload or "tracker" not in payload:
        raise ValueError(
            "Checkpoint payload missing required fields "
            "(workflow_fingerprint, tracker). The blob was likely "
            "produced by a pre-v1 writer; force_resume_with_drift=True "
            "is required to overwrite it."
        )
    return payload


def check_shape_drift_or_raise(
    *,
    idempotency_key: str,
    stored_payload: Mapping[str, Any],
    current_fingerprint: str,
    force_resume_with_drift: bool,
) -> None:
    """Compare stored vs current fingerprint; raise on drift.

    See :class:`WorkflowShapeDriftError` for semantics.
    """
    stored_fp = stored_payload.get("workflow_fingerprint", "")
    if stored_fp == current_fingerprint:
        return
    if force_resume_with_drift:
        logger.warning(
            "durable.resume.shape_drift_forced",
            extra={
                "idempotency_key_hash": _hash_short(idempotency_key),
                "stored_fp_short": stored_fp[:12],
                "current_fp_short": current_fingerprint[:12],
            },
        )
        return
    raise WorkflowShapeDriftError(
        idempotency_key=idempotency_key,
        stored_fingerprint=stored_fp,
        current_fingerprint=current_fingerprint,
    )


# ---------------------------------------------------------------------------
# Tenant context resolution (best-effort across runtime variants)
# ---------------------------------------------------------------------------


def resolve_tenant_id(runtime: Any) -> Optional[str]:
    """Resolve the active tenant_id from the runtime + ContextVar.

    Per the cross-cutting invariant 3.3, both checkpoint rows and history
    rows MUST carry the active tenant. We consult, in order:

    1. ``runtime.user_context.tenant_id`` if exposed
    2. ``kailash.trust.auth.context.get_current_tenant_id()`` if importable
    3. ``None`` (single-tenant deployments)

    The resolver never raises — a missing tenant context is a valid
    single-tenant deployment, NOT a security failure. Tenant enforcement
    happens at the storage layer (composite key includes ``tenant_id``).
    """
    user_ctx = getattr(runtime, "user_context", None)
    if user_ctx is not None:
        tenant_id = getattr(user_ctx, "tenant_id", None)
        if tenant_id:
            return str(tenant_id)
    try:
        from kailash.trust.auth.context import get_current_tenant_id

        tenant_id = get_current_tenant_id()
        if tenant_id:
            return str(tenant_id)
    except Exception:  # pragma: no cover — optional surface
        pass
    return None


# Re-export for symmetry with redact_event_for_persistence — both
# helpers live in the same module and share the same private alias
# convention used by the architecture plan citations.
_resolve_tenant_id = resolve_tenant_id
