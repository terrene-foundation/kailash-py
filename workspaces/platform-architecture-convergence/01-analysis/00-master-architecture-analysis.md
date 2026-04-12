# Platform Architecture Convergence — Master Analysis

**Date**: 2026-04-07 (rewritten)
**Status**: Analysis complete. All red team R1 findings resolved. Ready for /todos.
**Workspace**: `workspaces/platform-architecture-convergence/`

---

## 1. Executive Summary

The Kailash platform has nine frameworks (Core SDK, DataFlow, Nexus, Kaizen, PACT, Trust/EATP, ML, Align, MCP) that each work well individually, but cross-framework integration has rough edges because internal plumbing was built in parallel rather than composed from shared building blocks. This workspace audits the entire platform, makes 10 architectural decisions (ADR-001 through ADR-010), and defines 10 implementation specifications (SPEC-01 through SPEC-10) to converge the platform into a single cohesive architecture. The result: all features work together, the frameworks compose cleanly, and the platform feels like one product, not nine.

The convergence thesis is straightforward. Six of the nine frameworks already follow the correct pattern: engines compose primitives. Three areas (Kaizen agents, MCP protocol, LLM providers) grew parallel implementations instead of composing shared primitives. This workspace unifies those three areas, consolidates trust-related duplication in Nexus and Core SDK, and ensures both Python and Rust SDKs stay aligned.

## 2. The Problem

### Framework-first hierarchy

The Kailash platform follows a strict layering rule:

```
Specs  -->  Primitives  -->  Engines  -->  Entrypoints
```

Each layer composes the one below it. An engine wraps a primitive, not a copy of a primitive. This hierarchy holds in six frameworks but is violated in three.

### Where it works (no changes needed)

| Framework    | Why it works                                                                        |
| ------------ | ----------------------------------------------------------------------------------- |
| DataFlow     | `DataFlowEngine` takes `DataFlow` as a required constructor parameter. Composition. |
| PACT         | Primitives in `kailash.trust.pact`, engine in `kailash-pact`. Clean delegation.     |
| ML           | 4 primitives + 10 engines, constructor injection, no fragmentation.                 |
| Align        | Registry pattern, fully isolated, no duplication.                                   |
| Core SDK     | Zero hard dependencies on external frameworks.                                      |
| Nexus engine | `NexusEngine` takes `Nexus` as required parameter.                                  |

### Where it is broken (refactor scope)

**Kaizen: two parallel agent stacks.** BaseAgent (3,698 lines, 188 subclasses) has structured outputs and 7 extension points but broken MCP. Delegate (separate package, separate loop, separate provider adapters, separate MCP client) has working MCP and streaming but no structured outputs. Users must choose half the platform.

**MCP: phantom package.** There is no `packages/kailash-mcp/` directory. MCP code is scattered across 27+ files in 7+ locations. Two parallel client implementations exist (1,288-line `MCPClient` used by BaseAgent, 509-line `McpClient` used by Delegate). The prior `mcp-platform-server` workspace consolidated servers 85% but explicitly kept both clients.

**LLM providers: two parallel layers.** A 5,001-line monolith (`ai_providers.py`) serves BaseAgent with 14 providers, structured outputs, and embeddings. A separate set of clean per-provider adapters serves Delegate with 4 providers and real streaming. Each stack has features the other lacks.

**Additional violations:**

| Area                     | Issue                                                                  | Severity |
| ------------------------ | ---------------------------------------------------------------------- | -------- |
| Nexus auth/audit         | Duplicates `kailash.trust` instead of consuming it. Zero imports.      | Medium   |
| Nexus PACT integration   | Missing entirely.                                                      | Medium   |
| Core SDK audit stores    | 5+ audit implementations scattered across submodules.                  | Medium   |
| ConstraintEnvelope       | 3 incompatible types across chain, plane, and pact. EATP D6 violation. | Medium   |
| Trust integration wiring | BudgetTracker, PostureStore exist but are not auto-wired.              | Low      |

### Root cause

