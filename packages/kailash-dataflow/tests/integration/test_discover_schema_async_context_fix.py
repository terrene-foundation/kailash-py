"""
Verification tests for: DATAFLOW-ASYNC-MODEL-DECORATOR-001 fix

This test verifies that the fix for discover_schema() async context issue works correctly.

After the fix:
- @db.model should work in async contexts (pytest async fixtures, FastAPI lifespan, etc.)
- Relationship detection is deferred to initialize()
- All adapters should work consistently

The fix:
- @db.model no longer calls _auto_detect_relationships() directly
- Instead, models are marked for deferred relationship detection
- initialize() processes deferred relationship detection asynchronously
"""

import os

import pytest

from dataflow import DataFlow

# Database URLs for testing
POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL",
    "mysql://test_user:test_password@localhost:3306/kailash_test",
)
MONGODB_URL = os.getenv(
    "TEST_MONGODB_URL",
    "mongodb://localhost:27017/kailash_test",
)
SQLITE_URL = ":memory:"
SQLITE_FILE_URL = "sqlite:///test_async_context_fix.db"


class TestPostgreSQLAsyncContextFix:
    """Test PostgreSQL adapter works in async context after fix."""

    @pytest.mark.asyncio
    async def test_postgresql_model_in_async_context_succeeds(self):
        """
        FIX VERIFICATION: PostgreSQL @db.model now works in async context.

        After the fix, model registration defers relationship detection
        until initialize() is called.
        """
        db = DataFlow(
            database_url=POSTGRES_URL,
            instance_id="test_postgres_async_fix",
            test_mode=True,
            auto_migrate=False,
        )

        # This should now work - no RuntimeError!
        @db.model
        class PostgresModel:
            id: str
            name: str

        # Verify model was registered
        assert "PostgresModel" in db._models
        assert db._models["PostgresModel"]["class"] == PostgresModel

        # Verify model is marked for deferred relationship detection
        assert "PostgresModel" in db._pending_relationship_detection


class TestMySQLAsyncContextFix:
    """Test MySQL adapter works in async context after fix."""

    @pytest.mark.asyncio
    async def test_mysql_model_in_async_context_succeeds(self):
        """
        FIX VERIFICATION: MySQL @db.model now works in async context.
        """
        db = DataFlow(
            database_url=MYSQL_URL,
            instance_id="test_mysql_async_fix",
            test_mode=True,
            auto_migrate=False,
        )

        # This should now work - no RuntimeError!
        @db.model
        class MySQLModel:
            id: str
            name: str

        # Verify model was registered
        assert "MySQLModel" in db._models
        assert "MySQLModel" in db._pending_relationship_detection


class TestMongoDBAsyncContextFix:
    """Test MongoDB adapter works in async context after fix."""

    @pytest.mark.asyncio
    async def test_mongodb_model_in_async_context_succeeds(self):
        """
        FIX VERIFICATION: MongoDB @db.model now works in async context.
        """
        db = DataFlow(
            database_url=MONGODB_URL,
            instance_id="test_mongodb_async_fix",
            test_mode=True,
            auto_migrate=False,
        )

        # This should now work - no RuntimeError!
        @db.model
        class MongoModel:
            id: str
            name: str

        # Verify model was registered
        assert "MongoModel" in db._models
        assert "MongoModel" in db._pending_relationship_detection


