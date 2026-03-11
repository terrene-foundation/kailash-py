# Trust Knowledge Ledger Guide

This guide covers the Knowledge Ledger features (CARE-036, CARE-037, CARE-038) for the EATP trust system. The Knowledge Ledger enables agents to contribute verified knowledge with full trust chain accountability and complete provenance tracking.

## Overview

The Knowledge Ledger is a structured repository for agent-generated knowledge that maintains full trust provenance. When agents discover facts, develop procedures, or make decisions, they record this knowledge with cryptographic links to their trust chains, enabling verification of both the knowledge and the authority behind it.

| Feature                | CARE ID  | Purpose                                       |
| ---------------------- | -------- | --------------------------------------------- |
| Knowledge Entries      | CARE-036 | Typed knowledge structures with trust refs    |
| PROV-DM Provenance     | CARE-037 | W3C-compliant lineage and derivation tracking |
| Trust-Knowledge Bridge | CARE-038 | Connect trust chains to knowledge operations  |

### Why Knowledge Provenance Matters

Without provenance tracking, agent-generated knowledge lacks accountability:

- Who created this knowledge? Which agent, with what authority?
- Can we trust it? Was the source agent authorized at creation time?
- Where did it come from? Is it derived from other verified knowledge?
- Has trust changed? Is the source agent still trusted?

The Knowledge Ledger answers these questions by linking every knowledge entry to its trust chain and maintaining W3C PROV-DM compatible provenance records.

---

## Knowledge Entry Structures (CARE-036)

### KnowledgeType

Knowledge is categorized by type to enable appropriate handling and querying:

```python
from kaizen.trust.knowledge import KnowledgeType

# Available knowledge types
KnowledgeType.FACTUAL           # Verified facts and data points
KnowledgeType.PROCEDURAL        # Step-by-step procedures and methods
KnowledgeType.TACIT_TRACE       # Implicit knowledge from agent behavior
KnowledgeType.INSIGHT           # Analytical conclusions and interpretations
KnowledgeType.DECISION_RATIONALE # Reasoning behind decisions made
```

**When to use each type:**

| Type               | Use For               | Example                                      |
| ------------------ | --------------------- | -------------------------------------------- |
| FACTUAL            | Verified data points  | "API rate limit is 1000 req/min"             |
| PROCEDURAL         | How-to instructions   | "To deploy: 1. Build, 2. Test, 3. Push"      |
| TACIT_TRACE        | Behavioral patterns   | "Agent prefers JSON over XML for configs"    |
| INSIGHT            | Analysis conclusions  | "Error rates correlate with deployment time" |
| DECISION_RATIONALE | Decision explanations | "Chose PostgreSQL for ACID compliance needs" |

### KnowledgeEntry

A knowledge entry represents a single piece of verified knowledge:

```python
from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType

# Create a knowledge entry using the factory method
entry = KnowledgeEntry.create(
    content="API rate limit is 1000 requests per minute",
    content_type=KnowledgeType.FACTUAL,
    source_agent_id="agent-001",
    trust_chain_ref="chain-abc123",  # Hash of authorizing trust chain
    constraint_envelope_ref="env-xyz789",  # Optional constraint envelope
    confidence_score=0.95,  # 0.0 to 1.0, default 0.8
    metadata={"source": "api-docs", "version": "2.1"},
)

print(f"Entry ID: {entry.entry_id}")  # "ke-a1b2c3d4e5f6"
print(f"Created: {entry.created_at}")
print(f"Verified by: {entry.verified_by}")  # Initially empty
```

### Validation

Entries can be validated to ensure data integrity:

```python
# Validate with exceptions
try:
    entry.validate()
    print("Entry is valid")
except ValueError as e:
    print(f"Validation failed: {e}")

# Validate without exceptions
if entry.is_valid():
    print("Entry is valid")
else:
    print("Entry failed validation")
```

Validation checks:

- `entry_id` starts with "ke-"
- `confidence_score` is between 0.0 and 1.0
- `content` is non-empty
- `source_agent_id` is non-empty
- `trust_chain_ref` is non-empty

### Verification Workflow

Multiple agents can verify a knowledge entry:

```python
# Agent-002 verifies the entry
entry.add_verification("agent-002")

# Agent-003 also verifies
entry.add_verification("agent-003")

# Duplicate verifications are ignored
entry.add_verification("agent-002")  # No effect

print(f"Verified by: {entry.verified_by}")  # ["agent-002", "agent-003"]
```

