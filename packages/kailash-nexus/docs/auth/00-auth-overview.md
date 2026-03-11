# Nexus Auth Package Overview

The Nexus Auth package provides comprehensive authentication, authorization, and security features for Nexus applications. It includes JWT authentication, RBAC (Role-Based Access Control), multi-tenancy, rate limiting, audit logging, and SSO provider integrations.

## Architecture

The auth package is designed as a layered middleware stack with the **NexusAuthPlugin** as the unified entry point:

```
Request Flow (top to bottom):
+------------------------------------------+
|            Audit Middleware              |  <- Captures all requests (outermost)
+------------------------------------------+
|         Rate Limit Middleware            |  <- Prevents abuse before auth
+------------------------------------------+
|           JWT Middleware                 |  <- Core authentication
+------------------------------------------+
|          Tenant Middleware               |  <- Tenant isolation (needs JWT user)
+------------------------------------------+
|           RBAC Middleware                |  <- Permission resolution (needs JWT user)
+------------------------------------------+
|           Your Endpoint                  |  <- FastAPI route handlers
+------------------------------------------+
```

## Components

### Core Components

| Component               | Purpose                             | Config Class           |
| ----------------------- | ----------------------------------- | ---------------------- |
| **JWTMiddleware**       | Token verification, user extraction | `JWTConfig`            |
| **RBACMiddleware**      | Role/permission resolution          | `Dict[str, List[str]]` |
| **TenantMiddleware**    | Multi-tenant isolation              | `TenantConfig`         |
| **RateLimitMiddleware** | Request rate limiting               | `RateLimitConfig`      |
| **AuditMiddleware**     | Request/response logging            | `AuditConfig`          |

### Supporting Components

| Component             | Purpose                                     |
| --------------------- | ------------------------------------------- |
| **AuthenticatedUser** | Standardized user representation            |
| **RequireRole**       | FastAPI dependency for role checks          |
| **RequirePermission** | FastAPI dependency for permission checks    |
| **TenantContext**     | Thread-safe tenant state via contextvars    |
| **SSO Providers**     | Azure AD, Google, Apple, GitHub integration |

## Quick Start

### Basic Authentication (JWT Only)

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig

app = Nexus()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret="your-256-bit-secret-key-here"),
)

app.add_plugin(auth)
```

### SaaS Application (JWT + RBAC + Tenant)

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig, TenantConfig

app = Nexus()

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]  # min 32 chars),
    rbac={
        "admin": ["*"],
        "editor": ["read:*", "write:articles"],
        "viewer": ["read:*"],
    },
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",
        admin_role="super_admin",
    ),
)

app.add_plugin(auth)
```

### Enterprise (All Features)

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
        secret=os.environ["JWT_SECRET"]  # min 32 chars,
        issuer="https://myapp.com",
        audience="myapp-api",
    ),
    rbac={
        "super_admin": ["*"],
        "admin": ["read:*", "write:*", "delete:*"],
        "user": ["read:*", "write:own"],
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
)

app.add_plugin(auth)
```

## Middleware Ordering

The order of middleware execution is critical for security. **NexusAuthPlugin handles this automatically**, but if you're manually adding middleware, follow this order:

### Registration Order (reverse of execution)

When using Starlette's `add_middleware()`, middleware added later wraps middleware added earlier. So register in reverse order:

```python
# 1. RBAC (innermost - needs user from JWT)
app.add_middleware(RBACMiddleware, roles=roles)

# 2. Tenant (needs token_payload from JWT)
app.add_middleware(TenantMiddleware, config=tenant_config)

# 3. JWT (core authentication)
app.add_middleware(JWTMiddleware, config=jwt_config)

# 4. Rate Limit (before auth)
app.add_middleware(RateLimitMiddleware, config=rate_config)

# 5. Audit (outermost - captures everything)
app.add_middleware(AuditMiddleware, config=audit_config)
```

### Why This Order Matters

1. **Audit first**: Captures all requests including auth failures
2. **Rate limit before auth**: Prevents brute-force attacks on auth
3. **JWT before tenant/RBAC**: These need the authenticated user
4. **Tenant before RBAC**: RBAC may need tenant context
5. **RBAC last**: Operates on fully authenticated/contextualized request

## Request State

After middleware processing, the following attributes are available on `request.state`:

| Attribute          | Type                | Set By | Description               |
| ------------------ | ------------------- | ------ | ------------------------- |
| `user`             | `AuthenticatedUser` | JWT    | Authenticated user object |
| `token`            | `str`               | JWT    | Raw JWT token             |
| `token_payload`    | `Dict`              | JWT    | Decoded token claims      |
| `tenant_id`        | `str`               | Tenant | Current tenant ID         |
| `tenant`           | `TenantInfo`        | Tenant | Full tenant info          |
| `user_permissions` | `Set[str]`          | RBAC   | Resolved permissions      |
| `rbac_manager`     | `RBACManager`       | RBAC   | RBAC manager instance     |

## Error Responses

The auth package returns consistent JSON error responses:

### 401 Unauthorized

```json
{
  "detail": "Not authenticated",
  "error": "missing_token"
}
```

```json
{
  "detail": "Token has expired",
  "error": "token_expired"
}
```

### 403 Forbidden

```json
{
  "detail": "Requires one of roles: admin, super_admin"
}
```

```json
{
  "detail": "Tenant is inactive: tenant-123",
  "error_code": "TENANT_INACTIVE"
}
```

### 429 Too Many Requests

```json
{
  "detail": "Rate limit exceeded. Retry after 60 seconds.",
  "retry_after": 60
}
```

## Dependencies (via pip)

The auth package requires:

```
pyjwt[crypto]>=2.8.0  # JWT encoding/decoding with cryptographic algorithms
httpx>=0.24.0         # Async HTTP client for SSO providers
```

## Documentation Index

1. [JWT Authentication](./01-jwt-authentication.md) - Token verification, creation, multi-source extraction
2. [RBAC Authorization](./02-rbac-authorization.md) - Roles, permissions, wildcards, inheritance
3. [Tenant Isolation](./03-tenant-isolation.md) - Multi-tenancy, JWT claim resolution, admin override
4. [Rate Limiting](./04-rate-limiting.md) - Request limits, backends, per-route configuration
5. [Audit Logging](./05-audit-logging.md) - Request logging, backends, PII filtering
6. [SSO Providers](./06-sso-providers.md) - Azure AD, Google, Apple, GitHub integration
7. [NexusAuthPlugin](./07-nexusauthplugin.md) - Unified plugin, factory methods, configuration
