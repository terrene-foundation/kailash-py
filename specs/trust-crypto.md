# Trust Plane -- Cryptography, Stores, RBAC, and Interop

Parent domain: Kailash Trust Plane. This sub-spec covers Ed25519 signing, AES-256-GCM encryption at rest, store backends (in-memory, SQLite, filesystem), agent identity, key management, trust roles and RBAC, trust scoring, reasoning traces, the hook system, the exception hierarchy, cost event tracking, integration with PACT and DataFlow, OrganizationalAuthority, interoperability, messaging, revocation, security invariants, and cross-SDK alignment. See `trust-eatp.md` for the EATP protocol and `trust-posture.md` for posture and budget management.

---

## 12. Ed25519 Signing

### 12.1 Key Generation

```python
generate_keypair() -> Tuple[str, str]  # (private_key_base64, public_key_base64)
```

Uses PyNaCl's `SigningKey.generate()`. Keys are base64-encoded for storage and transport.

### 12.2 Signing

```python
sign(payload: Union[bytes, str, dict], private_key: str) -> str
```

Dict payloads are first processed through `serialize_for_signing()` which produces deterministic canonical JSON (sorted keys, no whitespace, UTC datetimes). The signature is base64-encoded.

### 12.3 Verification

```python
verify_signature(payload: Union[bytes, str, dict], signature: str, public_key: str) -> bool
```

Returns `True` if the signature is valid, `False` otherwise. Raises `InvalidSignatureError` for malformed inputs.

### 12.4 Dual Signing

```python
@dataclass
class DualSignature:
    ed25519_signature: str
    hmac_signature: str

dual_sign(payload, ed25519_private_key, hmac_key) -> DualSignature
dual_verify(payload, dual_sig, ed25519_public_key, hmac_key) -> bool
```

Combines Ed25519 (non-repudiation) with HMAC-SHA256 (fast internal verification). HMAC alone is NEVER sufficient for external verification.

### 12.5 Reasoning Trace Signing

```python
sign_reasoning_trace(trace: ReasoningTrace, private_key: str) -> str
hash_reasoning_trace(trace: ReasoningTrace) -> str
verify_reasoning_signature(trace: ReasoningTrace, signature: str, public_key: str) -> bool
```

Reasoning traces have a separate signature that is independent of the parent record signature. The trace hash is included in the parent record's signing payload for dual binding.

### 12.6 Key Derivation

```python
derive_key_with_salt(master_key, salt, key_length=32, iterations=100000) -> Tuple[bytes, bytes]
```

PBKDF2-HMAC-SHA256 with per-key random salt (CARE-001). Salt length: 32 bytes (256 bits).

### 12.7 Merkle Trees

`kailash.trust.signing.merkle` provides Merkle tree construction and proof verification for batch audit anchoring.

### 12.8 Key Rotation

`kailash.trust.signing.rotation` provides credential rotation manager. `kailash.trust.signing.crl` provides Certificate Revocation List management.

### 12.9 Timestamping

`kailash.trust.signing.timestamping` provides trusted timestamp services for temporal anchoring.

---

## 13. Encryption at Rest

Located in `kailash.trust.plane.encryption.crypto_utils`.

### 13.1 Algorithm

AES-256-GCM with HKDF-SHA256 key derivation.

### 13.2 API

```python
derive_encryption_key(private_key_bytes: bytes) -> bytes  # 32-byte AES key
encrypt_record(plaintext: bytes, key: bytes) -> bytes     # nonce(12) || ciphertext
decrypt_record(ciphertext: bytes, key: bytes) -> bytes    # plaintext
```

**Ciphertext format**: `nonce (12 bytes) || GCM ciphertext (includes 16-byte authentication tag)`.

**Key derivation**: HKDF-SHA256 with info `b"trustplane-encryption-v1"`, no salt, producing a 32-byte key from arbitrary key material.

**Contracts**:

- Fresh 12-byte random nonce per encryption.
- Decryption failure raises `TrustDecryptionError` (not a generic exception).
- Empty plaintext is valid (encrypts to nonce + tag).
- Key must be exactly 32 bytes.

---

## 14. Store Backends

### 14.1 TrustStore (Chain Storage)

Abstract base class for EATP trust chain storage (`kailash.trust.chain_store`).

**Implementations**:

| Backend              | Location                    | Use Case                            |
| -------------------- | --------------------------- | ----------------------------------- |
| `InMemoryTrustStore` | `chain_store/memory.py`     | Testing, development                |
| `FilesystemStore`    | `chain_store/filesystem.py` | Persistent JSON files, git-friendly |
| `SqliteTrustStore`   | `chain_store/sqlite.py`     | Persistent SQLite                   |

**Transaction support**: `TransactionContext` (CARE-008) provides atomic multi-chain updates with snapshot-based rollback.

### 14.2 TrustPlaneStore (Project Records)

Protocol for trust-plane record persistence (`kailash.trust.plane.store`).

**Store Security Contract** (all implementations MUST satisfy):

1. **ATOMIC_WRITES** -- every record write is all-or-nothing.
2. **INPUT_VALIDATION** -- every ID is validated before filesystem/SQL use.
3. **BOUNDED_RESULTS** -- every list method honors a `limit` parameter.
4. **PERMISSION_ISOLATION** -- records from other projects are invisible.
5. **CONCURRENT_SAFETY** -- concurrent reads/writes must not corrupt data.
6. **NO_SILENT_FAILURES** -- errors raise named exceptions, never return None.

**Implementations**:

| Backend                     | Location                    | Use Case                       |
| --------------------------- | --------------------------- | ------------------------------ |
| `FileSystemTrustPlaneStore` | `plane/store/filesystem.py` | Git-friendly JSON files        |
| `SqliteTrustPlaneStore`     | `plane/store/sqlite.py`     | Default single-file SQLite     |
| `PostgresTrustPlaneStore`   | `plane/store/postgres.py`   | Production (requires psycopg3) |

**Record types stored**: DecisionRecord, MilestoneRecord, HoldRecord, DelegationRecipient, ReviewResolution, ProjectManifest, AuditAnchor (raw JSON), WAL (cascade revocation).

---

## 15. Agent Identity

### 15.1 HumanOrigin

The most critical EATP data structure. Immutable (`frozen=True`) record of the human who authorized an execution chain.

```python
@dataclass(frozen=True)
class HumanOrigin:
    human_id: str             # Email or user_id from auth system
    display_name: str
    auth_provider: str        # "okta", "azure_ad", etc.
    session_id: str           # For correlation and revocation
    authenticated_at: datetime
```

**Contract**: Created at authentication time. Flows through every delegation and audit record. Cannot be modified after creation (`FrozenInstanceError`).

### 15.2 ExecutionContext

Ambient context that flows through all EATP operations via `contextvars.ContextVar`.

```python
set_execution_context(context: ExecutionContext) -> None
get_current_context() -> Optional[ExecutionContext]
```

Propagation: When an agent delegates work, the `HumanOrigin` from the current execution context is bound to the delegation record, ensuring every action traces back to a human.

### 15.3 Agent Registry

`kailash.trust.registry.agent_registry` provides agent registration, lookup, and health checking. Agents are identified by unique string IDs and can have metadata, capabilities, and health status.

### 15.4 OIDC Identity Verification

`kailash.trust.plane.identity` provides SSO integration via OIDC:

- Supported providers: Okta, Azure AD, Google, generic OIDC
- Token verification: signature, expiry, issuer, audience
- Token age checking against configurable `max_age_hours`
- JWKS key caching with auto-rotation on `kid` mismatch
- Supported algorithms: RS256, RS384, RS512, ES256

---

## 16. Key Management

### 16.1 TrustPlaneKeyManager Protocol

```python
@runtime_checkable
class TrustPlaneKeyManager(Protocol):
    def sign(self, data: bytes) -> bytes
    def get_public_key(self) -> bytes
    def key_id(self) -> str              # SHA-256 fingerprint
    def algorithm(self) -> str           # e.g., "ed25519"
```

### 16.2 Backends

| Backend                   | Algorithm         | Key Storage                    |
| ------------------------- | ----------------- | ------------------------------ |
| `LocalFileKeyManager`     | Ed25519           | `.trust-plane/keys/` directory |
| `AwsKmsKeyManager`        | ECDSA P-256       | AWS KMS                        |
| `AzureKeyVaultKeyManager` | EC P-256          | Azure Key Vault                |
| `VaultKeyManager`         | Ed25519 (Transit) | HashiCorp Vault                |

**Algorithm mismatch note**: AWS KMS does not support Ed25519. The AWS backend uses ECDSA P-256, which has different signature sizes and verification semantics. This is documented in `rules/eatp.md`.

---

