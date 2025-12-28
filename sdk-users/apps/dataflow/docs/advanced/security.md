# DataFlow Security Guide

Comprehensive security guide for DataFlow applications including the **6-Level Write Protection System**.

## Overview

DataFlow provides enterprise-grade security with a multi-layered write protection system that integrates directly with Core SDK workflow execution. This includes authentication, authorization, encryption, audit logging, and comprehensive write protection.

## 6-Level Write Protection System

DataFlow implements a comprehensive write protection system with six protection levels:

### Protection Levels

```python
from dataflow.core.protection import ProtectionLevel

# Available protection levels:
ProtectionLevel.OFF     # No protection
ProtectionLevel.WARN    # Log warnings but allow operations
ProtectionLevel.BLOCK   # Block operations with detailed errors
ProtectionLevel.AUDIT   # Block and create audit entries
```

### Level 1: Global Protection

```python
from dataflow import DataFlow
from dataflow.core.protection import GlobalProtection, ProtectionLevel

# Enable global write protection
global_protection = GlobalProtection(
    default_level=ProtectionLevel.BLOCK,
    maintenance_mode=True,
    allowed_users={"admin", "system"}
)

db = DataFlow(
    "postgresql://user:pass@localhost/db",
    protection=global_protection
)
```

### Level 2: Connection Protection

```python
# Connection-level protection based on time windows
from dataflow.core.protection import TimeWindow
from datetime import time

# Protect during business hours
business_hours = TimeWindow(
    start_time=time(9, 0),   # 9 AM
    end_time=time(17, 0),    # 5 PM
    days_of_week={0, 1, 2, 3, 4}  # Monday-Friday
)

db = DataFlow(
    "postgresql://user:pass@localhost/db",
    write_protection_window=business_hours
)
```

### Level 3: Model Protection

```python
from dataflow.core.protection import ModelProtection, OperationType

# Model-level protection configuration
user_protection = ModelProtection(
    model_name="User",
    protection_level=ProtectionLevel.AUDIT,
    allowed_operations={OperationType.READ, OperationType.CREATE},
    reason="User model requires approval for modifications"
)

@db.model
class User:
    name: str
    email: str

    __dataflow__ = {
        'protection': user_protection
    }
```

### Level 4: Operation Protection

```python
# Operation-specific protection
from dataflow.core.protection import OperationType

@db.model
class CriticalData:
    value: str

    __dataflow__ = {
        'protection': {
            'bulk_operations': ProtectionLevel.BLOCK,  # No bulk operations
            'delete_operations': ProtectionLevel.AUDIT,  # Audit all deletes
        }
    }
```

### Level 5: Field Protection

```python
from dataflow.core.protection import FieldProtection

@db.model
class Employee:
    name: str
    email: str
    salary: float
    ssn: str

    __dataflow__ = {
        'protection': {
            'fields': [
                FieldProtection(
                    field_name="salary",
                    protection_level=ProtectionLevel.AUDIT,
                    allowed_operations={OperationType.READ}
                ),
                FieldProtection(
                    field_name="ssn",
                    protection_level=ProtectionLevel.BLOCK,
                    reason="SSN is permanently read-only"
                )
            ]
        }
    }
```

### Level 6: Runtime Protection

```python
# Runtime protection with custom conditions
def protect_critical_records(context):
    """Custom protection logic."""
    if context.get('record_count', 0) > 1000:
        return False  # Block operations on large datasets
    return True

@db.model
class Order:
    amount: float
    status: str

    __dataflow__ = {
        'protection': {
            'conditions': [protect_critical_records],
            'runtime_checks': True
        }
    }
```

## Authentication

### Basic Authentication

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow import DataFlow, AuthConfig

# Configure authentication
auth_config = AuthConfig(
    provider="database",  # or "ldap", "oauth2", "saml"
    password_hash="argon2",  # Strong password hashing
    session_timeout=3600,  # 1 hour
    require_2fa=True
)

db = DataFlow(auth_config=auth_config)

# User model with security features
@db.model
class User:
    id: int
    email: str
    password_hash: str
    totp_secret: str
    failed_login_attempts: int
    locked_until: datetime
    last_login: datetime

    __dataflow__ = {
        'security': {
            'sensitive_fields': ['password_hash', 'totp_secret'],
            'audit_fields': ['email', 'last_login'],
            'encrypt_fields': ['totp_secret']
        }
    }
```

### OAuth2 Integration

```python
workflow = WorkflowBuilder()

# OAuth2 authentication flow
workflow.add_node("OAuth2AuthNode", "authenticate", {
    "provider": "google",
    "client_id": ":oauth_client_id",
    "client_secret": ":oauth_client_secret",
    "redirect_uri": "https://app.example.com/auth/callback",
    "scopes": ["email", "profile"],
    "state_validation": True
})

