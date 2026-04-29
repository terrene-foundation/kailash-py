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
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

# Track the active transaction connection per async context
_active_transaction: ContextVar[Optional[Any]] = ContextVar(
    "_active_transaction", default=None
)
_savepoint_depth: ContextVar[int] = ContextVar("_savepoint_depth", default=0)


class TransactionScope:
    """The yielded scope inside an ``async with db.transactions.begin()`` block.

    Holds the pinned connection for the lifetime of the ``async with`` body
    and exposes ``execute_raw(sql, params)`` for multi-statement raw SQL the
    Express API does not express directly (DDL inside a tx, SELECT FOR UPDATE
    + INSERT, complex UPSERT-or-UPDATE).

    The pinned connection is set in ``_active_transaction`` ContextVar by the
    enclosing ``TransactionManager`` and cleared on exit. Calling
    ``execute_raw`` outside the ``async with`` body raises ``RuntimeError``
    per ``rules/zero-tolerance.md`` Rule 3a (typed delegate guard) — the
    pinned connection only exists while the scope is active.

    Backward-compat: existing tests / consumer code may treat this as a dict
    (``txn["id"]``) — ``__getitem__`` maps the canonical attributes through.
    """

    __slots__ = ("id", "isolation_level", "status", "type", "depth")

    def __init__(
        self,
        *,
        id: str,
        isolation_level: str,
        status: str = "active",
        type: str = "transaction",
        depth: Optional[int] = None,
    ) -> None:
        self.id = id
        self.isolation_level = isolation_level
        self.status = status
        self.type = type
        self.depth = depth

    def __getitem__(self, key: str) -> Any:
        """Backward-compat dict-style access.

        ``txn["id"]`` / ``txn["isolation_level"]`` / ``txn["status"]`` MUST
        keep working for code written against the prior dict-yielding API.
        Unknown keys raise ``KeyError`` to keep the dict semantics tight.
        """
        if key == "id":
            return self.id
        if key == "isolation_level":
            return self.isolation_level
        if key == "status":
            return self.status
        if key == "type":
            return self.type
        if key == "depth":
            return self.depth
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Backward-compat: allow ``txn["status"] = "committed"`` writes.

        Internal manager code historically assigned ``txn_context["status"] =
        "committed"`` after COMMIT. Preserve that affordance.
        """
        if key == "id":
            self.id = value
        elif key == "isolation_level":
            self.isolation_level = value
        elif key == "status":
            self.status = value
        elif key == "type":
            self.type = value
        elif key == "depth":
            self.depth = value
        else:
            raise KeyError(key)

    async def execute_raw(self, sql: str, params: Optional[List[Any]] = None) -> Any:
        """Execute a raw SQL statement on the pinned transaction connection.

        Routes the call through the connection bound by the enclosing
        ``async with db.transactions.begin()`` block. Use for multi-statement
        atomicity the Express API does not express directly:

            async with db.transactions.begin() as tx:
                rows = await tx.execute_raw(
                    "SELECT id FROM oauth_tokens WHERE user_id = $1 FOR UPDATE",
                    [user_id],
                )
                if rows:
                    await tx.execute_raw(
                        "UPDATE oauth_tokens SET refresh_token = $1 "
                        "WHERE user_id = $2",
                        [new_refresh, user_id],
                    )

        Args:
            sql: SQL statement. PostgreSQL placeholders are ``$1``, ``$2``,
                ``...``; SQLite placeholders are ``?``; MySQL placeholders are
                ``%s``. Pass dialect-appropriate placeholders for the
                underlying connection.
            params: Optional positional parameter list. asyncpg expects
                positional unpacking; aiosqlite expects a list/tuple. The
                method dispatches the binding shape based on the underlying
                connection type.

        Returns:
            For SELECT statements on asyncpg: a list of ``asyncpg.Record``
            rows (use ``dict(row)`` to materialize). For
            INSERT/UPDATE/DELETE on asyncpg: the command-tag string
            (e.g. ``"INSERT 0 1"``). For aiosqlite: the cursor object after
            ``execute()`` — use ``await cursor.fetchall()`` for SELECT.

        Raises:
            RuntimeError: When called outside the ``async with`` body —
                the pinned connection only exists while the scope is active.
        """
        conn = _active_transaction.get()
        if conn is None:
            raise RuntimeError(
                "TransactionScope.execute_raw called outside the transaction "
                "body — ensure the call is inside the "
                "`async with db.transactions.begin()` scope. "
                "The pinned connection is only valid while the scope is active."
            )

        # asyncpg: connection.fetch / .execute take *params positional.
        # aiosqlite: connection.execute takes a single tuple/list arg.
        # Dispatch by connection type to bind correctly. asyncpg connections
        # have a `fetch` method; aiosqlite connections do not.
        is_asyncpg = hasattr(conn, "fetch") and hasattr(conn, "fetchrow")

        sql_stripped = sql.lstrip()
        is_select = (
            sql_stripped[:6].upper() == "SELECT" or sql_stripped[:4].upper() == "WITH"
        )

        if is_asyncpg:
            if params is None:
                if is_select:
                    return await conn.fetch(sql)
                return await conn.execute(sql)
            # asyncpg: positional unpacking
            if is_select:
                return await conn.fetch(sql, *params)
            return await conn.execute(sql, *params)
        # aiosqlite-style: single tuple param
        if params is None:
            return await conn.execute(sql)
        return await conn.execute(sql, params)


class TransactionManager:
    """Transaction management for DataFlow operations.

    Provides real database transactions with:
    - Configurable isolation levels (READ COMMITTED, REPEATABLE READ, SERIALIZABLE)
    - Automatic rollback on exception
    - Nested transactions via SAVEPOINTs
    - Async context manager interface
    - ContextVar-based connection tracking (async-safe)

    Usage::

        async with db.transactions.begin() as tx:
            await db.express.create("User", {"name": "Alice"})
            await db.express.create("Profile", {"user_id": 1})
            # Both committed atomically on exit

        async with db.transactions.begin() as tx:
            # Multi-statement raw SQL atomicity via tx.execute_raw
            existing = await tx.execute_raw(
                "SELECT id FROM users WHERE email = $1 FOR UPDATE",
                ["alice@example.com"],
            )
            if not existing:
                await tx.execute_raw(
                    "INSERT INTO users (email) VALUES ($1)",
                    ["alice@example.com"],
                )

        async with db.transactions.begin() as outer:
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
    ) -> AsyncGenerator[TransactionScope, None]:
        """Begin a database transaction.

        Args:
            isolation_level: SQL isolation level. One of:
                - "READ COMMITTED" (default, safest for most use cases)
                - "REPEATABLE READ" (snapshot isolation)
                - "SERIALIZABLE" (strictest, may fail under contention)

        Yields:
            TransactionScope with metadata (id, isolation_level, status) plus
            ``execute_raw(sql, params)`` for multi-statement raw SQL on the
            pinned connection. Backward-compatible dict-style access
            (``txn["id"]``) is preserved.

        Raises:
            Exception: Re-raises any exception from the transaction body
                after rolling back.
        """
        current = _active_transaction.get()
        if current is not None:
            # Nested transaction — use SAVEPOINT
            async with self._savepoint() as ctx:
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

            scope = TransactionScope(
                id=txn_id,
                isolation_level=isolation_level,
                status="active",
                type="transaction",
            )

            yield scope

            # Commit on clean exit
            await conn.execute("COMMIT")
            scope.status = "committed"
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
    async def _savepoint(self) -> AsyncGenerator[TransactionScope, None]:
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

            scope = TransactionScope(
                id=sp_name,
                isolation_level="",  # savepoints inherit from outer txn
                status="active",
                type="savepoint",
                depth=depth,
            )

            yield scope

            await conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            scope.status = "released"

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
