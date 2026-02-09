# Federated Trust Protocol Design

**Version 2.0** - Updated with Second-Pass Hardening from Red Team Findings

> Federated trust protocol design elements for EATP cross-organizational federation - revocation propagation, data sovereignty, cross-org verification flows, risk registers, implementation roadmap, and SDK vs Platform boundary.

> **Note**: The full innovative federated trust protocol specification (Trust Registry directory, Trust Level Agreements bilateral protocol, Cross-Genesis Bridges, Federated Constraint Envelopes, Distributed Audit Anchors, Revocation Broadcast Protocol) with complete protocol specification, message formats, sequence diagrams, and SDK API design was planned as File 4 but was not completed in the original analysis pass due to output length constraints. This document contains the protocol design elements that were produced.

---

## 5. Revocation Propagation

### 5.1 The Revocation Challenge

When Org A revokes an agent's trust:

- Org A's internal systems update immediately
- Org B may continue servicing the revoked agent
- Cross-org requests may succeed with stale trust

### 5.2 Revocation Propagation Models

#### Model A: Pull-Based (Status Check)

```
Org B checks Org A's revocation endpoint before each cross-org request
- Latency: +50-100ms per request
- Staleness: None
- Reliability: Depends on Org A's availability
```

#### Model B: Push-Based (Webhook)

```
Org A pushes revocation events to registered Org B endpoints
- Latency: None after push (async)
- Staleness: Seconds to minutes
- Reliability: Requires reliable messaging
```

#### Model C: Hybrid (TTL + Push)

```
- Trust tokens have short TTL (5-15 minutes)
- Push notifications for immediate revocation
- Token refresh checks revocation status
```

### 5.3 Revocation Protocol

```python
@dataclass
class RevocationEvent:
    """Cross-org revocation notification."""

    event_id: str
    event_type: str                       # "agent_revoked", "capability_revoked", "org_suspended"
    affected_entity: str                  # Agent ID, capability name, or org ID
    revoking_authority: str               # Who revoked
    revoked_at: datetime
    reason: str                           # "security_incident", "policy_violation", etc.
    scope: str                            # "immediate", "graceful" (allow in-flight)
    signature: str                        # Signed by revoking authority

@dataclass
class RevocationAcknowledgment:
    """Acknowledgment of revocation receipt."""

    event_id: str
    acknowledging_org: str
    acknowledged_at: datetime
    action_taken: str                     # "blocked", "pending_review", "already_blocked"
    signature: str
```

### 5.4 Revocation Broadcast Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    REVOCATION BROADCAST ARCHITECTURE                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌───────────────────────────────────────────────────────┐         │
│   │              TRUST REGISTRY / MESSAGE BUS              │         │
│   │  ┌──────────────────────────────────────────────────┐ │         │
│   │  │ Revocation Topic: eatp.revocations.global        │ │         │
│   │  └──────────────────────────────────────────────────┘ │         │
│   └───────────────────────────────────────────────────────┘         │
│        ▲                     │                     │                │
│        │ publish             │ subscribe           │ subscribe      │
│        │                     ▼                     ▼                │
│   ┌─────────┐           ┌─────────┐           ┌─────────┐           │
│   │  ORG A  │           │  ORG B  │           │  ORG C  │           │
│   │ (source)│           │         │           │         │           │
│   └─────────┘           └─────────┘           └─────────┘           │
│                                                                     │
│   Revocation Event Flow:                                            │
│   1. Org A revokes agent-a-001                                      │
│   2. Org A publishes to eatp.revocations.global                     │
│   3. All subscribed orgs receive within 1-5 seconds                 │
│   4. Each org acknowledges and blocks locally                       │
│   5. In-flight requests may complete (graceful) or abort            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Sovereignty

### 6.1 Cross-Org Data Access Constraints

When Org A's agent accesses Org B's data:

- Org A's constraints limit what data can be requested
- Org B's constraints limit what data can be served
- Regulatory constraints (GDPR, CCPA) override both

### 6.2 Data Sovereignty Framework

