# Tools API Reference

Complete API reference for tool calling, approval workflows, and permission management in Kaizen.

## Table of Contents

1. [Overview](#overview)
2. [Tool Execution API](#tool-execution-api)
3. [Danger Levels](#danger-levels)
4. [Approval Workflows](#approval-workflows)
5. [Permission Policies](#permission-policies)
6. [Builtin Tools](#builtin-tools)
7. [Custom Tool Integration](#custom-tool-integration)

---

## Overview

Kaizen provides a production-ready tool calling system with:

- **12 Builtin MCP Tools**: File, HTTP, Bash, and Web operations
- **Danger-Level Classification**: SAFE → MEDIUM → HIGH → CRITICAL
- **Approval Workflows**: Automatic approval for safe tools, user confirmation for risky operations
- **Permission Policies**: Fine-grained control with 8-layer decision logic
- **MCP Integration**: Built on Model Context Protocol for standardized tool interfaces

**Location**: `kaizen.core.base_agent`, `kaizen.mcp.builtin_server`, `kaizen.core.autonomy.permissions`

---

## Tool Execution API

### BaseAgent.execute_mcp_tool()

Execute MCP tools with server routing and approval workflows.

**Location**: `src/kaizen/core/base_agent.py:2328`

```python
async def execute_mcp_tool(
    self,
    tool_name: str,
    params: Dict[str, Any],
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """
    Execute MCP tool with server routing and approval workflow.

    Routes tool execution to the correct MCP server based on naming convention:
    mcp__<serverName>__<toolName>

    For builtin MCP tools (kaizen_builtin server), implements danger-level based
    approval workflow:
    - SAFE tools: Execute immediately (read_file, file_exists, etc.)
    - MEDIUM tools: Request approval (write_file, http_post, etc.)
    - HIGH tools: Always request approval (delete_file, bash_command, etc.)

    Args:
        tool_name: Tool name with naming convention (mcp__server__tool)
        params: Tool parameters
        timeout: Optional execution timeout

    Returns:
        Tool execution result with standardized dict format:
        {
            "success": bool,
            "output": str,
            "stdout": str,          # Bash commands only
            "stderr": str,          # Bash commands only
            "exit_code": int,       # Bash commands only
            "content": str,         # Raw content from CallToolResult
            "error": str,           # Error message if failed
            "isError": bool,        # MCP error flag
            "structured_content": dict  # Structured data from MCP
        }

    Raises:
        ValueError: If tool_name format invalid or server not found
        PermissionError: If approval required but denied or control_protocol not configured
    """
```

**Example Usage**:

```python
from kaizen.core.base_agent import BaseAgent

# Configure agent with MCP server
agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=[{
        "name": "kaizen_builtin",
        "transport": {"type": "builtin"}
    }]
)

# Execute SAFE tool (no approval needed)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__read_file",
    {"path": "/data/test.txt"}
)
print(result["output"])  # File contents

# Execute MEDIUM tool (requires approval if control_protocol configured)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/data/output.txt", "content": "Hello World"}
)

# Execute HIGH tool (always requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__bash_command",
    {"command": "ls -la"}
)
print(result["stdout"])  # Command output
```

**Tool Name Format**:
- Pattern: `mcp__<serverName>__<toolName>`
- Example: `mcp__kaizen_builtin__read_file`
- Handles tool names with underscores: `mcp__myserver__complex__tool__name`

**Return Structure**:

All tools return a standardized dict with these fields:

```python
{
    "success": True,              # Overall success status
    "output": "File contents",    # Main output (varies by tool)
    "stdout": "",                 # Standard output (Bash only)
    "stderr": "",                 # Standard error (Bash only)
    "exit_code": 0,               # Exit code (Bash only)
    "content": "Raw content",     # Raw MCP content
    "error": "",                  # Error message if failed
    "isError": False,             # MCP error flag
    "structured_content": {}      # Structured data from MCP
}
```

---

## Automatic MCP Tool Discovery

### WorkflowGenerator Integration

**Location**: `src/kaizen/core/workflow_generator.py:210-252`

Kaizen automatically discovers and exposes MCP tools to the LLM during workflow generation. When you create a `BaseAgent` with MCP servers configured, the `WorkflowGenerator` discovers available tools and passes them to `LLMAgentNode` in the correct provider-specific format.

**How It Works**:

1. **Agent Initialization**: BaseAgent passes itself to WorkflowGenerator
2. **Tool Discovery**: WorkflowGenerator calls `agent.discover_mcp_tools()` during workflow generation
3. **Format Conversion**: Tools are automatically converted to provider-specific format (OpenAI or Anthropic)
4. **LLM Integration**: Tools are passed to LLMAgentNode via `node_config["tools"]` parameter

**Example Usage**:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig

# Configure agent with MCP servers
mcp_servers = [{
    "name": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
}]

config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4o-mini",
    temperature=0.7
)

# Create agent - tools automatically discovered and exposed to LLM
agent = BaseAgent(
    config=config,
    signature=MySignature(),
    mcp_servers=mcp_servers  # Triggers automatic tool discovery
)

# Tools are now available to the LLM during execution
result = agent.run(task="Read file /workspace/data.txt and summarize")
# LLM can automatically call filesystem tools to complete the task
```

**Tool Format Conversion**:

**Location**: `src/kaizen/core/tool_formatters.py`

MCP tools are automatically converted to the correct format for your LLM provider:

```python
# MCP Format (from discover_mcp_tools)
mcp_tool = {
    "name": "mcp__filesystem__read_file",
    "description": "Read a file from the filesystem",
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"}
        },
        "required": ["path"]
    }
}

# OpenAI Function Calling Format (auto-converted)
openai_tool = {
    "type": "function",
    "function": {
        "name": "mcp__filesystem__read_file",
        "description": "Read a file from the filesystem",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    }
}

# Anthropic Tool Use Format (auto-converted)
anthropic_tool = {
    "name": "mcp__filesystem__read_file",
    "description": "Read a file from the filesystem",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"}
        },
        "required": ["path"]
    }
}
```

**Provider Support**:

- **OpenAI**: Function calling format (`type: "function"`)
- **Anthropic**: Tool use format (`input_schema`)
- **Ollama**: OpenAI function calling format (compatibility mode)

**Implementation Details**:

```python
# src/kaizen/core/tool_formatters.py

def convert_mcp_to_openai_tools(mcp_tools):
    """Convert MCP tools to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
        }
        for tool in mcp_tools
    ]

def get_tools_for_provider(mcp_tools, provider):
    """
    Get tools in provider-specific format.

    Currently uses OpenAI format as standard, with LLMAgentNode
    handling provider-specific conversion internally.
    """
    return convert_mcp_to_openai_tools(mcp_tools)
```

**Async Context Handling**:

WorkflowGenerator handles both sync and async contexts gracefully:

```python
# Detects if already in async context
try:
    loop = asyncio.get_running_loop()
    # Already async - skip tool discovery (will happen during execution)
    logger.warning("MCP tool discovery skipped: already in async context")
except RuntimeError:
    # Not async - safe to discover tools now
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        mcp_tools = loop.run_until_complete(agent.discover_mcp_tools())
        # Convert and add to node config
    finally:
        loop.close()
```

**Tool Naming Convention**:

All MCP tools follow the naming pattern: `mcp__<serverName>__<toolName>`

Examples:
- `mcp__filesystem__read_file`
- `mcp__kaizen_builtin__write_file`
- `mcp__custom_server__database_query`

**Testing**:

```python
# Test MCP tool discovery integration
agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=[{"name": "filesystem", "transport": {...}}]
)

# Verify WorkflowGenerator has agent reference
assert agent.workflow_generator.agent is agent

# Verify workflow includes tools
workflow = agent.workflow_generator.generate_signature_workflow()
built = workflow.build()

# Check LLMAgentNode has tools parameter
llm_node = built.nodes["agent_exec"]
assert "tools" in llm_node.config
assert len(llm_node.config["tools"]) > 0
```

**Benefits**:

1. **Zero Configuration**: Tools automatically discovered and exposed
2. **Provider Agnostic**: Automatic format conversion for OpenAI/Anthropic/Ollama
3. **Type Safe**: JSON schema validation from MCP protocol
4. **Extensible**: Works with any MCP server (filesystem, GitHub, Slack, custom)
5. **Consistent**: Same tool interface across all agents

---

## Danger Levels

### DangerLevel Enum

Classification system for tool safety levels.

**Location**: `src/kaizen/tools/types.py`

```python
from enum import Enum

class DangerLevel(Enum):
    """
    Danger level classification for tools.

    Determines approval requirements:
    - SAFE: No approval needed (read-only operations)
    - LOW: Minimal risk (safe mutations)
    - MEDIUM: Moderate risk (file writes, HTTP mutations)
    - HIGH: High risk (file deletion, shell commands)
    - CRITICAL: Extreme risk (system modifications, irreversible operations)
    """
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

### Builtin Tool Danger Levels

**Location**: `src/kaizen/mcp/builtin_server/danger_levels.py:12`

```python
TOOL_DANGER_LEVELS = {
    # SAFE tools (read-only, non-destructive operations)
    "read_file": DangerLevel.SAFE,
    "file_exists": DangerLevel.SAFE,
    "list_directory": DangerLevel.SAFE,
    "fetch_url": DangerLevel.SAFE,
    "extract_links": DangerLevel.SAFE,
    "http_get": DangerLevel.SAFE,

    # MEDIUM tools (writes, mutations)
    "write_file": DangerLevel.MEDIUM,
    "http_post": DangerLevel.MEDIUM,
    "http_put": DangerLevel.MEDIUM,

    # HIGH tools (destructive, requires approval every time)
    "delete_file": DangerLevel.HIGH,
    "http_delete": DangerLevel.HIGH,
    "bash_command": DangerLevel.HIGH,  # shell=True, command injection risk
}
```

### Danger Level API

```python
def get_tool_danger_level(tool_name: str) -> DangerLevel:
    """
    Get the danger level for a given tool name.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        DangerLevel enum value for the tool

    Raises:
        ValueError: If tool_name is not recognized
    """

def is_tool_safe(tool_name: str) -> bool:
    """
    Check if a tool is safe to execute without approval.

    Args:
        tool_name: Name of the MCP tool

    Returns:
        True if tool is SAFE level, False otherwise
    """

def requires_approval(
    tool_name: str,
    danger_threshold: DangerLevel = DangerLevel.MEDIUM
) -> bool:
    """
    Check if a tool requires approval based on danger threshold.

    Args:
        tool_name: Name of the MCP tool
        danger_threshold: Minimum danger level requiring approval

    Returns:
        True if tool's danger level meets or exceeds threshold
    """
```

**Example Usage**:

```python
from kaizen.mcp.builtin_server.danger_levels import (
    get_tool_danger_level,
    is_tool_safe,
    requires_approval
)

# Check danger level
level = get_tool_danger_level("bash_command")
print(level)  # DangerLevel.HIGH

# Check if safe
if is_tool_safe("read_file"):
    print("Can execute without approval")

# Check approval requirement
if requires_approval("write_file", DangerLevel.MEDIUM):
    print("Requires user approval")
```

---

## Approval Workflows

### ApprovalManager

Manages approval requests via control protocol integration.

**Location**: `src/kaizen/core/autonomy/permissions/approval_manager.py`

```python
class ApprovalManager:
    """
    Manages approval requests for tool execution.

    Integrates with BaseAgent's control protocol to request user approval
    for MEDIUM and HIGH danger level tools.
    """

    async def request_approval(
        self,
        tool_name: str,
        tool_input: dict,
        context: ExecutionContext,
        timeout: float = 60.0
    ) -> bool:
        """
        Request user approval for tool execution.

        Args:
            tool_name: Name of the tool requiring approval
            tool_input: Tool parameters for user review
            context: Current execution context
            timeout: Max time to wait for approval (seconds)

        Returns:
            True if approved, False if denied or timeout
        """
```

**Example Usage**:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.permissions import ApprovalManager, ExecutionContext

# Configure agent with control protocol for approvals
agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=[{
        "name": "kaizen_builtin",
        "transport": {"type": "builtin"}
    }],
    control_protocol=control_protocol  # Enable approval workflow
)

# MEDIUM/HIGH tools will request approval automatically
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/data/output.txt", "content": "Data"}
)
# User sees approval prompt:
# "Tool 'write_file' (danger=medium) requests approval:
#  Path: /data/output.txt
#  Content: Data
#  Approve? [Y/n]"
```

### Approval Configuration

**BaseAgent Integration**:

```python
class BaseAgent:
    def __init__(
        self,
        config: BaseAgentConfig,
        signature: Signature,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        control_protocol: Optional[ControlProtocol] = None,  # Enable approval workflow
        **kwargs
    ):
        """
        Args:
            control_protocol: Control protocol for approval requests.
                If None, MEDIUM/HIGH tools will raise PermissionError.
                If provided, MEDIUM/HIGH tools request approval.
        """
```

**Bypass Approval (E2E Tests)**:

```python
from kaizen.core.autonomy.permissions import PermissionPolicy, PermissionMode

# BYPASS mode for automated testing
policy = PermissionPolicy(ExecutionContext(mode=PermissionMode.BYPASS))

# All tools execute without approval
agent = BaseAgent(
    config=config,
    signature=signature,
    permission_policy=policy
)
```

---

## Permission Policies

### PermissionPolicy

8-layer permission decision engine for safe autonomous operation.

**Location**: `src/kaizen/core/autonomy/permissions/policy.py`

```python
class PermissionPolicy:
    """
    Permission decision engine with 8-layer evaluation logic.

    Evaluates tool execution requests through a series of checks:
    1. BYPASS mode (skip all checks)
    2. Budget check (before mode checks)
    3. PLAN mode (read-only restrictions)
    4. Explicit denied tools
    5. Explicit allowed tools
    6. Permission rules (pattern matching)
    7. Budget exhaustion
    8. Mode-based defaults / ASK fallback

    Returns:
        (True, None): Allow tool execution
        (False, reason): Deny tool execution with reason
        (None, None): Ask user for approval
    """

    def check_permission(
        self,
        tool_name: str,
        tool_input: dict,
        estimated_cost: float = 0.0,
    ) -> Tuple[Optional[bool], Optional[str]]:
        """
        Check if tool execution is permitted.

        Implements 8-layer decision logic.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            estimated_cost: Estimated cost in USD for this tool execution

        Returns:
            Tuple of (decision, reason):
            - (True, None): Allow tool execution
            - (False, reason): Deny with human-readable reason
            - (None, None): Ask user for approval
        """
```

### PermissionMode

**Location**: `src/kaizen/core/autonomy/permissions/types.py`

```python
class PermissionMode(Enum):
    """
    Permission modes for agent autonomy levels.

    - BYPASS: Allow all tools without checks (E2E tests)
    - PLAN: Read-only mode (planning phase)
    - DEFAULT: Standard mode with approval workflows
    - STRICT: Minimal tool access, explicit approval required
    """
    BYPASS = "bypass"
    PLAN = "plan"
    DEFAULT = "default"
    STRICT = "strict"
```

### ExecutionContext

**Location**: `src/kaizen/core/autonomy/permissions/context.py`

```python
class ExecutionContext:
    """
    Execution context for permission tracking.

    Tracks runtime state for permission decisions:
    - Permission mode (BYPASS, PLAN, DEFAULT, STRICT)
    - Budget tracking (limit, used)
    - Allowed/denied tools
    - Permission rules
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        budget_limit: Optional[float] = None,
        allowed_tools: Optional[set] = None,
        denied_tools: Optional[set] = None,
        rules: Optional[List[PermissionRule]] = None
    ):
        """
        Args:
            mode: Permission mode (BYPASS, PLAN, DEFAULT, STRICT)
            budget_limit: Maximum budget in USD (None = unlimited)
            allowed_tools: Explicitly allowed tools (bypass checks)
            denied_tools: Explicitly denied tools (hard block)
            rules: Permission rules for pattern matching
        """
```

**Example Usage**:

```python
from kaizen.core.autonomy.permissions import (
    PermissionPolicy,
    PermissionMode,
    ExecutionContext
)

# BYPASS mode - allow all tools (E2E tests)
ctx = ExecutionContext(mode=PermissionMode.BYPASS)
policy = PermissionPolicy(ctx)
decision, reason = policy.check_permission("bash_command", {"command": "ls"}, 0.0)
# Returns: (True, None)

# PLAN mode - read-only restrictions
ctx = ExecutionContext(mode=PermissionMode.PLAN)
policy = PermissionPolicy(ctx)
decision, reason = policy.check_permission("Read", {"path": "/data/file.txt"}, 0.0)
# Returns: (True, None) - Read allowed
decision, reason = policy.check_permission("Write", {"path": "/data/file.txt"}, 0.0)
# Returns: (False, "Plan mode: Only read-only tools allowed")

# Budget enforcement
ctx = ExecutionContext(budget_limit=10.0)
ctx.budget_used = 9.5
policy = PermissionPolicy(ctx)
decision, reason = policy.check_permission("expensive_tool", {}, 1.0)
# Returns: (False, "Budget exceeded: $9.50 spent, $0.50 remaining, tool needs $1.00")

# Explicit denied tools
ctx = ExecutionContext(denied_tools={"bash_command"})
policy = PermissionPolicy(ctx)
decision, reason = policy.check_permission("bash_command", {}, 0.0)
# Returns: (False, "Tool 'bash_command' is explicitly disallowed")

# Explicit allowed tools (bypass danger level checks)
ctx = ExecutionContext(allowed_tools={"bash_command"})
policy = PermissionPolicy(ctx)
decision, reason = policy.check_permission("bash_command", {}, 0.0)
# Returns: (True, None) - Allowed despite HIGH danger level
```

### 8-Layer Decision Logic

**Order of Evaluation**:

1. **BYPASS Mode** → Allow all (skip remaining checks)
2. **Budget Check** → Deny if budget exceeded
3. **PLAN Mode** → Allow read-only, deny execution tools
4. **Explicit Denied Tools** → Hard deny
5. **Explicit Allowed Tools** → Allow (skip remaining checks)
6. **Permission Rules** → Pattern matching with priority
7. **Budget Exhaustion** → (Already checked in Layer 2)
8. **Mode-Based Defaults** → ASK fallback for DEFAULT mode

---

## Builtin Tools

### File Tools

**5 MCP Tools** for file system operations with path traversal protection.

**Location**: `src/kaizen/mcp/builtin_server/tools/file.py`

```python
# read_file - SAFE
{
    "name": "read_file",
    "description": "Read file contents",
    "parameters": {
        "path": "File path to read"
    },
    "danger_level": "SAFE"
}

# write_file - MEDIUM
{
    "name": "write_file",
    "description": "Write content to file",
    "parameters": {
        "path": "File path to write",
        "content": "Content to write"
    },
    "danger_level": "MEDIUM"
}

# delete_file - HIGH
{
    "name": "delete_file",
    "description": "Delete a file",
    "parameters": {
        "path": "File path to delete"
    },
    "danger_level": "HIGH"
}

# list_directory - SAFE
{
    "name": "list_directory",
    "description": "List directory contents",
    "parameters": {
        "path": "Directory path to list"
    },
    "danger_level": "SAFE"
}

# file_exists - SAFE
{
    "name": "file_exists",
    "description": "Check if file exists",
    "parameters": {
        "path": "File path to check"
    },
    "danger_level": "SAFE"
}
```

**Security Features**:
- Path traversal protection (blocks `..` patterns)
- Dangerous system path blocking (`/etc`, `/sys`, `/proc`, `/dev`, `/boot`, `/root`)
- Optional sandboxing (`allowed_base` parameter)

**Example Usage**:

```python
# Read file (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__read_file",
    {"path": "/data/input.txt"}
)
print(result["output"])

