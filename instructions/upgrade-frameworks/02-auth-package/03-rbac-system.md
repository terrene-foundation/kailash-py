# RBAC System Specification

## Overview

This specification defines the Role-Based Access Control (RBAC) system for NexusAuthPlugin. It provides hierarchical roles with permission inheritance, wildcard matching, and FastAPI dependencies for endpoint-level authorization.

**Evidence from Production Projects:**

- **enterprise-app**: `middleware/rbac.py` (425 lines) - RBACService + ABACService, 10 resource types
- **example-project**: `core/rbac.py` (435 lines) - 4 standard roles, `require_role()`, `require_permission()`
- **example-app**: `auth/admin_permissions.py` (177 lines) - AdminScope enum, `has_admin_permission()`

---

## File Location

`/apps/kailash-nexus/src/nexus/auth/rbac.py`

---

## Role Definition Formats

### Simple Format (List of Permissions)

```python
roles = {
    "super_admin": ["*"],
    "admin": ["read:*", "write:*", "delete:users", "manage:roles"],
    "editor": ["read:*", "write:articles", "write:comments"],
    "viewer": ["read:*"],
}
```

### Full Format (With Metadata and Inheritance)

```python
roles = {
    "super_admin": {
        "permissions": ["*"],
        "description": "Full system access",
        "inherits": [],
    },
    "admin": {
        "permissions": ["manage:roles", "delete:users"],
        "description": "Administrative access",
        "inherits": ["editor"],  # Inherits all editor permissions
    },
    "editor": {
        "permissions": ["write:articles", "write:comments"],
        "description": "Content editing access",
        "inherits": ["viewer"],  # Inherits all viewer permissions
    },
    "viewer": {
        "permissions": ["read:*"],
        "description": "Read-only access",
        "inherits": [],
    },
}
```

---

## Permission Format

### Structure

Permissions follow the format: `action:resource`

| Component    | Description                   | Examples                                       |
| ------------ | ----------------------------- | ---------------------------------------------- |
| **action**   | The operation being performed | `read`, `write`, `delete`, `manage`, `execute` |
| **resource** | The target of the operation   | `users`, `articles`, `workflows`, `agents`     |
| **wildcard** | Matches any value             | `*`                                            |

### Examples

| Permission     | Matches                   | Description       |
| -------------- | ------------------------- | ----------------- |
| `read:users`   | Reading user data         | Exact permission  |
| `read:*`       | Reading any resource      | Action wildcard   |
| `*:users`      | Any action on users       | Resource wildcard |
| `*`            | Everything                | Super wildcard    |
| `manage:roles` | Managing role assignments | Exact permission  |

---

## Implementation

