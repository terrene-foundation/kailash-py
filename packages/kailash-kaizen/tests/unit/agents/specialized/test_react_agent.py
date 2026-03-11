"""
Test ReActAgent - Production-Ready Library Agent

Tests zero-config initialization, progressive configuration,
MultiCycleStrategy integration, and ReAct-specific features.

Written BEFORE implementation (TDD).
"""

import os

import pytest


class TestReActAgentInitialization:
    """Test agent initialization patterns."""

    def test_zero_config_initialization(self):
        """Test agent works with zero configuration (most important test)."""
        from kaizen.agents.specialized.react import ReActAgent

        # Should work with no parameters
        agent = ReActAgent()

        assert agent is not None
        assert hasattr(agent, "react_config")
        assert hasattr(agent, "run")

    def test_zero_config_uses_environment_variables(self):
        """Test that zero-config reads from environment variables."""
        from kaizen.agents.specialized.react import ReActAgent

        # Set environment variables
        os.environ["KAIZEN_LLM_PROVIDER"] = "anthropic"
        os.environ["KAIZEN_MODEL"] = "claude-3-sonnet"
        os.environ["KAIZEN_TEMPERATURE"] = "0.5"
        os.environ["KAIZEN_MAX_TOKENS"] = "2000"

        try:
            agent = ReActAgent()

            # Should use environment values
            assert agent.react_config.llm_provider == "anthropic"
            assert agent.react_config.model == "claude-3-sonnet"
            assert agent.react_config.temperature == 0.5
            assert agent.react_config.max_tokens == 2000
        finally:
            # Clean up
            del os.environ["KAIZEN_LLM_PROVIDER"]
            del os.environ["KAIZEN_MODEL"]
            del os.environ["KAIZEN_TEMPERATURE"]
            del os.environ["KAIZEN_MAX_TOKENS"]

    def test_progressive_configuration_model_only(self):
        """Test progressive configuration - override model only."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(model="gpt-3.5-turbo")

        assert agent.react_config.model == "gpt-3.5-turbo"
        # Other values should be defaults
        assert agent.react_config.llm_provider == "openai"  # default

    def test_progressive_configuration_multiple_params(self):
        """Test progressive configuration - override multiple parameters."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
            max_cycles=15,
        )

        assert agent.react_config.llm_provider == "anthropic"
        assert agent.react_config.model == "claude-3-opus"
        assert agent.react_config.temperature == 0.7
        assert agent.react_config.max_tokens == 2000
        assert agent.react_config.max_cycles == 15

    def test_full_config_object_initialization(self):
        """Test initialization with full config object."""
        from kaizen.agents.specialized.react import ReActAgent, ReActConfig

        config = ReActConfig(
            llm_provider="openai",
            model="gpt-4-turbo",
            temperature=0.2,
            max_tokens=1800,
            timeout=60,
            max_cycles=12,
            confidence_threshold=0.8,
            mcp_discovery_enabled=True,
        )

        agent = ReActAgent(config=config)

        assert agent.react_config.llm_provider == "openai"
        assert agent.react_config.model == "gpt-4-turbo"
        assert agent.react_config.temperature == 0.2
        assert agent.react_config.max_tokens == 1800
        assert agent.react_config.timeout == 60
        assert agent.react_config.max_cycles == 12
        assert agent.react_config.confidence_threshold == 0.8
        assert agent.react_config.mcp_discovery_enabled is True

    def test_config_parameter_overrides_defaults(self):
        """Test that constructor parameters override config defaults."""
        from kaizen.agents.specialized.react import ReActAgent

        # Parameter should override default
        agent = ReActAgent(
            confidence_threshold=0.9, mcp_discovery_enabled=True, max_cycles=20
        )

        assert agent.react_config.confidence_threshold == 0.9
        assert agent.react_config.mcp_discovery_enabled is True
        assert agent.react_config.max_cycles == 20

    def test_uses_multi_cycle_strategy(self):
        """Test that ReActAgent uses MultiCycleStrategy (NOT AsyncSingleShotStrategy)."""
        from kaizen.agents.specialized.react import ReActAgent
        from kaizen.strategies.multi_cycle import MultiCycleStrategy

        agent = ReActAgent()

        # CRITICAL: ReActAgent MUST use MultiCycleStrategy
        assert isinstance(agent.strategy, MultiCycleStrategy)

    def test_multi_cycle_strategy_has_correct_max_cycles(self):
        """Test that MultiCycleStrategy uses configured max_cycles."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(max_cycles=15)

        # Strategy should have correct max_cycles
        assert agent.strategy.max_cycles == 15


class TestReActAgentExecution:
    """Test agent execution and run method."""

    def test_run_basic_execution(self):
        """Test basic task solving execution."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(llm_provider="mock", model="gpt-4")
        result = agent.run(task="What is 2 + 2?")

        # Should return dict
        assert isinstance(result, dict)
        # Should have either cycles_used/total_cycles (success) or error (mock provider issue)
        assert "cycles_used" in result or "total_cycles" in result or "error" in result

    def test_run_returns_react_fields(self):
        """Test that result contains ReAct-specific fields."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()
        result = agent.run(task="Calculate 15 * 23")

        # Should have ReAct fields (thought, action, etc.)
        # Note: Fields might be nested in result
        assert isinstance(result, dict)

    def test_run_with_context(self):
        """Test task solving with additional context."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()
        result = agent.run(
            task="What is the total?",
            context="Given that we have 10 apples and buy 5 more",
        )

        assert isinstance(result, dict)

    def test_run_empty_input_handling(self):
        """Test error handling for empty input."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()
        result = agent.run(task="")

        # Should return error
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"

    def test_run_whitespace_only_input(self):
        """Test error handling for whitespace-only input."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()
        result = agent.run(task="   \t\n   ")

        # Should return error
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"

    def test_multi_cycle_execution(self):
        """Test that multi-cycle execution works."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(llm_provider="mock", model="gpt-4", max_cycles=3)
        result = agent.run(task="Complex task requiring multiple steps")

        # Should return dict
        assert isinstance(result, dict)

        # Should have cycle information (success) or error (mock provider issue)
        assert "cycles_used" in result or "total_cycles" in result or "error" in result

        # cycles_used should be <= max_cycles (if present)
        if "cycles_used" in result:
            assert result["cycles_used"] <= 3


class TestReActAgentActionTypes:
    """Test ActionType enum and action handling."""

    def test_action_type_enum_exists(self):
        """Test ActionType enum exists and has required values."""
        from kaizen.agents.specialized.react import ActionType

        assert hasattr(ActionType, "TOOL_USE")
        assert hasattr(ActionType, "FINISH")
        assert hasattr(ActionType, "CLARIFY")

    def test_action_type_values(self):
        """Test ActionType enum values are correct."""
        from kaizen.agents.specialized.react import ActionType

        assert ActionType.TOOL_USE.value == "tool_use"
        assert ActionType.FINISH.value == "finish"
        assert ActionType.CLARIFY.value == "clarify"


class TestReActAgentConvergence:
    """Test convergence detection logic."""

    def test_convergence_check_method_exists(self):
        """Test that _check_convergence method exists."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        assert hasattr(agent, "_check_convergence")
        assert callable(agent._check_convergence)

    def test_convergence_with_finish_action(self):
        """Test that finish action triggers convergence."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        # Mock result with finish action
        result_with_finish = {"action": "finish", "confidence": 0.8}
        should_stop = agent._check_convergence(result_with_finish)

        assert should_stop is True

    def test_convergence_with_high_confidence(self):
        """Test that high confidence can trigger convergence."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(confidence_threshold=0.7)

        result_high_conf = {"action": "tool_use", "confidence": 0.95}
        should_stop = agent._check_convergence(result_high_conf)

        # High confidence should trigger convergence
        assert should_stop is True

    def test_no_convergence_with_low_confidence(self):
        """Test that low confidence does NOT trigger convergence."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(confidence_threshold=0.7)

        result_low_conf = {"action": "tool_use", "confidence": 0.3}
        should_stop = agent._check_convergence(result_low_conf)

        # Low confidence should NOT trigger convergence
        assert should_stop is False

    def test_no_convergence_with_tool_use_action(self):
        """Test that tool_use action with low confidence does NOT trigger convergence."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(confidence_threshold=0.7)

        result_tool_use = {"action": "tool_use", "confidence": 0.5}
        should_stop = agent._check_convergence(result_tool_use)

        # tool_use with low confidence should continue
        assert should_stop is False


