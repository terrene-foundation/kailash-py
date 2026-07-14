"""
DataFlow Connection Management

Reachability validation for the configured database. Long-lived asyncpg /
aiomysql / aiosqlite pools are NOT retained here — pools are owned per-loop
by ``AsyncSQLDatabaseNode._get_adapter()`` (priority chain at
``async_sql.py:4173``) keyed on
``loop_id|db_type|connection|pool_size|max_pool_size``
(``async_sql.py:4130``). The sole responsibility of this module is the
init-time fail-fast contract from ``rules/dataflow-pool.md`` Rule 2: prove
the database is reachable before ``DataFlow.__init__`` returns, then let
the per-loop registry serve every subsequent operation.

Issue #835 — prior versions retained ``self._adapter`` constructed inside
``async_safe_run`` 's worker-thread loop; that loop was closed at return
and every later ``db.transactions.begin()`` from a different loop hit
``RuntimeError: Event loop is closed`` on ``pool.acquire()``. Phase 2 of
the fix removes the retention; reachability is proved with a transient
adapter that is opened, verified, and disconnected within one
``async_safe_run`` call.
"""

import logging
import time
from typing import Any, Dict, Optional

from ..adapters.connection_parser import ConnectionParser

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Database reachability validator for DataFlow.

    Proves the configured database is reachable at startup (per
    ``rules/dataflow-pool.md`` Rule 2 fail-fast contract) WITHOUT retaining
    a long-lived adapter. Long-lived pools live in
    ``AsyncSQLDatabaseNode._get_adapter()``'s per-loop priority chain
    (``async_sql.py:4173``), keyed by
    ``loop_id|db_type|connection|pool_size|max_pool_size`` so each event
    loop receives its own pool with WeakValueDictionary-based reaping on
    loop close.

    The connection-stats accessor walks the per-loop registry rather than
    a single retained pool; the disconnect path is now a no-op because
    pools are not owned here.

    Args:
        dataflow_instance: The owning DataFlow instance.
        url_override: Override the DataFlow's database URL (for read replicas).
        pool_size_override: Override the configured pool size.
    """

    def __init__(
        self,
        dataflow_instance: Any,
        url_override: Optional[str] = None,
        pool_size_override: Optional[int] = None,
    ):
        self.dataflow = dataflow_instance
        self._url_override = url_override
        self._pool_size_override = pool_size_override
        self._initialized = False

        effective_pool_size = (
            pool_size_override
            if pool_size_override is not None
            else dataflow_instance.config.database.get_pool_size(
                dataflow_instance.config.environment
            )
        )
        self._pool_size = effective_pool_size

    def _get_db_url(self) -> str:
        """Resolve the effective database URL."""
        if self._url_override:
            return self._url_override
        config = self.dataflow.config
        url = config.database.get_connection_url(config.environment)
        if not isinstance(url, str):
            raise ValueError(f"Expected database URL string, got {type(url).__name__}")
        return url

    async def initialize_pool(self) -> Dict[str, Any]:
        """Verify reachability via a transient adapter; retain no pool.

        Per ``rules/dataflow-pool.md`` Rule 2, ``DataFlow.__init__`` (via
        the lazy ``_ensure_connected`` bridge) MUST fail-fast on an
        unreachable database. The reachability proof is
        ``await adapter.connect()`` succeeding — preserved exactly.

        Issue #835 fix: the adapter that proves reachability is now
        transient (opened, verified, disconnected). No long-lived pool is
        retained at ``self._adapter``; long-lived pools are created
        per-loop on first user-driven async call via
        ``AsyncSQLDatabaseNode._get_adapter()``'s priority chain.

        Returns:
            Dict with pool_initialized, pool_size, database_type, success.
            ``pool_size`` is the configured size that the per-loop
            ``AsyncSQLDatabaseNode`` pools will use; ``pool_initialized``
            stays ``True`` to preserve the contract that callers test for
            "DataFlow is ready to serve queries."

        Raises:
            ConnectionError / RuntimeError: If the database is
                unreachable. Cleanup-on-failure: the transient adapter is
                ``disconnect()``-ed before the original error propagates;
                a narrow exception swallow covers the disconnect path
                only (per ``rules/zero-tolerance.md`` Rule 3 carve-out
                for cleanup-on-failure).
        """
        from ..adapters.factory import AdapterFactory

        db_url = self._get_db_url()
        db_type = ConnectionParser.detect_database_type(db_url)

        # Transient adapter — opened, verified, discarded. Pool size 1
        # because we do nothing with the pool but prove the connection
        # works, then close it.
        # Issue #1737: thread the configured credential_provider through so
        # this reachability probe also mints a fresh token rather than
        # reusing a static (possibly stale) password.
        factory = AdapterFactory()
        test_adapter = factory.create_adapter(
            db_url,
            pool_size=1,
            max_overflow=0,
            credential_provider=self.dataflow.config.database.credential_provider,
        )

        try:
            await test_adapter.connect()
        except Exception:
            # Cleanup-on-connect-failure: best-effort disconnect, then
            # re-raise the original error. Narrow swallow per
            # rules/zero-tolerance.md Rule 3 — cleanup path only.
            try:
                await test_adapter.disconnect()
            except Exception:
                pass
            raise

        # Connection succeeded — discard the transient adapter, leave no
        # state behind. Per-loop pools are constructed lazily on first
        # `db.express.*` / `db.transactions.begin()` call.
        try:
            await test_adapter.disconnect()
        except Exception:
            # If disconnect of the transient adapter fails, the
            # reachability gate is still satisfied — the connection DID
            # succeed. Log at WARN per rules/observability.md Rule 5; do
            # not raise (would convert a successful reachability check
            # into a failed startup).
            logger.warning(
                "connection.transient_disconnect_failed",
                extra={"database_type": db_type},
            )

        self._initialized = True

        logger.info(
            "connection.pool.initialized",
            extra={
                "database_type": db_type,
                "pool_size": self._pool_size,
            },
        )

        return {
            "pool_initialized": True,
            "pool_size": self._pool_size,
            "database_type": db_type,
            "success": True,
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check database health via a transient ``SELECT 1``.

        Opens a fresh adapter on demand, runs ``SELECT 1``, disconnects.
        Does not depend on any retained pool — long-lived pools live in
        ``AsyncSQLDatabaseNode._get_adapter()``'s per-loop registry,
        which is owned by user-driven calls, not by health checks.

        Returns:
            Dict with database_reachable, latency_ms, success.
        """
        if not self._initialized:
            return {
                "database_reachable": False,
                "error": "Connection pool not initialized",
                "success": False,
            }

        from ..adapters.factory import AdapterFactory

        db_url = self._get_db_url()
        factory = AdapterFactory()
        # Issue #1737: same credential_provider threading as initialize_pool().
        test_adapter = factory.create_adapter(
            db_url,
            pool_size=1,
            max_overflow=0,
            credential_provider=self.dataflow.config.database.credential_provider,
        )

        t0 = time.monotonic()
        try:
            await test_adapter.connect()
            await test_adapter.execute_query("SELECT 1 AS health")
            latency_ms = (time.monotonic() - t0) * 1000

            logger.debug(
                "connection.health_check.ok",
                extra={"latency_ms": round(latency_ms, 2)},
            )

            return {
                "database_reachable": True,
                "latency_ms": round(latency_ms, 2),
                "pool_size": self._pool_size,
                "success": True,
            }
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "connection.health_check.failed",
                extra={"error": str(e), "latency_ms": round(latency_ms, 2)},
            )
            return {
                "database_reachable": False,
                "error": str(e),
                "latency_ms": round(latency_ms, 2),
                "success": False,
            }
        finally:
            # Best-effort disconnect of the transient adapter. Narrow
            # swallow per rules/zero-tolerance.md Rule 3 — cleanup path
            # only; failure to disconnect a transient pool does not
            # change the health verdict already returned above.
            try:
                await test_adapter.disconnect()
            except Exception:
                pass

    def get_connection_stats(self) -> Dict[str, Any]:
        """Aggregate connection-pool statistics across all per-loop pools
        owned by ``AsyncSQLDatabaseNode._get_adapter()``.

        Walks ``_PROCESS_POOL_REGISTRY`` (``async_sql.py:2656``) for
        entries whose pool key includes this DataFlow's connection
        string, summing pool size / idle / in-use across loops. Returns
        a synthetic, framework-level view of pool occupancy that
        replaces the prior single-retained-pool stats.

        When no per-loop pool has been initialized yet (cold start, no
        ``db.express.*`` or ``db.transactions.begin()`` call has run),
        returns zeros with ``initialized=True`` to signal the framework
        is ready but no pool has been touched.
        """
        try:
            from kailash.nodes.data.async_sql import _PROCESS_POOL_REGISTRY
        except ImportError:
            # Defensive: registry import failure means async_sql is not
            # importable — DataFlow itself would have failed earlier.
            return {
                "active_connections": 0,
                "total_connections": 0,
                "pool_size": self._pool_size,
                "initialized": False,
            }

        if not self._initialized:
            return {
                "active_connections": 0,
                "total_connections": 0,
                "pool_size": self._pool_size,
                "initialized": False,
            }

        db_url = self._get_db_url()
        # Pool keys: `loop_id|db_type|connection|pool_size|max_pool_size`
        # (async_sql.py:_generate_pool_key). Filter by connection-string
        # component so stats reflect only this DataFlow's pools, not
        # other DataFlow instances sharing the registry.
        current_size = 0
        free_size = 0
        used_size = 0
        per_loop_count = 0
        for key, pool in list(_PROCESS_POOL_REGISTRY.items()):
            if db_url not in key:
                continue
            per_loop_count += 1
            # asyncpg pool stats
            if hasattr(pool, "get_size") and hasattr(pool, "get_idle_size"):
                size = pool.get_size()
                idle = pool.get_idle_size()
                current_size += size
                free_size += idle
                used_size += size - idle
            # aiomysql pool stats
            elif hasattr(pool, "size") and hasattr(pool, "freesize"):
                size = pool.size
                idle = pool.freesize
                current_size += size
                free_size += idle
                used_size += size - idle

        return {
            "pool_size": self._pool_size,
            "initialized": True,
            "current_size": current_size,
            "free_size": free_size,
            "used_size": used_size,
            "per_loop_pool_count": per_loop_count,
        }

    def parse_database_url(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Parse database URL into components (no credentials in output)."""
        target_url = url or self._get_db_url()
        components = ConnectionParser.parse_connection_string(target_url)

        return {
            "scheme": components.get("scheme"),
            "hostname": components.get("host"),
            "port": components.get("port"),
            "database": components.get("database"),
            "username": components.get("username"),
            "has_password": bool(components.get("password")),
        }

    async def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Test database connection with a real query.

        Creates a temporary adapter, connects, runs SELECT 1, disconnects.
        Does NOT modify the main connection pool.
        """
        from ..adapters.factory import AdapterFactory

        target_url = url or self._get_db_url()
        db_type = ConnectionParser.detect_database_type(target_url)

        # Route through `AdapterFactory.create_adapter` — the canonical
        # transient-adapter constructor (same path used by `initialize_pool`
        # / `health_check`). The previous `AdapterFactory.get_adapter`
        # call was a phantom — the method does not exist on the class
        # (only `get_adapter_class`). This was a latent bug that raised
        # `AttributeError` on every `test_connection()` call; fixed under
        # `rules/zero-tolerance.md` Rule 1 in the same shard as the #835
        # transient-adapter migration.
        factory = AdapterFactory()
        # Issue #1737: same credential_provider threading as initialize_pool().
        test_adapter = factory.create_adapter(
            target_url,
            pool_size=1,
            max_overflow=0,
            credential_provider=self.dataflow.config.database.credential_provider,
        )
        try:
            await test_adapter.connect()
            await test_adapter.execute_query("SELECT 1 AS test")
            parsed = self.parse_database_url(target_url)

            return {
                "connection_successful": True,
                "database_type": db_type,
                "host": parsed["hostname"],
                "port": parsed["port"],
                "success": True,
            }
        except Exception as e:
            return {
                "connection_successful": False,
                "error": str(e),
                "database_type": db_type,
                "success": False,
            }
        finally:
            await test_adapter.disconnect()

    async def close_all_connections(self) -> Dict[str, Any]:
        """Mark the manager closed; pool teardown is delegated.

        Per-loop pools owned by ``AsyncSQLDatabaseNode._get_adapter()``
        are closed by the WeakValueDictionary reaper on loop close
        (``rules/dataflow-cache.md`` §13.4). The framework-level
        ``DataFlow.close()`` / ``close_async()`` also walks the
        node cache and triggers explicit disconnect — see
        ``core/engine.py::clear_async_sql_node_cache``.

        This method exists to preserve API stability for callers that
        still invoke it; it now flips ``_initialized`` to ``False`` so
        subsequent ``health_check()`` returns the not-initialized
        sentinel.
        """
        self._initialized = False
        return {"success": True}

    def __del__(self) -> None:
        """No-op finalizer.

        Pre-issue-#835, ConnectionManager retained ``self._adapter``
        owning an asyncpg pool, and ``__del__`` emitted ``ResourceWarning``
        when the manager was GC'd while still initialized. After
        Phase 2, no pool is retained on the manager — ``initialize_pool``
        is a transient reachability check; long-lived pools are owned
        by ``AsyncSQLDatabaseNode._get_adapter()`` and reaped via
        ``WeakValueDictionary`` on loop close. The leak surface this
        finalizer used to guard does not exist anymore.
        """
        # Intentionally empty. `warnings` import retained at module
        # scope for the historical signature; future cleanup discipline
        # belongs in `AsyncSQLDatabaseNode` and the registry reaper.
        return
