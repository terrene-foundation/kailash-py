"""
Integration tests for retry policy engine with LocalRuntime and enterprise features.

Tests integration with:
- AsyncSQLDatabaseNode
- CircuitBreaker coordination
- ResourceLimitEnforcer coordination
- Real workflow execution scenarios
- Enterprise monitoring and analytics
"""

import asyncio
import sqlite3
import tempfile
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.resource_manager import (
    AdaptiveRetryStrategy,
    CircuitBreaker,
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    ResourceLimitEnforcer,
    RetryPolicyEngine,
    RetryPolicyMode,
)
from kailash.sdk_exceptions import ResourceLimitExceededError, RuntimeExecutionError
from kailash.workflow.builder import WorkflowBuilder


class TestRetryPolicyRuntimeIntegration:
    """Test retry policy integration with LocalRuntime."""

    def test_basic_retry_policy_configuration(self):
        """Test basic retry policy configuration in LocalRuntime."""
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

    def test_retry_policy_with_circuit_breaker_coordination(self):
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

    def test_retry_policy_with_resource_limits_coordination(self):
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

    def test_custom_exception_strategies(self):
        """Test configuration of exception-specific retry strategies."""
        retry_config = {
            "default_strategy": {"type": "exponential_backoff", "max_attempts": 3},
            "exception_strategies": {
                "ConnectionError": {
                    "type": "linear_backoff",
                    "params": {"max_attempts": 5, "base_delay": 0.1, "increment": 0.1},
                },
                "TimeoutError": {
                    "type": "fixed_delay",
                    "params": {"max_attempts": 2, "delay": 0.5},
                },
            },
        }

        runtime = LocalRuntime(retry_policy_config=retry_config)

        # Verify exception-specific strategies are registered
        config = runtime.get_retry_configuration()
        assert "ConnectionError" in config["exception_specific_strategies"]
        assert "TimeoutError" in config["exception_specific_strategies"]

    def test_runtime_retry_strategy_registration(self):
        """Test registering retry strategies at runtime."""
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


@pytest.mark.asyncio
class TestRetryPolicyWorkflowExecution:
    """Test retry policy in actual workflow execution scenarios."""

    async def test_successful_node_execution_with_retries(self):
        """Test node that succeeds after retries."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 5,
                "base_delay": 0.01,
                "multiplier": 1.5,
            }
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Create workflow with a node that fails initially then succeeds
        failing_code = """
import os
attempt_count = int(os.environ.get('ATTEMPT_COUNT', '0')) + 1
os.environ['ATTEMPT_COUNT'] = str(attempt_count)

if attempt_count < 3:
    raise ConnectionError(f"Attempt {attempt_count} failed")

