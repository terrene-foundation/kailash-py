"""
Trust Verification Levels Example.

Demonstrates the three EATP verification levels:
- QUICK: Hash + expiration only (~1ms) - For high-frequency operations
- STANDARD: + Capability match + constraints (~5ms) - For most operations
- FULL: + Cryptographic signatures (~50ms) - For sensitive operations

Choose the right level based on your performance vs security tradeoff.
"""

import asyncio
import time
from datetime import datetime, timedelta

from kaizen.trust import (  # Core operations; Storage; Authority; Crypto
    AuthorityPermission,
    AuthorityType,
    CapabilityRequest,
    CapabilityType,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    PostgresTrustStore,
    TrustKeyManager,
    TrustOperations,
    VerificationLevel,
    generate_keypair,
)


async def benchmark_verification(
    trust_ops: TrustOperations,
    agent_id: str,
    level: VerificationLevel,
    action: str | None,
    iterations: int = 100,
) -> dict:
    """Benchmark verification at a specific level."""
    latencies = []

    for _ in range(iterations):
        start = time.perf_counter()
        result = await trust_ops.verify(
            agent_id=agent_id,
            action=action,
            level=level,
        )
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # Convert to ms

    latencies.sort()
    return {
        "level": level.value,
        "valid": result.valid,
        "iterations": iterations,
        "p50_ms": latencies[len(latencies) // 2],
        "p95_ms": latencies[int(len(latencies) * 0.95)],
        "p99_ms": latencies[int(len(latencies) * 0.99)],
        "min_ms": min(latencies),
        "max_ms": max(latencies),
    }


async def main():
    """Demonstrate trust verification levels."""
    print("=" * 70)
    print("EATP Trust Verification Levels Example")
    print("=" * 70)

    # =========================================================================
    # Setup
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    database_url = "postgresql://localhost:5432/kaizen_trust"

    trust_store = PostgresTrustStore(
        database_url=database_url,
        enable_cache=True,  # Enable caching for QUICK verification
        cache_ttl_seconds=300,
    )
    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    # Setup authority
    private_key, public_key = generate_keypair()
    authority_id = "org-verification-demo"
    key_manager.register_key(f"key-{authority_id}", private_key)

    await authority_registry.initialize()
    await trust_store.initialize()

    try:
        await authority_registry.register_authority(
            OrganizationalAuthority(
                id=authority_id,
                name="Verification Demo Org",
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

    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    # Establish agent
    agent_id = "agent-verification-demo"
    try:
        await trust_ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
                CapabilityRequest(
                    capability="write_data",
                    capability_type=CapabilityType.ACTION,
                ),
                CapabilityRequest(
                    capability="admin_action",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )
    except Exception:
        pass

    print("   - Infrastructure ready")
    print(f"   - Agent established: {agent_id}")

    # =========================================================================
    # Explain Verification Levels
    # =========================================================================
    print("\n2. Verification Levels Explained:")
    print("-" * 70)
    print(
        """
    QUICK (<5ms target):
    - Verifies chain hash integrity
    - Checks expiration timestamps
    - Ideal for: High-frequency, low-risk operations
    - Use when: Reading cached data, simple queries

    STANDARD (<50ms target):
    - Everything in QUICK, plus:
    - Verifies capability exists for action
    - Evaluates constraint satisfaction
    - Ideal for: Most production operations
    - Use when: API calls, data processing, tool invocations

    FULL (<100ms target):
    - Everything in STANDARD, plus:
    - Cryptographically verifies all signatures
    - Validates complete chain integrity
    - Ideal for: Sensitive or high-value operations
    - Use when: Financial transactions, admin actions, deletions
    """
    )

    # =========================================================================
    # Demonstrate Each Level
    # =========================================================================
    print("\n3. Demonstrating verification levels...")
    print("-" * 70)

    # QUICK verification
    print("\n   QUICK Verification:")
    result = await trust_ops.verify(
        agent_id=agent_id,
        level=VerificationLevel.QUICK,
    )
    print(f"   - Valid: {result.valid}")
    print(f"   - Level: {result.level.value}")
    print(f"   - Latency: {result.latency_ms:.3f}ms")
    print("   - What was checked: Hash integrity, expiration")

    # STANDARD verification
    print("\n   STANDARD Verification (with action check):")
    result = await trust_ops.verify(
        agent_id=agent_id,
        action="read_data",
        level=VerificationLevel.STANDARD,
    )
    print(f"   - Valid: {result.valid}")
    print(f"   - Level: {result.level.value}")
    print("   - Action: read_data")
    print(f"   - Latency: {result.latency_ms:.3f}ms")
    print("   - What was checked: Hash, expiration, capability match, constraints")

    # FULL verification
    print("\n   FULL Verification (with signature check):")
    result = await trust_ops.verify(
        agent_id=agent_id,
        action="admin_action",
        level=VerificationLevel.FULL,
    )
    print(f"   - Valid: {result.valid}")
    print(f"   - Level: {result.level.value}")
    print("   - Action: admin_action (sensitive)")
    print(f"   - Latency: {result.latency_ms:.3f}ms")
    print(
        "   - What was checked: Hash, expiration, capabilities, constraints, signatures"
    )

    # =========================================================================
    # Performance Benchmarks
    # =========================================================================
    print("\n4. Performance Benchmarks (100 iterations each)...")
    print("-" * 70)

    iterations = 100

    # Benchmark QUICK
    quick_stats = await benchmark_verification(
        trust_ops, agent_id, VerificationLevel.QUICK, None, iterations
    )

    # Benchmark STANDARD
    standard_stats = await benchmark_verification(
        trust_ops, agent_id, VerificationLevel.STANDARD, "read_data", iterations
    )

    # Benchmark FULL
    full_stats = await benchmark_verification(
        trust_ops, agent_id, VerificationLevel.FULL, "admin_action", iterations
    )

    print("\n   Results:")
    print(f"   {'Level':<12} {'p50':<12} {'p95':<12} {'p99':<12} {'Target':<12}")
    print(f"   {'-'*60}")
    print(
        f"   {'QUICK':<12} {quick_stats['p50_ms']:.3f}ms     {quick_stats['p95_ms']:.3f}ms     {quick_stats['p99_ms']:.3f}ms     <5ms"
    )
    print(
        f"   {'STANDARD':<12} {standard_stats['p50_ms']:.3f}ms     {standard_stats['p95_ms']:.3f}ms     {standard_stats['p99_ms']:.3f}ms     <50ms"
    )
    print(
        f"   {'FULL':<12} {full_stats['p50_ms']:.3f}ms     {full_stats['p95_ms']:.3f}ms     {full_stats['p99_ms']:.3f}ms     <100ms"
    )

    # =========================================================================
    # When to Use Each Level
    # =========================================================================
    print("\n5. Recommended Usage Patterns:")
    print("-" * 70)
    print(
        """
    QUICK - Use for:
    - Cache reads
    - Lightweight health checks
    - Internal service communication
    - Pre-filtering before heavier checks

    STANDARD - Use for:
    - API request handling
    - Data processing tasks
    - Tool invocations
    - Most business logic operations

    FULL - Use for:
    - Financial transactions
    - User data modifications
    - System configuration changes
    - Admin/privileged operations
    - Cross-organization delegations
    - Audit-critical operations
    """
    )

    # =========================================================================
    # Code Examples
    # =========================================================================
    print("\n6. Code Examples:")
    print("-" * 70)
    print(
        """
    # High-frequency read (QUICK)
    if (await trust_ops.verify(agent_id, level=VerificationLevel.QUICK)).valid:
        data = cache.get(key)

    # Standard API operation (STANDARD)
    result = await trust_ops.verify(
        agent_id=agent_id,
        action="process_order",
        level=VerificationLevel.STANDARD,
    )
    if result.valid:
        process_order(order)

    # Sensitive operation (FULL)
    result = await trust_ops.verify(
        agent_id=agent_id,
        action="delete_user_data",
        level=VerificationLevel.FULL,
    )
    if result.valid:
        await delete_user_data(user_id)
    else:
        raise PermissionDeniedError(result.errors)
    """
    )

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n7. Cleaning up...")
    await trust_store.close()
    await authority_registry.close()

    print("\n" + "=" * 70)
    print("Verification Levels Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
