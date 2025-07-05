# MCP Transport Layers Guide

*Configure and optimize transport protocols for Model Context Protocol communication*

## Overview

MCP Transport Layers handle the communication protocols between MCP servers and clients. The SDK provides enhanced implementations of all standard MCP transports: STDIO, SSE (Server-Sent Events), HTTP, and WebSocket, with additional security, connection management, and monitoring features.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of network protocols
- Familiarity with async programming concepts

## Transport Types

### Enhanced STDIO Transport

Enhanced process-based communication with proper lifecycle management.

```python
from kailash.mcp_server.transports import EnhancedStdioTransport

# Basic STDIO transport
transport = EnhancedStdioTransport(
    command="python",
    args=["-m", "my_mcp_server"],
    working_directory="/app/servers",
    environment_filter=["PATH", "PYTHONPATH", "HOME"],
    timeout=30.0,
    max_restarts=3
)

# Use transport
async with transport:
    session = await transport.create_session()
    response = await session.send_request("tools.list", {})
    print(f"Available tools: {response}")
```

### Advanced STDIO Configuration

```python
# Production STDIO setup with monitoring
transport = EnhancedStdioTransport(
    command="python",
    args=["-m", "production_server", "--config", "/etc/mcp/config.json"],

    # Process management
    working_directory="/app/mcp-server",
    timeout=60.0,
    max_restarts=5,
    restart_delay=2.0,

    # Environment
    environment_filter=["PATH", "PYTHONPATH", "HOME", "SSL_CERT_DIR"],
    environment_additions={"MCP_LOG_LEVEL": "INFO"},

    # Security
    restrict_filesystem=True,
    allowed_paths=["/app", "/tmp", "/etc/mcp"],

    # Monitoring
    enable_process_monitoring=True,
    memory_limit_mb=1024,
    cpu_limit_percent=80
)

# Handle process events
@transport.on_process_event
async def handle_process_event(event_type: str, data: Dict):
    if event_type == "process_restart":
        logger.warning(f"Server restarted: {data}")
    elif event_type == "resource_limit_exceeded":
        logger.error(f"Resource limit exceeded: {data}")
```

## SSE Transport

Server-Sent Events for real-time streaming communication.

### Basic SSE Setup

```python
from kailash.mcp_server.transports import SSETransport

# SSE transport with authentication
transport = SSETransport(
    base_url="https://api.example.com/mcp",
    auth_header="Bearer your-api-token",
    endpoint_path="/sse",
    validate_origin=True,
    reconnect_interval=5.0,
    max_reconnects=10
)

# Connect and use
async with transport:
    session = await transport.create_session()

    # Send request
    response = await session.send_request("weather.current", {"city": "Seattle"})

    # Handle streaming responses
    async for chunk in session.stream_response():
        print(f"Received: {chunk}")
```

### SSE with Custom Headers and Security

```python
# Advanced SSE configuration
transport = SSETransport(
    base_url="https://secure-api.example.com/mcp",

    # Authentication
    auth_header="Bearer your-jwt-token",
    custom_headers={
        "X-Client-Version": "1.0.0",
        "X-Request-ID": str(uuid.uuid4()),
        "User-Agent": "MyApp/1.0 MCP-Client"
    },

    # Security
    validate_origin=True,
    allowed_origins=["https://myapp.com", "https://secure.myapp.com"],
    verify_ssl=True,
    ssl_context=ssl.create_default_context(),

    # Connection management
    endpoint_path="/mcp/events",
    reconnect_interval=3.0,
    max_reconnects=20,
    heartbeat_interval=30.0,

    # Streaming
    buffer_size=8192,
    max_message_size=1024*1024,  # 1MB
    enable_compression=True
)

# Handle connection events
@transport.on_connection_event
async def handle_connection(event: str, data: Dict):
    if event == "connected":
        print(f"SSE connected: {data['endpoint']}")
    elif event == "disconnected":
        print(f"SSE disconnected, reconnecting...")
    elif event == "error":
        print(f"SSE error: {data['error']}")
```

## StreamableHTTP Transport

HTTP-based transport with session management and streaming support.

### Basic HTTP Setup

