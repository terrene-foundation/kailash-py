"""Regression test for issue #1580 — core adapters expose a uniform
``transaction()`` async-context-manager contract.

Root cause (issue #1580, cluster B): the DataFlow transaction nodes
(``TransactionScopeNode`` / ``TransactionCommitNode`` / ``TransactionRollbackNode``
and the savepoint nodes) resolve their adapter via
``DataFlow._get_or_create_async_sql_node(db_type)._get_adapter()`` (the #835
per-loop priority chain) and call ``adapter.transaction()`` — an async context
manager yielding a scope with ``.connection`` / ``.commit()`` / ``.rollback()``.
The *DataFlow* adapters (``dataflow.adapters.*``) expose ``transaction()``, but
the *core* adapters (``kailash.nodes.data.async_sql`` — the classes the #835
resolution path actually returns) exposed only ``begin_transaction()`` /
``commit_transaction()`` / ``rollback_transaction()``. The mismatch surfaced as
``AttributeError: 'ProductionPostgreSQLAdapter' object has no attribute
'transaction'`` on every transaction-node workflow.

The fix adds a single concrete ``transaction()`` on the base ``DatabaseAdapter``
that wraps the existing ``begin/commit/rollback_transaction`` primitives, so
every core adapter inherits the uniform contract.

These tests pin BOTH halves:

* the STRUCTURAL invariant — ``transaction()`` exists on the base and every
  concrete core adapter and returns an async context manager. If a future
  refactor removes it (re-opening #1580), this fails loudly at Tier 1 with no
  database required.
* the BEHAVIORAL contract — against real PostgreSQL, a committed
  ``adapter.transaction()`` block persists its writes and a rolled-back /
  exception-unwound block discards them, and the yielded scope exposes a live
  ``.connection``.
"""

import os
import tempfile
import uuid

import pytest

from kailash.nodes.data.async_sql import (
    _AdapterTransactionContext,
    AsyncSQLDatabaseNode,
    DatabaseAdapter,
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    MySQLAdapter,
    PostgreSQLAdapter,
    ProductionMySQLAdapter,
    ProductionPostgreSQLAdapter,
    ProductionSQLiteAdapter,
    SQLiteAdapter,
)

from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Tier 1 — structural invariant (no database)
# ---------------------------------------------------------------------------

_CORE_ADAPTER_CLASSES = [
    PostgreSQLAdapter,
    MySQLAdapter,
    SQLiteAdapter,
    ProductionPostgreSQLAdapter,
    ProductionMySQLAdapter,
    ProductionSQLiteAdapter,
]


def test_base_adapter_declares_transaction():
    """The uniform ``transaction()`` contract lives on the base class."""
    assert hasattr(DatabaseAdapter, "transaction")
    assert callable(DatabaseAdapter.transaction)


@pytest.mark.parametrize("adapter_cls", _CORE_ADAPTER_CLASSES)
def test_core_adapter_inherits_transaction(adapter_cls):
    """Every concrete core adapter inherits the single base ``transaction()``.

    Pins issue #1580: the #835 resolution path returns these classes, and the
    transaction nodes call ``.transaction()`` on the result. If any concrete
    adapter stops resolving ``transaction`` to the base implementation, the
    #1580 AttributeError is back.
    """
    assert hasattr(adapter_cls, "transaction")
    # Resolves to the ONE base implementation — not a per-adapter divergence.
    assert adapter_cls.transaction is DatabaseAdapter.transaction


def test_transaction_returns_async_context_manager():
    """``transaction()`` returns an async context manager (has __aenter__/__aexit__).

    Uses a config with no live pool — we never enter the context here, only
    assert the returned object's shape, so no database is required.
    """
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string="postgresql://unused:unused@localhost:5432/unused",
    )
    adapter = ProductionPostgreSQLAdapter(config)
    ctx = adapter.transaction()
    assert hasattr(ctx, "__aenter__")
    assert hasattr(ctx, "__aexit__")


