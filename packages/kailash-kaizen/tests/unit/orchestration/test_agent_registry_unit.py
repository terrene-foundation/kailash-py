"""
Tier 1 Unit Tests for AgentRegistry

Test Coverage:
- Agent Lifecycle (5 tests)
- Agent Discovery (5 tests)
- Status Management (4 tests)
- Event Broadcasting (4 tests)
- Multi-Runtime Coordination (4 tests)
- Background Tasks (3 tests)

Strategy: Fast execution (<5s), mocked infrastructure
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.registry import (
    AgentRegistry,
    AgentRegistryConfig,
    RegistryEvent,
    RegistryEventType,
)
from kaizen.orchestration.runtime import AgentStatus
from kaizen.signatures import InputField, OutputField, Signature

# Check A2A availability for capability indexing tests
try:
    from kaizen.nodes.ai.a2a import A2AAgentCard

    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False

# ============================================================================
# Test Fixtures
# ============================================================================


class _TestSignature(Signature):
    """Simple signature for testing (prefixed to avoid pytest collection)."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


class _TestAgentConfig:
    """Simple config for testing (prefixed to avoid pytest collection)."""

    def __init__(self):
        self.llm_provider = "mock"
        self.model = "mock-model"


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    agent = Mock(spec=BaseAgent)
    agent.agent_id = "test_agent_1"
    agent.config = _TestAgentConfig()
    agent.signature = _TestSignature()
    agent.run = AsyncMock(return_value={"result": "success"})
    agent._a2a_card = {
        "name": "CodeAgent",
        "capability": "Code generation and analysis",
        "description": "Expert in Python, JavaScript, and other programming languages",
    }
    return agent


@pytest.fixture
def mock_agent_2():
    """Create a second mock agent for testing."""
    agent = Mock(spec=BaseAgent)
    agent.agent_id = "test_agent_2"
    agent.config = _TestAgentConfig()
    agent.signature = _TestSignature()
    agent.run = AsyncMock(return_value={"result": "success"})
    agent._a2a_card = {
        "name": "DataAgent",
        "capability": "Data analysis and visualization",
        "description": "Expert in data science, statistics, and ML",
    }
    return agent


@pytest.fixture
def registry_config():
    """Create default registry configuration."""
    return AgentRegistryConfig(
        enable_heartbeat_monitoring=True,
        heartbeat_timeout=60.0,
        auto_deregister_timeout=300.0,
        enable_capability_indexing=True,
        rebuild_index_interval=300.0,
        enable_event_broadcasting=True,
        event_queue_size=1000,
    )


@pytest.fixture
def registry(registry_config):
    """Create AgentRegistry instance."""
    return AgentRegistry(config=registry_config)


# ============================================================================
# Agent Lifecycle Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_agent_registration_basic(registry, mock_agent):
    """Test basic agent registration."""
    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Verify agent is registered
    assert agent_id == mock_agent.agent_id
    assert agent_id in registry.agents
    assert registry.agents[agent_id].status == AgentStatus.ACTIVE
    assert "runtime_1" in registry.runtime_agents
    assert agent_id in registry.runtime_agents["runtime_1"]


@pytest.mark.asyncio
async def test_agent_registration_duplicate_id(registry, mock_agent):
    """Test duplicate agent registration raises error."""
    # Register agent first time
    await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Try to register again - should fail
    with pytest.raises(ValueError, match="already registered"):
        await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")


@pytest.mark.asyncio
async def test_agent_registration_auto_id_generation(registry):
    """Test automatic agent ID generation."""
    # Create agent without agent_id
    agent = Mock(spec=BaseAgent)
    agent.agent_id = None  # No ID
    agent.config = _TestAgentConfig()
    agent.signature = _TestSignature()
    agent._a2a_card = {"name": "Test", "capability": "Testing"}

    # Register agent
    agent_id = await registry.register_agent(agent=agent, runtime_id="runtime_1")

    # Verify ID was generated
    assert agent_id is not None
    assert agent_id.startswith("agent_")
    assert agent_id in registry.agents


@pytest.mark.asyncio
async def test_agent_deregistration(registry, mock_agent):
    """Test agent deregistration."""
    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Deregister agent
    success = await registry.deregister_agent(agent_id, "runtime_1")

    # Verify agent is deregistered
    assert success is True
    assert agent_id not in registry.agents
    assert agent_id not in registry.runtime_agents.get("runtime_1", set())


@pytest.mark.asyncio
async def test_agent_deregistration_not_found(registry):
    """Test deregistering non-existent agent returns False."""
    success = await registry.deregister_agent("nonexistent_id", "runtime_1")
    assert success is False


# ============================================================================
# Agent Discovery Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_get_agent_by_id(registry, mock_agent):
    """Test getting agent metadata by ID."""
    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Get agent
    metadata = await registry.get_agent(agent_id)

    # Verify metadata
    assert metadata is not None
    assert metadata.agent_id == agent_id
    assert metadata.agent == mock_agent
    assert metadata.status == AgentStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_agent_not_found(registry):
    """Test getting non-existent agent returns None."""
    metadata = await registry.get_agent("nonexistent_id")
    assert metadata is None


