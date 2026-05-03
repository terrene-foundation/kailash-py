# MCP Implementations Master Inventory — 2026-04-07

**Audit scope**: Every MCP-related file in `/Users/esperie/repos/loom/kailash-py/` (clients, servers, transports, registries, tests, consumers).

## Finding 1: The MCP Client Situation Is Worse Than the Prior Audit Said

**The prior `mcp-platform-server` workspace audit identified 2 clients.** This audit found the full size and feature gap between them:

### Client A: `src/kailash/mcp_server/client.py` (MCPClient) — 1,288 LOC

Used by BaseAgent at `base_agent.py:40`.

**Capabilities**:

- 4 transports (stdio, WebSocket, SSE, HTTP via `transports.py`)
- 5 auth providers (APIKey, JWT, Basic, OAuth, Bearer)
- ServiceRegistry + LoadBalancer + HealthChecker
- Exponential backoff + circuit breaker retry
- Rate limiting
- Metrics collection
- Resource subscriptions, multi-modal content, structured tools

**The bug in #339 lives here**: tools returned from this client flow through `convert_mcp_to_openai_tools()` which strips `mcp_server_config`. But the client itself is production-grade.

### Client B: `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (McpClient) — 509 LOC

Used by Delegate.

**Capabilities**:

- stdio JSON-RPC 2.0 only
- No auth
- Basic discovery
- Manual retry
- Minimal features

**Why it works anyway**: It's coupled directly to Delegate's `ToolRegistry` with callable executors. The full execution closure is captured at registration time.

### Verdict: Delete McpClient, Keep MCPClient

The 509-line McpClient is strictly a subset of the 1,288-line MCPClient. There is zero justification for maintaining two. Delegate should consume `kailash.mcp_server.MCPClient` with stdio transport config.

## Finding 2: Ecosystem Inventory — 16 MCP Files

| File                                                                            | Type            | LOC   | Status                                  |
| ------------------------------------------------------------------------------- | --------------- | ----- | --------------------------------------- |
| `src/kailash/mcp_server/client.py`                                              | Client          | 1,288 | **ACTIVE (keep)**                       |
| `src/kailash/mcp_server/server.py`                                              | Server          | 2,924 | **ACTIVE (keep)**                       |
| `src/kailash/mcp_server/protocol.py`                                            | Protocol        | 1,152 | ACTIVE                                  |
| `src/kailash/mcp_server/discovery.py`                                           | Registry        | 1,636 | ACTIVE                                  |
| `src/kailash/mcp_server/auth.py`                                                | Auth            | 813   | ACTIVE                                  |
| `src/kailash/mcp_server/transports.py`                                          | Transport       | 1,481 | ACTIVE                                  |
| `src/kailash/mcp_server/advanced_features.py`                                   | Features        | 1,023 | ACTIVE                                  |
| `src/kailash/mcp_server/errors.py`                                              | Types           | 673   | ACTIVE                                  |
| `src/kailash/mcp_server/ai_registry_server.py`                                  | Server          | 737   | ACTIVE                                  |
| `src/kailash/mcp_server/registry_integration.py`                                | Integration     | 587   | ACTIVE                                  |
| `src/kailash/mcp_server/oauth.py`                                               | OAuth           | 1,730 | ACTIVE                                  |
| `src/kailash/mcp_server/subscriptions.py`                                       | Subscriptions   | 1,578 | ACTIVE                                  |
| `src/kailash/mcp_server/resource_cache.py`                                      | Cache           | 128   | ACTIVE                                  |
| `src/kailash/mcp/platform_server.py`                                            | Platform Server | 470   | **ACTIVE (consolidated unified entry)** |
| `src/kailash/trust/plane/mcp_server.py`                                         | Server          | ~200  | ACTIVE (trustplane-mcp CLI)             |
| `src/kailash/trust/mcp/server.py`                                               | Server          | ~50   | ACTIVE (thin wrapper)                   |
| `src/kailash/middleware/mcp/enhanced_server.py`                                 | Server          | 613   | **REFACTOR (unusual pattern)**          |
| `src/kailash/middleware/mcp/client_integration.py`                              | Client          | 648   | **REFACTOR**                            |
| `src/kailash/api/mcp_integration.py`                                            | Registry        | ~200  | **DELETE (broken schema)**              |
| `src/kailash/channels/mcp_channel.py`                                           | Channel         | ~150  | **REFACTOR**                            |
| `src/kailash/nodes/enterprise/mcp_executor.py`                                  | Node            | 430   | ACTIVE (workflow node)                  |
| `src/kailash/nodes/mixins/mcp.py`                                               | Mixin           | 233   | ACTIVE                                  |
| `src/kailash/adapters/mcp_platform_adapter.py`                                  | Adapter         | ~150  | ACTIVE                                  |
| `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py`                      | Client          | 509   | **DELETE (duplicate)**                  |
| `packages/kaizen-agents/src/kaizen_agents/runtime_adapters/tool_mapping/mcp.py` | Adapter         | ~200  | **REFACTOR (rewrite over MCPClient)**   |
| `packages/kailash-nexus/src/nexus/transports/mcp.py`                            | Transport       | ~150  | ACTIVE (thin wrapper over MCPServer)    |
| `packages/kailash-nexus/src/nexus/trust/mcp_handler.py`                         | Handler         | ~200  | ACTIVE                                  |
| `packages/kailash-nexus/src/nexus/mcp/__init__.py`                              | Export          | ~5    | **DELETE (deprecated)**                 |
| `packages/kailash-dataflow/src/dataflow/fabric/mcp_integration.py`              | Tools           | ~100  | ACTIVE (fabric MCP tools)               |

**Total**: ~22K LOC of MCP code spread across 27+ files in 3+ top-level locations.

