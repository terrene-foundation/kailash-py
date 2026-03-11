"""
Test ChainOfThoughtAgent - Production-Ready Library Agent

Tests zero-config initialization, progressive configuration,
and step-by-step reasoning capabilities.

Written BEFORE implementation (TDD).
"""

import os

import pytest

# Import will work after implementation
# from kaizen.agents.specialized.chain_of_thought import (
#     ChainOfThoughtAgent,
#     ChainOfThoughtConfig,
#     ChainOfThoughtSignature
# )


class TestChainOfThoughtAgentInitialization:
    """Test agent initialization patterns."""

    def test_zero_config_initialization(self):
        """Test agent works with zero configuration (most important test)."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        # Should work with no parameters
        agent = ChainOfThoughtAgent(llm_provider="mock")

        assert agent is not None
        assert hasattr(agent, "cot_config")
        assert hasattr(agent, "run")

    def test_zero_config_uses_environment_variables(self):
        """Test that zero-config reads from environment variables."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        # Set environment variables - use mock provider for testing
        os.environ["KAIZEN_LLM_PROVIDER"] = "mock"
        os.environ["KAIZEN_MODEL"] = "claude-3-sonnet"
        os.environ["KAIZEN_TEMPERATURE"] = "0.5"
        os.environ["KAIZEN_MAX_TOKENS"] = "2000"

        try:
            # Create agent without explicit llm_provider - should use env vars
            agent = ChainOfThoughtAgent()

            # Should use environment values
            assert agent.cot_config.llm_provider == "mock"
            assert agent.cot_config.model == "claude-3-sonnet"
            assert agent.cot_config.temperature == 0.5
            assert agent.cot_config.max_tokens == 2000
        finally:
            # Clean up
            del os.environ["KAIZEN_LLM_PROVIDER"]
            del os.environ["KAIZEN_MODEL"]
            del os.environ["KAIZEN_TEMPERATURE"]
            del os.environ["KAIZEN_MAX_TOKENS"]

    def test_progressive_configuration_model_only(self):
        """Test progressive configuration - override model only."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(model="gpt-3.5-turbo")

        assert agent.cot_config.model == "gpt-3.5-turbo"
        # Other values should be defaults
        assert agent.cot_config.llm_provider == "openai"  # default

    def test_progressive_configuration_multiple_params(self):
        """Test progressive configuration - override multiple parameters."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
        )

        assert agent.cot_config.llm_provider == "anthropic"
        assert agent.cot_config.model == "claude-3-opus"
        assert agent.cot_config.temperature == 0.7
        assert agent.cot_config.max_tokens == 2000

    def test_full_config_object_initialization(self):
        """Test initialization with full config object."""
        from kaizen.agents.specialized.chain_of_thought import (
            ChainOfThoughtAgent,
            ChainOfThoughtConfig,
        )

        config = ChainOfThoughtConfig(
            llm_provider="openai",
            model="gpt-4-turbo",
            temperature=0.2,
            max_tokens=1800,
            timeout=60,
            reasoning_steps=7,
            confidence_threshold=0.8,
        )

        agent = ChainOfThoughtAgent(config=config)

        assert agent.cot_config.llm_provider == "openai"
        assert agent.cot_config.model == "gpt-4-turbo"
        assert agent.cot_config.temperature == 0.2
        assert agent.cot_config.max_tokens == 1800
        assert agent.cot_config.timeout == 60
        assert agent.cot_config.reasoning_steps == 7
        assert agent.cot_config.confidence_threshold == 0.8

    def test_config_parameter_overrides_defaults(self):
        """Test that constructor parameters override config defaults."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        # Parameter should override default
        agent = ChainOfThoughtAgent(confidence_threshold=0.9, enable_verification=False)

        assert agent.cot_config.confidence_threshold == 0.9
        assert agent.cot_config.enable_verification is False


class TestChainOfThoughtAgentExecution:
    """Test agent execution and run method."""

    def test_run_basic_execution(self):
        """Test basic problem solving execution."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(problem="What is 2 + 2?")

        # Should return dict with required fields
        assert isinstance(result, dict)
        assert "final_answer" in result
        assert "confidence" in result

    def test_run_returns_all_steps(self):
        """Test that result contains all reasoning steps."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(problem="Calculate 15 * 23")

        # Should have all 5 steps plus final answer
        assert "step1" in result
        assert "step2" in result
        assert "step3" in result
        assert "step4" in result
        assert "step5" in result
        assert "final_answer" in result
        assert "confidence" in result

    def test_run_with_context(self):
        """Test problem solving with additional context."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(
            problem="What is the total?",
            context="Given that we have 10 apples and buy 5 more",
        )

        assert isinstance(result, dict)
        assert "final_answer" in result

    def test_run_empty_input_handling(self):
        """Test error handling for empty input."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(problem="")

        # Should return error
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"
        assert result["confidence"] == 0.0

    def test_run_whitespace_only_input(self):
        """Test error handling for whitespace-only input."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(problem="   \t\n   ")

        # Should return error
        assert "error" in result
        assert result["error"] == "INVALID_INPUT"