Engines were built clean-slate when they should have been built by composing primitives. Delegate was built from scratch because BaseAgent's Node inheritance seemed incompatible with streaming. MCP code grew inline because there was no package boundary enforcing "one MCP module." Nexus auth was built before `kailash.trust` existed. The 5,001-line provider monolith was never extracted, so Delegate built its own adapters.

## 3. Architectural Decisions (Decision Chain)

Ten ADRs form a dependency chain that resolves every identified problem. The chain flows from the foundational decision (how agents are built) through package extraction and consolidation to the governance process for cross-SDK coordination.

### Decision chain

```
ADR-002 (BaseAgent keeps Node)
   |
ADR-001 (Composition over extension points)
   |
ADR-003 (Streaming as wrapper)        ADR-007 (Delegate as facade)
         |                                    |
         +---------> ADR-004 (kailash-mcp)  <-+
                        |
                  ADR-005 (Provider split)
                        |
                  ADR-006 (ConstraintEnvelope)
                        |
                  ADR-010 (CO Five Layers mapping)
                        |
                  ADR-008 (Cross-SDK lockstep)
                        |
                  ADR-009 (Backward compat strategy)
```

### The three foundational decisions

**ADR-001: Composition over extension points.** BaseAgent's 7 extension points (override hooks for signatures, strategy, system prompts, validation, pre/post execution, error handling) are replaced by composition wrappers. Instead of subclassing to add a capability, users wrap an agent with a wrapper that adds that capability. Wrappers stack: `StreamingAgent(MonitoredAgent(L3GovernedAgent(BaseAgent(...))))`. This matches Rust's existing pattern exactly. The 7 extension points are deprecated in v2.x and removed in v3.0.

**ADR-002: BaseAgent keeps Node inheritance.** The red team initially diagnosed Node inheritance as the root problem preventing streaming. The Rust audit proved this wrong. Streaming and workflow composition are orthogonal concerns. BaseAgent stays as `BaseAgent(Node)` — preserving workflow composition for 188 subclasses and 600 tests. Streaming is added via a wrapper, not by modifying BaseAgent.

**ADR-010: CO Five Layers to agent runtime mapping.** The CO (Cognitive Orchestration) Five Layers (Intent, Context, Guardrails, Instructions, Learning) map directly to the convergence architecture. Each layer is owned by a specific component. The key new concept is posture-aware instruction enforcement: the same `signature=` parameter works for both tool agents (strict validation, reject on missing fields) and autonomous agents (soft validation, use judgment), with enforcement level determined by the agent's posture. AgentPosture (PSEUDO, TOOL, SUPERVISED, AUTONOMOUS, DELEGATING) lives in `kailash.trust.posture` and is referenced by ConstraintEnvelope via a new `posture_ceiling` field.

### All 10 ADRs summarized

| ADR | Decision                            | Key consequence                                                                                                                               |
| --- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 001 | Composition over extension points   | 7 BaseAgent hooks deprecated; capabilities added via stackable wrappers                                                                       |
| 002 | BaseAgent keeps Node inheritance    | 188 subclasses and 600 tests unaffected; workflow composition preserved                                                                       |
| 003 | Streaming as wrapper primitive      | `StreamingAgent` wraps any `BaseAgent`; uses internal `AgentLoop` for TAOD                                                                    |
| 004 | kailash-mcp package boundary        | Real `packages/kailash-mcp/` with one client, one server base, canonical JSON-RPC types                                                       |
| 005 | Provider capability protocol split  | Narrow protocols (`LLMProvider`, `StreamingProvider`, `EmbeddingProvider`, etc.) replace single fat interface; no stub methods                |
| 006 | Single canonical ConstraintEnvelope | One frozen dataclass with NaN protection, monotonic tightening, optional signing; 3 old types become aliases                                  |
| 007 | Delegate as composition facade      | Delegate internally composes `BaseAgent` + wrappers; parallel stack eliminated; users get streaming + structured outputs + MCP simultaneously |
| 008 | Cross-SDK lockstep convergence      | Canonical spec documents govern both SDKs; matched GitHub issues; interop test vectors                                                        |
| 009 | Backward compatibility strategy     | Deprecation shims live for 2 minor versions; removal in v3.0; 4-layer compat mechanism                                                        |
| 010 | CO Five Layers to agent runtime     | Posture-aware instruction enforcement; guardrails invariant across spectrum; `posture_ceiling` on envelope                                    |

