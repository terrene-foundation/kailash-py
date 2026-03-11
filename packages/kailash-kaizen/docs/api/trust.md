# EATP Trust Module API Reference

Enterprise Agent Trust Protocol (EATP) - Complete API documentation for cryptographically verifiable trust chains in AI agents.

## Overview

The `kaizen.trust` module provides enterprise-grade trust management for AI agents:

- **Cryptographic Verification**: Ed25519 signatures for all trust operations
- **Trust Lineage Chains**: Complete audit trail from authorization to action
- **Multi-Agent Coordination**: Delegation, orchestration, and secure messaging
- **A2A Protocol Compliance**: Google A2A protocol with trust extensions
- **Enterprise System Integration**: ESA pattern for legacy system proxying

## Quick Start

```python
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    CapabilityRequest,
    CapabilityType,
    VerificationLevel,
)

# Initialize components
store = PostgresTrustStore(database_url="postgresql://...")
registry = OrganizationalAuthorityRegistry(database_url="postgresql://...")
key_manager = TrustKeyManager()

trust_ops = TrustOperations(
    authority_registry=registry,
    key_manager=key_manager,
    trust_store=store,
)
await trust_ops.initialize()

# Establish trust for an agent
chain = await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[
        CapabilityRequest(
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
        )
    ],
)

# Verify trust before action
result = await trust_ops.verify(
    agent_id="agent-001",
    action="analyze_data",
    level=VerificationLevel.STANDARD,
)

if result.valid:
    print("Trust verified, proceed with action")
```

---

## Core Components

### TrustLineageChain

Complete cryptographic trust chain for an agent.

```python
@dataclass
class TrustLineageChain:
    genesis: GenesisRecord           # Who authorized this agent
    capabilities: List[CapabilityAttestation]  # What it can do
    delegations: List[DelegationRecord]        # Who delegated to it
    constraint_envelope: Optional[ConstraintEnvelope]  # Limits
    audit_anchors: List[AuditAnchor]  # What it has done
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `verify_basic()` | Quick integrity verification (hash, expiration) |
| `verify_signatures()` | Full cryptographic signature verification |
| `has_capability(cap)` | Check if agent has specific capability |
| `get_effective_constraints()` | Get merged constraints from all sources |
| `to_dict()` / `from_dict()` | Serialize/deserialize chain |

### TrustOperations

Core EATP operations: ESTABLISH, DELEGATE, VERIFY, AUDIT.

```python
class TrustOperations:
    def __init__(
        self,
        authority_registry: OrganizationalAuthorityRegistry,
        key_manager: TrustKeyManager,
        trust_store: PostgresTrustStore,
    ): ...
