"""
Test Template for Kaizen Agents

Use this template to create comprehensive tests for new agents.
Based on ReAct's successful 42-test structure.

INSTRUCTIONS:
1. Copy this file to tests/unit/agents/{category}/test_{agent_name}.py
2. Replace ALL {AgentName} with your agent class name (e.g., "SimpleQA", "ReAct")
3. Replace ALL {agent_name} with lowercase version (e.g., "simple_qa", "react")
4. Replace ALL {main_method} with your agent's main method (e.g., "ask", "solve", "execute")
5. Replace ALL {signature_input} with your signature's input field name
6. Replace ALL {signature_output} with your signature's output field name
7. Add/remove test classes based on agent features (see comments)
8. Write ALL tests BEFORE implementation (TDD)

MINIMUM: 30 tests across 6+ test classes
TARGET: 40+ tests for comprehensive coverage
"""

import os
from typing import Any, Dict

import pytest

# ============================================================================
# TEST CLASS 1: Initialization (REQUIRED - 5-8 tests)
# ============================================================================

class Test{AgentName}Initialization:
    """Test agent initialization patterns."""

    def test_zero_config_initialization(self):
        """Test agent works with zero configuration (CRITICAL TEST)."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        # Should work with no parameters
        agent = {AgentName}()

        assert agent is not None
        assert hasattr(agent, '{agent_name}_config')
        assert hasattr(agent, '{main_method}')

    def test_zero_config_uses_environment_variables(self):
        """Test that zero-config reads from environment variables."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        # Set environment variables
        os.environ['KAIZEN_LLM_PROVIDER'] = 'anthropic'
        os.environ['KAIZEN_MODEL'] = 'claude-3-sonnet'
        os.environ['KAIZEN_TEMPERATURE'] = '0.5'
        os.environ['KAIZEN_MAX_TOKENS'] = '2000'

        try:
            agent = {AgentName}()

            # Should use environment values
            assert agent.{agent_name}_config.llm_provider == 'anthropic'
            assert agent.{agent_name}_config.model == 'claude-3-sonnet'
            assert agent.{agent_name}_config.temperature == 0.5
            assert agent.{agent_name}_config.max_tokens == 2000
        finally:
            # Clean up environment variables
            del os.environ['KAIZEN_LLM_PROVIDER']
            del os.environ['KAIZEN_MODEL']
            del os.environ['KAIZEN_TEMPERATURE']
            del os.environ['KAIZEN_MAX_TOKENS']

    def test_progressive_configuration_model_only(self):
        """Test progressive configuration - override model only."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(model="gpt-3.5-turbo")

        assert agent.{agent_name}_config.model == "gpt-3.5-turbo"
        # Other values should be defaults
        assert agent.{agent_name}_config.llm_provider == "openai"  # default

    def test_progressive_configuration_multiple_params(self):
        """Test progressive configuration - override multiple parameters."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(
            llm_provider="anthropic",
            model="claude-3-opus",
            temperature=0.7,
            max_tokens=2000,
            # Add domain-specific params here
        )

        assert agent.{agent_name}_config.llm_provider == "anthropic"
        assert agent.{agent_name}_config.model == "claude-3-opus"
        assert agent.{agent_name}_config.temperature == 0.7
        assert agent.{agent_name}_config.max_tokens == 2000
        # Assert domain-specific params

    def test_full_config_object_initialization(self):
        """Test initialization with full config object."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}, {AgentName}Config

        config = {AgentName}Config(
            llm_provider="openai",
            model="gpt-4-turbo",
            temperature=0.2,
            max_tokens=1800,
            timeout=60,
            # Add domain-specific params
        )

        agent = {AgentName}(config=config)

        assert agent.{agent_name}_config.llm_provider == "openai"
        assert agent.{agent_name}_config.model == "gpt-4-turbo"
        assert agent.{agent_name}_config.temperature == 0.2

    def test_config_object_overrides_kwargs(self):
        """Test that config object takes precedence over kwargs."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}, {AgentName}Config

        config = {AgentName}Config(
            model="gpt-4",
            temperature=0.3
        )

        # Kwargs should be ignored when config is provided
        agent = {AgentName}(
            config=config,
            model="gpt-3.5-turbo",  # Should be ignored
            temperature=0.9  # Should be ignored
        )

        assert agent.{agent_name}_config.model == "gpt-4"
        assert agent.{agent_name}_config.temperature == 0.3

    def test_default_configuration_values(self):
        """Test that defaults are set correctly."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # LLM defaults
        assert agent.{agent_name}_config.llm_provider == "openai"
        assert agent.{agent_name}_config.model == "gpt-4"
        assert isinstance(agent.{agent_name}_config.temperature, float)
        assert isinstance(agent.{agent_name}_config.max_tokens, int)

        # Technical defaults
        assert agent.{agent_name}_config.timeout == 30
        assert agent.{agent_name}_config.retry_attempts == 3
        assert isinstance(agent.{agent_name}_config.provider_config, dict)

    def test_timeout_merged_into_provider_config(self):
        """Test that timeout is merged into provider_config."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(timeout=60)

        # Timeout should be in provider_config
        assert 'timeout' in agent.{agent_name}_config.provider_config
        assert agent.{agent_name}_config.provider_config['timeout'] == 60


