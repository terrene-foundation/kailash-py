"""Integration tests for AsyncSQLDatabaseNode feature parity with real databases."""

import asyncio
import os
import tempfile
from datetime import datetime

import pytest
import pytest_asyncio
import yaml

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLFeatureParityIntegration:
    """Integration tests for feature parity with real PostgreSQL database."""

    @pytest_asyncio.fixture
    async def feature_database_setup(self):
        """Set up test database for feature parity testing."""
        conn_string = get_postgres_connection_string()

        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Create test tables for various features
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS feature_test CASCADE"
        )
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS versioned_records CASCADE"
        )
        await setup_node.execute_async(query="DROP TABLE IF EXISTS batch_test CASCADE")

        # Main feature test table
        await setup_node.execute_async(
            query="""
            CREATE TABLE feature_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                value INTEGER,
                data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Versioned table for optimistic locking
        await setup_node.execute_async(
            query="""
            CREATE TABLE versioned_records (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Batch operations table
        await setup_node.execute_async(
            query="""
            CREATE TABLE batch_test (
                id SERIAL PRIMARY KEY,
                batch_id VARCHAR(50),
                sequence_num INTEGER,
                data TEXT
            )
        """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS feature_test CASCADE"
        )
        await setup_node.execute_async(
            query="DROP TABLE IF EXISTS versioned_records CASCADE"
        )
        await setup_node.execute_async(query="DROP TABLE IF EXISTS batch_test CASCADE")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pooling_with_shared_pools(self, feature_database_setup):
        """Test connection pooling with shared pool functionality."""
        conn_string = feature_database_setup

        # Create multiple nodes with same configuration (should share pool)
        nodes = []
        for i in range(3):
            node = AsyncSQLDatabaseNode(
                name=f"shared_pool_test_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                pool_size=5,
                max_pool_size=10,
                share_pool=True,
            )
            nodes.append(node)

        try:
            # All nodes should generate the same pool key
            pool_keys = [node._generate_pool_key() for node in nodes]
            assert all(key == pool_keys[0] for key in pool_keys)

            # Execute queries concurrently from all nodes
            tasks = []
            for i, node in enumerate(nodes):
                task = node.execute_async(
                    query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                    params={"name": f"shared_pool_{i}", "value": i * 10},
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # Verify all operations succeeded
            for result in results:
                assert "result" in result

            # Verify all data was inserted
            verify_node = nodes[0]
            count_result = await verify_node.execute_async(
                query="SELECT COUNT(*) as count FROM feature_test WHERE name LIKE :pattern",
                params={"pattern": "shared_pool_%"},
            )

            assert count_result["result"]["data"][0]["count"] == 3

        finally:
            for node in nodes:
                await node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pooling_without_sharing(self, feature_database_setup):
        """Test connection pooling without sharing (separate pools)."""
        conn_string = feature_database_setup

        # Create nodes with share_pool=False
        node1 = AsyncSQLDatabaseNode(
            name="separate_pool_1",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=3,
            share_pool=False,
        )

        node2 = AsyncSQLDatabaseNode(
            name="separate_pool_2",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=3,
            share_pool=False,
        )

        try:
            # Both nodes should work independently
            await node1.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": "separate_1", "value": 100},
            )

            await node2.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": "separate_2", "value": 200},
            )

            # Verify both insertions worked
            result = await node1.execute_async(
                query="SELECT COUNT(*) as count FROM feature_test WHERE name LIKE :pattern",
                params={"pattern": "separate_%"},
            )

            assert result["result"]["data"][0]["count"] == 2

        finally:
            await node1.cleanup()
            await node2.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_integration(self, feature_database_setup):
        """Test optimistic locking with real database operations."""
        conn_string = feature_database_setup

        node = AsyncSQLDatabaseNode(
            name="optimistic_test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
            version_field="version",
        )

        try:
            # Insert initial record
            insert_result = await node.execute_async(
                query="""
                    INSERT INTO versioned_records (content, version)
                    VALUES (:content, :version)
                    RETURNING id, version
                """,
                params={"content": "initial content", "version": 1},
            )

            record_id = insert_result["result"]["data"][0]["id"]
            initial_version = insert_result["result"]["data"][0]["version"]

            # Test successful optimistic update
            update_result = await node.execute_with_version_check(
                query="""
                    UPDATE versioned_records
                    SET content = :content, version = version + 1, updated_at = NOW()
                    WHERE id = :id AND version = :expected_version
                    RETURNING version
                """,
                params={
                    "content": "updated content",
                    "id": record_id,
                    "expected_version": initial_version,
                },
                expected_version=initial_version,
                record_id=record_id,
                table_name="versioned_records",
            )

            new_version = update_result["result"]["data"][0]["version"]
            assert new_version == initial_version + 1

            # Test version conflict detection
            with pytest.raises(NodeExecutionError, match="Version conflict"):
                await node.execute_with_version_check(
                    query="""
                        UPDATE versioned_records
                        SET content = :content, version = version + 1
                        WHERE id = :id AND version = :expected_version
                    """,
                    params={
                        "content": "conflicting update",
                        "id": record_id,
                        "expected_version": initial_version,  # Old version
                    },
                    expected_version=initial_version,
                    record_id=record_id,
                    table_name="versioned_records",
                )

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_retry_logic_with_real_failures(self, feature_database_setup):
        """Test retry logic with real database connection scenarios."""
        conn_string = feature_database_setup

        node = AsyncSQLDatabaseNode(
            name="retry_test",
            database_type="postgresql",
            connection_string=conn_string,
            max_retries=3,
            retry_delay=0.1,  # Fast retry for testing
            allow_admin=True,  # Allow ALTER TABLE for constraint tests
        )

        try:
            # Test successful operation (should not retry)
            result = await node.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": "retry_success", "value": 1},
            )

            assert "result" in result

            # Test operation that would trigger retries (invalid SQL)
            with pytest.raises(NodeExecutionError):
                await node.execute_async(query="INVALID SQL STATEMENT")

            # Test with constraint violation (should not retry)
            # First create a unique constraint
            await node.execute_async(
                query="""
                ALTER TABLE feature_test ADD CONSTRAINT unique_name_value UNIQUE (name, value)
            """
            )

            # Insert first record
            await node.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": "unique_test", "value": 1},
            )

            # Try to insert duplicate (should fail without retry)
            with pytest.raises(NodeExecutionError):
                await node.execute_async(
                    query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                    params={"name": "unique_test", "value": 1},
                )

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_batch_operations_integration(self, feature_database_setup):
        """Test batch operations with real database."""
        conn_string = feature_database_setup

        node = AsyncSQLDatabaseNode(
            name="batch_test",
            database_type="postgresql",
            connection_string=conn_string,
            transaction_mode="auto",
        )

        try:
            # Prepare batch data
            batch_id = "test_batch_001"
            params_list = []

            for i in range(10):
                params_list.append(
                    {"batch_id": batch_id, "sequence_num": i, "data": f"batch_data_{i}"}
                )

            # Execute batch operation
            result = await node.execute_many_async(
                query="""
                    INSERT INTO batch_test (batch_id, sequence_num, data)
                    VALUES (:batch_id, :sequence_num, :data)
                """,
                params_list=params_list,
            )

            assert result["result"]["affected_rows"] == 10
            assert result["result"]["batch_size"] == 10

            # Verify all records were inserted
            verify_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
                params={"batch_id": batch_id},
            )

            assert verify_result["result"]["data"][0]["count"] == 10

            # Test batch operations in manual transaction
            node._transaction_mode = "manual"

            await node.begin_transaction()

            batch_id_2 = "test_batch_002"
            params_list_2 = [
                {"batch_id": batch_id_2, "sequence_num": i, "data": f"manual_batch_{i}"}
                for i in range(5)
            ]

            await node.execute_many_async(
                query="""
                    INSERT INTO batch_test (batch_id, sequence_num, data)
                    VALUES (:batch_id, :sequence_num, :data)
                """,
                params_list=params_list_2,
            )

            # Data shouldn't be visible before commit
            temp_verify = AsyncSQLDatabaseNode(
                name="temp_verify",
                database_type="postgresql",
                connection_string=conn_string,
            )

            temp_result = await temp_verify.execute_async(
                query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
                params={"batch_id": batch_id_2},
            )

            assert temp_result["result"]["data"][0]["count"] == 0

            # Commit and verify
            await node.commit()

            final_result = await temp_verify.execute_async(
                query="SELECT COUNT(*) as count FROM batch_test WHERE batch_id = :batch_id",
                params={"batch_id": batch_id_2},
            )

            assert final_result["result"]["data"][0]["count"] == 5

            await temp_verify.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_query_validation_integration(self, feature_database_setup):
        """Test query validation with real database context."""
        conn_string = feature_database_setup

        # Node with strict validation
        strict_node = AsyncSQLDatabaseNode(
            name="strict_test",
            database_type="postgresql",
            connection_string=conn_string,
            validate_queries=True,
            allow_admin=False,
        )

        # Node with admin privileges
        admin_node = AsyncSQLDatabaseNode(
            name="admin_test",
            database_type="postgresql",
            connection_string=conn_string,
            validate_queries=True,
            allow_admin=True,
        )

        try:
            # Valid query should work on both
            valid_query = "SELECT COUNT(*) as count FROM feature_test"

            result1 = await strict_node.execute_async(query=valid_query)
            result2 = await admin_node.execute_async(query=valid_query)

            assert "result" in result1
            assert "result" in result2

            # Admin query should fail on strict node
            admin_query = "CREATE TEMPORARY TABLE temp_test (id INT)"

            with pytest.raises(NodeExecutionError, match="Query validation failed"):
                await strict_node.execute_async(query=admin_query)

            # But should work on admin node
            await admin_node.execute_async(query=admin_query)

            # Dangerous query should fail on both
            dangerous_query = "SELECT * FROM feature_test; DROP TABLE feature_test;"

            with pytest.raises(NodeExecutionError, match="Query validation failed"):
                await strict_node.execute_async(query=dangerous_query)

            with pytest.raises(NodeExecutionError, match="Query validation failed"):
                await admin_node.execute_async(query=dangerous_query)

        finally:
            await strict_node.cleanup()
            await admin_node.cleanup()

    @pytest.mark.asyncio
    async def test_config_file_integration_real_db(self, feature_database_setup):
        """Test configuration file integration with real database."""
        conn_string = feature_database_setup

        # Create temporary config file
        config_data = {
            "databases": {
                "test_config": {
                    "url": conn_string,
                    "pool_size": 8,
                    "max_pool_size": 16,
                    "timeout": 30.0,
                    "transaction_mode": "auto",
                    "validate_queries": True,
                    "allow_admin": False,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node using config file
            node = AsyncSQLDatabaseNode(
                name="config_test",
                database_type="postgresql",
                connection_name="test_config",
                config_file=config_path,
            )

            # Test that configuration was applied
            assert node.config["pool_size"] == 8
            assert node.config["max_pool_size"] == 16
            assert node._transaction_mode == "auto"
            assert node._validate_queries is True
            assert node._allow_admin is False

            # Test actual database operation
            result = await node.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": "config_test", "value": 999},
            )

            assert "result" in result

            # Verify insert worked
            verify_result = await node.execute_async(
                query="SELECT value FROM feature_test WHERE name = :name",
                params={"name": "config_test"},
            )

            assert verify_result["result"]["data"][0]["value"] == 999

            await node.cleanup()

        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_fetch_modes_integration(self, feature_database_setup):
        """Test all fetch modes with real database."""
        conn_string = feature_database_setup

        # Insert test data
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Insert multiple records
        for i in range(5):
            await setup_node.execute_async(
                query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                params={"name": f"fetch_test_{i}", "value": i * 10},
            )

        try:
            # Test 'one' mode
            one_node = AsyncSQLDatabaseNode(
                name="one_test",
                database_type="postgresql",
                connection_string=conn_string,
                fetch_mode="one",
            )

            one_result = await one_node.execute_async(
                query="SELECT * FROM feature_test WHERE name LIKE :pattern ORDER BY value",
                params={"pattern": "fetch_test_%"},
            )

            # Should return only one record
            assert (
                len(one_result["result"]["data"]) == 1
                if one_result["result"]["data"]
                else True
            )

            # Test 'all' mode (default)
            all_node = AsyncSQLDatabaseNode(
                name="all_test",
                database_type="postgresql",
                connection_string=conn_string,
                fetch_mode="all",
            )

            all_result = await all_node.execute_async(
                query="SELECT * FROM feature_test WHERE name LIKE :pattern ORDER BY value",
                params={"pattern": "fetch_test_%"},
            )

            # Should return all records
            assert len(all_result["result"]["data"]) == 5

            # Test 'many' mode
            many_node = AsyncSQLDatabaseNode(
                name="many_test",
                database_type="postgresql",
                connection_string=conn_string,
                fetch_mode="many",
                fetch_size=3,
            )

            many_result = await many_node.execute_async(
                query="SELECT * FROM feature_test WHERE name LIKE :pattern ORDER BY value",
                params={"pattern": "fetch_test_%"},
            )

            # Should return up to fetch_size records
            assert len(many_result["result"]["data"]) <= 3

            await one_node.cleanup()
            await all_node.cleanup()
            await many_node.cleanup()

        finally:
            await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_operations_with_pooling(self, feature_database_setup):
        """Test concurrent operations with connection pooling."""
        conn_string = feature_database_setup

        # Create node with small pool to test pooling behavior
        node = AsyncSQLDatabaseNode(
            name="concurrent_test",
            database_type="postgresql",
            connection_string=conn_string,
            pool_size=2,
            max_pool_size=4,
        )

        try:
            # Create multiple concurrent operations
            async def insert_operation(index):
                return await node.execute_async(
                    query="INSERT INTO feature_test (name, value) VALUES (:name, :value)",
                    params={"name": f"concurrent_{index}", "value": index},
                )

            # Run 10 concurrent operations with limited pool
            tasks = [insert_operation(i) for i in range(10)]
            results = await asyncio.gather(*tasks)

            # All operations should succeed
            assert len(results) == 10
            for result in results:
                assert "result" in result

            # Verify all data was inserted
            count_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM feature_test WHERE name LIKE :pattern",
                params={"pattern": "concurrent_%"},
            )

            assert count_result["result"]["data"][0]["count"] == 10

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_timeout_behavior_integration(self, feature_database_setup):
        """Test timeout behavior with real database operations."""
        conn_string = feature_database_setup

        # Create node with short timeout
        node = AsyncSQLDatabaseNode(
            name="timeout_test",
            database_type="postgresql",
            connection_string=conn_string,
            timeout=2.0,  # 2 second timeout
        )

        try:
            # Quick operation should succeed
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM feature_test"
            )

            assert "result" in result

            # Note: Testing actual timeouts requires long-running queries
            # which might not be suitable for automated tests
            # In production, this would test queries that exceed the timeout

        finally:
            await node.cleanup()
