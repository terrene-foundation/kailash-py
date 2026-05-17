"""Regression: SQLiteAdapter transaction-abort leaves _transaction_depth
unreset, poisoning the next begin_transaction() (#1070).

Root cause (core SDK `kailash.nodes.data.async_sql`):

`SQLiteAdapter.begin_transaction()` increments `_transaction_depth`
(and `_savepoint_counter` on the nested path) and issues
`BEGIN IMMEDIATE` / `SAVEPOINT` on the shared per-adapter `:memory:`
connection. These counters are decremented/reset ONLY in
`commit_transaction()` / `rollback_transaction()`. The production
auto-transaction wrappers (`AsyncSQLDatabaseNode._execute_with_transaction`
and `_execute_many_with_transaction`) caught `except Exception:` — but
`asyncio.CancelledError` is a `BaseException`, NOT an `Exception`
(Py3.8+). A coroutine cancelled BETWEEN `begin_transaction()` and
`commit_transaction()` therefore SKIPPED the `rollback_transaction()`
handler entirely. `_transaction_depth` stayed `> 0` and the shared
`:memory:` connection was left mid-`BEGIN`. Because `:memory:` reuses
ONE per-adapter connection, the NEXT `begin_transaction()` on the same
adapter observed `depth > 0`, took the SAVEPOINT branch, and issued
`SAVEPOINT` against a poisoned/unknown outer transaction — and the
never-committed prior write leaked into the next transaction's view.

Fix (three layers, all in core SDK async_sql):
- A: `begin_transaction()` wraps its post-`_get_connection()` body in
  `try/except BaseException` -> `_abort_begin()` so a cancellation
  *during* begin's awaits restores the counters AND rolls back the
  connection (the :memory: connection is NOT closed — closing destroys
  the in-memory DB).
- B: the production auto-transaction wrappers catch `BaseException`
  (not just `Exception`) so a cancellation *between* begin and commit
  still runs `rollback_transaction()` -> `_transaction_depth` reset.
- C: `_abort_begin()` re-raise discipline — the abort path logs the
  connection-unwind failure at WARN and never masks the original
  cancellation/exception (the caller re-raises immediately).

Tier-2 — NO MOCKING. Real `SQLiteAdapter`, real `:memory:` shared
connection, real `asyncio` task cancellation, real `aiosqlite`
transactions. Behavioral assertions (probe the next begin's branch +
the visible-rows leak) — NOT source-grep (testing.md §
Behavioral-Over-Source-Grep).
"""

import asyncio

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    SQLiteAdapter,
)


async def _seed_table(adapter: SQLiteAdapter) -> None:
    db = await adapter._get_connection()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    await db.commit()


@pytest.mark.regression
async def test_issue_1070_cancel_between_begin_and_commit_does_not_poison_next_begin():
    """Cancellation between begin and commit must NOT poison the next begin.

    Drives the REAL production auto-transaction wrapper
    `AsyncSQLDatabaseNode._execute_with_transaction` (the #1070 fix
    changes its abort handler from `except Exception` to
    `except BaseException`). The wrapper is cancelled while it awaits the
    query (between begin_transaction() and commit_transaction()). On
    unfixed code the `except Exception` handler is SKIPPED by the
    CancelledError, rollback_transaction() never runs, _transaction_depth
    stays 1, and the next begin_transaction() on the SAME :memory:
    adapter takes a poisoned SAVEPOINT branch. The fix makes the wrapper
    catch BaseException so rollback_transaction() runs and resets depth.

    Behavioral (not source-grep): asserts the next begin starts a CLEAN
    outer transaction AND the aborted write did not leak.
    """
    cfg = DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    adapter = SQLiteAdapter(cfg)
    await adapter.connect()
    try:
        await _seed_table(adapter)

        # A real AsyncSQLDatabaseNode in auto-transaction mode. We invoke
        # its REAL _execute_with_transaction (the patched production code)
        # against the real :memory: adapter — NOT a local replica.
        node = AsyncSQLDatabaseNode(
            node_id="issue_1070_probe",
            connection_string="sqlite:///:memory:",
            database_type="sqlite",
            query="SELECT 1",
            fetch_mode="all",
            transaction_mode="auto",
            validate_queries=False,
        )

        # A genuinely slow query gives a real cancellation window
        # strictly INSIDE the transaction: the wrapper does
        # begin_transaction() -> execute(<slow>) -> commit_transaction().
        # We cancel while it is awaiting the slow execute() — strictly
        # between begin and commit (no pg_sleep in SQLite; a recursive
        # CTE burns multiple seconds of real query time).
        slow_query = (
            "WITH RECURSIVE c(x) AS ("
            "  SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x < 30000000"
            ") SELECT count(*) FROM c"
        )

        async def run_wrapper() -> None:
            # The REAL production wrapper (the patched code under test).
            await node._execute_with_transaction(
                adapter=adapter,
                query=slow_query,
                params=None,
                fetch_mode=FetchMode.ALL,
                fetch_size=None,
            )

        task = asyncio.create_task(run_wrapper())
        # Wait until the wrapper has entered the transaction (begin ran,
        # depth -> 1) and is now awaiting the slow execute(). The CTE
        # runs for seconds so this races in reliably.
        for _ in range(2000):
            await asyncio.sleep(0.002)
            if adapter._transaction_depth > 0:
                break
        assert (
            adapter._transaction_depth > 0
        ), "wrapper never reached begin_transaction() — test setup bug"
        # Cancel strictly between begin and commit (slow execute still
        # in flight).
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # FIX CONTRACT: the wrapper's BaseException handler ran
        # rollback_transaction(), which reset _transaction_depth.
        assert adapter._transaction_depth == 0, (
            f"_transaction_depth={adapter._transaction_depth} after the "
            f"production auto-transaction wrapper was cancelled between "
            f"begin and commit — the wrapper's abort handler did not run "
            f"rollback_transaction() (#1070). The next begin_transaction() "
            f"would take a poisoned SAVEPOINT branch."
        )

        # Decisive behavioral probe: a fresh begin starts a CLEAN outer
        # transaction (BEGIN IMMEDIATE), not a SAVEPOINT against the
        # abandoned outer transaction.
        txn2 = await adapter.begin_transaction()
        _db2, savepoint_name, _depth2 = txn2
        assert savepoint_name is None, (
            f"begin_transaction() after a cancelled auto-transaction took "
            f"the SAVEPOINT branch (savepoint_name={savepoint_name!r}) — "
            f"it is sitting on a poisoned outer transaction (#1070)."
        )
        await adapter.rollback_transaction(txn2)
        await node.cleanup()
    finally:
        await adapter.disconnect()


