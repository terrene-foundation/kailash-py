# Gold Standard: Comprehensive Parameter Passing Guide for Kailash SDK

**Version**: 3.0 (Consolidated)
**Last Updated**: 2025-07-22
**Status**: ✅ Authoritative Reference - Replaces All Previous Versions
**Purpose**: Complete guide for parameter passing in Kailash SDK with enterprise patterns
**SDK Version**: Kailash SDK 0.8.x (tested with v0.6.6+)

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Three Methods of Parameter Passing](#three-methods-of-parameter-passing)
3. [Critical SDK Investigation Findings](#critical-sdk-investigation-findings)
4. [Enterprise Best Practices](#enterprise-best-practices)
5. [Implementation Patterns](#implementation-patterns)
6. [Common Pitfalls and Solutions](#common-pitfalls-and-solutions)
7. [Security Considerations](#security-considerations)
8. [Testing Guidelines](#testing-guidelines)
9. [Migration Guide](#migration-guide)
10. [Troubleshooting](#troubleshooting)

## Executive Summary

This document consolidates all parameter passing knowledge for the Kailash SDK, incorporating:
- Findings from extensive testing (TODO 023)
- SDK source code investigation results
- Enterprise security patterns
- Production-tested solutions

**Key Insight**: The SDK's requirement for explicit parameter declaration is a **security feature, not a bug**. It aligns with enterprise best practices by preventing arbitrary parameter injection attacks.

## Three Methods of Parameter Passing

### Method 1: Node Configuration ⭐⭐⭐⭐⭐
**Reliability**: Always works
**Best for**: Static values, test fixtures, default settings

```python
from kailash.workflow.builder import WorkflowBuilder
workflow.add_node("MyNode", "node_id", {
    "param1": "static_value",
    "param2": {"nested": "data"},
    "connection_string": database_url
})
```

**Advantages**:
- Most reliable method
- Clear and explicit
- Easy to debug
- Ideal for testing

### Method 2: Workflow Connections ⭐⭐⭐⭐⭐
**Reliability**: Always works
**Best for**: Dynamic data flow, pipelines, transformations

```python
workflow.add_connection("source_node", "output_field", "target_node", "input_param")
```

**Advantages**:
- Dynamic data flow
- Loose coupling between nodes
- Enables complex workflows
- Natural for data pipelines

### Method 3: Runtime Parameters ⭐⭐⭐
**Reliability**: Has edge case
**Best for**: User input, environment overrides, dynamic values

```python
runtime.execute(workflow.build(), parameters={
    "node_id": {
        "param1": "runtime_value"
    }
})
```

**⚠️ EDGE CASE WARNING**: Fails when ALL conditions are met:
- Empty node configuration `{}`
- All parameters are optional (`required=False`)
- No connections provide parameters

**Solution**: Always provide minimal config or have at least one required parameter.

## Critical SDK Investigation Findings

### 2025-07-22 Comprehensive Investigation Results

During TODO 023 implementation, we discovered:

1. **Node Registration is Irrelevant for Parameter Injection**
   - Both registered and unregistered nodes receive parameters identically
   - Registration only provides discoverability benefits
   - The WorkflowParameterInjector processes ALL nodes in `workflow._node_instances`

2. **Parameter Definition is the Real Requirement**
   ```python
   def get_parameters(self) -> Dict[str, NodeParameter]:
       return {
           "param_name": NodeParameter(
               name="param_name",
               type=str,
               required=True,
               description="Parameter description"
           )
       }
   ```
   - Nodes MUST define parameters to receive them
   - Empty `get_parameters()` = no parameters received
   - This is a security feature, not a limitation

3. **AsyncSQLDatabaseNode JSON Behavior**
   - Returns JSONB columns as JSON strings (standard SQL driver behavior)
   - Always parse JSON explicitly in your workflows
   - Example fix implemented in TPCTokenGeneratorNode

## Enterprise Best Practices

### Schema-First Approach (Industry Standard)

Used by AWS, Google Cloud, Microsoft Azure:

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional, Dict, Any

class UserManagementContract(BaseModel):
    """Enterprise parameter contract with full validation."""

    model_config = ConfigDict(
        extra="forbid",  # Security: reject unknown parameters
        validate_assignment=True,
        use_enum_values=True
    )

    operation: Literal["create", "update", "delete", "get"] = Field(
        description="Operation to perform"
    )
    user_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User data for operations"
    )
    tenant_id: str = Field(
        description="Tenant identifier"
    )
    requestor_id: str = Field(
        description="User making the request"
    )

    @model_validator(mode='after')
    def validate_operation_requirements(self):
        """Validate required fields for specific operations."""
        if self.operation in ['create', 'update'] and not self.user_data:
            raise ValueError(f"user_data required for {self.operation}")
        return self
```

### Why Enterprises Reject Dynamic Parameter Injection

| Risk | Impact | Example |
|------|--------|---------|
| **Security** | Parameter injection attacks | SQL injection via unvalidated params |
| **Compliance** | Audit failures | Can't track unknown parameters |
| **Debugging** | Hard to trace issues | Parameters appear/disappear dynamically |
| **Testing** | Incomplete coverage | Can't test all parameter combinations |
| **Documentation** | Unmaintainable | Can't document dynamic behavior |

## Implementation Patterns

### Pattern 1: Workflow-Specific Entry Nodes (Recommended)

```python
from kailash.nodes.base import Node, NodeParameter
from typing import Dict, Any

class UserManagementEntryNode(Node):
    """Entry node with explicit parameter declaration."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Declare ALL expected parameters explicitly."""
        return {
            "operation": NodeParameter(
                type=str,
                required=True,  # At least one required prevents edge case
                description="Operation to perform"
            ),
            "user_data": NodeParameter(
                type=dict,
                required=False,
                default={},
                description="User data"
            ),
            "tenant_id": NodeParameter(
                type=str,
                required=True,
                description="Tenant ID"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Process with guaranteed parameters."""
        # Required parameters are guaranteed to exist
        operation = kwargs["operation"]
        tenant_id = kwargs["tenant_id"]

        # Optional parameters need get() with defaults
        user_data = kwargs.get("user_data", {})

        # Business logic validation
        if operation == "create" and not user_data:
            raise ValueError("user_data required for create operation")

        return {
            "validated_params": {
                "operation": operation,
                "user_data": user_data,
                "tenant_id": tenant_id
            }
        }
```

### Pattern 2: GovernedNode with Contracts (Enterprise Pattern)

```python
from src.tpc.tpc_user_management.nodes.base.governed_node import GovernedNode
from pydantic import BaseModel

class MyNode(GovernedNode):
    """Node with automatic parameter governance."""

    @classmethod
    def get_parameter_contract(cls) -> Type[BaseModel]:
        """Return Pydantic contract for automatic validation."""
        return UserManagementContract

    def run(self, **kwargs) -> Dict[str, Any]:
        """Parameters are pre-validated by governance framework."""
        # All parameters guaranteed valid per contract
        return process_user_operation(**kwargs)
```

**CRITICAL SDK Parameter Filtering Discovery (2025-07-18)**:

The SDK passes internal parameters (like 'node_id', 'workflow_id') along with business parameters. Since contracts use `extra="forbid"` for security, GovernedNode must filter parameters to only include those defined in the contract. This is implemented in the GovernedNode base class:

```python
def execute(self, **kwargs) -> Dict[str, Any]:
    """Execute with parameter filtering and validation."""
    contract_class = self.get_parameter_contract()

    # CRITICAL: Filter to contract fields only
    contract_fields = set(contract_class.model_fields.keys())
    filtered_params = {
        k: v for k, v in kwargs.items()
        if k in contract_fields
    }

    # Validate against contract
    validated_contract = contract_class(**filtered_params)
    validated_params = validated_contract.model_dump()

    # Apply governance and execute
    return self.run(**validated_params)
```

This filtering prevents Pydantic validation errors when SDK internal parameters are passed to nodes with strict contracts.

### Pattern 3: SecureGovernedNode (Production Security)

```python
from src.tpc.tpc_user_management.nodes.base.secure_governed_node import SecureGovernedNode

class ProductionNode(SecureGovernedNode):
    """Enhanced security for connection parameters."""

    @classmethod
    def get_parameter_contract(cls):
        """Workflow parameters."""
        return MyParameterContract

    @classmethod
    def get_connection_contract(cls):
        """Connection parameters (validated separately)."""
        return MyConnectionContract

    def run(self, **kwargs):
        """Both parameter types are validated."""
        # Security: Undeclared parameters filtered and logged
        return secure_process(**kwargs)
```

### Pattern 4: JSON Handling for Database Results

```python
# CRITICAL: AsyncSQLDatabaseNode returns JSONB as strings
workflow.add_node("PythonCodeNode", "adapt_user_data", {
    "code": """
# Handle AsyncSQLDatabaseNode result format
if isinstance(user_result, dict) and 'data' in user_result:
    rows = user_result.get('data', [])
    if rows and len(rows) > 0:
        user_row = rows[0]

        # CRITICAL: Parse JSON attributes
        attributes = user_row.get('attributes', '{}')
        if isinstance(attributes, str):
            import json
            try:
                attributes = json.loads(attributes)
            except:
                attributes = {}

        result = {
            "user": user_row,
            "attributes": attributes  # Now a dict
        }
"""
})
```

## Common Pitfalls and Solutions

### Pitfall 1: Empty Parameter Declaration

```python
# ❌ WRONG - No parameters declared
class BadNode(Node):
    def get_parameters(self):
        return {}  # SDK injects nothing!

# ✅ CORRECT - Explicit declaration
class GoodNode(Node):
    def get_parameters(self):
        return {
            "config": NodeParameter(type=dict, required=True)
        }
```

### Pitfall 2: Expecting Parameters Without Declaration

```python
# ❌ WRONG - Expecting undeclared parameter
def run(self, **kwargs):
    operation = kwargs.get('operation')  # Always None if not declared!

# ✅ CORRECT - Declare in get_parameters() first
def get_parameters(self):
    return {"operation": NodeParameter(type=str, required=True)}
```

### Pitfall 3: Wrong Result Structure Assumptions

```python
# ❌ WRONG - Assuming structure without checking
assert results["validator"]["valid"] is False

# ✅ CORRECT - Check actual node output structure
assert results["validator"]["result"]["success"] is False
```

### Pitfall 4: Not Handling JSON from Database

```python
# ❌ WRONG - Assuming JSONB returns as dict
attributes = user_data["attributes"]
module_admin = attributes.get("module_admin")  # Error: str has no attribute 'get'

# ✅ CORRECT - Parse JSON first
attributes = user_data["attributes"]
if isinstance(attributes, str):
    import json
    attributes = json.loads(attributes)
module_admin = attributes.get("module_admin")
```

## Security Considerations

### SQL Injection Prevention

Context-aware validation based on field names:

```python
# User content fields - NEVER scan (allow O'Brien, user--admin)
user_content_fields = {
    'username', 'first_name', 'last_name', 'email',
    'display_name', 'requestor_id', 'created_by'
}

# SQL construction fields - ALWAYS scan
sql_dangerous_fields = {
    'query', 'sql', 'where', 'filter', 'order_by',
    'group_by', 'having', 'select', 'from', 'join'
}
```

### Parameter Injection Defense

```python
# SecureGovernedNode automatically:
# 1. Validates against contracts
# 2. Filters undeclared parameters
# 3. Logs security violations
# 4. Prevents injection attacks
```

## Testing Guidelines

### Gold Standard Test Structure

```python
def test_method1_authentication_workflow(self, test_environment, database_url, admin_user):
    """Test authentication with node configuration."""
    runtime = test_environment.runtime

    workflow = WorkflowBuilder()

    # Method 1: All parameters in config
    workflow.add_node("TPCParameterPrepNode", "prep", {
        "credentials": {
            "username": admin_user["username"],
            "password": "test_password"
        },
        "tenant_id": "test"
    })

    # Database node needs connection string
    workflow.add_node("AsyncSQLDatabaseNode", "lookup", {
        "connection_string": database_url,
        "query": "SELECT * FROM users WHERE username = $1"
    })

    # Connect and execute
    workflow.add_connection("prep", "result.db_params", "lookup", "params")
    results, run_id = runtime.execute(workflow.build())

    # Validate results
    assert results["prep"]["result"]["credentials"]["username"] == admin_user["username"]
```

### Key Testing Principles

1. **Always use Method 1 for tests** - Most reliable
2. **Reference actual output structure** - Check node contracts
3. **Handle JSON from databases** - Always parse explicitly
4. **Use existing fixtures** - test_environment, database_url, seed_json_data
5. **Test through workflows** - Not direct database operations

## Migration Guide

### From SDK < 0.8.x

```python
# Old pattern (deprecated)
builder.add_workflow_inputs("node", {"param": "value"})

# New pattern (Method 1)
builder.add_node("Node", "node", {"param": "value"})
```

### From Dynamic to Explicit Parameters

```python
# Before - Hoping parameters arrive
class OldNode(Node):
    def run(self, **kwargs):
        value = kwargs.get('some_param')  # Might be None

# After - Guaranteed parameters
class NewNode(Node):
    def get_parameters(self):
        return {
            "some_param": NodeParameter(type=str, required=True)
        }

    def run(self, **kwargs):
        value = kwargs['some_param']  # Guaranteed to exist
```

## Troubleshooting

### Symptom: Parameters Not Received

**Check**:
1. Is `get_parameters()` defined and returning parameters?
2. Are parameter names spelled correctly?
3. For Method 3: Is node config empty with all optional params?

**Solution**:
- Define parameters explicitly
- Add minimal config: `{"_init": True}`
- Make at least one parameter required

### Symptom: JSON Parse Errors

**Check**:
1. Is data coming from AsyncSQLDatabaseNode?
2. Are you accessing `.get()` on a string?

**Solution**:
```python
if isinstance(data, str):
    import json
    data = json.loads(data)
```

### Symptom: "Missing required inputs" Error

**Check**:
1. Does the contract require this parameter?
2. Is it being provided via config, connection, or runtime?

**Solution**:
- Check the node's parameter contract
- Provide required parameters via one of the three methods

## Best Practices Summary

1. **Explicit Over Implicit**: Always declare parameters
2. **Security First**: Use contracts to validate inputs
3. **Handle JSON**: Parse database JSON explicitly
4. **Test Reliably**: Use Method 1 for tests
5. **Document Parameters**: Use descriptions in NodeParameter
6. **Validate Business Logic**: Check requirements in run()
7. **Use Type Hints**: Enable IDE support and validation

## Version History

- **v3.0 (2025-07-22)**: Consolidated all parameter passing documentation
- **v2.0**: Added enterprise patterns and security considerations
- **v1.0**: Initial parameter passing guide

---

**Remember**: The SDK's explicit parameter requirement is a feature that protects your production systems from security vulnerabilities. Embrace it as a best practice, not a limitation.
