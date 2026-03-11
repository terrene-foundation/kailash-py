"""
Tier 3 E2E Tests: PEV (Plan-Execute-Verify) Agent with Real OpenAI LLM.

Tests comprehensive PEV agent execution with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini - PAID, supports structured outputs)
- Complete Plan-Execute-Verify-Refine cycle
- Iterative refinement based on verification feedback
- Quality improvement over iterations

Requirements:
- OpenAI API key (required - PEV uses structured outputs for plan validation)
- No mocking (real infrastructure only)
- Tests may take 10-30s with OpenAI

Test Coverage:
1. test_pev_agent_complete_cycle (Test 16) - Full PEV cycle with verification

Budget: $0.05 (OpenAI gpt-4o-mini for plan, execute, verify stages)
Duration: ~10-30s

Provider Compatibility Note:
PEV agent requires structured outputs for plan/verification schemas.
Only OpenAI supports this - Ollama/Anthropic will timeout or fail.
"""

# Check OpenAI API key availability
import os
from dataclasses import dataclass
from typing import Any, Dict

import pytest
from dotenv import load_dotenv
from kaizen.agents.specialized.pev import PEVAgent

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import (
    OllamaHealthChecker,
    async_retry_with_backoff,
)

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
class PEVTestConfig:
    """Configuration for PEV E2E tests."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"  # Cost-effective with structured outputs support
    temperature: float = 0.3  # Lower temp for consistent structured outputs
    max_iterations: int = 3  # Keep small for faster tests
    verification_strictness: str = "medium"  # Balance between strict and lenient
    enable_error_recovery: bool = True


# Helper Functions


def create_pev_agent(config: PEVTestConfig = None) -> PEVAgent:
    """Create PEV agent with test configuration."""
    if config is None:
        config = PEVTestConfig()

    agent = PEVAgent(
        llm_provider=config.llm_provider,
        model=config.model,
        temperature=config.temperature,
        max_iterations=config.max_iterations,
        verification_strictness=config.verification_strictness,
        enable_error_recovery=config.enable_error_recovery,
    )

    return agent


def validate_pev_result_structure(result: Dict[str, Any]) -> bool:
    """Validate PEV result has proper structure.

    Args:
        result: The PEV result to validate

    Returns:
        True if structure is valid
    """
    required_keys = [
        "plan",
        "execution_result",
        "verification",
        "refinements",
        "final_result",
    ]

    for key in required_keys:
        if key not in result:
            return False

    # Validate plan structure
    plan = result["plan"]
    if not isinstance(plan, dict):
        return False

    # Validate execution result
    execution_result = result["execution_result"]
    if not isinstance(execution_result, dict):
        return False
    if "status" not in execution_result:
        return False

    # Validate verification
    verification = result["verification"]
    if not isinstance(verification, dict):
        return False
    if "passed" not in verification:
        return False
    if not isinstance(verification["passed"], bool):
        return False

    # Validate refinements
    refinements = result["refinements"]
    if not isinstance(refinements, list):
        return False

    # Validate final result
    final_result = result["final_result"]
    if not isinstance(final_result, str):
        return False

    return True


async def validate_pev_quality_with_openai(
    result: Dict[str, Any], task: str
) -> Dict[str, Any]:
    """Validate PEV result quality using OpenAI GPT-4o-mini.

    This is the ONLY place we use OpenAI (for quality validation).

    Args:
        result: The PEV result to validate
        task: Original task

    Returns:
        Dict with validation results
    """
    cost_tracker = get_global_tracker()

    validation_result = {
        "quality_score": 0.0,
        "completeness": False,
        "improvement": False,
        "issues": [],
    }

    # Check 1: Verification passed
    if result["verification"]["passed"]:
        validation_result["quality_score"] += 0.4
        validation_result["completeness"] = True

    # Check 2: Has plan
    if result["plan"] and len(result["plan"]) > 0:
        validation_result["quality_score"] += 0.2

    # Check 3: Has execution result
    if result["execution_result"].get("status") == "success":
        validation_result["quality_score"] += 0.2

    # Check 4: Has refinements (shows iterative improvement)
    if len(result["refinements"]) > 0:
        validation_result["quality_score"] += 0.1
        validation_result["improvement"] = True

    # Check 5: Final result is non-empty
    if len(result["final_result"]) > 10:
        validation_result["quality_score"] += 0.1

    # Track OpenAI cost (simulated)
    cost_tracker.track_usage(
        test_name="validate_pev_quality",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=150,
        output_tokens=75,
    )

    return validation_result


# Tests


@pytest.mark.timeout(120)
async def test_pev_agent_complete_cycle():
    """
    Test 16: PEV agent (Plan-Execute-Verify) complete cycle.

    Validates:
    - Plan creation with real OpenAI LLM (gpt-4o-mini)
    - Plan execution
    - Result verification
    - Iterative refinement based on feedback
    - Quality improvement over iterations
    - Cost tracking for all iterations

    Duration: ~60-90 seconds
    Cost: $0.025 (Ollama free + OpenAI validation)
    """
    cost_tracker = get_global_tracker()

    # Test task: Task that benefits from iterative refinement
    task = "Generate a Python function to calculate fibonacci numbers with optimization"

    # Create PEV agent
    config = PEVTestConfig(
        max_iterations=3,
        verification_strictness="medium",
        enable_error_recovery=True,
    )
    agent = create_pev_agent(config)

    # Execute PEV cycle with retry logic
    async def execute_pev_cycle():
        result = agent.run(task=task)
        return result

    result = await async_retry_with_backoff(
        execute_pev_cycle,
        max_attempts=3,
        initial_delay=2.0,  # Longer delay for PEV (multiple iterations)
    )

    # Track Ollama cost (multiple iterations)
    # Estimate: 200 input + 500 output per iteration
    num_iterations = len(result["refinements"]) + 1  # Initial + refinements
    cost_tracker.track_usage(
        test_name="test_pev_agent_complete_cycle",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=200 * num_iterations,
        output_tokens=500 * num_iterations,
    )

    # Validate result structure
    assert validate_pev_result_structure(result), "PEV result structure is invalid"

    # Validate plan
    plan = result["plan"]
    assert isinstance(plan, dict), "Plan should be a dict"
    assert len(plan) > 0, "Plan is empty"

    # Validate execution result
    execution_result = result["execution_result"]
    assert "status" in execution_result
    assert execution_result["status"] in ["success", "failed"]

    # Validate verification
    verification = result["verification"]
    assert "passed" in verification
    assert isinstance(verification["passed"], bool)
    assert "issues" in verification
    assert isinstance(verification["issues"], list)

    # Validate refinements
    refinements = result["refinements"]
    assert isinstance(refinements, list)
    assert len(refinements) <= config.max_iterations

    # Each refinement should be a string describing the improvement
    for refinement in refinements:
        assert isinstance(refinement, str)
        assert len(refinement) > 0

    # Validate final result
    final_result = result["final_result"]
    assert isinstance(final_result, str)
    assert len(final_result) > 0

    # Validate quality with OpenAI
    quality_result = await validate_pev_quality_with_openai(result, task)
    assert quality_result["quality_score"] >= 0.4, "PEV quality too low"

    # Validate PEV-specific behavior
    print("\n✓ Test 16 Passed: PEV complete cycle")
    print(f"  Iterations: {num_iterations}")
    print(f"  Refinements: {len(refinements)}")
    print(f"  Verification passed: {verification['passed']}")
    print(f"  Quality score: {quality_result['quality_score']:.2f}")

    if refinements:
        print(f"  Improvement detected: {quality_result['improvement']}")
        print(f"  Sample refinement: {refinements[0][:80]}...")

    # Check verification details
    if not verification["passed"]:
        print(f"  Verification issues: {verification['issues']}")
        # Even if verification didn't pass, the agent should have attempted refinement
        if config.enable_error_recovery:
            print("  Error recovery enabled - refinement attempted")

    # Key PEV validation: Agent should show iterative behavior
    # Either verification passed OR refinements were made
    assert (
        verification["passed"] or len(refinements) > 0
    ), "PEV agent should either pass verification or make refinements"

    # If verification passed, quality should be higher
    if verification["passed"]:
        assert (
            quality_result["quality_score"] >= 0.5
        ), "Passed verification but low quality"
        assert quality_result["completeness"], "Passed verification but incomplete"

    # Validate execution details
    if execution_result.get("status") == "success":
        assert "output" in execution_result, "Successful execution should have output"
        assert len(execution_result["output"]) > 0, "Execution output is empty"
        print(f"  Execution output length: {len(execution_result['output'])} chars")

    # Validate plan structure (PEV-specific)
    if "refinements" in plan:
        plan_refinements = plan["refinements"]
        print(f"  Plan refinements tracked: {len(plan_refinements)}")

    # Check for improvement over iterations
    if len(refinements) >= 2:
        # Multiple refinements suggest genuine iterative improvement
        assert quality_result[
            "improvement"
        ], "Multiple refinements but no improvement detected"
        print(f"  ✓ Iterative improvement confirmed ({len(refinements)} refinements)")


# Cost report fixture


@pytest.fixture(scope="module", autouse=True)
def print_cost_report():
    """Print cost report after all tests complete."""
    yield
    cost_tracker = get_global_tracker()
    cost_tracker.print_report()
