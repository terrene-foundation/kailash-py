# Risk Assessment — kaizen-agents Orchestration Layer

## 1. Critical Risks

### R1: LLM Hallucination in Plan Generation (Severity: CRITICAL)

**Risk**: TaskDecomposer generates subtasks that don't cover the objective. PlanComposer wires edges incorrectly (missing data dependencies, wrong parallelism). AgentDesigner selects wrong tools or capabilities.

**Impact**: Plan executes but produces wrong results. Budget consumed. Audit trail shows "success" for a flawed plan.

**Mitigation**:

1. PlanValidator (SDK) catches structural impossibilities deterministically
2. PlanEvaluator (orchestration) provides semantic sanity check
3. Budget thresholds (gradient flag at 80%, hold at 95%) provide early warning
4. Envelope enforcement prevents runaway execution
5. Human-on-the-loop: critical plans require HELD → human approval before execution

**Residual Risk**: Medium. PlanEvaluator itself uses LLM — turtles all the way down. Ultimately depends on LLM quality.

### R2: Escalation Loops (Severity: CRITICAL)

**Risk**: Child escalates failure. Parent's FailureDiagnoser generates a recovery plan that hits the same failure. New child escalates. Loop continues until budget exhaustion.

**Impact**: Budget consumed without progress. Potential cascade of failures across plan.

**Mitigation**:

1. `retry_budget` in PlanGradient limits retries (default: 2)
2. `after_retry_exhaustion` escalates to HELD (not infinite retry)
3. `resolution_timeout_seconds` (default: 300s) auto-blocks held nodes
4. **New requirement**: Recomposer MUST track previous recovery attempts. If same failure recurs after recovery, escalate to HELD immediately (do not retry).

**Residual Risk**: Low with mitigation. The gradient system provides multiple circuit breakers.

### R3: L3RuntimeBridge Complexity (Severity: CRITICAL)

**Risk**: The bridge between PlanExecutor (sync, deterministic) and orchestration layer (async, LLM-dependent) is the most complex integration point. Race conditions between plan events and orchestration responses.

**Impact**: Deadlocks, lost events, inconsistent plan state.

**Mitigation**:

1. Clear event model: PlanExecutor emits events via callback, orchestration layer responds via PlanModification
2. Resolution timeout provides bounded wait
3. asyncio.Lock serialization (already in L3 primitives via AD-L3-04-AMENDED)
4. Comprehensive integration tests with deterministic LLM mocks

**Residual Risk**: Medium. This bridge requires careful implementation and extensive testing.

---

## 2. High Risks

### R4: Budget Allocation Accuracy (Severity: HIGH)

**Risk**: EnvelopeAllocator (LLM) estimates poorly — over-provisions some children, under-provisions others. Under-provisioned agents hit budget limits and fail.

**Impact**: Plan failures due to budget, not task difficulty. Wasted budget on over-provisioned agents.

**Mitigation**:

1. Budget reclamation on child completion returns unused budget to parent
2. Plan modification (UpdateSpec) can reallocate budget at runtime
3. Envelope flag threshold (80%) provides early warning before exhaustion
4. **New requirement**: EnvelopeAllocator should reserve a contingency (e.g., 10% of parent budget) for reallocation

**Residual Risk**: Medium. Budget estimation is inherently uncertain.

### R5: Clarification Deadlock (Severity: HIGH)

**Risk**: Child sends blocking clarification. Parent is also in Waiting state (waiting for another child). Neither can proceed.

**Impact**: Both agents stuck. Resolution timeout eventually blocks both.

**Mitigation**:

1. Resolution timeout (300s default) breaks any deadlock
2. **Design rule**: Only non-blocking clarifications when parent is in Waiting state
3. ClarificationProtocol should detect waiting parent and auto-escalate to non-blocking

**Residual Risk**: Low with design rule.

### R6: Context Leakage Through Messages (Severity: HIGH)

**Risk**: Agent A has C4 (TOP_SECRET) context. Agent A composes a DelegationPayload.task_description that includes classified information in natural language. The message passes through MessageRouter (which checks communication envelope, not content).

**Impact**: Classification bypass — sensitive data leaks to agents without appropriate clearance.

**Mitigation**:

1. ScopedContext's read projection already filters what agent A can SEE
2. **New requirement**: DelegationProtocol should compose task_description using only the context_snapshot (which is projected), not the agent's full memory
3. ClassificationAssigner can scan outgoing message content (expensive but available)
4. Audit trail records all messages for post-hoc review

**Residual Risk**: Medium. Content-level classification is hard — LLMs can paraphrase classified information.

---

## 3. Medium Risks

### R7: Testing LLM-Dependent Components

**Risk**: Orchestration components are non-deterministic (LLM output varies). Standard unit tests don't verify correctness.

**Mitigation**:

- **Tier 1**: Signature-level tests with mocked LLM responses (deterministic)
- **Tier 2**: Integration tests with cheap models (Haiku) and golden-file verification
- **Tier 3**: End-to-end with real LLMs, assertion on invariants (not exact output)
- SDK conformance tests remain fully deterministic

### R8: Package Dependency Bloat

**Risk**: kaizen-agents depends on kailash-kaizen (which depends on kailash core). Adding orchestration-specific dependencies (LLM providers, embedding models) increases install footprint.

**Mitigation**: Lazy imports for optional dependencies. Core kaizen-agents with minimal deps; extras for specific providers.

### R9: Existing Pattern Migration Friction

**Risk**: Users on L0-L2 patterns (SupervisorWorkerPattern, etc.) expected to migrate to L3. Breaking changes or divergent APIs.

**Mitigation**: L0-L2 patterns coexist unchanged. L3 is additive. Migration guide provided but not forced.

---

## 4. Dependency Map

```
                           kaizen-agents (NEW)
                          /        |        \
                         /         |         \
              TaskDecomposer  PlanComposer  L3RuntimeBridge
                    |              |              |
                    |              |              |
              AgentDesigner  EnvelopeAllocator   |
                    |              |              |
                    v              v              v
              ┌─────────────────────────────────────────┐
              │         kailash-kaizen L3 SDK           │
              │  (EnvelopeTracker, ScopedContext,       │
              │   MessageRouter, AgentFactory,          │
              │   PlanValidator, PlanExecutor)          │
              └─────────────────────────────────────────┘
                              |
              ┌───────────────┼───────────────┐
              v               v               v
         kailash-pact    kailash-trust    kailash (core)
         (governance)    (EATP audit)     (workflow engine)
```

---

## 5. Risk Summary Matrix

| Risk                        | Severity | Likelihood | Mitigation Quality  | Residual Risk |
| --------------------------- | -------- | ---------- | ------------------- | ------------- |
| R1: LLM hallucination       | Critical | High       | Good (multi-layer)  | Medium        |
| R2: Escalation loops        | Critical | Medium     | Strong (gradient)   | Low           |
| R3: Bridge complexity       | Critical | Medium     | Medium (design)     | Medium        |
| R4: Budget accuracy         | High     | High       | Good (reclamation)  | Medium        |
| R5: Clarification deadlock  | High     | Low        | Strong (timeout)    | Low           |
| R6: Context leakage         | High     | Medium     | Medium (projection) | Medium        |
| R7: Testing non-determinism | Medium   | High       | Good (tiered)       | Low           |
| R8: Dependency bloat        | Medium   | Low        | Good (lazy)         | Low           |
| R9: Migration friction      | Medium   | Medium     | Good (coexist)      | Low           |
