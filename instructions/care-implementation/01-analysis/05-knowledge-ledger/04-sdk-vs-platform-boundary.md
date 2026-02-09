# Knowledge Ledger: SDK vs Platform Boundary

## Executive Summary

This document defines the architectural boundary between what belongs in the Kailash SDK (the developer toolkit) and what belongs in the CARE Platform (the application layer). Getting this boundary wrong leads to either an SDK that's too opinionated (limiting developer freedom) or a platform that's too thin (requiring every implementation to rebuild fundamental capabilities).

**Core Principle**: The SDK provides primitives and data structures. The Platform provides workflows, UI, and business logic.

---

## 1. The Boundary Decision Framework

### 1.1 Decision Criteria

| Criterion                | Belongs in SDK                         | Belongs in Platform           |
| ------------------------ | -------------------------------------- | ----------------------------- |
| **Reusability**          | Useful across many applications        | Specific to CARE application  |
| **Stability**            | Changes infrequently                   | Evolves with requirements     |
| **Abstraction level**    | Data structures, protocols, primitives | Workflows, UI, business rules |
| **Dependency direction** | Platform depends on SDK                | SDK never depends on Platform |
| **Testing**              | Unit-testable in isolation             | Requires integration testing  |
| **Configuration**        | Minimal, convention-based              | Rich, user-configurable       |

### 1.2 The Spectrum

```
SDK (Primitives)                                    Platform (Application)
|                                                                        |
Data Structures -> Query Primitives -> Workflows -> UI -> Analytics
KnowledgeEntry     search()           CRUD flows   Browse  Dashboards
ProvenanceRecord   filter()           Review flows  Search  Reports
ConfidenceLevel    aggregate()        Governance    Edit    Predictions
ContributorRef     link_audit()       Resolution    Thread  Alerts
```

---

## 2. SDK Responsibilities

### 2.1 Knowledge Data Structures

The SDK defines the canonical data types for knowledge management.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/models.py

@dataclass
class KnowledgeEntry:
    """SDK-level knowledge entry data structure."""
    id: str
    title: str
    content: str
    content_type: str  # "fact", "procedure", "decision", "insight", "policy"
    confidence: ConfidenceLevel
    status: str  # "draft", "active", "contested", "archived"
    version: int
    created_by: ContributorReference
    created_at: datetime
    audit_anchor_id: Optional[str]
    # ... (full model as defined in provenance architecture)

@dataclass
class ConfidenceLevel:
    """SDK-level confidence metadata."""
    level: str  # "high", "medium", "low", "uncertain"
    score: float  # 0.0 to 1.0
    basis: str  # "empirical", "expert_judgment", "ai_inference", "consensus"
    evidence_references: List[str]

@dataclass
class ContributorReference:
    """SDK-level contributor reference."""
    agent_id: str
    agent_type: str  # "human", "ai_agent", "system"
    role: str  # "author", "reviewer", "approver", "annotator"
    delegation_record_id: Optional[str]

@dataclass
class KnowledgeEvent:
    """SDK-level knowledge event for event sourcing."""
    event_id: str
    event_type: str
    entry_id: str
    timestamp: datetime
    contributor: ContributorReference
    payload: dict
    audit_anchor_id: str

@dataclass
class KnowledgePerspective:
    """SDK-level perspective for contested knowledge."""
    id: str
    entry_id: str
    contributor: ContributorReference
    content: str
    confidence: ConfidenceLevel
    status: str
```

**Why SDK**: These are reusable data structures that any knowledge-aware application needs, regardless of whether it's the CARE platform or a custom application built on Kailash.

### 2.2 Provenance Schema

The SDK defines the provenance model inspired by W3C PROV-DM.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/provenance.py

@dataclass
class ProvenanceRecord:
    """Links a knowledge entry to its creation context."""
    entry_id: str
    activity: ActivityContext
    contributor: ContributorReference
    derived_from: List[str]  # Source entry IDs
    audit_anchor_id: str

@dataclass
class ActivityContext:
    """W3C PROV-DM Activity equivalent."""
    activity_id: str
    activity_type: str  # "creation", "modification", "review", "contestation"
    workspace_id: Optional[str]
    timestamp: datetime
    trust_context_snapshot: Optional[dict]
```

