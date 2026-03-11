"""
Credential Rotation Example for EATP.

This example demonstrates how to use the CredentialRotationManager to:
1. Rotate cryptographic keys for organizational authorities
2. Schedule automatic key rotations
3. Monitor rotation status
4. Revoke old keys after grace period
5. Handle trust chain re-signing automatically

Prerequisites:
    - PostgreSQL database running with POSTGRES_URL set
    - Initial authority registered with trust chains
"""

import asyncio
import os
from datetime import datetime, timedelta

from kaizen.trust import (  # Core components; Authority setup; Trust establishment; Credential rotation; Crypto
    AuthorityPermission,
    AuthorityType,
    CapabilityRequest,
    CapabilityType,
    CredentialRotationManager,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    PostgresTrustStore,
    RotationStatus,
    TrustKeyManager,
    TrustOperations,
    generate_keypair,
)


async def setup_infrastructure():
    """Initialize trust infrastructure components."""
    # Get database URL
    database_url = os.getenv("POSTGRES_URL")
    if not database_url:
        raise ValueError("POSTGRES_URL environment variable not set")

    # Initialize components
    trust_store = PostgresTrustStore(database_url=database_url)
    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    await trust_store.initialize()
    await authority_registry.initialize()

    return trust_store, authority_registry, key_manager


async def create_test_authority(authority_registry, key_manager):
    """Create a test organizational authority."""
    # Generate keypair for the authority
    private_key, public_key = generate_keypair()
    signing_key_id = "acme-signing-key-001"

    # Register the private key
    key_manager.register_key(signing_key_id, private_key)

    # Create authority
    authority = OrganizationalAuthority(
        id="org-acme",
        name="Acme Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id=signing_key_id,
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
        is_active=True,
        metadata={"department": "Engineering"},
    )

    await authority_registry.register_authority(authority)
    print(f"✓ Created authority: {authority.id}")
    return authority


async def establish_trust_chains(trust_ops, authority_id, num_agents=3):
    """Establish trust for multiple agents."""
    agent_ids = []

    for i in range(num_agents):
        agent_id = f"agent-{i+1:03d}"
        agent_ids.append(agent_id)

        # Establish trust
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACCESS,
                    constraints=["read_only"],
                ),
                CapabilityRequest(
                    capability="generate_reports",
                    capability_type=CapabilityType.ACTION,
                    constraints=["internal_use_only"],
                ),
            ],
        )

        print(f"✓ Established trust for {agent_id}")

    return agent_ids


async def demonstrate_basic_rotation(rotation_manager, authority_id):
    """Demonstrate basic key rotation."""
    print("\n=== Basic Key Rotation ===")

    # Rotate key
    print(f"Rotating key for {authority_id}...")
    result = await rotation_manager.rotate_key(authority_id)

    print("✓ Rotation completed!")
    print(f"  - Old key: {result.old_key_id}")
    print(f"  - New key: {result.new_key_id}")
    print(f"  - Chains updated: {result.chains_updated}")
    print(
        f"  - Duration: {(result.completed_at - result.started_at).total_seconds():.2f}s"
    )
    print(f"  - Grace period ends: {result.grace_period_end.isoformat()}")


async def demonstrate_rotation_status(rotation_manager, authority_id):
    """Demonstrate rotation status checking."""
    print("\n=== Rotation Status ===")

    status = await rotation_manager.get_rotation_status(authority_id)

    print(f"Current status for {authority_id}:")
    print(f"  - Current key: {status.current_key_id}")
    print(
        f"  - Last rotation: {status.last_rotation.isoformat() if status.last_rotation else 'Never'}"
    )
    print(
        f"  - Next scheduled: {status.next_scheduled.isoformat() if status.next_scheduled else 'None'}"
    )
    print(f"  - Status: {status.status.value}")
    print(f"  - Keys in grace period: {len(status.grace_period_keys)}")
    print(f"  - Pending revocations: {len(status.pending_revocations)}")

    if status.grace_period_keys:
        print("  Grace period keys:")
        for key_id, expiry in status.grace_period_keys.items():
            print(f"    - {key_id}: expires {expiry.isoformat()}")


async def demonstrate_scheduled_rotation(rotation_manager, authority_id):
    """Demonstrate scheduled rotation."""
    print("\n=== Scheduled Rotation ===")

    # Schedule rotation for 1 second in the future (for demo purposes)
    future_time = datetime.utcnow() + timedelta(seconds=2)
    rotation_id = await rotation_manager.schedule_rotation(authority_id, at=future_time)

    print(f"✓ Scheduled rotation {rotation_id} for {future_time.isoformat()}")

    # Wait for scheduled time
    print("Waiting for scheduled rotation...")
    await asyncio.sleep(3)

    # Process scheduled rotations
    results = await rotation_manager.process_scheduled_rotations()

    if results:
        print(f"✓ Processed {len(results)} scheduled rotation(s)")
        for result in results:
            print(f"  - Rotated {result.old_key_id} -> {result.new_key_id}")
    else:
        print("No scheduled rotations were due")