### Serialization

Entries serialize to JSON-compatible dictionaries:

```python
# Serialize for storage or transmission
data = entry.to_dict()
# {
#   "entry_id": "ke-a1b2c3d4e5f6",
#   "content": "API rate limit is 1000 requests per minute",
#   "content_type": "factual",
#   "source_agent_id": "agent-001",
#   "trust_chain_ref": "chain-abc123",
#   "constraint_envelope_ref": "env-xyz789",
#   "created_at": "2024-01-15T10:30:00+00:00",
#   "verified_by": ["agent-002", "agent-003"],
#   "confidence_score": 0.95,
#   "metadata": {"source": "api-docs", "version": "2.1"}
# }

# Deserialize from stored data
restored = KnowledgeEntry.from_dict(data)
```

### Usage Examples by Type

```python
from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType

# FACTUAL: Verified data point
fact = KnowledgeEntry.create(
    content="Database connection pool max size is 100",
    content_type=KnowledgeType.FACTUAL,
    source_agent_id="config-agent",
    trust_chain_ref="chain-config-001",
    confidence_score=1.0,  # High confidence for config values
)

# PROCEDURAL: Step-by-step procedure
procedure = KnowledgeEntry.create(
    content="Deploy procedure: 1. Run tests, 2. Build image, 3. Push to registry, 4. Update k8s manifest",
    content_type=KnowledgeType.PROCEDURAL,
    source_agent_id="devops-agent",
    trust_chain_ref="chain-devops-001",
    metadata={"last_verified": "2024-01-15"},
)

# INSIGHT: Analytical conclusion
insight = KnowledgeEntry.create(
    content="Response times degrade 15% when pool utilization exceeds 80%",
    content_type=KnowledgeType.INSIGHT,
    source_agent_id="analytics-agent",
    trust_chain_ref="chain-analytics-001",
    confidence_score=0.85,
    metadata={"analysis_period": "30d", "sample_size": 10000},
)

# DECISION_RATIONALE: Why a decision was made
rationale = KnowledgeEntry.create(
    content="Selected PostgreSQL over MySQL for transaction isolation requirements",
    content_type=KnowledgeType.DECISION_RATIONALE,
    source_agent_id="architect-agent",
    trust_chain_ref="chain-architect-001",
    metadata={"decision_id": "arch-2024-001", "stakeholders": ["team-a", "team-b"]},
)

# TACIT_TRACE: Implicit behavioral knowledge
trace = KnowledgeEntry.create(
    content="Agent tends to retry failed API calls 3 times before escalating",
    content_type=KnowledgeType.TACIT_TRACE,
    source_agent_id="observer-agent",
    trust_chain_ref="chain-observer-001",
    confidence_score=0.7,  # Lower confidence for inferred behavior
)
```

---

## W3C PROV-DM Provenance (CARE-037)

The Knowledge Ledger implements W3C PROV-DM (Provenance Data Model) for tracking knowledge lineage. This enables standard-compliant provenance export and interoperability.

### PROV-DM Concepts

W3C PROV-DM defines three core types:

| Type     | Description                               | In Knowledge Ledger            |
| -------- | ----------------------------------------- | ------------------------------ |
| Entity   | Something (physical, digital, conceptual) | Knowledge entries              |
| Activity | Something that occurs over time           | Knowledge creation, derivation |
| Agent    | Something bearing responsibility          | Kaizen agents                  |

And relationships between them:

| Relationship      | Meaning                            | Example                                |
| ----------------- | ---------------------------------- | -------------------------------------- |
| wasGeneratedBy    | Entity was generated by Activity   | Entry was created by creation activity |
| wasAttributedTo   | Entity was attributed to Agent     | Entry was contributed by agent-001     |
| wasAssociatedWith | Activity was associated with Agent | Creation activity done by agent-001    |
| wasDerivedFrom    | Entity was derived from Entity     | Insight derived from facts             |
| used              | Activity used Entity               | Derivation used source entries         |
| wasInformedBy     | Activity was informed by Activity  | Not yet implemented                    |

### ProvRelation Enum

