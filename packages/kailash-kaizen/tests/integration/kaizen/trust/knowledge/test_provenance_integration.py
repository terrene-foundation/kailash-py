"""
Integration tests for CARE-037: W3C PROV-DM Provenance Schema.

Tests provenance with REAL infrastructure (NO MOCKING).
Uses InMemoryProvenanceStore and real trust chains to verify
provenance integration with knowledge entries.

Note: These tests do NOT require PostgreSQL - they use InMemoryProvenanceStore
for Tier 2 integration testing of provenance with knowledge entries and trust chains.
"""

from datetime import datetime, timedelta, timezone

import pytest
from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.crypto import generate_keypair, sign
from kaizen.trust.knowledge import (
    InMemoryProvenanceStore,
    KnowledgeEntry,
    KnowledgeType,
    ProvenanceChain,
    ProvenanceRecord,
    ProvRelation,
)


class TestKnowledgeCreationProvenance:
    """Integration tests for knowledge creation with provenance."""

    @pytest.fixture
    def test_keypair(self):
        """Generate a test keypair for signing."""
        return generate_keypair()

    @pytest.fixture
    def store(self):
        """Create a fresh provenance store."""
        return InMemoryProvenanceStore()

    def create_trust_chain(
        self,
        agent_id: str,
        authority_id: str,
        private_key: str,
        capabilities: list[str],
    ) -> TrustLineageChain:
        """Create a real trust chain with signed genesis and capabilities."""
        genesis = GenesisRecord(
            id=f"genesis-{agent_id}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": agent_id}, private_key),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )

        attestations = []
        for i, cap in enumerate(capabilities):
            attestation = CapabilityAttestation(
                id=f"cap-{agent_id}-{i}",
                capability=cap,
                capability_type=CapabilityType.ACTION,
                constraints=[],
                attester_id=authority_id,
                attested_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                signature=sign({"capability": cap}, private_key),
            )
            attestations.append(attestation)

        return TrustLineageChain(genesis=genesis, capabilities=attestations)

    @pytest.mark.asyncio
    async def test_knowledge_creation_provenance(self, test_keypair, store):
        """
        Create KnowledgeEntry, create provenance, verify relationships.
        """
        private_key, public_key = test_keypair
        authority_id = "org-integration-test"
        agent_id = "knowledge-creator-001"

        # Create trust chain
        chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge"],
        )

        # Create knowledge entry
        entry = KnowledgeEntry.create(
            content="Integration test: API supports 10,000 concurrent connections",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref=chain.hash(),
            confidence_score=0.92,
            metadata={"domain": "infrastructure", "verified": True},
        )

        # Create provenance for the entry
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id=agent_id,
        )

        # Store provenance
        await store.store(prov)

        # Retrieve and verify
        retrieved = await store.get_provenance(entry.entry_id)
        assert retrieved is not None

        # Verify relationships
        assert ProvRelation.WAS_GENERATED_BY.value in retrieved.relations
        assert ProvRelation.WAS_ATTRIBUTED_TO.value in retrieved.relations
        assert ProvRelation.WAS_ASSOCIATED_WITH.value in retrieved.relations

        # Verify agent attribution
        assert agent_id in retrieved.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]

        # Verify attributes from knowledge entry
        assert retrieved.attributes["trust_chain_ref"] == chain.hash()
        assert retrieved.attributes["content_type"] == "factual"
        assert retrieved.attributes["confidence_score"] == 0.92

    @pytest.mark.asyncio
    async def test_knowledge_derivation_chain(self, test_keypair, store):
        """
        K1 -> K2 -> K3 derivation chain, verify provenance for each.
        """
        private_key, public_key = test_keypair
        authority_id = "org-derivation-test"
        agent_id = "knowledge-deriver-001"

        # Create trust chain
        chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge", "derive_knowledge"],
        )
        trust_ref = chain.hash()

        # Create K1 (root)
        k1 = KnowledgeEntry.create(
            content="Original fact: System uptime target is 99.99%",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref=trust_ref,
            confidence_score=1.0,
        )
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k1,
            activity="creation",
            agent_id=agent_id,
        )
        await store.store(prov1)

        # Create K2 (derived from K1)
        k2 = KnowledgeEntry.create(
            content="Derived: Maximum downtime is 52.56 minutes per year",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id=agent_id,
            trust_chain_ref=trust_ref,
            confidence_score=0.95,
        )
        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k2,
            activity="derivation",
            agent_id=agent_id,
            derived_from=[k1.entry_id],
        )
        await store.store(prov2)

        # Create K3 (derived from K2)
        k3 = KnowledgeEntry.create(
            content="Procedure: Implement health checks every 30 seconds",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id=agent_id,
            trust_chain_ref=trust_ref,
            confidence_score=0.88,
        )
        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k3,
            activity="derivation",
            agent_id=agent_id,
            derived_from=[k2.entry_id],
        )
        await store.store(prov3)

        # Verify K1 has no derived_from
        retrieved1 = await store.get_provenance(k1.entry_id)
        assert ProvRelation.WAS_DERIVED_FROM.value not in retrieved1.relations

        # Verify K2 derives from K1
        retrieved2 = await store.get_provenance(k2.entry_id)
        assert ProvRelation.WAS_DERIVED_FROM.value in retrieved2.relations
        assert k1.entry_id in retrieved2.relations[ProvRelation.WAS_DERIVED_FROM.value]

        # Verify K3 derives from K2
        retrieved3 = await store.get_provenance(k3.entry_id)
        assert ProvRelation.WAS_DERIVED_FROM.value in retrieved3.relations
        assert k2.entry_id in retrieved3.relations[ProvRelation.WAS_DERIVED_FROM.value]


