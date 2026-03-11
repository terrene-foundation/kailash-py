"""
PostgresTrustStore Integration Example with TrustedAgent.

This example demonstrates how to integrate PostgresTrustStore with the
TrustedAgent class for persistent trust chain storage.

This is a conceptual example showing the integration pattern.
Actual integration with TrustedAgent will happen in a future step.

Run with:
    POSTGRES_URL="postgresql://..." python -m examples.trust_store_integration
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.store import PostgresTrustStore


class TrustedAgentWithPersistence:
    """
    Example of how TrustedAgent might integrate with PostgresTrustStore.

    This is a conceptual example showing the integration pattern.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        trust_store: PostgresTrustStore,
    ):
        """
        Initialize TrustedAgent with persistent trust storage.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable agent name
            trust_store: PostgresTrustStore instance for persistence
        """
        self.agent_id = agent_id
        self.name = name
        self.trust_store = trust_store
        self._trust_chain: Optional[TrustLineageChain] = None

    async def establish_trust(
        self,
        authority_id: str,
        authority_type: AuthorityType,
        capabilities: list[str],
        constraints: list[dict] = None,
        expires_in_days: int = 365,
    ) -> TrustLineageChain:
        """
        Establish trust for this agent and persist to database.

        Args:
            authority_id: Who is authorizing this agent
            authority_type: Type of authority (ORGANIZATION, SYSTEM, HUMAN)
            capabilities: List of capabilities to grant
            constraints: Optional list of constraints
            expires_in_days: How many days until trust expires

        Returns:
            The established TrustLineageChain
        """
        # Create genesis record
        genesis = GenesisRecord(
            id=f"genesis-{self.agent_id}",
            agent_id=self.agent_id,
            authority_id=authority_id,
            authority_type=authority_type,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
            signature=f"signature-{self.agent_id}",  # In real impl: crypto.sign()
        )

        # Create capability attestations
        capability_attestations = []
        for i, capability in enumerate(capabilities):
            attestation = CapabilityAttestation(
                id=f"cap-{self.agent_id}-{i}",
                capability=capability,
                capability_type=CapabilityType.ACCESS,
                constraints=[],
                attester_id=authority_id,
                attested_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=90),
                signature=f"cap-signature-{i}",
            )
            capability_attestations.append(attestation)

        # Create constraint envelope
        constraint_envelope = None
        if constraints:
            active_constraints = []
            for i, constraint in enumerate(constraints):
                c = Constraint(
                    id=f"const-{self.agent_id}-{i}",
                    constraint_type=ConstraintType.RESOURCE_LIMIT,
                    value=constraint,
                    source=authority_id,
                    priority=1,
                )
                active_constraints.append(c)

            constraint_envelope = ConstraintEnvelope(
                id=f"env-{self.agent_id}",
                agent_id=self.agent_id,
                active_constraints=active_constraints,
            )

        # Create trust chain
        self._trust_chain = TrustLineageChain(
            genesis=genesis,
            capabilities=capability_attestations,
            delegations=[],
            constraint_envelope=constraint_envelope,
            audit_anchors=[],
        )

        # Persist to database
        await self.trust_store.store_chain(self._trust_chain)

        print(f"✓ Trust established for {self.name} (agent_id={self.agent_id})")
        print(f"  Authority: {authority_id}")
        print(f"  Capabilities: {len(capabilities)}")
        print(f"  Constraints: {len(constraints) if constraints else 0}")

        return self._trust_chain

    async def load_trust_chain(self) -> TrustLineageChain:
        """
        Load trust chain from database.

        Returns:
            The loaded TrustLineageChain

        Raises:
            TrustChainNotFoundError: If no trust chain exists for this agent
        """
        self._trust_chain = await self.trust_store.get_chain(self.agent_id)
        print(f"✓ Trust chain loaded for {self.name} (from cache/db)")
        return self._trust_chain

    async def has_capability(self, capability: str) -> bool:
        """
        Check if agent has a specific capability.

        Args:
            capability: The capability to check for

        Returns:
            True if agent has the capability and it's not expired
        """
        if not self._trust_chain:
            await self.load_trust_chain()

        return self._trust_chain.has_capability(capability)

    async def add_capability(
        self,
        capability: str,
        attester_id: str,
        expires_in_days: int = 90,
    ) -> None:
        """
        Add a new capability to this agent's trust chain.

        Args:
            capability: The capability to add
            attester_id: Who is attesting to this capability
            expires_in_days: How many days until capability expires
        """
        if not self._trust_chain:
            await self.load_trust_chain()

        # Create new capability attestation
        new_capability = CapabilityAttestation(
            id=f"cap-{self.agent_id}-{len(self._trust_chain.capabilities)}",
            capability=capability,
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id=attester_id,
            attested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
            signature="cap-signature-new",
        )

        # Add to chain
        self._trust_chain.capabilities.append(new_capability)

        # Update in database
        await self.trust_store.update_chain(self.agent_id, self._trust_chain)

        print(f"✓ Added capability '{capability}' to {self.name}")

    async def delegate_to(
        self,
        delegatee_agent_id: str,
        task_id: str,
        capabilities: list[str],
    ) -> DelegationRecord:
        """
        Delegate work to another agent.

        Args:
            delegatee_agent_id: The agent receiving the delegation
            task_id: Unique identifier for this task
            capabilities: List of capabilities to delegate

        Returns:
            The created DelegationRecord
        """
        if not self._trust_chain:
            await self.load_trust_chain()

        # Create delegation record
        delegation = DelegationRecord(
            id=f"delegation-{self.agent_id}-{task_id}",
            delegator_id=self.agent_id,
            delegatee_id=delegatee_agent_id,
            task_id=task_id,
            capabilities_delegated=capabilities,
            constraint_subset=[],
            delegated_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            signature=f"delegation-signature-{task_id}",
        )

        # Add to chain
        self._trust_chain.delegations.append(delegation)

        # Update in database
        await self.trust_store.update_chain(self.agent_id, self._trust_chain)

        print(f"✓ {self.name} delegated to {delegatee_agent_id} for task {task_id}")
        print(f"  Capabilities: {capabilities}")

        return delegation

    async def verify_integrity(self) -> bool:
        """
        Verify the integrity of this agent's trust chain.

        Returns:
            True if integrity is verified
        """
        return await self.trust_store.verify_chain_integrity(self.agent_id)

    async def revoke_trust(self, soft_delete: bool = True) -> None:
        """
        Revoke trust for this agent.

        Args:
            soft_delete: Use soft delete (preserves audit trail) vs hard delete
        """
        await self.trust_store.delete_chain(self.agent_id, soft_delete=soft_delete)
        self._trust_chain = None

        print(f"✓ Trust revoked for {self.name}")


