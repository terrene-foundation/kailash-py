# L3 Conformance Test Format

**Status**: Normative
**Audience**: kailash-rs (Rust core), kailash-py (Python bindings), any future SDK implementation
**Scope**: Behavioral parity verification for all L3 primitives defined in specs 01 through 05

---

## 1. Purpose

This document defines the format, structure, and runner contract for conformance tests that verify behavioral parity between the Rust core (kailash-rs) and the Python bindings (kailash-py) for L3 agent primitives. Both implementations must produce identical observable outcomes for every test vector. A passing conformance suite is the single source of truth for "these two implementations behave the same."

The conformance tests are purely deterministic. They exercise the SDK layer only -- no LLM calls, no network I/O, no randomness. Every test vector has exactly one correct output.

---

## 2. Test Vector JSON Schema

Each test vector is a single JSON object conforming to this schema. Test vectors are stored in files organized by primitive, one file per primitive, each containing an array of vectors.

### 2.1 Top-Level Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "L3ConformanceTestVector",
  "type": "object",
  "required": ["id", "primitive", "operation", "description", "setup", "action", "expected", "invariants_checked"],
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^CT-(ENV|CTX|MSG|FAC|PLAN)-[0-9]{2,3}$",
      "description": "Unique identifier. Prefix encodes primitive: ENV=envelope, CTX=context, MSG=messaging, FAC=factory, PLAN=plan-dag."
    },
    "primitive": {
      "type": "string",
      "enum": ["envelope", "context", "messaging", "factory", "plan"]
    },
    "operation": {
      "type": "string",
      "description": "The specific operation under test. Must match an operation name from the spec (e.g., 'record_consumption', 'split', 'route', 'spawn', 'validate_structure')."
    },
    "description": {
      "type": "string",
      "description": "Human-readable description of what this vector tests and why."
    },
    "setup": {
      "type": "object",
      "description": "Initial state that the test runner must establish before executing the action. Structure varies by primitive."
    },
    "action": {
      "oneOf": [
        {
          "type": "object",
          "description": "A single operation to perform."
        },
        {
          "type": "array",
          "items": { "type": "object" },
          "description": "A sequence of operations performed in order. Each element is an action object with its own expected outcome."
        }
      ],
      "description": "The operation(s) to execute against the state established by setup."
    },
    "expected": {
      "type": "object",
      "description": "Expected outcome. Contains either a success result or an error descriptor. Structure varies by operation.",
      "properties": {
        "outcome": {
          "type": "string",
          "enum": ["success", "error"],
          "description": "Whether the operation should succeed or fail."
        },
        "error_type": {
          "type": "string",
          "description": "If outcome is error, the error type name (not the message string)."
        }
      }
    },
    "invariants_checked": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of invariant IDs verified by this test (e.g., ['INV-1', 'INV-2'] or ['I-01', 'INV-PLAN-06'])."
    },
    "notes": {
      "type": "string",
      "description": "Optional. Clarifying notes for implementors about edge cases or non-obvious behavior."
    },
    "cross_primitive_deps": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional. List of other primitives this test exercises (e.g., ['envelope', 'context'] for a factory test that validates envelope tightening and context key requirements)."
    }
  }
}
```

### 2.2 ID Convention

IDs follow the pattern `CT-{PRIMITIVE}-{NUMBER}`:

| Prefix      | Primitive            | Spec   |
| ----------- | -------------------- | ------ |
| `CT-ENV-`   | Envelope Extensions  | 01     |
| `CT-CTX-`   | Scoped Context       | 02     |
| `CT-MSG-`   | Messaging            | 03     |
| `CT-FAC-`   | Agent Factory        | 04     |
| `CT-PLAN-`  | Plan DAG             | 05     |

Numbers are zero-padded to two digits minimum (01-99). If a primitive exceeds 99 vectors, three digits are used (100+).

### 2.3 Action Sequence Format

When `action` is an array (sequenced operations), each element has the form:

```json
{
  "step": 1,
  "operation": "record_consumption",
  "input": { "dimension": "financial", "cost": 30.0 },
  "expected": {
    "outcome": "success",
    "verdict": { "type": "APPROVED", "zone": "AUTO_APPROVED" },
    "state_after": { "financial_remaining": 70.0 }
  }
}
```

Each step carries its own `expected` block. The runner executes steps in order and validates each step's outcome before proceeding to the next. A failure at step N halts the sequence; steps N+1 through M are reported as "not reached."

### 2.4 File Layout

```
conformance/
  vectors/
    01-envelope.json       # Array of CT-ENV-* vectors
    02-context.json        # Array of CT-CTX-* vectors
    03-messaging.json      # Array of CT-MSG-* vectors
    04-factory.json        # Array of CT-FAC-* vectors
    05-plan-dag.json       # Array of CT-PLAN-* vectors
    06-cross-primitive.json # Vectors that span multiple primitives
  schema/
    test-vector.schema.json # The JSON Schema above
  runners/
    README.md              # Runner contract specification
