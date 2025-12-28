"""Integration tests for the async testing framework."""

import asyncio
import json
from datetime import datetime

import pytest
from kailash.nodes.code import PythonCodeNode
from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder


@pytest.mark.integration
class TestAsyncTestingFrameworkIntegration:
    """Integration tests for the async testing framework."""

    @pytest.mark.asyncio
    async def test_data_processing_workflow_with_mocks(self):
        """Test a complete data processing workflow using the testing framework."""

        class DataProcessingTest(AsyncWorkflowTestCase):
            """Test case for data processing workflow."""

            async def setUp(self):
                await super().setUp()

                # Create mock database
                self.mock_db = await self.create_test_resource(
                    "db", lambda: None, mock=True  # Factory doesn't matter for mocks
                )

                # Configure mock database responses
                self.mock_db.fetch.return_value = [
                    {"id": 1, "name": "Product A", "price": 100},
                    {"id": 2, "name": "Product B", "price": 200},
                    {"id": 3, "name": "Product C", "price": 150},
                ]

                # Create mock HTTP client
                self.mock_http = await self.create_test_resource(
                    "http",
                    lambda: AsyncWorkflowFixtures.create_mock_http_client(),
                    mock=True,
                )

                # Configure mock after creation (mock registry sets up get method)
                response_data = {"USD": 1.0, "EUR": 0.85, "GBP": 0.73}

                # The mock registry already configured get() to return a mock response
                # We just need to configure the json() method on that response
                from unittest.mock import AsyncMock

                mock_response = AsyncMock()
                mock_response.json = AsyncMock(return_value=response_data)
                mock_response.status = 200
                self.mock_http.get.return_value = mock_response

                # Create mock cache
                self.mock_cache = await AsyncWorkflowFixtures.create_test_cache()
                await self.create_test_resource(
                    "cache", lambda: self.mock_cache, mock=True
                )

            async def test_process_products_with_currency_conversion(self):
                """Test product processing with currency conversion."""
                # Create workflow
                workflow = (
                    AsyncWorkflowBuilder("product_processing")
                    .add_async_code(
                        "load_products",
                        """
# Load products from database
db = await get_resource("db")
products = await db.fetch("SELECT * FROM products WHERE active = true")
result = {"products": [dict(p) for p in products]}
""",
                    )
                    .add_async_code(
                        "fetch_exchange_rates",
                        """
# Fetch current exchange rates
import json
http = await get_resource("http")
cache = await get_resource("cache")

# Check cache first
rates = await cache.get("exchange_rates")
if not rates:
    resp = await http.get("https://api.rates.com/current")
    rates = await resp.json()
    await cache.setex("exchange_rates", 3600, json.dumps(rates))
else:
    rates = json.loads(rates)

result = {"rates": rates}
""",
                    )
                    .add_async_code(
                        "convert_prices",
                        """
# Convert prices to different currencies
converted_products = []
for product in products:
    converted = {
        "id": product["id"],
        "name": product["name"],
        "prices": {
            "USD": product["price"],
            "EUR": round(product["price"] * rates["EUR"], 2),
            "GBP": round(product["price"] * rates["GBP"], 2)
        }
    }
    converted_products.append(converted)

result = {
    "converted_products": converted_products,
    "total_products": len(converted_products)
}
""",
                    )
                    .add_connection(
                        "load_products", "products", "convert_prices", "products"
                    )
                    .add_connection(
                        "fetch_exchange_rates", "rates", "convert_prices", "rates"
                    )
                    .build()
                )

                # Execute workflow with performance tracking
                async with self.assert_time_limit(2.0):
                    result = await self.execute_workflow(workflow, {})

                # Assertions
                self.assert_workflow_success(result)

                # Check that all nodes executed
                assert "load_products" in result.outputs
                assert "fetch_exchange_rates" in result.outputs
                assert "convert_prices" in result.outputs

                # Check product conversion results
                converted = result.get_output("convert_prices", "converted_products")
                assert len(converted) == 3

                # Verify currency conversion
                product_a = next(p for p in converted if p["name"] == "Product A")
                assert product_a["prices"]["USD"] == 100
                assert product_a["prices"]["EUR"] == 85.0  # 100 * 0.85
                assert product_a["prices"]["GBP"] == 73.0  # 100 * 0.73

                # Verify resource calls
                self.assert_resource_called("db", "fetch", times=1)
                self.assert_resource_called("http", "get", times=1)
                self.assert_resource_called("cache", "get", times=1)
                self.assert_resource_called("cache", "setex", times=1)

        # Run the test
        async with DataProcessingTest("product_processing_test") as test:
            await test.test_process_products_with_currency_conversion()

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(self):
        """Test concurrent workflow execution with resource sharing."""

        class ConcurrencyTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Create shared mock resource
                self.shared_counter = 0

                class SharedResource:
                    def __init__(self, test_case):
                        self.test_case = test_case

                    async def increment(self):
                        # Simulate some async work
                        await asyncio.sleep(0.01)
                        self.test_case.shared_counter += 1
                        return self.test_case.shared_counter

                await self.create_test_resource("shared", lambda: SharedResource(self))

            async def test_concurrent_increments(self):
                """Test concurrent access to shared resource."""
                # Create simple workflow
                workflow = (
                    AsyncWorkflowBuilder("increment_workflow")
                    .add_async_code(
                        "increment",
                        """
shared = await get_resource("shared")
new_value = await shared.increment()
result = {"value": new_value, "worker_id": worker_id}
""",
                    )
                    .build()
                )

                # Execute multiple workflows concurrently
                tasks = []
                for i in range(5):
                    task = self.execute_workflow(workflow, {"worker_id": i})
                    tasks.append(task)

                # Wait for all to complete
                results = await AsyncTestUtils.run_concurrent(*tasks)

                # All should succeed
                for result in results:
                    self.assert_workflow_success(result)

                # Final counter should be 5
                assert self.shared_counter == 5

                # All results should have different values (1-5)
                values = [r.get_output("increment", "value") for r in results]
                assert set(values) == {1, 2, 3, 4, 5}

        async with ConcurrencyTest("concurrency_test") as test:
            await test.test_concurrent_increments()

    @pytest.mark.asyncio
    async def test_error_handling_and_retry_patterns(self):
        """Test error handling and retry patterns in workflows."""

        class ErrorHandlingTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Create flaky resource
                self.attempt_count = 0

                class FlakyResource:
                    def __init__(self, test_case):
                        self.test_case = test_case

                    async def flaky_operation(self):
                        self.test_case.attempt_count += 1
                        if self.test_case.attempt_count < 3:
                            raise ConnectionError("Temporary failure")
                        return {
                            "result": "success",
                            "attempts": self.test_case.attempt_count,
                        }

                await self.create_test_resource("flaky", lambda: FlakyResource(self))

            async def test_retry_on_failure(self):
                """Test retry logic with eventually successful operation."""
                workflow = (
                    AsyncWorkflowBuilder("retry_workflow")
                    .add_async_code(
                        "retry_operation",
                        """
import asyncio

flaky = await get_resource("flaky")
max_attempts = 5
delay = 0.01

for attempt in range(max_attempts):
    try:
        result = await flaky.flaky_operation()
        result["final_attempt"] = attempt + 1
        break
    except ConnectionError as e:
        if attempt == max_attempts - 1:
            raise
        await asyncio.sleep(delay)
        delay *= 2  # Exponential backoff
""",
                    )
                    .build()
                )

                # Execute workflow
                result = await self.execute_workflow(workflow, {})

                # Should succeed after retries
                self.assert_workflow_success(result)

                # Check retry behavior
                operation_result = result.get_output("retry_operation")
                assert operation_result["result"] == "success"
                assert operation_result["attempts"] == 3
                assert operation_result["final_attempt"] == 3

        async with ErrorHandlingTest("error_handling_test") as test:
            await test.test_retry_on_failure()

    @pytest.mark.asyncio
    async def test_performance_and_monitoring(self):
        """Test performance monitoring capabilities."""

        class PerformanceTest(AsyncWorkflowTestCase):
            async def test_workflow_performance(self):
                """Test workflow performance monitoring."""
                # Create CPU-intensive workflow
                workflow = (
                    AsyncWorkflowBuilder("performance_test")
                    .add_async_code(
                        "cpu_intensive",
                        """
import asyncio

# Simulate CPU work with some async operations
results = []
for i in range(100):
    # Mix of CPU and I/O
    if i % 10 == 0:
        await asyncio.sleep(0.001)  # Small async pause

    # CPU work
    value = sum(x * x for x in range(i))
    results.append(value)

result = {"computed_values": results, "count": len(results)}
""",
                    )
                    .add_async_code(
                        "memory_operations",
                        """
# Create and process data structures
data = []
for i in range(1000):
    item = {
        "id": i,
        "data": list(range(i % 100)),
        "metadata": {"created": i * 0.001}
    }
    data.append(item)

# Process data
processed = [
    {"id": item["id"], "size": len(item["data"])}
    for item in data
    if len(item["data"]) > 50
]

result = {"processed_items": processed, "total_processed": len(processed)}
""",
                    )
                    .build()
                )

                # Execute with performance monitoring
                start_time = asyncio.get_event_loop().time()

                result = await AsyncAssertions.assert_performance(
                    self.execute_workflow(workflow, {}),
                    max_time=2.0,  # Should complete within 2 seconds
                    operations=1,
                )

                execution_time = asyncio.get_event_loop().time() - start_time

                # Check results
                self.assert_workflow_success(result)

                # Verify outputs
                cpu_result = result.get_output("cpu_intensive")
                assert cpu_result["count"] == 100

                memory_result = result.get_output("memory_operations")
                assert memory_result["total_processed"] > 0

                # Performance should be reasonable
                assert execution_time < 1.0, f"Workflow too slow: {execution_time:.2f}s"
                assert (
                    result.execution_time < 1.0
                ), f"Reported time too slow: {result.execution_time:.2f}s"

        async with PerformanceTest("performance_test") as test:
            await test.test_workflow_performance()

    @pytest.mark.asyncio
    async def test_state_management_and_convergence(self):
        """Test state management and convergence patterns."""

        class ConvergenceTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Shared state for convergence test
                self.iteration_count = 0
                self.values = []

                class StateManager:
                    def __init__(self, test_case):
                        self.test_case = test_case

                    async def get_current_value(self):
                        if not self.test_case.values:
                            return 100.0
                        return self.test_case.values[-1]

                    async def update_value(self, new_value):
                        self.test_case.values.append(new_value)
                        self.test_case.iteration_count += 1
                        return new_value

                    async def get_iteration_count(self):
                        return self.test_case.iteration_count

                await self.create_test_resource("state", lambda: StateManager(self))

            async def test_iterative_convergence(self):
                """Test iterative algorithm convergence."""
                workflow = (
                    AsyncWorkflowBuilder("convergence_workflow")
                    .add_async_code(
                        "iteration_step",
                        """
import random

state = await get_resource("state")

# Get current value
current = await state.get_current_value()
target = 50.0

# Convergence step with very minimal noise for test reliability
step = (target - current) * 0.7 + random.uniform(-0.1, 0.1)
new_value = current + step

# Update state
await state.update_value(new_value)
iteration = await state.get_iteration_count()

result = {
    "current_value": new_value,
    "iteration": iteration,
    "distance_to_target": abs(new_value - target),
    "converged": abs(new_value - target) < 1.0
}
""",
                    )
                    .build()
                )

                # Run iterations until convergence
                async def get_latest_value():
                    result = await self.execute_workflow(workflow, {})
                    self.assert_workflow_success(result)
                    return result.get_output("iteration_step", "current_value")

                # Test convergence with lenient tolerance for test stability
                await AsyncAssertions.assert_converges(
                    get_latest_value, tolerance=15.0, timeout=10.0, samples=10
                )

                # Should have converged reasonably close to target
                final_value = self.values[-1] if self.values else 100.0
                assert (
                    abs(final_value - 50.0) < 10.0
                ), f"Did not converge close enough: {final_value}"
                assert self.iteration_count > 5, "Should have taken multiple iterations"

        async with ConvergenceTest("convergence_test") as test:
            await test.test_iterative_convergence()

    @pytest.mark.asyncio
    async def test_comprehensive_workflow_suite(self):
        """Test a comprehensive workflow test suite demonstrating all features."""

        class ComprehensiveTest(AsyncWorkflowTestCase):
            async def setUp(self):
                await super().setUp()

                # Set up multiple mock resources
                self.mock_db = await self.create_test_resource(
                    "db", lambda: None, mock=True
                )

                # Configure database mock
                self.mock_db.fetch.return_value = [
                    {
                        "user_id": 1,
                        "action": "login",
                        "timestamp": "2023-01-01T10:00:00",
                    },
                    {
                        "user_id": 2,
                        "action": "purchase",
                        "timestamp": "2023-01-01T10:30:00",
                    },
                    {
                        "user_id": 1,
                        "action": "logout",
                        "timestamp": "2023-01-01T11:00:00",
                    },
                ]

                # Create HTTP client as real resource (not mocked by registry)
                self.mock_http = AsyncWorkflowFixtures.create_mock_http_client()
                self.mock_http.add_response("POST", "/analytics", {"id": "report_123"})
                await self.create_test_resource(
                    "http", lambda: self.mock_http, mock=False
                )

                # Create cache as real resource
                self.mock_cache = await AsyncWorkflowFixtures.create_test_cache()
                await self.create_test_resource(
                    "cache", lambda: self.mock_cache, mock=False
                )

            async def test_complete_analytics_pipeline(self):
                """Test complete analytics pipeline with all testing features."""
                workflow = (
                    AsyncWorkflowBuilder("analytics_pipeline")
                    .add_async_code(
                        "extract_events",
                        """
db = await get_resource("db")
events = await db.fetch("SELECT * FROM user_events WHERE date = %s", "2023-01-01")
result = {"events": [dict(e) for e in events], "count": len(events)}
""",
                    )
                    .add_async_code(
                        "transform_events",
                        """
# Group events by user
user_sessions = {}
for event in events:
    user_id = event["user_id"]
    if user_id not in user_sessions:
        user_sessions[user_id] = []
    user_sessions[user_id].append(event)

# Calculate session metrics
metrics = []
for user_id, user_events in user_sessions.items():
    session_length = len(user_events)
    has_purchase = any(e["action"] == "purchase" for e in user_events)
    metrics.append({
        "user_id": user_id,
        "session_length": session_length,
        "has_purchase": has_purchase,
        "event_count": len(user_events)
    })

result = {"user_metrics": metrics, "total_users": len(metrics)}
""",
                    )
                    .add_async_code(
                        "cache_and_report",
                        """
import json

cache = await get_resource("cache")
http = await get_resource("http")

# Extract metrics from transform result
user_metrics = transform_result["user_metrics"]
total_users = transform_result["total_users"]

# Cache metrics
cache_key = "daily_metrics:2023-01-01"
await cache.setex(cache_key, 86400, json.dumps(user_metrics))

# Send report to analytics service
report_data = {
    "date": "2023-01-01",
    "total_users": total_users,
    "metrics": user_metrics
}

resp = await http.post("/analytics", json=report_data)
report_result = await resp.json()

result = {
    "cached": True,
    "report_id": report_result.get("id"),
    "metrics_cached": len(user_metrics)
}
""",
                    )
                    .add_connection(
                        "extract_events", "events", "transform_events", "events"
                    )
                    .add_connection(
                        "transform_events",
                        "result",
                        "cache_and_report",
                        "transform_result",
                    )
                    .build()
                )

                # Execute with comprehensive monitoring
                async with self.assert_time_limit(5.0):
                    result = await self.execute_workflow(workflow, {})

                # Comprehensive assertions
                self.assert_workflow_success(result)

                # Verify each step
                extract_result = result.get_output("extract_events")
                assert extract_result["count"] == 3

                transform_result = result.get_output("transform_events")
                assert transform_result["total_users"] == 2

                # Check user metrics
                metrics = transform_result["user_metrics"]
                user1_metrics = next(m for m in metrics if m["user_id"] == 1)
                user2_metrics = next(m for m in metrics if m["user_id"] == 2)

                assert user1_metrics["event_count"] == 2
                assert not user1_metrics["has_purchase"]
                assert user2_metrics["event_count"] == 1
                assert user2_metrics["has_purchase"]

                cache_result = result.get_output("cache_and_report")
                assert cache_result["cached"] is True
                assert cache_result["report_id"] == "report_123"

                # Verify all resource interactions
                self.assert_resource_called("db", "fetch", times=1)

                # Check that cache was called with correct data (setex calls set internally)
                cache_calls = self.mock_cache.get_calls("set")
                assert len(cache_calls) == 1
                assert cache_calls[0][1][0] == "daily_metrics:2023-01-01"  # cache key

                # Check HTTP was called with correct data
                http_calls = self.mock_http.get_calls("POST")
                assert len(http_calls) == 1
                assert "/analytics" in http_calls[0].url

        async with ComprehensiveTest("comprehensive_test") as test:
            await test.test_complete_analytics_pipeline()
