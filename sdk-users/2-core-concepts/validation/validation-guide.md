# Validation Guide

*Built-in validation framework for Kailash SDK workflows*

## 🎯 Overview

The Kailash SDK includes built-in validation for workflows, ensuring reliability, correctness, and performance. All validation is integrated directly into the WorkflowBuilder and Runtime systems.

## 📋 Quick Reference

| Validation Type | Method | Purpose |
|----------------|---------|---------|
| **Workflow Structure** | `workflow.build().validate()` | Validate workflow structure and connections |
| **Parameter Validation** | `workflow.validate_parameter_declarations()` | Check required parameters are provided |
| **Contract Validation** | `workflow.validate_all_contracts()` | Validate typed connections and contracts |
| **Runtime Validation** | `runtime.execute()` | Comprehensive validation during execution |

## 🔧 Built-in Workflow Validation

### Basic Workflow Validation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = {'value': 42}"})

# Validate workflow structure
built_workflow = workflow.build()
validation_result = built_workflow.validate()

# Validate contracts
contracts_valid, contract_errors = workflow.validate_all_contracts()
if not contracts_valid:
    print(f"Contract errors: {contract_errors}")

# Validate parameters
param_errors = workflow.validate_parameter_declarations()
if param_errors:
    for error in param_errors:
        print(f"Parameter error: {error}")

# Runtime validation (execute)
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow)
```

### Parameter Validation with Error Handling
```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with validation
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})

# Check for parameter errors
param_errors = workflow.validate_parameter_declarations()
if param_errors:
    for error in param_errors:
        print(f"Parameter error: {error}")
        print(f"  Suggestion: {error.suggestion}")
        print(f"  Severity: {error.severity}")
```

## 🔗 Connection Validation

### Basic Connection Validation
```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with connections
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 1}"})
workflow.add_node("PythonCodeNode", "node2", {"code": "result = input_data"})
workflow.add_connection("node1", "result", "node2", "input_data")

# Validate workflow
built_workflow = workflow.build()
validation_result = built_workflow.validate()  # Validates connections
```

### Advanced Connection Validation with Type Safety
```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with typed connections
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = len(data)"})

# Add connection with validation
workflow.add_connection("reader", "data", "processor", "data")

# Validate all contracts (includes type checking)
contracts_valid, contract_errors = workflow.validate_all_contracts()
if not contracts_valid:
    for error in contract_errors:
        print(f"Contract error: {error}")
```

## ⚡ Runtime Validation

### Comprehensive Runtime Validation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def validate_and_execute(workflow):
    """Validate workflow before execution"""

    # Pre-execution validation
    param_errors = workflow.validate_parameter_declarations()
    if param_errors:
        print("Parameter validation failed:")
        for error in param_errors:
            print(f"  - {error.message}")
        return None

    # Contract validation
    contracts_valid, contract_errors = workflow.validate_all_contracts()
    if not contracts_valid:
        print("Contract validation failed:")
        for error in contract_errors:
            print(f"  - {error}")
        return None

    # Build and validate structure
    built_workflow = workflow.build()
    structural_result = built_workflow.validate()

    # Execute with runtime validation
    try:
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)
        print("✅ Workflow executed successfully with validation")
        return results
    except Exception as e:
        print(f"❌ Runtime validation failed: {e}")
        return None

# Example usage
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {"code": "result = {'status': 'complete'}"})
results = validate_and_execute(workflow)
```

