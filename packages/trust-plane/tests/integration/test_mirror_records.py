# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for Mirror Thesis record types (M5-01).

Tests ExecutionRecord, EscalationRecord, InterventionRecord,
HumanCompetency enum, VerificationCategory enum, and the
project-level recording methods.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from trustplane.models import (
    EscalationRecord,
    ExecutionRecord,
    HumanCompetency,
    InterventionRecord,
    VerificationCategory,
)
from trustplane.project import TrustProject


@pytest.fixture
def tmp_trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def project(tmp_trust_dir):
    return asyncio.run(
        TrustProject.create(
            trust_dir=str(tmp_trust_dir),
            project_name="Mirror Test",
            author="Test Author",
        )
    )


# --- Model Tests ---


class TestHumanCompetency:
    def test_all_six_categories(self):
        assert len(HumanCompetency) == 6
        expected = {
            "ethical_judgment",
            "relationship_capital",
            "contextual_wisdom",
            "creative_synthesis",
            "emotional_intelligence",
            "cultural_navigation",
        }
        assert {c.value for c in HumanCompetency} == expected

    def test_invalid_competency_raises(self):
        with pytest.raises(ValueError):
            HumanCompetency("nonexistent")


class TestVerificationCategory:
    def test_all_four_categories(self):
        assert len(VerificationCategory) == 4
        expected = {"auto_approved", "flagged", "held", "blocked"}
        assert {v.value for v in VerificationCategory} == expected


class TestExecutionRecord:
    def test_creation_with_defaults(self):
        record = ExecutionRecord(action="draft_content")
        assert record.action == "draft_content"
        assert record.verification_category == VerificationCategory.AUTO_APPROVED
        assert record.confidence == 0.95
        assert record.execution_id.startswith("exec-")

    def test_to_dict_includes_record_type(self):
        record = ExecutionRecord(action="draft_content")
        d = record.to_dict()
        assert d["record_type"] == "execution"
        assert d["action"] == "draft_content"

    def test_from_dict_roundtrip(self):
        original = ExecutionRecord(
            action="cross_reference",
            constraint_reference="operational.allowed_actions",
            confidence=0.99,
        )
        restored = ExecutionRecord.from_dict(original.to_dict())
        assert restored.action == original.action
        assert restored.constraint_reference == original.constraint_reference
        assert restored.confidence == original.confidence
        assert restored.execution_id == original.execution_id

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError):
            ExecutionRecord(action="test", confidence=1.5)


class TestEscalationRecord:
    def test_creation_with_competencies(self):
        record = EscalationRecord(
            trigger="Claim exceeds evidence threshold",
            recommendation="Verify source before publishing",
            competency_categories=[
                HumanCompetency.ETHICAL_JUDGMENT,
                HumanCompetency.CONTEXTUAL_WISDOM,
            ],
            constraint_dimension="operational",
        )
        assert record.trigger == "Claim exceeds evidence threshold"
        assert len(record.competency_categories) == 2
        assert record.verification_category == VerificationCategory.HELD
        assert record.escalation_id.startswith("esc-")

    def test_to_dict_roundtrip(self):
        original = EscalationRecord(
            trigger="Budget limit approached",
            recommendation="Approve additional spend",
            human_response="Approved with conditions",
            human_authority="Dr. Jack Hong",
            competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
            constraint_dimension="financial",
            resolution="approved",
        )
        restored = EscalationRecord.from_dict(original.to_dict())
        assert restored.trigger == original.trigger
        assert restored.human_response == original.human_response
        assert restored.human_authority == original.human_authority
        assert restored.competency_categories == original.competency_categories
        assert restored.constraint_dimension == original.constraint_dimension
        assert restored.resolution == original.resolution

    def test_empty_competencies_allowed(self):
        record = EscalationRecord(trigger="Mechanical constraint hit")
        assert record.competency_categories == []
        d = record.to_dict()
        assert d["competency_categories"] == []
        restored = EscalationRecord.from_dict(d)
        assert restored.competency_categories == []


class TestInterventionRecord:
    def test_creation(self):
        record = InterventionRecord(
            observation="Overclaim in abstract — 'first' without survey",
            action_taken="Softened to 'among the first'",
            human_authority="Dr. Jack Hong",
            competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
        )
        assert record.observation == "Overclaim in abstract — 'first' without survey"
        assert record.confidence == 0.5
        assert record.intervention_id.startswith("int-")

    def test_to_dict_roundtrip(self):
        original = InterventionRecord(
            observation="Stakeholder sensitivity missed",
            action_taken="Reframed positioning to avoid disparaging competitors",
            human_authority="Jane Doe",
            competency_categories=[
                HumanCompetency.RELATIONSHIP_CAPITAL,
                HumanCompetency.CULTURAL_NAVIGATION,
            ],
        )
        restored = InterventionRecord.from_dict(original.to_dict())
        assert restored.observation == original.observation
        assert restored.action_taken == original.action_taken
        assert restored.human_authority == original.human_authority
        assert len(restored.competency_categories) == 2
        assert HumanCompetency.RELATIONSHIP_CAPITAL in restored.competency_categories
        assert HumanCompetency.CULTURAL_NAVIGATION in restored.competency_categories

    def test_multiple_competencies(self):
        record = InterventionRecord(
            observation="Cultural context missing",
            competency_categories=[
                HumanCompetency.CULTURAL_NAVIGATION,
                HumanCompetency.EMOTIONAL_INTELLIGENCE,
                HumanCompetency.CREATIVE_SYNTHESIS,
            ],
        )
        d = record.to_dict()
        assert len(d["competency_categories"]) == 3


