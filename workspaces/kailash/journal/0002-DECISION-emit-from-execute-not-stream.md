---
type: DECISION
date: 2026-03-29
project: kailash
topic: Emit tool events from _execute_tool_calls, not streaming detection
phase: todos
tags: [kaizen-agents, delegate, streaming, architecture]
---

# Decision: Emit Tool Events from Execution, Not Detection

## Choice

Emit `ToolCallStart` and `ToolCallEnd` events from `_execute_tool_calls()` (after stream completes), NOT from the streaming detection phase in `run_turn()`.

## Alternatives Considered

1. **Emit during streaming detection** (rejected): When `_stream_completion()` yields `tool_call_start`, immediately yield a `ToolCallStart` event. Problem: `StreamEvent.tool_calls` is empty at this time — adapters accumulate tool metadata locally and only populate it on the `done` event. Would require modifying all 4 adapter implementations to propagate metadata earlier.

2. **Callback + asyncio.Queue** (rejected): Add `on_tool_start`/`on_tool_end` callbacks to `_execute_tool_calls()`, push events into a queue, drain from `run_turn()`. Problem: Over-engineered. The gather-then-yield pattern achieves the same result with zero new infrastructure.

3. **Emit from execution (chosen)**: Build all events in `_execute_tool_calls()` which already has full tool metadata, return as list, yield from `run_turn()`.

## Rationale

- Full `call_id` and `name` are available at execution time (from `stream_result.tool_calls`)
- No adapter modifications needed (zero blast radius on 4 adapter implementations)
- Semantically correct: "tool started" means "execution started", not "model started generating JSON"
- Deterministic ordering: all starts before gather, all ends after gather (simplifies frontend rendering)
- ~60 lines vs ~120 lines for the alternatives

## Consequences

- `ToolCallStart` events are slightly delayed compared to streaming detection (by the time arguments finish streaming). In practice this is milliseconds — tools themselves take seconds.
- Event ordering is deterministic (all starts, then all ends) rather than interleaved (start1, end1, start2, end2). This is simpler but less "real-time" for long-running parallel tools.
