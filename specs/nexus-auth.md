# Kailash Nexus Specification — Authentication & Security

Version: 2.0.1
Package: `kailash-nexus`

Parent domain: Kailash Nexus (multi-channel workflow platform). This file covers JWT authentication, RBAC, CORS configuration, rate limiting, SSO integration, tenant isolation, and audit logging. See also `nexus-core.md`, `nexus-channels.md`, and `nexus-services.md`.

---

## 9. Authentication System

### 9.1 JWT Middleware

**Module:** `nexus.auth.jwt`

Core JWT validation logic lives in `kailash.trust.auth.jwt.JWTValidator`. The Nexus module retains the Starlette `BaseHTTPMiddleware` wrapper that delegates to `JWTValidator`.

```python
class JWTMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        config: Optional[JWTConfig] = None,
        *,
        secret: Optional[str] = None,
        algorithm: Optional[str] = None,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[Union[str, List[str]]] = None,
        token_header: Optional[str] = None,
        token_cookie: Optional[str] = None,
        token_query_param: Optional[str] = None,
        exempt_paths: Optional[List[str]] = None,
        jwks_url: Optional[str] = None,
    )
```

**Token extraction priority:**

1. API key header (if `api_key_enabled`).
2. `Authorization: Bearer <token>` header.
3. Cookie (if `token_cookie` configured).
4. Query parameter (if `token_query_param` configured, for WebSocket connections).

**On valid token:**

- Stores `AuthenticatedUser` on `request.state.user`.
- Stores raw token on `request.state.token`.
- Stores decoded payload on `request.state.token_payload`.
- Calls `on_token_validated` hook if configured.

**Error responses:**

- 401 `missing_token` -- no token found.
- 401 `token_expired` -- JWT has expired.
- 401 `invalid_token` -- JWT verification failed.
- 401 `invalid_api_key` -- API key validation failed.
- 401 `auth_error` -- unexpected error.

**Delegate methods (backward-compatible):**

- `create_access_token(**kwargs) -> str`
- `create_refresh_token(**kwargs) -> str`
- `_verify_token(token) -> Dict`
- `_create_user_from_payload(payload) -> AuthenticatedUser`
- `_is_path_exempt(path) -> bool`

All delegate methods guard against `None` `_validator` with a typed `RuntimeError`.

### 9.2 RBAC

**Module:** `nexus.auth.rbac`

Core RBAC logic lives in `kailash.trust.auth.rbac.RBACManager`.

**RBACMiddleware:** Attaches RBAC context (resolved permissions, `rbac_manager`) to `request.state`. Does NOT block requests -- use FastAPI dependencies for enforcement.

**FastAPI Dependencies:**

- `require_role_dep(*roles)` -- requires user to have any of the specified roles.
- `require_permission_dep(*permissions)` -- requires user to have any of the specified permissions.

**Decorators:**

- `@roles_required(*roles)` -- decorator requiring specific roles.
- `@permissions_required(*permissions)` -- decorator requiring specific permissions.

Both return 403 `Forbidden` on failure (without revealing required roles/permissions to prevent information leakage).

### 9.3 FastAPI Dependencies

**Module:** `nexus.auth.dependencies`

| Dependency                        | Returns                       | Raises                                               |
| --------------------------------- | ----------------------------- | ---------------------------------------------------- |
| `get_current_user(request)`       | `AuthenticatedUser`           | 401 if not authenticated                             |
| `get_optional_user(request)`      | `Optional[AuthenticatedUser]` | Never                                                |
| `require_auth(request)`           | `AuthenticatedUser`           | 401 (alias for `get_current_user`)                   |
| `RequireRole(*roles)`             | `AuthenticatedUser`           | 401 if not authenticated, 403 if missing roles       |
| `RequirePermission(*permissions)` | `AuthenticatedUser`           | 401 if not authenticated, 403 if missing permissions |

`RequirePermission` checks both user's direct permissions (from JWT claims) AND RBAC-resolved permissions (from `RBACMiddleware` on `request.state`).

### 9.4 NexusAuthPlugin

**Module:** `nexus.auth.plugin`

