# Workflow Parameter Injection Guide

## Overview

Starting with v0.6.2, the Kailash SDK supports automatic injection of workflow-level parameters into nodes. This feature dramatically simplifies parameter passing in workflows by allowing you to pass parameters directly to `runtime.execute()` without manually mapping them to each node.

## Key Benefits

1. **Simplified API**: Pass parameters as a flat dictionary instead of nested node-specific format
2. **Automatic Mapping**: Parameters are intelligently mapped to nodes based on names and aliases
3. **Backward Compatible**: Existing node-specific parameter format still works
4. **Smart Resolution**: Multiple strategies for parameter mapping ensure flexibility

## Basic Usage

### Before (Node-Specific Format)
```python
# Old way - requires knowledge of node IDs
results, _ = runtime.execute(workflow, parameters={
    "validator_node": {
        "email": "user@example.com",
        "password": "secure123"
    },
    "creator_node": {
        "email": "user@example.com",
        "password": "secure123",
        "tenant_id": "prod"
    }
})
```

### After (Workflow-Level Format)
```python
# New way - simple flat dictionary
results, _ = runtime.execute(workflow, parameters={
    "email": "user@example.com",
    "password": "secure123",
    "tenant_id": "prod"
})
```

## Parameter Mapping Strategies

The parameter injector uses multiple strategies to map workflow parameters to nodes:

### 1. Direct Name Matching
Parameters are matched to node parameters with the same name:

```python
# Workflow parameter
{"email": "user@example.com"}

# Matches node parameter
NodeParameter(name="email", type=str)
```

### 2. Workflow Alias
Use `workflow_alias` to define preferred parameter names:

```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "user_email": NodeParameter(
                name="user_email",
                type=str,
                workflow_alias="email"  # Maps workflow "email" to node "user_email"
            )
        }

# Usage
runtime.execute(workflow, parameters={"email": "test@example.com"})
```

### 3. Auto-Map Alternatives
Define alternative names that can be used:

```python
NodeParameter(
    name="input_data",
    type=str,
    auto_map_from=["data", "input", "payload"]  # Any of these names work
)
```

### 4. Primary Parameter
Mark a parameter to receive unmapped values:

```python
NodeParameter(
    name="config",
    type=dict,
    auto_map_primary=True  # Gets any unmapped parameters
)
```

### 5. Explicit Mappings (WorkflowBuilder)
Define explicit mappings when building workflows:

```python
builder = WorkflowBuilder()
builder.add_node(ValidatorNode(), "validator")
builder.add_workflow_inputs("validator", {
    "user_email": "email",      # Map workflow "user_email" to node "email"
    "user_password": "password"  # Map workflow "user_password" to node "password"
})
```

## Parameter Precedence

When multiple parameter sources exist, they are applied in this order (highest to lowest):

1. **Runtime node-specific parameters** - Explicit overrides
2. **Workflow-level parameters** - Automatic injection
3. **Node configuration** - Default values

Example:
```python
# Node configuration (lowest priority)
workflow.add_node("MyNode", "processor", {}))

# Workflow-level parameter (medium priority)
runtime.execute(workflow, parameters={
    "default_value": "workflow"
})

# Runtime override (highest priority)
runtime.execute(workflow, parameters={
    "processor": {"default_value": "override"}  # This wins
})
```

## Real-World Examples

### User Registration Workflow

```python
from kailash.workflow.builder import WorkflowBuilder, WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

# Create workflow
builder = WorkflowBuilder()

# Validation node
def validate_user(email, password):
    return {
        "valid": "@" in email and len(password) >= 8,
        "email": email
    }

# User creation node
def create_user(email, password, tenant_id="default"):
    return {
        "user_id": f"user_{email.split('@')[0]}",
        "email": email,
        "tenant_id": tenant_id
    }

# Build workflow
builder.add_node(PythonCodeNode.from_function(validate_user), "validator")
builder.add_node(PythonCodeNode.from_function(create_user), "creator")
builder.connect("validator", "creator", {"result.email": "email"})

# Map workflow inputs
builder.add_workflow_inputs("validator", {
    "user_email": "email",
    "user_password": "password"
})
builder.add_workflow_inputs("creator", {
    "user_password": "password",
    "tenant": "tenant_id"
})

workflow = builder.build()

# Execute with simple parameters
runtime = LocalRuntime()
results, _ = runtime.execute(workflow, parameters={
    "user_email": "john@example.com",
    "user_password": "secure123",
    "tenant": "production"
})
```

