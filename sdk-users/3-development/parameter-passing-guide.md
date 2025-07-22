# Parameter Passing Guide - Three Methods for Node Parameters

*Complete guide to providing parameters to nodes in Kailash SDK workflows*

## 🚨 Critical Understanding

With the Enterprise Parameter Passing Gold Standard (v0.7.0+), the SDK enforces strict parameter validation for security and reliability. **All required parameters must be provided through one of three methods**, or the workflow will fail at build time.

## ⚡ Quick Reference

```python
# Method 1: Node Configuration (Static)
workflow.add_node("NotificationNode", "notify", {
    "channel": "email",  # Known at build time
    "template": "welcome"
})

# Method 2: Workflow Connections (Dynamic)
workflow.add_connection("get_prefs", "channel", "notify", "channel")
# Parameter comes from another node's output

# Method 3: Runtime Parameters (Dynamic)
runtime.execute(workflow.build(), parameters={
    "notify": {"channel": "sms"}  # Override at execution
})
```

## 📋 The Three Methods Explained

### Method 1: Node Configuration (Static Parameters)

Use when parameter values are **known at workflow design time**.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# All parameters provided in node configuration
workflow.add_node("EmailNode", "send_email", {
    "to": "user@example.com",
    "subject": "Welcome",
    "template": "onboarding",
    "retry_count": 3
})

# ✅ All required parameters provided - will validate successfully
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**When to use:**
- Configuration values
- Fixed business rules
- Default settings
- Environment-specific values

### Method 2: Workflow Connections (Dynamic Parameters)

Use when parameter values come from **other nodes in the workflow**.

```python
workflow = WorkflowBuilder()

# Node 1: Fetches user preferences from database
workflow.add_node("DatabaseQueryNode", "get_user", {
    "query": "SELECT * FROM users WHERE id = ?",
    "params": [123]
})

# Node 2: Gets notification preferences
workflow.add_node("PythonCodeNode", "extract_prefs", {
    "code": """
channel = data['notification_channel']
frequency = data['email_frequency']
result = {'channel': channel, 'frequency': frequency}
"""
})

# Node 3: Sends notification (parameters come from connections)
workflow.add_node("NotificationNode", "notify", {
    # Don't provide 'channel' or 'frequency' here - they come from connections
    "template": "weekly_digest"  # Only static parameters
})

# Connect the data flow
workflow.add_connection("get_user", "result", "extract_prefs", "data")
workflow.add_connection("extract_prefs", "channel", "notify", "channel")
workflow.add_connection("extract_prefs", "frequency", "notify", "frequency")

# ✅ Parameters provided via connections - will validate successfully
results, run_id = runtime.execute(workflow.build())
```

**When to use:**
- Data transformation pipelines
- Conditional logic based on previous results
- Database-driven configurations
- Multi-step processing

### Method 3: Runtime Parameters (Dynamic Override)

Use when parameter values are **determined at execution time** or need to **override defaults**.

```python
workflow = WorkflowBuilder()

# Define nodes without all parameters
workflow.add_node("ReportGeneratorNode", "generate", {
    "template": "monthly_report"
    # 'start_date' and 'end_date' will come from runtime
})

workflow.add_node("EmailNode", "send_report", {
    "subject": "Monthly Report"
    # 'recipients' will come from runtime
})

workflow.add_connection("generate", "report", "send_report", "attachment")

# Provide parameters at execution time
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

## 🔄 Combining Methods

You can combine all three methods for maximum flexibility:

```python
workflow = WorkflowBuilder()

# Method 1: Static configuration
workflow.add_node("DataValidatorNode", "validate", {
    "rules": "strict",  # Static configuration
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
        "rules": "relaxed"  # Override the static "strict" value
    }
})
```

## 🚨 Common Errors and Solutions

### Error: Missing Required Parameters
```python
# ❌ This will fail at build time
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
    "email": "alice@example.com"  # ✅
})

# Option 2: Connect from another node
workflow.add_connection("form_data", "email", "create", "email")  # ✅

# Option 3: Provide at runtime
runtime.execute(workflow.build(), parameters={
    "create": {"email": "alice@example.com"}  # ✅
})
```

### Error: Parameter Type Mismatch
```python
# ❌ Wrong parameter type
workflow.add_node("BatchProcessorNode", "process", {
    "batch_size": "100"  # String instead of integer!
})
```

**Solution:** Ensure correct types:
```python
# ✅ Correct type
workflow.add_node("BatchProcessorNode", "process", {
    "batch_size": 100  # Integer
})
```

## 🎯 Best Practices

### 1. **Declare All Parameters in Custom Nodes**
```python
class MyCustomNode(Node):
    def get_parameters(self):
        return {
            "input_file": NodeParameter(type=str, required=True),
            "output_format": NodeParameter(type=str, required=False, default="json"),
            "batch_size": NodeParameter(type=int, required=False, default=100)
        }
```

### 2. **Use Descriptive Parameter Names**
```python
# ❌ Bad
workflow.add_node("ProcessorNode", "proc", {"d": data, "f": "json"})

# ✅ Good
workflow.add_node("ProcessorNode", "processor", {
    "input_data": data,
    "output_format": "json"
})
```

### 3. **Document Dynamic Parameters**
```python
# Add comments explaining parameter sources
workflow.add_node("NotificationNode", "notify", {
    "template": "order_confirmation"
    # 'customer_email' comes from 'get_order' node via connection
    # 'order_details' comes from 'process_order' node via connection
})
```

### 4. **Validate Early with Build**
```python
# Always build before execute to catch parameter errors
try:
    built_workflow = workflow.build()  # Validates all parameters
except WorkflowValidationError as e:
    print(f"Parameter error: {e}")
    # Fix missing parameters before proceeding
```

## 🔐 Security Benefits

The strict parameter validation provides:

1. **No Parameter Injection**: Nodes only receive declared parameters
2. **Type Safety**: Parameters are validated against declared types
3. **Explicit Data Flow**: All data movement is traceable
4. **Build-Time Validation**: Errors caught before execution

## 📚 Related Documentation

- [Connection Patterns](../2-core-concepts/cheatsheet/005-connection-patterns.md) - Data flow between nodes
- [Enterprise Parameter Passing Gold Standard](../7-gold-standards/enterprise-parameter-passing-gold-standard.md) - Security rationale
- [Node Development Guide](./05-custom-development.md) - Creating nodes with proper parameters
- [Common Mistakes](../2-core-concepts/validation/common-mistakes.md) - Parameter-related errors

## 🎓 Summary

Remember: **Every required parameter must come from somewhere**:
1. **Static** → Node configuration
2. **Dynamic from nodes** → Workflow connections  
3. **Dynamic from runtime** → Execution parameters

The SDK will validate this at build time, ensuring your workflows are correct before they run. This is a feature, not a limitation - it makes your workflows more reliable and secure!