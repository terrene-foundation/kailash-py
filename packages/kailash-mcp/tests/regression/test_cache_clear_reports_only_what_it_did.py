"""``MCPServer`` must never log a cache invalidation it did not perform.

The defect: ``UnifiedCache.clear()`` executed ``pass`` on the Redis branch, and
``MCPServer.clear_cache()`` logged ``"Cleared cache: <name>"`` immediately
after. An operator reading that line had an explicit confirmation of an
invalidation that never happened — worse than silence, because a confirmation
TERMINATES the investigation that would otherwise have found the staleness.

These tests pin the reporting contract, not just the deletion:

* a refusal emits NO success line;
* the async path's success line reports the ACTUAL key count, so it cannot
  claim more than the operation performed.

The Redis stand-in is a deterministic in-process adapter holding real state, not
a ``MagicMock`` — a Mock auto-satisfies every attribute, which is precisely how
the original vacuous test asserted nothing at all.
"""

import logging

import pytest

from kailash_mcp.server import MCPServer
from kailash_mcp.utils.cache import UnifiedCache

pytestmark = pytest.mark.regression


class _FakeRedis:
    """Minimal deterministic ``redis.asyncio`` stand-in (real state, no Mock)."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.flushdb_called = False

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, *keys):
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    async def scan(self, cursor=0, match=None, count=None):
        import re

        prefix = match[:-1].replace("\\", "")  # trailing '*' + unescape
        return 0, [k for k in self.store if k.startswith(prefix)]

    async def flushdb(self):
        self.flushdb_called = True
        self.store.clear()


def _redis_backed(server: MCPServer, name: str) -> tuple[UnifiedCache, _FakeRedis]:
    """Install a Redis-backed cache under ``name`` on the server's manager."""
    redis = _FakeRedis()
    cache = UnifiedCache(name=name, redis_client=redis)
    server.cache._caches[name] = cache
    return cache, redis


def _success_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "Cleared cache" in r.getMessage()]


class TestSyncClearCacheNeverClaimsFalseSuccess:
    def test_refusal_emits_no_success_log(self, caplog):
        """The whole point: no success line for an invalidation that didn't run."""
        server = MCPServer("cache-report-refusal")
        cache, redis = _redis_backed(server, "tools")
        redis.store["mcp:tools:k"] = '{"v": 1}'

        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError):
                server.clear_cache("tools")

        assert _success_lines(caplog) == [], (
            "clear_cache() logged a success line for a clear that raised — the "
            f"operator would believe the cache was invalidated: {_success_lines(caplog)!r}"
        )
        assert redis.store, "precondition broken: the key should still be present"

    def test_memory_backend_still_logs_success_and_actually_clears(self, caplog):
        """CONTROL: the working backend must keep reporting success.

        Without this, deleting the log line entirely would satisfy the test
        above — the assertion must distinguish 'no false success' from
        'no success reporting at all'.
        """
        server = MCPServer("cache-report-memory")
        cache = server.cache.get_cache("tools")
        cache.set("k", "v")

        with caplog.at_level(logging.INFO):
            server.clear_cache("tools")

        assert _success_lines(caplog), "the working path stopped reporting success"
        assert cache.get("k") is None, "the memory cache was not actually cleared"


class TestAsyncClearCacheDoesTheWorkAndReportsTheCount:
    @pytest.mark.asyncio
    async def test_aclear_cache_clears_named_redis_cache(self, caplog):
        server = MCPServer("cache-report-async")
        cache, redis = _redis_backed(server, "tools")
        await cache.aset("k1", {"v": 1})
        await cache.aset("k2", {"v": 2})

        with caplog.at_level(logging.INFO):
            deleted = await server.aclear_cache("tools")

        assert deleted == 2, f"reported {deleted} deleted, expected 2"
        assert await cache.aget("k1") is None, "k1 survived aclear_cache()"
        assert await cache.aget("k2") is None, "k2 survived aclear_cache()"
        assert not redis.flushdb_called, "aclear_cache() flushed the shared database"
        assert any(
            "deleted=2" in m for m in _success_lines(caplog)
        ), f"the success line does not report the real count: {_success_lines(caplog)!r}"

    @pytest.mark.asyncio
    async def test_aclear_cache_all_clears_every_cache(self):
        server = MCPServer("cache-report-async-all")
        tools, _ = _redis_backed(server, "tools")
        prompts, _ = _redis_backed(server, "prompts")
        await tools.aset("k", {"owner": "tools"})
        await prompts.aset("k", {"owner": "prompts"})

        deleted = await server.aclear_cache()

        assert deleted == 2, f"reported {deleted}, expected 2 across both caches"
        assert await tools.aget("k") is None
        assert await prompts.aget("k") is None
