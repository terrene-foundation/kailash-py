---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T00:00:00Z
author: agent
session_turn: 1
project: mcp-platform-server
topic: Existing kailash.mcp module conflicts with platform server placement
phase: analyze
tags: [mcp, module-conflict, blocking, rust-backend]
---

# DISCOVERY: Module Path Conflict with Existing Rust-Backed MCP Module

## Background

The brief for the MCP Platform Server specifies `src/kailash/mcp/server.py` as the location for the new FastMCP-based platform server. During the /analyze phase, a thorough audit of the codebase revealed that this module already exists.

## Finding

`src/kailash/mcp/` is an existing module containing:

- `__init__.py` (183 lines) — Re-exports Rust-backed MCP types (`McpServer`, `ToolDef`, `ToolParam`, `ToolRegistry`) from `kailash._kailash` and provides convenience helpers
- `server.py` (363 lines) — `McpApplication` class, a Flask-like decorator wrapper around the Rust-backed `McpServer`
- `server.pyi` (101 lines) — Type stubs for `McpApplication`

The `McpApplication` wraps a Rust/PyO3 backend and provides `@app.tool()`, `@app.resource()`, `@app.prompt()` decorators. However, `McpApplication.run()` raises `RuntimeError` because the Rust binding does not yet expose a standalone transport. Users are directed to Nexus for serving MCP tools.

## Impact

This is a BLOCKING issue for TSG-500 (server skeleton). The implementation plan assumes the `server.py` file is available for the new platform server. It is not.

## Resolution

Rename `server.py` -> `application.py` and update `__init__.py` to import from the new location. The `McpApplication` re-export in `__init__.py` means external code using `from kailash.mcp import McpApplication` continues to work. The platform server then takes the `platform_server.py` filename.

## For Discussion

1. The Rust-backed `McpServer` has no transport and cannot run standalone. If the platform server (FastMCP-based) succeeds and becomes the recommended way to serve MCP tools, what is the future of the Rust-backed `McpApplication`? Does it become deprecated, or does it gain a Rust transport eventually?

2. If we had discovered this conflict during implementation rather than analysis, it would have caused a refactoring detour mid-session. What other module naming assumptions in the brief should be verified before /todos approval?

3. The coexistence of two MCP server primitives (Rust `McpServer` and Python `FastMCP`) could confuse SDK users. Should documentation explicitly guide users on when to use which?