```python
from kaizen.trust.knowledge import ProvRelation

# PROV-DM relationship types
ProvRelation.WAS_GENERATED_BY     # "wasGeneratedBy"
ProvRelation.WAS_ATTRIBUTED_TO    # "wasAttributedTo"
ProvRelation.WAS_ASSOCIATED_WITH  # "wasAssociatedWith"
ProvRelation.WAS_DERIVED_FROM     # "wasDerivedFrom"
ProvRelation.USED                 # "used"
ProvRelation.WAS_INFORMED_BY      # "wasInformedBy"
```

### ProvenanceRecord

Create provenance records for knowledge entries:

```python
from kaizen.trust.knowledge import ProvenanceRecord, KnowledgeEntry, KnowledgeType

# First, create a knowledge entry
entry = KnowledgeEntry.create(
    content="System handles 10,000 concurrent connections",
    content_type=KnowledgeType.FACTUAL,
    source_agent_id="perf-agent",
    trust_chain_ref="chain-perf-001",
)

# Create provenance record for this entry
prov = ProvenanceRecord.create_for_knowledge(
    knowledge_entry=entry,
    activity="creation",  # Type of activity
    agent_id="perf-agent",
    derived_from=None,  # No source entries for original creation
)

print(f"Record ID: {prov.record_id}")       # "prov-a1b2c3d4e5f6"
print(f"Activity ID: {prov.activity_id}")   # "activity-creation-12345678"
print(f"Entity ID: {prov.entity_id}")       # Same as entry.entry_id
```

The factory method automatically sets up PROV-DM relationships:

- `wasGeneratedBy`: links entity to activity
- `wasAttributedTo`: links entity to agent
- `wasAssociatedWith`: links activity to agent
- `wasDerivedFrom`: links to source entities (if provided)

### Derived Knowledge

Track knowledge derived from other entries:

```python
# Source entries (previously created)
source1 = KnowledgeEntry.create(
    content="CPU usage averages 45% under normal load",
    content_type=KnowledgeType.FACTUAL,
    source_agent_id="monitor-agent",
    trust_chain_ref="chain-monitor-001",
)

source2 = KnowledgeEntry.create(
    content="Memory usage averages 60% under normal load",
    content_type=KnowledgeType.FACTUAL,
    source_agent_id="monitor-agent",
    trust_chain_ref="chain-monitor-001",
)

# Derived insight
insight = KnowledgeEntry.create(
    content="System has 40% headroom for traffic spikes",
    content_type=KnowledgeType.INSIGHT,
    source_agent_id="analytics-agent",
    trust_chain_ref="chain-analytics-001",
)

# Create provenance showing derivation
prov = ProvenanceRecord.create_for_knowledge(
    knowledge_entry=insight,
    activity="derivation",
    agent_id="analytics-agent",
    derived_from=[source1.entry_id, source2.entry_id],
)

# Check derivation relationships
sources = prov.relations.get("wasDerivedFrom", [])
print(f"Derived from: {sources}")  # [source1.entry_id, source2.entry_id]
```

### Adding Relations

Add additional relationships to existing records:

```python
from kaizen.trust.knowledge import ProvRelation

# Add a used relationship
prov.add_relation(ProvRelation.USED, "dataset-001")

# Duplicates are ignored
prov.add_relation(ProvRelation.USED, "dataset-001")  # No effect
```

### PROV-JSON Export

Export provenance records in W3C PROV-JSON format for interoperability:

```python
import json

prov_json = prov.to_prov_json()
print(json.dumps(prov_json, indent=2))

# Output:
# {
#   "entity": {
#     "ke-a1b2c3d4e5f6": {
#       "prov:type": "KnowledgeEntry",
#       "trust_chain_ref": "chain-analytics-001",
#       "content_type": "insight",
#       "confidence_score": 0.8
#     }
#   },
#   "activity": {
#     "activity-derivation-12345678": {
#       "prov:type": "KnowledgeActivity",
#       "prov:startTime": "2024-01-15T10:30:00+00:00"
#     }
#   },
#   "agent": {
#     "analytics-agent": {
#       "prov:type": "Agent"
#     }
#   },
#   "wasGeneratedBy": {
#     "_:ke-a1b2c3d4e5f6_gen": {
#       "prov:entity": "ke-a1b2c3d4e5f6",
#       "prov:activity": "activity-derivation-12345678"
#     }
#   },
#   "wasAttributedTo": {
#     "_:ke-a1b2c3d4e5f6_attr": {
#       "prov:entity": "ke-a1b2c3d4e5f6",
#       "prov:agent": "analytics-agent"
#     }
#   },
#   "wasDerivedFrom": {
#     "_:ke-a1b2c3d4e5f6_der_0": {
#       "prov:generatedEntity": "ke-a1b2c3d4e5f6",
#       "prov:usedEntity": "ke-source1-id"
#     },
#     "_:ke-a1b2c3d4e5f6_der_1": {
#       "prov:generatedEntity": "ke-a1b2c3d4e5f6",
#       "prov:usedEntity": "ke-source2-id"
#     }
#   }
# }
```

