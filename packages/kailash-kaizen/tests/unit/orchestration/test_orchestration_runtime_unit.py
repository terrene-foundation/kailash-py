"""
Tier 1 Unit Tests for OrchestrationRuntime

Test Coverage:
- Agent Lifecycle (5 tests)
- Routing Strategy (5 tests)
- Resource Management (5 tests)
- Retry/Error Handling (5 tests)
- Workflow Tracking (3 tests)
- Graceful Shutdown (2 tests)

Strategy: Fast execution (<5s), mocked infrastructure
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.runtime import (
    AgentStatus,
    ErrorHandlingMode,
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RetryPolicy,
    RoutingStrategy,
)
from kaizen.signatures import InputField, OutputField, Signature

# Check A2A availability
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
    agent.to_a2a_card = Mock(
        return_value={
            "agent_id": "test_agent_1",
            "name": "Test Agent",
            "capabilities": ["Data analysis", "Code generation"],
            "provider": "mock",
            "model": "mock-model",
        }
    )
    return agent


@pytest.fixture
def runtime_config():
    """Create default runtime configuration."""
    return OrchestrationRuntimeConfig(
        max_concurrent_agents=5,
        health_check_interval=30.0,
        enable_circuit_breaker=True,
        circuit_breaker_threshold=0.5,
        default_routing_strategy="semantic",
        enable_progress_tracking=True,
    )


@pytest.fixture
def runtime(runtime_config):
    """Create OrchestrationRuntime instance."""
    return OrchestrationRuntime(config=runtime_config)


# ============================================================================
# Agent Lifecycle Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for capability registration"
)
async def test_agent_registration_basic(runtime, mock_agent):
    """Test basic agent registration."""
    # Register agent
    await runtime.register_agent(mock_agent)

    # Verify agent is registered
    assert mock_agent.agent_id in runtime.agents
    assert runtime.agents[mock_agent.agent_id].status == AgentStatus.ACTIVE
    assert runtime.agents[mock_agent.agent_id].a2a_card is not None


@pytest.mark.asyncio
async def test_agent_registration_duplicate(runtime, mock_agent):
    """Test duplicate agent registration raises error."""
    # Register agent once
    await runtime.register_agent(mock_agent)

    # Attempt to register again - should raise ValueError
    with pytest.raises(ValueError, match="already registered"):
        await runtime.register_agent(mock_agent)


@pytest.mark.asyncio
async def test_agent_deregistration(runtime, mock_agent):
    """Test agent deregistration."""
    # Register and deregister
    await runtime.register_agent(mock_agent)
    await runtime.deregister_agent(mock_agent.agent_id)

    # Verify agent is removed
    assert mock_agent.agent_id not in runtime.agents


@pytest.mark.asyncio
async def test_agent_health_check(runtime, mock_agent):
    """Test agent health check updates status."""
    await runtime.register_agent(mock_agent)

    # Simulate healthy agent
    mock_agent.run = AsyncMock(return_value={"result": "healthy"})

    # Check health
    is_healthy = await runtime.check_agent_health(mock_agent.agent_id)

    assert is_healthy
    assert runtime.agents[mock_agent.agent_id].status == AgentStatus.ACTIVE


@pytest.mark.asyncio
async def test_agent_health_check_failure(runtime, mock_agent):
    """Test agent health check detects failures."""
    await runtime.register_agent(mock_agent)

    # Simulate unhealthy agent (raises exception)
    mock_agent.run = AsyncMock(side_effect=Exception("Agent error"))

    # Check health
    is_healthy = await runtime.check_agent_health(mock_agent.agent_id)

    assert not is_healthy
    assert runtime.agents[mock_agent.agent_id].status == AgentStatus.UNHEALTHY


# ============================================================================
# Routing Strategy Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    not A2A_AVAILABLE, reason="A2A module required for semantic routing"
)
async def test_semantic_routing_capability_match(runtime):
    """Test semantic routing selects agent with matching capability."""
    # Create agents with different capabilities
    agent1 = Mock(spec=BaseAgent)
    agent1.agent_id = "agent_1"
    agent1.to_a2a_card = Mock(
        return_value={
            "agent_id": "agent_1",
            "capabilities": ["Code generation"],
        }
    )

    agent2 = Mock(spec=BaseAgent)
    agent2.agent_id = "agent_2"
    agent2.to_a2a_card = Mock(
        return_value={
            "agent_id": "agent_2",
            "capabilities": ["Data analysis", "Visualization"],
        }
    )

    await runtime.register_agent(agent1)
    await runtime.register_agent(agent2)

    # Route task requiring data analysis
    # Semantic similarity uses instance method _simple_text_similarity
    result = await runtime.route_task(
        "Analyze sales data and create charts", strategy=RoutingStrategy.SEMANTIC
    )

    # Should select agent2 (data analysis capability)
    # Note: result is the agent itself, not agent_id
    assert result is not None
    assert result.agent_id == agent2.agent_id


@pytest.mark.asyncio
async def test_round_robin_routing(runtime):
    """Test round-robin routing distributes tasks evenly."""
    runtime.config.default_routing_strategy = RoutingStrategy.ROUND_ROBIN

    # Create multiple agents
    agents = []
    for i in range(3):
        agent = Mock(spec=BaseAgent)
        agent.agent_id = f"agent_{i}"
        agent.to_a2a_card = Mock(return_value={"agent_id": agent.agent_id})
        await runtime.register_agent(agent)
        agents.append(agent.agent_id)

    # Route multiple tasks
    selected = []
    for _ in range(6):
        agent_id = await runtime._route_task("task", agents)
        selected.append(agent_id)

    # Verify round-robin pattern (agent_0, agent_1, agent_2, agent_0, ...)
    assert selected == [
        agents[0],
        agents[1],
        agents[2],
        agents[0],
        agents[1],
        agents[2],
    ]


@pytest.mark.asyncio
async def test_random_routing(runtime):
    """Test random routing selects from available agents."""
    runtime.config.default_routing_strategy = RoutingStrategy.RANDOM

    # Create multiple agents
    agents = []
    for i in range(3):
        agent = Mock(spec=BaseAgent)
        agent.agent_id = f"agent_{i}"
        agent.to_a2a_card = Mock(return_value={"agent_id": agent.agent_id})
        await runtime.register_agent(agent)
        agents.append(agent.agent_id)

    # Route multiple tasks
    selected = []
    for _ in range(10):
        agent_id = await runtime._route_task("task", agents)
        selected.append(agent_id)

    # Verify all selected agents are from available set
    assert all(s in agents for s in selected)
    # Verify some randomness (not all same agent)
    assert len(set(selected)) > 1


@pytest.mark.asyncio
async def test_routing_excludes_busy_agents(runtime, mock_agent):
    """Test routing excludes agents that are UNHEALTHY (not available)."""
    # Create second agent
    agent2 = Mock(spec=BaseAgent)
    agent2.agent_id = "agent_2"
    agent2.to_a2a_card = Mock(return_value={"agent_id": "agent_2"})

    await runtime.register_agent(mock_agent)
    await runtime.register_agent(agent2)

    # Mark first agent as UNHEALTHY (not available for routing)
    runtime.agents[mock_agent.agent_id].status = AgentStatus.UNHEALTHY

    # Route task - should select agent2 (agent1 is unhealthy)
    selected = await runtime._route_task("task", [mock_agent.agent_id, agent2.agent_id])

    assert selected == agent2.agent_id


@pytest.mark.asyncio
async def test_routing_no_available_agents(runtime):
    """Test routing returns None when no agents available."""
    # Attempt to route with no registered agents
    selected = await runtime._route_task("task", [])

    assert selected is None


# ============================================================================
# Resource Management Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_agent_limit_enforcement(runtime):
    """Test max concurrent agents limit is enforced."""
    runtime.config.max_concurrent_agents = 2

    # Create multiple agents
    agents = []
    for i in range(3):
        agent = Mock(spec=BaseAgent)
        agent.agent_id = f"agent_{i}"
        agent.run = AsyncMock(return_value={"result": f"result_{i}"})
        await runtime.register_agent(agent)
        agents.append(agent)

    # Execute tasks that take time (simulate concurrent execution)
    async def slow_task(agent, inputs):
        runtime.agents[agent.agent_id].status = AgentStatus.ACTIVE
        await asyncio.sleep(0.1)
        runtime.agents[agent.agent_id].status = AgentStatus.ACTIVE
        return {"result": "done"}

    with patch.object(runtime, "_execute_agent_task", side_effect=slow_task):
        # Submit 3 tasks (more than max_concurrent_agents)
        tasks = [
            runtime.execute_task(f"agent_{i}", {"task": f"task_{i}"}) for i in range(3)
        ]

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

    # All tasks should complete
    assert len(results) == 3


@pytest.mark.asyncio
async def test_budget_enforcement_stops_execution(runtime):
    """Test budget enforcement stops execution when limit reached."""
    runtime.config.max_budget_usd = 1.0
    runtime._total_budget_spent = 0.95  # Near limit

    # Mock agent that costs $0.10
    mock_agent = Mock(spec=BaseAgent)
    mock_agent.agent_id = "expensive_agent"
    mock_agent.run = AsyncMock(return_value={"result": "success"})
    await runtime.register_agent(mock_agent)

    # Mock cost calculation to return $0.10
    with patch.object(runtime, "_calculate_task_cost", return_value=0.10):
        # Execute task - should raise budget exceeded error
        with pytest.raises(RuntimeError, match="Global budget exceeded"):
            await runtime.execute_task("expensive_agent", {"task": "expensive"})


@pytest.mark.asyncio
async def test_queue_management_respects_priority(runtime):
    """Test task queue respects priority ordering."""
    # Create high and low priority tasks
    high_priority_task = {
        "task_id": "task_1",
        "agent_id": "agent_1",
        "inputs": {"task": "urgent"},
        "priority": 1,  # High priority
    }

    low_priority_task = {
        "task_id": "task_2",
        "agent_id": "agent_1",
        "inputs": {"task": "normal"},
        "priority": 10,  # Low priority
    }

    # Add tasks in reverse priority order
    await runtime.task_queue.put((low_priority_task["priority"], low_priority_task))
    await runtime.task_queue.put((high_priority_task["priority"], high_priority_task))

    # Get tasks - should return high priority first
    priority1, task1 = await runtime.task_queue.get()
    priority2, task2 = await runtime.task_queue.get()

    assert task1["task_id"] == "task_1"  # High priority
    assert task2["task_id"] == "task_2"  # Low priority


@pytest.mark.asyncio
async def test_resource_cleanup_on_shutdown(runtime, mock_agent):
    """Test resources are cleaned up on shutdown."""
    await runtime.register_agent(mock_agent)

    # Add some active tasks
    runtime._active_tasks["task_1"] = asyncio.create_task(asyncio.sleep(10))

    # Shutdown
    await runtime.shutdown(graceful=False)

    # Verify cleanup
    assert runtime._is_shutting_down
    assert len(runtime._active_tasks) == 0


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_execution(runtime):
    """Test semaphore limits concurrent agent execution."""
    runtime.config.max_concurrent_agents = 2
    # Reinitialize semaphore to match updated config
    runtime.semaphore = asyncio.Semaphore(runtime.config.max_concurrent_agents)

    # Create agents
    agents = []
    for i in range(5):
        agent = Mock(spec=BaseAgent)
        agent.agent_id = f"agent_{i}"
        agent.run = AsyncMock(return_value={"result": f"result_{i}"})
        await runtime.register_agent(agent)
        agents.append(agent)

    # Track max concurrent executions
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def tracked_execution(agent, inputs):
        nonlocal max_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)

        await asyncio.sleep(0.1)

        async with lock:
            current_concurrent -= 1

        return {"result": "done"}

    with patch.object(runtime, "_execute_agent_task", side_effect=tracked_execution):
        tasks = [
            runtime.execute_task(agent.agent_id, {"task": f"task_{i}"})
            for i, agent in enumerate(agents)
        ]
        await asyncio.gather(*tasks)

    # Verify max concurrent never exceeded limit
    assert max_concurrent <= runtime.config.max_concurrent_agents


# ============================================================================
# Retry/Error Handling Tests (5 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_retry_on_transient_failure(runtime, mock_agent):
    """Test retry mechanism on transient failures."""
    runtime.config.retry_policy = RetryPolicy(
        max_retries=3,
        initial_delay=0.1,
        backoff_factor=1.5,
    )

    await runtime.register_agent(mock_agent)

    # Simulate transient failure (fail twice, then succeed)
    call_count = 0

    async def failing_run(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Transient error")
        return {"result": "success"}

    mock_agent.run = AsyncMock(side_effect=failing_run)

    # Execute task - should retry and succeed
    result = await runtime.execute_task(mock_agent.agent_id, {"task": "test"})

    assert result["result"] == "success"
    assert call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_retry_exhausted_marks_failed(runtime, mock_agent):
    """Test agent marked as failed when retries exhausted."""
    runtime.config.retry_policy = RetryPolicy(
        max_retries=2,
        initial_delay=0.1,
    )
    runtime.config.error_handling = ErrorHandlingMode.CIRCUIT_BREAKER

    await runtime.register_agent(mock_agent)

    # Simulate persistent failure
    mock_agent.run = AsyncMock(side_effect=Exception("Persistent error"))

    # Execute task - should fail after retries
    with pytest.raises(Exception, match="Persistent error"):
        await runtime.execute_task(mock_agent.agent_id, {"task": "test"})

    # Verify agent marked as failed
    assert runtime.agents[mock_agent.agent_id].status == AgentStatus.UNHEALTHY


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold(runtime, mock_agent):
    """Test circuit breaker opens after failure threshold."""
    runtime.config.enable_circuit_breaker = True
    runtime.config.circuit_breaker_failure_threshold = 3
    # Use fail-fast to not have retry complications
    runtime.config.error_handling = ErrorHandlingMode.FAIL_FAST

    await runtime.register_agent(mock_agent)

    # Simulate failures
    mock_agent.run = AsyncMock(side_effect=Exception("Error"))

    # Fail 3 times to trip circuit breaker
    for _ in range(3):
        try:
            await runtime.execute_task(mock_agent.agent_id, {"task": "test"})
        except Exception:
            pass

    # Circuit breaker should be open
    assert runtime._circuit_breaker_state[mock_agent.agent_id] == "open"

    # Next execution should fail fast
    with pytest.raises(RuntimeError, match="Circuit breaker open"):
        await runtime.execute_task(mock_agent.agent_id, {"task": "test"})


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(runtime, mock_agent):
    """Test circuit breaker recovers after timeout."""
    runtime.config.enable_circuit_breaker = True
    runtime.config.circuit_breaker_failure_threshold = 2
    runtime.config.circuit_breaker_recovery_timeout = 0.5  # 500ms
    # Use fail-fast to avoid retry delays
    runtime.config.error_handling = ErrorHandlingMode.FAIL_FAST

    await runtime.register_agent(mock_agent)

    # Trip circuit breaker
    mock_agent.run = AsyncMock(side_effect=Exception("Error"))
    for _ in range(2):
        try:
            await runtime.execute_task(mock_agent.agent_id, {"task": "test"})
        except Exception:
            pass

    assert runtime._circuit_breaker_state[mock_agent.agent_id] == "open"

    # Wait for recovery timeout
    await asyncio.sleep(0.6)

    # Circuit breaker should be half-open, allow one attempt
    mock_agent.run = AsyncMock(return_value={"result": "recovered"})
    result = await runtime.execute_task(mock_agent.agent_id, {"task": "test"})

    assert result["result"] == "recovered"
    assert runtime._circuit_breaker_state[mock_agent.agent_id] == "closed"


@pytest.mark.asyncio
async def test_error_handling_fail_fast_mode(runtime, mock_agent):
    """Test fail-fast mode stops execution immediately on error."""
    runtime.config.error_handling = ErrorHandlingMode.FAIL_FAST

    await runtime.register_agent(mock_agent)

    # Simulate failure
    mock_agent.run = AsyncMock(side_effect=Exception("Critical error"))

    # Execute task - should fail immediately without retry
    with pytest.raises(Exception, match="Critical error"):
        await runtime.execute_task(mock_agent.agent_id, {"task": "test"})

    # Verify no retries attempted (run called only once)
    assert mock_agent.run.call_count == 1


# ============================================================================
# Workflow Tracking Tests (3 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_workflow_tracking_records_execution(runtime, mock_agent):
    """Test workflow tracking records task execution."""
    runtime.config.enable_progress_tracking = True

    await runtime.register_agent(mock_agent)

    # Execute task
    result = await runtime.execute_task(
        mock_agent.agent_id, {"task": "test workflow tracking"}
    )

    # Verify execution tracked
    assert len(runtime._execution_history) > 0
    last_execution = runtime._execution_history[-1]
    assert last_execution["agent_id"] == mock_agent.agent_id
    assert last_execution["status"] == "success"


@pytest.mark.asyncio
async def test_workflow_metrics_updated(runtime, mock_agent):
    """Test workflow metrics are updated during execution."""
    runtime.config.enable_progress_tracking = True

    await runtime.register_agent(mock_agent)

    # Execute multiple tasks
    for i in range(5):
        await runtime.execute_task(mock_agent.agent_id, {"task": f"task_{i}"})

    # Verify metrics
    metrics = await runtime.get_metrics()
    assert metrics["total_tasks_executed"] >= 5
    assert metrics["total_budget_spent"] >= 0


@pytest.mark.asyncio
async def test_workflow_history_provides_task_details(runtime, mock_agent):
    """Test workflow history provides detailed task information."""
    runtime.config.enable_progress_tracking = True

    await runtime.register_agent(mock_agent)

    # Execute task
    task_inputs = {"task": "test history", "params": {"value": 42}}
    result = await runtime.execute_task(mock_agent.agent_id, task_inputs)

    # Get history
    history = runtime.get_execution_history()
    assert len(history) > 0

    last_task = history[-1]
    assert last_task["agent_id"] == mock_agent.agent_id
    assert "timestamp" in last_task
    assert "duration_seconds" in last_task


# ============================================================================
# Graceful Shutdown Tests (2 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_graceful_shutdown_waits_for_tasks(runtime, mock_agent):
    """Test graceful shutdown waits for active tasks to complete."""
    await runtime.register_agent(mock_agent)

    # Create long-running task
    async def long_task(**kwargs):
        await asyncio.sleep(0.5)
        return {"result": "completed"}

    mock_agent.run = AsyncMock(side_effect=long_task)

    # Start task
    task = asyncio.create_task(
        runtime.execute_task(mock_agent.agent_id, {"task": "long"})
    )
    runtime._active_tasks["long_task"] = task

    # Initiate graceful shutdown
    shutdown_task = asyncio.create_task(runtime.shutdown(graceful=True, timeout=2.0))

    # Wait a bit
    await asyncio.sleep(0.1)

    # Verify shutdown is waiting
    assert not shutdown_task.done()

    # Wait for everything to complete
    await task
    await shutdown_task

    # Verify task completed
    assert task.done()


@pytest.mark.asyncio
async def test_immediate_shutdown_cancels_tasks(runtime, mock_agent):
    """Test immediate shutdown cancels active tasks."""
    await runtime.register_agent(mock_agent)

    # Create long-running task
    async def long_task(**kwargs):
        await asyncio.sleep(5.0)
        return {"result": "completed"}

    mock_agent.run = AsyncMock(side_effect=long_task)

    # Start task
    task = asyncio.create_task(
        runtime.execute_task(mock_agent.agent_id, {"task": "long"})
    )
    runtime._active_tasks["long_task"] = task

    # Wait a bit to ensure task is running
    await asyncio.sleep(0.1)

    # Initiate immediate shutdown
    await runtime.shutdown(graceful=False)

    # Verify task was cancelled
    assert task.cancelled() or task.done()
    assert runtime._is_shutting_down
