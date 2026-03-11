"""
E2E Integration Tests: Health Monitoring.

Test Intent:
- Verify health status is tracked correctly for agents
- Test unhealthy agents are excluded from task assignment
- Validate health status transitions are detected
- Ensure health-aware selection works with registry

These tests use real EATP health monitoring - NO MOCKING.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from kaizen.trust import generate_keypair
from kaizen.trust.orchestration.execution_context import TrustExecutionContext
from kaizen.trust.orchestration.integration.registry_aware import (
    CapabilityBasedSelector,
    HealthAwareSelector,
    RegistryAwareRuntime,
    RegistryAwareRuntimeConfig,
)
from kaizen.trust.registry.agent_registry import AgentRegistry, DiscoveryQuery
from kaizen.trust.registry.health import AgentHealthMonitor, HealthStatus
from kaizen.trust.registry.models import AgentMetadata, AgentStatus, RegistrationRequest
from kaizen.trust.registry.store import InMemoryAgentRegistryStore


async def create_registry_with_agent():
    """Helper to create registry with registered agent."""
    store = InMemoryAgentRegistryStore()
    registry = AgentRegistry(store=store, verify_on_registration=False)
    private_key, public_key = generate_keypair()

    await registry.register(
        RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["analyze"],
            constraints=[],
            trust_chain_hash="test-hash",
            public_key=public_key,
            verify_trust=False,
        )
    )
    return registry


async def create_registry_with_workers():
    """Helper to create registry with multiple worker agents."""
    store = InMemoryAgentRegistryStore()
    registry = AgentRegistry(store=store, verify_on_registration=False)

    # Register workers
    for i in range(3):
        private_key, public_key = generate_keypair()
        await registry.register(
            RegistrationRequest(
                agent_id=f"worker-{i:03d}",
                agent_type="worker",
                capabilities=["analyze", "process"],
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=public_key,
                metadata={"role": "worker"},
                verify_trust=False,
            )
        )
        # Send heartbeat to make them healthy
        await registry.heartbeat(f"worker-{i:03d}")

    return registry


async def create_registry_with_multiple_agents():
    """Helper to create registry with multiple agents."""
    store = InMemoryAgentRegistryStore()
    registry = AgentRegistry(store=store, verify_on_registration=False)

    for i in range(3):
        private_key, public_key = generate_keypair()
        await registry.register(
            RegistrationRequest(
                agent_id=f"agent-{i:03d}",
                agent_type="worker",
                capabilities=["analyze"],
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=public_key,
                verify_trust=False,
            )
        )
    return registry


class TestHealthStatusTracking:
    """
    Test health status tracking for agents.

    Validates that health status is determined correctly based on
    agent registry state (active status and heartbeat recency).
    """

    @pytest.mark.asyncio
    async def test_active_agent_with_recent_heartbeat_is_healthy(self):
        """Agent with recent heartbeat should be considered healthy."""
        registry = await create_registry_with_agent()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Ensure heartbeat is recent
        await registry.heartbeat("agent-001")

        status = await monitor.check_agent("agent-001")

        assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_unknown_agent_returns_unknown_status(self):
        """Unknown agent should return UNKNOWN status."""
        registry = await create_registry_with_agent()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        status = await monitor.check_agent("nonexistent-agent")

        assert status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_suspended_agent_returns_suspended_status(self):
        """Suspended agent should return SUSPENDED status."""
        registry = await create_registry_with_agent()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Suspend the agent
        await registry.update_status(
            "agent-001",
            AgentStatus.SUSPENDED,
            reason="Test suspension",
        )

        status = await monitor.check_agent("agent-001")

        assert status == HealthStatus.SUSPENDED


class TestHealthStatusTransitions:
    """
    Test health status transitions.

    Validates that status changes based on registry state changes.
    """

    @pytest.mark.asyncio
    async def test_healthy_to_suspended_transition(self):
        """Status should transition from healthy to suspended."""
        registry = await create_registry_with_agent()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Initial healthy status (recent heartbeat)
        await registry.heartbeat("agent-001")
        status1 = await monitor.check_agent("agent-001")
        assert status1 == HealthStatus.HEALTHY

        # Suspend the agent
        await registry.update_status(
            "agent-001",
            AgentStatus.SUSPENDED,
            reason="Test suspension",
        )

        status2 = await monitor.check_agent("agent-001")
        assert status2 == HealthStatus.SUSPENDED

    @pytest.mark.asyncio
    async def test_suspended_to_healthy_recovery(self):
        """Agent should recover from suspended to healthy via reactivation."""
        registry = await create_registry_with_agent()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Start suspended
        await registry.update_status(
            "agent-001",
            AgentStatus.SUSPENDED,
        )
        status1 = await monitor.check_agent("agent-001")
        assert status1 == HealthStatus.SUSPENDED

        # Reactivate using health monitor
        result = await monitor.reactivate_agent("agent-001")
        assert result is True

        status2 = await monitor.check_agent("agent-001")
        assert status2 == HealthStatus.HEALTHY


class TestHealthAwareSelection:
    """
    Test health-aware agent selection.

    Validates that suspended agents are excluded from
    task assignment based on health status.
    """

    @pytest.mark.asyncio
    async def test_healthy_agents_are_selected(self):
        """Healthy agents should be eligible for selection."""
        registry = await create_registry_with_workers()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        supervisor_context = TrustExecutionContext.create(
            parent_agent_id="supervisor-001",
            task_id="test-task",
            delegated_capabilities=["analyze", "process"],
            inherited_constraints={},
        )

        base_selector = CapabilityBasedSelector()
        health_selector = HealthAwareSelector(
            inner_selector=base_selector,
            health_monitor=monitor,
            min_health_status=HealthStatus.HEALTHY,
        )

        # Get available agents from registry
        agents = await registry.discover(DiscoveryQuery())

        # Select agent for task
        selected = await health_selector.select_agent(
            task={"action": "analyze"},
            context=supervisor_context,
            available_agents=agents,
        )

        # Should select one of the healthy agents
        assert selected is not None
        assert selected.startswith("worker-")

    @pytest.mark.asyncio
    async def test_suspended_agents_are_excluded(self):
        """Suspended agents should be excluded from selection."""
        registry = await create_registry_with_workers()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        supervisor_context = TrustExecutionContext.create(
            parent_agent_id="supervisor-001",
            task_id="test-task",
            delegated_capabilities=["analyze", "process"],
            inherited_constraints={},
        )

        # Suspend all workers
        for i in range(3):
            await registry.update_status(
                f"worker-{i:03d}",
                AgentStatus.SUSPENDED,
                reason="Test suspension",
            )

        base_selector = CapabilityBasedSelector()
        health_selector = HealthAwareSelector(
            inner_selector=base_selector,
            health_monitor=monitor,
            min_health_status=HealthStatus.HEALTHY,
        )

        # Get agents
        agents = await registry.discover(DiscoveryQuery())

        # Selection should return None (no healthy agents)
        selected = await health_selector.select_agent(
            task={"action": "analyze"},
            context=supervisor_context,
            available_agents=agents,
        )

        assert selected is None


class TestHealthMonitorOperations:
    """
    Test health monitor lifecycle operations.

    Validates starting, stopping, and immediate checks.
    """

    @pytest.mark.asyncio
    async def test_monitor_start_and_stop(self):
        """Monitor should start and stop cleanly."""
        registry = await create_registry_with_multiple_agents()
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=60,
            stale_timeout=300,
        )

        await monitor.start()
        assert monitor.is_running is True

        await monitor.stop()
        assert monitor.is_running is False

    @pytest.mark.asyncio
    async def test_monitor_cannot_start_twice(self):
        """Monitor should raise error if started twice."""
        registry = await create_registry_with_multiple_agents()
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=60,
        )

        await monitor.start()

        with pytest.raises(RuntimeError):
            await monitor.start()

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_immediate_check_finds_stale_agents(self):
        """Immediate check should find stale agents."""
        registry = await create_registry_with_multiple_agents()

        # Create monitor with very short stale timeout
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=60,
            stale_timeout=1,  # 1 second
            auto_suspend_stale=False,  # Don't auto-suspend
        )

        # Wait for agents to become stale
        await asyncio.sleep(1.5)

        # Run immediate check
        stale_count = await monitor.run_immediate_check()

        # Should find stale agents
        assert stale_count > 0

    @pytest.mark.asyncio
    async def test_reactivate_suspended_agent(self):
        """Reactivate should restore suspended agent to active."""
        registry = await create_registry_with_multiple_agents()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Suspend agent
        await registry.update_status(
            "agent-000",
            AgentStatus.SUSPENDED,
        )

        # Reactivate
        result = await monitor.reactivate_agent("agent-000")
        assert result is True

        # Check status is now healthy
        status = await monitor.check_agent("agent-000")
        assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_reactivate_nonexistent_agent_fails(self):
        """Reactivating nonexistent agent should return False."""
        registry = await create_registry_with_multiple_agents()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        result = await monitor.reactivate_agent("nonexistent-agent")
        assert result is False

    @pytest.mark.asyncio
    async def test_reactivate_non_suspended_agent_fails(self):
        """Reactivating non-suspended agent should return False."""
        registry = await create_registry_with_multiple_agents()
        monitor = AgentHealthMonitor(
            registry=registry, check_interval=60, stale_timeout=300
        )

        # Ensure agent is active, not suspended
        await registry.heartbeat("agent-000")

        result = await monitor.reactivate_agent("agent-000")
        assert result is False
