# Kaizen Builtin MCP Server

## What is the Kaizen Builtin MCP Server?

The Kaizen Builtin MCP Server is a production-ready MCP server that provides 12 essential tools for file operations, HTTP requests, shell commands, and web scraping. All Kaizen agents automatically connect to this server by default, providing instant access to these tools without any configuration.

## Available Tools (12 Total)

### File Operations (5 tools)

**`read_file`** - Read file contents
```python
result = await agent.execute_mcp_tool("read_file", {
    "path": "/path/to/file.txt",
    "encoding": "utf-8"  # optional, defaults to utf-8
})
# Returns: {"content": "...", "size": 1024, "exists": true}
```

**`write_file`** - Write content to a file
```python
result = await agent.execute_mcp_tool("write_file", {
    "path": "/path/to/output.txt",
    "content": "Hello, World!",
    "encoding": "utf-8",  # optional
    "create_dirs": True   # optional, create parent directories
})
# Returns: {"written": true, "size": 13, "path": "/absolute/path/to/output.txt"}
```

**`delete_file`** - Delete a file
```python
result = await agent.execute_mcp_tool("delete_file", {
    "path": "/path/to/file.txt"
})
# Returns: {"deleted": true, "existed": true, "path": "/path/to/file.txt"}
```

**`list_directory`** - List directory contents
```python
result = await agent.execute_mcp_tool("list_directory", {
    "path": "/path/to/directory",
    "recursive": False,      # optional
    "include_hidden": False  # optional
})
# Returns: {"files": ["file1.txt", ...], "directories": ["subdir"], "count": 5}
```

**`file_exists`** - Check if a file exists
```python
result = await agent.execute_mcp_tool("file_exists", {
    "path": "/path/to/file.txt"
})
# Returns: {"exists": true, "is_file": true, "is_directory": false}
```

### HTTP Requests (4 tools)

**`http_get`** - Make HTTP GET request
```python
result = await agent.execute_mcp_tool("http_get", {
    "url": "https://api.example.com/data",
    "headers": {"Authorization": "Bearer token"},  # optional
    "timeout": 30  # optional, seconds
})
# Returns: {"status_code": 200, "body": "...", "headers": {...}, "success": true}
```

**`http_post`** - Make HTTP POST request
```python
result = await agent.execute_mcp_tool("http_post", {
    "url": "https://api.example.com/data",
    "data": {"key": "value"},  # dict or string
    "headers": {"Content-Type": "application/json"},  # optional
    "timeout": 30  # optional
})
# Returns: {"status_code": 201, "body": "...", "success": true}
```

**`http_put`** - Make HTTP PUT request
```python
result = await agent.execute_mcp_tool("http_put", {
    "url": "https://api.example.com/resource/123",
    "data": {"updated": "value"},
    "timeout": 30
})
```

**`http_delete`** - Make HTTP DELETE request
```python
result = await agent.execute_mcp_tool("http_delete", {
    "url": "https://api.example.com/resource/123",
    "headers": {"Authorization": "Bearer token"},
    "timeout": 30
})
```

### Shell Commands (1 tool)

**`bash_command`** - Execute shell command (⚠️ HIGH DANGER)
```python
result = await agent.execute_mcp_tool("bash_command", {
    "command": "ls -la /tmp",
    "timeout": 30,              # optional, seconds
    "working_dir": "/tmp"       # optional
})
# Returns: {"stdout": "...", "stderr": "...", "exit_code": 0, "success": true}
```

⚠️ **Security Warning**: This tool uses `shell=True` and is vulnerable to command injection. Requires approval workflow for execution.

### Web Scraping (2 tools)

**`fetch_url`** - Fetch content from a URL
```python
result = await agent.execute_mcp_tool("fetch_url", {
    "url": "https://example.com",
    "timeout": 30,                       # optional
    "user_agent": "MyBot/1.0"           # optional
})
# Returns: {"content": "<html>...</html>", "status_code": 200, "content_type": "text/html", "size": 4096}
```

**`extract_links`** - Extract links from HTML
```python
result = await agent.execute_mcp_tool("extract_links", {
    "html": "<html><a href='/page'>Link</a></html>",
    "base_url": "https://example.com"  # optional, for relative URLs
})
# Returns: {"links": ["https://example.com/page"], "count": 1, "unique_links": [...]}
```

## Automatic Connection

All Kaizen agents automatically connect to the builtin MCP server when `mcp_servers` parameter is not specified:

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

class MySignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer")

config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

# Auto-connects to kaizen_builtin server
agent = BaseAgent(config=config, signature=MySignature())

