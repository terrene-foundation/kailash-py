# L0-L2 Remediation Brief

**Status**: Active -- must be completed before L3 spec implementation begins
**Source**: L0-L2 Audit (`15-l0-l2-audit.md`) + architecture decisions D-AC1, DP-1 through DP-5
**Audience**: kailash-py team AND kailash-rs team (language-agnostic requirements)
**Date**: 2026-03-21

---

## How to Read This Brief

Items are grouped into two tiers:

- **BLOCKING** -- L3 primitives cannot be built until these are done. These are structural prerequisites.
- **PREPARATORY** -- L3 work can begin without these, but will hit friction or require rework if they are deferred. Complete before L3 reaches integration testing.

Each item specifies what to change, why it matters for L3, and how to verify the change is correct. Implementation details are deliberately omitted -- each team chooses the right approach for their language and codebase.

Where the two codebases differ today, the divergence is noted so each team knows their starting point.

---

## BLOCKING Items

These must be completed and released before any L3 spec implementation begins.

---

### B1: Add Optional Constraint Envelope to AgentConfig

**Decision**: D-AC1 -- envelope goes at SDK level, not L3 level.

**What to change**: Add an optional `envelope` field to `AgentConfig`. The field holds a reference to a `ConstraintEnvelope` (or its identifier). When absent, behavior is unchanged from today. When present, downstream systems (TAOD runner, tool executor, delegation) can read the envelope to enforce constraints.

**Why (L3 dependency)**: Every L3 primitive -- AgentInstance, AgentFactory, PlanExecutor, GovernedTaodRunner -- needs to know which envelope governs an agent. If the envelope is not on AgentConfig, L3 must invent a parallel configuration path, creating two sources of truth for agent configuration.

**Current state**:

- Rust: `AgentConfig` is `Serialize + Deserialize` with no envelope field. Adding an optional field with a default is non-breaking for deserialization (existing serialized configs deserialize with the field absent).
- Python: `AgentConfig` / `BaseAgentConfig` similarly has no envelope field. Adding an optional field with `None` default is non-breaking.

**Acceptance criteria**:

1. `AgentConfig` has an optional envelope field that defaults to absent/None
2. Existing code that constructs `AgentConfig` without an envelope continues to compile and run without modification
3. An agent constructed with an envelope can be queried for that envelope at runtime
4. Serialization round-trip works: config with envelope serializes and deserializes correctly; config without envelope deserializes from old format without error
5. Unit test demonstrates both paths (with and without envelope)

---

### B2: Harmonize Checkpoint Data Model Across Languages

**Decision**: DP-1 -- harmonize Rust AgentCheckpoint with Python AgentState BEFORE L3.

**What to change**: Bring the checkpoint/state data model to parity across both implementations. The target is a shared set of fields that both languages support, so that L3 checkpoint logic (plan-level checkpointing, cascading checkpoint across child agents, partial resume) can be designed once against a single data model.

**Why (L3 dependency)**: L3 plan-level checkpointing requires saving and restoring plan DAG state, per-node envelope consumption, child agent instance states, and message queue snapshots. If the checkpoint model is too minimal (Rust) or too divergent (different field names and semantics), L3 checkpoint specs cannot target a single contract.

**Current state**:

- Rust `AgentCheckpoint`: 8 fields -- `checkpoint_id`, `agent_name`, `model`, `conversation`, `memory_snapshot`, `tool_state`, `metadata`, plus timestamps. No structured fields for pending actions, completed actions, active specialists, workflow state, parent checkpoint reference, or hook event history.
- Python `AgentState`: 15+ fields -- includes `pending_actions`, `completed_actions`, `active_specialists`, `workflow_state`, `parent_checkpoint_id` (for forking), `hook_event_history`, control state, permission state. Significantly richer.

**Target parity set** (minimum fields both must support):

- `checkpoint_id` (unique identifier)
- `agent_name`
- `model`
- `conversation` (turn history)
- `memory_snapshot` (serialized memory state)
- `tool_state` (serialized tool state)
- `parent_checkpoint_id` (enables forking and lineage tracking)
- `pending_actions` (list of actions not yet executed)
- `completed_actions` (list of actions finished)
- `workflow_state` (serialized workflow/plan state -- opaque to checkpoint system, structured by consumer)
- `metadata` (extensible key-value for fields not yet in the schema)
- `created_at` / `updated_at` timestamps

