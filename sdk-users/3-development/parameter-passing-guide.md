# Parameter Passing Guide

Complete guide to providing parameters to nodes in Kailash SDK workflows.

## What This Is

Parameters control how nodes behave in your workflows. The Kailash SDK provides three methods to pass parameters to nodes, each suited for different scenarios. Parameters can be static (known at build time), dynamic (from other nodes), or runtime-specific (determined during execution).

## The Three Methods

### Method 1: Node Configuration (Static)

Provide parameters directly in node configuration when values are known at workflow design time.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# All parameters in node configuration
workflow.add_node("EmailNode", "send_email", {
    "to": "user@example.com",
    "subject": "Welcome",
    "template": "onboarding",
    "retry_count": 3
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**When to use:**
- Configuration values
- Fixed business rules
- Default settings
- Test fixtures

### Method 2: Workflow Connections (Dynamic)

Pass parameters from one node's output to another node's input using workflow connections.

```python
workflow = WorkflowBuilder()

# Node 1: Fetch user data
workflow.add_node("DatabaseQueryNode", "get_user", {
    "query": "SELECT * FROM users WHERE id = ?",
    "params": [123]
})

# Node 2: Extract preferences
workflow.add_node("PythonCodeNode", "extract_prefs", {
    "code": """
channel = data['notification_channel']
frequency = data['email_frequency']
result = {'channel': channel, 'frequency': frequency}
"""
})

# Node 3: Send notification (parameters from connections)
workflow.add_node("NotificationNode", "notify", {
    "template": "weekly_digest"  # Static parameter
    # 'channel' and 'frequency' come from connections
})

# Connect data flow (4-parameter syntax)
workflow.add_connection("get_user", "result", "extract_prefs", "data")
workflow.add_connection("extract_prefs", "channel", "notify", "channel")
workflow.add_connection("extract_prefs", "frequency", "notify", "frequency")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**When to use:**
- Data transformation pipelines
- Conditional logic based on previous results
- Database-driven configurations
- Multi-step processing

### Method 3: Runtime Parameters (Dynamic Override)

Provide or override parameters at execution time using the runtime's `parameters` argument.

```python
workflow = WorkflowBuilder()

# Define nodes without all parameters
workflow.add_node("ReportGeneratorNode", "generate", {
    "template": "monthly_report"
    # 'start_date' and 'end_date' from runtime
})

workflow.add_node("EmailNode", "send_report", {
    "subject": "Monthly Report"
    # 'recipients' from runtime
})

workflow.add_connection("generate", "report", "send_report", "attachment")

# Provide parameters at execution
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "generate": {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31"
    },
    "send_report": {
        "recipients": ["manager@company.com", "team@company.com"]
    }
})
```

**When to use:**
- User input required at runtime
- Date/time sensitive operations
- Environment-specific overrides
- Testing with different parameters
- Multi-tenant operations

## Parameter Scoping (How It Works Internally)

When you pass parameters to runtime execution, **node-specific parameters are automatically unwrapped** before being passed to nodes.

```python
# What you pass to runtime:
parameters = {
    "api_key": "global-key",      # Global param (goes to all nodes)
    "node1": {"value": 10},        # Node-specific param for node1
    "node2": {"value": 20}         # Node-specific param for node2
}

runtime.execute(workflow.build(), parameters=parameters)

# What node1 receives (automatically unwrapped):
{
    "api_key": "global-key",       # Global param included
    "value": 10                     # Unwrapped from {"node1": {"value": 10}}
}
# node1 does NOT receive node2's parameters (isolated)

# What node2 receives (automatically unwrapped):
{
    "api_key": "global-key",       # Global param included
    "value": 20                     # Unwrapped from {"node2": {"value": 20}}
}
# node2 does NOT receive node1's parameters (isolated)
```

**Key behaviors:**
- **Node-specific params**: Nested under node ID are unwrapped automatically
- **Global params**: Top-level params (not node IDs) go to all nodes
- **Parameter isolation**: Each node only receives its own params + globals
- **No parameter leakage**: Node1's params never reach Node2

## Combining Methods

Use all three methods together for maximum flexibility:

```python
workflow = WorkflowBuilder()

