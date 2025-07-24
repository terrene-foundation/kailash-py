# MCP Resource Subscriptions

*Real-time resource change notifications with full MCP specification compliance*

## ⚡ Quick Start

### Basic Subscription

```python
from kailash.mcp_server.server import MCPServer

# Create MCP server with subscription support
server = MCPServer(
    name="my-server",
    transport="websocket",
    websocket_host="127.0.0.1",
    websocket_port=3001,
    enable_subscriptions=True  # Enable resource subscriptions
)

# Register a resource
@server.resource("file:///{filename}")
def file_resource(filename):
    """Handle file resource requests."""
    return {"content": f"Content of {filename}", "version": 1}

# Start server
server.run()
```

### Client Subscription (WebSocket)

```javascript
// JavaScript MCP client example
const ws = new WebSocket('ws://127.0.0.1:3001');

// Initialize MCP session
ws.send(JSON.stringify({
    jsonrpc: "2.0",
    id: "init",
    method: "initialize",
    params: {
        protocolVersion: "2024-11-05",
        capabilities: { resources: { subscribe: true } },
        clientInfo: { name: "my-client", version: "1.0.0" }
    }
}));

// Subscribe to resource changes
ws.send(JSON.stringify({
    jsonrpc: "2.0",
    id: "sub1",
    method: "resources/subscribe",
    params: { uri: "file:///config.json" }
}));

// Listen for notifications
ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "notifications/resources/updated") {
        console.log("Resource changed:", message.params);
    }
};
```

## 🎯 Core Features

### 1. Real-time Notifications

```python
from kailash.mcp_server.protocol import ResourceChange, ResourceChangeType
from datetime import datetime

# Trigger resource change notification
change = ResourceChange(
    type=ResourceChangeType.UPDATED,
    uri="file:///config.json",
    timestamp=datetime.utcnow()
)

# Send to all subscribers
await server.subscription_manager.process_resource_change(change)
```

### 2. Wildcard Pattern Matching

```python
# Client subscribes to pattern
{
    "method": "resources/subscribe",
    "params": {
        "uri": "file://*.json"  # Matches all JSON files
    }
}

# Advanced patterns
"file:///**/*.md"     # All markdown files (recursive)
"config:///*"         # All config resources
"api:///{version}/*"  # Version-specific API resources
```

### 3. Cursor-based Pagination

```python
# List resources with pagination
{
    "method": "resources/list",
    "params": {
        "limit": 10,
        "cursor": "eyJwYWdlIjoxfQ=="  # Optional cursor
    }
}

# Response includes next page cursor
{
    "result": {
        "resources": [...],
        "nextCursor": "eyJwYWdlIjoyfQ=="
    }
}
```

## 🔧 Advanced Configuration

### Server with Authentication

```python
from kailash.mcp_server.auth import APIKeyAuth

# Configure authentication
auth_provider = APIKeyAuth(keys=["secret_key_123"])

server = MCPServer(
    name="secure-server",
    transport="websocket",
    enable_subscriptions=True,
    auth_provider=auth_provider,  # Add authentication
    rate_limit_config={
        "default_limit": 100,  # 100 requests per minute
        "burst_limit": 10
    }
)
```

### Event Store Integration

```python
from kailash.event_store import EventStore

# Create event store for audit logging
event_store = EventStore()

server = MCPServer(
    name="audited-server",
    enable_subscriptions=True,
    event_store=event_store  # All subscription events logged
)

# Query subscription history
events = await event_store.stream_events("subscriptions")
```

### Custom Resource Monitoring

```python
from kailash.mcp_server.subscriptions import ResourceSubscriptionManager

# Custom subscription manager
class CustomSubscriptionManager(ResourceSubscriptionManager):
    async def process_resource_change(self, change):
        """Custom change processing with business logic."""
        
        # Add custom validation
        if change.uri.startswith("sensitive://"):
            # Special handling for sensitive resources
            await self._handle_sensitive_change(change)
        
        # Call parent implementation
        await super().process_resource_change(change)
    
    async def _handle_sensitive_change(self, change):
        """Custom handling for sensitive resources."""
        # Log security event
        await self.event_store.append_event(
            stream_name="security",
            event_type="sensitive_resource_accessed",
            data={"uri": change.uri, "timestamp": change.timestamp.isoformat()}
        )
```

