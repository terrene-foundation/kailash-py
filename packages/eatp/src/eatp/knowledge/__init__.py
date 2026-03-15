# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-036/037/038: Trust Knowledge Ledger - Knowledge Module.

This module provides knowledge entry structures, W3C PROV-DM compatible
provenance tracking, and trust chain integration for the Trust Knowledge
Ledger, enabling agents to contribute and reference verified knowledge with
full trust chain traceability and complete lineage tracking.

Key Components:
- KnowledgeType: Enum categorizing knowledge types
- KnowledgeEntry: Dataclass for individual knowledge entries
- ProvRelation: W3C PROV-DM relationship types
- ProvenanceRecord: Provenance tracking for knowledge entries
- ProvenanceChain: Lineage traversal and verification
- InMemoryProvenanceStore: In-memory store for testing/development
- InMemoryKnowledgeStore: In-memory store for knowledge entries
- TrustKnowledgeBridge: Bridge between trust operations and knowledge management

Example (Knowledge Entry):
    from eatp.knowledge import KnowledgeEntry, KnowledgeType

    # Create a knowledge entry
    entry = KnowledgeEntry.create(
        content="API rate limit is 1000 requests per minute",
        content_type=KnowledgeType.FACTUAL,
        source_agent_id="agent-001",
        trust_chain_ref="chain-abc123",
    )

    # Validate the entry
    entry.validate()

    # Add verification
    entry.add_verification("agent-002")

    # Serialize for storage
    data = entry.to_dict()

Example (Provenance):
    from eatp.knowledge import (
        ProvenanceRecord,
        ProvRelation,
        ProvenanceChain,
        InMemoryProvenanceStore,
    )

    # Create provenance for a knowledge entry
    prov = ProvenanceRecord.create_for_knowledge(
        knowledge_entry=entry,
        activity="creation",
        agent_id="agent-001",
        derived_from=["ke-source123"],
    )

    # Export to W3C PROV-JSON format
    prov_json = prov.to_prov_json()

    # Store and query provenance
    store = InMemoryProvenanceStore()
    await store.store(prov)

    # Traverse lineage
    chain = ProvenanceChain(store)
    lineage = await chain.get_lineage(entry.entry_id)

Example (Trust Knowledge Bridge):
    from eatp.knowledge import (
        TrustKnowledgeBridge,
        InMemoryKnowledgeStore,
        InMemoryProvenanceStore,
    )

    # Create bridge (with or without trust operations)
    bridge = TrustKnowledgeBridge(
        trust_operations=None,  # Graceful degradation
        knowledge_store=InMemoryKnowledgeStore(),
        provenance_store=InMemoryProvenanceStore(),
    )

    # Create knowledge with trust
    entry = await bridge.create_knowledge_with_trust(
        content="API supports 10,000 concurrent connections",
        content_type="factual",
        agent_id="agent-001",
        confidence_score=0.95,
    )

    # Query by trust level
    trusted = await bridge.query_by_trust_level(min_confidence=0.9)
"""

from eatp.knowledge.bridge import InMemoryKnowledgeStore, TrustKnowledgeBridge
from eatp.knowledge.entry import KnowledgeEntry, KnowledgeType
from eatp.knowledge.provenance import (
    InMemoryProvenanceStore,
    ProvenanceChain,
    ProvenanceRecord,
    ProvRelation,
)

__all__ = [
    # CARE-036: Knowledge Entry
    "KnowledgeType",
    "KnowledgeEntry",
    # CARE-037: Provenance
    "ProvRelation",
    "ProvenanceRecord",
    "ProvenanceChain",
    "InMemoryProvenanceStore",
    # CARE-038: Trust Knowledge Bridge
    "InMemoryKnowledgeStore",
    "TrustKnowledgeBridge",
]
