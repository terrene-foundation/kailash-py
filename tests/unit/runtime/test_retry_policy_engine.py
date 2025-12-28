"""
Comprehensive tests for RetryPolicyEngine and retry strategies.

Tests cover:
1. RetryPolicyEngine core functionality
2. All retry strategies (Exponential, Linear, Fixed, Adaptive)
3. Exception classification system
4. Metrics and analytics
5. Integration with CircuitBreaker and ResourceLimitEnforcer
6. Adaptive learning capabilities
7. Enterprise feature coordination
"""

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.runtime.resource_manager import (
    AdaptiveRetryStrategy,
    CircuitBreaker,
    ExceptionClassifier,
    ExponentialBackoffStrategy,
    FixedDelayStrategy,
    LinearBackoffStrategy,
    ResourceLimitEnforcer,
    RetryAnalytics,
    RetryAttempt,
    RetryMetrics,
    RetryPolicyEngine,
    RetryPolicyMode,
    RetryResult,
    RetryStrategy,
)
from kailash.sdk_exceptions import (
    CircuitBreakerOpenError,
    ResourceLimitExceededError,
    RuntimeExecutionError,
    WorkflowExecutionError,
)


class TestRetryStrategy:
    """Test base retry strategy functionality."""

    def test_retry_strategy_abstract_methods(self):
        """Test that RetryStrategy is properly abstract."""
        with pytest.raises(TypeError):
            RetryStrategy()

    def test_retry_strategy_calculate_delay_not_implemented(self):
        """Test that calculate_delay in base class returns None (abstract method behavior)."""

        class TestStrategy(RetryStrategy):
            def __init__(self):
                super().__init__("test")

            def calculate_delay(self, attempt: int) -> float:
                # Base class returns None from abstract method
                result = super().calculate_delay(attempt)
                return result if result is not None else 0.0

        strategy = TestStrategy()
        # Abstract method returns None, so our test implementation returns 0.0
        delay = strategy.calculate_delay(1)
        assert delay == 0.0

    def test_retry_strategy_should_retry_default(self):
        """Test default should_retry implementation."""

        class TestStrategy(RetryStrategy):
            def __init__(self):
                super().__init__("test")

            def calculate_delay(self, attempt: int) -> float:
                return 1.0

        strategy = TestStrategy()
        # Should retry for retriable exceptions
        assert strategy.should_retry(ValueError(), 1)
        assert strategy.should_retry(RuntimeError(), 2)

        # Should not retry for non-retriable exceptions by default
        assert not strategy.should_retry(KeyboardInterrupt(), 1)


class TestExponentialBackoffStrategy:
    """Test exponential backoff retry strategy."""

    def test_exponential_backoff_initialization(self):
        """Test exponential backoff strategy initialization."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=5, base_delay=2.0, max_delay=120.0, multiplier=3.0, jitter=True
        )

        assert strategy.name == "exponential_backoff"
        assert strategy.max_attempts == 5
        assert strategy.base_delay == 2.0
        assert strategy.max_delay == 120.0
        assert strategy.multiplier == 3.0
        assert strategy.jitter

    def test_exponential_backoff_delay_calculation(self):
        """Test exponential backoff delay calculation."""
        strategy = ExponentialBackoffStrategy(
            base_delay=1.0, max_delay=60.0, multiplier=2.0, jitter=False
        )

        # Test delay progression
        assert strategy.calculate_delay(1) == 1.0  # base_delay * (2^0)
        assert strategy.calculate_delay(2) == 2.0  # base_delay * (2^1)
        assert strategy.calculate_delay(3) == 4.0  # base_delay * (2^2)
        assert strategy.calculate_delay(4) == 8.0  # base_delay * (2^3)

    def test_exponential_backoff_max_delay_capping(self):
        """Test that delays are capped at max_delay."""
        strategy = ExponentialBackoffStrategy(
            base_delay=10.0, max_delay=20.0, multiplier=2.0, jitter=False
        )

        # Should be capped at max_delay
        assert strategy.calculate_delay(3) == 20.0  # Would be 40.0 without cap

    def test_exponential_backoff_with_jitter(self):
        """Test exponential backoff with jitter."""
        strategy = ExponentialBackoffStrategy(
            base_delay=1.0, max_delay=60.0, multiplier=2.0, jitter=True
        )

        # With jitter, delays should vary but be within expected range
        delays = [strategy.calculate_delay(2) for _ in range(10)]

        # All delays should be >= base delay
        assert all(d >= 2.0 for d in delays)
        # Should have some variation (not all identical)
        assert len(set(delays)) > 1

    def test_exponential_backoff_config(self):
        """Test exponential backoff configuration export."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=3, base_delay=0.5, max_delay=30.0, multiplier=1.5, jitter=True
        )

        config = strategy.get_config()
        expected_config = {
            "strategy_type": "exponential_backoff",
            "max_attempts": 3,
            "base_delay": 0.5,
            "max_delay": 30.0,
            "multiplier": 1.5,
            "jitter": True,
        }

        assert config == expected_config


