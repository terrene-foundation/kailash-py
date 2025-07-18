# Nexus - Quick Reference for Claude Code

## 🚀 Zero-Config Multi-Channel Platform

**Nexus** provides unified workflow orchestration across API, CLI, and MCP channels with true zero-configuration setup. Register once, access everywhere.

## ⚡ Essential Patterns

### Pattern 1: Basic Multi-Channel Setup
```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero configuration - all channels auto-configured
app = Nexus()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "try:\n    user_name = name\nexcept NameError:\n    user_name = 'World'\nresult = {'message': f'Hello {user_name}!'}"
})

# Register workflow - available on all channels
app.register("greet", workflow.build())
app.start()

# Now available on:
# - API: POST /workflows/greet {"name": "Alice"}
# - CLI: nexus run greet --name Alice
# - MCP: greet tool for AI agents
```

### Pattern 2: Enterprise Configuration
```python
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=100,  # requests per minute
    auto_discovery=True
)

# Optional: Configure authentication
app.auth.configure(
    strategy="oauth2",
    provider="auth0",
    client_id="your_client_id"
)

# Optional: Configure monitoring
app.monitoring.configure(
    backend="prometheus",
    metrics_port=9090
)

app.start()
```

### Pattern 3: AI Agent Workflow
```python
# AI-powered workflow with real MCP execution
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {
    "model": "gpt-4",
    "prompt": "Analyze this data and provide insights: {data}",
    "use_real_mcp": True,  # Real MCP execution (default)
    "tools": ["web_search", "calculator", "file_reader"]
})

app.register("ai_analyst", workflow.build())
```

### Pattern 4: Data Processing Pipeline
```python
# Multi-step data processing
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": {"Authorization": "Bearer {{token}}"}
})
workflow.add_node("PythonCodeNode", "transform", {
    "code": "result = [item for item in data if item['active']]"
})
workflow.add_node("JSONWriterNode", "save", {
    "file_path": "/tmp/processed_data.json"
})

workflow.add_connection("fetch", "response", "transform", "data")
workflow.add_connection("transform", "result", "save", "data")

app.register("data_processor", workflow.build())
```

### Pattern 5: Real-time Event Processing
```python
# WebSocket-enabled real-time processing
workflow = WorkflowBuilder()
workflow.add_node("EventStreamNode", "stream", {
    "source": "websocket",
    "endpoint": "ws://events.example.com/feed"
})
workflow.add_node("PythonCodeNode", "filter", {
    "code": "result = [e for e in events if e['priority'] == 'high']"
})
workflow.add_node("NotificationNode", "notify", {
    "service": "slack",
    "webhook": "https://hooks.slack.com/..."
})

workflow.add_connection("stream", "events", "filter", "events")
workflow.add_connection("filter", "result", "notify", "data")

app.register("event_processor", workflow.build())
```

## 🎯 Core API Reference

### Nexus Constructor
```python
app = Nexus(
    api_port=8000,           # API server port
    mcp_port=3001,           # MCP server port
    enable_auth=False,       # Enable authentication
    enable_monitoring=False, # Enable monitoring
    rate_limit=None,         # Rate limit per minute
    auto_discovery=True,     # Auto-discover workflows
    channels_synced=True     # Synchronize sessions across channels
)
```

### Workflow Registration
```python
# Register single workflow
app.register("workflow_name", workflow)

# Register multiple workflows
app.register_batch({
    "workflow1": workflow1,
    "workflow2": workflow2,
    "workflow3": workflow3
})

# Register with metadata
app.register("workflow_name", workflow, metadata={
    "description": "Processes user data",
    "tags": ["data", "processing"],
    "version": "1.0.0"
})
```

### Channel Management
```python
# Start all channels
app.start()

# Start specific channels
app.start(channels=["api", "cli"])

# Stop specific channels
app.stop(channels=["mcp"])

# Health check
status = app.health_check()
print(f"API: {status['api']}, CLI: {status['cli']}, MCP: {status['mcp']}")
```

## 🔧 Advanced Patterns

### Parameter Passing Between Channels
```python
# Workflow with flexible parameter handling
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": """
# Parameters come from different sources:
# API: JSON body
# CLI: Command-line arguments  
# MCP: Tool parameters

# Set defaults first
user_name = 'Anonymous'
user_age = 0

# Override with parameters if available
try:
    user_name = name
except NameError:
    pass

try:
    user_age = age
except NameError:
    pass

result = {'greeting': f'Hello {user_name}, age {user_age}'}
"""
})

app.register("flexible_processor", workflow.build())

# Usage examples:
# API: POST /workflows/flexible_processor {"name": "Alice", "age": 30}
# CLI: nexus run flexible_processor --name Alice --age 30
# MCP: flexible_processor(name="Alice", age=30)
```