```python
@dataclass
class DataSovereigntyPolicy:
    """Policy governing data access across organizations."""

    policy_id: str
    org_id: str

    # Data classification
    data_classifications: Dict[str, str]  # data_type -> classification
    classification_levels: List[str]      # Ordered from least to most sensitive

    # Geographic constraints
    allowed_regions: List[str]            # Where data can flow
    prohibited_regions: List[str]         # Never allow
    residency_requirements: Dict[str, str]  # data_type -> required_region

    # Regulatory compliance
    applicable_regulations: List[str]     # ["GDPR", "CCPA", "HIPAA"]
    regulation_constraints: Dict[str, Dict]  # regulation -> constraints

    # Cross-org rules
    cross_org_allowed: bool
    cross_org_requires_consent: bool
    cross_org_anonymization: str          # "none", "pseudonymize", "full"
    cross_org_audit_required: bool

@dataclass
class DataAccessRequest:
    """Request for cross-org data access."""

    request_id: str
    requesting_agent_id: str
    requesting_org_id: str
    target_org_id: str
    data_type: str
    data_scope: Dict[str, Any]
    purpose: str
    retention_period: Optional[timedelta]

    # Constraint proofs
    requester_constraints: Dict[str, Any]   # Translated to target vocabulary
    requester_regulatory_compliance: List[str]
    consent_reference: Optional[str]        # If consent required
```

### 6.3 Data Flow Decision Engine

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATA FLOW DECISION ENGINE                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  INPUT: DataAccessRequest from Org A to Org B                       │
│                                                                     │
│  STEP 1: Check Org A's egress policy                                │
│  ─────────────────────────────────────                              │
│  - Can Org A's agents send this data type externally?               │
│  - Is Org B in allowed_regions?                                     │
│  - Does purpose align with Org A's usage policies?                  │
│                                                                     │
│  STEP 2: Check Org B's ingress policy                               │
│  ─────────────────────────────────────                              │
│  - Does Org B accept this data type from external orgs?             │
│  - Is Org A in Org B's trusted_sources?                             │
│  - Does purpose align with Org B's accepted purposes?               │
│                                                                     │
│  STEP 3: Check regulatory constraints                               │
│  ────────────────────────────────────                               │
│  - GDPR: Is lawful basis established? (consent, contract, etc.)     │
│  - CCPA: Is this a "sale"? Is opt-out respected?                    │
│  - Sector: HIPAA, PCI-DSS, etc.                                     │
│                                                                     │
│  STEP 4: Apply data transformations                                 │
│  ────────────────────────────────                                   │
│  - Anonymization if required                                        │
│  - Field-level redaction                                            │
│  - Aggregation for analytics                                        │
│                                                                     │
│  STEP 5: Generate audit record                                      │
│  ────────────────────────────────                                   │
│  - What data flowed                                                 │
│  - Under what authority                                             │
│  - What transformations applied                                     │
│  - Retention and deletion requirements                              │
│                                                                     │
│  OUTPUT: Allow/Deny + Transformed Data + Audit Record               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Cross-Org Verification Flow (from A2A-EATP Analysis)

### 2.3 Cross-Org Verification Flow

**Proposed Enhanced Verification:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                    CROSS-ORG A2A VERIFICATION FLOW                     │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  STEP 1: Agent A prepares cross-org request                           │
│  ───────────────────────────────────────────                           │
│  - Serialize full trust chain                                          │
│  - Include genesis proof with Org A's signature                        │
│  - Include Trust Level Agreement (TLA) reference                       │
│  - Sign entire payload with agent's Ed25519 key                        │
│                                                                        │
│  STEP 2: A2A transport                                                 │
│  ─────────────────────                                                 │
│  - HTTP POST to Agent B's /a2a/jsonrpc                                 │
│  - Authorization: Bearer <cross-org-jwt>                               │
│  - X-EATP-Cross-Org: true                                              │
│  - X-EATP-TLA-Ref: tla-123 (Trust Level Agreement ID)                  │
│                                                                        │
│  STEP 3: Agent B receives and validates                                │
│  ─────────────────────────────────────────                             │
│  a) Parse JWT, extract cross-org claims                                │
│  b) Verify Agent A's signature on payload                              │
│  c) Verify Org A's signature on genesis proof                          │
│  d) Check Org A's certificate against Trust Registry                   │
│  e) Load TLA to get constraint translation rules                       │
│  f) Translate Agent A's constraints to Org B's vocabulary              │
│  g) Verify translated constraints permit requested action              │
│                                                                        │
│  STEP 4: Execute with cross-org audit                                  │
│  ───────────────────────────────────                                   │
│  - Execute operation under Agent B's local trust                       │
│  - Create audit anchor linking to Agent A's trust chain                │
│  - Return result with audit chain continuation                         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Risk Register

