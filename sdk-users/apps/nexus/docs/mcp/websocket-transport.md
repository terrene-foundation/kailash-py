# WebSocket Transport for MCP

The WebSocketServerTransport provides a robust, production-ready transport layer for the Model Context Protocol (MCP) in Nexus. It offers advanced features like client management, broadcasting, and custom message handling while maintaining backward compatibility.

## Overview

The transport layer abstracts WebSocket communication, providing:
- Multiple concurrent client connections
- Message broadcasting capabilities
- Client session tracking
- Automatic connection management
- Configurable message size limits
- Built-in ping/pong for connection health

## Quick Start

### Basic Server Setup

```python
from nexus.mcp import MCPServer

# Create MCP server with WebSocketServerTransport (default in v0.8.5+)
server = MCPServer(host="0.0.0.0", port=3001, use_transport=True)

# Register workflows
server.register_workflow("my_tool", workflow)

# Start server
await server.start()
```

### Basic Client Setup

```python
from nexus.mcp import SimpleMCPClient

# Create client with WebSocketClientTransport
client = SimpleMCPClient(host="localhost", port=3001, use_transport=True)

# Connect to server
await client.connect()

# Use MCP protocol
tools = await client.list_tools()
result = await client.call_tool("my_tool", {"param": "value"})

# Disconnect
await client.disconnect()
```

## Advanced Usage

### Custom Message Handler

```python
from nexus.mcp.transport import WebSocketServerTransport

async def custom_handler(message):
    """Handle incoming messages with custom logic."""
    msg_type = message.get("type")

    if msg_type == "custom_command":
        # Process custom command
        return {"type": "custom_response", "data": "processed"}

    # Default handling
    return {"type": "echo", "original": message}

# Create transport with custom handler
transport = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    message_handler=custom_handler,
    max_message_size=10 * 1024 * 1024  # 10MB
)

await transport.start()
```

### Broadcasting to All Clients

```python
# Send notification to all connected clients
await transport.broadcast_notification({
    "event": "server_update",
    "data": {"status": "processing", "queue_length": 5}
})

# Send custom message to all clients
await transport.send_message({
    "type": "announcement",
    "message": "Server maintenance in 5 minutes"
})
```

### Client Management

```python
# Get number of connected clients
client_count = transport.get_connected_clients()

# Wait for minimum clients before starting
connected = await transport.wait_for_clients(
    min_clients=2,
    timeout=30.0  # Wait up to 30 seconds
)

if connected:
    print("Minimum clients connected, starting processing")
else:
    print("Timeout waiting for clients")
```

### Direct Transport Usage

For advanced scenarios, you can use the transport layer directly:

```python
from nexus.mcp.transport import WebSocketServerTransport, WebSocketClientTransport

# Server-side
server_transport = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    message_handler=async_message_processor
)
await server_transport.start()

# Client-side
client_transport = WebSocketClientTransport(
    uri="ws://localhost:3001",
    message_handler=async_notification_handler
)
await client_transport.start()

# Send message from client
await client_transport.send_message({
    "type": "request",
    "action": "process_data",
    "data": [1, 2, 3]
})

# Receive response
response = await client_transport.receive_message()
```

## Features

### 1. Connection Management

- Automatic client tracking
- Connection state monitoring
- Graceful disconnection handling
- Configurable timeouts

### 2. Message Handling

- JSON message serialization
- Error handling with proper responses
- Support for large messages (configurable limit)
- Automatic ping/pong for connection health

### 3. Broadcasting

- Send messages to all connected clients
- Send notifications with automatic type setting
- Selective client messaging

### 4. Client Features

- Automatic reconnection support (in client implementation)
- Background message receiving
- Connection status checking
- Asynchronous message handling

## Configuration Options

### WebSocketServerTransport

| Parameter | Default | Description |
|-----------|---------|-------------|
| `host` | `"0.0.0.0"` | Host to bind to |
| `port` | `3001` | Port to listen on |
| `message_handler` | `None` | Async function to handle messages |
| `max_message_size` | `10MB` | Maximum message size in bytes |

### WebSocketClientTransport

| Parameter | Default | Description |
|-----------|---------|-------------|
| `uri` | Required | WebSocket URI (e.g., `"ws://localhost:3001"`) |
| `message_handler` | `None` | Async function to handle incoming messages |
| `max_message_size` | `10MB` | Maximum message size in bytes |

## Error Handling

The transport layer provides comprehensive error handling:

```python
# Server-side error handling
async def message_handler(message):
    try:
        # Process message
        result = await process_message(message)
        return {"type": "success", "result": result}
    except ValueError as e:
        return {"type": "error", "error": f"Invalid value: {e}"}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"type": "error", "error": "Internal server error"}

# Client-side error handling
try:
    await client_transport.send_message(message)
except RuntimeError as e:
    print(f"Connection error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Migration Guide

### From Direct WebSockets to Transport

Before (direct WebSockets):
```python
# Server
server = await websockets.serve(handler, "localhost", 3001)

# Client
websocket = await websockets.connect("ws://localhost:3001")
await websocket.send(json.dumps(message))
response = json.loads(await websocket.recv())
```

After (using transport):
```python
# Server
transport = WebSocketServerTransport(
    host="localhost",
    port=3001,
    message_handler=handler
)
await transport.start()

# Client
transport = WebSocketClientTransport("ws://localhost:3001")
await transport.start()
await transport.send_message(message)
response = await transport.receive_message()
```

### Backward Compatibility

The MCP server maintains backward compatibility:

```python
# Use transport (recommended)
server = MCPServer(port=3001, use_transport=True)

# Use direct WebSockets (legacy)
server = MCPServer(port=3001, use_transport=False)
```

## Best Practices

1. **Always use transport layer** for new implementations
2. **Implement proper error handling** in message handlers
3. **Set appropriate message size limits** based on your use case
4. **Use broadcasting** for server-wide notifications
5. **Monitor client connections** for production deployments
6. **Implement graceful shutdown** procedures

## Examples

See the complete examples in:
- `/examples/websocket_transport_demo.py` - Comprehensive transport demonstrations
- `/examples/mcp_enhanced_demo.py` - MCP server with advanced features

## Testing

The transport layer includes comprehensive unit and integration tests:

```bash
# Run transport tests
pytest tests/unit/test_websocket_transport.py

# Run integration tests
pytest tests/integration/test_mcp_transport_integration.py
```

## Future Enhancements

Planned improvements for the transport layer:
- WebSocket compression support
- Connection rate limiting
- Message queuing for offline clients
- Transport layer encryption
- Multi-transport support (WebSocket + HTTP/2)
