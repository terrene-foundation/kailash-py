"""Regression for issue #2206 — the residual #1548 silent-write-loss window.

#1548 added a defense-in-depth physical-existence check: before
``mark_table_ensured`` on the SUCCESS path, ``ensure_table_exists`` verifies the
table exists on a FRESH connection reflecting COMMITTED state. That check is
THREE-state, and #1548 only wired TWO of them::

    True   -> confirmed        -> mark ensured, return True
    False  -> confirmed absent -> raise (the #1548 guard)
    None   -> INCONCLUSIVE     -> fell through to mark ensured, return True

The residual is the third row. The check goes inconclusive when the fresh
verify connect is REFUSED or TIMES OUT — i.e. under exactly the connection-pool
exhaustion / process-state accumulation #1548 was filed for — so the guard
failed OPEN precisely in the condition it exists to catch. Worse, the
``mark_table_ensured`` that followed CACHED the fail-open: every later access
short-circuited at the schema-cache fast path and never re-verified, so a single
transient blip blinded that DataFlow instance to a missing table for the rest of
its lifetime.

Observed as a ~1/137 non-deterministic failure of
``test_issue_1249_tenant_isolation_leak_postgres.py``: ``express.create`` and
``express.list`` both succeeded with correctly-isolated data on the POOLED
connection, then a raw SECOND connection raised ``UndefinedTableError``.
Read-your-writes on the pool, no durability — the #1548 signature, from a path
#1548's own fix did not cover.

The fix separates the two KINDS of inconclusive, which are not
interchangeable:

* ``"unverifiable-backend"`` (STRUCTURAL) — unknown backend with no SQL table
  concept, bare in-memory SQLite with no shared URI. A retry returns the
  identical verdict, so blocking buys no durability and only breaks legitimate
  flows. Proceeds, exactly as before (test 4).
* ``"check-error"`` (TRANSIENT) — the check itself could not run. Retried once
  (test 3); if still inconclusive, durability is UNCONFIRMED and the call
  refuses to cache OR to report success (test 1), while deliberately NOT
  recording failed-DDL state so the next access self-heals (test 2).

Distinct from #1548's three tests, which cover the migration-RAISES error path,
the plain durability happy path, and the benign migration-false-negative
recovery. NONE of them exercises the SUCCESS path with an INCONCLUSIVE verify —
that combination is this file.

Tier 2: a REAL PostgreSQL backend (shared infra). The only injections are at
the two fault boundaries #1548's own regression suite already injects at — the
migration result and the verify CONNECT — which ARE the faults being simulated
(pool exhaustion cannot be summoned deterministically in-process). The database
itself is never mocked, and no retry masks the failure under test.
"""

import uuid
from pathlib import Path

import asyncpg
import pytest

import dataflow
import dataflow.core.engine as engine_module
from dataflow import DataFlow
from dataflow.core.exceptions import DDLFailedError
from tests.infrastructure.test_harness import IntegrationTestSuite

# Import-path pin (relative to THIS checkout, never a hard-coded worktree
# path): tests/regression/<file> -> tests/ -> kailash-dataflow/ -> src/dataflow.
# An unpinned import silently resolves to an installed copy and produces a FALSE
# GREEN for a fix that is not actually under test.
_CHECKOUT_SRC = Path(__file__).resolve().parents[2] / "src"


def test_dataflow_is_imported_from_this_checkout():
    """Guard: every assertion below is meaningless against a stale install."""
    resolved = Path(dataflow.__file__).resolve()
    assert resolved.is_relative_to(_CHECKOUT_SRC), (
        f"dataflow resolved to {resolved}, not this checkout's {_CHECKOUT_SRC} — "
        f"the suite would be testing an installed copy, not the code under test"
    )