Python may retain additional fields beyond this set. Rust must gain the fields it currently lacks.

**Acceptance criteria**:

1. Both implementations support the target parity field set
2. All new fields are optional with sensible defaults (empty list, None/null, empty map) so existing checkpoint data deserializes without error
3. `CheckpointStorage` trait/interface (`save`/`load`/`list`/`delete`) works unchanged -- only the data model expands
4. A checkpoint created with `parent_checkpoint_id` set can be loaded and the parent reference is preserved
5. Round-trip test: create checkpoint with all parity fields populated, save, load, verify all fields match
6. Migration test: load a checkpoint saved by the CURRENT version (before this change), verify it deserializes with new optional fields absent/default

---

### B3: Add ContextScope to the SDK

**Decision**: DP-2 -- ContextScope is an SDK primitive, not an orchestration-layer concern.

**What to change**: Introduce a `ContextScope` type that wraps any memory implementation with projection-based access control. A ContextScope provides a filtered, hierarchical view of a flat memory store. A parent scope can create child scopes with tighter visibility (monotonic tightening -- children never see more than their parent).

**Why (L3 dependency)**: L3 agent delegation requires scoped context. When a parent agent delegates to a child, the child must receive a restricted view of memory -- it should not see deployment credentials when it is doing code review. Without ContextScope in the SDK, every L3 primitive that delegates (AgentFactory, PlanExecutor, AutonomousSupervisor) must independently invent scoping, leading to inconsistent enforcement.

**Current state**:

- Rust: `SharedMemory` is a flat `HashMap` behind `RwLock`. No scoping, no filtering, no access control. The `AgentMemory` trait has 5 flat methods (`store`, `retrieve`, `remove`, `keys`, `clear`).
- Python: `SharedMemoryPool` is a flat list with tag-based filtering (by tags, importance, segment, agent_id). Richer than Rust but still not hierarchical -- filtering is query-based, not enforcement-based.

**Behavioral requirements**:

- ContextScope wraps an existing memory implementation (does not replace it)
- A scope is defined by a projection: a set of rules determining which keys are visible (read) and which namespace writes go to
- Child scopes can be derived from parent scopes; child visibility is always a subset of parent visibility
- The underlying flat memory store does not change -- ContextScope is a lens over it
- The existing `AgentMemory` trait / interface is NOT modified

**Acceptance criteria**:

1. `ContextScope` can be created from any memory implementation
2. A root scope with full visibility behaves identically to the underlying memory
3. A child scope with restricted visibility cannot read keys outside its projection
4. A child scope's writes are namespaced (do not collide with parent or sibling writes)
5. Monotonic tightening: a child scope derived from a parent scope cannot have broader visibility than the parent
6. The existing `AgentMemory` trait/interface has zero changes
7. Existing code using `SharedMemory` / `SharedMemoryPool` directly continues to work without modification
8. Unit tests for: root scope full access, child restricted read, child namespaced write, grandchild further restricted, attempt to widen child scope fails

---

### B4: Extend MessageType Enum with L3 Variants

**Decision**: DP-3 -- extend the existing enum (do not create a parallel enum). Add forward-compatibility annotation first.

**What to change**: Two-step change:

**Step 1** (can ship independently): Mark the `MessageType` enum as forward-compatible so that adding variants in the future is not a breaking change for consumers.

- Rust: add `#[non_exhaustive]` attribute
- Python: document that consumers must handle unknown variants (use a default/fallback arm)

**Step 2** (ship together or after Step 1): Add the following variants to `MessageType`:

- `Delegation` -- parent requests child to perform a scoped task
- `DelegationResult` -- child returns result to parent
- `Escalation` -- child cannot complete, escalates to parent
- `SystemControl` -- lifecycle management (terminate, pause, resume, checkpoint)

**Why (L3 dependency)**: L3 inter-agent communication is typed delegation, not generic task requests. The current 6 variants (`TaskRequest`, `TaskResponse`, `StatusUpdate`, `CapabilityQuery`, `CapabilityResponse`, `Error`) cover discovery and basic request-response. L3 delegation chains, escalation protocols, and lifecycle management need distinct message types so that routing, logging, and enforcement can distinguish them without inspecting payloads.

**Current state**:

- Rust: `MessageType` has 6 variants, derives `Serialize`/`Deserialize`, is NOT marked `#[non_exhaustive]`
- Python: equivalent enum/type with similar variants

**Acceptance criteria**:

