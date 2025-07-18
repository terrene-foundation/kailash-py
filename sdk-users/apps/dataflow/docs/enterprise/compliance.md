# Compliance & Audit

DataFlow provides comprehensive compliance features for GDPR, HIPAA, SOC2, and other regulatory requirements.

## Overview

Compliance features in DataFlow include:
- **Data Privacy**: GDPR right to be forgotten, data portability
- **Healthcare**: HIPAA PHI protection and audit trails
- **Financial**: PCI DSS compliance for payment data
- **Audit Trails**: Immutable activity logs
- **Data Governance**: Retention policies and classification

## GDPR Compliance

### Right to Be Forgotten

Delete all user data while maintaining referential integrity:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Complete user data deletion
workflow.add_node("GDPRDeleteNode", "delete_user", {
    "user_id": 123,
    "cascade": True,  # Delete related data
    "anonymize_logs": True,  # Keep logs but anonymize
    "retention_override": True,  # Override retention policies
    "confirmation_token": "user_confirmed_deletion"
})

# Verify deletion
workflow.add_node("GDPRVerifyDeletionNode", "verify", {
    "user_id": 123,
    "check_all_tables": True,
    "include_backups": True
})
```

### Data Portability

Export user data in standard formats:

```python
# Export all user data
workflow.add_node("GDPRExportNode", "export_data", {
    "user_id": 123,
    "format": "json",  # or "csv", "xml"
    "include_metadata": True,
    "include_derived_data": True,
    "encrypt_export": True,
    "delivery_method": "secure_download"  # or "email"
})

# Track export for compliance
workflow.add_node("AuditLogNode", "log_export", {
    "event": "gdpr_data_export",
    "user_id": 123,
    "exported_at": "$export_data.timestamp",
    "export_id": "$export_data.id"
})
```

### Consent Management

Track and enforce user consent:

```python
@db.model
class UserConsent:
    user_id: int
    consent_type: str  # marketing, analytics, cookies
    granted: bool
    granted_at: datetime
    ip_address: str

    __dataflow__ = {
        'audit_log': True,
        'immutable_fields': ['granted_at', 'ip_address']
    }

# Check consent before processing
workflow.add_node("ConsentCheckNode", "check", {
    "user_id": 123,
    "required_consents": ["marketing", "analytics"],
    "fail_if_missing": True
})
```

### Data Minimization

Collect only necessary data:

```python
@db.model
class MinimalUser:
    # Only essential fields
    email: str = Field(required=True)
    name: str = Field(required=False)  # Optional

    # Auto-delete after purpose fulfilled
    __dataflow__ = {
        'auto_delete_after': 'purpose_fulfilled',
        'purpose_tracking': True
    }

# Configure field-level retention
@db.model
class UserActivity:
    user_id: int
    activity_type: str
    details: dict = Field(
        retention_days=90,  # Auto-delete after 90 days
        retention_reason="analytics"
    )
```

## HIPAA Compliance

### Protected Health Information (PHI)

Secure handling of medical data:

```python
@db.model
class PatientRecord:
    patient_id: int
    # PHI fields with encryption
    name: str = Field(phi=True, encrypted=True)
    ssn: str = Field(phi=True, encrypted=True, masked=True)
    diagnosis: str = Field(phi=True, encrypted=True)

    # Non-PHI fields
    record_number: str
    created_by: str

    __dataflow__ = {
        'compliance': {
            'hipaa': True,
            'phi_fields': ['name', 'ssn', 'diagnosis'],
            'encryption_required': True,
            'access_logging': 'detailed',
            'minimum_password_strength': 'strong',
            'session_timeout': 900  # 15 minutes
        }
    }
```

### Access Controls

Implement minimum necessary access:

```python
# Role-based PHI access
workflow.add_node("PHIAccessControlNode", "access", {
    "roles": {
        "doctor": {
            "can_access": ["name", "diagnosis", "treatment"],
            "purpose": "treatment"
        },
        "nurse": {
            "can_access": ["name", "vitals"],
            "purpose": "care"
        },
        "billing": {
            "can_access": ["name", "insurance"],
            "purpose": "payment"
        }
    }
})

