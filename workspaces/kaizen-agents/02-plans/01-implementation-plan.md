# kaizen-agents Implementation Plan

**Date**: 2026-03-23
**Approach**: SDK async-first — fix SDK bugs, build orchestration against correct async API

---

## SDK Prerequisites (fix in kailash-kaizen)

The kailash SDK is async-first. These are SDK defects, not design constraints. Fix them in `packages/kailash-kaizen/` before wiring orchestration.

### S1: Async PlanExecutor
- Current: PlanExecutor is synchronous, blocking
- Required: Async execution with event callbacks, concurrent node execution
- Location: `packages/kailash-kaizen/src/kaizen/l3/plan/executor.py`

### S2: HELD as Real State
- Current: Phantom — nodes stay FAILED, emit "held" event
- Required: HELD as a real state in PlanNodeState with pause-diagnose-resume transitions
- Location: `packages/kailash-kaizen/src/kaizen/l3/plan/types.py`

### S3: Structured Signature Output
- Current: String-only OutputField
- Required: Typed output parsing for structured objects (Plan DAGs, AgentSpecs)
- Location: `packages/kailash-kaizen/src/kaizen/signatures/`

---

## Phase 0: SDK Wiring

Replace local types with real SDK imports. Wire to async SDK primitives (after S1-S3 are fixed).

### P0-01: Type Compatibility Matrix
- Map every local type in `types.py` to its SDK equivalent
- Document field name differences, casing, representation mismatches
- Specifically: ConstraintEnvelope (local dict) vs PACT typed dataclasses, GradientZone casing
- **Evidence**: Compatibility matrix document with every type mapped

### P0-02: Replace types.py with SDK imports
- Delete local `types.py`
- Create `sdk.py` adapter where needed (orchestration-specific extensions only)
- Update all imports across planner/, recovery/, context/, policy/
- **Evidence**: Zero local type definitions that shadow SDK types

### P0-03: Wire PlanMonitor to async PlanExecutor
- PlanMonitor uses SDK async PlanExecutor (after S1 is fixed)
- Concurrent node execution via PlanExecutor's async API
- State transitions owned by SDK PlanExecutor
- **Evidence**: Multi-node plan executes with parallel independent nodes

### P0-04: Wire recovery to real HELD state
- FailureDiagnoser receives HELD nodes (real state, after S2 is fixed)
- Recomposer produces PlanModification targeting HELD nodes
- Resume transition: HELD → READY after modification applied
- **Evidence**: Node fails → HELD → diagnose → modify → resume → complete

### P0-05: Wire PlanComposer to Signatures
- PlanComposer uses SDK Signatures for structured output (after S3 is fixed)
- Produces SDK Plan type via typed Signature, validated by PlanValidator
- **Evidence**: PlanComposer produces valid SDK Plan from Signature output

### P0-06: Fix tests
- All tests pass against SDK types
- Import verification test: no local type shadows
- NaN vulnerability fixes in monitor.py (zero-tolerance, pre-existing)
- **Evidence**: pytest passes, security defects fixed

---

## Phase 1: Complete Missing Integrations

### P1-01: Wire protocols to SDK MessageRouter
- Protocols have real LLM composition logic (NOT stubs — red team corrected this)
- Missing: message transport via SDK MessageRouter
- Add: MessageRouter.route() calls, MessageChannel consumption, correlation tracking, TTL
- **Evidence**: Delegation protocol sends message, receives completion, end-to-end via SDK

### P1-02: Wire EnvelopeAllocator to SDK EnvelopeSplitter
- Replace local allocation with SDK EnvelopeSplitter.split()
- Keep BudgetPolicy (reserve, reallocation) as orchestration concern
- **Evidence**: Parent envelope split correctly across child agents

### P1-03: Wire Context to SDK ScopedContext
- Replace local context dicts with SDK ContextScope
- ContextInjector uses ContextScope.create_child()
- ClassificationAssigner uses SDK DataClassification levels
- **Evidence**: Child agent receives filtered context by classification

---

## Phase 2: Governance (M4)

### P2-00: PACT SDK Integration Map
- Map each governance requirement to existing PACT SDK classes
- GovernanceEngine, PactGovernedAgent, GovernanceEnvelopeAdapter, AuditChain, GradientEngine
- **Evidence**: Integration map document

### P2-01: EATP Audit Trail
### P2-02: D/T/R Accountability
### P2-03: Knowledge Clearance
### P2-04: Cascade Revocation
### P2-05: Vacancy Handling
### P2-06: Gradient Dereliction Detection
### P2-07: Emergency Bypass
### P2-08: Budget Reclamation + Warnings

---

## Phase 3: Red Team to Convergence

- Round 1: Structural audit against authority feature matrix
- Round 2: Integration verification (real SDK calls end-to-end)
- Round 3: Cross-SDK behavioral alignment with kailash-rs

### Convergence Criteria
- 0 CRITICAL, 0 HIGH findings
- All integration tests pass with real SDK
- NaN/Inf security checks on all numeric paths
- Cross-SDK behavioral test suite passing

---

## Dependencies

```
S1-S3 (SDK fixes in kailash-kaizen) — MUST be done first
  │
  ├── P0: SDK Wiring
  │   └── P1: Missing Integrations
  │       └── P2: Governance
  │           └── P3: Red Team
  │
  S1-S3 are in the same monorepo — no cross-repo blocking
```
