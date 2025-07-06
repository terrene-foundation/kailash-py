"""Enhanced Model Context Protocol (MCP) Service Layer with Service Discovery.

This module provides production-ready MCP client and server functionality with
comprehensive service discovery, authentication, monitoring, and resilience
features. Built on top of the official Anthropic MCP Python SDK.

Enhanced Features:
    - Service Discovery: Automatic server registration and discovery
    - Authentication: Multiple auth providers (API Key, JWT, OAuth)
    - Load Balancing: Intelligent server selection and failover
    - Health Monitoring: Automatic health checking and status tracking
    - Circuit Breaker: Failure detection and recovery patterns
    - Metrics Collection: Comprehensive performance monitoring
    - Network Discovery: UDP broadcast/multicast server discovery
    - Error Handling: Structured error codes and retry strategies

Design Philosophy:
    Provides production-ready distributed systems infrastructure for MCP
    while maintaining compatibility with the official SDK. Enhances the
    basic protocol implementation with enterprise-grade features.

Key Components:
    - MCPClient: Enhanced client with auth, retry, and multi-transport support
    - MCPServer: Production-ready server with all enterprise features
    - ServiceRegistry: Central registry for server discovery and management
    - ServiceMesh: Intelligent routing and load balancing
    - ServerRegistrar: Automatic server registration and lifecycle management

Service Discovery Features:
    - File-based registry with JSON storage
    - Network discovery via UDP broadcast/multicast
    - Health checking and automatic status updates
    - Capability-based server filtering
    - Load balancing with priority scoring
    - Automatic failover and circuit breaker patterns

Examples:
    Enhanced MCP client with discovery:

    >>> from kailash.mcp_server import get_mcp_client, discover_mcp_servers
    >>> # Discover servers with specific capability
    >>> servers = await discover_mcp_servers(capability="search")
    >>> # Get best client for capability
    >>> client = await get_mcp_client("search")
    >>> result = await client.call_tool(server_config, "search", {"query": "AI"})

    Production MCP server with auto-discovery:

    >>> from kailash.mcp_server import MCPServer, enable_auto_discovery
    >>> from kailash.mcp_server.auth import APIKeyAuth
    >>>
    >>> # Create server with authentication
    >>> auth = APIKeyAuth({"user1": "secret-key"})
    >>> server = MCPServer(
    ...     "my-tools",
    ...     auth_provider=auth,
    ...     enable_metrics=True,
    ...     circuit_breaker_config={"failure_threshold": 5}
    ... )
    >>>
    >>> @server.tool(required_permission="tools.calculate")
    ... def calculate(a: int, b: int) -> int:
    ...     return a + b
    >>>
    >>> # Enable auto-discovery and start
    >>> registrar = enable_auto_discovery(server, enable_network_discovery=True)
    >>> registrar.start_with_registration()

    Service mesh with failover:

    >>> from kailash.mcp_server import ServiceRegistry, ServiceMesh
    >>> registry = ServiceRegistry()
    >>> mesh = ServiceMesh(registry)
    >>>
    >>> # Call with automatic failover
    >>> result = await mesh.call_with_failover(
    ...     "search", "web_search", {"query": "Python"}, max_retries=3
    ... )
"""

# Advanced Features
from .advanced_features import (
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
from .advanced_features import ResourceTemplate as AdvancedResourceTemplate
from .advanced_features import (
    SchemaValidator,
    StreamingHandler,
    StructuredTool,
    ToolAnnotation,
    create_cancellation_context,
    create_progress_reporter,
    structured_tool,
)

# Authentication framework
from .auth import (
    APIKeyAuth,
    AuthManager,
    AuthProvider,
    BasicAuth,
    BearerTokenAuth,
    JWTAuth,
    PermissionManager,
    RateLimiter,
)
from .client import MCPClient

# Service Discovery System
from .discovery import (
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
from .errors import (
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

# OAuth 2.1 Authentication
from .oauth import (
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

# Complete Protocol Implementation
from .protocol import (
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

# Registry Integration
from .registry_integration import (
    NetworkAnnouncer,
    ServerRegistrar,
    enable_auto_discovery,
    register_server_manually,
)

# Enhanced server with production features
from .server import MCPServer, MCPServerBase, SimpleMCPServer

# Enhanced Transport Layer
from .transports import (
    BaseTransport,
    EnhancedStdioTransport,
    SSETransport,
    StreamableHTTPTransport,
    TransportManager,
    TransportSecurity,
    WebSocketTransport,
    get_transport_manager,
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
