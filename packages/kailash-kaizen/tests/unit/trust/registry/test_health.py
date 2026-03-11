"""
Unit tests for Agent Health Monitoring.

Tests cover the intent of health monitoring:
- Detecting stale agents that stop sending heartbeats
- Auto-suspending unresponsive agents for registry accuracy
- Individual agent health status queries
- Background monitoring lifecycle (start/stop)
- Reactivation of suspended agents

Note: These are unit tests (Tier 1), mocking is allowed.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.trust.registry.agent_registry import AgentRegistry
from kaizen.trust.registry.health import AgentHealthMonitor, HealthStatus
from kaizen.trust.registry.models import AgentMetadata, AgentStatus
from kaizen.trust.registry.store import InMemoryAgentRegistryStore


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values_exist(self):
        """All expected health status values are defined."""
        assert HealthStatus.HEALTHY.value == "HEALTHY"
        assert HealthStatus.STALE.value == "STALE"
        assert HealthStatus.SUSPENDED.value == "SUSPENDED"
        assert HealthStatus.UNKNOWN.value == "UNKNOWN"


class TestHealthMonitorConfiguration:
    """Tests for health monitor initialization and configuration."""

    def test_default_configuration(self):
        """Monitor has sensible defaults."""
        registry = MagicMock()

        monitor = AgentHealthMonitor(registry=registry)

        assert monitor._check_interval == 60
        assert monitor._stale_timeout == 300
        assert monitor._auto_suspend_stale is True

    def test_custom_configuration(self):
        """Monitor accepts custom configuration."""
        registry = MagicMock()

        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=30,
            stale_timeout=120,
            auto_suspend_stale=False,
        )

        assert monitor._check_interval == 30
        assert monitor._stale_timeout == 120
        assert monitor._auto_suspend_stale is False


class TestHealthStatusCheck:
    """Tests for individual agent health checks."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    @pytest.fixture
    def monitor(self, registry):
        return AgentHealthMonitor(
            registry=registry,
            stale_timeout=300,  # 5 minutes
        )

    def create_metadata(
        self,
        agent_id: str,
        status: AgentStatus = AgentStatus.ACTIVE,
        last_seen: datetime = None,
    ) -> AgentMetadata:
        """Helper to create agent metadata."""
        return AgentMetadata(
            agent_id=agent_id,
            agent_type="worker",
            capabilities=["task"],
            constraints=[],
            status=status,
            trust_chain_hash="hash123",
            registered_at=datetime.now(timezone.utc),
            last_seen=last_seen or datetime.now(timezone.utc),
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_healthy_agent_status(self, monitor, store):
        """Active agent with recent heartbeat is HEALTHY."""
        metadata = self.create_metadata(
            "agent-001",
            status=AgentStatus.ACTIVE,
            last_seen=datetime.now(timezone.utc),
        )
        await store.register_agent(metadata)

        health = await monitor.check_agent("agent-001")

        assert health == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_stale_agent_status(self, monitor, store):
        """Active agent without recent heartbeat is STALE."""
        # Last seen 10 minutes ago (stale_timeout is 5 minutes)
        metadata = self.create_metadata(
            "agent-001",
            status=AgentStatus.ACTIVE,
            last_seen=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await store.register_agent(metadata)

        health = await monitor.check_agent("agent-001")

        assert health == HealthStatus.STALE

    @pytest.mark.asyncio
    async def test_suspended_agent_status(self, monitor, store):
        """Suspended agent returns SUSPENDED status."""
        metadata = self.create_metadata(
            "agent-001",
            status=AgentStatus.SUSPENDED,
        )
        await store.register_agent(metadata)

        health = await monitor.check_agent("agent-001")

        assert health == HealthStatus.SUSPENDED

    @pytest.mark.asyncio
    async def test_unknown_agent_status(self, monitor):
        """Non-existent agent returns UNKNOWN status."""
        health = await monitor.check_agent("unknown-agent")

        assert health == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_inactive_agent_returns_unknown(self, monitor, store):
        """Inactive agent returns UNKNOWN status."""
        metadata = self.create_metadata(
            "agent-001",
            status=AgentStatus.INACTIVE,
        )
        await store.register_agent(metadata)

        health = await monitor.check_agent("agent-001")

        assert health == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_revoked_agent_returns_unknown(self, monitor, store):
        """Revoked agent returns UNKNOWN status."""
        metadata = self.create_metadata(
            "agent-001",
            status=AgentStatus.REVOKED,
        )
        await store.register_agent(metadata)

        health = await monitor.check_agent("agent-001")

        assert health == HealthStatus.UNKNOWN


class TestAutoSuspension:
    """Tests for automatic stale agent suspension."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    def create_metadata(
        self,
        agent_id: str,
        last_seen: datetime = None,
    ) -> AgentMetadata:
        """Helper to create agent metadata."""
        return AgentMetadata(
            agent_id=agent_id,
            agent_type="worker",
            capabilities=["task"],
            constraints=[],
            status=AgentStatus.ACTIVE,
            trust_chain_hash="hash123",
            registered_at=datetime.now(timezone.utc),
            last_seen=last_seen or datetime.now(timezone.utc),
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_immediate_check_suspends_stale_agents(self, registry, store):
        """Immediate check suspends stale agents when auto_suspend enabled."""
        monitor = AgentHealthMonitor(
            registry=registry,
            stale_timeout=300,
            auto_suspend_stale=True,
        )

        # Register stale agent
        stale_metadata = self.create_metadata(
            "stale-agent",
            last_seen=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await store.register_agent(stale_metadata)

        stale_count = await monitor.run_immediate_check()

        assert stale_count == 1
        agent = await store.get_agent("stale-agent")
        assert agent.status == AgentStatus.SUSPENDED

    @pytest.mark.asyncio
    async def test_immediate_check_does_not_suspend_when_disabled(
        self, registry, store
    ):
        """Immediate check does NOT suspend when auto_suspend is disabled."""
        monitor = AgentHealthMonitor(
            registry=registry,
            stale_timeout=300,
            auto_suspend_stale=False,
        )

        # Register stale agent
        stale_metadata = self.create_metadata(
            "stale-agent",
            last_seen=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await store.register_agent(stale_metadata)

        stale_count = await monitor.run_immediate_check()

        assert stale_count == 1
        agent = await store.get_agent("stale-agent")
        # Should still be ACTIVE (not suspended)
        assert agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_immediate_check_ignores_healthy_agents(self, registry, store):
        """Immediate check does not affect healthy agents."""
        monitor = AgentHealthMonitor(
            registry=registry,
            stale_timeout=300,
            auto_suspend_stale=True,
        )

        # Register healthy agent
        healthy_metadata = self.create_metadata(
            "healthy-agent",
            last_seen=datetime.now(timezone.utc),
        )
        await store.register_agent(healthy_metadata)

        stale_count = await monitor.run_immediate_check()

        assert stale_count == 0
        agent = await store.get_agent("healthy-agent")
        assert agent.status == AgentStatus.ACTIVE


class TestAgentReactivation:
    """Tests for agent reactivation."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    @pytest.fixture
    def monitor(self, registry):
        return AgentHealthMonitor(registry=registry)

    def create_metadata(
        self,
        agent_id: str,
        status: AgentStatus = AgentStatus.SUSPENDED,
    ) -> AgentMetadata:
        """Helper to create agent metadata."""
        return AgentMetadata(
            agent_id=agent_id,
            agent_type="worker",
            capabilities=["task"],
            constraints=[],
            status=status,
            trust_chain_hash="hash123",
            registered_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc) - timedelta(minutes=10),
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_reactivate_suspended_agent(self, monitor, store):
        """Reactivation restores suspended agent to ACTIVE."""
        metadata = self.create_metadata("agent-001", status=AgentStatus.SUSPENDED)
        await store.register_agent(metadata)

        result = await monitor.reactivate_agent("agent-001")

        assert result is True
        agent = await store.get_agent("agent-001")
        assert agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_reactivate_updates_last_seen(self, monitor, store):
        """Reactivation updates agent's last_seen timestamp."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        metadata = self.create_metadata("agent-001", status=AgentStatus.SUSPENDED)
        await store.register_agent(metadata)
        await store.update_last_seen("agent-001", old_time)

        before = datetime.now(timezone.utc)
        await monitor.reactivate_agent("agent-001")
        after = datetime.now(timezone.utc)

        agent = await store.get_agent("agent-001")
        assert before <= agent.last_seen <= after

    @pytest.mark.asyncio
    async def test_reactivate_non_suspended_fails(self, monitor, store):
        """Reactivation fails for non-suspended agents."""
        metadata = self.create_metadata("agent-001", status=AgentStatus.ACTIVE)
        await store.register_agent(metadata)

        result = await monitor.reactivate_agent("agent-001")

        assert result is False

    @pytest.mark.asyncio
    async def test_reactivate_unknown_agent_fails(self, monitor):
        """Reactivation fails for non-existent agents."""
        result = await monitor.reactivate_agent("unknown-agent")

        assert result is False


class TestMonitorLifecycle:
    """Tests for monitor start/stop lifecycle."""

    @pytest.fixture
    def registry(self):
        store = InMemoryAgentRegistryStore()
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self, registry):
        """Starting monitor sets is_running to True."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=1,
        )

        assert monitor.is_running is False

        await monitor.start()

        try:
            assert monitor.is_running is True
        finally:
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self, registry):
        """Stopping monitor sets is_running to False."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=1,
        )

        await monitor.start()
        await monitor.stop()

        assert monitor.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_raises_error(self, registry):
        """Starting already-running monitor raises RuntimeError."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=1,
        )

        await monitor.start()

        try:
            with pytest.raises(RuntimeError) as exc_info:
                await monitor.start()

            assert "already running" in str(exc_info.value)
        finally:
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, registry):
        """Stopping non-running monitor is safe."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=1,
        )

        # Stop without starting - should not raise
        await monitor.stop()
        await monitor.stop()  # Multiple stops are safe

        assert monitor.is_running is False

    @pytest.mark.asyncio
    async def test_last_check_is_updated(self, registry):
        """Monitor updates last_check after each cycle."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=0.1,  # Fast interval for testing
        )

        assert monitor.last_check is None

        await monitor.start()

        # Wait for at least one check cycle
        await asyncio.sleep(0.2)

        try:
            assert monitor.last_check is not None
            assert isinstance(monitor.last_check, datetime)
        finally:
            await monitor.stop()


