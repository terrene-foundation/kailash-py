# Phase 4: Trust UI Components Implementation Plan

## Component Specifications

### 1. Trust Chain Interactive Viewer

**Technology**: React Flow or D3.js

**Purpose**: Visualize delegation chains from human origin to leaf agents.

**Wireframe**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Trust Chain Viewer                                    [Zoom] [Fit] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│         ┌─────────────────────┐                                     │
│         │  👤 Alice Chen      │                                     │
│         │  CFO                │                                     │
│         │  alice@corp.com     │                                     │
│         │  Auth: Okta SSO     │                                     │
│         └──────────┬──────────┘                                     │
│                    │                                                │
│           DELEGATED (Nov 1)                                         │
│           └ Capabilities: read, process                             │
│           └ Cost limit: $10,000                                     │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                     │
│         │  🤖 Manager Agent   │                                     │
│         │  agent-mgr-001      │                                     │
│         └──────────┬──────────┘                                     │
│                    │                                                │
│           DELEGATED (Nov 2)                                         │
│           └ Cost limit: $1,000 (tightened)                          │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                     │
│         │  🤖 Worker Agent    │                                     │
│         │  agent-wkr-042      │                                     │
│         └─────────────────────┘                                     │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Selected: Worker Agent                                             │
│  Depth: 2 | Constraints: 5 | Active: Yes | Expires: Dec 1, 2025    │
└─────────────────────────────────────────────────────────────────────┘
```

**Props**:

```typescript
interface TrustChainViewerProps {
  chainData: TrustChainData;
  selectedNodeId?: string;
  onNodeSelect: (nodeId: string) => void;
  onNodeAction: (nodeId: string, action: "view" | "revoke") => void;
  layout: "vertical" | "horizontal" | "radial";
  highlightPath?: string[]; // Highlight specific path
  showConstraints: boolean;
  interactive: boolean;
}

interface TrustChainData {
  humanOrigin: HumanOriginNode;
  delegations: DelegationEdge[];
  agents: AgentNode[];
}
```

**SDK Data Requirements**:

- `TrustOperations.get_trust_chain(agent_id)` - Returns `TrustLineageChain`
- `DelegationRecord.human_origin` - Root human identity
- `DelegationRecord.delegation_chain` - Full path array

---

### 2. Genesis Ceremony Wizard

**Purpose**: Step-by-step trust establishment for new users.

**Steps**:

1. SSO Authentication
2. Organization Selection
3. Initial Capability Selection
4. Constraint Configuration
5. Confirmation & Genesis Creation

**Wireframe - Step 3 (Capability Selection)**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Genesis Ceremony                           Step 3 of 5            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Select Initial Capabilities                                        │
│  ────────────────────────────                                       │
│                                                                     │
│  These capabilities define what you can delegate to AI agents.      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  📊 Financial Operations                                     │   │
│  │  ├─ ☑ read_financial_data                                   │   │
│  │  ├─ ☑ process_invoices                                      │   │
│  │  ├─ ☐ approve_transactions (requires CFO approval)          │   │
│  │  └─ ☐ modify_budgets (requires CFO approval)                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  📝 Document Management                                      │   │
│  │  ├─ ☑ read_documents                                        │   │
│  │  ├─ ☑ generate_reports                                      │   │
│  │  └─ ☐ delete_documents                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Selected: 4 capabilities                                           │
│                                                                     │
│  [← Back]                                            [Continue →]  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Props**:

```typescript
interface GenesisCeremonyWizardProps {
  ssoToken: string;
  organizations: Organization[];
  capabilityRegistry: CapabilityDefinition[];
  constraintTemplates: ConstraintTemplate[];
  onComplete: (result: GenesisCeremonyResult) => void;
  onCancel: () => void;
}
```

---

### 3. Real-time Trust Event Stream

**Technology**: Server-Sent Events (SSE) or WebSocket

**Purpose**: Live feed of trust events (delegations, verifications, revocations).

**Wireframe**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Trust Events                                    [Filter] [Pause]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ● 10:32:15  DELEGATION  alice@corp.com → agent-inv-001            │
│              └ Capabilities: read_invoices, process_invoices        │
│              └ Expires: Dec 1, 2025                                 │
│                                                                     │
│  ● 10:32:17  VERIFICATION  agent-inv-001 → read_invoice            │
│              └ Resource: invoices/INV-2025-1234                     │
│              └ Result: ✓ VALID (2.3ms)                              │
│                                                                     │
│  ● 10:32:18  AUDIT  agent-inv-001 completed read_invoice           │
│              └ Duration: 45ms                                       │
│              └ Human Origin: alice@corp.com                         │
│                                                                     │
│  ○ 10:32:20  VERIFICATION  agent-inv-001 → approve_invoice         │
│              └ Resource: invoices/INV-2025-1234                     │
│              └ Result: ✗ DENIED (capability not granted)           │
│                                                                     │
│  ● 10:32:25  REVOCATION  bob@corp.com (cascade)                    │
│              └ Reason: Employee termination                         │
│              └ Agents revoked: 4                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Event Types**:

```typescript
type TrustEventType =
  | "GENESIS"
  | "DELEGATION"
  | "VERIFICATION"
  | "AUDIT"
  | "REVOCATION"
  | "POSTURE_CHANGE";

