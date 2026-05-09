---
skill: nexus-k8s-probes
description: Kubernetes probes, OpenAPI generation, security middleware, and deployment presets
priority: MEDIUM
tags: [nexus, kubernetes, probes, openapi, security, middleware, csrf]
---

# Nexus Kubernetes Probes, OpenAPI, and Security Middleware

## Overview

Nexus provides Kubernetes-native health probes, automatic OpenAPI specification generation from handler type information, security header middleware, CSRF protection, and deployment presets that bundle middleware configurations for common scenarios.

## When to Use

- Deploying Nexus in Kubernetes with readiness/liveness/startup probes
- Generating OpenAPI documentation from registered handlers
- Hardening HTTP responses with security headers
- Protecting against CSRF attacks in browser-facing deployments
- Selecting a pre-configured middleware stack for a deployment scenario

## Kubernetes Probes

### Probe Endpoints

| Endpoint   | Purpose                                    | Kubernetes Probe Type |
| ---------- | ------------------------------------------ | --------------------- |
| `/healthz` | Is the application alive?                  | Liveness probe        |
| `/readyz`  | Is the application ready to serve traffic? | Readiness probe       |
| `/startup` | Has the application finished starting?     | Startup probe         |

### Probe State Machine

Probes follow a state machine with thread-safe, atomic transitions:

```
STARTING --> READY --> DRAINING
    |          |          |
    +----------+----------+
               |
               v
            FAILED
```

| State    | Liveness | Readiness | Startup |
| -------- | -------- | --------- | ------- |
| Starting | 200      | 503       | 503     |
| Ready    | 200      | 200       | 200     |
| Draining | 200      | 503       | 200     |
| Failed   | 503      | 503       | 503     |

### Readiness Callbacks

Custom readiness checks can be registered to verify that dependencies (databases, caches, external services) are available before the application accepts traffic.

## OpenAPI Generation

Nexus can automatically generate an OpenAPI 3.0.3 specification from registered handlers:

- Schema derived from handler parameter type annotations
- Endpoint exposed at `/openapi.json`
- Includes handler descriptions, parameter types, and defaults
- Title and version configurable

## Security Middleware

### Security Headers

Applies standard security headers to all HTTP responses:

| Header                           | Purpose                       |
| -------------------------------- | ----------------------------- |
| Content-Security-Policy (CSP)    | Restricts content sources     |
| Strict-Transport-Security (HSTS) | Forces HTTPS                  |
| X-Content-Type-Options           | Prevents MIME sniffing        |
| X-Frame-Options                  | Prevents clickjacking         |
| X-XSS-Protection                 | Enables browser XSS filter    |
| Referrer-Policy                  | Controls referrer information |

Configuration options include CSP directives, HSTS max-age, and frame options.

### CSRF Protection

Origin-based CSRF protection for state-changing requests:

- Validates `Origin` and `Referer` headers on POST, PUT, DELETE, PATCH
- GET, HEAD, and OPTIONS requests bypass validation
- Configurable allowed origins
- Path exemptions for webhooks and API callbacks

## Middleware Presets

Pre-assembled middleware stacks for common deployment scenarios:

| Preset        | Middleware Included                            |
| ------------- | ---------------------------------------------- |
| `none`        | No middleware                                  |
| `lightweight` | Security headers                               |
| `standard`    | Security headers + CSRF + CORS + rate limiting |
| `saas`        | Standard + tenant isolation                    |
| `enterprise`  | SaaS + audit logging                           |

Presets are selected at Nexus construction time and can be overridden with individual middleware configuration.

## Best Practices

1. **Always configure probes in Kubernetes** -- without them, the orchestrator cannot manage application lifecycle
2. **Use startup probes for slow-starting applications** -- prevents premature liveness failures
3. **Set readiness to false during shutdown** -- allows graceful connection draining
4. **Register readiness callbacks for all dependencies** -- prevents serving traffic before dependencies are ready
5. **Use the `standard` preset as a baseline** -- add or remove middleware as needed

See language-specific variant for implementation details and code examples.

## Related Skills

- [nexus-health-monitoring](nexus-health-monitoring.md) - Application-level health monitoring
- [nexus-enterprise-features](nexus-enterprise-features.md) - Enterprise middleware stack
- [nexus-transport-architecture](nexus-transport-architecture.md) - HTTP transport layer