## 17. Trust Roles and RBAC

### 17.1 TrustRole Enum

```python
class TrustRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    OBSERVER = "observer"
    AUDITOR = "auditor"
```

### 17.2 Permission Matrix

| Role     | establish | delegate | verify | audit | read |
| -------- | --------- | -------- | ------ | ----- | ---- |
| ADMIN    | Y         | Y        | Y      | Y     | Y    |
| OPERATOR | N         | Y        | Y      | N     | Y    |
| OBSERVER | N         | N        | N      | N     | Y    |
| AUDITOR  | N         | N        | N      | Y     | Y    |

### 17.3 Backward Compatibility

`None` role = all-access. When no role is set, all operations are permitted. This preserves behavior for codebases that do not use RBAC.

### 17.4 API

```python
check_permission(role: Optional[TrustRole], operation: str) -> bool
require_permission(role: Optional[TrustRole], operation: str) -> None  # raises PermissionError
```

---

## 18. Trust Scoring

Deterministic trust scores (0-100) based on structural and behavioral factors.

### 18.1 Structural Scoring (60% of combined)

| Factor              | Weight | Scoring Logic                                      |
| ------------------- | ------ | -------------------------------------------------- |
| Chain completeness  | 30%    | Has genesis, capabilities, constraint envelope     |
| Delegation depth    | 15%    | Deeper chains = lower score (more risk)            |
| Constraint coverage | 25%    | More constraints = higher score (well-constrained) |
| Posture level       | 20%    | Stricter posture = higher score                    |
| Chain recency       | 10%    | Recent updates = higher score                      |

### 18.2 Behavioral Scoring (40% of combined)

| Factor             | Weight | Scoring Logic                           |
| ------------------ | ------ | --------------------------------------- |
| Approval rate      | 30     | approved_actions / total_actions        |
| Error rate         | 25     | Inverse of error_count / total_actions  |
| Posture stability  | 20     | Inverse of posture_transitions / window |
| Time at posture    | 15     | Normalized time at current posture      |
| Interaction volume | 10     | Log-scaled total_actions                |

### 18.3 Grade Mapping

A = 90-100, B = 80-89, C = 70-79, D = 60-69, F = 0-59.

### 18.4 Posture Score Map

Stricter postures (more human oversight) yield higher trust scores:

| Posture    | Score |
| ---------- | ----- |
| TOOL       | 100   |
| SUPERVISED | 80    |
| DELEGATING | 40    |
| AUTONOMOUS | 20    |
| PSEUDO     | 0     |

---

## 19. Reasoning Traces

### 19.1 ReasoningTrace

Structured explanation of WHY a decision was made:

```python
@dataclass
class ReasoningTrace:
    reasoning_text: str
    confidence: float              # 0.0 to 1.0
    methodology: str
    evidence_references: List[EvidenceReference]
    confidentiality: ConfidentialityLevel = ConfidentialityLevel.RESTRICTED
    constraints_considered: List[str]
    alternatives_evaluated: List[str]
    timestamp: datetime
```

### 19.2 ConfidentialityLevel

Supports ordering for access control:

`PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET`

An agent's clearance level must meet or exceed the trace's classification level to read the trace content.

### 19.3 Completeness Score

```python
reasoning_completeness_score(trace: ReasoningTrace) -> float  # 0.0 to 1.0
```

Evaluates how complete a reasoning trace is based on: presence of reasoning text, confidence, methodology, evidence references, constraints considered, and alternatives evaluated.

---

## 20. Hook System

### 20.1 Hook Types

Only 4 trust-native lifecycle events (ADR-002):

| Hook                | When                       |
| ------------------- | -------------------------- |
| `PRE_DELEGATION`    | Before delegation creation |
| `POST_DELEGATION`   | After delegation creation  |
| `PRE_VERIFICATION`  | Before verification        |
| `POST_VERIFICATION` | After verification         |

**Excluded events**: ESTABLISH hooks (one-time bootstrap), AUDIT hooks (read-only integrity), PRE_TOOL_USE/POST_TOOL_USE/SUBAGENT_SPAWN (belong in Kaizen, not trust protocol).

### 20.2 Abort Semantics

Any hook returning `allow=False` immediately aborts the remaining hook chain (fail-closed). A single deny hook prevents the action.

### 20.3 Crash Handling

If a hook raises an exception or times out, the result is `HookResult(allow=False)` -- fail-closed. A buggy hook cannot silently allow an action.

