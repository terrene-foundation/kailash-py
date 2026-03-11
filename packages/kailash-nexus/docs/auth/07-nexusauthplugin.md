# NexusAuthPlugin

The unified plugin that combines JWT, RBAC, rate limiting, tenant isolation, and audit logging into a single, correctly-ordered middleware stack.

## Why Use NexusAuthPlugin

1. **Correct middleware ordering**: Automatically handles the complex ordering requirements
2. **Dependency validation**: Fails fast if components have unmet dependencies
3. **Factory methods**: Pre-configured setups for common use cases
4. **Single configuration point**: All auth components in one place

## Quick Start

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig

app = Nexus()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]  # min 32 chars),
)

app.add_plugin(auth)
```

## Constructor Parameters

```python
NexusAuthPlugin(
    jwt: Optional[JWTConfig] = None,
    rbac: Optional[Dict[str, Union[List[str], Dict[str, Any]]]] = None,
    rbac_default_role: Optional[str] = None,
    rate_limit: Optional[RateLimitConfig] = None,
    tenant_isolation: Optional[TenantConfig] = None,
    audit: Optional[AuditConfig] = None,
)
```

| Parameter           | Type              | Description                                   |
| ------------------- | ----------------- | --------------------------------------------- |
| `jwt`               | `JWTConfig`       | JWT middleware configuration                  |
| `rbac`              | `Dict`            | RBAC role definitions                         |
| `rbac_default_role` | `str`             | Default role for users without explicit roles |
| `rate_limit`        | `RateLimitConfig` | Rate limiting configuration                   |
| `tenant_isolation`  | `TenantConfig`    | Tenant isolation configuration                |
| `audit`             | `AuditConfig`     | Audit logging configuration                   |

## Dependency Validation

The plugin validates dependencies at construction:

```python
# RBAC requires JWT
auth = NexusAuthPlugin(
    rbac={"admin": ["*"]},  # No jwt provided
)
# ValueError: RBAC requires JWT middleware. Provide jwt=JWTConfig(...) when using rbac.

# Tenant requires JWT
auth = NexusAuthPlugin(
    tenant_isolation=TenantConfig(),  # No jwt provided
)
# ValueError: Tenant isolation requires JWT middleware. Provide jwt=JWTConfig(...) when using tenant_isolation.
```

## Middleware Ordering

The plugin installs middleware in the correct order for request processing:

```
Request Flow (outermost to innermost):
1. Audit      <- Captures all requests/responses
2. RateLimit  <- Prevents abuse before auth
3. JWT        <- Core authentication
4. Tenant     <- Needs user from JWT
5. RBAC       <- Needs user from JWT
```

In Starlette, middleware added later wraps earlier middleware. So the plugin adds in reverse order (RBAC first, Audit last).

## Factory Methods

### basic_auth()

JWT authentication with audit logging:

```python
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]  # min 32 chars),
    audit=AuditConfig(backend="logging"),  # Optional, defaults to logging
)
```

Use case: Simple APIs that need authentication and audit trail.

### saas_app()

Multi-tenant SaaS application setup:

```python
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"]  # min 32 chars,
        issuer="https://myapp.com",
    ),
    rbac={
        "admin": ["*"],
        "editor": ["read:*", "write:*"],
        "viewer": ["read:*"],
    },
    tenant_isolation=TenantConfig(
        jwt_claim="org_id",
        admin_role="super_admin",
    ),
    audit=AuditConfig(backend="logging"),  # Optional
    rbac_default_role="viewer",  # Optional
)
```

Use case: Multi-tenant applications with role-based access control.

### enterprise()

Full-featured enterprise setup:

```python
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"]  # min 32 chars,
        algorithm="HS256",
        issuer="https://myapp.com",
        audience="myapp-api",
    ),
    rbac={
        "super_admin": {
            "permissions": ["*"],
            "description": "Full system access",
        },
        "admin": {
            "permissions": ["manage:*"],
            "inherits": ["user"],
        },
        "user": {
            "permissions": ["read:*", "write:own"],
        },
    },
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
        backend="redis",
        redis_url="redis://localhost:6379/0",
    ),
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",
        admin_role="super_admin",
        allow_admin_override=True,
    ),
    audit=AuditConfig(
        backend="dataflow",
        log_request_body=True,
    ),
    rbac_default_role="user",
)
```

Use case: Enterprise applications requiring all security features.

## Manual Configuration

For custom component combinations:

```python
auth = NexusAuthPlugin(
    # JWT only (required for RBAC and tenant)
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]  # min 32 chars),

    # Optional: RBAC
    rbac={
        "admin": ["*"],
        "user": ["read:*"],
    },
    rbac_default_role="user",

    # Optional: Tenant isolation
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",
    ),

    # Optional: Rate limiting
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
    ),

    # Optional: Audit logging
    audit=AuditConfig(
        backend="logging",
    ),
)
```

## Plugin Properties

### enabled_components

List of enabled component names:

```python
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    rbac={"admin": ["*"]},
    audit=AuditConfig(),
)

print(auth.enabled_components)
# ['jwt', 'rbac', 'audit']
```

### name and description

```python
print(auth.name)
# 'nexus_auth'