1. Forward-compatibility annotation is present (Rust: `#[non_exhaustive]`; Python: documented contract)
2. All four new variants exist and can be constructed
3. Existing code that handles the original 6 variants continues to compile/run (with a wildcard/default arm if exhaustive matching was used)
4. Serialization round-trip works for all new variants
5. `A2AMessage` can be constructed with any new variant and sent through `MessageBus` without error
6. Unit tests for construction, serialization, and bus transit of each new variant

---

### B5: Add AgentInstance Struct Alongside AgentCard

**Decision**: DP-5 -- separate struct, not extension of AgentCard.

**What to change**: Introduce an `AgentInstance` struct that represents a running agent. `AgentCard` remains the static capability description (what an agent CAN do). `AgentInstance` represents a live agent with runtime state (what an agent IS doing). An `AgentInstance` references an `AgentCard` for its capabilities and adds lifecycle state, envelope reference, parent lineage, and creation timestamp.

**Why (L3 dependency)**: L3 AgentFactory spawns agents at runtime. Each spawned agent needs lifecycle tracking (Pending, Running, Waiting, Completed, Failed, Terminated), parent reference (who spawned it), and envelope reference (what constraints govern it). Conflating this with AgentCard would mix static discovery data with dynamic runtime state, making the registry unreliable for discovery queries.

**Current state**:

- Rust: `AgentCard` has name, description, capabilities, schemas, endpoint, metadata. `AgentRegistry` maps name to `AgentCard`. No instance concept.
- Python: similar -- agent cards for discovery, no separate instance tracking.

**Behavioral requirements**:

- `AgentInstance` holds a reference to an `AgentCard` (not a copy)
- `AgentInstance` has a lifecycle state field with at minimum: Pending, Running, Waiting, Completed, Failed, Terminated
- `AgentInstance` has optional `parent_instance_id` for lineage tracking
- `AgentInstance` has optional envelope reference for constraint tracking
- `AgentInstance` has a unique instance ID distinct from the agent name (multiple instances of the same agent type can exist)
- State transitions are validated (cannot go from Completed back to Running)
- `AgentCard` is NOT modified (no new fields, no behavioral changes)

**Acceptance criteria**:

1. `AgentInstance` struct/class exists with: instance_id, agent_card reference, lifecycle_state, parent_instance_id (optional), envelope reference (optional), created_at
2. Lifecycle state enum exists with at minimum 6 states: Pending, Running, Waiting, Completed, Failed, Terminated
3. Invalid state transitions are rejected (return error or raise exception)
4. Multiple instances can reference the same AgentCard
5. AgentCard has zero changes from its current definition
6. Unit tests for: instance creation, valid state transitions, invalid state transition rejection, multiple instances per card

---

## PREPARATORY Items

These do not block L3 spec work but should be completed before L3 reaches integration testing. They remove friction, fix bugs, and prevent rework.

---

### P1: Mark All Public Enums as Forward-Compatible

**What to change**: Add forward-compatibility annotations to all public enums that will gain variants during L3 work.

Enums requiring this treatment:

- `OrchestrationStrategy` (will gain `PlanDriven`)
- `RoutingCondition` (will gain `CapabilityMatch`)
- `RoutingStrategy` (may gain new routing modes)
- `AgentEvent` (will gain lifecycle transition events, envelope violation events)

Note: `MessageType` is covered in B4 above.

**Why**: Without forward-compatibility, every new variant is a breaking change for any consumer doing exhaustive matching. The window to add this without breaking consumers is now -- before external adoption.

**Current state**:

- Rust: none of these enums are `#[non_exhaustive]`
- Python: enums are inherently extensible, but the contract should be documented

**Acceptance criteria**:

1. All listed enums have forward-compatibility annotations
2. Internal code that matches on these enums includes a wildcard/default arm
3. No existing tests break

---

### P2: Fix RoutingCondition::Regex

**What to change**: The `Regex` variant of `RoutingCondition` does not perform regex matching. It performs case-insensitive substring matching -- identical to `Contains`. Either implement actual regex matching or rename the variant to reflect its real behavior.

**Why**: Any consumer using `Regex` believing they get pattern matching will silently get wrong results. This is a correctness bug. L3 will add capability-based routing alongside existing variants; the existing variants must work correctly first.

**Current state**:

- Rust: confirmed in `multi_agent.rs` lines 76-81. Comment in code acknowledges this is a shortcut.
- Python: verify whether the same pattern exists.

