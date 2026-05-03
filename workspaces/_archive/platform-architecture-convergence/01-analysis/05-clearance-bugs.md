# Clearance Bug Analysis: Issues #363, #364, #367, #368, #377

## Executive Summary

Five bugs across Kaizen (4) and DataFlow (1). Four of the five (#363, #364, #367, #368) are **already fixed and tested** in the current codebase -- their code changes and regression tests landed as part of the platform architecture convergence work. Only **#377 (sync SingleShotStrategy missing MCP tool-call loop)** remains unfixed. The GitHub issues may still be open even though the code is resolved; those four need closing with commit references.

- **Complexity**: Simple (score 8) -- #377 is a straightforward port of existing async logic
- **Effort**: 1 session (parallel: #377 fix + close 4 resolved issues)

---

## Per-Issue Analysis

---

### #363 -- OllamaStreamAdapter strips tool_call_id and name from tool-role messages

**Status**: FIXED

**Root cause**: `_convert_messages_for_ollama()` originally copied only `role` and `content` from every message. Tool-role messages also carry `tool_call_id` (correlates result to the originating tool call) and `name` (function name). Without these fields, Ollama cannot match tool results to their calls, causing malformed conversation history.

**Fix location**: `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ollama_adapter.py` lines 321-325 -- tool-role messages now preserve both fields when present.

**Test**: `packages/kaizen-agents/tests/unit/delegate/adapters/test_ollama_adapter.py` class at line 90, `test_tool_call_id_and_name_preserved`.

**Impact**: Any Kaizen agent using Ollama with tool calling. Without the fix, multi-turn tool-call conversations produce 400 errors or hallucinated responses from the model.

**Risk (fix)**: None -- the fix is already in production code and tested.

---

### #364 -- OllamaStreamAdapter: stream=True + tools incompatible with many Ollama versions

**Status**: FIXED

**Root cause**: Early Ollama versions and OpenAI-compatible proxy servers do not support `stream: true` when `tools` are present in the request body. Sending `stream: true` with tools causes HTTP 400 or silent truncation of the tool_calls array.

**Fix location**: `ollama_adapter.py` line 92 -- `use_stream = not bool(tools)`. When tools are provided, the adapter switches to synchronous (single JSON response) mode. The non-streaming path at lines 131-188 handles the complete response.

**Test**: `test_ollama_adapter.py` line 124, section "Fix 3 -- #364".

**Impact**: All Ollama users with tool-calling agents. Without the fix, tool calls silently fail or return empty results.

**Risk (fix)**: None -- already shipped and tested.

---

### #367 -- OllamaStreamAdapter polish: num_predict default, kwargs options merge, synthetic tool-call ID collisions

Three sub-issues, all FIXED:

#### #367a -- num_predict default

**Root cause**: `default_max_tokens` was not mapped to Ollama's `num_predict` option. The model would use its own default (often very low), causing truncated responses.
**Fix**: Line 100 maps `resolved_max` to `options.num_predict`.

#### #367b -- kwargs options merge

**Root cause**: Caller-supplied `options` dict in kwargs would overwrite the entire `options` block (including temperature and num_predict) instead of merging. Security hardening also added an allowlist (`_ALLOWED_KWARGS` at line 110) to prevent request smuggling via `model`, `messages`, `stream`, or `tools` overwrite.
**Fix**: Lines 110-117 -- allowlisted kwargs only; `options` dict merges via `.update()` instead of overwriting.

#### #367c -- Synthetic tool-call ID collisions

**Root cause**: Original implementation used index-based IDs (`call_0`, `call_1`), which collide across multiple turns of a multi-turn conversation. Collision causes the LLM to misattribute tool results.
**Fix**: Lines 161, 238 use `uuid.uuid4().hex[:12]` for unique IDs: `call_ollama_{uuid}`.

**Tests**: Lines 229 (#367a), 246 (#367b), 304 (#367c) in `test_ollama_adapter.py`.

**Risk (fix)**: None -- already shipped. The uuid4 approach has a negligible collision probability (~1 in 2.8 trillion per ID).

---

### #368 -- \_on_source_change crashes parameterized products by calling execute_product without params

**Status**: FIXED

**Root cause**: `FabricRuntime._on_source_change()` in `packages/kailash-dataflow/src/dataflow/fabric/runtime.py` originally called `pipeline.execute_product(product_name, product_fn, context)` for all products. Parameterized products expect a `params` argument; calling without it causes `TypeError` or produces nonsensical results cached under the bare product name (cache poisoning).

**Fix location**: Lines 883-897 of `runtime.py` -- parameterized products are now detected by `product.mode == ProductMode.PARAMETERIZED` and handled by invalidating all cached parameter combinations via `cache.invalidate_all(prefix=...)` instead of re-executing. Lazy re-population on next request ensures correct params are always supplied by the serving layer.

**Tests**: `packages/kailash-dataflow/tests/regression/test_issue_368_parameterized_source_change.py` -- 4 tests covering: no-crash, cache invalidation, materialized still refreshes, unknown product no-op.

**Impact**: Any DataFlow Fabric user with parameterized data products and source-change detection. Without the fix, source changes crash the runtime or corrupt the cache.

**Risk (fix)**: None -- already shipped with comprehensive regression tests.

---

### #377 -- sync SingleShotStrategy lacks MCP tool-call execution loop

**Status**: UNFIXED

**Root cause**: `AsyncSingleShotStrategy` (in `packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`, lines 78-195) has a full MCP tool-call execution loop: after each LLM response, it checks for `tool_calls`, executes them via `agent.execute_mcp_tool()`, appends tool results to the conversation, and re-submits to the LLM (up to 5 rounds). The sync `SingleShotStrategy` (`packages/kailash-kaizen/src/kaizen/strategies/single_shot.py`) has **none of this logic**. It executes a single LLM call and returns, silently dropping any tool calls the model requests.

**Impact**: Any `BaseAgent` subclass explicitly using the sync strategy path with MCP tools. The default `BaseAgent` uses `AsyncSingleShotStrategy`, so the impact is limited to:

- Users who explicitly construct `SingleShotStrategy()` and pass it as the strategy
- Example code and documentation that references `SingleShotStrategy`
- The `content-generation` enterprise workflow example

The agent appears to work, but tool calls are silently ignored -- the model's intent to use tools is lost, and the response contains only the pre-tool-call text (often just "I'll use the X tool to..." with no actual result).

**Complexity**: Low. The fix is a port of the async loop to sync form:

1. Add `_extract_tool_calls()` and `_extract_assistant_content()` helper methods (can be copied from `AsyncSingleShotStrategy`)
2. Add the tool-call loop in `execute()` after the initial workflow execution
3. Replace `await agent.execute_mcp_tool()` with sync equivalent or `asyncio.run()` wrapper
4. Add `_TOOL_NAME_RE` validation (security: tool name allowlist)
5. Regression test: `test_issue_377_sync_single_shot_tool_calls.py`

**Dependencies**: None. Independent of the Ollama adapter chain.

**Risk (fix)**:

- **LOW**: Logic is well-understood (copy from async variant)
- **MEDIUM**: Sync execution of potentially-async MCP tool calls requires care -- `agent.execute_mcp_tool()` is async, so the sync strategy must handle the event loop bridging
- **LOW**: No API surface change -- behavior becomes correct (tool calls are honored) instead of silently broken

---

## Dependency Map

```
#363 (tool_call_id stripped) -----> FIXED
   |
   v
#364 (stream+tools compat)  -----> FIXED
   |
   v
#367 (polish: 3 sub-issues) -----> FIXED

#368 (parameterized _on_source_change) --> FIXED

#377 (sync SingleShotStrategy MCP loop) --> UNFIXED
```

## Implementation Plan

**Phase 1** (single session):

1. Fix #377: Port MCP tool-call loop to sync `SingleShotStrategy`
2. Write regression test `test_issue_377_sync_single_shot_tool_calls.py`
3. Close issues #363, #364, #367, #368 with commit references

## Risk Register

| Risk                                      | Likelihood | Impact | Level       | Mitigation                                                       |
| ----------------------------------------- | ---------- | ------ | ----------- | ---------------------------------------------------------------- |
| #377 sync/async bridge fails              | Low        | Medium | Significant | Use same pattern as `Delegate.run_sync()` (thread pool executor) |
| Closing fixed issues without verifying CI | Low        | Low    | Minor       | Verify regression tests pass in CI before closing                |
| Sync SingleShotStrategy is rarely used    | Medium     | Low    | Minor       | Still must be fixed -- public API parity with async variant      |

## Success Criteria

- [ ] #377: sync `SingleShotStrategy.execute()` honors MCP tool calls (up to 5 rounds)
- [ ] #377: Regression test verifies tool-call round-trip in sync mode
- [ ] #377: Tool name validation matches async variant (`_TOOL_NAME_RE`)
- [ ] #363, #364, #367, #368: GitHub issues closed with commit references
- [ ] All existing tests continue to pass
