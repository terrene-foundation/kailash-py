# Trust Plane -- EATP Protocol, Trust Chains, Envelopes, and Delegation

Parent domain: Kailash Trust Plane. This sub-spec covers the architecture overview, the EATP (Enterprise Agent Trust Protocol) four core operations, trust chain data structures, the constraint envelope (SPEC-07), capability attestation, and delegation. See `trust-posture.md` for TrustPosture, BudgetTracker, PostureStore, and AuditStore. See `trust-crypto.md` for Ed25519 signing, AES-256-GCM encryption, store backends, RBAC, and interop.

---

## 1. Architecture Overview

### 1.1 Dual Plane Model (CARE)

The Kailash platform operates on the CARE (Collaborative Agent Reasoning Environment) dual-plane architecture:

- **Execution Plane**: Where agents perform work -- workflows, database operations, API calls, AI reasoning. Managed by Core SDK, DataFlow, Nexus, Kaizen.
- **Trust Plane**: Where trust is established, delegated, verified, and audited. Sits _between_ human authority and AI execution, providing cryptographic attestation for every agent action.

The trust plane does not perform work. It governs who may perform work, under what constraints, and produces tamper-evident records of what was done.

### 1.2 Package Layers

```
kailash.trust                          Protocol layer (core EATP types)
  kailash.trust.chain                  Trust chain data structures
  kailash.trust.envelope               Canonical ConstraintEnvelope (SPEC-07)
  kailash.trust.posture                TrustPosture state machine
  kailash.trust.constraints            BudgetTracker, constraint evaluation
  kailash.trust.signing                Ed25519 crypto, Merkle trees, CRL
  kailash.trust.reasoning              Reasoning trace extension
  kailash.trust.hooks                  Lifecycle hook system
  kailash.trust.roles                  RBAC (TrustRole)
  kailash.trust.operations             Four core EATP operations
  kailash.trust.agents                 Trust-enhanced agent wrappers
  kailash.trust.exceptions             Exception hierarchy

kailash.trust.plane                    Platform layer (project-scoped environments)
  kailash.trust.plane.project          TrustProject (primary user-facing class)
  kailash.trust.plane.models           Decision/Milestone records, legacy envelopes
  kailash.trust.plane.store            Store protocol + backends (SQLite, Postgres, FS)
  kailash.trust.plane.delegation       Multi-stakeholder delegation
  kailash.trust.plane.encryption       AES-256-GCM encryption at rest
  kailash.trust.plane.identity         OIDC identity verification
  kailash.trust.plane.key_managers     Pluggable key management (local, AWS KMS, Azure, Vault)
  kailash.trust.plane.rbac             Role-based access control
  kailash.trust.plane.shadow           Shadow mode enforcement
  kailash.trust.plane.session          Session management

kailash.trust.pact                     PACT governance integration
  kailash.trust.pact.engine            GovernanceEngine
  kailash.trust.pact.envelopes         D/T/R envelope adapter
  kailash.trust.pact.gradient          Verification gradient
  kailash.trust.pact.clearance         Knowledge clearance

kailash.trust.a2a                      Agent-to-agent protocol
kailash.trust.auth                     Authentication (JWT, SSO, RBAC, sessions)
kailash.trust.interop                  Standards interop (DID, W3C VC, UCAN, Biscuit, SD-JWT)
kailash.trust.registry                 Agent registry
kailash.trust.revocation               Credential revocation + cascade
kailash.trust.messaging                Signed messaging channels
kailash.trust.knowledge                Knowledge provenance tracking
kailash.trust.esa                      Enterprise Service Agent integration
```

### 1.3 Dependency Strategy

Core types (chain records, postures, roles, hooks, exceptions) are importable without `pynacl`. Cryptographic functions (`generate_keypair`, `sign`, `verify_signature`, `dual_sign`, `dual_verify`) use lazy loading via `__getattr__` and raise `ImportError` with installation instructions if `pynacl` is missing. The base `pip install kailash` includes `pynacl`.

---

## 2. EATP Protocol -- Four Core Operations

The EATP protocol defines exactly four operations. All operations are implemented in `kailash.trust.operations.TrustOperations`.

### 2.1 ESTABLISH

Creates initial trust for an agent by producing a `GenesisRecord` signed by an `OrganizationalAuthority`.

**API**:

```python
async def establish_trust(
    agent_id: str,
    authority_id: str,
    capabilities: List[CapabilityRequest],
    constraints: List[Constraint],
    private_key: str,
    expiry_hours: Optional[int] = None,
) -> TrustLineageChain
```

**Contracts**:

- The authority MUST exist in the `AuthorityRegistryProtocol` and be active.
- The authority MUST have `AuthorityPermission.CREATE_AGENTS`.
- The agent MUST NOT already have an established trust chain (`AgentAlreadyEstablishedError`).
- The genesis record is signed with Ed25519 using `serialize_for_signing()` for deterministic payload construction.
- Each capability becomes a `CapabilityAttestation` signed by the authority.
- A `ConstraintEnvelope` is computed from the provided constraints.
- The resulting `TrustLineageChain` is persisted to the `TrustStore`.

**Failure modes**:

- `AuthorityNotFoundError`: Authority ID does not exist.
- `AuthorityInactiveError`: Authority exists but is deactivated.
- `AgentAlreadyEstablishedError`: Agent already has a genesis record.
- `InvalidSignatureError`: Signing key is malformed.

### 2.2 DELEGATE

Transfers trust from one agent (delegator) to another (delegatee) with constraint tightening.

**API**:

```python
async def delegate_trust(
    delegator_id: str,
    delegatee_id: str,
    task_id: str,
    capabilities: List[str],
    constraints: List[str],
    private_key: str,
    expiry_hours: Optional[int] = None,
) -> DelegationRecord
```

**Contracts**:

- The delegator MUST have an established trust chain.
- The delegator MUST have the `DELEGATION` capability.
- All delegated capabilities MUST exist in the delegator's capability set.
- Constraints can only be TIGHTENED, never loosened (monotonic tightening).
- Delegation depth MUST NOT exceed `MAX_DELEGATION_DEPTH` (default: 10, per CARE-004).
- Delegation cycles are detected and rejected (`DelegationCycleError`).
- The `HumanOrigin` from the `ExecutionContext` is bound to the delegation record, ensuring traceability back to the authorizing human.
- The delegation chain path is recorded: `[human_id, agent_1, ..., delegator, delegatee]`.
- `dimension_scope` limits delegation to specific CARE constraint dimensions (default: all five). Only scoped dimensions are intersected during envelope computation.

**Failure modes**:

- `TrustChainNotFoundError`: Delegator has no trust chain.
- `CapabilityNotFoundError`: Delegator lacks requested capability.
- `DelegationError`: Generic delegation failure (constraint violation, depth exceeded).
- `DelegationCycleError`: Circular delegation detected.
- `DelegationExpiredError`: Attempting to use an expired delegation.
- `ConstraintViolationError`: Delegatee constraints would be looser than delegator.

### 2.3 VERIFY

Validates an agent's trust chain for a specific action at a specified thoroughness level.

**API**:

```python
async def verify_trust(
    agent_id: str,
    action: str,
    resource: Optional[str] = None,
    level: VerificationLevel = VerificationLevel.STANDARD,
    context: Optional[Dict[str, Any]] = None,
) -> VerificationResult
```

**Verification levels**:

| Level      | Checks                                           | Approx. Latency |
| ---------- | ------------------------------------------------ | --------------- |
| `QUICK`    | Hash integrity + expiration                      | ~1ms            |
| `STANDARD` | + Capability match, constraint evaluation        | ~5ms            |
| `FULL`     | + Ed25519 signature verification on every record | ~50ms           |

**Contracts**:

- Returns `VerificationResult` with `is_valid`, `level`, and `violations` list.
- QUICK: Verifies chain hash and checks genesis/delegation expiration.
- STANDARD: Adds capability lookup for the requested action, evaluates constraint envelope.
- FULL: Adds cryptographic signature verification on genesis, all capability attestations, and all delegation records.
- Fail-closed: any unexpected error during verification results in denial.

**Failure modes**:

- `TrustChainNotFoundError`: Agent has no trust chain.
- `VerificationFailedError`: Verification failed with specific reasons.

### 2.4 AUDIT

Records an agent action in the trust chain's audit trail with cryptographic anchoring.

**Contracts**:

- Creates an `AuditAnchor` with the action, result, and timestamp.
- The anchor is hash-linked to the chain's state at the time of recording.
- Audit is append-only -- no updates, no deletes.
- Reasoning traces can be attached to audit anchors for decision transparency.
- Each audit anchor includes `ActionResult` (SUCCESS, FAILURE, DENIED, PARTIAL).

---

## 3. Trust Chain Data Structures

All data structures are `@dataclass` with `to_dict()` and `from_dict()` for serialization. Enums serialize as `.value`, datetimes as `.isoformat()`.

### 3.1 GenesisRecord

The origin of trust for an agent. Every agent has exactly one.

