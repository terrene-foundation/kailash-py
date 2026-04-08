# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 2 integration tests for ``RedisFabricCacheBackend``.

These tests require a real Redis instance reachable at the URL exposed
by ``FABRIC_TEST_REDIS_URL`` (defaults to ``redis://localhost:6380/0``,
matching the impact-verse docker compose layout this repo uses for
local development). When the URL is unreachable the entire module is
skipped — these are integration tests, not unit tests.

Per ``rules/testing.md`` Tier 2 prohibits ``unittest.mock``. Every test
in this file talks to a real Redis.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest

from dataflow.fabric.cache import RedisFabricCacheBackend, _FabricCacheEntry

REDIS_URL = os.environ.get("FABRIC_TEST_REDIS_URL", "redis://localhost:6380/0")


# ---------------------------------------------------------------------------
# Module-level skip when Redis is unreachable
# ---------------------------------------------------------------------------


def _redis_reachable(url: str) -> bool:
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=0.5)
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _redis_reachable(REDIS_URL),
        reason=f"Redis not reachable at {REDIS_URL}",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def redis_client():
    """Yield a fresh async Redis client and flush its keyspace after."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(REDIS_URL, decode_responses=False)
    yield client
    try:
        await client.flushdb()
    finally:
        await client.aclose()


@pytest.fixture
async def backend(redis_client):
    return RedisFabricCacheBackend(
        redis_client=redis_client,
        key_prefix="fabric_test",
        instance_name="test_instance",
        ttl_seconds=3600,
        redis_url_for_logging=REDIS_URL,
    )


def _entry(
    product_name: str = "p1",
    tenant_id: str | None = None,
    payload: bytes = b"hello",
    content_hash: str = "h1",
    cached_at: datetime | None = None,
    run_started_at: datetime | None = None,
    metadata: dict | None = None,
) -> _FabricCacheEntry:
    now = datetime.now(timezone.utc)
    return _FabricCacheEntry(
        product_name=product_name,
        tenant_id=tenant_id,
        data_bytes=payload,
        content_hash=content_hash,
        metadata=metadata or {"pipeline_ms": 12.0, "run_id": "abc"},
        cached_at=cached_at or now,
        run_started_at=run_started_at or (now - timedelta(seconds=1)),
        size_bytes=len(payload),
    )


# ---------------------------------------------------------------------------
# Basic write + read
# ---------------------------------------------------------------------------


async def test_redis_backend_writes_and_reads(backend):
    written = await backend.set("p1", _entry())
    assert written is True

    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.data_bytes == b"hello"
    assert fetched.content_hash == "h1"
    assert fetched.metadata.get("pipeline_ms") == 12.0


async def test_redis_backend_get_returns_none_when_missing(backend):
    assert await backend.get("nope") is None
    assert await backend.get_hash("nope") is None
    assert await backend.get_metadata("nope") is None


async def test_redis_backend_get_hash_fast_path(backend):
    await backend.set("p1", _entry(content_hash="abc123"))
    assert await backend.get_hash("p1") == "abc123"


async def test_redis_backend_get_metadata_no_payload_transfer(backend):
    """Verify get_metadata returns the metadata-only fields (not payload)."""
    big_payload = b"x" * 100_000  # 100 KB
    await backend.set(
        "big",
        _entry(payload=big_payload, content_hash="h-big", metadata={"size": "big"}),
    )

    meta = await backend.get_metadata("big")
    assert meta is not None
    assert meta["content_hash"] == "h-big"
    assert meta["size_bytes"] == 100_000
    assert isinstance(meta["cached_at"], datetime)
    assert isinstance(meta["run_started_at"], datetime)
    # Metadata response must NOT include the payload
    assert "data_bytes" not in meta


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


async def test_redis_backend_tenant_isolation(backend):
    """Two tenants writing the same product name MUST get separate entries."""
    await backend.set(
        "tenant-a:portfolio",
        _entry(
            product_name="portfolio",
            tenant_id="tenant-a",
            payload=b"a-data",
            content_hash="ha",
        ),
    )
    await backend.set(
        "tenant-b:portfolio",
        _entry(
            product_name="portfolio",
            tenant_id="tenant-b",
            payload=b"b-data",
            content_hash="hb",
        ),
    )

    a = await backend.get("tenant-a:portfolio")
    b = await backend.get("tenant-b:portfolio")
    assert a is not None and a.data_bytes == b"a-data"
    assert b is not None and b.data_bytes == b"b-data"
    assert a.tenant_id == "tenant-a"
    assert b.tenant_id == "tenant-b"


async def test_redis_backend_instance_name_prefix_isolation(redis_client):
    """Two backends with different instance names share Redis without colliding."""
    backend_a = RedisFabricCacheBackend(
        redis_client=redis_client,
        key_prefix="fabric_test",
        instance_name="instance_a",
    )
    backend_b = RedisFabricCacheBackend(
        redis_client=redis_client,
        key_prefix="fabric_test",
        instance_name="instance_b",
    )

    await backend_a.set("p1", _entry(payload=b"from-a"))
    await backend_b.set("p1", _entry(payload=b"from-b"))

    a = await backend_a.get("p1")
    b = await backend_b.get("p1")
    assert a is not None and a.data_bytes == b"from-a"
    assert b is not None and b.data_bytes == b"from-b"


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


async def test_redis_backend_invalidate_removes_key(backend):
    await backend.set("p1", _entry())
    assert await backend.get("p1") is not None
    await backend.invalidate("p1")
    assert await backend.get("p1") is None


async def test_redis_backend_invalidate_all_clears_everything(backend):
    for k in ("a", "b", "c"):
        await backend.set(k, _entry(product_name=k))

    await backend.invalidate_all()

    for k in ("a", "b", "c"):
        assert await backend.get(k) is None


async def test_redis_backend_invalidate_all_with_prefix(backend):
    await backend.set("tenant-a:p1", _entry(tenant_id="tenant-a"))
    await backend.set("tenant-a:p2", _entry(tenant_id="tenant-a"))
    await backend.set("tenant-b:p1", _entry(tenant_id="tenant-b"))

    await backend.invalidate_all(prefix="tenant-a:")

    assert await backend.get("tenant-a:p1") is None
    assert await backend.get("tenant-a:p2") is None
    assert await backend.get("tenant-b:p1") is not None


# ---------------------------------------------------------------------------
# Write CAS by run_started_at
# ---------------------------------------------------------------------------


async def test_redis_backend_cas_rejects_older_writer(backend):
    """Replica A starts at T=0 (slow), replica B starts at T=5 and writes
    first. Replica A's older write MUST be refused so the newer-but-faster
    writer wins. Closes the R3 last-writer-wins race.
    """
    t0 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t5 = t0 + timedelta(seconds=5)

    written_b = await backend.set(
        "p1",
        _entry(
            content_hash="hash-B",
            run_started_at=t5,
            payload=b"newer-data",
        ),
    )
    assert written_b is True

    written_a = await backend.set(
        "p1",
        _entry(
            content_hash="hash-A",
            run_started_at=t0,
            payload=b"older-data",
        ),
    )
    assert written_a is False, "older writer must be rejected by CAS"

    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.content_hash == "hash-B"
    assert fetched.data_bytes == b"newer-data"


async def test_redis_backend_cas_accepts_newer_writer(backend):
    t0 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t5 = t0 + timedelta(seconds=5)

    await backend.set("p1", _entry(run_started_at=t0, content_hash="old"))
    written = await backend.set("p1", _entry(run_started_at=t5, content_hash="new"))
    assert written is True

    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.content_hash == "new"


# ---------------------------------------------------------------------------
# Multi-replica read (simulates a hot cache shared across replicas)
# ---------------------------------------------------------------------------


async def test_redis_backend_multi_replica_read(redis_client):
    """Replica A writes; replica B reads via the same Redis instance."""
    replica_a = RedisFabricCacheBackend(
        redis_client=redis_client,
        key_prefix="fabric_test",
        instance_name="shared",
    )
    replica_b = RedisFabricCacheBackend(
        redis_client=redis_client,
        key_prefix="fabric_test",
        instance_name="shared",
    )

    await replica_a.set("p1", _entry(payload=b"shared-data"))

    fetched = await replica_b.get("p1")
    assert fetched is not None
    assert fetched.data_bytes == b"shared-data"


# ---------------------------------------------------------------------------
# Schema version round-trip
# ---------------------------------------------------------------------------


async def test_redis_backend_schema_version_round_trips(backend):
    await backend.set("p1", _entry())
    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.schema_version == 2


# ---------------------------------------------------------------------------
# Concurrency: many writers same key
# ---------------------------------------------------------------------------


async def test_redis_backend_concurrent_writers_cas_total_ordering(backend):
    """Two concurrent writers; whichever has the later run_started_at wins."""
    t0 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    later = t0 + timedelta(seconds=10)
    earlier = t0 + timedelta(seconds=1)

    async def write_later():
        return await backend.set(
            "race",
            _entry(content_hash="late", run_started_at=later, payload=b"late"),
        )

    async def write_earlier():
        return await backend.set(
            "race",
            _entry(content_hash="early", run_started_at=earlier, payload=b"early"),
        )

    results = await asyncio.gather(write_later(), write_earlier())
    # At least one write succeeded
    assert any(results)
    fetched = await backend.get("race")
    assert fetched is not None
    # The later run_started_at MUST be the durable winner.
    assert fetched.content_hash == "late"
    assert fetched.data_bytes == b"late"
