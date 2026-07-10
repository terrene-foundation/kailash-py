# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 2 integration tests — fail-closed tenant guards on the DataFlow fabric
WRITE path (issue #1659) and external-SOURCE path (issue #1658).

Real infrastructure only: a real DataFlow instance on file-backed SQLite,
real ``db.express`` CRUD, a real enforcing ``PipelineContext``, and a real
``MockSource`` (a ``BaseSourceAdapter`` subclass — a protocol-satisfying
deterministic adapter, NOT a unittest.mock). NO mocking.

Coverage:
  #1659 write path — for EACH of create / update / delete / upsert:
    * a cross-tenant attempt is REFUSED (raises FabricTenantScopeError), the
      refusal never exposes another tenant's stored field values / ids, and a
      read-back confirms the other tenant's row was NOT written / mutated /
      deleted;
    * a same-tenant op SUCCEEDS and is verified with a read-back.
  #1658 source path — a multi_tenant product's ctx.source(...) read is
    REFUSED fail-closed; a single-tenant (non-enforcing) context reads the
    source unchanged.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from dataflow import DataFlow
from dataflow.fabric.cache import FabricTenantRequiredError, FabricTenantScopeError
from dataflow.fabric.context import PipelineContext
from dataflow.fabric.testing import MockSource

# ---------------------------------------------------------------------------
# Fixture — real DataFlow on file-backed SQLite with two tenants' rows
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_with_two_tenants():
    """Real DataFlow (file-backed SQLite) with a Deal model and 2 tenants."""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "fabric_write.db"
    db = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)

    @db.model
    class Deal:  # noqa: D401 - test model
        tenant_id: str
        name: str

    await db.initialize()

    await db.express.create("Deal", {"tenant_id": "tenant-a", "name": "a-deal-1"})
    await db.express.create("Deal", {"tenant_id": "tenant-b", "name": "b-deal-1"})

    yield db

    close = getattr(db, "close", None)
    if close is not None:
        result = close()
        if hasattr(result, "__await__"):
            await result


def _enforcing_ctx(db: DataFlow, tenant_id: str) -> PipelineContext:
    """An enforcing multi_tenant PipelineContext bound to ``tenant_id``."""
    return PipelineContext(
        express=db.express,
        sources={},
        products_cache={},
        tenant_id=tenant_id,
        enforce_tenant_scope=True,
    )


async def _row_by_tenant(db: DataFlow, tenant_id: str) -> dict:
    """Discover a tenant's row via the RAW (unenforced) express."""
    rows = await db.express.list("Deal", filter={"tenant_id": tenant_id})
    return rows[0]