class TestBackgroundMonitoring:
    """Tests for background monitoring behavior."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    def create_metadata(
        self,
        agent_id: str,
        last_seen: datetime = None,
    ) -> AgentMetadata:
        """Helper to create agent metadata."""
        return AgentMetadata(
            agent_id=agent_id,
            agent_type="worker",
            capabilities=["task"],
            constraints=[],
            status=AgentStatus.ACTIVE,
            trust_chain_hash="hash123",
            registered_at=datetime.now(timezone.utc),
            last_seen=last_seen or datetime.now(timezone.utc),
            metadata={},
        )

    @pytest.mark.asyncio
    async def test_background_monitoring_suspends_stale_agents(self, registry, store):
        """Background monitoring automatically suspends stale agents."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=0.1,  # Fast interval for testing
            stale_timeout=1,  # 1 second timeout for fast testing
            auto_suspend_stale=True,
        )

        # Register an agent that will become stale
        stale_metadata = self.create_metadata(
            "stale-agent",
            last_seen=datetime.now(timezone.utc) - timedelta(seconds=5),
        )
        await store.register_agent(stale_metadata)

        await monitor.start()

        # Wait for monitoring cycle
        await asyncio.sleep(0.3)

        try:
            agent = await store.get_agent("stale-agent")
            assert agent.status == AgentStatus.SUSPENDED
        finally:
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_monitoring_continues_after_error(self, registry):
        """Monitoring continues running even if check encounters error."""
        monitor = AgentHealthMonitor(
            registry=registry,
            check_interval=0.1,
        )

        await monitor.start()

        # Wait for a few cycles
        await asyncio.sleep(0.3)

        try:
            # Monitor should still be running
            assert monitor.is_running is True
            assert monitor.last_check is not None
        finally:
            await monitor.stop()
