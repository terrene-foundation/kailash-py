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

### Phase 1: Basic Subscriptions

#### 1. Real-time Notifications

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

#### 2. Wildcard Pattern Matching

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

#### 3. Cursor-based Pagination

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

### Phase 2: Advanced Features

#### 4. GraphQL-style Field Selection

*Control exactly which fields are included in resource notifications*

```python
# Subscribe with specific fields
{
    "method": "resources/subscribe",
    "params": {
        "uri": "file://*.json",
        "fields": ["uri", "content.text", "metadata.size", "metadata.lastModified"]
    }
}

# Use fragments for reusable field sets
{
    "method": "resources/subscribe",
    "params": {
        "uri": "config://*",
        "fragments": {
            "basicInfo": ["uri", "name", "type"],
            "metadata": ["size", "modified", "permissions"]
        }
    }
}

# Nested field access with dot notation
{
    "method": "resources/subscribe",
    "params": {
        "uri": "api://*/users",
        "fields": [
            "user.profile.name",
            "user.settings.theme",
            "user.permissions.roles"
        ]
    }
}
```

**Benefits:**
- Reduce bandwidth by only receiving needed fields
- Improve client performance with smaller payloads
- Support different client capabilities (mobile vs desktop)
- Enable GraphQL-like query flexibility

#### 5. Server-side Transformation Pipeline

*Transform resource data before delivery to clients*

```python
from kailash.mcp_server.subscriptions import (
    DataEnrichmentTransformer,
    FormatConverterTransformer,
    AggregationTransformer
)

# Create transformation pipeline
manager = ResourceSubscriptionManager()

# Add data enrichment
enrichment_transformer = DataEnrichmentTransformer()
enrichment_transformer.add_enrichment(
    "file_size_mb",
    lambda data: len(str(data.get('content', ''))) / 1024 / 1024
)
enrichment_transformer.add_enrichment(
    "last_accessed",
    lambda data: get_last_access_time(data.get('uri'))
)

# Add format conversion
format_transformer = FormatConverterTransformer()
format_transformer.add_conversion(
    "content",  # Convert content field
    lambda value: convert_csv_to_json(value) if is_csv_content(value) else value
)

# Add aggregation
aggregation_transformer = AggregationTransformer()
aggregation_transformer.add_data_source(
    "related_files",
    lambda uri: find_related_files(uri)  # Data source function
)

# Configure pipeline
manager.transformation_pipeline.add_transformer(enrichment_transformer)
manager.transformation_pipeline.add_transformer(format_transformer)
manager.transformation_pipeline.add_transformer(aggregation_transformer)
```

**Use Cases:**
- Add computed fields (file sizes, checksums, derived data)
- Convert data formats (CSV to JSON, XML to JSON)
- Aggregate related information from multiple sources
- Apply business logic transformations before delivery

#### 6. Batch Subscribe/Unsubscribe Operations

*Efficiently manage multiple subscriptions in single requests*

```python
# Batch subscribe to multiple resources
batch_subscriptions = [
    {
        "uri_pattern": "file://*.json",
        "fields": ["uri", "content"],
        "name": "json_files"
    },
    {
        "uri_pattern": "config:///database",
        "fragments": {"dbInfo": ["host", "port", "database"]},
        "name": "db_config"
    },
    {
        "uri_pattern": "logs://*.error",
        "cursor": "error_cursor_123",
        "name": "error_logs"
    }
]

result = await manager.create_batch_subscriptions(
    subscriptions=batch_subscriptions,
    connection_id="client_123"
)

# Response includes success/failure for each subscription
{
    "total_requested": 3,
    "total_created": 2,
    "total_failed": 1,
    "successful": [
        {"subscription_id": "sub_001", "subscription_name": "json_files"},
        {"subscription_id": "sub_002", "subscription_name": "db_config"}
    ],
    "failed": [
        {"error": "Invalid cursor", "request": {"uri_pattern": "logs://*.error", "name": "error_logs"}}
    ]
}

# Batch unsubscribe
await manager.remove_batch_subscriptions(
    subscription_ids=["sub_001", "sub_002"],
    connection_id="client_123"
)
```

