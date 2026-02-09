# UI/UX Gaps: Trust-Related Components for Enterprise-App

## Executive Summary

This document analyzes the trust-related UI/UX components documented in the Enterprise-App platform, identifies what exists versus what is missing, and specifies requirements for each component including data dependencies from the Kailash SDK trust module.

**Key Finding**: The Enterprise-App documentation describes five primary trust UI components (HumanOriginBadge, CascadeRevocationModal, TrustPostureSelector, ConstraintEnvelopePanel, LineageViewer) with React code examples and TypeScript interfaces. However, several critical UI components needed for a complete trust management experience are not documented at all, and the documented components need verification that they are wired to backend services.

**Assessment**: The documented components handle the "display" layer well but lack the "management" layer -- dashboards, wizards, and administrative interfaces needed for trust operations at organizational scale.

---

## 1. Documented UI Components (Implementation Status Uncertain)

### 1.1 HumanOriginBadge

**Documented In**: `docs/00-developers/18-trust/02-human-origin-badge.md`

**Purpose**: Visual component that answers "Who is responsible for this?" by displaying the human who authorized an agent action.

**Documented Props**:
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `humanOrigin` | `HumanOrigin \| null` | required | The human origin data |
| `showDetails` | `boolean` | `false` | Show name and email inline |
| `showProvider` | `boolean` | `true` | Show auth provider icon |
| `showTimestamp` | `boolean` | `false` | Show relative time |
| `size` | `"sm" \| "md" \| "lg"` | `"md"` | Avatar size |

**Documented Variants**:

- **Compact** (default): Avatar with initials + auth provider icon + tooltip
- **Expanded** (`showDetails`): Avatar + name + email + provider icon
- **Legacy Badge**: "Legacy Action" indicator for pre-EATP actions
- **Unknown Badge**: "Unknown Origin" for actions without human origin

**Documented Usage Contexts**:

```tsx
// In audit event cards
<HumanOriginBadge humanOrigin={auditAnchor.human_origin} />

// With full details visible
<HumanOriginBadge humanOrigin={delegation.human_origin} showDetails />

// In trust chain viewer
<HumanOriginBadge humanOrigin={chain.genesis.human_origin} size="lg" showTimestamp />
```

**Data Requirements from SDK**:
| SDK Field | UI Display |
|-----------|------------|
| `HumanOrigin.human_id` | Used to generate initials and identify user |
| `HumanOrigin.display_name` | Shown in expanded variant and tooltip |
| `HumanOrigin.auth_provider` | Provider icon (Okta, Azure AD, Google, etc.) |
| `HumanOrigin.session_id` | Correlation for revocation |
| `HumanOrigin.auth_timestamp` | Relative time display ("2 hours ago") |
| `HumanOrigin.claims` | Additional details in tooltip |

**Gap Assessment**:

- **Component**: Likely implemented (has detailed prop documentation)
- **Backend Wiring**: Needs verification that HumanOrigin data is being passed from SDK through platform API to component props
- **Missing**: No "click-to-view-chain" behavior documented (badge should link to full trust chain viewer)

---

### 1.2 CascadeRevocationModal

**Documented In**: `docs/00-developers/18-trust/03-cascade-revocation.md`

**Purpose**: Modal dialog that shows cascade impact before executing revocation, with confirmation flow.

**Documented Flow**:

1. User clicks "Revoke" on target agent
2. System calls `GET /api/v1/trust/revoke/{id}/impact` to compute impact
3. Modal displays affected agents count, delegation depths, active workload warnings
4. User enters revocation reason
5. User types "REVOKE" to confirm (safety measure)
6. System calls `POST /api/v1/trust/revoke/{id}/cascade`
7. All affected agents are revoked

**Documented Hook Integration**:

```tsx
import { CascadeRevocationModal, useRevokeCascade } from "@/features/trust";
import { getRevocationImpact } from "@/features/trust/api";

function RevocationButton({ agentId, agentName }) {
  const [showModal, setShowModal] = useState(false);
  const [impact, setImpact] = useState(null);
  const revokeMutation = useRevokeCascade();

  const handleRevoke = async () => {
    const impactData = await getRevocationImpact(agentId);
    setImpact(impactData);
    setShowModal(true);
  };

  return (
    <>
      <Button variant="destructive" onClick={handleRevoke}>
        Revoke Trust
      </Button>
      <CascadeRevocationModal
        open={showModal}
        onClose={() => setShowModal(false)}
        agentId={agentId}
        agentName={agentName}
        impact={impact}
        onConfirm={(reason) => revokeMutation.mutate({ agentId, reason })}
      />
    </>
  );
}
```

