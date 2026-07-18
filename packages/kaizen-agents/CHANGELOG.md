# Changelog

All notable changes to the kaizen-agents package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] — 2026-07-18 — governance_required posture on the orchestration egress chokepoint (#1779)

### Added

- **`governance_required` posture enforcement for the orchestration subsystem
  (#1779, EATP D6 parity).** The orchestration components (planner / recovery /
  protocols / monitor / context) egress via `kaizen_agents.llm.LLMClient` (the
  raw OpenAI SDK), NOT the gated four-axis `kaizen.llm.LlmClient`. `LLMClient`
  now enforces the core `kailash.is_governance_required()` posture at its
  construction chokepoint: when the posture is ACTIVE, a bare client is refused
  fail-closed with `kailash.trust.pact.UngovernedEgressRefused` unless
  constructed with `ungoverned=True`. Because every orchestration component
  INJECTS a single `LLMClient` (dependency injection), this one chokepoint +
  the `ungoverned` opt-out covers all orchestration egress. OFF by default —
  byte-identical to prior behavior.

## [0.9.11] — 2026-06-17 — Gemini adapters on supported google-genai SDK; provider SDKs are runtime deps

### Changed

- **Gemini adapters migrated from the deprecated `google.generativeai` SDK to
  the supported `google.genai` SDK** (#1351). `delegate/adapters/google_adapter.py`
  and `runtime_adapters/gemini_cli.py` now use `genai.Client` +
  `client.aio.models.generate_content_stream` + `types.GenerateContentConfig` /
  `types.Tool` / `types.ToolCodeExecution` (generation knobs moved from the model
  object into the per-request config). No `FutureWarning` from the end-of-life
  package on the Gemini path.

### Fixed

- **Provider SDKs declared as runtime dependencies** (#1351). `google-genai` and
  the sibling `anthropic` (which had the identical defect) were declared only in
  `[dev]` extras yet imported at runtime by their adapters — so a normal
  `pip install kaizen-agents` raised `ImportError` on the Gemini / Anthropic path.
  Both are now `[project.dependencies]`; the deprecated `google-generativeai` pin
  is removed. Regression coverage:
  `tests/regression/test_issue_1351_google_genai_migration.py`.

## [0.9.10] — 2026-06-11 — enforce the slim-core import fix via the kailash-kaizen floor

### Changed

- **`kailash-kaizen` floor raised to `>=2.25.1`.** The slim-core
  `import kaizen_agents.patterns` contract claimed in 0.9.9 is only actually
  satisfied by kailash-kaizen 2.25.1, which lazy-loads the optional-extra autonomy
  hooks (`structlog` / `prometheus-client` / `opentelemetry`). Pinning the floor
  guarantees a fresh `pip install kaizen-agents` receives the fixed kaizen. No
  kaizen-agents source change.

## [0.9.9] — 2026-06-11 — slim-core import contract + ruff-clean test dirs + deprecation fixes

### Fixed

- **`import kaizen_agents.patterns` no longer requires optional heavy
  dependencies** (F31-FU5 sibling): `patterns/runtime.py` and
  `patterns/state_manager.py` moved runtime-optional type references behind
  `from __future__ import annotations`, completing the slim-core import contract
  (pinned by the kailash-kaizen FU5 subprocess regression suite).
- `datetime.utcnow()` → `datetime.now(UTC)` in `api/result.py`, `api/agent.py`,
  and `runtime_adapters/types.py` (DeprecationWarning class).
- Pre-existing integration fixture drift: the `orchestration_runtime` teardown
  called `shutdown(mode="immediate")` — a kwarg `OrchestrationRuntime.shutdown`
  never had (drift from the #75 structural split); now `shutdown(graceful=False)`.

### Changed

- All test directories (`tests/{unit,integration,e2e}`) are ruff-clean
  (394 findings → 0), enabling lint-gating kaizen-agents tests in CI. Adapter
  unit-test dependencies (`anthropic`, `google-generativeai`) declared in `[dev]`.

## [0.9.8] — 2026-06-01 — persistent/learning memory shortcut repair + pyright drift (#855)

### Fixed

- **`Agent(memory="persistent")` and `Agent(memory="learning")` no longer crash (#855)** — the shortcut factories passed `storage_path=`/`enable_*=` kwargs that `HierarchicalMemory.__init__` (`hot_size, warm_backend, cold_backend, ...`) never accepted, so both shortcuts raised `TypeError: unexpected keyword argument 'storage_path'` on every call and were unusable. Both factories now build a real warm-tier-backed `HierarchicalMemory`: a `_safe_sqlite_dsn()` helper emits DataFlow's required 4-slash absolute SQLite DSN (the 3-slash form fails `unable to open database file`) and rejects `?`/`#`/null bytes; a `_build_dataflow_warm_backend()` helper registers `MemoryEntryModel` with the `tag_list` column (not the reserved `NodeMetadata.tags`) and returns a `DataFlowMemoryBackend`, degrading to hot-tier-only with a logged warning when DataFlow is unavailable (never a silent drop). Verified end-to-end: `store()`→`get()` round-trips content AND tags.
- **pyright type-drift in `patterns/state_manager.py` and `journey/core.py` (#855)** — bound `DataFlow`/`AsyncLocalRuntime`/`WorkflowBuilder` in a `TYPE_CHECKING` block (previously "possibly unbound" from the lazy `try/except ImportError`); guaranteed an async-capable `self.runtime` via a graceful fallback to an owned `AsyncLocalRuntime` when a sync runtime is supplied; imported `Pipeline` unconditionally for type-checking (the prior `Pipeline = None` on ImportError broke every `Pipeline` annotation); switched to the canonical `Signature.with_guidelines()`. Reduces the three files from 19 errors / 14 warnings to 0/0.

## [0.9.7] — 2026-05-09 — slim core: orphan deletes + httpx/openai consolidation (#890)

Patch release shipping kaizen-agents' slice of the kailash 2.18.0 / #890 slim-core decoupling. **No public-API behavior change** — three deps audited as orphans (zero imports across `src/kaizen_agents/`) are deleted, and the dep ordering is cleaned up. Users see no difference in installed packages from the `kailash-kaizen` + `openai` transitive set.

### Changed

- **Removed orphan dependencies** — verified via grep across `src/kaizen_agents/`:
  - **`kailash-pact>=0.8.1`** — zero imports. PACT semantics are reached via `kailash.trust.pact.*` (in `kailash` core), not the separate `kailash-pact` package. DELETED.
  - **`python-dotenv>=1.0.0`** — zero imports. DELETED.
  - **`structlog>=23.1.0`** — zero imports. DELETED.
- **Re-ordered remaining deps** — `kailash`, `kailash-kaizen`, `openai`, `httpx`. `httpx` is function-local but small enough to keep in core for ergonomics (no extras gating).
- **`kailash` floor: 2.14.0** (unchanged) — kaizen-agents does not require the 2.16+ slim-core surface; kailash-kaizen floor handles the chain.

### Notes

- This is a **dependency-cleanup release** — no `__init__.py` exports change, no `__all__` change, no behavior change. Test suite verifies all symbols still resolve.

## [0.9.6] — 2026-05-06 — black + ruff modernization sweep (#815, PR #850)

1222 unit tests pass (PR #850 CI). No public API change: `__init__.py` exports + `__all__`
lists are byte-for-byte identical between main and HEAD on every package init module.
Wheel content unchanged for any consumer-visible surface.
Pre-existing pyright drift (not introduced by this release) tracked in issue #855.

### Changed (issue #815 — chore-only modernization sweep, packages/kaizen-agents/src/)

- Applied Black + Ruff modernization sweep across `src/` clearing pre-existing drift the T3 hygiene release (`0.9.5`) flagged as out-of-scope. **No public API change**: `__init__.py` exports + `__all__` lists are byte-for-byte identical between main and HEAD on every package init module. Wheel content unchanged for any consumer-visible surface.
- Black: 88 files reformatted at line-length=88 (aligned with repo-level pre-commit hook). Project `pyproject.toml::[tool.black]::line-length` updated 100 → 88 for single-source-of-truth.
- Ruff: 376 of 433 diagnostics auto-fixed (PEP 604 `Optional[X] → X | None`, PEP 585 `List[X] → list[X]`, unused imports, deprecated `typing` re-exports). Manual triage: F821 (undefined `ExecutionMode` annotation in `api/shortcuts.py` — fixed via `TYPE_CHECKING` import), F841 unused locals (3 dead assignments removed in `validation.py`, `journey/nexus.py`, `patterns/parallel.py`), B904 raise-from-clause (17 sites — every `except X as e: raise Y(...)` now chains via `from e` or `from None` for `ImportError` lazy-load probes), B007 unused loop vars (2 renamed to `_node_id` / `_subtask`), E402 (4 intentional late imports kept with `# noqa: E402` + rationale comments — circular avoidance + optional-dep probe ordering). Style-preference rules SIM102/103/105/108/116 disabled at project level (`pyproject.toml::[tool.ruff.lint]::ignore`) — the nested-if / try-except / ternary forms read clearer in the agent / pattern code than the SIM-suggested rewrites.
- Pre-commit hook coverage: repo-level `.pre-commit-config.yaml` already runs Black + Ruff against `packages/kaizen-agents/src/`; no per-package config added.

## [0.9.5] — 2026-05-03 — issue #781 hygiene release (T3)

Patch release cutting PyPI for T3 (kaizen-agents TODO-NNN comment-strip) of the issue #781 cleanup workstream.

### Changed (T3 of #781 — comment-only, packages/kaizen-agents/src/)

- Stripped 69 `TODO-NNN` markers across 17 files. Heavy concentration in `agents/autonomous/base.py` (28 hits — state persistence + interrupt handling banners), `runtime_adapters/docs/` (23 hits across architecture-diagram cells + table column headers in 5 files), `patterns/` (15 hits across 11 files), `api/shortcuts.py` (3 hits — verified `ClaudeCodeAdapter` / `OpenAICodexAdapter` / `GeminiCLIAdapter` exist at `runtime_adapters/{claude_code,openai_codex,gemini_cli}.py`; rewrote stale "may not exist yet" notes). Disposition: 27 Class 1a banner / group label / inline-shipped, 33 Class 1b docstring / doc-body provenance, 9 Class 3 mid-comment cross-reference, 0 Class 2.

### Notes

- Comment-only diff: zero changes to imports, signatures, control flow, or types. Three commits (`b9605dde`, `35eebba1`, `37bab09f`) bypassed pre-commit hooks per the documented `git -c core.hooksPath=/dev/null` exception in `rules/git.md` § Pre-Commit Hook Workarounds — Black + Ruff auto-formatters proposed `Optional[X] → X | None` and `Dict → dict` rewrites that exceed T3's comment-only mandate; the type-modernization sweep is flagged as a follow-up workstream (out of T3 scope).

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