### 20.4 Reserved Metadata Keys

Hooks cannot overwrite: `agent_id`, `authority_id`, `action`, `resource`, `hook_type`, `trace_id`. These carry trust-critical provenance.

---

## 21. Exception Hierarchy

All trust exceptions inherit from `TrustError`, which carries a `.details: Dict[str, Any]` for structured error context.

```
TrustError
  +-- AuthorityNotFoundError
  +-- AuthorityInactiveError
  +-- TrustChainNotFoundError
  +-- InvalidTrustChainError
  +-- CapabilityNotFoundError
  +-- ConstraintViolationError
  +-- DelegationError
  |     +-- DelegationCycleError    (CARE-003)
  |     +-- DelegationExpiredError
  +-- InvalidSignatureError
  +-- VerificationFailedError
  +-- AgentAlreadyEstablishedError
  +-- TrustStoreError
  |     +-- TrustChainInvalidError
  |     +-- TrustStoreDatabaseError
  +-- HookError
  |     +-- HookTimeoutError
  +-- ProximityError
  +-- BehavioralScoringError
  +-- KMSConnectionError
  +-- RevocationError
  +-- PathTraversalError
  +-- PostureStoreError
```

The `TrustPlaneError` hierarchy (in `plane/exceptions.py`) covers platform-level concerns:

```
TrustPlaneError
  +-- TrustPlaneStoreError
  |     +-- RecordNotFoundError    (inherits KeyError too)
  |     +-- StoreConnectionError
  |     +-- StoreQueryError
  |     +-- StoreTransactionError
  +-- TrustDecryptionError
  +-- SchemaTooNewError
  +-- SchemaMigrationError
  +-- ConstraintViolationError
  +-- BudgetExhaustedError
  +-- IdentityError
  +-- TokenVerificationError
  +-- JWKSError
  +-- KeyManagerError
  |     +-- KeyNotFoundError
  |     +-- KeyExpiredError
  +-- SigningError
  +-- VerificationError
  +-- RBACError
  +-- ArchiveError
  +-- TLSSyslogError
  +-- LockTimeoutError
```

---

## 22. Cost Event Tracking (SPEC-08)

```python
@dataclass(frozen=True)
class CostEvent:
    event_id: str
    agent_id: str
    action: str
    cost_microdollars: int
    currency: str = "USD"
    provider: str | None = None
    timestamp: datetime
    metadata: Dict[str, Any]
```

`CostDeduplicator` prevents double-counting of cost events using a bounded LRU cache of event IDs. Duplicate events raise `DuplicateCostError`.

---

## 23. Integration with PACT Governance

The `kailash.trust.pact` subpackage bridges the trust plane with PACT's D/T/R (Decide/Trust/Ratify) accountability grammar.

### 23.1 GovernanceEngine

`kailash.trust.pact.engine` provides the main governance enforcement engine:

- Thread-safe, fail-closed evaluation
- Policy-based decision making
- Verdict computation (AUTO_APPROVED / FLAGGED / HELD / BLOCKED)
- Monotonic trust state escalation: `AUTO_APPROVED -> FLAGGED -> HELD -> BLOCKED` (never downgrade)

### 23.2 Operating Envelopes

`kailash.trust.pact.envelopes` adapts EATP constraint envelopes to PACT's operating envelope model. PACT envelopes define the boundaries within which an agent may operate without human intervention.

### 23.3 Verification Gradient

`kailash.trust.pact.gradient` classifies actions by risk level and determines the appropriate verification depth. Maps to `GradientThresholds` in the canonical envelope.

### 23.4 Knowledge Clearance

`kailash.trust.pact.clearance` manages data classification and access clearance levels, mapping to `ConfidentialityLevel` in reasoning traces.

### 23.5 D/T/R Addressing

`kailash.trust.pact.addressing` implements the PACT accountability addressing grammar, enabling structured references to decision-makers, trust authorities, and ratifiers.

---

## 24. Integration with DataFlow

### 24.1 Trust-Aware Queries

When DataFlow's trust integration is enabled, database queries pass through the trust plane for:

- **Access control**: Constraint envelope's `data_access` dimension restricts which tables/schemas an agent can query.
- **Audit logging**: Every query produces an audit anchor in the agent's trust chain.
- **Budget tracking**: Query costs are recorded against the agent's budget tracker.
- **Classification enforcement**: Data classification policies (PII, CONFIDENTIAL) are enforced at the query layer.