async def demonstrate_custom_grace_period(rotation_manager, authority_id):
    """Demonstrate rotation with custom grace period."""
    print("\n=== Custom Grace Period ===")

    # Rotate with 48-hour grace period
    print("Rotating with 48-hour grace period...")
    result = await rotation_manager.rotate_key(authority_id, grace_period_hours=48)

    print("✓ Rotation completed!")
    print("  - Grace period: 48 hours")
    print(f"  - Grace period ends: {result.grace_period_end.isoformat()}")

    # Calculate remaining time
    remaining = result.grace_period_end - datetime.utcnow()
    print(f"  - Time remaining: {remaining.total_seconds() / 3600:.1f} hours")


async def demonstrate_key_revocation(rotation_manager, authority_id):
    """Demonstrate old key revocation."""
    print("\n=== Key Revocation ===")

    # Get current status
    status = await rotation_manager.get_rotation_status(authority_id)

    if not status.grace_period_keys:
        print("No keys in grace period to revoke")
        return

    # For demo purposes, manually expire a key
    for key_id, expiry in status.grace_period_keys.items():
        # Manually set expiry to past (for demo)
        rotation_manager._grace_period_keys[authority_id][
            key_id
        ] = datetime.utcnow() - timedelta(hours=1)
        print(f"Simulating expired grace period for {key_id}...")

        # Revoke key
        await rotation_manager.revoke_old_key(authority_id, key_id)
        print(f"✓ Revoked key {key_id}")
        break


async def demonstrate_rotation_history(rotation_manager, authority_id):
    """Display rotation history."""
    print("\n=== Rotation History ===")

    if authority_id not in rotation_manager._rotation_history:
        print("No rotation history available")
        return

    history = rotation_manager._rotation_history[authority_id]
    print(f"Found {len(history)} rotation(s):")

    for i, result in enumerate(history, 1):
        print(f"\n  Rotation {i}:")
        print(f"    - ID: {result.rotation_id}")
        print(f"    - Old key: {result.old_key_id}")
        print(f"    - New key: {result.new_key_id}")
        print(f"    - Chains updated: {result.chains_updated}")
        print(f"    - Completed: {result.completed_at.isoformat()}")


async def verify_chains_after_rotation(trust_store, agent_ids):
    """Verify that trust chains are still valid after rotation."""
    print("\n=== Verifying Trust Chains ===")

    for agent_id in agent_ids:
        chain = await trust_store.get_chain(agent_id)
        result = chain.verify_basic()

        status = "✓" if result.valid else "✗"
        print(f"{status} {agent_id}: {result.reason or 'Valid'}")


async def main():
    """Main demonstration flow."""
    print("Credential Rotation Example")
    print("=" * 50)

    # Setup
    print("\n=== Setup ===")
    trust_store, authority_registry, key_manager = await setup_infrastructure()

    # Create test authority
    authority = await create_test_authority(authority_registry, key_manager)

    # Create trust operations
    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    # Establish trust chains
    agent_ids = await establish_trust_chains(trust_ops, authority.id, num_agents=3)

    # Create rotation manager
    rotation_manager = CredentialRotationManager(
        key_manager=key_manager,
        trust_store=trust_store,
        authority_registry=authority_registry,
        rotation_period_days=90,
        grace_period_hours=24,
    )
    await rotation_manager.initialize()

    # Demonstrate features
    await demonstrate_basic_rotation(rotation_manager, authority.id)
    await demonstrate_rotation_status(rotation_manager, authority.id)
    await verify_chains_after_rotation(trust_store, agent_ids)

    await demonstrate_custom_grace_period(rotation_manager, authority.id)
    await demonstrate_rotation_status(rotation_manager, authority.id)

    await demonstrate_scheduled_rotation(rotation_manager, authority.id)
    await demonstrate_rotation_status(rotation_manager, authority.id)

    await demonstrate_key_revocation(rotation_manager, authority.id)
    await demonstrate_rotation_status(rotation_manager, authority.id)

    await demonstrate_rotation_history(rotation_manager, authority.id)

    # Cleanup
    print("\n=== Cleanup ===")
    await rotation_manager.close()
    await trust_store.close()
    await authority_registry.close()
    print("✓ Cleanup complete")

    print("\n" + "=" * 50)
    print("Demonstration complete!")


if __name__ == "__main__":
    asyncio.run(main())
