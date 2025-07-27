# Enterprise Security Patterns

*User management, RBAC, authentication, and access control for enterprise workflows*

## 🛡️ Overview

This guide covers enterprise security implementation for Kailash SDK workflows, including user management, role-based access control (RBAC), attribute-based access control (ABAC), authentication patterns, and security monitoring.

## 🔐 Authentication Patterns

### JWT Authentication with Enterprise Features

```python
from kailash.middleware.auth import KailashJWTAuth, EnterpriseAuthConfig
from kailash.api.middleware import create_gateway

# Enterprise JWT configuration
auth_config = EnterpriseAuthConfig(
    # JWT Settings
    secret_key="your-enterprise-jwt-secret-key",
    algorithm="RS256",              # RSA for enterprise security
    token_expiry_hours=8,           # Business hours
    refresh_token_enabled=True,
    refresh_token_expiry_days=30,

    # Session Management
    session_management=True,
    concurrent_sessions_limit=3,
    session_timeout_minutes=60,

    # Security Features
    rate_limiting=True,
    max_login_attempts=5,
    lockout_duration_minutes=15,

    # Compliance
    audit_logging=True,
    password_complexity=True,
    mfa_required=True,

    # Integration
    ldap_integration=True,
    saml_sso=True,
    oauth_providers=["google", "microsoft", "okta"]
)

# Apply authentication to gateway
gateway = create_gateway(
    title="Secure Enterprise Application",
    cors_origins=["https://app.company.com"],
    enable_docs=True
)

gateway.add_auth(KailashJWTAuth(auth_config))
```

### Multi-Factor Authentication

```python
from kailash.nodes.auth import MultiFactorAuthNode
from kailash.workflow.builder import WorkflowBuilder

# MFA workflow (correct constructor usage)
mfa_workflow = WorkflowBuilder()

# Add MFA node
mfa_workflow.add_node("MultiFactorAuthNode", "mfa_check", {
    "methods": ["totp", "sms", "email"],
    "require_multiple": True,
    "backup_codes": True,
    "timeout_seconds": 300
})

# Session validation
mfa_workflow.add_node("SessionManagementNode", "session_validate", {
    "session_timeout": 3600,
    "concurrent_limit": 3,
    "security_level": "high"
})

# Connect MFA to session
mfa_workflow.add_connection("mfa_check", "authenticated", "session_validate", "input")
```

## 👥 User Management

### Enterprise User Management Node

```python
from kailash.nodes.admin import UserManagementNode

# User management configuration in a workflow
workflow = WorkflowBuilder()
workflow.add_node("UserManagementNode", "user_mgmt", {
    "provider": "ldap",  # or "database", "azure_ad", "okta"

    # User lifecycle
    "auto_provisioning": True,
    "deprovisioning_policy": "immediate",
    "account_lockout_enabled": True,

    # Password policies
    password_min_length=12,
    password_complexity=True,
    password_expiry_days=90,
    password_history_count=12,

    # Audit settings
    audit_user_actions=True,
    failed_login_tracking=True
)

# User operations workflow
user_workflow = WorkflowBuilder()

user_workflow.add_node("UserManagementNode", "user_ops", {
    "operation": "create_user",
    "user_data": {
        "username": "john.doe",
        "email": "john.doe@company.com",
        "department": "engineering",
        "manager": "jane.smith"
    }
})

# Automatic role assignment based on attributes
user_workflow.add_node("RoleManagementNode", "assign_roles", {
    "auto_assign": True,
    "assignment_rules": {
        "department": {
            "engineering": ["developer", "api_user"],
            "marketing": ["business_user"],
            "finance": ["business_user", "finance_reports"]
        }
    }
})

user_workflow.add_connection("user_ops", "result", "user_created", "input")
```

### LDAP/Active Directory Integration