**Benefits:**
- Reduce network round-trips for multiple subscriptions
- Atomic operations with transaction-like semantics
- Bulk error handling and reporting
- Improved performance for large-scale clients

#### 7. WebSocket Compression Support

*Automatic gzip compression for large messages*

```python
# Server with compression enabled
server = MCPServer(
    name="compressed-server",
    enable_subscriptions=True,
    # Compression configuration
    enable_websocket_compression=True,
    compression_threshold=1024,      # Only compress messages > 1KB
    compression_level=6              # Balance of speed vs compression (1-9)
)

# Compression is transparent to clients
# Large notifications are automatically compressed
# Clients receive decompressed data seamlessly
```

**Configuration Options:**
- `compression_threshold`: Minimum message size to compress (bytes)
- `compression_level`: Gzip compression level (1=fast, 9=best compression)
- `enable_websocket_compression`: Enable/disable compression globally

**Performance Benefits:**
- 60-80% bandwidth reduction for large JSON payloads
- Improved performance on slower network connections
- Reduced server egress costs in cloud deployments
- Automatic adaptation based on message size

#### 8. Redis-backed Distributed Subscriptions

*Multi-instance MCP server coordination and failover*

```python
from kailash.mcp_server.subscriptions import DistributedSubscriptionManager

# Distributed subscription manager
manager = DistributedSubscriptionManager(
    redis_url="redis://localhost:6379",
    server_instance_id="mcp_server_1",
    subscription_key_prefix="mcp:subs:",
    notification_channel_prefix="mcp:notify:",
    heartbeat_interval=30,           # Heartbeat every 30 seconds
    instance_timeout=90              # Consider instance dead after 90s
)

# Initialize distributed coordination
await manager.initialize()

# Create server with distributed manager
server = MCPServer(
    name="distributed-server",
    enable_subscriptions=True,
    subscription_manager=manager
)

# Multiple server instances automatically coordinate:
# - Subscription state shared across all instances
# - Resource changes distributed to all relevant instances
# - Automatic cleanup when instances go down
# - Load balancing across healthy instances
```

**Deployment Pattern:**
```yaml
# docker-compose.yml for distributed deployment
version: '3.8'
services:
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  mcp-server-1:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379
      - SERVER_INSTANCE_ID=mcp_server_1
      - WEBSOCKET_PORT=3001
    ports:
      - "3001:3001"
    depends_on:
      - redis

  mcp-server-2:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379
      - SERVER_INSTANCE_ID=mcp_server_2
      - WEBSOCKET_PORT=3002
    ports:
      - "3002:3002"
    depends_on:
      - redis
```

