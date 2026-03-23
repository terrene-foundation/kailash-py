# Implementation Plan — kaizen-agents Orchestration Layer

## 1. Architecture Decision

### AD-ORC-01: Package Placement — Subpackage of kailash-kaizen

**Decision**: kaizen-agents is a subpackage within kailash-kaizen (`kaizen.agents.l3`), NOT a separate PyPI package.

**Rationale**:

1. The orchestration layer is tightly coupled to L3 SDK primitives — separate versioning creates compatibility risk
2. Kaizen already has `kaizen/agents/` with specialized and coordination subpackages
3. The LLM dependency already exists in kailash-kaizen (BaseAgent, signatures, llm providers)
4. Users install `pip install kailash-kaizen` and get both SDK primitives and orchestration layer
5. Single version number eliminates SDK/orchestration version matrix

**Trade-off**: Larger install footprint. Mitigated by lazy imports for optional LLM providers.

### AD-ORC-02: Component Pattern — Kaizen Signatures

**Decision**: Orchestration components use Kaizen's signature-based programming for LLM calls.

**Rationale**:

1. Signatures provide declarative input/output contracts — natural fit for "objective in, subtasks out"
2. Signatures are testable at the mock boundary (swap LLM response, verify output parsing)
3. Signatures integrate with Kaizen's LLM provider abstraction (OpenAI, Anthropic, Ollama)
4. DSPy-style optimization can improve signatures over time

**Pattern**:

```python
class DecomposeObjective(Signature):
    """Break an objective into subtasks suitable for agent delegation."""
    objective: str = InputField(desc="The high-level objective")
    constraints: str = InputField(desc="Budget and tool constraints from parent envelope")
    subtasks: list[Subtask] = OutputField(desc="Ordered list of subtasks")
    rationale: str = OutputField(desc="Why this decomposition was chosen")
```

### AD-ORC-03: Event Consumption — Async Callback Pattern

**Decision**: PlanExecutor events are consumed via an async callback injected at execution time.

**Rationale**:

1. PlanExecutor already uses a `node_callback` pattern
2. Adding an `event_callback` for orchestration events (NodeHeld, EnvelopeWarning) is consistent
3. No pub/sub infrastructure needed — direct callback is simplest
4. The orchestration layer registers its FailureDiagnoser + Recomposer as the event handler

### AD-ORC-04: Protocol Pattern — Stateful Protocol Objects

**Decision**: Communication protocols (Delegation, Clarification, Escalation, Completion) are stateful objects, not standalone functions.

**Rationale**:

1. Protocols have lifecycle state (waiting for response, timed out, completed)
2. Protocols need correlation tracking (request → response matching)
3. Stateful objects can enforce invariants (e.g., "don't send clarification if parent is waiting")
4. Protocol objects compose naturally: `DelegationProtocol` creates a `CompletionProtocol` on delegation

### AD-ORC-05: Testing Strategy — Three Tiers

**Decision**: Tests are structured in three tiers matching existing Kaizen testing patterns.

| Tier            | What                                                   | How                                             | Mocking                         |
| --------------- | ------------------------------------------------------ | ----------------------------------------------- | ------------------------------- |
| 1 (Unit)        | Individual signatures, protocol state machines         | Mock LLM responses at signature boundary        | Allowed (LLM only)              |
| 2 (Integration) | Cross-component flows (decompose → compose → validate) | Cheap LLM (Haiku) with golden files             | NO mocking of L3 SDK primitives |
| 3 (E2E)         | Full plan lifecycle (objective → execution → result)   | Real LLM, assert on invariants not exact output | NO mocking                      |

---

## 2. Module Structure

```
packages/kailash-kaizen/src/kaizen/agents/l3/
    __init__.py                         # Public API
    _bridge.py                          # L3RuntimeBridge (PlanExecutor ↔ orchestration)

    planning/                           # Plan generation pipeline
        __init__.py
        decomposer.py                   # TaskDecomposer signature
        composer.py                     # PlanComposer signature
        designer.py                     # AgentDesigner signature
        allocator.py                    # EnvelopeAllocator signature
        evaluator.py                    # PlanEvaluator signature
        types.py                        # Subtask, DecompositionResult, etc.

    recovery/                           # Failure handling
        __init__.py
        diagnoser.py                    # FailureDiagnoser signature
        recomposer.py                   # Recomposer signature
        _history.py                     # Recovery attempt tracking (R2 mitigation)

    protocols/                          # Communication protocols
        __init__.py
        delegation.py                   # DelegationProtocol
        clarification.py                # ClarificationProtocol
        escalation.py                   # EscalationProtocol
        completion.py                   # CompletionProtocol

    classification/                     # Content classification
        __init__.py
        assigner.py                     # ClassificationAssigner signature
        matcher.py                      # CapabilityMatcher signature

    aggregation/                        # Result aggregation
        __init__.py
        aggregator.py                   # ResultAggregator signature
```

---

## 3. Implementation Milestones

### M0: L3RuntimeBridge (P0 — Foundation)

The bridge wires PlanExecutor to the orchestration layer. Everything depends on this.

**Deliverables**:

1. `L3RuntimeBridge` class that implements PlanExecutor's `node_callback` and `event_callback`
2. `node_callback` implementation: spawn agent (Factory), create scope (ScopedContext), send delegation (MessageRouter), run agent, receive completion, update plan
3. `event_callback` implementation: route NodeHeld to FailureDiagnoser, EnvelopeWarning to budget monitor
4. Integration tests with mock LLM and real L3 SDK primitives

**Acceptance**:

- [ ] Bridge executes a 3-node linear plan end-to-end (mocked LLM)
- [ ] Bridge handles NodeHeld event and applies PlanModification within timeout
- [ ] Bridge handles EnvelopeWarning without blocking execution
- [ ] Budget reclamation works after node completion

### M1: Plan Generation Pipeline (P0)

**Deliverables**:

1. `DecomposeObjective` signature + `TaskDecomposer` module
2. `DesignAgent` signature + `AgentDesigner` module
3. `AllocateEnvelope` signature + `EnvelopeAllocator` module
4. `ComposePlan` signature + `PlanComposer` module
5. `EvaluatePlan` signature + `PlanEvaluator` module

**Acceptance**:

- [ ] TaskDecomposer produces valid subtask list from objective string
- [ ] AgentDesigner produces valid AgentSpec (passes SDK validation)
- [ ] EnvelopeAllocator produces envelopes that sum <= parent (INV-PLAN-06)
- [ ] PlanComposer produces valid Plan DAG (passes PlanValidator)
- [ ] PlanEvaluator catches semantically invalid plans (wrong decomposition)
- [ ] Full pipeline: objective → validated Plan DAG in one call

### M2: Communication Protocols (P0)

**Deliverables**:

1. `DelegationProtocol` with task_description composition
2. `CompletionProtocol` with result validation and context merge
3. Protocol state machines with correlation tracking

**Acceptance**:

- [ ] DelegationProtocol composes DelegationPayload with projected context
- [ ] CompletionProtocol validates result quality (LLM judgment)
- [ ] CompletionProtocol merges context_updates back to parent scope
- [ ] Correlation IDs correctly link delegation → completion

### M3: Failure Recovery (P1)

**Deliverables**:

1. `FailureDiagnoser` signature with error analysis
2. `Recomposer` signature with PlanModification generation
3. Recovery history tracking (R2 mitigation)

**Acceptance**:

- [ ] FailureDiagnoser classifies failures (retryable / recoverable / fatal)
- [ ] Recomposer generates valid PlanModification (passes SDK validation)
- [ ] Recovery history prevents same-failure loops (R2)
- [ ] Integration: NodeHeld → diagnose → recompose → apply → resume

### M4: Advanced Protocols (P1)

**Deliverables**:

1. `ClarificationProtocol` with bidirectional exchange
2. `EscalationProtocol` with severity-based routing
3. `CapabilityMatcher` for semantic agent selection
4. `ResultAggregator` for multi-output synthesis

**Acceptance**:

- [ ] Blocking clarification suspends child agent correctly
- [ ] Non-blocking clarification when parent is Waiting (R5 mitigation)
- [ ] Escalation routes to correct handler based on severity
- [ ] CapabilityMatcher selects appropriate agent for subtask
- [ ] ResultAggregator synthesizes leaf outputs into unified result

### M5: Classification & Polish (P2)

**Deliverables**:

1. `ClassificationAssigner` for data sensitivity assessment
2. L0-L2 pattern adapters (optional L3 governance on existing patterns)
3. Public API surface (`kaizen.agents.l3.__init__.py`)
4. Documentation and examples

**Acceptance**:

- [ ] ClassificationAssigner produces valid DataClassification
- [ ] SupervisorWorkerPattern works with optional L3 envelope
- [ ] Public API is clean and documented
- [ ] Example: "Deploy 3 agents to review code with $10 budget"

---

## 4. Critical Path

```
M0 (Bridge)
  ├── M1 (Planning) ──── can start immediately, validates against SDK
  │     └── M2 (Protocols) ── needs planning types for delegation
  │           └── M3 (Recovery) ── needs protocols for escalation
  │                 └── M4 (Advanced) ── builds on M3 patterns
  └── M5 (Classification) ── independent, can parallelize with M3/M4
```

**Minimum viable**: M0 + M1 + M2 = agent can decompose objectives, generate plans, delegate to children, and collect results. This is the "hello world" of governed autonomous agents.

---

## 5. Testing Strategy Detail

### Tier 1: Signature-Level Unit Tests

For each signature (DecomposeObjective, DesignAgent, etc.):

- Mock LLM response with valid structured output
- Verify output parsing and type validation
- Test error cases (malformed LLM response, missing fields)
- Test constraint validation (envelope sum, tool subsetting)

### Tier 2: Integration with Real SDK Primitives

For cross-component flows:

- Use cheap LLM (Haiku) for real LLM calls
- Use real L3 SDK primitives (no mocking — per testing rules)
- Golden-file verification: record LLM responses, replay for regression
- Test: objective → plan → validated → execution started

### Tier 3: End-to-End Plan Lifecycle

Full lifecycle tests:

- Real LLM, real SDK, real plan execution
- Assert on invariants: all envelopes valid, no budget overflow, all events emitted
- Do NOT assert on exact LLM output
- Test failure paths: node failure → diagnose → recover → retry