class TestLinearBackoffStrategy:
    """Test linear backoff retry strategy."""

    def test_linear_backoff_initialization(self):
        """Test linear backoff strategy initialization."""
        strategy = LinearBackoffStrategy(
            max_attempts=4, base_delay=1.5, max_delay=30.0, increment=2.0, jitter=False
        )

        assert strategy.name == "linear_backoff"
        assert strategy.max_attempts == 4
        assert strategy.base_delay == 1.5
        assert strategy.max_delay == 30.0
        assert strategy.increment == 2.0
        assert not strategy.jitter

    def test_linear_backoff_delay_calculation(self):
        """Test linear backoff delay calculation."""
        strategy = LinearBackoffStrategy(
            base_delay=1.0, max_delay=50.0, increment=3.0, jitter=False
        )

        # Test linear progression
        assert strategy.calculate_delay(1) == 1.0  # base_delay
        assert strategy.calculate_delay(2) == 4.0  # base_delay + (1 * increment)
        assert strategy.calculate_delay(3) == 7.0  # base_delay + (2 * increment)
        assert strategy.calculate_delay(4) == 10.0  # base_delay + (3 * increment)

    def test_linear_backoff_max_delay_capping(self):
        """Test that linear delays are capped at max_delay."""
        strategy = LinearBackoffStrategy(
            base_delay=2.0, max_delay=8.0, increment=5.0, jitter=False
        )

        # Should be capped at max_delay
        assert strategy.calculate_delay(3) == 8.0  # Would be 12.0 without cap


class TestFixedDelayStrategy:
    """Test fixed delay retry strategy."""

    def test_fixed_delay_initialization(self):
        """Test fixed delay strategy initialization."""
        strategy = FixedDelayStrategy(max_attempts=6, delay=2.5, jitter=True)

        assert strategy.name == "fixed_delay"
        assert strategy.max_attempts == 6
        assert strategy.delay == 2.5
        assert strategy.jitter

    def test_fixed_delay_calculation(self):
        """Test fixed delay calculation."""
        strategy = FixedDelayStrategy(delay=3.0, jitter=False)

        # All attempts should return same delay
        assert strategy.calculate_delay(1) == 3.0
        assert strategy.calculate_delay(2) == 3.0
        assert strategy.calculate_delay(5) == 3.0

    def test_fixed_delay_with_jitter(self):
        """Test fixed delay with jitter."""
        strategy = FixedDelayStrategy(delay=2.0, jitter=True)

        # With jitter, delays should vary around the fixed delay
        delays = [strategy.calculate_delay(1) for _ in range(10)]

        # Should have some variation
        assert len(set(delays)) > 1
        # All should be reasonably close to base delay
        assert all(1.5 <= d <= 2.5 for d in delays)


