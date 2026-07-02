# MCP Platform Server: Brief

## Summary

Build ONE unified `kailash-platform` MCP server that gives Claude Code (and any MCP client) full introspection into a Kailash project. The server uses **FastMCP** (`mcp.server.FastMCP`) as the single server primitive, discovers installed frameworks via importlib probing, and exposes namespace-prefixed tools (`dataflow.list_models`, `nexus.list_handlers`, `kaizen.list_agents`, `platform.platform_map`).

## Problem

The Kailash SDK has MCP code scattered across 6 locations, each using different protocols and patterns:

1. `nexus/mcp/server.py` -- Custom JSON protocol (NOT JSON-RPC 2.0). **Delete.**
2. `nexus/mcp_websocket_server.py` -- JSON-RPC bridge for the above. **Delete.**
3. `trust/plane/mcp_server.py` -- FastMCP-based, production quality. **Keep as reference model.**
4. `kailash/api/mcp_integration.py` -- Tool registry. **Refactor** to feed FastMCP.
5. `kailash/channels/mcp_channel.py` -- Nexus channel. **Refactor** as thin FastMCP wrapper.
6. `kaizen_agents/delegate/mcp.py` -- stdio JSON-RPC client. **Keep** (this is a client, not a server).

Multiple servers force MCP clients to configure 4-5 separate entries. MCP clients like Claude Code have no native aggregation. One server with namespace-prefixed tools is strictly better.

## Solution

### Architecture

```
kailash-platform MCP server starts
  -> Checks which frameworks are importable
  -> For each installed framework, imports its contributor module
  -> Each contributor registers tools with the FastMCP instance
  -> Server starts (stdio for Claude Code, HTTP/SSE for web tools)
```

### Contributor Plugin System

```python
FRAMEWORK_CONTRIBUTORS = [
    ("kailash.mcp.contrib.core", "core"),           # always available
    ("kailash.mcp.contrib.platform", "platform"),    # always available
    ("kailash.mcp.contrib.dataflow", "dataflow"),    # requires kailash-dataflow
    ("kailash.mcp.contrib.nexus", "nexus"),          # requires kailash-nexus
    ("kailash.mcp.contrib.kaizen", "kaizen"),        # requires kailash-kaizen
    ("kailash.mcp.contrib.trust", "trust"),          # requires kailash[trust]
    ("kailash.mcp.contrib.pact", "pact"),            # requires kailash-pact
]

for module_path, namespace in FRAMEWORK_CONTRIBUTORS:
    try:
        mod = importlib.import_module(module_path)
        mod.register_tools(mcp_server, project_root)
    except ImportError:
        logger.info("Framework %s not installed, skipping", namespace)
```

Each contributor implements exactly one function: `register_tools(server: FastMCP, project_root: Path) -> None`.

If only DataFlow is installed, only `dataflow.*` tools appear. The server gracefully degrades.

### Transport

- **stdio** (primary, for Claude Code): `kailash-mcp --project-root .`
- **HTTP/SSE** (web tools, remote access): `kailash-mcp --transport sse --port 8900`
- **WebSocket**: legacy compat only via Nexus. Not recommended for new integrations.

Claude Code configuration:
```json
{
  "mcpServers": {
    "kailash": {
      "command": "kailash-mcp",
      "args": ["--project-root", "."]
    }
  }
}
```

### Security Tiers

| Tier | Category | Authorization | Default |
|------|----------|---------------|---------|
| 1 | Introspection (list_models, describe_agent) | None required | Enabled |
| 2 | Scaffold (generate code, returned as string) | None required | Enabled |
| 3 | Validation (import+analyze project code) | `KAILASH_MCP_ENABLE_VALIDATION=false` to disable | Enabled |
| 4 | Execution (test_handler, test_agent -- makes HTTP/LLM calls) | `KAILASH_MCP_ENABLE_EXECUTION=true` required | Disabled |

