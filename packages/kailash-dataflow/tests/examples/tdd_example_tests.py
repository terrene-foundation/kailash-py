"""
Example TDD Tests for DataFlow

Demonstrates the enhanced TDD test fixtures and their capabilities:
- Fast savepoint-based isolation (<100ms)
- Pre-defined test models
- Performance monitoring
- Parallel test execution
- Memory usage tracking

These examples show how to use the new TDD infrastructure for fast,
isolated testing with real database operations.
"""

import asyncio
import os
import time

import pytest

# Enable TDD mode for these examples
os.environ["DATAFLOW_TDD_MODE"] = "true"


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_fast_transaction_isolation(tdd_test_context):
    """
    Example: Fast transaction isolation with savepoints.

    This test demonstrates the core TDD capability - fast test isolation
    using PostgreSQL savepoints instead of DROP SCHEMA CASCADE.

    Expected execution time: <100ms (vs >2000ms with traditional approach)
    """
    context = tdd_test_context

    # Direct database operations using the TDD connection
    connection = context.connection

    # Create a test table
    await connection.execute(
        """
        CREATE TEMP TABLE test_users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(255),
            active BOOLEAN DEFAULT TRUE
        )
    """
    )

    # Test operations - all will be automatically rolled back
    await connection.execute(
        "INSERT INTO test_users (name, email, active) VALUES ($1, $2, $3)",
        "Test User",
        "test@example.com",
        True,
    )

    # Query the created user
    users = await connection.fetch("SELECT * FROM test_users WHERE active = TRUE")
    assert len(users) == 1
    assert users[0]["name"] == "Test User"

    # The savepoint will automatically rollback on test completion
    # No manual cleanup required


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_predefined_models(tdd_models):
    """
    Example: Using pre-defined test models.

    This test demonstrates using the standardized test models that
    are optimized for common testing scenarios.
    """
    User, Product, Order, Comment = tdd_models

    # Models are ready to use with consistent schema
    assert User.__name__.startswith("TDDUser_")
    assert Product.__name__.startswith("TDDProduct_")
    assert Order.__name__.startswith("TDDOrder_")
    assert Comment.__name__.startswith("TDDComment_")

    # Each model has __test_model__ attribute
    assert getattr(User, "__test_model__", False) is True
    assert getattr(Product, "__test_model__", False) is True

    # Models have standard fields for common operations
    # User: name, email, active, created_at, metadata
    # Product: name, price, category, in_stock, sku, tags
    # Order: user_id, product_id, quantity, total_price, status
    # Comment: content, author_id, post_id, parent_id

    # These models can be used directly with DataFlow
    user_data = {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "active": True,
        "metadata": {"test": True},
    }

    product_data = {
        "name": "Test Laptop",
        "price": 999.99,
        "category": "electronics",
        "in_stock": True,
        "sku": "TEST001",
    }

    # Example usage - these would work with actual DataFlow instance
    # user = await df.User.create(user_data)
    # product = await df.Product.create(product_data)


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_performance_monitoring(tdd_performance_test):
    """
    Example: Performance monitoring and validation.

    This test demonstrates the performance monitoring capabilities
    and validation of the <100ms target.
    """
    metrics, context = tdd_performance_test

    # Simulate some database operations
    await asyncio.sleep(0.01)  # 10ms simulated work

    # The performance metrics are automatically collected
    assert metrics.test_id.startswith("perf_")
    assert metrics.setup_time_ms >= 0

    # Test context provides access to the database connection
    assert context.connection is not None
    assert context.savepoint_created is True

    # After test completion, metrics will show:
    # - setup_time_ms: Time to create test context
    # - execution_time_ms: Time spent in test
    # - teardown_time_ms: Time to cleanup
    # - total_time_ms: Total test time
    # - target_achieved: Whether <100ms target was met


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_parallel_safe_execution(tdd_parallel_safe):
    """
    Example: Parallel-safe test execution.

    This test demonstrates fixtures designed for parallel execution
    with proper isolation and race condition prevention.
    """
    context, unique_id = tdd_parallel_safe

    # Each parallel test gets a unique identifier
    assert unique_id.startswith("parallel_")
    assert len(unique_id) == 21  # parallel_ + 12 char hex

    # Context is configured for parallel safety
    assert context.metadata["parallel_safe"] is True
    assert context.metadata["unique_id"] == unique_id
    assert context.isolation_level == "SERIALIZABLE"

    # All operations use this unique context
    # preventing interference with other parallel tests

    # Example: Create a unique table name for this test
    table_suffix = unique_id.replace("parallel_", "")
    expected_table = f"tdd_test_table_{table_suffix}"

    # This would be safe to run in parallel with other tests
    # as each test gets its own isolated context


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_seeded_data_scenario(tdd_seeded_data):
    """
    Example: Using pre-seeded test data.

    This test demonstrates using pre-populated test data for
    scenarios that require existing data relationships.
    """
    context, data, models = tdd_seeded_data

    # Data is already seeded in the database
    users = data["users"]
    products = data["products"]
    orders = data["orders"]

    # Verify seeded data structure
    assert len(users) == 3
    assert len(products) == 5
    assert len(orders) == 3

    # Verify data quality
    for user in users:
        assert "name" in user
        assert "email" in user
        assert "active" in user
        assert user["email"].endswith("@example.com")

    for product in products:
        assert "name" in product
        assert "price" in product
        assert "category" in product
        assert product["price"] > 0

    # Models are available for additional operations
    User = models["User"]
    Product = models["Product"]
    Order = models["Order"]

    # Can perform additional operations on seeded data
    # user_count = await df.User.count()
    # assert user_count["data"] >= 3


