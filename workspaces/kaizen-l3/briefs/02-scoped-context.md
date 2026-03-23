# L3 Primitive Specification: ScopedContext

**Spec ID**: L3-002
**Status**: DRAFT
**Author**: kaizen-agents requirements-analyst
**Date**: 2026-03-21
**Dependencies**: None (standalone; does not depend on other L3 primitives)
**PACT Sections**: 6 (Knowledge Clearance), 4.1 (Containment Boundaries), 5.3 (Data Access Dimension), 10 (Architectural Inversion)

---

## 1. Overview

ScopedContext provides hierarchical context scopes with projection-based access control for multi-agent systems. It replaces the flat, unfiltered shared memory model with a tree of scopes where each child scope sees a controlled, filtered subset of its parent's data.

ScopedContext maps two PACT mechanisms to runtime data structures:

1. **Knowledge Clearance** (PACT Section 6): Five classification levels (C0-C4) where access follows need-to-know, not organizational rank. Each context value carries a classification; each agent has an effective clearance. Values above the agent's clearance are invisible.

2. **Data Access Constraints** (PACT Section 5.3): The Data Access dimension of the constraint envelope specifies a classification ceiling and allowed scopes. When a parent creates a child scope, the child's visibility is the intersection of the parent's visibility and the child's projections -- monotonic tightening applied to knowledge.

The primitive is deterministic. It requires no LLM. All filtering, projection, and merge operations are computed from configuration (projections, classifications, clearance levels). The orchestration layer (kaizen-agents) decides WHAT projections to assign; this primitive enforces them.

**Relationship to existing memory**: ScopedContext does NOT replace AgentMemory / SessionMemory / SharedMemory / PersistentMemory. Those are LLM conversation memory (message history, key-value scratch). ScopedContext is structured task data that flows between agents in a delegation hierarchy. An agent uses both:

- **Memory**: "What did the LLM say in turn 3?" (conversation history)
- **Context**: "What is the project name? What files did the parent identify?" (task data flowing through the agent tree)

---

## 2. Types

### 2.1 DataClassification

An ordered enumeration of sensitivity levels. Maps PACT's five classification levels (Section 6.2).

```
enum DataClassification {
    PUBLIC       = 0   // C0: Routine operations, published information
    RESTRICTED   = 1   // C1: Commercial data, personnel records
    CONFIDENTIAL = 2   // C2: Strategic plans, board materials
    SECRET       = 3   // C3: Legal privilege, regulatory investigation
    TOP_SECRET   = 4   // C4: Existential risk, crisis plans
}
```

**Ordering**: PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET. Comparison is numeric on the integer values. An agent with clearance level N can access values with classification <= N.

**Mapping to existing kailash-rs `DataClassification`**: The existing enum in `eatp::constraints::data_access` uses different names for levels 1 and 3: `Internal` (for PACT's RESTRICTED/C1) and `Restricted` (for PACT's SECRET/C3). Implementations MUST provide a bidirectional mapping:

| PACT Level | PACT Name    | kailash-rs Name | Numeric |
|------------|-------------|-----------------|---------|
| C0         | PUBLIC       | Public          | 0       |
| C1         | RESTRICTED   | Internal        | 1       |
| C2         | CONFIDENTIAL | Confidential    | 2       |
| C3         | SECRET       | Restricted      | 3       |
| C4         | TOP_SECRET   | TopSecret       | 4       |

Implementations MAY use either naming convention internally but MUST support conversion between them. The spec uses PACT names throughout.

### 2.2 ContextValue

A value stored in a context scope, with provenance and classification metadata.

```
struct ContextValue {
    value: JSON            // The actual value (any JSON-compatible type)
    written_by: UUID       // Agent instance ID that wrote this value
    updated_at: Timestamp  // When this value was last written
    classification: DataClassification  // Sensitivity level of this value
}
```

**Invariants**:
- `written_by` MUST be set at write time and MUST NOT be modified after creation.
- `updated_at` is refreshed on every write (including overwrites of the same key).
- `classification` MAY be set explicitly at write time. If not set, it inherits the default classification of the scope (see ContextScope.default_classification).

### 2.3 ScopeProjection

Controls which keys are visible (read projection) or writable (write projection) in a scope. Uses glob pattern matching on key strings.

```
struct ScopeProjection {
    allow_patterns: List<String>   // Glob patterns for permitted keys
    deny_patterns: List<String>    // Glob patterns for denied keys (precedence over allow)
}
```

