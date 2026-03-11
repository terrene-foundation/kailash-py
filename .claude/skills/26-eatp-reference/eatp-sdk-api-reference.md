# EATP SDK — API Reference (v0.1.0)

Complete API surface for the standalone EATP Python SDK.

**Package**: `packages/eatp/src/eatp/`
**Install**: `pip install eatp`
**License**: Apache 2.0 (Terrene Foundation)
**Python**: >=3.11

## Top-Level Exports (`from eatp import ...`)

### Operations

| Export                      | Type      | Module            |
| --------------------------- | --------- | ----------------- |
| `TrustOperations`           | Class     | `eatp.operations` |
| `TrustKeyManager`           | Class     | `eatp.operations` |
| `CapabilityRequest`         | Dataclass | `eatp.operations` |
| `AuthorityRegistryProtocol` | Protocol  | `eatp.authority`  |

### Chain Types (5 EATP Elements)

| Export                  | Type      | Module       |
| ----------------------- | --------- | ------------ |
| `TrustLineageChain`     | Dataclass | `eatp.chain` |
| `GenesisRecord`         | Dataclass | `eatp.chain` |
| `DelegationRecord`      | Dataclass | `eatp.chain` |
| `CapabilityAttestation` | Dataclass | `eatp.chain` |
| `ConstraintEnvelope`    | Dataclass | `eatp.chain` |
| `AuditAnchor`           | Dataclass | `eatp.chain` |
| `VerificationResult`    | Dataclass | `eatp.chain` |
| `VerificationLevel`     | Enum      | `eatp.chain` |
| `AuthorityType`         | Enum      | `eatp.chain` |
| `CapabilityType`        | Enum      | `eatp.chain` |
| `ConstraintType`        | Enum      | `eatp.chain` |

### Reasoning Traces

| Export                 | Type      | Module           |
| ---------------------- | --------- | ---------------- |
| `ReasoningTrace`       | Dataclass | `eatp.reasoning` |
| `ConfidentialityLevel` | Enum      | `eatp.reasoning` |

### Stores

| Export               | Type  | Module              |
| -------------------- | ----- | ------------------- |
| `TrustStore`         | ABC   | `eatp.store`        |
| `InMemoryTrustStore` | Class | `eatp.store.memory` |

### Crypto

| Export             | Type     | Module        |
| ------------------ | -------- | ------------- |
| `generate_keypair` | Function | `eatp.crypto` |
| `sign`             | Function | `eatp.crypto` |
| `verify_signature` | Function | `eatp.crypto` |

### Authority

| Export                    | Type      | Module           |
| ------------------------- | --------- | ---------------- |
| `OrganizationalAuthority` | Dataclass | `eatp.authority` |
| `AuthorityPermission`     | Enum      | `eatp.authority` |

### Postures

| Export                | Type  | Module          |
| --------------------- | ----- | --------------- |
| `TrustPosture`        | Enum  | `eatp.postures` |
| `PostureStateMachine` | Class | `eatp.postures` |

### Exceptions

| Export                    | Type      | Module            |
| ------------------------- | --------- | ----------------- |
| `TrustError`              | Exception | `eatp.exceptions` |
| `TrustChainNotFoundError` | Exception | `eatp.exceptions` |

## Module Reference

### `eatp.operations` — Core Operations

```python
class TrustOperations:
    def __init__(self, authority_registry, key_manager, trust_store): ...

    async def establish(
        self,
        agent_id: str,
        authority_id: str,
        capabilities: List[CapabilityRequest],
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrustLineageChain: ...

    async def delegate(
        self,
        delegator_id: str,
        delegatee_id: str,
        task_id: str,
        capabilities: List[str],
        additional_constraints: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ExecutionContext] = None,
        reasoning_trace: Optional[ReasoningTrace] = None,  # Reasoning extension
    ) -> DelegationRecord: ...

    async def verify(
        self,
        agent_id: str,
        action: str,
        level: VerificationLevel = VerificationLevel.STANDARD,
        resource: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult: ...

    async def audit(
        self,
        agent_id: str,
        action: str,
        resource: Optional[str] = None,
        result: ActionResult = ActionResult.SUCCESS,
        context_data: Optional[Dict[str, Any]] = None,
        reasoning_trace: Optional[ReasoningTrace] = None,  # Reasoning extension
    ) -> AuditAnchor: ...
```

### `eatp.authority` — Authority Types

```python
class AuthorityPermission(Enum):
    CREATE_AGENTS = "create_agents"
    DEACTIVATE_AGENTS = "deactivate_agents"
    DELEGATE_TRUST = "delegate_trust"
    GRANT_CAPABILITIES = "grant_capabilities"
    REVOKE_CAPABILITIES = "revoke_capabilities"
    CREATE_SUBORDINATE_AUTHORITIES = "create_subordinate_authorities"

@dataclass
class OrganizationalAuthority:
    id: str
    name: str
    authority_type: AuthorityType
    public_key: str
    signing_key_id: str
    permissions: List[AuthorityPermission] = []
    parent_authority_id: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = {}

    def has_permission(self, permission: AuthorityPermission) -> bool: ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrganizationalAuthority": ...

@runtime_checkable
class AuthorityRegistryProtocol(Protocol):
    async def initialize(self) -> None: ...
    async def get_authority(self, authority_id: str, include_inactive: bool = False) -> OrganizationalAuthority: ...
    async def update_authority(self, authority: OrganizationalAuthority) -> None: ...

# Backwards-compatible alias
OrganizationalAuthorityRegistry = AuthorityRegistryProtocol
```

