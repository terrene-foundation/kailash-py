# Nexus Agent Reference

Extracted reference material for cc-artifacts compliance.

## Authentication & Authorization (NexusAuthPlugin)

Complete auth package with JWT, RBAC, tenant isolation, rate limiting, and audit logging.

**Security Defaults (v1.4.1)**:

- `cors_allow_credentials=False` in both `Nexus()` and `NexusConfig` (safe with wildcard origins)
- JWTConfig enforces **32-character minimum** for HS\* algorithm secrets
- RBAC errors return generic "Forbidden" (no role/permission leakage)
- SSO errors are sanitized (status-only to client, details logged server-side)
- `create_access_token()` filters reserved JWT claims from `extra_claims`

### Quick Start - Factory Methods

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig

# Basic auth (JWT + audit)
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"])  # Must be >= 32 chars for HS256
)

# SaaS app (JWT + RBAC + tenant + audit)
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    tenant_isolation=TenantConfig()
)

# Enterprise (all features)
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "editor": ["read:*", "write:*"], "viewer": ["read:*"]},
    rate_limit=RateLimitConfig(requests_per_minute=100),
    tenant_isolation=TenantConfig(),
    audit=AuditConfig(backend="logging")
)

app = Nexus()
app.add_plugin(auth)
```

### JWT Configuration

```python
from nexus.auth import JWTConfig

# Symmetric (HS256) - secret MUST be >= 32 chars
jwt_config = JWTConfig(
    secret=os.environ["JWT_SECRET"],     # CRITICAL: `secret` not `secret_key`; >= 32 chars
    algorithm="HS256",
    exempt_paths=["/health", "/docs"],   # CRITICAL: `exempt_paths` not `exclude_paths`
    verify_exp=True,
    leeway=0,
)

# Asymmetric (RS256) with SSO
jwt_config = JWTConfig(
    algorithm="RS256",
    public_key="-----BEGIN PUBLIC KEY-----...",
    private_key="-----BEGIN PRIVATE KEY-----...",  # For token creation
    issuer="https://your-issuer.com",
    audience="your-api",
)

# JWKS for SSO providers (Auth0, Okta, etc.)
jwt_config = JWTConfig(
    algorithm="RS256",
    jwks_url="https://your-tenant.auth0.com/.well-known/jwks.json",
    jwks_cache_ttl=3600,
)
```

### RBAC Setup

```python
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user
from nexus.http import Depends

# Define roles in plugin
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # >= 32 chars
    rbac={
        "admin": ["*"],                           # Full access
        "editor": ["read:*", "write:articles"],   # Wildcard + specific
        "viewer": ["read:*"],                     # Read-only
    },
    rbac_default_role="viewer",  # Users without roles get this
)
# NOTE: RequireRole/RequirePermission return generic "Forbidden" (no role leakage)

# Use dependencies in endpoints
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

**Permission Matching:**

- `"*"` matches everything
- `"read:*"` matches `read:users`, `read:articles`, etc.
- `"*:users"` matches `read:users`, `write:users`, etc.

### Tenant Isolation

```python
from nexus.auth.tenant.config import TenantConfig

tenant_config = TenantConfig(
    tenant_id_header="X-Tenant-ID",
    jwt_claim="tenant_id",               # Claim name in JWT
    allow_admin_override=True,
    admin_role="super_admin",            # CRITICAL: Singular string, NOT `admin_roles`
    exclude_paths=["/health", "/docs"],
)

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # >= 32 chars
    tenant_isolation=tenant_config,
)
```

### Rate Limiting

```python
from nexus.auth.rate_limit.config import RateLimitConfig

rate_config = RateLimitConfig(
    requests_per_minute=100,
    burst_size=20,
    backend="memory",                    # or "redis"
    redis_url="redis://localhost:6379",  # Required if backend="redis"
    route_limits={
        "/api/chat/*": {"requests_per_minute": 30},
        "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
        "/health": None,                 # Disable rate limit
    },
    include_headers=True,                # X-RateLimit-* headers
    fail_open=True,                      # Allow when backend fails
)
# CRITICAL: RateLimitConfig has NO `exclude_paths` parameter
```

### Audit Logging

```python
from nexus.auth.audit.config import AuditConfig

audit_config = AuditConfig(
    backend="logging",                   # or "dataflow"
    log_level="INFO",
    log_request_body=False,              # PII risk
    log_response_body=False,
    exclude_paths=["/health", "/metrics"],
    redact_headers=["Authorization", "Cookie"],
    redact_fields=["password", "token", "api_key"],
)
```

### Middleware Ordering (CRITICAL)

Request execution order (outermost to innermost):

1. **Audit** - Captures everything
2. **RateLimit** - Before auth, prevents abuse
3. **JWT** - Core authentication
4. **Tenant** - Needs JWT user for tenant resolution
5. **RBAC** - Needs JWT user for role resolution

NexusAuthPlugin handles this automatically. Do NOT add middleware manually.

