---
skill: nexus-enterprise-features
description: Enterprise features including authentication, authorization, rate limiting, monitoring
priority: MEDIUM
tags: [nexus, enterprise, auth, security, monitoring]
---

# Nexus Enterprise Features

Production-grade features for enterprise deployments.

## Authentication (v1.3.0+)

### NexusAuthPlugin -- The Unified Auth System

Authentication in Nexus is configured through the `NexusAuthPlugin`, which assembles
JWT, RBAC, tenant isolation, rate limiting, and audit logging into a single plugin.

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig

# Basic auth (JWT + audit)
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"])  # CRITICAL: use `secret`, NOT `secret_key`
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

### JWT Configuration (Symmetric -- HS256)

```python
from nexus.auth import JWTConfig

jwt_config = JWTConfig(
    secret=os.environ["JWT_SECRET"],      # CRITICAL: `secret`, NOT `secret_key`
    algorithm="HS256",
    exempt_paths=["/health", "/docs"],    # CRITICAL: `exempt_paths`, NOT `exclude_paths`
    verify_exp=True,
    leeway=0,
)
```

### JWT Configuration (Asymmetric -- RS256 / SSO)

```python
from nexus.auth import JWTConfig

# JWKS for SSO providers (Auth0, Okta, etc.)
jwt_config = JWTConfig(
    algorithm="RS256",
    jwks_url="https://your-tenant.auth0.com/.well-known/jwks.json",
    jwks_cache_ttl=3600,
    issuer="https://your-issuer.com",
    audience="your-api",
)
```

### SaaS Application (JWT + RBAC + Tenant Isolation)

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    tenant_isolation=TenantConfig(admin_role="admin"),  # singular `admin_role`
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

## Authorization (RBAC)

RBAC is configured as part of the NexusAuthPlugin. Use FastAPI dependencies
to enforce roles and permissions on individual endpoints.

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user
from fastapi import Depends

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={
        "admin": ["*"],                           # Full access
        "editor": ["read:*", "write:articles"],   # Wildcard + specific
        "viewer": ["read:*"],                     # Read-only
    },
    rbac_default_role="viewer",
)

app = Nexus()
app.add_plugin(auth)

# Use dependencies in custom endpoints
@app.get("/admin")
async def admin_only(user=Depends(RequireRole("admin"))):
    return {"admin": True}

@app.delete("/articles/{id}")
async def delete_article(user=Depends(RequirePermission("delete:articles"))):
    return {"deleted": True}

@app.get("/profile")
async def profile(user=Depends(get_current_user)):
    return {"user_id": user.user_id, "roles": user.roles}
```

**Permission matching:**

- `"*"` matches everything
- `"read:*"` matches `read:users`, `read:articles`, etc.
- `"*:users"` matches `read:users`, `write:users`, etc.

## Rate Limiting

### Constructor-Level Rate Limiting

```python
app = Nexus(
    rate_limit=1000,  # Requests per minute (default: 100)
)
```

### Fine-Grained Rate Limiting via NexusAuthPlugin

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from nexus.auth.rate_limit.config import RateLimitConfig

auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
        backend="memory",                    # or "redis"
        redis_url="redis://localhost:6379",  # Required if backend="redis"
        route_limits={
            "/api/chat/*": {"requests_per_minute": 30},
            "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
            "/health": None,                 # Disable rate limit for health
        },
        include_headers=True,                # X-RateLimit-* headers
        fail_open=True,                      # Allow when backend fails
    ),
)
# CRITICAL: RateLimitConfig has NO `exclude_paths` parameter

app = Nexus()
app.add_plugin(auth)
app.start()
```

## Monitoring and Observability

### Enable Monitoring via Constructor

```python
app = Nexus(
    enable_monitoring=True,
)

# Health endpoint: GET http://localhost:8000/health
```

### Health Check

```python
app = Nexus()
health = app.health_check()
print(f"Status: {health['status']}")
```

## Audit Logging

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from nexus.auth.audit.config import AuditConfig

auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    audit=AuditConfig(
        backend="logging",                   # or "dataflow"
        log_level="INFO",
        log_request_body=False,              # PII risk
        log_response_body=False,
        exclude_paths=["/health", "/metrics"],
        redact_headers=["Authorization", "Cookie"],
        redact_fields=["password", "token", "api_key"],
    ),
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

