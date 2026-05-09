# EATP — Kaizen Trust Integration

Cryptographically verifiable trust chains for AI agents. As of v0.1.0, EATP is a standalone SDK (included in `pip install kailash`). `kaizen.trust` is a shim layer re-exporting from the standalone package. For standalone docs, see `skills/26-eatp-reference/`.

## Trust Establishment

```python
from kaizen.trust import (
    TrustOperations, PostgresTrustStore, OrganizationalAuthorityRegistry,
    TrustKeyManager, CapabilityRequest, CapabilityType,
)

store = PostgresTrustStore(connection_string=os.environ["TRUST_DATABASE_URL"])
registry = OrganizationalAuthorityRegistry()
key_manager = TrustKeyManager()
trust_ops = TrustOperations(registry, key_manager, store)
await trust_ops.initialize()

chain = await trust_ops.establish(
    agent_id="agent-001", authority_id="org-acme",
    capabilities=[CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACCESS)],
)

result = await trust_ops.verify(agent_id="agent-001", action="analyze_data")
```

## Human Traceability (v0.8.0)

Every action MUST be traceable to a human. PseudoAgents bridge human auth to the agentic world.

```python
from kaizen.trust.pseudo_agent import PseudoAgent, PseudoAgentFactory, PseudoAgentConfig

factory = PseudoAgentFactory(
    trust_operations=trust_ops,
    default_config=PseudoAgentConfig(
        session_timeout_minutes=60, require_mfa=True,
        allowed_capabilities=["read_data", "process_data"],
    ),
)
pseudo = factory.from_session(
    user_id="user-123", email="alice@corp.com",
    display_name="Alice Chen", session_id="sess-456", auth_provider="okta",
)

# Delegate to agent (ONLY way trust enters the system)
delegation, agent_ctx = await pseudo.delegate_to(
    agent_id="invoice-processor", task_id="november-invoices",
    capabilities=["read_invoices", "process_invoices"],
    constraints={"cost_limit": 1000},
)
result = await agent.execute_async(inputs, context=agent_ctx)
await pseudo.revoke_all_delegations()  # On logout
```

**Key**: HumanOrigin (immutable record), ExecutionContext (async ContextVar), PseudoAgent (ONLY entity initiating trust), ConstraintValidator (can only REDUCE permissions).

## TrustedAgent

```python
from kaizen.trust import TrustedAgent, TrustedAgentConfig

config = TrustedAgentConfig(
    agent_id="analyzer-001", authority_id="org-acme",
    capabilities=["analyze_data", "generate_reports"],
)
agent = TrustedAgent(config=config, trust_operations=trust_ops, signature=AnalyzeSignature())
await agent.establish_trust()
result = await agent.run(data="sales data...")
```

## TrustedSupervisorAgent

```python
from kaizen.trust import TrustedSupervisorAgent

supervisor = TrustedSupervisorAgent(config=supervisor_config, trust_operations=trust_ops)
await supervisor.delegate_to_worker(
    worker_agent=worker, capability="process_data",
    constraints={"max_records": 1000}, duration_hours=24,
)
```

## Core Operations

```python
# ESTABLISH, DELEGATE, VERIFY, AUDIT
chain = await trust_ops.establish(agent_id="agent-001", authority_id="org-acme",
    capabilities=[CapabilityRequest(capability="analyze", capability_type=CapabilityType.ACCESS)])

delegation = await trust_ops.delegate(
    delegator_id="supervisor-001", delegatee_id="worker-001",
    task_id="data-processing-q4", capabilities=["process_data"],
    additional_constraints=["max_records:100"])

result = await trust_ops.verify(agent_id="agent-001", action="analyze_data")

await trust_ops.audit(agent_id="agent-001", action="analyze_data",
    result=ActionResult.SUCCESS, context_data={"records_processed": 500})
```

## Agent Registry

