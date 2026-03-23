# L3 Autonomy Primitives — Red Team Report

## Executive Summary

The L3 specification suite is thorough and well-structured, with strong cross-referencing between briefs and clear SDK/orchestration boundary delineation. However, this analysis identifies 23 findings across 7 categories, including 3 CRITICAL issues, 6 HIGH issues, 9 MEDIUM issues, and 5 LOW issues. The most severe findings involve type system inconsistencies between specs, unspecified async lifecycle coordination, and a missing WaitReason variant that breaks the messaging-to-state-machine contract.

---

## 1. Spec Inconsistencies

### F-01: Verdict (spec 01) vs GradientZone (spec 05) — Overlapping But Incompatible Types [CRITICAL]

Spec 01 defines a `Verdict` enum with three variants: `APPROVED { zone: GradientZone }`, `HELD { ... }`, `BLOCKED { ... }`. Spec 05 uses `GradientZone` directly as the classification output (AutoApproved, Flagged, Held, Blocked). The Verdict type wraps GradientZone with additional metadata (hold_id, dimension, requested/available), but PlanExecutor's gradient rules (G1-G9) reference GradientZone directly — not Verdict.

**Gap**: When PlanExecutor processes an EnvelopeTracker callback, does it receive a `Verdict` or a `GradientZone`? The EnvelopeTracker's `record_consumption()` returns a `Verdict`. PlanExecutor's gradient rules expect to classify into `GradientZone`. The conversion is unspecified.

**Recommendation**: Spec 05 should explicitly state that PlanExecutor consumes `Verdict` from EnvelopeTracker and extracts the zone for gradient classification. The mapping: `Verdict::APPROVED { zone: FLAGGED } -> GradientZone::Flagged`, `Verdict::HELD -> GradientZone::Held`, `Verdict::BLOCKED -> GradientZone::Blocked`.

### F-02: MessageType in Brief 00 vs Brief 03 — Variant Name Mismatch [HIGH]

Brief 00 (B4) specifies four new MessageType variants: `Delegation`, `DelegationResult`, `Escalation`, `SystemControl`. Brief 03 specifies six: `Delegation`, `Status`, `Clarification`, `Completion`, `Escalation`, `System`. The names `DelegationResult` vs `Completion`, and `SystemControl` vs `System`, do not align. Brief 00 also omits `Status` and `Clarification` entirely.

**Gap**: If B4 is implemented as written and L3 messaging is built on top, there is a mismatch. Brief 00 was likely written before Brief 03 was finalized.

**Recommendation**: Update Brief 00 B4 to reference the six L3 variants from Brief 03 exactly, or note that B4's list is illustrative and the definitive list comes from Brief 03. The implementation plan (01-implementation-plan.md) line 21 repeats Brief 00's names, confirming this inconsistency propagated.

### F-03: WaitReason Missing ClarificationPending Variant [HIGH]

Spec 04 defines `WaitReason` with three variants: `DelegationResponse`, `HumanApproval`, `ResourceAvailability`. But Spec 03 (messaging, Section 4.3) specifies that when a blocking clarification is sent, the sender transitions to `Waiting { reason: ClarificationPending { message_id } }`. This variant does not exist in Spec 04's WaitReason enum.

**Recommendation**: Add `ClarificationPending { message_id: UUID }` to the WaitReason enum in Spec 04. Also consider `EscalationPending` (referenced in Spec 03 Section 4.6 for Critical severity escalations).

### F-04: Existing PACT VerificationLevel vs L3 GradientZone — Naming Collision [MEDIUM]

The existing codebase has `VerificationLevel(str, Enum)` in `pact/governance/config.py` with values `AUTO_APPROVED`, `FLAGGED`, `HELD`, `BLOCKED`. The L3 specs define `GradientZone` with the same four values. Creating a new `GradientZone` enum while `VerificationLevel` already exists creates a conversion burden.

**Recommendation**: Reuse `VerificationLevel` as `GradientZone` (alias/re-export), or define the canonical mapping. Do not create a second enum with identical values.

### F-05: PACT AgentConfig (Pydantic) vs Kaizen AgentConfig (dataclass) — B1 Target Ambiguity [MEDIUM]

Two `AgentConfig` classes exist: `pact/governance/config.py` (Pydantic BaseModel) and `kaizen/agent_config.py` (dataclass). B1 does not specify which one.

**Recommendation**: Explicitly target `kaizen/agent_config.py`. Verify whether the PACT AgentConfig also needs an envelope reference.

---

## 2. Missing Edge Cases

### F-06: No Specification for Async Channel Lifecycle Coordination [CRITICAL]

The specs describe a linear flow (spawn → channels → delegate → execute → complete) but in async Python, these are concurrent. **What happens if a child sends a Completion message but the parent has not yet started listening on the channel?**

