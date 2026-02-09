# Knowledge Ledger: Provenance Architecture

## Executive Summary

This document defines the provenance architecture for the Knowledge Ledger---the data model, EATP integration points, schema design, and relationship patterns that enable trustworthy organizational knowledge management. The architecture is inspired by W3C PROV-DM (Entity, Activity, Agent) and grounded in the EATP audit infrastructure already implemented in the Kailash SDK.

**Core Principle**: "Knowledge is flat. Authority is hierarchical." The provenance model tracks who contributed what, with what confidence, under what authority---without privileging any single contributor type.

---

## 1. Conceptual Model

### 1.1 W3C PROV-DM Mapping

The Knowledge Ledger maps directly to the W3C Provenance Data Model:

| PROV-DM Concept       | Knowledge Ledger Equivalent  | Description                                       |
| --------------------- | ---------------------------- | ------------------------------------------------- |
| **Entity**            | Knowledge Entry              | A piece of organizational knowledge               |
| **Activity**          | Knowledge Activity           | An action that creates/modifies/reviews knowledge |
| **Agent**             | Contributor                  | Human or AI agent contributing to knowledge       |
| **wasGeneratedBy**    | Entry.created_by_activity    | Links entry to creating activity                  |
| **wasAttributedTo**   | Entry.contributors           | Links entry to contributing agents                |
| **wasDerivedFrom**    | Entry.derived_from           | Links entry to source entries                     |
| **wasAssociatedWith** | Activity.agent               | Links activity to performing agent                |
| **actedOnBehalfOf**   | Contributor.delegation_chain | Links agent to delegating authority               |

### 1.2 Knowledge Entry Lifecycle

```
                   CREATE
                     |
                     v
    +----------------------------------+
    |        KNOWLEDGE ENTRY           |
    |  status: draft                   |
    +----------------------------------+
                     |
              REVIEW / APPROVE
                     |
                     v
    +----------------------------------+
    |        KNOWLEDGE ENTRY           |
    |  status: active                  |
    +----------------------------------+
          |              |              |
     EVOLVE          CONTEST         ARCHIVE
          |              |              |
          v              v              v
    +-----------+  +-----------+  +-----------+
    | version N |  | contested |  | archived  |
    +-----------+  +-----------+  +-----------+
```

---

## 2. Data Model

### 2.1 Core Entities

#### KnowledgeEntry

The fundamental unit of organizational knowledge.

```python
@dataclass
class KnowledgeEntry:
    """A discrete piece of organizational knowledge with full provenance."""

    # Identity
    id: str                          # UUID
    title: str                       # Human-readable title
    content: str                     # Knowledge content (markdown)
    content_type: str                # "fact", "procedure", "decision", "insight", "policy"

    # Classification
    workspace_id: Optional[str]      # Owning workspace
    category: str                    # Knowledge category/domain
    tags: List[str]                  # Searchable tags
    access_level: str                # "public", "department", "role", "individual", "bridge"

    # Provenance
    created_by: ContributorReference # Who created this entry
    created_at: datetime             # When created
    created_context: ActivityContext  # Why/how created (linked to workspace objective)
    confidence: ConfidenceLevel      # How certain is this knowledge

    # Evolution
    version: int                     # Version number
    previous_version_id: Optional[str]  # Link to previous version
    evolution_reason: Optional[str]  # Why this version exists
    status: str                      # "draft", "active", "contested", "archived", "deprecated"

    # Relationships
    derived_from: List[str]          # IDs of source entries
    related_to: List[str]           # IDs of related entries
    supersedes: Optional[str]        # ID of entry this replaces

    # Trust Linkage
    audit_anchor_id: Optional[str]   # Link to EATP audit anchor
    delegation_chain_id: Optional[str]  # Trust chain authorizing this entry

    # Embeddings (for semantic search)
    embedding_vector: Optional[List[float]]  # Vector embedding of content
```

#### ContributorReference

Links knowledge to its contributors with differentiation between human and AI.

```python
@dataclass
class ContributorReference:
    """Reference to a knowledge contributor with type differentiation."""

    agent_id: str                    # Agent or user identifier
    agent_type: str                  # "human", "ai_agent", "system", "bridge_team"
    role: str                        # "author", "reviewer", "approver", "annotator"
    contribution_type: str           # "original", "edit", "review", "annotation", "derivation"

    # For AI agents
    model_id: Optional[str]          # AI model identifier (e.g., "gpt-4")
    model_version: Optional[str]     # Model version
    prompt_hash: Optional[str]       # Hash of the prompt that generated this

    # For human contributors
    department: Optional[str]        # Human's department
    expertise_area: Optional[str]    # Self-declared or inferred expertise

    # Trust linkage
    delegation_record_id: Optional[str]  # EATP delegation authorizing contribution
    trust_posture: Optional[str]     # Posture at time of contribution
```

