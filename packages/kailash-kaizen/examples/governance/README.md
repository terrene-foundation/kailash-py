# External Agent Rate Limiting Examples

This directory contains examples demonstrating the External Agent Rate Limiting feature in Kaizen.

## Overview

The External Agent Rate Limiter provides enterprise-grade rate limiting for external agent invocations with:

- **Multi-tier limits**: Per-minute, per-hour, per-day
- **Burst handling**: Configurable burst multiplier for traffic spikes
- **Hierarchical scoping**: User, team, and organization-level quotas
- **Graceful degradation**: Continues when Redis unavailable
- **Performance**: <10ms p95 latency
- **Metrics tracking**: Prometheus-compatible metrics

## Prerequisites

1. **Redis server** running on localhost:6379
2. **Python packages**:
   ```bash
   pip install redis
   ```

## Quick Start

### Start Redis

```bash
redis-server --port 6379
```

### Run Demo

```bash
cd packages/kailash-kaizen
python examples/governance/rate_limiting_demo.py
```

## Example: Basic Rate Limiting

```python
import asyncio
from kaizen.governance import ExternalAgentRateLimiter, RateLimitConfig

async def main():
    # Configure limits
    config = RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
        burst_multiplier=1.5,  # 50% burst allowance
    )

    # Initialize rate limiter
    limiter = ExternalAgentRateLimiter(
        redis_url="redis://localhost:6379/0",
        config=config,
    )
    await limiter.initialize()

    # Check rate limit before invocation
    result = await limiter.check_rate_limit(
        agent_id="agent-001",
        user_id="user-123",
    )

    if result.allowed:
        # Proceed with external agent invocation
        await invoke_external_agent()

        # Record the invocation
        await limiter.record_invocation(
            agent_id="agent-001",
            user_id="user-123",
        )
        print(f"✅ Invocation allowed (remaining: {result.remaining})")
    else:
        # Rate limit exceeded
        print(f"❌ Rate limit exceeded: {result.limit_exceeded}")
        print(f"   Retry after {result.retry_after_seconds} seconds")

    await limiter.close()

asyncio.run(main())
```

## Example: FastAPI Integration

```python
from fastapi import FastAPI, HTTPException, Header
from kaizen.governance import ExternalAgentRateLimiter, RateLimitConfig

app = FastAPI()

# Initialize rate limiter (singleton)
rate_limiter = ExternalAgentRateLimiter(
    redis_url="redis://localhost:6379/0",
    config=RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
    )
)

@app.on_event("startup")
async def startup():
    await rate_limiter.initialize()

@app.on_event("shutdown")
async def shutdown():
    await rate_limiter.close()

@app.post("/api/v1/agents/{agent_id}/invoke")
async def invoke_agent(
    agent_id: str,
    request: dict,
    user_id: str = Header(..., alias="X-User-ID"),
):
    # Check rate limit
    result = await rate_limiter.check_rate_limit(
        agent_id=agent_id,
        user_id=user_id,
    )

    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit_exceeded": result.limit_exceeded,
                "retry_after": result.retry_after_seconds,
                "current_usage": result.current_usage,
            },
            headers={"Retry-After": str(result.retry_after_seconds)},
        )

    # Invoke external agent
    response = await external_agent_api.invoke(agent_id, request)

    # Record invocation
    await rate_limiter.record_invocation(
        agent_id=agent_id,
        user_id=user_id,
    )

    return {
        "response": response,
        "rate_limit": {
            "remaining": result.remaining,
            "current_usage": result.current_usage,
        }
    }
```

## Example: Team-Level Rate Limiting

```python
# Team members share quota
result = await limiter.check_rate_limit(
    agent_id="agent-001",
    user_id="user-123",
    team_id="team-alpha",  # Team-level quota
)

if result.allowed:
    print("Team has quota available")
else:
    print("Team quota exhausted")
```

## Example: Organization-Level Rate Limiting

```python
# Entire organization shares quota
result = await limiter.check_rate_limit(
    agent_id="agent-001",
    user_id="user-123",
    team_id="team-alpha",
    org_id="org-acme",  # Org-level quota (highest priority)
)

if result.allowed:
    print("Organization has quota available")
else:
    print("Organization quota exhausted")
```

## Example: Custom Configuration

```python
config = RateLimitConfig(
    # Base limits
    requests_per_minute=50,
    requests_per_hour=1000,
    requests_per_day=10000,

    # Burst handling
    burst_multiplier=2.0,  # 100% burst (double base limit)
    enable_burst=True,

    # Redis settings
    redis_max_connections=100,
    redis_timeout_seconds=10.0,

    # Error handling
    fail_open_on_error=True,  # Allow requests when Redis fails

    # Monitoring
    enable_metrics=True,
)
```

