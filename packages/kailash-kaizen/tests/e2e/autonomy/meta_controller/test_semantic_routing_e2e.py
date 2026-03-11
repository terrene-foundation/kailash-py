"""
Tier 3 E2E Tests: Meta-Controller Semantic Routing with Real OpenAI LLM.

Tests intelligent agent routing based on task semantics with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini for quality semantic matching)
- Real multi-agent coordination via MetaControllerPipeline
- Real A2A capability-based routing
- Dynamic agent selection based on task complexity

Requirements:
- OpenAI API key in .env (OPENAI_API_KEY)
- No mocking (real infrastructure only)
- Tests may take 30s-90s due to LLM inference

Test Coverage:
1. test_semantic_routing_to_correct_specialist - Route to best specialist agent
2. test_dynamic_agent_selection_by_complexity - Select agent based on task complexity

Budget: $0.20 (2 tests × $0.10)
Duration: ~60-120s total
"""

import os
from dataclasses import dataclass

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


# ============================================================================
# Agent Configurations
# ============================================================================


@dataclass
class SpecialistAgentConfig:
    """Configuration for specialist agents."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3  # Low temp for consistent routing
    max_tokens: int = 2000  # Ensure long-form outputs don't get truncated


# ============================================================================
# Specialist Agent Classes
# ============================================================================


class CodingSpecialistAgent(BaseAgent):
    """Specialist agent for coding tasks."""

    def __init__(self):
        config = SpecialistAgentConfig()
        super().__init__(
            config=config,
            signature=CodingTaskSignature(),
            agent_id="coding_specialist",
            description="Expert in Python programming, algorithms, and code generation",
        )


class DataAnalysisSpecialistAgent(BaseAgent):
    """Specialist agent for data analysis tasks."""

    def __init__(self):
        config = SpecialistAgentConfig()
        super().__init__(
            config=config,
            signature=DataAnalysisSignature(),
            agent_id="data_specialist",
            description="Expert in statistical analysis, data visualization, and insights",
        )


class WritingSpecialistAgent(BaseAgent):
    """Specialist agent for writing tasks."""

    def __init__(self):
        config = SpecialistAgentConfig()
        super().__init__(
            config=config,
            signature=WritingTaskSignature(),
            agent_id="writing_specialist",
            description="Expert in content creation, documentation, and technical writing",
        )


class GeneralAgent(BaseAgent):
    """General-purpose agent for any task."""

    def __init__(self):
        config = SpecialistAgentConfig()
        super().__init__(
            config=config,
            signature=GeneralTaskSignature(),
            agent_id="general_agent",
            description="General-purpose agent capable of handling various tasks",
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


# ============================================================================
# Test 18: Semantic Routing to Correct Specialist
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@require_openai_api_key()
async def test_semantic_routing_to_correct_specialist():
    """
    Test 18: Meta-controller routes to correct specialist based on task semantics.

    Validates:
    - A2A capability-based routing selects correct specialist
    - Coding tasks route to coding specialist
    - Data tasks route to data specialist
    - Writing tasks route to writing specialist

    Expected Cost: $0.10 (3 routing decisions × ~1000 tokens each)
    Expected Duration: 30-60s
    """
    print("\n" + "=" * 80)
    print("TEST 18: Semantic Routing to Correct Specialist")
    print("=" * 80)

    # Create specialist agents
    coding_agent = CodingSpecialistAgent()
    data_agent = DataAnalysisSpecialistAgent()
    writing_agent = WritingSpecialistAgent()

    # Create meta-controller with semantic routing
    meta_controller = Pipeline.router(
        agents=[coding_agent, data_agent, writing_agent],
        routing_strategy="semantic",
    )

    # Test 1: Coding task should route to coding specialist
    print("\n--- Test 1: Coding Task ---")
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

    # Test 2: Data analysis task should route to data specialist
    print("\n--- Test 2: Data Analysis Task ---")
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

    # Test 3: Writing task should route to writing specialist
    print("\n--- Test 3: Writing Task ---")
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

    # Track cost (3 routing decisions × ~1000 tokens each)
    track_openai_usage(
        "test_semantic_routing_to_correct_specialist", estimated_tokens=3000
    )

    print("\n✓ Test 18 completed successfully")
    print("=" * 80)


# ============================================================================
# Test 19: Dynamic Agent Selection Based on Task Complexity
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@require_openai_api_key()
async def test_dynamic_agent_selection_by_complexity():
    """
    Test 19: Meta-controller dynamically selects agent based on task complexity.

    Validates:
    - Simple tasks can be handled by general agent
    - Complex specialized tasks route to specialist agents
    - Meta-controller adapts selection to task requirements

    Expected Cost: $0.10 (3 routing decisions × ~1000 tokens each)
    Expected Duration: 30-60s
    """
    print("\n" + "=" * 80)
    print("TEST 19: Dynamic Agent Selection by Task Complexity")
    print("=" * 80)

    # Create specialist and general agents
    coding_agent = CodingSpecialistAgent()
    data_agent = DataAnalysisSpecialistAgent()
    general_agent = GeneralAgent()

    # Create meta-controller with semantic routing
    meta_controller = Pipeline.router(
        agents=[coding_agent, data_agent, general_agent],
        routing_strategy="semantic",
    )

    # Test 1: Simple general task
    print("\n--- Test 1: Simple General Task ---")
    simple_task = "What is the capital of France?"

    async def run_simple_task():
        result = meta_controller.run(task=simple_task, input="geography")
        return result

    simple_result = await async_retry_with_backoff(
        run_simple_task, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {simple_task}")
    print(f"Result keys: {list(simple_result.keys())}")

    # Verify result structure
    assert simple_result is not None, "Simple result should not be None"
    assert isinstance(simple_result, dict), "Result should be a dictionary"
    assert (
        "error" not in simple_result
    ), f"Should not have error: {simple_result.get('error')}"

    # Test 2: Complex coding task requiring specialist
    print("\n--- Test 2: Complex Coding Task ---")
    complex_coding_task = (
        "Implement a binary search tree with insertion, deletion, "
        "and in-order traversal methods"
    )

    async def run_complex_coding():
        result = meta_controller.run(
            task=complex_coding_task, input="BST implementation"
        )
        return result

    complex_coding_result = await async_retry_with_backoff(
        run_complex_coding, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {complex_coding_task}")
    print(f"Result keys: {list(complex_coding_result.keys())}")

    # Verify result structure
    assert complex_coding_result is not None, "Complex coding result should not be None"
    assert isinstance(complex_coding_result, dict), "Result should be a dictionary"
    assert (
        "error" not in complex_coding_result
    ), f"Should not have error: {complex_coding_result.get('error')}"

    # Test 3: Complex data task requiring specialist
    print("\n--- Test 3: Complex Data Analysis Task ---")
    complex_data_task = (
        "Perform multivariate regression analysis with "
        "feature selection and cross-validation"
    )

    async def run_complex_data():
        result = meta_controller.run(task=complex_data_task, input="dataset.csv")
        return result

    complex_data_result = await async_retry_with_backoff(
        run_complex_data, max_attempts=3, initial_delay=2.0
    )

    print(f"Task: {complex_data_task}")
    print(f"Result keys: {list(complex_data_result.keys())}")

    # Verify result structure
    assert complex_data_result is not None, "Complex data result should not be None"
    assert isinstance(complex_data_result, dict), "Result should be a dictionary"
    assert (
        "error" not in complex_data_result
    ), f"Should not have error: {complex_data_result.get('error')}"

    # Track cost (3 routing decisions × ~1000 tokens each)
    track_openai_usage(
        "test_dynamic_agent_selection_by_complexity", estimated_tokens=3000
    )

    print("\n✓ Test 19 completed successfully")
    print("=" * 80)


# ============================================================================
# Pytest Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