def test_performance_benchmarking(tdd_benchmark):
    """
    Example: Performance benchmarking utilities.

    This test demonstrates the benchmarking utilities for measuring
    and validating performance of specific operations.
    """
    # Measure a fast operation
    with tdd_benchmark.measure("fast_operation"):
        time.sleep(0.01)  # 10ms operation

    # Validate it meets target
    assert tdd_benchmark.validate_target(100.0)  # 100ms target
    assert tdd_benchmark.last_measurement < 50  # Should be ~10ms

    # Measure a slower operation
    with tdd_benchmark.measure("slower_operation"):
        time.sleep(0.05)  # 50ms operation

    # Check measurements are tracked
    assert len(tdd_benchmark.measurements["fast_operation"]) == 1
    assert len(tdd_benchmark.measurements["slower_operation"]) == 1

    # Get averages
    fast_avg = tdd_benchmark.get_average("fast_operation")
    slow_avg = tdd_benchmark.get_average("slower_operation")

    assert fast_avg < slow_avg
    assert fast_avg < 20  # Should be ~10ms
    assert slow_avg < 60  # Should be ~50ms


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_connection_pool_access(tdd_connection_pool):
    """
    Example: Direct connection pool access.

    This test demonstrates accessing the underlying connection pool
    for advanced scenarios and monitoring.
    """
    pool, manager = tdd_connection_pool

    # Verify pool is available and initialized
    assert pool is not None
    assert manager is not None
    assert manager.connection_pool == pool

    # Pool should be properly configured for tests
    assert pool.get_min_size() == 1
    assert pool.get_max_size() == 5

    # Can acquire connections directly if needed
    async with pool.acquire() as conn:
        # Direct database operations
        result = await conn.fetchval("SELECT 1")
        assert result == 1

        # Check connection is valid
        assert not conn.is_closed()

    # Connection automatically returned to pool


def test_memory_monitoring(tdd_memory_monitor):
    """
    Example: Memory usage monitoring.

    This test demonstrates memory monitoring to ensure efficient
    resource usage and prevent memory leaks.
    """
    # Track memory usage during operations
    with tdd_memory_monitor.track():
        # Simulate memory allocation
        data = [i for i in range(1000)]

        # Some processing
        processed = [x * 2 for x in data]

        # Update tracking
        tdd_memory_monitor.update_tracking()

    # Verify memory usage is reasonable
    delta_mb = tdd_memory_monitor.get_delta_mb()

    # Should be minimal for this simple operation
    assert delta_mb < 1.0  # Less than 1MB increase
    assert tdd_memory_monitor.peak_usage_mb > 0

    # Memory monitoring helps detect leaks across tests


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_backward_compatibility(fast_test_dataflow):
    """
    Example: Backward compatibility with existing tests.

    This test demonstrates that existing tests can gradually
    adopt TDD fixtures without breaking changes.
    """
    # This fixture is an alias for tdd_transaction_dataflow
    df = fast_test_dataflow

    # Works exactly like existing DataFlow usage
    @df.model
    class TestModel:
        name: str
        value: int = 0

    df.create_tables()

    # Standard DataFlow operations
    result = await df.TestModel.create({"name": "compatibility_test", "value": 42})

    assert result["success"] is True

    # Automatic cleanup and isolation still work
    # Existing tests can use this drop-in replacement


@pytest.mark.asyncio
@pytest.mark.tdd
async def test_isolated_context_compatibility(isolated_test_context):
    """
    Example: Isolated context for existing tests.

    This provides just the test context without DataFlow instance
    for tests that need manual setup.
    """
    context = isolated_test_context

    # Direct access to database connection
    assert context.connection is not None
    assert context.savepoint_created is True

    # Can perform raw SQL operations
    result = await context.connection.fetchval("SELECT version()")
    assert "PostgreSQL" in result

    # Test ID for tracking
    assert context.test_id.startswith("test_")

    # Automatic rollback on completion
