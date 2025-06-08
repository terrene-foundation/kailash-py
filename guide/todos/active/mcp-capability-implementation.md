# MCP as Capability Implementation Plan

## Overview
Redesign MCP integration as a built-in capability of LLM agents rather than separate nodes, using the official Anthropic MCP Python SDK.

## Phase 1: MCP Service Layer (Priority: High) ✅ COMPLETE

### 1.1 Remove Existing MCP Implementations
- [x] Delete `src/kailash/nodes/mcp/client.py` (MCPClient node)
- [x] Delete `src/kailash/nodes/mcp/server.py` (MCPServer node)
- [x] Delete `src/kailash/mcp/client.py` (duplicate MCPClientNode)
- [x] Delete `src/kailash/utils/mcp/` directory
- [x] Remove MCP node exports from `__init__.py` files

### 1.2 Create New MCP Service Structure
- [x] Create `src/kailash/mcp/__init__.py` with exports
- [x] Implement `src/kailash/mcp/client.py` using official SDK:
  ```python
  class MCPClient:
      """MCP client service using official Anthropic SDK."""
      async def discover_tools(server_url: str) -> List[Dict]
      async def call_tool(server_url: str, tool_name: str, arguments: Dict) -> Any
      async def list_resources(server_url: str) -> List[Dict]
      async def read_resource(server_url: str, uri: str) -> Any
  ```

### 1.3 Implement MCP Server Framework
- [x] Create `src/kailash/mcp/server.py`:
  ```python
  class MCPServer:
      """Base class for MCP servers using FastMCP."""
      def __init__(self, name: str, port: int)
      def add_tool(self, func: Callable)
      def add_resource(self, uri: str, handler: Callable)
      def start(self)
      def stop(self)
  ```

### 1.4 Build Example MCP Servers
- [ ] Implement `src/kailash/mcp/servers/filesystem.py`
- [ ] Implement `src/kailash/mcp/servers/database.py`
- [x] Migrate `src/kailash/mcp/ai_registry_server.py` to new framework
- [ ] Add CLI commands for starting servers

## Phase 2: LLM Agent Enhancement (Priority: High) ✅ COMPLETE

### 2.1 Update LLMAgentNode
- [x] Add MCP parameters to `get_parameters()`:
  - `mcp_servers`: List of MCP server URLs/configs
  - `auto_discover_tools`: Boolean for auto-discovery
  - `mcp_context`: List of specific resources to retrieve
- [x] Add internal `_mcp_client` instance variable
- [x] Implement MCP initialization in `async_run()`
- [x] Add tool discovery logic
- [x] Integrate tool execution with LLM responses
- [x] Update docstrings with MCP examples

### 2.2 Update IterativeLLMAgentNode
- [x] Remove inheritance from LLMAgentNode if needed
- [x] Add same MCP parameters as LLMAgentNode
- [x] Integrate MCP discovery into Phase 1 (Discovery)
- [x] Update tool execution in Phase 3 (Execution)
- [x] Remove direct imports of old MCPClient

### 2.3 Create MCP Mixin (Optional)
- [x] Create `src/kailash/nodes/mixins/mcp.py`:
  ```python
  class MCPCapabilityMixin:
      """Mixin to add MCP capabilities to any node."""
      def _init_mcp_client(self)
      async def _discover_mcp_tools(self, servers: List[str])
      async def _call_mcp_tool(self, server: str, tool: str, args: Dict)
  ```

## Phase 3: Migration and Compatibility (Priority: Medium)

### 3.1 Create Migration Guide
- [ ] Document breaking changes
- [ ] Provide before/after workflow examples
- [ ] Create migration script for common patterns
- [ ] Add to `guide/migration/mcp-capability-migration.md`

### 3.2 Update Examples
- [ ] Update `workflow_ai_strategy_consultation.py`
- [ ] Update `workflow_iterative_agent_comprehensive.py`
- [ ] Update `workflow_mcp_agentic.py`
- [ ] Update `workflow_mcp_agentic_simple.py`
- [ ] Create new example showing MCP capabilities

### 3.3 Add Deprecation Warnings
- [ ] Add warnings to old MCP node classes
- [ ] Point users to migration guide
- [ ] Plan removal in future version

## Phase 4: Testing and Documentation (Priority: High)

### 4.1 Update Tests
- [ ] Remove tests for MCPClient/MCPServer nodes
- [ ] Add tests for MCP service layer
- [ ] Add tests for LLMAgent MCP capabilities
- [ ] Add integration tests with mock MCP servers
- [ ] Test migration paths

### 4.2 Update Documentation
- [ ] Update `docs/api/nodes.rst` - remove MCP nodes
- [ ] Update `docs/api/llm_agents.rst` - add MCP capabilities
- [ ] Create `docs/guides/mcp_integration.rst`
- [ ] Update workflow examples in docs
- [ ] Update README with new patterns

### 4.3 Create New Examples
- [ ] Simple MCP-enabled agent example
- [ ] Multi-agent with different MCP servers
- [ ] Iterative agent with MCP discovery
- [ ] Custom node with MCP mixin (edge case)

## Implementation Order

1. **Week 1**:
   - Phase 1.1-1.2: Remove old, create service structure
   - Phase 1.3-1.4: Implement servers
   - Phase 2.1: Start LLMAgent enhancement

2. **Week 2**:
   - Phase 2.1-2.2: Complete agent enhancements
   - Phase 3.1-3.2: Migration support
   - Phase 4.1: Testing

3. **Week 3**:
   - Phase 4.2-4.3: Documentation and examples
   - Final testing and validation
   - Release preparation

## Success Criteria

1. All existing MCP node implementations removed
2. New MCP service layer working with official SDK
3. LLMAgent and IterativeLLMAgent support MCP natively
4. All examples updated and working
5. Comprehensive documentation available
6. Migration guide helps users transition
7. Tests pass with >90% coverage

## Risks and Mitigations

1. **Risk**: Breaking existing workflows
   - **Mitigation**: Comprehensive migration guide and deprecation period

2. **Risk**: Official SDK limitations
   - **Mitigation**: Implement fallbacks for missing features

3. **Risk**: Performance impact on agents
   - **Mitigation**: Lazy loading of MCP client, connection pooling

4. **Risk**: Complex debugging with embedded MCP
   - **Mitigation**: Comprehensive logging and debug modes
