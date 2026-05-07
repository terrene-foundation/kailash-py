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
* :func:`redact_event_for_persistence` — shared classification-aware
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
    "DurableExecutionEngine",
    "DurableExecutionEngineBuilder",
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
        # FAIL-CLOSED on policy lookup error per rules/zero-tolerance.md
        # Rule 2 (no fake redaction). A policy raise during classification
        # MUST default to REDACT — silent fall-through to unclassified
        # would let a policy bug leak classified data to the persistent
        # checkpoint store.  The redactor IS a security gate, not just a
        # display safety net: the classification policy may be unreachable
        # (lazy-loaded, transient backend failure, attribute drift) and
        # the persisted blob is the audit trail downstream consumers
        # rely on.
        policy_failed = False
        try:
            tag = _get_classification_tag(
                classification_policy, event.node_id, field_name
            )
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            logger.warning(
                "durable.redact.policy_lookup_failed",
                extra={
                    "node_id_hash": _hash_short(event.node_id),
                    "field_name_hash": _hash_short(field_name),
                    "error_type": type(exc).__name__,
                },
            )
            tag = "REDACT"  # FAIL-CLOSED: replace value with [REDACTED]
            policy_failed = True

        if tag == "REDACT":
            redacted_outputs[field_name] = "[REDACTED]"
            classified_count += 1
        elif tag == "HASH_PK":
            redacted_outputs[field_name] = _hash_pk(value)
            classified_count += 1
        else:
            # Only return the unclassified value when policy lookup
            # CONFIRMED unclassified (returned None cleanly).  The
            # policy_failed branch above already routed to REDACT.
            redacted_outputs[field_name] = value
            unclassified_fields.append(field_name)
        # Belt-and-suspenders: if policy lookup failed AND somehow tag
        # was not REDACT, the value is sentinel-replaced regardless.
        if policy_failed and redacted_outputs[field_name] is value:
            redacted_outputs[field_name] = "[REDACTED]"

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

    A maliciously-crafted upstream node can pass an object whose
    ``__str__`` raises (or whose ``__str__`` returns a non-string and
    triggers a TypeError on ``encode``); rather than crashing the
    redaction pipeline, return a stable sentinel ``"pk:unhashable"`` and
    log at DEBUG.  Same fail-closed posture as
    :func:`redact_event_for_persistence` — never let a malformed value
    propagate raw to the event store.
    """
    if value is None:
        return "pk:null"
    try:
        coerced = str(value).encode("utf-8")
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        logger.debug(
            "durable.redact.unhashable_pk_value",
            extra={
                "value_type": type(value).__name__,
                "error_type": type(exc).__name__,
            },
        )
        return "pk:unhashable"
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
        # Defensive runtime check per rules/zero-tolerance.md Rule 3a — Python's
        # static annotations are unenforced at runtime, so a non-callable can
        # still arrive here through a duck-typed caller. pyright sees the
        # parameter annotation and flags the negative branch as unreachable;
        # the runtime guard is intentional.
        if not callable(callback):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(  # pyright: ignore[reportUnreachable]
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

    A missing trust subsystem (ImportError / AttributeError on the
    ``kailash.trust.auth.context`` surface) is a valid single-tenant
    deployment posture and is logged WARN once per process for operator
    visibility.  ANY other exception (ContextVar lookup error, runtime
    bug, propagation glitch) is RE-RAISED — silently swallowing them
    would mask cross-tenant exposure under a buggy trust subsystem.
    Same posture as ``rules/zero-tolerance.md`` Rule 3 (no silent
    fallbacks): narrow the except clause to the documented "optional
    surface" path; let everything else propagate.
    """
    user_ctx = getattr(runtime, "user_context", None)
    if user_ctx is not None:
        tenant_id = getattr(user_ctx, "tenant_id", None)
        if tenant_id:
            return str(tenant_id)
    try:
        from kailash.trust.auth.context import get_current_tenant_id
    except (ImportError, AttributeError):
        if not getattr(resolve_tenant_id, "_warned_unavailable", False):
            logger.warning(
                "durable.tenant.trust_subsystem_unavailable",
                extra={
                    "hint": (
                        "kailash.trust.auth.context.get_current_tenant_id "
                        "is not importable; tenant_id will be None.  "
                        "Multi-tenant safety is reduced — verify the "
                        "trust extras are installed if multi-tenancy is "
                        "expected."
                    ),
                },
            )
            resolve_tenant_id._warned_unavailable = True  # type: ignore[attr-defined]
        return None
    # ANY exception from the actual tenant lookup propagates — a
    # ContextVar lookup error or a propagation bug is NOT an "optional
    # surface" — silencing it would mask cross-tenant exposure.
    tenant_id = get_current_tenant_id()
    if tenant_id:
        return str(tenant_id)
    return None


