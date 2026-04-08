# Delegate Surface Area Audit — 2026-04-07

**Audit scope**: Map Delegate, AgentLoop, adapters, hooks, MCP, and the architectural invariant that explains the kaizen split.

## Executive Summary

Delegate is a **parallel implementation** of autonomous agent execution that does NOT compose BaseAgent. The smoking gun is in `loop.py` lines 14-16:

> "Architectural invariant: the kz core loop MUST NOT use Kaizen Pipeline primitives. Pipelines are for user-space application construction, not core orchestration."

This invariant exists because **BaseAgent inherits from `Node`**, and Node-based execution is fundamentally incompatible with token streaming and the autonomous loop. Delegate had to be built from scratch — there was no path to add streaming to a workflow-graph execution model.

## Delegate Surface (delegate.py)

**Location**: `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py` (421 lines)

### Constructor

```python
def __init__(
    model: str = "",
    *,
    tools: ToolRegistry | list[str] | None = None,
    system_prompt: str | None = None,
    max_turns: int = 50,
    budget_usd: float | None = None,
    adapter: StreamingChatAdapter | None = None,
    config: KzConfig | None = None,
)
```

### Public methods

| Method             | Returns                         | Layer    |
| ------------------ | ------------------------------- | -------- |
| `run(prompt)`      | `AsyncGenerator[DelegateEvent]` | L1/L2/L3 |
| `run_sync(prompt)` | `str` (blocking)                | L1/L2    |
| `interrupt()`      | None                            | L2       |
| `close()`          | None                            | L3       |

### Public properties

`loop` (raw AgentLoop access), `tool_registry`, `budget_usd`, `consumed_usd`, `budget_remaining`

### Progressive disclosure

- **L1 (~10 LOC)**: `Delegate(model="...")` then `async for event in delegate.run(...)`
- **L2 (~15 LOC)**: configured with tools, system_prompt, max_turns
- **L3 (~50+ LOC)**: governed with budget_usd, raw `delegate.loop` access

## AgentLoop (loop.py)

**Location**: `packages/kaizen-agents/src/kaizen_agents/delegate/loop.py` (821 lines)

### The autonomous loop

```
LOOP:
  1. Assemble prompt (system + context + conversation + tool defs)
  2. Stream LLM response
  3. If tool calls -> execute tools (parallel for independent) -> append -> loop
  4. If text only -> yield to user
  5. Repeat until user exits
```

### Why the invariant exists

**BaseAgent's path**:

```
BaseAgent → Node (Core SDK) → WorkflowBuilder → LocalRuntime → graph traversal
```

Designed for: stateful multi-step, checkpoint recovery, audit trails, validation.

**AgentLoop's path**:

```
AgentLoop → StreamingChatAdapter (protocol) → autonomous loop → async generator
```

Designed for: single-turn, parallel tool execution, ephemeral state, per-token streaming.

**You cannot**:

- Add token streaming to a synchronous workflow graph
- Make tool execution parallel in a linear node sequence
- Make the LLM the sole decision maker when code routes between nodes

So Delegate had to be built clean-slate. **The invariant is not a stylistic choice — it's a structural necessity** given BaseAgent's Node inheritance.

### Constructor (lines 272-347)

```python
AgentLoop(
    config: KzConfig,
    tools: ToolRegistry,
    *,
    client: AsyncOpenAI | None = None,           # Legacy fallback
    adapter: StreamingChatAdapter | None = None, # Multi-provider
    system_prompt: str | None = None,
    budget_check: Callable[[], bool] | None = None,
    hydrator: ToolHydrator | None = None,
)
```

### Tool execution (lines 637-730)

- **Parallel execution** via `asyncio.gather()` — all tool calls in a `tool_calls` list run concurrently
- **Error isolation** — failed tools return JSON `{"error": "..."}` instead of raising
- **Conversation append** — results appended as `role: "tool"` messages
- **Event callback** — `ToolCallStart`/`ToolCallEnd` events pushed to Delegate via `_event_callback`

## ToolRegistry (in loop.py)

```python
class ToolRegistry:
    _tools: dict[str, ToolDef]            # OpenAI function-calling format
    _executors: dict[str, Callable[..., Awaitable[str]]]  # CALLABLE EXECUTORS

    def register(name, description, parameters, executor): ...
    def execute(name, arguments) -> str: ...
    def get_openai_tools() -> list[dict]: ...
```

**Critical difference from BaseAgent's tool system**: Delegate's ToolRegistry stores **callable executors**, not just JSON schemas. This is why MCP tools work — the registration captures the closure that knows how to call back to the MCP server.