**Documented Variants**:

- **Single Agent Revocation**: Revoke one agent and its downstream delegations
- **Revoke by Human**: Revoke all agents originating from a specific human (employee departure)
- **Emergency Revocation**: Skip confirmation for critical security events

**Data Requirements from SDK**:
| SDK Operation | UI Data Need |
|---------------|-------------|
| `TrustOperations.verify()` traversal | List of affected agents in delegation tree |
| `DelegationRecord.depth` | Delegation depth for each affected agent |
| Agent session status | Active workload warnings |
| `AuditAnchor` count per agent | Activity statistics for impact assessment |

**Gap Assessment**:

- **Component**: Documented with code examples but needs backend wiring verification
- **Backend Gap**: Cascade Revocation Engine service needed (see 01-platform-trust-gaps.md)
- **Missing Features**: No real-time progress indicator during cascade execution, no undo/rollback capability documented, no partial revocation option

---

### 1.3 TrustPostureSelector

**Documented In**: `docs/00-developers/18-trust/04-trust-postures.md`

**Purpose**: UI for selecting and configuring trust postures for agents.

**Documented Posture Levels**:
| Posture | Visual | Description |
|---------|--------|-------------|
| Pseudo | Human icon (blue) | Human decides everything |
| Supervised | Eye icon (green) | Human approves each action |
| Shared Planning | Handshake icon (yellow) | Human and AI co-plan |
| Continuous Insight | Dashboard icon (orange) | AI decides, human monitors |
| Delegated | Robot icon (red) | Full autonomy |

**Documented Configuration Per Posture**:

**Pseudo Agent Configuration**:

```typescript
{
  routingMethod: "email" | "slack" | "task_queue",
  responseTimeout: number,  // seconds before escalation
  fallbackUser: string      // who handles timeouts
}
```

**Supervised Autonomy Configuration**:

```typescript
{
  approvalMode: "explicit" | "implicit",
  approvalTimeout: number,
  autoApproveCategories: string[],
  requireJustification: boolean
}
```

**Shared Planning Configuration**:

```typescript
{
  planningHorizon: "immediate" | "short_term" | "long_term",
  humanReviewRequired: boolean,
  maxPlanSteps: number,
  allowParallelExecution: boolean
}
```

**Continuous Insight Configuration**:

```typescript
{
  monitoringDashboard: boolean,
  alertThresholds: Record<string, number>,
  humanInterventionTriggers: string[],
  reportingFrequency: "real_time" | "hourly" | "daily"
}
```

**Delegated Configuration**:

```typescript
{
  maxDelegationDepth: number,
  requiredConstraints: string[],
  auditFrequency: "per_action" | "per_session" | "daily",
  emergencyOverride: boolean
}
```

**Data Requirements from SDK**:
| SDK Component | UI Data Need |
|---------------|-------------|
| `TrustPolicyEngine` | Current posture for agent |
| Posture progression criteria | Whether agent is eligible for next posture |
| Agent action history | Track record for progression evaluation |
| `ConstraintEnvelope` | Current constraints tied to posture |

**Gap Assessment**:

- **Component**: Well-documented with per-posture configuration interfaces
- **Backend Gap**: Posture Progression Engine needed (see 01-platform-trust-gaps.md)
- **Missing**: No PostureConfigPanel implementation documented for each posture's configuration, no visual representation of posture progression timeline, no comparison view (current vs requested posture)

---

### 1.4 ConstraintEnvelopePanel

**Documented In**: `docs/00-developers/18-trust/05-constraint-envelope.md`

**Purpose**: Tabbed panel for configuring the five constraint categories.

**Documented Tab Structure**:

**Tab 1: Resource Constraints**

```typescript
interface ResourceConstraints {
  maxCostPerOperation: number; // Maximum $ per single operation
  maxTotalBudget: number; // Total budget for work unit
  maxApiCalls: number; // API call limit
  maxTokens: number; // Token usage limit
  allowedModels: string[]; // Permitted model IDs
}
```

