"""Regression for issue #1548 — async lazy-DDL silent write loss.

Root cause (confirmed deterministically): the async lazy table-creation path

    ensure_table_exists()
      -> _execute_postgresql_schema_management_async()
        -> _execute_postgresql_migration_system_async()
          -> await self._migration_system.auto_migrate(...)

wrapped the ``auto_migrate`` call in ``try/except Exception: logger.error(...)``
and returned None WITHOUT re-raising (and only ``logger.warning``-ed when
``auto_migrate`` returned ``success=False``). When the migration genuinely
failed (raised) or did-not-apply (``success=False``) — which happens under
connection-pool exhaustion / process-state accumulation — the failure was
SWALLOWED. Control returned normally to ``ensure_table_exists``, which then
called ``mark_table_ensured`` and returned ``True`` while the table PHYSICALLY
DID NOT EXIST. Subsequent CRUD "succeeded" via read-your-writes on a pooled
connection but the row was never durable → silent write loss.

The fix (both parts):

* **Part A (stop swallowing):** ``_execute_postgresql_migration_system_async``
  (and the SQLite sibling) now log AND re-raise on a genuine failure, so the
  outer ``ensure_table_exists`` handler records the failed-DDL state and raises
  ``DDLFailedError`` (loud). "Already applied" / "no changes" (``success=True``)
  stays non-raising.

* **Part B (defense-in-depth):** before ``mark_table_ensured`` on the success
  path, ``ensure_table_exists`` verifies the table PHYSICALLY exists using a
  FRESH connection reflecting COMMITTED state; a definitive "absent" raises
  ``DDLFailedError``.

These tests run against a REAL PostgreSQL backend (shared infra) — the ONLY
injection permitted is the deliberate failure-injection of ``auto_migrate`` in
the silent-loss guard (that IS the fault being simulated, per the 3-tier
contract; the database itself is never mocked). No retry masks the failure.
"""

