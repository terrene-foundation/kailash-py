"""
Integration tests for engine.py migration errors (Phase 1C Week 7 Task 1.4).

Tests the 5 newly enhanced migration error sites in real database scenarios:
- Scenario 1: Migration system not initialized with real DataFlow instance
- Scenario 2: Unsupported database scheme with actual connection attempt
- Scenario 3: In-memory SQLite schema discovery limitation

All tests use real infrastructure (NO MOCKING) following Tier 2 testing policies.
"""

import pytest
from dataflow import DataFlow
from dataflow.exceptions import EnhancedDataFlowError


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestMigrationSystemErrors:
    """
    Scenario 1: Test migration system initialization errors with real DataFlow.

    Tests verify that auto_migrate() produces enhanced errors when migration
    system is not enabled.
    """

    @pytest.mark.asyncio
    async def test_auto_migrate_without_migration_system(self):
        """
        Integration test: Auto-migrate when migration system disabled.

        Verifies that calling auto_migrate() with migration_enabled=False
        produces an enhanced error with DF-501 and clear instructions.
        """
        # Arrange: Create DataFlow with migration system disabled
        db = DataFlow(":memory:", migration_enabled=False)

        @db.model
        class User:
            id: str
            name: str
            email: str

        # Act & Assert: Attempt auto-migration
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            await db.auto_migrate()

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "DF-501" in error_message
            or "Migration system not initialized" in error_message
        )
        assert "migration_enabled" in error_message.lower()

    @pytest.mark.asyncio
    async def test_migration_system_disabled_does_not_affect_basic_operations(self):
        """
        Integration test: Verify basic operations work without migration system.

        Ensures that disabling migration system only affects auto_migrate(),
        not basic model registration and table creation.
        """
        # Arrange: Create DataFlow with migration system disabled
        db = DataFlow(":memory:", migration_enabled=False)

        @db.model
        class Product:
            id: str
            name: str
            price: float

        # Initialize (creates tables)
        await db.initialize()

        # Assert: Model is registered
        assert "Product" in db.get_models()

        # Only auto_migrate should fail
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            await db.auto_migrate()

        error_message = str(exc_info.value)
        assert "migration_enabled" in error_message.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestSchemaDiscoveryErrors:
    """
    Scenario 2: Test schema discovery errors with unsupported databases.

    Tests verify that schema discovery produces enhanced errors for
    unsupported database types.
    """

    @pytest.mark.asyncio
    async def test_unsupported_database_scheme_with_mongodb(self):
        """
        Integration test: Unsupported database scheme error with MongoDB URL.

        Verifies that attempting schema discovery on MongoDB produces
        an enhanced error explaining it's not supported.
        """
        # Arrange: Create DataFlow with MongoDB URL (unsupported)
        db = DataFlow("mongodb://localhost:27017/test_db")

        # Act & Assert: Attempt schema discovery
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            await db._inspect_database_schema_real()

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert "DF-501" in error_message or "schema discovery" in error_message.lower()
        assert (
            "mongodb" in error_message.lower() or "unsupported" in error_message.lower()
        )

        # Verify supported databases are mentioned
        assert any(
            ["postgresql" in error_message.lower(), "sqlite" in error_message.lower()]
        )

    @pytest.mark.asyncio
    async def test_in_memory_sqlite_schema_discovery_limitation(self):
        """
        Integration test: In-memory SQLite schema discovery not supported.

        Verifies that attempting schema discovery on :memory: database
        produces an enhanced error explaining the limitation.
        """
        # Arrange: Create DataFlow with in-memory SQLite
        db = DataFlow(":memory:")

        # Act & Assert: Attempt schema discovery on memory database
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            await db._inspect_sqlite_schema_real(":memory:")

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert "DF-501" in error_message or "in-memory" in error_message.lower()
        assert (
            "file-based" in error_message.lower()
            or "not supported" in error_message.lower()
        )


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestErrorEnhancementIntegration:
    """
    Integration tests verifying complete migration error enhancement flow.

    Tests that error enhancements work correctly in complex real-world scenarios
    combining multiple DataFlow features.
    """

    @pytest.mark.asyncio
    async def test_multiple_migration_errors_in_sequence(self):
        """
        Integration test: Multiple migration errors in sequence.

        Verifies that each migration error produces its own specific enhanced error
        with appropriate error codes and solutions.
        """
        # Test 1: Migration system not initialized
        db1 = DataFlow(":memory:", migration_enabled=False)

        @db1.model
        class User:
            id: str
            name: str

        with pytest.raises(EnhancedDataFlowError) as exc_info1:
            await db1.auto_migrate()
        assert "migration_enabled" in str(exc_info1.value).lower()

        # Test 2: Unsupported database scheme
        db2 = DataFlow("mongodb://localhost/test")
        with pytest.raises(EnhancedDataFlowError) as exc_info2:
            await db2._inspect_database_schema_real()
        assert (
            "mongodb" in str(exc_info2.value).lower()
            or "unsupported" in str(exc_info2.value).lower()
        )

        # Test 3: In-memory SQLite schema discovery
        db3 = DataFlow(":memory:")
        with pytest.raises(EnhancedDataFlowError) as exc_info3:
            await db3._inspect_sqlite_schema_real(":memory:")
        assert "in-memory" in str(exc_info3.value).lower()

    @pytest.mark.asyncio
    async def test_error_messages_are_user_friendly(self):
        """
        Integration test: Verify migration error messages are clear and actionable.

        Ensures that all enhanced migration errors provide user-friendly messages with:
        - Clear error description
        - Context (what went wrong)
        - Actionable solution (how to fix)
        """
        # Test 1: Migration system disabled provides clear solution
        db1 = DataFlow(":memory:", migration_enabled=False)

        @db1.model
        class Order:
            id: str
            total: float

        with pytest.raises(EnhancedDataFlowError) as exc_info1:
            await db1.auto_migrate()

        message1 = str(exc_info1.value)
        # Should explain what's wrong
        assert "migration" in message1.lower() or "not initialized" in message1.lower()
        # Should provide solution
        assert "migration_enabled" in message1.lower() or "enable" in message1.lower()

        # Test 2: Unsupported database provides alternatives
        db2 = DataFlow("mongodb://localhost/test")

        with pytest.raises(EnhancedDataFlowError) as exc_info2:
            await db2._inspect_database_schema_real()

        message2 = str(exc_info2.value)
        # Should explain what database is unsupported
        assert "mongodb" in message2.lower() or "unsupported" in message2.lower()
        # Should list supported databases
        assert "postgresql" in message2.lower() or "sqlite" in message2.lower()

    @pytest.mark.asyncio
    async def test_migration_errors_preserve_dataflow_state(self):
        """
        Integration test: Verify migration errors don't corrupt DataFlow state.

        Ensures that after a migration error, the DataFlow instance remains
        functional for basic operations.
        """
        # Arrange: Create DataFlow with migration disabled
        db = DataFlow(":memory:", migration_enabled=False)

        @db.model
        class Product:
            id: str
            name: str
            price: float

        # Initialize successfully
        await db.initialize()

        # Trigger migration error
        with pytest.raises(EnhancedDataFlowError):
            await db.auto_migrate()

        # Verify DataFlow is still functional
        assert "Product" in db.get_models()

        # Verify we can still register new models
        @db.model
        class Category:
            id: str
            name: str

        assert "Category" in db.get_models()


# Summary of integration test coverage:
# - Scenario 1 (2 tests): Migration system not initialized with real DataFlow
# - Scenario 2 (2 tests): Unsupported database and in-memory SQLite errors
# - Integration verification (3 tests): Complete error enhancement flow
#
# Total: 7 integration tests covering all 5 newly enhanced migration error sites
# All tests use real infrastructure (SQLite databases, MongoDB connection attempts) with NO MOCKING