# ---------------------------------------------------------------------------
# Tier 2 — behavioral contract against real PostgreSQL
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def pg_adapter(test_suite):
    """A connected core ProductionPostgreSQLAdapter against the shared test PG."""
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string=test_suite.config.url,
    )
    adapter = ProductionPostgreSQLAdapter(config)
    await adapter.connect()
    try:
        yield adapter
    finally:
        await adapter.disconnect()


@pytest.mark.integration
async def test_transaction_commit_persists(test_suite, pg_adapter):
    """A committed ``adapter.transaction()`` block persists its writes."""
    table = f"t1580_commit_{uuid.uuid4().hex[:8]}"
    async with test_suite.get_connection() as conn:
        await conn.execute(
            f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, note TEXT)'
        )
    try:
        async with pg_adapter.transaction() as txn:
            # The scope exposes a live connection (the savepoint nodes rely on this).
            assert txn.connection is not None
            await txn.connection.execute(
                f'INSERT INTO "{table}" (id, note) VALUES ($1, $2)', 1, "committed"
            )
            await txn.commit()

        async with test_suite.get_connection() as conn:
            rows = await conn.fetch(f'SELECT note FROM "{table}" WHERE id = 1')
        assert len(rows) == 1
        assert rows[0]["note"] == "committed"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}"')


@pytest.mark.integration
async def test_transaction_explicit_rollback_discards(test_suite, pg_adapter):
    """An explicitly rolled-back ``adapter.transaction()`` block discards writes."""
    table = f"t1580_rollback_{uuid.uuid4().hex[:8]}"
    async with test_suite.get_connection() as conn:
        await conn.execute(
            f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, note TEXT)'
        )
    try:
        async with pg_adapter.transaction() as txn:
            await txn.connection.execute(
                f'INSERT INTO "{table}" (id, note) VALUES ($1, $2)', 1, "rolled_back"
            )
            await txn.rollback()

        async with test_suite.get_connection() as conn:
            rows = await conn.fetch(f'SELECT note FROM "{table}" WHERE id = 1')
        assert len(rows) == 0
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}"')


@pytest.mark.integration
async def test_transaction_exception_unwind_rolls_back(test_suite, pg_adapter):
    """An exception propagating out of the block rolls the transaction back."""
    table = f"t1580_exc_{uuid.uuid4().hex[:8]}"
    async with test_suite.get_connection() as conn:
        await conn.execute(
            f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, note TEXT)'
        )
    try:
        with pytest.raises(RuntimeError, match="boom"):
            async with pg_adapter.transaction() as txn:
                await txn.connection.execute(
                    f'INSERT INTO "{table}" (id, note) VALUES ($1, $2)', 1, "doomed"
                )
                raise RuntimeError("boom")  # __aexit__ MUST roll back

        async with test_suite.get_connection() as conn:
            rows = await conn.fetch(f'SELECT note FROM "{table}" WHERE id = 1')
        assert len(rows) == 0
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}"')


class _BoomTransaction:
    """A stand-in transaction object whose commit/rollback raise — a boundary
    injection (NOT a mock of the DB/pool) exercising the primitive's cleanup path
    per user-flow-validation MUST-7(b). The real pooled connection + real pool are
    still used; only the driver commit/rollback is forced to fail.
    """

    async def commit(self):
        raise RuntimeError("driver commit boom")

    async def rollback(self):
        raise RuntimeError("driver rollback boom")