### ProvenanceChain

Traverse and verify provenance chains:

```python
from kaizen.trust.knowledge import ProvenanceChain, InMemoryProvenanceStore

# Set up provenance store with records
store = InMemoryProvenanceStore()
await store.store(prov_source1)
await store.store(prov_source2)
await store.store(prov_insight)

# Create chain traverser
chain = ProvenanceChain(store)

# Get complete lineage (BFS traversal)
lineage = await chain.get_lineage(insight.entry_id, max_depth=10)
for record in lineage:
    print(f"Entity: {record.entity_id}, Agent: {record.agent_id}")

# Verify chain integrity (all entities exist)
is_valid = await chain.verify_chain_integrity(insight.entry_id)
if is_valid:
    print("All entries in derivation chain exist")
else:
    print("Chain integrity compromised - missing entries")
```

### InMemoryProvenanceStore

For development and testing:

```python
from kaizen.trust.knowledge import InMemoryProvenanceStore

store = InMemoryProvenanceStore()

# Store provenance record
await store.store(prov)

# Retrieve by entity ID
record = await store.get_provenance(entry.entry_id)

# Query all records
all_records = await store.query()

# Query records derived from a specific entity
derived = await store.query(derived_from=source.entry_id)

# Check if entity has provenance
exists = await store.knowledge_exists(entry.entry_id)
```

---

## Trust-Knowledge Bridge (CARE-038)

The `TrustKnowledgeBridge` connects EATP trust operations with knowledge management, enabling trust-verified knowledge creation and trust-aware querying.

### TrustKnowledgeBridge

```python
from kaizen.trust.knowledge import (
    TrustKnowledgeBridge,
    InMemoryKnowledgeStore,
    InMemoryProvenanceStore,
)
from kaizen.trust.operations import TrustOperations

# With full trust operations
bridge = TrustKnowledgeBridge(
    trust_operations=trust_ops,  # TrustOperations instance
    knowledge_store=InMemoryKnowledgeStore(),
    provenance_store=InMemoryProvenanceStore(),
)

# Without trust operations (graceful degradation)
bridge = TrustKnowledgeBridge(
    trust_operations=None,  # Works without trust verification
    knowledge_store=InMemoryKnowledgeStore(),
    provenance_store=InMemoryProvenanceStore(),
)
```

### create_knowledge_with_trust()

Create knowledge entries with automatic trust chain attachment:

```python
# Create knowledge with trust verification
entry = await bridge.create_knowledge_with_trust(
    content="API supports 10,000 concurrent connections",
    content_type="factual",  # String value, not enum
    agent_id="perf-agent",
    confidence_score=0.95,
    derived_from=None,  # Or list of source entry IDs
    source="load-test-2024-01",  # Additional metadata
    test_duration="1h",
)

print(f"Entry ID: {entry.entry_id}")
print(f"Trust chain ref: {entry.trust_chain_ref}")
print(f"Constraint envelope: {entry.constraint_envelope_ref}")
```

When `TrustOperations` is configured:

- Retrieves the agent's current trust chain
- Attaches trust chain hash as `trust_chain_ref`
- Attaches constraint envelope ID if present
- Extracts constraint scope to metadata

When `TrustOperations` is None (graceful degradation):

- Uses `agent_id` as `trust_chain_ref`
- No constraint envelope attached
- Knowledge still created and stored

### Creating Derived Knowledge

```python
# Create derived knowledge with provenance
insight = await bridge.create_knowledge_with_trust(
    content="System can handle 3x current load with 40% headroom",
    content_type="insight",
    agent_id="analytics-agent",
    confidence_score=0.85,
    derived_from=[source1.entry_id, source2.entry_id],
)

# Provenance record automatically created with wasDerivedFrom relations
```

### Trust-Aware Queries

#### Query by Trust Level

