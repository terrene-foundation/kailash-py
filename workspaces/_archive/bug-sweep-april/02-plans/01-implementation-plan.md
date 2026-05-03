# Bug Sweep — April 2026 Implementation Plan

## Scope

Fix 9 user-facing bugs across Kaizen (#339, #340, #357), DataFlow (#362, #368), and kaizen-agents Ollama adapter (#361, #363, #364, #367). Close #355 (already fixed).

## PR Strategy

5 PRs organized by code area, each independently mergeable:

### PR A — Ollama adapter fixes (#361 + #363 + #364 + #367)

**File**: `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/ollama_adapter.py` (214 lines)
**Fixes**:

- #361: Deserialize tool-call arguments from JSON string back to dict in `_convert_messages_for_ollama()`
- #363: Pass through `tool_call_id` and `name` for tool-role messages
- #364: Disable streaming when tools are present; add non-streaming response parser
- #367a: Lower `default_max_tokens` from 16384 to 4096
- #367b: Merge `kwargs["options"]` instead of overwriting
- #367c: Use `uuid.uuid4().hex[:12]` for synthetic tool-call IDs
  **Test**: New `test_ollama_adapter.py`

### PR B — Gemini provider fix (#340 + #357)

**Files**:

- `packages/kailash-kaizen/src/kaizen/providers/llm/google.py`
- `packages/kailash-kaizen/src/kaizen/core/workflow_generator.py`
  **Fixes**:
- #340: Strip `response_mime_type` and `response_json_schema` from config when tools are present (in both `chat()` and `chat_async()`)
- #357: Defense-in-depth — drop `response_format` from node_config when provider is google/gemini and tools are present
  **Tests**: Add case to existing `test_google_provider.py`; new `test_workflow_generator_gemini_tools.py`

### PR C — DataFlow Fabric fixes (#362 + #368)

**Files**:

- `packages/kailash-dataflow/src/dataflow/fabric/pipeline.py`
- `packages/kailash-dataflow/src/dataflow/fabric/runtime.py`
  **Fixes**:
- #362: Wrap sync `product_fn` calls in `asyncio.to_thread()` instead of direct invocation
- #368: Skip parameterized products in `_on_source_change()` — invalidate all cached param combinations instead of crashing
  **Tests**: New `test_issue_362_sync_product_blocks_loop.py` and `test_issue_368_parameterized_source_change.py`

### PR D — BaseAgent MCP tool execution (#339)

**Files**:

- `packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`
- `packages/kailash-kaizen/src/kaizen/core/mcp_mixin.py` (remove debug spew)
  **Fix**: Add tool-call execution loop after workflow execution in `AsyncSingleShotStrategy.execute()`. Check LLM response for `tool_calls`, execute via `agent.execute_mcp_tool()`, re-submit with results, loop up to 5 rounds.
  **Test**: New `test_async_single_shot_tool_calls.py`

### PR E — Close #355 (already fixed)

No code change. Close issue with reference to existing fix.

## Execution Order

PRs A, B, C are independent — execute in parallel.
PR D is independent but the largest fix — can run in parallel or after A/B/C.
PR E is administrative — close immediately.

## Branch Strategy

Single branch `fix/bug-sweep-april` from main. One commit per PR-equivalent (5 commits). Single PR to main.