class TestProvenanceChainTraversal:
    """Integration tests for ProvenanceChain traversal."""

    @pytest.fixture
    def store(self):
        """Create a fresh provenance store."""
        return InMemoryProvenanceStore()

    @pytest.mark.asyncio
    async def test_provenance_chain_traversal(self, store):
        """
        Use ProvenanceChain.get_lineage() to traverse K3 back to K1.
        """
        # Create chain: K1 <- K2 <- K3
        entries = []
        for i in range(3):
            entry = KnowledgeEntry.create(
                content=f"Knowledge level {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-chain",
                trust_chain_ref=f"chain-{i}",
            )
            entries.append(entry)

        # Store with derivation relationships
        # K1 (root)
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-chain",
        )
        await store.store(prov1)

        # K2 derives from K1
        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[1],
            activity="derivation",
            agent_id="agent-chain",
            derived_from=[entries[0].entry_id],
        )
        await store.store(prov2)

        # K3 derives from K2
        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[2],
            activity="derivation",
            agent_id="agent-chain",
            derived_from=[entries[1].entry_id],
        )
        await store.store(prov3)

        # Traverse from K3 back to K1
        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(entries[2].entry_id)

        # Should find all 3 entries in BFS order
        assert len(lineage) == 3

        lineage_ids = [l.entity_id for l in lineage]
        # K3 should be first (starting point)
        assert lineage_ids[0] == entries[2].entry_id
        # K2 should be second (derived from)
        assert lineage_ids[1] == entries[1].entry_id
        # K1 should be third (root)
        assert lineage_ids[2] == entries[0].entry_id

    @pytest.mark.asyncio
    async def test_provenance_chain_integrity_valid(self, store):
        """
        verify_chain_integrity returns True for complete chain.
        """
        # Create complete chain
        entries = []
        for i in range(3):
            entry = KnowledgeEntry.create(
                content=f"Verified knowledge {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-verified",
                trust_chain_ref=f"chain-verified-{i}",
            )
            entries.append(entry)

        # Store all with derivation
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-verified",
        )
        await store.store(prov1)

        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[1],
            activity="derivation",
            agent_id="agent-verified",
            derived_from=[entries[0].entry_id],
        )
        await store.store(prov2)

        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[2],
            activity="derivation",
            agent_id="agent-verified",
            derived_from=[entries[1].entry_id],
        )
        await store.store(prov3)

        # Verify chain integrity
        chain = ProvenanceChain(store)
        is_valid = await chain.verify_chain_integrity(entries[2].entry_id)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_provenance_chain_integrity_broken(self, store):
        """
        Remove middle entry, verify_chain_integrity returns False.
        """
        # Create entries but don't store the middle one
        k1 = KnowledgeEntry.create(
            content="Root knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-broken",
            trust_chain_ref="chain-broken-1",
        )

        k2 = KnowledgeEntry.create(
            content="Middle knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-broken",
            trust_chain_ref="chain-broken-2",
        )

        k3 = KnowledgeEntry.create(
            content="End knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-broken",
            trust_chain_ref="chain-broken-3",
        )

        # Store K1 (root)
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k1,
            activity="creation",
            agent_id="agent-broken",
        )
        await store.store(prov1)

        # Skip K2 (don't store it)

        # Store K3 with reference to non-existent K2
        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k3,
            activity="derivation",
            agent_id="agent-broken",
            derived_from=[k2.entry_id],  # K2 doesn't exist in store
        )
        await store.store(prov3)

        # Verify chain integrity - should fail
        chain = ProvenanceChain(store)
        is_valid = await chain.verify_chain_integrity(k3.entry_id)

        assert is_valid is False


