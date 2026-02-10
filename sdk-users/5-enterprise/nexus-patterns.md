# Enterprise Nexus Patterns

_Advanced multi-channel orchestration for enterprise deployments_

## Overview

Enterprise Nexus patterns provide production-ready multi-channel orchestration with enterprise-grade security, monitoring, and compliance features. Unlike basic gateway patterns that focus on single-channel API access, Nexus orchestrates entire application ecosystems across API, CLI, and MCP interfaces.

## Enterprise Nexus Architecture

### Core Enterprise Features

- **Unified Authentication**: SSO/JWKS integration across all channels via NexusAuthPlugin
- **Cross-Channel Authorization**: RBAC enforcement on API, CLI, and MCP
- **Multi-Tenant Isolation**: Complete tenant separation via TenantConfig
- **Audit Logging**: Comprehensive audit trail with configurable backends
- **Rate Limiting**: Per-route and global rate limiting with Redis support
- **High Availability**: Load balancing and failover across channel types

### Production Deployment Pattern

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig

# Enterprise-grade multi-channel platform with NexusAuthPlugin (v1.3.0)
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],
        algorithm="RS256",
        jwks_url="https://sso.company.com/.well-known/jwks.json",  # SSO integration
    ),
    rbac={
        "admin": ["*"],
        "developer": ["read:*", "write:*", "execute:*"],
        "operator": ["read:*", "execute:monitoring"],
        "executive": ["read:dashboards", "read:reports"],
    },
    rate_limit=RateLimitConfig(requests_per_minute=1000),
    tenant_isolation=TenantConfig(
        jwt_claim="tenant_id",
        admin_role="admin",
    ),
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
        exclude_paths=["/health", "/metrics"],
    ),
)

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_monitoring=True,
)
app.add_plugin(auth)

# Start the platform
app.start()
```

## Enterprise Security Patterns

### SSO Authentication Across Channels

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig

# MFA is handled at the SSO/IdP level (Auth0, Okta, etc.)
# Nexus validates the JWT issued after MFA completion via JWKS
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(
        algorithm="RS256",
        jwks_url="https://sso.company.com/.well-known/jwks.json",  # SSO with MFA
        jwks_cache_ttl=3600,
        issuer="https://sso.company.com",
        audience="nexus-platform",
    ),
)

app = Nexus()
app.add_plugin(auth)

# Authentication flow across channels:
# 1. User authenticates via SSO provider (which enforces MFA)
# 2. SSO provider issues JWT after successful authentication
# 3. JWT is valid across all Nexus channels (API/CLI/MCP)
# 4. Sensitive operations can require re-authentication via SSO

app.start()
```

### Role-Based Access Control (RBAC)

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user
from fastapi import Depends

# Define enterprise roles with wildcard permissions
auth = NexusAuthPlugin.saas_app(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={
        # Executive: read-only dashboards and reports
        "executive": ["read:dashboards", "read:reports", "read:status"],
        # Developer: full workflow and tool access
        "developer": ["read:*", "write:*", "execute:*"],
        # Operator: monitoring and deployment
        "operator": ["read:health", "execute:monitoring", "execute:deploy"],
        # Admin: unrestricted access
        "admin": ["*"],
    },
)

app = Nexus()
app.add_plugin(auth)

# Permission matching supports wildcards:
#   "*"           matches everything
#   "read:*"      matches read:users, read:articles, etc.
#   "*:users"     matches read:users, write:users, etc.

# Use FastAPI dependencies for fine-grained control on custom routes
# @custom_router.get("/admin")
# async def admin_only(user=Depends(RequireRole("admin"))):
#     return {"admin": True}

# @custom_router.delete("/articles/{id}")
# async def delete_article(user=Depends(RequirePermission("delete:articles"))):
#     return {"deleted": True}

app.start()
```

### ABAC via Custom Middleware

For attribute-based access control (ABAC) beyond RBAC, use custom middleware with Nexus's native middleware API:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from datetime import datetime

class ABACMiddleware(BaseHTTPMiddleware):
    """Custom ABAC middleware for policy-based access control."""

    async def dispatch(self, request: Request, call_next):
        # Example: Business hours policy for sensitive endpoints
        current_hour = datetime.now().hour
        if request.url.path.startswith("/api/sensitive"):
            if not (9 <= current_hour <= 17):
                return JSONResponse(
                    {"error": "Access restricted to business hours"},
                    status_code=403,
                )

        return await call_next(request)

# Setup with NexusAuthPlugin + custom ABAC middleware
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
)

app = Nexus()
app.add_plugin(auth)
app.add_middleware(ABACMiddleware)  # Native Nexus middleware API

app.start()
```

## Multi-Tenant Enterprise Patterns

### Tenant Isolation Configuration

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig
from nexus.auth.tenant.config import TenantConfig

