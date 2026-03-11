# MCP Tool Migration Plan

**Status**: APPROVED - Ready for Implementation
**Created**: 2025-10-26
**Priority**: CRITICAL (Before Phase 1)
**Audit Report**: See [MCP_MIGRATION_AUDIT.md](./MCP_MIGRATION_AUDIT.md) for detailed analysis

---

## Executive Summary

**Problem**: Kaizen maintains a custom ToolRegistry and 12 custom builtin tools, duplicating MCP's functionality. This violates the principle of composability and portability.

**Decision**: **ELIMINATE custom tool system. Migrate 100% to MCP.**

**Audit Findings** (See MCP_MIGRATION_AUDIT.md):
- ✅ BaseAgent ALREADY FULLY SUPPORTS MCP (MCPClient, discover_mcp_tools(), execute_mcp_tool())
- ✅ 1,683 lines of custom code identified for removal (ToolRegistry + builtin tools)
- ✅ 570 lines of MCP-compliant code to be created
- ✅ Net reduction: 1,113 lines (66% reduction)
- ✅ All 12 tools analyzed and migration path identified

**Impact**:
- ✅ High composability - any MCP tool works instantly
- ✅ High portability - tools created daily by community
- ✅ No dual maintenance - single tool system
- ✅ Standards-compliant - follows MCP protocol
- ✅ Future-proof - grows with MCP ecosystem

---

## Part 1: Current State Analysis

### 1.1 Custom Tool System (TO REMOVE)

**kaizen/tools/registry.py** (Custom ToolRegistry):
- 200+ lines of custom tool management
- Custom ToolDefinition, ToolParameter, ToolCategory
- Custom DangerLevel approval system
- Custom executor functions

