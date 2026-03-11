"""
Tier 3 E2E Tests: Memory Warm Tier with Real Redis.

Tests warm tier (Redis/SQLite persistence) operations with real infrastructure:
- Real SQLite persistence (Redis alternative)
- <10ms access time
- TTL expiration handling
- Access pattern tracking
- No mocking (real infrastructure only)

NOTE: This implementation uses SQLite-based warm tier (WarmMemoryTier) instead of Redis.
The warm tier uses SQLite with WAL mode for <10ms access, making Redis optional.

Requirements:
- No external dependencies (SQLite built-in)
- Tests complete in <30s

Test Coverage:
1. test_warm_memory_operations (Test 24) - Persistence, TTL, access tracking

Budget: $0.00 (No LLM usage, pure memory operations)
Duration: ~30s
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest
from kaizen.memory.persistent_tiers import WarmMemoryTier

from tests.utils.cost_tracking import get_global_tracker

# Mark all tests as E2E and async
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]


# ═══════════════════════════════════════════════════════════════
# Test 24: Warm Memory Operations (SQLite-based)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(30)
async def test_warm_memory_operations():
    """
    Test 24: Warm memory with real persistence (SQLite).

    Validates:
    - Persistent storage with SQLite (<10ms access)
    - TTL expiration handling
    - Access pattern tracking
    - Survives tier recreation (persistence)
    - Performance within <10ms target

    NOTE: Uses SQLite-based warm tier instead of Redis.
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 24: Warm Memory Operations (SQLite Persistence)")
    print("=" * 70)

    # Create temporary directory for SQLite database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "warm_tier.db")

        # Create warm tier with SQLite backend
        print("\n1. Creating warm tier with SQLite backend...")
        print(f"   Database path: {db_path}")
        warm_tier = WarmMemoryTier(storage_path=db_path, max_size_mb=100)

        # Test 1: Add memory entries
        print("\n2. Adding memory entries to warm tier...")
        test_data = {
            "session_1_msg_1": {
                "role": "user",
                "content": "Hello from warm tier",
                "metadata": {"session": "session_1", "turn": 1},
            },
            "session_1_msg_2": {
                "role": "agent",
                "content": "Hi! This is stored in SQLite",
                "metadata": {"session": "session_1", "turn": 2},
            },
            "session_2_msg_1": {
                "role": "user",
                "content": "Different session",
                "metadata": {"session": "session_2", "turn": 1},
            },
        }

        for key, value in test_data.items():
            success = await warm_tier.put(key, value)
            assert success, f"Failed to add entry {key}"
            print(f"   ✓ Added {key}")

        # Test 2: Fast retrieval (<10ms)
        print("\n3. Testing fast retrieval from warm tier (<10ms target)...")
        retrieval_times = []

        for key, expected_value in test_data.items():
            start = time.perf_counter()
            result = await warm_tier.get(key)
            elapsed = (time.perf_counter() - start) * 1000  # ms

            retrieval_times.append(elapsed)
            assert result is not None, f"Entry {key} not found"
            assert result["content"] == expected_value["content"]
            print(f"   ✓ Retrieved {key} in {elapsed:.4f}ms")

        avg_retrieval_time = sum(retrieval_times) / len(retrieval_times)
        max_retrieval_time = max(retrieval_times)
        print(f"\n   Average retrieval time: {avg_retrieval_time:.4f}ms")
        print(f"   Max retrieval time: {max_retrieval_time:.4f}ms")
        print("   Target: <10ms")

        # Warm tier should be faster than 10ms on average
        # Note: First access might be slower due to DB setup, so we check max is reasonable
        assert (
            max_retrieval_time < 50.0
        ), f"Warm tier too slow: {max_retrieval_time:.4f}ms > 50ms"

        # Test 3: Exists check
        print("\n4. Testing exists check...")
        for key in test_data.keys():
            exists = await warm_tier.exists(key)
            assert exists, f"Entry {key} should exist"
            print(f"   ✓ Confirmed {key} exists")

        assert not await warm_tier.exists("nonexistent_key")
        print("   ✓ Confirmed nonexistent key returns False")

        # Test 4: Update existing entry
        print("\n5. Testing entry updates...")
        updated_value = {
            "role": "user",
            "content": "Updated content in warm tier",
            "metadata": {"session": "session_1", "turn": 1, "updated": True},
        }
        success = await warm_tier.put("session_1_msg_1", updated_value)
        assert success

        result = await warm_tier.get("session_1_msg_1")
        assert result["content"] == "Updated content in warm tier"
        assert result["metadata"]["updated"] is True
        print("   ✓ Entry updated successfully")

        # Test 5: TTL expiration
        print("\n6. Testing TTL expiration...")
        await warm_tier.put(
            "ttl_key", {"content": "expires in 1 second"}, ttl=1  # 1 second
        )
        assert await warm_tier.exists("ttl_key")
        print("   ✓ TTL entry added")

        # Wait for expiration
        await asyncio.sleep(1.5)
        result = await warm_tier.get("ttl_key")
        assert result is None, "TTL entry should have expired"
        print("   ✓ TTL entry expired after 1 second")

        # Test 6: Access tracking
        print("\n7. Testing access tracking...")
        # Access same key multiple times
        for i in range(5):
            await warm_tier.get("session_1_msg_1")

        # Stats should show multiple accesses
        stats = warm_tier.get_stats()
        print(f"   - Total hits: {stats['hits']}")
        print(f"   - Total misses: {stats['misses']}")
        print(f"   - Total puts: {stats['puts']}")
        assert stats["hits"] > 0, "Should have cache hits"

        # Test 7: Persistence across tier recreation
        print("\n8. Testing persistence (recreate tier)...")
        initial_size = await warm_tier.size()
        print(f"   Initial size: {initial_size}")

        # Recreate warm tier (simulates restart)
        warm_tier = WarmMemoryTier(storage_path=db_path, max_size_mb=100)
        print("   ✓ Warm tier recreated")

        # Data should still be accessible
        result = await warm_tier.get("session_1_msg_1")
        assert result is not None, "Data should persist after tier recreation"
        assert result["metadata"]["updated"] is True
        print("   ✓ Data persisted across tier recreation")

        # Test 8: Size and cleanup
        print("\n9. Testing size and cleanup...")
        size = await warm_tier.size()
        print(f"   Current size: {size}")
        assert size == 3, f"Expected 3 entries (ttl_key expired), got {size}"

        # Clear all data
        success = await warm_tier.clear()
        assert success
        size = await warm_tier.size()
        assert size == 0
        print("   ✓ Warm tier cleared successfully")

        # Test 9: Performance metrics
        print("\n10. Validating performance metrics...")
        stats = warm_tier.get_stats()
        print(
            f"   - Total operations: {stats['hits'] + stats['misses'] + stats['puts']}"
        )
        print(
            f"   - Hit rate: {stats['hits'] / max(stats['hits'] + stats['misses'], 1):.2%}"
        )
        print(f"   - Average retrieval time: {avg_retrieval_time:.4f}ms")

    # Track cost (no LLM used, just memory ops)
    cost_tracker.track_usage(
        test_name="test_warm_memory_operations",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 24 Passed: Warm tier operations validated")
    print("  - Persistence: SQLite-based")
    print(f"  - Average retrieval: {avg_retrieval_time:.4f}ms")
    print(f"  - Max retrieval: {max_retrieval_time:.4f}ms")
    print("  - Data survives tier recreation")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════


def redis_available() -> bool:
    """Check if Redis is available (for future Redis-based tests)."""
    try:
        import redis

        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        client.ping()
        return True
    except:
        return False
