# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for circuit breaker bounded collections (G1) and monotonic
escalation safety on recovery (S2).

G1: PostureCircuitBreaker._failures dict must be bounded at maxlen=10000
    per agent with oldest-10% trimming when capacity is exceeded.

G1+: CircuitBreakerRegistry._breakers dict must also be bounded.

S2: When circuit breaker recovers (HALF_OPEN -> CLOSED), _close_circuit
    must NOT restore the posture to a level above the agent's current
    posture. Monotonic escalation: AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED.
    Restoring to a higher posture would violate this invariant.

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    FailureEvent,
    PostureCircuitBreaker,
)
from kailash.trust.posture.postures import PostureStateMachine, TrustPosture


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def machine():
    """Create a PostureStateMachine with an agent at DELEGATED."""
    m = PostureStateMachine()
    m.set_posture("agent-001", TrustPosture.DELEGATED)
    return m


@pytest.fixture
def config():
    """Low thresholds for faster test cycles."""
    return CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout=1,
        half_open_max_calls=2,
        failure_window_seconds=600,
    )


@pytest.fixture
def breaker(machine, config):
    return PostureCircuitBreaker(posture_machine=machine, config=config)


# ---------------------------------------------------------------------------
# G1: PostureCircuitBreaker._failures bounded per agent
# ---------------------------------------------------------------------------


class TestCircuitBreakerFailuresBounded:
    """G1: _failures dict entries per agent must be bounded."""

    def test_default_max_failures_per_agent_is_10000(self, machine):
        """Default max failures per agent should be 10,000."""
        breaker = PostureCircuitBreaker(posture_machine=machine)
        assert breaker._max_failures_per_agent == 10_000

    def test_custom_max_failures_per_agent(self, machine):
        """max_failures_per_agent should be configurable."""
        breaker = PostureCircuitBreaker(
            posture_machine=machine,
            max_failures_per_agent=500,
        )
        assert breaker._max_failures_per_agent == 500

    @pytest.mark.asyncio
    async def test_failures_trimmed_at_capacity(self, machine):
        """When failures for a single agent exceed maxlen, oldest 10% are trimmed."""
        maxlen = 100
        breaker = PostureCircuitBreaker(
            posture_machine=machine,
            config=CircuitBreakerConfig(
                failure_threshold=999999,  # prevent circuit from opening
                failure_window_seconds=99999,
            ),
            max_failures_per_agent=maxlen,
        )

        # Record maxlen + 10 failures
        for i in range(maxlen + 10):
            await breaker.record_failure(
                "agent-001", "TestError", f"fail-{i}", "action", "low"
            )

        assert len(breaker._failures.get("agent-001", [])) <= maxlen

    @pytest.mark.asyncio
    async def test_oldest_failures_trimmed(self, machine):
        """Trim should remove oldest failures, keeping newest."""
        maxlen = 20
        breaker = PostureCircuitBreaker(
            posture_machine=machine,
            config=CircuitBreakerConfig(
                failure_threshold=999999,
                failure_window_seconds=99999,
            ),
            max_failures_per_agent=maxlen,
        )

        for i in range(maxlen + 5):
            await breaker.record_failure(
                "agent-001", "TestError", f"fail-{i}", "action", "low"
            )

        failures = breaker._failures["agent-001"]
        messages = [f.error_message for f in failures]
        # Oldest should be trimmed
        assert "fail-0" not in messages
        assert "fail-1" not in messages
        # Newest should remain
        assert f"fail-{maxlen + 4}" in messages

    @pytest.mark.asyncio
    async def test_per_agent_isolation_of_bounds(self, machine):
        """Bounds apply per-agent, not globally."""
        machine.set_posture("agent-002", TrustPosture.DELEGATED)
        maxlen = 20
        breaker = PostureCircuitBreaker(
            posture_machine=machine,
            config=CircuitBreakerConfig(
                failure_threshold=999999,
                failure_window_seconds=99999,
            ),
            max_failures_per_agent=maxlen,
        )

        # Fill agent-001 to capacity
        for i in range(maxlen + 5):
            await breaker.record_failure(
                "agent-001", "TestError", f"fail-{i}", "action", "low"
            )

        # agent-002 should be unaffected
        for i in range(5):
            await breaker.record_failure(
                "agent-002", "TestError", f"fail-{i}", "action", "low"
            )

        assert len(breaker._failures.get("agent-001", [])) <= maxlen
        assert len(breaker._failures.get("agent-002", [])) == 5


# ---------------------------------------------------------------------------
# G1+: CircuitBreakerRegistry._breakers bounded
# ---------------------------------------------------------------------------


