# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for issue #707 — `db.transactions.begin()` MUST pin one
connection across all `tx.execute_raw` calls, auto-commit on clean exit,
auto-rollback on exception. Tier 2 (real PostgreSQL).

The yielded `TransactionScope` exposes `execute_raw(sql, params=None)` so
consumers can express multi-statement atomic patterns (DDL inside a tx,
SELECT FOR UPDATE + INSERT, complex UPSERT-or-UPDATE) the Express API
does not express directly. Calling `tx.execute_raw` outside the
`async with` body raises `RuntimeError` per `rules/zero-tolerance.md`
Rule 3a (typed delegate guard).

Per `rules/testing.md` § "3-Tier Testing" Tier 2: NO mocking. Every
test runs against the real PostgreSQL test instance via the
`test_suite` fixture from `tests/integration/conftest.py`.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from dataflow import DataFlow
from dataflow.features.transactions import TransactionScope
from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.regression, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Local fixtures — `test_suite` lives in tests/integration/conftest.py and
# is not auto-discovered for tests/regression/. Define a regression-scope
# copy that uses the same IntegrationTestSuite harness against real Postgres.
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg_test_suite():
    """Create the IntegrationTestSuite once per regression test (real Postgres).

    Skips the test cleanly when PostgreSQL on port 5434 is not reachable —
    matches the integration-tier behavior where the test suite is the
    canonical real-infra harness.
    """
    suite = IntegrationTestSuite()
    try:
        async with suite.session():
            yield suite
    except Exception as exc:
        pytest.skip(
            f"Cannot reach PostgreSQL test infra: {type(exc).__name__}: {exc}. "
            f"Ensure shared SDK Docker is running on port 5434."
        )