## Streaming Adapters (delegate/adapters/)

### Protocol (protocol.py)

```python
@runtime_checkable
class StreamingChatAdapter(Protocol):
    async def stream_chat(
        messages, tools=None, *, model=None, temperature=None, max_tokens=None, **kwargs
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

### StreamEvent dataclass

```python
event_type: str  # "text_delta" | "tool_call_start" | "tool_call_delta" | "done"
content: str
delta_text: str
tool_calls: list[dict]  # OpenAI format
finish_reason: str | None
model: str
usage: dict[str, int]
```

### Adapters

| File                   | Provider      | Notes                                                                          |
| ---------------------- | ------------- | ------------------------------------------------------------------------------ |
| `openai_adapter.py`    | OpenAI        | Reasoning model support (o1, o3, gpt-5)                                        |
| `openai_stream.py`     | OpenAI        | Legacy stream processor (duplicate logic, should be removed)                   |
| `anthropic_adapter.py` | Anthropic     | system prompt extracted to separate param, tool_use → tool_calls normalization |
| `google_adapter.py`    | Google Gemini | FunctionDeclaration → OpenAI format conversion                                 |
| `ollama_adapter.py`    | Ollama        | local-only, limited tool support                                               |
| `protocol.py`          | (interface)   | Runtime-checkable Protocol                                                     |
| `registry.py`          | (selector)    | `get_adapter_for_model(model)` with prefix detection                           |

**Missing adapters**: Azure, Cohere, HuggingFace, Perplexity, DockerModelRunner

### openai_adapter vs openai_stream (duplication)

`openai_adapter.py` is the StreamingChatAdapter wrapper. `openai_stream.py` is the legacy stream processor used when `client` is passed directly to AgentLoop. **The two files duplicate logic** — `openai_stream.py` should be removed after consolidation.

## Tool Hydration (delegate/tools/hydrator.py)

When tool count exceeds threshold (~30):

1. `ToolHydrator()` indexes all tool definitions with BM25 scoring
2. Only base tools (~15) are sent to LLM by default
3. `search_tools` meta-tool is injected
4. LLM calls `search_tools(query)` to pull in deferred tools on-demand

**Key insight**: This is a **primitive concern** (tool organization for token efficiency), not an engine concern. Should live in the unified primitive layer.

## MCP Client (delegate/mcp.py)

**Already covered in 01-mcp-inventory.md.** 509 lines, stdio JSON-RPC only, production-quality, no auth, registers callable executors into ToolRegistry. **Should be replaced by `kailash.mcp_server.MCPClient` with stdio transport** — that one has 4 transports, 5 auth providers, retry, discovery, metrics.

## Hooks (delegate/hooks.py)

**HookManager** discovers and executes scripts from `.kz/hooks/`:

| HookEvent       | When                  |
| --------------- | --------------------- |
| `PRE_TOOL_USE`  | Before tool execution |
| `POST_TOOL_USE` | After tool execution  |
| `PRE_MODEL`     | Before LLM call       |
| `POST_MODEL`    | After LLM call        |
| `SESSION_START` | Session begins        |
| `SESSION_END`   | Session ends          |

Scripts run as subprocess with event payload on stdin as JSON. Exit codes: 0=allow, 1=warn, 2=block. Languages: `.js`, `.py`.

## Events (delegate/events.py)

```python
DelegateEvent (base)
├── TextDelta(text: str)
├── ToolCallStart(call_id, name)
├── ToolCallEnd(call_id, name, result, error)
├── TurnComplete(text, usage)
├── BudgetExhausted(budget_usd, consumed_usd)
└── ErrorEvent(error, details)
```

Pattern-matchable via `match` statement. **This is what BaseAgent lacks** — typed event stream for structured consumption (UI rendering, logging, governance).

## Governance Integration (supervisor.py)

**GovernedSupervisor** wraps Delegate with PACT enforcement:

- 6 subsystems: accountability, budget, cascade, clearance, audit, holds
- Imports `from kailash.trust.pact.agent import GovernanceHeldError`
- Imports `from kailash.trust.pact.config import ConstraintEnvelopeConfig, ...`
- Imports `from kailash.trust import ConfidentialityLevel`

**Constraint envelope**:

```python
ConstraintEnvelope(
    financial=FinancialConstraintConfig(budget_usd=10.0, spend_limit=0.5),
    temporal=TemporalConstraintConfig(max_duration_seconds=300),
    operational=OperationalConstraintConfig(max_turns=20, allowed_tools=[...]),
)
```

**Holds**: When constraints would be violated, agent execution is HELD pending human approval via `HoldRecord`.

## Capability Comparison: Delegate vs BaseAgent

(See 07-baseagent-audit.md for the full matrix.)

**What Delegate has that BaseAgent doesn't**:

1. Token streaming via async generators
2. Multi-provider streaming adapters (4 clean implementations)
3. Budget tracking with cost estimation (model-aware pricing)
4. Typed event stream
5. Tool hydration (BM25)
6. Hook system (clean lifecycle)
7. Progressive disclosure API (L1/L2/L3)
8. Working MCP execution
9. Governance wrapping via GovernedSupervisor

**What BaseAgent has that Delegate doesn't**:

1. Structured outputs (Signature → JSON schema)
2. Mixin composition
3. Strategy pattern (SingleShot, MultiCycle)
4. Node inheritance / workflow integration
5. 7 extension points
6. Tool definition types (DangerLevel, ToolCategory, ToolParameter)
7. Multi-agent patterns dependency surface
8. Vision/audio multi-modal support

## Convergence Target

### What gets extracted to the unified primitive layer

```
packages/kailash-kaizen/src/kaizen/
├── core/
│   ├── base_agent.py            # Slimmed primitive
│   ├── agent_loop.py            # MOVED from delegate/loop.py
│   ├── structured_output.py     # Already extracted
│   └── tools/
│       ├── registry.py          # Unified ToolRegistry (JSON + callable)
│       ├── hydrator.py          # MOVED from delegate/tools/hydrator.py
│       └── builtin/             # MOVED from delegate/tools/
├── adapters/                    # MOVED from delegate/adapters/
│   ├── protocol.py              # StreamingChatAdapter
│   ├── openai_adapter.py
│   ├── anthropic_adapter.py
│   ├── google_adapter.py
│   ├── ollama_adapter.py
│   └── registry.py
├── events.py                    # MOVED from delegate/events.py
├── hooks.py                     # MOVED from delegate/hooks.py
└── mcp/                         # Imports from kailash-mcp
```

### What stays in kaizen-agents (the engine)

```
packages/kaizen-agents/src/kaizen_agents/
├── delegate.py                  # THIN facade — composes BaseAgent + governance + budget
├── governance/                  # GovernedSupervisor, accountability, cascade
├── patterns/                    # Multi-agent patterns (already use run())
└── agents/                      # Specialized agents (specialized BaseAgent subclasses)
```

### Unified BaseAgent design

```python
class BaseAgent(Node):  # Keep Node inheritance for workflow compat
    def __init__(self, config, signature, ...):
        ...

    # Multiple strategies — autonomous loop is one of them
    def _default_strategy(self):
        if self.config.execution_model == "autonomous":
            return AsyncSingleShotStrategy(loop=AgentLoop(...))
        elif self.config.execution_model == "multi_cycle":
            return MultiCycleStrategy(loop=AgentLoop(...))
        elif self.config.execution_model == "workflow":
            return WorkflowStrategy(...)  # Traditional Node-based path

    async def run_async(self, **inputs) -> Dict[str, Any]:
        # Streaming variant if requested
        if self.config.streaming:
            async for event in self.strategy.execute_streaming(self, inputs):
                yield event
        else:
            return await self.strategy.execute(self, inputs)
```

### Delegate becomes a thin facade

```python
class Delegate:
    """Engine: composes BaseAgent + governance + budget + typed events."""

    def __init__(self, model, *, tools=None, budget_usd=None, ...):
        self._agent = BaseAgent(
            config=BaseAgentConfig(
                model=model,
                execution_model="autonomous",
                streaming=True,
            ),
            tools=tools,
        )
        if budget_usd:
            self._agent = GovernedSupervisor.wrap(self._agent, budget_usd=budget_usd)

    async def run(self, prompt) -> AsyncGenerator[DelegateEvent]:
        async for event in self._agent.run_async(prompt=prompt):
            yield event
```

**Result**: Public Delegate API stable. Internal composition replaces parallel implementation.

## Test Surface

- `packages/kaizen-agents/tests/unit/delegate/` — Delegate, AgentLoop, ToolRegistry, hydrator, MCP
- `packages/kaizen-agents/tests/unit/agents/coordination/` — multi-agent patterns
- `packages/kaizen-agents/tests/integration/` — end-to-end Nexus integration
- Total: ~600 tests across BaseAgent + Delegate + patterns

**Refactor regression net**: All ~600 tests must continue passing. No public API changes.