#### ConfidenceLevel

Structured confidence metadata.

```python
@dataclass
class ConfidenceLevel:
    """Structured confidence level for knowledge entries."""

    level: str                       # "high", "medium", "low", "uncertain"
    score: float                     # 0.0 to 1.0 numeric confidence
    basis: str                       # "empirical", "expert_judgment", "ai_inference", "consensus", "anecdotal"
    evidence_references: List[str]   # Links to supporting evidence
    last_validated: Optional[datetime]  # When confidence was last checked
    validated_by: Optional[str]      # Who validated the confidence level
```

#### ActivityContext

Captures the context in which knowledge was created or modified.

```python
@dataclass
class ActivityContext:
    """Context in which a knowledge activity occurred."""

    activity_id: str                 # UUID
    activity_type: str               # "creation", "modification", "review", "contestation", "resolution"
    workspace_id: Optional[str]      # Workspace where activity occurred
    objective_id: Optional[str]      # Workspace objective being served
    trigger: str                     # What triggered this activity
    timestamp: datetime              # When activity occurred

    # Linked audit
    audit_anchor_id: Optional[str]   # EATP audit anchor for this activity
    trust_context_snapshot: Optional[dict]  # Trust state at time of activity
```

### 2.2 Knowledge Perspectives (Contested Knowledge)

```python
@dataclass
class KnowledgePerspective:
    """A perspective on a knowledge entry, supporting contested knowledge."""

    id: str                          # UUID
    entry_id: str                    # Parent knowledge entry
    contributor: ContributorReference # Who holds this perspective
    content: str                     # The perspective content
    confidence: ConfidenceLevel      # Confidence in this perspective
    evidence: List[str]              # Supporting evidence
    status: str                      # "active", "withdrawn", "superseded"
    created_at: datetime
    resolution: Optional[str]        # How this perspective was resolved
```

### 2.3 Knowledge Thread (Discussion)

```python
@dataclass
class KnowledgeThread:
    """Discussion thread on a knowledge entry."""

    id: str                          # UUID
    entry_id: str                    # Parent knowledge entry
    thread_type: str                 # "discussion", "review", "contestation", "annotation"
    status: str                      # "open", "resolved", "archived"
    comments: List[ThreadComment]

@dataclass
class ThreadComment:
    """A comment in a knowledge thread."""

    id: str
    thread_id: str
    contributor: ContributorReference
    content: str
    timestamp: datetime
    reply_to: Optional[str]          # ID of parent comment
    audit_anchor_id: Optional[str]   # Trust linkage
```

---

## 3. EATP Integration Architecture

### 3.1 Trust Chain to Knowledge Bridge

Every knowledge entry is linked to the EATP trust system through two mechanisms:

1. **Audit Anchor Linkage**: Each knowledge activity generates an EATP audit anchor
2. **Delegation Chain Linkage**: Each contribution is authorized by an EATP delegation

```
EATP Trust Chain                    Knowledge Ledger
+------------------+               +------------------+
| Genesis Record   |               |                  |
|   (Organization) |               |                  |
+--------+---------+               |                  |
         |                         |                  |
         v                         |                  |
+------------------+               |                  |
| Delegation Record| ------>-----> | ContributorRef   |
| (to department)  |               | .delegation_id   |
+--------+---------+               +------------------+
         |                                  |
         v                                  v
+------------------+               +------------------+
| Capability       | ------>-----> | KnowledgeEntry   |
| Attestation      |               | .audit_anchor_id |
+--------+---------+               +------------------+
         |                                  |
         v                                  v
+------------------+               +------------------+
| Audit Anchor     | <------<----- | ActivityContext   |
| (immutable)      |               | .audit_anchor_id |
+------------------+               +------------------+
```

### 3.2 Provenance Verification

When querying knowledge, provenance can be verified through the EATP chain:

1. **Who**: Contributor's identity verified through delegation chain
2. **Authorization**: Contributor's right to contribute verified through capability attestation
3. **When**: Timestamp verified through audit anchor (tamper-evident)
4. **Integrity**: Content hash in audit anchor verifies entry has not been modified
5. **Confidence**: Confidence level linked to evidence and verification history

### 3.3 Human vs AI Provenance Differentiation

The Knowledge Ledger distinguishes between human and AI contributions structurally:

| Aspect             | Human Contributor                       | AI Contributor                    |
| ------------------ | --------------------------------------- | --------------------------------- |
| Identity           | user_id from EATP genesis               | agent_id from Kaizen registry     |
| Authorization      | Delegation from organization            | Delegation from supervising human |
| Confidence basis   | "expert_judgment", "empirical"          | "ai_inference", "model_output"    |
| Reproducibility    | Not guaranteed                          | Reproducible with prompt_hash     |
| Trust posture      | N/A (humans are implicit trust anchors) | Posture at time of contribution   |
| Review requirement | Based on access level                   | Always required (human review)    |

---

## 4. Event Sourcing Model

### 4.1 Knowledge Events

All knowledge changes are captured as immutable events:

```python
@dataclass
class KnowledgeEvent:
    """Immutable event in the knowledge event stream."""

    event_id: str                    # UUID
    event_type: str                  # See event types below
    entry_id: str                    # Affected knowledge entry
    timestamp: datetime              # Event timestamp
    contributor: ContributorReference # Who triggered this event
    payload: dict                    # Event-specific data
    audit_anchor_id: str             # EATP audit anchor

    # Event types:
    # "entry.created" - New knowledge entry
    # "entry.updated" - Entry content modified
    # "entry.evolved" - New version created
    # "entry.contested" - Perspective added
    # "entry.resolved" - Contestation resolved
    # "entry.archived" - Entry archived
    # "entry.deprecated" - Entry deprecated
    # "perspective.added" - New perspective
    # "perspective.withdrawn" - Perspective withdrawn
    # "thread.opened" - Discussion started
    # "thread.commented" - Comment added
    # "thread.resolved" - Thread resolved
    # "confidence.updated" - Confidence level changed
    # "access.changed" - Access level modified
```

### 4.2 Materialized Views

Current state is computed from the event stream:

| View                    | Purpose                           | Computation                        |
| ----------------------- | --------------------------------- | ---------------------------------- |
| **Current Entry**       | Latest version of knowledge entry | Apply all events in order          |
| **Entry History**       | Full evolution timeline           | All events for entry_id            |
| **Contributor Profile** | All contributions by an agent     | Events filtered by contributor     |
| **Workspace Knowledge** | All knowledge for a workspace     | Events filtered by workspace_id    |
| **Contested Entries**   | Entries with active contestation  | Entries where status = "contested" |
| **Confidence Map**      | Knowledge confidence landscape    | Latest confidence per entry        |

### 4.3 Event Stream to EATP Audit Bridge

Every knowledge event generates a corresponding EATP audit anchor:

```
Knowledge Event                    EATP Audit Anchor
+------------------+               +------------------+
| event_id: abc    |               | anchor_id: xyz   |
| type: created    | ------>-----> | action: knowledge|
| entry_id: 123    |               | subject: 123     |
| contributor: usr |               | agent: usr       |
| timestamp: T     |               | timestamp: T     |
+------------------+               | signature: ...   |
                                   | lineage_hash: ...|
                                   +------------------+
```

---

## 5. Schema Design

### 5.1 Relational Schema (PostgreSQL)

