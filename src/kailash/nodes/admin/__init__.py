"""Admin tool framework for enterprise user and permission management.

This module provides comprehensive admin functionality including user management,
role-based access control (RBAC), attribute-based access control (ABAC),
audit logging, and security event tracking.

Architecture:
- Built on Session 065's async database and ABAC infrastructure
- Django Admin-inspired features with SDK-native implementation
- Enterprise-grade scalability (500+ concurrent users)
- Multi-tenant support with data isolation
- Comprehensive audit trails for compliance

Core Components:
- UserManagementNode: Complete user lifecycle management
- RoleManagementNode: Role assignment and hierarchy management
- PermissionCheckNode: Real-time permission evaluation
- AuditLogNode: Comprehensive activity logging
- SecurityEventNode: Security incident tracking
"""

from .user_management import UserManagementNode
from .role_management import RoleManagementNode
from .permission_check import PermissionCheckNode
from .audit_log import AuditLogNode
from .security_event import SecurityEventNode

__all__ = [
    # Core admin nodes
    "UserManagementNode",
    "RoleManagementNode", 
    "PermissionCheckNode",
    "AuditLogNode",
    "SecurityEventNode",
]