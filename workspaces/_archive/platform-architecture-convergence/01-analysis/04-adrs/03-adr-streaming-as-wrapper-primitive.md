# ADR-003: Streaming as Wrapper Primitive

**Status**: ACCEPTED (2026-04-07)
**Scope**: Kaizen (kailash-kaizen, kaizen-agents)
**Deciders**: Platform Architecture Convergence workspace

## Context

Python currently has two parallel agent execution stacks:

1. **BaseAgent** — returns `Dict[str, Any]`, workflow-composable, no streaming
2. **Delegate + AgentLoop** — returns `AsyncGenerator[DelegateEvent]`, streaming, no workflow composition, no structured outputs

This is the core capability fragmentation the convergence is solving. Users who need structured outputs must use BaseAgent (but then they can't stream). Users who need streaming must use Delegate (but then they can't use signatures). Users who need both are stuck.

### Rust's pattern (the reference)

Rust doesn't have this fragmentation. It has:

- `BaseAgent` trait (2 methods, batch execution via `run()`)
- `Agent` struct (concrete BaseAgent implementation)
- `StreamingAgent(Agent)` — a wrapper struct that holds an Agent and adds streaming via `run_stream() -> CallerEventStream`

```rust
// crates/kaizen-agents/src/streaming/agent.rs
pub struct StreamingAgent {
    agent: Agent,                           // WRAPS the primitive
    handler: Option<Arc<dyn StreamHandler>>,
}

impl StreamingAgent {
    pub async fn run_stream(&self, prompt: &str) -> CallerEventStream { ... }
}
```

The key insight: **streaming is not an execution mode of BaseAgent — it's a capability added by a wrapper.** The wrapper uses an internal `TaodRunner` (Rust's equivalent of AgentLoop) to drive the autonomous loop and emit events.

### Why this is better

1. **BaseAgent doesn't need to change.** Its `run() -> Dict` interface stays. No streaming method needed on the primitive.
2. **Streaming becomes composable.** Want streaming + cost tracking + governance? Stack wrappers: `StreamingAgent(MonitoredAgent(L3GovernedAgent(base_agent)))`.
3. **Matches the composition-over-extension-points pattern** (ADR-001).
4. **The architectural invariant in `delegate/loop.py`** becomes trivially satisfied — AgentLoop isn't used by BaseAgent at all. It's used by StreamingAgent as an implementation detail.

## Decision

**Streaming is implemented as a `StreamingAgent` composition wrapper that wraps any `BaseAgent` and emits typed events via an internal `AgentLoop`. BaseAgent itself does NOT gain a streaming method.**

### Python implementation

