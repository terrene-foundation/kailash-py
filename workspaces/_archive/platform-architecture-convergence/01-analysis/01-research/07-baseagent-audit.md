# BaseAgent Surface Area Audit — 2026-04-07

**Audit scope**: Map BaseAgent's full surface, dependents, and refactor strategy.

## Key Numbers

- **3,698 lines** in `packages/kailash-kaizen/src/kaizen/core/base_agent.py`
- **7 extension points** (per documented architecture)
- **132 test files** import BaseAgent (~600 test cases)
- **188 files** define BaseAgent subclasses across the monorepo
- **68 public/protected methods**

## File Structure

**Inheritance**:

```
BaseAgent
  ↓
kailash.nodes.base.Node
  ↓
kailash.core.BaseNode (abstract)
```

**Why this matters**: Node inheritance pulls in workflow composition (`get_parameters()`, `to_workflow()`, NodeParameter conversion) — making BaseAgent fundamentally incompatible with token streaming.

## Extension Points (7)

| #   | Method                         | Line | Purpose                                           |
| --- | ------------------------------ | ---- | ------------------------------------------------- |
| 1   | `_default_signature()`         | 1544 | Provide agent-specific I/O schema                 |
| 2   | `_default_strategy()`          | 1573 | Select execution strategy (SingleShot/MultiCycle) |
| 3   | `_generate_system_prompt()`    | 1612 | Customize LLM system prompt with MCP tool docs    |
| 4   | `_validate_signature_output()` | 1688 | Validate LLM output against schema                |
| 5   | `_pre_execution_hook()`        | 1732 | Custom logic before execution                     |
| 6   | `_post_execution_hook()`       | 1759 | Custom logic after execution                      |
| 7   | `_handle_error()`              | 1785 | Custom error handling and recovery                |

**Note**: Extension points violate `agent-reasoning.md` LLM-first rule — they let code override LLM decisions. They should be deprecated in favor of composition, but kept for backward compat during the refactor.

## Strategies

**Location**: `packages/kailash-kaizen/src/kaizen/strategies/`

| Strategy                  | File                         | Purpose                             |
| ------------------------- | ---------------------------- | ----------------------------------- |
| `AsyncSingleShotStrategy` | `async_single_shot.py` (11K) | Default — single LLM call, async    |
| `MultiCycleStrategy`      | `multi_cycle.py` (44K)       | ReAct-style loops with tool calling |
| `Fallback`                | `fallback.py` (3K)           | Sequential fallback strategies      |
| `HumanInLoop`             | `human_in_loop.py` (3K)      | Pause for user approval             |
| `ParallelBatch`           | `parallel_batch.py` (2.5K)   | Batch execution with concurrency    |
| `Streaming`               | `streaming.py` (2.5K)        | Token-by-token streaming (limited)  |
| `Convergence`             | `convergence.py` (9K)        | Multi-run consensus                 |
| `BaseStrategy`            | `base_strategy.py` (3.2K)    | Abstract interface                  |

## Mixins (7)

**Location**: `packages/kailash-kaizen/src/kaizen/core/mixins/`

| Mixin             | Lines | Applied If                             |
| ----------------- | ----- | -------------------------------------- |
| `LoggingMixin`    | 5.3K  | `config.logging_enabled=True`          |
| `MetricsMixin`    | 5.9K  | `config.performance_enabled=True`      |
| `RetryMixin`      | 6.9K  | `config.error_handling_enabled=True`   |
| `CachingMixin`    | 6.7K  | `config.batch_processing_enabled=True` |
| `TimeoutMixin`    | 4.7K  | `config.memory_enabled=True`           |
| `TracingMixin`    | 7.2K  | `config.transparency_enabled=True`     |
| `ValidationMixin` | 8.1K  | `config.mcp_enabled=True`              |

## Signature System

**Location**: `packages/kailash-kaizen/src/kaizen/signatures/`

- `core.py` (79K) — Signature, InputField, OutputField
- `enterprise.py` (31K) — Enterprise validators, registry
- `multi_modal.py` (22K) — ImageField, AudioField
- `patterns.py` (41K) — ChainOfThought, ReAct patterns

**Critical: Signature → JSON schema lives in `kaizen/core/structured_output.py`** (481 lines):

- `StructuredOutputGenerator` — converts Signature to JSON schema via TypeIntrospector
- `StructuredOutput` — fluent API for provider-specific formats (OpenAI strict, Azure json_object, Gemini)
- `create_structured_output_config()` — production wrapper with strict mode auto-detection

**This is the capability Delegate is missing.** Already extracted into its own module — Delegate just needs to call it.

## Subclasses (188 files containing BaseAgent definitions)

### kaizen-agents specialized agents (10+ in `agents/specialized/`)

| Agent               | Method Overrides                   |
| ------------------- | ---------------------------------- |
| SimpleQAAgent       | `_default_signature()`             |
| ChainOfThoughtAgent | `_default_strategy()` → MultiCycle |
| ReActAgent          | `_default_strategy()` → MultiCycle |
| RAGResearchAgent    | signature + strategy               |
| CodeGenerationAgent | signature                          |
| TreeOfThoughtsAgent | strategy                           |
| MemoryAgent         | memory + session tracking          |
| HumanApprovalAgent  | `_pre_execution_hook()`            |
| MultiModalAgent     | image/audio fields                 |
| VisionAgent         | image processing                   |

### Multi-agent patterns (7 patterns in `patterns/patterns/`)

