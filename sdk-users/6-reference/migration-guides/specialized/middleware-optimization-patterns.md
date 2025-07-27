# Middleware Optimization Migration Guide

This guide helps you migrate from custom middleware implementations to SDK-optimized patterns for maximum performance.

## Key Principles

1. **Replace Custom Code with SDK Nodes** - The SDK has nodes for almost everything
2. **Use Workflows for Multi-Step Operations** - Convert procedural code to declarative workflows
3. **Delegate to SDK Runtime** - Never orchestrate execution manually
4. **Leverage Enterprise Nodes** - Use BatchProcessorNode, DataLineageNode, etc.

## Common Migration Patterns

### 1. Session Management

**Before (Custom Code):**
```python
from kailash.workflow.builder import WorkflowBuilder
class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.lock = asyncio.Lock()

    async def create_session(self, user_id):
        async with self.lock:
            session_id = str(uuid.uuid4())
            self.sessions[session_id] = {
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "active": True
            }
        return session_id
```

**After (SDK Nodes):**
```python
# Use workflow with SDK nodes
builder = WorkflowBuilder()

# Permission check
builder.add_node("PermissionCheckNode", node_id="check_perms",
    config={"permission": "session.create"})

# Data transformation
builder.add_node("DataTransformer", node_id="create_session",
    config={"transformations": [
        {"operation": "add_field", "field": "session_id", "value": "{{ generate_uuid() }}"},
        {"operation": "add_field", "field": "created_at", "value": "{{ current_timestamp() }}"}
    ]})

# Audit logging
builder.add_node("AuditLogNode", node_id="audit",
    config={"action": "create_session"})

# Connect and execute
workflow = builder.build()
results, run_id = await runtime.execute_async(workflow, parameters={"user_id": user_id})
```

### 2. Event Processing

**Before (Custom Code):**
```python
class EventProcessor:
    def __init__(self):
        self.events = []
        self.batch_size = 100

    async def process_events(self):
        while self.events:
            batch = self.events[:self.batch_size]
            self.events = self.events[self.batch_size:]
            await self._process_batch(batch)
```

**After (SDK Nodes):**
```python
# Use workflow with BatchProcessorNode
workflow = WorkflowBuilder()
workflow.add_node("BatchProcessorNode", "event_processor", {
    "operation": "process_events",
    "data_items": events,
    "batch_size": 100,
    "processing_function": transform_event
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 3. Database Operations

**Before (Custom Code):**
```python
async def save_workflow(self, workflow_data):
    async with self.db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workflows (id, data) VALUES ($1, $2)",
            workflow_data["id"], json.dumps(workflow_data)
        )
```

**After (SDK Nodes):**
```python
# Use workflow with AsyncSQLDatabaseNode
workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", "workflow_db", {
    "connection_string": database_url,
    "query": "INSERT INTO workflows (id, data) VALUES (:id, :data)",
    "parameters": {"id": workflow_id, "data": workflow_data}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 4. Caching

**Before (Custom Code):**
```python
class SimpleCache:
    def __init__(self):
        self.cache = {}
        self.ttl = {}

    def get(self, key):
        if key in self.cache:
            if time.time() < self.ttl.get(key, 0):
                return self.cache[key]
        return None
```

**After (SDK Pattern):**
```python
# Use DataTransformer as cache with TTL
cache_transformer = DataTransformer(
    name="cache_manager",
    transformations=[
        {"operation": "cache", "ttl_seconds": 300}
    ]
)

# Or use dedicated CacheNode when available
```

### 5. Rate Limiting

**Before (Custom Code):**
```python
class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []
```

**After (SDK Pattern):**
```python
# Use RateLimiterNode when available
# Or use BatchProcessorNode with rate limiting
batch_processor = BatchProcessorNode(
    name="rate_limited_processor",
    rate_limit=100,  # requests per minute
    rate_limit_strategy="sliding_window"
)
```

### 6. Monitoring and Metrics

**Before (Custom Code):**
```python
class MetricsCollector:
    def __init__(self):
        self.metrics = defaultdict(int)
        self.timings = []

    def record_event(self, event_type):
        self.metrics[event_type] += 1
```

**After (SDK Nodes):**
```python
# Use workflow with DataLineageNode for tracking
workflow = WorkflowBuilder()
workflow.add_node("DataLineageNode", "metrics_tracker", {
    "data_source": "middleware",
    "data_target": "metrics",
    "metadata": {"event_type": event_type, "timestamp": datetime.utcnow()}
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Use MetricsCollectorNode when available
```

### 7. Security and Authentication

**Before (Custom Code):**
```python
class TokenManager:
    def __init__(self):
        self.tokens = {}
        self.secret_key = "hardcoded_secret"

    def create_token(self, user_id):
        # Manual JWT creation
        pass
```

**After (SDK Nodes):**
```python
# Use RotatingCredentialNode for secrets
rotating_creds = RotatingCredentialNode(
    name="jwt_secrets",
    credential_name="jwt_signing_key",
    rotation_interval_days=30
)

# Use KailashJWTAuthManager
auth_manager = KailashJWTAuthManager()
token = await auth_manager.create_token(user_id)
```

## Performance Optimization Checklist

- [ ] Replace custom session management with workflows
- [ ] Use BatchProcessorNode for event processing
- [ ] Replace database code with AsyncSQLDatabaseNode
- [ ] Use DataTransformer for data manipulation
- [ ] Implement RotatingCredentialNode for secrets
- [ ] Add DataLineageNode for tracking
- [ ] Use PermissionCheckNode for authorization
- [ ] Add AuditLogNode for compliance
- [ ] Replace custom queues with SDK patterns
- [ ] Use AsyncLocalRuntime for all execution

## Migration Steps

1. **Identify Custom Code**: Find all custom implementations
2. **Map to SDK Nodes**: Identify equivalent SDK nodes
3. **Create Workflows**: Build workflows for multi-step operations
4. **Test Performance**: Verify improved performance
5. **Remove Old Code**: Clean up custom implementations

## Benefits After Migration

- **Better Performance**: SDK nodes are optimized
- **Automatic Retries**: Built-in error handling
- **Proper Logging**: Comprehensive audit trails
- **Security**: Enterprise-grade credential management
- **Monitoring**: Built-in metrics and tracking
- **Maintainability**: Declarative vs imperative code

## Next Steps

1. Review `optimized_middleware_example.py` for complete implementation
2. Use `MiddlewareWorkflows` class for common patterns
3. Leverage workflow templates for consistency
4. Monitor performance improvements with DataLineageNode
