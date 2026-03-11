# ADR-014: Comprehensive MCP Integration for BaseAgent

**Date**: 2025-10-22
**Status**: Proposed
**Decision Makers**: Kaizen Framework Team
**Impact**: CRITICAL - Replaces custom tool system with MCP standard

---

## Context

### Problem Statement

Our current tool system is **custom-built and NOT MCP-compliant**:
- Custom ToolRegistry, ToolExecutor, ToolDefinition (not MCP standard)
- Only supports tools, NOT resources or prompts
- No dynamic discovery from MCP servers
- Incompatible with MCP ecosystem

**User feedback**: "This is very disappointing... you would have implemented a toy mickey mouse product!"

### Discovery

Kailash Core SDK provides **production-ready MCP client** (`kailash.mcp_server.MCPClient`):

**Available Capabilities**:
1. ✅ **Tools**: `discover_tools()`, `call_tool()` - FULLY IMPLEMENTED
2. ⚠️ **Resources**: `list_resources()`, `read_resource()` - STUB ONLY
3. ❌ **Prompts**: Not yet implemented in Kailash MCP client

**MCP Protocol Specification** (from Anthropic):
- **Tools**: Executable functions with parameters
- **Resources**: Read-only data sources (files, databases, APIs)
- **Prompts**: Reusable prompt templates with variables

---

## Decision

We will **integrate Kailash MCP client directly into BaseAgent** with comprehensive support for **tools, resources, and prompts**.

### Core Principle

**Use Kailash MCP directly** - NO separate `mcp/` directory needed. Thin wrapper in BaseAgent for MCP capabilities.

### Architecture

**BaseAgent becomes MCP-aware**:
```python
class BaseAgent:
    def __init__(
        self,
        config,
        signature,
        mcp_servers: Optional[List[Dict]] = None,  # MCP server configs
        **kwargs
    ):
        # Existing BaseAgent init...

        # MCP Integration (opt-in)
        self.mcp_client = MCPClient() if mcp_servers else None
        self.mcp_servers = mcp_servers or []

        # Discovery caches (with server prefixes)
        self._discovered_mcp_tools = {}      # {server_name: [tools]}
        self._discovered_mcp_resources = {}  # {server_name: [resources]}
        self._discovered_mcp_prompts = {}    # {server_name: [prompts]}
```

---

## Implementation Plan

### Phase 1: MCP Tools Integration (Week 1)

**Goal**: Replace custom tool system with MCP tools

**Tasks**:
1. Add `mcp_client` and `mcp_servers` to BaseAgent.__init__
2. Implement `discover_mcp_tools()` using Kailash MCPClient
3. Implement `execute_mcp_tool()` with server routing
4. Merge MCP tools with existing builtin tools in `discover_tools()`
5. Tool naming: `mcp__<serverName>__<toolName>` format

**Code**:
```python
async def discover_mcp_tools(
    self,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """Discover tools from all configured MCP servers."""
    if not self.mcp_client:
        return []

    if self._discovered_mcp_tools and not force_refresh:
        # Return flattened list from cache
        return [
            tool for tools in self._discovered_mcp_tools.values()
            for tool in tools
        ]

    all_tools = []
    for server_config in self.mcp_servers:
        server_name = server_config.get("name", "unknown")

        # Discover tools from server
        tools = await self.mcp_client.discover_tools(server_config)

        # Prefix with mcp__<serverName>__
        for tool in tools:
            tool["name"] = f"mcp__{server_name}__{tool['name']}"
            tool["mcp_server"] = server_name
            tool["original_name"] = tool["name"].split("__")[-1]

        # Cache by server
        self._discovered_mcp_tools[server_name] = tools
        all_tools.extend(tools)

    return all_tools

async def execute_mcp_tool(
    self,
    tool_name: str,  # Format: mcp__serverName__toolName
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute MCP tool with server routing."""
    # Parse tool name: mcp__serverName__toolName
    parts = tool_name.split("__")
    if len(parts) != 3 or parts[0] != "mcp":
        raise ValueError(f"Invalid MCP tool name: {tool_name}")

    server_name, actual_tool_name = parts[1], parts[2]

    # Find server config
    server_config = next(
        (s for s in self.mcp_servers if s.get("name") == server_name),
        None
    )
    if not server_config:
        raise ValueError(f"Server not found: {server_name}")

    # Call tool via Kailash MCP client
    result = await self.mcp_client.call_tool(
        server_config,
        actual_tool_name,
        params
    )

    return result

async def discover_tools(self) -> List[Dict[str, Any]]:
    """Discover ALL tools (builtin + MCP)."""
    all_tools = []

    # Existing builtin tools (if tool_registry exists)
    if hasattr(self, 'tool_registry') and self.tool_registry:
        for tool_name in self.tool_registry.get_tool_names():
            tool = self.tool_registry.get(tool_name)
            all_tools.append({
                "name": tool_name,
                "description": tool.description,
                "danger_level": tool.danger_level.value,
                "source": "builtin"
            })

    # MCP tools
    mcp_tools = await self.discover_mcp_tools()
    all_tools.extend(mcp_tools)

    return all_tools
```

