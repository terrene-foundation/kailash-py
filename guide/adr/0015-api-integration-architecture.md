# ADR-0015: API Integration Architecture

Date: 2025-05-28
Status: Accepted
Author: Kailash SDK Team

## Context

Following the gaps analysis from the HMI project implementation, the Kailash SDK needed comprehensive built-in support for API integrations. The original SDK lacked standardized patterns for:

- REST API client integration with authentication and retry logic
- GraphQL API support
- OAuth 2.0 authentication flows
- **Rate limiting and throttling for API calls** (key missing piece identified)
- Comprehensive error handling for external service integration

The gaps analysis identified that users were implementing custom API wrappers (like `HmiMcpWrapper`) because the SDK didn't provide standardized API integration patterns, particularly for rate limiting which is essential for production API usage.

## Decision

We have implemented a comprehensive API integration architecture that provides:

### 1. Layered API Node Hierarchy
- Base HTTP nodes (`HTTPRequestNode`, `AsyncHTTPRequestNode`) for low-level HTTP operations
- Specialized client nodes (`RESTClientNode`, `GraphQLClientNode`) for higher-level protocols
- All with both synchronous and asynchronous implementations

### 2. Authentication Infrastructure
- `BasicAuthNode` for username/password authentication
- `OAuth2Node` for OAuth 2.0 flows (client credentials, password, refresh token)
- `APIKeyNode` for API key authentication (header, query, body placement)
- Token caching and automatic refresh for OAuth
- Separation allows reusing auth across multiple API operations

### 3. Rate Limiting and Throttling System
- `RateLimitConfig` for configurable rate limiting policies
- `TokenBucketRateLimiter` for burst-friendly rate limiting
- `SlidingWindowRateLimiter` for precise rate limiting
- `RateLimitedAPINode` and `AsyncRateLimitedAPINode` wrapper nodes
- Configurable backoff strategies and maximum wait times
- Thread-safe implementation for concurrent use

### 4. Comprehensive Error Handling
- Transport-level errors (connection failures, timeouts)
- HTTP-level errors (4xx, 5xx status codes)
- API-level errors (error responses with valid HTTP status)
- Retry logic with exponential backoff
- Rate limit detection and automatic waiting

### 5. Response Processing and Protocol Support
- Content-type aware response handling
- Automatic parsing of common formats (JSON, text, binary)
- Protocol-specific response validation (GraphQL errors, REST pagination)
- Resource-based URL patterns with path parameter substitution

## Consequences

### Positive

- **Production Ready**: Built-in rate limiting, error handling, and authentication for enterprise use
- **Comprehensive Coverage**: Addresses all gaps identified in the HMI analysis
- **Flexible Architecture**: Can handle simple HTTP calls or complex OAuth workflows
- **Performance Optimized**: Async support for high-throughput scenarios
- **Reusability**: Authentication and rate limiting can be reused across workflows
- **Standardized Patterns**: Consistent approach to API integration across projects

### Negative

- **Increased Complexity**: More node types and configuration options to learn
- **Memory Overhead**: Rate limiting state and token caching consume memory
- **Dependency Growth**: Additional dependencies for HTTP clients (requests, aiohttp)

### Neutral

- **Breaking Changes**: None - this is additive to existing functionality
- **Migration Path**: Existing code continues to work, new projects can adopt API nodes

## Implementation Details

### 1. Package Structure
```
nodes/api/
├── __init__.py              # Public API exports
├── http.py                  # Basic HTTP client nodes
├── rest.py                  # REST API client nodes
├── graphql.py              # GraphQL client nodes
├── auth.py                 # Authentication nodes
└── rate_limiting.py        # Rate limiting utilities
```

### 2. Rate Limiting Architecture
Uses decorator pattern where any API node can be wrapped:

```python
rate_config = RateLimitConfig(
    max_requests=100,
    time_window=60.0,
    strategy="token_bucket",
    burst_limit=120
)

rate_limited_node = RateLimitedAPINode(
    wrapped_node=api_node,
    rate_limit_config=rate_config
)
```

### 3. Node Classes Implemented
- **HTTP**: `HTTPRequestNode` & `AsyncHTTPRequestNode`
- **REST**: `RESTClientNode` & `AsyncRESTClientNode`
- **GraphQL**: `GraphQLClientNode` & `AsyncGraphQLClientNode`
- **Auth**: `BasicAuthNode`, `OAuth2Node`, `APIKeyNode`
- **Rate Limiting**: `RateLimitedAPINode` & `AsyncRateLimitedAPINode`

