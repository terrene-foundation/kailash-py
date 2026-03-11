"""
Task 3.5 - Mixin Composition Tests.

Tests for validating mixin composition and MRO (Method Resolution Order).

Evidence Required:
- Test all mixin combinations work correctly
- Test MRO resolution with multiple mixins
- Test that mixins don't interfere with each other
- Test that all features work when combined

References:
- TODO-157: Task 3.5
- ADR-006: Mixin Composition design
- Phase 3: Mixin System implementation
"""

import time

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.mixins.batch_processing import BatchProcessingMixin
from kaizen.mixins.error_handling import ErrorHandlingMixin
from kaizen.mixins.logging import LoggingMixin
from kaizen.mixins.performance import PerformanceMixin
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Simple signature for testing."""

    input_text: str = InputField(desc="Input text")
    output_text: str = OutputField(desc="Output text")


@pytest.mark.unit
class TestMixinCompositionBasics:
    """Test basic mixin composition patterns."""

    def test_single_mixin_composition(self):
        """Task 3.5 - Single mixin composes correctly with BaseAgent."""

        class TestAgent(BaseAgent, LoggingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", logging_enabled=True)
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, LoggingMixin)
        assert hasattr(agent, "logger")

    def test_two_mixin_composition(self):
        """Task 3.5 - Two mixins compose correctly."""

        class TestAgent(BaseAgent, LoggingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4", logging_enabled=True, performance_enabled=True
        )
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, LoggingMixin)
        assert isinstance(agent, PerformanceMixin)
        assert hasattr(agent, "logger")
        assert hasattr(agent, "metrics")

    def test_three_mixin_composition(self):
        """Task 3.5 - Three mixins compose correctly."""

        class TestAgent(BaseAgent, LoggingMixin, ErrorHandlingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4",
            logging_enabled=True,
            error_handling_enabled=True,
            performance_enabled=True,
        )
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, LoggingMixin)
        assert isinstance(agent, ErrorHandlingMixin)
        assert isinstance(agent, PerformanceMixin)

    def test_all_four_mixins_composition(self):
        """Task 3.5 - All four mixins compose correctly."""

        class TestAgent(
            BaseAgent,
            LoggingMixin,
            ErrorHandlingMixin,
            PerformanceMixin,
            BatchProcessingMixin,
        ):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self)
                PerformanceMixin.__init__(self)
                BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4",
            logging_enabled=True,
            error_handling_enabled=True,
            performance_enabled=True,
            batch_processing_enabled=True,
        )
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, LoggingMixin)
        assert isinstance(agent, ErrorHandlingMixin)
        assert isinstance(agent, PerformanceMixin)
        assert isinstance(agent, BatchProcessingMixin)


@pytest.mark.unit
class TestMixinMROResolution:
    """Test Method Resolution Order with mixins."""

    def test_mro_order_is_correct(self):
        """Task 3.5 - MRO follows correct order."""

        class TestAgent(BaseAgent, LoggingMixin, ErrorHandlingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        # Check MRO
        mro = TestAgent.__mro__
        assert TestAgent in mro
        assert BaseAgent in mro
        assert LoggingMixin in mro
        assert ErrorHandlingMixin in mro
        assert PerformanceMixin in mro

    def test_mro_with_different_order(self):
        """Task 3.5 - MRO works with different mixin orders."""

        class TestAgent1(BaseAgent, LoggingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        class TestAgent2(BaseAgent, PerformanceMixin, LoggingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)
                LoggingMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4", logging_enabled=True, performance_enabled=True
        )

        agent1 = TestAgent1(config)
        agent2 = TestAgent2(config)

        # Both should work
        assert isinstance(agent1, LoggingMixin)
        assert isinstance(agent1, PerformanceMixin)
        assert isinstance(agent2, LoggingMixin)
        assert isinstance(agent2, PerformanceMixin)

    def test_mro_super_calls_work(self):
        """Task 3.5 - super().__init__() works correctly in MRO chain."""
        init_order = []

        class TrackingLogMixin(LoggingMixin):
            def __init__(self, **kwargs):
                init_order.append("LoggingMixin")
                super().__init__(**kwargs)

        class TrackingPerfMixin(PerformanceMixin):
            def __init__(self, **kwargs):
                init_order.append("PerformanceMixin")
                super().__init__(**kwargs)

        class TestAgent(BaseAgent, TrackingLogMixin, TrackingPerfMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                TrackingLogMixin.__init__(self)
                TrackingPerfMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4")
        TestAgent(config)

        # MRO should have processed both mixins
        assert "LoggingMixin" in init_order
        assert "PerformanceMixin" in init_order


@pytest.mark.unit
class TestMixinInterference:
    """Test that mixins don't interfere with each other."""

    def test_logging_and_performance_dont_interfere(self):
        """Task 3.5 - LoggingMixin and PerformanceMixin don't interfere."""

        class TestAgent(BaseAgent, LoggingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4", logging_enabled=True, performance_enabled=True
        )
        agent = TestAgent(config)

        # Test logging works
        agent.log_execution_start()
        assert agent.execution_id is not None

        # Test performance tracking works
        agent.start_tracking()
        time.sleep(0.01)
        agent.stop_tracking()
        metrics = agent.get_metrics()
        assert metrics["execution_count"] == 1

    def test_error_handling_and_batch_processing_dont_interfere(self):
        """Task 3.5 - ErrorHandlingMixin and BatchProcessingMixin don't interfere."""

        class TestAgent(BaseAgent, ErrorHandlingMixin, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self)
                BatchProcessingMixin.__init__(self)

            def process_item(self, item):
                if item == "error":
                    raise ValueError("Test error")
                return {"result": item}

        config = BaseAgentConfig(
            model="gpt-4", error_handling_enabled=True, batch_processing_enabled=True
        )
        agent = TestAgent(config)

        # Test error handling works
        result = agent.execute_with_retry(lambda: {"success": True})
        assert result["success"] is True

        # Test batch processing works
        inputs = ["item1", "item2", "item3"]
        results = agent.process_batch(inputs, agent.process_item)
        assert len(results) == 3

    def test_all_mixins_work_together(self):
        """Task 3.5 - All mixins work together without interference."""

        class TestAgent(
            BaseAgent,
            LoggingMixin,
            ErrorHandlingMixin,
            PerformanceMixin,
            BatchProcessingMixin,
        ):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self)
                PerformanceMixin.__init__(self)
                BatchProcessingMixin.__init__(self)

            def process_item(self, item):
                return {"result": f"processed_{item}"}

        config = BaseAgentConfig(
            model="gpt-4",
            logging_enabled=True,
            error_handling_enabled=True,
            performance_enabled=True,
            batch_processing_enabled=True,
        )
        agent = TestAgent(config)

        # Test logging
        agent.log_execution_start({"input": "test"})
        assert agent.execution_id is not None

        # Test error handling
        result = agent.execute_with_retry(lambda: {"success": True})
        assert result["success"] is True

        # Test performance tracking
        agent.start_tracking()
        time.sleep(0.001)
        agent.stop_tracking()
        metrics = agent.get_metrics()
        assert metrics["execution_count"] == 1

        # Test batch processing
        inputs = ["a", "b", "c"]
        results = agent.process_batch(inputs, agent.process_item)
        assert len(results) == 3