**Pattern syntax**: Standard glob matching with `*` (any characters except `.`) and `**` (any characters including `.`). Examples:
- `"project.*"` matches `project.name`, `project.files` but not `project.config.debug`
- `"project.**"` matches `project.name`, `project.config.debug`, `project.a.b.c`
- `"*.output"` matches `task.output`, `review.output`
- `"**"` matches everything (unrestricted)

**Evaluation rules**:
1. If `allow_patterns` is empty, nothing is allowed (default-deny).
2. If `deny_patterns` is empty, all allowed patterns pass through.
3. A key is accessible if and only if: it matches at least one allow pattern AND it matches zero deny patterns.
4. **Deny takes precedence**: If a key matches both an allow and a deny pattern, the key is DENIED.

**Subset relation**: Projection A is a subset of projection B if every key that A permits is also permitted by B. Formally: for all keys k, if A.permits(k) then B.permits(k). This is used to enforce monotonic tightening at child creation time.

### 2.4 ContextScope

A hierarchical scope node in the context tree. Contains local data, a reference to its parent, and projections controlling what this scope can see and write.

```
struct ContextScope {
    scope_id: UUID                         // Unique identifier for this scope
    parent_id: Option<UUID>                // None for root scope
    owner_id: UUID                         // Agent instance that owns this scope
    data: Map<String, ContextValue>        // Local key-value store
    read_projection: ScopeProjection       // What keys this scope can read from parent chain
    write_projection: ScopeProjection      // What keys this scope can write locally
    effective_clearance: DataClassification // Max classification this scope can access
    default_classification: DataClassification // Default classification for new values written here
    children: List<UUID>                   // Child scope IDs (for traversal/cleanup)
    created_at: Timestamp                  // When this scope was created
}
```

**Invariants**:
- Root scope: `parent_id` is None, `read_projection` permits all (`allow_patterns: ["**"]`, `deny_patterns: []`), `write_projection` permits all.
- Child scope: `parent_id` is always set. `read_projection` MUST be a subset of the parent's `read_projection`. `write_projection` has no subset constraint relative to the parent (a child may write keys the parent cannot read -- the parent controls what it merges back).
- `effective_clearance` MUST be <= parent's `effective_clearance` (monotonic tightening of clearance).
- `scope_id` is globally unique (UUID v4 or equivalent).
- A scope MUST NOT appear as its own ancestor (no circular parent references).

### 2.5 MergeResult

The result of merging a child scope's writes back into its parent.

```
struct MergeResult {
    merged_keys: List<String>     // Keys successfully merged into parent
    skipped_keys: List<String>    // Keys the child wrote but that were outside its write_projection
    conflicts: List<MergeConflict> // Keys where parent had a newer value
}

struct MergeConflict {
    key: String
    parent_value_updated_at: Timestamp
    child_value_updated_at: Timestamp
    resolution: ConflictResolution  // How the conflict was resolved
}

enum ConflictResolution {
    CHILD_WINS    // Child's value overwrites parent (default)
    PARENT_WINS   // Parent's value kept (if parent was updated after child was created)
    SKIPPED       // Neither applied; reported for manual resolution
}
```

**Default merge strategy**: CHILD_WINS for all keys within the child's write_projection. The rationale: the child was delegated a task; its results are the purpose of the delegation. If the parent's value was updated after the child was created but before merge, the conflict is reported in `conflicts` with resolution CHILD_WINS unless the implementation provides an alternative merge policy.

---

## 3. Behavioral Invariants

These invariants are non-negotiable. Every implementation MUST satisfy all of them. Test vectors in Section 9 verify each invariant.

### INV-1: Monotonic Tightening of Visibility

A child scope's visible key set is ALWAYS a subset of its parent's visible key set at the time of child creation. Formally:

```
for all keys k:
    if child.is_visible(k) then parent.is_visible(k)
```

This is enforced at child creation time by requiring the child's read_projection to be a subset of the parent's read_projection. It is NOT dynamically re-evaluated -- see Edge Case 8.1 for implications.

### INV-2: Deny Precedence

In any ScopeProjection evaluation, deny patterns take absolute precedence over allow patterns. If a key matches both an allow pattern and a deny pattern, the key is DENIED.

```
permits(key) = matches_any(allow_patterns, key) AND NOT matches_any(deny_patterns, key)
```

### INV-3: Write Projection Enforcement

A scope cannot write (set) a key that is outside its write_projection. Attempting to write an unpermitted key MUST return an error -- it MUST NOT silently discard the write.

```
set(key, value) -> ERROR if NOT write_projection.permits(key)
```

### INV-4: Classification Filtering

An agent only sees context values at or below its scope's effective_clearance. Values with classification above the scope's effective_clearance are invisible to get(), visible_keys(), and snapshot().

