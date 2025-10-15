"""
Base abstract models for common entities.

Applications extend these models for their specific needs.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship, validates

from .base import BaseMixin, ComplianceMixin, EnterpriseBaseMixin
from .enums import (
    ComplianceFramework,
    ExecutionStatus,
    NodeType,
    SecurityEventType,
    TemplateCategory,
    WorkflowStatus,
)
from .models import Base


class BaseWorkflowModel(Base, EnterpriseBaseMixin):
    """Base workflow model with enterprise features."""

    __abstract__ = True

    # Core fields
    workflow_id = Column(
        String(255), primary_key=True, default=lambda: f"workflow_{uuid.uuid4().hex}"
    )
    name = Column(String(500), nullable=False)
    description = Column(Text, default="")
    status = Column(
        SQLEnum(WorkflowStatus), nullable=False, default=WorkflowStatus.DRAFT
    )

    # Workflow definition
    nodes = Column(JSON, default=list)
    connections = Column(JSON, default=list)
    workflow_metadata = Column(JSON, default=dict)

    # Session tracking for middleware
    session_id = Column(String(255), index=True)
    owner_id = Column(String(255), index=True)

    # Performance optimization
    estimated_runtime_seconds = Column(Integer)
    resource_requirements = Column(JSON, default=dict)
    optimization_hints = Column(JSON, default=dict)

    @declared_attr
    def __table_args__(cls):
        return (
            Index(f"idx_{cls.__tablename__}_tenant_status", "tenant_id", "status"),
            Index(f"idx_{cls.__tablename__}_owner_tenant", "owner_id", "tenant_id"),
            Index(f"idx_{cls.__tablename__}_session", "session_id"),
            Index(f"idx_{cls.__tablename__}_created", "created_at"),
            CheckConstraint(
                "version > 0", name=f"check_{cls.__tablename__}_version_positive"
            ),
            UniqueConstraint(
                "tenant_id",
                "name",
                "version",
                name=f"uq_{cls.__tablename__}_tenant_name_version",
            ),
        )

    @validates("name")
    def validate_name(self, key, name):
        """Validate workflow name."""
        if not name or len(name.strip()) < 3:
            raise ValueError("Workflow name must be at least 3 characters")
        if len(name) > 500:
            raise ValueError("Workflow name must be less than 500 characters")
        return name.strip()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "session_id": self.session_id,
            "nodes": self.nodes or [],
            "connections": self.connections or [],
            "metadata": self.workflow_metadata or {},
            "security_classification": self.security_classification,
            "compliance_requirements": self.compliance_requirements or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BaseExecutionModel(Base, BaseMixin):
    """Base execution model with progress tracking."""

    __abstract__ = True

    # Core fields
    execution_id = Column(
        String(255), primary_key=True, default=lambda: f"exec_{uuid.uuid4().hex}"
    )
    workflow_id = Column(String(255), nullable=False, index=True)
    status = Column(
        SQLEnum(ExecutionStatus), nullable=False, default=ExecutionStatus.PENDING
    )

    # Progress tracking
    total_nodes = Column(Integer, default=0)
    completed_nodes = Column(Integer, default=0)
    failed_nodes = Column(Integer, default=0)
    current_node = Column(String(255))
    progress_percentage = Column(Float, default=0.0)

    # Data
    inputs = Column(JSON, default=dict)
    outputs = Column(JSON, default=dict)
    intermediate_results = Column(JSON, default=dict)

    # Error handling
    error_message = Column(Text)
    error_details = Column(JSON, default=dict)
    retry_count = Column(Integer, default=0)

    # Performance
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    runtime_seconds = Column(Float)
    resource_usage = Column(JSON, default=dict)

    # Context
    started_by = Column(String(255))
    execution_context = Column(JSON, default=dict)

    # Logging
    logs = Column(JSON, default=list)
    debug_info = Column(JSON, default=dict)

    @declared_attr
    def __table_args__(cls):
        return (
            Index(f"idx_{cls.__tablename__}_workflow", "workflow_id"),
            Index(f"idx_{cls.__tablename__}_tenant_status", "tenant_id", "status"),
            Index(f"idx_{cls.__tablename__}_started_by", "started_by"),
            Index(f"idx_{cls.__tablename__}_started_at", "started_at"),
            CheckConstraint(
                "progress_percentage >= 0 AND progress_percentage <= 100",
                name=f"check_{cls.__tablename__}_progress_range",
            ),
            CheckConstraint(
                "completed_nodes >= 0",
                name=f"check_{cls.__tablename__}_completed_positive",
            ),
            CheckConstraint(
                "failed_nodes >= 0", name=f"check_{cls.__tablename__}_failed_positive"
            ),
        )

    def start(self, started_by: str = None):
        """Mark execution as started."""
        self.status = ExecutionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.started_by = started_by

    def complete(self, outputs: Dict[str, Any] = None):
        """Mark execution as completed."""
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        if outputs:
            self.outputs = outputs
        if self.started_at:
            self.runtime_seconds = (self.completed_at - self.started_at).total_seconds()
        self.progress_percentage = 100.0

    def fail(self, error_message: str, error_details: Dict[str, Any] = None):
        """Mark execution as failed."""
        self.status = ExecutionStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        if self.started_at:
            self.runtime_seconds = (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value if self.status else None,
            "progress": {
                "total_nodes": self.total_nodes,
                "completed_nodes": self.completed_nodes,
                "failed_nodes": self.failed_nodes,
                "current_node": self.current_node,
                "progress_percentage": self.progress_percentage,
            },
            "inputs": self.inputs or {},
            "outputs": self.outputs or {},
            "error_message": self.error_message,
            "error_details": self.error_details or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "runtime_seconds": self.runtime_seconds,
            "tenant_id": self.tenant_id,
            "started_by": self.started_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BaseTemplateModel(Base, BaseMixin):
    """Base template model with analytics."""

    __abstract__ = True

    # Core fields
    template_id = Column(
        String(255), primary_key=True, default=lambda: f"template_{uuid.uuid4().hex}"
    )
    name = Column(String(500), nullable=False)
    description = Column(Text, default="")
    category = Column(SQLEnum(TemplateCategory), nullable=False)

    # Organization
    tags = Column(JSON, default=list)
    industry = Column(String(100))
    difficulty_level = Column(String(50), default="intermediate")

    # Template definition
    workflow_definition = Column(JSON, nullable=False)
    preview_image = Column(String(1000))
    documentation = Column(Text)

    # Analytics
    usage_count = Column(Integer, default=0)
    rating_average = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    last_used = Column(DateTime(timezone=True))

    # Enterprise
    is_certified = Column(Boolean, default=False)
    certification_level = Column(String(50))
    compliance_frameworks = Column(JSON, default=list)
    security_requirements = Column(JSON, default=dict)

    # Visibility
    is_public = Column(Boolean, default=False)

    @declared_attr
    def __table_args__(cls):
        return (
            Index(f"idx_{cls.__tablename__}_category", "category"),
            Index(f"idx_{cls.__tablename__}_tenant_public", "tenant_id", "is_public"),
            Index(f"idx_{cls.__tablename__}_certified", "is_certified"),
            Index(f"idx_{cls.__tablename__}_usage", "usage_count"),
            CheckConstraint(
                "usage_count >= 0", name=f"check_{cls.__tablename__}_usage_positive"
            ),
            CheckConstraint(
                "rating_average >= 0 AND rating_average <= 5",
                name=f"check_{cls.__tablename__}_rating_range",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value if self.category else None,
            "tags": self.tags or [],
            "difficulty_level": self.difficulty_level,
            "workflow_definition": self.workflow_definition or {},
            "usage_count": self.usage_count,
            "rating_average": self.rating_average,
            "is_certified": self.is_certified,
            "tenant_id": self.tenant_id,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BaseSecurityEventModel(Base, BaseMixin, ComplianceMixin):
    """Base security event model for monitoring."""

    __abstract__ = True

    # Core fields
    event_id = Column(
        String(255), primary_key=True, default=lambda: f"sec_event_{uuid.uuid4().hex}"
    )
    event_type = Column(SQLEnum(SecurityEventType), nullable=False)
    severity = Column(String(50), nullable=False, default="info")
    description = Column(Text)

    # Associated resources
    workflow_id = Column(String(255), index=True)
    execution_id = Column(String(255), index=True)
    resource_type = Column(String(100))
    resource_id = Column(String(255))

    # User context
    user_id = Column(String(255), index=True)
    session_id = Column(String(255), index=True)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    geographic_location = Column(JSON)

    # Event data
    event_data = Column(JSON, default=dict)
    threat_indicators = Column(JSON, default=dict)
    response_actions = Column(JSON, default=list)

    # Detection
    detection_method = Column(String(100))
    confidence_score = Column(Float)
    false_positive = Column(Boolean, default=False)

    # Timing
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    detected_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    resolved_at = Column(DateTime(timezone=True))

    @declared_attr
    def __table_args__(cls):
        return (
            Index(f"idx_{cls.__tablename__}_type_severity", "event_type", "severity"),
            Index(
                f"idx_{cls.__tablename__}_tenant_occurred", "tenant_id", "occurred_at"
            ),
            Index(f"idx_{cls.__tablename__}_user", "user_id"),
            Index(f"idx_{cls.__tablename__}_session", "session_id"),
            CheckConstraint(
                "confidence_score >= 0 AND confidence_score <= 1",
                name=f"check_{cls.__tablename__}_confidence_range",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if self.event_type else None,
            "severity": self.severity,
            "description": self.description,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "event_data": self.event_data or {},
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


class BaseAuditLogModel(Base, BaseMixin, ComplianceMixin):
    """Base audit log model for compliance."""

    __abstract__ = True

    # Core fields
    audit_id = Column(
        String(255), primary_key=True, default=lambda: f"audit_{uuid.uuid4().hex}"
    )
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255))
    workflow_id = Column(String(255), index=True)

    # User context
    user_id = Column(String(255), index=True)
    user_email = Column(String(255))
    user_roles = Column(JSON, default=list)
    session_id = Column(String(255), index=True)

    # Change tracking
    old_values = Column(JSON)
    new_values = Column(JSON)
    changes = Column(JSON)

    # Request details
    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(255))
    api_endpoint = Column(String(500))
    http_method = Column(String(10))

    # Result
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)
    response_code = Column(Integer)

    # Data classification
    data_classification = Column(String(50))

    # Timing
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    duration_ms = Column(Integer)

    # Integrity
    checksum = Column(String(512))
    signature = Column(Text)

    @declared_attr
    def __table_args__(cls):
        return (
            Index(
                f"idx_{cls.__tablename__}_action_resource", "action", "resource_type"
            ),
            Index(
                f"idx_{cls.__tablename__}_tenant_timestamp", "tenant_id", "timestamp"
            ),
            Index(f"idx_{cls.__tablename__}_user_timestamp", "user_id", "timestamp"),
            Index(f"idx_{cls.__tablename__}_session", "session_id"),
            Index(f"idx_{cls.__tablename__}_success", "success"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "audit_id": self.audit_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "success": self.success,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class BaseComplianceModel(Base, BaseMixin):
    """Base compliance assessment model."""

    __abstract__ = True

    # Core fields
    assessment_id = Column(
        String(255), primary_key=True, default=lambda: f"compliance_{uuid.uuid4().hex}"
    )
    framework = Column(SQLEnum(ComplianceFramework), nullable=False)

    # Scope
    resource_type = Column(String(100))
    resource_id = Column(String(255))

    # Results
    overall_score = Column(Float, nullable=False)
    violations = Column(JSON, default=list)
    recommendations = Column(JSON, default=list)
    evidence = Column(JSON, default=dict)

    # Assessment details
    assessment_date = Column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    assessor = Column(String(255))
    assessment_method = Column(String(100))

    # Remediation
    remediation_plan = Column(JSON, default=dict)
    remediation_deadline = Column(DateTime(timezone=True))
    remediation_status = Column(String(50), default="pending")

    # Approval
    approved_by = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
    certification_valid_until = Column(DateTime(timezone=True))

    @declared_attr
    def __table_args__(cls):
        return (
            Index(
                f"idx_{cls.__tablename__}_framework_tenant", "framework", "tenant_id"
            ),
            Index(f"idx_{cls.__tablename__}_assessment_date", "assessment_date"),
            Index(f"idx_{cls.__tablename__}_score", "overall_score"),
            CheckConstraint(
                "overall_score >= 0 AND overall_score <= 100",
                name=f"check_{cls.__tablename__}_score_range",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "assessment_id": self.assessment_id,
            "framework": self.framework.value if self.framework else None,
            "tenant_id": self.tenant_id,
            "overall_score": self.overall_score,
            "violations": self.violations or [],
            "assessment_date": (
                self.assessment_date.isoformat() if self.assessment_date else None
            ),
            "remediation_status": self.remediation_status,
        }
