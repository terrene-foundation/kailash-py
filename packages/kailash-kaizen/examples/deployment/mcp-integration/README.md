# MCP Integration Deployment

Production deployment for Model Context Protocol (MCP) integration with Kaizen agents.

## Architecture

This deployment demonstrates:
- MCP server providing tools and resources
- MCP client agents consuming services
- Service discovery and communication
- Tool orchestration
- Extensible integration patterns

## Services

### MCP Server
- Provides tools, resources, and prompts
- HTTP API on port 8080
- Health checks enabled
- 0.5-1 CPU cores, 256-512MB memory

### MCP Client
- Connects to MCP server
- Uses provided tools
- Executes workflows
- 1-2 CPU cores, 512MB-1GB memory

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Add your API keys
```

### 2. Start Services

```bash
docker-compose up -d
```

### 3. Verify MCP Server

```bash
curl http://localhost:8080/health
```

### 4. View Logs

```bash
# Server logs
docker-compose logs -f mcp-server

# Client logs
docker-compose logs -f mcp-client
```

### 5. Stop Services

```bash
docker-compose down
```

## Configuration

### Environment Variables

**MCP Server:**
- `MCP_ROLE=server`: Server mode
- `MCP_SERVER_NAME`: Server identifier
- `MCP_SERVER_VERSION`: Version string

**MCP Client:**
- `MCP_ROLE=client`: Client mode
- `MCP_SERVER_URL`: Server endpoint (auto-configured)

## MCP Protocol

### Available Tools

The MCP server provides:
- File operations (read, write, list)
- Data processing tools
- API integrations
- Custom business logic

### Tool Discovery

Client agents automatically discover available tools:

```python
# Tools are discovered at runtime
tools = mcp_client.list_tools()
```

### Tool Execution

```python
# Execute tool via MCP
result = mcp_client.execute_tool(
    name="process_data",
    parameters={"data": "..."}
)
```

## Monitoring

### Server Health

```bash
curl http://localhost:8080/health
```

### Tool Usage

View tool execution logs:
```bash
docker-compose logs -f mcp-server | grep "tool_execution"
```

### Performance

```bash
docker stats kaizen-mcp-server kaizen-mcp-client
```

## Production Considerations

### High Availability

1. Deploy multiple MCP servers behind load balancer
2. Implement server discovery service
3. Add health monitoring and auto-recovery
4. Use service mesh for resilience

### Security

1. Enable authentication for MCP server
2. Use HTTPS/TLS for MCP communication
3. Implement authorization for tools
4. Rate limiting per client
5. Audit logging for tool usage

### Scaling

**Horizontal Scaling:**
```bash
# Multiple clients
docker-compose up -d --scale mcp-client=5

# Multiple servers with load balancer
docker-compose up -d --scale mcp-server=3
```

**Vertical Scaling:**
Adjust resources based on tool complexity:
```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 2G
```

## Advanced Configuration

### Custom Tools

Add custom tools to MCP server:

```python
from mcp import Tool

@Tool(name="custom_tool", description="...")
def custom_tool(param: str) -> dict:
    # Tool implementation
    return {"result": "..."}
```

### Tool Composition

Chain multiple tools:

```python
# Execute workflow with multiple tools
result = agent.execute_workflow([
    {"tool": "fetch_data", "params": {...}},
    {"tool": "process_data", "params": {...}},
    {"tool": "save_results", "params": {...}}
])
```

## Troubleshooting

### Client Can't Connect to Server

Check network:
```bash
docker network inspect kaizen-network
```

Check server health:
```bash
docker-compose exec mcp-server curl http://localhost:8080/health
```

### Tool Execution Fails

Check server logs:
```bash
docker-compose logs mcp-server
```

Verify tool registration:
```bash
curl http://localhost:8080/tools
```

### Performance Issues

Monitor tool execution time:
```bash
docker-compose logs mcp-server | grep "execution_time"
```

Increase timeouts if needed:
```yaml
environment:
  - TOOL_TIMEOUT=60
```

## Next Steps

- Add authentication with JWT
- Implement rate limiting
- Add Prometheus metrics
- Deploy with Kubernetes
- Add API gateway
- Implement tool caching
- Add distributed tracing
