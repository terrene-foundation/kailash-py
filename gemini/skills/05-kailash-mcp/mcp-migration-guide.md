---
name: mcp-migration-guide
description: "Migrate from old MCP implementations (MCPServer, MCPServerBase, MCPWebSocketServer) to the unified kailash-mcp platform server. Use when asking 'mcp migration', 'old mcp server', 'MCPServer to platform', 'migrate mcp', or 'mcp upgrade'."
---

# MCP Migration Guide

How to migrate from older MCP server implementations to the unified kailash-mcp FastMCP platform server. Covers the three legacy patterns and their platform server equivalents.

> **Skill Metadata**
> Category: `mcp`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-contributor-pattern`](mcp-contributor-pattern.md), [`mcp-claude-code-config`](mcp-claude-code-config.md)
> Related Subagents: `mcp-specialist` (migration planning, complex server conversions)

## Why Migrate?

The legacy MCP implementations (`MCPServer`, `MCPServerBase`, custom WebSocket servers) are per-project, per-framework servers. Each project needed its own MCP server code that manually registered tools. The platform server replaces all of these with a zero-config server that auto-discovers project artifacts.

| Legacy Approach                     | Platform Server                 |
| ----------------------------------- | ------------------------------- |
| Write custom MCP server per project | `kailash-mcp --project-root .`  |
| Manually register each tool         | Auto-discovers via AST scanning |
| One server per framework            | One server, all frameworks      |
| Custom transport code               | Built-in stdio + SSE            |
| No security tiers                   | 4-tier security model           |
| No cross-framework connections      | Automatic connection detection  |

**Why not keep both?** Running legacy MCP servers alongside the platform server creates port conflicts, tool namespace collisions, and duplicate tool registrations that confuse MCP clients.

## Migration Path 1: MCPServerBase Subclass

### Before (Legacy)

```python
# my_mcp_server.py
from kailash_mcp.server import MCPServerBase


class MyProjectServer(MCPServerBase):
    def setup(self):
        @self.add_tool()
        def list_users() -> list:
            """List all users in the database."""
            return db.query_users()

        @self.add_tool()
        def create_user(name: str, email: str) -> dict:
            """Create a new user."""
            return db.create_user(name=name, email=email)


