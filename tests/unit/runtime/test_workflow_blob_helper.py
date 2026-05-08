# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for :mod:`kailash.runtime._workflow_blob`.

The helper is the single source of truth for queue-dispatch payload
serialization across :class:`WorkflowScheduler` and
:class:`DurableExecutionEngine`. Every producer site routes through
:func:`serialize_workflow_to_blob` so the byte output is identical for
the same workflow regardless of which surface enqueues the task.
"""
from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from kailash.runtime._workflow_blob import (
    MAX_WORKFLOW_BLOB_BYTES,
    serialize_workflow_to_blob,
)
from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Discriminator dispatch
# ---------------------------------------------------------------------------


class _ProtocolStub:
    """Class-level ``to_dict()`` protocol — accepted by the helper.

    Per ``rules/zero-tolerance.md`` Rule 3d the helper accepts class-
    level ``to_dict()`` (not instance attribute) so deterministic test
    stubs can satisfy the protocol without subclassing
    :class:`Workflow`.
    """

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return self._payload


class _NoToDict:
    """No ``to_dict`` method — the helper MUST refuse this with TypeError."""


def test_canonical_workflow_serializes_via_to_dict() -> None:
    """A built :class:`Workflow` is encoded as JSON-decodable UTF-8 bytes."""
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "n1", {"code": "result = 42"})
    workflow = builder.build()

    blob = serialize_workflow_to_blob(workflow)

    assert isinstance(blob, bytes)
    assert blob != b""
    decoded = json.loads(blob.decode("utf-8"))
    assert isinstance(decoded, dict)
    # Helper output MUST equal the JSON-roundtripped form of the
    # workflow's own to_dict — that is the byte sequence worker-side
    # reconstruction reads. JSON normalizes tuples into lists, so the
    # comparison is against the roundtripped shape, not the raw dict.
    assert decoded == json.loads(json.dumps(workflow.to_dict()))


def test_protocol_stub_with_class_level_to_dict_accepted() -> None:
    """Class-level ``to_dict`` protocol satisfies the helper.

    Tier-1 stubs that satisfy the protocol via class definition are
    accepted; instance-attribute ``to_dict`` is NOT enough — the
    discriminator deliberately checks ``hasattr(type(workflow), ...)``
    to defeat the duck-type silent-fallback pattern.
    """
    payload = {"name": "stub", "nodes": []}
    stub = _ProtocolStub(payload)

    blob = serialize_workflow_to_blob(stub)

    assert json.loads(blob.decode("utf-8")) == payload


def test_object_without_to_dict_raises_type_error() -> None:
    """A type with no ``to_dict`` is refused with an actionable message."""
    with pytest.raises(TypeError, match="to_dict"):
        serialize_workflow_to_blob(_NoToDict())


# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------


class _OversizedStub:
    """Returns a payload large enough to exceed the cap when JSON-encoded."""

    def __init__(self, payload_bytes: int) -> None:
        self._payload_bytes = payload_bytes

    def to_dict(self) -> Dict[str, Any]:
        return {"name": "big", "blob": "x" * self._payload_bytes}


def test_size_cap_raises_with_actionable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oversized payloads raise ``ValueError`` naming the cap."""
    from kailash.runtime import _workflow_blob as wb_mod

    monkeypatch.setattr(wb_mod, "MAX_WORKFLOW_BLOB_BYTES", 1024)

    with pytest.raises(ValueError, match="MAX_WORKFLOW_BLOB_BYTES"):
        serialize_workflow_to_blob(_OversizedStub(payload_bytes=2000))


def test_size_cap_default_value_is_eight_mib() -> None:
    """The default cap is documented at 8 MiB."""
    assert MAX_WORKFLOW_BLOB_BYTES == 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# Determinism / idempotence
# ---------------------------------------------------------------------------


def test_same_workflow_produces_byte_identical_output() -> None:
    """Calling the helper twice on the same workflow yields the same bytes.

    Worker-side reconstruction (``Workflow.from_dict``) is deterministic
    only if the producer emits stable JSON. Repeated serialization MUST
    produce byte-identical output so multiple enqueue paths cannot
    drift even when called concurrently.
    """
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "n1", {"code": "result = 1"})
    builder.add_node("PythonCodeNode", "n2", {"code": "result = 2"})
    workflow = builder.build()

    assert serialize_workflow_to_blob(workflow) == serialize_workflow_to_blob(workflow)
