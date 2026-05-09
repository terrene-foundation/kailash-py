---
skill: nexus-enterprise-features
description: Enterprise capabilities including authentication, RBAC, tenant isolation, CORS, and rate limiting
priority: MEDIUM
tags: [nexus, enterprise, auth, security, monitoring]
---

# Nexus Enterprise Features

## Overview

Nexus includes a comprehensive enterprise feature set covering authentication, authorization, multi-tenancy, rate limiting, audit logging, and CORS configuration. These features are delivered through a unified auth plugin system and constructor-level configuration, with automatic middleware ordering.

## When to Use

- Deploying Nexus to production with authentication requirements
- Building SaaS applications with tenant isolation
- Implementing role-based access control (RBAC)
- Adding rate limiting and abuse prevention
- Meeting compliance requirements with audit logging

## Architecture

Enterprise features are assembled through a single auth plugin that combines multiple middleware layers. The plugin installs middleware in the correct execution order automatically:

```
Inbound Request
    |
    v
Audit Logging (outermost -- captures everything)
    |
    v
Rate Limiting (blocks before authentication overhead)
    |
    v
JWT Authentication (validates token, populates user context)
    |
    v
Tenant Isolation (resolves tenant from JWT claims)
    |
    v
RBAC Authorization (resolves permissions from roles)
    |
    v
Handler Execution
```

## Capabilities

### Authentication (JWT)

| Capability                 | Description                                                        |
| -------------------------- | ------------------------------------------------------------------ |
| Symmetric signing (HS256)  | Shared secret, minimum 32 characters enforced                      |
| Asymmetric signing (RS256) | Public/private key pairs for production deployments                |
| JWKS support               | Auto-fetch keys from SSO providers (Auth0, Okta, Azure AD, Google) |
| Token extraction           | Authorization header, cookie, or query parameter                   |
| Path exemption             | Skip authentication for health checks, docs, public endpoints      |
| Token creation             | Generate access and refresh tokens                                 |

### Authorization (RBAC)

| Capability              | Description                                                                |
| ----------------------- | -------------------------------------------------------------------------- |
| Role definitions        | Map roles to permission lists                                              |
| Permission wildcards    | `"*"` (all), `"read:*"` (read anything), `"*:users"` (any action on users) |
| Role inheritance        | Roles can inherit permissions from other roles                             |
| Default roles           | Assign a fallback role to users without explicit roles                     |
| Per-handler enforcement | Require specific roles or permissions on individual endpoints              |

### Tenant Isolation

| Capability                     | Description                             |
| ------------------------------ | --------------------------------------- |
| JWT-based tenant resolution    | Extract tenant ID from JWT claims       |
| Header-based tenant resolution | Accept tenant ID via HTTP header        |
| Admin override                 | Allow super-admin access across tenants |
| Path exclusion                 | Skip tenant checks for public endpoints |

### Rate Limiting

| Capability         | Description                                        |
| ------------------ | -------------------------------------------------- |
| Global rate limits | Requests per minute at the application level       |
| Per-route limits   | Different limits for different endpoints           |
| Burst allowance    | Short-term burst above sustained rate              |
| Backend options    | In-memory (single instance) or Redis (distributed) |
| Response headers   | Standard `X-RateLimit-*` headers                   |
| Fail-open mode     | Allow requests when the rate limit backend is down |

### Audit Logging

| Capability               | Description                                                 |
| ------------------------ | ----------------------------------------------------------- |
| Request/response logging | Configurable granularity                                    |
| Field redaction          | Automatically redact sensitive fields (passwords, tokens)   |
| Header redaction         | Strip authorization headers from logs                       |
| Path exclusion           | Skip logging for high-frequency endpoints (health, metrics) |
| Backend options          | Structured logging or DataFlow persistence                  |

### CORS

| Capability          | Description                                      |
| ------------------- | ------------------------------------------------ |
| Origin allowlist    | Restrict to specific origins                     |
| Credentials control | Enable/disable cookie and auth header forwarding |

### Deployment Presets

Pre-configured middleware stacks for common deployment scenarios:

| Preset      | Includes                                       |
| ----------- | ---------------------------------------------- |
| None        | No middleware                                  |
| Lightweight | Security headers only                          |
| Standard    | Security headers + CSRF + CORS + rate limiting |
| SaaS        | Standard + tenant isolation                    |
| Enterprise  | SaaS + audit logging                           |

## Configuration Tiers

Enterprise features can be configured at three levels:

1. **Constructor** -- Basic settings (port, CORS, global rate limit, monitoring toggle)
2. **Auth plugin factory methods** -- Pre-assembled feature bundles (basic, SaaS, enterprise)
3. **Individual config objects** -- Fine-grained control over each component

### Factory Method Summary

| Factory    | Includes                                                      |
| ---------- | ------------------------------------------------------------- |
| Basic auth | JWT + audit logging                                           |
| SaaS app   | JWT + RBAC + tenant isolation + audit logging                 |
| Enterprise | JWT + RBAC + rate limiting + tenant isolation + audit logging |

## Common Configuration Pitfalls

| Issue                       | Cause                                     | Resolution                              |
| --------------------------- | ----------------------------------------- | --------------------------------------- |
| RBAC without authentication | RBAC requires JWT to resolve user roles   | Always configure JWT when using RBAC    |
| Weak signing secret         | HS256 secret under 32 characters          | Use secrets of 32+ characters           |
| Credential leakage in CORS  | Wildcard origins with credentials enabled | Restrict origins when using credentials |

## Production Deployment Checklist

1. Use asymmetric signing (RS256) or JWKS for SSO integration
2. Configure rate limiting with Redis backend for distributed deployments
3. Enable audit logging with field redaction for PII protection
4. Set `auto_discovery=False` when integrating with DataFlow
5. Restrict CORS origins to known domains
6. Set up monitoring endpoints for health checks
7. Use HTTPS via reverse proxy for all traffic

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-auth-plugin](nexus-auth-plugin.md) - Detailed auth plugin reference
- [nexus-health-monitoring](nexus-health-monitoring.md) - Monitoring and observability
- [nexus-k8s-probes](nexus-k8s-probes.md) - Kubernetes integration
- [nexus-quickstart](nexus-quickstart.md) - Basic setup
