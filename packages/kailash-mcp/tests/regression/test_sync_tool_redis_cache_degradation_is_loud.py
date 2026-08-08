"""A SYNC tool that cannot reach Redis MUST say so, and MUST NOT claim it cached.

Measured behaviour on this surface (both legs driven in
``TestTheDegradationIsReal`` below so the premise is asserted, not assumed):

* NO running loop  -> ``asyncio.run`` is available, the result IS cached.
* INSIDE a loop    -> ``asyncio.run`` is unavailable, caching is skipped
  ENTIRELY and the tool body re-executes on every call.

The second leg is the NORMAL production path: ``MCPServer._execute_tool``
invokes sync handlers directly (``return handler(**arguments)``) with no thread
offload, so a sync tool served over an async transport runs on the loop thread.

This file pins the OBSERVABILITY contract, which is all that can be fixed
locally. Actually caching on that path requires an architectural change
(offload sync tools to a thread, or declare the tool ``async def``) and is NOT
attempted here — an async tool takes the ``get_or_compute`` path and is
unaffected either way.
"""

import asyncio
import logging

import pytest

from kailash_mcp.server import MCPServer
from kailash_mcp.utils.cache import UnifiedCache

pytestmark = pytest.mark.regression


class _FakeRedis:
    """Deterministic in-process ``redis.asyncio`` stand-in (real state, no Mock)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, *keys):
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    async def scan(self, cursor=0, match=None, count=None):
        prefix = match[:-1].replace("\\", "")
        return 0, [k for k in self.store if k.startswith(prefix)]


def _server_with_redis_tool(name: str):
    """A server whose sync tool is backed by a REAL redis-shaped cache.

    The cache is pre-installed under the tool's ``cache_key`` BEFORE any call.
    Installing it after the decorator runs is not enough: ``_caches`` is empty
    at decoration time and ``get_cache`` would lazily create a MEMORY cache on
    first call, so the test would silently measure the wrong backend.
    """
    server = MCPServer(name)
    calls = {"n": 0}

    @server.tool(cache_key="probe", cache_ttl=300)
    def probe_tool(x: int) -> dict:
        calls["n"] += 1
        return {"doubled": x * 2}

    redis = _FakeRedis()
    cache = UnifiedCache(name="probe", redis_client=redis)
    server.cache._caches["probe"] = cache
    # Anti-vacuity: if this is not the object the tool actually uses, or is not
    # Redis-backed, every assertion below is meaningless.
    assert server.cache.get_cache("probe") is cache
    assert cache.is_redis
    return probe_tool, redis, calls


def _degradation_warnings(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if "cache.sync.degraded_on_redis" in r.getMessage()
    ]


class TestTheDegradationIsReal:
    """Assert the premise, so the observability tests are not guarding a myth."""

    def test_without_a_running_loop_the_result_is_cached(self):
        probe_tool, redis, calls = _server_with_redis_tool("degr-no-loop")

        probe_tool(x=21)
        probe_tool(x=21)

        assert redis.store, "nothing reached Redis even though asyncio.run was usable"
        assert calls["n"] == 1, (
            f"the tool ran {calls['n']}x with no loop running; caching should have "
            "served the second call"
        )

    @pytest.mark.asyncio
    async def test_inside_a_running_loop_caching_is_skipped_entirely(self):
        probe_tool, redis, calls = _server_with_redis_tool("degr-in-loop")

        probe_tool(x=21)
        probe_tool(x=21)

        assert redis.store == {}, (
            "something reached Redis from a sync tool on the loop thread — if "
            "this now works, the WARN below is obsolete and must be removed"
        )
        assert calls["n"] == 2, (
            f"the tool ran {calls['n']}x; the degraded path must re-execute the "
            "body every call"
        )


class TestTheDegradationIsAnnouncedNotSilent:
    @pytest.mark.asyncio
    async def test_read_and_write_skips_each_warn_once(self, caplog):
        probe_tool, _, _ = _server_with_redis_tool("degr-warn")

        with caplog.at_level(logging.WARNING):
            probe_tool(x=21)
            probe_tool(x=21)
            probe_tool(x=22)

        warnings = _degradation_warnings(caplog)
        reads = [w for w in warnings if "tool-cache-read-in-running-loop" in w]
        writes = [w for w in warnings if "tool-cache-write-in-running-loop" in w]

        assert len(reads) == 1, (
            f"the skipped cache READ must be announced exactly once per cache "
            f"(0 = silent degradation, >1 = hot-path log flood); got {len(reads)}"
        )
        assert len(writes) == 1, (
            f"the skipped cache WRITE must be announced exactly once per cache; "
            f"got {len(writes)}"
        )
        assert "async def" in reads[0], (
            "the WARN must name the remedy the caller can actually apply: "
            f"{reads[0]!r}"
        )

    def test_the_working_path_never_warns(self, caplog):
        """CONTROL: no loop running means caching works, so nothing to announce.

        Without this, warning unconditionally would satisfy the test above.
        """
        probe_tool, redis, _ = _server_with_redis_tool("degr-control")

        with caplog.at_level(logging.WARNING):
            probe_tool(x=21)

        assert redis.store, "precondition: this leg should have cached"
        assert _degradation_warnings(caplog) == [], (
            "the working path emitted a degradation warning: "
            f"{_degradation_warnings(caplog)!r}"
        )


class TestNoFalseCachedResultLog:
    @pytest.mark.asyncio
    async def test_skipped_write_does_not_log_cached_result(self, caplog):
        """``Cached result for <tool>`` fired unconditionally before this fix."""
        probe_tool, redis, _ = _server_with_redis_tool("degr-false-log")

        with caplog.at_level(logging.DEBUG):
            probe_tool(x=21)

        assert redis.store == {}, "precondition: the write should have been skipped"
        claimed = [
            r.getMessage()
            for r in caplog.records
            if "Cached result for" in r.getMessage()
        ]
        assert claimed == [], (
            "the server logged that it cached a result it never stored: " f"{claimed!r}"
        )

    def test_real_store_still_logs_cached_result(self, caplog):
        """CONTROL: the line must survive for writes that DID happen."""
        probe_tool, redis, _ = _server_with_redis_tool("degr-true-log")

        with caplog.at_level(logging.DEBUG):
            probe_tool(x=21)

        assert redis.store, "precondition: this leg should have stored"
        assert [
            r.getMessage()
            for r in caplog.records
            if "Cached result for" in r.getMessage()
        ], "a genuine store stopped reporting itself"
