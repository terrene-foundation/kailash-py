f# ADR-0017: Multi-Workflow API Architecture

## Status
Proposed

## Context
Users need to run multiple Kailash workflows simultaneously, each with different endpoints. Additionally, MCP (Model Context Protocol) servers need to be integrated into the same system. The current WorkflowAPIWrapper creates a single FastAPI application per workflow, which doesn't scale well for multiple workflows.

## Decision
We will implement a unified API gateway architecture that:
1. Manages multiple workflows through a registry pattern
2. Provides dynamic endpoint routing
3. Integrates MCP servers alongside workflow endpoints
4. Supports both synchronous and asynchronous execution
5. Enables workflow discovery and management

## Architecture Components

### 1. Workflow Registry
- Central registry to manage all workflows
- Dynamic loading and unloading of workflows
- Metadata storage (name, version, description, endpoints)

### 2. API Gateway
- Single FastAPI application managing all endpoints
- Dynamic route registration
- Unified authentication and middleware
- WebSocket support for real-time updates

### 3. MCP Integration Layer
- MCP server manager
- Tool registration from MCP to workflows
- Bidirectional communication between workflows and MCP

### 4. Execution Manager
- Thread pool for synchronous workflows
- Async event loop for async workflows
- Resource allocation and limits
- Execution monitoring and metrics

## Implementation Approach

### Option 1: Unified Server (Recommended)
```python
# Single server managing multiple workflows
app = WorkflowAPIGateway()
app.register_workflow("sales", sales_workflow)
app.register_workflow("analytics", analytics_workflow)
app.register_mcp_server("tools", mcp_server)
app.run()
```

### Option 2: Microservices with Proxy
```python
# Each workflow runs independently, proxied through gateway
gateway = WorkflowProxy()
gateway.add_service("sales", "http://localhost:8001")
gateway.add_service("analytics", "http://localhost:8002")
```

### Option 3: Hybrid Approach
```python
# Core workflows in unified server, compute-heavy in separate processes
app = HybridWorkflowServer()
app.embed_workflow("api_endpoints", lightweight_workflow)
app.proxy_workflow("ml_pipeline", "http://ml-service:8080")
```

## Consequences

### Positive
- Single entry point for all workflows
- Centralized management and monitoring
- Efficient resource utilization
- Easy service discovery
- Unified authentication/authorization

### Negative
- Single point of failure (mitigated by clustering)
- More complex than single workflow deployment
- Requires careful resource management
- Potential for one workflow to affect others

### Neutral
- Requires migration from single workflow pattern
- New deployment considerations
- Additional monitoring requirements
