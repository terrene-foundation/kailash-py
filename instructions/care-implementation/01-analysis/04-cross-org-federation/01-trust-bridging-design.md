# Trust Bridging Design

> Cross-organizational trust bridging analysis for EATP - genesis recognition, Trust Level Agreements (TLAs), constraint translation, and trust level interoperability.

---

## Part 1: Trust Bridging Challenges

## Executive Summary

This analysis examines the fundamental challenges of bridging trust across organizational boundaries in the EATP framework. Trust bridging is distinct from simple authentication - it requires establishing mutual recognition of governance frameworks, constraint systems, and accountability structures between independent organizations.

**Key Finding:** The core challenge is not technical (cryptography works across organizations) but semantic (what does "trusted" mean in different organizational contexts?).

**Complexity Score: Enterprise (32 points)**

- Technical: 10/15 (cryptographic bridging is well-understood)
- Business: 12/10 (liability, accountability, policy conflicts)
- Operational: 10/10 (governance, compliance, revocation)

---

## 1. Genesis Record Recognition

### 1.1 The Trust Root Problem

Every EATP trust chain traces back to a genesis record (from `chain.py:68-115`):

```python
@dataclass
class GenesisRecord:
    id: str
    agent_id: str
    authority_id: str           # Who authorized
    authority_type: AuthorityType  # org, system, human
    created_at: datetime
    signature: str
    signature_algorithm: str = "Ed25519"
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**The Problem:** When Org B receives a request from Org A's agent:

- Org B sees `authority_id: "org-a"`
- But Org B has no basis to trust "org-a"
- Org A's signature means nothing without trust in Org A's key

### 1.2 Current Validation Gap

From `auth.py:124-186`:

```python
async def verify_token(
    self,
    token: str,
    expected_audience: Optional[str] = None,
    verify_trust: bool = True,
) -> A2AToken:
    # ...
    if verify_trust:
        result = await self._trust_ops.verify(claims.iss)
        if not result.valid:
            raise TrustVerificationError(...)

        # Verify trust chain hash matches
        chain = await self._trust_ops.get_chain(claims.iss)
        if chain and chain.hash() != claims.trust_chain_hash:
            raise TrustVerificationError(...)