**Monitoring Distributed State:**
```python
# Get distributed statistics
stats = manager.get_distributed_stats()
print(f"Local subscriptions: {stats['local_subscriptions']}")
print(f"Other instances: {stats['other_instances']}")
print(f"Total distributed: {stats['total_distributed_subscriptions']}")

# Monitor instance health
for instance_id, sub_count in stats['distributed_subscriptions'].items():
    print(f"Instance {instance_id}: {sub_count} subscriptions")
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

### Phase 1: Basic Issues

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

### Phase 2: Advanced Issues

4. **Field Selection Not Working**
   ```python
   # Verify field selection is enabled
   subscription = manager.get_subscription(sub_id)
   assert subscription.fields is not None

   # Check field path validity
   test_data = {"user": {"profile": {"name": "test"}}}
   result = subscription.apply_field_selection(test_data)
   assert "user.profile.name" in str(result)

   # Debug field selection
   print(f"Requested fields: {subscription.fields}")
   print(f"Fragments: {subscription.fragments}")
   ```

5. **Transformation Pipeline Issues**
   ```python
   # Check pipeline configuration
   pipeline = manager.transformation_pipeline
   assert len(pipeline.transformers) > 0

   # Test individual transformers
   for transformer in pipeline.transformers:
       if transformer.enabled:
           test_result = await transformer.transform(test_data, {})
           print(f"Transformer {transformer.id}: {test_result}")

   # Check transformation errors
   if hasattr(pipeline, '_last_error'):
       print(f"Pipeline error: {pipeline._last_error}")
   ```

6. **Batch Operation Failures**
   ```python
   # Check batch results
   result = await manager.create_batch_subscriptions(batch_data, conn_id)
   print(f"Success rate: {result['total_created']}/{result['total_requested']}")

   # Examine individual failures
   for item in result['results']:
       if item['status'] == 'failed':
           print(f"Failed subscription: {item['name']} - {item['error']}")

   # Verify connection limits
   active_subs = await manager.get_connection_subscriptions(conn_id)
   print(f"Active subscriptions for connection: {len(active_subs)}")
   ```

7. **WebSocket Compression Issues**
   ```python
   # Check compression configuration
   assert server.enable_websocket_compression is True
   assert server.compression_threshold > 0

   # Monitor compression effectiveness
   stats = server.get_compression_stats()
   print(f"Messages compressed: {stats['messages_compressed']}")
   print(f"Average compression ratio: {stats['avg_compression_ratio']}")
   print(f"Total bandwidth saved: {stats['bytes_saved']}")

   # Debug compression decisions
   message_size = len(json.dumps(large_notification))
   should_compress = message_size > server.compression_threshold
   print(f"Message size: {message_size}, will compress: {should_compress}")
   ```

8. **Distributed Subscription Issues**
   ```python
   # Check Redis connectivity
   try:
       await manager.redis_client.ping()
       print("Redis connection: OK")
   except Exception as e:
       print(f"Redis connection failed: {e}")

   # Monitor instance health
   stats = manager.get_distributed_stats()
   print(f"Live instances: {len(stats['other_instances'])}")
   print(f"Distributed subscriptions: {stats['total_distributed_subscriptions']}")

   # Check heartbeat status
   for instance_id in stats['other_instances']:
       last_heartbeat = await manager.redis_client.hget(
           f"mcp:instances:{instance_id}", "last_heartbeat"
       )
       print(f"Instance {instance_id} last heartbeat: {last_heartbeat}")

   # Verify subscription replication
   local_subs = set(manager._subscriptions.keys())
   redis_subs = await manager.redis_client.smembers(
       f"mcp:instance_subs:{manager.server_instance_id}"
   )
   print(f"Local: {len(local_subs)}, Redis: {len(redis_subs)}")
   if local_subs != redis_subs:
       print("WARNING: Subscription state out of sync!")
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
    # Basic subscription management
    async def create_subscription(
        self,
        connection_id: str,
        uri_pattern: str,
        user_context: Optional[Dict[str, Any]] = None,
        cursor: Optional[str] = None,
        fields: Optional[List[str]] = None,           # GraphQL-style field selection
        fragments: Optional[Dict[str, List[str]]] = None  # Fragment definitions
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

    # Phase 2: Batch operations
    async def create_batch_subscriptions(
        self,
        subscriptions: List[Dict[str, Any]],
        connection_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create multiple subscriptions in a single batch operation."""

    async def remove_batch_subscriptions(
        self,
        subscription_ids: List[str],
        connection_id: str
    ) -> Dict[str, Any]:
        """Remove multiple subscriptions in a single batch operation."""

# Phase 2: Transformation Pipeline
class TransformationPipeline:
    def add_transformer(self, transformer: ResourceTransformer) -> None:
        """Add a transformer to the pipeline."""

    def remove_transformer(self, transformer_id: str) -> bool:
        """Remove a transformer from the pipeline."""

    async def apply(
        self,
        resource_data: Dict[str, Any],
        uri: str,
        subscription: ResourceSubscription
    ) -> Dict[str, Any]:
        """Apply all transformations to resource data."""

class ResourceTransformer(ABC):
    @abstractmethod
    async def transform(
        self,
        resource_data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Transform resource data."""

# Phase 2: Distributed subscriptions
class DistributedSubscriptionManager(ResourceSubscriptionManager):
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        server_instance_id: Optional[str] = None,
        subscription_key_prefix: str = "mcp:subs:",
        notification_channel_prefix: str = "mcp:notify:",
        heartbeat_interval: int = 30,
        instance_timeout: int = 90
    ):
        """Initialize distributed subscription manager."""

    async def initialize(self) -> None:
        """Initialize Redis connections and start background tasks."""

    async def shutdown(self) -> None:
        """Shutdown distributed coordination."""

    def get_distributed_stats(self) -> Dict[str, Any]:
        """Get statistics about distributed subscription state."""
```

### MCP Protocol Messages

#### Basic Subscription Messages

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

#### Phase 2: Enhanced Subscription Messages

```json
// Subscribe with field selection
{
    "jsonrpc": "2.0",
    "id": "sub2",
    "method": "resources/subscribe",
    "params": {
        "uri": "file://*.json",
        "fields": ["uri", "content.text", "metadata.size"],
        "fragments": {
            "basicInfo": ["uri", "name", "type"],
            "metadata": ["size", "modified", "permissions"]
        }
    }
}

// Batch subscribe
{
    "jsonrpc": "2.0",
    "id": "batch1",
    "method": "resources/batch_subscribe",
    "params": {
        "subscriptions": [
            {
                "uri": "file://*.json",
                "fields": ["uri", "content"],
                "name": "json_files"
            },
            {
                "uri": "config:///database",
                "fragments": {"dbInfo": ["host", "port"]},
                "name": "db_config"
            }
        ]
    }
}

// Batch subscribe response
{
    "jsonrpc": "2.0",
    "id": "batch1",
    "result": {
        "total_requested": 2,
        "total_created": 2,
        "total_failed": 0,
        "results": [
            {"name": "json_files", "subscription_id": "sub_001", "status": "created"},
            {"name": "db_config", "subscription_id": "sub_002", "status": "created"}
        ]
    }
}

// Batch unsubscribe
{
    "jsonrpc": "2.0",
    "id": "batch2",
    "method": "resources/batch_unsubscribe",
    "params": {
        "subscription_ids": ["sub_001", "sub_002"]
    }
}

// Enhanced notification with field selection
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "file:///config.json",
        "type": "updated",
        "timestamp": "2025-01-20T10:30:00Z",
        "data": {
            // Only requested fields included
            "uri": "file:///config.json",
            "content": {"text": "updated content"},
            "metadata": {"size": 1024}
        }
    }
}

// Compressed notification (WebSocket compression)
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "file:///large_data.json",
        "type": "updated",
        "timestamp": "2025-01-20T10:30:00Z",
        "compressed": true,
        "compression_type": "gzip",
        "original_size": 5120,
        "compressed_size": 1024
    }
}
```

## ✨ Summary

Resource subscriptions provide **real-time notifications** with comprehensive Phase 1 and Phase 2 capabilities:

### Phase 1: Foundation
- **Real-time notifications** via WebSocket transport
- **Wildcard pattern matching** for flexible resource selection
- **Cursor-based pagination** for efficient resource listing
- **Enterprise security** with authentication, authorization, and rate limiting
- **Performance optimization** with connection pooling and memory management

### Phase 2: Advanced Features
- **GraphQL-style field selection** to reduce bandwidth and improve performance
- **Server-side transformation pipeline** for data enrichment and format conversion
- **Batch operations** for efficient bulk subscription management
- **WebSocket compression** with intelligent threshold-based compression
- **Redis-backed distributed subscriptions** for multi-instance coordination and failover

**Full MCP specification compliance** ensures seamless integration with any MCP-compatible client, while **enterprise-grade reliability** supports production deployments at scale.
