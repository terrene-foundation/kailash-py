# API Integration in Kailash SDK

## Overview

The API Integration module in Kailash SDK provides a comprehensive set of nodes for interacting with external APIs. It supports both synchronous and asynchronous operations, various API styles (HTTP, REST, GraphQL), and multiple authentication methods.

## Features

- **HTTP Client Nodes**: Basic HTTP request capabilities for any protocol/endpoint
- **REST API Client Nodes**: Specialized support for RESTful API patterns
- **GraphQL Client Nodes**: Support for GraphQL APIs with query/mutation capabilities
- **Authentication Helpers**: Support for Basic Auth, OAuth2, and API Keys
- **Async Support**: Non-blocking API operations for high-performance workflows
- **Error Handling**: Comprehensive error handling and retry capabilities
- **Response Processing**: Content type detection and automatic parsing

## Node Types

### HTTP Client Nodes

- `HTTPRequestNode`: Core node for making HTTP requests
- `AsyncHTTPRequestNode`: Asynchronous version with the same interface

These nodes provide low-level access to make any HTTP request with the following capabilities:
- All HTTP methods (GET, POST, PUT, DELETE, etc.)
- Custom headers and query parameters
- Request body in various formats
- Response parsing based on content type
- Timeout and SSL verification control
- Retry logic with exponential backoff

### REST Client Nodes

- `RESTClientNode`: High-level node for RESTful API interactions
- `AsyncRESTClientNode`: Asynchronous version with the same interface

These nodes build on the HTTP client with REST-specific features:
- Resource-based URL construction
- Path parameter substitution
- Pagination handling
- Error response format standardization
- API versioning support

### GraphQL Client Nodes

- `GraphQLClientNode`: Specialized node for GraphQL API operations
- `AsyncGraphQLClientNode`: Asynchronous version with the same interface

These nodes offer GraphQL-specific functionality:
- Query and mutation support
- Variable binding
- Operation name specification
- GraphQL error handling
- Response formatting options

### Authentication Nodes

- `BasicAuthNode`: Username/password authentication
- `OAuth2Node`: OAuth 2.0 authentication with various grant types
- `APIKeyNode`: API key authentication in headers, query params, or body

## Usage Examples

### Basic HTTP Request

```python
from kailash.workflow import Workflow
from kailash.nodes.api import HTTPRequestNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow(name="http_example")

# Add HTTP request node
http_node = HTTPRequestNode(
    id="get_users",
    name="Get Users",
    url="https://api.example.com/users",
    method="GET",
    headers={"Accept": "application/json"}
)
workflow.add_node(http_node, "get_users")

# Execute workflow
runtime = LocalRuntime()
results, _ = runtime.execute(workflow)

# Access results
users = results["get_users"]["response"]["content"]
```

### REST API with Path Parameters

```python
from kailash.workflow import Workflow
from kailash.nodes.api import RESTClientNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow(name="rest_example")

# Add REST client node
rest_node = RESTClientNode(
    id="get_user",
    name="Get User",
    base_url="https://api.example.com",
    resource="users/{id}",
    method="GET",
    path_params={"id": 123}
)
workflow.add_node(rest_node, "get_user")

# Execute workflow
runtime = LocalRuntime()
results, _ = runtime.execute(workflow)

# Access results
user = results["get_user"]["data"]
```

### GraphQL Query with Variables

```python
from kailash.workflow import Workflow
from kailash.nodes.api import GraphQLClientNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow(name="graphql_example")

# Add GraphQL client node
graphql_node = GraphQLClientNode(
    id="get_user",
    name="Get User",
    endpoint="https://api.example.com/graphql",
    query="""
    query GetUser($id: ID!) {
      user(id: $id) {
        id
        name
        email
      }
    }
    """,
    variables={"id": "123"},
    operation_name="GetUser"
)
workflow.add_node(graphql_node, "get_user")

# Execute workflow
runtime = LocalRuntime()
results, _ = runtime.execute(workflow)

# Access results
user = results["get_user"]["data"]["user"]
```

### OAuth 2.0 Authentication

```python
from kailash.workflow import Workflow
from kailash.nodes.api import OAuth2Node, RESTClientNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow(name="oauth_example")

# Add OAuth2 node
oauth_node = OAuth2Node(
    id="oauth",
    name="OAuth Authentication",
    token_url="https://api.example.com/oauth/token",
    client_id="your_client_id",
    client_secret="your_client_secret",
    grant_type="client_credentials"
)
workflow.add_node(oauth_node, "oauth")

# Add REST client node
rest_node = RESTClientNode(
    id="get_data",
    name="Get Protected Data",
    base_url="https://api.example.com",
    resource="protected-data",
    method="GET"
)
workflow.add_node(rest_node, "get_data")

# Connect OAuth node to REST node
workflow.connect(
    "oauth", 
    "get_data",
    {"headers": "headers"}
)

# Execute workflow
runtime = LocalRuntime()
results, _ = runtime.execute(workflow)
```

### Asynchronous API Calls

```python
import asyncio
from kailash.workflow import Workflow
from kailash.nodes.api import AsyncHTTPRequestNode
from kailash.runtime.async_local import AsyncLocalRuntime

async def main():
    # Create workflow
    workflow = Workflow(name="async_example")
    
    # Add async HTTP request nodes
    users_node = AsyncHTTPRequestNode(
        id="get_users",
        name="Get Users",
        url="https://api.example.com/users",
        method="GET"
    )
    workflow.add_node(users_node, "get_users")
    
    posts_node = AsyncHTTPRequestNode(
        id="get_posts",
        name="Get Posts",
        url="https://api.example.com/posts",
        method="GET"
    )
    workflow.add_node(posts_node, "get_posts")
    
    # Execute workflow asynchronously
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_async(workflow)
    
    # Access results
    users = results["get_users"]["response"]["content"]
    posts = results["get_posts"]["response"]["content"]

# Run async example
asyncio.run(main())
```

## Implementation Details

### Error Handling

All API nodes include comprehensive error handling:
- Transport-level errors (connection failures, timeouts)
- HTTP-level errors (4xx, 5xx status codes)
- API-level errors (error responses with valid HTTP status)
- Validation errors (invalid parameters)

### Response Processing

Response handling is content-type aware:
- JSON responses are automatically parsed
- Text responses are returned as strings
- Binary responses are returned as bytes
- Mixed content types can be handled with the `response_format` parameter

### Retry Logic

All nodes support configurable retry behavior:
- Number of retry attempts
- Backoff factor for increasing delays
- Specific status codes to retry

### Extension Points

The module is designed for extensibility:
- Create specialized API client nodes for specific services
- Extend authentication mechanisms for custom auth flows
- Implement custom response processors for special content types

## See Also

- [API Integration Example](../../examples/api_integration_example.py)
- [HTTP Node Tests](../../tests/test_nodes/test_api.py)