| Risk                          | Likelihood | Impact   | Mitigation                           |
| ----------------------------- | ---------- | -------- | ------------------------------------ |
| Genesis recognition failure   | Medium     | Critical | Multi-tier trust model + fallback    |
| Constraint translation errors | High       | High     | Standardized vocabulary + validation |
| Liability disputes            | Medium     | Critical | Explicit TLA terms + arbitration     |
| Trust level mapping abuse     | Medium     | High     | Conservative mapping + restrictions  |
| Revocation propagation delay  | High       | Medium   | Short TTL + push notifications       |
| Data sovereignty violations   | Medium     | Critical | Policy engine + audit                |
| Audit data leakage            | Low        | High     | Visibility levels + encryption       |
| Asymmetric trust exploitation | Medium     | Medium   | Explicit bidirectional TLA           |

---

## Dispute Resolution Framework (Second-Pass Hardening)

The original design left TLA enforcement undefined. This section specifies the complete dispute resolution process.

### Automated Violation Detection

```python
class TLAComplianceMonitor:
    """Monitors federation agreements for violations in real-time."""

    VIOLATION_TYPES = {
        "data_sovereignty": "Data crossed geo boundary without consent",
        "constraint_escalation": "Delegated agent exceeded federated constraints",
        "revocation_delay": "Revocation not propagated within SLA",
        "capacity_exceeded": "Cross-org delegation count exceeded TLA limit",
        "auth_failure": "Authentication failures from federated org exceeded threshold",
    }

    async def check_compliance(self, event: FederationEvent) -> list[TLAViolation]:
        """Check every cross-org event against TLA terms."""
        violations = []
        tla = await self.registry.get_tla(event.source_org, event.target_org)

        for term in tla.terms:
            if not term.evaluate(event):
                violations.append(TLAViolation(
                    tla_id=tla.id,
                    term=term,
                    event=event,
                    severity=term.violation_severity,
                    detected_at=datetime.now(timezone.utc),
                ))

        return violations
```

### Escalation Ladder

| Stage                | Trigger                                    | Timeline               | Action                                                  |
| -------------------- | ------------------------------------------ | ---------------------- | ------------------------------------------------------- |
| **Detection**        | Automated violation found                  | Immediate              | Log violation, notify both orgs                         |
| **Notification**     | Any violation                              | Within 1 hour          | Email/webhook to designated contacts                    |
| **Self-Remediation** | Non-critical violation                     | 48 hours               | Violating org fixes issue                               |
| **Mediation**        | Unresolved after 48h OR critical violation | 48h-7 days             | Designated mediator reviews                             |
| **Sanctions**        | Mediation fails                            | 7-14 days              | Graduated: warning -> reduced trust -> suspension       |
| **Termination**      | Repeated violations or critical breach     | Immediate for critical | Federation suspended, all cross-org delegations revoked |
| **Appeal**           | Any sanction                               | 30 days                | Independent review panel                                |

### Graduated Sanctions

```
Level 0: WARNING         - Logged, no operational impact
Level 1: REDUCED_TRUST   - Cross-org delegations limited to SUPERVISED posture max
Level 2: RESTRICTED      - No new cross-org delegations; existing ones continue
Level 3: SUSPENDED       - All cross-org operations paused; 72h to resolve
Level 4: TERMINATED      - Federation agreement revoked; cascade revocation of all cross-org trust
```

### Arbitration Mechanism

Each TLA MUST name:

1. **Primary arbitrator**: Mutually agreed third party
2. **Backup arbitrator**: If primary unavailable within 48 hours
3. **Governing law**: Jurisdiction for legal disputes
4. **Evidence preservation**: Both orgs must retain 90 days of federation logs

---

## 10. Implementation Priority

### Phase 1: Foundation (Weeks 1-4)

1. Genesis proof structure and validation
2. Basic TLA data model
3. Simple constraint translation (same vocabulary)
4. Revocation event structure

### Phase 2: Core (Weeks 5-8)

1. Multi-tier trust model
2. Constraint translation framework
3. Trust level mapping
4. Cross-org audit linking

### Phase 3: Enterprise (Weeks 9-12)

1. Liability tracking
2. Data sovereignty engine
3. Revocation broadcast
4. Asymmetric trust enforcement

---

## 11. SDK vs Platform Boundary