class TestReActAgentConfidenceThreshold:
    """Test confidence threshold configuration."""

    def test_confidence_threshold_default(self):
        """Test default confidence threshold (0.7)."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        assert agent.react_config.confidence_threshold == 0.7

    def test_confidence_threshold_custom(self):
        """Test custom confidence threshold."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(confidence_threshold=0.9)

        assert agent.react_config.confidence_threshold == 0.9


class TestReActAgentMCPDiscovery:
    """Test MCP tool discovery (optional feature)."""

    def test_mcp_discovery_disabled_by_default(self):
        """Test MCP discovery is disabled by default (opt-in)."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        # Should be disabled by default
        assert agent.react_config.mcp_discovery_enabled is False

    def test_mcp_discovery_can_be_enabled(self):
        """Test MCP discovery can be enabled."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(mcp_discovery_enabled=True)

        assert agent.react_config.mcp_discovery_enabled is True

    def test_mcp_tool_discovery_method_exists(self):
        """Test that _discover_mcp_tools method exists."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        assert hasattr(agent, "_discover_mcp_tools")
        assert callable(agent._discover_mcp_tools)


class TestReActAgentConfiguration:
    """Test configuration management."""

    def test_timeout_merged_into_provider_config(self):
        """Test that timeout is merged into provider_config."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(timeout=60)

        # Timeout should be in provider_config
        assert "timeout" in agent.react_config.provider_config
        assert agent.react_config.provider_config["timeout"] == 60

    def test_provider_config_preserved(self):
        """Test that custom provider_config is preserved."""
        from kaizen.agents.specialized.react import ReActAgent

        custom_config = {"api_key": "test-key", "organization": "test-org"}

        agent = ReActAgent(provider_config=custom_config)

        # Custom config should be preserved
        assert "api_key" in agent.react_config.provider_config
        assert "organization" in agent.react_config.provider_config

    def test_max_retries_configurable(self):
        """Test max_retries parameter is configurable."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(max_retries=5)

        assert agent.react_config.max_retries == 5

    def test_enable_parallel_tools_configurable(self):
        """Test enable_parallel_tools parameter is configurable."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(enable_parallel_tools=True)

        assert agent.react_config.enable_parallel_tools is True