# ---------------------------------------------------------------------------
# #1659 create — foreign tenant_id refused; same-tenant + force-inject work
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_cross_tenant_payload_is_refused_no_leak(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")

    with pytest.raises(FabricTenantScopeError) as exc:
        await ctx.express.create("Deal", {"tenant_id": "tenant-b", "name": "intruder"})
    msg = str(exc.value)
    assert "cross-tenant" in msg
    assert isinstance(exc.value, FabricTenantRequiredError)
    # No-leak: the refusal does not expose tenant-b's STORED row values.
    assert "b-deal-1" not in msg

    # Read-back: tenant-b still has exactly its original row (nothing written).
    b_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-b"})
    assert [r["name"] for r in b_rows] == ["b-deal-1"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_same_tenant_succeeds_and_force_injects(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")

    # Explicit own tenant → succeeds.
    await ctx.express.create("Deal", {"tenant_id": "tenant-a", "name": "a-deal-2"})
    # Absent tenant → forced to the bound tenant (never unscoped).
    await ctx.express.create("Deal", {"name": "a-forced"})

    # Read-back: both new rows landed under tenant-a; tenant-b untouched.
    a_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-a"})
    assert sorted(r["name"] for r in a_rows) == ["a-deal-1", "a-deal-2", "a-forced"]
    assert all(r["tenant_id"] == "tenant-a" for r in a_rows)
    b_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-b"})
    assert [r["name"] for r in b_rows] == ["b-deal-1"]


# ---------------------------------------------------------------------------
# #1659 update — cross-tenant PK refused (no leak); same-tenant works
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_cross_tenant_pk_is_refused_no_leak(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    b_id = (await _row_by_tenant(db, "tenant-b"))["id"]

    with pytest.raises(FabricTenantScopeError) as exc:
        await ctx.express.update("Deal", b_id, {"name": "hijacked"})
    msg = str(exc.value)
    assert "cross-tenant" in msg
    # No-leak: the FOREIGN tenant id (from the DB) is fingerprinted, not echoed.
    assert "tenant-b" not in msg
    assert "sha256:" in msg
    assert "tenant-a" in msg  # bound (own) tenant is safe to name

    # Read-back: tenant-b's row is unchanged.
    assert (await _row_by_tenant(db, "tenant-b"))["name"] == "b-deal-1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_foreign_tenant_in_patch_is_refused(db_with_two_tenants):
    """Updating OWN row but attempting to MOVE it to a foreign tenant is refused."""
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    a_id = (await _row_by_tenant(db, "tenant-a"))["id"]

    with pytest.raises(FabricTenantScopeError) as exc:
        await ctx.express.update("Deal", a_id, {"tenant_id": "tenant-b"})
    assert "cross-tenant" in str(exc.value)

    # Read-back: the row still belongs to tenant-a.
    assert (await _row_by_tenant(db, "tenant-a"))["tenant_id"] == "tenant-a"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_same_tenant_succeeds(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    a_id = (await _row_by_tenant(db, "tenant-a"))["id"]

    await ctx.express.update("Deal", a_id, {"name": "a-deal-renamed"})

    # Read-back: the own-tenant update persisted.
    assert (await _row_by_tenant(db, "tenant-a"))["name"] == "a-deal-renamed"


# ---------------------------------------------------------------------------
# #1659 delete — cross-tenant PK refused (no leak); same-tenant works
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_cross_tenant_pk_is_refused_no_leak(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    b_id = (await _row_by_tenant(db, "tenant-b"))["id"]

    with pytest.raises(FabricTenantScopeError) as exc:
        await ctx.express.delete("Deal", b_id)
    msg = str(exc.value)
    assert "cross-tenant" in msg
    assert "tenant-b" not in msg  # foreign id not leaked verbatim
    assert "sha256:" in msg

    # Read-back: tenant-b's row still exists.
    b_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-b"})
    assert [r["name"] for r in b_rows] == ["b-deal-1"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_same_tenant_succeeds(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    a_id = (await _row_by_tenant(db, "tenant-a"))["id"]

    await ctx.express.delete("Deal", a_id)

    # Read-back: the own-tenant row is gone.
    a_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-a"})
    assert a_rows == []


# ---------------------------------------------------------------------------
# #1659 upsert — foreign payload + foreign-PK conflict refused; own works
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_cross_tenant_payload_is_refused_no_leak(db_with_two_tenants):
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")

    with pytest.raises(FabricTenantScopeError) as exc:
        await ctx.express.upsert("Deal", {"tenant_id": "tenant-b", "name": "x"})
    msg = str(exc.value)
    assert "cross-tenant" in msg
    assert "b-deal-1" not in msg

    b_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-b"})
    assert [r["name"] for r in b_rows] == ["b-deal-1"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_foreign_pk_conflict_is_refused_no_leak(db_with_two_tenants):
    """An upsert carrying another tenant's global PK (the UPDATE-by-conflict
    half) is refused before it can overwrite that tenant's row."""
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    b_id = (await _row_by_tenant(db, "tenant-b"))["id"]

    with pytest.raises(FabricTenantScopeError) as exc:
        # tenant_id is force-injected to tenant-a, but the PK targets tenant-b.
        await ctx.express.upsert("Deal", {"id": b_id, "name": "steal"})
    msg = str(exc.value)
    assert "cross-tenant" in msg
    assert "tenant-b" not in msg
    assert "sha256:" in msg

    # Read-back: tenant-b's row is unchanged (not overwritten / reassigned).
    b_row = await _row_by_tenant(db, "tenant-b")
    assert b_row["name"] == "b-deal-1"
    assert b_row["tenant_id"] == "tenant-b"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_same_tenant_own_row_by_pk_succeeds(db_with_two_tenants):
    """A same-tenant upsert conflicting on the caller's OWN PK passes both the
    payload guard and the target-row tenant verify, and persists. (express
    upsert derives its conflict ``where`` from the ``id`` field.)"""
    db = db_with_two_tenants
    ctx = _enforcing_ctx(db, "tenant-a")
    a_id = (await _row_by_tenant(db, "tenant-a"))["id"]

    await ctx.express.upsert(
        "Deal", {"id": a_id, "tenant_id": "tenant-a", "name": "a-ups-updated"}
    )

    # Read-back: the own-tenant upsert persisted; tenant-b untouched.
    assert (await _row_by_tenant(db, "tenant-a"))["name"] == "a-ups-updated"
    b_rows = await db.express.list("Deal", filter={"tenant_id": "tenant-b"})
    assert [r["name"] for r in b_rows] == ["b-deal-1"]


# ---------------------------------------------------------------------------
# #1658 source — multi_tenant product's source read refused; single-tenant OK
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_tenant_product_source_read_is_refused_fail_closed():
    """A multi_tenant product's ctx.source(...) data read is refused
    fail-closed — the fabric cannot prove an external source is tenant-scoped,
    so it never returns unscoped cross-tenant rows (issue #1658)."""
    crm = MockSource("crm", data={"": {"deals": ["cross-tenant-secret"]}})

    ctx = PipelineContext(
        express=None,
        sources={"crm": crm},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,  # multi_tenant product
    )
    handle = ctx.source("crm")

    # Every data method is refused fail-closed.
    for op in (
        lambda: handle.fetch(),
        lambda: handle.fetch_all(),
        lambda: handle.read(),
        lambda: handle.list(),
    ):
        with pytest.raises(FabricTenantScopeError) as exc:
            await op()
        msg = str(exc.value)
        assert "tenant-a" in msg  # bound (own) tenant named
        assert "crm" in msg  # source named
        # No-leak: the un-returned source payload is never in the refusal.
        assert "cross-tenant-secret" not in msg
        assert isinstance(exc.value, FabricTenantRequiredError)

    # fetch_pages is an async generator — refused on first iteration.
    with pytest.raises(FabricTenantScopeError):
        async for _ in handle.fetch_pages():
            pass

    # Metadata accessors carry no row data and stay open.
    assert handle.name == "crm"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_tenant_product_source_write_and_degradation_are_refused():
    """The source ``write`` (async) and ``last_successful_data`` (sync
    degradation) paths are refused fail-closed under enforcement, exactly like
    the read paths — one direct test per variant (issue #1658), so neither
    one-line delegation can regress silently."""
    crm = MockSource("crm", data={"": {"deals": ["cross-tenant-secret"]}})

    ctx = PipelineContext(
        express=None,
        sources={"crm": crm},
        products_cache={},
        tenant_id="tenant-a",
        enforce_tenant_scope=True,  # multi_tenant product
    )
    handle = ctx.source("crm")

    # write (async) is refused before it can touch the adapter.
    with pytest.raises(FabricTenantScopeError) as exc_write:
        await handle.write("deals", {"amount": 100})
    msg_write = str(exc_write.value)
    assert "tenant-a" in msg_write and "crm" in msg_write
    assert "cross-tenant-secret" not in msg_write
    assert isinstance(exc_write.value, FabricTenantRequiredError)

    # last_successful_data (sync degradation helper) is refused too — the
    # cached payload is prior fetched row data.
    with pytest.raises(FabricTenantScopeError) as exc_deg:
        handle.last_successful_data()
    assert "cross-tenant-secret" not in str(exc_deg.value)
    assert isinstance(exc_deg.value, FabricTenantRequiredError)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_single_tenant_product_source_read_is_unaffected():
    """A single-tenant (non-enforcing) context reads the source unchanged —
    no regression for products that are not multi_tenant (issue #1658)."""
    crm = MockSource("crm", data={"": {"deals": [1, 2, 3]}})

    ctx = PipelineContext(
        express=None,
        sources={"crm": crm},
        products_cache={},
        tenant_id=None,
        enforce_tenant_scope=False,  # single-tenant product
    )
    handle = ctx.source("crm")

    data = await handle.fetch()
    assert data == {"deals": [1, 2, 3]}
