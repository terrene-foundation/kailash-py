"""
Unit tests for DataFlow Retry & Circuit Breaking.

Tests cover:
1. Retry Handler Tests (4 tests)
2. Circuit Breaker Tests (4 tests)
3. Integration Tests (2 tests)

Total: 10 tests

Following TDD methodology - tests written BEFORE implementation.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# Test Group 1: Retry Handler Tests (4 tests)
# ============================================================================


@pytest.mark.unit
class TestRetryHandler:
    """Test automatic retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        """Test success on first attempt - no retries needed."""
        from dataflow.platform.resilience import RetryConfig, RetryHandler

        # Create retry handler with default config
        config = RetryConfig(max_attempts=3, base_delay=0.1, max_delay=5.0)
        handler = RetryHandler(config)

        # Mock function that succeeds immediately
        mock_func = AsyncMock(return_value="success")

        # Execute with retry
        result = await handler.execute_with_retry(mock_func, "arg1", kwarg="kwarg1")

        # Verify success on first attempt
        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_with("arg1", kwarg="kwarg1")

        # Verify metrics show 1 attempt, 0 failures
        metrics = handler.get_metrics()
        assert metrics["total_attempts"] == 1
        assert metrics["total_failures"] == 0
        assert metrics["total_successes"] == 1

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test success after 2 failures - retry works."""
        from dataflow.platform.resilience import RetryConfig, RetryHandler

        config = RetryConfig(max_attempts=3, base_delay=0.05, max_delay=5.0)
        handler = RetryHandler(config)

        # Mock function that fails twice, then succeeds
        call_count = 0

        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError(f"Transient failure {call_count}")
            return "success"

        # Execute with retry
        start_time = time.time()
        result = await handler.execute_with_retry(flaky_function)
        duration = time.time() - start_time

        # Verify success after retries
        assert result == "success"
        assert call_count == 3

        # Verify backoff delays were applied (should take > 0.05s for 2 retries)
        assert duration >= 0.05

        # Verify metrics
        metrics = handler.get_metrics()
        assert metrics["total_attempts"] == 3
        assert metrics["total_failures"] == 2
        assert metrics["total_successes"] == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test max attempts reached - raises RetryExhausted."""
        from dataflow.platform.resilience import (
            RetryConfig,
            RetryExhausted,
            RetryHandler,
        )

        config = RetryConfig(max_attempts=3, base_delay=0.01, max_delay=5.0)
        handler = RetryHandler(config)

        # Mock function that always fails
        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError(f"Persistent failure {call_count}")

        # Execute with retry - should exhaust retries
        with pytest.raises(RetryExhausted) as exc_info:
            await handler.execute_with_retry(failing_function)

        # Verify exception details
        assert "Max retry attempts (3) reached" in str(exc_info.value)
        assert exc_info.value.original_error is not None
        assert isinstance(exc_info.value.original_error, ConnectionError)

        # Verify all attempts were made
        assert call_count == 3

        # Verify metrics
        metrics = handler.get_metrics()
        assert metrics["total_attempts"] == 3
        assert metrics["total_failures"] == 3
        assert metrics["total_successes"] == 0

    @pytest.mark.asyncio
    async def test_exponential_backoff_with_jitter(self):
        """Test exponential backoff delays with jitter applied."""
        from dataflow.platform.resilience import (
            RetryConfig,
            RetryHandler,
            RetryStrategy,
        )

        config = RetryConfig(
            max_attempts=4,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=0.1,  # 100ms base
            max_delay=5.0,
            multiplier=2.0,
            jitter=True,
        )
        handler = RetryHandler(config)

        # Track delays between attempts
        attempt_times = []

        async def failing_function():
            attempt_times.append(time.time())
            raise ConnectionError("Always fails")

        # Execute with retry
        try:
            await handler.execute_with_retry(failing_function)
        except Exception:
            pass

        # Verify exponential backoff pattern
        # Expected delays (before jitter): 0.1, 0.2, 0.4
        # With jitter (50-100%): 0.05-0.1, 0.1-0.2, 0.2-0.4
        assert len(attempt_times) == 4

        # Calculate actual delays
        delays = [attempt_times[i + 1] - attempt_times[i] for i in range(3)]

        # Verify first delay: 0.05-0.1s (100ms * 50-100%)
        assert 0.05 <= delays[0] <= 0.15

        # Verify second delay: 0.1-0.2s (200ms * 50-100%)
        assert 0.1 <= delays[1] <= 0.25

        # Verify third delay: 0.2-0.4s (400ms * 50-100%)
        assert 0.2 <= delays[2] <= 0.45

        # Verify delays increase (exponential pattern)
        # Note: Jitter can occasionally make this not strictly increasing
        # but on average the pattern should hold
        assert delays[1] > delays[0] * 0.5  # Allow for jitter variance
        assert delays[2] > delays[1] * 0.5


