"""RBAC (Role-Based Access Control) for Nexus Authentication.

Provides:
    - Hierarchical roles with permission inheritance
    - Wildcard permission matching
    - FastAPI dependencies for authorization
    - Dynamic role management
    - Permission caching for performance

Note: Do NOT use ``from __future__ import annotations`` in this module.
FastAPI inspects parameter annotations at runtime to recognize special types
like Request. PEP 563 deferred annotations turn them into strings, which
prevents FastAPI from injecting the Request object into callable dependencies.
"""

import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Union

from nexus.auth.exceptions import InsufficientPermissionError, InsufficientRoleError
from nexus.auth.models import AuthenticatedUser
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


@dataclass
class RoleDefinition:
    """Role definition with permissions and inheritance.

    Attributes:
        name: Role name
        permissions: List of permissions granted to this role
        description: Human-readable description
        inherits: List of roles this role inherits from
    """

    name: str
    permissions: List[str] = field(default_factory=list)
    description: str = ""
    inherits: List[str] = field(default_factory=list)


class RBACManager:
    """Role-Based Access Control manager.

    Manages role definitions and provides permission checking with:
    - Permission inheritance through role hierarchy
    - Wildcard matching for flexible permissions
    - Caching of resolved permissions for performance

    Usage:
        >>> rbac = RBACManager(roles={
        ...     "admin": ["*"],
        ...     "editor": ["read:*", "write:articles"],
        ...     "viewer": ["read:*"],
        ... })
        >>>
        >>> rbac.has_permission("editor", "read:users")  # True (read:*)
        >>> rbac.has_permission("editor", "delete:users")  # False
    """

    def __init__(
        self,
        roles: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        default_role: Optional[str] = None,
    ):
        """Initialize RBAC manager.

        Args:
            roles: Role definitions (simple list or full dict format)
            default_role: Role assigned to users without explicit roles
        """
        self.roles: Dict[str, RoleDefinition] = {}
        self.default_role = default_role
        self._permission_cache: Dict[str, Set[str]] = {}

        if roles:
            self._load_roles(roles)

    def _load_roles(
        self,
        roles: Dict[str, Union[List[str], Dict[str, Any]]],
    ) -> None:
        """Load role definitions from config.

        Args:
            roles: Role definitions in simple or full format
        """
        for name, definition in roles.items():
            if isinstance(definition, list):
                self.roles[name] = RoleDefinition(
                    name=name,
                    permissions=definition,
                    description=f"Role: {name}",
                )
            elif isinstance(definition, dict):
                self.roles[name] = RoleDefinition(
                    name=name,
                    permissions=definition.get("permissions", []),
                    description=definition.get("description", f"Role: {name}"),
                    inherits=definition.get("inherits", []),
                )
            else:
                raise ValueError(f"Invalid role definition for {name}")

        self._validate_inheritance()

        logger.info(f"Loaded {len(self.roles)} roles: {list(self.roles.keys())}")

    def _validate_inheritance(self) -> None:
        """Validate role inheritance graph.

        Raises:
            ValueError: If inheritance cycle detected or invalid role referenced
        """
        for role_name, role_def in self.roles.items():
            for inherited in role_def.inherits:
                if inherited not in self.roles:
                    raise ValueError(
                        f"Role '{role_name}' inherits from undefined role '{inherited}'"
                    )

            visited: Set[str] = set()
            self._check_cycle(role_name, visited, set())

    def _check_cycle(
        self,
        role_name: str,
        visited: Set[str],
        path: Set[str],
    ) -> None:
        """Check for inheritance cycles using DFS.

        Args:
            role_name: Current role being checked
            visited: All visited roles
            path: Current path in DFS

        Raises:
            ValueError: If cycle detected
        """
        if role_name in path:
            raise ValueError(f"Inheritance cycle detected involving role '{role_name}'")

        if role_name in visited:
            return

        visited.add(role_name)
        path.add(role_name)

        role_def = self.roles.get(role_name)
        if role_def:
            for inherited in role_def.inherits:
                self._check_cycle(inherited, visited, path)

        path.remove(role_name)

    def get_role_permissions(self, role_name: str) -> Set[str]:
        """Get all permissions for a role (including inherited).

        Args:
            role_name: Role name

        Returns:
            Set of all permissions for the role
        """
        if role_name in self._permission_cache:
            return self._permission_cache[role_name]

        permissions: Set[str] = set()

        role_def = self.roles.get(role_name)
        if not role_def:
            logger.warning(f"Unknown role: {role_name}")
            return permissions

        permissions.update(role_def.permissions)

        for inherited in role_def.inherits:
            inherited_perms = self.get_role_permissions(inherited)
            permissions.update(inherited_perms)

        self._permission_cache[role_name] = permissions

        return permissions

    def get_user_permissions(self, user: AuthenticatedUser) -> Set[str]:
        """Get all permissions for a user (from all their roles).

        Args:
            user: Authenticated user

        Returns:
            Set of all permissions for the user
        """
        permissions: Set[str] = set()

        for role in user.roles:
            role_perms = self.get_role_permissions(role)
            permissions.update(role_perms)

        if not user.roles and self.default_role:
            permissions.update(self.get_role_permissions(self.default_role))

        permissions.update(user.permissions)

        return permissions

    def has_permission(
        self,
        role_or_user: Union[str, AuthenticatedUser],
        permission: str,
    ) -> bool:
        """Check if role/user has a specific permission.

        Supports wildcard matching:
        - "read:*" matches "read:users", "read:articles", etc.
        - "*" matches everything

        Args:
            role_or_user: Role name or AuthenticatedUser
            permission: Permission to check

        Returns:
            True if permission is granted
        """
        if isinstance(role_or_user, str):
            permissions = self.get_role_permissions(role_or_user)
        else:
            permissions = self.get_user_permissions(role_or_user)

        return matches_permission_set(permissions, permission)

    def has_role(
        self,
        user: AuthenticatedUser,
        *roles: str,
    ) -> bool:
        """Check if user has any of the specified roles.

        Args:
            user: Authenticated user
            *roles: Roles to check

        Returns:
            True if user has at least one of the roles
        """
        return bool(set(roles) & set(user.roles))

    def require_permission(
        self,
        user: AuthenticatedUser,
        permission: str,
    ) -> None:
        """Require user to have a permission.

        Args:
            user: Authenticated user
            permission: Required permission

        Raises:
            InsufficientPermissionError: If user lacks permission
        """
        if not self.has_permission(user, permission):
            raise InsufficientPermissionError(permission)

    def require_role(
        self,
        user: AuthenticatedUser,
        *roles: str,
    ) -> None:
        """Require user to have one of the specified roles.

        Args:
            user: Authenticated user
            *roles: Required roles (any one is sufficient)

        Raises:
            InsufficientRoleError: If user lacks all roles
        """
        if not self.has_role(user, *roles):
            raise InsufficientRoleError(list(roles))

    def add_role(
        self,
        name: str,
        permissions: List[str],
        description: str = "",
        inherits: Optional[List[str]] = None,
    ) -> None:
        """Add a new role dynamically.

        Args:
            name: Role name
            permissions: Permissions for the role
            description: Role description
            inherits: Roles to inherit from

        Raises:
            ValueError: If role already exists or inheritance is invalid
        """
        if name in self.roles:
            raise ValueError(f"Role '{name}' already exists")

        inherits = inherits or []

        for inherited in inherits:
            if inherited not in self.roles:
                raise ValueError(f"Cannot inherit from undefined role '{inherited}'")

        self.roles[name] = RoleDefinition(
            name=name,
            permissions=permissions,
            description=description,
            inherits=inherits,
        )

        self._permission_cache.clear()

        logger.info(f"Added role: {name} with {len(permissions)} permissions")

    def remove_role(self, name: str) -> None:
        """Remove a role.

        Args:
            name: Role name

        Raises:
            ValueError: If role doesn't exist or is inherited by other roles
        """
        if name not in self.roles:
            raise ValueError(f"Role '{name}' doesn't exist")

        for role_name, role_def in self.roles.items():
            if name in role_def.inherits:
                raise ValueError(
                    f"Cannot remove role '{name}': inherited by '{role_name}'"
                )

        del self.roles[name]

        self._permission_cache.clear()

        logger.info(f"Removed role: {name}")

    def get_stats(self) -> Dict[str, Any]:
        """Get RBAC statistics.

        Returns:
            Dict with role count, permission stats, etc.
        """
        all_permissions: Set[str] = set()
        for role_def in self.roles.values():
            all_permissions.update(role_def.permissions)

        return {
            "total_roles": len(self.roles),
            "total_unique_permissions": len(all_permissions),
            "roles": {
                name: {
                    "direct_permissions": len(role_def.permissions),
                    "inherited_from": role_def.inherits,
                    "total_permissions": len(self.get_role_permissions(name)),
                }
                for name, role_def in self.roles.items()
            },
            "default_role": self.default_role,
        }


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
                f"RBAC: User {user.user_id} has roles {user.roles}, "
                f"{len(permissions)} permissions"
            )

        return await call_next(request)


