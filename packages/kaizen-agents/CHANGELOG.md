# Changelog

All notable changes to the kaizen-agents package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.4] - 2026-04-21 — ToolRegistry pre-hydrate eliminates discovery tax (#579)

### Added

- **`ToolHydrator.pre_hydrate_from_query(query, top_k=5)`** — BM25 retrieval over the deferred tool index, seeded with the user's own input. When the hydrator is active (tool count above threshold), the top-K matches are merged into the active set so the LLM sees candidate tools on turn 1. Prior behaviour required a dedicated `search_tools` meta-call on turn 1 before the LLM could emit the real data-tool call on turn 2 — a 25% overhead on an 8-turn budget (issue #579, documented in ImpactVerse/Iris live staging).
- **`AgentLoop.run_turn`** now invokes `pre_hydrate_from_query(user_message, top_k=5)` once per turn before the first LLM completion. `search_tools` remains available as the escape hatch when the BM25 pre-hydrate misses.
- **System prompt addendum** — the default system prompt now tells the LLM it can batch a `search_tools + real_tool` pair in a single tool-call batch when the target name is known, saving the round-trip on models that support parallel tool calls (GPT-4-class).

### Why this is LLM-first compatible

Pre-hydration is **retrieval, not routing or classification**. The framework runs a BM25 scoring pass (documented data operation) and merges results into the visible tool set. The LLM still decides whether to invoke any hydrated tool, which one, and how. `search_tools` is preserved for queries where the pre-hydrate misses — the multi-hop discovery path is unchanged. See `rules/agent-reasoning.md` Permitted Exception 6 (tool-result parsing / retrieval as data operation).

### Behavior change

Tool-call latency drops by ~600ms and turn-budget consumption drops by 25% on the common case where the user's natural-language query contains tokens that BM25 resolves to the correct candidates. Token cost per turn increases slightly (~600 tokens of hydrated tool schemas) — amortized over session length.

### Tests

- 9 new Tier 1 unit tests at `packages/kaizen-agents/tests/unit/delegate/test_tool_hydration.py::TestPreHydrateFromQuery` + `TestAgentLoopCallsPreHydrate` covering: top-K BM25 hits, `top_k` cap, inactive-hydrator no-op, empty-query no-op, no-match no-op, active-set idempotence across repeated queries, `search_tools` escape-hatch preservation, `AgentLoop.run_turn` invocation on active hydrator, and skip on inactive hydrator.

### Cross-SDK

Filed as follow-up for kailash-rs if `DefaultToolHydrator::search` + hot-path wiring shows the same pattern. Rust semantic parity MUST use the same method name and same behavior per `rules/cross-sdk-inspection.md` EATP D6.

Closes #579.

## [0.9.3] - 2026-04-15 — Python 3.14 compatibility

### Fixed

- **`DataFlowConnection.get_table_schema`** previously called `model.__annotations__` directly, which raises `NameError` instead of returning the annotation dict on Python 3.14 when a model uses any string forward reference. Replaced with `kailash.utils.annotations.get_resolved_type_hints(model)`, which evaluates the lazy 3.14 `__annotate__` callable safely and surfaces a clear per-field error if any forward reference is unresolvable.

## [0.7.0] - 2026-04-07

### Added

- **Top-level pattern exports** — All 5 multi-agent pattern classes (`BaseMultiAgentPattern`, `SupervisorWorkerPattern`, `ConsensusPattern`, `DebatePattern`, `HandoffPattern`, `SequentialPipelinePattern`) and 5 factory functions now exported from `kaizen_agents` top-level
- Deprecated `coordination/` module removed; 33 files migrated to `patterns/`

## [0.5.0] - 2026-03-30

### Added

- **ToolCallStart/ToolCallEnd event wiring** — Delegate streaming now emits all 6 defined event types. Applications can pattern-match on `ToolCallStart(name=...)` and `ToolCallEnd(name=..., result=...)` for tool execution visibility (spinners, SSE, progress bars). Closes #159.
- 8 new unit tests for tool call event emission, ordering, error handling, multi-turn, and consumer compatibility.

### Fixed

- **Error message sanitization** — `str(exc)` replaced with `type(exc).__name__` in 5 error paths (`Delegate.run()`, `PrintRunner.run()`, `AgentLoop._run_single()`, `run_interactive()`, `HookManager._run_hook()`). Prevents internal detail leakage (file paths, connection strings) via events and API responses.

### Changed

- `AgentLoop.run_turn()` return type widened to `AsyncGenerator[str | DelegateEvent, None]` (internal API — only consumed by `Delegate.run()`).
- `AgentLoop._execute_tool_calls()` now returns `list[DelegateEvent]` instead of `None`.
- `run_interactive()`, `run_print()`, and `PrintRunner.run()` filter non-string chunks from `run_turn()`.

## [0.4.0] - 2026-03-27

### Added

- **Delegate facade** — `Delegate` class as the primary user-facing API for autonomous AI execution with typed event system, progressive disclosure (Layer 1/2/3), and budget tracking. Closes #114.
- **Incremental streaming** — `AgentLoop.run_turn()` yields text tokens incrementally as they arrive from the model. Closes #115.
- **Multi-provider LLM adapter** — `StreamingChatAdapter` protocol with 4 provider adapters (OpenAI, Anthropic, Google, Ollama). Closes #113.
- **Tool hydration** — `ToolHydrator` with BM25 search for large tool sets (100+ tools). Closes #76.
- **Hook system** — `HookManager` with lifecycle events (PRE/POST tool use, model, session).

## [0.3.0] - 2026-03-25

### Added

- **Structural split**: Absorbed ~44K lines of Layer 2 engine code from kailash-kaizen
- `kaizen_agents.agents/` — 29 specialized agents (ReAct, RAG, ToT, CoT, vision, audio, etc.)
- `kaizen_agents.patterns/` — Multi-agent patterns (debate, supervisor-worker, pipeline, consensus, ensemble)
- `kaizen_agents.journey/` — Journey orchestration with LLM intent detection
- `kaizen_agents.api/` — Canonical async-first Agent API
- `kaizen_agents.workflows/` — Enterprise workflow templates
- `kaizen_agents.coordination/` — Backward-compatibility coordination shims
- `kaizen_agents.integrations/dataflow/` — AI-enhanced database operations
- `kaizen_agents.runtime_adapters/` — Concrete LLM provider adapters
- `kaizen_agents.research_patterns/` — Advanced ML patterns
- Re-exports: `Agent`, `ReActAgent`, `Pipeline` from top-level `kaizen_agents`

### Changed

- Version bump: 0.2.0 → 0.3.0
- Dependency: `kailash-kaizen>=2.3.0` (requires version after structural split)

## [0.2.0] - 2026-03-21

### Added

- Initial release with GovernedSupervisor, Delegate engine, orchestration (planner, protocols, recovery), PACT governance integration
