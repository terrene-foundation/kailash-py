# ADR-0035: Access Control and Authentication Architecture

## Status
Accepted (2025-06-05)

## Context
The Kailash SDK needed a comprehensive access control and authentication system to support production deployments with multi-tenancy, role-based permissions, and secure workflow execution. The system needed to be:

1. **Optional by default** - Existing workflows must continue to work unchanged
2. **Transparent** - No changes required to existing node implementations
3. **Fine-grained** - Support both workflow-level and node-level permissions
4. **Multi-tenant** - Complete isolation between different organizations
5. **JWT-compatible** - Standard authentication for web applications
6. **Data masking** - Hide sensitive fields from unauthorized users

## Decision
We will implement a layered access control architecture with the following components:

### 1. Authentication Layer
- **JWT Authentication**: Standard bearer tokens with access/refresh token pattern
- **Multi-tenant Architecture**: Complete tenant isolation using tenant_id
- **Role-Based Access Control (RBAC)**: Admin, Editor, Viewer roles with permissions
- **API Key Authentication**: Alternative authentication for service accounts

### 2. Access Control Layer
```python
# Core Components
- UserContext: Contains user_id, tenant_id, email, roles
- AccessControlManager: Centralized permission checking
- PermissionRule: Defines who can do what on which resources
- AccessDecision: Result of permission evaluation with masking info
```

### 3. Runtime Layer
```python
# Two runtime options
- LocalRuntime: No access control (existing behavior)
- AccessControlledRuntime: Enforces permissions transparently
```

### 4. Node-Level Integration
```python
# Optional access control for nodes
add_access_control(node, 
    enable_access_control=True,
    required_permission=NodePermission.EXECUTE,
    node_id="unique_id",
    mask_output_fields=["ssn", "phone"]
)
```

## Architecture Components

### Permission System
```python
# Workflow Permissions
WorkflowPermission.VIEW      # Can see workflow
WorkflowPermission.EXECUTE   # Can run workflow  
WorkflowPermission.MODIFY    # Can edit workflow
WorkflowPermission.DELETE    # Can delete workflow
WorkflowPermission.SHARE     # Can share with others
WorkflowPermission.ADMIN     # Full control

# Node Permissions  
NodePermission.EXECUTE       # Can run the node
NodePermission.READ_OUTPUT   # Can see outputs
NodePermission.WRITE_INPUT   # Can provide inputs
NodePermission.SKIP          # Node is skipped
NodePermission.MASK_OUTPUT   # Sensitive fields hidden
```

### User Context Structure
```python
@dataclass
class UserContext:
    user_id: str
    tenant_id: str  
    email: str
    roles: List[str]
    attributes: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
```

### Permission Rules
```python
@dataclass
class PermissionRule:
    id: str
    resource_type: str  # "workflow" or "node"
    resource_id: str    # workflow_id or node_id
    permission: Union[WorkflowPermission, NodePermission]
    effect: PermissionEffect  # ALLOW or DENY
    
    # Targeting
    user_id: Optional[str] = None      # Specific user
    role: Optional[str] = None         # Any user with role
    tenant_id: Optional[str] = None    # All users in tenant
    
    # Conditions
    conditions: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    priority: int = 0
```

## Implementation Details

### 1. Backward Compatibility
```python
# Existing code works unchanged
workflow = Workflow(workflow_id="example", name="Example")
reader = CSVReaderNode(file_path="data.csv")
workflow.add_node("reader", reader)

# Run without access control
runtime = LocalRuntime()
result = runtime.execute(workflow)

# Run with access control (same API)
user = UserContext(user_id="user1", tenant_id="tenant1", 
                   email="user@example.com", roles=["analyst"])
ac_runtime = AccessControlledRuntime(user)
result = ac_runtime.execute(workflow)  # Same call!
```

### 2. Node-Level Access Control
```python
# Add access control to sensitive nodes
sensitive_processor = add_access_control(
    PythonCodeNode(name="processor", code="..."),
    enable_access_control=True,
    required_permission=NodePermission.EXECUTE,
    node_id="process_sensitive_data",
    mask_output_fields=["ssn", "credit_card"]  # Masked for non-admin
)
```

