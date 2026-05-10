# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the runtime subscriber-error handler.

Issue #876 C-2b — the per-node subscriber chain
(:class:`kailash.runtime.durable.NodeCompletionHookRegistry.dispatch_async`)
MUST observe a typed :class:`~kailash.sdk_exceptions.MissingRunIdError`
specifically — BEFORE the generic ``Exception`` fallback — and emit:

* a WARN log line ``history_store.record_event.dropped`` with hashed
  ``node_id_hash`` + ``workflow_id_hash`` per ``rules/observability.md``
  Rule 8.
* a metric counter increment on
  ``kailash_history_store_record_event_dropped_total``.

Forward-progress invariant: the handler MUST NOT re-raise; the
runtime continues processing the next subscriber AND the next node.

The same handler lives in ``durable.py`` and is shared by BOTH
:class:`~kailash.runtime.local.LocalRuntime` and
:class:`~kailash.runtime.async_local.AsyncLocalRuntime` — see
``rules/security.md`` § Multi-Site Kwarg Plumbing (a single
extraction point prevents drift across sibling runtimes).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import pytest

from kailash.runtime.durable import NodeCompletionEvent, NodeCompletionHookRegistry
from kailash.runtime.metrics import get_metrics_bridge
from kailash.sdk_exceptions import MissingRunIdError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_short(value: str) -> str:
    """Match the helper at ``durable.py::_hash_short``."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _make_event(
    *, node_id: str = "n1", workflow_id: str | None = "wf-1", run_id: str | None = None
) -> NodeCompletionEvent:
    """Construct a NodeCompletionEvent with the minimal required fields."""
    now = datetime.now(timezone.utc)
    return NodeCompletionEvent(
        run_id=run_id,
        workflow_id=workflow_id or "",
        workflow_fingerprint="fp",
        node_id=node_id,
        node_type="PythonCodeNode",
        outputs={},
        started_at=now,
        ended_at=now,
        duration_ms=1,
    )


# ---------------------------------------------------------------------------
# Typed-handler precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_async_catches_missing_run_id_error_typed() -> None:
    """A subscriber raising ``MissingRunIdError`` MUST be caught by the
    typed branch — the generic ``Exception`` fallback MUST NOT fire,
    so the generic ``subscriber.error`` metric counter stays at zero.
    """
    registry = NodeCompletionHookRegistry()

    async def raising_subscriber(event: NodeCompletionEvent) -> None:
        raise MissingRunIdError(node_id=event.node_id, workflow_id=event.workflow_id)

    registry.register(raising_subscriber)
    event = _make_event(node_id="n-typed", workflow_id="wf-typed")

    # MUST NOT re-raise — forward-progress invariant.
    await registry.dispatch_async(event)


@pytest.mark.asyncio
async def test_dispatch_async_logs_history_store_dropped_with_hashed_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The typed handler emits ``history_store.record_event.dropped`` at
    WARN with hashed identifiers — raw node_id / workflow_id MUST NOT
    appear in any log record per ``rules/observability.md`` Rule 8.
    """
    caplog.set_level(logging.WARNING)
    registry = NodeCompletionHookRegistry()

    async def raising_subscriber(event: NodeCompletionEvent) -> None:
        raise MissingRunIdError(node_id=event.node_id, workflow_id=event.workflow_id)

    registry.register(raising_subscriber)
    secret_node = "n-secret-123"
    secret_wf = "wf-secret-abc"
    event = _make_event(node_id=secret_node, workflow_id=secret_wf)

    await registry.dispatch_async(event)

    # Locate the dropped-event log record.
    dropped_records = [
        r
        for r in caplog.records
        if r.getMessage() == "history_store.record_event.dropped"
    ]
    assert len(dropped_records) == 1
    record = dropped_records[0]
    assert record.levelno == logging.WARNING
    # Hashed identifiers present.
    assert getattr(record, "node_id_hash", None) == _hash_short(secret_node)
    assert getattr(record, "workflow_id_hash", None) == _hash_short(secret_wf)
    # mode label per ``specs/core-runtime.md`` § audit-log emission contract.
    assert getattr(record, "mode", None) == "missing_run_id"
    # Raw identifiers MUST NOT appear ANYWHERE in the record's data.
    record_blob = repr(record.__dict__) + record.getMessage()
    assert secret_node not in record_blob
    assert secret_wf not in record_blob