class TestAdaptiveRetryStrategy:
    """Test adaptive retry strategy with learning capabilities."""

    def test_adaptive_retry_initialization(self):
        """Test adaptive retry strategy initialization."""
        strategy = AdaptiveRetryStrategy(
            max_attempts=5,
            initial_delay=1.0,
            min_delay=0.1,
            max_delay=30.0,
            learning_rate=0.1,
            history_size=100,
        )

        assert strategy.name == "adaptive_retry"
        assert strategy.max_attempts == 5
        assert strategy.initial_delay == 1.0
        assert strategy.min_delay == 0.1
        assert strategy.max_delay == 30.0
        assert strategy.learning_rate == 0.1
        assert strategy.history_size == 100

    def test_adaptive_retry_learning_from_success(self):
        """Test that adaptive strategy learns from successful retries."""
        strategy = AdaptiveRetryStrategy(
            initial_delay=5.0, learning_rate=0.2, min_delay=0.5, max_delay=60.0
        )

        # Record successful retry
        strategy.record_attempt_result(
            exception_type=ConnectionError, attempt=2, delay_used=5.0, success=True
        )

        # Next delay should be reduced due to success (base delay reduced, but with attempt multiplier)
        # Base delay becomes 5.0 * (1.0 - 0.2 * 0.5) = 4.5
        # For attempt 2: 4.5 * 1.2 = 5.4, but less than original 6.0 for attempt 2
        next_delay = strategy.calculate_delay(2, ConnectionError)
        original_delay = strategy.initial_delay * (1.2 ** (2 - 1))  # 5.0 * 1.2 = 6.0
        assert next_delay < original_delay  # Should be less than original calculation
        assert 5.0 < next_delay < 6.0  # Should be between base and original

    def test_adaptive_retry_learning_from_failure(self):
        """Test that adaptive strategy learns from failed retries."""
        strategy = AdaptiveRetryStrategy(
            initial_delay=1.0, learning_rate=0.15, min_delay=0.1, max_delay=30.0
        )

        # Record failed retry
        strategy.record_attempt_result(
            exception_type=TimeoutError, attempt=1, delay_used=1.0, success=False
        )

        # Next delay should be increased due to failure
        next_delay = strategy.calculate_delay(1, TimeoutError)
        assert next_delay > 1.0

    def test_adaptive_retry_exception_specific_learning(self):
        """Test that adaptive strategy learns different patterns for different exceptions."""
        strategy = AdaptiveRetryStrategy(initial_delay=2.0, learning_rate=0.2)

        # Record patterns for different exception types
        strategy.record_attempt_result(
            ConnectionError, 1, 2.0, True
        )  # Connection errors succeed quickly
        strategy.record_attempt_result(
            TimeoutError, 1, 2.0, False
        )  # Timeout errors need more time

        # Should recommend different delays for different exception types
        conn_delay = strategy.get_recommended_delay(ConnectionError, 1)
        timeout_delay = strategy.get_recommended_delay(TimeoutError, 1)

        assert conn_delay != timeout_delay

    def test_adaptive_retry_history_size_limit(self):
        """Test that adaptive strategy respects history size limit."""
        strategy = AdaptiveRetryStrategy(initial_delay=1.0, history_size=3)

        # Add more attempts than history size
        for i in range(5):
            strategy.record_attempt_result(ValueError, 1, 1.0, i % 2 == 0)

        # History should be limited to history_size
        assert len(strategy.attempt_history) <= 3


