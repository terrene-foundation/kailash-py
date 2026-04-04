# Delegate — Unified Autonomous Core

The `Delegate` class is the primary user-facing API for kaizen-agents. It composes `AgentLoop` with typed events, budget tracking, and progressive disclosure.

## Progressive Disclosure API

```python
from kaizen_agents import Delegate

# Layer 1 — Simple (one-liner)
delegate = Delegate(model=os.environ["LLM_MODEL"])

# Layer 2 — Configured (tools + system prompt)
delegate = Delegate(
    model=os.environ["LLM_MODEL"],
    tools=[search_tool, calculator_tool],
    system_prompt="You are a research assistant.",
)

# Layer 3 — Governed (budget + envelope)
delegate = Delegate(
    model=os.environ["LLM_MODEL"],
    tools=[search_tool],
    budget_usd=10.0,  # NaN/Inf validated via math.isfinite()
)
```

## Typed Event System

```python
from kaizen_agents.delegate.events import TextDelta, ToolCallStart, ToolCallEnd, TurnComplete

async for event in delegate.run("Analyze this dataset"):
    match event:
        case TextDelta(text=chunk):
            print(chunk, end="", flush=True)
        case ToolCallStart(name=name):
            print(f"\n[Calling {name}...]")
        case ToolCallEnd(name=name, result=result):
            print(f"[{name} returned]")
        case TurnComplete(text=text, usage=usage):
            print(f"\n[Done — {usage}]")
```

### Event Types

| Event             | Fields                         | When                     |
| ----------------- | ------------------------------ | ------------------------ |
| `TextDelta`       | `text: str`                    | Each text chunk from LLM |
| `ToolCallStart`   | `call_id, name`                | Before tool execution    |
| `ToolCallEnd`     | `call_id, name, result, error` | After tool execution     |
| `TurnComplete`    | `text, usage`                  | End of turn              |
| `BudgetExhausted` | `spent, limit`                 | Budget exceeded          |
| `ErrorEvent`      | `error, error_type`            | Unrecoverable error      |

### Event Ordering

Tool events follow a deterministic pattern per tool batch:

```
TextDelta("Let me search...")          # Optional pre-tool text
ToolCallStart(call_id="c1", name="search")   # All starts before execution
ToolCallStart(call_id="c2", name="read")
ToolCallEnd(call_id="c1", name="search", result="...")  # All ends after gather
ToolCallEnd(call_id="c2", name="read", result="...")
TextDelta("Based on results...")       # Next turn text
TurnComplete(text="...", usage={...})
```

For consecutive tool turns (model calls tools, sees results, calls more tools), each batch emits its own start/end events sequentially.

### Error Reporting in ToolCallEnd

- **Normal tool errors** (exception caught inside executor): Error JSON in `result` field, `error` field empty. The error is sent back to the model as a tool result.
- **Catastrophic failures** (BaseException escaping asyncio.gather): `error` field populated with `"Tool execution was interrupted"`, `result` field empty.
- **Error messages are sanitized**: Exception messages use `type(exc).__name__` only — raw `str(exc)` is never exposed in events (prevents internal detail leakage).

## Synchronous Convenience

```python
result = delegate.run_sync("What is 2+2?")
print(result)  # "4"
```

## Budget Tracking

Per-model cost estimation with NaN/Inf defense:

```python
delegate = Delegate(model=os.environ["LLM_MODEL"], budget_usd=5.0)
# Tracks cumulative cost per turn
# Yields BudgetExhausted event when limit reached
```

## Source Files

- `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/events.py`
