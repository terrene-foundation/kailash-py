"""
API integration and HTTP client nodes for the Kailash SDK.

This module provides nodes for interacting with external HTTP APIs, with support for
various authentication methods, request/response formats, and both synchronous and
asynchronous operation.

The module includes:
- Base HTTP client nodes
- Specialized API client nodes (REST, GraphQL)
- Authentication helpers
- Request/response formatters

Design philosophy:
- Support both simple one-off API calls and complex client integrations
- Maintain consistent interface patterns with other node types
- Provide sensible defaults while allowing full customization
- Enable both synchronous and asynchronous operation
"""

from .auth import APIKeyNode, BasicAuthNode, OAuth2Node
from .graphql import AsyncGraphQLClientNode, GraphQLClientNode
from .http import AsyncHTTPRequestNode, HTTPRequestNode
from .rate_limiting import (
    AsyncRateLimitedAPINode,
    RateLimitConfig,
    RateLimitedAPINode,
    RateLimiter,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    create_rate_limiter,
)
from .rest import AsyncRESTClientNode, RESTClientNode

__all__ = [
    "HTTPRequestNode",
    "AsyncHTTPRequestNode",
    "RESTClientNode",
    "AsyncRESTClientNode",
    "GraphQLClientNode",
    "AsyncGraphQLClientNode",
    "BasicAuthNode",
    "OAuth2Node",
    "APIKeyNode",
    "RateLimitConfig",
    "RateLimiter",
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "RateLimitedAPINode",
    "AsyncRateLimitedAPINode",
    "create_rate_limiter",
]
