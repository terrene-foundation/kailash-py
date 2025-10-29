# Parameter Passing Comprehensive Guide

Complete enterprise guide for parameter passing in Kailash SDK workflows.

## What This Is

This is the comprehensive reference for parameter passing in Kailash SDK. It covers the three methods of parameter passing, parameter scoping internals, security patterns, and enterprise best practices. For quick reference, see [Parameter Passing Guide](../3-development/parameter-passing-guide.md).

## The Three Methods

### Method 1: Node Configuration

**Best for:** Static values, test fixtures, configuration settings

Parameters provided directly in node configuration are the most reliable method:

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data.csv",
    "delimiter": ",",
    "has_header": True
})
```

### Method 2: Workflow Connections

**Best for:** Dynamic data flow, pipelines, transformations

Parameters flow from one node's output to another node's input:

```python
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'count': len(data)}"
})

# 4-parameter syntax: from_node, output_key, to_node, input_key
workflow.add_connection("reader", "data", "processor", "data")
```

### Method 3: Runtime Parameters

**Best for:** User input, environment overrides, dynamic values

Parameters provided at execution time:

```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        "reader": {"file_path": "custom.csv"},
        "processor": {"batch_size": 100}
    }
)
```

## Parameter Scoping (How It Works)

When you pass parameters to `runtime.execute()`, the runtime automatically handles parameter scoping:

### Node-Specific Parameters (Unwrapped)

```python
# What you pass to runtime:
parameters = {
    "api_key": "global-key",      # Global param
    "node1": {"value": 10},        # Node-specific for node1
    "node2": {"value": 20}         # Node-specific for node2
}

runtime.execute(workflow.build(), parameters=parameters)

# What node1 receives (unwrapped automatically):
{
    "api_key": "global-key",       # Global param included
    "value": 10                     # Unwrapped from nested dict
}

# What node2 receives (unwrapped automatically):
{
    "api_key": "global-key",       # Global param included
    "value": 20                     # Unwrapped from nested dict
}
```

### Parameter Scoping Rules

**Implementation** (src/kailash/runtime/local.py:1621-1640):

1. **Parameters filtered by node ID**: Only relevant params passed to each node
2. **Node-specific params unwrapped**: Contents extracted from nested dict
3. **Global params included**: Top-level non-node-ID keys go to all nodes
4. **Other nodes' params excluded**: Prevents parameter leakage

```python
# Example of parameter isolation
parameters = {
    "db_connection": "postgresql://...",  # Global - all nodes get this
    "reader": {                           # Only reader node gets these
        "table": "users",
        "limit": 100
    },
    "writer": {                           # Only writer node gets these
        "table": "processed_users",
        "batch_size": 50
    }
}

# reader node receives:
{
    "db_connection": "postgresql://...",  # Global param
    "table": "users",                      # Unwrapped from reader dict
    "limit": 100                           # Unwrapped from reader dict
}
# Does NOT receive: writer's table or batch_size

# writer node receives:
{
    "db_connection": "postgresql://...",  # Global param
    "table": "processed_users",            # Unwrapped from writer dict
    "batch_size": 50                       # Unwrapped from writer dict
}
# Does NOT receive: reader's table or limit
```

## Parameter Naming (Core SDK v0.10.3+)

### Using "metadata" as a Parameter Name

You can use `metadata` as a parameter name in custom nodes. This is commonly needed for database models, monitoring systems, and data pipelines that track metadata.

**What "metadata" means:**
- **User metadata parameter** - Your dict parameter named "metadata"
- **Node internal metadata** - The node's NodeMetadata object (name, description, version)

Both types work independently without conflict.

**Example:**

```python
from kailash.nodes.base import Node, NodeParameter
from typing import Dict, Any, Optional