# Tenant isolation via NexusAuthPlugin
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={
        "admin": ["*"],
        "tenant_admin": ["read:*", "write:*"],
        "tenant_user": ["read:*"],
    },
    tenant_isolation=TenantConfig(
        tenant_id_header="X-Tenant-ID",
        jwt_claim="tenant_id",             # Claim name in JWT
        allow_admin_override=True,
        admin_role="admin",                # Singular string, NOT admin_roles
        exclude_paths=["/health", "/docs"],
    ),
    rate_limit=RateLimitConfig(
        requests_per_minute=10000,
        route_limits={
            "/api/workflows/*": {"requests_per_minute": 1000},
        },
    ),
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
    ),
)

app = Nexus()
app.add_plugin(auth)

# Tenant ID is extracted from JWT claims or X-Tenant-ID header
# Each request is automatically scoped to its tenant
# Admin roles can override tenant isolation when needed

app.start()
```

### Tenant-Aware Workflows

```python
import os
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Handler pattern for tenant-aware processing
@app.handler("tenant_data_processing", description="Process data with tenant context")
async def process_tenant_data(tenant_id: str, customer_id: str, compliance_level: str = "standard") -> dict:
    """Process data with tenant-specific logic.

    The tenant_id is validated by TenantConfig middleware before reaching this handler.
    """
    if compliance_level == "hipaa":
        # Apply HIPAA-specific processing
        return {"tenant_id": tenant_id, "customer_id": customer_id, "processing": "hipaa"}
    elif compliance_level == "gdpr":
        # Apply GDPR-specific processing
        return {"tenant_id": tenant_id, "customer_id": customer_id, "processing": "gdpr"}
    else:
        return {"tenant_id": tenant_id, "customer_id": customer_id, "processing": "standard"}

# Alternatively, register a workflow with .build()
tenant_workflow = WorkflowBuilder()
tenant_workflow.add_node("PythonCodeNode", "process_tenant_data", {
    "code": """
try:
    tenant_id = tenant_id
except NameError:
    tenant_id = "unknown"
try:
    compliance_level = compliance_level
except NameError:
    compliance_level = "standard"

result = {"tenant_id": tenant_id, "compliance_level": compliance_level}
"""
})
app.register("tenant_workflow", tenant_workflow.build())  # ALWAYS .build()

app.start()
```

## Enterprise Monitoring & Observability

### Monitoring with Nexus

Nexus provides built-in monitoring via the `enable_monitoring` flag. For comprehensive observability, combine Nexus monitoring with external tools deployed alongside your application:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, AuditConfig

# Enable monitoring and audit logging
auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
)

app = Nexus(
    enable_monitoring=True,  # Built-in Nexus monitoring
)
app.add_plugin(auth)

# Register health-check handler
@app.handler("system_status", description="Get system status")
async def system_status() -> dict:
    """Return system health information."""
    health = app.health_check()
    return {"status": "healthy", "health": health}

app.start()

# For production observability, deploy alongside:
# - Prometheus: Scrape /metrics endpoint
# - Grafana: Dashboard visualization
# - Elasticsearch + Kibana: Log aggregation
# - Jaeger/Zipkin: Distributed tracing
#
# Configure these as infrastructure (Docker Compose, Kubernetes)
# rather than in application code.
```

### Audit Logging for Compliance

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, AuditConfig

# Audit logging captures all access for compliance
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*"]},
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
        log_request_body=False,              # Disable for PII protection
        log_response_body=False,
        exclude_paths=["/health", "/metrics"],
        redact_headers=["Authorization", "Cookie"],
        redact_fields=["password", "token", "api_key"],
    ),
)

app = Nexus()
app.add_plugin(auth)
app.start()

# Audit log captures:
# - All API requests with user identity
# - Authentication events (login, logout, failures)
# - Authorization decisions (permit/deny)
# - Tenant context for multi-tenant deployments
```

## High Availability Patterns

### Load Balancing Configuration

For high availability, deploy multiple Nexus instances behind a load balancer. Each instance is stateless (sessions can be shared via Redis):

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, RateLimitConfig

# Each Nexus instance is identical and stateless
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "operator": ["read:*", "execute:*"]},
    rate_limit=RateLimitConfig(
        requests_per_minute=1000,
        backend="redis",                    # Shared state across instances
        redis_url=os.environ["REDIS_URL"],
    ),
)

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_monitoring=True,
)
app.add_plugin(auth)
app.start()

# Deploy behind load balancer (nginx, HAProxy, K8s Ingress):
# - API channel: Round-robin across instances
# - Health check: GET /health on each instance
# - Session affinity: Not required (stateless JWT auth)
# - Rate limiting: Shared via Redis backend
```

### Health Check Integration

```python
from nexus import Nexus

app = Nexus()

# Built-in health check
@app.handler("deep_health", description="Deep health check")
async def deep_health() -> dict:
    """Comprehensive health check for load balancer integration."""
    health = app.health_check()
    return {
        "status": "healthy" if health else "unhealthy",
        "channels": {
            "api": "running",
            "cli": "available",
            "mcp": "running",
        },
    }

# The /health endpoint is automatically available
# Load balancers should probe: GET /health
app.start()
```

## Compliance & Governance

### GDPR Compliance Pattern

Implement GDPR compliance using Nexus audit logging and handler patterns:

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, AuditConfig

# GDPR requires audit trails for all data access
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "dpo": ["read:*", "delete:*"], "user": ["read:own"]},
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
        redact_fields=["password", "ssn", "credit_card"],  # PII protection
    ),
)

