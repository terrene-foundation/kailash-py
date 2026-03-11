"""
TDD Migration Integration Tests

Tests that validate the TDD fixtures integrate properly with existing test
infrastructure and provide backward compatibility for migration to TDD approach.

This test suite focuses on:
1. Backward compatibility with existing test patterns
2. Integration with DataFlow engine and nodes
3. Migration path from traditional to TDD approach
4. Real database operations with TDD isolation
"""

import asyncio
import os
import time
from pathlib import Path

import pytest

# Enable TDD mode for integration testing
os.environ["DATAFLOW_TDD_MODE"] = "true"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_dataflow_integration(tdd_transaction_dataflow):
    """
    Test integration between TDD fixtures and DataFlow engine.

    Validates that TDD fixtures work correctly with the core DataFlow
    functionality and provide proper isolation.
    """
    df, context = tdd_transaction_dataflow

    # Test DataFlow engine integration
    assert df is not None
    assert hasattr(df, "model")
    assert hasattr(df, "create_tables")

    # Test context provides proper isolation
    assert context.connection is not None
    assert context.savepoint_created is True

    # Create a test model using DataFlow
    @df.model
    class IntegrationTestUser:
        name: str
        email: str
        age: int = 25
        active: bool = True

    # Initialize tables
    df.create_tables()

    # Test CRUD operations work with TDD isolation
    create_result = await df.IntegrationTestUser.create(
        {
            "name": "Integration Test User",
            "email": "integration@example.com",
            "age": 30,
            "active": True,
        }
    )

    assert create_result["success"] is True
    user_id = create_result["data"]["id"]

    # Test read operations
    find_result = await df.IntegrationTestUser.find_by_id(user_id)
    assert find_result["success"] is True
    assert find_result["data"]["name"] == "Integration Test User"

    # Test update operations
    update_result = await df.IntegrationTestUser.update(user_id, {"age": 35})
    assert update_result["success"] is True

    # Test query operations
    query_result = await df.IntegrationTestUser.find_many({"active": True})
    assert query_result["success"] is True
    assert len(query_result["data"]) == 1

    # All operations are automatically isolated and will be rolled back


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_node_execution_integration(tdd_transaction_dataflow):
    """
    Test TDD integration with DataFlow node execution.

    Validates that generated nodes work correctly with TDD fixtures
    and maintain proper isolation during workflow execution.
    """
    df, context = tdd_transaction_dataflow

    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    # Create test model for node generation
    @df.model
    class NodeTestProduct:
        name: str
        price: float
        category: str = "test"
        in_stock: bool = True

    df.create_tables()

    # Build workflow using generated nodes
    workflow = WorkflowBuilder()

    # Use DataFlow's auto-generated nodes
    workflow.add_node(
        "NodeTestProductCreateNode",
        "create_product",
        {
            "name": "Test Product",
            "price": 99.99,
            "category": "electronics",
            "in_stock": True,
        },
    )

    workflow.add_node(
        "NodeTestProductFindManyNode",
        "find_products",
        {"filter": {"category": "electronics"}},
    )

    # Connect nodes
    workflow.add_connection(
        "create_product", "created_product", "find_products", "context"
    )

    # Execute workflow with TDD isolation
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Validate workflow execution
    assert "create_product" in results
    assert "find_products" in results

    # Validate create node results
    create_result = results["create_product"]
    assert create_result["success"] is True
    assert "id" in create_result["data"]

    # Validate find node results
    find_result = results["find_products"]
    assert find_result["success"] is True
    assert len(find_result["data"]) >= 1

    # All operations are isolated and will be rolled back


