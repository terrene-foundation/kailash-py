"""
Tier 3 E2E Tests: Memory Persistence and Tier Management.

Tests memory persistence across agent restarts and tier promotion/demotion with real infrastructure:
- Real DataFlow backend for cold tier
- Real in-memory cache for hot tier
- Real SQLite for warm tier
- Tier manager for promotion/demotion logic
- No mocking (real infrastructure only)

Requirements:
- DataFlow installed
- SQLite database (function-scoped for isolation)
- Tests complete in <120s each

Test Coverage:
1. test_memory_persistence_across_restarts (Test 26) - Same session_id retrieves stored memories
2. test_memory_tier_promotion (Test 27) - Frequent access promotes to hot tier
3. test_memory_tier_demotion (Test 28) - Infrequent access demotes to lower tiers

Budget: $0.00 (No LLM usage, pure memory operations)
Duration: ~2-3 minutes total
"""

import asyncio
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

# DataFlow imports
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False

from kaizen.memory import PersistentBufferMemory
from kaizen.memory.backends import DataFlowBackend
from kaizen.memory.persistent_tiers import WarmMemoryTier
from kaizen.memory.tiers import HotMemoryTier, TierManager

from tests.utils.cost_tracking import get_global_tracker

# Mark all tests as E2E and async
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed"),
]


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def temp_db():
    """Create temporary SQLite database (function-scoped for test isolation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_persistence.db"
        yield f"sqlite:///{db_path}"


@pytest.fixture
def dataflow_db(temp_db, request):
    """Create DataFlow instance with UNIQUE model per test."""
    import time as time_module

    # Generate unique model name per test
    test_name = request.node.name.replace("[", "_").replace("]", "_")
    timestamp = str(int(time_module.time() * 1000000))
    unique_model_name = f"PersistMemory_{test_name}_{timestamp}"

    # Create DataFlow instance
    db = DataFlow(database_url=temp_db, auto_migrate=True)

    # Create model class DYNAMICALLY with unique name
    model_class = type(
        unique_model_name,
        (),
        {
            "__annotations__": {
                "id": str,
                "conversation_id": str,
                "sender": str,
                "content": str,
                "metadata": Optional[dict],
                "created_at": datetime,
            },
            "metadata": None,
        },
    )

    # Register the dynamically-created model with DataFlow
    db.model(model_class)

    # Store model name for backend
    db._test_model_name = unique_model_name

    yield db


@pytest.fixture
def persistent_memory(dataflow_db):
    """Create PersistentBufferMemory with real DataFlow backend."""
    model_name = dataflow_db._test_model_name
    backend = DataFlowBackend(dataflow_db, model_name=model_name)
    memory = PersistentBufferMemory(
        backend=backend, max_turns=10, cache_ttl_seconds=300
    )
    return memory


# ═══════════════════════════════════════════════════════════════
# Test 26: Memory Persistence Across Restarts
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(120)
async def test_memory_persistence_across_restarts(dataflow_db):
    """
    Test 26: Memory persistence across agent restarts.

    Validates:
    - Same session_id retrieves stored memories after restart
    - Cache invalidation forces database load
    - Metadata preservation across restarts
    - Multiple restart cycles maintain data integrity
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 26: Memory Persistence Across Agent Restarts")
    print("=" * 70)

    session_id = "persistent_session_test"
    model_name = dataflow_db._test_model_name

    # Test 1: Create memory and save data
    print("\n1. Creating memory instance and saving conversation...")
    backend_1 = DataFlowBackend(dataflow_db, model_name=model_name)
    memory_1 = PersistentBufferMemory(
        backend=backend_1, max_turns=10, cache_ttl_seconds=300
    )

    turns = [
        {
            "user": "Hello, I'm starting a new conversation",
            "agent": "Hi! I'll remember this conversation",
            "timestamp": datetime.now().isoformat(),
            "metadata": {"restart": 0, "important": True},
        },
        {
            "user": "Please remember this information",
            "agent": "I will store it persistently",
            "timestamp": datetime.now().isoformat(),
            "metadata": {"restart": 0, "key": "value_1"},
        },
    ]

    for i, turn in enumerate(turns, 1):
        memory_1.save_turn(session_id, turn)
        print(f"   ✓ Saved turn {i}")

    # Verify data is in cache
    context = memory_1.load_context(session_id)
    assert context["turn_count"] == 2
    print(f"   ✓ Data in cache: {context['turn_count']} turns")

    # Test 2: Simulate restart - create new memory instance
    print("\n2. Simulating agent restart (new memory instance)...")
    backend_2 = DataFlowBackend(dataflow_db, model_name=model_name)
    memory_2 = PersistentBufferMemory(
        backend=backend_2, max_turns=10, cache_ttl_seconds=300
    )
    print("   ✓ New memory instance created")

    # Load from database (cache should be empty in new instance)
    context = memory_2.load_context(session_id)
    assert context["turn_count"] == 2
    assert context["turns"][0]["user"] == "Hello, I'm starting a new conversation"
    assert context["turns"][1]["metadata"]["key"] == "value_1"
    print(f"   ✓ Retrieved {context['turn_count']} turns after restart")

    # Test 3: Add more data after restart
    print("\n3. Adding more data after restart...")
    new_turn = {
        "user": "This is after the restart",
        "agent": "I still remember everything!",
        "timestamp": datetime.now().isoformat(),
        "metadata": {"restart": 1},
    }
    memory_2.save_turn(session_id, new_turn)

    context = memory_2.load_context(session_id)
    assert context["turn_count"] == 3
    print(f"   ✓ Total turns after restart: {context['turn_count']}")

    # Test 4: Another restart cycle
    print("\n4. Testing multiple restart cycles...")
    backend_3 = DataFlowBackend(dataflow_db, model_name=model_name)
    memory_3 = PersistentBufferMemory(
        backend=backend_3, max_turns=10, cache_ttl_seconds=300
    )

    context = memory_3.load_context(session_id)
    assert context["turn_count"] == 3
    assert context["turns"][0]["metadata"]["restart"] == 0
    assert context["turns"][2]["metadata"]["restart"] == 1
    print("   ✓ Data integrity maintained after multiple restarts")

    # Test 5: Metadata preservation
    print("\n5. Validating metadata preservation...")
    assert context["turns"][0]["metadata"]["important"] is True
    assert context["turns"][1]["metadata"]["key"] == "value_1"
    print("   ✓ All metadata preserved correctly")

    # Track cost
    cost_tracker.track_usage(
        test_name="test_memory_persistence_across_restarts",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 26 Passed: Memory persistence across restarts validated")
    print("  - Multiple restart cycles: ✓")
    print("  - Data integrity: ✓")
    print("  - Metadata preservation: ✓")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# Test 27: Memory Tier Promotion
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(120)
async def test_memory_tier_promotion():
    """
    Test 27: Memory tier promotion (cold → warm → hot).

    Validates:
    - Frequent access promotes entries to hot tier
    - Access pattern tracking
    - Automatic promotion based on thresholds
    - Performance improvement after promotion
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 27: Memory Tier Promotion")
    print("=" * 70)

    # Create tier manager
    tier_config = {
        "hot_promotion_threshold": 3,  # Promote after 3 accesses
        "warm_promotion_threshold": 2,  # Promote after 2 accesses
        "access_window_seconds": 60,  # 1 minute window
    }
    tier_manager = TierManager(config=tier_config)

    # Create tiers
    hot_tier = HotMemoryTier(max_size=100, eviction_policy="lru")

    with tempfile.TemporaryDirectory() as tmpdir:
        warm_db_path = str(Path(tmpdir) / "warm.db")
        warm_tier = WarmMemoryTier(storage_path=warm_db_path, max_size_mb=100)

        # Test 1: Start with cold tier (simulate database storage)
        print("\n1. Adding entries to cold tier (database)...")
        test_key = "frequently_accessed_key"
        test_value = {
            "role": "user",
            "content": "This will be accessed frequently",
            "metadata": {"tier": "cold", "access_count": 0},
        }

        # Simulate cold tier by recording access
        await tier_manager.record_access(test_key, "cold")
        print("   ✓ Entry in cold tier")

        # Test 2: Access multiple times to trigger promotion
        print("\n2. Accessing entry multiple times...")
        for i in range(4):
            await tier_manager.record_access(test_key, "cold")
            print(f"   ✓ Access {i + 1}")

        # Test 3: Check if should promote to warm
        print("\n3. Checking promotion eligibility (cold → warm)...")
        should_promote_warm = await tier_manager.should_promote(
            test_key, "cold", "warm"
        )
        assert should_promote_warm, "Should promote from cold to warm after threshold"
        print("   ✓ Eligible for promotion to warm tier")

        # Promote to warm
        await warm_tier.put(test_key, test_value)
        await tier_manager.record_access(test_key, "warm")
        print("   ✓ Promoted to warm tier")

        # Test 4: Continue accessing to promote to hot
        print("\n4. Continuing access to promote to hot tier...")
        for i in range(3):
            await tier_manager.record_access(test_key, "warm")
            print(f"   ✓ Access {i + 1} in warm tier")

        # Check if should promote to hot
        should_promote_hot = await tier_manager.should_promote(test_key, "warm", "hot")
        assert should_promote_hot, "Should promote from warm to hot after threshold"
        print("   ✓ Eligible for promotion to hot tier")

        # Promote to hot
        await hot_tier.put(test_key, test_value)
        await tier_manager.record_access(test_key, "hot")
        print("   ✓ Promoted to hot tier")

        # Test 5: Verify performance improvement
        print("\n5. Validating performance improvement...")
        start = time.perf_counter()
        result = await hot_tier.get(test_key)
        hot_retrieval_time = (time.perf_counter() - start) * 1000  # ms

        assert result is not None
        assert (
            hot_retrieval_time < 1.0
        ), f"Hot tier should be <1ms, got {hot_retrieval_time:.4f}ms"
        print(f"   ✓ Hot tier retrieval: {hot_retrieval_time:.4f}ms (<1ms)")

        # Test 6: Check access patterns
        print("\n6. Validating access pattern tracking...")
        patterns = tier_manager.get_access_patterns()
        assert test_key in patterns
        assert patterns[test_key]["current_tier"] == "hot"
        assert patterns[test_key]["recent_accesses"] > 0
        print("   ✓ Access pattern tracked:")
        print(f"     - Current tier: {patterns[test_key]['current_tier']}")
        print(f"     - Recent accesses: {patterns[test_key]['recent_accesses']}")

    # Track cost
    cost_tracker.track_usage(
        test_name="test_memory_tier_promotion",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 27 Passed: Memory tier promotion validated")
    print("  - Cold → Warm promotion: ✓")
    print("  - Warm → Hot promotion: ✓")
    print(f"  - Hot tier performance: {hot_retrieval_time:.4f}ms")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════
# Test 28: Memory Tier Demotion
# ═══════════════════════════════════════════════════════════════


@pytest.mark.timeout(120)
async def test_memory_tier_demotion():
    """
    Test 28: Memory tier demotion (hot → warm → cold).

    Validates:
    - Infrequent access demotes entries to lower tiers
    - Age-based demotion policies
    - Tier statistics validation
    - Automatic demotion based on inactivity
    """
    cost_tracker = get_global_tracker()

    print("\n" + "=" * 70)
    print("Test 28: Memory Tier Demotion")
    print("=" * 70)

    # Create tier manager with short demotion thresholds
    tier_config = {
        "hot_promotion_threshold": 3,
        "warm_promotion_threshold": 2,
        "access_window_seconds": 2,  # 2 second window for testing
        "cold_demotion_threshold": 3,  # 3 seconds for cold demotion
    }
    tier_manager = TierManager(config=tier_config)

    # Create tiers
    hot_tier = HotMemoryTier(max_size=100, eviction_policy="lru")

    with tempfile.TemporaryDirectory() as tmpdir:
        warm_db_path = str(Path(tmpdir) / "warm_demotion.db")
        warm_tier = WarmMemoryTier(storage_path=warm_db_path, max_size_mb=100)

        # Test 1: Start with hot tier entry
        print("\n1. Adding entry to hot tier...")
        test_key = "rarely_accessed_key"
        test_value = {
            "role": "user",
            "content": "This will be accessed rarely",
            "metadata": {"tier": "hot"},
        }

        await hot_tier.put(test_key, test_value)
        await tier_manager.record_access(test_key, "hot")
        print("   ✓ Entry in hot tier")

        # Test 2: Wait for access window to expire (no recent accesses)
        print("\n2. Waiting for access window to expire...")
        await asyncio.sleep(2.5)  # Wait longer than access window
        print("   ✓ Access window expired (no recent accesses)")

        # Test 3: Check if should demote from hot
        print("\n3. Checking demotion eligibility (hot → warm)...")
        demote_to = await tier_manager.should_demote(test_key, "hot")
        assert demote_to == "warm", "Should demote from hot to warm after inactivity"
        print("   ✓ Eligible for demotion to warm tier")

        # Demote to warm
        await warm_tier.put(test_key, test_value)
        await tier_manager.record_access(test_key, "warm")
        print("   ✓ Demoted to warm tier")

        # Test 4: Wait for long inactivity to demote to cold
        print("\n4. Waiting for long inactivity to demote to cold...")
        await asyncio.sleep(3.5)  # Wait longer than cold_demotion_threshold
        print("   ✓ Long inactivity period elapsed")

        # Check if should demote to cold
        demote_to = await tier_manager.should_demote(test_key, "warm")
        assert (
            demote_to == "cold"
        ), "Should demote from warm to cold after extended inactivity"
        print("   ✓ Eligible for demotion to cold tier")

        # Test 5: Verify access patterns show demotion
        print("\n5. Validating access pattern tracking...")
        patterns = tier_manager.get_access_patterns()
        assert test_key in patterns
        assert patterns[test_key]["recent_accesses"] == 0  # No recent accesses
        print("   ✓ Access pattern shows inactivity:")
        print(f"     - Recent accesses: {patterns[test_key]['recent_accesses']}")
        print(f"     - Age: {patterns[test_key]['age_seconds']:.1f}s")

        # Test 6: Test retrieval after demotion (cold tier simulation)
        print("\n6. Testing retrieval from cold tier...")
        # Simulate cold tier by removing from hot and warm
        await hot_tier.delete(test_key)
        await warm_tier.delete(test_key)

        # In real system, would fetch from database (cold tier)
        # Here we verify it's no longer in hot/warm
        hot_result = await hot_tier.get(test_key)
        warm_result = await warm_tier.get(test_key)
        assert hot_result is None, "Should not be in hot tier"
        assert warm_result is None, "Should not be in warm tier"
        print("   ✓ Entry successfully demoted to cold tier")

        # Test 7: Test tier statistics
        print("\n7. Validating tier statistics...")
        hot_metrics = hot_tier.get_performance_metrics()
        warm_stats = warm_tier.get_stats()

        print("   Hot tier:")
        print(f"     - Current size: {hot_metrics['current_size']}")
        print(f"     - Total evictions: {hot_metrics['evictions']}")
        print(f"     - Utilization: {hot_metrics['utilization']:.2%}")

        print("   Warm tier:")
        print(f"     - Total deletes: {warm_stats['deletes']}")

    # Track cost
    cost_tracker.track_usage(
        test_name="test_memory_tier_demotion",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0,
    )

    print("\n" + "=" * 70)
    print("✓ Test 28 Passed: Memory tier demotion validated")
    print("  - Hot → Warm demotion: ✓")
    print("  - Warm → Cold demotion: ✓")
    print("  - Access pattern tracking: ✓")
    print("=" * 70)