class TestProvenanceStoreQuery:
    """Integration tests for InMemoryProvenanceStore.query()."""

    @pytest.fixture
    def store(self):
        """Create a fresh provenance store."""
        return InMemoryProvenanceStore()

    @pytest.mark.asyncio
    async def test_provenance_store_query_derived(self, store):
        """
        InMemoryProvenanceStore.query(derived_from=...) returns correct records.
        """
        # Create source entry
        source = KnowledgeEntry.create(
            content="Source knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-source",
            trust_chain_ref="chain-source",
        )
        source_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=source,
            activity="creation",
            agent_id="agent-source",
        )
        await store.store(source_prov)

        # Create multiple derived entries from the same source
        derived_entries = []
        for i in range(3):
            derived = KnowledgeEntry.create(
                content=f"Derived {i}",
                content_type=KnowledgeType.INSIGHT,
                source_agent_id="agent-deriver",
                trust_chain_ref=f"chain-derived-{i}",
            )
            derived_entries.append(derived)

            derived_prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=derived,
                activity="derivation",
                agent_id="agent-deriver",
                derived_from=[source.entry_id],
            )
            await store.store(derived_prov)

        # Create another entry NOT derived from source
        unrelated = KnowledgeEntry.create(
            content="Unrelated knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-other",
            trust_chain_ref="chain-unrelated",
        )
        unrelated_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=unrelated,
            activity="creation",
            agent_id="agent-other",
        )
        await store.store(unrelated_prov)

        # Query for entries derived from source
        results = await store.query(derived_from=source.entry_id)

        # Should find exactly 3 derived entries
        assert len(results) == 3

        result_ids = [r.entity_id for r in results]
        for derived in derived_entries:
            assert derived.entry_id in result_ids

        # Source and unrelated should NOT be in results
        assert source.entry_id not in result_ids
        assert unrelated.entry_id not in result_ids

    @pytest.mark.asyncio
    async def test_provenance_store_query_no_results(self, store):
        """
        Query with non-existent derived_from returns empty list.
        """
        # Store some entries
        entry = KnowledgeEntry.create(
            content="Some knowledge",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-001",
        )
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov)

        # Query for non-existent source
        results = await store.query(derived_from="ke-non-existent")

        assert len(results) == 0


class TestMultiAgentProvenance:
    """Integration tests for multi-agent provenance scenarios."""

    @pytest.fixture
    def store(self):
        """Create a fresh provenance store."""
        return InMemoryProvenanceStore()

    @pytest.mark.asyncio
    async def test_multi_agent_derivation(self, store):
        """
        Multiple agents contribute to a derivation chain.
        """
        # Agent A creates initial knowledge
        k1 = KnowledgeEntry.create(
            content="Agent A: Initial discovery",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-a",
            trust_chain_ref="chain-a",
        )
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k1,
            activity="discovery",
            agent_id="agent-a",
        )
        await store.store(prov1)

        # Agent B derives insight from Agent A's knowledge
        k2 = KnowledgeEntry.create(
            content="Agent B: Derived insight",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id="agent-b",
            trust_chain_ref="chain-b",
        )
        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k2,
            activity="analysis",
            agent_id="agent-b",
            derived_from=[k1.entry_id],
        )
        await store.store(prov2)

        # Agent C creates procedure based on Agent B's insight
        k3 = KnowledgeEntry.create(
            content="Agent C: Implementation procedure",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id="agent-c",
            trust_chain_ref="chain-c",
        )
        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=k3,
            activity="synthesis",
            agent_id="agent-c",
            derived_from=[k2.entry_id],
        )
        await store.store(prov3)

        # Verify each agent is properly attributed
        retrieved1 = await store.get_provenance(k1.entry_id)
        assert "agent-a" in retrieved1.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]

        retrieved2 = await store.get_provenance(k2.entry_id)
        assert "agent-b" in retrieved2.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]

        retrieved3 = await store.get_provenance(k3.entry_id)
        assert "agent-c" in retrieved3.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]

        # Verify full lineage
        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(k3.entry_id)

        assert len(lineage) == 3
        agents = [l.agent_id for l in lineage]
        assert "agent-a" in agents
        assert "agent-b" in agents
        assert "agent-c" in agents
