"""
DataFlow Transaction Management

Real transaction support using the underlying database adapter.
Supports isolation levels, savepoints (nested transactions), and
automatic rollback on exception.

All transactions run on a single connection from the pool to ensure
atomicity. The connection is returned to the pool on commit/rollback.

Sync surface — ``db.transactions_sync.begin()`` — mirrors the async API
for callers that cannot ``await`` (CLI scripts, sync FastAPI handlers,
pytest non-async tests, Jupyter sync cells). The sync wrapper owns a
persistent daemon-thread event loop and routes every coroutine via
``asyncio.run_coroutine_threadsafe`` so the pinned connection survives
across multiple ``tx.execute_raw`` calls — the same pattern
``SyncExpress`` uses (see ``packages/kailash-dataflow/src/dataflow/
features/express.py::SyncExpress``). Cross-context safe: the BG loop
thread is independent of the host event loop, so the surface works
inside pytest-asyncio, Nexus handlers, and Jupyter without raising
``RuntimeError: This event loop is already running``.
"""

import asyncio
import logging
import threading
import warnings

from dataflow.core.exceptions import (
    sanitize_db_error,
)  # Issue #1552: redact driver-error VALUES
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any, AsyncGenerator, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Track the active transaction connection per async context
_active_transaction: ContextVar[Optional[Any]] = ContextVar(
    "_active_transaction", default=None
)
_savepoint_depth: ContextVar[int] = ContextVar("_savepoint_depth", default=0)


def _classify_raw_sql_operation(sql: str) -> str:
    """Classify raw SQL into a `WriteProtectionEngine.check_operation` name.

    Closes the same-bug-class gap surfaced by /redteam against the #1050
    chain: `TransactionScope.execute_raw` and `SyncTransactionScope.
    execute_raw` were the only DataFlow write surfaces not routed through
    `check_operation` (spec invariant I1). Without this classifier a
    caller with `read_only_mode=True` could `DELETE FROM users` through
    `async with db.transactions.begin()`.

    The classifier reads the leading SQL keyword and maps to an existing
    operation name so the protection engine's `_operation_mapping` decides
    BLOCK / AUDIT / WARN per its existing semantics (no new enum needed).

    Mapping:
    - `SELECT` / `WITH` / `SHOW` / `EXPLAIN` → "read" (READ tier — always
      allowed under read_only_global / production_safe).
    - `INSERT` → "create"; `UPDATE` → "update"; `DELETE` → "delete";
      `UPSERT` (PostgreSQL `INSERT ... ON CONFLICT` is technically INSERT,
      caught above) → "upsert".
    - DDL (`CREATE` / `DROP` / `ALTER` / `TRUNCATE`) → falls through to
      `custom_query` which the engine maps to `OperationType.CUSTOM_QUERY`
      and BLOCKS under read_only_global / production_safe defaults.
    - Anything unrecognized → "custom_query" (fail-closed in protected mode).
    """
    stripped = sql.lstrip()
    if not stripped:
        return "custom_query"
    head = stripped[:8].upper().split()[0] if stripped else ""
    if head in ("SELECT", "WITH", "SHOW", "EXPLAIN", "VALUES", "TABLE"):
        return "read"
    if head == "INSERT":
        return "create"
    if head == "UPDATE":
        return "update"
    if head == "DELETE":
        return "delete"
    if head == "UPSERT":  # MySQL UPSERT keyword if exposed
        return "upsert"
    # DDL + everything else falls through to CUSTOM_QUERY (engine BLOCKS
    # under read_only_global / production_safe by default).
    return "custom_query"