@pytest.mark.asyncio
async def test_list_agents_all(registry, mock_agent, mock_agent_2):
    """Test listing all agents."""
    # Register agents
    await registry.register_agent(mock_agent, runtime_id="runtime_1")
    await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # List all agents
    agents = await registry.list_agents()

    # Verify all agents returned
    assert len(agents) == 2
    assert any(a.agent_id == mock_agent.agent_id for a in agents)
    assert any(a.agent_id == mock_agent_2.agent_id for a in agents)


@pytest.mark.asyncio
async def test_list_agents_by_runtime(registry, mock_agent, mock_agent_2):
    """Test listing agents by runtime ID."""
    # Register agents to different runtimes
    await registry.register_agent(mock_agent, runtime_id="runtime_1")
    await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # List agents for runtime_1
    agents = await registry.list_agents(runtime_id="runtime_1")

    # Verify only runtime_1 agents returned
    assert len(agents) == 1
    assert agents[0].agent_id == mock_agent.agent_id


@pytest.mark.asyncio
@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability indexing"
)
async def test_find_agents_by_capability(registry, mock_agent, mock_agent_2):
    """Test finding agents by capability."""
    # Register agents
    await registry.register_agent(mock_agent, runtime_id="runtime_1")
    await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Find agents with "code" capability
    agents = await registry.find_agents_by_capability("code")

    # Verify correct agent found
    assert len(agents) >= 1
    assert any(a.agent_id == mock_agent.agent_id for a in agents)


# ============================================================================
# Status Management Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_update_agent_status(registry, mock_agent):
    """Test updating agent status."""
    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Update status
    success = await registry.update_agent_status(
        agent_id=agent_id, status=AgentStatus.DEGRADED, runtime_id="runtime_1"
    )

    # Verify status updated
    assert success is True
    assert registry.agents[agent_id].status == AgentStatus.DEGRADED


@pytest.mark.asyncio
async def test_update_agent_status_not_found(registry):
    """Test updating status of non-existent agent returns False."""
    success = await registry.update_agent_status(
        agent_id="nonexistent_id", status=AgentStatus.DEGRADED
    )
    assert success is False


@pytest.mark.asyncio
async def test_update_agent_heartbeat(registry, mock_agent):
    """Test updating agent heartbeat."""
    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Get initial heartbeat
    initial_heartbeat = registry.agents[agent_id].last_heartbeat

    # Wait a bit
    await asyncio.sleep(0.1)

    # Update heartbeat
    success = await registry.update_agent_heartbeat(agent_id)

    # Verify heartbeat updated
    assert success is True
    assert registry.agents[agent_id].last_heartbeat > initial_heartbeat


