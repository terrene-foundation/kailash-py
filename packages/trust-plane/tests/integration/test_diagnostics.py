# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for constraint diagnostics (M8-02).

Tests utilization analysis, boundary pressure, gap detection,
quality scoring, suggestion generation, and report formatting.
"""

import json
from collections import Counter

import pytest

from trustplane.diagnostics import (
    _compute_boundary_pressure,
    _compute_quality_score,
    _compute_utilization,
    _detect_gaps,
    _generate_suggestions,
    analyze_constraints,
    format_diagnostics,
)
from trustplane.models import ConstraintEnvelope, OperationalConstraints


@pytest.fixture
def tmp_trust_dir(tmp_path):
    """Trust directory with anchors/ subdirectory."""
    trust = tmp_path / "trust-plane"
    (trust / "anchors").mkdir(parents=True)
    return trust


@pytest.fixture
def sample_envelope():
    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=["draft_content", "cross_reference", "format_output"],
            blocked_actions=["delete_project", "publish_externally"],
        ),
    )


def _write_anchor(anchors_dir, name, action, verdict="auto_approved"):
    """Write a minimal anchor file for diagnostics testing."""
    data = {
        "action": action,
        "timestamp": "2026-03-14T10:00:00+00:00",
        "resource": f"test/{action}",
        "context": {"verification_category": verdict},
    }
    with open(anchors_dir / name, "w") as f:
        json.dump(data, f)


class TestUtilization:
    def test_no_envelope(self):
        result = _compute_utilization(None, Counter())
        assert result["status"] == "no_envelope"
        assert result["percentage"] == 0

    def test_empty_envelope(self):
        env = ConstraintEnvelope()
        result = _compute_utilization(env, Counter())
        assert result["status"] == "unconstrained"

    def test_full_utilization(self, sample_envelope):
        actions = Counter(
            {"draft_content": 5, "cross_reference": 3, "format_output": 2}
        )
        result = _compute_utilization(sample_envelope, actions)
        assert result["status"] == "computed"
        assert result["allowed_utilization_pct"] == 100
        assert result["allowed_unused"] == []

    def test_partial_utilization(self, sample_envelope):
        actions = Counter({"draft_content": 5})
        result = _compute_utilization(sample_envelope, actions)
        assert result["allowed_utilization_pct"] == 33  # 1/3
        assert "cross_reference" in result["allowed_unused"]
        assert "format_output" in result["allowed_unused"]

    def test_blocked_tested(self, sample_envelope):
        actions = Counter({"delete_project": 2})
        result = _compute_utilization(sample_envelope, actions)
        assert "delete_project" in result["blocked_tested"]
        assert "publish_externally" in result["blocked_untested"]


class TestBoundaryPressure:
    def test_no_data(self):
        result = _compute_boundary_pressure(Counter())
        assert result["status"] == "no_data"
        assert result["friction_points"] == []

    def test_no_friction(self):
        verdicts = Counter({"auto_approved": 10})
        result = _compute_boundary_pressure(verdicts)
        assert result["status"] == "computed"
        assert result["friction_points"] == []

    def test_friction_detected(self):
        verdicts = Counter({"auto_approved": 7, "blocked": 3})
        result = _compute_boundary_pressure(verdicts)
        assert len(result["friction_points"]) == 1
        assert result["friction_points"][0]["verdict"] == "blocked"
        assert result["friction_points"][0]["count"] == 3
        assert result["friction_points"][0]["percentage"] == 30

    def test_multiple_friction_types(self):
        verdicts = Counter({"auto_approved": 5, "held": 3, "flagged": 2})
        result = _compute_boundary_pressure(verdicts)
        assert len(result["friction_points"]) == 2

    def test_case_insensitive_friction(self):
        verdicts = Counter({"BLOCKED": 5, "auto_approved": 5})
        result = _compute_boundary_pressure(verdicts)
        assert len(result["friction_points"]) == 1


class TestGapDetection:
    def test_no_envelope(self):
        actions = Counter({"some_action": 1})
        result = _detect_gaps(None, actions)
        assert result["status"] == "no_envelope"
        assert "some_action" in result["unconstrained_actions"]

    def test_no_gaps(self, sample_envelope):
        actions = Counter({"draft_content": 5, "delete_project": 1})
        result = _detect_gaps(sample_envelope, actions)
        assert result["unconstrained_count"] == 0

    def test_gaps_detected(self, sample_envelope):
        actions = Counter({"draft_content": 5, "unknown_action": 3})
        result = _detect_gaps(sample_envelope, actions)
        assert "unknown_action" in result["unconstrained_actions"]
        assert result["unconstrained_count"] == 1

    def test_internal_actions_filtered(self, sample_envelope):
        actions = Counter(
            {"session_start": 1, "posture_change": 1, "enforcement_check": 1}
        )
        result = _detect_gaps(sample_envelope, actions)
        assert result["unconstrained_count"] == 0


class TestQualityScore:
    def test_no_actions(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 0},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_count": 0},
            total_actions=0,
        )
        assert result["score"] == 0
        assert result["level"] == "insufficient_data"

    def test_perfect_score(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 80},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_count": 0},
            total_actions=10,
        )
        assert result["score"] == 100
        assert result["level"] == "well_tuned"

    def test_low_utilization_penalty(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 30},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_count": 0},
            total_actions=10,
        )
        assert result["score"] == 80  # -20 for low utilization

    def test_high_friction_penalty(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 80},
            boundary_pressure={"friction_points": [{"count": 5}]},
            gaps={"unconstrained_count": 0},
            total_actions=10,
        )
        assert result["score"] == 75  # -25 for >30% friction (5/10)

    def test_moderate_friction_penalty(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 80},
            boundary_pressure={"friction_points": [{"count": 2}]},
            gaps={"unconstrained_count": 0},
            total_actions=10,
        )
        assert result["score"] == 90  # -10 for >10% friction (2/10)

    def test_many_gaps_penalty(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 80},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_count": 6},
            total_actions=10,
        )
        assert result["score"] == 75  # -25 for >5 gaps

    def test_no_envelope_penalty(self):
        result = _compute_quality_score(
            utilization={"status": "no_envelope"},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_count": 0},
            total_actions=10,
        )
        assert result["score"] == 60  # -40 for no envelope

    def test_combined_penalties(self):
        result = _compute_quality_score(
            utilization={"status": "computed", "allowed_utilization_pct": 30},
            boundary_pressure={"friction_points": [{"count": 5}]},
            gaps={"unconstrained_count": 6},
            total_actions=10,
        )
        assert result["score"] == 30  # -20 -25 -25 = 30
        assert result["level"] == "major_issues"

    def test_score_never_below_zero(self):
        result = _compute_quality_score(
            utilization={"status": "no_envelope"},
            boundary_pressure={"friction_points": [{"count": 10}]},
            gaps={"unconstrained_count": 10},
            total_actions=10,
        )
        assert result["score"] >= 0


class TestSuggestions:
    def test_no_envelope_suggestion(self):
        suggestions = _generate_suggestions(
            utilization={"status": "no_envelope"},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_actions": []},
        )
        assert any("No constraint envelope" in s for s in suggestions)

    def test_unused_actions_suggestion(self):
        suggestions = _generate_suggestions(
            utilization={
                "status": "computed",
                "allowed_unused": ["action_a", "action_b"],
            },
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_actions": []},
        )
        assert any("Unused allowed actions" in s for s in suggestions)

    def test_untested_blocked_suggestion(self):
        suggestions = _generate_suggestions(
            utilization={"status": "computed", "blocked_untested": ["block_a"]},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_actions": []},
        )
        assert any("Blocked actions never attempted" in s for s in suggestions)

    def test_friction_suggestion(self):
        suggestions = _generate_suggestions(
            utilization={"status": "computed"},
            boundary_pressure={
                "friction_points": [
                    {"verdict": "blocked", "count": 5, "percentage": 50}
                ]
            },
            gaps={"unconstrained_actions": []},
        )
        assert any("High friction" in s for s in suggestions)

    def test_unconstrained_suggestion(self):
        suggestions = _generate_suggestions(
            utilization={"status": "computed"},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_actions": ["rogue_action"]},
        )
        assert any("Unconstrained actions" in s for s in suggestions)

    def test_well_tuned_no_suggestions(self):
        suggestions = _generate_suggestions(
            utilization={"status": "computed"},
            boundary_pressure={"friction_points": []},
            gaps={"unconstrained_actions": []},
        )
        assert len(suggestions) == 0


class TestAnalyzeConstraints:
    def test_empty_project(self, tmp_trust_dir):
        report = analyze_constraints(tmp_trust_dir)
        assert report["total_actions"] == 0
        assert report["quality_score"]["level"] == "insufficient_data"

    def test_with_anchors(self, tmp_trust_dir, sample_envelope):
        anchors = tmp_trust_dir / "anchors"
        _write_anchor(anchors, "001.json", "draft_content", "auto_approved")
        _write_anchor(anchors, "002.json", "cross_reference", "auto_approved")
        _write_anchor(anchors, "003.json", "delete_project", "blocked")

        report = analyze_constraints(tmp_trust_dir, envelope=sample_envelope)
        assert report["total_actions"] == 3
        assert report["verdict_distribution"]["auto_approved"] == 2
        assert report["verdict_distribution"]["blocked"] == 1

    def test_with_no_envelope(self, tmp_trust_dir):
        anchors = tmp_trust_dir / "anchors"
        _write_anchor(anchors, "001.json", "some_action")

        report = analyze_constraints(tmp_trust_dir, envelope=None)
        assert report["utilization"]["status"] == "no_envelope"
        assert any("No constraint envelope" in s for s in report["suggestions"])


class TestFormatDiagnostics:
    def test_empty_report(self):
        report = analyze_constraints("/nonexistent")
        text = format_diagnostics(report)
        assert "Quality Score" in text
        assert "No actions recorded" in text

    def test_formatted_report_has_sections(self, tmp_trust_dir, sample_envelope):
        anchors = tmp_trust_dir / "anchors"
        _write_anchor(anchors, "001.json", "draft_content", "auto_approved")
        _write_anchor(anchors, "002.json", "delete_project", "blocked")

        report = analyze_constraints(tmp_trust_dir, envelope=sample_envelope)
        text = format_diagnostics(report)
        assert "Quality Score" in text
        assert "Utilization" in text