### Error Handling and Recovery
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def robust_workflow_execution(workflow, parameters=None):
    """Execute workflow with comprehensive validation and error handling"""

    try:
        # Parameter validation
        param_errors = workflow.validate_parameter_declarations()
        if param_errors:
            warnings = [err for err in param_errors if err.severity.value == 'warning']
            errors = [err for err in param_errors if err.severity.value == 'error']

            if errors:
                print("❌ Critical parameter errors:")
                for error in errors:
                    print(f"  - {error.message}")
                return None, "Parameter validation failed"

            if warnings:
                print("⚠️  Parameter warnings:")
                for warning in warnings:
                    print(f"  - {warning.message}")

        # Build and execute
        built_workflow = workflow.build()
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow, parameters=parameters)

        return results, "Success"

    except ValueError as e:
        # Validation errors (wrong validation mode, invalid parameters, etc.)
        error_msg = str(e)
        if "missing required inputs" in error_msg:
            return None, f"Missing required parameters: {error_msg}"
        elif "connection" in error_msg.lower():
            return None, f"Connection error: {error_msg}"
        else:
            return None, f"Validation error: {error_msg}"
    except Exception as e:
        # Other execution errors
        return None, f"Execution error: {str(e)}"

# Example usage with error handling
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = len(data)"})
workflow.add_connection("reader", "data", "processor", "data")

results, status = robust_workflow_execution(workflow)
print(f"Execution status: {status}")
```

## 📊 Performance Validation

### Basic Performance Monitoring
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import time

def validate_performance(workflow, max_duration=30.0):
    """Validate workflow performance requirements"""

    runtime = LocalRuntime()

    # Measure execution time
    start_time = time.time()
    try:
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        if execution_time > max_duration:
            print(f"❌ Performance validation failed: {execution_time:.2f}s > {max_duration}s")
            return False, execution_time
        else:
            print(f"✅ Performance validation passed: {execution_time:.2f}s")
            return True, execution_time

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"❌ Execution failed after {execution_time:.2f}s: {e}")
        return False, execution_time

# Example usage
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "fast_task", {"code": "result = {'processed': True}"})

performance_ok, duration = validate_performance(workflow.build(), max_duration=5.0)
```

## 🔐 Security Validation

### Input Security Validation
```python
from kailash.workflow.builder import WorkflowBuilder

def validate_secure_inputs(workflow_config):
    """Validate workflow configuration for security issues"""

    security_issues = []

    # Check for sensitive data in configuration
    sensitive_keywords = ['password', 'secret', 'key', 'token']

    for node_id, config in workflow_config.items():
        for param, value in config.items():
            if any(keyword in param.lower() for keyword in sensitive_keywords):
                if isinstance(value, str) and len(value) > 0:
                    security_issues.append(f"Potential sensitive data in {node_id}.{param}")

    return security_issues

# Example usage
config = {
    "database": {"host": "localhost", "password": "secret123"},  # Security issue
    "processor": {"code": "result = data"}  # Safe
}

issues = validate_secure_inputs(config)
if issues:
    print("🔐 Security validation issues:")
    for issue in issues:
        print(f"  - {issue}")
```

## 📋 Best Practices

1. **Always Validate Before Execution**
   - Use `validate_parameter_declarations()` to catch missing parameters
   - Use `validate_all_contracts()` for type safety
   - Use `workflow.build().validate()` for structure validation

2. **Handle Validation Errors Gracefully**
   - Check error severity (warning vs error)
   - Provide clear error messages to users
   - Implement recovery strategies for warnings

3. **Use Runtime Validation**
   - LocalRuntime performs comprehensive validation during execution
   - Catch and handle specific error types
   - Monitor execution time and resource usage

## 🚀 Quick Reference

### Essential Validation Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "task", {"code": "result = {'done': True}"})

# Validate before execution
param_errors = workflow.validate_parameter_declarations()
contracts_valid, contract_errors = workflow.validate_all_contracts()

if param_errors or not contracts_valid:
    print("❌ Validation failed")
else:
    # Execute with runtime validation
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    print("✅ Execution successful")
```

### Common Validation Errors
- **Missing Parameters**: Use `validate_parameter_declarations()`
- **Type Mismatches**: Use `validate_all_contracts()`
- **Connection Issues**: Runtime validation will catch these
- **Missing Files**: Runtime validation during node execution

---
*Related: [Parameter Passing Guide](../3-development/parameter-passing-guide.md), [Common Mistakes](common-mistakes.md)*
