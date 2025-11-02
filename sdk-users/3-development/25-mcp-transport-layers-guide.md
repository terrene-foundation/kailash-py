# MCP Transport Layers Guide

*Understanding and configuring transport protocols for MCP communication*

## Overview

MCP (Model Context Protocol) supports multiple transport layers for different deployment scenarios and performance requirements. This guide covers HTTP, WebSocket, and stdio transports, their configuration, and best practices for production deployments.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Understanding of network protocols
- Basic knowledge of WebSocket and HTTP concepts

## Transport Types

### HTTP Transport

The most common transport for web-based MCP deployments.

```python
from kailash.mcp_server.transports import HTTPTransport

# Basic HTTP transport
http_transport = HTTPTransport(
    host="0.0.0.0",
    port=8080,
    cors_enabled=True,
    cors_origins=["http://localhost:3000", "https://app.example.com"]
)

# Configure HTTP server
server = MCPServer(
    name="http-server",
    transport=http_transport,
    tools=[weather_tool, calendar_tool]
)

await server.start()
```

### WebSocket Transport

For real-time, bidirectional communication with enterprise connection pooling.

```python
from kailash.mcp_server.transports import WebSocketTransport, WebSocketServerTransport
from kailash.mcp_server import MCPClient

# Client-side WebSocket transport
client = MCPClient(
    connection_pool_config={
        "max_connections": 20,      # Pool up to 20 connections
        "connection_timeout": 30.0, # 30 second timeout
        "pool_cleanup_interval": 300, # Clean up every 5 minutes
        "keep_alive": True          # Keep connections alive
    }
)

# Basic WebSocket connection
async with client:
    result = await client.call_tool(
        "ws://localhost:3001/mcp",
        "search",
        {"query": "WebSocket example"}
    )

# Direct transport configuration
ws_transport = WebSocketTransport(
    url="wss://secure-api.example.com/mcp",
    subprotocols=["mcp-v1"],    # MCP protocol version
    ping_interval=20.0,         # Send ping every 20 seconds
    ping_timeout=10.0,          # Wait 10 seconds for pong
    allow_localhost=False,      # Security: disable localhost in production
    skip_security_validation=False  # Security: always validate URLs
)

# Server-side WebSocket transport
ws_server = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    ping_interval=20.0,
    ping_timeout=10.0,
    max_message_size=10 * 1024 * 1024  # 10MB message limit
)

# Start server
await ws_server.start()
```

### Stdio Transport

For command-line and subprocess integration.

```python
from kailash.mcp_server.transports import StdioTransport

# Stdio transport for CLI integration
stdio_transport = StdioTransport(
    buffer_size=8192,
    line_buffered=True,
    encoding="utf-8"
)

# Perfect for command-line tools
server = MCPServer(
    name="cli-server",
    transport=stdio_transport,
    tools=[file_tool, git_tool]
)
```

## Transport Configuration

### Performance Tuning

```python
# High-performance HTTP configuration
high_perf_transport = HTTPTransport(
    host="0.0.0.0",
    port=8080,
    worker_processes=4,
    max_connections=1000,
    keep_alive_timeout=30,
    request_timeout=60,
    enable_compression=True
)

# Connection pooling for clients
from kailash.mcp_server.client import MCPClient

client = MCPClient(
    transport_url="http://localhost:8080",
    connection_pool_size=10,
    max_retries=3,
    timeout=30
)
```

### Security Configuration

```python
# HTTPS transport with certificates
from kailash.mcp_server.transports import HTTPSTransport

https_transport = HTTPSTransport(
    host="0.0.0.0",
    port=8443,
    ssl_cert_file="/etc/ssl/certs/server.crt",
    ssl_key_file="/etc/ssl/private/server.key",
    ssl_ca_file="/etc/ssl/certs/ca.crt",
    verify_client_cert=True
)

# WebSocket Secure (WSS)
wss_transport = WebSocketTransport(
    host="0.0.0.0",
    port=8444,
    ssl_context=ssl_context,
    auth_handler=jwt_auth_handler
)
```

## Load Balancing

### Multiple Transport Endpoints

```python
from kailash.mcp_server.load_balancer import TransportLoadBalancer

# Create load balancer with multiple transports
load_balancer = TransportLoadBalancer(
    strategy="round_robin",  # or "least_connections", "weighted"
    health_check_interval=30
)

# Add transport endpoints
load_balancer.add_transport("http://server1:8080", weight=2)
load_balancer.add_transport("http://server2:8080", weight=1)
load_balancer.add_transport("ws://server3:8081", weight=1)

# Client automatically uses load balancer
client = MCPClient(load_balancer=load_balancer)
```

## Transport Middleware

### Request/Response Interceptors

```python
from kailash.mcp_server.middleware import TransportMiddleware

class LoggingMiddleware(TransportMiddleware):
    async def before_request(self, request):
        logger.info(f"Incoming request: {request.method} {request.path}")
        return request

    async def after_response(self, response):
        logger.info(f"Outgoing response: {response.status_code}")
        return response

# Apply middleware to transport
http_transport.add_middleware(LoggingMiddleware())
http_transport.add_middleware(RateLimitMiddleware(max_requests=100))
```