### 24.2 ESA (Enterprise Service Agent)

`kailash.trust.esa` provides the Enterprise Service Agent registry for DataFlow integration:

- API-based ESA discovery
- Database-backed ESA registration
- Health monitoring for registered agents

---

## 25. OrganizationalAuthority

Root of all trust chains. Represents organizations, departments, or entities that can establish trust.

```python
@dataclass
class OrganizationalAuthority:
    id: str
    name: str
    authority_type: AuthorityType     # ORGANIZATION | SYSTEM | HUMAN
    public_key: str
    signing_key_id: str
    permissions: List[AuthorityPermission]
    parent_authority_id: Optional[str] = None
    is_active: bool = True
```

**Permissions**: `CREATE_AGENTS`, `DEACTIVATE_AGENTS`, `DELEGATE_TRUST`, `GRANT_CAPABILITIES`, `REVOKE_CAPABILITIES`, `CREATE_SUBORDINATE_AUTHORITIES`.

**AuthorityRegistryProtocol**: Async protocol for authority storage with `initialize()`, `get_authority()`, and `update_authority()`.

---

## 26. Interoperability

`kailash.trust.interop` provides adapters for standard credential/token formats:

| Module       | Standard | Purpose                                |
| ------------ | -------- | -------------------------------------- |
| `did.py`     | W3C DID  | Decentralized Identifiers              |
| `w3c_vc.py`  | W3C VC   | Verifiable Credentials                 |
| `ucan.py`    | UCAN     | User Controlled Authorization Networks |
| `biscuit.py` | Biscuit  | Datalog-based authorization tokens     |
| `jwt.py`     | JWT      | JSON Web Tokens                        |
| `sd_jwt.py`  | SD-JWT   | Selective Disclosure JWT               |

---

## 27. Messaging

`kailash.trust.messaging` provides signed messaging channels between trust-plane participants:

- **Envelope**: Signed message wrapper with sender/receiver verification
- **Signer/Verifier**: Ed25519 message signing and verification
- **Replay protection**: Nonce-based replay attack prevention
- **Channel**: Authenticated communication channel with message ordering

---

## 28. Revocation

`kailash.trust.revocation` handles credential and delegation revocation:

- **Cascade revocation**: Revoking a capability or delegation cascades to all downstream dependencies.
- **Broadcaster**: Propagates revocation events to interested parties.
- **CRL (Certificate Revocation List)**: Standard revocation list management in `signing/crl.py`.

---

## 29. Security Invariants

These invariants are enforced across the entire trust plane (per `rules/trust-plane-security.md`):

1. **No bare `open()` for record files** -- use `safe_read_json()` / `safe_open()` (symlink protection).
2. **`validate_id()` on every externally-sourced record ID** -- path traversal prevention.
3. **`math.isfinite()` on all numeric constraint fields** -- NaN bypass prevention.
4. **Bounded collections (`maxlen=10000`)** -- OOM prevention.
5. **Parameterized SQL for all queries** -- injection prevention.
6. **SQLite file permissions `0o600`** -- access control.
7. **All record writes through `atomic_write()`** -- crash-consistency.
8. **`hmac.compare_digest()` for all hash/signature comparisons** -- timing attack prevention.
9. **Monotonic trust state escalation** -- no downgrades.
10. **No private key material lingering in memory** -- minimize exposure window.
11. **Frozen constraint dataclasses** -- prevent runtime envelope widening.
12. **NaN cost value rejection** -- budget bypass prevention.
13. **`RecordNotFoundError` instead of bare `KeyError`** -- error specificity.
14. **`normalize_resource_path()` for constraint patterns** -- platform independence.

---

## 30. Cross-SDK Alignment

Both Python (`kailash-py`) and Rust (`kailash-rs`) SDKs implement the EATP spec independently (D6). Convention names may differ (Python snake_case) but semantics MUST match. Key alignment points:

- `BudgetTracker` semantics (reserve/record, saturating arithmetic, microdollars)
- Trust chain data structures (genesis, capability, delegation, audit anchor)
- Verification levels (QUICK, STANDARD, FULL)
- Posture levels and transition semantics
- Constraint envelope structure and intersection semantics
- Hash chain format (SHA-256, genesis sentinel `"0" * 64`)
- Hook types and abort semantics

Cross-SDK issues are tracked with `cross-sdk` label per `rules/cross-sdk-inspection.md`.
