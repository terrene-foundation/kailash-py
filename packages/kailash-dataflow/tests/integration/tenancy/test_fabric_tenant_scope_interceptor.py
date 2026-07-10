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

import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from dataflow import DataFlow
from dataflow.fabric.cache import FabricTenantRequiredError, FabricTenantScopeError
from dataflow.fabric.context import PipelineContext
from dataflow.fabric.pipeline import PipelineExecutor

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