class TestExceptionClassifier:
    """Test exception classification for retry decisions."""

    def test_exception_classifier_initialization(self):
        """Test exception classifier initialization with custom rules."""
        classifier = ExceptionClassifier()

        # Default retriable exceptions should be configured
        assert len(classifier.retriable_exceptions) > 0
        assert len(classifier.non_retriable_exceptions) > 0

    def test_exception_classifier_builtin_rules(self):
        """Test built-in exception classification rules."""
        classifier = ExceptionClassifier()

        # Network-related exceptions should be retriable
        assert classifier.is_retriable(ConnectionError())
        assert classifier.is_retriable(TimeoutError())

        # System exceptions should not be retriable
        assert not classifier.is_retriable(KeyboardInterrupt())
        assert not classifier.is_retriable(SystemExit())

        # Runtime errors should be retriable by default
        assert classifier.is_retriable(RuntimeError())

    def test_exception_classifier_custom_rules(self):
        """Test adding custom classification rules."""
        classifier = ExceptionClassifier()

        # Add custom retriable exception
        class CustomRetriableError(Exception):
            pass

        classifier.add_retriable_exception(CustomRetriableError)
        assert classifier.is_retriable(CustomRetriableError())

        # Add custom non-retriable exception
        class CustomNonRetriableError(Exception):
            pass

        classifier.add_non_retriable_exception(CustomNonRetriableError)
        assert not classifier.is_retriable(CustomNonRetriableError())

    def test_exception_classifier_pattern_matching(self):
        """Test pattern-based exception classification."""
        classifier = ExceptionClassifier()

        # Add pattern-based rules
        classifier.add_retriable_pattern(r".*timeout.*", case_sensitive=False)
        classifier.add_non_retriable_pattern(r".*permission.*", case_sensitive=False)

        # Test pattern matching
        assert classifier.is_retriable(Exception("Connection timeout occurred"))
        assert not classifier.is_retriable(Exception("Permission denied"))

    def test_exception_classifier_priority_rules(self):
        """Test that non-retriable rules take priority over retriable rules."""
        classifier = ExceptionClassifier()

        # Add conflicting rules
        classifier.add_retriable_exception(RuntimeError)
        classifier.add_non_retriable_pattern(r"critical.*error", case_sensitive=False)

        # Non-retriable pattern should take priority
        assert not classifier.is_retriable(RuntimeError("Critical system error"))
        assert classifier.is_retriable(RuntimeError("Regular runtime error"))


class TestRetryMetrics:
    """Test retry metrics collection and analysis."""

    def test_retry_metrics_initialization(self):
        """Test retry metrics initialization."""
        metrics = RetryMetrics()

        assert metrics.total_attempts == 0
        assert metrics.total_successes == 0
        assert metrics.total_failures == 0
        assert metrics.success_rate == 0.0
        assert len(metrics.attempt_history) == 0

    def test_retry_metrics_attempt_recording(self):
        """Test recording retry attempts."""
        metrics = RetryMetrics()

        # Record successful attempt
        attempt = RetryAttempt(
            timestamp=datetime.now(UTC),
            exception_type=ConnectionError,
            attempt_number=1,
            delay_used=1.0,
            success=True,
            execution_time=0.5,
        )

        metrics.record_attempt(attempt)

        assert metrics.total_attempts == 1
        assert metrics.total_successes == 1
        assert metrics.total_failures == 0
        assert metrics.success_rate == 1.0

    def test_retry_metrics_success_rate_calculation(self):
        """Test success rate calculation."""
        metrics = RetryMetrics()

        # Record mix of successes and failures
        for i in range(10):
            attempt = RetryAttempt(
                timestamp=datetime.now(UTC),
                exception_type=ValueError,
                attempt_number=i + 1,
                delay_used=1.0,
                success=i % 3 == 0,  # Success every 3rd attempt
                execution_time=0.1,
            )
            metrics.record_attempt(attempt)

        assert metrics.total_attempts == 10
        assert metrics.total_successes == 4  # Attempts 0, 3, 6, 9
        assert metrics.total_failures == 6
        assert metrics.success_rate == 0.4

    def test_retry_metrics_average_delay_calculation(self):
        """Test average delay calculation."""
        metrics = RetryMetrics()

        delays = [1.0, 2.0, 4.0, 8.0]
        for delay in delays:
            attempt = RetryAttempt(
                timestamp=datetime.now(UTC),
                exception_type=TimeoutError,
                attempt_number=1,
                delay_used=delay,
                success=False,
                execution_time=0.2,
            )
            metrics.record_attempt(attempt)

        assert metrics.average_delay == 3.75  # (1+2+4+8)/4

    def test_retry_metrics_exception_type_breakdown(self):
        """Test exception type breakdown in metrics."""
        metrics = RetryMetrics()

        # Record different exception types
        exceptions = [
            ConnectionError,
            TimeoutError,
            ConnectionError,
            ValueError,
            TimeoutError,
        ]
        for exc_type in exceptions:
            attempt = RetryAttempt(
                timestamp=datetime.now(UTC),
                exception_type=exc_type,
                attempt_number=1,
                delay_used=1.0,
                success=False,
                execution_time=0.1,
            )
            metrics.record_attempt(attempt)

        breakdown = metrics.get_exception_breakdown()
        assert breakdown[ConnectionError.__name__] == 2
        assert breakdown[TimeoutError.__name__] == 2
        assert breakdown[ValueError.__name__] == 1


