# Security & Encryption

DataFlow provides comprehensive security features including encryption, access control, and threat protection.

## Overview

Security in DataFlow is implemented at multiple layers:
- **Data Encryption**: At-rest and in-transit encryption
- **Access Control**: Role-based and attribute-based access
- **Threat Protection**: SQL injection prevention, rate limiting
- **Audit Trail**: Comprehensive activity logging
- **Compliance**: GDPR, HIPAA, SOC2 support

## Encryption

### Field-Level Encryption

Encrypt sensitive fields automatically:

```python
from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow
from dataflow.fields import Field

db = DataFlow()

@db.model
class PaymentMethod:
    customer_id: int
    # Encrypted fields
    card_number: str = Field(encrypted=True)
    cvv: str = Field(encrypted=True)
    # Regular fields
    card_type: str
    expires: str
```

### Configuration Options

```python
db = DataFlow(
    encryption={
        "enabled": True,
        "algorithm": "AES-256-GCM",  # or "RSA-4096"
        "key_source": "env",  # or "kms", "vault"
        "key_rotation_days": 90,
        "encrypt_at_rest": True,
        "encrypt_in_transit": True
    }
)
```

### Key Management

```python
# Environment-based keys (development)
# DATAFLOW_ENCRYPTION_KEY=base64_encoded_key

# AWS KMS integration (production)
db = DataFlow(
    encryption={
        "key_source": "kms",
        "kms_key_id": "arn:aws:kms:us-east-1:123456:key/abc",
        "kms_region": "us-east-1"
    }
)

# HashiCorp Vault integration
db = DataFlow(
    encryption={
        "key_source": "vault",
        "vault_url": "https://vault.example.com",
        "vault_path": "secret/dataflow/encryption",
        "vault_token": "from_env"
    }
)
```

### Transparent Encryption

```python
# Automatic encryption/decryption
workflow.add_node("PaymentMethodCreateNode", "create", {
    "customer_id": 123,
    "card_number": "4111111111111111",  # Encrypted before storage
    "cvv": "123"  # Encrypted before storage
})

# Decrypted automatically when reading
workflow.add_node("PaymentMethodReadNode", "read", {
    "id": 1,
    "decrypt_fields": True  # Default
})
```

## Access Control

### Role-Based Access Control (RBAC)

```python
from dataflow.security import require_role, require_permission

@db.model
class Document:
    title: str
    content: str
    classification: str  # public, internal, confidential, restricted

    __dataflow__ = {
        'access_control': {
            'read': ['user', 'admin'],
            'create': ['editor', 'admin'],
            'update': ['editor', 'admin'],
            'delete': ['admin']
        }
    }

# Enforce permissions in workflows
@require_role(['admin', 'editor'])
def create_document(data):
    workflow = WorkflowBuilder()
    workflow.add_node("DocumentCreateNode", "create", data)
    return workflow

# Fine-grained permissions
@require_permission('documents.create.confidential')
def create_confidential_document(data):
    data['classification'] = 'confidential'
    return create_document(data)
```

### Attribute-Based Access Control (ABAC)

```python
@db.model
class Project:
    name: str
    department: str
    budget: float

    __dataflow__ = {
        'access_control': {
            'type': 'abac',
            'policies': [
                {
                    'name': 'department_access',
                    'condition': 'user.department == record.department',
                    'permissions': ['read', 'update']
                },
                {
                    'name': 'budget_visibility',
                    'condition': 'user.role in ["manager", "director"]',
                    'fields': ['budget']
                }
            ]
        }
    }
```

### Row-Level Security

```python
@db.model
class CustomerData:
    customer_id: int
    data: dict

    __dataflow__ = {
        'row_level_security': {
            'enabled': True,
            'policy': 'user.customer_id == record.customer_id',
            'bypass_roles': ['admin', 'support']
        }
    }

# Automatic filtering based on user context
workflow.add_node("CustomerDataListNode", "my_data", {
    # Automatically adds filter: customer_id = current_user.customer_id
})
```