Unified auth plugin combining JWT, RBAC, rate limiting, tenant isolation, and audit logging.

**Middleware installation order (outermost to innermost):**

1. Audit (captures everything)
2. RateLimit (before auth, prevent abuse)
3. JWT (core authentication)
4. Tenant (needs JWT user for tenant claim resolution)
5. RBAC (needs JWT user for role->permission resolution)

**Dependencies:** RBAC requires JWT. Tenant isolation requires JWT. Raises `ValueError` if dependencies are not met.

**Factory methods:**

- `NexusAuthPlugin.basic_auth(jwt, audit=None)` -- JWT + audit.
- `NexusAuthPlugin.saas_app(jwt, rbac, tenant_isolation, ...)` -- multi-tenant SaaS.
- `NexusAuthPlugin.enterprise(jwt, rbac, rate_limit, tenant_isolation, audit)` -- full enterprise.

---

## 11. CORS Configuration

### 11.1 Environment-Aware Defaults

**Production (`NEXUS_ENV=production`):**

- No origins allowed by default (must be explicit).
- Methods: `["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]`.
- Headers: `["Authorization", "Content-Type", "X-Request-ID"]`.
- Credentials: `True`.
- Wildcard origins: **rejected** with `ValueError`.

**Development (default):**

- Origins: `["*"]`.
- Methods/Headers: `["*"]`.
- Credentials: `True`.

### 11.2 configure_cors

```python
def configure_cors(
    self,
    allow_origins: Optional[List[str]] = None,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
    allow_credentials: Optional[bool] = None,
    expose_headers: Optional[List[str]] = None,
    max_age: Optional[int] = None,
) -> Nexus
```

Can be called before or after `start()`. Warns if reconfiguring after gateway initialization.

### 11.3 Security Validation

- `allow_credentials=True` with `allow_origins=["*"]` logs a warning (browsers reject this combination).
- Origins not starting with `http://` or `https://` generate warnings.
- `is_origin_allowed(origin) -> bool` for runtime checks.

---

## 23. Rate Limiting

### 23.1 Endpoint-Level Rate Limiting

The `@app.endpoint()` decorator includes a built-in in-memory per-client-IP rate limiter:

- Window: 60 seconds.
- Cleanup: old entries evicted after 5 windows.
- Response on limit: 429 with `"Rate limit exceeded. Maximum N requests per minute."`.

### 23.2 Auth Rate Limiting

**Module:** `nexus.auth.rate_limit`

Provides `RateLimitMiddleware` with pluggable backends:

- `MemoryBackend` -- in-process (development/testing).
- `RedisBackend` -- distributed (production).

Configuration via `RateLimitConfig` from `kailash.trust.rate_limit.config`.

---

## 24. SSO Integration

**Module:** `nexus.auth.sso`

Providers:

- `GoogleSSO` (`nexus.auth.sso.google`)
- `GitHubSSO` (`nexus.auth.sso.github`)
- `AppleSSO` (`nexus.auth.sso.apple`)
- `AzureSSO` (`nexus.auth.sso.azure`)

All extend `BaseSSOProvider` (`nexus.auth.sso.base`).

---

## 25. Tenant Isolation

**Module:** `nexus.auth.tenant`

- `TenantMiddleware` -- extracts tenant from JWT claims or `X-Tenant-ID` header.
- `TenantConfig` -- configuration for tenant resolution strategy.
- `TenantContext` -- context var for per-request tenant state.
- `TenantResolver` -- resolves tenant from various sources.

**Contract:** Tenant-scoped operations must include `tenant_id` in cache keys, query filters, metric labels, and audit rows per `rules/tenant-isolation.md`.

---

## 26. Audit Logging

**Module:** `nexus.auth.audit`

- `AuditMiddleware` -- captures all HTTP requests with PII filtering.
- `AuditConfig` -- configuration (backend, log bodies flag).
- `PiiFilter` -- redacts sensitive fields from audit records.
- `AuditRecord` -- structured audit entry.

**Backends:**

- `LoggingAuditBackend` -- writes to structured logger.
- `DataFlowAuditBackend` -- persists to DataFlow models.
- `CustomAuditBackend` -- user-provided callback.
