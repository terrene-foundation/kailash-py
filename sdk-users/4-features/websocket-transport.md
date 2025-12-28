# WebSocket Transport for MCP

*Enterprise-grade WebSocket transport with connection pooling, error handling, and security features*

## Overview

The Kailash SDK provides a production-ready WebSocket transport implementation for the Model Context Protocol (MCP) that extends beyond basic WebSocket support to include enterprise features like connection pooling, automatic error recovery, and comprehensive security validation.

## Key Features

- **Enterprise Connection Pooling** - Automatic connection reuse for improved performance
- **Automatic Error Recovery** - Built-in retry logic and connection healing
- **Security Validation** - URL validation and configurable security checks
- **Performance Monitoring** - Built-in metrics and pool efficiency tracking
- **Production Ready** - Designed for high-throughput enterprise deployments

## Quick Start

### Basic WebSocket Client

```python
from kailash.mcp_server import MCPClient

# Simple WebSocket connection
client = MCPClient()

async with client:
    # Automatically detects WebSocket URLs and uses appropriate transport
    result = await client.call_tool(
        "ws://localhost:3001/mcp",
        "search",
        {"query": "WebSocket transport"}
    )
    print(f"Result: {result}")
```

### WebSocket with Connection Pooling

```python
from kailash.mcp_server import MCPClient

# Configure enterprise connection pooling
client = MCPClient(
    connection_pool_config={
        "max_connections": 20,        # Pool up to 20 connections per URL
        "connection_timeout": 30.0,   # 30 second connection timeout
        "pool_cleanup_interval": 300, # Clean up every 5 minutes
        "keep_alive": True            # Maintain persistent connections
    },
    enable_metrics=True  # Track pool performance
)

async with client:
    # First call creates and pools connection
    result1 = await client.call_tool("ws://api.example.com/mcp", "task1", {"data": "test"})

    # Second call reuses pooled connection (much faster!)
    result2 = await client.call_tool("ws://api.example.com/mcp", "task2", {"data": "test"})

    # Check pool efficiency
    metrics = client.get_metrics()
    print(f"Pool hits: {metrics.get('websocket_pool_hits', 0)}")
    print(f"Pool efficiency: {metrics.get('websocket_pool_hits', 0) / max(1, metrics.get('websocket_pool_misses', 0)) * 100:.1f}%")
```

## Connection Pooling Deep Dive

### Pool Configuration

```python
from kailash.mcp_server import MCPClient

client = MCPClient(
    connection_pool_config={
        # Core pooling settings
        "max_connections": 50,        # Maximum pooled connections (per URL)
        "connection_timeout": 30.0,   # How long to wait for connection establishment
        "pool_cleanup_interval": 300, # How often to clean up stale connections (seconds)

        # Connection management
        "keep_alive": True,           # Keep connections alive between requests
        "ping_interval": 20.0,        # WebSocket ping frequency (seconds)
        "ping_timeout": 10.0,         # How long to wait for pong response

        # Performance tuning
        "max_idle_time": 600,         # Close connections idle for 10+ minutes
        "connection_retry_delay": 1.0, # Delay between connection attempts
        "enable_compression": True     # Enable WebSocket compression
    }
)
```

### Pool Performance Analysis

