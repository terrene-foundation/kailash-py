# Access Control Examples for Kailash SDK

This directory contains comprehensive examples demonstrating the unified access control features of the Kailash Python SDK.

## Overview (Updated Session 066)

The Kailash SDK provides a **unified access control interface** supporting multiple strategies:
- **Role-Based Access Control (RBAC)** - Traditional role-based permissions
- **Attribute-Based Access Control (ABAC)** - Fine-grained attribute conditions
- **Hybrid Mode** - Combine RBAC and ABAC for maximum flexibility
- **Single Interface** - Use `AccessControlManager(strategy="abac")` for any mode
- **Node-Level Permissions** - Control who can execute specific nodes
- **Output Masking** - Hide sensitive fields based on user attributes
- **Multi-Tenant Isolation** - Complete data separation between organizations
- **Backward Compatibility** - Access control is completely optional

## Key Features

### 1. Opt-In Security
- Access control is **OFF by default**
- Existing workflows continue to work unchanged
- Enable access control only where needed

### 2. Transparent Integration
- Use `LocalRuntime` for no access control (existing behavior)
- Use `AccessControlledRuntime` to enforce permissions
- Same API, different security levels

### 3. Fine-Grained Control
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Node-level permissions
NodePermission.EXECUTE      # Can run the node
NodePermission.READ_OUTPUT  # Can see outputs
NodePermission.WRITE_INPUT  # Can provide inputs
NodePermission.SKIP         # Node is skipped
NodePermission.MASK_OUTPUT  # Sensitive fields hidden

# Workflow-level permissions
WorkflowPermission.VIEW     # Can see workflow
WorkflowPermission.EXECUTE  # Can run workflow
WorkflowPermission.MODIFY   # Can edit workflow
WorkflowPermission.DELETE   # Can delete workflow
WorkflowPermission.SHARE    # Can share with others
WorkflowPermission.ADMIN    # Full control

```

## Example Files

### 1. `access_control_comprehensive.py`
Complete demonstration of all access control features:
- Node-level access control
- Workflow-level permissions
- Permission-based routing
- Output masking
- Custom access rules
- Multi-tenant isolation

### 2. `access_control_simple.py`
Practical example of a data processing workflow:
- Admin users can see and export all data
- Analysts can process but see masked sensitive fields
- Viewers only see summary statistics

### 3. `access_control_backward_compatible.py`
Shows how access control maintains backward compatibility:
- Existing workflows work unchanged
- Mix ACL and non-ACL nodes
- Gradual migration path

### 4. `test_jwt_auth.py`
JWT authentication example:
- User registration and login
- Token generation and refresh
- API key authentication
- Tenant isolation

### 5. `test_rbac_permissions.py`
Role-based access control testing:
- Different user roles
- Permission inheritance
- Cross-tenant access prevention

## NEW: Unified Access Control Interface (Session 066)

The SDK now provides a single, unified `AccessControlManager` class that supports all access control strategies:

### Strategy Selection
```python
from kailash.access_control import AccessControlManager

# RBAC - Role-based access control
rbac_manager = AccessControlManager(strategy="rbac")

# ABAC - Attribute-based access control
abac_manager = AccessControlManager(strategy="abac")

# Hybrid - Combine RBAC and ABAC
hybrid_manager = AccessControlManager(strategy="hybrid")  # Default

```

### ABAC Example with Helper Functions
```python
from kailash.access_control import (
    AccessControlManager,
    create_attribute_condition,
    create_complex_condition,
    UserContext
)

# Create manager with ABAC strategy
manager = AccessControlManager(strategy="abac")

# Simple attribute condition
dept_condition = create_attribute_condition(
    path="user.attributes.department",
    operator="hierarchical_match",
    value="finance"
)

# Complex condition with AND/OR logic
complex_condition = create_complex_condition(
    operator="and",
    conditions=[
        create_attribute_condition("user.attributes.security_clearance", "security_level_meets", "secret"),
        create_attribute_condition("user.attributes.region", "in", ["US", "EU"])
    ]
)

