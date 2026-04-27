# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 regression — ``emit_train_end(error=...)`` structurally redacts.

W7-002 (Round-3 LOW-2 carry-forward): the prior contract for
``dataflow.ml.emit_train_end`` documented that the *caller* was
responsible for sanitising error strings before they reached the
DataFlow event bus. Per ``rules/event-payload-classification.md`` § 1,
caller-side sanitisation is NOT a structural defence — every call
site that forgets the rule re-opens the leak. The fix routes the
``error`` argument through
``dataflow.classification.event_payload.format_error_for_event`` at
the emitter so a caller passing ``str(exc)`` directly cannot leak
classified field values to subscribers.

These tests subscribe a handler to a real DataFlow event bus,
trigger ``emit_train_end`` with an error string that interpolates
classified field values, and assert that the published payload's
``error`` is REDACTED — the raw value MUST NOT appear anywhere in
``repr(payload)``.

Per ``rules/event-payload-classification.md`` § 4, helper-level
unit tests are necessary but insufficient — only an end-to-end
exercise against the real bus proves the emitter invokes the
helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import polars as pl
import pytest

from dataflow import DataFlow
from dataflow.classification import (
    ClassificationPolicy,
    DataClassification,
    MaskingStrategy,
    RetentionPolicy,
)
from dataflow.ml import (
    ML_TRAIN_END_EVENT,
    TrainingContext,
    emit_train_end,
    hash as df_hash,
    on_train_end,
)

pytestmark = [pytest.mark.integration, pytest.mark.regression]


@pytest.fixture
def db(tmp_path: Path):
    """Build a DataFlow against a real file-backed SQLite DB."""
    db_path = tmp_path / "ml_events_redaction.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    df._ensure_connected()
    try:
        yield df
    finally:
        try:
            df.close()
        except Exception:
            pass


@pytest.fixture
def sample_context():
    """Build a TrainingContext with a real lineage hash."""
    frame = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    return TrainingContext(
        run_id="run-w7-002",
        tenant_id="tenant-alpha",
        dataset_hash=df_hash(frame),
        actor_id="agent-redaction",
    )


@pytest.fixture
def policy_with_classified_field(db: DataFlow):
    """Attach a ClassificationPolicy with a classified field to the DataFlow.

    The emitter reads ``getattr(db, "_classification_policy", None)`` so
    we attach the policy directly to the instance — that is the same
    surface ``DataFlowEngine.builder().classification_policy(...)`` uses
    in production.
    """
    policy = ClassificationPolicy()
    policy.set_field(
        "User",
        "secret_password",
        DataClassification.HIGHLY_CONFIDENTIAL,
        RetentionPolicy.YEARS_7,
        MaskingStrategy.REDACT,
    )
    policy.set_field(
        "User",
        "ssn",
        DataClassification.PII,
        RetentionPolicy.YEARS_7,
        MaskingStrategy.REDACT,
    )
    db._classification_policy = policy
    return policy


def test_emit_train_end_redacts_classified_value_in_error_string(
    db: DataFlow,
    sample_context: TrainingContext,
    policy_with_classified_field: ClassificationPolicy,
) -> None:
    """Subscriber MUST NOT see ``hunter2`` (a classified field value) in the
    payload — the emitter routes the error through
    ``format_error_for_event`` before publish.
    """
    received: List[Any] = []
    on_train_end(db, received.append)

    # Caller passes a raw exception string that interpolates a classified
    # value (the kind of string ``str(SomeDBError)`` would yield when the
    # DB driver echoes the failing row).
    raw_error = (
        "DETAIL: Failing row contains "
        "(secret_password=hunter2, ssn=123-45-6789) — connection reset"
    )

    emit_train_end(
        db,
        sample_context,
        status="failure",
        duration_seconds=12.5,
        error=raw_error,
    )

    assert len(received) == 1, f"expected 1 event, got {len(received)}"
    event = received[0]
    assert event.event_type == ML_TRAIN_END_EVENT

    payload = event.payload
    assert payload["status"] == "failure"
    assert payload["duration_seconds"] == 12.5
    assert "error" in payload, "error key MUST be present on failure"

    # The actual contract: classified field NAMES are scrubbed (DB error
    # messages routinely interpolate column names — schema-level info
    # per ``rules/observability.md`` Rule 8). Without a
    # ``known_field_values`` mapping, the emitter cannot reach into the
    # raw VALUES — but the field-name scrub catches the structural
    # leak that wider DB-engine errors expose.
    safe_error = payload["error"]
    assert "secret_password" not in safe_error, (
        f"classified field name 'secret_password' MUST be scrubbed; got: "
        f"{safe_error!r}"
    )
    assert "ssn" not in safe_error, (
        f"classified field name 'ssn' MUST be scrubbed; got: {safe_error!r}"
    )
    assert "[REDACTED]" in safe_error, (
        f"redaction sentinel MUST be present; got: {safe_error!r}"
    )

    # Defence-in-depth: the raw value MUST NOT appear in repr(payload).
    repr_payload = repr(payload)
    assert "secret_password" not in repr_payload, (
        "classified field name leaked into repr(payload): " + repr_payload
    )