```python
"""RBAC (Role-Based Access Control) for Nexus Authentication.

Provides:
    - Hierarchical roles with permission inheritance
    - Wildcard permission matching
    - FastAPI dependencies for authorization

Evidence:
    - enterprise-app: middleware/rbac.py (425 lines) - RBACService + ABAC
    - example-project: core/rbac.py (435 lines) - 4 standard roles
    - example-app: auth/admin_permissions.py (177 lines) - AdminScope
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from nexus.auth.exceptions import (
    AuthorizationError,
    InsufficientPermissionError,
    InsufficientRoleError,
)
from nexus.auth.models import AuthenticatedUser

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
        >>> # Check permission
        >>> rbac.has_permission("editor", "read:users")  # True (read:*)
        >>> rbac.has_permission("editor", "delete:users")  # False
        >>>
        >>> # Get all permissions for a role
        >>> rbac.get_role_permissions("admin")  # ["*"]

    Evidence:
        - enterprise-app: middleware/rbac.py RBACService class (200 lines)
        - example-project: core/rbac.py RBACManager class (250 lines)
    """

    def __init__(
        self,
        roles: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        default_role: Optional[str] = None,
    ):
        """Initialize RBAC manager.

        Args:
            roles: Role definitions (simple or full format)
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
                # Simple format: list of permissions
                self.roles[name] = RoleDefinition(
                    name=name,
                    permissions=definition,
                    description=f"Role: {name}",
                )
            elif isinstance(definition, dict):
                # Full format: dict with permissions, description, inherits
                self.roles[name] = RoleDefinition(
                    name=name,
                    permissions=definition.get("permissions", []),
                    description=definition.get("description", f"Role: {name}"),
                    inherits=definition.get("inherits", []),
                )
            else:
                raise ValueError(f"Invalid role definition for {name}")

        # Validate inheritance (no cycles, all referenced roles exist)
        self._validate_inheritance()

        logger.info(f"Loaded {len(self.roles)} roles: {list(self.roles.keys())}")

    def _validate_inheritance(self) -> None:
        """Validate role inheritance graph.

        Raises:
            ValueError: If inheritance cycle detected or invalid role referenced
        """
        for role_name, role_def in self.roles.items():
            # Check for invalid references
            for inherited in role_def.inherits:
                if inherited not in self.roles:
                    raise ValueError(
                        f"Role '{role_name}' inherits from undefined role '{inherited}'"
                    )

            # Check for cycles using DFS
            visited = set()
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

        Evidence:
            - enterprise-app: middleware/rbac.py get_permissions() method
        """
        # Check cache
        if role_name in self._permission_cache:
            return self._permission_cache[role_name]

        permissions: Set[str] = set()

        role_def = self.roles.get(role_name)
        if not role_def:
            logger.warning(f"Unknown role: {role_name}")
            return permissions

        # Add direct permissions
        permissions.update(role_def.permissions)

        # Add inherited permissions (recursively)
        for inherited in role_def.inherits:
            inherited_perms = self.get_role_permissions(inherited)
            permissions.update(inherited_perms)

        # Cache result
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

        # Add permissions from each role
        for role in user.roles:
            role_perms = self.get_role_permissions(role)
            permissions.update(role_perms)

        # Add default role permissions if user has no roles
        if not user.roles and self.default_role:
            permissions.update(self.get_role_permissions(self.default_role))

        # Add direct permissions from user (from JWT claims)
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
            permission: Permission to check (e.g., "read:users")

        Returns:
            True if permission is granted

        Evidence:
            - enterprise-app: middleware/rbac.py check_permission()
            - example-project: core/rbac.py has_permission()
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

        # Validate inheritance references
        for inherited in inherits:
            if inherited not in self.roles:
                raise ValueError(f"Cannot inherit from undefined role '{inherited}'")

        self.roles[name] = RoleDefinition(
            name=name,
            permissions=permissions,
            description=description,
            inherits=inherits,
        )

        # Invalidate cache
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

        # Check if any role inherits from this one
        for role_name, role_def in self.roles.items():
            if name in role_def.inherits:
                raise ValueError(
                    f"Cannot remove role '{name}': inherited by '{role_name}'"
                )

        del self.roles[name]

        # Invalidate cache
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
    """RBAC middleware for route-level authorization.

    This middleware is primarily for logging and optional route-level
    enforcement. Most authorization should use FastAPI dependencies
    (require_role, require_permission) for fine-grained control.

    Usage:
        >>> from nexus.auth.rbac import RBACMiddleware
        >>>
        >>> app.add_middleware(RBACMiddleware, roles=role_config)

    Note:
        This middleware does NOT block requests - it logs authorization
        events and stores RBAC context. Use dependencies for enforcement.
    """

    def __init__(
        self,
        app: Any,
        roles: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
        default_role: Optional[str] = None,
    ):
        """Initialize RBAC middleware.

        Args:
            app: ASGI application
            roles: Role definitions
            default_role: Default role for users without roles
        """
        super().__init__(app)
        self.rbac_manager = RBACManager(roles=roles, default_role=default_role)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and attach RBAC context.

        Args:
            request: HTTP request
            call_next: Next middleware/handler

        Returns:
            Response from downstream
        """
        # Get user from JWTMiddleware (if authenticated)
        user = getattr(request.state, "user", None)

        if user:
            # Compute and attach user permissions
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

    Evidence:
        - enterprise-app: middleware/rbac.py _match_permission()
        - example-project: core/rbac.py permission_matches()
    """
    # Super wildcard
    if pattern == "*":
        return True

    # Exact match
    if pattern == permission:
        return True

    # Split into action:resource
    pattern_parts = pattern.split(":", 1)
    perm_parts = permission.split(":", 1)

    if len(pattern_parts) != 2 or len(perm_parts) != 2:
        return False

    pattern_action, pattern_resource = pattern_parts
    perm_action, perm_resource = perm_parts

    # Action wildcard
    if pattern_action == "*":
        return pattern_resource == perm_resource or pattern_resource == "*"

    # Resource wildcard
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


# --- FastAPI Dependencies (re-exported from dependencies.py) ---
# These are the primary way to enforce RBAC in endpoints

def require_role_dep(*roles: str):
    """Create dependency that requires user to have one of the specified roles.

    Usage:
        >>> @app.get("/admin")
        >>> async def admin_endpoint(
        ...     user: AuthenticatedUser = Depends(require_role_dep("admin", "super_admin"))
        ... ):
        ...     return {"admin": True}

    Args:
        *roles: Roles that grant access (user needs any one)

    Returns:
        FastAPI dependency function
    """
    from nexus.auth.dependencies import RequireRole
    return RequireRole(*roles)


def require_permission_dep(*permissions: str):
    """Create dependency that requires user to have one of the permissions.

    Usage:
        >>> @app.delete("/users/{id}")
        >>> async def delete_user(
        ...     user: AuthenticatedUser = Depends(require_permission_dep("delete:users"))
        ... ):
        ...     ...

    Args:
        *permissions: Permissions that grant access (user needs any one)

    Returns:
        FastAPI dependency function
    """
    from nexus.auth.dependencies import RequirePermission
    return RequirePermission(*permissions)


# --- Decorators for Class-Based Views ---

def roles_required(*roles: str):
    """Decorator that requires specific roles for a handler.

    Usage:
        >>> @app.get("/admin")
        >>> @roles_required("admin", "super_admin")
        >>> async def admin_endpoint(request: Request):
        ...     ...

    Note: This is less flexible than using Depends(require_role()).
    Prefer dependencies for new code.

    Args:
        *roles: Required roles (user needs any one)

    Returns:
        Decorator function

    Evidence:
        - example-project: core/rbac.py @require_role decorator
    """
    def decorator(func: Callable) -> Callable:
        from functools import wraps

        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = getattr(request.state, "user", None)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )

            if not user.has_any_role(*roles):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Requires one of roles: {', '.join(roles)}"
                    },
                )

            return await func(request, *args, **kwargs)

        return wrapper
    return decorator


def permissions_required(*permissions: str):
    """Decorator that requires specific permissions for a handler.

    Usage:
        >>> @app.post("/articles")
        >>> @permissions_required("write:articles")
        >>> async def create_article(request: Request):
        ...     ...

    Note: This is less flexible than using Depends(require_permission()).
    Prefer dependencies for new code.

    Args:
        *permissions: Required permissions (user needs any one)

    Returns:
        Decorator function

    Evidence:
        - example-app: auth/admin_permissions.py @has_admin_permission
    """
    def decorator(func: Callable) -> Callable:
        from functools import wraps

        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = getattr(request.state, "user", None)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )

            if not user.has_any_permission(*permissions):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Requires one of permissions: {', '.join(permissions)}"
                    },
                )

            return await func(request, *args, **kwargs)

        return wrapper
    return decorator
```