```python
# packages/kaizen-agents/src/kaizen_agents/streaming_agent.py

from dataclasses import dataclass
from typing import AsyncGenerator, Optional
from kaizen.core.base_agent import BaseAgent
from kaizen.core.agent_loop import AgentLoop, AgentLoopConfig
from kaizen_agents.events import (
    DelegateEvent, TextDelta, ToolCallStart, ToolCallEnd,
    TurnComplete, BudgetExhausted, ErrorEvent
)


class StreamingAgent(BaseAgent):
    """Composition wrapper that adds streaming to any BaseAgent.

    StreamingAgent holds an inner BaseAgent and uses an internal AgentLoop
    (TAOD loop) to drive autonomous execution, emitting typed events as
    tokens arrive from the LLM provider.

    Examples:

        # Basic streaming with a plain BaseAgent
        agent = BaseAgent(config=cfg, signature=MySig)
        streaming = StreamingAgent(agent)
        async for event in streaming.run_stream(query="..."):
            match event:
                case TextDelta(text=t): print(t, end="")
                case ToolCallEnd(name=n, result=r): log(n, r)
                case TurnComplete(text=t, structured=s): final = s

        # Stacking wrappers (order matters: innermost first)
        agent = BaseAgent(...)
        agent = MonitoredAgent(agent, budget_usd=10.0)     # adds cost tracking
        agent = L3GovernedAgent(agent, envelope=my_env)    # adds PACT governance
        streaming = StreamingAgent(agent)                   # adds event stream
        async for event in streaming.run_stream(...):
            ...
    """

    def __init__(
        self,
        inner: BaseAgent,
        *,
        loop_config: Optional[AgentLoopConfig] = None,
        budget_check: Optional[Callable[[], bool]] = None,
    ):
        # StreamingAgent itself is a BaseAgent (so it can be nested/composed)
        # but it proxies node-level concerns to the inner agent
        self._inner = inner
        self._loop = AgentLoop(
            agent=inner,
            config=loop_config or AgentLoopConfig.from_agent(inner),
            budget_check=budget_check,
        )

    # ─── The streaming API (new surface) ───────────────────────────────

    async def run_stream(
        self, **inputs
    ) -> AsyncGenerator[DelegateEvent, None]:
        """Execute autonomously, yielding typed events as they arrive.

        Event types:
        - TextDelta(text): incremental text tokens from the LLM
        - ToolCallStart(call_id, name): tool invocation beginning
        - ToolCallEnd(call_id, name, result, error): tool invocation complete
        - TurnComplete(text, usage, structured): turn ended naturally
        - BudgetExhausted(budget_usd, consumed_usd): budget cap hit
        - ErrorEvent(error, details): exception during execution
        """
        async for event in self._loop.run_stream(**inputs):
            yield event

    # ─── BaseAgent interface (preserved for composability) ──────────────

    def run(self, **inputs) -> Dict[str, Any]:
        """Blocking variant: collect stream, return final Dict.

        Allows StreamingAgent to be used in contexts that expect Dict return
        (multi-agent patterns, workflow composition, tests).
        """
        events = asyncio.run(self._collect_events(**inputs))
        return self._events_to_dict(events)

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Async blocking variant."""
        events = await self._collect_events(**inputs)
        return self._events_to_dict(events)

    async def _collect_events(self, **inputs) -> list[DelegateEvent]:
        return [event async for event in self.run_stream(**inputs)]

    def _events_to_dict(self, events: list[DelegateEvent]) -> Dict[str, Any]:
        # Find TurnComplete event, extract structured output if present
        for event in reversed(events):
            if isinstance(event, TurnComplete):
                return {
                    "text": event.text,
                    "usage": event.usage,
                    "structured": event.structured,
                }
        # No TurnComplete means error or interrupt
        for event in events:
            if isinstance(event, ErrorEvent):
                return {"error": event.error, "details": event.details}
        return {"text": "", "usage": {}, "structured": None}

    # ─── Node interface (proxied to inner) ─────────────────────────────
    # StreamingAgent is NOT meant for workflow composition. If users want
    # a wrapped agent inside a workflow, they should use the inner agent's
    # to_workflow() directly.

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return self._inner.get_parameters()

    # Deliberately NOT implementing to_workflow() — streaming agents don't
    # belong in batch workflow graphs.
```

### Cross-SDK parallel

Python's `StreamingAgent` corresponds semantically to Rust's `streaming::StreamingAgent`:

| Concern             | Python                                       | Rust                                |
| ------------------- | -------------------------------------------- | ----------------------------------- |
| Class name          | `StreamingAgent`                             | `StreamingAgent`                    |
| Wraps               | `BaseAgent`                                  | `Agent`                             |
| Loop implementation | `AgentLoop` (kaizen/core/agent_loop.py)      | `TaodRunner` (agent_engine/taod.rs) |
| Event type          | `DelegateEvent` (Python dataclass hierarchy) | `CallerEvent` (Rust enum)           |
| Stream return       | `AsyncGenerator[DelegateEvent]`              | `CallerEventStream`                 |

### Event type hierarchy (unchanged from existing `delegate/events.py`)

```python
@dataclass(frozen=True)
class DelegateEvent:
    """Base class for typed streaming events."""
    timestamp: float  # time.monotonic()

@dataclass(frozen=True)
class TextDelta(DelegateEvent):
    text: str  # incremental text fragment

@dataclass(frozen=True)
class ToolCallStart(DelegateEvent):
    call_id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True)
class ToolCallEnd(DelegateEvent):
    call_id: str
    name: str
    result: Any
    error: Optional[str] = None

@dataclass(frozen=True)
class TurnComplete(DelegateEvent):
    text: str                              # final accumulated text
    usage: dict[str, int]                  # prompt_tokens, completion_tokens, total_tokens
    structured: Optional[Any] = None       # structured output if signature was provided
                                           # THIS IS NEW — carries the Signature-parsed result

@dataclass(frozen=True)
class BudgetExhausted(DelegateEvent):
    budget_usd: float
    consumed_usd: float

@dataclass(frozen=True)
class ErrorEvent(DelegateEvent):
    error: str
    details: dict[str, Any]
```

**Key addition**: `TurnComplete.structured` — carries the Signature-parsed result. This is how Delegate users get structured outputs after the stream completes.

## Rationale

1. **Resolves the red team's composition self-contradiction.** The red team's original diagnosis was that BaseAgent couldn't stream because of Node inheritance. This ADR shows that was the wrong question. BaseAgent doesn't need to stream — StreamingAgent streams on its behalf by wrapping it. ADR-002 handles the Node inheritance preservation.

2. **Matches Rust exactly.** Rust has `streaming::StreamingAgent` wrapping `Agent`. Python has `StreamingAgent` wrapping `BaseAgent`. Semantic parity achieved.

