# APIESA - REST API Enterprise System Agent

## Overview

APIESA is a specialized Enterprise System Agent (ESA) implementation for REST API integration. It provides trust-aware proxy access to REST APIs with automatic capability discovery, rate limiting, and comprehensive audit logging.

## Key Features

### 1. **OpenAPI Spec Parsing**
- Automatic capability discovery from OpenAPI/Swagger specifications
- Parses paths, HTTP methods, parameters, and responses
- Generates capability metadata with parameter types and descriptions
- Falls back to generic capabilities if no spec provided

### 2. **HTTP Method Support**
- Full support for all major HTTP methods:
  - `GET` - Retrieve resources
  - `POST` - Create resources
  - `PUT` - Update resources
  - `DELETE` - Remove resources
  - `PATCH` - Partially update resources

### 3. **Rate Limiting**
- Configurable rate limits at three levels:
  - Per-second
  - Per-minute
  - Per-hour
- Sliding window algorithm for accurate enforcement
- Automatic request throttling with async sleep
- Rate limit status reporting

### 4. **Request/Response Logging**
- Complete audit trail of all API requests
- Logs method, path, parameters, status code, duration
- Request statistics (success rate, average duration, etc.)
- Configurable log retention (last 1000 requests)

### 5. **Trust Integration**
- Full integration with EATP trust operations
- Trust verification before every request
- Automatic audit logging via TrustOperations
- Capability delegation support

### 6. **Authentication Support**
- Flexible authentication header configuration
- Support for Bearer tokens, API keys, etc.
- Headers automatically merged with request headers

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         APIESA                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │         EnterpriseSystemAgent (Base)                  │ │
│  │  - Trust establishment                                │ │
│  │  - Capability management                              │ │
│  │  - Delegation support                                 │ │
│  └───────────────────────────────────────────────────────┘ │
│                          ▲                                  │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐ │
│  │              APIESA Implementation                     │ │
│  │                                                        │ │
│  │  Capability Discovery:                                │ │
│  │  - OpenAPI spec parsing                               │ │
│  │  - Path -> capability mapping                         │ │
│  │  - Parameter extraction                               │ │
│  │                                                        │ │
│  │  HTTP Operations:                                     │ │
│  │  - GET/POST/PUT/DELETE/PATCH                          │ │
│  │  - call_endpoint() core method                        │ │
│  │  - httpx async client                                 │ │
│  │                                                        │ │
│  │  Rate Limiting:                                       │ │
│  │  - Sliding window algorithm                           │ │
│  │  - Multi-level enforcement                            │ │
│  │  - Automatic throttling                               │ │
│  │                                                        │ │
│  │  Request Logging:                                     │ │
│  │  - Complete audit trail                               │ │
│  │  - Statistics tracking                                │ │
│  │  - Error logging                                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Usage Examples

### Basic Usage

```python
from kaizen.trust.esa import APIESA, RateLimitConfig

# Create APIESA with minimal configuration
esa = APIESA(
    system_id="api-crm-001",
    base_url="https://api.crm.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
)

# Establish trust
await esa.establish_trust(authority_id="org-acme")

# Make requests
result = await esa.get("/users", params={"limit": 10})
print(f"Status: {result.status_code}, Data: {result.data}")
```

### With OpenAPI Spec

```python
openapi_spec = {
    "openapi": "3.0.0",
    "paths": {
        "/users": {
            "get": {"summary": "List users"},
            "post": {"summary": "Create user"}
        },
        "/users/{id}": {
            "get": {"summary": "Get user"},
            "put": {"summary": "Update user"},
            "delete": {"summary": "Delete user"}
        }
    }
}

esa = APIESA(
    system_id="api-crm-001",
    base_url="https://api.crm.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    openapi_spec=openapi_spec,
)

await esa.establish_trust(authority_id="org-acme")

# Capabilities are automatically discovered from spec
print(f"Capabilities: {esa.capabilities}")
# Output: ['get_users', 'post_users', 'get_users_id', 'put_users_id', 'delete_users_id']
```