```sql
-- Core knowledge entries
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    workspace_id UUID REFERENCES workspaces(id),
    category VARCHAR(200),
    tags TEXT[],
    access_level VARCHAR(50) NOT NULL DEFAULT 'department',
    confidence_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    confidence_score FLOAT NOT NULL DEFAULT 0.5,
    confidence_basis VARCHAR(50),
    version INTEGER NOT NULL DEFAULT 1,
    previous_version_id UUID REFERENCES knowledge_entries(id),
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    derived_from UUID[],
    supersedes UUID REFERENCES knowledge_entries(id),
    audit_anchor_id VARCHAR(200),
    delegation_chain_id VARCHAR(200),
    created_by_agent_id VARCHAR(200) NOT NULL,
    created_by_agent_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Contributor references
CREATE TABLE knowledge_contributors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id),
    agent_id VARCHAR(200) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    role VARCHAR(50) NOT NULL,
    contribution_type VARCHAR(50) NOT NULL,
    model_id VARCHAR(200),
    model_version VARCHAR(100),
    prompt_hash VARCHAR(200),
    department VARCHAR(200),
    expertise_area VARCHAR(200),
    delegation_record_id VARCHAR(200),
    trust_posture VARCHAR(50),
    contributed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Perspectives (contested knowledge)
CREATE TABLE knowledge_perspectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id),
    contributor_id UUID NOT NULL REFERENCES knowledge_contributors(id),
    content TEXT NOT NULL,
    confidence_level VARCHAR(20) NOT NULL,
    confidence_score FLOAT NOT NULL,
    evidence TEXT[],
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    resolution TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Discussion threads
CREATE TABLE knowledge_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id),
    thread_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Thread comments
CREATE TABLE knowledge_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES knowledge_threads(id),
    contributor_agent_id VARCHAR(200) NOT NULL,
    contributor_agent_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    reply_to UUID REFERENCES knowledge_comments(id),
    audit_anchor_id VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Knowledge events (append-only)
CREATE TABLE knowledge_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    entry_id UUID NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    contributor_agent_id VARCHAR(200) NOT NULL,
    contributor_agent_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    audit_anchor_id VARCHAR(200) NOT NULL,
    -- Immutability: no UPDATE or DELETE allowed (enforced by policy)
    CONSTRAINT no_future_timestamps CHECK (timestamp <= NOW() + INTERVAL '1 minute')
);

-- Indexes for common access patterns
CREATE INDEX idx_entries_workspace ON knowledge_entries(workspace_id);
CREATE INDEX idx_entries_status ON knowledge_entries(status);
CREATE INDEX idx_entries_category ON knowledge_entries(category);
CREATE INDEX idx_entries_created_by ON knowledge_entries(created_by_agent_id);
CREATE INDEX idx_entries_tags ON knowledge_entries USING GIN(tags);
CREATE INDEX idx_contributors_agent ON knowledge_contributors(agent_id);
CREATE INDEX idx_contributors_entry ON knowledge_contributors(entry_id);
CREATE INDEX idx_events_entry ON knowledge_events(entry_id);
CREATE INDEX idx_events_type ON knowledge_events(event_type);
CREATE INDEX idx_events_timestamp ON knowledge_events(timestamp);
```

### 5.2 Vector Search Extension (pgvector)

```sql
-- Vector embeddings for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE knowledge_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id),
    embedding vector(1536),  -- OpenAI ada-002 dimension
    model_id VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_embeddings_vector ON knowledge_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## 6. Access Control Model

### 6.1 Knowledge Access Levels

| Level          | Who Can Read                 | Who Can Write                | Use Case                         |
| -------------- | ---------------------------- | ---------------------------- | -------------------------------- |
| **public**     | Everyone                     | Contributors with capability | General organizational knowledge |
| **department** | Department members + bridges | Department members           | Department-specific knowledge    |
| **role**       | Users with specific role     | Users with specific role     | Role-specific procedures         |
| **individual** | Named individuals only       | Named individuals only       | Sensitive knowledge              |
| **bridge**     | Bridge team members          | Bridge team members          | Cross-functional insights        |

### 6.2 Trust-Based Access Enhancement

Access control is enhanced by EATP trust posture:

| Trust Posture      | Read Access         | Write Access         | Review Requirement    |
| ------------------ | ------------------- | -------------------- | --------------------- |
| Pseudo-Agent       | All visible entries | Create draft only    | Human review required |
| Supervised         | All visible entries | Create with approval | Supervisor review     |
| Shared Planning    | All visible entries | Co-create with human | Joint review          |
| Continuous Insight | All visible entries | Annotate only        | Async review          |
| Delegated          | All visible entries | Full write           | Post-hoc audit        |

---

## 7. Relationship Patterns

### 7.1 Knowledge Relationships

```
Entry A ----derives_from----> Entry B
Entry A ----relates_to------> Entry C
Entry A ----supersedes-------> Entry D (deprecated)
Entry A ----conflicts_with---> Entry E (contested)
Entry A ----supports---------> Entry F (evidence)
```

### 7.2 Cross-Workspace Knowledge Flow

Knowledge can flow between workspaces through explicit references:

```
Workspace 1                    Workspace 2
+-------------------+         +-------------------+
| Entry: "Finding"  |-------->| Entry: "Applied"  |
| confidence: high  |         | derived_from: W1  |
+-------------------+         | confidence: med   |
                              +-------------------+
```

The `derived_from` relationship preserves provenance across workspace boundaries.

### 7.3 Knowledge Evolution Chain

```
Version 1 (2024-01) ----evolved_to----> Version 2 (2024-03) ----evolved_to----> Version 3 (2024-06)
   confidence: 0.5                         confidence: 0.7                         confidence: 0.9
   basis: ai_inference                     basis: empirical                        basis: consensus
   contributors: [AI]                      contributors: [AI, Human]               contributors: [Human team]
```

This chain shows knowledge becoming more certain over time, with increasing human validation.
