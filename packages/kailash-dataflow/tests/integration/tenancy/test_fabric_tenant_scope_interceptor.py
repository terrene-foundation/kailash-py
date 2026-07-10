# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 2 integration tests — fail-closed tenant-scope interceptor on the
DataFlow fabric READ path (issue #1654).

Real infrastructure only: a real DataFlow instance on file-backed SQLite,
real ``db.express`` CRUD, a real ``PipelineExecutor``, and a real
``PipelineContext``. NO mocking (no unittest.mock / MagicMock / @patch).

The interceptor proves the tenant predicate was ACTUALLY APPLIED to the
executed query before rows are returned — it does not merely trust the
product's ``multi_tenant=True`` declaration. A multi-tenant product read
that omits the tenant predicate (unscoped) or carries a predicate for a
different tenant (cross-tenant) is REFUSED with ``FabricTenantScopeError``
BEFORE the query runs, so unscoped / cross-tenant rows are never returned.

Invariant coverage (issue #1654):
  (1) multi_tenant product without a resolvable tenant scope -> RAISES
      -> test_missing_tenant_scope_is_refused_fail_closed
  (2) tenant predicate provably present on the executed query, else RAISE
      -> test_unscoped_read_leaks_without_guard_then_is_refused (RED->GREEN)
  (3) cross-tenant query attempt -> REFUSED (raises), NOT silently empty
      -> test_cross_tenant_read_is_refused_not_empty
  (4) non-multi_tenant products unaffected (no regression)
      -> test_non_multi_tenant_product_is_unaffected
  (5) the proof inspects the EXECUTED query/params, not the declaration
      -> test_scoped_read_returns_only_own_tenant_rows (predicate proven +
         only own-tenant rows returned) & the RED half of (2)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from dataflow import DataFlow
from dataflow.fabric.cache import FabricTenantRequiredError, FabricTenantScopeError
from dataflow.fabric.config import ProductMode, StalenessPolicy
from dataflow.fabric.context import PipelineContext
from dataflow.fabric.pipeline import PipelineExecutor
from dataflow.fabric.products import ProductRegistration, register_product
from dataflow.fabric.runtime import FabricRuntime
from dataflow.fabric.serving import FabricServingLayer

# ---------------------------------------------------------------------------
# Product functions — real reads through ctx.express (NOT mocks)
# ---------------------------------------------------------------------------


async def _scoped_product(ctx: Any) -> Dict[str, Any]:
    """Correctly-scoped multi-tenant product: filters by the bound tenant."""
    rows = await ctx.express.list("Deal", filter={"tenant_id": ctx.tenant_id})
    return {"deals": sorted(r["name"] for r in rows)}


async def _unscoped_product(ctx: Any) -> Dict[str, Any]:
    """Mis-scoped product: forgets the tenant predicate -> would leak every
    tenant's rows into the caller's tenant cache slot."""
    rows = await ctx.express.list("Deal")
    return {"deals": sorted(r["name"] for r in rows)}


async def _cross_tenant_product(ctx: Any) -> Dict[str, Any]:
    """Adversarial product: bound to one tenant but queries another."""
    rows = await ctx.express.list("Deal", filter={"tenant_id": "tenant-b"})
    return {"deals": sorted(r["name"] for r in rows)}


# ---------------------------------------------------------------------------
# Fixture — real DataFlow on file-backed SQLite with two tenants' rows
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_with_two_tenants():
    """Real DataFlow (file-backed SQLite) with a Deal model and 2 tenants."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "fabric_tenant.db"
    db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    @db.model
    class Deal:  # noqa: D401 - test model
        tenant_id: str
        name: str

    await db.initialize()

    # Two tenants' rows — a genuine cross-tenant dataset.
    await db.express.create("Deal", {"tenant_id": "tenant-a", "name": "a-deal-1"})
    await db.express.create("Deal", {"tenant_id": "tenant-a", "name": "a-deal-2"})
    await db.express.create("Deal", {"tenant_id": "tenant-b", "name": "b-deal-1"})

    yield db

    close = getattr(db, "close", None)
    if close is not None:
        result = close()
        if hasattr(result, "__await__"):
            await result


# ---------------------------------------------------------------------------
# Invariant (2) + (5): the proof inspects the EXECUTED query — RED -> GREEN
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unscoped_read_leaks_without_guard_then_is_refused(db_with_two_tenants):
    """RED->GREEN: the same mis-scoped product leaks cross-tenant rows when
    enforcement is OFF (pre-#1654 behaviour), and is REFUSED when ON."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    # --- RED: without the interceptor the unscoped read returns EVERY
    #     tenant's rows into tenant-a's execution (the cross-tenant leak). ---
    leaky_ctx = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=False,  # pre-#1654: no proof
    )
    leaked = await pipeline.execute_product(
        "deals_unscoped", _unscoped_product, leaky_ctx, tenant_id="tenant-a"
    )
    # tenant-b's row leaked into tenant-a's product result.
    assert "b-deal-1" in leaked.data["deals"]
    assert leaked.data["deals"] == ["a-deal-1", "a-deal-2", "b-deal-1"]

    # --- GREEN: with the interceptor the SAME unscoped read is refused
    #     BEFORE the query runs — no unscoped rows are ever returned. ---
    guarded_ctx = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,  # #1654: prove the predicate
    )
    with pytest.raises(FabricTenantScopeError) as exc:
        await pipeline.execute_product(
            "deals_unscoped", _unscoped_product, guarded_ctx, tenant_id="tenant-a"
        )
    # The proof cites the executed query's filter, not the declaration.
    assert "did not carry" in str(exc.value)
    assert "tenant_id" in str(exc.value)


# ---------------------------------------------------------------------------
# Invariant (5): scoped read proves the predicate + returns only own rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scoped_read_returns_only_own_tenant_rows(db_with_two_tenants):
    """A correctly-scoped multi-tenant product returns ONLY the bound
    tenant's rows, and the executed query provably carried the predicate
    (proven by the read succeeding under enforcement)."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    ctx = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    result = await pipeline.execute_product(
        "deals_scoped", _scoped_product, ctx, tenant_id="tenant-a"
    )
    # Only tenant-a's rows — tenant-b never appears.
    assert result.data["deals"] == ["a-deal-1", "a-deal-2"]
    assert "b-deal-1" not in result.data["deals"]

    # State-persistence read-back: the tenant-a result is cached under
    # tenant-a's slot (per-tenant cache partition).
    cached = await pipeline.get_cached("deals_scoped", tenant_id="tenant-a")
    assert cached is not None


# ---------------------------------------------------------------------------
# Invariant (3): cross-tenant attempt is REFUSED, not silently empty
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_tenant_read_is_refused_not_empty(db_with_two_tenants):
    """A tenant-a execution that queries tenant-b's scope RAISES — it does
    NOT silently return an empty/filtered result."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    ctx = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    with pytest.raises(FabricTenantScopeError) as exc:
        await pipeline.execute_product(
            "deals_cross", _cross_tenant_product, ctx, tenant_id="tenant-a"
        )
    assert "cross-tenant" in str(exc.value)
    # It is a tenant-isolation failure of the shared family.
    assert isinstance(exc.value, FabricTenantRequiredError)


# ---------------------------------------------------------------------------
# Invariant (1): multi_tenant product without a resolvable tenant -> RAISES
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_tenant_scope_is_refused_fail_closed():
    """Building an enforcing multi-tenant context with no resolved tenant
    is itself refused fail-closed — the proof can never be silently
    disabled by a missing tenant."""
    with pytest.raises(FabricTenantScopeError):
        PipelineContext(
            express=None,
            sources={},
            products_cache={},
            tenant_id=None,
            enforce_tenant_scope=True,
        )


# ---------------------------------------------------------------------------
# Invariant (4): non-multi_tenant products are unaffected (no regression)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_multi_tenant_product_is_unaffected(db_with_two_tenants):
    """A single-tenant (non-multi_tenant) product reads without a tenant
    predicate exactly as before — enforcement is OFF, no raise."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    ctx = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id=None,
        enforce_tenant_scope=False,  # single-tenant product
    )
    result = await pipeline.execute_product("deals_all", _unscoped_product, ctx)
    # Returns all rows, no raise — behaviour unchanged for single-tenant.
    assert result.data["deals"] == ["a-deal-1", "a-deal-2", "b-deal-1"]


# ---------------------------------------------------------------------------
# Redteam finding 1: ctx.express.read() by PK is tenant-verified post-fetch
# ---------------------------------------------------------------------------


async def _read_by_id_product(ctx: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Read a single Deal by PK (the record_id arrives via params)."""
    row = await ctx.express.read("Deal", params["id"])
    return {"deal": row}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_by_pk_cross_tenant_is_refused(db_with_two_tenants):
    """A multi_tenant product reading another tenant's row by global PK is
    REFUSED post-fetch (no row returned); own-tenant PK read still works."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    # Raw express (no enforcement) to discover each tenant's row PK.
    a_id = (await db.express.list("Deal", filter={"tenant_id": "tenant-a"}))[0]["id"]
    b_id = (await db.express.list("Deal", filter={"tenant_id": "tenant-b"}))[0]["id"]

    # Own-tenant PK read succeeds under enforcement.
    ctx_ok = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    ok = await pipeline.execute_product(
        "read_own",
        _read_by_id_product,
        ctx_ok,
        params={"id": a_id},
        tenant_id="tenant-a",
    )
    assert ok.data["deal"]["tenant_id"] == "tenant-a"

    # Cross-tenant PK read (tenant-a fetching tenant-b's PK) → refused.
    ctx_x = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    with pytest.raises(FabricTenantScopeError) as exc:
        await pipeline.execute_product(
            "read_cross",
            _read_by_id_product,
            ctx_x,
            params={"id": b_id},
            tenant_id="tenant-a",
        )
    assert "post-fetch" in str(exc.value)


# ---------------------------------------------------------------------------
# Redteam finding 2: empty / whitespace tenant is fail-closed like None
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_or_blank_tenant_is_refused_like_none():
    """An empty/whitespace tenant is NOT a valid scope — refused at BOTH
    context construction AND serving-layer extraction (issue #1654 f2)."""
    # (a) enforcing context construction with a blank tenant → refused.
    for blank in ("", "   ", "\t"):
        with pytest.raises(FabricTenantScopeError):
            PipelineContext(
                express=None,
                sources={},
                products_cache={},
                tenant_id=blank,
                enforce_tenant_scope=True,
            )

    # (b) serving-layer extraction normalizes blank → None (so the existing
    # multi_tenant guard rejects it as a missing tenant, never a shared
    # pseudo-tenant).
    serving = FabricServingLayer(
        products={},
        pipeline_executor=None,
        tenant_extractor=lambda r: r.headers.get("X-Tenant-Id", ""),
    )

    class _Req:
        def __init__(self, headers):
            self.headers = headers

    assert serving._extract_tenant(_Req({})) is None  # header absent → ""
    assert serving._extract_tenant(_Req({"X-Tenant-Id": "  "})) is None  # blank
    assert serving._extract_tenant(_Req({"X-Tenant-Id": "tenant-a"})) == "tenant-a"


# ---------------------------------------------------------------------------
# Redteam finding 3: multi_tenant=False over a tenant-column model WARNs loud
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_tenant_false_over_tenant_column_model_warns(caplog):
    """Declaring a product multi_tenant=False over a model that HAS a
    tenant_id column emits a LOUD warning (enforcement silently disabled).
    A model with no tenant_id column does NOT warn."""
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    @db.model
    class Widget:  # noqa: D401 - test model (has tenant_id)
        tenant_id: str
        name: str

    @db.model
    class Gadget:  # noqa: D401 - test model (NO tenant_id)
        name: str

    products: Dict[str, ProductRegistration] = {}

    async def _p(ctx: Any) -> Dict[str, Any]:
        return {}

    with caplog.at_level(logging.WARNING):
        register_product(
            products=products,
            models=db._models,
            sources={},
            name="widgets",
            fn=_p,
            mode="materialized",
            depends_on=["Widget"],
            multi_tenant=False,
        )
        register_product(
            products=products,
            models=db._models,
            sources={},
            name="gadgets",
            fn=_p,
            mode="materialized",
            depends_on=["Gadget"],
            multi_tenant=False,
        )

    warns = [
        r
        for r in caplog.records
        if r.getMessage() == "fabric.product.tenant_enforcement_disabled"
    ]
    # Exactly the tenant-column model warns; the plain model does not.
    assert len(warns) == 1
    assert warns[0].product == "widgets"
    assert warns[0].model == "Widget"


# ---------------------------------------------------------------------------
# Redteam finding 4: $or / filtering-kwarg cannot bypass the tenant proof
# ---------------------------------------------------------------------------


async def _or_filter_product(ctx: Any) -> Dict[str, Any]:
    """Correct top-level tenant_id BUT a sibling $or that can re-admit
    other tenants."""
    rows = await ctx.express.list(
        "Deal",
        filter={
            "tenant_id": ctx.tenant_id,
            "$or": [{"name": "a-deal-1"}, {"name": "b-deal-1"}],
        },
    )
    return {"deals": [r["name"] for r in rows]}


async def _kwarg_filter_product(ctx: Any) -> Dict[str, Any]:
    """Correct filter BUT a filtering **kwarg forwarded to express."""
    rows = await ctx.express.list(
        "Deal", filter={"tenant_id": ctx.tenant_id}, where="1=1"
    )
    return {"deals": [r["name"] for r in rows]}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_operator_filter_and_filtering_kwarg_are_refused(db_with_two_tenants):
    """On an enforced read, a top-level $or operator key OR a filtering
    **kwarg is refused even when the scalar tenant_id is correct."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    ctx_or = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    with pytest.raises(FabricTenantScopeError) as exc_or:
        await pipeline.execute_product(
            "or_prod", _or_filter_product, ctx_or, tenant_id="tenant-a"
        )
    assert "operator" in str(exc_or.value)

    ctx_kw = PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,
    )
    with pytest.raises(FabricTenantScopeError) as exc_kw:
        await pipeline.execute_product(
            "kwarg_prod", _kwarg_filter_product, ctx_kw, tenant_id="tenant-a"
        )
    assert "kwarg" in str(exc_kw.value)


# ---------------------------------------------------------------------------
# Redteam finding 5 (wiring): the serving-layer handler wires enforcement
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_serving_handler_wires_enforcement_for_multi_tenant_product(
    db_with_two_tenants,
):
    """The real FabricServingLayer handler builds an ENFORCING context for a
    multi_tenant product (enforce_tenant_scope=product.multi_tenant): a
    mis-scoped product returns no rows (fail-closed), a correctly-scoped one
    returns only its own tenant's rows."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    def _extractor(req: Any) -> Any:
        return getattr(req, "tenant", None)

    class _Req:
        def __init__(self, query_params, tenant):
            self.query_params = query_params
            self.tenant = tenant

    # (a) mis-scoped multi_tenant product, forced fresh via ?refresh=true.
    reg_bad = ProductRegistration(
        name="deals_unscoped_serve",
        fn=_unscoped_product,
        mode=ProductMode.MATERIALIZED,
        depends_on=["Deal"],
        staleness=StalenessPolicy(),
        multi_tenant=True,
    )
    serving_bad = FabricServingLayer(
        products={"deals_unscoped_serve": reg_bad},
        pipeline_executor=pipeline,
        express=db.express,
        sources={},
        tenant_extractor=_extractor,
    )
    handler_bad = serving_bad._make_product_handler("deals_unscoped_serve", reg_bad)
    resp_bad = await handler_bad(request=_Req({"refresh": "true"}, "tenant-a"))
    # Enforcement fired inside execute_product → refresh failed → 500, NO
    # rows. Without the wiring this would be 200 with all-tenant data.
    assert resp_bad["_status"] == 500
    assert "data" not in resp_bad

    # (b) correctly-scoped multi_tenant product → 200 with only own rows.
    reg_ok = ProductRegistration(
        name="deals_scoped_serve",
        fn=_scoped_product,
        mode=ProductMode.MATERIALIZED,
        depends_on=["Deal"],
        staleness=StalenessPolicy(),
        multi_tenant=True,
    )
    serving_ok = FabricServingLayer(
        products={"deals_scoped_serve": reg_ok},
        pipeline_executor=pipeline,
        express=db.express,
        sources={},
        tenant_extractor=_extractor,
    )
    handler_ok = serving_ok._make_product_handler("deals_scoped_serve", reg_ok)
    resp_ok = await handler_ok(request=_Req({"refresh": "true"}, "tenant-a"))
    assert resp_ok["_status"] == 200
    assert resp_ok["data"]["deals"] == ["a-deal-1", "a-deal-2"]


# ---------------------------------------------------------------------------
# Redteam finding 5 (prewarm): _prewarm_products_serial skips multi_tenant
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prewarm_serial_skips_multi_tenant(db_with_two_tenants):
    """Dev-mode serial pre-warm SKIPS multi_tenant products — it never runs
    their unscoped all-tenant query nor writes an untenanted cache entry."""
    db = db_with_two_tenants
    pipeline = PipelineExecutor(dataflow=db, dev_mode=True)

    executed: list[str] = []

    async def _recording_product(ctx: Any) -> Dict[str, Any]:
        executed.append("ran")
        rows = await ctx.express.list("Deal")  # unscoped — would leak if run
        return {"deals": [r["name"] for r in rows]}

    reg = ProductRegistration(
        name="mt_prewarm",
        fn=_recording_product,
        mode=ProductMode.MATERIALIZED,
        depends_on=["Deal"],
        staleness=StalenessPolicy(),
        multi_tenant=True,
    )
    runtime = FabricRuntime(
        dataflow=db,
        sources={},
        products={"mt_prewarm": reg},
        dev_mode=True,
        tenant_extractor=lambda r: None,
    )
    runtime._pipeline = pipeline

    await runtime._prewarm_products_serial()

    # The multi_tenant product was skipped: fn never ran, no cache written.
    assert executed == []
    assert await pipeline.get_cached("mt_prewarm", tenant_id=None) is None
