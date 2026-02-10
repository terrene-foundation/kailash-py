---
skill: nexus-auth-plugin
description: NexusAuthPlugin unified authentication with JWT, RBAC, tenant isolation, rate limiting, and audit logging
priority: HIGH
tags: [nexus, auth, jwt, rbac, tenant, rate-limit, audit, sso]
---

# NexusAuthPlugin - Unified Authentication

Complete auth package combining JWT, RBAC, rate limiting, tenant isolation, and audit logging into a single plugin.

**Security Defaults (v1.3.0)**:

- JWTConfig enforces **32-char minimum** for HS\* secrets (`ValueError` if shorter)
- RBAC errors return generic "Forbidden" (no role/permission leakage)
- SSO errors are sanitized (status-only to client, details logged server-side)
- `create_access_token()` filters reserved claims from `extra_claims`

## Quick Reference

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig
```

## Factory Methods (Recommended)

### Basic Auth (JWT + Audit)

```python
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # Must be >= 32 chars for HS256
    audit=AuditConfig(backend="logging"),  # Optional, defaults to logging
)
app = Nexus()
app.add_plugin(auth)
```

### SaaS App (JWT + RBAC + Tenant + Audit)

```python
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={
        "admin": ["*"],
        "user": ["read:*", "write:own"],
    },
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",
        admin_role="super_admin",
    ),
    rbac_default_role="user",
)
```

### Enterprise (All Features)

```python
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],  # >= 32 chars
        issuer="https://your-domain.com",
        audience="your-api",
    ),
    rbac={
        "super_admin": ["*"],
        "admin": {"permissions": ["admin:*"], "inherits": ["editor"]},
        "editor": ["read:*", "write:*"],
        "viewer": ["read:*"],
    },
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
        backend="redis",
        redis_url="redis://localhost:6379",
    ),
    tenant_isolation=TenantConfig(),
    audit=AuditConfig(backend="logging", log_request_body=True),
)
```

## Component Configurations

### JWTConfig

```python
from nexus.auth import JWTConfig

# Symmetric (HS256) - secret MUST be >= 32 chars
jwt = JWTConfig(
    secret=os.environ["JWT_SECRET"],   # REQUIRED for HS*; >= 32 chars or ValueError
    algorithm="HS256",                  # Default
    exempt_paths=["/health", "/docs", "/auth/login"],
    verify_exp=True,
    leeway=0,                           # Seconds tolerance for exp/nbf
)

# Asymmetric (RS256) - Production
jwt = JWTConfig(
    algorithm="RS256",
    public_key="-----BEGIN PUBLIC KEY-----...",
    private_key="-----BEGIN PRIVATE KEY-----...",  # For token creation
    issuer="https://auth.example.com",
    audience="https://api.example.com",
)

# JWKS (SSO providers - Auth0, Okta, Azure AD)
jwt = JWTConfig(
    algorithm="RS256",
    jwks_url="https://your-tenant.auth0.com/.well-known/jwks.json",
    jwks_cache_ttl=3600,
    issuer="https://your-tenant.auth0.com/",
)
```

**Token Extraction Priority:**

1. `Authorization: Bearer <token>` header
2. Cookie (if `token_cookie` configured)
3. Query parameter (if `token_query_param` configured)

### RBAC Roles

```python
# Simple format: role -> list of permissions
rbac = {
    "admin": ["*"],
    "editor": ["read:*", "write:articles", "write:comments"],
    "viewer": ["read:*"],
}

# Full format with inheritance
rbac = {
    "super_admin": {"permissions": ["*"], "description": "Full access"},
    "admin": {
        "permissions": ["admin:*"],
        "inherits": ["editor"],  # Gets all editor permissions too
    },
    "editor": {
        "permissions": ["write:*"],
        "inherits": ["viewer"],
    },
    "viewer": {"permissions": ["read:*"]},
}
```

**Permission Wildcards:**

- `"*"` - matches everything
- `"read:*"` - matches `read:users`, `read:articles`, etc.
- `"*:users"` - matches `read:users`, `write:users`, etc.

### TenantConfig

```python
from nexus.auth.tenant.config import TenantConfig

tenant = TenantConfig(
    tenant_id_header="X-Tenant-ID",      # Header for explicit tenant
    jwt_claim="tenant_id",               # JWT claim name
    fallback_to_user_org=True,           # Look up from user record
    allow_admin_override=True,           # Super admins access any tenant
    admin_role="super_admin",            # SINGULAR string, not list
    exclude_paths=["/health", "/docs"],
)
```

### RateLimitConfig

```python
from nexus.auth.rate_limit.config import RateLimitConfig