```python
@dataclass
class GenesisRecord:
    id: str
    agent_id: str
    authority_id: str
    authority_type: AuthorityType        # ORGANIZATION | SYSTEM | HUMAN
    created_at: datetime
    signature: str                       # Ed25519 signature from authority
    signature_algorithm: str = "Ed25519"
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any]
```

**Contract**: `to_signing_payload()` produces a deterministic dict for signature verification. The payload includes `id`, `agent_id`, `authority_id`, `authority_type`, `created_at`, `expires_at`, and `metadata`. The `signature` field is excluded from the payload (it is the signature OF the payload).

### 3.2 CapabilityAttestation

Cryptographic proof that an agent can perform a specific action.

```python
@dataclass
class CapabilityAttestation:
    id: str
    capability: str                      # e.g., "analyze_financial_data"
    capability_type: CapabilityType      # ACCESS | ACTION | DELEGATION
    constraints: List[str]               # e.g., ["read_only", "no_pii"]
    attester_id: str
    attested_at: datetime
    signature: str
    expires_at: Optional[datetime] = None
    scope: Optional[Dict[str, Any]] = None  # e.g., {"tables": ["transactions"]}
```

### 3.3 DelegationRecord

Records trust transfer between agents with full human origin tracing.

```python
@dataclass
class DelegationRecord:
    id: str
    delegator_id: str
    delegatee_id: str
    task_id: str
    capabilities_delegated: List[str]
    constraint_subset: List[str]
    delegated_at: datetime
    signature: str
    expires_at: Optional[datetime] = None
    parent_delegation_id: Optional[str] = None

    # EATP Enhancement Fields
    human_origin: Optional[HumanOrigin] = None
    delegation_chain: List[str]          # Full path from human
    delegation_depth: int = 0            # 0 = direct from human

    # Reasoning Trace Extension
    reasoning_trace: Optional[ReasoningTrace] = None
    reasoning_trace_hash: Optional[str] = None
    reasoning_signature: Optional[str] = None

    # Dimension Scope Extension (#170)
    dimension_scope: frozenset[str] = ALL_DIMENSIONS
```

**Signing contract**: `to_signing_payload()` includes `reasoning_trace_hash` (binding the reasoning to the delegation signature) and `dimension_scope` (sorted list, preventing post-hoc scope widening). The full reasoning trace and its separate signature are excluded from the parent payload -- they have their own verification path.

**Dimension scope validation**: `__post_init__` validates that all scope values are from `VALID_DIMENSION_NAMES = {"financial", "operational", "temporal", "data_access", "communication"}`. At least one dimension is required.

### 3.4 AuditAnchor

Tamper-evident record of an agent action.

```python
@dataclass
class AuditAnchor:
    id: str
    agent_id: str
    action: str
    result: ActionResult                 # SUCCESS | FAILURE | DENIED | PARTIAL
    timestamp: datetime
    chain_hash: str                      # Hash of chain state at recording time
    resource: Optional[str] = None
    metadata: Dict[str, Any]
    reasoning_trace: Optional[ReasoningTrace] = None
    reasoning_trace_hash: Optional[str] = None
    reasoning_signature: Optional[str] = None
```

### 3.5 TrustLineageChain

Complete trust lineage for an agent, aggregating all records.

```python
@dataclass
class TrustLineageChain:
    genesis: GenesisRecord
    capabilities: List[CapabilityAttestation]
    delegations: List[DelegationRecord]
    constraint_envelope: ChainConstraintEnvelope
    audit_anchors: List[AuditAnchor]     # field name: audit_trail
    chain_hash: str
    is_active: bool = True
```

### 3.6 DelegationLimits

Configuration for delegation chain depth limits (CARE-004).

```python
@dataclass
class DelegationLimits:
    max_depth: int = 10
    max_chain_length: int = 50
    require_expiry: bool = True
    default_expiry_hours: int = 24
```

Validation: `max_depth >= 1`, `max_chain_length >= max_depth`.

### 3.7 LinkedHashChain

Merkle-style linked hash chain for tamper detection across sequential records.

---

## 4. Constraint Envelope (SPEC-07)

### 4.1 Canonical Envelope

SPEC-07 unified the three previously scattered constraint envelope implementations into a single canonical type in `kailash.trust.envelope`. All new code MUST import from this module.

**Layering note:** `ConstraintEnvelope` (this spec) is the EATP protocol-level type with rich per-dimension fields. PACT uses a separate `ConstraintEnvelopeConfig` (see `specs/pact-envelopes.md` section 4.3) as a simplified governance-facing configuration type. The PACT config maps to the protocol envelope at runtime. The two have different field sets — the protocol envelope is a superset.