class _CountingPool:
    """Proxy over the adapter's real connection pool that counts ``release``
    calls while delegating every operation to the real pool. asyncpg's
    ``Pool.release`` is a read-only attribute, so we swap the adapter's writable
    ``_pool`` reference for this proxy rather than patching the method. NOT a mock
    — acquire and release execute the real pool's behavior."""

    def __init__(self, real):
        self._real = real
        self.releases = []

    async def acquire(self, *args, **kwargs):
        return await self._real.acquire(*args, **kwargs)

    async def release(self, conn, *args, **kwargs):
        self.releases.append(conn)
        return await self._real.release(conn, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.mark.integration
async def test_commit_then_context_exit_releases_connection_once(
    test_suite, pg_adapter
):
    """Redteam MEDIUM-1: an explicit ``scope.commit()`` followed by the context
    manager's ``__aexit__`` (the consumer-node pattern) releases the pooled
    connection EXACTLY once — the single-shot guard prevents a double-release."""
    real_pool = pg_adapter._pool
    counting = _CountingPool(real_pool)
    pg_adapter._pool = counting
    try:
        ctx = pg_adapter.transaction()
        scope = await ctx.__aenter__()
        await scope.commit()  # release #1
        await ctx.__aexit__(None, None, None)  # guarded — MUST NOT release again
        assert len(counting.releases) == 1
    finally:
        pg_adapter._pool = real_pool


@pytest.mark.integration
async def test_commit_failure_still_releases_connection(test_suite, pg_adapter):
    """Redteam security-MEDIUM: if the driver commit raises, the pooled connection
    is STILL returned to the bounded pool (try/finally in commit_transaction) —
    otherwise repeated commit failures drain the pool (DoS)."""
    real_pool = pg_adapter._pool
    counting = _CountingPool(real_pool)
    pg_adapter._pool = counting
    try:
        conn = await pg_adapter._pool.acquire()  # real pooled connection
        with pytest.raises(RuntimeError, match="driver commit boom"):
            await pg_adapter.commit_transaction((conn, _BoomTransaction()))
        assert counting.releases == [conn]  # released despite the commit failure
    finally:
        pg_adapter._pool = real_pool


@pytest.mark.integration
async def test_rollback_failure_still_releases_connection(test_suite, pg_adapter):
    """Sibling of the commit-failure case for the rollback primitive."""
    real_pool = pg_adapter._pool
    counting = _CountingPool(real_pool)
    pg_adapter._pool = counting
    try:
        conn = await pg_adapter._pool.acquire()
        with pytest.raises(RuntimeError, match="driver rollback boom"):
            await pg_adapter.rollback_transaction((conn, _BoomTransaction()))
        assert counting.releases == [conn]
    finally:
        pg_adapter._pool = real_pool


# ---------------------------------------------------------------------------
# Tier 2 — behavioral contract against SQLite (the default store; the most
# complex transaction primitive: (conn, savepoint, depth) tuple + nesting)
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db_path():
    fd, path = tempfile.mkstemp(suffix="_t1580.db")
    os.close(fd)
    os.unlink(path)  # let SQLite create it fresh on first connect
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
async def sqlite_adapter(sqlite_db_path):
    config = DatabaseConfig(type=DatabaseType.SQLITE, database=sqlite_db_path)
    adapter = SQLiteAdapter(config)
    await adapter.connect()
    await adapter.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, note TEXT)")
    try:
        yield adapter
    finally:
        await adapter.disconnect()


async def _sqlite_note(adapter, row_id):
    result = await adapter.execute("SELECT note FROM t WHERE id = ?", (row_id,))
    return result["data"] if isinstance(result, dict) else result


@pytest.mark.integration
async def test_sqlite_transaction_commit_persists(sqlite_adapter):
    async with sqlite_adapter.transaction() as txn:
        assert txn.connection is not None
        await txn.connection.execute("INSERT INTO t (id, note) VALUES (1, 'committed')")
        await txn.commit()
    rows = await _sqlite_note(sqlite_adapter, 1)
    assert len(rows) == 1
    assert rows[0]["note"] == "committed"


@pytest.mark.integration
async def test_sqlite_transaction_explicit_rollback_discards(sqlite_adapter):
    async with sqlite_adapter.transaction() as txn:
        await txn.connection.execute(
            "INSERT INTO t (id, note) VALUES (1, 'rolled_back')"
        )
        await txn.rollback()
    rows = await _sqlite_note(sqlite_adapter, 1)
    assert len(rows) == 0