**Tests**:
- `tests/unit/core/test_base_agent_mcp_tools.py` (30 tests)
- `tests/integration/core/test_mcp_tool_discovery.py` (real MCP server)

---

### Phase 2: MCP Resources Integration (Week 2)

**Goal**: Add resource discovery and reading capabilities

**Challenge**: Kailash MCPClient has **stubs only** for resources
- `list_resources()` - returns `pass` (line 527-537)
- `read_resource()` - returns `pass` (line 539-547)

**Solution**: Implement missing resource methods OR wait for Kailash to complete them

**Option A: Implement in Kailash** (recommended)
```python
# Contribute to kailash.mcp_server.client.MCPClient

async def list_resources(
    self,
    server_config: Union[str, Dict[str, Any]],
    force_refresh: bool = False,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """List available resources from MCP server."""
    # Implementation similar to discover_tools()
    transport_type = self._get_transport_type(server_config)

    if transport_type == "stdio":
        return await self._list_resources_stdio(server_config, timeout)
    elif transport_type == "sse":
        return await self._list_resources_sse(server_config, timeout)
    elif transport_type == "http":
        return await self._list_resources_http(server_config, timeout)

    # Use official Anthropic MCP SDK: session.list_resources()
```

**Option B: Workaround in Kaizen** (if Kailash not updated)
```python
# src/kaizen/core/base_agent.py

async def discover_mcp_resources(self) -> List[Dict[str, Any]]:
    """Discover resources from MCP servers (workaround)."""
    # Direct use of Anthropic MCP SDK if Kailash client incomplete
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    # ... implementation ...
```

**BaseAgent Methods**:
```python
async def discover_mcp_resources(
    self,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """Discover resources from all configured MCP servers."""
    # Similar to discover_mcp_tools()
    # Resource naming: mcp__<serverName>__<resourceUri>

async def read_mcp_resource(
    self,
    resource_uri: str  # Format: mcp__serverName__uri
) -> Dict[str, Any]:
    """Read MCP resource with server routing."""
    # Parse URI, find server, call read_resource()
```

**Tests**:
- `tests/unit/core/test_base_agent_mcp_resources.py` (20 tests)
- `tests/integration/core/test_mcp_resource_reading.py` (real MCP server)

---

### Phase 3: MCP Prompts Integration (Week 3)

**Goal**: Add prompt discovery and retrieval capabilities

**Challenge**: Kailash MCPClient has **NO prompt methods yet**

**Solution**: Implement prompt methods using Anthropic MCP SDK

**Kailash MCP Client Addition**:
```python
# kailash.mcp_server.client.MCPClient (to be added)

async def list_prompts(
    self,
    server_config: Union[str, Dict[str, Any]],
    force_refresh: bool = False,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """List available prompts from MCP server."""
    # Use official Anthropic SDK: session.list_prompts()

async def get_prompt(
    self,
    server_config: Union[str, Dict[str, Any]],
    prompt_name: str,
    arguments: Dict[str, Any],
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Get prompt template with arguments."""
    # Use official Anthropic SDK: session.get_prompt()
```

