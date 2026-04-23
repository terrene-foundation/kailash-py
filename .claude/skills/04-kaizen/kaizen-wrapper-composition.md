# Kaizen Wrapper Composition & Provider Protocols

Advanced composition surface for Kaizen agents: wrapper stacking, provider capability protocols, LLM-based routing, and SPEC-02/05/10 convergence. Load when building layered agents (governance + monitoring + streaming) or implementing provider-aware code.

## Wrapper Composition System

Composition wrappers add cross-cutting concerns (governance, monitoring, streaming) around a `BaseAgent` without modifying it. `WrapperBase` enforces a canonical stacking order and duplicate detection.

**Canonical stacking order** (innermost to outermost):

```
BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent
```

`WrapperBase` rejects duplicate wrappers (`DuplicateWrapperError`) and out-of-order stacking (`WrapperOrderError`). Every wrapper proxies `get_parameters()` and `to_workflow()` to the inner agent. The `innermost` property walks the full stack to the non-wrapper agent.

### Key files

- `packages/kaizen-agents/src/kaizen_agents/wrapper_base.py` -- `WrapperBase` with stack ordering + duplicate detection
- `packages/kaizen-agents/src/kaizen_agents/governed_agent.py` -- `L3GovernedAgent` with `ConstraintEnvelope` enforcement (Financial, Operational, Temporal, Data Access, Communication, Posture ceiling). Rejects BEFORE LLM cost is incurred. Uses `_ProtectedInnerProxy` to block governance bypass via `.inner._inner`.
- `packages/kaizen-agents/src/kaizen_agents/monitored_agent.py` -- `MonitoredAgent` with `CostTracker`, budget enforcement via `BudgetExhaustedError`, NaN/Inf defense on budget values
- `packages/kaizen-agents/src/kaizen_agents/streaming_agent.py` -- `StreamingAgent` with `run_stream()` async iterator, typed `StreamEvent` events, buffer overflow protection, timeout enforcement. Falls back to batch when provider lacks `StreamingProvider`.
- `packages/kaizen-agents/src/kaizen_agents/events.py` -- Frozen dataclass events: `TextDelta`, `ToolCallStart`, `ToolCallEnd`, `TurnComplete`, `BudgetExhausted`, `ErrorEvent`, `StreamBufferOverflow`
- `packages/kaizen-agents/src/kaizen_agents/supervisor_wrapper.py` -- `SupervisorWrapper` for task delegation to worker pool via `LLMBased` routing

### Building a wrapper stack

```python
from kaizen.core.base_agent import BaseAgent
from kaizen_agents.governed_agent import L3GovernedAgent
from kaizen_agents.monitored_agent import MonitoredAgent
from kaizen_agents.streaming_agent import StreamingAgent
from kaizen_agents.events import TextDelta, TurnComplete
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint

# Stack innermost to outermost
agent = MyAgent(config=config)
governed = L3GovernedAgent(agent, envelope=ConstraintEnvelope(
    financial=FinancialConstraint(budget_limit=10.0)
))
monitored = MonitoredAgent(governed, budget_usd=5.0)
streaming = StreamingAgent(monitored)

# Stream typed events
async for event in streaming.run_stream(prompt="analyze this"):
    match event:
        case TextDelta(text=t): print(t, end="")
        case TurnComplete(text=t): print(f"\n[Done: {t[:50]}]")
```

### SupervisorWrapper

Delegates tasks to a worker pool using LLM-based routing:

```python
from kaizen_agents.supervisor_wrapper import SupervisorWrapper
from kaizen_agents.patterns.llm_routing import LLMBased

supervisor = SupervisorWrapper(inner_agent, workers=[w1, w2], routing=LLMBased())
result = await supervisor.run_async(task="complex task")
```

## Provider Capability Protocols

SPEC-02 defines `runtime_checkable` protocols in `kaizen.providers.base` for structural capability discovery. Providers satisfy protocols structurally — no explicit inheritance needed.

| Protocol                   | Key Method                          | Purpose                        |
| -------------------------- | ----------------------------------- | ------------------------------ |
| `StreamingProvider`        | `stream_chat()` -> `StreamEvent`    | Token-by-token streaming       |
| `ToolCallingProvider`      | `chat_with_tools(messages, tools)`  | Native function calling        |
| `StructuredOutputProvider` | `chat_structured(messages, schema)` | JSON schema structured outputs |
| `AsyncLLMProvider`         | `chat_async(messages)`              | Async chat completions         |

`ProviderCapability` enum: `CHAT_SYNC`, `CHAT_ASYNC`, `CHAT_STREAM`, `TOOLS`, `STRUCTURED_OUTPUT`, `EMBEDDINGS`, `VISION`, `AUDIO`, `REASONING_MODELS`, `BYOK`.

Use `get_provider_for_model(model)` from `kaizen.providers.registry` to resolve a model string to a provider instance. Use `isinstance(provider, StreamingProvider)` for capability checks.

## LLM-Based Routing

`LLMBased` from `kaizen_agents.patterns.llm_routing` scores agent capabilities against task requirements using Kaizen signatures (not keyword matching or dispatch tables).

```python
from kaizen_agents.patterns.llm_routing import LLMBased

routing = LLMBased(config=config)  # config optional; falls back to .env defaults
score = await routing.score("analyze revenue data", agent_capability)
best = await routing.select_best("analyze revenue data", [agent1, agent2, agent3])
```

`score()` returns `[0.0, 1.0]`. Accepts `Capability` dataclasses (`.name` + `.description`) or plain strings. `select_best()` returns the highest-scoring candidate or `None` when empty.

## Convergence Status (SPEC-02 / SPEC-05 / SPEC-10)

Three convergence SPECs have shipped on the `feat/spec04-baseagent-slim` branch:

### SPEC-02 (Provider Split)

The provider monolith (`kaizen.nodes.ai.ai_providers`) is now split into per-provider modules under `kaizen/providers/`. See [kaizen-multi-provider](kaizen-multi-provider.md) for the updated registry, protocols, and CostTracker.

- `kaizen.providers.base` -- `ProviderCapability` enum (10 members), 5 runtime-checkable protocols
- `kaizen.providers.registry` -- `ProviderRegistry` with 14 provider entries and prefix-dispatch model detection
- `kaizen.providers.cost` -- `CostTracker` with thread-safe accumulation
- Backward-compat shim at `kaizen.nodes.ai.ai_providers` re-exports all public names

### SPEC-05 (Delegate Facade)

Delegate is now a composition facade wrapping `AgentLoop -> [L3GovernedAgent] -> [MonitoredAgent]`. See [kaizen-delegate](kaizen-delegate.md) for the updated API surface.

- `ConstructorIOError` -- raised on outbound IO in `__init__`
- `ToolRegistryCollisionError` -- raised on duplicate tool name registration
- `run_sync()` refuses under a running event loop with an actionable error message
- Deferred MCP: `mcp_servers=` stores configs, connects on first `run()`
- Introspection: `.core_agent`, `.signature`, `.model` read-only properties

### SPEC-10 (Multi-Agent)

11 deprecated agent subclasses (SupervisorAgent, WorkerAgent, CoordinatorAgent, PipelineStageAgent, etc.) now emit `DeprecationWarning`. Composition patterns accept plain `BaseAgent` instances. `max_total_delegations` cap (default 20) with `DelegationCapExceeded` exception.