## Authentication Integration

### OAuth2 / OIDC

```python
db = DataFlow(
    auth={
        "provider": "oauth2",
        "issuer": "https://auth.example.com",
        "client_id": "dataflow-app",
        "client_secret": "from_env",
        "scopes": ["read", "write"],
        "user_info_endpoint": "/userinfo"
    }
)

# Extract user context from token
from dataflow.security import get_current_user

@db.model
class UserContent:
    title: str
    content: str
    owner_id: int = Field(default_factory=lambda: get_current_user().id)
```

### API Key Authentication

```python
# Configure API key validation
db = DataFlow(
    auth={
        "provider": "api_key",
        "header_name": "X-API-Key",
        "validation_endpoint": "https://api.example.com/validate",
        "cache_ttl": 300  # Cache validation for 5 minutes
    }
)

# Rate limiting per API key
workflow.add_node("RateLimiterNode", "limiter", {
    "key": "$api_key",
    "limit": 1000,  # requests
    "window": 3600  # per hour
})
```

### Multi-Factor Authentication

```python
@db.model
class SecureOperation:
    operation_type: str
    requires_mfa: bool = True

    __dataflow__ = {
        'mfa_required': {
            'operations': ['delete', 'bulk_update'],
            'verification_method': 'totp',  # or 'sms', 'email'
            'timeout': 300  # 5 minutes
        }
    }
```

## SQL Injection Prevention

### Automatic Parameterization

```python
# All queries are automatically parameterized
workflow.add_node("UserListNode", "search", {
    "filter": {
        "name": user_input,  # Safely parameterized
        "email": {"$regex": email_pattern}  # Safely escaped
    }
})

# Custom queries are validated
workflow.add_node("CustomQueryNode", "report", {
    "query": "SELECT * FROM users WHERE name = :name",
    "params": {"name": user_input},  # Parameterized
    "validate_query": True  # Default
})
```

### Query Validation

```python
from dataflow.security import QueryValidator

# Configure query validation rules
db = DataFlow(
    security={
        "query_validation": {
            "allow_raw_sql": False,
            "max_query_depth": 5,
            "blocked_keywords": ["DROP", "TRUNCATE", "EXEC"],
            "allowed_functions": ["COUNT", "SUM", "AVG", "MAX", "MIN"]
        }
    }
)

# Validate custom queries
validator = QueryValidator()
if validator.is_safe(custom_query):
    workflow.add_node("CustomQueryNode", "execute", {
        "query": custom_query
    })
```

## Rate Limiting & DDoS Protection

### Request Rate Limiting

```python
# Global rate limiting
db = DataFlow(
    rate_limiting={
        "enabled": True,
        "default_limit": 1000,  # per hour
        "burst_limit": 100,     # per minute
        "by_ip": True,
        "by_user": True,
        "by_api_key": True
    }
)

# Per-operation rate limits
@db.model
class RateLimitedResource:
    name: str

    __dataflow__ = {
        'rate_limits': {
            'create': {'limit': 10, 'window': 3600},
            'bulk_create': {'limit': 1, 'window': 86400},
            'delete': {'limit': 5, 'window': 3600}
        }
    }
```

### Connection Limits

```python
# Prevent connection exhaustion
db = DataFlow(
    connection_limits={
        "max_connections_per_ip": 10,
        "max_connections_per_user": 5,
        "connection_timeout": 30,
        "idle_timeout": 300,
        "blacklist_threshold": 100  # Failed attempts
    }
)
```

## Audit Logging

### Comprehensive Activity Tracking

```python
@db.model
class SensitiveData:
    content: str = Field(encrypted=True)
    classification: str

    __dataflow__ = {
        'audit_log': {
            'enabled': True,
            'log_reads': True,
            'log_writes': True,
            'log_deletes': True,
            'log_failed_access': True,
            'include_user_info': True,
            'include_ip_address': True,
            'retention_days': 2555  # 7 years
        }
    }
```

### Audit Query Interface

