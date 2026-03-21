# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for reasoning trace support in EATP knowledge modules (TODO-019).

Covers:
- KnowledgeType.DECISION_RATIONALE enum value exists and works
- TrustKnowledgeBridge.reasoning_trace_to_knowledge(): Converts a
  ReasoningTrace to a KnowledgeEntry with provenance information
- The converted entry has proper content_type, content, metadata, and
  provenance linking

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from kailash.trust.knowledge.bridge import InMemoryKnowledgeStore, TrustKnowledgeBridge
from kailash.trust.knowledge.entry import KnowledgeEntry, KnowledgeType
from kailash.trust.knowledge.provenance import InMemoryProvenanceStore, ProvRelation
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace

FIXED_TIMESTAMP = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def knowledge_store() -> InMemoryKnowledgeStore:
    """Fresh in-memory knowledge store."""
    return InMemoryKnowledgeStore()


@pytest.fixture
def provenance_store() -> InMemoryProvenanceStore:
    """Fresh in-memory provenance store."""
    return InMemoryProvenanceStore()


@pytest.fixture
def bridge(
    knowledge_store: InMemoryKnowledgeStore,
    provenance_store: InMemoryProvenanceStore,
) -> TrustKnowledgeBridge:
    """TrustKnowledgeBridge without trust operations (graceful degradation)."""
    return TrustKnowledgeBridge(
        trust_operations=None,
        knowledge_store=knowledge_store,
        provenance_store=provenance_store,
    )


@pytest.fixture
def simple_trace() -> ReasoningTrace:
    """A simple reasoning trace for testing."""
    return ReasoningTrace(
        decision="Delegate financial analysis to agent-gamma",
        rationale="Agent-gamma has specialized financial analysis capabilities and lower cost",
        confidentiality=ConfidentialityLevel.RESTRICTED,
        timestamp=FIXED_TIMESTAMP,
        alternatives_considered=[
            "Use agent-delta (rejected: higher latency)",
            "Process in-house (rejected: lacks capability)",
        ],
        evidence=[
            {
                "type": "capability_check",
                "result": "passed",
                "capability": "financial_analysis",
            },
        ],
        methodology="cost_benefit",
        confidence=0.87,
    )


@pytest.fixture
def confidential_trace() -> ReasoningTrace:
    """A CONFIDENTIAL reasoning trace."""
    return ReasoningTrace(
        decision="Block agent from accessing PII data",
        rationale="Agent lacks GDPR compliance attestation",
        confidentiality=ConfidentialityLevel.CONFIDENTIAL,
        timestamp=FIXED_TIMESTAMP,
        methodology="compliance_check",
        confidence=0.95,
    )


# ===========================================================================
# Test Class 1: DECISION_RATIONALE KnowledgeType
# ===========================================================================


class TestDecisionRationaleKnowledgeType:
    """Tests that DECISION_RATIONALE exists as a KnowledgeType."""

    def test_decision_rationale_exists(self):
        """KnowledgeType must have a DECISION_RATIONALE member."""
        assert hasattr(KnowledgeType, "DECISION_RATIONALE")

    def test_decision_rationale_value(self):
        """DECISION_RATIONALE must have value 'decision_rationale'."""
        assert KnowledgeType.DECISION_RATIONALE.value == "decision_rationale"

    def test_decision_rationale_constructible_from_string(self):
        """Must be constructable from its string value."""
        assert KnowledgeType("decision_rationale") == KnowledgeType.DECISION_RATIONALE

    def test_create_entry_with_decision_rationale(self):
        """KnowledgeEntry can be created with DECISION_RATIONALE type."""
        entry = KnowledgeEntry.create(
            content="Decided to delegate to agent-gamma due to cost efficiency",
            content_type=KnowledgeType.DECISION_RATIONALE,
            source_agent_id="agent-001",
            trust_chain_ref="chain-abc123",
        )
        assert entry.content_type == KnowledgeType.DECISION_RATIONALE
        assert entry.is_valid()


# ===========================================================================
# Test Class 2: TrustKnowledgeBridge.reasoning_trace_to_knowledge()
# ===========================================================================


