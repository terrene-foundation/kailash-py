# ADR-0029: MCP Ecosystem Architecture

## Status
Accepted

## Context
The Kailash SDK needs to provide a zero-code solution for deploying workflows, similar to the MCP Gateway project. This would enable non-technical users to create and deploy workflows through a visual interface without writing code.

Key requirements:
- Visual workflow builder with drag-and-drop interface
- Integration with MCP (Model Context Protocol) servers
- REST API for programmatic access
- Real-time execution monitoring
- Pre-built workflow templates

## Decision

### Overall Architecture
We will implement a three-tier architecture:

1. **Web UI Layer** - Interactive dashboard for visual workflow building
2. **MCP Ecosystem Gateway** - Middleware that bridges web UI with Kailash SDK
3. **Kailash SDK Core** - Existing workflow engine and node execution

### Technology Choices

#### Frontend Stack
We chose a **vanilla web technology approach** for the frontend:
- **HTML5** - Embedded directly in Python as HTMLResponse
- **Vanilla JavaScript** - No frameworks, using native APIs
- **CSS3** - Modern layouts without CSS frameworks
- **FastAPI** - Python web framework for serving the UI

Rationale:
1. Zero build process required
2. No external dependencies to manage
3. Single file deployment
4. Easy to understand and maintain
5. Proves that complex UIs can be built without heavy frameworks

#### Backend Integration
- **WorkflowAPIGateway** - Base class for REST API management
- **MCP Server Registry** - Manages MCP server connections
- **Dynamic Node Generation** - Creates Kailash nodes from MCP tools

### Key Components

#### 1. Visual Workflow Builder
```javascript
// Native drag-and-drop for node placement
canvas.addEventListener('drop', (e) => {
    const nodeType = e.dataTransfer.getData('nodeType');
    addNodeToCanvas(nodeType);
});
```

#### 2. MCP Server Integration
```python
class MCPServerRegistry:
    async def register_server(self, name: str, config: dict):
        # Start MCP server process
        # Discover available tools
        # Create corresponding Kailash nodes
```

#### 3. Zero-Code Deployment
```python
@app.post("/api/deploy/{workflow_id}")
async def deploy_workflow(workflow_id: str):
    # Convert visual definition to Kailash workflow
    # Register with runtime
    # Return deployment status
```

### File Organization
- `examples/integration_examples/` - Working examples and demos
  - `mcp_ecosystem_demo.py` - Simplified demo with mock data
  - `mcp_ecosystem_fixed.py` - Full implementation with Kailash SDK
  - `README.md` - Comprehensive documentation
  - Supporting files (run scripts, tests)

## Consequences

### Positive
- Non-technical users can create workflows visually
- No build tools or npm dependencies required
- Easy to deploy and maintain
- Extensible architecture for adding new MCP servers
- Provides both visual and programmatic interfaces

### Negative
- Limited to browser capabilities without frameworks
- Manual DOM manipulation can be error-prone
- Polling for updates instead of WebSockets
- No component reusability without a framework

### Future Enhancements
1. WebSocket support for real-time updates
2. Persistent workflow storage
3. User authentication and multi-tenancy
4. Export/import workflow definitions
5. Integration with more MCP servers
6. Optional React/Vue integration for complex UIs

## References
- [MCP Gateway Project](https://github.com/mcp-ecosystem/mcp-gateway)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [FastAPI Documentation](https://fastapi.tiangolo.com)