# Track all PHI access
workflow.add_node("PHIAuditNode", "audit", {
    "user_id": current_user_id,
    "patient_id": 123,
    "fields_accessed": ["diagnosis"],
    "purpose": "treatment",
    "access_time": datetime.now()
})
```

### Breach Notification

Automated breach detection and notification:

```python
workflow.add_node("BreachDetectionNode", "monitor", {
    "detection_rules": [
        {
            "name": "mass_export",
            "condition": "export_count > 500",
            "severity": "critical"
        },
        {
            "name": "unauthorized_phi_access",
            "condition": "access_denied_count > 10",
            "severity": "high"
        }
    ]
})

workflow.add_node("BreachNotificationNode", "notify", {
    "breach_type": "$monitor.breach_type",
    "affected_records": "$monitor.affected_count",
    "notify_patients": True,  # Within 60 days
    "notify_hhs": True,      # Within 60 days
    "notify_media": "$monitor.affected_count > 500"  # If >500 affected
})
```

## PCI DSS Compliance

### Payment Card Data Protection

Secure credit card handling:

```python
@db.model
class PaymentCard:
    # Tokenized card data
    card_token: str = Field(primary_key=True)
    # Masked display
    card_last4: str
    card_brand: str

    # Never store these
    # cvv: NEVER STORE
    # pin: NEVER STORE

    __dataflow__ = {
        'pci_dss': {
            'level': 1,  # Highest security
            'tokenization': True,
            'encryption': 'AES-256',
            'key_rotation': 90,  # days
            'access_logging': True
        }
    }

# Use tokenization service
workflow.add_node("TokenizationNode", "tokenize", {
    "card_number": "4111111111111111",
    "tokenization_service": "stripe",  # or internal
    "return_token": True,
    "return_last4": True
})
```

### Network Segmentation

Isolate payment processing:

```python
# Separate database for payment data
payment_db = DataFlow(
    database_url="postgresql://payment_db/secure",
    network_segment="pci_zone",
    firewall_rules={
        "ingress": ["application_server"],
        "egress": ["tokenization_service"]
    }
)

# Restricted access workflow
workflow.add_node("PCIAccessNode", "payment_access", {
    "require_mfa": True,
    "ip_whitelist": ["10.0.1.0/24"],
    "session_recording": True
})
```

## SOC 2 Compliance

### Security Controls

Implement SOC 2 Type II controls:

```python
@db.model
class SystemAccess:
    user_id: int
    resource: str
    action: str
    timestamp: datetime
    ip_address: str

    __dataflow__ = {
        'soc2': {
            'trust_principle': 'security',
            'controls': [
                'access_monitoring',
                'change_management',
                'risk_assessment'
            ]
        }
    }

# Continuous monitoring
workflow.add_node("SOC2MonitoringNode", "monitor", {
    "controls": [
        {
            "id": "CC6.1",
            "name": "Logical Access Controls",
            "check": "unauthorized_access_attempts",
            "threshold": 5
        },
        {
            "id": "CC7.2",
            "name": "Change Management",
            "check": "unauthorized_changes",
            "threshold": 0
        }
    ],
    "reporting_frequency": "daily"
})
```

### Availability Monitoring

Track system availability for SOC 2:

```python
workflow.add_node("AvailabilityMonitorNode", "uptime", {
    "sla_target": 99.9,  # percentage
    "measurement_window": "monthly",
    "excluded_maintenance": True,
    "alert_threshold": 99.5
})

workflow.add_node("IncidentTrackingNode", "incidents", {
    "severity_levels": ["critical", "high", "medium", "low"],
    "resolution_sla": {
        "critical": 4,   # hours
        "high": 24,      # hours
        "medium": 72,    # hours
        "low": 168       # hours (1 week)
    }
})
```

## Audit Trail Management

### Immutable Audit Logs

Create tamper-proof audit trails:

```python
@db.model
class AuditLog:
    id: int = Field(primary_key=True, auto_increment=True)
    timestamp: datetime = Field(default=datetime.utcnow)
    user_id: int
    action: str
    resource_type: str
    resource_id: int
    details: dict
    ip_address: str
    user_agent: str

    # Cryptographic hash for integrity
    hash: str = Field(computed=True)
    previous_hash: str

    __dataflow__ = {
        'immutable': True,  # No updates allowed
        'retention_years': 7,
        'backup_required': True,
        'hash_algorithm': 'sha256'
    }
