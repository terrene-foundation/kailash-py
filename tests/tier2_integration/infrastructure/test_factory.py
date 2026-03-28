# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for StoreFactory with auto-detection from KAILASH_DATABASE_URL.

Tests cover:
- Level 0 (no URL): Returns Level 0 defaults (SQLite/in-memory/disk)
- Level 1+ (URL set): Returns DB-backed stores sharing a ConnectionManager
- Schema versioning via kailash_meta table
- Singleton pattern and reset behavior
- Idempotent initialization and resource cleanup
- Lazy imports: factory module must not import SQLAlchemy at module level
"""

from __future__ import annotations

import logging

import pytest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def clean_factory():
    """Ensure StoreFactory singleton is reset before and after each test."""
    from kailash.infrastructure.factory import StoreFactory

    StoreFactory.reset()
    yield StoreFactory
    StoreFactory.reset()


@pytest.fixture
async def level1_factory():
    """Provide an initialized Level 1 StoreFactory with in-memory SQLite."""
    from kailash.infrastructure.factory import StoreFactory

    StoreFactory.reset()
    factory = StoreFactory(database_url="sqlite:///:memory:")
    await factory.initialize()
    yield factory
    await factory.close()
    StoreFactory.reset()


# ---------------------------------------------------------------------------
# Level 0 (no database URL configured)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestLevel0NoUrl:
    async def test_level0_no_url(self, clean_factory):
        """StoreFactory with no URL should report is_level0 = True."""
        factory = clean_factory(database_url=None)
        assert factory.is_level0 is True
        assert factory.database_url is None

    async def test_level0_returns_sqlite_event_store(self, clean_factory):
        """Level 0 event store should be SqliteEventStoreBackend."""
        from kailash.middleware.gateway.event_store_sqlite import (
            SqliteEventStoreBackend,
        )

        factory = clean_factory(database_url=None)
        store = await factory.create_event_store()
        assert isinstance(store, SqliteEventStoreBackend)
        await factory.close()

    async def test_level0_returns_disk_checkpoint_store(self, clean_factory):
        """Level 0 checkpoint store should be DiskStorage."""
        from kailash.middleware.gateway.checkpoint_manager import DiskStorage

        factory = clean_factory(database_url=None)
        store = await factory.create_checkpoint_store()
        assert isinstance(store, DiskStorage)
        await factory.close()

    async def test_level0_returns_persistent_dlq(self, clean_factory):
        """Level 0 DLQ should be PersistentDLQ (SQLite file-based)."""
        from kailash.workflow.dlq import PersistentDLQ

        factory = clean_factory(database_url=None)
        store = await factory.create_dlq()
        assert isinstance(store, PersistentDLQ)
        await factory.close()

    async def test_level0_returns_in_memory_execution_store(self, clean_factory):
        """Level 0 execution store should be InMemoryExecutionStore."""
        from kailash.infrastructure.execution_store import InMemoryExecutionStore

        factory = clean_factory(database_url=None)
        store = await factory.create_execution_store()
        assert isinstance(store, InMemoryExecutionStore)
        await factory.close()

    async def test_level0_returns_none_for_idempotency(self, clean_factory):
        """Level 0 has no persistent idempotency -- returns None."""
        factory = clean_factory(database_url=None)
        store = await factory.create_idempotency_store()
        assert store is None
        await factory.close()


# ---------------------------------------------------------------------------
# Level 1+ (database URL configured)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestLevel1SqliteUrl:
    async def test_level1_is_not_level0(self, level1_factory):
        """StoreFactory with a URL should report is_level0 = False."""
        assert level1_factory.is_level0 is False
        assert level1_factory.database_url == "sqlite:///:memory:"

    async def test_level1_event_store_is_db_backed(self, level1_factory):
        """Level 1 event store should be DBEventStoreBackend."""
        from kailash.infrastructure.event_store import DBEventStoreBackend

        store = await level1_factory.create_event_store()
        assert isinstance(store, DBEventStoreBackend)

    async def test_level1_checkpoint_is_db_backed(self, level1_factory):
        """Level 1 checkpoint store should be DBCheckpointStore."""
        from kailash.infrastructure.checkpoint_store import DBCheckpointStore

        store = await level1_factory.create_checkpoint_store()
        assert isinstance(store, DBCheckpointStore)

    async def test_level1_dlq_is_db_backed(self, level1_factory):
        """Level 1 DLQ should be DBDeadLetterQueue."""
        from kailash.infrastructure.dlq import DBDeadLetterQueue

        store = await level1_factory.create_dlq()
        assert isinstance(store, DBDeadLetterQueue)

    async def test_level1_execution_is_db_backed(self, level1_factory):
        """Level 1 execution store should be DBExecutionStore."""
        from kailash.infrastructure.execution_store import DBExecutionStore

        store = await level1_factory.create_execution_store()
        assert isinstance(store, DBExecutionStore)

    async def test_level1_idempotency_is_db_backed(self, level1_factory):
        """Level 1 idempotency store should be DBIdempotencyStore."""
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        store = await level1_factory.create_idempotency_store()
        assert isinstance(store, DBIdempotencyStore)


# ---------------------------------------------------------------------------
# Shared ConnectionManager
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSharedConnectionManager:
    async def test_shared_connection_manager(self, level1_factory):
        """All DB stores created by the factory must share the same ConnectionManager."""
        event_store = await level1_factory.create_event_store()
        checkpoint_store = await level1_factory.create_checkpoint_store()
        dlq = await level1_factory.create_dlq()
        execution_store = await level1_factory.create_execution_store()
        idempotency_store = await level1_factory.create_idempotency_store()

        # All stores should reference the same underlying ConnectionManager
        conn = level1_factory._conn
        assert conn is not None, "ConnectionManager must be set after initialization"
        assert event_store._conn is conn
        assert checkpoint_store._conn is conn
        assert dlq._conn is conn
        assert execution_store._conn is conn
        assert idempotency_store._conn is conn


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSchemaVersioning:
    async def test_schema_version_stamped(self, level1_factory):
        """After initialization, kailash_meta table should have schema_version=1."""
        from kailash.infrastructure.factory import SCHEMA_VERSION

        conn = level1_factory._conn
        row = await conn.fetchone(
            "SELECT value FROM kailash_meta WHERE key = ?", "schema_version"
        )
        assert row is not None, "kailash_meta must contain a schema_version row"
        assert int(row["value"]) == SCHEMA_VERSION

    async def test_schema_too_new_raises(self, clean_factory):
        """If the DB schema version is newer than code, a RuntimeError must be raised."""
        from kailash.db.connection import ConnectionManager

        # Set up a database with a schema version higher than the code knows
        conn = ConnectionManager("sqlite:///:memory:")
        await conn.initialize()
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS kailash_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        await conn.execute(
            "INSERT INTO kailash_meta (key, value) VALUES (?, ?)",
            "schema_version",
            "999",
        )

        factory = clean_factory(database_url="sqlite:///:memory:")
        # Replace the internal connection to use our pre-seeded DB
        factory._conn = conn
        factory._url = "sqlite:///:memory:"

        with pytest.raises(RuntimeError, match="newer than code version"):
            await factory._stamp_schema_version()

        await conn.close()


# ---------------------------------------------------------------------------
# Singleton pattern
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSingletonPattern:
    async def test_singleton_pattern(self, clean_factory):
        """get_default() should return the same instance on repeated calls."""
        a = clean_factory.get_default()
        b = clean_factory.get_default()
        assert a is b

    async def test_reset_clears_singleton(self, clean_factory):
        """reset() should allow a new instance to be created."""
        a = clean_factory.get_default()
        clean_factory.reset()
        b = clean_factory.get_default()
        assert a is not b


# ---------------------------------------------------------------------------
# Initialization idempotency and lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestInitializationAndLifecycle:
    async def test_double_initialize_is_idempotent(self, clean_factory):
        """Calling initialize() twice should not raise or create duplicate tables."""
        factory = clean_factory(database_url="sqlite:///:memory:")
        await factory.initialize()
        await factory.initialize()  # Should be a safe no-op
        # Verify tables still work
        store = await factory.create_event_store()
        from kailash.infrastructure.event_store import DBEventStoreBackend

        assert isinstance(store, DBEventStoreBackend)
        await factory.close()

    async def test_close_releases_resources(self, clean_factory):
        """After close(), the ConnectionManager should be None."""
        factory = clean_factory(database_url="sqlite:///:memory:")
        await factory.initialize()
        assert factory._conn is not None
        await factory.close()
        assert factory._conn is None
        assert factory._initialized is False

    async def test_close_on_level0_is_safe(self, clean_factory):
        """Calling close() on a Level 0 factory should not raise."""
        factory = clean_factory(database_url=None)
        await factory.initialize()
        await factory.close()  # Should be a no-op without errors

    async def test_close_twice_is_safe(self, clean_factory):
        """Calling close() twice should not raise."""
        factory = clean_factory(database_url="sqlite:///:memory:")
        await factory.initialize()
        await factory.close()
        await factory.close()  # Should be safe


# ---------------------------------------------------------------------------
# Lazy import safety
# ---------------------------------------------------------------------------
class TestLazyImports:
    def test_factory_module_does_not_import_sqlalchemy(self):
        """The factory module must not import SQLAlchemy or optional deps at module level."""
        import importlib
        import sys

        # Remove the module from cache to force a fresh import
        module_name = "kailash.infrastructure.factory"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Track which modules are imported during the factory import
        before = set(sys.modules.keys())
        importlib.import_module(module_name)
        after = set(sys.modules.keys())

        newly_imported = after - before
        # These are optional heavy deps that must NOT be imported at module level
        forbidden = {"sqlalchemy", "asyncpg", "aiomysql", "aiosqlite"}
        violations = newly_imported & forbidden
        assert not violations, (
            f"Factory module must not import {violations} at module level. "
            f"Use lazy imports inside factory methods instead."
        )
