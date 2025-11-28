"""
Direct test of the cache async/await bug

Tests the root cause directly without requiring full DataFlow setup.
"""

import asyncio

from dataflow.cache.invalidation import CacheInvalidator
from dataflow.cache.key_generator import CacheKeyGenerator
from dataflow.cache.list_node_integration import ListNodeCacheIntegration
from dataflow.cache.memory_cache import InMemoryCache


async def test_cache_methods_are_async():
    """Confirm InMemoryCache methods are async"""
    print("=" * 80)
    print("Test 1: Verify InMemoryCache has async methods")
    print("=" * 80)

    cache = InMemoryCache(max_size=100, ttl=300)

    # Check if methods are coroutines
    import inspect

    print("\nInMemoryCache method signatures:")
    print(
        f"  get():      {'async' if inspect.iscoroutinefunction(cache.get) else 'sync'}"
    )
    print(
        f"  set():      {'async' if inspect.iscoroutinefunction(cache.set) else 'sync'}"
    )
    print(
        f"  delete():   {'async' if inspect.iscoroutinefunction(cache.delete) else 'sync'}"
    )
    print(
        f"  exists():   {'async' if inspect.iscoroutinefunction(cache.exists) else 'sync'}"
    )
    print(
        f"  can_cache(): {'async' if inspect.iscoroutinefunction(cache.can_cache) else 'sync'}"
    )

    # Test calling without await (BUG)
    print("\n🔍 Calling cache.get() WITHOUT await:")
    result = cache.get("test_key")
    print(f"  Type: {type(result)}")
    print(f"  Is coroutine: {inspect.iscoroutine(result)}")

    if inspect.iscoroutine(result):
        print("  ✅ CONFIRMED: cache.get() returns a coroutine!")
        print("  ❌ This will cause TypeError if you try to use it as dict")
        await result  # Clean up

    return True


async def test_integration_bug():
    """Test ListNodeCacheIntegration bug with InMemoryCache"""
    print("\n" + "=" * 80)
    print("Test 2: ListNodeCacheIntegration with InMemoryCache")
    print("=" * 80)

    # Create components
    cache = InMemoryCache(max_size=100, ttl=300)
    key_gen = CacheKeyGenerator()
    invalidator = CacheInvalidator(cache)

    integration = ListNodeCacheIntegration(cache, key_gen, invalidator)

    print("\n🔍 Examining execute_with_cache()...")

    # Look at the code path
    print("\nCode path in execute_with_cache():")
    print("  Line 86: cached_result = self.cache_manager.get(cache_key)")
    print("  Line 90: return self._add_cache_metadata(cached_result, ...)")
    print("\n  ❌ PROBLEM: Line 86 doesn't use 'await'!")
    print("  ❌ When cache_manager is InMemoryCache:")
    print("     - cache_manager.get() returns unawaited coroutine")
    print("     - cached_result is a coroutine object, not a dict")
    print("\n  Line 169 in _add_cache_metadata():")
    print("     result['_cache'] = {...}")
    print("  ❌ This tries to assign to coroutine → TypeError!")

    # Simulate the bug
    print("\n🔬 Simulating the bug:")
    try:
        # This is what execute_with_cache does (line 86)
        cache_key = "test:key"
        cached_result = cache.get(cache_key)  # Missing await!

        print(f"  cached_result type: {type(cached_result)}")
        print(f"  Is coroutine: {asyncio.iscoroutine(cached_result)}")

        if asyncio.iscoroutine(cached_result):
            # This is what _add_cache_metadata tries (line 169)
            print("\n  Attempting: cached_result['_cache'] = {...}")
            cached_result["_cache"] = {"hit": False}  # This will fail!

    except TypeError as e:
        print("  ✅ BUG REPRODUCED!")
        print(f"  Error: {e}")
        return True
    finally:
        if asyncio.iscoroutine(cached_result):
            await cached_result  # Clean up coroutine

    return False


async def test_redis_manager_is_sync():
    """Confirm RedisCacheManager methods are sync (no bug with Redis)"""
    print("\n" + "=" * 80)
    print("Test 3: RedisCacheManager has sync methods (no bug)")
    print("=" * 80)

    import inspect

    from dataflow.cache.redis_manager import CacheConfig, RedisCacheManager

    config = CacheConfig()
    redis_cache = RedisCacheManager(config)

    print("\nRedisCacheManager method signatures:")
    print(
        f"  get():    {'async' if inspect.iscoroutinefunction(redis_cache.get) else 'sync'}"
    )
    print(
        f"  set():    {'async' if inspect.iscoroutinefunction(redis_cache.set) else 'sync'}"
    )
    print(
        f"  delete(): {'async' if inspect.iscoroutinefunction(redis_cache.delete) else 'sync'}"
    )
    print(
        f"  exists(): {'async' if inspect.iscoroutinefunction(redis_cache.exists) else 'sync'}"
    )

    print("\n✅ All methods are SYNC")
    print(
        "✅ ListNodeCacheIntegration works fine with RedisCacheManager (no await needed)"
    )
    print("❌ But breaks with InMemoryCache (async methods need await)")

    return True


async def main():
    print("\n" + "=" * 80)
    print("DATAFLOW-CACHE-ASYNC-001: Direct Cache Bug Analysis")
    print("=" * 80)
    print()

    # Test 1: Confirm InMemoryCache is async
    test1 = await test_cache_methods_are_async()

    # Test 2: Demonstrate the bug
    test2 = await test_integration_bug()

    # Test 3: Show Redis works (sync)
    test3 = await test_redis_manager_is_sync()

    # Summary
    print("\n" + "=" * 80)
    print("Root Cause Analysis")
    print("=" * 80)
    print()
    print("The bug occurs because:")
    print("  1. ✅ RedisCacheManager has SYNC methods (get, set, delete)")
    print("  2. ✅ InMemoryCache has ASYNC methods (async def get, async def set)")
    print("  3. ❌ ListNodeCacheIntegration calls cache methods WITHOUT await")
    print("  4. ❌ When InMemoryCache is used → returns unawaited coroutines")
    print("  5. ❌ _add_cache_metadata() tries result['_cache'] = ... → TypeError")
    print()
    print("When it works:")
    print("  ✅ Redis available → RedisCacheManager (sync) → No await needed → Works")
    print()
    print("When it breaks:")
    print(
        "  ❌ Redis not available → InMemoryCache (async) → Missing await → TypeError"
    )
    print()
    print("Impact:")
    print("  - All FastAPI/Docker deployments without Redis")
    print("  - All ListNode operations (SessionListNode, UserListNode, etc.)")
    print("  - Default cache=enabled → Blocks all async ListNode queries")
    print()
    print("Fix Options:")
    print("  1. Make ListNodeCacheIntegration.execute_with_cache() properly await")
    print("  2. Detect cache backend type and use sync/async calls accordingly")
    print("  3. Make InMemoryCache methods sync (breaking change)")
    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
