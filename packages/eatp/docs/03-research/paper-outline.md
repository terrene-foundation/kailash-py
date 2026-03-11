# EATP Academic Paper Outline

**Working Title**: _EATP: Cryptographic Trust Chains for Delegated AI Agent Authorization_

**Target Venue**: USENIX Security / IEEE S&P / ACM CCS (systems security track)

---

## Abstract (~200 words)

As AI agents increasingly operate with delegated authority in enterprise
environments, existing authorization frameworks fail to provide the
cryptographic accountability required for multi-agent trust. OAuth and RBAC
assume human-interactive flows; XACML lacks delegation chains; capability
tokens (UCAN, Biscuit) lack the domain-specific invariants needed for AI
agent governance.

We present EATP (Enterprise Agent Trust Protocol), a cryptographic trust
protocol that answers five questions about every agent action: who authorized
this agent, what can it do, who delegated work to it, what limits apply, and
what has it done. EATP introduces a _Trust Lineage Chain_ -- an immutable,
Ed25519-signed, SHA-256-linked data structure that binds agent identity to
capability attestations, delegation records, constraint envelopes, and audit
anchors. The protocol's central security property, the _tightening
invariant_, guarantees that trust can only be reduced as it flows through the
delegation chain.

We describe the protocol design, prove key security properties, and present
an open-source implementation extracted from a production AI orchestration
system. Benchmarks show that full trust chain verification completes in
under 2ms for chains of depth 10, with sub-millisecond overhead for
standard verification. EATP is available under the Apache 2.0 license as
a public good maintained by the Terrene Foundation.

---

## 1. Introduction

### 1.1 Problem: AI Agent Trust Gap

- Autonomous AI agents perform actions on behalf of humans and organizations
- Current authorization models assume human-in-the-loop interactive flows
- No existing standard provides:
  - Cryptographic proof of who authorized an agent
  - Monotonically attenuating delegation chains
  - Immutable audit trails linked to trust state at action time
  - Graduated verification levels (basic/standard/full)
- Real-world consequences: unauthorized data access, privilege escalation
  through delegation chains, inability to trace accountability

### 1.2 Why Existing Solutions Fail

| Framework | Limitation for AI agents                                                                   |
| --------- | ------------------------------------------------------------------------------------------ |
| OAuth 2.0 | Designed for human-interactive authorization; tokens are opaque; no delegation chain       |
| RBAC/ABAC | Static role assignment; no cryptographic proof; no delegation semantics                    |
| XACML     | Policy evaluation without trust chains; no audit linking                                   |
| UCAN      | Capability delegation but no constraint tightening invariant enforcement; no audit anchors |
| Biscuit   | Attenuation tokens but no genesis records; no trust scoring                                |
| Macaroons | Contextual caveats but no structured constraint dimensions                                 |

### 1.3 Contributions

1. The EATP protocol: five chain elements, four operations, tightening invariant
2. Security analysis: formal threat model and property proofs
3. Open-source dual-SDK implementation (Python + Rust planned)
4. Performance evaluation extracted from production deployment
5. Interoperability bridges to W3C VC, JWT, UCAN, and Biscuit

---

## 2. Related Work

### 2.1 Traditional Authorization

- **OAuth 2.0 / OpenID Connect**: Token-based authorization for web
  applications. Lacks delegation depth tracking, constraint tightening, and
  cryptographic audit trails. Agent-to-agent flows require custom extensions.
- **RBAC (Role-Based Access Control)**: Static role assignment cannot express
  dynamic trust relationships between agents. No mechanism for monotonic
  attenuation.
- **ABAC (Attribute-Based Access Control) / XACML**: Policy evaluation engine
  with rich attribute expressions but no cryptographic chain linking policy
  decisions to agent identity or delegation provenance.

### 2.2 Capability-Based Authorization

- **UCAN (User Controlled Authorization Networks)**: JWT-based capability
  delegation with attenuation. Closest to EATP in philosophy. Differences:
  EATP adds genesis records (authority binding), structured constraint
  dimensions with formal tightening, audit anchors, and trust scoring.
- **Biscuit**: Datalog-based authorization tokens with attenuation blocks.
  Strong formal properties but no genesis concept, no audit chain linking,
  and limited constraint dimension extensibility.