```python
from kailash.integrations import LDAPIntegration

# Active Directory integration
ldap_config = LDAPIntegration(
    server="ldaps://ldap.company.com:636",
    base_dn="dc=company,dc=com",
    user_dn="ou=Users,dc=company,dc=com",
    group_dn="ou=Groups,dc=company,dc=com",

    # Authentication
    bind_user="cn=kailash-service,ou=ServiceAccounts,dc=company,dc=com",
    bind_password="service-account-password",

    # User mapping
    user_attributes={
        "username": "sAMAccountName",
        "email": "mail",
        "first_name": "givenName",
        "last_name": "sn",
        "department": "department",
        "title": "title",
        "manager": "manager"
    },

    # Group mapping for roles
    group_role_# mapping removed,OU=Groups,DC=company,DC=com": "admin",
        "CN=DataScientists,OU=Groups,DC=company,DC=com": "data_scientist",
        "CN=BusinessUsers,OU=Groups,DC=company,DC=com": "business_user"
    },

    # Sync settings
    sync_interval_hours=4,
    sync_deleted_users=True,
    cache_groups=True
)
```

## 🔑 Role-Based Access Control (RBAC)

### Role Definitions

```python
from kailash.access_control import AccessControlManager, RoleDefinition

# Define enterprise roles
roles = [
    RoleDefinition(
        name="admin",
        permissions=[
            "workflow:create", "workflow:execute", "workflow:delete",
            "user:manage", "system:configure", "audit:view"
        ],
        resource_limits={
            "max_workflows": 100,
            "max_executions_per_hour": 1000,
            "max_memory_mb": 8192
        },
        data_access_level="all"
    ),

    RoleDefinition(
        name="data_scientist",
        permissions=[
            "workflow:create", "workflow:execute",
            "data:read", "model:train", "model:deploy"
        ],
        resource_limits={
            "max_workflows": 20,
            "max_executions_per_hour": 100,
            "max_memory_mb": 4096
        },
        data_access_level="department"
    ),

    RoleDefinition(
        name="business_user",
        permissions=[
            "workflow:execute", "report:view", "dashboard:access"
        ],
        resource_limits={
            "max_workflows": 5,
            "max_executions_per_hour": 50,
            "max_memory_mb": 1024
        },
        data_access_level="team"
    ),

    RoleDefinition(
        name="auditor",
        permissions=[
            "audit:view", "report:view", "compliance:check"
        ],
        resource_limits={
            "max_workflows": 10,
            "max_executions_per_hour": 20,
            "max_memory_mb": 512
        },
        data_access_level="audit_only"
    )
]

# Enterprise access control
access_manager = AccessControlManager(
    strategy="rbac",
    roles=roles,
    enforce_resource_limits=True,
    audit_access_attempts=True,

    # Role inheritance
    role_hierarchy={
        "admin": ["data_scientist", "business_user"],
        "data_scientist": ["business_user"]
    }
)
```

### RBAC in Workflows

```python
from kailash.nodes.admin import PermissionCheckNode, RoleManagementNode

# Permission-aware workflow
secure_workflow = WorkflowBuilder()

# Check permissions before execution
secure_workflow.add_node("PermissionCheckNode", "auth_check", {
    "required_permission": "data:process",
    "resource_type": "sensitive_data",
    "fail_on_deny": True
})

# Role-based data access
secure_workflow.add_node("RoleManagementNode", "role_filter", {
    "operation": "filter_data_by_role",
    "data_classification": "confidential"
})

# Secure data processing
secure_workflow.add_node("LLMAgentNode", "process_data", {
    "model": "gpt-4",
    "security_level": "high",
    "audit_prompts": True
})

# Connections with role validation
secure_workflow.add_connection("auth_check", "result", "authorized", "input")

secure_workflow.add_connection("role_filter", "result", "filtered_data", "input")
```

## 🎯 Attribute-Based Access Control (ABAC)

### ABAC Policy Engine

