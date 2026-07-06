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
    DatabaseAdapter,
    DatabaseConfig,
    DatabaseType,
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