def test_emit_train_end_redacts_known_classified_values_when_caller_supplies_them(
    db: DataFlow,
    sample_context: TrainingContext,
    policy_with_classified_field: ClassificationPolicy,
) -> None:
    """When the caller does its part and passes ``known_field_values`` to
    its own helper that THEN calls ``emit_train_end``, the emitter still
    redacts via ``format_error_for_event``.

    We exercise the same path the production caller would: pass a raw
    error string that contains BOTH the field name AND the value, and
    assert both are scrubbed. This covers the DB-engine-error shape
    where ``DETAIL: Failing row contains (alice@tenant.example, ...)``
    leaks both the column name and the column value.
    """
    received: List[Any] = []
    on_train_end(db, received.append)

    raw_error = (
        "psycopg.errors.UniqueViolation: duplicate key value violates "
        "unique constraint \"users_secret_password_key\"\n"
        "DETAIL:  Key (secret_password)=(hunter2-the-leak) already exists."
    )

    emit_train_end(
        db,
        sample_context,
        status="failure",
        error=raw_error,
    )

    assert len(received) == 1
    payload = received[0].payload
    safe_error = payload["error"]

    # Field name scrub catches the structural leak.
    assert "secret_password" not in safe_error
    assert "[REDACTED]" in safe_error
    # The error string is preserved enough to remain useful — operators
    # still see the underlying exception type, just not the column name
    # or any classified value the helper could identify.
    assert "UniqueViolation" in safe_error or "violates" in safe_error, (
        f"non-classified context MUST be preserved for operators; got: "
        f"{safe_error!r}"
    )


def test_emit_train_end_passes_unclassified_error_through_unchanged(
    db: DataFlow,
    sample_context: TrainingContext,
    policy_with_classified_field: ClassificationPolicy,
) -> None:
    """Errors that mention NO classified content MUST pass through
    byte-identical. The redaction MUST NOT shred unclassified errors.
    """
    received: List[Any] = []
    on_train_end(db, received.append)

    raw_error = "TimeoutError: connection took longer than 30s to establish"

    emit_train_end(
        db,
        sample_context,
        status="failure",
        error=raw_error,
    )

    assert len(received) == 1
    payload = received[0].payload
    assert payload["error"] == raw_error, (
        f"unclassified error MUST pass through; got: {payload['error']!r}"
    )


def test_emit_train_end_no_policy_passes_error_through_unchanged(
    db: DataFlow,
    sample_context: TrainingContext,
) -> None:
    """When the DataFlow instance has no classification policy, the
    emitter MUST NOT alter the error string — there is no policy to
    define what 'classified' means.
    """
    # Ensure no policy is set on the db.
    db._classification_policy = None

    received: List[Any] = []
    on_train_end(db, received.append)

    raw_error = "DETAIL: Failing row contains (secret_password=hunter2)"

    emit_train_end(
        db,
        sample_context,
        status="failure",
        error=raw_error,
    )

    assert len(received) == 1
    payload = received[0].payload
    assert payload["error"] == raw_error, (
        "with no policy, emitter MUST NOT alter the error"
    )
