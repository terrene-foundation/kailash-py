# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for CircuitBreakerRegistry (G4).

Verifies lazy creation, per-agent isolation, bulk status queries,
default config propagation, and cleanup operations.
"""

from __future__ import annotations

import pytest

from eatp.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    PostureCircuitBreaker,
)
from eatp.postures import PostureStateMachine, TrustPosture


@pytest.fixture
def machine():
    """Create a PostureStateMachine with two agents at DELEGATED."""
    m = PostureStateMachine()
    m.set_posture("agent-001", TrustPosture.DELEGATED)
    m.set_posture("agent-002", TrustPosture.DELEGATED)
    return m


@pytest.fixture
def registry(machine):
    """Create a CircuitBreakerRegistry with default config."""
    return CircuitBreakerRegistry(posture_machine=machine)


class TestCircuitBreakerRegistryCreation:
    """G4: Lazy creation and initialization."""

    def test_get_or_create_creates_breaker(self, registry):
        """First access for an agent must create a breaker."""
        breaker = registry.get_or_create("agent-001")
        assert isinstance(breaker, PostureCircuitBreaker)

    def test_get_or_create_returns_same_instance(self, registry):
        """Subsequent access must return the same breaker instance."""
        breaker1 = registry.get_or_create("agent-001")
        breaker2 = registry.get_or_create("agent-001")
        assert breaker1 is breaker2

    def test_different_agents_get_different_breakers(self, registry):
        """Different agents must get distinct breaker instances."""
        b1 = registry.get_or_create("agent-001")
        b2 = registry.get_or_create("agent-002")
        assert b1 is not b2

    def test_default_config_propagated(self, machine):
        """Custom default config must be used for new breakers."""
        custom_config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30)
        reg = CircuitBreakerRegistry(
            posture_machine=machine, default_config=custom_config
        )
        breaker = reg.get_or_create("agent-001")
        # Verify by checking metrics (which expose config values)
        metrics = breaker.get_metrics("agent-001")
        assert metrics["failure_threshold"] == 3
        assert metrics["recovery_timeout_seconds"] == 30

    def test_per_agent_config_override(self, machine):
        """Per-agent config must override default config."""
        default = CircuitBreakerConfig(failure_threshold=5)
        custom = CircuitBreakerConfig(failure_threshold=2)
        reg = CircuitBreakerRegistry(posture_machine=machine, default_config=default)
        breaker = reg.get_or_create("agent-001", config=custom)
        metrics = breaker.get_metrics("agent-001")
        assert metrics["failure_threshold"] == 2

    def test_config_ignored_for_existing_breaker(self, registry, caplog):
        """Config override must be ignored with warning for existing breakers."""
        import logging

        registry.get_or_create("agent-001")
        custom = CircuitBreakerConfig(failure_threshold=2)
        with caplog.at_level(logging.WARNING, logger="eatp.circuit_breaker"):
            registry.get_or_create("agent-001", config=custom)
        assert "already exists" in caplog.text
        assert "ignoring provided config" in caplog.text.lower()


class TestCircuitBreakerRegistryIsolation:
    """G4: Per-agent isolation guarantees."""

    async def test_failures_isolated_between_agents(self, registry):
        """One agent's failures must not affect another agent's breaker."""
        b1 = registry.get_or_create("agent-001")
        b2 = registry.get_or_create("agent-002")

        # Record failures for agent-001 only
        for _ in range(10):
            await b1.record_failure("agent-001", "Error", "fail", "action", "critical")

        # agent-001 should be open
        assert b1.get_state("agent-001") == CircuitState.OPEN
        # agent-002 should be unaffected
        assert b2.get_state("agent-002") == CircuitState.CLOSED


class TestCircuitBreakerRegistryBulkStatus:
    """G4: Bulk status queries."""

    async def test_get_all_open_empty_initially(self, registry):
        """No agents in OPEN state initially."""
        registry.get_or_create("agent-001")
        assert registry.get_all_open() == {}

    async def test_get_all_open_after_failures(self, registry):
        """Agents in OPEN state after threshold exceeded."""
        breaker = registry.get_or_create("agent-001")
        for _ in range(10):
            await breaker.record_failure(
                "agent-001", "Error", "fail", "action", "critical"
            )
        result = registry.get_all_open()
        assert "agent-001" in result
        assert isinstance(result["agent-001"], PostureCircuitBreaker)

    def test_get_status_summary_initial(self, registry):
        """Status summary with no agents must show zero counts."""
        summary = registry.get_status_summary()
        assert summary["closed"] == 0
        assert summary["open"] == 0
        assert summary["half_open"] == 0
        assert summary["total"] == 0

    async def test_get_status_summary_mixed(self, registry):
        """Status summary with mixed states."""
        registry.get_or_create("agent-001")
        registry.get_or_create("agent-002")

        # Open agent-001's circuit
        breaker1 = registry.get_or_create("agent-001")
        for _ in range(10):
            await breaker1.record_failure(
                "agent-001", "Error", "fail", "action", "critical"
            )

        summary = registry.get_status_summary()
        assert summary["total"] == 2
        assert summary["open"] == 1
        assert summary["closed"] == 1


class TestCircuitBreakerRegistryCleanup:
    """G4: Cleanup and removal operations."""

    def test_remove_agent(self, registry):
        """remove_agent must remove the breaker."""
        registry.get_or_create("agent-001")
        assert registry.has("agent-001")
        registry.remove_agent("agent-001")
        assert not registry.has("agent-001")

    def test_remove_nonexistent_is_noop(self, registry):
        """Removing a non-existent agent must not raise."""
        registry.remove_agent("nonexistent")  # Should not raise

    def test_reset_agent(self, registry):
        """reset_agent must create a fresh breaker for the agent."""
        b1 = registry.get_or_create("agent-001")
        registry.reset_agent("agent-001")
        b2 = registry.get_or_create("agent-001")
        assert b1 is not b2  # New instance after reset

    def test_has_returns_false_before_creation(self, registry):
        """has() must return False for unknown agents."""
        assert not registry.has("unknown-agent")

    def test_has_returns_true_after_creation(self, registry):
        """has() must return True after get_or_create."""
        registry.get_or_create("agent-001")
        assert registry.has("agent-001")
