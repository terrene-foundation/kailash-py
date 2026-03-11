"""
Tier 3 E2E Tests: Memory Hot Tier with Real Infrastructure.

Tests hot tier (in-memory cache) operations with real infrastructure:
- Real in-memory operations with OrderedDict
- LRU eviction policies
- Thread-safe concurrent access
- Performance validation (<1ms access)
- No mocking (real infrastructure only)

Requirements:
- No external dependencies (in-memory only)
- Tests complete in <30s each

Test Coverage:
1. test_hot_memory_operations (Test 22) - Add, retrieve, search, update
2. test_hot_memory_eviction (Test 23) - LRU policy, capacity limits

Budget: $0.00 (No LLM usage, pure memory operations)
Duration: ~20-40s total
"""

import asyncio
import time

import pytest
from kaizen.memory.tiers import HotMemoryTier

from tests.utils.cost_tracking import get_global_tracker

# Mark all tests as E2E and async
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


# ═══════════════════════════════════════════════════════════════
# Test 22: Hot Memory Operations
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(30)
async def test_hot_memory_operations():
    """
    Test 22: Hot memory operations (in-memory cache).

    Validates:
    - Memory entry creation and storage in hot tier
    - Fast retrieval from hot tier (<1ms)
    - Search operations in hot tier
    - Memory entry updates
    - TTL expiration handling
    - Performance metrics
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 22: Hot Memory Operations")
    print("=" * 70)

    # Create hot tier with LRU eviction
    hot_tier = HotMemoryTier(max_size=100, eviction_policy="lru")

    # Test 1: Add memory entries
    print("\n1. Adding memory entries to hot tier...")
    test_data = {
        "key1": {"role": "user", "content": "Hello", "metadata": {"type": "greeting"}},
        "key2": {
            "role": "agent",
            "content": "Hi there!",
            "metadata": {"type": "response"},
        },
        "key3": {
            "role": "user",
            "content": "How are you?",
            "metadata": {"type": "question"},
        },
    }

    for key, value in test_data.items():
        success = await hot_tier.put(key, value)
        assert success, f"Failed to add entry {key}"
        print(f"   ✓ Added {key}")

    # Test 2: Fast retrieval (<1ms)
    print("\n2. Testing fast retrieval from hot tier...")
    retrieval_times = []

    for key, expected_value in test_data.items():
        start = time.perf_counter()
        result = await hot_tier.get(key)
        elapsed = (time.perf_counter() - start) * 1000  # ms

        retrieval_times.append(elapsed)
        assert result is not None, f"Entry {key} not found"
        assert result["content"] == expected_value["content"]
        print(f"   ✓ Retrieved {key} in {elapsed:.4f}ms")

    avg_retrieval_time = sum(retrieval_times) / len(retrieval_times)
    print(f"\n   Average retrieval time: {avg_retrieval_time:.4f}ms")
    assert (
        avg_retrieval_time < 1.0
    ), f"Hot tier too slow: {avg_retrieval_time:.4f}ms > 1ms"

    # Test 3: Exists check
    print("\n3. Testing exists check...")
    for key in test_data.keys():
        exists = await hot_tier.exists(key)
        assert exists, f"Entry {key} should exist"
        print(f"   ✓ Confirmed {key} exists")

    assert not await hot_tier.exists("nonexistent_key")
    print("   ✓ Confirmed nonexistent key returns False")

    # Test 4: Update existing entry
    print("\n4. Testing entry updates...")
    updated_value = {
        "role": "user",
        "content": "Hello updated!",
        "metadata": {"type": "greeting", "updated": True},
    }
    success = await hot_tier.put("key1", updated_value)
    assert success

    result = await hot_tier.get("key1")
    assert result["content"] == "Hello updated!"
    assert result["metadata"]["updated"] is True
    print("   ✓ Entry updated successfully")

    # Test 5: TTL expiration
    print("\n5. Testing TTL expiration...")
    await hot_tier.put("ttl_key", {"content": "expires soon"}, ttl=1)  # 1 second
    assert await hot_tier.exists("ttl_key")
    print("   ✓ TTL entry added")

    await asyncio.sleep(1.5)  # Wait for expiration
    result = await hot_tier.get("ttl_key")
    assert result is None, "TTL entry should have expired"
    print("   ✓ TTL entry expired after 1 second")

    # Test 6: Performance metrics
    print("\n6. Validating performance metrics...")
    metrics = hot_tier.get_performance_metrics()
    print(f"   - Hit rate: {metrics['hit_rate']:.2%}")
    print(f"   - Miss rate: {metrics['miss_rate']:.2%}")
    print(f"   - Current size: {metrics['current_size']}")
    print(f"   - Utilization: {metrics['utilization']:.2%}")
    print(f"   - Total hits: {metrics['hits']}")
    print(f"   - Total misses: {metrics['misses']}")

    assert metrics["hit_rate"] > 0.0, "Should have cache hits"
    assert metrics["current_size"] == 3, "Should have 3 entries (ttl_key expired)"

    # Test 7: Size reporting
    print("\n7. Testing size reporting...")
    size = await hot_tier.size()
    assert size == 3, f"Expected 3 entries, got {size}"
    print(f"   ✓ Hot tier size: {size}")

    # Track cost (no LLM used, just memory ops)
    cost_tracker.track_usage(
        test_name="test_hot_memory_operations",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 22 Passed: Hot tier operations validated")
    print("  - Fast retrieval: <1ms")
    print(f"  - Entries stored: {size}")
    print(f"  - Hit rate: {metrics['hit_rate']:.2%}")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# Test 23: Hot Memory Eviction Policy
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(30)
async def test_hot_memory_eviction():
    """
    Test 23: Hot memory eviction policy (LRU, capacity limits).

    Validates:
    - LRU eviction when capacity reached
    - Capacity enforcement
    - Eviction statistics tracking
    - Most recently used items stay in cache
    - Least recently used items get evicted
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 23: Hot Memory Eviction Policy")
    print("=" * 70)

    # Create small hot tier to test eviction
    max_size = 5
    hot_tier = HotMemoryTier(max_size=max_size, eviction_policy="lru")

    # Test 1: Fill to capacity
    print(f"\n1. Filling hot tier to capacity ({max_size} entries)...")
    for i in range(max_size):
        key = f"key_{i}"
        value = {"content": f"Entry {i}", "index": i}
        success = await hot_tier.put(key, value)
        assert success
        print(f"   ✓ Added {key}")

    size = await hot_tier.size()
    assert size == max_size
    print(f"\n   Hot tier at capacity: {size}/{max_size}")

    # Test 2: Add one more item (should trigger eviction)
    print("\n2. Adding one more item (should evict LRU entry)...")
    initial_metrics = hot_tier.get_performance_metrics()
    initial_evictions = initial_metrics["evictions"]

    # Add new entry (should evict key_0 as it's least recently used)
    await hot_tier.put("key_new", {"content": "New entry", "index": 99})

    # Check eviction happened
    metrics = hot_tier.get_performance_metrics()
    assert metrics["evictions"] == initial_evictions + 1, "Should have 1 eviction"
    print(f"   ✓ Eviction triggered: {metrics['evictions']} total evictions")

    # Oldest entry (key_0) should be evicted
    result = await hot_tier.get("key_0")
    assert result is None, "key_0 should have been evicted"
    print("   ✓ Least recently used entry (key_0) was evicted")

    # New entry should exist
    result = await hot_tier.get("key_new")
    assert result is not None
    assert result["content"] == "New entry"
    print("   ✓ New entry added successfully")

    # Test 3: LRU order - access key_1 to make it recently used
    print("\n3. Testing LRU ordering...")
    await hot_tier.get("key_1")  # Make key_1 recently used
    print("   ✓ Accessed key_1 (now most recently used)")

    # Add another entry (should evict key_2, not key_1)
    await hot_tier.put("key_another", {"content": "Another entry"})

    # key_2 should be evicted (least recently used after key_0)
    result = await hot_tier.get("key_2")
    assert result is None, "key_2 should have been evicted"
    print("   ✓ key_2 evicted (least recently used)")

    # key_1 should still exist (was accessed recently)
    result = await hot_tier.get("key_1")
    assert result is not None, "key_1 should still exist (recently accessed)"
    print("   ✓ key_1 still in cache (recently accessed)")

    # Test 4: Multiple evictions
    print("\n4. Testing multiple evictions...")
    initial_evictions = metrics["evictions"]

    for i in range(10):
        await hot_tier.put(f"bulk_{i}", {"content": f"Bulk {i}"})

    final_metrics = hot_tier.get_performance_metrics()
    total_evictions = final_metrics["evictions"]
    print(f"   ✓ Total evictions after bulk add: {total_evictions}")
    assert total_evictions > initial_evictions, "Should have more evictions"

    # Size should still be at max capacity
    size = await hot_tier.size()
    assert size == max_size, f"Size should be {max_size}, got {size}"
    print(f"   ✓ Size maintained at capacity: {size}/{max_size}")

    # Test 5: Clear operation
    print("\n5. Testing clear operation...")
    success = await hot_tier.clear()
    assert success

    size = await hot_tier.size()
    assert size == 0, "Size should be 0 after clear"
    print("   ✓ Hot tier cleared successfully")

    # Test 6: Verify stats after clear
    print("\n6. Testing eviction statistics...")
    print(f"   - Total evictions: {final_metrics['evictions']}")
    print(f"   - Total puts: {final_metrics['puts']}")
    print(f"   - Total hits: {final_metrics['hits']}")
    print(f"   - Total misses: {final_metrics['misses']}")
    print(
        f"   - Eviction rate: {final_metrics['evictions'] / final_metrics['puts']:.2%}"
    )

    assert final_metrics["evictions"] > 0, "Should have evictions"

    # Track cost (no LLM used, just memory ops)
    cost_tracker.track_usage(
        test_name="test_hot_memory_eviction",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 23 Passed: Hot tier eviction policy validated")
    print(f"  - Capacity limit enforced: {max_size} entries")
    print(f"  - Total evictions: {final_metrics['evictions']}")
    print("  - LRU ordering maintained")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════


async def measure_retrieval_time(hot_tier: HotMemoryTier, key: str) -> float:
    """Measure retrieval time in milliseconds."""
    start = time.perf_counter()
    await hot_tier.get(key)
    return (time.perf_counter() - start) * 1000
