"""
Regression tests for cache invalidation exact-match behaviour.

Bug 1: InMemoryCache.invalidate_model used substring ``in`` matching,
so invalidating "User" also nuked entries for "UserAudit", "UserSession",
and any other model whose name started with "User".

Bug 2: AsyncRedisCacheAdapter.invalidate_model used the SCAN pattern
``dataflow:{model}:*`` which does NOT match the real Express key format
``dataflow:v1:{model}:...``.  The method therefore matched nothing and
Redis invalidation was silently broken.

Bug 3: features/express.py had its own ``_invalidate_model_cache`` that
duplicated key-format logic instead of delegating to the backend.

Fixes:
- InMemoryCache uses exact segment match ``:{model_name}:``
- AsyncRedisCacheAdapter scans both Express and SQL key patterns
- Express layer delegates to ``cache_manager.invalidate_model()``
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.memory_cache import InMemoryCache

# ---------------------------------------------------------------------------
# Bug 1 regression: InMemoryCache substring collision
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_invalidate_user_does_not_nuke_user_audit():
    """Regression: invalidating 'User' must not affect 'UserAudit' entries."""
    cache = InMemoryCache(max_size=100, ttl=300)
    key_gen = CacheKeyGenerator()

    # Populate cache with entries for both User and UserAudit
    user_list_key = key_gen.generate_express_key("User", "list", {"active": True})
    user_read_key = key_gen.generate_express_key("User", "read", {"id": "u1"})
    audit_list_key = key_gen.generate_express_key("UserAudit", "list", {"limit": 10})
    audit_read_key = key_gen.generate_express_key("UserAudit", "read", {"id": "a1"})

    await cache.set(user_list_key, [{"id": "u1"}])
    await cache.set(user_read_key, {"id": "u1"})
    await cache.set(audit_list_key, [{"id": "a1"}])
    await cache.set(audit_read_key, {"id": "a1"})

    # Invalidate only "User"
    removed = await cache.invalidate_model("User")

    # User entries must be gone
    assert await cache.get(user_list_key) is None
    assert await cache.get(user_read_key) is None

    # UserAudit entries must still be present
    assert (
        await cache.get(audit_list_key) is not None
    ), "UserAudit list entry was incorrectly removed when invalidating 'User'"
    assert (
        await cache.get(audit_read_key) is not None
    ), "UserAudit read entry was incorrectly removed when invalidating 'User'"

    # Exactly 2 entries removed (both User keys)
    assert removed == 2


@pytest.mark.regression
@pytest.mark.asyncio
async def test_invalidate_user_does_not_nuke_user_session():
    """Regression: invalidating 'User' must not affect 'UserSession' entries."""
    cache = InMemoryCache(max_size=100, ttl=300)
    key_gen = CacheKeyGenerator()

    user_key = key_gen.generate_express_key("User", "list")
    session_key = key_gen.generate_express_key("UserSession", "list")

    await cache.set(user_key, [{"id": "u1"}])
    await cache.set(session_key, [{"id": "s1"}])

    await cache.invalidate_model("User")

    assert await cache.get(user_key) is None
    assert (
        await cache.get(session_key) is not None
    ), "UserSession entry was incorrectly removed when invalidating 'User'"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_invalidate_model_handles_sql_query_keys():
    """Regression: invalidation must handle SQL query key format too.

    SQL query keys use: ``dataflow:{model}:v1:{hash}``
    Express keys use:   ``dataflow:v1:{model}:{op}:{hash}``

    Both formats must be invalidated for a given model.
    """
    cache = InMemoryCache(max_size=100, ttl=300)
    key_gen = CacheKeyGenerator()

    # Express key format
    express_key = key_gen.generate_express_key("Order", "list", {"status": "active"})
    # SQL query key format
    sql_key = key_gen.generate_key("Order", "SELECT * FROM orders", [])

    await cache.set(express_key, [{"id": "o1"}])
    await cache.set(sql_key, [{"id": "o2"}])

    removed = await cache.invalidate_model("Order")

    assert await cache.get(express_key) is None
    assert await cache.get(sql_key) is None
    assert removed == 2


# ---------------------------------------------------------------------------
# Bug 2 regression: Redis SCAN pattern mismatch
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_invalidation_matches_real_key_format():
    """Regression: Redis SCAN pattern must match the actual key format.

    Before fix, AsyncRedisCacheAdapter used ``dataflow:{model}:*`` which
    does NOT match Express keys ``dataflow:v1:{model}:...``.
    """
    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    key_gen = CacheKeyGenerator()

    # Generate a real Express key to understand the format
    real_key = key_gen.generate_express_key("User", "list", {"active": True})

    # The key must start with "dataflow:v1:User:"
    assert real_key.startswith(
        "dataflow:v1:User:"
    ), f"Express key format changed unexpectedly: {real_key}"

    # Create a mock RedisCacheManager that records SCAN patterns
    mock_redis = MagicMock()
    scanned_patterns = []

    def capture_clear_pattern(pattern):
        scanned_patterns.append(pattern)
        return 0

    mock_redis.clear_pattern.side_effect = capture_clear_pattern
    mock_redis.can_cache.return_value = True
    mock_redis.ping.return_value = True

    adapter = AsyncRedisCacheAdapter(mock_redis)
    await adapter.invalidate_model("User")

    # Must include the Express key pattern
    assert (
        "dataflow:v1:User:*" in scanned_patterns
    ), f"Express key pattern not scanned. Patterns used: {scanned_patterns}"
    # Must also include the SQL query key pattern
    assert (
        "dataflow:User:v1:*" in scanned_patterns
    ), f"SQL query key pattern not scanned. Patterns used: {scanned_patterns}"

    # Verify the Express pattern would actually match a real key
    import fnmatch

    express_pattern = "dataflow:v1:User:*"
    assert fnmatch.fnmatch(
        real_key, express_pattern
    ), f"Pattern '{express_pattern}' does not match real key '{real_key}'"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_redis_invalidation_does_not_match_similar_models():
    """Regression: Redis SCAN for 'User' must not match 'UserAudit'.

    The SCAN pattern ``dataflow:v1:User:*`` must NOT match
    ``dataflow:v1:UserAudit:*`` because the glob ``User:*`` requires a
    colon immediately after 'User'.
    """
    import fnmatch

    key_gen = CacheKeyGenerator()

    user_key = key_gen.generate_express_key("User", "list")
    audit_key = key_gen.generate_express_key("UserAudit", "list")

    express_pattern = "dataflow:v1:User:*"

    assert fnmatch.fnmatch(user_key, express_pattern)
    assert not fnmatch.fnmatch(
        audit_key, express_pattern
    ), f"Pattern '{express_pattern}' incorrectly matches UserAudit key '{audit_key}'"


# ---------------------------------------------------------------------------
# Bug 3 regression: Express layer delegation
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_express_delegates_invalidation_to_cache_backend():
    """Regression: Express layer must delegate to cache backend's invalidate_model.

    Before fix, Express had its own ``_invalidate_model_cache`` that built
    a pattern and called ``clear_pattern`` directly, duplicating logic.
    Now it must call ``invalidate_model`` on the cache manager.
    """
    from dataflow.features.express import DataFlowExpress

    # Create a minimal mock DataFlow instance
    mock_db = MagicMock()
    mock_db._models = {}
    mock_db._node_classes = {}
    mock_db._engine_ref = None

    # Create Express with a mock cache backend that has invalidate_model
    express = DataFlowExpress(mock_db, cache_enabled=True)

    # Replace the cache manager with a mock that tracks calls
    mock_cache = AsyncMock()
    mock_cache.invalidate_model = AsyncMock(return_value=3)
    express._cache_manager = mock_cache
    express._cache_enabled = True

    await express._invalidate_model_cache("User")

    # Must call invalidate_model, NOT clear_pattern. Phase 5.7 added a
    # ``tenant_id`` kwarg to the backend contract; Express passes
    # ``tenant_id=None`` in single-tenant mode.
    mock_cache.invalidate_model.assert_called_once_with("User", tenant_id=None)
