# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP Phase 4 Reasoning Trace Enrichment (TODOs 4.7-4.12).

Covers:
- reasoning_completeness_score(): scoring logic for 0-100 range
- ReasoningTrace.redact(): redaction round-trip, sentinel values, hash linkage
- ReasoningTrace.is_redacted(): detection before and after redaction
- ReasoningTrace.content_hash(): deterministic SHA-256 raw digest (32 bytes)
- ReasoningTrace.content_hash_hex(): deterministic hex string (64 chars)
- EvidenceReference: structured evidence, to_dict/from_dict, optional summary
- Backward compatibility: raw dict evidence in ReasoningTrace, signing payload
  stability after Phase 4 additions

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import json

import pytest
from datetime import datetime, timezone

from eatp.reasoning import (
    ConfidentialityLevel,
    EvidenceReference,
    ReasoningTrace,
    reasoning_completeness_score,
)
from eatp.crypto import (
    generate_keypair,
    serialize_for_signing,
    sign_reasoning_trace,
    verify_reasoning_signature,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXED_TIMESTAMP = datetime(2026, 3, 14, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def minimal_trace():
    """A ReasoningTrace with only required fields (decision + rationale)."""
    return ReasoningTrace(
        decision="Grant read access to dataset-alpha",
        rationale="Agent holds valid capability attestation for read_data",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
    )


@pytest.fixture
def full_trace():
    """A ReasoningTrace with all optional fields populated."""
    return ReasoningTrace(
        decision="Delegate analytics to agent-gamma",
        rationale="Agent-gamma has specialized analytics capability and lowest cost",
        confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        timestamp=FIXED_TIMESTAMP,
        alternatives_considered=[
            "Use agent-delta (rejected: higher latency)",
            "Keep in-house (rejected: lacks capability)",
        ],
        evidence=[
            {
                "type": "capability_check",
                "result": "passed",
                "capability": "analytics",
            },
            {"type": "cost_estimate", "value": 0.03, "currency": "USD"},
        ],
        methodology="cost_benefit",
        confidence=0.92,
    )


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for signing tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


# ===========================================================================
# Test Class 1: reasoning_completeness_score (TODO 4.7)
# ===========================================================================


class TestReasoningCompletenessScore:
    """Tests for reasoning_completeness_score() function."""

    def test_all_fields_present_without_signature(self, full_trace):
        """All fields present, signature_verified=False must yield 90."""
        score = reasoning_completeness_score(full_trace, signature_verified=False)
        # 30 (present) + 20 (alternatives) + 15 (evidence) + 15 (methodology) + 10 (confidence) = 90
        assert score == 90

    def test_all_fields_present_with_signature_verified(self, full_trace):
        """All fields present, signature_verified=True must yield 100."""
        score = reasoning_completeness_score(full_trace, signature_verified=True)
        # 90 + 10 (signature) = 100
        assert score == 100

    def test_partial_fields_alternatives_only(self):
        """Trace with alternatives_considered only (no evidence, methodology, confidence)."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["Alt A"],
        )
        score = reasoning_completeness_score(trace)
        # 30 (present) + 20 (alternatives) = 50
        assert score == 50

    def test_partial_fields_evidence_only(self):
        """Trace with evidence only."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[{"type": "metric", "value": 42}],
        )
        score = reasoning_completeness_score(trace)
        # 30 + 15 = 45
        assert score == 45

    def test_partial_fields_methodology_only(self):
        """Trace with methodology only."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="risk_assessment",
        )
        score = reasoning_completeness_score(trace)
        # 30 + 15 = 45
        assert score == 45

    def test_partial_fields_confidence_only(self):
        """Trace with confidence only."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=0.75,
        )
        score = reasoning_completeness_score(trace)
        # 30 + 10 = 40
        assert score == 40

    def test_no_optional_fields_yields_30(self, minimal_trace):
        """Trace with no optional fields (trace present only) must yield 30."""
        score = reasoning_completeness_score(minimal_trace)
        assert score == 30

    def test_none_trace_yields_zero(self):
        """None trace must yield 0."""
        score = reasoning_completeness_score(None)
        assert score == 0

    def test_signature_verified_adds_10_points(self, minimal_trace):
        """signature_verified=True adds exactly 10 points over base score."""
        base_score = reasoning_completeness_score(
            minimal_trace, signature_verified=False
        )
        sig_score = reasoning_completeness_score(minimal_trace, signature_verified=True)
        assert sig_score - base_score == 10

    def test_empty_methodology_string_not_counted(self):
        """Empty string methodology must NOT count as present."""
        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            methodology="",
        )
        score = reasoning_completeness_score(trace)
        # 30 only, empty string methodology should not add 15
        assert score == 30

    def test_score_never_exceeds_100(self, full_trace):
        """Score must be clamped to 100 maximum."""
        score = reasoning_completeness_score(full_trace, signature_verified=True)
        assert score <= 100

    def test_score_never_below_zero(self):
        """Score must be clamped to 0 minimum."""
        score = reasoning_completeness_score(None, signature_verified=False)
        assert score >= 0