class TestSQLiteAsyncContextFix:
    """Test SQLite adapters continue to work in async context."""

    @pytest.mark.asyncio
    async def test_sqlite_memory_model_in_async_context_succeeds(self):
        """
        SQLite in-memory continues to work in async context.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_sqlite_memory_async_fix",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class SQLiteMemoryModel:
            id: str
            name: str

        # Verify model was registered
        assert "SQLiteMemoryModel" in db._models
        assert "SQLiteMemoryModel" in db._pending_relationship_detection

    @pytest.mark.asyncio
    async def test_sqlite_file_model_in_async_context_succeeds(self):
        """
        SQLite file-based continues to work in async context.
        """
        db = DataFlow(
            database_url=SQLITE_FILE_URL,
            instance_id="test_sqlite_file_async_fix",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class SQLiteFileModel:
            id: str
            name: str

        # Verify model was registered
        assert "SQLiteFileModel" in db._models


class TestSessionFixtureScenarioFixed:
    """Test the exact scenario from the bug report - now works!"""

    @pytest.mark.asyncio
    async def test_session_fixture_postgresql_succeeds(self):
        """
        FIX VERIFICATION: Session fixture scenario now works.

        This simulates the pattern from the bug report:
            @pytest.fixture(scope="session")
            async def session_dataflow(session_database_url):
                db = DataFlow(database_url=session_database_url, ...)

                @db.model  # ✅ NOW WORKS!
                class Session:
                    session_id: str
                    user_id: str
        """
        db = DataFlow(
            database_url=POSTGRES_URL,
            instance_id="test_session_fixture_fix",
            test_mode=True,
            auto_migrate=False,
        )

        # This is what happens in a session-scoped async fixture
        # NOW IT WORKS!
        @db.model
        class Session:
            session_id: str
            user_id: str
            token: str

        # Verify model was registered successfully
        assert "Session" in db._models
        assert "Session" in db._pending_relationship_detection


class TestSyncFunctionFromAsyncContextFixed:
    """Test that defining in sync function from async context now works."""

    @pytest.mark.asyncio
    async def test_sync_function_from_async_context_succeeds(self):
        """
        FIX VERIFICATION: Sync function from async context now works.

        Even defining model in a sync function called from async context works now.
        """

        def define_model_sync():
            """Sync function that defines a model."""
            db = DataFlow(
                database_url=POSTGRES_URL,
                instance_id="test_sync_from_async_fix",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class SyncDefinedModel:
                id: str
                name: str

            return db

        # Calling sync function from async context now works!
        db = define_model_sync()

        # Verify model was registered
        assert "SyncDefinedModel" in db._models
        assert "SyncDefinedModel" in db._pending_relationship_detection


class TestAllAdaptersWorkInAsyncContext:
    """Summary test showing all adapters now work in async context."""

    @pytest.mark.asyncio
    async def test_all_adapters_work_in_async_context(self):
        """
        FIX VERIFICATION: All adapters work in async context.

        Before fix:
        - PostgreSQL: ❌ Failed with RuntimeError
        - MySQL: ❌ Failed with RuntimeError
        - MongoDB: ❌ Failed with RuntimeError
        - SQLite: ✅ Worked (skipped relationship detection)

        After fix:
        - PostgreSQL: ✅ Works (deferred relationship detection)
        - MySQL: ✅ Works (deferred relationship detection)
        - MongoDB: ✅ Works (deferred relationship detection)
        - SQLite: ✅ Works (deferred relationship detection)
        """
        working_adapters = []

        # Test PostgreSQL
        try:
            db = DataFlow(
                POSTGRES_URL,
                instance_id="matrix_pg_fix",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class PgTest:
                id: str

            assert "PgTest" in db._models
            working_adapters.append("postgresql")
        except RuntimeError as e:
            if "discover_schema()" in str(e):
                pytest.fail(f"PostgreSQL still fails: {e}")
            raise

        # Test MySQL
        try:
            db = DataFlow(
                MYSQL_URL,
                instance_id="matrix_mysql_fix",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class MysqlTest:
                id: str

            assert "MysqlTest" in db._models
            working_adapters.append("mysql")
        except RuntimeError as e:
            if "discover_schema()" in str(e):
                pytest.fail(f"MySQL still fails: {e}")
            raise

        # Test MongoDB
        try:
            db = DataFlow(
                MONGODB_URL,
                instance_id="matrix_mongo_fix",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class MongoTest:
                id: str

            assert "MongoTest" in db._models
            working_adapters.append("mongodb")
        except RuntimeError as e:
            if "discover_schema()" in str(e):
                pytest.fail(f"MongoDB still fails: {e}")
            raise

        # Test SQLite
        try:
            db = DataFlow(
                SQLITE_URL,
                instance_id="matrix_sqlite_fix",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class SqliteTest:
                id: str

            assert "SqliteTest" in db._models
            working_adapters.append("sqlite")
        except RuntimeError as e:
            pytest.fail(f"SQLite failed: {e}")

        # All adapters should work now
        assert "postgresql" in working_adapters
        assert "mysql" in working_adapters
        assert "mongodb" in working_adapters
        assert "sqlite" in working_adapters

        # Print summary for visibility
        print("\n" + "=" * 60)
        print("ASYNC CONTEXT FIX - ALL ADAPTERS WORK")
        print("=" * 60)
        print(f"WORKING ADAPTERS: {', '.join(working_adapters)}")
        print("=" * 60)


class TestDeferredRelationshipDetectionProcessing:
    """Test that deferred relationship detection is processed during initialize()."""

    @pytest.mark.asyncio
    async def test_pending_models_marked_during_registration(self):
        """
        Test that models are marked for deferred relationship detection during registration.
        """
        db = DataFlow(
            database_url=SQLITE_URL,  # Use SQLite for simplicity
            instance_id="test_deferred_processing",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class TestModel:
            id: str
            name: str

        # After registration: model should be in pending set
        assert "TestModel" in db._pending_relationship_detection

        # Model should also be fully registered in _models
        assert "TestModel" in db._models
        assert db._models["TestModel"]["class"] == TestModel
        assert "id" in db._model_fields["TestModel"]
        assert "name" in db._model_fields["TestModel"]

    @pytest.mark.asyncio
    async def test_process_pending_relationship_detection_clears_set(self):
        """
        Test that _process_pending_relationship_detection clears the pending set.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_process_pending",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class TestModel2:
            id: str
            name: str

        # Before processing: model is in pending set
        assert "TestModel2" in db._pending_relationship_detection

        # Directly call the processing function (bypassing initialize complications)
        await db._process_pending_relationship_detection()

        # After processing: pending set should be cleared
        assert "TestModel2" not in db._pending_relationship_detection
        assert len(db._pending_relationship_detection) == 0
