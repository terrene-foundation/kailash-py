# ADR-001: Composition Over Extension Points

**Status**: ACCEPTED (2026-04-07)
**Scope**: Kaizen (kailash-kaizen, kaizen-agents)
**Deciders**: Platform Architecture Convergence workspace, user decision 2026-04-07 ("Option B please")

## Context

Python's `BaseAgent(Node)` in `packages/kailash-kaizen/src/kaizen/core/base_agent.py` is 3,698 lines and exposes **7 extension points** that subclasses override to add capabilities:

1. `_default_signature()` — provide agent-specific I/O schema
2. `_default_strategy()` — select execution strategy (SingleShot/MultiCycle)
3. `_generate_system_prompt()` — customize LLM system prompt with MCP tool docs
4. `_validate_signature_output()` — validate LLM output against schema
5. `_pre_execution_hook()` — custom logic before execution
6. `_post_execution_hook()` — custom logic after execution
7. `_handle_error()` — custom error handling and recovery

**188 subclasses** across the monorepo (kaizen-agents specialized agents, multi-agent coordination patterns, kailash-align agents, kailash-ml agents, examples, tests) use these extension points. Approximately 600 tests exercise the BaseAgent surface.

Rust's equivalent, `kailash-kaizen/src/agent/mod.rs`, exposes a **2-method trait**:

```rust
#[async_trait]
pub trait BaseAgent: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError>;
    async fn run_with_memory(&self, input: &str, shared_memory: Arc<dyn AgentMemory>)
        -> Result<AgentResult, AgentError>;
}
```

Zero extension points. All capabilities are added via **composition wrappers** (`MonitoredAgent`, `StreamingAgent`, `L3GovernedAgent`, `SupervisorAgent`, `WorkerAgent`) that each implement the same `BaseAgent` trait and wrap another `BaseAgent`.

### Problems with the Python extension-point model

1. **Capability fragmentation** — Different subclasses override different points inconsistently. Hard to reason about which agents have which capabilities.
2. **Hooks system is fragile** — `executor.submit(asyncio.run(...))` violates async/sync boundaries in the hook system.
3. **Permission system is advisory** — `budget_warnings` don't actually block execution because permission checks happen in an extension point that subclasses may not call.
4. **MCP integration is rotted** — bug #339 (4 sub-issues) stems from `_execute_regular_tool()` being an extension point stub that never got implemented.
5. **Signature validation is opt-in** — `_validate_signature_output()` is an extension point, not automatic. Most subclasses don't override it, so output validation is silently absent.
6. **Violates `rules/agent-reasoning.md`** — extension points let code override LLM decisions, which is the opposite of the LLM-first principle. A subclass that overrides `_default_strategy()` is doing code-based routing; a subclass that overrides `_generate_system_prompt()` is doing prompt engineering outside the agent's reasoning path.
7. **Inheritance limit** — a subclass can only inherit once. If you want both cost tracking AND streaming AND governance, you can't combine three subclasses; you have to build one mega-subclass that hardcodes all three.

## Decision

**Python's `BaseAgent` will be slimmed to match Rust's minimal trait-like contract. All capabilities will be added via composition wrappers that each implement `BaseAgent` and wrap another `BaseAgent`. The 7 extension points will be deprecated in v2.x and removed in v3.0.**

New contract (Python):

```python
class BaseAgent(Node):
    """Minimal primitive contract for Kaizen agents.

    Composes: LlmClient + ToolRegistry + AgentMemory + StructuredOutput + Signature.
    All capabilities beyond the minimal contract are added via composition wrappers
    (StreamingAgent, MonitoredAgent, L3GovernedAgent, SupervisorAgent, WorkerAgent).

    The 7 extension points (v1/v2) are deprecated:
    - _default_signature() → pass signature= parameter instead
    - _default_strategy() → use config.execution_mode or wrap in an execution wrapper
    - _generate_system_prompt() → pass system_prompt= parameter instead
    - _validate_signature_output() → signature validation is automatic
    - _pre_execution_hook() → wrap with a PreExecutionWrapper or use hook system
    - _post_execution_hook() → wrap with a PostExecutionWrapper or use hook system
    - _handle_error() → wrap with an ErrorHandlerWrapper
    """

    # Required: Node inheritance preserved for workflow composition (see ADR-002)
    # Required: name, description attributes
    # Required: run() returning Dict[str, Any] for workflow compatibility
    # Required: run_async() returning Dict[str, Any] for Nexus/FastAPI

    def __init__(self, config, *, signature=None, llm=None, tools=None, memory=None, ...):
        self._config = config
        self._signature = signature
        self._llm = llm or get_provider(config.model)  # from kaizen.providers
        self._tools = tools or ToolRegistry()           # unified registry
        self._memory = memory or SessionMemory()
        self._structured_output = (
            StructuredOutput.from_signature(signature) if signature else None
        )

    def run(self, **inputs) -> Dict[str, Any]: ...
    async def run_async(self, **inputs) -> Dict[str, Any]: ...

    # Node interface (workflow integration)
    def get_parameters(self) -> Dict[str, NodeParameter]: ...
    def to_workflow(self) -> Workflow: ...

    # Deprecated extension points (kept in v2.x for backward compat)
    @deprecated("Use composition wrappers instead. Removed in v3.0.")
    def _default_signature(self) -> Signature: ...
    @deprecated(...)
    def _default_strategy(self) -> ExecutionStrategy: ...
    # ... etc for all 7
```

