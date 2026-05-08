# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical workflow-blob serialization for queue dispatch.

Single source of truth for converting a built ``Workflow`` (or a class
that satisfies the ``to_dict()`` protocol) into the JSON-encoded UTF-8
``bytes`` payload that lands in :class:`kailash.runtime.dispatcher.Task`'s
``workflow_blob``. Both producer surfaces — :class:`WorkflowScheduler`
(``runtime/scheduler.py``) and :class:`DurableExecutionEngine`
(``runtime/durable.py``) — route through this helper so they emit
byte-identical output for the same workflow. Multi-site drift here would
break worker-side ``Workflow.from_dict(json.loads(blob.decode("utf-8")))``
reconstruction asymmetrically across the two enqueue paths.

Why JSON, not pickle: a queue payload an attacker can INSERT into is
remote code execution under ``pickle.loads`` (`rules/security.md`
§ "No arbitrary-code execution on user input"). Workers reconstruct
deterministically from the JSON dict via
:meth:`kailash.workflow.graph.Workflow.from_dict`.

Why a discriminator (per `rules/zero-tolerance.md` Rule 3d): a
``hasattr(workflow, "to_dict")`` duck-type check silently returns False
for any object whose ``to_dict`` is an instance attribute that gets
shadowed; the explicit type-check + class-level protocol branch admits
the canonical :class:`~kailash.workflow.graph.Workflow` AND deterministic
test stubs that satisfy the protocol via class definition, while
rejecting types that have no JSON-serializable representation.
"""
from __future__ import annotations

import json
from typing import Any

# 8 MiB is generous for legitimate Workflow shapes and tight enough to
# refuse a poisoned config before it reaches the queue. Documented in
# `specs/scheduling.md` § "Queue dispatch — payload bounds". The size
# cap is enforced at the producer boundary (here) and again at the
# queue adapter (defense-in-depth) per `rules/security.md`
# § "Input Validation".
MAX_WORKFLOW_BLOB_BYTES = 8 * 1024 * 1024  # 8 MiB


def serialize_workflow_to_blob(workflow: Any) -> bytes:
    """Serialize *workflow* to the canonical queue-dispatch byte payload.

    Returns JSON-encoded UTF-8 bytes obtained from ``workflow.to_dict()``.
    Refuses workflows whose serialized size exceeds
    :data:`MAX_WORKFLOW_BLOB_BYTES` with an actionable :class:`ValueError`
    naming the cap and the workflow's serialized size — workers
    dequeueing an unbounded blob would ``json.loads`` it into memory
    and OOM the worker process.

    Workers reconstruct via::

        from kailash.workflow.graph import Workflow
        workflow = Workflow.from_dict(json.loads(blob.decode("utf-8")))

    :param workflow: A built :class:`~kailash.workflow.graph.Workflow`
        OR any object whose class defines a ``to_dict()`` method
        returning a JSON-serializable mapping.
    :raises TypeError: when *workflow* is neither a ``Workflow`` instance
        nor a class with a ``to_dict()`` method (no JSON representation
        is derivable).
    :raises ValueError: when the serialized size exceeds the cap.
    :returns: UTF-8-encoded JSON bytes representing *workflow*.
    """
    # Lazy import — keeps this module importable in environments that
    # haven't fully initialised the workflow package (e.g. minimal CLI
    # tooling that touches scheduler.py constants without building a
    # graph).
    from kailash.workflow.graph import Workflow as _Workflow

    if isinstance(workflow, _Workflow):
        workflow_dict = workflow.to_dict()
    elif hasattr(type(workflow), "to_dict") and callable(
        getattr(type(workflow), "to_dict")
    ):
        # Class-level to_dict() — admits Tier-1 stubs that satisfy
        # the protocol via class definition (NOT instance attr,
        # which is too permissive and reintroduces the duck-type
        # silent-fallback pattern per zero-tolerance Rule 3d).
        workflow_dict = workflow.to_dict()
    else:
        raise TypeError(
            f"workflow argument is {type(workflow).__name__} which is not a "
            f"kailash.workflow.graph.Workflow nor a class defining to_dict() — "
            f"queue dispatch requires JSON-serializable workflow representation. "
            f"Use Workflow or a subclass that implements to_dict()."
        )

    workflow_blob = json.dumps(workflow_dict).encode("utf-8")
    if len(workflow_blob) > MAX_WORKFLOW_BLOB_BYTES:
        raise ValueError(
            f"workflow_blob size {len(workflow_blob)} bytes exceeds "
            f"MAX_WORKFLOW_BLOB_BYTES ({MAX_WORKFLOW_BLOB_BYTES} bytes / "
            f"{MAX_WORKFLOW_BLOB_BYTES // (1024 * 1024)} MiB). Workflow "
            f"is too large to dispatch through the queue path; reduce "
            f"the workflow surface (split into sub-workflows, externalize "
            f"large data) or use in-process dispatch (dispatch_via=None)."
        )
    return workflow_blob


__all__ = ["MAX_WORKFLOW_BLOB_BYTES", "serialize_workflow_to_blob"]
