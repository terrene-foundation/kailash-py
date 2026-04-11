"""Tests for Kaizen reasoning trace shim exports (TODO-025).

Verifies that reasoning trace types are properly re-exported through the
Kaizen trust module and that the PostgresAuditStore preserves reasoning
trace fields during serialization/deserialization.
"""

from datetime import datetime, timezone

import pytest


class TestReasoningShimImports:
    """Verify reasoning types are importable from kaizen.trust."""

    def test_import_confidentiality_level_from_trust_init(self):
        """ConfidentialityLevel should be importable from kaizen.trust."""
        from kaizen.trust import ConfidentialityLevel

        assert hasattr(ConfidentialityLevel, "PUBLIC")
        assert hasattr(ConfidentialityLevel, "RESTRICTED")
        assert hasattr(ConfidentialityLevel, "CONFIDENTIAL")
        assert hasattr(ConfidentialityLevel, "SECRET")
        assert hasattr(ConfidentialityLevel, "TOP_SECRET")

    def test_import_reasoning_trace_from_trust_init(self):
        """ReasoningTrace should be importable from kaizen.trust."""
        from kaizen.trust import ReasoningTrace

        trace = ReasoningTrace(
            decision="Allow data access",
            rationale="Agent has valid capability attestation",
            confidentiality=self._get_confidentiality_level("RESTRICTED"),
            timestamp=datetime.now(timezone.utc),
        )
        assert trace.decision == "Allow data access"
        assert trace.confidence is None  # optional

    def test_import_from_reasoning_submodule(self):
        """Types should also be importable from kailash.trust.reasoning.traces."""
        from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace

        assert ConfidentialityLevel.PUBLIC.value == "public"
        assert ReasoningTrace is not None

    def test_confidentiality_level_ordering(self):
        """ConfidentialityLevel supports ordering comparisons."""
        from kaizen.trust import ConfidentialityLevel

        assert ConfidentialityLevel.PUBLIC < ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.RESTRICTED < ConfidentialityLevel.CONFIDENTIAL
        assert ConfidentialityLevel.CONFIDENTIAL < ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET < ConfidentialityLevel.TOP_SECRET

    def test_constraint_type_reasoning_required(self):
        """ConstraintType.REASONING_REQUIRED should be available."""
        from kaizen.trust import ConstraintType

        assert hasattr(ConstraintType, "REASONING_REQUIRED")
        assert ConstraintType.REASONING_REQUIRED.value == "reasoning_required"

    def test_reasoning_trace_to_dict_roundtrip(self):
        """ReasoningTrace should serialize/deserialize correctly."""
        from kaizen.trust import ConfidentialityLevel, ReasoningTrace

        original = ReasoningTrace(
            decision="Delegate analysis capability",
            rationale="Worker agent has required training certification",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            alternatives_considered=["Reject delegation", "Partial delegation"],
            evidence=[{"type": "cert", "id": "cert-123"}],
            methodology="capability_matching",
            confidence=0.95,
        )

        serialized = original.to_dict()
        restored = ReasoningTrace.from_dict(serialized)

        assert restored.decision == original.decision
        assert restored.rationale == original.rationale
        assert restored.confidentiality == original.confidentiality
        assert restored.alternatives_considered == original.alternatives_considered
        assert restored.evidence == original.evidence
        assert restored.methodology == original.methodology
        assert restored.confidence == original.confidence

    def test_reasoning_trace_signing_payload(self):
        """Signing payload should be deterministic (sorted keys)."""
        from kaizen.trust import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Allow",
            rationale="Valid",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        payload = trace.to_signing_payload()
        keys = list(payload.keys())
        assert keys == sorted(keys), "Signing payload keys must be sorted"

    def test_reasoning_trace_confidence_validation(self):
        """Confidence must be between 0.0 and 1.0."""
        from kaizen.trust import ConfidentialityLevel, ReasoningTrace

        with pytest.raises(ValueError, match="confidence must be between"):
            ReasoningTrace(
                decision="test",
                rationale="test",
                confidentiality=ConfidentialityLevel.PUBLIC,
                timestamp=datetime.now(timezone.utc),
                confidence=1.5,
            )

    @staticmethod
    def _get_confidentiality_level(name: str):
        from kaizen.trust import ConfidentialityLevel

        return ConfidentialityLevel[name]


class TestAuditStoreReasoningPreservation:
    """Verify PostgresAuditStore preserves reasoning trace fields."""

    def test_deserialize_anchor_with_reasoning_trace(self):
        """_deserialize_anchor should restore reasoning trace from anchor_data."""
        from kaizen.trust.audit_store import PostgresAuditStore

        # Create a mock record as it would come from the database,
        # with reasoning trace stored in anchor_data
        record = {
            "id": "aud-001",
            "agent_id": "agent-001",
            "action": "analyze_data",
            "resource": "dataset-42",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "trust_chain_hash": "abc123",
            "result": "success",
            "parent_anchor_id": None,
            "signature": "sig-xyz",
            "anchor_data": {
                "context": {"workflow_id": "wf-1"},
                "reasoning_trace": {
                    "decision": "Approved data analysis",
                    "rationale": "Agent has valid scope for dataset-42",
                    "confidentiality": "restricted",
                    "timestamp": "2026-01-15T12:00:00+00:00",
                    "alternatives_considered": [],
                    "evidence": [],
                    "methodology": "scope_matching",
                    "confidence": 0.9,
                },
                "reasoning_trace_hash": "hash-abc",
                "reasoning_signature": "sig-reasoning-123",
            },
        }

        # We can't instantiate PostgresAuditStore without a DB URL,
        # but _deserialize_anchor is a regular method we can call directly.
        # Create a minimal instance by bypassing __init__.
        store = object.__new__(PostgresAuditStore)
        anchor = store._deserialize_anchor(record)

        assert anchor.id == "aud-001"
        assert anchor.reasoning_trace is not None
        assert anchor.reasoning_trace.decision == "Approved data analysis"
        assert anchor.reasoning_trace.methodology == "scope_matching"
        assert anchor.reasoning_trace.confidence == 0.9
        assert anchor.reasoning_trace_hash == "hash-abc"
        assert anchor.reasoning_signature == "sig-reasoning-123"

    def test_deserialize_anchor_without_reasoning_trace(self):
        """_deserialize_anchor should handle records without reasoning fields."""
        from kaizen.trust.audit_store import PostgresAuditStore

        record = {
            "id": "aud-002",
            "agent_id": "agent-002",
            "action": "read_data",
            "timestamp": "2026-01-15T13:00:00+00:00",
            "trust_chain_hash": "def456",
            "result": "success",
            "signature": "sig-abc",
            "anchor_data": {
                "context": {},
            },
        }

        store = object.__new__(PostgresAuditStore)
        anchor = store._deserialize_anchor(record)

        assert anchor.id == "aud-002"
        assert anchor.reasoning_trace is None
        assert anchor.reasoning_trace_hash is None
        assert anchor.reasoning_signature is None