## Tenant Isolation

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from nexus.auth.tenant.config import TenantConfig

auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    tenant_isolation=TenantConfig(
        tenant_id_header="X-Tenant-ID",
        jwt_claim="tenant_id",               # Claim name in JWT
        allow_admin_override=True,
        admin_role="super_admin",            # CRITICAL: singular string, NOT `admin_roles`
        exclude_paths=["/health", "/docs"],
    ),
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

## Security Hardening

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.audit.config import AuditConfig

auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "editor": ["read:*", "write:*"], "viewer": ["read:*"]},
    rate_limit=RateLimitConfig(requests_per_minute=5000),
    tenant_isolation=TenantConfig(admin_role="admin"),
    audit=AuditConfig(backend="logging"),
)

app = Nexus(
    cors_origins=["https://app.example.com"],
    cors_allow_credentials=False,
    rate_limit=5000,
)
app.add_plugin(auth)
app.start()
```

## CORS Configuration

```python
# CORS via constructor
app = Nexus(
    cors_origins=["https://app.example.com"],
    cors_allow_credentials=False,
)
```

## Presets

```python
# One-line middleware stacks
app = Nexus(preset="saas")          # Sensible SaaS defaults
app = Nexus(preset="enterprise")    # Full enterprise stack
```

## Production Deployment Example

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.audit.config import AuditConfig

def create_production_app():
    # Auth via NexusAuthPlugin
    auth = NexusAuthPlugin.enterprise(
        jwt=JWTConfig(
            algorithm="RS256",
            jwks_url="https://auth.company.com/.well-known/jwks.json",
            jwks_cache_ttl=3600,
        ),
        rbac={"admin": ["*"], "editor": ["read:*", "write:*"], "viewer": ["read:*"]},
        rate_limit=RateLimitConfig(
            requests_per_minute=5000,
            backend="redis",
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
        ),
        tenant_isolation=TenantConfig(admin_role="admin"),
        audit=AuditConfig(backend="logging"),
    )

    app = Nexus(
        # Server
        api_port=int(os.getenv("PORT", "8000")),
        api_host="0.0.0.0",

        # Security
        rate_limit=5000,
        cors_origins=["https://app.example.com"],
        cors_allow_credentials=False,

        # Monitoring
        enable_monitoring=True,

        # Logging
        log_level="INFO",

        # Discovery
        auto_discovery=False,
    )
    app.add_plugin(auth)

    return app

# Create and start
app = create_production_app()
app.start()
```

## Best Practices

1. **Use NexusAuthPlugin** for all authentication needs
2. **Use HTTPS** for all traffic (via reverse proxy)
3. **Configure Rate Limiting** appropriately (default 100 req/min)
4. **Enable Monitoring** in production
5. **Use Redis** for distributed sessions and rate limiting
6. **Enable Audit Logging** for compliance
7. **Regular Security Audits**
8. **Use `auto_discovery=False`** with DataFlow integration

## Common Auth Gotchas

| Issue                                   | Cause                                | Fix                            |
| --------------------------------------- | ------------------------------------ | ------------------------------ |
| `TypeError: 'secret_key' unexpected`    | Wrong param name                     | Use `secret`, not `secret_key` |
| `TypeError: 'exclude_paths' unexpected` | JWTConfig uses different name        | Use `exempt_paths`             |
| `TypeError: 'admin_roles' unexpected`   | TenantConfig uses singular           | Use `admin_role` (string)      |
| FastAPI dependency injection fails      | `from __future__ import annotations` | Remove PEP 563 import          |
| RBAC without JWT                        | RBAC requires JWT                    | Add `jwt=JWTConfig(...)`       |

## Key Takeaways

- Authentication configured via `NexusAuthPlugin` (not attribute access)
- Factory methods: `basic_auth()`, `saas_app()`, `enterprise()`
- Middleware ordering handled automatically by the plugin
- RBAC uses wildcard patterns for permission matching
- Rate limiting available at constructor level or via plugin
- Audit logging integrated into the auth plugin

## Related Skills

- [nexus-auth-plugin](#) - Full NexusAuthPlugin reference
- [nexus-config-options](#) - Configuration reference
- [nexus-quickstart](#) - Basic setup
- [nexus-troubleshooting](#) - Fix production issues
