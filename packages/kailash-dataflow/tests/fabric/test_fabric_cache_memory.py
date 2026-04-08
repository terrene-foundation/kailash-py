# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 tests for ``InMemoryFabricCacheBackend``.

Covers basic get/set, LRU eviction, dedup via ``get_hash``, tenant
isolation through cache-key construction, write CAS by ``run_started_at``,
``invalidate_all`` with prefix, and the ``FabricTenantRequiredError`` raise
path that callers use for ``multi_tenant=True`` products.

These tests are mocking-allowed (Tier 1) but use no MagicMock — the
backend is a pure asyncio data structure with no external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dataflow.fabric.cache import (
    FabricTenantRequiredError,
    InMemoryFabricCacheBackend,
    _FabricCacheEntry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    product_name: str = "p1",
    tenant_id: str | None = None,
    payload: bytes = b"hello",
    content_hash: str = "h1",
    cached_at: datetime | None = None,
    run_started_at: datetime | None = None,
    metadata: dict | None = None,
) -> _FabricCacheEntry:
    now = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    return _FabricCacheEntry(
        product_name=product_name,
        tenant_id=tenant_id,
        data_bytes=payload,
        content_hash=content_hash,
        metadata=metadata or {"pipeline_ms": 12, "run_id": "abc"},
        cached_at=cached_at or now,
        run_started_at=run_started_at or (now - timedelta(seconds=1)),
        size_bytes=len(payload),
    )


def _cache_key(product_name: str, tenant_id: str | None = None) -> str:
    """Reproduce the caller-side key shape used by PipelineExecutor."""
    if tenant_id is not None:
        return f"{tenant_id}:{product_name}"
    return product_name


# ---------------------------------------------------------------------------
# Basic get/set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_basic_get_set() -> None:
    backend = InMemoryFabricCacheBackend()
    entry = _make_entry()

    written = await backend.set(_cache_key("p1"), entry)
    assert written is True

    fetched = await backend.get(_cache_key("p1"))
    assert fetched is not None
    assert fetched.data_bytes == b"hello"
    assert fetched.content_hash == "h1"
    assert fetched.metadata["pipeline_ms"] == 12


@pytest.mark.asyncio
async def test_in_memory_backend_get_returns_none_when_missing() -> None:
    backend = InMemoryFabricCacheBackend()
    assert await backend.get("nope") is None
    assert await backend.get_hash("nope") is None
    assert await backend.get_metadata("nope") is None


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_lru_eviction_at_max_entries() -> None:
    backend = InMemoryFabricCacheBackend(max_entries=3)
    for i in range(5):
        await backend.set(f"k{i}", _make_entry(product_name=f"p{i}"))

    assert len(backend) == 3
    # Oldest two were evicted
    assert await backend.get("k0") is None
    assert await backend.get("k1") is None
    # Newest three remain
    assert await backend.get("k2") is not None
    assert await backend.get("k3") is not None
    assert await backend.get("k4") is not None


@pytest.mark.asyncio
async def test_in_memory_backend_get_promotes_to_mru() -> None:
    """Reading a key marks it most-recently-used so it survives the next eviction."""
    backend = InMemoryFabricCacheBackend(max_entries=3)
    await backend.set("a", _make_entry(product_name="a"))
    await backend.set("b", _make_entry(product_name="b"))
    await backend.set("c", _make_entry(product_name="c"))

    # Read "a" → promote it
    await backend.get("a")
    # Insert one more → "b" should be evicted, not "a"
    await backend.set("d", _make_entry(product_name="d"))

    assert await backend.get("a") is not None
    assert await backend.get("b") is None
    assert await backend.get("c") is not None
    assert await backend.get("d") is not None


# ---------------------------------------------------------------------------
# Dedup via get_hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_dedup_on_unchanged_hash() -> None:
    """Callers compare get_hash() before set() — verify the fast path works."""
    backend = InMemoryFabricCacheBackend()
    e1 = _make_entry(content_hash="hash-X")
    await backend.set("p1", e1)

    # Caller computes a new hash and compares
    cached_hash = await backend.get_hash("p1")
    assert cached_hash == "hash-X"

    # Same content → caller skips the set; no entry change
    e2 = _make_entry(
        content_hash="hash-X",
        run_started_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
    )
    # We DO call set here to verify CAS allows newer writes (and that
    # data does not change because the same payload is being set).
    written = await backend.set("p1", e2)
    assert written is True
    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.run_started_at == datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tenant isolation (key-based)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_tenant_isolation() -> None:
    """Two tenants writing to the same product name MUST get separate entries."""
    backend = InMemoryFabricCacheBackend()
    tenant_a_key = _cache_key("portfolio", tenant_id="tenant-a")
    tenant_b_key = _cache_key("portfolio", tenant_id="tenant-b")

    await backend.set(
        tenant_a_key,
        _make_entry(
            product_name="portfolio",
            tenant_id="tenant-a",
            payload=b"a-data",
            content_hash="ha",
        ),
    )
    await backend.set(
        tenant_b_key,
        _make_entry(
            product_name="portfolio",
            tenant_id="tenant-b",
            payload=b"b-data",
            content_hash="hb",
        ),
    )

    a = await backend.get(tenant_a_key)
    b = await backend.get(tenant_b_key)
    assert a is not None and a.data_bytes == b"a-data"
    assert b is not None and b.data_bytes == b"b-data"
    # Critically, no cross-tenant leakage
    assert a.content_hash != b.content_hash