async def _execute_raw_with_protection(
    sql: str,
    params: Optional[List[Any]],
    *,
    dataflow_instance: Optional[Any],
    conn: Any,
) -> Any:
    """Run protection check then dispatch raw SQL on the pinned connection.

    Single helper used by both `TransactionScope.execute_raw` (async) and
    `SyncTransactionScope.execute_raw` (sync, via the BG loop). Pulls the
    protection engine off the DataFlow instance the same way Express does
    (`packages/kailash-dataflow/src/dataflow/features/express.py::
    DataFlowExpress._check_protection_if_enabled`); on a non-protected
    DataFlow the check is a no-op.
    """
    if dataflow_instance is not None:
        protection_engine = getattr(dataflow_instance, "_protection_engine", None)
        if protection_engine is not None:
            connection_string = getattr(dataflow_instance, "database_url", None)
            operation = _classify_raw_sql_operation(sql)
            # context mirrors DataFlowExpress._check_protection_if_enabled —
            # auditor accepts missing keys.
            protection_engine.check_operation(
                operation=operation,
                model_name=None,
                connection_string=connection_string,
                context={"surface": "transactions.execute_raw"},
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
        if is_select:
            return await conn.fetch(sql, *params)
        return await conn.execute(sql, *params)
    if params is None:
        return await conn.execute(sql)
    return await conn.execute(sql, params)


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

    __slots__ = (
        "id",
        "isolation_level",
        "status",
        "type",
        "depth",
        "_dataflow_instance",
    )

    def __init__(
        self,
        *,
        id: str,
        isolation_level: str,
        status: str = "active",
        type: str = "transaction",
        depth: Optional[int] = None,
        dataflow_instance: Optional[Any] = None,
    ) -> None:
        self.id = id
        self.isolation_level = isolation_level
        self.status = status
        self.type = type
        self.depth = depth
        # Held so execute_raw can route through _protection_engine the same
        # way DataFlowExpress does. See _execute_raw_with_protection.
        self._dataflow_instance = dataflow_instance

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
            ProtectionViolation: When the DataFlow instance has write
                protection enabled and the SQL is classified as a write
                under the current protection level (spec invariant I1 —
                single-check discipline extended to the raw-SQL surface,
                closes the same-bug-class gap surfaced post-#1050 by the
                multi-agent /redteam against the closure of #1083).
        """
        conn = _active_transaction.get()
        if conn is None:
            raise RuntimeError(
                "TransactionScope.execute_raw called outside the transaction "
                "body — ensure the call is inside the "
                "`async with db.transactions.begin()` scope. "
                "The pinned connection is only valid while the scope is active."
            )
        return await _execute_raw_with_protection(
            sql,
            params,
            dataflow_instance=self._dataflow_instance,
            conn=conn,
        )


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
        adapter = await self._get_adapter()
        # Normalize pool access across adapter shapes:
        #
        # - DataFlow-package adapters (`packages/kailash-dataflow/src/dataflow/
        #   adapters/postgresql.py`) expose the asyncpg pool on
        #   ``self.connection_pool``.
        # - Core-SDK adapters (`src/kailash/nodes/data/async_sql.py::PostgreSQLAdapter`,
        #   ``ProductionPostgreSQLAdapter``) expose it on ``self._pool``.
        #
        # After issue #835's per-loop migration, ``_get_adapter`` resolves to
        # the core-SDK adapter (returned by ``AsyncSQLDatabaseNode._get_adapter``),
        # so we read both attributes and use whichever holds the pool. The
        # historical `_PoolWrapper` class did this same normalization; its
        # responsibility moved here once `_get_adapter` was simplified.
        pool = getattr(adapter, "connection_pool", None) or getattr(
            adapter, "_pool", None
        )
        if adapter is None or pool is None:
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

        conn = await pool.acquire()
        token = _active_transaction.set(conn)

        try:
            # Start the transaction with the requested isolation level
            await conn.execute(f"BEGIN ISOLATION LEVEL {isolation_level}")

            scope = TransactionScope(
                id=txn_id,
                isolation_level=isolation_level,
                status="active",
                type="transaction",
                dataflow_instance=self.dataflow,
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
                    # Issue #1552 (FIX 3): the rolled-back transaction's driver
                    # error may carry a VALUE-bearing constraint clause; sanitize
                    # the ERROR log. The re-raise below preserves the caller's raw
                    # exception for local diagnosability (mirrors #1550 / FIX 1).
                    "error": sanitize_db_error(str(e)),
                },
            )
            raise

        finally:
            _active_transaction.reset(token)
            await pool.release(conn)

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
                dataflow_instance=self.dataflow,
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

    async def _get_adapter(self) -> Any:
        """Resolve the per-loop database adapter via DataFlow's cached
        ``AsyncSQLDatabaseNode``.

        Routes through ``DataFlow._get_or_create_async_sql_node(db_type)`` —
        the single source of truth for the cached node, with built-in
        event-loop change detection (engine.py:7794) — and then through the
        node's own ``_get_adapter()`` priority chain (async_sql.py:4173:
        ``_shared_pools`` → runtime pool → ``_PROCESS_POOL_REGISTRY`` →
        fallback). The 5-component pool key
        ``loop_id|db_type|connection|pool_size|max_pool_size``
        (async_sql.py:4130 ``_generate_pool_key``) means the transaction
        path and ``db.express.*`` share one entry per loop in
        ``_PROCESS_POOL_REGISTRY``.

        Resolves issue #835: prior implementation read
        ``_connection_manager._adapter``, an asyncpg pool bound to whichever
        loop the lazy ``_ensure_connected`` happened to run inside (typically
        the daemon thread loop or a worker-thread loop closed at return).
        Subsequent ``begin()`` from any caller-loop hit
        ``RuntimeError: Event loop is closed`` on ``pool.acquire()``.
        Per-loop resolution + WeakValueDictionary auto-reaping
        (specs/dataflow-cache.md §13.4) makes the failure mode unreachable.

        Raises:
            RuntimeError: When called outside a running event loop, or
                when the priority chain returns ``None``.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "TransactionManager.begin() requires a running event loop. "
                "Call from within an async function or `asyncio.run(...)`."
            ) from e

        db_type = self.dataflow._detect_database_type()
        node = self.dataflow._get_or_create_async_sql_node(db_type)
        adapter = await node._get_adapter()
        if adapter is None:
            raise RuntimeError(
                "TransactionManager could not resolve a database adapter — "
                "the AsyncSQLDatabaseNode priority chain returned None. "
                "Check DataFlow init logs."
            )
        return adapter

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


