# Access Control & Multi-Tenancy

## Basic Setup

```python
from kailash import Workflow
from kailash.access_control import UserContext, AccessControlManager
from kailash.runtime.access_controlled import AccessControlledRuntime

# Define user context
user = UserContext(
    user_id="user_001",
    tenant_id="company_abc",
    email="analyst@company.com",
    roles=["analyst", "viewer"]
)

# Create secure runtime
secure_runtime = AccessControlledRuntime(user_context=user)

# Execute with automatic permission checks
results, run_id = secure_runtime.execute(workflow)

```

## Access Control Strategies

### Role-Based Access Control (RBAC)
```python
# Configure RBAC
access_manager = AccessControlManager(strategy="rbac")

# Define role permissions
access_manager.add_role_permission("analyst", "read", "financial_data")
access_manager.add_role_permission("analyst", "write", "reports")
access_manager.add_role_permission("admin", "*", "*")  # Full access

# Apply to runtime
secure_runtime = AccessControlledRuntime(
    user_context=user,
    access_manager=access_manager
)

```

### Attribute-Based Access Control (ABAC)
```python
# Configure ABAC with policies
access_manager = AccessControlManager(strategy="abac")

# Define attribute policies
access_manager.add_policy({
    "name": "department_access",
    "effect": "allow",
    "conditions": {
        "user.department": "${resource.department}",
        "user.clearance_level": {">=>": "${resource.sensitivity}"}
    }
})

```

### Hybrid Strategy
```python
# Combine RBAC and ABAC
access_manager = AccessControlManager(strategy="hybrid")

# RBAC for base permissions
access_manager.add_role_permission("analyst", "read", "data")

# ABAC for fine-grained control
access_manager.add_policy({
    "name": "tenant_isolation",
    "effect": "deny",
    "conditions": {
        "user.tenant_id": {"!=": "${resource.tenant_id}"}
    }
})

```

## Multi-Tenant Patterns

### Tenant Isolation
```python
from kailash.nodes.data import SQLDatabaseNode

# Automatic tenant filtering
workflow.add_node("db_query", SQLDatabaseNode(
    connection_string="postgresql://user:pass@localhost:5432/mydb"
),
    query="SELECT * FROM customers WHERE tenant_id = :tenant_id",
    parameters={"tenant_id": "${user.tenant_id}"}  # Injected from context
)

# Runtime enforces tenant isolation
for tenant_user in users:
    runtime = AccessControlledRuntime(user_context=tenant_user)
    results, _ = runtime.execute(workflow)
    # Each tenant only sees their data

```

### Cross-Tenant Admin Access
```python
# Admin user with cross-tenant access
admin_user = UserContext(
    user_id="admin_001",
    tenant_id="system",
    roles=["super_admin"],
    attributes={"cross_tenant_access": True}
)

# Policy for cross-tenant access
access_manager.add_policy({
    "name": "admin_override",
    "effect": "allow",
    "conditions": {
        "user.attributes.cross_tenant_access": True,
        "user.roles": {"contains": "super_admin"}
    }
})

```

## Security Patterns

### Data Encryption
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

# Encrypt sensitive data per tenant
workflow = Workflow("example", name="Example")
workflow.add_node("encrypt", EncryptionNode(),
    encryption_key="${tenant.encryption_key}",
    algorithm="AES-256-GCM"
)

```

### Audit Logging
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

# Automatic audit trail
secure_runtime = AccessControlledRuntime(
    user_context=user,
    audit_enabled=True,
    audit_handler=AuditLogger()
)

# All operations logged with user context
runtime = LocalRuntime()
workflow.execute(workflow)

```

## Common Patterns

### Dynamic Permission Checking
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

def check_data_access(user, resource) -> bool:
    """Custom permission logic."""
    if user.tenant_id != resource.get("tenant_id"):
        return False

    if "confidential" in resource.get("tags", []):
        return "senior_analyst" in user.roles

    return True

# Apply in workflow
workflow = Workflow("example", name="Example")
workflow.add_node("filter", FilterNode(),
    filter_function=lambda item: check_data_access(user, item)
)

```

### Resource-Level Permissions
```python
# Check permissions per resource
for record in data:
    if access_manager.check_permission(
        user_context=user,
        action="read",
        resource=record
    ):
        process_record(record)

```

## Common Pitfalls

1. **Forgetting Tenant Context**: Always pass user context to runtime
2. **Hardcoded Tenant IDs**: Use context variables, not literals
3. **Missing Audit Trail**: Enable audit_enabled for compliance
4. **Overly Permissive Roles**: Start restrictive, add permissions as needed

## Next Steps
- [Enterprise gateway patterns](../middleware/agent-ui-communication.md)
- [Security workflows](../workflows/by-pattern/enterprise-security/)