```python
from kailash.mcp_server.transports import StreamableHTTPTransport

# HTTP transport with session management
transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",
    endpoint_path="/http",
    session_management=True,
    streaming_threshold=1024,  # Stream responses > 1KB
    timeout=30.0
)

async with transport:
    session = await transport.create_session()

    # Regular request
    response = await session.send_request("analytics.query", {
        "sql": "SELECT COUNT(*) FROM users",
        "format": "json"
    })

    # Streaming request for large data
    large_response = await session.send_streaming_request("data.export", {
        "format": "csv",
        "table": "transactions"
    })

    async for chunk in large_response:
        process_data_chunk(chunk)
```

### Production HTTP Configuration

```python
# Production HTTP transport with full features
transport = StreamableHTTPTransport(
    base_url="https://production-api.example.com/mcp",

    # Endpoints
    endpoint_path="/v1/mcp",
    health_endpoint="/health",

    # Authentication
    auth_provider=BearerTokenAuth("your-production-token"),

    # Session management
    session_management=True,
    session_timeout=300,  # 5 minutes
    max_sessions=10,
    session_cleanup_interval=60,

    # Streaming
    streaming_threshold=4096,  # 4KB
    chunk_size=8192,
    max_response_size=100*1024*1024,  # 100MB
    enable_compression=True,

    # Connection pooling
    connection_pool_size=20,
    max_connections_per_host=5,
    connection_timeout=10.0,

    # Retry and resilience
    max_retries=3,
    retry_delay=1.0,
    retry_backoff_multiplier=2,
    circuit_breaker_enabled=True,

    # Security
    verify_ssl=True,
    ssl_context=create_secure_ssl_context(),
    validate_content_type=True,
    max_redirects=3
)

# Handle streaming with progress
@transport.on_streaming_progress
async def handle_progress(bytes_received: int, total_bytes: Optional[int]):
    if total_bytes:
        percent = (bytes_received / total_bytes) * 100
        print(f"Download progress: {percent:.1f}%")
```

## WebSocket Transport

Real-time bidirectional communication with WebSocket protocol.

### Basic WebSocket Setup

```python
from kailash.mcp_server.transports import WebSocketTransport

# WebSocket transport for real-time communication
transport = WebSocketTransport(
    url="wss://api.example.com/mcp/ws",
    subprotocols=["mcp.v1"],
    auth_header="Bearer your-websocket-token",
    ping_interval=30.0,
    ping_timeout=10.0,
    max_message_size=1024*1024  # 1MB
)

async with transport:
    session = await transport.create_session()

    # Send requests
    response = await session.send_request("realtime.subscribe", {
        "channels": ["notifications", "updates"]
    })

    # Handle real-time messages
    async for message in session.listen():
        if message["type"] == "notification":
            handle_notification(message["data"])
        elif message["type"] == "update":
            handle_update(message["data"])
```

### Advanced WebSocket Features

```python
# Production WebSocket with advanced features
transport = WebSocketTransport(
    url="wss://realtime.example.com/mcp",

    # Protocol configuration
    subprotocols=["mcp.v1", "mcp.realtime"],

    # Authentication
    auth_header="Bearer production-ws-token",
    custom_headers={
        "X-Client-ID": "my-app-client",
        "X-Session-ID": str(uuid.uuid4())
    },

    # Connection management
    ping_interval=20.0,
    ping_timeout=5.0,
    reconnect_interval=3.0,
    max_reconnects=50,

    # Message handling
    max_message_size=10*1024*1024,  # 10MB
    enable_compression=True,
    compression_threshold=1024,

    # Buffering
    send_buffer_size=64*1024,
    receive_buffer_size=64*1024,
    max_pending_messages=100,

    # Security
    verify_ssl=True,
    ssl_context=create_websocket_ssl_context(),
    validate_origin=True,
    allowed_origins=["https://myapp.com"]
)

# Handle connection lifecycle
@transport.on_lifecycle_event
async def handle_lifecycle(event: str, data: Dict):
    if event == "connecting":
        print("Establishing WebSocket connection...")
    elif event == "connected":
        print(f"WebSocket connected: {data['url']}")
        # Subscribe to channels
        await session.send_request("subscribe", {"channels": ["all"]})
    elif event == "disconnected":
        print(f"WebSocket disconnected: {data.get('reason', 'Unknown')}")
    elif event == "error":
        print(f"WebSocket error: {data['error']}")

# Real-time message routing
@transport.route_message("notification")
async def handle_notification(message: Dict):
    """Handle notification messages."""
    print(f"Notification: {message}")

@transport.route_message("data.update")
async def handle_data_update(message: Dict):
    """Handle data update messages."""
    update_local_cache(message["data"])
```

## Transport Security

