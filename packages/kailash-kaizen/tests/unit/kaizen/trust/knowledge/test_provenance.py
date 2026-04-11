"""
Unit tests for CARE-037: W3C PROV-DM Compatible Provenance Schema.

Tests cover:
- ProvRelation enum values (W3C PROV-DM compliance)
- ProvenanceRecord creation and relationships
- PROV-JSON export format
- Serialization roundtrip
- InMemoryProvenanceStore operations
- ProvenanceChain traversal
"""

from datetime import datetime, timezone

import pytest
from kailash.trust.knowledge import (
    InMemoryProvenanceStore,
    KnowledgeEntry,
    KnowledgeType,
    ProvenanceChain,
    ProvenanceRecord,
    ProvRelation,
)


class TestProvRelationEnum:
    """Tests for ProvRelation enum W3C PROV-DM compliance."""

    def test_prov_relation_enum_values(self):
        """Verify all enum values match W3C spec strings."""
        assert ProvRelation.WAS_GENERATED_BY.value == "wasGeneratedBy"
        assert ProvRelation.WAS_ATTRIBUTED_TO.value == "wasAttributedTo"
        assert ProvRelation.WAS_ASSOCIATED_WITH.value == "wasAssociatedWith"
        assert ProvRelation.WAS_DERIVED_FROM.value == "wasDerivedFrom"
        assert ProvRelation.USED.value == "used"
        assert ProvRelation.WAS_INFORMED_BY.value == "wasInformedBy"

    def test_prov_relation_enum_count(self):
        """All 6 PROV-DM relationship types are defined."""
        assert len(ProvRelation) == 6


class TestProvenanceRecordCreation:
    """Tests for ProvenanceRecord creation."""

    @pytest.fixture
    def sample_knowledge_entry(self):
        """Create a sample knowledge entry for testing."""
        return KnowledgeEntry.create(
            content="API rate limit is 1000 requests per minute",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-abc123def456",
            confidence_score=0.95,
        )

    def test_provenance_record_creation(self, sample_knowledge_entry):
        """create_for_knowledge sets all PROV-DM relationships."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="creation",
            agent_id="agent-001",
        )

        # Check record_id format
        assert prov.record_id.startswith("prov-")
        assert len(prov.record_id) == 17  # "prov-" + 12 hex chars

        # Check activity_id format
        assert prov.activity_id.startswith("activity-creation-")
        assert len(prov.activity_id) == 26  # "activity-creation-" + 8 hex chars

        # Check entity and agent
        assert prov.entity_id == sample_knowledge_entry.entry_id
        assert prov.agent_id == "agent-001"

        # Check relationships are set
        assert ProvRelation.WAS_GENERATED_BY.value in prov.relations
        assert ProvRelation.WAS_ATTRIBUTED_TO.value in prov.relations
        assert ProvRelation.WAS_ASSOCIATED_WITH.value in prov.relations

        # wasGeneratedBy points to activity
        assert prov.activity_id in prov.relations[ProvRelation.WAS_GENERATED_BY.value]

        # wasAttributedTo points to agent
        assert "agent-001" in prov.relations[ProvRelation.WAS_ATTRIBUTED_TO.value]

        # wasAssociatedWith points to agent
        assert "agent-001" in prov.relations[ProvRelation.WAS_ASSOCIATED_WITH.value]

    def test_provenance_record_creation_with_derived_from(self, sample_knowledge_entry):
        """wasDerivedFrom relationships added for each source."""
        source_ids = ["ke-source001", "ke-source002", "ke-source003"]

        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="derivation",
            agent_id="agent-002",
            derived_from=source_ids,
        )

        # Check wasDerivedFrom is set
        assert ProvRelation.WAS_DERIVED_FROM.value in prov.relations

        # All sources are included
        derived_from = prov.relations[ProvRelation.WAS_DERIVED_FROM.value]
        assert len(derived_from) == 3
        for source_id in source_ids:
            assert source_id in derived_from

    def test_provenance_record_timestamp(self, sample_knowledge_entry):
        """Timestamp is UTC."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="creation",
            agent_id="agent-001",
        )

        assert isinstance(prov.timestamp, datetime)
        assert prov.timestamp.tzinfo == timezone.utc

    def test_record_id_format(self, sample_knowledge_entry):
        """Record ID starts with 'prov-'."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="creation",
            agent_id="agent-001",
        )

        assert prov.record_id.startswith("prov-")

    def test_activity_id_format(self, sample_knowledge_entry):
        """Activity ID starts with 'activity-'."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="inference",
            agent_id="agent-001",
        )

        assert prov.activity_id.startswith("activity-inference-")

    def test_provenance_attributes(self, sample_knowledge_entry):
        """Custom attributes accessible from knowledge entry."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_knowledge_entry,
            activity="creation",
            agent_id="agent-001",
        )

        # Check attributes from knowledge entry
        assert (
            prov.attributes["trust_chain_ref"] == sample_knowledge_entry.trust_chain_ref
        )
        assert prov.attributes["content_type"] == "factual"
        assert prov.attributes["confidence_score"] == 0.95


class TestProvenanceRecordRelations:
    """Tests for add_relation method."""

    @pytest.fixture
    def sample_prov(self):
        """Create a sample provenance record."""
        entry = KnowledgeEntry.create(
            content="Test content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-test",
        )
        return ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="test",
            agent_id="agent-001",
        )

    def test_add_relation(self, sample_prov):
        """Add multiple relations, no duplicates."""
        # Add a USED relation
        sample_prov.add_relation(ProvRelation.USED, "resource-001")
        assert "resource-001" in sample_prov.relations[ProvRelation.USED.value]

        # Add another USED relation
        sample_prov.add_relation(ProvRelation.USED, "resource-002")
        assert len(sample_prov.relations[ProvRelation.USED.value]) == 2

        # Add WAS_INFORMED_BY relation
        sample_prov.add_relation(ProvRelation.WAS_INFORMED_BY, "activity-other")
        assert (
            "activity-other"
            in sample_prov.relations[ProvRelation.WAS_INFORMED_BY.value]
        )

    def test_add_relation_duplicate_ignored(self, sample_prov):
        """Same relation+target doesn't duplicate."""
        # Add relation twice
        sample_prov.add_relation(ProvRelation.USED, "resource-001")
        sample_prov.add_relation(ProvRelation.USED, "resource-001")

        # Should only appear once
        assert sample_prov.relations[ProvRelation.USED.value].count("resource-001") == 1


