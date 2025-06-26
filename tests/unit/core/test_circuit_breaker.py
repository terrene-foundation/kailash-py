"""Unit tests for circuit breaker implementation."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from kailash.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitBreakerManager,
    CircuitState,
    ConnectionCircuitBreaker,
)


def async_lambda(value):
    """Helper to create async lambda functions."""

    async def func():
        return value

    return func


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=1,  # 1 second for faster tests
            half_open_requests=2,
            error_rate_threshold=0.5,
            window_size=10,
        )

    @pytest.fixture
    def breaker(self, config):
        """Create test circuit breaker."""
        return ConnectionCircuitBreaker(config)

    @pytest.mark.asyncio
    async def test_initial_state(self, breaker):
        """Test circuit breaker starts in closed state."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.total_calls == 0
        assert breaker.metrics.failed_calls == 0

    @pytest.mark.asyncio
    async def test_successful_calls(self, breaker):
        """Test successful calls don't open circuit."""

        async def success_func():
            return "success"

        # Multiple successful calls
        for _ in range(5):
            result = await breaker.call(success_func)
            assert result == "success"

        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.total_calls == 5
        assert breaker.metrics.successful_calls == 5
        assert breaker.metrics.failed_calls == 0

    @pytest.mark.asyncio
    async def test_circuit_opens_on_failures(self, breaker):
        """Test circuit opens after failure threshold."""

        async def failing_func():
            raise Exception("Test failure")

        # Fail threshold times
        for i in range(3):
            with pytest.raises(Exception):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.metrics.consecutive_failures == 3

        # Further calls should fail fast
        with pytest.raises(CircuitBreakerError) as exc_info:
            await breaker.call(failing_func)

        assert "Circuit breaker is OPEN" in str(exc_info.value)
        assert breaker.metrics.rejected_calls == 1

    @pytest.mark.asyncio
    async def test_recovery_to_half_open(self, breaker):
        """Test circuit recovers to half-open after timeout."""

        async def failing_func():
            raise Exception("Test failure")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(1.1)

        # Next call should be allowed (half-open)
        async def success_func():
            return "success"

        result = await breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed(self, breaker):
        """Test circuit closes after success threshold in half-open."""

        # Open the circuit
        async def failing_func():
            raise Exception("Test failure")

        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(failing_func)

        # Wait for half-open
        await asyncio.sleep(1.1)

        # Succeed enough times to close
        async def success_func():
            return "success"

        for _ in range(2):  # success_threshold = 2
            await breaker.call(success_func)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.consecutive_successes >= 2

    @pytest.mark.asyncio
    async def test_half_open_to_open(self, breaker):
        """Test circuit reopens on failure in half-open state."""

        # Open the circuit
        async def failing_func():
            raise Exception("Test failure")

        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(failing_func)

        # Wait for half-open
        await asyncio.sleep(1.1)

        # Fail again
        with pytest.raises(Exception):
            await breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_error_rate_threshold(self, breaker):
        """Test circuit opens based on error rate."""

        async def sometimes_failing(fail):
            if fail:
                raise Exception("Test failure")
            return "success"

        # Create pattern: success, fail, success, fail...
        # This gives 50% error rate
        for i in range(10):
            try:
                await breaker.call(sometimes_failing, fail=(i % 2 == 1))
            except:
                pass

        # With 50% error rate and threshold of 0.5, should be open
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_excluded_exceptions(self):
        """Test excluded exceptions don't count as failures."""
        config = CircuitBreakerConfig(
            failure_threshold=2, excluded_exceptions=[ValueError]
        )
        breaker = ConnectionCircuitBreaker(config)

        async def failing_func():
            raise ValueError("This should be ignored")

        # These shouldn't count
        for _ in range(5):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.failed_calls == 0

    @pytest.mark.asyncio
    async def test_manual_control(self, breaker):
        """Test manual open/close functionality."""
        assert breaker.state == CircuitState.CLOSED

        # Manually open
        await breaker.force_open("Testing manual open")
        assert breaker.state == CircuitState.OPEN

        # Calls should fail
        with pytest.raises(CircuitBreakerError):
            await breaker.call(async_lambda("test"))

        # Manually close
        await breaker.force_close("Testing manual close")
        assert breaker.state == CircuitState.CLOSED

        # Calls should work
        result = await breaker.call(async_lambda("success"))
        assert result == "success"

    @pytest.mark.asyncio
    async def test_state_listeners(self, breaker):
        """Test state change listeners."""
        transitions = []

        async def listener(old_state, new_state, metrics):
            transitions.append((old_state, new_state))

        breaker.add_listener(listener)

        # Cause state changes
        async def failing_func():
            raise Exception("Test")

        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(failing_func)

        assert len(transitions) == 1
        assert transitions[0] == (CircuitState.CLOSED, CircuitState.OPEN)

    @pytest.mark.asyncio
    async def test_get_status(self, breaker):
        """Test status reporting."""
        # Make some calls
        await breaker.call(async_lambda("success"))

        with pytest.raises(Exception):

            async def divide_by_zero():
                return 1 / 0

            await breaker.call(divide_by_zero)

        status = breaker.get_status()

        assert status["state"] == "closed"
        assert status["metrics"]["total_calls"] == 2
        assert status["metrics"]["successful_calls"] == 1
        assert status["metrics"]["failed_calls"] == 1
        assert "config" in status
        assert "state_transitions" in status


class TestCircuitBreakerManager:
    """Test circuit breaker manager."""

    @pytest.fixture
    def manager(self):
        """Create test manager."""
        return CircuitBreakerManager()

    def test_get_or_create(self, manager):
        """Test breaker creation and retrieval."""
        # First call creates
        breaker1 = manager.get_or_create("test1")
        assert isinstance(breaker1, ConnectionCircuitBreaker)

        # Second call returns same instance
        breaker2 = manager.get_or_create("test1")
        assert breaker1 is breaker2

        # Different name creates new instance
        breaker3 = manager.get_or_create("test2")
        assert breaker3 is not breaker1

    def test_custom_config(self, manager):
        """Test custom configuration."""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = manager.get_or_create("custom", config)

        assert breaker.config.failure_threshold == 10

    def test_get_all_status(self, manager):
        """Test getting all breaker statuses."""
        manager.get_or_create("breaker1")
        manager.get_or_create("breaker2")

        all_status = manager.get_all_status()

        assert len(all_status) == 2
        assert "breaker1" in all_status
        assert "breaker2" in all_status
        assert all_status["breaker1"]["state"] == "closed"

    @pytest.mark.asyncio
    async def test_reset_all(self, manager):
        """Test resetting all breakers."""
        breaker1 = manager.get_or_create("breaker1")
        breaker2 = manager.get_or_create("breaker2")

        # Make some calls to change state
        await breaker1.call(async_lambda("success"))
        await breaker2.call(async_lambda("success"))

        # Reset all
        await manager.reset_all()

        # Check states are reset
        assert breaker1.metrics.total_calls == 0
        assert breaker2.metrics.total_calls == 0
