---
skill: nexus-security-best-practices
description: Security best practices for Nexus including authentication, rate limiting, input validation, and production deployment
priority: HIGH
tags:
  [nexus, security, authentication, rate-limiting, input-validation, production]
---

# Nexus Security Best Practices

Nexus v1.1.1+ includes production-safe defaults: environment-aware auth, rate limiting, disabled auto-discovery, unified input validation.

## Authentication

### Environment-Aware (Recommended)

```bash
NEXUS_ENV=production  # Auto-enables auth
```

```python
from nexus import Nexus
app = Nexus()  # Auth auto-enabled when NEXUS_ENV=production
```

- `NEXUS_ENV=production` -- auth auto-enabled
- `NEXUS_ENV=development` -- auth disabled (default)
- Explicit `enable_auth=False` in production -- CRITICAL WARNING logged

### Multi-Environment Config

```python
import os
from nexus import Nexus

env = os.getenv("NEXUS_ENV", "development")
app = Nexus(
    enable_auth=(env == "production"),
    rate_limit=1000 if env == "production" else None,
    auto_discovery=(env != "production"),
)
```

## Rate Limiting

Default: 100 req/min (v1.1.1+).

```python
app = Nexus(rate_limit=1000)  # High-traffic API

# Per-endpoint limits
@app.endpoint("/api/search", rate_limit=50)      # Expensive operation
async def search(q: str): ...

@app.endpoint("/api/login", rate_limit=10)        # Brute force prevention
async def login(username: str, password: str): ...
```

MUST NOT disable in production unless behind an API gateway with its own rate limiting.

## Input Validation (Automatic)

All channels validated (API, MCP, CLI):

- Dangerous keys blocked: `__import__`, `eval`, `exec`, `compile`, `globals`, `locals`, `__builtins__`
- Path traversal blocked: `../`, `..\\`
- Size limit: 10MB default

```python
# Adjust size limit
app._max_input_size = 50 * 1024 * 1024  # 50MB for file uploads
app._max_input_size = 1 * 1024 * 1024   # 1MB for strict APIs
```

## Production Configuration

```python
import os
from nexus import Nexus

app = Nexus(
    api_port=int(os.getenv("PORT", "8000")),
    enable_auth=True,
    rate_limit=1000,
    auto_discovery=False,
    force_https=True,
    ssl_cert=os.getenv("SSL_CERT_PATH"),
    ssl_key=os.getenv("SSL_KEY_PATH"),
    session_backend="redis",
    redis_url=os.getenv("REDIS_URL"),
    session_timeout=3600,
    enable_monitoring=True,
    log_level="INFO",
    log_format="json",
    max_concurrent_workflows=200,
    request_timeout=60,
)
```

### Production Checklist

- [ ] `NEXUS_ENV=production`
- [ ] Authentication enabled
- [ ] Rate limiting configured (>=100 req/min)
- [ ] Auto-discovery disabled
- [ ] Redis for sessions
- [ ] HTTPS/TLS enabled
- [ ] Secrets from env vars (never hardcoded)
- [ ] Monitoring and alerting configured

### Docker

```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 nexus
WORKDIR /app
COPY --chown=nexus:nexus requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=nexus:nexus . .
ENV NEXUS_ENV=production
USER nexus
EXPOSE 8000 3001
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "app.py"]
```

### Kubernetes Security Context

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
  readOnlyRootFilesystem: true
```

## Common Mistakes

| Mistake                                       | Fix                                          |
| --------------------------------------------- | -------------------------------------------- |
| Auth disabled in production                   | Set `NEXUS_ENV=production` (auto-enables)    |
| No rate limiting (`rate_limit=None`)          | Use default 100 or set explicit limit        |
| Auto-discovery in production (5-10s blocking) | `auto_discovery=False` + manual registration |
| Secrets in code                               | Use `os.getenv()` for all secrets            |
| No HTTPS                                      | `force_https=True` or reverse proxy          |

## Monitoring

Key security metrics to track:

- Authentication failures (failed logins, invalid tokens)
- Rate limit violations (429 responses per endpoint/IP)
- Input validation blocks (dangerous keys, path traversal, size violations)
- System health (auth service, Redis, database)

```python
from prometheus_client import Counter
auth_failures = Counter('nexus_auth_failures_total', 'Authentication failures')
rate_limit_hits = Counter('nexus_rate_limit_hits_total', 'Rate limit violations')
input_validation_blocks = Counter('nexus_input_blocked_total', 'Blocked inputs')
```
