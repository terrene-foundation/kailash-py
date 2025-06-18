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

from .exceptions import (
    AuthenticationError,
    InvalidTokenError,
    PermissionDeniedError,
    TokenBlacklistedError,
    TokenExpiredError,
)

# Import without circular dependencies
from .jwt_auth import JWTAuthManager
from .models import AuthenticationResult, JWTConfig, TokenPair, TokenPayload, UserClaims
from .utils import generate_key_pair, generate_secret_key, parse_bearer_token

# Import other components (check for circular deps)
try:
    from .access_control import (
        MiddlewareAccessControlManager,
        MiddlewareAuthenticationMiddleware,
    )
    from .auth_manager import AuthLevel, MiddlewareAuthManager

    _has_access_control = True
except ImportError:
    # These imports might fail due to circular dependencies with communication
    _has_access_control = False

# KailashJWTAuthManager has been consolidated into JWTAuthManager
# For backward compatibility, use JWTAuthManager directly

__all__ = [
    # Core authentication (always available)
    "JWTAuthManager",
    "JWTConfig",
    "TokenPayload",
    "TokenPair",
    "UserClaims",
    "AuthenticationResult",
    # Exceptions
    "AuthenticationError",
    "TokenExpiredError",
    "InvalidTokenError",
    "TokenBlacklistedError",
    "PermissionDeniedError",
    # Utilities
    "generate_secret_key",
    "generate_key_pair",
    "parse_bearer_token",
]

# Add access control components if available
if _has_access_control:
    __all__.extend(
        [
            "MiddlewareAuthManager",
            "AuthLevel",
            "MiddlewareAccessControlManager",
            "MiddlewareAuthenticationMiddleware",
        ]
    )
