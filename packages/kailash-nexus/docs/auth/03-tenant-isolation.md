# Tenant Isolation

Multi-tenancy support with JWT claim resolution, admin override capability, and thread-safe context management via Python's contextvars.

## Quick Start

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig, TenantConfig

app = Nexus()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",        # Claim containing tenant ID
        admin_role="super_admin",     # Role that can access any tenant
        allow_admin_override=True,    # Allow X-Tenant-ID header override
    ),
)

app.add_plugin(auth)
```

## TenantConfig Reference

```python
from dataclasses import dataclass, field
from typing import Callable, List, Optional

@dataclass
class TenantConfig:
    # Whether tenant isolation is enabled (default: True)
    enabled: bool = True

    # Header name for explicit tenant ID (default: "X-Tenant-ID")
    tenant_id_header: str = "X-Tenant-ID"

    # JWT claim containing tenant ID (default: "tenant_id")
    jwt_claim: str = "tenant_id"

    # Look up org from user record if not in JWT (default: True)
    fallback_to_user_org: bool = True

    # Field name for organization in user record (default: "organization_id")
    org_field_name: str = "organization_id"

    # Validate tenant exists in database (default: True)
    validate_tenant_exists: bool = True

    # Validate tenant is active (default: True)
    validate_tenant_active: bool = True

    # Allow super admins to access any tenant (default: True)
    allow_admin_override: bool = True

    # Role name for super admins (default: "super_admin")
    admin_role: str = "super_admin"

    # Paths to exclude from tenant isolation
    exclude_paths: List[str] = field(default_factory=lambda: [
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
    ])

    # Custom tenant resolver function (optional)
    custom_resolver: Optional[Callable] = None
```

## Tenant Resolution Order

The middleware resolves tenants in this priority order:

1. **X-Tenant-ID Header** (admin override)
   - Only allowed for users with `admin_role`
   - Fail-closed security: non-admins are rejected

2. **JWT Claim**
   - Checks `token_payload.{jwt_claim}` (e.g., `tenant_id`)
   - Also checks `token_claims` for compatibility

3. **User Organization Lookup**
   - Falls back to user record's organization field
   - Only if `fallback_to_user_org=True`

```python
# Resolution example:
# 1. Header: X-Tenant-ID: tenant-admin-override (admin only)
# 2. JWT: {"sub": "user-123", "tenant_id": "tenant-from-jwt"}
# 3. User org: user.organization_id = "tenant-from-user"
```

## Admin Override

Super admins can access any tenant via the `X-Tenant-ID` header:

```python
config = TenantConfig(
    allow_admin_override=True,
    admin_role="super_admin",  # Singular string, not a list
)
```

### Security: Fail-Closed

If a non-admin user sends `X-Tenant-ID`:

```json
{
  "detail": "Tenant override header requires 'super_admin' role",
  "error_code": "TENANT_ACCESS_DENIED"
}
```

### Disable Admin Override

```python
config = TenantConfig(
    allow_admin_override=False,  # All users bound to their JWT tenant
)
```

## Accessing Tenant Context

### In Request Handlers

```python
from fastapi import Request

@app.get("/data")
async def get_data(request: Request):
    tenant_id = request.state.tenant_id      # Just the ID
    tenant = request.state.tenant            # Full TenantInfo object

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "tenant_active": tenant.active,
    }
```

### Via Module Functions

```python
from nexus.auth.tenant.context import (
    get_current_tenant,
    get_current_tenant_id,
    require_tenant,
)

@app.get("/data")
async def get_data():
    # Get current tenant (None if not set)
    tenant = get_current_tenant()

    # Get just the ID (None if not set)
    tenant_id = get_current_tenant_id()

    # Require tenant (raises TenantContextError if not set)
    tenant = require_tenant()

    return {"tenant_id": tenant.tenant_id}
```

### In Background Tasks

The context is thread/async-safe via contextvars:

```python
from nexus.auth.tenant.context import get_current_tenant_id

async def background_task():
    tenant_id = get_current_tenant_id()  # Works in async context
    # Process data for this tenant
```

## TenantContext for Manual Control

For advanced use cases where you need to manually switch contexts:

```python
from nexus.auth.tenant.context import TenantContext, TenantInfo

# Create context manager
ctx = TenantContext(validate_registered=True)

# Register tenants
ctx.register("tenant-a", name="Tenant A", metadata={"plan": "pro"})
ctx.register("tenant-b", name="Tenant B", active=False)

# Synchronous context switching
with ctx.switch("tenant-a"):
    tenant = ctx.current()
    print(f"Operating as: {tenant.tenant_id}")  # tenant-a

# Asynchronous context switching
async with ctx.aswitch("tenant-a"):
    tenant = ctx.current()
    print(f"Operating as: {tenant.tenant_id}")

# Tenant management
ctx.deactivate("tenant-b")  # Prevents switching to this tenant
ctx.activate("tenant-b")    # Re-enables the tenant
ctx.unregister("tenant-a")  # Removes tenant (fails if currently active)

