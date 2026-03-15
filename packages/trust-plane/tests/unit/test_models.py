# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane data models."""

from datetime import datetime, timezone

import pytest

from trustplane.models import (
    DecisionRecord,
    DecisionType,
    MilestoneRecord,
    ProjectManifest,
    ReviewRequirement,
)


class TestDecisionRecord:
    def test_create_with_defaults(self):
        record = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="Focus on philosophy only",
            rationale="Separation of concerns",
        )
        assert record.decision_type == DecisionType.SCOPE
        assert record.decision == "Focus on philosophy only"
        assert record.confidence == 0.8
        assert record.review_requirement == ReviewRequirement.STANDARD
        assert record.confidentiality == "public"
        assert record.author == "human"
        assert record.decision_id.startswith("dec-")

    def test_create_with_all_fields(self):
        record = DecisionRecord(
            decision_type=DecisionType.ARGUMENT,
            decision="Mirror Thesis is central",
            rationale="Differentiates from existing frameworks",
            alternatives=["Drop Mirror Thesis", "Make it appendix"],
            evidence=[{"type": "citation", "ref": "Ostrom 1990"}],
            risks=["May be too philosophical for CS audience"],
            review_requirement=ReviewRequirement.FULL,
            confidence=0.95,
            author="Dr. Hong",
        )
        assert record.confidence == 0.95
        assert len(record.alternatives) == 2
        assert len(record.evidence) == 1
        assert len(record.risks) == 1

    def test_confidence_validation(self):
        with pytest.raises(ValueError, match="confidence must be 0.0-1.0"):
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="test",
                rationale="test",
                confidence=1.5,
            )

    def test_confidence_validation_negative(self):
        with pytest.raises(ValueError, match="confidence must be 0.0-1.0"):
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="test",
                rationale="test",
                confidence=-0.1,
            )

    def test_deterministic_id(self):
        ts = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        r1 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="same decision",
            rationale="same rationale",
            timestamp=ts,
        )
        r2 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="same decision",
            rationale="same rationale",
            timestamp=ts,
        )
        # IDs include random nonce to prevent collision — each is unique
        assert r1.decision_id != r2.decision_id
        assert r1.decision_id.startswith("dec-")
        assert r2.decision_id.startswith("dec-")

    def test_different_decisions_different_ids(self):
        ts = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        r1 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="decision A",
            rationale="rationale",
            timestamp=ts,
        )
        r2 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="decision B",
            rationale="rationale",
            timestamp=ts,
        )
        assert r1.decision_id != r2.decision_id

    def test_to_dict_roundtrip(self):
        record = DecisionRecord(
            decision_type=DecisionType.LITERATURE,
            decision="Cite Ostrom 1990",
            rationale="Commons governance is foundational",
            alternatives=["Cite Williamson instead"],
            confidence=0.9,
        )
        data = record.to_dict()
        restored = DecisionRecord.from_dict(data)
        assert restored.decision == record.decision
        assert restored.decision_type == record.decision_type
        assert restored.confidence == record.confidence
        assert restored.decision_id == record.decision_id

    def test_content_hash_deterministic(self):
        ts = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        record = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="test",
            rationale="test",
            timestamp=ts,
        )
        assert record.content_hash() == record.content_hash()

    def test_content_hash_changes_on_modification(self):
        ts = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        r1 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="original",
            rationale="test",
            timestamp=ts,
        )
        r2 = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="modified",
            rationale="test",
            timestamp=ts,
        )
        assert r1.content_hash() != r2.content_hash()


class TestMilestoneRecord:
    def test_create_with_defaults(self):
        ms = MilestoneRecord(version="v0.1", description="First draft")
        assert ms.version == "v0.1"
        assert ms.milestone_id.startswith("ms-")
        assert ms.file_path == ""
        assert ms.file_hash == ""

    def test_create_with_file(self):
        ms = MilestoneRecord(
            version="v0.2",
            description="Revised draft",
            file_path="paper.md",
            file_hash="abc123",
            decision_count=5,
        )
        assert ms.file_path == "paper.md"
        assert ms.decision_count == 5

    def test_to_dict_roundtrip(self):
        ms = MilestoneRecord(
            version="v1.0",
            description="Final version",
            file_path="output.pdf",
            file_hash="deadbeef",
        )
        data = ms.to_dict()
        restored = MilestoneRecord.from_dict(data)
        assert restored.version == ms.version
        assert restored.milestone_id == ms.milestone_id


class TestProjectManifest:
    def test_create(self):
        now = datetime.now(timezone.utc)
        m = ProjectManifest(
            project_id="proj-abc123",
            project_name="Test Project",
            author="Alice",
            created_at=now,
        )
        assert m.total_decisions == 0
        assert m.total_milestones == 0

    def test_to_dict_roundtrip(self):
        now = datetime.now(timezone.utc)
        m = ProjectManifest(
            project_id="proj-abc123",
            project_name="Test Project",
            author="Alice",
            created_at=now,
            genesis_id="gen-xyz",
            chain_hash="hash123",
            constraints=["rule_a", "rule_b"],
        )
        data = m.to_dict()
        restored = ProjectManifest.from_dict(data)
        assert restored.project_id == m.project_id
        assert restored.constraints == ["rule_a", "rule_b"]