```

### Audit Query Interface

Search and analyze audit logs:

```python
# Complex audit queries
workflow.add_node("AuditSearchNode", "search", {
    "filters": {
        "date_range": {
            "start": "2025-01-01",
            "end": "2025-01-31"
        },
        "users": [123, 456],
        "actions": ["delete", "export"],
        "resource_types": ["user_data", "payment_data"]
    },
    "aggregations": {
        "by_user": True,
        "by_action": True,
        "by_hour": True
    }
})

# Anomaly detection
workflow.add_node("AuditAnomalyNode", "anomalies", {
    "detection_methods": [
        "unusual_hours",     # Outside business hours
        "unusual_volume",    # Spike in activity
        "unusual_pattern",   # Deviation from baseline
        "privilege_escalation"
    ],
    "baseline_period": 30,  # days
    "sensitivity": "medium"
})
```

### Audit Reports

Generate compliance reports:

```python
workflow.add_node("ComplianceReportNode", "report", {
    "report_type": "quarterly_audit",
    "compliance_frameworks": ["gdpr", "hipaa", "soc2"],
    "sections": [
        "user_access_reviews",
        "data_retention_compliance",
        "security_incidents",
        "policy_violations",
        "training_completion"
    ],
    "format": "pdf",
    "sign_report": True
})
```

## Data Classification

### Automatic Classification

Classify data based on content:

```python
@db.model
class Document:
    content: str
    classification: str = Field(
        computed=True,
        classifier="auto"
    )

    __dataflow__ = {
        'classification': {
            'rules': [
                {"pattern": r"\b\d{3}-\d{2}-\d{4}\b", "label": "pii_ssn"},
                {"pattern": r"\b\d{16}\b", "label": "pci_card"},
                {"keywords": ["diagnosis", "treatment"], "label": "phi"}
            ],
            'default_classification': 'public',
            'reclassification_allowed': True
        }
    }

# Manual classification override
workflow.add_node("ClassificationNode", "classify", {
    "document_id": 123,
    "classification": "confidential",
    "reason": "contains trade secrets",
    "approved_by": "data_governance_team"
})
```

### Data Retention Policies

Implement retention and deletion policies:

```python
@db.model
class RetentionPolicy:
    data_type: str
    classification: str
    retention_days: int
    legal_hold: bool = False
    deletion_method: str  # "soft", "hard", "secure_wipe"

    __dataflow__ = {
        'system_table': True
    }

# Apply retention policies
workflow.add_node("RetentionEnforcementNode", "enforce", {
    "scan_frequency": "daily",
    "actions": {
        "archive": {
            "after_days": 365,
            "to_storage": "cold_storage"
        },
        "delete": {
            "after_days": 2555,  # 7 years
            "method": "secure_wipe",
            "verify_deletion": True
        }
    },
    "exclude_legal_hold": True
})
```

## Compliance Monitoring

### Continuous Compliance Checks

Monitor compliance status in real-time:

```python
workflow.add_node("ComplianceMonitorNode", "monitor", {
    "frameworks": ["gdpr", "hipaa", "pci_dss", "soc2"],
    "checks": [
        {
            "name": "encryption_enabled",
            "query": "SELECT COUNT(*) FROM tables WHERE encryption = false",
            "expected": 0
        },
        {
            "name": "audit_gaps",
            "query": "SELECT MAX(gap) FROM audit_continuity",
            "threshold": 300  # seconds
        },
        {
            "name": "access_reviews",
            "check": "last_review_date < 90 days ago",
            "action": "alert"
        }
    ],
    "dashboard_url": "https://compliance.example.com"
})
```

### Compliance Automation

Automate compliance workflows:

```python
# Automated access reviews
workflow.add_node("AccessReviewNode", "review", {
    "frequency": "quarterly",
    "reviewers": ["manager", "security_team"],
    "scope": {
        "privileged_accounts": True,
        "service_accounts": True,
        "inactive_accounts": True
    },
    "actions": {
        "disable_inactive": {"days": 90},
        "require_mfa": {"for_roles": ["admin", "finance"]},
        "rotate_credentials": {"age_days": 180}
    }
})

