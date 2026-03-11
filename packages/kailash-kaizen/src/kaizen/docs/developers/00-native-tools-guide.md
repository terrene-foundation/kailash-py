# Native Tool System Developer Guide

## Overview

The Native Tool System provides a framework for building tools that execute within LocalKaizenAdapter's autonomous Think-Act-Observe-Decide (TAOD) loop. Unlike MCP tools (used by BaseAgent for LLM tool calling), native tools are designed for programmatic execution with any LLM provider.

## Architecture

```
kaizen/tools/native/
├── __init__.py        # Public exports
├── base.py            # BaseTool, NativeToolResult
├── registry.py        # KaizenToolRegistry
├── file_tools.py      # File operation tools (7 tools)
├── bash_tools.py      # BashTool for command execution
└── search_tools.py    # WebSearchTool, WebFetchTool
```

## Core Components

### NativeToolResult

Standardized result type for all native tool executions:

```python
from kaizen.tools.native import NativeToolResult

# Success result
result = NativeToolResult.from_success(
    output="File contents here",
    bytes_read=1024,
    lines=50
)

# Error result
result = NativeToolResult.from_error(
    "File not found: /path/to/file.txt",
    attempted_path="/path/to/file.txt"
)

# From exception
try:
    risky_operation()
except Exception as e:
    result = NativeToolResult.from_exception(e)
```

### BaseTool

Abstract base class for all native tools:

```python
from kaizen.tools.native import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

class MyCustomTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    danger_level = DangerLevel.LOW
    category = ToolCategory.CUSTOM

    async def execute(self, param1: str, param2: int = 10) -> NativeToolResult:
        try:
            # Tool logic here
            result = do_something(param1, param2)
            return NativeToolResult.from_success(result)
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "First parameter"
                },
                "param2": {
                    "type": "integer",
                    "description": "Second parameter",
                    "default": 10
                }
            },
            "required": ["param1"]
        }
```

### KaizenToolRegistry

Central registry for managing and executing tools:

```python
from kaizen.tools.native import KaizenToolRegistry

# Create registry
registry = KaizenToolRegistry()

# Register default tools by category
registry.register_defaults(categories=["file", "bash", "search"])

# Register custom tool
registry.register(MyCustomTool())

# List available tools
tools = registry.list_tools()  # ['bash_command', 'edit_file', 'glob', ...]

# Get tool schemas for LLM
schemas = registry.get_tool_schemas()

# Execute tool
result = await registry.execute("read_file", {"path": "/tmp/file.txt"})
```

## Available Tools

### File Tools

| Tool | Description | Danger Level |
|------|-------------|--------------|
| `read_file` | Read file contents with pagination | SAFE |
| `write_file` | Write content to files | MEDIUM |
| `edit_file` | String replacement editing | MEDIUM |
| `glob` | Pattern matching file discovery | SAFE |
| `grep` | Regex content search | SAFE |
| `list_directory` | List directory contents | SAFE |
| `file_exists` | Check file/directory existence | SAFE |

### Bash Tool

| Tool | Description | Danger Level |
|------|-------------|--------------|
| `bash_command` | Sandboxed command execution | HIGH |

Security features:
- Blocks dangerous patterns (rm -rf /, fork bombs, etc.)
- Configurable timeout (max 600 seconds)
- Output size limits (30KB max)
- Optional command whitelisting

### Search Tools

| Tool | Description | Danger Level |
|------|-------------|--------------|
| `web_search` | DuckDuckGo web search | SAFE |
| `web_fetch` | Fetch and extract URL content | SAFE |

Security features:
- SSRF protection (blocks localhost, private IPs)
- Content length limits
- HTML text extraction with script removal

## Danger Levels

Tools are classified by danger level for approval workflows:

| Level | Description | Requires Approval |
|-------|-------------|-------------------|
| SAFE | Read-only, no side effects | No |
| LOW | Minor side effects, easily reversible | No |
| MEDIUM | Modifies files or state | By default |
| HIGH | System commands, network operations | Yes |
| CRITICAL | Irreversible or dangerous operations | Always |