class TestReviewRequirement:
    def test_values(self):
        assert ReviewRequirement.QUICK.value == "quick"
        assert ReviewRequirement.STANDARD.value == "standard"
        assert ReviewRequirement.FULL.value == "full"


class TestDecisionType:
    def test_research_types(self):
        types = [t.value for t in DecisionType]
        assert "argument" in types
        assert "literature" in types
        assert "structure" in types
        assert "scope" in types
        assert "framing" in types
        assert "evidence" in types
        assert "methodology" in types

    def test_generic_types(self):
        types = [t.value for t in DecisionType]
        assert "design" in types
        assert "policy" in types
        assert "technical" in types
        assert "process" in types
        assert "trade_off" in types
        assert "requirement" in types


class TestCustomDecisionType:
    """Test that DecisionRecord accepts arbitrary strings as decision_type."""

    def test_custom_string_type(self):
        record = DecisionRecord(
            decision_type="compliance_ruling",
            decision="Accept risk",
            rationale="Within tolerance",
        )
        assert record.decision_type == "compliance_ruling"
        assert record.decision_id.startswith("dec-")

    def test_custom_type_to_dict_roundtrip(self):
        record = DecisionRecord(
            decision_type="financial_allocation",
            decision="Allocate 10k",
            rationale="Budget available",
        )
        data = record.to_dict()
        assert data["decision_type"] == "financial_allocation"

        restored = DecisionRecord.from_dict(data)
        # Custom types stay as strings after roundtrip
        assert restored.decision_type == "financial_allocation"

    def test_custom_type_content_hash(self):
        ts = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        r1 = DecisionRecord(
            decision_type="custom_a",
            decision="same",
            rationale="test",
            timestamp=ts,
        )
        r2 = DecisionRecord(
            decision_type="custom_b",
            decision="same",
            rationale="test",
            timestamp=ts,
        )
        assert r1.content_hash() != r2.content_hash()

    def test_enum_type_roundtrips_to_enum(self):
        record = DecisionRecord(
            decision_type=DecisionType.DESIGN,
            decision="Use microservices",
            rationale="Scalability",
        )
        data = record.to_dict()
        restored = DecisionRecord.from_dict(data)
        # Known enum values roundtrip back to the enum
        assert restored.decision_type == DecisionType.DESIGN


class TestFromDictValidation:
    """TODO-07: from_dict() must raise ValueError on malformed/tampered input."""

    def test_decision_record_missing_required_field(self):
        with pytest.raises(ValueError, match="missing required field 'decision_id'"):
            DecisionRecord.from_dict(
                {
                    "decision_type": "scope",
                    "decision": "x",
                    "rationale": "y",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_decision_record_missing_timestamp(self):
        with pytest.raises(ValueError, match="missing required field 'timestamp'"):
            DecisionRecord.from_dict(
                {
                    "decision_id": "dec-test",
                    "decision_type": "scope",
                    "decision": "x",
                    "rationale": "y",
                }
            )

    def test_decision_record_non_string_id(self):
        with pytest.raises(ValueError, match="'decision_id' must be a string"):
            DecisionRecord.from_dict(
                {
                    "decision_id": 12345,
                    "decision_type": "scope",
                    "decision": "x",
                    "rationale": "y",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_decision_record_nan_confidence(self):
        with pytest.raises(ValueError, match="'confidence' must be a finite number"):
            DecisionRecord.from_dict(
                {
                    "decision_id": "dec-test",
                    "decision_type": "scope",
                    "decision": "x",
                    "rationale": "y",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "confidence": float("nan"),
                }
            )

    def test_decision_record_inf_confidence(self):
        with pytest.raises(ValueError, match="'confidence' must be a finite number"):
            DecisionRecord.from_dict(
                {
                    "decision_id": "dec-test",
                    "decision_type": "scope",
                    "decision": "x",
                    "rationale": "y",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "confidence": float("inf"),
                }
            )

    def test_milestone_record_missing_required_field(self):
        with pytest.raises(ValueError, match="missing required field 'version'"):
            MilestoneRecord.from_dict(
                {
                    "milestone_id": "ms-test",
                    "description": "x",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_milestone_record_non_string_timestamp(self):
        with pytest.raises(ValueError, match="'timestamp' must be an ISO-8601 string"):
            MilestoneRecord.from_dict(
                {
                    "milestone_id": "ms-test",
                    "version": "v1.0",
                    "description": "x",
                    "timestamp": 12345,
                }
            )

    def test_delegate_missing_required_field(self):
        from trustplane.delegation import Delegate

        with pytest.raises(ValueError, match="missing required field 'delegate_id'"):
            Delegate.from_dict(
                {
                    "name": "x",
                    "dimensions": [],
                    "delegated_by": "y",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_delegate_negative_depth(self):
        from trustplane.delegation import Delegate

        with pytest.raises(ValueError, match="'depth' must be a non-negative integer"):
            Delegate.from_dict(
                {
                    "delegate_id": "del-test",
                    "name": "x",
                    "dimensions": ["operational"],
                    "delegated_by": "root",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "depth": -1,
                }
            )

    def test_delegate_non_integer_depth(self):
        from trustplane.delegation import Delegate

        with pytest.raises(ValueError, match="'depth' must be a non-negative integer"):
            Delegate.from_dict(
                {
                    "delegate_id": "del-test",
                    "name": "x",
                    "dimensions": ["operational"],
                    "delegated_by": "root",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "depth": 1.5,
                }
            )
