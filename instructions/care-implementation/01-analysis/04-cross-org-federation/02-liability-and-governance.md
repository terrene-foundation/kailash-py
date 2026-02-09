# Liability and Governance

> Cross-organizational liability, governance, and accountability analysis for EATP - liability models, audit access, asymmetric trust, and audit trail continuity.

---

## 3. Liability Boundary

### 3.1 The Accountability Problem

**Scenario:** Org A's agent delegates a financial analysis task to Org B's agent. Org B's agent makes an error that causes $1M loss.

**Questions:**

- Who is liable: Org A (delegator) or Org B (executor)?
- Does Org A's trust chain transfer liability?
- What if Org B exceeded constraints?
- What if constraints were mistranslated?

### 3.2 Liability Models

#### Model 1: Delegator Retains Liability

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DELEGATOR LIABILITY MODEL                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Org A (Delegator)           Org B (Executor)                      │
│   ┌───────────────┐           ┌───────────────┐                     │
│   │ Delegates     │ ────────► │ Executes      │                     │
│   │ task to B     │           │ task          │                     │
│   │               │           │               │                     │
│   │ LIABILITY:    │           │ LIABILITY:    │                     │
│   │ - For harm    │           │ - None for    │                     │
│   │   caused      │           │   result      │                     │
│   │ - For choice  │           │ - Only for    │                     │
│   │   of delegate │           │   gross       │                     │
│   │               │           │   negligence  │                     │
│   └───────────────┘           └───────────────┘                     │
│                                                                     │
│   Rationale: Org A chose to delegate; A is responsible for choice   │
│   Challenge: Org A has no control over B's execution quality        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Model 2: Executor Assumes Liability

```
┌─────────────────────────────────────────────────────────────────────┐
│                    EXECUTOR LIABILITY MODEL                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Org A (Delegator)           Org B (Executor)                      │
│   ┌───────────────┐           ┌───────────────┐                     │
│   │ Delegates     │ ────────► │ Executes      │                     │
│   │ task to B     │           │ task          │                     │
│   │               │           │               │                     │
│   │ LIABILITY:    │           │ LIABILITY:    │                     │
│   │ - For correct │           │ - For result  │                     │
│   │   constraints │           │ - For correct │                     │
│   │ - For data    │           │   execution   │                     │
│   │   provided    │           │ - For staying │                     │
│   │               │           │   in bounds   │                     │
│   └───────────────┘           └───────────────┘                     │
│                                                                     │
│   Rationale: Org B controls execution; B is responsible for quality │
│   Challenge: Org B may not have full context of A's requirements    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### Model 3: Shared Liability (Recommended)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SHARED LIABILITY MODEL                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Org A (Delegator)           Org B (Executor)                      │
│   ┌───────────────┐           ┌───────────────┐                     │
│   │ Delegates     │ ────────► │ Executes      │                     │
│   │ task to B     │           │ task          │                     │
│   │               │           │               │                     │
│   │ LIABILITY:    │           │ LIABILITY:    │                     │
│   │ - For scope   │           │ - For quality │                     │
│   │   definition  │           │   of work     │                     │
│   │ - For correct │           │ - For staying │                     │
│   │   constraints │           │   within      │                     │
│   │ - For data    │           │   constraints │                     │
│   │   accuracy    │           │ - For proper  │                     │
│   │               │           │   reporting   │                     │
│   └───────────────┘           └───────────────┘                     │
│                                                                     │
│   TLA defines liability split:                                      │
│   - "scope_error": 70% A, 30% B                                     │
│   - "execution_error": 30% A, 70% B                                 │
│   - "constraint_violation": 0% A, 100% B                            │
│   - "translation_error": 50% A, 50% B (or 100% TLA provider)        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 EATP Liability Tracking

**Proposed Extension to DelegationRecord:**

```python
@dataclass
class CrossOrgDelegationRecord(DelegationRecord):
    """Extended delegation with liability terms."""

    # Existing fields
    # ...

    # Liability extensions
    liability_model: str                  # "delegator", "executor", "shared"
    liability_split: Dict[str, float]     # Error type -> delegator percentage
    liability_cap: Optional[float]        # Maximum liability amount
    insurance_reference: Optional[str]    # Insurance policy reference
    dispute_resolution: str               # "arbitration", "court", "mediation"
    governing_law: str                    # "us-ca", "eu-gdpr", etc.

    # Audit requirements
    liability_audit_level: str            # "full", "summary", "hash"
    evidence_retention_days: int          # How long to keep audit data
