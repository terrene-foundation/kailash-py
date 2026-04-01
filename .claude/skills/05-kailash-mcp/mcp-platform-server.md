---
name: mcp-platform-server
description: "Unified kailash-platform MCP server with contributor plugin system and security tiers. Use when asking about 'platform server', 'kailash-mcp', 'MCP contributor', 'security tiers', 'ContributorProtocol', 'register_tools', 'AST scanning', or 'namespace-prefixed tools'."
---

# MCP Platform Server

Unified `kailash-mcp` command that exposes namespace-prefixed tools for every installed Kailash framework via a contributor plugin system.

## Quick Reference

| Feature              | Details                                                                     |
| -------------------- | --------------------------------------------------------------------------- |
| Command              | `kailash-mcp` (stdio default)                                               |
| Server name          | `kailash-platform`                                                          |
| Contributors         | 7 (core, platform, dataflow, nexus, kaizen, trust, pact)                    |
| Tool naming          | `{namespace}.{tool_name}` (e.g., `core.list_nodes`, `dataflow.list_models`) |
| Discovery            | AST-based source scanning (not runtime registry)                            |
| Graceful degradation | Missing frameworks are skipped                                              |

## Usage

### Command Line

```bash
# stdio (default, for Claude Desktop / Claude Code)
kailash-mcp

# SSE transport
kailash-mcp --transport sse --port 8900

# Custom project root
kailash-mcp --project-root /path/to/project
```

### Claude Code Settings

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

## Contributor System

### Architecture

```
create_platform_server(project_root)
    |
    |--> import kailash.mcp.contrib.core     -> core.* tools
    |--> import kailash.mcp.contrib.platform  -> platform.* tools
    |--> import kailash.mcp.contrib.dataflow  -> dataflow.* tools
    |--> import kailash.mcp.contrib.nexus     -> nexus.* tools
    |--> import kailash.mcp.contrib.kaizen    -> kaizen.* tools
    |--> import kailash.mcp.contrib.trust     -> trust.* tools
    |--> import kailash.mcp.contrib.pact      -> pact.* tools
```

### Contributor Protocol

Every contributor module implements `register_tools()`:

```python
def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
    """Register framework-specific MCP tools on the shared server.

    Rules:
    - All tool names MUST start with '{namespace}.' prefix
    - MUST be synchronous and non-blocking
    - MUST NOT perform network calls during registration
    """
```

### Namespace Validation

The server validates that each contributor only registers tools within its namespace. Tools outside the namespace produce a warning at startup.

## Security Tiers

Tools are gated by security tiers controlled via environment variables:

| Tier | Name          | Default   | Env Var                                          | Use Case                                         |
| ---- | ------------- | --------- | ------------------------------------------------ | ------------------------------------------------ |
| 1    | INTROSPECTION | Always on | --                                               | Read-only discovery (list models, nodes, agents) |
| 2    | SCAFFOLD      | Always on | --                                               | Code generation helpers                          |
| 3    | VALIDATION    | Enabled   | `KAILASH_MCP_ENABLE_VALIDATION=false` to disable | Lint, validate, test runners                     |
| 4    | EXECUTION     | Disabled  | `KAILASH_MCP_ENABLE_EXECUTION=true` to enable    | Run workflows, execute code                      |

```python
from kailash.mcp.contrib import SecurityTier, is_tier_enabled

if is_tier_enabled(SecurityTier.EXECUTION):
    # Register execution tools (Tier 4)
    @server.tool(f"{namespace}.run_workflow")
    async def run_workflow(workflow_name: str) -> dict:
        # Runs in subprocess isolation
        ...
```

## AST-Based Discovery

Contributors discover project resources by scanning source code with Python's `ast` module, NOT by importing or executing modules. This means:

- **Safe**: No side effects from scanning
- **Fast**: No runtime initialization needed
- **scan_info metadata**: Each contributor returns scan statistics

```python
# Example scan_info from kaizen contributor
{
    "scan_method": "ast",
    "files_scanned": 42,
    "agents_found": 7,
    "limitations": ["Cannot detect dynamically registered agents"],
}
```

## Example Tools by Namespace

| Namespace  | Example Tools                                                         |
| ---------- | --------------------------------------------------------------------- |
| `core`     | `core.list_nodes`, `core.show_node`, `core.list_workflows`            |
| `platform` | `platform.project_info`, `platform.framework_status`                  |
| `dataflow` | `dataflow.list_models`, `dataflow.show_model`, `dataflow.show_schema` |
| `nexus`    | `nexus.list_handlers`, `nexus.show_handler`, `nexus.list_routes`      |
| `kaizen`   | `kaizen.list_agents`, `kaizen.show_agent`, `kaizen.agent_graph`       |
| `trust`    | `trust.list_delegates`, `trust.show_policy`                           |
| `pact`     | `pact.list_envelopes`, `pact.show_org`                                |

## Tier 4: Subprocess Isolation

Execution tools (Tier 4) run in isolated subprocesses for safety:

- Separate Python process
- Timeout enforcement
- Output capture
- No access to the MCP server's memory space

## Source Code

- `src/kailash/mcp/platform_server.py` -- Server factory, contributor loading, namespace validation
- `src/kailash/mcp/contrib/__init__.py` -- SecurityTier, is_tier_enabled, protocol definition
- `src/kailash/mcp/contrib/core.py` -- Core SDK contributor
- `src/kailash/mcp/contrib/dataflow.py` -- DataFlow contributor
- `src/kailash/mcp/contrib/nexus.py` -- Nexus contributor
- `src/kailash/mcp/contrib/kaizen.py` -- Kaizen contributor (AST agent scanning)
- `src/kailash/mcp/contrib/trust.py` -- Trust contributor
- `src/kailash/mcp/contrib/pact.py` -- PACT contributor
- `src/kailash/mcp/contrib/platform.py` -- Platform contributor
- `tests/unit/mcp/test_platform_server.py` -- Unit tests
