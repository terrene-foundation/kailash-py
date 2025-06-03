# Multi-Workflow API Gateway

The Multi-Workflow API Gateway provides a unified entry point for managing and executing multiple Kailash workflows through a single server with dynamic routing, MCP integration, and production-ready features.

## Overview

The gateway architecture solves the problem of running multiple workflows with different endpoints alongside MCP (Model Context Protocol) servers. Instead of running each workflow as a separate service, the gateway provides:

- **Unified Access**: Single server managing all workflows
- **Dynamic Routing**: Path-based routing to different workflows
- **MCP Integration**: AI-powered tools available to all workflows
- **Resource Efficiency**: Shared infrastructure and thread pools
- **Production Features**: Health monitoring, WebSocket support, CORS

## Quick Start

```python
from kailash.api.gateway import WorkflowAPIGateway
from kailash.workflow import Workflow

# Create gateway
gateway = WorkflowAPIGateway(
    title="My Platform",
    description="Unified workflow platform",
    max_workers=10
)

# Register workflows
gateway.register_workflow("process", data_processing_workflow)
gateway.register_workflow("analyze", analytics_workflow)

# Start server
gateway.run(port=8000)
```

## Core Components

### WorkflowAPIGateway

The main gateway class that manages multiple workflows.

```python
class WorkflowAPIGateway:
    def __init__(
        self,
        title: str = "Kailash Workflow Gateway",
        description: str = "Unified API for Kailash workflows",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: List[str] = None
    ):
        """Initialize the API gateway."""
```

**Parameters:**
- `title`: API title shown in documentation
- `description`: API description
- `version`: API version string
- `max_workers`: Thread pool size for synchronous execution
- `cors_origins`: List of allowed CORS origins

### Workflow Registration

Register workflows to make them available through the gateway:

```python
gateway.register_workflow(
    name="sales",
    workflow=sales_workflow,
    description="Sales data processing",
    version="1.0.0",
    tags=["sales", "data"]
)
```

This creates endpoints:
- `POST /sales/execute` - Execute the workflow
- `GET /sales/workflow/info` - Get workflow information
- `GET /sales/health` - Check workflow health
- `GET /sales/docs` - Interactive API documentation

### MCP Integration

Integrate AI-powered tools through MCP servers:

```python
from kailash.api.mcp_integration import MCPIntegration

# Create MCP server
mcp = MCPIntegration("ai_tools", "AI-powered analysis tools")

# Add tools
mcp.add_tool(
    "sentiment_analysis",
    analyze_sentiment_function,
    "Analyze text sentiment",
    parameters={
        "text": {"type": "string", "required": True}
    }
)

# Register with gateway
gateway.register_mcp_server("ai", mcp)
```

Use MCP tools in workflows:

```python
from kailash.api.mcp_integration import MCPToolNode

# Create node that uses MCP tool
sentiment_node = MCPToolNode(
    mcp_server="ai_tools",
    tool_name="sentiment_analysis"
)
workflow.add_node("analyze_sentiment", sentiment_node)
```

## Gateway Endpoints

### Root Endpoints

- `GET /` - Gateway information
  ```json
  {
    "name": "My Platform",
    "version": "1.0.0",
    "workflows": ["sales", "analytics"],
    "mcp_servers": ["ai_tools"]
  }
  ```

- `GET /workflows` - List all workflows
  ```json
  {
    "sales": {
      "type": "embedded",
      "description": "Sales processing",
      "version": "1.0.0",
      "tags": ["sales"],
      "endpoints": [
        "/sales/execute",
        "/sales/workflow/info",
        "/sales/health",
        "/sales/docs"
      ]
    }
  }
  ```

- `GET /health` - Gateway health check
  ```json
  {
    "status": "healthy",
    "workflows": {
      "sales": "healthy",
      "analytics": "healthy"
    },
    "mcp_servers": {
      "ai_tools": "healthy"
    }
  }
  ```

- `WS /ws` - WebSocket for real-time updates

### Workflow Endpoints

Each registered workflow gets its own set of endpoints under `/{workflow_name}/`:

- `POST /{name}/execute` - Execute workflow
- `GET /{name}/workflow/info` - Workflow metadata
- `GET /{name}/health` - Workflow health
- `GET /{name}/docs` - Interactive docs

## Deployment Patterns

### Pattern 1: Single Gateway (Recommended)

