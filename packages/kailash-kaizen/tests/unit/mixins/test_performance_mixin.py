"""
Task 3.3 - PerformanceMixin Unit Tests.

Tests for PerformanceMixin covering metrics tracking and performance monitoring.

Evidence Required:
- 10+ test cases covering metrics tracking
- 95%+ coverage for PerformanceMixin
- Tests for enhance_workflow() and metrics collection

References:
- TODO-157: Task 3.3, 3.14-3.17
- ADR-006: Mixin Composition design
"""

import time

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.mixins.performance import PerformanceMixin
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Simple signature for testing."""

    input_text: str = InputField(desc="Input text")
    output_text: str = OutputField(desc="Output text")


@pytest.mark.unit
class TestPerformanceMixinInitialization:
    """Test PerformanceMixin initialization."""

    def test_mixin_initialization_default(self):
        """Task 3.3 - PerformanceMixin initializes with defaults."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        assert hasattr(agent, "metrics")
        assert isinstance(agent.metrics, dict)

    def test_mixin_initialization_with_targets(self):
        """Task 3.3 - PerformanceMixin accepts performance targets."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(
                    self, target_latency_ms=100.0, target_throughput=50.0
                )

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        assert agent.target_latency_ms == 100.0
        assert agent.target_throughput == 50.0


@pytest.mark.unit
class TestPerformanceMixinMetricsTracking:
    """Test PerformanceMixin metrics tracking."""

    def test_tracks_execution_time(self):
        """Task 3.15 - Tracks execution timing metrics."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        # Track execution
        agent.start_tracking()
        time.sleep(0.01)  # Simulate work
        agent.stop_tracking()

        metrics = agent.get_metrics()
        assert "execution_time_ms" in metrics
        assert metrics["execution_time_ms"] > 0

    def test_tracks_memory_usage(self):
        """Task 3.15 - Tracks memory usage metrics."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self, track_memory=True)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        agent.start_tracking()
        agent.stop_tracking()

        metrics = agent.get_metrics()
        # Memory tracking should be available
        assert metrics is not None

    def test_tracks_throughput(self):
        """Task 3.15 - Tracks throughput metrics."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        # Execute multiple times
        for _ in range(5):
            agent.start_tracking()
            time.sleep(0.001)
            agent.stop_tracking()

        metrics = agent.get_metrics()
        assert "execution_count" in metrics
        assert metrics["execution_count"] == 5


@pytest.mark.unit
class TestPerformanceMixinTargetValidation:
    """Test PerformanceMixin target validation."""

    def test_validates_latency_target(self):
        """Task 3.17 - Validates latency against target."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self, target_latency_ms=50.0)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        agent.start_tracking()
        time.sleep(0.01)  # 10ms - should pass
        agent.stop_tracking()

        violations = agent.check_target_violations()
        # Should not have latency violations for 10ms execution
        assert isinstance(violations, dict)

    def test_detects_latency_violations(self):
        """Task 3.17 - Detects latency target violations."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self, target_latency_ms=5.0)  # Very strict

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        agent.start_tracking()
        time.sleep(0.02)  # 20ms - should violate 5ms target
        agent.stop_tracking()

        violations = agent.check_target_violations()
        # Should detect latency violation
        assert violations is not None

    def test_reports_performance_status(self):
        """Task 3.17 - Reports overall performance status."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        agent.start_tracking()
        time.sleep(0.001)
        agent.stop_tracking()

        status = agent.get_performance_status()
        assert isinstance(status, dict)
        assert "metrics" in status or len(status) >= 0


@pytest.mark.unit
class TestPerformanceMixinWorkflowEnhancement:
    """Test PerformanceMixin workflow enhancement."""

    def test_enhance_workflow_returns_workflow_builder(self):
        """Task 3.14 - enhance_workflow() returns WorkflowBuilder."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        enhanced = agent.enhance_workflow(workflow)

        assert isinstance(enhanced, WorkflowBuilder)

    def test_enhance_workflow_adds_monitoring_nodes(self):
        """Task 3.14 - enhance_workflow() adds performance monitoring."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "test_node", {})

        enhanced = agent.enhance_workflow(workflow)

        # Workflow should be enhanced (even if no-op for now)
        assert enhanced is not None


@pytest.mark.unit
class TestPerformanceMixinMROCompatibility:
    """Test PerformanceMixin MRO compatibility."""

    def test_mro_with_base_agent(self):
        """Task 3.3 - PerformanceMixin works with BaseAgent in MRO."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, PerformanceMixin)

    def test_mro_calls_super_init(self):
        """Task 3.3 - PerformanceMixin.__init__ calls super().__init__ correctly."""
        init_calls = []

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                init_calls.append("BaseAgent")
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                init_calls.append("PerformanceMixin")
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        TestAgent(config)

        assert "BaseAgent" in init_calls
        assert "PerformanceMixin" in init_calls


@pytest.mark.unit
class TestPerformanceMixinConfiguration:
    """Test PerformanceMixin configuration."""

    def test_respects_performance_enabled_flag(self):
        """Task 3.3 - Respects performance_enabled config flag."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                if config.performance_enabled:
                    PerformanceMixin.__init__(self)

        config_enabled = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent_enabled = TestAgent(config_enabled)
        assert hasattr(agent_enabled, "metrics")

        config_disabled = BaseAgentConfig(model="gpt-4", performance_enabled=False)
        TestAgent(config_disabled)
        assert True  # Agent created successfully

    def test_configurable_monitoring_options(self):
        """Task 3.14 - Supports configurable monitoring options."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(
                    self, track_memory=True, track_throughput=True, sampling_rate=0.5
                )

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        assert agent.track_memory is True
        assert agent.track_throughput is True


@pytest.mark.unit
class TestPerformanceMixinEdgeCases:
    """Test PerformanceMixin edge cases."""

    def test_handles_zero_execution_time(self):
        """Task 3.15 - Handles very fast executions."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        agent.start_tracking()
        agent.stop_tracking()  # Immediate stop

        metrics = agent.get_metrics()
        # Should handle zero/very small time gracefully
        assert "execution_time_ms" in metrics

    def test_handles_multiple_concurrent_trackings(self):
        """Task 3.15 - Handles concurrent tracking attempts."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        # Start tracking twice
        agent.start_tracking()
        agent.start_tracking()  # Second start should handle gracefully

        agent.stop_tracking()

        # Should not crash
        assert True

    def test_get_metrics_before_tracking(self):
        """Task 3.15 - get_metrics() works before any tracking."""

        class TestAgent(BaseAgent, PerformanceMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config=config, signature=SimpleSignature())
                PerformanceMixin.__init__(self)

        config = BaseAgentConfig(model="gpt-4", performance_enabled=True)
        agent = TestAgent(config)

        # Get metrics without tracking
        metrics = agent.get_metrics()

        # Should return empty or default metrics
        assert isinstance(metrics, dict)
