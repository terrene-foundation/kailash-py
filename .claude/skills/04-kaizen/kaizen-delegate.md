# Delegate — Unified Autonomous Core

The `Delegate` class is the primary user-facing API for kaizen-agents. It composes `AgentLoop` with typed events, budget tracking, and progressive disclosure.

## Progressive Disclosure API

```python
from kaizen_agents import Delegate

# Layer 1 — Simple (one-liner)
delegate = Delegate(model="claude-sonnet-4-20250514")

# Layer 2 — Configured (tools + system prompt)
delegate = Delegate(
    model="claude-sonnet-4-20250514",
    tools=[search_tool, calculator_tool],
    system_prompt="You are a research assistant.",
)

# Layer 3 — Governed (budget + envelope)
delegate = Delegate(
    model="claude-sonnet-4-20250514",
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

## Synchronous Convenience

```python
result = delegate.run_sync("What is 2+2?")
print(result)  # "4"
```

## Budget Tracking

Per-model cost estimation with NaN/Inf defense:

```python
delegate = Delegate(model="claude-sonnet-4-20250514", budget_usd=5.0)
# Tracks cumulative cost per turn
# Yields BudgetExhausted event when limit reached
```

## Source Files

- `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/events.py`