```python
# Advanced ABAC policies
abac_policies = {
    "data_access": {
        "condition": "user.department == data.department AND user.clearance >= data.classification",
        "effect": "allow",
        "description": "Users can only access data from their department with appropriate clearance"
    },

    "time_based_access": {
        "condition": "current_time.hour >= 9 AND current_time.hour <= 17 AND current_time.weekday < 5",
        "effect": "allow",
        "description": "Access restricted to business hours"
    },

    "geo_restriction": {
        "condition": "user.location.country IN ['US', 'CA', 'GB'] AND NOT user.location.is_vpn",
        "effect": "allow",
        "description": "Access restricted to specific countries, no VPN"
    },

    "project_based": {
        "condition": "user.project_assignments CONTAINS workflow.project_id",
        "effect": "allow",
        "description": "Users can only access workflows for their assigned projects"
    },

    "data_sensitivity": {
        "condition": "user.security_clearance >= data.sensitivity_level AND user.training.data_handling == true",
        "effect": "allow",
        "description": "High-sensitivity data requires appropriate clearance and training"
    }
}

# ABAC access control manager
abac_manager = AccessControlManager(
    strategy="abac",
    policies=abac_policies,
    dynamic_evaluation=True,

    # Context providers
    context_providers={
        "time": "kailash.context.TimeContextProvider",
        "location": "kailash.context.LocationContextProvider",
        "data": "kailash.context.DataContextProvider"
    },

    # Policy evaluation
    cache_policy_decisions=True,
    decision_cache_ttl=300,  # 5 minutes
    audit_policy_decisions=True
)
```

### Hybrid RBAC + ABAC

```python
# Hybrid access control combining RBAC and ABAC
hybrid_manager = AccessControlManager(
    strategy="hybrid",

    # RBAC component
    roles=roles,
    role_hierarchy={"admin": ["data_scientist", "business_user"]},

    # ABAC component
    policies=abac_policies,

    # Hybrid configuration
    evaluation_order=["rbac", "abac"],  # Try RBAC first, then ABAC
    require_both=False,  # Either RBAC OR ABAC approval is sufficient

    # Override policies
    rbac_overrides_abac=True,  # Admin role can override ABAC restrictions
    emergency_access=True,
    emergency_access_roles=["admin", "security_officer"]
)
```

## 🔍 Security Monitoring & Threat Detection

### Threat Detection Node

```python
from kailash.nodes.security import ThreatDetectionNode, SecurityEventNode

# Threat detection workflow
security_workflow = WorkflowBuilder()

# Real-time threat detection
security_workflow.add_node("ThreatDetectionNode", "threat_scanner", {
    "detection_types": [
        "suspicious_login",
        "unusual_data_access",
        "privilege_escalation",
        "data_exfiltration",
        "brute_force_attack"
    ],

    # Machine learning models
    "ml_models": {
        "anomaly_detection": True,
        "behavior_analysis": True,
        "pattern_recognition": True
    },

    # Thresholds
    "alert_thresholds": {
        "high": 0.8,
        "medium": 0.6,
        "low": 0.4
    },

    # Response actions
    "auto_response": {
        "block_suspicious_ip": True,
        "lock_compromised_account": True,
        "notify_security_team": True
    }
})

# Security event processing
security_workflow.add_node("SecurityEventNode", "event_processor", {
    "event_types": ["auth", "access", "data", "system"],
    "enrichment": True,
    "correlation": True,
    "retention_days": 2555  # 7 years for compliance
})

# Alert generation
security_workflow.add_node("AlertingNode", "security_alerts", {
    "channels": ["slack", "email", "sms", "pagerduty"],
    "escalation_rules": {
        "critical": {"immediate": True, "channels": ["sms", "pagerduty"]},
        "high": {"delay_minutes": 5, "channels": ["slack", "email"]},
        "medium": {"delay_minutes": 15, "channels": ["slack"]}
    }
})

# Connect threat detection pipeline
security_workflow.add_connection("threat_scanner", "result", "threats_detected", "input")

security_workflow.add_connection("event_processor", "result", "processed_events", "input")
```

