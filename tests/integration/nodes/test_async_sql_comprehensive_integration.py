"""Comprehensive integration tests for AsyncSQLDatabaseNode with real-world scenarios."""

import asyncio
import gc
import json
import os
import time
import uuid
from datetime import date, datetime

import psutil
import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError

from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLComprehensiveIntegration:
    """Comprehensive integration tests covering real-world scenarios."""

    @pytest_asyncio.fixture
    async def comprehensive_database_setup(self):
        """Set up comprehensive test database for integration testing."""
        conn_string = get_postgres_connection_string()

        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Create realistic tables for testing
        await setup_node.execute_async(query="DROP TABLE IF EXISTS users CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS orders CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS products CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS order_items CASCADE")
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS performance_test CASCADE"
        )

        # Users table
        await setup_node.execute_async(
            query="""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT true,
                metadata JSONB
            )
        """
        )

        # Products table
        await setup_node.execute_async(
            query="""
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                stock_quantity INTEGER DEFAULT 0,
                category VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Orders table
        await setup_node.execute_async(
            query="""
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                total_amount DECIMAL(10, 2) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Order items table
        await setup_node.execute_async(
            query="""
            CREATE TABLE order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                total_price DECIMAL(10, 2) NOT NULL
            )
        """
        )

        # Performance test table
        await setup_node.execute_async(
            query="""
            CREATE TABLE performance_test (
                id SERIAL PRIMARY KEY,
                data TEXT,
                number_value INTEGER,
                timestamp_value TIMESTAMP DEFAULT NOW(),
                json_data JSONB
            )
        """
        )

        # Insert sample data
        await setup_node.execute_async(
            query="""
            INSERT INTO users (email, name, metadata) VALUES
            ('admin@test.com', 'Admin User', '{"role": "admin"}'),
            ('user1@test.com', 'Test User 1', '{"role": "user"}'),
            ('user2@test.com', 'Test User 2', '{"role": "user"}')
        """
        )

        await setup_node.execute_async(
            query="""
            INSERT INTO products (name, price, stock_quantity, category) VALUES
            ('Product A', 19.99, 100, 'electronics'),
            ('Product B', 29.99, 50, 'electronics'),
            ('Product C', 9.99, 200, 'books')
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS users CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS orders CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS products CASCADE")
        await setup_node.execute_async(query="DROP TABLE IF EXISTS order_items CASCADE")
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS performance_test CASCADE"
        )
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_high_concurrency_operations(self, comprehensive_database_setup):
        """Test high concurrency with many simultaneous operations."""
        conn_string = comprehensive_database_setup

        # Create multiple nodes with shared pool
        nodes = []
        for i in range(5):
            node = AsyncSQLDatabaseNode(
                name=f"concurrent_node_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                pool_size=5,
                max_pool_size=10,
                share_pool=True,
            )
            nodes.append(node)

        try:
            # Define different types of operations
            async def read_operation(node, index):
                return await node.execute_async(
                    query="SELECT COUNT(*) as count FROM users WHERE is_active = :active",
                    params={"active": True},
                )

            async def write_operation(node, index):
                return await node.execute_async(
                    query="""
                        INSERT INTO performance_test (data, number_value, json_data)
                        VALUES (:data, :number, :json_data)
                    """,
                    params={
                        "data": f"concurrent_test_{index}",
                        "number": index,
                        "json_data": {"test": True, "index": index},
                    },
                )

            async def update_operation(node, index):
                return await node.execute_async(
                    query="""
                        UPDATE products
                        SET stock_quantity = stock_quantity + :increment
                        WHERE id = :product_id
                    """,
                    params={"increment": 1, "product_id": (index % 3) + 1},
                )

            # Create 100 mixed operations
            tasks = []
            for i in range(100):
                node = nodes[i % len(nodes)]
                operation_type = i % 3

                if operation_type == 0:
                    task = read_operation(node, i)
                elif operation_type == 1:
                    task = write_operation(node, i)
                else:
                    task = update_operation(node, i)

                tasks.append(task)

            # Execute all operations concurrently
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Verify results
            successful_operations = 0
            for result in results:
                if isinstance(result, Exception):
                    print(f"Operation failed: {result}")
                else:
                    successful_operations += 1
                    assert "result" in result

            # Most operations should succeed (allowing for some contention)
            assert (
                successful_operations >= 90
            ), f"Only {successful_operations}/100 operations succeeded"

            execution_time = end_time - start_time
            print(
                f"100 concurrent operations completed in {execution_time:.2f} seconds"
            )

            # Verify data consistency
            final_count = await nodes[0].execute_async(
                query="SELECT COUNT(*) as count FROM performance_test WHERE data LIKE :pattern",
                params={"pattern": "concurrent_test_%"},
            )

            write_operations = len(
                [
                    r
                    for i, r in enumerate(results)
                    if i % 3 == 1 and not isinstance(r, Exception)
                ]
            )
            assert final_count["result"]["data"][0]["count"] == write_operations

        finally:
            for node in nodes:
                await node.cleanup()

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, comprehensive_database_setup):
        """Test memory usage during sustained operations."""
        conn_string = comprehensive_database_setup

        node = AsyncSQLDatabaseNode(
            name="memory_test",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=10,
            max_pool_size=20,
        )

        try:
            # Get initial memory usage
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Perform many operations
            for batch in range(10):  # 10 batches
                tasks = []

                # Create batch of operations
                for i in range(50):  # 50 operations per batch
                    task = node.execute_async(
                        query="""
                            INSERT INTO performance_test (data, number_value, json_data)
                            VALUES (:data, :number, :json_data)
                        """,
                        params={
                            "data": f"memory_test_batch_{batch}_item_{i}",
                            "number": batch * 50 + i,
                            "json_data": {
                                "batch": batch,
                                "item": i,
                                "large_data": "x" * 1000,
                            },
                        },
                    )
                    tasks.append(task)

                # Execute batch
                await asyncio.gather(*tasks)

                # Force garbage collection
                gc.collect()

                # Check memory usage
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = current_memory - initial_memory

                print(
                    f"Batch {batch}: Memory usage {current_memory:.1f}MB (+{memory_increase:.1f}MB)"
                )

                # Memory increase should be reasonable (not constantly growing)
                assert (
                    memory_increase < 100
                ), f"Memory usage increased by {memory_increase:.1f}MB - possible memory leak"

            # Verify all data was inserted
            final_count = await node.execute_async(
                query="SELECT COUNT(*) as count FROM performance_test WHERE data LIKE :pattern",
                params={"pattern": "memory_test_%"},
            )

            assert (
                final_count["result"]["data"][0]["count"] == 500
            )  # 10 batches * 50 items

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_failure_recovery(self, comprehensive_database_setup):
        """Test recovery from connection failures."""
        conn_string = comprehensive_database_setup

        node = AsyncSQLDatabaseNode(
            name="failure_recovery_test",
            database_type="postgresql",
            connection_string=conn_string,
            max_retries=3,
            retry_delay=0.5,
        )

        try:
            # Normal operation should work
            result = await node.execute_async(
                query="INSERT INTO performance_test (data, number_value) VALUES (:data, :number)",
                params={"data": "before_failure", "number": 1},
            )
            assert "result" in result

            # Simulate connection failure by clearing adapter
            node._adapter = None
            node._connected = False

            # Next operation should recover automatically
            result = await node.execute_async(
                query="INSERT INTO performance_test (data, number_value) VALUES (:data, :number)",
                params={"data": "after_recovery", "number": 2},
            )
            assert "result" in result

            # Verify both records exist
            count_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM performance_test WHERE data IN (:val1, :val2)",
                params={"val1": "before_failure", "val2": "after_recovery"},
            )

            assert count_result["result"]["data"][0]["count"] == 2

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_large_result_set_handling(self, comprehensive_database_setup):
        """Test handling of large result sets."""
        conn_string = comprehensive_database_setup

        # Insert large dataset
        setup_node = AsyncSQLDatabaseNode(
            name="large_data_setup",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Insert data in batches to avoid memory issues
        for batch in range(10):
            params_list = []
            for i in range(100):  # 100 records per batch
                record_id = batch * 100 + i
                params_list.append(
                    {
                        "data": f"large_dataset_record_{record_id}",
                        "number": record_id,
                        "json_data": {
                            "id": record_id,
                            "batch": batch,
                            "data": ["item1", "item2", "item3"],
                        },
                    }
                )

            await setup_node.execute_many_async(
                query="""
                    INSERT INTO performance_test (data, number_value, json_data)
                    VALUES (:data, :number, :json_data)
                """,
                params_list=params_list,
            )

        try:
            # Test different fetch modes with large dataset
            # Test 'all' mode
            all_node = AsyncSQLDatabaseNode(
                name="all_fetch_test",
                database_type="postgresql",
                connection_string=conn_string,
                fetch_mode="all",
            )

            start_time = time.time()
            all_result = await all_node.execute_async(
                query="SELECT * FROM performance_test WHERE data LIKE :pattern ORDER BY number_value",
                params={"pattern": "large_dataset_%"},
            )
            all_time = time.time() - start_time

            assert len(all_result["result"]["data"]) == 1000
            print(f"Fetched 1000 records in 'all' mode: {all_time:.2f} seconds")

            # Test 'many' mode
            many_node = AsyncSQLDatabaseNode(
                name="many_fetch_test",
                database_type="postgresql",
                connection_string=conn_string,
                fetch_mode="many",
                fetch_size=100,
            )

            start_time = time.time()
            many_result = await many_node.execute_async(
                query="SELECT * FROM performance_test WHERE data LIKE :pattern ORDER BY number_value",
                params={"pattern": "large_dataset_%"},
            )
            many_time = time.time() - start_time

            assert len(many_result["result"]["data"]) == 100  # Limited by fetch_size
            print(f"Fetched 100 records in 'many' mode: {many_time:.2f} seconds")

            # Test result format with large dataset
            list_node = AsyncSQLDatabaseNode(
                name="list_format_test",
                database_type="postgresql",
                connection_string=conn_string,
                result_format="list",
            )

            start_time = time.time()
            list_result = await list_node.execute_async(
                query="SELECT id, data, number_value FROM performance_test WHERE data LIKE :pattern LIMIT 500",
                params={"pattern": "large_dataset_%"},
            )
            list_time = time.time() - start_time

            assert len(list_result["result"]["data"]) == 500
            assert isinstance(list_result["result"]["data"][0], list)
            print(f"Formatted 500 records as lists: {list_time:.2f} seconds")

            await all_node.cleanup()
            await many_node.cleanup()
            await list_node.cleanup()

        finally:
            await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_complex_transaction_scenarios(self, comprehensive_database_setup):
        """Test complex transaction scenarios with real business logic."""
        conn_string = comprehensive_database_setup

        node = AsyncSQLDatabaseNode(
            name="complex_transaction_test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="manual",
        )

        try:
            # Scenario: Process multiple orders in single transaction
            await node.begin_transaction()

            # Create orders for different users
            orders_data = [
                {"user_id": 1, "total_amount": 59.97},  # 3 x Product A
                {"user_id": 2, "total_amount": 39.98},  # 2 x Product B
                {"user_id": 3, "total_amount": 49.97},  # 1 x Product A + 3 x Product C
            ]

            order_ids = []
            for order_data in orders_data:
                order_result = await node.execute_async(
                    query="""
                        INSERT INTO orders (user_id, total_amount, status)
                        VALUES (:user_id, :total_amount, 'processing')
                        RETURNING id
                    """,
                    params=order_data,
                )
                order_ids.append(order_result["result"]["data"][0]["id"])

            # Add order items
            order_items_data = [
                # Order 1 items
                {
                    "order_id": order_ids[0],
                    "product_id": 1,
                    "quantity": 3,
                    "unit_price": 19.99,
                    "total_price": 59.97,
                },
                # Order 2 items
                {
                    "order_id": order_ids[1],
                    "product_id": 2,
                    "quantity": 2,
                    "unit_price": 29.99,
                    "total_price": 59.98,
                },
                # Order 3 items
                {
                    "order_id": order_ids[2],
                    "product_id": 1,
                    "quantity": 1,
                    "unit_price": 19.99,
                    "total_price": 19.99,
                },
                {
                    "order_id": order_ids[2],
                    "product_id": 3,
                    "quantity": 3,
                    "unit_price": 9.99,
                    "total_price": 29.97,
                },
            ]

            await node.execute_many_async(
                query="""
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
                    VALUES (:order_id, :product_id, :quantity, :unit_price, :total_price)
                """,
                params_list=order_items_data,
            )

            # Update product stock
            stock_updates = [
                {"product_id": 1, "quantity_sold": 4},  # 3 + 1
                {"product_id": 2, "quantity_sold": 2},
                {"product_id": 3, "quantity_sold": 3},
            ]

            for update in stock_updates:
                await node.execute_async(
                    query="""
                        UPDATE products
                        SET stock_quantity = stock_quantity - :quantity_sold
                        WHERE id = :product_id
                    """,
                    params=update,
                )

            # Update order statuses
            await node.execute_async(
                query="UPDATE orders SET status = 'confirmed', updated_at = NOW() WHERE id = ANY(:order_ids)",
                params={"order_ids": order_ids},
            )

            # Commit all changes
            await node.commit()

            # Verify transaction results
            orders_count = await node.execute_async(
                query="SELECT COUNT(*) as count FROM orders WHERE status = 'confirmed'"
            )
            assert orders_count["result"]["data"][0]["count"] == 3

            items_count = await node.execute_async(
                query="SELECT COUNT(*) as count FROM order_items"
            )
            assert items_count["result"]["data"][0]["count"] == 4

            # Verify stock updates
            stock_result = await node.execute_async(
                query="SELECT id, stock_quantity FROM products ORDER BY id"
            )

            stock_data = stock_result["result"]["data"]
            assert stock_data[0]["stock_quantity"] == 96  # 100 - 4
            assert stock_data[1]["stock_quantity"] == 48  # 50 - 2
            assert stock_data[2]["stock_quantity"] == 197  # 200 - 3

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pool_stress_test(self, comprehensive_database_setup):
        """Test connection pool under stress conditions."""
        conn_string = comprehensive_database_setup

        # Create node with limited pool size
        node = AsyncSQLDatabaseNode(
            name="pool_stress_test",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=3,
            max_pool_size=6,
            timeout=10.0,
        )

        try:
            # Create many concurrent long-running operations
            async def long_running_operation(index):
                # Simulate longer operation with multiple queries
                await node.execute_async(
                    query="INSERT INTO performance_test (data, number_value) VALUES (:data, :number)",
                    params={"data": f"stress_test_{index}", "number": index},
                )

                # Small delay to increase contention
                await asyncio.sleep(0.1)

                return await node.execute_async(
                    query="SELECT * FROM performance_test WHERE data = :data",
                    params={"data": f"stress_test_{index}"},
                )

            # Run 30 concurrent operations with limited pool
            tasks = [long_running_operation(i) for i in range(30)]

            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Check results
            successful_operations = 0
            for result in results:
                if isinstance(result, Exception):
                    print(f"Operation failed: {result}")
                else:
                    successful_operations += 1
                    assert len(result["result"]["data"]) == 1

            # All operations should complete successfully despite pool limitations
            assert (
                successful_operations == 30
            ), f"Only {successful_operations}/30 operations succeeded"

            execution_time = end_time - start_time
            print(
                f"30 concurrent operations with limited pool completed in {execution_time:.2f} seconds"
            )

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_data_type_handling_comprehensive(self, comprehensive_database_setup):
        """Test comprehensive data type handling."""
        conn_string = comprehensive_database_setup

        node = AsyncSQLDatabaseNode(
            name="data_type_test",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        try:
            # Create table with various data types
            await node.execute_async(
                query="""
                CREATE TEMPORARY TABLE data_type_test (
                    id SERIAL PRIMARY KEY,
                    text_field TEXT,
                    integer_field INTEGER,
                    decimal_field DECIMAL(10, 2),
                    boolean_field BOOLEAN,
                    date_field DATE,
                    timestamp_field TIMESTAMP,
                    json_field JSONB,
                    array_field INTEGER[],
                    uuid_field UUID
                )
            """
            )

            # Insert data with various types
            test_data = {
                "text_field": "Test string with special chars: àáâãäå",
                "integer_field": 42,
                "decimal_field": 123.45,
                "boolean_field": True,
                "date_field": date(2024, 1, 15),
                "timestamp_field": datetime(2024, 1, 15, 10, 30, 0),
                "json_field": {"key": "value", "nested": {"array": [1, 2, 3]}},
                "array_field": [1, 2, 3, 4, 5],
                "uuid_field": uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            }

            insert_result = await node.execute_async(
                query="""
                    INSERT INTO data_type_test (
                        text_field, integer_field, decimal_field, boolean_field,
                        date_field, timestamp_field, json_field, array_field, uuid_field
                    ) VALUES (
                        :text_field, :integer_field, :decimal_field, :boolean_field,
                        :date_field, :timestamp_field, :json_field, :array_field, :uuid_field
                    ) RETURNING id
                """,
                params=test_data,
            )

            record_id = insert_result["result"]["data"][0]["id"]

            # Retrieve and verify data
            select_result = await node.execute_async(
                query="SELECT * FROM data_type_test WHERE id = :id",
                params={"id": record_id},
            )

            retrieved_data = select_result["result"]["data"][0]

            # Verify data integrity
            assert retrieved_data["text_field"] == test_data["text_field"]
            assert retrieved_data["integer_field"] == test_data["integer_field"]
            assert float(retrieved_data["decimal_field"]) == float(
                test_data["decimal_field"]
            )
            assert retrieved_data["boolean_field"] == test_data["boolean_field"]
            # JSON field is returned as string, need to parse it
            assert json.loads(retrieved_data["json_field"]) == test_data["json_field"]
            assert retrieved_data["array_field"] == test_data["array_field"]
            # UUID field comparison - PostgreSQL returns as string, convert to UUID
            assert uuid.UUID(retrieved_data["uuid_field"]) == test_data["uuid_field"]

            # Test NULL handling
            null_result = await node.execute_async(
                query="""
                    INSERT INTO data_type_test (text_field, integer_field)
                    VALUES (:text, :number)
                    RETURNING id
                """,
                params={"text": "with_nulls", "number": None},
            )

            null_record_id = null_result["result"]["data"][0]["id"]

            null_select = await node.execute_async(
                query="SELECT * FROM data_type_test WHERE id = :id",
                params={"id": null_record_id},
            )

            null_data = null_select["result"]["data"][0]
            assert null_data["text_field"] == "with_nulls"
            assert null_data["integer_field"] is None
            assert null_data["decimal_field"] is None

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_performance_benchmarking(self, comprehensive_database_setup):
        """Test performance benchmarking scenarios."""
        conn_string = comprehensive_database_setup

        node = AsyncSQLDatabaseNode(
            name="performance_benchmark",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=10,
            max_pool_size=20,
        )

        try:
            # Benchmark single inserts
            start_time = time.time()
            for i in range(100):
                await node.execute_async(
                    query="INSERT INTO performance_test (data, number_value) VALUES (:data, :number)",
                    params={"data": f"single_insert_{i}", "number": i},
                )
            single_insert_time = time.time() - start_time

            # Benchmark batch inserts
            batch_params = [
                {"data": f"batch_insert_{i}", "number": i + 1000} for i in range(100)
            ]

            start_time = time.time()
            await node.execute_many_async(
                query="INSERT INTO performance_test (data, number_value) VALUES (:data, :number)",
                params_list=batch_params,
            )
            batch_insert_time = time.time() - start_time

            # Benchmark large selects
            start_time = time.time()
            large_select = await node.execute_async(
                query="SELECT * FROM performance_test ORDER BY number_value"
            )
            large_select_time = time.time() - start_time

            # Benchmark complex queries
            start_time = time.time()
            complex_query = await node.execute_async(
                query="""
                    SELECT
                        COUNT(*) as total_records,
                        AVG(number_value) as avg_number,
                        MAX(number_value) as max_number,
                        MIN(number_value) as min_number
                    FROM performance_test
                    WHERE data LIKE :pattern
                """,
                params={"pattern": "%insert%"},
            )
            complex_query_time = time.time() - start_time

            # Print benchmark results
            print("\n=== Performance Benchmark Results ===")
            print(
                f"Single inserts (100 ops): {single_insert_time:.3f}s ({100/single_insert_time:.1f} ops/sec)"
            )
            print(
                f"Batch insert (100 ops): {batch_insert_time:.3f}s ({100/batch_insert_time:.1f} ops/sec)"
            )
            print(
                f"Large select ({len(large_select['result']['data'])} rows): {large_select_time:.3f}s"
            )
            print(f"Complex query: {complex_query_time:.3f}s")

            # Verify results
            assert single_insert_time < 10.0, "Single inserts took too long"
            assert (
                batch_insert_time < single_insert_time
            ), "Batch insert should be faster than individual inserts"
            assert large_select_time < 5.0, "Large select took too long"
            assert complex_query_time < 2.0, "Complex query took too long"

            # Verify data integrity
            assert (
                len(large_select["result"]["data"]) >= 200
            )  # At least 200 records inserted
            stats = complex_query["result"]["data"][0]
            assert stats["total_records"] == 200  # Exactly 200 insert operations

        finally:
            await node.cleanup()