# Write file (MEDIUM - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__write_file",
    {"path": "/data/output.txt", "content": "Hello World"}
)

# Delete file (HIGH - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__delete_file",
    {"path": "/data/temp.txt"}
)

# List directory (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__list_directory",
    {"path": "/data"}
)
print(result["output"])  # ["file1.txt", "file2.txt"]

# Check file exists (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__file_exists",
    {"path": "/data/test.txt"}
)
print(result["output"])  # "true" or "false"
```

### HTTP Tools

**4 MCP Tools** for HTTP operations (GET, POST, PUT, DELETE).

**Location**: `src/kaizen/mcp/builtin_server/tools/api.py`

```python
# http_get - SAFE
{
    "name": "http_get",
    "description": "HTTP GET request",
    "parameters": {
        "url": "URL to fetch",
        "headers": "Optional headers dict"
    },
    "danger_level": "SAFE"
}

# http_post - MEDIUM
{
    "name": "http_post",
    "description": "HTTP POST request",
    "parameters": {
        "url": "URL to post",
        "data": "Request body (dict or str)",
        "headers": "Optional headers dict"
    },
    "danger_level": "MEDIUM"
}

# http_put - MEDIUM
{
    "name": "http_put",
    "description": "HTTP PUT request",
    "parameters": {
        "url": "URL to put",
        "data": "Request body (dict or str)",
        "headers": "Optional headers dict"
    },
    "danger_level": "MEDIUM"
}

