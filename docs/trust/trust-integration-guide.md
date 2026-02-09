# Runtime Trust Integration Guide

This guide explains how to use the EATP trust integration in the Core SDK runtime to track human authorization chains, enforce trust policies, and generate audit trails during workflow execution.

## Why Trust Integration?

AI agent workflows need verifiable accountability. When agent A delegates to agent B which delegates to agent C, every action C takes should be traceable back to the human who authorized it. The trust integration provides:

- **Human origin tracking**: Every workflow execution records which human authorized it
- **Delegation chain propagation**: Agent-to-agent delegation paths are preserved through execution
- **Constraint enforcement**: Constraints from delegation chains are propagated and can only be tightened
- **Trust verification**: Pluggable verification backend (Kaizen or custom) can allow/deny operations
- **Audit trail**: EATP-compliant event log for compliance and forensics

## Quick Start

### No-Trust Mode (Default)

Existing code works unchanged. Trust is disabled by default:

```python
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
# No trust context, no verification, no audit - same as before
```

### Permissive Mode (Log Only)

Log trust-related events without blocking execution:

```python
from kailash.runtime import LocalRuntime
from kailash.runtime.trust import (
    RuntimeTrustContext,
    TrustVerificationMode,
    TrustVerifier,
    TrustVerifierConfig,
)

ctx = RuntimeTrustContext(
    trace_id="trace-abc",
    delegation_chain=["agent-a", "agent-b"],
    verification_mode=TrustVerificationMode.PERMISSIVE,
)

verifier = TrustVerifier(
    config=TrustVerifierConfig(mode="permissive"),
)

runtime = LocalRuntime(
    trust_context=ctx,
    trust_verifier=verifier,
    trust_verification_mode="permissive",
)

results, run_id = runtime.execute(workflow.build())
# Trust context propagated through execution, denied ops logged but allowed
```

### Enforcing Mode (Block Untrusted)

Block workflows that fail trust verification:

```python
runtime = LocalRuntime(
    trust_context=ctx,
    trust_verifier=verifier,
    trust_verification_mode="enforcing",
)

try:
    results, run_id = runtime.execute(workflow.build())
except WorkflowExecutionError:
    print("Trust verification denied execution")
```

## Core Concepts

### RuntimeTrustContext

The central trust data carrier. Immutable updates ensure thread safety:

```python
from kailash.runtime.trust import RuntimeTrustContext, TrustVerificationMode

ctx = RuntimeTrustContext(
    trace_id="trace-123",           # Correlation ID (auto-generated if omitted)
    human_origin=human_origin_obj,  # Who authorized this chain
    delegation_chain=["A", "B"],    # Agent delegation path
    delegation_depth=2,             # Depth in delegation tree
    constraints={"max_tokens": 1000},  # Active constraints
    verification_mode=TrustVerificationMode.ENFORCING,
    workflow_id=None,               # Set by runtime during execution
    node_path=[],                   # Tracks execution path
    metadata={},                    # Extensible metadata
)
```

**Immutable updates**:

```python
# Add node to execution path (creates new context)
node_ctx = ctx.with_node("process_data")
# ctx.node_path is still []
# node_ctx.node_path is ["process_data"]

# Tighten constraints (creates new context)
tighter = ctx.with_constraints({"allowed_tools": ["read"]})
# Original ctx unchanged
```

### TrustVerificationMode

Three modes control runtime behavior:

| Mode         | Behavior                                | Use Case                                  |
| ------------ | --------------------------------------- | ----------------------------------------- |
| `DISABLED`   | No verification, no overhead            | Production without trust, backward compat |
| `PERMISSIVE` | Verify and log, but allow all           | Rollout phase, monitoring                 |
| `ENFORCING`  | Block operations that fail verification | Production with trust                     |

### TrustVerifier

Pluggable verification backend. Works standalone or with Kaizen:

```python
from kailash.runtime.trust import TrustVerifier, TrustVerifierConfig

# Standalone (no Kaizen dependency)
verifier = TrustVerifier(
    config=TrustVerifierConfig(
        mode="enforcing",
        cache_ttl_seconds=60,
        high_risk_nodes=["BashCommand", "FileWrite"],
    ),
)

# With Kaizen backend
from kaizen.trust.operations import TrustOperations
verifier = TrustVerifier(
    kaizen_backend=trust_operations,
    config=TrustVerifierConfig(mode="enforcing"),
)
```

