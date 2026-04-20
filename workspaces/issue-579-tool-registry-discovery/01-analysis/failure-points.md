# Failure-Point Analysis — Issue #579 ToolRegistry Discovery Tax

**Framework**: Kaizen (Delegate + ToolRegistry + ToolHydrator)
**Scope**: Python SDK (`packages/kaizen-agents/src/kaizen_agents/delegate/`) + cross-SDK parity with `crates/kaizen-agents/src/hydration/` in kailash-rs
**Date**: 2026-04-20
**Source code anchors**:

- `packages/kaizen-agents/src/kaizen_agents/delegate/loop.py::AgentLoop._setup_hydration` (lines 349–391)
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py::ToolHydrator` (entire file)
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/search.py::create_search_tools_executor` (lines 70–131)
- `packages/kaizen-agents/src/kaizen_agents/delegate/config/loader.py::KzConfig.max_turns = 50` (line 138)
- `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py` default `max_turns=50` (line 356); `AgentEngine` default is 20 (line 293)

## 1. Architecture Recap

`ToolHydrator` (Python) / `DefaultToolHydrator` (Rust) sits between `ToolRegistry` and the LLM call. When the total tool count exceeds the threshold (Python: 30, Rust: config-driven), only a **base/always-active set** (~15 tools incl. `search_tools`) is sent to the LLM. All other tools are **deferred** — indexed by a BM25-style (Python) or TF-IDF-style (Rust) scorer but NOT sent in the `tools` parameter of the chat completion.

When the LLM needs a deferred tool, the flow is:

```
Turn N  : LLM emits tool_call search_tools(query="<verb-phrase>")
          → executor: hydrator.search(query) → [ranked tool names]
          → executor: hydrator.hydrate([...]) → adds names to _hydrated_names set
          → tool_result appended to conversation (JSON blob with ranked results)
          → has_tool_calls=True → loop goes back to _stream_completion

Turn N+1: LLM call now includes hydrated tools in the `tools` parameter
          → LLM emits the REAL tool call it wanted
          → executor runs; result appended
          → has_tool_calls=True → loop goes back to _stream_completion

Turn N+2: LLM sees the real-tool result → may emit text OR more tool calls
```

This is the "discovery tax": the turn budget advances by two every time a Delegate request needs a deferred tool, and only one of those two turns did user-visible work.

## 2. Load-Bearing Invariants

The current implementation holds these invariants; any fix MUST NOT break them:

1. **LLM decides discovery** (`rules/agent-reasoning.md` — MUST Rule 1). No deterministic code classifies the user prompt to pre-hydrate. The `search_tools` call is emitted by the LLM, not the framework.
2. **`search_tools` is a dumb data endpoint** (rule MUST 2). It fetches ranked tool names and mutates hydrator state via `hydrate()`; it does NOT decide which tools should run.
3. **Base tools fit in context** — the `_DEFAULT_BASE_TOOL_NAMES` frozenset (`file_read`, `file_write`, `file_edit`, `glob`, `grep`, `bash`, `search_tools`) is 7 entries; the threshold of 30 assumes ~15 base tools and ~85% deferred.
4. **Hydration is sticky within a conversation** (`hydrator.dehydrate()` clears but the loop never calls it automatically). Once discovered, a tool stays in the active set for the rest of the conversation.
5. **`ToolRegistry` is the execution surface, hydrator is the visibility surface** — `AgentLoop._execute_tool_calls` uses `hydrator.get_executor_force()` which bypasses the active-set check (loop.py line 683), so a tool hydrated mid-batch still executes. This is a subtle but load-bearing guard that allows `search_tools + real_tool` in ONE turn's tool-call batch (if the LLM emits them together) — which is the escape hatch we later examine in Option 4.
6. **Turn budget is the scarce resource** — `KzConfig.max_turns = 50`, `Delegate(max_turns=50)`, `AgentEngine(max_turns=20)`. Every discovery tax consumes 1 of N turns per Delegate session.

## 3. Where Does "2 of N Turns Lost per Delegate Request" Come From?

Each Delegate request = one `AgentLoop.run_turn(user_message)` call. Inside `run_turn`, there is an **inner loop** that counts up to `max_turns`:

```python
while inner_turns < self._config.max_turns:   # loop.py:475
    inner_turns += 1
    ...
    if not has_tool_calls: return              # user-visible text reply
    # else: tool calls → append results → loop
```

An "inner turn" = one LLM completion round. So a Delegate request that needs a deferred tool spends:

- **1 inner turn**: LLM sees base-tool schemas, emits `search_tools(query)`, executor hydrates matches
- **1 inner turn**: LLM sees hydrated-tool schema, emits real tool call, executor runs
- **1 inner turn** (often): LLM sees tool result, emits final text (or more tools)

If the Delegate request's `max_turns` budget is 5–10 (typical for an in-conversation sub-agent), losing 2 to discovery is 20–40% of the budget. For `max_turns=50` (default interactive kz), losing 2 is 4% — but the issue title "2 of N turns lost per Delegate request" is specifically about **Delegate requests**, which tend to have smaller budgets.

## 4. How Does `search_tools` Actually Hydrate?

Reading `search.py::_execute_search_tools` lines 90–131:

1. `hydrator.search(query, top_n=10)` — BM25 over deferred `_ToolDoc` corpus; returns `[{name, description, score}]`.
2. `hydrator.hydrate([r["name"] for r in results])` — adds ALL top_n results to `_hydrated_names`. **Note**: the executor hydrates EVERY search result, not just the top-1. The LLM can then pick any of them on turn N+1.
3. Returns JSON blob with `{query, results, hydrated, message}` to the model.

