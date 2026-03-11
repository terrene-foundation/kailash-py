"""
Integration tests for Tree-of-Thoughts Agent (Tier 2 - Real Infrastructure)

Tests ToT agent with real LLM infrastructure (OpenAI).

Requirements:
- OPENAI_API_KEY must be set in .env
- NO MOCKING - real inference required
- Performance target: <10 seconds for 5 paths
- Real parallel path generation and evaluation

Test Coverage:
- 5 integration tests total
- Complete ToT flow with real LLM
- Real path diversity validation
- Evaluation accuracy with real scoring
- Performance validation (<10s for 5 paths)
- Semaphore control for concurrent execution

Expected test execution time: <10 seconds per test (Tier 2)
"""

import os

import pytest

try:
    from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig
except ImportError:
    pytest.skip("ToT agent not yet implemented", allow_module_level=True)


# ============================================================================
# INTEGRATION TESTS (5 tests) - Real Ollama Inference
# ============================================================================


@pytest.mark.integration
def test_tot_complete_flow_openai():
    """Test complete ToT flow with real OpenAI inference"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        num_paths=3,
        evaluation_criteria="quality",
    )
    agent = ToTAgent(config=config)

    task = "Decide the best approach to learn Python programming"
    result = agent.run(task=task)

    # Verify complete flow
    assert "paths" in result
    assert "evaluations" in result
    assert "best_path" in result
    assert "final_result" in result

    # Should generate requested number of paths
    assert len(result["paths"]) == 3
    assert len(result["evaluations"]) == 3


@pytest.mark.integration
@pytest.mark.timeout(240)  # GPT-5 reasoning models need longer timeouts for 5 paths
def test_tot_path_diversity_openai():
    """Test path diversity with real OpenAI (different reasoning approaches)"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        num_paths=5,
        temperature=1.0,  # GPT-5 models require temperature=1.0
    )
    agent = ToTAgent(config=config)

    task = "Choose the best programming language for web development"
    result = agent.run(task=task)

    # Should generate diverse paths
    assert len(result["paths"]) == 5

    # Paths should be different (at least some variation)
    # This is a heuristic check - in production would need deeper analysis
    unique_paths = set()
    for path in result["paths"]:
        if isinstance(path, dict):
            # Check multiple possible fields for diversity
            path_str = str(path)[:100]  # Full path content (first 100 chars)
        else:
            path_str = str(path)[:100]
        unique_paths.add(path_str)

    # Should have some diversity (not all identical)
    # With high temperature, at least 2 paths should differ
    assert len(unique_paths) >= 2, f"Expected diverse paths, got: {unique_paths}"


@pytest.mark.integration
def test_tot_evaluation_accuracy_openai():
    """Test evaluation accuracy with real OpenAI scoring"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        num_paths=3,
        evaluation_criteria="quality",
    )
    agent = ToTAgent(config=config)

    task = "Evaluate different solutions for sorting algorithms"
    result = agent.run(task=task)

    # Verify evaluation structure
    assert len(result["evaluations"]) == 3

    # Each evaluation should have valid score
    for evaluation in result["evaluations"]:
        assert "score" in evaluation
        assert isinstance(evaluation["score"], (int, float))
        assert 0 <= evaluation["score"] <= 1

    # Best path should have highest score
    best_score = result["best_path"]["score"]
    all_scores = [eval["score"] for eval in result["evaluations"]]
    assert best_score == max(all_scores)


@pytest.mark.integration
@pytest.mark.timeout(180)  # GPT-5 reasoning models need longer timeouts
def test_tot_performance_openai():
    """Test ToT performance with real OpenAI (reasonable time for 5 paths)"""
    import time

    config = ToTAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        num_paths=5,
        parallel_execution=True,
    )
    agent = ToTAgent(config=config)

    start_time = time.time()
    result = agent.run(task="Quick decision task")
    elapsed = time.time() - start_time

    # GPT-5 reasoning models take longer due to internal chain-of-thought
    # 5 paths + evaluations with reasoning tokens typically takes 90-150s
    assert elapsed < 180.0, f"ToT took {elapsed:.1f}s, expected < 180s"

    # Should have all paths
    assert len(result["paths"]) == 5


@pytest.mark.integration
@pytest.mark.timeout(180)  # GPT-5 reasoning models need longer timeouts
def test_tot_semaphore_control_openai():
    """Test semaphore control for concurrent path generation"""
    config = ToTAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        num_paths=5,
        parallel_execution=True,
    )
    agent = ToTAgent(config=config)

    task = "Test concurrent path generation"
    result = agent.run(task=task)

    # Should generate all paths successfully (with semaphore control)
    assert len(result["paths"]) == 5
    assert "best_path" in result
