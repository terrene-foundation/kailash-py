# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for event-payload classification hygiene.

Issue #491 — DataFlowExpress ``_emit_write_event`` leaked the raw PK
value into the ``DomainEvent`` payload. For a model keyed by a classified
string (e.g. ``Account`` keyed by ``email`` with ``@classify("email",
PII)``), every ``create`` / ``update`` / ``upsert`` / ``delete`` event
shipped ``record_id: "alice@tenant.example"`` to every subscriber,
tracing span, observability vendor, and downstream microservice.

The fix routes ``record_id`` through
``dataflow.classification.event_payload.format_record_id_for_event``
before emission. Integer PKs and unclassified string PKs pass through;
classified string PKs are hashed to ``"sha256:XXXXXXXX"``.

These tests pin the contract — each exercise ``_emit_write_event``
indirectly via ``db.express.create/update/upsert/delete`` with a real
subscribed handler and assert the payload shape.

Cross-SDK: the same hash prefix / hex-length is used in kailash-rs
v3.17.1 (``format_record_id_for_event`` helper, BP-048). A sha256
digest of the same raw value produces the same prefix across SDKs,
so log + event correlation across polyglot deployments works.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from dataflow import DataFlow
from dataflow.classification import (
    DataClassification,
    MaskingStrategy,
    classify,
)

from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with real PostgreSQL."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_model_name() -> str:
    """Unique DataFlow model name per test — avoids registry collisions."""
    return f"Evt{uuid.uuid4().hex[:10]}"


def _make_db_with_int_pk_model(db_url: str, model_name: str) -> DataFlow:
    """Model keyed by integer ``id`` (the Kailash convention).

    Integer PKs are safe by type — the helper MUST pass them through as
    ``str(value)``, NOT hash them.
    """
    db = DataFlow(db_url, auto_migrate=True, pool_size=2, max_overflow=2)
    cls = type(
        model_name,
        (),
        {
            "__annotations__": {"id": int, "label": str},
            "id": 0,
            "label": "",
        },
    )
    db.model(cls)
    return db


def _make_db_with_classified_string_pk(db_url: str, model_name: str) -> DataFlow:
    """Model whose PK (``id``) is a classified string.

    This is the exact leak shape documented in #491: a model keyed by a
    classified field (e.g. ``Account`` keyed by ``email`` with
    ``@classify("email", PII)``). The ``id`` field itself is classified
    here to stay within the Kailash DataFlow "PK must be named id"
    convention while still modelling the classified-PK scenario.
    """
    db = DataFlow(db_url, auto_migrate=True, pool_size=2, max_overflow=2)
    cls = type(
        model_name,
        (),
        {
            "__annotations__": {"id": str, "label": str},
            "id": "",
            "label": "",
        },
    )
    cls = classify("id", DataClassification.PII, masking=MaskingStrategy.REDACT)(cls)
    db.model(cls)
    return db


def _make_db_with_unclassified_string_pk(db_url: str, model_name: str) -> DataFlow:
    """Model keyed by an unclassified string ``id``."""
    db = DataFlow(db_url, auto_migrate=True, pool_size=2, max_overflow=2)
    cls = type(
        model_name,
        (),
        {
            "__annotations__": {"id": str, "label": str},
            "id": "",
            "label": "",
        },
    )
    db.model(cls)
    return db


# ---------------------------------------------------------------------------
# Tests — format_record_id_for_event direct contract
# ---------------------------------------------------------------------------


def test_helper_passes_none_through():
    """``format_record_id_for_event(None)`` returns ``None``."""
    from dataflow.classification.event_payload import format_record_id_for_event
    from dataflow.classification.policy import ClassificationPolicy

    assert format_record_id_for_event(ClassificationPolicy(), "M", None) is None


def test_helper_passes_integer_through_as_string():
    """Integer PKs pass through as ``str(value)``, never hashed."""
    from dataflow.classification.event_payload import format_record_id_for_event
    from dataflow.classification.policy import ClassificationPolicy

    policy = ClassificationPolicy()
    assert format_record_id_for_event(policy, "M", 42) == "42"
    assert format_record_id_for_event(policy, "M", 0) == "0"
    # Even with no policy at all — still pass through.
    assert format_record_id_for_event(None, "M", 999) == "999"


def test_helper_passes_unclassified_string_pk_through():
    """Unclassified string PKs pass through unchanged."""
    from dataflow.classification.event_payload import format_record_id_for_event
    from dataflow.classification.policy import ClassificationPolicy

    policy = ClassificationPolicy()  # empty — no fields classified
    assert format_record_id_for_event(policy, "M", "user-1") == "user-1"
    assert format_record_id_for_event(policy, "M", "abc-123-def") == "abc-123-def"