The hydrator tokenizes with `re.findall(r"[a-z0-9]+", text.lower())` (hydrator.py line 72) and scores with `k1=1.5, b=0.75` BM25 plus a `+2.0` exact-name-match boost (line 136–137). The index is built once in `load_tools()` and does not update.

## 5. Five-Why Root Cause

- **Why 1**: Two turns are spent per discovery. → Because the LLM cannot see the deferred tools' schemas without calling `search_tools` first.
- **Why 2**: Why can't it see them? → Because `_setup_hydration` only sends base + hydrated tools to the `tools=` parameter of the chat completion (loop.py:566–569).
- **Why 3**: Why is the set so small? → Because sending all 30+ tool schemas on every call wastes tokens AND degrades model accuracy (documented in `hydrator.py` docstring lines 5–10).
- **Why 4**: Why is the only discovery mechanism a round-trip through `search_tools`? → Because the hydrator assumes the LLM is the ONLY classifier that can match a free-form user request to a tool (MUST Rule 1 of `agent-reasoning.md`).
- **Why 5**: Why can't the match happen on turn N instead of N+1? → **This is the leverage point.** The framework could use the user's turn-N input (not the model's reasoning) to pre-populate hydrator state BEFORE the first LLM call. The framework is not classifying the user's intent; it is running a content-addressable index over the input and showing the LLM relevant tools. That is data-retrieval, not decision-making — the same semantic slot RAG occupies, which `agent-reasoning.md` Permitted Exception 6 ("Tool result parsing") and the broader principle of "dumb data endpoints" explicitly allow.

## 6. Failure Modes of the Current Design

### 6a. Discovery-tax amplification in sub-agent calls

A Delegate configured with `max_turns=5` that needs three different deferred tools spends 6 of 5 turns on discovery (clipped at 5). The sub-agent either:

- Returns a partial answer (discovered tools 1 & 2, never got to 3)
- Emits "Max turns reached" warning (loop.py:534) — a WARN that the caller cannot recover from

### 6b. First-call empty hydrator

On every fresh Delegate conversation, `_hydrated_names = set()` (hydrator.py:202). The first real tool call always pays the tax. Long sessions amortize, short sessions pay every time.

### 6c. LLM may not call `search_tools` even when it should

The LLM is prompted with the `search_tools` description (search.py:35–41), but there is no hard guarantee it emits the call. For ambiguous queries ("check the db") the LLM may guess a base-tool answer, get it wrong, and retry — same turn cost, worse output.

### 6d. BM25 relevance blind spots

BM25 with a `+2.0` name-match boost is verb-biased. Queries like "read the metrics" match `read_file` (base tool) above specialized tools like `metrics_query` (deferred). The LLM then uses the wrong tool on turn N+1 because the "wrong" match was hydrated with score 3.2 while the "right" match got score 0.8 and wasn't in top_n.

### 6e. `_hydrated_names` grows unboundedly

`hydrate()` (hydrator.py:276) adds to the set; `dehydrate()` clears everything; there is NO LRU eviction. In Rust, `ToolHydratorConfig.max_hydrated: 50` provides a cap via eviction (mod.rs:142–143); Python has no equivalent. Over a long session a 600-tool registry can hydrate all 600, defeating the purpose.

### 6f. Rust/Python default drift

- Rust: `auto_include_search_tool: true` and `max_hydrated: 50` (mod.rs:149–155). Hydration is effectively always-on once a hydrator is constructed.
- Python: `threshold: 30` — below 30 tools, no hydration; above, hydration kicks in but with no max-hydrated cap.

These defaults are _not_ in EATP D6 semantic parity. A user migrating a Rust Delegate to Python, or vice versa, gets different discovery behavior.

## 7. Related Patterns Already in the Codebase

- `packages/kailash-kaizen/src/kaizen/tools/native/registry.py::KaizenToolRegistry.get_tool_schemas(filter_category=...)` (line 248–265) — already supports **category filtering** at the registry layer. This is a pre-existing primitive for scoping which tools the LLM sees.
- `packages/kailash-kaizen/src/kaizen/tools/types.py::ToolCategory` — structured categorical tagging that hydrator.py IGNORES when building its index. The search index is pure-text, even though category metadata is available.
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py::_build_search_index` (line 211) — rebuilds from scratch; no incremental update path. If a tool is registered mid-session, the index is stale.

These are existing primitives the remediation should compose with, not re-implement.

## 8. Scope of the Problem

| Surface                                                   | LOC  | Load-bearing?                    |
| --------------------------------------------------------- | ---- | -------------------------------- |
| `hydrator.py::ToolHydrator`                               | 362  | Yes — state machine              |
| `search.py::_execute_search_tools`                        | 45   | Yes — hot path                   |
| `loop.py::_setup_hydration`                               | 43   | Yes — bootstrap                  |
| `loop.py::_execute_tool_calls::get_executor_force` branch | 8    | Yes — enables single-turn escape |
| Rust `hydration/search.rs` + `mod.rs` + `meta_tool.rs`    | ~800 | Yes — same roles                 |

Total load-bearing logic: ~500 Python LOC + ~800 Rust LOC. Single-shard work per `autonomous-execution.md` capacity budget (≤500 LOC, ≤5 invariants, ≤3 call-graph hops).

## 9. Invariants Any Fix Must Preserve

1. LLM-first reasoning — no code classification of user intent (`agent-reasoning.md` MUST 1)
2. Tools remain dumb endpoints (MUST 2)
3. Base-tool set stays small enough to fit alongside hydrated tools in the context window
4. `search_tools` still available for multi-hop discovery (the LLM may want to search twice)
5. Cross-SDK semantic parity — whatever Python does, Rust does equivalently (`rules/cross-sdk-inspection.md` EATP D6)
6. No regression in the single-turn escape hatch (loop.py:682–686) — LLM may still batch `search_tools + real_tool` in one tool-call batch