**Why SDK**: Provenance is a fundamental concept that must be consistent across all implementations. Different platforms may display provenance differently, but the underlying model must be the same.

### 2.3 Trust Chain to Knowledge Bridge

The SDK provides utilities to link EATP trust chains to knowledge entries.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/trust_bridge.py

class TrustKnowledgeBridge:
    """Bridges EATP trust system to knowledge provenance."""

    def link_entry_to_audit(self, entry: KnowledgeEntry, anchor: AuditAnchor) -> None:
        """Link a knowledge entry to its EATP audit anchor."""
        ...

    def verify_entry_provenance(self, entry: KnowledgeEntry) -> ProvenanceVerification:
        """Verify entry's provenance through EATP chain."""
        ...

    def extract_knowledge_from_audit(self, anchor: AuditAnchor) -> Optional[KnowledgeEntry]:
        """Extract knowledge entry from audit anchor metadata."""
        ...

    def create_entry_audit_anchor(self, entry: KnowledgeEntry, activity: ActivityContext) -> AuditAnchor:
        """Generate EATP audit anchor for a knowledge operation."""
        ...
```

**Why SDK**: Trust-knowledge bridging is a technical capability that must be implemented consistently. The alternative---every platform reimplementing this---leads to inconsistent provenance.

### 2.4 Knowledge Query Primitives

The SDK provides basic query capabilities.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/queries.py

class KnowledgeQueryBuilder:
    """Composable query builder for knowledge entries."""

    def filter_by_workspace(self, workspace_id: str) -> 'KnowledgeQueryBuilder': ...
    def filter_by_status(self, status: str) -> 'KnowledgeQueryBuilder': ...
    def filter_by_contributor(self, agent_id: str) -> 'KnowledgeQueryBuilder': ...
    def filter_by_confidence(self, min_score: float) -> 'KnowledgeQueryBuilder': ...
    def filter_by_time_range(self, start: datetime, end: datetime) -> 'KnowledgeQueryBuilder': ...
    def filter_by_category(self, category: str) -> 'KnowledgeQueryBuilder': ...
    def search_text(self, query: str) -> 'KnowledgeQueryBuilder': ...
    def search_semantic(self, query: str, model: str = "default") -> 'KnowledgeQueryBuilder': ...
    def include_provenance(self) -> 'KnowledgeQueryBuilder': ...
    def include_perspectives(self) -> 'KnowledgeQueryBuilder': ...
    def order_by(self, field: str, direction: str = "desc") -> 'KnowledgeQueryBuilder': ...
    def limit(self, n: int) -> 'KnowledgeQueryBuilder': ...
    def execute(self) -> List[KnowledgeEntry]: ...
```

**Why SDK**: Query primitives are composable building blocks. The platform builds specific query patterns from these primitives.

### 2.5 Event Sourcing Infrastructure

The SDK provides the event sourcing foundation.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/events.py

class KnowledgeEventStore:
    """Append-only event store for knowledge changes."""

    async def append(self, event: KnowledgeEvent) -> None: ...
    async def get_events(self, entry_id: str) -> List[KnowledgeEvent]: ...
    async def get_events_by_type(self, event_type: str, time_range: Tuple) -> List[KnowledgeEvent]: ...
    async def replay(self, entry_id: str) -> KnowledgeEntry: ...  # Rebuild from events

class KnowledgeEventHandler(Protocol):
    """Protocol for event handlers."""
    async def handle(self, event: KnowledgeEvent) -> None: ...
```

**Why SDK**: Event sourcing is an infrastructure pattern that should be consistent. Platforms register handlers; the SDK manages the event stream.

### 2.6 DataFlow Model Generation

If using Kailash DataFlow, the SDK provides model definitions that auto-generate CRUD nodes.

**Belongs in SDK**:

```python
# kailash-knowledge/src/knowledge/dataflow_models.py

