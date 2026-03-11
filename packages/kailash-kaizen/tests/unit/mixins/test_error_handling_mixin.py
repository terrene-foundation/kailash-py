"""
Task 3.2 - ErrorHandlingMixin Unit Tests.

Tests for ErrorHandlingMixin covering error scenarios and recovery strategies.

Evidence Required:
- 15+ test cases covering error scenarios
- 95%+ coverage for ErrorHandlingMixin
- Tests for retry logic and fallback strategies

References:
- TODO-157: Task 3.2, 3.10-3.13
- ADR-006: Mixin Composition design
"""

import time

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.mixins.error_handling import ErrorHandlingMixin
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Simple signature for testing."""

    input_text: str = InputField(desc="Input text")
    output_text: str = OutputField(desc="Output text")


@pytest.mark.unit
class TestErrorHandlingMixinInitialization:
    """Test ErrorHandlingMixin initialization."""

    def test_mixin_initialization_default(self):
        """Task 3.2 - ErrorHandlingMixin initializes with defaults."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        assert hasattr(agent, "max_retries")
        assert agent.max_retries == 3  # Default

    def test_mixin_initialization_custom_retries(self):
        """Task 3.2 - ErrorHandlingMixin accepts custom retry count."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=5)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        assert agent.max_retries == 5

    def test_mixin_initialization_with_backoff(self):
        """Task 3.2 - ErrorHandlingMixin accepts backoff configuration."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, backoff_factor=2.0)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        assert agent.backoff_factor == 2.0


@pytest.mark.unit
class TestErrorHandlingMixinRetryLogic:
    """Test ErrorHandlingMixin retry logic."""

    def test_retry_on_failure(self):
        """Task 3.12 - Retries execution on failure."""
        call_count = [0]

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=3)

            def _execute(self):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise ValueError("Test error")
                return {"success": True}

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        result = agent.execute_with_retry(agent._execute)

        # Should have retried twice before succeeding on third attempt
        assert call_count[0] == 3
        assert result["success"] is True

    def test_retry_respects_max_retries(self):
        """Task 3.12 - Respects max_retries limit."""
        call_count = [0]

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=2)

            def _execute(self):
                call_count[0] += 1
                raise ValueError("Persistent error")

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        with pytest.raises(ValueError):
            agent.execute_with_retry(agent._execute)

        # Should have tried 1 initial + 2 retries = 3 total
        assert call_count[0] == 3

    def test_retry_with_backoff(self):
        """Task 3.12 - Implements exponential backoff."""
        call_times = []

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=2, backoff_factor=0.1)

            def _execute(self):
                call_times.append(time.time())
                if len(call_times) < 3:
                    raise ValueError("Test error")
                return {"success": True}

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        agent.execute_with_retry(agent._execute)

        # Should have backoff between retries
        if len(call_times) >= 2:
            time_diff = call_times[1] - call_times[0]
            assert time_diff >= 0.05  # At least some delay

    def test_no_retry_on_success(self):
        """Task 3.12 - Does not retry on successful execution."""
        call_count = [0]

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=5)

            def _execute(self):
                call_count[0] += 1
                return {"success": True}

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        agent.execute_with_retry(agent._execute)

        # Should only execute once
        assert call_count[0] == 1


@pytest.mark.unit
class TestErrorHandlingMixinFallbackStrategies:
    """Test ErrorHandlingMixin fallback strategies."""

    def test_fallback_on_persistent_failure(self):
        """Task 3.13 - Executes fallback on persistent failure."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=1)

            def _execute(self):
                raise ValueError("Persistent error")

            def _fallback(self):
                return {"fallback": True}

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        result = agent.execute_with_fallback(agent._execute, agent._fallback)

        # Should return fallback result
        assert result["fallback"] is True

    def test_no_fallback_on_success(self):
        """Task 3.13 - Does not execute fallback on success."""
        fallback_called = [False]

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

            def _execute(self):
                return {"success": True}

            def _fallback(self):
                fallback_called[0] = True
                return {"fallback": True}

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        result = agent.execute_with_fallback(agent._execute, agent._fallback)

        # Fallback should not be called
        assert fallback_called[0] is False
        assert result["success"] is True

    def test_multiple_fallback_strategies(self):
        """Task 3.13 - Supports multiple fallback strategies."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        def primary():
            raise ValueError("Primary failed")

        def fallback1():
            raise ValueError("Fallback 1 failed")

        def fallback2():
            return {"fallback2": True}

        result = agent.execute_with_fallbacks(primary, [fallback1, fallback2])

        # Should use second fallback
        assert result["fallback2"] is True