```
get(key) returns None if value.classification > scope.effective_clearance
```

This applies even if the key passes projection filtering. Classification filtering is a second, independent gate applied after projection filtering.

### INV-5: Merge Respects Write Projection

merge_child_results() only propagates keys that match the child's write_projection. Keys the child wrote that are outside its write_projection (which should not exist per INV-3, but may exist due to direct data manipulation in tests) are reported in `skipped_keys` and NOT merged.

```
for each key in child.data:
    if child.write_projection.permits(key):
        merge into parent
    else:
        add to skipped_keys
```

### INV-6: Root Scope Unrestricted

The root scope has no parent, no projection restrictions, and the highest possible effective_clearance. It is the single entry point for all context in a delegation tree.

```
root.parent_id = None
root.read_projection = ScopeProjection(allow: ["**"], deny: [])
root.write_projection = ScopeProjection(allow: ["**"], deny: [])
root.effective_clearance = TOP_SECRET
```

### INV-7: Parent Traversal for Reads

get(key) checks the local data store first. If not found locally, it traverses up to the parent scope, then the grandparent, and so on until the root. At each level, the read_projection of the REQUESTING scope (not the ancestor) is checked. A key is only visible through traversal if the requesting scope's read_projection permits it AND the value's classification does not exceed the requesting scope's effective_clearance.

```
get(key):
    if key in local data AND classification_ok AND read_projection.permits(key):
        return local value
    if parent exists AND read_projection.permits(key):
        return parent.get_for_child(key, self.effective_clearance)
    return None
```

### INV-8: Remove Is Local Only

remove(key) removes a key from the local data store only. It MUST NOT propagate removal to parent or child scopes. After removal, a subsequent get(key) will traverse to the parent and may return the parent's value (if projections permit).

---

## 4. Operations

### 4.1 create_child

```
create_child(
    owner_id: UUID,
    read_projection: ScopeProjection,
    write_projection: ScopeProjection,
    effective_clearance: Optional<DataClassification> = None,
    default_classification: Optional<DataClassification> = None
) -> Result<ContextScope, ContextError>
```

**Preconditions**:
- `read_projection` MUST be a subset of `self.read_projection` (INV-1).
- If `effective_clearance` is provided, it MUST be <= `self.effective_clearance`. If not provided, it defaults to `self.effective_clearance`.
- If `default_classification` is provided, it MUST be <= the child's effective_clearance. If not provided, it inherits from `self.default_classification`.

**Postconditions**:
- Returns a new ContextScope with `parent_id = self.scope_id`.
- The child's `data` map is empty (context is accessed via parent traversal, not copied).
- The child's `scope_id` is added to `self.children`.

**Errors**:
- `ProjectionNotSubset`: The requested read_projection permits keys that self.read_projection does not permit.
- `ClearanceExceedsParent`: The requested effective_clearance exceeds self.effective_clearance.

### 4.2 get

```
get(key: String) -> Result<Option<ContextValue>, ContextError>
```

**Behavior**:
1. Check if `self.read_projection.permits(key)`. If not, return `Ok(None)`.
2. Check local `self.data` for the key.
3. If found locally, check `value.classification <= self.effective_clearance`. If classification too high, return `Ok(None)`.
4. If found locally and classification passes, return `Ok(Some(value))`.
5. If not found locally and parent exists, delegate to parent with this scope's read_projection and effective_clearance as the filtering criteria.
6. If not found in any ancestor, return `Ok(None)`.

**Errors**:
- No error cases for get (inaccessible keys return None, not errors).

### 4.3 set

```
set(key: String, value: JSON, classification: Optional<DataClassification> = None) -> Result<(), ContextError>
```

**Behavior**:
1. Check if `self.write_projection.permits(key)`. If not, return `Err(WriteProjectionViolation)`.
2. Determine classification: use provided classification, or fall back to `self.default_classification`.
3. If the determined classification > self.effective_clearance, return `Err(ClassificationExceedsClearance)`. An agent cannot create values it cannot itself read.
4. Create ContextValue with `written_by = self.owner_id`, `updated_at = now()`, classification as determined.
5. Insert into `self.data` (overwriting any existing value at this key).
6. Return `Ok(())`.

**Errors**:
- `WriteProjectionViolation`: Key does not match write_projection.
- `ClassificationExceedsClearance`: Attempted to write a value with classification above the scope's effective_clearance.

### 4.4 remove

```
remove(key: String) -> Result<Option<ContextValue>, ContextError>
```

