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
    await test_suite.clean_database()

    db = DataFlow(db_url, auto_migrate=True, multi_tenant=True)

    @db.model
    class Feat1249:
        entity_id: str
        score: int

    await db.initialize()

    db.tenant_context.register_tenant("acme", "A")
    db.tenant_context.register_tenant("globex", "G")

    with db.tenant_context.switch("acme"):
        await db.express.create("Feat1249", {"entity_id": "e1", "score": 10})
    with db.tenant_context.switch("globex"):
        await db.express.create("Feat1249", {"entity_id": "e1", "score": 99})

    with db.tenant_context.switch("acme"):
        acme_rows = await db.express.list("Feat1249", {})
    with db.tenant_context.switch("globex"):
        globex_rows = await db.express.list("Feat1249", {})

    acme_scores = sorted(r.get("score") for r in acme_rows)
    globex_scores = sorted(r.get("score") for r in globex_rows)

    assert acme_scores == [10], f"cross-tenant leak (postgres): acme saw {acme_scores}"
    assert globex_scores == [
        99
    ], f"cross-tenant leak (postgres): globex saw {globex_scores}"

    # Raw-row assertion: tenant_id persisted non-NULL per row (defect #2).
    async with test_suite.get_connection() as conn:
        rows = await conn.fetch(
            "SELECT entity_id, score, tenant_id FROM feat1249s ORDER BY id"
        )
    tenants = {r["tenant_id"] for r in rows}
    assert None not in tenants, f"tenant_id stored NULL on postgres: {rows}"
    assert tenants == {"acme", "globex"}, f"wrong tenant_id values: {rows}"