```python
# Query audit logs
workflow.add_node("AuditQueryNode", "security_audit", {
    "filters": {
        "user_id": suspicious_user_id,
        "action": "delete",
        "date_range": {
            "start": "2025-01-01",
            "end": "2025-01-31"
        }
    },
    "include_details": True
})

# Real-time alerts
workflow.add_node("AuditAlertNode", "alerts", {
    "filter": [
        {
            "pattern": "multiple_failed_logins",
            "threshold": 5,
            "window": 300  # 5 minutes
        },
        {
            "pattern": "bulk_data_export",
            "threshold": 1000,
            "action": "notify_security"
        }
    ]
})
```

## Data Masking & Anonymization

### Field Masking

```python
@db.model
class CustomerProfile:
    name: str
    email: str = Field(mask_pattern="***@$domain")
    phone: str = Field(mask_pattern="XXX-XXX-$last4")
    ssn: str = Field(
        encrypted=True,
        mask_pattern="XXX-XX-$last4",
        unmask_roles=["admin", "compliance"]
    )
```

### Dynamic Data Masking

```python
# Role-based data masking
workflow.add_node("CustomerListNode", "customers", {
    "mask_fields": {
        "email": {"roles": ["support"], "pattern": "***@$domain"},
        "phone": {"roles": ["support"], "pattern": "XXX-XXX-$last4"},
        "ssn": {"roles": ["admin"], "pattern": "FULL_MASK"}
    }
})

# Export with anonymization
workflow.add_node("DataExportNode", "gdpr_export", {
    "anonymize": True,
    "anonymization_rules": {
        "name": "generalize",  # John Doe -> J*** D***
        "email": "pseudonymize",  # Consistent fake email
        "ip_address": "remove",
        "birth_date": "generalize_year"
    }
})
```

## Secure Communication

### TLS Configuration

```python
# Database connections
db = DataFlow(
    "postgresql://user:pass@host/db",
    connection_args={
        "sslmode": "require",  # or "verify-full"
        "sslcert": "/path/to/client-cert.pem",
        "sslkey": "/path/to/client-key.pem",
        "sslrootcert": "/path/to/ca-cert.pem"
    }
)

# API communication
workflow.add_node("SecureAPINode", "external_call", {
    "url": "https://api.example.com/endpoint",
    "tls_version": "1.3",
    "verify_cert": True,
    "client_cert": "/path/to/cert.pem",
    "timeout": 30
})
```

### End-to-End Encryption

```python
# Encrypt data before transmission
workflow.add_node("E2EEncryptNode", "encrypt", {
    "data": sensitive_data,
    "recipient_public_key": recipient_key,
    "algorithm": "RSA-4096"
})

# Decrypt on receiving end
workflow.add_node("E2EDecryptNode", "decrypt", {
    "encrypted_data": "$encrypt.result",
    "private_key": "from_secure_storage"
})
```

## Security Headers

### HTTP Security Headers

```python
# When using with Gateway/Nexus
from kailash.servers.gateway import create_gateway

gateway = create_gateway(
    dataflow_integration=db,
    security_headers={
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
        "Referrer-Policy": "strict-origin-when-cross-origin"
    }
)
```

## Vulnerability Scanning

### Dependency Scanning

```python
# Automated security scanning
workflow.add_node("SecurityScanNode", "scan", {
    "scan_type": "dependencies",
    "check_cve": True,
    "severity_threshold": "medium",
    "auto_update": False,
    "notify": ["security@example.com"]
})

# SQL injection testing
workflow.add_node("SQLInjectionTestNode", "test", {
    "test_endpoints": True,
    "test_patterns": "owasp_top_10",
    "report_format": "json"
})
```

## Secret Management

### Environment Variables

```python
# Secure secret loading
from dataflow.security import SecretManager

secrets = SecretManager()

db = DataFlow(
    database_url=secrets.get("DATABASE_URL"),
    encryption_key=secrets.get("ENCRYPTION_KEY"),
    api_keys=secrets.get_json("API_KEYS")
)

# Automatic secret rotation
workflow.add_node("SecretRotationNode", "rotate", {
    "secret_type": "database_password",
    "rotation_schedule": "0 0 * * 0",  # Weekly
    "update_applications": True
})
```