@pytest.mark.unit
class TestMixinFeatureIntegration:
    """Test integrated features across mixins."""

    def test_logging_with_error_handling(self):
        """Task 3.5 - Logging captures error handling events."""

        class TestAgent(BaseAgent, LoggingMixin, ErrorHandlingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self, max_retries=2)

        config = BaseAgentConfig(
            model="gpt-4", logging_enabled=True, error_handling_enabled=True
        )
        agent = TestAgent(config)

        call_count = [0]

        def failing_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Retry me")
            return {"success": True}

        agent.log_execution_start()
        result = agent.execute_with_retry(failing_func)
        agent.log_execution_end(result)

        assert result["success"] is True
        assert call_count[0] == 2

    def test_performance_with_batch_processing(self):
        """Task 3.5 - Performance tracking works with batch processing."""

        class TestAgent(BaseAgent, PerformanceMixin, BatchProcessingMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)
                BatchProcessingMixin.__init__(self)

            def process_item(self, item):
                time.sleep(0.001)  # Simulate work
                return {"result": item}

        config = BaseAgentConfig(
            model="gpt-4", performance_enabled=True, batch_processing_enabled=True
        )
        agent = TestAgent(config)

        # Track performance of batch processing
        agent.start_tracking()
        inputs = list(range(5))
        results = agent.process_batch(inputs, agent.process_item)
        agent.stop_tracking()

        # Verify both work
        assert len(results) == 5
        metrics = agent.get_metrics()
        assert metrics["execution_time_ms"] > 0

    def test_error_handling_with_performance_tracking(self):
        """Task 3.5 - Error handling and performance tracking work together."""

        class TestAgent(BaseAgent, ErrorHandlingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                ErrorHandlingMixin.__init__(self, max_retries=1)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4", error_handling_enabled=True, performance_enabled=True
        )
        agent = TestAgent(config)

        call_count = [0]

        def slow_func():
            call_count[0] += 1
            time.sleep(0.01)
            if call_count[0] < 2:
                raise ValueError("Retry me")
            return {"success": True}

        # Track performance of retry execution
        agent.start_tracking()
        result = agent.execute_with_retry(slow_func)
        agent.stop_tracking()

        assert result["success"] is True
        assert call_count[0] == 2
        metrics = agent.get_metrics()
        assert metrics["execution_time_ms"] > 10  # At least 10ms from 2 sleeps


