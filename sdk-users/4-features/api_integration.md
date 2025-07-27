# API Integration Guide for Kailash SDK

This guide demonstrates how to use the Kailash SDK's comprehensive API integration capabilities. The SDK provides built-in support for common API patterns including REST, GraphQL, authentication, rate limiting, and error handling.

## Quick Start

Run the simple test to verify everything works:

```bash
cd examples
python simple_api_test.py
```

## Core Features

### 1. HTTP Client Nodes

The SDK provides both synchronous and asynchronous HTTP client nodes:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Basic HTTP request
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# Async version for better performance
workflow_async = WorkflowBuilder()
workflow_async.add_node("AsyncHTTPRequestNode", "async_call", {
    "url": "https://api.example.com/data",
    "method": "GET"
})

result, run_id = runtime.execute(workflow_async.build())

```

### 2. REST API Client

High-level interface for REST APIs with resource patterns:

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("RESTClientNode", "api_client", {
    "base_url": "https://api.example.com",
    "resource": "users/{id}",
    "method": "GET",
    "path_params": {"id": 123}
})

# GET /users/123
runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

```

### 3. Authentication

Multiple authentication methods are supported:

#### Basic Authentication
```python
workflow = WorkflowBuilder()
workflow.add_node("BasicAuthNode", "auth", {
    "username": "myuser",
    "password": "mypass"
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# Use auth headers in API calls
api_headers = result["auth"]["headers"]

```

#### API Key Authentication
```python
# Header-based API key
workflow = WorkflowBuilder()
workflow.add_node("APIKeyNode", "api_key", {
    "api_key": "your-api-key",
    "location": "header",
    "param_name": "X-API-Key"
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

```

#### OAuth 2.0
```python
workflow = WorkflowBuilder()
workflow.add_node("OAuth2Node", "oauth", {
    "token_url": "https://api.example.com/oauth/token",
    "client_id": "your-client-id",
    "client_secret": "your-secret",
    "grant_type": "client_credentials"
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

```

### 4. Rate Limiting

Protect your API calls with sophisticated rate limiting:

```python
from kailash.nodes.api import RateLimitConfig, RateLimitedAPINode, HTTPRequestNode

# Configure rate limiting
rate_config = RateLimitConfig(
    max_requests=10,        # 10 requests
    time_window=60.0,       # per minute
    strategy="token_bucket", # algorithm
    burst_limit=15,         # allow burst up to 15
    backoff_factor=1.5      # exponential backoff
)

# Wrap any API node with rate limiting
http_node = HTTPRequestNode(node_id="api", url="https://api.example.com/data")
rate_limited = RateLimitedAPINode(
    wrapped_node=http_node,
    rate_limit_config=rate_config,
    node_id="rate_limited_api"
)

# API calls will automatically respect rate limits
result = runtime.execute_node(rate_limited)

```

#### Rate Limiting Strategies

- **Token Bucket**: Allows burst requests while maintaining steady rate
- **Sliding Window**: More accurate rate limiting, prevents boundary bursts

### 5. GraphQL Support

Full GraphQL integration with variables and error handling:

```python
from kailash.nodes.api import GraphQLClientNode

graphql_node = GraphQLClientNode(node_id="graphql", endpoint="https://api.example.com/graphql")

query = """
query GetUsers($limit: Int!) {
    users(limit: $limit) {
        id
        name
        email
    }
}
"""

result = runtime.execute_node(
    graphql_node,
    query=query,
    variables={"limit": 10}
)

```

## Advanced Examples

### HMI-Style Healthcare API Integration

The `hmi_style_api_example.py` demonstrates a real-world healthcare API integration pattern:

```bash
python hmi_style_api_example.py
```

This example shows:
- Multi-step API workflows (doctor search → slot check → insurance verification)
- Different authentication methods for different APIs
- Rate limiting strategies for different service tiers
- Error handling and resilience patterns

### Comprehensive API Integration Examples

Run the full example suite:

```bash
python api_integration_examples.py
```