Comprehensive security features across all transport types.

### SSL/TLS Configuration

```python
import ssl
from kailash.mcp_server.transports import TransportSecurity

# Create secure SSL context
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

# Custom certificate validation
ssl_context.load_verify_locations("/path/to/ca-bundle.crt")

# Configure for HTTP/SSE/WebSocket transports
transport = StreamableHTTPTransport(
    base_url="https://secure-api.example.com/mcp",
    ssl_context=ssl_context,
    verify_ssl=True,
    validate_content_type=True
)
```

### URL and Origin Validation

```python
# Security validation
if TransportSecurity.validate_url("https://api.example.com/mcp"):
    transport = SSETransport(
        base_url="https://api.example.com/mcp",
        validate_origin=True,
        allowed_origins=[
            "https://myapp.com",
            "https://secure.myapp.com",
            "https://admin.myapp.com"
        ]
    )
```

### Authentication Integration

```python
from kailash.mcp_server.auth import APIKeyAuth, JWTAuth

# Different auth methods for different transports
api_key_auth = APIKeyAuth({"client1": "secret-key-1"})
jwt_auth = JWTAuth(secret="jwt-secret", algorithm="HS256")

# HTTP transport with API key
http_transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",
    auth_provider=api_key_auth
)

# WebSocket transport with JWT
ws_transport = WebSocketTransport(
    url="wss://realtime.example.com/mcp",
    auth_provider=jwt_auth
)
```

## Transport Management

Centralized management of multiple transports.

### Transport Manager

```python
from kailash.mcp_server.transports import TransportManager

# Create transport manager
manager = TransportManager(
    default_timeout=30.0,
    max_concurrent_connections=50,
    health_check_interval=60.0,
    enable_metrics=True
)

# Register transports
await manager.register_transport("stdio", EnhancedStdioTransport(
    command="python", args=["-m", "local_server"]
))

await manager.register_transport("sse", SSETransport(
    base_url="https://api.example.com/mcp"
))

await manager.register_transport("ws", WebSocketTransport(
    url="wss://realtime.example.com/mcp"
))

# Use transports through manager
async with manager:
    # Get optimal transport for capability
    transport = await manager.get_transport_for_capability("realtime.updates")
    session = await transport.create_session()

    # Manager handles connection pooling and load balancing
    response = await manager.send_request("stdio", "data.process", {"items": data})
```

### Health Monitoring

```python
# Transport health monitoring
@manager.on_health_event
async def handle_transport_health(transport_name: str, health_data: Dict):
    if health_data["status"] == "unhealthy":
        print(f"Transport {transport_name} is unhealthy: {health_data}")

        # Attempt recovery
        if health_data["error_type"] == "connection_failed":
            await manager.restart_transport(transport_name)
        elif health_data["error_type"] == "auth_expired":
            await manager.refresh_auth(transport_name)

# Get health status
health_report = await manager.get_health_report()
for transport_name, health in health_report.items():
    print(f"{transport_name}: {health['status']} "
          f"(Latency: {health['avg_latency']:.2f}ms)")
```

## Performance Optimization

### Connection Pooling

```python
# HTTP transport with connection pooling
transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",

    # Connection pool settings
    connection_pool_size=20,
    max_connections_per_host=5,
    keep_alive_timeout=300,
    connection_timeout=10.0,

    # Request optimization
    enable_request_pipelining=True,
    max_pipeline_size=10,

    # Compression
    enable_compression=True,
    compression_level=6
)
```

### Streaming Optimization

```python
# Optimized streaming configuration
transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",

    # Streaming thresholds
    streaming_threshold=4096,  # Stream responses > 4KB
    chunk_size=32*1024,        # 32KB chunks
    buffer_size=256*1024,      # 256KB buffer

    # Memory management
    max_response_size=500*1024*1024,  # 500MB max
    enable_response_caching=False,     # Don't cache large responses

    # Performance
    enable_compression=True,
    compression_threshold=1024,
    tcp_nodelay=True,
    tcp_keepalive=True
)
```

## Error Handling and Resilience

### Retry Mechanisms

