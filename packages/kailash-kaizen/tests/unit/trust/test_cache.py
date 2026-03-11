"""
Unit tests for Trust Chain Cache (EATP Week 11).

Tests the TrustChainCache implementation for:
- Basic get/set operations
- TTL-based expiration
- LRU eviction when max_size exceeded
- Thread-safe concurrent access
- Statistics tracking
- Cleanup operations

Target: <1ms cache hit performance
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kaizen.trust.cache import CacheEntry, CacheStats, TrustChainCache
from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    GenesisRecord,
    TrustLineageChain,
)

# Test Fixtures


@pytest.fixture
def sample_genesis() -> GenesisRecord:
    """Create a sample genesis record for testing."""
    return GenesisRecord(
        id="gen-001",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="test-signature",
        signature_algorithm="Ed25519",
    )


@pytest.fixture
def sample_chain(sample_genesis: GenesisRecord) -> TrustLineageChain:
    """Create a sample trust chain for testing."""
    capability = CapabilityAttestation(
        id="cap-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACCESS,
        constraints=["read_only"],
        attester_id="org-acme",
        attested_at=datetime.now(timezone.utc),
        signature="test-signature",
    )

    return TrustLineageChain(
        genesis=sample_genesis,
        capabilities=[capability],
        delegations=[],
        constraint_envelope=ConstraintEnvelope(
            id="env-001",
            agent_id="agent-001",
        ),
    )


@pytest.fixture
def cache() -> TrustChainCache:
    """Create a cache instance for testing."""
    return TrustChainCache(ttl_seconds=300, max_size=100)


# Basic Operations Tests


@pytest.mark.asyncio
async def test_cache_miss(cache: TrustChainCache):
    """Test cache miss returns None."""
    result = await cache.get("nonexistent-agent")
    assert result is None

    stats = cache.get_stats()
    assert stats.misses == 1
    assert stats.hits == 0


@pytest.mark.asyncio
async def test_cache_hit(cache: TrustChainCache, sample_chain: TrustLineageChain):
    """Test cache hit returns stored chain."""
    # Store chain
    await cache.set("agent-001", sample_chain)

    # Retrieve chain
    result = await cache.get("agent-001")
    assert result is not None
    assert result.genesis.agent_id == "agent-001"
    assert result.genesis.id == "gen-001"

    stats = cache.get_stats()
    assert stats.hits == 1
    assert stats.misses == 0


@pytest.mark.asyncio
async def test_cache_update(cache: TrustChainCache, sample_chain: TrustLineageChain):
    """Test updating an existing cache entry."""
    # Store initial chain
    await cache.set("agent-001", sample_chain)

    # Update with modified chain
    sample_chain.capabilities.append(
        CapabilityAttestation(
            id="cap-002",
            capability="modify_data",
            capability_type=CapabilityType.ACTION,
            constraints=["audit_required"],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            signature="test-signature",
        )
    )
    await cache.set("agent-001", sample_chain)

    # Retrieve updated chain
    result = await cache.get("agent-001")
    assert result is not None
    assert len(result.capabilities) == 2


# TTL Expiration Tests


@pytest.mark.asyncio
async def test_ttl_expiration(sample_chain: TrustLineageChain):
    """Test that entries expire after TTL."""
    # Create cache with 1 second TTL
    cache = TrustChainCache(ttl_seconds=1, max_size=100)

    # Store chain
    await cache.set("agent-001", sample_chain)

    # Immediate retrieval should succeed
    result = await cache.get("agent-001")
    assert result is not None

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Retrieval after expiration should fail
    result = await cache.get("agent-001")
    assert result is None

    # Should count as a miss
    stats = cache.get_stats()
    assert stats.misses == 1


@pytest.mark.asyncio
async def test_cleanup_expired(sample_chain: TrustLineageChain):
    """Test explicit cleanup of expired entries."""
    cache = TrustChainCache(ttl_seconds=1, max_size=100)

    # Store multiple chains
    for i in range(5):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:03d}",
                agent_id=f"agent-{i:03d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:03d}", chain)

    # Verify all stored
    stats = cache.get_stats()
    assert stats.size == 5

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Cleanup expired
    removed = await cache.cleanup_expired()
    assert removed == 5

    # Verify all removed
    stats = cache.get_stats()
    assert stats.size == 0


# LRU Eviction Tests


@pytest.mark.asyncio
async def test_lru_eviction():
    """Test LRU eviction when max_size exceeded."""
    cache = TrustChainCache(ttl_seconds=300, max_size=3)

    # Store 3 chains (at capacity)
    for i in range(3):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:03d}",
                agent_id=f"agent-{i:03d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:03d}", chain)

    # Verify at capacity
    stats = cache.get_stats()
    assert stats.size == 3
    assert stats.evictions == 0

    # Access agent-001 to make it recently used
    await cache.get("agent-001")

    # Add 4th chain - should evict agent-000 (least recently used)
    chain = TrustLineageChain(
        genesis=GenesisRecord(
            id="gen-003",
            agent_id="agent-003",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="test-signature",
        ),
    )
    await cache.set("agent-003", chain)

    # Verify eviction occurred
    stats = cache.get_stats()
    assert stats.size == 3
    assert stats.evictions == 1

    # Verify agent-000 was evicted
    result = await cache.get("agent-000")
    assert result is None

    # Verify agent-001 still present (was accessed recently)
    result = await cache.get("agent-001")
    assert result is not None


@pytest.mark.asyncio
async def test_lru_ordering():
    """Test that LRU ordering is maintained correctly."""
    cache = TrustChainCache(ttl_seconds=300, max_size=3)

    # Store 3 chains
    for i in range(3):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:03d}",
                agent_id=f"agent-{i:03d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:03d}", chain)

    # Access in order: 0, 1, 2 (making 0 least recently used)
    await cache.get("agent-000")
    await cache.get("agent-001")
    await cache.get("agent-002")

    # Add 4th chain - should evict agent-000
    chain = TrustLineageChain(
        genesis=GenesisRecord(
            id="gen-003",
            agent_id="agent-003",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="test-signature",
        ),
    )
    await cache.set("agent-003", chain)

    # Now access order is: 1, 2, 3 (1 is least recently used)
    # Add 5th chain - should evict agent-001
    chain = TrustLineageChain(
        genesis=GenesisRecord(
            id="gen-004",
            agent_id="agent-004",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="test-signature",
        ),
    )
    await cache.set("agent-004", chain)

    # Verify evictions
    assert await cache.get("agent-000") is None
    assert await cache.get("agent-001") is None
    assert await cache.get("agent-002") is not None
    assert await cache.get("agent-003") is not None
    assert await cache.get("agent-004") is not None


# Statistics Tests


@pytest.mark.asyncio
async def test_statistics_tracking(
    cache: TrustChainCache, sample_chain: TrustLineageChain
):
    """Test that statistics are tracked correctly."""
    # Initial stats
    stats = cache.get_stats()
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.hit_rate == 0.0
    assert stats.size == 0
    assert stats.evictions == 0

    # Cache miss
    await cache.get("agent-001")
    stats = cache.get_stats()
    assert stats.misses == 1

    # Store and hit
    await cache.set("agent-001", sample_chain)
    await cache.get("agent-001")
    stats = cache.get_stats()
    assert stats.hits == 1
    assert stats.size == 1

    # Calculate hit rate
    stats = cache.get_stats()
    assert stats.hit_rate == 0.5  # 1 hit / 2 total requests


@pytest.mark.asyncio
async def test_hit_rate_calculation(
    cache: TrustChainCache, sample_chain: TrustLineageChain
):
    """Test hit rate calculation."""
    # Store chain
    await cache.set("agent-001", sample_chain)

    # 5 hits, 0 misses
    for _ in range(5):
        await cache.get("agent-001")

    stats = cache.get_stats()
    assert stats.hits == 5
    assert stats.misses == 0
    assert stats.hit_rate == 1.0

    # 5 misses (use agent IDs that don't exist: agent-100 through agent-104)
    for i in range(100, 105):
        await cache.get(f"agent-{i:03d}")

    stats = cache.get_stats()
    assert stats.hits == 5
    assert stats.misses == 5
    assert stats.hit_rate == 0.5


@pytest.mark.asyncio
async def test_reset_stats(cache: TrustChainCache, sample_chain: TrustLineageChain):
    """Test statistics reset."""
    # Generate some stats
    await cache.set("agent-001", sample_chain)
    await cache.get("agent-001")
    await cache.get("agent-002")

    # Verify stats exist
    stats = cache.get_stats()
    assert stats.hits > 0 or stats.misses > 0

    # Reset stats
    cache.reset_stats()

    # Verify stats cleared
    stats = cache.get_stats()
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.evictions == 0
    # Size should not be reset
    assert stats.size == 1


# Invalidation Tests


@pytest.mark.asyncio
async def test_invalidate_specific(
    cache: TrustChainCache, sample_chain: TrustLineageChain
):
    """Test invalidating a specific cache entry."""
    # Store multiple chains
    for i in range(3):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:03d}",
                agent_id=f"agent-{i:03d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:03d}", chain)

    # Verify all present
    stats = cache.get_stats()
    assert stats.size == 3

    # Invalidate one
    await cache.invalidate("agent-001")

    # Verify only one removed
    stats = cache.get_stats()
    assert stats.size == 2

    # Verify correct one removed
    assert await cache.get("agent-000") is not None
    assert await cache.get("agent-001") is None
    assert await cache.get("agent-002") is not None


@pytest.mark.asyncio
async def test_invalidate_nonexistent(cache: TrustChainCache):
    """Test invalidating a non-existent entry doesn't error."""
    # Should not raise exception
    await cache.invalidate("nonexistent-agent")

    stats = cache.get_stats()
    assert stats.size == 0


