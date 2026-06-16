# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Redis-backed :class:`~kailash.infrastructure.lock_store.LockBackend`.

Single-instance / single-replica Redis distributed lock.  Lives in its own
module behind the ``[redis]`` extra so a slim-core install never pays for
``redis.asyncio``: the driver is imported lazily inside
:meth:`RedisLockBackend.initialize` and raises a typed, actionable
``ImportError`` if the extra is missing (the same guard pattern
:mod:`kailash.trust._locking` uses for ``filelock`` per issue #1154).

Mechanism:

* **acquire** — ``SET lock:{key} {owner} NX PX {ttl_ms}`` claims the key
  atomically only when free; on success ``INCR fence:{key}`` yields the
  strictly-monotonic fencing token.  The ``fence:{key}`` counter is a separate
  key with NO expiry, so the token survives lock churn (release / native
  expiry / steal) and is therefore strictly increasing and NEVER reset.
* **release** — a Lua compare-owner-then-DEL script: deletes the lock key
  only when its value still equals this owner, so a holder whose lease expired
  and was stolen can never delete the new holder's lock.
* **extend** — a Lua compare-owner-then-PEXPIRE script: pushes out the TTL
  only while still owned.
* **expiry** — native (the ``PX`` on the SET); no reaper thread is needed.

Honesty note (read before relying on this in a multi-node Redis topology):
this is a **single-instance** (or single-primary + replicas) lock, NOT the
multi-master Redlock algorithm across N independent Redis nodes — that timing
model is contested (Kleppmann).  Safety here does NOT rest on the TTL: it rests
on the **fencing token**.  A protected resource MUST reject any write carrying
a token ``<=`` the highest it has seen (see
:class:`~kailash.infrastructure.lock_store.DistributedLock` docstring).  Under
a primary failover that loses an un-replicated ``SET``, two workers can briefly
hold the same key — but only the one with the higher fencing token can mutate
the resource, so correctness is preserved by the fence, not by Redis timing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "RedisLockBackend",
]

# Lua: delete the lock key only if its current value matches this owner.
# Returns 1 if deleted, 0 if owner mismatch / key absent.
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

# Lua: PEXPIRE the lock key only if its current value matches this owner.
# Returns 1 if the TTL was set, 0 if owner mismatch / key absent.
_EXTEND_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
else
    return 0
end
"""


class RedisLockBackend:
    """Redis-backed lock backend satisfying the ``LockBackend`` Protocol.

    Parameters
    ----------
    url:
        A Redis connection URL, e.g. ``redis://localhost:6379/0``.
    namespace:
        Key prefix for this backend's lock + fence keys (default ``kailash``).
        Lock keys are ``{namespace}:lock:{key}``; fence counters are
        ``{namespace}:fence:{key}``.
    """

    def __init__(self, url: str, namespace: str = "kailash") -> None:
        self._url = url
        self._namespace = namespace
        self._client: Any = None  # redis.asyncio.Redis once initialized
        self._release_script: Any = None
        self._extend_script: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """Connect to Redis and register the Lua scripts.

        Raises
        ------
        ImportError
            If the ``[redis]`` extra is not installed.  Install it with
            ``pip install kailash[redis]``.
        """
        # Lazy import — see module docstring + issue #1154 (slim-core).
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:  # pragma: no cover - exercised via extra-absent test
            raise ImportError(
                "RedisLockBackend requires the redis driver. Install the "
                "redis extra: pip install kailash[redis]"
            ) from exc

        if self._client is None:
            # redis-py leaves `from_url` untyped in its stubs (returns Any);
            # the targeted ignore acknowledges the upstream gap, not a missing module.
            self._client = aioredis.from_url(self._url)  # type: ignore[no-untyped-call]
            # register_script returns an AsyncScript callable bound to the client.
            self._release_script = self._client.register_script(_RELEASE_LUA)
            self._extend_script = self._client.register_script(_EXTEND_LUA)
            logger.info("RedisLockBackend connected (namespace=%s)", self._namespace)

    async def close(self) -> None:
        """Close the Redis client connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("RedisLockBackend closed")

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------
    def _lock_key(self, key: str) -> str:
        return f"{self._namespace}:lock:{key}"

    def _fence_key(self, key: str) -> str:
        return f"{self._namespace}:fence:{key}"

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError(
                "RedisLockBackend is not initialized. Call await "
                "backend.initialize() first."
            )
        return self._client

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    async def try_acquire(
        self, key: str, owner: str, ttl_seconds: int
    ) -> Optional[int]:
        """Acquire ``key`` for ``owner`` via ``SET ... NX PX``.

        Native ``PX`` expiry means an expired lock is automatically free for
        the next ``SET NX`` — that IS the steal-if-expired behaviour, with no
        reaper.  On success ``INCR`` on the (never-expiring) fence counter
        yields the strictly-monotonic token.
        """
        client = self._require_client()
        ttl_ms = max(1, int(ttl_seconds * 1000))
        acquired = await client.set(self._lock_key(key), owner, nx=True, px=ttl_ms)
        if not acquired:
            return None
        token = await client.incr(self._fence_key(key))
        logger.debug(
            "lock.acquire key=%s owner=%s token=%d ttl=%ds",
            key,
            owner,
            token,
            ttl_seconds,
        )
        return int(token)

    async def release(self, key: str, owner: str, token: int) -> bool:
        """Release the lock iff still owned by ``owner`` (compare-then-DEL).

        The ``token`` argument is accepted for Protocol parity; correctness on
        Redis rests on the owner check (the owner uuid is unique per acquire,
        so it already distinguishes a stale holder from the current one).
        """
        self._require_client()
        result = await self._release_script(keys=[self._lock_key(key)], args=[owner])
        released = bool(result)
        logger.debug(
            "lock.release key=%s owner=%s token=%d released=%s",
            key,
            owner,
            token,
            released,
        )
        return released

    async def extend(self, key: str, owner: str, token: int, ttl_seconds: int) -> bool:
        """Extend the lease TTL iff still owned (compare-then-PEXPIRE)."""
        self._require_client()
        ttl_ms = max(1, int(ttl_seconds * 1000))
        result = await self._extend_script(
            keys=[self._lock_key(key)], args=[owner, ttl_ms]
        )
        extended = bool(result)
        logger.debug(
            "lock.extend key=%s owner=%s token=%d ttl=%ds extended=%s",
            key,
            owner,
            token,
            ttl_seconds,
            extended,
        )
        return extended

    async def reap_expired(self, before: Optional[str] = None) -> int:
        """No-op on Redis: expiry is native (``PX``).

        Returns 0 always — there is nothing to reap because Redis evicts
        expired lock keys itself.  The ``before`` argument is accepted for
        Protocol parity with :class:`DBLockBackend`.
        """
        return 0

    # ------------------------------------------------------------------
    # Test-only helper
    # ------------------------------------------------------------------
    async def _flush_namespace(self) -> None:
        """Delete every lock + fence key under this backend's namespace.

        Used by the Tier-2 test fixture for isolation between runs.  NOT part
        of the public API; production code never calls this.
        """
        client = self._require_client()
        pattern = f"{self._namespace}:*"
        keys = [k async for k in client.scan_iter(match=pattern)]
        if keys:
            await client.delete(*keys)