print(auth.description)
# 'Auth plugin (JWT, RBAC, Audit)'
```

## Installation Methods

### Using add_plugin (Recommended)

```python
app = Nexus()
app.add_plugin(auth)
```

### Using install directly

```python
app = FastAPI()
auth.install(app)
```

Both methods call the same installation logic.

## Complete Examples

### API with Basic Auth

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig, AuditConfig

app = Nexus()

auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],  # min 32 chars
        exempt_paths=["/health", "/docs", "/openapi.json"],
    ),
)

app.add_plugin(auth)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/data")
async def get_data():
    return {"data": "authenticated"}
```

### Multi-Tenant SaaS

```python
from nexus import Nexus
from nexus.auth import (
    NexusAuthPlugin,
    JWTConfig,
    TenantConfig,
    AuditConfig,
)
from nexus.auth.dependencies import RequireRole, RequirePermission

app = Nexus()

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"]  # min 32 chars,
        issuer="https://myapp.com",
    ),
    rbac={
        "owner": ["*"],
        "admin": ["read:*", "write:*", "manage:users"],
        "member": ["read:*", "write:own"],
    },
    tenant_isolation=TenantConfig(
        jwt_claim="org_id",
        admin_role="super_admin",
    ),
    rbac_default_role="member",
)

app.add_plugin(auth)

@app.get("/api/team")
async def get_team(user = Depends(RequirePermission("read:team"))):
    return {"members": []}

@app.post("/api/team/invite")
async def invite_member(user = Depends(RequirePermission("manage:users"))):
    return {"invited": True}
```

### Enterprise Application

```python
from nexus import Nexus
from nexus.auth import (
    NexusAuthPlugin,
    JWTConfig,
    TenantConfig,
    RateLimitConfig,
    AuditConfig,
)

app = Nexus()

auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],  # min 32 chars
        algorithm="HS256",
        issuer="https://api.enterprise.com",
        audience="enterprise-api",
        exempt_paths=[
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/auth/login",
            "/auth/sso/*",
        ],
    ),
    rbac={
        "super_admin": {
            "permissions": ["*"],
            "description": "System administrator",
        },
        "org_admin": {
            "permissions": ["manage:org", "manage:users"],
            "inherits": ["user"],
            "description": "Organization administrator",
        },
        "user": {
            "permissions": ["read:*", "write:own"],
            "description": "Standard user",
        },
        "readonly": {
            "permissions": ["read:*"],
            "description": "Read-only access",
        },
    },
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
        backend="redis",
        redis_url="redis://redis:6379/0",
        route_limits={
            "/api/ai/*": {"requests_per_minute": 10},
            "/api/export/*": {"requests_per_minute": 5},
            "/health": None,
            "/metrics": None,
        },
    ),
    tenant_isolation=TenantConfig(
        jwt_claim="org_id",
        admin_role="super_admin",
        allow_admin_override=True,
        exclude_paths=["/health", "/metrics", "/auth/*"],
    ),
    audit=AuditConfig(
        backend="dataflow",
        include_query_params=True,
        exclude_paths=["/health", "/metrics"],
    ),
    rbac_default_role="readonly",
)

app.add_plugin(auth)
```

## Configuration Reference

### JWTConfig Parameters

| Parameter      | Type        | Default | Description                |
| -------------- | ----------- | ------- | -------------------------- |
| `secret`       | `str`       | None    | Secret for HS\* algorithms |
| `algorithm`    | `str`       | "HS256" | JWT algorithm              |
| `public_key`   | `str`       | None    | Public key for RS*/ES*     |
| `exempt_paths` | `List[str]` | [...]   | Paths exempt from auth     |
| `jwks_url`     | `str`       | None    | JWKS endpoint URL          |

### TenantConfig Parameters

| Parameter              | Type        | Default       | Description                |
| ---------------------- | ----------- | ------------- | -------------------------- |
| `jwt_claim`            | `str`       | "tenant_id"   | Claim containing tenant ID |
| `admin_role`           | `str`       | "super_admin" | Role for admin override    |
| `allow_admin_override` | `bool`      | True          | Allow X-Tenant-ID header   |
| `exclude_paths`        | `List[str]` | [...]         | Paths to exclude           |

### RateLimitConfig Parameters

| Parameter             | Type   | Default  | Description             |
| --------------------- | ------ | -------- | ----------------------- |
| `requests_per_minute` | `int`  | 100      | Base rate limit         |
| `burst_size`          | `int`  | 20       | Burst allowance         |
| `backend`             | `str`  | "memory" | "memory" or "redis"     |
| `route_limits`        | `Dict` | {}       | Per-route overrides     |
| `include_headers`     | `bool` | True     | Add X-RateLimit headers |

### AuditConfig Parameters

| Parameter          | Type        | Default   | Description                        |
| ------------------ | ----------- | --------- | ---------------------------------- |
| `backend`          | `str`       | "logging" | "logging", "dataflow", or callable |
| `exclude_paths`    | `List[str]` | [...]     | Paths to exclude                   |
| `log_request_body` | `bool`      | False     | Log request bodies                 |
| `redact_fields`    | `List[str]` | [...]     | Fields to redact                   |

## Best Practices

1. **Use factory methods**: They enforce common patterns and sensible defaults
2. **Always configure exempt_paths**: Reduce noise from health checks
3. **Use Redis for rate limiting in production**: Memory backend doesn't scale
4. **Enable audit logging**: Essential for security and compliance
5. **Set rbac_default_role**: Ensures users always have baseline permissions
6. **Configure tenant isolation early**: Prevents cross-tenant data access
7. **Test middleware order**: Verify auth errors are logged by audit