**Acceptance criteria**:

1. `Regex` variant either performs actual regex matching OR is renamed to accurately describe its behavior
2. If regex is implemented: test with a pattern that matches via regex but would NOT match via substring (e.g., `^start` should match "start here" but not "fresh start")
3. If renamed: all internal usages updated to the new name
4. No silent wrong behavior for any variant of `RoutingCondition`

---

### P3: Rename RoutingStrategy::LlmDecision

**What to change**: Rename `LlmDecision` to `CapabilityWithHint` or similar. The current implementation falls back to keyword capability matching -- it does not make LLM calls. The SDK boundary rule says "no LLM = SDK", so an LLM-named variant in the SDK is misleading.

**Why**: Naming accuracy matters for trust. Consumers choosing `LlmDecision` expect LLM-powered routing. Getting keyword matching instead is a silent capability gap. LLM-based routing is an L3 kaizen-agents concern and should not be implied at SDK level.

**Current state**:

- Rust: confirmed in `supervisor.rs` lines 201-205. Falls back to capability matching with a comment acknowledging the gap.
- Python: verify whether an equivalent exists.

**Acceptance criteria**:

1. The variant is renamed to reflect its actual behavior
2. All internal usages updated
3. If a deprecation path is needed (the variant was already in a release), the old name is kept as a deprecated alias pointing to the new name
4. Documentation reflects that LLM-based routing is an orchestration-layer concern, not an SDK concern

---

### P4: Fix SupervisorAgent Delegation Depth Race Condition

**What to change**: `current_depth` is tracked per supervisor instance via an atomic counter. When the supervisor handles concurrent calls, they share the counter, causing false depth-exceeded rejections. Depth must be tracked per invocation chain, not per supervisor.

**Why**: L3 will increase concurrent supervisor usage (dynamic worker spawning, parallel delegation). The race condition that is rare at L1-L2 becomes frequent at L3.

**Current state**:

- Rust: confirmed in `supervisor.rs` lines 271-282. `current_depth: AtomicU32` is shared across all concurrent `run()` calls.
- Python: verify whether the same pattern exists.

**Acceptance criteria**:

1. Two concurrent invocations of the same supervisor do not interfere with each other's depth tracking
2. Depth limit still enforced correctly for recursive delegation (supervisor -> worker -> supervisor -> worker should hit the limit)
3. Test: launch two concurrent tasks through the same supervisor, both at max_depth-1. Both should succeed. Today, the second would be rejected because the shared counter shows max_depth.

---

### P5: Make Topological Sort Public

**What to change**: `MultiAgentOrchestrator::topological_sort()` is currently private. Make it public (or extract it into a standalone utility function). This method implements Kahn's algorithm with cycle detection, returning execution layers of parallel-safe nodes.

**Why**: L3 PlanExecutor needs DAG scheduling. The topological sort is already implemented and tested. Making it public avoids reimplementation and ensures L3 uses the same battle-tested algorithm.

**Current state**:

- Rust: private method `fn topological_sort()` on `MultiAgentOrchestrator`. Operates on agent name strings.
- Python: verify whether an equivalent exists and its visibility.

**Acceptance criteria**:

1. Topological sort is callable from outside the module
2. Function signature accepts generic node identifiers (not just agent name strings), OR a standalone version exists that is generic
3. Existing internal usage continues to work
4. Cycle detection behavior is preserved and tested

---

### P6: Add Metadata Field to A2AMessage

**What to change**: `A2AMessage` currently has no general-purpose extensibility field beyond the payload. Add an optional `metadata` field (same pattern as `AgentCard.metadata` -- a flexible key-value map).

**Why**: L3 needs to attach envelope references, priority, TTL, delegation chain context, and correlation metadata to messages without changing the message struct shape for each new need. The metadata field provides a forward-compatible extension point.

**Current state**:

- Rust: `A2AMessage` has `id`, `from`, `to`, `message_type`, `payload`, `correlation_id`, `timestamp`. No metadata.
- Python: verify current field set.

**Acceptance criteria**:

1. `A2AMessage` has an optional metadata field that defaults to empty/absent
2. Existing code constructing messages without metadata continues to work
3. Serialization round-trip preserves metadata contents
4. Deserialization of old-format messages (no metadata field) succeeds with metadata defaulting to empty

---

### P7: Add #[non_exhaustive] to AgentCard and AgentCheckpoint Structs