## 🌐 Client Integration Patterns

### Python Client

```python
import asyncio
import websockets
import json

class MCPClient:
    def __init__(self, uri):
        self.uri = uri
        self.websocket = None
        self.subscriptions = {}
        
    async def connect(self):
        self.websocket = await websockets.connect(self.uri)
        await self._initialize()
    
    async def _initialize(self):
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"resources": {"subscribe": True}},
            "clientInfo": {"name": "python-client", "version": "1.0.0"}
        })
    
    async def subscribe(self, uri_pattern):
        response = await self._send_request("resources/subscribe", {
            "uri": uri_pattern
        })
        subscription_id = response["result"]["subscriptionId"]
        self.subscriptions[subscription_id] = uri_pattern
        return subscription_id
    
    async def _send_request(self, method, params):
        request = {
            "jsonrpc": "2.0",
            "id": f"req_{len(self.subscriptions)}",
            "method": method,
            "params": params
        }
        await self.websocket.send(json.dumps(request))
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def listen_for_notifications(self):
        async for message in self.websocket:
            data = json.loads(message)
            if "method" in data and data["method"].startswith("notifications/"):
                yield data

# Usage
async def main():
    client = MCPClient("ws://localhost:3001")
    await client.connect()
    
    # Subscribe to resources
    await client.subscribe("file://*.json")
    
    # Listen for changes
    async for notification in client.listen_for_notifications():
        print(f"Resource changed: {notification['params']['uri']}")

asyncio.run(main())
```

### Node.js Client

```javascript
const WebSocket = require('ws');

class MCPClient {
    constructor(uri) {
        this.uri = uri;
        this.ws = null;
        this.subscriptions = new Map();
        this.requestId = 0;
    }
    
    async connect() {
        this.ws = new WebSocket(this.uri);
        
        return new Promise((resolve) => {
            this.ws.on('open', async () => {
                await this.initialize();
                resolve();
            });
        });
    }
    
    async initialize() {
        await this.sendRequest('initialize', {
            protocolVersion: '2024-11-05',
            capabilities: { resources: { subscribe: true } },
            clientInfo: { name: 'nodejs-client', version: '1.0.0' }
        });
    }
    
    async subscribe(uriPattern) {
        const response = await this.sendRequest('resources/subscribe', {
            uri: uriPattern
        });
        
        const subscriptionId = response.result.subscriptionId;
        this.subscriptions.set(subscriptionId, uriPattern);
        return subscriptionId;
    }
    
    async sendRequest(method, params) {
        const request = {
            jsonrpc: '2.0',
            id: `req_${++this.requestId}`,
            method,
            params
        };
        
        return new Promise((resolve) => {
            const handler = (data) => {
                const message = JSON.parse(data);
                if (message.id === request.id) {
                    this.ws.off('message', handler);
                    resolve(message);
                }
            };
            
            this.ws.on('message', handler);
            this.ws.send(JSON.stringify(request));
        });
    }
    
    onNotification(callback) {
        this.ws.on('message', (data) => {
            const message = JSON.parse(data);
            if (message.method && message.method.startsWith('notifications/')) {
                callback(message);
            }
        });
    }
}

// Usage
async function main() {
    const client = new MCPClient('ws://localhost:3001');
    await client.connect();
    
    // Subscribe to resources
    await client.subscribe('config://*');
    
    // Listen for notifications
    client.onNotification((notification) => {
        console.log('Resource changed:', notification.params.uri);
    });
}

main().catch(console.error);
```

## 🔒 Security Best Practices

### 1. Authentication & Authorization

