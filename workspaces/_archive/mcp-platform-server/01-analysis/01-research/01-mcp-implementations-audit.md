# MCP Implementations Audit

## Summary

Six MCP-related implementations exist in the codebase. All claimed file paths verified. One critical discovery: `src/kailash/mcp/` already contains a Rust-backed `McpApplication` wrapping `McpServer` from `kailash._kailash`. The brief's plan to place the new FastMCP platform server at `src/kailash/mcp/server.py` directly conflicts with this existing module.

---

## Implementation 1: Nexus MCP Server (Custom JSON Protocol)

**Path**: `packages/kailash-nexus/src/nexus/mcp/server.py`
**Verified**: YES
**Lines**: 434
**Protocol**: Custom JSON — NOT JSON-RPC 2.0
**Quality**: Low

### Assessment

- `MCPServer` class registers `Workflow` objects as MCP tools over WebSocket
- Custom message format: `{"type": "list_tools"}`, `{"type": "call_tool", "name": "...", "arguments": {...}}`
- NOT JSON-RPC 2.0 compliant (no `jsonrpc: "2.0"`, no `id`, no `method`)
- Includes `SimpleMCPClient` (WebSocket test client)
- Uses `WebSocketServerTransport` / `WebSocketClientTransport` from `transport.py`
- Shared runtime pattern (M3-001) properly implemented
- Resource cleanup with `close()` and `__del__` with `ResourceWarning`

### Supporting Files

- `packages/kailash-nexus/src/nexus/mcp/transport.py` (419 lines) — WebSocket server/client transport, abstract `MCPTransport` base class
- `packages/kailash-nexus/src/nexus/mcp/__init__.py` — package init

### Action: DELETE

Non-standard protocol. No MCP client (Claude Code, Kaizen McpClient) speaks this protocol. The WebSocket transport layer has no reuse value — the new server uses FastMCP's built-in stdio/SSE transports.

### Migration Risk

- Tests in `tests/integration/mcp_server/` likely reference `MCPServer` and `SimpleMCPClient`
- Nexus documentation may reference these classes
- Check for imports of `nexus.mcp.server` across codebase

---

## Implementation 2: MCP WebSocket Server (JSON-RPC Bridge)

**Path**: `packages/kailash-nexus/src/nexus/mcp_websocket_server.py`
**Verified**: YES
**Lines**: 360
**Protocol**: JSON-RPC 2.0 over WebSocket
**Quality**: Medium

### Assessment

- `MCPWebSocketServer` wraps Implementation #1 to add JSON-RPC 2.0 compliance
- Implements `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`
- Bridges between `_tools` (Core SDK) and `_workflows` (simple server) dicts via `hasattr` checks
- Proper JSON-RPC error codes (-32700, -32601, -32602, -32603)
- Uses `websockets 14.0+` API (`ServerConnection`)
- Shared runtime pattern (M3-001) properly implemented

### Action: DELETE

Exists only because #1 isn't spec-compliant. Both are superseded by FastMCP. No reuse value.

### Migration Risk

- Same test migration concerns as #1
- May have integration tests that need rewriting

---

## Implementation 3: TrustPlane MCP Server (FastMCP Reference)

**Path**: `src/kailash/trust/plane/mcp_server.py`
**Verified**: YES
**Lines**: 302
**Protocol**: FastMCP (official MCP Python SDK)
**Quality**: HIGH — This is the reference model

### Assessment

- Uses `mcp.server.FastMCP` (the official Python MCP SDK)
- 5 tools: `trust_check`, `trust_record`, `trust_envelope`, `trust_status`, `trust_verify`
- Thread-safe caching with double-checked locking (`_project_lock`)
- File-watching: reloads when `manifest.json` mtime changes
- Standalone CLI entry point: `trustplane-mcp` (registered in pyproject.toml)
- Test helpers: `_set_project()`, `_reset_project()`, `_get_manifest_mtime()`
- Clean `@mcp.tool()` decorator usage with descriptions
- Proper Apache 2.0 / Terrene Foundation header

### Patterns to Replicate

1. `FastMCP("ServerName", instructions="...")` with clear instructions
2. Module-level `mcp` instance (not class-based)
3. Double-checked locking for cached state
4. File-watching via `stat().st_mtime` comparison
5. `argparse` CLI with `mcp.run()` entry point
6. Test injection via `_set_project()` / `_reset_project()`

### Action: KEEP as-is

This remains an independent server for trust-specific operations. The platform server will expose `trust.*` tools via a separate contributor that calls into the same underlying `TrustProject` API. The TrustPlane MCP server continues to run standalone for trust-only use cases.

---

## Implementation 4: Core SDK MCP Integration (Tool Registry)

**Path**: `src/kailash/api/mcp_integration.py`
**Verified**: YES
**Lines**: 528
**Protocol**: In-process registry (not a server)
**Quality**: Medium

### Assessment

- `MCPIntegration` — in-process tool/resource registry using Pydantic models
- `MCPTool` and `MCPResource` Pydantic models
- `MCPToolNode` — AsyncNode that executes MCP tools within workflows
- Safe math evaluator (`_safe_math_eval`) using AST parsing
- `create_example_mcp_server()` creates demo with fake data (simulated web_search)
- No transport layer — purely in-process
- Uses `asyncio.get_event_loop()` (deprecated pattern)

### Issues

- `create_example_mcp_server()` returns simulated/fake data — technically a stub violation
- `MCPToolNode.run()` has duplicated parameter mapping logic (sync and async versions)
- Uses `asyncio.get_event_loop()` instead of `asyncio.get_running_loop()`

