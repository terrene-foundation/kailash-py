# Async Testing Framework Guide

*Comprehensive testing tools for async workflows in Kailash SDK*

## Overview

The Kailash Async Testing Framework provides tools for testing async workflows with real-world complexity, including mock resources, performance monitoring, and developer-friendly APIs.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Workflow basics
- Understanding of Python async/await
- Familiarity with pytest

## Core Components

### AsyncWorkflowTestCase

The foundation of async testing - a base class for workflow tests.

```python
from kailash.testing import AsyncWorkflowTestCase

class MyWorkflowTest(AsyncWorkflowTestCase):
    async def setUp(self):
        await super().setUp()
        # Set up test resources

    async def test_my_workflow(self):
        # Create workflow
        workflow = self.create_test_workflow()

        # Execute with test environment
        result = await self.execute_workflow(workflow, {"param": "value"})

        # Assertions
        self.assert_workflow_success(result)
        self.assert_node_output(result, "processor", expected_value)
```

**Key Features:**
- Automatic resource cleanup
- Built-in assertions
- Performance monitoring
- Mock resource management

### Resource Management

#### Creating Test Resources

```python
# Real resource (will be cleaned up automatically)
database = await self.create_test_resource(
    "db",
    lambda: create_database_connection(),
    mock=False
)

# Mock resource
mock_service = await self.create_test_resource(
    "service",
    lambda: MockService(),
    mock=True
)
```

#### Mock Resource Configuration

```python
# Configure mock behavior
mock_service.fetch = AsyncMock(return_value={"data": [1, 2, 3]})
mock_service.post = AsyncMock(side_effect=[
    {"id": "123"},
    {"id": "124"}
])

# Verify calls
self.assert_resource_called("service", "fetch", times=1)
self.assert_resource_called("service", "post", times=2)
```

## Testing Patterns

### Basic Async Workflow Test

```python
import pytest
from kailash.testing import AsyncWorkflowTestCase
from kailash.workflow import AsyncWorkflowBuilder

class TestDataProcessing(AsyncWorkflowTestCase):
    async def setUp(self):
        await super().setUp()

        # Create mock database
        self.mock_db = await self.create_test_resource(
            "database",
            lambda: MockDatabase(),
            mock=True
        )

        # Configure mock responses
        self.mock_db.fetch = AsyncMock(return_value=[
            {"id": 1, "value": 100},
            {"id": 2, "value": 200}
        ])

    async def test_data_aggregation(self):
        """Test data aggregation workflow."""
        # Build workflow
        workflow = (
            AsyncWorkflowBuilder("aggregator")
            .add_async_code("fetch_data", """
                db = await get_resource("database")
                data = await db.fetch("SELECT * FROM metrics")
                result = {"records": data}
            """)
            .add_async_code("aggregate", """
                total = sum(r["value"] for r in records)
                result = {"total": total, "count": len(records)}
            """)
            .add_connection("fetch_data", "records", "aggregate", "records")
            .build()
        )

        # Execute workflow
        result = await self.execute_workflow(workflow)

        # Verify results
        self.assert_workflow_success(result)
        self.assert_node_output(result, "aggregate", 300, "total")
        self.assert_node_output(result, "aggregate", 2, "count")

        # Verify database was called
        self.assert_resource_called("database", "fetch", times=1)
```

### Performance Testing

```python
class TestPerformance(AsyncWorkflowTestCase):
    async def test_workflow_performance(self):
        """Test workflow completes within time limit."""
        workflow = self.create_complex_workflow()

        # Assert execution time
        async with self.assert_time_limit(2.0):
            result = await self.execute_workflow(workflow, {
                "data_size": 1000
            })

        self.assert_workflow_success(result)

    async def test_concurrent_execution(self):
        """Test concurrent workflow execution."""
        workflow = self.create_simple_workflow()

        # Execute multiple workflows concurrently
        tasks = []
        for i in range(10):
            task = self.execute_workflow(workflow, {"worker_id": i})
            tasks.append(task)

        # All should complete successfully
        results = await asyncio.gather(*tasks)

        for result in results:
            self.assert_workflow_success(result)
```

### Error Handling Tests

```python
class TestErrorHandling(AsyncWorkflowTestCase):
    async def test_retry_logic(self):
        """Test workflow retry on transient failures."""
        # Create flaky service mock
        flaky_service = await self.create_test_resource(
            "flaky_api",
            lambda: MockAPI(),
            mock=True
        )

        # Configure to fail twice, then succeed
        flaky_service.call = AsyncMock(side_effect=[
            ConnectionError("Network error"),
            ConnectionError("Network error"),
            {"status": "success"}
        ])

        # Build workflow with retry logic
        workflow = (
            AsyncWorkflowBuilder("retry_test")
            .add_async_code("api_call", """
                api = await get_resource("flaky_api")
                max_retries = 3

                for attempt in range(max_retries):
                    try:
                        result = await api.call()
                        break
                    except ConnectionError as e:
                        if attempt == max_retries - 1:
                            raise
                        await asyncio.sleep(0.1 * (2 ** attempt))
            """)
            .build()
        )

        # Should succeed after retries
        result = await self.execute_workflow(workflow)
        self.assert_workflow_success(result)

        # Verify retry attempts
        self.assert_resource_called("flaky_api", "call", times=3)
```

## Test Fixtures

### HTTP Client Mocking

```python
from kailash.testing import AsyncWorkflowFixtures

# Create mock HTTP client
http_client = AsyncWorkflowFixtures.create_mock_http_client()

# Add expected responses
http_client.add_response("GET", "/api/users", {
    "users": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    ]
})

http_client.add_response("POST", "/api/users", {
    "id": 3,
    "name": "Charlie"
}, status=201)

# Use in test
await self.create_test_resource("http", lambda: http_client, mock=True)
```