## Finding 3: Transports Are Already Unified (Good)

`src/kailash/mcp_server/transports.py` owns stdio, WebSocket, SSE, HTTP. All MCPServer/MCPClient consumers use this. **No transport duplication** — this is already correct.

## Finding 4: `kailash-mcp` Package Does Not Exist

- **On disk**: `packages/kailash-mcp/` does NOT exist (verified via Glob)
- **In pyproject.toml**: No references to `kailash-mcp`
- **In docs**: `.claude/skills/05-kailash-mcp/` exists but describes actual implementations in `src/kailash/mcp*` — the docs are accurate, but the package is a phantom
- **CLI entry point**: `kailash-mcp` CLI is registered in the main `kailash` pyproject.toml pointing at `src/kailash/mcp/platform_server.py:main`

The unified MCP server entry exists. The **package boundary** does not.

## Finding 5: 7→1 Server Consolidation Is In Progress

The `mcp-platform-server` workspace closed issues #299, #300, #301 consolidating MCP **servers** down to `src/kailash/mcp/platform_server.py` which namespaces contributors:

- `core.*` tools
- `dataflow.*` tools
- `nexus.*` tools
- `kaizen.*` tools
- `platform.*` tools
- `trust.*` tools
- `pact.*` tools

Status:

- ✅ `nexus/mcp/server.py` (custom JSON) — DELETED (deprecated in `nexus/mcp/__init__.py`)
- ✅ `nexus/mcp_websocket_server.py` (JSON-RPC bridge) — DELETED
- ✅ Platform server at `src/kailash/mcp/platform_server.py` — EXISTS, contributors wired
- ⚠️ `src/kailash/api/mcp_integration.py` — BROKEN (schema shape mismatch), still referenced by `gateway.py`
- ⚠️ `src/kailash/channels/mcp_channel.py` — REFACTORING
- ⚠️ `src/kailash/middleware/mcp/enhanced_server.py` — REFACTORING (unusual pattern using SDK components to define servers)
- ✅ `src/kailash/trust/plane/mcp_server.py` — KEPT as standalone trustplane-mcp CLI

**The server side is 85% done.** The client side is 0% done.

## Finding 6: Zero Consumer Code for api/mcp_integration.py

Only reference is a docstring in `gateway.py`. This file (`MCPIntegration` class, ~200 LOC) has broken schema semantics and no active consumers. **Delete candidate**.

## Convergence Target (from the inventory)

```
packages/kailash-mcp/                       ← NEW primitive package
  src/kailash_mcp/
    __init__.py              ← Public exports
    client.py                ← ONE MCPClient (from src/kailash/mcp_server/client.py)
    server.py                ← ONE MCPServer (from src/kailash/mcp_server/server.py)
    protocol.py              ← Full MCP protocol (from src/kailash/mcp_server/protocol.py)
    transports.py            ← All transports (from src/kailash/mcp_server/transports.py)
    auth.py                  ← Auth providers (from src/kailash/mcp_server/auth.py)
    discovery.py             ← ServiceRegistry, LoadBalancer
    advanced_features.py     ← StructuredTool, Progress, etc.
    errors.py                ← Error types
    subscriptions.py         ← Resource subscriptions
    registry_integration.py  ← Auto-discovery
    oauth.py                 ← OAuth 2.1 (optional, enterprise)
    platform_server.py       ← FastMCP entry with contrib tools
    tools/
      core.py
      dataflow.py
      nexus.py
      kaizen.py
      trust.py
      pact.py
      ml.py                  ← NEW — ML tools
      align.py               ← NEW — Align tools
  pyproject.toml
    [project.scripts]
    kailash-mcp = "kailash_mcp.platform_server:main"
    trustplane-mcp = "kailash_mcp.trust:main"  (or keep separate)
```

**What stays in src/kailash/** (as glue):

- `src/kailash/nodes/enterprise/mcp_executor.py` — Workflow node calling MCP tools
- `src/kailash/nodes/mixins/mcp.py` — Node mixin

**What gets deleted**:

- `src/kailash/mcp_server/` → moved to `packages/kailash-mcp/` (not deleted, migrated)
- `src/kailash/mcp/` → moved to `packages/kailash-mcp/`
- `src/kailash/api/mcp_integration.py` → DELETE (broken, no consumers)
- `src/kailash/channels/mcp_channel.py` → DELETE after refactor, consumed via `packages/kailash-mcp/`
- `src/kailash/middleware/mcp/` → DELETE or merge into `kailash-mcp` if the "build servers with SDK components" pattern has value
- `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` → DELETE (replaced by `kailash-mcp.MCPClient`)
- `packages/kailash-nexus/src/nexus/mcp/` → already deprecated, DELETE

**What becomes a thin wrapper**:

- `packages/kaizen-agents/src/kaizen_agents/runtime_adapters/tool_mapping/mcp.py` — rewritten to adapt MCPClient tools to Delegate's ToolRegistry callable executor shape

## Cross-SDK Alignment

kailash-rs has NO `kailash-mcp` crate either. It has MCP code in:

- `kailash-kaizen/src/mcp/` (client, ONE implementation — good)
- `kailash-nexus/src/mcp/` (server, ONE implementation)
- `eatp/src/mcp/` (custom server — fragmented)
- `kailash-pact/src/mcp.rs` (bridge, not a server)
- `trust-plane/src/mcp/proxy.rs` (proxy, not a server)

Rust has LESS fragmentation than Python on the client side (1 client vs 2) but SAME fragmentation on the server side (4+ custom server implementations).

**Lockstep target**: Create `crates/kailash-mcp/` in Rust alongside `packages/kailash-mcp/` in Python. Move the kailash-kaizen MCP client + kailash-nexus MCP server into kailash-mcp. Refactor eatp, pact, trust-plane to consume the base.
