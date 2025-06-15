"""
Enhanced Database Models for Kailash Middleware

Consolidates and enhances existing database models from api/database.py
with middleware-specific features and event integration.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class WorkflowModel(Base):
    """Enhanced workflow model with middleware integration"""

    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    definition = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    is_published = Column(Boolean, default=False)

    # Middleware enhancements
    session_id = Column(String(36), nullable=True, index=True)  # Associated session
    agent_ui_config = Column(JSON)  # UI-specific configuration
    real_time_enabled = Column(Boolean, default=True)  # Enable real-time updates

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    executions = relationship(
        "WorkflowExecutionModel",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    versions = relationship(
        "WorkflowVersionModel", back_populates="workflow", cascade="all, delete-orphan"
    )
    permissions = relationship(
        "WorkflowPermissionModel",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_workflow_tenant_created", "tenant_id", "created_at"),
        Index("idx_workflow_tenant_name", "tenant_id", "name"),
        Index("idx_workflow_session", "session_id"),
    )


class WorkflowVersionModel(Base):
    """Enhanced workflow version with change tracking"""

    __tablename__ = "workflow_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    version = Column(Integer, nullable=False)
    definition = Column(JSON, nullable=False)
    change_message = Column(Text)

    # Middleware enhancements
    diff_data = Column(JSON)  # Structured diff from previous version
    migration_notes = Column(Text)  # Notes about breaking changes

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())

    # Relationships
    workflow = relationship("WorkflowModel", back_populates="versions")

    __table_args__ = (
        Index("idx_version_workflow_version", "workflow_id", "version", unique=True),
    )


class CustomNodeModel(Base):
    """Enhanced custom node with middleware features"""

    __tablename__ = "custom_nodes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), default="custom")
    description = Column(Text)
    icon = Column(String(50))
    color = Column(String(7))  # Hex color

    # Node configuration
    parameters = Column(JSON)  # Parameter definitions
    inputs = Column(JSON)  # Input port definitions
    outputs = Column(JSON)  # Output port definitions

    # Implementation
    implementation_type = Column(String(50))  # 'python', 'workflow', 'api', 'kailash'
    implementation = Column(JSON)  # Implementation details

    # Middleware enhancements
    middleware_config = Column(JSON)  # Middleware-specific configuration
    real_time_capable = Column(Boolean, default=False)  # Supports real-time updates
    event_types = Column(JSON)  # List of event types this node can emit

    # Metadata
    is_published = Column(Boolean, default=False)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_node_tenant_name", "tenant_id", "name", unique=True),
        Index("idx_node_tenant_category", "tenant_id", "category"),
    )


class WorkflowExecutionModel(Base):
    """Enhanced execution model with real-time tracking"""

    __tablename__ = "workflow_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    tenant_id = Column(String(36), nullable=False, index=True)
    status = Column(
        String(50), nullable=False
    )  # 'pending', 'running', 'completed', 'failed'

    # Execution details
    parameters = Column(JSON)
    result = Column(JSON)
    error = Column(Text)

    # Middleware enhancements
    session_id = Column(String(36), nullable=True, index=True)  # Associated session
    real_time_events = Column(JSON)  # List of real-time events emitted
    agent_ui_data = Column(JSON)  # UI-specific execution data
    execution_metrics = Column(JSON)  # Performance and resource metrics

    # Performance metrics
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    execution_time_ms = Column(Integer)

    # Node execution details
    node_executions = Column(JSON)  # Detailed per-node execution data

    # Relationships
    workflow = relationship("WorkflowModel", back_populates="executions")

    __table_args__ = (
        Index("idx_execution_tenant_started", "tenant_id", "started_at"),
        Index("idx_execution_workflow_started", "workflow_id", "started_at"),
        Index("idx_execution_status", "status"),
        Index("idx_execution_session", "session_id"),
    )


class UserPreferencesModel(Base):
    """Enhanced user preferences with middleware features"""

    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False)
    user_id = Column(String(255), nullable=False)

    # UI preferences
    theme = Column(String(20), default="light")
    canvas_settings = Column(JSON)  # Zoom level, grid settings, etc.

    # Workflow preferences
    default_parameters = Column(JSON)
    favorite_nodes = Column(JSON)
    recent_workflows = Column(JSON)

    # Middleware enhancements
    real_time_preferences = Column(JSON)  # Real-time update preferences
    agent_ui_settings = Column(JSON)  # Agent-UI specific settings
    notification_settings = Column(JSON)  # Event notification preferences

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pref_tenant_user", "tenant_id", "user_id", unique=True),
    )


class WorkflowTemplateModel(Base):
    """Enhanced workflow templates with middleware integration"""

    __tablename__ = "workflow_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=True)  # Null for global templates
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    description = Column(Text)
    thumbnail = Column(String(255))

    # Template definition
    definition = Column(JSON, nullable=False)
    default_parameters = Column(JSON)

    # Middleware enhancements
    middleware_features = Column(JSON)  # Required middleware features
    agent_ui_template = Column(JSON)  # Agent-UI template configuration
    real_time_template = Column(JSON)  # Real-time update template

    # Metadata
    is_public = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_template_category", "category"),
        Index("idx_template_public", "is_public"),
    )


class WorkflowPermissionModel(Base):
    """Enhanced workflow permissions with middleware access control"""

    __tablename__ = "workflow_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    tenant_id = Column(String(36), nullable=False, index=True)

    # Who does this permission apply to?
    user_id = Column(String(36), nullable=True)  # Specific user
    role = Column(String(50), nullable=True)  # Role-based
    group_id = Column(String(36), nullable=True)  # Group-based

    # What permission?
    permission = Column(
        String(50), nullable=False
    )  # view, execute, modify, delete, share, admin
    effect = Column(
        String(20), nullable=False, default="allow"
    )  # allow, deny, conditional

    # Conditions (JSON object for flexibility)
    conditions = Column(JSON)

    # Middleware enhancements
    session_restrictions = Column(JSON)  # Session-based restrictions
    real_time_permissions = Column(JSON)  # Real-time access permissions
    agent_ui_permissions = Column(JSON)  # Agent-UI specific permissions

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    workflow = relationship("WorkflowModel", back_populates="permissions")

    __table_args__ = (
        Index("idx_workflow_perm_workflow", "workflow_id"),
        Index("idx_workflow_perm_user", "user_id"),
        Index("idx_workflow_perm_tenant", "tenant_id"),
    )


class NodePermissionModel(Base):
    """Enhanced node permissions with middleware features"""

    __tablename__ = "node_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    node_id = Column(String(255), nullable=False)  # Node ID within workflow
    tenant_id = Column(String(36), nullable=False, index=True)

    # Who does this permission apply to?
    user_id = Column(String(36), nullable=True)
    role = Column(String(50), nullable=True)
    group_id = Column(String(36), nullable=True)

    # What permission?
    permission = Column(
        String(50), nullable=False
    )  # execute, read_output, write_input, skip, mask_output
    effect = Column(String(20), nullable=False, default="allow")

    # Conditions and special handling
    conditions = Column(JSON)
    masked_fields = Column(JSON)  # Fields to mask in output
    redirect_node = Column(String(255))  # Alternative node if access denied

    # Middleware enhancements
    real_time_masking = Column(JSON)  # Real-time output masking rules
    event_filtering = Column(JSON)  # Event filtering rules for this node

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    workflow = relationship("WorkflowModel", backref="node_permissions")

    __table_args__ = (
        Index("idx_node_perm_workflow", "workflow_id"),
        Index("idx_node_perm_node", "workflow_id", "node_id"),
        Index("idx_node_perm_user", "user_id"),
        Index("idx_node_perm_tenant", "tenant_id"),
    )


class AccessLogModel(Base):
    """Enhanced access log with middleware event integration"""

    __tablename__ = "access_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)

    # What was accessed?
    resource_type = Column(String(50), nullable=False)  # workflow, node, session, api
    resource_id = Column(String(255), nullable=False)
    permission = Column(String(50), nullable=False)

    # Result
    allowed = Column(Boolean, nullable=False)
    reason = Column(Text)

    # Context
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    session_id = Column(String(36))

    # Middleware enhancements
    event_id = Column(String(36))  # Associated middleware event
    real_time_logged = Column(
        Boolean, default=False
    )  # Whether logged to real-time stream
    agent_ui_context = Column(JSON)  # Agent-UI specific context

    # Timestamp
    timestamp = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index("idx_access_log_user_time", "user_id", "timestamp"),
        Index("idx_access_log_resource", "resource_type", "resource_id", "timestamp"),
        Index("idx_access_log_event", "event_id"),
    )


class UserGroupModel(Base):
    """Enhanced user groups with middleware features"""

    __tablename__ = "user_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Group permissions (can be inherited)
    permissions = Column(JSON)

    # Middleware enhancements
    middleware_permissions = Column(JSON)  # Middleware-specific permissions
    real_time_access = Column(JSON)  # Real-time feature access
    agent_ui_access = Column(JSON)  # Agent-UI access configuration

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    members = relationship(
        "UserGroupMemberModel", back_populates="group", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_group_tenant_name", "tenant_id", "name", unique=True),)


class UserGroupMemberModel(Base):
    """Enhanced group membership with middleware tracking"""

    __tablename__ = "user_group_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("user_groups.id"), nullable=False)
    user_id = Column(String(36), nullable=False)

    # Membership details
    role = Column(String(50), default="member")  # member, admin
    joined_at = Column(DateTime, default=func.now())
    added_by = Column(String(255))

    # Middleware enhancements
    middleware_role_overrides = Column(JSON)  # Role overrides for middleware features

    # Relationships
    group = relationship("UserGroupModel", back_populates="members")

    __table_args__ = (
        Index("idx_group_member", "group_id", "user_id", unique=True),
        Index("idx_member_user", "user_id"),
    )


class MiddlewareSessionModel(Base):
    """Middleware-specific session tracking"""

    __tablename__ = "middleware_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)

    # Session details
    session_type = Column(String(50), nullable=False)  # agent_ui, api, websocket, mcp
    status = Column(String(20), default="active")  # active, inactive, expired

    # Session data
    session_metadata = Column(JSON)  # Session-specific metadata
    preferences = Column(JSON)  # User preferences for this session
    context = Column(JSON)  # Session context data

    # Connection details
    connection_id = Column(String(255))  # WebSocket/API connection ID
    ip_address = Column(String(50))
    user_agent = Column(String(255))

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    last_activity = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)

    __table_args__ = (
        Index("idx_session_tenant_user", "tenant_id", "user_id"),
        Index("idx_session_status", "status"),
        Index("idx_session_type", "session_type"),
        Index("idx_session_activity", "last_activity"),
    )


class MiddlewareEventModel(Base):
    """Middleware event logging for audit and replay"""

    __tablename__ = "middleware_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)

    # Event details
    event_type = Column(String(100), nullable=False, index=True)
    event_source = Column(
        String(50), nullable=False
    )  # agent_ui, api_gateway, realtime, etc.

    # Event data
    data = Column(JSON, nullable=False)
    context = Column(JSON)  # Additional context

    # Associated entities
    session_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    workflow_id = Column(String(36), nullable=True, index=True)
    execution_id = Column(String(36), nullable=True, index=True)

    # Event metadata
    correlation_id = Column(String(36))  # For tracing related events
    sequence_number = Column(Integer)  # For ordering within correlation

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    error_message = Column(Text)

    # Timestamp
    timestamp = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index("idx_event_type_time", "event_type", "timestamp"),
        Index("idx_event_correlation", "correlation_id", "sequence_number"),
        Index("idx_event_processed", "processed"),
    )