# Validate and create session
workflow.add_node("SessionCreateNode", "create_session", {
    "user_info": ":oauth_user_info",
    "session_duration": 7200,  # 2 hours
    "device_fingerprint": ":device_id",
    "ip_address": ":client_ip"
})
```

### Multi-Factor Authentication

```python
# TOTP-based 2FA
workflow.add_node("TOTPValidationNode", "validate_2fa", {
    "user_id": ":user_id",
    "totp_code": ":user_totp_code",
    "window": 1,  # Allow 1 time step drift
    "rate_limit": {
        "attempts": 3,
        "window": 300  # 5 minutes
    }
})

# Backup codes
workflow.add_node("BackupCodeGeneratorNode", "generate_backup", {
    "user_id": ":user_id",
    "count": 10,
    "code_length": 8,
    "hash_codes": True
})
```

## Authorization

### Role-Based Access Control (RBAC)

```python
# Define roles and permissions
@db.model
class Role:
    id: int
    name: str
    permissions: list[str]

@db.model
class UserRole:
    user_id: int
    role_id: int
    granted_at: datetime
    granted_by: int

# Check permissions in workflow
workflow.add_node("PermissionCheckNode", "check_access", {
    "user_id": ":user_id",
    "required_permissions": ["users.read", "orders.write"],
    "check_mode": "all",  # or "any"
    "on_denied": "throw_403"
})
```

### Attribute-Based Access Control (ABAC)

```python
# Define access policies
access_policies = [
    {
        "name": "owner_can_edit",
        "resource": "document",
        "action": "edit",
        "condition": "resource.owner_id == user.id"
    },
    {
        "name": "department_read",
        "resource": "document",
        "action": "read",
        "condition": "resource.department == user.department"
    },
    {
        "name": "time_based_access",
        "resource": "report",
        "action": "view",
        "condition": "current_time between resource.valid_from and resource.valid_until"
    }
]

workflow.add_node("ABACEnforcerNode", "enforce_policy", {
    "policies": access_policies,
    "user_attributes": ":user_context",
    "resource_attributes": ":resource_context",
    "action": ":requested_action"
})
```

### Row-Level Security

```python
# Automatic row-level filtering
@db.secure_model
class Order:
    id: int
    user_id: int
    total: float
    status: str

    __dataflow__ = {
        'row_security': {
            'read': 'user_id = current_user_id() OR has_role("admin")',
            'write': 'user_id = current_user_id() AND status != "completed"',
            'delete': 'has_role("admin")'
        }
    }

# Apply security in workflows
workflow.add_node("SecureQueryNode", "get_orders", {
    "model": "Order",
    "filter": {"status": "pending"},
    "apply_row_security": True  # Automatically filters by user
})
```

## Encryption

### Data at Rest

```python
# Configure encryption
encryption_config = {
    "algorithm": "AES-256-GCM",
    "key_management": "aws_kms",  # or "vault", "local"
    "key_rotation": "monthly",
    "encrypt_fields": ["ssn", "credit_card", "bank_account"]
}

db = DataFlow(encryption_config=encryption_config)

# Transparent encryption
@db.model
class Customer:
    id: int
    name: str
    ssn: str  # Automatically encrypted
    credit_card: str  # Automatically encrypted

    __dataflow__ = {
        'encryption': {
            'fields': ['ssn', 'credit_card'],
            'search_enabled': ['ssn']  # Enable searching on encrypted field
        }
    }
```

### Data in Transit

```python
# TLS configuration
tls_config = {
    "min_version": "TLS1.3",
    "cipher_suites": [
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256"
    ],
    "client_auth": "required",
    "verify_depth": 2
}

# Database connections with TLS
db_config = DataFlowConfig(
    database_url="postgresql://db.example.com/app",
    ssl_mode="require",
    ssl_cert="/path/to/client-cert.pem",
    ssl_key="/path/to/client-key.pem",
    ssl_ca="/path/to/ca-cert.pem"
)
```

### Field-Level Encryption

```python
workflow.add_node("FieldEncryptionNode", "encrypt_sensitive", {
    "data": ":user_data",
    "fields_to_encrypt": ["ssn", "dob", "salary"],
    "encryption_key_id": "user-data-key-2024",
    "format": "base64"
})

# Searchable encryption
workflow.add_node("SearchableEncryptionNode", "encrypt_searchable", {
    "field": "email",
    "value": ":email",
    "allow_prefix_search": True,
    "allow_wildcard": False
})
```

## Audit Logging

### Comprehensive Audit Trail

```python
# Configure audit logging
audit_config = {
    "enabled": True,
    "log_reads": True,
    "log_writes": True,
    "log_schema_changes": True,
    "exclude_tables": ["sessions", "cache"],
    "storage": "separate_database"  # Don't mix with application data
}

@db.model
class AuditLog:
    id: int
    timestamp: datetime
    user_id: int
    action: str  # CREATE, READ, UPDATE, DELETE
    resource_type: str
    resource_id: str
    changes: dict  # JSON diff of changes
    ip_address: str
    user_agent: str
    request_id: str

    __dataflow__ = {
        'indexes': [
            ['timestamp', 'user_id'],
            ['resource_type', 'resource_id'],
            ['action', 'timestamp']
        ],
        'retention': '7 years',
        'immutable': True  # Prevent modifications
    }