@pytest.mark.asyncio
async def test_invalidate_all(cache: TrustChainCache):
    """Test invalidating all cache entries."""
    # Store multiple chains
    for i in range(5):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:03d}",
                agent_id=f"agent-{i:03d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:03d}", chain)

    # Verify all present
    stats = cache.get_stats()
    assert stats.size == 5

    # Invalidate all
    await cache.invalidate_all()

    # Verify all removed
    stats = cache.get_stats()
    assert stats.size == 0

    # Verify lookups fail
    for i in range(5):
        result = await cache.get(f"agent-{i:03d}")
        assert result is None


# Thread Safety Tests


@pytest.mark.asyncio
async def test_concurrent_access(sample_chain: TrustLineageChain):
    """Test thread-safe concurrent access."""
    cache = TrustChainCache(ttl_seconds=300, max_size=100)

    # Store initial chain
    await cache.set("agent-001", sample_chain)

    # Concurrent reads
    async def read_chain():
        for _ in range(10):
            result = await cache.get("agent-001")
            assert result is not None
            await asyncio.sleep(0.001)  # Small delay

    # Run 10 concurrent readers
    tasks = [read_chain() for _ in range(10)]
    await asyncio.gather(*tasks)

    # Verify stats (100 hits from 10 readers x 10 reads each)
    stats = cache.get_stats()
    assert stats.hits == 100