class ArticleProcessorNode(Node):
    """Node that processes articles with metadata."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "title": NodeParameter(type=str, required=True),
            "content": NodeParameter(type=str, required=True),
            # ✅ You can use "metadata" as a parameter name
            "metadata": NodeParameter(
                type=dict,
                required=False,
                default=None,
                description="Article metadata (author, tags, timestamps)"
            )
        }

    def run(self, title: str, content: str, metadata: Optional[dict] = None, **kwargs) -> Dict[str, Any]:
        # Access user's metadata parameter
        article_metadata = metadata or {}

        # Access node's internal metadata (different object)
        node_name = self.metadata.name
        node_version = self.metadata.version

        return {
            "article": {
                "title": title,
                "content": content,
                "metadata": article_metadata  # User parameter
            },
            "processing_info": {
                "node_name": node_name,      # Internal NodeMetadata
                "node_version": node_version  # Internal NodeMetadata
            }
        }
```

**In workflows:**

```python
workflow = WorkflowBuilder()

workflow.add_node("ArticleProcessorNode", "processor", {
    "title": "Introduction to Workflows",
    "content": "...",
    "metadata": {
        "author": "Alice Smith",
        "tags": ["workflows", "tutorial"],
        "created_at": "2025-01-01"
    }
})
```

### Reserved Parameter Names

Only one parameter name is reserved:

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "data": NodeParameter(...),      # ✅ Allowed
        "metadata": NodeParameter(...),  # ✅ Allowed (v0.10.3+)
        "config": NodeParameter(...),    # ✅ Allowed
        "value": NodeParameter(...),     # ✅ Allowed
        "_node_id": NodeParameter(...)   # ❌ Reserved - do not use
    }
```

## Enterprise Patterns

### Pattern 1: Explicit Parameter Declaration

Custom nodes must declare all expected parameters:

```python
from kailash.nodes.base import Node, NodeParameter
from typing import Dict, Any

class DataProcessorNode(Node):
    """Node with explicit parameter declaration."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "input_file": NodeParameter(
                type=str,
                required=True,
                description="Path to input file"
            ),
            "output_format": NodeParameter(
                type=str,
                required=False,
                default="json",
                description="Output format (json, csv, xml)"
            ),
            "batch_size": NodeParameter(
                type=int,
                required=False,
                default=100,
                description="Processing batch size"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Required parameters guaranteed to exist
        input_file = kwargs["input_file"]

        # Optional parameters with defaults
        output_format = kwargs.get("output_format", "json")
        batch_size = kwargs.get("batch_size", 100)

        return {"processed": True}
```

### Pattern 2: Parameter Validation

Validate business logic requirements:

```python
class UserCreateNode(Node):
    def get_parameters(self):
        return {
            "name": NodeParameter(type=str, required=True),
            "email": NodeParameter(type=str, required=True),
            "role": NodeParameter(type=str, required=False, default="user")
        }

    def run(self, **kwargs):
        name = kwargs["name"]
        email = kwargs["email"]
        role = kwargs.get("role", "user")

        # Business logic validation
        if not email or "@" not in email:
            raise ValueError("Invalid email address")

        if role not in ["user", "admin", "moderator"]:
            raise ValueError(f"Invalid role: {role}")

        return {"user_id": create_user(name, email, role)}
```

### Pattern 3: Multi-Tenant Parameter Isolation

Ensure tenant data isolation using parameter scoping:

```python
# Workflow with tenant isolation
workflow = WorkflowBuilder()

workflow.add_node("TenantDataFetcher", "fetch_tenant_a", {
    "tenant_id": "tenant-a"
})

workflow.add_node("TenantDataFetcher", "fetch_tenant_b", {
    "tenant_id": "tenant-b"
})

# Each node only receives its own tenant_id
# No parameter leakage between tenants
```

## Security Considerations

### SQL Injection Prevention

Context-aware validation for SQL-related parameters:

```python
# Safe: User content fields (allow special characters)
user_content_fields = {
    'username', 'first_name', 'last_name', 'email',
    'display_name', 'bio', 'address'
}

# Dangerous: SQL construction fields (strict validation)
sql_construction_fields = {
    'query', 'sql', 'where', 'filter', 'order_by',
    'group_by', 'having', 'select', 'from', 'join'
}

# Always use parameterized queries for SQL
workflow.add_node("AsyncSQLDatabaseNode", "query", {
    "connection_string": "postgresql://...",
    "query": "SELECT * FROM users WHERE id = $1",  # Parameterized
    "params": [user_id]  # Safe parameter binding
})
```

### Parameter Injection Defense

The SDK's explicit parameter requirement prevents injection:

```python
# Node only receives declared parameters
class SecureNode(Node):
    def get_parameters(self):
        return {
            "allowed_param": NodeParameter(type=str, required=True)
        }

    def run(self, **kwargs):
        # Only 'allowed_param' is available
        # Undeclared parameters are filtered out
        # No risk of parameter injection
        return {"result": process(kwargs["allowed_param"])}
```

## Common Pitfalls

### Pitfall 1: Empty Parameter Declaration

```python
# WRONG - No parameters declared
class BadNode(Node):
    def get_parameters(self):
        return {}  # SDK won't inject any parameters!

    def run(self, **kwargs):
        value = kwargs.get('data')  # Always None!

# CORRECT - Declare expected parameters
class GoodNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(type=dict, required=True)
        }
