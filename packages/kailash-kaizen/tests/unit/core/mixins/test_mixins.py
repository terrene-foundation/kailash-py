"""
Unit tests for BaseAgent mixins.

Tests all 7 mixin implementations:
- LoggingMixin: Structured logging
- MetricsMixin: Metrics collection
- CachingMixin: Response caching
- TracingMixin: Distributed tracing
- RetryMixin: Automatic retry
- TimeoutMixin: Timeout handling
- ValidationMixin: Input/output validation

Test Tier: Unit (Tier 1) - Mocks allowed for isolation
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.core.mixins import (
    CachingMixin,
    LoggingMixin,
    MetricsMixin,
    RetryMixin,
    TimeoutMixin,
    TracingMixin,
    ValidationMixin,
)

pytestmark = pytest.mark.unit


class MockAgent:
    """Mock agent for testing mixins."""

    def __init__(self):
        self.config = MagicMock()
        self.config.cache_ttl = 60
        self.config.max_retries = 2
        self.config.timeout = 5.0
        self.signature = None
        self._call_count = 0

    async def run(self, **kwargs):
        """Mock run method."""
        self._call_count += 1
        return {"result": "success", "input": kwargs}


class TestLoggingMixin:
    """Tests for LoggingMixin."""

    def test_apply_creates_logger(self):
        """Test that apply creates an agent-specific logger."""
        agent = MockAgent()
        LoggingMixin.apply(agent)

        assert hasattr(agent, "_agent_logger")
        assert "kaizen.agent.MockAgent" in agent._agent_logger.name

    @pytest.mark.asyncio
    async def test_logging_wraps_run(self):
        """Test that logging wraps the run method."""
        agent = MockAgent()
        LoggingMixin.apply(agent)

        with patch.object(agent._agent_logger, "info") as mock_info:
            result = await agent.run(question="test")

            assert result["result"] == "success"
            assert mock_info.call_count >= 2  # Start and end

    @pytest.mark.asyncio
    async def test_logging_on_error(self):
        """Test that errors are logged."""
        agent = MockAgent()

        async def failing_run(**kwargs):
            raise ValueError("Test error")

        agent.run = failing_run
        LoggingMixin.apply(agent)

        with patch.object(agent._agent_logger, "error") as mock_error:
            with pytest.raises(ValueError):
                await agent.run(question="test")

            mock_error.assert_called_once()


class TestMetricsMixin:
    """Tests for MetricsMixin."""

    def test_apply_creates_metrics(self):
        """Test that apply creates metrics collector."""
        agent = MockAgent()
        MetricsMixin.apply(agent)

        assert hasattr(agent, "_metrics")

    @pytest.mark.asyncio
    async def test_metrics_tracks_executions(self):
        """Test that executions are tracked."""
        agent = MockAgent()
        MetricsMixin.apply(agent)

        await agent.run(question="test1")
        await agent.run(question="test2")

        metrics = agent._metrics.get_metrics()
        assert metrics["counters"]["agent.MockAgent.executions.total"] == 2
        assert metrics["counters"]["agent.MockAgent.executions.success"] == 2

    @pytest.mark.asyncio
    async def test_metrics_tracks_failures(self):
        """Test that failures are tracked."""
        agent = MockAgent()
        original_run = agent.run

        call_count = 0

        async def sometimes_fail(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Fail")
            return await original_run(**kwargs)

        agent.run = sometimes_fail
        MetricsMixin.apply(agent)

        with pytest.raises(ValueError):
            await agent.run(question="test")

        metrics = agent._metrics.get_metrics()
        assert metrics["counters"]["agent.MockAgent.executions.failure"] == 1


class TestCachingMixin:
    """Tests for CachingMixin."""

    def test_apply_creates_cache(self):
        """Test that apply creates cache."""
        agent = MockAgent()
        CachingMixin.apply(agent)

        assert hasattr(agent, "_cache")

    @pytest.mark.asyncio
    async def test_caching_returns_cached_result(self):
        """Test that cached results are returned."""
        agent = MockAgent()
        CachingMixin.apply(agent)

        result1 = await agent.run(question="test")
        result2 = await agent.run(question="test")

        assert result1 == result2
        assert agent._call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_cache_bypass(self):
        """Test that cache_bypass works."""
        agent = MockAgent()
        CachingMixin.apply(agent)

        await agent.run(question="test")
        await agent.run(question="test", cache_bypass=True)

        assert agent._call_count == 2  # Called twice

    @pytest.mark.asyncio
    async def test_different_inputs_not_cached(self):
        """Test that different inputs are not cached together."""
        agent = MockAgent()
        CachingMixin.apply(agent)

        await agent.run(question="test1")
        await agent.run(question="test2")

        assert agent._call_count == 2


class TestTracingMixin:
    """Tests for TracingMixin."""

    def test_apply_creates_tracer(self):
        """Test that apply creates tracer."""
        agent = MockAgent()
        TracingMixin.apply(agent)

        assert hasattr(agent, "_tracer")

    @pytest.mark.asyncio
    async def test_tracing_creates_spans(self):
        """Test that spans are created."""
        agent = MockAgent()
        TracingMixin.apply(agent)

        await agent.run(question="test")

        spans = agent._tracer.get_spans()
        assert len(spans) == 1
        assert spans[0].name == "MockAgent.run"
        assert spans[0].status == "success"

    @pytest.mark.asyncio
    async def test_tracing_records_errors(self):
        """Test that errors are recorded in spans."""
        agent = MockAgent()

        async def failing_run(**kwargs):
            raise ValueError("Test error")

        agent.run = failing_run
        TracingMixin.apply(agent)

        with pytest.raises(ValueError):
            await agent.run(question="test")

        spans = agent._tracer.get_spans()
        assert len(spans) == 1
        assert spans[0].status == "error"
        assert len(spans[0].events) == 1


class TestRetryMixin:
    """Tests for RetryMixin."""

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Test retry on ConnectionError."""
        agent = MockAgent()
        call_count = 0

        async def sometimes_fail(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection failed")
            return {"result": "success"}

        agent.run = sometimes_fail
        RetryMixin.apply(agent, max_retries=3, base_delay=0.01)

        result = await agent.run(question="test")

        assert result["result"] == "success"
        assert call_count == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_no_retry_on_value_error(self):
        """Test no retry on non-retryable exception."""
        agent = MockAgent()

        async def fail(**kwargs):
            raise ValueError("Invalid value")

        agent.run = fail
        RetryMixin.apply(agent, max_retries=3)

        with pytest.raises(ValueError):
            await agent.run(question="test")

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that max retries is respected."""
        agent = MockAgent()
        call_count = 0

        async def always_fail(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        agent.run = always_fail
        RetryMixin.apply(agent, max_retries=2, base_delay=0.01)

        with pytest.raises(ConnectionError):
            await agent.run(question="test")

        assert call_count == 3  # Initial + 2 retries


class TestTimeoutMixin:
    """Tests for TimeoutMixin."""

    @pytest.mark.asyncio
    async def test_timeout_completes_fast(self):
        """Test that fast operations complete normally."""
        agent = MockAgent()
        TimeoutMixin.apply(agent, timeout=5.0)

        result = await agent.run(question="test")
        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_timeout_raises_on_slow(self):
        """Test that slow operations raise TimeoutError."""
        agent = MockAgent()

        async def slow_run(**kwargs):
            await asyncio.sleep(10)
            return {"result": "success"}

        agent.run = slow_run
        TimeoutMixin.apply(agent, timeout=0.1)

        with pytest.raises(TimeoutError):
            await agent.run(question="test")


class TestValidationMixin:
    """Tests for ValidationMixin."""

    def test_apply_enables_validation(self):
        """Test that apply enables validation."""
        agent = MockAgent()
        ValidationMixin.apply(agent)

        assert agent._validation_enabled is True

    @pytest.mark.asyncio
    async def test_validation_passes_without_signature(self):
        """Test that validation passes when no signature."""
        agent = MockAgent()
        ValidationMixin.apply(agent)

        result = await agent.run(question="test")
        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_validation_with_signature(self):
        """Test validation with a mock signature."""
        agent = MockAgent()

        # Create mock signature with required field
        mock_signature = MagicMock()
        mock_field = MagicMock()
        mock_field.required = True
        mock_field.default = None
        mock_field.type_ = str
        mock_signature._input_fields = {"question": mock_field}
        mock_signature._output_fields = {}
        agent.signature = mock_signature

        ValidationMixin.apply(agent)

        # Should pass with required field
        result = await agent.run(question="test")
        assert result["result"] == "success"


class TestMixinIntegration:
    """Tests for mixin integration with BaseAgent."""

    def test_apply_mixins_method(self):
        """Test that _apply_mixins method works correctly."""
        from kaizen.core.config import BaseAgentConfig

        # Create a mock agent-like object with config
        agent = MockAgent()
        agent._mixins_applied = []
        agent.config = BaseAgentConfig(
            logging_enabled=True,
            performance_enabled=True,
        )

        # Apply mixins directly
        LoggingMixin.apply(agent)
        MetricsMixin.apply(agent)

        # Verify mixins are applied
        assert hasattr(agent, "_agent_logger")
        assert hasattr(agent, "_metrics")


class TestMixinOrder:
    """Tests for mixin application order."""

    @pytest.mark.asyncio
    async def test_multiple_mixins_compose(self):
        """Test that multiple mixins compose correctly."""
        agent = MockAgent()

        # Apply multiple mixins
        LoggingMixin.apply(agent)
        MetricsMixin.apply(agent)
        TracingMixin.apply(agent)

        # All should have wrapped run
        result = await agent.run(question="test")
        assert result["result"] == "success"

        # Check all mixins worked
        assert hasattr(agent, "_agent_logger")
        assert hasattr(agent, "_metrics")
        assert hasattr(agent, "_tracer")

        # Metrics should be tracked
        metrics = agent._metrics.get_metrics()
        assert metrics["counters"]["agent.MockAgent.executions.total"] >= 1

        # Spans should be created
        spans = agent._tracer.get_spans()
        assert len(spans) >= 1