### Risk Assessment

```python
from kailash.nodes.auth import RiskAssessmentNode

# User risk assessment
risk_workflow = WorkflowBuilder()

risk_workflow.add_node("RiskAssessmentNode", "risk_analyzer", {
    "risk_factors": [
        "login_location",
        "device_fingerprint",
        "time_of_access",
        "access_patterns",
        "data_sensitivity",
        "user_behavior"
    ],

    # Risk scoring
    "scoring_algorithm": "weighted_composite",
    "risk_thresholds": {
        "low": 0.3,
        "medium": 0.6,
        "high": 0.8,
        "critical": 0.9
    },

    # Adaptive responses
    "adaptive_responses": {
        "low": {"action": "allow"},
        "medium": {"action": "mfa_required"},
        "high": {"action": "manager_approval"},
        "critical": {"action": "block_and_investigate"}
    }
})

# Behavioral analysis
risk_workflow.add_node("BehaviorAnalysisNode", "behavior_analysis", {
    "baseline_period_days": 30,
    "anomaly_sensitivity": 0.8,
    "learning_enabled": True,
    "features": [
        "access_times",
        "resource_usage",
        "workflow_patterns",
        "data_access_patterns"
    ]
})

risk_workflow.add_connection("risk_analyzer", "result", "risk_score", "input")
```

## 🔐 Data Protection & Privacy

### Data Encryption Patterns

```python
from kailash.nodes.security import DataMaskingNode
# Note: EncryptionNode not yet available - use middleware encryption instead

# Data protection workflow
protection_workflow = WorkflowBuilder()

# Note: For encryption, use middleware-level encryption or CredentialManagerNode
# Field-level encryption coming in future SDK version

# Data masking for non-production
protection_workflow.add_node("DataMaskingNode", "mask_data", {
    "masking_rules": {
        "ssn": {"type": "partial", "show_last": 4},
        "credit_card": {"type": "tokenization"},
        "email": {"type": "domain_preserve"},
        "phone": {"type": "format_preserve"}
    },

    "preserve_referential_integrity": True,
    "consistent_masking": True
})

# PII detection and redaction
protection_workflow.add_node("PIIDetectionNode", "pii_detector", {
    "detection_types": [
        "ssn", "credit_card", "phone", "email",
        "passport", "driver_license", "medical_record"
    ],
    "confidence_threshold": 0.9,
    "auto_redact": True,
    "audit_detections": True
})
```

### GDPR Compliance

```python
from kailash.nodes.compliance import GDPRComplianceNode

# GDPR compliance workflow
gdpr_workflow = WorkflowBuilder()

gdpr_workflow.add_node("GDPRComplianceNode", "gdpr_processor", {
    # Data subject rights
    "data_retention_days": 730,
    "anonymization_enabled": True,
    "consent_tracking": True,
    "right_to_erasure": True,
    "data_portability": True,

    # Export formats
    "data_export_format": "json",
    "include_metadata": True,
    "structured_export": True,

    # Compliance monitoring
    "audit_trail": True,
    "breach_detection": True,
    "lawful_basis_tracking": True
})

# Consent management
gdpr_workflow.add_node("ConsentManagementNode", "consent_mgmt", {
    "consent_types": [
        "data_processing",
        "marketing",
        "analytics",
        "third_party_sharing"
    ],
    "granular_consent": True,
    "withdrawal_mechanism": True,
    "consent_expiry_days": 365
})

gdpr_workflow.add_connection("consent_mgmt", "result", "consent_status", "input")
```

## 🔒 Secure Credential Management

### Rotating Credentials

