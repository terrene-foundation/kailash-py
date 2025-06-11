# MCP Integration

## Enhanced MCP Server (New!)

Create production-ready MCP servers with caching, metrics, and configuration out of the box:

```python
from kailash.mcp import MCPServer

# Production-ready server with all enhancements
server = MCPServer("my-server")

@server.tool(cache_key="expensive", cache_ttl=600)  # Cache for 10 minutes
async def expensive_operation(data: str) -> dict:
    """Expensive operation with automatic caching and metrics."""
    # First call: executes and caches
    # Subsequent calls: returns cached result
    return {"processed": data, "result": "..."}

@server.tool(format_response="markdown")  # Format for LLMs
async def get_status(service: str) -> dict:
    """Service status with markdown formatting."""
    return {"title": f"{service} Status", "status": "healthy"}

if __name__ == "__main__":
    server.run()  # Includes caching, metrics, config management
```

### Enhanced Features
- **Automatic caching** with TTL
- **Metrics collection** (latency, error rates)
- **Configuration management** (YAML, env vars)
- **Response formatting** (JSON, Markdown, tables)
- **Production monitoring** built-in

### Simple Server for Prototyping
```python
from kailash.mcp import SimpleMCPServer

# Minimal features for quick development
server = SimpleMCPServer("prototype", "Quick prototype")

@server.tool()
def calculate(a: float, b: float) -> float:
    return a + b

server.run()
```

## LLMAgentNode with Built-in MCP

The **new pattern** integrates MCP directly into LLMAgentNode, eliminating the need for separate MCPClient nodes.

### ✅ New Pattern (Recommended)
```python
from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Single node with integrated MCP support
workflow = Workflow("mcp-integrated", "MCP Integration")
workflow.add_node("agent", LLMAgentNode(name="mcp_enabled_agent"))

# Configure MCP servers in parameters
runtime = LocalRuntime()
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.1:8b-instruct-q8_0",
        "messages": [
            {"role": "user", "content": "What data is available in the MCP servers?"}
        ],
        "mcp_servers": [
            {
                "name": "data-server",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_data_server"]
            }
        ],
        "auto_discover_tools": True
    }
})
```

### ❌ Old Pattern (Deprecated)
```python
# DON'T DO THIS - Requires two separate nodes and manual connection
from kailash.nodes.mcp import MCPClient  # Deprecated

workflow.add_node("mcp_client", MCPClient())  # Deprecated
workflow.add_node("agent", LLMAgentNode())
workflow.connect("mcp_client", "agent")
```

## MCP Server Configuration

### STDIO Transport (Local Commands)
```python
# Local MCP server via command line
mcp_servers = [
    {
        "name": "filesystem-server",
        "transport": "stdio",
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem", "/path/to/data"]
    },
    {
        "name": "sqlite-server",
        "transport": "stdio",
        "command": "mcp-server-sqlite",
        "args": ["--db-path", "/path/to/database.db"]
    }
]
```

### HTTP Transport (Remote Servers)
```python
# Remote MCP server via HTTP
mcp_servers = [
    {
        "name": "api-server",
        "transport": "http",
        "url": "http://localhost:8080",
        "headers": {
            "Authorization": "Bearer your-token",
            "Content-Type": "application/json"
        }
    }
]
```

### Multiple Server Configuration
```python
# Combine multiple MCP servers
mcp_servers = [
    {
        "name": "knowledge-base",
        "transport": "stdio",
        "command": "mcp-kb-server"
    },
    {
        "name": "data-analytics",
        "transport": "http",
        "url": "https://analytics.company.com/mcp",
        "headers": {"API-Key": "your-key"}
    },
    {
        "name": "document-store",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "document_server", "--path", "/docs"]
    }
]

results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "mcp_servers": mcp_servers,
        "auto_discover_tools": True,
        "messages": [
            {"role": "user", "content": "Search all available data sources for project information"}
        ]
    }
})
```

## Automatic Tool Discovery

### Enable Auto-Discovery
```python
# Automatically discover and use MCP tools
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "Search for customer data from last quarter"}
        ],
        "mcp_servers": [
            {
                "name": "data-server",
                "transport": "stdio",
                "command": "mcp-data-server"
            }
        ],
        "auto_discover_tools": True,  # Key setting
        "tool_discovery_config": {
            "max_tools": 50,
            "filter_by_relevance": True,
            "cache_discoveries": True
        }
    }
})

# Check what tools were discovered
if results["agent"]["success"]:
    context = results["agent"]["context"]
    discovered_tools = context.get("tools_available", [])
    print(f"Discovered {len(discovered_tools)} MCP tools:")
    for tool in discovered_tools:
        print(f"- {tool['name']}: {tool['description']}")
```

