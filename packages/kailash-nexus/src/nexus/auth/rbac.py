"""RBAC (Role-Based Access Control) for Nexus Authentication.

SPEC-06 Migration: Core RBAC logic extracted to kailash.trust.auth.rbac.
This module retains the Starlette/FastAPI RBACMiddleware and convenience
decorators/dependency factories.

Note: Do NOT use ``from __future__ import annotations`` in this module.
FastAPI inspects parameter annotations at runtime to recognize special types
like Request. PEP 563 deferred annotations turn them into strings, which
prevents FastAPI from injecting the Request object into callable dependencies.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kailash.trust.auth.exceptions import (
    InsufficientPermissionError,
    InsufficientRoleError,
)
from kailash.trust.auth.models import AuthenticatedUser
from kailash.trust.auth.rbac import (
    RBACManager,
    RoleDefinition,
    matches_permission,
    matches_permission_set,
)

logger = logging.getLogger(__name__)

# Re-export core RBAC types for backward compatibility
__all__ = [
    "RoleDefinition",
    "RBACManager",
    "RBACMiddleware",
    "matches_permission",
    "matches_permission_set",
    "require_role_dep",
    "require_permission_dep",
    "roles_required",
    "permissions_required",
]


class RBACMiddleware(BaseHTTPMiddleware):
    """RBAC middleware for route-level authorization context.

    Attaches RBAC context (resolved permissions, rbac_manager) to request
    state for downstream handlers and dependencies.

    Note: This middleware does NOT block requests. Use FastAPI dependencies
    (require_role_dep, require_permission_dep) for enforcement.
    """

    def __init__(
        self,
        app: Any,
        roles: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        default_role: Optional[str] = None,
    ):
        super().__init__(app)
        self.rbac_manager = RBACManager(roles=roles, default_role=default_role)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Attach RBAC context to request state."""
        user = getattr(request.state, "user", None)

        if user:
            permissions = self.rbac_manager.get_user_permissions(user)
            request.state.user_permissions = permissions
            request.state.rbac_manager = self.rbac_manager

            logger.debug(
                "RBAC: User %s has roles %s, %d permissions",
                user.user_id,
                user.roles,
                len(permissions),
            )

        return await call_next(request)


# --- FastAPI Dependency Factories ---


def require_role_dep(*roles: str):
    """Create dependency that requires user to have one of the specified roles.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(
            user: AuthenticatedUser = Depends(require_role_dep("admin"))
        ):
            return {"admin": True}

    Args:
        *roles: Roles that grant access (user needs any one)

    Returns:
        FastAPI dependency (RequireRole instance)
    """
    from nexus.auth.dependencies import RequireRole

    return RequireRole(*roles)


def require_permission_dep(*permissions: str):
    """Create dependency that requires user to have one of the permissions.

    Usage:
        @app.delete("/users/{id}")
        async def delete_user(
            user: AuthenticatedUser = Depends(require_permission_dep("delete:users"))
        ):
            ...

    Args:
        *permissions: Permissions that grant access (user needs any one)

    Returns:
        FastAPI dependency (RequirePermission instance)
    """
    from nexus.auth.dependencies import RequirePermission

    return RequirePermission(*permissions)


# --- Decorators for Class-Based Views ---


def roles_required(*roles: str):
    """Decorator that requires specific roles for a handler.

    Usage:
        @app.get("/admin")
        @roles_required("admin", "super_admin")
        async def admin_endpoint(request: Request):
            ...

    Note: Prefer Depends(require_role_dep()) for new code.

    Args:
        *roles: Required roles (user needs any one)

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            user = getattr(request.state, "user", None)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )

            if not user.has_any_role(*roles):
                # SECURITY: Don't reveal required roles to potential attacker
                logger.warning(
                    "Access denied: user %s lacks required roles %s",
                    user.user_id,
                    roles,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden"},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def permissions_required(*permissions: str):
    """Decorator that requires specific permissions for a handler.

    Usage:
        @app.post("/articles")
        @permissions_required("write:articles")
        async def create_article(request: Request):
            ...

    Note: Prefer Depends(require_permission_dep()) for new code.

    Args:
        *permissions: Required permissions (user needs any one)

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            user = getattr(request.state, "user", None)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )

            if not user.has_any_permission(*permissions):
                # SECURITY: Don't reveal required permissions to potential attacker
                logger.warning(
                    "Access denied: user %s lacks required permissions %s",
                    user.user_id,
                    permissions,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden"},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