```python
import asyncio
import time
from kailash.mcp_server import MCPClient

async def analyze_pool_performance():
    """Demonstrate connection pool performance benefits."""

    # Client with pooling enabled
    pooled_client = MCPClient(
        connection_pool_config={"max_connections": 10},
        enable_metrics=True
    )

    # Client without pooling (for comparison)
    non_pooled_client = MCPClient(
        connection_pool_config={"max_connections": 0},  # Disable pooling
        enable_metrics=True
    )

    url = "ws://localhost:3001/mcp"
    calls = 10

    # Test with pooling
    async with pooled_client:
        start_time = time.time()
        tasks = [pooled_client.call_tool(url, "test", {"id": i}) for i in range(calls)]
        await asyncio.gather(*tasks)
        pooled_time = time.time() - start_time

    # Test without pooling
    async with non_pooled_client:
        start_time = time.time()
        tasks = [non_pooled_client.call_tool(url, "test", {"id": i}) for i in range(calls)]
        await asyncio.gather(*tasks)
        non_pooled_time = time.time() - start_time

    # Performance comparison
    improvement = ((non_pooled_time - pooled_time) / non_pooled_time) * 100
    print(f"Performance Improvement with Pooling:")
    print(f"  Without pooling: {non_pooled_time:.2f}s")
    print(f"  With pooling: {pooled_time:.2f}s")
    print(f"  Improvement: {improvement:.1f}% faster")

# Run analysis
asyncio.run(analyze_pool_performance())
```

## Security Features

### Production Security Configuration

```python
from kailash.mcp_server.transports import WebSocketTransport
from kailash.mcp_server import MCPClient

# Secure production configuration
secure_client = MCPClient()
transport = WebSocketTransport(
    url="wss://secure-api.example.com/mcp",  # Always use wss:// in production

    # Security settings
    allow_localhost=False,           # Block localhost connections
    skip_security_validation=False,  # Always validate URLs

    # Connection security
    subprotocols=["mcp-v1"],        # Specific protocol version
    ping_interval=30.0,             # Heartbeat every 30 seconds
    ping_timeout=10.0,              # Fail fast on connection issues

    # Message limits
    max_message_size=5 * 1024 * 1024,  # 5MB message limit
)

# Use the secure transport
await transport.connect()
```

### Development vs Production Settings

```python
# Development configuration (more permissive)
dev_config = {
    "url": "ws://localhost:3001/mcp",
    "allow_localhost": True,          # OK for development
    "skip_security_validation": True, # Skip validation for testing
    "ping_interval": 5.0,            # Frequent pings for quick feedback
    "ping_timeout": 2.0
}

# Production configuration (secure)
prod_config = {
    "url": "wss://api.company.com/mcp",
    "allow_localhost": False,         # Block localhost
    "skip_security_validation": False, # Always validate
    "ping_interval": 30.0,           # Less frequent pings
    "ping_timeout": 10.0,            # Reasonable timeout
    "max_message_size": 1024 * 1024   # 1MB limit
}
```

## Error Handling & Resilience

### Automatic Error Recovery

```python
from kailash.mcp_server import MCPClient
from kailash.mcp_server.errors import TransportError, ConnectionError
import asyncio
import logging

logger = logging.getLogger(__name__)

async def resilient_websocket_calls():
    """Demonstrate built-in error recovery."""

    client = MCPClient(
        retry_strategy="exponential",  # Built-in exponential backoff
        connection_pool_config={"max_connections": 5}
    )

    try:
        async with client:
            # This will automatically retry on connection failures
            result = await client.call_tool(
                "wss://sometimes-unreliable.example.com/mcp",
                "important_task",
                {"data": "critical_operation"}
            )
            return result

    except ConnectionError as e:
        logger.error(f"Connection failed after retries: {e}")
        # Pool automatically clears bad connections

    except TransportError as e:
        logger.error(f"Transport error: {e}")
        # Handle specific transport issues
```

### Custom Error Handling

```python
async def custom_error_handling():
    """Implement custom error handling logic."""

    client = MCPClient(enable_metrics=True)
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            async with client:
                result = await client.call_tool(
                    "ws://api.example.com/mcp",
                    "sensitive_operation",
                    {"data": "important"}
                )
                return result

        except TransportError as e:
            if "websocket" in str(e).lower():
                logger.warning(f"WebSocket error (attempt {attempt + 1}): {e}")

                # Clear stale connections for this URL
                await client._remove_connection_from_pool(url)

                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
            raise

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    raise Exception("Max retries exceeded")
```

## Performance Monitoring