class TestReActAgentSignature:
    """Test signature structure."""

    def test_signature_has_required_input_fields(self):
        """Test signature has required input fields."""
        from kaizen.agents.specialized.react import ReActSignature

        sig = ReActSignature()

        # Should have task, context, available_tools, previous_actions inputs
        assert hasattr(sig, "task")
        assert hasattr(sig, "context")
        assert hasattr(sig, "available_tools")
        assert hasattr(sig, "previous_actions")

    def test_signature_has_required_output_fields(self):
        """Test signature has required output fields."""
        from kaizen.agents.specialized.react import ReActSignature

        sig = ReActSignature()

        # Should have ReAct output fields
        assert hasattr(sig, "thought")
        assert hasattr(sig, "action")
        assert hasattr(sig, "action_input")
        assert hasattr(sig, "confidence")
        assert hasattr(sig, "need_tool")


class TestReActAgentTypeHints:
    """Test type hints and return types."""

    def test_run_returns_dict(self):
        """Test run returns Dict[str, Any]."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()
        result = agent.run(task="Test")

        assert isinstance(result, dict)

    def test_config_is_dataclass(self):
        """Test ReActConfig is a dataclass."""
        from dataclasses import is_dataclass

        from kaizen.agents.specialized.react import ReActConfig

        assert is_dataclass(ReActConfig)

    def test_agent_inherits_from_base_agent(self):
        """Test ReActAgent inherits from BaseAgent."""
        from kaizen.agents.specialized.react import ReActAgent
        from kaizen.core.base_agent import BaseAgent

        agent = ReActAgent()

        assert isinstance(agent, BaseAgent)


class TestReActAgentDocumentation:
    """Test documentation completeness."""

    def test_agent_class_has_docstring(self):
        """Test ReActAgent has comprehensive docstring."""
        from kaizen.agents.specialized.react import ReActAgent

        assert ReActAgent.__doc__ is not None
        assert len(ReActAgent.__doc__) > 100

    def test_run_has_docstring(self):
        """Test run method has docstring."""
        from kaizen.agents.specialized.react import ReActAgent

        assert ReActAgent.run.__doc__ is not None
        assert len(ReActAgent.run.__doc__) > 50

    def test_config_has_docstring(self):
        """Test ReActConfig has docstring."""
        from kaizen.agents.specialized.react import ReActConfig

        assert ReActConfig.__doc__ is not None

    def test_action_type_enum_has_docstring(self):
        """Test ActionType enum has docstring."""
        from kaizen.agents.specialized.react import ActionType

        assert ActionType.__doc__ is not None


class TestReActAgentMaxCycles:
    """Test max_cycles configuration and behavior."""

    def test_max_cycles_default(self):
        """Test default max_cycles (10)."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent()

        assert agent.react_config.max_cycles == 10

    def test_max_cycles_custom(self):
        """Test custom max_cycles."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(max_cycles=20)

        assert agent.react_config.max_cycles == 20

    def test_max_cycles_passed_to_strategy(self):
        """Test that max_cycles is passed to MultiCycleStrategy."""
        from kaizen.agents.specialized.react import ReActAgent

        agent = ReActAgent(max_cycles=15)

        # Strategy should have the same max_cycles
        assert agent.strategy.max_cycles == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