```python
@dataclass(frozen=True)
class ConstraintEnvelope:
    financial: FinancialConstraint | None = None
    operational: OperationalConstraint | None = None
    temporal: TemporalConstraint | None = None
    data_access: DataAccessConstraint | None = None
    communication: CommunicationConstraint | None = None
    gradient: GradientThresholds | None = None
    posture_ceiling: AgentPosture | None = None
    hmac_signature: str | None = None
    hmac_key_ref: SecretRef | None = None
```

**Contract**: The envelope is `frozen=True`. All constraint dimension dataclasses are also `frozen=True`. Mutable constraints are BLOCKED because they allow runtime modification after governance approval, enabling an agent to widen its own operating envelope.

### 4.2 Five Constraint Dimensions

#### Financial (`FinancialConstraint`)

Cost and budget boundaries.

| Field                         | Type            | Purpose                               |
| ----------------------------- | --------------- | ------------------------------------- |
| `budget_limit`                | `float \| None` | Total budget cap                      |
| `cost_per_call`               | `float \| None` | Per-call cost limit                   |
| `currency`                    | `str`           | Currency code (default: "USD")        |
| `max_cost_per_session`        | `float \| None` | Session-level cost cap                |
| `max_cost_per_action`         | `float \| None` | Per-action cost cap                   |
| `budget_tracking`             | `bool`          | Whether budget tracking is enabled    |
| `max_spend_usd`               | `float \| None` | Total USD spend cap                   |
| `api_cost_budget_usd`         | `float \| None` | API-specific budget                   |
| `requires_approval_above_usd` | `float \| None` | Human approval threshold              |
| `reasoning_required`          | `bool`          | Whether reasoning traces are required |

All numeric fields are validated for finiteness (`math.isfinite`) and non-negativity in `__post_init__`. NaN/Inf values raise `EnvelopeValidationError`.

#### Operational (`OperationalConstraint`)

What the agent can do.

| Field                    | Type              | Purpose                               |
| ------------------------ | ----------------- | ------------------------------------- |
| `max_retries`            | `int \| None`     | Retry limit                           |
| `timeout_seconds`        | `float \| None`   | Per-operation timeout                 |
| `max_concurrent`         | `int \| None`     | Concurrency limit                     |
| `allowed_actions`        | `tuple[str, ...]` | Allowlist of actions                  |
| `blocked_actions`        | `tuple[str, ...]` | Blocklist of actions                  |
| `max_actions_per_day`    | `int \| None`     | Daily action limit                    |
| `max_actions_per_hour`   | `int \| None`     | Hourly action limit                   |
| `rate_limit_window_type` | `str`             | "fixed" or "rolling"                  |
| `reasoning_required`     | `bool`            | Whether reasoning traces are required |

Lists are coerced to tuples in `__post_init__` for frozen immutability.

#### Temporal (`TemporalConstraint`)

Time boundaries.

| Field                    | Type                      | Purpose                                   |
| ------------------------ | ------------------------- | ----------------------------------------- |
| `valid_from`             | `datetime \| None`        | Earliest valid time                       |
| `valid_until`            | `datetime \| None`        | Latest valid time                         |
| `max_duration_seconds`   | `float \| None`           | Max operation duration                    |
| `max_session_hours`      | `float \| None`           | Max session length                        |
| `allowed_hours`          | `tuple[int, int] \| None` | Active hours (0-23, no wrap-around)       |
| `cooldown_minutes`       | `int`                     | Cooldown between operations               |
| `active_hours_start/end` | `str \| None`             | Alternative active hours format           |
| `timezone`               | `str`                     | Timezone for time checks (default: "UTC") |
| `blackout_periods`       | `tuple[str, ...]`         | Blocked time periods                      |

#### Data Access (`DataAccessConstraint`)

What data the agent can see and modify.

| Field                    | Type              | Purpose                         |
| ------------------------ | ----------------- | ------------------------------- |
| `read_paths`             | `tuple[str, ...]` | Allowed read resource paths     |
| `write_paths`            | `tuple[str, ...]` | Allowed write resource paths    |
| `blocked_paths`          | `tuple[str, ...]` | Blocked resource paths          |
| `blocked_patterns`       | `tuple[str, ...]` | Blocked path patterns           |
| `pii_allowed`            | `bool`            | Whether PII access is permitted |
| `classification_ceiling` | `str \| None`     | Max data classification level   |
| `allowed_schemas`        | `tuple[str, ...]` | Allowed database schemas        |
| `blocked_schemas`        | `tuple[str, ...]` | Blocked database schemas        |

All paths are normalized via `normalize_resource_path()` (platform-independent, rejects `os.path.normpath` which produces backslashes on Windows).

