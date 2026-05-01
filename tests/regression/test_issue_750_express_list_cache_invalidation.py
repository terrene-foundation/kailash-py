"""Issue #750 regression — db.express.list MUST reflect mutations on SQLite.

Issue: db.express.list("Tag") returned STALE data after db.express.update / .delete on
SQLite (and PostgreSQL with `enable_query_cache=True`). The disk WAS updated; the bug
was in the cache invalidation pattern strings used by `ListNodeCacheIntegration`.

Root cause:
  ListNodeCacheIntegration._setup_invalidation_patterns registered InvalidationPattern
  objects with `invalidates=["{model}:list:*", "{model}:count:*"]`. These pattern
  strings were intended to match cache keys produced by `CacheKeyGenerator.generate_key`
  but the actual key shape is `{prefix}:{model}:{version}:{hash}` where `prefix`
  defaults to `"dataflow:query"` (from `DataFlowConfig.cache_key_prefix`). So the
  expanded pattern `Tag:list:*` never matched the actual key
  `dataflow:query:Tag:v2:<hash>`. Cache invalidation was a no-op; subsequent list
  queries served stale results from the cache_integration cache.

Fix: align invalidation patterns with the producer-side key format using version-
wildcard sweep `{prefix}:{{model}}:*` per `tenant-isolation.md` Rule 3a — so legacy
v1 keys, current v2 keys, and any future keyspace bump are all swept in one call.

Disk state was always correct. The user-observable bug was list staleness:
  1. create row → disk has row
  2. update value → disk has new value, list cache has old row
  3. list → returns STALE (cache hit on stale entry never invalidated)

This test asserts the user-visible contract: after every mutation, list reflects
the new state. Runs against SQLite (deterministic, sub-second feedback) and exercises
the full express → node → cache_integration path that the fix repairs.

See:
- packages/kailash-dataflow/src/dataflow/cache/list_node_integration.py::_setup_invalidation_patterns
- packages/kailash-dataflow/src/dataflow/cache/key_generator.py::generate_key
- packages/kailash-dataflow/src/dataflow/cache/memory_cache.py::InMemoryCache.clear_pattern
- rules/tenant-isolation.md MUST Rule 3a (Keyspace Version Bumps Require Invalidation-Path Sweep)
- rules/zero-tolerance.md Rule 2 (no fake/no-op invalidation)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from dataflow import DataFlow

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


@pytest.fixture
def sqlite_url():
    """File-backed SQLite URL — exercises the same cache-integration path as Postgres."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="issue_750_")
    os.close(fd)
    yield f"sqlite:///{path}"
    try:
        os.unlink(path)
    except OSError:
        pass


async def test_list_after_update_reflects_change(sqlite_url):
    """list() MUST return the updated row after express.update — not a cached stale entry."""
    db = DataFlow(sqlite_url, auto_migrate=True)

    @db.model
    class Tag:
        name: str
        value: str = ""

    try:
        await db.express.create("Tag", {"name": "x", "value": "old"})
        rows = await db.express.list("Tag")
        assert len(rows) == 1
        rid = rows[0]["id"]

        # First list populates the cache_integration cache for this query.
        # Subsequent update MUST invalidate the cached entry.
        upd = await db.express.update("Tag", rid, {"value": "new"})
        assert upd["value"] == "new"

        # Default cache TTL applies — invalidation is the only correct
        # mechanism here. cache_ttl=0 would bypass the bug; this assertion
        # exercises the actual invalidation path.
        rows_after = await db.express.list("Tag")
        assert rows_after[0]["value"] == "new", (
            f"list() returned stale value after update — cache invalidation failed. "
            f"Got: {rows_after[0]}"
        )
    finally:
        await db.close_async()


async def test_list_after_delete_reflects_removal(sqlite_url):
    """list() MUST omit the deleted row after express.delete — not return a cached stale entry."""
    db = DataFlow(sqlite_url, auto_migrate=True)

    @db.model
    class Tag:
        name: str
        value: str = ""

    try:
        await db.express.create("Tag", {"name": "x", "value": "v1"})
        await db.express.create("Tag", {"name": "y", "value": "v2"})
        rows = await db.express.list("Tag")
        assert len(rows) == 2
        deleted_id = rows[0]["id"]

        deleted = await db.express.delete("Tag", deleted_id)
        assert deleted is True

        rows_after = await db.express.list("Tag")
        assert len(rows_after) == 1, (
            f"list() returned {len(rows_after)} rows after deleting one of two — "
            f"cache invalidation failed. Got: {rows_after}"
        )
        assert rows_after[0]["id"] != deleted_id
    finally:
        await db.close_async()


async def test_list_after_create_reflects_new_row(sqlite_url):
    """list() MUST include the new row after express.create — not return a cached pre-create entry."""
    db = DataFlow(sqlite_url, auto_migrate=True)

    @db.model
    class Tag:
        name: str
        value: str = ""

    try:
        await db.express.create("Tag", {"name": "first", "value": "v1"})
        rows = await db.express.list("Tag")
        assert len(rows) == 1

        await db.express.create("Tag", {"name": "second", "value": "v2"})

        rows_after = await db.express.list("Tag")
        assert len(rows_after) == 2, (
            f"list() returned {len(rows_after)} rows after creating second — "
            f"cache invalidation failed. Got: {rows_after}"
        )
        names = {r["name"] for r in rows_after}
        assert names == {"first", "second"}
    finally:
        await db.close_async()


async def test_invalidation_patterns_match_actual_key_shape():
    """Structural invariant: ListNodeCacheIntegration patterns MUST cover the actual key shape.

    This is the structural defense against a future refactor that re-introduces
    a producer/invalidator key-format drift (rules/tenant-isolation.md Rule 3a).

    Asserts:
      1. The default key prefix the cache integration uses
      2. The invalidator's registered patterns include a version-wildcard sweep
         covering the actual prefix (so v1, v2, and any future bump are swept)
    """
    from dataflow.cache import (
        CacheBackend,
        CacheInvalidator,
        CacheKeyGenerator,
        create_cache_integration,
    )

    cm = CacheBackend.auto_detect(
        redis_url="redis://localhost:6379/0", ttl=300, max_size=100
    )
    kg = CacheKeyGenerator(prefix="dataflow:query")
    inv = CacheInvalidator(cm)
    ci = create_cache_integration(cm, kg, inv)

    sample_key = kg.generate_key("Tag", "SELECT * FROM tags", [])
    assert sample_key.startswith(
        "dataflow:query:Tag:"
    ), f"Cache key shape changed. Patterns must be re-aligned. Got: {sample_key}"

    update_patterns = [p for p in ci.invalidator.patterns if p.operation == "update"]
    assert update_patterns, "no update invalidation pattern registered"

    matching = []
    for p in update_patterns:
        for inv_pattern in p.invalidates:
            expanded = inv_pattern.replace("{model}", "Tag")
            if "*" in expanded:
                segment = expanded.replace("*", "")
                if segment in sample_key:
                    matching.append(expanded)
            elif expanded == sample_key:
                matching.append(expanded)

    assert matching, (
        f"No registered update-invalidation pattern matches the actual cache key. "
        f"Patterns: {[p.invalidates for p in update_patterns]}; "
        f"key sample: {sample_key!r}. "
        f"Per rules/tenant-isolation.md Rule 3a, patterns MUST cover the producer-side "
        f"key format with a version-wildcard sweep."
    )