| Component                | SDK | Platform | Rationale                |
| ------------------------ | --- | -------- | ------------------------ |
| Genesis proof generation | ✓   |          | Cryptographic primitive  |
| Constraint vocabulary    | ✓   |          | Standard definitions     |
| Translation rules        | ✓   |          | Algorithm implementation |
| Trust level mapping      | ✓   |          | Data structure           |
| Liability models         | ✓   |          | Protocol definitions     |
| Trust Registry client    | ✓   |          | API client               |
| TLA management           |     | ✓        | Multi-tenant + UI        |
| Revocation broadcast     |     | ✓        | Push infrastructure      |
| Data sovereignty engine  |     | ✓        | Policy management        |
| Cross-org audit storage  |     | ✓        | Centralized persistence  |

---

## Trust Registry Governance Model

### Federated Registry with Quorum

The Trust Registry uses a federated model where each participating organization runs a registry node. Uses Raft consensus with 2/3 majority.

### Governance Rules

| Operation                  | Required Quorum                 | Initiated By         |
| -------------------------- | ------------------------------- | -------------------- |
| Add new org to federation  | 2/3 existing members            | Sponsoring org       |
| Revoke org from federation | Revoking org + 1 witness        | Any member           |
| Update TLA terms           | Both parties to TLA             | Either party         |
| Emergency revocation       | Any single org (for own agents) | Affected org         |
| Registry software update   | 3/4 majority                    | Governance committee |

### Organization Identity Verification

Inspired by TLS Certificate Transparency:

1. **Registration**: New org submits identity proof (legal entity, domain verification)
2. **Verification**: 2+ existing members verify org identity out-of-band
3. **Publication**: Org added to public federation log (append-only)
4. **Monitoring**: Any member can audit the federation log for unauthorized additions
5. **Challenge**: 7-day challenge period where any member can object

```python
class OrgIdentityVerifier:
    """Verify organization identity before federation admission."""

    async def verify_org(self, applicant: OrgApplication) -> VerificationResult:
        # Step 1: Domain verification (DNS TXT record)
        dns_verified = await self._verify_dns(applicant.domain)

        # Step 2: Legal entity verification (signed attestation)
        legal_verified = await self._verify_legal_entity(applicant.legal_docs)

        # Step 3: Existing member vouching (2+ members)
        vouches = await self._collect_vouches(applicant.org_id, required=2)

        # Step 4: Genesis key exchange (out-of-band)
        key_verified = await self._verify_genesis_key(applicant.genesis_public_key)

        return VerificationResult(
            verified=all([dns_verified, legal_verified, len(vouches) >= 2, key_verified]),
            dns=dns_verified, legal=legal_verified,
            vouches=vouches, key=key_verified,
        )
```

### Data Sovereignty After-the-Fact

For data that has already crossed organizational boundaries:

1. **Provenance tracking**: Every cross-org data transfer includes provenance metadata
2. **Data lineage graph**: Track where data has been replicated/transformed
3. **Right to erasure**: Request deletion of data from federated org (GDPR-compatible)
4. **Erasure verification**: Requesting org receives cryptographic proof of deletion
5. **Audit trail**: All cross-org data flows logged immutably

---

## A2A-EATP Implementation Phases

## 8. Implementation Phases

### Phase 1: Foundation (SDK)

- [ ] Extend TrustExtensions with cross-org fields
- [ ] Implement CrossOrgA2AToken
- [ ] Add genesis proof generation and verification
- [ ] Create constraint translation framework

### Phase 2: Protocol (SDK + Platform)

- [ ] Implement mutual authentication handshake
- [ ] Build constraint reconciliation engine
- [ ] Extend audit anchors for cross-org references
- [ ] Add cross-org JSON-RPC methods

### Phase 3: Federation (Platform)

- [ ] Build Trust Registry service
- [ ] Implement TLA (Trust Level Agreement) management
- [ ] Create revocation broadcast protocol
- [ ] Add cross-org audit verification endpoints

---

## A2A-EATP SDK vs Platform Boundary

## 9. SDK vs Platform Boundary

| Component                | SDK | Platform | Rationale                  |
| ------------------------ | --- | -------- | -------------------------- |
| CrossOrgA2AToken         | ✓   |          | Core data structure        |
| Genesis proof generation | ✓   |          | Cryptographic operation    |
| Constraint translation   | ✓   |          | Algorithm implementation   |
| Mutual auth protocol     | ✓   |          | Protocol specification     |
| Trust Registry           |     | ✓        | Requires persistence + API |
| TLA management           |     | ✓        | Multi-tenant + UI          |
| Cross-org audit storage  |     | ✓        | Centralized persistence    |
| Revocation broadcast     |     | ✓        | Push infrastructure        |