```

**Gap:** `self._trust_ops.get_chain(claims.iss)` only works within the same trust store. Cross-org requires fetching and validating external chains.

### 1.3 Genesis Recognition Models

#### Model A: Direct Federation (Bilateral)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DIRECT FEDERATION MODEL                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ORG A                              ORG B                          │
│   ┌──────────────┐                   ┌──────────────┐               │
│   │ Genesis: A   │ ◄───── TLA ─────► │ Genesis: B   │               │
│   └──────────────┘                   └──────────────┘               │
│                                                                     │
│   TLA (Trust Level Agreement):                                      │
│   - Org A's public key: [key-a]                                     │
│   - Org B's public key: [key-b]                                     │
│   - Mutual recognition: "FULL" or "LIMITED"                         │
│   - Signed by both orgs                                             │
│                                                                     │
│   Verification: Org B validates Org A's genesis using               │
│   pre-shared Org A public key from TLA                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Pros:**

- Simple to implement
- No third-party dependency
- Fast verification (local TLA lookup)

**Cons:**

- Doesn't scale (N orgs = N\*(N-1)/2 TLAs)
- Requires manual TLA creation
- No revocation broadcast mechanism

#### Model B: Trust Registry (Centralized)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TRUST REGISTRY MODEL                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                    ┌────────────────────┐                           │
│                    │   TRUST REGISTRY   │                           │
│                    │   (Central Authority)                          │
│                    └─────────┬──────────┘                           │
│                              │                                      │
│              ┌───────────────┼───────────────┐                      │
│              │               │               │                      │
│              ▼               ▼               ▼                      │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│   │   ORG A      │  │   ORG B      │  │   ORG C      │              │
│   │ Genesis: A   │  │ Genesis: B   │  │ Genesis: C   │              │
│   │ Registered   │  │ Registered   │  │ Registered   │              │
│   └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                     │
│   Registry provides:                                                │
│   - Org public key attestation                                      │
│   - Genesis validation                                              │
│   - Revocation status                                               │
│   - Trust level certification                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Pros:**

- Scales linearly (N orgs = N registrations)
- Centralized revocation
- Consistent trust policies

**Cons:**

- Single point of failure
- Privacy concerns (registry sees all orgs)
- Governance complexity (who runs registry?)

#### Model C: Decentralized Web of Trust

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WEB OF TRUST MODEL                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ORG A ◄──── attestation ────► ORG B                               │
│     │                              │                                │
│     │ attestation                  │ attestation                    │
│     ▼                              ▼                                │
│   ORG C ◄──── attestation ────► ORG D                               │
│                                                                     │
│   Trust Resolution:                                                 │
│   - Org A trusts Org B (direct)                                     │
│   - Org A trusts Org D via Org B (transitive, depth 1)              │
│   - Trust decays with depth: trust_level * 0.8^depth                │
│                                                                     │
│   Verification:                                                     │
│   - Build trust path from target to known-trusted org               │
│   - Verify each attestation signature in path                       │
│   - Calculate effective trust level                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Pros:**

- No central authority
- Organic trust network
- Resilient to single failures

**Cons:**

- Path discovery complexity
- Trust calculation ambiguity
- Revocation propagation slow

### 1.4 Recommended Hybrid Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HYBRID TRUST MODEL                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   TIER 1: Trust Registries (Federated)                              │
│   ─────────────────────────────────────                             │
│   - Industry-specific registries (FinServ, Healthcare, etc.)        │
│   - Geographic registries (EU, US, APAC)                            │
│   - Cross-registry attestation protocol                             │
│                                                                     │
│   TIER 2: Direct TLAs (High-Trust Pairs)                            │
│   ─────────────────────────────────────                             │
│   - Organizations with frequent interaction                         │
│   - Overrides registry trust level                                  │
│   - Faster verification (no registry call)                          │
│                                                                     │
│   TIER 3: Web of Trust (Discovery)                                  │
│   ────────────────────────────────                                  │
│   - Fallback when no TLA or registry                                │
│   - Limited trust level (max 50%)                                   │
│   - Requires human approval for high-stakes operations              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Constraint Translation

### 2.1 Semantic Constraint Mismatch

**Scenario 1: Financial Constraints**

| Org A Constraint     | Org B Constraint      | Challenge        |
| -------------------- | --------------------- | ---------------- |
| `max_cost_usd: 1000` | `budget_limit_eur: ?` | Exchange rate    |
| `daily_spend_limit`  | `monthly_budget`      | Time granularity |
| `cost_center: "R&D"` | `kostenstelle: ???`   | Taxonomy mapping |

**Scenario 2: Data Scope Constraints**

| Org A Constraint                 | Org B Constraint                      | Challenge     |
| -------------------------------- | ------------------------------------- | ------------- |
| `data_scope: ["PII"]`            | `daten_typ: ["personenbezogen"]`      | Vocabulary    |
| `regions: ["US-WEST"]`           | `geo_scope: ["california", "oregon"]` | Granularity   |
| `classification: "CONFIDENTIAL"` | `sensitivity: 3`                      | Scale mapping |

**Scenario 3: Temporal Constraints**

| Org A Constraint              | Org B Constraint          | Challenge |
| ----------------------------- | ------------------------- | --------- |
| `business_hours: "9-5 PST"`   | `arbeitszeit: "9-17 CET"` | Timezone  |
| `embargo_until: "2025-03-01"` | `sperrfrist: Date`        | Format    |
| `max_duration: "1h"`          | `zeitlimit: 3600`         | Units     |

### 2.2 Constraint Translation Framework

```python
@dataclass
class ConstraintVocabulary:
    """
    Standardized constraint vocabulary for cross-org translation.

    Based on W3C ODRL (Open Digital Rights Language) patterns.
    """

    namespace: str = "urn:eatp:constraints:v1"

    # Standard constraint types (extensible)
    STANDARD_TYPES = {
        # Financial
        "monetary_limit": {
            "base_unit": "USD",
            "properties": ["amount", "currency", "period"]
        },
        # Temporal
        "time_window": {
            "base_unit": "UTC",
            "properties": ["start", "end", "timezone", "recurrence"]
        },
        # Data
        "data_scope": {
            "vocabulary": "urn:eatp:data-classification:v1",
            "properties": ["categories", "regions", "sensitivity"]
        },
        # Action
        "action_restriction": {
            "vocabulary": "urn:eatp:actions:v1",
            "properties": ["allowed", "denied", "requires_approval"]
        },
    }

