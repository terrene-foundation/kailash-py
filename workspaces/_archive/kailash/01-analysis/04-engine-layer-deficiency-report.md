---
title: "Engine Layer Deficiency Report — Cross-Project Analysis"
date: 2026-03-30
type: analysis
severity: P0
sources:
  - ~/repos/terrene/arbor/workspaces/hr-ai-advisory/01-analysis/16-engines-vs-primitives/
  - ~/repos/terrene/pact/workspaces/pact/01-analysis/43-engine-api-verification-report.md
  - ~/repos/tpc/impact-verse/workspaces/impactverse-methods/01-analysis/09-kailash-engine-deficiency-report.md
  - kailash-rs deep dive (2026-03-30)
repos_affected:
  - terrene-foundation/kailash-py (BUILD)
  - esperie/kailash-rs (BUILD, reference architecture)
  - kailash/ (COC source of truth)
---

# Engine Layer Deficiency Report

## Executive Summary

Three independent development teams (Arbor/Terrene, Pact/Terrene, ImpactVerse/TPC) independently discovered that the Kailash Python SDK's engine layer is broken or invisible. Investigation reveals this is a **dual failure**: real code bugs in kailash-py's engine implementations AND COC artifacts that teach only primitives. kailash-rs's engine architecture is clean and can serve as the reference implementation.

## The Three-Layer Model

Each Kailash framework has three abstraction layers:

```
Layer 3: ENGINE      — High-level, zero-config, composes primitives automatically
Layer 2: PRIMITIVES  — Individual components, manual wiring
Layer 1: RAW         — Outside Kailash entirely (SQL, FastAPI, raw LLM calls)
```

| Framework | Layer 1 (Raw)     | Layer 2 (Primitives)                  | Layer 3 (Engine)                             |
| --------- | ----------------- | ------------------------------------- | -------------------------------------------- |
| DataFlow  | Raw SQL           | @db.model + WorkflowBuilder nodes     | DataFlowEngine + Express (23x faster)        |
| Nexus     | FastAPI/CLI       | ChannelManager, manual channels       | Nexus() zero-config, NexusEngine.builder()   |
| Kaizen    | Raw LLM API calls | BaseAgent + Signature (single agents) | Agent/Delegate, Pipeline, GovernedSupervisor |

## Part 1: kailash-py Code Deficiencies

### 1.1 Kaizen Agent API — 3 CRITICAL Bugs (ALL CONFIRMED IN v0.5.0)

**BUG-1: AgentResult.error() does not exist**

- File: `packages/kaizen-agents/src/kaizen_agents/api/agent.py` lines 408, 746
- `Agent.run()` calls `AgentResult.error(...)` in exception handlers
- `AgentResult` only defines `from_error()` (result.py line 400)
- **Impact**: Any error in Agent.run() crashes with `AttributeError`

**BUG-2: Silent success fabrication**

- File: `packages/kaizen-agents/src/kaizen_agents/api/agent.py` lines 660-666
- `_execute_single()` catches ALL exceptions and returns `AgentResult.success(text=f"Executed task: {context['task']}")`
- **Impact**: Runtime failures return the user's prompt back as a fake "answer". Masks BUG-1.

**BUG-3: Tools parameter accepted but never wired**

- File: `packages/kaizen-agents/src/kaizen_agents/api/agent.py` line 103 (accepts), 225 (stores), 622 (passes to context)
- `_get_runtime()` (line 324) never passes tools to runtime adapter
- `resolve_runtime_shortcut()` ignores tools
- `LocalKaizenAdapter.__init__()` accepts `tool_registry` but not raw callable list
- **Impact**: `Agent(tools=[func1, func2])` silently drops all tools. LLM makes text-only calls.

**Contrast**: `Delegate` class handles all three correctly — tools wired via `ToolRegistry`, errors yield `ErrorEvent`, budget tracking built-in.

### 1.2 Kaizen Agent vs Delegate Relationship — Unclear