# ============================================================================
# TEST CLASS 2: Execution (REQUIRED - 8-12 tests)
# ============================================================================

class Test{AgentName}Execution:
    """Test agent execution and behavior."""

    def test_main_method_exists(self):
        """Test that main convenience method exists."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        assert hasattr(agent, '{main_method}')
        assert callable(getattr(agent, '{main_method}'))

    def test_main_method_returns_dict(self):
        """Test that main method returns a dictionary."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # NOTE: This will fail until implementation is complete
        # Temporarily skip or mock if needed during TDD
        result = agent.{main_method}("test input")

        assert isinstance(result, dict)

    def test_main_method_has_expected_output_fields(self):
        """Test that output contains expected signature fields."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        result = agent.{main_method}("test input")

        # Check for signature output fields
        assert '{signature_output}' in result
        # Add more output field assertions

    def test_main_method_accepts_required_inputs(self):
        """Test that main method accepts required signature inputs."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # Should accept required input parameter
        result = agent.{main_method}({signature_input}="test value")

        assert result is not None
        assert isinstance(result, dict)

    def test_run_method_integration(self):
        """Test that agent.run() method works (inherited from BaseAgent)."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # Direct call to BaseAgent.run()
        result = agent.run({signature_input}="test value")

        assert isinstance(result, dict)
        assert '{signature_output}' in result

    def test_execution_with_different_inputs(self):
        """Test execution with various input types."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # Test with different inputs
        test_cases = [
            "simple input",
            "complex multi-word input",
            "input with special characters!?",
            # Add more test cases
        ]

        for test_input in test_cases:
            result = agent.{main_method}(test_input)
            assert isinstance(result, dict)
            assert '{signature_output}' in result

    def test_execution_performance(self):
        """Test that execution completes in reasonable time."""
        import time

        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        start = time.time()
        result = agent.{main_method}("test input")
        duration = time.time() - start

        # Should complete in less than 30 seconds (mocked execution is fast)
        assert duration < 30
        assert result is not None

    # Add 4-5 more execution tests specific to your agent's behavior


# ============================================================================
# TEST CLASS 3: Configuration (REQUIRED - 5-8 tests)
# ============================================================================

class Test{AgentName}Configuration:
    """Test configuration class and behavior."""

    def test_config_class_exists(self):
        """Test that configuration class exists."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        assert {AgentName}Config is not None

    def test_config_is_dataclass(self):
        """Test that config uses dataclass decorator."""
        import dataclasses

        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        assert dataclasses.is_dataclass({AgentName}Config)

    def test_config_has_required_llm_fields(self):
        """Test that config has required LLM fields."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        config = {AgentName}Config()

        assert hasattr(config, 'llm_provider')
        assert hasattr(config, 'model')
        assert hasattr(config, 'temperature')
        assert hasattr(config, 'max_tokens')

    def test_config_has_required_technical_fields(self):
        """Test that config has required technical fields."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        config = {AgentName}Config()

        assert hasattr(config, 'timeout')
        assert hasattr(config, 'retry_attempts')
        assert hasattr(config, 'provider_config')

    def test_config_environment_variable_defaults(self):
        """Test that config reads from environment variables."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        os.environ['KAIZEN_MODEL'] = 'test-model'

        try:
            config = {AgentName}Config()
            assert config.model == 'test-model'
        finally:
            del os.environ['KAIZEN_MODEL']

    def test_config_can_be_instantiated_with_custom_values(self):
        """Test that config accepts custom values."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        config = {AgentName}Config(
            llm_provider="custom_provider",
            model="custom_model",
            temperature=0.123,
            max_tokens=999,
            # Add domain-specific params
        )

        assert config.llm_provider == "custom_provider"
        assert config.model == "custom_model"
        assert config.temperature == 0.123
        assert config.max_tokens == 999

    def test_config_provider_config_is_dict(self):
        """Test that provider_config is initialized as dict."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        config = {AgentName}Config()

        assert isinstance(config.provider_config, dict)

    # Add domain-specific configuration tests


