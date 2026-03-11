"""
Single Agent Trust Example.

Demonstrates basic EATP workflow:
1. Setup authority and trust store
2. Establish trust for an agent
3. Verify trust before action
4. Audit actions after execution

This is the simplest EATP use case - a single trusted agent.
"""

import asyncio
from datetime import datetime, timedelta

from kaizen.trust import (  # Core operations; Storage; Authority; Crypto
    ActionResult,
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


async def main():
    """Demonstrate single agent trust workflow."""
    print("=" * 60)
    print("EATP Single Agent Trust Example")
    print("=" * 60)

    # =========================================================================
    # Step 1: Setup Infrastructure
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    # In production, use real PostgreSQL URL
    # For demo, we'll use in-memory stores
    database_url = "postgresql://localhost:5432/kaizen_trust"

    # Create trust store (holds trust chains)
    trust_store = PostgresTrustStore(
        database_url=database_url,
        enable_cache=True,
        cache_ttl_seconds=300,
    )

    # Create authority registry (manages authorities)
    authority_registry = OrganizationalAuthorityRegistry(
        database_url=database_url,
        enable_cache=True,
    )

    # Create key manager (holds signing keys)
    key_manager = TrustKeyManager()

    print("   - PostgresTrustStore created")
    print("   - OrganizationalAuthorityRegistry created")
    print("   - TrustKeyManager created")

    # =========================================================================
    # Step 2: Register an Authority
    # =========================================================================
    print("\n2. Registering organizational authority...")

    # Generate Ed25519 keypair for the authority
    private_key, public_key = generate_keypair()
    authority_id = "org-acme-corp"
    signing_key_id = f"key-{authority_id}"

    # Register the private key with key manager
    key_manager.register_key(signing_key_id, private_key)

    # Create and register the authority
    authority = OrganizationalAuthority(
        id=authority_id,
        name="Acme Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id=signing_key_id,
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
        is_active=True,
        metadata={
            "department": "AI Operations",
            "contact": "trust-admin@acme.com",
        },
    )

    try:
        await authority_registry.initialize()
        await authority_registry.register_authority(authority)
        print(f"   - Authority registered: {authority.name}")
        print(f"   - Authority ID: {authority_id}")
        print(f"   - Permissions: {[p.value for p in authority.permissions]}")
    except Exception as e:
        print(f"   Note: {e}")

    # =========================================================================
    # Step 3: Create TrustOperations
    # =========================================================================
    print("\n3. Initializing TrustOperations...")

    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()
    print("   - TrustOperations initialized")

    # =========================================================================
    # Step 4: Establish Trust for an Agent
    # =========================================================================
    print("\n4. Establishing trust for agent...")

    agent_id = "agent-data-analyst-001"

    try:
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACCESS,
                    constraints=["read_only", "max_records:10000"],
                ),
                CapabilityRequest(
                    capability="generate_reports",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            metadata={
                "purpose": "Financial data analysis",
                "owner": "data-science-team",
            },
            expires_at=datetime.utcnow() + timedelta(days=90),
        )

        print(f"   - Agent established: {agent_id}")
        print(f"   - Genesis Record ID: {chain.genesis.id}")
        print(f"   - Capabilities granted: {len(chain.capabilities)}")
        for cap in chain.capabilities:
            print(f"     * {cap.capability_uri} ({cap.capability_type.value})")

    except Exception as e:
        print(f"   Note: {e}")
        return

    # =========================================================================
    # Step 5: Verify Trust (QUICK level)
    # =========================================================================
    print("\n5. Verifying trust (QUICK level)...")

    result = await trust_ops.verify(
        agent_id=agent_id,
        level=VerificationLevel.QUICK,
    )

    print(f"   - Valid: {result.valid}")
    print(f"   - Level: {result.level.value}")
    print(f"   - Latency: {result.latency_ms:.2f}ms")

    # =========================================================================
    # Step 6: Verify Trust with Capability Check (STANDARD level)
    # =========================================================================
    print("\n6. Verifying trust with capability check (STANDARD level)...")

    result = await trust_ops.verify(
        agent_id=agent_id,
        action="analyze_data",
        level=VerificationLevel.STANDARD,
    )

    print(f"   - Valid: {result.valid}")
    print("   - Action checked: analyze_data")
    print(f"   - Latency: {result.latency_ms:.2f}ms")

    # =========================================================================
    # Step 7: Verify Trust with Signature Check (FULL level)
    # =========================================================================
    print("\n7. Verifying trust with signature check (FULL level)...")

    result = await trust_ops.verify(
        agent_id=agent_id,
        action="analyze_data",
        level=VerificationLevel.FULL,
    )

    print(f"   - Valid: {result.valid}")
    print("   - Signatures verified: Yes")
    print(f"   - Latency: {result.latency_ms:.2f}ms")

    # =========================================================================
    # Step 8: Audit an Action
    # =========================================================================
    print("\n8. Recording audit anchor...")

    anchor = await trust_ops.audit(
        agent_id=agent_id,
        action_type="data_analysis",
        resource_uri="database://finance/transactions",
        result=ActionResult.SUCCESS,
        metadata={
            "records_processed": 5000,
            "report_generated": True,
            "duration_seconds": 12.5,
        },
    )

    print(f"   - Audit Anchor ID: {anchor.id}")
    print(f"   - Action Type: {anchor.action_type}")
    print(f"   - Resource: {anchor.resource_uri}")
    print(f"   - Result: {anchor.result.value}")
    print(f"   - Timestamp: {anchor.timestamp}")

    # =========================================================================
    # Step 9: Cleanup
    # =========================================================================
    print("\n9. Cleaning up...")
    await trust_store.close()
    await authority_registry.close()
    print("   - Connections closed")

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