**BaseAgent Methods**:
```python
async def discover_mcp_prompts(
    self,
    force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """Discover prompts from all configured MCP servers."""
    # Prompt naming: mcp__<serverName>__<promptName>

async def get_mcp_prompt(
    self,
    prompt_name: str,  # Format: mcp__serverName__promptName
    arguments: Dict[str, Any] = {}
) -> str:
    """Get rendered prompt template with arguments."""
    # Parse name, find server, call get_prompt()
    # Return: rendered prompt string
```

**Use Case**:
```python
# User: Configure agent with prompt templates from MCP
mcp_servers = [
    {
        "name": "templates",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "mcp_server_prompts"]
    }
]

agent = BaseAgent(config=config, signature=signature, mcp_servers=mcp_servers)

# Discover available prompts
prompts = await agent.discover_mcp_prompts()
# Returns: [
#   {"name": "mcp__templates__code_review", "description": "..."},
#   {"name": "mcp__templates__summarization", "description": "..."}
# ]

# Get rendered prompt
prompt = await agent.get_mcp_prompt(
    "mcp__templates__code_review",
    arguments={"language": "python", "style": "strict"}
)
# Returns: "Review the following Python code with strict standards: ..."
```

**Tests**:
- `tests/unit/core/test_base_agent_mcp_prompts.py` (20 tests)
- `tests/integration/core/test_mcp_prompt_templates.py` (real MCP server)

---

### Phase 4: Unified Discovery API (Week 4)

**Goal**: Single method to discover all MCP capabilities

```python
async def discover_mcp_capabilities(
    self,
    force_refresh: bool = False
) -> Dict[str, List[Dict[str, Any]]]:
    """Discover ALL MCP capabilities (tools, resources, prompts)."""
    return {
        "tools": await self.discover_mcp_tools(force_refresh),
        "resources": await self.discover_mcp_resources(force_refresh),
        "prompts": await self.discover_mcp_prompts(force_refresh)
    }
```

---

## User Configuration Examples

### Example 1: MCP Tools Only
```python
from kaizen.core.base_agent import BaseAgent

mcp_servers = [
    {
        "name": "filesystem",
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "mcp_server_filesystem"]
    }
]

agent = BaseAgent(
    config=config,
    signature=signature,
    mcp_servers=mcp_servers
)

# Discover tools (builtin + MCP)
tools = await agent.discover_tools()
# Returns: [
#   {"name": "read_file", "source": "builtin"},
#   {"name": "mcp__filesystem__list_directory", "source": "mcp"}
# ]

# Execute MCP tool
result = await agent.execute_tool("mcp__filesystem__list_directory", {"path": "/tmp"})
```

### Example 2: MCP Tools + Resources
```python
mcp_servers = [
    {
        "name": "github",
        "transport": "sse",
        "url": "http://localhost:8000/mcp",
        "auth": {"type": "bearer", "token": "ghp_..."}
    }
]

agent = BaseAgent(config=config, signature=signature, mcp_servers=mcp_servers)

# Discover resources
resources = await agent.discover_mcp_resources()
# Returns: [
#   {"name": "mcp__github__repos/user/project/README.md", "uri": "..."}
# ]

# Read resource
readme = await agent.read_mcp_resource("mcp__github__repos/user/project/README.md")
```

### Example 3: Full MCP Integration
```python
mcp_servers = [
    {"name": "filesystem", "transport": "stdio", ...},
    {"name": "github", "transport": "sse", ...},
    {"name": "templates", "transport": "stdio", ...}
]

agent = BaseAgent(config=config, signature=signature, mcp_servers=mcp_servers)

# Discover ALL capabilities
capabilities = await agent.discover_mcp_capabilities()
print(f"Tools: {len(capabilities['tools'])}")
print(f"Resources: {len(capabilities['resources'])}")
print(f"Prompts: {len(capabilities['prompts'])}")
```

---

## Migration from Custom Tools

### Current (Custom ToolRegistry)
```python
# Tools auto-configured via MCP



# 12 builtin tools enabled via MCP

agent = BaseAgent(config=config, signature=signature, tools="all"  # Enable 12 builtin tools via MCP
```

