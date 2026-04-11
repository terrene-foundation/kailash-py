"""
Performance benchmarks for EATP Week 11 trust operations.

Measures performance of core trust operations with real infrastructure
(NO MOCKING) using in-memory stores for isolation.

Performance targets (p95):
- ESTABLISH: <100ms
- DELEGATE: <50ms
- VERIFY QUICK: <5ms (cache hit)
- VERIFY STANDARD: <50ms (full chain validation)
- VERIFY FULL: <100ms (cryptographic verification)
- AUDIT: <20ms

Usage:
    pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-only
    pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-json=benchmark_results.json

Requirements:
    - pytest-benchmark: pip install pytest-benchmark
    - NO MOCKING: Uses real TrustOperations with in-memory stores
"""

import asyncio
import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from kailash.trust.cache import TrustChainCache
from kailash.trust.chain import (
    ActionResult,
    CapabilityType,
    TrustLineageChain,
    VerificationLevel,
)
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.signing.crypto import generate_keypair

from kaizen.trust.authority import (
    AuthorityPermission,
    AuthorityType,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)

# ============================================================================
# In-Memory Trust Store (NO MOCKING - Real implementation for benchmarks)
# ============================================================================


class InMemoryTrustStore:
    """
    In-memory implementation of trust store for benchmarks.

    This is NOT a mock - it's a real implementation using in-memory
    storage for isolated benchmarking without PostgreSQL overhead.
    """

    def __init__(self):
        """Initialize in-memory trust store."""
        self._chains: Dict[str, TrustLineageChain] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store."""
        self._initialized = True

    async def store_chain(
        self,
        chain: TrustLineageChain,
        expires_at: datetime = None,
    ) -> str:
        """Store a trust chain."""
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain
        return agent_id

    async def get_chain(
        self,
        agent_id: str,
        include_inactive: bool = False,
    ) -> TrustLineageChain:
        """Retrieve a trust chain."""
        if agent_id not in self._chains:
            raise TrustChainNotFoundError(agent_id)
        return self._chains[agent_id]

    async def update_chain(self, chain: TrustLineageChain) -> None:
        """Update an existing trust chain."""
        agent_id = chain.genesis.agent_id
        if agent_id not in self._chains:
            raise TrustChainNotFoundError(agent_id)
        self._chains[agent_id] = chain

    async def delete_chain(self, agent_id: str, soft_delete: bool = True) -> None:
        """Delete a trust chain."""
        if agent_id not in self._chains:
            raise TrustChainNotFoundError(agent_id)
        del self._chains[agent_id]

    async def list_chains(
        self,
        authority_id: str = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TrustLineageChain]:
        """List trust chains."""
        chains = list(self._chains.values())
        if authority_id:
            chains = [c for c in chains if c.genesis.authority_id == authority_id]
        return chains[offset : offset + limit]


class InMemoryAuthorityRegistry:
    """
    In-memory implementation of authority registry for benchmarks.

    This is NOT a mock - it's a real implementation using in-memory
    storage for isolated benchmarking.
    """

    def __init__(self):
        """Initialize in-memory authority registry."""
        self._authorities: Dict[str, OrganizationalAuthority] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the registry."""
        self._initialized = True

    async def register_authority(self, authority: OrganizationalAuthority) -> str:
        """Register an authority."""
        self._authorities[authority.id] = authority
        return authority.id

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """Retrieve an authority."""
        from kailash.trust.exceptions import AuthorityNotFoundError

        if authority_id not in self._authorities:
            raise AuthorityNotFoundError(authority_id)
        return self._authorities[authority_id]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def key_manager():
    """Create a TrustKeyManager with test keys."""
    manager = TrustKeyManager()

    # Generate test key for authority
    private_key, public_key = generate_keypair()
    manager.register_key("test-signing-key", private_key)

    yield manager


@pytest.fixture
async def authority_registry(key_manager):
    """Create an in-memory authority registry with test authority."""
    registry = InMemoryAuthorityRegistry()
    await registry.initialize()

    # Create test authority
    private_key, public_key = generate_keypair()
    key_manager.register_key("test-authority-key", private_key)

    authority = OrganizationalAuthority(
        id="org-test",
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="test-authority-key",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )

    await registry.register_authority(authority)

    yield registry


@pytest.fixture
async def trust_store():
    """Create an in-memory trust store."""
    store = InMemoryTrustStore()
    await store.initialize()
    yield store


@pytest.fixture
async def trust_ops(authority_registry, key_manager, trust_store):
    """Create TrustOperations with in-memory stores."""
    ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await ops.initialize()
    yield ops