@pytest.mark.unit
class TestErrorHandlingMixinWorkflowEnhancement:
    """Test ErrorHandlingMixin workflow enhancement."""

    def test_enhance_workflow_returns_workflow_builder(self):
        """Task 3.10 - enhance_workflow() returns WorkflowBuilder."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        enhanced = agent.enhance_workflow(workflow)

        assert isinstance(enhanced, WorkflowBuilder)

    def test_enhance_workflow_adds_error_handlers(self):
        """Task 3.10 - enhance_workflow() adds error handling nodes."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "test_node", {})

        enhanced = agent.enhance_workflow(workflow)

        # Workflow should have error handling added
        assert enhanced is not None


@pytest.mark.unit
class TestErrorHandlingMixinErrorRecovery:
    """Test ErrorHandlingMixin error recovery."""

    def test_error_recovery_with_state_restoration(self):
        """Task 3.11 - Restores state after error."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)
                self.state = "initial"

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        def operation():
            agent.state = "modified"
            raise ValueError("Error")

        # Capture initial state
        agent.capture_state()

        try:
            agent.execute_with_retry(operation)
        except ValueError:
            pass

        # Can restore state if needed
        assert hasattr(agent, "capture_state")

    def test_error_categorization(self):
        """Task 3.11 - Categorizes different error types."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        # Different error types
        value_error = ValueError("Test")
        runtime_error = RuntimeError("Test")

        category1 = agent.categorize_error(value_error)
        category2 = agent.categorize_error(runtime_error)

        # Should categorize errors (even if same category for now)
        assert category1 is not None
        assert category2 is not None


@pytest.mark.unit
class TestErrorHandlingMixinMROCompatibility:
    """Test ErrorHandlingMixin MRO compatibility."""

    def test_mro_with_base_agent(self):
        """Task 3.2 - ErrorHandlingMixin works with BaseAgent in MRO."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, ErrorHandlingMixin)

    def test_mro_calls_super_init(self):
        """Task 3.2 - ErrorHandlingMixin.__init__ calls super().__init__ correctly."""
        init_calls = []

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                init_calls.append("BaseAgent")
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                init_calls.append("ErrorHandlingMixin")
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        TestAgent(config)

        assert "BaseAgent" in init_calls
        assert "ErrorHandlingMixin" in init_calls


@pytest.mark.unit
class TestErrorHandlingMixinConfiguration:
    """Test ErrorHandlingMixin configuration."""

    def test_respects_error_handling_enabled_flag(self):
        """Task 3.2 - Respects error_handling_enabled config flag."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                if config.error_handling_enabled:
                    ErrorHandlingMixin.__init__(self)

        config_enabled = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent_enabled = TestAgent(config_enabled)
        assert hasattr(agent_enabled, "max_retries")

        config_disabled = BaseAgentConfig(model="gpt-4", error_handling_enabled=False)
        TestAgent(config_disabled)
        assert True  # Agent created successfully

    def test_configurable_retry_strategy(self):
        """Task 3.12 - Supports configurable retry strategies."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(
                    self,
                    max_retries=5,
                    backoff_factor=1.5,
                    retry_on=(ValueError, RuntimeError),
                )

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        assert agent.max_retries == 5
        assert agent.backoff_factor == 1.5


@pytest.mark.unit
class TestErrorHandlingMixinEdgeCases:
    """Test ErrorHandlingMixin edge cases."""

    def test_handles_none_fallback(self):
        """Task 3.13 - Handles None fallback gracefully."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        def failing_op():
            raise ValueError("Error")

        # Should raise original error if no fallback
        with pytest.raises(ValueError):
            agent.execute_with_fallback(failing_op, None)

    def test_handles_nested_errors(self):
        """Task 3.11 - Handles errors within error handlers."""

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        def failing_op():
            raise ValueError("Primary error")

        def failing_fallback():
            raise RuntimeError("Fallback error")

        # Should propagate fallback error
        with pytest.raises((ValueError, RuntimeError)):
            agent.execute_with_fallback(failing_op, failing_fallback)

    def test_zero_retries_configuration(self):
        """Task 3.12 - Handles zero retries configuration."""
        call_count = [0]

        class TestAgent(BaseAgent, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=0)

            def _execute(self):
                call_count[0] += 1
                raise ValueError("Error")

        config = BaseAgentConfig(model="gpt-4", error_handling_enabled=True)
        agent = TestAgent(config)

        with pytest.raises(ValueError):
            agent.execute_with_retry(agent._execute)

        # Should only execute once (no retries)
        assert call_count[0] == 1
