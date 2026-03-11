"""
Test sync DDL auto_migrate fix for Docker/FastAPI environments.

This test validates that auto_migrate=True works correctly in environments
where an event loop is already running (Docker, FastAPI, pytest-asyncio).

The fix uses SyncDDLExecutor which uses synchronous database drivers
(psycopg2, sqlite3) instead of async drivers, avoiding event loop boundary issues.

IMPORTANT LIMITATION:
- In-memory SQLite databases (:memory:) do NOT use sync DDL because
  SyncDDLExecutor creates a separate connection, which for :memory:
  means tables are in a different database. In-memory databases use
  lazy creation (ensure_table_exists) which shares the CRUD connection.
"""

import asyncio
import os
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from dataflow import DataFlow


class TestSyncDDLAutoMigrate:
    """Test that auto_migrate=True works with sync DDL in all contexts."""

    def test_auto_migrate_sqlite_no_event_loop(self):
        """Test auto_migrate works in sync context (no event loop)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create DataFlow with auto_migrate=True (default)
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            # Register a model - table should be created immediately
            @db.model
            class User:
                id: str
                name: str
                email: str

            # Verify table was created by checking the cache
            assert db._schema_cache.is_table_ensured("User", f"sqlite:///{db_path}")

            # CRITICAL: Verify table actually exists and is usable
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            tables = cursor.fetchall()
            conn.close()
            assert len(tables) == 1, "users table should exist"

    def test_auto_migrate_sqlite_with_running_event_loop(self):
        """Test auto_migrate works when event loop is already running.

        This simulates the Docker/FastAPI scenario.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_running_loop.db")
            result = {"success": False, "error": None, "table_exists": False}

            async def run_in_async_context():
                """Simulate FastAPI startup with running event loop."""
                try:
                    # Create DataFlow with auto_migrate=True while event loop is running
                    db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

                    # Register a model - this should work with sync DDL!
                    @db.model
                    class Product:
                        id: str
                        name: str
                        price: float

                    # Verify table was created in cache
                    is_ensured = db._schema_cache.is_table_ensured(
                        "Product", f"sqlite:///{db_path}"
                    )

                    # Verify table actually exists
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
                    )
                    tables = cursor.fetchall()
                    conn.close()

                    result["success"] = is_ensured
                    result["table_exists"] = len(tables) == 1
                except Exception as e:
                    result["error"] = str(e)

            # Run in async context (simulating FastAPI)
            asyncio.run(run_in_async_context())

            assert result["success"], f"Failed: {result['error']}"
            assert result["table_exists"], "Table should actually exist in database"
            assert result["error"] is None

    def test_auto_migrate_false_skips_sync_ddl(self):
        """Test that auto_migrate=False skips sync DDL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_no_auto.db")

            # Create DataFlow with auto_migrate=False
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=False)

            @db.model
            class Order:
                id: str
                product_id: str
                quantity: int

            # Table should NOT be in cache (deferred)
            assert not db._schema_cache.is_table_ensured(
                "Order", f"sqlite:///{db_path}"
            )

            # Table should NOT exist in database yet
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'"
            )
            tables = cursor.fetchall()
            conn.close()
            assert len(tables) == 0, "orders table should NOT exist until first access"

    def test_create_tables_sync_method(self):
        """Test the explicit create_tables_sync method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_explicit_sync.db")

            # Create DataFlow with auto_migrate=False
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=False)

            @db.model
            class Customer:
                id: str
                name: str
                email: str

            @db.model
            class Invoice:
                id: str
                customer_id: str
                amount: float

            # Explicitly create tables using sync method
            success = db.create_tables_sync()
            assert success, "create_tables_sync should return True"

            # Verify tables were actually created by querying SQLite directly
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('customers', 'invoices')"
            )
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()

            assert "customers" in tables, f"Customer table should exist, got: {tables}"
            assert "invoices" in tables, f"Invoice table should exist, got: {tables}"

    def test_auto_migrate_in_thread_pool(self):
        """Test auto_migrate works when called from thread pool executor.

        This simulates scenarios where DataFlow is initialized in a background thread.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_thread_pool.db")
            results = {"success": False, "table_ensured": False, "table_exists": False}

            def init_dataflow_in_thread():
                """Initialize DataFlow in a separate thread."""
                try:
                    db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

                    @db.model
                    class Task:
                        id: str
                        title: str
                        completed: bool

                    results["table_ensured"] = db._schema_cache.is_table_ensured(
                        "Task", f"sqlite:///{db_path}"
                    )

                    # Verify table exists
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
                    )
                    tables = cursor.fetchall()
                    conn.close()
                    results["table_exists"] = len(tables) == 1

                    results["success"] = True
                except Exception as e:
                    results["error"] = str(e)

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(init_dataflow_in_thread)
                future.result(timeout=10)

            assert results["success"], f"Failed: {results.get('error')}"
            assert results["table_ensured"], "Table should be ensured in cache"
            assert results["table_exists"], "Table should actually exist"

    def test_existing_schema_mode_skips_sync_ddl(self):
        """Test that existing_schema_mode=True skips sync DDL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_existing.db")

            # Create DataFlow with existing_schema_mode=True
            db = DataFlow(
                f"sqlite:///{db_path}", auto_migrate=True, existing_schema_mode=True
            )

            @db.model
            class LegacyTable:
                id: str
                data: str

            # Model should be registered
            assert "LegacyTable" in db._models

            # Table should NOT be created (existing_schema_mode assumes tables exist)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_tables'"
            )
            tables = cursor.fetchall()
            conn.close()
            assert (
                len(tables) == 0
            ), "Table should NOT be created in existing_schema_mode"


