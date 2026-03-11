"""
Cache Performance Example.

Demonstrates EATP trust chain caching:
1. LRU cache with configurable size
2. TTL-based expiration
3. Cache invalidation strategies
4. Performance comparison (cache vs database)

Caching provides 100x+ speedup for trust verification.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Tuple

from kaizen.trust import (  # Core operations; Cache; Storage; Authority; Crypto
    AuthorityPermission,
    AuthorityType,
    CacheStats,
    CapabilityRequest,
    CapabilityType,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    PostgresTrustStore,
    TrustChainCache,
    TrustKeyManager,
    TrustOperations,
    VerificationLevel,
    generate_keypair,
)


async def benchmark_verification(
    trust_ops: TrustOperations,
    agent_ids: List[str],
    iterations: int,
    use_cache: bool,
) -> Tuple[float, float, float]:
    """Benchmark verification with/without cache."""
    latencies = []

    for _ in range(iterations):
        for agent_id in agent_ids:
            start = time.perf_counter()
            await trust_ops.verify(
                agent_id=agent_id,
                level=VerificationLevel.QUICK,
            )
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

    latencies.sort()
    return (
        latencies[len(latencies) // 2],  # p50
        latencies[int(len(latencies) * 0.95)],  # p95
        sum(latencies) / len(latencies),  # avg
    )


async def main():
    """Demonstrate cache performance benefits."""
    print("=" * 70)
    print("EATP Trust Chain Cache Performance Example")
    print("=" * 70)

    # =========================================================================
    # Setup
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    database_url = "postgresql://localhost:5432/kaizen_trust"

    # Create cache with specific configuration
    cache = TrustChainCache(
        max_size=1000,  # Maximum entries
        ttl_seconds=300,  # 5 minute TTL
    )

    # Create trust store WITH caching enabled
    trust_store_cached = PostgresTrustStore(
        database_url=database_url,
        enable_cache=True,
        cache_ttl_seconds=300,
    )

    # Create trust store WITHOUT caching (for comparison)
    trust_store_uncached = PostgresTrustStore(
        database_url=database_url,
        enable_cache=False,
    )

    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    # Setup authority
    private_key, public_key = generate_keypair()
    authority_id = "org-cache-demo"
    key_manager.register_key(f"key-{authority_id}", private_key)

    await authority_registry.initialize()
    await trust_store_cached.initialize()
    await trust_store_uncached.initialize()

    try:
        await authority_registry.register_authority(
            OrganizationalAuthority(
                id=authority_id,
                name="Cache Demo Org",
                authority_type=AuthorityType.ORGANIZATION,
                public_key=public_key,
                signing_key_id=f"key-{authority_id}",
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.GRANT_CAPABILITIES,
                ],
                is_active=True,
            )
        )
    except Exception:
        pass

    # Create TrustOperations with cache
    trust_ops_cached = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store_cached,
    )
    await trust_ops_cached.initialize()

    # Create TrustOperations without cache
    trust_ops_uncached = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store_uncached,
    )
    await trust_ops_uncached.initialize()

    print("   - Infrastructure ready")
    print("   - Cache max size: 1000 entries")
    print("   - Cache TTL: 300 seconds")

    # =========================================================================
    # Create Test Agents
    # =========================================================================
    print("\n2. Creating test agents...")

    num_agents = 10
    agent_ids = []

    for i in range(num_agents):
        agent_id = f"agent-cache-test-{i:03d}"
        agent_ids.append(agent_id)

        try:
            await trust_ops_cached.establish(
                agent_id=agent_id,
                authority_id=authority_id,
                capabilities=[
                    CapabilityRequest(
                        capability="test_action",
                        capability_type=CapabilityType.ACTION,
                    ),
                ],
            )
        except Exception:
            pass  # Agent may already exist

    print(f"   - Created {num_agents} test agents")

    # =========================================================================
    # Cache Demonstration
    # =========================================================================
    print("\n3. Cache operation demonstration...")
    print("-" * 70)

    test_agent = agent_ids[0]

    # First access (cache miss)
    print(f"\n   First access to {test_agent} (cache miss):")
    start = time.perf_counter()
    result1 = await trust_ops_cached.verify(
        agent_id=test_agent, level=VerificationLevel.QUICK
    )
    first_access_ms = (time.perf_counter() - start) * 1000
    print(f"   - Latency: {first_access_ms:.3f}ms")
    print(f"   - Valid: {result1.valid}")

    # Second access (cache hit)
    print(f"\n   Second access to {test_agent} (cache hit):")
    start = time.perf_counter()
    result2 = await trust_ops_cached.verify(
        agent_id=test_agent, level=VerificationLevel.QUICK
    )
    second_access_ms = (time.perf_counter() - start) * 1000
    print(f"   - Latency: {second_access_ms:.3f}ms")
    print(f"   - Speedup: {first_access_ms/second_access_ms:.1f}x")

    # =========================================================================
    # Performance Benchmark
    # =========================================================================
    print("\n4. Performance benchmark...")
    print("-" * 70)

    iterations = 50

    # Warm up cache
    for agent_id in agent_ids:
        await trust_ops_cached.verify(agent_id=agent_id, level=VerificationLevel.QUICK)

    # Benchmark cached
    print(f"\n   Benchmarking WITH cache ({iterations * num_agents} verifications)...")
    cached_p50, cached_p95, cached_avg = await benchmark_verification(
        trust_ops_cached, agent_ids, iterations, use_cache=True
    )

    # Benchmark uncached (limited iterations due to database load)
    print(f"   Benchmarking WITHOUT cache ({5 * num_agents} verifications)...")
    uncached_p50, uncached_p95, uncached_avg = await benchmark_verification(
        trust_ops_uncached, agent_ids, 5, use_cache=False
    )

    print("\n   Results:")
    print(f"   {'Metric':<20} {'Cached':<15} {'Uncached':<15} {'Speedup':<10}")
    print(f"   {'-'*60}")
    print(
        f"   {'p50 (ms)':<20} {cached_p50:.3f}           {uncached_p50:.3f}           {uncached_p50/cached_p50:.1f}x"
    )
    print(
        f"   {'p95 (ms)':<20} {cached_p95:.3f}           {uncached_p95:.3f}           {uncached_p95/cached_p95:.1f}x"
    )
    print(
        f"   {'Average (ms)':<20} {cached_avg:.3f}           {uncached_avg:.3f}           {uncached_avg/cached_avg:.1f}x"
    )

    # =========================================================================
    # Cache Statistics
    # =========================================================================
    print("\n5. Cache statistics...")
    print("-" * 70)

    stats = trust_store_cached.get_cache_stats()
    print("\n   Cache Stats:")
    print(f"   - Size: {stats.size} entries")
    print(f"   - Hits: {stats.hits}")
    print(f"   - Misses: {stats.misses}")
    print(f"   - Hit Rate: {stats.hit_rate:.1%}")
    print(f"   - Evictions: {stats.evictions}")

    # =========================================================================
    # Cache Invalidation
    # =========================================================================
    print("\n6. Cache invalidation strategies...")
    print("-" * 70)

    print("\n   Strategy 1: Invalidate single agent")
    trust_store_cached.invalidate_cache(agent_ids[0])
    print(f"   - Invalidated: {agent_ids[0]}")

    print("\n   Strategy 2: Invalidate all")
    trust_store_cached.invalidate_all_cache()
    print("   - All cache entries cleared")

    # Check stats after invalidation
    stats = trust_store_cached.get_cache_stats()
    print("\n   After invalidation:")
    print(f"   - Size: {stats.size} entries")

    # =========================================================================
    # TTL Demonstration
    # =========================================================================
    print("\n7. TTL (Time-To-Live) demonstration...")
    print("-" * 70)

    # Create a short-TTL cache for demo
    short_ttl_cache = TrustChainCache(max_size=100, ttl_seconds=2)

    print("   - TTL set to 2 seconds")
    print("   - Adding entry to cache...")

    # Manually add to cache for demo
    chain = await trust_store_cached.get_chain(agent_ids[0])
    short_ttl_cache.set(agent_ids[0], chain)

    # Immediate access
    cached_chain = short_ttl_cache.get(agent_ids[0])
    print(f"   - Immediate access: {'Hit' if cached_chain else 'Miss'}")

    # Wait for TTL
    print("   - Waiting 3 seconds for TTL expiration...")
    await asyncio.sleep(3)

    # Access after TTL
    cached_chain = short_ttl_cache.get(agent_ids[0])
    print(f"   - After TTL: {'Hit' if cached_chain else 'Miss (expired)'}")

    # =========================================================================
    # LRU Eviction
    # =========================================================================
    print("\n8. LRU eviction demonstration...")
    print("-" * 70)

    # Create small cache
    small_cache = TrustChainCache(max_size=3, ttl_seconds=300)
    print("   - Cache max size: 3 entries")

    # Add 4 entries
    for i in range(4):
        agent_id = agent_ids[i]
        chain = await trust_store_cached.get_chain(agent_id)
        small_cache.set(agent_id, chain)
        print(f"   - Added {agent_id}, cache size: {small_cache.get_stats().size}")

    print("\n   First entry (LRU) should be evicted:")
    first_entry = small_cache.get(agent_ids[0])
    print(f"   - {agent_ids[0]}: {'Present' if first_entry else 'Evicted'}")

    last_entry = small_cache.get(agent_ids[3])
    print(f"   - {agent_ids[3]}: {'Present' if last_entry else 'Missing'}")

    # =========================================================================
    # Best Practices
    # =========================================================================
    print("\n9. Cache configuration best practices...")
    print("-" * 70)
    print(
        """
    Cache Size:
    - Set based on expected concurrent agents
    - Rule of thumb: 2x expected concurrent agents
    - Monitor eviction rate and adjust

    TTL (Time-To-Live):
    - Production: 300-600 seconds (5-10 minutes)
    - High-security: 60-120 seconds (1-2 minutes)
    - Low-change environments: 900-1800 seconds (15-30 minutes)

    Invalidation:
    - Invalidate on trust chain updates
    - Invalidate on delegation changes
    - Invalidate on authority changes
    - Consider broadcast invalidation for distributed caches

    Monitoring:
    - Track hit rate (target: >90%)
    - Monitor eviction rate
    - Alert on sustained cache misses
    """
    )

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n10. Cleaning up...")
    await trust_store_cached.close()
    await trust_store_uncached.close()
    await authority_registry.close()

    print("\n" + "=" * 70)
    print("Cache Performance Example Complete!")
    print("=" * 70)
    print("\nKey Results:")
    print(f"- Cache speedup: {uncached_avg/cached_avg:.0f}x faster")
    print(f"- Target latency (<1ms): {'Met' if cached_p95 < 1 else 'Not met'}")


if __name__ == "__main__":
    asyncio.run(main())