**Behavior**:
1. Remove key from `self.data` and return the removed value (if any).
2. Does NOT check projections (removing a locally-held key is always permitted).
3. Does NOT propagate to parent or children.

**Errors**:
- None. Removing a non-existent key returns `Ok(None)`.

### 4.5 visible_keys

```
visible_keys() -> List<String>
```

**Behavior**:
1. Collect all keys from local data where `read_projection.permits(key)` AND `value.classification <= effective_clearance`.
2. Recursively collect all visible keys from parent (applying this scope's projections and clearance as the filter).
3. Return the union, deduplicated. Local keys shadow parent keys (if the same key exists locally and in an ancestor, it appears once).

### 4.6 snapshot

```
snapshot() -> Map<String, JSON>
```

**Behavior**:
1. Call `visible_keys()` to get all accessible keys.
2. For each key, call `get(key)` and extract the `value` field (not the full ContextValue).
3. Return a flat map of key -> JSON value.

This is the primary serialization point for sending context to an LLM. The snapshot represents the scope's complete "view of the world" as a flat key-value map.

### 4.7 merge_child_results

```
merge_child_results(child: ContextScope) -> Result<MergeResult, ContextError>
```

**Preconditions**:
- `child.parent_id` MUST equal `self.scope_id`.

**Behavior**:
1. For each key in `child.data`:
   a. If `child.write_projection.permits(key)`:
      - If `self.data` contains the key AND `self.data[key].updated_at > child.created_at`:
        - Record a MergeConflict. Apply default resolution (CHILD_WINS).
      - Copy `child.data[key]` into `self.data[key]`. Preserve the child's `written_by` and `updated_at`.
      - Add key to `merged_keys`.
   b. If NOT `child.write_projection.permits(key)`:
      - Add key to `skipped_keys`. Do NOT merge.
2. Remove `child.scope_id` from `self.children`.
3. Return MergeResult.

**Errors**:
- `NotAChild`: The provided scope is not a child of this scope.

### 4.8 Factory: create root scope

```
ContextScope.root(
    owner_id: UUID,
    effective_clearance: DataClassification = TOP_SECRET,
    default_classification: DataClassification = RESTRICTED
) -> ContextScope
```

Creates the root scope for a delegation tree. The root has no parent, unrestricted projections, and the specified clearance level.

---

## 5. PACT Record Mapping

Every ScopedContext operation that constitutes a governance event MUST produce the corresponding EATP record. The records are emitted but the ScopedContext primitive itself does not persist them -- it delegates to the EATP audit subsystem.

| ScopedContext Operation | EATP Record | Contents |
|------------------------|-------------|----------|
| create_child() succeeds | Delegation Record | Parent scope ID, child scope ID, read_projection, write_projection, effective_clearance, timestamp |
| create_child() with effective_clearance set | Constraint Envelope (Data Access dimension) | Classification ceiling, allowed scope patterns from projection |
| get() returns None due to classification filtering | Audit Anchor (subtype: `barrier_enforced`) | Requesting scope ID, key, value classification, scope effective_clearance, timestamp |
| get() returns None due to projection denial | Audit Anchor (subtype: `barrier_enforced`) | Requesting scope ID, key, denied by which deny_pattern, timestamp |
| set() rejected by write_projection | Audit Anchor (subtype: `barrier_enforced`) | Scope ID, key, write_projection, timestamp |
| set() rejected by classification ceiling | Audit Anchor (subtype: `barrier_enforced`) | Scope ID, key, attempted classification, effective_clearance, timestamp |
| merge_child_results() | Audit Anchor (subtype: `context_merged`) | Parent scope ID, child scope ID, merged_keys count, skipped_keys count, conflict count |

**Implementation note**: Whether get()-denial audit records are emitted on every call or only on the first denial per key per scope is an implementation decision. Emitting on every call provides full traceability but may generate high volume. Implementations MAY batch or deduplicate denial records within a configurable window.

---

## 6. Knowledge Clearance Integration

This section maps PACT Section 6 (Knowledge Clearance) to ScopedContext runtime behavior.

### 6.1 Clearance Is Independent of Hierarchy Position

A child agent deep in the delegation tree MAY have higher clearance than a sibling closer to the root, if its role requires access to sensitive data. The clearance is set per-scope at creation time by the parent, based on the task's data requirements -- not by the child's depth in the tree.

However, monotonic tightening still applies: a child's effective_clearance MUST NOT exceed its parent's effective_clearance. A parent at CONFIDENTIAL cannot grant SECRET to a child. If a task requires SECRET clearance, the delegating agent must itself hold SECRET clearance. This is PACT's containment boundary applied to clearance.

### 6.2 Posture-Gated Effective Clearance

PACT Section 6.3 defines:

```
effective_clearance = min(role.max_clearance, posture_ceiling[agent.posture])
```

ScopedContext does NOT evaluate trust posture itself. The effective_clearance passed to create_child() is expected to already incorporate posture gating. The caller (AgentFactory or orchestration layer) computes the effective clearance from the agent's role clearance and trust posture, then passes the result to create_child().

This separation ensures ScopedContext remains a pure data structure with deterministic behavior, while posture evaluation remains in the trust-plane subsystem where it belongs.

### 6.3 Classification of New Values

When an agent writes a new value via set():

1. **Explicit classification**: If the caller provides a DataClassification, that classification is used. The classification MUST NOT exceed the scope's effective_clearance (you cannot create data you cannot read).

2. **Default classification**: If no classification is provided, the scope's `default_classification` is used. This defaults to the parent's `default_classification` at child creation time, which defaults to RESTRICTED at root creation time.

3. **Orchestration-layer override**: The orchestration layer (kaizen-agents) may use a ClassificationAssigner (LLM-driven) to determine classification based on content analysis. This happens BEFORE calling set(), not inside ScopedContext.

### 6.4 Compartments (Future Extension)

PACT Section 6.2 specifies compartment-based isolation at SECRET and TOP_SECRET levels. This spec does not define compartment semantics. Compartments can be modeled as key namespace prefixes (e.g., `compartment.aml-investigations.findings`) combined with projection patterns. A future revision may add first-class compartment support.

---

## 7. What Exists Today

| Component | Location | Reuse Strategy |
|-----------|----------|---------------|
| `AgentMemory` trait (store/retrieve/remove/keys/clear) | kailash-rs: `kailash-kaizen/src/memory/mod.rs` | Interface reference only. ScopedContext is a new trait/struct, not an extension of AgentMemory. |
| `SharedMemory` (Arc-locked HashMap) | kailash-rs: `kailash-kaizen/src/memory/shared.rs` | Flat store reference. ScopedContext adds hierarchy, projections, classification. No code reuse. |
| `SharedMemoryPool` with tag-based filtering | kailash-py: `kaizen/memory/shared_memory.py` | Conceptual ancestor. Tag-based filtering is a weaker version of ScopeProjection. No code reuse, but the test patterns (write, filter, read back) apply. |
| `DataClassification` enum (5 levels) | kailash-rs: `eatp::constraints::data_access` | Direct reuse with name mapping (see Section 2.1). Import and re-export. |
| `DataAccessConstraints` (allowed/denied sources) | kailash-rs: `eatp::constraints::data_access` | Conceptual alignment with ScopeProjection's allow/deny patterns. Different granularity (data sources vs. context keys). |
| Data Access dimension of ConstraintEnvelope | kailash-rs: `trust-plane/envelope.rs` | The envelope's data access ceiling maps to ContextScope.effective_clearance. Read at child creation time. |

---

## 8. Edge Cases

### 8.1 Parent Scope Modified After Child Created

**Question**: If a parent writes a new key after a child is created, does the child see it?

**Answer**: YES, if the child's read_projection permits the key and the value's classification is within the child's clearance. Context scopes use lazy traversal (get() walks up the parent chain at read time), not eager copying. The child sees the parent's current state, not a snapshot from creation time.

**Consequence**: The monotonic tightening invariant (INV-1) governs which keys the child CAN see (determined by projections set at creation), not which keys exist. New parent keys that match the child's projections become visible. New parent keys outside the child's projections remain invisible.

### 8.2 Circular Parent Reference Prevention

**Invariant**: A scope MUST NOT appear as its own ancestor. Implementations MUST prevent this structurally:
- create_child() always creates a NEW scope with a fresh UUID.
- There is no `set_parent()` or `reparent()` operation.
- The only way to create a parent-child relationship is through create_child(), which guarantees the child is new.

If an implementation provides scope deserialization (e.g., ScopeSerializer), it MUST validate the parent chain on deserialization and reject cycles.

### 8.3 Empty Projection

A ScopeProjection with `allow_patterns: []` and `deny_patterns: []` permits NOTHING. This is valid but results in a scope that cannot see or write any keys. It is the maximally restrictive projection.

A ScopeProjection with `allow_patterns: ["**"]` and `deny_patterns: ["**"]` also permits NOTHING (deny takes precedence). This is equivalent to the empty allow case.

Implementations MUST handle these cases without error. A scope with an empty read projection simply sees no data. A scope with an empty write projection cannot store any data.

### 8.4 Child Writes a Key That Parent's Read Projection Denies

**Scenario**: Child has `write_projection: allow ["results.**"]`. Parent has `read_projection: deny ["results.internal.*"]`. Child writes `results.internal.debug_log`.

**Behavior at merge time**: merge_child_results() checks the child's write_projection, NOT the parent's read_projection. The key `results.internal.debug_log` passes the child's write_projection, so it IS merged into the parent's data store. The parent's read_projection only governs what the parent can SEE via get(), not what data is stored.

**Post-merge**: The key exists in the parent's data but the parent cannot read it via get() (filtered by the parent's own read_projection). The parent's parent (grandparent) may be able to see it if the grandparent's projections permit it. This is correct behavior: data propagates upward through the tree; visibility is controlled independently at each level.

