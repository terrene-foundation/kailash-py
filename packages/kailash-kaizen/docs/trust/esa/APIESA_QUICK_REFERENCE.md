# APIESA Quick Reference

## Import

```python
from kaizen.trust.esa import APIESA, ESAResult, RateLimitConfig
```

## Basic Setup

```python
# Minimal setup
esa = APIESA(
    system_id="api-001",
    base_url="https://api.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
)

# With authentication
esa = APIESA(
    system_id="api-001",
    base_url="https://api.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    auth_headers={"Authorization": "Bearer TOKEN"},
)

# With rate limiting
esa = APIESA(
    system_id="api-001",
    base_url="https://api.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    rate_limit_config=RateLimitConfig(
        requests_per_second=10,
        requests_per_minute=100,
    ),
)

# With OpenAPI spec
esa = APIESA(
    system_id="api-001",
    base_url="https://api.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    openapi_spec={"paths": {...}},
)

# Establish trust
await esa.establish_trust(authority_id="org-acme")
```

## HTTP Methods

```python
# GET
result = await esa.get("/users", params={"limit": 10})

# POST
result = await esa.post("/users", data={"name": "Alice"})

# PUT
result = await esa.put("/users/123", data={"name": "Alice Updated"})

# DELETE
result = await esa.delete("/users/123")

# PATCH
result = await esa.patch("/users/123", data={"email": "new@example.com"})

# Generic (any method)
result = await esa.call_endpoint("GET", "/custom", params={}, data=None)
```

## Result Handling

```python
result: ESAResult = await esa.get("/users")

# Check success
if result.success:
    print(f"Status: {result.status_code}")
    print(f"Data: {result.data}")
    print(f"Duration: {result.duration_ms}ms")
else:
    print(f"Error: {result.error}")
    print(f"Status: {result.status_code}")

# Access headers
content_type = result.headers.get("Content-Type")

# Access metadata
print(f"Method: {result.metadata['method']}")
print(f"Path: {result.metadata['path']}")
```

## Agent Integration

```python
# Agent executes through ESA
result = await esa.execute(
    operation="get_users",
    parameters={
        "path": "/users",
        "params": {"limit": 10},
    },
    requesting_agent_id="agent-001",
)

# Result includes audit info
print(f"Audit anchor: {result.audit_anchor_id}")
print(f"Capability used: {result.metadata['capability_used']}")
```

## Rate Limiting

```python
# Check rate limit status
status = esa.get_rate_limit_status()
print(f"Per second: {status['per_second']['current']}/{status['per_second']['limit']}")
print(f"Per minute: {status['per_minute']['current']}/{status['per_minute']['limit']}")
print(f"Per hour: {status['per_hour']['current']}/{status['per_hour']['limit']}")

# Configure limits
config = RateLimitConfig(
    requests_per_second=5,   # Max 5/sec
    requests_per_minute=100, # Max 100/min
    requests_per_hour=1000,  # Max 1000/hour
    burst_size=10,           # Allow bursts up to 10
)
```

## Request Logging

```python
# Get recent requests
log = esa.get_request_log(limit=10)
for entry in log:
    print(f"{entry['timestamp']} - {entry['method']} {entry['path']}")
    print(f"  Status: {entry['status_code']}, Duration: {entry['duration_ms']}ms")

# Get statistics
stats = esa.get_request_statistics()
print(f"Total: {stats['total_requests']}")
print(f"Success rate: {stats['success_rate']:.1%}")
print(f"Avg duration: {stats['average_duration_ms']}ms")
print(f"Methods: {stats['methods']}")
print(f"Status codes: {stats['status_codes']}")

# Filtered log
log = esa.get_request_log(
    limit=50,
    start_time=datetime.utcnow() - timedelta(hours=1),
    end_time=datetime.utcnow(),
)
```

## Capabilities

```python
# List capabilities
print(esa.capabilities)
# Output: ['get_users', 'post_users', 'get_users_id', ...]

# Get capability metadata
meta = esa.get_capability_metadata("get_users")
if meta:
    print(f"Description: {meta.description}")
    print(f"Type: {meta.capability_type.value}")
    print(f"Parameters: {meta.parameters}")

# Refresh capabilities (if API changed)
capabilities = await esa.refresh_capabilities()
```

## Delegation

```python
# Delegate capability to another agent
delegation_id = await esa.delegate_capability(
    capability="get_users",
    delegatee_id="agent-002",
    task_id="task-001",
    additional_constraints=["read_only", "limit:100"],
    expires_at=datetime.utcnow() + timedelta(hours=1),
)
```

## Error Handling

