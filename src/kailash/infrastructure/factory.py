# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Store factory with auto-detection from KAILASH_DATABASE_URL.

Provides a single entry point for creating infrastructure store backends.
The factory inspects ``KAILASH_DATABASE_URL`` (via :func:`resolve_database_url`)
and returns the appropriate backend tier:

* **Level 0** (no env var): Returns Level 0 defaults -- SQLite file-based event
  store, disk-based checkpoints, file-based DLQ, in-memory execution store,
  and no idempotency store.
* **Level 1+** (env var set): Returns dialect-portable DB backends that share
  a single :class:`~kailash.db.connection.ConnectionManager`.

All Level 0 imports are **lazy** (inside factory methods) so that the factory
module itself has no dependency on ``aiosqlite`` or any optional driver.

Schema versioning is enforced via a ``kailash_meta`` table that stores the
current schema version.  If the database schema is newer than the running code,
initialization fails fast with a clear error message.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from kailash.db.registry import resolve_database_url

logger = logging.getLogger(__name__)

__all__ = [
    "SCHEMA_VERSION",
    "StoreFactory",
]

# Current schema version for the infrastructure tables.
# Bump this when adding new tables or altering existing schemas.
SCHEMA_VERSION = 1


class StoreFactory:
    """Creates and manages store backends based on KAILASH_DATABASE_URL.

    Level 0 (no env var): Returns Level 0 defaults (SQLite/in-memory).
    Level 1+ (env var set): Returns dialect-portable DB backends sharing
    a single ConnectionManager.

    Parameters
    ----------
    database_url:
        Explicit database URL.  If ``None``, the factory auto-detects from
        ``KAILASH_DATABASE_URL`` / ``DATABASE_URL`` environment variables.
    """

    _instance: Optional[StoreFactory] = None

    def __init__(self, database_url: Optional[str] = None) -> None:
        self._url = database_url or resolve_database_url()
        # Lazy import: ConnectionManager is only created when needed
        self._conn: Any = None  # Optional[ConnectionManager]
        self._initialized = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------
    @classmethod
    def get_default(cls) -> StoreFactory:
        """Get or create the default factory (singleton).

        Returns the same instance on repeated calls.  Use :meth:`reset`
        to discard the singleton (primarily for testing).
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing).

        The caller is responsible for calling :meth:`close` on the old
        instance before reset if it was initialized.
        """
        cls._instance = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def is_level0(self) -> bool:
        """``True`` if no database URL is configured (Level 0 defaults)."""
        return self._url is None

    @property
    def database_url(self) -> Optional[str]:
        """The resolved database URL, or ``None`` for Level 0."""
        return self._url

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Create the ConnectionManager and initialize all infrastructure tables.

        For Level 0 this is a no-op.  For Level 1+ this creates the
        connection pool, creates all store tables, and stamps the schema
        version in ``kailash_meta``.

        Safe to call multiple times (idempotent).
        """
        if self._initialized:
            return

        if self._url is None:
            # Level 0: no DB backend needed
            self._initialized = True
            return

        from kailash.db.connection import ConnectionManager

        self._conn = ConnectionManager(self._url)
        await self._conn.initialize()

        # Create all infrastructure tables
        from kailash.infrastructure.checkpoint_store import DBCheckpointStore
        from kailash.infrastructure.dlq import DBDeadLetterQueue
        from kailash.infrastructure.event_store import DBEventStoreBackend
        from kailash.infrastructure.execution_store import DBExecutionStore
        from kailash.infrastructure.idempotency_store import DBIdempotencyStore
        from kailash.infrastructure.lock_store import DBLockBackend

        for StoreClass in [
            DBEventStoreBackend,
            DBCheckpointStore,
            DBDeadLetterQueue,
            DBExecutionStore,
            DBIdempotencyStore,
            DBLockBackend,
        ]:
            store = StoreClass(self._conn)
            await store.initialize()

        # Stamp schema version
        await self._stamp_schema_version()

        self._initialized = True
        # Log connection info without leaking credentials
        safe_url = self._url.split("@")[-1] if "@" in self._url else self._url
        logger.info("Infrastructure stores initialized on %s", safe_url)

    async def _stamp_schema_version(self) -> None:
        """Write schema version to ``kailash_meta`` table.

        Raises
        ------
        RuntimeError
            If the database schema version is newer than the running code
            (downgrade protection).
        """
        if self._conn is None:
            raise RuntimeError(
                "Cannot stamp schema version: ConnectionManager is not initialized. "
                "Call initialize() first or provide a database_url."
            )

        await self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS kailash_meta "
            f"(key {self._conn.dialect.text_column(indexed=True)} PRIMARY KEY, value TEXT)"
        )

        row = await self._conn.fetchone(
            "SELECT value FROM kailash_meta WHERE key = ?", "schema_version"
        )

        if row:
            existing = int(row["value"])
            if existing > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {existing} is newer than code "
                    f"version {SCHEMA_VERSION}. Upgrade kailash to a newer version."
                )
            # If existing == SCHEMA_VERSION, nothing to do.
            # If existing < SCHEMA_VERSION, future migrations would go here.
        else:
            await self._conn.execute(
                "INSERT INTO kailash_meta (key, value) VALUES (?, ?)",
                "schema_version",
                str(SCHEMA_VERSION),
            )

    async def close(self) -> None:
        """Shutdown and release all resources.

        Safe to call multiple times.  After close, :meth:`initialize` can
        be called again to re-create the connection.
        """
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Store creation methods
    # ------------------------------------------------------------------
    async def create_event_store(self) -> Any:
        """Create an event store backend.

        Level 0: :class:`~kailash.middleware.gateway.event_store_sqlite.SqliteEventStoreBackend`
        Level 1+: :class:`~kailash.infrastructure.event_store.DBEventStoreBackend`
        """
        await self.initialize()
        if self._conn is None:
            from kailash.middleware.gateway.event_store_sqlite import (
                SqliteEventStoreBackend,
            )

            return SqliteEventStoreBackend()

        from kailash.infrastructure.event_store import DBEventStoreBackend

        return DBEventStoreBackend(self._conn)

    async def create_checkpoint_store(self) -> Any:
        """Create a checkpoint storage backend.

        Level 0: :class:`~kailash.middleware.gateway.checkpoint_manager.DiskStorage`
        Level 1+: :class:`~kailash.infrastructure.checkpoint_store.DBCheckpointStore`
        """
        await self.initialize()
        if self._conn is None:
            from kailash.middleware.gateway.checkpoint_manager import DiskStorage

            return DiskStorage()

        from kailash.infrastructure.checkpoint_store import DBCheckpointStore

        return DBCheckpointStore(self._conn)

    async def create_dlq(self) -> Any:
        """Create a dead letter queue.

        Level 0: :class:`~kailash.workflow.dlq.PersistentDLQ` (SQLite file-based)
        Level 1+: :class:`~kailash.infrastructure.dlq.DBDeadLetterQueue`
        """
        await self.initialize()
        if self._conn is None:
            from kailash.workflow.dlq import PersistentDLQ

            return PersistentDLQ()

        from kailash.infrastructure.dlq import DBDeadLetterQueue

        return DBDeadLetterQueue(self._conn)

    async def create_execution_store(self) -> Any:
        """Create an execution store.

        Level 0: :class:`~kailash.infrastructure.execution_store.InMemoryExecutionStore`
        Level 1+: :class:`~kailash.infrastructure.execution_store.DBExecutionStore`
        """
        await self.initialize()
        if self._conn is None:
            from kailash.infrastructure.execution_store import InMemoryExecutionStore

            return InMemoryExecutionStore()

        from kailash.infrastructure.execution_store import DBExecutionStore

        return DBExecutionStore(self._conn)

    async def create_idempotency_store(self) -> Optional[Any]:
        """Create an idempotency store.

        Level 0: ``None`` (no persistent idempotency at Level 0)
        Level 1+: :class:`~kailash.infrastructure.idempotency_store.DBIdempotencyStore`
        """
        await self.initialize()
        if self._conn is None:
            return None

        from kailash.infrastructure.idempotency_store import DBIdempotencyStore

        return DBIdempotencyStore(self._conn)

    async def create_lock_store(self, backend: Optional[str] = None) -> Any:
        """Create a :class:`~kailash.infrastructure.lock_store.DistributedLock`.

        Backend selection:

        * Explicit ``backend="redis"`` or ``backend="sql"`` overrides
          auto-detection.
        * Otherwise, a Redis backend is used when ``REDIS_URL`` (or
          ``KAILASH_REDIS_URL``) is set, falling back to the SQL backend
          (SQLite at Level 0, PostgreSQL / MySQL at Level 1+).

        Parameters
        ----------
        backend:
            ``"redis"``, ``"sql"``, or ``None`` (auto-detect).

        Returns
        -------
        DistributedLock
            A facade wrapping the selected, initialized backend.

        Raises
        ------
        ValueError
            If *backend* is not one of ``"redis"``, ``"sql"``, or ``None``.
        ImportError
            If the Redis backend is requested but the ``[redis]`` extra is
            not installed.
        """
        import os

        from kailash.infrastructure.lock_store import DBLockBackend, DistributedLock

        if backend not in (None, "redis", "sql"):
            raise ValueError(
                f"backend must be 'redis', 'sql', or None, got {backend!r}"
            )

        redis_url = os.environ.get("REDIS_URL") or os.environ.get("KAILASH_REDIS_URL")
        use_redis = backend == "redis" or (backend is None and bool(redis_url))

        if use_redis:
            if not redis_url:
                raise ValueError(
                    "Redis lock backend requested but no REDIS_URL / "
                    "KAILASH_REDIS_URL is set."
                )
            # Lazy import — the Redis backend lives behind the [redis] extra.
            from kailash.infrastructure.lock_store_redis import RedisLockBackend

            redis_backend = RedisLockBackend(redis_url)
            await redis_backend.initialize()
            return DistributedLock(redis_backend)

        # SQL backend — shares the factory's ConnectionManager (or a
        # private SQLite connection at Level 0).
        await self.initialize()
        if self._conn is None:
            # Level 0: build a dedicated in-process SQLite connection so the
            # lock store works with no database URL configured (SQLite is the
            # default store per the progressive-infrastructure model).
            from kailash.db.connection import ConnectionManager

            conn = ConnectionManager("sqlite:///kailash_locks.db")
            await conn.initialize()
            sql_backend = DBLockBackend(conn)
            await sql_backend.initialize()
            return DistributedLock(sql_backend)

        sql_backend = DBLockBackend(self._conn)
        await sql_backend.initialize()
        return DistributedLock(sql_backend)