### 4. Examples and Testing
- `api_integration_examples.py` - Comprehensive integration patterns
- `hmi_style_api_example.py` - Real-world healthcare API workflow
- `simple_api_test.py` - Validation tests for core functionality

## Alternatives Considered

### Library-Based Approach
We considered using existing API client libraries (like httpx) directly rather than building nodes. However, this would not integrate with the Kailash workflow system and would require users to handle their own rate limiting and error handling.

### Built-in Rate Limiting Only
We considered only implementing rate limiting without the full API integration suite. However, the gaps analysis showed users needed comprehensive API support, not just rate limiting.

### Different Rate Limiting Algorithms
We evaluated various algorithms (fixed window, leaky bucket, etc.) and chose token bucket and sliding window as they provide the best balance of accuracy and performance for typical API usage patterns.

## Implementation Status

As of 2025-05-30, the API integration architecture has been fully implemented:
- All API node classes (HTTP, REST, GraphQL) with sync and async versions
- Complete authentication infrastructure (BasicAuth, OAuth2, APIKey)
- Robust rate limiting system with token bucket and sliding window algorithms
- Comprehensive error handling and retry logic
- Full test coverage across all API node types
- Working examples demonstrating all features
- Production-ready with all gaps from HMI analysis addressed

## Agentic Workflow Integration

**Updated 2025-06-01**: Following client requirements for agentic AI workflows, the API integration architecture has been extended to support:

### LangChain/Langgraph Integration Patterns

The API nodes are designed to integrate seamlessly with agentic workflows:

1. **Agent Tool Integration**: API nodes can be exposed as tools to LLM agents
```python
# LLM Agent with API tool integration
workflow.add_node("LLMAgent", "research_agent", config={
    "provider": "openai",
    "model": "gpt-4",
    "tools": [
        {
            "name": "search_api", 
            "node": "RESTClientNode",
            "config": {"base_url": "https://api.search.com"}
        },
        {
            "name": "data_api",
            "node": "GraphQLClientNode", 
            "config": {"endpoint": "https://api.data.com/graphql"}
        }
    ]
})
```

2. **Multi-Agent API Coordination**: API calls coordinated between multiple agents
```python
# Agent A fetches data, Agent B processes results
workflow.add_node("LLMAgent", "data_fetcher", config={
    "role": "data_collector",
    "api_tools": ["search_api", "database_api"]
})

workflow.add_node("LLMAgent", "data_processor", config={
    "role": "data_analyzer", 
    "receives_from": ["data_fetcher"],
    "api_tools": ["analysis_api"]
})
```

3. **MCP Protocol Support**: API nodes support Model Context Protocol for context sharing
```python
# API node with MCP context sharing
workflow.add_node("RESTClientNode", "mcp_api", config={
    "base_url": "https://api.example.com",
    "mcp_context": {
        "share_responses": True,
        "context_key": "api_data",
        "format": "structured"
    }
})
```

### Agent-to-Agent API Communication

API nodes facilitate communication between agents in distributed workflows:

1. **Agent Registry API**: Agents discover each other through registry APIs
2. **Status APIs**: Agents report status and coordinate through API endpoints  
3. **Data Exchange APIs**: Agents share data and results via structured APIs

### Agentic Workflow Patterns

Common patterns for API integration in agentic workflows:

1. **Research Agent Pattern**: Agent uses search/knowledge APIs as tools
2. **Data Pipeline Agent**: Agent orchestrates multiple data APIs
3. **Monitoring Agent**: Agent uses status/health check APIs
4. **Coordination Agent**: Agent manages other agents via control APIs

## References

- Gaps Analysis: HMI Project Implementation
- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [HTTP/1.1 RFC 7231](https://tools.ietf.org/html/rfc7231)
- [GraphQL Specification](https://spec.graphql.org/)
- [Token Bucket Algorithm](https://en.wikipedia.org/wiki/Token_bucket)
- [LangChain Tool Integration](https://python.langchain.com/docs/modules/tools/)
- [ADR-0022: MCP Integration Architecture](0022-mcp-integration-architecture.md)
- [ADR-0023: A2A Communication Architecture](0023-a2a-communication-architecture.md)
- [ADR-0024: LLM Agent Architecture](0024-llm-agent-architecture.md)
