---
name: mcp-platform-overview
description: "Kailash MCP platform server architecture — FastMCP, contributor pattern, framework registration, transport modes, platform_map. Use when asking 'kailash-mcp', 'platform server', 'mcp architecture', 'contributor pattern', or 'platform map'."
---

# MCP Platform Server Architecture

The `kailash-mcp` platform server is a unified FastMCP server that gives MCP clients (Claude Code, Cursor, etc.) full introspection into a Kailash project through a single connection.

> **Skill Metadata**
> Category: `mcp`
> Priority: `HIGH`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-contributor-pattern`](mcp-contributor-pattern.md), [`mcp-tool-catalog`](mcp-tool-catalog.md), [`mcp-security-tiers`](mcp-security-tiers.md)
> Related Subagents: `mcp-platform-specialist` (platform server implementation, troubleshooting)

## How It Works

The platform server discovers which Kailash frameworks are installed and registers namespace-prefixed tools for each. One MCP server entry, full project visibility.

```
kailash-mcp (FastMCP)
    ├── core.*       ← Always available (node types, SDK version, workflow validation)
    ├── platform.*   ← Always available (platform_map, project_info)
    ├── dataflow.*   ← If kailash-dataflow installed (models, schemas, scaffolding)
    ├── nexus.*      ← If kailash-nexus installed (handlers, channels, scaffolding)
    ├── kaizen.*     ← If kailash-kaizen installed (agents, signatures, scaffolding)
    ├── trust.*      ← Part of core (trust plane status)
    └── pact.*       ← If kailash-pact installed (org tree, governance)
```

**Why a single server?** MCP clients configure one entry and get everything. No per-framework MCP servers to manage, no port conflicts, no tool namespace collisions.

## Framework Contributor System

Each framework implements a `register_tools(server, project_root, namespace)` function in `kailash.mcp.contrib.<framework>`. The platform server imports each contributor module, calls `register_tools`, and validates that tools use the correct namespace prefix.

Contributors that fail to import (framework not installed) are skipped gracefully -- the server starts with whatever frameworks are available.

```python
# kailash/mcp/platform_server.py

FRAMEWORK_CONTRIBUTORS = [
    ("kailash.mcp.contrib.core", "core"),
    ("kailash.mcp.contrib.platform", "platform"),
    ("kailash.mcp.contrib.dataflow", "dataflow"),
    ("kailash.mcp.contrib.nexus", "nexus"),
    ("kailash.mcp.contrib.kaizen", "kaizen"),
    ("kailash.mcp.contrib.trust", "trust"),
    ("kailash.mcp.contrib.pact", "pact"),
]

server = FastMCP("kailash-platform", instructions="...")

for module_path, namespace in FRAMEWORK_CONTRIBUTORS:
    try:
        mod = importlib.import_module(module_path)
        mod.register_tools(server, project_root, namespace)
    except ImportError:
        logger.info("Framework %s not installed, skipping", namespace)
```

**Why namespace prefixes?** Each tool name starts with `{namespace}.` (e.g., `dataflow.list_models`, `kaizen.list_agents`). This prevents collisions and makes tool purpose immediately clear to the MCP client.

## Transport Modes

### stdio (Default -- Local Development with Claude Code)

```bash
kailash-mcp --project-root /path/to/project
```

Communicates over stdin/stdout. Claude Code launches the server as a subprocess.

### SSE (Remote -- Shared Servers)

```bash
kailash-mcp --transport sse --port 8900 --project-root /path/to/project
```

Server-Sent Events transport for remote MCP clients. Use when the server runs on a different machine or as a shared service.

### Project Root Resolution

The server determines which project to introspect using this priority:

1. `--project-root` CLI argument
2. `KAILASH_PROJECT_ROOT` environment variable
3. Current working directory

## Discovery Method: AST Static Analysis

All contributors use AST-based static analysis to discover project artifacts. The server parses Python source files without importing them, which means:

- No runtime side effects during scanning
- Works even if dependencies are not installed in the server's environment
- Cannot detect dynamically registered models/handlers/agents
- Scans only `project_root`, not installed packages

**Why AST instead of runtime introspection?** Importing user code during MCP server startup could trigger database connections, API calls, or other side effects. AST scanning is safe, fast, and deterministic.

## platform_map() -- The Single-Call Overview

The `platform.platform_map` tool aggregates discovery from all contributors into one response:

```json
{
  "project": {
    "name": "my-app",
    "root": "/path/to/project",
    "kailash_version": "2.5.0"
  },
  "frameworks": {
    "core": { "installed": true, "version": "2.5.0" },
    "dataflow": { "installed": true, "version": "1.3.0" },
    "nexus": { "installed": true, "version": "0.8.0" },
    "kaizen": { "installed": false }
  },
  "models": [{ "name": "User", "fields_count": 5, "file": "models/user.py" }],
  "handlers": [
    {
      "name": "create_user",
      "method": "POST",
      "path": "/api/users",
      "file": "handlers/users.py"
    }
  ],
  "agents": [],
  "connections": [
    {
      "from": "User",
      "to": "create_user",
      "type": "model_to_handler",
      "via": "CreateUser"
    }
  ],
  "trust": { "installed": true, "trust_dir_exists": true },
  "scan_metadata": {
    "frameworks_scanned": ["dataflow", "nexus"],
    "total_files_scanned": 42,
    "scan_duration_ms": 150
  }
}
```

Connections are detected via deterministic naming conventions (e.g., a handler referencing `CreateUser` connects to the `User` model).

## Key Architecture Decisions

| Decision                  | Rationale                                                                  |
| ------------------------- | -------------------------------------------------------------------------- |
| FastMCP as base           | Official MCP Python SDK, maintained by Anthropic, handles protocol details |
| Contributor plugin system | Frameworks register independently -- no monolithic server file             |
| Namespace-prefixed tools  | Prevents collisions, self-documenting tool names                           |
| AST-based scanning        | No runtime side effects, no import-time errors                             |
| Graceful degradation      | Missing frameworks skip silently, server starts with what's available      |
| Tiered security           | Read-only by default, write/execute opt-in via env vars                    |

## Related Files

- **[mcp-contributor-pattern](mcp-contributor-pattern.md)** -- How to write a new contributor
- **[mcp-tool-catalog](mcp-tool-catalog.md)** -- Complete list of all registered tools
- **[mcp-security-tiers](mcp-security-tiers.md)** -- Security tier system
- **[mcp-claude-code-config](mcp-claude-code-config.md)** -- Claude Code setup
- **[mcp-platform-map](mcp-platform-map.md)** -- platform_map() deep dive

## When to Escalate to Subagent

Use `mcp-platform-specialist` when:

- Troubleshooting contributor registration failures
- Implementing custom transport configurations
- Diagnosing namespace prefix validation warnings
- Setting up SSE transport behind a reverse proxy

<!-- Trigger Keywords: kailash-mcp, platform server, mcp architecture, contributor pattern, platform map, mcp overview, fastmcp, namespace tools, mcp introspection -->