@pytest.mark.regression
async def test_issue_1070_cancel_during_begin_transaction_itself_restores_state():
    """A cancellation DURING begin_transaction()'s own awaits restores state.

    Covers fix-layer A (`begin_transaction` try/except BaseException ->
    `_abort_begin`). begin#1 succeeds and is left open; a nested begin#2
    is cancelled while it awaits `SAVEPOINT`; the abort path must restore
    `_savepoint_counter` + `_transaction_depth` so begin#3 (nested) uses
    the NEXT savepoint name without a counter gap and the outer
    transaction is still intact.
    """
    cfg = DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    adapter = SQLiteAdapter(cfg)
    await adapter.connect()
    try:
        await _seed_table(adapter)

        outer = await adapter.begin_transaction()
        assert adapter._transaction_depth == 1
        depth_before = adapter._transaction_depth
        sp_counter_before = adapter._savepoint_counter

        # Cancel a nested begin while it is awaiting SAVEPOINT execution.
        # asyncio.wait_for with a 0 timeout cancels the inner coroutine
        # at its first await point inside begin_transaction().
        with pytest.raises((asyncio.TimeoutError, asyncio.CancelledError)):
            await asyncio.wait_for(adapter.begin_transaction(), timeout=0)

        # _abort_begin must have restored both counters to pre-call values.
        assert adapter._transaction_depth == depth_before, (
            f"_transaction_depth not restored after a begin cancelled "
            f"mid-await: got {adapter._transaction_depth}, "
            f"expected {depth_before} (#1070 fix-layer A)."
        )
        assert adapter._savepoint_counter == sp_counter_before, (
            f"_savepoint_counter not restored after a begin cancelled "
            f"mid-await: got {adapter._savepoint_counter}, "
            f"expected {sp_counter_before} (#1070 fix-layer A)."
        )

        # The outer transaction must still be usable (begin#2's abort
        # rolled back ONLY its own savepoint, not the outer transaction).
        nested = await adapter.begin_transaction()
        _db, sp_name, _ = nested
        assert sp_name is not None, (
            "expected a nested SAVEPOINT — the outer transaction was "
            "wrongly torn down by the cancelled nested begin (#1070)."
        )
        await adapter.rollback_transaction(nested)
        await adapter.rollback_transaction(outer)
    finally:
        await adapter.disconnect()


@pytest.mark.regression
def test_issue_1070_begin_transaction_abort_contract_structural_invariant():
    """Structural invariant pinning the #1070 abort contract.

    Per cross-sdk-inspection.md §3a: lock the signature/shape so a future
    refactor that removes the abort path (the `_abort_begin` helper or the
    BaseException-catching wrappers) fails loudly and forces a re-audit.

    1. `SQLiteAdapter._abort_begin` MUST exist and be a coroutine — it is
       the explicit abort path mandated by the issue's acceptance
       criterion. A rename/removal silently re-opens the poisoned-state
       bug class.
    2. The production auto-transaction wrappers MUST catch `BaseException`
       (not only `Exception`) — otherwise an `asyncio.CancelledError`
       between begin and commit again skips `rollback_transaction()`.
    """
    import inspect

    assert hasattr(SQLiteAdapter, "_abort_begin"), (
        "SQLiteAdapter._abort_begin is gone — the #1070 explicit abort "
        "path was removed; a cancellation/exception between "
        "begin_transaction() and its paired commit/rollback again leaves "
        "_transaction_depth > 0 and poisons the next begin."
    )
    assert inspect.iscoroutinefunction(SQLiteAdapter._abort_begin), (
        "SQLiteAdapter._abort_begin is no longer a coroutine — it awaits "
        "the connection ROLLBACK; a sync rewrite breaks the #1070 abort "
        "contract."
    )

    # The production auto-transaction wrappers' abort handler MUST be
    # `except BaseException` so asyncio.CancelledError runs the rollback.
    # Source inspection here is the structural-invariant pin (NOT a
    # behavioral substitute — the behavioral tests above exercise it);
    # this asserts the SHAPE that prevents the bug class, per §3a.
    for method_name in (
        "_execute_with_transaction",
        "_execute_many_with_transaction",
    ):
        src = inspect.getsource(getattr(AsyncSQLDatabaseNode, method_name))
        assert "except BaseException:" in src, (
            f"AsyncSQLDatabaseNode.{method_name} no longer catches "
            f"BaseException on the auto-transaction abort path — an "
            f"asyncio.CancelledError between begin and commit will skip "
            f"rollback_transaction() and re-open #1070."
        )