# Statistics
stats = ctx.get_stats()
# {
#     "total_tenants": 2,
#     "active_tenants": 1,
#     "total_switches": 5,
#     "active_switches": 0,
#     "current_tenant": None,
# }
```

### Validation Modes

```python
# Strict mode (default): Only registered tenants allowed
ctx = TenantContext(validate_registered=True)
ctx.switch("unknown-tenant")  # Raises TenantNotFoundError

# Permissive mode: Any tenant ID allowed
ctx = TenantContext(validate_registered=False)
ctx.switch("any-tenant-id")  # Creates ad-hoc TenantInfo
```

## Custom Tenant Resolver

For complex resolution logic:

```python
from fastapi import Request
from nexus.auth.tenant.context import TenantInfo

async def custom_resolver(request: Request) -> Optional[TenantInfo]:
    """Custom resolver that checks multiple sources."""
    # Check subdomain
    host = request.headers.get("host", "")
    if "." in host:
        subdomain = host.split(".")[0]
        if subdomain not in ("www", "api"):
            return TenantInfo(tenant_id=subdomain)

    # Check path prefix
    path = request.url.path
    if path.startswith("/org/"):
        parts = path.split("/")
        if len(parts) >= 3:
            return TenantInfo(tenant_id=parts[2])

    # Fall back to JWT
    claims = getattr(request.state, "token_payload", {})
    if "tenant_id" in claims:
        return TenantInfo(tenant_id=claims["tenant_id"])

    return None

config = TenantConfig(
    custom_resolver=custom_resolver,
)
```

## Path Exclusion

Exclude paths from tenant isolation:

```python
config = TenantConfig(
    exclude_paths=[
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/api/public/*",      # Wildcard support via fnmatch
        "/webhooks/*",
    ],
)
```

## Error Responses

### Tenant Not Found (404)

```json
{
  "detail": "Tenant not found: unknown-tenant",
  "error_code": "TENANT_NOT_FOUND"
}
```

### Tenant Inactive (403)

```json
{
  "detail": "Tenant is inactive: suspended-tenant",
  "error_code": "TENANT_INACTIVE"
}
```

### Access Denied (403)

```json
{
  "detail": "Tenant override header requires 'super_admin' role",
  "error_code": "TENANT_ACCESS_DENIED"
}
```

## Request State

After TenantMiddleware processes a request:

| Attribute                 | Type         | Description             |
| ------------------------- | ------------ | ----------------------- |
| `request.state.tenant_id` | `str`        | Current tenant ID       |
| `request.state.tenant`    | `TenantInfo` | Full tenant info object |

### TenantInfo Structure

```python
@dataclass
class TenantInfo:
    tenant_id: str                          # Unique identifier
    name: Optional[str] = None              # Human-readable name
    active: bool = True                     # Whether tenant is active
    metadata: Dict[str, Any] = field(...)   # Additional data
    created_at: Optional[datetime] = None   # Creation timestamp
```

## Complete Example

```python
from fastapi import FastAPI, Request, Depends, HTTPException
from nexus.auth import (
    NexusAuthPlugin,
    JWTConfig,
    TenantConfig,
    AuthenticatedUser,
)
from nexus.auth.dependencies import get_current_user
from nexus.auth.tenant.context import get_current_tenant_id, require_tenant

app = FastAPI()

# Configure multi-tenant auth
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    tenant_isolation=TenantConfig(
        jwt_claim="org_id",           # Use org_id claim for tenant
        admin_role="super_admin",
        allow_admin_override=True,
        exclude_paths=["/health", "/auth/*"],
    ),
)
auth.install(app)

@app.get("/health")
async def health():
    """Public endpoint, no tenant context."""
    return {"status": "ok"}

@app.get("/data")
async def get_tenant_data(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Tenant-scoped data access."""
    tenant = require_tenant()

    # Filter data by tenant
    return {
        "tenant_id": tenant.tenant_id,
        "user_id": user.user_id,
        "data": f"Data for {tenant.tenant_id}",
    }

@app.get("/admin/tenants/{tenant_id}/data")
async def admin_get_tenant_data(
    tenant_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Admin endpoint with tenant override."""
    if not user.has_role("super_admin"):
        raise HTTPException(403, "Super admin required")

    # Current tenant is set from X-Tenant-ID header if provided
    current = get_current_tenant_id()

    return {
        "requested_tenant": tenant_id,
        "current_context": current,
        "data": f"Admin view of {tenant_id}",
    }
```

## Integration with DataFlow

For tenant-scoped database operations:

```python
from dataflow import DataFlow
from nexus.auth.tenant.context import get_current_tenant_id

db = DataFlow("postgresql://...")

@app.get("/users")
async def list_users():
    tenant_id = get_current_tenant_id()

    # Filter by tenant
    users = await db.execute(
        ListUser(filter={"tenant_id": tenant_id})
    )
    return users
```

## Best Practices

1. **Always validate tenant existence**: Prevents access to deleted tenants
2. **Use JWT claims as primary source**: Most secure, can't be tampered with
3. **Limit admin override**: Only super admins should access other tenants
4. **Exclude health/metrics endpoints**: System endpoints don't need tenant context
5. **Log tenant context**: Include tenant_id in all audit logs
6. **Use contextvars for background tasks**: Ensures tenant context propagates correctly
7. **Fail-closed on override attempts**: Reject unauthorized override attempts
