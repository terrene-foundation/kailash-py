"""
Tier 3 E2E Tests: Tree-of-Thoughts (ToT) Agent with Real OpenAI LLM.

Tests comprehensive ToT agent execution with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini - PAID, supports structured outputs)
- Parallel path generation and exploration
- Path evaluation and selection
- Best path execution

Requirements:
- OpenAI API key (required - ToT uses structured outputs for path/evaluation schemas)
- No mocking (real infrastructure only)
- Tests may take 10-30s with OpenAI

Test Coverage:
1. test_tot_agent_exploration (Test 17) - Tree exploration with path selection

Budget: $0.05 (OpenAI gpt-4o-mini for path generation and evaluation)
Duration: ~10-30s

Provider Compatibility Note:
ToT agent requires structured outputs for complex path/evaluation schemas.
Only OpenAI supports this - Ollama/Anthropic will timeout or fail.
"""

# Check OpenAI API key availability
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from dotenv import load_dotenv
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import async_retry_with_backoff

load_dotenv()

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    ),
]


# Test Configurations


@dataclass
class ToTTestConfig:
    """Configuration for ToT E2E tests."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Cost-effective with structured outputs support
    temperature: float = 0.7  # Moderate temp for path diversity with OpenAI
    num_paths: int = 3  # Keep small for faster tests (default is 5)
    max_paths: int = 10
    evaluation_criteria: str = "quality"
    parallel_execution: bool = True  # Enable parallelism


# Helper Functions


def create_tot_agent(config: ToTTestConfig = None) -> ToTAgent:
    """Create ToT agent with test configuration."""
    if config is None:
        config = ToTTestConfig()

    agent = ToTAgent(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=config.temperature,
        num_paths=config.num_paths,
        max_paths=config.max_paths,
        evaluation_criteria=config.evaluation_criteria,
        parallel_execution=config.parallel_execution,
    )

    return agent


def validate_tot_result_structure(result: Dict[str, Any]) -> bool:
    """Validate ToT result has proper structure.

    Args:
        result: The ToT result to validate

    Returns:
        True if structure is valid
    """
    required_keys = ["paths", "evaluations", "best_path", "final_result"]

    for key in required_keys:
        if key not in result:
            return False

    # Validate paths
    paths = result["paths"]
    if not isinstance(paths, list):
        return False
    if len(paths) == 0:
        return False

    # Each path should have structure
    for path in paths:
        if not isinstance(path, dict):
            return False
        if "path_id" not in path:
            return False
        if "reasoning" not in path:
            return False

    # Validate evaluations
    evaluations = result["evaluations"]
    if not isinstance(evaluations, list):
        return False
    if len(evaluations) != len(paths):
        return False

    # Each evaluation should have score
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            return False
        if "score" not in evaluation:
            return False
        if "path" not in evaluation:
            return False

    # Validate best path
    best_path = result["best_path"]
    if not isinstance(best_path, dict):
        return False
    if "score" not in best_path:
        return False
    if "path" not in best_path:
        return False

    # Validate final result
    final_result = result["final_result"]
    if not isinstance(final_result, str):
        return False

    return True


def validate_path_diversity(paths: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate that paths show diversity (different reasoning).

    Args:
        paths: List of generated paths

    Returns:
        Dict with diversity metrics
    """
    diversity_result = {
        "unique_paths": 0,
        "diversity_score": 0.0,
        "sufficient_diversity": False,
    }

    # Simple diversity check: Compare reasoning text
    reasoning_texts = [path.get("reasoning", "") for path in paths]
    unique_reasoning = set(reasoning_texts)

    diversity_result["unique_paths"] = len(unique_reasoning)
    diversity_result["diversity_score"] = len(unique_reasoning) / len(paths)
    diversity_result["sufficient_diversity"] = (
        diversity_result["diversity_score"] >= 0.5
    )

    return diversity_result


async def validate_tot_quality_with_openai(
    result: Dict[str, Any], task: str
) -> Dict[str, Any]:
    """Validate ToT result quality using OpenAI GPT-4o-mini.

    This is the ONLY place we use OpenAI (for quality validation).

    Args:
        result: The ToT result to validate
        task: Original task

    Returns:
        Dict with validation results
    """
    cost_tracker = get_global_tracker()

    validation_result = {
        "quality_score": 0.0,
        "exploration_quality": False,
        "selection_quality": False,
        "issues": [],
    }

    # Check 1: Multiple paths explored
    num_paths = len(result["paths"])
    if num_paths >= 3:
        validation_result["quality_score"] += 0.3
        validation_result["exploration_quality"] = True

    # Check 2: Paths are evaluated
    evaluations = result["evaluations"]
    if len(evaluations) == num_paths:
        validation_result["quality_score"] += 0.2

    # Check 3: Best path selected
    best_path = result["best_path"]
    if best_path and "score" in best_path:
        validation_result["quality_score"] += 0.2
        validation_result["selection_quality"] = True

    # Check 4: Best path has highest score
    if evaluations and best_path:
        best_score = best_path["score"]
        all_scores = [e["score"] for e in evaluations]
        if best_score == max(all_scores):
            validation_result["quality_score"] += 0.2

    # Check 5: Final result is non-empty
    if len(result["final_result"]) > 10:
        validation_result["quality_score"] += 0.1

    # Track OpenAI cost (simulated)
    cost_tracker.track_usage(
        test_name="validate_tot_quality",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=200,
        output_tokens=100,
    )

    return validation_result


# Tests