app = Nexus()
app.add_plugin(auth)

# Right to be forgotten (GDPR Article 17)
@app.handler("gdpr_delete_user_data", description="Delete all user data (GDPR Art. 17)")
async def gdpr_delete_user_data(user_id: str) -> dict:
    """Delete all personal data for a user. Requires 'delete:*' permission."""
    # Implementation would use DataFlow to delete across all tables
    return {"user_id": user_id, "status": "deleted", "gdpr_article": "17"}

# Data portability (GDPR Article 20)
@app.handler("gdpr_export_user_data", description="Export user data (GDPR Art. 20)")
async def gdpr_export_user_data(user_id: str, format: str = "json") -> dict:
    """Export all personal data for a user."""
    return {"user_id": user_id, "format": format, "status": "exported"}

app.start()
```

### HIPAA Compliance Pattern

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, AuditConfig

# HIPAA requires strict access controls and audit logging
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],
        verify_exp=True,  # Token expiration required
    ),
    rbac={
        "admin": ["*"],
        "physician": ["read:phi", "write:phi"],
        "nurse": ["read:phi"],
        "billing": ["read:billing"],
    },
    tenant_isolation=TenantConfig(
        jwt_claim="organization_id",
        admin_role="admin",
    ),
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
        log_request_body=False,      # Never log PHI
        log_response_body=False,     # Never log PHI
        redact_fields=["ssn", "dob", "diagnosis", "medication"],
    ),
)

app = Nexus()
app.add_plugin(auth)

# PHI access is controlled by RBAC + tenant isolation
# All access is audit-logged for HIPAA compliance
# Use RequirePermission("read:phi") on PHI endpoints

app.start()
```

## Performance Optimization

### Rate Limiting Strategy

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, RateLimitConfig

# Per-route rate limiting for different traffic patterns
auth = NexusAuthPlugin.enterprise(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    rbac={"admin": ["*"], "user": ["read:*", "execute:*"]},
    rate_limit=RateLimitConfig(
        requests_per_minute=100,         # Global default
        burst_size=20,                   # Allow burst traffic
        backend="redis",                 # Shared across instances
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
        route_limits={
            "/api/chat/*": {"requests_per_minute": 30},           # LLM endpoints
            "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},  # Login
            "/health": None,                                       # No limit
        },
        include_headers=True,            # X-RateLimit-* response headers
        fail_open=True,                  # Allow when Redis is down
    ),
)

app = Nexus()
app.add_plugin(auth)
app.start()
```

### Kubernetes Auto-Scaling

For auto-scaling, configure Kubernetes HPA (Horizontal Pod Autoscaler) targeting Nexus metrics:

```yaml
# kubernetes/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nexus-platform
  namespace: nexus
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nexus-platform
  minReplicas: 3
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
```

## Quick Enterprise Setup Checklist

### Essential Enterprise Components

- [ ] **Multi-Channel Configuration**: API, CLI, MCP channels enabled
- [ ] **Enterprise Authentication**: SSO/JWKS integration via NexusAuthPlugin
- [ ] **Authorization**: RBAC roles defined for all user types
- [ ] **Multi-Tenancy**: TenantConfig with JWT claim-based isolation
- [ ] **Rate Limiting**: RateLimitConfig with per-route limits and Redis backend
- [ ] **Audit Logging**: AuditConfig with PII redaction
- [ ] **Monitoring**: `enable_monitoring=True` with external Prometheus/Grafana
- [ ] **Compliance**: GDPR/HIPAA patterns with appropriate audit and redaction
- [ ] **High Availability**: Multiple instances behind load balancer
- [ ] **Secrets Management**: All secrets via environment variables (never hardcoded)

### Production Deployment Steps

1. **Infrastructure Setup**: Deploy Kubernetes cluster with monitoring
2. **Security Configuration**: Configure SSO provider, generate JWT secrets
3. **NexusAuthPlugin Setup**: Use `NexusAuthPlugin.enterprise()` factory method
4. **Tenant Configuration**: Configure TenantConfig with JWT claims
5. **Rate Limiting**: Configure RateLimitConfig with Redis backend
6. **Monitoring Deployment**: Deploy Prometheus, Grafana, Elasticsearch
7. **Audit Configuration**: Enable AuditConfig with PII redaction
8. **Testing**: Comprehensive security and performance testing

## Related Enterprise Patterns

- **[Security Patterns](security-patterns.md)** - Advanced authentication and authorization
- **[Compliance Patterns](compliance-patterns.md)** - Regulatory compliance frameworks
- **[Production Patterns](production-patterns.md)** - Production deployment strategies
- **[Monitoring Patterns](../monitoring/enterprise-monitoring.md)** - Comprehensive observability
- **[Gateway Patterns](gateway-patterns.md)** - Single-channel API gateway patterns

---

**Ready for enterprise multi-channel deployment?** Nexus provides unified orchestration across API, CLI, and MCP with enterprise-grade security, compliance, and monitoring. Start with `Nexus()` and `NexusAuthPlugin.enterprise()` for full enterprise features.