### Capability wrappers (new)

```python
class StreamingAgent(BaseAgent):
    """Wraps any BaseAgent and emits typed events via AgentLoop (TAOD)."""
    def __init__(self, inner: BaseAgent, loop_config: Optional[AgentLoopConfig] = None): ...
    async def run_stream(self, **inputs) -> AsyncGenerator[DelegateEvent, None]: ...
    def run(self, **inputs) -> Dict[str, Any]: ...  # blocking variant

class MonitoredAgent(BaseAgent):
    """Wraps any BaseAgent with cost tracking via kailash.trust.BudgetTracker."""
    def __init__(self, inner: BaseAgent, budget_usd: float,
                 cost_config: Optional[CostConfig] = None): ...
    def run(self, **inputs) -> Dict[str, Any]: ...

class L3GovernedAgent(BaseAgent):
    """Wraps any BaseAgent with PACT envelope enforcement."""
    def __init__(self, inner: BaseAgent, envelope: ConstraintEnvelope,
                 pact_engine: Optional[PactEngine] = None): ...
    def run(self, **inputs) -> Dict[str, Any]: ...

class SupervisorAgent(BaseAgent):
    """Composes multiple WorkerAgents with routing strategy."""
    def __init__(self, workers: list[WorkerAgent],
                 routing: RoutingStrategy = RoundRobin): ...
    def run(self, **inputs) -> Dict[str, Any]: ...

class WorkerAgent(BaseAgent):
    """Wraps any BaseAgent with worker status tracking and capability list."""
    def __init__(self, inner: BaseAgent, capabilities: list[str]): ...
    def run(self, **inputs) -> Dict[str, Any]: ...
```

Each wrapper itself implements `BaseAgent`, so wrappers can be stacked:

```python
# Stack order matters (innermost → outermost)
agent = BaseAgent(config=cfg, signature=MySig, tools=...)  # primitive
agent = MonitoredAgent(agent, budget_usd=10.0)              # adds cost tracking
agent = L3GovernedAgent(agent, envelope=my_env)             # adds PACT governance
agent = StreamingAgent(agent)                                # adds event stream

# Usage
async for event in agent.run_stream(query="..."):
    ...
# OR blocking
result = agent.run(query="...")
```

## Rationale

1. **Rust is the reference implementation.** It already has this exact pattern and works. Python converging to match eliminates cross-SDK divergence.

2. **Composition is unlimited; inheritance is single-shot.** With composition, users can stack any number of capabilities. With subclassing, they can only pick one subclass.

3. **Capabilities become explicit and testable.** `MonitoredAgent` has a single concern (cost tracking) and can be unit-tested without touching BaseAgent. Currently, cost tracking is buried inside BaseAgent's `MetricsMixin` which is applied conditionally based on config flags.

4. **Eliminates the extension-point anti-pattern** that conflicts with `rules/agent-reasoning.md` (LLM-first). Subclasses that override `_default_strategy()` or `_generate_system_prompt()` are doing code-based agent routing, which is blocked by the rule.

5. **Fix for bug #339 becomes trivial.** The 4 sub-issues all trace back to extension points:
   - Sub-issue 1: `tool_formatters.convert_mcp_to_openai_tools()` strips `mcp_server_config` — moving this to shared `kailash-mcp` removes the stripping.
   - Sub-issue 2: `_execute_regular_tool()` stub — this extension point disappears; tools are executed by the unified ToolRegistry.
   - Sub-issue 3: `_generate_system_prompt()` injects text-based tool instructions — the extension point disappears; system prompts are configured via parameter, not generated by override.
   - (Sub-issue 4: `_execute_mcp_tool_call()` reads stripped config — solved by shared client.)

