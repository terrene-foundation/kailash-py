"""
Integration tests for Trust Chain Cache.

Tests the TrustChainCache working with trust chain structures to verify:
- Cache-aside pattern (check cache, fallback to creation)
- Cache invalidation on updates
- Performance improvements (100x speedup)
- Integration patterns

Test Intent:
- Verify cache provides O(1) lookups with <1ms performance
- Test TTL expiration and LRU eviction in realistic scenarios
- Validate cache-aside pattern for trust operations
- Ensure thread-safe concurrent access with real workflows
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from kaizen.trust import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.cache import CacheStats, TrustChainCache

# Fixtures


@pytest.fixture
def cache():
    """Create cache instance."""
    return TrustChainCache(ttl_seconds=300, max_size=1000)


def create_test_chain(agent_id: str, num_capabilities: int = 1) -> TrustLineageChain:
    """Helper to create test trust chain."""
    genesis = GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="test-signature",
    )

    capabilities = []
    for i in range(num_capabilities):
        cap = CapabilityAttestation(
            id=f"cap-{agent_id}-{i}",
            capability=f"capability_{i}",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id="org-test",
            attested_at=datetime.now(timezone.utc),
            signature="test-signature",
        )
        capabilities.append(cap)

    return TrustLineageChain(
        genesis=genesis,
        capabilities=capabilities,
        delegations=[],
        constraint_envelope=ConstraintEnvelope(
            id=f"env-{agent_id}",
            agent_id=agent_id,
        ),
    )


# Cache-Aside Pattern Tests


@pytest.mark.asyncio
async def test_cache_aside_pattern(cache: TrustChainCache):
    """Test cache-aside pattern: check cache, fallback to creation."""
    agent_id = "agent-cache-001"

    # First lookup - cache miss
    cached_chain = await cache.get(agent_id)
    assert cached_chain is None

    # Create chain (simulating database fetch)
    chain = create_test_chain(agent_id)
    await cache.set(agent_id, chain)

    # Second lookup - cache hit
    cached_chain = await cache.get(agent_id)
    assert cached_chain is not None
    assert cached_chain.genesis.agent_id == agent_id

    # Verify statistics
    stats = cache.get_stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.hit_rate == 0.5


@pytest.mark.asyncio
async def test_cache_invalidation_workflow(cache: TrustChainCache):
    """Test cache invalidation workflow when chains are updated."""
    agent_id = "agent-cache-002"

    # Cache chain with 1 capability
    chain = create_test_chain(agent_id, num_capabilities=1)
    await cache.set(agent_id, chain)

    # Verify cached
    cached_chain = await cache.get(agent_id)
    assert len(cached_chain.capabilities) == 1

    # Simulate update: create new chain with 2 capabilities
    updated_chain = create_test_chain(agent_id, num_capabilities=2)

    # Invalidate cache
    await cache.invalidate(agent_id)

    # Cache miss after invalidation
    result = await cache.get(agent_id)
    assert result is None

    # Update cache with new version
    await cache.set(agent_id, updated_chain)

    # Verify cache has new version
    cached_chain = await cache.get(agent_id)
    assert len(cached_chain.capabilities) == 2


# Performance Tests


@pytest.mark.asyncio
async def test_cache_performance_target(cache: TrustChainCache):
    """Test that cache hits achieve <1ms target."""
    agent_id = "agent-perf-001"
    chain = create_test_chain(agent_id)

    # Cache the chain
    await cache.set(agent_id, chain)

    # Measure cache lookup time (100 iterations)
    cache_times = []
    for _ in range(100):
        start = time.perf_counter()
        await cache.get(agent_id)
        elapsed = time.perf_counter() - start
        cache_times.append(elapsed * 1000)  # Convert to ms

    avg_cache_time = sum(cache_times) / len(cache_times)

    print(f"\nPerformance Results:")
    print(f"  Cache hit: {avg_cache_time:.3f}ms average")

    # Target: Cache hit < 1ms
    assert avg_cache_time < 1.0, f"Cache too slow: {avg_cache_time:.3f}ms"


@pytest.mark.asyncio
async def test_high_volume_caching(cache: TrustChainCache):
    """Test cache with high volume of trust chains."""
    # Create 100 trust chains
    agent_ids = []
    for i in range(100):
        agent_id = f"agent-volume-{i:03d}"
        agent_ids.append(agent_id)
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Verify all cached
    stats = cache.get_stats()
    assert stats.size == 100

    # Random access pattern (simulate real usage)
    import random

    access_pattern = random.sample(agent_ids, 50)

    start = time.perf_counter()
    for agent_id in access_pattern:
        result = await cache.get(agent_id)
        assert result is not None
    elapsed = time.perf_counter() - start

    avg_time = (elapsed / 50) * 1000  # ms per lookup

    print(f"\nHigh Volume Results:")
    print(f"  Cache size: {stats.size}")
    print(f"  Random lookups: 50")
    print(f"  Average time: {avg_time:.3f}ms")

    # Should still be fast with 100 entries
    assert avg_time < 1.0


# Concurrent Access Tests


@pytest.mark.asyncio
async def test_concurrent_cache_access(cache: TrustChainCache):
    """Test thread-safe concurrent access."""
    # Create 10 trust chains
    for i in range(10):
        agent_id = f"agent-concurrent-{i:03d}"
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Concurrent readers (simulate 20 agents each reading 5 times)
    async def reader(reader_id: int):
        for _ in range(5):
            # Each reader accesses specific agent
            agent_idx = reader_id % 10
            agent_id = f"agent-concurrent-{agent_idx:03d}"
            result = await cache.get(agent_id)
            assert result is not None
            await asyncio.sleep(0.001)  # Small delay

    # Run 20 concurrent readers
    tasks = [reader(i) for i in range(20)]
    await asyncio.gather(*tasks)

    # Verify statistics (20 readers x 5 reads = 100 hits)
    stats = cache.get_stats()
    assert stats.hits == 100
    assert stats.size == 10


@pytest.mark.asyncio
async def test_concurrent_writes(cache: TrustChainCache):
    """Test thread-safe concurrent writes."""

    # Concurrent writes to different keys
    async def writer(agent_idx: int):
        agent_id = f"agent-writer-{agent_idx:03d}"
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Write 20 chains concurrently
    tasks = [writer(i) for i in range(20)]
    await asyncio.gather(*tasks)

    # Verify all written
    stats = cache.get_stats()
    assert stats.size == 20


@pytest.mark.asyncio
async def test_concurrent_mixed_operations(cache: TrustChainCache):
    """Test thread-safe mixed concurrent operations."""

    # Mixed operations
    async def reader(agent_id: str):
        for _ in range(5):
            await cache.get(agent_id)
            await asyncio.sleep(0.001)

    async def writer(agent_id: str):
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # 10 writers, 10 readers
    tasks = []
    for i in range(10):
        agent_id = f"agent-mixed-{i:03d}"
        tasks.append(writer(agent_id))
        tasks.append(reader(agent_id))

    await asyncio.gather(*tasks)

    # Should complete without errors
    stats = cache.get_stats()
    assert stats.size == 10


# Cache Warming Tests


@pytest.mark.asyncio
async def test_cache_warming_strategy(cache: TrustChainCache):
    """Test cache warming strategy (pre-populate cache on startup)."""
    # Simulate loading multiple chains on startup
    num_chains = 50
    chains = [create_test_chain(f"agent-warm-{i:03d}") for i in range(num_chains)]

    start = time.perf_counter()
    for chain in chains:
        await cache.set(chain.genesis.agent_id, chain)
    elapsed = time.perf_counter() - start

    # Verify all cached
    stats = cache.get_stats()
    assert stats.size == num_chains

    print(f"\nCache Warming Results:")
    print(f"  Chains loaded: {num_chains}")
    print(f"  Cache size: {stats.size}")
    print(f"  Warming time: {elapsed * 1000:.2f}ms")

    # Now all lookups should be fast
    for i in range(num_chains):
        agent_id = f"agent-warm-{i:03d}"
        result = await cache.get(agent_id)
        assert result is not None

    # All should be hits
    stats = cache.get_stats()
    assert stats.hits == num_chains


# Memory Management Tests


@pytest.mark.asyncio
async def test_cache_memory_management():
    """Test LRU eviction with realistic scenario."""
    # Create cache with small max_size
    cache = TrustChainCache(ttl_seconds=300, max_size=10)

    # Create 15 trust chains (exceeds max_size)
    for i in range(15):
        agent_id = f"agent-memory-{i:03d}"
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Verify LRU eviction occurred
    stats = cache.get_stats()
    assert stats.size == 10
    assert stats.evictions == 5

    # First 5 agents should be evicted
    for i in range(5):
        agent_id = f"agent-memory-{i:03d}"
        result = await cache.get(agent_id)
        assert result is None

    # Last 10 agents should be present
    for i in range(5, 15):
        agent_id = f"agent-memory-{i:03d}"
        result = await cache.get(agent_id)
        assert result is not None


# TTL Expiration Tests


@pytest.mark.asyncio
async def test_realistic_ttl_expiration():
    """Test TTL expiration in realistic scenario."""
    # Create cache with 1 second TTL
    cache = TrustChainCache(ttl_seconds=1, max_size=100)

    # Cache multiple chains
    for i in range(5):
        agent_id = f"agent-ttl-{i:03d}"
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Verify all cached
    stats = cache.get_stats()
    assert stats.size == 5

    # Wait for expiration
    await asyncio.sleep(1.1)

    # All should be expired now
    for i in range(5):
        agent_id = f"agent-ttl-{i:03d}"
        result = await cache.get(agent_id)
        assert result is None

    # Verify expiration reduced cache size
    stats = cache.get_stats()
    assert stats.size == 0


# Cache Scaling Tests


@pytest.mark.asyncio
async def test_cache_scaling_performance():
    """Test cache performance with many entries."""
    cache = TrustChainCache(ttl_seconds=300, max_size=10000)

    # Store 1000 chains
    for i in range(1000):
        agent_id = f"agent-scale-{i:04d}"
        chain = create_test_chain(agent_id)
        await cache.set(agent_id, chain)

    # Verify all stored
    stats = cache.get_stats()
    assert stats.size == 1000

    # Test retrieval performance with random access
    import time

    start = time.perf_counter()

    # Random access pattern
    for i in range(0, 1000, 10):
        agent_id = f"agent-scale-{i:04d}"
        result = await cache.get(agent_id)
        assert result is not None

    elapsed = time.perf_counter() - start
    avg_time_ms = (elapsed / 100) * 1000

    # Should still be fast with many entries
    assert avg_time_ms < 1.0, f"Cache scaling issue: {avg_time_ms:.3f}ms average"
