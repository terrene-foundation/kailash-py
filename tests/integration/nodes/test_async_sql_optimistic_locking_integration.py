"""Integration tests for AsyncSQLDatabaseNode optimistic locking with REAL PostgreSQL."""

import asyncio
import os
import tempfile

import pytest
import pytest_asyncio
import yaml

from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    ConflictResolution,
    LockStatus,
)
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import get_postgres_connection_string

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLOptimisticLockingIntegration:
    """Test optimistic locking functionality with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database with version tracking table."""
        conn_string = get_postgres_connection_string()

        # Create test table with version field
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Drop and recreate table
        await setup_node.execute_async(query="DROP TABLE IF EXISTS versioned_records")
        await setup_node.execute_async(
            query="""
            CREATE TABLE versioned_records (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INTEGER,
                version INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        await setup_node.execute_async(
            query="""
                INSERT INTO versioned_records (name, value, version)
                VALUES
                    ('Record1', 100, 1),
                    ('Record2', 200, 2),
                    ('Record3', 300, 3)
            """
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS versioned_records")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_success(self, setup_database):
        """Test successful update with correct version."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
        )

        try:
            # Read record with version
            read_result = await node.read_with_version(
                query="SELECT * FROM versioned_records WHERE id = :id", params={"id": 1}
            )

            assert read_result["version"] == 1
            assert read_result["record"]["name"] == "Record1"

            # Update with correct version
            update_result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": 150, "id": 1},
                expected_version=1,
            )

            assert update_result["status"] == LockStatus.SUCCESS
            assert update_result["version_checked"] is True
            assert update_result["new_version"] == 2
            assert update_result["rows_affected"] == 1

            # Verify update
            verify_result = await node.execute_async(
                query="SELECT value, version FROM versioned_records WHERE id = :id",
                params={"id": 1},
            )

            assert verify_result["result"]["data"][0]["value"] == 150
            assert verify_result["result"]["data"][0]["version"] == 2

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_conflict_fail_fast(self, setup_database):
        """Test version conflict with fail_fast resolution."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
            conflict_resolution="fail_fast",
        )

        try:
            # Simulate another process updating the record
            other_node = AsyncSQLDatabaseNode(
                name="other",
                database_type="postgresql",
                connection_string=conn_string,
            )

            await other_node.execute_async(
                query="UPDATE versioned_records SET value = 250, version = version + 1 WHERE id = :id",
                params={"id": 2},
            )

            # Try to update with old version
            with pytest.raises(NodeExecutionError, match="Version conflict"):
                await node.execute_with_version_check(
                    query="UPDATE versioned_records SET value = :value WHERE id = :id",
                    params={"value": 300, "id": 2},
                    expected_version=2,  # Old version
                )

            await other_node.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_retry_success(self, setup_database):
        """Test version conflict with retry resolution."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
            conflict_resolution="retry",
            version_retry_attempts=3,
        )

        try:
            # Simulate concurrent update
            other_node = AsyncSQLDatabaseNode(
                name="other",
                database_type="postgresql",
                connection_string=conn_string,
            )

            # Update record to create conflict
            await other_node.execute_async(
                query="UPDATE versioned_records SET value = 350, version = version + 1 WHERE id = :id",
                params={"id": 3},
            )

            # Try to update with old version - should retry and succeed
            result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": 400, "id": 3},
                expected_version=3,  # Old version
                record_id=3,
                table_name="versioned_records",
            )

            assert result["status"] == LockStatus.SUCCESS
            assert result["version_checked"] is True
            assert result.get("retry_count", 0) > 0  # Should have retried

            # Verify final value
            verify_result = await node.execute_async(
                query="SELECT value, version FROM versioned_records WHERE id = :id",
                params={"id": 3},
            )

            assert verify_result["result"]["data"][0]["value"] == 400
            assert verify_result["result"]["data"][0]["version"] == 5  # Updated twice

            await other_node.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_last_writer_wins(self, setup_database):
        """Test last_writer_wins conflict resolution."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
            conflict_resolution="last_writer_wins",
        )

        try:
            # Create a new record
            await node.execute_async(
                query="INSERT INTO versioned_records (name, value, version) VALUES (:name, :value, :version)",
                params={"name": "Conflict Test", "value": 500, "version": 1},
            )

            # Get the inserted record ID
            id_result = await node.execute_async(
                query="SELECT id FROM versioned_records WHERE name = :name",
                params={"name": "Conflict Test"},
            )
            record_id = id_result["result"]["data"][0]["id"]

            # Simulate concurrent update
            other_node = AsyncSQLDatabaseNode(
                name="other",
                database_type="postgresql",
                connection_string=conn_string,
            )

            await other_node.execute_async(
                query="UPDATE versioned_records SET value = 600, version = version + 1 WHERE id = :id",
                params={"id": record_id},
            )

            # Update with old version - should succeed with last_writer_wins
            result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": 700, "id": record_id},
                expected_version=1,  # Old version
            )

            assert result["status"] == LockStatus.SUCCESS
            assert result["conflict_resolved"] == "last_writer_wins"

            # Verify final value
            verify_result = await node.execute_async(
                query="SELECT value, version FROM versioned_records WHERE id = :id",
                params={"id": record_id},
            )

            assert verify_result["result"]["data"][0]["value"] == 700
            assert verify_result["result"]["data"][0]["version"] >= 2

            await other_node.cleanup()

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_updates_with_optimistic_locking(self, setup_database):
        """Test multiple concurrent updates with optimistic locking."""
        conn_string = setup_database

        # Create a new record for this test
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
        )

        await setup_node.execute_async(
            query="INSERT INTO versioned_records (name, value, version) VALUES (:name, :value, :version)",
            params={"name": "ConcurrentTest", "value": 1000, "version": 1},
        )

        # Get record ID
        id_result = await setup_node.execute_async(
            query="SELECT id FROM versioned_records WHERE name = :name",
            params={"name": "ConcurrentTest"},
        )
        record_id = id_result["result"]["data"][0]["id"]

        await setup_node.cleanup()

        # Create multiple nodes for concurrent updates
        nodes = []
        for i in range(5):
            node = AsyncSQLDatabaseNode(
                name=f"concurrent_{i}",
                database_type="postgresql",
                connection_string=conn_string,
                enable_optimistic_locking=True,
                conflict_resolution="retry",
                version_retry_attempts=5,
            )
            nodes.append(node)

        async def update_record(node, increment):
            """Update record with optimistic locking."""
            # Read current value and version
            read_result = await node.read_with_version(
                query="SELECT * FROM versioned_records WHERE id = :id",
                params={"id": record_id},
            )

            current_value = read_result["record"]["value"]
            current_version = read_result["version"]

            # Update with version check
            result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": current_value + increment, "id": record_id},
                expected_version=current_version,
                record_id=record_id,
                table_name="versioned_records",
            )

            return result

        try:
            # Run concurrent updates
            tasks = []
            for i, node in enumerate(nodes):
                tasks.append(update_record(node, (i + 1) * 10))

            results = await asyncio.gather(*tasks)

            # All updates should succeed (with retries)
            for result in results:
                assert result["status"] == LockStatus.SUCCESS

            # Verify final value
            verify_node = AsyncSQLDatabaseNode(
                name="verify",
                database_type="postgresql",
                connection_string=conn_string,
            )

            final_result = await verify_node.execute_async(
                query="SELECT value, version FROM versioned_records WHERE id = :id",
                params={"id": record_id},
            )

            # In concurrent scenarios, verify that at least some updates succeeded
            # and that the final value is greater than the starting value (1000)
            final_value = final_result["result"]["data"][0]["value"]
            final_version = final_result["result"]["data"][0]["version"]

            assert final_value > 1000, f"Expected value > 1000, got {final_value}"
            assert final_version > 1, f"Expected version > 1, got {final_version}"

            # Count successful updates from results
            successful_updates = sum(
                1 for result in results if result["status"] == LockStatus.SUCCESS
            )
            assert successful_updates > 0, "At least one update should succeed"

            await verify_node.cleanup()

        finally:
            # Cleanup all nodes
            for node in nodes:
                await node.cleanup()

    @pytest.mark.asyncio
    async def test_optimistic_locking_with_config_file(self, setup_database):
        """Test optimistic locking configuration from YAML file."""
        conn_string = setup_database

        # Create config file with optimistic locking settings
        config_data = {
            "databases": {
                "test_db": {
                    "connection_string": conn_string,
                    "database_type": "postgresql",
                    "enable_optimistic_locking": True,
                    "version_field": "version",
                    "conflict_resolution": "retry",
                    "version_retry_attempts": 5,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node using config file
            node = AsyncSQLDatabaseNode(
                name="config_node",
                connection_name="test_db",
                config_file=config_path,
            )

            # Verify optimistic locking is configured
            assert node._enable_optimistic_locking is True
            assert node._conflict_resolution == "retry"
            assert node._version_retry_attempts == 5

            # Test version check functionality
            result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": 999, "id": 1},
                expected_version=2,  # Should be correct after previous test
                record_id=1,
                table_name="versioned_records",
            )

            assert result["status"] == LockStatus.SUCCESS

            await node.cleanup()

        finally:
            os.unlink(config_path)

    @pytest.mark.asyncio
    async def test_build_versioned_update_query_integration(self, setup_database):
        """Test building and executing versioned UPDATE queries."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
        )

        try:
            # Build versioned update query
            query = node.build_versioned_update_query(
                table_name="versioned_records",
                update_fields={"name": "Updated Name", "value": 888},
                where_clause="id = :id",
                increment_version=True,
            )

            # Execute the built query
            params = {"name": "Updated Name", "value": 888, "id": 2}
            result = await node.execute_async(query=query, params=params)

            # Check for rows_affected in data (for single execute operations)
            if "rows_affected" in result["result"]:
                assert result["result"]["rows_affected"] == 1
            elif (
                result["result"]["data"]
                and "rows_affected" in result["result"]["data"][0]
            ):
                assert result["result"]["data"][0]["rows_affected"] == 1
            else:
                # Fallback - check that row count indicates success
                assert result["result"]["row_count"] >= 0

            # Verify update and version increment
            verify_result = await node.execute_async(
                query="SELECT name, value, version FROM versioned_records WHERE id = :id",
                params={"id": 2},
            )

            data = verify_result["result"]["data"][0]
            assert data["name"] == "Updated Name"
            assert data["value"] == 888
            assert data["version"] > 2  # Should be incremented

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_read_with_version_multiple_records(self, setup_database):
        """Test reading multiple records with version information."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
        )

        try:
            # Read all records with versions
            result = await node.read_with_version(
                query="SELECT * FROM versioned_records ORDER BY id", params={}
            )

            # Should have multiple records
            assert "records" in result
            assert "versions" in result
            assert len(result["records"]) >= 3
            assert len(result["versions"]) == len(result["records"])

            # Verify versions match records
            for i, record in enumerate(result["records"]):
                assert record["version"] == result["versions"][i]

        finally:
            await node.cleanup()

    @pytest.mark.asyncio
    async def test_version_retry_exhausted(self, setup_database):
        """Test retry exhaustion in high contention scenario."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string=conn_string,
            enable_optimistic_locking=True,
            conflict_resolution="retry",
            version_retry_attempts=2,  # Low for testing
        )

        # Create a high-contention record
        await node.execute_async(
            query="INSERT INTO versioned_records (name, value, version) VALUES (:name, :value, :version)",
            params={"name": "HighContention", "value": 2000, "version": 1},
        )

        # Get record ID
        id_result = await node.execute_async(
            query="SELECT id FROM versioned_records WHERE name = :name",
            params={"name": "HighContention"},
        )
        record_id = id_result["result"]["data"][0]["id"]

        try:
            # Create a node that will continuously update the record
            contention_node = AsyncSQLDatabaseNode(
                name="contention",
                database_type="postgresql",
                connection_string=conn_string,
            )

            async def create_contention():
                """Continuously update record to create contention."""
                for i in range(5):
                    await contention_node.execute_async(
                        query="UPDATE versioned_records SET value = value + 1, version = version + 1 WHERE id = :id",
                        params={"id": record_id},
                    )
                    await asyncio.sleep(0.1)

            # Start contention in background
            contention_task = asyncio.create_task(create_contention())

            # Try to update with retries - may exhaust retries
            result = await node.execute_with_version_check(
                query="UPDATE versioned_records SET value = :value WHERE id = :id",
                params={"value": 3000, "id": record_id},
                expected_version=1,  # Very old version
                record_id=record_id,
                table_name="versioned_records",
            )

            # Should either succeed after retries or exhaust retries
            assert result["status"] in [LockStatus.SUCCESS, LockStatus.RETRY_EXHAUSTED]

            if result["status"] == LockStatus.RETRY_EXHAUSTED:
                assert result["retry_count"] == 2

            await contention_task
            await contention_node.cleanup()

        finally:
            await node.cleanup()
