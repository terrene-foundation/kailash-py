# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for the DistributedLock primitive.

NO MOCKING (rules/testing.md § Tier 2) — every test runs against REAL
infrastructure: an in-memory SQLite ConnectionManager, a real PostgreSQL
instance (POSTGRES_TEST_URL, :5434), and a real Redis instance
(REDIS_TEST_URL, redis://localhost:6380).

The ``lock`` fixture is parametrized across all available backends so the full
invariant matrix runs identically on SQLite + PostgreSQL + Redis:

* acquire-succeeds
* second-acquire-fails-under-contention
* expiry-steal: an expired lock is re-acquirable AND the fencing token
  strictly increases across the steal
* release-only-own-lease: a stale token cannot release or extend (returns
  False / None)
* extend extends the TTL; extend-after-loss fails
* the ``lease`` contextmanager auto-releases on normal exit AND on exception

Run infra (if not up)::

    bash tests/utils/start_docker_services.sh
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

logger = logging.getLogger(__name__)

POSTGRES_TEST_URL = os.environ.get(
    "POSTGRES_TEST_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6380")


# ---------------------------------------------------------------------------
# Backend availability probes
# ---------------------------------------------------------------------------
async def _postgres_available() -> bool:
    try:
        import asyncpg
    except ImportError:
        return False
    try:
        conn = await asyncpg.connect(POSTGRES_TEST_URL)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:
        return False


async def _redis_available() -> bool:
    try:
        import redis.asyncio as aioredis
    except ImportError:
        return False
    try:
        client = aioredis.from_url(REDIS_TEST_URL)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Parametrized backend fixture: sqlite + postgres + redis
# ---------------------------------------------------------------------------
@pytest.fixture(params=["sqlite", "postgres", "redis"])
async def lock(request):
    """Yield an initialized DistributedLock for each available backend.

    Each backend uses unique key namespaces / fresh tables so tests do not
    collide. SQLite uses a private in-memory connection; PostgreSQL drops +
    recreates its tables; Redis flushes its lock key namespace.
    """
    from kailash.infrastructure.lock_store import DBLockBackend, DistributedLock

    which = request.param

    if which == "sqlite":
        from kailash.db.connection import ConnectionManager

        conn = ConnectionManager("sqlite:///:memory:")
        await conn.initialize()
        backend = DBLockBackend(conn)
        await backend.initialize()
        lock = DistributedLock(backend, default_ttl_seconds=30)
        lock._test_backend_kind = "sql"  # type: ignore[attr-defined]
        try:
            yield lock
        finally:
            await lock.close()
            await conn.close()

    elif which == "postgres":
        if not await _postgres_available():
            pytest.skip(f"PostgreSQL not available at {POSTGRES_TEST_URL}")
        from kailash.db.connection import ConnectionManager

        conn = ConnectionManager(POSTGRES_TEST_URL)
        await conn.initialize()
        # Fresh tables per test for isolation.
        await conn.execute("DROP TABLE IF EXISTS kailash_locks")
        await conn.execute("DROP TABLE IF EXISTS kailash_lock_fence")
        backend = DBLockBackend(conn)
        await backend.initialize()
        lock = DistributedLock(backend, default_ttl_seconds=30)
        lock._test_backend_kind = "sql"  # type: ignore[attr-defined]
        try:
            yield lock
        finally:
            await conn.execute("DROP TABLE IF EXISTS kailash_locks")
            await conn.execute("DROP TABLE IF EXISTS kailash_lock_fence")
            await lock.close()
            await conn.close()

    elif which == "redis":
        if not await _redis_available():
            pytest.skip(f"Redis not available at {REDIS_TEST_URL}")
        from kailash.infrastructure.lock_store_redis import RedisLockBackend

        backend = RedisLockBackend(REDIS_TEST_URL, namespace="testlock")
        await backend.initialize()
        # Clear any residue from a prior run.
        await backend._flush_namespace()  # test-only helper
        lock = DistributedLock(backend, default_ttl_seconds=30)
        lock._test_backend_kind = "redis"  # type: ignore[attr-defined]
        try:
            yield lock
        finally:
            await backend._flush_namespace()
            await lock.close()

    else:  # pragma: no cover
        raise AssertionError(f"unknown backend {which}")


# ---------------------------------------------------------------------------
# acquire / contention
# ---------------------------------------------------------------------------
class TestAcquire:
    async def test_acquire_succeeds_on_free_key(self, lock):
        lease = await lock.acquire("res-acq", ttl_seconds=30)
        assert lease is not None
        assert lease.key == "res-acq"
        assert lease.owner  # non-empty uuid
        assert lease.fencing_token >= 1
        assert lease.expires_at  # ISO-8601 string

    async def test_second_acquire_fails_under_contention(self, lock):
        first = await lock.acquire("res-contend", ttl_seconds=30)
        assert first is not None
        second = await lock.acquire("res-contend", ttl_seconds=30)
        assert second is None  # held — no steal before expiry

    async def test_distinct_keys_are_independent(self, lock):
        a = await lock.acquire("res-a", ttl_seconds=30)
        b = await lock.acquire("res-b", ttl_seconds=30)
        assert a is not None and b is not None
        assert a.key != b.key

    async def test_fencing_token_strictly_increases_across_keys_namespace(self, lock):
        # Each key's fence starts at 1 and increments per acquire; a reacquire
        # after release of the SAME key must produce a higher token.
        first = await lock.acquire("res-mono", ttl_seconds=30)
        assert first is not None
        released = await lock.release(first)
        assert released is True
        second = await lock.acquire("res-mono", ttl_seconds=30)
        assert second is not None
        assert second.fencing_token > first.fencing_token


# ---------------------------------------------------------------------------
# expiry-steal + fencing monotonicity across the steal
# ---------------------------------------------------------------------------
class TestExpirySteal:
    async def test_expired_lock_is_reacquirable(self, lock):
        held = await lock.acquire("res-expire", ttl_seconds=1)
        assert held is not None
        # Contended while live.
        assert await lock.acquire("res-expire", ttl_seconds=1) is None
        # Wait past TTL.
        await asyncio.sleep(1.2)
        stolen = await lock.acquire("res-expire", ttl_seconds=30)
        assert stolen is not None

    async def test_fencing_token_strictly_increases_across_steal(self, lock):
        held = await lock.acquire("res-steal-fence", ttl_seconds=1)
        assert held is not None
        await asyncio.sleep(1.2)
        stolen = await lock.acquire("res-steal-fence", ttl_seconds=30)
        assert stolen is not None
        # THE safety invariant: the token must strictly increase even though
        # the prior lease was never explicitly released (it expired + stolen).
        assert stolen.fencing_token > held.fencing_token
        assert stolen.owner != held.owner


# ---------------------------------------------------------------------------
# release-only-own-lease (stale token / owner cannot release or extend)
# ---------------------------------------------------------------------------
class TestReleaseOnlyOwnLease:
    async def test_release_returns_true_for_held_lease(self, lock):
        held = await lock.acquire("res-rel-ok", ttl_seconds=30)
        assert held is not None
        assert await lock.release(held) is True

    async def test_stale_token_cannot_release_after_steal(self, lock):
        original = await lock.acquire("res-stale-rel", ttl_seconds=1)
        assert original is not None
        await asyncio.sleep(1.2)
        stolen = await lock.acquire("res-stale-rel", ttl_seconds=30)
        assert stolen is not None
        # The original holder's stale lease must NOT be able to release the
        # new holder's lock.
        assert await lock.release(original) is False
        # The new holder is still in force.
        assert await lock.acquire("res-stale-rel", ttl_seconds=30) is None
        # The legitimate holder can release.
        assert await lock.release(stolen) is True

    async def test_double_release_is_false_second_time(self, lock):
        held = await lock.acquire("res-double-rel", ttl_seconds=30)
        assert held is not None
        assert await lock.release(held) is True
        assert await lock.release(held) is False


# ---------------------------------------------------------------------------
# extend
# ---------------------------------------------------------------------------
class TestExtend:
    async def test_extend_extends_ttl_and_keeps_token(self, lock):
        held = await lock.acquire("res-extend", ttl_seconds=1)
        assert held is not None
        extended = await lock.extend(held, ttl_seconds=30)
        assert extended is not None
        # Same fencing token — extending a held lease is the same critical
        # section, not a new one.
        assert extended.fencing_token == held.fencing_token
        # After the original 1s TTL would have lapsed, the key is still held
        # because the extend pushed expiry out.
        await asyncio.sleep(1.2)
        assert await lock.acquire("res-extend", ttl_seconds=1) is None
        assert await lock.release(extended) is True

    async def test_extend_after_loss_returns_none(self, lock):
        original = await lock.acquire("res-extend-loss", ttl_seconds=1)
        assert original is not None
        await asyncio.sleep(1.2)
        stolen = await lock.acquire("res-extend-loss", ttl_seconds=30)
        assert stolen is not None
        # The original (now stale) lease cannot be extended.
        assert await lock.extend(original, ttl_seconds=30) is None
        # The legitimate holder can extend.
        assert await lock.extend(stolen, ttl_seconds=30) is not None


# ---------------------------------------------------------------------------
# lease() contextmanager
# ---------------------------------------------------------------------------
class TestLeaseContextManager:
    async def test_lease_acquires_and_auto_releases_on_normal_exit(self, lock):
        async with lock.lease("res-cm-normal", ttl_seconds=30) as held:
            assert held is not None
            assert held.key == "res-cm-normal"
            # While inside the block, the key is held.
            assert await lock.acquire("res-cm-normal", ttl_seconds=30) is None
        # After the block, it is released — a fresh acquire succeeds.
        after = await lock.acquire("res-cm-normal", ttl_seconds=30)
        assert after is not None
        await lock.release(after)

    async def test_lease_auto_releases_on_exception(self, lock):
        class Boom(RuntimeError):
            pass

        with pytest.raises(Boom):
            async with lock.lease("res-cm-exc", ttl_seconds=30) as held:
                assert held is not None
                raise Boom("inside critical section")
        # Despite the exception, the lock was released.
        after = await lock.acquire("res-cm-exc", ttl_seconds=30)
        assert after is not None
        await lock.release(after)

    async def test_lease_raises_when_contended(self, lock):
        from kailash.infrastructure.lock_store import LockAcquireError

        held = await lock.acquire("res-cm-contend", ttl_seconds=30)
        assert held is not None
        with pytest.raises(LockAcquireError):
            async with lock.lease("res-cm-contend", ttl_seconds=30):
                pass
        await lock.release(held)


# ---------------------------------------------------------------------------
# blocking acquire
# ---------------------------------------------------------------------------
class TestBlockingAcquire:
    async def test_blocking_acquire_times_out_when_held(self, lock):
        held = await lock.acquire("res-block-timeout", ttl_seconds=30)
        assert held is not None
        # Blocking acquire with a short timeout returns None (the held lock
        # never frees within the window).
        result = await lock.acquire(
            "res-block-timeout", ttl_seconds=30, blocking=True, timeout=0.3
        )
        assert result is None
        await lock.release(held)

    async def test_blocking_acquire_succeeds_after_release(self, lock):
        held = await lock.acquire("res-block-ok", ttl_seconds=30)
        assert held is not None

        async def release_soon():
            await asyncio.sleep(0.2)
            await lock.release(held)

        releaser = asyncio.create_task(release_soon())
        # Blocking acquire should succeed once the releaser frees the lock.
        result = await lock.acquire(
            "res-block-ok", ttl_seconds=30, blocking=True, timeout=5.0
        )
        await releaser
        assert result is not None
        # Fencing token strictly increased over the released lease.
        assert result.fencing_token > held.fencing_token
        await lock.release(result)


# ---------------------------------------------------------------------------
# reap_expired
# ---------------------------------------------------------------------------
class TestReapExpired:
    async def test_reap_removes_expired_locks(self, lock):
        kind = getattr(lock, "_test_backend_kind", "sql")
        first = await lock.acquire("res-reap-1", ttl_seconds=1)
        assert first is not None
        await lock.acquire("res-reap-2", ttl_seconds=1)
        await asyncio.sleep(1.2)
        reaped = await lock.reap_expired()
        if kind == "redis":
            # Redis expiry is native (PX); reap_expired is a documented no-op
            # returning 0 — there is nothing for the SDK to reap.
            assert reaped == 0
        else:
            assert reaped >= 2
        # On BOTH backends, the expired key is re-acquirable with a strictly
        # higher fencing token — the fence survives reaping / native expiry.
        again = await lock.acquire("res-reap-1", ttl_seconds=30)
        assert again is not None
        assert again.fencing_token > first.fencing_token

    async def test_reap_leaves_live_locks(self, lock):
        live = await lock.acquire("res-reap-live", ttl_seconds=30)
        assert live is not None
        await lock.reap_expired()
        # The live lock is still held (on every backend).
        assert await lock.acquire("res-reap-live", ttl_seconds=30) is None
        await lock.release(live)
