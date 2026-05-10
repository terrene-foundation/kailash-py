# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for :class:`kailash.sdk_exceptions.MissingRunIdError`.

Covers the typed-exception contract documented in
``specs/core-runtime.md`` § audit-log emission contract:

* Subclasses :class:`~kailash.sdk_exceptions.RuntimeException` so callers
  catching the runtime-level base also catch this typed cause.
* Constructor accepts keyword-only ``node_id`` + ``workflow_id`` and
  records both as attributes for the subscriber-error handler to extract.
* Message hashes record-level identifiers via SHA-256[:8] per
  ``rules/observability.md`` Rule 8 — raw ``node_id`` / ``workflow_id``
  MUST NOT appear in the exception's ``str()``.
* Handles ``workflow_id=None`` cleanly (renders as ``"None"`` hash sentinel,
  not a hashed string of the literal ``"None"``).

Issue #876 cluster C-2a.
"""

from __future__ import annotations

import hashlib

import pytest

from kailash.sdk_exceptions import KailashException, MissingRunIdError, RuntimeException


def _hash_short(value: str) -> str:
    """Match the helper at ``history_store.py:_hash_short``."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Type hierarchy
# ---------------------------------------------------------------------------


def test_missing_run_id_error_subclasses_runtime_exception() -> None:
    """The error MUST sit under ``RuntimeException`` per
    ``kailash.sdk_exceptions``'s base-class convention so callers catching
    the runtime-level base also catch this typed cause.
    """
    assert issubclass(MissingRunIdError, RuntimeException)
    assert issubclass(MissingRunIdError, KailashException)


def test_missing_run_id_error_is_an_exception() -> None:
    """Sanity: instances are catchable as plain ``Exception``."""
    err = MissingRunIdError(node_id="n1", workflow_id="w1")
    assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Constructor + attribute exposure
# ---------------------------------------------------------------------------


def test_missing_run_id_error_records_node_id_and_workflow_id() -> None:
    """``node_id`` + ``workflow_id`` MUST be exposed as attributes so the
    subscriber-error handler can extract them and emit hashed log fields.
    """
    err = MissingRunIdError(node_id="node-42", workflow_id="wf-abc")
    assert err.node_id == "node-42"
    assert err.workflow_id == "wf-abc"


def test_missing_run_id_error_handles_none_workflow_id() -> None:
    """A ``None`` ``workflow_id`` is permitted — some runtime paths
    construct events without a workflow_id.
    """
    err = MissingRunIdError(node_id="node-1", workflow_id=None)
    assert err.node_id == "node-1"
    assert err.workflow_id is None


def test_missing_run_id_error_requires_keyword_only_args() -> None:
    """Constructor is keyword-only — callers MUST be explicit about which
    identifier is which to prevent transposition bugs.
    """
    with pytest.raises(TypeError):
        MissingRunIdError("node-1", "wf-1")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Message hashing per ``rules/observability.md`` Rule 8
# ---------------------------------------------------------------------------


def test_missing_run_id_error_message_hashes_node_id() -> None:
    """The exception message MUST NOT contain the raw ``node_id`` — it
    hashes via SHA-256[:8] so an exception surfacing in a log aggregator
    cannot reveal schema-level identifiers.
    """
    secret_node = "node-secret-correlation-id-12345"
    err = MissingRunIdError(node_id=secret_node, workflow_id="w1")
    message = str(err)
    assert secret_node not in message
    assert _hash_short(secret_node) in message


def test_missing_run_id_error_message_hashes_workflow_id() -> None:
    """Same hashing contract for ``workflow_id`` — raw value MUST NOT
    appear in the message.
    """
    secret_wf = "wf-tenant-billing-2026-q4"
    err = MissingRunIdError(node_id="n1", workflow_id=secret_wf)
    message = str(err)
    assert secret_wf not in message
    assert _hash_short(secret_wf) in message


def test_missing_run_id_error_message_renders_none_workflow_sentinel() -> None:
    """When ``workflow_id`` is ``None``, the message renders the literal
    ``workflow_id_hash=None`` sentinel — NOT a hash of the string ``"None"``
    — so the subscriber-error handler can distinguish the two cases.
    """
    err = MissingRunIdError(node_id="n1", workflow_id=None)
    message = str(err)
    assert "workflow_id_hash=None" in message


def test_missing_run_id_error_message_mentions_skipped_audit_log() -> None:
    """The message MUST name the action taken (audit-log skipped) so
    operators reading a stack trace understand the runtime invariant
    without consulting the spec.
    """
    err = MissingRunIdError(node_id="n1", workflow_id="w1")
    message = str(err)
    assert "audit-log" in message
    assert "run_id" in message