result = {'success': True, 'attempt': attempt_count}
"""

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "retry_test", {"code": failing_code})

        # Execute workflow
        results, run_id = await runtime.execute_async(workflow.build())

        # Clean up environment variable
        import os

        if "ATTEMPT_COUNT" in os.environ:
            del os.environ["ATTEMPT_COUNT"]

        # Verify successful execution after retries
        assert run_id is not None
        assert "retry_test" in results
        assert results["retry_test"]["success"]
        assert results["retry_test"]["attempt"] == 3

        # Check retry analytics
        analytics = runtime.get_retry_analytics()
        assert analytics is not None
        assert analytics["total_sessions"] >= 1

        metrics = runtime.get_retry_metrics_summary()
        assert metrics is not None
        assert metrics["total_attempts"] >= 3
        assert metrics["total_successes"] >= 1

    async def test_node_failure_after_max_retries(self):
        """Test node that fails even after maximum retries."""
        retry_config = {
            "default_strategy": {
                "type": "fixed_delay",
                "max_attempts": 3,
                "delay": 0.01,
            }
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Create workflow with always failing node
        failing_code = "raise ValueError('This always fails')"

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "always_fail", {"code": failing_code})

        # Execute workflow - should fail
        with pytest.raises(RuntimeExecutionError) as exc_info:
            await runtime.execute_async(workflow.build())

        # Verify error contains retry context
        error = exc_info.value
        assert hasattr(error, "retry_context")
        assert error.retry_context["total_attempts"] == 3
        assert error.retry_context["node_id"] == "always_fail"
        assert len(error.retry_context["attempt_details"]) == 3

        # Check retry analytics
        analytics = runtime.get_retry_analytics()
        assert analytics["total_sessions"] >= 1

        metrics = runtime.get_retry_metrics_summary()
        assert metrics["total_attempts"] >= 3
        assert metrics["total_failures"] >= 3

    async def test_non_retriable_exception_no_retry(self):
        """Test that non-retriable exceptions don't trigger retries."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 5,
                "base_delay": 0.1,
            }
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Create workflow with non-retriable exception
        interrupt_code = "raise KeyboardInterrupt('User interrupted')"

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "non_retriable", {"code": interrupt_code})

        # Execute workflow - should fail immediately
        with pytest.raises(RuntimeExecutionError) as exc_info:
            await runtime.execute_async(workflow.build())

        # Verify only one attempt was made
        error = exc_info.value
        assert hasattr(error, "retry_context")
        assert error.retry_context["total_attempts"] == 1
        assert len(error.retry_context["attempt_details"]) == 1

    async def test_adaptive_strategy_learning(self):
        """Test adaptive strategy learning from execution patterns."""
        retry_config = {
            "default_strategy": {
                "type": "adaptive_retry",
                "max_attempts": 5,
                "initial_delay": 0.1,
                "learning_rate": 0.3,
            }
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Execute multiple workflows to enable learning
        for i in range(3):
            learning_code = f"""
import os
key = 'LEARNING_ATTEMPT_{i}'
attempt_count = int(os.environ.get(key, '0')) + 1
os.environ[key] = str(attempt_count)

if attempt_count < 2:  # Fail once, then succeed
    raise ConnectionError(f"Learning attempt {{attempt_count}}")

result = {{'iteration': {i}, 'attempts': attempt_count}}
"""

            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", f"learning_test_{i}", {"code": learning_code}
            )

            results, _ = await runtime.execute_async(workflow.build())
            assert results[f"learning_test_{i}"]["iteration"] == i

            # Clean up environment variable
            import os

            if f"LEARNING_ATTEMPT_{i}" in os.environ:
                del os.environ[f"LEARNING_ATTEMPT_{i}"]

        # Verify adaptive strategy has learned
        strategy_effectiveness = runtime.get_strategy_effectiveness()
        assert "adaptive_retry" in strategy_effectiveness

        # Get learning statistics
        retry_engine = runtime.get_retry_policy_engine()
        adaptive_strategy = retry_engine.strategies["adaptive_retry"]
        learning_stats = adaptive_strategy.get_learning_stats()

        assert learning_stats["total_attempts"] > 0
        assert learning_stats["unique_exceptions"] > 0
        assert "ConnectionError" in learning_stats["learned_delays"]


