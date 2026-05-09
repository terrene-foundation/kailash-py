---
skill: nexus-auth-plugin
description: Unified authentication architecture with JWT, RBAC, tenant isolation, rate limiting, and audit logging
priority: HIGH
tags: [nexus, auth, jwt, rbac, tenant, rate-limit, audit, sso]
---

# Nexus Auth Architecture

## Overview

Nexus authentication is built as a unified plugin that assembles JWT verification, RBAC, tenant isolation, rate limiting, and audit logging into a single composable unit. The plugin manages middleware ordering automatically, preventing common security misconfigurations.

## When to Use

- Any production Nexus deployment requiring authentication
- SaaS applications with multi-tenant data isolation
- APIs with role-based or permission-based access control
- Applications integrating with SSO providers (Auth0, Okta, Azure AD, Google)
- Compliance-sensitive deployments requiring audit trails

## Architecture

### Component Assembly

The auth plugin assembles independent security components into a correctly-ordered middleware stack:

```
Auth Plugin
    |
    +-- JWT Component (token verification, user resolution)
    +-- RBAC Component (role-to-permission mapping)
    +-- Tenant Component (tenant isolation enforcement)
    +-- Rate Limit Component (request throttling)
    +-- Audit Component (request/response logging)
```

### Middleware Execution Order

The plugin installs middleware in a fixed, security-correct order:

```
Request -> Audit -> Rate Limit -> JWT -> Tenant -> RBAC -> Handler
Response <- Audit <- Rate Limit <- JWT <- Tenant <- RBAC <- Handler
```

1. **Audit** (outermost) -- logs all requests including rejected ones
2. **Rate Limit** -- blocks abuse before incurring authentication overhead
3. **JWT** -- authenticates and populates user context
4. **Tenant** -- resolves tenant from authenticated user's claims
5. **RBAC** (innermost) -- checks permissions against resolved roles

## Configuration Tiers

Three factory methods provide escalating feature sets:

| Factory    | JWT | RBAC | Tenant | Rate Limit | Audit         |
| ---------- | --- | ---- | ------ | ---------- | ------------- |
| Basic auth | Yes | No   | No     | No         | Yes (default) |
| SaaS app   | Yes | Yes  | Yes    | No         | Yes (default) |
| Enterprise | Yes | Yes  | Yes    | Yes        | Yes           |

## JWT Configuration

### Signing Algorithms

| Algorithm          | Use Case                        | Key Material                                   |
| ------------------ | ------------------------------- | ---------------------------------------------- |
| HS256 (symmetric)  | Development, simple deployments | Shared secret (minimum 32 characters enforced) |
| RS256 (asymmetric) | Production, SSO integration     | Public/private key pair or JWKS URL            |

### Token Extraction Priority

1. `Authorization: Bearer <token>` header
2. Cookie (if configured)
3. Query parameter (if configured)

### SSO Integration

JWKS (JSON Web Key Set) support enables automatic key rotation with SSO providers. The JWKS response is cached with a configurable TTL. Compatible with:

- Auth0
- Azure AD
- Google
- Okta
- Any provider publishing a `.well-known/jwks.json` endpoint

### Path Exemption

Certain paths (health checks, documentation, login endpoints) can be exempted from JWT verification.

## RBAC Configuration

### Role Definitions

Roles map to permission lists. Two formats are supported:

**Simple format**: Role name maps to a list of permission strings.

**Full format**: Role name maps to an object with permissions and optional inheritance.

### Permission Wildcards

| Pattern     | Matches                                           |
| ----------- | ------------------------------------------------- |
| `"*"`       | Everything                                        |
| `"read:*"`  | `read:users`, `read:articles`, etc.               |
| `"*:users"` | `read:users`, `write:users`, `delete:users`, etc. |

### Role Inheritance

Roles can inherit permissions from other roles, creating a permission hierarchy without duplication.

### Per-Handler Authorization

Individual handlers can require specific roles or permissions. The auth system checks both:

1. Direct permissions from the JWT `permissions` claim
2. RBAC-resolved permissions from the user's roles

## Tenant Isolation

### Tenant Resolution

Tenant ID is resolved from multiple sources in priority order:

1. JWT claim (e.g., `tenant_id` in the token payload)
2. HTTP header (e.g., `X-Tenant-ID`)
3. User organization lookup (fallback)

### Admin Override

A designated admin role can access data across all tenants, bypassing isolation checks.

## Rate Limiting

### Configuration Options

| Setting             | Description                                        |
| ------------------- | -------------------------------------------------- |
| Requests per minute | Sustained rate limit                               |
| Burst size          | Short-term allowance above sustained rate          |
| Backend             | In-memory (single instance) or Redis (distributed) |
| Per-route limits    | Different rates for different endpoints            |
| Response headers    | Standard `X-RateLimit-*` headers                   |
| Fail-open           | Allow requests when backend is unavailable         |

Specific routes can have rate limiting disabled entirely (e.g., health endpoints).

## Audit Logging

### Configuration Options

| Setting          | Description                                        |
| ---------------- | -------------------------------------------------- |
| Backend          | Structured logging or DataFlow persistence         |
| Body logging     | Optionally log request/response bodies (PII risk)  |
| Path exclusion   | Skip high-frequency endpoints                      |
| Header redaction | Strip sensitive headers (Authorization, Cookie)    |
| Field redaction  | Remove sensitive fields (password, token, api_key) |

## Security Defaults

- HS256 secrets must be at least 32 characters (enforced with validation error)
- RBAC errors return generic "Forbidden" responses (no role or permission leakage)
- SSO errors are sanitized (status-only to client, details logged server-side)
- Token creation filters reserved JWT claims from extra claims
- CORS credentials default to disabled (safe with wildcard origins)

## Common Pitfalls

| Issue                          | Root Cause                                | Resolution                                           |
| ------------------------------ | ----------------------------------------- | ---------------------------------------------------- |
| Wrong secret parameter name    | Configuration uses `secret_key`           | Use `secret`                                         |
| Wrong path exemption parameter | Configuration uses `exclude_paths`        | Use `exempt_paths`                                   |
| Wrong admin role parameter     | Configuration uses `admin_roles` (plural) | Use `admin_role` (singular string)                   |
| Dependency injection fails     | PEP 563 future annotations enabled        | Remove `from __future__ import annotations`          |
| RBAC without JWT               | RBAC requires JWT for user context        | Always configure JWT when using RBAC                 |
| Permission check incomplete    | Only checking JWT direct permissions      | Use permission dependency (checks both JWT and RBAC) |

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-enterprise-features](nexus-enterprise-features.md) - Enterprise deployment patterns
- [nexus-k8s-probes](nexus-k8s-probes.md) - Security middleware and probes
- [nexus-quickstart](nexus-quickstart.md) - Basic setup