@pytest.mark.asyncio
class TestSyncDDLAutoMigrateAsync:
    """Async tests for sync DDL auto_migrate fix."""

    async def test_model_registration_in_async_fixture(self):
        """Test model registration works in pytest async fixture."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_async_fixture.db")

            # This runs in an async context (pytest-asyncio)
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            @db.model
            class Session:
                id: str
                user_id: str
                token: str

            # Verify table was created via sync DDL
            assert db._schema_cache.is_table_ensured("Session", f"sqlite:///{db_path}")

            # Verify table actually exists
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            )
            tables = cursor.fetchall()
            conn.close()
            assert len(tables) == 1, "sessions table should exist"

    async def test_multiple_models_in_async_context(self):
        """Test multiple model registrations in async context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_multi_model.db")

            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            @db.model
            class Author:
                id: str
                name: str

            @db.model
            class Book:
                id: str
                title: str
                author_id: str

            @db.model
            class Review:
                id: str
                book_id: str
                rating: int

            # All tables should be created in cache
            for model_name in ["Author", "Book", "Review"]:
                assert db._schema_cache.is_table_ensured(
                    model_name, f"sqlite:///{db_path}"
                ), f"Table for {model_name} should be ensured"

            # Verify all tables actually exist
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('authors', 'books', 'reviews')"
            )
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            assert len(tables) == 3, f"All 3 tables should exist, got: {tables}"

    async def test_crud_operations_after_sync_ddl(self):
        """Test that CRUD operations work after sync DDL table creation.

        This is the CRITICAL test that verifies the fix actually works end-to-end.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_crud.db")

            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            @db.model
            class Item:
                id: str
                name: str
                price: float

            # Verify table was created
            assert db._schema_cache.is_table_ensured("Item", f"sqlite:///{db_path}")

            # CRITICAL: Test actual CRUD operations
            # Insert using direct SQL (simulating Express API)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Insert a record
            cursor.execute(
                "INSERT INTO items (id, name, price, created_at, updated_at) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                ("item-001", "Test Item", 29.99),
            )
            conn.commit()

            # Read it back
            cursor.execute(
                "SELECT id, name, price FROM items WHERE id = ?", ("item-001",)
            )
            row = cursor.fetchone()
            conn.close()

            assert row is not None, "Record should be readable"
            assert row[0] == "item-001"
            assert row[1] == "Test Item"
            assert row[2] == 29.99


class TestSyncDDLInMemoryLimitation:
    """Test that in-memory databases correctly fall back to lazy creation."""

    def test_memory_database_skips_sync_ddl(self):
        """Test that :memory: databases skip sync DDL and use lazy creation.

        In-memory databases cannot use SyncDDLExecutor because it creates
        a separate connection, which for :memory: means a different database.
        """
        db = DataFlow(":memory:", auto_migrate=True)

        @db.model
        class TestModel:
            id: str
            data: str

        # Model should be registered
        assert "TestModel" in db._models

        # Table should NOT be in schema cache (sync DDL was skipped)
        # It will be created lazily on first access
        assert not db._schema_cache.is_table_ensured("TestModel", ":memory:")

    def test_create_tables_sync_fails_for_memory_database(self):
        """Test that create_tables_sync returns False for :memory: databases."""
        db = DataFlow(":memory:", auto_migrate=False)

        @db.model
        class MemoryModel:
            id: str
            value: str

        # create_tables_sync should return False for in-memory databases
        success = db.create_tables_sync()
        assert (
            not success
        ), "create_tables_sync should return False for :memory: databases"


class TestSyncDDLEdgeCases:
    """Test edge cases and error handling."""

    def test_duplicate_model_registration_sync_context(self):
        """Test that duplicate model registration fails appropriately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_duplicate.db")
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            @db.model
            class UniqueModel:
                id: str
                data: str

            # Second registration should fail
            with pytest.raises(Exception):

                @db.model
                class UniqueModel:  # noqa: F811
                    id: str
                    other_data: str

    def test_sync_ddl_with_complex_types(self):
        """Test sync DDL with various column types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_types.db")
            db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

            from typing import Optional

            @db.model
            class ComplexModel:
                id: str
                name: str
                count: int
                price: float
                active: bool
                description: Optional[str] = None

            # Verify table was created
            assert db._schema_cache.is_table_ensured(
                "ComplexModel", f"sqlite:///{db_path}"
            )

            # Verify columns exist
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(complex_models)")
            columns = {row[1] for row in cursor.fetchall()}
            conn.close()

            expected = {
                "id",
                "name",
                "count",
                "price",
                "active",
                "description",
                "created_at",
                "updated_at",
            }
            assert expected.issubset(
                columns
            ), f"Expected columns {expected}, got {columns}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