# ============================================================================
# Sync surface — ``db.transactions_sync.begin()`` (issue #711)
# ============================================================================

# Sentinel placed in the sync scope when the ``with`` block has exited. Any
# subsequent ``tx.execute_raw`` call MUST raise ``RuntimeError`` per
# ``rules/zero-tolerance.md`` Rule 3a (typed delegate guard) — the pinned
# connection only exists while the scope is active.
_SCOPE_INACTIVE = object()


# --- Async helpers used by SyncTransactionManager ------------------------
#
# These are module-level coroutines (NOT methods on the class) so the BG
# loop can await them without holding a reference to the manager — keeps
# the coroutine objects pickle-light and avoids retaining the manager
# across the BG loop's lifetime.


async def _open_connection_for_url(
    url: str, credential_provider: Optional[Callable[[], str]] = None
) -> Any:
    """Open a fresh asyncpg/aiosqlite connection on the current loop.

    Dispatches by URL scheme. The returned connection is bound to the
    event loop currently executing this coroutine — for the sync surface,
    that is the SyncTransactionManager's BG loop.

    Issue #1741: when ``credential_provider`` is set (token-based DB auth —
    Azure AD / AWS IAM), the PostgreSQL branch mints a FRESH credential for
    this physical connection via the shared fail-closed helper rather than
    trusting the (possibly stale) password embedded in ``url``. Because the
    sync manager opens one connection per ``begin()`` (not a pool), the
    helper's ``connect`` callable is invoked directly. Absent (None),
    behavior is unchanged.
    """
    scheme = url.split(":", 1)[0].lower()
    if scheme in ("postgresql", "postgres"):
        import asyncpg

        if credential_provider is not None:
            from dataflow.core.credential_provider import (
                build_asyncpg_credential_connect,
            )

            connect = build_asyncpg_credential_connect(
                credential_provider,
                asyncpg,
                context="PostgreSQL sync transaction",
            )
            return await connect(url)
        return await asyncpg.connect(url)
    if scheme == "sqlite":
        import aiosqlite

        # Strip the sqlite:// prefix; aiosqlite expects the path.
        path = url.split("://", 1)[1] if "://" in url else url
        # aiosqlite.connect returns a connection-context object; calling
        # ``__aenter__`` opens the connection and returns the conn.
        conn = aiosqlite.connect(path)
        return await conn.__aenter__()
    raise RuntimeError(
        f"SyncTransactionManager: unsupported database scheme '{scheme}' "
        f"in URL — only postgresql and sqlite are wired."
    )


