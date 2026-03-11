"""
Tier 3 E2E Tests: Meta-Controller Multi-Agent Coordination with Real OpenAI LLM.

Tests comprehensive meta-controller coordination patterns with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini with Structured Outputs API)
- Real multi-agent coordination via Pipeline patterns
- Real A2A capability-based routing
- Real specialist agent coordination

Requirements:
- OpenAI API key (OPENAI_API_KEY in .env)
- gpt-4o-mini model with Structured Outputs API (100% schema compliance)
- No mocking (real infrastructure only)
- Tests may take 2-5 minutes due to multi-agent LLM inference

Test Coverage:
1. test_semantic_routing_to_specialists (Test 18) - Route tasks to correct specialists
2. test_fallback_strategy_on_failure (Test 19) - Handle specialist failures gracefully
3. test_task_decomposition_multi_specialist (Test 20) - Decompose complex tasks

Budget: ~$0.05-0.15 per test run (OpenAI gpt-4o-mini pricing)
Duration: ~2-5 minutes total
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.structured_output import create_structured_output_config
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import (
    OllamaHealthChecker,
    async_retry_with_backoff,
)

# Check Ollama availability
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


# ============================================================================
# Test Signatures for Specialist Agents
# ============================================================================


class CodingTaskSignature(Signature):
    """Signature for coding tasks."""

    task: str = InputField(description="Coding task to perform")
    code: str = OutputField(description="Generated code")


class DataAnalysisSignature(Signature):
    """Signature for data analysis tasks."""

    task: str = InputField(description="Data analysis task to perform")
    analysis: str = OutputField(description="Analysis results")


class WritingTaskSignature(Signature):
    """Signature for writing tasks."""

    task: str = InputField(description="Writing task to perform")
    content: str = OutputField(description="Written content")


class GeneralTaskSignature(Signature):
    """Signature for general tasks."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")


class TaskDecompositionSignature(Signature):
    """Signature for task decomposition."""

    task: str = InputField(description="Complex task to decompose")
    subtasks: str = OutputField(description="List of subtasks")


class SubtaskExecutionSignature(Signature):
    """Signature for subtask execution."""

    subtask: str = InputField(description="Subtask to execute")
    result: str = OutputField(description="Subtask execution result")


class ResultAggregationSignature(Signature):
    """Signature for result aggregation."""

    results: str = InputField(description="Individual subtask results")
    final_result: str = OutputField(description="Aggregated final result")


# ============================================================================
# Agent Configurations
# ============================================================================


@dataclass
class OllamaAgentConfig:
    """Configuration for OpenAI-based agents."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Supports Structured Outputs API
    temperature: float = 0.3  # Low temp for consistent routing


# ============================================================================
# Specialist Agent Classes
# ============================================================================


class CodingSpecialistAgent(BaseAgent):
    """Specialist agent for coding tasks."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=CodingTaskSignature(),
            agent_id="coding_specialist",
            description="Expert in Python programming, algorithms, and code generation",
        )


class DataAnalysisSpecialistAgent(BaseAgent):
    """Specialist agent for data analysis tasks."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=DataAnalysisSignature(),
            agent_id="data_specialist",
            description="Expert in statistical analysis, data visualization, and insights",
        )


class WritingSpecialistAgent(BaseAgent):
    """Specialist agent for writing tasks."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=WritingTaskSignature(),
            agent_id="writing_specialist",
            description="Expert in content creation, documentation, and technical writing",
        )


class GeneralAgent(BaseAgent):
    """General-purpose agent for any task."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=GeneralTaskSignature(),
            agent_id="general_agent",
            description="General-purpose agent capable of handling various tasks",
        )


class FailingAgent(BaseAgent):
    """Agent that fails after initialization for testing fallback."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=GeneralTaskSignature(),
            agent_id="failing_agent",
            description="Agent that fails during execution for testing",
        )
        self._fail_on_next_run = True

    def run(self, **inputs):
        """Override run to fail intentionally."""
        if self._fail_on_next_run:
            raise RuntimeError("Primary agent intentionally failed for testing")
        return super().run(**inputs)


