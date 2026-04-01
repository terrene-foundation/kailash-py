---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T00:00:00Z
author: agent
session_turn: 1
project: mcp-platform-server
topic: MCP server must use AST-based static introspection, not runtime registries
phase: analyze
tags: [mcp, introspection, ast, architecture]
---

# DISCOVERY: Introspection Tools Must Use AST-Based Source Scanning

## Background

The brief and architecture document describe introspection tools (e.g., `dataflow.list_models()`) as querying framework registries like `DataFlow._models` or `NodeRegistry.list_nodes()`. During the /analyze phase, deep research into how these registries work revealed a fundamental constraint.

## Finding

The MCP platform server runs as a standalone subprocess (`kailash-mcp --project-root .`), not inside the project's application process. Framework registries are populated at APPLICATION runtime:

- **DataFlow**: Models register when `@db.model` decorates a class AND a `DataFlow(url)` instance is created. No instance, no registry.
- **Nexus**: Handlers register when `app.register(handler)` is called. No Nexus app, no registry.
- **Kaizen**: No central project-level registry exists at all. `AgentRegistry` (trust module) and `LocalRegistry` (deploy module) are runtime/file-based.
- **Core SDK**: `NodeRegistry` IS populated by import alone (decorator triggers registration). This is the one exception.

The MCP server process has no DataFlow database URL, no Nexus app, no running application. It has only the `project_root` directory and the installed packages.

## Impact

This fundamentally changes the Tier 1 introspection strategy from runtime registry queries to static analysis:

- **Primary (Tier 1)**: AST-based source scanning of `project_root`
  - Scan for `@db.model` decorated classes
  - Scan for `BaseAgent` subclasses
  - Scan for handler registrations
  - Extract field types, signatures, tool lists from AST
- **Secondary (Tier 3/4)**: Subprocess-based code import for validation and execution

The architecture document's example of `db._models` access is not viable for the introspection server. The implementation must build AST scanners for each framework's patterns.

## Positive Side Effect

AST-based scanning is actually more robust for Claude Code's use case:

- Works even if the project has syntax errors in other files
- Doesn't trigger side effects (database connections, API calls)
- Faster than importing the entire project
- Works without a configured database URL

## Effort Impact

Each framework contributor needs an AST scanner (~100 lines each). The `core` contributor is the exception -- it can use `NodeRegistry` directly since nodes register on import. Total additional effort: ~300 lines of AST scanning code across 3 contributors.

## For Discussion

1. The DataFlow `@db.model` decorator has a deterministic generated-node naming pattern (`Create{Name}`, `Read{Name}`, etc.). If this pattern ever changes, the AST scanner would return incorrect generated node names. Should the scanner import DataFlow's naming function directly, or is the pattern stable enough to hardcode?

2. If the project has 500+ Python files, AST scanning at startup could take several seconds. Should scanning be lazy (on first tool call) or eager (at startup)? The TrustPlane reference model uses lazy loading with caching.

3. The Core SDK `NodeRegistry` works via import because of the `@register_node` decorator. Could DataFlow and Kaizen adopt a similar pattern, making their registries available without a full application instance?