@pytest.mark.asyncio
async def test_concurrent_writes():
    """Test thread-safe concurrent writes."""
    cache = TrustChainCache(ttl_seconds=300, max_size=100)

    # Concurrent writes to different keys
    async def write_chain(agent_id: str):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{agent_id}",
                agent_id=agent_id,
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(agent_id, chain)

    # Write 20 chains concurrently
    tasks = [write_chain(f"agent-{i:03d}") for i in range(20)]
    await asyncio.gather(*tasks)

    # Verify all written
    stats = cache.get_stats()
    assert stats.size == 20


@pytest.mark.asyncio
async def test_concurrent_mixed_operations(sample_chain: TrustLineageChain):
    """Test thread-safe mixed concurrent operations."""
    cache = TrustChainCache(ttl_seconds=300, max_size=50)

    # Mixed operations
    async def reader(agent_id: str):
        for _ in range(5):
            await cache.get(agent_id)
            await asyncio.sleep(0.001)

    async def writer(agent_id: str):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{agent_id}",
                agent_id=agent_id,
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(agent_id, chain)

    # 10 writers, 10 readers
    tasks = []
    for i in range(10):
        tasks.append(writer(f"agent-{i:03d}"))
        tasks.append(reader(f"agent-{i:03d}"))

    await asyncio.gather(*tasks)

    # Should complete without errors
    stats = cache.get_stats()
    assert stats.size == 10


# Property Tests


def test_cache_properties():
    """Test cache property accessors."""
    cache = TrustChainCache(ttl_seconds=123, max_size=456, eviction_policy="lru")

    assert cache.ttl_seconds == 123
    assert cache.max_size == 456
    assert cache.eviction_policy == "lru"


def test_invalid_eviction_policy():
    """Test that invalid eviction policy raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported eviction policy"):
        TrustChainCache(eviction_policy="fifo")


# CacheEntry Tests


def test_cache_entry_expiration(sample_chain: TrustLineageChain):
    """Test CacheEntry expiration checking."""
    # Create entry that expires in 1 second
    entry = CacheEntry(
        chain=sample_chain,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )

    # Should not be expired immediately
    assert not entry.is_expired()

    # Create entry that's already expired
    expired_entry = CacheEntry(
        chain=sample_chain,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    # Should be expired
    assert expired_entry.is_expired()


# Performance Tests


@pytest.mark.asyncio
async def test_cache_performance(sample_chain: TrustLineageChain):
    """Test that cache hits are fast (<1ms)."""
    cache = TrustChainCache(ttl_seconds=300, max_size=1000)

    # Store chain
    await cache.set("agent-001", sample_chain)

    # Measure cache hit time
    import time

    start = time.perf_counter()

    for _ in range(1000):
        result = await cache.get("agent-001")
        assert result is not None

    elapsed = time.perf_counter() - start
    avg_time_ms = (elapsed / 1000) * 1000

    # Average should be well under 1ms
    assert avg_time_ms < 1.0, f"Cache hit too slow: {avg_time_ms:.3f}ms average"


@pytest.mark.asyncio
async def test_cache_scaling():
    """Test cache performance with many entries."""
    cache = TrustChainCache(ttl_seconds=300, max_size=10000)

    # Store 1000 chains
    for i in range(1000):
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id=f"gen-{i:04d}",
                agent_id=f"agent-{i:04d}",
                authority_id="org-acme",
                authority_type=AuthorityType.ORGANIZATION,
                created_at=datetime.now(timezone.utc),
                signature="test-signature",
            ),
        )
        await cache.set(f"agent-{i:04d}", chain)

    # Verify all stored
    stats = cache.get_stats()
    assert stats.size == 1000

    # Test retrieval performance
    import time

    start = time.perf_counter()

    # Random access pattern
    for i in range(0, 1000, 10):
        result = await cache.get(f"agent-{i:04d}")
        assert result is not None

    elapsed = time.perf_counter() - start
    avg_time_ms = (elapsed / 100) * 1000

    # Should still be fast with many entries
    assert avg_time_ms < 1.0, f"Cache scaling issue: {avg_time_ms:.3f}ms average"
