"""
E2E tests for Tree-of-Thoughts Agent (Tier 3 - Production Infrastructure)

Tests ToT agent with real OpenAI API (paid).

Requirements:
- OPENAI_API_KEY must be set in .env
- NO MOCKING - real production inference
- Budget control: <$0.50 total for all tests
- Real-world high-stakes decisions

Test Coverage:
- 3 E2E tests total
- High-stakes decision task
- Alternative exploration validation
- Real-world complex problem

Expected test execution time: <30 seconds per test (Tier 3)
"""

import os

import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig
except ImportError:
    pytest.skip("ToT agent not yet implemented", allow_module_level=True)

# Skip if no OpenAI API key
if not os.getenv("OPENAI_API_KEY"):
    pytest.skip("OPENAI_API_KEY not found in environment", allow_module_level=True)


# ============================================================================
# E2E TESTS (3 tests) - Real OpenAI Inference
# ============================================================================


@pytest.mark.e2e
def test_tot_high_stakes_decision_openai():
    """Test ToT with high-stakes decision (OpenAI)"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        num_paths=5,
        evaluation_criteria="quality",
        temperature=0.9,
    )
    agent = ToTAgent(config=config)

    task = """
    Make a strategic decision: Should a startup focus on:
    A) Enterprise B2B market
    B) Consumer B2C market
    C) Platform/marketplace model
    D) Vertical integration
    E) Hybrid approach

    Consider: market size, competition, resources, time to market, scalability.
    """

    result = agent.run(task=task)

    # Should explore multiple paths
    assert len(result["paths"]) == 5
    assert len(result["evaluations"]) == 5

    # Should select best path with reasoning
    assert "best_path" in result
    assert "final_result" in result
    assert len(result["final_result"]) > 100  # Detailed analysis


@pytest.mark.e2e
def test_tot_alternative_exploration_openai():
    """Test ToT explores diverse alternatives (OpenAI)"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        num_paths=7,
        evaluation_criteria="creativity",
        temperature=0.95,  # High for maximum diversity
    )
    agent = ToTAgent(config=config)

    task = """
    Design a novel solution for reducing urban traffic congestion.
    Explore unconventional approaches beyond typical solutions.
    """

    result = agent.run(task=task)

    # Should generate diverse paths
    assert len(result["paths"]) == 7

    # Paths should be evaluated for creativity
    for evaluation in result["evaluations"]:
        assert "score" in evaluation
        assert isinstance(evaluation["score"], (int, float))

    # Should select most creative approach
    assert "best_path" in result


@pytest.mark.e2e
def test_tot_real_world_complex_problem_openai():
    """Test ToT with real-world complex problem (OpenAI)"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        num_paths=5,
        evaluation_criteria="quality",
        parallel_execution=True,
    )
    agent = ToTAgent(config=config)

    task = """
    Analyze and recommend the best architecture for a large-scale
    e-commerce platform that needs to:
    - Handle 1M+ daily users
    - Process real-time inventory
    - Support multiple payment gateways
    - Ensure high availability (99.99% uptime)
    - Scale globally

    Consider: microservices, serverless, monolith, database choices,
    caching, CDN, deployment strategy.
    """

    result = agent.run(task=task)

    # Should generate comprehensive analysis
    assert len(result["paths"]) == 5

    # Each path should be evaluated
    for evaluation in result["evaluations"]:
        assert "score" in evaluation

    # Best path should be technically sound
    assert "best_path" in result
    assert "final_result" in result
    assert len(result["final_result"]) > 200  # Detailed architecture
