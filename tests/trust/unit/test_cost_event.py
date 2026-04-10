# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for CostEvent and CostDeduplicator (SPEC-08).

Covers:
- CostEvent frozen immutability
- Source validation (known and unknown sources)
- Numeric field validation (NaN, Inf, negative)
- Serialization round-trip (to_dict / from_dict)
- CostDeduplicator duplicate detection
- CostDeduplicator bounded capacity (LRU eviction)
- CostEvent.create factory method
"""

from __future__ import annotations

import math

import pytest

from kailash.trust.cost_event import (
    CostDeduplicator,
    CostEvent,
    CostEventError,
    DuplicateCostError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cost_event(**overrides) -> CostEvent:
    defaults = {
        "cost_id": "cost-001",
        "call_id": "call-abc-123",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "source": "openai",
        "model": "gpt-4",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_microdollars": 1500,
    }
    defaults.update(overrides)
    return CostEvent(**defaults)


# ---------------------------------------------------------------------------
# CostEvent frozen semantics
# ---------------------------------------------------------------------------


class TestCostEventFrozen:
    """CostEvent must be immutable (frozen=True)."""

    def test_cannot_set_attribute(self):
        event = _make_cost_event()
        with pytest.raises(AttributeError):
            event.source = "anthropic"  # type: ignore[misc]

    def test_cannot_delete_attribute(self):
        event = _make_cost_event()
        with pytest.raises(AttributeError):
            del event.source  # type: ignore[misc]

    def test_all_fields_accessible(self):
        event = _make_cost_event(
            agent_id="agent-1",
            workflow_id="wf-1",
            metadata={"key": "val"},
        )
        assert event.cost_id == "cost-001"
        assert event.call_id == "call-abc-123"
        assert event.source == "openai"
        assert event.model == "gpt-4"
        assert event.input_tokens == 100
        assert event.output_tokens == 50
        assert event.cost_microdollars == 1500
        assert event.agent_id == "agent-1"
        assert event.workflow_id == "wf-1"
        assert event.metadata == {"key": "val"}

    def test_default_optional_fields(self):
        event = _make_cost_event()
        assert event.agent_id is None
        assert event.workflow_id is None
        assert event.metadata == {}


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------


class TestCostEventSourceValidation:
    """Source field validation."""

    def test_known_sources_accepted(self):
        for source in [
            "openai",
            "anthropic",
            "google",
            "deepseek",
            "mistral",
            "local",
            "test",
        ]:
            event = _make_cost_event(source=source)
            assert event.source == source

    def test_unknown_source_accepted_with_warning(self):
        """Unknown sources are accepted but should log a warning."""
        event = _make_cost_event(source="custom_provider")
        assert event.source == "custom_provider"

    def test_empty_source_rejected(self):
        with pytest.raises(CostEventError, match="non-empty string"):
            _make_cost_event(source="")

    def test_none_source_rejected(self):
        with pytest.raises(CostEventError):
            CostEvent(
                cost_id="c1",
                call_id="x",
                timestamp="2026-01-01T00:00:00+00:00",
                source=None,  # type: ignore[arg-type]
                model="m",
                input_tokens=0,
                output_tokens=0,
                cost_microdollars=0,
            )


# ---------------------------------------------------------------------------
# call_id validation
# ---------------------------------------------------------------------------


class TestCostEventCallIdValidation:
    """call_id must be non-empty."""

    def test_empty_call_id_rejected(self):
        with pytest.raises(CostEventError, match="non-empty string"):
            _make_cost_event(call_id="")

    def test_valid_call_id_accepted(self):
        event = _make_cost_event(call_id="chatcmpl-123456")
        assert event.call_id == "chatcmpl-123456"


# ---------------------------------------------------------------------------
# Numeric validation (NaN / Inf / negative protection)
# ---------------------------------------------------------------------------


class TestCostEventNumericValidation:
    """Numeric fields must be validated against NaN, Inf, and negative values."""

    def test_negative_input_tokens_rejected(self):
        with pytest.raises(CostEventError, match="non-negative"):
            _make_cost_event(input_tokens=-1)

    def test_negative_output_tokens_rejected(self):
        with pytest.raises(CostEventError, match="non-negative"):
            _make_cost_event(output_tokens=-1)

    def test_negative_cost_rejected(self):
        with pytest.raises(CostEventError, match="non-negative"):
            _make_cost_event(cost_microdollars=-100)

    def test_zero_values_accepted(self):
        event = _make_cost_event(input_tokens=0, output_tokens=0, cost_microdollars=0)
        assert event.input_tokens == 0

    def test_float_tokens_rejected(self):
        """Tokens must be int, not float."""
        with pytest.raises(CostEventError, match="integer"):
            _make_cost_event(input_tokens=1.5)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestCostEventSerialization:
    """to_dict / from_dict must round-trip cleanly."""

    def test_round_trip(self):
        event = _make_cost_event(
            agent_id="agent-1",
            workflow_id="wf-1",
            metadata={"key": "value"},
        )
        d = event.to_dict()
        restored = CostEvent.from_dict(d)
        assert restored == event

    def test_to_dict_types(self):
        event = _make_cost_event()
        d = event.to_dict()
        assert isinstance(d["cost_id"], str)
        assert isinstance(d["input_tokens"], int)
        assert isinstance(d["cost_microdollars"], int)
        assert isinstance(d["metadata"], dict)

    def test_from_dict_missing_optional(self):
        """from_dict should handle missing optional fields."""
        d = {
            "cost_id": "c1",
            "call_id": "x",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "source": "openai",
            "model": "gpt-4",
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_microdollars": 100,
        }
        event = CostEvent.from_dict(d)
        assert event.agent_id is None
        assert event.workflow_id is None
        assert event.metadata == {}

    def test_cross_sdk_json_format(self):
        """Verify the serialized format is deterministic for cross-SDK compat."""
        event = CostEvent.create(
            call_id="chatcmpl-abc",
            source="openai",
            model="gpt-4-turbo",
            input_tokens=1000,
            output_tokens=500,
            cost_microdollars=4500,
            agent_id="agent-1",
            cost_id="fixed-id",
            timestamp="2026-01-15T12:00:00+00:00",
        )
        d = event.to_dict()
        # These field names and types must match the Rust SDK format
        assert "cost_id" in d
        assert "call_id" in d
        assert "source" in d
        assert "model" in d
        assert "input_tokens" in d
        assert "output_tokens" in d
        assert "cost_microdollars" in d
        assert isinstance(d["input_tokens"], int)
        assert isinstance(d["cost_microdollars"], int)


# ---------------------------------------------------------------------------
# CostEvent.create factory
# ---------------------------------------------------------------------------


class TestCostEventCreate:
    """CostEvent.create factory method."""

    def test_create_auto_generates_id_and_timestamp(self):
        event = CostEvent.create(
            call_id="call-1",
            source="openai",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_microdollars=1000,
        )
        assert event.cost_id  # non-empty UUID
        assert event.timestamp  # non-empty timestamp
        assert event.call_id == "call-1"

    def test_create_with_overrides(self):
        event = CostEvent.create(
            call_id="call-1",
            source="anthropic",
            model="claude-3-opus",
            input_tokens=200,
            output_tokens=100,
            cost_microdollars=5000,
            cost_id="override-id",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert event.cost_id == "override-id"
        assert event.timestamp == "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# CostDeduplicator
# ---------------------------------------------------------------------------


class TestCostDeduplicator:
    """CostDeduplicator must prevent double-counting."""

    def test_new_event_accepted(self):
        dedup = CostDeduplicator()
        event = _make_cost_event(call_id="unique-1")
        assert dedup.check_and_record(event) is True

    def test_duplicate_event_rejected(self):
        dedup = CostDeduplicator()
        event1 = _make_cost_event(call_id="dup-1", cost_id="c1")
        event2 = _make_cost_event(call_id="dup-1", cost_id="c2")
        dedup.check_and_record(event1)
        with pytest.raises(DuplicateCostError):
            dedup.check_and_record(event2)

    def test_different_call_ids_accepted(self):
        dedup = CostDeduplicator()
        for i in range(5):
            event = _make_cost_event(call_id=f"call-{i}", cost_id=f"cost-{i}")
            dedup.check_and_record(event)
        assert dedup.count == 5

    def test_is_duplicate_check(self):
        dedup = CostDeduplicator()
        event = _make_cost_event(call_id="check-1")
        assert dedup.is_duplicate("check-1") is False
        dedup.check_and_record(event)
        assert dedup.is_duplicate("check-1") is True
        assert dedup.is_duplicate("check-2") is False

    def test_bounded_capacity_eviction(self):
        """Oldest entries are evicted when capacity is exceeded."""
        dedup = CostDeduplicator(capacity=5)
        for i in range(10):
            event = _make_cost_event(call_id=f"call-{i}", cost_id=f"cost-{i}")
            dedup.check_and_record(event)

        assert dedup.count == 5
        # Oldest entries (0-4) should have been evicted
        assert dedup.is_duplicate("call-0") is False
        assert dedup.is_duplicate("call-4") is False
        # Recent entries (5-9) should still be tracked
        assert dedup.is_duplicate("call-5") is True
        assert dedup.is_duplicate("call-9") is True

    def test_clear(self):
        dedup = CostDeduplicator()
        event = _make_cost_event(call_id="clear-1")
        dedup.check_and_record(event)
        assert dedup.count == 1
        dedup.clear()
        assert dedup.count == 0
        # After clear, the same call_id should be accepted
        dedup.check_and_record(event)
        assert dedup.count == 1

    def test_capacity_must_be_positive(self):
        with pytest.raises(CostEventError, match="at least 1"):
            CostDeduplicator(capacity=0)

    def test_duplicate_error_does_not_leak_call_id(self):
        """DuplicateCostError message must use fingerprint, not raw call_id."""
        dedup = CostDeduplicator()
        event = _make_cost_event(call_id="sensitive-call-id-12345")
        dedup.check_and_record(event)
        with pytest.raises(DuplicateCostError) as exc_info:
            dedup.check_and_record(
                _make_cost_event(call_id="sensitive-call-id-12345", cost_id="c2")
            )
        # The raw call_id must NOT appear in the error message
        assert "sensitive-call-id-12345" not in str(exc_info.value)
        assert "fingerprint=" in str(exc_info.value)