| Aspect           | Agent API (BROKEN)              | Delegate API (WORKS)                        |
| ---------------- | ------------------------------- | ------------------------------------------- |
| Tool interface   | Plain functions (silently lost) | ToolRegistry → wired to LLM                 |
| Tool execution   | Never happens                   | AgentLoop.\_execute_tool_calls() → parallel |
| Error handling   | Crashes or fabricates success   | ErrorEvent yielded to caller                |
| Budget tracking  | Not implemented                 | budget_usd parameter + auto-cost            |
| Streaming events | stream() yields plain strings   | run() yields typed DelegateEvent objects    |
| Designed for     | Unknown (broken)                | Autonomous agents with 200+ tools           |

**Decision needed**: Is Agent a convenience wrapper around Delegate, or a separate (broken) implementation? Currently they're separate with incompatible tool models.

### 1.3 DataFlow Express — Mostly Fixed

| Issue                           | Status at report time | Current status (v1.2.1)                               |
| ------------------------------- | --------------------- | ----------------------------------------------------- |
| create() doesn't return auto-ID | BROKEN                | **FIXED** — returns full record                       |
| SQLite :memory: async fails     | BROKEN                | **MITIGATED** — auto shared-cache URI, warning issued |
| Express is async-only           | MISSING               | **STILL MISSING** — no sync API                       |
| DataFlowEngine.builder()        | —                     | **WORKING** — fully implemented                       |

### 1.4 DataFlow Convention Drift

Pact-platform has **83 primitive call sites** across 15 files using `db.create_workflow()` / `db.add_node()` / `db.execute_workflow()` for single-record CRUD. Every one should be `db.express.create()` instead. This pattern exists because COC teaches only primitives.

### 1.5 Kaizen Streaming Gap — RESOLVED

~~DelegateEvent types `ToolCallStart` and `ToolCallEnd` are defined but never yielded during streaming.~~

**Red team correction (2026-03-30)**: ToolCallStart and ToolCallEnd ARE wired in the current Delegate code. Both terrene-foundation/kailash-py#159 and esperie/kailash-rs#100 are CLOSED. Events flow: `loop.py:_execute_tool_calls()` creates events → `run_turn()` yields them → `delegate.py:run()` passes them through as `DelegateEvent` instances. Verified in code at loop.py lines 645-716 and delegate.py lines 310-314.

### 1.6 Journey Module

4 import errors in test collection for the Journey module (kaizen-agents). TODO-JO-003/004 incomplete.

## Part 2: kailash-rs Architecture — Reference Implementation

Deep dive into kailash-rs found **zero anti-patterns**:

| Check                                  | Result | Detail                                                      |
| -------------------------------------- | ------ | ----------------------------------------------------------- |
| Engines compose from primitives        | PASS   | DataFlowEngine wraps DataFlow + Validation + Classification |
| No engine re-implements primitives     | PASS   | All engines delegate to their primitive layers              |
| No primitive sets without an engine    | PASS   | Every primitive has an engine on top                        |
| No engine bypasses primitives          | PASS   | All engines go through their primitives                     |
| No half-implemented engines            | PASS   | All engines are feature-complete                            |
| No parallel implementations            | PASS   | Single coherent entry point per framework                   |
| Cross-framework intentional decoupling | PASS   | By design — user assembles at application boundary          |

**Composition graphs (kailash-rs)**:

```
DataFlowEngine ──wraps──> DataFlow ──uses──> QueryBuilder/ModelDefinition/Nodes
NexusEngine    ──wraps──> Nexus   ──uses──> HandlerRegistry/Channels/Middleware
Agent          ──implements──> BaseAgent ──uses──> LlmClient/ToolRegistry/Memory
OrchestrationRuntime ──takes──> Vec<dyn BaseAgent> ──delegates──> individual agents
GovernedSupervisor ──composes──> Agent + 9 governance modules
```

**kailash-rs is the reference architecture for fixing kailash-py.**

## Part 3: COC Artifact Gap

### What artifacts teach now