# ============================================================================
# Test Group 2: Circuit Breaker Tests (4 tests)
# ============================================================================


@pytest.mark.unit
class TestCircuitBreaker:
    """Test circuit breaker for failing dependencies."""

    @pytest.mark.asyncio
    async def test_circuit_closed_normal_operation(self):
        """Test circuit closed during normal operation - all requests pass."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)
        breaker = CircuitBreaker(config)

        # Verify initial state
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

        # Execute successful operations
        mock_func = AsyncMock(return_value="success")

        for i in range(10):
            result = await breaker.execute(mock_func, f"arg{i}")
            assert result == "success"

        # Verify circuit remains closed
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert mock_func.call_count == 10

        # Verify metrics
        metrics = breaker.get_metrics()
        assert metrics["state"] == "closed"
        assert metrics["failure_count"] == 0
        assert metrics["success_count"] == 0  # Only tracked in HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpen,
            CircuitState,
        )

        config = CircuitBreakerConfig(failure_threshold=5, timeout=60.0)
        breaker = CircuitBreaker(config)

        # Execute failing operations
        async def failing_func():
            raise ConnectionError("Service unavailable")

        # First 4 failures - circuit stays closed
        for i in range(4):
            try:
                await breaker.execute(failing_func)
            except ConnectionError:
                pass

        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 4

        # 5th failure - circuit opens
        try:
            await breaker.execute(failing_func)
        except ConnectionError:
            pass

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 5
        assert breaker.last_failure_time is not None

        # Subsequent requests should be rejected immediately
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await breaker.execute(failing_func)

        assert "Circuit breaker is open" in str(exc_info.value)

        # Verify metrics
        metrics = breaker.get_metrics()
        assert metrics["state"] == "open"
        assert metrics["failure_count"] == 5

    @pytest.mark.asyncio
    async def test_circuit_half_open_testing(self):
        """Test circuit enters HALF_OPEN for testing after timeout."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(failure_threshold=3, timeout=0.1)  # 100ms timeout
        breaker = CircuitBreaker(config)

        # Force circuit to open
        async def failing_func():
            raise ConnectionError("Service down")

        for i in range(3):
            try:
                await breaker.execute(failing_func)
            except ConnectionError:
                pass

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)  # Wait > timeout

        # Next request should transition to HALF_OPEN
        async def success_func():
            return "success"

        result = await breaker.execute(success_func)

        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.success_count == 1

        # Verify metrics
        metrics = breaker.get_metrics()
        assert metrics["state"] == "half_open"
        assert metrics["success_count"] == 1

    @pytest.mark.asyncio
    async def test_circuit_closes_after_recovery(self):
        """Test circuit closes after successful tests in HALF_OPEN."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=0.1,  # Need 2 successes to close
        )
        breaker = CircuitBreaker(config)

        # Force circuit to open
        async def failing_func():
            raise ConnectionError("Service down")

        for i in range(3):
            try:
                await breaker.execute(failing_func)
            except ConnectionError:
                pass

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout and transition to HALF_OPEN
        await asyncio.sleep(0.15)

        async def success_func():
            return "success"

        # First success in HALF_OPEN
        result1 = await breaker.execute(success_func)
        assert result1 == "success"
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.success_count == 1

        # Second success - should close circuit
        result2 = await breaker.execute(success_func)
        assert result2 == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.success_count == 0  # Reset after closing
        assert breaker.failure_count == 0  # Reset after closing

        # Verify metrics
        metrics = breaker.get_metrics()
        assert metrics["state"] == "closed"
        assert metrics["failure_count"] == 0


# ============================================================================
# Test Group 3: Integration Tests (2 tests)
# ============================================================================


@pytest.mark.unit
class TestRetryCircuitBreakerIntegration:
    """Test retry and circuit breaker working together."""

    @pytest.mark.asyncio
    async def test_retry_with_circuit_breaker(self):
        """Test retry handler + circuit breaker integration."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitBreakerOpen,
            RetryConfig,
            RetryHandler,
        )

        retry_config = RetryConfig(max_attempts=3, base_delay=0.01)
        circuit_config = CircuitBreakerConfig(failure_threshold=5, timeout=0.1)

        retry_handler = RetryHandler(retry_config)
        circuit_breaker = CircuitBreaker(circuit_config)

        # Simulate service that fails initially then recovers
        call_count = 0

        async def flaky_service():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Transient failure")
            return "success"

        # Execute with both retry and circuit breaker
        async def protected_call():
            return await circuit_breaker.execute(flaky_service)

        result = await retry_handler.execute_with_retry(protected_call)

        # Verify success with retry
        assert result == "success"
        assert call_count == 3

        # Now test circuit breaker opening after persistent failures
        async def always_failing():
            raise ConnectionError("Service down")

        async def protected_failing_call():
            return await circuit_breaker.execute(always_failing)

        # Make calls until circuit opens (5 failures)
        for i in range(5):
            try:
                await protected_failing_call()
            except ConnectionError:
                pass

        # Circuit should be open now
        assert circuit_breaker.state.value == "open"

        # Retry should fail fast with RetryExhausted (wrapping CircuitBreakerOpen)
        from dataflow.platform.resilience import RetryExhausted

        with pytest.raises(RetryExhausted) as exc_info:
            await retry_handler.execute_with_retry(protected_failing_call)

        # Verify the original error is CircuitBreakerOpen
        assert isinstance(exc_info.value.original_error, CircuitBreakerOpen)

    @pytest.mark.asyncio
    async def test_database_operation_with_resilience(self):
        """Test database operation retry with circuit breaker protection."""
        from dataflow.platform.resilience import (
            CircuitBreaker,
            CircuitBreakerConfig,
            RetryConfig,
            RetryHandler,
        )

        retry_config = RetryConfig(max_attempts=3, base_delay=0.01)
        circuit_config = CircuitBreakerConfig(failure_threshold=5, timeout=0.1)

        retry_handler = RetryHandler(retry_config)
        circuit_breaker = CircuitBreaker(circuit_config)

        # Simulate database operation that has transient failures
        attempt_count = 0

        async def database_query():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                # First attempt: connection timeout
                raise ConnectionError("Connection timeout")
            elif attempt_count == 2:
                # Second attempt: temporary lock
                raise Exception("Database locked")
            else:
                # Third attempt: success
                return {"id": 1, "name": "test", "status": "active"}

        # Execute with resilience
        async def resilient_query():
            return await circuit_breaker.execute(database_query)

        result = await retry_handler.execute_with_retry(resilient_query)

        # Verify success after retries
        assert result == {"id": 1, "name": "test", "status": "active"}
        assert attempt_count == 3

        # Verify circuit breaker metrics
        cb_metrics = circuit_breaker.get_metrics()
        assert cb_metrics["state"] == "closed"  # Closed after successful recovery

        # Verify retry metrics
        retry_metrics = retry_handler.get_metrics()
        assert retry_metrics["total_attempts"] == 3
        assert retry_metrics["total_successes"] == 1