### Future (MCP + Builtin)
```python
# Option 1: MCP only
mcp_servers = [...]
agent = BaseAgent(config=config, signature=signature, mcp_servers=mcp_servers)

# Option 2: Builtin + MCP (backward compatible)

# 12 builtin tools enabled via MCP

agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    mcp_servers=mcp_servers  # Additional MCP tools
)

# discover_tools() returns BOTH builtin and MCP tools
```

---

## Rationale

### Why Use Kailash MCP Directly?

| Dimension | Kailash MCP | Custom Kaizen MCP |
|-----------|-------------|-------------------|
| **Implementation Effort** | ~200 lines (thin wrapper) | ~2000+ lines (full MCP client) |
| **Maintenance** | Kailash team maintains | Kaizen team maintains |
| **Compatibility** | Standard MCP protocol | Risk of divergence |
| **Features** | Auth, retry, metrics, discovery | Need to build all |
| **Testing** | Kailash already tested | Need full test suite |

### Why NO mcp/ Directory?

1. **Kailash already has it** - Use existing production-ready client
2. **Minimal code** - Just add methods to BaseAgent (~200 lines total)
3. **No duplication** - Don't reinvent MCP protocol
4. **Clear ownership** - MCP client = Kailash, agent integration = Kaizen

---

## Consequences

### Benefits

1. **Standard compliance**: 100% MCP protocol (not custom)
2. **Dynamic discovery**: Find tools/resources/prompts from any MCP server
3. **Ecosystem compatibility**: Works with all MCP servers (Claude Code, filesystem, GitHub, etc.)
4. **Production-ready**: Kailash MCP has auth, retry, metrics, failover
5. **Minimal code**: ~200 lines in BaseAgent vs. ~2000+ for full implementation

### Costs

1. **Kailash dependency**: Need Kailash MCP client updates for missing features (resources, prompts)
2. **Breaking change**: Custom ToolRegistry still works but MCP is recommended
3. **Learning curve**: Users need to configure MCP servers

### Risks

1. **Kailash incomplete**: Resources/prompts not yet implemented
   - **Mitigation**: Phase 1 (tools) uses complete implementation, Phase 2-3 can use direct Anthropic SDK if needed
2. **Server availability**: MCP servers must be running
   - **Mitigation**: Builtin tools still work as fallback

---

## Action Items

### Phase 1: MCP Tools (Week 1) - PRIORITY
- [ ] Add `mcp_client`, `mcp_servers` to BaseAgent.__init__
- [ ] Implement `discover_mcp_tools()` method
- [ ] Implement `execute_mcp_tool()` method
- [ ] Merge MCP + builtin in `discover_tools()`
- [ ] Write 30 unit tests for MCP tool integration
- [ ] Write 10 integration tests with real MCP server

### Phase 2: MCP Resources (Week 2)
- [ ] Check Kailash MCP for `list_resources()` implementation
- [ ] Implement OR contribute to Kailash
- [ ] Add `discover_mcp_resources()` method
- [ ] Add `read_mcp_resource()` method
- [ ] Write 20 unit tests
- [ ] Write 10 integration tests

### Phase 3: MCP Prompts (Week 3)
- [ ] Check Kailash MCP for `list_prompts()` implementation
- [ ] Implement OR contribute to Kailash
- [ ] Add `discover_mcp_prompts()` method
- [ ] Add `get_mcp_prompt()` method
- [ ] Write 20 unit tests
- [ ] Write 10 integration tests

### Phase 4: Documentation & Examples (Week 4)
- [ ] Write comprehensive MCP integration guide
- [ ] Create 3 examples (tools, resources, prompts)
- [ ] Update BaseAgent API reference
- [ ] Write migration guide from custom tools

---

## Decision Outcome

**PROPOSED** - Awaiting user confirmation on:
1. ✅ Use Kailash MCP directly (NO separate mcp/ directory)
2. ❓ Implementation order: Start with Phase 1 (tools) first?
3. ❓ Handling incomplete Kailash features: Contribute to Kailash OR workaround in Kaizen?

**Next Step**: User discussion on implementation approach.

---

**Last Updated**: 2025-10-22
**Supersedes**: None (first MCP integration ADR)
**Superseded By**: None (active)
