# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #711 — sync surface for transactions.

`db.transactions_sync.begin()` MUST pin one connection across all
`tx.execute_raw` calls (sync), auto-commit on clean exit, auto-rollback
on exception. Tier 2 (real PostgreSQL).

This is the sync analogue of issue #707 (which covered the async
surface ``db.transactions.begin()``). Per
``rules/cross-sdk-inspection.md`` § 3a "Structural API-Divergence
Disposition" and ``rules/testing.md`` § "One Direct Test Per Variant",
the sync paired variant gets its own direct-call regression coverage —
delegation through the async path does not satisfy the contract.

Per ``rules/testing.md`` § "3-Tier Testing" Tier 2: NO mocking. Every
test runs against the real PostgreSQL test instance via the
``IntegrationTestSuite`` fixture from ``tests/infrastructure/test_harness``.
"""

from __future__ import annotations

import time
import uuid

import pytest

from dataflow import DataFlow
from dataflow.features.transactions import (
    SyncTransactionManager,
    SyncTransactionScope,
)
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
    return f"tx_711_{int(time.time() * 1_000_000)}_{uuid.uuid4().hex[:8]}"


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

    The fixture is async because IntegrationTestSuite is async; the
    DataFlow returned is used SYNCHRONOUSLY by the body (no await on
    db.transactions_sync.begin()). Sync surface is exercised inside a
    pytest-asyncio context — proves no `RuntimeError: event loop already
    running` per the issue's cross-context safety acceptance criterion.

    NOTE: ``await instance.initialize()`` is required for the DataFlow
    connection adapter to be created on the host event loop. Without
    it, ``TransactionManager._get_adapter()`` returns None and the
    sync surface raises "no database connection available" before it
    can even reach the BG-loop dispatch.
    """
    instance = DataFlow(database_url=pg_test_suite.config.url, auto_migrate=False)
    await instance.initialize()
    try:
        yield instance
    finally:
        # Explicit close per rules/testing.md § "Fixtures Yield + Cleanup".
        # close_async() also stops the SyncTransactionManager BG thread
        # if `db.transactions_sync` was accessed during the test.
        try:
            await instance.close_async()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_rows(pg_test_suite, table: str) -> int:
    """Verify-via-readback per rules/testing.md § State Persistence Verification.

    Uses a FRESH connection from the integration test suite — outside any
    DataFlow transaction. This proves the transaction's commit/rollback
    actually persisted to the database, not just to the pinned connection.
    """
    async with pg_test_suite.get_connection() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table}")


# ---------------------------------------------------------------------------
# Tier 2 regression coverage — mirrors test_issue_707 for the SYNC surface
# ---------------------------------------------------------------------------


async def test_multi_statement_atomicity_via_sync_tx_execute_raw(
    df, pg_test_suite, temp_table
):
    """Issue #711 canonical: BEGIN-INSERT-INSERT-COMMIT all via sync tx.execute_raw.

    Asserts both rows are visible after commit when read back from a fresh
    connection — proves the COMMIT actually persisted state to the database
    AND that the sync wrapper preserved the connection pinning across calls.
    """
    # NOTE: The fixture body is async (pytest-asyncio), but the with block
    # below uses the SYNC surface — this is exactly the cross-context
    # scenario the issue calls out. If the sync surface tried to call
    # ``asyncio.run()`` per statement, this test would raise
    # ``RuntimeError: This event loop is already running``.
    assert isinstance(df.transactions_sync, SyncTransactionManager)

    with df.transactions_sync.begin() as tx:
        assert isinstance(tx, SyncTransactionScope), (
            f"transactions_sync.begin() yielded {type(tx).__name__}, "
            "expected SyncTransactionScope (issue #711 contract)"
        )
        assert tx.status == "active"
        assert tx.type == "transaction"

        tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["alice@example.test", "row-1"],
        )
        tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["bob@example.test", "row-2"],
        )
        # Read-within-transaction: the pinned connection sees its own writes.
        in_tx_rows = tx.execute_raw(f"SELECT email FROM {temp_table} ORDER BY email")
        assert len(in_tx_rows) == 2
        assert {dict(r)["email"] for r in in_tx_rows} == {
            "alice@example.test",
            "bob@example.test",
        }

    # Read-back via a DIFFERENT connection — proves COMMIT happened.
    assert await _count_rows(pg_test_suite, temp_table) == 2


async def test_sync_auto_rollback_on_exception(df, pg_test_suite, temp_table):
    """Exceptions inside the `with` body MUST roll back the entire txn.

    Insert one row, raise, then read back from a FRESH connection — zero
    rows MUST persist. Sync analogue of the load-bearing rollback
    invariant for the OAuth credential rotation pattern.
    """
    with pytest.raises(RuntimeError, match="forced rollback"):
        with df.transactions_sync.begin() as tx:
            tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                ["alice@example.test", "should-not-persist"],
            )
            raise RuntimeError("forced rollback")

    # Read-back: nothing persisted because the txn was rolled back.
    assert await _count_rows(pg_test_suite, temp_table) == 0