# ---------------------------------------------------------------------------
# Invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_invalidate_removes_key() -> None:
    backend = InMemoryFabricCacheBackend()
    await backend.set("p1", _make_entry())
    assert await backend.get("p1") is not None
    await backend.invalidate("p1")
    assert await backend.get("p1") is None
    # Idempotent
    await backend.invalidate("p1")


@pytest.mark.asyncio
async def test_in_memory_backend_invalidate_all_clears_everything() -> None:
    backend = InMemoryFabricCacheBackend()
    for k in ("a", "b", "c"):
        await backend.set(k, _make_entry(product_name=k))
    await backend.invalidate_all()
    assert len(backend) == 0


@pytest.mark.asyncio
async def test_in_memory_backend_invalidate_all_with_prefix() -> None:
    backend = InMemoryFabricCacheBackend()
    await backend.set(
        "tenant-a:p1", _make_entry(product_name="p1", tenant_id="tenant-a")
    )
    await backend.set(
        "tenant-a:p2", _make_entry(product_name="p2", tenant_id="tenant-a")
    )
    await backend.set(
        "tenant-b:p1", _make_entry(product_name="p1", tenant_id="tenant-b")
    )

    await backend.invalidate_all(prefix="tenant-a:")

    assert await backend.get("tenant-a:p1") is None
    assert await backend.get("tenant-a:p2") is None
    assert await backend.get("tenant-b:p1") is not None


# ---------------------------------------------------------------------------
# CAS by run_started_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_cas_rejects_older_write() -> None:
    """Replica A starts at T=0 (slow), replica B starts at T=5 and writes
    first. When replica A tries to write at T=10, the older entry MUST be
    refused so the newer-but-faster writer wins.
    """
    backend = InMemoryFabricCacheBackend()

    t0 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t5 = t0 + timedelta(seconds=5)

    # Replica B writes first (newer run_started_at)
    written_b = await backend.set(
        "p1",
        _make_entry(
            content_hash="hash-B",
            run_started_at=t5,
            payload=b"newer-data",
        ),
    )
    assert written_b is True

    # Replica A tries to write its older result
    written_a = await backend.set(
        "p1",
        _make_entry(
            content_hash="hash-A",
            run_started_at=t0,
            payload=b"older-data",
        ),
    )
    assert written_a is False, "older writer must be rejected"

    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.content_hash == "hash-B"
    assert fetched.data_bytes == b"newer-data"


@pytest.mark.asyncio
async def test_in_memory_backend_cas_accepts_newer_write() -> None:
    backend = InMemoryFabricCacheBackend()
    t0 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t5 = t0 + timedelta(seconds=5)

    await backend.set("p1", _make_entry(run_started_at=t0, content_hash="old"))
    written = await backend.set(
        "p1", _make_entry(run_started_at=t5, content_hash="new")
    )
    assert written is True
    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.content_hash == "new"


# ---------------------------------------------------------------------------
# Multi-tenant invariant — caller raises FabricTenantRequiredError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_tenant_without_tenant_id_raises() -> None:
    """Simulate the caller-side enforcement.

    The PipelineExecutor enforces this invariant before calling the
    backend. The backend itself does not know which products are
    multi_tenant, so the test verifies the canonical caller pattern.
    """

    def lookup(product_name: str, tenant_id: str | None, multi_tenant: bool) -> str:
        if multi_tenant and tenant_id is None:
            raise FabricTenantRequiredError(
                f"Product '{product_name}' is multi_tenant=True but no "
                f"tenant_id was supplied at lookup time."
            )
        return _cache_key(product_name, tenant_id)

    # Multi-tenant product without tenant — must raise
    with pytest.raises(FabricTenantRequiredError) as exc_info:
        lookup("portfolio", tenant_id=None, multi_tenant=True)
    assert "portfolio" in str(exc_info.value)
    assert "tenant_id" in str(exc_info.value)

    # Multi-tenant product WITH tenant — fine
    assert lookup("portfolio", tenant_id="tenant-a", multi_tenant=True) == (
        "tenant-a:portfolio"
    )

    # Non-multi-tenant product without tenant — fine
    assert lookup("dashboard", tenant_id=None, multi_tenant=False) == "dashboard"


# ---------------------------------------------------------------------------
# Metadata fast path returns the same fields as the entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_backend_get_metadata_returns_payload_independent_fields() -> (
    None
):
    backend = InMemoryFabricCacheBackend()
    now = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    await backend.set(
        "p1",
        _make_entry(
            cached_at=now,
            run_started_at=now - timedelta(seconds=1),
            content_hash="hh",
        ),
    )
    meta = await backend.get_metadata("p1")
    assert meta is not None
    assert meta["cached_at"] == now
    assert meta["content_hash"] == "hh"
    assert meta["run_started_at"] == now - timedelta(seconds=1)
    assert meta["schema_version"] == 2
    assert meta["size_bytes"] == 5  # len(b"hello")