### `eatp.chain` — Data Structures

```python
class AuthorityType(Enum):
    ORGANIZATION = "organization"
    SYSTEM = "system"
    HUMAN = "human"

class CapabilityType(Enum):
    ACCESS = "access"
    ACTION = "action"
    DELEGATION = "delegation"

class ActionResult(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    PARTIAL = "partial"

class ConstraintType(Enum):
    RESOURCE_LIMIT = "resource_limit"
    TEMPORAL = "temporal"
    DATA_SCOPE = "data_scope"
    ACTION_RESTRICTION = "action_restriction"
    AUDIT_REQUIREMENT = "audit_requirement"
    REASONING_REQUIRED = "reasoning_required"  # Reasoning trace extension

class VerificationLevel(Enum):
    QUICK = "quick"       # Hash + expiration (~1ms)
    STANDARD = "standard" # + Capability match, constraints, reasoning presence (~5ms)
    FULL = "full"         # + Signature verification, reasoning hash/sig verification (~50ms)

@dataclass
class VerificationResult:
    valid: bool
    level: VerificationLevel
    reason: Optional[str] = None
    capability_used: Optional[str] = None
    effective_constraints: List[str] = []
    violations: List[Dict[str, str]] = []
    # Reasoning trace extension
    reasoning_present: Optional[bool] = None   # True/False/None (STANDARD+)
    reasoning_verified: Optional[bool] = None  # True/False/None (FULL only)
```

### `eatp.crypto` — Cryptographic Primitives

```python
def generate_keypair() -> Tuple[str, str]:
    """Returns (private_key_base64, public_key_base64). PRIVATE FIRST."""

def sign(payload: Union[str, bytes], private_key: str) -> str:
    """Sign payload with Ed25519 key. Returns base64-encoded signature."""

def verify_signature(payload: Union[str, bytes], signature: str, public_key: str) -> bool:
    """Verify Ed25519 signature. Signature is base64-encoded."""

def hash_chain(data: str) -> str:
    """SHA-256 hash for chain integrity."""

def serialize_for_signing(obj: Any) -> str:
    """Deterministic JSON serialization for signing."""

# Reasoning trace crypto functions
def hash_reasoning_trace(trace: ReasoningTrace) -> str:
    """SHA-256 hash of reasoning trace signing payload. Returns 64-char hex string."""

def sign_reasoning_trace(trace: ReasoningTrace, private_key: str) -> str:
    """Sign reasoning trace with Ed25519 key. Returns base64-encoded signature."""

def verify_reasoning_signature(trace: ReasoningTrace, signature: str, public_key: str) -> bool:
    """Verify reasoning trace Ed25519 signature."""
```

### `eatp.store` — Storage

```python
class TrustStore(ABC):
    async def initialize(self) -> None: ...
    async def store_chain(self, chain: TrustLineageChain, expires_at: Optional[datetime] = None) -> str: ...
    async def get_chain(self, agent_id: str) -> TrustLineageChain: ...
    async def update_chain(self, agent_id: str, chain: TrustLineageChain) -> None: ...
    async def delete_chain(self, agent_id: str) -> None: ...
    async def list_chains(self, ...) -> List[TrustLineageChain]: ...
    def transaction(self) -> TransactionContext: ...

# Implementations
class InMemoryTrustStore(TrustStore): ...      # eatp.store.memory
class FilesystemStore(TrustStore): ...          # eatp.store.filesystem
```

### `eatp.enforce` — Enforcement

```python
class Verdict(Enum):
    AUTO_APPROVED = "auto_approved"
    FLAGGED = "flagged"
    HELD = "held"
    BLOCKED = "blocked"

class StrictEnforcer:
    def __init__(self, on_held=HeldBehavior.RAISE, held_callback=None, flag_threshold=None): ...
    def classify(self, result: VerificationResult) -> Verdict: ...
    def enforce(self, agent_id: str, action: str, result: VerificationResult) -> Verdict: ...

class EATPBlockedError(PermissionError): ...
class EATPHeldError(PermissionError): ...
```

### `eatp.postures` — Trust Postures

```python
class TrustPosture(str, Enum):
    FULL_AUTONOMY = "full_autonomy"   # autonomy_level=5
    ASSISTED = "assisted"              # autonomy_level=4
    SUPERVISED = "supervised"          # autonomy_level=3
    HUMAN_DECIDES = "human_decides"    # autonomy_level=2
    BLOCKED = "blocked"                # autonomy_level=1

    @property
    def autonomy_level(self) -> int: ...
    def can_upgrade_to(self, target: TrustPosture) -> bool: ...
    def can_downgrade_to(self, target: TrustPosture) -> bool: ...
```