### 8.5 Concurrent Reads and Writes from Multiple Children

**Scenario**: A parent has multiple active children. Child A writes `results.analysis`, Child B writes `results.review`. Both are merged back.

**Requirement**: Implementations MUST be thread-safe for concurrent get() and set() operations on the same scope. The specific concurrency mechanism (RwLock, channels, MVCC) is implementation-defined.

**Merge ordering**: If two children write to the SAME key, the merge order determines the final value. merge_child_results() is called sequentially (one child at a time). The last child merged wins for conflicting keys. The caller (orchestration layer) controls merge order.

**No cross-child visibility**: A child CANNOT see another child's local data. Children share visibility of the parent's data (via traversal), but each child's local writes are private until merged back into the parent.

### 8.6 Deeply Nested Scope Chains

**Scenario**: Root -> A -> B -> C -> D. Agent D calls get("project.name").

**Behavior**: Traversal walks D -> C -> B -> A -> Root, checking D's read_projection at each level. The first scope containing the key (where projections and classification permit) returns the value.

**Performance concern**: Deep chains create long traversal paths. Implementations MAY cache resolved values, but caches MUST be invalidated when a parent scope's data changes. Alternatively, snapshot() materializes the full visible state and avoids repeated traversal.

### 8.7 Root Scope with Reduced Clearance

