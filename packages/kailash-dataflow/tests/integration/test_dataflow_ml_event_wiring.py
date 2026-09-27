# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring — ``on_train_start`` / ``on_train_end`` event subscribers.

Per ``rules/event-payload-classification.md`` § 4, every event-emitting
primitive MUST have a Tier 2 integration test that subscribes a handler
through the facade, triggers the emission, and asserts the payload
shape end-to-end against a real DataFlow instance (real SQLite, real
event bus).

This test verifies:

* ``dataflow.ml.on_train_start`` / ``on_train_end`` register subscribers
  that receive the exact payload kailash-ml will emit.
* The ``dataset_hash`` in the payload is routed through
  ``format_record_id_for_event`` so the event surface stays uniform
  with DataFlow's write-event classification contract.
* ``TrainingContext`` fields (``run_id``, ``tenant_id``, ``actor_id``,
  ``dataset_hash``) are preserved verbatim in the payload.
* Multiple subscribers receive the event (pub/sub semantics).
* Subscribing to ``train_end`` does NOT fire when ``train_start`` is
  emitted — event types are strictly separated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import polars as pl
import pytest

from dataflow import DataFlow
from dataflow.ml import (
    ML_TRAIN_END_EVENT,
    ML_TRAIN_START_EVENT,
    TrainingContext,
    emit_train_end,
    emit_train_start,
    hash as df_hash,
    on_train_end,
    on_train_start,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def db(tmp_path: Path):
    """Build a DataFlow against a real file-backed SQLite DB."""
    db_path = tmp_path / "ml_events.sqlite"
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
        run_id="run-42",
        tenant_id="tenant-alpha",
        dataset_hash=df_hash(frame),
        actor_id="agent-9",
    )


def test_on_train_start_receives_emitted_event(db: DataFlow, sample_context):
    """Subscriber registered via on_train_start gets the exact event payload."""
    received: List[Any] = []

    on_train_start(db, received.append)

    emit_train_start(
        db,
        sample_context,
        model_name="churn_v3",
        engine="sklearn",
    )

    assert len(received) == 1, f"expected 1 event, got {len(received)}"
    event = received[0]
    assert event.event_type == ML_TRAIN_START_EVENT

    payload = event.payload
    assert payload["event"] == ML_TRAIN_START_EVENT
    assert payload["run_id"] == "run-42"
    assert payload["tenant_id"] == "tenant-alpha"
    assert payload["actor_id"] == "agent-9"
    assert payload["dataset_hash"] == sample_context.dataset_hash
    assert payload["model_name"] == "churn_v3"
    assert payload["engine"] == "sklearn"


def test_on_train_end_receives_emitted_event(db: DataFlow, sample_context):
    """Subscriber via on_train_end gets the exact end-of-run payload."""
    received: List[Any] = []

    on_train_end(db, received.append)

    emit_train_end(
        db,
        sample_context,
        status="success",
        duration_seconds=12.34,
    )

    assert len(received) == 1
    event = received[0]
    assert event.event_type == ML_TRAIN_END_EVENT

    payload = event.payload
    assert payload["status"] == "success"
    assert payload["duration_seconds"] == 12.34
    assert payload["run_id"] == "run-42"
    assert payload["dataset_hash"] == sample_context.dataset_hash


def test_train_start_payload_record_id_hashed_like_write_events(
    db: DataFlow, sample_context
):
    """rules/event-payload-classification.md § 1 — record_id routes through
    format_record_id_for_event so train events follow the same classification
    contract as DataFlow write events."""
    received: List[Any] = []
    on_train_start(db, received.append)

    emit_train_start(db, sample_context)

    assert len(received) == 1
    payload = received[0].payload
    # record_id field must be present — DataFlow's write-event contract.
    assert "record_id" in payload
    # For the train event, we use the dataset_hash as the input to
    # format_record_id_for_event. The dataset_hash is already a
    # "sha256:..." string; the helper treats it as an unclassified
    # string PK and passes it through as str(value).
    assert payload["record_id"] == sample_context.dataset_hash


def test_train_start_does_not_fire_train_end_subscribers(db: DataFlow, sample_context):
    """Strict event-type separation — subscribing to end does NOT see start."""
    start_events: List[Any] = []
    end_events: List[Any] = []

    on_train_start(db, start_events.append)
    on_train_end(db, end_events.append)

    emit_train_start(db, sample_context)

    assert len(start_events) == 1
    assert len(end_events) == 0


def test_multiple_subscribers_each_receive_train_start(db: DataFlow, sample_context):
    """Pub/sub semantics — two subscribers, two delivered copies."""
    a_received: List[Any] = []
    b_received: List[Any] = []

    on_train_start(db, a_received.append)
    on_train_start(db, b_received.append)

    emit_train_start(db, sample_context)

    assert len(a_received) == 1
    assert len(b_received) == 1
    assert a_received[0].payload == b_received[0].payload


def test_train_end_failure_status_emits_warn_level_payload(
    db: DataFlow, sample_context
):
    """status='failure' still emits; subscriber sees the error field."""
    received: List[Any] = []
    on_train_end(db, received.append)

    emit_train_end(
        db,
        sample_context,
        status="failure",
        duration_seconds=0.5,
        error="convergence failed after 100 iterations",
    )

    assert len(received) == 1
    payload = received[0].payload
    assert payload["status"] == "failure"
    assert payload["error"] == "convergence failed after 100 iterations"


def test_on_train_start_returns_subscription_ids(db: DataFlow):
    """Subscriber registration returns at least one subscription id (shape
    matches DataFlow.on_model_change for uniform sub/unsub handling)."""
    sub_ids = on_train_start(db, lambda evt: None)
    assert isinstance(sub_ids, list)
    assert len(sub_ids) == 1
    assert sub_ids[0]  # non-empty id


def test_train_event_type_names_match_public_constants(db: DataFlow, sample_context):
    """Emitted event_type strings match the module-level constants."""
    received: List[Any] = []
    on_train_start(db, received.append)
    on_train_end(db, received.append)

    emit_train_start(db, sample_context)
    emit_train_end(db, sample_context, status="success")

    assert [e.event_type for e in received] == [
        ML_TRAIN_START_EVENT,
        ML_TRAIN_END_EVENT,
    ]
    assert ML_TRAIN_START_EVENT == "kailash_ml.train.start"
    assert ML_TRAIN_END_EVENT == "kailash_ml.train.end"


def test_train_payload_never_contains_raw_non_fingerprint_record_id(
    db: DataFlow, sample_context
):
    """Sanity — payload's record_id is the fingerprint (already sha256:...),
    never something else that could leak."""
    received: List[Any] = []
    on_train_start(db, received.append)

    emit_train_start(db, sample_context)
    payload = received[0].payload

    # The payload MUST NOT leak any un-fingerprinted opaque IDs disguised
    # as record_id; we use dataset_hash (already a fingerprint).
    assert isinstance(payload["record_id"], str)
    assert payload["record_id"].startswith("sha256:")