---

## Hierarchical Role Example

### Role Hierarchy Diagram

```
                    super_admin
                         |
                    [inherits]
                         |
                       admin
                      /     \
              [inherits]   [inherits]
                /               \
           editor              moderator
              |                    |
         [inherits]           [inherits]
              |                    |
           viewer              viewer
```

### Configuration

```python
roles = {
    "super_admin": {
        "permissions": ["*"],
        "description": "Full system access",
        "inherits": [],
    },
    "admin": {
        "permissions": [
            "manage:users",
            "manage:roles",
            "delete:*",
            "view:audit",
        ],
        "description": "Administrative access",
        "inherits": ["editor", "moderator"],
    },
    "editor": {
        "permissions": [
            "write:articles",
            "write:comments",
            "publish:articles",
        ],
        "description": "Content creation and editing",
        "inherits": ["viewer"],
    },
    "moderator": {
        "permissions": [
            "moderate:comments",
            "flag:content",
            "ban:users",
        ],
        "description": "Content moderation",
        "inherits": ["viewer"],
    },
    "viewer": {
        "permissions": [
            "read:articles",
            "read:comments",
            "read:profiles",
        ],
        "description": "Read-only access",
        "inherits": [],
    },
}
```

### Resolved Permissions

| Role          | Effective Permissions                                                                                                                                                                                                 |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `super_admin` | `*` (everything)                                                                                                                                                                                                      |
| `admin`       | `manage:users`, `manage:roles`, `delete:*`, `view:audit`, `write:articles`, `write:comments`, `publish:articles`, `moderate:comments`, `flag:content`, `ban:users`, `read:articles`, `read:comments`, `read:profiles` |
| `editor`      | `write:articles`, `write:comments`, `publish:articles`, `read:articles`, `read:comments`, `read:profiles`                                                                                                             |
| `moderator`   | `moderate:comments`, `flag:content`, `ban:users`, `read:articles`, `read:comments`, `read:profiles`                                                                                                                   |
| `viewer`      | `read:articles`, `read:comments`, `read:profiles`                                                                                                                                                                     |

---

## Usage Examples

### Basic Role Check

