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

from .models import (
    Base,
    WorkflowModel,
    WorkflowVersionModel,
    CustomNodeModel,
    WorkflowExecutionModel,
    UserPreferencesModel,
    WorkflowTemplateModel,
    WorkflowPermissionModel,
    NodePermissionModel,
    AccessLogModel,
    UserGroupModel,
    UserGroupMemberModel
)

from .repositories import (
    MiddlewareWorkflowRepository, 
    MiddlewareExecutionRepository,
    MiddlewareUserRepository,
    MiddlewarePermissionRepository
)

from .session_manager import MiddlewareDatabaseManager, get_middleware_db_session
from .migrations import MiddlewareMigrationRunner

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