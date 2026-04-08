# kailash-rs MCP Deep Audit — 2026-04-07

**Audit scope**: Every MCP file in kailash-rs crates, clients, servers, transports, bridges, tests.

## Scale

- **24 MCP files** across 7 crates
- **~17,650 LOC of MCP code**
- **3,433 LOC (19%) of tests**
- **7,100+ LOC of duplication** (JSON-RPC types, error codes, request dispatch)

## Master Inventory

| File                                                    | Crate          | Type                   | LOC   | Uses kailash_kaizen::mcp? |
| ------------------------------------------------------- | -------------- | ---------------------- | ----- | ------------------------- |
| `kailash-kaizen/src/mcp/mod.rs`                         | kailash-kaizen | Protocol types         | 400   | origin                    |
| `kailash-kaizen/src/mcp/client.rs`                      | kailash-kaizen | **Client**             | 1,313 | origin                    |
| `kailash-kaizen/src/mcp/transport.rs`                   | kailash-kaizen | Transport trait        | 253   | origin                    |
| `kailash-kaizen/src/mcp/stdio.rs`                       | kailash-kaizen | Transport impl         | 566   | origin                    |
| `kailash-kaizen/src/mcp/http_transport.rs`              | kailash-kaizen | Transport impl         | 369   | origin                    |
| `kailash-nexus/src/mcp/server.rs`                       | kailash-nexus  | **Server**             | 2,411 | NO                        |
| `kailash-nexus/src/mcp/auth.rs`                         | kailash-nexus  | Auth                   | 695   | NO                        |
| `kailash-nexus/src/mcp/sse.rs`                          | kailash-nexus  | SSE transport          | 700   | NO                        |
| `kailash-nexus/src/mcp/stdio.rs`                        | kailash-nexus  | stdio transport        | 534   | NO                        |
| `kailash-nexus/src/mcp/http_transport.rs`               | kailash-nexus  | HTTP transport         | 390   | NO                        |
| `eatp/src/mcp/mod.rs`                                   | eatp           | **Server**             | 591   | NO                        |
| `eatp/src/mcp/tools.rs`                                 | eatp           | Tool handlers          | 756   | NO                        |
| `eatp/src/mcp/resources.rs`                             | eatp           | Resource handlers      | 334   | NO                        |
| `trust-plane/src/mcp/mod.rs`                            | trust-plane    | **Server**             | 918   | NO                        |
| `trust-plane/src/mcp/proxy.rs`                          | trust-plane    | Constraint proxy       | 479   | NO                        |
| `kailash-pact/src/mcp.rs`                               | kailash-pact   | **Bridge (policy)**    | 1,114 | NO                        |
| `kz/src/mcp_bridge.rs`                                  | kz             | **Subprocess manager** | 914   | Planned (comment)         |
| `kailash-nodes/src/enterprise/mcp_executor.rs`          | kailash-nodes  | Workflow node          | 724   | NO (stubbed)              |
| `kailash-nodes/src/enterprise/mcp_service_discovery.rs` | kailash-nodes  | Workflow node          | 898   | NO                        |
| Tests: `kailash-kaizen/tests/mcp_integration.rs`        | kailash-kaizen | Test                   | 642   | Yes                       |
| Tests: `kailash-nexus/tests/mcp_integration.rs`         | kailash-nexus  | Test                   | 757   | No                        |
| Tests: `eatp/tests/mcp_tests.rs`                        | eatp           | Test                   | 2,034 | No                        |

## Client Side: ONE Implementation (GOOD)

**Location**: `crates/kailash-kaizen/src/mcp/`

```rust
pub use client::McpClient;
pub use transport::{McpTransport, InMemoryTransport};
pub use stdio::StdioTransport;
pub use http_transport::HttpTransport;
```