@pytest.fixture
async def temp_table_name():
    """Unique temp table name per test for isolation."""
    return f"tx_707_{int(time.time() * 1_000_000)}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def temp_table(pg_test_suite, temp_table_name):
    """Create + drop a clean test table for each test.

    The CREATE / DROP DDL runs OUTSIDE any DataFlow transaction (the
    test is exercising the transaction surface against pre-existing
    tables). Cleanup uses a fresh connection to guarantee teardown
    even when the test transaction was rolled back.
    """
    create_sql = f"""
        CREATE TABLE {temp_table_name} (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            payload TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    async with pg_test_suite.get_connection() as conn:
        await conn.execute(create_sql)

    yield temp_table_name

    async with pg_test_suite.get_connection() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {temp_table_name} CASCADE")


@pytest.fixture
async def df(pg_test_suite):
    """A DataFlow against the real Postgres infra; closed on teardown.

    NOTE: ``await instance.initialize()`` is required for the DataFlow
    connection adapter to be created on the host event loop. Without
    it, ``TransactionManager._get_adapter()`` returns None and
    ``db.transactions.begin()`` raises "no database connection
    available" before reaching the BEGIN statement. This is the
    pre-existing bug Issue #711 surfaced when the sync fixture was
    derived from this one — applied here too for symmetry per
    rules/zero-tolerance.md Rule 1 (fix-immediately, same bug class).
    """
    instance = DataFlow(database_url=pg_test_suite.config.url, auto_migrate=False)
    await instance.initialize()
    try:
        yield instance
    finally:
        # Explicit close per rules/testing.md § "Fixtures Yield + Cleanup"
        # — avoids the GC-finalizer deadlock the __del__ rule warns about.
        try:
            await instance.close_async()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tier 2 regression coverage
# ---------------------------------------------------------------------------


async def _count_rows(pg_test_suite, table: str) -> int:
    """Verify-via-readback per rules/testing.md § State Persistence Verification.

    Uses a FRESH connection from the integration test suite — outside any
    DataFlow transaction. This proves the transaction's commit/rollback
    actually persisted to the database, not just to the pinned connection.
    """
    async with pg_test_suite.get_connection() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table}")


async def test_multi_statement_atomicity_via_tx_execute_raw(
    df, pg_test_suite, temp_table
):
    """Issue #707 canonical: BEGIN-INSERT-INSERT-COMMIT all via tx.execute_raw.

    Asserts both rows are visible after commit when read back from a fresh
    connection — proves the COMMIT actually persisted state to the database.
    """
    async with df.transactions.begin() as tx:
        assert isinstance(tx, TransactionScope), (
            f"transactions.begin() yielded {type(tx).__name__}, expected "
            "TransactionScope (issue #707 contract)"
        )
        assert tx.status == "active"

        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["alice@example.test", "row-1"],
        )
        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["bob@example.test", "row-2"],
        )
        # Read-within-transaction: the pinned connection sees its own writes.
        in_tx_rows = await tx.execute_raw(
            f"SELECT email FROM {temp_table} ORDER BY email"
        )
        assert len(in_tx_rows) == 2
        assert {dict(r)["email"] for r in in_tx_rows} == {
            "alice@example.test",
            "bob@example.test",
        }

    # Read-back via a DIFFERENT connection — proves COMMIT happened.
    assert await _count_rows(pg_test_suite, temp_table) == 2


async def test_auto_rollback_on_exception(df, pg_test_suite, temp_table):
    """Exceptions inside the `async with` body MUST roll back the entire txn.

    Insert one row, raise, then read back from a FRESH connection — zero
    rows MUST persist. This is the load-bearing invariant for the OAuth
    credential rotation pattern (failure mid-rotation MUST NOT leave a
    partially-written token row).
    """
    with pytest.raises(RuntimeError, match="forced rollback"):
        async with df.transactions.begin() as tx:
            await tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                ["alice@example.test", "should-not-persist"],
            )
            raise RuntimeError("forced rollback")

    # Read-back: nothing persisted because the txn was rolled back.
    assert await _count_rows(pg_test_suite, temp_table) == 0


async def test_oauth_credential_rotation_pattern(df, pg_test_suite, temp_table):
    """Canonical use case from issue #707: SELECT existing token + UPDATE-or-INSERT.

    1. Tx A inserts the initial token row (commit).
    2. Tx B reads the row, decides to UPDATE, commits.
    3. Tx C reads the row, decides to UPDATE again, commits.
    4. Tx D for a NEW user — row missing, INSERT branch fires.

    All steps run via `tx.execute_raw` only. Read-back from a fresh
    connection verifies the final state.
    """
    user_a = "user-a@example.test"
    user_b = "user-b@example.test"

    # Tx A: initial INSERT for user A
    async with df.transactions.begin() as tx:
        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            [user_a, "refresh-v1"],
        )

    # Tx B: rotation 1 — SELECT then UPDATE
    async with df.transactions.begin() as tx:
        existing = await tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_a],
        )
        assert len(existing) == 1, "user_a row MUST exist for UPDATE branch"
        await tx.execute_raw(
            f"UPDATE {temp_table} SET payload = $1 WHERE email = $2",
            ["refresh-v2", user_a],
        )

    # Tx C: rotation 2 — same UPDATE branch
    async with df.transactions.begin() as tx:
        existing = await tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_a],
        )
        assert len(existing) == 1
        await tx.execute_raw(
            f"UPDATE {temp_table} SET payload = $1 WHERE email = $2",
            ["refresh-v3", user_a],
        )

    # Tx D: new user — row missing, INSERT branch fires
    async with df.transactions.begin() as tx:
        existing = await tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_b],
        )
        assert len(existing) == 0, "user_b row MUST be absent for INSERT branch"
        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            [user_b, "refresh-v1"],
        )

    # Read-back from a fresh connection: 2 rows, user_a's payload is v3.
    async with pg_test_suite.get_connection() as conn:
        rows = await conn.fetch(
            f"SELECT email, payload FROM {temp_table} ORDER BY email"
        )
    by_email = {r["email"]: r["payload"] for r in rows}
    assert by_email == {user_a: "refresh-v3", user_b: "refresh-v1"}


async def test_insert_on_conflict_do_nothing_idempotency(pg_test_suite, temp_table):
    """Two concurrent transactions racing on the canonical PostgreSQL
    idempotency pattern: ``INSERT ... ON CONFLICT DO NOTHING``.

    The unique constraint on ``email`` makes the second concurrent INSERT
    collide; ``ON CONFLICT DO NOTHING`` returns 0 affected rows for the
    losing task without raising. Net effect: exactly one row persists,
    both tasks complete cleanly, and neither task sees a
    ``UniqueViolationError``.

    Why this pattern (not ``SELECT FOR UPDATE`` + conditional INSERT):
    PostgreSQL's READ COMMITTED isolation (DataFlow's default per
    ``transactions.py:244``) does NOT predicate-lock empty result sets.
    A ``SELECT ... WHERE x = $1 FOR UPDATE`` that matches zero rows
    takes no lock at all — both concurrent transactions see no
    pre-existing row, both proceed to INSERT, and the second hits
    ``UniqueViolationError`` on the unique constraint. SERIALIZABLE
    isolation + retry-on-serialization-failure would also work but
    has worse throughput; ``ON CONFLICT DO NOTHING`` is the documented
    canonical pattern for this exact scenario:
    https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT

    This test exercises ``db.transactions.begin()`` + ``tx.execute_raw``
    end-to-end against real PostgreSQL with two genuinely concurrent
    DataFlow instances racing on the same row.
    """
    idempotency_token = "idem-707-abc"

    async def maybe_insert(label: str) -> int:
        # Each task uses its OWN DataFlow instance — distinct connection
        # pools, so the two tasks genuinely race against each other on
        # the database, not on a shared in-process lock.
        local_df = DataFlow(database_url=pg_test_suite.config.url, auto_migrate=False)
        await local_df.initialize()
        try:
            async with local_df.transactions.begin() as tx:
                # Insert a tiny delay so both tasks reliably overlap on
                # the unique-constraint race.
                await asyncio.sleep(0.05)
                # ON CONFLICT DO NOTHING is the canonical PostgreSQL
                # idempotency pattern — atomic INSERT-or-skip with no
                # SELECT-then-INSERT race window. tx.execute_raw on
                # INSERT routes through asyncpg .execute() (it only
                # treats SELECT/WITH as fetch-shape), so the return
                # value is the asyncpg command tag — "INSERT 0 1" if
                # the row was inserted, "INSERT 0 0" if the conflict
                # triggered DO NOTHING. The rowcount is the trailing
                # integer.
                tag = await tx.execute_raw(
                    f"INSERT INTO {temp_table} (email, payload) "
                    f"VALUES ($1, $2) ON CONFLICT (email) DO NOTHING",
                    [idempotency_token, label],
                )
                # Parse rowcount from "INSERT <oid> <count>" command tag.
                return int(str(tag).rsplit(" ", 1)[-1]) if tag else 0
        finally:
            try:
                await local_df.close_async()
            except Exception:
                pass

    results = await asyncio.gather(maybe_insert("task-1"), maybe_insert("task-2"))

    # Exactly one task's INSERT took effect (rowcount=1); the other's
    # ON CONFLICT DO NOTHING returned rowcount=0. Neither raised.
    assert sorted(results) == [0, 1], (
        f"ON CONFLICT idempotency failed: results={results!r} "
        f"(expected exactly one rowcount=1 and one rowcount=0)"
    )
    # And exactly one row persists.
    assert await _count_rows(pg_test_suite, temp_table) == 1


async def test_partial_failure_within_transaction_rolls_back_all(
    df, pg_test_suite, temp_table
):
    """INSERT row 1, INSERT row 2 with constraint violation, expect rollback.

    Asserts neither row persists. The constraint is the UNIQUE on `email`:
    insert the same email twice in the same transaction.
    """
    duplicate_email = "duplicate@example.test"

    with pytest.raises(Exception):  # asyncpg.UniqueViolationError or wrapper
        async with df.transactions.begin() as tx:
            await tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                [duplicate_email, "row-1"],
            )
            # Same email — UNIQUE constraint violation, rolls back row-1 too.
            await tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                [duplicate_email, "row-2"],
            )

    # Read-back from a fresh connection: NEITHER row persists.
    assert await _count_rows(pg_test_suite, temp_table) == 0


# ---------------------------------------------------------------------------
# Outside-scope guard — typed delegate per rules/zero-tolerance.md Rule 3a
# ---------------------------------------------------------------------------


async def test_execute_raw_outside_scope_raises_runtime_error():
    """Calling `tx.execute_raw` AFTER the `async with` block raises RuntimeError.

    The typed delegate guard converts an opaque AttributeError ("None has
    no attribute 'execute'") into an actionable RuntimeError that names
    the scope contract.

    This test does not need real Postgres — it exercises the guard purely.
    """
    # Construct a TransactionScope without entering any begin() — the
    # ContextVar is unset, so execute_raw MUST raise the typed guard.
    scope = TransactionScope(
        id="manual",
        isolation_level="READ COMMITTED",
        status="active",
        type="transaction",
    )

    with pytest.raises(RuntimeError, match="outside the transaction body"):
        await scope.execute_raw("SELECT 1")