```python
# Transport with comprehensive retry logic
transport = StreamableHTTPTransport(
    base_url="https://api.example.com/mcp",

    # Retry configuration
    max_retries=5,
    retry_delay=1.0,
    retry_backoff_multiplier=2.0,
    max_retry_delay=30.0,

    # Retry conditions
    retry_on_status_codes=[502, 503, 504, 429],
    retry_on_exceptions=[aiohttp.ClientTimeout, aiohttp.ClientConnectorError],

    # Circuit breaker
    circuit_breaker_enabled=True,
    circuit_breaker_threshold=10,
    circuit_breaker_timeout=60.0
)

# Custom retry logic
@transport.on_retry_attempt
async def handle_retry(attempt: int, error: Exception, delay: float):
    print(f"Retry attempt {attempt} after {delay}s due to: {error}")
```

### Error Recovery

```python
# Comprehensive error handling
@transport.on_error
async def handle_transport_error(error_type: str, error_data: Dict):
    if error_type == "connection_lost":
        # Attempt reconnection
        await transport.reconnect()
    elif error_type == "auth_failed":
        # Refresh authentication
        await transport.refresh_auth()
    elif error_type == "rate_limited":
        # Back off and retry
        await asyncio.sleep(error_data.get("retry_after", 60))
    elif error_type == "server_error":
        # Log and possibly switch to backup transport
        logger.error(f"Server error: {error_data}")
        await manager.switch_to_backup_transport()
```

## Production Deployment

### Load Balancing

```python
# Multiple transports with load balancing
primary_transport = StreamableHTTPTransport(
    base_url="https://primary-api.example.com/mcp"
)

backup_transport = StreamableHTTPTransport(
    base_url="https://backup-api.example.com/mcp"
)

# Manager handles automatic failover
manager = TransportManager(
    load_balancing_strategy="round_robin",
    health_check_interval=30.0,
    failover_threshold=3  # Switch after 3 failures
)

await manager.register_transport("primary", primary_transport, weight=3)
await manager.register_transport("backup", backup_transport, weight=1)
```

### Monitoring and Metrics

```python
# Transport metrics collection
from kailash.mcp_server.transports import TransportMetrics

metrics = TransportMetrics(
    transport_manager=manager,
    export_interval=60,
    exporters=["prometheus", "json"]
)

# Custom metrics
@metrics.histogram("request_duration_by_transport")
async def track_request_duration():
    """Track request duration by transport type."""
    return {
        "transport": transport.transport_type,
        "endpoint": request.endpoint,
        "status": response.status_code
    }

# Performance alerts
@metrics.alert("high_latency")
def high_latency_alert(transport_name: str, avg_latency: float):
    if avg_latency > 1000:  # > 1 second
        send_alert(f"High latency on {transport_name}: {avg_latency:.2f}ms")
```

## Best Practices

### 1. Transport Selection

```python
# Choose transport based on use case
def select_transport(use_case: str) -> BaseTransport:
    if use_case == "local_development":
        return EnhancedStdioTransport(command="python", args=["-m", "dev_server"])
    elif use_case == "real_time_updates":
        return WebSocketTransport(url="wss://realtime.example.com/mcp")
    elif use_case == "large_data_transfer":
        return StreamableHTTPTransport(
            base_url="https://api.example.com/mcp",
            streaming_threshold=1024
        )
    elif use_case == "event_streaming":
        return SSETransport(base_url="https://events.example.com/mcp")
    else:
        return StreamableHTTPTransport(base_url="https://api.example.com/mcp")
```

### 2. Security Configuration

```python
# Production security settings
def create_secure_transport(url: str) -> StreamableHTTPTransport:
    return StreamableHTTPTransport(
        base_url=url,

        # Always verify SSL in production
        verify_ssl=True,
        ssl_context=create_production_ssl_context(),

        # Validate all inputs
        validate_content_type=True,
        validate_origin=True,

        # Use proper authentication
        auth_provider=get_production_auth_provider(),

        # Limit resource usage
        max_response_size=100*1024*1024,
        connection_timeout=30.0,
        max_connections_per_host=10
    )
```

### 3. Resource Management

```python
# Proper resource cleanup
async def use_transport_safely(transport: BaseTransport):
    try:
        async with transport:
            session = await transport.create_session()
            try:
                response = await session.send_request("tool.execute", data)
                return response
            finally:
                await session.close()
    except Exception as e:
        logger.error(f"Transport error: {e}")
        raise
```

## Related Guides

**Prerequisites:**
- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server configuration

**Next Steps:**
- [MCP Advanced Features Guide](27-mcp-advanced-features-guide.md) - Advanced patterns
- [MCP Service Discovery Guide](24-mcp-service-discovery-guide.md) - Service discovery

---

**Configure secure, performant transport layers for production MCP deployments!**