# Module-scope flag init for the WARN-once latch above.  Stored on the
# function object directly so that test fixtures can reset it via
# ``del resolve_tenant_id._warned_unavailable`` between tests.
resolve_tenant_id._warned_unavailable = False  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# W4: DurableExecutionEngine — composes W1 (checkpoint) + W2 (history) +
#     W3 (dispatch) over a wrapped AsyncLocalRuntime.
# ---------------------------------------------------------------------------
#
# Design goals (per workspaces/runtime-integration-trio/todos/active/W4-...):
#
# * **No parallel implementation.** Every store / queue interaction routes
#   through W1 / W2 / W3 public APIs. The engine never re-implements
#   checkpoint persistence, history-row writing, or task dispatch — it
#   only composes the primitives.
# * **Public-only.** The engine consumes the public surface of each
#   primitive (``DBCheckpointStore.save / .load``,
#   ``WorkflowHistoryStore.record_event / .list_runs / .get_run /
#   .get_run_events``, ``Dispatcher.enqueue / .poll / .ack / .nack``). It
#   does NOT touch private members.
# * **Hook-routed.** Per-node events flow exclusively via the runtime's
#   :meth:`on_node_complete` hook registry. The engine MUST NOT read
#   runtime internals to observe node completions.
#
# The engine is deliberately small: a builder + an immutable engine + a
# thin :meth:`execute` shim that delegates to the wrapped runtime AND
# (when configured) enqueues a fire-time :class:`Task` through the W3
# dispatcher. The runtime itself auto-subscribes ``history_store.record_event``
# at construction time (W2 wiring) so the engine never has to manually
# call ``runtime.on_node_complete(history_store.record_event)`` — doing
# so would double-register the subscriber.