@pytest.mark.asyncio
async def test_find_agents_by_status(registry, mock_agent, mock_agent_2):
    """Test finding agents by status."""
    # Register agents
    agent_id_1 = await registry.register_agent(mock_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Update one agent to DEGRADED
    await registry.update_agent_status(agent_id_1, AgentStatus.DEGRADED)

    # Find ACTIVE agents
    active_agents = await registry.find_agents_by_status(AgentStatus.ACTIVE)

    # Verify correct agents found
    assert len(active_agents) == 1
    assert active_agents[0].agent_id == agent_id_2

    # Find DEGRADED agents
    degraded_agents = await registry.find_agents_by_status(AgentStatus.DEGRADED)
    assert len(degraded_agents) == 1
    assert degraded_agents[0].agent_id == agent_id_1


# ============================================================================
# Event Broadcasting Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_event_subscription(registry):
    """Test event subscription."""
    # Track received events
    received_events = []

    # Create callback
    def callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to AGENT_REGISTERED events
    registry.subscribe(RegistryEventType.AGENT_REGISTERED, callback)

    # Verify subscription
    assert callback in registry.event_listeners[RegistryEventType.AGENT_REGISTERED]


@pytest.mark.asyncio
async def test_event_unsubscribe(registry):
    """Test event unsubscription."""

    # Create callback
    def callback(event: RegistryEvent):
        pass

    # Subscribe
    registry.subscribe(RegistryEventType.AGENT_REGISTERED, callback)

    # Unsubscribe
    registry.unsubscribe(RegistryEventType.AGENT_REGISTERED, callback)

    # Verify unsubscribed
    assert callback not in registry.event_listeners[RegistryEventType.AGENT_REGISTERED]


@pytest.mark.asyncio
async def test_event_emission_on_registration(registry, mock_agent):
    """Test event is emitted on agent registration."""
    # Start registry
    await registry.start()

    # Track received events
    received_events = []

    # Create async callback
    async def callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to AGENT_REGISTERED events
    registry.subscribe(RegistryEventType.AGENT_REGISTERED, callback)

    # Register agent (will emit event)
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Wait for event to be processed
    await asyncio.sleep(0.2)

    # Verify event received
    assert len(received_events) >= 1
    assert received_events[0].event_type == RegistryEventType.AGENT_REGISTERED
    assert received_events[0].agent_id == agent_id

    # Cleanup
    await registry.shutdown()


@pytest.mark.asyncio
async def test_event_emission_on_status_change(registry, mock_agent):
    """Test event is emitted on status change."""
    # Start registry
    await registry.start()

    # Track received events
    received_events = []

    # Create async callback
    async def callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to STATUS_CHANGED events
    registry.subscribe(RegistryEventType.AGENT_STATUS_CHANGED, callback)

    # Register agent
    agent_id = await registry.register_agent(agent=mock_agent, runtime_id="runtime_1")

    # Update status (will emit event)
    await registry.update_agent_status(agent_id, AgentStatus.DEGRADED, "runtime_1")

    # Wait for event to be processed
    await asyncio.sleep(0.2)

    # Verify event received
    assert len(received_events) >= 1
    assert received_events[0].event_type == RegistryEventType.AGENT_STATUS_CHANGED
    assert received_events[0].agent_id == agent_id

    # Cleanup
    await registry.shutdown()


# ============================================================================
# Multi-Runtime Coordination Tests (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_multi_runtime_agent_tracking(registry, mock_agent, mock_agent_2):
    """Test tracking agents across multiple runtimes."""
    # Register agents to different runtimes
    agent_id_1 = await registry.register_agent(mock_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Verify runtime tracking
    assert agent_id_1 in registry.runtime_agents["runtime_1"]
    assert agent_id_2 in registry.runtime_agents["runtime_2"]
    assert len(registry.runtime_agents) == 2


@pytest.mark.asyncio
async def test_find_agents_by_runtime(registry, mock_agent, mock_agent_2):
    """Test finding all agents for a specific runtime."""
    # Register agents
    agent_id_1 = await registry.register_agent(mock_agent, runtime_id="runtime_1")
    await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Find agents for runtime_1
    agents = await registry.find_agents_by_runtime("runtime_1")

    # Verify correct agents found
    assert len(agents) == 1
    assert agents[0].agent_id == agent_id_1


@pytest.mark.asyncio
async def test_runtime_isolation(registry, mock_agent, mock_agent_2):
    """Test runtime isolation - deregistering from one runtime doesn't affect others."""
    # Register agents to different runtimes
    agent_id_1 = await registry.register_agent(mock_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Deregister agent from runtime_1
    await registry.deregister_agent(agent_id_1, "runtime_1")

    # Verify runtime_2 agent still exists
    assert agent_id_2 in registry.agents
    assert agent_id_2 in registry.runtime_agents["runtime_2"]


@pytest.mark.asyncio
async def test_metrics_multi_runtime(registry, mock_agent, mock_agent_2):
    """Test metrics across multiple runtimes."""
    # Register agents to different runtimes
    await registry.register_agent(mock_agent, runtime_id="runtime_1")
    await registry.register_agent(mock_agent_2, runtime_id="runtime_2")

    # Get metrics
    metrics = await registry.get_metrics()

    # Verify metrics
    assert metrics["total_agents"] == 2
    assert metrics["total_runtimes"] == 2
    assert "runtime_1" in metrics["runtime_distribution"]
    assert "runtime_2" in metrics["runtime_distribution"]
    assert metrics["total_registrations"] == 2


# ============================================================================
# Background Tasks Tests (3 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_registry_start_and_shutdown(registry):
    """Test starting and shutting down registry."""
    # Start registry
    await registry.start()

    # Verify running
    assert registry._running is True

    # Shutdown registry
    await registry.shutdown()

    # Verify shutdown
    assert registry._running is False
    assert len(registry.agents) == 0


@pytest.mark.asyncio
async def test_heartbeat_monitoring_task_starts(registry):
    """Test heartbeat monitoring task starts when configured."""
    # Start registry
    await registry.start()

    # Verify heartbeat monitor task created
    assert registry._heartbeat_monitor_task is not None

    # Cleanup
    await registry.shutdown()


@pytest.mark.asyncio
async def test_event_broadcaster_task_starts(registry):
    """Test event broadcaster task starts when configured."""
    # Start registry
    await registry.start()

    # Verify event broadcaster task created
    assert registry._event_broadcaster_task is not None

    # Cleanup
    await registry.shutdown()


# ============================================================================
# Capability Indexing Tests (2 tests)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability indexing"
)
async def test_capability_indexing(registry, mock_agent):
    """Test capability indexing on agent registration."""
    # Register agent
    await registry.register_agent(mock_agent, runtime_id="runtime_1")

    # Verify capability index updated
    assert len(registry.capability_index) > 0
    # Check if capability was indexed
    found = False
    for cap, agent_ids in registry.capability_index.items():
        if mock_agent.agent_id in agent_ids:
            found = True
            break
    assert found


@pytest.mark.asyncio
@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability indexing"
)
async def test_capability_deindexing(registry, mock_agent):
    """Test capability deindexing on agent deregistration."""
    # Register agent
    agent_id = await registry.register_agent(mock_agent, runtime_id="runtime_1")

    # Verify indexed
    initial_index_size = len(registry.capability_index)
    assert initial_index_size > 0

    # Deregister agent
    await registry.deregister_agent(agent_id, "runtime_1")

    # Verify agent removed from capability index
    for cap, agent_ids in registry.capability_index.items():
        assert agent_id not in agent_ids