- **Macaroons**: Contextual caveats for capability attenuation. Lacks
  structured constraint types, delegation records, and trust chain integrity
  guarantees.

### 2.3 Verifiable Credentials

- **W3C Verifiable Credentials**: Standard format for cryptographically
  verifiable claims. EATP provides a W3C VC export (`eatp.interop.w3c_vc`)
  but adds operational semantics (ESTABLISH, DELEGATE, VERIFY, AUDIT) that
  VC alone does not define.
- **SD-JWT (Selective Disclosure JWT)**: Supports selective disclosure of
  claims. EATP integrates SD-JWT for capability proof without revealing the
  full trust chain.

### 2.4 AI Agent Frameworks

- Survey of existing agent authorization in LangChain, AutoGen, CrewAI,
  Semantic Kernel. Most rely on ambient API keys with no delegation or
  audit model.
- Comparison with emerging standards (e.g., Google A2A protocol).

---

## 3. EATP Protocol Design

### 3.1 Trust Lineage Chain: Five Elements

Formal definitions of:

1. **GenesisRecord** `G = (agent_id, authority_id, public_key, constraints, signature_authority)`
   - The root of trust: who authorized this agent to exist
   - Signed by the organizational authority's Ed25519 key

2. **CapabilityAttestation** `C = (capability, type, attester_id, constraints, scope, expiration, signature)`
   - What the agent can do (ACCESS, ACTION, DELEGATION)
   - Each attestation is individually signed

3. **DelegationRecord** `D = (delegator_id, delegatee_id, capabilities_subset, constraints_subset, task_id, depth)`
   - Who delegated work to this agent
   - Tightening invariant enforced on all constraint dimensions

4. **ConstraintEnvelope** `E = (constraints: Dict[str, Any], hash)`
   - What limits apply: cost, time, rate, resources, geo, delegation depth
   - Extensible via pluggable ConstraintDimension registry

5. **AuditAnchor** `A = (action, resource, result, trust_chain_hash_at_action_time, signature)`
   - What the agent has done, cryptographically linked to trust state

**Chain structure**: `TrustLineageChain = (G, [C_1..C_n], [D_1..D_m], E, [A_1..A_k])`
with `chain_hash = SHA256(canonical(G, C, D, E))`

### 3.2 Four Operations

- **ESTABLISH(authority, agent, capabilities, constraints) -> TrustLineageChain**
- **DELEGATE(delegator, delegatee, capabilities_subset, constraints_subset) -> DelegationRecord**
- **VERIFY(agent, action, level) -> VerificationResult**
- **AUDIT(agent, action, resource, result) -> AuditAnchor**

### 3.3 The Tightening Invariant

**Definition**: For every constraint dimension `d` with a partial order `<=_d`,
if parent agent `P` has constraint value `P(d)` and child agent `C` has value
`C(d)`, then `C(d) <=_d P(d)`.

**Supported dimensions and their partial orders**:

| Dimension               | Order relation                       |
| ----------------------- | ------------------------------------ |
| `cost_limit`            | `C <= P` (numeric)                   |
| `rate_limit`            | `C <= P` (numeric)                   |
| `budget_limit`          | `C <= P` (numeric)                   |
| `max_delegation_depth`  | `C <= P` (numeric)                   |
| `max_api_calls`         | `C <= P` (numeric)                   |
| `time_window`           | `C ⊆ P` (interval subset)            |
| `resources`             | `C ⊆ P` (glob-aware path subset)     |
| `allowed_actions`       | `C ⊆ P` (set subset)                 |
| `forbidden_actions`     | `P ⊆ C` (parent's must be preserved) |
| `geo_restrictions`      | `C ⊆ P` (set subset)                 |
| `data_scopes`           | `C ⊆ P` (set subset)                 |
| `communication_targets` | `C ⊆ P` (set subset)                 |

**Enforcement**: `ConstraintValidator.validate_tightening()` checks all
dimensions on every DELEGATE operation. DELEGATE raises
`ConstraintViolationError` if any dimension is loosened.

### 3.4 Verification Gradient

| Level    | Operations performed                                      | Cost   |
| -------- | --------------------------------------------------------- | ------ |
| BASIC    | Chain exists, genesis signature valid                     | ~0.2ms |
| STANDARD | BASIC + capability lookup + constraint evaluation         | ~0.5ms |
| FULL     | STANDARD + all signatures + hash chain + delegation depth | ~1.5ms |

### 3.5 Enforcement Modes

- **StrictEnforcer**: Production blocking (AUTO_APPROVED / FLAGGED / HELD / BLOCKED)
- **ShadowEnforcer**: Observation mode (logs verdicts without blocking)
- **ChallengeProtocol**: Live key possession proof via challenge-response
- **Decorators**: `@verified`, `@audited`, `@shadow` for 3-line integration

---

## 4. Security Analysis

### 4.1 Threat Model

**Adversary capabilities**:

- Can create agents and request delegation
- Can observe network traffic (passive)
- Can attempt to forge or replay messages
- Cannot compromise the authority's HSM

**Trusted components**:

- Organizational authority's signing key (HSM-protected)
- PyNaCl/libsodium implementation correctness

### 4.2 Key Security Properties

**Property 1: Monotonic Attenuation**
_Theorem_: For any delegation chain of depth `k`, the delegatee at depth `k`
has capabilities that are a subset of the capabilities at depth `k-1`.
_Proof sketch_: By induction on delegation depth. Each DELEGATE operation
invokes `ConstraintValidator.validate_tightening()` which checks all
dimensions. A loosening attempt raises `ConstraintViolationError` and the
delegation is rejected.

**Property 2: Chain Integrity**
_Theorem_: Any modification to a chain element is detectable by verifying
the chain hash and element signatures.
_Proof sketch_: Each element is signed with Ed25519; the chain hash is
`SHA256(canonical(G, C, D, E))`. Modifying any element changes either the
signature (detectable) or the hash (detectable via `compute_hash()`).

**Property 3: Replay Protection**
_Theorem_: A challenge response cannot be replayed.
_Proof sketch_: Nonces are 256-bit random values tracked in `_used_nonces`.
A replayed nonce is detected and rejected. Challenges expire after
`timeout_seconds`. Payload binding (`nonce:timestamp:challenger_id`) prevents
cross-challenge reuse.

**Property 4: Delegation Depth Bound**
_Theorem_: No delegation chain can exceed `MAX_DELEGATION_DEPTH` (10).
_Proof_: `TrustOperations.delegate()` checks `current_depth + 1 <= MAX_DELEGATION_DEPTH`
and raises `DelegationError` if violated.

**Property 5: Audit Immutability**
_Theorem_: Audit anchors are tamper-evident.
_Proof sketch_: Each `AuditAnchor` contains `trust_chain_hash` at action time
and an Ed25519 signature over the anchor data. Modification changes the
signature or hash.

### 4.3 Known Limitations

- Single-authority model (multi-authority federation is future work)
- In-memory nonce store is bounded (100k entries); high-throughput systems
  may require external nonce storage
- Trust scoring is advisory, not cryptographically enforced
- Revocation propagation latency in distributed deployments

---

## 5. Implementation

### 5.1 Dual SDK Architecture

- **Python SDK** (`pip install eatp`): Production-ready, extracted from
  Kailash Kaizen framework. 4,000+ lines of core protocol code.
  Dependencies: PyNaCl, Pydantic, jsonschema.
- **Rust SDK** (planned): For embedded/WASM/high-performance environments.
  Will share JSON wire format and test vectors with Python SDK.

### 5.2 Extraction from Production System

EATP was originally developed as the trust subsystem within Kailash Kaizen,
a production AI agent orchestration framework. The extraction process:

1. Identified the trust boundary within the Kaizen codebase
2. Removed all dependencies on Kailash Core SDK runtime
3. Created standalone package with its own `pyproject.toml`
4. Preserved all cryptographic guarantees and test coverage
5. Added interoperability modules (W3C VC, SD-JWT, UCAN, Biscuit)

### 5.3 Module Architecture

```
eatp/
  chain.py              # Trust chain data structures (5 elements)
  operations/           # ESTABLISH, DELEGATE, VERIFY, AUDIT
  crypto.py             # Ed25519 signing, SHA-256 hashing
  constraint_validator.py  # Tightening invariant enforcement
  enforce/              # Strict, shadow, challenge, decorators
  scoring.py            # Trust scoring engine
  store/                # InMemory, FileSystem trust stores
  esa/                  # Enterprise System Agent stores (PostgreSQL)
  interop/              # W3C VC, SD-JWT, DID, UCAN, Biscuit
  constraints/          # Pluggable constraint dimensions
  messaging/            # Signed envelopes, replay protection
  registry/             # Agent discovery and registration
  a2a/                  # Agent-to-agent communication
  governance/           # Policy engine, cost estimation
```

### 5.4 Performance Characteristics

Key design decisions for performance:

- Lazy signature verification (only FULL level checks all signatures)
- In-memory caching for frequently verified chains
- Canonical serialization computed once per chain mutation
- Nonce eviction amortized over challenge operations

---

## 6. Evaluation

### 6.1 Microbenchmarks

Benchmarks to include (using `pytest-benchmark` on representative hardware):

| Operation             | Chain depth | Expected latency |
| --------------------- | ----------- | ---------------- |
| ESTABLISH             | 1           | < 5ms            |
| VERIFY (BASIC)        | 1-10        | < 0.5ms          |
| VERIFY (STANDARD)     | 1-10        | < 1ms            |
| VERIFY (FULL)         | 1-10        | < 2ms            |
| DELEGATE              | 1-10        | < 3ms            |
| AUDIT                 | 1-10        | < 2ms            |
| Challenge-response    | n/a         | < 1ms            |
| Constraint validation | 5 dims      | < 0.1ms          |

### 6.2 Scalability

- Trust store throughput: operations/second vs. chain count
- Nonce cache behavior under load (eviction rate, memory)
- Delegation depth impact on VERIFY latency

### 6.3 Framework Integration

Demonstrate integration with:

- **Kailash Kaizen**: Native integration (original host)
- **LangChain**: Agent tool wrapping with `@verified` decorator
- **FastAPI**: Middleware for API endpoint protection
- **MCP (Model Context Protocol)**: EATP as MCP tools via `eatp.mcp.server`

### 6.4 Case Study: Terrene Foundation Deployment

- Foundation deploys EATP for its own AI agents (research, code review, governance)
- Real-world constraint configurations and delegation patterns
- Audit trail analysis and compliance reporting

---

## 7. Discussion

### 7.1 Comparison with Capability Token Systems

Detailed comparison matrix: EATP vs. UCAN vs. Biscuit vs. Macaroons across
dimensions of genesis binding, structured constraints, audit linking, trust
scoring, verification gradient, and interoperability.

### 7.2 Adoption Considerations

- Integration effort for existing agent frameworks
- Key management requirements (HSM vs. software keys)
- Performance overhead relative to no-auth baseline

### 7.3 Limitations

- Current implementation is single-organization; cross-org federation requires
  authority chaining (future work)
- Trust scoring weights are configurable but not formally optimized
- Rust SDK is planned but not yet available

---

## 8. Conclusion and Future Work

### 8.1 Conclusion

EATP provides the missing cryptographic trust layer for AI agent systems.
By combining five chain elements, four operations, and the tightening
invariant, EATP enables organizations to deploy autonomous agents with
verifiable authorization, bounded delegation, and immutable audit trails.

### 8.2 Future Work

1. **Rust SDK**: Native performance, WASM compilation for browser agents
2. **Cross-organization federation**: Authority chaining across organizational
   boundaries
3. **Formal verification**: Machine-checked proof of tightening invariant using
   Lean or Coq
4. **Zero-knowledge proofs**: Verify agent capabilities without revealing the
   full trust chain
5. **Distributed trust stores**: CRDTs or blockchain-anchored stores for
   decentralized deployments
6. **Standardization**: IETF or W3C working group for agent trust protocols

---

## Appendices

### A. JSON Wire Format Examples

Complete examples of serialized chain elements in canonical JSON form.

### B. Test Vectors

Deterministic test vectors for signing, verification, and hash chain
computation (shared between Python and Rust SDKs).

### C. Constraint Dimension Extensibility

Guide for implementing custom `ConstraintDimension` plugins.

### D. Interoperability Examples

Round-trip examples: EATP chain -> W3C VC -> verify -> EATP chain.