@pytest.mark.asyncio
async def test_dispatch_async_renders_none_workflow_id_hash_sentinel(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the typed error carries ``workflow_id=None`` the handler
    renders the literal ``workflow_id_hash="None"`` sentinel — NOT a
    hash of the string ``"None"`` — so the subscriber-error handler
    distinguishes the two cases.
    """
    caplog.set_level(logging.WARNING)
    registry = NodeCompletionHookRegistry()

    async def raising_subscriber(event: NodeCompletionEvent) -> None:
        raise MissingRunIdError(node_id=event.node_id, workflow_id=None)

    registry.register(raising_subscriber)
    event = _make_event(node_id="n1", workflow_id="")

    await registry.dispatch_async(event)

    dropped_records = [
        r
        for r in caplog.records
        if r.getMessage() == "history_store.record_event.dropped"
    ]
    assert len(dropped_records) == 1
    assert getattr(dropped_records[0], "workflow_id_hash", None) == "None"


@pytest.mark.asyncio
async def test_dispatch_async_increments_dropped_metric_counter() -> None:
    """The typed handler increments
    ``kailash_history_store_record_event_dropped_total`` by 1 per typed
    error observed. Issue #876 C-2b acceptance gate.
    """
    bridge = get_metrics_bridge()
    counter_name = "kailash_history_store_record_event_dropped_total"
    before = bridge.cumulative_count(counter_name)

    registry = NodeCompletionHookRegistry()

    async def raising_subscriber(event: NodeCompletionEvent) -> None:
        raise MissingRunIdError(node_id=event.node_id, workflow_id=event.workflow_id)

    registry.register(raising_subscriber)
    await registry.dispatch_async(_make_event())

    after = bridge.cumulative_count(counter_name)
    assert after == before + 1


# ---------------------------------------------------------------------------
# Forward-progress invariant (siblings continue)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_async_continues_past_typed_error_to_next_subscriber() -> None:
    """When subscriber A raises ``MissingRunIdError``, subscriber B
    MUST still run. The runtime's per-node loop depends on this
    invariant for every downstream metric / audit / replication path.
    """
    registry = NodeCompletionHookRegistry()
    b_calls: list[NodeCompletionEvent] = []

    async def raising_subscriber(event: NodeCompletionEvent) -> None:
        raise MissingRunIdError(node_id=event.node_id, workflow_id=event.workflow_id)

    async def recording_subscriber(event: NodeCompletionEvent) -> None:
        b_calls.append(event)

    registry.register(raising_subscriber)
    registry.register(recording_subscriber)

    await registry.dispatch_async(_make_event(node_id="forward-progress"))

    assert len(b_calls) == 1
    assert b_calls[0].node_id == "forward-progress"


@pytest.mark.asyncio
async def test_dispatch_async_distinct_from_generic_subscriber_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-typed ``Exception`` MUST land in the generic
    ``durable.on_node_complete.subscriber_failed`` branch, NOT the
    typed ``history_store.record_event.dropped`` branch. This proves
    the typed-handler precedence is not accidentally catching every
    exception.
    """
    caplog.set_level(logging.WARNING)
    registry = NodeCompletionHookRegistry()

    async def generic_failure(event: NodeCompletionEvent) -> None:
        raise RuntimeError("unrelated subscriber bug")

    registry.register(generic_failure)
    await registry.dispatch_async(_make_event())

    typed_records = [
        r
        for r in caplog.records
        if r.getMessage() == "history_store.record_event.dropped"
    ]
    generic_records = [
        r
        for r in caplog.records
        if r.getMessage() == "durable.on_node_complete.subscriber_failed"
    ]
    assert typed_records == []
    assert len(generic_records) >= 1