## 4. Composition-Wrapper Pattern

The composition-wrapper pattern is the central architectural resolution. It resolves the red team's critical finding that the original convergence target was self-contradicting (claiming BaseAgent would gain streaming while also stating Node inheritance makes streaming structurally impossible).

### How it works

Every agent capability beyond the minimal contract is added by wrapping the agent in a wrapper class. Each wrapper implements `BaseAgent`, so wrappers can be nested. The inner agent does not know it is wrapped. The wrapper adds one concern (cost tracking, governance, streaming, supervision, worker status) and delegates everything else to the inner agent.

### The wrapper stack

```python
# Innermost: the primitive agent
agent = BaseAgent(config=cfg, signature=MySig, tools=[...])

# Add cost tracking (via kailash.trust.BudgetTracker)
agent = MonitoredAgent(agent, budget_usd=10.0)

# Add PACT governance (via ConstraintEnvelope)
agent = L3GovernedAgent(agent, envelope=my_envelope)

# Add streaming (outermost — provides run_stream() API)
agent = StreamingAgent(agent)

# Use it
async for event in agent.run_stream(query="..."):
    match event:
        case TextDelta(text=t): print(t, end="")
        case TurnComplete(structured=result): handle(result)
```

### Five composition wrappers

| Wrapper           | Adds                                             | Corresponds to (Rust)            |
| ----------------- | ------------------------------------------------ | -------------------------------- |
| `StreamingAgent`  | Token streaming via internal AgentLoop (TAOD)    | `streaming::StreamingAgent`      |
| `MonitoredAgent`  | Cost tracking via `kailash.trust.BudgetTracker`  | `cost::MonitoredAgent`           |
| `L3GovernedAgent` | PACT envelope enforcement, verification gradient | `l3_runtime::L3GovernedAgent`    |
| `SupervisorAgent` | Multi-agent routing with worker selection        | `orchestration::SupervisorAgent` |
| `WorkerAgent`     | Worker status tracking, capability declaration   | `orchestration::WorkerAgent`     |

### How Delegate composes the stack

Delegate becomes a thin facade. Its constructor builds a wrapper stack based on what the user configures:

```python
class Delegate:
    def __init__(self, model, *, signature=None, tools=None,
                 mcp_servers=None, budget_usd=None, envelope=None, ...):
        # Build the core agent
        core = BaseAgent(config=..., signature=signature, tools=tools)
        if mcp_servers:
            core.configure_mcp(mcp_servers)

        # Stack wrappers based on configuration
        current = core
        if budget_usd is not None:
            current = MonitoredAgent(current, budget_usd=budget_usd)
        if envelope is not None:
            current = L3GovernedAgent(current, envelope=envelope)

        # Streaming is always outermost
        self._streaming = StreamingAgent(current)

    async def run(self, prompt=None, **inputs):
        async for event in self._streaming.run_stream(**inputs):
            yield event
```

The user-facing API is unchanged. Internally, the parallel stack (separate loop, separate adapters, separate MCP client, separate tool registry) is eliminated. Delegate users now get structured outputs (via signature on the inner BaseAgent), working MCP (via shared `kailash_mcp.MCPClient`), cost tracking, and PACT governance — all at once.

## 5. CO Five Layers to Agent Runtime Mapping

ADR-010 maps the CO (Cognitive Orchestration) Five Layers onto the convergence architecture. This mapping is canonical for both Python and Rust.

### Layer ownership

