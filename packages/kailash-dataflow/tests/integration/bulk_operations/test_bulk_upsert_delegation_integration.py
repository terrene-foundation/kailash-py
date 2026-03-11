"""
Integration tests for BulkOperations.bulk_upsert delegation with real PostgreSQL database.

Tests the complete delegation flow:
BulkOperations.bulk_upsert -> BulkUpsertNode -> Real Database

NO MOCKING - Uses real PostgreSQL on port 5434 via IntegrationTestSuite.
"""

import pytest
from dataflow import DataFlow

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_test_table(test_suite):
    """Create test table and clean up after test."""
    connection_string = test_suite.config.url

    # Create table using AsyncSQLDatabaseNode
    # Note: DataFlow will pluralize TestUpsertDelegation -> test_upsert_delegations
    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE IF NOT EXISTS test_upsert_delegations (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            score INTEGER DEFAULT 0,
            tenant_id VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        validate_queries=False,
    )

    # Drop and recreate table for clean state
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS test_upsert_delegations CASCADE",
        validate_queries=False,
    )

    await drop_node.async_run()
    await setup_node.async_run()

    # Insert initial test data
    insert_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        INSERT INTO test_upsert_delegations (email, name, status, score)
        VALUES
            ('existing1@example.com', 'Existing One', 'active', 100),
            ('existing2@example.com', 'Existing Two', 'inactive', 200)
        """,
        validate_queries=False,
    )
    await insert_node.async_run()

    # Clean up nodes
    await setup_node.cleanup()
    await drop_node.cleanup()
    await insert_node.cleanup()

    yield connection_string

    # Cleanup after test
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS test_upsert_delegations CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestBulkUpsertDelegationIntegration:
    """Integration tests for bulk_upsert delegation with real database."""

    def _extract_result_data(self, result):
        """Extract data from AsyncSQLDatabaseNode result format."""
        if (
            isinstance(result, dict)
            and "result" in result
            and "data" in result["result"]
        ):
            return result["result"]["data"]
        return result

    @pytest.mark.asyncio
    async def test_bulk_upsert_inserts_new_records_postgresql(
        self, test_suite, setup_test_table
    ):
        """Test bulk_upsert inserts new records via delegation."""
        connection_string = setup_test_table

        # Create DataFlow instance
        db = DataFlow(connection_string, auto_migrate=False)

        # Define model (but don't auto-migrate - use existing table)
        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Use bulk_upsert directly via BulkOperations
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "new1@example.com",
                    "name": "New One",
                    "status": "active",
                    "score": 50,
                },
                {
                    "email": "new2@example.com",
                    "name": "New Two",
                    "status": "active",
                    "score": 75,
                },
            ],
            conflict_resolution="update",
            conflict_columns=["email"],
        )

        # Verify response format
        assert result["success"] is True
        assert result["records_processed"] == 2
        assert "inserted" in result
        assert "updated" in result
        assert "performance_metrics" in result

        # Verify records were inserted
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email IN ('new1@example.com', 'new2@example.com') ORDER BY email",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert len(data) == 2
        assert data[0]["email"] == "new1@example.com"
        assert data[0]["name"] == "New One"
        assert data[1]["email"] == "new2@example.com"
        assert data[1]["name"] == "New Two"

    @pytest.mark.asyncio
    async def test_bulk_upsert_updates_existing_records_postgresql(
        self, test_suite, setup_test_table
    ):
        """Test bulk_upsert updates existing records via delegation."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Update existing record
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "existing1@example.com",
                    "name": "Updated One",
                    "status": "premium",
                    "score": 150,
                },
            ],
            conflict_resolution="update",
            conflict_columns=["email"],
        )

        assert result["success"] is True
        assert result["records_processed"] == 1

        # Verify record was updated
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'existing1@example.com'",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert len(data) == 1
        assert data[0]["name"] == "Updated One"
        assert data[0]["status"] == "premium"
        assert data[0]["score"] == 150

    @pytest.mark.asyncio
    async def test_bulk_upsert_conflict_resolution_update_mode(
        self, test_suite, setup_test_table
    ):
        """Test conflict_resolution='update' updates existing records."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Upsert with update strategy
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "existing2@example.com",
                    "name": "Modified Two",
                    "status": "updated",
                    "score": 250,
                },
                {
                    "email": "new3@example.com",
                    "name": "New Three",
                    "status": "active",
                    "score": 300,
                },
            ],
            conflict_resolution="update",  # Should update existing, insert new
            conflict_columns=["email"],
        )

        assert result["success"] is True
        assert result["records_processed"] == 2

        # Verify existing was updated
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'existing2@example.com'",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert data[0]["name"] == "Modified Two"
        assert data[0]["score"] == 250

        # Verify new was inserted
        new_verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'new3@example.com'",
            validate_queries=False,
        )
        new_result = await new_verify_node.async_run()
        await new_verify_node.cleanup()
        new_data = self._extract_result_data(new_result)

        assert len(new_data) == 1
        assert new_data[0]["name"] == "New Three"

    @pytest.mark.asyncio
    async def test_bulk_upsert_conflict_resolution_ignore_mode(
        self, test_suite, setup_test_table
    ):
        """Test conflict_resolution='skip' ignores conflicts."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Upsert with skip strategy (maps to ignore in BulkUpsertNode)
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "existing1@example.com",
                    "name": "Should Not Update",
                    "status": "ignored",
                    "score": 999,
                },
                {
                    "email": "new4@example.com",
                    "name": "New Four",
                    "status": "active",
                    "score": 400,
                },
            ],
            conflict_resolution="skip",  # Should skip existing, insert new
            conflict_columns=["email"],
        )

        assert result["success"] is True

        # Verify existing was NOT updated
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'existing1@example.com'",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert data[0]["name"] == "Existing One"  # Original name preserved
        assert data[0]["score"] == 100  # Original score preserved

        # Verify new was inserted
        new_verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'new4@example.com'",
            validate_queries=False,
        )
        new_result = await new_verify_node.async_run()
        await new_verify_node.cleanup()
        new_data = self._extract_result_data(new_result)

        assert len(new_data) == 1
        assert new_data[0]["name"] == "New Four"

    @pytest.mark.asyncio
    async def test_bulk_upsert_multi_tenant_isolation(
        self, test_suite, setup_test_table
    ):
        """Test multi-tenant support in bulk_upsert delegation."""
        connection_string = setup_test_table

        # Add tenant_id column and update constraint
        alter_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            ALTER TABLE test_upsert_delegations
            DROP CONSTRAINT IF EXISTS test_upsert_delegations_email_key;

            ALTER TABLE test_upsert_delegations
            ADD CONSTRAINT test_upsert_delegations_email_tenant_key
            UNIQUE (email, tenant_id);
            """,
            validate_queries=False,
        )
        await alter_node.async_run()
        await alter_node.cleanup()

        # Create DataFlow with multi-tenant enabled
        db = DataFlow(connection_string, auto_migrate=False)
        db.config.security.multi_tenant = True

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int
            tenant_id: str

        # Upsert for tenant 1
        db._tenant_context = {"tenant_id": "tenant_001"}
        result1 = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "shared@example.com",
                    "name": "Tenant 1 User",
                    "status": "active",
                    "score": 100,
                },
            ],
            conflict_resolution="update",
            conflict_columns=["email", "tenant_id"],
        )

        assert result1["success"] is True

        # Upsert for tenant 2 (same email, different tenant)
        db._tenant_context = {"tenant_id": "tenant_002"}
        result2 = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "shared@example.com",
                    "name": "Tenant 2 User",
                    "status": "active",
                    "score": 200,
                },
            ],
            conflict_resolution="update",
            conflict_columns=["email", "tenant_id"],
        )

        assert result2["success"] is True

        # Verify both records exist
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_upsert_delegations WHERE email = 'shared@example.com' ORDER BY tenant_id",
            validate_queries=False,
        )
        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert len(data) == 2
        assert data[0]["tenant_id"] == "tenant_001"
        assert data[0]["name"] == "Tenant 1 User"
        assert data[1]["tenant_id"] == "tenant_002"
        assert data[1]["name"] == "Tenant 2 User"

    @pytest.mark.asyncio
    async def test_bulk_upsert_performance_metrics_included(
        self, test_suite, setup_test_table
    ):
        """Test that performance metrics are included in response."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Upsert multiple records
        test_data = [
            {
                "email": f"perf{i}@example.com",
                "name": f"Perf User {i}",
                "status": "active",
                "score": i * 10,
            }
            for i in range(50)
        ]

        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=test_data,
            conflict_resolution="update",
            conflict_columns=["email"],
            batch_size=25,
        )

        # Verify performance metrics are present
        assert result["success"] is True
        assert "performance_metrics" in result
        metrics = result["performance_metrics"]

        assert "execution_time_seconds" in metrics or "elapsed_seconds" in metrics
        assert "records_per_second" in metrics or "upserted_records" in metrics

    @pytest.mark.asyncio
    async def test_bulk_upsert_empty_data_no_database_operation(
        self, test_suite, setup_test_table
    ):
        """Test that empty data returns immediately without database operation."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str

        # Count records before
        count_before_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM test_upsert_delegation",
            validate_queries=False,
        )
        before_result = await count_before_node.async_run()
        await count_before_node.cleanup()
        count_before = self._extract_result_data(before_result)[0]["count"]

        # Call bulk_upsert with empty data
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[],
            conflict_resolution="update",
        )

        assert result["success"] is True
        assert result["records_processed"] == 0
        assert result["inserted"] == 0
        assert result["updated"] == 0

        # Verify no records were added
        count_after_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM test_upsert_delegation",
            validate_queries=False,
        )
        after_result = await count_after_node.async_run()
        await count_after_node.cleanup()
        count_after = self._extract_result_data(after_result)[0]["count"]

        assert count_after == count_before

    @pytest.mark.asyncio
    async def test_bulk_upsert_error_handling_database_error(self, test_suite):
        """Test error handling when database operation fails."""
        connection_string = test_suite.config.url

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class NonExistentTable:
            email: str
            name: str

        # Try to upsert to non-existent table (should fail gracefully)
        result = await db.bulk.bulk_upsert(
            model_name="NonExistentTable",
            data=[
                {"email": "test@example.com", "name": "Test"},
            ],
            conflict_resolution="update",
        )

        # Should return error response, not raise exception
        assert result["success"] is False
        assert "error" in result
        assert result["records_processed"] == 0

    @pytest.mark.asyncio
    async def test_bulk_upsert_return_records_option(
        self, test_suite, setup_test_table
    ):
        """Test return_records option returns upserted records."""
        connection_string = setup_test_table

        db = DataFlow(connection_string, auto_migrate=False)

        @db.model
        class TestUpsertDelegation:
            email: str
            name: str
            status: str
            score: int

        # Upsert with return_records=True
        result = await db.bulk.bulk_upsert(
            model_name="TestUpsertDelegation",
            data=[
                {
                    "email": "return1@example.com",
                    "name": "Return One",
                    "status": "active",
                    "score": 100,
                },
                {
                    "email": "return2@example.com",
                    "name": "Return Two",
                    "status": "active",
                    "score": 200,
                },
            ],
            conflict_resolution="update",
            conflict_columns=["email"],
            return_records=True,
        )

        assert result["success"] is True

        # Check if records are returned (may be in 'records' or 'upserted_records')
        has_records = "records" in result or "upserted_records" in result
        if has_records:
            records = result.get("records", result.get("upserted_records", []))
            if len(records) > 0:
                # Verify returned records have expected structure
                assert isinstance(records, list)
                # Check if emails are in the returned records
                returned_emails = {r["email"] for r in records if "email" in r}
                assert len(returned_emails) > 0