3. **Resolves case 2 from user question**: "I need structured output for Delegate". Structured output happens inside the inner `BaseAgent` (via its `signature` parameter). The `StreamingAgent` wrapper accumulates the text stream, and when the turn completes, the inner BaseAgent's structured output parser produces the final typed result, which is emitted as `TurnComplete.structured`.

4. **Preserves the AgentLoop architectural invariant.** `AgentLoop` (moved from `kaizen_agents/delegate/loop.py` to `kaizen/core/agent_loop.py` — see SPEC-04) is a primitive that doesn't use workflow primitives. `StreamingAgent` uses `AgentLoop` internally. Users don't see `AgentLoop` directly. `BaseAgent` doesn't use `AgentLoop` at all.

5. **Wrappers stack cleanly.** Because `StreamingAgent` itself implements `BaseAgent`, you can stack it with other wrappers:

   ```python
   agent = BaseAgent(...)
   agent = MonitoredAgent(agent, budget_usd=10.0)
   agent = L3GovernedAgent(agent, envelope=env)
   agent = StreamingAgent(agent)  # outermost for streaming API
   ```

6. **Streaming is optional.** Users who don't need streaming never touch `StreamingAgent`. They use `BaseAgent.run() -> Dict` directly. Zero cognitive overhead for batch users.

## Consequences

### Positive

- ✅ BaseAgent doesn't change — no new methods, no new execution modes
- ✅ Streaming is a first-class capability via wrapping
- ✅ Structured outputs and streaming compose (TurnComplete carries the typed result)
- ✅ Matches Rust's architecture exactly
- ✅ Stackable with other wrappers (MonitoredAgent, L3GovernedAgent, SupervisorAgent, WorkerAgent)
- ✅ Fixes the n8n-era assumption that "agent = node" without breaking it
- ✅ Delegate becomes a thin facade that internally constructs `StreamingAgent(BaseAgent)` (see ADR-007)
- ✅ The existing `delegate/events.py` file can be reused (events are the same types)
- ✅ The existing `delegate/loop.py` implementation can be moved to `kaizen/core/agent_loop.py` and reused

### Negative