The root factory defaults to TOP_SECRET clearance, but callers MAY create a root with lower clearance. A root with CONFIDENTIAL clearance means no scope in the tree can access SECRET or TOP_SECRET data, even if such data is somehow injected into the data store. Classification filtering applies unconditionally.

---

## 9. Conformance Test Vectors

Each test vector is a JSON object with `setup`, `operation`, and `expected` fields. Implementations MUST pass all test vectors.

### TV-1: Basic Projection Filtering (verifies INV-1, INV-2)

```json
{
  "test_id": "TV-1",
  "description": "Child scope sees only keys matching its read_projection; deny takes precedence",
  "setup": {
    "root": {
      "owner_id": "root-agent-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "project.name": { "value": "kaizen", "classification": "PUBLIC" },
        "project.budget": { "value": 50000, "classification": "CONFIDENTIAL" },
        "secrets.api_key": { "value": "sk-abc123", "classification": "SECRET" },
        "shared.status": { "value": "active", "classification": "PUBLIC" }
      }
    },
    "child": {
      "owner_id": "child-agent-001",
      "read_projection": {
        "allow_patterns": ["project.**", "shared.*"],
        "deny_patterns": ["project.budget"]
      },
      "write_projection": {
        "allow_patterns": ["results.*"],
        "deny_patterns": []
      },
      "effective_clearance": "CONFIDENTIAL"
    }
  },
  "operations": [
    { "op": "child.get", "key": "project.name", "expected": { "value": "kaizen" } },
    { "op": "child.get", "key": "project.budget", "expected": null, "reason": "denied by deny_pattern" },
    { "op": "child.get", "key": "secrets.api_key", "expected": null, "reason": "not in allow_patterns AND classification SECRET > CONFIDENTIAL" },
    { "op": "child.get", "key": "shared.status", "expected": { "value": "active" } },
    { "op": "child.visible_keys", "expected": ["project.name", "shared.status"] }
  ]
}
```

### TV-2: Write Projection Enforcement (verifies INV-3)

