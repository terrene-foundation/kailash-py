# Parameter Scoping (v0.9.31+)

The runtime's parameter-injection contract for `runtime.execute(workflow, parameters=...)`. Critical for any multi-node workflow author — controls what each node sees vs. what it must NOT see.

## The Contract

When you pass `parameters={...}` to `runtime.execute(workflow, parameters=...)`, the runtime applies node-isolation rules BEFORE injecting into each node's `kwargs`:

```python
parameters = {
    "api_key": "global",     # Global param (visible to ALL nodes)
    "node1": {"value": 10},  # Node-specific (visible ONLY to node1)
    "node2": {"value": 20},  # Node-specific (visible ONLY to node2)
}

runtime.execute(workflow.build(), parameters=parameters)
```

**What `node1` actually receives in its `run(**kwargs)`:\*\*

```python
{
    "api_key": "global",  # Global pass-through
    "value": 10,          # node1's own dict, UNWRAPPED
}
# node1 does NOT see "node2": {"value": 20} — isolation enforced
```

## Scoping Rules

1. **Filtered by node ID** — keys matching a workflow node ID are routed to that node only.
2. **Unwrapped on injection** — node-specific dicts are flattened so the node receives `value=10` directly, not `node1={"value": 10}`.
3. **Global pass-through** — keys NOT matching any node ID are visible to every node (treat as runtime-wide config like `api_key`, `tenant_id`).
4. **Cross-node leakage prevented** — `node2`'s parameters are excluded from `node1`'s kwargs even if both happen to contain the same key.

## Parameter Priority

```
Connection-based  >  Runtime parameters  >  Static (node config)
   (highest)                                    (lowest)
```

A value declared at workflow-build time (static) is overridden by `runtime.execute(parameters=)`, which is overridden by an inbound connection from another node's output.

## Multi-Tenant Isolation Pattern

Parameter scoping is the structural defense for multi-tenant isolation:

```python
parameters = {
    "tenant_a_processor": {"tenant_id": "tenant-a", "data": sensitive_a},
    "tenant_b_processor": {"tenant_id": "tenant-b", "data": sensitive_b},
}
runtime.execute(workflow.build(), parameters=parameters)
# tenant_a_processor receives only tenant_a's data; cross-tenant leak is structurally prevented.
```

## Validation Errors (v0.9.31+)

Parameter validation failures raise `ValueError` (not `RuntimeExecutionError`):

```python
try:
    workflow.build()
except ValueError as e:
    print(f"Missing parameters: {e}")
```

## See Also

- `param-passing-quick.md` — basic three ways to pass parameters
- `runtime-execution.md` — full runtime contract
- `core-workflow-dag.md` — connection-based parameter flow
