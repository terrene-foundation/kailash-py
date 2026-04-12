# ADR-004: kailash-mcp Package Boundary

**Status**: ACCEPTED (2026-04-07)
**Scope**: Cross-SDK (kailash-py, kailash-rs)
**Deciders**: Platform Architecture Convergence workspace

## Context

MCP (Model Context Protocol) is fragmented across **both SDKs** despite being a shared protocol:

### Python fragmentation

- 27+ MCP files across 7+ locations
- **Two parallel client implementations**:
  - `src/kailash/mcp_server/client.py` (1,288 LOC) — used by BaseAgent (broken via #339)
  - `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (509 LOC) — used by Delegate (working)
- **Seven+ server implementations**:
  - `nexus/mcp/server.py` (deprecated custom JSON)
  - `nexus/mcp_websocket_server.py` (JSON-RPC bridge)
  - `trust/plane/mcp_server.py` (FastMCP standalone)
  - `api/mcp_integration.py` (in-process registry — broken)
  - `channels/mcp_channel.py` (Nexus channel)
  - `kailash/mcp/server.py` (Rust-backed McpApplication)
  - `kailash/mcp/platform_server.py` (unified platform server — consolidating)
  - `middleware/mcp/enhanced_server.py` (REFACTORING)
- **No `packages/kailash-mcp/` directory exists** — the package is a phantom. All code lives inline inside other packages.

### Rust fragmentation

- 24 MCP files across 7 crates, ~17,650 LOC total
- **One MCP client** (`crates/kailash-kaizen/src/mcp/`) — good
- **Three+ server implementations** with **four different `JsonRpcRequest` type variants**:
  - `kailash-nexus/src/mcp/server.rs` (2,411 LOC) — own JSON-RPC types
  - `eatp/src/mcp/` (1,681 LOC) — own JSON-RPC types
  - `trust-plane/src/mcp/` (1,397 LOC) — own JSON-RPC types
  - `kailash-pact/src/mcp.rs` (1,114 LOC) — not a server, policy bridge
- **No `kailash-mcp` crate exists** — same phantom package problem

### Cross-SDK problems

- Python client A (`kailash.mcp_server.MCPClient`) and Client B (`kaizen_agents.delegate.mcp.McpClient`) use **incompatible tool registry shapes** (JSON schemas vs callable executors)
- Rust's 4 `JsonRpcRequest` variants are **not round-trip compatible** with each other
- Python client and Rust client can't be guaranteed to interoperate because the wire types are defined independently

### Prior consolidation (incomplete)

The `mcp-platform-server` workspace (Apr 1-6, 2026) consolidated the Python server side 85% — closed issues #299, #300, #301. But it explicitly kept **two parallel client implementations** with the note "KEEP as-is. This is a CLIENT, not a server. No changes needed." The client consolidation was never done.

## Decision

**Extract a new `kailash-mcp` package in Python and a new `kailash-mcp` crate in Rust, with canonical protocol types defined in a shared spec document. Both SDKs converge onto this package in lockstep. The package contains: one client, one server base, one transport layer, one set of JSON-RPC types, shared authentication primitives, platform tools.**

### Python package structure

```
packages/kailash-mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── kailash_mcp/
│       ├── __init__.py               # Public API
│       ├── protocol/                 # Wire types (canonical)
│       │   ├── __init__.py
│       │   ├── jsonrpc.py            # JsonRpcRequest, JsonRpcResponse, JsonRpcError
│       │   ├── types.py              # McpToolInfo, McpResourceInfo, ServerInfo, ServerCapabilities
│       │   └── errors.py             # McpError, error codes per spec
│       ├── client.py                 # MCPClient (single implementation)
│       ├── server.py                 # MCPServer base class
│       ├── server_platform.py        # PlatformMCPServer (contrib tools consolidation)
│       ├── transports/
│       │   ├── __init__.py
│       │   ├── base.py               # MCPTransport protocol
│       │   ├── stdio.py              # StdioTransport (subprocess JSON-RPC)
│       │   ├── http.py               # HTTPTransport (POST)
│       │   ├── sse.py                # SSETransport
│       │   └── websocket.py          # WebSocketTransport
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── api_key.py            # APIKeyAuth
│       │   ├── jwt.py                # JWTAuth
│       │   ├── oauth.py              # OAuth 2.1
│       │   └── basic.py              # BasicAuth
│       ├── discovery/
│       │   ├── __init__.py
│       │   ├── service_registry.py   # ServiceRegistry
│       │   ├── load_balancer.py
│       │   └── health_checker.py
│       ├── retry/
│       │   ├── __init__.py
│       │   ├── exponential.py        # ExponentialBackoffRetry
│       │   └── circuit_breaker.py    # CircuitBreakerRetry
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py           # Unified ToolRegistry (JSON + callable)
│       │   └── hydrator.py           # BM25 tool hydrator (MOVED from kaizen_agents)
│       ├── contrib/                  # Framework-specific tools
│       │   ├── __init__.py
│       │   ├── core.py               # core.* tools
│       │   ├── dataflow.py           # dataflow.* tools
│       │   ├── nexus.py              # nexus.* tools
│       │   ├── kaizen.py             # kaizen.* tools
│       │   ├── trust.py              # trust.* tools
│       │   ├── pact.py               # pact.* tools
│       │   ├── ml.py                 # ml.* tools
│       │   └── align.py              # align.* tools
│       └── advanced/
│           ├── __init__.py
│           ├── subscriptions.py      # Resource subscriptions
│           ├── structured_tools.py   # StructuredTool
│           └── multimodal.py         # MultiModalContent
├── tests/
│   ├── unit/
│   ├── integration/
│   │   └── test_interop.py           # Python client ↔ Rust server round-trip
│   └── e2e/
```

### Rust crate structure

```
crates/kailash-mcp/
├── Cargo.toml
├── src/
│   ├── lib.rs
│   ├── protocol/
│   │   ├── mod.rs                    // Wire types (canonical)
│   │   ├── jsonrpc.rs                // JsonRpcRequest, JsonRpcResponse, JsonRpcError
│   │   ├── types.rs                  // McpToolInfo, ServerInfo, etc.
│   │   └── errors.rs
│   ├── client.rs                     // McpClient (moved from kailash-kaizen/src/mcp/client.rs)
│   ├── server/
│   │   ├── mod.rs                    // McpServerCore trait (the SHARED server base)
│   │   ├── handler.rs
│   │   └── dispatch.rs
│   ├── transport/
│   │   ├── mod.rs                    // McpTransport trait
│   │   ├── stdio.rs                  // StdioTransport
│   │   ├── http.rs                   // HttpTransport
│   │   └── sse.rs                    // SseTransport (extracted from nexus)
│   ├── auth/
│   │   ├── mod.rs
│   │   ├── api_key.rs
│   │   └── jwt.rs
│   ├── tools/
│   │   ├── mod.rs
│   │   ├── registry.rs               // Unified ToolRegistry
│   │   └── hydrator.rs               // BM25 hydrator
│   └── contrib/
│       ├── mod.rs
│       └── platform_server.rs        // Platform server with contrib namespaces
├── tests/
│   ├── integration/
│   │   └── interop_tests.rs          // Rust client ↔ Python server round-trip
│   └── unit/
```

### Canonical protocol types (shared spec)

The JSON-RPC types must be **byte-identical** on the wire in both SDKs. Defined in a shared spec document at `docs/specs/mcp-protocol.md`:

```python
# Python (src/kailash_mcp/protocol/jsonrpc.py)
@dataclass
class JsonRpcRequest:
    jsonrpc: Literal["2.0"] = "2.0"
    method: str = ""
    params: Optional[dict[str, Any]] = None
    id: Optional[int | str] = None  # None for notifications

@dataclass
class JsonRpcResponse:
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[int | str] = None
    result: Optional[Any] = None
    error: Optional[JsonRpcError] = None

@dataclass
class JsonRpcError:
    code: int                    # -32700 (parse) | -32600 (invalid) | -32601 (method) | -32602 (params) | -32603 (internal)
    message: str
    data: Optional[Any] = None
```

```rust
// Rust (crates/kailash-mcp/src/protocol/jsonrpc.rs)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    #[serde(default = "default_version")]
    pub jsonrpc: String,  // always "2.0"
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<Value>,  // i64 or String, None for notifications
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}
```

**Cross-SDK validation**: The `tests/integration/test_interop.py` and `tests/integration/interop_tests.rs` must successfully round-trip every supported message shape between a Python client and a Rust server, and vice versa.

## Rationale

1. **Both SDKs have the same problem.** Python and Rust both lack a real `kailash-mcp` package. The fix is cross-SDK.

2. **Consolidation is already 85% done for Python servers.** The `mcp-platform-server` workspace finished the server side. This ADR finishes the client side and extracts everything into a real package.

3. **Rust has ONE MCP client already** (in kailash-kaizen). Moving it to `kailash-mcp` is a simple crate extraction.

4. **ONE canonical set of JSON-RPC types** fixes the cross-SDK interop risk. Currently, a Python client talking to a Rust server (or vice versa) may fail on subtle serialization differences (e.g., Rust's trust-plane uses `id: Value` but kailash-kaizen uses `id: u64`).

5. **Framework-first compliance.** `kailash-mcp` becomes a real primitive package. Every consumer (BaseAgent, Delegate, Nexus, PACT, TrustPlane, ML, Align) imports from it instead of rolling its own.

6. **Fixes bug #339 as a side-effect.** BaseAgent's broken `tool_formatters` code disappears — it's replaced by `kailash_mcp.MCPClient` which already works (it's the same production-grade client kaizen-agents has been using all along, just consolidated).

7. **Eliminates the 4 JSON-RPC type variants in Rust** (same problem as Python, worse by count).

8. **Enables a plugin story.** Contrib tools (`kailash_mcp.contrib.*`) become a clean extension point for framework-specific MCP tooling.

## Consequences

### Positive

- ✅ One client in Python (was 2)
- ✅ One server base in Python (was 7+, 85% consolidated already)
- ✅ One set of JSON-RPC types in both SDKs (was 2 in Python, 4 in Rust)
- ✅ One transport layer per SDK
- ✅ Bug #339 fixed as side-effect
- ✅ ~7,100 LOC of Rust JSON-RPC duplication eliminated
- ✅ Cross-SDK interop becomes verifiable via round-trip tests
- ✅ `packages/kailash-mcp/` becomes a real package users can install independently: `pip install kailash-mcp`
- ✅ Rust's `crates/kailash-mcp/` provides a shared base for all MCP servers in the workspace
- ✅ Framework-first hierarchy is finally real for MCP

### Negative

- ❌ Migration touches BaseAgent, Delegate, Nexus, PACT, TrustPlane MCP servers, kailash-nodes enterprise MCP executor. High blast radius.
- ❌ Backward compat shims required at old import paths (`kailash.mcp_server.*`, `kaizen_agents.delegate.mcp`). Deprecation over v2.x, removal in v3.0 (ADR-009).
- ❌ Cross-SDK lockstep (ADR-008) adds process overhead for coordinated releases.
- ❌ Rust's 4 MCP server implementations need refactoring to use the shared `McpServerCore`. Non-trivial work for eatp, trust-plane, kailash-pact crates.
- ❌ The `kailash.mcp_server.client.MCPClient` absorbed by `kailash_mcp.MCPClient` is the larger, more featureful one (1,288 LOC vs 509). Delegate's client was missing features (auth, retry, metrics, discovery) — Delegate gains those automatically, which is good but changes its runtime behavior.

### Neutral

- Python's `mcp-platform-server` workspace work is NOT lost — the platform server consolidation moves into `kailash_mcp.server_platform.PlatformMCPServer`.
- TrustPlane's FastMCP-based MCP server (`src/kailash/trust/plane/mcp_server.py`) becomes an application-level server that uses `kailash_mcp.server.MCPServer` as its base. The `trustplane-mcp` CLI entry point is preserved.

## Alternatives Considered

### Alternative 1: Keep MCP code inline; just consolidate clients and types

**Rejected**. Would leave the phantom package problem. Consumers still import from `kailash.mcp_server.*` or `kaizen_agents.delegate.mcp`. No package boundary means the next developer inevitably creates a third MCP client somewhere.

### Alternative 2: Put MCP in `kailash-core`

**Rejected**. Violates framework-first separation — `kailash-core` should not pull in MCP protocol implementation. Also makes MCP updates require a `kailash-core` release.

### Alternative 3: Python does `kailash-mcp`, Rust stays fragmented

**Rejected**. Violates EATP D6 (cross-SDK semantic parity). Interop between Python and Rust remains fragile. Same mistake that led to 4 variants of `JsonRpcRequest` in Rust.

### Alternative 4: Use an external MCP library (e.g., `mcp` Python package from Anthropic)

**Partially considered**. The `kailash_mcp.server` may wrap `mcp.server.FastMCP` (the official Python SDK) internally. But the package boundary at `packages/kailash-mcp/` is still needed because:

- We have platform-specific tools (contrib/)
- We have Kailash-specific auth providers (JWT tied to `kailash.trust`)
- We have Kailash-specific ToolRegistry that unifies JSON schemas + callables

External MCP library usage is an implementation detail, not a package boundary decision.

## Implementation Notes

### Migration order (per SPEC-01)

1. **Create the package skeleton** (pyproject.toml, directory structure, empty modules)
2. **Move the production-grade client** from `src/kailash/mcp_server/client.py` to `packages/kailash-mcp/src/kailash_mcp/client.py`
3. **Move protocol types** and unify them with the canonical spec
4. **Move transports** (stdio, http, sse, websocket, advanced_features, subscriptions, auth, discovery)
5. **Add backward-compat shims** at `src/kailash/mcp_server/__init__.py` that re-export from `kailash_mcp`
6. **Migrate BaseAgent's MCP integration** to use `kailash_mcp.MCPClient` (fixes #339)
7. **Delete `kaizen_agents/delegate/mcp.py`** (after Delegate is migrated to use BaseAgent + wrappers per ADR-007)
8. **Move ToolHydrator** from `kaizen_agents/delegate/tools/hydrator.py` to `kailash_mcp/tools/hydrator.py`
9. **Move platform_server** to `kailash_mcp/server_platform.py`
10. **Delete `src/kailash/api/mcp_integration.py`** (verified zero consumers per red team recommendation)
11. **Refactor `src/kailash/channels/mcp_channel.py`** to use `kailash_mcp`
12. **Refactor/delete `src/kailash/middleware/mcp/enhanced_server.py`** (document or delete the unusual pattern)
13. **Add cross-SDK interop tests** (Python client ↔ Rust server, Rust client ↔ Python server)

### Rust migration order (parallel)

1. **Create `crates/kailash-mcp/` crate** with canonical protocol types
2. **Move `kailash-kaizen/src/mcp/` to `kailash-mcp`** (the client lives here now)
3. **Move transports** (stdio, http, sse) from `kailash-nexus/src/mcp/` to `kailash-mcp/src/transport/`
4. **Extract `McpServerCore` trait** from the three existing servers (nexus, eatp, trust-plane)
5. **Refactor `kailash-nexus/src/mcp/server.rs`** to implement `McpServerCore` and use shared transports
6. **Refactor `crates/eatp/src/mcp/`** similarly
7. **Refactor `crates/trust-plane/src/mcp/`** similarly
8. **Fix zero-tolerance violations** in `kailash-nodes/src/enterprise/mcp_executor.rs` (real execution, not simulated) and `kz/src/mcp_bridge.rs` (wire to `kailash_mcp::client::McpClient`)

### Backward compatibility shims

**Python (v2.x)**:

```python
# src/kailash/mcp_server/__init__.py (backward compat)
import warnings

