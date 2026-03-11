"""
Unit tests for Planning Agent (TDD Approach - Tests Written First)

Test Philosophy (Tier 1 - Unit Tests with Mock Provider):
- Test agent instantiation and configuration
- Test method existence and signature
- Test input validation and error handling
- Test config defaults and custom values
- DO NOT test LLM output content (that's for Tier 2/3 with real providers)

Note: Tests that verify actual LLM response content (plan structure, step quality,
validation results, execution results) belong in integration tests (Tier 2/3) with
real LLM providers configured via .env file.

Expected test execution time: <1 second per test (Tier 1)
"""

import pytest

# Import agent components (will be implemented after tests)
try:
    from kaizen.agents.specialized.planning import (
        PlanningAgent,
        PlanningConfig,
        PlanningSignature,
    )
except ImportError:
    pytest.skip("Planning agent not yet implemented", allow_module_level=True)


# ============================================================================
# INSTANTIATION AND CONFIGURATION TESTS
# ============================================================================


def test_planning_agent_instantiation():
    """Test PlanningAgent can be instantiated with config."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    assert agent is not None
    assert agent.config is not None
    assert agent.config.llm_provider == "mock"


def test_planning_agent_has_run_method():
    """Test PlanningAgent has run() method."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    assert hasattr(agent, "run")
    assert callable(agent.run)


def test_planning_config_defaults():
    """Test PlanningConfig default values."""
    config = PlanningConfig()

    # Verify default values
    assert config.llm_provider == "openai"
    assert config.model == "gpt-4"
    assert config.temperature == 0.7
    assert config.max_plan_steps == 10
    assert config.validation_mode == "strict"
    assert config.enable_replanning is True


def test_planning_config_custom_values():
    """Test PlanningConfig with custom values."""
    config = PlanningConfig(
        llm_provider="anthropic",
        model="claude-3-opus",
        temperature=0.3,
        max_plan_steps=5,
        validation_mode="warn",
        enable_replanning=False,
    )

    # Verify custom values
    assert config.llm_provider == "anthropic"
    assert config.model == "claude-3-opus"
    assert config.temperature == 0.3
    assert config.max_plan_steps == 5
    assert config.validation_mode == "warn"
    assert config.enable_replanning is False


def test_planning_signature_fields():
    """Test PlanningSignature has required fields."""
    sig = PlanningSignature()

    # Verify input fields
    assert hasattr(sig, "task")
    assert hasattr(sig, "context")

    # Verify output fields
    assert hasattr(sig, "plan")
    assert hasattr(sig, "validation_result")
    assert hasattr(sig, "execution_results")
    assert hasattr(sig, "final_result")


# ============================================================================
# RUN METHOD EXECUTION TESTS
# ============================================================================


def test_run_accepts_simple_task():
    """Test run() accepts a simple task string and returns dict.

    Note: Actual plan structure depends on LLM response and is validated
    in integration tests with real providers.
    """
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    result = agent.run(task="Research AI ethics")

    # Unit test: verify execution completes and returns dict
    assert isinstance(result, dict)


def test_run_accepts_complex_task():
    """Test run() accepts a complex task string and returns dict.

    Note: Actual plan content depends on LLM response and is validated
    in integration tests with real providers.
    """
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        max_plan_steps=10,
    )
    agent = PlanningAgent(config=config)

    result = agent.run(
        task="Create comprehensive research report on AI ethics with citations"
    )

    # Unit test: verify execution completes and returns dict
    assert isinstance(result, dict)
    # Configuration should be respected (stored in planning_config, not config)
    assert agent.planning_config.max_plan_steps == 10


def test_run_accepts_task_with_context():
    """Test run() accepts task with additional context kwargs.

    Note: How context affects plan generation is validated in integration tests.
    """
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    context = {"max_pages": 10, "audience": "executives"}
    result = agent.run(task="Create report", context=context)

    # Unit test: verify execution completes with context argument
    assert isinstance(result, dict)


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================


def test_run_handles_empty_task():
    """Test run() handles empty task gracefully."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    result = agent.run(task="")

    # Should return a dict (either with error or empty plan)
    assert isinstance(result, dict)
    # If error handling is implemented, should return INVALID_INPUT
    if "error" in result:
        assert result["error"] == "INVALID_INPUT"


def test_run_handles_whitespace_task():
    """Test run() handles whitespace-only task."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    result = agent.run(task="   ")

    # Should return a dict
    assert isinstance(result, dict)


# ============================================================================
# CONFIGURATION ACCEPTANCE TESTS
# ============================================================================


def test_config_max_steps_accepted():
    """Test that max_plan_steps config is accepted by agent."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        max_plan_steps=3,
    )
    agent = PlanningAgent(config=config)

    # Verify config is stored (in planning_config, not config)
    assert agent.planning_config.max_plan_steps == 3

    # Execution should complete
    result = agent.run(task="Complex task")
    assert isinstance(result, dict)


def test_config_temperature_accepted():
    """Test that temperature config is accepted by agent."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        temperature=0.0,
    )
    agent = PlanningAgent(config=config)

    # Verify config is stored (in planning_config, not config)
    assert agent.planning_config.temperature == 0.0

    # Execution should complete
    result = agent.run(task="Simple task")
    assert isinstance(result, dict)


def test_config_validation_mode_strict():
    """Test that strict validation mode is accepted."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        validation_mode="strict",
    )
    agent = PlanningAgent(config=config)

    assert agent.planning_config.validation_mode == "strict"

    # Execution should complete
    result = agent.run(task="Valid task")
    assert isinstance(result, dict)


def test_config_validation_mode_warn():
    """Test that warn validation mode is accepted."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        validation_mode="warn",
    )
    agent = PlanningAgent(config=config)

    assert agent.planning_config.validation_mode == "warn"

    # Execution should complete
    result = agent.run(task="Task with potential issues")
    assert isinstance(result, dict)


def test_config_validation_mode_off():
    """Test that off validation mode is accepted."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        validation_mode="off",
    )
    agent = PlanningAgent(config=config)

    assert agent.planning_config.validation_mode == "off"

    # Execution should complete
    result = agent.run(task="Any task")
    assert isinstance(result, dict)


def test_config_enable_replanning():
    """Test that enable_replanning config is accepted."""
    config = PlanningConfig(
        llm_provider="mock",
        model="mock-model",
        enable_replanning=False,
    )
    agent = PlanningAgent(config=config)

    assert agent.planning_config.enable_replanning is False

    # Execution should complete
    result = agent.run(task="Task that may fail")
    assert isinstance(result, dict)


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


def test_multiple_runs_same_agent():
    """Test that same agent can be used for multiple runs."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    result1 = agent.run(task="First task")
    result2 = agent.run(task="Second task")

    # Both should complete successfully
    assert isinstance(result1, dict)
    assert isinstance(result2, dict)


def test_run_with_special_characters():
    """Test run() handles task with special characters."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    # Task with various special characters
    task = "Create report about 'AI & ML' - including 50% stats @work"
    result = agent.run(task=task)

    assert isinstance(result, dict)


def test_run_with_very_long_task():
    """Test run() handles very long task description."""
    config = PlanningConfig(llm_provider="mock", model="mock-model")
    agent = PlanningAgent(config=config)

    # Very long task
    task = "Please create a comprehensive report " * 100
    result = agent.run(task=task)

    assert isinstance(result, dict)