# ===========================================================================
# Test Class 2: ReasoningTrace.redact() (TODO 4.8)
# ===========================================================================


class TestReasoningTraceRedact:
    """Tests for ReasoningTrace.redact() and is_redacted()."""

    def test_redact_returns_tuple(self, full_trace):
        """redact() must return a (ReasoningTrace, str) tuple."""
        result = full_trace.redact()
        assert isinstance(result, tuple)
        assert len(result) == 2
        redacted_trace, original_hash = result
        assert isinstance(redacted_trace, ReasoningTrace)
        assert isinstance(original_hash, str)

    def test_redact_sentinel_values(self, full_trace):
        """Redacted trace must have [REDACTED] sentinel in content fields."""
        redacted, _ = full_trace.redact()
        assert redacted.decision == "[REDACTED]"
        assert redacted.rationale == "[REDACTED]"
        assert redacted.methodology == "[REDACTED]"
        assert redacted.alternatives_considered == ["[REDACTED]"]
        assert redacted.evidence == [{"redacted": True}]

    def test_redacted_trace_retains_timestamp(self, full_trace):
        """Redacted trace must retain the original timestamp."""
        redacted, _ = full_trace.redact()
        assert redacted.timestamp == full_trace.timestamp

    def test_redacted_trace_retains_confidentiality(self, full_trace):
        """Redacted trace must retain the original confidentiality level."""
        redacted, _ = full_trace.redact()
        assert redacted.confidentiality == full_trace.confidentiality

    def test_redacted_trace_clears_confidence(self, full_trace):
        """Redacted trace must set confidence to None (prevent info leakage)."""
        redacted, _ = full_trace.redact()
        assert redacted.confidence is None

    def test_original_content_hash_returned(self, full_trace):
        """redact() must return the original trace's content_hash_hex."""
        redacted, original_hash = full_trace.redact()
        expected_hash = full_trace.content_hash_hex()
        assert original_hash == expected_hash

    def test_is_redacted_true_after_redact(self, full_trace):
        """is_redacted() must return True on a redacted trace."""
        redacted, _ = full_trace.redact()
        assert redacted.is_redacted() is True

    def test_is_redacted_false_before_redact(self, full_trace):
        """is_redacted() must return False on a non-redacted trace."""
        assert full_trace.is_redacted() is False

    def test_is_redacted_false_on_minimal_trace(self, minimal_trace):
        """is_redacted() must return False on a minimal (non-redacted) trace."""
        assert minimal_trace.is_redacted() is False

    def test_redact_does_not_mutate_original(self, full_trace):
        """redact() must not modify the original trace in-place."""
        original_decision = full_trace.decision
        original_rationale = full_trace.rationale
        _ = full_trace.redact()
        assert full_trace.decision == original_decision
        assert full_trace.rationale == original_rationale
        assert full_trace.is_redacted() is False

    def test_redacted_trace_has_different_content_hash(self, full_trace):
        """The redacted trace must have a different content hash than the original."""
        redacted, original_hash = full_trace.redact()
        redacted_hash = redacted.content_hash_hex()
        assert redacted_hash != original_hash


