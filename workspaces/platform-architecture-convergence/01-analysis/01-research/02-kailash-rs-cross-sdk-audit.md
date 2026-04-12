# kailash-rs Cross-SDK Audit — 2026-04-07

**Audit scope**: Does the Rust SDK have the same fragmentation as Python, or did it do things right?

## Verdict: Rust Is Mostly Correct — Python Is The Outlier

Rust has the architecture Python should have. Python's fragmentation is a Python-side execution failure, not a shared design flaw.

## Crate Inventory (Relevant Subset)

| Crate              | Purpose                | Key Contents                                                                                                                                                                                                                                                                 |
| ------------------ | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **kailash-kaizen** | Agent SDK primitives   | `agent::BaseAgent` trait, `llm/` (5 per-provider adapters + dispatcher), `mcp/` (ONE McpClient with pluggable transports), `output/` (StructuredOutput pipeline), `memory/`, `cost/`, `checkpoint/`, `tools/`, `l3/`                                                         |
| **kaizen-agents**  | Agent orchestration    | `agent_engine::Agent` (BaseAgent impl), `orchestration/` (OrchestrationRuntime, SupervisorAgent, WorkerAgent), `delegate_engine::DelegateEngine` (composes Agent + TaodRunner + GovernedSupervisor + PactEngine), `governance/`, `streaming/`, `l3_runtime/`, `pact_engine/` |
| **kailash-nexus**  | Multi-channel platform | `mcp/` (ONE McpServer with transport abstraction)                                                                                                                                                                                                                            |
| **eatp**           | Trust protocol         | `mcp/` (custom MCP server for trust ops — fragmentation candidate)                                                                                                                                                                                                           |
| **kailash-pact**   | PACT governance        | `mcp.rs` (PactMcpBridge — bridge only, not a server)                                                                                                                                                                                                                         |
| **trust-plane**    | Trust environment      | `mcp/proxy.rs` (TrustProxy — proxy only, not a server)                                                                                                                                                                                                                       |
| **kailash-nodes**  | 139+ Core SDK nodes    | `enterprise/mcp_executor.rs`, `enterprise/mcp_service_discovery.rs`                                                                                                                                                                                                          |
| **kz**             | CLI                    | `mcp_bridge.rs` (subprocess management)                                                                                                                                                                                                                                      |

**No `kailash-mcp` crate in Rust either.** Same phantom package problem.

## BaseAgent in Rust

**Location**: `crates/kailash-kaizen/src/agent/mod.rs`

```rust
#[async_trait]
pub trait BaseAgent: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError>;
    async fn run_with_memory(&self, input: &str, mem: Arc<dyn AgentMemory>)
        -> Result<AgentResult, AgentError>;
}
```

**Key differences from Python BaseAgent**:

- 4 methods (vs 7 extension points + mixins + strategies in Python)
- No Node inheritance (no workflow coupling)
- No monolithic `ai_providers.py` — uses modular `llm::client::LlmClient`
- Has working MCP via `kailash_kaizen::mcp::McpClient` (pluggable transports)
- Has working StructuredOutput pipeline

## Delegate in Rust

**Location**: `crates/kaizen-agents/src/delegate_engine.rs`

```rust
pub struct DelegateEngine {
    agent: Option<Agent>,
    taod: Option<TaodRunner>,
    supervisor: Option<GovernedSupervisor>,
    pact: Option<PactEngine>,
    llm_client: Option<Arc<LlmClient>>,
    hydrator: Option<Arc<dyn ToolHydrator>>,
}
```

**This is correct composition**: DelegateEngine composes Agent (which implements BaseAgent), TaodRunner, GovernedSupervisor, PactEngine. Not parallel — composed.

**Cargo dependency**:

```toml
[dependencies]
kailash-kaizen = { path = "../kailash-kaizen" }
```

kaizen-agents properly depends on kailash-kaizen. No parallel stack.

## LLM Providers in Rust

**Location**: `crates/kailash-kaizen/src/llm/`

| File           | Provider       |
| -------------- | -------------- |
| `openai.rs`    | OpenAI         |
| `anthropic.rs` | Anthropic      |
| `google.rs`    | Google/Gemini  |
| `azure.rs`     | Azure OpenAI   |
| `mock.rs`      | Mock (testing) |
| `client.rs`    | Dispatcher     |

**Single modular structure.** kaizen-agents depends on kailash-kaizen and uses `kailash_kaizen::llm::client::LlmClient` directly. NO parallel provider adapters in kaizen-agents.

**This is what Python's `ai_providers.py` (4000-line monolith) should become.**

## MCP in Rust

**Client side (GOOD)**:

- **ONE** `kailash_kaizen::mcp::McpClient` with pluggable transports:
  - `stdio.rs` (subprocess JSON-RPC)
  - `http_transport.rs` (HTTP POST + SSE)
  - In-memory (for testing)
