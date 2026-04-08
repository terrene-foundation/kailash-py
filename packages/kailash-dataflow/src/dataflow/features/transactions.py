"""
DataFlow Transaction Management

Real transaction support using the underlying database adapter.
Supports isolation levels, savepoints (nested transactions), and
automatic rollback on exception.

All transactions run on a single connection from the pool to ensure
atomicity. The connection is returned to the pool on commit/rollback.
"""

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)

# Track the active transaction connection per async context
_active_transaction: ContextVar[Optional[Any]] = ContextVar(
    "_active_transaction", default=None
)
_savepoint_depth: ContextVar[int] = ContextVar("_savepoint_depth", default=0)


class TransactionManager:
    """Transaction management for DataFlow operations.

    Provides real database transactions with:
    - Configurable isolation levels (READ COMMITTED, REPEATABLE READ, SERIALIZABLE)
    - Automatic rollback on exception
    - Nested transactions via SAVEPOINTs
    - Async context manager interface
    - ContextVar-based connection tracking (async-safe)

    Usage::

        async with db.transactions.begin() as txn:
            await db.express.create("User", {"name": "Alice"})
            await db.express.create("Profile", {"user_id": 1})
            # Both committed atomically on exit

        async with db.transactions.begin() as txn:
            await db.express.create("User", {"name": "Bob"})
            async with db.transactions.begin() as nested:
                # This is a SAVEPOINT
                await db.express.create("Profile", {"user_id": 2})
                raise ValueError("oops")
                # SAVEPOINT rolled back; outer transaction continues
    """

    def __init__(self, dataflow_instance: Any) -> None:
        self.dataflow = dataflow_instance
        self._stats = {
            "total_started": 0,
            "total_committed": 0,
            "total_rolled_back": 0,
        }

    @asynccontextmanager
    async def begin(
        self, isolation_level: str = "READ COMMITTED"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Begin a database transaction.

        Args:
            isolation_level: SQL isolation level. One of:
                - "READ COMMITTED" (default, safest for most use cases)
                - "REPEATABLE READ" (snapshot isolation)
                - "SERIALIZABLE" (strictest, may fail under contention)

        Yields:
            Transaction context dict with metadata (id, isolation_level, status).

        Raises:
            Exception: Re-raises any exception from the transaction body
                after rolling back.
        """
        current = _active_transaction.get()
        if current is not None:
            # Nested transaction — use SAVEPOINT
            async for ctx in self._savepoint():
                yield ctx
            return

        # Top-level transaction
        adapter = self._get_adapter()
        if adapter is None or adapter.connection_pool is None:
            raise RuntimeError(
                "TransactionManager: no database connection available. "
                "Ensure DataFlow is initialized with a database URL."
            )

        self._stats["total_started"] += 1
        txn_id = f"txn_{self._stats['total_started']}"

        logger.info(
            "transaction.begin",
            extra={
                "transaction_id": txn_id,
                "isolation_level": isolation_level,
            },
        )

        conn = await adapter.connection_pool.acquire()
        token = _active_transaction.set(conn)

        try:
            # Start the transaction with the requested isolation level
            await conn.execute(f"BEGIN ISOLATION LEVEL {isolation_level}")

            txn_context: Dict[str, Any] = {
                "id": txn_id,
                "isolation_level": isolation_level,
                "status": "active",
            }

            yield txn_context

            # Commit on clean exit
            await conn.execute("COMMIT")
            txn_context["status"] = "committed"
            self._stats["total_committed"] += 1
            logger.info(
                "transaction.commit",
                extra={"transaction_id": txn_id},
            )

        except Exception as e:
            # Rollback on exception
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                logger.warning(
                    "transaction.rollback_failed",
                    extra={"transaction_id": txn_id},
                )
            self._stats["total_rolled_back"] += 1
            logger.error(
                "transaction.rollback",
                extra={
                    "transaction_id": txn_id,
                    "error": str(e),
                },
            )
            raise

        finally:
            _active_transaction.reset(token)
            await adapter.connection_pool.release(conn)

    @asynccontextmanager
    async def _savepoint(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Create a SAVEPOINT within an existing transaction."""
        conn = _active_transaction.get()
        if conn is None:
            raise RuntimeError("_savepoint called outside a transaction")

        depth = _savepoint_depth.get()
        sp_name = f"sp_{depth}"
        depth_token = _savepoint_depth.set(depth + 1)

        logger.debug(
            "transaction.savepoint.begin",
            extra={"savepoint": sp_name, "depth": depth},
        )

        try:
            await conn.execute(f"SAVEPOINT {sp_name}")

            ctx: Dict[str, Any] = {
                "id": sp_name,
                "type": "savepoint",
                "depth": depth,
                "status": "active",
            }

            yield ctx

            await conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            ctx["status"] = "released"

        except Exception as e:
            try:
                await conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            except Exception:
                logger.warning(
                    "transaction.savepoint.rollback_failed",
                    extra={"savepoint": sp_name},
                )
            logger.debug(
                "transaction.savepoint.rollback",
                extra={"savepoint": sp_name, "error": str(e)},
            )
            raise

        finally:
            _savepoint_depth.reset(depth_token)

    def _get_adapter(self) -> Any:
        """Get the database adapter from the DataFlow instance.

        Walks the DataFlow instance to find an adapter with a live
        connection pool.
        """
        # Try the connection manager's adapter
        if hasattr(self.dataflow, "_connection_manager"):
            cm = self.dataflow._connection_manager
            if hasattr(cm, "_adapter") and cm._adapter is not None:
                return cm._adapter

        # Try direct adapter references
        for attr in ("_adapter", "_db_adapter", "adapter"):
            adapter = getattr(self.dataflow, attr, None)
            if adapter is not None and hasattr(adapter, "connection_pool"):
                return adapter

        # Try getting from the node cache
        if hasattr(self.dataflow, "_cached_async_node"):
            node = self.dataflow._cached_async_node
            if hasattr(node, "_pool") and node._pool is not None:
                return _PoolWrapper(node._pool)

        return None

    @staticmethod
    def get_active_connection() -> Any:
        """Get the connection for the current transaction, if any.

        Returns None if no transaction is active in the current async context.
        Express operations can check this to reuse the transaction connection.
        """
        return _active_transaction.get()

    def get_stats(self) -> Dict[str, int]:
        """Get transaction statistics."""
        return self._stats.copy()

    # Backward-compatible aliases for code that used the old API
    transaction = begin
    get_active_transactions = get_stats

    def rollback_all(self) -> Dict[str, Any]:
        """Emergency rollback — clears stats. Real rollbacks happen per-transaction."""
        count = self._stats["total_started"] - self._stats["total_committed"]
        self._stats = {
            "total_started": 0,
            "total_committed": 0,
            "total_rolled_back": 0,
        }
        return {"rolled_back_transactions": [], "count": count, "success": True}


class _PoolWrapper:
    """Minimal wrapper to present a raw pool as an adapter-like object."""

    def __init__(self, pool: Any) -> None:
        self.connection_pool = pool
