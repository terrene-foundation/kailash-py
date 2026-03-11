"""FastAPI dependencies for authentication.

Provides dependency functions for endpoint-level authentication checks.

Note: Do NOT use `from __future__ import annotations` in this module.
FastAPI inspects parameter annotations at runtime to recognize special types
like Request. PEP 563 deferred annotations turn them into strings, which
prevents FastAPI from injecting the Request object into callable dependencies.
"""

from typing import Optional

from fastapi import HTTPException, Request
from nexus.auth.models import AuthenticatedUser


def get_current_user(request: Request) -> AuthenticatedUser:
    """Get the current authenticated user.

    Must be used after JWTMiddleware has processed the request.

    Usage:
        @app.get("/profile")
        async def get_profile(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """Get the current user if authenticated, None otherwise.

    Useful for endpoints that work for both authenticated and anonymous users.
    """
    return getattr(request.state, "user", None)


def require_auth(request: Request) -> AuthenticatedUser:
    """Require authentication (alias for get_current_user)."""
    return get_current_user(request)


class RequireRole:
    """Dependency that requires specific roles.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(
            user: AuthenticatedUser = Depends(RequireRole("admin", "super_admin"))
        ):
            return {"admin": True}
    """

    def __init__(self, *roles: str):
        self.roles = roles

    def __call__(self, request: Request) -> AuthenticatedUser:
        user = get_current_user(request)
        if not user.has_any_role(*self.roles):
            import logging

            logging.getLogger(__name__).warning(
                "Access denied: user %s lacks required roles %s",
                user.user_id,
                self.roles,
            )
            raise HTTPException(
                status_code=403,
                detail="Forbidden",
            )
        return user


class RequirePermission:
    """Dependency that requires specific permissions.

    Checks both the user's direct permissions (from JWT claims) and
    RBAC-resolved permissions (from RBACMiddleware on request.state).

    Usage:
        @app.post("/articles")
        async def create_article(
            user: AuthenticatedUser = Depends(RequirePermission("write:articles"))
        ):
            return {"created": True}
    """

    def __init__(self, *permissions: str):
        self.permissions = permissions

    def __call__(self, request: Request) -> AuthenticatedUser:
        user = get_current_user(request)

        # Check user's direct permissions (from JWT claims)
        if user.has_any_permission(*self.permissions):
            return user

        # Check RBAC-resolved permissions (from RBACMiddleware)
        rbac_permissions = getattr(request.state, "user_permissions", None)
        if rbac_permissions:
            from nexus.auth.rbac import matches_permission_set

            for perm in self.permissions:
                if matches_permission_set(rbac_permissions, perm):
                    return user

        import logging

        logging.getLogger(__name__).warning(
            "Access denied: user %s lacks required permissions %s",
            user.user_id,
            self.permissions,
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )


def require_role(*roles: str) -> RequireRole:
    """Create a role requirement dependency."""
    return RequireRole(*roles)


def require_permission(*permissions: str) -> RequirePermission:
    """Create a permission requirement dependency."""
    return RequirePermission(*permissions)