- `McpTransport` trait allows swapping without duplicating client logic
- Used by BaseAgent, Agent, DelegateEngine — single source of truth

**Server side (FRAGMENTED)**:

| Crate         | MCP Server                                         | Shared Base? |
| ------------- | -------------------------------------------------- | ------------ |
| kailash-nexus | McpServer for handlers/workflows                   | No           |
| eatp          | Custom MCP server for verify/delegate/revoke/audit | No           |
| kailash-pact  | PactMcpBridge (not a server, bridge only)          | N/A          |
| trust-plane   | TrustProxy (not a server, proxy only)              | N/A          |

**Same problem as Python server side**: no shared base, each crate rolls its own.

## Multi-Agent Patterns in Rust

**Location**: `crates/kaizen-agents/src/orchestration/`

| Pattern                       | File                           | Builds On |
| ----------------------------- | ------------------------------ | --------- |
| SupervisorAgent + WorkerAgent | `supervisor.rs` + `worker.rs`  | BaseAgent |
| Sequential                    | `runtime.rs` + `strategies.rs` | BaseAgent |
| Parallel                      | `strategies.rs`                | BaseAgent |
| Hierarchical                  | `strategies.rs`                | BaseAgent |
| Pipeline                      | `strategies.rs`                | BaseAgent |
| MultiAgentOrchestrator        | `multi_agent.rs`               | BaseAgent |

All patterns operate on the BaseAgent trait. Same clean abstraction Python should have.

## Rust vs Python Comparison

| Concern                 | Rust                                                              | Python                                                       | Verdict                        |
| ----------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------ |
| Agent trait location    | kailash-kaizen                                                    | kailash-kaizen                                               | ✓ Match                        |
| Concrete Agent location | kaizen-agents                                                     | kaizen-agents                                                | ✓ Match                        |
| MCP client count        | **1** (kailash-kaizen)                                            | **2** (client.py + delegate/mcp.py)                          | **Fix Python**                 |
| LLM providers location  | kailash-kaizen/llm/ (modular, 5 files)                            | kailash-kaizen/nodes/ai/ai_providers.py (4000-line monolith) | **Refactor Python**            |
| MCP servers             | 4 separate (Nexus, eatp, pact, trust-plane) — fragmented          | 7 separate — more fragmented                                 | Fix both                       |
| Structured outputs      | ✓ StructuredOutput pipeline                                       | ✓ BaseAgent signatures (works)                               | ✓ Match                        |
| Composition strategy    | kaizen-agents depends on kailash-kaizen                           | Same on paper, BROKEN in practice                            | **Fix Python**                 |
| Multi-agent patterns    | SupervisorAgent, WorkerAgent, OrchestrationRuntime (on BaseAgent) | Delegate (parallel stack) + patterns/ (on broken BaseAgent)  | **Fix Python**                 |
| Trust integration       | via eatp crate + trait                                            | via kailash.trust but duplicated in Nexus                    | Fix Python's Nexus duplication |

## Cross-SDK Convergence Requirements

### Changes required in Python (Rust is the reference)

1. **Merge BaseAgent and Delegate stacks** — Python needs kaizen-agents/Delegate to COMPOSE kailash-kaizen/BaseAgent, not replace it
2. **Consolidate MCP clients** — delete `kaizen_agents/delegate/mcp.py`, use `kailash.mcp_server.MCPClient` (or whatever becomes `kailash_mcp.MCPClient`)
3. **Split ai_providers.py monolith** — create per-provider adapter modules matching Rust's `llm/` layout
4. **Adopt orchestration patterns** — Python's multi-agent patterns should work the same way as Rust's (pure composition on BaseAgent trait)

### Changes required in BOTH SDKs (lockstep)

1. **Create `kailash-mcp` package/crate** — single source of truth for McpClient + McpServer + transports + tools
2. **Move MCP server from kailash-kaizen/kailash-nexus into kailash-mcp** — then eatp, pact, trust-plane consume the base instead of rolling their own
3. **Extract cross-framework primitives** that every consumer needs

### Changes unique to Rust

1. **Create `kailash-mcp-core` crate** — consolidate the 4 fragmented server implementations (Nexus, eatp, pact, trust-plane) onto a shared base

## Summary

**Rust's agent+LLM architecture is the target.** Python's refactor should:

1. Match Rust's BaseAgent trait (minimal, 3-4 methods)
2. Match Rust's composition model (kaizen-agents depends on kailash-kaizen)
3. Match Rust's modular provider layer (per-provider files, single dispatcher)
4. Match Rust's single MCP client with pluggable transports

**MCP server side is a cross-SDK problem**: both Python and Rust need `kailash-mcp` as a shared package/crate to break the server fragmentation.
