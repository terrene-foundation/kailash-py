# API Integration Nodes

**Module**: `kailash.nodes.api`
**Last Updated**: 2025-01-06

This document covers all API integration nodes including HTTP clients, authentication, GraphQL, REST, and rate limiting.

## Table of Contents
- [Authentication Nodes](#authentication-nodes)
- [HTTP Client Nodes](#http-client-nodes)
- [GraphQL Nodes](#graphql-nodes)
- [REST Client Nodes](#rest-client-nodes)
- [Rate Limiting Nodes](#rate-limiting-nodes)

## Authentication Nodes

### APIKeyNode
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: API key authentication
- **Parameters**:
  - `api_key`: API key value
  - `header_name`: Header field name

### BasicAuthNode
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: Basic HTTP authentication
- **Parameters**:
  - `username`: Username
  - `password`: Password

### OAuth2Node
- **Module**: `kailash.nodes.api.auth`
- **Purpose**: OAuth2 authentication flow
- **Parameters**:
  - `client_id`: OAuth client ID
  - `client_secret`: OAuth client secret
  - `token_url`: Token endpoint URL

## HTTP Client Nodes

### HTTPRequestNode
- **Module**: `kailash.nodes.api.http`
- **Purpose**: Make HTTP requests (synchronous)
- **Parameters**:
  - `url`: Target URL
  - `method`: HTTP method (GET, POST, etc.)
  - `headers`: Request headers
  - `body`: Request body
  - `timeout`: Request timeout

**Example**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# HTTP GET request
workflow.add_node("HTTPRequestNode", "api_get", {
    "url": "https://api.github.com/users/octocat",
    "method": "GET",
    "headers": {"User-Agent": "Kailash-SDK"},
    "timeout": 30
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Response: {results['api_get']['result']['status_code']}")
```

### AsyncHTTPRequestNode
- **Module**: `kailash.nodes.api.http`
- **Purpose**: Make HTTP requests (asynchronous)
- **Parameters**: Same as HTTPRequestNode

## GraphQL Nodes

### GraphQLClientNode
- **Module**: `kailash.nodes.api.graphql`
- **Purpose**: Execute GraphQL queries (synchronous)
- **Parameters**:
  - `endpoint`: GraphQL endpoint URL
  - `query`: GraphQL query string
  - `variables`: Query variables

### AsyncGraphQLClientNode
- **Module**: `kailash.nodes.api.graphql`
- **Purpose**: Execute GraphQL queries (asynchronous)
- **Parameters**: Same as GraphQLClientNode

## REST Client Nodes

### RESTClientNode
- **Module**: `kailash.nodes.api.rest`
- **Purpose**: RESTful API client (synchronous)
- **Parameters**:
  - `base_url`: API base URL
  - `endpoint`: Specific endpoint
  - `method`: HTTP method
  - `params`: Query parameters
  - `json_data`: JSON payload

**Example**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# REST API POST request
workflow.add_node("RESTClientNode", "create_user", {
    "base_url": "https://api.example.com",
    "endpoint": "/users",
    "method": "POST",
    "json_data": {
        "name": "John Doe",
        "email": "john@example.com"
    },
    "headers": {"Authorization": "Bearer token123"}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### AsyncRESTClientNode
- **Module**: `kailash.nodes.api.rest`
- **Purpose**: RESTful API client (asynchronous)
- **Parameters**: Same as RESTClientNode

## Rate Limiting Nodes

### RateLimitedAPINode
- **Module**: `kailash.nodes.api.rate_limiting`
- **Purpose**: API calls with rate limiting (synchronous)
- **Parameters**:
  - `rate_limit`: Calls per time period
  - `time_window`: Time window in seconds

### AsyncRateLimitedAPINode
- **Module**: `kailash.nodes.api.rate_limiting`
- **Purpose**: API calls with rate limiting (asynchronous)
- **Parameters**: Same as RateLimitedAPINode

## See Also
- [Data Nodes](03-data-nodes.md) - Data I/O operations
- [Code Nodes](07-code-nodes.md) - Custom code execution
- [API Reference](../api/08-nodes-api.yaml) - Detailed API documentation