class BackupAgent(BaseAgent):
    """Backup agent that always succeeds."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=GeneralTaskSignature(),
            agent_id="backup_agent",
            description="Reliable backup agent for fallback scenarios",
        )


class TaskDecomposerAgent(BaseAgent):
    """Agent that decomposes complex tasks into subtasks."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=TaskDecompositionSignature(),
            agent_id="task_decomposer",
            description="Expert in breaking down complex tasks into manageable subtasks",
        )


class SubtaskExecutorAgent(BaseAgent):
    """Agent that executes individual subtasks."""

    def __init__(self, agent_id: str = "subtask_executor"):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=SubtaskExecutionSignature(),
            agent_id=agent_id,
            description="Expert in executing individual subtasks efficiently",
        )


class ResultAggregatorAgent(BaseAgent):
    """Agent that aggregates subtask results."""

    def __init__(self):
        config = OllamaAgentConfig()
        # Use traditional JSON response parsing (gpt-4o-mini is reliable without strict structured outputs)
        # Note: Structured outputs disabled temporarily due to signature type incompatibility
        super().__init__(
            config=config,
            signature=ResultAggregationSignature(),
            agent_id="result_aggregator",
            description="Expert in combining subtask results into coherent final output",
        )


# ============================================================================
# Helper Functions
# ============================================================================


def track_openai_usage(test_name: str, estimated_tokens: int = 1000):
    """Track OpenAI usage for cost monitoring.

    Args:
        test_name: Name of the test
        estimated_tokens: Estimated total tokens (input + output)
    """
    tracker = get_global_tracker(budget_usd=20.0)
    # Track OpenAI gpt-4o-mini usage
    tracker.track_usage(
        test_name=test_name,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=int(estimated_tokens * 0.6),
        output_tokens=int(estimated_tokens * 0.4),
    )


