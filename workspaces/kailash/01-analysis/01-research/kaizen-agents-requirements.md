# kaizen-agents Requirements Analysis

## Executive Summary

- **Feature**: LLM-dependent orchestration layer on top of kailash-kaizen L3 SDK primitives
- **Complexity**: High (13 components across 4 subsystems, deep integration with 5 L3 primitive modules)
- **Risk Level**: High (LLM non-determinism meets deterministic governance invariants)
- **Estimated Effort**: 5-7 autonomous sessions across parallel tracks

The `kaizen-agents` package bridges the gap between deterministic L3 SDK primitives (which validate and enforce) and the LLM-driven decisions (which create and compose). Every component in `kaizen-agents` produces output that an L3 primitive consumes and validates -- the LLM proposes, the SDK disposes.

---

## 1. Requirements Decomposition

### 1.1 Plan Generation Pipeline

#### COMP-01: TaskDecomposer

**Purpose**: Break a high-level objective into a flat list of atomic subtasks suitable for agent assignment.

**Inputs**:

- `objective: str` -- natural language description of the goal
- `context: dict[str, Any]` -- available context from parent ScopedContext snapshot
- `parent_envelope: dict[str, Any]` -- budget/constraint envelope constraining total plan
- `available_capabilities: list[str]` -- capabilities registered in AgentFactory's spec catalog
- `max_subtasks: int` -- upper bound on decomposition fanout (default: 20)

**Outputs**:

- `subtasks: list[Subtask]` where `Subtask` is a frozen dataclass:
  ```
  Subtask(subtask_id, description, required_capabilities, estimated_cost,
          dependencies: list[str], optional: bool, context_keys_needed: list[str],
          context_keys_produced: list[str])
  ```

**Business Logic**:

1. Invoke LLM with structured output (Kaizen Signature: `objective, context, capabilities -> subtasks`)
2. Validate subtask count <= `max_subtasks`
3. Validate estimated costs are finite and non-negative (pre-check before SDK enforcement)
4. Validate no circular dependencies in the subtask dependency list
5. Validate all `required_capabilities` exist in `available_capabilities`

**Invariants**:

- INV-TD-01: Sum of `estimated_cost` across subtasks MUST NOT exceed `parent_envelope.financial_limit` (pre-check; SDK validates definitively)
- INV-TD-02: Every subtask MUST have at least one capability that maps to a known AgentSpec
- INV-TD-03: Subtask dependency graph MUST be acyclic

**Edge Cases**:

- LLM returns empty subtask list -> re-prompt with explicit "the objective requires at least one step"
- LLM returns circular dependencies -> strip dependencies and log warning; PlanComposer handles linearization
- LLM hallucinates capabilities not in the available set -> filter to known capabilities + flag for AgentDesigner
- Estimated costs sum exceeds budget -> request LLM to reduce scope or merge subtasks

**SDK Mapping**: Output feeds directly into PlanComposer (COMP-02) and AgentDesigner (COMP-03)

---

#### COMP-02: PlanComposer

**Purpose**: Wire subtasks into a valid Plan DAG with correct PlanEdge dependencies and PlanNode structure.

**Inputs**:

- `subtasks: list[Subtask]` -- from TaskDecomposer
- `agent_specs: dict[str, AgentSpec]` -- from AgentDesigner (subtask_id -> AgentSpec)
- `allocations: dict[str, AllocationRequest]` -- from EnvelopeAllocator (subtask_id -> allocation)
- `parent_envelope: dict[str, Any]` -- parent budget envelope
- `gradient: PlanGradient` -- gradient configuration for the plan

**Outputs**:

- `plan: Plan` (in `PlanState.DRAFT`) -- the L3 Plan DAG ready for validation

**Business Logic**:

1. Create `PlanNode` for each subtask, mapping `subtask_id` -> `node_id`, `agent_spec_id` from AgentDesigner output
2. Infer `PlanEdge` relationships:
   - Explicit dependencies from `Subtask.dependencies` -> `EdgeType.DATA_DEPENDENCY`
   - Implicit data flow from `context_keys_produced` / `context_keys_needed` -> `EdgeType.DATA_DEPENDENCY`
   - Optional advisory co-start hints from LLM -> `EdgeType.CO_START`
3. Build `input_mapping` from dependency edges (source_node + output_key)
4. Set `node.envelope` from EnvelopeAllocator output
5. Set `node.optional` from `Subtask.optional`
6. Construct `Plan` with all nodes, edges, envelope, gradient, and state=DRAFT
7. Optionally invoke LLM for edge refinement: "given these subtasks, are there additional data dependencies I missed?"

**Invariants**:

- INV-PC-01: Every subtask MUST appear as exactly one PlanNode
- INV-PC-02: Plan MUST pass `PlanValidator.validate_structure()` (no cycles, roots exist, leaves exist)
- INV-PC-03: Plan MUST pass `PlanValidator.validate_envelopes()` (budget summation, per-node tightening)

**Edge Cases**:

- Subtask has dependency on non-existent subtask -> drop edge, log warning
- All subtasks are independent -> valid DAG with no edges (parallel execution)
- Single subtask -> degenerate plan with one node, zero edges

**SDK Mapping**: Plan is validated by `PlanValidator.validate()` and executed by `PlanExecutor.execute()`

---

#### COMP-03: AgentDesigner

**Purpose**: Map each subtask to a concrete AgentSpec with appropriate tools, capabilities, envelope sizing, and configuration.

**Inputs**:

- `subtask: Subtask` -- a single subtask from TaskDecomposer
- `available_specs: list[AgentSpec]` -- catalog of known agent specifications
- `available_tools: list[str]` -- tools available from parent's tool set
- `parent_envelope: dict[str, Any]` -- parent's constraint envelope (for monotonic tightening)

**Outputs**:

- `agent_spec: AgentSpec` -- frozen dataclass blueprint for the agent

**Business Logic**:

1. Invoke CapabilityMatcher (COMP-13) to find specs whose capabilities overlap with `subtask.required_capabilities`
2. If exact match found, clone the spec with subtask-specific overrides
3. If no match, invoke LLM to design a new AgentSpec:
   - Select `tool_ids` subset from `available_tools` relevant to the task
   - Set `required_context_keys` from `subtask.context_keys_needed`
   - Set `produced_context_keys` from `subtask.context_keys_produced`
   - Set `description` from subtask description
   - Propose `max_lifetime`, `max_children`, `max_depth` based on task complexity
4. Validate that `tool_ids` is a subset of `available_tools` (enforce before AgentFactory.spawn checks)
5. Generate unique `spec_id` incorporating subtask lineage

**Invariants**:

- INV-AD-01: `agent_spec.tool_ids` MUST be a subset of `available_tools` (AgentFactory pre-check)
- INV-AD-02: `agent_spec.envelope` MUST be tighter than or equal to `parent_envelope` (monotonic tightening)
- INV-AD-03: Every AgentSpec MUST have a non-empty `spec_id` and `name`

**Edge Cases**:

- No matching spec and LLM proposes invalid tools -> filter to valid set, re-invoke if empty
- LLM proposes envelope wider than parent -> clamp to parent envelope, log
- Subtask requires no tools -> valid; agent may be a pure-reasoning agent

**SDK Mapping**: Output is consumed by `AgentFactory.spawn(child_spec, parent_id)`

---

#### COMP-04: EnvelopeAllocator

**Purpose**: Distribute parent budget to children based on LLM-estimated resource needs.

**Inputs**:

- `subtasks: list[Subtask]` -- subtasks with `estimated_cost`
- `parent_envelope: dict[str, Any]` -- parent's constraint envelope
- `reserve_pct: float` -- fraction to reserve for overhead/retries (default: 0.10)

**Outputs**:

- `allocations: list[AllocationRequest]` -- per-child allocation ratios
- `remaining_reserve: dict[str, float]` -- how much budget is reserved

**Business Logic**:

1. Compute raw ratios from `subtask.estimated_cost / total_estimated_cost` for financial dimension
2. Apply `reserve_pct` reduction (each child's ratio scaled by `1.0 - reserve_pct`)
3. For temporal dimension: invoke LLM to estimate relative time needs per subtask (or use proportional fallback)
4. Validate ratio sums (financial_ratios + reserve <= 1.0, temporal_ratios + reserve <= 1.0)
5. If LLM estimates produce ratios > 1.0, re-normalize to fit within budget
6. Build `AllocationRequest` per subtask with validated ratios

**Invariants**:

- INV-EA-01: `sum(financial_ratio) + reserve_pct <= 1.0` (enforced by `EnvelopeSplitter.split()`)
- INV-EA-02: Each `financial_ratio` in [0.0, 1.0] and finite (enforced by `AllocationRequest.__post_init__`)
- INV-EA-03: Each `temporal_ratio` in [0.0, 1.0] and finite

**Edge Cases**:

- All subtasks have zero estimated_cost -> equal allocation
- Single subtask -> ratio = 1.0 - reserve_pct
- LLM estimates wildly off (e.g., 90% for one task) -> cap individual allocation, redistribute

**SDK Mapping**: Output fed to `EnvelopeSplitter.split(parent, allocations, reserve_pct)` for deterministic validation

---

#### COMP-05: PlanEvaluator

**Purpose**: Semantic quality check on a composed plan before execution. Not structural validation (that is PlanValidator), but "does this plan make sense?"

**Inputs**:

- `plan: Plan` -- a validated plan (state: VALIDATED)
- `objective: str` -- the original objective
- `subtasks: list[Subtask]` -- the decomposition used

**Outputs**:

- `evaluation: PlanEvaluation` (frozen dataclass):
  ```
  PlanEvaluation(score: float, issues: list[str], suggestions: list[str],
                 approved: bool, reasoning: str)
  ```

**Business Logic**:

1. Invoke LLM as judge: "Given this objective and this plan, rate the plan quality 0-1"
2. Check for:
   - Missing subtasks that the objective implies
   - Redundant subtasks
   - Incorrect dependency ordering (semantic, not structural)
   - Budget allocation proportionality (does it make sense?)
   - Completeness (does the plan cover the full objective?)
3. If `score < threshold` (configurable, default 0.6), set `approved = False` with reasons
4. Return suggestions for improvement (fed back to TaskDecomposer/PlanComposer for iteration)

**Invariants**:

- INV-PE-01: Score MUST be in [0.0, 1.0] and finite
- INV-PE-02: Evaluation MUST NOT modify the Plan (read-only operation)
- INV-PE-03: If `approved = False`, `issues` list MUST be non-empty

**Edge Cases**:

- LLM always approves -> configurable minimum issue detection prompt
- LLM score is NaN/Inf -> reject evaluation, return default score 0.0 with issue "evaluation_error"

**SDK Mapping**: Advisory only; does not interact with L3 primitives directly. Gates plan execution.

---

### 1.2 Failure Recovery

#### COMP-06: FailureDiagnoser

**Purpose**: Interpret why a plan node failed, using LLM to analyze error context beyond what the PlanEvent provides.

**Inputs**:

- `failed_node: PlanNode` -- the node that failed
- `error_event: PlanEvent` -- the failure event (NodeFailed, NodeBlocked, NodeHeld)
- `plan: Plan` -- the full plan for context
- `execution_context: dict[str, Any]` -- context scope snapshot at failure time
- `recent_messages: list[MessageEnvelope]` -- last N messages involving the failed agent

**Outputs**:

- `diagnosis: FailureDiagnosis` (frozen dataclass):
  ```
  FailureDiagnosis(root_cause: str, severity: str, retryable: bool,
                   suggested_recovery: str, affected_downstream: list[str],
                   additional_context: dict[str, Any])
  ```

**Business Logic**:

1. Classify failure type: envelope_violation, runtime_error, timeout, dependency_failure, quality_failure
2. Invoke LLM with error context, node spec, and surrounding plan topology
3. Determine if the failure is recoverable via retry, recomposition, or escalation
4. Identify downstream nodes that may be affected (via DAG traversal -- deterministic, no LLM)
5. Generate human-readable diagnosis

**Invariants**:

- INV-FD-01: Diagnosis MUST NOT change plan state (read-only analysis)
- INV-FD-02: `affected_downstream` computed deterministically from plan edges, not from LLM

**Edge Cases**:

- Node failed with no error message -> LLM diagnoses from context only
- Envelope violation (BLOCKED) -> diagnosis is deterministic, LLM adds remediation suggestions
- Cascaded failure (upstream blocked) -> diagnosis differentiates root vs. cascaded

**SDK Mapping**: Consumes `PlanEvent` from `PlanExecutor`; output feeds `Recomposer` (COMP-07)

---

#### COMP-07: Recomposer

**Purpose**: Generate recovery `PlanModification` objects to repair a failed plan.

**Inputs**:

- `plan: Plan` -- the current (possibly SUSPENDED or partially FAILED) plan
- `diagnosis: FailureDiagnosis` -- from FailureDiagnoser
- `available_specs: list[AgentSpec]` -- spec catalog for replacement agents
- `remaining_budget: BudgetRemaining` -- from EnvelopeTracker

**Outputs**:

- `modifications: list[PlanModification]` -- ordered list of modifications to apply

**Business Logic**:

1. Based on diagnosis, select recovery strategy:
   - **Retry**: No modification needed (PlanExecutor handles retries)
   - **Replace**: Generate `PlanModification.replace_node()` with an alternative AgentSpec
   - **Skip**: Generate `PlanModification.skip_node()` for optional nodes
   - **Restructure**: Generate `PlanModification.add_node()` + `PlanModification.add_edge()` for workarounds
   - **Abort**: Return empty list (plan will fail)
2. Invoke LLM: "Given this failure diagnosis and remaining budget, propose a recovery"
3. Convert LLM proposal into concrete `PlanModification` objects
4. Ensure modifications are within remaining budget (pre-validate before SDK apply)
5. Order modifications correctly (removes before adds, edge updates after node updates)

**Invariants**:

- INV-RC-01: All modifications MUST maintain DAG validity (no cycles after apply)
- INV-RC-02: Budget for new/replacement nodes MUST come from reclaimed or reserved budget
- INV-RC-03: Modifications MUST NOT alter completed nodes

**Edge Cases**:

- No remaining budget for replacement -> skip or abort
- LLM proposes modification that would create a cycle -> reject and re-prompt
- Multiple nodes failed simultaneously -> batch modifications

**SDK Mapping**: Output passed to `apply_modifications(plan, modifications)` from `kaizen.l3.plan`

---

### 1.3 Communication Protocols

#### COMP-08: DelegationProtocol

**Purpose**: High-level protocol for composing and tracking delegation messages between parent and child agents.

**Inputs**:

- `task_description: str` -- what the child should do
- `child_instance_id: str` -- target child instance
- `parent_instance_id: str` -- source parent instance
- `context_snapshot: dict[str, Any]` -- relevant context for the child
- `child_envelope: dict[str, Any]` -- the child's allocated envelope
- `deadline: datetime | None` -- optional deadline
- `priority: Priority` -- message priority

**Outputs**:

- `delegation_message: MessageEnvelope` -- a complete message envelope with `DelegationPayload`
- Tracks correlation_id for matching completion responses

**Business Logic**:

1. Construct `DelegationPayload` from inputs
2. Wrap in `MessageEnvelope` with generated `message_id`, `correlation_id`, and `ttl_seconds`
3. Route via `MessageRouter.route()` to deliver to child's channel
4. Register correlation_id in an internal tracker for completion matching
5. Optionally invoke LLM to refine `task_description` for clarity (if description is terse)
6. Set TTL based on envelope temporal_limit or explicit deadline

**Invariants**:

- INV-DP-01: Every delegation MUST have a unique `correlation_id`
- INV-DP-02: `ttl_seconds` MUST be finite and positive (or None for no TTL)
- INV-DP-03: Child must be in Pending or Running state to receive delegation

**Edge Cases**:

- Child channel not yet created -> create channels before delegation (atomic)
- Message exceeds channel capacity -> backpressure (wait for space)
- Child was terminated before message delivery -> message goes to DeadLetterStore

**SDK Mapping**: `MessageRouter.route()`, `MessageChannel`, `DelegationPayload`

---

#### COMP-09: ClarificationProtocol

**Purpose**: Handle bidirectional clarification exchanges between child and parent.

**Inputs** (child asks):

- `question: str` -- the clarification question
- `blocking: bool` -- whether the child should pause execution
- `options: list[str] | None` -- optional suggested answers

**Inputs** (parent responds):

- `answer: str` -- the clarification answer
- `correlation_id: str` -- matching the question's correlation_id

**Outputs**:

- `clarification_message: MessageEnvelope` with `ClarificationPayload`

**Business Logic**:

1. Child sends `ClarificationPayload(question, blocking=True, is_response=False)`
2. If blocking, child agent transitions to `Waiting` state
3. Parent receives clarification, invokes LLM (or escalates to human) to generate answer
4. Parent sends `ClarificationPayload(answer, is_response=True)` with matching `correlation_id`
5. Child receives response, resumes execution
6. Track timeout: if no response within `resolution_timeout` (from PlanGradient), escalate or proceed with best-effort

**Invariants**:

- INV-CP-01: Response MUST have `correlation_id` matching the question's `message_id`
- INV-CP-02: If `blocking=True`, child MUST NOT proceed until response or timeout
- INV-CP-03: Both question and response routed through `MessageRouter` (validated)

**Edge Cases**:

- Parent has no context to answer -> escalate up the hierarchy
- Multiple clarifications in flight -> each tracked by separate correlation_id
- Timeout with no response -> child proceeds with conservative default (or fails)
- Non-blocking clarification -> child continues, incorporates answer when available

**SDK Mapping**: `MessageRouter.route()`, `ClarificationPayload`, `MessageChannel`

---

#### COMP-10: EscalationProtocol

**Purpose**: Receive escalation messages from children, diagnose the problem, and direct recovery.

**Inputs**:

- `escalation_message: MessageEnvelope` with `EscalationPayload`
- `plan: Plan` -- for context
- `router: MessageRouter` -- for responding

**Outputs**:

- Recovery action: one of retry, recompose, terminate, approve_hold, escalate_further

**Business Logic**:

1. Parse `EscalationPayload` (severity, problem_description, attempted_mitigations)
2. Based on severity:
   - `BLOCKED`: Invoke FailureDiagnoser + Recomposer
   - `WARNING`: Log + monitor (may invoke LLM for advice)
   - `BUDGET_ALERT`: Check remaining budget, optionally reallocate from reserve
   - `CRITICAL`: Invoke immediate recomposition or plan suspension
3. Invoke LLM for non-obvious escalations: "what should we do about this?"
4. Execute recovery action (send instructions back to child, or trigger plan modification)
5. If this agent cannot resolve, escalate to own parent (recursive escalation)

**Invariants**:

- INV-EP-01: Escalation response MUST reference the escalation's `correlation_id`
- INV-EP-02: Recovery action MUST be within the current agent's remaining budget
- INV-EP-03: Escalation chain MUST terminate (bounded by hierarchy depth)

**Edge Cases**:

- Root agent receives escalation with no parent -> log as unresolvable, apply best effort
- Multiple escalations from same child -> batch processing
- Escalation during plan suspension -> queue for resume

**SDK Mapping**: `MessageRouter`, `EscalationPayload`, feeds into FailureDiagnoser/Recomposer

---

#### COMP-11: CompletionProtocol

**Purpose**: Validate completion results from child agents and merge context.

**Inputs**:

- `completion_message: MessageEnvelope` with `CompletionPayload`
- `parent_context: ContextScope` -- parent's scoped context for merging
- `expected_outputs: list[str]` -- keys the child was expected to produce

**Outputs**:

- `validated: bool` -- whether the result meets quality expectations
- `merge_result: MergeResult` -- from ContextScope.merge_child_results()
- `quality_score: float` -- LLM-judged result quality

**Business Logic**:

1. Extract `CompletionPayload` (result, context_updates, resource_consumed, success)
2. If `success=False`, route to FailureDiagnoser (COMP-06)
3. If `success=True`:
   a. Invoke LLM quality judge: "does this result satisfy the original task?"
   b. Verify all `expected_outputs` are present in `context_updates`
   c. Merge context via `ContextScope.merge_child_results()` (deterministic SDK call)
   d. Trigger budget reclamation via `EnvelopeTracker.reclaim()` (deterministic SDK call)
4. Update PlanNode state to COMPLETED if quality passes, FAILED if not
5. Close communication channels

**Invariants**:

- INV-VP-01: Context merge MUST go through `ContextScope.merge_child_results()` (not raw dict update)
- INV-VP-02: Budget reclamation MUST happen after completion, before channel teardown
- INV-VP-03: `quality_score` MUST be in [0.0, 1.0] and finite

**Edge Cases**:

- Child reports success but result is empty -> quality check flags as low quality
- Context merge has conflicts -> CompletionProtocol respects MergeResult.conflicts
- Child over-consumed budget (resource_consumed > allocation) -> already handled by EnvelopeEnforcer during execution

**SDK Mapping**: `ContextScope.merge_child_results()`, `EnvelopeTracker.reclaim()`, `MessageRouter`

---

### 1.4 Content and Classification

#### COMP-12: ClassificationAssigner

**Purpose**: Use LLM to classify data sensitivity before storage in ScopedContext.

**Inputs**:

- `key: str` -- the context key being stored
- `value: Any` -- the value being stored
- `context_hints: dict[str, Any]` -- surrounding context for classification
- `default_classification: DataClassification` -- default if LLM is uncertain

**Outputs**:

- `classification: DataClassification` -- C0 (PUBLIC) through C4 (TOP_SECRET)

**Business Logic**:

1. Invoke LLM with Kaizen Signature: `key, value_summary, context -> classification`
2. Map LLM output string to `DataClassification` enum (IntEnum, C0-C4)
3. Apply monotonic tightening: classification can only escalate within a session, never relax
4. If LLM is uncertain, use `default_classification` (conservative fallback)
5. Cache classifications for repeated keys within the same scope

**Invariants**:

- INV-CA-01: Classification MUST be a valid `DataClassification` value (0-4)
- INV-CA-02: Classification MUST NOT exceed the scope's `effective_clearance` (validated by `ContextScope.set()`)
- INV-CA-03: Classification MUST NOT decrease for a key within a session (monotonic)

**Edge Cases**:

- LLM returns invalid classification -> use `default_classification`
- Value contains PII detected by heuristic but LLM says PUBLIC -> override to RESTRICTED (safety floor)
- Large value that cannot be sent to LLM -> classify by key name pattern only

**SDK Mapping**: Output passed to `ContextScope.set(key, value, classification)`, validated against `effective_clearance`

---

#### COMP-13: CapabilityMatcher

**Purpose**: Semantic matching of required capabilities to available AgentSpecs, beyond exact string comparison.

**Inputs**:

- `required_capabilities: list[str]` -- what the subtask needs
- `available_specs: list[AgentSpec]` -- catalog of available agents
- `min_match_score: float` -- minimum similarity threshold (default: 0.7)

**Outputs**:

- `matches: list[tuple[AgentSpec, float]]` -- ranked (spec, score) pairs

**Business Logic**:

1. First pass: exact string match on `AgentSpec.capabilities` (fast, no LLM)
2. Second pass (if no exact match): invoke LLM to score semantic similarity
   - "On a scale of 0-1, how well does this agent's capabilities match these requirements?"
3. Filter by `min_match_score`
4. Rank by score descending
5. Cache LLM similarity scores for repeated queries

**Invariants**:

- INV-CM-01: Exact string matches MUST score 1.0
- INV-CM-02: Score MUST be in [0.0, 1.0] and finite
- INV-CM-03: Empty `required_capabilities` -> all specs match with score 1.0

**Edge Cases**:

- No specs match at any threshold -> return empty list (AgentDesigner creates new spec)
- Single capability required, multiple specs have it -> rank by number of additional capabilities
- LLM returns non-numeric score -> parse failure, score 0.0

**SDK Mapping**: Used by AgentDesigner (COMP-03) to select specs before `AgentFactory.spawn()`

---

## 2. Interface Design

### 2.1 Core Protocol: LLMComponent

All 13 components share a common execution pattern. Each is a Kaizen Signature-based component.

```python
@dataclass(frozen=True)
class ComponentResult:
    """Standard wrapper for all component outputs."""
    output: Any
    llm_calls: int
    total_tokens: int
    total_cost_usd: float
    elapsed_seconds: float

class LLMComponent(Protocol):
    """Protocol all 13 components implement."""

    async def execute(self, **inputs) -> ComponentResult:
        """Execute the component. All LLM calls happen here."""
        ...

    @property
    def signature(self) -> Signature:
        """The Kaizen Signature defining I/O shape."""
        ...
```

### 2.2 Subsystem Interfaces

#### PlanGenerationPipeline

```python
class PlanGenerationPipeline:
    """Orchestrates COMP-01 through COMP-05 to produce a validated Plan."""

    def __init__(
        self,
        decomposer: TaskDecomposer,
        composer: PlanComposer,
        designer: AgentDesigner,
        allocator: EnvelopeAllocator,
        evaluator: PlanEvaluator,
        *,
        max_iterations: int = 3,  # re-compose if evaluator rejects
    ): ...

    async def generate(
        self,
        objective: str,
        parent_envelope: dict[str, Any],
        context: ContextScope,
        spec_catalog: list[AgentSpec],
        gradient: PlanGradient | None = None,
    ) -> tuple[Plan, PlanEvaluation]:
        """
        Full pipeline: decompose -> design agents -> allocate envelopes
        -> compose plan -> validate (SDK) -> evaluate (LLM).

        Returns validated Plan + evaluation. Iterates up to max_iterations
        if evaluator rejects the plan.
        """
        ...
```

#### FailureRecoveryPipeline

```python
class FailureRecoveryPipeline:
    """Orchestrates COMP-06 and COMP-07 for plan repair."""

    def __init__(
        self,
        diagnoser: FailureDiagnoser,
        recomposer: Recomposer,
    ): ...

    async def recover(
        self,
        plan: Plan,
        failed_event: PlanEvent,
        remaining_budget: BudgetRemaining,
        spec_catalog: list[AgentSpec],
    ) -> list[PlanModification]:
        """Diagnose failure and produce recovery modifications."""
        ...
```

#### CommunicationManager

```python
class CommunicationManager:
    """Orchestrates COMP-08 through COMP-11 as a unified messaging layer."""

    def __init__(
        self,
        router: MessageRouter,
        context_root: ContextScope,
        envelope_tracker: EnvelopeTracker,
    ): ...

    async def delegate(self, ...) -> str:
        """Delegate task, return correlation_id.""" ...

    async def handle_clarification(self, message: MessageEnvelope) -> None:
        """Process incoming clarification (invoke LLM or escalate).""" ...

    async def handle_escalation(self, message: MessageEnvelope) -> None:
        """Process escalation, trigger recovery if needed.""" ...

    async def handle_completion(self, message: MessageEnvelope) -> tuple[bool, MergeResult]:
        """Validate completion, merge context, reclaim budget.""" ...
```

### 2.3 Call Graph

```
User objective
    |
    v
PlanGenerationPipeline.generate()
    |
    |--> TaskDecomposer.execute()        [LLM call]
    |--> AgentDesigner.execute() x N     [LLM calls, uses CapabilityMatcher]
    |      \--> CapabilityMatcher        [LLM call if no exact match]
    |--> EnvelopeAllocator.execute()     [LLM call for temporal estimates]
    |--> PlanComposer.execute()          [LLM call for edge refinement]
    |--> PlanValidator.validate()        [SDK, deterministic]
    |--> PlanEvaluator.execute()         [LLM call]
    |
    v
PlanExecutor.execute()  [SDK, deterministic scheduling]
    |
    |--> For each ready node:
    |      |--> CommunicationManager.delegate()       [builds DelegationPayload]
    |      |      \--> MessageRouter.route()           [SDK, validated delivery]
    |      |--> AgentFactory.spawn()                   [SDK, precondition checks]
    |      |--> EnvelopeSplitter.split()               [SDK, budget split]
    |      |--> ContextScope.create_child()            [SDK, projection setup]
    |
    |--> On child messages:
    |      |--> ClarificationProtocol.handle()         [LLM to answer question]
    |      |--> EscalationProtocol.handle()            [LLM for recovery decision]
    |      |      \--> FailureRecoveryPipeline.recover() [LLM diagnosis + recomposition]
    |      |--> CompletionProtocol.handle()            [LLM quality validation]
    |             |--> ContextScope.merge_child_results()  [SDK, deterministic]
    |             |--> EnvelopeTracker.reclaim()            [SDK, deterministic]
    |
    |--> On failure events:
           |--> FailureDiagnoser.execute()             [LLM error analysis]
           |--> Recomposer.execute()                   [LLM plan modification]
           |--> apply_modifications()                  [SDK, deterministic]
```

---

## 3. Dependency Map

### 3.1 Inter-Component Dependencies

```
                   CapabilityMatcher (COMP-13)
                        |
                        v
TaskDecomposer -----> AgentDesigner -----> EnvelopeAllocator
   (COMP-01)          (COMP-03)             (COMP-04)
        \                |                      |
         \               v                      v
          '---------> PlanComposer ----------> PlanEvaluator
                      (COMP-02)                (COMP-05)
                         |
                         v
               [SDK: PlanValidator, PlanExecutor]
                         |
                         v
          DelegationProtocol (COMP-08)
                |
         .------+-------.---------.
         |              |         |
         v              v         v
  ClarificationProtocol  EscalationProtocol  CompletionProtocol
     (COMP-09)            (COMP-10)           (COMP-11)
                            |
                            v
                    FailureDiagnoser (COMP-06)
                            |
                            v
                      Recomposer (COMP-07)

  ClassificationAssigner (COMP-12) -- standalone, called by ContextScope layer
```

### 3.2 Build Order (respecting dependencies)

**Phase A (Independent, parallelizable)**:

1. `ClassificationAssigner` (COMP-12) -- standalone
2. `CapabilityMatcher` (COMP-13) -- standalone
3. `FailureDiagnoser` (COMP-06) -- standalone
4. `DelegationProtocol` (COMP-08) -- depends only on SDK types

**Phase B (depends on Phase A)**: 5. `TaskDecomposer` (COMP-01) -- standalone inputs 6. `AgentDesigner` (COMP-03) -- depends on CapabilityMatcher 7. `ClarificationProtocol` (COMP-09) -- depends on DelegationProtocol patterns 8. `EscalationProtocol` (COMP-10) -- depends on FailureDiagnoser 9. `CompletionProtocol` (COMP-11) -- depends on SDK types

**Phase C (depends on Phase B)**: 10. `EnvelopeAllocator` (COMP-04) -- depends on TaskDecomposer output shape 11. `PlanComposer` (COMP-02) -- depends on TaskDecomposer + AgentDesigner + EnvelopeAllocator 12. `Recomposer` (COMP-07) -- depends on FailureDiagnoser

**Phase D (integration)**: 13. `PlanEvaluator` (COMP-05) -- depends on PlanComposer 14. `PlanGenerationPipeline` -- composes COMP-01 through COMP-05 15. `FailureRecoveryPipeline` -- composes COMP-06 + COMP-07 16. `CommunicationManager` -- composes COMP-08 through COMP-11

### 3.3 External Dependencies

| Dependency                                                                                             | Used By                            | Nature                |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------- | --------------------- |
| `kaizen.l3.plan` (Plan, PlanNode, PlanEdge, PlanValidator, PlanExecutor, PlanModification)             | COMP-02, COMP-05, COMP-06, COMP-07 | Direct import         |
| `kaizen.l3.envelope` (EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer, AllocationRequest, Verdict) | COMP-04, COMP-08, COMP-11          | Direct import         |
| `kaizen.l3.messaging` (MessageRouter, MessageChannel, DelegationPayload, etc.)                         | COMP-08 through COMP-11            | Direct import         |
| `kaizen.l3.factory` (AgentFactory, AgentSpec, AgentInstance)                                           | COMP-03, COMP-08                   | Direct import         |
| `kaizen.l3.context` (ContextScope, ScopeProjection, DataClassification, ContextValue)                  | COMP-11, COMP-12                   | Direct import         |
| `kaizen.signatures` (Signature, InputField, OutputField)                                               | All components                     | Signature definitions |
| `kaizen.llm` (LLMRouter, FallbackRouter)                                                               | All components                     | LLM call abstraction  |

---

## 4. Architecture Decisions (ADR Candidates)

### ADR-KA-01: Package Structure -- Subpackage vs. Separate PyPI Package

**Context**: Should `kaizen-agents` be a separate PyPI package (`pip install kaizen-agents`) or a subpackage within `kailash-kaizen`?

**Option A: Separate PyPI Package**

- Pros: Independent versioning, separate install, clear dependency direction (kaizen-agents depends on kailash-kaizen, not vice versa)
- Cons: Another package to publish, version coordinate, test matrix

**Option B: Subpackage within kailash-kaizen (e.g., `kaizen.agents.l3` or `kaizen.orchestration.l3`)**

- Pros: Single install, shared test infrastructure, no version coordination
- Cons: Forces all kaizen users to install LLM-dependent code even if they only need L3 primitives

**Option C: Extra dependency in kailash-kaizen (e.g., `pip install kailash-kaizen[agents]`)**

- Pros: Single package name, optional install, clear "this needs LLM" boundary
- Cons: Still same version, extras can be confusing

**Recommendation**: **Option A (separate package)**. The LLM dependency boundary is a fundamental architectural divide. L3 primitives are deterministic; kaizen-agents is non-deterministic. Users who only need the SDK primitives should not pull in LLM provider dependencies. The dependency is strictly one-directional: `kaizen-agents -> kailash-kaizen`.

---

### ADR-KA-02: Component Implementation Pattern -- Signature vs. Standalone Functions

**Context**: Should each component be a Kaizen Signature class, a standalone async function, or a class with methods?

**Option A: Kaizen Signatures (class-based, declarative I/O)**

```python
class TaskDecomposerSignature(Signature):
    """Break objective into subtasks."""
    objective: str = InputField(desc="The goal to decompose")
    context: dict = InputField(desc="Available context")
    subtasks: list = OutputField(desc="List of atomic subtasks")
```

- Pros: Leverages existing signature compilation, auto-optimization hooks, structured I/O
- Cons: Signatures are designed for single LLM calls; some components need multi-step logic

**Option B: Async functions**

```python
async def decompose_task(objective: str, context: dict, ...) -> list[Subtask]:
    ...
```

- Pros: Simple, composable, easy to test
- Cons: No structured I/O metadata, no auto-optimization, no signature composition

**Option C: Protocol-implementing classes with internal signatures**

```python
class TaskDecomposer:
    _signature = TaskDecomposerSignature  # internal
    async def execute(self, objective, context, ...) -> list[Subtask]:
        # Multi-step logic, may invoke _signature multiple times
        ...
```

- Pros: Class encapsulates multi-step logic; internal signatures get optimization; Protocol enforces interface
- Cons: More boilerplate than pure functions

**Recommendation**: **Option C (Protocol classes with internal signatures)**. Components like Recomposer need multi-step logic (diagnose, generate modifications, validate). Pure signatures cannot express this. Internal signatures enable optimization on individual LLM calls while the class orchestrates the multi-step flow.

---

### ADR-KA-03: LLM Abstraction -- Provider Agnostic Call Interface

**Context**: How should components make LLM calls? Direct provider APIs, Kaizen's existing routing, or a new abstraction?

**Option A: Use Kaizen's existing `LLMRouter` / `FallbackRouter`**

- Pros: Already exists, handles model selection, fallback chains, cost tracking
- Cons: Routing is designed for agent-level model selection, not per-component calls

**Option B: New `LLMClient` protocol for components**

```python
class LLMClient(Protocol):
    async def complete(self, messages: list[dict], **kwargs) -> LLMResponse: ...
    async def complete_structured(self, messages: list[dict], output_schema: type, **kwargs) -> Any: ...
```

- Pros: Simple, testable (mock with deterministic responses for tests), provider-agnostic
- Cons: Another abstraction layer

**Option C: Direct Signature execution**

- Each component defines a Signature and uses the existing Signature execution pipeline which already abstracts LLM calls
- Pros: No new abstraction, leverages existing infrastructure
- Cons: Signature execution may not support all needed patterns (e.g., multi-turn, structured output)

**Recommendation**: **Option B with adapter to existing Kaizen LLM infrastructure**. Define a minimal `LLMClient` protocol. Provide a default adapter that delegates to Kaizen's `LLMRouter`. This gives clean testability (inject deterministic LLMClient for tests) while reusing existing LLM infrastructure in production. The protocol has two methods: `complete` (freeform) and `complete_structured` (returns parsed structured output -- essential for components that produce typed dataclasses).

---

### ADR-KA-04: Classification Integration -- Inline vs. Async Background

**Context**: How should ClassificationAssigner integrate with ContextScope writes?

**Option A: Synchronous inline (classify before every write)**

- Pros: Every value is classified before storage; no unclassified data
- Cons: LLM latency on every context write; may be prohibitively slow

**Option B: Async background (write with default, reclassify async)**

- Pros: Low latency writes; classification happens in background
- Cons: Window where data has incorrect classification; requires re-check on read

**Option C: Policy-based (classify on first write per key pattern, cache, apply to subsequent)**

- Pros: Amortized cost; patterns like "financial.\*" are always CONFIDENTIAL
- Cons: May miss context-dependent classification

**Recommendation**: **Option C (policy-based with LLM fallback)**. Define classification policies by key pattern (regex/glob). Most keys have deterministic classification based on naming convention. LLM is invoked only for keys that match no policy. Cache LLM results per key. This keeps the hot path fast while using LLM for genuinely ambiguous cases.

---

### ADR-KA-05: Structured Output Enforcement

**Context**: LLM outputs must be parsed into typed dataclasses (Subtask, PlanEvaluation, FailureDiagnosis, etc.). How to enforce structure?

**Option A: JSON mode + Pydantic validation**

- Pros: Most LLM providers support JSON mode; Pydantic already in Kaizen deps
- Cons: LLM may produce invalid JSON; retry overhead

**Option B: Function calling / tool_use**

- Pros: Strongest structural guarantees from providers; less parsing
- Cons: Provider-specific, not all providers support it

**Option C: Kaizen Signature structured execution + retry with repair**

- Pros: Provider-agnostic; retry with error feedback; already exists in Signature system
- Cons: May need extension for complex nested structures

**Recommendation**: **Option C with Option A fallback**. Use Kaizen Signature execution with structured output parsing. If parsing fails, use Pydantic validation error messages as feedback to re-prompt the LLM (up to `max_retries`). This keeps provider-agnosticism while ensuring structural correctness.

---

## 5. Acceptance Criteria

### Per-Component Minimum Criteria

| Component                  | Test Type            | Criteria                                              | Measurement                                                          |
| -------------------------- | -------------------- | ----------------------------------------------------- | -------------------------------------------------------------------- |
| **TaskDecomposer**         | Unit (mock LLM)      | Produces valid Subtask list from objective            | subtask_count >= 1, no circular deps, sum(cost) <= budget            |
| **PlanComposer**           | Unit (mock LLM)      | Produces Plan that passes PlanValidator               | `PlanValidator.validate()` returns zero errors                       |
| **AgentDesigner**          | Unit (mock LLM)      | Produces AgentSpec with valid tool subset             | `tool_ids <= available_tools`, non-empty spec_id                     |
| **EnvelopeAllocator**      | Unit (deterministic) | Produces AllocationRequests within budget             | `sum(financial_ratio) + reserve <= 1.0`, all finite                  |
| **PlanEvaluator**          | Unit (mock LLM)      | Produces evaluation with score in [0,1]               | `0 <= score <= 1`, issues non-empty when score < threshold           |
| **FailureDiagnoser**       | Unit (mock LLM)      | Produces FailureDiagnosis with root cause             | root_cause non-empty, affected_downstream computed deterministically |
| **Recomposer**             | Unit (mock LLM)      | Produces PlanModifications that maintain DAG validity | `PlanValidator.validate()` passes after `apply_modifications()`      |
| **DelegationProtocol**     | Unit                 | Produces valid MessageEnvelope with DelegationPayload | MessageRouter.route() succeeds                                       |
| **ClarificationProtocol**  | Unit                 | Handles blocking question/response cycle              | correlation_id matches, response delivered                           |
| **EscalationProtocol**     | Unit (mock LLM)      | Routes to recovery pipeline on BLOCKED severity       | FailureDiagnoser invoked, modifications produced                     |
| **CompletionProtocol**     | Unit                 | Triggers merge + reclamation on success               | MergeResult produced, budget reclaimed                               |
| **ClassificationAssigner** | Unit (mock LLM)      | Returns valid DataClassification                      | classification in C0-C4, monotonic within session                    |
| **CapabilityMatcher**      | Unit                 | Exact match scores 1.0, semantic match uses LLM       | matches ranked by score, filtered by threshold                       |

### Integration Criteria

| Test                        | Description                                     | Criteria                                                    |
| --------------------------- | ----------------------------------------------- | ----------------------------------------------------------- |
| **E2E Plan Generation**     | Objective -> validated Plan                     | Plan passes all PlanValidator checks                        |
| **E2E Delegation Chain**    | Parent spawns child, delegates, collects result | Full delegation flow completes (steps 1-11 from flow doc)   |
| **E2E Failure Recovery**    | Node fails, plan recomposes and completes       | Plan reaches COMPLETED state after recomposition            |
| **E2E Budget Conservation** | Budget tracking through delegation chain        | `sum(child_consumed) + reserve == parent_allocated`         |
| **E2E Classification Flow** | Data classified before context storage          | All values in ScopedContext have appropriate classification |

### Non-Functional Criteria

| Requirement                  | Target                               | Measurement                                           |
| ---------------------------- | ------------------------------------ | ----------------------------------------------------- |
| Plan generation latency      | < 30s for 10-node plan               | Wall clock time                                       |
| Single LLM component latency | < 5s excluding LLM call              | Component overhead only                               |
| Memory per plan              | < 50MB                               | Peak RSS during plan execution                        |
| Concurrent plans             | 10+ plans simultaneously             | No deadlocks, correct budget isolation                |
| LLM failure tolerance        | Graceful degradation                 | All components handle LLM timeout/error without panic |
| Provider agnosticism         | Works with OpenAI, Anthropic, Google | Test matrix with all three providers                  |

---

## 6. Risk Assessment

### Critical (High Probability, High Impact)

1. **LLM structural output failures**
   - Risk: LLM produces malformed JSON or invalid types, breaking typed dataclass parsing
   - Mitigation: Structured output enforcement (ADR-KA-05) with retry + error feedback
   - Prevention: Use Kaizen Signature execution with Pydantic validation on all outputs

2. **Budget conservation violation**
   - Risk: LLM-estimated costs are wildly inaccurate, leading to over-allocation
   - Mitigation: EnvelopeSplitter enforces ratio sums <= 1.0; EnvelopeTracker catches at runtime
   - Prevention: Double-check: kaizen-agents pre-validates, SDK validates definitively

3. **Plan cycle introduction by Recomposer**
   - Risk: LLM-generated PlanModifications create cycles in the DAG
   - Mitigation: `PlanValidator.validate_structure()` after every `apply_modifications()`
   - Prevention: Recomposer validates modifications against current graph before returning

### Medium Risk (Monitor)

4. **LLM latency compounding**
   - Risk: Plan generation requires 5+ sequential LLM calls, total latency > 60s
   - Mitigation: Parallelize AgentDesigner calls (one per subtask); cache CapabilityMatcher results
   - Prevention: Benchmark pipeline latency; set timeouts per component

5. **Monotonic tightening violation by AgentDesigner**
   - Risk: LLM designs AgentSpec with wider envelope than parent
   - Mitigation: Clamp to parent envelope before returning; AgentFactory.spawn() validates definitively
   - Prevention: Include parent envelope in LLM prompt as hard constraint

6. **Classification drift**
   - Risk: ClassificationAssigner assigns different levels to semantically identical data across runs
   - Mitigation: Policy-based deterministic classification for common patterns
   - Prevention: Cache + log classifications; flag inconsistencies

### Low Risk (Accept)

7. **Provider-specific structured output differences**
   - Risk: Structured output parsing works on OpenAI but fails on Anthropic
   - Mitigation: LLMClient adapter normalizes output
   - Acceptance: Test matrix across providers

8. **Dead letter accumulation**
   - Risk: DeadLetterStore fills during complex plans
   - Mitigation: DeadLetterStore already has bounded capacity (maxlen)
   - Acceptance: Monitor, alert at 80% capacity

---

## 7. Implementation Roadmap

### Phase A: Foundations (1 autonomous session)

- Package structure and build configuration
- `LLMClient` protocol + adapter to existing Kaizen LLM infrastructure
- `ComponentResult` wrapper
- `Subtask`, `PlanEvaluation`, `FailureDiagnosis` dataclass definitions
- ClassificationAssigner (COMP-12) -- standalone, immediate value
- CapabilityMatcher (COMP-13) -- standalone, immediate value

### Phase B: Plan Generation (2 autonomous sessions, parallelizable)

- Track 1: TaskDecomposer (COMP-01) + AgentDesigner (COMP-03) + EnvelopeAllocator (COMP-04)
- Track 2: PlanComposer (COMP-02) + PlanEvaluator (COMP-05)
- PlanGenerationPipeline integration + E2E test

### Phase C: Communication Protocols (1 autonomous session)

- DelegationProtocol (COMP-08)
- ClarificationProtocol (COMP-09)
- EscalationProtocol (COMP-10)
- CompletionProtocol (COMP-11)
- CommunicationManager integration

### Phase D: Failure Recovery (1 autonomous session)

- FailureDiagnoser (COMP-06)
- Recomposer (COMP-07)
- FailureRecoveryPipeline integration
- E2E failure-and-recovery test

### Phase E: Integration + Polish (1-2 autonomous sessions)

- Full E2E: objective -> plan -> execute -> delegate -> complete
- Budget conservation tests
- Provider matrix tests (OpenAI, Anthropic, Google)
- Performance benchmarks
- Documentation

---

## Key Files Referenced

- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/__init__.py` -- L3 public API surface
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/plan/types.py` -- Plan, PlanNode, PlanEdge, PlanModification, PlanEvent
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/envelope/types.py` -- AllocationRequest, Verdict, GradientZone, BudgetRemaining
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/messaging/types.py` -- MessageEnvelope, DelegationPayload, ClarificationPayload, etc.
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/factory/spec.py` -- AgentSpec
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/factory/factory.py` -- AgentFactory
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/context/types.py` -- DataClassification, ContextValue, MergeResult
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/context/scope.py` -- ContextScope
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/plan/executor.py` -- PlanExecutor, NodeCallback
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/plan/validator.py` -- PlanValidator
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/envelope/splitter.py` -- EnvelopeSplitter
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/envelope/enforcer.py` -- EnvelopeEnforcer
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/l3/messaging/router.py` -- MessageRouter
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/signatures/__init__.py` -- Signature, InputField, OutputField
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/llm/__init__.py` -- LLMRouter, FallbackRouter
- `/Users/esperie/repos/kailash/kailash-py/packages/kailash-kaizen/src/kaizen/agent.py` -- Unified Agent API
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-l3/03-user-flows/01-delegation-flow.md` -- Full delegation chain flow
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-l3/03-user-flows/02-plan-execution-flow.md` -- Plan execution lifecycle
- `/Users/esperie/repos/kailash/kailash-py/workspaces/kaizen-l3/02-plans/02-architecture-decisions.md` -- L3 architecture decisions