```

Each vector file is a JSON array of test vector objects. Vectors within a file are ordered by ID.

---

## 3. Coverage Requirements

### 3.1 Per-Primitive Minimum Coverage

Every conformance suite MUST include test vectors that cover:

1. **Every public operation** defined in the spec's Section 4 (Operations), with at least one happy-path and one error-path vector.
2. **Every behavioral invariant** defined in the spec's Section 3, with at least one test vector whose `invariants_checked` field includes that invariant ID.
3. **Every edge case** enumerated in the spec's Section 8, with at least one test vector that exercises that scenario.
4. **Every error type** listed in the spec's Appendix A (Error Types), with at least one vector that triggers that error.

### 3.2 Envelope Extensions (Spec 01)

| Category | Requirement | Minimum Vectors |
| --- | --- | --- |
| Operations | `new`, `record_consumption`, `remaining`, `usage_pct`, `can_afford`, `split`, `allocate_to_child`, `reclaim`, `verify` | 1 happy + 1 error each |
| Invariants | INV-1 through INV-10 | 1 per invariant |
| Edge Cases | 8.1 through 8.9 | 1 per edge case |
| Error Types | InvalidCost, InvalidEnvelope, InvalidGradient, BudgetExceeded, RatioSumExceedsOne, NonFiniteRatio, ReserveInvalid, EmptyAllocations, ParentDimensionUnbounded | 1 per error type |
| Gradient Zones | AUTO_APPROVED, FLAGGED, HELD, BLOCKED | 1 transition vector per zone |
| Multi-Dimension | Most-restrictive-wins across 2+ dimensions | 1 vector minimum |

### 3.3 Scoped Context (Spec 02)

| Category | Requirement | Minimum Vectors |
| --- | --- | --- |
| Operations | `create_root`, `create_child`, `get`, `set`, `remove`, `visible_keys`, `snapshot`, `merge_child_results` | 1 happy + 1 error each |
| Invariants | INV-1 through INV-8 | 1 per invariant |
| Edge Cases | 8.1 through 8.6 (as referenced in spec) | 1 per edge case |
| Error Types | ProjectionNotSubset, ClearanceExceedsParent, WriteProjectionViolation, ClassificationExceedsClearance, NotAChild, CircularReference | 1 per error type |
| Classification Levels | PUBLIC, RESTRICTED, CONFIDENTIAL, SECRET, TOP_SECRET filtering | 1 vector with multi-level hierarchy |
| Traversal | 3-level parent chain with shadowing | 1 vector minimum |

### 3.4 Messaging (Spec 03)

| Category | Requirement | Minimum Vectors |
| --- | --- | --- |
| Operations | `route`, `send` (channel), `receive`, `close_channels_for`, `dead_letter_record`, `drain` | 1 happy + 1 error each |
| Invariants | Invariant 1 through 9 | 1 per invariant |
| Message Types | Delegation, Status, Clarification, Completion, Escalation, System | 1 routing vector per type |
| Directionality | Parent-to-child, child-to-parent, sibling (rejected), ancestor escalation | 1 per direction |
| Error Conditions | CommunicationBlocked, RecipientTerminated, Expired, DirectionalityViolation, ChannelClosed, Backpressure | 1 per error |
| Dead Letters | Record, eviction at capacity, drain | 1 per operation |

### 3.5 Agent Factory (Spec 04)

| Category | Requirement | Minimum Vectors |
| --- | --- | --- |
| Operations | `spawn`, `terminate`, `transition_state`, `lineage`, `list_children`, `get_instance` | 1 happy + 1 error each |
| Invariants | I-01 through I-10 | 1 per invariant |
| State Transitions | Pending->Running, Running->Waiting, Waiting->Running, Running->Completed, Running->Failed, *->Terminated, invalid transitions | 1 per valid transition + 1 invalid |
| Cascade | 3-level cascade termination with budget reclamation | 1 vector minimum |
| Error Types | EnvelopeNotTighter, ToolNotInParent, MaxDepthExceeded, MaxChildrenExceeded, RequiredContextMissing, InvalidStateTransition, BudgetInsufficient | 1 per error type |
| EATP Records | DelegationRecord + ConstraintEnvelope on success; AuditAnchor on rejection | 1 per EATP record type |

### 3.6 Plan DAG (Spec 05)

| Category | Requirement | Minimum Vectors |
| --- | --- | --- |
| Validation | validate_structure, validate_envelopes, validate_resources | 1 happy + 1 error each |
| Execution Patterns | Linear chain, fan-out/fan-in, diamond, single-node | 1 per pattern |
| Gradient Handling | AutoApproved retry, Held (retry exhausted), Flagged (optional failure), Blocked (envelope violation) | 1 per gradient zone |
| Modifications | AddNode, RemoveNode, AddEdge, RemoveEdge, UpdateSpec, ReplaceNode | 1 per modification type |
| Edge Cases | EC-01 through EC-11 | 1 per edge case |
| Error Types | CycleDetected, BudgetOverflow, ReferentialIntegrityViolation, EmptyPlan, RunningNodeProtection | 1 per error type |
| Event Ordering | Strict ordering constraints (Ready before Started, Started before Completed) | 1 vector with ordering assertions |

### 3.7 Cross-Primitive Interactions

These vectors verify that primitives integrate correctly:

| Interaction | What It Tests | Minimum Vectors |
| --- | --- | --- |
| Factory uses Envelope | Spawn deducts parent budget; termination reclaims | 2 |
| Factory uses Context | `required_context_keys` validated against parent scope | 1 |
| Factory uses Messaging | Bidirectional channels created at spawn, closed at termination | 1 |
| Plan uses Factory | PlanExecutor spawns agents via factory for each node | 1 |
| Plan uses Envelope | Budget summation validation; per-node envelope tightening | 1 |
| Plan uses Messaging | Delegation/Completion messages between plan executor and node agents | 1 |
| Context merge after Completion | Child writes to scoped context; completion merges back to parent | 1 |

---

## 4. Test Runner Contract

A conformant test runner is any program that loads test vectors, executes them against an L3 implementation, and reports results. Both kailash-rs and kailash-py must provide a conformance test runner.

### 4.1 Runner Requirements

1. **Load vectors**: Parse all JSON files from the `conformance/vectors/` directory. Validate each vector against the JSON Schema before execution. Reject malformed vectors with a clear error.

2. **Establish state**: For each vector, construct the initial state described by `setup`. This includes creating envelope trackers, scoped contexts, message routers, agent instances, or plan structures as required. The runner must not carry state between vectors -- each vector starts from a clean slate.

3. **Execute action**: Perform the operation(s) described by `action` against the established state. For sequenced actions, execute in order.

4. **Compare outcome**: Compare the actual result against `expected` using the parity rules defined in Section 5. On match, record PASS. On mismatch, record FAIL with a structured diff.

5. **Report**: Produce a report containing:
   - Total vectors: count
   - Passed: count
   - Failed: count with per-vector diff
   - Skipped: count (vectors that could not be set up)
   - Coverage: percentage of invariants covered
   - Duration: wall-clock time

6. **Exit code**: Exit 0 if all vectors pass. Exit 1 if any vector fails. Exit 2 if vectors could not be loaded.

### 4.2 State Construction Helpers

Runners should provide helper functions for common setup patterns:

```
make_envelope_tracker(setup.envelope, setup.gradient) -> EnvelopeTracker
make_scoped_context(setup.root, setup.children?) -> ScopedContext hierarchy
make_message_router(setup.agents, setup.channels) -> MessageRouter
make_agent_factory(setup.instances?) -> AgentFactory with pre-registered instances
make_plan(setup.plan) -> Plan with nodes and edges
```

These helpers translate the JSON setup into the SDK's native types. The mapping is implementation-specific but the observable behavior must be identical.

### 4.3 Vector Filtering

Runners MUST support filtering vectors by:
- Primitive: `--primitive envelope`
- ID pattern: `--id CT-ENV-01`
- Invariant: `--invariant INV-1`
- Tag: `--tag error-path` (future extensibility)

### 4.4 Deterministic Execution

Runners MUST execute vectors in ID-sorted order within each primitive file. Cross-primitive vectors (file 06) execute after all single-primitive files. This ensures reproducible results across runs.

---

## 5. Parity Verification Rules

When comparing actual output from kailash-rs against actual output from kailash-py (or comparing either against the expected values in the vector), the following rules apply.

### 5.1 Floating-Point Comparison

All floating-point comparisons use an absolute tolerance of `1e-9` (one billionth). This accounts for IEEE 754 representation differences between Rust's `f64` and Python's `float` (both 64-bit, but intermediary calculation order may differ).

```
PASS if |actual - expected| <= 1e-9
```

For percentage values (usage_pct, ratios), the same tolerance applies.

For financial values, the comparison is exact to 2 decimal places when the expected value has at most 2 decimal places. When the expected value has more precision, the `1e-9` tolerance applies.

Rationale: Financial limits are typically set as whole numbers or two-decimal currency amounts. The 1e-9 tolerance catches floating-point representation errors without masking real bugs.

### 5.2 Error Comparison

Errors are compared at the **type level**, not by message string. The comparison checks:

1. **Error type name**: Must match exactly (e.g., `InvalidCost`, `EnvelopeNotTighter`, `CycleDetected`).
2. **Error fields**: Structured fields listed in the expected block must be present and match. Fields in the actual error not listed in expected are ignored (forward-compatible).
3. **Error message strings**: NOT compared. Implementations may use different wording, different languages, or include additional context. Only the type and structured fields matter.

Example:
```json
{
  "expected": {
    "outcome": "error",
    "error_type": "EnvelopeNotTighter",
    "error_dimension": "financial",
    "parent_value": "5000",
    "child_value": "10000"
  }
}
```

This passes if the actual error has type `EnvelopeNotTighter` with a `dimension` field containing `"financial"`, regardless of the message text.

### 5.3 Ordering Requirements

Some outputs have defined ordering; others do not.

**Strict ordering (comparison must match sequence)**:
- Cost history entries within an EnvelopeTracker (timestamp order)
- Lineage path (root to leaf)
- Cascade termination order (leaves first, then parents)
- Plan event sequence for sequential nodes (Ready before Started before Completed)
- Action sequence step results (step 1 before step 2)

**Unordered (comparison uses set equality)**:
- `visible_keys()` return value (set of key strings)
- `list_children()` return value (set of instance IDs)
- Parallel-ready nodes in plan execution (worker_1 and worker_2 may become Ready in either order)
- `merged_keys` and `skipped_keys` in merge results
- Validation errors (all errors are returned, order is unspecified)
- EATP records within a single operation (order is unspecified unless the spec mandates it)

**Partially ordered (DAG order must be respected, but siblings are unordered)**:
- Plan events for parallel nodes: NodeReady events for siblings may appear in any order, but NodeReady for a node must appear before NodeStarted for that same node.
- Cascade termination: all children terminate before parent, but sibling termination order is unspecified.

When an expected field has ordering implications, the vector's `notes` field clarifies whether strict, unordered, or partial ordering applies.

### 5.4 Timestamp Handling

Conformance tests use **relative timestamps**, never absolute wall-clock times. Test vectors that involve time use one of two patterns:

**Pattern A: Fixed timestamps (ISO 8601 strings)**

Used for setup data where specific instants matter (e.g., temporal window boundaries). The runner parses these as fixed instants. Comparison checks structural properties (e.g., "window_start < window_end") rather than clock equality.

```json
{
  "temporal": {
    "window_start": "2026-03-21T00:00:00Z",
    "window_end": "2026-03-22T00:00:00Z"
  }
}
```

**Pattern B: Duration offsets**

Used for TTL, elapsed time, and timeout scenarios. The runner controls the clock.

```json
{
  "action": {
    "operation": "route",
    "current_time": "2026-03-21T10:05:00Z",
    "envelope": {
      "sent_at": "2026-03-21T10:00:00Z",
      "ttl": "PT60S"
    }
  }
}
```

The runner provides `current_time` to the routing logic. It does not depend on the system clock. The expected outcome is computed from the given times.

**Generated timestamps** (e.g., `created_at` on an AgentInstance) are NOT compared. The vector marks such fields with the sentinel value `"<generated>"` or omits them from the expected block.

### 5.5 UUID Handling

Test vectors use fixed UUIDs for reproducibility:
- `"00000000-0000-0000-0000-000000000001"` through `"...0099"` for pre-existing entities in setup.
- `"aaaa-0001"` through `"aaaa-9999"` as shorthand (runners should accept both full and abbreviated forms in test vectors, but implementations generate standard UUID v4 or v7).

For UUIDs generated during test execution (e.g., a spawned agent's instance_id), the expected block uses the sentinel `"<generated>"`. The runner:
1. Captures the actual generated UUID.
2. Uses it for all subsequent references within the same vector.
3. Does not compare it against a fixed value.

### 5.6 Null vs. Absent

In expected output:
- `"field": null` means the field must be present with value null.
- Omitting a field means the field is not checked (may be present or absent).
- `"field": "<absent>"` means the field must NOT be present.

---

## 6. Test Vector Index

### 6.1 Summary

| Primitive | Spec | Existing Vectors | Invariants | Edge Cases | ID Range |
| --- | --- | --- | --- | --- | --- |
| Envelope Extensions | 01 | 6 | 10 (INV-1 through INV-10) | 9 (8.1 through 8.9) | CT-ENV-01 through CT-ENV-06 |
| Scoped Context | 02 | 7 | 8 (INV-1 through INV-8) | 6 (8.1 through 8.6) | CT-CTX-01 through CT-CTX-07 |
| Messaging | 03 | 7 | 9 (Invariant 1 through 9) | 0 (inline in invariants) | CT-MSG-01 through CT-MSG-07 |
| Agent Factory | 04 | 7 | 10 (I-01 through I-10) | 6 (8.1 through 8.6) | CT-FAC-01 through CT-FAC-07 |
| Plan DAG | 05 | 12 | 15 (INV-PLAN-01 through INV-PLAN-15) | 11 (EC-01 through EC-11) | CT-PLAN-01 through CT-PLAN-12 |
| **Total** | | **39** | **52** | **32** | |

### 6.2 Envelope Extensions Vectors (Spec 01)

| Vector ID | Original Name | Operation | Invariants Checked |
| --- | --- | --- | --- |
| CT-ENV-01 | Test Vector 1 | record_consumption (multi-step: approve, flag, hold, block) | INV-1, INV-4, INV-8, INV-10 |
| CT-ENV-02 | Test Vector 2 | split + allocate_to_child + reclaim | INV-2, INV-5, INV-6 |
| CT-ENV-03 | Test Vector 3 | split (rejection: ratios exceed 1.0) | INV-2 |
| CT-ENV-04 | Test Vector 4 | record_consumption + split (NaN, Inf, boundary) | INV-4, INV-7, INV-8 |
| CT-ENV-05 | Test Vector 5 | record_consumption (multi-dimension, most-restrictive) | INV-4, INV-10 |
| CT-ENV-06 | Test Vector 6 | allocate_to_child + record_consumption + reclaim (zone restoration) | INV-1, INV-5, INV-10 |

### 6.3 Scoped Context Vectors (Spec 02)

| Vector ID | Original Name | Operation | Invariants Checked |
| --- | --- | --- | --- |
| CT-CTX-01 | TV-1 | get, visible_keys (projection filtering) | INV-1, INV-2 |
| CT-CTX-02 | TV-2 | set (write projection enforcement) | INV-3 |
| CT-CTX-03 | TV-3 | get, visible_keys (classification filtering) | INV-4 |
| CT-CTX-04 | TV-4 | set + merge_child_results | INV-5 |
| CT-CTX-05 | TV-5 | get, visible_keys (3-level parent traversal) | INV-7 |
| CT-CTX-06 | TV-6 | set + get (dynamic parent update visibility) | INV-7, Edge 8.1 |
| CT-CTX-07 | TV-7 | get, set, visible_keys, snapshot (empty projection) | INV-1, INV-2, INV-3, Edge 8.3 |

### 6.4 Messaging Vectors (Spec 03)

| Vector ID | Original Name | Operation | Invariants Checked |
| --- | --- | --- | --- |
| CT-MSG-01 | TV-MSG-01 | route (delegation, happy path) | Inv-1, Inv-2, Inv-3, Inv-5, Inv-8 |
| CT-MSG-02 | TV-MSG-02 | route (communication constraint blocks) | Inv-1 |
| CT-MSG-03 | TV-MSG-03 | route (message to terminated agent) | Inv-2, Inv-4 |
| CT-MSG-04 | TV-MSG-04 | route (TTL expiry) | Inv-6 |
| CT-MSG-05 | TV-MSG-05 | route (directionality violation: sibling delegation) | Inv-3 |
| CT-MSG-06 | TV-MSG-06 | route (completion without correlation_id) | Inv-5 |
| CT-MSG-07 | TV-MSG-07 | dead_letter_record (capacity eviction) | Inv-9 |

### 6.5 Agent Factory Vectors (Spec 04)

| Vector ID | Original Name | Operation | Invariants Checked |
| --- | --- | --- | --- |
| CT-FAC-01 | TV-01 | spawn (success with tighter envelope) | I-01, I-07 |
| CT-FAC-02 | TV-02 | spawn (rejected: envelope not tighter) | I-01 |
| CT-FAC-03 | TV-03 | terminate (cascade with budget reclamation) | I-02, I-08 |
| CT-FAC-04 | TV-04 | spawn (rejected: tool not in parent) | I-05 |
| CT-FAC-05 | TV-05 | spawn (rejected: max depth exceeded) | I-09 |
| CT-FAC-06 | TV-06 | terminate (idempotent on already-terminated) | Edge 8.3 |
| CT-FAC-07 | TV-07 | lineage (root-to-instance path) | I-04 |

### 6.6 Plan DAG Vectors (Spec 05)

| Vector ID | Original Name | Operation | Invariants Checked |
| --- | --- | --- | --- |
| CT-PLAN-01 | CT-PLAN-01 | execute (linear 3-node happy path) | INV-PLAN-01, INV-PLAN-09 |
| CT-PLAN-02 | CT-PLAN-02 | execute (parallel fan-out/fan-in) | INV-PLAN-01, INV-PLAN-09 |
| CT-PLAN-03 | CT-PLAN-03 | execute (retry within budget, AutoApproved) | INV-PLAN-12 |
| CT-PLAN-04 | CT-PLAN-04 | execute (retry exhausted, Held) | INV-PLAN-12 |
| CT-PLAN-05 | CT-PLAN-05 | execute (optional node failure, Flagged skip) | INV-PLAN-08, INV-PLAN-09 |
| CT-PLAN-06 | CT-PLAN-06 | execute (envelope violation, always Blocked) | INV-PLAN-08 |
| CT-PLAN-07 | CT-PLAN-07 | execute + modify (AddNode during execution) | INV-PLAN-13, INV-PLAN-14 |
| CT-PLAN-08 | CT-PLAN-08 | modify (AddEdge creates cycle, rejected) | INV-PLAN-01, INV-PLAN-13 |
| CT-PLAN-09 | CT-PLAN-09 | execute (resolution timeout escalation) | INV-PLAN-12 |
| CT-PLAN-10 | CT-PLAN-10 | execute (budget warning thresholds) | INV-PLAN-06, INV-PLAN-08 |
| CT-PLAN-11 | CT-PLAN-11 | validate (budget overflow rejected) | INV-PLAN-06 |
| CT-PLAN-12 | CT-PLAN-12 | execute (CompletionDependency unblocks on failure) | INV-PLAN-09 |

### 6.7 Invariant Coverage Matrix

This matrix tracks which invariants are covered by at least one test vector. An implementation's conformance suite MUST fill every cell.

#### Envelope (10 invariants)

| Invariant | Description | Covered By |
| --- | --- | --- |
| INV-1 | Monotonically decreasing budget | CT-ENV-01, CT-ENV-06 |
| INV-2 | Split conservation | CT-ENV-02, CT-ENV-03 |
| INV-3 | Non-bypassable enforcement | (requires additional vector) |
| INV-4 | Envelope violations always BLOCKED | CT-ENV-01, CT-ENV-04, CT-ENV-05 |
| INV-5 | Reclamation ceiling | CT-ENV-02, CT-ENV-06 |
| INV-6 | Child tighter than parent | CT-ENV-02 |
| INV-7 | Finite arithmetic only | CT-ENV-04 |
| INV-8 | Zero budget means blocked | CT-ENV-01, CT-ENV-04 |
| INV-9 | Atomic cost recording | (requires additional vector) |
| INV-10 | Gradient zone monotonicity | CT-ENV-01, CT-ENV-05, CT-ENV-06 |

#### Scoped Context (8 invariants)

| Invariant | Description | Covered By |
| --- | --- | --- |
| INV-1 | Monotonic tightening of visibility | CT-CTX-01, CT-CTX-07 |
| INV-2 | Deny precedence | CT-CTX-01, CT-CTX-07 |
| INV-3 | Write projection enforcement | CT-CTX-02, CT-CTX-07 |
| INV-4 | Classification filtering | CT-CTX-03 |
| INV-5 | Merge respects write projection | CT-CTX-04 |
| INV-6 | Root scope unrestricted | (implicit in all root setups; requires explicit vector) |
| INV-7 | Parent traversal for reads | CT-CTX-05, CT-CTX-06 |
| INV-8 | Remove is local only | (requires additional vector) |

#### Messaging (9 invariants)

| Invariant | Description | Covered By |
| --- | --- | --- |
| Inv-1 | Communication envelope enforcement | CT-MSG-01, CT-MSG-02 |
| Inv-2 | Recipient state acceptance | CT-MSG-01, CT-MSG-03 |
| Inv-3 | Message type directionality | CT-MSG-01, CT-MSG-05 |
| Inv-4 | Terminated agent messages to dead letters | CT-MSG-03 |
| Inv-5 | Correlation ID consistency | CT-MSG-01, CT-MSG-06 |
| Inv-6 | TTL enforcement | CT-MSG-04 |
| Inv-7 | Channel capacity bounds | (requires additional vector) |
| Inv-8 | Bidirectional channel setup at spawn | CT-MSG-01 |
| Inv-9 | Dead letter bounded growth | CT-MSG-07 |

#### Agent Factory (10 invariants)

| Invariant | Description | Covered By |
| --- | --- | --- |
| I-01 | Monotonic envelope tightening | CT-FAC-01, CT-FAC-02 |
| I-02 | Cascade termination | CT-FAC-03 |
| I-03 | Globally unique instance IDs | (structural; requires additional vector) |
| I-04 | Immutable lineage | CT-FAC-07 |
| I-05 | Tool allowlist subsetting | CT-FAC-04 |
| I-06 | State machine validity | (requires additional vector) |
| I-07 | Budget accounting at spawn | CT-FAC-01 |
| I-08 | Budget reclamation on completion | CT-FAC-03 |
| I-09 | Max depth enforcement | CT-FAC-05 |
| I-10 | Required context validation | (requires additional vector) |

#### Plan DAG (15 invariants)

| Invariant | Description | Covered By |
| --- | --- | --- |
| INV-PLAN-01 | Acyclicity | CT-PLAN-01, CT-PLAN-02, CT-PLAN-08 |
| INV-PLAN-02 | Referential integrity | (requires additional vector) |
| INV-PLAN-03 | Root existence | (requires additional vector) |
| INV-PLAN-04 | Leaf existence | (requires additional vector) |
| INV-PLAN-05 | Non-empty | (requires additional vector; related: CT-PLAN-11 tests budget) |
| INV-PLAN-06 | Budget summation | CT-PLAN-10, CT-PLAN-11 |
| INV-PLAN-07 | Monotonic tightening | (requires additional vector) |
| INV-PLAN-08 | Envelope violations are blocked | CT-PLAN-05, CT-PLAN-06 |
| INV-PLAN-09 | Event completeness | CT-PLAN-01, CT-PLAN-02, CT-PLAN-05, CT-PLAN-12 |
| INV-PLAN-10 | Suspension semantics | (requires additional vector) |
| INV-PLAN-11 | Cancellation semantics | (requires additional vector) |
| INV-PLAN-12 | Gradient determinism | CT-PLAN-03, CT-PLAN-04, CT-PLAN-09 |
| INV-PLAN-13 | Atomic validation | CT-PLAN-07, CT-PLAN-08 |
| INV-PLAN-14 | Batch atomicity | CT-PLAN-07 |
| INV-PLAN-15 | Running node protection | (requires additional vector) |

### 6.8 Coverage Gaps

The existing 39 vectors leave **16 invariants without direct coverage**. Before the conformance suite is considered complete, additional vectors MUST be authored for:

| Gap ID | Primitive | Invariant | Required Vector Description |
| --- | --- | --- | --- |
| GAP-01 | Envelope | INV-3 | Verify that no API path bypasses enforcement (attempt to record without enforcer) |
| GAP-02 | Envelope | INV-9 | Two concurrent record_consumption calls; both costs must be recorded or one blocked |
| GAP-03 | Context | INV-6 | Explicit test that root scope has TOP_SECRET clearance and unrestricted projections |
| GAP-04 | Context | INV-8 | Remove a key locally, then get() returns parent's value |
| GAP-05 | Messaging | Inv-7 | Send to a full channel; verify backpressure error (not silent drop) |
| GAP-06 | Factory | I-03 | Spawn two agents; verify instance IDs are distinct |
| GAP-07 | Factory | I-06 | Attempt invalid state transition (Completed -> Running); verify error |
| GAP-08 | Factory | I-10 | Spawn with required_context_keys; parent context missing key; verify rejection |
| GAP-09 | Plan | INV-PLAN-02 | Edge referencing non-existent node; verify rejection |
| GAP-10 | Plan | INV-PLAN-03 | Plan with no root node (all nodes have incoming deps forming a cycle-free but rootless graph -- impossible, but test that the validator catches degenerate configurations) |
| GAP-11 | Plan | INV-PLAN-04 | Plan with no leaf node (impossible in a finite DAG, but validator should check) |
| GAP-12 | Plan | INV-PLAN-05 | Empty plan (zero nodes); verify rejection |
| GAP-13 | Plan | INV-PLAN-07 | Node envelope wider than plan envelope on one dimension; verify rejection |
| GAP-14 | Plan | INV-PLAN-10 | Suspend plan; verify no new nodes start; verify running nodes continue |
| GAP-15 | Plan | INV-PLAN-11 | Cancel plan; verify all running agents terminated; pending nodes skipped |
| GAP-16 | Plan | INV-PLAN-15 | RemoveNode on a running node; verify Held (not silent termination) |

The target for a complete conformance suite is **39 existing + 16 gap vectors = 55 minimum vectors**, plus cross-primitive vectors from Section 3.7 (minimum 8) for a total target of **63 vectors minimum**.

---

## 7. Running the Conformance Suite

### 7.1 Rust (kailash-rs)

```bash
cargo test --test conformance -- --test-threads=1
```

The conformance test runner lives in `tests/conformance/` within the kailash-rs repository. It loads vectors from `conformance/vectors/`, constructs Rust types from JSON setup, executes operations, and compares results.

### 7.2 Python (kailash-py)

```bash
pytest tests/conformance/ -v --tb=short
```

The conformance test runner lives in `tests/conformance/` within the kailash-py repository. It uses `pytest` parametrization to generate one test case per vector. Each test loads the vector JSON, constructs Python objects from setup, executes operations, and compares results.

### 7.3 Cross-Implementation Parity Check

To verify parity between Rust and Python, run both suites against the same vector files and compare the reports:

```bash
# Generate structured reports
cargo test --test conformance -- --format json > rust-results.json
pytest tests/conformance/ --json-report --json-report-file=python-results.json