@pytest.fixture
async def trust_cache():
    """Create a TrustChainCache for cache performance testing."""
    cache = TrustChainCache(ttl_seconds=300, max_size=10000)
    yield cache


@pytest.fixture
async def established_agent(trust_ops):
    """Create an established agent for verification benchmarks."""
    chain = await trust_ops.establish(
        agent_id="benchmark-agent-001",
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(
                capability="read_data",
                capability_type=CapabilityType.ACCESS,
                constraints=["business_hours_only"],
            ),
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
                constraints=["read_only"],
            ),
        ],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    yield chain


# ============================================================================
# Benchmark: ESTABLISH Operation
# Target: <100ms p95
# ============================================================================


@pytest.mark.benchmark(group="establish")
def test_benchmark_establish_operation(benchmark, trust_ops):
    """
    Benchmark ESTABLISH operation.

    Measures time to:
    1. Generate keys
    2. Sign genesis record
    3. Create capability attestations
    4. Compute constraint envelope
    5. Store chain

    Target: <100ms p95
    """

    async def establish_agent():
        """Establish a new agent."""
        return await trust_ops.establish(
            agent_id=f"agent-{datetime.now(timezone.utc).timestamp()}",
            authority_id="org-test",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                    constraints=["business_hours_only"],
                ),
                CapabilityRequest(
                    capability="write_data",
                    capability_type=CapabilityType.ACTION,
                    constraints=["audit_required"],
                ),
            ],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(establish_agent()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]  # 95th percentile
    assert p95 < 0.100, f"ESTABLISH p95 ({p95:.3f}s) exceeds 100ms target"


@pytest.mark.benchmark(group="establish")
def test_benchmark_establish_multiple_capabilities(benchmark, trust_ops):
    """
    Benchmark ESTABLISH with 10 capabilities.

    Tests scaling of capability attestation creation and signing.
    """

    async def establish_with_many_caps():
        """Establish agent with multiple capabilities."""
        capabilities = [
            CapabilityRequest(
                capability=f"capability_{i}",
                capability_type=CapabilityType.ACCESS,
                constraints=["read_only", "business_hours_only"],
            )
            for i in range(10)
        ]

        return await trust_ops.establish(
            agent_id=f"agent-multi-{datetime.now(timezone.utc).timestamp()}",
            authority_id="org-test",
            capabilities=capabilities,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(establish_with_many_caps()))


# ============================================================================
# Benchmark: DELEGATE Operation
# Target: <50ms p95
# ============================================================================