```python
from kaizen.trust import AgentRegistry, AgentHealthMonitor, DiscoveryQuery, AgentStatus, PostgresAgentRegistryStore

store = PostgresAgentRegistryStore(connection_string=os.environ["REGISTRY_DATABASE_URL"])
registry = AgentRegistry(store=store)
await registry.register(agent_id="analyzer-001", capabilities=["analyze_data"],
    metadata={"version": "1.0"})
agents = await registry.discover(DiscoveryQuery(capability="analyze_data", status=AgentStatus.ACTIVE))

monitor = AgentHealthMonitor(registry=registry)
await monitor.start()
```

## Secure Messaging

```python
from kaizen.trust import SecureChannel, MessageSigner, MessageVerifier, InMemoryReplayProtection

channel = SecureChannel(
    sender_id="agent-001", receiver_id="agent-002",
    signer=MessageSigner(private_key=sender_private_key),
    verifier=MessageVerifier(public_keys={"agent-001": sender_public_key}),
    replay_protection=InMemoryReplayProtection(),
)
envelope = await channel.send(payload={"task": "analyze", "data": "..."})
result = await channel.receive(envelope)
```

## Trust-Aware Orchestration

```python
from kaizen.trust import (
    TrustAwareOrchestrationRuntime, TrustAwareRuntimeConfig,
    TrustExecutionContext, TrustPolicyEngine, TrustPolicy, PolicyType,
)

config = TrustAwareRuntimeConfig(verify_on_execute=True, propagate_context=True, enforce_policies=True)
policy_engine = TrustPolicyEngine()
policy_engine.add_policy(TrustPolicy(
    name="require-active-agents", policy_type=PolicyType.CAPABILITY,
    rule=lambda ctx: ctx.agent_status == AgentStatus.ACTIVE,
))
runtime = TrustAwareOrchestrationRuntime(trust_operations=trust_ops, policy_engine=policy_engine, config=config)
result = await runtime.execute(workflow=my_workflow,
    context=TrustExecutionContext(agent_id="agent-001", capabilities=["analyze_data"], delegation_chain=[]))
```

## Enterprise System Agent (ESA)

```python
from kaizen.trust import EnterpriseSystemAgent, ESAConfig, SystemMetadata, SystemConnectionInfo, CapabilityMetadata

esa = EnterpriseSystemAgent(
    config=ESAConfig(
        system_id="erp-system",
        system_metadata=SystemMetadata(name="Enterprise ERP", version="5.2", vendor="SAP"),
        connection_info=SystemConnectionInfo(protocol="https", host="erp.example.com", port=443),
        capabilities=[CapabilityMetadata(name="get_inventory", description="Retrieve inventory",
            parameters={"warehouse_id": "string"})],
    ),
    trust_operations=trust_ops,
)
await esa.establish_trust(authority_id="org-acme")
result = await esa.execute(operation="get_inventory", parameters={"warehouse_id": "WH-001"})
```

## A2A HTTP Service

```python
from kaizen.trust import create_a2a_app, A2AService, AgentCardGenerator

service = A2AService(trust_operations=trust_ops, agent_registry=registry)
app = create_a2a_app(service)
```

Endpoints: `POST /a2a/verify`, `POST /a2a/delegate`, `GET /a2a/card/{agent_id}`, `POST /a2a/audit/query`
JSON-RPC: `trust.verify`, `trust.delegate`, `trust.audit`, `agent.card`

## Security Features

```python
# Credential rotation
from kaizen.trust import CredentialRotationManager
rotation_manager = CredentialRotationManager(key_manager=key_manager, trust_store=store)
await rotation_manager.schedule_rotation(agent_id="agent-001", interval_days=30)

# Rate limiting
from kaizen.trust import TrustRateLimiter
rate_limiter = TrustRateLimiter(max_verifications_per_minute=100, max_delegations_per_hour=10)

# Audit logging
from kaizen.trust import SecurityAuditLogger, SecurityEvent, SecurityEventType, SecurityEventSeverity
audit_logger = SecurityAuditLogger(output="security.log")
```