#### Communication (`CommunicationConstraint`)

External communication controls.

| Field                    | Type              | Purpose                          |
| ------------------------ | ----------------- | -------------------------------- |
| `allowed_channels`       | `tuple[str, ...]` | Permitted communication channels |
| `blocked_channels`       | `tuple[str, ...]` | Blocked channels                 |
| `max_message_length`     | `int \| None`     | Message size limit               |
| `require_human_approval` | `bool`            | Whether human approval is needed |
| `allowed_recipients`     | `tuple[str, ...]` | Permitted recipients             |
| `blocked_recipients`     | `tuple[str, ...]` | Blocked recipients               |
| `allowed_domains`        | `tuple[str, ...]` | Allowed external domains         |
| `blocked_domains`        | `tuple[str, ...]` | Blocked external domains         |

### 4.3 Monotonic Tightening (`intersect()`)

The `intersect()` method on `ConstraintEnvelope` produces a new envelope that is the intersection (strictest combination) of two envelopes. Used during delegation to ensure constraints can only become tighter.

- Numeric limits: `min(a, b)` (stricter)
- Allowlists: intersection (fewer permissions)
- Blocklists: union (more restrictions)
- Booleans (`require_human_approval`): logical OR (if either requires it, result requires it)

### 4.4 Canonical JSON and Signing

Envelopes produce deterministic canonical JSON via `to_canonical_json()` for cross-SDK compatibility. HMAC-SHA256 signing is supported via `SecretRef` for key material reference. Signing uses `hmac.compare_digest()` for constant-time comparison.

### 4.5 Gradient Thresholds

```python
@dataclass(frozen=True)
class GradientThresholds:
    auto_approve_below: float | None = None
    flag_above: float | None = None
    hold_above: float | None = None
    block_above: float | None = None
```

Used by the verification gradient (PACT integration) to classify actions into AUTO_APPROVED / FLAGGED / HELD / BLOCKED based on risk score.

### 4.6 Posture Ceiling

`AgentPosture` enum (mapping to `TrustPosture`) sets the maximum autonomy level the envelope permits. An agent cannot operate at a posture higher than its envelope ceiling, regardless of what the posture state machine would otherwise allow.

---

## 10. Capability Attestation

Capabilities are typed as `CapabilityType`:

| Type         | Meaning                                             |
| ------------ | --------------------------------------------------- |
| `ACCESS`     | Can access resources (read data, query APIs)        |
| `ACTION`     | Can perform actions (write data, trigger workflows) |
| `DELEGATION` | Can delegate trust to other agents                  |

Each attestation carries:

- A scope restriction (optional): `{"tables": ["transactions"], "schemas": ["finance"]}`
- A constraint list: `["read_only", "no_pii", "us_region_only"]`
- An expiration (optional)
- A cryptographic signature from the attester

Capabilities are NEVER implicitly granted. Every capability must be explicitly attested and signed.

---

## 11. Delegation

### 11.1 Protocol-Level Delegation (chain.py)

`DelegationRecord` captures the trust transfer between agents. Key properties:

- **Monotonic tightening**: A delegatee's constraints are always a subset of (or equal to) the delegator's constraints.
- **Human origin tracing**: Every delegation traces back to a human via `HumanOrigin`.
- **Depth limits**: `MAX_DELEGATION_DEPTH = 10` (CARE-004).
- **Cycle detection**: Delegation chains are checked for cycles before creation.
- **Dimension scoping**: A delegation can be scoped to specific constraint dimensions.

### 11.2 Platform-Level Delegation (plane/delegation.py)

`DelegationRecipient` represents a delegate authorized to review actions in specific dimensions:

```python
@dataclass
class DelegationRecipient:
    delegate_id: str
    name: str
    dimensions: list[str]         # e.g., ["operational", "data_access"]
    delegated_by: str             # ID of delegator
    status: DelegateStatus        # ACTIVE | REVOKED | EXPIRED
    depth: int = 0                # 0 = directly delegated by owner
```

**Architecture** (multi-stakeholder):

```
Project Owner (Genesis Record)
  +-- Delegate: Senior Dev (operational, data_access)
  +-- Delegate: Security Lead (communication)
  +-- Delegate: Team Lead (all dimensions, backup)
```

**Cascade revocation**: Revoking a delegate revokes all sub-delegates. Uses a WAL (Write-Ahead Log) for crash recovery during cascade operations. WAL hashes are verified with `hmac.compare_digest()`.

**Valid dimensions**: `{"operational", "data_access", "financial", "temporal", "communication"}`.

---