# Compare (both should show identical pass/fail per vector ID)
diff <(jq -r '.[] | "\(.id): \(.result)"' rust-results.json | sort) \
     <(jq -r '.[] | "\(.id): \(.result)"' python-results.json | sort)
```

Any difference in this diff is a parity bug. The investigation starts with the vector ID where behavior diverges.

---

## 8. Authoring New Vectors

### 8.1 Process

1. Identify the invariant, edge case, or operation that lacks coverage (see Section 6.8 for known gaps).
2. Write the vector as a JSON object conforming to the schema in Section 2.1.
3. Add it to the appropriate primitive file in `conformance/vectors/`.
4. Assign the next available ID within the primitive's range.
5. List all invariants the vector checks in `invariants_checked`.
6. Add a `notes` field if the expected behavior has non-obvious reasoning.
7. Run both conformance suites. The new vector should pass in both implementations (or reveal a bug in one).

### 8.2 Guidelines

- **One concept per vector**: Each vector should test one specific behavior. Combine operations only when the sequence is the point of the test (e.g., "reclamation restores zone" requires consume + allocate + reclaim).
- **Minimal setup**: Include only the state necessary to exercise the behavior. Do not include unrelated agents, channels, or context keys.
- **Fixed values for reproducibility**: Use fixed UUIDs and timestamps. Avoid any source of non-determinism.
- **Explicit expected values**: Prefer explicit values over computed assertions. Write `"financial_remaining": 70.0`, not `"financial_remaining": "envelope.limit - cost"`.
- **Document the why**: The `notes` field should explain non-obvious expected behavior, especially boundary conditions and ordering constraints.

### 8.3 Naming Conventions for Operations

Use the operation names from the specs consistently:

| Primitive | Operations |
| --- | --- |
| Envelope | `new`, `record_consumption`, `remaining`, `usage_pct`, `can_afford`, `split`, `allocate_to_child`, `reclaim`, `verify` |
| Context | `create_root`, `create_child`, `get`, `set`, `remove`, `visible_keys`, `snapshot`, `merge_child_results` |
| Messaging | `route`, `send`, `receive`, `close_channels_for`, `dead_letter_record`, `drain` |
| Factory | `spawn`, `terminate`, `transition_state`, `lineage`, `list_children`, `get_instance` |
| Plan | `validate_structure`, `validate_envelopes`, `validate_resources`, `validate`, `execute`, `apply_modification`, `suspend`, `resume`, `cancel` |

---

## 9. Versioning

The conformance test suite is versioned alongside the L3 specs. When a spec changes, the corresponding vectors must be updated.

- **Version**: `1.0.0` (initial release, covering specs 01-05 as written on 2026-03-22)
- **Compatibility**: Vectors are forward-compatible. New fields in expected blocks with a default of "not checked" (omitted) can be added without breaking older runners.
- **Breaking changes**: Any change to an existing vector's `expected` block that would cause a previously-passing implementation to fail requires a major version bump and a migration guide.

---

## Appendix A: Example Conformance Vector (Complete)

This is CT-ENV-01 translated to the formal schema:

```json
{
  "id": "CT-ENV-01",
  "primitive": "envelope",
  "operation": "record_consumption",
  "description": "Basic budget tracking through all four gradient zones: AUTO_APPROVED, FLAGGED, HELD, BLOCKED. Verifies that costs are recorded, remaining budget decreases, and zone transitions follow threshold configuration.",
  "setup": {
    "envelope": {
      "financial_limit": 100.0,
      "action_limit": 10,
      "temporal_limit_seconds": 3600
    },
    "gradient": {
      "budget_flag_threshold": 0.8,
      "budget_hold_threshold": 0.95
    }
  },
  "action": [
    {
      "step": 1,
      "operation": "record_consumption",
      "input": {
        "action": "llm_call_1",
        "dimension": "financial",
        "cost": 30.0,
        "agent_instance_id": "00000000-0000-0000-0000-000000000001"
      },
      "expected": {
        "outcome": "success",
        "verdict": { "type": "APPROVED", "zone": "AUTO_APPROVED" },
        "state_after": {
          "financial_remaining": 70.0,
          "financial_pct": 0.3
        }
      }
    },
    {
      "step": 2,
      "operation": "record_consumption",
      "input": {
        "action": "llm_call_2",
        "dimension": "financial",
        "cost": 55.0,
        "agent_instance_id": "00000000-0000-0000-0000-000000000001"
      },
      "expected": {
        "outcome": "success",
        "verdict": { "type": "APPROVED", "zone": "FLAGGED" },
        "state_after": {
          "financial_remaining": 15.0,
          "financial_pct": 0.85
        }
      }
    },
    {
      "step": 3,
      "operation": "record_consumption",
      "input": {
        "action": "llm_call_3",
        "dimension": "financial",
        "cost": 12.0,
        "agent_instance_id": "00000000-0000-0000-0000-000000000001"
      },
      "expected": {
        "outcome": "success",
        "verdict": { "type": "HELD", "dimension": "financial", "current_usage": 0.97 },
        "state_after": {
          "financial_remaining": 3.0
        }
      }
    },
    {
      "step": 4,
      "operation": "record_consumption",
      "input": {
        "action": "llm_call_4",
        "dimension": "financial",
        "cost": 5.0,
        "agent_instance_id": "00000000-0000-0000-0000-000000000001"
      },
      "expected": {
        "outcome": "error",
        "verdict": { "type": "BLOCKED", "dimension": "financial", "requested": 5.0, "available": 3.0 },
        "state_after": {
          "financial_remaining": 3.0
        }
      },
      "notes": "Cost NOT recorded because action was BLOCKED. Remaining unchanged."
    }
  ],
  "expected": {
    "outcome": "success",
    "total_steps": 4,
    "final_state": {
      "financial_remaining": 3.0,
      "actions_remaining": 10,
      "cost_history_length": 3
    }
  },
  "invariants_checked": ["INV-1", "INV-4", "INV-8", "INV-10"],
  "notes": "The third call (cost=12) brings usage to 97/100=0.97 which exceeds hold_threshold (0.95), so verdict is HELD and cost IS recorded. The fourth call (cost=5) would bring usage to 102/100>1.0 so it is BLOCKED and cost is NOT recorded."
}
```

---

## Appendix B: Canonical Invariant ID Reference

For cross-referencing across specs and this conformance format, here is the complete list of invariant IDs:

### Envelope Extensions (01): `INV-1` through `INV-10`

- INV-1: Monotonically decreasing budget
- INV-2: Split conservation
- INV-3: Non-bypassable enforcement
- INV-4: Envelope violations always BLOCKED
- INV-5: Reclamation ceiling
- INV-6: Child tighter than parent
- INV-7: Finite arithmetic only
- INV-8: Zero budget means blocked
- INV-9: Atomic cost recording
- INV-10: Gradient zone monotonicity

### Scoped Context (02): `INV-1` through `INV-8`

*Note: Context invariant IDs overlap with envelope IDs. When ambiguity exists, prefix with the spec number: `02-INV-1`.*

- INV-1: Monotonic tightening of visibility
- INV-2: Deny precedence
- INV-3: Write projection enforcement
- INV-4: Classification filtering
- INV-5: Merge respects write projection
- INV-6: Root scope unrestricted
- INV-7: Parent traversal for reads
- INV-8: Remove is local only

### Messaging (03): `Inv-1` through `Inv-9`

- Inv-1: Communication envelope enforcement
- Inv-2: Recipient state acceptance
- Inv-3: Message type directionality
- Inv-4: Terminated agent messages to dead letters
- Inv-5: Correlation ID consistency
- Inv-6: TTL enforcement
- Inv-7: Channel capacity bounds
- Inv-8: Bidirectional channel setup at spawn
- Inv-9: Dead letter bounded growth

### Agent Factory (04): `I-01` through `I-10`

- I-01: Monotonic envelope tightening at spawn
- I-02: Cascade termination
- I-03: Globally unique instance IDs
- I-04: Immutable lineage
- I-05: Tool allowlist subsetting
- I-06: State machine validity
- I-07: Budget accounting at spawn
- I-08: Budget reclamation on completion
- I-09: Max depth enforcement
- I-10: Required context validation at spawn

### Plan DAG (05): `INV-PLAN-01` through `INV-PLAN-15`

- INV-PLAN-01: Acyclicity
- INV-PLAN-02: Referential integrity
- INV-PLAN-03: Root existence
- INV-PLAN-04: Leaf existence
- INV-PLAN-05: Non-empty
- INV-PLAN-06: Budget summation
- INV-PLAN-07: Monotonic tightening
- INV-PLAN-08: Envelope violations are blocked
- INV-PLAN-09: Event completeness
- INV-PLAN-10: Suspension semantics
- INV-PLAN-11: Cancellation semantics
- INV-PLAN-12: Gradient determinism
- INV-PLAN-13: Atomic validation
- INV-PLAN-14: Batch atomicity
- INV-PLAN-15: Running node protection

**Total invariants across all L3 primitives: 52**