# http_delete - HIGH
{
    "name": "http_delete",
    "description": "HTTP DELETE request",
    "parameters": {
        "url": "URL to delete",
        "headers": "Optional headers dict"
    },
    "danger_level": "HIGH"
}
```

**Example Usage**:

```python
# GET request (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__http_get",
    {"url": "https://api.example.com/data"}
)
print(result["output"])  # JSON response

# POST request (MEDIUM - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__http_post",
    {
        "url": "https://api.example.com/submit",
        "data": {"name": "Test", "value": 123},
        "headers": {"Content-Type": "application/json"}
    }
)

# PUT request (MEDIUM - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__http_put",
    {
        "url": "https://api.example.com/update/123",
        "data": {"status": "active"}
    }
)

# DELETE request (HIGH - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__http_delete",
    {"url": "https://api.example.com/resource/123"}
)
```

### Bash Tools

**1 MCP Tool** for shell command execution.

**Location**: `src/kaizen/mcp/builtin_server/tools/bash.py`

```python
# bash_command - HIGH
{
    "name": "bash_command",
    "description": "Execute bash command",
    "parameters": {
        "command": "Bash command to execute"
    },
    "danger_level": "HIGH"  # shell=True, command injection risk
}
```

**Security Considerations**:
- Always HIGH danger level (shell=True)
- Command injection risk
- Requires approval every time
- Returns stdout, stderr, exit_code

**Example Usage**:

```python
# Execute bash command (HIGH - requires approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__bash_command",
    {"command": "ls -la /data"}
)