No spec defines when or how the parent begins consuming messages from children. Without specifying the message consumption loop, implementations will make different assumptions.

**Recommendation**: Add a section to Spec 03 or Spec 04 describing the message consumption model: does each agent run a message processing loop as a background asyncio task? Is it callback-driven?

### F-07: Cascade Termination + Spawn Interleaving Under Async [CRITICAL]

Spec 04 I-02 specifies cascade termination is "depth-first, leaves first." But in async: if a child spawns a new grandchild between the descendant collection and the termination iteration, that grandchild is missed. Idempotent termination (R2 mitigation) does NOT address this interleaving problem.

**Recommendation**: Spec 04 should specify that spawn operations MUST be blocked (held) while a cascade termination is in progress for any ancestor. Implement by holding the parent's lock during the entire cascade.

### F-08: Plan Modification Re-validation During Execution — Draft Transition Problem [HIGH]

Spec 05's `apply_modification()` states: "If Executing, re-validate in-place." But PlanState transitions don't include `Executing -> Draft`. What if re-validation fails during execution?

**Recommendation**: Clarify that for Executing plans, modification + re-validation is atomic and the plan stays in Executing state throughout. If re-validation fails, the modification is rejected. Add `Executing -> Executing` as an explicit self-transition.

### F-09: ScopedContext Merge After Child Failure — Unspecified [MEDIUM]

Spec 02 defines `merge_child_results()` but doesn't specify behavior when the child's state is Failed. The child may have written partial results.

**Recommendation**: Add edge case: "merge_child_results() MAY be called regardless of child's terminal state. The parent decides whether to merge partial results from a failed child."

### F-10: Budget Split vs. Tracker Allocation — Two-Step Not Atomic [MEDIUM]

`EnvelopeSplitter.split()` applies ratios to the original envelope; `EnvelopeTracker.allocate_to_child()` checks remaining budget. Split can succeed but allocation can fail.

**Recommendation**: Consider `split_and_allocate()` composite operation, or document the rollback pattern.

### F-11: asyncio.Queue Is FIFO; Spec Requires Priority Ordering [LOW]

Spec 03 defines Priority (Low/Normal/High/Critical) with ordering, but `asyncio.Queue` is FIFO.

**Recommendation**: Use `asyncio.PriorityQueue` or document priority as advisory.

---

## 3. Implementation Plan Gaps

### F-12: B3 (ContextScope) Listed as Both Blocking and Phase 1b — Scope Confusion [HIGH]

Brief 00's B3 describes a basic ContextScope; Brief 02 describes the full L3 ScopedContext. The plan doesn't clearly distinguish "add basic ContextScope to SDK" (B3) from "implement full L3 ScopedContext" (Spec 02).

**Recommendation**: Clarify B3 as the minimal ContextScope (projections, monotonic tightening) and Phase 1b as the full implementation. Or collapse B3 into Phase 1b.

### F-13: P5 Not Enforced as Prerequisite for Phase 3a [MEDIUM]

PlanValidator depends on `dag_validator.py` (AD-L3-08), which depends on P5 (public topological sort). P5 is PREPARATORY, not BLOCKING.

**Recommendation**: Move P5 to blocking or note as hard prerequisite for Phase 3a.

### F-14: No Implementation Item for EATP Event System [MEDIUM]

AD-L3-07 decides L3 primitives emit governance events, with audit hooks translating to EATP records. But no work item defines the event types or implements the translators.

**Recommendation**: Add explicit work item in Phase 1a or Phase 2 for L3 governance event types + translator hooks.

---

## 4. Architecture Decision Risks

### F-15: threading.Lock vs asyncio.Queue — Mixed Paradigm [HIGH]

`threading.Lock.acquire()` from a coroutine blocks the event loop (not just the coroutine). If `AgentFactory.spawn()` is async and acquires a `threading.Lock`, the entire event loop blocks during the critical section. For cascade termination with async channel-close, this is problematic.

**Recommendation**: Use `asyncio.Lock` for async paths. Provide dual interfaces if both sync and async access is needed. Consider `janus` for dual-compatible primitives.

### F-16: fnmatch Treats \* as Matching Dots; Spec Says It Should Not [LOW]

`fnmatch.fnmatch("project.config.debug", "project.*")` returns True in Python, but the spec says `*` should NOT match across dots.

**Recommendation**: Use custom segment-based matcher (split on `.`, match per segment).

---

## 5. Cross-Primitive Integration

### F-17: Factory Spawn + Router Channel Creation Not Transactional [MEDIUM]

If spawn succeeds but channel creation fails, the child exists in registry with no channel and parent's budget is debited.

**Recommendation**: Make spawn + channel creation atomic. If channel creation fails, roll back (deregister, reclaim budget).

### F-18: PlanExecutor Missing Gradient Rule for Spawn Failure [MEDIUM]