@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra)."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class _RefuseVerifyConnect:
    """Make the FRESH committed-state verify connect fail, the way a saturated
    server does. ``TooManyConnectionsError`` is the literal error PostgreSQL
    returns as ``FATAL: sorry, too many clients already`` — the condition
    ``_verify_table_physically_exists`` reports as the TRANSIENT
    ``"check-error"`` inconclusive.

    ``fail_first_n=None`` refuses every attempt; an integer refuses only the
    first N so the retry can be observed absorbing a passing blip.

    Scoped by ``context`` to the verify connect ONLY. ``engine.py`` routes other
    fresh connects through the same helper (notably the #1600 column-reconcile
    inspect), and counting or refusing those would make ``attempts`` mean
    something other than "verify attempts" — the exact instrument-scope error of
    reading a counter for a question it does not answer.
    """

    VERIFY_CONTEXT = "PostgreSQL table-exists verify"

    def __init__(self, fail_first_n=None):
        self.fail_first_n = fail_first_n
        self.attempts = 0
        self._original = engine_module.open_credentialed_connection

    async def _patched(self, *args, **kwargs):
        if kwargs.get("context") != self.VERIFY_CONTEXT:
            return await self._original(*args, **kwargs)
        self.attempts += 1
        if self.fail_first_n is None or self.attempts <= self.fail_first_n:
            raise asyncpg.exceptions.TooManyConnectionsError(
                "sorry, too many clients already"
            )
        return await self._original(*args, **kwargs)

    def __enter__(self):
        engine_module.open_credentialed_connection = self._patched
        return self

    def __exit__(self, *exc):
        engine_module.open_credentialed_connection = self._original
        return False


async def _make_db_with_real_table(db_url, test_suite):
    """A DataFlow whose table REALLY exists, positioned for a cache-MISS ensure.

    The table is created through the normal path (no injection), then the schema
    cache is cleared so the next ``ensure_table_exists`` re-runs the full path —
    which is where the verify under test happens. Creating it for real matters:
    it makes the tests below about the VERIFY's three-state handling and not
    about DDL success.
    """
    suffix = uuid.uuid4().hex[:8]
    model_name = f"Issue2206{suffix}"

    db = DataFlow(db_url, auto_migrate=True)
    Model = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Model)
    table = db._models[model_name]["table_name"]

    db._ensure_connected()
    assert await db.ensure_table_exists(model_name) is True, (
        "precondition failed: the table could not be created through the normal "
        "path, so nothing below would be testing the verify"
    )
    async with test_suite.get_connection() as conn:
        assert await conn.fetchval("SELECT to_regclass($1)", table) is not None

    # Force the next ensure to MISS the cache (the HIT fast path returns before
    # the verify, so it would bypass the code under test entirely).
    db._schema_cache._cache.clear()

    # Put the instance on the SUCCESS path: the table already exists and matches,
    # so auto_migrate legitimately reports success with nothing to do. This is
    # the real shape of the residual — schema management says "fine", and the
    # verify is then the ONLY evidence the table is durable.
    db._schema_state_manager = None

    async def _success_nothing_to_do(*args, **kwargs):
        return (True, [])

    db._migration_system.auto_migrate = _success_nothing_to_do

    return db, model_name, table