async def _begin_isolation(conn: Any, isolation_level: str) -> None:
    """Issue ``BEGIN ISOLATION LEVEL <level>`` on the connection."""
    is_asyncpg = hasattr(conn, "fetch") and hasattr(conn, "fetchrow")
    if is_asyncpg:
        await conn.execute(f"BEGIN ISOLATION LEVEL {isolation_level}")
    else:
        # SQLite ignores ISOLATION LEVEL; use plain BEGIN.
        await conn.execute("BEGIN")


async def _commit(conn: Any) -> None:
    """Issue COMMIT on the pinned transaction connection."""
    await conn.execute("COMMIT")


async def _rollback(conn: Any) -> None:
    """Issue ROLLBACK on the pinned transaction connection."""
    await conn.execute("ROLLBACK")


async def _close_connection(conn: Any) -> None:
    """Close the connection. Dispatches by connection type."""
    is_asyncpg = hasattr(conn, "fetch") and hasattr(conn, "fetchrow")
    if is_asyncpg:
        await conn.close()
    else:
        # aiosqlite Connection has ``close`` returning a coroutine.
        await conn.close()


class SyncTransactionScope:
    """Sync analogue of :class:`TransactionScope`.

    Yielded by :func:`SyncTransactionManager.begin`. Holds the BG-loop
    submitter and a reference to the pinned asyncpg/aiosqlite connection
    so ``tx.execute_raw(sql, params)`` can issue async DB calls from sync
    code without the caller awaiting anything.

    The scope is single-use — exiting the ``with`` block clears the
    pinned connection reference so any further ``execute_raw`` calls
    raise the typed-guard ``RuntimeError`` (per
    ``rules/zero-tolerance.md`` Rule 3a) instead of silently re-using a
    connection that has been returned to the pool / closed.

    Mirrors the async ``TransactionScope`` metadata surface (id,
    isolation_level, status, type) for parity with the async API; the
    backward-compat dict ``__getitem__`` / ``__setitem__`` from the async
    scope is intentionally NOT mirrored — sync callers landed in 0.x with
    the canonical attribute access only.
    """

    __slots__ = (
        "_conn",
        "_run_sync",
        "_id",
        "_isolation_level",
        "_status",
        "_type",
        "_depth",
        "_dataflow_instance",
    )

    def __init__(
        self,
        *,
        conn: Any,
        run_sync: Any,
        id: str,
        isolation_level: str,
        status: str = "active",
        type: str = "transaction",
        depth: Optional[int] = None,
        dataflow_instance: Optional[Any] = None,
    ) -> None:
        # ``conn`` is the pinned asyncpg/aiosqlite connection (NOT a pool)
        # bound to the manager's BG event loop. Set to ``_SCOPE_INACTIVE``
        # when the with-block exits so post-block ``execute_raw`` raises.
        self._conn: Any = conn
        # ``run_sync`` is a callable: ``run_sync(coro) -> result``. It
        # submits the coroutine to the manager's BG event loop and blocks
        # for the result. Stored on the scope so it survives the with body.
        self._run_sync = run_sync
        self._id = id
        self._isolation_level = isolation_level
        self._status = status
        self._type = type
        self._depth = depth
        # Held so execute_raw can route through _protection_engine the same
        # way the async scope does. See _execute_raw_with_protection.
        self._dataflow_instance = dataflow_instance

    # --- Metadata mirror of the async scope (read-only attribute proxies) ---

    @property
    def id(self) -> str:
        return self._id

    @property
    def isolation_level(self) -> str:
        return self._isolation_level

    @property
    def status(self) -> str:
        return self._status

    @property
    def type(self) -> str:
        return self._type

    @property
    def depth(self) -> Optional[int]:
        return self._depth

    # --- Sync execute_raw — the load-bearing surface ---

    def execute_raw(self, sql: str, params: Optional[List[Any]] = None) -> Any:
        """Execute a raw SQL statement on the pinned transaction connection.

        Sync analogue of :meth:`TransactionScope.execute_raw`. Submits the
        underlying async call to the manager's BG event loop and blocks for
        the result, so the pinned connection is the same across every call
        inside the ``with`` body — the load-bearing invariant for the OAuth
        credential-rotation pattern this surface was added for.

        Calling ``execute_raw`` outside the ``with`` body raises
        ``RuntimeError`` (typed delegate guard per
        ``rules/zero-tolerance.md`` Rule 3a) — the pinned connection only
        exists while the scope is active.

        Args:
            sql: SQL statement using dialect-appropriate placeholders
                (``$1`` / ``$2`` for asyncpg, ``?`` for aiosqlite, ``%s``
                for MySQL).
            params: Optional positional parameter list.

        Returns:
            For SELECT statements on asyncpg: a list of ``asyncpg.Record``
            rows (use ``dict(row)`` to materialize). For
            INSERT/UPDATE/DELETE on asyncpg: the command-tag string. For
            aiosqlite: the cursor object after ``execute()``.

        Raises:
            ProtectionViolation: When the DataFlow instance has write
                protection enabled and the SQL is classified as a write
                under the current protection level — same routing as
                :meth:`TransactionScope.execute_raw`.
        """
        conn = self._guarded_conn()
        return self._run_sync(
            _execute_raw_with_protection(
                sql,
                params,
                dataflow_instance=self._dataflow_instance,
                conn=conn,
            )
        )

    # --- Internal: typed guard for out-of-scope access ---

    def _guarded_conn(self) -> Any:
        if self._conn is _SCOPE_INACTIVE:
            raise RuntimeError(
                "SyncTransactionScope.execute_raw called outside the "
                "transaction body — ensure the call is inside the "
                "`with db.transactions_sync.begin()` scope. "
                "The pinned connection is only valid while the scope is "
                "active."
            )
        return self._conn

    def _mark_inactive(self) -> None:
        """Called by the manager when the ``with`` block exits.

        Replaces the connection reference with the inactive sentinel so
        the guarded accessor raises a typed error rather than silently
        re-using a connection that has been returned to the pool.
        """
        self._conn = _SCOPE_INACTIVE