async def test_sync_oauth_credential_rotation_pattern(df, pg_test_suite, temp_table):
    """Canonical use case from issue #711: SELECT existing token + UPDATE-or-INSERT.

    1. Tx A inserts the initial token row (commit).
    2. Tx B reads the row, decides to UPDATE, commits.
    3. Tx C reads the row, decides to UPDATE again, commits.
    4. Tx D for a NEW user — row missing, INSERT branch fires.

    All steps run via sync `tx.execute_raw` only. Read-back from a fresh
    connection verifies the final state.
    """
    user_a = "user-a@example.test"
    user_b = "user-b@example.test"

    # Tx A: initial INSERT for user A
    with df.transactions_sync.begin() as tx:
        tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            [user_a, "refresh-v1"],
        )

    # Tx B: rotation 1 — SELECT then UPDATE
    with df.transactions_sync.begin() as tx:
        existing = tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_a],
        )
        assert len(existing) == 1, "user_a row MUST exist for UPDATE branch"
        tx.execute_raw(
            f"UPDATE {temp_table} SET payload = $1 WHERE email = $2",
            ["refresh-v2", user_a],
        )

    # Tx C: rotation 2 — same UPDATE branch
    with df.transactions_sync.begin() as tx:
        existing = tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_a],
        )
        assert len(existing) == 1
        tx.execute_raw(
            f"UPDATE {temp_table} SET payload = $1 WHERE email = $2",
            ["refresh-v3", user_a],
        )

    # Tx D: new user — row missing, INSERT branch fires
    with df.transactions_sync.begin() as tx:
        existing = tx.execute_raw(
            f"SELECT id FROM {temp_table} WHERE email = $1 FOR UPDATE",
            [user_b],
        )
        assert len(existing) == 0, "user_b row MUST be absent for INSERT branch"
        tx.execute_raw(
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


async def test_sync_partial_failure_within_transaction_rolls_back_all(
    df, pg_test_suite, temp_table
):
    """INSERT row 1, INSERT row 2 with constraint violation, expect rollback.

    Asserts neither row persists. The constraint is the UNIQUE on `email`:
    insert the same email twice in the same transaction.
    """
    duplicate_email = "duplicate@example.test"

    with pytest.raises(Exception):  # asyncpg.UniqueViolationError or wrapper
        with df.transactions_sync.begin() as tx:
            tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                [duplicate_email, "row-1"],
            )
            # Same email — UNIQUE constraint violation, rolls back row-1 too.
            tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                [duplicate_email, "row-2"],
            )

    # Read-back from a fresh connection: NEITHER row persists.
    assert await _count_rows(pg_test_suite, temp_table) == 0


async def test_sync_execute_raw_outside_scope_raises_runtime_error(df):
    """Calling `tx.execute_raw` AFTER the `with` block raises RuntimeError.

    The typed delegate guard converts an opaque AttributeError into an
    actionable RuntimeError that names the scope contract. Sync analogue
    of the test_execute_raw_outside_scope_raises_runtime_error from the
    async regression file.

    This test does need a real DataFlow because the sync `begin()` runs
    on the BG event loop and calls into the async `begin()` which needs
    a live adapter — but only the RuntimeError-on-out-of-scope branch is
    asserted here, NOT the database side-effect.
    """
    captured_scope: SyncTransactionScope | None = None

    with df.transactions_sync.begin() as tx:
        captured_scope = tx
        # Inside the with block: execute_raw works.
        result = tx.execute_raw("SELECT 1 AS one")
        assert len(result) == 1
        assert dict(result[0])["one"] == 1

    # Outside the with block: the typed guard fires.
    assert captured_scope is not None
    with pytest.raises(RuntimeError, match="outside the transaction body"):
        captured_scope.execute_raw("SELECT 1")


async def test_sync_surface_inside_pytest_asyncio_does_not_raise_event_loop_error(
    df, pg_test_suite, temp_table
):
    """Cross-context safety: sync surface MUST work inside pytest-asyncio.

    This is the load-bearing acceptance criterion from issue #711 — the
    sync surface MUST work without raising
    ``RuntimeError: This event loop is already running`` when the caller
    is inside an active event loop (pytest-asyncio, Nexus handler,
    Jupyter cell). The other tests in this module already exercise the
    sync surface from inside an async test body (every test in this file
    is async because the fixture is async), but this test asserts the
    invariant explicitly with a comment that pins the contract.

    If a future refactor moves the sync surface to per-call
    ``asyncio.run()``, every other test in this file will start raising
    ``RuntimeError`` — and this test makes the failure mode legible by
    naming it.
    """
    # We are inside a pytest-asyncio test → there IS an active event loop
    # in this thread. The sync surface uses a SEPARATE BG-thread event
    # loop, so calling ``begin()`` here MUST NOT raise.
    import asyncio

    assert (
        asyncio.get_running_loop() is not None
    ), "test precondition: must run inside pytest-asyncio event loop"

    with df.transactions_sync.begin() as tx:
        tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["nested@example.test", "from-async-context"],
        )

    assert await _count_rows(pg_test_suite, temp_table) == 1
