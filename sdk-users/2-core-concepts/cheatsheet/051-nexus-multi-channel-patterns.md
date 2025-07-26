# Nexus Multi-Channel Patterns

*Complete patterns for unified API, CLI, and MCP orchestration*

## 🌟 Basic Nexus Creation

### Zero-Configuration Start
```python
from nexus import Nexus

# Instant multi-channel platform - all channels enabled
nexus = Nexus()

# Provides:
# - REST API on port 8000 with OpenAPI docs
# - CLI interface with command discovery
# - MCP server on port 3000 for tool/resource access
# - WebSocket/SSE real-time communication
# - Unified session management across channels
# - Cross-channel event synchronization
```

### Channel-Specific Configuration
```python
# API-only nexus for pure REST services
api_nexus = Nexus(
    name="API Service",
    port=8080,
    enable_docs=True
)

# Development nexus with all channels
dev_nexus = Nexus(
    name="Development Platform",
    api_port=8000,
    mcp_port=3000,
    enable_hot_reload=True
)

# Production nexus with enterprise features
prod_nexus = Nexus(
    name="Production Platform",
    api_port=8000,
    mcp_port=3000,
    enable_auth=True,
    enable_monitoring=True
)
```

### Custom Channel Selection
```python
# Selective channel enabling
nexus = Nexus(
    name="Custom Platform",
    enable_api=True,     # REST API + WebSocket
    enable_cli=True,     # Command-line interface
    enable_mcp=False,    # Disable MCP for simpler setup
    api_port=8080,
    channels_synced=True # Synchronize sessions/events
)
```

## 🔗 Workflow Registration

### Cross-Channel Workflow Access
```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow once
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch", {"url": "https://api.example.com"})
workflow.add_node("LLMAgentNode", "analyze", {"model": "gpt-4"})
workflow.add_connection("fetch", "response", "analyze", "input_data")

# Register with nexus - automatically available on all channels
nexus.register_workflow("data_analysis", workflow.build())

# Now accessible via:
# - API: POST /api/executions {"workflow": "data_analysis", "inputs": {...}}
# - CLI: nexus run data_analysis --parameters='{...}'
# - MCP: Call "workflow_data_analysis" tool
```

### Channel-Specific Workflows
```python
# Register workflow with specific channel
api_workflow = WorkflowBuilder()
api_workflow.add_node("PythonCodeNode", "api_response", {
    "code": "return {'status': 'success', 'data': input_data}"
})

# Only available on API channel
nexus.register_workflow("api_only", api_workflow.build(), channels=["api"])

# Only available on MCP channel
nexus.register_workflow("mcp_tool", tool_workflow.build(), channels=["mcp"])
```

## 🎯 Session Management

### Unified Sessions Across Channels
```python
# Create session - automatically shared across channels
session_id = await nexus.create_session(
    user_id="user123",
    metadata={"role": "developer", "tenant": "acme"}
)

# Session accessible from:
# - API: Authorization: Bearer {session_token}
# - CLI: --session={session_id}
# - MCP: Session context in tool calls

# Session state syncs across all channels
await nexus.set_session_data(session_id, "preference", "dark_mode")
# Available immediately in API, CLI, and MCP contexts
```

### Cross-Channel Session Events
```python
# Events broadcast to all channels in session
await nexus.broadcast_to_session(session_id, {
    "type": "workflow_completed",
    "workflow": "data_analysis",
    "results": {...},
    "channels": ["api", "cli", "mcp"]  # Delivered to all
})

# Channels receive appropriate format:
# - API: WebSocket/SSE event
# - CLI: Console notification
# - MCP: Tool execution result
```

## 🔄 Real-Time Communication

### WebSocket Integration
```javascript
// Frontend WebSocket - unified across workflows
const ws = new WebSocket(`ws://localhost:8000/ws?session=${sessionId}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch(data.source_channel) {
        case 'api':
            handleAPIEvent(data);
            break;
        case 'cli':
            showCLIActivity(data);
            break;
        case 'mcp':
            updateMCPStatus(data);
            break;
    }
};
```

### Server-Sent Events (SSE)
```python
# SSE endpoint automatically provides cross-channel events
const eventSource = new EventSource(`/events?session=${sessionId}`);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    // Events include channel context
    console.log(`${data.channel}: ${data.event_type}`, data.payload);
};
```

## 🛠️ CLI Integration Patterns

### Command-Line Interface Access
```bash
# Direct workflow execution
nexus run data_analysis --parameters='{"url": "https://example.com"}'

# Interactive mode with session persistence
nexus shell --session=dev_session_123
> run data_analysis --url=https://example.com
> set preference dark_mode
> status --verbose

# Batch processing
nexus batch workflows.yaml --session=batch_001
```

### CLI Command Registration
```python
from kailash.nodes.system.command_parser import CommandParserNode

# Register custom CLI commands
nexus.register_cli_command(
    name="deploy",
    description="Deploy workflows to production",
    parameters={
        "environment": {"required": True, "help": "Target environment"},
        "force": {"action": "store_true", "help": "Force deployment"}
    },
    handler=deploy_workflow
)