```python
# Check if tool requires approval
tool = registry.get_tool("bash_command")
if tool.requires_approval():
    # Request user confirmation
    pass
```

## Creating Custom Tools

### Step 1: Define the Tool

```python
from kaizen.tools.native import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory

class DatabaseQueryTool(BaseTool):
    name = "db_query"
    description = "Execute read-only database queries"
    danger_level = DangerLevel.LOW
    category = ToolCategory.DATA

    def __init__(self, connection_string: str):
        super().__init__()
        self.connection_string = connection_string

    async def execute(self, query: str) -> NativeToolResult:
        # Validate query is read-only
        if not query.strip().upper().startswith("SELECT"):
            return NativeToolResult.from_error(
                "Only SELECT queries are allowed"
            )

        try:
            # Execute query (using your DB library)
            results = await self._execute_query(query)
            return NativeToolResult.from_success(
                results,
                rows_returned=len(results)
            )
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to execute"
                }
            },
            "required": ["query"]
        }
```

### Step 2: Register the Tool

```python
registry = KaizenToolRegistry()
registry.register_defaults()  # Register standard tools

# Register custom tool
db_tool = DatabaseQueryTool("postgresql://...")
registry.register(db_tool)
```

### Step 3: Use in Autonomous Loop

```python
# Tool schemas for LLM prompt
schemas = registry.get_tool_schemas()
prompt_docs = registry.format_for_prompt()

# Execute tool based on LLM response
tool_name = "db_query"
tool_params = {"query": "SELECT * FROM users LIMIT 10"}
result = await registry.execute(tool_name, tool_params)

if result.success:
    # Continue with result.output
    pass
else:
    # Handle error: result.error
    pass
```

## Best Practices

### 1. Always Return NativeToolResult

Never raise exceptions for expected failures. Use `NativeToolResult.from_error()`:

```python
# Good
if not os.path.exists(path):
    return NativeToolResult.from_error(f"File not found: {path}")

# Bad - don't raise for expected conditions
if not os.path.exists(path):
    raise FileNotFoundError(f"File not found: {path}")
```

### 2. Validate Inputs Early

Check parameters before doing work:

```python
async def execute(self, path: str, content: str) -> NativeToolResult:
    # Validate first
    if not os.path.isabs(path):
        return NativeToolResult.from_error("Path must be absolute")

    if not content:
        return NativeToolResult.from_error("Content cannot be empty")

    # Then do work
    ...
```

### 3. Include Useful Metadata

Add context to successful results:

```python
return NativeToolResult.from_success(
    file_content,
    path=path,
    lines=len(file_content.splitlines()),
    bytes_read=len(file_content),
    encoding="utf-8"
)
```

### 4. Set Appropriate Danger Levels

Be conservative - it's better to require approval than to cause unintended damage:

- File reads: SAFE
- File writes: MEDIUM or HIGH
- Command execution: HIGH
- Network operations: Varies by operation

### 5. Document Schema Clearly

LLMs use the schema to understand how to call tools:

```python
def get_schema(self) -> dict:
    return {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to read. Must start with /"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum lines to read (1-10000)",
                "default": 1000
            }
        },
        "required": ["path"]
    }
```

## Testing

Tests are located in `tests/unit/tools/native/`:

```bash
# Run all native tool tests
pytest tests/unit/tools/native/ -v

# Run specific test file
pytest tests/unit/tools/native/test_file_tools.py -v
```

## Integration with LocalKaizenAdapter

The native tool system is designed for LocalKaizenAdapter's autonomous loop:

```python
from kaizen.tools.native import KaizenToolRegistry

class LocalKaizenAdapter:
    def __init__(self):
        self.registry = KaizenToolRegistry()
        self.registry.register_defaults()

    async def execute_tool(self, tool_name: str, params: dict):
        tool = self.registry.get_tool(tool_name)

        # Check approval if needed
        if tool and tool.requires_approval():
            if not await self.request_approval(tool_name, params):
                return NativeToolResult.from_error("User denied tool execution")

        return await self.registry.execute(tool_name, params)
```
