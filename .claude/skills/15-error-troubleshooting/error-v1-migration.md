---
description: Common errors when migrating from Kailash SDK v0.x to v1.0.0
---

# v1.0 Migration Errors

## Legacy Fluent API Removed

**Error**: `WorkflowValidationError: Legacy fluent API (add_node('node_id', NodeClass, ...)) was removed in v1.0.0.`

**Cause**: Using the old `add_node("node_id", NodeClass, param=value)` pattern.

**Fix**: Swap the arguments to use the current API:

```python
# OLD (v0.x) - no longer works
workflow.add_node("my_node", HTTPRequestNode, url="https://api.com")

# NEW (v1.0+)
workflow.add_node("HTTPRequestNode", "my_node", {"url": "https://api.com"})
```

## cycle=True Removed from connect()

**Error**: `WorkflowValidationError: Direct cycle=True in connect() was removed in v1.0.0.`

**Cause**: Using `workflow.connect(a, b, cycle=True)` directly.

**Fix**: Use the CycleBuilder API:

```python
# OLD (v0.x) - no longer works
workflow.connect("node_a", "node_b", cycle=True, max_iterations=10)

# NEW (v1.0+)
workflow.create_cycle("my_cycle") \
    .connect("node_a", "node_b") \
    .max_iterations(10) \
    .converge_when("error < 0.01") \
    .build()
```

## WorkflowGraph Deprecation Warning

**Warning**: `DeprecationWarning: WorkflowGraph is deprecated and will be removed in v2.0.0. Use Workflow instead.`

**Fix**: Replace `WorkflowGraph` with `Workflow`:

```python
# OLD
from kailash import WorkflowGraph

# NEW
from kailash import Workflow
```

## Legacy Middleware Import Warning

**Warning**: `DeprecationWarning: AgentUIMiddleware is no longer exported from kailash top-level.`

**Fix**: Import from `kailash.middleware` instead:

```python
# OLD
from kailash import AgentUIMiddleware

# NEW
from kailash.middleware import AgentUIMiddleware
```

## Removed JWT Methods

**Error**: `AttributeError: 'JWTAuthManager' object has no attribute 'generate_token'`

**Fix**: Use the renamed methods:

```python
# OLD → NEW
auth.generate_token(user_id)         → auth.create_access_token(user_id)
auth.verify_and_decode_token(token)  → auth.verify_token(token)
auth.blacklist_token(token)          → auth.revoke_token(token)
auth.generate_refresh_token(user_id) → auth.create_refresh_token(user_id)
```

## HTTPClientNode Removed

**Error**: `AttributeError: module 'kailash.nodes.api' has no attribute 'HTTPClientNode'`

**Fix**: Use `HTTPRequestNode` instead:

```python
# OLD
from kailash.nodes.api import HTTPClientNode

# NEW
from kailash.nodes.api import HTTPRequestNode
```

## execute_workflow() Removed from AgentUIMiddleware

**Error**: `AttributeError: 'AgentUIMiddleware' object has no attribute 'execute_workflow'`

**Fix**: Use `execute()` instead:

```python
# OLD
await middleware.execute_workflow(session_id, workflow_id, inputs)

# NEW
await middleware.execute(session_id, workflow_id, inputs)
```