### `eatp.exceptions` — Error Hierarchy

```python
class TrustError(Exception): ...                    # Base
class AuthorityNotFoundError(TrustError): ...        # Authority missing
class AuthorityInactiveError(TrustError): ...        # Authority deactivated
class TrustChainNotFoundError(TrustError): ...       # No chain for agent
class InvalidTrustChainError(TrustError): ...        # Chain verification failed
class AgentAlreadyEstablishedError(TrustError): ...  # Duplicate ESTABLISH
class CapabilityNotFoundError(TrustError): ...       # Missing capability
class ConstraintViolationError(TrustError): ...      # Constraint check failed
class DelegationError(TrustError): ...               # Delegation problem
class InvalidSignatureError(TrustError): ...         # Crypto verification failed
class VerificationFailedError(TrustError): ...       # VERIFY operation failed
```

### Additional Modules

| Module                             | Purpose                         | Key Classes                                                    |
| ---------------------------------- | ------------------------------- | -------------------------------------------------------------- |
| `eatp.reasoning`                   | Reasoning trace extension       | `ReasoningTrace`, `ConfidentialityLevel`                       |
| `eatp.scoring`                     | Trust score computation         | `compute_trust_score()`, `analyse_trust_chain()`               |
| `eatp.trusted_agent`               | Trust-enhanced agent wrapper    | `TrustedAgent`, `TrustedAgentConfig`, `TrustedSupervisorAgent` |
| `eatp.constraint_validator`        | Constraint tightening logic     | `ConstraintValidator`                                          |
| `eatp.constraints.builtin`         | Built-in constraint types       | Financial, temporal, operational constraints                   |
| `eatp.constraints.dimension`       | 5 constraint dimensions         | `ConstraintDimension`                                          |
| `eatp.constraints.evaluator`       | Constraint evaluation           | `ConstraintEvaluator`                                          |
| `eatp.messaging.channel`           | Secure agent communication      | `SecureChannel`                                                |
| `eatp.messaging.signer`            | Message signing                 | `MessageSigner`                                                |
| `eatp.messaging.verifier`          | Message verification            | `MessageVerifier`                                              |
| `eatp.messaging.replay_protection` | Nonce-based replay defense      | `InMemoryReplayProtection`                                     |
| `eatp.registry.agent_registry`     | Agent discovery                 | `AgentRegistry`                                                |
| `eatp.registry.health`             | Health monitoring               | `AgentHealthMonitor`                                           |
| `eatp.orchestration.runtime`       | Trust-aware workflow runtime    | `TrustAwareOrchestrationRuntime`                               |
| `eatp.orchestration.policy`        | Policy engine                   | `TrustPolicyEngine`                                            |
| `eatp.esa.base`                    | Enterprise System Agent         | `EnterpriseSystemAgent`                                        |
| `eatp.a2a.service`                 | HTTP/JSON-RPC service           | `A2AService`                                                   |
| `eatp.a2a.agent_card`              | Agent card generation           | `AgentCardGenerator`                                           |
| `eatp.rotation`                    | Credential rotation             | `CredentialRotationManager`                                    |
| `eatp.security`                    | Security events + rate limiting | `SecurityEventType`, `TrustRateLimiter`                        |
| `eatp.merkle`                      | Merkle tree audit integrity     | `MerkleTree`                                                   |
| `eatp.cache`                       | Trust chain caching             | `TrustChainCache`                                              |
| `eatp.crl`                         | Certificate revocation list     | `CertificateRevocationList`                                    |
| `eatp.multi_sig`                   | Multi-signature support         | `MultiSigPolicy`                                               |
| `eatp.interop.jwt`                 | JWT interoperability            | `to_jwt()`, `from_jwt()`                                       |
| `eatp.interop.sd_jwt`              | SD-JWT selective disclosure     | SD-JWT functions                                               |
| `eatp.interop.did`                 | DID resolution                  | DID functions                                                  |
| `eatp.interop.w3c_vc`              | W3C Verifiable Credentials      | VC conversion                                                  |
| `eatp.interop.ucan`                | UCAN token conversion           | UCAN functions                                                 |
| `eatp.interop.biscuit`             | Biscuit token conversion        | Biscuit functions                                              |
| `eatp.knowledge.bridge`            | Knowledge provenance bridge     | `KnowledgeBridge`                                              |
| `eatp.governance.policy_engine`    | Governance policy engine        | `GovernancePolicyEngine`                                       |
| `eatp.governance.rate_limiter`     | Rate limiting                   | `GovernanceRateLimiter`                                        |
| `eatp.mcp.server`                  | MCP server for trust ops        | `EATPMCPServer`                                                |
| `eatp.cli.commands`                | CLI interface                   | `eatp` command                                                 |