**kaizen/tools/builtin/** (12 Custom Tools):
- `file.py` - read_file, write_file, delete_file, list_directory
- `api.py` - http_get, http_post, http_put, http_delete
- `bash.py` - bash_command, run_script
- `web.py` - fetch_url, extract_links

**Problem**: This duplicates MCP functionality!

### 1.2 Existing MCP Integration (TO EXPAND)

**BaseAgent already has MCP**:
- `discover_mcp_tools()` - Discovers tools from MCP servers
- `execute_mcp_tool()` - Executes MCP tools
- `MCPClient` integration - Full MCP client support
- Naming convention: `mcp__<serverName>__<toolName>`

**Good News**: Infrastructure already exists!

---

## Part 2: Migration Strategy

### 2.1 Phase 0: Create Builtin MCP Server (NEW)

**Approach**: Convert 12 builtin tools into an MCP server

**Why MCP Server (not client)**:
- MCP servers provide tools to clients
- BaseAgent is an MCP client (already implemented)
- Builtin tools should be an MCP server that BaseAgent connects to

**Implementation**:
```
kaizen/mcp/
├── builtin_server/
│   ├── __init__.py
│   ├── server.py          # MCP server implementation
│   ├── tools/
│   │   ├── file.py        # read_file, write_file (MCP tools)
│   │   ├── api.py         # http_get, http_post (MCP tools)
│   │   ├── bash.py        # bash_command (MCP tool)
│   │   └── web.py         # fetch_url (MCP tool)
│   └── config.json        # MCP server config
```

**Example - file.py as MCP tool**:
```python
# kaizen/mcp/builtin_server/tools/file.py

from kailash.mcp_server import MCPServer, tool

@tool(
    name="read_file",
    description="Read contents from a file",
    parameters={
        "file_path": {"type": "string", "description": "Path to file"},
    },
)
async def read_file(file_path: str) -> dict:
    """Read file contents (MCP tool implementation)."""
    with open(file_path, "r") as f:
        content = f.read()
    return {"content": content}

@tool(
    name="write_file",
    description="Write contents to a file",
    parameters={
        "file_path": {"type": "string"},
        "content": {"type": "string"},
    },
)
async def write_file(file_path: str, content: str) -> dict:
    """Write file contents (MCP tool implementation)."""
    with open(file_path, "w") as f:
        f.write(content)
    return {"success": True}
```

**Server Implementation**:
```python
# kaizen/mcp/builtin_server/server.py

from kailash.mcp_server import MCPServer

from .tools import file, api, bash, web

# Create MCP server with all builtin tools
server = MCPServer(name="kaizen_builtin")

# Auto-register all @tool decorated functions
server.auto_register_tools([file, api, bash, web])

# Start server (stdio transport for BaseAgent)
if __name__ == "__main__":
    server.run(transport="stdio")
```

**BaseAgent Auto-Connect**:
```python
# kaizen/core/base_agent.py

class BaseAgent:
    def __init__(self, ...):
        # Auto-connect to builtin MCP server
        self.mcp_servers = mcp_servers or [
            {
                "name": "kaizen_builtin",
                "command": "python",
                "args": ["-m", "kaizen.mcp.builtin_server"],
                "transport": "stdio",
            }
        ]

        # Discover tools automatically
        if self.mcp_servers:
            self._setup_mcp_client()
```

### 2.2 Benefits of This Approach

**Composability**:
- Any MCP tool from any server works instantly
- Community tools integrate seamlessly
- No code changes needed for new tools

**Portability**:
- Builtin tools are standard MCP tools
- Can run standalone or integrated
- Works with any MCP client

**Maintainability**:
- Single tool protocol (MCP)
- No dual system maintenance
- Standards-compliant

**Ecosystem**:
- Grows with MCP ecosystem
- Benefits from community contributions
- Future-proof architecture

---

## Part 3: Migration Steps

### Step 1: Create Builtin MCP Server

- [ ] Create `kaizen/mcp/builtin_server/` structure
- [ ] Migrate `file.py` tools to MCP format
- [ ] Migrate `api.py` tools to MCP format
- [ ] Migrate `bash.py` tools to MCP format
- [ ] Migrate `web.py` tools to MCP format
- [ ] Create `server.py` with MCPServer
- [ ] Test server standalone

### Step 2: Update BaseAgent

- [ ] Add auto-connection to builtin MCP server
- [ ] Update `get_available_tools()` to use MCP discovery
- [ ] Update tool execution to use `execute_mcp_tool()`
- [ ] Remove ToolRegistry references
- [ ] Test MCP tool discovery and execution

### Step 3: Remove Custom Tool System

- [ ] Delete `kaizen/tools/registry.py`
- [ ] Delete `kaizen/tools/builtin/` directory
- [ ] Delete `kaizen/tools/types.py` (ToolDefinition, etc.)
- [ ] Delete `kaizen/tools/executor.py`
- [ ] Update all imports

### Step 4: Update Agent Integration

- [ ] Update ReActAgent to use MCP tools only
- [ ] Update AutonomousAgent to use MCP tools only
- [ ] Update all agent examples
- [ ] Update documentation

### Step 5: Update Tests

- [ ] Update tool tests to use MCP
- [ ] Test builtin MCP server
- [ ] Test agent tool calling via MCP
- [ ] Test approval workflow with MCP tools

---

## Part 4: MCP Tool Approval Workflow

**Challenge**: MCP doesn't have DangerLevel approval built-in.

**Solution**: Implement approval at BaseAgent level based on tool name patterns.

```python
# kaizen/core/base_agent.py

class BaseAgent:
    # Tool approval configuration
    TOOL_DANGER_LEVELS = {
        # SAFE - Auto-approve
        "read_file": "SAFE",
        "http_get": "SAFE",
        "fetch_url": "SAFE",

        # MODERATE - Confirm before execution
        "write_file": "MODERATE",
        "http_post": "MODERATE",

        # DANGEROUS - Require explicit approval
        "delete_file": "DANGEROUS",
        "bash_command": "DANGEROUS",

        # CRITICAL - Require confirmation + rationale
        "run_script": "CRITICAL",
    }

    async def execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """Execute tool with approval workflow."""
        # Get danger level
        danger_level = self.TOOL_DANGER_LEVELS.get(tool_name, "MODERATE")

        # Approval workflow
        if danger_level in ["DANGEROUS", "CRITICAL"]:
            approved = await self._request_tool_approval(
                tool_name, arguments, danger_level
            )
            if not approved:
                return {"error": "Tool execution denied by user"}

        # Execute via MCP
        return await self.execute_mcp_tool(
            server_name="kaizen_builtin",
            tool_name=tool_name,
            arguments=arguments,
        )
```

**Benefits**:
- Approval logic in BaseAgent (single place)
- MCP tools remain standard-compliant
- Easy to extend for community tools

---

## Part 5: Migration Timeline

### Week 0 (Pre-Phase 1): MCP Migration
- [ ] Day 1-2: Create builtin MCP server
- [ ] Day 3: Update BaseAgent integration
- [ ] Day 4: Remove custom tool system
- [ ] Day 5: Testing and validation

### Week 1 (Phase 1): Standardization
- [ ] Method standardization
- [ ] Agent registration
- [ ] MCP/A2A compliance verification

---

## Part 6: Code Removal Summary

**DELETE (No longer needed)**:
```
kaizen/tools/
├── registry.py          # ❌ DELETE (327 lines)
├── types.py             # ❌ DELETE (ToolDefinition, etc.)
├── executor.py          # ❌ DELETE (tool execution)
└── builtin/
    ├── file.py          # ❌ DELETE (migrate to MCP)
    ├── api.py           # ❌ DELETE (migrate to MCP)
    ├── bash.py          # ❌ DELETE (migrate to MCP)
    └── web.py           # ❌ DELETE (migrate to MCP)
```

**CREATE (New MCP-based system)**:
```
kaizen/mcp/
└── builtin_server/
    ├── server.py        # ✅ NEW (MCP server)
    └── tools/
        ├── file.py      # ✅ NEW (MCP tools)
        ├── api.py       # ✅ NEW (MCP tools)
        ├── bash.py      # ✅ NEW (MCP tools)
        └── web.py       # ✅ NEW (MCP tools)
```

**Total Code Reduction**: ~500 lines removed, ~200 lines added (MCP)
**Net Reduction**: ~300 lines (simpler, standards-compliant)

---

## Part 7: Benefits Summary

### Composability
- ✅ Any MCP tool works instantly
- ✅ No custom integration needed
- ✅ Community tools "just work"

### Portability
- ✅ Builtin tools are standard MCP
- ✅ Can be used by any MCP client
- ✅ Not locked into Kaizen

### Maintainability
- ✅ Single protocol (MCP)
- ✅ No dual system
- ✅ Standards-based

### Ecosystem
- ✅ Grows with MCP
- ✅ Community contributions
- ✅ Future-proof

### Example - Adding New Tool

**BEFORE (Custom System)**:
```python
# Requires custom ToolDefinition, registration, executor...
def my_tool_impl(arg1, arg2):
    ...

registry.register(
    name="my_tool",
    description="...",
    category=ToolCategory.CUSTOM,
    danger_level=DangerLevel.SAFE,
    parameters=[ToolParameter(...)],
    returns={...},
    executor=my_tool_impl,
)
```

**AFTER (MCP)**:
```python
# Just create an MCP server!
@tool(name="my_tool", description="...")
async def my_tool(arg1: str, arg2: int) -> dict:
    ...

# That's it! BaseAgent discovers it automatically.
```

---

## Part 8: Decision Points

**Confirmed**:
1. ✅ Eliminate custom ToolRegistry completely
2. ✅ Eliminate custom builtin tools
3. ✅ Convert builtin tools to MCP server
4. ✅ BaseAgent auto-connects to builtin MCP server
5. ✅ All tool calling goes through MCP
6. ✅ Approval workflow at BaseAgent level

**Implementation Priority**: Week 0 (BEFORE Phase 1)

---

**END OF MCP MIGRATION PLAN**