@dataclass
class ConstraintTranslationRule:
    """Rule for translating between two constraint systems."""

    source_type: str              # Org A's constraint type
    target_type: str              # Org B's constraint type
    translation_expression: str    # JEXL or similar expression
    bidirectional: bool = False   # Can translate both ways?
    requires_context: List[str] = field(default_factory=list)  # e.g., ["exchange_rate"]
    validation_schema: Optional[str] = None  # JSON Schema for result

# Example: USD to EUR translation
USD_TO_EUR_RULE = ConstraintTranslationRule(
    source_type="monetary_limit.usd",
    target_type="monetary_limit.eur",
    translation_expression="""
        {
            "amount": source.amount * context.exchange_rates.USD_EUR,
            "currency": "EUR",
            "period": source.period,
            "_translated_at": now(),
            "_translation_rate": context.exchange_rates.USD_EUR
        }
    """,
    bidirectional=True,
    requires_context=["exchange_rates"],
)
```

### 2.3 Translation Protocol

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONSTRAINT TRANSLATION PROTOCOL                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 1: Extract source constraints                                 │
│  ───────────────────────────────────                                │
│  Source: Agent A's trust chain                                      │
│  {                                                                  │
│    "max_cost_usd": 1000,                                            │
│    "data_scope": ["finance", "q4"],                                 │
│    "business_hours": "9-17 PST"                                     │
│  }                                                                  │
│                                                                     │
│  STEP 2: Normalize to standard vocabulary                           │
│  ─────────────────────────────────────────                          │
│  {                                                                  │
│    "urn:eatp:constraints:v1:monetary_limit": {                      │
│      "amount": 1000,                                                │
│      "currency": "USD",                                             │
│      "period": "per_operation"                                      │
│    },                                                               │
│    "urn:eatp:constraints:v1:data_scope": {                          │
│      "categories": ["finance"],                                     │
│      "temporal": ["Q4-2024"]                                        │
│    },                                                               │
│    "urn:eatp:constraints:v1:time_window": {                         │
│      "start": "09:00",                                              │
│      "end": "17:00",                                                │
│      "timezone": "America/Los_Angeles",                             │
│      "recurrence": "weekdays"                                       │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  STEP 3: Apply TLA translation rules                                │
│  ───────────────────────────────────                                │
│  TLA tla-123 specifies:                                             │
│  - monetary_limit.usd → monetary_limit.eur (via exchange rate)      │
│  - data_scope categories mapping defined                            │
│  - time_window timezone conversion                                  │
│                                                                     │
│  STEP 4: Translate to target vocabulary                             │
│  ───────────────────────────────────────                            │
│  {                                                                  │
│    "budget_limit_eur": {                                            │
│      "betrag": 920,  // 1000 * 0.92                                 │
│      "waehrung": "EUR",                                             │
│      "zeitraum": "pro_vorgang"                                      │
│    },                                                               │
│    "datenzugriff": {                                                │
│      "kategorien": ["finanzen"],                                    │
│      "zeitlich": ["Q4-2024"]                                        │
│    },                                                               │
│    "arbeitszeit": {                                                 │
│      "beginn": "18:00",  // 9:00 PST = 18:00 CET                    │
│      "ende": "02:00",    // 17:00 PST = 02:00 CET (next day)        │
│      "zeitzone": "Europe/Berlin",                                   │
│      "wiederholung": "werktags"                                     │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  STEP 5: Merge with target's local constraints (tightening only)    │
│  ─────────────────────────────────────────────────────────────────  │
│  Apply EATP constraint tightening rule:                             │
│  - monetary: use minimum amount                                     │
│  - data_scope: use intersection of categories                       │
│  - time_window: use intersection of time ranges                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Trust Level Interoperability

### 4.1 Trust Level Mismatch

**Org A's Trust Postures (5 levels):**

1. MINIMAL - Basic identity only
2. CONSTRAINED - Specific constraints
3. SUPERVISED - Requires human approval
4. AUTONOMOUS - Full independence
5. ORCHESTRATOR - Can delegate to others

**Org B's Trust Levels (3 levels):**

1. VIEWER - Read-only access
2. CONTRIBUTOR - Can modify
3. ADMIN - Full control

**Challenge:** How to map Org A's "AUTONOMOUS" to Org B's system?

### 4.2 Trust Level Mapping Framework

```python
@dataclass
class TrustLevelMapping:
    """Mapping between trust level systems."""

    source_system: str                    # "org-a-postures"
    target_system: str                    # "org-b-levels"
    mappings: Dict[str, str]              # source -> target
    confidence: float                     # 0.0 - 1.0
    restrictions: Dict[str, List[str]]    # Additional constraints per mapping