| CO Layer         | What it governs                     | Owned by                                                                                                                                          |
| ---------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Intent**       | What the agent is trying to achieve | `BaseAgent(signature=...)` — InputField defines the ask, OutputField defines the deliverable                                                      |
| **Context**      | What the agent knows                | `BaseAgent._memory`, `BaseAgent._tools`, `MCPClient` resources; `L3GovernedAgent` filters by classification ceiling                               |
| **Guardrails**   | What the agent must not do          | `L3GovernedAgent(envelope=...)` for hard walls (5D constraint envelope, never-delegated actions); `MonitoredAgent(budget_usd=...)` for soft walls |
| **Instructions** | What the agent should do            | `BaseAgent(system_prompt=..., signature=...)` + posture-aware enforcement via `StructuredOutput`                                                  |
| **Learning**     | What the agent has learned          | `MonitoredAgent` metrics, `PostureStore` evidence, TrustPlane `DecisionRecord` traces                                                             |

### Posture-aware instruction enforcement

The same `signature=` parameter drives both tool agents and autonomous agents. The difference is how strictly the output schema is enforced:

| Posture            | Schema enforcement  | Behavior on missing fields                   |
| ------------------ | ------------------- | -------------------------------------------- |
| TOOL (L1-L2)       | Strict validation   | Reject. `SignatureValidationError`.          |
| SUPERVISED (L3)    | Moderate validation | Warn, retry with correction prompt.          |
| AUTONOMOUS (L4-L5) | Soft validation     | Accept partial result, note what is missing. |

This means a product manager edits one field (`signature`) to control what an agent outputs. The enforcement level comes from the agent's posture in its PACT envelope — not from a separate "strict vs soft" configuration.

### Guardrails invariance

Guardrails do not soften with higher autonomy. An operating envelope blocks an L5 delegating agent exactly as hard as an L1 tool agent. This is PACT principle P1 (envelope is recursive) enforced through the verification gradient (AUTO_APPROVED, FLAGGED, HELD, BLOCKED).

### AgentPosture and posture_ceiling

`AgentPosture` is an enum in `kailash.trust.posture`:

```
PSEUDO      (L1) — Not a real agent; direct API call
TOOL        (L2) — Deterministic invocation
SUPERVISED  (L3) — Agent with human oversight
AUTONOMOUS  (L4) — Independent within envelope
DELEGATING  (L5) — Can delegate to other agents
```

`ConstraintEnvelope` gains a `posture_ceiling: Optional[AgentPosture]` field. A supervisor can delegate a task at a lower posture than their own, but never higher. This enforces the principle that autonomy can only narrow during delegation.

## 6. Implementation Plan

The 10 SPECs are organized into 6 phases with explicit dependencies. Phases within a group can run in parallel; phases across groups are sequential.

### Phase 1: Foundation extraction

**SPEC-01** — Extract `kailash-mcp` package. Creates `packages/kailash-mcp/` with one client, one server base, canonical JSON-RPC types, unified transports, auth, discovery. Backward-compat shims at old import paths. This unblocks everything else because every framework consumes MCP.

### Phase 2: Shared primitives (parallel)

- **SPEC-02** — Provider layer. Split the 5,001-line monolith into per-provider modules with capability protocols. Both BaseAgent and Delegate consume the same providers.
- **SPEC-07** — ConstraintEnvelope unification. Define ONE canonical type with NaN protection, monotonic tightening, and optional signing. Three old types become aliases.

### Phase 3: BaseAgent + wrappers (sequential after Phase 2)

- **SPEC-03** — Composition wrappers. Create `StreamingAgent`, `MonitoredAgent`, `L3GovernedAgent`, `SupervisorAgent`, `WorkerAgent`.
- **SPEC-04** — BaseAgent slimming. Add `posture` to config, deprecate 7 extension points, move AgentLoop to `kaizen.core`.

### Phase 4: Engine facade + patterns (sequential after Phase 3)

- **SPEC-05** — Delegate engine facade. Rewrite Delegate as composition of BaseAgent + wrappers. Delete parallel loop, adapters, MCP client.
- **SPEC-10** — Multi-agent patterns migration. Verify all 7 coordination patterns (SupervisorWorker, Sequential, Parallel, Debate, Consensus, Handoff, Blackboard) work with the slimmed BaseAgent and wrappers.

