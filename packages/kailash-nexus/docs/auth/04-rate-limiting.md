# Rate Limiting

Request rate limiting with in-memory and Redis backends, per-route configuration, and standardized response headers.

## Quick Start

```python
from nexus import Nexus
from nexus.auth import NexusAuthPlugin, JWTConfig, RateLimitConfig

app = Nexus()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    rate_limit=RateLimitConfig(
        requests_per_minute=100,
        burst_size=20,
    ),
)

app.add_plugin(auth)
```

## RateLimitConfig Reference

```python
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

@dataclass
class RateLimitConfig:
    # Base limits
    requests_per_minute: int = 100    # Sustained rate limit
    burst_size: int = 20              # Additional burst allowance

    # Backend configuration
    backend: Literal["memory", "redis"] = "memory"
    redis_url: Optional[str] = None
    redis_key_prefix: str = "nexus:rl:"
    redis_connection_pool_size: int = 50
    redis_timeout_seconds: float = 5.0

    # Per-route overrides (path pattern -> config or None to disable)
    route_limits: Dict[str, Optional[Dict[str, int]]] = field(default_factory=dict)

    # Response behavior
    include_headers: bool = True      # Add X-RateLimit-* headers

    # Failure behavior
    fail_open: bool = True            # Allow requests when backend fails
```

Note: `RateLimitConfig` does not have an `exclude_paths` parameter. Use `route_limits` with `None` values to disable rate limiting for specific paths.

## Backend Options

### In-Memory Backend (Default)

Best for single-instance deployments:

```python
config = RateLimitConfig(
    backend="memory",
    requests_per_minute=100,
    burst_size=20,
)
```

Features:

- No external dependencies
- Fast (in-process)
- Per-instance limits (not shared)
- Automatic cleanup

### Redis Backend

Best for distributed deployments:

```python
config = RateLimitConfig(
    backend="redis",
    redis_url="redis://localhost:6379/0",
    redis_key_prefix="myapp:rl:",
    redis_connection_pool_size=50,
    redis_timeout_seconds=5.0,
    requests_per_minute=100,
    burst_size=20,
    fail_open=True,  # Allow requests if Redis is down
)
```

Features:

- Shared limits across instances
- Persistent across restarts
- Atomic operations (no race conditions)
- Connection pooling

## Identifier Extraction

The middleware identifies requesters in this priority:

1. **User ID** from auth middleware (`request.state.user_id`)
2. **API Key** from `X-API-Key` header (truncated for privacy)
3. **IP Address** from client connection

```python
# Example identifiers:
# "user:user-123"        <- Authenticated user
# "apikey:abc12345"      <- API key (first 8 chars)
# "ip:192.168.1.1"       <- Anonymous IP
```

### Custom Identifier Extractor

```python
from fastapi import Request
from nexus.auth.rate_limit import RateLimitMiddleware

def custom_extractor(request: Request) -> str:
    """Custom identifier based on API key tier."""
    api_key = request.headers.get("X-API-Key", "")

    # Premium keys get their own bucket
    if api_key.startswith("premium_"):
        return f"premium:{api_key}"

    # Standard keys share a bucket
    if api_key:
        return f"standard:{api_key[:8]}"

    # Anonymous by IP
    return f"ip:{request.client.host}"

app.add_middleware(
    RateLimitMiddleware,
    config=config,
    identifier_extractor=custom_extractor,
)
```

## Per-Route Limits

Configure different limits for specific routes:

```python
config = RateLimitConfig(
    requests_per_minute=100,  # Default limit
    route_limits={
        # Stricter limit for expensive operations
        "/api/chat/*": {"requests_per_minute": 30},
        "/api/search": {"requests_per_minute": 50},

        # Very strict for auth endpoints (prevent brute force)
        "/api/auth/login": {"requests_per_minute": 10, "burst_size": 5},
        "/api/auth/register": {"requests_per_minute": 5},

        # No rate limit for these paths
        "/health": None,
        "/metrics": None,
        "/docs": None,
    },
)
```

### Pattern Matching

Route patterns use `fnmatch` for matching:

| Pattern          | Matches                                |
| ---------------- | -------------------------------------- |
| `/api/chat/*`    | `/api/chat/send`, `/api/chat/history`  |
| `/users/*/posts` | `/users/123/posts`, `/users/abc/posts` |
| `*`              | Everything                             |

## Response Headers