### Built-in Metrics

```python
from kailash.mcp_server import MCPClient
import json

# Enable comprehensive metrics
client = MCPClient(
    connection_pool_config={"max_connections": 20},
    enable_metrics=True
)

async with client:
    # Make some WebSocket calls
    for i in range(5):
        await client.call_tool(f"ws://api{i%2}.example.com/mcp", "test", {"id": i})

    # Analyze metrics
    metrics = client.get_metrics()

    print("WebSocket Performance Metrics:")
    print(f"  Pool hits: {metrics.get('websocket_pool_hits', 0)}")
    print(f"  Pool misses: {metrics.get('websocket_pool_misses', 0)}")
    print(f"  Active connections: {len(client._websocket_pools)}")
    print(f"  Total bytes sent: {metrics.get('bytes_sent', 0)}")
    print(f"  Total bytes received: {metrics.get('bytes_received', 0)}")
    print(f"  Connection errors: {metrics.get('connection_errors', 0)}")

    # Pool efficiency calculation
    hits = metrics.get('websocket_pool_hits', 0)
    misses = metrics.get('websocket_pool_misses', 0)
    if hits + misses > 0:
        efficiency = (hits / (hits + misses)) * 100
        print(f"  Pool efficiency: {efficiency:.1f}%")
```

### Custom Metrics Collection

```python
import time
from collections import defaultdict

class WebSocketMetricsCollector:
    """Custom metrics collector for WebSocket operations."""

    def __init__(self):
        self.metrics = defaultdict(int)
        self.timings = defaultdict(list)

    async def timed_call(self, client, url, tool, params):
        """Make a timed WebSocket call with metrics collection."""
        start_time = time.time()

        try:
            result = await client.call_tool(url, tool, params)

            # Record success metrics
            duration = time.time() - start_time
            self.timings[url].append(duration)
            self.metrics[f"{url}_success"] += 1
            self.metrics["total_success"] += 1

            return result

        except Exception as e:
            # Record error metrics
            self.metrics[f"{url}_error"] += 1
            self.metrics["total_errors"] += 1
            raise

    def get_summary(self):
        """Get performance summary."""
        summary = {"metrics": dict(self.metrics)}

        # Calculate timing statistics
        for url, times in self.timings.items():
            if times:
                summary[f"{url}_avg_time"] = sum(times) / len(times)
                summary[f"{url}_min_time"] = min(times)
                summary[f"{url}_max_time"] = max(times)

        return summary

# Usage
collector = WebSocketMetricsCollector()
client = MCPClient(connection_pool_config={"max_connections": 10})

async with client:
    # Make monitored calls
    for i in range(10):
        url = f"ws://api{i%3}.example.com/mcp"
        await collector.timed_call(client, url, "test", {"id": i})

    # Print performance summary
    summary = collector.get_summary()
    print(json.dumps(summary, indent=2))
```

## Production Deployment

### Load Balancer Configuration

```nginx
# nginx.conf for WebSocket load balancing
upstream websocket_mcp_servers {
    server mcp-server-1:3001;
    server mcp-server-2:3001;
    server mcp-server-3:3001;
}

server {
    listen 443 ssl;
    server_name api.company.com;

    # SSL configuration
    ssl_certificate /etc/ssl/certs/api.company.com.crt;
    ssl_certificate_key /etc/ssl/private/api.company.com.key;

    # WebSocket proxy configuration
    location /mcp {
        proxy_pass http://websocket_mcp_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket specific timeouts
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 60s;
    }
}
```

### Docker Deployment