### Action: REFACTOR

- `MCPIntegration` becomes the internal API feeding FastMCP tool registration
- `MCPToolNode` remains useful (workflow nodes calling MCP tools)
- `create_example_mcp_server()` should be moved to test fixtures or deleted
- Safe math evaluator is useful but unrelated to MCP; consider moving to utils

---

## Implementation 5: MCP Channel (Nexus Channel)

**Path**: `src/kailash/channels/mcp_channel.py`
**Verified**: YES
**Lines**: 711
**Protocol**: Nexus channel wrapping MiddlewareMCPServer
**Quality**: Medium

### Assessment

- `MCPChannel` extends `Channel` base class from Nexus channel system
- Registers default tools: `list_workflows`, `execute_workflow`, `get_workflow_schema`, `channel_status`
- Delegates to `MiddlewareMCPServer` for actual MCP handling
- Lazy import of MCP dependencies with fallback classes
- Uses `MCPPlatformAdapter` for platform-format config translation
- Shared runtime pattern properly implemented
- `_server_loop()` is a sleep loop (`await asyncio.sleep(1)`) — effectively a stub

### Issues

- `_server_loop()` is an `asyncio.sleep(1)` loop — placeholder, not real server loop
- `_handle_get_workflow_schema()` returns stub data: `"schema": {"inputs": "object", "outputs": "object"}`
- Depends on `MiddlewareMCPServer` from `middleware.mcp.enhanced_server` which may be complex

### Action: REFACTOR

- Make thin FastMCP wrapper: channel creates a FastMCP instance, registers its workflows as tools
- The channel's `handle_request()` becomes a proxy to FastMCP
- Default tools (list_workflows, execute_workflow) move to the nexus contributor

---

## Implementation 6: Kaizen MCP Client (stdio JSON-RPC)

**Path**: `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py`
**Verified**: YES
**Lines**: 510
**Protocol**: stdio JSON-RPC 2.0 client
**Quality**: HIGH

### Assessment

- `McpClient` manages MCP server subprocesses
- `McpServerConfig` (frozen dataclass) — server command, args, env
- `McpToolDef` (frozen dataclass) — discovered tool definitions
- Full JSON-RPC 2.0 protocol: `initialize` handshake, `notifications/initialized`, `tools/list`, `tools/call`
- Subprocess management with SIGTERM -> SIGKILL escalation
- Background `_read_stdout()` task with pending future resolution
- EOF handling: fails all pending futures on unexpected server exit
- `register_mcp_tools()` — registers discovered tools into Kaizen ToolRegistry with `mcp_<server>_<tool>` prefix
- `load_mcp_server_configs()` — parses TOML config files

### Action: KEEP as-is

This is a CLIENT, not a server. It is the test harness for integration testing the platform server. No changes needed.

---

## CRITICAL DISCOVERY: Existing `src/kailash/mcp/` Module

**Path**: `src/kailash/mcp/__init__.py` + `src/kailash/mcp/server.py`
**Lines**: 183 + 363
**Content**: Rust-backed MCP types via PyO3

### Assessment

This module already exists and provides:

- `McpServer` — Rust-backed MCP server from `kailash._kailash`
- `McpApplication` — Pythonic decorator wrapper (`@app.tool()`, `@app.resource()`, `@app.prompt()`)
- `ToolDef`, `ToolParam`, `ToolRegistry` — Rust-backed types
- Helper functions: `create_server()`, `create_tool()`, `tool_param()`, `prompt_argument()`
- Auth support: `require_auth()` with API keys and JWT

**Critical**: `McpApplication.run()` raises `RuntimeError` — "standalone MCP transport is not yet available in the Rust binding." The Rust-backed server has no transport yet. It can only be served through Nexus.

### Impact on Plan

The brief's module layout puts the new FastMCP server at `src/kailash/mcp/server.py`. This file already exists (McpApplication). Options:

1. **Rename existing**: Move `McpApplication` to `src/kailash/mcp/application.py`; put platform server at `server.py`
2. **New submodule**: Put platform server at `src/kailash/mcp/platform/server.py`
3. **Different location**: Put platform server at `src/kailash/platform/mcp_server.py`

**Recommendation**: Option 1. The `McpApplication` is Rust-backed and focused on individual server creation. The platform server is the FastMCP-based consolidation server. Rename `server.py` -> `application.py`, update `__init__.py` imports, place platform server at `server.py`. This keeps `kailash-mcp` as the entry point and `from kailash.mcp import McpApplication` still works.

---

## Existing Test Infrastructure

- `tests/integration/mcp_server/` — 18 test files including `test_fastmcp_integration.py`, `test_mcp_comprehensive_integration.py`, stress tests, protocol tests
- `tests/utils/mcp_test_runner.py` — Existing MCP test utilities

---

## Consolidation Summary

| #   | File                          | Current              | Target                   |
| --- | ----------------------------- | -------------------- | ------------------------ |
| 1   | nexus/mcp/server.py           | Custom JSON server   | DELETE                   |
| 2   | nexus/mcp_websocket_server.py | JSON-RPC bridge      | DELETE                   |
| 3   | trust/plane/mcp_server.py     | FastMCP (standalone) | KEEP                     |
| 4   | api/mcp_integration.py        | Tool registry        | REFACTOR                 |
| 5   | channels/mcp_channel.py       | Nexus channel        | REFACTOR                 |
| 6   | kaizen_agents/delegate/mcp.py | stdio client         | KEEP                     |
| 7   | kailash/mcp/server.py         | Rust-backed McpApp   | RENAME to application.py |