def register_knowledge_models(db: DataFlow) -> None:
    """Register knowledge models with DataFlow for auto-generated nodes."""

    @db.model
    class KnowledgeEntry:
        id: str = field(primary_key=True)
        title: str
        content: str
        content_type: str
        # ... generates CreateKnowledgeEntry, ReadKnowledgeEntry, etc.

    @db.model
    class KnowledgeContributor:
        id: str = field(primary_key=True)
        entry_id: str
        agent_id: str
        agent_type: str
        # ... generates 11 CRUD nodes
```

**Why SDK**: Model definitions are reusable across platforms. Auto-generated nodes provide consistent data access.

---

## 3. Platform Responsibilities

### 3.1 Knowledge CRUD Workflows

The Platform implements business-logic-rich workflows for knowledge management.

**Belongs in Platform**:

```python
# care-platform/knowledge/workflows.py

async def create_knowledge_entry_workflow(
    title: str, content: str, contributor: ContributorReference,
    workspace_id: str, review_required: bool = True
) -> KnowledgeEntry:
    """Platform workflow for creating knowledge entries."""

    # 1. Validate contributor has permission (EATP check)
    # 2. Create entry via SDK
    # 3. If AI contributor, set status to "draft" and trigger review
    # 4. If review_required, assign reviewer from workspace team
    # 5. Notify relevant team members
    # 6. Generate audit anchor
    # 7. Update workspace knowledge index
    # 8. Trigger embedding generation for semantic search
    ...
