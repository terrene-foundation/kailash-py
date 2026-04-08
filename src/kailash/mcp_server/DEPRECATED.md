# ⚠️ DEPRECATED: `kailash.mcp_server`

**Status:** This entire directory is a deprecation shim layer. All files are thin re-exports from the canonical `kailash_mcp` package.

**Canonical location:** `packages/kailash-mcp/src/kailash_mcp/`

**Import instead:** `from kailash_mcp import ...`

---

## 🤖 If you are an AI coding agent

**STOP. Do NOT edit any file in `src/kailash/mcp_server/`.**

Every `.py` file in this directory is a compatibility shim that re-exports from `kailash_mcp`. Any code you write here:

1. Will be LOST the next time the shim layer is regenerated
2. Will NOT reach any consumer (consumers get re-exported symbols from `kailash_mcp`)
3. Will cause silent inconsistency between the shim and the canonical location

**When making changes to MCP functionality, navigate to `packages/kailash-mcp/src/kailash_mcp/` and work there.**

When adding a new export, add it to the canonical `kailash_mcp` package first, then the wildcard re-export in the shim will pick it up automatically.

---

## Why this shim exists

1. **431 import sites across 120 files** still use `kailash.mcp_server.*`. Breaking all of them in one change would be a flag day; the shim gives consumers time to migrate.
2. **Cross-SDK architectural symmetry with kailash-rs**. The Rust SDK has `crates/kailash-mcp` as a standalone workspace member (see `kailash-rs/crates/kailash-mcp/Cargo.toml`, described as _"Canonical MCP primitives"_). The Python SDK now matches that layout, which makes SPEC-09 cross-SDK wire testing symmetric.
3. **Framework separability**. The convergence north star is that each Kailash framework (MCP, DataFlow, Nexus, Kaizen, PACT, ML, Align) is an extractable package that depends on `kailash` core but is not embedded inside it. The shim moves MCP from _embedded-inside-core_ to _peer-of-core_.

## How the shim works

Every file in `src/kailash/mcp_server/` is a thin module that:

1. Emits `DeprecationWarning` on import (with `stacklevel=2` so the warning points at the consumer's import line, not the shim).
2. Does a wildcard re-export from the canonical module (`from kailash_mcp.X import *`).
3. Defines a `__getattr__` module-level fallback that forwards to the canonical module for any symbol not picked up by the wildcard (private underscore-prefixed symbols, newly-added symbols, etc.). Each fallback access also warns.

The public API surface (exports) of the shim is **identical** to the old `kailash.mcp_server` — every symbol that used to be importable still is.

## Symbol migration table

| Old import                                              | New (canonical) import                                     |
| ------------------------------------------------------- | ---------------------------------------------------------- |
| `from kailash.mcp_server import X`                      | `from kailash_mcp import X`                                |
| `from kailash.mcp_server.client import X`               | `from kailash_mcp.client import X`                         |
| `from kailash.mcp_server.server import X`               | `from kailash_mcp.server import X`                         |
| `from kailash.mcp_server.auth import X`                 | `from kailash_mcp.auth.providers import X`                 |
| `from kailash.mcp_server.oauth import X`                | `from kailash_mcp.auth.oauth import X`                     |
| `from kailash.mcp_server.errors import X`               | `from kailash_mcp.errors import X`                         |
| `from kailash.mcp_server.discovery import X`            | `from kailash_mcp.discovery.discovery import X`            |
| `from kailash.mcp_server.registry_integration import X` | `from kailash_mcp.discovery.registry_integration import X` |
| `from kailash.mcp_server.protocol import X`             | `from kailash_mcp.protocol.protocol import X`              |
| `from kailash.mcp_server.transports import X`           | `from kailash_mcp.transports.transports import X`          |
| `from kailash.mcp_server.advanced_features import X`    | `from kailash_mcp.advanced.features import X`              |
| `from kailash.mcp_server.resource_cache import X`       | `from kailash_mcp.advanced.resource_cache import X`        |
| `from kailash.mcp_server.subscriptions import X`        | `from kailash_mcp.advanced.subscriptions import X`         |
| `from kailash.mcp_server.ai_registry_server import X`   | `from kailash_mcp.contrib.ai_registry import X`            |
| `from kailash.mcp_server.utils import X`                | `from kailash_mcp.utils import X`                          |
| `from kailash.mcp_server.utils.cache import X`          | `from kailash_mcp.utils.cache import X`                    |
| `from kailash.mcp_server.utils.config import X`         | `from kailash_mcp.utils.config import X`                   |
| `from kailash.mcp_server.utils.formatters import X`     | `from kailash_mcp.utils.formatters import X`               |
| `from kailash.mcp_server.utils.metrics import X`        | `from kailash_mcp.utils.metrics import X`                  |

**Most common:** `from kailash.mcp_server import MCPClient` → `from kailash_mcp import MCPClient`.

## Finding consumer sites

Every shim emits a `DeprecationWarning` on import. To find your consumers:

```bash
# Run your test suite with warnings promoted to errors
uv run python -W error::DeprecationWarning -m pytest tests/

# Or grep the code directly
uv run python -c "import warnings; warnings.simplefilter('error'); import your_package"

# Or search for the old import paths
rg 'from kailash\.mcp_server' --type py
rg 'import kailash\.mcp_server' --type py
```

## Removed items (no shim)

Two items from the old `kailash.mcp_server` namespace were removed entirely rather than shimmed, because they had **zero consumers** in the repository:

- `src/kailash/mcp_server/servers/ai_registry.py` (289 LOC) — a FastMCP-based variant of the AI Registry server. The canonical Anthropic-SDK-based variant at `kailash_mcp.contrib.ai_registry` (737 LOC) remains available and is the path forward. If you depended on the FastMCP variant, recover it from `scrap/pre-triage-snapshot-2026-04-08` and file an issue.
- `src/kailash/mcp_server/servers/` directory itself (contained only the file above, no `__init__.py`).

## Timeline

1. **kailash 2.x** — `kailash.mcp_server` is a deprecation shim. DeprecationWarning on every import. Consumers should migrate but are not yet broken.
2. **kailash 3.0** — `kailash.mcp_server` removed entirely. Consumers must use `kailash_mcp`.

There is no hard date on 3.0 yet — the removal happens after the consumer migration has demonstrably completed (zero imports of `kailash.mcp_server` in the downstream dependency graph that we can verify).

## Tracking

- **SPEC:** `workspaces/platform-architecture-convergence/01-analysis/03-specs/01-spec-kailash-mcp-package.md`
- **Cross-SDK architecture:** `loom/kailash-rs/crates/kailash-mcp/Cargo.toml` (the Rust parallel)
- **Red team finding driving this:** issue #339 (BaseAgent → kailash.mcp_server coupling)
- **Safety net:** `scrap/pre-triage-snapshot-2026-04-08` branch preserves the pre-shim working tree