warnings.warn(
    "kailash.mcp_server is deprecated. Use `from kailash_mcp import ...` instead. "
    "This shim will be removed in v3.0.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash_mcp import (
    MCPClient,
    MCPServer,
    ServiceRegistry,
    # ... all public API
)
from kailash_mcp.auth import APIKeyAuth, JWTAuth
from kailash_mcp.transports import StdioTransport, HTTPTransport, SSETransport, WebSocketTransport
```

**Rust (v2.x)**:

```rust
// crates/kailash-kaizen/src/mcp/mod.rs (backward compat)
#[deprecated(
    since = "0.X.Y",
    note = "Use `kailash_mcp::client::McpClient` instead. \
            This re-export will be removed in the next major version."
)]
pub use kailash_mcp::client::McpClient;
```

### Feature flags for optional capabilities

**Python pyproject.toml**:

```toml
[project]
name = "kailash-mcp"

[project.optional-dependencies]
stdio = []  # base, always available
http = ["httpx>=0.27"]
sse = ["sse-starlette>=1.8"]
websocket = ["websockets>=12"]
auth-oauth = ["authlib>=1.3"]
auth-jwt = ["pyjwt>=2.8"]
full = ["kailash-mcp[http,sse,websocket,auth-oauth,auth-jwt]"]
```

**Rust Cargo.toml**:

```toml
[features]
default = ["client", "server", "stdio-transport"]
client = []
server = []
stdio-transport = []
http-transport = ["reqwest"]
sse-transport = ["axum"]
websocket-transport = ["tokio-tungstenite"]
auth = ["jsonwebtoken"]
platform-server = ["contrib"]
contrib = []
```

### CLI entry points

Python:

```toml
[project.scripts]
kailash-mcp = "kailash_mcp.server_platform:main"
trustplane-mcp = "kailash_mcp.contrib.trust:main"
```

Rust:

```toml
[[bin]]
name = "kailash-mcp"
path = "src/bin/platform_server.rs"
required-features = ["platform-server"]
```

## Related ADRs

- **ADR-001**: Composition over extension points (BaseAgent consumes `kailash_mcp.MCPClient`)
- **ADR-005**: Provider capability protocol split (providers and MCP are independent primitives)
- **ADR-008**: Cross-SDK lockstep convergence (Python and Rust converge in parallel)
- **ADR-009**: Backward compatibility strategy (shim lifetime, deprecation window)

## Related Research

- `01-research/01-mcp-inventory.md` — full Python MCP file inventory (27+ files)
- `02-rs-research/01-rs-mcp-audit.md` — full Rust MCP file inventory (24 files)

## Related Issues

- Python #339 — BaseAgent MCP broken (fixed as side-effect)
- Prior `mcp-platform-server` workspace — 85% Python server consolidation (this ADR completes the remaining 15%)
