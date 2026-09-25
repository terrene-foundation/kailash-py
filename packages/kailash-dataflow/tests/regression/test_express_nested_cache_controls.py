"""Cache controls must reach the real ListNode query cache beneath Express."""

import sys

import pytest

from dataflow import DataFlow
from dataflow.cache.invalidation import CacheInvalidator
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.list_node_integration import ListNodeCacheIntegration
from dataflow.cache.memory_cache import InMemoryCache


async def _observe_sql(node, operation):
    """Observe actual SQL execution without replacing the implementation."""
    code = type(node).async_run.__code__
    hits = 0
    previous = sys.getprofile()

    def profile(frame, event, arg):
        nonlocal hits
        if (
            event == "call"
            and frame.f_code is code
            and frame.f_locals.get("self") is node
        ):
            hits += 1

    sys.setprofile(profile)
    try:
        return await operation(), lambda: hits
    finally:
        sys.setprofile(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["list", "find_one", "generated_list"])
@pytest.mark.parametrize("cache_policy", ["zero_ttl", "disabled"])
async def test_cache_controls_bypass_warm_inner_cache(tmp_path, surface, cache_policy):
    url = f"sqlite:///{tmp_path / 'cache-control.db'}"
    reader = DataFlow(url, cache_enabled=True, test_mode=False)
    writer = DataFlow(url, cache_enabled=False, test_mode=False)
    original_integration = reader._cache_integration
    cache = InMemoryCache()

    for db in (reader, writer):

        @db.model
        class CacheControlRow:
            id: str
            value: str

    try:
        await reader.express.create("CacheControlRow", {"id": "one", "value": "old"})
        reader._cache_integration = ListNodeCacheIntegration(
            cache, CacheKeyGenerator(), CacheInvalidator(cache)
        )
        generated = reader.express._create_node("CacheControlRow", "List")
        sql_node = reader._get_or_create_async_sql_node("sqlite")
        params = {
            "filter": {"id": "one"},
            "limit": 1,
            "offset": 0,
            "include_deleted": False,
        }
        warm, warm_calls = await _observe_sql(
            sql_node, lambda: generated.async_run(**params)
        )
        assert warm_calls() > 0, "SQL observer must fire on a real cache miss"
        assert warm["records"][0]["value"] == "old"
        await writer.express.update("CacheControlRow", "one", {"value": "new"})
        updated = await writer.express.read("CacheControlRow", "one", cache_ttl=0)
        assert updated["value"] == "new"
        cached, cached_calls = await _observe_sql(
            sql_node, lambda: generated.async_run(**params)
        )
        assert cached_calls() == 0
        assert cached["records"][0]["value"] == "old", "inner cache must really be warm"

        ttl = 0 if cache_policy == "zero_ttl" else None
        if cache_policy == "disabled":
            reader.express._cache_enabled = False
        if surface == "generated_list":

            async def operation():
                return await generated.async_run(
                    **params, cache_ttl=ttl, enable_cache=cache_policy != "disabled"
                )

        elif surface == "find_one":

            async def operation():
                return await reader.express.find_one(
                    "CacheControlRow", {"id": "one"}, cache_ttl=ttl
                )

        else:

            async def operation():
                return await reader.express.list(
                    "CacheControlRow", filter={"id": "one"}, limit=1, cache_ttl=ttl
                )

        result, calls = await _observe_sql(sql_node, operation)
        print("BYPASS_SQL_CALLS", surface, cache_policy, calls())
        assert calls() > 0, "disabled caching must execute SQL below both cache layers"
        row = result["records"][0] if surface == "generated_list" else result
        if surface == "list":
            row = row[0]
        assert row["value"] == "new"
    finally:
        reader._cache_integration = original_integration
        await reader.close_async()
        await writer.close_async()
        await cache.clear()
