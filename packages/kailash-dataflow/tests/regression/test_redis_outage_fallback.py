# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression: ``RedisFabricCacheBackend`` MUST degrade gracefully when
Redis becomes unreachable mid-operation, and recover automatically.

Per ``workspaces/issue-354/04-validate/01-red-team-findings.md``
amendment D: ``get``/``set``/``invalidate`` wrap Redis operations in
try/except for ``ConnectionError``/``TimeoutError`` and:
1. WARN log the masked URL + error class
2. Increment ``fabric_cache_errors_total``
3. Flip ``fabric_cache_degraded{backend=redis}=1``
4. Return ``None`` (get) or ``False`` (set), never raise
5. Flip the gauge back to 0 on the next successful op

This test exercises the fallback path with a fault-injection client
that raises ``ConnectionError`` on demand. We use a fault-injecting
client (not a mock) so the real backend code path runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from dataflow.fabric.cache import RedisFabricCacheBackend, _FabricCacheEntry

# ---------------------------------------------------------------------------
# Fault-injection Redis client — NOT a mock; real callable surface that
# raises a real ConnectionError when armed. Compatible with the subset of
# the redis.asyncio.Redis API the backend uses.
# ---------------------------------------------------------------------------


class _FaultInjectingRedisClient:
    """A minimal async Redis-like client that supports fault injection.

    Stores hashes in a dict so the backend's CRUD path is exercised end
    to end. Methods that the backend calls: ``script_load``, ``evalsha``,
    ``hgetall``, ``hget``, ``hmget``, ``delete``, ``scan``.

    The ``armed`` flag, when set, causes every call to raise
    ``ConnectionError("simulated outage")``.
    """

    def __init__(self) -> None:
        self.armed: bool = False
        self._hashes: dict[str, dict[str, Any]] = {}
        self._scripts: dict[str, str] = {}
        self._next_sha = 0

    def _check(self) -> None:
        if self.armed:
            raise ConnectionError("simulated outage")

    async def script_load(self, script: str) -> str:
        self._check()
        self._next_sha += 1
        sha = f"sha-{self._next_sha}"
        self._scripts[sha] = script
        return sha

    async def evalsha(self, sha: str, num_keys: int, *argv: Any) -> int:
        self._check()
        # Single-key CAS script: KEYS[1] = full key
        key = argv[0]
        incoming_ts = argv[1]  # ARGV[1]
        # Field/value pairs are argv[2 .. -2]; ttl is argv[-1].
        existing = self._hashes.get(key, {})
        existing_ts = existing.get("run_started_at")
        if isinstance(existing_ts, bytes):
            existing_ts = existing_ts.decode("utf-8")
        if existing_ts is not None and existing_ts > incoming_ts:
            return 0
        # Build new hash
        new_hash: dict[str, Any] = {}
        i = 2
        while i < len(argv) - 1:
            field = argv[i]
            value = argv[i + 1]
            if isinstance(field, bytes):
                field = field.decode("utf-8")
            new_hash[field] = value
            i += 2
        self._hashes[key] = new_hash
        return 1

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        self._check()
        raw = self._hashes.get(key)
        if not raw:
            return {}
        return {
            (k.encode("utf-8") if isinstance(k, str) else k): (
                v if isinstance(v, (bytes, bytearray)) else (str(v).encode("utf-8"))
            )
            for k, v in raw.items()
        }

    async def hget(self, key: str, field: str) -> Any:
        self._check()
        raw = self._hashes.get(key)
        if not raw:
            return None
        value = raw.get(field)
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return str(value).encode("utf-8")

    async def hmget(self, key: str, *fields: str) -> list[Any]:
        self._check()
        raw = self._hashes.get(key, {})
        out = []
        for f in fields:
            value = raw.get(f)
            if value is None:
                out.append(None)
            elif isinstance(value, (bytes, bytearray)):
                out.append(bytes(value))
            else:
                out.append(str(value).encode("utf-8"))
        return out

    async def delete(self, *keys: str) -> int:
        self._check()
        count = 0
        for k in keys:
            if k in self._hashes:
                del self._hashes[k]
                count += 1
        return count

    async def scan(self, cursor: int = 0, match: str = "*", count: int = 100) -> tuple:
        self._check()
        import fnmatch

        keys = [k for k in self._hashes.keys() if fnmatch.fnmatch(k, match)]
        return 0, keys


def _entry(
    payload: bytes = b"hello",
    content_hash: str = "h1",
    run_started_at: datetime | None = None,
) -> _FabricCacheEntry:
    now = datetime.now(timezone.utc)
    return _FabricCacheEntry(
        product_name="p1",
        tenant_id=None,
        data_bytes=payload,
        content_hash=content_hash,
        metadata={"pipeline_ms": 5.0},
        cached_at=now,
        run_started_at=run_started_at or (now - timedelta(seconds=1)),
        size_bytes=len(payload),
    )


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_outage_get_returns_none_and_flags_degraded() -> None:
    """When Redis is unreachable, get() returns None and degraded flips on."""
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
        redis_url_for_logging="redis://test:secret@host:6379/0",
    )

    # Seed an entry while Redis is healthy
    await backend.set("p1", _entry())
    fetched = await backend.get("p1")
    assert fetched is not None
    assert backend.degraded is False

    # Bring Redis "down"
    client.armed = True
    fallback = await backend.get("p1")
    assert fallback is None, "get must return None on Redis outage"
    assert backend.degraded is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_outage_set_returns_false_and_flags_degraded() -> None:
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
        redis_url_for_logging="redis://test:secret@host:6379/0",
    )
    client.armed = True
    written = await backend.set("p1", _entry())
    assert written is False, "set must return False on Redis outage"
    assert backend.degraded is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_outage_get_metadata_returns_none() -> None:
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
    )
    client.armed = True
    meta = await backend.get_metadata("p1")
    assert meta is None
    assert backend.degraded is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_outage_invalidate_no_raise() -> None:
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
    )
    client.armed = True
    # Must not raise
    await backend.invalidate("p1")
    assert backend.degraded is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_recovery_flips_degraded_back_off() -> None:
    """First successful operation after an outage flips the gauge back to 0."""
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
    )

    # Seed before outage
    await backend.set("p1", _entry(content_hash="h-good"))
    assert backend.degraded is False

    # Bring Redis down
    client.armed = True
    assert await backend.get("p1") is None
    assert backend.degraded is True

    # Restore Redis
    client.armed = False
    fetched = await backend.get("p1")
    assert fetched is not None
    assert fetched.content_hash == "h-good"
    assert backend.degraded is False, "degraded must flip back to 0 on first success"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_outage_invalidate_all_no_raise() -> None:
    client = _FaultInjectingRedisClient()
    backend = RedisFabricCacheBackend(
        redis_client=client,
        key_prefix="fabric_test",
        instance_name="outage_test",
    )
    client.armed = True
    # Must not raise
    await backend.invalidate_all()
    assert backend.degraded is True