### With Authentication

```python
esa = APIESA(
    system_id="api-crm-001",
    base_url="https://api.crm.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    auth_headers={
        "Authorization": "Bearer YOUR_API_TOKEN",
        "X-API-Key": "your-api-key"
    },
)

await esa.establish_trust(authority_id="org-acme")

# Auth headers are automatically included in all requests
result = await esa.get("/protected/resource")
```

### With Rate Limiting

```python
from kaizen.trust.esa import RateLimitConfig

esa = APIESA(
    system_id="api-crm-001",
    base_url="https://api.crm.example.com",
    trust_ops=trust_ops,
    authority_id="org-acme",
    rate_limit_config=RateLimitConfig(
        requests_per_second=10,   # Max 10 req/sec
        requests_per_minute=100,  # Max 100 req/min
        requests_per_hour=1000,   # Max 1000 req/hour
    ),
)

await esa.establish_trust(authority_id="org-acme")

# Rate limiting is automatically enforced
for i in range(20):
    result = await esa.get("/users")  # Will be throttled after 10 requests

# Check rate limit status
status = esa.get_rate_limit_status()
print(f"Requests this second: {status['per_second']['current']}/{status['per_second']['limit']}")
```

### Agent Integration (Trust Verification)

```python
# Create agent with capability
await trust_ops.establish(
    agent_id="agent-001",
    authority_id="org-acme",
    capabilities=[
        CapabilityRequest(
            capability="get_users",
            capability_type=CapabilityType.ACTION,
            constraints=["read_only"],
        )
    ],
)

# Agent executes operation through ESA
result = await esa.execute(
    operation="get_users",
    parameters={
        "path": "/users",
        "params": {"limit": 10},
    },
    requesting_agent_id="agent-001",
)

# Trust verification is automatic
print(f"Success: {result.success}")
print(f"Audit anchor: {result.audit_anchor_id}")
```

### Capability Delegation

```python
# Delegate capability to another agent
delegation_id = await esa.delegate_capability(
    capability="get_users",
    delegatee_id="agent-002",
    task_id="task-001",
    additional_constraints=["limit:50"],  # Tighter constraint
    expires_at=datetime.utcnow() + timedelta(hours=1),
)

print(f"Capability delegated: {delegation_id}")
```

### Request Logging & Statistics

```python
# Make several requests
await esa.get("/users")
await esa.post("/users", data={"name": "Alice"})
await esa.put("/users/123", data={"name": "Alice Updated"})
await esa.delete("/users/123")

# Get request log
log = esa.get_request_log(limit=10)
for entry in log:
    print(f"{entry['timestamp']} - {entry['method']} {entry['path']} - {entry['status_code']}")

# Get statistics
stats = esa.get_request_statistics()
print(f"Total requests: {stats['total_requests']}")
print(f"Success rate: {stats['success_rate']:.1%}")
print(f"Average duration: {stats['average_duration_ms']}ms")
print(f"Methods: {stats['methods']}")
```

## API Reference

### Class: `APIESA`

#### Constructor

```python
APIESA(
    system_id: str,
    base_url: str,
    trust_ops: TrustOperations,
    authority_id: str,
    openapi_spec: Optional[Dict[str, Any]] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    rate_limit_config: Optional[RateLimitConfig] = None,
    metadata: Optional[SystemMetadata] = None,
    config: Optional[ESAConfig] = None,
    timeout_seconds: int = 30,
)
```

**Parameters:**
- `system_id`: Unique identifier for the API system
- `base_url`: Base URL for the API (e.g., "https://api.example.com")
- `trust_ops`: TrustOperations instance for trust management
- `authority_id`: Authority ID for trust establishment
- `openapi_spec`: Optional OpenAPI/Swagger spec for capability discovery
- `auth_headers`: Optional authentication headers
- `rate_limit_config`: Optional rate limiting configuration
- `metadata`: System metadata (optional)
- `config`: ESA configuration (optional)
- `timeout_seconds`: Request timeout in seconds (default: 30)