```

**Why Platform**: The workflow includes business rules (review requirements, notification logic, workspace-specific behavior) that are application-specific.

### 3.2 Knowledge Review and Approval Workflows

**Belongs in Platform**:

- Review assignment logic (who reviews what)
- Approval workflows (single approver, multi-approver, consensus)
- Notification and escalation
- SLA enforcement (review within N days)
- Auto-assignment based on expertise

### 3.3 Knowledge UI Components

**Belongs in Platform**:

- Knowledge browse/search interface
- Knowledge entry editor (markdown with provenance display)
- Provenance timeline visualization
- Confidence indicator widgets
- Contributor attribution display
- Perspective comparison view
- Discussion thread UI
- Knowledge flow graph visualization

### 3.4 Cross-Functional Knowledge Views

**Belongs in Platform**:

- Workspace knowledge dashboard
- Cross-workspace knowledge flow visualization
- Bridge team knowledge contributions
- Department knowledge landscape
- Knowledge health metrics

### 3.5 Contested Knowledge Resolution Workflows

**Belongs in Platform**:

- Resolution workflow engine (human judgment, consensus, evidence-based)
- Conflict detection and notification
- Resolution history and audit trail
- Escalation to designated authority
- Time-bound resolution enforcement

### 3.6 Knowledge Dashboards and Analytics

**Belongs in Platform**:

- Knowledge creation velocity metrics
- Contributor leaderboard
- Confidence distribution
- Knowledge age and staleness
- Cross-functional sharing metrics
- Decision divergence analytics
- Escalation pattern reports

### 3.7 Tacit Knowledge Detection Algorithms

**Belongs in Platform**:

- Decision divergence pattern detection
- Escalation pattern clustering
- Bridge override analysis
- Constraint adjustment tracking
- Knowledge gap identification algorithms

**Why Platform for all above**: These involve application-specific business logic, UI rendering, user interaction patterns, and analytics that vary between deployments.

---

## 4. The Boundary Line

### 4.1 Visual Boundary

```
+-----------------------------------------------------------------------+
|                        CARE PLATFORM                                   |
|                                                                        |
|  +-------------------+  +-------------------+  +-------------------+  |
|  |  Knowledge UI     |  |  Review Workflows |  |  Analytics        |  |
|  |  - Browse          |  |  - Assignment     |  |  - Dashboards     |  |
|  |  - Search          |  |  - Approval       |  |  - Reports        |  |
|  |  - Edit            |  |  - Notification   |  |  - Predictions    |  |
|  |  - Thread          |  |  - Escalation     |  |  - Alerts         |  |
|  +-------------------+  +-------------------+  +-------------------+  |
|                                                                        |
+============================BOUNDARY====================================+
|                                                                        |
|                        KAILASH SDK                                     |
|                                                                        |
|  +-------------------+  +-------------------+  +-------------------+  |
|  |  Data Structures  |  |  Query Primitives |  |  Event Sourcing   |  |
|  |  - KnowledgeEntry |  |  - QueryBuilder   |  |  - EventStore     |  |
|  |  - Provenance     |  |  - Filters        |  |  - EventHandler   |  |
|  |  - Contributor    |  |  - Search         |  |  - Replay         |  |
|  |  - Confidence     |  |  - Semantic       |  |  - Materialized   |  |
|  +-------------------+  +-------------------+  +-------------------+  |
|                                                                        |
|  +-------------------+  +-------------------+  +-------------------+  |
|  |  Trust Bridge     |  |  DataFlow Models  |  |  Nexus Endpoints  |  |
|  |  - EATP linkage   |  |  - Auto CRUD      |  |  - API routes     |  |
|  |  - Verification   |  |  - Bulk ops       |  |  - MCP tools      |  |
|  |  - Audit gen      |  |  - Queries        |  |  - CLI commands   |  |
|  +-------------------+  +-------------------+  +-------------------+  |
|                                                                        |
+-----------------------------------------------------------------------+
```

### 4.2 Rule of Thumb

Ask these questions to determine where something belongs:

1. **Would a different CARE deployment want this exactly the same way?**
   - Yes -> SDK
   - No -> Platform

2. **Does this involve user interaction or business rules?**
   - Yes -> Platform
   - No -> SDK

3. **Is this a data structure or a workflow?**
   - Data structure -> SDK
   - Workflow -> Platform

4. **Does this need to be consistent across all implementations?**
   - Yes -> SDK
   - No -> Platform

5. **Does this depend on deployment-specific configuration?**
   - Heavy configuration -> Platform
   - Minimal/no configuration -> SDK

---

## 5. Package Structure

### 5.1 SDK Package: `kailash-knowledge`

```
kailash-knowledge/
    src/knowledge/
        __init__.py              # Public API
        models.py                # KnowledgeEntry, ConfidenceLevel, ContributorReference
        provenance.py            # ProvenanceRecord, ActivityContext
        events.py                # KnowledgeEvent, KnowledgeEventStore
        queries.py               # KnowledgeQueryBuilder
        trust_bridge.py          # TrustKnowledgeBridge
        dataflow_models.py       # DataFlow model definitions
        nexus_endpoints.py       # Nexus endpoint registration helpers
        exceptions.py            # Knowledge-specific exceptions
    tests/
        unit/                    # Tier 1: Data structure tests
        integration/             # Tier 2: DataFlow + trust integration
```

**Install**: `pip install kailash-knowledge`
**Dependencies**: `kailash` (Core SDK), optionally `kailash-dataflow`, `kailash-nexus`, `kailash-kaizen`

### 5.2 Platform Package: `care-knowledge`

```
care-knowledge/
    src/care_knowledge/
        __init__.py
        workflows/
            create.py            # Entry creation workflow
            review.py            # Review and approval workflow
            evolve.py            # Version evolution workflow
            contest.py           # Contestation workflow
            resolve.py           # Resolution workflow
        analytics/
            divergence.py        # Decision divergence detection
            escalation.py        # Escalation pattern analysis
            knowledge_gaps.py    # Gap identification
            metrics.py           # Knowledge health metrics
        ui/
            components/          # UI component definitions
            pages/               # Page layouts
            widgets/             # Dashboard widgets
        config/
            governance.py        # Knowledge governance rules
            review_policies.py   # Review assignment policies
```

**Dependencies**: `kailash-knowledge` (SDK package), platform-specific dependencies

---

## 6. API Design at the Boundary

### 6.1 SDK API (Developer-Facing)

```python
from kailash_knowledge import KnowledgeLedger, KnowledgeEntry, ConfidenceLevel

# Initialize
ledger = KnowledgeLedger(db=dataflow_instance, trust_store=trust_store)

