# Risk Assessment — L3 Autonomy Primitives

## Critical Risks

### R1: Thread Safety in Budget Operations (HIGH)

**Risk**: EnvelopeTracker's `record_consumption()` and `allocate_to_child()` require atomic operations. Concurrent spawns from the same parent can race on budget deduction, causing over-allocation.

**Impact**: Two children spawned concurrently could each be allocated the parent's full remaining budget, violating INV-2 (split conservation).

**Mitigation**:

- Use `threading.Lock` per tracker instance for all mutation operations
- `record_consumption()` must check-and-record atomically (no TOCTOU gap)
- `can_afford()` is advisory only; `record_consumption()` is authoritative
- AgentFactory serializes spawn operations per parent (spec Section 8.5)

### R2: Cascade Termination Ordering (MEDIUM-HIGH)

**Risk**: Cascade termination must be depth-first, leaves-first. If termination proceeds parent-before-children, budget reclamation is lost (child's tracker is gone before reclamation happens).

**Impact**: Budget leak — unused child budget is never returned to parent, reducing effective authority of the delegation hierarchy.

**Mitigation**:

- `all_descendants()` traversal with depth sorting (deepest first)
- Each descendant reclaims to its direct parent before parent is terminated
- Idempotent termination (spec Section 8.3): re-termination is a no-op

### R3: NaN/Inf Poisoning Across Boundaries (HIGH)

**Risk**: NaN or Inf entering budget calculations permanently poisons the accumulator (`NaN += X` is always NaN). Every subsequent budget check silently passes.

**Impact**: Complete bypass of budget enforcement for the poisoned tracker.

**Mitigation**:

- `math.isfinite()` on every input boundary (constructor, method params)
- Already established pattern in PACT (`_validate_finite()` in envelopes.py)
- Reject NaN/Inf before any arithmetic
- Per trust-plane-security.md Rule 3: mandatory on all numeric constraint fields

### R4: Plan Modification During Execution (MEDIUM)

**Risk**: Hot modifications to a running plan (AddNode, RemoveNode, etc.) while agents are active. Must serialize with ongoing execution, re-validate invariants, and protect running nodes.

**Impact**: Race between modification and node completion could lead to inconsistent plan state.

**Mitigation**:

- Serialized modification (mutex on plan state)
- Running-node protection (INV-PLAN-15): Remove/Replace on running node → Held
- Batch atomicity (INV-PLAN-14): all modifications in batch succeed or none
- Re-validation after every modification

### R5: Context Scope Parent Traversal Performance (LOW-MEDIUM)

**Risk**: Deeply nested scope chains (Root → A → B → C → D) create long traversal paths on every `get()` call. Performance degrades linearly with depth.

**Impact**: Latency increase for deeply nested delegation hierarchies.

**Mitigation**:

- `snapshot()` materializes the full view, avoiding repeated traversal
- Optional caching with invalidation (spec Section 8.6)
- Practical depth limits via `max_depth` on AgentSpec
- Most agent hierarchies are 3-5 levels deep, not hundreds

### R6: Dead Letter Store Capacity Under Load (LOW)

**Risk**: Under high message throughput with many terminations, the DeadLetterStore fills rapidly and evicts entries before they can be inspected.

**Impact**: Loss of diagnostic information for message routing failures.

**Mitigation**:

- Ring buffer with configurable capacity (default adequate for most deployments)
- EATP audit anchors are created independently of DeadLetterStore — the governance audit trail is always complete
- `drain_for()` allows targeted retrieval before eviction
- Monitoring on dead letter rate

### R7: Cross-Primitive Integration Complexity (MEDIUM)

**Risk**: Five primitives with deep cross-references (Factory uses Router for channels, Router uses Enforcer for validation, Executor uses Factory for spawning, etc.). Integration bugs are likely.

**Impact**: Subtle state inconsistencies between primitives.

**Mitigation**:

- Clear ownership boundaries per spec
- Each primitive is independently testable with conformance vectors
- Tier 2 integration tests exercise cross-primitive wiring
- Tier 3 E2E tests validate full delegation chains

### R8: GradientZone String vs Enum Alignment (LOW)

**Risk**: Existing Python PACT uses string-based levels ("auto_approved") while specs define enum-based `GradientZone`. Mixing conventions creates brittle comparisons.

**Impact**: Comparison bugs (`"flagged" != GradientZone.FLAGGED`).

**Mitigation**:

- Define `GradientZone` as str-backed enum (per EATP SDK conventions)
- Provide mapping from existing string levels
- Single source of truth for zone comparison

## Non-Risks (Explicitly Called Out)

| Concern                                          | Why It's Not a Risk                                                                           |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Python GIL prevents true concurrent budget races | GIL applies to CPU-bound only; async code needs explicit locking regardless                   |
| Existing PACT tests cover envelope algebra       | True, but L3 extends use (splitting, continuous tracking). New tests needed.                  |
| ScopedContext replaces agent memory              | No — ScopedContext is task data flow; memory is LLM conversation history. Different concerns. |
| L3 primitives require LLM calls                  | No — all L3 primitives are deterministic. LLM decisions live in orchestration layer.          |
