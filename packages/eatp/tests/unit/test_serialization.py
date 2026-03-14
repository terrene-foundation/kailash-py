# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for to_dict()/from_dict() serialization on dataclasses.

Covers round-trip serialization for:
- BehavioralData (scoring.py)
- BehavioralScore (scoring.py)
- CombinedTrustScore (scoring.py)
- HookContext (hooks.py)
- HookResult (hooks.py)
- EvidenceReference (reasoning.py) — already has to_dict/from_dict, verified here

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from eatp.hooks import HookContext, HookResult, HookType
from eatp.reasoning import EvidenceReference
from eatp.scoring import (
    BehavioralData,
    BehavioralScore,
    CombinedTrustScore,
    TrustScore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)


def _make_trust_score() -> TrustScore:
    """Create a representative TrustScore for testing."""
    return TrustScore(
        score=85,
        breakdown={
            "chain_completeness": 28.5,
            "delegation_depth": 14.25,
            "constraint_coverage": 20.0,
            "posture_level": 16.0,
            "chain_recency": 6.25,
        },
        grade="B",
        computed_at=NOW,
        agent_id="agent-001",
    )


# ===================================================================
# BehavioralData
# ===================================================================


class TestBehavioralDataSerialization:
    """Tests for BehavioralData.to_dict() and BehavioralData.from_dict()."""

    def test_to_dict_returns_dict(self) -> None:
        data = BehavioralData(
            total_actions=100,
            approved_actions=90,
            denied_actions=5,
            error_count=5,
            posture_transitions=2,
            time_at_current_posture_hours=48.5,
            observation_window_hours=168.0,
        )
        result = data.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_all_fields_present(self) -> None:
        data = BehavioralData(
            total_actions=100,
            approved_actions=90,
            denied_actions=5,
            error_count=5,
            posture_transitions=2,
            time_at_current_posture_hours=48.5,
            observation_window_hours=168.0,
        )
        result = data.to_dict()
        expected_keys = {
            "total_actions",
            "approved_actions",
            "denied_actions",
            "error_count",
            "posture_transitions",
            "time_at_current_posture_hours",
            "observation_window_hours",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_values_match(self) -> None:
        data = BehavioralData(
            total_actions=100,
            approved_actions=90,
            denied_actions=5,
            error_count=5,
            posture_transitions=2,
            time_at_current_posture_hours=48.5,
            observation_window_hours=168.0,
        )
        result = data.to_dict()
        assert result["total_actions"] == 100
        assert result["approved_actions"] == 90
        assert result["denied_actions"] == 5
        assert result["error_count"] == 5
        assert result["posture_transitions"] == 2
        assert result["time_at_current_posture_hours"] == 48.5
        assert result["observation_window_hours"] == 168.0

    def test_round_trip(self) -> None:
        original = BehavioralData(
            total_actions=200,
            approved_actions=180,
            denied_actions=10,
            error_count=10,
            posture_transitions=3,
            time_at_current_posture_hours=72.0,
            observation_window_hours=336.0,
        )
        reconstructed = BehavioralData.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_defaults(self) -> None:
        """Round-trip with all-default (zero) values."""
        original = BehavioralData()
        reconstructed = BehavioralData.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(BehavioralData.__dict__["from_dict"], classmethod)


# ===================================================================
# BehavioralScore
# ===================================================================


class TestBehavioralScoreSerialization:
    """Tests for BehavioralScore.to_dict() and BehavioralScore.from_dict()."""

    def test_to_dict_returns_dict(self) -> None:
        score = BehavioralScore(
            score=75,
            breakdown={"approval_rate": 22.5, "error_rate": 20.0},
            grade="C",
            computed_at=NOW,
            agent_id="agent-002",
        )
        result = score.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_all_fields_present(self) -> None:
        score = BehavioralScore(
            score=75,
            breakdown={"approval_rate": 22.5},
            grade="C",
            computed_at=NOW,
            agent_id="agent-002",
        )
        result = score.to_dict()
        expected_keys = {"score", "breakdown", "grade", "computed_at", "agent_id"}
        assert set(result.keys()) == expected_keys

    def test_datetime_serialized_as_isoformat(self) -> None:
        score = BehavioralScore(
            score=75,
            breakdown={},
            grade="C",
            computed_at=NOW,
            agent_id="agent-002",
        )
        result = score.to_dict()
        assert result["computed_at"] == NOW.isoformat()
        assert isinstance(result["computed_at"], str)

    def test_round_trip(self) -> None:
        original = BehavioralScore(
            score=92,
            breakdown={
                "approval_rate": 27.0,
                "error_rate": 23.75,
                "posture_stability": 18.0,
                "time_at_posture": 14.0,
                "interaction_volume": 9.25,
            },
            grade="A",
            computed_at=NOW,
            agent_id="agent-003",
        )
        reconstructed = BehavioralScore.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(BehavioralScore.__dict__["from_dict"], classmethod)


# ===================================================================
# CombinedTrustScore
# ===================================================================


class TestCombinedTrustScoreSerialization:
    """Tests for CombinedTrustScore.to_dict()/from_dict()."""

    def test_to_dict_returns_dict(self) -> None:
        combined = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=None,
            combined_score=85,
            breakdown={
                "structural_weight": 1.0,
                "behavioral_weight": 0.0,
                "structural_contribution": 85,
                "behavioral_contribution": 0,
            },
        )
        result = combined.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_all_fields_present(self) -> None:
        combined = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=None,
            combined_score=85,
            breakdown={"structural_weight": 1.0},
        )
        result = combined.to_dict()
        expected_keys = {
            "structural_score",
            "behavioral_score",
            "combined_score",
            "breakdown",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_structural_score_nested(self) -> None:
        """structural_score should be serialized as a dict, not a TrustScore."""
        combined = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=None,
            combined_score=85,
            breakdown={},
        )
        result = combined.to_dict()
        assert isinstance(result["structural_score"], dict)
        assert result["structural_score"]["score"] == 85
        assert result["structural_score"]["agent_id"] == "agent-001"

    def test_to_dict_behavioral_score_none(self) -> None:
        combined = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=None,
            combined_score=85,
            breakdown={},
        )
        result = combined.to_dict()
        assert result["behavioral_score"] is None

    def test_to_dict_behavioral_score_nested(self) -> None:
        behavioral = BehavioralScore(
            score=70,
            breakdown={"approval_rate": 21.0},
            grade="C",
            computed_at=NOW,
            agent_id="agent-001",
        )
        combined = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=behavioral,
            combined_score=79,
            breakdown={
                "structural_weight": 0.6,
                "behavioral_weight": 0.4,
            },
        )
        result = combined.to_dict()
        assert isinstance(result["behavioral_score"], dict)
        assert result["behavioral_score"]["score"] == 70

    def test_round_trip_without_behavioral(self) -> None:
        original = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=None,
            combined_score=85,
            breakdown={
                "structural_weight": 1.0,
                "behavioral_weight": 0.0,
                "structural_contribution": 85,
                "behavioral_contribution": 0,
            },
        )
        reconstructed = CombinedTrustScore.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_with_behavioral(self) -> None:
        behavioral = BehavioralScore(
            score=70,
            breakdown={
                "approval_rate": 21.0,
                "error_rate": 18.75,
                "posture_stability": 14.0,
                "time_at_posture": 10.5,
                "interaction_volume": 5.75,
            },
            grade="C",
            computed_at=NOW,
            agent_id="agent-001",
        )
        original = CombinedTrustScore(
            structural_score=_make_trust_score(),
            behavioral_score=behavioral,
            combined_score=79,
            breakdown={
                "structural_weight": 0.6,
                "behavioral_weight": 0.4,
                "structural_contribution": 51.0,
                "behavioral_contribution": 28.0,
            },
        )
        reconstructed = CombinedTrustScore.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(CombinedTrustScore.__dict__["from_dict"], classmethod)