class TestReasoningTraceToKnowledge:
    """Tests that TrustKnowledgeBridge can convert ReasoningTrace to KnowledgeEntry."""

    @pytest.mark.asyncio
    async def test_method_exists(self, bridge: TrustKnowledgeBridge):
        """Bridge must have a reasoning_trace_to_knowledge() method."""
        assert hasattr(bridge, "reasoning_trace_to_knowledge")
        assert callable(bridge.reasoning_trace_to_knowledge)

    @pytest.mark.asyncio
    async def test_converts_trace_to_entry(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Must convert a ReasoningTrace into a KnowledgeEntry."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert isinstance(entry, KnowledgeEntry)

    @pytest.mark.asyncio
    async def test_entry_has_decision_rationale_type(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Converted entry must have DECISION_RATIONALE content type."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert entry.content_type == KnowledgeType.DECISION_RATIONALE

    @pytest.mark.asyncio
    async def test_entry_content_includes_decision_and_rationale(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Converted entry content must include the decision and rationale."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert simple_trace.decision in entry.content
        assert simple_trace.rationale in entry.content

    @pytest.mark.asyncio
    async def test_entry_has_correct_agent_id(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Converted entry must have the specified source_agent_id."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-gamma",
        )
        assert entry.source_agent_id == "agent-gamma"

    @pytest.mark.asyncio
    async def test_entry_metadata_contains_trace_fields(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Entry metadata must include key reasoning trace fields."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert entry.metadata["confidentiality"] == "restricted"
        assert entry.metadata["methodology"] == "cost_benefit"
        assert entry.metadata["alternatives_considered"] == simple_trace.alternatives_considered
        assert entry.metadata["evidence"] == simple_trace.evidence

    @pytest.mark.asyncio
    async def test_entry_confidence_from_trace(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Entry confidence_score must come from trace.confidence when present."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert entry.confidence_score == 0.87

    @pytest.mark.asyncio
    async def test_entry_confidence_default_when_trace_has_none(
        self,
        bridge: TrustKnowledgeBridge,
    ):
        """Entry confidence_score must use 0.8 default when trace.confidence is None."""
        trace = ReasoningTrace(
            decision="Allow access",
            rationale="Meets all criteria",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=FIXED_TIMESTAMP,
            confidence=None,
        )
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=trace,
            agent_id="agent-001",
        )
        assert entry.confidence_score == 0.8

    @pytest.mark.asyncio
    async def test_entry_is_stored_in_knowledge_store(
        self,
        bridge: TrustKnowledgeBridge,
        knowledge_store: InMemoryKnowledgeStore,
        simple_trace: ReasoningTrace,
    ):
        """Converted entry must be stored in the knowledge store."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        retrieved = await knowledge_store.get(entry.entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id

    @pytest.mark.asyncio
    async def test_provenance_record_created(
        self,
        bridge: TrustKnowledgeBridge,
        provenance_store: InMemoryProvenanceStore,
        simple_trace: ReasoningTrace,
    ):
        """A provenance record must be created for the converted entry."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        prov = await provenance_store.get_provenance(entry.entry_id)
        assert prov is not None
        assert prov.entity_id == entry.entry_id
        assert prov.agent_id == "agent-001"

    @pytest.mark.asyncio
    async def test_provenance_has_creation_activity(
        self,
        bridge: TrustKnowledgeBridge,
        provenance_store: InMemoryProvenanceStore,
        simple_trace: ReasoningTrace,
    ):
        """Provenance record must have wasGeneratedBy relationship."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        prov = await provenance_store.get_provenance(entry.entry_id)
        assert prov is not None
        assert ProvRelation.WAS_GENERATED_BY.value in prov.relations

    @pytest.mark.asyncio
    async def test_derived_from_linked(
        self,
        bridge: TrustKnowledgeBridge,
        provenance_store: InMemoryProvenanceStore,
        simple_trace: ReasoningTrace,
    ):
        """If derived_from is provided, provenance must include wasDerivedFrom."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
            derived_from=["ke-source001", "ke-source002"],
        )
        prov = await provenance_store.get_provenance(entry.entry_id)
        assert prov is not None
        derived = prov.relations.get(ProvRelation.WAS_DERIVED_FROM.value, [])
        assert "ke-source001" in derived
        assert "ke-source002" in derived

    @pytest.mark.asyncio
    async def test_entry_is_valid(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Converted entry must pass validation."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert entry.is_valid()

    @pytest.mark.asyncio
    async def test_queryable_by_decision_rationale_type(
        self,
        bridge: TrustKnowledgeBridge,
        knowledge_store: InMemoryKnowledgeStore,
        simple_trace: ReasoningTrace,
    ):
        """Converted entries must be queryable by content_type='decision_rationale'."""
        await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        results = await knowledge_store.query(content_type="decision_rationale")
        assert len(results) == 1
        assert results[0].content_type == KnowledgeType.DECISION_RATIONALE

    @pytest.mark.asyncio
    async def test_metadata_includes_timestamp(
        self,
        bridge: TrustKnowledgeBridge,
        simple_trace: ReasoningTrace,
    ):
        """Entry metadata must include the reasoning trace timestamp."""
        entry = await bridge.reasoning_trace_to_knowledge(
            trace=simple_trace,
            agent_id="agent-001",
        )
        assert "reasoning_timestamp" in entry.metadata
        assert entry.metadata["reasoning_timestamp"] == FIXED_TIMESTAMP.isoformat()