# Method 1: Static configuration
workflow.add_node("DataValidatorNode", "validate", {
    "rules": "strict",  # Static config
    "log_errors": True
})

# Method 2: Connection from previous node
workflow.add_node("DataTransformerNode", "transform", {
    "format": "json"  # Static
    # 'data' comes from connection
})

workflow.add_connection("validate", "valid_data", "transform", "data")

# Method 3: Runtime override
results, run_id = runtime.execute(workflow.build(), parameters={
    "validate": {
        "rules": "relaxed"  # Override static "strict" value
    }
})
```

## Common Errors and Solutions

### Error: Missing Required Parameters

```python
# This will fail at build time
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # Missing required 'email' parameter!
})
# Error: Node 'create' missing required inputs: ['email']
```

**Solution:** Provide via one of the three methods:

```python
# Option 1: Add to configuration
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# Option 2: Connect from another node
workflow.add_connection("form_data", "email", "create", "email")

# Option 3: Provide at runtime
runtime.execute(workflow.build(), parameters={
    "create": {"email": "alice@example.com"}
})
```

### Error: Parameter Type Mismatch

```python
# Wrong parameter type
workflow.add_node("BatchProcessorNode", "process", {
    "batch_size": "100"  # String instead of integer!
})
```

**Solution:** Ensure correct types:

```python
# Correct type
workflow.add_node("BatchProcessorNode", "process", {
    "batch_size": 100  # Integer
})
```

## Best Practices

### 1. Declare All Parameters in Custom Nodes

```python
from kailash.nodes.base import Node, NodeParameter

class MyCustomNode(Node):
    def get_parameters(self):
        return {
            "input_file": NodeParameter(type=str, required=True),
            "output_format": NodeParameter(type=str, required=False, default="json"),
            "batch_size": NodeParameter(type=int, required=False, default=100)
        }
```

### 2. Use Descriptive Parameter Names

```python
# Bad
workflow.add_node("ProcessorNode", "proc", {"d": data, "f": "json"})

# Good
workflow.add_node("ProcessorNode", "processor", {
    "input_data": data,
    "output_format": "json"
})
```

### 3. Document Dynamic Parameters

```python
# Add comments explaining parameter sources
workflow.add_node("NotificationNode", "notify", {
    "template": "order_confirmation"
    # 'customer_email' comes from 'get_order' node via connection
    # 'order_details' comes from 'process_order' node via connection
})
```

### 4. Validate Early with Build

```python
# Always build before execute to catch parameter errors
try:
    built_workflow = workflow.build()  # Validates all parameters
except ValueError as e:  # Changed from RuntimeExecutionError
    print(f"Parameter error: {e}")
    # Fix missing parameters before proceeding
```

## Security Benefits

Strict parameter validation provides:

1. **No Parameter Injection**: Nodes only receive declared parameters
2. **Type Safety**: Parameters validated against declared types
3. **Explicit Data Flow**: All data movement is traceable
4. **Build-Time Validation**: Errors caught before execution
5. **Parameter Isolation**: Prevents cross-node parameter leakage

## Related Documentation

- [Connection Patterns](../2-core-concepts/cheatsheet/005-connection-patterns.md) - Data flow between nodes
- [Node Development Guide](./05-custom-development.md) - Creating nodes with proper parameters
- [Common Mistakes](../2-core-concepts/validation/common-mistakes.md) - Parameter-related errors

## Summary

**Every required parameter must come from one of three methods:**
1. **Static** → Node configuration
2. **Dynamic from nodes** → Workflow connections
3. **Dynamic from runtime** → Execution parameters

The SDK validates this at build time, ensuring your workflows are correct before they run. Parameter scoping ensures nodes only receive their own parameters plus any global parameters, preventing security issues and making workflows more reliable.
