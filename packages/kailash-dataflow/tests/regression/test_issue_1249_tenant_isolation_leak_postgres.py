"""PostgreSQL variant of the issue #1249 cross-tenant isolation regression.

Mirrors the core leak assertion from
``test_issue_1249_tenant_isolation_leak.py`` against a REAL PostgreSQL backend
(shared infra on port 5434 via ``IntegrationTestSuite``). Marked
``requires_postgres`` so it is skipped in the default no-infra run and exercised
in CI where the shared database is available.

The leak (#1249) was backend-agnostic — it lived in the SQL ``QueryInterceptor``
identifier-normalization path, which runs identically for SQLite and
PostgreSQL. This test confirms isolation holds on PostgreSQL's quoted-identifier
SQL (``INSERT INTO "feats" ...`` + ``$1, $2`` placeholders + ``RETURNING``).
"""

import uuid

import pytest

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra, port 5434)."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_express_multi_tenant_isolation_no_cross_tenant_leak_postgres(test_suite):
    """Two tenants create rows on PostgreSQL; each reads back ONLY its own."""
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Feat1249{suffix}"
    table = f"{model_name.lower()}s"

    db = DataFlow(db_url, auto_migrate=True, multi_tenant=True)

    Feat = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Feat)

    try:
        await db.initialize()

        db.tenant_context.register_tenant("acme", "A")
        db.tenant_context.register_tenant("globex", "G")

        with db.tenant_context.switch("acme"):
            await db.express.create(model_name, {"entity_id": "e1", "score": 10})
        with db.tenant_context.switch("globex"):
            await db.express.create(model_name, {"entity_id": "e1", "score": 99})

        with db.tenant_context.switch("acme"):
            acme_rows = await db.express.list(model_name, {})
        with db.tenant_context.switch("globex"):
            globex_rows = await db.express.list(model_name, {})

        acme_scores = sorted(r.get("score") for r in acme_rows)
        globex_scores = sorted(r.get("score") for r in globex_rows)

        assert acme_scores == [
            10
        ], f"cross-tenant leak (postgres): acme saw {acme_scores}"
        assert globex_scores == [
            99
        ], f"cross-tenant leak (postgres): globex saw {globex_scores}"

        # Raw-row assertion: tenant_id persisted non-NULL per row (defect #2).
        async with test_suite.get_connection() as conn:
            rows = await conn.fetch(
                f'SELECT entity_id, score, tenant_id FROM "{table}" ORDER BY id'
            )
        tenants = {r["tenant_id"] for r in rows}
        assert None not in tenants, f"tenant_id stored NULL on postgres: {rows}"
        assert tenants == {"acme", "globex"}, f"wrong tenant_id values: {rows}"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_express_multi_tenant_list_with_limit_isolates_postgres(test_suite):
    """Multi-tenant ``list`` (default LIMIT/OFFSET) isolates on PostgreSQL.

    Regression for the #1249 follow-up (2.11.0 → 2.11.1): the SELECT-condition
    injector hardcoded a ``?`` placeholder for the tenant predicate and did NOT
    renumber the existing ``$N`` placeholders. DataFlow's ``list`` emits a
    trailing ``LIMIT $1 OFFSET $2``; injecting ``WHERE tenant_id = ?`` produced
    ``... WHERE tenant_id = ? ORDER BY id DESC LIMIT $1 OFFSET $2`` with params
    ``['acme', 100, 0]`` — on PostgreSQL ``$1`` bound to the tenant STRING and
    asyncpg raised ``argument of LIMIT must be type bigint, not type text``.
    SQLite (all-``?``, positional) hid the defect because positional binding
    happened to line up.

    Pre-fix this test ERRORS at the first ``list`` (LIMIT type error). Post-fix
    the injected predicate is ``$1`` and the existing placeholders renumber to
    ``LIMIT $2 OFFSET $3``, so each tenant's list returns ONLY its own rows.
    This is the exact path that shipped broken in 2.11.0 — covered here because
    the pre-fix suite never exercised a multi-tenant Postgres ``list`` with the
    default LIMIT.
    """
    db_url = test_suite.config.url

    # Unique model/table per run (shared test DB); DROPped in finally.
    suffix = uuid.uuid4().hex[:8]
    model_name = f"Feat1249Limit{suffix}"
    table = f"{model_name.lower()}s"

    db = DataFlow(db_url, auto_migrate=True, multi_tenant=True)

    Feat = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Feat)

    try:
        await db.initialize()

        db.tenant_context.register_tenant("acme", "A")
        db.tenant_context.register_tenant("globex", "G")

        # Multiple rows per tenant so the LIMIT (default) is genuinely exercised.
        with db.tenant_context.switch("acme"):
            for i in range(3):
                await db.express.create(model_name, {"entity_id": f"a{i}", "score": i})
        with db.tenant_context.switch("globex"):
            for i in range(3):
                await db.express.create(
                    model_name, {"entity_id": f"g{i}", "score": 100 + i}
                )

        # list() with the framework default LIMIT — the trailing ``LIMIT $N
        # OFFSET $N`` path that bound the tenant string to LIMIT pre-fix.
        with db.tenant_context.switch("acme"):
            acme_rows = await db.express.list(model_name, {})
        with db.tenant_context.switch("globex"):
            globex_rows = await db.express.list(model_name, {})

        acme_scores = sorted(r.get("score") for r in acme_rows)
        globex_scores = sorted(r.get("score") for r in globex_rows)

        assert acme_scores == [0, 1, 2], f"list leak/wrong (acme, pg): {acme_scores}"
        assert globex_scores == [
            100,
            101,
            102,
        ], f"list leak/wrong (globex, pg): {globex_scores}"

        # Explicit non-default LIMIT/OFFSET also stays tenant-scoped (renumber
        # holds when MORE trailing $N placeholders precede the injection point).
        with db.tenant_context.switch("acme"):
            acme_limited = await db.express.list(model_name, {}, limit=2, offset=0)
        assert (
            len(acme_limited) == 2
        ), f"explicit LIMIT broke isolation/paging: {acme_limited}"
        assert all(
            r.get("score") in (0, 1, 2) for r in acme_limited
        ), f"explicit-LIMIT list leaked globex rows: {acme_limited}"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