### Data Processing Pipeline

```python
# Define nodes with parameter aliases
class DataLoader(Node):
    def get_parameters(self):
        return {
            "source_path": NodeParameter(
                name="source_path",
                type=str,
                workflow_alias="input_file",  # Accept "input_file" as alias
                description="Path to input data"
            )
        }

    def run(self, source_path):
        # Load data...
        return {"data": loaded_data}

class DataProcessor(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                auto_map_primary=True,  # Receives any extra parameters
                default={}
            )
        }

    def run(self, data, config):
        # Process with config...
        return {"processed": result}

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("loader", DataLoader())
workflow.add_node("processor", DataProcessor())
workflow.add_connection("loader", "result", "processor", "input")

# Execute with mixed parameters
runtime = LocalRuntime()
results, _ = runtime.execute(workflow, parameters={
    "input_file": "/path/to/data.csv",  # Maps to loader via alias
    "batch_size": 100,                   # Goes to processor config
    "parallel": True                     # Goes to processor config
})
```

## Migration Guide

### Converting Existing Workflows

1. **Identify node parameter names**:
   ```python
   # Check what parameters each node expects
   for node_id, node in workflow._node_instances.items():
       print(f"{node_id}: {list(node.get_parameters().keys())}")
   ```

2. **Update parameter passing**:
   ```python
   # Old way
   params = {
       "node1": {"param1": "value1"},
       "node2": {"param1": "value1", "param2": "value2"}
   }

   # New way (if params have unique names)
   params = {
       "param1": "value1",
       "param2": "value2"
   }
   ```

3. **Add aliases for conflicts**:
   ```python
   # If multiple nodes use "data" parameter
   class Node1(Node):
       def get_parameters(self):
           return {
               "data": NodeParameter(
                   name="data",
                   workflow_alias="input_data"  # Unique alias
               )
           }

   class Node2(Node):
       def get_parameters(self):
           return {
               "data": NodeParameter(
                   name="data",
                   workflow_alias="output_data"  # Different alias
               )
           }
   ```

## Best Practices

1. **Use descriptive parameter names**: Avoid generic names like "data" or "input"
2. **Define workflow aliases**: Make parameters more intuitive for workflow users
3. **Document parameters**: Use the description field in NodeParameter
4. **Validate early**: The runtime validates all parameters before execution
5. **Use auto_map_primary sparingly**: Only for truly generic catch-all parameters

## Troubleshooting

### Missing Required Parameter
```
WorkflowValidationError: Node 'processor' missing required inputs: ['config']
```
**Solution**: Ensure the parameter name matches or add a workflow_alias

### Parameter Not Reaching Node
Enable debug mode to see parameter mapping:
```python
runtime = LocalRuntime(debug=True)
# Check logs for "Mapped workflow parameter" messages
```

### Unexpected Parameter Values
Check precedence - runtime overrides might be overwriting your workflow parameters

## Advanced Features

### Conditional Parameter Injection
Parameters are only injected into nodes that declare them:

```python
# Only nodes with "debug" parameter receive this
runtime.execute(workflow, parameters={"debug": True})
```

### Multi-Node Parameter Broadcasting
The same parameter can be sent to multiple nodes:

```python
# Both validator and creator receive tenant_id
runtime.execute(workflow, parameters={
    "tenant_id": "prod"  # Goes to all nodes that have this parameter
})
```

### Dynamic Parameter Discovery
The parameter injector examines node parameters at runtime, so dynamically created nodes work correctly.

## Related Documentation

- [Workflow Builder Guide](08-async-workflow-builder.md)
- [Node Development Guide](06-custom-nodes.md)
- [Unified Async Runtime Guide](09-unified-async-runtime-guide.md)
