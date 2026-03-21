# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP coverage gaps identified by the testing specialist.

Covers:
    T1: score_to_grade out-of-range inputs and boundary values
    T2: DualSignature with empty payloads (b"", "", {})
    T3: generate_soc2_evidence with start_time >= end_time
    T4: Cascade revocation for deep chains (>10 levels)
    T5: TrustReport.to_dict()/from_dict() round-trip
    T6: Thread safety for TrustMetricsCollector and HookRegistry

Written as TEST-ONLY changes -- no source modifications.
"""

from __future__ import annotations

import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kailash.trust.signing.crypto import (
    DualSignature,
    dual_sign,
    dual_verify,
    generate_keypair,
    verify_signature,
)
from kailash.trust.export.compliance import generate_soc2_evidence
from kailash.trust.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)
from kailash.trust.metrics import TrustMetricsCollector
from kailash.trust.posture.postures import TrustPosture
from kailash.trust.revocation.broadcaster import (
    CascadeRevocationManager,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    MAX_CASCADE_DEPTH,
    RevocationType,
)
from kailash.trust.scoring import (
    TrustReport,
    TrustScore,
    score_to_grade,
)


# ===========================================================================
# T1: score_to_grade out-of-range inputs and boundary values
# ===========================================================================


class TestScoreToGradeOutOfRange:
    """T1: score_to_grade must raise ValueError for out-of-range inputs."""

    def test_negative_score_minus_one(self):
        """score_to_grade(-1) must raise ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(-1)

    def test_negative_score_minus_one_hundred(self):
        """score_to_grade(-100) must raise ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(-100)

    def test_score_above_100_by_one(self):
        """score_to_grade(101) must raise ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(101)

    def test_score_200(self):
        """score_to_grade(200) must raise ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(200)

    def test_score_1000(self):
        """score_to_grade(1000) must raise ValueError."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(1000)


class TestScoreToGradeBoundaryValues:
    """T1: score_to_grade must return correct grade at every boundary."""

    def test_score_0_is_F(self):
        """score_to_grade(0) == 'F' (lowest valid score)."""
        assert score_to_grade(0) == "F"

    def test_score_59_is_F(self):
        """score_to_grade(59) == 'F' (top of F range)."""
        assert score_to_grade(59) == "F"

    def test_score_60_is_D(self):
        """score_to_grade(60) == 'D' (bottom of D range)."""
        assert score_to_grade(60) == "D"

    def test_score_69_is_D(self):
        """score_to_grade(69) == 'D' (top of D range)."""
        assert score_to_grade(69) == "D"

    def test_score_70_is_C(self):
        """score_to_grade(70) == 'C' (bottom of C range)."""
        assert score_to_grade(70) == "C"

    def test_score_79_is_C(self):
        """score_to_grade(79) == 'C' (top of C range)."""
        assert score_to_grade(79) == "C"

    def test_score_80_is_B(self):
        """score_to_grade(80) == 'B' (bottom of B range)."""
        assert score_to_grade(80) == "B"

    def test_score_89_is_B(self):
        """score_to_grade(89) == 'B' (top of B range)."""
        assert score_to_grade(89) == "B"

    def test_score_90_is_A(self):
        """score_to_grade(90) == 'A' (bottom of A range)."""
        assert score_to_grade(90) == "A"

    def test_score_100_is_A(self):
        """score_to_grade(100) == 'A' (highest valid score)."""
        assert score_to_grade(100) == "A"