```python
from kailash.nodes.security import RotatingCredentialNode, CredentialManagerNode

# Credential management workflow
cred_workflow = WorkflowBuilder()

# Automatic credential rotation
cred_workflow.add_node("RotatingCredentialNode", "auto_rotate", {
    "credential_name": "database_passwords",
    "rotation_interval_days": 30,
    "rotation_window_hours": 2,  # 2 AM - 4 AM

    # Rotation strategy
    "rotation_strategy": "gradual",  # or "immediate"
    "grace_period_hours": 24,
    "backup_credentials": 2,

    # Validation
    "test_new_credentials": True,
    "rollback_on_failure": True,

    # Notifications
    "notify_on_rotation": True,
    "notify_on_failure": True
})

# Secure credential storage
cred_workflow.add_node("CredentialManagerNode", "cred_store", {
    "storage_backend": "aws_secrets_manager",  # or "azure_key_vault", "hashicorp_vault"
    "encryption_at_rest": True,
    "access_logging": True,

    # Access patterns
    "credential_types": {
        "database": {"rotation": True, "max_age_days": 30},
        "api_keys": {"rotation": True, "max_age_days": 90},
        "certificates": {"rotation": True, "max_age_days": 365}
    }
})

cred_workflow.add_connection("auto_rotate", "result", "new_credentials", "input")
```

## 🛡️ Connection Parameter Validation (v0.6.7+)

### Overview

Starting in v0.6.7, the Kailash SDK provides connection parameter validation to prevent security vulnerabilities where parameters passed through workflow connections could bypass validation checks. This is a **CRITICAL** security feature that prevents injection attacks and ensures type safety.

### Security Vulnerability Fixed

Previously, parameters had two paths with different validation:
- **Direct parameters** (via `runtime.execute()`) - ✅ VALIDATED
- **Connection parameters** (via `workflow.add_connection("source", "result", "target", "input")`) - ❌ NOT VALIDATED

This created attack vectors for SQL injection, command injection, and other parameter-based exploits.

### Implementation

```python
from kailash.runtime.local import LocalRuntime

# Production: Always use strict mode
runtime = LocalRuntime(connection_validation="strict")

# Migration period: Use warn mode to identify issues
runtime_migration = LocalRuntime(connection_validation="warn")

# Legacy compatibility only (NOT RECOMMENDED)
runtime_legacy = LocalRuntime(connection_validation="off")
```

### Enterprise Security Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import SQLDatabaseNode

# Create secure workflow
workflow = WorkflowBuilder()

# User input node (potentially untrusted data)
workflow.add_node("UserInputNode", "user_input", {})

# Database operation with parameter validation
workflow.add_node(SQLDatabaseNode, "db_operation", {
    "connection_string": "postgresql://secure_db",
    "operation": "query"
})

# Connection will now validate parameters
workflow.add_connection("user_input", "result", "query_params", "input")

# Strict validation prevents SQL injection
runtime = LocalRuntime(connection_validation="strict")

try:
    # Malicious input will be caught by validation
    results, _ = runtime.execute(workflow.build(), {
        "user_input": {
            "query_params": {
                "user_id": "1; DROP TABLE users;--"  # SQL injection attempt
            }
        }
    })
except WorkflowExecutionError as e:
    # Connection validation will reject invalid parameters
    logger.error(f"Security: Blocked malicious input: {e}")
```

### Integration with Access Control

```python
# Combine with RBAC for defense in depth
workflow = WorkflowBuilder()

# Add access control
workflow.add_node("AccessControlNode", "rbac_check", {
    "required_permissions": ["data:read", "user:view"]
})

# Add input validation
workflow.add_node("InputValidationNode", "validate", {
    "schema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "integer", "minimum": 1},
            "fields": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["user_id"]
    }
})

# Database query with validated parameters
workflow.add_node("AsyncSQLDatabaseNode", "secure_query", {
    "operation": "query",
    "query": "SELECT {fields} FROM users WHERE id = $1"
})

