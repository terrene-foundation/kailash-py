# Enterprise Agent Trust Protocol (EATP) - v0.8.0

**Cryptographically verifiable trust chains for AI agents**, enabling enterprise-grade accountability, authorization, and secure multi-agent communication.

## Overview

EATP provides complete trust infrastructure for production AI agents:

- **Trust Lineage Chains**: Cryptographically linked chain of genesis, capabilities, delegations, and audit anchors
- **TrustedAgent**: BaseAgent extension with built-in trust verification
- **Agent Registry**: Capability-based discovery with health monitoring
- **Secure Messaging**: End-to-end encrypted, replay-protected agent communication
- **Trust-Aware Orchestration**: Workflow runtime with trust context propagation
- **Enterprise System Agent (ESA)**: Proxy agents for legacy systems
- **A2A HTTP Service**: REST/JSON-RPC API for trust operations

**Location**: `kaizen.trust` module

## Quick Start

### Basic Trust Establishment

```python
from kaizen.trust import (
    TrustOperations,
    PostgresTrustStore,
    OrganizationalAuthorityRegistry,
    TrustKeyManager,
    CapabilityRequest,
    CapabilityType,
)

# Initialize trust components
store = PostgresTrustStore(connection_string="postgresql://...")
registry = OrganizationalAuthorityRegistry()
key_manager = TrustKeyManager()
trust_ops = TrustOperations(registry, key_manager, store)
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
)

if result.valid:
    print(f"Verification level: {result.level}")
```

### TrustedAgent Usage

```python
from kaizen.trust import TrustedAgent, TrustedAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

class AnalyzeSignature(Signature):
    data: str = InputField(description="Data to analyze")
    result: str = OutputField(description="Analysis result")

# Create TrustedAgent (inherits from BaseAgent)
config = TrustedAgentConfig(
    agent_id="analyzer-001",
    authority_id="org-acme",
    capabilities=["analyze_data", "generate_reports"],
    llm_provider="openai",
    model="gpt-4",
)

agent = TrustedAgent(
    config=config,
    trust_operations=trust_ops,
    signature=AnalyzeSignature(),
)

# Trust establishment happens automatically
await agent.establish_trust()

# Run with trust verification
result = await agent.run(data="sales data...")
```

### Trust Delegation

```python
from kaizen.trust import TrustedSupervisorAgent

# Supervisor delegates to workers
supervisor = TrustedSupervisorAgent(
    config=supervisor_config,
    trust_operations=trust_ops,
)

# Delegate capability to worker with constraints
await supervisor.delegate_to_worker(
    worker_agent=worker,
    capability="process_data",
    constraints={"max_records": 1000},
    duration_hours=24,
)

# Worker now has delegated capability
result = await worker.run(data=input_data)
```

## Core Concepts

### Trust Lineage Chain

A complete trust chain for an agent containing:

```python
from kaizen.trust import (
    TrustLineageChain,
    GenesisRecord,
    CapabilityAttestation,
    DelegationRecord,
    AuditAnchor,
    AuthorityType,
    CapabilityType,
)

chain = TrustLineageChain(
    agent_id="agent-001",
    genesis=GenesisRecord(
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATIONAL,
        timestamp=datetime.utcnow(),
        public_key=public_key,
        signature=signature,
    ),
    capabilities=[
        CapabilityAttestation(
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            attestor_id="org-acme",
            timestamp=datetime.utcnow(),
            signature=signature,
        )
    ],
    delegations=[],  # DelegationRecord list
    audit_anchors=[],  # AuditAnchor list
)
```

**Components**:
- **GenesisRecord**: Initial trust establishment (who created this agent)
- **CapabilityAttestation**: Attested capabilities (what can it do)
- **DelegationRecord**: Delegated capabilities from other agents
- **AuditAnchor**: Cryptographic proof of actions taken

### Trust Operations

Four core operations: ESTABLISH, DELEGATE, VERIFY, AUDIT

```python
from kaizen.trust import TrustOperations, ActionResult

# ESTABLISH - Create trust chain for new agent
chain = await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[CapabilityRequest(
        capability="analyze",
        capability_type=CapabilityType.ACCESS
    )],
)

# DELEGATE - Grant capability from one agent to another
delegation = await trust_ops.delegate(
    from_agent_id="supervisor-001",
    to_agent_id="worker-001",
    capability="process_data",
    constraints={"max_records": 100},
    duration_hours=24,
)

# VERIFY - Check if agent can perform action
result = await trust_ops.verify(
    agent_id="agent-001",
    action="analyze_data",
)

# AUDIT - Record action for compliance
await trust_ops.audit(
    agent_id="agent-001",
    action="analyze_data",
    result=ActionResult.SUCCESS,
    metadata={"records_processed": 500},
)
```

### Agent Registry

Capability-based discovery with health monitoring:

```python
from kaizen.trust import (
    AgentRegistry,
    AgentHealthMonitor,
    DiscoveryQuery,
    AgentStatus,
    PostgresAgentRegistryStore,
)

# Initialize registry
store = PostgresAgentRegistryStore(connection_string="postgresql://...")
registry = AgentRegistry(store=store)

# Register agents
await registry.register(
    agent_id="analyzer-001",
    capabilities=["analyze_data", "generate_reports"],
    metadata={"version": "1.0", "owner": "data-team"},
)

# Discover agents by capability
agents = await registry.discover(
    DiscoveryQuery(
        capability="analyze_data",
        status=AgentStatus.ACTIVE,
    )
)

# Health monitoring
monitor = AgentHealthMonitor(registry=registry)
await monitor.start()

# Update agent health
await registry.update_status("analyzer-001", AgentStatus.ACTIVE)
await registry.heartbeat("analyzer-001")
```

### Secure Messaging

End-to-end encrypted, replay-protected communication:

```python
from kaizen.trust import (
    SecureChannel,
    MessageSigner,
    MessageVerifier,
    InMemoryReplayProtection,
)

# Create secure channel between agents
channel = SecureChannel(
    sender_id="agent-001",
    receiver_id="agent-002",
    signer=MessageSigner(private_key=sender_private_key),
    verifier=MessageVerifier(
        public_keys={"agent-001": sender_public_key}
    ),
    replay_protection=InMemoryReplayProtection(),
)

# Send encrypted message
envelope = await channel.send(
    payload={"task": "analyze", "data": "..."},
)

# Receive and verify message
result = await channel.receive(envelope)
if result.valid:
    payload = result.payload
```

**SecureMessageEnvelope** features:
- HMAC-based message authentication
- Nonce-based replay protection
- Timestamp validation
- Sender/receiver verification

### Trust-Aware Orchestration

Workflow runtime with trust context propagation:

```python
from kaizen.trust import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustExecutionContext,
    TrustPolicyEngine,
    TrustPolicy,
    PolicyType,
)

# Configure trust-aware runtime
config = TrustAwareRuntimeConfig(
    verify_on_execute=True,
    propagate_context=True,
    enforce_policies=True,
)

# Create policy engine
policy_engine = TrustPolicyEngine()
policy_engine.add_policy(TrustPolicy(
    name="require-active-agents",
    policy_type=PolicyType.CAPABILITY,
    rule=lambda ctx: ctx.agent_status == AgentStatus.ACTIVE,
))

# Create trust-aware runtime
runtime = TrustAwareOrchestrationRuntime(
    trust_operations=trust_ops,
    policy_engine=policy_engine,
    config=config,
)

# Execute with trust context
context = TrustExecutionContext(
    agent_id="agent-001",
    capabilities=["analyze_data"],
    delegation_chain=[],
)

result = await runtime.execute(
    workflow=my_workflow,
    context=context,
)
```

### Enterprise System Agent (ESA)

Proxy agents for legacy systems:

```python
from kaizen.trust import (
    EnterpriseSystemAgent,
    ESAConfig,
    SystemMetadata,
    SystemConnectionInfo,
    CapabilityMetadata,
)

# Configure ESA for legacy system
config = ESAConfig(
    system_id="erp-system",
    system_metadata=SystemMetadata(
        name="Enterprise ERP",
        version="5.2",
        vendor="SAP",
    ),
    connection_info=SystemConnectionInfo(
        protocol="https",
        host="erp.company.com",
        port=443,
    ),
    capabilities=[
        CapabilityMetadata(
            name="get_inventory",
            description="Retrieve inventory levels",
            parameters={"warehouse_id": "string"},
        ),
    ],
)

# Create ESA
esa = EnterpriseSystemAgent(
    config=config,
    trust_operations=trust_ops,
)

# Establish trust for ESA
await esa.establish_trust(authority_id="org-acme")

# Execute operation through ESA
result = await esa.execute(
    operation="get_inventory",
    parameters={"warehouse_id": "WH-001"},
)
```

**ESA Use Cases**:
- Wrap legacy APIs with trust verification
- Bridge non-AI systems into agent ecosystem
- Provide accountability for external system calls

### A2A HTTP Service

REST/JSON-RPC API for trust operations:

```python
from kaizen.trust import create_a2a_app, A2AService, AgentCardGenerator

# Create A2A service
service = A2AService(
    trust_operations=trust_ops,
    agent_registry=registry,
)

# Generate agent cards
card_generator = AgentCardGenerator(trust_operations=trust_ops)
card = await card_generator.generate("agent-001")

# Create FastAPI app
app = create_a2a_app(service)

# Run server
# uvicorn app:app --host 0.0.0.0 --port 8000
```

**Available Endpoints**:
- `POST /a2a/verify` - Verify agent trust
- `POST /a2a/delegate` - Delegate capability
- `GET /a2a/card/{agent_id}` - Get agent card
- `POST /a2a/audit/query` - Query audit trail

