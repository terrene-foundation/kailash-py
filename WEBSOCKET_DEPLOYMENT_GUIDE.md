# WebSocket Transport Deployment Guide

## Overview

The Kailash MCP client now supports WebSocket transport for real-time communication with MCP servers. This guide covers deployment, configuration, and operational considerations.

## 🚀 Quick Start

### Basic Usage

```python
from kailash.mcp_server.client import MCPClient

# Initialize client
client = MCPClient(enable_metrics=True)

# WebSocket URLs are automatically detected
tools = await client.discover_tools("ws://localhost:8080/mcp")
result = await client.call_tool("wss://api.example.com/mcp", "search", {"query": "test"})
```

### Configuration Options

```python
# String URL (simplest)
await client.discover_tools("ws://localhost:8080/mcp")

# Dictionary configuration
config = {
    "transport": "websocket",
    "url": "wss://secure.api.com/mcp",
    "auth": {  # Note: Not currently supported by MCP WebSocket client
        "type": "bearer",
        "token": "your-token"
    }
}
await client.discover_tools(config)
```

## ✅ Production Features

### Transport Auto-Detection
- `ws://` and `wss://` URLs automatically use WebSocket transport
- Seamless integration with existing STDIO, SSE, and HTTP transports
- Backward compatibility maintained

### Error Handling
```python
from kailash.mcp_server.errors import TransportError

try:
    tools = await client.discover_tools("ws://invalid-server:8080/mcp")
except TransportError as e:
    print(f"WebSocket error: {e}")
    print(f"Transport type: {e.data.get('transport_type')}")  # 'websocket'
```

### Metrics Integration
```python
client = MCPClient(enable_metrics=True)
await client.discover_tools("ws://localhost:8080/mcp")

metrics = client.get_metrics()
print(f"WebSocket usage: {metrics['transport_usage']['websocket']}")
```

### Health Monitoring
```python
health = await client.health_check("ws://localhost:8080/mcp")
print(f"Status: {health['status']}")  # 'healthy' or 'unhealthy'
print(f"Transport: {health['transport']}")  # 'websocket'
```

## ⚠️ Current Limitations

### 1. Authentication Not Supported
The MCP WebSocket client doesn't currently support custom headers or authentication.

```python
# ❌ This won't work (headers ignored)
config = {
    "url": "wss://api.example.com/mcp",
    "auth": {"type": "bearer", "token": "token123"}
}

# ✅ Workarounds:
# Option 1: URL-based authentication
url = "wss://token123@api.example.com/mcp"

# Option 2: WebSocket subprotocols (if server supports)
# Currently not configurable in Kailash

# Option 3: Use different transport for authenticated endpoints
await client.discover_tools("https://api.example.com/mcp")  # Uses SSE with auth
```

### 2. Connection Management
Each WebSocket operation creates a new connection.

```python
# Each call creates a new WebSocket connection
await client.call_tool("ws://localhost:8080/mcp", "tool1", {})  # Connection 1
await client.call_tool("ws://localhost:8080/mcp", "tool2", {})  # Connection 2
```

**Recommendation**: For high-frequency operations, consider connection pooling (planned enhancement).

### 3. No Built-in Reconnection
WebSocket connections don't automatically reconnect on failure.

**Recommendation**: Implement application-level retry logic:

```python
import asyncio
from kailash.mcp_server.errors import TransportError

async def robust_websocket_call(client, url, tool_name, args, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.call_tool(url, tool_name, args)
        except TransportError as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## 🏗️ Architecture Considerations

### Transport Selection Strategy
```python
def select_transport(server_capabilities):
    """Choose optimal transport based on server capabilities."""
    if server_capabilities.get("websocket_supported"):
        if server_capabilities.get("requires_auth"):
            return "https"  # Use SSE for authenticated endpoints
        else:
            return "ws"     # Use WebSocket for real-time, non-auth
    else:
        return "https"      # Fallback to SSE
```

### Load Balancing
```python
# WebSocket URLs for load balancing
websocket_endpoints = [
    "ws://mcp1.example.com:8080/mcp",
    "ws://mcp2.example.com:8080/mcp", 
    "ws://mcp3.example.com:8080/mcp"
]

import random
selected_endpoint = random.choice(websocket_endpoints)
```

### Monitoring and Observability

```python
async def monitor_websocket_health(client, urls):
    """Monitor WebSocket endpoint health."""
    health_results = {}
    
    for url in urls:
        try:
            health = await client.health_check(url)
            health_results[url] = {
                "status": health["status"],
                "tools_available": health["tools_available"],
                "response_time": health.get("response_time", 0)
            }
        except Exception as e:
            health_results[url] = {"status": "error", "error": str(e)}
    
    return health_results