```

### Database Integration with Access Control
```python
from kailash.nodes.data import AsyncSQLDatabaseNode

# Create database node with access control
db_node = AsyncSQLDatabaseNode(
    name="sensitive_query",
    query="SELECT * FROM financial_data",
    access_control_manager=manager  # Pass the unified manager
)

```

## Quick Start

### Basic Usage (No Access Control)
```python
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime

# Your existing code works unchanged
workflow = Workflow()
# ... add nodes ...
runtime = LocalRuntime()
result = runtime.execute(workflow)

```

### With Access Control
```python
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.access_control import UserContext, AccessControlManager

# Create user context
user = UserContext(
    user_id="user-001",
    tenant_id="tenant-001",
    email="user@example.com",
    roles=["analyst"],
    attributes={
        "department": "finance.trading",
        "security_clearance": "secret",
        "region": "US"
    }
)

# Create unified access control manager
manager = AccessControlManager(strategy="abac")

# Use access-controlled runtime
runtime = AccessControlledRuntime(user, access_control_manager=manager)
result = runtime.execute(workflow)  # Same API!

```

### Adding Access Control to a Node
```python
from kailash.nodes.base_with_acl import add_access_control

# Take any existing node
node = PythonCodeNode(...)

# Add access control
secure_node = add_access_control(
    node,
    enable_access_control=True,
    required_permission=NodePermission.EXECUTE,
    mask_output_fields=["ssn", "credit_card"]
)

```

## Access Control Architecture

```
┌─────────────────┐
│   User Context  │
│  (roles, perms) │
└────────┬────────┘
         │
┌────────▼────────┐
│ Access Control  │
│    Manager      │
└────────┬────────┘
         │
┌────────▼────────┐     ┌──────────────┐
│ AccessControlled│────►│   Workflow   │
│    Runtime      │     │              │
└─────────────────┘     └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │ ACL-Enabled  │
                        │    Nodes     │
                        └──────────────┘
```

## Common Patterns

### 1. Sensitive Data Processing
```python
# Mask sensitive fields for non-admin users
processor = add_access_control(
    data_processor_node,
    mask_output_fields=["ssn", "credit_card", "bank_account"]
)

```

### 2. Admin-Only Operations
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Only admins can export data
exporter = add_access_control(
    csv_writer_node,
    required_permission=NodePermission.EXECUTE,
    node_id="export_sensitive_data"
)

# Add rule for admin role
acm.add_rule(PermissionRule(
    resource_id="export_sensitive_data",
    permission=NodePermission.EXECUTE,
    roles=["admin"]
))

```

### 3. Conditional Execution Paths
```python
# High-privilege path
detailed_analysis = add_access_control(
    complex_ml_node,
    fallback_node="simple_analysis"  # Redirect low-privilege users
)

```

## Testing Access Control

Run the examples:
```bash
# Simple example
python access_control_simple.py

# Comprehensive examples
python access_control_comprehensive.py

# Test backward compatibility
python access_control_backward_compatible.py

# Run tests
pytest test_access_control_examples.py -v
```

## Security Best Practices

1. **Principle of Least Privilege** - Grant minimum necessary permissions
2. **Defense in Depth** - Use multiple layers of security
3. **Audit Logging** - All access attempts are logged
4. **Fail-Safe Defaults** - Deny access unless explicitly allowed
5. **Tenant Isolation** - Complete separation of data between tenants

## Migration Guide

To add access control to existing workflows:

1. **No changes needed** initially - existing code works as-is
2. **Identify sensitive nodes** that need protection
3. **Wrap sensitive nodes** with `add_access_control()`
4. **Define access rules** using AccessControlManager
5. **Switch to AccessControlledRuntime** when ready
6. **Test thoroughly** with different user roles

## Support

For questions or issues with access control:
- Check the examples in this directory
- Review the test cases
- See the main SDK documentation
- File issues on GitHub
