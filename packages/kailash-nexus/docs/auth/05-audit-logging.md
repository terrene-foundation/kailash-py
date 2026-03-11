# Audit Logging

Comprehensive request/response logging with multiple backends (logging, DataFlow, custom), PII filtering, and path exclusions.

## Quick Start

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig, AuditConfig

app = Nexus()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    audit=AuditConfig(
        backend="logging",
        log_level="INFO",
    ),
)

app.add_plugin(auth)
```

## AuditConfig Reference

```python
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union

@dataclass
class AuditConfig:
    # Enable/disable audit logging
    enabled: bool = True

    # Backend configuration
    backend: Union[str, Callable] = "logging"  # "logging", "dataflow", or callable
    dataflow_model_name: str = "AuditRecord"   # Model name for DataFlow backend
    log_level: str = "INFO"                    # Log level for logging backend

    # What to log
    log_request_body: bool = False             # Log request bodies (caution: may contain PII)
    log_response_body: bool = False            # Log response bodies
    max_body_log_size: int = 10 * 1024         # Max body size to log (10KB)
    include_query_params: bool = True          # Include query params in metadata
    include_request_headers: bool = False      # Include headers in metadata

    # Exclusions
    exclude_paths: List[str] = field(default_factory=lambda: [
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
    ])
    exclude_methods: List[str] = field(default_factory=lambda: ["OPTIONS"])

    # PII filtering
    redact_headers: List[str] = field(default_factory=lambda: [
        "Authorization",
        "Cookie",
        "Set-Cookie",
        "X-API-Key",
        "X-Auth-Token",
        "X-Session-ID",
    ])
    redact_fields: List[str] = field(default_factory=lambda: [
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "credit_card",
        "card_number",
        "cvv",
        "ssn",
        "social_security",
        "access_token",
        "refresh_token",
    ])
    redact_replacement: str = "[REDACTED]"
```

## Backend Options

### Logging Backend (Default)

Outputs audit records to Python's logging system:

```python
config = AuditConfig(
    backend="logging",
    log_level="INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
)
```

Output format:

```
INFO:nexus.audit:AuditRecord(
    method=GET,
    path=/api/users,
    status_code=200,
    duration_ms=45.23,
    user_id=user-123,
    tenant_id=tenant-456,
    ip_address=192.168.1.1
)
```

### DataFlow Backend

Persists audit records to a database via DataFlow:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

config = AuditConfig(
    backend="dataflow",
    dataflow_model_name="AuditRecord",
)

# Pass DataFlow instance when adding middleware
from nexus.auth.audit import AuditMiddleware

app.add_middleware(
    AuditMiddleware,
    config=config,
    dataflow=db,
)
```

DataFlow model example:

```python
@db.model
class AuditRecord:
    id: str = field(primary_key=True)
    timestamp: datetime
    method: str
    path: str
    status_code: int
    duration_ms: float
    ip_address: str
    user_agent: str
    user_id: Optional[str]
    tenant_id: Optional[str]
    request_body_size: int
    response_body_size: int
    error: Optional[str]
    metadata: Optional[dict]
```

### Custom Backend

For custom storage (external services, queues, etc.):

```python
from nexus.auth.audit.record import AuditRecord

async def custom_store(record: AuditRecord) -> None:
    """Store audit record in external service."""
    await external_service.store({
        "timestamp": record.timestamp.isoformat(),
        "method": record.method,
        "path": record.path,
        "status_code": record.status_code,
        "user_id": record.user_id,
        "tenant_id": record.tenant_id,
        "duration_ms": record.duration_ms,
        "metadata": record.metadata,
    })

config = AuditConfig(
    backend=custom_store,  # Pass the callable directly
)
```

## AuditRecord Structure

Each request generates an `AuditRecord`:

```python
@dataclass
class AuditRecord:
    id: str                           # Unique record ID (UUID)
    timestamp: datetime               # Request start time (UTC)
    method: str                       # HTTP method
    path: str                         # Request path
    status_code: int                  # Response status code
    duration_ms: float                # Request duration in milliseconds
    ip_address: str                   # Client IP address
    user_agent: str                   # User-Agent header
    user_id: Optional[str]            # Authenticated user ID
    tenant_id: Optional[str]          # Tenant ID (if multi-tenant)
    request_body_size: int            # Request body size in bytes
    response_body_size: int           # Response body size in bytes
    error: Optional[str]              # Error message (for 4xx/5xx)
    metadata: Dict[str, Any]          # Additional metadata
```

## PII Filtering

The audit middleware automatically redacts sensitive data.

### Header Redaction

```python
config = AuditConfig(
    include_request_headers=True,
    redact_headers=[
        "Authorization",
        "Cookie",
        "X-API-Key",
        "X-Custom-Secret",  # Add custom headers
    ],
)

# Before redaction:
# {"Authorization": "Bearer eyJhbG...", "X-API-Key": "secret123"}

# After redaction:
# {"Authorization": "[REDACTED]", "X-API-Key": "[REDACTED]"}
```

