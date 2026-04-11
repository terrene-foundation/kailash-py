"""
Unit tests for CARE-038: Trust-Chain-to-Knowledge Bridge.

Tests cover:
- InMemoryKnowledgeStore operations
- TrustKnowledgeBridge creation without TrustOperations (graceful degradation)
- Knowledge creation with automatic provenance
- Trust level filtering
- Agent-based queries (with and without derived knowledge)
- Trust verification
- Untrusted knowledge flagging
- Constraint scope queries

NO MOCKING - uses InMemoryKnowledgeStore and InMemoryProvenanceStore.
"""

from datetime import datetime, timezone

import pytest
from kailash.trust.knowledge import (
    InMemoryKnowledgeStore,
    InMemoryProvenanceStore,
    KnowledgeEntry,
    KnowledgeType,
    ProvenanceRecord,
    ProvRelation,
    TrustKnowledgeBridge,
)


class TestInMemoryKnowledgeStore:
    """Tests for InMemoryKnowledgeStore operations."""

    @pytest.fixture
    def store(self):
        """Create a fresh knowledge store."""
        return InMemoryKnowledgeStore()

    @pytest.mark.asyncio
    async def test_store_and_get(self, store):
        """Store and retrieve a knowledge entry."""
        entry = KnowledgeEntry.create(
            content="Test content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-test",
        )

        await store.store(entry)
        retrieved = await store.get(entry.entry_id)

        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id
        assert retrieved.content == "Test content"

    @pytest.mark.asyncio
    async def test_get_not_found(self, store):
        """Get returns None for non-existent entry."""
        result = await store.get("non-existent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update(self, store):
        """Update modifies existing entry."""
        entry = KnowledgeEntry.create(
            content="Original content",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-test",
        )
        await store.store(entry)

        # Modify and update
        entry.metadata["updated"] = True
        await store.update(entry)

        retrieved = await store.get(entry.entry_id)
        assert retrieved.metadata.get("updated") is True

    @pytest.mark.asyncio
    async def test_query_by_content_type(self, store):
        """Query filters by content type."""
        factual = KnowledgeEntry.create(
            content="Fact",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-1",
        )
        insight = KnowledgeEntry.create(
            content="Insight",
            content_type=KnowledgeType.INSIGHT,
            source_agent_id="agent-001",
            trust_chain_ref="chain-2",
        )

        await store.store(factual)
        await store.store(insight)

        results = await store.query(content_type="factual")
        assert len(results) == 1
        assert results[0].entry_id == factual.entry_id

    @pytest.mark.asyncio
    async def test_query_by_source_agent(self, store):
        """Query filters by source agent ID."""
        entry1 = KnowledgeEntry.create(
            content="Content 1",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-001",
            trust_chain_ref="chain-1",
        )
        entry2 = KnowledgeEntry.create(
            content="Content 2",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id="agent-002",
            trust_chain_ref="chain-2",
        )

        await store.store(entry1)
        await store.store(entry2)

        results = await store.query(source_agent_id="agent-001")
        assert len(results) == 1
        assert results[0].entry_id == entry1.entry_id

    @pytest.mark.asyncio
    async def test_get_all(self, store):
        """get_all returns all entries."""
        for i in range(5):
            entry = KnowledgeEntry.create(
                content=f"Content {i}",
                content_type=KnowledgeType.FACTUAL,
                source_agent_id="agent-001",
                trust_chain_ref=f"chain-{i}",
            )
            await store.store(entry)

        all_entries = await store.get_all()
        assert len(all_entries) == 5


class TestTrustKnowledgeBridgeWithoutTrustOps:
    """Tests for TrustKnowledgeBridge without TrustOperations."""

    @pytest.fixture
    def bridge(self):
        """Create bridge without TrustOperations."""
        return TrustKnowledgeBridge(
            trust_operations=None,
            knowledge_store=InMemoryKnowledgeStore(),
            provenance_store=InMemoryProvenanceStore(),
        )

    @pytest.mark.asyncio
    async def test_create_knowledge_without_trust_ops(self, bridge):
        """TrustOperations=None, creates entry with agent_id as trust_chain_ref."""
        entry = await bridge.create_knowledge_with_trust(
            content="Test knowledge",
            content_type="factual",
            agent_id="agent-001",
            confidence_score=0.9,
        )

        assert entry is not None
        assert entry.entry_id.startswith("ke-")
        assert entry.content == "Test knowledge"
        assert entry.source_agent_id == "agent-001"
        # Without trust ops, trust_chain_ref should be agent_id
        assert entry.trust_chain_ref == "agent-001"
        assert entry.constraint_envelope_ref is None

    @pytest.mark.asyncio
    async def test_create_knowledge_stores_entry(self, bridge):
        """After create, entry is retrievable from store."""
        entry = await bridge.create_knowledge_with_trust(
            content="Stored knowledge",
            content_type="insight",
            agent_id="agent-002",
        )

        # Retrieve from store
        retrieved = await bridge._knowledge_store.get(entry.entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id
        assert retrieved.content == "Stored knowledge"

    @pytest.mark.asyncio
    async def test_create_knowledge_creates_provenance(self, bridge):
        """After create, provenance record exists."""
        entry = await bridge.create_knowledge_with_trust(
            content="Knowledge with provenance",
            content_type="procedural",
            agent_id="agent-003",
        )

        # Check provenance exists
        prov = await bridge._provenance_store.get_provenance(entry.entry_id)
        assert prov is not None
        assert prov.entity_id == entry.entry_id
        assert prov.agent_id == "agent-003"
        assert ProvRelation.WAS_GENERATED_BY.value in prov.relations

    @pytest.mark.asyncio
    async def test_query_by_trust_level_filters_confidence(self, bridge):
        """Query min_confidence=0.9 returns only high confidence entries."""
        # Create 5 entries with varying confidence
        confidences = [0.7, 0.8, 0.85, 0.9, 0.95]
        for i, conf in enumerate(confidences):
            await bridge.create_knowledge_with_trust(
                content=f"Knowledge {i}",
                content_type="factual",
                agent_id="agent-001",
                confidence_score=conf,
            )

        # Query with min_confidence=0.9
        results = await bridge.query_by_trust_level(min_confidence=0.9)

        assert len(results) == 2  # 0.9 and 0.95
        for entry in results:
            assert entry.confidence_score >= 0.9

    @pytest.mark.asyncio
    async def test_query_by_trust_level_filters_verifiers(self, bridge):
        """Entries with verifiers vs without, min_verifiers filter works."""
        # Create entries with different verifier counts
        entry1 = await bridge.create_knowledge_with_trust(
            content="No verifiers",
            content_type="factual",
            agent_id="agent-001",
        )

        entry2 = await bridge.create_knowledge_with_trust(
            content="Two verifiers",
            content_type="factual",
            agent_id="agent-001",
        )
        # Add verifiers
        entry2.add_verification("verifier-1")
        entry2.add_verification("verifier-2")
        await bridge._knowledge_store.update(entry2)

        entry3 = await bridge.create_knowledge_with_trust(
            content="One verifier",
            content_type="factual",
            agent_id="agent-001",
        )
        entry3.add_verification("verifier-1")
        await bridge._knowledge_store.update(entry3)

        # Query with min_verifiers=2
        results = await bridge.query_by_trust_level(min_confidence=0.0, min_verifiers=2)

        assert len(results) == 1
        assert results[0].entry_id == entry2.entry_id

    @pytest.mark.asyncio
    async def test_query_by_trust_level_filters_content_type(self, bridge):
        """content_type filter works in query_by_trust_level."""
        await bridge.create_knowledge_with_trust(
            content="Factual 1",
            content_type="factual",
            agent_id="agent-001",
            confidence_score=0.9,
        )
        await bridge.create_knowledge_with_trust(
            content="Insight 1",
            content_type="insight",
            agent_id="agent-001",
            confidence_score=0.9,
        )
        await bridge.create_knowledge_with_trust(
            content="Factual 2",
            content_type="factual",
            agent_id="agent-001",
            confidence_score=0.9,
        )

        results = await bridge.query_by_trust_level(
            min_confidence=0.8, content_type="factual"
        )

        assert len(results) == 2
        for entry in results:
            assert entry.content_type == KnowledgeType.FACTUAL

    @pytest.mark.asyncio
    async def test_query_by_agent_basic(self, bridge):
        """Agent A creates 3, Agent B creates 2, query agent A returns 3."""
        # Agent A creates 3 entries
        for i in range(3):
            await bridge.create_knowledge_with_trust(
                content=f"Agent A knowledge {i}",
                content_type="factual",
                agent_id="agent-a",
            )

        # Agent B creates 2 entries
        for i in range(2):
            await bridge.create_knowledge_with_trust(
                content=f"Agent B knowledge {i}",
                content_type="factual",
                agent_id="agent-b",
            )

        # Query agent A
        results = await bridge.query_by_agent("agent-a")

        assert len(results) == 3
        for entry in results:
            assert entry.source_agent_id == "agent-a"

    @pytest.mark.asyncio
    async def test_query_by_agent_with_derived(self, bridge):
        """K1 by agent A, K2 derived from K1 by agent B, query agent A include_derived=True returns both."""
        # Agent A creates K1
        k1 = await bridge.create_knowledge_with_trust(
            content="Original from Agent A",
            content_type="factual",
            agent_id="agent-a",
        )

        # Agent B creates K2 derived from K1
        k2 = await bridge.create_knowledge_with_trust(
            content="Derived by Agent B",
            content_type="insight",
            agent_id="agent-b",
            derived_from=[k1.entry_id],
        )

        # Query agent A with include_derived=True
        results = await bridge.query_by_agent("agent-a", include_derived=True)

        assert len(results) == 2
        result_ids = {e.entry_id for e in results}
        assert k1.entry_id in result_ids
        assert k2.entry_id in result_ids

    @pytest.mark.asyncio
    async def test_verify_knowledge_trust_no_trust_ops(self, bridge):
        """Without TrustOperations, returns valid with basic info."""
        entry = await bridge.create_knowledge_with_trust(
            content="Test entry",
            content_type="factual",
            agent_id="agent-001",
        )

        result = await bridge.verify_knowledge_trust(entry.entry_id)

        assert result["valid"] is True
        assert "Basic validation passed" in result["reason"]
        assert result["has_trust_operations"] is False
        assert result["agent_id"] == "agent-001"

    @pytest.mark.asyncio
    async def test_verify_knowledge_trust_not_found(self, bridge):
        """Non-existent entry returns valid=False."""
        result = await bridge.verify_knowledge_trust("ke-non-existent")

        assert result["valid"] is False
        assert "not found" in result["reason"]

    @pytest.mark.asyncio
    async def test_flag_untrusted_knowledge(self, bridge):
        """Flag entry, verify metadata updated."""
        entry = await bridge.create_knowledge_with_trust(
            content="Potentially untrusted",
            content_type="factual",
            agent_id="agent-001",
        )

        await bridge.flag_untrusted_knowledge(
            entry.entry_id, reason="Failed verification"
        )

        # Retrieve and check metadata
        flagged = await bridge._knowledge_store.get(entry.entry_id)
        assert flagged.metadata.get("untrusted") is True
        assert flagged.metadata.get("untrusted_reason") == "Failed verification"
        assert "flagged_at" in flagged.metadata

    @pytest.mark.asyncio
    async def test_flag_untrusted_knowledge_not_found(self, bridge):
        """Flag non-existent entry does not raise error."""
        # Should not raise
        await bridge.flag_untrusted_knowledge("ke-non-existent", reason="Test reason")

    @pytest.mark.asyncio
    async def test_create_knowledge_with_metadata(self, bridge):
        """Custom metadata preserved in entry."""
        entry = await bridge.create_knowledge_with_trust(
            content="Knowledge with metadata",
            content_type="factual",
            agent_id="agent-001",
            domain="infrastructure",
            priority="high",
            verified=True,
        )

        assert entry.metadata.get("domain") == "infrastructure"
        assert entry.metadata.get("priority") == "high"
        assert entry.metadata.get("verified") is True

    @pytest.mark.asyncio
    async def test_create_knowledge_derived_from(self, bridge):
        """derived_from creates proper provenance relationship."""
        # Create source entry
        source = await bridge.create_knowledge_with_trust(
            content="Source knowledge",
            content_type="factual",
            agent_id="agent-001",
        )

        # Create derived entry
        derived = await bridge.create_knowledge_with_trust(
            content="Derived knowledge",
            content_type="insight",
            agent_id="agent-002",
            derived_from=[source.entry_id],
        )

        # Check provenance has wasDerivedFrom
        prov = await bridge._provenance_store.get_provenance(derived.entry_id)
        assert ProvRelation.WAS_DERIVED_FROM.value in prov.relations
        assert source.entry_id in prov.relations[ProvRelation.WAS_DERIVED_FROM.value]

    @pytest.mark.asyncio
    async def test_query_by_constraint_scope(self, bridge):
        """Entries with matching scope returned."""
        # Create entries with different constraint scopes
        entry1 = await bridge.create_knowledge_with_trust(
            content="Financial data",
            content_type="factual",
            agent_id="agent-001",
            constraint_scope="finance;read_only",
        )

        entry2 = await bridge.create_knowledge_with_trust(
            content="HR data",
            content_type="factual",
            agent_id="agent-001",
            constraint_scope="hr;confidential",
        )

        entry3 = await bridge.create_knowledge_with_trust(
            content="Public data",
            content_type="factual",
            agent_id="agent-001",
        )

        # Query for finance scope
        results = await bridge.query_by_constraint_scope("finance")

        assert len(results) == 1
        assert results[0].entry_id == entry1.entry_id

    @pytest.mark.asyncio
    async def test_create_knowledge_invalid_content_type(self, bridge):
        """Invalid content_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await bridge.create_knowledge_with_trust(
                content="Test",
                content_type="invalid_type",
                agent_id="agent-001",
            )

        assert "Invalid content_type" in str(exc_info.value)