# CRUD (simple, no business logic)
entry = await ledger.create(entry_data)
entry = await ledger.read(entry_id)
entry = await ledger.update(entry_id, updates)
await ledger.delete(entry_id)

# Query (composable primitives)
results = await ledger.query().filter_by_workspace("ws-1").search_text("budget").execute()

# Events (subscribe to changes)
ledger.on_event("entry.created", my_handler)

# Trust (provenance verification)
verification = await ledger.verify_provenance(entry_id)
```

### 6.2 Platform API (Application-Facing)

```python
from care_knowledge import KnowledgeManager

# Initialize (wraps SDK with business logic)
manager = KnowledgeManager(
    ledger=ledger,
    review_policy=ReviewPolicy.REQUIRE_FOR_AI,
    governance_rules=governance_config
)

# Business workflows (includes validation, review, notification)
entry = await manager.submit_knowledge(
    title="Q4 Budget Process",
    content="...",
    contributor=current_user,
    workspace=current_workspace,
    # Triggers review workflow if contributor is AI
)

# Analytics (platform-specific)
divergences = await manager.get_decision_divergences(workspace_id, time_range)
health = await manager.get_knowledge_health(workspace_id)
```

---

## 7. Migration and Compatibility

### 7.1 SDK Versioning

- SDK maintains semantic versioning
- Data structure changes follow backward-compatible evolution
- New fields are always optional with defaults
- Deprecated fields remain for at least 2 major versions

### 7.2 Platform Independence

- Multiple platforms can use the same SDK
- Platform A and Platform B share knowledge via SDK data structures
- SDK upgrades do not require platform changes (minor versions)

### 7.3 Extension Points

The SDK provides extension points for platform-specific behavior:

```python
# SDK extension point
class KnowledgeLedger:
    def __init__(self, ..., hooks: Optional[KnowledgeHooks] = None):
        self._hooks = hooks or DefaultHooks()

class KnowledgeHooks(Protocol):
    """Extension points for platform behavior."""
    async def on_entry_created(self, entry: KnowledgeEntry) -> None: ...
    async def on_entry_updated(self, entry: KnowledgeEntry, changes: dict) -> None: ...
    async def on_entry_contested(self, entry: KnowledgeEntry, perspective: KnowledgePerspective) -> None: ...
    async def validate_entry(self, entry: KnowledgeEntry) -> ValidationResult: ...
```

Platforms implement hooks to inject business logic without modifying SDK code.

---

## 8. Summary Decision Table

| Component                      | SDK | Platform | Rationale                            |
| ------------------------------ | --- | -------- | ------------------------------------ |
| KnowledgeEntry dataclass       | X   |          | Reusable data structure              |
| ConfidenceLevel dataclass      | X   |          | Reusable data structure              |
| ContributorReference dataclass | X   |          | Reusable data structure              |
| ProvenanceRecord dataclass     | X   |          | Reusable data structure              |
| KnowledgeEvent dataclass       | X   |          | Reusable data structure              |
| KnowledgeEventStore            | X   |          | Infrastructure primitive             |
| KnowledgeQueryBuilder          | X   |          | Composable query primitive           |
| TrustKnowledgeBridge           | X   |          | Trust integration must be consistent |
| DataFlow model definitions     | X   |          | Auto-generated nodes                 |
| Nexus endpoint helpers         | X   |          | Multi-channel access                 |
| Entry creation workflow        |     | X        | Business rules, notifications        |
| Review/approval workflow       |     | X        | Organization-specific logic          |
| Contestation workflow          |     | X        | Resolution policies vary             |
| Knowledge UI components        |     | X        | UX is application-specific           |
| Decision divergence detection  |     | X        | Analytics algorithms evolve          |
| Escalation pattern analysis    |     | X        | Analytics algorithms evolve          |
| Knowledge dashboards           |     | X        | Metrics vary by deployment           |
| Governance rules               |     | X        | Policies are organization-specific   |
| Review assignment logic        |     | X        | Varies by team structure             |
| Notification system            |     | X        | Channel preferences vary             |
| Knowledge search page          |     | X        | UX is application-specific           |
