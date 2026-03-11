# EATP Integration Testing Guide

Integration testing for Enterprise Agent Trust Protocol (EATP) verifies that
trust components work together correctly in realistic multi-agent scenarios.

## What It Is

Integration tests validate **trust boundaries in action** - they exercise
real cryptographic operations, trust chains, policy enforcement, and
multi-agent coordination without mocking critical security components.

Key principles:
- **Real Cryptography**: Ed25519 signing/verification with actual keys
- **Real Trust Chains**: Capability attestations and constraint propagation
- **Real Policy Evaluation**: Policy engine with composition (AND, OR, NOT)
- **Real Health Monitoring**: Agent heartbeats and status transitions

## Test Categories

### Trust Chain Verification

Tests that verify trust lineage and delegation integrity:

```python
from kaizen.trust import (
    TrustLineageChain,
    TrustExecutionContext,
    CapabilityAttestation,
    CapabilityType,
)

# Create trust chain with capabilities
chain = TrustLineageChain.create_genesis(
    agent_id="supervisor-001",
    authority_type=AuthorityType.ORGANIZATIONAL,
    authority_id="org-001",
    capabilities=["delegate", "analyze", "report"],
)

# Add capability attestation
chain.add_capability_attestation(
    CapabilityAttestation.create(
        capability="process_data",
        capability_type=CapabilityType.WORKFLOW,
        attester_id="authority-001",
        constraints={"max_records": 10000},
    )
)

# Verify chain has expected capabilities
assert chain.has_capability("process_data")
assert not chain.has_capability("admin")  # Not granted
```

### Trust Context Propagation

Tests that verify capability delegation follows security invariants:

```python
# Parent context with capabilities
parent_ctx = TrustExecutionContext.create(
    parent_agent_id="supervisor",
    task_id="main-task",
    delegated_capabilities=["analyze", "report", "read_data"],
    inherited_constraints={"max_records": 5000},
)

# Child cannot gain capabilities parent doesn't have
child_ctx = parent_ctx.create_child(
    agent_id="worker",
    task_id="subtask",
    capabilities=["analyze", "read_data"],  # Subset only
    constraints={"max_records": 2000},  # Can only tighten
)

# Verify security invariants
assert set(child_ctx.capabilities).issubset(set(parent_ctx.capabilities))
assert child_ctx.constraints["max_records"] <= parent_ctx.constraints["max_records"]
```

### Secure Messaging

Tests for cryptographic integrity of agent-to-agent communication:

```python
from kaizen.trust import (
    generate_keypair,
    sign,
    verify_signature,
    SecureMessageEnvelope,
    InMemoryReplayProtection,
)

# Generate keys
private_key, public_key = generate_keypair()

# Sign message
message = b"task delegation request"
signature = sign(message, private_key)

# Verify succeeds with correct key
assert verify_signature(message, signature, public_key)

# Verify fails with wrong key
_, other_public_key = generate_keypair()
assert not verify_signature(message, signature, other_public_key)

# Replay protection
replay = InMemoryReplayProtection()
envelope = SecureMessageEnvelope(payload={"task": "analyze"})

assert replay.is_valid(envelope.nonce)  # First use allowed
assert not replay.is_valid(envelope.nonce)  # Replay blocked
```

### Policy Enforcement

Tests for trust policy evaluation and composition:

```python
from kaizen.trust import TrustPolicy, TrustPolicyEngine

# Create policies
read_policy = TrustPolicy.require_capability("read_data")
write_policy = TrustPolicy.require_capability("write_data")
constraint_policy = TrustPolicy.enforce_constraint(
    constraint_type="max_records",
    constraint_value=5000,
)

# Compose policies
combined = read_policy.and_(write_policy)  # Both required
either = read_policy.or_(write_policy)  # Either sufficient

# Evaluate against context
engine = TrustPolicyEngine(trust_operations=trust_ops)
result = await engine.evaluate_policy(
    policy=combined,
    agent_id="agent-001",
    context=execution_context,
)

assert result.allowed is True  # If context has both capabilities
```

### Health Monitoring

Tests for agent health status tracking:

```python
from kaizen.trust.registry import (
    AgentRegistry,
    AgentHealthMonitor,
    HealthStatus,
)

# Create monitor
monitor = AgentHealthMonitor(
    registry=registry,
    check_interval=60,
    stale_timeout=300,
)

# Check agent health
status = await monitor.check_agent("agent-001")
assert status == HealthStatus.HEALTHY  # Recent heartbeat

# Suspend agent
await registry.update_status("agent-001", AgentStatus.SUSPENDED)
status = await monitor.check_agent("agent-001")
assert status == HealthStatus.SUSPENDED

# Reactivate
await monitor.reactivate_agent("agent-001")
status = await monitor.check_agent("agent-001")
assert status == HealthStatus.HEALTHY
```

### Multi-Agent Workflow

Tests for orchestration across multiple agents with trust verification:

```python
from kaizen.trust.orchestration import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
)

# Create runtime
runtime = TrustAwareOrchestrationRuntime(
    trust_operations=trust_ops,
    agent_registry=registry,
    config=TrustAwareRuntimeConfig(
        verify_before_execution=True,
        enable_policy_engine=True,
    ),
)

await runtime.start()

# Execute multi-agent workflow
status = await runtime.execute_trusted_workflow(
    tasks=["analyze_data", "generate_report", "process_batch"],
    context=supervisor_context,
    agent_selector=lambda task: task_to_agent_mapping[task],
    task_executor=executor,
)

# Verify all tasks completed
assert status.completed_tasks == 3
assert status.failed_tasks == 0

await runtime.shutdown()
```

