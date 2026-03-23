# Agent Findings Convergence Report

## 1. Agent Team Summary

Four analysis agents were deployed in parallel. Their findings converge on key themes but diverge on one critical architectural decision.

| Agent                    | Focus                                          | Key Finding                                                                             |
| ------------------------ | ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| **deep-analyst**         | Failure modes, complexity, integration risks   | PlanExecutor sync/async mismatch is BLOCKING; escalation loops need plan fingerprinting |
| **requirements-analyst** | Requirements decomposition, interface design   | "LLM proposes, SDK disposes" pattern; recommends SEPARATE PyPI package                  |
| **framework-advisor**    | Package structure, component patterns, testing | Subpackage within kailash-kaizen; hybrid signatures + async functions                   |
| **value-auditor**        | Enterprise buyer perspective                   | "Foundation exceptional; house not built." Need GovernedAgent API + end-to-end demo     |

---

## 2. BLOCKING Issues (Must Resolve Before Implementation)

### BLOCK-01: PlanExecutor Sync/Async Mismatch

**Source**: deep-analyst (SEAM-01)

The L3 PlanExecutor is synchronous (`kaizen/l3/plan/executor.py`). However, all L3 primitives it depends on are async:

- `AgentFactory.spawn()` — async
- `MessageRouter.route()` — async
- `EnvelopeTracker.record_consumption()` — async (asyncio.Lock)

The `NodeCallback` type is currently `Callable[[str, str], dict[str, Any]]` (sync). The orchestration layer's node callback needs to be async because it must call AgentFactory.spawn(), create channels, and send messages.

**Resolution**: PlanExecutor's NodeCallback must become async. This is a breaking change to the L3 SDK API (released as kailash-kaizen v2.1.0). Options:

1. Add `AsyncNodeCallback` alongside existing sync callback (backward-compatible)
2. Make PlanExecutor fully async (breaking change, semver minor bump)

**Recommendation**: Option 1 — add async variant. The sync executor remains for unit tests and conformance testing.

### BLOCK-02: DelegationPayload Context Serialization

**Source**: deep-analyst (SEAM-02)

`DelegationPayload.context_snapshot` is `dict[str, Any]` but `ScopedContext` returns `ContextValue` objects with provenance and classification metadata. When context is serialized into DelegationPayload, classification information is LOST. The child cannot know what clearance level the data was at in the parent's scope.

**Resolution**: Extend `DelegationPayload.context_snapshot` to carry `dict[str, ContextValue.to_dict()]` instead of `dict[str, Any]`, preserving classification metadata through the message boundary. This is an additive change to the L3 messaging types.

---

## 3. Architecture Decision Conflict

### ADR-ORC-01: Package Placement (CONFLICTING RECOMMENDATIONS)

| Agent                    | Recommendation                                  | Rationale                                                                     |
| ------------------------ | ----------------------------------------------- | ----------------------------------------------------------------------------- |
| **framework-advisor**    | Subpackage (`kaizen/agents/l3/`)                | Follows AD-L3-01 precedent; avoids separate package overhead                  |
| **requirements-analyst** | Separate PyPI package (`kailash-kaizen-agents`) | LLM dependency boundary is fundamental; L3 users shouldn't pull LLM providers |
| **deep-analyst**         | Flagged as decision point                       | "Separate package adds deployment complexity but enforces boundary"           |

**Analysis**: The framework advisor's argument is stronger for the current phase:

1. kailash-kaizen ALREADY depends on LLM providers (BaseAgent, signatures, llm module)
2. There is NO "L3 SDK without LLM" use case — users who install kaizen already get LLM infrastructure
3. AD-L3-01 explicitly rejected separate packages: "Adds deployment complexity with no benefit"
4. Single version number eliminates compatibility matrix

**Resolution**: Subpackage at `kaizen/agents/l3/`. Revisit if kaizen-agents grows large enough to justify separation.

---

## 4. Critical Insights from Value Auditor

The value auditor's assessment is the most important strategic input:

### "The foundation is exceptional; the house is not yet built on it."

The L3 SDK has:

- 7,242 lines of source, 10,029 lines of tests
- NaN injection protection (~100 tests), state machine fuzzing (~100 tests)
- Red team with 23 findings addressed
- Non-bypassable enforcement (no `disable()` or `bypass()` methods)

But zero agents actually doing governed work. The kaizen-agents layer IS the product.

