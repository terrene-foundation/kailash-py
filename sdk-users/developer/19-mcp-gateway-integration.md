# MCP Gateway Integration Guide

This guide covers how to integrate MCP (Model Context Protocol) servers with Kailash gateways, enabling workflows to use external tools and resources through a unified interface.

## Table of Contents
1. [Overview](#overview)
2. [Gateway Architecture](#gateway-architecture)
3. [Creating a Gateway with MCP Support](#creating-a-gateway-with-mcp-support)
4. [Registering MCP Servers](#registering-mcp-servers)
5. [Using MCPToolNode in Workflows](#using-mcptoolnode-in-workflows)
6. [Complete Examples](#complete-examples)
7. [Best Practices](#best-practices)

## Overview

The Kailash SDK provides a unified `create_gateway()` function that creates an API Gateway supporting multiple interfaces:

- **REST API**: HTTP endpoints for workflow management
- **WebSocket**: Real-time communication
- **CLI Support**: Via gateway client
- **MCP Integration**: External tool and resource access

All gateway operations are **fully async**, providing:
- Non-blocking I/O operations
- Concurrent workflow execution
- Real-time updates via WebSocket/SSE
- Efficient resource utilization

## Gateway Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   CLI App   │     │  Web App     │     │  MCP Client │
└──────┬──────┘     └──────┬───────┘     └──────┬──────┘
       │                   │                     │
       └───────────────────┴─────────────────────┘
                           │
                    ┌──────▼────────┐
                    │  API Gateway  │ ← create_gateway()
                    │               │
                    │ - REST API    │
                    │ - WebSocket   │
                    │ - Auth        │
                    │ - MCP Servers │
                    └──────┬────────┘
                           │
                    ┌──────▼────────┐
                    │   Middleware  │
                    │               │
                    │ - AgentUI     │
                    │ - Realtime    │
                    │ - Workflows   │
                    └───────────────┘
```

## Creating a Gateway with MCP Support

### Basic Gateway Creation

```python
from kailash.middleware import create_gateway

# Create gateway with API and MCP support
gateway = create_gateway(
    title="My App Gateway",
    description="API with MCP tool integration",
    cors_origins=["http://localhost:3000"],
    enable_docs=True,
    enable_auth=True
)

# Run the async gateway
gateway.run(host="0.0.0.0", port=8000)
```

### Gateway with Custom Configuration

```python
from kailash.middleware import create_gateway, AgentUIMiddleware

# Create custom agent UI middleware
agent_ui = AgentUIMiddleware(
    max_sessions=1000,
    session_timeout_minutes=60,
    enable_persistence=True
)

# Create gateway with custom middleware
gateway = create_gateway(
    agent_ui_middleware=agent_ui,
    title="Enterprise Gateway",
    cors_origins=["https://myapp.com"],
    enable_auth=True,
    database_url="postgresql://user:pass@localhost/db"
)
```

## Registering MCP Servers

### Method 1: Simple MCP Integration

```python
from kailash.api.mcp_integration import MCPIntegration

# Create MCP integration
mcp = MCPIntegration(
    name="tools_server",
    description="Utility tools for workflows"
)

# Add async tool
async def search_web(query: str, max_results: int = 10):
    """Search the web for information."""
    # Tool implementation
    results = await fetch_search_results(query, max_results)
    return {"results": results}

# Add sync tool
def calculate(expression: str):
    """Calculate mathematical expressions."""
    result = eval(expression, {"__builtins__": {}}, {})
    return {"result": result}

# Register tools with parameter schemas
mcp.add_tool(
    name="search",
    function=search_web,
    description="Search the web",
    parameters={
        "query": {"type": "string", "required": True},
        "max_results": {"type": "integer", "default": 10}
    }
)

mcp.add_tool(
    name="calculate",
    function=calculate,
    description="Calculate math expressions",
    parameters={
        "expression": {"type": "string", "required": True}
    }
)

# Register MCP server with gateway (if using WorkflowAPIGateway)
# gateway.register_mcp_server("tools", mcp)
```

### Method 2: Enterprise MCP Server

```python
from kailash.middleware import MiddlewareMCPServer
from kailash.middleware.mcp import MCPServerConfig

# Configure MCP server
config = MCPServerConfig()
config.name = "enterprise-tools"
config.enable_caching = True
config.enable_metrics = True
config.cache_ttl = 300  # 5 minutes

# Create MCP server connected to gateway
mcp_server = MiddlewareMCPServer(
    config=config,
    agent_ui=gateway.agent_ui  # Connect to gateway's agent UI
)

# Register enterprise tools
async def analyze_document(
    content: str, 
    analysis_type: str = "summary",
    max_length: int = 500
):
    """Analyze document content using AI."""
    # This could use LLMAgentNode internally
    from kailash.nodes.ai import LLMAgentNode
    
    llm = LLMAgentNode(
        name="analyzer",
        model="gpt-4",
        system_prompt=f"Perform {analysis_type} analysis"
    )
    
    result = await llm.async_run(prompt=content)
    return {
        "analysis": result["response"][:max_length],
        "type": analysis_type
    }

mcp_server.register_tool(
    name="analyze_document",
    function=analyze_document,
    description="AI-powered document analysis",
    parameters={
        "content": {"type": "string", "required": True},
        "analysis_type": {
            "type": "string", 
            "default": "summary",
            "enum": ["summary", "sentiment", "key_points", "entities"]
        },
        "max_length": {"type": "integer", "default": 500}
    }
)

# Start the MCP server
await mcp_server.start()
```

## Using MCPToolNode in Workflows

### Basic MCPToolNode Usage

```python
from kailash.api.mcp_integration import MCPToolNode
from kailash.workflow.builder import WorkflowBuilder

# Create workflow builder
builder = WorkflowBuilder("mcp_workflow")

# Add MCP tool node
search_node = MCPToolNode(
    mcp_server="tools",  # Name of registered MCP server
    tool_name="search",   # Name of tool to execute
    parameter_mapping={   # Optional: map workflow inputs to tool params
        "search_query": "query"  # workflow key -> tool param
    }
)

# Add node to workflow
builder.add_node("web_search", search_node)

# Add other nodes
builder.add_node("processor", PythonCodeNode.from_function(
    lambda results: {"summary": f"Found {len(results)} items"}
))

# Connect nodes
builder.add_connection("web_search", "result", "processor", "results")

# Build and register workflow
workflow = builder.build()
await gateway.agent_ui.register_workflow(
    workflow_id="search_workflow",
    workflow=workflow,
    make_shared=True  # Available to all sessions
)
```

### Advanced MCPToolNode with Dynamic Parameters

```python
from kailash.nodes.base import Node

class DynamicMCPToolNode(Node):
    """MCPToolNode that determines tool at runtime."""
    
    def __init__(self, mcp_server: str):
        super().__init__(name="dynamic_mcp")
        self.mcp_server = mcp_server
        self._mcp_integration = None
    
    def set_mcp_integration(self, mcp: MCPIntegration):
        self._mcp_integration = mcp
    
    def process(self, tool_name: str, **kwargs):
        """Execute MCP tool dynamically."""
        if not self._mcp_integration:
            raise RuntimeError("MCP integration not set")
        
        # Execute tool synchronously
        return self._mcp_integration.execute_tool_sync(
            tool_name, 
            kwargs
        )

# Use in workflow
builder = WorkflowBuilder("dynamic_mcp_workflow")
dynamic_node = DynamicMCPToolNode("tools")
builder.add_node("dynamic_tool", dynamic_node)
```

## Complete Examples

### Example 1: Search and Analyze Workflow

```python
import asyncio
from kailash.middleware import create_gateway
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode

async def create_search_analyze_gateway():
    # 1. Create gateway
    gateway = create_gateway(
        title="Search & Analyze Gateway",
        cors_origins=["*"],
        enable_docs=True
    )
    
    # 2. Create MCP server with search and analysis tools
    mcp = MCPIntegration("analysis_tools", "Search and analysis tools")
    
    # Search tool
    async def search_articles(topic: str, count: int = 5):
        # Simulate article search
        return {
            "articles": [
                {"title": f"Article {i} about {topic}", "url": f"https://example.com/{i}"}
                for i in range(count)
            ]
        }
    
    # Analysis tool using LLM
    async def analyze_articles(articles: list, analysis_goal: str):
        llm = LLMAgentNode(
            name="analyzer",
            model="gpt-3.5-turbo",
            system_prompt="You are an expert article analyzer."
        )
        
        article_text = "\n".join([a["title"] for a in articles])
        prompt = f"Analyze these articles for: {analysis_goal}\n\n{article_text}"
        
        result = await llm.async_run(prompt=prompt)
        return {"analysis": result["response"]}
    
    # Register tools
    mcp.add_tool("search_articles", search_articles, "Search for articles", {
        "topic": {"type": "string", "required": True},
        "count": {"type": "integer", "default": 5}
    })
    
    mcp.add_tool("analyze_articles", analyze_articles, "Analyze articles", {
        "articles": {"type": "array", "required": True},
        "analysis_goal": {"type": "string", "required": True}
    })
    
    # 3. Create workflow using MCP tools
    builder = WorkflowBuilder("search_analyze_workflow")
    
    # Search node
    search = MCPToolNode("analysis_tools", "search_articles")
    builder.add_node("search", search)
    
    # Analyze node
    analyze = MCPToolNode("analysis_tools", "analyze_articles")
    builder.add_node("analyze", analyze)
    
    # Connect nodes
    builder.add_connection("search", "articles", "analyze", "articles")
    
    # Register workflow
    await gateway.agent_ui.register_workflow(
        "search_analyze",
        builder.build(),
        make_shared=True
    )
    
    return gateway

# Run the gateway
if __name__ == "__main__":
    gateway = asyncio.run(create_search_analyze_gateway())
    
    # Gateway provides endpoints:
    # POST /api/sessions - Create session
    # POST /api/executions - Execute workflow
    # GET /api/workflows - List workflows
    # WS /ws - WebSocket for real-time updates
    
    gateway.run(port=8000)
```

### Example 2: Multi-Tool Processing Pipeline

```python
async def create_processing_gateway():
    gateway = create_gateway(
        title="Processing Pipeline Gateway",
        enable_auth=True
    )
    
    # Create MCP with multiple tool categories
    mcp = MCPIntegration("processing_tools")
    
    # Data extraction tools
    async def extract_text(file_path: str, format: str = "plain"):
        # Extract text from various formats
        return {"text": f"Extracted text from {file_path}"}
    
    async def extract_data(text: str, schema: dict):
        # Extract structured data
        return {"data": {"example": "structured data"}}
    
    # Processing tools
    def transform_data(data: dict, operations: list):
        # Apply transformations
        return {"transformed": data}
    
    async def validate_data(data: dict, rules: dict):
        # Validate against rules
        return {"valid": True, "errors": []}
    
    # Register all tools
    tools = [
        ("extract_text", extract_text, {"file_path": {"type": "string", "required": True}}),
        ("extract_data", extract_data, {"text": {"type": "string", "required": True}}),
        ("transform", transform_data, {"data": {"type": "object", "required": True}}),
        ("validate", validate_data, {"data": {"type": "object", "required": True}})
    ]
    
    for name, func, params in tools:
        mcp.add_tool(name, func, f"{name} operation", params)
    
    # Create complex workflow
    builder = WorkflowBuilder("processing_pipeline")
    
    # Add all MCP tool nodes
    nodes = {}
    for tool_name, _, _ in tools:
        node = MCPToolNode("processing_tools", tool_name)
        nodes[tool_name] = tool_name + "_node"
        builder.add_node(nodes[tool_name], node)
    
    # Connect in pipeline
    builder.add_connection(nodes["extract_text"], "text", nodes["extract_data"], "text")
    builder.add_connection(nodes["extract_data"], "data", nodes["transform"], "data")
    builder.add_connection(nodes["transform"], "transformed", nodes["validate"], "data")
    
    # Register workflow
    await gateway.agent_ui.register_workflow(
        "processing_pipeline",
        builder.build(),
        make_shared=True
    )
    
    return gateway
```

## Best Practices

### 1. **Tool Design**
- Keep tools focused on a single responsibility
- Use clear, descriptive parameter names
- Provide comprehensive parameter schemas
- Handle errors gracefully and return structured errors

### 2. **Async Considerations**
- Use async tools for I/O operations (API calls, database queries)
- Use sync tools for CPU-bound operations
- The gateway handles both transparently

### 3. **Parameter Mapping**
- Use `parameter_mapping` in MCPToolNode for clear workflow interfaces
- Map workflow-friendly names to tool-specific parameters
- Document expected input/output formats

### 4. **Error Handling**
```python
async def robust_tool(param: str):
    try:
        result = await risky_operation(param)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 5. **Caching and Performance**
```python
# Use enterprise MCP server for caching
config = MCPServerConfig()
config.enable_caching = True
config.cache_ttl = 300  # Cache for 5 minutes

mcp_server = MiddlewareMCPServer(config=config)
```

### 6. **Security**
- Validate all tool inputs
- Use the gateway's built-in authentication
- Limit tool permissions based on user roles
- Audit tool usage via gateway logging

## Summary

The Kailash gateway provides seamless MCP integration:

1. **Unified Interface**: Single `create_gateway()` function for all needs
2. **Async Throughout**: Non-blocking execution for performance
3. **Flexible Tools**: Support for sync and async tools
4. **Enterprise Features**: Caching, metrics, authentication
5. **Workflow Integration**: MCPToolNode makes tools first-class workflow citizens

This architecture enables building sophisticated applications where workflows can leverage external tools and services while maintaining the benefits of the Kailash SDK's workflow management, monitoring, and execution capabilities.