**What to change**: Mark `AgentCard` and `AgentCheckpoint` as forward-compatible for struct construction. This prevents external code from constructing these types via struct literal syntax, forcing use of builder/constructor methods. Future field additions then become non-breaking.

**Why**: B2 (checkpoint harmonization) adds fields to AgentCheckpoint. B5 keeps AgentCard unchanged but future L3 work may add fields. Forward-compatibility annotations make these additions safe.

**Current state**:

- Rust: neither struct is `#[non_exhaustive]`. Both are constructed via builders/constructors internally, but struct literal construction is possible for external consumers.
- Python: not applicable in the same way (Python classes are inherently extensible).

**Acceptance criteria**:

1. Forward-compatibility annotations present on both structs (Rust-specific; Python team should document the construction contract)
2. All internal construction uses builder/constructor methods (no struct literals)
3. Deserialization with `#[serde(default)]` on optional fields works for old serialized data

---

## Decision Traceability

| Decision | Brief Item(s)       | Summary                                                                                                |
| -------- | ------------------- | ------------------------------------------------------------------------------------------------------ |
| D-AC1    | B1                  | Envelope on AgentConfig at SDK level, optional, None default                                           |
| DP-1     | B2                  | Harmonize Rust checkpoint with Python state BEFORE L3                                                  |
| DP-2     | B3                  | ContextScope goes in SDK, both implementations                                                         |
| DP-3     | B4                  | Extend existing MessageType enum, add forward-compatibility first                                      |
| DP-4     | (not in this brief) | Autonomy requirements folded into L3 specs -- Python builds on existing subsystem, Rust builds its own |
| DP-5     | B5                  | Separate AgentInstance struct alongside AgentCard                                                      |

DP-4 is not in this brief because it defines L3 scope, not L0-L2 remediation. It means: the Python team does NOT need to port their autonomy subsystem to Rust before L3. Instead, each L3 spec will define the required primitives, and Rust will build them fresh while Python extends what it already has.

---

## Sequencing Recommendation

The items have natural ordering based on dependencies:

```
Phase 1 (immediate, parallel across teams):
  B1  AgentConfig envelope       -- no dependencies
  B4  MessageType extension      -- no dependencies (Step 1 first, Step 2 after)
  P1  Non-exhaustive enums       -- no dependencies
  P2  Fix Regex routing          -- no dependencies
  P3  Rename LlmDecision         -- no dependencies

Phase 2 (after Phase 1, parallel across teams):
  B2  Checkpoint harmonization   -- benefits from B1 (envelope field informs checkpoint schema)
  B5  AgentInstance struct       -- benefits from B4 (message types inform instance lifecycle events)
  P4  Depth race condition fix   -- no dependencies
  P5  Public topological sort    -- no dependencies
  P6  A2AMessage metadata        -- benefits from P1 (non-exhaustive on related types)
  P7  Non-exhaustive on structs  -- benefits from B2 (checkpoint fields finalized first)

Phase 3 (after Phase 2):
  B3  ContextScope               -- benefits from B2 (checkpoint can save scope projections)
                                 -- benefits from B5 (AgentInstance holds scope reference)
```

L3 spec work can begin once Phase 1 is complete. L3 implementation should not begin until all blocking items (B1-B5) are done.

---

## Audit Findings NOT in This Brief

The following audit findings are acknowledged but intentionally excluded from this remediation brief because they fall under L3 spec scope (not L0-L2 fixes):

- **AgentFactory / runtime agent spawning** (Arbor gap #1) -- L3 spec concern
- **GovernedTaodRunner / TAOD envelope interception** -- L3 spec concern
- **GuardedToolExecutor / tool call gating** -- L3 spec concern
- **BudgetHierarchy / budget carving for child agents** -- L3 spec concern
- **DynamicWorkerPool** -- L3 spec concern (DP-4: Rust builds its own)
- **PlanExecutor / Plan DAG** -- L3 spec concern
- **MessageRouter with envelope validation** -- L3 spec concern
- **RetryDecision callback** -- L3 spec concern
- **PreExecutionHook (Allow/Hold/Block)** -- L3 spec concern
- **Python autonomy subsystem parity** -- DP-4 defers this to per-spec decisions
- **Pipeline restructuring mid-execution** (Arbor gap #5) -- L3 spec concern
- **LlmDecision actual LLM routing** -- L3 kaizen-agents concern
- **Production coordination patterns** (debate, consensus) -- L3 kaizen-agents concern