async def _cleanup(db, table, test_suite):
    async with test_suite.get_connection() as conn:
        await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    result = db.close()
    if result is not None and hasattr(result, "__await__"):
        await result


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_inconclusive_verification_must_not_report_or_cache_success(
    test_suite,
):
    """THE residual window: success path + inconclusive verify.

    Pre-fix ``ensure_table_exists`` returns ``True`` and marks the table ensured
    on an UNVERIFIED result — the silent-write-loss fail-open. Post-fix it
    raises ``DDLFailedError`` and leaves the cache cold.

    ``DDLFailedError`` specifically: it is the ONLY exception type
    ``nodes.py``'s ensure handler re-raises instead of logging and continuing
    into the CRUD call, so it is the only type that actually stops a write into
    a table whose existence was never confirmed.
    """
    db_url = test_suite.config.url
    db, model_name, table = await _make_db_with_real_table(db_url, test_suite)

    try:
        with _RefuseVerifyConnect() as refuser:
            with pytest.raises(DDLFailedError) as excinfo:
                await db.ensure_table_exists(model_name)

        # The retry fired: one initial attempt plus one retry, both refused.
        assert refuser.attempts == 2, (
            f"expected exactly 1 verify + 1 retry, saw {refuser.attempts} — "
            f"the bounded retry is part of the contract (a single attempt would "
            f"surface transient blips as hard failures)"
        )

        assert "2206" in str(excinfo.value) or "verification" in str(excinfo.value), (
            f"the error must name the unconfirmed-durability cause so an "
            f"operator can act on it; got: {excinfo.value}"
        )

        # The cache MUST stay cold. This is the half that made the pre-fix bug
        # permanent rather than momentary: a marked cache makes every later
        # access short-circuit at the fast path and never re-verify.
        assert not db._schema_cache.is_table_ensured(model_name, db_url, None), (
            "schema cache marked a table ensured on an UNVERIFIED result — the "
            "cached fail-open that made #2206 outlive the transient condition"
        )
    finally:
        await _cleanup(db, table, test_suite)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_inconclusive_verification_does_not_trip_the_ddl_circuit_breaker(
    test_suite,
):
    """The refusal must be RECOVERABLE, not a permanent brick.

    The #696 circuit breaker (``_check_failed_ddl``) has NO TTL — once
    ``_failed_table_creations`` holds a model, every later access raises until
    something calls ``_clear_failed_ddl``. Recording a momentary connect refusal
    there would convert a transient condition into a dead model for the life of
    the instance, which would be a worse bug than the one being fixed. The
    inconclusive path therefore leaves BOTH the breaker and the cache untouched,
    and the very next access re-runs the ensure and succeeds.
    """
    db_url = test_suite.config.url
    db, model_name, table = await _make_db_with_real_table(db_url, test_suite)

    try:
        with _RefuseVerifyConnect():
            with pytest.raises(DDLFailedError):
                await db.ensure_table_exists(model_name)

        assert model_name not in db._failed_table_creations, (
            "an UNCONFIRMED verification recorded failed-DDL state; the #696 "
            "breaker has no TTL, so this would permanently brick a model whose "
            "table exists, over a momentary connect refusal"
        )

        # Condition cleared (the refuser's context manager restored the real
        # connect): the next access must self-heal with no operator action.
        assert await db.ensure_table_exists(model_name) is True, (
            "the next access did not self-heal after the transient verification "
            "failure cleared"
        )
        assert db._schema_cache.is_table_ensured(model_name, db_url, None)
    finally:
        await _cleanup(db, table, test_suite)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_transient_verification_blip_is_absorbed_by_the_retry(test_suite):
    """No-false-positive: one failed attempt then a good one must NOT raise.

    Without the bounded retry, the fix would turn every momentary connect blip
    into a ``DDLFailedError`` against a table that exists perfectly — trading
    the silent-loss bug for a loud-but-wrong one.
    """
    db_url = test_suite.config.url
    db, model_name, table = await _make_db_with_real_table(db_url, test_suite)

    try:
        with _RefuseVerifyConnect(fail_first_n=1) as refuser:
            result = await db.ensure_table_exists(model_name)

        assert result is True, (
            "a verification blip that cleared on retry was surfaced as a "
            "failure; the retry exists precisely to absorb it"
        )
        assert refuser.attempts == 2, (
            f"expected 1 refused attempt + 1 successful retry, saw "
            f"{refuser.attempts}"
        )
        assert db._schema_cache.is_table_ensured(model_name, db_url, None), (
            "a CONFIRMED table was not cached, costing a full ensure on every "
            "later access"
        )
    finally:
        await _cleanup(db, table, test_suite)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_structural_inconclusive_is_reported_as_unverifiable_backend(
    test_suite,
):
    """The STRUCTURAL kind stays non-blocking — the fix is narrow.

    An unknown backend has no SQL table concept to check, so the verdict is
    inconclusive no matter how often it is retried. Blocking on it would buy no
    durability and break legitimate flows, so it keeps #1548's proceed
    behaviour. Only the reason code distinguishes it from the transient kind, so
    this pins that the two are actually reported differently — without it, the
    fix could collapse both back into one and still pass every test above.
    """
    db_url = test_suite.config.url

    db = DataFlow(db_url, auto_migrate=True)
    model_name = f"Issue2206S{uuid.uuid4().hex[:8]}"
    Model = type(model_name, (), {"__annotations__": {"entity_id": str}})
    db.model(Model)

    try:
        verdict, reason = await db._verify_table_physically_exists_detailed(
            model_name, "mongodb://localhost:27017/app"
        )
        assert verdict is None
        assert reason == "unverifiable-backend", (
            f"an unverifiable BACKEND was reported as {reason!r}; if it is "
            f"reported as 'check-error' the success path will retry and then "
            f"fail a flow that can never be verified"
        )

        # And the transient kind is reported differently, against a real DSN
        # whose connect is refused.
        with _RefuseVerifyConnect():
            verdict, reason = await db._verify_table_physically_exists_detailed(
                model_name, db_url
            )
        assert verdict is None
        assert reason == "check-error", (
            f"a refused verify CONNECT was reported as {reason!r}; if it is "
            f"reported as 'unverifiable-backend' the success path proceeds and "
            f"#2206 is reopened"
        )
    finally:
        result = db.close()
        if result is not None and hasattr(result, "__await__"):
            await result