# ===========================================================================
# Test Class 3: content_hash / content_hash_hex (TODO 4.9)
# ===========================================================================


class TestContentHash:
    """Tests for ReasoningTrace.content_hash() and content_hash_hex()."""

    def test_content_hash_returns_bytes(self, full_trace):
        """content_hash() must return bytes."""
        result = full_trace.content_hash()
        assert isinstance(result, bytes)

    def test_content_hash_returns_32_bytes(self, full_trace):
        """content_hash() must return exactly 32 bytes (SHA-256 digest)."""
        result = full_trace.content_hash()
        assert len(result) == 32

    def test_content_hash_hex_returns_string(self, full_trace):
        """content_hash_hex() must return a string."""
        result = full_trace.content_hash_hex()
        assert isinstance(result, str)

    def test_content_hash_hex_returns_64_chars(self, full_trace):
        """content_hash_hex() must return exactly 64 hex characters."""
        result = full_trace.content_hash_hex()
        assert len(result) == 64

    def test_content_hash_hex_is_valid_hex(self, full_trace):
        """content_hash_hex() must return a valid hexadecimal string."""
        result = full_trace.content_hash_hex()
        # Must not raise ValueError
        int(result, 16)

    def test_content_hash_deterministic(self, full_trace):
        """Same trace must produce the same hash on repeated calls."""
        hash1 = full_trace.content_hash()
        hash2 = full_trace.content_hash()
        assert hash1 == hash2

    def test_content_hash_hex_deterministic(self, full_trace):
        """Same trace must produce the same hex hash on repeated calls."""
        hex1 = full_trace.content_hash_hex()
        hex2 = full_trace.content_hash_hex()
        assert hex1 == hex2

    def test_content_hash_hex_matches_content_hash(self, full_trace):
        """content_hash_hex() must equal content_hash().hex()."""
        raw = full_trace.content_hash()
        hex_str = full_trace.content_hash_hex()
        assert hex_str == raw.hex()

    def test_content_hash_changes_on_different_decision(self):
        """Changing the decision must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="Decision A",
            rationale="Same rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="Decision B",
            rationale="Same rationale",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert trace1.content_hash() != trace2.content_hash()

    def test_content_hash_changes_on_different_rationale(self):
        """Changing the rationale must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="Same",
            rationale="Rationale A",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="Same",
            rationale="Rationale B",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        assert trace1.content_hash() != trace2.content_hash()

    def test_content_hash_changes_on_different_confidentiality(self):
        """Changing the confidentiality must produce a different hash."""
        trace1 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
        )
        trace2 = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=FIXED_TIMESTAMP,
        )
        assert trace1.content_hash_hex() != trace2.content_hash_hex()

    def test_equivalent_traces_produce_same_hash(self):
        """Two independently constructed but equivalent traces must hash identically."""
        kwargs = dict(
            decision="Test",
            rationale="Reason",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=FIXED_TIMESTAMP,
            alternatives_considered=["A"],
            evidence=[{"k": "v"}],
            methodology="m",
            confidence=0.5,
        )
        trace1 = ReasoningTrace(**kwargs)
        trace2 = ReasoningTrace(**kwargs)
        assert trace1.content_hash() == trace2.content_hash()

    def test_content_hash_stable_across_round_trip(self, full_trace):
        """Content hash must be identical before and after to_dict/from_dict."""
        hash_before = full_trace.content_hash_hex()
        d = full_trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        hash_after = restored.content_hash_hex()
        assert hash_before == hash_after


