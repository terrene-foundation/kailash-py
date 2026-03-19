# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for PostureEvidence, PostureEvaluationResult, and PostureStore protocol.

Tests cover:
- PostureEvidence: construction, validation, serialization roundtrip
- PostureEvaluationResult: construction, decision validation, serialization roundtrip
- PostureStore: runtime_checkable protocol verification
- PostureStateMachine: backward compatibility with store=None
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from eatp.postures import (
    PostureEvidence,
    PostureEvaluationResult,
    PostureStateMachine,
    PostureStore,
    PostureTransitionRequest,
    TransitionResult,
    TrustPosture,
)


# ---------------------------------------------------------------------------
# PostureEvidence tests
# ---------------------------------------------------------------------------


class TestPostureEvidence:
    """Tests for the PostureEvidence dataclass."""

    def test_posture_evidence_valid(self) -> None:
        """Construct PostureEvidence with valid data."""
        evidence = PostureEvidence(
            observation_count=100,
            success_rate=0.95,
            time_at_current_posture_hours=48.0,
            anomaly_count=2,
            source="behavioral_monitor",
        )
        assert evidence.observation_count == 100
        assert evidence.success_rate == 0.95
        assert evidence.time_at_current_posture_hours == 48.0
        assert evidence.anomaly_count == 2
        assert evidence.source == "behavioral_monitor"
        assert isinstance(evidence.timestamp, datetime)
        assert evidence.metadata == {}

    def test_posture_evidence_rejects_nan_success_rate(self) -> None:
        """math.isfinite check rejects NaN for success_rate."""
        with pytest.raises(ValueError, match="success_rate must be finite"):
            PostureEvidence(
                observation_count=10,
                success_rate=float("nan"),
                time_at_current_posture_hours=1.0,
                anomaly_count=0,
                source="test",
            )

    def test_posture_evidence_rejects_inf_success_rate(self) -> None:
        """math.isfinite check rejects Inf for success_rate."""
        with pytest.raises(ValueError, match="success_rate must be finite"):
            PostureEvidence(
                observation_count=10,
                success_rate=float("inf"),
                time_at_current_posture_hours=1.0,
                anomaly_count=0,
                source="test",
            )

    def test_posture_evidence_rejects_inf_time(self) -> None:
        """math.isfinite check rejects Inf for time_at_current_posture_hours."""
        with pytest.raises(
            ValueError, match="time_at_current_posture_hours must be finite"
        ):
            PostureEvidence(
                observation_count=10,
                success_rate=0.9,
                time_at_current_posture_hours=float("inf"),
                anomaly_count=0,
                source="test",
            )

    def test_posture_evidence_rejects_nan_time(self) -> None:
        """math.isfinite check rejects NaN for time_at_current_posture_hours."""
        with pytest.raises(
            ValueError, match="time_at_current_posture_hours must be finite"
        ):
            PostureEvidence(
                observation_count=10,
                success_rate=0.9,
                time_at_current_posture_hours=float("nan"),
                anomaly_count=0,
                source="test",
            )

    def test_posture_evidence_rejects_negative_observation_count(self) -> None:
        """Negative observation_count is rejected."""
        with pytest.raises(ValueError, match="observation_count must be non-negative"):
            PostureEvidence(
                observation_count=-1,
                success_rate=0.9,
                time_at_current_posture_hours=1.0,
                anomaly_count=0,
                source="test",
            )

    def test_posture_evidence_rejects_negative_anomaly_count(self) -> None:
        """Negative anomaly_count is rejected."""
        with pytest.raises(ValueError, match="anomaly_count must be non-negative"):
            PostureEvidence(
                observation_count=10,
                success_rate=0.9,
                time_at_current_posture_hours=1.0,
                anomaly_count=-5,
                source="test",
            )

    def test_posture_evidence_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict roundtrip preserves all fields."""
        original = PostureEvidence(
            observation_count=50,
            success_rate=0.88,
            time_at_current_posture_hours=24.5,
            anomaly_count=3,
            source="trust_evaluator",
            metadata={"region": "us-east-1", "cluster": "prod"},
        )
        d = original.to_dict()
        restored = PostureEvidence.from_dict(d)

        assert restored.observation_count == original.observation_count
        assert restored.success_rate == original.success_rate
        assert (
            restored.time_at_current_posture_hours
            == original.time_at_current_posture_hours
        )
        assert restored.anomaly_count == original.anomaly_count
        assert restored.source == original.source
        assert restored.metadata == original.metadata
        assert restored.timestamp == original.timestamp

    def test_posture_evidence_to_dict_structure(self) -> None:
        """to_dict returns expected keys and value types."""
        evidence = PostureEvidence(
            observation_count=10,
            success_rate=0.5,
            time_at_current_posture_hours=1.0,
            anomaly_count=0,
            source="test",
        )
        d = evidence.to_dict()
        assert isinstance(d, dict)
        assert d["observation_count"] == 10
        assert d["success_rate"] == 0.5
        assert d["time_at_current_posture_hours"] == 1.0
        assert d["anomaly_count"] == 0
        assert d["source"] == "test"
        assert "timestamp" in d
        assert isinstance(d["timestamp"], str)  # ISO format string


# ---------------------------------------------------------------------------
# PostureEvaluationResult tests
# ---------------------------------------------------------------------------


class TestPostureEvaluationResult:
    """Tests for the PostureEvaluationResult dataclass."""

    def test_evaluation_result_valid_approved(self) -> None:
        """Construct PostureEvaluationResult with 'approved' decision."""
        result = PostureEvaluationResult(
            decision="approved",
            rationale="Agent has demonstrated consistent reliability.",
        )
        assert result.decision == "approved"
        assert result.rationale == "Agent has demonstrated consistent reliability."
        assert result.suggested_posture is None
        assert result.evidence_summary == {}
        assert result.evaluator_id == ""
        assert isinstance(result.timestamp, datetime)

    def test_evaluation_result_valid_denied(self) -> None:
        """Construct PostureEvaluationResult with 'denied' decision."""
        result = PostureEvaluationResult(
            decision="denied",
            rationale="Anomaly rate too high.",
        )
        assert result.decision == "denied"

    def test_evaluation_result_valid_deferred(self) -> None:
        """Construct PostureEvaluationResult with 'deferred' decision."""
        result = PostureEvaluationResult(
            decision="deferred",
            rationale="Insufficient observation data.",
        )
        assert result.decision == "deferred"

    def test_evaluation_result_rejects_invalid_decision(self) -> None:
        """Invalid decision string 'maybe' is rejected."""
        with pytest.raises(ValueError, match="decision must be one of"):
            PostureEvaluationResult(
                decision="maybe",
                rationale="Not a real decision.",
            )

    def test_evaluation_result_rejects_empty_decision(self) -> None:
        """Empty decision string is rejected."""
        with pytest.raises(ValueError, match="decision must be one of"):
            PostureEvaluationResult(
                decision="",
                rationale="Empty decision.",
            )

    def test_evaluation_result_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict roundtrip preserves all fields."""
        original = PostureEvaluationResult(
            decision="approved",
            rationale="All checks passed.",
            evaluator_id="eval-001",
            evidence_summary={"success_rate": 0.99, "observations": 500},
        )
        d = original.to_dict()
        restored = PostureEvaluationResult.from_dict(d)

        assert restored.decision == original.decision
        assert restored.rationale == original.rationale
        assert restored.evaluator_id == original.evaluator_id
        assert restored.evidence_summary == original.evidence_summary
        assert restored.suggested_posture == original.suggested_posture
        assert restored.timestamp == original.timestamp

    def test_evaluation_result_with_suggested_posture(self) -> None:
        """TrustPosture serializes correctly through to_dict/from_dict."""
        original = PostureEvaluationResult(
            decision="approved",
            rationale="Ready for upgrade.",
            suggested_posture=TrustPosture.DELEGATED,
            evaluator_id="eval-002",
        )
        d = original.to_dict()
        # Verify the posture is serialized as its value string
        assert d["suggested_posture"] == "delegated"

        restored = PostureEvaluationResult.from_dict(d)
        assert restored.suggested_posture == TrustPosture.DELEGATED

    def test_evaluation_result_roundtrip_none_posture(self) -> None:
        """Roundtrip with suggested_posture=None works correctly."""
        original = PostureEvaluationResult(
            decision="denied",
            rationale="Not ready.",
        )
        d = original.to_dict()
        assert d["suggested_posture"] is None

        restored = PostureEvaluationResult.from_dict(d)
        assert restored.suggested_posture is None

    def test_evaluation_result_to_dict_structure(self) -> None:
        """to_dict returns expected keys and value types."""
        result = PostureEvaluationResult(
            decision="deferred",
            rationale="Need more data.",
            evaluator_id="eval-003",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == "deferred"
        assert d["rationale"] == "Need more data."
        assert d["evaluator_id"] == "eval-003"
        assert "timestamp" in d
        assert isinstance(d["timestamp"], str)


# ---------------------------------------------------------------------------
# PostureStore protocol tests
# ---------------------------------------------------------------------------


class TestPostureStoreProtocol:
    """Tests for the PostureStore protocol."""

    def test_posture_store_protocol_is_runtime_checkable(self) -> None:
        """Verify PostureStore is runtime_checkable with isinstance."""

        class InMemoryPostureStore:
            """Minimal conforming implementation."""

            def __init__(self) -> None:
                self._postures: Dict[str, TrustPosture] = {}
                self._history: List[TransitionResult] = []

            def get_posture(self, agent_id: str) -> TrustPosture:
                return self._postures.get(agent_id, TrustPosture.SHARED_PLANNING)

            def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
                self._postures[agent_id] = posture

            def get_history(
                self, agent_id: str, limit: int = 100
            ) -> List[TransitionResult]:
                agent_history = [
                    r for r in self._history if r.metadata.get("agent_id") == agent_id
                ]
                return agent_history[-limit:]

            def record_transition(self, result: TransitionResult) -> None:
                self._history.append(result)

        store = InMemoryPostureStore()
        assert isinstance(store, PostureStore)

    def test_non_conforming_class_not_posture_store(self) -> None:
        """A class missing methods is NOT a PostureStore."""

        class NotAStore:
            def get_posture(self, agent_id: str) -> TrustPosture:
                return TrustPosture.SUPERVISED

        obj = NotAStore()
        assert not isinstance(obj, PostureStore)


# ---------------------------------------------------------------------------
# PostureStateMachine backward compatibility tests
# ---------------------------------------------------------------------------


class TestPostureStateMachineBackwardCompat:
    """Tests ensuring PostureStateMachine remains backward-compatible."""

    def test_posture_state_machine_backward_compat_no_store(self) -> None:
        """store=None preserves the existing in-memory behavior."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Default behavior: get_posture returns default
        posture = machine.get_posture("agent-001")
        assert posture == TrustPosture.SHARED_PLANNING

        # set_posture works in-memory
        machine.set_posture("agent-001", TrustPosture.DELEGATED)
        assert machine.get_posture("agent-001") == TrustPosture.DELEGATED

        # Transition works
        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-001",
                from_posture=TrustPosture.DELEGATED,
                to_posture=TrustPosture.SUPERVISED,
                reason="Downgrade for review",
            )
        )
        assert result.success is True
        assert machine.get_posture("agent-001") == TrustPosture.SUPERVISED

    def test_posture_state_machine_with_store(self) -> None:
        """When store is provided, it delegates get/set to the store."""

        class FakeStore:
            """A store that records all calls for verification."""

            def __init__(self) -> None:
                self._postures: Dict[str, TrustPosture] = {}
                self._transitions: List[TransitionResult] = []

            def get_posture(self, agent_id: str) -> TrustPosture:
                if agent_id not in self._postures:
                    raise KeyError(f"Agent {agent_id} not found in store")
                return self._postures[agent_id]

            def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
                self._postures[agent_id] = posture

            def get_history(
                self, agent_id: str, limit: int = 100
            ) -> List[TransitionResult]:
                agent_history = [
                    r
                    for r in self._transitions
                    if r.metadata.get("agent_id") == agent_id
                ]
                return agent_history[-limit:]

            def record_transition(self, result: TransitionResult) -> None:
                self._transitions.append(result)

        store = FakeStore()
        assert isinstance(store, PostureStore)

        machine = PostureStateMachine(
            require_upgrade_approval=False,
            store=store,
        )

        # set_posture via machine writes to the store
        machine.set_posture("agent-X", TrustPosture.CONTINUOUS_INSIGHT)
        assert store._postures["agent-X"] == TrustPosture.CONTINUOUS_INSIGHT

        # get_posture via machine reads from the store
        assert machine.get_posture("agent-X") == TrustPosture.CONTINUOUS_INSIGHT

        # Transition updates the store
        result = machine.transition(
            PostureTransitionRequest(
                agent_id="agent-X",
                from_posture=TrustPosture.CONTINUOUS_INSIGHT,
                to_posture=TrustPosture.DELEGATED,
                reason="Upgrade approved",
            )
        )
        assert result.success is True
        assert store._postures["agent-X"] == TrustPosture.DELEGATED

        # Transition is recorded in the store
        assert len(store._transitions) == 1
        assert store._transitions[0].success is True

    def test_posture_state_machine_store_default_posture_fallback(self) -> None:
        """When store raises KeyError, machine falls back to default_posture."""

        class StrictStore:
            def get_posture(self, agent_id: str) -> TrustPosture:
                raise KeyError(f"No posture for {agent_id}")

            def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
                pass

            def get_history(
                self, agent_id: str, limit: int = 100
            ) -> List[TransitionResult]:
                return []

            def record_transition(self, result: TransitionResult) -> None:
                pass

        machine = PostureStateMachine(
            default_posture=TrustPosture.SUPERVISED,
            store=StrictStore(),
        )
        # Should fall back to default_posture when store raises KeyError
        assert machine.get_posture("unknown-agent") == TrustPosture.SUPERVISED