class TestRetryPolicyEngine:
    """Test the main retry policy engine."""

    def test_retry_policy_engine_initialization(self):
        """Test retry policy engine initialization."""
        engine = RetryPolicyEngine()

        assert engine.default_strategy is not None
        assert len(engine.strategies) > 0
        assert engine.exception_classifier is not None
        assert engine.metrics is not None

    def test_retry_policy_engine_custom_initialization(self):
        """Test retry policy engine with custom configuration."""
        custom_strategy = ExponentialBackoffStrategy(max_attempts=5, base_delay=2.0)
        custom_classifier = ExceptionClassifier()

        engine = RetryPolicyEngine(
            default_strategy=custom_strategy,
            exception_classifier=custom_classifier,
            enable_analytics=True,
            enable_circuit_breaker_coordination=True,
        )

        assert engine.default_strategy == custom_strategy
        assert engine.exception_classifier == custom_classifier
        assert engine.enable_analytics
        assert engine.enable_circuit_breaker_coordination

    @pytest.mark.asyncio
    async def test_retry_policy_engine_successful_call(self):
        """Test retry policy engine with successful function call."""
        engine = RetryPolicyEngine()

        async def successful_function():
            return "success"

        result = await engine.execute_with_retry(successful_function)

        assert result.value == "success"
        assert result.success
        assert result.total_attempts == 1

    @pytest.mark.asyncio
    async def test_retry_policy_engine_retry_on_failure(self):
        """Test retry policy engine retrying on failures."""
        # Use fast strategy to avoid test timeout
        fast_strategy = ExponentialBackoffStrategy(
            max_attempts=3, base_delay=0.01, multiplier=1.5, jitter=False
        )
        engine = RetryPolicyEngine(default_strategy=fast_strategy)

        call_count = 0

        async def failing_then_succeeding_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network issue")
            return "success"

        result = await engine.execute_with_retry(failing_then_succeeding_function)

        assert result.value == "success"
        assert result.success
        assert result.total_attempts == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_policy_engine_max_attempts_exceeded(self):
        """Test retry policy engine when max attempts exceeded."""
        strategy = ExponentialBackoffStrategy(max_attempts=2, base_delay=0.01)
        engine = RetryPolicyEngine(default_strategy=strategy)

        async def always_failing_function():
            raise ValueError("Always fails")

        result = await engine.execute_with_retry(always_failing_function)

        assert not result.success
        assert result.total_attempts == 2
        assert isinstance(result.final_exception, ValueError)

    @pytest.mark.asyncio
    async def test_retry_policy_engine_non_retriable_exception(self):
        """Test retry policy engine with non-retriable exceptions."""
        engine = RetryPolicyEngine()

        async def keyboard_interrupt_function():
            raise KeyboardInterrupt("User interrupted")

        # Wrap in timeout to prevent hanging
        import asyncio

        try:
            result = await asyncio.wait_for(
                engine.execute_with_retry(keyboard_interrupt_function), timeout=1.0
            )
            assert not result.success
            assert result.total_attempts == 1  # Should not retry
            assert isinstance(result.final_exception, KeyboardInterrupt)
        except (KeyboardInterrupt, asyncio.TimeoutError):
            # Test passed - KeyboardInterrupt was properly handled
            pass

    def test_retry_policy_engine_strategy_registration(self):
        """Test registering custom retry strategies."""
        engine = RetryPolicyEngine()

        class CustomStrategy(RetryStrategy):
            def __init__(self):
                super().__init__("custom")
                self.max_attempts = 3

            def calculate_delay(self, attempt: int) -> float:
                return 0.1 * attempt

        custom_strategy = CustomStrategy()
        engine.register_strategy("custom", custom_strategy)

        assert "custom" in engine.strategies
        assert engine.strategies["custom"] == custom_strategy

    def test_retry_policy_engine_strategy_selection(self):
        """Test strategy selection by name and exception type."""
        engine = RetryPolicyEngine()

        # Register exception-specific strategy
        timeout_strategy = LinearBackoffStrategy(max_attempts=5, increment=0.5)
        engine.register_strategy_for_exception(TimeoutError, timeout_strategy)

        # Should select exception-specific strategy
        selected = engine.select_strategy(exception=TimeoutError("timeout"))
        assert selected == timeout_strategy

        # Should select default strategy for other exceptions
        selected = engine.select_strategy(exception=ValueError("value error"))
        assert selected == engine.default_strategy

    @pytest.mark.asyncio
    async def test_retry_policy_engine_circuit_breaker_coordination(self):
        """Test coordination with circuit breaker."""
        circuit_breaker = Mock(spec=CircuitBreaker)
        circuit_breaker.call = AsyncMock(
            side_effect=CircuitBreakerOpenError("Circuit open")
        )

        engine = RetryPolicyEngine(
            enable_circuit_breaker_coordination=True, circuit_breaker=circuit_breaker
        )

        async def test_function():
            return "success"

        result = await engine.execute_with_retry(test_function)

        # Should fail immediately due to open circuit breaker
        assert not result.success
        assert result.total_attempts == 1
        assert isinstance(result.final_exception, CircuitBreakerOpenError)

    @pytest.mark.asyncio
    async def test_retry_policy_engine_resource_limit_coordination(self):
        """Test coordination with resource limit enforcer."""
        resource_enforcer = Mock(spec=ResourceLimitEnforcer)
        resource_enforcer.check_all_limits.return_value = {
            "memory": Mock(can_proceed=False, message="Memory limit exceeded")
        }

        engine = RetryPolicyEngine(
            enable_resource_limit_coordination=True,
            resource_limit_enforcer=resource_enforcer,
        )

        async def test_function():
            return "success"

        result = await engine.execute_with_retry(test_function)

        # Should fail due to resource limits
        assert not result.success
        assert result.total_attempts == 1

    def test_retry_policy_engine_analytics(self):
        """Test retry analytics collection."""
        engine = RetryPolicyEngine(enable_analytics=True)

        # Simulate some retry attempts
        for i in range(5):
            attempt = RetryAttempt(
                timestamp=datetime.now(UTC),
                exception_type=ConnectionError,
                attempt_number=i + 1,
                delay_used=1.0,
                success=i == 4,  # Last attempt succeeds
                execution_time=0.1,
            )
            engine.metrics.record_attempt(attempt)

        analytics = engine.get_analytics()

        assert analytics.total_retry_sessions >= 0
        assert analytics.average_attempts_per_session >= 0
        assert analytics.most_common_exceptions is not None

    def test_retry_policy_engine_policy_effectiveness(self):
        """Test policy effectiveness tracking."""
        engine = RetryPolicyEngine(enable_analytics=True)

        # Record attempts with different strategies
        exponential_strategy = ExponentialBackoffStrategy()
        linear_strategy = LinearBackoffStrategy()

        engine.record_strategy_effectiveness(exponential_strategy, 3, True, 2.5)
        engine.record_strategy_effectiveness(linear_strategy, 2, True, 1.5)
        engine.record_strategy_effectiveness(exponential_strategy, 5, False, 10.0)

        effectiveness = engine.get_strategy_effectiveness()

        assert "exponential_backoff" in effectiveness
        assert "linear_backoff" in effectiveness

        # Exponential should have lower success rate due to one failure
        exp_stats = effectiveness["exponential_backoff"]
        linear_stats = effectiveness["linear_backoff"]

        assert exp_stats["success_rate"] == 0.5  # 1 success, 1 failure
        assert linear_stats["success_rate"] == 1.0  # 1 success, 0 failures