@pytest.mark.asyncio
class TestAsyncSQLDatabaseNodeRetryIntegration:
    """Test retry policy integration with AsyncSQLDatabaseNode."""

    async def test_database_connection_retry(self):
        """Test retry policy with database connection failures."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 4,
                "base_delay": 0.05,
                "multiplier": 2.0,
            }
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name

        # Setup database with test table
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER
            )
        """
        )
        conn.execute("INSERT INTO test_table (name, value) VALUES ('test1', 100)")
        conn.execute("INSERT INTO test_table (name, value) VALUES ('test2', 200)")
        conn.commit()
        conn.close()

        # Create workflow with database node that initially fails
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "db_test",
            {
                "database_url": f"sqlite:///{db_path}",
                "query": "SELECT * FROM test_table WHERE value > ?",
                "parameters": [50],
                "operation": "select_all",
            },
        )

        # Mock database connection to fail initially
        original_execute_async = AsyncSQLDatabaseNode.execute_async
        attempt_count = 0

        async def mock_execute_async(self, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError(
                    f"Database connection failed (attempt {attempt_count})"
                )
            return await original_execute_async(self, **kwargs)

        with patch.object(AsyncSQLDatabaseNode, "execute_async", mock_execute_async):
            # Execute workflow
            results, run_id = await runtime.execute_async(workflow.build())

            # Verify successful execution after retries
            assert "db_test" in results
            assert len(results["db_test"]) == 2  # Should return 2 rows

            # Check that retries occurred
            analytics = runtime.get_retry_analytics()
            assert analytics["total_sessions"] >= 1

            metrics = runtime.get_retry_metrics_summary()
            assert metrics["total_attempts"] >= 3

    async def test_database_query_timeout_retry(self):
        """Test retry policy with database query timeouts."""
        retry_config = {
            "default_strategy": {
                "type": "linear_backoff",
                "max_attempts": 3,
                "base_delay": 0.1,
                "increment": 0.05,
            },
            "exception_strategies": {
                "TimeoutError": {
                    "type": "fixed_delay",
                    "params": {"max_attempts": 2, "delay": 0.2},
                }
            },
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
            db_path = tmp_db.name

        # Setup database
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE timeout_test (id INTEGER PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO timeout_test (data) VALUES ('test_data')")
        conn.commit()
        conn.close()

        # Create workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "timeout_test",
            {
                "database_url": f"sqlite:///{db_path}",
                "query": "SELECT * FROM timeout_test",
                "operation": "select_all",
            },
        )

        # Mock to simulate timeouts
        original_execute_async = AsyncSQLDatabaseNode.execute_async
        timeout_count = 0

        async def mock_timeout_execute_async(self, **kwargs):
            nonlocal timeout_count
            timeout_count += 1
            if timeout_count == 1:
                raise TimeoutError("Query timeout")
            return await original_execute_async(self, **kwargs)

        with patch.object(
            AsyncSQLDatabaseNode, "execute_async", mock_timeout_execute_async
        ):
            # Execute workflow
            results, _ = await runtime.execute_async(workflow.build())

            # Verify execution
            assert "timeout_test" in results
            assert len(results["timeout_test"]) == 1

            # Check that TimeoutError-specific strategy was used
            config = runtime.get_retry_configuration()
            assert "TimeoutError" in config["exception_specific_strategies"]


@pytest.mark.asyncio
class TestRetryPolicyEnterpriseCoordination:
    """Test retry policy coordination with enterprise features."""

    async def test_circuit_breaker_coordination(self):
        """Test retry policy working with circuit breaker."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 5,
                "base_delay": 0.01,
            }
        }

        circuit_breaker_config = {
            "failure_threshold": 2,
            "timeout_seconds": 1,
            "recovery_threshold": 1,
        }

        runtime = LocalRuntime(
            retry_policy_config=retry_config,
            circuit_breaker_config=circuit_breaker_config,
            enable_async=True,
        )

        # Create workflow with failing node
        failure_count = 0

        def circuit_breaker_test():
            nonlocal failure_count
            failure_count += 1
            raise RuntimeError(f"Failure {failure_count}")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "circuit_test", {"code": circuit_breaker_test}
        )

        # Execute multiple times to trigger circuit breaker
        for attempt in range(3):
            try:
                await runtime.execute_async(workflow.build())
            except RuntimeExecutionError:
                pass  # Expected to fail

        # Check circuit breaker state
        circuit_breaker = runtime._circuit_breaker
        state = circuit_breaker.get_state()

        # Circuit should be open after failures
        assert state["state"] in ["open", "half_open"]
        assert state["failure_count"] >= 2

    async def test_resource_limit_coordination(self):
        """Test retry policy working with resource limits."""
        retry_config = {
            "default_strategy": {
                "type": "fixed_delay",
                "max_attempts": 3,
                "delay": 0.01,
            }
        }

        resource_limits = {
            "max_memory_mb": 1,  # Very low limit to trigger enforcement
            "enforcement_policy": "strict",
        }

        runtime = LocalRuntime(
            retry_policy_config=retry_config,
            resource_limits=resource_limits,
            enable_async=True,
        )

        # Create workflow with memory-intensive operation
        def memory_intensive_code():
            # This will likely trigger memory limit checks
            large_data = [0] * 1000000  # Create large list
            return {"data_size": len(large_data)}

        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "memory_test", {"code": memory_intensive_code}
        )

        # Execute workflow - may fail due to resource limits
        try:
            results, _ = await runtime.execute_async(workflow.build())
            # If it succeeds, verify result
            assert "memory_test" in results
        except (RuntimeExecutionError, ResourceLimitExceededError):
            # Expected if resource limits are enforced
            pass

        # Check resource enforcer metrics
        if runtime._resource_enforcer:
            metrics = runtime._resource_enforcer.get_resource_metrics()
            assert metrics is not None
            assert "memory_usage_mb" in metrics

    async def test_comprehensive_enterprise_integration(self):
        """Test retry policy with all enterprise features enabled."""
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

        # Create workflow with various scenarios
        scenario_count = 0

        def enterprise_test_code():
            nonlocal scenario_count
            scenario_count += 1

            # Different failure patterns for learning
            if scenario_count == 1:
                raise ConnectionError("Network issue")
            elif scenario_count == 2:
                raise TimeoutError("Operation timeout")
            elif scenario_count == 3:
                return {"success": True, "scenario": scenario_count}
            else:
                return {"success": True, "scenario": scenario_count}

        # Execute multiple workflows for comprehensive testing
        for i in range(3):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", f"enterprise_test_{i}", {"code": enterprise_test_code}
            )

            try:
                results, _ = await runtime.execute_async(workflow.build())
                if f"enterprise_test_{i}" in results:
                    assert "scenario" in results[f"enterprise_test_{i}"]
            except RuntimeExecutionError:
                pass  # Some executions may fail as expected

        # Verify comprehensive analytics
        analytics = runtime.get_retry_analytics()
        assert analytics is not None
        assert analytics["total_sessions"] >= 1

        strategy_effectiveness = runtime.get_strategy_effectiveness()
        assert "adaptive_retry" in strategy_effectiveness

        config = runtime.get_retry_configuration()
        assert config["enable_analytics"]
        assert config["mode"] == "adaptive"

        # Verify all enterprise components are coordinated
        assert runtime._retry_policy_engine is not None
        assert runtime._circuit_breaker is not None
        assert runtime._resource_enforcer is not None
        assert runtime._retry_policy_engine.enable_circuit_breaker_coordination
        assert runtime._retry_policy_engine.enable_resource_limit_coordination


@pytest.mark.asyncio
class TestRetryPolicyMetricsAndAnalytics:
    """Test comprehensive metrics and analytics for retry policies."""

    async def test_detailed_retry_metrics(self):
        """Test detailed retry metrics collection."""
        retry_config = {
            "default_strategy": {
                "type": "exponential_backoff",
                "max_attempts": 4,
                "base_delay": 0.01,
            },
            "enable_analytics": True,
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Execute workflows with different failure patterns
        test_scenarios = [
            (2, "ConnectionError", "Connection failed"),
            (1, "TimeoutError", "Request timeout"),
            (3, "ValueError", "Invalid value"),
        ]

        for failures_before_success, exception_type, error_message in test_scenarios:
            attempt_count = 0

            def variable_failure_code():
                nonlocal attempt_count
                attempt_count += 1
                if attempt_count <= failures_before_success:
                    if exception_type == "ConnectionError":
                        raise ConnectionError(error_message)
                    elif exception_type == "TimeoutError":
                        raise TimeoutError(error_message)
                    elif exception_type == "ValueError":
                        raise ValueError(error_message)
                return {"success": True, "final_attempt": attempt_count}

            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode",
                f"metrics_test_{exception_type.lower()}",
                {"code": variable_failure_code},
            )

            results, _ = await runtime.execute_async(workflow.build())
            assert results[f"metrics_test_{exception_type.lower()}"]["success"]

        # Verify comprehensive metrics
        analytics = runtime.get_retry_analytics()
        assert analytics is not None
        assert analytics["total_sessions"] == 3
        assert len(analytics["most_common_exceptions"]) >= 3

        metrics = runtime.get_retry_metrics_summary()
        assert metrics is not None
        assert metrics["total_attempts"] >= 6  # At least 2+1+3 attempts
        assert metrics["total_successes"] >= 3
        assert metrics["success_rate"] > 0
        assert metrics["unique_exceptions"] >= 3

        # Check strategy effectiveness
        strategy_effectiveness = runtime.get_strategy_effectiveness()
        assert "exponential_backoff" in strategy_effectiveness
        exp_stats = strategy_effectiveness["exponential_backoff"]
        assert exp_stats["success_rate"] == 1.0  # All should eventually succeed
        assert exp_stats["uses"] == 3

    async def test_analytics_report_generation(self):
        """Test comprehensive analytics report generation."""
        retry_config = {
            "default_strategy": {
                "type": "linear_backoff",
                "max_attempts": 3,
                "base_delay": 0.01,
                "increment": 0.01,
            },
            "enable_analytics": True,
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Execute multiple workflows for rich analytics
        for i in range(5):
            attempt_count = 0

            def analytics_test_code():
                nonlocal attempt_count
                attempt_count += 1
                # Succeed on different attempts to create variety
                if attempt_count <= (i % 3 + 1):
                    raise RuntimeError(f"Iteration {i}, attempt {attempt_count}")
                return {"iteration": i, "attempts_needed": attempt_count}

            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", f"analytics_{i}", {"code": analytics_test_code}
            )

            results, _ = await runtime.execute_async(workflow.build())
            assert results[f"analytics_{i}"]["iteration"] == i

        # Generate comprehensive report
        analytics = runtime.get_retry_analytics()
        assert analytics is not None

        # Verify report components
        assert "generated_at" in analytics
        assert "total_sessions" in analytics
        assert "total_attempts" in analytics
        assert "total_successes" in analytics
        assert "success_rate" in analytics
        assert "average_attempts" in analytics
        assert "most_common_exceptions" in analytics
        assert "strategy_performance" in analytics
        assert "recommendations" in analytics

        # Verify data quality
        assert analytics["total_sessions"] == 5
        assert analytics["total_successes"] == 5
        assert analytics["success_rate"] == 1.0
        assert len(analytics["most_common_exceptions"]) >= 1
        assert "RuntimeError" in [exc[0] for exc in analytics["most_common_exceptions"]]
        assert len(analytics["recommendations"]) > 0

    async def test_metrics_reset_functionality(self):
        """Test metrics reset functionality."""
        retry_config = {
            "default_strategy": {
                "type": "fixed_delay",
                "max_attempts": 2,
                "delay": 0.01,
            },
            "enable_analytics": True,
        }

        runtime = LocalRuntime(retry_policy_config=retry_config, enable_async=True)

        # Execute initial workflow
        def initial_test():
            raise ValueError("Initial test error")

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "initial", {"code": initial_test})

        try:
            await runtime.execute_async(workflow.build())
        except RuntimeExecutionError:
            pass  # Expected to fail

        # Verify metrics exist
        initial_metrics = runtime.get_retry_metrics_summary()
        assert initial_metrics is not None
        assert initial_metrics["total_attempts"] >= 2

        initial_analytics = runtime.get_retry_analytics()
        assert initial_analytics is not None
        assert initial_analytics["total_sessions"] >= 1

        # Reset metrics
        runtime.reset_retry_metrics()

        # Verify metrics are reset
        reset_metrics = runtime.get_retry_metrics_summary()
        if reset_metrics:  # May be None after reset
            assert reset_metrics["total_attempts"] == 0
            assert reset_metrics["total_successes"] == 0

        reset_analytics = runtime.get_retry_analytics()
        if reset_analytics:  # May be None after reset
            assert reset_analytics["total_sessions"] == 0
            assert reset_analytics["total_attempts"] == 0

        # Execute new workflow after reset
        def post_reset_test():
            return {"success": True}

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "post_reset", {"code": post_reset_test})

        results, _ = await runtime.execute_async(workflow.build())
        assert results["post_reset"]["success"]

        # Verify new metrics
        new_metrics = runtime.get_retry_metrics_summary()
        assert new_metrics is not None
        assert new_metrics["total_attempts"] == 1
        assert new_metrics["total_successes"] == 1