```yaml
# docker-compose.yml for WebSocket MCP servers
version: '3.8'

services:
  mcp-server-1:
    image: company/mcp-server:latest
    ports:
      - "3001:3001"
    environment:
      - SERVER_ID=mcp-server-1
      - TRANSPORT_TYPE=websocket
      - WEBSOCKET_HOST=0.0.0.0
      - WEBSOCKET_PORT=3001
      - MAX_MESSAGE_SIZE=10485760  # 10MB
      - PING_INTERVAL=30
      - PING_TIMEOUT=10
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  mcp-server-2:
    image: company/mcp-server:latest
    ports:
      - "3002:3001"
    environment:
      - SERVER_ID=mcp-server-2
      - TRANSPORT_TYPE=websocket
      - WEBSOCKET_HOST=0.0.0.0
      - WEBSOCKET_PORT=3001
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3001/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx-lb:
    image: nginx:alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl
    depends_on:
      - mcp-server-1
      - mcp-server-2
```

## Troubleshooting

### Common WebSocket Issues

```python
import asyncio
import websockets
from kailash.mcp_server import MCPClient
from kailash.mcp_server.errors import TransportError

async def diagnose_websocket_issues():
    """Comprehensive WebSocket diagnostics."""

    print("=== WebSocket Diagnostic Tool ===")

    # Test 1: Basic connectivity
    url = "ws://localhost:3001"
    print(f"\n1. Testing basic connectivity to {url}")

    try:
        async with websockets.connect(url, ping_interval=None) as ws:
            await ws.send('{"method": "ping"}')
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"   ✅ Basic WebSocket connectivity works: {response[:50]}...")
    except Exception as e:
        print(f"   ❌ Basic connectivity failed: {e}")

    # Test 2: MCP client connectivity
    print(f"\n2. Testing MCP client connectivity")
    try:
        client = MCPClient()
        async with client:
            result = await client.discover_tools(url)
            print(f"   ✅ MCP client connectivity works: found {len(result)} tools")
    except TransportError as e:
        if "Unsupported transport: websocket" in str(e):
            print(f"   ❌ WebSocket transport not supported: {e}")
        else:
            print(f"   ⚠️  Transport error (may be server issue): {e}")
    except Exception as e:
        print(f"   ⚠️  Connection error (may be server down): {e}")

    # Test 3: Connection pooling
    print(f"\n3. Testing connection pooling")
    try:
        client = MCPClient(
            connection_pool_config={"max_connections": 5},
            enable_metrics=True
        )
        async with client:
            # Make multiple calls to same URL
            for i in range(3):
                await client.call_tool(url, "ping", {"id": i})

            metrics = client.get_metrics()
            hits = metrics.get('websocket_pool_hits', 0)
            misses = metrics.get('websocket_pool_misses', 0)

            if hits > 0:
                print(f"   ✅ Connection pooling works: {hits} hits, {misses} misses")
            else:
                print(f"   ⚠️  Pooling may not be working: {hits} hits, {misses} misses")

    except Exception as e:
        print(f"   ❌ Pooling test failed: {e}")

    # Test 4: Security validation
    print(f"\n4. Testing security validation")
    try:
        client = MCPClient()
        # This should fail with security validation
        await client.discover_tools("ws://malicious-site.com/mcp")
        print(f"   ⚠️  Security validation may be disabled")
    except TransportError as e:
        if "Invalid or unsafe URL" in str(e):
            print(f"   ✅ Security validation working: {e}")
        else:
            print(f"   ⚠️  Unexpected security error: {e}")
    except Exception as e:
        print(f"   ⚠️  Security test inconclusive: {e}")

# Run diagnostics
asyncio.run(diagnose_websocket_issues())
```

### Performance Troubleshooting