# Secure connection chain
workflow.add_connection("rbac_check", "authorized", "validate", "proceed")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Production configuration
runtime = LocalRuntime(
    connection_validation="strict",  # Enforce parameter validation
    access_control_enabled=True,     # Enable RBAC
    audit_logging=True              # Log all operations
)
```

### Migration Guide

1. **Audit existing workflows** - Run with `warn` mode
   ```python
   runtime = LocalRuntime(connection_validation="warn")
   # Check logs for validation warnings
   ```

2. **Fix validation issues** - Update node parameters
   ```python
   # Ensure all nodes declare their parameters correctly
   def get_parameters(self):
       return {
           "user_id": NodeParameter(name="user_id", type=int, required=True),
           "action": NodeParameter(name="action", type=str, enum=["read", "write"])
       }
   ```

3. **Enable strict mode** - Deploy to production
   ```python
   runtime = LocalRuntime(connection_validation="strict")
   ```

### Security Best Practices

1. **Always use strict mode in production**
2. **Validate at multiple layers** - Connection validation + input validation + RBAC
3. **Monitor validation failures** - Could indicate attack attempts
4. **Regular security audits** - Review workflow connections
5. **Type enforcement** - Use proper NodeParameter types

### Related Security Features

- **Input Validation Nodes** - Schema-based validation
- **SQL Parameter Binding** - Automatic SQL injection prevention
- **Command Sanitization** - Safe shell command execution
- **Access Control Integration** - Combined with RBAC/ABAC

For complete documentation, see [Connection Parameter Validation Guide](../security/connection-parameter-validation.md).

## 🏢 Enterprise Integration Security

### SSO Integration

```python
from kailash.integrations import SAMLIntegration, OAuthIntegration

# SAML SSO configuration
saml_config = SAMLIntegration(
    entity_id="https://kailash.company.com",
    acs_url="https://kailash.company.com/auth/saml/acs",
    sso_url="https://sso.company.com/saml/login",

    # Certificate configuration
    x509_cert_file="/ssl/saml.crt",
    private_key_file="/ssl/saml.key",

    # Security settings
    want_assertions_signed=True,
    want_name_id_encrypted=True,
    signature_algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",

    # Attribute mapping
    attribute_# mapping removed,
        "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        "department": "http://schemas.company.com/claims/department"
    },

    # Session management
    session_timeout=3600,
    maximum_session_lifetime=28800
)

# OAuth 2.0 / OpenID Connect
oauth_config = OAuthIntegration(
    provider="okta",  # or "azure_ad", "google", "auth0"
    client_id="your_client_id",
    client_secret="your_client_secret",

    # OIDC settings
    discovery_url="https://company.okta.com/.well-known/openid_configuration",
    scopes=["openid", "profile", "email", "groups"],

    # Security
    pkce_enabled=True,
    state_verification=True,
    nonce_verification=True,

    # Token management
    access_token_lifetime=3600,
    refresh_token_lifetime=86400,
    token_rotation=True
)
```

## 🚨 Incident Response

### Automated Incident Response

```python
from kailash.nodes.security import IncidentResponseNode

# Incident response workflow
incident_workflow = WorkflowBuilder()

incident_workflow.add_node("IncidentResponseNode", "incident_handler", {
    "response_types": {
        "data_breach": {
            "severity": "critical",
            "actions": [
                "isolate_affected_systems",
                "preserve_evidence",
                "notify_stakeholders",
                "activate_breach_protocol"
            ],
            "timeline": {
                "immediate": ["isolate", "preserve"],
                "1_hour": ["notify_security_team"],
                "4_hours": ["notify_management"],
                "24_hours": ["notify_authorities"]
            }
        },

        "unauthorized_access": {
            "severity": "high",
            "actions": [
                "disable_compromised_accounts",
                "reset_credentials",
                "audit_access_logs",
                "enhance_monitoring"
            ]
        },

        "malware_detection": {
            "severity": "high",
            "actions": [
                "quarantine_affected_systems",
                "run_deep_scan",
                "update_signatures",
                "restore_from_backup"
            ]
        }
    },

    # Communication
    "notification_channels": ["security_team", "management", "legal"],
    "escalation_matrix": {
        "critical": ["ciso", "cto", "ceo"],
        "high": ["security_manager", "it_manager"],
        "medium": ["security_analyst"]
    },

    # Documentation
    "auto_documentation": True,
    "evidence_preservation": True,
    "chain_of_custody": True
})