rate_limit = RateLimitConfig(
    requests_per_minute=100,
    burst_size=20,
    backend="memory",                    # or "redis"
    redis_url="redis://localhost:6379",  # Required if backend="redis"
    route_limits={
        "/api/chat/*": {"requests_per_minute": 30},
        "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
        "/health": None,                 # Disable for this route
    },
    include_headers=True,                # Add X-RateLimit-* headers
    fail_open=True,                      # Allow when backend fails
)
```

### AuditConfig

```python
from nexus.auth.audit.config import AuditConfig

audit = AuditConfig(
    backend="logging",                   # or "dataflow"
    log_level="INFO",
    log_request_body=False,
    log_response_body=False,
    max_body_log_size=10 * 1024,         # 10KB
    exclude_paths=["/health", "/metrics"],
    exclude_methods=["OPTIONS"],
    redact_headers=["Authorization", "Cookie", "X-API-Key"],
    redact_fields=["password", "token", "secret", "api_key"],
)
```

## FastAPI Dependencies

```python
from fastapi import Depends
from nexus.auth.dependencies import (
    get_current_user,
    get_optional_user,
    RequireRole,
    RequirePermission,
)

# Get authenticated user (401 if not authenticated)
@app.get("/profile")
async def profile(user=Depends(get_current_user)):
    return {"user_id": user.user_id}

# Optional user (None if not authenticated)
@app.get("/public")
async def public(user=Depends(get_optional_user)):
    return {"authenticated": user is not None}

# Require specific role
@app.get("/admin")
async def admin(user=Depends(RequireRole("admin", "super_admin"))):
    return {"admin": True}

# Require specific permission
@app.delete("/articles/{id}")
async def delete(user=Depends(RequirePermission("delete:articles"))):
    return {"deleted": True}
```

## Middleware Execution Order

NexusAuthPlugin installs middleware in the correct order automatically:

```
Request -> Audit -> RateLimit -> JWT -> Tenant -> RBAC -> Handler
Response <- Audit <- RateLimit <- JWT <- Tenant <- RBAC <- Handler
```

1. **Audit** (outermost) - Logs all requests/responses
2. **RateLimit** - Blocks before authentication overhead
3. **JWT** - Authenticates and populates `request.state.user`
4. **Tenant** - Resolves tenant from JWT claims
5. **RBAC** (innermost) - Resolves permissions from roles

## Common Gotchas

### Parameter Name Mismatches

| Wrong           | Correct        | Component    |
| --------------- | -------------- | ------------ |
| `secret_key`    | `secret`       | JWTConfig    |
| `exclude_paths` | `exempt_paths` | JWTConfig    |
| `admin_roles`   | `admin_role`   | TenantConfig |

### PEP 563 Breaks FastAPI Injection

```python
# NEVER do this in files with FastAPI dependencies:
from __future__ import annotations  # BREAKS INJECTION

# FastAPI cannot inject Request when annotations are strings
```

### RBAC Requires JWT

```python
# This will raise ValueError:
auth = NexusAuthPlugin(
    rbac={"admin": ["*"]},  # Error: RBAC requires JWT
)

# Correct:
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # >= 32 chars
    rbac={"admin": ["*"]},
)
```

### RequirePermission Checks Both Sources

`RequirePermission` checks:

1. User's direct permissions (from JWT `permissions` claim)
2. RBAC-resolved permissions (from roles via RBACMiddleware)

If using RBAC, ensure RBACMiddleware is installed (NexusAuthPlugin does this automatically).

## Token Creation

```python
# Get JWTMiddleware instance
jwt_middleware = ...

# Create access token
access_token = jwt_middleware.create_access_token(
    user_id="user123",
    email="user@example.com",
    roles=["editor"],
    permissions=["write:articles"],
    tenant_id="tenant456",
    expires_minutes=30,
)

# Create refresh token
refresh_token = jwt_middleware.create_refresh_token(
    user_id="user123",
    tenant_id="tenant456",
    expires_days=7,
)
```

## SSO Provider Examples

### Auth0

```python
jwt = JWTConfig(
    algorithm="RS256",
    jwks_url="https://YOUR_DOMAIN.auth0.com/.well-known/jwks.json",
    issuer="https://YOUR_DOMAIN.auth0.com/",
    audience="YOUR_API_IDENTIFIER",
)
```

### Azure AD

```python
jwt = JWTConfig(
    algorithm="RS256",
    jwks_url="https://login.microsoftonline.com/TENANT_ID/discovery/v2.0/keys",
    issuer="https://login.microsoftonline.com/TENANT_ID/v2.0",
    audience="YOUR_CLIENT_ID",
)
```

### Google

```python
jwt = JWTConfig(
    algorithm="RS256",
    jwks_url="https://www.googleapis.com/oauth2/v3/certs",
    issuer="https://accounts.google.com",
    audience="YOUR_CLIENT_ID",
)
```

## Related Skills

- [nexus-enterprise-features](nexus-enterprise-features.md) - Enterprise deployment patterns
- [nexus-security-best-practices](nexus-security-best-practices.md) - Security hardening
- [nexus-production-deployment](nexus-production-deployment.md) - Production setup