## Component Reference

| Component                                              | Purpose                                    | Location                              |
| ------------------------------------------------------ | ------------------------------------------ | ------------------------------------- |
| `TrustOperations`                                      | Core ops (establish/delegate/verify/audit) | `kaizen.trust.operations`             |
| `TrustedAgent` / `TrustedSupervisorAgent`              | BaseAgent with trust / delegation          | `kaizen.trust.trusted_agent`          |
| `AgentRegistry` / `AgentHealthMonitor`                 | Discovery + health                         | `kaizen.trust.registry`               |
| `SecureChannel` / `MessageSigner` / `MessageVerifier`  | Encrypted messaging                        | `kaizen.trust.messaging`              |
| `TrustAwareOrchestrationRuntime` / `TrustPolicyEngine` | Trust-aware runtime                        | `kaizen.trust.orchestration`          |
| `EnterpriseSystemAgent`                                | Legacy system proxy                        | `kaizen.trust.esa`                    |
| `A2AService`                                           | HTTP API                                   | `kaizen.trust.a2a`                    |
| `PseudoAgent` / `PseudoAgentFactory`                   | Human facade (v0.8.0)                      | `kaizen.trust.pseudo_agent`           |
| `PostgresTrustStore` / `TrustChainCache`               | Storage + caching                          | `kaizen.trust.store` / `.cache`       |
| `CredentialRotationManager` / `TrustRateLimiter`       | Security ops                               | `kaizen.trust.rotation` / `.security` |

## Shim Architecture

After extraction, `kaizen.trust` files are thin shims: `from kailash.trust.chain import *`.
Kaizen adds `PostgresTrustStore` (DataFlow-backed) not in standalone SDK.

| Kaizen Import                                      | Canonical Import                                            |
| -------------------------------------------------- | ----------------------------------------------------------- |
| `from kaizen.trust import TrustOperations`         | `from kailash.trust import TrustOperations`                 |
| `from kaizen.trust.crypto import generate_keypair` | `from kailash.trust.signing.crypto import generate_keypair` |

## When to Use EATP

**Use when**: Enterprise accountability, regulatory compliance (audit trails, provenance), cross-org agent coordination, secure agent-to-agent messaging, capability-based access control, trust delegation with constraints.

**Don't use when**: Simple single-agent apps, internal-only prototypes, no compliance requirements, performance-critical paths without trust needs.

## Best Practices

**Trust**: Establish trust before first agent action. Use specific capability types (ACCESS, EXECUTE, DELEGATE). Set constraints. MUST NOT skip verification in production.

**Delegation**: Time-limited. Least privilege. Record chain for audit. MUST NOT delegate more capabilities than needed.

**Messaging**: Always use SecureChannel for inter-agent comms. Enable replay protection. Verify signatures. MUST NOT send sensitive data unencrypted.

**Production**: Use PostgresTrustStore. Enable TrustChainCache. Configure credential rotation. Enable SecurityAuditLogger. MUST NOT disable trust verification.

## Security Testing

- **127 adversarial tests** (CARE-040): `python -m pytest tests/security/ -v --timeout=120`
- **Node-level trust verification** (CARE-039): High-risk nodes (`BashCommand`, `FileWrite`, `HttpRequest`, `DatabaseQuery`, `CodeExecution`, `SystemCommand`) get full verification (no caching)
- CI: `.github/workflows/trust-tests.yml` (Monday), `.github/workflows/security-tests.yml` (Wednesday)

## Related Skills

- **[kaizen-agent-registry](kaizen-agent-registry.md)** - Distributed agent coordination (non-trust)
- **[kaizen-a2a-protocol](kaizen-a2a-protocol.md)** - Basic A2A capability cards
- **[kaizen-supervisor-worker](kaizen-supervisor-worker.md)** - Supervisor-worker patterns
- **[kaizen-observability-audit](kaizen-observability-audit.md)** - Compliance audit trails
