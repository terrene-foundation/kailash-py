# Ground Truth Audit: kaizen-agents Source Code

**Date**: 2026-03-23
**Auditor**: Code audit against actual source files in `src/`
**Scope**: All 51 Python source files across `kaizen_agents/` and `kz/` packages

## Executive Summary

**kaizen-agents claims 690 tests passing against M0-M3 milestones. The code audit reveals that the implementation is entirely self-contained with ZERO imports from the kailash-py SDK it was designed to build on.** All "L3 SDK integration" is local type stubs. The kz CLI works but bypasses the orchestration layer entirely, calling OpenAI directly.

---

## 1. SDK Integration: Zero

### Imports Audit

Grep for `from kailash`, `import kailash`, `from kaizen.l3`, `from eatp` across all 51 source files: **zero matches**.

The `pyproject.toml` declares these dependencies:

```
kailash>=1.0.0
kailash-nexus>=1.4.2
kailash-dataflow>=1.0.1
kailash-kaizen>=1.3.0
eatp>=0.2.0
trust-plane>=0.2.1
```

None are imported anywhere in the codebase. The packages are installed but unused.

### What Should Have Been Imported (kailash-py v2.1.0 Exports)

```python
from kaizen.l3 import (
    EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, GradientZone, Verdict,
    ContextScope, ScopeProjection, DataClassification, ContextValue,
    MessageRouter, MessageChannel, MessageEnvelope, MessageType, DeadLetterStore,
    AgentFactory, AgentInstance, AgentInstanceRegistry, AgentSpec,
    Plan, PlanValidator, PlanExecutor, apply_modification, apply_modifications,
)
```

These are all production-ready (868 tests, released as kaizen v2.1.0 on PyPI). This repo defines local versions of the same types instead of importing them.

---

## 2. Module-by-Module Reality

### kaizen_agents/types.py (715 lines)

**Status**: Local type definitions mirroring PACT spec concepts.

Defines `GradientZone`, `ConstraintEnvelope`, `AgentSpec`, `Plan`, `PlanNode`, `PlanEdge`, `PlanEvent`, `PlanModification`, `L3Message` variants — all locally. These duplicate what `kaizen.l3` already exports.

**Verdict**: Must be replaced with imports from `kaizen.l3`. Adapter layer may be needed for any orchestration-specific extensions.

### kaizen_agents/llm.py (240 lines)

**Status**: Real implementation. OpenAI-compatible LLM client wrapper with `complete()` and `complete_structured()`.

**Verdict**: Legitimate orchestration-layer code. This is the LLM boundary — it belongs here.

### kaizen_agents/planner/ (1,575 lines total)

| File          | Lines | Real Logic                   | SDK Calls |
| ------------- | ----- | ---------------------------- | --------- |
| decomposer.py | 368   | Yes — LLM task decomposition | Zero      |
| designer.py   | 839   | Yes — LLM agent spec design  | Zero      |
| composer.py   | 787   | Yes — LLM plan composition   | Zero      |

**Verdict**: Real LLM orchestration logic. But outputs go to local types, not SDK types. Needs rewiring to produce `kaizen.l3.Plan`, `kaizen.l3.AgentSpec`, etc.

### kaizen_agents/monitor.py (780 lines)

**Status**: Core execution engine. Lines 7-18 explicitly admit:

> "The PlanMonitor does NOT directly call the SDK's PlanExecutor (it does not exist yet in kailash-py). Instead, it implements a simplified execution loop..."

This was written when kailash-py didn't have PlanExecutor. **It does now** (v2.1.0). But PlanMonitor was never updated.

