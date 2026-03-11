"""
Tier 2 Integration Tests for AgentRegistry.

Tests centralized agent registry with Ollama models (llama3.2:3b).
NO MOCKING - real infrastructure only ($0 cost via Ollama).

Test Scenarios:
1. Multi-runtime agent registration
2. Capability-based agent discovery with semantic matching
3. Event broadcasting across runtimes
4. Heartbeat monitoring with real agent lifecycle
5. Status management and transitions
6. Concurrent registry operations
7. Agent deregistration with cleanup
8. Registry lifecycle management
"""

import asyncio

import pytest
import pytest_asyncio
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration import (
    AgentRegistry,
    AgentRegistryConfig,
    AgentStatus,
    RegistryEvent,
    RegistryEventType,
)
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def integration_registry_config():
    """Create integration test configuration for agent registry."""
    return AgentRegistryConfig(
        enable_heartbeat_monitoring=True,
        heartbeat_timeout=5.0,  # Short timeout for testing (seconds)
        auto_deregister_timeout=10.0,  # Auto-deregister after 10s
        enable_event_broadcasting=True,
        event_queue_size=100,
    )


@pytest_asyncio.fixture
async def registry(integration_registry_config):
    """Create registry instance with integration config."""
    registry = AgentRegistry(config=integration_registry_config)
    await registry.start()
    yield registry
    await registry.shutdown()


@pytest.fixture
def code_generation_signature():
    """Signature for code generation agent."""

    class CodeGenerationSignature(Signature):
        task: str = InputField(description="Task description")
        code: str = OutputField(description="Generated code")

    return CodeGenerationSignature()


@pytest.fixture
def data_analysis_signature():
    """Signature for data analysis agent."""

    class DataAnalysisSignature(Signature):
        task: str = InputField(description="Task description")
        analysis: str = OutputField(description="Analysis results")

    return DataAnalysisSignature()


@pytest.fixture
def qa_signature():
    """Signature for Q&A agent."""

    class QASignature(Signature):
        question: str = InputField(description="Question to answer")
        answer: str = OutputField(description="Answer")

    return QASignature()


@pytest.fixture
def writing_signature():
    """Signature for writing agent."""

    class WritingSignature(Signature):
        task: str = InputField(description="Writing task")
        content: str = OutputField(description="Written content")

    return WritingSignature()


@pytest.fixture
def code_agent(code_generation_signature):
    """Create real code generation agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:3b",
        temperature=0.7,
    )

    agent = BaseAgent(
        config=config,
        signature=code_generation_signature,
    )

    # Override a2a_card with explicit capabilities
    agent._a2a_card = {
        "name": "CodeAgent",
        "capability": "Code generation and software development",
        "description": "Generate Python, JavaScript, and other programming code",
    }

    return agent


@pytest.fixture
def data_agent(data_analysis_signature):
    """Create real data analysis agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:3b",
        temperature=0.7,
    )

    agent = BaseAgent(
        config=config,
        signature=data_analysis_signature,
    )

    # Override a2a_card with explicit capabilities
    agent._a2a_card = {
        "name": "DataAgent",
        "capability": "Data analysis and visualization",
        "description": "Analyze datasets and create visualizations",
    }

    return agent


