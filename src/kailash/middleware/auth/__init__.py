"""
Enterprise Authentication and Authorization for Kailash Middleware

Provides comprehensive authentication, authorization, and tenant isolation
capabilities for the Kailash middleware layer.

Features:
- JWT-based authentication with refresh tokens
- Role-based access control (RBAC)
- Attribute-based access control (ABAC)
- Multi-tenant isolation
- API key authentication
- OAuth2/OIDC integration
- Session management
- Audit logging
"""

from .access_control import (
    MiddlewareAccessControlManager,
    MiddlewareAuthenticationMiddleware,
)
from .auth_manager import AuthLevel, MiddlewareAuthManager
from .kailash_jwt_auth import KailashJWTAuthManager

__all__ = [
    # Core authentication
    "KailashJWTAuthManager",
    "MiddlewareAuthManager",  # Main auth manager using SDK nodes
    "AuthLevel",
    # Authorization & Access Control
    "MiddlewareAccessControlManager",
    "MiddlewareAuthenticationMiddleware",
]
