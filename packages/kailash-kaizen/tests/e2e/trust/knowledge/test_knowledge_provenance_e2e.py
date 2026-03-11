"""
E2E tests for CARE-037: W3C PROV-DM Compatible Provenance Schema.

End-to-end tests verify the complete provenance workflow:
- Knowledge creation with trust chains
- Provenance record creation
- PROV-JSON export for interoperability
- Lineage traversal across derivation chains

These tests use REAL infrastructure (NO MOCKING):
- Real trust chain generation with cryptographic signatures
- Real InMemoryProvenanceStore (not mocked)
- Real ProvenanceChain traversal
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


class TestProvJsonExportE2E:
    """E2E tests for PROV-JSON export and validation."""

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
    async def test_e2e_prov_json_export(self, test_keypair, store):
        """
        Create knowledge with provenance, export to PROV-JSON,
        validate structure has all required W3C keys.
        """
        private_key, public_key = test_keypair
        authority_id = "org-e2e-test"
        agent_id = "e2e-agent-001"

        # Step 1: Create real trust chain with cryptographic signatures
        trust_chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge", "derive_knowledge"],
        )

        # Verify trust chain is valid
        verification = trust_chain.verify_basic()
        assert verification.valid is True

        # Step 2: Create source knowledge entry
        source_entry = KnowledgeEntry.create(
            content="E2E Test: Primary data source documentation",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain.hash(),
            confidence_score=0.98,
            metadata={
                "domain": "e2e-testing",
                "version": "1.0",
                "classification": "internal",
            },
        )

        # Validate knowledge entry
        assert source_entry.validate() is True

        # Step 3: Create provenance for source entry
        source_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=source_entry,
            activity="creation",
            agent_id=agent_id,
        )

        # Store provenance
        await store.store(source_prov)

        # Step 4: Create derived knowledge entry
        derived_entry = KnowledgeEntry.create(
            content="E2E Test: Derived analysis from primary source",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain.hash(),
            confidence_score=0.85,
            metadata={
                "domain": "e2e-testing",
                "derived": True,
            },
        )

        # Step 5: Create provenance for derived entry with derivation reference
        derived_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=derived_entry,
            activity="analysis",
            agent_id=agent_id,
            derived_from=[source_entry.entry_id],
        )

        # Store provenance
        await store.store(derived_prov)

        # Step 6: Export to PROV-JSON and validate W3C structure
        prov_json = derived_prov.to_prov_json()

        # Verify all required W3C PROV-JSON keys are present
        assert "entity" in prov_json, "PROV-JSON must have 'entity' section"
        assert "activity" in prov_json, "PROV-JSON must have 'activity' section"
        assert "agent" in prov_json, "PROV-JSON must have 'agent' section"
        assert "wasGeneratedBy" in prov_json, "PROV-JSON must have 'wasGeneratedBy'"
        assert "wasAttributedTo" in prov_json, "PROV-JSON must have 'wasAttributedTo'"
        assert "wasDerivedFrom" in prov_json, "PROV-JSON must have 'wasDerivedFrom'"

        # Verify entity section structure
        entity_section = prov_json["entity"]
        assert derived_entry.entry_id in entity_section
        entity = entity_section[derived_entry.entry_id]
        assert entity["prov:type"] == "KnowledgeEntry"
        assert entity["trust_chain_ref"] == trust_chain.hash()
        assert entity["content_type"] == "insight"
        assert entity["confidence_score"] == 0.85

        # Verify activity section structure
        activity_section = prov_json["activity"]
        assert derived_prov.activity_id in activity_section
        activity = activity_section[derived_prov.activity_id]
        assert activity["prov:type"] == "KnowledgeActivity"
        assert "prov:startTime" in activity

        # Verify agent section structure
        agent_section = prov_json["agent"]
        assert agent_id in agent_section
        agent = agent_section[agent_id]
        assert agent["prov:type"] == "Agent"

        # Verify wasGeneratedBy relationship
        gen_section = prov_json["wasGeneratedBy"]
        assert len(gen_section) == 1
        gen_rel = list(gen_section.values())[0]
        assert gen_rel["prov:entity"] == derived_entry.entry_id
        assert gen_rel["prov:activity"] == derived_prov.activity_id

        # Verify wasAttributedTo relationship
        attr_section = prov_json["wasAttributedTo"]
        assert len(attr_section) == 1
        attr_rel = list(attr_section.values())[0]
        assert attr_rel["prov:entity"] == derived_entry.entry_id
        assert attr_rel["prov:agent"] == agent_id

        # Verify wasDerivedFrom relationship
        der_section = prov_json["wasDerivedFrom"]
        assert len(der_section) == 1
        der_rel = list(der_section.values())[0]
        assert der_rel["prov:generatedEntity"] == derived_entry.entry_id
        assert der_rel["prov:usedEntity"] == source_entry.entry_id

        # Step 7: Verify chain traversal works with stored provenance
        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(derived_entry.entry_id)

        # Should find both entries
        assert len(lineage) == 2
        lineage_ids = [l.entity_id for l in lineage]
        assert derived_entry.entry_id in lineage_ids
        assert source_entry.entry_id in lineage_ids

        # Verify chain integrity
        is_valid = await chain.verify_chain_integrity(derived_entry.entry_id)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_e2e_complex_derivation_graph(self, test_keypair, store):
        """
        Test complex derivation graph with multiple sources.
        """
        private_key, public_key = test_keypair
        authority_id = "org-complex-e2e"
        agent_id = "complex-agent"

        # Create trust chain
        trust_chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge"],
        )

        # Create multiple source entries
        sources = []
        for i in range(3):
            entry = KnowledgeEntry.create(
                content=f"Source {i}: Independent data point",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id=agent_id,
                trust_chain_ref=trust_chain.hash(),
            )
            prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=entry,
                activity="collection",
                agent_id=agent_id,
            )
            await store.store(prov)
            sources.append(entry)

        # Create derived entry from ALL sources
        derived = KnowledgeEntry.create(
            content="Synthesized insight from multiple sources",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain.hash(),
            confidence_score=0.75,
        )
        derived_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=derived,
            activity="synthesis",
            agent_id=agent_id,
            derived_from=[s.entry_id for s in sources],
        )
        await store.store(derived_prov)

        # Export PROV-JSON
        prov_json = derived_prov.to_prov_json()

        # Should have 3 wasDerivedFrom relationships
        assert len(prov_json["wasDerivedFrom"]) == 3

        # All sources should be referenced
        used_entities = [
            rel["prov:usedEntity"] for rel in prov_json["wasDerivedFrom"].values()
        ]
        for source in sources:
            assert source.entry_id in used_entities

        # Verify lineage includes all sources
        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(derived.entry_id)

        assert len(lineage) == 4  # derived + 3 sources

    @pytest.mark.asyncio
    async def test_e2e_serialization_persistence(self, test_keypair, store):
        """
        Test that provenance can be serialized, stored, and restored.
        """
        private_key, public_key = test_keypair
        agent_id = "serial-agent"

        # Create entry and provenance
        entry = KnowledgeEntry.create(
            content="Serialization test data",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref="chain-serial",
            confidence_score=0.99,
        )
        original_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id=agent_id,
        )

        # Serialize to dict (simulating storage)
        serialized = original_prov.to_dict()

        # Deserialize (simulating retrieval)
        restored_prov = ProvenanceRecord.from_dict(serialized)

        # Verify all fields match
        assert restored_prov.record_id == original_prov.record_id
        assert restored_prov.entity_id == original_prov.entity_id
        assert restored_prov.activity_id == original_prov.activity_id
        assert restored_prov.agent_id == original_prov.agent_id
        assert restored_prov.relations == original_prov.relations
        assert restored_prov.attributes == original_prov.attributes
        assert restored_prov.timestamp == original_prov.timestamp

        # Export both to PROV-JSON and compare
        original_json = original_prov.to_prov_json()
        restored_json = restored_prov.to_prov_json()

        # Structure should be identical
        assert original_json.keys() == restored_json.keys()
        assert original_json["entity"] == restored_json["entity"]
        assert original_json["agent"] == restored_json["agent"]
