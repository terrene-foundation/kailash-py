"""
Enterprise Database Layer for Kailash Middleware

Consolidates existing Kailash database implementations with middleware-specific
enhancements for workflow management, user data, and audit logging.

Features:
- Enhanced SQLAlchemy models with middleware integration
- Repository pattern with event streaming
- Multi-tenant data isolation
- Advanced permission models
- Audit logging with real-time events
- Connection pooling and optimization
"""

from .migrations import MiddlewareMigrationRunner
from .models import (
    AccessLogModel,
    Base,
    CustomNodeModel,
    NodePermissionModel,
    UserGroupMemberModel,
    UserGroupModel,
    UserPreferencesModel,
    WorkflowExecutionModel,
    WorkflowModel,
    WorkflowPermissionModel,
    WorkflowTemplateModel,
    WorkflowVersionModel,
)
from .repositories import (
    MiddlewareExecutionRepository,
    MiddlewarePermissionRepository,
    MiddlewareUserRepository,
    MiddlewareWorkflowRepository,
)
from .session_manager import MiddlewareDatabaseManager, get_middleware_db_session

__all__ = [
    # Models
    "Base",
    "WorkflowModel",
    "WorkflowVersionModel",
    "CustomNodeModel",
    "WorkflowExecutionModel",
    "UserPreferencesModel",
    "WorkflowTemplateModel",
    "WorkflowPermissionModel",
    "NodePermissionModel",
    "AccessLogModel",
    "UserGroupModel",
    "UserGroupMemberModel",
    # Repositories
    "MiddlewareWorkflowRepository",
    "MiddlewareExecutionRepository",
    "MiddlewareUserRepository",
    "MiddlewarePermissionRepository",
    # Session Management
    "MiddlewareDatabaseManager",
    "get_middleware_db_session",
    # Migrations
    "MiddlewareMigrationRunner",
]