### Phase 5: Nexus + Core SDK cleanup (parallel)

- **SPEC-06** — Nexus auth/audit migration. Migrate JWT, RBAC, SSO, rate limiting, audit to consume `kailash.trust`. Add `PACTMiddleware`.
- **SPEC-08** — Core SDK consolidation. Unify 5+ audit implementations into `trust.audit_store`. Wire BudgetTracker into LocalRuntime.

### Phase 6: Cross-SDK lockstep

- **SPEC-09** — Cross-SDK parity. Validate all canonical type mappings, run interop test vectors, file matched issues on both repos.

### Dependency graph

```
Phase 1:  SPEC-01 (MCP)
              |
Phase 2:  SPEC-02 (Providers)  ||  SPEC-07 (Envelope)
              |                        |
Phase 3:  SPEC-03 (Wrappers)  ----  SPEC-04 (BaseAgent slim)
              |                        |
Phase 4:  SPEC-05 (Delegate)  ----  SPEC-10 (Multi-agent)
              |
Phase 5:  SPEC-06 (Nexus)  ||  SPEC-08 (Core SDK)
              |
Phase 6:  SPEC-09 (Cross-SDK)
```

`||` means parallel. `----` means co-dependent within the same phase.

### Parallelization opportunities

- SPEC-02 and SPEC-07 run in parallel (no dependency between provider split and envelope unification).
- SPEC-06 and SPEC-08 run in parallel (Nexus migration and Core SDK consolidation are independent).
- SPEC-09 (cross-SDK validation) can begin its spec-writing and issue-filing work during earlier phases.

## 7. Cross-SDK Convergence Design

### Dual-model-with-shared-primitives

Python and Rust are semantically aligned but structurally different. Python uses class inheritance (`BaseAgent(Node)`). Rust uses traits (`BaseAgent` trait + `AgentAsNode` adapter). The convergence does not try to make the two SDKs byte-identical in code. Instead, both implement the same canonical spec documents independently, and interop test vectors verify wire-level equivalence.

### Canonical type mappings

| Concept             | Python                                                 | Rust                                                       |
| ------------------- | ------------------------------------------------------ | ---------------------------------------------------------- |
| MCP package         | `kailash_mcp`                                          | `kailash_mcp` crate                                        |
| JSON-RPC types      | `kailash_mcp.protocol.JsonRpc{Request,Response,Error}` | `kailash_mcp::protocol::JsonRpc{Request,Response,Error}`   |
| Agent contract      | `kaizen.core.BaseAgent(Node)`                          | `kailash_kaizen::agent::BaseAgent` trait                   |
| Streaming wrapper   | `kaizen_agents.StreamingAgent`                         | `kaizen_agents::streaming::StreamingAgent`                 |
| Engine facade       | `kaizen_agents.Delegate`                               | `kaizen_agents::delegate_engine::DelegateEngine`           |
| TAOD loop           | `kaizen.core.AgentLoop`                                | `kaizen_agents::agent_engine::TaodRunner`                  |
| Constraint envelope | `kailash.trust.ConstraintEnvelope` (frozen dataclass)  | `eatp::constraints::ConstraintEnvelope` (struct)           |
| Agent posture       | `kailash.trust.posture.AgentPosture` (IntEnum)         | `kailash_kaizen::types::ExecutionMode` (expand to posture) |
| Streaming events    | `DelegateEvent` hierarchy (Python dataclasses)         | `CallerEvent` enum (Rust)                                  |
| Provider protocols  | `LLMProvider`, `StreamingProvider`, etc. (Protocols)   | `Chat`, `Streaming`, `Embeddings` (traits)                 |

### Gaps requiring Rust changes

