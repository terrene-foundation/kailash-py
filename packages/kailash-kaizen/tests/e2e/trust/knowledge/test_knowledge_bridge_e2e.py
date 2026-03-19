"""
E2E tests for CARE-038: Trust-Chain-to-Knowledge Bridge.

End-to-end tests verify the complete trustworthy knowledge ledger workflow:
- Multiple agents with trust chains creating knowledge
- Cross-agent knowledge derivation
- Trust level queries and verification
- Provenance export and full traceability

These tests use REAL infrastructure (NO MOCKING):
- Real trust chain generation with cryptographic signatures
- Real InMemoryTrustStore
- Real InMemoryKnowledgeStore
- Real InMemoryProvenanceStore
- Real TrustOperations
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
    ProvenanceChain,
    ProvRelation,
    TrustKnowledgeBridge,
)
from kaizen.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kaizen.trust.store import InMemoryTrustStore


class InMemoryAuthorityRegistry:
    """
    In-memory authority registry for E2E testing.

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


class TestTrustworthyKnowledgeLedgerE2E:
    """E2E tests for the complete trustworthy knowledge ledger."""

    @pytest.fixture
    def keypair(self):
        """Generate a test keypair."""
        return generate_keypair()

    @pytest_asyncio.fixture
    async def trust_infrastructure(self, keypair):
        """Set up complete trust infrastructure for E2E testing."""
        private_key, public_key = keypair

        # Create in-memory registry
        registry = InMemoryAuthorityRegistry()
        await registry.initialize()

        # Create and register authority
        authority = OrganizationalAuthority(
            id="org-e2e",
            name="E2E Test Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=public_key,
            signing_key_id="e2e-signing-key",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.GRANT_CAPABILITIES,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )
        await registry.register_authority(authority)

        # Create key manager and register key
        key_manager = TrustKeyManager()
        key_manager.register_key("e2e-signing-key", private_key)

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

    @pytest.mark.asyncio
    async def test_e2e_trustworthy_knowledge_ledger(self, trust_infrastructure):
        """
        Complete E2E test:
        1. Setup 3 agents with trust chains
        2. Create 6+ knowledge entries across agents
        3. Query by trust level
        4. Query by agent
        5. Verify all knowledge has provenance
        6. Export provenance to PROV-JSON
        7. Assert full traceability
        """
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # ========================================
        # Step 1: Setup 3 agents with trust chains
        # ========================================
        agent_ids = ["research-agent", "analyst-agent", "reviewer-agent"]
        agent_chains = {}

        for agent_id in agent_ids:
            chain = await trust_ops.establish(
                agent_id=agent_id,
                authority_id=authority.id,
                capabilities=[
                    CapabilityRequest(
                        capability="contribute_knowledge",
                        capability_type=CapabilityType.ACTION,
                    ),
                    CapabilityRequest(
                        capability="derive_knowledge",
                        capability_type=CapabilityType.ACTION,
                    ),
                    CapabilityRequest(
                        capability="verify_knowledge",
                        capability_type=CapabilityType.ACTION,
                    ),
                ],
                constraints=["audit_required"],
            )
            agent_chains[agent_id] = chain

        # Verify all 3 agents have trust chains
        assert len(agent_chains) == 3
        for agent_id, chain in agent_chains.items():
            assert chain.genesis.agent_id == agent_id
            assert not chain.is_expired()

        # ========================================
        # Step 2: Create bridge and 6+ knowledge entries
        # ========================================
        knowledge_store = InMemoryKnowledgeStore()
        provenance_store = InMemoryProvenanceStore()

        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=knowledge_store,
            provenance_store=provenance_store,
        )

        entries = []

        # Research agent creates 2 factual entries (high confidence)
        for i in range(2):
            entry = await bridge.create_knowledge_with_trust(
                content=f"Research finding {i}: Core infrastructure capacity",
                content_type="factual",
                agent_id="research-agent",
                confidence_score=0.95 + (i * 0.02),  # 0.95, 0.97
                domain="infrastructure",
            )
            entries.append(entry)

        # Analyst agent creates 2 insight entries (derived from research)
        for i in range(2):
            source_entry = entries[i]
            entry = await bridge.create_knowledge_with_trust(
                content=f"Analysis {i}: Derived insight from research",
                content_type="insight",
                agent_id="analyst-agent",
                confidence_score=0.85 + (i * 0.03),  # 0.85, 0.88
                derived_from=[source_entry.entry_id],
                analysis_type="quantitative",
            )
            entries.append(entry)

        # Reviewer agent creates 2 entries (one procedural, one decision rationale)
        entry = await bridge.create_knowledge_with_trust(
            content="Procedure: Steps to validate infrastructure claims",
            content_type="procedural",
            agent_id="reviewer-agent",
            confidence_score=0.92,
        )
        entries.append(entry)

        # Create a decision rationale derived from multiple insights
        insight_entries = [e for e in entries if e.content_type.value == "insight"]
        entry = await bridge.create_knowledge_with_trust(
            content="Decision: Approved infrastructure upgrade based on analysis",
            content_type="decision_rationale",
            agent_id="reviewer-agent",
            confidence_score=0.90,
            derived_from=[ie.entry_id for ie in insight_entries],
        )
        entries.append(entry)

        # Verify we have at least 6 entries
        assert len(entries) >= 6, f"Expected at least 6 entries, got {len(entries)}"

        # ========================================
        # Step 3: Query by trust level
        # ========================================

        # High confidence entries (>= 0.9)
        high_confidence = await bridge.query_by_trust_level(min_confidence=0.9)
        assert len(high_confidence) >= 3, (
            "Should have at least 3 high-confidence entries"
        )

        # Medium confidence entries (>= 0.85)
        medium_confidence = await bridge.query_by_trust_level(min_confidence=0.85)
        assert len(medium_confidence) >= len(high_confidence)

        # All entries
        all_entries = await bridge.query_by_trust_level(min_confidence=0.0)
        assert len(all_entries) == len(entries)

        # ========================================
        # Step 4: Query by agent
        # ========================================

        # Research agent entries (should be 2)
        research_entries = await bridge.query_by_agent("research-agent")
        assert len(research_entries) == 2

        # Analyst agent entries (should be 2)
        analyst_entries = await bridge.query_by_agent("analyst-agent")
        assert len(analyst_entries) == 2

        # Reviewer agent entries (should be 2)
        reviewer_entries = await bridge.query_by_agent("reviewer-agent")
        assert len(reviewer_entries) == 2

        # Research agent with derived (should include insights derived from research)
        research_with_derived = await bridge.query_by_agent(
            "research-agent", include_derived=True
        )
        assert len(research_with_derived) > len(research_entries)

        # ========================================
        # Step 5: Verify all knowledge has provenance
        # ========================================

        for entry in entries:
            prov = await provenance_store.get_provenance(entry.entry_id)
            assert prov is not None, f"Entry {entry.entry_id} should have provenance"

            # Verify core PROV relationships exist
            assert ProvRelation.WAS_GENERATED_BY.value in prov.relations
            assert ProvRelation.WAS_ATTRIBUTED_TO.value in prov.relations
            assert ProvRelation.WAS_ASSOCIATED_WITH.value in prov.relations

            # Verify agent attribution
            attributed_to = prov.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]
            assert entry.source_agent_id in attributed_to

        # ========================================
        # Step 6: Export provenance to PROV-JSON
        # ========================================

        # Export the decision rationale (last entry with multiple derivations)
        decision_entry = entries[-1]
        decision_prov = await provenance_store.get_provenance(decision_entry.entry_id)
        prov_json = decision_prov.to_prov_json()

        # Verify W3C PROV-JSON structure
        assert "entity" in prov_json
        assert "activity" in prov_json
        assert "agent" in prov_json
        assert "wasGeneratedBy" in prov_json
        assert "wasAttributedTo" in prov_json
        assert "wasDerivedFrom" in prov_json

        # Verify entity section
        assert decision_entry.entry_id in prov_json["entity"]
        entity = prov_json["entity"][decision_entry.entry_id]
        assert entity["prov:type"] == "KnowledgeEntry"
        assert entity["content_type"] == "decision_rationale"

        # Verify derivation section has multiple sources
        derivations = prov_json["wasDerivedFrom"]
        assert len(derivations) == 2, "Decision should be derived from 2 insights"

        # ========================================
        # Step 7: Assert full traceability
        # ========================================

        # Use ProvenanceChain to traverse full lineage
        chain = ProvenanceChain(provenance_store)
        lineage = await chain.get_lineage(decision_entry.entry_id)

        # Should be able to trace back to original research
        # Decision -> 2 Insights -> 2 Research findings
        # Plus the decision itself = at least 5 entries in lineage
        assert len(lineage) >= 5, f"Expected lineage of at least 5, got {len(lineage)}"

        # Collect all agents in the lineage
        lineage_agents = {l.agent_id for l in lineage}

        # All three agents should be represented in the lineage
        assert "research-agent" in lineage_agents
        assert "analyst-agent" in lineage_agents
        assert "reviewer-agent" in lineage_agents

        # Verify chain integrity
        is_valid = await chain.verify_chain_integrity(decision_entry.entry_id)
        assert is_valid is True, "Chain integrity should be valid"

        # ========================================
        # Final: Trust verification for all entries
        # ========================================

        for entry in entries:
            verification = await bridge.verify_knowledge_trust(entry.entry_id)
            assert verification["valid"] is True, (
                f"Entry {entry.entry_id} should have valid trust: {verification}"
            )
            assert verification["has_trust_operations"] is True
            assert "chain_hash" in verification

    @pytest.mark.asyncio
    async def test_e2e_cross_organization_knowledge(self, trust_infrastructure):
        """
        Test cross-agent knowledge sharing and verification.
        """
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Create two agents
        await trust_ops.establish(
            agent_id="producer-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        await trust_ops.establish(
            agent_id="consumer-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="verify_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Producer creates knowledge
        entry = await bridge.create_knowledge_with_trust(
            content="Cross-org knowledge: API documentation",
            content_type="factual",
            agent_id="producer-agent",
            confidence_score=0.9,
        )

        # Consumer verifies the knowledge
        verification = await bridge.verify_knowledge_trust(entry.entry_id)
        assert verification["valid"] is True

        # Consumer adds verification
        entry.add_verification("consumer-agent")
        await bridge._knowledge_store.update(entry)

        # Query with verifier requirement
        verified_entries = await bridge.query_by_trust_level(
            min_confidence=0.8, min_verifiers=1
        )
        assert len(verified_entries) == 1
        assert "consumer-agent" in verified_entries[0].verified_by

    @pytest.mark.asyncio
    async def test_e2e_knowledge_flagging_workflow(self, trust_infrastructure):
        """
        Test the workflow of detecting and flagging untrusted knowledge.
        """
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Create one trusted agent
        await trust_ops.establish(
            agent_id="trusted-agent",
            authority_id=authority.id,
            capabilities=[
                CapabilityRequest(
                    capability="contribute_knowledge",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create valid knowledge
        valid_entry = await bridge.create_knowledge_with_trust(
            content="Valid knowledge from trusted agent",
            content_type="factual",
            agent_id="trusted-agent",
        )

        # Create invalid knowledge (directly in store, bypassing trust)
        from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType

        invalid_entry = KnowledgeEntry.create(
            content="Suspicious knowledge from unknown source",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="unknown-agent",
            trust_chain_ref="fake-chain",
        )
        await bridge._knowledge_store.store(invalid_entry)

        # Verify valid entry
        valid_result = await bridge.verify_knowledge_trust(valid_entry.entry_id)
        assert valid_result["valid"] is True

        # Verify invalid entry - should fail
        invalid_result = await bridge.verify_knowledge_trust(invalid_entry.entry_id)
        assert invalid_result["valid"] is False

        # Flag the invalid entry
        await bridge.flag_untrusted_knowledge(
            invalid_entry.entry_id, reason=invalid_result["reason"]
        )

        # Verify flagging worked
        flagged = await bridge._knowledge_store.get(invalid_entry.entry_id)
        assert flagged.metadata.get("untrusted") is True
        assert "flagged_at" in flagged.metadata

        # Valid entry should not be flagged
        valid = await bridge._knowledge_store.get(valid_entry.entry_id)
        assert valid.metadata.get("untrusted") is not True

    @pytest.mark.asyncio
    async def test_e2e_provenance_export_complete_graph(self, trust_infrastructure):
        """
        Test exporting a complete provenance graph to PROV-JSON format.
        """
        trust_ops = trust_infrastructure["trust_ops"]
        authority = trust_infrastructure["authority"]

        # Create agents
        for agent_id in ["source-agent", "processor-agent", "aggregator-agent"]:
            await trust_ops.establish(
                agent_id=agent_id,
                authority_id=authority.id,
                capabilities=[
                    CapabilityRequest(
                        capability="contribute_knowledge",
                        capability_type=CapabilityType.ACTION,
                    ),
                ],
            )

        bridge = TrustKnowledgeBridge(
            trust_operations=trust_ops,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

        # Create a complex graph:
        # source-1 ---\
        #              \--> processed --> aggregated
        # source-2 ---/

        source1 = await bridge.create_knowledge_with_trust(
            content="Source data 1",
            content_type="factual",
            agent_id="source-agent",
        )

        source2 = await bridge.create_knowledge_with_trust(
            content="Source data 2",
            content_type="factual",
            agent_id="source-agent",
        )

        processed = await bridge.create_knowledge_with_trust(
            content="Processed data from both sources",
            content_type="insight",
            agent_id="processor-agent",
            derived_from=[source1.entry_id, source2.entry_id],
        )

        aggregated = await bridge.create_knowledge_with_trust(
            content="Final aggregated result",
            content_type="decision_rationale",
            agent_id="aggregator-agent",
            derived_from=[processed.entry_id],
        )

        # Get full lineage from aggregated
        chain = ProvenanceChain(bridge._provenance_store)
        lineage = await chain.get_lineage(aggregated.entry_id)

        # Should have 4 entries: aggregated, processed, source1, source2
        assert len(lineage) == 4

        # Export each provenance record to PROV-JSON
        for record in lineage:
            prov_json = record.to_prov_json()

            # All must have core sections
            assert "entity" in prov_json
            assert "activity" in prov_json
            assert "agent" in prov_json

        # Verify the aggregated entry's PROV-JSON
        agg_prov = await bridge._provenance_store.get_provenance(aggregated.entry_id)
        agg_json = agg_prov.to_prov_json()

        # Should have one derivation (from processed)
        assert len(agg_json["wasDerivedFrom"]) == 1

        # Processed should have two derivations (from source1 and source2)
        proc_prov = await bridge._provenance_store.get_provenance(processed.entry_id)
        proc_json = proc_prov.to_prov_json()
        assert len(proc_json["wasDerivedFrom"]) == 2
