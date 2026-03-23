# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for EATP audit record translator.

Covers:
- Translation mapping for each L3EventType
- Severity classification
- Bounded deque eviction
- Thread safety of handle_event
- NaN/Inf in event details does not corrupt records
- Filtering by agent and event type
- Integration with L3EventBus
"""

from __future__ import annotations

import math
import threading

import pytest

from kaizen.l3.eatp_translator import EatpTranslator, _SEVERITY_MAP, _DEFAULT_SEVERITY
from kaizen.l3.event_hooks import L3EventBus
from kaizen.l3.events import L3Event, L3EventType


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_event(
    event_type: str = "agent_spawned",
    agent_id: str = "agent-001",
    details: dict | None = None,
) -> L3Event:
    return L3Event(
        event_type=event_type,
        agent_id=agent_id,
        timestamp="2026-03-23T12:00:00+00:00",
        details=details or {},
    )


# ---------------------------------------------------------------------------
# EatpTranslator basic tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorBasic:
    """Core translation logic."""

    def test_translate_mapping(self):
        translator = EatpTranslator()
        event = _make_event(
            event_type="agent_spawned",
            agent_id="agent-001",
            details={"spec_id": "researcher"},
        )
        record = translator.translate(event)

        assert record["action_type"] == "agent_spawned"
        assert record["subject_id"] == "agent-001"
        assert record["recorded_at"] == "2026-03-23T12:00:00+00:00"
        assert record["context"] == {"spec_id": "researcher"}
        assert record["source"] == "l3_event_bus"
        assert "record_id" in record

    def test_translate_returns_unique_record_ids(self):
        translator = EatpTranslator()
        event = _make_event()
        r1 = translator.translate(event)
        r2 = translator.translate(event)
        assert r1["record_id"] != r2["record_id"]

    def test_handle_event_stores_record(self):
        translator = EatpTranslator()
        event = _make_event()
        translator.handle_event(event)

        records = translator.get_records()
        assert len(records) == 1
        assert records[0]["action_type"] == "agent_spawned"

    def test_get_records_returns_copy(self):
        """Modifying the returned list must not affect internal state."""
        translator = EatpTranslator()
        translator.handle_event(_make_event())

        records = translator.get_records()
        records.clear()
        assert translator.record_count == 1

    def test_record_count(self):
        translator = EatpTranslator()
        assert translator.record_count == 0
        translator.handle_event(_make_event())
        assert translator.record_count == 1

    def test_clear(self):
        translator = EatpTranslator()
        translator.handle_event(_make_event())
        translator.clear()
        assert translator.record_count == 0

    def test_invalid_max_records(self):
        with pytest.raises(ValueError, match="max_records must be >= 1"):
            EatpTranslator(max_records=0)

        with pytest.raises(ValueError, match="max_records must be >= 1"):
            EatpTranslator(max_records=-5)


# ---------------------------------------------------------------------------
# Severity classification tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorSeverity:
    """Verify severity mapping for all event types."""

    def test_high_severity_events(self):
        translator = EatpTranslator()
        for event_type in ["envelope_violation", "context_access_denied"]:
            record = translator.translate(_make_event(event_type=event_type))
            assert record["severity"] == "high", f"{event_type} should be high severity"

    def test_medium_severity_events(self):
        translator = EatpTranslator()
        for event_type in [
            "agent_terminated",
            "message_dead_lettered",
            "plan_node_failed",
            "plan_node_held",
        ]:
            record = translator.translate(_make_event(event_type=event_type))
            assert (
                record["severity"] == "medium"
            ), f"{event_type} should be medium severity"

    def test_low_severity_events(self):
        translator = EatpTranslator()
        for event_type in [
            "envelope_registered",
            "envelope_split",
            "agent_spawned",
            "agent_state_changed",
            "message_routed",
            "plan_validated",
            "plan_executed",
            "plan_node_completed",
            "context_scope_created",
        ]:
            record = translator.translate(_make_event(event_type=event_type))
            assert record["severity"] == "low", f"{event_type} should be low severity"

    def test_all_event_types_have_severity(self):
        """Every L3EventType must translate to a valid severity."""
        translator = EatpTranslator()
        valid_severities = {"low", "medium", "high"}
        for et in L3EventType:
            record = translator.translate(_make_event(event_type=et.value))
            assert (
                record["severity"] in valid_severities
            ), f"Event type {et.value} has invalid severity: {record['severity']}"


# ---------------------------------------------------------------------------
# Per-event-type translation tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorPerEventType:
    """Each L3EventType translates correctly."""

    @pytest.mark.parametrize("event_type", list(L3EventType))
    def test_translates_event_type(self, event_type: L3EventType):
        translator = EatpTranslator()
        event = L3Event.create(event_type, "agent-test", {"key": "value"})
        record = translator.translate(event)

        assert record["action_type"] == event_type.value
        assert record["subject_id"] == "agent-test"
        assert record["context"] == {"key": "value"}
        assert record["source"] == "l3_event_bus"
        assert record["record_id"]  # non-empty
        assert record["recorded_at"]  # non-empty


# ---------------------------------------------------------------------------
# Bounded collection tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorBounded:
    """Bounded deque eviction behavior."""

    def test_eviction_at_max(self):
        translator = EatpTranslator(max_records=5)
        for i in range(10):
            translator.handle_event(_make_event(agent_id=f"agent-{i:03d}"))

        assert translator.record_count == 5
        records = translator.get_records()
        # Oldest records (agent-000 through agent-004) should have been evicted
        agent_ids = [r["subject_id"] for r in records]
        assert agent_ids == [f"agent-{i:03d}" for i in range(5, 10)]

    def test_max_records_1(self):
        translator = EatpTranslator(max_records=1)
        translator.handle_event(_make_event(agent_id="first"))
        translator.handle_event(_make_event(agent_id="second"))

        assert translator.record_count == 1
        assert translator.get_records()[0]["subject_id"] == "second"

    def test_default_max_records(self):
        translator = EatpTranslator()
        # Default is 10,000 — just verify it's set
        assert translator._max_records == 10_000


# ---------------------------------------------------------------------------
# NaN/Inf in details tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorNanInf:
    """NaN/Inf in event details must not corrupt audit records."""

    def test_nan_in_details_sanitized_before_translation(self):
        """NaN is sanitized at L3Event creation time, so it never reaches the translator."""
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"cost": float("nan")},
        )
        translator = EatpTranslator()
        record = translator.translate(event)
        # The context should contain the sanitized sentinel, not a float NaN
        assert isinstance(record["context"]["cost"], str)
        assert "non-finite" in record["context"]["cost"]

    def test_inf_in_details_sanitized_before_translation(self):
        event = L3Event(
            event_type="envelope_violation",
            agent_id="agent-001",
            timestamp="2026-03-23T12:00:00+00:00",
            details={"cost": float("inf")},
        )
        translator = EatpTranslator()
        record = translator.translate(event)
        assert isinstance(record["context"]["cost"], str)
        assert "non-finite" in record["context"]["cost"]

    def test_normal_floats_preserved(self):
        event = _make_event(details={"cost": 42.5, "limit": 100.0})
        translator = EatpTranslator()
        record = translator.translate(event)
        assert record["context"]["cost"] == 42.5
        assert record["context"]["limit"] == 100.0


# ---------------------------------------------------------------------------
# Filtering tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorFiltering:
    """Filter records by agent and event type."""

    def test_get_records_by_agent(self):
        translator = EatpTranslator()
        translator.handle_event(_make_event(agent_id="agent-001"))
        translator.handle_event(_make_event(agent_id="agent-002"))
        translator.handle_event(_make_event(agent_id="agent-001"))

        records = translator.get_records_by_agent("agent-001")
        assert len(records) == 2
        assert all(r["subject_id"] == "agent-001" for r in records)

    def test_get_records_by_agent_empty(self):
        translator = EatpTranslator()
        translator.handle_event(_make_event(agent_id="agent-001"))
        assert translator.get_records_by_agent("nonexistent") == []

    def test_get_records_by_type_string(self):
        translator = EatpTranslator()
        translator.handle_event(_make_event(event_type="agent_spawned"))
        translator.handle_event(_make_event(event_type="envelope_violation"))
        translator.handle_event(_make_event(event_type="agent_spawned"))

        records = translator.get_records_by_type("agent_spawned")
        assert len(records) == 2
        assert all(r["action_type"] == "agent_spawned" for r in records)

    def test_get_records_by_type_enum(self):
        translator = EatpTranslator()
        translator.handle_event(_make_event(event_type="agent_spawned"))
        translator.handle_event(_make_event(event_type="envelope_violation"))

        records = translator.get_records_by_type(L3EventType.ENVELOPE_VIOLATION)
        assert len(records) == 1
        assert records[0]["action_type"] == "envelope_violation"


# ---------------------------------------------------------------------------
# Thread safety tests
# ---------------------------------------------------------------------------


class TestEatpTranslatorThreadSafety:
    """Concurrent handle_event calls must not corrupt state."""

    def test_concurrent_handle_event(self):
        translator = EatpTranslator()
        events_per_thread = 100
        num_threads = 10
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(events_per_thread):
                    translator.handle_event(
                        _make_event(agent_id=f"thread-{thread_id}-{i}")
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert translator.record_count == num_threads * events_per_thread

    def test_concurrent_handle_and_read(self):
        """Reading while writing must not raise."""
        translator = EatpTranslator()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(200):
                    translator.handle_event(_make_event(agent_id=f"w-{i}"))
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(200):
                    translator.get_records()
                    translator.get_records_by_agent("w-0")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ---------------------------------------------------------------------------
# Integration with L3EventBus
# ---------------------------------------------------------------------------


class TestEatpTranslatorBusIntegration:
    """EatpTranslator works end-to-end with L3EventBus."""

    def test_subscribe_all_captures_events(self):
        bus = L3EventBus()
        translator = EatpTranslator()
        bus.subscribe_all(translator.handle_event)

        bus.emit(L3Event.create(L3EventType.AGENT_SPAWNED, "agent-001"))
        bus.emit(L3Event.create(L3EventType.ENVELOPE_VIOLATION, "agent-002"))
        bus.emit(L3Event.create(L3EventType.PLAN_EXECUTED, "agent-001"))

        records = translator.get_records()
        assert len(records) == 3
        assert records[0]["action_type"] == "agent_spawned"
        assert records[1]["action_type"] == "envelope_violation"
        assert records[2]["action_type"] == "plan_executed"

    def test_subscribe_specific_type(self):
        bus = L3EventBus()
        translator = EatpTranslator()
        bus.subscribe(L3EventType.ENVELOPE_VIOLATION, translator.handle_event)

        bus.emit(L3Event.create(L3EventType.AGENT_SPAWNED, "agent-001"))
        bus.emit(L3Event.create(L3EventType.ENVELOPE_VIOLATION, "agent-002"))

        records = translator.get_records()
        assert len(records) == 1
        assert records[0]["action_type"] == "envelope_violation"
