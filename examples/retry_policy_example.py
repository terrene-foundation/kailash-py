"""
Comprehensive Retry Policy Example for Kailash SDK

This example demonstrates the comprehensive retry policy engine with:
- Exponential backoff with jitter
- Adaptive retry strategies that learn from failure patterns
- Smart exception classification
- Enterprise coordination with circuit breakers and resource limits
- Comprehensive metrics and analytics
- Multi-strategy configuration
"""

import asyncio
import logging

from kailash.runtime.local import LocalRuntime
from kailash.runtime.resource_manager import (
    AdaptiveRetryStrategy,
    ExponentialBackoffStrategy,
    LinearBackoffStrategy,
    RetryPolicyMode,
)
from kailash.workflow.builder import WorkflowBuilder

# Setup logging to see retry attempts
logging.basicConfig(level=logging.INFO)


async def main():
    print("🚀 Kailash SDK - Comprehensive Retry Policy Example\n")

    # 1. Configure comprehensive retry policy with enterprise coordination
    retry_config = {
        "default_strategy": {
            "type": "exponential_backoff",
            "max_attempts": 5,
            "base_delay": 0.5,
            "max_delay": 30.0,
            "multiplier": 2.0,
            "jitter": True,
        },
        "exception_strategies": {
            # Database connection errors need more aggressive retries
            "ConnectionError": {
                "type": "exponential_backoff",
                "params": {
                    "max_attempts": 7,
                    "base_delay": 0.2,
                    "max_delay": 60.0,
                    "multiplier": 2.5,
                },
            },
            # Timeout errors use linear backoff
            "TimeoutError": {
                "type": "linear_backoff",
                "params": {
                    "max_attempts": 4,
                    "base_delay": 1.0,
                    "increment": 2.0,
                    "max_delay": 20.0,
                },
            },
            # Rate limiting uses adaptive learning
            "HTTPError": {
                "type": "adaptive_retry",
                "params": {
                    "max_attempts": 6,
                    "initial_delay": 1.0,
                    "learning_rate": 0.3,
                    "min_delay": 0.1,
                    "max_delay": 120.0,
                },
            },
        },
        "exception_rules": {
            "retriable_patterns": [
                {"pattern": r".*timeout.*", "case_sensitive": False},
                {"pattern": r".*connection.*", "case_sensitive": False},
                {"pattern": r".*rate.*limit.*", "case_sensitive": False},
            ],
            "non_retriable_patterns": [
                {"pattern": r".*authentication.*", "case_sensitive": False},
                {"pattern": r".*permission.*", "case_sensitive": False},
            ],
        },
        "enable_analytics": True,
        "mode": "adaptive",
    }

    # Circuit breaker configuration for enterprise coordination
    circuit_breaker_config = {
        "name": "workflow_breaker",
        "failure_threshold": 5,
        "timeout_seconds": 30,
        "recovery_threshold": 3,
    }

    # Resource limits for comprehensive enterprise features
    resource_limits = {
        "max_memory_mb": 1024,
        "max_connections": 20,
        "enforcement_policy": "adaptive",
        "enable_alerts": True,
        "memory_alert_threshold": 0.8,
        "cpu_alert_threshold": 0.7,
    }

    # 2. Initialize LocalRuntime with comprehensive enterprise features
    runtime = LocalRuntime(
        retry_policy_config=retry_config,
        circuit_breaker_config=circuit_breaker_config,
        resource_limits=resource_limits,
        enable_async=True,
        enable_monitoring=True,
        debug=True,
    )

    print("✅ LocalRuntime initialized with comprehensive retry policies")
    print(f"📊 Retry configuration: {runtime.get_retry_configuration()['mode']} mode")
    print(
        f"🔄 Circuit breaker: {runtime._circuit_breaker.name if runtime._circuit_breaker else 'None'}"
    )
    print(f"📈 Resource limits: {bool(runtime._resource_enforcer)}")
    print(
        f"🧠 Analytics enabled: {runtime.get_retry_configuration()['enable_analytics']}"
    )
    print()

    # 3. Demonstrate different retry strategies with workflow execution

    print("🎯 Test 1: Exponential Backoff with Transient Failures")
    print("-" * 50)

    # Workflow with node that fails initially then succeeds
    workflow1 = WorkflowBuilder()
    workflow1.add_node(
        "PythonCodeNode",
        "connection_test",
        {
            "code": """
import random
if random.random() < 0.7:  # 70% chance to fail initially
    raise ConnectionError("Database connection temporarily unavailable")
result = {'status': 'connected', 'attempts': 'multiple'}
"""
        },
    )

    try:
        results1, run_id1 = await runtime.execute_async(workflow1.build())
        print(f"✅ Workflow succeeded: {results1['connection_test']['status']}")
    except Exception as e:
        print(f"❌ Workflow failed: {e}")

    print()

    print("🎯 Test 2: Adaptive Learning with Pattern Recognition")
    print("-" * 50)

    # Multiple workflows to enable adaptive learning
    for i in range(3):
        workflow_adaptive = WorkflowBuilder()
        workflow_adaptive.add_node(
            "PythonCodeNode",
            f"learning_test_{i}",
            {
                "code": f"""
import os
key = 'ADAPTIVE_COUNT_{i}'
count = int(os.environ.get(key, '0')) + 1
os.environ[key] = str(count)

if count <= {i + 1}:  # Gradually increasing failure counts
    if count == 1:
        raise ConnectionError(f"Connection failed on attempt {{count}}")
    elif count == 2:
        raise TimeoutError(f"Request timeout on attempt {{count}}")
    else:
        raise ValueError(f"Processing error on attempt {{count}}")

result = {{'iteration': {i}, 'learned_from_attempts': count}}
"""
            },
        )

        try:
            results_adaptive, _ = await runtime.execute_async(workflow_adaptive.build())
            print(
                f"✅ Adaptive test {i+1} succeeded after {results_adaptive[f'learning_test_{i}']['learned_from_attempts']} attempts"
            )
        except Exception as e:
            print(f"❌ Adaptive test {i+1} failed: {e}")

    print()

    print("🎯 Test 3: Non-Retriable Exception Handling")
    print("-" * 50)

    # Workflow with non-retriable exception
    workflow3 = WorkflowBuilder()
    workflow3.add_node(
        "PythonCodeNode",
        "auth_test",
        {
            "code": "raise PermissionError('Authentication failed - invalid credentials')"
        },
    )

    try:
        results3, run_id3 = await runtime.execute_async(workflow3.build())
    except Exception as e:
        print(f"✅ Correctly failed without retry: {type(e).__name__}")
        print("   Reason: Authentication errors are non-retriable")

    print()

    # 4. Advanced runtime configuration and analytics
    print("📊 Advanced Runtime Configuration")
    print("-" * 50)

    # Register custom retry strategies at runtime
    custom_aggressive_strategy = ExponentialBackoffStrategy(
        max_attempts=10, base_delay=0.1, max_delay=120.0, multiplier=3.0, jitter=True
    )
    runtime.register_retry_strategy(
        "aggressive_exponential", custom_aggressive_strategy
    )

    # Add custom exception classifications
    class CustomServiceError(Exception):
        pass

    runtime.add_retriable_exception(CustomServiceError)
    runtime.register_retry_strategy_for_exception(
        CustomServiceError, custom_aggressive_strategy
    )

    print("✅ Registered custom 'aggressive_exponential' strategy")
    print("✅ Added CustomServiceError as retriable with aggressive strategy")
    print()

    # 5. Comprehensive analytics and metrics
    print("📈 Comprehensive Analytics & Metrics")
    print("-" * 50)

    # Get retry analytics
    analytics = runtime.get_retry_analytics()
    if analytics:
        print(f"📊 Total retry sessions: {analytics.get('total_sessions', 0)}")
        print(f"📊 Overall success rate: {analytics.get('success_rate', 0):.1%}")
        print(
            f"📊 Average attempts per session: {analytics.get('average_attempts', 0):.1f}"
        )

        if analytics.get("most_common_exceptions"):
            print("📊 Most common exceptions:")
            for exc_name, count in analytics["most_common_exceptions"][:3]:
                print(f"   • {exc_name}: {count} occurrences")

    # Get strategy effectiveness
    effectiveness = runtime.get_strategy_effectiveness()
    if effectiveness:
        print("\n🎯 Strategy Effectiveness:")
        for strategy_name, stats in effectiveness.items():
            print(
                f"   • {strategy_name}: {stats['success_rate']:.1%} success rate, {stats['average_attempts']:.1f} avg attempts"
            )

    # Get retry configuration summary
    config = runtime.get_retry_configuration()
    if config:
        print("\n⚙️  Configuration Summary:")
        print(f"   • Mode: {config['mode']}")
        print(f"   • Analytics: {config['enable_analytics']}")
        print(
            f"   • Circuit breaker coordination: {config['enable_circuit_breaker_coordination']}"
        )
        print(
            f"   • Resource limit coordination: {config['enable_resource_limit_coordination']}"
        )
        print(f"   • Registered strategies: {len(config['registered_strategies'])}")
        print(
            f"   • Exception-specific strategies: {len(config['exception_specific_strategies'])}"
        )

    print()

    # 6. Adaptive strategy learning insights
    print("🧠 Adaptive Learning Insights")
    print("-" * 50)

    retry_engine = runtime.get_retry_policy_engine()
    if retry_engine and "adaptive_retry" in retry_engine.strategies:
        adaptive_strategy = retry_engine.strategies["adaptive_retry"]
        learning_stats = adaptive_strategy.get_learning_stats()

        print("🧠 Learning Statistics:")
        print(f"   • Total attempts recorded: {learning_stats['total_attempts']}")
        print(
            f"   • Unique exception types learned: {learning_stats['unique_exceptions']}"
        )

        if learning_stats["learned_delays"]:
            print("   • Learned optimal delays:")
            for exc_type, delay in learning_stats["learned_delays"].items():
                print(f"     - {exc_type}: {delay:.2f}s")

        if learning_stats["success_rates"]:
            print("   • Exception success rates:")
            for exc_type, rate in learning_stats["success_rates"].items():
                print(f"     - {exc_type}: {rate:.1%}")

    print()
    print("🎉 Comprehensive retry policy demonstration completed!")
    print("💡 Key benefits demonstrated:")
    print("   • Intelligent exponential backoff with jitter")
    print("   • Adaptive learning from failure patterns")
    print("   • Smart exception classification")
    print("   • Enterprise coordination with circuit breakers")
    print("   • Comprehensive metrics and analytics")
    print("   • Runtime strategy configuration")


if __name__ == "__main__":
    asyncio.run(main())