```

### Pitfall 2: Expecting Undeclared Parameters

```python
# WRONG - Expecting parameter without declaration
class BadNode(Node):
    def get_parameters(self):
        return {
            "input_file": NodeParameter(type=str, required=True)
        }

    def run(self, **kwargs):
        file = kwargs["input_file"]  # OK
        format = kwargs.get("output_format")  # Always None! Not declared!

# CORRECT - Declare all expected parameters
class GoodNode(Node):
    def get_parameters(self):
        return {
            "input_file": NodeParameter(type=str, required=True),
            "output_format": NodeParameter(type=str, required=False, default="json")
        }
```

### Pitfall 3: Assuming Parameter Structure

```python
# WRONG - Assuming nested structure from runtime
runtime.execute(workflow.build(), parameters={
    "processor": {"config": {"nested": "value"}}
})

# Node receives (unwrapped):
{
    "config": {"nested": "value"}  # First level unwrapped only
}

# CORRECT - Use flat structure or handle nesting in node
runtime.execute(workflow.build(), parameters={
    "processor": {
        "config_nested_value": "value"  # Flatten structure
    }
})
```

## Validation Errors

### ValueError for Validation Failures

**Changed in v0.9.31:** Validation failures now raise `ValueError` instead of `RuntimeExecutionError`:

```python
from kailash.runtime.local import LocalRuntime

try:
    runtime = LocalRuntime(connection_validation="invalid_mode")
except ValueError as e:  # Changed from RuntimeExecutionError
    print(f"Configuration error: {e}")

# Also applies to parameter validation
try:
    workflow.build()  # Validates parameters
except ValueError as e:  # Missing required parameters raise ValueError
    print(f"Parameter validation failed: {e}")
```

## Best Practices Summary

1. **Explicit Over Implicit**: Always declare parameters in `get_parameters()`
2. **Security First**: Use parameter scoping to prevent data leakage
3. **Type Safety**: Declare parameter types for validation
4. **Business Validation**: Check requirements in `run()` method
5. **Use Method 1 for Tests**: Most reliable and deterministic
6. **Document Parameters**: Use descriptions in NodeParameter
7. **Validate Early**: Catch errors at build time with `workflow.build()`

## Testing with Parameters

### Test Pattern 1: Node Configuration

```python
def test_workflow_with_static_params():
    workflow = WorkflowBuilder()

    # Method 1: Most reliable for tests
    workflow.add_node("DataProcessorNode", "processor", {
        "input_file": "test_data.csv",
        "output_format": "json",
        "batch_size": 10
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["processor"]["result"]["processed"] is True
```

### Test Pattern 2: Runtime Parameters

```python
def test_workflow_with_runtime_params():
    workflow = WorkflowBuilder()

    workflow.add_node("DataProcessorNode", "processor", {
        "output_format": "json"  # Static param
    })

    runtime = LocalRuntime()

    # Test with different input files
    for test_file in ["test1.csv", "test2.csv", "test3.csv"]:
        results, run_id = runtime.execute(
            workflow.build(),
            parameters={
                "processor": {"input_file": test_file}
            }
        )
        assert results["processor"]["result"]["processed"] is True
```

## Related Documentation

- [Parameter Passing Guide](../3-development/parameter-passing-guide.md) - Quick reference
- [Connection Patterns](../2-core-concepts/cheatsheet/005-connection-patterns.md) - Data flow
- [Node Development](../3-development/05-custom-development.md) - Creating custom nodes
- [Validation Guide](../2-core-concepts/validation/validation-guide.md) - Error handling

## Summary

Parameter passing in Kailash SDK uses three methods (node configuration, connections, runtime parameters) with automatic parameter scoping for security and isolation. The SDK's explicit parameter requirement is a security feature that prevents injection attacks and ensures reliable workflows. Always declare parameters in custom nodes and use the appropriate method based on your use case.
