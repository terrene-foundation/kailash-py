# Kaizen Tool Calling (v0.2.0+)

Autonomous tool execution with approval workflows for AI agents.

## LLM-First Rule (ABSOLUTE)

Tools are dumb data endpoints. The LLM does ALL reasoning. Tools fetch/write data and call APIs. They MUST NOT contain decision logic, routing, or classification.

## Quick Start

```python
from kaizen.core.base_agent import BaseAgent

agent = MyAgent(config=config, signature=signature, tools="all")  # 12 builtin tools via MCP
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# Custom MCP servers
mcp_servers = [{"name": "kaizen_builtin", "command": "python",
    "args": ["-m", "kaizen.mcp.builtin_server"], "transport": "stdio"}]
agent = MyAgent(config=config, signature=signature, custom_mcp_servers=mcp_servers)
```

## Builtin Tools (12)

```python
# File (5): read_file, write_file, delete_file, list_directory, file_exists
content = await agent.execute_tool("read_file", {"path": "data.txt"})
await agent.execute_tool("write_file", {"path": "out.txt", "content": "Hello"})

# HTTP (4): http_get, http_post, http_put, http_delete
response = await agent.execute_tool("http_get", {"url": "https://api.example.com/data"})
response = await agent.execute_tool("http_post", {"url": "https://api.example.com/create", "data": {"name": "John"}})

# Bash (1): bash_command
result = await agent.execute_tool("bash_command", {"command": "ls -la", "timeout": 10})

# Web (2): fetch_url, extract_links
content = await agent.execute_tool("fetch_url", {"url": "https://example.com"})
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
    {"tool_name": "http_post", "params": {"url": "https://api.example.com", "data": "${previous.content}"}},
    {"tool_name": "write_file", "params": {"path": "output.txt", "content": "${previous.response}"}},
])
```

## Danger Levels

| Level      | Approval          | Examples                       |
| ---------- | ----------------- | ------------------------------ |
| `SAFE`     | No                | read_file, http_get, fetch_url |
| `LOW`      | No                | write_file (non-critical)      |
| `MEDIUM`   | Yes (auto in dev) | http_post, http_put            |
| `HIGH`     | Yes               | delete_file, bash_command      |
| `CRITICAL` | Yes (manual only) | System commands                |

## Custom Tools

```python
from kaizen.tools import Tool, ToolParameter

def my_tool(param1: str, param2: int) -> dict:
    return {"result": f"Processed {param1} with {param2}"}

custom_tool = Tool(
    name="my_tool", description="Processes data", function=my_tool,
    parameters=[
        ToolParameter(name="param1", type="string", description="First param", required=True),
        ToolParameter(name="param2", type="integer", description="Second param", required=True),
    ],
    category="custom", danger_level="LOW",
)
registry.register_tool(custom_tool)
```

## MCP Server Integration

```python
mcp_servers = [
    {"name": "filesystem", "command": "mcp-server-filesystem", "args": ["--root", "/data"]},
    {"name": "git", "command": "mcp-server-git", "args": ["--repo", "/repo"]},
]
agent = MyAgent(config=config, signature=signature, tools="all", mcp_servers=mcp_servers)
result = await agent.execute_tool("git_status", {})
```

## Autonomous Agent with Tools

```python
from kaizen_agents.agents import ReActAgent

agent = ReActAgent(config=config, tools="all")
result = agent.solve("Find all Python files and count lines of code")
# Agent autonomously calls list_directory, read_file, processes results
```

## Complete Example

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class DataProcessingSignature(Signature):
    source_file: str = InputField(description="Source file path")
    result: str = OutputField(description="Processing result")

@dataclass
class DataConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")

class DataProcessingAgent(BaseAgent):
    def __init__(self, config: DataConfig):
        super().__init__(config=config, signature=DataProcessingSignature(), tools="all")

    async def process_data(self, source_file: str) -> dict:
        content = await self.execute_tool("read_file", {"path": source_file})
        result = self.run(source_file=source_file, content=content["content"])
        api_response = await self.execute_tool("http_post",
            {"url": "https://api.example.com/process", "data": result})
        await self.execute_tool("write_file",
            {"path": "result.txt", "content": api_response["response"]})
        return result
```

## Integration with Multi-Agent

```python
# NOTE: kaizen.agents.coordination is DEPRECATED (removal in v0.5.0)
# Use kaizen.orchestration.patterns instead
from kaizen_agents.patterns.patterns import SupervisorWorkerPattern

supervisor = SupervisorAgent(config, tools="all")
file_worker = FileAgent(config, tools="all")
pattern = SupervisorWorkerPattern(supervisor, [file_worker, api_worker], ...)
```

## Control Protocol Integration

```python
class SafeAgent(BaseAgent):
    async def process(self):
        dangerous = [t for t in await self.discover_tools()
                    if t["danger_level"] in ["HIGH", "CRITICAL"]]
        if dangerous:
            approved = await self.ask_user_question(
                question=f"Allow {len(dangerous)} dangerous tools?",
                options=["Yes", "No"])
            if approved == "No":
                return {"status": "cancelled"}
        result = await self.execute_tool("delete_file", {...})
```

## Testing

```python
import pytest
from kaizen.tools import Tool

@pytest.mark.asyncio
async def test_tool_execution():
    def mock_tool(param: str) -> dict:
        return {"result": f"Processed {param}"}

    tool = Tool(name="mock_tool", function=mock_tool,
        parameters=[ToolParameter(name="param", type="string", required=True)],
        danger_level="SAFE")
    registry.register_tool(tool)

    agent = MyAgent(config, tools="all")
    result = await agent.execute_tool("mock_tool", {"param": "test"})
    assert result["result"] == "Processed test"
```

## Troubleshooting

| Issue                                     | Fix                                                            |
| ----------------------------------------- | -------------------------------------------------------------- |
| `ToolNotFoundError: Tool 'xyz' not found` | Ensure tool is registered; builtin tools require `tools="all"` |
| Tool execution hangs                      | Add timeout: `{"command": "...", "timeout": 10}`               |
| Approval prompt not showing               | Enable control protocol in agent config                        |

## Performance

| Operation             | Latency       |
| --------------------- | ------------- |
| Tool discovery        | <1ms (cached) |
| Single tool execution | 10-100ms      |
| Tool chain (3 tools)  | 30-300ms      |
| MCP tool call         | 50-200ms      |