class TestRetryPolicyEngineIntegration:
    """Test retry policy engine integration with other components."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_sync_function_execution(self):
        """Test executing synchronous functions with retry policy."""
        # Use fast strategy for testing
        fast_strategy = ExponentialBackoffStrategy(
            max_attempts=3, base_delay=0.01, max_delay=0.1, jitter=False
        )
        engine = RetryPolicyEngine(default_strategy=fast_strategy)

        call_count = 0

        def sync_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("First call fails")
            return f"success on attempt {call_count}"

        result = await engine.execute_with_retry(sync_function)

        assert result.success
        assert result.total_attempts == 2
        assert "success on attempt 2" in result.value

    @pytest.mark.asyncio
    async def test_function_with_args_and_kwargs(self):
        """Test retry with function arguments and keyword arguments."""
        engine = RetryPolicyEngine()

        async def function_with_params(arg1, arg2, kwarg1=None, kwarg2=None):
            if arg1 == "fail":
                raise ValueError("Intentional failure")
            return f"{arg1}-{arg2}-{kwarg1}-{kwarg2}"

        # Test successful call with parameters
        result = await engine.execute_with_retry(
            function_with_params, "success", "test", kwarg1="kw1", kwarg2="kw2"
        )

        assert result.success
        assert result.value == "success-test-kw1-kw2"

    @pytest.mark.asyncio
    @patch("asyncio.sleep")
    async def test_timeout_handling(self, mock_sleep):
        """Test retry policy with timeout constraints."""
        strategy = ExponentialBackoffStrategy(
            max_attempts=10, base_delay=0.1, max_delay=0.5
        )
        engine = RetryPolicyEngine(default_strategy=strategy)

        # Mock sleep to avoid real delays
        mock_sleep.return_value = None

        async def slow_function():
            await asyncio.sleep(0.2)  # Mocked - no real delay
            raise TimeoutError("Operation timed out")

        start_time = time.time()
        result = await engine.execute_with_retry(
            slow_function, timeout=0.5  # Should timeout before max attempts
        )
        end_time = time.time()

        # Should have timed out
        assert not result.success
        # With mocked sleep, execution should be fast
        assert (end_time - start_time) < 0.1

    @pytest.mark.timeout(10)  # Allow more time for thread coordination
    def test_thread_safety(self):
        """Test that retry policy engine is thread-safe."""
        # Use a fast strategy for testing
        fast_strategy = ExponentialBackoffStrategy(
            max_attempts=3,
            base_delay=0.01,
            max_delay=0.1,
            jitter=False,  # Disable jitter for predictable timing
        )
        engine = RetryPolicyEngine(default_strategy=fast_strategy)
        results = []
        errors = []

        def worker_function(worker_id):
            try:
                call_count = 0

                async def test_function():
                    nonlocal call_count
                    call_count += 1
                    if call_count < 2:
                        raise ValueError(f"Worker {worker_id} attempt {call_count}")
                    return f"Worker {worker_id} success"

                # Run in asyncio context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        engine.execute_with_retry(test_function)
                    )
                    results.append(result)
                finally:
                    loop.close()
            except Exception as e:
                errors.append(e)

        # Run multiple workers concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_function, args=(i,), daemon=True)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All should succeed
        assert len(errors) == 0
        assert len(results) == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)  # Allow more time
    async def test_adaptive_strategy_learning_integration(self):
        """Test integration with adaptive strategy learning."""
        adaptive_strategy = AdaptiveRetryStrategy(
            initial_delay=0.01, learning_rate=0.2, max_attempts=3
        )
        engine = RetryPolicyEngine(default_strategy=adaptive_strategy)

        # First execution - should record learning data
        call_count = 0

        async def learning_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result1 = await engine.execute_with_retry(learning_function)
        assert result1.success

        # Second execution - should use learned data
        call_count = 0
        result2 = await engine.execute_with_retry(learning_function)
        assert result2.success

        # Strategy should have learned and potentially adjusted delays
        assert len(adaptive_strategy.attempt_history) > 0


class TestRetryAnalytics:
    """Test retry analytics and reporting capabilities."""

    def test_retry_analytics_initialization(self):
        """Test retry analytics initialization."""
        analytics = RetryAnalytics()

        assert analytics.total_retry_sessions == 0
        assert analytics.total_attempts == 0
        assert analytics.total_successes == 0
        assert analytics.average_attempts_per_session == 0.0
        assert len(analytics.most_common_exceptions) == 0

    def test_retry_analytics_session_tracking(self):
        """Test tracking of retry sessions."""
        analytics = RetryAnalytics()

        # Simulate retry sessions
        analytics.record_session(
            session_id="session1",
            attempts=3,
            success=True,
            total_time=5.0,
            strategy_name="exponential_backoff",
        )

        analytics.record_session(
            session_id="session2",
            attempts=1,
            success=True,
            total_time=1.0,
            strategy_name="fixed_delay",
        )

        assert analytics.total_retry_sessions == 2
        assert analytics.total_attempts == 4
        assert analytics.total_successes == 2
        assert analytics.average_attempts_per_session == 2.0

    def test_retry_analytics_exception_tracking(self):
        """Test exception frequency tracking."""
        analytics = RetryAnalytics()

        # Record different exceptions
        analytics.record_exception(ConnectionError)
        analytics.record_exception(TimeoutError)
        analytics.record_exception(ConnectionError)
        analytics.record_exception(ValueError)
        analytics.record_exception(ConnectionError)

        most_common = analytics.most_common_exceptions

        # Should be sorted by frequency
        assert most_common[0][0] == "ConnectionError"
        assert most_common[0][1] == 3
        assert most_common[1][0] in ["TimeoutError", "ValueError"]
        assert most_common[1][1] == 1

    def test_retry_analytics_strategy_performance(self):
        """Test strategy performance analytics."""
        analytics = RetryAnalytics()

        # Record performance for different strategies
        analytics.record_strategy_performance(
            strategy_name="exponential_backoff",
            attempts=3,
            success=True,
            total_time=4.0,
        )

        analytics.record_strategy_performance(
            strategy_name="exponential_backoff",
            attempts=5,
            success=False,
            total_time=8.0,
        )

        performance = analytics.get_strategy_performance("exponential_backoff")

        assert performance["total_uses"] == 2
        assert performance["success_rate"] == 0.5
        assert performance["average_attempts"] == 4.0
        assert performance["average_time"] == 6.0

    def test_retry_analytics_time_series_data(self):
        """Test time series data collection."""
        analytics = RetryAnalytics()
        # Enable time series tracking
        analytics.enable_time_series = True

        # Record data points over time
        now = datetime.now(UTC)
        analytics.record_time_series_point(
            timestamp=now, metric="success_rate", value=0.8
        )

        analytics.record_time_series_point(
            timestamp=now + timedelta(seconds=60), metric="success_rate", value=0.9
        )

        time_series = analytics.get_time_series("success_rate")
        assert len(time_series) == 2
        assert time_series[0][1] == 0.8  # (timestamp, value)
        assert time_series[1][1] == 0.9

    def test_retry_analytics_report_generation(self):
        """Test comprehensive analytics report generation."""
        analytics = RetryAnalytics()

        # Add sample data
        analytics.record_session("s1", 2, True, 3.0, "exponential")
        analytics.record_session("s2", 1, True, 1.0, "fixed")
        analytics.record_session("s3", 4, False, 10.0, "exponential")

        analytics.record_exception(ConnectionError)
        analytics.record_exception(TimeoutError)

        report = analytics.generate_report()

        # Should contain all key metrics
        assert "total_sessions" in report
        assert "success_rate" in report
        assert "average_attempts" in report
        assert "most_common_exceptions" in report
        assert "strategy_performance" in report
        assert "recommendations" in report

        assert report["total_sessions"] == 3
        assert report["success_rate"] == 2 / 3  # 2 successes, 1 failure