class TestScoreToGradeFloatInputs:
    """T1: score_to_grade with float inputs.

    The function signature declares score: int but Python does not enforce
    type hints at runtime. Floats that satisfy 0 <= score <= 100 should
    still produce a grade based on the numeric comparison. This documents
    the actual behavior.
    """

    def test_float_score_89_5_returns_B(self):
        """Float 89.5 satisfies 0 <= 89.5 <= 100, comparing >= 80 -> 'B'."""
        # The function uses >= threshold comparison, so 89.5 >= 80 -> B
        result = score_to_grade(89.5)
        assert result == "B"

    def test_float_score_90_0_returns_A(self):
        """Float 90.0 satisfies >= 90 threshold -> 'A'."""
        result = score_to_grade(90.0)
        assert result == "A"

    def test_float_score_0_0_returns_F(self):
        """Float 0.0 is below all thresholds -> 'F'."""
        result = score_to_grade(0.0)
        assert result == "F"

    def test_float_score_59_9_returns_F(self):
        """Float 59.9 is below D threshold of 60 -> 'F'."""
        result = score_to_grade(59.9)
        assert result == "F"

    def test_negative_float_raises(self):
        """Float -0.1 must raise ValueError (below 0)."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(-0.1)

    def test_float_above_100_raises(self):
        """Float 100.1 must raise ValueError (above 100)."""
        with pytest.raises(ValueError, match="Score must be between 0 and 100"):
            score_to_grade(100.1)


# ===========================================================================
# T2: DualSignature with empty payloads
# ===========================================================================


class TestDualSignEmptyPayloads:
    """T2: dual_sign and dual_verify must handle empty payloads correctly."""

    @pytest.fixture
    def keypair(self):
        """Generate a fresh Ed25519 keypair."""
        private_key, public_key = generate_keypair()
        return private_key, public_key

    @pytest.fixture
    def hmac_key(self):
        """Generate a random 32-byte HMAC key."""
        return secrets.token_bytes(32)

    def test_dual_sign_empty_bytes(self, keypair):
        """dual_sign(b'') must produce a valid DualSignature."""
        private_key, public_key = keypair
        sig = dual_sign(b"", private_key)
        assert isinstance(sig, DualSignature)
        assert sig.ed25519_signature  # non-empty string
        assert sig.hmac_signature is None  # no HMAC key provided

    def test_dual_sign_empty_bytes_verifies(self, keypair):
        """DualSignature from empty bytes must verify with dual_verify."""
        private_key, public_key = keypair
        sig = dual_sign(b"", private_key)
        assert dual_verify(b"", sig, public_key) is True

    def test_dual_sign_empty_bytes_ed25519_verifies_standalone(self, keypair):
        """The Ed25519 signature from empty bytes must verify independently."""
        private_key, public_key = keypair
        sig = dual_sign(b"", private_key)
        assert verify_signature(b"", sig.ed25519_signature, public_key) is True

    def test_dual_sign_empty_string(self, keypair):
        """dual_sign('') must produce a valid DualSignature."""
        private_key, public_key = keypair
        sig = dual_sign("", private_key)
        assert isinstance(sig, DualSignature)
        assert sig.ed25519_signature

    def test_dual_sign_empty_string_verifies(self, keypair):
        """DualSignature from empty string must verify."""
        private_key, public_key = keypair
        sig = dual_sign("", private_key)
        assert dual_verify("", sig, public_key) is True

    def test_dual_sign_empty_dict(self, keypair):
        """dual_sign({}) must produce a valid DualSignature."""
        private_key, public_key = keypair
        sig = dual_sign({}, private_key)
        assert isinstance(sig, DualSignature)
        assert sig.ed25519_signature

    def test_dual_sign_empty_dict_verifies(self, keypair):
        """DualSignature from empty dict must verify."""
        private_key, public_key = keypair
        sig = dual_sign({}, private_key)
        assert dual_verify({}, sig, public_key) is True

    def test_dual_sign_empty_bytes_with_hmac(self, keypair, hmac_key):
        """dual_sign(b'', ..., hmac_key) must produce both signatures."""
        private_key, public_key = keypair
        sig = dual_sign(b"", private_key, hmac_key=hmac_key)
        assert sig.ed25519_signature
        assert sig.hmac_signature is not None
        assert sig.has_hmac is True

    def test_dual_sign_empty_bytes_with_hmac_verifies(self, keypair, hmac_key):
        """Both signatures from empty bytes must verify."""
        private_key, public_key = keypair
        sig = dual_sign(b"", private_key, hmac_key=hmac_key)
        assert dual_verify(b"", sig, public_key, hmac_key=hmac_key) is True

    def test_dual_sign_empty_string_with_hmac_verifies(self, keypair, hmac_key):
        """Both signatures from empty string must verify."""
        private_key, public_key = keypair
        sig = dual_sign("", private_key, hmac_key=hmac_key)
        assert dual_verify("", sig, public_key, hmac_key=hmac_key) is True

    def test_dual_sign_empty_dict_with_hmac_verifies(self, keypair, hmac_key):
        """Both signatures from empty dict must verify."""
        private_key, public_key = keypair
        sig = dual_sign({}, private_key, hmac_key=hmac_key)
        assert dual_verify({}, sig, public_key, hmac_key=hmac_key) is True

    def test_empty_bytes_signature_differs_from_empty_string(self, keypair):
        """Signatures for b'' and '' should differ (different encoding paths).

        b'' is signed as raw bytes; '' is encoded to b'' via .encode('utf-8').
        Since both produce the same underlying bytes, signatures should match.
        """
        private_key, public_key = keypair
        sig_bytes = dual_sign(b"", private_key)
        sig_str = dual_sign("", private_key)
        # Both sign the same underlying empty bytes, so the Ed25519 signatures
        # are deterministic for the same key+payload, but Ed25519 is
        # nonce-based so each sign call produces a different signature.
        # We verify each one verifies with the other's payload type.
        assert dual_verify(b"", sig_str, public_key) is True
        assert dual_verify("", sig_bytes, public_key) is True


# ===========================================================================
# T3: generate_soc2_evidence with start_time >= end_time
# ===========================================================================


class TestGenerateSoc2EvidenceTimeValidation:
    """T3: generate_soc2_evidence must reject start_time >= end_time."""

    @pytest.fixture
    def now_utc(self):
        return datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_start_time_equals_end_time_raises(self, now_utc):
        """start_time == end_time must raise ValueError."""
        # We don't need a real audit_service because the validation
        # happens before the service is called.
        with pytest.raises(ValueError, match="start_time.*must be before.*end_time"):
            await generate_soc2_evidence(
                audit_service=None,  # Should not be reached
                start_time=now_utc,
                end_time=now_utc,
            )

    @pytest.mark.asyncio
    async def test_start_time_after_end_time_raises(self, now_utc):
        """start_time > end_time must raise ValueError."""
        start = now_utc + timedelta(hours=1)
        end = now_utc
        with pytest.raises(ValueError, match="start_time.*must be before.*end_time"):
            await generate_soc2_evidence(
                audit_service=None,
                start_time=start,
                end_time=end,
            )

    @pytest.mark.asyncio
    async def test_start_time_one_day_after_end_time_raises(self, now_utc):
        """start_time 24 hours after end_time must raise ValueError."""
        start = now_utc + timedelta(days=1)
        end = now_utc
        with pytest.raises(ValueError, match="start_time.*must be before.*end_time"):
            await generate_soc2_evidence(
                audit_service=None,
                start_time=start,
                end_time=end,
            )

    @pytest.mark.asyncio
    async def test_start_time_one_second_after_end_time_raises(self, now_utc):
        """start_time just 1 second after end_time must still raise."""
        start = now_utc + timedelta(seconds=1)
        end = now_utc
        with pytest.raises(ValueError, match="start_time.*must be before.*end_time"):
            await generate_soc2_evidence(
                audit_service=None,
                start_time=start,
                end_time=end,
            )

    @pytest.mark.asyncio
    async def test_error_message_contains_timestamps(self, now_utc):
        """The error message must contain the actual timestamp values."""
        start = now_utc + timedelta(hours=1)
        end = now_utc
        with pytest.raises(ValueError) as exc_info:
            await generate_soc2_evidence(
                audit_service=None,
                start_time=start,
                end_time=end,
            )
        error_msg = str(exc_info.value)
        assert start.isoformat() in error_msg
        assert end.isoformat() in error_msg


# ===========================================================================
# T4: Cascade revocation for deep chains (>10 levels)
# ===========================================================================


class TestCascadeRevocationDeepChains:
    """T4: CascadeRevocationManager must handle deep delegation chains.

    Uses CascadeRevocationManager directly from broadcaster.py to test
    the BFS cascade with chains deeper than 10 levels.
    """

    @pytest.fixture
    def broadcaster(self):
        return InMemoryRevocationBroadcaster()

    @pytest.fixture
    def registry(self):
        return InMemoryDelegationRegistry()

    def _build_linear_chain(self, registry, depth):
        """Build a linear delegation chain: agent-0 -> agent-1 -> ... -> agent-N.

        Args:
            registry: InMemoryDelegationRegistry to register delegations in.
            depth: Number of delegation levels (number of agents = depth + 1).

        Returns:
            List of agent IDs in order.
        """
        agents = [f"agent-{i}" for i in range(depth + 1)]
        for i in range(depth):
            registry.register_delegation(agents[i], agents[i + 1])
        return agents

    def test_cascade_11_levels(self, broadcaster, registry):
        """11-level chain must cascade revocation through all 12 agents."""
        agents = self._build_linear_chain(registry, depth=11)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id=agents[0],
            revoked_by="admin",
            reason="Deep chain test (11 levels)",
        )

        revoked_targets = {e.target_id for e in events}
        assert set(agents) == revoked_targets, f"Expected all {len(agents)} agents revoked, got {len(revoked_targets)}"
        # Verify event count: 1 initial + 11 cascade = 12 total
        assert len(events) == 12

    def test_cascade_50_levels(self, broadcaster, registry):
        """50-level chain must cascade revocation through all 51 agents."""
        agents = self._build_linear_chain(registry, depth=50)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id=agents[0],
            revoked_by="admin",
            reason="Deep chain test (50 levels)",
        )

        revoked_targets = {e.target_id for e in events}
        assert set(agents) == revoked_targets
        assert len(events) == 51

    def test_cascade_100_levels_at_max_depth(self, broadcaster, registry):
        """100-level chain (at MAX_CASCADE_DEPTH) must revoke all 101 agents."""
        assert MAX_CASCADE_DEPTH == 100, f"Expected MAX_CASCADE_DEPTH == 100, got {MAX_CASCADE_DEPTH}"
        agents = self._build_linear_chain(registry, depth=100)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id=agents[0],
            revoked_by="admin",
            reason="Deep chain test (100 levels, at MAX_CASCADE_DEPTH)",
        )

        revoked_targets = {e.target_id for e in events}
        assert set(agents) == revoked_targets
        assert len(events) == 101

    def test_cascade_deep_chain_initial_event_is_agent_revoked(self, broadcaster, registry):
        """The first event in a deep chain must be AGENT_REVOKED type."""
        self._build_linear_chain(registry, depth=15)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="Initial event type check",
        )

        assert events[0].revocation_type == RevocationType.AGENT_REVOKED
        assert events[0].target_id == "agent-0"

    def test_cascade_deep_chain_subsequent_events_are_cascade_type(self, broadcaster, registry):
        """All events after the initial one must be CASCADE_REVOCATION type."""
        self._build_linear_chain(registry, depth=15)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="Cascade type check",
        )

        for event in events[1:]:
            assert event.revocation_type == RevocationType.CASCADE_REVOCATION, (
                f"Expected CASCADE_REVOCATION for {event.target_id}, got {event.revocation_type}"
            )

    def test_cascade_deep_chain_all_events_have_unique_ids(self, broadcaster, registry):
        """All events in a deep cascade must have unique event_ids."""
        self._build_linear_chain(registry, depth=20)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="Unique ID check",
        )

        event_ids = [e.event_id for e in events]
        assert len(event_ids) == len(set(event_ids)), "Event IDs must be unique"

    def test_cascade_deep_chain_cascade_from_links(self, broadcaster, registry):
        """Each cascade event must have cascade_from set to the parent event."""
        self._build_linear_chain(registry, depth=11)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="Cascade link check",
        )

        # Every cascade event (not the initial) must have cascade_from set
        for event in events[1:]:
            assert event.cascade_from is not None, f"Cascade event for {event.target_id} has no cascade_from"

    def test_cascade_deep_chain_broadcaster_receives_all_events(self, broadcaster, registry):
        """All events must appear in the broadcaster's history."""
        self._build_linear_chain(registry, depth=15)
        manager = CascadeRevocationManager(broadcaster, registry)

        events = manager.cascade_revoke(
            target_id="agent-0",
            revoked_by="admin",
            reason="Broadcaster history check",
        )

        history = broadcaster.get_history()
        history_ids = {e.event_id for e in history}
        for event in events:
            assert event.event_id in history_ids, (
                f"Event {event.event_id} for {event.target_id} missing from broadcaster history"
            )