print(result["stdout"])    # Command output
print(result["stderr"])    # Error output
print(result["exit_code"]) # Exit code (0 = success)
```

### Web Tools

**2 MCP Tools** for web scraping.

**Location**: `src/kaizen/mcp/builtin_server/tools/web.py`

```python
# fetch_url - SAFE
{
    "name": "fetch_url",
    "description": "Fetch URL content",
    "parameters": {
        "url": "URL to fetch"
    },
    "danger_level": "SAFE"
}

# extract_links - SAFE
{
    "name": "extract_links",
    "description": "Extract links from HTML",
    "parameters": {
        "url": "URL to extract links from"
    },
    "danger_level": "SAFE"
}
```

**Example Usage**:

```python
# Fetch URL (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__fetch_url",
    {"url": "https://example.com"}
)
print(result["output"])  # HTML content

# Extract links (SAFE - no approval)
result = await agent.execute_mcp_tool(
    "mcp__kaizen_builtin__extract_links",
    {"url": "https://example.com"}
)
print(result["output"])  # ["https://example.com/page1", ...]
```

---

## Custom Tool Integration

### Creating Custom MCP Tools

**Step 1: Define Tool with @mcp_tool Decorator**

```python
from kaizen.mcp.builtin_server.decorators import mcp_tool
from kaizen.tools.types import DangerLevel