# Available as: nexus deploy --environment=prod --force
```

## 🔌 MCP Integration Patterns

### Tool and Resource Registration
```python
# MCP automatically exposes workflows as tools
# But you can register custom tools too

async def custom_analyzer(data):
    """Custom MCP tool for data analysis."""
    return {"analysis": f"Processed {len(data)} items"}

# Register as MCP tool
nexus.register_mcp_tool(
    name="custom_analyzer",
    description="Analyze data with custom logic",
    handler=custom_analyzer,
    parameters={
        "data": {"type": "array", "description": "Data to analyze"}
    }
)

# Register MCP resource
nexus.register_mcp_resource(
    uri="workflow://templates",
    description="Available workflow templates",
    handler=get_workflow_templates
)
```

### MCP Service Discovery
```python
# Nexus automatically provides MCP service discovery
mcp_client = MCPClient("http://localhost:3000")

# Discover available tools
tools = await mcp_client.list_tools()
# Returns: workflow tools + custom tools + system tools

# Discover resources
resources = await mcp_client.list_resources()
# Returns: workflow schemas + custom resources + system info
```

## 📊 Monitoring & Health Checks

### Unified Health Monitoring
```python
# Comprehensive health check across all channels
health = await nexus.health_check()

# Returns:
{
    "healthy": True,
    "nexus_running": True,
    "channels": {
        "api": {"healthy": True, "port": 8000, "connections": 45},
        "cli": {"healthy": True, "sessions": 12},
        "mcp": {"healthy": True, "port": 3000, "tools": 8}
    },
    "sessions": {"total": 156, "active": 89},
    "workflows": {"registered": 12, "executing": 3}
}
```

### Performance Statistics
```python
# Unified statistics across channels
stats = await nexus.get_stats()

# Includes per-channel metrics:
{
    "nexus": {"name": "Platform", "uptime": 86400},
    "channels": {
        "api": {"requests": 15420, "avg_response": 45},
        "cli": {"commands": 892, "avg_execution": 120},
        "mcp": {"tool_calls": 2341, "avg_latency": 23}
    },
    "sessions": {"peak": 234, "current": 156},
    "workflows": {"total_executions": 8932, "success_rate": 0.997}
}
```

## 🚀 Advanced Patterns

### Custom Channel Development
```python
from kailash.channels.base import Channel, ChannelConfig, ChannelType

class CustomChannel(Channel):
    """Custom channel implementation."""

    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        # Custom initialization

    async def start(self):
        # Start custom channel
        pass

    async def handle_request(self, request):
        # Handle custom requests
        pass

# Register custom channel
nexus.register_channel("custom", CustomChannel(config))
```

### Event-Driven Workflows
```python
# Workflows triggered by cross-channel events
event_workflow = WorkflowBuilder()
event_workflow.add_node("PythonCodeNode", "process_event", {
    "code": """
# Process events from any channel
if event_source == 'cli':
    result = process_cli_event(event_data)
elif event_source == 'api':
    result = process_api_event(event_data)
elif event_source == 'mcp':
    result = process_mcp_event(event_data)
"""
})

nexus.register_event_workflow("cross_channel_processor", event_workflow.build())
```

### Enterprise Security Integration
```python
# Unified authentication across channels
nexus = Nexus(
    auth_provider="enterprise_ldap",
    enable_rbac=True,
    security_config={
        "api": {"require_https": True, "rate_limit": 1000},
        "cli": {"require_auth": True, "session_timeout": 3600},
        "mcp": {"require_auth": True, "tool_permissions": True}
    }
)
```

## 🎯 Quick Integration Checklist

### Essential Nexus Setup
- [ ] **Channel Selection**: Choose API/CLI/MCP combination
- [ ] **Session Management**: Configure unified sessions
- [ ] **Workflow Registration**: Register workflows for cross-channel access
- [ ] **Real-time Events**: Set up WebSocket/SSE for live updates
- [ ] **Health Monitoring**: Configure health checks and statistics
- [ ] **Authentication**: Enable auth if needed across channels
- [ ] **Command Interface**: Set up CLI commands and MCP tools
- [ ] **Event Routing**: Configure cross-channel event distribution

### Production Deployment
- [ ] **Performance Tuning**: Configure appropriate ports and workers
- [ ] **Security Hardening**: Enable authentication and rate limiting
- [ ] **Monitoring Setup**: Configure metrics collection and alerting
- [ ] **Backup Strategy**: Plan for session persistence and recovery
- [ ] **Load Balancing**: Configure for high availability
- [ ] **Documentation**: Document channel APIs and CLI commands

## 📚 Related Patterns

- **[Enterprise Gateway Patterns](../enterprise/gateway-patterns.md)** - Single-channel API gateway patterns
- **[MCP Integration](025-mcp-integration.md)** - Detailed MCP protocol patterns
- **[Middleware Patterns](../enterprise/middleware-patterns.md)** - Advanced middleware configuration
- **[Session Management](../enterprise/security-patterns.md)** - Authentication and session security
- **[Real-time Communication](../frontend-integration/realtime-patterns.md)** - WebSocket and SSE patterns

---

**Need unified multi-channel orchestration?** Nexus provides instant API, CLI, and MCP interfaces with zero configuration. Start with `Nexus()` and progressively enhance with enterprise features.