```json
{
  "test_id": "TV-2",
  "description": "Child cannot write keys outside its write_projection",
  "setup": {
    "root": {
      "owner_id": "root-agent-001",
      "effective_clearance": "TOP_SECRET",
      "data": {}
    },
    "child": {
      "owner_id": "child-agent-001",
      "read_projection": { "allow_patterns": ["**"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["results.*"], "deny_patterns": [] },
      "effective_clearance": "CONFIDENTIAL"
    }
  },
  "operations": [
    {
      "op": "child.set",
      "key": "results.output",
      "value": "analysis complete",
      "expected": "OK"
    },
    {
      "op": "child.set",
      "key": "project.name",
      "value": "tampered",
      "expected": "ERROR:WriteProjectionViolation"
    },
    {
      "op": "child.set",
      "key": "results.classified",
      "value": "top-secret-data",
      "classification": "SECRET",
      "expected": "ERROR:ClassificationExceedsClearance",
      "reason": "child clearance is CONFIDENTIAL, cannot write SECRET value"
    }
  ]
}
```

### TV-3: Classification Filtering (verifies INV-4)

```json
{
  "test_id": "TV-3",
  "description": "Agent cannot see values above its effective_clearance even if projection permits",
  "setup": {
    "root": {
      "owner_id": "root-agent-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "report.public_summary": { "value": "Q3 results positive", "classification": "PUBLIC" },
        "report.internal_details": { "value": "Revenue: $12M", "classification": "RESTRICTED" },
        "report.board_strategy": { "value": "Acquire CompanyX", "classification": "CONFIDENTIAL" },
        "report.legal_privileged": { "value": "Litigation pending", "classification": "SECRET" },
        "report.crisis_plan": { "value": "Scenario Alpha", "classification": "TOP_SECRET" }
      }
    },
    "child": {
      "owner_id": "analyst-agent-001",
      "read_projection": { "allow_patterns": ["report.**"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["analysis.*"], "deny_patterns": [] },
      "effective_clearance": "RESTRICTED"
    }
  },
  "operations": [
    { "op": "child.get", "key": "report.public_summary", "expected": { "value": "Q3 results positive" } },
    { "op": "child.get", "key": "report.internal_details", "expected": { "value": "Revenue: $12M" } },
    { "op": "child.get", "key": "report.board_strategy", "expected": null, "reason": "CONFIDENTIAL > RESTRICTED clearance" },
    { "op": "child.get", "key": "report.legal_privileged", "expected": null, "reason": "SECRET > RESTRICTED clearance" },
    { "op": "child.get", "key": "report.crisis_plan", "expected": null, "reason": "TOP_SECRET > RESTRICTED clearance" },
    { "op": "child.visible_keys", "expected": ["report.public_summary", "report.internal_details"] }
  ]
}
```

### TV-4: Merge Child Results (verifies INV-5)

```json
{
  "test_id": "TV-4",
  "description": "merge_child_results propagates only keys matching child's write_projection",
  "setup": {
    "root": {
      "owner_id": "root-agent-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "project.name": { "value": "kaizen", "classification": "PUBLIC" }
      }
    },
    "child": {
      "owner_id": "worker-agent-001",
      "read_projection": { "allow_patterns": ["project.*"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["results.*"], "deny_patterns": [] },
      "effective_clearance": "CONFIDENTIAL"
    }
  },
  "operations": [
    { "op": "child.set", "key": "results.review", "value": { "status": "approved", "score": 95 }, "expected": "OK" },
    { "op": "child.set", "key": "results.summary", "value": "All tests passed", "expected": "OK" },
    {
      "op": "root.merge_child_results",
      "child_scope_id": "CHILD_SCOPE_ID",
      "expected": {
        "merged_keys": ["results.review", "results.summary"],
        "skipped_keys": [],
        "conflicts": []
      }
    },
    { "op": "root.get", "key": "results.review", "expected": { "value": { "status": "approved", "score": 95 } } },
    { "op": "root.get", "key": "results.summary", "expected": { "value": "All tests passed" } },
    { "op": "root.get", "key": "project.name", "expected": { "value": "kaizen" }, "reason": "original data preserved" }
  ]
}
```

### TV-5: Parent Traversal Across Multiple Levels (verifies INV-7, Edge Case 8.6)

