---
skill: nexus-security-best-practices
description: Security best practices for Nexus including authentication, rate limiting, input validation, and production deployment
priority: HIGH
tags:
  [nexus, security, authentication, rate-limiting, input-validation, production]
---

# Nexus Security Best Practices

Nexus includes production-safe defaults: environment-aware auth, rate limiting, disabled auto-discovery, unified input validation.

## Authentication

### Environment-Aware (Recommended)

Set the environment to production to auto-enable authentication:

```bash
export NEXUS_ENV=production
```

```
app = Nexus()  # Auth auto-enabled when NEXUS_ENV=production
```

- `NEXUS_ENV=production` -- auth auto-enabled
- `NEXUS_ENV=development` -- auth disabled (default)
- Explicitly disabling auth in production logs a CRITICAL WARNING

### Plugin-Based Auth

Authentication is configured via the plugin system:

```
app = Nexus()
app.add_plugin(auth_plugin)
```

Auth plugin capabilities include JWT, RBAC, tenant isolation, and SSO. See [nexus-auth-plugin](nexus-auth-plugin.md) for details. The exact auth plugin classes and configuration vary by SDK -- see language-specific variant.

## Rate Limiting

Nexus provides default rate limiting for DoS protection.

- Default rate limit applies automatically
- Per-endpoint rate limiting available (implementation varies by SDK)
- MUST NOT disable in production unless behind an API gateway with its own rate limiting

## Input Validation (Automatic)

All channels (API, MCP, CLI) are validated automatically:

- Dangerous keys blocked: `__import__`, `eval`, `exec`, `compile`, `globals`, `locals`, `__builtins__`
- Path traversal blocked: `../`, `..\\`
- Size limit: 10MB default

No configuration needed -- applied across all channels automatically.

## Production Checklist

- [ ] `NEXUS_ENV=production` set
- [ ] Authentication enabled (auto or explicit)
- [ ] Rate limiting configured (100+ req/min)
- [ ] Auto-discovery disabled (`auto_discovery=False`)
- [ ] Redis for distributed sessions
- [ ] HTTPS/TLS enabled (direct or reverse proxy)
- [ ] Secrets from environment variables (never hardcoded)
- [ ] Monitoring and alerting configured

## Common Mistakes

| Mistake                                       | Fix                                          |
| --------------------------------------------- | -------------------------------------------- |
| Auth disabled in production                   | Set `NEXUS_ENV=production` (auto-enables)    |
| No rate limiting                              | Use default or set explicit limit            |
| Auto-discovery in production (blocking delay) | `auto_discovery=False` + manual registration |
| Secrets in code                               | Use environment variables for all secrets    |
| No HTTPS                                      | Enable TLS directly or via reverse proxy     |

## Docker Security

```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 nexus
WORKDIR /app
COPY --chown=nexus:nexus . .
ENV NEXUS_ENV=production
USER nexus
EXPOSE 8000 3001
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "app.py"]
```

The Dockerfile above applies to Python deployments. Adapt the base image, build steps, and CMD for other SDKs.

## Kubernetes Security Context

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
  readOnlyRootFilesystem: true
```

## Monitoring

Key security metrics to track:

- Authentication failures (failed logins, invalid tokens)
- Rate limit violations (429 responses per endpoint/IP)
- Input validation blocks (dangerous keys, path traversal, size violations)
- System health (auth service, session backend, database)

See language-specific variant for auth plugin configuration, rate limiting API, CORS setup, and production configuration constructor parameters.
