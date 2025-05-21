# 0015. API Integration Architecture

Date: 2025-05-21
Status: Accepted
Author: Kailash SDK Team

## Context

The Kailash SDK needs to support integration with external APIs to enable workflows that interact with external services, fetch data from REST endpoints, query GraphQL APIs, and more. This requires a robust, flexible approach to API integration that supports both synchronous and asynchronous operations, various authentication mechanisms, and different API styles.

The architecture decision needs to address:
- How to support different API styles (HTTP, REST, GraphQL)
- How to handle authentication consistently
- How to enable both synchronous and asynchronous operations
- How to structure API-related nodes within the existing node system

## Decision

We will implement a set of API integration nodes with the following architecture:

1. **Layered API Node Hierarchy**:
   - Base HTTP nodes (`HTTPRequestNode`, `AsyncHTTPRequestNode`) for low-level HTTP operations
   - Specialized client nodes (`RESTClientNode`, `GraphQLClientNode`) for higher-level protocols
   - All with both synchronous and asynchronous implementations

2. **Separate Authentication Nodes**:
   - Authentication nodes (`BasicAuthNode`, `OAuth2Node`, `APIKeyNode`) that output auth headers/credentials
   - These can be connected to API request nodes via workflow connections
   - This separation allows reusing auth across multiple API operations

3. **Asynchronous Support**:
   - Leverage the existing `AsyncNode` base class for async operations
   - Provide both synchronous and asynchronous versions of all API nodes
   - Allow mixing sync and async nodes in workflows based on performance needs

4. **Consistent Error Handling**:
   - Transport-level errors (connection failures, timeouts)
   - HTTP-level errors (4xx, 5xx status codes)
   - API-level errors (error responses with valid HTTP status)
   - Standardized error response formats across protocols

5. **Response Processing**:
   - Content-type aware response handling
   - Automatic parsing of common formats (JSON, text, binary)
   - Protocol-specific response validation (GraphQL errors, REST pagination)

## Consequences

### Positive

- **Flexibility**: Users can choose the appropriate node type for their API integration needs
- **Reusability**: Authentication and request nodes can be reused across workflows
- **Performance**: Asynchronous nodes enable high-throughput API operations
- **Consistency**: Standardized error handling and response processing
- **Protocol Support**: Native support for HTTP, REST, and GraphQL APIs

### Negative

- **Complexity**: More node types to document and maintain
- **Learning Curve**: Users need to understand the appropriate node type for their needs
- **Versioning**: API endpoints may change and require versioning support

### Neutral

- **Dependency on HTTP Libraries**: Relies on requests/aiohttp for HTTP operations
- **Authentication Management**: Separate nodes for auth requires more connections

## Implementation Details

The implementation includes:

1. **API Package Structure**:
   ```
   nodes/api/
     ├── __init__.py
     ├── http.py        # HTTP request nodes
     ├── rest.py        # REST client nodes
     ├── graphql.py     # GraphQL client nodes
     └── auth.py        # Authentication nodes
   ```

2. **Node Classes**:
   - `HTTPRequestNode` & `AsyncHTTPRequestNode`
   - `RESTClientNode` & `AsyncRESTClientNode`
   - `GraphQLClientNode` & `AsyncGraphQLClientNode`
   - `BasicAuthNode`, `OAuth2Node`, `APIKeyNode`

3. **Request/Response Models**:
   - `HTTPResponse` for standardized response structure
   - Enum types for HTTP methods, response formats, etc.

## Alternatives Considered

### Single Unified API Node

We considered implementing a single unified API node that could handle all API types, but this would create a complex, difficult-to-maintain node with many configuration options. The layered approach provides better separation of concerns and more flexibility.

### Client-Only Authentication

We considered building authentication directly into the API nodes rather than using separate authentication nodes. While this would simplify the workflow, it would limit reusability of authentication across multiple API calls and make authentication less transparent in the workflow.

### Protocol-Specific Base Classes

We considered creating separate inheritance hierarchies for each protocol instead of building on the HTTP nodes. This would provide cleaner abstractions but would lead to code duplication for common HTTP functionality.

## References

- [RESTful API Best Practices](https://docs.microsoft.com/en-us/azure/architecture/best-practices/api-design)
- [GraphQL Specification](https://spec.graphql.org/)
- [OAuth 2.0 Specification](https://oauth.net/2/)