**JSON-RPC Methods**:
- `trust.verify` - Verify trust
- `trust.delegate` - Delegate capability
- `trust.audit` - Record audit event
- `agent.card` - Get agent card

## Security Features

### Credential Rotation

```python
from kaizen.trust import CredentialRotationManager, RotationStatus

rotation_manager = CredentialRotationManager(
    key_manager=key_manager,
    trust_store=store,
)

# Schedule automatic rotation
await rotation_manager.schedule_rotation(
    agent_id="agent-001",
    interval_days=30,
)

# Manual rotation
result = await rotation_manager.rotate("agent-001")
if result.status == RotationStatus.SUCCESS:
    print(f"New key fingerprint: {result.new_key_fingerprint}")
```

### Rate Limiting

```python
from kaizen.trust import TrustRateLimiter, RateLimitExceededError

rate_limiter = TrustRateLimiter(
    max_verifications_per_minute=100,
    max_delegations_per_hour=10,
)

try:
    await rate_limiter.check("verify", agent_id="agent-001")
except RateLimitExceededError:
    print("Rate limit exceeded")
```

### Security Audit Logging

```python
from kaizen.trust import (
    SecurityAuditLogger,
    SecurityEvent,
    SecurityEventType,
    SecurityEventSeverity,
)

audit_logger = SecurityAuditLogger(output="security.log")

await audit_logger.log(SecurityEvent(
    event_type=SecurityEventType.VERIFICATION_FAILED,
    severity=SecurityEventSeverity.WARNING,
    agent_id="agent-001",
    details={"reason": "capability not found"},
))
```

## Component Reference

| Component | Purpose | Module |
|-----------|---------|--------|
| `TrustLineageChain` | Complete trust chain | `kaizen.trust.chain` |
| `TrustOperations` | Core trust operations | `kaizen.trust.operations` |
| `TrustedAgent` | BaseAgent with trust | `kaizen.trust.trusted_agent` |
| `TrustedSupervisorAgent` | Delegation support | `kaizen.trust.trusted_agent` |
| `AgentRegistry` | Agent discovery | `kaizen.trust.registry` |
| `AgentHealthMonitor` | Health monitoring | `kaizen.trust.registry` |
| `SecureChannel` | Encrypted messaging | `kaizen.trust.messaging` |
| `TrustExecutionContext` | Context propagation | `kaizen.trust.orchestration` |
| `TrustPolicyEngine` | Policy enforcement | `kaizen.trust.orchestration` |
| `TrustAwareOrchestrationRuntime` | Trust-aware runtime | `kaizen.trust.orchestration` |
| `EnterpriseSystemAgent` | Legacy system proxy | `kaizen.trust.esa` |
| `A2AService` | HTTP API | `kaizen.trust.a2a` |
| `CredentialRotationManager` | Key rotation | `kaizen.trust.rotation` |
| `TrustRateLimiter` | Rate limiting | `kaizen.trust.security` |
| `SecurityAuditLogger` | Audit logging | `kaizen.trust.security` |
| `PostgresTrustStore` | Persistent storage | `kaizen.trust.store` |
| `TrustChainCache` | Performance caching | `kaizen.trust.cache` |

## When to Use EATP

**Use EATP when you need**:
- Enterprise-grade accountability for AI agents
- Regulatory compliance (audit trails, provenance)
- Cross-organization agent coordination
- Secure agent-to-agent communication
- Capability-based access control
- Trust delegation with constraints

**Don't use EATP when**:
- Simple single-agent applications
- Internal-only prototypes
- No compliance requirements
- Performance-critical paths without trust needs

## Best Practices

### Trust Establishment
- ✅ Establish trust before first agent action
- ✅ Use specific capability types (ACCESS, EXECUTE, DELEGATE)
- ✅ Set appropriate constraints on capabilities
- ❌ Never skip trust verification in production

### Delegation
- ✅ Use time-limited delegations
- ✅ Apply principle of least privilege
- ✅ Record delegation chain for audit
- ❌ Never delegate more capabilities than needed

### Secure Messaging
- ✅ Always use SecureChannel for inter-agent communication
- ✅ Enable replay protection
- ✅ Verify message signatures
- ❌ Never send sensitive data without encryption

### Production Deployment
- ✅ Use PostgresTrustStore for persistence
- ✅ Enable TrustChainCache for performance
- ✅ Configure credential rotation
- ✅ Enable security audit logging
- ❌ Never disable trust verification in production

## Related Guides

- **[BaseAgent Architecture](baseagent-architecture.md)** - Foundation for TrustedAgent
- **[Multi-Agent Coordination](multi-agent-coordination.md)** - Coordination patterns
- **[Hooks System](hooks-system.md)** - Event-driven observability

## Support

- **Source**: `src/kaizen/trust/`
- **Tests**: `tests/unit/trust/`, `tests/integration/trust/`, `tests/e2e/trust/`
