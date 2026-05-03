# Sprint S11 Analysis — Delegate Tool Call Event Wiring

**Date**: 2026-03-29
**Issues**: #159
**Status**: Analysis phase

## Open Issues

| #       | Title                                                       | Type | Severity | Dependencies |
| ------- | ----------------------------------------------------------- | ---- | -------- | ------------ |
| **159** | Wire ToolCallStart/ToolCallEnd events in Delegate streaming | FEAT | HIGH     | None         |

## Issue #159: ToolCallStart/ToolCallEnd Event Wiring

### Problem Statement

The Delegate streaming system defines six event types but only emits four. `ToolCallStart` and `ToolCallEnd` are fully defined in `events.py` (lines 72-100) with correct dataclass structure, but never yielded during `Delegate.run()`. Applications that need tool execution visibility (spinners, progress bars, structured SSE) must build custom agent loops — defeating the Delegate's purpose as a reusable autonomous engine.

### Architecture Analysis

The streaming pipeline has three layers with a type mismatch at the boundary between loop and delegate:

```
Layer 3: Delegate.run()           yields DelegateEvent (TextDelta, TurnComplete, ...)
         ↑ consumes str chunks from Layer 2
Layer 2: AgentLoop.run_turn()     yields str (text deltas only)
         ↑ consumes (event_type, StreamResult) from Layer 1
Layer 1: _stream_completion()     yields ("text"|"tool_call_start"|..., StreamResult)
         ↑ consumes StreamEvent from adapter
Layer 0: StreamingChatAdapter     yields StreamEvent with tool_call_start/end events
```

**The gap**: Layer 1 emits `tool_call_start` events, but Layer 2 discards them (line 497: `has_tool_calls = True` — flag only, no yield). Layer 2's `_execute_tool_calls()` runs tools in parallel but emits nothing about execution progress. Layer 3 only receives `str` chunks, so it cannot distinguish text from tool events.

### Root Cause

`AgentLoop.run_turn()` (line 444) is typed as `AsyncGenerator[str, None]`. It can only yield text strings. When the streaming adapter reports a tool call starting, the loop sets a boolean flag and moves on. When tools execute, the method runs them silently and appends results to the conversation — no event is surfaced to the Delegate.

The Delegate's `run()` method (line 268) documents yielding `ToolCallStart` and `ToolCallEnd` in its docstring, but the implementation at lines 309-343 only processes `str` chunks as `TextDelta`.

### Existing Infrastructure (What's Already Done)

| Component                                  | File                                   | Lines    | Status          |
| ------------------------------------------ | -------------------------------------- | -------- | --------------- |
| `ToolCallStart` dataclass                  | `delegate/events.py`                   | 72-82    | Complete        |
| `ToolCallEnd` dataclass                    | `delegate/events.py`                   | 86-100   | Complete        |
| `DelegateEvent` base class                 | `delegate/events.py`                   | 45-56    | Complete        |
| `_stream_completion()` emits tool events   | `delegate/loop.py`                     | 524-614  | Complete        |
| `_execute_tool_calls()` parallel execution | `delegate/loop.py`                     | 616-687  | Complete        |
| Streaming adapter protocol                 | `delegate/adapters/protocol.py`        | 27-51    | Complete        |
| Event type unit tests                      | `tests/unit/delegate/test_delegate.py` | ~160-173 | Type tests only |

**Estimated: 80% of the infrastructure exists. Only the wiring is missing.**

### Red Team Findings (Incorporated)

| #   | Severity | Finding                                                                                                                                | Resolution                                                                                   |
| --- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| F1  | CRITICAL | `call_id`/`name` not in `StreamResult` at `tool_call_start` time — adapters don't populate `StreamEvent.tool_calls` until `done` event | Emit `ToolCallStart` from `_execute_tool_calls()` where full metadata is available           |
| F2  | HIGH     | `run_interactive()`, `run_print()`, and `PrintRunner` also consume `run_turn()` — not just `Delegate.run()`                            | All three must filter `isinstance(chunk, str)` to skip `DelegateEvent` objects               |
| F3  | HIGH     | `run_interactive()` crashes on `DelegateEvent` objects (`display.append_text(chunk)` and `full_text += chunk`)                         | Filter at minimum; enhanced tool display is future scope                                     |
| F7  | MEDIUM   | `asyncio.Queue` callback approach over-engineered — simpler gather-then-yield pattern exists                                           | Use gather-then-yield: parallel tools complete via `asyncio.gather`, then yield sequentially |
| F6  | MEDIUM   | Test plan missing multi-turn tool scenario (tool turn 1 -> text turn 2 in same `run_turn()` call)                                      | Added to test plan                                                                           |

### Implementation Approach (Post Red Team)

Widen `run_turn()` yield type to `str | DelegateEvent`. Emit `ToolCallStart` and `ToolCallEnd` from `_execute_tool_calls()` (not during streaming detection), where full tool metadata is available.

**Why NOT emit during streaming detection**: At `tool_call_start` time in the stream, `StreamEvent.tool_calls` is empty — adapters accumulate tool metadata locally and only populate it at `done` time. The full `call_id` and `name` are only available in `stream_result.tool_calls` after the stream completes, which is exactly when `_execute_tool_calls()` is called.

**Semantic correctness**: "ToolCallStart" meaning "tool execution started" (not "model started generating tool call JSON") is more useful for frontends showing spinners. The model's streaming of tool call arguments is an internal detail; the user cares when the tool actually runs.

#### Changes Required (7 files)

**1. `loop.py:run_turn()` — Type annotation + event yielding**

