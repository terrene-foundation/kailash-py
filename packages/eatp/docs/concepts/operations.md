# Four Operations

EATP defines exactly four operations for managing trust.

## ESTABLISH

Creates initial trust for an agent by generating a Genesis Record and binding capabilities.

```python
chain = await ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[
        CapabilityRequest(
            capability="analyze_data",
            capability_type=CapabilityType.ACTION,
        )
    ],
)
```

## DELEGATE

Transfers trust from one agent to another with constraint tightening.

**Key invariant**: Delegations can only **tighten** constraints, never loosen them. A child agent can never have more permissions than its parent.

```python
await ops.delegate(
    delegator_id="agent-001",
    delegatee_id="agent-002",
    task_id="task-analysis",
    capabilities=["analyze_data"],
    constraints=["read_only", "max_100_records"],
)
```

## VERIFY

Validates an agent's trust chain before allowing an action. Returns a `VerificationResult` with a `valid` boolean.

Three verification levels:

| Level | Checks | Latency |
|-------|--------|---------|
| QUICK | Hash + expiration | ~1ms |
| STANDARD | + Capability match, constraints | ~5ms |
| FULL | + Signature verification | ~50ms |

```python
result = await ops.verify(agent_id="agent-001", action="analyze_data")
if result.valid:
    # Proceed with action
    pass
```

## AUDIT

Records an agent action in the immutable audit trail.

```python
await ops.audit(
    agent_id="agent-001",
    action="analyze_data",
    resource="transactions_table",
)
```

Audit anchors are hash-linked, creating a tamper-evident chain. Each anchor includes the trust chain hash at the time of action, enabling post-hoc verification.
