"""PostgreSQL variant of the issue #1252 bulk cross-tenant isolation regression.

Mirrors the core leak assertion from
``test_issue_1252_bulk_tenant_isolation.py`` against a REAL PostgreSQL backend
(shared infra on port 5434 via ``IntegrationTestSuite``). Marked
``requires_postgres`` so it is skipped in the default no-infra run and exercised
in CI where the shared database is available.

The leak (#1252) was backend-agnostic — it lived in the bulk subsystem's
stale-dict tenant source (``self.dataflow._tenant_context``), which is empty
under ``tenant_context.switch()`` on every backend. This test confirms isolation
holds on PostgreSQL's quoted-identifier SQL (``INSERT INTO "feats" ...`` +
``$N`` placeholders + ``ON CONFLICT (id) ... RETURNING``) for bulk_create,
bulk_update (filter-scoped), bulk_delete (filter-scoped), and bulk_upsert.

Each test uses a UNIQUE model/table name (shared DB) and DROPs it in a finally
block — the harness here has no ``clean_database()`` helper, so the prior
``await test_suite.clean_database()`` aborted these tests before they ever
exercised the Postgres bulk SQL (the coverage gap that let the #1249 follow-up
ship a Postgres-only ``list`` regression on 2.11.0).
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
async def test_bulk_isolation_no_cross_tenant_leak_postgres(test_suite):
    """Two tenants exercise all four bulk ops on PostgreSQL; isolation holds."""
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Feat1252{suffix}"
    table = f"{model_name.lower()}s"

    db = DataFlow(db_url, auto_migrate=True, multi_tenant=True)

    Feat = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Feat)

    try:
        await db.initialize()

        db.tenant_context.register_tenant("acme", "A")
        db.tenant_context.register_tenant("globex", "G")

        # bulk_create — non-NULL tenant_id + cross-read isolation.
        with db.tenant_context.switch("acme"):
            await db.bulk.bulk_create(
                model_name,
                [{"entity_id": "a1", "score": 1}, {"entity_id": "a2", "score": 2}],
            )
        with db.tenant_context.switch("globex"):
            await db.bulk.bulk_create(
                model_name,
                [
                    {"entity_id": "g1", "score": 100},
                    {"entity_id": "g2", "score": 200},
                ],
            )

        # express.list AFTER bulk_create — the Postgres ``list`` path (trailing
        # ``LIMIT $N OFFSET $N``) that bound the tenant string to LIMIT pre-#1249
        # follow-up. Isolation here proves the bulk-written rows are readable
        # tenant-scoped on Postgres (the placeholder-renumber path).
        with db.tenant_context.switch("acme"):
            acme_scores = sorted(
                r.get("score") for r in await db.express.list(model_name, {})
            )
        with db.tenant_context.switch("globex"):
            globex_scores = sorted(
                r.get("score") for r in await db.express.list(model_name, {})
            )
        assert acme_scores == [
            1,
            2,
        ], f"cross-tenant leak (pg list): acme saw {acme_scores}"
        assert globex_scores == [
            100,
            200,
        ], f"cross-tenant leak (pg list): globex saw {globex_scores}"

        async with test_suite.get_connection() as conn:
            rows = await conn.fetch(f'SELECT tenant_id FROM "{table}"')
        tenants = {r["tenant_id"] for r in rows}
        assert None not in tenants, f"tenant_id stored NULL on postgres: {tenants}"
        assert tenants == {"acme", "globex"}, f"wrong tenant_id values: {tenants}"

        # bulk_update — empty filter (update-all) MUST only touch acme's rows.
        with db.tenant_context.switch("acme"):
            await db.bulk.bulk_update(
                model_name,
                filter_criteria={},
                update_values={"score": 0},
                confirmed=True,
            )
        async with test_suite.get_connection() as conn:
            globex_after = sorted(
                r["score"]
                for r in await conn.fetch(
                    f"SELECT score FROM \"{table}\" WHERE tenant_id = 'globex'"
                )
            )
        assert globex_after == [
            100,
            200,
        ], f"cross-tenant bulk_update leaked into globex (pg): {globex_after}"

        # bulk_upsert — round-trips under acme on the id PK; globex untouched.
        with db.tenant_context.switch("acme"):
            acme_rows = await db.express.list(model_name, {})
            acme_id = acme_rows[0]["id"]
            result = await db.bulk.bulk_upsert(
                model_name,
                [{"id": acme_id, "entity_id": "a1", "score": 999}],
                conflict_resolution="update",
            )
        assert result.get("success") is True, f"bulk_upsert failed (pg): {result}"
        async with test_suite.get_connection() as conn:
            upserted = await conn.fetchrow(
                f'SELECT score, tenant_id FROM "{table}" WHERE id = $1', acme_id
            )
            globex_after = sorted(
                r["score"]
                for r in await conn.fetch(
                    f"SELECT score FROM \"{table}\" WHERE tenant_id = 'globex'"
                )
            )
        assert (
            upserted["score"] == 999 and upserted["tenant_id"] == "acme"
        ), f"bulk_upsert round-trip failed (pg): {dict(upserted)}"
        assert globex_after == [
            100,
            200,
        ], f"bulk_upsert leaked into globex (pg): {globex_after}"

        # bulk_delete — empty filter (delete-all) MUST only delete acme's rows.
        with db.tenant_context.switch("acme"):
            await db.bulk.bulk_delete(model_name, filter_criteria={}, confirmed=True)
        async with test_suite.get_connection() as conn:
            remaining = await conn.fetch(f'SELECT tenant_id FROM "{table}"')
        remaining_tenants = {r["tenant_id"] for r in remaining}
        assert (
            "acme" not in remaining_tenants
        ), f"acme rows not deleted (pg): {remaining_tenants}"
        assert remaining_tenants == {
            "globex"
        }, f"bulk_delete leaked into globex (pg): {remaining_tenants}"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_bulk_create_without_bound_tenant_fails_closed_postgres(test_suite):
    """bulk_create under multi_tenant=True with NO bound tenant fails closed on PG."""
    db_url = test_suite.config.url

    suffix = uuid.uuid4().hex[:8]
    model_name = f"Feat1252Fc{suffix}"
    table = f"{model_name.lower()}s"

    db = DataFlow(db_url, auto_migrate=True, multi_tenant=True)

    Feat = type(model_name, (), {"__annotations__": {"entity_id": str, "score": int}})
    db.model(Feat)

    try:
        await db.initialize()
        db.tenant_context.register_tenant("acme", "A")

        with pytest.raises(RuntimeError, match="no tenant is bound"):
            await db.bulk.bulk_create(model_name, [{"entity_id": "orphan", "score": 1}])

        # Fail-open check: NO row may exist with no bound tenant. The fail-closed
        # raise fires before any INSERT, so the table may legitimately not exist
        # (nothing was ever written) — that is ALSO a pass (zero rows persisted).
        async with test_suite.get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", f"public.{table}"
            )
            rows = await conn.fetch(f'SELECT * FROM "{table}"') if exists else []
        assert (
            rows == []
        ), f"fail-open: a row was persisted with no bound tenant (pg): {rows}"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