## Example: Metrics Monitoring

```python
# Get metrics
metrics = limiter.get_metrics()

print(f"Total checks: {metrics.checks_total}")
print(f"Total exceeded: {metrics.exceeded_total}")
print(f"Exceeded by limit:")
for limit_type, count in metrics.exceeded_by_limit.items():
    print(f"  - {limit_type}: {count}")
print(f"Redis errors: {metrics.redis_errors_total}")
print(f"Fail-open count: {metrics.fail_open_total}")

# Calculate average latency
avg_latency = metrics.check_duration_total / metrics.checks_total
print(f"Average check latency: {avg_latency * 1000:.2f}ms")
```

## Configuration Options

### RateLimitConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `requests_per_minute` | int | 60 | Base requests per minute |
| `requests_per_hour` | int | 1000 | Base requests per hour |
| `requests_per_day` | int | 10000 | Base requests per day |
| `burst_multiplier` | float | 1.5 | Burst allowance multiplier |
| `enable_burst` | bool | True | Enable burst handling |
| `redis_max_connections` | int | 50 | Connection pool size |
| `redis_timeout_seconds` | float | 5.0 | Redis operation timeout |
| `fail_open_on_error` | bool | True | Allow requests when Redis fails |
| `enable_metrics` | bool | True | Enable metrics tracking |

### RateLimitCheckResult

| Field | Type | Description |
|-------|------|-------------|
| `allowed` | bool | Whether request is allowed |
| `limit_exceeded` | str \| None | Which limit was exceeded ("per_minute", "per_hour", "per_day") |
| `remaining` | int | Requests remaining in most restrictive window |
| `reset_time` | datetime \| None | When most restrictive window resets |
| `retry_after_seconds` | int \| None | Seconds to wait before retrying |
| `current_usage` | dict[str, int] | Usage across all windows |

## Best Practices

### 1. Connection Pooling

```python
# Good: Reuse single instance
rate_limiter = ExternalAgentRateLimiter(...)
await rate_limiter.initialize()

# Use across multiple requests
for request in requests:
    result = await rate_limiter.check_rate_limit(...)

# Bad: Creating new instance per request (inefficient)
for request in requests:
    limiter = ExternalAgentRateLimiter(...)  # ❌ Don't do this
    await limiter.initialize()
```

### 2. Error Handling

```python
from kaizen.governance import RateLimitError

try:
    result = await limiter.check_rate_limit(...)
except RateLimitError as e:
    # Handle rate limiter errors
    logger.error(f"Rate limit check failed: {e}")
    # Fail-open or fail-closed based on config
```

### 3. Graceful Shutdown

```python
# FastAPI
@app.on_event("shutdown")
async def shutdown():
    await rate_limiter.close()

# General async app
try:
    # Application logic
    pass
finally:
    await rate_limiter.close()
```

### 4. Monitoring

```python
# Periodic metrics reporting
async def report_metrics():
    while True:
        await asyncio.sleep(60)  # Every minute
        metrics = rate_limiter.get_metrics()
        logger.info(f"Rate limiter metrics: {metrics}")
```

## Testing

See comprehensive test suite:
- **Unit tests**: `tests/unit/governance/test_rate_limiter.py` (20 tests)
- **Integration tests**: `tests/integration/governance/test_rate_limiter_integration.py` (6 tests)
- **E2E tests**: `tests/e2e/governance/test_rate_limiter_e2e.py` (5 tests)

## Performance

Benchmarks with Redis on localhost:

| Scenario | Latency (p95) | Target |
|----------|---------------|--------|
| Single check | <5ms | <10ms ✅ |
| 100 concurrent checks | <50ms | <100ms ✅ |
| 1000 concurrent checks | <100ms | <200ms ✅ |

## Troubleshooting

### Redis Connection Failed

```python
# Error: Connection refused
# Solution: Start Redis server
redis-server --port 6379
```

### Burst Limit Not Working

```python
# Check burst multiplier
config = RateLimitConfig(
    requests_per_minute=10,
    burst_multiplier=1.5,  # Effective limit: 10 * 1.5 = 15
    enable_burst=True,     # ← Must be True
)
```

### Rate Limit Always Allowed

```python
# Check fail-open configuration
config = RateLimitConfig(
    fail_open_on_error=True,  # ← Allows requests when Redis fails
)

# If Redis is down, all requests are allowed
# Check Redis connection: await limiter.initialize()
```

## Related Documentation

- **Implementation Summary**: `RATE_LIMITING_IMPLEMENTATION_SUMMARY.md`
- **API Reference**: `src/kaizen/governance/rate_limiter.py` (inline docs)
- **TODO Specification**: `todos/active/TODO-EXTINT-002-rate-limiting.md`