# Policy enforcement
workflow.add_node("PolicyEnforcementNode", "enforce", {
    "policies": [
        {
            "name": "password_policy",
            "requirements": {
                "min_length": 12,
                "complexity": "high",
                "history": 12,
                "max_age_days": 90
            }
        },
        {
            "name": "data_handling",
            "requirements": {
                "encryption_at_rest": True,
                "encryption_in_transit": True,
                "secure_deletion": True
            }
        }
    ]
})
```

## Privacy by Design

### Data Minimization

Collect only what's necessary:

```python
@db.model
class MinimalProfile:
    # Required fields only
    user_id: int
    email: str = Field(purpose="authentication")

    # Optional with purpose
    name: str = Field(
        required=False,
        purpose="personalization",
        deletion_after_days=365
    )

    # Derived data with auto-cleanup
    last_login: datetime = Field(
        purpose="security",
        retention_days=90
    )
```

### Purpose Limitation

Track and enforce data usage purpose:

```python
workflow.add_node("PurposeTrackingNode", "track", {
    "data_collection": {
        "field": "email",
        "purpose": "newsletter",
        "consent_id": "consent_123",
        "expiry": "2026-01-01"
    }
})

workflow.add_node("PurposeEnforcementNode", "enforce", {
    "check_before_use": True,
    "block_if_expired": True,
    "require_new_consent": True
})
```

## Cross-Border Data Transfer

### Data Residency

Ensure data stays in allowed regions:

```python
db = DataFlow(
    data_residency={
        "default_region": "eu-west-1",
        "allowed_regions": ["eu-west-1", "eu-central-1"],
        "user_region_mapping": True,  # Store user data in their region
        "cross_region_replication": False
    }
)

@db.model
class RegionalData:
    user_id: int
    data: dict

    __dataflow__ = {
        'region_locked': True,
        'region_field': 'user_region'
    }
```

### Transfer Mechanisms

Implement approved transfer mechanisms:

```python
workflow.add_node("DataTransferNode", "transfer", {
    "from_region": "eu-west-1",
    "to_region": "us-east-1",
    "mechanism": "standard_contractual_clauses",  # or "adequacy_decision"
    "encryption": "in_transit",
    "audit_transfer": True,
    "user_consent": True
})
```

## Compliance Dashboard

### Real-Time Compliance Status

Monitor compliance across all frameworks:

```python
workflow.add_node("ComplianceDashboardNode", "dashboard", {
    "metrics": {
        "gdpr": {
            "deletion_requests": {"completed": 45, "pending": 2},
            "export_requests": {"completed": 23, "pending": 1},
            "consent_rate": 87.5
        },
        "hipaa": {
            "phi_access_logged": 100,  # percentage
            "encryption_coverage": 100,
            "breach_incidents": 0
        },
        "pci_dss": {
            "card_data_tokenized": 100,
            "vulnerability_scans": "passed",
            "penetration_tests": "scheduled"
        },
        "soc2": {
            "availability": 99.97,
            "security_incidents": 2,
            "change_approvals": 100
        }
    },
    "alerts": [
        {"type": "warning", "message": "Access review due in 7 days"},
        {"type": "info", "message": "Quarterly audit scheduled"}
    ]
})
```

## Best Practices

### 1. Defense in Depth

Layer multiple compliance controls:

```python
# Multiple layers of protection
@db.model
class SensitiveData:
    content: str

    __dataflow__ = {
        # Layer 1: Classification
        'classification': 'confidential',

        # Layer 2: Encryption
        'encryption': True,

        # Layer 3: Access Control
        'access_control': 'role_based',

        # Layer 4: Audit
        'audit_log': True,

        # Layer 5: Retention
        'retention_days': 365
    }
```

### 2. Automate Compliance

Reduce manual compliance burden:

```python
# Automated compliance workflow
def setup_compliance_automation():
    workflow = WorkflowBuilder()

    # Daily checks
    workflow.add_node("DailyComplianceNode", "daily", {
        "checks": ["encryption", "access_logs", "backups"]
    })

    # Weekly reports
    workflow.add_node("WeeklyReportNode", "weekly", {
        "recipients": ["compliance@example.com"],
        "include_metrics": True
    })

    # Monthly audits
    workflow.add_node("MonthlyAuditNode", "monthly", {
        "full_scan": True,
        "generate_evidence": True
    })

    return workflow
```

### 3. Document Everything

Maintain compliance documentation:

```python
workflow.add_node("DocumentationNode", "document", {
    "auto_generate": {
        "data_flow_diagrams": True,
        "privacy_impact_assessments": True,
        "security_policies": True,
        "incident_procedures": True
    },
    "version_control": True,
    "approval_workflow": True
})
```

---

**Next**: See [Integration Examples](../integration/nexus.md) for connecting DataFlow with Nexus platform.