```

### Workflow Audit

```python
workflow.add_node("AuditContextNode", "enable_audit", {
    "audit_level": "detailed",
    "include": [
        "input_parameters",
        "output_results",
        "execution_time",
        "user_context",
        "database_queries"
    ],
    "redact_sensitive": True
})

# Custom audit events
workflow.add_node("AuditEventNode", "log_custom_event", {
    "event_type": "financial_transaction",
    "severity": "high",
    "details": {
        "amount": ":transaction_amount",
        "from_account": ":from_account",
        "to_account": ":to_account",
        "authorization": ":auth_code"
    }
})
```

## SQL Injection Prevention

### Parameterized Queries

```python
# Safe query construction
workflow.add_node("SafeQueryNode", "search_users", {
    "query": "SELECT * FROM users WHERE email = :email AND status = :status",
    "parameters": {
        "email": ":user_email",
        "status": "active"
    },
    "validate_parameters": True
})

# Query builder with automatic escaping
workflow.add_node("QueryBuilderNode", "build_query", {
    "table": "products",
    "select": ["id", "name", "price"],
    "where": {
        "category": ":category",
        "price": {"$between": [":min_price", ":max_price"]}
    },
    "order_by": ["name"],
    "sanitize_all": True
})
```

### Input Validation

```python
# Comprehensive input validation
workflow.add_node("InputValidationNode", "validate_input", {
    "rules": {
        "email": {
            "type": "email",
            "required": True,
            "max_length": 255
        },
        "age": {
            "type": "integer",
            "min": 0,
            "max": 150
        },
        "username": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_]+$",
            "min_length": 3,
            "max_length": 30
        },
        "url": {
            "type": "url",
            "allowed_schemes": ["https"],
            "allowed_domains": ["example.com", "trusted.com"]
        }
    },
    "on_validation_error": "reject_400"
})
```

## Security Headers

### Response Security

```python
workflow.add_node("SecurityHeadersNode", "add_headers", {
    "headers": {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'",
        "Referrer-Policy": "strict-origin-when-cross-origin"
    }
})
```

## Rate Limiting

### API Rate Limiting

```python
workflow.add_node("RateLimiterNode", "check_rate_limit", {
    "identifier": ":user_id",  # or IP address
    "limits": [
        {"requests": 100, "window": "1m"},  # 100 per minute
        {"requests": 1000, "window": "1h"},  # 1000 per hour
        {"requests": 10000, "window": "1d"}  # 10000 per day
    ],
    "on_exceeded": "return_429",
    "custom_limits": {
        "premium_users": {"requests": 10000, "window": "1h"},
        "api_endpoints": {
            "/api/expensive": {"requests": 10, "window": "1m"}
        }
    }
})
```

## Security Testing

### Automated Security Scans

```python
def test_sql_injection():
    """Test SQL injection prevention."""
    malicious_parameters= [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "admin'--",
        "1; SELECT * FROM passwords"
    ]

    for payload in malicious_inputs:
        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "search", {
            "filter": {"name": payload}
        })

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Should not cause errors or return unauthorized data
        assert "error" not in results
        assert len(results.get("search", {}).get("data", [])) == 0

def test_authorization():
    """Test authorization enforcement."""
    # Create users with different roles
    regular_user = create_user(role="user")
    admin_user = create_user(role="admin")

    # Test accessing admin resource as regular user
    with db.authenticate(regular_user):
        workflow = WorkflowBuilder()
        workflow.add_node("AdminResourceNode", "access", {})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        assert results["access"]["error"] == "Forbidden"

    # Test accessing as admin
    with db.authenticate(admin_user):
        results, _ = runtime.execute(workflow.build())
        assert results["access"]["success"] == True
```

## Security Checklist

```python
# Security validation workflow
workflow.add_node("SecurityChecklistNode", "validate_security", {
    "checks": [
        "authentication_enabled",
        "authorization_configured",
        "encryption_at_rest",
        "encryption_in_transit",
        "audit_logging_enabled",
        "rate_limiting_active",
        "sql_injection_prevention",
        "xss_protection",
        "csrf_protection",
        "secure_headers",
        "vulnerability_scanning",
        "penetration_testing"
    ],
    "fail_on_missing": True
})
```

## Best Practices

1. **Defense in Depth**: Multiple layers of security
2. **Least Privilege**: Grant minimum necessary permissions
3. **Encrypt Everything**: Data at rest and in transit
4. **Audit Everything**: Comprehensive logging
5. **Regular Updates**: Keep dependencies updated
6. **Security Testing**: Regular penetration testing
7. **Incident Response**: Have a plan ready

## Next Steps

- **Performance**: [Performance Guide](../production/performance.md)
- **Monitoring**: [Monitoring Guide](monitoring.md)
- **Troubleshooting**: [Troubleshooting Guide](../production/troubleshooting.md)

Security is not optional in DataFlow applications. Implement comprehensive security measures from the start.
