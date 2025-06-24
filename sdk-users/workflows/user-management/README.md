# User Management Workflows

This directory contains production-ready user management workflows built with Kailash SDK.

## 📚 Documentation

- **[User Management Implementation Guide](../../user-management-implementation-guide.md)** - Complete guide with examples
- **[Admin Nodes Bug Report](../../admin-nodes-bug-report.md)** - Known issues and workarounds
- **[Admin Nodes Guide](../../nodes/admin-nodes-guide.md)** - Node reference documentation

## 🎯 Complete Solutions

### 1. **full_user_management_system.py**
Complete user management system with Django admin feature parity:
- User CRUD operations
- Role-based access control (RBAC)
- JWT authentication
- Audit logging
- Bulk operations
- Search and filtering

### 2. **user_management_enterprise_gateway.py**
Enterprise gateway with real-time communication:
- WebSocket/SSE streaming
- Multi-tenant session management
- AI chat integration
- REST API endpoints
- Real-time notifications

### 3. **user_onboarding_enterprise.py**
Enterprise user onboarding workflow:
- Multi-step onboarding process
- Department assignment
- Role provisioning
- Welcome emails
- Training assignments

## 🎬 Scenario-Based Examples

### 4. **scenario_user_lifecycle.py**
Complete user lifecycle management:
- New employee onboarding
- Role transitions
- Department transfers
- User offboarding
- Audit trail

### 5. **scenario_security_operations.py**
Security-focused operations:
- Threat detection
- Access reviews
- Permission audits
- Compliance reporting
- Incident response

### 6. **scenario_compliance_audit.py**
Compliance and audit workflows:
- GDPR compliance
- Access reports
- Permission validation
- Audit logging
- Data retention

## 🔧 Quick Start

```python
# Basic user creation
from kailash.nodes.admin.user_management import UserManagementNode

user_node = UserManagementNode()
result = user_node.execute(
    operation="create_user",
    tenant_id="your_tenant",
    database_config={
        "connection_string": "postgresql://user:pass@localhost:5432/db",
        "database_type": "postgresql"
    },
    user_data={
        "email": "user@example.com",
        "username": "johndoe",
        "password": "SecurePass123!",
        "attributes": {"department": "Engineering"}
    }
)
```

## ⚠️ Known Issues

The admin nodes have datetime serialization bugs. Workarounds:

1. **Use the patched nodes** with `parse_datetime` and `format_datetime` helpers
2. **Use PythonCodeNode** for custom implementations
3. **Check bug report** for latest status

## 📊 Performance

Based on integration testing:
- User Creation: ~50ms per user
- Role Assignment: ~10ms per assignment
- Search Operations: <100ms for most queries
- Concurrent Support: 20+ operations

## 🧪 Testing

```bash
# Run integration tests
pytest tests/integration/apps/user_management/ -v

# Run E2E tests with personas
pytest tests/e2e/apps/user_management/ -v
```

## 📋 Next Steps

1. Review the [Implementation Guide](../../user-management-implementation-guide.md)
2. Check [Bug Report](../../admin-nodes-bug-report.md) for known issues
3. Run the examples with your database configuration
4. Customize for your specific requirements

---

*Last Updated: June 2025*
