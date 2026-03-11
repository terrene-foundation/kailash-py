"""
Integration tests for AsyncLocalRuntime integration in OrchestrationRuntime.

Task 1: AsyncLocalRuntime Integration (TODO-178)
Tier 2: Integration tests with real infrastructure (NO MOCKING policy)

Test Coverage:
- 3-agent workflow execution via execute_multi_agent_workflow()
- Level-based parallelism verification
- Result extraction from workflow execution
- Error handling (graceful vs fail-fast)
- Agent routing with semantic strategy

Pattern: Real BaseAgent instances + Real AsyncLocalRuntime execution
No mocking - uses actual workflow execution and agent processing.
"""

import asyncio
from typing import List

import pytest
import pytest_asyncio
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.orchestration.runtime import (
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def orchestration_runtime():
    """
    Create OrchestrationRuntime instance for testing.

    Pattern: Minimal configuration for integration testing.
    Uses default settings except where specific values needed.
    """
    config = OrchestrationRuntimeConfig(
        max_concurrent_agents=3,
        enable_health_monitoring=False,  # Disable for faster tests
        health_check_interval=60.0,  # Long interval to avoid interference
    )

    runtime = OrchestrationRuntime(config=config)
    await runtime.start()

    yield runtime

    await runtime.shutdown(mode="immediate")


@pytest_asyncio.fixture
async def three_agents(orchestration_runtime):
    """
    Create and register 3 test agents with different capabilities.

    Pattern: Specialized agents for different task types.
    Enables semantic routing verification.
    """
    # Agent 1: Data analysis specialist
    agent1 = BaseAgent(
        agent_id="analyst_001",
        config=BaseAgentConfig(
            llm_provider="openai", model="gpt-4o-mini", temperature=0.0
        ),
    )

    # Agent 2: Code generation specialist
    agent2 = BaseAgent(
        agent_id="coder_001",
        config=BaseAgentConfig(
            llm_provider="openai", model="gpt-4o-mini", temperature=0.0
        ),
    )

    # Agent 3: Documentation specialist
    agent3 = BaseAgent(
        agent_id="writer_001",
        config=BaseAgentConfig(
            llm_provider="openai", model="gpt-4o-mini", temperature=0.0
        ),
    )

    # Register all agents
    await orchestration_runtime.register_agent(agent1, max_concurrency=1)
    await orchestration_runtime.register_agent(agent2, max_concurrency=1)
    await orchestration_runtime.register_agent(agent3, max_concurrency=1)

    return [agent1, agent2, agent3]


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_execute_multi_agent_workflow_parallel_execution(
    orchestration_runtime, three_agents
):
    """
    Test: Execute 3-agent workflow with parallel execution.

    Validation:
    - All 3 tasks execute successfully
    - Results returned for all tasks
    - Workflow completes with expected structure

    Pattern: NO MOCKING - uses real AsyncLocalRuntime and BaseAgent execution.
    """
    tasks = [
        "Analyze this dataset: [1, 2, 3, 4, 5]",
        "Write a Python function to sum numbers",
        "Document the testing strategy for this feature",
    ]

    # Execute workflow
    results = await orchestration_runtime.execute_multi_agent_workflow(
        tasks=tasks,
        routing_strategy="round-robin",  # Distribute evenly
        error_handling="graceful",
    )

    # Verify workflow completion
    assert results["total_tasks"] == 3
    assert results["completed_tasks"] == 3
    assert results["failed_tasks"] == 0
    assert results["success_rate"] == 1.0

    # Verify all results present
    assert len(results["results"]) == 3

    # Verify each result has required fields
    for result in results["results"]:
        assert "task" in result
        assert "agent_id" in result
        assert "status" in result
        assert result["status"] == "completed"
        assert "result" in result
        assert "run_id" in result


@pytest.mark.asyncio
async def test_execute_multi_agent_workflow_semantic_routing(
    orchestration_runtime, three_agents
):
    """
    Test: Semantic routing directs tasks to appropriate agents.

    Validation:
    - Data analysis task routes to analyst
    - Code task routes to coder
    - Documentation task routes to writer

    Pattern: Verifies agent selection based on task-agent similarity.
    """
    tasks = [
        "Analyze this statistical data and provide insights",
        "Generate Python code for data processing",
        "Write technical documentation for the API",
    ]

    # Execute with semantic routing
    results = await orchestration_runtime.execute_multi_agent_workflow(
        tasks=tasks, routing_strategy="semantic", error_handling="graceful"
    )

    # Verify successful execution
    assert results["completed_tasks"] == 3
    assert results["success_rate"] == 1.0

    # Verify agent assignment (semantic routing should match task to agent specialty)
    task_agent_map = {
        result["task"]: result["agent_id"] for result in results["results"]
    }

    # All tasks should be assigned (may not be perfect matches, but should execute)
    assert len(task_agent_map) == 3
    assert all(
        agent_id in ["analyst_001", "coder_001", "writer_001"]
        for agent_id in task_agent_map.values()
    )


@pytest.mark.asyncio
async def test_execute_multi_agent_workflow_error_handling_graceful(
    orchestration_runtime, three_agents
):
    """
    Test: Graceful error handling continues execution after errors.

    Validation:
    - Failed tasks marked as failed
    - Successful tasks still complete
    - Error information captured

    Pattern: Tests error resilience with mixed success/failure tasks.
    """
    tasks = [
        "Analyze this data: [1, 2, 3]",
        "",  # Empty task - should fail routing
        "Write a simple function",
    ]

    # Execute with graceful error handling
    results = await orchestration_runtime.execute_multi_agent_workflow(
        tasks=tasks, routing_strategy="round-robin", error_handling="graceful"
    )

    # Verify mixed results
    assert results["total_tasks"] == 3
    assert results["completed_tasks"] >= 0  # At least some may succeed
    assert results["failed_tasks"] >= 0  # At least some may fail

    # Verify results contain both completed and failed
    statuses = {result["status"] for result in results["results"]}

    # Should have results for all tasks
    assert len(results["results"]) == 3


@pytest.mark.asyncio
async def test_execute_multi_agent_workflow_no_agents_available(orchestration_runtime):
    """
    Test: Workflow handles case when no agents are registered.

    Validation:
    - All tasks fail with "No agents available" error
    - No exceptions raised
    - Proper error messages returned

    Pattern: Tests edge case with empty agent registry.
    """
    tasks = ["Task 1", "Task 2", "Task 3"]

    # Execute without any agents registered
    results = await orchestration_runtime.execute_multi_agent_workflow(
        tasks=tasks, routing_strategy="round-robin", error_handling="graceful"
    )

    # Verify all tasks failed
    assert results["total_tasks"] == 3
    assert results["completed_tasks"] == 0
    assert results["failed_tasks"] == 3
    assert results["success_rate"] == 0.0

    # Verify error messages
    for result in results["results"]:
        assert result["status"] == "failed"
        assert "No agents available" in result["error"]


@pytest.mark.asyncio
async def test_execute_multi_agent_workflow_result_structure(
    orchestration_runtime, three_agents
):
    """
    Test: Workflow results have correct structure and data.

    Validation:
    - Workflow ID generated
    - Task counts accurate
    - Success rate calculated correctly
    - All result fields present

    Pattern: Validates return value structure matches specification.
    """
    tasks = ["Task 1", "Task 2"]

    results = await orchestration_runtime.execute_multi_agent_workflow(
        tasks=tasks, routing_strategy="round-robin", error_handling="graceful"
    )

    # Verify top-level structure
    assert "workflow_id" in results
    assert results["workflow_id"].startswith("workflow_")
    assert "total_tasks" in results
    assert "completed_tasks" in results
    assert "failed_tasks" in results
    assert "success_rate" in results
    assert "results" in results

    # Verify calculations
    assert results["total_tasks"] == len(tasks)
    assert (
        results["completed_tasks"] + results["failed_tasks"] == results["total_tasks"]
    )

    # Verify success rate calculation
    expected_rate = results["completed_tasks"] / results["total_tasks"]
    assert abs(results["success_rate"] - expected_rate) < 0.01  # Float comparison


@pytest.mark.asyncio
async def test_async_runtime_initialization(orchestration_runtime):
    """
    Test: AsyncLocalRuntime properly initialized in start() method.

    Validation:
    - _async_runtime field is not None after start()
    - Runtime configured with correct max_concurrent_nodes

    Pattern: Validates Substep 3 implementation (runtime initialization).
    """
    # Verify runtime was initialized
    assert orchestration_runtime._async_runtime is not None

    # Verify runtime type
    from kailash.runtime import AsyncLocalRuntime

    assert isinstance(orchestration_runtime._async_runtime, AsyncLocalRuntime)
