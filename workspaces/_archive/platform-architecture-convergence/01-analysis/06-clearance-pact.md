# PACT Spec Conformance Analysis (Issues #380-#386)

**Complexity**: Moderate (score 16: Governance 7, Legal 2, Strategic 7)
**Total effort**: ~5-6 autonomous execution cycles
**Cross-SDK**: All 7 issues require matched kailash-rs issues per ADR-008

---

## Executive Summary

Seven PACT conformance gaps span two categories: six new contracts (N1-N6, #380-#385) that extend the governance layer with missing lifecycle gates, cache correctness, plan suspension, audit persistence, observation emission, and cross-implementation validation, plus one enum alignment (#386) that renames `AgentPosture` values to match canonical EATP posture names. The PACT code at `src/kailash/trust/pact/` is architecturally mature (thread-safe engine, fail-closed, bounded stores, NaN guards), so these are additive contracts rather than rewrites. SPEC-07 (ConstraintEnvelope convergence) and SPEC-08 (audit consolidation) from the existing workspace overlap with N4 and N5 -- those dependencies must be sequenced to avoid double-work.

---

## Per-Issue Analysis

### #380 -- PACT N1: KnowledgeFilter Contract (Pre-Retrieval Lifecycle Gate)

**What it requires**: A `KnowledgeFilter` protocol that sits between a knowledge retrieval request and the actual fetch, enforcing classification + compartment checks BEFORE data leaves the store. Today, `can_access()` in `access.py` checks access post-retrieval (the caller already has the `KnowledgeItem`). N1 demands a pre-retrieval gate: the filter receives a query intent, consults clearance, and either passes the query through or blocks it before any data is returned.

**Affected code**:

- `src/kailash/trust/pact/access.py` -- existing `can_access()` (5-step check) stays; new `KnowledgeFilter(Protocol)` added alongside it
- `src/kailash/trust/pact/engine.py` -- `GovernanceEngine` gains optional `knowledge_filter` parameter wired into `verify_action()` when context contains a retrieval intent
- `src/kailash/trust/pact/knowledge.py` -- `KnowledgeItem` unchanged; new `KnowledgeQuery` frozen dataclass (intent without data)
- `src/kailash/trust/pact/store.py` -- new `KnowledgeFilterStore(Protocol)` for persistent filter rules

**Complexity**: 1 cycle. New protocol + in-memory implementation + engine wiring + tests.
**Dependencies**: None from convergence workspace. Independent.
**Cross-SDK**: Protocol shape + `KnowledgeQuery` wire format must match Rust trait.

---

### #381 -- PACT N2: Effective Envelope Cache Correctness (5 Invalidation Properties)

**What it requires**: The effective envelope cache (currently `_effective_envelope_cache` OrderedDict in `engine.py`) must satisfy 5 properties: (1) invalidation on role envelope mutation, (2) invalidation on task envelope mutation, (3) invalidation on ancestor envelope mutation, (4) bounded staleness (TTL), (5) cross-thread visibility (no stale reads after mutation). Today the engine holds a `_lock` around all mutations and cache lookups, which satisfies property 5 by serialization. Properties 1-3 are partially implemented -- `set_role_envelope()` and `set_task_envelope()` clear the cache, but ancestor changes (via `set_role_envelope` on a parent address) do NOT cascade invalidation to descendant entries.

**Affected code**:

- `src/kailash/trust/pact/engine.py` -- `_effective_envelope_cache` management in `set_role_envelope()`, `set_task_envelope()`, `_compute_envelope_with_version_locked()`. Must add prefix-based invalidation: when address `D:engineering` changes, all cache entries starting with `D:engineering` must be evicted.
- `src/kailash/trust/pact/envelopes.py` -- `compute_effective_envelope_with_version()` already produces a version hash; the cache must compare version hashes on read to detect stale entries (TTL + version check).

**Complexity**: 0.5 cycle. The lock already provides thread safety. Main work is prefix invalidation + TTL + regression tests.
**Dependencies**: None from convergence workspace.
**Cross-SDK**: Cache semantics must match (same 5 invariants) but implementation may differ.

---

### #382 -- PACT N3: Plan Re-Entry Guarantee (4 Suspension Triggers)

**What it requires**: When an agent's plan execution is suspended (budget exhaustion, temporal window close, posture downgrade, or envelope tightening), the plan state must be preserved and re-enterable when conditions change. Today `verify_action()` returns a BLOCKED verdict on vacancy/envelope failure, but there is no plan suspension/resume protocol. The 4 triggers:

1. **Budget exhaustion** -- `BudgetTracker` signals exhaustion (connects to SPEC-08 TASK-08-20)
2. **Temporal window close** -- `TemporalConstraintConfig.active_hours` window expires
3. **Posture downgrade** -- `PostureStateMachine.emergency_downgrade()` fires
4. **Envelope tightening** -- runtime `intersect_envelopes()` narrows mid-execution

**Affected code**:

- `src/kailash/trust/pact/engine.py` -- new `suspend_plan()` / `resume_plan()` methods; `verify_action()` returns `HELD` (not BLOCKED) with `suspension_token` when a resumable condition triggers
- `src/kailash/trust/pact/context.py` -- `GovernanceContext` gains `suspended_plans: frozenset[str]` for the agent to inspect
- New file: `src/kailash/trust/pact/suspension.py` -- `PlanSuspension` frozen dataclass (`plan_id`, `trigger`, `snapshot`, `resume_conditions`)
- `src/kailash/trust/pact/store.py` -- `SuspensionStore(Protocol)` + `MemorySuspensionStore`

**Complexity**: 1.5 cycles. Requires careful state machine design: suspension is NOT a permanent block, and the resume path must re-verify all conditions.
**Dependencies**: SPEC-08 TASK-08-18..20 (BudgetTracker wiring) must land first for trigger 1.
**Cross-SDK**: Suspension wire format + trigger enum must match Rust.

---

### #383 -- PACT N4: Audit Durability Tiers (Gradient-Aligned Persistence)

**What it requires**: Audit records at different verification levels have different durability requirements. AUTO_APPROVED may use in-memory with periodic flush. FLAGGED must be persisted within 1 second. HELD and BLOCKED must be synchronously persisted before the verdict is returned. Today, `AuditChain.append()` in `audit.py` is in-memory only (bounded deque); the SQLite `SqliteAuditLog` in `stores/sqlite.py` is synchronous but is not tiered by verification level.

**Affected code**:

- `src/kailash/trust/pact/audit.py` -- `AuditChain` gains a `durability_tier` dispatch: AUTO_APPROVED goes to in-memory buffer, FLAGGED to async flush queue, HELD/BLOCKED to synchronous SQLite
- `src/kailash/trust/pact/stores/sqlite.py` -- `SqliteAuditLog` extended with flush queue for FLAGGED tier
- `src/kailash/trust/pact/engine.py` -- `_emit_audit_unlocked()` passes verification level to the chain

**Complexity**: 1 cycle. Main risk is the async flush queue for FLAGGED tier (threading + crash recovery).
**Dependencies**: Overlaps with SPEC-08 (audit consolidation). SPEC-08 creates the canonical `AuditStore` with `InMemoryAuditStore` and `SqliteAuditStore`. N4 should build ON TOP of SPEC-08's canonical store, adding tiered dispatch. Sequence: SPEC-08 first, then N4.
**Cross-SDK**: Tier definitions (which levels get which durability) must match Rust. Persistence format already covered by SPEC-08 cross-SDK vectors.

---

### #384 -- PACT N5: ObservationSink Contract (Structured Evidence Emission)

**What it requires**: A `ObservationSink(Protocol)` that receives structured evidence from the governance layer -- gradient evaluation results, constraint dimension checks, access decisions -- as typed events. Today the engine emits audit anchors (string-based action + metadata dict) but does not emit structured observation records that monitoring systems can consume for posture evaluation.

**Affected code**:

- New file: `src/kailash/trust/pact/observation.py` -- `ObservationSink(Protocol)`, `ObservationEvent` frozen dataclass (`event_type: ObservationType`, `role_address`, `action`, `dimension_results`, `verdict`, `timestamp`, `metadata`)
- `src/kailash/trust/pact/engine.py` -- `GovernanceEngine.__init__` gains `observation_sink: ObservationSink | None`; `_verify_action_locked()` emits observations after verdict
- `src/kailash/trust/posture/postures.py` -- `PostureEvidence` can be constructed from `ObservationEvent` aggregations (bridge between N5 and existing posture evaluation)

**Complexity**: 0.75 cycle. New protocol + event types + engine wiring. Consumption by `PostureStateMachine` is a follow-up integration.
**Dependencies**: None from convergence workspace. The `PactEatpEmitter` protocol in `eatp_emitter.py` is a related pattern but different scope (EATP chain records vs observation events).
**Cross-SDK**: `ObservationType` enum values + `ObservationEvent` wire format must match Rust.

---

### #385 -- PACT N6: Cross-Implementation Conformance (Shared Schema and Test Suite)

**What it requires**: A machine-readable PACT conformance schema (JSON Schema or similar) and a shared test suite that both Python and Rust implementations run against. The schema covers: D/T/R address format, envelope field names + types, verification level names, audit action names, and wire formats for all cross-boundary types.

**Affected code**:

- New directory: `tests/cross_sdk/pact/` -- conformance test vectors (JSON fixtures)
- New file: `tests/cross_sdk/pact/test_pact_conformance.py` -- Python-side runner
- New file: `tests/cross_sdk/pact/pact_schema.json` -- JSON Schema for envelope wire format, audit event format, address grammar
- `src/kailash/trust/pact/envelopes.py` -- may need `to_wire_dict()` / `from_wire_dict()` separate from `to_dict()` if wire format differs from internal representation

**Complexity**: 1 cycle. Mostly fixture authoring + test writing. Must coordinate with kailash-rs for fixture agreement.
**Dependencies**: Benefits from SPEC-08 TASK-08-27 (audit event cross-SDK vectors) and SPEC-09 (cross-SDK validation phase). Should run during or after Phase 6.
**Cross-SDK**: This IS the cross-SDK validation -- both repos consume the same fixtures.

---

### #386 -- Align AgentPosture Enum with Canonical EATP Posture Names (Decision 007)

**What it requires**: The `AgentPosture` enum in `src/kailash/trust/envelope.py` (values: `pseudo_agent`, `supervised`, `shared_planning`, `continuous_insight`, `delegated`) must align with EATP canonical posture names from Decision 007. The existing `TrustPosture` enum in `posture/postures.py` uses the SAME values, so the question is whether Decision 007 changes those names.

**Current state**: Three posture enums exist:

1. `TrustPosture` at `src/kailash/trust/posture/postures.py` -- the primary posture enum (5 levels)
2. `AgentPosture` at `src/kailash/trust/envelope.py` -- posture ceiling on constraint envelopes (same 5 values)
3. `TrustPostureLevel` at `src/kailash/trust/pact/config.py` -- alias for `TrustPosture`

If Decision 007 renames any of the 5 posture names, ALL three must be updated atomically with backward-compat aliases.

**Affected code**:

- `src/kailash/trust/envelope.py` line 549 -- `AgentPosture` enum
- `src/kailash/trust/posture/postures.py` line 21 -- `TrustPosture` enum
- `src/kailash/trust/pact/config.py` line 36 -- `TrustPostureLevel` alias
- `src/kailash/trust/pact/envelopes.py` -- uses `TrustPostureLevel` for envelope posture defaults
- `src/kailash/trust/pact/clearance.py` -- `POSTURE_CEILING` mapping
- All tests referencing posture string values

**Complexity**: 0.5 cycle if value names change; 0.25 cycle if only the enum class unification is needed (making `AgentPosture` an alias for `TrustPosture` rather than a separate enum).
**Dependencies**: Convergence TASK-CC-08 already checks "AgentPosture exists at `kailash.trust.posture.AgentPosture`" and "posture_ceiling on envelope". This issue formalizes the name alignment.
**Cross-SDK**: Posture string values are wire-format -- any rename requires matched Rust change.

---

## Risk Register

| Risk                                                                      | Likelihood | Impact | Mitigation                                                                                               |
| ------------------------------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------------------------------------------- |
| N3 (plan re-entry) under-scoped -- resumption may need saga-like rollback | HIGH       | HIGH   | Design suspension as frozen snapshot with explicit resume preconditions; do NOT attempt automatic replay |
| N4 (audit tiers) crash during FLAGGED flush loses records                 | MEDIUM     | HIGH   | WAL mode + fsync for FLAGGED tier; bounded in-memory buffer with overflow-to-sync fallback               |
| N2 (cache invalidation) prefix eviction performance on large orgs         | MEDIUM     | MEDIUM | LRU eviction already bounded at 10k entries; prefix scan is O(cache_size) which is bounded               |
| #386 posture rename breaks wire compatibility                             | HIGH       | HIGH   | Backward-compat: accept old names via `_missing_()` on enum; emit new names; deprecation period          |
| SPEC-08 / N4 ordering conflict                                            | MEDIUM     | MEDIUM | N4 MUST wait for SPEC-08 audit consolidation; add explicit dependency in todo                            |

## Convergence Workspace Overlap

| PACT Issue           | Convergence Task                               | Overlap                                            | Resolution                                                                   |
| -------------------- | ---------------------------------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------- |
| N4 (Audit Tiers)     | SPEC-08 (audit consolidation)                  | N4 builds atop SPEC-08's canonical AuditStore      | Sequence: SPEC-08 first; N4 adds tiered dispatch as follow-on                |
| N5 (ObservationSink) | SPEC-08 TASK-08-24 (registry audit logging)    | Both emit structured events but to different sinks | Keep separate: audit store for compliance, observation sink for monitoring   |
| #386 (AgentPosture)  | TASK-CC-08 check #7 (AgentPosture exists)      | CC-08 verifies; #386 implements                    | #386 lands before CC-08 runs                                                 |
| N3 (Plan Re-Entry)   | SPEC-08 TASK-08-18..20 (BudgetTracker)         | Budget exhaustion is one of N3's 4 triggers        | SPEC-08 budget work first; N3 consumes the exhaustion signal                 |
| N6 (Conformance)     | SPEC-09 (Cross-SDK validation), CC-06 (CI job) | N6 is PACT-specific instance of SPEC-09            | N6 fixtures live in `tests/cross_sdk/pact/`; SPEC-09 provides the CI harness |

## Implementation Sequence

```
Phase 5a (SPEC-08 audit consolidation)
    |
    v
#381 N2 (cache correctness) ──> Independent, can run anytime
#380 N1 (KnowledgeFilter) ──> Independent, can run anytime
#386 (AgentPosture alignment) ──> Should run early (wire format)
    |
    v
#383 N4 (audit tiers) ──> After SPEC-08
#384 N5 (ObservationSink) ──> After N1 and N2 (consumes their contracts)
#382 N3 (plan re-entry) ──> After SPEC-08 budget tasks
    |
    v
#385 N6 (conformance suite) ──> After all above (validates them)
```

**Recommended grouping**: N1 + N2 + #386 as a first batch (independent, 2 cycles); N4 + N5 after SPEC-08 (1.75 cycles); N3 after budget tasks (1.5 cycles); N6 as validation (1 cycle).

## Success Criteria

- [ ] `KnowledgeFilter(Protocol)` blocks retrieval before data leaves store
- [ ] Effective envelope cache passes 5 invalidation property tests (including ancestor cascade)
- [ ] Plan suspension/resume round-trips through all 4 trigger types
- [ ] HELD/BLOCKED audit records persisted synchronously before verdict return
- [ ] `ObservationSink` receives typed events for every `verify_action()` call
- [ ] Shared PACT conformance fixtures pass in both Python and Rust CI
- [ ] `AgentPosture` values match canonical EATP posture names per Decision 007
- [ ] All existing ~3,000 tests pass (zero regressions)
- [ ] 7 matched cross-SDK issue pairs filed on kailash-rs
