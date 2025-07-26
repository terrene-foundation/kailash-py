# Connection Parameter Validation

**Version**: 0.6.7+
**Priority**: CRITICAL - Security Feature

## Overview

Starting in version 0.6.7, the Kailash SDK provides connection parameter validation to prevent security vulnerabilities where parameters passed through workflow connections could bypass validation checks.

## The Security Issue

Previously, parameters had two paths with different validation:
- **Direct parameters** (via `runtime.execute()`) - ✅ VALIDATED
- **Connection parameters** (via `workflow.add_connection("source", "result", "target", "input")`) - ❌ NOT VALIDATED

This created a security vulnerability where malicious data could flow between nodes without validation.

## Solution: Connection Validation Modes

The `LocalRuntime` now supports a `connection_validation` parameter with three modes:

### 1. "off" Mode - No Validation
```python
runtime = LocalRuntime(connection_validation="off")
```
- Maintains backward compatibility
- No validation of connection parameters
- Use only for legacy workflows

### 2. "warn" Mode - Log Warnings (Default)
```python
runtime = LocalRuntime()  # Default is "warn"
# or explicitly:
runtime = LocalRuntime(connection_validation="warn")
```
- Validates connection parameters
- Logs warnings on validation failures but continues execution
- Recommended for migration period

### 3. "strict" Mode - Enforce Validation
```python
runtime = LocalRuntime(connection_validation="strict")
```
- Validates all connection parameters
- Raises errors on validation failures
- Recommended for production

## Examples

### Basic Usage
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("DataSourceNode", "source", {"data": "test"})
workflow.add_node("ProcessorNode", "processor", {})
workflow.add_connection("source", "output", "processor", "input")

# Strict validation - ensures type safety
runtime = LocalRuntime(connection_validation="strict")
results, _ = runtime.execute(workflow.build(), {})
```

### Migration Example
```python
# During migration, use warn mode to identify issues
runtime = LocalRuntime(connection_validation="warn")

# Monitor logs for validation warnings
import logging
logging.basicConfig(level=logging.WARNING)

# Execute workflow
results, _ = runtime.execute(workflow.build(), {})
# Check logs for warnings about validation failures
```

### Type Validation Example
```python
class StrictNode(Node):
    def get_parameters(self):
        return {
            "count": NodeParameter(name="count", type=int, required=True),
            "name": NodeParameter(name="name", type=str, required=True)
        }

    def run(self, **kwargs):
        # Parameters are guaranteed to be correct types
        count = kwargs["count"]  # Always int
        name = kwargs["name"]    # Always str
        return {"result": f"{name}: {count}"}

# With strict validation, type conversion happens automatically
# String "123" -> int 123
# But "not_a_number" would fail validation
```

## Security Best Practices

1. **Use strict mode in production**
   ```python
   runtime = LocalRuntime(connection_validation="strict")
   ```

2. **Validate during development**
   ```python
   # Run tests with strict validation
   def test_workflow():
       runtime = LocalRuntime(connection_validation="strict")
       # Test will fail if validation issues exist
   ```

3. **Monitor warnings during migration**
   ```python
   import logging
   logger = logging.getLogger("kailash.runtime.local")
   logger.addHandler(logging.StreamHandler())
   logger.setLevel(logging.WARNING)
   ```

## DataFlow Integration

When using kailash-dataflow, connection validation adds an extra layer of security for database operations:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# DataFlow already has SQL injection protection
# Connection validation adds parameter type safety

workflow = WorkflowBuilder()
workflow.add_node("UserInputNode", "input", {})
workflow.add_node("UserCreateNode", "create_user", {})

# Connect user input to database operation
workflow.add_connection("input", "user_data", "create_user", "")

# Strict mode ensures parameters are validated
runtime = LocalRuntime(connection_validation="strict")
results, _ = runtime.execute(workflow.build(), parameters={
    "input": {"user_data": {"name": "Alice", "age": "25"}}  # age will be converted to int
})
```

## Migration Guide

### Step 1: Identify Affected Workflows
```python
# Run with warn mode
runtime = LocalRuntime(connection_validation="warn")

# Execute and check logs
import logging
logging.basicConfig(level=logging.WARNING)
results, _ = runtime.execute(workflow.build(), {})
```

### Step 2: Fix Validation Issues
Common issues and solutions:
- **Missing required parameters**: Ensure connections provide all required inputs
- **Type mismatches**: Add type conversion or fix source node outputs
- **Extra parameters**: Remove undeclared parameters or add them to `get_parameters()`

### Step 3: Enable Strict Mode
```python
# After fixing issues, enable strict mode
runtime = LocalRuntime(connection_validation="strict")
```

## Performance Impact

- **Minimal overhead**: < 2ms per connection
- **Caching**: Validation results are cached within execution
- **Type conversion**: Automatic conversion attempts before failing

## Troubleshooting

### "Connection validation failed"
- Check node's `get_parameters()` declarations
- Verify parameter types match
- Ensure required parameters are provided

### "Missing required inputs"
- Check workflow connections provide all required parameters
- Use workflow visualization to trace data flow

### Performance concerns
- Use "off" mode for performance-critical paths (with caution)
- Consider caching validation results across executions

## Related Documentation
- [Security Best Practices](../enterprise/security-patterns.md)
- [Workflow Building Guide](../workflows/workflow-building-guide.md)
- [Node Parameter Reference](../nodes/node-parameter-reference.md)