@mcp_tool(
    name="custom_database_query",
    description="Execute database query",
    danger_level=DangerLevel.MEDIUM,
    parameters={
        "query": {"type": "string", "description": "SQL query to execute"},
        "database": {"type": "string", "description": "Database name"}
    }
)
async def custom_database_query(query: str, database: str) -> dict:
    """
    Custom tool implementation.

    Returns:
        Dict with success, output, error fields
    """
    try:
        # Execute query
        result = execute_sql(query, database)
        return {
            "success": True,
            "output": result,
            "error": ""
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "error": str(e)
        }
```

**Step 2: Register Custom MCP Server**

```python
# Configure custom MCP server
custom_server_config = {
    "name": "custom_server",
    "transport": {
        "type": "stdio",
        "command": "python",
        "args": ["-m", "my_custom_server"]
    }
}

# Create agent with custom server
agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=[
        {"name": "kaizen_builtin", "transport": {"type": "builtin"}},
        custom_server_config
    ]
)
```

**Step 3: Execute Custom Tool**

```python
# Execute custom tool
result = await agent.execute_mcp_tool(
    "mcp__custom_server__custom_database_query",
    {
        "query": "SELECT * FROM users LIMIT 10",
        "database": "production"
    }
)
print(result["output"])
```

### Custom Danger Levels

```python
from kaizen.mcp.builtin_server.danger_levels import TOOL_DANGER_LEVELS
from kaizen.tools.types import DangerLevel