@pytest.mark.integration
async def test_sqlite_transaction_exception_unwind_rolls_back(sqlite_adapter):
    with pytest.raises(RuntimeError, match="boom"):
        async with sqlite_adapter.transaction() as txn:
            await txn.connection.execute(
                "INSERT INTO t (id, note) VALUES (1, 'doomed')"
            )
            raise RuntimeError("boom")
    rows = await _sqlite_note(sqlite_adapter, 1)
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# Tier 1 — __aexit__ must not mask the original body exception (redteam MEDIUM-2)
# ---------------------------------------------------------------------------


class _FailingScope:
    """A scope whose commit/rollback both raise — to drive the __aexit__ cleanup
    path without a database."""

    async def commit(self):
        raise RuntimeError("cleanup commit failure")

    async def rollback(self):
        raise RuntimeError("cleanup rollback failure")


class _HarnessContext(_AdapterTransactionContext):
    """Drives the REAL ``_AdapterTransactionContext.__aexit__`` via a genuine
    ``async with`` (so the original-exception re-raise machinery runs) while
    yielding a DB-free failing scope from ``__aenter__``."""

    def __init__(self, scope):
        self._adapter = None
        self._scope = scope

    async def __aenter__(self):
        return self._scope


async def test_aexit_preserves_original_exception_when_rollback_fails():
    """MEDIUM-2: when the body raises AND the rollback also raises, __aexit__ must
    let the ORIGINAL body exception propagate — never mask it with the cleanup
    error."""
    with pytest.raises(ValueError, match="original body error"):
        async with _HarnessContext(_FailingScope()):
            raise ValueError("original body error")


async def test_aexit_surfaces_commit_failure_on_clean_body():
    """MEDIUM-2: on a clean body exit, a commit failure IS the error the caller
    must see — __aexit__ re-raises it rather than swallowing."""
    with pytest.raises(RuntimeError, match="cleanup commit failure"):
        async with _HarnessContext(_FailingScope()):
            pass


# ---------------------------------------------------------------------------
# Round 2 — begin-transaction acquire->start orphan window (redteam security-MEDIUM)
# ---------------------------------------------------------------------------


class _BeginBoomTransaction:
    """A transaction object whose start() raises — boundary injection for the
    begin_transaction failure path."""

    async def start(self):
        raise RuntimeError("driver begin boom")


class _BeginBoomConnection:
    """Stand-in pooled connection whose transaction().start() raises."""

    def transaction(self, *args, **kwargs):
        return _BeginBoomTransaction()


class _BeginBoomPool:
    """Minimal pool whose acquire() hands out a connection that fails to start a
    transaction; release() records the returned connection. Boundary injection
    for begin_transaction's acquire->start orphan window — no database needed."""

    def __init__(self):
        self.releases = []
        self.handed = None

    async def acquire(self, *args, **kwargs):
        self.handed = _BeginBoomConnection()
        return self.handed

    async def release(self, conn, *args, **kwargs):
        self.releases.append(conn)


async def test_pg_begin_failure_releases_connection():
    """Redteam security-MEDIUM (round 2): if the driver transaction start raises,
    PostgreSQLAdapter.begin_transaction returns the acquired pooled connection to
    the pool — otherwise a repeated BEGIN-failure workload orphans connections and
    drains the bounded pool (the begin half of the acquire->teardown window that
    commit_transaction / rollback_transaction guard on the other side)."""
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        connection_string="postgresql://unused:unused@localhost:5432/unused",
    )
    adapter = ProductionPostgreSQLAdapter(config)
    pool = _BeginBoomPool()
    adapter._pool = pool
    with pytest.raises(RuntimeError, match="driver begin boom"):
        await adapter.begin_transaction()
    # Released despite the begin failure — the connection is not orphaned.
    assert pool.releases == [pool.handed]


async def test_mysql_begin_failure_releases_connection():
    """MySQL sibling of the begin-failure release guarantee. MySQL begins via
    ``conn.begin()`` (no separate transaction object), so the stand-in connection
    raises there."""

    class _MySQLBeginBoomConn:
        async def begin(self):
            raise RuntimeError("driver begin boom")

    class _MySQLBeginBoomPool(_BeginBoomPool):
        async def acquire(self, *args, **kwargs):
            self.handed = _MySQLBeginBoomConn()
            return self.handed

    config = DatabaseConfig(
        type=DatabaseType.MYSQL,
        connection_string="mysql://unused:unused@localhost:3306/unused",
    )
    adapter = ProductionMySQLAdapter(config)
    pool = _MySQLBeginBoomPool()
    adapter._pool = pool
    with pytest.raises(RuntimeError, match="driver begin boom"):
        await adapter.begin_transaction()
    assert pool.releases == [pool.handed]


