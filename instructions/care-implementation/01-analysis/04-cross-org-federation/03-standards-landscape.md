# Standards Landscape

> Standards landscape analysis for EATP cross-organizational federation - current A2A implementation assessment, constraint reconciliation, performance benchmarks, and risk analysis.

> **Note**: The original agent analysis produced the A2A-EATP interoperability study covering how EATP integrates with Google A2A, existing authentication standards, and cross-org protocol design. A dedicated deep-dive into W3C Verifiable Credentials, DIDs, SPIFFE/SPIRE, OAuth 2.0/OIDC, and X.509/PKI mapping was planned as File 3 but was not completed in the original analysis pass due to output length constraints.

---

## Executive Summary

This analysis examines how EATP (Enterprise Agent Trust Protocol) can integrate with Google's A2A (Agent-to-Agent) protocol for cross-organizational agent communication. The current implementation provides a solid foundation with TrustExtensions in Agent Cards, JWT-based authentication, and JSON-RPC methods for trust operations. However, significant gaps exist for true cross-organizational federation.

**Complexity Score: Enterprise (28 points)**

- Technical: 12/15 (Ed25519 crypto across HTTP boundaries, chain serialization, mutual auth)
- Business: 9/10 (multi-org liability, constraint reconciliation, compliance)
- Operational: 7/10 (distributed verification, audit continuity, revocation propagation)

---

## 1. Current A2A Implementation Assessment

### 1.1 Existing Components

The current implementation in `/apps/kailash-kaizen/src/kaizen/trust/a2a/` provides:

| Component          | File            | Purpose                                   | Cross-Org Readiness              |
| ------------------ | --------------- | ----------------------------------------- | -------------------------------- |
| A2AService         | `service.py`    | FastAPI HTTP service                      | Partial - single org only        |
| AgentCardGenerator | `agent_card.py` | Generate Agent Cards with TrustExtensions | Partial - needs cross-org fields |
| A2AAuthenticator   | `auth.py`       | JWT token creation/verification           | Partial - single trust root      |
| JsonRpcHandler     | `jsonrpc.py`    | JSON-RPC 2.0 method dispatch              | Ready - protocol-agnostic        |
| TrustExtensions    | `models.py`     | EATP extensions for Agent Cards           | Partial - single genesis         |

### 1.2 Current TrustExtensions Structure

From `models.py:42-72`:

```python
@dataclass
class TrustExtensions:
    trust_chain_hash: str
    genesis_authority_id: str
    genesis_authority_type: str
    verification_endpoint: Optional[str] = None
    delegation_endpoint: Optional[str] = None
    capabilities_attested: Optional[List[str]] = None
    constraints: Optional[Dict[str, Any]] = None
```

**Gap Analysis:**

- No field for cross-organizational genesis recognition
- No field for trust level/posture mapping
- No field for federated constraint policies
- No field for cross-org revocation endpoints

### 1.3 Current A2AToken Structure

From `models.py:217-271`:

```python
@dataclass
class A2AToken:
    # Standard JWT claims
    sub: str  # agent_id
    iss: str  # issuing agent_id
    aud: str  # target agent_id
    exp: datetime
    iat: datetime
    jti: str
    # EATP claims
    authority_id: str
    trust_chain_hash: str
    capabilities: List[str] = field(default_factory=list)
    constraints: Optional[Dict[str, Any]] = None
```

**Gap Analysis:**

- `authority_id` is from issuer's organization only
- No claim for recipient's expected authority validation
- No claim for cross-org trust agreement reference
- No claim for constraint translation rules

---

## 6. Performance Implications

### 6.1 Current Single-Org Performance

From `chain.py:59-64`:

```python
class VerificationLevel(Enum):
    QUICK = "quick"      # Hash + expiration only (~1ms)
    STANDARD = "standard"  # + Capability match, constraints (~5ms)
    FULL = "full"        # + Signature verification (~50ms)
```

### 6.2 Cross-Org Performance Impact

| Operation              | Single-Org | Cross-Org | Delta                           |
| ---------------------- | ---------- | --------- | ------------------------------- |
| QUICK verification     | ~1ms       | ~5ms      | +4ms (network)                  |
| STANDARD verification  | ~5ms       | ~50ms     | +45ms (chain fetch + translate) |
| FULL verification      | ~50ms      | ~200ms    | +150ms (multi-sig verify)       |
| Mutual auth handshake  | N/A        | ~100ms    | New requirement                 |
| Constraint translation | N/A        | ~10ms     | New requirement                 |
| Cross-org audit write  | ~5ms       | ~30ms     | +25ms (multi-store)             |

### 6.3 Optimization Strategies

1. **Session Caching**: After mutual auth, cache session for 15-60 minutes
2. **Constraint Translation Cache**: Pre-compute common translations
3. **Batch Verification**: Verify multiple operations in single round-trip
4. **Async Audit**: Write cross-org audit asynchronously
5. **Genesis Proof Caching**: Cache verified genesis proofs for 1 hour

---

## 7. Risk Register

| Risk                           | Likelihood | Impact   | Mitigation                                   |
| ------------------------------ | ---------- | -------- | -------------------------------------------- |
| Genesis proof forgery          | Low        | Critical | Multi-signature from Trust Registry          |
| Man-in-the-middle on handshake | Medium     | High     | TLS 1.3 + certificate pinning                |
| Constraint translation errors  | Medium     | High     | Formal verification of translation rules     |
| Audit trail discontinuity      | Medium     | Medium   | Hash-based linking + periodic reconciliation |
| Revocation propagation delay   | High       | Medium   | Push notifications + TTL-based expiry        |
| Performance degradation        | High       | Medium   | Caching + async patterns                     |

---