Best for most use cases where all workflows have similar resource requirements.

```python
gateway = WorkflowAPIGateway(title="Company Platform")
gateway.register_workflow("sales", sales_wf)
gateway.register_workflow("analytics", analytics_wf)
gateway.register_workflow("reports", reports_wf)
gateway.run(port=8000)
```

### Pattern 2: Hybrid Deployment

For mixed workloads with some compute-intensive workflows.

```python
# Light workflows embedded
gateway.register_workflow("api", api_workflow)
gateway.register_workflow("data", data_workflow)

# Heavy workflows proxied to separate services
gateway.proxy_workflow(
    "ml_training",
    "http://ml-service:8001",
    health_check="/health"
)
```

### Pattern 3: High Availability

For production environments requiring high uptime.

```yaml
# docker-compose.yml
services:
  gateway1:
    image: kailash-gateway
    environment:
      - INSTANCE_ID=1
  
  gateway2:
    image: kailash-gateway
    environment:
      - INSTANCE_ID=2
  
  haproxy:
    image: haproxy
    depends_on:
      - gateway1
      - gateway2
    ports:
      - "80:80"
```

### Pattern 4: Kubernetes

For cloud-native deployments with auto-scaling.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kailash-gateway
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: gateway
        image: kailash-gateway:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kailash-gateway-hpa
spec:
  scaleTargetRef:
    kind: Deployment
    name: kailash-gateway
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Advanced Features

### WebSocket Support

The gateway provides WebSocket support for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  // Subscribe to workflow events
  ws.send(JSON.stringify({
    type: 'subscribe',
    workflow: 'sales'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Workflow update:', data);
};
```

### Dynamic Workflow Management

Add or remove workflows at runtime:

```python
# Add new workflow
gateway.register_workflow("new_workflow", new_wf)

# Remove workflow (planned feature)
# gateway.unregister_workflow("old_workflow")
```

### Custom Middleware

Add custom middleware for authentication, logging, etc.:

```python
from fastapi import Request

@gateway.app.middleware("http")
async def add_custom_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Custom-Header"] = "value"
    return response
```

## Example: Complete Platform

```python
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Create MCP server with AI tools
mcp = MCPIntegration("ai_tools")
mcp.add_tool("analyze", analyze_data)
mcp.add_tool("predict", make_predictions)

# Create gateway
gateway = WorkflowAPIGateway(
    title="Enterprise Data Platform",
    description="Unified platform for data processing and analytics",
    version="2.0.0",
    max_workers=20,
    cors_origins=["https://app.company.com"]
)

# Register MCP
gateway.register_mcp_server("ai", mcp)

# Register workflows
gateway.register_workflow(
    "ingest",
    data_ingestion_workflow,
    description="Data ingestion and validation",
    tags=["data", "etl"]
)

gateway.register_workflow(
    "process",
    data_processing_workflow,
    description="Data transformation and enrichment",
    tags=["data", "processing"]
)

gateway.register_workflow(
    "analyze",
    analytics_workflow,
    description="Analytics and insights generation",
    tags=["analytics", "reporting"]
)

# Start server
if __name__ == "__main__":
    gateway.run(
        host="0.0.0.0",
        port=8000,
        ssl_keyfile="ssl/key.pem",
        ssl_certfile="ssl/cert.pem"
    )
```

## Best Practices

1. **Workflow Naming**: Use clear, descriptive names for workflows
2. **Error Handling**: Implement proper error handling in workflows
3. **Monitoring**: Use the health endpoints for monitoring
4. **Security**: Implement authentication/authorization as needed
5. **Resource Management**: Set appropriate thread pool sizes
6. **Documentation**: Keep workflow descriptions up to date

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Find process using port
   lsof -i :8000
   # Kill process
   kill -9 <PID>
   ```

2. **Workflow Registration Fails**
   - Check workflow has unique name
   - Ensure workflow is properly initialized
   - Verify no circular dependencies

3. **High Memory Usage**
   - Reduce max_workers setting
   - Implement workflow cleanup
   - Use proxied workflows for heavy processing

## See Also

- [WorkflowAPI Documentation](workflow_api.md) - Single workflow API wrapper
- [MCP Integration Guide](mcp_integration.md) - MCP server details
- [Gateway Examples](../../examples/integration_examples/) - Complete examples
- [ADR-0017](../adr/0017-multi-workflow-api-architecture.md) - Architecture decision