- CLAUDE.md Directive 1: "Instead of raw SQL → check dataflow-specialist" (Layer 1 → Layer 2 only)
- rules/patterns.md: WorkflowBuilder examples (Layer 2 only)
- skills/02-dataflow/SKILL.md: Quick Start shows @db.model then WorkflowBuilder (Layer 2)
- skills/04-kaizen/SKILL.md: Quick Start shows BaseAgent (Layer 2)
- Framework specialists: No three-layer guidance

### What artifacts should teach

- Default to Engine (Layer 3); drop to Primitives (Layer 2) only when Engine doesn't fit
- DataFlow: `db.express` for simple CRUD, WorkflowBuilder for complex multi-step
- Nexus: `Nexus()` for standard deployment (already close to correct)
- Kaizen: `Delegate` for autonomous agents, `BaseAgent` for custom logic, `GovernedSupervisor` for governed teams

### The ImpactVerse "friction gradient" finding

| API                      | Lines to Start | Teaching Artifacts           | Friction  |
| ------------------------ | -------------- | ---------------------------- | --------- |
| BaseAgent (primitive)    | ~60 lines      | 5 skill files, first in path | LOW       |
| Delegate (engine, works) | 2 lines        | 1 file, buried in governance | HIGH      |
| Agent (engine, broken)   | 6 lines        | 6 lines in patterns.md       | INVISIBLE |

**The COC friction gradient is backwards.** The simplest working API (Delegate, 2 lines) has the highest discovery friction. The most complex API (BaseAgent, 60 lines) is taught first.

## Part 4: Root Cause Chain

```
kailash-rs engines work (clean architecture)
  → kailash-py engines ported but left incomplete (Agent API 3 bugs)
    → COC written when py engines didn't work → COC teaches primitives
      → Devs use primitives → Devs try to upgrade → Engines broken
        → Devs fall back to primitives → COC reinforces primitive usage
          → FEEDBACK LOOP
```

The COC artifact gap is real but is a **symptom**. The root cause is incomplete engine implementations in kailash-py.

## Part 5: Recommended Actions

### P0 — Fix in kailash-py before any COC changes