# ---------------------------------------------------------------------------
# Round 2 — auto-transaction caller invokes EXACTLY ONE terminal primitive
# (redteam HIGH: a failed commit must NOT be followed by rollback_transaction,
#  which would double-release the pooled connection / double-decrement depth)
# ---------------------------------------------------------------------------


class _RecordingAdapter:
    """Records begin/execute/commit/rollback calls so a test can assert the
    auto-transaction caller invokes exactly ONE terminal primitive per
    transaction. Boundary injection over the caller's control flow — NOT a
    database mock (no I/O, deterministic)."""

    def __init__(self, *, commit_raises: bool = False, execute_raises: bool = False):
        self.calls: list[str] = []
        self._commit_raises = commit_raises
        self._execute_raises = execute_raises

    async def begin_transaction(self):
        self.calls.append("begin")
        return ("conn", "tx")

    async def execute(self, **kwargs):
        self.calls.append("execute")
        if self._execute_raises:
            raise RuntimeError("driver execute boom")
        return {"data": []}

    async def execute_many(self, *args, **kwargs):
        self.calls.append("execute_many")
        if self._execute_raises:
            raise RuntimeError("driver execute boom")

    async def commit_transaction(self, transaction):
        self.calls.append("commit")
        if self._commit_raises:
            raise RuntimeError("driver commit boom")

    async def rollback_transaction(self, transaction):
        self.calls.append("rollback")


class _AutoTxNode:
    """Minimal stand-in exposing only the two attributes the
    _execute(_many)_with_transaction methods read from ``self`` — lets us drive
    the REAL unbound method (its exact control flow) without constructing a full
    AsyncSQLDatabaseNode."""

    _active_transaction = None
    _transaction_mode = "auto"


async def test_auto_execute_commit_failure_invokes_no_rollback():
    """Redteam HIGH: in auto mode a COMMIT failure must NOT be followed by
    rollback_transaction. commit_transaction self-releases the pooled connection
    (#1580), so a following rollback would double-release it / double-decrement
    the SQLite depth. Assert exactly one terminal primitive (commit) runs and the
    ORIGINAL commit error propagates."""
    adapter = _RecordingAdapter(commit_raises=True)
    with pytest.raises(RuntimeError, match="driver commit boom"):
        await AsyncSQLDatabaseNode._execute_with_transaction(
            _AutoTxNode(), adapter, "SELECT 1", None, FetchMode.ALL, None
        )
    assert adapter.calls == ["begin", "execute", "commit"]
    assert "rollback" not in adapter.calls


async def test_auto_execute_body_failure_invokes_rollback_not_commit():
    """Complement: an EXECUTE (body) failure DOES roll back — and only rolls back,
    never commits — preserving the #1070 cancellation-safety contract (rollback on
    a cancelled/failed body resets _transaction_depth)."""
    adapter = _RecordingAdapter(execute_raises=True)
    with pytest.raises(RuntimeError, match="driver execute boom"):
        await AsyncSQLDatabaseNode._execute_with_transaction(
            _AutoTxNode(), adapter, "SELECT 1", None, FetchMode.ALL, None
        )
    assert adapter.calls == ["begin", "execute", "rollback"]
    assert "commit" not in adapter.calls


async def test_auto_execute_success_commits_only():
    """The clean path commits exactly once and never rolls back."""
    adapter = _RecordingAdapter()
    result = await AsyncSQLDatabaseNode._execute_with_transaction(
        _AutoTxNode(), adapter, "SELECT 1", None, FetchMode.ALL, None
    )
    assert result == {"data": []}
    assert adapter.calls == ["begin", "execute", "commit"]


