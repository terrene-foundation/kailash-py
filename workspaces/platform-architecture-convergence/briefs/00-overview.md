# Platform Architecture Convergence — Workspace Brief

**Created**: 2026-04-07
**Trigger**: GH issues #339 (BaseAgent MCP broken) and #340 (Gemini structured+tools crash) revealed deeper architectural fragmentation in kaizen + MCP. Investigation expanded scope: the framework-first hierarchy is violated across **all** Kailash frameworks, not just kaizen. This workspace audits and converges the **entire platform** primitive/engine architecture.

## The Problem (One Sentence)

Across the Kailash platform (Core SDK, DataFlow, Nexus, Kaizen, PACT, Trust/EATP, ML, Align, MCP), what we call "primitives" and "engines" are often parallel implementations rather than a real composition hierarchy — engines were built fresh instead of composing primitives, primitives have leaked into engines as duplicates, and cross-framework synergies (kaizen→trust, pact→trust, dataflow→trust, kaizen→pact, etc.) suffer from broken or duplicated integration paths.

## Decision Already Made

**No bandaid. Full rework. Break everything up. Gut everything out. Rebuild properly.**

Per `rules/framework-first.md`:

- **Specs** define standards (CARE, EATP, CO, COC, PACT)
- **Primitives** implement building blocks
- **Engines** compose primitives into opinionated frameworks
- **Entrypoints** are products users interact with

The current code violates this hierarchy in multiple places. This workspace finds every violation, designs the convergence target, and rebuilds.

## In Scope — All Kailash Frameworks

### 1. Core SDK (`kailash`)

**Primitives**: `Node`, `WorkflowBuilder`, `LocalRuntime`, `AsyncLocalRuntime`, `NodeParameter`, `kailash.workflow.*`
**Engines**: (none today — Core SDK is primitive-only)
**Audit**: How does every other framework consume Core SDK primitives? Are there places where Core SDK has "engine-like" behavior buried inside primitives?

### 2. DataFlow (`kailash-dataflow`)

**Primitives**: `DataFlow`, `@db.model`, `db.express`, generated CRUD nodes
**Engine**: `DataFlowEngine.builder()` — validation, classification, query tracking, retention
**Audit**: Does `DataFlowEngine` actually compose `DataFlow`, or is it a parallel implementation? Where does the Express API live? How does it consume Trust (audit) and PACT (governance)?

### 3. Nexus (`kailash-nexus`)

**Primitives**: `Nexus()`, handlers, channels, transports
**Engine**: `NexusEngine` — middleware stack, auth, K8s probes, OpenAPI
**Audit**: Same question — composition or duplication? How does Nexus consume MCP (it has its own MCP channel — does that consume `kailash-mcp` or roll its own)? How does Nexus consume Trust/PACT for auth and rate limiting?

### 4. Kaizen (`kailash-kaizen` + `kaizen-agents`)

**Primitives**: `BaseAgent`, `Signature`, `InputField`, `OutputField`, tool types
**Engines**: `Delegate`, `GovernedSupervisor`, multi-agent patterns
**Known broken**: BaseAgent has structured outputs but broken MCP. Delegate has working MCP but no structured outputs. They are parallel stacks with zero shared code. See `01-analysis/01-research/09-open-issues-apr7-analysis.md` (kailash-ml workspace) for full bug analysis.

### 5. PACT (`kailash-pact`)

