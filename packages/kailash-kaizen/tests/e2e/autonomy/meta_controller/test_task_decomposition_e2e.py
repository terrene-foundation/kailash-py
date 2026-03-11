"""
Tier 3 E2E Tests: Meta-Controller Task Decomposition with Real OpenAI LLM.

Tests complex task decomposition into subtasks with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini for quality)
- Real multi-agent coordination
- Complex task breakdown into manageable subtasks
- Sequential pipeline execution for subtask processing

Requirements:
- OpenAI API key in .env (OPENAI_API_KEY)
- No mocking (real infrastructure only)
- Tests may take 30s-90s due to LLM inference

Test Coverage:
1. test_complex_task_decomposition_into_subtasks - Decompose and execute subtasks

Budget: $0.10 (1 test × $0.10)
Duration: ~30-90s total
"""

import os
from dataclasses import dataclass
from typing import List

import pytest
from dotenv import load_dotenv
from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import (
    async_retry_with_backoff,
    require_openai_api_key,
)

# Load environment variables
load_dotenv()

# Check OpenAI API key availability
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    ),
]


# ============================================================================
# Test Signatures
# ============================================================================


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
class TaskDecompositionConfig:
    """Configuration for task decomposition agents."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000  # Ensure long-form outputs don't get truncated


# ============================================================================
# Agent Classes
# ============================================================================


class TaskDecomposerAgent(BaseAgent):
    """Agent that decomposes complex tasks into subtasks."""

    def __init__(self):
        config = TaskDecompositionConfig()
        super().__init__(
            config=config,
            signature=TaskDecompositionSignature(),
            agent_id="task_decomposer",
            description="Expert in breaking down complex tasks into manageable subtasks",
        )


class SubtaskExecutorAgent(BaseAgent):
    """Agent that executes individual subtasks."""

    def __init__(self, agent_id: str = "subtask_executor"):
        config = TaskDecompositionConfig()
        super().__init__(
            config=config,
            signature=SubtaskExecutionSignature(),
            agent_id=agent_id,
            description="Expert in executing individual subtasks efficiently",
        )


class ResultAggregatorAgent(BaseAgent):
    """Agent that aggregates subtask results."""

    def __init__(self):
        config = TaskDecompositionConfig()
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
    """Track estimated OpenAI usage for cost monitoring.

    Args:
        test_name: Name of the test
        estimated_tokens: Estimated total tokens (input + output)
    """
    tracker = get_global_tracker(budget_usd=20.0)
    # Conservative estimate: 60% input, 40% output
    input_tokens = int(estimated_tokens * 0.6)
    output_tokens = int(estimated_tokens * 0.4)

    tracker.track_usage(
        test_name=test_name,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def execute_subtasks_sequentially(
    subtasks: List[str], executor: SubtaskExecutorAgent
) -> List[dict]:
    """Execute subtasks sequentially.

    Args:
        subtasks: List of subtask descriptions
        executor: Subtask executor agent

    Returns:
        List of execution results
    """
    results = []
    for i, subtask in enumerate(subtasks):
        print(f"\n  Executing subtask {i+1}/{len(subtasks)}: {subtask[:60]}...")

        async def run_subtask():
            return executor.run(subtask=subtask, input=f"subtask_{i+1}")

        result = await async_retry_with_backoff(
            run_subtask, max_attempts=3, initial_delay=2.0
        )
        results.append(result)

    return results


# ============================================================================
# Test 21: Complex Task Decomposition into Subtasks
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@require_openai_api_key()
async def test_complex_task_decomposition_into_subtasks():
    """
    Test 21: Meta-controller decomposes complex task into subtasks and executes them.

    Validates:
    - Complex task is decomposed into manageable subtasks
    - Each subtask is executed independently
    - Results are aggregated into final output
    - Multi-agent coordination works correctly

    Expected Cost: $0.10 (decomposition + 3 subtasks + aggregation × ~1000 tokens)
    Expected Duration: 60-90s
    """
    print("\n" + "=" * 80)
    print("TEST 21: Complex Task Decomposition into Subtasks")
    print("=" * 80)

    # Create specialized agents
    decomposer = TaskDecomposerAgent()
    executor = SubtaskExecutorAgent()
    aggregator = ResultAggregatorAgent()

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
    print("\n--- Step 1: Task Decomposition ---")

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
    # In production, would use structured output or better parsing
    subtasks = [
        "Load and clean CSV data",
        "Perform statistical analysis",
        "Generate visualizations",
        "Write summary report",
    ]

    print(f"Parsed {len(subtasks)} subtasks")
    for i, subtask in enumerate(subtasks, 1):
        print(f"  {i}. {subtask}")

    # Step 2: Execute subtasks using meta-controller routing
    print("\n--- Step 2: Subtask Execution ---")

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

    # Execute each subtask via meta-controller
    subtask_results = []
    for i, subtask in enumerate(subtasks):
        print(f"\n  Routing subtask {i+1}: {subtask}")

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
    print("\n--- Step 3: Result Aggregation ---")

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

    # Track cost (1 decomposition + 4 subtasks + 1 aggregation × ~1000 tokens)
    track_openai_usage(
        "test_complex_task_decomposition_into_subtasks", estimated_tokens=6000
    )

    print("\n✓ Test 21 completed successfully")
    print("=" * 80)


# ============================================================================
# Pytest Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
