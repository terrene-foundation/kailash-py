# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for competency map generation (M5-02).

Tests build_competency_map(), format_competency_map(), and
the attest mirror CLI integration.
"""

import asyncio
import json

import pytest

from kailash.trust.plane.mirror import (
    build_competency_map,
    competency_map_json,
    format_competency_map,
)
from kailash.trust.plane.models import (
    EscalationRecord,
    ExecutionRecord,
    HumanCompetency,
    InterventionRecord,
)
from kailash.trust.plane.project import TrustProject


@pytest.fixture
def tmp_trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def project(tmp_trust_dir):
    return asyncio.run(
        TrustProject.create(
            trust_dir=str(tmp_trust_dir),
            project_name="Mirror Map Test",
            author="Test Author",
        )
    )


def _empty_records():
    return {"executions": [], "escalations": [], "interventions": []}


def _mixed_records():
    return {
        "executions": [
            ExecutionRecord(action="draft_content"),
            ExecutionRecord(action="draft_content"),
            ExecutionRecord(action="cross_reference"),
            ExecutionRecord(action="format_output"),
        ],
        "escalations": [
            EscalationRecord(
                trigger="Claim verification needed",
                competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
            ),
            EscalationRecord(
                trigger="Audience framing question",
                competency_categories=[HumanCompetency.CONTEXTUAL_WISDOM],
            ),
        ],
        "interventions": [
            InterventionRecord(
                observation="Spotted overclaim AI missed",
                competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
                human_authority="Dr. Hong",
            ),
        ],
    }


class TestBuildCompetencyMap:
    def test_empty_project(self):
        cmap = build_competency_map(_empty_records(), project_name="Empty")
        assert cmap["total_actions"] == 0
        assert cmap["message"] == "No mirror data yet"

    def test_single_execution(self):
        records = _empty_records()
        records["executions"] = [ExecutionRecord(action="draft_content")]
        cmap = build_competency_map(records, project_name="Single")
        assert cmap["total_actions"] == 1
        assert cmap["autonomous"]["count"] == 1
        assert cmap["autonomous"]["percentage"] == 100
        assert cmap["escalated"]["count"] == 0
        assert cmap["intervened"]["count"] == 0

    def test_mixed_records(self):
        cmap = build_competency_map(_mixed_records(), project_name="Mixed")
        assert cmap["total_actions"] == 7
        assert cmap["autonomous"]["count"] == 4
        assert cmap["escalated"]["count"] == 2
        assert cmap["intervened"]["count"] == 1

    def test_competency_categorization(self):
        cmap = build_competency_map(_mixed_records())
        # Escalated competencies
        assert "ethical_judgment" in cmap["escalated"]["by_competency"]
        assert "contextual_wisdom" in cmap["escalated"]["by_competency"]
        # Intervened competencies
        assert "ethical_judgment" in cmap["intervened"]["by_competency"]

    def test_action_breakdown(self):
        cmap = build_competency_map(_mixed_records())
        actions = cmap["autonomous"]["by_action"]
        assert actions["draft_content"] == 2
        assert actions["cross_reference"] == 1
        assert actions["format_output"] == 1

    def test_pattern_identification(self):
        cmap = build_competency_map(_mixed_records())
        patterns = cmap["patterns"]
        # draft_content appears 2+ times → AI reliable
        assert "draft_content" in patterns["ai_reliable"]
        # ethical_judgment is top escalation competency
        assert "ethical_judgment" in patterns["human_judgment_needed"]
        # ethical_judgment is top intervention competency
        assert "ethical_judgment" in patterns["human_detects_missed"]

    def test_proportions_correct(self):
        cmap = build_competency_map(_mixed_records())
        # 4/7 ≈ 57%, 2/7 ≈ 29%, 1/7 ≈ 14%
        assert cmap["autonomous"]["percentage"] == 57
        assert cmap["escalated"]["percentage"] == 29
        assert cmap["intervened"]["percentage"] == 14

    def test_uncategorized_competencies(self):
        records = _empty_records()
        records["escalations"] = [
            EscalationRecord(trigger="Mechanical limit hit"),
        ]
        cmap = build_competency_map(records)
        assert "uncategorized" in cmap["escalated"]["by_competency"]

    def test_period_metadata(self):
        cmap = build_competency_map(
            _mixed_records(),
            project_name="Test",
            period_start="2026-03-14",
            period_end="2026-03-18",
        )
        assert cmap["period_start"] == "2026-03-14"
        assert cmap["period_end"] == "2026-03-18"


class TestFormatCompetencyMap:
    def test_empty_format(self):
        cmap = build_competency_map(_empty_records(), project_name="Empty")
        text = format_competency_map(cmap)
        assert "No mirror data yet" in text
        assert "Empty" in text

    def test_mixed_format(self):
        cmap = build_competency_map(_mixed_records(), project_name="CARE Thesis")
        text = format_competency_map(cmap)
        assert "CARE Thesis" in text
        assert "Autonomous" in text
        assert "Escalated" in text
        assert "Intervened" in text
        assert "draft_content" in text
        assert "ethical judgment" in text

    def test_patterns_in_format(self):
        cmap = build_competency_map(_mixed_records(), project_name="Test")
        text = format_competency_map(cmap)
        assert "Emerging Patterns:" in text
        assert "AI reliably handles" in text

    def test_period_in_format(self):
        cmap = build_competency_map(
            _mixed_records(),
            period_start="2026-03-14",
            period_end="2026-03-18",
        )
        text = format_competency_map(cmap)
        assert "2026-03-14 to 2026-03-18" in text


class TestCompetencyMapJson:
    def test_valid_json(self):
        cmap = build_competency_map(_mixed_records())
        result = competency_map_json(cmap)
        parsed = json.loads(result)
        assert parsed["total_actions"] == 7

    def test_empty_json(self):
        cmap = build_competency_map(_empty_records())
        result = competency_map_json(cmap)
        parsed = json.loads(result)
        assert parsed["total_actions"] == 0


class TestProjectMirrorIntegration:
    def test_full_workflow(self, project):
        """Full workflow: record → mirror."""
        # Record mixed types
        asyncio.run(project.record_execution(ExecutionRecord(action="draft_content")))
        asyncio.run(project.record_execution(ExecutionRecord(action="draft_content")))
        asyncio.run(project.record_execution(ExecutionRecord(action="cross_reference")))
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
                    observation="Overclaim spotted",
                    competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
                    human_authority="Test Author",
                )
            )
        )

        # Build competency map
        records = project.get_mirror_records()
        cmap = build_competency_map(records, project_name="Mirror Map Test")

        assert cmap["total_actions"] == 5
        assert cmap["autonomous"]["count"] == 3
        assert cmap["escalated"]["count"] == 1
        assert cmap["intervened"]["count"] == 1
        assert "draft_content" in cmap["patterns"]["ai_reliable"]

    def test_mirror_survives_across_sessions(self, project):
        """Mirror data persists across sessions."""
        asyncio.run(project.start_session())
        asyncio.run(project.record_execution(ExecutionRecord(action="format_output")))
        asyncio.run(project.end_session())

        asyncio.run(project.start_session())
        asyncio.run(
            project.record_escalation(
                EscalationRecord(
                    trigger="Scope question",
                    competency_categories=[HumanCompetency.CONTEXTUAL_WISDOM],
                )
            )
        )
        asyncio.run(project.end_session())

        records = project.get_mirror_records()
        assert len(records["executions"]) == 1
        assert len(records["escalations"]) == 1

    def test_all_six_competencies(self, project):
        """Each of the six competency categories can appear."""
        for comp in HumanCompetency:
            asyncio.run(
                project.record_escalation(
                    EscalationRecord(
                        trigger=f"Test {comp.value}",
                        competency_categories=[comp],
                    )
                )
            )

        records = project.get_mirror_records()
        assert len(records["escalations"]) == 6
        cmap = build_competency_map(records)
        by_comp = cmap["escalated"]["by_competency"]
        for comp in HumanCompetency:
            assert comp.value in by_comp