# --- Permission Matching Functions ---


def matches_permission(pattern: str, permission: str) -> bool:
    """Check if a permission pattern matches a specific permission.

    Pattern syntax:
    - Exact match: "read:users" matches "read:users"
    - Action wildcard: "read:*" matches "read:users", "read:articles"
    - Resource wildcard: "*:users" matches "read:users", "write:users"
    - Super wildcard: "*" matches everything

    Args:
        pattern: Permission pattern (may include wildcards)
        permission: Specific permission to check

    Returns:
        True if pattern matches permission
    """
    if pattern == "*":
        return True

    if pattern == permission:
        return True

    pattern_parts = pattern.split(":", 1)
    perm_parts = permission.split(":", 1)

    if len(pattern_parts) != 2 or len(perm_parts) != 2:
        return False

    pattern_action, pattern_resource = pattern_parts
    perm_action, perm_resource = perm_parts

    if pattern_action == "*":
        return pattern_resource == perm_resource or pattern_resource == "*"

    if pattern_resource == "*":
        return pattern_action == perm_action

    return False


def matches_permission_set(permissions: Set[str], required: str) -> bool:
    """Check if any permission in set matches required permission.

    Args:
        permissions: Set of permission patterns
        required: Required permission

    Returns:
        True if any permission matches
    """
    for pattern in permissions:
        if matches_permission(pattern, required):
            return True
    return False


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