```python
from kailash.mcp_server.auth import JWTAuth, PermissionManager

# JWT-based authentication
jwt_auth = JWTAuth(
    secret="your-secret-key",
    algorithm="HS256",
    expiration=3600  # 1 hour
)

# Permission-based access control
permission_manager = PermissionManager(
    roles={
        "admin": ["read", "write", "subscribe", "manage"],
        "user": ["read", "subscribe"],
        "guest": ["read"]
    }
)

# Create token with permissions
token = jwt_auth.create_token({
    "user": "alice",
    "permissions": ["read", "subscribe"],
    "roles": ["user"]
})
```

### 2. Rate Limiting

```python
from kailash.mcp_server.auth import RateLimiter

# Configure rate limiting
rate_limiter = RateLimiter(
    default_limit=60,    # 60 requests per minute
    burst_limit=10,      # 10 requests burst
    per_user_limits={
        "premium_user": 120,  # Premium users get higher limits
        "basic_user": 30
    }
)

server = MCPServer(
    name="rate-limited-server",
    enable_subscriptions=True,
    rate_limit_config={
        "default_limit": 60,
        "burst_limit": 10
    }
)
```

### 3. Secure Resource Patterns

```python
# Secure resource registration
@server.resource("user:///{user_id}/data")
def user_data_resource(user_id):
    """User-specific data with access control."""
    # Validate user access in handler
    current_user = get_current_user()  # From auth context
    if current_user["id"] != user_id and not current_user.get("is_admin"):
        raise PermissionError("Access denied")
    
    return load_user_data(user_id)

# Pattern-based access control
subscription_patterns = {
    "public://**": ["read"],           # Public resources
    "user://{user_id}/**": ["read"],   # User's own resources
    "admin://**": ["admin"]            # Admin-only resources
}
```

## 📊 Performance Optimization

### 1. Connection Pooling

```python
from kailash.mcp_server.server import MCPServer

server = MCPServer(
    name="optimized-server",
    enable_subscriptions=True,
    # Connection pool configuration
    connection_pool_config={
        "max_connections": 1000,
        "connection_timeout": 30.0,
        "keepalive_timeout": 300.0
    },
    # WebSocket optimization
    transport_timeout=60.0,
    max_request_size=10_000_000  # 10MB
)
```

### 2. Subscription Batching

```python
from kailash.mcp_server.subscriptions import ResourceSubscriptionManager

class BatchingSubscriptionManager(ResourceSubscriptionManager):
    def __init__(self, *args, batch_size=100, batch_timeout=0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self._pending_changes = []
        self._batch_task = None
    
    async def process_resource_change(self, change):
        """Batch resource changes for efficiency."""
        self._pending_changes.append(change)
        
        if len(self._pending_changes) >= self.batch_size:
            await self._flush_batch()
        elif not self._batch_task:
            self._batch_task = asyncio.create_task(
                self._auto_flush_batch()
            )
    
    async def _auto_flush_batch(self):
        """Auto-flush batch after timeout."""
        await asyncio.sleep(self.batch_timeout)
        await self._flush_batch()
    
    async def _flush_batch(self):
        """Flush pending changes."""
        if not self._pending_changes:
            return
        
        changes = self._pending_changes.copy()
        self._pending_changes.clear()
        
        if self._batch_task:
            self._batch_task.cancel()
            self._batch_task = None
        
        # Process all changes
        for change in changes:
            await super().process_resource_change(change)
```

### 3. Memory Management

```python
# Configure subscription cleanup
server = MCPServer(
    name="memory-optimized-server",
    enable_subscriptions=True,
    # Subscription cleanup configuration
    subscription_cleanup_interval=300,  # 5 minutes
    max_subscriptions_per_connection=100,
    subscription_ttl=3600  # 1 hour
)

# Monitor subscription memory usage
def monitor_subscriptions():
    """Monitor subscription memory usage."""
    manager = server.subscription_manager
    
    metrics = {
        "active_subscriptions": len(manager._subscriptions),
        "connections": len(manager._connection_subscriptions),
        "patterns": len(manager._pattern_index)
    }
    
    logger.info(f"Subscription metrics: {metrics}")
    
    # Alert if memory usage is high
    if metrics["active_subscriptions"] > 10000:
        logger.warning("High subscription count detected")
```