```python
# Get highly trusted knowledge
trusted = await bridge.query_by_trust_level(
    min_confidence=0.9,    # Minimum confidence score
    min_verifiers=2,       # Minimum number of verifying agents
    content_type="factual",  # Optional type filter
)

for entry in trusted:
    print(f"{entry.content} (confidence: {entry.confidence_score})")
```

#### Query by Agent

```python
# Get knowledge from a specific agent
agent_knowledge = await bridge.query_by_agent(
    agent_id="analytics-agent",
    include_derived=False,  # Only direct contributions
)

# Include knowledge derived from this agent's entries
with_derived = await bridge.query_by_agent(
    agent_id="analytics-agent",
    include_derived=True,  # Include downstream derivatives
)
```

#### Query by Constraint Scope

```python
# Find knowledge created under specific constraints
scoped = await bridge.query_by_constraint_scope(
    constraint_scope="invoices",  # Partial match on constraint scope
)
```

### verify_knowledge_trust()

Verify that a knowledge entry's trust chain is still valid:

```python
result = await bridge.verify_knowledge_trust(entry.entry_id)

print(f"Valid: {result['valid']}")
print(f"Reason: {result['reason']}")
print(f"Agent: {result['agent_id']}")
print(f"Trust chain ref: {result['trust_chain_ref']}")
print(f"Has trust operations: {result['has_trust_operations']}")

# Full result when trust operations configured and valid:
# {
#   "valid": True,
#   "reason": "Trust chain verification passed",
#   "entry_id": "ke-a1b2c3d4e5f6",
#   "agent_id": "perf-agent",
#   "trust_chain_ref": "hash-abc123",
#   "constraint_envelope_ref": "env-xyz789",
#   "has_trust_operations": True,
#   "chain_hash": "hash-abc123",
#   "capabilities": ["analyze", "report"]
# }
```

Verification checks:

1. Entry exists in knowledge store
2. Source agent has a trust chain (if `TrustOperations` configured)
3. Trust chain is not expired
4. Trust chain hash matches the stored reference

### flag_untrusted_knowledge()

Flag knowledge entries when trust verification fails:

```python
# Flag an entry as untrusted
await bridge.flag_untrusted_knowledge(
    entry_id=entry.entry_id,
    reason="Source agent trust chain expired",
)

# Entry metadata is updated
flagged = await bridge._knowledge_store.get(entry.entry_id)
print(f"Untrusted: {flagged.metadata['untrusted']}")  # True
print(f"Reason: {flagged.metadata['untrusted_reason']}")
print(f"Flagged at: {flagged.metadata['flagged_at']}")
```

### Graceful Degradation

The bridge works without `TrustOperations` for development and testing:

```python
# No trust operations - still functional
bridge = TrustKnowledgeBridge(
    trust_operations=None,
    knowledge_store=InMemoryKnowledgeStore(),
    provenance_store=InMemoryProvenanceStore(),
)

# Creation works (uses agent_id as trust_chain_ref)
entry = await bridge.create_knowledge_with_trust(
    content="Test knowledge",
    content_type="factual",
    agent_id="test-agent",
)

# Verification returns basic validation
result = await bridge.verify_knowledge_trust(entry.entry_id)
print(result["reason"])  # "Basic validation passed (no TrustOperations configured)"
```

### InMemoryKnowledgeStore

For development and testing:

```python
from kaizen.trust.knowledge import InMemoryKnowledgeStore

store = InMemoryKnowledgeStore()

# Store entry
await store.store(entry)

# Retrieve by ID
retrieved = await store.get(entry.entry_id)

# Update entry
entry.add_verification("agent-002")
await store.update(entry)

# Query with filters
factual = await store.query(content_type="factual")
by_agent = await store.query(source_agent_id="perf-agent")
combined = await store.query(content_type="factual", source_agent_id="perf-agent")

# Get all entries
all_entries = await store.get_all()
```

---

## Complete Integration Example

This example demonstrates a complete workflow with multiple agents creating knowledge, establishing derivation chains, and verifying trust:

```python
import asyncio
import json
from kaizen.trust.knowledge import (
    KnowledgeEntry,
    KnowledgeType,
    ProvenanceRecord,
    ProvenanceChain,
    ProvRelation,
    InMemoryKnowledgeStore,
    InMemoryProvenanceStore,
    TrustKnowledgeBridge,
)


async def knowledge_ledger_demo():
    """Demonstrate Knowledge Ledger with multiple agents."""

    # 1. Initialize stores and bridge (without trust operations for demo)
    knowledge_store = InMemoryKnowledgeStore()
    provenance_store = InMemoryProvenanceStore()

    bridge = TrustKnowledgeBridge(
        trust_operations=None,  # Graceful degradation mode
        knowledge_store=knowledge_store,
        provenance_store=provenance_store,
    )

    # 2. Agent 1: Performance Monitor creates factual knowledge
    print("=== Agent 1: Performance Monitor ===")
    cpu_fact = await bridge.create_knowledge_with_trust(
        content="Average CPU utilization is 45% under normal load",
        content_type="factual",
        agent_id="perf-monitor-agent",
        confidence_score=0.98,
        measurement_period="7d",
        sample_count=10080,
    )
    print(f"Created: {cpu_fact.entry_id}")

    memory_fact = await bridge.create_knowledge_with_trust(
        content="Average memory utilization is 62% under normal load",
        content_type="factual",
        agent_id="perf-monitor-agent",
        confidence_score=0.98,
        measurement_period="7d",
        sample_count=10080,
    )
    print(f"Created: {memory_fact.entry_id}")

    # 3. Agent 2: Analytics derives insights from facts
    print("\n=== Agent 2: Analytics Agent ===")
    capacity_insight = await bridge.create_knowledge_with_trust(
        content="System has approximately 38% headroom for traffic spikes based on CPU/memory analysis",
        content_type="insight",
        agent_id="analytics-agent",
        confidence_score=0.85,
        derived_from=[cpu_fact.entry_id, memory_fact.entry_id],
        analysis_method="resource_utilization_projection",
    )
    print(f"Created insight: {capacity_insight.entry_id}")
    print(f"Derived from: {cpu_fact.entry_id}, {memory_fact.entry_id}")

    # 4. Agent 3: Architect creates decision rationale based on insight
    print("\n=== Agent 3: Architect Agent ===")
    decision = await bridge.create_knowledge_with_trust(
        content="Recommend horizontal scaling at 75% average utilization to maintain 25% safety margin",
        content_type="decision_rationale",
        agent_id="architect-agent",
        confidence_score=0.90,
        derived_from=[capacity_insight.entry_id],
        decision_id="arch-2024-scaling-001",
    )
    print(f"Created decision: {decision.entry_id}")

    # 5. Add verifications
    print("\n=== Verification ===")
    cpu_fact.add_verification("qa-agent")
    cpu_fact.add_verification("senior-agent")
    await knowledge_store.update(cpu_fact)
    print(f"CPU fact verified by: {cpu_fact.verified_by}")

    # 6. Query by trust level
    print("\n=== Trust-Level Query ===")
    high_trust = await bridge.query_by_trust_level(
        min_confidence=0.9,
        min_verifiers=1,
    )
    print(f"High-trust entries (confidence >= 0.9, >= 1 verifier): {len(high_trust)}")
    for entry in high_trust:
        print(f"  - {entry.entry_id}: {entry.content[:50]}...")

    # 7. Query by agent with derivatives
    print("\n=== Agent Query with Derivatives ===")
    perf_knowledge = await bridge.query_by_agent(
        agent_id="perf-monitor-agent",
        include_derived=True,
    )
    print(f"Knowledge from perf-monitor-agent (including derivatives): {len(perf_knowledge)}")

    # 8. Verify knowledge trust
    print("\n=== Trust Verification ===")
    verification = await bridge.verify_knowledge_trust(decision.entry_id)
    print(f"Decision trust valid: {verification['valid']}")
    print(f"Reason: {verification['reason']}")

    # 9. Traverse provenance chain
    print("\n=== Provenance Chain ===")
    chain = ProvenanceChain(provenance_store)
    lineage = await chain.get_lineage(decision.entry_id, max_depth=5)
    print(f"Lineage depth: {len(lineage)} records")
    for record in lineage:
        print(f"  Entity: {record.entity_id}")
        print(f"    Agent: {record.agent_id}")
        print(f"    Activity: {record.activity_id}")
        derived = record.relations.get(ProvRelation.WAS_DERIVED_FROM.value, [])
        if derived:
            print(f"    Derived from: {derived}")

    # 10. Verify chain integrity
    print("\n=== Chain Integrity ===")
    integrity = await chain.verify_chain_integrity(decision.entry_id)
    print(f"Chain integrity valid: {integrity}")

    # 11. Export PROV-JSON
    print("\n=== PROV-JSON Export ===")
    decision_prov = await provenance_store.get_provenance(decision.entry_id)
    if decision_prov:
        prov_json = decision_prov.to_prov_json()
        print(json.dumps(prov_json, indent=2, default=str))

    # 12. Flag untrusted knowledge (demonstration)
    print("\n=== Flagging Untrusted Knowledge ===")
    await bridge.flag_untrusted_knowledge(
        entry_id=capacity_insight.entry_id,
        reason="Source agent authorization expired - pending re-verification",
    )
    flagged = await knowledge_store.get(capacity_insight.entry_id)
    print(f"Entry {capacity_insight.entry_id} flagged as untrusted")
    print(f"  Reason: {flagged.metadata.get('untrusted_reason')}")

    print("\n=== Knowledge Ledger Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(knowledge_ledger_demo())
```