**Primitives**: Envelopes, D/T/R addressing, vetting, vacancy, gradient
**Engine**: `GovernanceEngine` — thread-safe, fail-closed, write-time tightening
**Audit**: How does PACT consume Trust/EATP primitives (or vice versa — there was issue #63 about moving governance primitives into `kailash.trust.pact`)? How does kaizen-agents consume PACT? How does Nexus consume PACT for multi-tenant governance? Are envelope semantics consistent between Python and Rust?

### 6. Trust / EATP (`kailash[trust]`, `eatp` SDK)

**Primitives**: `BudgetTracker`, `PostureStore`, `AuditStore`, `ConstraintEnvelope`, `ConfidentialityLevel`, `ShadowEnforcer`
**Engine**: TrustPlane, AuditLogger with chain verification
**Audit**: This is the foundational governance layer. Every other framework should consume Trust primitives. Map the consumption graph. Identify where trust is duplicated or bypassed. Verify EATP D6 (cross-SDK semantic parity).

### 7. ML (`kailash-ml`)

**Primitives**: `FeatureStore`, `ModelRegistry`, `TrainingPipeline`, `PreprocessingPipeline`, `MetricSpec`
**Engines**: `AutoMLEngine`, `InferenceServer`, `DriftMonitor`, `DataExplorer`, `ExperimentTracker`
**Audit**: 14 files in `kailash-ml/engines/` with shared `_shared.py`. The architecture seems cleaner than kaizen — verify. Check polars-only invariant, agent guardrails (5 mandatory), ONNX bridge fallback, kailash-ml-protocols circular dependency resolution.

### 8. Align (`kailash-align`)

**Primitives**: `AlignmentConfig`, `AlignmentPipeline`, GGUF tools
**Engines**: `align.train()`, `align.deploy()` — Ollama, vLLM serving
**Audit**: Newest framework. Check that it doesn't repeat the kaizen/MCP fragmentation pattern. How does it consume Trust for budget tracking on training runs?

### 9. MCP (no package today)

**The biggest violation**: MCP is NOT a real package. There is no `packages/kailash-mcp/`. MCP code lives inline in 7+ different places:

- `src/kailash/mcp_server/` (used by BaseAgent — broken)
- `src/kailash/mcp/` (Rust-backed McpApplication, no transport)
- `src/kailash/api/mcp_integration.py` (in-process registry)
- `src/kailash/channels/mcp_channel.py` (Nexus channel)
- `src/kailash/trust/plane/mcp_server.py` (FastMCP standalone)
- `packages/kailash-nexus/src/nexus/mcp/server.py` (custom JSON server)
- `packages/kailash-nexus/src/nexus/mcp_websocket_server.py` (JSON-RPC bridge)
- `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (production-quality stdio client — used by Delegate)

The `mcp-platform-server` workspace consolidated SERVERS but explicitly KEPT two parallel CLIENT implementations. This workspace finishes the job.

## Cross-Framework Synergies to Audit

The platform's value comes from how frameworks compose. Each integration point is a potential primitive/engine violation:

| Consumer → Provider       | Integration Point              | Status                                        |
| ------------------------- | ------------------------------ | --------------------------------------------- |
| Kaizen agents → MCP       | Tool execution                 | **Broken** (#339)                             |
| Kaizen agents → Trust     | Budget tracking, posture       | Audit needed                                  |
| Kaizen agents → PACT      | Governance, vetting, clearance | Audit needed                                  |
| Kaizen agents → DataFlow  | AI-enhanced DB ops             | Audit needed                                  |
| Kaizen agents → ML        | ML tool integration via MCP    | Audit needed                                  |
| DataFlow → Trust          | Audit logging, classification  | Audit needed                                  |
| DataFlow → PACT           | Field-level governance         | Audit needed                                  |
| Nexus → MCP               | MCP channel                    | Duplicated impl                               |
| Nexus → Trust             | Auth, rate limiting, audit     | Audit needed                                  |
| Nexus → PACT              | Multi-tenant governance        | Audit needed                                  |
| PACT → Trust              | Envelope storage, audit        | Audit needed (#63 history)                    |
| ML → DataFlow             | Feature store backend          | Audit needed                                  |
| ML → Trust                | Agent guardrails, audit        | Audit needed                                  |
| ML → MCP                  | ML tools as MCP                | Audit needed                                  |
| Align → Trust             | Training run budgets           | Audit needed                                  |
| TrustPlane (server) → MCP | trust.\* tools                 | Already FastMCP — check primitive consumption |

## Out of Scope

- Rewriting any feature behavior. The primitive/engine convergence is purely architectural — public APIs preserve behavior, internal composition changes.
- The 8 ML feature issues (#341–#348) — independent feature additions, runs in parallel in `workspaces/kailash-ml/`.
- New framework features beyond what's needed to fix the architecture.
- Frontend (React/Flutter) work.
- Documentation updates beyond what the convergence requires.

## Hard Constraints

1. **Zero net regressions.** Every test that passes today must pass after the rework. Existing user code (Delegate facade calls, BaseAgent subclasses, multi-agent patterns, DataFlowEngine builders, NexusEngine apps, GovernanceEngine usage, TrainingPipeline, etc.) must work unchanged.

2. **No stubs, no bandaids, no parallel implementations.** Per zero-tolerance rules. If something is half-done, it gets finished. If something is duplicated, it gets unified.

3. **Cross-SDK semantic parity per EATP D6.** Whatever the Python side ends up with, the Rust side must mirror — same package boundaries, same primitive/engine separation, same composition graph. Audit kailash-rs in lockstep.

4. **Real package boundaries.** Primitives belong in dedicated packages with explicit `Cargo.toml` / `pyproject.toml` boundaries. No more "primitive code lives inside the engine package because it grew there organically."

5. **No new commercial references.** Per `rules/independence.md`, design for SDK users, not for any specific downstream consumer.

6. **Framework-first hierarchy is the law.** After this workspace, the hierarchy is:
   ```
   Specs → Primitives → Engines → Entrypoints
   ```
   And every consumer at layer N+1 actually composes layer N, never duplicates it.

## Success Criteria

A user can:

```python
# Single MCP client, used everywhere
from kailash_mcp import McpClient, McpServerConfig

# DataFlow engine actually composes DataFlow primitive
from kailash_dataflow import DataFlow, DataFlowEngine
df = DataFlow(...)
engine = DataFlowEngine.builder(df).build()  # composes, not duplicates

# Nexus engine composes Nexus primitive
from kailash_nexus import Nexus, NexusEngine
nexus = Nexus()
engine = NexusEngine(nexus).build()  # composes, not duplicates

# Delegate engine composes BaseAgent primitive
from kaizen_agents import Delegate
from kaizen import BaseAgent, Signature
delegate = Delegate(model=os.environ["LLM_MODEL"])
# Internally: delegate wraps a BaseAgent, reuses signatures, providers, MCP

# Cross-framework: Kaizen consumes Trust, PACT, DataFlow, MCP — all working
delegate = Delegate(
    model=os.environ["LLM_MODEL"],
    mcp_servers=[...],          # uses kailash-mcp
    budget_usd=10.0,            # uses Trust BudgetTracker
    governance_envelope=env,    # uses PACT envelope
    db=df,                      # uses DataFlow for tool data
)
result = await delegate.run(signature=MySig, query="...")
# Native function calls work, structured output parsed, budget tracked,
# envelope enforced, audit logged — all primitives composed cleanly
```

And the platform-wide invariants hold:

- `packages/kailash-mcp/` exists as a real primitive package
- `packages/kailash-trust/` (or `kailash[trust]` extras) is the only place trust primitives live
- Every "Engine" actually wraps the corresponding primitive — verified by `Engine` constructors taking the primitive as input
- No two packages contain implementations of the same MCP/provider/audit/envelope concept
- kailash-rs has the same package layout (within Rust crate idioms)

## Execution Model

This is **autonomous AI agent execution**. Per `rules/autonomous-execution.md`, no human-day estimates, maximum parallelization, frame trade-offs in terms of complexity and validation rigor.

This is a **multi-session workspace** — likely 6–10 autonomous execution sessions across analyze → todos → implement → redteam → codify. Significant work parallelizes across worktrees because each framework's refactor is largely independent (the cross-framework integration points are the dependent serialization).

## What Users Care About

In plain language (per `rules/communication.md`):

- **Today**: The Kailash platform has many great features, but using them together sometimes hits weird limitations because the underlying frameworks weren't built to compose cleanly. AI agents can break with MCP tools. Some DataFlow features can't be used with full governance. The frameworks each work well alone but cross-framework integration has rough edges.
- **After**: All features work together. The frameworks compose cleanly. You can mix and match — any combination of DataFlow + Nexus + Kaizen + PACT + Trust + ML works as expected. The platform feels like one product, not nine.
- **Cost**: Existing code keeps working. The internal plumbing gets rebuilt cleanly, but the public APIs stay stable.