## 🐛 Troubleshooting

### Common Issues

1. **Subscriptions Not Working**
   ```python
   # Check server configuration
   assert server.enable_subscriptions is True
   assert server.subscription_manager is not None
   
   # Verify WebSocket transport
   assert server.transport == "websocket"
   ```

2. **Missing Notifications**
   ```python
   # Verify subscription exists
   subscription = server.subscription_manager.get_subscription(sub_id)
   assert subscription is not None
   
   # Check URI pattern matching
   assert subscription.matches_uri("file:///test.json")
   
   # Verify notification callback is set
   assert server.subscription_manager._notification_callback is not None
   ```

3. **Performance Issues**
   ```python
   # Monitor subscription metrics
   metrics = server.subscription_manager.get_metrics()
   print(f"Subscriptions: {metrics['active_subscriptions']}")
   print(f"Notifications sent: {metrics['notifications_sent']}")
   
   # Check for subscription leaks
   if metrics['active_subscriptions'] > expected_count:
       # Cleanup orphaned subscriptions
       await server.subscription_manager.cleanup_expired_subscriptions()
   ```

### Debug Mode

```python
import logging

# Enable debug logging
logging.getLogger("kailash.mcp_server").setLevel(logging.DEBUG)

# Server with debug configuration
server = MCPServer(
    name="debug-server",
    enable_subscriptions=True,
    # Debug settings
    enable_metrics=True,
    enable_monitoring=True,
    debug_mode=True
)

# Access debug information
debug_info = server.get_debug_info()
print(f"Active connections: {debug_info['connections']}")
print(f"Subscription stats: {debug_info['subscriptions']}")
```

## 🔗 Related Resources

- **[MCP Integration Guide](025-mcp-integration.md)** - Complete MCP setup
- **[WebSocket Transport](../transports/websocket-transport.md)** - WebSocket configuration
- **[Authentication Patterns](../../5-enterprise/security-patterns.md)** - Security implementation
- **[Event Store Integration](../events/event-store-patterns.md)** - Event logging
- **[Performance Monitoring](../monitoring/performance-monitoring.md)** - Metrics & alerts

## 📋 API Reference

### ResourceSubscriptionManager

```python
class ResourceSubscriptionManager:
    async def create_subscription(
        self, 
        connection_id: str, 
        uri_pattern: str,
        user_context: Optional[Dict[str, Any]] = None,
        cursor: Optional[str] = None
    ) -> str:
        """Create a new resource subscription."""
    
    async def remove_subscription(
        self, 
        subscription_id: str, 
        connection_id: str
    ) -> bool:
        """Remove a subscription."""
    
    async def process_resource_change(
        self, 
        change: ResourceChange
    ) -> None:
        """Process and notify about resource changes."""
    
    async def cleanup_connection(
        self, 
        connection_id: str
    ) -> int:
        """Clean up all subscriptions for a connection."""
```

### MCP Protocol Messages

```json
// Subscribe to resources
{
    "jsonrpc": "2.0",
    "id": "sub1",
    "method": "resources/subscribe",
    "params": {
        "uri": "file://*.json",
        "cursor": "optional_cursor"
    }
}

// Subscription response
{
    "jsonrpc": "2.0",
    "id": "sub1",
    "result": {
        "subscriptionId": "uuid-123"
    }
}

// Resource change notification
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "file:///config.json",
        "type": "updated",
        "timestamp": "2025-01-20T10:30:00Z"
    }
}
```

Resource subscriptions provide **real-time notifications** with **enterprise-grade security**, **performance optimization**, and **full MCP specification compliance**.