---
type: DISCOVERY
date: 2026-03-29
project: kailash
topic: Delegate streaming has a type-boundary gap preventing tool event emission
phase: analyze
tags: [kaizen-agents, delegate, streaming, events, architecture]
---

# Delegate Streaming Architecture Gap

## Discovery

The Delegate streaming pipeline has a type-boundary mismatch at the loop-to-delegate layer that prevents tool call events from reaching consumers:

- **Layer 0** (Adapters): Emit `StreamEvent` with `tool_call_start` — but `StreamEvent.tool_calls` is empty at this time (metadata accumulated locally, only populated at `done` time)
- **Layer 1** (`_stream_completion`): Converts to `(event_type, StreamResult)` — forwards the empty metadata
- **Layer 2** (`run_turn`): Typed as `AsyncGenerator[str, None]` — can only yield text, discards tool events as a boolean flag
- **Layer 3** (`Delegate.run`): Yields `DelegateEvent` — documents `ToolCallStart`/`ToolCallEnd` in docstring but never emits them

## Key Insight

The correct emission point for `ToolCallStart`/`ToolCallEnd` is `_execute_tool_calls()`, NOT during streaming detection. At execution time, the full tool metadata (`call_id`, `name`) is available in `stream_result.tool_calls`. This also has better semantic meaning: "tool execution started" is what frontends care about, not "model started generating tool call JSON".

## Additional Discovery

Three hidden consumers of `run_turn()` beyond `Delegate.run()`: `run_interactive()` (line 730), `run_print()` (line 771), and `PrintRunner` (print_mode.py:87). All three do `full_text += chunk` and would crash on `DelegateEvent` objects. They need isinstance filtering.

## Impact

This gap is the subject of GH #159 and blocks frontend integration for applications needing tool execution status (spinners, SSE events). The fix requires widening `run_turn()` to `AsyncGenerator[str | DelegateEvent, None]` — a minimal internal API change with no adapter modifications needed.