- Generic over `McpTransport` trait — **pluggable transports** (unlike Python's 2 parallel clients)
- `discover_and_register()` auto-converts MCP tools to `ToolRegistry` entries
- Uses `kailash_value::Value` for schema representation
- Test transport for unit testing

**Consumers**: kaizen-agents, kz (planned), direct tests

**Verdict**: ✅ Rust has ONE MCP client. Python has TWO. This is the architecture Python should match.

## Server Side: THREE Fragmented Implementations (BAD)

### 1. kailash-nexus MCP Server (6 files, 4,730 LOC)

- `server.rs` (2,411 LOC) — Main server, tool registration, JSON-RPC dispatch
- `auth.rs` (695 LOC) — API key + JWT authentication
- `sse.rs`, `stdio.rs`, `http_transport.rs` — Transport handlers
- **Defines its own JSON-RPC types** (JsonRpcRequest, JsonRpcResponse, JsonRpcError)
- **Defines its own McpToolInfo, ServerInfo, McpTransport enum**

### 2. eatp MCP Server (3 files, 1,681 LOC)

- `mod.rs` (591 LOC) — Server core, stdio/SSE dispatch
- `tools.rs` (756 LOC) — eatp_verify, eatp_delegate, eatp_revoke, eatp_audit_query, eatp_status, eatp_validate_multi_sig
- `resources.rs` (334 LOC) — `eatp://authorities`, `eatp://agents/{id}`, `eatp://chains/{id}`, `eatp://constraints/{id}`
- **Defines its own JSON-RPC types** (different field ordering than nexus)
- Uses hyper v1 for SSE (nexus uses axum)

### 3. trust-plane MCP Server (2 files, 1,397 LOC)

- `mod.rs` (918 LOC) — Server core, tool/resource handlers (trust_check, trust_record, trust_envelope, trust_status, trust_verify)
- `proxy.rs` (479 LOC) — TrustProxy — wraps calls with constraint enforcement
- **Defines its own JSON-RPC types** (third variant)

**Total server LOC**: 7,808 across 3 crates, each with its own JSON-RPC types.

## JSON-RPC Type Duplication (The Core Problem)

Four variants of the same type in four different files:

| Crate          | `id` field             | `params` field  |
| -------------- | ---------------------- | --------------- |
| kailash-kaizen | `u64` (atomic counter) | `Option<Value>` |
| kailash-nexus  | `Option<Value>`        | `Value`         |
| eatp           | `Option<Value>`        | `Value`         |
| trust-plane    | `Value`                | `Option<Value>` |

**Impact**: Incompatible round-tripping. Client and servers can't share types even within the same Rust workspace.

## Transport Layer: Trait Defined But Not Used by Servers

`kailash-kaizen` defines:

```rust
pub trait McpTransport: Send + Sync + 'static {
    fn send(&self, request: &str)
        -> Pin<Box<dyn Future<Output = Result<String, McpError>> + Send + '_>>;
}
```

**Used by**: `McpClient` only.

**Not used by**: nexus, eatp, trust-plane — they each implement SSE/stdio/HTTP transport handling inline, without implementing the trait.

**Missed opportunity**: A shared transport layer could eliminate ~2,000 LOC of transport duplication.

## Bridges (Not Servers or Clients)

### kailash-pact/src/mcp.rs (1,114 LOC) — Policy Engine

- **NOT a server or client** — a governance policy evaluator
- `PactMcpBridge::evaluate_tool_call()` returns `McpVerdict`:
  ```rust
  pub enum McpVerdict {
      AutoApproved { tool_name },
      Flagged { tool_name, reason },
      Held { tool_name, reason },
      Blocked { tool_name, reason },
  }
  ```
- Depends on `kailash-governance` (verdict types) and `eatp` (clearance levels)
- Upstream servers call it to decide whether to allow tool execution

### kz/src/mcp_bridge.rs (914 LOC) — Subprocess Manager

- **NOT a protocol implementation** — process lifecycle management
- Spawns MCP server subprocesses, maintains tool inventory per server
- Qualifies tool names as `mcp_{server}_{tool}`
- Trust model: project-level servers must be explicitly trusted; user-level are implicit
- **Code comment**: "actual MCP protocol communication will be wired through `kailash_kaizen::mcp::client::McpClient` in a future integration"
- **Status**: NOT yet using kaizen client. Subprocess management only.

## Executor Nodes: Stubbed

### kailash-nodes/src/enterprise/mcp_executor.rs (724 LOC)

- Workflow node for executing MCP tool calls
- Inputs: `service_id`, `tool_name`, `tool_args`, `timeout_seconds`, `retry_on_failure`
- **Simulated execution** — returns mock `{ "tool": name, "args": args, "service_name": ..., "status": "success" }`
- Code comment: "actual MCP tool execution requires network calls to real services"
- **Zero-tolerance violation**: Stub returning fake success

### kailash-nodes/src/enterprise/mcp_service_discovery.rs (898 LOC)

- Workflow node for registering/discovering MCP services
- Uses global `DashMap`-based service registry
- Operations: `register`, `deregister`, `discover`, `list`, `health_check`

## Dependency Graph

```
kaizen-agents
    ↓
kailash-kaizen (MCP client, trait, transports)
    ├── depends on: kailash-core, kailash-value
    ├── optional: eatp, trust-plane, kailash-pact
    └── tests import: kailash-nexus (for server testing)

kailash-nexus (MCP server, own JSON-RPC types)
    ├── depends on: kailash-core, kailash-value
    └── INDEPENDENT from kaizen (different JSON-RPC types)

eatp (MCP server + EATP trust ops)
    ├── depends on: (crypto only, no kailash deps)
    └── optional feature: mcp (requires hyper, tokio-stream)

trust-plane (MCP server + constraint proxy)
    ├── depends on: eatp
    └── optional feature: mcp (requires axum)

kailash-pact (Governance policy engine)
    ├── depends on: kailash-governance, eatp
    └── feature: mcp (empty, just enables the module)

kz (CLI + MCP bridge)
    ├── depends on: kailash-kaizen
    └── NOT yet using: kaizen's McpClient (planned)

kailash-nodes (Workflow nodes)
    └── enterprise nodes: mcp_service_discovery, mcp_executor
        └── no direct MCP imports (uses abstract registry)
```

**Key observation**: **No cross-crate sharing of MCP types.** Each server re-implements JSON-RPC from scratch.

## Python vs Rust Parallel

| Problem                       | Python                              | Rust                                                            |
| ----------------------------- | ----------------------------------- | --------------------------------------------------------------- |
| Parallel MCP clients          | 2 (client.py + delegate/mcp.py)     | **1 (kaizen)** — better                                         |
| Parallel MCP servers          | 7+                                  | 3 (nexus, eatp, trust-plane) — less fragmented but same problem |
| JSON-RPC type duplication     | ~2 variants                         | **4 variants** — worse                                          |
| Shared transport trait        | No                                  | Yes (trait defined in kaizen) but not used by servers           |
| Governance MCP bridge         | `kailash-pact/mcp/` middleware      | `kailash-pact/src/mcp.rs` (evaluator)                           |
| CLI MCP bridge                | (Python uses MCPClient directly)    | `kz/mcp_bridge.rs` (subprocess manager, planned integration)    |
| `kailash-mcp` package exists? | NO                                  | NO                                                              |
| Server consolidation status   | 85% (mcp-platform-server workspace) | 0% (fragmented)                                                 |

**Critical finding**: Rust's MCP situation is DIFFERENT from Python's but equally fragmented. Python has more servers; Rust has fewer but each with its own JSON-RPC types. **Both SDKs need `kailash-mcp` extraction**.

## Convergence Target (Rust Side)

### Phase 1: Create `crates/kailash-mcp/`

```rust
// crates/kailash-mcp/src/lib.rs
pub mod protocol {
    // Canonical JSON-RPC types (one source)
    pub use canonical::{JsonRpcRequest, JsonRpcResponse, JsonRpcError};
    pub use types::{McpToolInfo, McpResourceInfo, ServerInfo, ServerCapabilities};
}

pub mod transport {
    pub use trait_def::McpTransport;
    pub use in_memory::InMemoryTransport;
    pub use stdio::StdioTransport;
    pub use http::HttpTransport;
    pub use sse::SseTransport;
}

pub mod client {
    pub use mcp_client::McpClient;
}

pub mod server {
    pub use mcp_server::{McpServerCore, McpServerBuilder};
}
```

**Contents** (extracted from existing code):

- Unified JSON-RPC types (from nexus — has the most complete field set)
- Unified protocol types (McpToolInfo, ServerInfo — from nexus/kaizen)
- McpTransport trait (from kaizen)
- Transport implementations (from kaizen, plus SSE extracted from nexus)
- McpClient (from kaizen, unchanged)
- **NEW**: McpServerCore — refactored base shared by nexus/eatp/trust-plane

**Features**:

```toml
[features]
default = ["client", "server"]
client = []
server = []
stdio-transport = []
http-transport = []
sse-transport = []
auth = []
```

### Phase 2: Migrate Servers to Use Shared Base

1. **kailash-nexus**: Depends on `kailash-mcp`, uses `McpServerCore`, keeps Nexus-specific tool registration
2. **eatp**: Depends on `kailash-mcp`, uses `McpServerCore`, keeps EATP-specific trust tools
3. **trust-plane**: Depends on `kailash-mcp`, uses `McpServerCore`, keeps TrustProxy as enforcement layer
4. **kailash-pact**: No changes (policy bridge, not a server)

### Phase 3: Wire kz CLI Bridge

1. Make `kz/src/mcp_bridge.rs` use `kailash_kaizen::mcp::client::McpClient` (or after extraction, `kailash_mcp::McpClient`)
2. Implement actual tool invocation (currently stubbed)
3. Add workflow node integration

### Phase 4: Complete Executor Node Implementation

1. Replace simulated execution in `kailash-nodes/mcp_executor.rs` with real calls
2. Use service registry + MCP client for actual tool invocation
3. **Zero-tolerance fix**: Remove the mock success response

### Phase 5: Reduce Duplication (Side-Effect)

- ~7,100 LOC of JSON-RPC duplication → ~500 LOC shared
- Transport duplication → shared trait impls
- Auth code (695 LOC in nexus) → shared auth crate

## Cross-SDK D6 Parity Path

Both Python and Rust need to:

1. Create `kailash-mcp` package/crate
2. Consolidate servers onto a shared base
3. Use canonical JSON-RPC types

**Lockstep plan**:

1. Define the canonical protocol types ONCE (in a spec doc)
2. Implement in Python `packages/kailash-mcp/src/kailash_mcp/protocol.py`
3. Implement in Rust `crates/kailash-mcp/src/protocol/` with matching serialization
4. Cross-validate via integration tests that round-trip messages between Python client and Rust server (and vice versa)

## Zero-Tolerance Violations Found (Must Fix)

1. **`kailash-nodes/src/enterprise/mcp_executor.rs`**: Simulated execution returning fake success responses — violates Rule 2 (no stubs, no fake data)
2. **`kz/src/mcp_bridge.rs`**: Comment says "will be wired in future integration" — violates Rule 6 (implement fully)

Both must be fixed as part of this convergence work, not deferred.