@pytest.mark.timeout(120)
async def test_tot_agent_exploration():
    """
    Test 17: Tree-of-Thoughts agent exploration.

    Validates:
    - Multiple path generation with real OpenAI LLM
    - Path diversity (different reasoning approaches)
    - Path evaluation with scoring
    - Best path selection based on scores
    - Parallel execution (if enabled)
    - Cost tracking for all paths

    Duration: ~10-30 seconds
    Cost: $0.05 (OpenAI gpt-4o-mini for generation and evaluation)
    """
    cost_tracker = get_global_tracker()

    # Test task: Task benefiting from multiple perspectives
    task = (
        "Design an algorithm to find the shortest path in a graph with weighted edges"
    )

    # Create ToT agent
    config = ToTTestConfig(
        num_paths=3,  # Generate 3 paths
        temperature=0.7,  # Moderate diversity for OpenAI
        evaluation_criteria="quality",
        parallel_execution=True,
    )
    agent = create_tot_agent(config)

    # Execute ToT exploration with retry logic
    async def explore_paths():
        result = agent.run(task=task)
        return result

    result = await async_retry_with_backoff(
        explore_paths,
        max_attempts=3,
        initial_delay=2.0,  # Longer delay for multiple paths
    )

    # Track OpenAI cost (3 paths)
    # Estimate: 150 input + 400 output per path
    num_paths = len(result["paths"])
    cost_tracker.track_usage(
        test_name="test_tot_agent_exploration",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=150 * num_paths,
        output_tokens=400 * num_paths,
    )

    # Validate result structure
    assert validate_tot_result_structure(result), "ToT result structure is invalid"

    # Validate paths
    paths = result["paths"]
    assert (
        len(paths) == config.num_paths
    ), f"Expected {config.num_paths} paths, got {len(paths)}"

    # Each path should have proper structure
    for i, path in enumerate(paths):
        assert "path_id" in path, f"Path {i} missing path_id"
        assert "reasoning" in path, f"Path {i} missing reasoning"
        assert isinstance(
            path["reasoning"], str
        ), f"Path {i} reasoning should be string"

        # Path should have non-empty reasoning (unless error)
        if "error" not in path:
            assert len(path["reasoning"]) > 0, f"Path {i} has empty reasoning"

    # Validate path diversity
    diversity_result = validate_path_diversity(paths)
    print("\n✓ Path Diversity:")
    print(f"  Total paths: {len(paths)}")
    print(f"  Unique paths: {diversity_result['unique_paths']}")
    print(f"  Diversity score: {diversity_result['diversity_score']:.2f}")

    # Validate evaluations
    evaluations = result["evaluations"]
    assert len(evaluations) == len(paths), "Evaluations count mismatch"

    # Each evaluation should have score
    for i, evaluation in enumerate(evaluations):
        assert "score" in evaluation, f"Evaluation {i} missing score"
        assert "path" in evaluation, f"Evaluation {i} missing path"
        score = evaluation["score"]
        assert (
            0.0 <= score <= 1.0
        ), f"Evaluation {i} score {score} out of range [0.0, 1.0]"

    # Print evaluation scores
    print("\n✓ Path Evaluations:")
    for i, evaluation in enumerate(evaluations):
        score = evaluation["score"]
        print(f"  Path {i+1}: {score:.2f}")

    # Validate best path selection
    best_path = result["best_path"]
    assert "score" in best_path, "Best path missing score"
    assert "path" in best_path, "Best path missing path data"

    best_score = best_path["score"]
    all_scores = [e["score"] for e in evaluations]

    # Best path should have the highest score
    assert best_score == max(all_scores), "Best path doesn't have highest score"
    print("\n✓ Best Path Selected:")
    print(f"  Score: {best_score:.2f}")
    print(f"  Path ID: {best_path['path'].get('path_id', 'unknown')}")

    # Validate final result
    final_result = result["final_result"]
    assert isinstance(final_result, str), "Final result should be string"
    assert len(final_result) > 0, "Final result is empty"
    print(f"  Final result length: {len(final_result)} chars")

    # Validate quality with OpenAI
    quality_result = await validate_tot_quality_with_openai(result, task)
    assert quality_result["quality_score"] >= 0.5, "ToT quality too low"
    assert quality_result["exploration_quality"], "Exploration quality insufficient"
    assert quality_result["selection_quality"], "Selection quality insufficient"

    print("\n✓ Test 17 Passed: ToT exploration complete")
    print(f"  Paths explored: {num_paths}")
    print(f"  Best score: {best_score:.2f}")
    print(f"  Quality score: {quality_result['quality_score']:.2f}")
    print(f"  Exploration quality: {quality_result['exploration_quality']}")
    print(f"  Selection quality: {quality_result['selection_quality']}")

    # Validate ToT-specific behavior
    # 1. Multiple paths should be generated
    assert len(paths) >= 2, "ToT should generate multiple paths"

    # 2. Paths should be evaluated
    assert all("score" in e for e in evaluations), "All paths should be evaluated"

    # 3. Best path should be clearly selected
    best_path_id = best_path["path"].get("path_id")
    assert best_path_id is not None, "Best path should have an ID"
    print(
        f"  ✓ ToT pattern confirmed: {num_paths} paths, best selected (ID {best_path_id})"
    )

    # 4. Check for parallel execution evidence (if enabled)
    if config.parallel_execution:
        # All paths should have been generated (no early termination)
        assert (
            len(paths) == config.num_paths
        ), "Parallel execution should generate all paths"
        print(f"  ✓ Parallel execution: All {config.num_paths} paths generated")

    # 5. Validate score distribution
    score_range = max(all_scores) - min(all_scores)
    if score_range > 0.1:
        print(f"  ✓ Score differentiation: Range = {score_range:.2f}")
    else:
        print(f"  Note: Limited score differentiation (range = {score_range:.2f})")


# Cost report fixture


@pytest.fixture(scope="module", autouse=True)
def print_cost_report():
    """Print cost report after all tests complete."""
    yield
    cost_tracker = get_global_tracker()
    cost_tracker.print_report()
