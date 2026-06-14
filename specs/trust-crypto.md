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

## 30. Shamir Secret-Sharing (SLIP-0039)

Trust Vault key backup uses Shamir secret-sharing per SLIP-0039 (SatoshiLabs reference standard) via `kailash.trust.vault.shamir`. The wrapper composes the audited reference implementation `shamir-mnemonic` (PyPI) into an ergonomic ritual surface for splitting and reconstructing high-value Trust Vault key material.

### Public Surface

`kailash.trust.vault` re-exports the wrapper API:

- **`ShamirRitual(threshold: int, total_shards: int)`** -- frozen dataclass capturing m-of-n parameters. Validation enforced in `__post_init__`:
  - `1 <= threshold <= total_shards`
  - `total_shards <= 16` (SLIP-0039 4-bit member-index field)
  - `threshold >= 2` when `total_shards > 1` (trivial 1-of-n splits rejected pending mint ISS-37 governance review -- a 1-of-n ritual provides distribution but zero threshold protection, so the wrapper refuses by default)
- **`generate(secret: bytes, ritual: ShamirRitual, *, passphrase: bytes = b"") -> List[List[str]]`** -- splits the secret into `ritual.total_shards` SLIP-0039 mnemonic shards. Single-group `m`-of-`n` configuration (`group_threshold=1`); multi-group rituals reserved for mint ISS-37.
- **`reconstruct(shards: List[List[str]], *, passphrase: bytes = b"") -> bytes`** -- recombines threshold-many shards into the original secret.
- **`serialize_shard(shard: List[str]) -> str`** -- canonical paper-print form (single space-joined dictionary words). Interop surface across SDKs and the form holders write to paper, engrave on metal, or print on cards.
- **`deserialize_shard(shard: str) -> List[str]`** -- reverse operation, whitespace-tolerant for paper transcription.
- **`rotate_holders(old_shards: List[List[str]], new_ritual: ShamirRitual, *, passphrase: bytes = b"") -> List[List[str]]`** -- recombine then re-shard. Used when the holder set changes (a holder leaves, a new holder joins, or the ritual is updated). The intermediate secret is `del`-eted before the function returns; rotation SHOULD run on an air-gapped host per Trust Vault operational guidance.
- **`back_up_vault_key(key_handle, ritual, clearance, holders, *, resolver, dispatcher, signer, signer_identity, alg_id, ...) -> BackupReceipt`** (`kailash.trust.vault.backup`) -- the handle-based EATP-12 Trust-Vault binding (issue #1312). The KEK is resolved INTERNALLY from `key_handle` via the injected `resolver` (the trusted-module boundary, N12-IN-01); raw KEK bytes do NOT cross the public API and the resolved secret is consumed-and-`del`-eted in a `finally` (N12-IN-05). It gates clearance (`vault:backup`), the ritual floor (`2<=k<=n<=9`), and holder-registry membership; shards under the vetted ritual; registers the KEK-identity commitment + KCV; dispatches a signed `vault_key_backup` audit anchor to the `recovery` tier (no shard release until the dispatch receipt is in hand, N12-AU-02b); and returns a `BackupReceipt` (commitment, KCV, k, n, holder ids -- NEVER the secret). The full EATP-12 binding contract is § "Trust-Vault Binding (EATP-12)" below.

### Optional Extra

Install via:

```
pip install kailash[shamir]
```

The audited reference library (`shamir-mnemonic>=0.3`) is shipped as an optional extra so the base `pip install kailash` does not pull in cryptographic mnemonic code most users do not need.

### Lazy-Import Contract

Module import of `kailash.trust.vault.shamir` MUST succeed even without the optional extra installed -- so `__all__` membership, `from kailash.trust.vault import *`, Sphinx autodoc, and static analysers all resolve. The audited library is imported lazily inside each public function via `_require_shamir_mnemonic()`. When the extra is absent, the FIRST call site raises:

```
RuntimeError: SLIP-0039 Shamir secret-sharing requires the 'shamir'
optional extra. Install via: pip install kailash[shamir]
```

This is the "loud failure at call site" pattern from `rules/dependencies.md`. The silent `X = None` fallback anti-pattern is BLOCKED.

### Threshold Convention

The ritual is captured as `(threshold, total_shards)` -- m-of-n. Reconstruction requires AT LEAST `threshold` shards from the originally-generated set; fewer than `threshold` MUST refuse with the underlying SLIP-0039 library's typed exception (propagated unchanged through the wrapper).

### Paper-Print Format

`serialize_shard` produces a single-line whitespace-separated string of SLIP-0039 dictionary words. The format is the cross-SDK interop surface: a shard serialised by Python `kailash-py` round-trips through Rust `kailash-rs` (matching scaffold expected). `deserialize_shard` collapses any run of ASCII whitespace, so transcription artefacts (extra spaces, line breaks) survive the round-trip.

### Rotation Protocol

`rotate_holders(old_shards, new_ritual)`:

1. Reconstruct the secret from `old_shards` via `reconstruct()`.
2. Re-shard the secret via `generate(secret, new_ritual)`.
3. `del` the intermediate secret reference before return.

The intermediate secret is held in memory for the duration of the re-shard call. Hardened deployments SHOULD perform rotation in a process that exits immediately afterward to minimize the residence window. To rotate the passphrase as well as the holder set, call `reconstruct()` and `generate()` explicitly.

### Trust-Vault Binding (EATP-12)

The EATP-12 v1.0 Trust-Vault key-binding (issue #1312) composes the SLIP-0039 wrapper above with a commitment/KCV control, a clearance/authz gate, a named-tier audit dispatcher, a per-(vault, generation) commitment registry, a stale-generation guard, holder rotation, and Complete-level governance gates. The two operator-facing operations live in `kailash.trust.vault.backup`:

- **`back_up_vault_key(...) -> BackupReceipt`** -- splits a resolver-resolved KEK under a vetted ritual and dispatches a signed `vault_key_backup` anchor (see the Public-Surface bullet above for the gate order).
- **`restore_vault_key(shards, target_handle, clearance, *, resolver, dispatcher, signer, signer_identity, alg_id, ...) -> RestoreReceipt`** -- reconstructs a KEK from presented shards and re-establishes it opaquely. Runs the canonical FT-02 first-failing gate order (§4.6): clearance (tenant->domain->token fail-closed + the N12-CL-04 cooling-off suspension) -> handle-type -> foreign-shard (presented shard ciphertext-hashes checked against the distribution anchor BEFORE reconstruction) -> reconstruct -> commitment-auth (3-way discrimination: `commitment-alg-mismatch` / `retired-commitment-alg` / `kek-commitment-mismatch`, plus `key-identity-mismatch`) -> stale-generation (ordinal gen derived from the audited rotation chain). The reconstructed secret is consumed-and-`del`-eted in a `finally` (N12-IN-05); the `RestoreReceipt` is an opaque handle ref, never the secret.

Supporting surface (all under `kailash.trust.vault`):

- **Commitment + KCV** (`commitment.py`): `kek_identity_commitment` binds `(vault_id, kek_generation, secret, passphrase_provenance, resolved key-id)` under the EATP-08 §3.3 registry alg token; `key_check_value` is the key-free domain-separated 8-byte KCV. The canonical pre-image uses RFC-8785/JCS (`canonical_json_dumps`, `ensure_ascii=False`).
- **Audit anchors** (`anchors.py`): the closed `vault_*` subtype set (`vault_key_backup`, `vault_key_restore`, `vault_key_restore_denied`, `vault_kek_rotation`, `vault_kek_recommit`, `vault_kek_retire`, `vault_holder_rotation`, `vault_key_restore_forced_stale`, `vault_denial_summary`), each a canonical `event_payload` whose pre-image is `content_signing_bytes` (`event_type="external_side_effect"`); `alg_id` rides `event_payload.alg_id`. Denials carry a distinct minimal schema and are dispatched to the `safety` tier; secrets/shard contents are never recorded.
- **Commitment registry + recommit/retire** (`registry.py` / `registry_ops.py`): additive per-(vault, generation) commitment registration; `vault_kek_recommit` adds a new-alg commitment without deleting the prior (EATP-08 hash-sunset migration); `vault_kek_retire` marks an alg entry non-verifiable (`retired-commitment-alg` on restore under it).
- **Stale-generation guard** (`stale_guard.py`): default stale-refusal; the `force_stale` override (distinct `vault:restore-stale` capability) overrides ONLY the ordinal gate and loudly dual-emits `vault_key_restore_forced_stale` to recovery + safety; a compromised-generation denylist (`revoked-generation`) is NOT overridable by `force_stale`. Every materializing restore triggers the N12-RT-05 D6 downgrade (principal -> SUPERVISED + 7-day cooling-off).
- **Rotation** (`rotation.py`): `rotate_vault_holders` (amicable, generation unchanged) and `revoke_holder_for_cause` (for-cause generation-advance + new distribution), composing `shamir.rotate_holders` + the k-floor revocation check.
- **Complete-level gates** (`complete.py`, gated behind `ConformanceLevel.COMPLETE`): `verify_governance_approval` (N12-CL-03 -- a distinct `vault:approve` holder, no self-approval on principal or `delegate_id`, signed approval bound into the restore anchor's `event_payload["approval"]`), `verify_ceremony_witness` (N12-CL-05 -- a distinct `vault:witness` holder bound into the backup anchor's `event_payload["witness"]`), and per-holder wrapping (N12-SH-02). At `ConformanceLevel.CONFORMANT` these are not invoked and the audit pre-image is byte-unchanged.

Conformance vectors V1-V8 (spec §7) are exercised as Tier-2 tests; the canonical §12 byte-vectors live at `tests/test-vectors/eatp12-vault-canonical.json`. The closed typed-error enum is `N12FT01Code` (`errors.py`).

### Security Caveat

The `shamir-mnemonic` reference implementation is **not constant-time** and is documented by its authors as suitable for correctness verification rather than handling of high-value secrets in adversarial settings. Trust Vault deployments that need side-channel resistance MUST evaluate hardened alternatives before production use. The wrapper exists today to (1) freeze the SLIP-0039 API surface so downstream callers can compile against it and (2) enable end-to-end ritual rehearsal.

### Memory Hygiene

Per `rules/trust-plane-security.md` MUST NOT Rule 3, callers MUST `del` returned secret bytes immediately after use. The wrapper itself does not log shard contents or passphrases at any level (`rules/observability.md` MUST Rule 4). The wrapper does not zeroize the bytes object (Python `bytes` is immutable; in-place clearing is not portable). Hardened deployments needing cryptographic zeroization MUST use a hardened secret-handling library above the wrapper.

### Cross-SDK

A matching scaffold is expected on the Rust SDK (`kailash-rs`) using a parallel audited Rust SLIP-0039 implementation. The serialised paper-print form is the cross-SDK interop surface. Per `rules/cross-sdk-inspection.md` a follow-up issue MUST be filed on `esperie/kailash-rs` if the matching scaffold is not yet present.

### Tests

- Tier 1 regression: `tests/regression/test_issue_606_shamir_wrapper.py` -- ritual validation, frozen invariant, lazy-import absence-path contract, the handle-based `back_up_vault_key` conformant surface.
- Tier 2 integration: `tests/integration/trust/test_shamir_round_trip.py` -- real `shamir-mnemonic` round-trip across multiple shard subsets, threshold-minus-1 reconstruct refusal, paper-print round-trip, holder rotation 3-of-5 -> 2-of-3 + 3-of-5 -> 5-of-7 secret preservation. Per `rules/orphan-detection.md` Rule 2a (Crypto-Pair Round-Trip Through Facade), all crypto operations route through the public `kailash.trust.vault.shamir.<name>` surface, NOT the underlying library directly.
- EATP-12 binding (Tier-1 byte-pin + Tier-2 wiring): `tests/regression/test_eatp12_vault_canonical_vectors.py` + `test_eatp12_vault_anchor_vectors.py` (§12 byte-pins), `test_eatp12_vault_3way_discrimination.py`, and the `tests/integration/test_eatp12_vault_*_wiring.py` suites (dispatch, clearance, registry, stale-guard, rotation, recommit/retire, holder-registry, backup/restore, complete, x1-embed) exercising the full gate order, audit chain, and Complete-level V8 governance binding against the real substrate.

### §30 Change log

- 2026-06-15: replaced the "Awaiting Mint ISS-37" `back_up_vault_key` stub description with the shipped EATP-12 Trust-Vault binding contract (issue #1312, Waves 1-6); `back_up_vault_key` is now the handle-based conformant surface returning `BackupReceipt` and `restore_vault_key` is its inverse, per `rules/spec-accuracy.md` Rule 5 (code-first, spec describes what landed).

---

## 31. Cross-SDK Alignment

Both Python (`kailash-py`) and Rust (`kailash-rs`) SDKs implement the EATP spec independently (D6). Convention names may differ (Python snake_case) but semantics MUST match. Key alignment points:

- `BudgetTracker` semantics (reserve/record, saturating arithmetic, microdollars)
- Trust chain data structures (genesis, capability, delegation, audit anchor)
- Verification levels (QUICK, STANDARD, FULL)
- Posture levels and transition semantics
- Constraint envelope structure and intersection semantics
- Hash chain format (SHA-256, genesis sentinel `"0" * 64`)
- Hook types and abort semantics

Cross-SDK issues are tracked with `cross-sdk` label per `rules/cross-sdk-inspection.md`.

## 32. Algorithm Identifier (EATP-08 v1.1)

The signed-record surface threads an `AlgorithmIdentifier` registry token
through every producer/verifier. This implements **EATP-08
"Algorithm-Identifier Versioning" v1.1** (published 2026-04-26,
`foundation/docs/02-standards/eatp/08-algorithm-identifier.md`), which
supersedes the closed pre-publication #604 scaffold. The threading
(producer → record → verifier) is in place across every Layer-1
signed-record pair; see § 32.4.

### 32.1 Registry constants and the wire shape

Canonical home: `kailash.trust.signing.algorithm_id`; the package
`kailash.trust.signing` re-exports the full surface as the canonical import
path (`src/kailash/trust/signing/__init__.py:27-44`).

- `ALGORITHM_DEFAULT: str = "eatp-v1"` — the sole **Active** identifier
  (Ed25519 + SHA-256), per EATP-08 §3.3 (`algorithm_id.py:61`). Replaces
  the pre-publication scaffold default `"ed25519+sha256"`.
- `DEPRECATED_PRE_REGISTRY_LITERAL: str = "ed25519+sha256"` — accepted
  ONLY on the bounded D2d legacy path (§ 32.3), never a conformant
  emission (`algorithm_id.py:67`).
- `ADOPTION_DATE: str = "2026-04-26"` + `ADOPTION_DATE_PARSED` — the
  EATP-08 §7.1 pinned adoption date, consumed by the D2d temporal gate
  (`algorithm_id.py:71-76`).

Wire encoding (EATP-08 §3.1/§3.2, binding D3): the identifier serialises as
a **top-level `alg_id` string** member. Under JCS (RFC 8785) key ordering,
`alg_id` sorts first, so a verifier reads the algorithm before parsing the
payload. The pre-registry nested object `{"algorithm": "..."}` and the
deprecated literal are NON-conformant emissions. `AlgorithmIdentifier.to_dict()`
returns exactly `{"alg_id": "<token>"}` (`algorithm_id.py:406-415`).

### 32.2 Registry and dispatch (EATP-08 §3.3 / §5.1)

`ALGORITHM_REGISTRY` (`algorithm_id.py:108-140`) carries `eatp-v1` (Active)
plus reserved rows (`eatp-v1.1`, `eatp-v2`, `eatp-v2.ml-dsa`,
`eatp-v2.slh-dsa`). `AlgorithmStatus` enumerates `Active` / `Reserved` /
`Reserved-Unregistered` (`algorithm_id.py:79-85`).

- `AlgorithmIdentifier(...)` (`algorithm_id.py:350`, validation `:379`) accepts any **registered**
  token as a value; an unregistered token raises `UnsupportedAlgorithmError`
  with code `unsupported-algorithm`.
- `resolve_dispatch(alg_id)` (`algorithm_id.py:273`) is the §5.1 step-2
  dispatch gate: only an **Active** row dispatches. Unregistered, Reserved,
  and Reserved-Unregistered all raise `unsupported-algorithm` and MUST NOT
  fall through to `eatp-v1` semantics.
- `is_registered` / `is_active` (`algorithm_id.py:260-271`) are the value vs
  dispatchability predicates.

`UnsupportedAlgorithmError` (`algorithm_id.py:142`) carries the normative
EATP-08 §5.3 error code: `unsupported-algorithm`, `alg-id-shape-mismatch`,
`missing-alg-id-post-adoption`, or `implicit-v1-witness-failure`.

### 32.3 Backward-compat regime (EATP-08 §4 — D1/D2a/D2b/D2c/D2d)

The post-adoption path is strict (D2b): `AlgorithmIdentifier.from_dict()`
and the consumer helper `decode_wire_alg_id()` (`algorithm_id.py:417`, `:558`)
do NOT silently default-fill. A missing/empty `alg_id` post-adoption raises
`missing-alg-id-post-adoption`; a non-string or nested form raises
`alg-id-shape-mismatch`. A **bare top-level-string** `alg_id` equal to the
deprecated literal `ed25519+sha256` is an unregistered token and raises
`unsupported-algorithm` (EATP-08 §3.3 / §5.1 step 2, v1.1.1 / mint#26): it is
NOT a D2d pre-registry form, and a D2d witness MUST NOT rescue it. A present
`alg_id` key is authoritative, so `{"alg_id":"ed25519+sha256","algorithm":...}`
also raises `unsupported-algorithm` rather than falling through to the
`algorithm`-key D2d match (`from_dict`, `algorithm_id.py:474`).

The legacy path (D2d, §4.5) is **dated and witnessed**. The pre-1.1 scaffold
accepted a bare `legacy_path: bool` — a perpetual un-sunsetted downgrade
channel — and defined `ADOPTION_DATE` but never consulted it. D2d replaces
that with `D2dWitness` (`algorithm_id.py:169`): a pre-registry explicit form
(`is_pre_registry_form`, `algorithm_id.py:309`) is accepted as `eatp-v1`
ONLY when a witness is supplied AND its witnessed-date AND chain-head date
are both strictly before `ADOPTION_DATE`. The gate is
`assert_d2d_witness_pre_adoption()` (`algorithm_id.py:223`): a missing
witness OR a witness dated on/after adoption raises
`implicit-v1-witness-failure` — the form is rejected, never silently
downgraded. Accepted legacy acceptance is logged for migration tracking.

### 32.4 Threaded surface

Every Layer-1 signed-record producer/verifier carries the top-level `alg_id`
member and decodes it through `decode_wire_alg_id` (witness-aware):

- `src/kailash/trust/pact/envelopes.py` — `SignedEnvelope` (`alg_id` field,
  `envelopes.py:1227`) sign/verify pair.
- `src/kailash/trust/envelope.py` — `sign_envelope` / `verify_envelope`
  (optional `alg_id` kwarg, `envelope.py:1388`).
- `src/kailash/trust/signing/timestamping.py` — `RFC3161TimestampManager`
  (`create_anchor` / `verify_anchor` + `TimestampToken`).
- `src/kailash/trust/signing/crl.py` — `CRLMetadata.sign` / `verify_signature`.
- `src/kailash/trust/messaging/{signer,verifier}.py` — `MessageEnvelope`.

Layer-2 stores (audit_store, chain_store, key_manager) inherit threading
through their underlying Layer-1 primitives.

### 32.5 Cross-SDK alignment

Cross-SDK sibling: `esperie-enterprise/kailash-rs` (companion conformance
issue). EATP-08 is wire-format-breaking; the version bump and the
transition provision for already-emitted `ed25519+sha256` records (an open
EATP-08 §4 erratum question — flagged to mint, not resolved unilaterally)
are coordinated with the Rust SDK before release. Cross-SDK conformance
vectors carrying `alg_id` byte-align with the Rust sibling per
`rules/cross-sdk-inspection.md` Rule 4.

Origin: GitHub issue terrene-foundation/kailash-py#1304 (mint#6 / EATP-08
v1.1), superseding the closed #604 scaffold.