# ===================================================================
# HookContext
# ===================================================================


class TestHookContextSerialization:
    """Tests for HookContext.to_dict() and HookContext.from_dict()."""

    def test_to_dict_returns_dict(self) -> None:
        ctx = HookContext(
            agent_id="agent-001",
            action="read_data",
            hook_type=HookType.PRE_VERIFICATION,
            metadata={"key": "value"},
            timestamp=NOW,
        )
        result = ctx.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_all_fields_present(self) -> None:
        ctx = HookContext(
            agent_id="agent-001",
            action="read_data",
            hook_type=HookType.PRE_VERIFICATION,
            metadata={},
            timestamp=NOW,
        )
        result = ctx.to_dict()
        expected_keys = {"agent_id", "action", "hook_type", "metadata", "timestamp"}
        assert set(result.keys()) == expected_keys

    def test_enum_serialized_as_value(self) -> None:
        ctx = HookContext(
            agent_id="agent-001",
            action="read_data",
            hook_type=HookType.POST_DELEGATION,
            metadata={},
            timestamp=NOW,
        )
        result = ctx.to_dict()
        assert result["hook_type"] == "post_delegation"
        assert isinstance(result["hook_type"], str)

    def test_datetime_serialized_as_isoformat(self) -> None:
        ctx = HookContext(
            agent_id="agent-001",
            action="read_data",
            hook_type=HookType.PRE_VERIFICATION,
            metadata={},
            timestamp=NOW,
        )
        result = ctx.to_dict()
        assert result["timestamp"] == NOW.isoformat()
        assert isinstance(result["timestamp"], str)

    def test_round_trip(self) -> None:
        original = HookContext(
            agent_id="agent-007",
            action="delegate_task",
            hook_type=HookType.PRE_DELEGATION,
            metadata={"task_id": "t-123", "priority": 5},
            timestamp=NOW,
        )
        reconstructed = HookContext.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_all_hook_types(self) -> None:
        """Verify round-trip works for all HookType enum values."""
        for hook_type in HookType:
            original = HookContext(
                agent_id="agent-001",
                action="test",
                hook_type=hook_type,
                metadata={},
                timestamp=NOW,
            )
            reconstructed = HookContext.from_dict(original.to_dict())
            assert reconstructed == original, f"Round-trip failed for {hook_type}"

    def test_round_trip_empty_metadata(self) -> None:
        original = HookContext(
            agent_id="agent-001",
            action="test",
            hook_type=HookType.POST_VERIFICATION,
            metadata={},
            timestamp=NOW,
        )
        reconstructed = HookContext.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(HookContext.__dict__["from_dict"], classmethod)