```

---

## 7. Audit Access

### 7.1 Cross-Org Audit Visibility Problem

When Org A delegates to Org B:

- Org A wants to see what Org B did
- Org B may have proprietary processes
- Both have compliance obligations

### 7.2 Audit Visibility Levels

```python
class AuditVisibility(Enum):
    """Levels of audit data sharing between organizations."""

    FULL = "full"                 # Complete audit data shared
    SUMMARY = "summary"           # Aggregated/summarized data only
    HASH_ONLY = "hash_only"       # Cryptographic proof only
    REDACTED = "redacted"         # Selected fields removed
    NONE = "none"                 # No access (except compliance)

@dataclass
class CrossOrgAuditPolicy:
    """Policy for audit data sharing."""

    default_visibility: AuditVisibility
    visibility_by_action: Dict[str, AuditVisibility]

    # Redaction rules
    always_redact: List[str]              # Fields never shared
    redact_for_non_compliance: List[str]  # Only shown for compliance

    # Retention
    cross_org_retention_days: int
    compliance_retention_days: int

    # Access control
    audit_query_allowed: bool
    real_time_streaming_allowed: bool
    bulk_export_allowed: bool
```

### 7.3 Audit Query Protocol

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CROSS-ORG AUDIT QUERY PROTOCOL                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  QUERY from Org A to Org B:                                         │
│  ─────────────────────────                                          │
│  {                                                                  │
│    "query_type": "delegation_trace",                                │
│    "delegation_id": "del-123",                                      │
│    "requesting_org": "org-a",                                       │
│    "requesting_agent": "agent-a-001",                               │
│    "reason": "compliance_audit",                                    │
│    "compliance_reference": "SOC2-2024-Q4"                           │
│  }                                                                  │
│                                                                     │
│  RESPONSE from Org B:                                               │
│  ────────────────────                                               │
│  {                                                                  │
│    "visibility_applied": "summary",                                 │
│    "audit_summary": {                                               │
│      "delegation_id": "del-123",                                    │
│      "executed_by": "[REDACTED]",  // Agent ID hidden               │
│      "execution_time": "2024-12-15T10:30:00Z",                      │
│      "duration_ms": 1234,                                           │
│      "result": "success",                                           │
│      "actions_performed": 5,                                        │
│      "data_accessed": ["financial_summary"],  // Detailed tables hidden │
│      "constraint_violations": 0                                     │
│    },                                                               │
│    "proof_hash": "abc123...",  // Merkle root for verification      │
│    "verification_endpoint": "https://org-b.com/audit/verify"        │
│  }                                                                  │
│                                                                     │
│  VERIFICATION (optional):                                           │
│  ────────────────────────                                           │
│  Org A can verify summary matches full audit via proof_hash         │
│  without seeing full audit details                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Asymmetric Trust

### 8.1 The Asymmetry Problem

Trust is often asymmetric:

- Large enterprise may trust startup less than vice versa
- Regulated entity may trust non-regulated less
- Org with security incident may be trusted less

### 8.2 Asymmetric Trust Model

```python
@dataclass
class AsymmetricTrustRelationship:
    """Bidirectional trust relationship with different levels."""

    org_a: str
    org_b: str

    # A's trust in B
    a_trusts_b: float                     # 0.0 - 1.0
    a_trusts_b_constraints: List[str]
    a_trusts_b_capabilities: List[str]

    # B's trust in A
    b_trusts_a: float                     # 0.0 - 1.0
    b_trusts_a_constraints: List[str]
    b_trusts_a_capabilities: List[str]

    # Effective trust for operations
    def effective_trust(self, direction: str) -> float:
        """Calculate effective trust for a direction."""
        if direction == "a_to_b":
            return min(self.a_trusts_b, 1.0)
        elif direction == "b_to_a":
            return min(self.b_trusts_a, 1.0)
        else:
            raise ValueError(f"Invalid direction: {direction}")