# All 12 tools are now available
tools = await agent.discover_mcp_tools(server_name="kaizen_builtin")
```

## Disabling Auto-Connection

To disable MCP integration entirely, pass an empty list:

```python
# Disable MCP integration
agent = BaseAgent(config=config, signature=MySignature(), mcp_servers=[])
```

## Using Custom MCP Servers

To use custom MCP servers instead of (or in addition to) the builtin server:

```python
custom_servers = [
    {
        "name": "my_custom_server",
        "command": "python",
        "args": ["-m", "my_mcp_server"],
        "transport": "stdio"
    }
]

agent = BaseAgent(config=config, signature=MySignature(), mcp_servers=custom_servers)
```

## Tool Discovery

Discover all available tools from the builtin server:

```python
# Discover all tools
tools = await agent.discover_mcp_tools(server_name="kaizen_builtin")

print(f"Available tools: {len(tools)}")
for tool in tools:
    print(f"- {tool['name']}: {tool['description']}")
```

## Tool Execution

Execute tools directly:

```python
# Single tool execution
result = await agent.execute_mcp_tool(
    tool_name="read_file",
    params={"path": "/path/to/file.txt"}
)

# Check result
if result.get("exists"):
    content = result["content"]
    print(f"File size: {result['size']} bytes")
```

## Chaining Multiple Tools

Execute multiple tools in sequence:

```python
results = await agent.execute_tool_chain([
    {
        "tool_name": "fetch_url",
        "params": {"url": "https://example.com"}
    },
    {
        "tool_name": "extract_links",
        "params": {"html": "{{previous.content}}", "base_url": "https://example.com"}
    }
])

# Access results
html_content = results[0]["content"]
extracted_links = results[1]["links"]
```

## Security Features

All builtin tools include enterprise-grade security with danger-level based approval workflows.

### Danger Levels

Each builtin MCP tool is assigned a danger level that determines whether user approval is required:

- **SAFE** (6 tools): No approval needed - read-only, non-destructive operations
  - `read_file`, `file_exists`, `list_directory`
  - `fetch_url`, `extract_links`, `http_get`

- **MEDIUM** (3 tools): Approval required - write operations and mutations
  - `write_file`, `http_post`, `http_put`

- **HIGH** (3 tools): Approval always required - destructive operations
  - `delete_file`, `http_delete`
  - `bash_command` (shell=True, command injection risk)

### Approval Workflow

To enable approval for MEDIUM and HIGH danger tools, pass a `control_protocol` to BaseAgent:

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Create control protocol for approval workflow
transport = CLITransport()
protocol = ControlProtocol(transport=transport)
await protocol.start()

# Create agent with approval workflow enabled
config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
agent = BaseAgent(
    config=config,
    signature=MySignature(),
    control_protocol=protocol  # Enable approval workflow
)

# SAFE tools execute immediately (no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__read_file",
    {"path": "/data.txt"}
)

# MEDIUM/HIGH tools request approval from user
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/output.txt", "content": "data"}
)
# User sees prompt: "Agent wants to write to file: /output.txt. Approve?"
```

### Without Control Protocol

If `control_protocol` is not configured, MEDIUM and HIGH tools raise `PermissionError`:

```python
# No control_protocol = approval workflow disabled
agent = BaseAgent(config=config, signature=MySignature())

# SAFE tools work fine
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__read_file",
    {"path": "/data.txt"}
)

# MEDIUM/HIGH tools raise PermissionError
try:
    await agent.execute_mcp_tool(
        "mcp__kaizen_builtin__write_file",
        {"path": "/output.txt", "content": "data"}
    )
except PermissionError as e:
    print(f"Error: {e}")
    # Error: Tool 'write_file' (danger=medium) requires approval
    #        but control_protocol not configured
```

### Security Validations

#### File Tools
- Path traversal protection (blocks `..` patterns)
- Dangerous system path blocking (`/etc`, `/sys`, `/proc`, `/dev`, `/boot`, `/root`)
- Optional sandboxing via `allowed_base` parameter

#### HTTP Tools
- SSRF protection (blocks localhost, private IPs)
- Timeout validation (1-300 seconds)
- Response size limiting (10MB max)
- Allowed schemes only (`http`, `https`)

#### Bash Tool
- HIGH danger level (requires approval workflow)
- Uses `shell=True` (vulnerable to command injection)
- Timeout protection
- Working directory isolation

#### Web Tools
- HTMLParser-based link extraction (not regex)
- User agent customization
- Timeout protection

## Running the Server Standalone

The builtin server can be run standalone for testing:

```bash
python -m kaizen.mcp.builtin_server
```

This starts the server on stdio transport, making it available for MCP client connections.

## Server Configuration

