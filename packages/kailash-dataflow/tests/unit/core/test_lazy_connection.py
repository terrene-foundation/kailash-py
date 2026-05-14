"""
Tests for Issue #171: Deferred DB connection from __init__() to first query.

DataFlow.__init__() should store config only — no pool probe, no migration,
no database connection. The connection happens lazily on first query.
"""

import pytest


class TestLazyConnection:
    """Verify DataFlow defers database connection until first use."""

    def test_init_does_not_connect(self):
        """DataFlow.__init__() should not attempt any database connection.

        This is the core fix for #171: importing DataFlow models should
        work without a live database.
        """
        from dataflow import DataFlow

        # Use a URL that would fail if actually connected to
        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,  # Skip pool entirely for this test
        ) as db:
            # Verify we're in the not-yet-connected state
            assert db._connected is False
            assert db._pending_table_creations == []

            # Verify models dict is initialized (metadata structures ready)
            assert db._models == {}
            assert db._registered_models == {}

    def test_model_decorator_without_connection(self):
        """@db.model should register schema without connecting to database."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:

            @db.model
            class User:
                id: str
                name: str
                email: str

            # Model registered in metadata
            assert "User" in db._models
            assert "User" in db._registered_models

            # But no connection happened
            assert db._connected is False

            # Table creation deferred
            assert "User" in db._pending_table_creations

            # Nodes generated (metadata-only, no DB)
            assert any("User" in key for key in db._nodes)

    def test_multiple_models_without_connection(self):
        """Multiple @db.model decorators should all work without connecting."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:

            @db.model
            class Organization:
                id: str
                name: str

            @db.model
            class User:
                id: str
                name: str
                org_id: str

            @db.model
            class Project:
                id: str
                title: str
                owner_id: str

            assert db._connected is False
            assert len(db._models) == 3
            assert len(db._pending_table_creations) == 3

    def test_ensure_connected_idempotent(self, tmp_path):
        """_ensure_connected() should be idempotent — safe to call multiple times."""
        from dataflow import DataFlow

        # Use SQLite which doesn't require a running server.
        # tmp_path ensures the file is cleaned up by pytest automatically.
        db_path = tmp_path / "test_lazy.db"
        with DataFlow(f"sqlite:///{db_path}") as db:

            @db.model
            class Item:
                id: str
                name: str

            assert db._connected is False

            # First call connects
            db._ensure_connected()
            assert db._connected is True
            assert db._pending_table_creations == []  # Cleared after processing

            # Second call is a no-op
            db._ensure_connected()
            assert db._connected is True

    def test_close_without_connecting(self):
        """close() should work even if never connected."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:

            @db.model
            class User:
                id: str
                name: str

            # Never connected
            assert db._connected is False

        # __exit__ called close() on a never-connected instance and did not raise.

    def test_schema_cache_initialized_without_connection(self):
        """Schema cache (in-memory) should be ready without DB connection."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:
            # Schema cache is initialized (it's pure in-memory, no DB needed)
            assert db._schema_cache is not None
            assert db._connected is False

    def test_config_accessible_without_connection(self):
        """Config properties should be accessible without triggering connection."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:
            # These should all work without connecting
            assert db.config is not None
            assert db.config.database is not None
            assert db._auto_migrate is True
            assert db.runtime is not None
            assert db._connected is False

    def test_pool_stats_without_connection(self):
        """pool_stats() should return zeros without requiring connection."""
        from dataflow import DataFlow

        with DataFlow(
            "postgresql://nonexistent:password@192.0.2.1:5432/fake_db",
            enable_connection_pooling=False,
        ) as db:
            # pool_stats should work without connection (returns zeros)
            stats = db.pool_stats()
            assert stats is not None
            assert db._connected is False