**Critical finding**: PlanMonitor implements its own execution loop with callback patterns. The real `PlanExecutor` in kailash-py is synchronous and blocking (The Hard Truth finding #1). This means PlanMonitor can't simply swap to calling PlanExecutor — the async/sync mismatch must be resolved.

**Verdict**: Needs major rework. Either:

- (A) Wrap sync PlanExecutor in async adapter, or
- (B) Implement async node execution here and use PlanValidator + Plan types from SDK only

### kaizen_agents/recovery/ (1,058 lines total)

| File          | Lines | Real Logic                    |
| ------------- | ----- | ----------------------------- |
| diagnoser.py  | 351   | Yes — LLM failure analysis    |
| recomposer.py | 707   | Yes — Plan modification logic |

**Verdict**: Real implementation. Produces `PlanModification` objects — but local type, not SDK type. Needs rewiring.

**Hard Truth impact**: Recovery assumes HELD is a runtime state that can be resolved. kailash-py's HELD is phantom — nodes stay FAILED and emit a "held" event. Recovery model must adapt to event-driven HELD, not state-driven HELD.

### kaizen_agents/protocols/ (type stubs only)

```
delegation.py   — class DelegationProtocol with type hints, no methods
clarification.py — class ClarificationProtocol with type hints, no methods
escalation.py   — class EscalationProtocol with type hints, no methods
```

**Verdict**: Empty shells. M2-06 was marked complete but protocols have no implementation. Zero messaging, zero queueing, zero agent-to-agent communication.

### kaizen_agents/governance/ (empty)

```
__init__.py — 79 bytes, docstring only
```

**Verdict**: M4 was correctly marked "not started." But this means the entire PACT governance layer that makes kaizen-agents distinctive is unbuilt.

### kaizen_agents/audit/ (empty)

```
__init__.py — 72 bytes, docstring only
```

**Verdict**: EATP audit trail unbuilt. No genesis records, delegation records, or hash chains.

### kaizen_agents/policy/envelope_allocator.py (170 lines)

**Status**: Partial implementation. Budget allocation logic exists but uses local ConstraintEnvelope type.

**Verdict**: Needs rewiring to SDK EnvelopeSplitter.

### kaizen_agents/context/ (2 files)

| File          | Status                                           |
| ------------- | ------------------------------------------------ |
| injector.py   | Implemented — context selection for child agents |
| summarizer.py | Implemented — LLM context compression            |

**Verdict**: Real code, uses local types. Needs rewiring to SDK ScopedContext.

### kz/ CLI (4,841 lines)

| Component     | Status                     | Uses kaizen_agents?            |
| ------------- | -------------------------- | ------------------------------ |
| cli/loop.py   | Real — full agent loop     | **NO — calls OpenAI directly** |
| cli/app.py    | Real — Click CLI app       | No                             |
| tools/\*      | Real — 7 file/shell tools  | No                             |
| commands/\*   | Real — command registry    | No                             |
| hooks/\*      | Real — hook manager        | No                             |
| session/\*    | Real — session persistence | No                             |
| config/\*     | Real — TOML config loading | No                             |
| mcp/client.py | Partial — 3 bare `pass`    | No                             |

**Critical finding**: The kz CLI is a **standalone OpenAI-native agent loop**. It does not import or use anything from `kaizen_agents`. The orchestration layer is completely bypassed. The CLI is effectively a Claude Code clone that happens to live in the same repo.

---

## 3. The Three Hard Truths (from kailash-py Red Team)

kailash-py's codebase verification red team found that kaizen-agents was designed against specs, not the actual SDK implementation:

| Assumption                                 | Reality                                              | Impact Here                                                        |
| ------------------------------------------ | ---------------------------------------------------- | ------------------------------------------------------------------ |
| PlanExecutor is async with event callbacks | Fully synchronous, blocking loop, no event injection | PlanMonitor's async callback model is wrong                        |
| HELD is a runtime state                    | Phantom — nodes stay FAILED, emit "held" event       | Recovery model (diagnoser/recomposer) has no foundation            |
| Signatures produce typed objects           | String-only OutputField, no structured parsing       | PlanComposer can't produce validated DAG structures via Signatures |

### Impact Assessment

These aren't minor issues — they invalidate the core integration assumptions:

1. **PlanMonitor** assumes it can inject async callbacks into PlanExecutor's execution loop. It can't — PlanExecutor runs synchronously to completion.
2. **FailureDiagnoser** assumes it receives `NodeHeld` events with a live node in HELD state that can be resumed. In reality, the node is in FAILED state and "held" is just an event classification.
3. **PlanComposer** was designed to produce structured Plan DAGs via Kaizen Signatures. Signatures return strings, not typed objects.

---

## 4. Test Coverage Reality

690 tests pass. But what do they test?

- **Planner tests**: Mock the LLM, verify prompt construction and output parsing against local types. Never touch SDK.
- **Recovery tests**: Mock the LLM, verify diagnosis logic against local types. Never touch SDK.
- **CLI tests**: Test file tools, config loading, session management. Never touch kaizen_agents orchestration.
- **Integration tests**: Test the planner → monitor → recovery pipeline — but using local types and callback stubs, not SDK.

**No test imports kailash-py SDK types.** The 690 tests validate an internally-consistent but SDK-disconnected system.

---

## 5. What Is Real vs What Is Claimed

### Actually Complete (real working code)

1. **LLM client** — OpenAI-compatible wrapper with structured output
2. **Task decomposition** — objective → subtasks via LLM
3. **Agent design** — subtask → spec via LLM (capability matching, spawn policy)
4. **Plan composition** — subtasks → DAG via LLM (with local PlanValidator)
5. **Failure diagnosis** — error → root cause via LLM
6. **Plan recomposition** — diagnosis → modifications via LLM
7. **Context injection/summarization** — LLM-driven context management
8. **kz CLI** — full standalone agent loop with tools, sessions, hooks, commands

### Claimed Complete But Actually Stubbed

1. **Protocols** (M2-06) — type definitions only, no implementation
2. **PlanMonitor integration** (M2-08) — admits it's a stub in its own comments
3. **SDK integration** — zero imports from any kailash package

### Correctly Marked Incomplete

1. **Governance** (M4) — empty directory
2. **Audit** (M4) — empty directory
3. **Sandbox, Skills, Checkpoint** (M5) — empty directories

---

## 6. Scope of Required Work

### Phase 0: SDK Wiring (this repo, blocked on kailash-py Phase 0)

- Replace local `types.py` with imports from `kaizen.l3`
- Adapt PlanMonitor to work with sync PlanExecutor (or async adapter)
- Adapt recovery model to event-driven HELD (not state-driven)
- Adapt PlanComposer to work with string Signatures (JSON parse layer)
- Wire kz CLI to use kaizen_agents orchestration (not direct OpenAI)

### Phase 1: Implement Missing Stubs (this repo)

- Protocols: real message exchange using SDK MessageRouter
- EnvelopeAllocator: use SDK EnvelopeSplitter
- Context: use SDK ScopedContext

### Phase 2: Build Governance (M4, this repo)

- EATP audit trail
- D/T/R accountability
- Knowledge clearance
- Cascade revocation
- Vacancy handling
- Dereliction detection
- Emergency bypass
- Budget reclamation/warnings

### Phase 3: Polish (M5, this repo)

- Context compaction, sandbox, skills, web tools, CI mode, undo

### Phase 4: Red Team to Convergence

- Against authority feature matrix (doc 14)
- Against PACT thesis requirements
- Against kailash-rs behavioral alignment

---

## 7. Dependencies and Blocking

```
kailash-py Phase 0 (SDK prerequisites)
├── Async PlanExecutor (or async adapter)
├── HELD as resolvable state (or documented event-driven pattern)
└── Structured output from Signatures (or documented string→parse pattern)
    │
    ▼
kaizen-agents Phase 0 (SDK wiring) ← BLOCKED until above resolves
├── Replace types.py with SDK imports
├── Adapt PlanMonitor
├── Adapt recovery model
└── Wire kz CLI to orchestration
    │
    ▼
kaizen-agents Phase 1-3 (implementation)
    │
    ▼
kaizen-agents Phase 4 (red team convergence)
    │
    ▼
kailash-rs kaizen-agents (uses THIS as behavioral reference)
```

**Critical path**: kailash-py Phase 0 → this repo Phase 0 → this repo Phases 1-3 → red team → kailash-rs alignment.

OR: Decide that kaizen-agents works with the SDK AS-IS (sync PlanExecutor, phantom HELD, string Signatures) by adapting the orchestration layer's assumptions. This removes the kailash-py Phase 0 blocker.
