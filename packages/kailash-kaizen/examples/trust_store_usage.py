"""
PostgresTrustStore Usage Examples.

This file demonstrates common usage patterns for the PostgresTrustStore,
including:
1. Basic CRUD operations
2. Caching patterns for performance
3. Filtering and pagination
4. Soft delete workflows
5. Integrity verification

Run with:
    python -m examples.trust_store_usage
"""

import asyncio
import os
from datetime import datetime, timedelta

from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.store import PostgresTrustStore


async def example_1_basic_crud():
    """Example 1: Basic CRUD operations."""
    print("\n=== Example 1: Basic CRUD Operations ===\n")

    # Initialize store
    store = PostgresTrustStore(
        database_url=os.getenv("POSTGRES_URL"),
        enable_cache=True,
    )
    await store.initialize()

    # Create a trust chain
    genesis = GenesisRecord(
        id="genesis-demo-001",
        agent_id="demo-agent-001",
        authority_id="org-demo",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        signature="demo-signature",
    )

    capability = CapabilityAttestation(
        id="cap-demo-001",
        capability="read:customer_data",
        capability_type=CapabilityType.ACCESS,
        constraints=["region:us-west"],
        attester_id="org-demo",
        attested_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=90),
        signature="cap-signature",
    )

    chain = TrustLineageChain(
        genesis=genesis,
        capabilities=[capability],
    )

    # Store the chain
    print("Storing trust chain...")
    agent_id = await store.store_chain(chain)
    print(f"✓ Stored chain for agent: {agent_id}")

    # Retrieve the chain
    print("\nRetrieving trust chain...")
    retrieved_chain = await store.get_chain(agent_id)
    print(f"✓ Retrieved chain for agent: {retrieved_chain.genesis.agent_id}")
    print(f"  - Authority: {retrieved_chain.genesis.authority_id}")
    print(f"  - Capabilities: {len(retrieved_chain.capabilities)}")

    # Update the chain
    print("\nUpdating trust chain...")
    retrieved_chain.capabilities.append(
        CapabilityAttestation(
            id="cap-demo-002",
            capability="write:customer_data",
            capability_type=CapabilityType.ACTION,
            constraints=["region:us-west", "role:admin"],
            attester_id="org-demo",
            attested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=90),
            signature="cap-signature-2",
        )
    )
    await store.update_chain(agent_id, retrieved_chain)
    print("✓ Updated chain with new capability")

    # Verify the update
    updated_chain = await store.get_chain(agent_id)
    print(f"  - Capabilities now: {len(updated_chain.capabilities)}")

    # Clean up
    await store.close()


async def example_2_cache_performance():
    """Example 2: Caching for high performance."""
    print("\n=== Example 2: Cache Performance ===\n")

    import time

    # Initialize store with caching
    store = PostgresTrustStore(
        database_url=os.getenv("POSTGRES_URL"),
        enable_cache=True,
        cache_ttl_seconds=300,  # 5 minutes
    )
    await store.initialize()

    # Create and store a chain
    genesis = GenesisRecord(
        id="genesis-perf-001",
        agent_id="perf-agent-001",
        authority_id="org-demo",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        signature="perf-signature",
    )

    chain = TrustLineageChain(genesis=genesis)
    await store.store_chain(chain)

    # First retrieval (cache miss)
    print("First retrieval (cache miss)...")
    start = time.perf_counter()
    await store.get_chain("perf-agent-001")
    first_time = (time.perf_counter() - start) * 1000
    print(f"✓ Time: {first_time:.2f}ms")

    # Second retrieval (cache hit)
    print("\nSecond retrieval (cache hit)...")
    start = time.perf_counter()
    await store.get_chain("perf-agent-001")
    cached_time = (time.perf_counter() - start) * 1000
    print(f"✓ Time: {cached_time:.2f}ms")

    # Performance improvement
    improvement = ((first_time - cached_time) / first_time) * 100
    print(f"\n📊 Performance improvement: {improvement:.1f}%")
    print(f"   Cache makes retrieval {first_time/cached_time:.1f}x faster!")

    # Clean up
    await store.close()