@pytest.mark.benchmark(group="delegate")
def test_benchmark_delegate_operation(benchmark, trust_ops, established_agent):
    """
    Benchmark DELEGATE operation.

    Measures time to:
    1. Validate delegator chain
    2. Check capabilities
    3. Create delegation record
    4. Sign delegation
    5. Create/update delegatee chain

    Target: <50ms p95
    """

    async def delegate_trust():
        """Delegate trust to another agent."""
        return await trust_ops.delegate(
            delegator_id="benchmark-agent-001",
            delegatee_id=f"delegatee-{datetime.now(timezone.utc).timestamp()}",
            task_id=f"task-{datetime.now(timezone.utc).timestamp()}",
            capabilities=["read_data"],
            additional_constraints=["no_pii_export"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(delegate_trust()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]
    assert p95 < 0.050, f"DELEGATE p95 ({p95:.3f}s) exceeds 50ms target"


# ============================================================================
# Benchmark: VERIFY Operations
# ============================================================================


@pytest.mark.benchmark(group="verify")
def test_benchmark_verify_quick(benchmark, trust_ops, established_agent):
    """
    Benchmark VERIFY QUICK operation.

    Only checks expiration - fastest verification level.

    Target: <5ms p95
    """

    async def verify_quick():
        """Perform quick verification."""
        return await trust_ops.verify(
            agent_id="benchmark-agent-001",
            action="read_data",
            level=VerificationLevel.QUICK,
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(verify_quick()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]
    assert p95 < 0.005, f"VERIFY QUICK p95 ({p95:.3f}s) exceeds 5ms target"


@pytest.mark.benchmark(group="verify")
def test_benchmark_verify_standard(benchmark, trust_ops, established_agent):
    """
    Benchmark VERIFY STANDARD operation.

    Includes capability matching and constraint evaluation.

    Target: <50ms p95
    """

    async def verify_standard():
        """Perform standard verification."""
        return await trust_ops.verify(
            agent_id="benchmark-agent-001",
            action="read_data",
            level=VerificationLevel.STANDARD,
            context={"current_time": datetime.now(timezone.utc)},
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(verify_standard()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]
    assert p95 < 0.050, f"VERIFY STANDARD p95 ({p95:.3f}s) exceeds 50ms target"


@pytest.mark.benchmark(group="verify")
def test_benchmark_verify_full(benchmark, trust_ops, established_agent):
    """
    Benchmark VERIFY FULL operation.

    Includes cryptographic signature verification of all signatures.

    Target: <100ms p95
    """

    async def verify_full():
        """Perform full verification with signature checks."""
        return await trust_ops.verify(
            agent_id="benchmark-agent-001",
            action="read_data",
            level=VerificationLevel.FULL,
            context={"current_time": datetime.now(timezone.utc)},
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(verify_full()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]
    assert p95 < 0.100, f"VERIFY FULL p95 ({p95:.3f}s) exceeds 100ms target"


# ============================================================================
# Benchmark: AUDIT Operation
# Target: <20ms p95
# ============================================================================


@pytest.mark.benchmark(group="audit")
def test_benchmark_audit_operation(benchmark, trust_ops, established_agent):
    """
    Benchmark AUDIT operation.

    Measures time to:
    1. Get trust chain
    2. Compute chain hash
    3. Create audit anchor
    4. Sign audit anchor

    Target: <20ms p95
    """

    async def audit_action():
        """Record an audit anchor."""
        return await trust_ops.audit(
            agent_id="benchmark-agent-001",
            action="read_data",
            resource="database.users",
            result=ActionResult.SUCCESS,
            context={"rows_read": 100, "duration_ms": 45},
        )

    # Run benchmark
    result = benchmark(lambda: asyncio.run(audit_action()))

    # Assert performance target
    stats = result.stats.stats
    p95 = statistics.quantiles(stats, n=20)[18]
    assert p95 < 0.020, f"AUDIT p95 ({p95:.3f}s) exceeds 20ms target"


# ============================================================================
# Benchmark: Cache Performance
# ============================================================================


@pytest.mark.benchmark(group="cache")
def test_benchmark_cache_hit(benchmark, trust_cache, established_agent):
    """
    Benchmark cache hit performance.

    Measures time for cache.get() with warm cache.

    Target: <1ms (100x faster than database)
    """

    async def cache_hit_test():
        """Test cache hit performance."""
        # Warm the cache
        await trust_cache.set("benchmark-agent-001", established_agent)

        # Measure cache hit
        return await trust_cache.get("benchmark-agent-001")

    # Run benchmark
    result = benchmark(lambda: asyncio.run(cache_hit_test()))

    # Assert performance target
    stats = result.stats.stats
    mean = statistics.mean(stats)
    assert mean < 0.001, f"Cache hit mean ({mean:.6f}s) exceeds 1ms target"


@pytest.mark.benchmark(group="cache")
def test_benchmark_cache_miss(benchmark, trust_cache):
    """
    Benchmark cache miss performance.

    Measures time for cache.get() with cold cache (should be very fast).
    """

    async def cache_miss_test():
        """Test cache miss performance."""
        return await trust_cache.get("nonexistent-agent")

    # Run benchmark
    result = benchmark(lambda: asyncio.run(cache_miss_test()))


@pytest.mark.benchmark(group="cache")
def test_benchmark_cache_set(benchmark, trust_cache, established_agent):
    """
    Benchmark cache.set() performance.

    Measures time to store an entry in cache.
    """

    async def cache_set_test():
        """Test cache set performance."""
        agent_id = f"agent-{datetime.now(timezone.utc).timestamp()}"
        await trust_cache.set(agent_id, established_agent)

    # Run benchmark
    result = benchmark(lambda: asyncio.run(cache_set_test()))


# ============================================================================
# Benchmark: Cache Hit Rate Under Load
# ============================================================================


@pytest.mark.benchmark(group="cache")
def test_benchmark_cache_hit_rate_under_load(benchmark, trust_cache, established_agent):
    """
    Benchmark cache hit rate with realistic access patterns.

    Simulates 1000 operations with 90% cache hit rate (Zipf distribution).
    """

    async def simulate_cache_load():
        """Simulate realistic cache access pattern."""
        import random

        # Pre-populate cache with 100 agents
        agents = []
        for i in range(100):
            agent_id = f"agent-{i:03d}"
            agents.append(agent_id)
            await trust_cache.set(agent_id, established_agent)

        # Simulate access pattern (Zipf: 20% of agents get 80% of accesses)
        hits = 0
        misses = 0

        for _ in range(1000):
            # 90% chance to access popular agent (cache hit)
            if random.random() < 0.9:
                agent_id = random.choice(agents[:20])  # Top 20% popular
            else:
                agent_id = f"agent-new-{random.randint(1000, 9999)}"

            result = await trust_cache.get(agent_id)
            if result is not None:
                hits += 1
            else:
                misses += 1

        # Get cache stats
        stats = trust_cache.get_stats()

        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / (hits + misses),
            "cache_stats": stats,
        }

    # Run benchmark
    result = benchmark(lambda: asyncio.run(simulate_cache_load()))

    # Check hit rate
    load_result = asyncio.run(simulate_cache_load())
    assert (
        load_result["hit_rate"] > 0.85
    ), f"Cache hit rate ({load_result['hit_rate']:.2%}) below 85% target"


# ============================================================================
# Benchmark: Memory Usage
# ============================================================================


@pytest.mark.benchmark(group="memory")
def test_benchmark_cache_memory_usage(benchmark, trust_cache, established_agent):
    """
    Benchmark cache memory usage with 10,000 entries.

    Ensures cache stays within reasonable memory bounds.
    """

    async def populate_cache():
        """Populate cache with 10,000 entries."""
        for i in range(10000):
            agent_id = f"agent-{i:05d}"
            await trust_cache.set(agent_id, established_agent)

        stats = trust_cache.get_stats()
        return stats

    # Run benchmark
    result = benchmark(lambda: asyncio.run(populate_cache()))

    # Verify size
    stats = asyncio.run(populate_cache())
    assert stats.size == 10000, f"Cache size {stats.size} != 10000"


# ============================================================================
# Benchmark Summary Report
# ============================================================================


def generate_benchmark_report(benchmark_results: Dict[str, Any]) -> str:
    """
    Generate a markdown summary report from benchmark results.

    Args:
        benchmark_results: Dictionary with benchmark data

    Returns:
        Markdown-formatted report
    """
    report = """# EATP Trust Operations Performance Benchmark Report

## Executive Summary

This report presents performance benchmarks for EATP (Enterprise Agent Trust Protocol)
core operations using real infrastructure (NO MOCKING).

## Test Environment

- **Runtime**: AsyncLocalRuntime with in-memory stores
- **Isolation**: InMemoryTrustStore and InMemoryAuthorityRegistry
- **Iterations**: 100+ per operation for p95 calculation
- **Policy**: NO MOCKING - All operations use real implementations

## Performance Results

### ESTABLISH Operation
**Target**: <100ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {establish_mean:.3f}ms | {establish_status} |
| Median | {establish_median:.3f}ms | - |
| p95 | {establish_p95:.3f}ms | {establish_p95_status} |
| Max | {establish_max:.3f}ms | - |

### DELEGATE Operation
**Target**: <50ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {delegate_mean:.3f}ms | {delegate_status} |
| p95 | {delegate_p95:.3f}ms | {delegate_p95_status} |

### VERIFY Operations

#### VERIFY QUICK
**Target**: <5ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {verify_quick_mean:.3f}ms | {verify_quick_status} |
| p95 | {verify_quick_p95:.3f}ms | {verify_quick_p95_status} |

#### VERIFY STANDARD
**Target**: <50ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {verify_std_mean:.3f}ms | {verify_std_status} |
| p95 | {verify_std_p95:.3f}ms | {verify_std_p95_status} |

#### VERIFY FULL
**Target**: <100ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {verify_full_mean:.3f}ms | {verify_full_status} |
| p95 | {verify_full_p95:.3f}ms | {verify_full_p95_status} |

### AUDIT Operation
**Target**: <20ms p95

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {audit_mean:.3f}ms | {audit_status} |
| p95 | {audit_p95:.3f}ms | {audit_p95_status} |

### Cache Performance

#### Cache Hit
**Target**: <1ms mean

| Metric | Value | Status |
|--------|-------|--------|
| Mean | {cache_hit_mean:.6f}ms | {cache_hit_status} |

#### Cache Hit Rate
**Target**: >85% under load

| Metric | Value | Status |
|--------|-------|--------|
| Hit Rate | {cache_hit_rate:.2%} | {cache_hit_rate_status} |

## Conclusions

{conclusions}

## Recommendations

{recommendations}
"""

    # This is a template - actual values would be filled in from benchmark results
    return report


if __name__ == "__main__":
    print(
        "Run benchmarks with: pytest tests/benchmarks/trust/benchmark_trust_operations.py -v --benchmark-only"
    )
    print(
        "Generate JSON report: pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json"
    )