# --- Project Integration Tests ---


class TestProjectMirrorRecording:
    def test_record_execution(self, project):
        record = ExecutionRecord(
            action="draft_content",
            constraint_reference="operational.allowed_actions",
        )
        exec_id = asyncio.run(project.record_execution(record))
        assert exec_id == record.execution_id

        # Verify anchor was created
        anchors = list((project._dir / "anchors").glob("*.json"))
        assert len(anchors) >= 1

    def test_record_execution_populates_envelope_hash(self, project):
        record = ExecutionRecord(action="draft_content")
        asyncio.run(project.record_execution(record))
        # envelope_hash should be populated if envelope exists
        # (no envelope in default test project, so empty)
        assert record.envelope_hash == ""

    def test_record_escalation(self, project):
        record = EscalationRecord(
            trigger="Publication claim needs verification",
            recommendation="Check against source material",
            competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
            constraint_dimension="operational",
            human_authority="Test Author",
        )
        esc_id = asyncio.run(project.record_escalation(record))
        assert esc_id == record.escalation_id

    def test_record_intervention(self, project):
        record = InterventionRecord(
            observation="Audience framing is wrong for government context",
            action_taken="Reframed as risk mitigation narrative",
            human_authority="Test Author",
            competency_categories=[HumanCompetency.CONTEXTUAL_WISDOM],
        )
        int_id = asyncio.run(project.record_intervention(record))
        assert int_id == record.intervention_id

    def test_get_mirror_records_empty(self, project):
        records = project.get_mirror_records()
        assert records["executions"] == []
        assert records["escalations"] == []
        assert records["interventions"] == []

    def test_get_mirror_records_after_recording(self, project):
        # Record one of each type
        asyncio.run(project.record_execution(ExecutionRecord(action="format_output")))
        asyncio.run(
            project.record_escalation(
                EscalationRecord(
                    trigger="Need ethical review",
                    competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
                )
            )
        )
        asyncio.run(
            project.record_intervention(
                InterventionRecord(
                    observation="Spotted overclaim",
                    competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
                    human_authority="Test Author",
                )
            )
        )

        records = project.get_mirror_records()
        assert len(records["executions"]) == 1
        assert len(records["escalations"]) == 1
        assert len(records["interventions"]) == 1
        assert records["executions"][0].action == "format_output"
        assert records["escalations"][0].trigger == "Need ethical review"
        assert records["interventions"][0].observation == "Spotted overclaim"

    def test_mirror_records_with_session(self, project):
        session = asyncio.run(project.start_session())
        asyncio.run(project.record_execution(ExecutionRecord(action="cross_reference")))
        asyncio.run(
            project.record_escalation(EscalationRecord(trigger="Scope question"))
        )
        summary = asyncio.run(project.end_session())
        assert summary["total_actions"] >= 2

    def test_decision_record_still_works(self, project):
        """Backward compat: DecisionRecord works alongside Mirror types."""
        from trustplane.models import DecisionRecord, DecisionType

        dec = DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="Focus on X",
            rationale="Because Y",
        )
        dec_id = asyncio.run(project.record_decision(dec))
        assert dec_id == dec.decision_id

        # Mirror records should not include decision records
        records = project.get_mirror_records()
        assert len(records["executions"]) == 0
        assert len(records["escalations"]) == 0
        assert len(records["interventions"]) == 0

    def test_envelope_hash_populated_with_envelope(self, tmp_path):
        """When project has constraint envelope, mirror records get its hash."""
        from trustplane.models import ConstraintEnvelope, OperationalConstraints

        trust_dir = tmp_path / "tp-envelope"
        envelope = ConstraintEnvelope(
            operational=OperationalConstraints(
                allowed_actions=["draft_content"],
            ),
            signed_by="Test Author",
        )
        project = asyncio.run(
            TrustProject.create(
                trust_dir=str(trust_dir),
                project_name="Envelope Test",
                author="Test Author",
                constraint_envelope=envelope,
            )
        )

        record = ExecutionRecord(action="draft_content")
        asyncio.run(project.record_execution(record))
        assert record.envelope_hash == envelope.envelope_hash()