# Forensics integration
incident_workflow.add_node("ForensicsNode", "evidence_collector", {
    "collection_types": ["logs", "memory_dumps", "disk_images", "network_traffic"],
    "chain_of_custody": True,
    "hash_verification": True,
    "encrypted_storage": True
})

incident_workflow.add_connection("incident_handler", "result", "incident_details", "input")
```

## 📊 Security Auditing & Compliance

### Audit Trail Management

```python
from kailash.nodes.admin import EnterpriseAuditLogNode
from kailash.nodes.compliance import ComplianceReportNode

# Comprehensive audit workflow
audit_workflow = WorkflowBuilder()

# Detailed audit logging
audit_workflow.add_node("EnterpriseAuditLogNode", "audit_logger", {
    "event_types": [
        "authentication",
        "authorization",
        "data_access",
        "configuration_change",
        "administrative_action",
        "security_event"
    ],

    # Audit detail levels
    "detail_levels": {
        "authentication": "high",
        "data_access": "high",
        "configuration": "medium",
        "general": "low"
    },

    # Retention and storage
    "retention_days": 2555,  # 7 years
    "immutable_storage": True,
    "encryption_at_rest": True,

    # Real-time monitoring
    "real_time_alerts": True,
    "anomaly_detection": True
})

# Compliance reporting
audit_workflow.add_node("ComplianceReportNode", "compliance_reporter", {
    "frameworks": ["SOC2", "ISO27001", "GDPR", "HIPAA", "PCI_DSS"],
    "report_frequency": "monthly",
    "automated_evidence_collection": True,

    # Control mapping
    "control_mappings": {
        "access_control": ["AC-2", "AC-3", "AC-6"],
        "audit_logging": ["AU-2", "AU-3", "AU-12"],
        "encryption": ["SC-13", "SC-28"]
    }
})

audit_workflow.add_connection("audit_logger", "result", "audit_data", "input")
```

## 🔗 Quick Security Implementation Checklist

### Essential Security Components
- [ ] **Authentication**: JWT with MFA enabled
- [ ] **Authorization**: RBAC or ABAC implementation
- [ ] **User Management**: Automated provisioning/deprovisioning
- [ ] **Credential Management**: Automatic rotation and secure storage
- [ ] **Data Protection**: Encryption at rest and in transit
- [ ] **Threat Detection**: Real-time monitoring and alerting
- [ ] **Audit Logging**: Comprehensive audit trail
- [ ] **Compliance**: GDPR, SOC2, ISO27001 controls
- [ ] **Incident Response**: Automated response procedures
- [ ] **Security Monitoring**: Continuous monitoring and reporting

### Security Nodes Reference
- **UserManagementNode** - User lifecycle management
- **MultiFactorAuthNode** - MFA implementation
- **PermissionCheckNode** - Runtime permission validation
- **RoleManagementNode** - Role assignment and management
- **ThreatDetectionNode** - Security threat monitoring
- **CredentialManagerNode** - Secure credential storage and encryption
- **EnterpriseAuditLogNode** - Comprehensive audit logging
- **GDPRComplianceNode** - GDPR compliance automation
- **IncidentResponseNode** - Automated incident handling

### Related Security Guides
- **[Enterprise Middleware](middleware-patterns.md)** - Security-enabled middleware
- **[Compliance Patterns](compliance-patterns.md)** - Regulatory compliance
- **[Production Security](production-patterns.md)** - Production security hardening
- **[Security Testing](../testing/security-testing-guide.md)** - Security validation

---

**Ready to secure your enterprise workflows?** Start with authentication and user management, then progressively add authorization, threat detection, and compliance controls.