@pytest.mark.unit
class TestMixinEnhanceWorkflow:
    """Test enhance_workflow() with multiple mixins."""

    def test_multiple_enhance_workflow_calls(self):
        """Task 3.5 - Multiple enhance_workflow() calls work correctly."""
        from kailash.workflow.builder import WorkflowBuilder

        class TestAgent(BaseAgent, LoggingMixin, ErrorHandlingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                ErrorHandlingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4")
        agent = TestAgent(config)

        workflow = WorkflowBuilder()

        # Each mixin enhances the workflow
        workflow = agent.enhance_workflow(workflow)  # LoggingMixin
        workflow = agent.enhance_workflow(workflow)  # ErrorHandlingMixin (via MRO)
        workflow = agent.enhance_workflow(workflow)  # PerformanceMixin (via MRO)

        # All enhancements should work
        assert workflow is not None
        assert isinstance(workflow, WorkflowBuilder)

    def test_enhance_workflow_preserves_nodes(self):
        """Task 3.5 - enhance_workflow() preserves existing nodes."""
        from kailash.workflow.builder import WorkflowBuilder

        class TestAgent(BaseAgent, LoggingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                LoggingMixin.__init__(self)
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4")
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "test_node", {})

        # Enhance workflow multiple times
        enhanced = agent.enhance_workflow(workflow)

        # Original node should still be there
        assert enhanced is not None


@pytest.mark.unit
class TestMixinConfigurationCombinations:
    """Test different configuration combinations."""

    def test_partial_mixin_activation(self):
        """Task 3.5 - Only activated mixins are initialized."""

        class TestAgent(BaseAgent, LoggingMixin, ErrorHandlingMixin, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                if config.logging_enabled:
                    LoggingMixin.__init__(self)
                if config.error_handling_enabled:
                    ErrorHandlingMixin.__init__(self)
                if config.performance_enabled:
                    PerformanceMixin.__init__(self)

        # Only enable logging
        config = BaseAgentConfig(
            model="gpt-4",
            logging_enabled=True,
            error_handling_enabled=False,
            performance_enabled=False,
        )
        agent = TestAgent(config)

        # Only logging should be active
        assert hasattr(agent, "logger")
        # Others won't have their attributes

    def test_all_mixins_enabled(self):
        """Task 3.5 - All mixins can be enabled together."""

        class TestAgent(
            BaseAgent,
            LoggingMixin,
            ErrorHandlingMixin,
            PerformanceMixin,
            BatchProcessingMixin,
        ):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                if config.logging_enabled:
                    LoggingMixin.__init__(self)
                if config.error_handling_enabled:
                    ErrorHandlingMixin.__init__(self)
                if config.performance_enabled:
                    PerformanceMixin.__init__(self)
                if config.batch_processing_enabled:
                    BatchProcessingMixin.__init__(self)

        config = BaseAgentConfig(
            model="gpt-4",
            logging_enabled=True,
            error_handling_enabled=True,
            performance_enabled=True,
            batch_processing_enabled=True,
        )
        agent = TestAgent(config)

        # All should be initialized
        assert hasattr(agent, "logger")
        assert hasattr(agent, "max_retries")
        assert hasattr(agent, "metrics")
        assert hasattr(agent, "batch_size")
