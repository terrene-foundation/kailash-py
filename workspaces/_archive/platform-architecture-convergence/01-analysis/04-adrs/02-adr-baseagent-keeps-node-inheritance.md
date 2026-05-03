# ADR-002: BaseAgent Keeps Node Inheritance

**Status**: ACCEPTED (2026-04-07)
**Scope**: Kaizen (kailash-kaizen)
**Deciders**: Platform Architecture Convergence workspace, user historical context 2026-04-07

## Context

Python's `BaseAgent` currently inherits from `kailash.nodes.base.Node`:

```python
# packages/kailash-kaizen/src/kaizen/core/base_agent.py:78
class BaseAgent(Node):
    ...
```

This inheritance was a deliberate decision made in the **n8n era** when agents were naturally workflow steps. The reasoning (per user context 2026-04-07):

> "kaizen started out as a node because we were in the n8n era where agents were (and still are) part of workflows, and it made sense to have baseagent inherit node and get all the capabilities of the sdk without rewriting anything."

This gave BaseAgent:

- Workflow composition capability (`get_parameters()`, `to_workflow()`)
- Node identity and configuration management
- Integration with Core SDK `WorkflowBuilder` and `LocalRuntime`
- Checkpoint recovery, audit hooks, parameter validation

### The shift since the n8n era

Two things changed the ground under BaseAgent's feet:

1. **Claude Code / Cursor / Codex changed what "AI agent" means.** Agents are no longer "run once, produce output, workflow advances." They're interactive, streaming, multi-turn, tool-calling loops where the LLM owns the control flow. The unit of work is a _session_, not a _node execution_.

2. **Token streaming became table stakes.** Users expect to see tokens arrive in real-time. That requires `AsyncGenerator` at every layer, which is fundamentally incompatible with `Node.run() -> Dict` because workflow graphs are batch-oriented by design.

This led to `Delegate` being built as a **parallel stack** in `packages/kaizen-agents/`, clean-slate, with the explicit architectural invariant in `delegate/loop.py:14-16`:

> "Architectural invariant: the kz core loop MUST NOT use Kaizen Pipeline primitives. Pipelines are for user-space application construction, not core orchestration."

### The trap

The red team's initial diagnosis was that BaseAgent's Node inheritance was **the problem** — it prevented streaming and created the split with Delegate. The red team proposed three options:

- **A**: BaseAgent drops Node inheritance (breaks 188 subclasses + workflow integration)
- **B**: BaseAgent grows a parallel `run_streaming()` path on itself
- **C**: Delegate is a sibling, not a facade

**All three options assume Node inheritance is incompatible with modern agents.** The kailash-rs audit proved this assumption wrong.

### What Rust does

Rust's `BaseAgent` is a minimal trait (2 methods). `Agent` implements it. `StreamingAgent` wraps `Agent` and emits events. Rust has **no Node inheritance** because Rust's Core SDK uses traits and the workflow integration happens via separate `AgentAsNode` adapters (not inheritance).

**Key insight**: Streaming and workflow composition are **orthogonal**. Rust solves it by having Agent NOT inherit anything workflow-related, and using explicit adapters to turn agents into nodes. Python could do the same, but it would break 188 subclasses and 600 tests.

**Better insight**: Python can have both. Streaming is added by a **wrapper**, not by modifying BaseAgent. BaseAgent stays Node-inheriting (workflow composition intact), and `StreamingAgent(inner_baseagent)` provides the streaming API. The two paths don't conflict because they're at different layers.

## Decision

**Python's `BaseAgent` will continue to inherit from `kailash.nodes.base.Node`. The n8n-era decision was correct and is preserved.**

Streaming is added via the `StreamingAgent` composition wrapper (see ADR-003), NOT by modifying BaseAgent's execution model. BaseAgent's `run() -> Dict[str, Any]` signature is preserved for workflow composition, multi-agent patterns that expect `Dict` returns, and the 188 existing subclasses.

```python
class BaseAgent(Node):
    """Workflow-composable agent primitive.

    Inherits from Node for workflow composition (to_workflow, get_parameters,
    NodeRegistry integration). n8n-era decision, preserved intentionally.

    For streaming / autonomous execution, use StreamingAgent wrapper:
        streaming = StreamingAgent(base_agent)
        async for event in streaming.run_stream(prompt):
            ...

    For cost tracking, use MonitoredAgent wrapper.
    For PACT governance, use L3GovernedAgent wrapper.
    For multi-agent coordination, use SupervisorAgent/WorkerAgent wrappers.
    """

    def run(self, **inputs) -> Dict[str, Any]:
        """Batch execution. Returns Dict for workflow compatibility."""
        ...

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Async batch execution. Returns Dict for Nexus/FastAPI."""
        ...

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Node interface — workflow parameter definitions."""
        ...

    def to_workflow(self) -> Workflow:
        """Node interface — convert agent to workflow."""
        ...
```

## Rationale

1. **Zero regressions for 188 subclasses.** Every existing subclass (ReActAgent, RAGResearchAgent, SupervisorAgent, WorkerAgent, ChainOfThoughtAgent, ModelSelectorAgent, DataScientistAgent, etc.) keeps working without modification.

2. **Workflow composition use case remains valid.** DataFlow pipelines that include agents as steps, Nexus workflow endpoints that invoke agents, batch ML inference that calls agents as part of a data pipeline — all these require the Node interface. Removing it would break significant real-world usage.

3. **~600 tests stay passing.** Most tests use BaseAgent's public API (`run()`, `run_async()`, `get_parameters()`, `to_workflow()`) which is unchanged.

4. **The multi-agent coordination patterns are composition-based.** They call `agent.run() -> Dict` — they don't need streaming. SupervisorWorker, Sequential, Parallel, Debate, Consensus, Handoff, Blackboard all work with the batch-Dict return type. No refactor needed.