EXAMPLE_MAPPING = TrustLevelMapping(
    source_system="org-a-postures",
    target_system="org-b-levels",
    mappings={
        "MINIMAL": "VIEWER",
        "CONSTRAINED": "VIEWER",
        "SUPERVISED": "CONTRIBUTOR",
        "AUTONOMOUS": "CONTRIBUTOR",  # Downgrade: no ADMIN
        "ORCHESTRATOR": "CONTRIBUTOR",  # Downgrade: no ADMIN
    },
    confidence=0.85,
    restrictions={
        "AUTONOMOUS": ["no_delete", "requires_review"],
        "ORCHESTRATOR": ["no_delete", "requires_review", "no_subdelegation"],
    }
)
```

### 4.3 Trust Level Negotiation Protocol

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TRUST LEVEL NEGOTIATION                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  STEP 1: Agent A declares trust level                               │
│  ─────────────────────────────────────                              │
│  {                                                                  │
│    "agent_id": "agent-a-001",                                       │
│    "source_trust_level": "AUTONOMOUS",                              │
│    "source_trust_system": "org-a-postures-v2",                      │
│    "capabilities_requested": ["analyze_data", "write_report"]       │
│  }                                                                  │
│                                                                     │
│  STEP 2: Org B looks up TLA mapping                                 │
│  ───────────────────────────────────                                │
│  TLA tla-123 defines:                                               │
│    org-a-postures-v2:AUTONOMOUS -> org-b-levels-v1:CONTRIBUTOR      │
│    restrictions: ["no_delete", "requires_review"]                   │
│                                                                     │
│  STEP 3: Org B evaluates mapped level against request               │
│  ─────────────────────────────────────────────────────              │
│  - CONTRIBUTOR can "analyze_data": YES                              │
│  - CONTRIBUTOR can "write_report": CONDITIONAL (requires_review)    │
│                                                                     │
│  STEP 4: Org B responds with effective trust                        │
│  ───────────────────────────────────────────                        │
│  {                                                                  │
│    "effective_trust_level": "CONTRIBUTOR",                          │
│    "effective_trust_system": "org-b-levels-v1",                     │
│    "capabilities_granted": ["analyze_data"],                        │
│    "capabilities_conditional": {                                    │
│      "write_report": {                                              │
│        "requires": "review_before_publish",                         │
│        "reviewer": "human@org-b.com"                                │
│      }                                                              │
│    },                                                               │
│    "capabilities_denied": []                                        │
│  }                                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 2: A2A-EATP Trust Lineage and Mutual Authentication

## 2. Trust Lineage Extension Across A2A Calls

### 2.1 The Cross-Boundary Trust Challenge

When Org A's agent calls Org B's agent via A2A:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CURRENT SINGLE-ORG MODEL                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ORG A                              ORG A (same org)               │
│   ┌──────────┐                       ┌──────────┐                   │
│   │ Agent A  │ ──── A2A + EATP ───→  │ Agent B  │                   │
│   │          │        Token          │          │                   │
│   └────┬─────┘                       └────┬─────┘                   │
│        │                                  │                         │
│        │ genesis: org-A                   │ genesis: org-A          │
│        │ Same trust root ✓                │ Same trust root ✓       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CROSS-ORG MODEL (UNSUPPORTED)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ORG A                              ORG B (different org)          │
│   ┌──────────┐                       ┌──────────┐                   │
│   │ Agent A  │ ──── A2A + EATP ───→  │ Agent B  │                   │
│   │          │        Token          │          │                   │
│   └────┬─────┘                       └────┬─────┘                   │
│        │                                  │                         │
│        │ genesis: org-A                   │ genesis: org-B          │
│        │                                  │                         │
│        └──────────── ? ──────────────────┘                          │
│          How does Org B trust Org A's genesis?                      │
│          Who vouches for cross-org trust?                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Trust Chain Serialization Requirements

For cross-org A2A calls, the full trust chain must be serializable and transmittable:

**Current Serialization (from `chain.py:693-759`):**

```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "genesis": {...},          # ~200 bytes
        "capabilities": [...],     # ~500 bytes per capability
        "delegations": [...],      # ~400 bytes per delegation
        "constraint_envelope": {...},  # ~300 bytes
        "chain_hash": self.hash(), # 64 bytes
    }