class DurableExecutionEngine:
    """First-party durable execution engine for Kailash workflows.

    Composes the runtime-integration-trio primitives — per-node
    checkpointing (W1), persistent workflow history (W2), and pluggable
    task dispatch (W3) — into a single facade callers can construct via
    :meth:`builder`. Each primitive is opt-in; an engine constructed
    with no primitives behaves like a plain ``AsyncLocalRuntime``.

    Example::

        from kailash.runtime.durable import DurableExecutionEngine
        from kailash.infrastructure.checkpoint_store import DBCheckpointStore
        from kailash.infrastructure.history_store import PostgresHistoryStore
        from kailash.infrastructure.task_queue import (
            SQLTaskQueue,
            SQLTaskQueueDispatcher,
        )

        engine = (
            DurableExecutionEngine.builder()
                .checkpoint_store(DBCheckpointStore(conn))
                .history_store(PostgresHistoryStore(conn))
                .dispatch_via(SQLTaskQueueDispatcher(queue=SQLTaskQueue(conn)))
                .build()
        )
        results, run_id = await engine.execute(
            workflow.build(), idempotency_key="user-42-prewarm",
        )
        # Native history-store API for queries (tenant_id required):
        runs = await engine.history.list_runs(filter={"tenant_id": "default"})
        events = await engine.history.get_run_events(run_id, tenant_id="default")

    Composition contract
    --------------------
    * ``checkpoint_store`` is forwarded to ``AsyncLocalRuntime(checkpoint_store=...,
      checkpoint_after_each_node=True)`` so per-node blobs land via the W1
      hot path (see :mod:`kailash.runtime.local` ``_record_node_completion``).
    * ``history_store`` is forwarded to ``AsyncLocalRuntime(history_store=...)``
      which auto-subscribes ``history_store.record_event`` against the
      hook registry at construction time. The engine does NOT call
      ``runtime.on_node_complete(history_store.record_event)`` separately
      — doing so would double-register the subscriber.
    * ``dispatcher`` is consulted ONLY when configured. When set,
      :meth:`execute` enqueues a fire-time :class:`Task` via the
      dispatcher in addition to running the workflow in-process. The
      enqueue is best-effort observability of the run; dispatcher
      failures emit a WARN log and do NOT abort the in-process
      execution. Future: a worker-pool variant that defers execution
      entirely to the dispatcher would override :meth:`execute`.

    Immutability
    ------------
    The engine is immutable after :meth:`DurableExecutionEngineBuilder.build`.
    Mutating any of its primitives in-place after construction is
    unsupported — construct a new engine via the builder if the
    composition needs to change.
    """

    def __init__(
        self,
        *,
        checkpoint_store: Optional[Any],
        history_store: Optional[Any],
        dispatcher: Optional[Any],
        idempotency_key_default: Optional[str],
        runtime_factory: Callable[..., Any],
        runtime_kwargs: Optional[Mapping[str, Any]],
    ) -> None:
        """Construct an engine. Use :meth:`builder` for the public path."""
        # Build the wrapped runtime via the caller-supplied factory,
        # forwarding the W1 + W2 wiring as kwargs. The factory receives
        # ``checkpoint_store=``, ``checkpoint_after_each_node=True`` (when
        # checkpoint_store is set), and ``history_store=`` so the runtime
        # auto-subscribes the W2 record_event callback at construction.
        kwargs: Dict[str, Any] = dict(runtime_kwargs or {})
        if checkpoint_store is not None:
            # Per-node checkpoint emission requires BOTH the store AND the
            # opt-in flag — see ``LocalRuntime.__init__`` (W1).  Primitive
            # setters OVERRIDE conflicting runtime_kwargs entries — the
            # setter is the explicit composition contract; runtime_kwargs
            # is the escape hatch for non-conflicting kwargs (e.g.
            # ``max_concurrent_nodes``).
            kwargs["checkpoint_store"] = checkpoint_store
            kwargs.setdefault("checkpoint_after_each_node", True)
        if history_store is not None:
            # Forwarding via the constructor is the W2-sanctioned path.
            # The runtime calls ``self._hook_registry.register(record_event)``
            # itself; calling ``runtime.on_node_complete(record_event)``
            # here would double-register the subscriber and double-write
            # every event.  Same override-runtime_kwargs semantics.
            kwargs["history_store"] = history_store

        runtime = runtime_factory(**kwargs)
        if not hasattr(runtime, "execute_workflow_async"):
            raise TypeError(
                "DurableExecutionEngine: runtime_factory(...) returned an "
                f"object of type {type(runtime).__name__!r} which does not "
                "expose execute_workflow_async(). Provide an AsyncLocalRuntime"
                " subclass or a duck-typed equivalent."
            )

        self._runtime = runtime
        self._checkpoint_store = checkpoint_store
        self._history_store = history_store
        self._dispatcher = dispatcher
        self._idempotency_key_default = idempotency_key_default

    # -- Public properties ---------------------------------------------

    @property
    def runtime(self) -> Any:
        """The wrapped :class:`AsyncLocalRuntime` (or factory-supplied alt).

        Returned for advanced callers who need direct access to the
        runtime — e.g. to register additional ``on_node_complete``
        subscribers beyond the W2 history store auto-subscribe. The
        runtime instance is the SAME one ``engine.execute`` delegates to.
        """
        return self._runtime

    @property
    def history(self) -> Any:
        """The composed history store, if configured. ``None`` otherwise.

        Exposes the native :class:`~kailash.infrastructure.history_store.WorkflowHistoryStore`
        read API (``list_runs``, ``get_run``, ``get_run_events``,
        ``list_failed``). Tenant scope is mandatory on every read per
        ``rules/tenant-isolation.md`` MUST Rule 5.
        """
        return self._history_store

    @property
    def checkpoint_store(self) -> Any:
        """The composed checkpoint store, if configured. ``None`` otherwise."""
        return self._checkpoint_store

    @property
    def dispatcher(self) -> Any:
        """The composed dispatcher, if configured. ``None`` otherwise."""
        return self._dispatcher

    @property
    def idempotency_key_default(self) -> Optional[str]:
        """The default idempotency key applied when ``execute`` omits it."""
        return self._idempotency_key_default

    # -- Builder factory -----------------------------------------------

    @classmethod
    def builder(cls) -> "DurableExecutionEngineBuilder":
        """Return a fresh fluent builder. See :class:`DurableExecutionEngineBuilder`."""
        return DurableExecutionEngineBuilder()

    # -- Execution -----------------------------------------------------

    async def execute(
        self,
        workflow: Any,
        *,
        idempotency_key: Optional[str] = None,
        inputs: Optional[Mapping[str, Any]] = None,
        force_resume_with_drift: bool = False,
        dispatch_kwargs: Optional[Mapping[str, Any]] = None,
        queue_name: str = "default",
    ) -> Tuple[Dict[str, Any], str]:
        """Execute *workflow* through the wrapped runtime and (optionally) dispatch.

        Parameters
        ----------
        workflow:
            The workflow returned by ``WorkflowBuilder.build()``.
        idempotency_key:
            Caller-supplied resume key. Falls back to
            :attr:`idempotency_key_default` when omitted. Forwarded to
            ``runtime.execute_workflow_async(idempotency_key=...)`` so the
            W1 checkpoint-resume path fires when a prior blob exists.
        inputs:
            Workflow inputs dict. Defaults to an empty dict.
        force_resume_with_drift:
            Forwarded to the runtime — when ``True`` an
            :class:`WorkflowShapeDriftError` is suppressed and the engine
            proceeds against the new shape per W1 §4.6.4. The default is
            to refuse on drift, matching ``git reset --keep`` and
            ``MigrationManager.apply_downgrade(force_downgrade=True)``.
        dispatch_kwargs:
            Free-form dict serialised into the dispatched
            :class:`~kailash.runtime.dispatcher.Task` ``kwargs`` field.
            Ignored when no dispatcher is configured.
        queue_name:
            Target queue when a dispatcher is configured. Defaults to
            ``"default"``.

        Returns
        -------
        Tuple[Dict[str, Any], str]
            ``(results, run_id)`` from the wrapped runtime. The runtime's
            ``run_id`` is also used to derive the dispatched task's
            ``schedule_id`` so an operator can correlate the queue row
            with the history row.

        Notes
        -----
        Dispatcher failures emit a WARN log via the standard runtime
        logger AND re-raise — the dispatch is part of the run's
        durability contract per the W3 wave, not best-effort. Callers
        who want best-effort dispatch should construct a custom
        :class:`~kailash.runtime.dispatcher.Dispatcher` whose ``enqueue``
        catches its own failures.
        """
        effective_inputs: Dict[str, Any] = (
            dict(inputs) if isinstance(inputs, Mapping) else {}
        )
        effective_key = (
            idempotency_key
            if idempotency_key is not None
            else self._idempotency_key_default
        )

        # Dispatch happens BEFORE in-process execution when configured —
        # the W3 contract treats enqueue as the durable record of intent.
        # If the dispatcher rejects the enqueue, in-process execution does
        # NOT proceed (the operator surfaced a real error). Workers polling
        # the queue will pick up the same task; idempotency on the
        # dispatcher's ``task_id`` (Dispatcher MUST Rule 1) prevents
        # double-execution by the worker if the in-process engine already
        # ran the workflow.
        run_id_hint: Optional[str] = None
        if self._dispatcher is not None:
            run_id_hint = await self._enqueue_for_run(
                workflow=workflow,
                inputs=effective_inputs,
                idempotency_key=effective_key,
                dispatch_kwargs=dispatch_kwargs or {},
                queue_name=queue_name,
            )

        # In-process execution. The runtime drives W1 (checkpoint emit)
        # and W2 (history record) via its own hook registry.
        results, run_id = await self._runtime.execute_workflow_async(
            workflow,
            inputs=effective_inputs,
            idempotency_key=effective_key,
            force_resume_with_drift=force_resume_with_drift,
        )
        # If the dispatcher returned a hint, the schedule_id and the
        # in-process run_id are correlated via the engine's WARN log line
        # so operators reading queue rows can find the matching history
        # row without spelunking.
        if run_id_hint is not None:
            logger.info(
                "durable.engine.execute.dispatched_and_executed",
                extra={
                    "schedule_id": run_id_hint,
                    "run_id": run_id,
                    "queue_name": queue_name,
                    "has_history_store": self._history_store is not None,
                    "has_checkpoint_store": self._checkpoint_store is not None,
                },
            )
        return results, run_id

    # -- Internals -----------------------------------------------------

    async def _enqueue_for_run(
        self,
        *,
        workflow: Any,
        inputs: Mapping[str, Any],
        idempotency_key: Optional[str],
        dispatch_kwargs: Mapping[str, Any],
        queue_name: str,
    ) -> str:
        """Serialise + enqueue a fire-time :class:`Task` for *workflow*.

        Lazy imports per ``rules/infrastructure-sql.md`` MUST Rule 8 —
        the W3 dispatcher module pulls in ``ConnectionManager`` and a
        translator stack; deferring the import keeps the durable module
        importable in environments that don't ship the W3 dependency.
        Returns the synthesised ``schedule_id`` so callers can correlate
        the enqueued row with the in-process run.
        """
        from kailash.runtime.dispatcher import Task, compute_task_id

        workflow_fingerprint = compute_workflow_fingerprint(workflow)
        # Resolve tenant scope from the runtime context BEFORE deriving the
        # schedule_id.  Per rules/tenant-isolation.md MUST Rule 5, every
        # idempotency-keyed identifier MUST partition on tenant — otherwise
        # two tenants invoking the same workflow with the same caller-supplied
        # idempotency_key (a perfectly normal pattern, e.g. per-user
        # "user-42-prewarm") collide on schedule_id and the dispatcher's
        # idempotency gate (Dispatcher MUST Rule 1) silently drops the
        # second tenant's task.  Mirrors the partitioning already enforced
        # by build_checkpoint_key (see § build_checkpoint_key above).
        # Empty-string fallback is intentional for legacy single-tenant
        # deployments — collapses to ``engine..{fingerprint}.{key}`` which
        # is unchanged from a single-tenant perspective.
        tenant_id = resolve_tenant_id(self._runtime) or ""
        # Deterministic schedule_id — ties the queue row to (tenant,
        # workflow shape, caller idempotency key).  Two ``engine.execute``
        # calls from the SAME tenant with the same key + same workflow
        # produce the same schedule_id, so the dispatcher's idempotency
        # gate (Dispatcher MUST Rule 1) drops the duplicate.  Two
        # different tenants get DIFFERENT schedule_ids and both tasks
        # land cleanly.
        schedule_id = (
            f"engine.{tenant_id}.{workflow_fingerprint[:12]}."
            f"{(idempotency_key or 'noop')}"
        )
        planned_fire_time = datetime.now(timezone.utc).isoformat()
        task_id = compute_task_id(schedule_id, datetime.now(timezone.utc))

        # The W3 contract serialises the workflow blob as the dispatcher's
        # responsibility — but the engine has no built-in serialiser for
        # arbitrary workflow objects (the SDK does not pickle workflows by
        # default, see ``Task.workflow_blob`` JSON contract). We pass an
        # empty bytes blob; the worker side reconstructs the workflow from
        # the orchestrator's local registry per project convention. Future
        # waves MAY add a workflow-blob serialiser, but the engine's job
        # here is to surface the dispatcher invocation, not to define the
        # serialisation format.
        workflow_blob = b""
        kwargs_payload: Dict[str, Any] = {
            "inputs": dict(inputs),
            "idempotency_key": idempotency_key,
            "engine": "DurableExecutionEngine",
        }
        kwargs_payload.update(dict(dispatch_kwargs))

        task = Task(
            task_id=task_id,
            schedule_id=schedule_id,
            workflow_blob=workflow_blob,
            planned_fire_time=planned_fire_time,
            queue_name=queue_name,
            kwargs=kwargs_payload,
        )
        # Typed delegate guard per rules/zero-tolerance.md Rule 3a — although
        # the public ``execute()`` only calls _enqueue_for_run when
        # self._dispatcher is not None, the helper is a private method that
        # could be reached via subclassing or refactor.  The guard turns an
        # opaque AttributeError on ``None.enqueue`` into an actionable
        # RuntimeError naming the missing builder call.
        if self._dispatcher is None:
            raise RuntimeError(
                "DurableExecutionEngine._enqueue_for_run(): no dispatcher "
                "configured.  Call .dispatch_via(<Dispatcher>) on the builder, "
                "or invoke .execute() without dispatch for in-process execution."
            )
        await self._dispatcher.enqueue(task)
        return schedule_id


