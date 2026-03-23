# Architecture Decisions

## AD-L3-01: L3 Module Location

**Decision**: Place all L3 primitives under `packages/kailash-kaizen/src/kaizen/l3/`

**Rationale**: L3 primitives belong in the Kaizen package (agent framework), not in trust-plane or PACT. They consume PACT governance types but are agent-framework features. Separate `l3/` namespace keeps them cleanly isolated from L0-L2 code while living in the same package.

**Alternatives Rejected**:

- `packages/kailash-l3/` (separate package): Adds deployment complexity with no benefit. L3 is part of Kaizen.
- `src/kailash/trust/l3/` (trust-plane): L3 is agent lifecycle, not trust infrastructure. Wrong layer.
- Mixed into existing modules: Would tangle L0-L2 code with L3, making both harder to maintain.

## AD-L3-02: GradientZone as str-backed Enum

**Decision**: Define `GradientZone` as a Python `str` enum for L3 types.

```python
class GradientZone(str, Enum):
    AUTO_APPROVED = "auto_approved"
    FLAGGED = "flagged"
    HELD = "held"
    BLOCKED = "blocked"
```

**Rationale**: Existing PACT code uses string-based levels. A str-backed enum provides type safety while maintaining string compatibility. Can compare directly with existing string values. Follows EATP SDK convention of str-backed enums for JSON-friendly serialization.

## AD-L3-03: asyncio.Queue for MessageChannel

**Decision**: Use `asyncio.Queue` (bounded) as the internal transport for `MessageChannel`.

**Rationale**: Python's `asyncio.Queue(maxsize=capacity)` provides exactly the bounded, async-safe channel semantics the spec requires. `put()` blocks when full (backpressure). `get()` blocks when empty. Queue operations are coroutine-safe without additional locking. Thread-safe operation can be added via `janus.Queue` if needed for mixed sync/async.

**Alternatives Rejected**:

- `queue.Queue` (threading): L3 agents are async-first. Threading queue would require adapter layer.
- Custom ring buffer: Unnecessary when asyncio.Queue provides all required semantics.

## AD-L3-04: threading.Lock for Shared State

**Decision**: Use `threading.Lock` (not `asyncio.Lock`) for `EnvelopeTracker` and `AgentInstanceRegistry` shared state.

**Rationale**: These structures may be accessed from both sync and async contexts. `threading.Lock` works in both; `asyncio.Lock` only works in async contexts. The GIL plus `threading.Lock` provides sufficient atomicity for Python. Lock granularity: one lock per tracker/registry instance, not global.

## AD-L3-05: Conformance Test Vectors as Parameterized Tests

**Decision**: Implement all 47 spec conformance test vectors as parameterized pytest tests, one test file per spec.

**Rationale**: Each spec provides JSON test vectors with setup/action/expected. `@pytest.mark.parametrize` maps directly to this structure. Single test function per invariant, parameterized across vectors. Ensures cross-SDK alignment: both Python and Rust run identical test vectors.

## AD-L3-06: ScopedContext Uses fnmatch for Glob Patterns

**Decision**: Use Python's `fnmatch` module for ScopeProjection glob pattern matching.

**Rationale**: The spec defines glob patterns with `*` and `**`. Python's `fnmatch.fnmatch()` handles `*` natively. For `**` (match including dots), we translate to regex. This is simpler and more maintainable than a custom glob engine.

**Extension**: For dot-separated key hierarchies like `project.config.debug`, treat `.` as a path separator. `*` matches one segment, `**` matches any number of segments.

## AD-L3-07: EATP Record Creation via Event System

**Decision**: L3 primitives emit governance events (not create EATP records directly). The existing audit hook system translates events to EATP records.

**Rationale**: Direct EATP record creation from L3 code would couple primitives to the trust-plane storage layer. Instead, L3 emits structured events (e.g., `SpawnEvent`, `TerminateEvent`, `BudgetConsumedEvent`) and the existing audit hook infrastructure translates them to EATP records. This keeps L3 primitives testable in isolation.

## AD-L3-08: Plan DAG Uses Existing dag_validator for Cycle Detection

**Decision**: PlanValidator reuses the topological sort and cycle detection from `kaizen/composition/dag_validator.py`.

**Rationale**: The existing DAG validator implements Kahn's algorithm with cycle detection. PlanValidator adds envelope and resource validation on top. No need to reimplement graph algorithms.

**Prerequisite**: P5 (make topological_sort public/reusable).