# Register custom tool danger level
TOOL_DANGER_LEVELS["custom_database_query"] = DangerLevel.MEDIUM

# Or define custom danger level mapping
CUSTOM_DANGER_LEVELS = {
    "safe_analytics_query": DangerLevel.SAFE,
    "data_export": DangerLevel.MEDIUM,
    "schema_migration": DangerLevel.HIGH,
    "production_deployment": DangerLevel.CRITICAL
}

# Merge with builtin levels
TOOL_DANGER_LEVELS.update(CUSTOM_DANGER_LEVELS)
```

---

## Testing

**Location**: `tests/e2e/autonomy/test_tool_calling_e2e.py`, `tests/e2e/autonomy/tools/`

**Test Coverage**:
- 13 E2E tests with real Ollama/OpenAI inference
- Tool calling tests (file, HTTP, bash)
- Approval workflow tests (SAFE, MEDIUM, HIGH)
- Permission policy tests (BYPASS, PLAN, DEFAULT)
- Budget enforcement tests

**Example Test**:

```python
import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.permissions import PermissionPolicy, PermissionMode, ExecutionContext

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_file_tools_e2e():
    """Test file tools with real MCP execution."""

    # Create agent with BYPASS mode for E2E testing
    policy = PermissionPolicy(ExecutionContext(mode=PermissionMode.BYPASS))
    agent = BaseAgent(
        config=config,
        signature=signature,
        mcp_servers=[{
            "name": "kaizen_builtin",
            "transport": {"type": "builtin"}
        }],
        permission_policy=policy
    )

    # Test read_file (SAFE)
    result = await agent.execute_mcp_tool(
        "mcp__kaizen_builtin__read_file",
        {"path": test_file_path}
    )
    assert result["success"] is True
    assert "content" in result["output"]

    # Test write_file (MEDIUM - bypassed by policy)
    result = await agent.execute_mcp_tool(
        "mcp__kaizen_builtin__write_file",
        {"path": output_path, "content": "Test"}
    )
    assert result["success"] is True
```

---

## See Also

- [Control Protocol API](control-protocol-api.md) - Control protocol integration
- [Multi-Agent Coordination Guide](../guides/multi-agent-coordination.md) - Tool delegation patterns
- [BaseAgent Architecture Guide](../guides/baseagent-architecture.md) - Agent lifecycle
- [Approval Workflows E2E Tests](../../tests/e2e/autonomy/tools/test_approval_workflows_e2e.py) - Test examples