**Tab 2: Temporal Constraints**

```typescript
interface TemporalConstraints {
  validFrom: string; // ISO 8601 start time
  validUntil: string; // ISO 8601 end time
  allowedHours: { start: number; end: number; timezone: string };
  maxDurationMinutes: number; // Maximum execution duration
}
```

**Tab 3: Data Access Constraints**

```typescript
interface DataConstraints {
  allowedPaths: string[]; // Glob patterns for allowed data
  deniedPaths: string[]; // Glob patterns for denied data
  sensitivityLevel: "public" | "internal" | "confidential" | "restricted";
  requireEncryption: boolean;
  allowExternalTransfer: boolean;
}
```

**Tab 4: Operational/Action Constraints**

```typescript
interface ActionConstraints {
  allowedTools: string[]; // Tools agent can use
  deniedTools: string[]; // Tools agent cannot use
  maxConcurrency: number; // Max parallel operations
  requireApprovalFor: string[]; // Actions needing human approval
  sandboxMode: boolean; // Run in sandbox environment
}
```

**Tab 5: Communication/Transaction Constraints**

```typescript
interface CommunicationConstraints {
  allowedRecipients: string[]; // Who agent can communicate with
  maxRecipients: number; // Max recipients per message
  requireReview: boolean; // Human review before send
  allowedChannels: string[]; // Permitted communication channels
  retentionPolicy: "none" | "30d" | "90d" | "1y" | "forever";
}
```

**Validation Rules** (documented):

- `maxCostPerOperation` must be <= `maxTotalBudget`
- `maxCostPerOperation` cannot exceed parent delegation's limit
- At least one model must be allowed
- `validFrom` must be before `validUntil`
- Allowed hours must be valid (0-23)
- `maxDurationMinutes` must be positive

**Data Requirements from SDK**:
| SDK Component | UI Data Need |
|---------------|-------------|
| `ConstraintEnvelope` | Current constraints for display |
| `ConstraintType` enum | Mapping UI categories to SDK constraint types |
| Parent delegation constraints | Tightening bounds (child cannot exceed parent) |
| Constraint validation rules | Real-time validation feedback |

**Gap Assessment**:

- **Component**: Thoroughly documented with TypeScript interfaces and validation rules
- **Backend Gap**: Constraint Envelope Compiler needed (see 01-platform-trust-gaps.md)
- **Missing**: No constraint template library (pre-built configurations for common roles), no visual constraint comparison (parent vs child), no constraint impact preview ("what would this constraint block?")

---

### 1.5 LineageViewer

**Documented In**: `docs/00-developers/06-gateways/lineage-visualization.md`

**Purpose**: Interactive graph visualization of agent invocation flows and trust chains.