# ============================================================================
# TEST CLASS 4: Signature (REQUIRED - 3-5 tests)
# ============================================================================

class Test{AgentName}Signature:
    """Test signature definition and structure."""

    def test_signature_class_exists(self):
        """Test that signature class exists."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature

        assert {AgentName}Signature is not None

    def test_signature_inherits_from_base(self):
        """Test that signature inherits from Signature base class."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature
        from kaizen.signatures import Signature

        assert issubclass({AgentName}Signature, Signature)

    def test_signature_has_input_fields(self):
        """Test that signature has defined input fields."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature

        sig = {AgentName}Signature()

        # Check for input fields
        assert hasattr(sig, '{signature_input}')
        # Add more input field checks

    def test_signature_has_output_fields(self):
        """Test that signature has defined output fields."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature

        sig = {AgentName}Signature()

        # Check for output fields
        assert hasattr(sig, '{signature_output}')
        # Add more output field checks

    def test_signature_field_types(self):
        """Test that signature fields have correct types."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature
        from kaizen.signatures import InputField, OutputField

        sig = {AgentName}Signature()

        # Check field types (this is schema-based, adjust as needed)
        # Example:
        # assert isinstance(sig.{signature_input}, InputField)
        # assert isinstance(sig.{signature_output}, OutputField)


# ============================================================================
# TEST CLASS 5: Error Handling (REQUIRED - 3-5 tests)
# ============================================================================

class Test{AgentName}ErrorHandling:
    """Test error handling and edge cases."""

    def test_empty_input_handling(self):
        """Test handling of empty input."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # Should handle empty input gracefully
        result = agent.{main_method}("")

        assert isinstance(result, dict)
        # Should have error indicator or empty result
        assert 'error' in result or result.get('{signature_output}') == ""

    def test_none_input_handling(self):
        """Test handling of None input."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # Should handle None input gracefully
        # May raise TypeError or return error dict
        try:
            result = agent.{main_method}(None)
            assert isinstance(result, dict)
            assert 'error' in result
        except TypeError:
            # Acceptable to raise TypeError for None
            pass

    def test_invalid_config_handling(self):
        """Test handling of invalid configuration values."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        # Test with invalid temperature (negative)
        try:
            agent = {AgentName}(temperature=-1.0)
            # If it doesn't raise, it should clamp or handle gracefully
            assert agent.{agent_name}_config.temperature >= 0
        except ValueError:
            # Acceptable to raise ValueError for invalid config
            pass

    def test_missing_required_parameters(self):
        """Test behavior when required parameters are missing."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        # If signature has required fields without defaults, test missing param
        # This depends on your signature structure
        # Example:
        # with pytest.raises(TypeError):
        #     result = agent.run()  # Missing required parameter


# ============================================================================
# TEST CLASS 6: Documentation (REQUIRED - 2-3 tests)
# ============================================================================

class Test{AgentName}Documentation:
    """Test docstrings and documentation completeness."""

    def test_agent_class_has_docstring(self):
        """Test that agent class has docstring."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        assert {AgentName}.__doc__ is not None
        assert len({AgentName}.__doc__) > 50  # Substantial docstring

    def test_main_method_has_docstring(self):
        """Test that main method has docstring."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        assert {AgentName}.{main_method}.__doc__ is not None
        assert len({AgentName}.{main_method}.__doc__) > 20

    def test_config_class_has_docstring(self):
        """Test that config class has docstring."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Config

        assert {AgentName}Config.__doc__ is not None

    def test_signature_class_has_docstring(self):
        """Test that signature class has docstring."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}Signature

        assert {AgentName}Signature.__doc__ is not None


# ============================================================================
# TEST CLASS 7: Type Hints (REQUIRED - 2-3 tests)
# ============================================================================

class Test{AgentName}TypeHints:
    """Test type hint completeness."""

    def test_main_method_has_type_hints(self):
        """Test that main method has type hints."""
        import inspect

        from kaizen.agents.{category}.{agent_name} import {AgentName}

        sig = inspect.signature({AgentName}.{main_method})

        # Check return type hint
        assert sig.return_annotation != inspect.Parameter.empty

        # Check parameter type hints
        for param_name, param in sig.parameters.items():
            if param_name != 'self':
                # Parameters should have type hints
                assert param.annotation != inspect.Parameter.empty

    def test_init_method_has_type_hints(self):
        """Test that __init__ has type hints."""
        import inspect

        from kaizen.agents.{category}.{agent_name} import {AgentName}

        sig = inspect.signature({AgentName}.__init__)

        # Check parameter type hints (most should have hints)
        params_with_hints = 0
        total_params = 0

        for param_name, param in sig.parameters.items():
            if param_name not in ['self', 'kwargs']:
                total_params += 1
                if param.annotation != inspect.Parameter.empty:
                    params_with_hints += 1

        # At least 80% of parameters should have type hints
        if total_params > 0:
            hint_percentage = params_with_hints / total_params
            assert hint_percentage >= 0.8


# ============================================================================
# OPTIONAL TEST CLASSES (Add based on agent features)
# ============================================================================

# ----------------------------------------------------------------------------
# If agent uses MultiCycleStrategy:
# ----------------------------------------------------------------------------
class Test{AgentName}MultiCycle:
    """Test multi-cycle strategy behavior (DELETE IF NOT APPLICABLE)."""

    def test_uses_multi_cycle_strategy(self):
        """Test that agent uses MultiCycleStrategy."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        from kailash.strategies.multi_cycle import MultiCycleStrategy

        agent = {AgentName}()

        assert agent.strategy is not None
        assert isinstance(agent.strategy, MultiCycleStrategy)

    def test_max_cycles_configuration(self):
        """Test that max_cycles can be configured."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(max_cycles=20)

        assert agent.{agent_name}_config.max_cycles == 20

    def test_convergence_check_method_exists(self):
        """Test that convergence check method exists."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        assert hasattr(agent, '_check_convergence')
        assert callable(agent._check_convergence)

    # Add more multi-cycle specific tests