**Verification methods**:

```python
result = await verifier.verify_workflow_access(
    workflow_id="my-workflow",
    agent_id="agent-123",
    trust_context=ctx,
)

result = await verifier.verify_node_access(
    node_id="node-1",
    node_type="BashCommand",  # High-risk gets FULL verification
    agent_id="agent-123",
    trust_context=ctx,
)

result = await verifier.verify_resource_access(
    resource="/data/customers.csv",
    action="read",
    agent_id="agent-123",
    trust_context=ctx,
)
```

### MockTrustVerifier (Testing)

For testing without Kaizen:

```python
from kailash.runtime.trust import MockTrustVerifier

verifier = MockTrustVerifier(
    default_allow=True,
    denied_agents=["blocked-agent"],
    denied_nodes=["BashCommand"],
)

# agent-123 can run workflows
result = await verifier.verify_workflow_access("wf", "agent-123")
assert result.allowed

# blocked-agent cannot
result = await verifier.verify_workflow_access("wf", "blocked-agent")
assert not result.allowed
```

## Context Propagation

Trust context propagates through execution via Python `ContextVar`:

```python
from kailash.runtime.trust import (
    RuntimeTrustContext,
    runtime_trust_context,
    get_runtime_trust_context,
)

# Context manager for scoped propagation
ctx = RuntimeTrustContext(trace_id="trace-123")
with runtime_trust_context(ctx):
    # Any code in this block sees the trust context
    current = get_runtime_trust_context()
    assert current.trace_id == "trace-123"

# Outside the block, context is cleared
assert get_runtime_trust_context() is None
```

The runtime automatically:

1. Sets the trust context before workflow execution
2. Updates it with workflow_id
3. Resets it after execution (even on exceptions)

### Async Safety

`ContextVar` propagates correctly across `async/await` boundaries. Both `LocalRuntime.execute()` and `AsyncLocalRuntime.execute_workflow_async()` handle this.

## Audit Trail

The `RuntimeAuditGenerator` creates EATP-compliant audit events:

```python
from kailash.runtime.trust import RuntimeAuditGenerator, AuditEventType

# Basic usage
generator = RuntimeAuditGenerator(enabled=True)

# Record events
await generator.workflow_started("run-1", "my-workflow", trust_ctx)
await generator.node_executed("run-1", "node-1", "HttpRequest", 150, trust_ctx)
await generator.workflow_completed("run-1", 500, trust_ctx)

# Query events
all_events = generator.get_events()
node_events = generator.get_events_by_type(AuditEventType.NODE_END)
trace_events = generator.get_events_by_trace("trace-123")
```

### Event Types

| Event Type           | When Recorded                   |
| -------------------- | ------------------------------- |
| `WORKFLOW_START`     | Workflow execution begins       |
| `WORKFLOW_END`       | Workflow completes successfully |
| `WORKFLOW_ERROR`     | Workflow fails with error       |
| `NODE_START`         | Node execution begins           |
| `NODE_END`           | Node completes successfully     |
| `NODE_ERROR`         | Node fails with error           |
| `TRUST_VERIFICATION` | Trust check passes              |
| `TRUST_DENIED`       | Trust check denies operation    |
| `RESOURCE_ACCESS`    | Resource access attempted       |
| `DELEGATION_USED`    | Delegation chain extended       |

### Kaizen AuditStore Bridge

Events can be persisted to Kaizen's AuditStore:

```python
from kaizen.trust.audit_store import PostgresAuditStore

audit_store = PostgresAuditStore(db_url="...")
generator = RuntimeAuditGenerator(
    audit_store=audit_store,
    enabled=True,
)
# Events automatically persisted to Kaizen store
```

### Audit Safety

Audit failures never break workflow execution. All audit operations are wrapped in `try/except` and log errors without raising.

## Runtime Configuration

### LocalRuntime