- Change return type: `AsyncGenerator[str, None]` -> `AsyncGenerator[str | DelegateEvent, None]`
- Import `ToolCallStart`, `ToolCallEnd` from `events.py`
- At line 519, replace `await self._execute_tool_calls(...)` with yield-from pattern

**2. `loop.py:_execute_tool_calls()` — Return events alongside conversation updates**

- Change return type from `None` to `list[DelegateEvent]`
- Emit `ToolCallStart` for each tool BEFORE `asyncio.gather`
- After gather completes, emit `ToolCallEnd` for each result
- Continue appending to conversation as before

**3. `delegate.py:run()` — Dispatch on type**

- `isinstance(chunk, str)` -> wrap in `TextDelta` (current behavior)
- `isinstance(chunk, DelegateEvent)` -> yield as-is
- Guard `accumulated_text += chunk` to only operate on strings

**4. `loop.py:run_interactive()` line 730 — Filter DelegateEvents**

- Add: `if not isinstance(chunk, str): continue`

**5. `loop.py:run_print()` line 771 — Filter DelegateEvents**

- Add: `if not isinstance(chunk, str): continue`

**6. `print_mode.py:PrintRunner.run()` line 87 — Filter DelegateEvents**

- Add: `if not isinstance(chunk, str): continue`

**7. `tests/unit/delegate/test_delegate.py` — New event emission tests**

#### Event Emission Pattern

```python
# In _execute_tool_calls (simplified):
async def _execute_tool_calls(self, tool_calls) -> list[DelegateEvent]:
    events: list[DelegateEvent] = []

    # Emit ToolCallStart for each tool before execution
    for tc in tool_calls:
        events.append(ToolCallStart(
            call_id=tc["id"], name=tc["function"]["name"]
        ))

    # Execute all tools in parallel (unchanged)
    results = await asyncio.gather(
        *[_run_single(tc) for tc in tool_calls], return_exceptions=True
    )

    # Process results and emit ToolCallEnd (unchanged conversation logic)
    for idx, result in enumerate(results):
        tc = tool_calls[idx]
        if isinstance(result, BaseException):
            events.append(ToolCallEnd(
                call_id=tc["id"], name=tc["function"]["name"],
                error="Tool execution was interrupted"
            ))
            self._conversation.add_tool_result(...)
        else:
            tc_id, name, content = result
            events.append(ToolCallEnd(
                call_id=tc_id, name=name, result=content
            ))
            self._conversation.add_tool_result(tc_id, name, content)

    return events

# In run_turn (at line 519):
    tool_events = await self._execute_tool_calls(stream_result.tool_calls)
    for event in tool_events:
        yield event
```

### Event Ordering Guarantee

```
TextDelta("Let me search for that...")     # Model reasoning (optional)
ToolCallStart(call_id="tc_1", name="web_search")   # All starts emitted before execution
ToolCallStart(call_id="tc_2", name="read_file")
ToolCallEnd(call_id="tc_1", name="web_search", result="...")   # Ends in gather order
ToolCallEnd(call_id="tc_2", name="read_file", result="...")
TextDelta("Based on what I found...")      # Next turn's text
TurnComplete(text="...", usage={...})
```

All `ToolCallStart` events are emitted before parallel execution begins. `ToolCallEnd` events are emitted after `asyncio.gather` completes (order matches `tool_calls` list order, not completion order). This provides deterministic ordering — simpler for frontend rendering.

### Scope Estimate

~60-90 lines of production code across 4 files (`loop.py`, `delegate.py`, `print_mode.py` + imports). ~60-100 lines of new tests. Estimated: 1 autonomous session.

### Test Plan

1. **Unit**: FakeAdapter with tool calls -> verify `ToolCallStart` emitted by `Delegate.run()`
2. **Unit**: Tool execution -> verify `ToolCallEnd` emitted with correct result/error fields
3. **Unit**: Parallel tool calls -> verify multiple `ToolCallStart` + `ToolCallEnd` pairs
4. **Unit**: Tool error -> verify `ToolCallEnd` with error field populated, result empty
5. **Unit**: Multi-turn scenario (turn 1: tools, turn 2: text-only) -> verify correct event sequence across turns
6. **Unit**: Budget exhaustion mid-tool -> verify clean event sequence
7. **Regression**: Existing `TextDelta` and `TurnComplete` behavior unchanged
8. **Regression**: `run_sync()` ignores tool events (returns text only)
9. **Regression**: `run_print()` and `run_interactive()` continue working with str-only filtering

### Cross-SDK Alignment

Issue #159 notes the same gap exists in kailash-rs (`CallerEvent::ToolCallStart` defined but never emitted in `streaming/agent.rs`). A cross-SDK issue should be filed after implementation, including:

- Matching event field names (`call_id`, `name`, `result`, `error`)
- Matching ordering guarantee (all starts before execution, ends after gather)
- Spec-level requirement that both SDKs emit these events

### Risk Assessment

| Risk                                        | Severity   | Mitigation                                                                   |
| ------------------------------------------- | ---------- | ---------------------------------------------------------------------------- |
| Breaking existing consumers of `run_turn()` | MEDIUM     | 3 hidden consumers (F2/F3) — all need `isinstance` filter (6 lines total)    |
| Event ordering confusion                    | LOW        | Deterministic: all starts before gather, ends in list order after gather     |
| Performance overhead of yielding events     | NEGLIGIBLE | One yield per tool call — tools are already the bottleneck                   |
| `run_sync()` compatibility                  | LOW        | Verified: tool events fall through with no handler (correct)                 |
| Adapter changes needed                      | NONE       | Resolved by emitting from `_execute_tool_calls()` instead of streaming layer |