# ===========================================================================
# Test Class 4: EvidenceReference (TODO 4.10)
# ===========================================================================


class TestEvidenceReference:
    """Tests for EvidenceReference dataclass."""

    def test_construction_required_fields(self):
        """EvidenceReference with required fields only must succeed."""
        ref = EvidenceReference(
            evidence_type="document",
            reference="https://docs.example.com/policy-v2",
        )
        assert ref.evidence_type == "document"
        assert ref.reference == "https://docs.example.com/policy-v2"
        assert ref.summary is None

    def test_construction_with_summary(self):
        """EvidenceReference with optional summary must succeed."""
        ref = EvidenceReference(
            evidence_type="metric",
            reference="dashboard://metrics/latency-p99",
            summary="P99 latency within SLA threshold of 200ms",
        )
        assert ref.summary == "P99 latency within SLA threshold of 200ms"

    def test_to_dict_without_summary(self):
        """to_dict() without summary must omit summary key."""
        ref = EvidenceReference(
            evidence_type="audit_log",
            reference="log://audit/2026-03-14/agent-gamma",
        )
        d = ref.to_dict()
        assert d == {
            "evidence_type": "audit_log",
            "reference": "log://audit/2026-03-14/agent-gamma",
        }
        assert "summary" not in d

    def test_to_dict_with_summary(self):
        """to_dict() with summary must include summary key."""
        ref = EvidenceReference(
            evidence_type="external_api",
            reference="https://api.ratings.example.com/agent/gamma",
            summary="Agent trust score 0.95 from external registry",
        )
        d = ref.to_dict()
        assert d["evidence_type"] == "external_api"
        assert d["reference"] == "https://api.ratings.example.com/agent/gamma"
        assert d["summary"] == "Agent trust score 0.95 from external registry"

    def test_from_dict_without_summary(self):
        """from_dict() without summary must create EvidenceReference with None summary."""
        data = {
            "evidence_type": "document",
            "reference": "/docs/policy.pdf",
        }
        ref = EvidenceReference.from_dict(data)
        assert ref.evidence_type == "document"
        assert ref.reference == "/docs/policy.pdf"
        assert ref.summary is None

    def test_from_dict_with_summary(self):
        """from_dict() with summary must preserve it."""
        data = {
            "evidence_type": "metric",
            "reference": "metric://cpu-usage",
            "summary": "CPU usage below 80%",
        }
        ref = EvidenceReference.from_dict(data)
        assert ref.summary == "CPU usage below 80%"

    def test_round_trip_without_summary(self):
        """to_dict() -> from_dict() round-trip must preserve all fields (no summary)."""
        original = EvidenceReference(
            evidence_type="audit_log",
            reference="log://chain/del-001",
        )
        d = original.to_dict()
        restored = EvidenceReference.from_dict(d)
        assert restored.evidence_type == original.evidence_type
        assert restored.reference == original.reference
        assert restored.summary is None

    def test_round_trip_with_summary(self):
        """to_dict() -> from_dict() round-trip must preserve all fields (with summary)."""
        original = EvidenceReference(
            evidence_type="external_api",
            reference="https://trust.example.com/scores/agent-gamma",
            summary="Trust score 0.92 as of 2026-03-14",
        )
        d = original.to_dict()
        restored = EvidenceReference.from_dict(d)
        assert restored.evidence_type == original.evidence_type
        assert restored.reference == original.reference
        assert restored.summary == original.summary

    def test_to_dict_is_json_serializable(self):
        """to_dict() output must be JSON serializable."""
        ref = EvidenceReference(
            evidence_type="metric",
            reference="metric://throughput",
            summary="1500 req/s sustained",
        )
        d = ref.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed == d

    def test_backward_compat_raw_dict_evidence_in_trace(self):
        """ReasoningTrace.evidence must accept raw dicts alongside EvidenceReference.to_dict()."""
        raw_evidence = {"type": "legacy_check", "result": "pass", "score": 0.95}
        structured_evidence = EvidenceReference(
            evidence_type="document",
            reference="/docs/attestation.pdf",
            summary="Valid capability attestation",
        ).to_dict()

        trace = ReasoningTrace(
            decision="Grant access",
            rationale="Both evidence types present",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[raw_evidence, structured_evidence],
        )
        assert len(trace.evidence) == 2
        assert trace.evidence[0] == raw_evidence
        assert trace.evidence[1] == structured_evidence

    def test_backward_compat_raw_dict_round_trip(self):
        """ReasoningTrace with mixed evidence (raw dict + EvidenceReference) must round-trip."""
        raw_evidence = {"type": "metric", "value": 42}
        structured = EvidenceReference(
            evidence_type="document",
            reference="/attestation.json",
        ).to_dict()

        trace = ReasoningTrace(
            decision="d",
            rationale="r",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            evidence=[raw_evidence, structured],
        )
        d = trace.to_dict()
        restored = ReasoningTrace.from_dict(d)
        assert restored.evidence == [raw_evidence, structured]