```

**Cross-Org Extension Required:**

```python
def to_cross_org_dict(self) -> Dict[str, Any]:
    return {
        "genesis": {...},
        "genesis_proof": {
            "issuing_org_signature": str,     # Org A signs genesis
            "issuing_org_certificate": str,   # Org A's public cert
            "trust_registry_attestation": str, # Registry vouches for Org A
        },
        "capabilities": [...],
        "delegations": [...],
        "constraint_envelope": {...},
        "cross_org_policies": {
            "constraint_translation": {...},  # How constraints map
            "liability_terms": str,           # Legal terms reference
            "audit_sharing": str,             # Audit trail sharing policy
        },
        "chain_hash": self.hash(),
    }
```

**Size Implications:**

- Single-org chain: ~2-5 KB typical
- Cross-org chain: ~10-20 KB with proofs and policies
- Performance impact: Additional 5-10ms for serialization/deserialization

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

## 3. Mutual Authentication Between Organizations

### 3.1 Current Authentication Model

From `auth.py:72-123`:

```python
async def create_token(
    self,
    audience: str,
    capabilities: Optional[list[str]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    # Get trust chain for this agent
    chain = await self._trust_ops.get_chain(self._agent_id)
    if not chain:
        raise AuthenticationError(...)

    token_data = A2AToken(
        sub=self._agent_id,
        iss=self._agent_id,
        aud=audience,
        exp=now + timedelta(seconds=ttl_seconds),
        iat=now,
        jti=str(uuid.uuid4()),
        authority_id=chain.genesis.authority_id,  # Single org
        trust_chain_hash=chain.hash(),
        capabilities=capabilities or [],
        constraints=constraints,
    )
```

**Gap:** This only works when both agents share the same `authority_id` root.

### 3.2 Cross-Org Mutual Authentication Design

**Proposed Enhancement:**

```python
@dataclass
class CrossOrgA2AToken(A2AToken):
    """Extended token for cross-organizational authentication."""

    # Existing fields from A2AToken
    # ...

    # Cross-org extensions
    issuer_org_id: str                    # Org A's identifier
    issuer_org_certificate: str           # Org A's X.509 or DID certificate
    target_org_id: str                    # Org B's identifier
    trust_agreement_id: Optional[str]     # TLA reference
    constraint_translation_hash: str      # Hash of constraint mapping

    # Mutual authentication
    mutual_auth_challenge: str            # Challenge for recipient
    mutual_auth_response_endpoint: str    # Where to send response

    def to_claims(self) -> Dict[str, Any]:
        claims = super().to_claims()
        claims.update({
            "iss_org": self.issuer_org_id,
            "iss_org_cert": self.issuer_org_certificate,
            "aud_org": self.target_org_id,
            "tla_id": self.trust_agreement_id,
            "constraint_tx_hash": self.constraint_translation_hash,
            "mutual_auth": {
                "challenge": self.mutual_auth_challenge,
                "response_endpoint": self.mutual_auth_response_endpoint,
            },
        })
        return claims
```

### 3.3 Mutual Authentication Protocol

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MUTUAL AUTHENTICATION HANDSHAKE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  PHASE 1: Agent A → Agent B (Initial Request)                          │
│  ───────────────────────────────────────────────                        │
│                                                                         │
│  POST /a2a/jsonrpc                                                      │
│  Authorization: Bearer <cross-org-jwt-a>                                │
│  Content-Type: application/json                                         │
│                                                                         │
│  {                                                                      │
│    "jsonrpc": "2.0",                                                    │
│    "method": "trust.initiate_mutual_auth",                              │
│    "params": {                                                          │
│      "challenge_a": "random-32-bytes-hex-a",                            │
│      "org_a_genesis_proof": {...},                                      │
│      "tla_reference": "tla-123"                                         │
│    },                                                                   │
│    "id": 1                                                              │
│  }                                                                      │
│                                                                         │
│  PHASE 2: Agent B → Agent A (Challenge Response + Counter-Challenge)   │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  Response:                                                              │
│  {                                                                      │
│    "jsonrpc": "2.0",                                                    │
│    "result": {                                                          │
│      "challenge_a_response": "sign(challenge_a, agent_b_key)",          │
│      "challenge_b": "random-32-bytes-hex-b",                            │
│      "org_b_genesis_proof": {...},                                      │
│      "session_id": "session-uuid"                                       │
│    },                                                                   │
│    "id": 1                                                              │
│  }                                                                      │
│                                                                         │
│  PHASE 3: Agent A → Agent B (Complete Handshake)                        │
│  ──────────────────────────────────────────────────                     │
│                                                                         │
│  POST /a2a/jsonrpc                                                      │
│  Authorization: Bearer <cross-org-jwt-a>                                │
│  X-EATP-Session: session-uuid                                           │
│                                                                         │
│  {                                                                      │
│    "jsonrpc": "2.0",                                                    │
│    "method": "trust.complete_mutual_auth",                              │
│    "params": {                                                          │
│      "challenge_b_response": "sign(challenge_b, agent_a_key)",          │
│      "session_id": "session-uuid"                                       │
│    },                                                                   │
│    "id": 2                                                              │
│  }                                                                      │
│                                                                         │
│  RESULT: Mutual authentication established                              │
│  - Both agents verified each other's genesis proofs                     │
│  - Session ID can be used for subsequent calls                          │
│  - Session has TTL based on TLA terms                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Constraint Reconciliation

### 4.1 The Constraint Conflict Problem

**Scenario:** Org A's agent has constraint `max_cost_usd: 1000`. Org B's system uses `budget_limit_eur`. How do these reconcile?

**Current Constraint Model (from `chain.py:298-319`):**

```python
@dataclass
class Constraint:
    id: str
    constraint_type: ConstraintType
    value: Any
    source: str
    priority: int = 0

class ConstraintType(Enum):
    RESOURCE_LIMIT = "resource_limit"
    TIME_WINDOW = "time_window"
    DATA_SCOPE = "data_scope"
    ACTION_RESTRICTION = "action_restriction"
    AUDIT_REQUIREMENT = "audit_requirement"
```

**Gap:** No semantic constraint vocabulary or translation mechanism.

### 4.2 Constraint Translation Architecture

**Proposed Constraint Translation Layer:**

```python
@dataclass
class ConstraintVocabulary:
    """Standard vocabulary for cross-org constraint translation."""

    namespace: str                        # e.g., "eatp.org/v1"
    constraint_types: Dict[str, str]      # Local name -> Standard name
    unit_mappings: Dict[str, str]         # Local unit -> Standard unit
    value_transformers: Dict[str, Callable]  # Conversion functions

@dataclass
class ConstraintTranslation:
    """Translation rule between two organizations' constraint systems."""

    source_org: str
    target_org: str
    source_constraint: str
    target_constraint: str
    translation_rule: str                 # Expression or function reference
    requires_runtime_context: bool        # e.g., exchange rate lookup

# Example Translation Rules
STANDARD_TRANSLATIONS = {
    ("max_cost_usd", "budget_limit_eur"): {
        "rule": "source_value * get_exchange_rate('USD', 'EUR')",
        "requires_runtime_context": True,
    },
    ("business_hours_pst", "business_hours_cet"): {
        "rule": "shift_timezone(source_value, 'PST', 'CET')",
        "requires_runtime_context": False,
    },
    ("read_only", "schreibschutz"): {  # German equivalent
        "rule": "source_value",  # Direct mapping
        "requires_runtime_context": False,
    },
}
```

### 4.3 Constraint Reconciliation Protocol

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONSTRAINT RECONCILIATION FLOW                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  INPUT: Agent A's constraints + Agent B's capabilities                  │
│                                                                         │
│  STEP 1: Extract constraints from Agent A's request                     │
│  ─────────────────────────────────────────────────                      │
│  Agent A constraints:                                                   │
│    - max_cost_usd: 1000                                                 │
│    - data_scope: ["finance", "q4_2024"]                                 │
│    - audit_level: "full"                                                │
│                                                                         │
│  STEP 2: Load TLA constraint mapping                                    │
│  ───────────────────────────────────                                    │
│  TLA tla-123 defines:                                                   │
│    max_cost_usd -> budget_limit_eur (via exchange rate)                 │
│    data_scope -> datenzugriff (direct mapping)                          │
│    audit_level -> pruefungsstufe (value mapping: full->vollstaendig)    │
│                                                                         │
│  STEP 3: Translate constraints                                          │
│  ───────────────────────────────                                        │
│  Translated to Org B vocabulary:                                        │
│    - budget_limit_eur: 920 (1000 * 0.92 exchange rate)                  │
│    - datenzugriff: ["finanzen", "q4_2024"]                              │
│    - pruefungsstufe: "vollstaendig"                                     │
│                                                                         │
│  STEP 4: Merge with Agent B's local constraints                         │
│  ─────────────────────────────────────────────────                      │
│  Agent B's own constraints:                                             │
│    - budget_limit_eur: 5000 (higher - not restrictive)                  │
│    - datenzugriff: ["finanzen"] (more restrictive - use this)           │
│    - pruefungsstufe: "standard" (less restrictive - use translated)     │
│                                                                         │
│  RESULT: Effective constraints for operation                            │
│  ──────────────────────────────────────────────                         │
│    - budget_limit_eur: 920 (stricter of 920 vs 5000)                    │
│    - datenzugriff: ["finanzen"] (intersection)                          │
│    - pruefungsstufe: "vollstaendig" (stricter of full vs standard)      │
│                                                                         │
│  PRINCIPLE: Constraints can only be TIGHTENED, never loosened           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---
