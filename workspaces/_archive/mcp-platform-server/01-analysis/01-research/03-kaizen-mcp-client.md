# Kaizen MCP Client Analysis

**Source**: `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (510 lines)

## Purpose

The `McpClient` is a production-quality stdio JSON-RPC 2.0 client that manages MCP server subprocesses. It is the test harness for the platform server's integration tests.

## Core Classes

### McpServerConfig (frozen dataclass)

```python
@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
```

- Parsed from TOML `[mcp.servers]` section
- Immutable (frozen)
- `env` dict overlays `os.environ` for subprocess

### McpToolDef (frozen dataclass)

```python
@dataclass(frozen=True)
class McpToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str
```

- Represents a discovered MCP tool
- `server_name` enables prefixed registration

### McpClient

The main client class managing one subprocess per MCP server.

## Protocol Flow

### 1. Start (subprocess + initialize handshake)

```
Client                          Server (subprocess)
  |--- create_subprocess_exec ----->|
  |--- "initialize" (JSON-RPC) ---->|
  |<--- {"result": {"serverInfo": ...}} ---|
  |--- "notifications/initialized" -->|
```

- 15-second timeout for initialize handshake
- Sends `protocolVersion: "2024-11-05"`
- Sends `clientInfo: {"name": "kz", "version": "0.1.0"}`
- On timeout or error: calls `stop()` and raises `RuntimeError`

### 2. Tool Discovery

```
Client                          Server
  |--- "tools/list" {} ------------>|
  |<--- {"tools": [...]} ----------|
```

- 30-second timeout per request
- Returns `list[McpToolDef]`
- Each tool has `name`, `description`, `inputSchema`

### 3. Tool Execution

```
Client                          Server
  |--- "tools/call" {"name": ..., "arguments": ...} -->|
  |<--- {"content": [{"type": "text", "text": "..."}]} |
```

- Returns concatenated text content blocks
- Checks `isError` flag for error responses
- 30-second timeout

### 4. Shutdown

```
Client                          Server
  |--- SIGTERM ------------------->|
  |--- wait(timeout=5) ----------->|
  |--- SIGKILL (if still alive) -->|
```

- Cancels reader task
- SIGTERM with 5-second grace period
- Escalates to SIGKILL
- Cancels all pending futures
- Handles `ProcessLookupError` (process already dead)

## Background Reader

```python
async def _read_stdout(self) -> None:
    while True:
        raw = await self._process.stdout.readline()
        if not raw:
            break  # EOF
        msg = json.loads(line)
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending[msg_id]
            future.set_result(msg)
        elif msg.get("method"):
            logger.debug("notification: %s", msg.get("method"))

    # EOF: fail all pending futures
    for future in self._pending.values():
        if not future.done():
            future.set_exception(RuntimeError("server exited unexpectedly"))
```

Key patterns:

- Line-delimited JSON-RPC (one message per line)
- Future-based request/response correlation via `id`
- Server notifications logged but not processed
- EOF triggers failure of all pending futures (prevents hangs)

## Integration Test Usage Pattern

```python
async def test_platform_server():
    config = McpServerConfig(
        name="kailash-platform",
        command="python",
        args=["-m", "kailash.mcp.server", "--project-root", str(project_dir)],
    )
    client = McpClient(config)
    await client.start()

    # Discover tools
    tools = await client.discover_tools()
    assert any(t.name == "dataflow.list_models" for t in tools)

    # Call a tool
    result = await client.call_tool("dataflow.list_models", {})
    parsed = json.loads(result)
    assert "models" in parsed

    await client.stop()
```

## Tool Registration into Kaizen

```python
async def register_mcp_tools(client: McpClient, registry: Any) -> list[McpToolDef]:
    tools = await client.discover_tools()
    for tool_def in tools:
        prefixed_name = f"mcp_{client.server_name}_{tool_def.name}"

        async def _executor(_client=client, _tool_name=tool_def.name, **kwargs):
            return await _client.call_tool(_tool_name, kwargs)

        registry.register(
            name=prefixed_name,
            description=f"[MCP:{client.server_name}] {tool_def.description}",
            parameters=tool_def.input_schema,
            executor=_executor,
        )
    return tools
```

- Prefix: `mcp_<server>_<tool>` (e.g., `mcp_kailash_dataflow.list_models`)
- Closure captures client and tool name correctly (default arg pattern)
- Description includes server name for disambiguation

## Config Loading

```python
def load_mcp_server_configs(raw_config: dict) -> list[McpServerConfig]:
    """Parse from TOML:
    [mcp.servers.filesystem]
    command = "npx"
    args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env = { SOME_VAR = "value" }
    """
```

## Test Considerations

1. **Subprocess startup time**: server must initialize within 15 seconds
2. **stdio transport**: platform server must support `python -m kailash.mcp.server`
3. **Line-delimited JSON**: each response on a single line (no pretty-printing)
4. **Error handling**: client expects JSON-RPC error format `{"error": {"code": ..., "message": ...}}`
5. **Graceful shutdown**: server should handle SIGTERM cleanly