```

### 8.3 Asymmetric Trust Enforcement

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ASYMMETRIC TRUST ENFORCEMENT                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Scenario: Org A (large bank) ↔ Org B (startup)                    │
│                                                                     │
│   Trust Levels:                                                     │
│   - A trusts B: 0.6 (LIMITED)                                       │
│   - B trusts A: 0.95 (HIGH)                                         │
│                                                                     │
│   A → B Request (A trusts B at 0.6):                                │
│   ────────────────────────────────                                  │
│   - A can delegate: read-only, non-sensitive data                   │
│   - A requires: full audit, short TTL, human review of results      │
│   - A enforces: max 1 delegation depth, no subdelegation            │
│                                                                     │
│   B → A Request (B trusts A at 0.95):                               │
│   ────────────────────────────────                                  │
│   - B can delegate: most operations                                 │
│   - B requires: standard audit                                      │
│   - B allows: longer TTL, delegation chains                         │
│                                                                     │
│   Resulting Protocol:                                               │
│   ───────────────────                                               │
│   - Each request direction applies different constraints            │
│   - TLA defines both directions explicitly                          │
│   - Lower trust direction limits overall interaction                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Audit Trail Continuity

### 5.1 Current Audit Model

From `chain.py:381-456`, AuditAnchor includes:

```python
@dataclass
class AuditAnchor:
    id: str
    agent_id: str
    action: str
    timestamp: datetime
    trust_chain_hash: str
    result: ActionResult
    signature: str
    resource: Optional[str] = None
    parent_anchor_id: Optional[str] = None  # Links to triggering action
    context: Dict[str, Any] = field(default_factory=dict)
    human_origin: Optional["HumanOrigin"] = None
```

**Gap:** `parent_anchor_id` assumes same audit store. Cross-org audit requires external references.

### 5.2 Cross-Org Audit Linking

**Proposed Extension:**

```python
@dataclass
class CrossOrgAuditAnchor(AuditAnchor):
    """Extended audit anchor for cross-organizational operations."""

    # Existing fields
    # ...

    # Cross-org extensions
    originating_org_id: str               # Which org initiated the chain
    originating_anchor_id: str            # Anchor ID in originating org
    originating_anchor_hash: str          # Hash for verification
    cross_org_reference: Optional[str]    # URI to originating audit endpoint

    # Audit sharing policy
    audit_visibility: str                 # "full", "summary", "hash_only"
    redacted_fields: List[str]            # Fields hidden from other org

@dataclass
class AuditChainContinuation:
    """Structure for passing audit continuity across organizations."""

    originating_org_id: str
    originating_agent_id: str
    anchor_chain: List[str]               # List of anchor IDs
    chain_hash: str                       # Merkle root of anchor chain
    verification_endpoint: str            # Where to verify
    signature: str                        # Originating org's signature
```

### 5.3 Audit Trail Protocol

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CROSS-ORG AUDIT TRAIL CONTINUATION                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ORG A (Initiating)                      ORG B (Receiving)              │
│                                                                         │
│  ┌────────────────────┐                  ┌────────────────────┐         │
│  │ Audit Anchor A1    │                  │ Audit Anchor B1    │         │
│  │ action: delegate   │ ──────────────→  │ action: execute    │         │
│  │ agent: agent-a-001 │                  │ agent: agent-b-001 │         │
│  │ context: {         │                  │ context: {         │         │
│  │   task: "analyze"  │                  │   task: "analyze"  │         │
│  │ }                  │                  │   cross_org_ref: { │         │
│  └────────────────────┘                  │     org: "org-a",  │         │
│          ↓                               │     anchor: "A1",  │         │
│  ┌────────────────────┐                  │     hash: "abc..."│         │
│  │ Audit Anchor A2    │                  │   }                │         │
│  │ action: receive_   │ ←────────────── │ }                  │         │
│  │         result     │                  └────────────────────┘         │
│  │ context: {         │                          ↓                      │
│  │   result_from:     │                  ┌────────────────────┐         │
│  │     "org-b",       │                  │ Audit Anchor B2    │         │
│  │   anchor: "B2",    │                  │ action: complete   │         │
│  │   hash: "def..."   │                  │ cross_org_ref: ... │         │
│  │ }                  │                  └────────────────────┘         │
│  └────────────────────┘                                                 │
│                                                                         │
│  VERIFICATION: Either org can verify the complete chain                 │
│  - Org A calls Org B's /audit/verify endpoint                           │
│  - Org B provides hash proof without exposing sensitive data            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---