class TestChainOfThoughtAgentConfidenceThreshold:
    """Test confidence threshold validation."""

    def test_confidence_threshold_default(self):
        """Test default confidence threshold (0.7)."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")

        assert agent.cot_config.confidence_threshold == 0.7

    def test_confidence_threshold_custom(self):
        """Test custom confidence threshold."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(confidence_threshold=0.9)

        assert agent.cot_config.confidence_threshold == 0.9

    def test_low_confidence_warning(self):
        """Test that low confidence results include warning."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(confidence_threshold=0.9)
        result = agent.run(problem="Simple test problem")

        # If confidence < 0.9, should have warning
        confidence = result.get("confidence", 0)
        if confidence < 0.9:
            assert "warning" in result
            assert "Low confidence" in result["warning"]

    def test_high_confidence_no_warning(self):
        """Test that high confidence results have no warning."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(confidence_threshold=0.3)
        result = agent.run(problem="What is 1+1?")

        # If confidence >= 0.3, should not have warning (or warning should be absent)
        confidence = result.get("confidence", 0)
        if confidence >= 0.3:
            # Warning might not be present, or might be empty
            if "warning" in result:
                assert (
                    result["warning"] == "" or "Low confidence" not in result["warning"]
                )


class TestChainOfThoughtAgentVerification:
    """Test verification flag behavior."""

    def test_verification_enabled_by_default(self):
        """Test verification is enabled by default."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")

        assert agent.cot_config.enable_verification is True

    def test_verification_disabled(self):
        """Test verification can be disabled."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(enable_verification=False)

        assert agent.cot_config.enable_verification is False

    def test_verification_flag_in_result_when_enabled(self):
        """Test verification flag appears in result when enabled."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(enable_verification=True)
        result = agent.run(problem="Test problem")

        # Should have verified flag when enabled
        assert "verified" in result
        assert isinstance(result["verified"], bool)

    def test_verification_flag_absent_when_disabled(self):
        """Test verification flag absent when disabled."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(enable_verification=False)
        result = agent.run(problem="Test problem")

        # Should NOT have verified flag when disabled
        assert "verified" not in result

    def test_verification_true_when_confidence_high(self):
        """Test verification is True when confidence meets threshold."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(enable_verification=True, confidence_threshold=0.5)
        result = agent.run(problem="What is 2+2?")

        # If confidence >= threshold, verified should be True
        confidence = result.get("confidence", 0)
        if confidence >= 0.5:
            assert result.get("verified") is True

    def test_verification_false_when_confidence_low(self):
        """Test verification is False when confidence below threshold."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(
            enable_verification=True, confidence_threshold=0.99  # Very high threshold
        )
        result = agent.run(problem="Complex uncertain problem")

        # If confidence < threshold, verified should be False
        confidence = result.get("confidence", 0)
        if confidence < 0.99:
            assert result.get("verified") is False


class TestChainOfThoughtAgentConfiguration:
    """Test configuration management."""

    def test_timeout_merged_into_provider_config(self):
        """Test that timeout is merged into provider_config."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(timeout=60)

        # Timeout should be in provider_config
        assert "timeout" in agent.cot_config.provider_config
        assert agent.cot_config.provider_config["timeout"] == 60

    def test_provider_config_preserved(self):
        """Test that custom provider_config is preserved."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        custom_config = {"api_key": "test-key", "organization": "test-org"}

        agent = ChainOfThoughtAgent(provider_config=custom_config)

        # Custom config should be preserved
        assert "api_key" in agent.cot_config.provider_config
        assert "organization" in agent.cot_config.provider_config

    def test_reasoning_steps_configurable(self):
        """Test reasoning_steps parameter is configurable."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(reasoning_steps=7)

        assert agent.cot_config.reasoning_steps == 7

    def test_retry_attempts_configurable(self):
        """Test retry_attempts parameter is configurable."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(retry_attempts=5)

        assert agent.cot_config.retry_attempts == 5


class TestChainOfThoughtAgentSignature:
    """Test signature structure."""

    def test_signature_has_required_input_fields(self):
        """Test signature has required input fields."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtSignature

        sig = ChainOfThoughtSignature()

        # Should have problem and context inputs
        assert hasattr(sig, "problem")
        assert hasattr(sig, "context")

    def test_signature_has_required_output_fields(self):
        """Test signature has required output fields."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtSignature

        sig = ChainOfThoughtSignature()

        # Should have all step outputs
        assert hasattr(sig, "step1")
        assert hasattr(sig, "step2")
        assert hasattr(sig, "step3")
        assert hasattr(sig, "step4")
        assert hasattr(sig, "step5")
        assert hasattr(sig, "final_answer")
        assert hasattr(sig, "confidence")


class TestChainOfThoughtAgentTypeHints:
    """Test type hints and return types."""

    def test_run_returns_dict(self):
        """Test run returns Dict[str, Any]."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")
        result = agent.run(problem="Test")

        assert isinstance(result, dict)

    def test_config_is_dataclass(self):
        """Test ChainOfThoughtConfig is a dataclass."""
        from dataclasses import is_dataclass

        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig

        assert is_dataclass(ChainOfThoughtConfig)

    def test_agent_inherits_from_base_agent(self):
        """Test ChainOfThoughtAgent inherits from BaseAgent."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent
        from kaizen.core.base_agent import BaseAgent

        agent = ChainOfThoughtAgent(llm_provider="mock")

        assert isinstance(agent, BaseAgent)


class TestChainOfThoughtAgentDocumentation:
    """Test documentation completeness."""

    def test_agent_class_has_docstring(self):
        """Test ChainOfThoughtAgent has comprehensive docstring."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        assert ChainOfThoughtAgent.__doc__ is not None
        assert len(ChainOfThoughtAgent.__doc__) > 100

    def test_run_has_docstring(self):
        """Test run method has docstring."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent

        assert ChainOfThoughtAgent.run.__doc__ is not None
        assert len(ChainOfThoughtAgent.run.__doc__) > 50

    def test_config_has_docstring(self):
        """Test ChainOfThoughtConfig has docstring."""
        from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtConfig

        assert ChainOfThoughtConfig.__doc__ is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
