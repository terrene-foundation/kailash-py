# Kaizen Tool Calling (v0.2.0+)

Autonomous tool execution with approval workflows. 12 builtin tools, custom tools, MCP integration.

## LLM-First Rule (ABSOLUTE)

Tools are dumb data endpoints. The LLM does ALL reasoning. Tools fetch/write data and call APIs. They MUST NOT contain decision logic, routing, or classification. See `rules/agent-reasoning.md`.

## Quick Start

```python
from kaizen.core.base_agent import BaseAgent

agent = MyAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
)
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# OR configure custom MCP servers
mcp_servers = [{
    "name": "kaizen_builtin",
    "command": "python",
    "args": ["-m", "kaizen.mcp.builtin_server"],
    "transport": "stdio"
}]
agent = MyAgent(config=config, signature=signature, custom_mcp_servers=mcp_servers)
```

## Builtin Tools (12)

### File Operations (5)

```python
content = await agent.execute_tool("read_file", {"path": "data.txt"})
await agent.execute_tool("write_file", {"path": "out.txt", "content": "Hello"})
await agent.execute_tool("delete_file", {"path": "temp.txt"})
files = await agent.execute_tool("list_directory", {"path": "."})
exists = await agent.execute_tool("file_exists", {"path": "data.txt"})
```

### HTTP Operations (4)

```python
response = await agent.execute_tool("http_get", {"url": "https://api.example.com/data"})
response = await agent.execute_tool("http_post", {
    "url": "https://api.example.com/create",
    "data": {"name": "John"}
})
# http_put, http_delete also available
```

### Bash (1) and Web (2)

```python
result = await agent.execute_tool("bash_command", {"command": "ls -la", "timeout": 10})
content = await agent.execute_tool("fetch_url", {"url": "https://example.com"})
links = await agent.execute_tool("extract_links", {"url": "https://example.com"})
```

## Tool Discovery

```python
tools = await agent.discover_tools()
file_tools = await agent.discover_tools(category="file")
# Returns: {"name", "description", "category", "danger_level", "parameters"}
```

## Tool Chaining

```python
results = await agent.execute_tool_chain([
    {"tool_name": "read_file", "params": {"path": "input.txt"}},
    {"tool_name": "http_post", "params": {
        "url": "https://api.example.com/process",
        "data": "${previous.content}"  # Reference previous result
    }},
    {"tool_name": "write_file", "params": {
        "path": "output.txt",
        "content": "${previous.response}"
    }}
])
```

## Danger Levels

| Level      | Approval Required         | Examples                       |
| ---------- | ------------------------- | ------------------------------ |
| `SAFE`     | No                        | read_file, http_get, fetch_url |
| `LOW`      | No                        | write_file (non-critical)      |
| `MEDIUM`   | Yes (auto-approve in dev) | http_post, http_put            |
| `HIGH`     | Yes                       | delete_file, bash_command      |
| `CRITICAL` | Yes (manual only)         | System commands                |

HIGH/CRITICAL tools trigger interactive approval: `"Approve tool execution: delete_file?" [Yes/No]`

## Custom Tools

```python
from kaizen.tools import Tool, ToolParameter

def my_custom_tool(param1: str, param2: int) -> dict:
    return {"result": f"Processed {param1} with {param2}"}

custom_tool = Tool(
    name="my_custom_tool",
    description="Processes data with custom logic",
    function=my_custom_tool,
    parameters=[
        ToolParameter(name="param1", type="string", description="First parameter", required=True),
        ToolParameter(name="param2", type="integer", description="Second parameter", required=True)
    ],
    category="custom",
    danger_level="LOW"
)
registry.register_tool(custom_tool)
result = await agent.execute_tool("my_custom_tool", {"param1": "data", "param2": 42})
```

## MCP Server Integration

```python
mcp_servers = [
    {"name": "filesystem", "command": "mcp-server-filesystem", "args": ["--root", "/data"]},
    {"name": "git", "command": "mcp-server-git", "args": ["--repo", "/repo"]}
]

agent = MyAgent(config=config, signature=signature, tools="all", mcp_servers=mcp_servers)
result = await agent.execute_tool("git_status", {})  # MCP tools auto-available
```

## Autonomous Agents with Tools

```python
from kaizen_agents.agents import ReActAgent

agent = ReActAgent(config=config, tools="all")
result = agent.solve("Find all Python files and count lines of code")
# Agent autonomously: reasons -> calls list_directory -> calls read_file -> returns result
```

## Integration Patterns

### With Control Protocol

```python
class SafeAgent(BaseAgent):
    async def process(self):
        dangerous = [t for t in await self.discover_tools()
                    if t["danger_level"] in ["HIGH", "CRITICAL"]]
        if dangerous:
            approved = await self.ask_user_question(
                question=f"Allow {len(dangerous)} dangerous tools?",
                options=["Yes", "No"]
            )
            if approved == "No":
                return {"status": "cancelled"}
        result = await self.execute_tool("delete_file", {"path": "temp.txt"})
```

### With Multi-Agent

```python
# NOTE: kaizen.agents.coordination is DEPRECATED (removal in v0.5.0)
# Use kaizen.orchestration.patterns instead
from kaizen_agents.patterns.patterns import SupervisorWorkerPattern

supervisor = SupervisorAgent(config, tools="all")
file_worker = FileAgent(config, tools="all")
api_worker = APIAgent(config, tools="all")
pattern = SupervisorWorkerPattern(supervisor, [file_worker, api_worker])
```

## Testing

```python
import pytest

@pytest.mark.asyncio
async def test_tool_execution():
    def mock_tool(param: str) -> dict:
        return {"result": f"Processed {param}"}

    tool = Tool(name="mock_tool", function=mock_tool, parameters=[...], danger_level="SAFE")
    registry.register_tool(tool)
    agent = MyAgent(config, tools="all")

    result = await agent.execute_tool("mock_tool", {"param": "test"})
    assert result["result"] == "Processed test"
```

## Best Practices

- **Discover before calling** -- use `discover_tools(category=...)` instead of assuming tool names
- **Handle errors** -- wrap `execute_tool` in try/except for expected failures
- **Set danger levels accurately** -- SAFE for reads, CRITICAL for destructive ops
- **Prefer chaining** -- `execute_tool_chain` over sequential `execute_tool` calls
- **Set timeouts** -- especially for `bash_command` to prevent hangs

## Performance

| Operation             | Latency  | Notes                |
| --------------------- | -------- | -------------------- |
| Tool discovery        | <1ms     | Cached registry      |
| Single tool execution | 10-100ms | Depends on tool      |
| Tool chain (3 tools)  | 30-300ms | Sequential execution |
| MCP tool call         | 50-200ms | IPC overhead         |

## Related

- [kaizen-control-protocol.md](kaizen-control-protocol.md) -- Approval workflows
- [kaizen-baseagent-quick.md](kaizen-baseagent-quick.md) -- BaseAgent fundamentals
- [kaizen-react-pattern.md](kaizen-react-pattern.md) -- Autonomous reasoning + action
