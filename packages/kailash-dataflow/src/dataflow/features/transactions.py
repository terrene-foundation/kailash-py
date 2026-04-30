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
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Iterator,
    List,
    Optional,
)

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


# ============================================================================
# Sync surface — ``db.transactions_sync.begin()`` (issue #711)
# ============================================================================

# Sentinel placed in the sync scope when the ``with`` block has exited. Any
# subsequent ``tx.execute_raw`` call MUST raise ``RuntimeError`` per
# ``rules/zero-tolerance.md`` Rule 3a (typed delegate guard) — the pinned
# connection only exists while the scope is active.
_SCOPE_INACTIVE = object()


class SyncTransactionScope:
    """Sync analogue of :class:`TransactionScope`.

    Yielded by :func:`SyncTransactionManager.begin`. Holds a reference to the
    underlying async :class:`TransactionScope` and the BG-loop submitter so
    ``tx.execute_raw(sql, params)`` can invoke the async ``execute_raw`` from
    sync code without the caller awaiting anything.

    The scope is single-use — exiting the ``with`` block sets ``_async_scope``
    to ``_SCOPE_INACTIVE`` so any further ``execute_raw`` calls raise the
    typed-guard ``RuntimeError`` instead of silently re-using a connection
    that has been returned to the pool.

    Mirrors the async ``TransactionScope`` metadata surface (id,
    isolation_level, status, type) for parity with the async API; the
    backward-compat dict ``__getitem__`` / ``__setitem__`` from the async
    scope is intentionally NOT mirrored — sync callers landed in 0.x with
    the canonical attribute access only.
    """

    __slots__ = ("_async_scope", "_run_sync")

    def __init__(self, async_scope: TransactionScope, run_sync: Any) -> None:
        # ``run_sync`` is a callable: ``run_sync(coro) -> result``. It submits
        # the coroutine to the manager's BG event loop and blocks for the
        # result. Stored on the scope so it survives the ``with`` body even
        # when the manager is closed mid-call (rare).
        self._async_scope: Any = async_scope
        self._run_sync = run_sync

    # --- Metadata mirror of the async scope (read-only attribute proxies) ---

    @property
    def id(self) -> str:
        return self._guarded_async_scope().id

    @property
    def isolation_level(self) -> str:
        return self._guarded_async_scope().isolation_level

    @property
    def status(self) -> str:
        return self._guarded_async_scope().status

    @property
    def type(self) -> str:
        return self._guarded_async_scope().type

    @property
    def depth(self) -> Optional[int]:
        return self._guarded_async_scope().depth

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
            Same return shape as :meth:`TransactionScope.execute_raw` — the
            sync wrapper does not transform the result.
        """
        async_scope = self._guarded_async_scope()
        return self._run_sync(async_scope.execute_raw(sql, params))

    # --- Internal: typed guard for out-of-scope access ---

    def _guarded_async_scope(self) -> TransactionScope:
        if self._async_scope is _SCOPE_INACTIVE:
            raise RuntimeError(
                "SyncTransactionScope.execute_raw called outside the "
                "transaction body — ensure the call is inside the "
                "`with db.transactions_sync.begin()` scope. "
                "The pinned connection is only valid while the scope is "
                "active."
            )
        return self._async_scope  # type: ignore[return-value]

    def _mark_inactive(self) -> None:
        """Called by the manager when the ``with`` block exits.

        Replaces the async-scope reference with the inactive sentinel so the
        guarded accessor raises a typed error rather than silently re-using
        a connection that has been returned to the pool.
        """
        self._async_scope = _SCOPE_INACTIVE


class SyncTransactionManager:
    """Sync surface for :class:`TransactionManager` (issue #711).

    Mirror of :func:`TransactionManager.begin` for sync callers. Owns a
    persistent daemon-thread event loop and submits every coroutine to it
    via ``asyncio.run_coroutine_threadsafe`` — the same pattern
    :class:`SyncExpress` uses. One BG loop is shared across all
    ``begin()`` calls so the pinned connection survives across multiple
    ``tx.execute_raw`` invocations inside one ``with`` block.

    Cross-context safe — the BG loop thread is independent of any host
    event loop. The surface works inside pytest-asyncio, Nexus handlers,
    and Jupyter cells without raising
    ``RuntimeError: This event loop is already running``.

    Lifecycle::

        # Construction (lazy at db.transactions_sync first access):
        sync_mgr = SyncTransactionManager(async_mgr)

        # Use:
        with sync_mgr.begin() as tx:
            existing = tx.execute_raw(
                "SELECT id FROM oauth_tokens WHERE user_id = %s FOR UPDATE",
                [user_id],
            )
            if existing:
                tx.execute_raw(
                    "UPDATE oauth_tokens SET refresh_token = %s "
                    "WHERE user_id = %s",
                    [new_refresh, user_id],
                )

        # Teardown (wired into DataFlow.close() / close_async()):
        sync_mgr.close_sync()
    """

    def __init__(self, transactions: TransactionManager) -> None:
        # Reference to the async manager — every ``begin()`` call delegates
        # to the async ``begin()`` context manager so the sync surface
        # cannot drift from the async semantics (single source of truth).
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
        # The async ``begin()`` is itself an ``@asynccontextmanager`` — we
        # cannot directly enter it from sync code, so we drive it manually
        # via ``__aenter__`` / ``__aexit__`` on the BG loop. This preserves
        # the async manager's commit-on-clean-exit / rollback-on-exception
        # semantics WITHOUT duplicating the SQL or the ContextVar wiring.
        async_cm = self._transactions.begin(isolation_level)

        # Enter the async context manager on the BG loop. The pinned
        # connection (set in `_active_transaction` ContextVar) becomes
        # visible to every subsequent ``execute_raw`` submitted to the
        # same loop.
        async_scope = self._run_sync(async_cm.__aenter__())
        sync_scope = SyncTransactionScope(async_scope, self._run_sync)

        try:
            yield sync_scope
        except BaseException:
            # Propagate the exception type/value/tb to the async CM so it
            # rolls back. Use ``sys.exc_info()`` shape via a wrapper coro
            # — the async CM expects ``(exc_type, exc_val, exc_tb)``.
            import sys

            exc_type, exc_val, exc_tb = sys.exc_info()
            try:
                # Returns True iff the async CM swallowed the exception.
                # ``TransactionManager.begin`` re-raises after rollback so
                # we expect this to return False; we re-raise either way to
                # preserve the original traceback chain.
                self._run_sync(async_cm.__aexit__(exc_type, exc_val, exc_tb))
            except BaseException:
                # The async CM may itself raise during rollback — surface
                # that to the caller. Either way, mark the scope inactive
                # so any post-with ``execute_raw`` raises the typed guard.
                sync_scope._mark_inactive()
                raise
            sync_scope._mark_inactive()
            raise
        else:
            # Clean-exit: drive the async CM exit, then mark the scope
            # inactive so post-with ``execute_raw`` calls raise the typed
            # guard (rules/zero-tolerance.md Rule 3a).
            self._run_sync(async_cm.__aexit__(None, None, None))
            sync_scope._mark_inactive()

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