import uuid

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import DDLFailedError
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra)."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_ensure_table_exists_raises_not_lies_on_migration_failure(test_suite):
    """Silent-loss guard: a swallowed migration failure MUST NOT mark ensured.

    Forces the async lazy path (neutralizing sync creation), injects a genuine
    migration failure, and asserts ``ensure_table_exists``:

    1. RAISES ``DDLFailedError`` (NOT returns True) — Part A.
    2. did NOT mark the table ensured in the schema cache.
    3. recorded the failed-DDL state (fail-fast on next access).
    4. left the table physically ABSENT (a fresh committed-state connection
       confirms it).

    Pre-fix this test FAILS: ``ensure_table_exists`` returns True and marks the
    (non-existent) table ensured. Post-fix it PASSES.
    """
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Issue1548G{suffix}"

    db = DataFlow(db_url, auto_migrate=True)

    # Neutralize sync creation BEFORE registration/connection so the ONLY path
    # to table creation is the async lazy path under test.
    db._create_table_sync = lambda *a, **k: False
    db._create_tables_batch = lambda *a, **k: None

    Model = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Model)

    # Real table name from DataFlow (snake_case underscore before capital-after-
    # digit: Issue1548G... -> issue1548_g...s). Never guess model_name.lower()+"s".
    table = db._models[model_name]["table_name"]

    # Connect: lazily builds the migration system AND processes pending table
    # creations via _create_tables_batch — which we neutralized above, so NO
    # table is created here and the async lazy path stays the only route.
    db._ensure_connected()

    # Inject the fault: force the migration-system fallback (no enhanced state
    # manager) and make auto_migrate raise. This is the deterministic proxy for
    # the pool-exhaustion / process-state failure that produced the wild bug.
    db._schema_state_manager = None

    assert db._migration_system is not None, (
        "PostgreSQL DataFlow(auto_migrate=True) must have a migration system to "
        "inject the fault into"
    )

    async def _raise_migration(*a, **k):
        raise RuntimeError("injected migration failure (issue #1548 fault injection)")

    db._migration_system.auto_migrate = _raise_migration

    try:
        # 1. MUST raise DDLFailedError, NOT return True.
        with pytest.raises(DDLFailedError):
            await db.ensure_table_exists(model_name)

        # 2. MUST NOT have marked the table ensured.
        assert not db._schema_cache.is_table_ensured(model_name, db_url, None), (
            "schema cache marked a table ensured whose creation failed — the "
            "silent-write-loss bug (#1548)"
        )

        # 3. MUST have recorded the failed-DDL state (fail-fast next access).
        assert model_name in db._failed_table_creations, (
            "failed DDL was not recorded; next access would silently re-fire "
            "instead of failing fast"
        )

        # 4. The table MUST be physically absent — verified via a SEPARATE
        #    connection reflecting committed state (not the pooled one).
        async with test_suite.get_connection() as conn:
            reg = await conn.fetchval("SELECT to_regclass($1)", table)
            assert reg is None, (
                f"table {table!r} physically exists despite the migration "
                f"failure — ensure_table_exists lied about success"
            )
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_express_create_is_durable_on_separate_connection(test_suite):
    """Durability regression (happy path): a created row is durable.

    Normal ``express.create`` on a uniquely-named model, then a SEPARATE
    asyncpg connection MUST see the row. This is the positive control: the fix
    MUST NOT break the benign create path. The table name is derived from
    DataFlow's own registry (never a naive ``model_name.lower()+"s"`` guess).
    """
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Issue1548D{suffix}"

    db = DataFlow(db_url, auto_migrate=True)

    Model = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Model)

    table = db._models[model_name]["table_name"]

    try:
        await db.initialize()

        row = await db.express.create(model_name, {"entity_id": "e1", "score": 10})
        assert row is not None

        # Read-back through a SEPARATE connection — proves durability, not just
        # read-your-writes on the pooled connection.
        async with test_suite.get_connection() as conn:
            reg = await conn.fetchval("SELECT to_regclass($1)", table)
            assert reg is not None, (
                f"table {table!r} not durable — express.create reported success "
                f"but the table is absent on a separate connection (#1548)"
            )
            count = await conn.fetchval(f'SELECT count(*) FROM "{table}"')
            assert count >= 1, (
                f"row not durable — express.create reported success but the row "
                f"is absent on a separate connection (#1548)"
            )

        # Red-team #2: pin that the internal verify helper resolves a
        # normally-created (default-schema) table as True. This is the
        # search_path-parity control — the fresh verify connection rebuilt from
        # the same DSN sees the table the DDL path created under the same
        # search_path. If this ever returns False/None for a durable table, the
        # Part-B arbiter would false-raise on the success path.
        verified = await db._verify_table_physically_exists(model_name, db_url)
        assert verified is True, (
            f"_verify_table_physically_exists returned {verified!r} for a "
            f"durable default-schema table {table!r} — search_path parity broken"
        )
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_benign_migration_false_negative_does_not_raise_when_table_exists(
    test_suite,
):
    """Benign-reconciliation guard: a migration ``success=False`` on an
    already-existing table MUST NOT raise.

    The async migration system builds a SINGLE-table target schema and diffs it
    against the WHOLE database; on a shared / multi-table DB it can report
    ``success=False`` (e.g. refusing a spurious cross-table DROP) even though
    THIS model's table exists fine. If the fix raised unconditionally on
    ``success=False`` it would false-fail every such benign re-ensure. The
    physical-existence arbiter (Part B) reconciles: because the table is
    physically present, ``ensure_table_exists`` marks it ensured and returns
    True — no false ``DDLFailedError``, no false circuit-breaker trip.

    This is the positive control for the un-swallow: it MUST distinguish a real
    silent-write-loss (table absent -> raise) from a benign false-negative
    (table present -> proceed).

    Determinism (red-team #1): the ``success=False`` outcome is INJECTED
    (``auto_migrate`` patched to return ``(False, [])``) AFTER the table is
    physically created — NOT relied upon from the real migration system, whose
    return depends on shared-DB state (on a clean/isolated DB it returns
    ``success=True`` and the SUCCESS path would run, never exercising the
    except-path arbiter this test guards). The database itself is never mocked;
    only the deliberate fault (``auto_migrate`` not applying) is injected, per
    the 3-tier contract. Asserting BOTH ``ok is True`` AND the model is NOT
    recorded failed proves the EXCEPT-path arbiter recovered — not the success
    path.
    """
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Issue1548B{suffix}"

    db = DataFlow(db_url, auto_migrate=True)

    Model = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Model)

    table = db._models[model_name]["table_name"]

    try:
        # Create the table normally (sync path), so it PHYSICALLY exists.
        await db.initialize()

        # Force the async migration-system fallback (no enhanced state manager)
        # and clear the schema cache so the slow ensure path RE-RUNS (a cache
        # HIT would short-circuit ensure_table_exists before the migration path
        # and never exercise the except-path arbiter this test guards).
        db._schema_state_manager = None
        db._schema_cache.clear()
        db._failed_table_creations.clear()

        # INJECT the benign false-negative deterministically: auto_migrate
        # reports "did not apply" (success=False) though the table exists. The
        # un-swallowed helper raises MigrationNotAppliedError; the except-path
        # arbiter MUST reconcile against physical existence and recover.
        assert db._migration_system is not None

        async def _return_not_applied(*a, **k):
            return (False, [])

        db._migration_system.auto_migrate = _return_not_applied

        ok = await db.ensure_table_exists(model_name)
        assert ok is True, (
            "benign migration false-negative on an EXISTING table raised or "
            "returned False — the physical-existence arbiter must recover it"
        )
        assert model_name not in db._failed_table_creations, (
            "a physically-present table was wrongly recorded as failed-DDL "
            "(would fail-fast every subsequent access) — proves the EXCEPT-path "
            "arbiter recovered, not the success path"
        )

        # The table is still physically present (nothing dropped it).
        async with test_suite.get_connection() as conn:
            reg = await conn.fetchval("SELECT to_regclass($1)", table)
            assert reg is not None, f"table {table!r} vanished during reconcile"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res