@pytest.fixture
def qa_agent(qa_signature):
    """Create real Q&A agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:3b",
        temperature=0.7,
    )

    agent = BaseAgent(
        config=config,
        signature=qa_signature,
    )

    # Override a2a_card with explicit capabilities
    agent._a2a_card = {
        "name": "QAAgent",
        "capability": "Question answering and information retrieval",
        "description": "Answer general knowledge questions",
    }

    return agent


@pytest.fixture
def writing_agent(writing_signature):
    """Create real writing agent with Ollama."""
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:3b",
        temperature=0.7,
    )

    agent = BaseAgent(
        config=config,
        signature=writing_signature,
    )

    # Override a2a_card with explicit capabilities
    agent._a2a_card = {
        "name": "WritingAgent",
        "capability": "Content writing and editing",
        "description": "Write blog posts, articles, and documentation",
    }

    return agent


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multi_runtime_agent_registration_integration(
    registry, code_agent, data_agent, qa_agent
):
    """Test registering agents from multiple runtimes to single registry."""
    # Register agents from different runtimes
    agent_id_1 = await registry.register_agent(code_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(data_agent, runtime_id="runtime_2")
    agent_id_3 = await registry.register_agent(qa_agent, runtime_id="runtime_1")

    # Verify all agents registered
    assert len(registry.agents) == 3
    assert agent_id_1 in registry.agents
    assert agent_id_2 in registry.agents
    assert agent_id_3 in registry.agents

    # Verify runtime associations
    assert agent_id_1 in registry.runtime_agents["runtime_1"]
    assert agent_id_2 in registry.runtime_agents["runtime_2"]
    assert agent_id_3 in registry.runtime_agents["runtime_1"]

    # Verify runtime_1 has 2 agents, runtime_2 has 1
    assert len(registry.runtime_agents["runtime_1"]) == 2
    assert len(registry.runtime_agents["runtime_2"]) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_capability_based_discovery_integration(
    registry, code_agent, data_agent, writing_agent
):
    """Test semantic capability-based agent discovery with real agents."""
    # Register agents
    await registry.register_agent(code_agent, runtime_id="runtime_1")
    await registry.register_agent(data_agent, runtime_id="runtime_1")
    await registry.register_agent(writing_agent, runtime_id="runtime_2")

    # Search for code-related capability (use terms that appear in the capability string)
    code_agents = await registry.find_agents_by_capability(
        "code generation",  # Matches "Code generation and software development"
        status_filter=AgentStatus.ACTIVE,
    )
    assert len(code_agents) >= 1
    assert any(meta.agent == code_agent for meta in code_agents)

    # Search for data-related capability
    data_agents = await registry.find_agents_by_capability(
        "data analysis",  # Matches "Data analysis and visualization"
        status_filter=AgentStatus.ACTIVE,
    )
    assert len(data_agents) >= 1
    assert any(meta.agent == data_agent for meta in data_agents)

    # Search for writing capability
    writing_agents = await registry.find_agents_by_capability(
        "writing",  # Matches "Content writing and editing"
        status_filter=AgentStatus.ACTIVE,
    )
    assert len(writing_agents) >= 1
    assert any(meta.agent == writing_agent for meta in writing_agents)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_event_broadcasting_integration(registry, code_agent, data_agent):
    """Test event broadcasting across runtimes."""
    received_events = []

    async def event_callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to registration events
    registry.subscribe(RegistryEventType.AGENT_REGISTERED, event_callback)

    # Register agents from different runtimes
    agent_id_1 = await registry.register_agent(code_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(data_agent, runtime_id="runtime_2")

    # Wait for events to be processed
    await asyncio.sleep(0.5)

    # Verify events were received
    assert len(received_events) >= 2

    # Verify event details
    registration_events = [
        e for e in received_events if e.event_type == RegistryEventType.AGENT_REGISTERED
    ]
    assert len(registration_events) >= 2

    agent_ids_from_events = {e.agent_id for e in registration_events}
    assert agent_id_1 in agent_ids_from_events
    assert agent_id_2 in agent_ids_from_events


@pytest.mark.asyncio
@pytest.mark.integration
async def test_status_change_events_integration(registry, code_agent):
    """Test status change event broadcasting."""
    received_events = []

    async def event_callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to status change events
    registry.subscribe(RegistryEventType.AGENT_STATUS_CHANGED, event_callback)

    # Register agent
    agent_id = await registry.register_agent(code_agent, runtime_id="runtime_1")

    # Change agent status
    await registry.update_agent_status(agent_id, AgentStatus.DEGRADED)

    # Wait for event processing
    await asyncio.sleep(0.3)

    # Verify status change event
    status_events = [
        e
        for e in received_events
        if e.event_type == RegistryEventType.AGENT_STATUS_CHANGED
    ]
    assert len(status_events) >= 1

    # Verify event details
    event = status_events[0]
    assert event.agent_id == agent_id
    assert event.metadata["new_status"] == AgentStatus.DEGRADED.value


@pytest.mark.asyncio
@pytest.mark.integration
async def test_heartbeat_monitoring_integration(registry, code_agent):
    """Test heartbeat monitoring with real agent lifecycle.

    Note: Uses 5s heartbeat timeout and 10s auto-deregister timeout.
    Registry monitors heartbeats and marks agents as stale after timeout.
    """
    # Register agent
    agent_id = await registry.register_agent(code_agent, runtime_id="runtime_1")

    # Verify initial status
    metadata = registry.agents[agent_id]
    assert metadata.status == AgentStatus.ACTIVE

    # Update heartbeat manually (simulates runtime sending heartbeat)
    await registry.update_agent_heartbeat(agent_id)

    # Wait less than timeout - agent should still be active
    await asyncio.sleep(2.0)
    assert registry.agents[agent_id].status == AgentStatus.ACTIVE

    # Wait for auto-deregister timeout (10s + buffer)
    await asyncio.sleep(12.0)

    # Verify agent was deregistered due to stale heartbeat
    # (heartbeat monitor auto-deregisters stale agents)
    assert agent_id not in registry.agents


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_registration_integration(
    registry, code_agent, data_agent, qa_agent, writing_agent
):
    """Test concurrent agent registration from multiple runtimes."""
    # Register agents concurrently
    tasks = [
        registry.register_agent(code_agent, runtime_id="runtime_1"),
        registry.register_agent(data_agent, runtime_id="runtime_2"),
        registry.register_agent(qa_agent, runtime_id="runtime_3"),
        registry.register_agent(writing_agent, runtime_id="runtime_1"),
    ]

    agent_ids = await asyncio.gather(*tasks)

    # Verify all agents registered successfully
    assert len(agent_ids) == 4
    assert all(agent_id in registry.agents for agent_id in agent_ids)

    # Verify runtime associations
    assert len(registry.runtime_agents["runtime_1"]) == 2
    assert len(registry.runtime_agents["runtime_2"]) == 1
    assert len(registry.runtime_agents["runtime_3"]) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_deregistration_with_cleanup_integration(
    registry, code_agent, data_agent
):
    """Test agent deregistration removes all references."""
    # Register agents
    agent_id_1 = await registry.register_agent(code_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(data_agent, runtime_id="runtime_1")

    assert len(registry.agents) == 2
    assert len(registry.runtime_agents["runtime_1"]) == 2

    # Deregister first agent
    success = await registry.deregister_agent(agent_id_1, runtime_id="runtime_1")
    assert success is True

    # Verify agent removed from all indexes
    assert agent_id_1 not in registry.agents
    assert agent_id_1 not in registry.runtime_agents["runtime_1"]
    assert agent_id_1 not in registry.status_index[AgentStatus.ACTIVE]

    # Verify second agent still registered
    assert agent_id_2 in registry.agents
    assert len(registry.runtime_agents["runtime_1"]) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_runtime_join_leave_events_integration(registry, code_agent):
    """Test RUNTIME_JOINED and RUNTIME_LEFT event broadcasting."""
    received_events = []

    async def event_callback(event: RegistryEvent):
        received_events.append(event)

    # Subscribe to runtime events
    registry.subscribe(RegistryEventType.RUNTIME_JOINED, event_callback)
    registry.subscribe(RegistryEventType.RUNTIME_LEFT, event_callback)

    # Register agent (new runtime joins)
    agent_id = await registry.register_agent(code_agent, runtime_id="runtime_new")

    # Deregister agent (runtime leaves if no more agents)
    await registry.deregister_agent(agent_id, runtime_id="runtime_new")

    # Wait for event processing
    await asyncio.sleep(0.3)

    # Verify RUNTIME_JOINED event
    join_events = [
        e for e in received_events if e.event_type == RegistryEventType.RUNTIME_JOINED
    ]
    assert len(join_events) >= 1
    assert join_events[0].runtime_id == "runtime_new"

    # Verify RUNTIME_LEFT event
    leave_events = [
        e for e in received_events if e.event_type == RegistryEventType.RUNTIME_LEFT
    ]
    assert len(leave_events) >= 1
    assert leave_events[0].runtime_id == "runtime_new"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_capability_indexing_integration(
    registry, code_agent, data_agent, qa_agent
):
    """Test capability index is properly maintained."""
    # Register agents with different capabilities
    agent_id_1 = await registry.register_agent(code_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(data_agent, runtime_id="runtime_1")
    agent_id_3 = await registry.register_agent(qa_agent, runtime_id="runtime_2")

    # Verify capability index contains expected capabilities
    # Each agent should have at least one capability keyword indexed
    assert len(registry.capability_index) > 0

    # Verify agents are findable by capability
    code_results = await registry.find_agents_by_capability(
        "code", status_filter=AgentStatus.ACTIVE
    )
    data_results = await registry.find_agents_by_capability(
        "data", status_filter=AgentStatus.ACTIVE
    )
    qa_results = await registry.find_agents_by_capability(
        "question", status_filter=AgentStatus.ACTIVE
    )

    # At least one result for each capability
    assert len(code_results) >= 1
    assert len(data_results) >= 1
    assert len(qa_results) >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_status_filtering_integration(registry, code_agent, data_agent):
    """Test agent discovery with status filtering."""
    # Register agents
    agent_id_1 = await registry.register_agent(code_agent, runtime_id="runtime_1")
    agent_id_2 = await registry.register_agent(data_agent, runtime_id="runtime_1")

    # Mark one agent as DEGRADED
    await registry.update_agent_status(agent_id_1, AgentStatus.DEGRADED)

    # Search for ACTIVE agents only (use real capability term)
    active_agents = await registry.find_agents_by_capability(
        "data",  # Matches "Data analysis and visualization"
        status_filter=AgentStatus.ACTIVE,
    )
    assert len(active_agents) == 1
    assert active_agents[0].agent_id == agent_id_2

    # Search for DEGRADED agents only (use real capability term)
    degraded_agents = await registry.find_agents_by_capability(
        "code",  # Matches "Code generation and software development"
        status_filter=AgentStatus.DEGRADED,
    )
    assert len(degraded_agents) == 1
    assert degraded_agents[0].agent_id == agent_id_1

    # Search with no filter (None) - should return all matching agents
    all_agents = await registry.find_agents_by_capability(
        "generation",  # Matches only "Code generation" (CodeAgent), not "Data analysis"
        status_filter=None,
    )
    assert len(all_agents) == 1
    assert all_agents[0].agent_id == agent_id_1  # CodeAgent (DEGRADED)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_registry_lifecycle_integration(integration_registry_config):
    """Test registry start and shutdown lifecycle."""
    registry = AgentRegistry(config=integration_registry_config)

    # Start registry
    await registry.start()
    assert registry._running is True

    # Shutdown registry
    await registry.shutdown()
    assert registry._running is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_capability_search_integration(
    registry, code_agent, data_agent, qa_agent, writing_agent
):
    """Test concurrent capability searches."""
    # Register agents
    await registry.register_agent(code_agent, runtime_id="runtime_1")
    await registry.register_agent(data_agent, runtime_id="runtime_1")
    await registry.register_agent(qa_agent, runtime_id="runtime_2")
    await registry.register_agent(writing_agent, runtime_id="runtime_2")

    # Perform concurrent capability searches
    tasks = [
        registry.find_agents_by_capability("code", status_filter=AgentStatus.ACTIVE),
        registry.find_agents_by_capability("data", status_filter=AgentStatus.ACTIVE),
        registry.find_agents_by_capability(
            "question", status_filter=AgentStatus.ACTIVE
        ),
        registry.find_agents_by_capability("writing", status_filter=AgentStatus.ACTIVE),
    ]

    results = await asyncio.gather(*tasks)

    # Verify all searches completed
    assert len(results) == 4
    assert all(len(result) >= 1 for result in results)


# ============================================================================
# Summary
# ============================================================================
# Total Tests: 13
# Coverage:
# - Multi-runtime registration (1 test)
# - Capability-based discovery (2 tests: semantic search, indexing)
# - Event broadcasting (3 tests: registration, status change, runtime join/leave)
# - Heartbeat monitoring (1 test)
# - Concurrent operations (2 tests: registration, search)
# - Agent deregistration (1 test)
# - Status filtering (1 test)
# - Registry lifecycle (1 test)
# - Capability indexing (1 test)
#
# Cost: $0.00 (Ollama is free)
# Infrastructure: Real Ollama models (llama3.2:3b)
# NO MOCKING - 100% real infrastructure testing