Tier 4 tools integrate with Trust Plane (if `kailash[trust]` installed) and PACT governance (if `kailash-pact` installed) for authorization checks.

### Ships As

- Package: `kailash[mcp]` optional install (dependency: `mcp[cli]>=1.23.0,<2.0`, already in pyproject.toml)
- Entry point: `kailash-mcp` console script in pyproject.toml
- Module: `src/kailash/mcp/` with `server.py`, `contrib/` directory

### Tool Categories

**Introspection** (Tier 1): `dataflow.list_models`, `dataflow.describe_model`, `dataflow.query_schema`, `nexus.list_handlers`, `nexus.list_channels`, `nexus.list_events`, `kaizen.list_agents`, `kaizen.describe_agent`, `core.list_node_types`, `core.describe_node`, `platform.platform_map`, `trust.trust_status`, `pact.org_tree`

**Scaffold** (Tier 2): `nexus.scaffold_handler`, `kaizen.scaffold_agent`, `dataflow.scaffold_model`

**Validation** (Tier 3): `dataflow.validate_model`, `nexus.validate_handler`, `core.validate_workflow`

**Test Generation** (Tier 2): `dataflow.generate_tests`, `nexus.generate_tests`, `kaizen.generate_tests`, `core.generate_test_data`

**Execution** (Tier 4): `nexus.test_handler`, `kaizen.test_agent`

### MCP Resources

Resources for data that changes infrequently and benefits from subscriptions:
- `kailash://models` -- list of all DataFlow models
- `kailash://models/{model_name}` -- schema for a specific model
- `kailash://handlers` -- list of all Nexus handlers
- `kailash://agents` -- list of all Kaizen agents
- `kailash://platform-map` -- full cross-framework graph
- `kailash://node-types` -- available Core SDK node types
- `kailash://trust/envelope` -- current constraint envelope

### MCP Prompts

Reusable prompt templates combining documentation with live introspection:
- `kailash://prompts/new-model` -- creating a new DataFlow model
- `kailash://prompts/new-handler` -- creating a new Nexus handler
- `kailash://prompts/new-agent` -- creating a new Kaizen agent

## Key Reference: TrustPlane MCP Server

The TrustPlane MCP server at `src/kailash/trust/plane/mcp_server.py` is the quality model. It demonstrates: FastMCP usage, thread-safe caching with double-checked locking, file-watching for config changes, standalone CLI entry point (`trustplane-mcp`). Follow this pattern.

## Key Reference: Kaizen McpClient

The Kaizen MCP client at `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` is the test harness for integration tests. It manages MCP server subprocesses, performs the initialize handshake, discovers tools via `tools/list`, and executes via `tools/call`. Use it for all integration/E2E tests.

## Success Criteria

- `kailash-mcp --project-root .` starts and responds to `tools/list` with namespace-prefixed tools
- Only installed frameworks contribute tools (graceful degradation)
- `platform.platform_map()` returns a single-call cross-framework graph of the project
- 6 old MCP implementations reduced to 1 FastMCP-based server + 1 Kaizen client
- All scaffold tools return valid Python code (parseable by `ast.parse`)
- Integration tests use `McpClient` as the test harness
- Security tiers enforced (Tier 4 tools absent without env var)

## Implementation Order

1. **TSG-500**: Server skeleton (FastMCP, contributor plugin, consolidation)
2. **TSG-501**: DataFlow contributor (list_models, describe_model, query_schema) -- parallel with 502, 503
3. **TSG-502**: Nexus contributor (list_handlers, list_channels, scaffold_handler) -- parallel with 501, 503
4. **TSG-503**: Kaizen contributor (list_agents, describe_agent, scaffold_agent) -- parallel with 501, 502
5. **TSG-504**: platform_map() (depends on 501+502+503)
6. **TSG-505**: Validation tools (subprocess isolation)
7. **TSG-506**: Test generation tools
8. **TSG-507**: Full integration and E2E test suite
