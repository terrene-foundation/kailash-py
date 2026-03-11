"""
RBAC (Role-Based Access Control) middleware for API Gateway.

Provides role hierarchy enforcement, permission checks, and organization access control.
"""

from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request

# Role hierarchy: owner > admin > member
ROLE_HIERARCHY = {"owner": 3, "admin": 2, "member": 1}


def require_role(min_role: str) -> Callable:
    """
    Decorator to enforce minimum role requirement for endpoint access.

    Args:
        min_role: Minimum role required ("owner", "admin", or "member")

    Returns:
        Decorator function that checks role permissions

    Raises:
        HTTPException: 401 if user not authenticated, 403 if insufficient permissions

    Example:
        ```python
        @app.post("/admin/settings")
        @require_role("admin")
        async def update_settings(request: Request):
            # Only admin and owner can access
            return {"status": "updated"}
        ```
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(request: Request, *args, **kwargs):
            # Check if user is authenticated (request.state.role should be set by auth middleware)
            if not hasattr(request.state, "role"):
                raise HTTPException(status_code=401, detail="Authentication required")

            user_role = request.state.role

            # Validate role exists in hierarchy
            if user_role not in ROLE_HIERARCHY:
                raise HTTPException(
                    status_code=400, detail=f"Invalid role: {user_role}"
                )

            if min_role not in ROLE_HIERARCHY:
                raise HTTPException(status_code=400, detail=f"Invalid role: {min_role}")

            # Check permission
            if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY[min_role]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required role: {min_role}, current role: {user_role}",
                )

            # Call the original function (handle both async and sync)
            import asyncio

            if asyncio.iscoroutinefunction(func):
                return await func(request, *args, **kwargs)
            else:
                return func(request, *args, **kwargs)

        @wraps(func)
        def sync_wrapper(request: Request, *args, **kwargs):
            # Check if user is authenticated (request.state.role should be set by auth middleware)
            if not hasattr(request.state, "role"):
                raise HTTPException(status_code=401, detail="Authentication required")

            user_role = request.state.role

            # Validate role exists in hierarchy
            if user_role not in ROLE_HIERARCHY:
                raise HTTPException(
                    status_code=400, detail=f"Invalid role: {user_role}"
                )

            if min_role not in ROLE_HIERARCHY:
                raise HTTPException(status_code=400, detail=f"Invalid role: {min_role}")

            # Check permission
            if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY[min_role]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required role: {min_role}, current role: {user_role}",
                )

            return func(request, *args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def check_role_permission(user_role: str, required_role: str) -> bool:
    """
    Check if user role meets minimum requirement.

    Args:
        user_role: User's current role
        required_role: Required minimum role

    Returns:
        True if user has sufficient permissions, False otherwise

    Example:
        ```python
        # Check if admin can access member-level resource
        has_permission = await check_role_permission("admin", "member")
        assert has_permission is True

        # Check if member can access admin-level resource
        has_permission = await check_role_permission("member", "admin")
        assert has_permission is False
        ```
    """
    if user_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False

    return ROLE_HIERARCHY[user_role] >= ROLE_HIERARCHY[required_role]


async def check_organization_access(user_org_id: str, resource_org_id: str) -> bool:
    """
    Verify user belongs to resource organization.

    Args:
        user_org_id: User's organization ID
        resource_org_id: Resource's organization ID

    Returns:
        True if user belongs to same organization, False otherwise

    Example:
        ```python
        # User can access resources in their own organization
        can_access = await check_organization_access("org-123", "org-123")
        assert can_access is True

        # User cannot access resources in different organization
        can_access = await check_organization_access("org-123", "org-456")
        assert can_access is False
        ```
    """
    return user_org_id == resource_org_id