```

**Methods:**

#### establish()

Create initial trust for an agent.

```python
async def establish(
    agent_id: str,
    authority_id: str,
    capabilities: List[CapabilityRequest],
    constraints: Optional[List[Constraint]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    expires_at: Optional[datetime] = None,
) -> TrustLineageChain
```

**Parameters:**
- `agent_id`: Unique identifier for the agent
- `authority_id`: ID of the authorizing authority
- `capabilities`: List of capabilities to grant
- `constraints`: Optional constraints on agent behavior
- `metadata`: Additional context (department, owner, etc.)
- `expires_at`: Optional expiration datetime

**Returns:** Complete `TrustLineageChain`

**Raises:**
- `AuthorityNotFoundError`: Authority doesn't exist
- `AuthorityInactiveError`: Authority is deactivated
- `AgentAlreadyEstablishedError`: Agent already has trust chain

#### delegate()

Transfer trust from one agent to another.

```python
async def delegate(
    delegator_agent_id: str,
    delegatee_agent_id: str,
    task_id: str,
    capabilities: List[str],
    constraints: Optional[List[Constraint]] = None,
    expires_at: Optional[datetime] = None,
) -> DelegationRecord
```

**Important:** Constraints can only be tightened, never loosened.

**Raises:**
- `DelegationError`: Delegator doesn't have trust
- `ConstraintViolationError`: Attempted to loosen constraints

#### verify()

Validate trust for an action.

```python
async def verify(
    agent_id: str,
    action: Optional[str] = None,
    resource_uri: Optional[str] = None,
    level: VerificationLevel = VerificationLevel.STANDARD,
) -> VerificationResult
```

**Verification Levels:**

| Level | Target Latency | Checks |
|-------|---------------|--------|
| `QUICK` | <1ms | Hash + expiration only |
| `STANDARD` | <5ms | + Capability match, constraints |
| `FULL` | <50ms | + Signature verification |

#### audit()

Record an agent action.

```python
async def audit(
    agent_id: str,
    action_type: str,
    resource_uri: str,
    result: ActionResult,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditAnchor
```

---

## Data Structures

### GenesisRecord

Cryptographic proof of agent authorization.

```python
@dataclass
class GenesisRecord:
    id: str                          # Unique record ID
    agent_id: str                    # Agent being authorized
    authority_id: str                # Who authorized
    authority_type: AuthorityType    # ORGANIZATION, SYSTEM, HUMAN
    created_at: datetime             # When authorized
    expires_at: Optional[datetime]   # Optional expiration
    signature: str                   # Ed25519 signature
    signature_algorithm: str = "Ed25519"
    metadata: Dict[str, Any] = {}
```

### CapabilityAttestation

What an agent is authorized to do.

```python
@dataclass
class CapabilityAttestation:
    id: str
    agent_id: str
    capability_type: CapabilityType  # ACCESS, ACTION, DELEGATION
    capability_uri: str              # e.g., "analyze_data"
    granted_by: str                  # Authority ID
    granted_at: datetime
    expires_at: Optional[datetime]
    constraints: List[str]           # Capability-specific limits
    signature: str
```

### CapabilityType Enum

```python
class CapabilityType(Enum):
    ACCESS = "access"       # Can access resources
    ACTION = "action"       # Can perform actions
    DELEGATION = "delegation"  # Can delegate to others
```

### DelegationRecord

Trust transfer between agents.

```python
@dataclass
class DelegationRecord:
    id: str
    delegator_agent_id: str
    delegatee_agent_id: str
    task_id: str
    capabilities_delegated: List[str]
    constraints: List[Constraint]
    delegated_at: datetime
    expires_at: Optional[datetime]
    signature: str
```

### Constraint

Limits on agent behavior.

```python
@dataclass
class Constraint:
    constraint_type: ConstraintType
    name: str
    value: Any
    metadata: Dict[str, Any] = {}
```

### ConstraintType Enum

```python
class ConstraintType(Enum):
    RESOURCE_LIMIT = "resource_limit"      # max_api_calls, max_tokens
    TIME_WINDOW = "time_window"            # business_hours_only
    DATA_SCOPE = "data_scope"              # department_data_only
    ACTION_RESTRICTION = "action_restriction"  # read_only
    AUDIT_REQUIREMENT = "audit_requirement"    # log_all_actions
```

### AuditAnchor

Tamper-proof record of agent action.

```python
@dataclass
class AuditAnchor:
    id: str
    agent_id: str
    action_type: str
    resource_uri: str
    timestamp: datetime
    result: ActionResult
    trust_verification_id: Optional[str]
    metadata: Dict[str, Any]
    signature: str
```

### VerificationResult

Result of trust verification.

```python
@dataclass
class VerificationResult:
    valid: bool
    level: VerificationLevel
    errors: List[str] = []
    latency_ms: float = 0.0
    chain_hash: Optional[str] = None
    verified_at: Optional[datetime] = None
```

---

## Storage

### PostgresTrustStore

Persistent storage for trust chains.

```python
class PostgresTrustStore:
    def __init__(
        self,
        database_url: str,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 300,
        pool_min_size: int = 5,
        pool_max_size: int = 20,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `initialize()` | Create tables and connection pool |
| `get_chain(agent_id)` | Retrieve trust chain |
| `store_chain(chain)` | Store new trust chain |
| `update_chain(chain)` | Update existing chain |
| `delete_chain(agent_id)` | Remove trust chain |
| `list_chains(authority_id)` | List chains by authority |
| `close()` | Close connections |

### TrustChainCache

In-memory LRU cache for trust chains (Phase 3 Week 11).

```python
class TrustChainCache:
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 300,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `get(agent_id)` | Get cached chain |
| `set(agent_id, chain)` | Cache chain with TTL |
| `invalidate(agent_id)` | Remove from cache |
| `invalidate_all()` | Clear entire cache |
| `get_stats()` | Get hit/miss statistics |

**Performance:** <1ms cache hit (100x+ speedup vs database)

---

## Authority Management

### OrganizationalAuthority

An entity that can authorize agents.

```python
@dataclass
class OrganizationalAuthority:
    id: str
    name: str
    authority_type: AuthorityType
    public_key: str
    signing_key_id: str
    permissions: List[AuthorityPermission]
    is_active: bool = True
    metadata: Dict[str, Any] = {}
```

### AuthorityPermission Enum

```python
class AuthorityPermission(Enum):
    CREATE_AGENTS = "create_agents"
    GRANT_CAPABILITIES = "grant_capabilities"
    REVOKE_CAPABILITIES = "revoke_capabilities"
    CREATE_SUB_AUTHORITIES = "create_sub_authorities"
```

### OrganizationalAuthorityRegistry

Manages authority lifecycle.

```python
class OrganizationalAuthorityRegistry:
    def __init__(
        self,
        database_url: str,
        enable_cache: bool = True,
        cache_ttl_seconds: int = 300,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `register_authority(authority)` | Register new authority |
| `get_authority(authority_id)` | Retrieve authority |
| `update_authority(authority)` | Update authority |
| `deactivate_authority(authority_id)` | Mark inactive |
| `list_authorities()` | List all authorities |

---

## Trusted Agents

### TrustedAgent

BaseAgent with automatic trust verification.

```python
class TrustedAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        trust_operations: TrustOperations,
        config: Optional[TrustedAgentConfig] = None,
        **kwargs,
    ): ...
```

**Configuration:**

```python
@dataclass
class TrustedAgentConfig:
    verification_level: VerificationLevel = VerificationLevel.STANDARD
    audit_all_actions: bool = True
    fail_on_verification_error: bool = True
    cache_verification_ms: int = 5000
```

**Automatic Behavior:**
- Verifies trust before `run()`
- Verifies capability before `call_tool()`
- Audits all actions after execution

### TrustedSupervisorAgent

Supervisor that can delegate to workers.

```python
class TrustedSupervisorAgent(TrustedAgent):
    async def delegate_task(
        self,
        worker_agent_id: str,
        task_id: str,
        capabilities: List[str],
        constraints: Optional[List[Constraint]] = None,
    ) -> DelegationRecord: ...

    async def verify_worker(
        self,
        worker_agent_id: str,
    ) -> VerificationResult: ...
```

---

## Agent Registry (Phase 2 Week 5)

### AgentRegistry

Central registry for agent discovery.

```python
class AgentRegistry:
    def __init__(
        self,
        store: AgentRegistryStore,
        trust_operations: TrustOperations,
        health_monitor: Optional[AgentHealthMonitor] = None,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `register(request)` | Register agent with trust verification |
| `discover(query)` | Find agents by capability, status |
| `get(agent_id)` | Get agent metadata |
| `update_status(agent_id, status)` | Update agent status |
| `deregister(agent_id)` | Remove agent |

### DiscoveryQuery

Query agents by capability and status.

```python
@dataclass
class DiscoveryQuery:
    capabilities: Optional[List[str]] = None
    status: Optional[AgentStatus] = None
    authority_id: Optional[str] = None
    limit: int = 100
```

### AgentHealthMonitor

Background health monitoring.

```python
class AgentHealthMonitor:
    def __init__(
        self,
        registry_store: AgentRegistryStore,
        check_interval_seconds: int = 60,
        stale_threshold_seconds: int = 300,
    ): ...
```

---

## Secure Messaging (Phase 2 Week 6)

### SecureChannel

End-to-end encrypted messaging between agents.

```python
class SecureChannel:
    def __init__(
        self,
        sender_id: str,
        sender_private_key: str,
        key_manager: TrustKeyManager,
        replay_protection: Optional[ReplayProtection] = None,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `send(recipient_id, message)` | Send encrypted message |
| `receive(envelope)` | Verify and decrypt message |
| `get_statistics()` | Get channel statistics |

### SecureMessageEnvelope

Signed, encrypted message container.

```python
@dataclass
class SecureMessageEnvelope:
    id: str
    sender_id: str
    recipient_id: str
    encrypted_payload: str
    signature: str
    timestamp: datetime
    nonce: str
    metadata: MessageMetadata
```

---

## Orchestration Integration (Phase 2 Week 7)

### TrustExecutionContext

Trust state propagation through workflows.

```python
class TrustExecutionContext:
    @classmethod
    def create(
        cls,
        parent_agent_id: str,
        task_id: str,
        delegated_capabilities: List[str],
        inherited_constraints: Optional[Dict[str, Any]] = None,
    ) -> "TrustExecutionContext": ...
```

### TrustPolicy

Policy-based trust evaluation.

```python
class TrustPolicy:
    @staticmethod
    def require_genesis() -> TrustPolicy: ...

    @staticmethod
    def require_capability(capability: str) -> TrustPolicy: ...

    @staticmethod
    def enforce_constraint(
        constraint_type: str,
        constraint_value: Any,
    ) -> TrustPolicy: ...

    # Composition
    def and_(self, other: TrustPolicy) -> TrustPolicy: ...
    def or_(self, other: TrustPolicy) -> TrustPolicy: ...
    def not_(self) -> TrustPolicy: ...
```

### TrustAwareOrchestrationRuntime

Trust-aware workflow execution.

```python
class TrustAwareOrchestrationRuntime:
    def __init__(
        self,
        trust_operations: TrustOperations,
        config: Optional[TrustAwareRuntimeConfig] = None,
    ): ...

    async def execute_trusted_workflow(
        self,
        tasks: List[Any],
        context: TrustExecutionContext,
        agent_selector: Callable,
        task_executor: Callable,
    ) -> WorkflowStatus: ...
```

---

## A2A HTTP Service (Phase 3 Week 9)

### A2AService

FastAPI service for A2A protocol.

```python
class A2AService:
    def __init__(
        self,
        trust_operations: TrustOperations,
        agent_id: str,
        agent_name: str,
        agent_capabilities: List[str],
    ): ...

    def create_app(self) -> FastAPI: ...
```

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/.well-known/agent.json` | GET | Agent Card |
| `/a2a/jsonrpc` | POST | JSON-RPC 2.0 |

**JSON-RPC Methods:**

| Method | Description |
|--------|-------------|
| `agent.invoke` | Invoke agent action |
| `agent.capabilities` | List capabilities |
| `trust.verify` | Verify agent trust |
| `trust.delegate` | Request delegation |
| `audit.query` | Query audit trail |

### AgentCard

A2A Agent Card with trust extensions.

```python
@dataclass
class AgentCard:
    name: str
    version: str
    description: str
    capabilities: List[AgentCapability]
    trust_extensions: TrustExtensions
    endpoint: str
```

---

## Enterprise System Agent (Phase 3 Week 10)

### EnterpriseSystemAgent

Proxy agents for legacy systems.

```python
class EnterpriseSystemAgent:
    def __init__(
        self,
        system_id: str,
        system_type: str,
        trust_operations: TrustOperations,
        authority_id: str,
        config: Optional[ESAConfig] = None,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `discover_capabilities()` | Discover system capabilities |
| `establish_trust()` | Establish trust for ESA |
| `execute(operation, params)` | Execute system operation |
| `delegate_to_agent(agent_id)` | Delegate to AI agent |

### DatabaseESA

ESA for SQL databases.

```python
from kaizen.trust.esa import DatabaseESA

esa = DatabaseESA(
    system_id="db-finance",
    database_url="postgresql://...",
    trust_operations=trust_ops,
    authority_id="org-acme",
)

# Discover capabilities from schema
capabilities = await esa.discover_capabilities()
# Returns: ["select_users", "insert_users", ...]

# Execute query with trust
result = await esa.execute(
    operation="select_users",
    parameters={"limit": 100},
)
```

### APIESA

ESA for REST APIs.

```python
from kaizen.trust.esa import APIESA

esa = APIESA(
    system_id="api-crm",
    base_url="https://api.crm.com",
    trust_operations=trust_ops,
    authority_id="org-acme",
    openapi_spec=spec,  # Optional OpenAPI spec
)

# Discover capabilities from OpenAPI
capabilities = await esa.discover_capabilities()
# Returns: ["get_customers", "post_orders", ...]

# Execute API call with trust
result = await esa.execute(
    operation="get_customers",
    parameters={"path": "/customers", "params": {"limit": 50}},
)
```

---

## Security (Phase 3 Week 11)

### CredentialRotationManager

Periodic key rotation.

```python
class CredentialRotationManager:
    def __init__(
        self,
        key_manager: TrustKeyManager,
        trust_store: PostgresTrustStore,
        authority_registry: OrganizationalAuthorityRegistry,
        rotation_period_days: int = 90,
        grace_period_hours: int = 24,
    ): ...
```

**Methods:**

| Method | Description |
|--------|-------------|
| `rotate_key(authority_id)` | Rotate authority key |
| `schedule_rotation(authority_id, at)` | Schedule future rotation |
| `get_rotation_status(authority_id)` | Query rotation status |
| `revoke_old_key(authority_id, key_id)` | Revoke after grace period |

### TrustSecurityValidator

Input validation and sanitization.

```python
class TrustSecurityValidator:
    @staticmethod
    def validate_agent_id(agent_id: str) -> bool: ...

    @staticmethod
    def validate_authority_id(authority_id: str) -> bool: ...

    @staticmethod
    def validate_capability_uri(uri: str) -> bool: ...

    @staticmethod
    def sanitize_metadata(metadata: Dict) -> Dict: ...
```

### SecureKeyStorage

Encrypted key storage.

```python
class SecureKeyStorage:
    def __init__(self, encryption_key: Optional[bytes] = None): ...

    def store_key(self, key_id: str, private_key: str) -> None: ...
    def get_key(self, key_id: str) -> str: ...
    def delete_key(self, key_id: str) -> None: ...
```

### TrustRateLimiter

Per-authority rate limiting.

```python
class TrustRateLimiter:
    def __init__(
        self,
        default_limit: int = 100,
        window_seconds: int = 60,
    ): ...

    async def check(self, authority_id: str) -> bool: ...
    def get_remaining(self, authority_id: str) -> int: ...
```

---

## Exceptions

### Core Exceptions

| Exception | Description |
|-----------|-------------|
| `TrustError` | Base exception |
| `AuthorityNotFoundError` | Authority doesn't exist |
| `AuthorityInactiveError` | Authority deactivated |
| `TrustChainNotFoundError` | No trust chain for agent |
| `InvalidTrustChainError` | Chain fails verification |
| `CapabilityNotFoundError` | Capability not granted |
| `ConstraintViolationError` | Constraint check failed |
| `DelegationError` | Delegation not allowed |
| `InvalidSignatureError` | Signature verification failed |
| `VerificationFailedError` | Trust verification failed |
| `AgentAlreadyEstablishedError` | Agent already has trust |

### A2A Exceptions

| Exception | Description |
|-----------|-------------|
| `A2AError` | Base A2A exception |
| `JsonRpcParseError` | Invalid JSON-RPC |
| `JsonRpcInvalidRequestError` | Malformed request |
| `JsonRpcMethodNotFoundError` | Unknown method |
| `AuthenticationError` | Invalid/expired token |
| `AuthorizationError` | Insufficient permissions |

### ESA Exceptions

| Exception | Description |
|-----------|-------------|
| `ESAError` | Base ESA exception |
| `ESANotEstablishedError` | ESA lacks trust |
| `ESACapabilityNotFoundError` | Capability not discovered |
| `ESAOperationError` | System operation failed |
| `ESAConnectionError` | System unreachable |

---

## Cryptographic Utilities

### Key Generation

```python
from kaizen.trust.crypto import generate_keypair

private_key, public_key = generate_keypair()
```

### Signing

```python
from kaizen.trust.crypto import sign, verify_signature

signature = sign(private_key, message_bytes)
is_valid = verify_signature(public_key, message_bytes, signature)
```

### Serialization

```python
from kaizen.trust.crypto import serialize_for_signing

# Deterministic JSON serialization for signing
payload_bytes = serialize_for_signing(data_dict)
```

---

## Performance Targets

| Operation | Target (p95) | Achieved |
|-----------|--------------|----------|
| VERIFY QUICK | <5ms | <1ms |
| VERIFY STANDARD | <50ms | <5ms |
| VERIFY FULL | <100ms | <50ms |
| ESTABLISH | <100ms | <50ms |
| DELEGATE | <50ms | <30ms |
| AUDIT | <20ms | <10ms |
| Cache Hit | <1ms | <0.5ms |

---

## See Also

- [EATP Migration Guide](../guides/eatp-migration-guide.md)
- [EATP Security Best Practices](../guides/eatp-security-best-practices.md)
- [Trust Examples](../../examples/trust/)
- [Phase 3 Week 11 Documentation](../eatp/phase3-week11-enterprise-hardening.md)