This demonstrates:
- Basic REST API calls
- GraphQL queries
- Rate limiting in action
- OAuth 2.0 flows
- Complex multi-API workflows
- Asynchronous API calls
- Error handling strategies

## Rate Limiting Configuration

### Token Bucket Strategy
```python
rate_limit_config = {
    "max_requests": 100,
    "time_window": 60.0,
    "strategy": "token_bucket",
    "burst_limit": 120,  # Allow occasional bursts
    "backoff_factor": 1.5
}

```

### Sliding Window Strategy
```python
rate_limit_config = {
    "max_requests": 100,
    "time_window": 60.0,
    "strategy": "sliding_window",
    "backoff_factor": 2.0  # More aggressive backoff
}

```

## Error Handling

All API nodes include comprehensive error handling:

```python
# HTTP requests with retry logic
result = runtime.execute_node(
    http_node,
    url="https://api.example.com/data",
    retry_count=3,           # Retry 3 times
    retry_backoff=0.5,       # 0.5s base backoff
    timeout=30               # 30s timeout
)

if result["success"]:
    data = result["response"]["content"]
else:
    error_code = result["status_code"]
    # Handle error appropriately

```

## Best Practices

### 1. Use Rate Limiting
Always wrap API calls in rate limiting to respect service limits:

```python
# Good: Rate limited API calls
rate_limited_api = RateLimitedAPINode(
    wrapped_node=your_api_node,
    rate_limit_config=appropriate_config
)

```

### 2. Handle Authentication Properly
Separate authentication from API calls for reusability:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Step 1: Get authentication
runtime = LocalRuntime()
workflow.execute_node(auth_node, ...)

# Step 2: Use auth in API calls
runtime = LocalRuntime()
workflow.execute_node(
    api_node,
    headers=auth_result["headers"],
    # ... (example continues)
)

```

### 3. Use Async for High Throughput
For concurrent API calls, use async nodes:

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Multiple concurrent API calls
tasks = []
for item in items:
runtime = LocalRuntime()
workflow.execute_node_async(api_node, data=item)
    tasks.append(task)

results = await asyncio.gather(*tasks)

```

### 4. Implement Proper Error Handling
Always check for errors and implement appropriate retry logic:

```python
if not result["success"]:
    if result["status_code"] == 429:  # Rate limited
        # Wait and retry
        pass
    elif result["status_code"] >= 500:  # Server error
        # Retry with backoff
        pass
    else:  # Client error
        # Log and handle appropriately
        pass

```

## Configuration Examples

### Development Environment
```python
# Permissive rate limiting for development
dev_config = RateLimitConfig(
    max_requests=1000,
    time_window=60.0,
    strategy="token_bucket",
    burst_limit=1500
)

```

### Production Environment
```python
# Conservative rate limiting for production
prod_config = RateLimitConfig(
    max_requests=100,
    time_window=60.0,
    strategy="sliding_window",
    backoff_factor=2.0,
    max_backoff=300.0
)

```

### High-Frequency Trading
```python
# Aggressive rate limiting for high-frequency scenarios
hft_config = RateLimitConfig(
    max_requests=1000,
    time_window=1.0,  # Per second
    strategy="token_bucket",
    burst_limit=1200,
    backoff_factor=1.1  # Quick recovery
)

```

## Testing Your Integration

Use the provided test script to validate your setup:

```bash
# Test core functionality
python simple_api_test.py

# Test specific features
python -c "from kailash.nodes.api import *; print('API integration ready!')"
```

## Troubleshooting

### Common Issues

1. **Rate Limiting Too Aggressive**: Adjust `max_requests` and `time_window`
2. **Authentication Failures**: Verify credentials and token expiration
3. **Connection Timeouts**: Increase `timeout` parameter
4. **SSL Certificate Issues**: Set `verify_ssl=False` for development

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

```

## Next Steps

1. Review the example files in this directory
2. Adapt the patterns to your specific API requirements
3. Implement proper error handling for your use case
4. Configure appropriate rate limiting for your service tiers
5. Test thoroughly in development before production deployment

For more advanced usage patterns, see the `hmi_style_api_example.py` which demonstrates real-world healthcare API integration patterns.