The builtin server is configured as:

```python
{
    "name": "kaizen_builtin",
    "command": "python",
    "args": ["-m", "kaizen.mcp.builtin_server"],
    "transport": "stdio",
    "description": "Kaizen builtin tools (file, HTTP, bash, web)"
}
```

## Implementation Details

### Architecture
- **Server Class**: `KaizenMCPServer` extends `MCPServer` from Kailash SDK
- **Auto-Registration**: `auto_register_tools()` method scans modules for `@mcp_tool` decorated functions
- **Decorator**: `@mcp_tool` adds metadata for tool discovery
- **Protocol Compliance**: 100% MCP spec compliant

### Tool Registration
Tools are registered using the `@mcp_tool` decorator:

```python
from kaizen.mcp.builtin_server.decorators import mcp_tool

@mcp_tool(
    name="my_tool",
    description="Tool description",
    parameters={
        "param1": {"type": "string", "description": "Parameter 1"}
    }
)
async def my_tool(param1: str) -> dict:
    return {"result": f"Processed {param1}"}
```

### Server Initialization
The server auto-registers all tools on import:

```python
from kaizen.mcp.builtin_server.server import server

# Server already initialized with all 12 tools
print(f"Server: {server.name}")
print(f"Tools: {len(server._tool_registry)}")
```

## Integration with BaseAgent

BaseAgent provides high-level methods for MCP tool usage:

```python
# Discover tools
tools = await agent.discover_mcp_tools(
    server_name="kaizen_builtin",
    category="file"  # optional filter
)

# Execute tool
result = await agent.execute_mcp_tool(
    tool_name="read_file",
    params={"path": "/data.txt"}
)

# Execute tool chain
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "{{previous.content}}"}}
])
```

## Error Handling

All tools return structured error information:

```python
result = await agent.execute_mcp_tool("read_file", {"path": "/nonexistent.txt"})

if "error" in result:
    print(f"Error: {result['error']}")
    # Error: File not found
else:
    content = result["content"]
```

## Best Practices

1. **Always check for errors**: All tools return `error` key if operation failed
2. **Use appropriate timeouts**: Set timeouts based on expected operation duration
3. **Validate paths**: File tools include built-in validation, but verify paths in your logic
4. **Handle SSRF**: HTTP tools block private IPs, but validate URLs in application logic
5. **Approve dangerous operations**: `bash_command` requires approval workflow - implement proper controls
6. **Chain tools efficiently**: Use `execute_tool_chain()` for sequential operations
7. **Filter tool discovery**: Use `category` parameter to discover only needed tools

## Examples

### Read, Process, and Write File
```python
# Read
read_result = await agent.execute_mcp_tool("read_file", {"path": "input.txt"})
content = read_result["content"]

# Process
processed = content.upper()

# Write
write_result = await agent.execute_mcp_tool("write_file", {
    "path": "output.txt",
    "content": processed
})
```

### Fetch and Parse Web Page
```python
# Fetch
fetch_result = await agent.execute_mcp_tool("fetch_url", {
    "url": "https://example.com"
})

# Extract links
links_result = await agent.execute_mcp_tool("extract_links", {
    "html": fetch_result["content"],
    "base_url": "https://example.com"
})

print(f"Found {links_result['count']} links")
```

### API Request with Error Handling
```python
result = await agent.execute_mcp_tool("http_get", {
    "url": "https://api.example.com/data",
    "headers": {"Authorization": "Bearer token"},
    "timeout": 10
})

if result["success"]:
    data = result["body"]
    print(f"Status: {result['status_code']}")
else:
    print(f"Request failed: {result.get('error', 'Unknown error')}")
```

## Tool Module Locations

- **File tools**: `kaizen.mcp.builtin_server.tools.file`
- **API tools**: `kaizen.mcp.builtin_server.tools.api`
- **Bash tool**: `kaizen.mcp.builtin_server.tools.bash`
- **Web tools**: `kaizen.mcp.builtin_server.tools.web`

## Related Documentation

- [MCP Integration Guide](README.md) - Complete MCP integration documentation
- [MCP Architecture](architecture.md) - MCP protocol and architecture details
- [BaseAgent API Reference](../../reference/api-reference.md) - BaseAgent API documentation
- [Tool Integration Guide](../../features/baseagent-tool-integration.md) - Tool calling integration

## Further Reading

- [MCP Specification](https://spec.modelcontextprotocol.io/) - Official MCP protocol specification
- [Kailash MCP Server](https://github.com/terrene-foundation/kailash-sdk) - Production-ready MCP server implementation
- [BaseAgent Source](../../src/kaizen/core/base_agent.py) - BaseAgent implementation details