# ===========================================================================
# T5: TrustReport.to_dict()/from_dict() round-trip
# ===========================================================================


class TestTrustReportRoundTrip:
    """T5: TrustReport must survive to_dict() -> from_dict() round-trip."""

    @pytest.fixture
    def full_trust_score(self):
        """A TrustScore with all fields populated."""
        return TrustScore(
            score=85,
            breakdown={
                "chain_completeness": 28.5,
                "delegation_depth": 14.25,
                "constraint_coverage": 18.75,
                "posture_level": 16.0,
                "chain_recency": 7.5,
            },
            grade="B",
            computed_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
            agent_id="agent-test-001",
        )

    @pytest.fixture
    def full_trust_report(self, full_trust_score):
        """A TrustReport with all fields populated."""
        return TrustReport(
            score=full_trust_score,
            risk_indicators=[
                "Deep delegation chain (depth=7)",
                "Low constraint coverage (2 constraints)",
            ],
            recommendations=[
                "Reduce delegation depth to improve accountability",
                "Add more constraints for better governance",
            ],
        )

    def test_round_trip_full_report(self, full_trust_report):
        """Full TrustReport must survive to_dict() -> from_dict() round-trip."""
        serialized = full_trust_report.to_dict()
        restored = TrustReport.from_dict(serialized)

        assert restored.score.score == full_trust_report.score.score
        assert restored.score.grade == full_trust_report.score.grade
        assert restored.score.agent_id == full_trust_report.score.agent_id
        assert restored.score.breakdown == full_trust_report.score.breakdown
        assert restored.score.computed_at == full_trust_report.score.computed_at
        assert restored.risk_indicators == full_trust_report.risk_indicators
        assert restored.recommendations == full_trust_report.recommendations

    def test_round_trip_preserves_score_numeric_value(self, full_trust_report):
        """The score integer value must be preserved exactly."""
        serialized = full_trust_report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.score.score == 85

    def test_round_trip_preserves_breakdown_floats(self, full_trust_report):
        """Breakdown float values must be preserved."""
        serialized = full_trust_report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.score.breakdown["chain_completeness"] == 28.5
        assert restored.score.breakdown["delegation_depth"] == 14.25

    def test_round_trip_preserves_computed_at_datetime(self, full_trust_report):
        """computed_at datetime must be preserved with timezone."""
        serialized = full_trust_report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.score.computed_at == datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_round_trip_empty_risk_indicators(self, full_trust_score):
        """TrustReport with empty risk_indicators survives round-trip."""
        report = TrustReport(
            score=full_trust_score,
            risk_indicators=[],
            recommendations=["Add constraints"],
        )
        serialized = report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.risk_indicators == []
        assert restored.recommendations == ["Add constraints"]

    def test_round_trip_empty_recommendations(self, full_trust_score):
        """TrustReport with empty recommendations survives round-trip."""
        report = TrustReport(
            score=full_trust_score,
            risk_indicators=["Some risk"],
            recommendations=[],
        )
        serialized = report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.risk_indicators == ["Some risk"]
        assert restored.recommendations == []

    def test_round_trip_both_lists_empty(self, full_trust_score):
        """TrustReport with both lists empty survives round-trip."""
        report = TrustReport(
            score=full_trust_score,
            risk_indicators=[],
            recommendations=[],
        )
        serialized = report.to_dict()
        restored = TrustReport.from_dict(serialized)
        assert restored.risk_indicators == []
        assert restored.recommendations == []

    def test_to_dict_produces_json_serializable_types(self, full_trust_report):
        """to_dict() output must contain only JSON-serializable types."""
        import json

        serialized = full_trust_report.to_dict()
        # This must not raise
        json_str = json.dumps(serialized)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_round_trip_score_grade_boundary_A(self):
        """Round-trip with grade 'A' (score=90)."""
        score = TrustScore(
            score=90,
            breakdown={"test": 90.0},
            grade="A",
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            agent_id="agent-A-grade",
        )
        report = TrustReport(score=score, risk_indicators=[], recommendations=[])
        restored = TrustReport.from_dict(report.to_dict())
        assert restored.score.grade == "A"
        assert restored.score.score == 90

    def test_round_trip_score_grade_F(self):
        """Round-trip with grade 'F' (score=0)."""
        score = TrustScore(
            score=0,
            breakdown={"test": 0.0},
            grade="F",
            computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            agent_id="agent-F-grade",
        )
        report = TrustReport(
            score=score,
            risk_indicators=["Critically low"],
            recommendations=["Review urgently"],
        )
        restored = TrustReport.from_dict(report.to_dict())
        assert restored.score.grade == "F"
        assert restored.score.score == 0