async def example_3_filtering_pagination():
    """Example 3: Filtering and pagination."""
    print("\n=== Example 3: Filtering and Pagination ===\n")

    store = PostgresTrustStore(database_url=os.getenv("POSTGRES_URL"))
    await store.initialize()

    # Create multiple chains with different authorities
    print("Creating 15 test chains...")
    for i in range(15):
        authority = f"org-{i % 3}"  # 3 different authorities
        genesis = GenesisRecord(
            id=f"genesis-filter-{i}",
            agent_id=f"filter-agent-{i}",
            authority_id=authority,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=365),
            signature=f"filter-signature-{i}",
        )
        chain = TrustLineageChain(genesis=genesis)
        await store.store_chain(chain)
    print("✓ Created 15 chains")

    # Count all chains
    print("\nCounting chains...")
    total = await store.count_chains()
    print(f"✓ Total chains: {total}")

    # Filter by authority
    print("\nFiltering by authority (org-0)...")
    org0_chains = await store.list_chains(authority_id="org-0")
    print(f"✓ Found {len(org0_chains)} chains for org-0")

    # Pagination
    print("\nPagination demo (5 per page)...")
    page1 = await store.list_chains(limit=5, offset=0)
    page2 = await store.list_chains(limit=5, offset=5)
    page3 = await store.list_chains(limit=5, offset=10)

    print(f"✓ Page 1: {len(page1)} chains")
    print(f"✓ Page 2: {len(page2)} chains")
    print(f"✓ Page 3: {len(page3)} chains")

    # Display page 1 agent IDs
    print("\n  Page 1 agent IDs:")
    for chain in page1[:3]:  # Show first 3
        print(f"    - {chain.genesis.agent_id}")

    # Clean up
    await store.close()


async def example_4_soft_delete():
    """Example 4: Soft delete workflows."""
    print("\n=== Example 4: Soft Delete Workflows ===\n")

    store = PostgresTrustStore(database_url=os.getenv("POSTGRES_URL"))
    await store.initialize()

    # Create a chain
    genesis = GenesisRecord(
        id="genesis-delete-001",
        agent_id="delete-agent-001",
        authority_id="org-demo",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        signature="delete-signature",
    )
    chain = TrustLineageChain(genesis=genesis)
    await store.store_chain(chain)
    print("✓ Created chain for delete-agent-001")

    # Soft delete
    print("\nPerforming soft delete...")
    await store.delete_chain("delete-agent-001", soft_delete=True)
    print("✓ Chain soft deleted")

    # Try to retrieve (should fail)
    print("\nTrying to retrieve (active_only=True)...")
    try:
        await store.get_chain("delete-agent-001")
        print("✗ Unexpected: chain found!")
    except Exception as e:
        print(f"✓ Expected: {type(e).__name__}")

    # Retrieve with include_inactive
    print("\nRetrieving with include_inactive=True...")
    inactive_chain = await store.get_chain("delete-agent-001", include_inactive=True)
    print(f"✓ Retrieved inactive chain: {inactive_chain.genesis.agent_id}")

    # Hard delete
    print("\nPerforming hard delete...")
    await store.delete_chain("delete-agent-001", soft_delete=False)
    print("✓ Chain hard deleted")

    # Try to retrieve with include_inactive (should still fail)
    print("\nTrying to retrieve with include_inactive=True...")
    try:
        await store.get_chain("delete-agent-001", include_inactive=True)
        print("✗ Unexpected: chain found!")
    except Exception as e:
        print(f"✓ Expected: {type(e).__name__}")

    # Clean up
    await store.close()


async def example_5_integrity_verification():
    """Example 5: Chain integrity verification."""
    print("\n=== Example 5: Integrity Verification ===\n")

    store = PostgresTrustStore(database_url=os.getenv("POSTGRES_URL"))
    await store.initialize()

    # Create a chain with constraints
    genesis = GenesisRecord(
        id="genesis-verify-001",
        agent_id="verify-agent-001",
        authority_id="org-demo",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        signature="verify-signature",
    )

    constraint_envelope = ConstraintEnvelope(
        id="env-verify-001",
        agent_id="verify-agent-001",
        active_constraints=[
            Constraint(
                id="const-verify-001",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value={"max_api_calls": 1000},
                source="org-demo",
                priority=1,
            )
        ],
    )

    chain = TrustLineageChain(
        genesis=genesis,
        constraint_envelope=constraint_envelope,
    )

    # Store chain
    print("Storing chain with constraints...")
    await store.store_chain(chain)
    print("✓ Chain stored")

    # Verify integrity
    print("\nVerifying chain integrity...")
    is_valid = await store.verify_chain_integrity("verify-agent-001")

    if is_valid:
        print("✓ Chain integrity verified!")
        print("  Hash matches stored value - no tampering detected")
    else:
        print("✗ Chain integrity check failed!")
        print("  Hash mismatch - possible tampering")

    # Display chain hash
    retrieved_chain = await store.get_chain("verify-agent-001")
    print(f"\n📊 Chain hash: {retrieved_chain.hash()}")
    print(
        f"   Constraints: {len(retrieved_chain.constraint_envelope.active_constraints)}"
    )

    # Clean up
    await store.close()


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("PostgresTrustStore Usage Examples")
    print("=" * 60)

    try:
        await example_1_basic_crud()
        await example_2_cache_performance()
        await example_3_filtering_pagination()
        await example_4_soft_delete()
        await example_5_integrity_verification()

        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