async def demo_integration():
    """Demonstrate integration of PostgresTrustStore with TrustedAgent."""
    print("\n" + "=" * 70)
    print("PostgresTrustStore Integration with TrustedAgent")
    print("=" * 70 + "\n")

    # Initialize trust store
    print("1. Initializing trust store...")
    store = PostgresTrustStore(
        database_url=os.getenv("POSTGRES_URL"),
        enable_cache=True,
        cache_ttl_seconds=300,
    )
    await store.initialize()
    print("   ✓ Trust store initialized\n")

    # Create first agent
    print("2. Creating analyst agent...")
    analyst = TrustedAgentWithPersistence(
        agent_id="agent-analyst-001",
        name="Data Analyst Agent",
        trust_store=store,
    )

    # Establish trust for analyst
    await analyst.establish_trust(
        authority_id="org-acme-analytics",
        authority_type=AuthorityType.ORGANIZATION,
        capabilities=[
            "read:customer_data",
            "read:analytics_data",
            "create:reports",
        ],
        constraints=[
            {"max_api_calls": 1000},
            {"data_scope": "department:analytics"},
        ],
        expires_in_days=365,
    )
    print()

    # Create second agent
    print("3. Creating research agent...")
    researcher = TrustedAgentWithPersistence(
        agent_id="agent-researcher-001",
        name="Research Agent",
        trust_store=store,
    )

    await researcher.establish_trust(
        authority_id="org-acme-research",
        authority_type=AuthorityType.ORGANIZATION,
        capabilities=[
            "read:research_data",
            "create:experiments",
        ],
        expires_in_days=365,
    )
    print()

    # Demonstrate capability checking
    print("4. Checking capabilities...")
    has_customer_data = await analyst.has_capability("read:customer_data")
    print(f"   Analyst has 'read:customer_data': {has_customer_data}")

    has_research_data = await researcher.has_capability("read:research_data")
    print(f"   Researcher has 'read:research_data': {has_research_data}")
    print()

    # Add new capability
    print("5. Adding new capability to analyst...")
    await analyst.add_capability(
        capability="write:analytics_data",
        attester_id="org-acme-analytics",
        expires_in_days=90,
    )
    print()

    # Delegation
    print("6. Analyst delegating to researcher...")
    delegation = await analyst.delegate_to(
        delegatee_agent_id="agent-researcher-001",
        task_id="task-data-analysis-2024",
        capabilities=["read:customer_data"],
    )
    print()

    # Verify integrity
    print("7. Verifying trust chain integrity...")
    analyst_valid = await analyst.verify_integrity()
    print(f"   Analyst chain integrity: {'✓ Valid' if analyst_valid else '✗ Invalid'}")

    researcher_valid = await researcher.verify_integrity()
    print(
        f"   Researcher chain integrity: {'✓ Valid' if researcher_valid else '✗ Invalid'}"
    )
    print()

    # List all chains
    print("8. Listing all trust chains...")
    all_chains = await store.list_chains()
    print(f"   Total active chains: {len(all_chains)}")
    for chain in all_chains:
        print(
            f"   - {chain.genesis.agent_id} (authority: {chain.genesis.authority_id})"
        )
    print()

    # Count by authority
    print("9. Counting chains by authority...")
    analytics_count = await store.count_chains(authority_id="org-acme-analytics")
    research_count = await store.count_chains(authority_id="org-acme-research")
    print(f"   Analytics department: {analytics_count} agents")
    print(f"   Research department: {research_count} agents")
    print()

    # Demonstrate persistence by reloading
    print("10. Testing persistence (reload from database)...")
    new_analyst_instance = TrustedAgentWithPersistence(
        agent_id="agent-analyst-001",
        name="Data Analyst Agent (Reloaded)",
        trust_store=store,
    )
    await new_analyst_instance.load_trust_chain()

    # Verify capabilities persisted
    has_write = await new_analyst_instance.has_capability("write:analytics_data")
    print(f"   Reloaded agent has 'write:analytics_data': {has_write}")
    print()

    # Soft delete
    print("11. Soft deleting researcher agent...")
    await researcher.revoke_trust(soft_delete=True)
    print()

    # Verify soft delete
    print("12. Verifying soft delete...")
    active_count = await store.count_chains(active_only=True)
    all_count = await store.count_chains(active_only=False)
    print(f"   Active chains: {active_count}")
    print(f"   All chains (including inactive): {all_count}")
    print()

    # Cleanup
    print("13. Cleaning up...")
    await store.close()
    print("   ✓ Trust store closed\n")

    print("=" * 70)
    print("Integration Demo Complete!")
    print("=" * 70)
    print("\nKey Features Demonstrated:")
    print("✓ Persistent trust chain storage")
    print("✓ Automatic caching (fast retrieval)")
    print("✓ Capability management")
    print("✓ Delegation tracking")
    print("✓ Integrity verification")
    print("✓ Soft delete (audit trail)")
    print("✓ Filtering and counting")
    print("✓ Cross-session persistence")
    print()


if __name__ == "__main__":
    asyncio.run(demo_integration())