| Gap                                          | Python status     | Rust action needed                                                        |
| -------------------------------------------- | ----------------- | ------------------------------------------------------------------------- |
| `kailash-mcp` crate                          | SPEC-01           | Create `crates/kailash-mcp/`, move kaizen MCP client, extract server base |
| Provider capability split                    | SPEC-02           | Add `Chat`, `Streaming`, `Embeddings` traits                              |
| AgentPosture / posture-aware validation      | ADR-010           | Expand `ExecutionMode` to full posture spectrum                           |
| `posture_ceiling` on ConstraintEnvelope      | SPEC-07           | Add field to `eatp::constraints::ConstraintEnvelope`                      |
| Reasoning model parameter filtering          | SPEC-02           | Apply `max_completion_tokens` + strip temperature for o1/o3/o4            |
| MCP executor stub                            | rs-mcp audit      | Replace simulated execution with real calls                               |
| kz MCP bridge stub                           | rs-mcp audit      | Wire to `kailash_mcp::client::McpClient`                                  |
| Missing providers (Ollama, Cohere, HF, etc.) | Already in Python | Add adapters to `kailash-kaizen/src/llm/`                                 |

### ADR-008 lockstep process

Every cross-SDK change follows the same protocol:

1. Write a canonical spec document first (wire types, semantics, test vectors).
2. File matched GitHub issues on both repos with `cross-sdk` label.
3. Each SDK implements against the spec independently — not against the other SDK's code.
4. Interop test vectors validate round-trip equivalence.
5. Release in matched minor versions with cross-referenced release notes.

### What kailash-rs needs to start

The Rust team can begin their analysis with the 7 Rust research files (`01-analysis/02-rs-research/01` through `07`) and the 10 SPEC documents. Their implementation order mirrors Python's: SPEC-01 (MCP crate) first, then provider traits, then agent wrappers. The canonical specs ensure both SDKs converge to the same target without waiting for each other.

## 8. Risk Analysis

### Red team round 1 findings (all resolved)

The red team identified 7 critical gaps and 7 major risks. All critical gaps have been resolved through ADRs:

| R1 finding                                                                    | Resolution                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Composition target self-contradicts (BaseAgent can't stream AND inherit Node) | ADR-002 + ADR-003: streaming is a wrapper, not a BaseAgent method. Node inheritance preserved.                                                                                                                            |
| Architectural invariant violated or moved                                     | ADR-003: AgentLoop moves to `kaizen.core.agent_loop`. Invariant rewritten: "AgentLoop MUST NOT use workflow primitives (WorkflowBuilder, LocalRuntime)."                                                                  |
| Public API breaks silently                                                    | ADR-009: 4-layer backward compat. `Delegate.run()` returns `AsyncGenerator[DelegateEvent]` (unchanged). `BaseAgent.run()` returns `Dict` (unchanged). `StreamingAgent.run()` returns `Dict` (wrapper preserves contract). |
| "No consumers" claim for `api/mcp_integration.py` unverified                  | Exhaustive grep across all directories confirmed zero import consumers. Safe to delete.                                                                                                                                   |
| 3 ConstraintEnvelopes not semantically equivalent                             | ADR-006 + SPEC-07: field-by-field semantic diff completed. Canonical type adopts the strictest invariants from all three.                                                                                                 |
| Nexus migration assumes trust has Nexus capabilities                          | SPEC-06: per-capability matrix created. Some Nexus features (SSO, Redis rate limiting, hierarchical RBAC caching) must be extracted INTO trust first, not consumed from it.                                               |
| Provider interface forces stubs                                               | ADR-005: capability protocol split. Providers implement only the protocols they support. No stub methods.                                                                                                                 |

### Backward compatibility risks

| Change                                | Risk                                                    | Mitigation (ADR-009)                                                        |
| ------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------- |
| MCP import paths move                 | Thousands of `from kailash.mcp_server import ...` sites | Re-export shims at old paths, DeprecationWarning, removal in v3.0           |
| BaseAgent extension points deprecated | 188 subclasses, ~600 tests                              | `@deprecated` decorator on all 7 hooks; hooks still work in v2.x            |
| ConstraintEnvelope types unified      | 3 types in production use                               | Class aliases that subclass canonical type; `isinstance()` checks preserved |
| Delegate internals rewritten          | Test suites reference internal modules                  | Backward-compat shim at `kaizen_agents.delegate.*` subpackage               |
| Provider monolith split               | Direct imports from `ai_providers.py`                   | Re-export shim with class aliases                                           |

### Migration complexity by framework

| Framework                     | Scope   | Complexity | Notes                                                                        |
| ----------------------------- | ------- | ---------- | ---------------------------------------------------------------------------- |
| Kaizen (BaseAgent + Delegate) | Highest | High       | 188 subclasses, parallel stack elimination, wrapper creation                 |
| MCP                           | High    | Medium     | Package extraction is mechanical; client unification is the real work        |
| LLM Providers                 | High    | Medium     | Monolith split is refactoring; capability protocol design is the design work |
| Nexus auth                    | Medium  | Medium     | Some features must be built in trust before Nexus can consume them           |
| Core SDK audit                | Medium  | Low        | Consolidation of existing implementations                                    |
| ConstraintEnvelope            | Medium  | Medium     | Behavioral merge, not a rename; field-by-field semantic diff required        |

## 9. Success Criteria

After this workspace completes, these outcomes are measurable and verifiable.

### User-facing outcomes

- All features work together. A single `Delegate(...)` call can use streaming, structured outputs, MCP tools, budget tracking, and PACT governance simultaneously.
- `packages/kailash-mcp/` exists as a real package installable via `pip install kailash-mcp`.
- Every engine's constructor takes its corresponding primitive as input, verified by inspection.
- No two packages contain implementations of the same MCP/provider/audit/envelope concept.

### Test verification

- [ ] Every test that passes today passes after the rework (zero net regressions)
- [ ] New composition tests verify wrapper stacking (streaming + budget + governance + structured output)
- [ ] Cross-SDK interop test vectors pass in both Python and Rust CI
- [ ] `ConstraintEnvelope` round-trip tests pass between SDKs
- [ ] JsonRpcRequest/Response round-trip tests pass between SDKs
- [ ] All deprecated import paths emit `DeprecationWarning` with correct replacement guidance

### Architectural verification

- [ ] `packages/kailash-mcp/` contains the single MCP client and server base
- [ ] `kaizen/providers/` contains per-provider modules with capability protocols
- [ ] `BaseAgent` is under 1,000 lines (down from 3,698)
- [ ] Delegate has zero internal provider adapters, zero internal MCP client, zero internal AgentLoop
- [ ] Nexus has zero internal JWT/RBAC/SSO/audit/rate-limiter implementations (consumes `kailash.trust`)
- [ ] One canonical `ConstraintEnvelope` type in `kailash.trust.envelope`
- [ ] `AgentPosture` enum exists in `kailash.trust.posture`
- [ ] `posture_ceiling` field exists on `ConstraintEnvelope`
- [ ] kailash-rs has the same package layout (within Rust crate idioms)

### Cross-SDK verification

- [ ] Matched `cross-sdk` issues filed on both repos for every convergence change
- [ ] Canonical spec documents exist for all 10 SPECs
- [ ] Interop test vectors defined and passing
- [ ] Release notes cross-reference matched releases

## Reference Documents

### ADRs (decisions)

`01-analysis/04-adrs/01-adr-*.md` through `10-adr-*.md` — 10 architectural decisions forming the decision chain.

### SPECs (implementation contracts)

`01-analysis/03-specs/01-spec-*.md` through `10-spec-*.md` — 10 implementation specifications, each the canonical source of truth for both SDKs.

### Research (evidence base)

`01-analysis/01-research/` — 11 Python research files covering every framework audit.
`01-analysis/02-rs-research/` — 7 Rust research files covering cross-SDK comparison.

### Red team

`01-analysis/02-red-team-r1.md` — Round 1 findings and verdict (GO WITH CHANGES). All critical gaps resolved through ADRs.

### Brief

`briefs/00-overview.md` — Workspace scope, hard constraints, success criteria.
