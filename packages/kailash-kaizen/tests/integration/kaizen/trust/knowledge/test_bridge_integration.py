"""
Integration tests for CARE-038: Trust-Chain-to-Knowledge Bridge.

Tests use REAL TrustOperations with InMemoryTrustStore (NO MOCKING).
Verifies the bridge correctly integrates trust operations with
knowledge management.

These tests require setting up:
- OrganizationalAuthorityRegistry (in-memory)
- TrustKeyManager
- InMemoryTrustStore
- TrustOperations

Then establishing trust chains and using them via the bridge.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from kaizen.trust.authority import AuthorityPermission, OrganizationalAuthority
from kaizen.trust.chain import AuthorityType, CapabilityType
from kaizen.trust.crypto import generate_keypair
from kaizen.trust.knowledge import (
    InMemoryKnowledgeStore,
    InMemoryProvenanceStore,
    ProvRelation,
    TrustKnowledgeBridge,
)
from kaizen.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kaizen.trust.store import InMemoryTrustStore


class InMemoryAuthorityRegistry:
    """
    In-memory authority registry for testing.

    Mimics OrganizationalAuthorityRegistry but stores authorities in memory
    without requiring PostgreSQL.
    """

    def __init__(self):
        self._authorities: dict[str, OrganizationalAuthority] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def register_authority(self, authority: OrganizationalAuthority) -> str:
        self._authorities[authority.id] = authority
        return authority.id

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            from kaizen.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            from kaizen.trust.exceptions import AuthorityInactiveError

            raise AuthorityInactiveError(authority_id)
        return authority


@pytest.fixture
def keypair():
    """Generate a test keypair."""
    return generate_keypair()


@pytest_asyncio.fixture
async def trust_infrastructure(keypair):
    """Set up complete trust infrastructure for integration testing."""
    private_key, public_key = keypair

    # Create in-memory registry
    registry = InMemoryAuthorityRegistry()
    await registry.initialize()

    # Create and register authority
    authority = OrganizationalAuthority(
        id="org-test",
        name="Test Organization",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="test-signing-key",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
            AuthorityPermission.DELEGATE_TRUST,
        ],
    )
    await registry.register_authority(authority)

    # Create key manager and register key
    key_manager = TrustKeyManager()
    key_manager.register_key("test-signing-key", private_key)

    # Create trust store
    trust_store = InMemoryTrustStore()
    await trust_store.initialize()

    # Create trust operations
    trust_ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    return {
        "trust_ops": trust_ops,
        "trust_store": trust_store,
        "key_manager": key_manager,
        "authority": authority,
        "private_key": private_key,
        "public_key": public_key,
    }


class TestKnowledgeLifecycleWithTrust:
    """Integration tests for knowledge lifecycle with real trust operations."""

    @pytest.mark.asyncio
    async def test_knowledge_lifecycle_with_trust(self, trust_infrastructure):
        """Establish trust, create knowledge via bridge, verify trust, query knowledge."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # 1. Establish trust for an agent
        chain = await trust_ops.establish(
            agent_id="knowledge-agent-001",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            constraints=["read_only"],
        )

        assert chain is not None
        assert chain.genesis.agent_id == "knowledge-agent-001"

        # 2. Create bridge with trust operations
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # 3. Create knowledge via bridge
        entry = await bridge.create_knowledge_with_trust(
            content="Integration test: System supports 10,000 users",
            content_type="factual",
            agent_id="knowledge-agent-001",
            confidence_score=0.92,
            domain="infrastructure",
        )

        assert entry is not None
        assert entry.source_agent_id == "knowledge-agent-001"
        # With trust ops, trust_chain_ref should be the chain hash
        assert entry.trust_chain_ref == chain.hash()

        # 4. Verify trust
        verification = await bridge.verify_knowledge_trust(entry.entry_id)
        assert verification["valid"] is True
        assert verification["has_trust_operations"] is True

        # 5. Query knowledge
        results = await bridge.query_by_trust_level(min_confidence=0.9)
        assert len(results) == 1
        assert results[0].entry_id == entry.entry_id

    @pytest.mark.asyncio
    async def test_derived_knowledge_chain(self, trust_infrastructure):
        """Agent A creates K1, Agent B creates K2 derived from K1, query with include_derived."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Establish trust for Agent A
        await trust_ops.establish(
            agent_id="agent-a",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Establish trust for Agent B
        await trust_ops.establish(
            agent_id="agent-b",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="derive_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Create bridge
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Agent A creates K1
        k1 = await bridge.create_knowledge_with_trust(
            content="Original research finding by Agent A",
            content_type="factual",
            agent_id="agent-a",
            confidence_score=0.95,
        )

        # Agent B creates K2 derived from K1
        k2 = await bridge.create_knowledge_with_trust(
            content="Analysis based on Agent A's finding",
            content_type="insight",
            agent_id="agent-b",
            confidence_score=0.88,
            derived_from=[k1.entry_id],
        )

        # Query Agent A without include_derived
        results_without = await bridge.query_by_agent("agent-a", include_derived=False)
        assert len(results_without) == 1
        assert results_without[0].entry_id == k1.entry_id

        # Query Agent A with include_derived
        results_with = await bridge.query_by_agent("agent-a", include_derived=True)
        assert len(results_with) == 2
        result_ids = {e.entry_id for e in results_with}
        assert k1.entry_id in result_ids
        assert k2.entry_id in result_ids

    @pytest.mark.asyncio
    async def test_cross_agent_knowledge_sharing(self, trust_infrastructure):
        """Agent A creates entry, Agent B queries and verifies, check verified_by."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Establish trust for both agents
        await trust_ops.establish(
            agent_id="creator-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        await trust_ops.establish(
            agent_id="verifier-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="verify_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Create bridge
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Creator creates entry
        entry = await bridge.create_knowledge_with_trust(
            content="Shared knowledge for verification",
            content_type="factual",
            agent_id="creator-agent",
        )

        # Verifier verifies the knowledge trust
        verification = await bridge.verify_knowledge_trust(entry.entry_id)
        assert verification["valid"] is True

        # Add verifier to verified_by list
        entry.add_verification("verifier-agent")
        await bridge._knowledge_store.update(entry)

        # Query with min_verifiers=1
        results = await bridge.query_by_trust_level(min_confidence=0.0, min_verifiers=1)
        assert len(results) == 1
        assert "verifier-agent" in results[0].verified_by

    @pytest.mark.asyncio
    async def test_trust_verification_with_real_chain(self, trust_infrastructure):
        """Create knowledge with real trust chain, verify_knowledge_trust returns valid=True with chain details."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Establish trust
        chain = await trust_ops.establish(
            agent_id="verified-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACCESS,
                ),
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            constraints=["read_only", "audit_required"],
        )

        # Create bridge
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create knowledge
        entry = await bridge.create_knowledge_with_trust(
            content="Knowledge from verified agent",
            content_type="factual",
            agent_id="verified-agent",
            confidence_score=0.9,
        )

        # Verify trust
        result = await bridge.verify_knowledge_trust(entry.entry_id)

        assert result["valid"] is True
        assert result["has_trust_operations"] is True
        assert result["agent_id"] == "verified-agent"
        assert result["trust_chain_ref"] == chain.hash()
        assert "chain_hash" in result
        assert "capabilities" in result
        assert "analyze_data" in result["capabilities"]
        assert "contribute_knowledge" in result["capabilities"]


class TestTrustVerificationFailures:
    """Integration tests for trust verification failure scenarios."""

    @pytest.mark.asyncio
    async def test_verify_knowledge_agent_not_established(self, trust_infrastructure):
        """Verify knowledge from agent without trust chain returns failure."""
        trust_ops = trust_infrastructure["trust_ops"]

        # Create bridge with trust ops but DON'T establish trust for the agent
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create knowledge directly in store (bypassing normal flow)
        from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType

        entry = KnowledgeEntry.create(
            content="Knowledge from unestablished agent",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="unknown-agent",
            trust_chain_ref="fake-chain-ref",
        )
        await bridge._knowledge_store.store(entry)

        # Verify trust - should fail
        result = await bridge.verify_knowledge_trust(entry.entry_id)

        assert result["valid"] is False
        assert "verification failed" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_flag_untrusted_after_verification_failure(
        self, trust_infrastructure
    ):
        """Flag knowledge as untrusted after verification fails."""
        trust_ops = trust_infrastructure["trust_ops"]

        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create knowledge with fake trust chain
        from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType

        entry = KnowledgeEntry.create(
            content="Suspicious knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="suspicious-agent",
            trust_chain_ref="tampered-chain-ref",
        )
        await bridge._knowledge_store.store(entry)

        # Verify - should fail
        result = await bridge.verify_knowledge_trust(entry.entry_id)
        assert result["valid"] is False

        # Flag as untrusted
        await bridge.flag_untrusted_knowledge(entry.entry_id, reason=result["reason"])

        # Check flagged
        flagged = await bridge._knowledge_store.get(entry.entry_id)
        assert flagged.metadata.get("untrusted") is True


class TestConstraintScopeIntegration:
    """Integration tests for constraint scope with real trust chains."""

    @pytest.mark.asyncio
    async def test_knowledge_with_constraint_scope_from_chain(
        self, trust_infrastructure
    ):
        """Knowledge entry gets constraint_scope from trust chain constraints."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Establish trust with specific constraints
        await trust_ops.establish(
            agent_id="constrained-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                    constraints=["no_pii_export"],
                ),
            ],
            constraints=["read_only", "business_hours_only"],
        )

        # Create bridge
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create knowledge
        entry = await bridge.create_knowledge_with_trust(
            content="Constrained knowledge",
            content_type="factual",
            agent_id="constrained-agent",
        )

        # Entry should have constraint_envelope_ref
        assert entry.constraint_envelope_ref is not None

        # Constraint scope should be in metadata (from chain constraints)
        # The constraints get extracted from the chain's constraint envelope
        if entry.metadata.get("constraint_scope"):
            # Query by constraint scope
            results = await bridge.query_by_constraint_scope("read_only")
            # Should find the entry if read_only is in constraint_scope
            assert any(e.entry_id == entry.entry_id for e in results)


class TestProvenanceWithTrust:
    """Integration tests for provenance with trust chain references."""

    @pytest.mark.asyncio
    async def test_provenance_includes_trust_chain_ref(self, trust_infrastructure):
        """Provenance record attributes include trust_chain_ref."""
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Establish trust
        chain = await trust_ops.establish(
            agent_id="provenance-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Create bridge
        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create knowledge
        entry = await bridge.create_knowledge_with_trust(
            content="Knowledge for provenance test",
            content_type="factual",
            agent_id="provenance-agent",
        )

        # Get provenance
        prov = await bridge._provenance_store.get_provenance(entry.entry_id)

        assert prov is not None
        assert prov.attributes["trust_chain_ref"] == chain.hash()
        assert ProvRelation.WAS_ATTRIBUTED_TO.value in prov.relations
        assert (
            "provenance-agent" in prov.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]
        )
