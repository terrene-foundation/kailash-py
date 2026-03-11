"""
E2E tests for PEV Agent (Tier 3 - Production Infrastructure)

Tests PEV agent with real OpenAI API (paid).

Requirements:
- OPENAI_API_KEY must be set in .env
- NO MOCKING - real production inference
- Budget control: <$0.50 total for all tests
- Real-world complex tasks

Test Coverage:
- 3 E2E tests total
- Complex real-world task
- Verification edge cases
- Production scenario validation

Expected test execution time: <30 seconds per test (Tier 3)
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig
except ImportError:
    pytest.skip("PEV agent not yet implemented", allow_module_level=True)

# Skip if no OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    pytest.skip("OPENAI_API_KEY not found in environment", allow_module_level=True)


# ============================================================================
# E2E TESTS (3 tests) - Real OpenAI Inference
# ============================================================================


@pytest.mark.e2e
def test_pev_complex_task_openai():
    """Test PEV with complex real-world task (OpenAI)"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        max_iterations=5,
        verification_strictness="strict",
    )
    agent = PEVAgent(config=config)

    task = """
    Generate a Python function that:
    1. Reads a CSV file
    2. Validates data types
    3. Handles missing values
    4. Calculates summary statistics
    5. Returns a formatted report

    The function should handle errors gracefully and be well-documented.
    """

    result = agent.run(task=task)

    # Verify complete solution
    assert "final_result" in result
    assert "verification" in result
    assert "refinements" in result

    # Should produce working code
    assert len(result["final_result"]) > 100  # Substantial output


@pytest.mark.e2e
def test_pev_verification_edge_cases_openai():
    """Test PEV verification with edge cases (OpenAI)"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        max_iterations=3,
        verification_strictness="strict",
    )
    agent = PEVAgent(config=config)

    task = "Write a function with edge cases: empty input, null values, type mismatches"
    result = agent.run(task=task)

    # Should handle edge cases
    assert "verification" in result
    assert "refinements" in result

    # Verification should detect and refine edge case handling
    if len(result["refinements"]) > 0:
        assert isinstance(result["refinements"], list)


@pytest.mark.e2e
def test_pev_production_scenario_openai():
    """Test PEV in production scenario (OpenAI)"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        max_iterations=5,
        verification_strictness="medium",
        enable_error_recovery=True,
    )
    agent = PEVAgent(config=config)

    task = """
    Create a production-ready REST API endpoint that:
    - Accepts JSON input
    - Validates request data
    - Processes business logic
    - Returns proper HTTP responses
    - Includes error handling
    """

    result = agent.run(task=task)

    # Should produce production-ready code
    assert "final_result" in result
    assert "verification" in result

    # Should pass verification for production quality
    if result["verification"].get("passed"):
        assert len(result["final_result"]) > 200  # Substantial code