### Common Auth Gotchas

| Issue                                   | Cause                                | Fix                                   |
| --------------------------------------- | ------------------------------------ | ------------------------------------- |
| `TypeError: 'secret_key' unexpected`    | Wrong param name                     | Use `secret`, not `secret_key`        |
| `TypeError: 'exclude_paths' unexpected` | JWTConfig uses different name        | Use `exempt_paths`                    |
| `TypeError: 'admin_roles' unexpected`   | TenantConfig uses singular           | Use `admin_role` (string)             |
| Nexus dependency injection fails      | `from __future__ import annotations` | Remove PEP 563 import                 |
| Permission check fails                  | Only checking JWT direct             | Use `RequirePermission` (checks both) |
| RBAC without JWT                        | RBAC requires JWT                    | Add `jwt=JWTConfig(...)`              |

### Nexus Dependency Injection Warning

**NEVER use `from __future__ import annotations` in files with Nexus dependencies.**

```python
# auth_routes.py
# DO NOT add: from __future__ import annotations  # BREAKS INJECTION

from nexus.http import Depends, Request
from nexus.auth.dependencies import RequireRole

@app.get("/admin")
async def admin(user=Depends(RequireRole("admin"))):  # Works
    return user
```

PEP 563 turns type annotations into strings, preventing Nexus from recognizing `Request` and other special types.

## MCP Transport

- **`receive_message()`**: MCP transport now supports `receive_message()` for bidirectional communication in custom MCP transports

## Performance & Monitoring

- **SQLite CARE Audit Storage** (v0.12.2): Nexus creates `AsyncLocalRuntime()` with `enable_monitoring=True` (default), so all workflow executions automatically get CARE audit persistence to SQLite WAL-mode database. Zero in-loop I/O (~35us/node overhead) with post-execution ACID flush.

## Common Issues & Solutions

| Issue                            | Solution                                                       |
| -------------------------------- | -------------------------------------------------------------- |
| Nexus blocks on startup          | Use `auto_discovery=False` with DataFlow                       |
| Workflow not found               | Ensure `.build()` called before registration                   |
| Parameter not accessible         | Use try/except in PythonCodeNode OR use @app.handler() instead |
| Port conflicts                   | Use custom ports: `Nexus(api_port=8001)`                       |
| Import blocked in PythonCodeNode | Use @app.handler() to bypass sandbox restrictions              |
| Sandbox warnings at registration | Switch to handlers OR set sandbox_mode="permissive" (dev only) |
| Auth dependency injection fails  | Remove `from __future__ import annotations`                    |
| RBAC not resolving permissions   | Ensure JWT middleware runs before RBAC (use NexusAuthPlugin)   |

## Skill References

### Quick Start

- **[nexus-quickstart](../../.claude/skills/03-nexus/nexus-quickstart.md)** - Basic setup
- **[nexus-workflow-registration](../../.claude/skills/03-nexus/nexus-workflow-registration.md)** - Registration patterns
- **[nexus-multi-channel](../../.claude/skills/03-nexus/nexus-multi-channel.md)** - Multi-channel architecture

### Channel Patterns

- **[nexus-api-patterns](../../.claude/skills/03-nexus/nexus-api-patterns.md)** - API deployment
- **[nexus-cli-patterns](../../.claude/skills/03-nexus/nexus-cli-patterns.md)** - CLI integration
- **[nexus-mcp-channel](../../.claude/skills/03-nexus/nexus-mcp-channel.md)** - MCP server

### Integration

- **[nexus-dataflow-integration](../../.claude/skills/03-nexus/nexus-dataflow-integration.md)** - DataFlow integration
- **[nexus-sessions](../../.claude/skills/03-nexus/nexus-sessions.md)** - Session management

### Authentication & Authorization

- **[nexus-auth-plugin](../../.claude/skills/03-nexus/nexus-auth-plugin.md)** - NexusAuthPlugin unified auth
- **[nexus-enterprise-features](../../.claude/skills/03-nexus/nexus-enterprise-features.md)** - Enterprise auth patterns

## Related Agents

- **dataflow-specialist**: Database integration with Nexus platform
- **mcp-specialist**: MCP channel implementation
- **pattern-expert**: Core SDK workflows for Nexus registration
- **`decide-framework` skill**: Choose between Core SDK and Nexus
- **release-specialist**: Production deployment and scaling

## Full Documentation

When this guidance is insufficient, consult:

- `.claude/skills/03-nexus/` - Complete Nexus skills directory
- `.claude/skills/03-nexus/nexus-dataflow-integration.md` - Integration patterns
- `.claude/skills/03-nexus/nexus-troubleshooting.md` - Troubleshooting and input mapping

---

**Use this agent when:**

- Setting up Nexus production deployments
- Implementing multi-channel orchestration
- Resolving DataFlow blocking issues
- Configuring enterprise features (auth, monitoring)
- Debugging channel-specific problems

**For basic patterns (setup, simple registration), use Skills directly for faster response.**