# ----------------------------------------------------------------------------
# If agent uses Memory:
# ----------------------------------------------------------------------------
class Test{AgentName}Memory:
    """Test memory integration (DELETE IF NOT APPLICABLE)."""

    def test_memory_disabled_by_default(self):
        """Test that memory is disabled by default (opt-in)."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        assert agent.memory is None

    def test_memory_enabled_with_config(self):
        """Test that memory can be enabled via configuration."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(max_turns=10)  # Or whatever param enables memory

        assert agent.memory is not None

    # Add more memory-specific tests


# ----------------------------------------------------------------------------
# If agent uses MCP Tools:
# ----------------------------------------------------------------------------
class Test{AgentName}MCPTools:
    """Test MCP tool integration (DELETE IF NOT APPLICABLE)."""

    def test_mcp_discovery_disabled_by_default(self):
        """Test that MCP discovery is disabled by default."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}()

        assert agent.{agent_name}_config.mcp_discovery_enabled is False

    def test_mcp_discovery_can_be_enabled(self):
        """Test that MCP discovery can be enabled."""
        from kaizen.agents.{category}.{agent_name} import {AgentName}

        agent = {AgentName}(mcp_discovery_enabled=True)

        assert agent.{agent_name}_config.mcp_discovery_enabled is True

    # Add more MCP-specific tests


# ============================================================================
# DOMAIN-SPECIFIC TEST CLASSES
# ============================================================================

# Add test classes specific to your agent's domain functionality
# Examples:
# - TestRAGRetrieval (for RAG agents)
# - TestCodeGeneration (for code generation agents)
# - TestSelfReflection (for reflection agents)
# - TestToolUsage (for tool-using agents)
# etc.

class Test{AgentName}DomainSpecific:
    """Test domain-specific functionality."""

    # Add domain-specific tests here
    pass


# ============================================================================
# FINAL CHECKLIST
# ============================================================================

"""
Test Coverage Checklist:

[ ] At least 30 tests total
[ ] TestInitialization: 5-8 tests
[ ] TestExecution: 8-12 tests
[ ] TestConfiguration: 5-8 tests
[ ] TestSignature: 3-5 tests
[ ] TestErrorHandling: 3-5 tests
[ ] TestDocumentation: 2-3 tests
[ ] TestTypeHints: 2-3 tests
[ ] Optional classes added based on features
[ ] Domain-specific tests added
[ ] All tests pass (100%)
[ ] No warnings
[ ] Test execution time < 5 seconds

Quality Gates:
[ ] Zero-config test passes
[ ] Environment variable test passes
[ ] Progressive configuration tests pass
[ ] Main method execution tests pass
[ ] Error handling tests pass
[ ] Documentation tests pass

Ready for pattern-expert validation? [ ]
Ready for import validation? [ ]
Ready for merge? [ ]
"""
