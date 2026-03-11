"""
Integration tests for PEV Agent (Tier 2 - Real Infrastructure)

Tests PEV agent with real LLM infrastructure (OpenAI).

Requirements:
- OPENAI_API_KEY must be set in .env
- NO MOCKING - real inference required
- Performance target: <5 seconds per test
- Real iterative refinement cycles

Test Coverage:
- 5 integration tests total
- Complete PEV flow with real LLM
- Real error recovery scenarios
- Iteration limits with real cycles
- Performance validation
- Tool integration (if applicable)

Expected test execution time: <5 seconds per test (Tier 2)
"""

import os

import pytest

try:
    from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig
except ImportError:
    pytest.skip("PEV agent not yet implemented", allow_module_level=True)


# ============================================================================
# INTEGRATION TESTS (5 tests) - Real Ollama Inference
# ============================================================================


@pytest.mark.integration
def test_pev_complete_flow_openai():
    """Test complete PEV flow with real OpenAI inference"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        max_iterations=3,
        verification_strictness="medium",
    )
    agent = PEVAgent(config=config)

    task = "Generate a Python function to calculate factorial"
    result = agent.run(task=task)

    # Verify complete flow
    assert "plan" in result
    assert "execution_result" in result
    assert "verification" in result
    assert "refinements" in result
    assert "final_result" in result

    # Should complete successfully
    assert isinstance(result["final_result"], str)
    assert len(result["final_result"]) > 0


@pytest.mark.integration
def test_pev_error_recovery_openai():
    """Test PEV error recovery with real OpenAI"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        max_iterations=5,
        enable_error_recovery=True,
    )
    agent = PEVAgent(config=config)

    task = "Write code with intentional errors then fix them"
    result = agent.run(task=task)

    # Should attempt error recovery
    assert "refinements" in result
    assert isinstance(result["refinements"], list)


@pytest.mark.integration
def test_pev_iteration_limits_openai():
    """Test PEV respects max_iterations with real cycles"""
    config = PEVAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        max_iterations=2,
    )
    agent = PEVAgent(config=config)

    task = "Complex task requiring multiple iterations"
    result = agent.run(task=task)

    # Should not exceed max_iterations
    assert "refinements" in result
    assert len(result["refinements"]) <= 2


@pytest.mark.integration
@pytest.mark.timeout(120)  # GPT-5 reasoning models need longer timeouts
def test_pev_performance_openai():
    """Test PEV performance with real OpenAI (reasonable time per iteration)"""
    import time

    config = PEVAgentConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        max_iterations=1,  # Single iteration for performance test
    )
    agent = PEVAgent(config=config)

    start_time = time.time()
    result = agent.run(task="Simple task for performance test")
    elapsed = time.time() - start_time

    # GPT-5 reasoning models take longer due to internal chain-of-thought
    # PEV has 3 phases (Plan, Execute, Verify), each with reasoning tokens
    assert elapsed < 60.0, f"PEV took {elapsed:.1f}s, expected < 60s"

    # Should have valid result
    assert "final_result" in result


@pytest.mark.integration
@pytest.mark.timeout(300)  # 3 strictness levels × ~60s each for GPT-5
def test_pev_verification_strictness_openai():
    """Test different verification strictness levels with real OpenAI"""
    strictness_levels = ["strict", "medium", "lenient"]

    for strictness in strictness_levels:
        config = PEVAgentConfig(
            llm_provider="openai",
            model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
            temperature=1.0,  # GPT-5 models require temperature=1.0
            max_iterations=2,
            verification_strictness=strictness,
        )
        agent = PEVAgent(config=config)

        result = agent.run(task=f"Task with {strictness} verification")

        # Should complete with verification result
        assert "verification" in result
        assert isinstance(result["verification"], dict)
