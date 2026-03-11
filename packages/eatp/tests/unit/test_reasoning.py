# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP Reasoning Trace Extension (TODO-006).

Covers:
- ConfidentialityLevel enum: values, ordering, string conversion
- ReasoningTrace dataclass: construction, validation, serialization,
  deserialization, signing payload, edge cases
- Backward-compatible defaults in from_dict()
- Confidence validation (0.0 to 1.0)
- Deterministic to_signing_payload() output

Written BEFORE implementation (TDD). Tests define the contract.
"""

import json

import pytest
from datetime import datetime, timezone

from eatp.reasoning import ConfidentialityLevel, ReasoningTrace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def minimal_trace():
    """A ReasoningTrace with only required fields."""
    return ReasoningTrace(
        decision="Approve data access for agent-beta",
        rationale="Agent has valid capability attestation and passes constraint checks",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
    )


@pytest.fixture
def full_trace():
    """A ReasoningTrace with all fields populated."""
    return ReasoningTrace(
        decision="Delegate financial analysis to agent-gamma",
        rationale="Agent-gamma has specialized financial analysis capabilities and lower cost",
        confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        timestamp=FIXED_TIMESTAMP,
        alternatives_considered=[
            "Use agent-delta (rejected: higher latency)",
            "Process in-house (rejected: lacks capability)",
        ],
        evidence=[
            {
                "type": "capability_check",
                "result": "passed",
                "capability": "financial_analysis",
            },
            {"type": "cost_estimate", "value": 0.05, "currency": "USD"},
        ],
        methodology="cost_benefit",
        confidence=0.87,
    )


# ===========================================================================
# Test Class 1: ConfidentialityLevel Enum
# ===========================================================================


class TestConfidentialityLevel:
    """Tests for the ConfidentialityLevel enum."""

    def test_all_values_exist(self):
        """All five confidentiality levels must exist with correct string values."""
        assert ConfidentialityLevel.PUBLIC.value == "public"
        assert ConfidentialityLevel.RESTRICTED.value == "restricted"
        assert ConfidentialityLevel.CONFIDENTIAL.value == "confidential"
        assert ConfidentialityLevel.SECRET.value == "secret"
        assert ConfidentialityLevel.TOP_SECRET.value == "top_secret"

    def test_total_member_count(self):
        """Exactly five confidentiality levels must exist."""
        assert len(ConfidentialityLevel) == 5

    def test_from_string_value(self):
        """ConfidentialityLevel must be constructable from its string value."""
        assert ConfidentialityLevel("public") == ConfidentialityLevel.PUBLIC
        assert ConfidentialityLevel("restricted") == ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel("confidential") == ConfidentialityLevel.CONFIDENTIAL
        assert ConfidentialityLevel("secret") == ConfidentialityLevel.SECRET
        assert ConfidentialityLevel("top_secret") == ConfidentialityLevel.TOP_SECRET

    def test_invalid_value_raises(self):
        """Invalid string value must raise ValueError."""
        with pytest.raises(ValueError):
            ConfidentialityLevel("invalid")

    def test_ordering_less_than(self):
        """Confidentiality levels must support < comparison."""
        assert ConfidentialityLevel.PUBLIC < ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.RESTRICTED < ConfidentialityLevel.CONFIDENTIAL
        assert ConfidentialityLevel.CONFIDENTIAL < ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET < ConfidentialityLevel.TOP_SECRET

    def test_ordering_greater_than(self):
        """Confidentiality levels must support > comparison."""
        assert ConfidentialityLevel.TOP_SECRET > ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET > ConfidentialityLevel.CONFIDENTIAL
        assert ConfidentialityLevel.CONFIDENTIAL > ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.RESTRICTED > ConfidentialityLevel.PUBLIC

    def test_ordering_less_than_or_equal(self):
        """Confidentiality levels must support <= comparison."""
        assert ConfidentialityLevel.PUBLIC <= ConfidentialityLevel.PUBLIC
        assert ConfidentialityLevel.PUBLIC <= ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.RESTRICTED <= ConfidentialityLevel.CONFIDENTIAL

    def test_ordering_greater_than_or_equal(self):
        """Confidentiality levels must support >= comparison."""
        assert ConfidentialityLevel.TOP_SECRET >= ConfidentialityLevel.TOP_SECRET
        assert ConfidentialityLevel.TOP_SECRET >= ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET >= ConfidentialityLevel.CONFIDENTIAL

    def test_ordering_equality(self):
        """Same level must be equal."""
        assert ConfidentialityLevel.RESTRICTED == ConfidentialityLevel.RESTRICTED
        assert not (ConfidentialityLevel.PUBLIC == ConfidentialityLevel.SECRET)

    def test_ordering_transitivity(self):
        """If A < B and B < C then A < C."""
        a = ConfidentialityLevel.PUBLIC
        b = ConfidentialityLevel.CONFIDENTIAL
        c = ConfidentialityLevel.TOP_SECRET
        assert a < b
        assert b < c
        assert a < c

    def test_ordering_not_less_than_when_greater(self):
        """Greater level must not be less than lesser level."""
        assert not (ConfidentialityLevel.SECRET < ConfidentialityLevel.PUBLIC)

    def test_full_ordering_chain(self):
        """Complete ordering chain: PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET."""
        levels = [
            ConfidentialityLevel.PUBLIC,
            ConfidentialityLevel.RESTRICTED,
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
            ConfidentialityLevel.TOP_SECRET,
        ]
        for i in range(len(levels) - 1):
            assert (
                levels[i] < levels[i + 1]
            ), f"{levels[i].name} should be < {levels[i + 1].name}"

    def test_sorting(self):
        """Confidentiality levels must be sortable."""
        unsorted = [
            ConfidentialityLevel.SECRET,
            ConfidentialityLevel.PUBLIC,
            ConfidentialityLevel.TOP_SECRET,
            ConfidentialityLevel.RESTRICTED,
            ConfidentialityLevel.CONFIDENTIAL,
        ]
        sorted_levels = sorted(unsorted)
        assert sorted_levels == [
            ConfidentialityLevel.PUBLIC,
            ConfidentialityLevel.RESTRICTED,
            ConfidentialityLevel.CONFIDENTIAL,
            ConfidentialityLevel.SECRET,
            ConfidentialityLevel.TOP_SECRET,
        ]


# ===========================================================================
# Test Class 2: ReasoningTrace Construction
# ===========================================================================


class TestReasoningTraceConstruction:
    """Tests for ReasoningTrace dataclass creation and validation."""

    def test_minimal_construction(self, minimal_trace):
        """ReasoningTrace with only required fields must succeed."""
        assert minimal_trace.decision == "Approve data access for agent-beta"
        assert (
            minimal_trace.rationale
            == "Agent has valid capability attestation and passes constraint checks"
        )
        assert minimal_trace.confidentiality == ConfidentialityLevel.RESTRICTED
        assert minimal_trace.timestamp == FIXED_TIMESTAMP

    def test_minimal_defaults(self, minimal_trace):
        """Optional fields must have correct defaults."""
        assert minimal_trace.alternatives_considered == []
        assert minimal_trace.evidence == []
        assert minimal_trace.methodology is None
        assert minimal_trace.confidence is None

    def test_full_construction(self, full_trace):
        """ReasoningTrace with all fields must succeed."""
        assert full_trace.decision == "Delegate financial analysis to agent-gamma"
        assert full_trace.confidentiality == ConfidentialityLevel.CONFIDENTIAL
        assert len(full_trace.alternatives_considered) == 2
        assert len(full_trace.evidence) == 2
        assert full_trace.methodology == "cost_benefit"
        assert full_trace.confidence == 0.87

    def test_confidence_valid_zero(self):
        """Confidence of 0.0 must be valid."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.0,
        )
        assert trace.confidence == 0.0

    def test_confidence_valid_one(self):
        """Confidence of 1.0 must be valid."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=1.0,
        )
        assert trace.confidence == 1.0

    def test_confidence_valid_midpoint(self):
        """Confidence of 0.5 must be valid."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.5,
        )
        assert trace.confidence == 0.5

    def test_confidence_too_low_raises(self):
        """Confidence below 0.0 must raise ValueError."""
        with pytest.raises(ValueError, match="confidence"):
            ReasoningTrace(
                decision="d",
                rationale="r",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=-0.01,
            )

    def test_confidence_too_high_raises(self):
        """Confidence above 1.0 must raise ValueError."""
        with pytest.raises(ValueError, match="confidence"):
            ReasoningTrace(
                decision="d",
                rationale="r",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=1.01,
            )

    def test_confidence_way_too_low_raises(self):
        """Confidence of -100 must raise ValueError."""
        with pytest.raises(ValueError, match="confidence"):
            ReasoningTrace(
                decision="d",
                rationale="r",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=-100.0,
            )

    def test_confidence_way_too_high_raises(self):
        """Confidence of 5.0 must raise ValueError."""
        with pytest.raises(ValueError, match="confidence"):
            ReasoningTrace(
                decision="d",
                rationale="r",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=FIXED_TIMESTAMP,
                confidence=5.0,
            )

    def test_confidence_none_is_valid(self):
        """Confidence of None (not specified) must be valid."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=None,
        )
        assert trace.confidence is None


# ===========================================================================
# Test Class 3: ReasoningTrace.to_dict() Serialization
# ===========================================================================


class TestReasoningTraceToDict:
    """Tests for ReasoningTrace.to_dict() serialization."""

    def test_minimal_to_dict_keys(self, minimal_trace):
        """to_dict() on minimal trace must contain all expected keys."""
        d = minimal_trace.to_dict()
        expected_keys = {
            "decision",
            "rationale",
            "confidentiality",
            "timestamp",
            "alternatives_considered",
            "evidence",
            "methodology",
            "confidence",
        }
        assert set(d.keys()) == expected_keys

    def test_minimal_to_dict_values(self, minimal_trace):
        """to_dict() on minimal trace must serialize correctly."""
        d = minimal_trace.to_dict()
        assert d["decision"] == "Approve data access for agent-beta"
        assert (
            d["rationale"]
            == "Agent has valid capability attestation and passes constraint checks"
        )
        assert d["confidentiality"] == "restricted"
        assert d["timestamp"] == "2026-03-11T14:30:00+00:00"
        assert d["alternatives_considered"] == []
        assert d["evidence"] == []
        assert d["methodology"] is None
        assert d["confidence"] is None

    def test_full_to_dict_values(self, full_trace):
        """to_dict() on full trace must serialize all fields correctly."""
        d = full_trace.to_dict()
        assert d["confidentiality"] == "confidential"
        assert d["timestamp"] == "2026-03-11T14:30:00+00:00"
        assert len(d["alternatives_considered"]) == 2
        assert (
            d["alternatives_considered"][0]
            == "Use agent-delta (rejected: higher latency)"
        )
        assert len(d["evidence"]) == 2
        assert d["evidence"][0]["type"] == "capability_check"
        assert d["methodology"] == "cost_benefit"
        assert d["confidence"] == 0.87

    def test_confidentiality_serialized_as_string_value(self, full_trace):
        """ConfidentialityLevel must be serialized as its string value, not enum repr."""
        d = full_trace.to_dict()
        assert isinstance(d["confidentiality"], str)
        assert d["confidentiality"] == "confidential"
        # Must not be something like "ConfidentialityLevel.CONFIDENTIAL"
        assert "ConfidentialityLevel" not in d["confidentiality"]

    def test_timestamp_serialized_as_iso(self, minimal_trace):
        """Timestamp must be serialized as ISO 8601 string."""
        d = minimal_trace.to_dict()
        assert isinstance(d["timestamp"], str)
        # Must be parseable back
        parsed = datetime.fromisoformat(d["timestamp"])
        assert parsed == FIXED_TIMESTAMP

    def test_to_dict_is_json_serializable(self, full_trace):
        """to_dict() output must be JSON serializable."""
        d = full_trace.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["decision"] == d["decision"]
        assert parsed["confidence"] == d["confidence"]


# ===========================================================================
# Test Class 4: ReasoningTrace.from_dict() Deserialization
# ===========================================================================


class TestReasoningTraceFromDict:
    """Tests for ReasoningTrace.from_dict() deserialization."""

    def test_full_round_trip(self, full_trace):
        """to_dict() -> from_dict() must produce equivalent trace."""
        d = full_trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.decision == full_trace.decision
        assert restored.rationale == full_trace.rationale
        assert restored.confidentiality == full_trace.confidentiality
        assert restored.timestamp == full_trace.timestamp
        assert restored.alternatives_considered == full_trace.alternatives_considered
        assert restored.evidence == full_trace.evidence
        assert restored.methodology == full_trace.methodology
        assert restored.confidence == full_trace.confidence

    def test_minimal_round_trip(self, minimal_trace):
        """Minimal trace round-trip must preserve all fields."""
        d = minimal_trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.decision == minimal_trace.decision
        assert restored.rationale == minimal_trace.rationale
        assert restored.confidentiality == minimal_trace.confidentiality
        assert restored.timestamp == minimal_trace.timestamp
        assert restored.alternatives_considered == []
        assert restored.evidence == []
        assert restored.methodology is None
        assert restored.confidence is None

    def test_from_dict_backward_compatible_missing_optional_fields(self):
        """from_dict() must handle missing optional fields with defaults."""
        data = {
            "decision": "Test decision",
            "rationale": "Test rationale",
            "confidentiality": "restricted",
            "timestamp": "2026-03-11T14:30:00+00:00",
        }
        trace = ReasoningTrace.from_dict(data)
        assert trace.decision == "Test decision"
        assert trace.rationale == "Test rationale"
        assert trace.confidentiality == ConfidentialityLevel.RESTRICTED
        assert trace.alternatives_considered == []
        assert trace.evidence == []
        assert trace.methodology is None
        assert trace.confidence is None

    def test_from_dict_with_none_optional_fields(self):
        """from_dict() must handle explicit None for optional fields."""
        data = {
            "decision": "Test",
            "rationale": "Reason",
            "confidentiality": "public",
            "timestamp": "2026-03-11T14:30:00+00:00",
            "alternatives_considered": None,
            "evidence": None,
            "methodology": None,
            "confidence": None,
        }
        trace = ReasoningTrace.from_dict(data)
        assert trace.alternatives_considered == []
        assert trace.evidence == []
        assert trace.methodology is None
        assert trace.confidence is None

    def test_from_dict_parses_confidentiality_string(self):
        """from_dict() must parse confidentiality from string value."""
        for level in ConfidentialityLevel:
            data = {
                "decision": "d",
                "rationale": "r",
                "confidentiality": level.value,
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
            trace = ReasoningTrace.from_dict(data)
            assert trace.confidentiality == level

    def test_from_dict_parses_timestamp(self):
        """from_dict() must parse ISO 8601 timestamp string."""
        data = {
            "decision": "d",
            "rationale": "r",
            "confidentiality": "public",
            "timestamp": "2026-06-15T08:30:45+00:00",
        }
        trace = ReasoningTrace.from_dict(data)
        assert trace.timestamp == datetime(2026, 6, 15, 8, 30, 45, tzinfo=timezone.utc)

    def test_from_dict_double_round_trip(self, full_trace):
        """Double round-trip must be stable: to_dict -> from_dict -> to_dict -> from_dict."""
        d1 = full_trace.to_dict()
        t1 = ReasoningTrace.from_dict(d1)
        d2 = t1.to_dict()
        t2 = ReasoningTrace.from_dict(d2)
        assert t1.decision == t2.decision
        assert t1.rationale == t2.rationale
        assert t1.confidentiality == t2.confidentiality
        assert t1.timestamp == t2.timestamp
        assert t1.alternatives_considered == t2.alternatives_considered
        assert t1.evidence == t2.evidence
        assert t1.methodology == t2.methodology
        assert t1.confidence == t2.confidence
        assert d1 == d2


# ===========================================================================
# Test Class 5: ReasoningTrace.to_signing_payload() Determinism
# ===========================================================================


class TestReasoningTraceSigningPayload:
    """Tests for ReasoningTrace.to_signing_payload() deterministic output."""

    def test_signing_payload_is_deterministic(self, full_trace):
        """to_signing_payload() must produce identical output across calls."""
        p1 = full_trace.to_signing_payload()
        p2 = full_trace.to_signing_payload()
        assert p1 == p2

    def test_signing_payload_contains_all_fields(self, full_trace):
        """to_signing_payload() must include all fields."""
        payload = full_trace.to_signing_payload()
        expected_keys = {
            "decision",
            "rationale",
            "confidentiality",
            "timestamp",
            "alternatives_considered",
            "evidence",
            "methodology",
            "confidence",
        }
        assert set(payload.keys()) == expected_keys

    def test_signing_payload_keys_are_sorted(self, full_trace):
        """to_signing_payload() must return dict with sorted keys."""
        payload = full_trace.to_signing_payload()
        keys = list(payload.keys())
        assert keys == sorted(
            keys
        ), f"Keys must be sorted for deterministic signing. Got: {keys}"

    def test_signing_payload_serializes_enum_as_value(self, full_trace):
        """ConfidentialityLevel must be serialized as string value in signing payload."""
        payload = full_trace.to_signing_payload()
        assert payload["confidentiality"] == "confidential"
        assert isinstance(payload["confidentiality"], str)

    def test_signing_payload_serializes_timestamp_as_iso(self, full_trace):
        """Timestamp must be ISO 8601 in signing payload."""
        payload = full_trace.to_signing_payload()
        assert payload["timestamp"] == "2026-03-11T14:30:00+00:00"

    def test_signing_payload_minimal_trace(self, minimal_trace):
        """to_signing_payload() on minimal trace must include all fields with defaults."""
        payload = minimal_trace.to_signing_payload()
        assert payload["alternatives_considered"] == []
        assert payload["evidence"] == []
        assert payload["methodology"] is None
        assert payload["confidence"] is None

    def test_signing_payload_json_serializable(self, full_trace):
        """to_signing_payload() output must be JSON serializable."""
        payload = full_trace.to_signing_payload()
        json_str = json.dumps(payload, sort_keys=True)
        parsed = json.loads(json_str)
        assert parsed == payload

    def test_signing_payload_different_traces_produce_different_payloads(
        self, minimal_trace, full_trace
    ):
        """Different traces must produce different signing payloads."""
        p1 = minimal_trace.to_signing_payload()
        p2 = full_trace.to_signing_payload()
        assert p1 != p2

    def test_signing_payload_serialize_for_signing_integration(self, full_trace):
        """to_signing_payload() output must work with serialize_for_signing()."""
        from eatp.crypto import serialize_for_signing

        payload = full_trace.to_signing_payload()
        serialized = serialize_for_signing(payload)
        # Must be valid JSON
        parsed = json.loads(serialized)
        assert parsed["decision"] == full_trace.decision
        # Must be deterministic
        serialized_2 = serialize_for_signing(payload)
        assert serialized == serialized_2


# ===========================================================================
# Test Class 6: Edge Cases
# ===========================================================================


class TestReasoningTraceEdgeCases:
    """Edge case tests for ReasoningTrace."""

    def test_empty_decision_string(self):
        """Empty decision string must be accepted (no validation on content)."""
        trace = ReasoningTrace(
            decision="",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert trace.decision == ""

    def test_empty_rationale_string(self):
        """Empty rationale string must be accepted."""
        trace = ReasoningTrace(
            decision="d",
            rationale="",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert trace.rationale == ""

    def test_large_alternatives_list(self):
        """Large alternatives_considered list must be handled."""
        alternatives = [f"Alternative {i}" for i in range(100)]
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=alternatives,
        )
        assert len(trace.alternatives_considered) == 100

    def test_complex_evidence_dicts(self):
        """Evidence with nested dicts must serialize/deserialize correctly."""
        evidence = [
            {
                "type": "nested",
                "data": {"inner": {"deep": [1, 2, 3]}, "flag": True},
            }
        ]
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=FIXED_TIMESTAMP,
            evidence=evidence,
        )
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.evidence == evidence

    def test_all_confidentiality_levels_round_trip(self):
        """Every confidentiality level must survive to_dict/from_dict round-trip."""
        for level in ConfidentialityLevel:
            trace = ReasoningTrace(
                decision="d",
                rationale="r",
                confidentiality=level,
                timestamp=FIXED_TIMESTAMP,
            )
            d = trace.to_dict()
            restored = ReasoningTrace.from_dict(d)
            assert (
                restored.confidentiality == level
            ), f"Round-trip failed for {level.name}"

    def test_confidence_boundary_exact_zero(self):
        """Confidence of exactly 0.0 must be valid and round-trip."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.0,
        )
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.confidence == 0.0

    def test_confidence_boundary_exact_one(self):
        """Confidence of exactly 1.0 must be valid and round-trip."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=1.0,
        )
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.confidence == 1.0

    def test_naive_timestamp_not_rejected(self):
        """Naive (timezone-unaware) timestamp should be accepted by the dataclass."""
        naive_ts = datetime(2026, 1, 1, 0, 0, 0)
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=naive_ts,
        )
        assert trace.timestamp == naive_ts