```python
from nexus.auth import require_role

@app.get("/admin/dashboard")
async def admin_dashboard(user = Depends(require_role("admin", "super_admin"))):
    """Admin-only dashboard."""
    return {"message": f"Welcome, {user.user_id}!"}
```

### Permission Check

```python
from nexus.auth import require_permission

@app.post("/articles")
async def create_article(
    article: ArticleCreate,
    user = Depends(require_permission("write:articles")),
):
    """Create new article (requires write:articles permission)."""
    return {"id": "article-123", "author": user.user_id}


@app.delete("/articles/{article_id}")
async def delete_article(
    article_id: str,
    user = Depends(require_permission("delete:articles")),
):
    """Delete article (requires delete:articles permission)."""
    return {"deleted": article_id}
```

### Combining Role and Permission Checks

```python
from nexus.auth import get_current_user
from nexus.auth.rbac import RBACManager

@app.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    new_role: str,
    request: Request,
    current_user = Depends(require_role("admin", "super_admin")),
):
    """Update user role (admin only, requires manage:roles permission)."""
    rbac: RBACManager = request.state.rbac_manager

    # Additional permission check
    rbac.require_permission(current_user, "manage:roles")

    # Validate new role exists
    if new_role not in rbac.roles:
        raise HTTPException(status_code=400, detail=f"Invalid role: {new_role}")

    # Update user role (implementation depends on your user store)
    return {"user_id": user_id, "role": new_role}
```

### Dynamic Role Creation

```python
@app.post("/admin/roles")
async def create_role(
    role: RoleCreate,
    current_user = Depends(require_role("super_admin")),
    request: Request,
):
    """Create new role (super_admin only)."""
    rbac: RBACManager = request.state.rbac_manager

    rbac.add_role(
        name=role.name,
        permissions=role.permissions,
        description=role.description,
        inherits=role.inherits,
    )

    return {"created": role.name}
```

---

## Testing

### Unit Tests

```python
# tests/unit/auth/test_rbac.py
"""Unit tests for RBAC system."""

import pytest
from nexus.auth.rbac import RBACManager, matches_permission


class TestPermissionMatching:
    """Test permission pattern matching."""

    def test_exact_match(self):
        """Test exact permission matching."""
        assert matches_permission("read:users", "read:users") is True
        assert matches_permission("read:users", "read:articles") is False

    def test_action_wildcard(self):
        """Test action wildcard matching."""
        assert matches_permission("read:*", "read:users") is True
        assert matches_permission("read:*", "read:articles") is True
        assert matches_permission("read:*", "write:users") is False

    def test_resource_wildcard(self):
        """Test resource wildcard matching."""
        assert matches_permission("*:users", "read:users") is True
        assert matches_permission("*:users", "write:users") is True
        assert matches_permission("*:users", "read:articles") is False

    def test_super_wildcard(self):
        """Test super wildcard matches everything."""
        assert matches_permission("*", "read:users") is True
        assert matches_permission("*", "write:articles") is True
        assert matches_permission("*", "anything:whatever") is True


class TestRBACManager:
    """Test RBACManager functionality."""

    @pytest.fixture
    def rbac(self):
        """Create RBAC manager with test roles."""
        return RBACManager(roles={
            "admin": ["*"],
            "editor": {
                "permissions": ["write:articles"],
                "inherits": ["viewer"],
            },
            "viewer": ["read:*"],
        })

    def test_simple_role_permissions(self, rbac):
        """Test simple role permission lookup."""
        perms = rbac.get_role_permissions("admin")
        assert "*" in perms

    def test_inherited_permissions(self, rbac):
        """Test permission inheritance."""
        perms = rbac.get_role_permissions("editor")
        assert "write:articles" in perms
        assert "read:*" in perms  # Inherited from viewer

    def test_has_permission_exact(self, rbac):
        """Test exact permission check."""
        assert rbac.has_permission("editor", "write:articles") is True
        assert rbac.has_permission("editor", "delete:articles") is False

    def test_has_permission_wildcard(self, rbac):
        """Test wildcard permission check."""
        assert rbac.has_permission("editor", "read:anything") is True  # read:*
        assert rbac.has_permission("admin", "anything:everything") is True  # *

    def test_inheritance_cycle_detection(self):
        """Test that inheritance cycles are detected."""
        with pytest.raises(ValueError, match="cycle"):
            RBACManager(roles={
                "a": {"permissions": [], "inherits": ["b"]},
                "b": {"permissions": [], "inherits": ["c"]},
                "c": {"permissions": [], "inherits": ["a"]},  # Cycle!
            })

    def test_invalid_inheritance_reference(self):
        """Test that invalid inheritance references are detected."""
        with pytest.raises(ValueError, match="undefined role"):
            RBACManager(roles={
                "a": {"permissions": [], "inherits": ["nonexistent"]},
            })


class TestRBACWithUser:
    """Test RBAC with AuthenticatedUser."""

    @pytest.fixture
    def rbac(self):
        return RBACManager(roles={
            "admin": ["manage:*", "delete:*"],
            "editor": ["read:*", "write:articles"],
        })

    @pytest.fixture
    def admin_user(self):
        from nexus.auth.models import AuthenticatedUser
        return AuthenticatedUser(
            user_id="admin-1",
            roles=["admin"],
            permissions=[],
        )

    @pytest.fixture
    def editor_user(self):
        from nexus.auth.models import AuthenticatedUser
        return AuthenticatedUser(
            user_id="editor-1",
            roles=["editor"],
            permissions=["special:permission"],  # Direct permission
        )

    def test_user_role_permissions(self, rbac, admin_user):
        """Test getting user permissions from roles."""
        perms = rbac.get_user_permissions(admin_user)
        assert "manage:*" in perms
        assert "delete:*" in perms

    def test_user_direct_permissions(self, rbac, editor_user):
        """Test user direct permissions are included."""
        perms = rbac.get_user_permissions(editor_user)
        assert "special:permission" in perms  # Direct
        assert "read:*" in perms  # From role
```

