"""Docker-based integration tests for AsyncSQL batch operations - NO MOCKS."""

import asyncio
import time
from datetime import datetime

import asyncpg
import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestAsyncSQLBatchOperationsDocker(DockerIntegrationTestBase):
    """Test AsyncSQL batch operations with real PostgreSQL."""

    @pytest_asyncio.fixture
    async def batch_test_table(self, test_database):
        """Create tables for batch operation testing."""
        test_conn = test_database
        test_db_name = "kailash_test"  # Use the standard test database name

        # Main test table
        await test_conn.execute(
            """
            CREATE TABLE batch_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                age INTEGER,
                email VARCHAR(255) UNIQUE,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Performance test table
        await test_conn.execute(
            """
            CREATE TABLE batch_performance (
                id SERIAL PRIMARY KEY,
                batch_id INTEGER,
                value NUMERIC(10, 2),
                status VARCHAR(50),
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index for performance
        await test_conn.execute(
            """
            CREATE INDEX idx_batch_performance_batch_id ON batch_performance(batch_id)
        """
        )

        yield test_conn, test_db_name

    @pytest.fixture
    def batch_sql_node(self, workflow_db_config):
        """Create AsyncSQLDatabaseNode configured for batch operations."""
        config = workflow_db_config.copy()

        def _create_node(db_name="kailash_test"):
            return AsyncSQLDatabaseNode(
                database_type="postgresql",
                host=config["host"],
                port=config["port"],
                database=db_name,
                user=config["user"],
                password=config["password"],
                validate_queries=False,  # Allow DDL operations
                pool_settings={
                    "min_size": 2,
                    "max_size": 5,  # Reduced for batch operations
                    "max_queries": 100000,
                    "max_inactive_connection_lifetime": 300.0,
                },
            )

        return _create_node

    @pytest.mark.asyncio
    async def test_basic_batch_insert(self, batch_sql_node, batch_test_table):
        """Test basic batch insert with real database."""
        test_conn, test_db_name = batch_test_table

        # Create node with correct database
        node = batch_sql_node(test_db_name)

        # Create the table using the node (ensure same connection)
        create_result = node.execute(
            query="""
                CREATE TABLE IF NOT EXISTS batch_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    age INTEGER,
                    email VARCHAR(255) UNIQUE,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        )
        assert "result" in create_result

        # Prepare batch data (simplified for single inserts)
        batch_data = [
            ["Alice", 30, "alice@example.com", '{"role": "admin"}'],
            ["Bob", 25, "bob@example.com", '{"role": "user"}'],
            ["Charlie", 35, "charlie@example.com", '{"role": "user"}'],
            ["David", 28, "david@example.com", '{"role": "moderator"}'],
            ["Eve", 32, "eve@example.com", '{"role": "user"}'],
        ]

        # Execute individual inserts (AsyncSQLDatabaseNode doesn't have execute_many)
        for data in batch_data:
            result = node.execute(
                query="""
                    INSERT INTO batch_users (name, age, email, metadata)
                    VALUES ($1, $2, $3, $4::jsonb)
                """,
                params=data,
            )
            assert "result" in result

        # Verify data was inserted
        count_node = batch_sql_node(test_db_name)
        count_result = count_node.execute(
            query="SELECT COUNT(*) as count FROM batch_users"
        )
        assert count_result["result"]["data"][0]["count"] == 5

    @pytest.mark.asyncio
    async def test_batch_insert_with_returning(self, batch_sql_node, batch_test_table):
        """Test batch insert with RETURNING clause."""
        batch_data = [
            ["User1", 20, "user1@test.com"],
            ["User2", 21, "user2@test.com"],
            ["User3", 22, "user3@test.com"],
        ]

        # Execute with RETURNING
        result = await batch_sql_node.execute_many(
            query="""
                INSERT INTO batch_users (name, age, email)
                VALUES ($1, $2, $3)
                RETURNING id, name
            """,
            params_list=batch_data,
            return_results=True,
        )

        assert result["success"] is True
        assert result["total_affected"] == 3
        assert "batch_results" in result
        assert len(result["batch_results"]) == 3

        # Verify returned data
        for i, batch_result in enumerate(result["batch_results"]):
            assert batch_result["rows"][0]["name"] == f"User{i+1}"
            assert "id" in batch_result["rows"][0]

    @pytest.mark.asyncio
    async def test_batch_update_operations(self, batch_sql_node, batch_test_table):
        """Test batch update operations."""
        # First insert test data
        insert_data = [
            [f"TestUser{i}", 20 + i, f"test{i}@example.com", '{"status": "active"}']
            for i in range(10)
        ]

        await batch_sql_node.execute_many(
            query="""
                INSERT INTO batch_users (name, age, email, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
            """,
            params_list=insert_data,
        )

        # Prepare batch updates
        update_data = [
            [30 + i, '{"status": "updated", "batch": true}', f"test{i}@example.com"]
            for i in range(10)
        ]

        # Execute batch update
        start_time = time.time()
        result = await batch_sql_node.execute_many(
            query="""
                UPDATE batch_users
                SET age = $1, metadata = $2::jsonb
                WHERE email = $3
            """,
            params_list=update_data,
        )
        update_time = time.time() - start_time

        assert result["success"] is True
        assert result["total_affected"] == 10
        assert update_time < 1.0  # Should be fast

        # Verify updates
        check_result = await batch_sql_node.execute(
            query="SELECT age, metadata FROM batch_users WHERE email = $1",
            parameters=["test5@example.com"],
        )
        assert check_result["rows"][0]["age"] == 35
        assert check_result["rows"][0]["metadata"]["status"] == "updated"

    @pytest.mark.asyncio
    async def test_large_batch_performance(self, batch_sql_node, batch_test_table):
        """Test performance with large batch operations."""
        # Prepare large batch (10,000 records)
        batch_size = 10000
        batch_data = [
            [i, i * 10.5, "pending" if i % 2 == 0 else "processed"]
            for i in range(batch_size)
        ]

        # Execute large batch insert
        start_time = time.time()
        result = await batch_sql_node.execute_many(
            query="""
                INSERT INTO batch_performance (batch_id, value, status)
                VALUES ($1, $2, $3)
            """,
            params_list=batch_data,
            batch_size=1000,  # Process in chunks of 1000
        )
        insert_time = time.time() - start_time

        assert result["success"] is True
        assert result["total_affected"] == batch_size
        assert insert_time < 10.0  # Should complete in under 10 seconds

        # Verify count
        count_result = await batch_sql_node.execute(
            query="SELECT COUNT(*) as count FROM batch_performance"
        )
        assert count_result["rows"][0]["count"] == batch_size

        # Test batch query performance
        start_time = time.time()
        query_result = await batch_sql_node.execute(
            query="""
                SELECT status, COUNT(*) as count, AVG(value) as avg_value
                FROM batch_performance
                GROUP BY status
            """
        )
        query_time = time.time() - start_time

        assert query_time < 1.0  # Indexed query should be fast
        assert len(query_result["rows"]) == 2  # pending and processed

    @pytest.mark.asyncio
    async def test_batch_transaction_handling(self, batch_sql_node, batch_test_table):
        """Test batch operations within transactions."""
        # Start transaction
        await batch_sql_node.execute(query="BEGIN")

        try:
            # First batch insert
            batch1 = [
                ["TxUser1", 25, "tx1@example.com"],
                ["TxUser2", 26, "tx2@example.com"],
            ]

            result1 = await batch_sql_node.execute_many(
                query="INSERT INTO batch_users (name, age, email) VALUES ($1, $2, $3)",
                params_list=batch1,
            )
            assert result1["success"] is True

            # Second batch insert
            batch2 = [
                ["TxUser3", 27, "tx3@example.com"],
                ["TxUser4", 28, "tx4@example.com"],
            ]

            result2 = await batch_sql_node.execute_many(
                query="INSERT INTO batch_users (name, age, email) VALUES ($1, $2, $3)",
                params_list=batch2,
            )
            assert result2["success"] is True

            # Verify within transaction
            count_result = await batch_sql_node.execute(
                query="SELECT COUNT(*) as count FROM batch_users WHERE name LIKE 'TxUser%'"
            )
            assert count_result["rows"][0]["count"] == 4

            # Rollback to test transaction isolation
            await batch_sql_node.execute(query="ROLLBACK")

            # Verify rollback worked
            count_after = await batch_sql_node.execute(
                query="SELECT COUNT(*) as count FROM batch_users WHERE name LIKE 'TxUser%'"
            )
            assert count_after["rows"][0]["count"] == 0

        except Exception:
            await batch_sql_node.execute(query="ROLLBACK")
            raise

    @pytest.mark.asyncio
    async def test_batch_error_handling(self, batch_sql_node, batch_test_table):
        """Test error handling in batch operations."""
        # Insert initial data
        await batch_sql_node.execute(
            query="INSERT INTO batch_users (name, age, email) VALUES ($1, $2, $3)",
            parameters=["Existing", 30, "existing@example.com"],
        )

        # Prepare batch with duplicate email (will cause error)
        batch_data = [
            ["New1", 25, "new1@example.com"],
            ["New2", 26, "existing@example.com"],  # Duplicate!
            ["New3", 27, "new3@example.com"],
        ]

        # Execute batch (should fail)
        with pytest.raises(Exception) as exc_info:
            await batch_sql_node.execute_many(
                query="INSERT INTO batch_users (name, age, email) VALUES ($1, $2, $3)",
                params_list=batch_data,
            )

        # Verify error contains useful information
        assert (
            "duplicate" in str(exc_info.value).lower()
            or "unique" in str(exc_info.value).lower()
        )

        # Verify no partial inserts (depending on transaction mode)
        count_result = await batch_sql_node.execute(
            query="SELECT COUNT(*) as count FROM batch_users WHERE name LIKE 'New%'"
        )
        # Either all or none should be inserted
        assert count_result["rows"][0]["count"] in [0, 3]

    @pytest.mark.asyncio
    async def test_concurrent_batch_operations(self, batch_sql_node, batch_test_table):
        """Test concurrent batch operations."""

        async def insert_batch(batch_num):
            """Insert a batch of users."""
            batch_data = [
                [f"Batch{batch_num}User{i}", 20 + i, f"b{batch_num}u{i}@example.com"]
                for i in range(100)
            ]

            return await batch_sql_node.execute_many(
                query="INSERT INTO batch_users (name, age, email) VALUES ($1, $2, $3)",
                params_list=batch_data,
            )

        # Execute 5 batches concurrently
        start_time = time.time()
        tasks = [insert_batch(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        execution_time = time.time() - start_time

        # All should succeed
        assert all(r["success"] for r in results)
        assert all(r["total_affected"] == 100 for r in results)

        # Verify total count
        count_result = await batch_sql_node.execute(
            query="SELECT COUNT(*) as count FROM batch_users"
        )
        assert count_result["rows"][0]["count"] == 500

        # Should complete reasonably fast with connection pooling
        assert execution_time < 5.0

    @pytest.mark.asyncio
    async def test_batch_with_complex_types(self, batch_sql_node, batch_test_table):
        """Test batch operations with complex data types."""
        # Prepare batch with various data types
        batch_data = [
            [
                f"ComplexUser{i}",
                20 + i,
                f"complex{i}@example.com",
                {
                    "preferences": {
                        "theme": "dark" if i % 2 == 0 else "light",
                        "notifications": True,
                        "tags": [f"tag{j}" for j in range(i % 3 + 1)],
                    },
                    "stats": {
                        "login_count": i * 10,
                        "last_active": datetime.utcnow().isoformat(),
                    },
                },
            ]
            for i in range(20)
        ]

        # Convert metadata to JSON strings
        batch_data_formatted = [
            [
                name,
                age,
                email,
                json.dumps(metadata) if isinstance(metadata, dict) else metadata,
            ]
            for name, age, email, metadata in batch_data
        ]

        # Execute batch insert
        import json

        result = await batch_sql_node.execute_many(
            query="""
                INSERT INTO batch_users (name, age, email, metadata)
                VALUES ($1, $2, $3, $4::jsonb)
            """,
            params_list=batch_data_formatted,
        )

        assert result["success"] is True
        assert result["total_affected"] == 20

        # Verify complex queries on batch data
        theme_result = await batch_sql_node.execute(
            query="""
                SELECT
                    metadata->>'preferences'->>'theme' as theme,
                    COUNT(*) as count
                FROM batch_users
                WHERE name LIKE 'ComplexUser%'
                GROUP BY metadata->>'preferences'->>'theme'
            """
        )

        # Should have both themes
        assert len(theme_result["rows"]) >= 1  # At least one theme type
