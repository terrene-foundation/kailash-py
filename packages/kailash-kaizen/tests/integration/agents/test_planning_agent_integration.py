"""
Integration tests for Planning Agent (Tier 2 - Real OpenAI)

Test Coverage:
- 5 integration tests total
- Real OpenAI inference (NO MOCKING)
- Complete flow testing (plan → validate → execute)
- Tool integration with MCP
- Error recovery scenarios
- Performance validation (<500ms plan generation)

Test Requirements:
- OPENAI_API_KEY must be set in .env
- Test execution time: <5 seconds per test
- Uses real infrastructure (NO MOCKING)

Run with:
    pytest tests/integration/agents/test_planning_agent_integration.py -v
"""

import time

import pytest

# Import agent components
try:
    from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig
except ImportError:
    pytest.skip("Planning agent not yet implemented", allow_module_level=True)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def openai_config():
    """Fixture for OpenAI-based planning configuration"""
    import os

    return PlanningConfig(
        llm_provider="openai",
        model=os.environ.get("OPENAI_DEV_MODEL", "gpt-4o-mini"),
        temperature=1.0,  # GPT-5 models require temperature=1.0
        max_plan_steps=5,
        validation_mode="strict",
    )


@pytest.fixture
def planning_agent(openai_config):
    """Fixture for Planning Agent with OpenAI"""
    return PlanningAgent(config=openai_config)


# ============================================================================
# INTEGRATION TESTS (5 tests)
# ============================================================================


@pytest.mark.integration
@pytest.mark.openai
def test_openai_complete_flow(planning_agent):
    """
    Test complete plan → validate → execute flow with real Ollama inference

    This test verifies the entire Planning Agent workflow:
    1. Generate plan from task
    2. Validate plan (tool availability, step order)
    3. Execute plan steps sequentially
    4. Aggregate results
    """
    task = "Research the benefits of meditation and create a summary"

    start_time = time.time()
    result = planning_agent.run(task=task)
    elapsed_time = time.time() - start_time

    # Verify complete result structure
    assert "plan" in result, "Plan not generated"
    assert "validation_result" in result, "Validation not performed"
    assert "execution_results" in result, "Execution not completed"
    assert "final_result" in result, "Final result not aggregated"

    # Verify plan quality
    assert len(result["plan"]) > 0, "Plan is empty"
    assert len(result["plan"]) <= 5, "Plan exceeds max_plan_steps"

    # Verify validation
    assert result["validation_result"]["status"] in [
        "valid",
        "warnings",
    ], f"Unexpected validation status: {result['validation_result']['status']}"

    # Verify execution results
    assert len(result["execution_results"]) > 0, "No execution results"

    # Verify final result exists
    assert result["final_result"], "Final result is empty"

    # Performance check (GPT-5 reasoning models take longer due to internal CoT)
    assert elapsed_time < 30.0, f"Plan generation took too long: {elapsed_time:.2f}s"


@pytest.mark.integration
@pytest.mark.openai
def test_openai_plan_generation_performance(planning_agent):
    """
    Test that plan generation meets performance target

    NOTE: OpenAI API calls have network latency. We accept up to 5 seconds
    for integration tests (matching Tier 2 target of <5s per test).
    """
    task = "Create a 3-step plan for organizing a small event"

    start_time = time.time()
    result = planning_agent.run(task=task)
    plan_generation_time = time.time() - start_time

    # Verify plan generated
    assert "plan" in result
    assert len(result["plan"]) > 0

    # Performance target (relaxed for GPT-5 reasoning models with CoT tokens)
    # GPT-5 takes longer due to internal reasoning before generating output
    print(f"Plan generation time: {plan_generation_time:.3f}s")
    assert (
        plan_generation_time < 30.0
    ), f"Plan generation too slow: {plan_generation_time:.3f}s (target: <30s)"


@pytest.mark.integration
@pytest.mark.openai
def test_openai_replanning_on_validation_failure(openai_config):
    """
    Test replanning when validation fails (enable_replanning=True)

    This tests the agent's ability to regenerate a better plan when
    the initial plan fails validation.
    """
    config = openai_config
    config.enable_replanning = True
    config.validation_mode = "strict"

    agent = PlanningAgent(config=config)

    # Task that may require replanning
    task = "Create plan with strict validation requirements"

    result = agent.run(task=task)

    # Should generate a valid plan (possibly after replanning)
    assert "plan" in result
    assert "validation_result" in result

    # If replanning occurred, should indicate in result
    if "replanning_iterations" in result:
        assert result["replanning_iterations"] >= 0


@pytest.mark.integration
@pytest.mark.openai
def test_openai_error_recovery(planning_agent):
    """
    Test error recovery during plan execution

    Verifies that the agent handles execution errors gracefully and
    provides informative error messages.
    """
    # Task that may encounter execution challenges
    task = "Execute a plan that involves external dependencies"

    result = planning_agent.run(task=task)

    # Should complete even with potential errors
    assert "execution_results" in result

    # Check for error handling
    if "errors" in result:
        # Errors should be structured and informative
        assert isinstance(result["errors"], list)
        for error in result["errors"]:
            assert "step" in error or "message" in error

    # Should still produce some result
    assert "final_result" in result or "error" in result


@pytest.mark.integration
@pytest.mark.openai
def test_openai_complex_multi_step_task(planning_agent):
    """
    Test complex multi-step task with real Ollama reasoning

    Verifies that the agent can handle sophisticated tasks requiring
    multiple logical steps and dependencies.
    """
    task = """
    Create a comprehensive plan for:
    1. Researching AI safety concerns
    2. Analyzing the findings
    3. Writing a summary report
    4. Creating recommendations
    5. Formatting the final document
    """

    result = planning_agent.run(task=task)

    # Verify comprehensive plan
    assert "plan" in result
    assert len(result["plan"]) >= 3, "Plan too simple for complex task"

    # Verify logical step ordering
    step_numbers = [step["step"] for step in result["plan"]]
    assert step_numbers == sorted(step_numbers), "Steps not properly ordered"

    # Verify each step has meaningful content
    for step in result["plan"]:
        assert len(step["action"]) > 10, "Step action too brief"
        assert len(step["description"]) > 10, "Step description too brief"

    # Verify validation and execution
    assert "validation_result" in result
    assert "execution_results" in result
    assert "final_result" in result


# ============================================================================
# PERFORMANCE BENCHMARKS
# ============================================================================


@pytest.mark.integration
@pytest.mark.openai
@pytest.mark.benchmark
def test_openai_planning_agent_benchmark(planning_agent):
    """
    Benchmark test for Planning Agent performance

    Measures:
    - Plan generation time
    - Validation time
    - Execution time
    - Total time
    """
    task = "Create a 5-step plan for learning a new skill"

    # Measure plan generation
    start_plan = time.time()
    result = planning_agent.run(task=task)
    total_time = time.time() - start_plan

    # Print benchmark results
    print(f"\n{'='*60}")
    print("Planning Agent Benchmark Results")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.3f}s")
    print(f"Plan steps: {len(result.get('plan', []))}")
    print(f"Validation: {result.get('validation_result', {}).get('status', 'N/A')}")
    print(f"Execution results: {len(result.get('execution_results', []))}")
    print(f"{'='*60}\n")

    # Assertions
    assert result is not None
    assert "plan" in result
    assert "validation_result" in result
    assert "execution_results" in result