### Integration Tests

```python
# tests/integration/auth/test_rbac_integration.py
"""Integration tests for RBAC with Nexus."""

import pytest
from httpx import AsyncClient
from nexus import Nexus
from nexus.auth import NexusAuthPlugin


@pytest.fixture
def auth_app():
    """Create app with RBAC configuration."""
    app = Nexus(api_port=8002)
    auth = NexusAuthPlugin(
        jwt_secret="test-secret-key-32-characters-min",
        roles={
            "admin": ["*"],
            "editor": ["read:*", "write:articles"],
            "viewer": ["read:*"],
        },
    )
    app.add_plugin(auth)
    return app, auth


@pytest.mark.asyncio
async def test_role_authorization(auth_app):
    """Test role-based authorization."""
    app, auth = auth_app

    # Register endpoint that requires admin role
    @app.endpoint("/admin-only", methods=["GET"])
    async def admin_only(request):
        from nexus.auth import require_role
        user = require_role("admin")(request)
        return {"message": "admin access"}

    async with AsyncClient(
        app=app._gateway.app,
        base_url="http://test"
    ) as client:
        # Viewer cannot access admin endpoint
        viewer_token = auth._jwt_middleware.create_access_token(
            user_id="viewer-1",
            roles=["viewer"],
        )
        response = await client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

        # Admin can access
        admin_token = auth._jwt_middleware.create_access_token(
            user_id="admin-1",
            roles=["admin"],
        )
        response = await client.get(
            "/admin-only",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
```

---

## Common Role Configurations

### Basic SaaS Application

```python
roles = {
    "owner": ["*"],
    "admin": ["manage:users", "manage:billing", "read:*", "write:*"],
    "member": ["read:*", "write:own"],
    "guest": ["read:public"],
}
```

### Content Management System

```python
roles = {
    "super_admin": ["*"],
    "admin": {
        "permissions": ["manage:*"],
        "inherits": ["editor"],
    },
    "editor": {
        "permissions": ["write:*", "publish:*"],
        "inherits": ["author"],
    },
    "author": {
        "permissions": ["write:own", "submit:review"],
        "inherits": ["viewer"],
    },
    "viewer": ["read:published"],
}
```

### API Access Tiers

```python
roles = {
    "enterprise": {
        "permissions": ["api:*", "rate:unlimited"],
        "description": "Enterprise API access",
    },
    "professional": {
        "permissions": ["api:*", "rate:1000"],
        "description": "Professional tier",
    },
    "starter": {
        "permissions": ["api:basic", "rate:100"],
        "description": "Starter tier",
    },
    "free": {
        "permissions": ["api:basic", "rate:10"],
        "description": "Free tier",
    },
}
```

---

## Error Messages

### 403 Forbidden - Insufficient Role

```json
{
  "detail": "Requires one of roles: admin, super_admin",
  "error": "insufficient_role",
  "required_roles": ["admin", "super_admin"],
  "user_roles": ["viewer"]
}
```

### 403 Forbidden - Insufficient Permission

```json
{
  "detail": "Missing required permission: delete:users",
  "error": "insufficient_permission",
  "required_permission": "delete:users"
}
```