```python
async def websocket_performance_troubleshooting():
    """Identify WebSocket performance issues."""

    client = MCPClient(
        connection_pool_config={"max_connections": 10},
        enable_metrics=True
    )

    print("=== WebSocket Performance Analysis ===")

    async with client:
        # Baseline test
        url = "ws://localhost:3001/mcp"
        start_time = time.time()

        await client.call_tool(url, "ping", {})
        first_call_time = time.time() - start_time

        # Pooled call test
        start_time = time.time()
        await client.call_tool(url, "ping", {})
        second_call_time = time.time() - start_time

        print(f"First call (creates connection): {first_call_time:.3f}s")
        print(f"Second call (uses pool): {second_call_time:.3f}s")

        if second_call_time < first_call_time * 0.5:
            print("✅ Connection pooling is working effectively")
        elif second_call_time < first_call_time * 0.8:
            print("⚠️  Connection pooling has moderate benefit")
        else:
            print("❌ Connection pooling may not be working")
            print("   Check: server keeps connections alive, network latency")

        # Pool efficiency check
        metrics = client.get_metrics()
        hits = metrics.get('websocket_pool_hits', 0)
        misses = metrics.get('websocket_pool_misses', 0)

        if hits + misses > 0:
            efficiency = (hits / (hits + misses)) * 100
            print(f"Pool efficiency: {efficiency:.1f}%")

            if efficiency > 50:
                print("✅ Good pool efficiency")
            else:
                print("⚠️  Low pool efficiency - consider tuning pool settings")

# Run performance analysis
asyncio.run(websocket_performance_troubleshooting())
```

## Best Practices

### 1. Connection Pool Sizing
```python
# For high-throughput applications
high_throughput_config = {
    "max_connections": 50,     # Scale based on concurrent needs
    "connection_timeout": 15.0, # Shorter timeout for faster failover
    "pool_cleanup_interval": 120, # More frequent cleanup
}

# For low-latency applications
low_latency_config = {
    "max_connections": 20,     # Fewer connections, more reuse
    "connection_timeout": 30.0, # Longer timeout for stability
    "keep_alive": True,        # Keep connections warm
    "ping_interval": 10.0      # Frequent heartbeat
}
```

### 2. Security Hardening
```python
# Production security checklist
production_transport = WebSocketTransport(
    url="wss://api.company.com/mcp",  # ✅ Always use wss:// in production
    allow_localhost=False,            # ✅ Block localhost
    skip_security_validation=False,   # ✅ Always validate URLs
    max_message_size=1024*1024,       # ✅ Limit message size
    ping_timeout=10.0,                # ✅ Fail fast on issues
    subprotocols=["mcp-v1"]           # ✅ Specific protocol version
)
```

### 3. Error Handling Strategy
```python
# Implement comprehensive error handling
async def robust_websocket_client():
    client = MCPClient(
        retry_strategy="exponential",
        connection_pool_config={"max_connections": 10}
    )

    try:
        async with client:
            return await client.call_tool(url, tool, params)
    except ConnectionError:
        # Connection failed - clear pool and retry
        await client._clear_connection_pools()
        raise
    except TransportError as e:
        if "websocket" in str(e).lower():
            # WebSocket specific error
            logger.error(f"WebSocket transport error: {e}")
        raise
```

### 4. Monitoring Integration
```python
# Production monitoring setup
import prometheus_client

# Custom metrics
websocket_pool_efficiency = prometheus_client.Gauge('websocket_pool_efficiency_percent')
websocket_active_connections = prometheus_client.Gauge('websocket_active_connections')

async def update_metrics(client):
    """Update Prometheus metrics."""
    metrics = client.get_metrics()

    hits = metrics.get('websocket_pool_hits', 0)
    misses = metrics.get('websocket_pool_misses', 0)

    if hits + misses > 0:
        efficiency = (hits / (hits + misses)) * 100
        websocket_pool_efficiency.set(efficiency)

    websocket_active_connections.set(len(client._websocket_pools))
```

## Related Documentation

- [MCP Transport Layers Guide](../3-development/25-mcp-transport-layers-guide.md) - Comprehensive transport configuration
- [MCP Integration Guide](../4-features/mcp/README.md) - Complete MCP feature overview
- [Enterprise Deployment Patterns](../5-enterprise/production-patterns.md) - Production deployment strategies
- [Performance Optimization Guide](../3-development/04-production.md) - Performance tuning guidelines