When `include_headers=True` (default), responses include:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1699123456
```

| Header                  | Description                          |
| ----------------------- | ------------------------------------ |
| `X-RateLimit-Limit`     | Maximum requests per window          |
| `X-RateLimit-Remaining` | Requests remaining in current window |
| `X-RateLimit-Reset`     | Unix timestamp when window resets    |

### Disable Headers

```python
config = RateLimitConfig(
    include_headers=False,  # Don't expose rate limit info
)
```

## Rate Limit Exceeded Response

When the limit is exceeded:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1699123456
Content-Type: application/json

{
  "detail": "Rate limit exceeded. Retry after 45 seconds.",
  "retry_after": 45
}
```

## Fail-Open Behavior

When the backend is unavailable:

```python
# Fail-open (default): Allow requests, log warning
config = RateLimitConfig(
    fail_open=True,  # Continue even if Redis is down
)

# Fail-closed: Block requests if rate limiting unavailable
config = RateLimitConfig(
    fail_open=False,  # Return 503 if backend unavailable
)
```

## Token Bucket Algorithm

The rate limiter uses a token bucket algorithm:

- **Bucket capacity**: `requests_per_minute + burst_size`
- **Refill rate**: `requests_per_minute / 60` tokens per second
- **Request cost**: 1 token per request

Example with `requests_per_minute=60, burst_size=20`:

- Capacity: 80 tokens
- Refill: 1 token/second
- Can burst up to 80 requests instantly
- Sustained rate of 60 requests/minute

## Per-Endpoint Decorator

For fine-grained control on specific endpoints:

```python
from nexus.auth.rate_limit import rate_limit

@app.post("/api/expensive-operation")
@rate_limit(requests_per_minute=10)
async def expensive_operation():
    """This endpoint has its own rate limit."""
    return {"result": "computed"}

@app.post("/api/chat")
@rate_limit(requests_per_minute=30, burst_size=5)
async def chat():
    """Chat with custom burst."""
    return {"response": "Hello!"}
```

## Complete Example

```python
from fastapi import FastAPI
from nexus.auth import (
    NexusAuthPlugin,
    JWTConfig,
    RateLimitConfig,
)

app = FastAPI()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # min 32 chars
    rate_limit=RateLimitConfig(
        # Base configuration
        requests_per_minute=100,
        burst_size=20,

        # Production: Use Redis for shared limits
        backend="redis",
        redis_url="redis://localhost:6379/0",
        redis_key_prefix="myapp:ratelimit:",

        # Route-specific limits
        route_limits={
            # AI endpoints are expensive
            "/api/ai/*": {"requests_per_minute": 20},
            "/api/chat/*": {"requests_per_minute": 30},

            # Auth endpoints need brute-force protection
            "/api/auth/login": {"requests_per_minute": 10},
            "/api/auth/forgot-password": {"requests_per_minute": 5},

            # Disable for system endpoints
            "/health": None,
            "/metrics": None,
            "/docs": None,
            "/openapi.json": None,
        },

        # Response configuration
        include_headers=True,

        # Resilience
        fail_open=True,  # Don't break the app if Redis is down
    ),
)
auth.install(app)

@app.get("/health")
async def health():
    """No rate limit."""
    return {"status": "ok"}

@app.post("/api/chat")
async def chat(message: str):
    """Rate limited to 30 req/min."""
    return {"response": f"Echo: {message}"}

@app.get("/api/data")
async def get_data():
    """Default rate limit (100 req/min)."""
    return {"data": []}
```

## Monitoring

### Logging

The middleware logs rate limit events:

```
WARNING - Rate limit exceeded: identifier=user:123, path=/api/chat, retry_after=45s
```

### Metrics

Track rate limiting in your monitoring:

```python
from prometheus_client import Counter, Histogram

rate_limit_exceeded = Counter(
    'rate_limit_exceeded_total',
    'Rate limit exceeded events',
    ['path', 'identifier_type']
)

# In custom middleware or hook
if response.status_code == 429:
    rate_limit_exceeded.labels(
        path=request.url.path,
        identifier_type=identifier.split(":")[0],
    ).inc()
```

## Best Practices

1. **Use Redis for distributed systems**: Memory backend doesn't share state
2. **Set appropriate burst sizes**: Allow legitimate burst traffic
3. **Protect auth endpoints**: Low limits to prevent brute-force
4. **Protect expensive operations**: AI/ML endpoints need strict limits
5. **Fail-open in production**: Don't break the app if Redis is down
6. **Include response headers**: Helps clients implement backoff
7. **Monitor 429 responses**: High rates indicate misconfigured limits or attacks
8. **Use different limits per tier**: Premium users get higher limits