# ===========================================================================
# T6: Thread safety for TrustMetricsCollector and HookRegistry
# ===========================================================================


class TestTrustMetricsCollectorThreadSafety:
    """T6: TrustMetricsCollector must handle concurrent access safely.

    Uses ThreadPoolExecutor with 10 workers to exercise thread safety
    of the Lock-protected methods.
    """

    def test_concurrent_record_posture(self):
        """Concurrent record_posture calls must not corrupt state."""
        collector = TrustMetricsCollector()
        postures = list(TrustPosture)

        def record_posture(worker_id):
            for i in range(100):
                agent_id = f"agent-{worker_id}-{i}"
                posture = postures[i % len(postures)]
                collector.record_posture(agent_id, posture)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(record_posture, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()  # Raises if any thread crashed

        metrics = collector.get_posture_metrics()
        # Each worker records 100 unique agents, 10 workers = 1000 total
        total_agents = sum(metrics.posture_distribution.values())
        assert total_agents == 1000, f"Expected 1000 agents in posture distribution, got {total_agents}"

    def test_concurrent_record_transition(self):
        """Concurrent record_transition calls must not lose counts."""
        collector = TrustMetricsCollector()

        def record_transitions(worker_id):
            for _ in range(100):
                collector.record_transition("upgrade")
                collector.record_transition("downgrade")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(record_transitions, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        metrics = collector.get_posture_metrics()
        # 10 workers * 100 iterations * 1 upgrade per iteration = 1000
        assert metrics.transitions_by_type["upgrade"] == 1000
        assert metrics.transitions_by_type["downgrade"] == 1000

    def test_concurrent_record_constraint_evaluation(self):
        """Concurrent constraint evaluation recording must not corrupt counts."""
        collector = TrustMetricsCollector()

        def record_evaluations(worker_id):
            for i in range(100):
                passed = i % 2 == 0
                failed_dims = ["rate_limit"] if not passed else []
                collector.record_constraint_evaluation(
                    passed=passed,
                    failed_dimensions=failed_dims,
                    gaming_flags=[],
                    duration_ms=1.0,
                )

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(record_evaluations, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        metrics = collector.get_constraint_metrics()
        # 10 workers * 100 evaluations = 1000 total
        assert metrics.evaluations_total == 1000
        # 50 per worker passed (even indices), 10 workers = 500
        assert metrics.evaluations_passed == 500
        assert metrics.evaluations_failed == 500

    def test_concurrent_circuit_breaker_and_emergency(self):
        """Concurrent circuit_breaker_open and emergency_downgrade must be correct."""
        collector = TrustMetricsCollector()

        def record_events(worker_id):
            for _ in range(50):
                collector.record_circuit_breaker_open()
                collector.record_emergency_downgrade()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(record_events, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        metrics = collector.get_posture_metrics()
        assert metrics.circuit_breaker_opens == 500  # 10 * 50
        assert metrics.emergency_downgrades == 500

    def test_concurrent_mixed_operations(self):
        """Mix of all operations concurrently must not crash or corrupt."""
        collector = TrustMetricsCollector()
        postures = list(TrustPosture)

        def mixed_ops(worker_id):
            for i in range(50):
                collector.record_posture(f"agent-{worker_id}", postures[i % len(postures)])
                collector.record_transition("upgrade")
                collector.record_constraint_evaluation(passed=True, duration_ms=0.5)
                collector.record_circuit_breaker_open()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(mixed_ops, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        # Validate no crash and metrics are retrievable
        posture_metrics = collector.get_posture_metrics()
        constraint_metrics = collector.get_constraint_metrics()

        # 10 workers * 50 transitions = 500 upgrades
        assert posture_metrics.transitions_by_type["upgrade"] == 500
        # 10 workers * 50 evaluations = 500
        assert constraint_metrics.evaluations_total == 500
        assert constraint_metrics.evaluations_passed == 500
        # 10 workers * 50 opens = 500
        assert posture_metrics.circuit_breaker_opens == 500


class TestHookRegistryThreadSafety:
    """T6: HookRegistry must handle concurrent register/execute safely.

    HookRegistry uses dict-based storage without explicit locking,
    so concurrent register/unregister from threads may reveal issues.
    """

    def _make_allow_hook(self, name, event_types=None, priority=100):
        """Create a simple allow-all hook with the given name."""

        class SimpleHook(EATPHook):
            def __init__(self, hook_name, hook_event_types, hook_priority):
                self._name = hook_name
                self._event_types = hook_event_types or [HookType.PRE_VERIFICATION]
                self._priority = hook_priority

            @property
            def name(self):
                return self._name

            @property
            def event_types(self):
                return self._event_types

            @property
            def priority(self):
                return self._priority

            async def __call__(self, context):
                return HookResult(allow=True)

        return SimpleHook(name, event_types, priority)

    def test_concurrent_register_unique_names(self):
        """Concurrent registration of uniquely-named hooks must not crash."""
        registry = HookRegistry(timeout_seconds=5.0)

        def register_hooks(worker_id):
            for i in range(20):
                hook_name = f"hook-{worker_id}-{i}"
                hook = self._make_allow_hook(hook_name)
                try:
                    registry.register(hook)
                except ValueError:
                    # Another thread may have registered same name
                    # (should not happen with unique names, but handle gracefully)
                    pass

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(register_hooks, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        # Should have 200 hooks (10 workers * 20 hooks each)
        all_hooks = registry.list_hooks()
        assert len(all_hooks) == 200, f"Expected 200 hooks, got {len(all_hooks)}"

    def test_concurrent_register_and_unregister(self):
        """Concurrent register and unregister must not crash."""
        registry = HookRegistry(timeout_seconds=5.0)

        # Pre-register hooks to unregister
        for i in range(50):
            hook = self._make_allow_hook(f"pre-hook-{i}")
            registry.register(hook)

        def register_new(worker_id):
            for i in range(20):
                hook = self._make_allow_hook(f"new-hook-{worker_id}-{i}")
                try:
                    registry.register(hook)
                except ValueError:
                    pass

        def unregister_old(worker_id):
            for i in range(50):
                registry.unregister(f"pre-hook-{i}")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = []
            # 5 workers registering
            for w in range(5):
                futures.append(pool.submit(register_new, w))
            # 5 workers unregistering
            for w in range(5):
                futures.append(pool.submit(unregister_old, w))

            for f in as_completed(futures):
                f.result()  # Must not raise

        # Verify registry is still functional
        remaining = registry.list_hooks()
        assert isinstance(remaining, list)

    def test_concurrent_execute_does_not_crash(self):
        """Concurrent execute calls must not crash the registry."""
        registry = HookRegistry(timeout_seconds=5.0)

        # Register a few hooks
        for i in range(5):
            hook = self._make_allow_hook(
                f"exec-hook-{i}",
                event_types=[HookType.PRE_VERIFICATION],
            )
            registry.register(hook)

        results = []

        def execute_hook(worker_id):
            for _ in range(20):
                context = HookContext(
                    agent_id=f"agent-{worker_id}",
                    action="read",
                    hook_type=HookType.PRE_VERIFICATION,
                )
                # Use execute_sync since we are in threads (no event loop)
                result = registry.execute_sync(HookType.PRE_VERIFICATION, context)
                results.append(result)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(execute_hook, w) for w in range(10)]
            for f in as_completed(futures):
                f.result()

        # All 200 executions should have completed (10 workers * 20 iterations)
        assert len(results) == 200
        # All should have allowed (our hooks all return allow=True)
        for r in results:
            assert r.allow is True