server = MyProjectServer("my-project")
server.start()
```

### After (Platform Server)

No custom server code needed. The platform server auto-discovers DataFlow models and Nexus handlers.

```bash
# Just run the platform server
kailash-mcp --project-root .
```

If you need custom tools that are not covered by auto-discovery, write a contributor module:

```python
# kailash/mcp/contrib/myproject.py
from pathlib import Path
from typing import Any


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register project-specific tools."""

    @server.tool(name=f"{namespace}.list_users")
    async def list_users() -> dict:
        """List all users in the database."""
        # Use AST scanning or file-based discovery instead of runtime DB calls
        return {"users": [], "scan_metadata": {"method": "static"}}
```

**Key difference**: Platform server tools use AST-based discovery by default. If you need runtime database access, that belongs in a Tier 4 execution tool with subprocess isolation.

### Migration Checklist

- [ ] Identify all tools registered in the `setup()` method
- [ ] Classify each tool: is it discovery (Tier 1), scaffolding (Tier 2), validation (Tier 3), or execution (Tier 4)?
- [ ] For Tier 1 tools: check if `platform.platform_map`, `dataflow.list_models`, `nexus.list_handlers`, or `kaizen.list_agents` already provides the same data
- [ ] For tools not covered by existing contributors: write a custom contributor module
- [ ] Remove the legacy server file
- [ ] Update Claude Code `mcpServers` config to use `kailash-mcp`

## Migration Path 2: MCPServer (Production Server)

### Before (Legacy)

```python
# server.py
from kailash_mcp import MCPServer
from kailash_mcp.auth import APIKeyAuth

auth = APIKeyAuth({"user1": "secret-key"})
server = MCPServer(
    "my-server",
    auth_provider=auth,
    enable_cache=True,
    enable_metrics=True,
    enable_http_transport=True,
    rate_limit_config={"requests_per_minute": 100},
)


@server.tool(cache_key="search", cache_ttl=600)
def search(query: str) -> dict:
    """Search the knowledge base."""
    return {"results": do_search(query)}


server.run()
```

### After (Platform Server)

```bash
kailash-mcp --transport sse --port 8900 --project-root .
```

**What about authentication, caching, and rate limiting?** The platform server focuses on project introspection, not production API serving. If you need authenticated, cached, rate-limited MCP tools for production, keep the `MCPServer` for that use case and use the platform server for development introspection.

| Use Case                                | Server                        |
| --------------------------------------- | ----------------------------- |
| Development introspection (Claude Code) | `kailash-mcp` platform server |
| Production API with auth/cache/metrics  | `MCPServer` (keep legacy)     |

**Why this split?** The platform server is designed for safe, read-only project discovery. Production servers need authentication, caching, and rate limiting that are orthogonal to discovery. Combining them creates a server that is too complex for development and too discovery-focused for production.

### Migration Checklist

- [ ] Separate discovery tools (list, describe, query) from production tools (search, execute, mutate)
- [ ] Move discovery tools to `kailash-mcp` platform server
- [ ] Keep production tools in `MCPServer` if they need auth/cache/rate-limiting
- [ ] Update Claude Code config to point to `kailash-mcp` for development
- [ ] Keep production MCP config pointing to `MCPServer` for deployed environments

## Migration Path 3: Custom WebSocket/Channel Servers

### Before (Legacy)

```python
# Custom MCP channel in Nexus
from kailash.channels.mcp_channel import MCPChannel

channel = MCPChannel(
    name="my-mcp",
    workflows={"summarize": summarize_workflow},
)
nexus.add_channel(channel)
```

### After (Platform Server)

The platform server replaces standalone MCP channel servers for introspection. Nexus MCP channels still serve a different purpose -- they expose workflows as MCP tools at runtime. The platform server discovers what Nexus has configured.

```bash
# Platform server discovers Nexus handlers automatically
kailash-mcp --project-root .
# nexus.list_handlers will show the registered handlers
```

**What about runtime workflow execution via MCP?** That stays in Nexus. The platform server does not execute workflows -- it discovers them. If you need MCP clients to execute workflows, keep the Nexus MCP channel.

| Concern           | Platform Server             | Nexus MCP Channel        |
| ----------------- | --------------------------- | ------------------------ |
| Discover handlers | Yes (`nexus.list_handlers`) | No                       |
| Execute workflows | No                          | Yes                      |
| Auto-discovery    | Yes (AST scan)              | No (manual registration) |
| Security tiers    | Yes (T1-T4)                 | Custom auth              |

### Migration Checklist

- [ ] Identify which MCP tools are for discovery vs execution
- [ ] Move discovery to `kailash-mcp` platform server (automatic)
- [ ] Keep workflow execution in Nexus MCP channel
- [ ] Update Claude Code config for development introspection

## Breaking Changes

### Tool Names

Legacy servers used unnamespaced tool names. The platform server uses namespace prefixes.

| Legacy           | Platform Server           |
| ---------------- | ------------------------- |
| `list_users`     | `dataflow.list_models`    |
| `create_user`    | `dataflow.scaffold_model` |
| `search`         | (custom contributor)      |
| `list_endpoints` | `nexus.list_handlers`     |

**Impact**: Any MCP client code that references tools by name must be updated. Claude Code handles this automatically -- it reads the tool list from the server.

### Transport Configuration

Legacy servers often used custom transport code. The platform server supports stdio and SSE natively.

| Legacy                        | Platform Server               |
| ----------------------------- | ----------------------------- |
| Custom WebSocket server       | `--transport sse`             |
| Custom HTTP endpoints         | `--transport sse`             |
| stdio with process management | `--transport stdio` (default) |

### Authentication

The platform server does not include built-in authentication. For authenticated remote access, place the SSE server behind a reverse proxy with authentication.

| Legacy       | Platform Server    |
| ------------ | ------------------ |
| `APIKeyAuth` | Reverse proxy auth |
| `JWTAuth`    | Reverse proxy auth |
| `OAuth2`     | Reverse proxy auth |

**Why no built-in auth?** The platform server's primary use case is local development via stdio, where authentication adds no value. For remote SSE deployments, reverse proxy authentication is more robust and maintainable than in-process auth.

## Common Migration Questions

### Can I run both servers during migration?

Yes. Use different ports or transports. Configure Claude Code to use the platform server, and keep the legacy server for any production MCP clients.

### Do I lose my custom tools?

Only if they are discovery tools already covered by the platform server's contributors. Custom business logic tools should either become a contributor module or stay in the legacy server.

### What about tests that use the legacy MCP server?

Update test fixtures to use `create_platform_server()`:

```python
# Before
from kailash_mcp import MCPServer
server = MCPServer("test")

# After
from kailash.mcp.platform_server import create_platform_server
server = create_platform_server(project_root=tmp_path)
```

### What if I need runtime database access in MCP tools?

Use a Tier 4 execution tool with subprocess isolation, or keep the legacy `MCPServer` for that specific use case. The platform server's philosophy is AST-based discovery without runtime side effects.

## Quick Tips

- Start by running `kailash-mcp --project-root .` alongside your legacy server to compare tool coverage
- Most discovery tools (list, describe, query) are already covered by platform contributors
- Custom business logic tools need a contributor module or stay in the legacy server
- Update Claude Code config first -- that is the highest-value migration step
- Production MCP servers with auth/cache can coexist with the platform server indefinitely

## When to Escalate to Subagent

Use `mcp-specialist` when:

- Migrating a complex `MCPServerBase` subclass with many custom tools
- Converting WebSocket-based MCP servers to SSE
- Writing custom contributor modules for project-specific discovery
- Planning a phased migration for a production MCP deployment

<!-- Trigger Keywords: mcp migration, old mcp server, MCPServer to platform, migrate mcp, mcp upgrade, MCPServerBase, legacy mcp, mcp_server migration -->