**Documented Node Types**:
| Node Type | Visual | Description |
|-----------|--------|-------------|
| External Agent | Purple border (#8B5CF6) | External agent integration point |
| Workflow | Blue border (#3B82F6) | Kailash workflow node |
| Webhook Endpoint | Green border (#10B981) | Webhook delivery point |

**Documented Edge Types**:
| Edge Type | Visual | Description |
|-----------|--------|-------------|
| Invocation | Solid line with arrow | Agent was invoked |
| Data Flow | Dashed line | Data was passed |
| Delegation | Dotted line | Trust was delegated |

**Documented Interactions**:

- Click on node to see details
- Hover for tooltip with metadata
- Zoom and pan for large graphs
- Export to SVG/PNG

**Data Requirements from SDK**:
| SDK Component | UI Data Need |
|---------------|-------------|
| `TrustLineageChain` | Complete chain data for graph construction |
| `DelegationRecord` chain | Parent-child relationships for edges |
| `HumanOrigin` | Root node display |
| `CapabilityAttestation` | Node capability annotations |
| `AuditAnchor` list | Action history for each node |

**Gap Assessment**:

- **Component**: Documented with React Flow integration for external agent lineage
- **Missing**: No EATP-specific trust chain viewer (documented viewer is for external agent invocation lineage, not the 5-element EATP trust chain), no real-time updates (graph should update when new delegations are created or revocations occur), no filtering by posture, constraint, or time range

---

## 2. Missing UI Components (Not Documented)

### 2.1 Trust Chain Interactive Viewer

**Priority**: P0-Critical
**Description**: An interactive D3/React Flow visualization showing the complete EATP trust chain from HumanOrigin through all delegation levels to leaf agents.

**Required Elements**:

```
[Human Origin Node]
    ├── [Genesis Record] → displays who, when, what authority
    │     └── [Pseudo Agent] → human's proxy in trust system
    │           ├── [Delegation 1] → shows constraints tightening
    │           │     └── [Agent A] → displays posture, capabilities
    │           │           ├── [Sub-Delegation] → further tightening
    │           │           │     └── [Agent B] → leaf agent
    │           │           └── [Audit Anchors] → action history
    │           └── [Delegation 2]
    │                 └── [Agent C]
    └── [Constraint Envelope Overlay] → shows accumulated constraints at any level
```

**Interaction Patterns**:

- Click any node to see full details in side panel
- Click "Compare Constraints" to see tightening progression
- Click "Audit Trail" on any agent to see action history
- Real-time updates via SSE when chain changes
- "Revoke" action accessible from any node
- Color coding by posture level and health status

**Data Dependencies**:

- SDK `TrustLineageChain.to_dict()` for full chain data
- SDK `TrustOperations.verify()` for chain validity indicators
- Platform Cascade Revocation Engine for revocation from any node
- Platform Trust Event Bus for real-time updates

---

### 2.2 Genesis Ceremony Wizard

**Priority**: P1-High
**Description**: Step-by-step wizard for establishing initial trust when a new user or organization onboards.

**Required Steps**:

1. **Identity Verification**: Confirm SSO identity, display claims
2. **Authority Selection**: Choose authority level (organization admin, team lead, individual)
3. **Capability Assignment**: Select capabilities for the user's pseudo-agent
4. **Constraint Configuration**: Set initial constraint envelope (use templates or custom)
5. **Review and Confirm**: Summary of all selections before genesis record creation
6. **Completion**: Display genesis record ID, trust chain visualization

**Wireframe Description**:

```
┌─────────────────────────────────────────────────────────────┐
│ Genesis Ceremony                              Step 3 of 6   │
│                                                             │
│ ● Identity ● Authority ◉ Capabilities ○ Constraints        │
│                                                             │
│ Assign Capabilities to Your Proxy Agent                     │
│                                                             │
│ ┌──────────────────────┐  ┌──────────────────────┐         │
│ │ ☑ ACCESS             │  │ ☑ Read Data          │         │
│ │   Access resources   │  │ ☑ Write Reports      │         │
│ │                      │  │ ☐ Delete Records     │         │
│ ├──────────────────────┤  │ ☑ Execute Workflows  │         │
│ │ ☑ ACTION             │  │ ☐ Deploy Agents      │         │
│ │   Perform actions    │  │ ☑ Send Notifications │         │
│ │                      │  └──────────────────────┘         │
│ ├──────────────────────┤                                   │
│ │ ☐ DELEGATION         │  Note: You can only delegate      │
│ │   Delegate to others │  capabilities you select here.    │
│ └──────────────────────┘                                   │
│                                                             │
│                              [Back]  [Next: Constraints →]  │
└─────────────────────────────────────────────────────────────┘
```

**Data Dependencies**:

- SDK `PseudoAgent.create_for_human()` for creating human proxy
- SDK `TrustOperations.establish()` for genesis record creation
- SDK `CapabilityType` enum for capability options
- Platform SSO claims for identity verification step
- Platform Constraint Templates for template selection in step 4

---

### 2.3 Real-Time Trust Event Stream

**Priority**: P1-High
**Description**: Live feed of trust events displayed in a sidebar or dashboard panel.

**Event Types to Display**:
| Event | Icon | Color | Message Format |
|-------|------|-------|----------------|
| Chain Established | Link | Green | "Trust chain established for {agent} by {human}" |
| Chain Verified | Check | Blue | "Action verified for {agent}: {action}" |
| Chain Revoked | X-Circle | Red | "Trust revoked for {agent}: {reason}" |
| Delegation Created | Arrow-Right | Purple | "{delegator} delegated to {delegatee}" |
| Delegation Revoked | Arrow-X | Orange | "Delegation revoked: {delegator} → {delegatee}" |
| Constraint Violated | Alert | Red | "Constraint violation by {agent}: {detail}" |
| Posture Changed | Trending-Up | Yellow | "{agent} posture changed: {old} → {new}" |
| Health Degraded | Heart-Off | Red | "{agent} health degraded: {reason}" |

**Wireframe Description**:

```
┌──────────────────────────────────────┐
│ Trust Events (Live)         ⚙ Filter │
│──────────────────────────────────────│
│ 🔴 2:34 PM                          │
│ Trust revoked for worker-agent-7     │
│ Reason: Human origin revoked         │
│ Impact: 3 downstream agents          │
│                                      │
│ 🟢 2:33 PM                          │
│ Chain established for analyst-12     │
│ Authorized by: alice@company.com     │
│ Posture: Supervised                  │
│                                      │
│ 🔵 2:32 PM                          │
│ Action verified for researcher-5     │
│ Action: read_database                │
│ Constraint: within budget ($45/$100) │
│                                      │
│ 🟣 2:30 PM                          │
│ Delegation created                   │
│ coordinator → specialist-3           │
│ Capabilities: read:data, analyze     │
└──────────────────────────────────────┘
```

**Data Dependencies**:

- Platform Trust Event Bus (SSE/WebSocket)
- SDK trust operation callbacks
- Platform organization/agent name resolution

---

### 2.4 Delegation Management Dashboard

**Priority**: P1-High
**Description**: Administrative interface for managing all delegations across an organization.

**Required Views**:

- **Tree View**: Hierarchical delegation tree from human origins down
- **Table View**: Flat list of all active delegations with filtering
- **Graph View**: Network visualization of delegation relationships
- **Timeline View**: Delegation creation/revocation over time

**Table View Columns**:
| Column | Source | Description |
|--------|--------|-------------|
| Delegator | `DelegationRecord.delegator_id` | Who granted the delegation |
| Delegatee | `DelegationRecord.delegatee_id` | Who received the delegation |
| Capabilities | `DelegationRecord.capabilities` | What was delegated |
| Constraints | `DelegationRecord.constraints` | Constraint tightening applied |
| Human Origin | `DelegationRecord.human_origin` | Root human authority |
| Created | `DelegationRecord.created_at` | When delegation was created |
| Status | Active/Revoked | Current status |
| Depth | Computed | Distance from human origin |
| Actions | Buttons | View, Edit Constraints, Revoke |

**Filtering and Search**:

- Filter by delegator, delegatee, human origin
- Filter by status (active, revoked, expired)
- Filter by capability type
- Filter by constraint category
- Search by agent name or ID
- Date range filter

**Data Dependencies**:

- SDK `TrustOperations.delegate()` results via Platform API
- Platform Trust Chain DataFlow model
- Platform Trust Delegation DataFlow model
- Cascade Revocation Engine (for revocation actions)

---

### 2.5 Trust Health Dashboard

**Priority**: P1-High
**Description**: Organizational overview of trust health metrics.

**Required Panels**:

**Panel 1: Trust Health Score** (large numeric display)

```
┌─────────────────────────────────────┐
│          Trust Health               │
│                                     │
│            ████████                 │
│           ██      ██               │
│          █    87    █              │
│           ██      ██               │
│            ████████                 │
│                                     │
│     ▲ +3 from last week            │
└─────────────────────────────────────┘
```

**Panel 2: Agent Status Distribution** (pie/donut chart)

- Healthy (green): Valid trust chains, no violations
- Warning (yellow): Near-expiry chains, approaching limits
- Degraded (orange): Constraint violations, stale postures
- Revoked (red): Recently revoked agents

**Panel 3: Posture Distribution** (stacked bar chart)

- Count of agents at each posture level
- Trend over time (are agents progressing or regressing?)

**Panel 4: Recent Trust Events** (timeline)

- Last 24 hours of trust events
- Color-coded by severity
- Click-through to event details

**Panel 5: Constraint Usage** (gauges)

- Budget utilization (% of total budget used)
- API call utilization (% of limits used)
- Token utilization (% of token limits used)

**Panel 6: Compliance Status** (checklist)

- SOC 2 readiness indicators
- HIPAA compliance status
- GDPR data protection status
- Number of audit anchors created this period

**Data Dependencies**:

- Trust Health Dashboard Service (see 01-platform-trust-gaps.md)
- SDK `AgentHealthMonitor` metrics
- SDK `AgentRegistry` for agent counts
- Platform Audit Anchor DataFlow model for compliance metrics

---

### 2.6 Constraint Template Library

**Priority**: P2-Medium
**Description**: Pre-built constraint configurations for common organizational roles.

**Required Templates**:
| Template | Description | Key Constraints |
|----------|-------------|----------------|
| CFO Profile | Financial oversight agent | High budget limits, approval required for >$10K, restricted external communication |
| Analyst Profile | Data analysis agent | Read-only data access, no external transfer, token limits |
| Developer Profile | Code assistance agent | Access to code repos, no production access, sandbox mode |
| Customer Service | Customer-facing agent | Limited data access (public only), communication review required |
| Researcher Profile | Research and analysis | Broad data access, no action permissions, high token limits |
| Compliance Officer | Compliance monitoring | Read access to all audit logs, no modification rights |

**UI Features**:

- Browse templates by role category
- Preview constraint details before applying
- Clone and customize templates
- Organization-specific template creation
- Version history for templates

**Data Dependencies**:

- Platform Constraint Template DataFlow model
- SDK `ConstraintEnvelope` for template compilation
- Constraint Envelope Compiler for validation

---

### 2.7 Audit Trail Explorer

**Priority**: P1-High
**Description**: Comprehensive audit event viewer with advanced querying.

**Required Features**:

- Full-text search across audit events
- Filter by agent, human origin, action type, result, time range
- Export to CSV/JSON/CEF (Common Event Format)
- Compliance-specific views (SOC 2, HIPAA, GDPR)
- Tamper-evidence verification (verify hash chain integrity)
- Drill-down from audit event to full trust chain

**Table View Columns**:
| Column | Source | Description |
|--------|--------|-------------|
| Timestamp | `AuditAnchor.timestamp` | When action occurred |
| Agent | `AuditAnchor.agent_id` | Which agent performed action |
| Action | `AuditAnchor.action_type` | What was done |
| Resource | `AuditAnchor.resource_id` | What was affected |
| Result | `AuditAnchor.result` | SUCCESS/FAILURE/DENIED/PARTIAL |
| Human Origin | `AuditAnchor.human_origin` | Who authorized |
| Constraint Check | Computed | Whether constraints were satisfied |
| Chain Valid | Computed | Trust chain validity at time of action |

**Documented API Endpoints (for data retrieval)**:
| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/trust/audit/by-human/{id}` | Query audit by human origin |
| `client.trust.audit.list()` | List audit events with filters |
| `client.trust.audit.get()` | Get audit event details |
| `client.trust.audit.export()` | Export audit data |

**Data Dependencies**:

- Platform Audit Anchor DataFlow model
- SDK `AuditAnchor` data via Platform API
- SDK hash chain verification for tamper-evidence
- Platform compliance export formatting

---

## 3. Component Interaction Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Trust Management Dashboard                       │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Trust Health     │  │ Posture          │  │ Trust Events     │  │
│  │ Dashboard (2.5)  │  │ Distribution     │  │ Stream (2.3)     │  │
│  │                  │  │ Chart            │  │                  │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           │                     │                      │            │
│  ┌────────▼─────────────────────▼──────────────────────▼─────────┐ │
│  │                  Agent Detail View                              │ │
│  │  ┌──────────┐ ┌──────────────┐ ┌────────────┐ ┌────────────┐ │ │
│  │  │ Human    │ │ Trust Chain  │ │ Constraint │ │ Posture    │ │ │
│  │  │ Origin   │ │ Interactive  │ │ Envelope   │ │ Selector   │ │ │
│  │  │ Badge    │ │ Viewer (2.1) │ │ Panel      │ │ (1.3)      │ │ │
│  │  │ (1.1)    │ │              │ │ (1.4)      │ │            │ │ │
│  │  └──────────┘ └──────────────┘ └────────────┘ └────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Delegation       │  │ Audit Trail      │  │ Cascade          │  │
│  │ Management       │  │ Explorer         │  │ Revocation       │  │
│  │ Dashboard (2.4)  │  │ (2.7)            │  │ Modal (1.2)      │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐                        │
│  │ Genesis Ceremony │  │ Constraint       │                        │
│  │ Wizard (2.2)     │  │ Template Library │                        │
│  │                  │  │ (2.6)            │                        │
│  └──────────────────┘  └──────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow: SDK to UI

```
SDK Layer                    Platform API Layer              UI Layer
─────────                    ──────────────────              ────────

HumanOrigin ──────────────→ GET /trust/chains/{id} ──────→ HumanOriginBadge
                                                          Trust Chain Viewer

TrustLineageChain ────────→ GET /trust/chains ───────────→ Trust Chain Viewer
                           GET /trust/chains/{id}         Delegation Dashboard

DelegationRecord ─────────→ GET /trust/delegations ──────→ Delegation Dashboard
                           POST /trust/delegations        Genesis Wizard

ConstraintEnvelope ───────→ GET /trust/constraints/{id} ─→ Constraint Panel
                           PUT /trust/constraints/{id}    Constraint Templates

AuditAnchor ──────────────→ GET /trust/audit ─────────────→ Audit Explorer
                           GET /trust/audit/export        Trust Events Stream

TrustPolicyEngine ────────→ GET /trust/postures/{id} ────→ Posture Selector
                           PUT /trust/postures/{id}       Health Dashboard

AgentHealthMonitor ───────→ GET /trust/health ────────────→ Health Dashboard
                           WebSocket /trust/events        Trust Events Stream

CascadeRevocation ────────→ GET /trust/revoke/{id}/impact → Revocation Modal
(computed)                 POST /trust/revoke/{id}/cascade
```

---

## 5. Implementation Priority

### Phase 1: Foundation Components (Weeks 1-3)

| Component                                      | Priority | Dependencies              |
| ---------------------------------------------- | -------- | ------------------------- |
| HumanOriginBadge verification + backend wiring | P0       | Platform API              |
| Trust Chain Interactive Viewer                 | P0       | Platform Trust Chain API  |
| CascadeRevocationModal backend wiring          | P0       | Cascade Revocation Engine |

### Phase 2: Management Components (Weeks 4-6)

| Component                       | Priority | Dependencies                |
| ------------------------------- | -------- | --------------------------- |
| Audit Trail Explorer            | P1       | Audit Anchor DataFlow model |
| Real-Time Trust Event Stream    | P1       | Trust Event Bus             |
| Delegation Management Dashboard | P1       | Delegation DataFlow model   |

### Phase 3: Intelligence Components (Weeks 7-9)

| Component                              | Priority | Dependencies               |
| -------------------------------------- | -------- | -------------------------- |
| Trust Health Dashboard                 | P1       | Trust Health Service       |
| Posture Selector backend wiring        | P1       | Posture Progression Engine |
| ConstraintEnvelopePanel backend wiring | P1       | Constraint Compiler        |

### Phase 4: Optimization Components (Weeks 10-12)

| Component                                 | Priority | Dependencies                 |
| ----------------------------------------- | -------- | ---------------------------- |
| Genesis Ceremony Wizard                   | P1       | Genesis Ceremony Service     |
| Constraint Template Library               | P2       | Constraint Templates model   |
| LineageViewer enhancement (EATP-specific) | P2       | Trust Chain Viewer (Phase 1) |

---

## 6. Design Principles

All trust UI components must follow these design principles:

1. **Trust Visibility**: Trust status must be visible at a glance (color coding, badges, health indicators)
2. **Human Accountability**: Every displayed action must trace back to a human origin
3. **Progressive Disclosure**: Summary first, details on demand (tooltips, expandable panels, drill-down)
4. **Real-Time Awareness**: Changes to trust state must be reflected immediately (SSE/WebSocket)
5. **Destructive Action Safety**: Revocation and constraint changes require explicit confirmation
6. **Audit Readiness**: All trust UI interactions should themselves be auditable
7. **Multi-Tenancy**: UI must scope all data to the current organization
8. **Accessibility**: All trust indicators must have text alternatives (not color-only)
9. **Responsive**: Trust dashboard must work on desktop and tablet
10. **Dark Mode**: All trust visualization components must support dark mode

---

_Document Version: 1.0_
_Analysis Date: February 2026_
_Source: Enterprise-App developer docs (18-trust/02-human-origin-badge.md, 18-trust/03-cascade-revocation.md, 18-trust/04-trust-postures.md, 18-trust/05-constraint-envelope.md, 06-gateways/lineage-visualization.md)_
_Author: Gap Analysis Agent_