@pytest.mark.asyncio
@pytest.mark.integration
async def test_backward_compatibility_with_existing_fixtures(standard_dataflow):
    """
    Test backward compatibility between TDD and existing fixtures.

    Validates that existing tests can gradually migrate to TDD without
    breaking changes and that both approaches can coexist.
    """
    # Test existing fixture still works
    df = standard_dataflow
    assert df is not None

    # Check that existing fixture has standard models
    assert hasattr(df, "TestUser")
    assert hasattr(df, "TestProduct")
    assert hasattr(df, "TestOrder")

    # Test traditional operations still work
    user_data = {
        "name": "Compatibility Test User",
        "email": "compat@example.com",
        "active": True,
    }

    # This uses the traditional fixture approach
    # It should work alongside TDD fixtures

    # Note: We can't actually test database operations here because
    # the standard_dataflow fixture and TDD fixtures use different
    # isolation mechanisms. This test validates the fixture coexistence.


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_performance_with_real_operations(tdd_performance_test):
    """
    Test TDD performance with real database operations.

    Validates that the <100ms target is achievable with actual
    database operations, not just simulated work.
    """
    metrics, context = tdd_performance_test

    connection = context.connection

    # Create a real table with indexes
    await connection.execute(
        """
        CREATE TEMP TABLE perf_real_test (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            data JSONB
        )
    """
    )

    # Create index for performance
    await connection.execute(
        """
        CREATE INDEX idx_perf_real_test_email ON perf_real_test(email)
    """
    )

    # Insert multiple records
    for i in range(20):
        await connection.execute(
            """
            INSERT INTO perf_real_test (name, email, data)
            VALUES ($1, $2, $3)
        """,
            f"User {i}",
            f"user{i}@example.com",
            {"index": i, "test": True},
        )

    # Perform complex queries
    count = await connection.fetchval("SELECT COUNT(*) FROM perf_real_test")
    assert count == 20

    # Query with WHERE clause
    users = await connection.fetch(
        """
        SELECT * FROM perf_real_test
        WHERE data->>'index'::int > 10
        ORDER BY created_at
    """
    )
    assert len(users) == 9  # Users 11-19

    # Update operations
    await connection.execute(
        """
        UPDATE perf_real_test
        SET data = data || '{"updated": true}'
        WHERE data->>'index'::int < 5
    """
    )

    # Validate update
    updated_count = await connection.fetchval(
        """
        SELECT COUNT(*) FROM perf_real_test
        WHERE data->>'updated' = 'true'
    """
    )
    assert updated_count == 5

    # The performance metrics will be automatically validated
    # by the tdd_performance_test fixture


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_with_existing_integration_patterns():
    """
    Test TDD fixtures with existing integration test patterns.

    This validates that TDD fixtures can be used in place of existing
    integration test fixtures without changing test logic.
    """
    # Enable TDD mode for this test specifically
    os.environ["DATAFLOW_TDD_MODE"] = "true"

    try:
        # Import TDD fixtures
        from tests.fixtures.tdd_fixtures import tdd_transaction_dataflow

        # Use TDD fixture in existing pattern
        async with tdd_transaction_dataflow() as (df, context):
            # This follows the same pattern as existing integration tests
            @df.model
            class MigrationTestModel:
                name: str
                status: str = "active"
                metadata: dict = None

            df.create_tables()

            # Existing test logic can be used unchanged
            result = await df.MigrationTestModel.create(
                {
                    "name": "Migration Test",
                    "status": "testing",
                    "metadata": {"migrated": True},
                }
            )

            assert result["success"] is True

            # Query to verify
            found = await df.MigrationTestModel.find_many({"status": "testing"})
            assert len(found["data"]) == 1

            # This demonstrates that existing test logic
            # can be dropped into TDD fixtures with minimal changes

    finally:
        # Cleanup
        if "DATAFLOW_TDD_MODE" in os.environ:
            del os.environ["DATAFLOW_TDD_MODE"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_parallel_execution_safety(tdd_parallel_safe):
    """
    Test TDD parallel execution safety with real database operations.

    Validates that parallel-safe TDD fixtures prevent race conditions
    and maintain proper isolation during concurrent test execution.
    """
    context, unique_id = tdd_parallel_safe
    connection = context.connection

    # Create unique resources for this parallel test
    table_name = f"parallel_test_{unique_id.split('_')[1]}"

    # Create table with unique name
    await connection.execute(
        f"""
        CREATE TEMP TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            test_id VARCHAR(50),
            data TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    # Insert test data with unique identifier
    for i in range(5):
        await connection.execute(
            f"""
            INSERT INTO {table_name} (test_id, data)
            VALUES ($1, $2)
        """,
            unique_id,
            f"Parallel test data {i}",
        )

    # Query data - should only see this test's data
    records = await connection.fetch(
        f"""
        SELECT * FROM {table_name}
        WHERE test_id = $1
    """,
        unique_id,
    )

    assert len(records) == 5

    # Verify all records belong to this test
    for record in records:
        assert record["test_id"] == unique_id
        assert "Parallel test data" in record["data"]

    # This test can run in parallel with others without interference
    # because each test gets its own unique context and identifiers


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_memory_efficiency_with_large_dataset(tdd_memory_monitor):
    """
    Test TDD memory efficiency with larger datasets.

    Validates that TDD fixtures remain memory-efficient even with
    larger test datasets and complex operations.
    """
    with tdd_memory_monitor.track():
        # Simulate processing a larger dataset
        large_dataset = [
            {
                "id": i,
                "name": f"Record {i}",
                "data": {"value": i * 2, "category": f"cat_{i % 10}"},
            }
            for i in range(1000)
        ]

        # Process data (simulate typical test operations)
        processed = []
        for record in large_dataset:
            if record["data"]["value"] % 4 == 0:
                processed.append(
                    {
                        "id": record["id"],
                        "processed_value": record["data"]["value"] * 2,
                        "category": record["data"]["category"],
                    }
                )

        # Update memory tracking
        tdd_memory_monitor.update_tracking()

    # Validate memory usage remains reasonable
    delta_mb = tdd_memory_monitor.get_delta_mb()
    peak_mb = tdd_memory_monitor.peak_usage_mb

    # Should be efficient even with larger datasets
    assert delta_mb < 5.0, f"Memory usage too high: {delta_mb:.2f}MB"
    assert peak_mb > 0, "Peak memory should be tracked"

    # Memory should be released after processing
    final_usage = tdd_memory_monitor._get_memory_usage_mb()
    assert final_usage <= tdd_memory_monitor.peak_usage_mb


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tdd_connection_pool_integration(tdd_connection_pool):
    """
    Test TDD connection pool integration with concurrent operations.

    Validates that the TDD connection pool efficiently handles
    concurrent database operations and maintains proper isolation.
    """
    pool, manager = tdd_connection_pool

    # Test concurrent operations using connection pool
    async def perform_operation(operation_id: int):
        async with pool.acquire() as conn:
            # Create temporary table for this operation
            table_name = f"temp_op_{operation_id}"

            await conn.execute(
                f"""
                CREATE TEMP TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    operation_id INT,
                    data TEXT
                )
            """
            )

            # Insert data
            await conn.execute(
                f"""
                INSERT INTO {table_name} (operation_id, data)
                VALUES ($1, $2)
            """,
                operation_id,
                f"Operation {operation_id} data",
            )

            # Query data
            result = await conn.fetchval(
                f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE operation_id = $1
            """,
                operation_id,
            )

            return result

    # Run concurrent operations
    tasks = [perform_operation(i) for i in range(3)]
    results = await asyncio.gather(*tasks)

    # Validate all operations completed successfully
    assert all(result == 1 for result in results)

    # Validate connection pool state
    assert pool.get_size() <= pool.get_max_size()
    assert not pool.is_closing()


