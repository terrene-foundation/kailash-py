# Parameter Troubleshooting Guide

## Overview

This guide helps you troubleshoot parameter injection issues in the Kailash SDK. Parameter injection is the process of passing runtime values to workflow nodes during execution.

## 🚨 Common Parameter Issues

### Issue 1: Parameters Not Received by Nodes

**Symptoms:**
```python
# Node receives empty parameters despite providing them
results = runtime.execute(workflow, parameters={"node_id": {"param": "value"}})
print(results["node_id"]["received_params"])  # Output: []
```

**Root Causes:**
1. **Undeclared Parameters**: Parameters not declared in `get_parameters()`
2. **Node ID Mismatch**: Wrong node ID in parameter dictionary
3. **Parameter Format Issues**: Incorrect parameter structure

**Solutions:**

#### ✅ **Solution 1: Declare All Parameters**
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "param": NodeParameter(
                name="param",
                type=str,  # Always specify type
                required=False,
                description="Parameter description"
            )
        }
```

#### ✅ **Solution 2: Use Enhanced Validation**
```python
# Enable strict validation to catch issues early
runtime = LocalRuntime(
    parameter_validation="strict",  # "warn", "strict", or "debug"
    enable_parameter_debugging=True
)
```

#### ✅ **Solution 3: Debug Parameter Flow**
```python
from kailash.runtime.parameter_debugger import ParameterDebugger

# Analyze parameter flow
debugger = ParameterDebugger()
report = debugger.trace_parameter_flow(workflow, runtime_parameters)
debugger.print_parameter_flow_report(report)
```

### Issue 2: "Required Parameter Missing" Errors

**Symptoms:**
```
NodeValidationError: Node 'my_node' missing required inputs: ['required_param']
```

**Solutions:**

#### ✅ **Provide Required Parameters**
```python
# Method 1: Node configuration
workflow.add_node("MyNode", "node_id", {"required_param": "value"})

# Method 2: Runtime parameters  
runtime.execute(workflow, parameters={
    "node_id": {"required_param": "value"}
})

# Method 3: Workflow-level parameters (distributed to all nodes)
runtime.execute(workflow, parameters={
    "required_param": "value"  # Not nested under node_id
})
```

#### ✅ **Make Parameters Optional**
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "param": NodeParameter(
                name="param",
                type=str,
                required=False,  # Make optional
                default="default_value"  # Provide default
            )
        }
```

### Issue 3: Parameter Type Validation Errors

**Symptoms:**
```
Parameter 'param' type mismatch. Expected <class 'dict'>, got <class 'str'>
```

**Solutions:**

#### ✅ **Fix Parameter Types**
```python
# Wrong: Passing string when dict expected
parameters = {"node_id": {"config": "string_value"}}

# Correct: Pass proper type
parameters = {"node_id": {"config": {"key": "value"}}}
```

#### ✅ **Update Parameter Declaration**
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "flexible_param": NodeParameter(
                name="flexible_param",
                type=object,  # Accept any type
                required=False
            )
        }
```

### Issue 4: "Unused Workflow Parameters" Warnings

**Symptoms:**
```
WARNING: Unused workflow parameters: ['unused_param']
```

**Solutions:**

#### ✅ **Remove Unused Parameters**
```python
# Remove parameters that aren't used by any nodes
parameters = {
    "node_id": {"used_param": "value"}
    # Remove: "unused_param": "value"
}
```

#### ✅ **Add Parameter Declarations**
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "used_param": NodeParameter(name="used_param", type=str, required=False),
            "previously_unused": NodeParameter(name="previously_unused", type=str, required=False)
        }
```

## 🔧 Parameter Validation Modes

### Validation Mode: `"warn"` (Default)
- Logs warnings for parameter issues
- Allows execution to continue
- Good for development and debugging

```python
runtime = LocalRuntime(parameter_validation="warn")
```

### Validation Mode: `"strict"`
- Raises errors for parameter issues
- Prevents execution with validation problems
- Recommended for production

```python
runtime = LocalRuntime(parameter_validation="strict")
```

### Validation Mode: `"debug"`
- Verbose logging for troubleshooting
- Shows detailed parameter flow analysis
- Best for investigating complex issues

```python
runtime = LocalRuntime(
    parameter_validation="debug",
    enable_parameter_debugging=True
)
```

### Validation Mode: `"off"`
- Disables enhanced parameter validation
- Uses only basic SDK validation
- For backward compatibility

```python
runtime = LocalRuntime(parameter_validation="off")
```

## 🔍 Debugging Tools

### 1. Parameter Flow Tracer

Use the `ParameterDebugger` to trace parameter flow through your workflow:

```python
from kailash.runtime.parameter_debugger import ParameterDebugger

debugger = ParameterDebugger()

# Analyze parameter flow
report = debugger.trace_parameter_flow(
    workflow=workflow,
    runtime_parameters=parameters,
    node_configs=node_configs
)

# Print human-readable report
debugger.print_parameter_flow_report(report)
```

**Sample Output:**
```
============================================================
PARAMETER FLOW ANALYSIS REPORT
============================================================

📊 SUMMARY:
  Total Operations: 12
  Success Rate: 83.3%
  Blocked Operations: 2

📋 PARAMETER FORMAT:
  Node-specific parameters: 2 nodes
    node1: ['param1', 'param2']
    node2: ['param3']
  Workflow-level parameters: ['global_param']

🚫 COMMON ISSUES:
  (2x) Parameter not declared and node doesn't accept **kwargs
  (1x) Runtime parameters provided for non-existent node

💡 RECOMMENDATIONS:
  1. Found 2 parameters blocked due to missing declarations. Add these parameters to the node's get_parameters() method.
  2. Found 1 reference to non-existent nodes. Check node ID spelling in runtime parameters.
```