### Cross-Channel Session Management
```python
# Enable unified sessions across channels
app = Nexus(channels_synced=True)

# Session data persists across API, CLI, and MCP
workflow = WorkflowBuilder()
workflow.add_node("SessionNode", "session", {
    "action": "store",
    "key": "user_data",
    "value": "{{user_input}}"
})

app.register("store_session", workflow.build())

# Session accessible from any channel
workflow2 = WorkflowBuilder()
workflow2.add_node("SessionNode", "retrieve", {
    "action": "get",
    "key": "user_data"
})

app.register("get_session", workflow2.build())
```

### Error Handling and Retry
```python
# Workflow with built-in error handling
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api_call", {
    "url": "https://api.example.com/data",
    "retry_attempts": 3,
    "retry_delay": 1000,  # milliseconds
    "timeout": 5000
})
workflow.add_node("PythonCodeNode", "fallback", {
    "code": "result = {'error': 'API unavailable', 'data': []}"
})

# Connect with error handling
workflow.add_connection("api_call", "response", "fallback", "input")
workflow.add_error_handler("api_call", "fallback")

app.register("resilient_api", workflow.build())
```

## 🏗️ Integration Patterns

### Nexus + DataFlow Integration
```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# Initialize DataFlow
db = DataFlow()

@db.model
class User:
    name: str
    email: str

# Create workflow using DataFlow nodes
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "{{name}}",
    "email": "{{email}}"
})
workflow.add_node("UserListNode", "list", {
    "filter": {"active": True}
})

# Register with Nexus
app = Nexus()
app.register("user_manager", workflow.build())
app.start()

# Database operations now available on all channels
```

### Gateway Integration
```python
from kailash.servers.gateway import create_gateway

# Create enterprise gateway with Nexus
gateway = create_gateway(
    title="Enterprise API",
    server_type="enterprise",
    nexus_integration=app,
    auto_generate_openapi=True
)

# Workflows automatically exposed as REST endpoints
```

### MCP Tool Integration
```python
# Register workflow as MCP tool
workflow = WorkflowBuilder()
workflow.add_node("WebSearchNode", "search", {
    "query": "{{query}}",
    "num_results": 10
})

app.register("web_search", workflow.build(), 
    mcp_config={
        "tool_name": "web_search",
        "description": "Search the web for information",
        "parameters": {
            "query": {"type": "string", "description": "Search query"}
        }
    }
)

# Now available to AI agents as a tool
```

## 📊 Performance Optimization

### Async Execution
```python
# Enable async processing for high throughput
app = Nexus(
    async_execution=True,
    max_concurrent_workflows=100,
    queue_size=1000
)

# Async workflow execution
workflow = WorkflowBuilder()
workflow.add_node("AsyncHTTPRequestNode", "fetch", {
    "url": "https://api.example.com/data",
    "async_mode": True
})

app.register("async_processor", workflow.build())
```

### Load Balancing
```python
# Multiple Nexus instances for load balancing
app = Nexus(
    api_port=8000,
    load_balancer=True,
    cluster_mode=True,
    redis_url="redis://localhost:6379"
)

# Shared state across instances
```

### Caching
```python
# Enable result caching
workflow = WorkflowBuilder()
workflow.add_node("CacheNode", "cache", {
    "cache_key": "expensive_computation_{{input_hash}}",
    "ttl": 3600,  # 1 hour
    "backend": "redis"
})

app.register("cached_processor", workflow.build())
```

## 🛡️ Security & Authentication

### OAuth2 Integration
```python
app = Nexus(enable_auth=True)

app.auth.configure(
    strategy="oauth2",
    provider="auth0",
    client_id="your_client_id",
    client_secret="your_client_secret",
    redirect_uri="http://localhost:8000/callback"
)

# Protected workflows
app.register("protected_workflow", workflow.build(), 
    requires_auth=True,
    required_scopes=["read", "write"]
)
```

### API Key Authentication
```python
app.auth.configure(
    strategy="api_key",
    header_name="X-API-Key",
    key_validation_url="https://auth.example.com/validate"
)
```