Rules G1-G9 cover node success/failure/budget/envelope but not **spawn failure** (InsufficientBudget, MaxDepthExceeded, ToolNotInParent).

**Recommendation**: Add rule G10: SpawnFailure → Held (for budget failures, allow reallocation) or Blocked (for structural failures).

---

## 6. Python-Specific Concerns

### F-19: BudgetTracker Uses Integer Microdollars; L3 Specs Use Float [MEDIUM]

Existing BudgetTracker uses `int` microdollars (1 USD = 1M). L3 specs use `f64` floats. Conversion boundary introduces precision drift.

**Recommendation**: Document precision tolerance in conformance tests. Microdollar approach is sound — extend to EnvelopeTracker.

### F-20: frozen=True vs Mutable AgentInstance [LOW]

EATP conventions require `@dataclass`, PACT rules require `frozen=True`. But AgentInstance has mutable fields (state, active_envelope, budget_tracker).

**Recommendation**: Distinguish value types (frozen) from entity types (mutable). Document this convention.

---

## 7. EATP Record Completeness

### F-21: Zone Transition Records Not Clearly Mapped [MEDIUM]

Spec 01 says zone transitions create Audit Anchors, but the record mapping table only maps `record_consumption()` outcomes — not transitions as distinct events.

**Recommendation**: Clarify that `action_flagged`/`action_held` Audit Anchors ARE the zone transition records. Add `previous_zone` as mandatory field.

### F-22: Bridge EATP Records Have No Test Coverage [LOW]

Spec 03 includes bridge creation/teardown EATP records but no conformance test vector exercises bridges.

**Recommendation**: Add test vector for bridge messaging, or mark as future extension.

### F-23: B3 Should Not Be BLOCKING — It IS L3 Work [HIGH]

B3's acceptance criteria (monotonic tightening, parent traversal, namespaced writes) ARE Spec 02 requirements. B3's Phase 3 sequencing contradicts its BLOCKING status. If B3 blocks all L3, it creates a serialization bottleneck.

**Recommendation**: Downgrade B3 from BLOCKING to PREPARATORY. L3 primitives can use simplified context interface initially. Full ScopedContext is Phase 1b.

---

## Risk Register Summary

| ID   | Severity | Finding                                       | Recommendation                                    |
| ---- | -------- | --------------------------------------------- | ------------------------------------------------- |
| F-01 | CRITICAL | Verdict vs GradientZone type mismatch         | Define Verdict→GradientZone mapping in Spec 05    |
| F-06 | CRITICAL | No async message consumption model            | Add message processing architecture to Spec 03/04 |
| F-07 | CRITICAL | Cascade termination + spawn interleaving      | Block spawns during ancestor cascade              |
| F-02 | HIGH     | MessageType variant names mismatch            | Update B4 to match Brief 03's six variants        |
| F-03 | HIGH     | WaitReason missing ClarificationPending       | Add ClarificationPending + EscalationPending      |
| F-08 | HIGH     | Plan modification Draft transition undefined  | Clarify in-place re-validation for Executing      |
| F-12 | HIGH     | B3 scope confusion (blocking vs L3 spec)      | Separate B3-minimal from Spec 02-full             |
| F-15 | HIGH     | threading.Lock blocks asyncio event loop      | Use asyncio.Lock for async paths                  |
| F-23 | HIGH     | B3 should not be BLOCKING                     | Downgrade to PREPARATORY                          |
| F-04 | MEDIUM   | VerificationLevel vs GradientZone duplicate   | Reuse or alias existing enum                      |
| F-05 | MEDIUM   | Two AgentConfig classes — B1 target ambiguous | Specify kaizen/agent_config.py                    |
| F-09 | MEDIUM   | merge_child_results() undefined for failures  | Add edge case to Spec 02                          |
| F-10 | MEDIUM   | Split + allocate not atomic                   | Add composite or document rollback                |
| F-13 | MEDIUM   | P5 not enforced as Phase 3a prerequisite      | Move to blocking                                  |
| F-14 | MEDIUM   | No EATP event system implementation item      | Add to Phase 1a/2                                 |
| F-17 | MEDIUM   | Spawn + channel not transactional             | Make atomic or specify rollback                   |
| F-18 | MEDIUM   | No gradient rule for spawn failure            | Add rule G10                                      |
| F-19 | MEDIUM   | Float vs int microdollars conversion          | Document precision tolerance                      |
| F-21 | MEDIUM   | Zone transition EATP records unclear          | Clarify action records = transition records       |
| F-11 | LOW      | asyncio.Queue FIFO vs priority ordering       | Use PriorityQueue or document advisory            |
| F-16 | LOW      | fnmatch matches dots; spec says no            | Custom segment matcher                            |
| F-20 | LOW      | frozen=True vs mutable entities               | Distinguish value vs entity types                 |
| F-22 | LOW      | Bridge EATP records untested                  | Add test vector or mark future                    |