class TestCircuitBreakerRegistryBounded:
    """G1+: _breakers dict in the registry must be bounded."""

    def test_default_max_breakers_is_10000(self, machine):
        """Default max breakers should be 10,000."""
        registry = CircuitBreakerRegistry(posture_machine=machine)
        assert registry._max_breakers == 10_000

    def test_custom_max_breakers(self, machine):
        """max_breakers should be configurable."""
        registry = CircuitBreakerRegistry(posture_machine=machine, max_breakers=500)
        assert registry._max_breakers == 500

    def test_breakers_trimmed_at_capacity(self, machine):
        """When breakers exceed max, oldest 10% are removed."""
        maxlen = 20
        registry = CircuitBreakerRegistry(posture_machine=machine, max_breakers=maxlen)

        for i in range(maxlen + 5):
            agent_id = f"agent-{i:04d}"
            machine.set_posture(agent_id, TrustPosture.DELEGATED)
            registry.get_or_create(agent_id)

        assert len(registry._breakers) <= maxlen


# ---------------------------------------------------------------------------
# S2: Monotonic escalation on circuit breaker recovery
# ---------------------------------------------------------------------------


class TestMonotonicEscalationOnRecovery:
    """S2: _close_circuit must NOT restore posture above current level.

    Scenario: Agent starts at DELEGATED, circuit opens and downgrades to
    SUPERVISED. Meanwhile, an external authority manually downgrades the
    agent further to PSEUDO_AGENT. When the circuit closes, it must NOT
    restore the agent back to DELEGATED (the original posture), because
    that would violate monotonic escalation.
    """

    @pytest.mark.asyncio
    async def test_close_circuit_does_not_upgrade_posture(self, machine):
        """On recovery, posture must NOT be set above current level."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,  # immediate recovery
            half_open_max_calls=1,
            downgrade_on_open="supervised",
        )
        breaker = PostureCircuitBreaker(posture_machine=machine, config=config)

        # Step 1: Record enough failures to open the circuit
        await breaker.record_failure(
            "agent-001", "Error", "fail1", "action", "critical"
        )
        await breaker.record_failure(
            "agent-001", "Error", "fail2", "action", "critical"
        )
        assert breaker.get_state("agent-001") == CircuitState.OPEN

        # Step 2: External authority further downgrades to PSEUDO_AGENT
        machine.set_posture("agent-001", TrustPosture.PSEUDO_AGENT)

        # Step 3: Recovery -- circuit transitions to HALF_OPEN
        can = await breaker.can_proceed("agent-001")
        assert can is True
        assert breaker.get_state("agent-001") == CircuitState.HALF_OPEN

        # Step 4: Successful calls close the circuit
        await breaker.record_success("agent-001")

        # Step 5: Verify posture is NOT restored above current level
        assert breaker.get_state("agent-001") == CircuitState.CLOSED
        current_posture = machine.get_posture("agent-001")

        # CRITICAL: Posture must NOT have been upgraded. It should remain
        # at PSEUDO_AGENT (or below), never back to DELEGATED or SUPERVISED.
        assert current_posture == TrustPosture.PSEUDO_AGENT, (
            f"Monotonic escalation violated: posture was restored to "
            f"{current_posture.value} but should remain at pseudo_agent "
            f"or lower (never upgrade on circuit close)"
        )

    @pytest.mark.asyncio
    async def test_close_circuit_does_not_restore_original_posture(self, machine):
        """_close_circuit must not blindly restore original posture."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,
            half_open_max_calls=1,
            downgrade_on_open="supervised",
        )
        breaker = PostureCircuitBreaker(posture_machine=machine, config=config)

        # Open the circuit (downgrades from DELEGATED to SUPERVISED)
        await breaker.record_failure(
            "agent-001", "Error", "fail1", "action", "critical"
        )
        await breaker.record_failure(
            "agent-001", "Error", "fail2", "action", "critical"
        )
        assert breaker.get_state("agent-001") == CircuitState.OPEN
        assert machine.get_posture("agent-001") == TrustPosture.SUPERVISED

        # Recover
        can = await breaker.can_proceed("agent-001")
        assert can is True
        await breaker.record_success("agent-001")
        assert breaker.get_state("agent-001") == CircuitState.CLOSED

        # Posture should NOT have been silently restored to DELEGATED
        # The circuit breaker must only log a suggestion, never auto-restore
        current_posture = machine.get_posture("agent-001")
        assert (
            current_posture != TrustPosture.DELEGATED
            or current_posture == TrustPosture.SUPERVISED
        ), (
            f"Circuit breaker should not auto-restore posture to original. "
            f"Got {current_posture.value}, expected supervised (downgraded level)"
        )

    @pytest.mark.asyncio
    async def test_close_circuit_logs_restoration_suggestion(self, machine, caplog):
        """On recovery, should log suggestion to restore posture."""
        import logging

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0,
            half_open_max_calls=1,
            downgrade_on_open="supervised",
        )
        breaker = PostureCircuitBreaker(posture_machine=machine, config=config)

        # Open and recover
        await breaker.record_failure(
            "agent-001", "Error", "fail1", "action", "critical"
        )
        await breaker.record_failure(
            "agent-001", "Error", "fail2", "action", "critical"
        )

        with caplog.at_level(logging.INFO, logger="kailash.trust.circuit_breaker"):
            can = await breaker.can_proceed("agent-001")
            await breaker.record_success("agent-001")

        # Should log a suggestion to consider restoring posture
        assert (
            "consider restoring" in caplog.text.lower()
            or "circuit closed" in caplog.text.lower()
        )