interface TrustEvent {
  eventId: string;
  eventType: TrustEventType;
  timestamp: string;
  actorId: string;
  targetId?: string;
  details: Record<string, unknown>;
  humanOrigin?: HumanOriginSummary;
}
```

---

### 4. Delegation Management Dashboard

**Purpose**: Organization-wide view of all active delegations.

**Wireframe**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Delegation Management                         [+ New Delegation]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Filters: [All Humans ▼] [All Agents ▼] [Active ▼] [🔍 Search]     │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Human            Agent              Status    Expires    Act  │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │ alice@corp.com   Invoice Processor  🟢 Active Dec 1      ⋮   │ │
│  │                  └ Cost: $234/$1000 used                      │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │ alice@corp.com   Report Generator   🟢 Active Jan 15     ⋮   │ │
│  │                  └ Executions: 47 successful                  │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │ bob@corp.com     Data Analyzer      🔴 Revoked N/A        ⋮   │ │
│  │                  └ Revoked: Employee termination              │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │ carol@corp.com   Email Responder    🟡 Expiring Nov 30    ⋮   │ │
│  │                  └ 3 days until expiration                    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Total: 42 delegations | Active: 38 | Expiring Soon: 4            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 5. Constraint Template Library

**Purpose**: Pre-built constraint patterns for common use cases.

**Wireframe**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Constraint Templates                          [+ Create Custom]   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  System Templates                                                   │
│  ─────────────────                                                  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  📋 Standard Office Hours                                     │ │
│  │  ─────────────────────────                                    │ │
│  │  Time: 09:00-17:00 Mon-Fri                                    │ │
│  │  Cost: $10,000/day                                            │ │
│  │  Rate: 100 requests/hour                                      │ │
│  │                                           [Use Template]      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  🔒 Strict Compliance                                         │ │
│  │  ───────────────────                                          │ │
│  │  Time: 10:00-16:00 Mon-Thu                                    │ │
│  │  Cost: $1,000/transaction                                     │ │
│  │  Rate: 10 requests/hour                                       │ │
│  │  Geo: US, CA only                                             │ │
│  │  Requires: MFA confirmation                                   │ │
│  │                                           [Use Template]      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Organization Templates                                             │
│  ──────────────────────                                             │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  💰 Finance Department                     Created by: CFO    │ │
│  │  ───────────────────                                          │ │
│  │  Resources: invoices/*, reports/*                             │ │
│  │  Cost: $50,000/month                                          │ │
│  │                                           [Use Template]      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 6. Audit Trail Explorer

**Purpose**: Query and explore audit records with human origin tracing.

**Wireframe**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Audit Trail Explorer                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  🔍 Search: [invoice_id:INV-2025-1234               ] [Search]     │
│                                                                     │
│  Filters:                                                           │
│  Date: [Nov 1    ] to [Nov 30, 2025]                               │
│  Action: [All Actions        ▼]                                     │
│  Agent: [All Agents         ▼]                                      │
│  Result: [All Results       ▼]                                      │
│                                                                     │
│  Results (47 records found)                                         │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ Time           Action            Agent           Result   Src │ │
│  ├───────────────────────────────────────────────────────────────┤ │
│  │ Nov 15 10:32   read_invoice      inv-proc-001    ✓       👤  │ │
│  │ Nov 15 10:33   process_invoice   inv-proc-001    ✓       👤  │ │
│  │ Nov 15 10:34   submit_approval   inv-proc-001    ✓       👤  │ │
│  │ Nov 16 09:15   read_invoice      inv-proc-001    ✗       👤  │ │
│  │   └ Denied: Outside time window                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  👤 = Click to view human origin chain                             │
│                                                                     │
│  [Export CSV] [Export JSON] [Generate Compliance Report]           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---