### Database Testing

```python
# Create test database fixture
class TestWithDatabase(AsyncWorkflowTestCase):
    async def setUp(self):
        await super().setUp()

        # Create test database
        self.test_db = await AsyncWorkflowFixtures.create_test_database(
            engine="postgresql",
            database="test_db"
        )

        # Create connection
        self.db = await self.create_test_resource(
            "database",
            lambda: create_async_connection(self.test_db.connection_string)
        )

    async def test_database_workflow(self):
        """Test workflow with real database."""
        # Insert test data
        await self.db.execute("""
            INSERT INTO users (name, email)
            VALUES ('Test User', 'test@example.com')
        """)

        # Run workflow
        workflow = self.create_user_processing_workflow()
        result = await self.execute_workflow(workflow)

        # Verify results
        self.assert_workflow_success(result)
```

### Cache Mocking

```python
# Create mock cache
cache = await AsyncWorkflowFixtures.create_test_cache()

# Pre-populate cache
await cache.set("user:123", {"name": "Alice"}, ttl=60)
await cache.set("session:abc", {"user_id": 123}, ttl=3600)

# Use in workflow
await self.create_test_resource("cache", lambda: cache, mock=True)
```

## Advanced Features

### Convergence Testing

```python
async def test_optimization_convergence(self):
    """Test optimization workflow converges."""
    workflow = self.create_optimization_workflow()

    async def get_metric():
        result = await self.execute_workflow(workflow)
        return result.get_output("optimizer", "current_loss")

    # Test convergence
    await AsyncAssertions.assert_converges(
        get_metric,
        tolerance=0.01,
        timeout=10.0,
        samples=20
    )
```

### Integration Testing

```python
class TestIntegration(AsyncWorkflowTestCase):
    async def test_end_to_end_pipeline(self):
        """Test complete data pipeline."""
        # Set up all required mocks
        await self.setup_integration_mocks()

        # Create complex workflow
        workflow = (
            AsyncWorkflowBuilder("pipeline")
            .add_async_code("extract", "...")
            .add_async_code("transform", "...")
            .add_async_code("load", "...")
            .add_connection("extract", "data", "transform", "raw_data")
            .add_connection("transform", "processed", "load", "data")
            .build()
        )

        # Execute with test data
        result = await self.execute_workflow(workflow, {
            "source": "test_source",
            "date": "2024-01-01"
        })

        # Verify each stage
        self.assert_workflow_success(result)
        self.assert_node_success(result, "extract")
        self.assert_node_success(result, "transform")
        self.assert_node_success(result, "load")
```

## Best Practices

### 1. Test Organization

```python
# Group related tests
class TestUserWorkflows(AsyncWorkflowTestCase):
    """Test user-related workflows."""

    async def setUp(self):
        await super().setUp()
        await self.setup_user_mocks()

    async def test_user_registration(self):
        pass

    async def test_user_authentication(self):
        pass

class TestDataWorkflows(AsyncWorkflowTestCase):
    """Test data processing workflows."""

    async def test_etl_pipeline(self):
        pass
```

### 2. Resource Cleanup

```python
async def setUp(self):
    await super().setUp()
    # Resources created here are automatically cleaned up

async def tearDown(self):
    # Additional cleanup if needed
    await super().tearDown()
```

### 3. Mock Configuration

```python
# Configure mocks after creation
mock_service = await self.create_test_resource("service", MockService, mock=True)

# Set up behavior
mock_service.method.return_value = "result"
mock_service.async_method = AsyncMock(return_value="async_result")
```

### 4. Performance Assertions

```python
# Set realistic expectations
async with self.assert_time_limit(5.0):  # Allow reasonable time
    result = await self.execute_workflow(complex_workflow)

# Test throughput
result = await AsyncAssertions.assert_performance(
    self.execute_workflow(workflow),
    max_time=1.0,
    min_throughput=100,  # Operations per second
    operations=1000
)
```

## Running Tests

### Test Execution

```bash
# Run all async tests
pytest tests/async/ -v

# Run specific test class
pytest tests/async/test_workflows.py::TestDataProcessing -v

# Run with coverage
pytest tests/async/ --cov=kailash.testing --cov-report=html

# Run performance tests only
pytest tests/async/ -m performance -v
```

### Test Configuration

```python
# pytest.ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "performance: Performance tests",
    "slow: Slow tests"
]
```

## Troubleshooting

### Common Issues

**Mock Not Working:**
```python
# ❌ Wrong - Mock created incorrectly
mock = Mock()
mock.async_method = lambda: "result"  # Won't work for async

# ✅ Correct - Use AsyncMock
mock = Mock()
mock.async_method = AsyncMock(return_value="result")
```

**Resource Not Found:**
```python
# ❌ Wrong - Resource not registered
db = MockDatabase()
result = await runtime.execute(workflow.build(), )  # Can't find "database"

# ✅ Correct - Register resource
db = await self.create_test_resource("database", MockDatabase, mock=True)
result = await self.execute_workflow(workflow)
```

**Timeout Issues:**
```python
# ❌ Wrong - Too strict timeout
async with self.assert_time_limit(0.1):
    result = await complex_workflow()  # Fails

# ✅ Correct - Reasonable timeout
async with self.assert_time_limit(5.0):
    result = await complex_workflow()
```

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Workflow basics
- [Async Workflow Builder](07-async-workflow-builder.md) - Async patterns

**Advanced Topics:**
- [Testing Production Quality](12-testing-production-quality.md) - General testing
- [Unified Async Runtime](10-unified-async-runtime-guide.md) - Async execution

---

**Build robust async workflows with comprehensive testing at every level!**
