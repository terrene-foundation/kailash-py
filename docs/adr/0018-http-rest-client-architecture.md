# ADR-0018: HTTP and REST Client Architecture

## Status
Accepted

## Context
Enterprise workflows require robust API integration capabilities with proper authentication, error handling, retry logic, and REST semantics. The existing HTTPRequestNode and RESTClientNode were placeholders that needed full implementation.

## Decision
We implemented two complementary nodes with a layered architecture:

1. **HTTPClient**: Low-level HTTP client with full request/response control
2. **RESTClient**: High-level REST client built on HTTPClient with resource-oriented operations

### Architecture:
```
RESTClient (nodes/api/rest_client.py)
    └── uses → HTTPClient (nodes/api/http_client.py)
                    └── uses → urllib (standard library)
```

### Key Design Principles:
1. **Minimal Dependencies**: Use standard library (urllib) instead of external libraries
2. **Separation of Concerns**: HTTP mechanics vs REST semantics
3. **Enterprise Features**: Authentication, retries, rate limiting, logging
4. **Graceful Error Handling**: Detailed error types and recovery suggestions
5. **REST Conventions**: CRUD operations, resource paths, HATEOAS support

## Implementation Details

### HTTPClient Features:
- Multiple authentication methods (Bearer, Basic, API Key, OAuth)
- Exponential backoff retry strategy
- Request/response logging
- Rate limiting support
- SSL certificate verification
- Timeout handling
- Custom headers and query parameters

### RESTClient Features:
- Resource-oriented design (GET, LIST, CREATE, UPDATE, PATCH, DELETE)
- Automatic JSON serialization/deserialization
- API versioning support
- Pagination metadata extraction
- HATEOAS link following
- REST-specific error handling (404, 401, 403, 400, 409)
- Nested resource support

## Consequences

### Positive:
- Zero external dependencies (uses urllib)
- Clear separation between HTTP and REST concerns
- Enterprise-ready with all common features
- Easy to extend for specific APIs
- Consistent with Node pattern
- Comprehensive error handling

### Negative:
- More verbose than using requests library
- Manual implementation of some features
- Type simplification needed for Pydantic compatibility

## Usage Examples

### HTTPClient:
```python
client = HTTPClient()
result = client.run(
    method="POST",
    url="https://api.example.com/data",
    auth_type="bearer",
    auth_token="secret-token",
    body={"key": "value"},
    max_retries=3,
    timeout=30
)
```

### RESTClient:
```python
client = RESTClient()
result = client.run(
    base_url="https://api.example.com",
    resource="users",
    resource_id="123",
    operation="update",
    data={"name": "Updated Name"},
    auth_type="bearer",
    auth_token="secret-token"
)
```

## Trade-offs
- Chose urllib over requests to minimize dependencies
- Simplified Union types to single types for Pydantic compatibility
- Implemented mock responses for testing without actual HTTP calls
- Focused on synchronous implementation (async versions exist separately)