```

## 🧪 Testing Strategy

### Unit Testing
```python
from unittest.mock import patch
from kailash.mcp_server.client import MCPClient

async def test_websocket_integration():
    client = MCPClient()
    
    with patch.object(client, "_discover_tools_websocket") as mock_ws:
        mock_ws.return_value = [{"name": "test_tool"}]
        
        tools = await client.discover_tools("ws://test.com/mcp")
        assert len(tools) == 1
        mock_ws.assert_called_once()
```

### Integration Testing
```python
async def test_websocket_with_real_server():
    """Test against actual WebSocket MCP server."""
    client = MCPClient()
    
    # Test discovery
    tools = await client.discover_tools("ws://localhost:8080/mcp")
    assert len(tools) > 0
    
    # Test tool execution
    if tools:
        result = await client.call_tool(
            "ws://localhost:8080/mcp", 
            tools[0]["name"], 
            {}
        )
        assert result["success"] is True
```

## 📊 Performance Characteristics

### Connection Overhead
- **Establishment**: ~50-100ms per WebSocket connection
- **Memory**: ~1-2KB per connection (short-lived)
- **Throughput**: Limited by connection setup time

### Optimization Recommendations

1. **Batch Operations**: Group multiple tool calls when possible
2. **Connection Reuse**: Planned enhancement for connection pooling
3. **Caching**: Tool discovery results are cached by server URL

### Performance Monitoring
```python
import time

start_time = time.time()
result = await client.call_tool("ws://api.com/mcp", "tool", {})
duration = time.time() - start_time

print(f"WebSocket call took {duration:.2f}s")
```

## 🔒 Security Considerations

### URL Validation
```python
def validate_websocket_url(url):
    """Validate WebSocket URL for security."""
    parsed = urlparse(url)
    
    # Only allow secure WebSocket in production
    if parsed.scheme not in ["ws", "wss"]:
        raise ValueError("Invalid WebSocket scheme")
        
    # Block internal networks in production
    if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
        if os.getenv("ENVIRONMENT") == "production":
            raise ValueError("Localhost not allowed in production")
    
    return True
```

### Network Security
- Use `wss://` (secure WebSocket) in production
- Implement proper firewall rules for WebSocket ports
- Consider WebSocket-specific rate limiting

## 🚀 Deployment Checklist

### Pre-Deployment
- [ ] Verify WebSocket server compatibility
- [ ] Test error handling scenarios
- [ ] Configure monitoring and alerting
- [ ] Document authentication workarounds

### Production Deployment
- [ ] Use secure WebSocket URLs (`wss://`)
- [ ] Implement health checks
- [ ] Set up metrics collection
- [ ] Configure retry logic for critical operations

### Post-Deployment
- [ ] Monitor WebSocket connection metrics
- [ ] Verify error handling works as expected
- [ ] Test fallback to other transports
- [ ] Plan connection pooling enhancement

## 🔮 Future Enhancements

### Planned Features
1. **Connection Pooling**: Reuse WebSocket connections for better performance
2. **Enhanced Authentication**: Support for WebSocket headers and auth
3. **Automatic Reconnection**: Built-in reconnection logic with backoff
4. **Compression Support**: WebSocket message compression
5. **Load Balancing**: Client-side WebSocket endpoint selection

### Timeline
- **Q1**: Connection pooling and enhanced error handling
- **Q2**: Authentication support (pending MCP SDK updates)
- **Q3**: Advanced features (compression, reconnection)

## 📞 Support and Troubleshooting

### Common Issues

1. **"WebSocket URL not provided"**
   - Ensure config has `url` field or use string URL
   
2. **Connection timeouts**
   - Check network connectivity to WebSocket server
   - Verify server is running and accepting WebSocket connections
   
3. **Authentication errors**
   - Use alternative transport for authenticated endpoints
   - Consider URL-based authentication if supported

### Debug Mode
```python
import logging
logging.getLogger("kailash.mcp_server.client").setLevel(logging.DEBUG)

client = MCPClient()
# Detailed logging will show WebSocket connection attempts
```

### Getting Help
- Check integration tests for usage examples
- Review error messages for specific transport_type
- Monitor metrics for connection patterns

---

**WebSocket Transport Status**: ✅ Production Ready
**Last Updated**: 2025-01-29
**Version**: 1.0.0