### 2. Enhanced Logging

Enable detailed parameter logging:

```python
import logging

# Enable debug logging
logging.getLogger('kailash.runtime.local').setLevel(logging.DEBUG)
logging.getLogger('kailash.runtime.parameter_validator').setLevel(logging.DEBUG)

# Create runtime with debug features
runtime = LocalRuntime(
    debug=True,
    parameter_validation="debug",
    enable_parameter_debugging=True
)
```

### 3. Validation Reports

Get structured validation reports:

```python
from kailash.runtime.parameter_validator import EnhancedParameterValidator, ValidationMode

validator = EnhancedParameterValidator(ValidationMode.DEBUG)
validated_params, issues = validator.validate_runtime_parameters(
    workflow_nodes=workflow._node_instances,
    runtime_parameters=parameters
)

# Get detailed report
report = validator.get_validation_report()
print(f"Validation report: {report}")
```

## 📋 Parameter Format Reference

### Node-Specific Format
Parameters are grouped by node ID:

```python
parameters = {
    "node1": {
        "param1": "value1",
        "param2": "value2"
    },
    "node2": {
        "param3": "value3"
    }
}
```

### Workflow-Level Format
Parameters are distributed to all compatible nodes:

```python
parameters = {
    "global_param": "value",     # Goes to all nodes that can accept it
    "another_global": "value2"   # Also distributed
}
```

### Mixed Format
Both formats can be combined:

```python
parameters = {
    "node1": {                   # Node-specific
        "specific_param": "value"
    },
    "global_param": "value"      # Workflow-level
}
```

## ⚡ Quick Fixes

### Quick Fix 1: Missing Parameter Declaration

**Error:**
```
Runtime parameter 'my_param' not declared in node's get_parameters()
```

**Fix:**
```python
class MyNode(Node):
    def get_parameters(self):
        return {
            "my_param": NodeParameter(  # Add this declaration
                name="my_param",
                type=str,
                required=False
            )
        }
```

### Quick Fix 2: Wrong Node ID

**Error:**
```
Runtime parameters provided for non-existent node 'wrong_id'
```

**Fix:**
```python
# Check your node IDs
workflow.add_node("MyNode", "correct_id", {})  # Use this ID

parameters = {
    "correct_id": {"param": "value"}  # Not "wrong_id"
}
```

### Quick Fix 3: **kwargs Nodes

For nodes that should accept any parameters:

```python
class FlexibleNode(Node):
    def run(self, **kwargs):  # Accept any parameters
        return {"received": list(kwargs.keys())}
```

**Note:** PythonCodeNode automatically accepts **kwargs.

## 🧪 Testing Parameter Injection

### Test Template

```python
def test_parameter_injection():
    workflow = WorkflowBuilder()
    workflow.add_node("MyNode", "test_node", {})
    
    runtime = LocalRuntime(
        parameter_validation="strict",  # Catch issues early
        enable_parameter_debugging=True
    )
    
    parameters = {
        "test_node": {
            "test_param": "test_value"
        }
    }
    
    try:
        results, _ = runtime.execute(workflow.build(), parameters=parameters)
        
        # Verify parameters were received
        assert "test_param" in results["test_node"]["received_params"]
        print("✅ Parameter injection test passed")
        
    except Exception as e:
        print(f"❌ Parameter injection test failed: {e}")
        
        # Use debugger to investigate
        from kailash.runtime.parameter_debugger import ParameterDebugger
        debugger = ParameterDebugger()
        report = debugger.trace_parameter_flow(workflow.build(), parameters)
        debugger.print_parameter_flow_report(report)
```

## 🔗 Related Documentation

- [Parameter Passing Guide](parameter-passing-guide.md) - Comprehensive parameter usage
- [Node Development Guide](05-custom-development.md) - Creating nodes with parameters
- [Common Mistakes](../2-core-concepts/validation/common-mistakes.md) - Avoid these pitfalls
- [Troubleshooting Guide](05-troubleshooting.md) - General SDK troubleshooting

## 💡 Best Practices

1. **Always Declare Parameters**: Every runtime parameter should be declared in `get_parameters()`
2. **Use Type Information**: Always specify parameter types for better validation
3. **Enable Validation**: Use strict validation in production environments
4. **Debug with Tools**: Use the parameter debugger for complex issues
5. **Test Parameter Injection**: Include parameter tests in your test suite
6. **Follow Naming Conventions**: Use clear, consistent parameter names
7. **Document Parameters**: Include descriptions in parameter declarations

## 🚀 Performance Tips

1. **Avoid Large Parameter Objects**: Keep parameter values reasonably sized
2. **Use Appropriate Validation Modes**: "strict" for production, "debug" for troubleshooting
3. **Cache Parameter Validation**: Reuse workflows when possible
4. **Monitor Parameter Usage**: Remove unused parameters to reduce overhead

---

**Need more help?** 
- Check the [SDK Users Guide](../README.md) for comprehensive documentation
- Review [examples/](../../examples/) for working parameter usage patterns
- Use the parameter debugger for detailed flow analysis