## MCP Context and Resources

### Resource Access Patterns
```python
# Access specific MCP resources
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "mcp_servers": [
            {
                "name": "knowledge-base",
                "transport": "stdio",
                "command": "mcp-kb-server"
            }
        ],
        "mcp_context": [
            "data://sales/2024",              # Data resource
            "resource://templates/analysis",   # Template resource
            "knowledge://policies/compliance", # Knowledge resource
            "registry://stats"                 # Registry statistics
        ],
        "messages": [
            {"role": "user", "content": "Create a compliance report using the available templates"}
        ]
    }
})

# Resources are automatically injected into conversation context
if results["agent"]["success"]:
    mcp_resources = results["agent"]["context"]["mcp_resources_used"]
    print(f"Used {len(mcp_resources)} MCP resources")
```

### Dynamic Resource Discovery
```python
# Let the agent discover resources dynamically
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "mcp_servers": [{"name": "data-server", "transport": "stdio", "command": "mcp-server"}],
        "auto_discover_tools": True,
        "auto_discover_resources": True,  # Also discover resources
        "messages": [
            {"role": "user", "content": "Find all available data and create a summary report"}
        ],
        "discovery_config": {
            "resource_types": ["data", "templates", "knowledge"],
            "max_resources": 20,
            "relevance_threshold": 0.7
        }
    }
})
```

## Tool Calling with MCP

### Explicit Tool Calling
```python
# Configure for tool calling with MCP tools
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "temperature": 0,  # Use 0 for tool calling
        "messages": [
            {"role": "user", "content": "Create a sales report for Q4 2024"}
        ],
        "mcp_servers": [
            {
                "name": "sales-data",
                "transport": "stdio",
                "command": "mcp-sales-server"
            }
        ],
        "auto_discover_tools": True,
        "generation_config": {
            "tool_choice": "auto",  # Let agent decide when to use tools
            "max_tool_calls": 5
        }
    }
})

# Check if tools were called
if results["agent"]["success"]:
    response = results["agent"]["response"]
    if "tool_calls" in response:
        print(f"Agent made {len(response['tool_calls'])} tool calls:")
        for call in response["tool_calls"]:
            print(f"- {call['function']['name']}")
            print(f"  Args: {call['function']['arguments']}")
```

### Tool Calling with Error Handling
```python
class MCPToolHandler(LLMAgentNode):
    """Enhanced LLM agent with robust MCP tool handling."""

    def run(self, context, **kwargs):
        try:
            # Execute with MCP integration
            result = super().run(context, **kwargs)

            # Post-process tool call results
            if result.get("success") and "tool_calls" in result.get("response", {}):
                result["tool_call_summary"] = self.summarize_tool_calls(
                    result["response"]["tool_calls"]
                )

            return result

        except MCPConnectionError as e:
            return {
                "success": False,
                "error": f"MCP connection failed: {e}",
                "fallback_response": self.generate_fallback_response(kwargs)
            }
        except MCPToolError as e:
            return {
                "success": False,
                "error": f"MCP tool execution failed: {e}",
                "partial_results": e.partial_results if hasattr(e, 'partial_results') else None
            }
```

## IterativeLLMAgentNode with MCP

### Multi-Iteration MCP Integration
```python
from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode

# Iterative agent with progressive MCP tool discovery
workflow.add_node("iterative_agent", IterativeLLMAgentNode())

results, _ = runtime.execute(workflow, parameters={
    "iterative_agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {
                "role": "user",
                "content": "Analyze market trends iteratively using all available data sources"
            }
        ],
        "system_prompt": """You are an iterative market analyst.
        Each iteration, discover and use MCP tools to gather more data.

        Process:
        1. DISCOVERY: Find available MCP tools and resources
        2. PLANNING: Decide what analysis to do this iteration
        3. EXECUTION: Call tools with specific parameters
        4. REFLECTION: Analyze findings and identify gaps
        5. CONVERGENCE: Decide if more iterations are needed
        """,
        "mcp_servers": [
            {
                "name": "market-data",
                "transport": "stdio",
                "command": "mcp-market-server"
            }
        ],
        "auto_discover_tools": True,
        "iterative_config": {
            "max_iterations": 6,
            "convergence_threshold": 0.85,
            "tool_discovery_per_iteration": True
        }
    }
})

# Access iterative results with MCP integration
if results["iterative_agent"]["success"]:
    iterations = results["iterative_agent"]["iterations"]
    for i, iteration in enumerate(iterations):
        print(f"Iteration {i+1}:")
        print(f"  Phase: {iteration['phase']}")
        print(f"  Tools used: {len(iteration.get('tools_used', []))}")
        print(f"  Resources accessed: {len(iteration.get('resources_accessed', []))}")
```

