# Admin Tool Framework

The Kailash SDK provides a comprehensive admin tool framework for enterprise deployments, combining powerful backend nodes with production-ready React UI components.

## Overview

The admin framework provides:
- **User & Role Management**: Complete CRUD operations with hierarchical roles
- **Permission Control**: Fine-grained ABAC-based permission management
- **Audit Logging**: Comprehensive audit trails with compliance support
- **Security Monitoring**: Real-time security event tracking and alerting
- **Multi-tenant Support**: Isolated tenant management and administration
- **React UI Components**: Production-ready admin interfaces

## Core Admin Nodes

### UserManagementNode
Manages user accounts with full ABAC integration:
```python
from kailash.core.nodes.admin import UserManagementNode

# Create user management node
user_node = UserManagementNode(
    name="user_manager",
    operation="create",  # create, read, update, delete, list
    tenant_id="default"
)

# In a workflow
workflow.add_node(user_node)
workflow.run({
    "user_data": {
        "email": "john.doe@example.com",
        "username": "johndoe",
        "roles": ["employee", "analyst"],
        "attributes": {
            "department": "finance",
            "security_level": 3
        }
    }
})
```

### RoleManagementNode
Manages hierarchical roles with permission inheritance:
```python
from kailash.core.nodes.admin import RoleManagementNode

role_node = RoleManagementNode(
    name="role_manager",
    operation="assign_permissions"
)

workflow.run({
    "role_id": "senior_analyst",
    "permissions": [
        "data:read",
        "data:write",
        "reports:create"
    ],
    "parent_role": "analyst"
})
```

### PermissionCheckNode
Evaluates complex permission conditions:
```python
from kailash.core.nodes.admin import PermissionCheckNode

permission_node = PermissionCheckNode(
    name="permission_checker",
    resource="financial_report",
    action="read"
)

# Checks user permissions with ABAC conditions
workflow.run({
    "user_id": "user123",
    "resource_attributes": {
        "department": "finance",
        "sensitivity": "high",
        "region": "US"
    }
})
```

### AuditLogNode
Records comprehensive audit trails:
```python
from kailash.core.nodes.admin import AuditLogNode

audit_node = AuditLogNode(
    name="audit_logger",
    compliance_tags=["SOC2", "HIPAA"]
)

workflow.run({
    "event_type": "data_access",
    "user_id": "user123",
    "resource": "patient_records",
    "action": "view",
    "metadata": {
        "ip_address": "192.168.1.1",
        "session_id": "abc123"
    }
})
```

### SecurityEventNode
Tracks security events in real-time:
```python
from kailash.core.nodes.admin import SecurityEventNode

security_node = SecurityEventNode(
    name="security_monitor",
    alert_threshold="high"
)

workflow.run({
    "event_type": "failed_login",
    "severity": "medium",
    "user_id": "user123",
    "details": "Multiple failed login attempts",
    "metadata": {
        "attempts": 5,
        "time_window": "5m"
    }
})
```

## Admin Workflows

### User Onboarding Workflow
Complete user onboarding with validation and notifications:
```python
from kailash.core.workflow import Workflow
from kailash.core.nodes.admin import UserManagementNode, RoleManagementNode, AuditLogNode

def create_user_onboarding_workflow():
    workflow = Workflow(name="user_onboarding")
    
    # Validate user data
    validate = PythonCodeNode(
        name="validate_user",
        code="""
# Validate email, check duplicates, etc.
result = {"valid": True, "user_data": input_data}
"""
    )
    
    # Create user
    create_user = UserManagementNode(
        name="create_user",
        operation="create"
    )
    
    # Assign default role
    assign_role = RoleManagementNode(
        name="assign_role",
        operation="assign_role"
    )
    
    # Log onboarding
    audit = AuditLogNode(
        name="audit_onboarding",
        compliance_tags=["user_management"]
    )
    
    # Connect nodes
    workflow.add_nodes([validate, create_user, assign_role, audit])
    workflow.connect(validate.name, create_user.name, {"user_data": "user_data"})
    workflow.connect(create_user.name, assign_role.name, {"user_id": "user_id"})
    workflow.connect(assign_role.name, audit.name)
    
    return workflow
```