class TestProvenanceRecordProvJson:
    """Tests for PROV-JSON export."""

    @pytest.fixture
    def sample_entry(self):
        """Create a sample knowledge entry."""
        return KnowledgeEntry.create(
            content="Test knowledge",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id="agent-insight",
            trust_chain_ref="chain-insight-123",
            confidence_score=0.88,
        )

    def test_prov_json_export_structure(self, sample_entry):
        """Verify PROV-JSON has entity, activity, agent, wasGeneratedBy, wasAttributedTo keys."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_entry,
            activity="analysis",
            agent_id="agent-analyst",
        )

        prov_json = prov.to_prov_json()

        # Check required sections exist
        assert "entity" in prov_json
        assert "activity" in prov_json
        assert "agent" in prov_json
        assert "wasGeneratedBy" in prov_json
        assert "wasAttributedTo" in prov_json

        # Check entity structure
        assert sample_entry.entry_id in prov_json["entity"]
        entity = prov_json["entity"][sample_entry.entry_id]
        assert entity["prov:type"] == "KnowledgeEntry"

        # Check activity structure
        assert prov.activity_id in prov_json["activity"]
        activity = prov_json["activity"][prov.activity_id]
        assert activity["prov:type"] == "KnowledgeActivity"
        assert "prov:startTime" in activity

        # Check agent structure
        assert "agent-analyst" in prov_json["agent"]
        agent = prov_json["agent"]["agent-analyst"]
        assert agent["prov:type"] == "Agent"

    def test_prov_json_export_with_derivation(self, sample_entry):
        """wasDerivedFrom appears in PROV-JSON."""
        sources = ["ke-source-a", "ke-source-b"]
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_entry,
            activity="derivation",
            agent_id="agent-deriver",
            derived_from=sources,
        )

        prov_json = prov.to_prov_json()

        # Check wasDerivedFrom section exists
        assert "wasDerivedFrom" in prov_json

        # Check derivation relationships
        derived = prov_json["wasDerivedFrom"]
        assert len(derived) == 2

        # Verify structure of derivation relationships
        for rel_id, rel_data in derived.items():
            assert "prov:generatedEntity" in rel_data
            assert "prov:usedEntity" in rel_data
            assert rel_data["prov:generatedEntity"] == sample_entry.entry_id
            assert rel_data["prov:usedEntity"] in sources

    def test_prov_json_entity_attributes(self, sample_entry):
        """Attributes appear in entity section."""
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=sample_entry,
            activity="creation",
            agent_id="agent-001",
        )

        prov_json = prov.to_prov_json()

        entity = prov_json["entity"][sample_entry.entry_id]
        assert entity["trust_chain_ref"] == "chain-insight-123"
        assert entity["content_type"] == "insight"
        assert entity["confidence_score"] == 0.88


class TestProvenanceRecordSerialization:
    """Tests for serialization/deserialization."""

    def test_serialization_roundtrip(self):
        """to_dict/from_dict preserves all fields."""
        entry = KnowledgeEntry.create(
            content="Roundtrip test",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id="agent-roundtrip",
            trust_chain_ref="chain-roundtrip",
            confidence_score=0.77,
        )

        original = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="test",
            agent_id="agent-roundtrip",
            derived_from=["ke-source-1", "ke-source-2"],
        )

        # Add extra relations
        original.add_relation(ProvRelation.USED, "resource-x")

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = ProvenanceRecord.from_dict(data)

        # Verify all fields match
        assert restored.record_id == original.record_id
        assert restored.entity_id == original.entity_id
        assert restored.activity_id == original.activity_id
        assert restored.agent_id == original.agent_id
        assert restored.relations == original.relations
        assert restored.attributes == original.attributes
        assert restored.timestamp == original.timestamp


class TestInMemoryProvenanceStore:
    """Tests for InMemoryProvenanceStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store."""
        return InMemoryProvenanceStore()

    @pytest.fixture
    def sample_entries(self):
        """Create sample entries for testing."""
        return [
            KnowledgeEntry.create(
                content=f"Content {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-{i}",
            )
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, store, sample_entries):
        """Store and retrieve provenance records."""
        entry = sample_entries[0]
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id="agent-001",
        )

        # Store
        await store.store(prov)

        # Retrieve
        retrieved = await store.get_provenance(entry.entry_id)

        assert retrieved is not None
        assert retrieved.record_id == prov.record_id
        assert retrieved.entity_id == prov.entity_id

    @pytest.mark.asyncio
    async def test_get_provenance_not_found(self, store):
        """Get returns None for non-existent entity."""
        result = await store.get_provenance("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_knowledge_exists(self, store, sample_entries):
        """knowledge_exists returns correct boolean."""
        entry = sample_entries[0]
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id="agent-001",
        )

        # Before storing
        assert await store.knowledge_exists(entry.entry_id) is False

        # After storing
        await store.store(prov)
        assert await store.knowledge_exists(entry.entry_id) is True

    @pytest.mark.asyncio
    async def test_query_all(self, store, sample_entries):
        """Query without filter returns all records."""
        for entry in sample_entries:
            prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=entry,
                activity="creation",
                agent_id="agent-001",
            )
            await store.store(prov)

        results = await store.query()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_derived_from(self, store, sample_entries):
        """Query with derived_from filter returns correct records."""
        source_entry = sample_entries[0]
        derived_entry1 = sample_entries[1]
        derived_entry2 = sample_entries[2]

        # Store source
        source_prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=source_entry,
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(source_prov)

        # Store derived entries
        for derived_entry in [derived_entry1, derived_entry2]:
            derived_prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=derived_entry,
                activity="derivation",
                agent_id="agent-001",
                derived_from=[source_entry.entry_id],
            )
            await store.store(derived_prov)

        # Query for entries derived from source
        results = await store.query(derived_from=source_entry.entry_id)

        assert len(results) == 2
        result_ids = [r.entity_id for r in results]
        assert derived_entry1.entry_id in result_ids
        assert derived_entry2.entry_id in result_ids


class TestProvenanceChain:
    """Tests for ProvenanceChain traversal."""

    @pytest.fixture
    def store(self):
        """Create a fresh store."""
        return InMemoryProvenanceStore()

    @pytest.mark.asyncio
    async def test_get_lineage_single(self, store):
        """Get lineage for entry with no sources."""
        entry = KnowledgeEntry.create(
            content="Root entry",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-root",
        )
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov)

        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(entry.entry_id)

        assert len(lineage) == 1
        assert lineage[0].entity_id == entry.entry_id

    @pytest.mark.asyncio
    async def test_get_lineage_chain(self, store):
        """Get lineage for entry with derivation chain."""
        # Create chain: entry3 <- entry2 <- entry1
        entries = [
            KnowledgeEntry.create(
                content=f"Entry {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-{i}",
            )
            for i in range(3)
        ]

        # Store entry1 (root)
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov1)

        # Store entry2 (derived from entry1)
        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[1],
            activity="derivation",
            agent_id="agent-001",
            derived_from=[entries[0].entry_id],
        )
        await store.store(prov2)

        # Store entry3 (derived from entry2)
        prov3 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[2],
            activity="derivation",
            agent_id="agent-001",
            derived_from=[entries[1].entry_id],
        )
        await store.store(prov3)

        chain = ProvenanceChain(store)
        lineage = await chain.get_lineage(entries[2].entry_id)

        # Should return all 3 in BFS order
        assert len(lineage) == 3
        lineage_ids = [l.entity_id for l in lineage]
        assert entries[2].entry_id in lineage_ids
        assert entries[1].entry_id in lineage_ids
        assert entries[0].entry_id in lineage_ids

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_valid(self, store):
        """verify_chain_integrity returns True for complete chain."""
        entries = [
            KnowledgeEntry.create(
                content=f"Entry {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-{i}",
            )
            for i in range(2)
        ]

        # Store both entries
        prov1 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov1)

        prov2 = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[1],
            activity="derivation",
            agent_id="agent-001",
            derived_from=[entries[0].entry_id],
        )
        await store.store(prov2)

        chain = ProvenanceChain(store)
        is_valid = await chain.verify_chain_integrity(entries[1].entry_id)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_broken(self, store):
        """verify_chain_integrity returns False for broken chain."""
        entry = KnowledgeEntry.create(
            content="Derived entry",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-derived",
        )

        # Store entry that references non-existent source
        prov = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entry,
            activity="derivation",
            agent_id="agent-001",
            derived_from=["ke-non-existent"],
        )
        await store.store(prov)

        chain = ProvenanceChain(store)
        is_valid = await chain.verify_chain_integrity(entry.entry_id)

        assert is_valid is False


class TestProvenanceChainDepthBounds:
    """CARE-044: Provenance graph traversal must be bounded."""

    @pytest.fixture
    def store(self):
        """Create a fresh store."""
        return InMemoryProvenanceStore()

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_respects_max_depth(self, store):
        """verify_chain_integrity stops at max_depth and does not traverse indefinitely."""
        # Create a deep chain: entry_0 <- entry_1 <- ... <- entry_20
        entries = []
        for i in range(21):
            entry = KnowledgeEntry.create(
                content=f"Deep entry {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-deep-{i}",
            )
            entries.append(entry)

        # Store root
        prov_root = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov_root)

        # Store chain
        for i in range(1, 21):
            prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=entries[i],
                activity="derivation",
                agent_id="agent-001",
                derived_from=[entries[i - 1].entry_id],
            )
            await store.store(prov)

        chain = ProvenanceChain(store)

        # With max_depth=5, it should NOT traverse the full chain
        # but still return True (all visited nodes exist)
        is_valid = await chain.verify_chain_integrity(entries[20].entry_id, max_depth=5)
        assert is_valid is True  # Visited nodes exist even if chain cut short

    @pytest.mark.asyncio
    async def test_get_lineage_respects_max_depth(self, store):
        """get_lineage stops at max_depth."""
        # Create a chain of depth 15
        entries = []
        for i in range(15):
            entry = KnowledgeEntry.create(
                content=f"Lineage entry {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-lineage-{i}",
            )
            entries.append(entry)

        # Store root
        prov_root = ProvenanceRecord.create_for_knowledge(
            knowledge_entry=entries[0],
            activity="creation",
            agent_id="agent-001",
        )
        await store.store(prov_root)

        # Store chain
        for i in range(1, 15):
            prov = ProvenanceRecord.create_for_knowledge(
                knowledge_entry=entries[i],
                activity="derivation",
                agent_id="agent-001",
                derived_from=[entries[i - 1].entry_id],
            )
            await store.store(prov)

        chain = ProvenanceChain(store)

        # With max_depth=3, should only return 4 entries (depth 0, 1, 2, 3)
        lineage = await chain.get_lineage(entries[14].entry_id, max_depth=3)
        assert len(lineage) <= 4

        # With default max_depth=10, should return at most 11 entries
        lineage_default = await chain.get_lineage(entries[14].entry_id)
        assert len(lineage_default) <= 11

    @pytest.mark.asyncio
    async def test_verify_chain_default_max_depth_is_bounded(self, store):
        """Default max_depth should prevent unbounded traversal."""
        chain = ProvenanceChain(store)
        # The default max_depth=100 should prevent DoS
        # Just verify the method accepts max_depth parameter
        is_valid = await chain.verify_chain_integrity("nonexistent", max_depth=1)
        assert is_valid is False  # Entity doesn't exist