6. **Test migration is manageable.** ~600 tests touch BaseAgent, but most test the public API (`run()`, `run_async()`, attributes) which stays stable. Tests that exercise extension points get rewritten to use composition wrappers. Estimated 100-200 tests need active migration.

## Consequences

### Positive

- ✅ Matches Rust architecture exactly (EATP D6 compliance)
- ✅ Composition is unbounded — users can stack 5+ wrappers if needed
- ✅ Each capability is independently testable
- ✅ Agent reasoning rule (`rules/agent-reasoning.md`) is enforceable at the primitive layer
- ✅ Bug #339 and related MCP issues become trivially fixable
- ✅ Signature validation becomes automatic (no opt-in extension point)
- ✅ Multi-agent patterns (Supervisor/Worker) can be expressed as wrappers, not separate pattern classes
- ✅ Delegate becomes a real composition facade (see ADR-007)

### Negative

- ❌ 188 subclasses need audit. Most just override `_default_signature()` — these become constructor parameters. Some override multiple extension points — these become stacked wrappers.
- ❌ ~100-200 tests need active migration (others work unchanged).
- ❌ v2.x → v3.0 migration path required. Deprecation warnings for v2.x, removal in v3.0 (see ADR-009).
- ❌ Documentation needs a complete rewrite of "how to build an agent" — new canonical pattern is composition, not inheritance.
- ❌ User-facing tutorials must be updated to show wrapper stacking rather than subclassing.

### Neutral

- ~3,698 lines of BaseAgent become ~500-800 lines (much simpler). The removed code gets redistributed across wrappers and shared primitives (kailash-mcp, kaizen/providers/, etc.).
- Node inheritance stays (see ADR-002), so workflow composition still works.

## Alternatives Considered

### Alternative 1: Keep extension points, add composition as an additional option

**Rejected**. Maintains two competing patterns in the codebase forever. Users don't know which to pick. The extension point pattern is the ANTI-pattern we're trying to eliminate.

### Alternative 2: Create a new minimal `Agent` class alongside the existing `BaseAgent`

**Considered then rejected**. This was "Option A" in the red team response. User explicitly chose **Option B** (slim `BaseAgent` into the Agent role) on 2026-04-07 with rationale: "we should deprecate the 7 extension points, we will have to work through all the tests."

Option A would have two concept names for similar things, making docs confusing ("use `Agent` for new code, `BaseAgent` if you inherited from it"). Option B is cleaner conceptually but requires migrating existing tests.

### Alternative 3: Remove extension points immediately (no deprecation period)

**Rejected**. Breaks 188 subclasses and ~600 tests in a single release. Violates the `zero net regressions` constraint from the brief. Must use a deprecation period (v2.x → v3.0) per ADR-009.

## Implementation Notes

1. **Extension point deprecation** uses `@deprecated` decorator with clear migration guidance in the warning message.
2. **Test migration** is tracked as a dedicated phase in the workspace's todos.
3. **Subclass migration guide** lives in `packages/kailash-kaizen/docs/migration/composition-pattern.md` (written during `/codify` phase).
4. **Bundled wrappers** should be re-exported from `kaizen_agents.__init__` for discoverability.
5. **Wrapper unit tests** follow the pattern: mock the inner BaseAgent, verify the wrapper's added behavior in isolation.

## Related ADRs

- **ADR-002**: BaseAgent keeps Node inheritance (preserves workflow composition)
- **ADR-003**: Streaming as wrapper primitive (the StreamingAgent pattern)
- **ADR-007**: Delegate as composition facade (depends on this ADR)
- **ADR-009**: Backward compatibility strategy (defines v2.x → v3.0 deprecation window)

## Related Research

- `01-research/07-baseagent-audit.md` — full BaseAgent surface area audit
- `01-research/08-delegate-audit.md` — Delegate vs BaseAgent parallel stack analysis
- `02-rs-research/07-rs-agents-audit.md` — Rust's composition-wrapper pattern (the reference)

## Related Issues

- Python #339 — BaseAgent MCP tool execution broken (solved as side-effect of this ADR)
- Python #340 — Gemini structured + tools crash (solved by ADR-005 + shared provider layer)