# ===========================================================================
# Test Class 5: Signing Payload Compatibility (TODO 4.11)
# ===========================================================================


class TestSigningPayloadCompatibility:
    """Tests that Phase 4 additions do not break existing signing payloads."""

    def test_to_signing_payload_excludes_content_hash(self, full_trace):
        """to_signing_payload() must NOT contain content_hash or content_hash_hex keys."""
        payload = full_trace.to_signing_payload()
        assert "content_hash" not in payload
        assert "content_hash_hex" not in payload

    def test_to_signing_payload_excludes_redaction_fields(self, full_trace):
        """to_signing_payload() must NOT contain redaction-related keys."""
        payload = full_trace.to_signing_payload()
        assert "is_redacted" not in payload
        assert "redacted" not in payload

    def test_to_signing_payload_key_set_unchanged(self, full_trace):
        """to_signing_payload() must contain exactly the original 8 fields."""
        payload = full_trace.to_signing_payload()
        expected_keys = {
            "alternatives_considered",
            "confidence",
            "confidentiality",
            "decision",
            "evidence",
            "methodology",
            "rationale",
            "timestamp",
        }
        assert set(payload.keys()) == expected_keys

    def test_existing_signature_valid_after_phase4_additions(self, full_trace, keypair):
        """Signatures created on a trace must remain valid -- Phase 4 methods do not alter payload."""
        private_key, public_key = keypair

        # Sign the trace
        signature = sign_reasoning_trace(full_trace, private_key)

        # Call Phase 4 methods (must have no side-effects on signing payload)
        _ = full_trace.content_hash()
        _ = full_trace.content_hash_hex()
        _ = full_trace.redact()
        _ = full_trace.is_redacted()

        # Verify signature still holds
        assert verify_reasoning_signature(full_trace, signature, public_key) is True

    def test_signing_payload_deterministic_after_phase4_calls(self, full_trace):
        """to_signing_payload() must remain deterministic after Phase 4 method calls."""
        payload_before = full_trace.to_signing_payload()

        # Exercise all Phase 4 methods
        _ = full_trace.content_hash()
        _ = full_trace.content_hash_hex()
        _ = full_trace.redact()
        _ = full_trace.is_redacted()
        _ = reasoning_completeness_score(full_trace, signature_verified=True)

        payload_after = full_trace.to_signing_payload()
        assert payload_before == payload_after

    def test_signing_payload_json_stable_after_phase4(self, full_trace):
        """JSON serialization of signing payload must be identical before and after Phase 4 calls."""
        serialized_before = serialize_for_signing(full_trace.to_signing_payload())

        _ = full_trace.content_hash()
        _ = full_trace.redact()
        _ = reasoning_completeness_score(full_trace)

        serialized_after = serialize_for_signing(full_trace.to_signing_payload())
        assert serialized_before == serialized_after