### 3. Data Masking
```python
# Automatic field masking based on user role
original_output = {"name": "John", "ssn": "123-45-6789", "balance": 1500}

# Admin sees everything
admin_output = {"name": "John", "ssn": "123-45-6789", "balance": 1500}

# Analyst sees masked sensitive fields  
analyst_output = {"name": "John", "ssn": "***-**-6789", "balance": 1500}

# Viewer might see only summary
viewer_output = {"total_records": 1, "average_balance": 1500}
```

### 4. Multi-Tenant Isolation
```python
# Users in different tenants cannot access each other's resources
user_a = UserContext(user_id="u1", tenant_id="tenant-a", ...)
user_b = UserContext(user_id="u2", tenant_id="tenant-b", ...)

# user_a can only access workflows in tenant-a
# user_b can only access workflows in tenant-b
# Complete data isolation enforced at runtime
```

## Security Considerations

### 1. Fail-Safe Defaults
- Access is **denied by default** unless explicitly allowed
- Missing permissions result in access denial, not execution
- Unknown users/tenants are rejected

### 2. Defense in Depth
- Authentication at API layer (JWT validation)
- Authorization at runtime layer (permission checking)
- Data masking at output layer (field-level security)
- Tenant isolation at all layers

### 3. Audit Logging
- All access attempts are logged with user context
- Permission decisions are recorded for compliance
- Failed access attempts trigger security alerts

### 4. Production Hardening
- Rate limiting on authentication endpoints
- Token expiration and refresh mechanisms
- Encrypted token storage and transmission
- Session management and cleanup

## Benefits

### 1. Developer Experience
- **Zero breaking changes** - Existing code works unchanged
- **Opt-in security** - Add access control only where needed
- **Simple API** - Same runtime interface with/without security
- **Clear permissions** - Explicit, auditable permission rules

### 2. Enterprise Features
- **Multi-tenancy** - Complete tenant isolation
- **RBAC** - Standard role-based access control
- **Data security** - Field-level masking and protection
- **Compliance** - Audit trails and access logging

### 3. Operational Benefits
- **Gradual migration** - Add security incrementally
- **Performance** - Minimal overhead when disabled
- **Scalability** - Distributed permission checking
- **Monitoring** - Built-in security metrics

## Implementation Status

### Completed ✅
- [x] Core authentication system with JWT
- [x] Multi-tenant architecture with complete isolation
- [x] Role-based access control (Admin, Editor, Viewer)
- [x] Node-level access control with permission checking
- [x] Data masking for sensitive fields
- [x] AccessControlledRuntime with transparent security
- [x] Backward compatibility with existing workflows
- [x] Comprehensive examples and documentation
- [x] Security testing and validation

### Future Enhancements 🔄
- [ ] Dynamic permission evaluation based on data content
- [ ] Time-based access restrictions (business hours only)
- [ ] Delegation and impersonation support
- [ ] Integration with external identity providers (SAML, LDAP)
- [ ] Advanced audit and compliance features
- [ ] Performance optimization for large-scale deployments

## Examples

See the following files for comprehensive demonstrations:
- `examples/integration_examples/access_control_demo.py` - Simple working demo
- `examples/integration_examples/access_control_simple.py` - Basic role-based demo  
- `examples/integration_examples/access_control_consolidated.py` - Full JWT/RBAC demo
- `examples/studio_examples/test_jwt_auth.py` - JWT authentication testing
- `examples/studio_examples/test_rbac_permissions.py` - RBAC testing

## Related ADRs
- ADR-0032: Production Security Architecture
- ADR-0033: Workflow Studio Multi-Tenant Architecture  
- ADR-0034: AI Assistant Architecture

---
**Author**: Claude Code  
**Date**: 2025-06-05  
**Supersedes**: None  
**Status**: Accepted and Implemented