#### Methods

##### HTTP Methods

```python
async def get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Execute GET request.

```python
async def post(
    path: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Execute POST request.

```python
async def put(
    path: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Execute PUT request.

```python
async def delete(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Execute DELETE request.

```python
async def patch(
    path: str,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Execute PATCH request.

##### Core Method

```python
async def call_endpoint(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
) -> ESAResult
```
Core method for making HTTP requests with rate limiting and logging.

##### Rate Limiting

```python
def get_rate_limit_status() -> Dict[str, Any]
```
Get current rate limit status.

**Returns:**
```python
{
    "per_second": {"current": 5, "limit": 10},
    "per_minute": {"current": 45, "limit": 100},
    "per_hour": {"current": 432, "limit": 1000}
}
```

##### Request Logging

```python
def get_request_log(
    limit: int = 100,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]
```
Get request log entries.

```python
def get_request_statistics() -> Dict[str, Any]
```
Get request statistics.

**Returns:**
```python
{
    "total_requests": 150,
    "successful_requests": 145,
    "failed_requests": 5,
    "success_rate": 0.967,
    "average_duration_ms": 125,
    "methods": {"GET": 100, "POST": 30, "PUT": 15, "DELETE": 5},
    "status_codes": {"200": 130, "201": 15, "500": 5}
}
```

##### Cleanup

```python
async def cleanup() -> None
```
Clean up resources (closes HTTP client).

### Class: `ESAResult`

Result from an API operation.

**Attributes:**
- `success`: `bool` - Whether the operation succeeded
- `status_code`: `int` - HTTP status code
- `data`: `Optional[Any]` - Response data (parsed JSON or raw text)
- `headers`: `Optional[Dict[str, str]]` - Response headers
- `error`: `Optional[str]` - Error message if failed
- `duration_ms`: `Optional[int]` - Request duration in milliseconds
- `metadata`: `Dict[str, Any]` - Additional metadata

### Class: `RateLimitConfig`

Configuration for rate limiting.

**Attributes:**
- `requests_per_second`: `Optional[int]` - Maximum requests per second
- `requests_per_minute`: `Optional[int]` - Maximum requests per minute
- `requests_per_hour`: `Optional[int]` - Maximum requests per hour
- `burst_size`: `int` - Maximum burst size (default: 10)

## Capability Discovery

### Without OpenAPI Spec

When no OpenAPI spec is provided, APIESA discovers generic capabilities:
- `get_request`
- `post_request`
- `put_request`
- `delete_request`
- `patch_request`

These allow any endpoint to be called with the respective HTTP method.

### With OpenAPI Spec

When an OpenAPI spec is provided, capabilities are generated from paths and methods:

**Naming Convention:**
- `{method}_{path_name}`
- Path parameters are included: `/users/{id}` → `users_id`
- Slashes become underscores: `/api/v1/users` → `api_v1_users`
- Hyphens become underscores: `/user-profiles` → `user_profiles`

**Examples:**
- `GET /users` → `get_users`
- `POST /users` → `post_users`
- `GET /users/{id}` → `get_users_id`
- `PUT /users/{id}` → `put_users_id`
- `DELETE /users/{id}` → `delete_users_id`
- `GET /api/v1/posts` → `get_api_v1_posts`

## Rate Limiting

APIESA implements a **sliding window** rate limiting algorithm:

1. **Multi-Level**: Enforces limits at second, minute, and hour levels
2. **Sliding Window**: Uses actual request timestamps (not fixed windows)
3. **Automatic Throttling**: Waits if rate limit is reached
4. **Cleanup**: Automatically removes old timestamps

**Example:**
```python
# Rate limit: 2 requests per second
config = RateLimitConfig(requests_per_second=2)

# Requests 1-2: Execute immediately
# Request 3: Waits ~1 second (rate limit enforced)
# Request 4: Waits again
```

**Long Wait Prevention:**
If hourly rate limit would require waiting more than 60 seconds, an `ESAOperationError` is raised instead of waiting.

## Error Handling

APIESA provides comprehensive error handling:

### Exception Types

- `ESAConnectionError`: Connection to API failed
- `ESAOperationError`: API operation failed (timeout, request error, etc.)
- `ESANotEstablishedError`: Trust not established
- `ESACapabilityNotFoundError`: Requested capability not available
- `ESAAuthorizationError`: Agent not authorized for operation

### Error Context

All errors include detailed context:
- `system_id`: Which API system
- `operation`: What operation failed
- `reason`: Why it failed
- `original_error`: Original exception (if applicable)

### Example

```python
try:
    result = await esa.get("/users")
except ESAOperationError as e:
    print(f"Operation failed: {e.operation}")
    print(f"Reason: {e.reason}")
    print(f"Original error: {e.original_error}")
```

## Performance Considerations

### HTTP Client

- Uses `httpx.AsyncClient` for async I/O
- Client is created on first use and reused
- Proper cleanup with `await esa.cleanup()`

### Rate Limiting

- Lock-based synchronization for thread safety
- Efficient timestamp cleanup (only keeps relevant timestamps)
- No unnecessary delays (precise sleep times)

### Request Logging

- Circular buffer (last 1000 requests)
- Minimal memory footprint
- Fast statistics calculation

## Security Considerations

### Authentication

- Auth headers are stored in memory (not persisted)
- Headers are merged with request headers (overridable)
- No automatic credential refresh (implement externally if needed)

### Trust Verification

- Every operation goes through trust verification
- Agent must have appropriate capability
- Audit trail for all operations

### Rate Limiting

- Prevents API abuse
- Enforces organizational policies
- Protects against runaway agents

## Integration with Trust System

APIESA fully integrates with the EATP trust system:

### Trust Establishment

```python
# ESA establishes trust via SYSTEM authority
await esa.establish_trust(authority_id="org-acme")

# Capabilities are registered in trust system
# Trust chain is created and stored
```

### Trust Verification

```python
# Agent requests operation
result = await esa.execute(
    operation="get_users",
    parameters={"path": "/users"},
    requesting_agent_id="agent-001",
)

# ESA verifies:
# 1. Agent has trust chain
# 2. Agent has required capability
# 3. Constraints are satisfied
# 4. Trust is not expired
```

### Audit Logging

```python
# Every operation is audited
# Audit anchor includes:
# - Agent ID
# - Action (operation name)
# - Resource (API endpoint)
# - Result (success/failure)
# - Context (parameters, duration, error)
```

## Testing

Comprehensive unit tests are provided in `tests/unit/trust/esa/test_apiesa.py`:

- Initialization tests
- Capability discovery tests
- Connection validation tests
- HTTP method tests
- Rate limiting tests
- Request logging tests
- Error handling tests
- Cleanup tests

Run tests:
```bash
pytest tests/unit/trust/esa/test_apiesa.py -v
```

## Examples

See `examples/trust/esa_api_example.py` for complete examples:
- Basic usage
- OpenAPI spec parsing
- Agent integration
- Rate limiting
- Request logging
- Health checks

## Dependencies

- `httpx` - Async HTTP client
- Base ESA dependencies (TrustOperations, etc.)

Install:
```bash
pip install httpx
```

## Future Enhancements

- **OAuth2 Support**: Automatic token refresh
- **Retry Logic**: Configurable retry with exponential backoff
- **Circuit Breaker**: Prevent cascading failures
- **Response Caching**: Cache GET responses
- **Webhook Support**: Receive API callbacks
- **GraphQL Support**: Query and mutation operations
- **Batch Operations**: Multiple requests in single call
- **Request Signing**: HMAC or digital signatures

## License

Part of Kailash Kaizen - Enterprise Agent Trust Protocol (EATP) implementation.