- ❌ Users need to know about both BaseAgent and StreamingAgent. Documentation burden.
- ❌ Stacking wrappers in the wrong order is an error mode users can hit (e.g., putting `StreamingAgent` innermost and `MonitoredAgent` outermost would mean MonitoredAgent can't see individual stream events).
- ❌ `StreamingAgent.run() -> Dict` is a blocking variant that calls `asyncio.run()` internally, which has its own edge cases (nested event loops, etc.)

### Neutral

- `StreamingAgent` deliberately does NOT implement `to_workflow()`. Streaming agents aren't meant for batch workflow graphs. If users need a streaming agent inside a workflow, they should construct the workflow from the inner BaseAgent directly (then the workflow uses batch execution; streaming is lost).
- The `AgentLoop` class is now a public primitive in `kaizen/core/` rather than buried in `kaizen_agents/delegate/`. It's a low-level API — most users should use `StreamingAgent` or `Delegate` instead.

## Alternatives Considered

### Alternative 1: Add `run_stream()` to `BaseAgent` directly

**Rejected**. This was the red team's Option B. Problems:

- Doubles BaseAgent's surface area with two execution modes
- Forces all 188 subclasses to potentially implement streaming
- Couples streaming implementation to BaseAgent's class hierarchy
- Makes BaseAgent harder to test (two paths to cover)
- Violates separation of concerns — streaming is a capability, not a core requirement

The composition wrapper approach in this ADR is cleaner.

### Alternative 2: Keep Delegate as a separate class (sibling of BaseAgent)

**Superseded by ADR-007**. Keeping Delegate separate was the red team's Option C. It leaves the capability fragmentation unsolved — users still have to pick between BaseAgent (structured outputs, no streaming) and Delegate (streaming, no structured outputs).

This ADR and ADR-007 combined give users both capabilities by making Delegate a thin facade over `StreamingAgent(BaseAgent)`.

### Alternative 3: `StreamingMixin` that BaseAgent subclasses opt into

**Rejected**. Multiple inheritance for capabilities is exactly the anti-pattern that ADR-001 eliminates. Would reintroduce the mixin-based capability management that caused bugs in Python's `kaizen/core/mixins/` (conditional application, fragile async boundaries).

### Alternative 4: Two separate primitives — `BatchAgent` and `StreamingAgent` with no shared base

**Rejected**. Users would have to pick one at agent creation time and couldn't switch. No composition. No wrapping. Worse than the current situation.

## Implementation Notes

### 1. Move `AgentLoop` from `kaizen_agents/delegate/loop.py` to `kaizen/core/agent_loop.py`

The `AgentLoop` class currently lives in the `kaizen_agents` package as part of Delegate's internals. It becomes a public primitive in `kailash-kaizen`:

```
packages/kailash-kaizen/src/kaizen/core/
├── base_agent.py         (slimmed per ADR-001)
├── agent_loop.py         (MOVED from kaizen_agents/delegate/loop.py)
├── structured_output.py  (already exists)
└── signatures/
```

Rationale: `AgentLoop` needs to be reachable from both `BaseAgent` (if Delegate composes it) and `StreamingAgent` (which uses it internally). Putting it in `kailash-kaizen` makes it a primitive used by both packages.

### 2. `AgentLoopConfig.from_agent(agent: BaseAgent)` factory

Creates a default loop config from an agent's existing config:

```python
@dataclass
class AgentLoopConfig:
    max_turns: int = 50
    timeout: timedelta = timedelta(minutes=10)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    streaming: bool = True

    @classmethod
    def from_agent(cls, agent: BaseAgent) -> AgentLoopConfig:
        cfg = agent.config
        return cls(
            max_turns=cfg.max_cycles if hasattr(cfg, 'max_cycles') else 50,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
```

### 3. Event dispatch contract

`StreamingAgent.run_stream()` yields events in this order:

1. Zero or more `TextDelta` events (tokens as they arrive)
2. Zero or more `ToolCallStart` → `ToolCallEnd` pairs (during tool execution)
3. Exactly one `TurnComplete` at the end (or `BudgetExhausted` / `ErrorEvent` on failure)

If the turn doesn't complete naturally, a terminal `ErrorEvent` or `BudgetExhausted` is emitted instead of `TurnComplete`.

### 4. Structured output integration

When the inner `BaseAgent` has a `signature` configured:

1. The LLM is told (via system prompt / response_format) to emit structured JSON
2. `AgentLoop` accumulates `TextDelta` events into a final text buffer
3. On turn completion, `BaseAgent._parse_structured_output(text)` is called
4. The parsed result is attached to `TurnComplete.structured`
5. If parsing fails, a retry loop (existing `structured_output.py` retry logic) is triggered automatically
6. After max retries, `ErrorEvent` is emitted with parse failure details

### 5. Test migration strategy

Existing `delegate/test_streaming.py` tests become `kaizen_agents/tests/unit/test_streaming_agent.py`. Test structure is preserved; import paths change.

New tests needed:

- `StreamingAgent(BaseAgent)` with structured output (verifies TurnComplete.structured is populated)
- `StreamingAgent` stacking with `MonitoredAgent` (verifies cost tracking still works)
- `StreamingAgent.run() -> Dict` blocking variant (for multi-agent pattern compatibility)
- `StreamingAgent` does NOT implement `to_workflow()` (negative test)

### 6. Delegate migration (preview — full detail in ADR-007)

```python
class Delegate:
    def __init__(self, model, *, signature=None, tools=None,
                 mcp_servers=None, budget_usd=None, envelope=None, ...):
        inner = BaseAgent(
            config=BaseAgentConfig(model=model),
            signature=signature,
            tools=tools,
        )
        if mcp_servers:
            inner._mcp_client = MCPClient(servers=mcp_servers)
        if budget_usd:
            inner = MonitoredAgent(inner, budget_usd=budget_usd)
        if envelope:
            inner = L3GovernedAgent(inner, envelope=envelope)

        self._streaming = StreamingAgent(inner)

    async def run(self, **inputs) -> AsyncGenerator[DelegateEvent, None]:
        async for event in self._streaming.run_stream(**inputs):
            yield event
```

The user-facing `Delegate(...)` API is unchanged. Internal implementation is refactored to use composition.

## Related ADRs

- **ADR-001**: Composition over extension points (why wrappers exist)
- **ADR-002**: BaseAgent keeps Node inheritance (why BaseAgent doesn't need streaming)
- **ADR-007**: Delegate as composition facade (how Delegate uses StreamingAgent internally)
- **ADR-009**: Backward compatibility strategy (how users migrate from old Delegate to new Delegate — zero changes for users, internal changes only)

## Related Research

- `01-research/08-delegate-audit.md` — Delegate's AgentLoop, the architectural invariant
- `02-rs-research/07-rs-agents-audit.md` — Rust's StreamingAgent pattern (the reference)

## Related Issues

- Python #339 (MCP broken) — fixed as a side-effect because AgentLoop + StreamingAgent use the new `kailash_mcp.MCPClient`
- Python #340 (Gemini structured + tools) — fixed as a side-effect via ADR-005 (provider layer)