```python
runtime = LocalRuntime(
    # Trust context (optional)
    trust_context=ctx,
    trust_verifier=verifier,
    trust_verification_mode="enforcing",  # "disabled", "permissive", "enforcing"

    # Audit (optional)
    audit_generator=generator,
    enable_audit=True,
    audit_log_to_stdout=False,
)
```

### AsyncLocalRuntime

```python
runtime = AsyncLocalRuntime(
    trust_context=ctx,
    trust_verifier=verifier,
    trust_verification_mode="enforcing",
    audit_generator=generator,
)

results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={},
)
```

## Kaizen Bridge

When using Kaizen's trust system, bridge contexts:

```python
from kaizen.core.context import ExecutionContext
from kailash.runtime.trust import RuntimeTrustContext

# Bridge Kaizen context to Core SDK
kaizen_ctx = ExecutionContext(...)
runtime_ctx = RuntimeTrustContext.from_kaizen_context(kaizen_ctx)
# Automatically sets verification_mode=ENFORCING

# Use with runtime
runtime = LocalRuntime(trust_context=runtime_ctx)
```

## Node-Level Trust Verification (CARE-039)

Trust verification is enforced at the individual node level, not just at workflow entry. Every node execution call goes through `_verify_node_trust()` before the node runs.

**Execution paths covered**:

| Runtime             | Method                              | Trust Gate                      |
| ------------------- | ----------------------------------- | ------------------------------- |
| `LocalRuntime`      | `_execute_workflow_async()`         | Before node execution           |
| `AsyncLocalRuntime` | `_execute_node_async()`             | Before async node execution     |
| `AsyncLocalRuntime` | `_execute_sync_node_async()`        | Before sync-in-thread execution |
| `AsyncLocalRuntime` | `_execute_sync_workflow_internal()` | Before sync fallback execution  |

**High-risk node types** receive FULL verification (no caching): `BashCommand`, `FileWrite`, `HttpRequest`, `DatabaseQuery`, `CodeExecution`, `SystemCommand`.

**Behavior by mode**:

- `DISABLED`: `_verify_node_trust()` returns `True` immediately. Zero overhead.
- `PERMISSIVE`: Denied nodes log a warning but continue execution.
- `ENFORCING`: Denied nodes raise `WorkflowExecutionError` and halt.

```python
# Trust denial prevents node execution in ENFORCING mode
runtime = LocalRuntime(
    trust_context=ctx,
    trust_verifier=MockTrustVerifier(denied_nodes=["BashCommand"]),
    trust_verification_mode="enforcing",
)

try:
    results, run_id = runtime.execute(workflow_with_bash.build())
except WorkflowExecutionError as e:
    # Node was blocked before execution
    print(f"Blocked: {e}")
```

## Architecture

```
RuntimeTrustContext (context.py)      TrustVerifier (verifier.py)
   |                                      |
   |  [ContextVar propagation]           |  [verify_workflow/node/resource]
   v                                      v
BaseRuntime._get_effective_trust_context()
BaseRuntime._verify_workflow_trust()    <-- workflow-level gate
BaseRuntime._verify_node_trust()        <-- node-level gate (CARE-039)
   |
   |--- LocalRuntime.execute()           ---> audit events
   |--- AsyncLocalRuntime.execute_workflow_async() ---> audit events
   |
   v
RuntimeAuditGenerator (audit.py)
   |
   |--- In-memory events list
   |--- Optional Kaizen AuditStore bridge
```

## Testing

Use `MockTrustVerifier` for tests:

```python
from kailash.runtime.trust import (
    MockTrustVerifier,
    RuntimeTrustContext,
    TrustVerificationMode,
)

def test_workflow_with_trust():
    verifier = MockTrustVerifier(
        default_allow=True,
        denied_agents=["bad-agent"],
    )

    ctx = RuntimeTrustContext(
        delegation_chain=["good-agent"],
        verification_mode=TrustVerificationMode.ENFORCING,
    )

    runtime = LocalRuntime(
        trust_context=ctx,
        trust_verifier=verifier,
        trust_verification_mode="enforcing",
    )

    results, run_id = runtime.execute(workflow.build())
    assert results is not None
```