## MCP + RAG Integration

### Combined MCP and RAG
```python
# Use MCP alongside RAG capabilities
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "Find and summarize our compliance policies"}
        ],
        "mcp_servers": [
            {
                "name": "knowledge-base",
                "transport": "stdio",
                "command": "mcp-kb-server"
            }
        ],
        "rag_config": {
            "enabled": True,
            "top_k": 5,
            "similarity_threshold": 0.7,
            "embedding_model": "nomic-embed-text"
        },
        "auto_discover_tools": True,
        "integration_mode": "mcp_rag_combined"  # Use both MCP and RAG
    }
})

# Both MCP and RAG resources are used
if results["agent"]["success"]:
    context = results["agent"]["context"]
    print(f"MCP resources: {context['mcp_resources_used']}")
    print(f"RAG documents: {context['rag_documents_retrieved']}")
```

## Error Handling and Fallbacks

### Graceful MCP Failure Handling
```python
# Configure fallback behavior when MCP fails
results, _ = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [
            {"role": "user", "content": "Get latest sales data"}
        ],
        "mcp_servers": [
            {
                "name": "sales-server",
                "transport": "stdio",
                "command": "mcp-sales-server",
                "timeout": 30  # 30 second timeout
            }
        ],
        "mcp_config": {
            "connection_timeout": 10,
            "retry_attempts": 3,
            "fallback_on_failure": True,
            "fallback_message": "MCP servers unavailable. Providing response based on general knowledge."
        },
        "auto_discover_tools": True
    }
})

# Check for MCP errors
if not results["agent"]["success"]:
    error = results["agent"]["error"]
    if "MCP" in error:
        print(f"MCP Error: {error}")
        # Handle MCP-specific errors
```

### MCP Health Monitoring
```python
class MCPHealthMonitor(Node):
    """Monitor MCP server health and performance."""

    def run(self, context, **kwargs):
        mcp_servers = kwargs.get("mcp_servers", [])
        health_report = {}

        for server in mcp_servers:
            server_name = server["name"]
            health_report[server_name] = {
                "status": self.check_server_status(server),
                "response_time": self.measure_response_time(server),
                "available_tools": self.count_available_tools(server),
                "last_successful_call": self.get_last_success_time(server)
            }

        return {
            "health_report": health_report,
            "overall_health": self.calculate_overall_health(health_report),
            "recommendations": self.generate_health_recommendations(health_report)
        }

# Add health monitoring to workflow
workflow.add_node("mcp_monitor", MCPHealthMonitor())
```

## Best Practices

### 1. Server Configuration Management
```python
# Centralize MCP server configurations
MCP_SERVER_CONFIGS = {
    "development": [
        {
            "name": "local-data",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "local_data_server"]
        }
    ],
    "production": [
        {
            "name": "production-data",
            "transport": "http",
            "url": "https://mcp.company.com/data",
            "headers": {"Authorization": f"Bearer {os.getenv('MCP_TOKEN')}"}
        }
    ]
}

# Use environment-specific configuration
environment = os.getenv("ENVIRONMENT", "development")
mcp_servers = MCP_SERVER_CONFIGS[environment]
```

### 2. Tool Discovery Optimization
```python
# Optimize tool discovery for performance
tool_discovery_config = {
    "cache_discoveries": True,
    "cache_ttl": 3600,  # 1 hour
    "filter_by_relevance": True,
    "relevance_threshold": 0.6,
    "max_tools_per_server": 20,
    "parallel_discovery": True
}
```

### 3. Security Considerations
```python
# Secure MCP configuration
secure_mcp_config = {
    "validate_ssl": True,
    "timeout": 30,
    "max_retry_attempts": 3,
    "allowed_commands": ["safe-command-1", "safe-command-2"],
    "sandbox_execution": True,
    "log_all_calls": True
}
```

### 4. Performance Monitoring
```python
# Monitor MCP performance
def monitor_mcp_performance(results):
    """Monitor MCP call performance."""
    context = results["agent"]["context"]

    metrics = {
        "tools_called": len(context.get("tools_used", [])),
        "resources_accessed": len(context.get("mcp_resources_used", [])),
        "total_call_time": context.get("mcp_call_duration", 0),
        "average_call_time": context.get("avg_mcp_call_time", 0),
        "success_rate": context.get("mcp_success_rate", 1.0)
    }

    # Log performance metrics
    print(f"MCP Performance: {metrics}")

    # Alert on poor performance
    if metrics["success_rate"] < 0.8:
        print("⚠️ Low MCP success rate!")
    if metrics["average_call_time"] > 5000:  # 5 seconds
        print("⚠️ Slow MCP responses!")
```