5. **Streaming is a separate concern.** Users who want streaming wrap their BaseAgent in `StreamingAgent`. Users who want workflow composition use BaseAgent directly. Both use cases are first-class.

6. **The architectural invariant in `delegate/loop.py` is still respected.** AgentLoop / TAOD doesn't use workflow primitives — it's a separate execution path accessed via the StreamingAgent wrapper. The invariant becomes: "AgentLoop is a primitive that doesn't use workflow graphs. StreamingAgent wraps any BaseAgent and delegates to AgentLoop for autonomous streaming execution."

7. **Cross-SDK parity is preserved at the semantic level, not the literal structure.** Rust's BaseAgent trait doesn't inherit from anything Node-like because Rust uses traits. Python's BaseAgent inherits from Node for class-hierarchy reasons, but both exhibit the same composition-wrapper pattern at the BaseAgent layer. The two SDKs can't be byte-identical (Rust is trait-based, Python is class-based), but they're semantically aligned.

## Consequences

### Positive

- ✅ 188 subclasses keep working (zero net regressions per the brief)
- ✅ ~600 tests keep passing without migration (most of them)
- ✅ Workflow composition via `BaseAgent.to_workflow()` stays working
- ✅ DataFlow / Nexus / ML / Align agent usage unchanged
- ✅ Multi-agent patterns (SupervisorWorker, Sequential, etc.) need no API changes
- ✅ Streaming becomes a capability added by a wrapper, not a core requirement
- ✅ The n8n-era architectural decision is validated retroactively — it was correct

### Negative

- ❌ Python's BaseAgent stays slightly more complex than Rust's trait (inherits Node, has `get_parameters()` / `to_workflow()` methods that Rust doesn't have)
- ❌ The two SDKs aren't structurally identical — Python has Node inheritance, Rust uses traits + AgentAsNode adapter
- ❌ Users reading the docs need to understand: "BaseAgent is Node-composable, StreamingAgent is stream-composable, both are primitives"

### Neutral

- Node inheritance overhead is small in practice — `Node.__init__()` does parameter validation and registry setup, which is cheap
- The `to_workflow()` method is opt-in — streaming agents just don't call it

## Alternatives Considered

### Alternative 1: Drop Node inheritance (red team's Option A)

**Rejected**. Would break:

- 188 subclasses (all inherit from `BaseAgent(Node)`)
- ~600 tests (many of which use Node interface indirectly)
- `BaseAgent.to_workflow()` (fundamental workflow integration)
- DataFlow agent nodes (they assume BaseAgent is Node-composable)
- Nexus agent endpoints (register via `nexus.add_workflow(agent.to_workflow())`)
- ML agents that run in batch pipelines
- Align agents

Would require a complete rewrite of the kaizen → kailash integration story. User's constraint is "zero net regressions."

### Alternative 2: Grow a parallel `run_streaming()` method on BaseAgent (red team's Option B)

**Rejected**. This was the original "option B" in the red team's 3-choice framing. It would add a second execution path directly on BaseAgent, doubling the surface area of the class. Worse, it would force every subclass to potentially implement streaming, even if they don't need it.

The better version of Option B is what this ADR adopts: add streaming as a **separate wrapper class** (`StreamingAgent`), not as a method on BaseAgent itself.

### Alternative 3: Delegate is a sibling, not a facade (red team's Option C)

**Superseded**. Originally proposed in the red team's Option C framing. This ADR and ADR-007 combined supersede it with a better framing: Delegate IS a composition facade, but what it composes is `BaseAgent` (Node-inheriting, batch) plus wrappers (`StreamingAgent`, `MonitoredAgent`, `L3GovernedAgent`). The red team's Option C was half right — the half that was wrong was assuming Delegate couldn't wrap BaseAgent due to Node inheritance. With wrappers, it can.

### Alternative 4: Two separate agent primitives — `WorkflowAgent(Node)` and `AutonomousAgent` (no Node)

**Rejected**. Creates two concept names for similar things. Users would constantly ask "which one do I use?" The composition-wrapper pattern (this ADR) achieves the same outcome with one primitive name.

## Implementation Notes

1. **BaseAgent's Node inheritance is preserved verbatim.** No changes to `class BaseAgent(Node):` declaration.

2. **The 7 extension points are still deprecated** (per ADR-001). Node inheritance and extension-point deprecation are independent decisions.

3. **`to_workflow()` stays** as a public method on BaseAgent. Wrappers (StreamingAgent, MonitoredAgent, L3GovernedAgent) do NOT implement `to_workflow()` — they're meant for autonomous execution, not workflow composition. If a user wants a wrapped agent inside a workflow, they construct `agent.to_workflow()` from the inner BaseAgent directly.

4. **Rust's AgentAsNode adapter pattern** is documented but not ported. Python doesn't need it because BaseAgent IS a Node.

5. **`rules/patterns.md` guidance stays**: "Delegate (recommended for autonomous agents). BaseAgent (for custom logic only)." After this ADR, the guidance becomes slightly richer: "BaseAgent (for workflow-composable agents). StreamingAgent(BaseAgent) or Delegate (for autonomous/streaming agents)."

## Related ADRs

- **ADR-001**: Composition over extension points (BaseAgent's class shape)
- **ADR-003**: Streaming as wrapper primitive (how streaming works without modifying BaseAgent)
- **ADR-007**: Delegate as composition facade (how Delegate composes BaseAgent + wrappers)

## Related Research

- `01-research/07-baseagent-audit.md` — Python BaseAgent surface area
- `01-research/08-delegate-audit.md` — Why Delegate was built parallel (the invariant)
- `02-rs-research/07-rs-agents-audit.md` — Rust's 2-method BaseAgent trait