## Security Monitoring

### Real-Time Threat Detection

```python
workflow.add_node("ThreatDetectionNode", "monitor", {
    "detection_rules": [
        {
            "name": "brute_force",
            "pattern": "failed_login",
            "threshold": 5,
            "window": 300,
            "action": "block_ip"
        },
        {
            "name": "data_exfiltration",
            "pattern": "bulk_export",
            "threshold": 10000,
            "action": "alert_and_block"
        },
        {
            "name": "privilege_escalation",
            "pattern": "role_change",
            "condition": "new_role == 'admin'",
            "action": "require_mfa"
        }
    ]
})
```

### Security Dashboard

```python
workflow.add_node("SecurityMetricsNode", "dashboard", {
    "metrics": [
        "failed_login_attempts",
        "blocked_ips",
        "encryption_operations",
        "audit_log_volume",
        "threat_detection_alerts"
    ],
    "time_range": "last_24_hours",
    "refresh_interval": 60  # seconds
})
```

## Best Practices

### 1. Defense in Depth

```python
# Multiple security layers
db = DataFlow(
    # Layer 1: Encryption
    encryption={"enabled": True, "algorithm": "AES-256-GCM"},

    # Layer 2: Access Control
    auth={"provider": "oauth2", "mfa_required": True},

    # Layer 3: Rate Limiting
    rate_limiting={"enabled": True, "default_limit": 1000},

    # Layer 4: Audit Logging
    audit={"enabled": True, "log_all_access": True}
)
```

### 2. Principle of Least Privilege

```python
# Minimal permissions by default
@db.model
class SecureResource:
    data: str

    __dataflow__ = {
        'access_control': {
            'default': 'deny',  # Deny by default
            'rules': [
                {'role': 'owner', 'permissions': ['all']},
                {'role': 'viewer', 'permissions': ['read']}
            ]
        }
    }
```

### 3. Regular Security Audits

```python
# Automated security audit workflow
def security_audit_workflow():
    workflow = WorkflowBuilder()

    # Check for weak passwords
    workflow.add_node("PasswordAuditNode", "passwords", {
        "check_complexity": True,
        "check_breached": True
    })

    # Review access permissions
    workflow.add_node("PermissionAuditNode", "permissions", {
        "check_orphaned": True,
        "check_excessive": True
    })

    # Scan for vulnerabilities
    workflow.add_node("VulnerabilityScanNode", "vulnerabilities", {
        "scan_code": True,
        "scan_dependencies": True
    })

    return workflow
```

### 4. Incident Response

```python
# Incident response workflow
workflow.add_node("IncidentResponseNode", "respond", {
    "incident_type": "data_breach",
    "actions": [
        {"type": "isolate", "target": "affected_systems"},
        {"type": "notify", "recipients": ["security_team", "legal"]},
        {"type": "preserve", "evidence": True},
        {"type": "analyze", "forensics": True}
    ],
    "playbook": "incident_response_v2"
})
```

## Compliance Features

### GDPR Compliance

```python
# Right to be forgotten
workflow.add_node("GDPRDeleteNode", "forget_user", {
    "user_id": 123,
    "cascade": True,
    "anonymize_logs": True,
    "retention_override": True
})

# Data portability
workflow.add_node("GDPRExportNode", "export_user_data", {
    "user_id": 123,
    "format": "json",
    "include_metadata": True,
    "encrypt_export": True
})
```

### HIPAA Compliance

```python
@db.model
class PatientRecord:
    patient_id: int
    medical_data: dict = Field(encrypted=True)

    __dataflow__ = {
        'compliance': {
            'hipaa': True,
            'phi_fields': ['medical_data'],
            'access_logging': 'detailed',
            'encryption_required': True,
            'retention_years': 6
        }
    }
```

---

**Next**: See [Compliance & Audit](compliance.md) for regulatory compliance features.
