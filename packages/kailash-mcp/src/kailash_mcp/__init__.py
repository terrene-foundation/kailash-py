# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kailash MCP -- Production-ready Model Context Protocol for Kailash SDK.

Provides MCP client/server, authentication, service discovery, transports,
and the Kailash Platform MCP Server for AI assistant introspection.
"""

__version__ = "0.2.8"

# Advanced Features
from kailash_mcp.advanced.features import (
    BinaryResourceHandler,
    CancellationContext,
    ChangeType,
    Content,
    ContentType,
    ElicitationSystem,
    MultiModalContent,
    ProgressReporter,
    ResourceChange,
)
from kailash_mcp.advanced.features import ResourceTemplate as AdvancedResourceTemplate
from kailash_mcp.advanced.features import (
    SchemaValidator,
    StreamingHandler,
    StructuredTool,
    ToolAnnotation,
    create_cancellation_context,
    create_progress_reporter,
    structured_tool,
)

# Authentication framework
from kailash_mcp.auth.providers import (
    APIKeyAuth,
    AuthManager,
    AuthProvider,
    BasicAuth,
    BearerTokenAuth,
    JWTAuth,
    PermissionManager,
    RateLimiter,
)
from kailash_mcp.client import MCPClient

# Service Discovery System
from kailash_mcp.discovery.discovery import (
    DiscoveryBackend,
    FileBasedDiscovery,
    HealthChecker,
    LoadBalancer,
    NetworkDiscovery,
    ServerInfo,
    ServiceMesh,
    ServiceRegistry,
    create_default_registry,
    discover_mcp_servers,
    get_mcp_client,
)

# Enhanced error handling
from kailash_mcp.errors import (
    AuthenticationError,
    AuthorizationError,
    CircuitBreakerRetry,
    ErrorAggregator,
    ExponentialBackoffRetry,
    MCPError,
    MCPErrorCode,
    RateLimitError,
    ResourceError,
    RetryableOperation,
    RetryStrategy,
    ServiceDiscoveryError,
    ToolError,
    TransportError,
    ValidationError,
)

# OAuth 2.1 Authentication (requires the [auth-oauth] extra:
# aiohttp + PyJWT + cryptography). If the extra is not installed, symbols
# below are absent and the module emits an INFO-level log at import time so
# operators see the downgrade; accessing a missing OAuth symbol raises a
# descriptive ImportError via `kailash_mcp.auth.__getattr__` rather than
# a silent AttributeError (rules/dependencies.md § "Declared = Gated
# Consistently").
try:
    from kailash_mcp.auth.oauth import (
        AccessToken,
        AuthorizationCode,
        AuthorizationServer,
        ClientStore,
        ClientType,
        GrantType,
        InMemoryClientStore,
        InMemoryTokenStore,
        JWTManager,
        OAuth2Client,
        OAuthClient,
        RefreshToken,
        ResourceServer,
        TokenStore,
        TokenType,
    )
except ImportError as _oauth_err:  # pragma: no cover
    import logging as _logging

    _logging.getLogger(__name__).info(
        "oauth.module_unavailable",
        extra={
            "hint": "install with: pip install kailash-mcp[auth-oauth]",
            "missing": str(_oauth_err),
        },
    )

# Registry Integration
from kailash_mcp.discovery.registry_integration import (
    NetworkAnnouncer,
    ServerRegistrar,
    enable_auto_discovery,
    register_server_manually,
)

# Complete Protocol Implementation
from kailash_mcp.protocol.protocol import (
    CancellationManager,
    CancelledNotification,
    CompletionManager,
    CompletionRequest,
    CompletionResult,
    MessageType,
    MetaData,
    ProgressManager,
    ProgressNotification,
    ProgressToken,
    ProtocolManager,
    ResourceTemplate,
    RootsManager,
    SamplingManager,
    SamplingRequest,
    ToolResult,
    cancel_request,
    complete_progress,
    get_protocol_manager,
    is_cancelled,
    start_progress,
    update_progress,
)

# Enhanced server with production features
from kailash_mcp.server import MCPServer, MCPServerBase, SimpleMCPServer

# Enhanced Transport Layer (requires aiohttp + websockets)
try:
    from kailash_mcp.transports.transports import (
        BaseTransport,
        EnhancedStdioTransport,
        SSETransport,
        StreamableHTTPTransport,
        TransportManager,
        TransportSecurity,
        WebSocketTransport,
        get_transport_manager,
    )
except ImportError:
    import logging as _logging

    _logging.getLogger(__name__).debug(
        "Transport modules not available -- install with: pip install kailash-mcp[full]"
    )

__all__ = [
    # Core MCP Components
    "MCPClient",
    "MCPServer",
    "MCPServerBase",
    # Prototyping server
    "SimpleMCPServer",
    # Service Discovery System
    "ServiceRegistry",
    "ServerInfo",
    "DiscoveryBackend",
    "FileBasedDiscovery",
    "NetworkDiscovery",
    "HealthChecker",
    "LoadBalancer",
    "ServiceMesh",
    "create_default_registry",
    "discover_mcp_servers",
    "get_mcp_client",
    # Registry Integration
    "ServerRegistrar",
    "NetworkAnnouncer",
    "enable_auto_discovery",
    "register_server_manually",
    # Authentication
    "AuthProvider",
    "APIKeyAuth",
    "BearerTokenAuth",
    "JWTAuth",
    "BasicAuth",
    "AuthManager",
    "PermissionManager",
    "RateLimiter",
    # Enhanced Error Handling
    "MCPError",
    "MCPErrorCode",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "ToolError",
    "ResourceError",
    "TransportError",
    "ServiceDiscoveryError",
    "ValidationError",
    "RetryStrategy",
    "RetryableOperation",
    "ExponentialBackoffRetry",
    "CircuitBreakerRetry",
    "ErrorAggregator",
    # Complete Protocol Implementation
    "MessageType",
    "ProgressToken",
    "MetaData",
    "ProgressNotification",
    "CancelledNotification",
    "CompletionRequest",
    "CompletionResult",
    "SamplingRequest",
    "ResourceTemplate",
    "ToolResult",
    "ProgressManager",
    "CancellationManager",
    "CompletionManager",
    "SamplingManager",
    "RootsManager",
    "ProtocolManager",
    "get_protocol_manager",
    "start_progress",
    "update_progress",
    "complete_progress",
    "is_cancelled",
    "cancel_request",
    # Enhanced Transport Layer
    "BaseTransport",
    "EnhancedStdioTransport",
    "SSETransport",
    "StreamableHTTPTransport",
    "WebSocketTransport",
    "TransportSecurity",
    "TransportManager",
    "get_transport_manager",
    # OAuth 2.1 Authentication
    "GrantType",
    "TokenType",
    "ClientType",
    "OAuthClient",
    "AccessToken",
    "RefreshToken",
    "AuthorizationCode",
    "ClientStore",
    "InMemoryClientStore",
    "TokenStore",
    "InMemoryTokenStore",
    "JWTManager",
    "AuthorizationServer",
    "ResourceServer",
    "OAuth2Client",
    # Advanced Features
    "ContentType",
    "ChangeType",
    "Content",
    "ResourceChange",
    "ToolAnnotation",
    "MultiModalContent",
    "SchemaValidator",
    "StructuredTool",
    "AdvancedResourceTemplate",
    "BinaryResourceHandler",
    "StreamingHandler",
    "ElicitationSystem",
    "ProgressReporter",
    "CancellationContext",
    "structured_tool",
    "create_progress_reporter",
    "create_cancellation_context",
]
