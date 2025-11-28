"""
Fix Verification Test for DATAFLOW-CACHE-ASYNC-001

Verifies that the async/await bug fix works correctly with both cache backends.
"""

import asyncio

from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter
from dataflow.cache.invalidation import CacheInvalidator
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.list_node_integration import ListNodeCacheIntegration
from dataflow.cache.memory_cache import InMemoryCache
from dataflow.cache.redis_manager import CacheConfig, RedisCacheManager


async def test_inmemory_cache_fix():
    """Verify fix works with InMemoryCache (async backend)."""
    print("=" * 80)
    print("Test 1: InMemoryCache (Async Backend)")
    print("=" * 80)

    # Create InMemoryCache (async)
    memory_cache = InMemoryCache()
    key_gen = CacheKeyGenerator()
    invalidator = CacheInvalidator(memory_cache)

    integration = ListNodeCacheIntegration(memory_cache, key_gen, invalidator)

    print("\n✅ Testing execute_with_cache with InMemoryCache...")

    # Test cache miss
    execution_count = 0

    def executor():
        nonlocal execution_count
        execution_count += 1
        return {"records": [{"id": 1, "name": "Alice"}]}

    result = await integration.execute_with_cache(
        model_name="User",
        query="SELECT * FROM users",
        params=[],
        executor_func=executor,
        cache_enabled=True,
    )

    print(f"  Cache miss result: {result}")
    print(f"  Cache hit: {result['_cache']['hit']}")
    print(f"  Executor called: {execution_count} times")

    assert result["_cache"]["hit"] is False
    assert execution_count == 1
    assert result["records"] == [{"id": 1, "name": "Alice"}]

    # Test cache hit
    result2 = await integration.execute_with_cache(
        model_name="User",
        query="SELECT * FROM users",
        params=[],
        executor_func=executor,
        cache_enabled=True,
    )

    print(f"\n  Cache hit result: {result2}")
    print(f"  Cache hit: {result2['_cache']['hit']}")
    print(f"  Executor called: {execution_count} times (should still be 1)")

    assert result2["_cache"]["hit"] is True
    assert execution_count == 1  # Should not execute again
    assert result2["records"] == [{"id": 1, "name": "Alice"}]

    print("\n✅ SUCCESS: InMemoryCache fix verified!")
    return True


async def test_async_redis_adapter_fix():
    """Verify fix works with AsyncRedisCacheAdapter (wrapped sync backend)."""
    print("\n" + "=" * 80)
    print("Test 2: AsyncRedisCacheAdapter (Wrapped Sync Backend)")
    print("=" * 80)

    # Create mock sync Redis manager
    from unittest.mock import Mock

    mock_redis_manager = Mock()
    mock_redis_manager.get = Mock(return_value=None)
    mock_redis_manager.set = Mock(return_value=True)
    mock_redis_manager.can_cache = Mock(return_value=True)

    # Wrap in async adapter
    async_adapter = AsyncRedisCacheAdapter(mock_redis_manager)

    key_gen = CacheKeyGenerator()
    invalidator = Mock()

    integration = ListNodeCacheIntegration(async_adapter, key_gen, invalidator)

    print("\n✅ Testing execute_with_cache with AsyncRedisCacheAdapter...")

    # Test cache miss (adapter wraps sync calls)
    execution_count = 0

    def executor():
        nonlocal execution_count
        execution_count += 1
        return {"records": [{"id": 2, "name": "Bob"}]}

    result = await integration.execute_with_cache(
        model_name="User",
        query="SELECT * FROM users WHERE id = ?",
        params=[2],
        executor_func=executor,
        cache_enabled=True,
    )

    print(f"  Cache miss result: {result}")
    print(f"  Cache hit: {result['_cache']['hit']}")
    print(f"  Mock Redis get called: {mock_redis_manager.get.called}")
    print(f"  Mock Redis set called: {mock_redis_manager.set.called}")

    assert result["_cache"]["hit"] is False
    assert execution_count == 1
    assert result["records"] == [{"id": 2, "name": "Bob"}]

    # Verify sync methods were called (via adapter)
    assert mock_redis_manager.can_cache.called
    assert mock_redis_manager.get.called
    assert mock_redis_manager.set.called

    print("\n✅ SUCCESS: AsyncRedisCacheAdapter fix verified!")
    return True


async def test_no_await_error():
    """Verify the bug is actually fixed (no TypeError)."""
    print("\n" + "=" * 80)
    print("Test 3: Verify No TypeError with Async Cache")
    print("=" * 80)

    memory_cache = InMemoryCache()
    key_gen = CacheKeyGenerator()
    invalidator = CacheInvalidator(memory_cache)

    integration = ListNodeCacheIntegration(memory_cache, key_gen, invalidator)

    print("\n✅ Executing with cache enabled (would previously fail)...")

    try:
        result = await integration.execute_with_cache(
            model_name="User",
            query="SELECT * FROM users",
            params=[],
            executor_func=lambda: {"data": "test"},
            cache_enabled=True,
        )

        print(f"  Result type: {type(result)}")
        print(f"  Result has _cache: {'_cache' in result}")

        # Verify result is dict, not coroutine
        assert isinstance(result, dict)
        assert "_cache" in result
        assert not asyncio.iscoroutine(result)

        print("\n✅ SUCCESS: No TypeError - fix verified!")
        return True

    except TypeError as e:
        print(f"\n❌ FAILED: TypeError still occurs: {e}")
        return False


async def main():
    """Run all verification tests."""
    print("\n" + "=" * 80)
    print("DATAFLOW-CACHE-ASYNC-001: Fix Verification Suite")
    print("=" * 80)
    print()

    # Test 1: InMemoryCache
    test1_passed = await test_inmemory_cache_fix()

    # Test 2: AsyncRedisCacheAdapter
    test2_passed = await test_async_redis_adapter_fix()

    # Test 3: No TypeError
    test3_passed = await test_no_await_error()

    # Summary
    print("\n" + "=" * 80)
    print("Fix Verification Summary")
    print("=" * 80)
    print(
        f"InMemoryCache test:           {'✅ PASSED' if test1_passed else '❌ FAILED'}"
    )
    print(
        f"AsyncRedisCacheAdapter test:  {'✅ PASSED' if test2_passed else '❌ FAILED'}"
    )
    print(
        f"No TypeError test:            {'✅ PASSED' if test3_passed else '❌ FAILED'}"
    )
    print()

    all_passed = test1_passed and test2_passed and test3_passed

    if all_passed:
        print("🎉 ALL TESTS PASSED - Fix verified successfully!")
        print()
        print("The fix implements:")
        print("  1. AsyncRedisCacheAdapter - wraps sync Redis with async interface")
        print("  2. Added 'await' to ListNodeCacheIntegration (3 locations)")
        print("  3. Both cache backends now have unified async interface")
        print()
        print("Impact:")
        print("  ✅ InMemoryCache (async) - works correctly")
        print("  ✅ Redis (sync wrapped) - works correctly via adapter")
        print("  ✅ ListNode operations - no longer throw TypeError")
    else:
        print("❌ SOME TESTS FAILED - Review fix implementation")

    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