async def _execute_raw_on_conn(
    conn: Any, sql: str, params: Optional[List[Any]] = None
) -> Any:
    """Execute a raw SQL statement on an asyncpg/aiosqlite connection.

    Connection-type dispatch only — does NOT route through the protection
    engine. Prefer :func:`_execute_raw_with_protection` from the
    `TransactionScope` / `SyncTransactionScope` entry points; this helper
    remains for callers that have already done the protection check OR
    are operating on a non-DataFlow-owned connection.
    """
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
        if is_select:
            return await conn.fetch(sql, *params)
        return await conn.execute(sql, *params)
    # aiosqlite-style: single tuple param.
    if params is None:
        return await conn.execute(sql)
    return await conn.execute(sql, params)


class SyncTransactionManager:
    """Sync surface for :class:`TransactionManager` (issue #711).

    Mirror of :func:`TransactionManager.begin` for sync callers. Owns a
    persistent daemon-thread event loop AND a private asyncpg/aiosqlite
    connection lifecycle on that loop — every ``begin()`` opens a fresh
    connection on the BG loop, runs the transaction body, and closes the
    connection. The same BG loop is shared across all ``begin()`` calls
    so the pinned connection survives across multiple ``tx.execute_raw``
    invocations inside one ``with`` block.

    Cross-context safe — the BG loop thread is independent of any host
    event loop. The surface works inside pytest-asyncio, Nexus handlers,
    and Jupyter cells without raising
    ``RuntimeError: This event loop is already running`` AND without
    sharing the DataFlow asyncpg pool (which is bound to whatever loop
    initialized it). asyncpg connections are loop-bound; sharing a pool
    across the host loop and the BG loop produces
    ``RuntimeError: Future ... attached to a different loop``. Owning
    a private connection lifecycle on the BG loop is the structural
    fix for cross-loop usage.

    Lifecycle::

        # Construction (lazy at db.transactions_sync first access):
        sync_mgr = SyncTransactionManager(async_mgr)

        # Use:
        with sync_mgr.begin() as tx:
            existing = tx.execute_raw(
                "SELECT id FROM oauth_tokens WHERE user_id = $1 FOR UPDATE",
                [user_id],
            )
            if existing:
                tx.execute_raw(
                    "UPDATE oauth_tokens SET refresh_token = $1 "
                    "WHERE user_id = $2",
                    [new_refresh, user_id],
                )

        # Teardown (wired into DataFlow.close() / close_async()):
        sync_mgr.close_sync()
    """

    def __init__(self, transactions: TransactionManager) -> None:
        # Reference to the async manager — used to read the database URL
        # via ``transactions.dataflow`` AND to participate in the shared
        # transaction-statistics counter. The sync surface does NOT drive
        # the async ``begin()`` directly because asyncpg connections are
        # loop-bound (see class docstring).
        self._transactions = transactions

        # Persistent BG event loop in a daemon thread. Mirrors
        # ``SyncExpress.__init__`` (express.py:1772-1779). Daemon=True so
        # the thread dies with the interpreter even if ``close_sync`` was
        # not called — defensive, matches SyncExpress.
        self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.new_event_loop()
        self._thread: Optional[threading.Thread] = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="SyncTransactionManager-loop",
        )
        self._thread.start()

        # Per `rules/zero-tolerance.md` Rule 6 — explicit close path.
        # `_closed` lets ``__del__`` distinguish "user forgot to close"
        # (ResourceWarning) from "user closed correctly" (silent).
        self._closed = False

        # Counter shared with the async manager so `db.transactions.get_stats`
        # reflects sync transactions too. Falls back to a private counter
        # when the async manager has no `_stats` attribute (defensive).
        if not hasattr(self._transactions, "_stats"):
            self._transactions._stats = {  # type: ignore[attr-defined]
                "total_started": 0,
                "total_committed": 0,
                "total_rolled_back": 0,
            }

    # --- BG-loop dispatch ---

    def _run_sync(self, coro: Any) -> Any:
        """Run an async coroutine synchronously on the persistent BG loop.

        Mirrors ``SyncExpress._run_sync`` (express.py:1775-1784). All async
        operations submit to the same BG loop so the pinned transaction
        connection (which is bound to that loop) survives across calls.
        """
        if self._closed or self._loop is None:
            raise RuntimeError(
                "SyncTransactionManager is closed — construct a fresh "
                "DataFlow instance or avoid calling close_sync() before "
                "the transaction surface is fully drained."
            )
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _resolve_database_url(self) -> str:
        """Resolve the database URL from the wrapped DataFlow instance.

        The URL is the only state the sync manager needs from the
        DataFlow — the asyncpg connection is opened fresh on the BG loop
        for each transaction. Raises a typed error if the URL cannot be
        resolved (per rules/zero-tolerance.md Rule 3a).
        """
        dataflow = getattr(self._transactions, "dataflow", None)
        if dataflow is None:
            raise RuntimeError(
                "SyncTransactionManager: TransactionManager has no "
                "`dataflow` back-reference; cannot resolve database URL."
            )
        # DataFlow's canonical URL accessor — falls back to config.database.url.
        url = None
        for attr_path in (
            ("config", "database", "url"),
            ("_database_url",),
            ("database_url",),
        ):
            obj = dataflow
            try:
                for attr in attr_path:
                    obj = getattr(obj, attr)
            except AttributeError:
                continue
            if obj:
                url = obj
                break
        if not url:
            raise RuntimeError(
                "SyncTransactionManager: could not resolve database URL "
                "from DataFlow instance."
            )
        # `url` resolves through `getattr` chains so mypy sees `Any`; coerce
        # to the declared `str` return type per rules/zero-tolerance.md Rule 1
        # (mypy --strict was complaining; pre-existing minor typing gap fixed
        # in same shard as #835's transaction migration).
        return str(url)

    # --- Public: begin() ---

    @contextmanager
    def begin(
        self, isolation_level: str = "READ COMMITTED"
    ) -> Iterator[SyncTransactionScope]:
        """Begin a database transaction (sync).

        Mirror of :func:`TransactionManager.begin`. Yields a
        :class:`SyncTransactionScope` whose ``execute_raw(sql, params)``
        runs on the pinned connection.

        Args:
            isolation_level: SQL isolation level (default ``"READ COMMITTED"``).
                See :func:`TransactionManager.begin` for supported values.

        Yields:
            :class:`SyncTransactionScope` — exposes ``execute_raw`` and the
            metadata fields (``id``, ``isolation_level``, ``status``,
            ``type``, ``depth``) mirrored from the async scope.

        Raises:
            Re-raises any exception from the body after rollback.
        """
        url = self._resolve_database_url()
        # Issue #1741: resolve the optional per-connection credential callback
        # from the wrapped DataFlow so token-based auth mints a fresh token for
        # this transaction's connection (defensive getattr chain — a bare
        # TransactionManager without a DataFlow back-reference resolves None).
        credential_provider = getattr(
            getattr(
                getattr(getattr(self._transactions, "dataflow", None), "config", None),
                "database",
                None,
            ),
            "credential_provider",
            None,
        )
        # Acquire a fresh connection on the BG loop, BEGIN the transaction.
        # The connection is loop-bound to the BG loop, NOT the host loop,
        # so subsequent ``execute_raw`` calls (also routed via the BG loop)
        # use the same connection without cross-loop drift.
        conn = self._run_sync(_open_connection_for_url(url, credential_provider))
        try:
            self._run_sync(_begin_isolation(conn, isolation_level))
        except BaseException:
            # If BEGIN fails, close the conn before propagating so we
            # don't leak the asyncpg socket on the BG loop.
            try:
                self._run_sync(_close_connection(conn))
            except Exception:
                pass
            raise

        self._transactions._stats["total_started"] += 1
        txn_id = f"sync_txn_{self._transactions._stats['total_started']}"

        logger.info(
            "transaction.sync.begin",
            extra={
                "transaction_id": txn_id,
                "isolation_level": isolation_level,
            },
        )

        sync_scope = SyncTransactionScope(
            conn=conn,
            run_sync=self._run_sync,
            id=txn_id,
            isolation_level=isolation_level,
            status="active",
            type="transaction",
            dataflow_instance=self._transactions.dataflow,
        )

        try:
            yield sync_scope
        except BaseException:
            # Rollback on exception — mirror TransactionManager.begin's
            # rollback path.
            try:
                self._run_sync(_rollback(conn))
            except Exception:
                logger.warning(
                    "transaction.sync.rollback_failed",
                    extra={"transaction_id": txn_id},
                )
            self._transactions._stats["total_rolled_back"] += 1
            logger.error(
                "transaction.sync.rollback",
                extra={"transaction_id": txn_id},
            )
            raise
        else:
            # Commit on clean exit.
            self._run_sync(_commit(conn))
            sync_scope._status = "committed"
            self._transactions._stats["total_committed"] += 1
            logger.info(
                "transaction.sync.commit",
                extra={"transaction_id": txn_id},
            )
        finally:
            sync_scope._mark_inactive()
            try:
                self._run_sync(_close_connection(conn))
            except Exception:
                logger.debug(
                    "transaction.sync.close_failed",
                    extra={"transaction_id": txn_id},
                )

    # --- Lifecycle ---

    def close_sync(self) -> None:
        """Stop the BG event loop thread cleanly.

        Wired into :func:`DataFlow.close` and :func:`DataFlow.close_async`
        so ``with DataFlow(...)`` / ``async with`` callers do not need to
        invoke this manually. Safe to call multiple times.
        """
        if self._closed:
            return
        self._closed = True

        loop = self._loop
        thread = self._thread
        # Drop references first so concurrent ``_run_sync`` callers see
        # ``self._closed = True`` and raise the closed-error.
        self._loop = None
        self._thread = None

        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                # Loop already stopped or destroyed — safe to ignore in
                # cleanup; the closed flag prevents reuse.
                pass

        if thread is not None and thread.is_alive():
            # Bounded join — the loop should stop near-instantly. A 5s
            # ceiling prevents test hangs if something pathological keeps
            # the loop alive (we can't deadlock the suite for cleanup).
            thread.join(timeout=5.0)

        if loop is not None:
            try:
                loop.close()
            except RuntimeError:
                # Loop may already be closed by run_forever() shutdown —
                # the closed flag is the source of truth.
                pass

    def __del__(self, _warnings: Any = warnings) -> None:
        """Emit ``ResourceWarning`` if the BG thread was not stopped cleanly.

        Per ``rules/patterns.md`` § Async Resource Cleanup: emit warning,
        do nothing else. We do NOT call ``close_sync`` here — touching the
        BG loop / thread from a finalizer is the deadlock pattern that
        rule documents.
        """
        if not getattr(self, "_closed", True):
            try:
                _warnings.warn(
                    f"{type(self).__name__} not closed; call "
                    f"db.close()/await db.close_async() to stop the BG "
                    f"event loop thread cleanly.",
                    ResourceWarning,
                    stacklevel=2,
                )
            except Exception:
                # Finalizer must not raise. Hooks/cleanup carve-out per
                # rules/zero-tolerance.md Rule 3.
                pass