### Role-Based Access Control
```python
# Register workflow with role requirements
app.register("admin_workflow", workflow.build(),
    required_roles=["admin", "operator"]
)

# Register with permission requirements
app.register("user_workflow", workflow.build(),
    required_permissions=["user:read", "user:write"]
)
```

## 🔍 Monitoring & Observability

### Prometheus Metrics
```python
app = Nexus(enable_monitoring=True)

app.monitoring.configure(
    backend="prometheus",
    metrics_port=9090,
    custom_metrics=[
        "workflow_execution_time",
        "workflow_success_rate",
        "channel_request_count"
    ]
)
```

### Logging Configuration
```python
app.logging.configure(
    level="INFO",
    format="json",
    output="stdout",
    include_request_id=True,
    include_user_id=True
)
```

### Health Checks
```python
# Custom health check
def custom_health_check():
    return {
        "database": db.health_check(),
        "external_api": check_external_api(),
        "cache": redis.ping()
    }

app.add_health_check(custom_health_check)
```

## ⚠️ Critical Rules

### ✅ ALWAYS DO
- Use `app.register()` to register workflows
- Call `workflow.build()` before registering
- Use `app.start()` to start all channels
- Configure authentication for production
- Enable monitoring for production deployments

### ❌ NEVER DO
- Import `from kailash.nexus import create_nexus` - Use `from nexus import Nexus`
- Use `app.register(workflow, name)` - Wrong parameter order
- Skip `workflow.build()` - Workflows must be built first
- Use default ports in production without checking availability
- Disable authentication in production

### 🔧 Common Patterns
```python
# Correct workflow registration
app.register("workflow_name", workflow.build())

# Correct parameter access in workflows
"code": "try:\n    result = input_data\nexcept NameError:\n    result = {}"

# Correct connection syntax
workflow.add_connection("source", "output_port", "target", "input_port")
```

## 🧪 Testing Patterns

### Unit Testing
```python
def test_nexus_workflow():
    app = Nexus()
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test", {
        "code": "result = {'test': 'passed'}"
    })
    
    app.register("test_workflow", workflow.build())
    
    # Test registration
    assert "test_workflow" in app.list_workflows()
    
    # Test execution
    result = app.execute("test_workflow", {})
    assert result["test"] == "passed"
```

### Integration Testing
```python
def test_multi_channel_integration():
    app = Nexus()
    app.register("test_workflow", workflow.build())
    
    # Test API channel
    api_response = requests.post("http://localhost:8000/workflows/test_workflow")
    assert api_response.status_code == 200
    
    # Test CLI channel
    cli_result = subprocess.run(["nexus", "run", "test_workflow"], 
                               capture_output=True, text=True)
    assert cli_result.returncode == 0
```

## 📚 Documentation Navigation

### Quick Reference
- **[Complete Documentation](docs/README.md)** - Full navigation
- **[Quick Start](docs/getting-started/quick-start.md)** - Get running in 1 minute
- **[Basic Usage](docs/getting-started/basic-usage.md)** - Essential patterns

### User Guides
- **[Zero Configuration](docs/user-guides/zero-configuration.md)** - Understanding zero-config
- **[Multi-Channel Usage](docs/user-guides/multi-channel-usage.md)** - API, CLI, MCP integration
- **[Workflow Registration](docs/user-guides/workflow-registration.md)** - Register workflows
- **[Session Management](docs/user-guides/session-management.md)** - Cross-channel sessions

### Technical Guides
- **[Architecture Overview](docs/technical/architecture-overview.md)** - System design
- **[Performance Guide](docs/technical/performance-guide.md)** - Optimization
- **[Security Guide](docs/technical/security-guide.md)** - Authentication & authorization
- **[Integration Guide](docs/technical/integration-guide.md)** - System integration

### Advanced Topics
- **[Plugin Development](docs/advanced/plugin-development.md)** - Custom plugins
- **[Production Deployment](docs/advanced/production-deployment.md)** - Scale deployment
- **[Custom Nodes](docs/advanced/custom-nodes.md)** - Build custom workflow nodes

### Reference
- **[API Reference](docs/reference/api-reference.md)** - Complete API documentation
- **[CLI Reference](docs/reference/cli-reference.md)** - Command-line interface
- **[Configuration Reference](docs/reference/configuration-reference.md)** - All options

---

**Nexus: One workflow, three channels, zero configuration.** 🚀

*Register once, access everywhere - API, CLI, and MCP unified.*