### Registry-Aware Discovery

Tests for capability-based agent discovery:

```python
from kaizen.trust.orchestration.integration import (
    RegistryAwareRuntime,
    CapabilityBasedSelector,
    HealthAwareSelector,
)

# Create runtime with auto-discovery
runtime = RegistryAwareRuntime(
    trust_operations=trust_ops,
    agent_registry=registry,
    health_monitor=health_monitor,
    config=RegistryAwareRuntimeConfig(
        auto_discover_agents=True,
        health_aware_selection=True,
    ),
)

# Discover agents by capability
agents = await runtime.discover_agents(
    capabilities=["analyze", "process"],
)
assert len(agents) >= 1

# Execute with auto-discovery
status = await runtime.execute_workflow_with_discovery(
    tasks=["task1", "task2"],
    context=context,
    required_capabilities=["analyze"],
)
assert status.completed_tasks == 2
```

## Test Fixtures

### Shared Test Agent

```python
class TestAgent:
    """Test agent with real keys and capabilities."""

    def __init__(self, agent_id: str, capabilities: List[str]):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.private_key, self.public_key = generate_keypair()
        self.executed_tasks = []

    async def execute_task(self, task, context):
        self.executed_tasks.append({
            "task": task,
            "context_id": context.context_id,
        })
        return {"status": "completed", "agent_id": self.agent_id}
```

### Registry Population

```python
@pytest.fixture
async def populated_registry(agent_registry, agents):
    """Registry with registered test agents."""
    for agent in agents:
        await agent_registry.register(
            RegistrationRequest(
                agent_id=agent.agent_id,
                agent_type="worker",
                capabilities=agent.capabilities,
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=agent.public_key,
                verify_trust=False,  # Testing without full chain
            )
        )
        await agent_registry.heartbeat(agent.agent_id)
    return agent_registry
```

### Healthy Agents

```python
@pytest.fixture
async def healthy_agents(registry, health_monitor, agents):
    """Health monitor with all agents healthy."""
    for agent in agents:
        await registry.heartbeat(agent.agent_id)
    return health_monitor
```

## Running Tests

```bash
# Run all trust integration tests
pytest tests/integration/trust/ -v

# Run specific test category
pytest tests/integration/trust/test_trust_chain_verification.py -v
pytest tests/integration/trust/test_policy_enforcement.py -v
pytest tests/integration/trust/test_health_monitoring.py -v
pytest tests/integration/trust/test_multi_agent_workflow.py -v
pytest tests/integration/trust/test_secure_messaging.py -v

# Run with coverage
pytest tests/integration/trust/ --cov=kaizen.trust --cov-report=html
```

## Test Results Summary

```
tests/integration/trust/test_trust_chain_verification.py     10 passed
tests/integration/trust/test_policy_enforcement.py           16 passed
tests/integration/trust/test_health_monitoring.py            14 passed
tests/integration/trust/test_multi_agent_workflow.py         12 passed
tests/integration/trust/test_secure_messaging.py             21 passed

Total: 73 passed
```

## Best Practices

### Test Intent, Not Implementation

Tests should verify the **intent** of security properties:

```python
# Good: Tests security invariant
async def test_child_cannot_gain_capabilities():
    """Child context cannot have capabilities parent doesn't have."""
    parent = TrustExecutionContext.create(
        capabilities=["read_data"],  # Only read
    )

    # Attempt to create child with extra capabilities
    with pytest.raises(ConstraintLooseningError):
        parent.create_child(
            capabilities=["read_data", "write_data"],  # Tries to add write
        )

# Bad: Tests implementation detail
async def test_capabilities_list_length():
    """Child has fewer capabilities than parent."""
    # This tests implementation, not security property
```

### Use Real Cryptography

Never mock cryptographic operations in trust tests:

```python
# Good: Real Ed25519 operations
private_key, public_key = generate_keypair()
signature = sign(message, private_key)
assert verify_signature(message, signature, public_key)

# Bad: Mocked crypto
mock_sign = Mock(return_value="fake-signature")
mock_verify = Mock(return_value=True)  # Always passes!
```

### Test State Transitions

Verify health and status transitions follow expected patterns:

```python
async def test_healthy_to_suspended_to_healthy():
    """Agent status transitions correctly through states."""
    # Start healthy
    await registry.heartbeat(agent_id)
    assert await monitor.check_agent(agent_id) == HealthStatus.HEALTHY

    # Suspend
    await registry.update_status(agent_id, AgentStatus.SUSPENDED)
    assert await monitor.check_agent(agent_id) == HealthStatus.SUSPENDED

    # Reactivate
    await monitor.reactivate_agent(agent_id)
    assert await monitor.check_agent(agent_id) == HealthStatus.HEALTHY
```

### Test Error Cases

Verify security violations are properly caught:

```python
async def test_replay_attack_blocked():
    """Replay protection blocks duplicate nonces."""
    replay = InMemoryReplayProtection()
    envelope = SecureMessageEnvelope(payload={})

    assert replay.is_valid(envelope.nonce)  # First use OK
    assert not replay.is_valid(envelope.nonce)  # Replay blocked

async def test_signature_tampering_detected():
    """Signature verification detects message tampering."""
    signature = sign(b"original", private_key)

    # Tampering detected
    assert not verify_signature(b"tampered", signature, public_key)
```

## Related Documentation

- [Agent Registry](agent_registry.md) - Agent discovery and registration
- [PostgreSQL Store](postgres_store.md) - Persistent trust storage
- [Trust Implementation](IMPLEMENTATION_COMPLETE.md) - Implementation details
