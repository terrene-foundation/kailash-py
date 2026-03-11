# RBAC Authorization

Role-Based Access Control (RBAC) provides hierarchical roles with permission inheritance, wildcard matching, and FastAPI dependencies for endpoint-level authorization.

## Quick Start

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig

app = Nexus()

# Define roles and their permissions
roles = {
    "admin": ["*"],                                    # Super user
    "editor": ["read:*", "write:articles", "write:comments"],
    "viewer": ["read:*"],
}

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    rbac=roles,
    rbac_default_role="viewer",  # Assigned to users without explicit roles
)

app.add_plugin(auth)
```

## Role Definition Formats

### Simple Format (List of Permissions)

```python
roles = {
    "admin": ["*"],
    "editor": ["read:*", "write:*"],
    "viewer": ["read:*"],
}
```

### Full Format (With Inheritance and Description)

```python
roles = {
    "super_admin": {
        "permissions": ["*"],
        "description": "Full system access",
    },
    "admin": {
        "permissions": ["manage:users", "manage:settings"],
        "inherits": ["editor"],  # Gets all editor permissions too
        "description": "Administrative access",
    },
    "editor": {
        "permissions": ["write:articles", "write:comments"],
        "inherits": ["viewer"],
        "description": "Content editor",
    },
    "viewer": {
        "permissions": ["read:*"],
        "description": "Read-only access",
    },
}
```

## Permission Wildcards

The RBAC system supports flexible wildcard patterns:

| Pattern          | Matches                                        | Does Not Match                    |
| ---------------- | ---------------------------------------------- | --------------------------------- |
| `*`              | Everything                                     | -                                 |
| `read:*`         | `read:users`, `read:articles`, `read:settings` | `write:users`, `delete:articles`  |
| `*:users`        | `read:users`, `write:users`, `delete:users`    | `read:articles`, `write:settings` |
| `write:articles` | `write:articles` only                          | `write:users`, `read:articles`    |

### Permission Matching Logic

```python
from nexus.auth.rbac import matches_permission

# Exact match
matches_permission("read:users", "read:users")      # True

# Action wildcard
matches_permission("read:*", "read:users")          # True
matches_permission("read:*", "read:articles")       # True
matches_permission("read:*", "write:users")         # False

# Resource wildcard
matches_permission("*:users", "read:users")         # True
matches_permission("*:users", "write:users")        # True
matches_permission("*:users", "read:articles")      # False

# Super wildcard
matches_permission("*", "anything:at:all")          # True
```

## Role Inheritance

Roles can inherit permissions from other roles, creating a hierarchy:

```python
roles = {
    "super_admin": {
        "permissions": ["manage:system"],
        "inherits": ["admin"],
    },
    "admin": {
        "permissions": ["manage:users"],
        "inherits": ["editor"],
    },
    "editor": {
        "permissions": ["write:*"],
        "inherits": ["viewer"],
    },
    "viewer": {
        "permissions": ["read:*"],
    },
}

# Result:
# - viewer: read:*
# - editor: read:*, write:*
# - admin: read:*, write:*, manage:users
# - super_admin: read:*, write:*, manage:users, manage:system
```

### Cycle Detection

The RBAC manager automatically detects and prevents inheritance cycles:

```python
# This will raise ValueError
roles = {
    "a": {"permissions": [], "inherits": ["b"]},
    "b": {"permissions": [], "inherits": ["c"]},
    "c": {"permissions": [], "inherits": ["a"]},  # Cycle!
}
# ValueError: Inheritance cycle detected involving role 'a'
```

## FastAPI Dependencies

### RequireRole

Require users to have specific roles:

```python
from fastapi import Depends
from nexus.auth.dependencies import RequireRole
from nexus.auth import AuthenticatedUser

@app.get("/admin/dashboard")
async def admin_dashboard(
    user: AuthenticatedUser = Depends(RequireRole("admin", "super_admin"))
):
    """Only accessible by admin or super_admin roles."""
    return {"message": f"Welcome, {user.display_name}"}
```

### RequirePermission

Require users to have specific permissions:

```python
from fastapi import Depends
from nexus.auth.dependencies import RequirePermission
from nexus.auth import AuthenticatedUser

@app.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: AuthenticatedUser = Depends(RequirePermission("delete:users"))
):
    """Requires delete:users permission."""
    return {"deleted": user_id}

@app.post("/articles")
async def create_article(
    user: AuthenticatedUser = Depends(RequirePermission("write:articles"))
):
    """Requires write:articles permission (also granted by write:* or *)."""
    return {"created": True}
```

### Permission Resolution

`RequirePermission` checks both sources:

1. **JWT direct permissions**: Permissions in the token's `permissions` claim
2. **RBAC-resolved permissions**: Permissions resolved from roles via RBACMiddleware

```python
# User has role "editor" with permissions ["read:*", "write:articles"]
# User's JWT also has permissions: ["admin:reports"]

# RequirePermission("write:articles") -> PASS (from role)
# RequirePermission("read:users") -> PASS (from role wildcard read:*)
# RequirePermission("admin:reports") -> PASS (from JWT direct)
# RequirePermission("delete:users") -> FAIL (neither source)
```

### Factory Functions

For cleaner syntax:

```python
from nexus.auth.rbac import require_role_dep, require_permission_dep

@app.get("/admin")
async def admin(user = Depends(require_role_dep("admin"))):
    ...