---

## API Reference

### Quick Import Reference

```python
from kaizen.trust.knowledge import (
    # CARE-036: Knowledge Entry
    KnowledgeType,
    KnowledgeEntry,
    # CARE-037: Provenance
    ProvRelation,
    ProvenanceRecord,
    ProvenanceChain,
    InMemoryProvenanceStore,
    # CARE-038: Trust Knowledge Bridge
    InMemoryKnowledgeStore,
    TrustKnowledgeBridge,
)
```

### Classes and Methods

| Class                       | Method                                 | Description                                                         |
| --------------------------- | -------------------------------------- | ------------------------------------------------------------------- |
| **KnowledgeType**           |                                        | Enum: FACTUAL, PROCEDURAL, TACIT_TRACE, INSIGHT, DECISION_RATIONALE |
| **KnowledgeEntry**          | `create()`                             | Factory method to create entry with auto-generated ID               |
|                             | `validate()`                           | Validate entry, raises ValueError on failure                        |
|                             | `is_valid()`                           | Validate without exceptions, returns bool                           |
|                             | `add_verification(agent_id)`           | Add verifying agent (no duplicates)                                 |
|                             | `to_dict()`                            | Serialize to JSON-compatible dict                                   |
|                             | `from_dict(data)`                      | Deserialize from dict                                               |
| **ProvRelation**            |                                        | Enum for W3C PROV-DM relationships                                  |
| **ProvenanceRecord**        | `create_for_knowledge()`               | Create provenance for knowledge entry                               |
|                             | `add_relation(relation, target)`       | Add PROV-DM relationship                                            |
|                             | `to_prov_json()`                       | Export to W3C PROV-JSON format                                      |
|                             | `to_dict()`                            | Serialize to dict                                                   |
|                             | `from_dict(data)`                      | Deserialize from dict                                               |
| **ProvenanceChain**         | `get_lineage(entity_id, max_depth)`    | BFS traversal of derivation chain                                   |
|                             | `verify_chain_integrity(entity_id)`    | Verify all entities in chain exist                                  |
| **InMemoryProvenanceStore** | `store(record)`                        | Store provenance record                                             |
|                             | `get_provenance(entity_id)`            | Get record by entity ID                                             |
|                             | `query(derived_from)`                  | Query with optional filter                                          |
|                             | `knowledge_exists(entity_id)`          | Check if entity has provenance                                      |
| **InMemoryKnowledgeStore**  | `store(entry)`                         | Store knowledge entry                                               |
|                             | `get(entry_id)`                        | Get entry by ID                                                     |
|                             | `update(entry)`                        | Update existing entry                                               |
|                             | `query(content_type, source_agent_id)` | Query with filters                                                  |
|                             | `get_all()`                            | Get all entries                                                     |
| **TrustKnowledgeBridge**    | `create_knowledge_with_trust()`        | Create entry with trust verification                                |
|                             | `query_by_trust_level()`               | Query by confidence and verifiers                                   |
|                             | `query_by_agent()`                     | Query by source agent                                               |
|                             | `query_by_constraint_scope()`          | Query by constraint scope                                           |
|                             | `verify_knowledge_trust()`             | Verify entry's trust chain                                          |
|                             | `flag_untrusted_knowledge()`           | Flag entry as untrusted                                             |

---

## See Also

- [Trust Production Readiness Guide](./trust-production-readiness-guide.md) - Key management, revocation, audit
- [Trust Enterprise Features Guide](./trust-enterprise-features-guide.md) - Enterprise trust features
- [EATP Architecture](../architecture/eatp-architecture.md) - Full EATP protocol specification