async def test_auto_execute_many_commit_failure_invokes_no_rollback():
    """execute_many sibling of the commit-failure single-terminal assertion."""
    adapter = _RecordingAdapter(commit_raises=True)
    with pytest.raises(RuntimeError, match="driver commit boom"):
        await AsyncSQLDatabaseNode._execute_many_with_transaction(
            _AutoTxNode(), adapter, "INSERT INTO t VALUES (?)", [(1,)]
        )
    assert adapter.calls == ["begin", "execute_many", "commit"]
    assert "rollback" not in adapter.calls


# ---------------------------------------------------------------------------
# Round 2 — SQLite commit/rollback failure still resets _transaction_depth
# (redteam HIGH SQLite half: a failed commit must not leave depth > 0 and poison
#  the next begin_transaction — #1070 class)
# ---------------------------------------------------------------------------


class _SQLiteBoomConn:
    """Stand-in aiosqlite connection whose commit()/rollback() raise — boundary
    injection for the SQLite commit_transaction failure path. execute()/close()
    are no-ops so the cleanup-rollback + close paths run without a database."""

    def __init__(self):
        self.calls: list[str] = []

    async def commit(self):
        self.calls.append("commit")
        raise RuntimeError("sqlite commit boom")

    async def rollback(self):
        self.calls.append("rollback")

    async def execute(self, *args, **kwargs):
        self.calls.append("execute")

    async def close(self):
        self.calls.append("close")


async def test_sqlite_commit_failure_decrements_depth_and_rolls_back(sqlite_adapter):
    """Redteam HIGH (SQLite half): SQLiteAdapter.commit_transaction decrements
    _transaction_depth in its finally even when db.commit() raises, and rolls the
    transaction back so a shared connection is not left mid-transaction — the
    ORIGINAL commit error propagates (the cleanup rollback does not mask it)."""
    sqlite_adapter._transaction_depth = 1
    boom = _SQLiteBoomConn()
    with pytest.raises(RuntimeError, match="sqlite commit boom"):
        # (connection, savepoint_name=None -> outer transaction, depth)
        await sqlite_adapter.commit_transaction((boom, None, 1))
    # Depth decremented despite the failure (finally ran) — next begin is not poisoned.
    assert sqlite_adapter._transaction_depth == 0
    # The failed commit triggered a rollback of the SQLite transaction.
    assert "rollback" in boom.calls


async def test_sqlite_rollback_failure_still_decrements_depth(sqlite_adapter):
    """Sibling: rollback_transaction decrements depth in its finally even when the
    driver rollback raises, so a failed rollback does not poison the next begin."""

    class _RollbackBoomConn:
        async def rollback(self):
            raise RuntimeError("sqlite rollback boom")

        async def close(self):
            pass

    sqlite_adapter._transaction_depth = 1
    with pytest.raises(RuntimeError, match="sqlite rollback boom"):
        await sqlite_adapter.rollback_transaction((_RollbackBoomConn(), None, 1))
    assert sqlite_adapter._transaction_depth == 0


async def test_sqlite_commit_failure_close_error_does_not_mask_original(sqlite_adapter):
    """Redteam round-3 LOW: if db.close() in the terminal finally ALSO raises, it
    must NOT replace the ORIGINAL driver commit error the caller keys a retry on —
    _close_quietly logs the close error and never raises. Depth is still reset
    (the decrement precedes the close), so the next begin is not poisoned."""

    class _CloseBoomConn(_SQLiteBoomConn):
        async def close(self):
            self.calls.append("close")
            raise RuntimeError("sqlite close boom")

    sqlite_adapter._transaction_depth = 1  # file-DB adapter -> depth-0 close fires
    boom = _CloseBoomConn()
    # The original commit error surfaces, NOT "sqlite close boom".
    with pytest.raises(RuntimeError, match="sqlite commit boom"):
        await sqlite_adapter.commit_transaction((boom, None, 1))
    assert sqlite_adapter._transaction_depth == 0
    assert (
        "close" in boom.calls
    )  # the close was attempted (and its error swallowed+logged)