| #   | Action                                                          | File                                      | Effort               |
| --- | --------------------------------------------------------------- | ----------------------------------------- | -------------------- |
| 1   | Fix `AgentResult.error()` → `AgentResult.from_error()`          | kaizen-agents/api/agent.py                | 2 lines              |
| 2   | Remove silent success fabrication in `_execute_single`          | kaizen-agents/api/agent.py                | 10 lines             |
| 3   | Wire Agent tools to LLM OR deprecate Agent in favor of Delegate | kaizen-agents/api/agent.py + shortcuts.py | 50-100 lines         |
| 4   | Wire ToolCallStart/ToolCallEnd events in Delegate               | kaizen-agents/delegate/                   | 50-100 lines (#159)  |
| 5   | Fix Journey module import errors                                | kaizen-agents/                            | Investigation needed |

### P1 — Design decision (requires human authority)

| #   | Decision                       | Options                                                                                                               |
| --- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 6   | Agent vs Delegate relationship | A: Agent wraps Delegate internally. B: Deprecate Agent, promote Delegate. C: Fix Agent as independent implementation. |
| 7   | DataFlow Express sync API      | A: Add express_sync companion. B: Document async-only as intentional.                                                 |

### P2 — COC artifacts (at kailash/ level, AFTER P0 fixes)

| #   | Action                                                      | Classification        |
| --- | ----------------------------------------------------------- | --------------------- |
| 8   | Create `rules/framework-first.md` — three-layer model       | GLOBAL                |
| 9   | Create `skills/13-architecture-decisions/decide-layer.md`   | GLOBAL                |
| 10  | Update framework specialists with layer preference sections | GLOBAL                |
| 11  | Reorder kaizen skills: Delegate first, BaseAgent second     | GLOBAL                |
| 12  | Update CLAUDE.md Directive 1 with engine-first language     | Per-repo (not synced) |
| 13  | Update patterns.md with engine examples first               | GLOBAL                |

### P3 — Cross-SDK alignment

| #   | Action                                                                        |
| --- | ----------------------------------------------------------------------------- |
| 14  | File kailash-rs issues for any gaps found in reverse audit                    |
| 15  | Verify kailash-rs Agent API doesn't have same 3 bugs                          |
| 16  | Ensure ToolCallStart/ToolCallEnd wired in kailash-rs (esperie/kailash-rs#100) |

## Appendix: Developer Feedback Sources

### Arbor (Terrene, HR AI Advisory)

- DataFlowEngine: 70/100 — feature-complete but eager connection doesn't fix test isolation
- NexusEngine: 85/100 — production-ready, Arbor uses Nexus correctly
- Kaizen: 60/100 — Agent/BaseAgent/Delegate "split brain", specialist shim debt

### Pact (Terrene, Governance Platform)

- DataFlowEngine: Ready with caveats (auto-ID now fixed)
- NexusEngine: Not suitable for pact-platform's 62+ custom endpoints
- Kaizen: GovernedSupervisor already correctly used
- Convention drift: 83 primitive call sites that should be Express

### ImpactVerse (TPC, Network Intelligence)

- Agent API: 3 CRITICAL bugs discovered during production migration
- Delegate API: Works correctly but not taught
- COC: Teaching path routes to primitives, engines invisible
- Recommendation: "Start with Delegate, graduate to BaseAgent"

## Appendix B: Red Team Corrections (2026-03-30)

| #   | Original Claim                           | Verdict           | Correction                                                                                                    |
| --- | ---------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------- |
| 1   | kailash-rs has same bugs                 | **NOT PRESENT**   | Rust type system prevents all 3. All engines compose correctly.                                               |
| 2   | ToolCallStart/ToolCallEnd not wired      | **WRONG**         | Both events ARE wired in Delegate (loop.py, delegate.py). #159 and #100 CLOSED.                               |
| 3   | Root cause: "ported from rs, incomplete" | **PARTIAL**       | NexusEngine was modeled on rs. Agent API was independent development, not a port.                             |
| 4   | P0 = fix Agent bugs                      | **REPRIORITIZED** | Zero downstream projects use Agent API. P0 is the Agent/Delegate decision.                                    |
| 5   | Only 3 bugs exist                        | **INCOMPLETE**    | BUG-4 (run_sync deprecated), BUG-5 (unbounded history), BUG-6 (Pipeline NotImplementedError) also found.      |
| 6   | Only Arbor/Pact/ImpactVerse affected     | **INCOMPLETE**    | kaizen-cli, treasury, aegis, aerith, aether also use Kaizen (all via Delegate/GovernedSupervisor, not Agent). |

### Additional Bugs Found by Red Team

- **BUG-4**: `Agent.run_sync()` uses deprecated `asyncio.get_event_loop()` — fails on Python 3.12+
- **BUG-5**: `OrchestrationRuntime._execution_history` grows without bound (memory leak)
- **BUG-6**: `Pipeline.run()` raises `NotImplementedError` instead of using `@abstractmethod`

### Resolution Status (post-implementation)

| Bug                                 | Fix                                                    | Status    |
| ----------------------------------- | ------------------------------------------------------ | --------- |
| BUG-1: AgentResult.error()          | Changed to from_error()                                | FIXED     |
| BUG-2: Silent success fabrication   | Returns from_error() on exception                      | FIXED     |
| BUG-3: Tools never wired            | Agent API deprecated; Delegate handles tools correctly | MITIGATED |
| BUG-4: run_sync() deprecated API    | Uses asyncio.run() with running-loop detection         | FIXED     |
| BUG-5: Unbounded execution_history  | Changed to deque(maxlen=10000)                         | FIXED     |
| BUG-6: Pipeline NotImplementedError | Converted to ABC with @abstractmethod                  | FIXED     |
| Agent deprecation                   | DeprecationWarning in **init**, docstring updated      | DONE      |
| COC three-layer model               | rules/framework-first.md created at kailash/           | DONE      |
| Kaizen teaching reorder             | Delegate-first in specialist, SKILL.md, patterns.md    | DONE      |
| DataFlow/Nexus engine-first         | Layer preference sections in all specialists + skills  | DONE      |