## WebSocket Transport Deep Dive

### Connection Pooling Architecture

The Kailash MCP client provides enterprise-grade WebSocket connection pooling that dramatically improves performance for applications making multiple MCP calls.

```python
from kailash.mcp_server import MCPClient
import asyncio

# Configure connection pooling
client = MCPClient(
    connection_pool_config={
        "max_connections": 50,        # Maximum pooled connections per URL
        "connection_timeout": 30.0,   # Connection establishment timeout
        "pool_cleanup_interval": 300, # Clean up stale connections every 5 minutes
        "keep_alive": True,           # Maintain persistent connections
        "ping_interval": 20.0         # WebSocket ping/pong heartbeat
    },
    enable_metrics=True  # Track pool performance
)

async def demonstrate_pooling():
    async with client:
        # First call to a URL creates a new connection
        result1 = await client.call_tool(
            "wss://api.example.com/mcp",
            "search",
            {"query": "machine learning"}
        )

        # Second call to the same URL reuses the pooled connection (faster!)
        result2 = await client.call_tool(
            "wss://api.example.com/mcp",
            "analyze",
            {"text": result1["content"]}
        )

        # Different URL creates a separate pooled connection
        result3 = await client.call_tool(
            "wss://nlp.example.com/mcp",
            "sentiment",
            {"text": "This is amazing!"}
        )

        # Check pool efficiency
        metrics = client.get_metrics()
        print(f"Pool hits: {metrics.get('websocket_pool_hits', 0)}")
        print(f"Pool misses: {metrics.get('websocket_pool_misses', 0)}")
        print(f"Pool efficiency: {metrics.get('websocket_pool_hits', 0) / max(1, metrics.get('websocket_pool_misses', 0))}")

# Run the demonstration
asyncio.run(demonstrate_pooling())
```

### WebSocket Security Configuration

WebSocket transport includes comprehensive security features:

```python
from kailash.mcp_server.transports import WebSocketTransport
from kailash.mcp_server.errors import TransportError

# Production security configuration
production_transport = WebSocketTransport(
    url="wss://secure-api.example.com/mcp",

    # Security settings
    allow_localhost=False,           # Block localhost connections
    skip_security_validation=False,  # Always validate URLs

    # Connection settings
    ping_interval=30.0,             # Heartbeat every 30 seconds
    ping_timeout=10.0,              # Fail if no pong within 10 seconds
    subprotocols=["mcp-v1"],        # Specific MCP protocol version

    # Size limits
    max_message_size=5 * 1024 * 1024  # 5MB message limit
)

# Development/testing configuration (less restrictive)
dev_transport = WebSocketTransport(
    url="ws://localhost:3001/mcp",
    allow_localhost=True,            # Allow localhost for development
    skip_security_validation=True,   # Skip URL validation for testing
    ping_interval=10.0,              # More frequent pings for development
    ping_timeout=5.0
)

# Validate configuration before use
try:
    await production_transport.connect()
    print("Production transport connected securely")
except TransportError as e:
    print(f"Security validation failed: {e}")
```

### Advanced WebSocket Error Handling

```python
from kailash.mcp_server.errors import TransportError, ConnectionError
import asyncio
import logging

logger = logging.getLogger(__name__)

async def resilient_websocket_client():
    """Demonstrate robust WebSocket error handling with automatic retry."""

    client = MCPClient(
        connection_pool_config={"max_connections": 10},
        retry_strategy="exponential"  # Built-in exponential backoff
    )

    max_retries = 3
    retry_delay = 1.0

    for attempt in range(max_retries):
        try:
            async with client:
                result = await client.call_tool(
                    "wss://unreliable-api.example.com/mcp",
                    "process",
                    {"data": "important task"}
                )
                return result

        except ConnectionError as e:
            logger.warning(f"WebSocket connection failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                continue
            else:
                logger.error("Max retries exceeded for WebSocket connection")
                raise

        except TransportError as e:
            if "websocket" in str(e).lower():
                logger.error(f"WebSocket transport error: {e}")
                # Clear any stale connections from pool
                await client._clear_connection_pools()
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
            raise

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

# Usage
try:
    result = await resilient_websocket_client()
    print(f"Success: {result}")
except Exception as e:
    print(f"Failed after all retries: {e}")
```

### Performance Monitoring & Optimization