@app.delete("/articles/{id}")
async def delete_article(user = Depends(require_permission_dep("delete:articles"))):
    ...
```

## Decorators (Legacy)

For class-based views or when dependencies aren't suitable:

```python
from nexus.auth.rbac import roles_required, permissions_required
from fastapi import Request

@app.get("/admin")
@roles_required("admin", "super_admin")
async def admin_endpoint(request: Request):
    return {"admin": True}

@app.post("/articles")
@permissions_required("write:articles")
async def create_article(request: Request):
    return {"created": True}
```

Note: Prefer `Depends()` for new code as it integrates better with FastAPI's dependency injection.

## RBACManager Direct Usage

For programmatic access control:

```python
from nexus.auth.rbac import RBACManager
from nexus.auth import AuthenticatedUser

rbac = RBACManager(
    roles={
        "admin": ["*"],
        "editor": ["read:*", "write:articles"],
        "viewer": ["read:*"],
    },
    default_role="viewer",
)

# Check role permissions
rbac.has_permission("editor", "read:users")     # True (read:*)
rbac.has_permission("editor", "delete:users")   # False

# Check user permissions
user = AuthenticatedUser(
    user_id="123",
    roles=["editor"],
    permissions=["delete:own"],  # Direct permissions
)
rbac.has_permission(user, "read:users")         # True (from role)
rbac.has_permission(user, "delete:own")         # True (direct)
rbac.has_permission(user, "delete:users")       # False

# Get all permissions for a user
all_perms = rbac.get_user_permissions(user)
# {"read:*", "write:articles", "delete:own"}

# Require permission (raises exception)
try:
    rbac.require_permission(user, "admin:*")
except InsufficientPermissionError:
    print("Access denied")

# Role checks
rbac.has_role(user, "admin")                    # False
rbac.has_role(user, "editor", "viewer")         # True (has editor)
```

## Dynamic Role Management

Add or remove roles at runtime:

```python
rbac = RBACManager(roles={
    "viewer": ["read:*"],
})

# Add new role
rbac.add_role(
    name="moderator",
    permissions=["moderate:comments", "ban:users"],
    inherits=["viewer"],
    description="Community moderator",
)

# Remove role (fails if inherited by other roles)
rbac.remove_role("moderator")

# Get statistics
stats = rbac.get_stats()
# {
#     "total_roles": 2,
#     "total_unique_permissions": 5,
#     "roles": {
#         "viewer": {"direct_permissions": 1, "inherited_from": [], "total_permissions": 1},
#         "moderator": {"direct_permissions": 2, "inherited_from": ["viewer"], "total_permissions": 3},
#     },
#     "default_role": None,
# }
```

## Request State

After RBACMiddleware processes a request, these are available:

```python
from fastapi import Request

@app.get("/debug")
async def debug(request: Request):
    return {
        "user_permissions": list(request.state.user_permissions),  # Set of resolved permissions
        "rbac_manager": request.state.rbac_manager,  # RBACManager instance
    }
```

## Error Responses

### 403 Forbidden (Role)

```json
{
  "detail": "Requires one of roles: admin, super_admin"
}
```

### 403 Forbidden (Permission)

```json
{
  "detail": "Requires one of permissions: delete:users"
}
```

## Complete Example

```python
from fastapi import FastAPI, Depends
from nexus.auth import NexusAuthPlugin, JWTConfig, AuthenticatedUser
from nexus.auth.dependencies import RequireRole, RequirePermission

app = FastAPI()

# Configure auth with RBAC
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    rbac={
        "super_admin": {
            "permissions": ["*"],
            "description": "Full access",
        },
        "admin": {
            "permissions": ["manage:users", "manage:settings"],
            "inherits": ["editor"],
        },
        "editor": {
            "permissions": ["write:*"],
            "inherits": ["viewer"],
        },
        "viewer": {
            "permissions": ["read:*"],
        },
    },
    rbac_default_role="viewer",
)
auth.install(app)

# Public endpoint (exempt from JWT via config)
@app.get("/health")
async def health():
    return {"status": "ok"}

# Authenticated endpoint (any valid JWT)
@app.get("/profile")
async def get_profile(user: AuthenticatedUser = Depends(RequireRole())):
    return {"user_id": user.user_id}

# Role-protected endpoint
@app.get("/admin/users")
async def list_users(
    user: AuthenticatedUser = Depends(RequireRole("admin", "super_admin"))
):
    return {"users": []}

# Permission-protected endpoint
@app.post("/articles")
async def create_article(
    user: AuthenticatedUser = Depends(RequirePermission("write:articles"))
):
    return {"created": True}

@app.delete("/articles/{id}")
async def delete_article(
    id: str,
    user: AuthenticatedUser = Depends(RequirePermission("delete:articles"))
):
    return {"deleted": id}
```

## Best Practices

1. **Use permission-based checks**: More flexible than role-based for endpoint protection
2. **Keep roles coarse-grained**: Roles represent job functions, not individual permissions
3. **Use wildcards wisely**: `read:*` is useful, but `*` should be reserved for super admins
4. **Document role permissions**: Keep a reference of what each role can do
5. **Use inheritance**: Reduces duplication and makes hierarchies clear
6. **Set a default role**: Ensures users always have some baseline permissions
7. **Prefer Depends over decorators**: Better integration with FastAPI's dependency system