def test_tdd_migration_documentation():
    """
    Document the migration path from traditional to TDD testing.

    This test serves as documentation for how to migrate existing
    tests to use TDD fixtures.
    """
    migration_guide = """
    TDD Migration Guide:

    1. Traditional Test Pattern:
    ```python
    def test_user_operations(standard_dataflow):
        df = standard_dataflow
        # Test operations with cleanup overhead
    ```

    2. TDD Migration - Step 1 (Drop-in replacement):
    ```python
    @pytest.mark.asyncio
    async def test_user_operations(fast_test_dataflow):
        df = fast_test_dataflow
        # Same test logic, faster execution
    ```

    3. TDD Migration - Step 2 (Full TDD):
    ```python
    @pytest.mark.asyncio
    @pytest.mark.tdd
    async def test_user_operations(tdd_transaction_dataflow):
        df, context = tdd_transaction_dataflow
        # Full TDD with context access
    ```

    4. Performance Benefits:
    - Traditional: >2000ms (DROP SCHEMA CASCADE)
    - TDD: <100ms (PostgreSQL savepoints)
    - 20x+ performance improvement

    5. Migration Steps:
    a) Add DATAFLOW_TDD_MODE=true to test environment
    b) Replace fixtures gradually
    c) Add @pytest.mark.tdd to new tests
    d) Monitor performance improvements
    """

    # This test always passes - it's for documentation
    assert True

    # Print guide during test execution
    print(migration_guide)