| Pattern          | Subclasses                                     | Coupling                    |
| ---------------- | ---------------------------------------------- | --------------------------- |
| SupervisorWorker | SupervisorAgent, WorkerAgent, CoordinatorAgent | High (delegation via run()) |
| Sequential       | PipelineStageAgent                             | High (chained run calls)    |
| Parallel         | (mocks in tests)                               | High (asyncio.gather)       |
| Debate           | ProponentAgent, OpponentAgent, JudgeAgent      | Medium                      |
| Consensus        | ProposerAgent, VoterAgent                      | Medium                      |
| Handoff          | HandoffAgent                                   | High                        |
| Blackboard       | (pattern, not agent)                           | Medium                      |

**Critical finding**: All patterns are **composition-based** (call `agent.run()`), NOT inheritance-based. They work with ANY agent that implements `run(inputs) -> Dict[str, Any]`. **Migration impact: zero API changes** — patterns work with Delegate too if Delegate has `run()`.

### kailash-align agents (4 in `agents/`)

All extend BaseAgent via lazy import. Same pattern as ML agents.

## Capability Matrix vs Delegate

| Capability                                   | BaseAgent                     | Delegate                 |
| -------------------------------------------- | ----------------------------- | ------------------------ |
| Structured outputs (Signature → JSON schema) | ✅                            | ❌                       |
| MCP integration                              | ❌ broken                     | ✅ working               |
| Token streaming                              | ❌                            | ✅                       |
| Multi-provider streaming adapters            | ❌                            | ✅ (4 clean)             |
| Budget tracking                              | ⚠️ exists but advisory        | ✅ enforced              |
| Typed event stream                           | ❌                            | ✅                       |
| Tool hydration (BM25)                        | ❌                            | ✅                       |
| Hook system                                  | ✅ (10+ event types, fragile) | ✅ (HookManager)         |
| Permission system                            | ✅ exists, not wired          | ❌                       |
| Mixin composition                            | ✅ 7 mixins                   | ❌                       |
| Strategy pattern                             | ✅ (SingleShot, MultiCycle)   | ❌ (single shot only)    |
| Node inheritance                             | ✅ (workflow integration)     | ❌                       |
| Multi-modal (vision/audio)                   | ✅                            | ⚠️ partial               |
| 7 extension points                           | ✅                            | ❌ (composition instead) |

## Design Flaws

1. **Monolith** — 3,698 lines in one file. Should split into core execution / MCP / permissions / hooks / observability modules.
2. **Broken MCP** — known issue #339 (text-based prompt injection, `_execute_regular_tool()` stub, missing server config preservation)
3. **4,000-line ai_providers.py monolith** — separate audit (#09)
4. **Permission system is advisory** — budget warnings don't actually block execution
5. **Hook system is fragile** — `executor.submit(asyncio.run(...))` violates async/sync boundaries
6. **Lazy MCP discovery** — first `run()` call triggers blocking discovery, breaks tests
7. **Config auto-conversion** — `BaseAgentConfig.from_domain_config()` magic conversion is silently lossy
8. **Signature validation missing** — `_validate_signature_output()` is opt-in extension point, not automatic

## Public API Contract (Stable)

| Method                   | Signature                     | Contract                         |
| ------------------------ | ----------------------------- | -------------------------------- |
| `run()`                  | `**inputs -> Dict[str, Any]`  | Stable — patterns depend on this |
| `run_async()`            | async variant                 | Stable                           |
| `get_parameters()`       | `-> Dict[str, NodeParameter]` | Stable — Node interface          |
| `to_workflow()`          | `-> Workflow`                 | Stable — Core SDK integration    |
| `discover_mcp_tools()`   | async tool discovery          | Stable (broken)                  |
| `execute_mcp_tool()`     | tool execution                | Stable (broken)                  |
| `enable_observability()` | observability config          | Stable                           |
| `register_hook()`        | event hook registration       | Stable                           |

**Refactor must preserve all of these.** Public API is the contract.

## Refactor Strategy

### Phase 1: Decoupling (Low Risk)

- ✅ Already extracted: `structured_output.py`, hooks, observability
- 🔄 Extract: `permissions.py` (in progress)
- ⬜ Extract: `ai_providers.py` → `providers/` per-provider modules (separate audit)
- ⬜ Create: `ToolRegistry` abstraction unifying JSON schema (Signature) + executor (AgentLoop)

**Result**: BaseAgent shrinks from 3,698 → ~1,200 lines

### Phase 2: Delegate Convergence (Medium Risk)

- Add `structured_output` support to Delegate via `StructuredOutput.for_provider()`
- Add permission system (PermissionPolicy, BudgetEnforcer)
- Expose MCP tool discovery to Delegate
- Optional: Hook + observability integration

**Result**: Delegate becomes enterprise-capable (~900 lines of new code)

### Phase 3: Pattern Migration (Low Risk)

- Verify all 7 multi-agent patterns work with Delegate
- **No code changes needed** — patterns use `run()` which both provide
- All specialized agents become Delegate subclasses (or thin BaseAgent wrappers)

### Phase 4: Cleanup (Low Risk)

- Deprecate BaseAgent extension points (anti-pattern per `agent-reasoning.md`)
- Agents should use composition, not inheritance
- Mark for removal in v2.0

## Refactor Risk Assessment

| Phase                | Risk   | Test Coverage                                  |
| -------------------- | ------ | ---------------------------------------------- |
| Decoupling           | Low    | ~600 tests cover BaseAgent surface             |
| Delegate convergence | Medium | New tests needed for unified behavior          |
| Pattern migration    | Low    | Patterns are composition-based, no API changes |
| Cleanup              | Low    | Backward-compat shims maintain stability       |

**Total: ~600 tests must continue passing** — they're the regression net.