### 20-Concept Learning Curve

The L3 SDK surface has ~20 concepts. This must be hidden behind progressive disclosure:

- **Layer 1**: `GovernedAgent(model="gpt-4", budget_usd=10.0)` — Just Works
- **Layer 2**: Custom envelope, gradient config, tools
- **Layer 3**: Direct L3 primitive access

### Demo-Ready Path

The value auditor's demo scenario (5 research agents, live budget bars, one HOLD event, reallocation, audit trail) is the minimum viable demo. All SDK primitives exist to support it. Only the orchestration intelligence is missing.

---

## 5. Refined Risk Register (Agent-Informed)

### New Risks Identified by Agents

| ID           | Severity | Risk                                                                          | Source        |
| ------------ | -------- | ----------------------------------------------------------------------------- | ------------- |
| **R-NEW-01** | CRITICAL | PlanExecutor sync/async mismatch blocks entire orchestration layer            | deep-analyst  |
| **R-NEW-02** | CRITICAL | Context classification metadata lost in DelegationPayload serialization       | deep-analyst  |
| **R-NEW-03** | CRITICAL | Plan fingerprinting needed to detect re-delegation loops                      | deep-analyst  |
| **R-NEW-04** | HIGH     | AgentSpec.metadata has no schema — orchestration layer needs conventions      | deep-analyst  |
| **R-NEW-05** | HIGH     | LLM must produce input_mapping with PlanNodeOutput references — non-trivial   | deep-analyst  |
| **R-NEW-06** | HIGH     | 20-concept surface area blocks adoption without high-level API                | value-auditor |
| **R-NEW-07** | MEDIUM   | EnvelopeAllocator must handle ALL 3 depletable dimensions, not just financial | deep-analyst  |
| **R-NEW-08** | MEDIUM   | SharedMemoryPool → MessageRouter migration path undefined                     | deep-analyst  |

### Upgraded Risks

| Original               | New Severity                  | Reason                                                                             |
| ---------------------- | ----------------------------- | ---------------------------------------------------------------------------------- |
| R1 (LLM hallucination) | CRITICAL (unchanged)          | Deep analyst confirms: "who watches the watchmen" problem in PlanEvaluator         |
| R2 (Escalation loops)  | CRITICAL (unchanged)          | Deep analyst: plan fingerprinting + failure memory with exponential backoff needed |
| R6 (Context leakage)   | CRITICAL (upgraded from HIGH) | Deep analyst: free-text task_description bypasses all context classification       |

---

## 6. Refined Implementation Plan

### Pre-Implementation SDK Changes (M-1)

Before any orchestration work, resolve BLOCK-01 and BLOCK-02:

1. Add `AsyncNodeCallback` to PlanExecutor (non-breaking)
2. Extend DelegationPayload.context_snapshot to preserve ContextValue metadata (additive)
3. Define AgentSpec.metadata conventions for orchestration layer

### Updated Milestone Order

```
M-1: SDK prep (AsyncNodeCallback, DelegationPayload fix)    — 1 session
M0:  L3RuntimeBridge (wires async PlanExecutor to agents)     — 1 session
M1:  Plan Generation Pipeline (signatures for LLM decisions)  — 2 sessions
M2:  GovernedAgent high-level API + end-to-end demo           — 1 session  ← NEW
M3:  Communication Protocols (delegation, completion)         — 1 session
M4:  Failure Recovery (diagnoser, recomposer, fingerprinting) — 1 session
M5:  Advanced Protocols (clarification, escalation, matching) — 1 session
M6:  Classification & Polish                                  — 1 session
Total: 9-10 autonomous sessions
```

**Key change**: M2 (GovernedAgent + demo) is pulled forward to P0, before advanced protocols. The value auditor is right — a working demo is worth more than all architecture docs combined.

---

## 7. Decision Points for Human Review

These require stakeholder input before implementation begins:

1. **PlanExecutor async strategy**: Add async variant (backward-compatible) or full async migration (breaking)?
2. **DelegationPayload extension**: Preserve full ContextValue metadata or just classification level?
3. **GovernedAgent API design**: What should the Layer 1 API look like?
4. **ClassificationAssigner enforcement mode**: Hard enforcement (block) or advisory (warn)?
5. **Existing pattern migration**: L0-L2 patterns coexist, get L3 adapters, or are deprecated?
6. **Demo scenario**: Which end-to-end task demonstrates the value proposition best?
