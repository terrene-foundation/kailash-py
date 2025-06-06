"""
Database models and storage backend for Kailash Workflow Studio.

This module provides:
- SQLAlchemy models for workflows, nodes, executions, and user data
- Database initialization and migration support
- Repository classes for data access
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
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
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


class Workflow(Base):
    """Workflow database model"""

    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    definition = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    is_published = Column(Boolean, default=False)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    executions = relationship(
        "WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan"
    )
    versions = relationship(
        "WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_workflow_tenant_created", "tenant_id", "created_at"),
        Index("idx_workflow_tenant_name", "tenant_id", "name"),
    )


class WorkflowVersion(Base):
    """Workflow version history"""

    __tablename__ = "workflow_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=False)
    version = Column(Integer, nullable=False)
    definition = Column(JSON, nullable=False)
    change_message = Column(Text)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="versions")

    __table_args__ = (
        Index("idx_version_workflow_version", "workflow_id", "version", unique=True),
    )


class CustomNode(Base):
    """Custom node definitions created by users"""

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
    implementation_type = Column(String(50))  # 'python', 'workflow', 'api'
    implementation = Column(JSON)  # Implementation details

    # Metadata
    is_published = Column(Boolean, default=False)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_node_tenant_name", "tenant_id", "name", unique=True),
        Index("idx_node_tenant_category", "tenant_id", "category"),
    )


class WorkflowExecution(Base):
    """Workflow execution history"""

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

    # Performance metrics
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    execution_time_ms = Column(Integer)

    # Node execution details
    node_executions = Column(JSON)  # Detailed per-node execution data

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")

    __table_args__ = (
        Index("idx_execution_tenant_started", "tenant_id", "started_at"),
        Index("idx_execution_workflow_started", "workflow_id", "started_at"),
        Index("idx_execution_status", "status"),
    )


class UserPreferences(Base):
    """User preferences and settings"""

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

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pref_tenant_user", "tenant_id", "user_id", unique=True),
    )


class WorkflowTemplate(Base):
    """Pre-built workflow templates"""

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


class WorkflowPermission(Base):
    """Workflow-level permissions"""

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

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    workflow = relationship("Workflow", backref="permissions")

    __table_args__ = (
        Index("idx_workflow_perm_workflow", "workflow_id"),
        Index("idx_workflow_perm_user", "user_id"),
        Index("idx_workflow_perm_tenant", "tenant_id"),
    )


class NodePermission(Base):
    """Node-level permissions"""

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

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    workflow = relationship("Workflow", backref="node_permissions")

    __table_args__ = (
        Index("idx_node_perm_workflow", "workflow_id"),
        Index("idx_node_perm_node", "workflow_id", "node_id"),
        Index("idx_node_perm_user", "user_id"),
        Index("idx_node_perm_tenant", "tenant_id"),
    )


class AccessLog(Base):
    """Audit log for access attempts"""

    __tablename__ = "access_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)

    # What was accessed?
    resource_type = Column(String(50), nullable=False)  # workflow, node
    resource_id = Column(String(255), nullable=False)
    permission = Column(String(50), nullable=False)

    # Result
    allowed = Column(Boolean, nullable=False)
    reason = Column(Text)

    # Context
    ip_address = Column(String(50))
    user_agent = Column(String(255))
    session_id = Column(String(36))

    # Timestamp
    timestamp = Column(DateTime, default=func.now(), index=True)

    __table_args__ = (
        Index("idx_access_log_user_time", "user_id", "timestamp"),
        Index("idx_access_log_resource", "resource_type", "resource_id", "timestamp"),
    )


class UserGroup(Base):
    """User groups for permission management"""

    __tablename__ = "user_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Group permissions (can be inherited)
    permissions = Column(JSON)

    # Metadata
    created_by = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    members = relationship(
        "UserGroupMember", back_populates="group", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_group_tenant_name", "tenant_id", "name", unique=True),)


class UserGroupMember(Base):
    """User membership in groups"""

    __tablename__ = "user_group_members"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("user_groups.id"), nullable=False)
    user_id = Column(String(36), nullable=False)

    # Membership details
    role = Column(String(50), default="member")  # member, admin
    joined_at = Column(DateTime, default=func.now())
    added_by = Column(String(255))

    # Relationships
    group = relationship("UserGroup", back_populates="members")

    __table_args__ = (
        Index("idx_group_member", "group_id", "user_id", unique=True),
        Index("idx_member_user", "user_id"),
    )


# Repository classes for data access
class WorkflowRepository:
    """Repository for workflow operations"""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        tenant_id: str,
        name: str,
        description: str,
        definition: Dict[str, Any],
        created_by: str = None,
    ) -> Workflow:
        """Create a new workflow"""
        workflow = Workflow(
            tenant_id=tenant_id,
            name=name,
            description=description,
            definition=definition,
            created_by=created_by,
        )
        self.session.add(workflow)
        self.session.commit()

        # Create initial version
        self.create_version(workflow.id, 1, definition, "Initial version", created_by)

        return workflow

    def update(
        self, workflow_id: str, updates: Dict[str, Any], updated_by: str = None
    ) -> Workflow:
        """Update a workflow"""
        workflow = self.session.query(Workflow).filter_by(id=workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Update fields
        for key, value in updates.items():
            if hasattr(workflow, key):
                setattr(workflow, key, value)

        # If definition changed, create new version
        if "definition" in updates:
            workflow.version += 1
            self.create_version(
                workflow_id,
                workflow.version,
                updates["definition"],
                updates.get("change_message", "Updated workflow"),
                updated_by,
            )

        self.session.commit()
        return workflow

    def create_version(
        self,
        workflow_id: str,
        version: int,
        definition: Dict[str, Any],
        change_message: str,
        created_by: str = None,
    ):
        """Create a workflow version"""
        version_record = WorkflowVersion(
            workflow_id=workflow_id,
            version=version,
            definition=definition,
            change_message=change_message,
            created_by=created_by,
        )
        self.session.add(version_record)
        self.session.commit()

    def get(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID"""
        return self.session.query(Workflow).filter_by(id=workflow_id).first()

    def list(self, tenant_id: str, limit: int = 100, offset: int = 0) -> List[Workflow]:
        """List workflows for a tenant"""
        return (
            self.session.query(Workflow)
            .filter_by(tenant_id=tenant_id)
            .order_by(Workflow.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def delete(self, workflow_id: str):
        """Delete a workflow"""
        workflow = self.get(workflow_id)
        if workflow:
            self.session.delete(workflow)
            self.session.commit()


class CustomNodeRepository:
    """Repository for custom node operations"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, tenant_id: str, node_data: Dict[str, Any]) -> CustomNode:
        """Create a custom node"""
        node = CustomNode(tenant_id=tenant_id, **node_data)
        self.session.add(node)
        self.session.commit()
        return node

    def update(self, node_id: str, updates: Dict[str, Any]) -> CustomNode:
        """Update a custom node"""
        node = self.session.query(CustomNode).filter_by(id=node_id).first()
        if not node:
            raise ValueError(f"Custom node {node_id} not found")

        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)

        self.session.commit()
        return node

    def list(self, tenant_id: str) -> List[CustomNode]:
        """List custom nodes for a tenant"""
        return (
            self.session.query(CustomNode)
            .filter_by(tenant_id=tenant_id)
            .order_by(CustomNode.category, CustomNode.name)
            .all()
        )

    def get(self, node_id: str) -> Optional[CustomNode]:
        """Get a custom node by ID"""
        return self.session.query(CustomNode).filter_by(id=node_id).first()

    def delete(self, node_id: str):
        """Delete a custom node"""
        node = self.get(node_id)
        if node:
            self.session.delete(node)
            self.session.commit()


class ExecutionRepository:
    """Repository for execution operations"""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self, workflow_id: str, tenant_id: str, parameters: Dict[str, Any] = None
    ) -> WorkflowExecution:
        """Create an execution record"""
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            status="pending",
            parameters=parameters,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(execution)
        self.session.commit()
        return execution

    def update_status(
        self,
        execution_id: str,
        status: str,
        result: Dict[str, Any] = None,
        error: str = None,
    ):
        """Update execution status"""
        execution = (
            self.session.query(WorkflowExecution).filter_by(id=execution_id).first()
        )
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = status
        if result is not None:
            execution.result = result
        if error is not None:
            execution.error = error

        if status in ["completed", "failed"]:
            execution.completed_at = datetime.now(timezone.utc)
            if execution.started_at:
                execution.execution_time_ms = int(
                    (execution.completed_at - execution.started_at).total_seconds()
                    * 1000
                )

        self.session.commit()

    def get(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get execution by ID"""
        return self.session.query(WorkflowExecution).filter_by(id=execution_id).first()

    def list_for_workflow(
        self, workflow_id: str, limit: int = 50
    ) -> List[WorkflowExecution]:
        """List executions for a workflow"""
        return (
            self.session.query(WorkflowExecution)
            .filter_by(workflow_id=workflow_id)
            .order_by(WorkflowExecution.started_at.desc())
            .limit(limit)
            .all()
        )


# Database initialization
def init_database(db_path: str = None) -> tuple[sessionmaker, Engine]:
    """Initialize the database"""
    if db_path is None:
        db_path = Path.home() / ".kailash" / "studio.db"

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return SessionLocal, engine


# Context manager for database sessions


@contextmanager
def get_db_session(SessionLocal):
    """Provide a transactional scope for database operations"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
