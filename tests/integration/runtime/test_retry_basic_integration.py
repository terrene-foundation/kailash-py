"""
Basic integration tests for retry policy engine with LocalRuntime.

Simple tests to verify the retry policy system is properly integrated
without complex workflow execution scenarios.
"""

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.resource_manager import (
    AdaptiveRetryStrategy,
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    RetryPolicyEngine,
    RetryPolicyMode,
)


class TestRetryPolicyBasicIntegration:
    """Test basic retry policy integration with LocalRuntime."""

    def test_retry_policy_initialization(self):
        """Test retry policy initialization in LocalRuntime."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 5,
                "base_delay": 0.1,
                "multiplier": 2.0,
            },
            "enable_analytics": True,
            "mode": "adaptive",
        }

        runtime = LocalRuntime(retry_policy_config=retry_config)

        # Verify retry policy engine is initialized
        assert runtime._retry_policy_engine is not None
        assert runtime._enable_retry_coordination

        # Verify configuration
        config = runtime.get_retry_configuration()
        assert config is not None
        assert config["mode"] == "adaptive"
        assert config["enable_analytics"]
        assert config["default_strategy"]["strategy_type"] == "exponential_backoff"

    def test_retry_policy_with_circuit_breaker(self):
        """Test retry policy coordination with circuit breaker."""
        retry_config = {
            "default_strategy": {"type": "fixed_delay", "max_attempts": 3, "delay": 0.1}
        }

        circuit_breaker_config = {
            "name": "test_breaker",
            "failure_threshold": 3,
            "timeout_seconds": 1,
            "recovery_threshold": 2,
        }

        runtime = LocalRuntime(
            retry_policy_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
        )

        # Verify both systems are initialized and coordinated
        assert runtime._retry_policy_engine is not None
        assert runtime._circuit_breaker is not None
        assert runtime._retry_policy_engine.enable_circuit_breaker_coordination
        assert runtime._retry_policy_engine.circuit_breaker is runtime._circuit_breaker

    def test_retry_policy_with_resource_limits(self):
        """Test retry policy coordination with resource limits."""
        retry_config = {
            "default_strategy": {
                "type": "linear_backoff",
                "max_attempts": 4,
                "base_delay": 0.05,
                "increment": 0.05,
            }
        }

        resource_limits = {
            "max_memory_mb": 512,
            "max_connections": 10,
            "enforcement_policy": "adaptive",
        }

        runtime = LocalRuntime(
            retry_policy_config=retry_config, resource_limits=resource_limits
        )

        # Verify coordination
        assert runtime._retry_policy_engine is not None
        assert runtime._resource_enforcer is not None
        assert runtime._retry_policy_engine.enable_resource_limit_coordination
        assert (
            runtime._retry_policy_engine.resource_limit_enforcer
            is runtime._resource_enforcer
        )

    def test_retry_policy_public_interface(self):
        """Test the public interface for retry policy management."""
        retry_config = {
            "default_strategy": {"type": "exponential_backoff", "max_attempts": 3},
            "enable_analytics": True,
        }

        runtime = LocalRuntime(retry_policy_config=retry_config)

        # Test getter methods
        engine = runtime.get_retry_policy_engine()
        assert engine is not None
        assert isinstance(engine, RetryPolicyEngine)

        config = runtime.get_retry_configuration()
        assert config is not None
        assert "mode" in config
        assert "default_strategy" in config

        # Initial metrics should be empty or None
        metrics = runtime.get_retry_metrics_summary()
        if metrics is not None:
            assert metrics["total_attempts"] == 0

        analytics = runtime.get_retry_analytics()
        if analytics is not None:
            assert analytics["total_sessions"] == 0

        effectiveness = runtime.get_strategy_effectiveness()
        assert isinstance(effectiveness, dict)

    def test_retry_strategy_registration(self):
        """Test registering custom retry strategies."""
        runtime = LocalRuntime(retry_policy_config={"enable_analytics": True})

        # Create custom strategies
        custom_exponential = ExponentialBackoffStrategy(
            max_attempts=10, base_delay=0.5, multiplier=1.5
        )

        custom_adaptive = AdaptiveRetryStrategy(
            max_attempts=7, initial_delay=0.2, learning_rate=0.2
        )

        # Register strategies
        runtime.register_retry_strategy("custom_exponential", custom_exponential)
        runtime.register_retry_strategy_for_exception(ValueError, custom_adaptive)

        # Verify registration
        config = runtime.get_retry_configuration()
        assert "custom_exponential" in config["registered_strategies"]
        assert "ValueError" in config["exception_specific_strategies"]

    def test_exception_classification_management(self):
        """Test runtime management of exception classification."""
        runtime = LocalRuntime(retry_policy_config={"enable_analytics": True})

        # Custom exception types
        class CustomRetriableError(Exception):
            pass

        class CustomNonRetriableError(Exception):
            pass

        # Add custom exception classifications
        runtime.add_retriable_exception(CustomRetriableError)
        runtime.add_non_retriable_exception(CustomNonRetriableError)

        # Verify classifications
        config = runtime.get_retry_configuration()
        rules = config["classification_rules"]
        assert "CustomRetriableError" in rules["retriable_exceptions"]
        assert "CustomNonRetriableError" in rules["non_retriable_exceptions"]

    def test_retry_metrics_reset(self):
        """Test metrics reset functionality."""
        runtime = LocalRuntime(retry_policy_config={"enable_analytics": True})

        # Reset metrics (should not raise error even if no metrics exist)
        runtime.reset_retry_metrics()

        # Verify methods don't raise errors
        metrics = runtime.get_retry_metrics_summary()
        analytics = runtime.get_retry_analytics()
        effectiveness = runtime.get_strategy_effectiveness()

        # These may be None or empty, but shouldn't raise errors
        assert metrics is None or isinstance(metrics, dict)
        assert analytics is None or isinstance(analytics, dict)
        assert isinstance(effectiveness, dict)

    def test_retry_policy_without_config(self):
        """Test LocalRuntime without retry policy configuration."""
        runtime = LocalRuntime()

        # Verify retry policy is not initialized
        assert runtime._retry_policy_engine is None
        assert not runtime._enable_retry_coordination

        # Public interface should handle gracefully
        assert runtime.get_retry_policy_engine() is None
        assert runtime.get_retry_configuration() is None
        assert runtime.get_retry_metrics_summary() is None
        assert runtime.get_retry_analytics() is None
        assert runtime.get_strategy_effectiveness() == {}

    def test_comprehensive_enterprise_initialization(self):
        """Test initialization with all enterprise features."""
        retry_config = {
            "default_strategy": {
                "type": "adaptive_retry",
                "max_attempts": 4,
                "initial_delay": 0.05,
                "learning_rate": 0.2,
            },
            "enable_analytics": True,
            "mode": "adaptive",
        }

        circuit_breaker_config = {"failure_threshold": 3, "timeout_seconds": 1}

        resource_limits = {"max_connections": 5, "enforcement_policy": "adaptive"}

        runtime = LocalRuntime(
            retry_policy_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
            resource_limits=resource_limits,
            enable_async=True,
            enable_monitoring=True,
        )

        # Verify all enterprise components are initialized and coordinated
        assert runtime._retry_policy_engine is not None
        assert runtime._circuit_breaker is not None
        assert runtime._resource_enforcer is not None

        # Verify coordination
        assert runtime._retry_policy_engine.enable_circuit_breaker_coordination
        assert runtime._retry_policy_engine.enable_resource_limit_coordination
        assert runtime._retry_policy_engine.circuit_breaker is runtime._circuit_breaker
        assert (
            runtime._retry_policy_engine.resource_limit_enforcer
            is runtime._resource_enforcer
        )

        # Verify configuration
        config = runtime.get_retry_configuration()
        assert config["mode"] == "adaptive"
        assert config["enable_analytics"]
        assert config["default_strategy"]["strategy_type"] == "adaptive_retry"
        assert config["enable_circuit_breaker_coordination"]
        assert config["enable_resource_limit_coordination"]


class TestRetryPolicyEngineDirectUsage:
    """Test direct usage of RetryPolicyEngine."""

    @pytest.mark.asyncio
    async def test_direct_retry_engine_success(self):
        """Test direct usage of retry engine with successful function."""
        engine = RetryPolicyEngine()

        async def successful_function():
            return "success"

        result = await engine.execute_with_retry(successful_function)

        assert result.success
        assert result.value == "success"
        assert result.total_attempts == 1

    @pytest.mark.asyncio
    async def test_direct_retry_engine_with_transient_failure(self):
        """Test direct usage of retry engine with transient failure."""
        strategy = ExponentialBackoffStrategy(max_attempts=3, base_delay=0.01)
        engine = RetryPolicyEngine(default_strategy=strategy)

        call_count = 0

        async def failing_then_succeeding_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient failure")
            return "success"

        result = await engine.execute_with_retry(failing_then_succeeding_function)

        assert result.success
        assert result.value == "success"
        assert result.total_attempts == 2

    @pytest.mark.asyncio
    async def test_direct_retry_engine_with_non_retriable_exception(self):
        """Test direct usage with non-retriable exception."""
        engine = RetryPolicyEngine()

        async def keyboard_interrupt_function():
            raise KeyboardInterrupt("User interrupted")

        result = await engine.execute_with_retry(keyboard_interrupt_function)

        assert not result.success
        assert result.total_attempts == 1
        assert isinstance(result.final_exception, KeyboardInterrupt)

    @pytest.mark.asyncio
    async def test_adaptive_strategy_learning(self):
        """Test adaptive strategy learning."""
        adaptive_strategy = AdaptiveRetryStrategy(
            max_attempts=3, initial_delay=0.1, learning_rate=0.3
        )
        engine = RetryPolicyEngine(default_strategy=adaptive_strategy)

        # Execute function that fails once then succeeds
        call_count = 0

        async def learning_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Learning failure")
            return f"success on attempt {call_count}"

        result = await engine.execute_with_retry(learning_function)

        assert result.success
        assert "success on attempt 2" in result.value
        assert result.total_attempts == 2

        # Verify adaptive strategy learned
        learning_stats = adaptive_strategy.get_learning_stats()
        assert learning_stats["total_attempts"] > 0
        assert "ConnectionError" in learning_stats["learned_delays"]
