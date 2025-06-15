"""
Common enums for middleware database models.

These enums are used across all Kailash applications to ensure consistency.
"""

from enum import Enum


class WorkflowStatus(Enum):
    """Workflow lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    TEMPLATE = "template"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ExecutionStatus(Enum):
    """Workflow execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    TIMEOUT = "timeout"


class NodeType(Enum):
    """Node category types from comprehensive catalog."""

    AI_ML = "ai_ml"
    DATA_PROCESSING = "data_processing"
    API_INTEGRATION = "api_integration"
    LOGIC_CONTROL = "logic_control"
    TRANSFORM = "transform"
    ADMIN_SECURITY = "admin_security"
    ENTERPRISE = "enterprise"
    TESTING = "testing"
    CODE_EXECUTION = "code_execution"


class TemplateCategory(Enum):
    """Template categories for organization."""

    BUSINESS = "business"
    DATA_PROCESSING = "data_processing"
    AI_ORCHESTRATION = "ai_orchestration"
    API_INTEGRATION = "api_integration"
    ENTERPRISE_AUTOMATION = "enterprise_automation"
    QUALITY_ASSURANCE = "quality_assurance"
    ADMIN_SECURITY = "admin_security"
    COMPLIANCE = "compliance"


class SecurityEventType(Enum):
    """Security event types for comprehensive monitoring."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    EXPORT = "export"
    THREAT_DETECTION = "threat_detection"
    POLICY_VIOLATION = "policy_violation"
    COMPLIANCE_CHECK = "compliance_check"
    PERMISSION_CHANGE = "permission_change"
    ACCOUNT_LOCK = "account_lock"
    SESSION_ANOMALY = "session_anomaly"


class ComplianceFramework(Enum):
    """Supported compliance frameworks."""

    GDPR = "gdpr"
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"


class SecurityClassification(Enum):
    """Data security classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AuditAction(Enum):
    """Audit log action types."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    EXPORT = "export"
    IMPORT = "import"
    SHARE = "share"
    ARCHIVE = "archive"
    RESTORE = "restore"
