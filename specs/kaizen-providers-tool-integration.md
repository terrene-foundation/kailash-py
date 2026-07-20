# Kailash Kaizen -- Domain Specification — Tool Integration (MCP)

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers tool integration via MCP (Model Context Protocol) — the builtin MCP server, tool discovery, tool execution, tool types, and MCP suppression under structured output. Split from `kaizen-providers.md` (specs-authority.md Rule 8 — the original file exceeded the 300-line split threshold). Sibling sub-files covering the rest of the parent domain: `kaizen-providers.md` (index), `kaizen-providers-provider-system.md`, `kaizen-providers-execution-strategies.md`, `kaizen-providers-tool-integration.md`, `kaizen-providers-memory-system.md`, `kaizen-providers-error-handling.md`, `kaizen-providers-streaming.md`. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 10. Tool Integration (MCP)

Kaizen uses MCP (Model Context Protocol) as the sole tool integration mechanism. `ToolRegistry` and `ToolExecutor` are removed.

### 10.1 Builtin MCP Server

BaseAgent auto-connects to `kaizen.mcp.builtin_server` which provides 12 builtin tools:

- File operations (read_file, write_file, list_directory)
- HTTP operations (http_get, http_post)
- System operations (bash_command)
- Web operations (web_search)
- And more

### 10.2 Tool Discovery

```python
tools = await agent.discover_tools(
    category=ToolCategory.FILE,    # Optional filter
    safe_only=True,                # Only SAFE danger level
    keyword="file",                # Keyword search
)
```

### 10.3 Tool Execution

```python
result = await agent.execute_mcp_tool("read_file", {"path": "/tmp/data.txt"})
```

### 10.4 Tool Types

```python
class DangerLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ToolCategory(Enum):
    SYSTEM = "system"
    FILE = "file"
    API = "api"
    # ... etc.
```

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    danger_level: DangerLevel
    parameters: List[ToolParameter]
    returns: Dict
    executor: Optional[Callable]

@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = False

@dataclass
class ToolResult:
    # Tool execution result
```

### 10.5 MCP Suppression

When `config.has_structured_output` is True, MCP auto-discovery is suppressed because some providers (notably Gemini) reject requests combining function calling with JSON response mode. This is logged at DEBUG level.