# ===================================================================
# HookResult
# ===================================================================


class TestHookResultSerialization:
    """Tests for HookResult.to_dict() and HookResult.from_dict()."""

    def test_to_dict_returns_dict(self) -> None:
        result = HookResult(allow=True, reason="all good")
        d = result.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_all_fields_present(self) -> None:
        result = HookResult(
            allow=False,
            reason="rate limited",
            modified_context={"extra": "data"},
        )
        d = result.to_dict()
        expected_keys = {"allow", "reason", "modified_context"}
        assert set(d.keys()) == expected_keys

    def test_to_dict_values_match(self) -> None:
        result = HookResult(
            allow=False,
            reason="denied",
            modified_context={"flag": True},
        )
        d = result.to_dict()
        assert d["allow"] is False
        assert d["reason"] == "denied"
        assert d["modified_context"] == {"flag": True}

    def test_round_trip_allow_true(self) -> None:
        original = HookResult(allow=True, reason=None, modified_context=None)
        reconstructed = HookResult.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_allow_false_with_reason(self) -> None:
        original = HookResult(
            allow=False,
            reason="Hook rate_limiter denied pre_verification",
            modified_context=None,
        )
        reconstructed = HookResult.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_with_modified_context(self) -> None:
        original = HookResult(
            allow=True,
            reason="approved with metadata",
            modified_context={"injected_key": "injected_value", "count": 42},
        )
        reconstructed = HookResult.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(HookResult.__dict__["from_dict"], classmethod)


# ===================================================================
# EvidenceReference (already has to_dict/from_dict — verification)
# ===================================================================


class TestEvidenceReferenceSerialization:
    """Verify existing EvidenceReference serialization still works."""

    def test_round_trip_with_summary(self) -> None:
        original = EvidenceReference(
            evidence_type="document",
            reference="https://example.com/doc.pdf",
            summary="Quarterly compliance report",
        )
        reconstructed = EvidenceReference.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_without_summary(self) -> None:
        original = EvidenceReference(
            evidence_type="metric",
            reference="prometheus://cpu_usage_avg",
        )
        reconstructed = EvidenceReference.from_dict(original.to_dict())
        assert reconstructed == original

    def test_to_dict_all_fields_with_summary(self) -> None:
        ref = EvidenceReference(
            evidence_type="audit_log",
            reference="/var/log/audit.log",
            summary="System audit log",
        )
        d = ref.to_dict()
        assert d["evidence_type"] == "audit_log"
        assert d["reference"] == "/var/log/audit.log"
        assert d["summary"] == "System audit log"

    def test_to_dict_omits_summary_when_none(self) -> None:
        ref = EvidenceReference(
            evidence_type="external_api",
            reference="https://api.example.com/status",
        )
        d = ref.to_dict()
        assert "summary" not in d


# ===================================================================
# TrustScore (used as nested field in CombinedTrustScore)
# ===================================================================


class TestTrustScoreSerialization:
    """Tests for TrustScore.to_dict() and TrustScore.from_dict().

    TrustScore needs to_dict/from_dict because it is nested inside
    CombinedTrustScore. These are added alongside the other dataclasses.
    """

    def test_to_dict_returns_dict(self) -> None:
        ts = _make_trust_score()
        result = ts.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_all_fields_present(self) -> None:
        ts = _make_trust_score()
        result = ts.to_dict()
        expected_keys = {"score", "breakdown", "grade", "computed_at", "agent_id"}
        assert set(result.keys()) == expected_keys

    def test_datetime_serialized_as_isoformat(self) -> None:
        ts = _make_trust_score()
        result = ts.to_dict()
        assert result["computed_at"] == NOW.isoformat()

    def test_round_trip(self) -> None:
        original = _make_trust_score()
        reconstructed = TrustScore.from_dict(original.to_dict())
        assert reconstructed == original

    def test_from_dict_type_is_classmethod(self) -> None:
        assert isinstance(TrustScore.__dict__["from_dict"], classmethod)