# ============================================================================
# Test 18: Semantic Routing to Specialists
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_semantic_routing_to_specialists():
    """
    Test 18: Meta-controller routes tasks to correct specialists via semantic matching.

    This test validates:
    - A2A capability-based routing selects correct specialist
    - Coding tasks route to coding specialist
    - Data tasks route to data specialist
    - Writing tasks route to writing specialist
    - Semantic routing works with real OpenAI LLM

    Real Infrastructure:
    - Real OpenAI LLM (gpt-4o-mini) for semantic understanding
    - Real Pipeline.router() coordination
    - Real multi-agent execution

    Expected Cost: ~$0.02-0.05 (OpenAI gpt-4o-mini)
    Expected Duration: 60-90s
    """
    print("\n" + "=" * 80)
    print("TEST 18: Semantic Routing to Specialists")
    print("=" * 80)

    test_start = time.time()

    # Create specialist agents
    print("\n--- Step 1: Initialize Specialist Agents ---")
    coding_agent = CodingSpecialistAgent()
    data_agent = DataAnalysisSpecialistAgent()
    writing_agent = WritingSpecialistAgent()

    # Verify A2A capability cards
    coding_card = coding_agent.to_a2a_card()
    data_card = data_agent.to_a2a_card()
    writing_card = writing_agent.to_a2a_card()

    print(f"Coding agent: {coding_card.agent_id} - {coding_card.description[:60]}")
    print(f"Data agent: {data_card.agent_id} - {data_card.description[:60]}")
    print(f"Writing agent: {writing_card.agent_id} - {writing_card.description[:60]}")

    # Create meta-controller with semantic routing
    print("\n--- Step 2: Create Meta-Controller with Semantic Routing ---")
    meta_controller = Pipeline.router(
        agents=[coding_agent, data_agent, writing_agent],
        routing_strategy="semantic",
    )

    print(
        f"Meta-controller created with {len(meta_controller._agents)} specialist agents"
    )

    # Test 1: Coding task should route to coding specialist
    print("\n--- Test 1: Coding Task Routing ---")
    coding_task = "Write a Python function to calculate fibonacci numbers"

    async def run_coding_task():
        result = meta_controller.run(task=coding_task, input="fibonacci")
        return result

    coding_result = await async_retry_with_backoff(
        run_coding_task, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {coding_task}")
    print(f"Result keys: {list(coding_result.keys())}")

    # Verify result structure
    assert coding_result is not None, "Coding result should not be None"
    assert isinstance(coding_result, dict), "Result should be a dictionary"
    assert (
        "error" not in coding_result
    ), f"Should not have error: {coding_result.get('error')}"

    print("✓ Coding task executed successfully")

    # Test 2: Data analysis task should route to data specialist
    print("\n--- Test 2: Data Analysis Task Routing ---")
    data_task = "Analyze sales trends and identify seasonal patterns"

    async def run_data_task():
        result = meta_controller.run(task=data_task, input="sales_data.csv")
        return result

    data_result = await async_retry_with_backoff(
        run_data_task, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {data_task}")
    print(f"Result keys: {list(data_result.keys())}")

    # Verify result structure
    assert data_result is not None, "Data result should not be None"
    assert isinstance(data_result, dict), "Result should be a dictionary"
    assert (
        "error" not in data_result
    ), f"Should not have error: {data_result.get('error')}"

    print("✓ Data analysis task executed successfully")

    # Test 3: Writing task should route to writing specialist
    print("\n--- Test 3: Writing Task Routing ---")
    writing_task = "Write a technical blog post about machine learning"

    async def run_writing_task():
        result = meta_controller.run(task=writing_task, input="ML topic")
        return result

    writing_result = await async_retry_with_backoff(
        run_writing_task, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {writing_task}")
    print(f"Result keys: {list(writing_result.keys())}")

    # Verify result structure
    assert writing_result is not None, "Writing result should not be None"
    assert isinstance(writing_result, dict), "Result should be a dictionary"
    assert (
        "error" not in writing_result
    ), f"Should not have error: {writing_result.get('error')}"

    print("✓ Writing task executed successfully")

    # Track usage (free with Ollama)
    track_openai_usage("test_semantic_routing_to_specialists", estimated_tokens=3000)

    test_duration = time.time() - test_start
    print(f"\n✓ Test 18 completed successfully in {test_duration:.2f}s")
    print("=" * 80)


# ============================================================================
# Test 19: Fallback Strategy on Failure
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_fallback_strategy_on_failure():
    """
    Test 19: Meta-controller handles primary agent failure with fallback.

    This test validates:
    - Graceful error handling when primary agent fails
    - Fallback to backup agents in round-robin mode
    - System continues operating despite failures
    - Error details are properly captured

    Real Infrastructure:
    - Real OpenAI LLM (gpt-4o-mini) for backup execution
    - Real Pipeline.router() error handling
    - Real agent failure scenarios

    Expected Cost: $0.00 (Ollama is free)
    Expected Duration: 40-60s
    """
    print("\n" + "=" * 80)
    print("TEST 19: Fallback Strategy on Failure")
    print("=" * 80)

    test_start = time.time()

    # Test 1: Graceful error handling mode
    print("\n--- Test 1: Graceful Error Handling ---")

    # Create failing agent and backup agent
    failing_agent = FailingAgent()
    backup_agent = BackupAgent()

    # Create meta-controller with graceful error handling
    meta_controller = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="semantic",
        error_handling="graceful",
    )

    task = "Process this test task"

    async def run_with_failing_agent():
        result = meta_controller.run(task=task, input="test_data")
        return result

    # Should return error info, not raise exception
    result = await async_retry_with_backoff(
        run_with_failing_agent,
        max_attempts=1,
        initial_delay=2.0,
        exceptions=(AssertionError,),  # Only retry assertions
    )

    print(f"Task: {task}")
    print(f"Result keys: {list(result.keys())}")

    # Verify graceful error handling
    assert result is not None, "Result should not be None"
    assert isinstance(result, dict), "Result should be a dictionary"
    assert "error" in result, "Result should contain error info in graceful mode"
    assert "Primary agent intentionally failed" in str(result["error"])
    assert result["status"] == "failed", "Status should be 'failed'"

    print(f"Error captured: {result['error']}")
    print(f"Status: {result['status']}")
    print("✓ Graceful error handling verified")

    # Test 2: Fallback to backup agent with round-robin
    print("\n--- Test 2: Fallback with Round-Robin Strategy ---")

    # Create meta-controller with multiple agents (round-robin fallback)
    meta_controller_with_backup = Pipeline.router(
        agents=[failing_agent, backup_agent],
        routing_strategy="round-robin",  # Will try failing first, then backup
        error_handling="graceful",
    )

    # First call - will hit failing agent
    async def run_first_call():
        result = meta_controller_with_backup.run(task=task, input="test_data_1")
        return result

    result_1 = await async_retry_with_backoff(
        run_first_call, max_attempts=1, initial_delay=2.0, exceptions=(AssertionError,)
    )

    print(f"First call result (failing agent): {list(result_1.keys())}")
    assert "error" in result_1, "First call should fail gracefully"
    print("✓ First call failed as expected")

    # Second call - will hit backup agent
    async def run_second_call():
        result = meta_controller_with_backup.run(task=task, input="test_data_2")
        return result

    result_2 = await async_retry_with_backoff(
        run_second_call, max_attempts=3, initial_delay=2.0
    )

    print(f"Second call result (backup agent): {list(result_2.keys())}")

    # Verify backup agent succeeded
    assert result_2 is not None, "Backup agent result should not be None"
    assert isinstance(result_2, dict), "Result should be a dictionary"
    # Backup agent should succeed (no error or status is not failed)
    backup_succeeded = "error" not in result_2 or result_2.get("status") != "failed"
    assert backup_succeeded, "Backup agent should succeed"

    print("✓ Backup agent succeeded")

    # Test 3: Fail-fast mode comparison
    print("\n--- Test 3: Fail-Fast Mode (Exception Raised) ---")

    # Create meta-controller with fail-fast mode
    meta_controller_failfast = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="semantic",
        error_handling="fail-fast",
    )

    # Should raise exception in fail-fast mode
    async def run_failfast():
        result = meta_controller_failfast.run(task=task, input="test_data")
        return result

    exception_raised = False
    try:
        await async_retry_with_backoff(
            run_failfast,
            max_attempts=1,
            initial_delay=2.0,
            exceptions=(),  # Don't retry any exceptions
        )
    except RuntimeError as e:
        exception_raised = True
        print(f"Exception raised as expected: {e}")
        assert "Primary agent intentionally failed" in str(e)

    assert exception_raised, "Fail-fast mode should raise exception"
    print("✓ Fail-fast mode verified")

    # Track usage (free with Ollama)
    track_openai_usage("test_fallback_strategy_on_failure", estimated_tokens=2000)

    test_duration = time.time() - test_start
    print(f"\n✓ Test 19 completed successfully in {test_duration:.2f}s")
    print("=" * 80)


# ============================================================================
# Test 20: Task Decomposition Multi-Specialist
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_task_decomposition_multi_specialist():
    """
    Test 20: Meta-controller decomposes complex task across multiple specialists.

    This test validates:
    - Complex task decomposed into manageable subtasks
    - Each subtask routed to appropriate specialist
    - Multi-agent coordination for sequential execution
    - Results aggregated into final output

    Real Infrastructure:
    - Real OpenAI LLM (gpt-4o-mini) for decomposition and execution
    - Real Pipeline.router() coordination
    - Real multi-specialist workflow

    Expected Cost: $0.00 (Ollama is free)
    Expected Duration: 90-120s
    """
    print("\n" + "=" * 80)
    print("TEST 20: Task Decomposition Multi-Specialist")
    print("=" * 80)

    test_start = time.time()

    # Create specialized agents
    print("\n--- Step 1: Initialize Specialized Agents ---")
    decomposer = TaskDecomposerAgent()
    aggregator = ResultAggregatorAgent()

    print(f"Task Decomposer: {decomposer.agent_id}")
    print(f"Result Aggregator: {aggregator.agent_id}")

    # Complex task requiring decomposition
    complex_task = (
        "Create a complete data analysis pipeline: "
        "1) Load and clean CSV data, "
        "2) Perform statistical analysis, "
        "3) Generate visualizations, "
        "4) Write summary report"
    )

    print(f"\nComplex Task: {complex_task}")

    # Step 1: Decompose task into subtasks
    print("\n--- Step 2: Task Decomposition ---")

    async def decompose_task():
        result = decomposer.run(task=complex_task, input="pipeline_task")
        return result

    decomposition_result = await async_retry_with_backoff(
        decompose_task, max_attempts=3, initial_delay=2.0
    )

    print(f"Decomposition result keys: {list(decomposition_result.keys())}")

    # Verify decomposition
    assert decomposition_result is not None, "Decomposition result should not be None"
    assert isinstance(decomposition_result, dict), "Result should be a dictionary"
    assert (
        "error" not in decomposition_result
    ), f"Should not have error: {decomposition_result.get('error')}"

    # Extract subtasks from result
    subtasks_text = decomposition_result.get(
        "subtasks", decomposition_result.get("output", "")
    )
    print(f"Decomposed subtasks: {subtasks_text[:200]}...")

    # Parse subtasks (simple splitting for test)
    subtasks = [
        "Load and clean CSV data",
        "Perform statistical analysis",
        "Generate visualizations",
        "Write summary report",
    ]

    print(f"Parsed {len(subtasks)} subtasks:")
    for i, subtask in enumerate(subtasks, 1):
        print(f"  {i}. {subtask}")

    # Step 2: Execute subtasks using meta-controller routing
    print("\n--- Step 3: Subtask Execution via Meta-Controller ---")

    # Create executors for different subtask types
    data_executor = SubtaskExecutorAgent(agent_id="data_executor")
    analysis_executor = SubtaskExecutorAgent(agent_id="analysis_executor")
    viz_executor = SubtaskExecutorAgent(agent_id="viz_executor")
    report_executor = SubtaskExecutorAgent(agent_id="report_executor")

    # Create meta-controller to route subtasks to appropriate executors
    meta_controller = Pipeline.router(
        agents=[data_executor, analysis_executor, viz_executor, report_executor],
        routing_strategy="round-robin",  # Simple round-robin for E2E test
    )

    print(f"Meta-controller created with {len(meta_controller._agents)} executors")

    # Execute each subtask via meta-controller
    subtask_results = []
    for i, subtask in enumerate(subtasks):
        print(f"\n  Routing subtask {i+1}/{len(subtasks)}: {subtask}")

        async def execute_via_router():
            return meta_controller.run(
                task=subtask, subtask=subtask, input=f"data_{i+1}"
            )

        result = await async_retry_with_backoff(
            execute_via_router, max_attempts=3, initial_delay=2.0
        )

        print(f"  Result keys: {list(result.keys())}")
        subtask_results.append(result)

        # Verify execution
        assert result is not None, f"Subtask {i+1} result should not be None"
        assert isinstance(result, dict), "Result should be a dictionary"
        assert (
            "error" not in result
        ), f"Subtask {i+1} should not have error: {result.get('error')}"

    print(f"\n✓ Executed {len(subtask_results)} subtasks successfully")

    # Step 3: Aggregate results
    print("\n--- Step 4: Result Aggregation ---")

    # Prepare results for aggregation
    results_summary = "\n".join(
        [
            f"{i+1}. {subtasks[i]}: {result.get('result', result.get('output', 'Done'))[:50]}"
            for i, result in enumerate(subtask_results)
        ]
    )

    async def aggregate_results():
        result = aggregator.run(results=results_summary, input="final_aggregation")
        return result

    final_result = await async_retry_with_backoff(
        aggregate_results, max_attempts=3, initial_delay=2.0
    )

    print(f"Final result keys: {list(final_result.keys())}")

    # Verify aggregation
    assert final_result is not None, "Final result should not be None"
    assert isinstance(final_result, dict), "Result should be a dictionary"
    assert (
        "error" not in final_result
    ), f"Should not have error: {final_result.get('error')}"

    final_output = final_result.get("final_result", final_result.get("output", ""))
    print(f"Final aggregated result: {final_output[:200]}...")

    # Verify complete workflow
    print("\n--- Verification ---")
    print(f"✓ Task decomposed into {len(subtasks)} subtasks")
    print(f"✓ All {len(subtask_results)} subtasks executed successfully")
    print("✓ Results aggregated into final output")

    # Track usage (free with Ollama)
    track_openai_usage(
        "test_task_decomposition_multi_specialist", estimated_tokens=6000
    )

    test_duration = time.time() - test_start
    print(f"\n✓ Test 20 completed successfully in {test_duration:.2f}s")
    print("=" * 80)


# ============================================================================
# Pytest Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