### Field Redaction (Query Params & Bodies)

```python
config = AuditConfig(
    include_query_params=True,
    log_request_body=True,
    redact_fields=[
        "password",
        "api_key",
        "credit_card",
        "custom_secret",  # Add custom fields
    ],
)

# Query params: /api/login?username=john&password=secret
# After redaction: {"username": "john", "password": "[REDACTED]"}

# Request body: {"email": "john@example.com", "password": "secret123"}
# After redaction: {"email": "john@example.com", "password": "[REDACTED]"}
```

### Custom Replacement String

```python
config = AuditConfig(
    redact_replacement="***FILTERED***",
)
```

## Path and Method Exclusions

### Exclude Paths

```python
config = AuditConfig(
    exclude_paths=[
        "/health",           # Exact match
        "/metrics",
        "/docs",
        "/openapi.json",
        "/internal/*",       # Wildcard (fnmatch pattern)
        "/webhooks/*",
    ],
)
```

### Exclude Methods

```python
config = AuditConfig(
    exclude_methods=["OPTIONS", "HEAD"],  # Don't log these methods
)
```

## Request/Response Body Logging

### Enable Body Logging

```python
config = AuditConfig(
    log_request_body=True,
    log_response_body=True,
    max_body_log_size=10 * 1024,  # 10KB max
)
```

### Security Considerations

Body logging may expose PII. Always:

1. Use `redact_fields` for sensitive field names
2. Limit `max_body_log_size` to prevent log bloat
3. Consider compliance requirements (GDPR, HIPAA)

## Client IP Extraction

The middleware handles proxied requests:

1. **X-Forwarded-For**: Uses first IP in the chain
2. **X-Real-IP**: Alternative proxy header
3. **Client connection**: Direct connection IP

```python
# X-Forwarded-For: 203.0.113.1, 198.51.100.1, 192.0.2.1
# Extracted: 203.0.113.1 (original client)
```

## Error Isolation

Audit failures never break the application:

```python
# If backend fails, error is logged but request continues
try:
    await self._backend.store(record)
except Exception as e:
    logger.error(f"Failed to store audit record: {e}")
    # Request processing continues normally
```

## Complete Example

```python
from fastapi import FastAPI
from nexus.auth import (
    NexusAuthPlugin,
    JWTConfig,
    AuditConfig,
)

app = FastAPI()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    audit=AuditConfig(
        # Backend
        backend="logging",
        log_level="INFO",

        # What to log
        include_query_params=True,
        include_request_headers=True,
        log_request_body=False,  # Security: avoid logging bodies
        log_response_body=False,

        # Exclusions
        exclude_paths=[
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/favicon.ico",
        ],
        exclude_methods=["OPTIONS"],

        # PII protection
        redact_headers=[
            "Authorization",
            "Cookie",
            "Set-Cookie",
            "X-API-Key",
        ],
        redact_fields=[
            "password",
            "secret",
            "token",
            "api_key",
            "credit_card",
            "ssn",
        ],
        redact_replacement="[REDACTED]",
    ),
)
auth.install(app)

@app.get("/health")
async def health():
    """Not audited (excluded path)."""
    return {"status": "ok"}

@app.get("/api/users")
async def list_users():
    """Audited with user/tenant context."""
    return {"users": []}

@app.post("/api/auth/login")
async def login(username: str, password: str):
    """Password will be redacted if body logging enabled."""
    return {"token": "..."}
```

## Integration with Monitoring

### Structured Logging

```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })

# Configure audit logger for JSON output
audit_logger = logging.getLogger("nexus.audit")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
audit_logger.addHandler(handler)
```

### Metrics

```python
from prometheus_client import Counter, Histogram

request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'path', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'path']
)

# Custom backend with metrics
async def metrics_backend(record):
    request_count.labels(
        method=record.method,
        path=record.path,
        status=str(record.status_code),
    ).inc()

    request_duration.labels(
        method=record.method,
        path=record.path,
    ).observe(record.duration_ms / 1000)

    # Also log to stdout
    logging.info(f"Audit: {record.method} {record.path} {record.status_code}")

config = AuditConfig(backend=metrics_backend)
```

## Best Practices

1. **Always enable audit logging**: Essential for security and compliance
2. **Exclude high-frequency endpoints**: Health checks create log noise
3. **Redact all PII**: Configure comprehensive redaction lists
4. **Avoid body logging in production**: Risk of logging sensitive data
5. **Use structured logging**: Enables log aggregation and analysis
6. **Set appropriate log levels**: INFO for production, DEBUG for development
7. **Monitor audit failures**: Alert on `Failed to store audit record` errors
8. **Comply with retention policies**: Configure log rotation and deletion
9. **Include tenant context**: Essential for multi-tenant debugging
10. **Never let audit failures break requests**: Always use error isolation