### Permission Assignment Workflow
Manage permission changes with approval:
```python
def create_permission_assignment_workflow():
    workflow = Workflow(name="permission_assignment")
    
    # Check current permissions
    check_current = PermissionCheckNode(
        name="check_current_permissions"
    )
    
    # Validate permission change
    validate = PythonCodeNode(
        name="validate_change",
        code="""
# Ensure no privilege escalation
# Check approval requirements
result = {"approved": True, "changes": input_data}
"""
    )
    
    # Update permissions
    update = RoleManagementNode(
        name="update_permissions",
        operation="update_permissions"
    )
    
    # Audit the change
    audit = AuditLogNode(
        name="audit_permission_change",
        compliance_tags=["access_control"]
    )
    
    # Connect workflow
    workflow.add_nodes([check_current, validate, update, audit])
    # ... connections
    
    return workflow
```

## React UI Components

The framework includes production-ready React components:

### UserManagement Component
```typescript
import { UserManagement } from '@kailash/admin-ui';

function AdminPanel() {
  return (
    <UserManagement 
      tenantId="default"
      onUserCreated={(user) => console.log('User created:', user)}
    />
  );
}
```

### SecurityDashboard Component
```typescript
import { SecurityDashboard } from '@kailash/admin-ui';

function SecurityMonitoring() {
  return (
    <SecurityDashboard 
      refreshInterval={30000}  // 30 seconds
      alertThreshold="medium"
    />
  );
}
```

### PermissionMatrix Component
```typescript
import { PermissionMatrix } from '@kailash/admin-ui';

function PermissionManagement() {
  return (
    <PermissionMatrix 
      onPermissionChange={(roleId, permissionId, granted) => {
        // Handle permission update
      }}
    />
  );
}
```

## Integration with ABAC

The admin framework fully integrates with Session 065's ABAC system:

```python
# Configure ABAC for admin operations
from kailash.security import EnhancedAccessControlManager

access_manager = EnhancedAccessControlManager()

# Define admin-specific policies
access_manager.add_policy({
    "policy_id": "admin_user_management",
    "description": "Admin can manage users in their department",
    "conditions": [
        {
            "attribute": "user.role",
            "operator": "equals",
            "value": "admin"
        },
        {
            "attribute": "user.department",
            "operator": "equals",
            "value": "$resource.department"
        }
    ],
    "effect": "allow"
})

# Use in admin nodes
user_node = UserManagementNode(
    name="user_manager",
    access_manager=access_manager
)
```

## Production Architecture

The admin framework is designed for enterprise deployments:

### Distributed Architecture
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Admin UI      │────▶│   API Gateway   │────▶│  Admin Nodes    │
│   (React)       │     │   (FastAPI)     │     │  (Workflows)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   PostgreSQL    │     │     Redis       │
                        │  (Persistence)  │     │   (Sessions)    │
                        └─────────────────┘     └─────────────────┘
```

### Security Considerations
- All admin operations require authentication
- ABAC policies enforce fine-grained access control
- Audit logs capture all administrative actions
- Security events trigger real-time alerts
- Data masking protects sensitive information

## Testing with QA Agents

The framework includes comprehensive QA testing:

```python
from examples.feature_examples.integrations.admin import comprehensive_qa_suite

# Run full QA test suite
comprehensive_qa_suite.main()

# Output includes:
# - Functional test results
# - Security vulnerability assessment
# - Performance metrics
# - Recommendations for improvements
```

## Best Practices

1. **Always use admin nodes** instead of direct database access
2. **Enable audit logging** for all administrative operations
3. **Configure ABAC policies** before deployment
4. **Use the React components** for consistent UI
5. **Run QA tests** before production deployment
6. **Monitor security events** continuously
7. **Implement approval workflows** for sensitive operations

## Example: Complete Admin Setup

```python
from kailash.core.workflow import Workflow
from kailash.core.nodes.admin import *
from kailash.security import EnhancedAccessControlManager

# 1. Configure ABAC
access_manager = EnhancedAccessControlManager()
access_manager.load_policies("admin_policies.json")

# 2. Create admin workflow
admin_workflow = Workflow(name="admin_operations")

# 3. Add admin nodes
user_mgmt = UserManagementNode("user_mgmt", access_manager=access_manager)
role_mgmt = RoleManagementNode("role_mgmt", access_manager=access_manager)
audit = AuditLogNode("audit", compliance_tags=["SOC2"])

admin_workflow.add_nodes([user_mgmt, role_mgmt, audit])

# 4. Deploy with API
from kailash.api import WorkflowAPI

api = WorkflowAPI()
api.register_workflow("admin", admin_workflow)
api.start(port=8000)

# 5. Use React UI
# In your React app:
# import { AdminLayout } from '@kailash/admin-ui';
# <AdminLayout apiUrl="http://localhost:8000" />
```

The admin tool framework provides everything needed for enterprise-grade administration of Kailash SDK deployments.