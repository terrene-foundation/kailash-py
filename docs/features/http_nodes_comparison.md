# HTTP Node Comparison Guide

The Kailash SDK provides two HTTP client nodes with different design philosophies:

## HTTPRequestNode vs HTTPClientNode

### HTTPRequestNode
- **Purpose**: Modern, feature-rich HTTP client for general use
- **Dependencies**: Uses `requests` (sync) and `aiohttp` (async) libraries
- **Async Support**: ✅ Yes (via AsyncHTTPRequestNode)
- **Key Features**:
  - Session reuse for better performance
  - Structured response with Pydantic models
  - Enum-based validation for methods and formats
  - Built-in retry with exponential backoff
  - Multiple response formats (JSON, text, binary, auto)
  - Clean error handling with NodeExecutionError

**Use When**:
- You need async/await support
- You want maximum performance with session reuse
- You're building modern workflows with external dependencies
- You need structured, validated responses

### HTTPClientNode
- **Purpose**: Zero-dependency HTTP client with built-in auth and rate limiting
- **Dependencies**: None (uses only Python standard library)
- **Async Support**: ❌ No (sync only)
- **Key Features**:
  - No external dependencies (uses urllib)
  - Built-in authentication (Bearer, Basic, API Key, OAuth2)
  - Built-in rate limiting with configurable delays
  - Request/response logging capability
  - Detailed error recovery suggestions
  - Configurable retry status codes
  - Query parameter merging

**Use When**:
- You need to avoid external dependencies
- You want built-in authentication handling
- You need rate limiting without additional nodes
- You're in a restricted environment with limited packages
- You need detailed request/response logging

## Example Usage

### HTTPRequestNode (Modern approach)
```python
from kailash.nodes.api import HTTPRequestNode

# Simple GET request with retry
node = HTTPRequestNode()
result = node.execute(
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer token"},
    retry_count=3,
    timeout=30
)
```

### HTTPClientNode (Zero-dependency approach)
```python
from kailash.nodes.api import HTTPClientNode

# GET request with built-in auth and rate limiting
node = HTTPClientNode()
result = node.execute(
    url="https://api.example.com/data",
    method="GET",
    auth_type="bearer",
    auth_token="your-token",
    rate_limit_delay=1.0,  # 1 second between requests
    max_retries=3,
    log_requests=True
)
```

## Recommendation

Both nodes serve valid use cases:
- Choose **HTTPRequestNode** for most scenarios, especially when you need async support or are building modern workflows
- Choose **HTTPClientNode** when you need zero dependencies, built-in auth, or rate limiting without additional complexity

The nodes can coexist in the same project, allowing you to choose the right tool for each specific use case.
