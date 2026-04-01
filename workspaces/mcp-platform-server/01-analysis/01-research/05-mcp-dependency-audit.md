# MCP Dependency Audit

## FastMCP Availability

### pyproject.toml Dependency

```toml
# Line 64 of pyproject.toml
"mcp[cli]>=1.23.0,<2.0",
```

The `mcp` package is already a standard dependency of `kailash` (not an optional extra). This means `mcp.server.FastMCP` is available to ALL users who install `kailash`, not just those who install `kailash[mcp]`.

### Existing Entry Points

```toml
[project.scripts]
kailash = "kailash.cli:main"
eatp = "kailash.trust.cli:main"
attest = "kailash.trust.plane.cli.commands:main"
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

The `trustplane-mcp` entry point already exists. The platform server needs `kailash-mcp` added:

```toml
kailash-mcp = "kailash.mcp.platform_server:main"  # new
```

### Import Verification

The TrustPlane MCP server already uses `from mcp.server import FastMCP` successfully. The import path is confirmed working.

### Version Compatibility

- `mcp[cli]>=1.23.0,<2.0` — the `[cli]` extra includes CLI utilities for running servers
- FastMCP was introduced in early versions of the `mcp` Python SDK
- The `<2.0` upper bound protects against breaking changes

## Existing `kailash[mcp]` Extra

The brief mentions `kailash[mcp]` as an optional install, but the dependency is already in the base `dependencies` list, NOT in `[project.optional-dependencies]`. This means:

1. `pip install kailash` already includes `mcp[cli]`
2. There is no separate `kailash[mcp]` extra to install
3. The platform server can assume `mcp` is always available

This simplifies the implementation -- no need for conditional `try/except ImportError` around `mcp.server.FastMCP`.

## Framework Dependencies for Contributors

The contributor plugin system depends on framework packages being installed:

| Contributor | Dependency         | Install Command                |
| ----------- | ------------------ | ------------------------------ |
| core        | `kailash` (always) | `pip install kailash`          |
| platform    | `kailash` (always) | `pip install kailash`          |
| dataflow    | `kailash-dataflow` | `pip install kailash-dataflow` |
| nexus       | `kailash-nexus`    | `pip install kailash-nexus`    |
| kaizen      | `kailash-kaizen`   | `pip install kailash-kaizen`   |
| trust       | `kailash` (always) | `pip install kailash`          |
| pact        | `kailash-pact`     | `pip install kailash-pact`     |

The `importlib` probing loop handles optional packages:

```python
try:
    mod = importlib.import_module("kailash.mcp.contrib.dataflow")
    mod.register_tools(server, project_root)
except ImportError:
    logger.info("kailash-dataflow not installed, skipping dataflow tools")
```

## Rust-Backed MCP Types

The existing `src/kailash/mcp/` module imports from `kailash._kailash`:

```python
from kailash._kailash import McpServer, ToolDef, ToolParam, ToolRegistry
```

These are Rust-backed via PyO3. The platform server does NOT use these types -- it uses `mcp.server.FastMCP` from the Python MCP SDK. The two systems coexist:

- `kailash._kailash.McpServer` — Rust-backed, no transport yet, used via `McpApplication`
- `mcp.server.FastMCP` — Python SDK, full transport support (stdio, SSE), used by platform server

## Conclusion

- FastMCP is available and confirmed working via the TrustPlane server
- `mcp[cli]>=1.23.0,<2.0` is a base dependency (not optional)
- No additional dependency needed for the platform server
- Framework contributors use `importlib` probing for optional packages
- The Rust-backed `McpServer` and Python `FastMCP` coexist without conflict