```json
{
  "test_id": "TV-5",
  "description": "get() traverses parent chain; local values shadow parent values",
  "setup": {
    "root": {
      "owner_id": "root-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "config.db_host": { "value": "prod.db.example.com", "classification": "RESTRICTED" },
        "config.app_name": { "value": "kaizen-root", "classification": "PUBLIC" },
        "config.secret_key": { "value": "root-secret", "classification": "SECRET" }
      }
    },
    "middle": {
      "owner_id": "middle-001",
      "parent": "root",
      "read_projection": { "allow_patterns": ["config.**"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["config.app_name", "results.*"], "deny_patterns": [] },
      "effective_clearance": "CONFIDENTIAL",
      "data": {
        "config.app_name": { "value": "kaizen-middle", "classification": "PUBLIC" }
      }
    },
    "leaf": {
      "owner_id": "leaf-001",
      "parent": "middle",
      "read_projection": { "allow_patterns": ["config.*"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["output.*"], "deny_patterns": [] },
      "effective_clearance": "RESTRICTED"
    }
  },
  "operations": [
    {
      "op": "leaf.get",
      "key": "config.app_name",
      "expected": { "value": "kaizen-middle" },
      "reason": "middle's local value shadows root's value"
    },
    {
      "op": "leaf.get",
      "key": "config.db_host",
      "expected": { "value": "prod.db.example.com" },
      "reason": "traverses through middle to root; RESTRICTED <= RESTRICTED clearance"
    },
    {
      "op": "leaf.get",
      "key": "config.secret_key",
      "expected": null,
      "reason": "SECRET > RESTRICTED (leaf's clearance); filtered by classification"
    },
    {
      "op": "leaf.visible_keys",
      "expected": ["config.app_name", "config.db_host"],
      "reason": "config.secret_key excluded by classification filter"
    }
  ]
}
```

### TV-6: Dynamic Parent Update Visibility (verifies Edge Case 8.1)

```json
{
  "test_id": "TV-6",
  "description": "Child sees parent's new keys written after child creation (lazy traversal)",
  "setup": {
    "root": {
      "owner_id": "root-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "project.name": { "value": "kaizen", "classification": "PUBLIC" }
      }
    },
    "child": {
      "owner_id": "child-001",
      "read_projection": { "allow_patterns": ["project.*"], "deny_patterns": [] },
      "write_projection": { "allow_patterns": ["results.*"], "deny_patterns": [] },
      "effective_clearance": "CONFIDENTIAL"
    }
  },
  "operations": [
    { "op": "child.get", "key": "project.deadline", "expected": null, "reason": "key does not exist yet" },
    { "op": "root.set", "key": "project.deadline", "value": "2026-04-01", "classification": "PUBLIC" },
    { "op": "child.get", "key": "project.deadline", "expected": { "value": "2026-04-01" }, "reason": "child sees parent's new key via lazy traversal" }
  ]
}
```

### TV-7: Empty Projection Scope (verifies Edge Case 8.3)

```json
{
  "test_id": "TV-7",
  "description": "Scope with empty allow_patterns sees nothing and writes nothing",
  "setup": {
    "root": {
      "owner_id": "root-001",
      "effective_clearance": "TOP_SECRET",
      "data": {
        "project.name": { "value": "kaizen", "classification": "PUBLIC" }
      }
    },
    "child": {
      "owner_id": "sandboxed-001",
      "read_projection": { "allow_patterns": [], "deny_patterns": [] },
      "write_projection": { "allow_patterns": [], "deny_patterns": [] },
      "effective_clearance": "PUBLIC"
    }
  },
  "operations": [
    { "op": "child.get", "key": "project.name", "expected": null, "reason": "empty allow = no visibility" },
    { "op": "child.visible_keys", "expected": [] },
    { "op": "child.set", "key": "anything", "value": "test", "expected": "ERROR:WriteProjectionViolation" },
    { "op": "child.snapshot", "expected": {} }
  ]
}
```

---

## Appendix A: Error Types

```
enum ContextError {
    ProjectionNotSubset {
        parent_projection: ScopeProjection,
        requested_projection: ScopeProjection,
        violating_pattern: String       // The first allow_pattern in requested that exceeds parent
    }
    ClearanceExceedsParent {
        parent_clearance: DataClassification,
        requested_clearance: DataClassification
    }
    WriteProjectionViolation {
        key: String,
        write_projection: ScopeProjection
    }
    ClassificationExceedsClearance {
        key: String,
        value_classification: DataClassification,
        scope_clearance: DataClassification
    }
    NotAChild {
        expected_parent_id: UUID,
        actual_parent_id: Option<UUID>
    }
    CircularReference {
        scope_id: UUID
    }
}
```

All errors are structured and inspectable. Implementations MUST provide at minimum the fields listed above in their error types.

---

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **Scope** | A node in the context hierarchy, owned by one agent, containing local data and projections |
| **Projection** | A filter (allow/deny glob patterns) controlling key visibility or writability |
| **Traversal** | Walking up the parent chain to resolve a get() request |
| **Classification** | The sensitivity level attached to a context value |
| **Clearance** | The maximum classification level a scope (and its owning agent) can access |
| **Monotonic tightening** | The invariant that child visibility/clearance is always <= parent's |
| **Merge** | Propagating a child's local writes back into the parent scope after task completion |
| **Snapshot** | A flat, materialized view of all keys visible to a scope |