```python
from kaizen.trust.esa.exceptions import (
    ESAOperationError,
    ESAConnectionError,
    ESANotEstablishedError,
)

try:
    result = await esa.get("/users")
except ESAOperationError as e:
    print(f"Operation failed: {e.operation}")
    print(f"Reason: {e.reason}")
    print(f"System: {e.system_id}")
except ESAConnectionError as e:
    print(f"Connection failed: {e.endpoint}")
except ESANotEstablishedError as e:
    print(f"Trust not established for: {e.system_id}")
```

## Health Check

```python
# Check ESA health
health = await esa.health_check()

print(f"Healthy: {health['healthy']}")
print(f"Established: {health['established']}")

# Check individual components
for check_name, check_result in health['checks'].items():
    print(f"{check_name}: {check_result['status']}")

# View statistics
stats = health['statistics']
print(f"Operations: {stats['operation_count']}")
print(f"Success rate: {stats['success_rate']}")
```

## Connection Validation

```python
# Validate connection to API
is_valid = await esa.validate_connection()
if is_valid:
    print("✓ Connection valid")
else:
    print("✗ Connection failed")
```

## Cleanup

```python
# Always cleanup when done
await esa.cleanup()

# Or use async context manager pattern
async with httpx.AsyncClient() as client:
    # Use client
    pass
```

## OpenAPI Capability Mapping

```python
# OpenAPI paths -> Capabilities
"/users"           → "get_users", "post_users"
"/users/{id}"      → "get_users_id", "put_users_id", "delete_users_id"
"/api/v1/posts"    → "get_api_v1_posts", "post_api_v1_posts"
"/user-profiles"   → "get_user_profiles", "post_user_profiles"
```

## Common Patterns

### Pattern 1: Simple GET Request
```python
result = await esa.get("/users", params={"limit": 10})
if result.success:
    users = result.data  # Parsed JSON
```

### Pattern 2: Create Resource
```python
result = await esa.post("/users", data={
    "name": "Alice",
    "email": "alice@example.com"
})
if result.success:
    user_id = result.data["id"]
```

### Pattern 3: Update Resource
```python
result = await esa.put(f"/users/{user_id}", data={
    "name": "Alice Updated"
})
```

### Pattern 4: Delete Resource
```python
result = await esa.delete(f"/users/{user_id}")
```

### Pattern 5: Paginated Requests
```python
page = 1
while True:
    result = await esa.get("/users", params={
        "page": page,
        "limit": 100
    })

    if not result.success or not result.data:
        break

    process_users(result.data)
    page += 1
```

### Pattern 6: With Custom Headers
```python
result = await esa.get("/users", headers={
    "X-Custom-Header": "value",
    "Accept-Language": "en-US"
})
```

### Pattern 7: Error Handling
```python
try:
    result = await esa.get("/users")
    if result.success:
        return result.data
    else:
        logger.error(f"API error: {result.status_code} - {result.error}")
        return None
except ESAOperationError as e:
    logger.error(f"Operation failed: {e.reason}")
    return None
```

### Pattern 8: Rate Limited Batch
```python
# With rate limiting, requests are automatically throttled
for user_id in user_ids:
    result = await esa.get(f"/users/{user_id}")
    # ESA handles rate limiting internally
```

## Configuration Options

```python
APIESA(
    system_id="api-001",              # Required: Unique system ID
    base_url="https://api.com",       # Required: API base URL
    trust_ops=trust_ops,              # Required: TrustOperations instance
    authority_id="org-acme",          # Required: Authority ID
    openapi_spec=None,                # Optional: OpenAPI spec dict
    auth_headers=None,                # Optional: Auth headers dict
    rate_limit_config=None,           # Optional: RateLimitConfig
    metadata=None,                    # Optional: SystemMetadata
    config=None,                      # Optional: ESAConfig
    timeout_seconds=30,               # Optional: Request timeout
)
```

## Tips

1. **Always establish trust first**: `await esa.establish_trust(authority_id)`
2. **Clean up resources**: `await esa.cleanup()` when done
3. **Check result.success**: Don't assume all requests succeed
4. **Use rate limiting**: Prevents API abuse and quota exhaustion
5. **Monitor statistics**: Track success rates and performance
6. **Handle errors**: Wrap requests in try/except for production
7. **Use OpenAPI spec**: Automatic capability discovery
8. **Delegate carefully**: Only delegate what's necessary

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| "ESA not established" | Call `await esa.establish_trust()` first |
| "Capability not found" | Check `esa.capabilities` for available operations |
| "Rate limit exceeded" | Check `esa.get_rate_limit_status()`, adjust config |
| "Timeout" | Increase `timeout_seconds` parameter |
| "Connection failed" | Check `base_url`, network, and API availability |
| "Invalid auth" | Verify `auth_headers` are correct |

## See Also

- Full documentation: `docs/trust/esa/APIESA.md`
- Examples: `examples/trust/esa_api_example.py`
- Tests: `tests/unit/trust/esa/test_apiesa.py`