def test_helper_hashes_classified_string_pk():
    """Classified string PKs are hashed to ``sha256:XXXXXXXX``."""
    from dataflow.classification.event_payload import format_record_id_for_event
    from dataflow.classification.policy import ClassificationPolicy

    policy = ClassificationPolicy()
    policy.set_field(
        "Account",
        "id",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    result = format_record_id_for_event(policy, "Account", "alice@tenant.example")
    expected = hashlib.sha256(b"alice@tenant.example").hexdigest()[:8]
    assert result == f"sha256:{expected}"
    # Stable across calls — forensic correlation works.
    assert result == format_record_id_for_event(
        policy, "Account", "alice@tenant.example"
    )
    # Different values produce different hashes.
    other = format_record_id_for_event(policy, "Account", "bob@tenant.example")
    assert other != result


def test_helper_hashes_only_for_classified_model():
    """A classified PK on model A does NOT cause hashing on model B."""
    from dataflow.classification.event_payload import format_record_id_for_event
    from dataflow.classification.policy import ClassificationPolicy

    policy = ClassificationPolicy()
    policy.set_field(
        "Account",
        "id",
        DataClassification.PII,
        masking=MaskingStrategy.REDACT,
    )
    # Same raw value, different model — passes through on unclassified model.
    assert (
        format_record_id_for_event(policy, "User", "alice@tenant.example")
        == "alice@tenant.example"
    )


# ---------------------------------------------------------------------------
# Tests — end-to-end via DataFlow.express → _emit_write_event
# ---------------------------------------------------------------------------


async def test_create_event_with_integer_pk_uses_str_passthrough(
    test_suite, unique_model_name
):
    """Integer-PK model: event payload ``record_id`` is ``str(int)``."""
    db = _make_db_with_int_pk_model(test_suite.config.url, unique_model_name)
    received = []
    try:
        await db.initialize()
        db.on_model_change(unique_model_name, lambda evt: received.append(evt))
        created = await db.express.create(unique_model_name, {"label": "hello"})
        assert created is not None
        # Find the create event for this model.
        creates = [
            e for e in received if e.event_type.endswith(f".{unique_model_name}.create")
        ]
        assert len(creates) == 1
        record_id = creates[0].payload["record_id"]
        assert record_id is not None
        # Integer passed through as string (e.g. "1", "2", ...).
        assert record_id.isdigit(), (
            f"Integer PK MUST pass through as canonical digit string, "
            f"got {record_id!r}"
        )
    finally:
        db.close()


async def test_create_event_with_unclassified_string_pk_passes_through(
    test_suite, unique_model_name
):
    """Unclassified string PK: event payload carries the raw value."""
    db = _make_db_with_unclassified_string_pk(test_suite.config.url, unique_model_name)
    received = []
    try:
        await db.initialize()
        db.on_model_change(unique_model_name, lambda evt: received.append(evt))
        raw_pk = f"rec-{uuid.uuid4().hex[:8]}"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "ok"})
        creates = [
            e for e in received if e.event_type.endswith(f".{unique_model_name}.create")
        ]
        assert len(creates) == 1
        assert (
            creates[0].payload["record_id"] == raw_pk
        ), "Unclassified string PK MUST pass through raw — no hashing applied."
    finally:
        db.close()


async def test_create_event_with_classified_string_pk_is_hashed(
    test_suite, unique_model_name
):
    """Classified string PK: event payload carries ``sha256:XXXXXXXX``.

    This is the exact leak documented in #491. Before the fix, the raw
    PK (e.g. ``alice@tenant.example``) shipped to every subscriber.
    """
    db = _make_db_with_classified_string_pk(test_suite.config.url, unique_model_name)
    received = []
    try:
        await db.initialize()
        db.on_model_change(unique_model_name, lambda evt: received.append(evt))
        raw_pk = f"alice-{uuid.uuid4().hex[:8]}@tenant.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "hi"})
        creates = [
            e for e in received if e.event_type.endswith(f".{unique_model_name}.create")
        ]
        assert len(creates) == 1
        record_id = creates[0].payload["record_id"]
        assert record_id is not None
        assert record_id.startswith("sha256:"), (
            f"Classified string PK MUST be hashed, got raw value {record_id!r} — "
            "this is the #491 leak."
        )
        assert (
            len(record_id) == len("sha256:") + 8
        ), f"Hash prefix MUST be 8 hex chars, got len {len(record_id)}: {record_id!r}"
        # Verify the hash matches what the helper would produce.
        expected = hashlib.sha256(raw_pk.encode()).hexdigest()[:8]
        assert record_id == f"sha256:{expected}"
        # Raw value MUST NOT appear anywhere in the payload.
        payload_repr = repr(creates[0].payload)
        assert raw_pk not in payload_repr, (
            f"Raw classified PK MUST NOT appear anywhere in payload; "
            f"found {raw_pk!r} inside {payload_repr!r}"
        )
    finally:
        db.close()


async def test_update_event_with_classified_string_pk_is_hashed(
    test_suite, unique_model_name
):
    """update events on a classified-PK model hash the PK."""
    db = _make_db_with_classified_string_pk(test_suite.config.url, unique_model_name)
    received = []
    try:
        await db.initialize()
        raw_pk = f"bob-{uuid.uuid4().hex[:8]}@tenant.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "v1"})
        # Subscribe AFTER the create so we only capture the update.
        db.on_model_change(unique_model_name, lambda evt: received.append(evt))
        await db.express.update(unique_model_name, raw_pk, {"label": "v2"})
        updates = [
            e for e in received if e.event_type.endswith(f".{unique_model_name}.update")
        ]
        assert len(updates) == 1
        record_id = updates[0].payload["record_id"]
        assert record_id.startswith("sha256:")
        assert raw_pk not in repr(updates[0].payload)
    finally:
        db.close()


async def test_delete_event_with_classified_string_pk_is_hashed(
    test_suite, unique_model_name
):
    """delete events on a classified-PK model hash the PK."""
    db = _make_db_with_classified_string_pk(test_suite.config.url, unique_model_name)
    received = []
    try:
        await db.initialize()
        raw_pk = f"charlie-{uuid.uuid4().hex[:8]}@tenant.example"
        await db.express.create(unique_model_name, {"id": raw_pk, "label": "x"})
        db.on_model_change(unique_model_name, lambda evt: received.append(evt))
        await db.express.delete(unique_model_name, raw_pk)
        deletes = [
            e for e in received if e.event_type.endswith(f".{unique_model_name}.delete")
        ]
        assert len(deletes) == 1
        record_id = deletes[0].payload["record_id"]
        assert record_id.startswith("sha256:")
        assert raw_pk not in repr(deletes[0].payload)
    finally:
        db.close()