```python
import time
import asyncio
from kailash.mcp_server import MCPClient

async def websocket_performance_analysis():
    """Analyze WebSocket connection pool performance."""

    client = MCPClient(
        connection_pool_config={
            "max_connections": 20,
            "connection_timeout": 30.0,
            "pool_cleanup_interval": 60  # More frequent cleanup for analysis
        },
        enable_metrics=True
    )

    async with client:
        # Warm up the connection pool
        await client.call_tool("ws://api.example.com/mcp", "ping", {})

        # Measure pooled vs non-pooled performance
        start_time = time.time()

        # Make multiple calls (should use pooled connections after first)
        tasks = []
        for i in range(10):
            task = client.call_tool(
                "ws://api.example.com/mcp",
                "quick_task",
                {"id": i}
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time

        # Analyze metrics
        metrics = client.get_metrics()
        pool_hits = metrics.get('websocket_pool_hits', 0)
        pool_misses = metrics.get('websocket_pool_misses', 0)
        total_calls = pool_hits + pool_misses

        print(f"Performance Analysis:")
        print(f"  Total calls: {total_calls}")
        print(f"  Pool hits: {pool_hits} ({pool_hits/total_calls*100:.1f}%)")
        print(f"  Pool misses: {pool_misses} ({pool_misses/total_calls*100:.1f}%)")
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Average time per call: {elapsed/total_calls:.3f}s")
        print(f"  Active pooled connections: {len(client._websocket_pools)}")

# Run performance analysis
asyncio.run(websocket_performance_analysis())
```

## Error Handling

### Transport-Specific Error Handling

```python
from kailash.mcp_server.errors import TransportError, ConnectionError

class RobustMCPServer(MCPServer):
    async def handle_transport_error(self, error: TransportError):
        if isinstance(error, ConnectionError):
            # Attempt reconnection
            await self.reconnect_transport()
        else:
            # Log error and continue
            logger.error(f"Transport error: {error}")

    async def reconnect_transport(self):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                await self.transport.reconnect()
                logger.info("Transport reconnected successfully")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to reconnect after max retries")
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Monitoring and Metrics

### Transport Metrics Collection

```python
from kailash.mcp_server.monitoring import TransportMetrics

# Enable metrics collection
metrics = TransportMetrics(
    collect_request_duration=True,
    collect_response_size=True,
    collect_connection_stats=True
)

http_transport.enable_metrics(metrics)

# Access metrics
stats = await metrics.get_stats()
print(f"Average request duration: {stats.avg_request_duration}ms")
print(f"Active connections: {stats.active_connections}")
print(f"Total requests: {stats.total_requests}")
```

## Production Deployment

### Docker Configuration

```yaml
# docker-compose.yml for MCP server cluster
version: '3.8'
services:
  mcp-server-1:
    image: myapp/mcp-server
    ports:
      - "8080:8080"
    environment:
      - TRANSPORT_TYPE=http
      - TRANSPORT_PORT=8080
      - SERVER_NAME=mcp-server-1

  mcp-server-2:
    image: myapp/mcp-server
    ports:
      - "8081:8081"
    environment:
      - TRANSPORT_TYPE=websocket
      - TRANSPORT_PORT=8081
      - SERVER_NAME=mcp-server-2

  nginx-lb:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - mcp-server-1
      - mcp-server-2
```

### Kubernetes Deployment

```yaml
# mcp-transport-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: mcp-transport-service
spec:
  selector:
    app: mcp-server
  ports:
    - name: http
      port: 80
      targetPort: 8080
    - name: websocket
      port: 8081
      targetPort: 8081
  type: LoadBalancer

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: myapp/mcp-server:latest
        ports:
        - containerPort: 8080
        - containerPort: 8081
        env:
        - name: TRANSPORT_HTTP_PORT
          value: "8080"
        - name: TRANSPORT_WS_PORT
          value: "8081"
```

## Best Practices

### Transport Selection Guidelines

1. **HTTP Transport**: Best for stateless, request/response patterns
2. **WebSocket Transport**: Best for real-time, bidirectional communication
3. **Stdio Transport**: Best for CLI tools and subprocess integration

### Performance Optimization

```python
# Optimize for high throughput
high_throughput_config = {
    "worker_processes": os.cpu_count(),
    "max_connections": 2000,
    "connection_pool_size": 50,
    "request_timeout": 30,
    "keep_alive_timeout": 60,
    "enable_compression": True,
    "compression_level": 1  # Fast compression
}

# Optimize for low latency
low_latency_config = {
    "worker_processes": 1,
    "max_connections": 100,
    "connection_pool_size": 10,
    "request_timeout": 5,
    "keep_alive_timeout": 5,
    "enable_compression": False,
    "tcp_nodelay": True
}
```

## Troubleshooting

### Common Transport Issues

1. **Connection Timeouts**: Increase timeout values or check network
2. **SSL Certificate Errors**: Verify certificate paths and validity
3. **Port Conflicts**: Ensure ports are available and not blocked
4. **CORS Issues**: Configure cors_origins properly for web clients

### Debug Mode

```python
# Enable debug mode for transport issues
transport = HTTPTransport(
    host="0.0.0.0",
    port=8080,
    debug=True,
    log_level="DEBUG"
)

# Debug WebSocket connections
ws_transport = WebSocketTransport(
    host="0.0.0.0",
    port=8081,
    debug=True,
    log_connections=True,
    log_messages=True
)
```

## See Also

- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server setup and configuration
- [MCP Service Discovery Guide](24-mcp-service-discovery-guide.md) - Service discovery and registration
- [MCP Advanced Features Guide](27-mcp-advanced-features-guide.md) - Advanced MCP capabilities