class DurableExecutionEngineBuilder:
    """Fluent builder for :class:`DurableExecutionEngine`.

    Build pattern:

    1. ``DurableExecutionEngine.builder()`` returns a fresh builder.
    2. Chain optional ``.checkpoint_store(store)`` / ``.history_store(store)``
       / ``.dispatch_via(dispatcher)`` / ``.idempotency_key_default(key)`` /
       ``.runtime(factory)`` / ``.runtime_kwargs(mapping)`` calls.
    3. Call ``.build()`` to produce the immutable engine.

    Each setter returns ``self`` so the chain can run in one expression.
    Calling a setter twice OVERRIDES the prior value (no implicit fan-in)
    so the final ``.build()`` reflects the last setter call. The default
    runtime factory is :class:`~kailash.runtime.async_local.AsyncLocalRuntime`
    — pass a custom factory only when a subclass is needed (Docker, custom
    timeout, alternative scheduler).
    """

    def __init__(self) -> None:
        self._checkpoint_store: Optional[Any] = None
        self._history_store: Optional[Any] = None
        self._dispatcher: Optional[Any] = None
        self._idempotency_key_default: Optional[str] = None
        self._runtime_factory: Optional[Callable[..., Any]] = None
        self._runtime_kwargs: Dict[str, Any] = {}

    # -- Setters --------------------------------------------------------

    def checkpoint_store(self, store: Any) -> "DurableExecutionEngineBuilder":
        """Configure the checkpoint store. ``None`` clears the prior value."""
        self._checkpoint_store = store
        return self

    def history_store(self, store: Any) -> "DurableExecutionEngineBuilder":
        """Configure the history store. ``None`` clears the prior value."""
        self._history_store = store
        return self

    def dispatch_via(self, dispatcher: Any) -> "DurableExecutionEngineBuilder":
        """Configure the dispatcher. ``None`` clears the prior value."""
        self._dispatcher = dispatcher
        return self

    def idempotency_key_default(
        self, key: Optional[str]
    ) -> "DurableExecutionEngineBuilder":
        """Set the default ``idempotency_key`` applied to ``execute`` calls."""
        # Defensive runtime type guard per rules/zero-tolerance.md Rule 3a.
        # The Optional[str] annotation is unenforced at runtime; a duck-typed
        # caller passing an int / dict / object would otherwise propagate to
        # the workflow_runs row write where the typed error would be
        # opaque.  pyright sees the annotation and flags the negative branch
        # as unreachable; the runtime guard is intentional.
        if key is not None and not isinstance(
            key, str
        ):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(  # pyright: ignore[reportUnreachable]
                "DurableExecutionEngineBuilder.idempotency_key_default(): "
                f"key must be str or None, got {type(key).__name__}"
            )
        self._idempotency_key_default = key
        return self

    def runtime(
        self,
        runtime_factory: Optional[Callable[..., Any]] = None,
    ) -> "DurableExecutionEngineBuilder":
        """Set the runtime factory.

        Passing ``runtime_factory=None`` (or omitting the call entirely)
        defers to the default
        :class:`~kailash.runtime.async_local.AsyncLocalRuntime`. Pass a
        custom callable when an ``AsyncLocalRuntime`` subclass or a
        compatible alternative is required.
        """
        # Defensive runtime guard per rules/zero-tolerance.md Rule 3a — the
        # Optional[Callable] annotation does not prevent a duck-typed caller
        # from passing a non-callable.  pyright sees the annotation and flags
        # the negative branch as unreachable; the runtime guard is intentional.
        if runtime_factory is not None and not callable(runtime_factory):
            raise TypeError(  # pyright: ignore[reportUnreachable]
                "DurableExecutionEngineBuilder.runtime(): runtime_factory "
                f"must be callable or None, got {type(runtime_factory).__name__}"
            )
        self._runtime_factory = runtime_factory
        return self

    def runtime_kwargs(
        self, kwargs: Mapping[str, Any]
    ) -> "DurableExecutionEngineBuilder":
        """Override base kwargs forwarded to the runtime factory.

        ``checkpoint_store`` / ``checkpoint_after_each_node`` /
        ``history_store`` are added by :meth:`build` AFTER these kwargs,
        so they always win over conflicting entries here. Use this for
        ``max_concurrent_nodes``, ``execution_timeout``, ``user_context``,
        etc.
        """
        # Defensive runtime guard per rules/zero-tolerance.md Rule 3a.  The
        # Mapping[str, Any] annotation is unenforced at runtime; a string
        # ("max_concurrent=10") would hit the dict() copy below with a
        # cryptic ValueError.  pyright sees the annotation and flags the
        # negative branch as unreachable; the runtime guard is intentional.
        if not isinstance(
            kwargs, Mapping
        ):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError(  # pyright: ignore[reportUnreachable]
                "DurableExecutionEngineBuilder.runtime_kwargs(): kwargs must "
                f"be a Mapping, got {type(kwargs).__name__}"
            )
        self._runtime_kwargs = dict(kwargs)
        return self

    # -- Build ----------------------------------------------------------

    def build(self) -> "DurableExecutionEngine":
        """Construct the immutable :class:`DurableExecutionEngine`.

        Lazy-imports :class:`~kailash.runtime.async_local.AsyncLocalRuntime`
        as the default factory. The lazy import keeps :mod:`kailash.runtime.durable`
        importable when ``async_local`` is not yet available (cyclic-import
        safety) and matches the W1 / W2 module-load contracts.
        """
        if self._runtime_factory is None:
            # Lazy import to avoid a hard module-load cycle:
            # async_local imports durable, so durable importing async_local
            # at module scope would be a cycle. The factory is only needed
            # at build() time, well after both modules have loaded.
            from kailash.runtime.async_local import (
                AsyncLocalRuntime,  # local import is intentional
            )

            factory: Callable[..., Any] = AsyncLocalRuntime
        else:
            factory = self._runtime_factory

        return DurableExecutionEngine(
            checkpoint_store=self._checkpoint_store,
            history_store=self._history_store,
            dispatcher=self._dispatcher,
            idempotency_key_default=self._idempotency_key_default,
            runtime_factory=factory,
            runtime_kwargs=self._runtime_kwargs,
        )