**Note**: Existing implementation uses DFS 3-color marking, not Kahn's algorithm. Same result, different approach.

---

## Red Team Amendments (from 04-validate/01-redteam-report.md)

### AD-L3-02-AMENDED: Reuse VerificationLevel, Don't Create GradientZone (F-04)

**Revised Decision**: Reuse existing `VerificationLevel` from `pact/governance/config.py` instead of creating a new `GradientZone` enum. Import as alias if naming clarity is needed:

```python
from pact.governance.config import VerificationLevel as GradientZone
```

**Rationale**: Red team finding F-04 identified that `VerificationLevel` already has the same 4 values. Creating a parallel enum adds conversion burden with no benefit.

### AD-L3-04-AMENDED: asyncio.Lock for Async Paths (F-15)

**Revised Decision**: Use `asyncio.Lock` (not `threading.Lock`) for `EnvelopeTracker`, `AgentInstanceRegistry`, and `AgentFactory` — all of which are called from async code paths (PlanExecutor, message handlers).

**Rationale**: Red team finding F-15 identified that `threading.Lock.acquire()` blocks the entire asyncio event loop, not just the calling coroutine. Since L3 primitives are predominantly async (PlanExecutor, MessageRouter), `asyncio.Lock` is the correct choice. For the rare sync access path (test helpers, CLI tools), provide sync wrappers that run the async lock in a new event loop.

### AD-L3-09: Verdict-to-GradientZone Mapping (F-01)

**Decision**: PlanExecutor receives `Verdict` from EnvelopeTracker and extracts the zone:

```python
def _verdict_to_zone(verdict: Verdict) -> GradientZone:
    if verdict.type == "APPROVED":
        return verdict.zone  # AUTO_APPROVED or FLAGGED
    elif verdict.type == "HELD":
        return GradientZone.HELD
    elif verdict.type == "BLOCKED":
        return GradientZone.BLOCKED
```

**Rationale**: Red team finding F-01 (CRITICAL) identified that Spec 01 returns `Verdict` but Spec 05 expects `GradientZone`. The mapping is explicit and deterministic.

### AD-L3-10: Spawn-Blocked During Cascade Termination (F-07)

**Decision**: AgentFactory holds the parent's lock during cascade termination. Spawn requests for any descendant of the terminating agent are queued until cascade completes.

**Rationale**: Red team finding F-07 (CRITICAL) identified that a child could spawn a grandchild between descendant collection and termination iteration, causing the grandchild to be missed.

### AD-L3-11: WaitReason Extended with ClarificationPending (F-03)

**Decision**: Add `ClarificationPending { message_id: UUID }` and `EscalationPending` to the WaitReason enum.

**Rationale**: Red team finding F-03 identified that Spec 03's messaging flow creates waiting states that Spec 04's WaitReason doesn't cover.

### AD-L3-12: Spawn + Channel Creation Atomic (F-17)

**Decision**: `AgentFactory.spawn()` internally calls `MessageRouter.create_channel()`. If channel creation fails, spawn is rolled back (instance deregistered, budget reclaimed).

**Rationale**: Red team finding F-17 identified that non-atomic spawn + channel leaves orphaned instances.

### AD-L3-13: ScopeProjection Custom Matcher (F-16)

**Decision**: Implement custom dot-separated segment matcher instead of raw `fnmatch`. Split keys on `.`, match `*` per segment, `**` across segments.

**Rationale**: Red team finding F-16 identified that Python's `fnmatch` treats `*` as matching dots, which violates the spec's semantics.

### AD-L3-14: Gradient Rule G10 for Spawn Failure (F-18)

**Decision**: Add gradient rule G10 to PlanExecutor:

- `SpawnFailure (budget)` → Held (orchestration can reallocate)
- `SpawnFailure (structural)` → Blocked (ToolNotInParent, MaxDepthExceeded)

**Rationale**: Red team finding F-18 identified that G1-G9 don't cover the case where spawning itself fails.

### AD-L3-15: Value Types vs Entity Types (F-20)

**Decision**: Use `@dataclass(frozen=True)` for value types (AgentSpec, PlanGradient, CostEntry, ContextValue, ScopeProjection). Use `@dataclass` (mutable) for entity types (AgentInstance, EnvelopeTracker, ContextScope, Plan). Entity types are always behind a lock.

**Rationale**: Red team finding F-20 identified the tension between EATP's `frozen=True` convention and mutable lifecycle state.
