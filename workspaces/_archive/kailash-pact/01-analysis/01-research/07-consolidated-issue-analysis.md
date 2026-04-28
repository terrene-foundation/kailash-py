# Consolidated Issue Analysis: kailash-py Issues #59-68

**Date**: 2026-03-24
**Complexity Score**: 26 (Complex -- Governance: 10, Legal: 2, Strategic: 14)
**Analyst**: deep-analyst

## Executive Summary

Nine open issues span three packages (kaizen-agents, kailash-pact, kailash core) with a clear dependency bottleneck: **Issue #63 (governance file migration)** is the structural linchpin that blocks #64 (PactEngine) and should be sequenced carefully. The issues decompose into three independent work streams that can be parallelized, plus two gated sequences that require specific ordering. One-session feasibility is achievable for Groups A+B+E+F but NOT for the full set including #63 and #64.

---

## 1. Per-Issue Complexity Assessment

### Group A: Quick Bug Fixes (kaizen-agents)

#### Issue #68 -- Session files world-readable

| Dimension        | Score   | Rationale                                                                             |
| ---------------- | ------- | ------------------------------------------------------------------------------------- |
| **Complexity**   | Trivial | Single `os.chmod()` call after `path.write_text()`                                    |
| **Risk**         | Minor   | Security defect -- session files contain conversation history, API keys in usage data |
| **Blast radius** | 1 file  | `session.py` line 99, plus POSIX guard                                                |

**Source evidence**: `SessionManager.save_session()` at line 99 calls `path.write_text(...)` with no subsequent permission restriction. The `fork_session()` method at line 194 has the same issue via `dest_path.write_text(...)`. The `auto_save()` method delegates to `save_session()` so it inherits the fix.

**Implementation**:

- Add `os.chmod(path, 0o600)` after each `write_text()` call (lines 99, 194)
- Must handle Windows gracefully (POSIX-only guard: `if hasattr(os, 'chmod')` or `sys.platform != 'win32'`)
- Affects: `save_session()`, `fork_session()`, `_session_path()` (directory creation at line 37 should also use `mode=0o700`)

**Hidden complexity**: The `mkdir(parents=True, exist_ok=True)` at line 37 does not restrict directory permissions. Sessions directory itself should be `0o700`. This is a second fix point the issue description does not mention.

**Estimated effort**: 15 minutes.

---

#### Issue #67 -- Clearance 'restricted' maps to C1_INTERNAL instead of C2_CONFIDENTIAL

| Dimension        | Score          | Rationale                                                                                                     |
| ---------------- | -------------- | ------------------------------------------------------------------------------------------------------------- |
| **Complexity**   | Trivial        | One-line dict value change                                                                                    |
| **Risk**         | Significant    | **Semantic security defect** -- users setting `data_clearance="restricted"` get LOWER clearance than intended |
| **Blast radius** | 1 line + tests | `supervisor.py` line 113, plus any tests asserting the old mapping                                            |

**Source evidence**: `_CLEARANCE_MAP` at line 110-117 maps `"restricted"` to `DataClassification.C1_INTERNAL`. The `kailash.trust.reasoning.traces.ConfidentialityLevel` enum defines RESTRICTED as level 1 (between PUBLIC=0 and CONFIDENTIAL=2). The `pact.governance.config` module imports `ConfidentialityLevel` from `kailash.trust` which has `RESTRICTED` at ordering 1. The mapping should be `C2_CONFIDENTIAL` to match PACT's interpretation where "restricted" means confidential-tier data.

**Risk analysis**: This is a data exposure defect. An agent configured with `data_clearance="restricted"` currently sees C1_INTERNAL data (one level above public) when it should see up to C2_CONFIDENTIAL. The effect is over-restriction (agent sees LESS data than intended), not under-restriction, so this is a usability bug rather than a security breach. However, the semantic mismatch between kaizen-agents and PACT is a governance integrity issue.

**Cross-reference with issue #60**: This mapping uses the local `DataClassification` enum (IntEnum, C0-C4). When #60 replaces it with `kailash.trust.ConfidentialityLevel` (str Enum, PUBLIC/RESTRICTED/CONFIDENTIAL/SECRET/TOP_SECRET), the mapping key "restricted" should map to `ConfidentialityLevel.RESTRICTED` directly -- which resolves this issue automatically. **If #60 is done first, #67 becomes a no-op.**

**Estimated effort**: 5 minutes standalone, 0 minutes if sequenced after #60.

---

### Group B: Type Alignment (kaizen-agents to kailash.trust / kailash-pact)

#### Issue #60 -- Import ConfidentialityLevel from kailash.trust

| Dimension        | Score                      | Rationale                                                                          |
| ---------------- | -------------------------- | ---------------------------------------------------------------------------------- |
| **Complexity**   | Moderate                   | Type system migration across 12+ files with semantic differences                   |
| **Risk**         | Major                      | Two different `ConfidentialityLevel` types exist with DIFFERENT value systems      |
| **Blast radius** | 12+ files in kaizen-agents | All files importing `DataClassification` from `kaizen_agents.governance.clearance` |

**Source evidence -- the type mismatch**:

1. **Local type** (`kaizen_agents.governance.clearance.DataClassification`): `IntEnum` with values `C0_PUBLIC=0, C1_INTERNAL=1, C2_CONFIDENTIAL=2, C3_SECRET=3, C4_TOP_SECRET=4`. Compared with `<=` and `>=` operators via IntEnum.

2. **kailash.trust type** (`kailash.trust.reasoning.traces.ConfidentialityLevel`): `Enum` (str-backed) with values `PUBLIC="public", RESTRICTED="restricted", CONFIDENTIAL="confidential", SECRET="secret", TOP_SECRET="top_secret"`. Compared with custom `__lt__`, `__le__`, `__gt__`, `__ge__` methods via `_CONFIDENTIALITY_ORDER` dict.

**Critical differences**:

- The local `DataClassification` has `C1_INTERNAL` -- the kailash.trust type has `RESTRICTED` instead. These are NOT semantically equivalent.
- The local type is IntEnum (direct numeric comparison); the trust type is str Enum (comparison via lookup table).
- The local type uses `C0_`, `C1_`, `C2_`, `C3_`, `C4_` prefixes; the trust type uses plain names.

**Affected files** (from grep analysis):

- `kaizen_agents/governance/clearance.py` -- defines `DataClassification`, used in `ClearanceEnforcer`, `ClassificationAssigner`, `ClassifiedValue`, and `_PREFILTER_PATTERNS`
- `kaizen_agents/supervisor.py` -- imports `DataClassification`, uses it in `_CLEARANCE_MAP` and `clearance_level` property
- `kaizen_agents/governance/__init__.py` -- re-exports `DataClassification`
- `kaizen_agents/orchestration/context/_scope_bridge.py` -- uses a DIFFERENT `DataClassification` (from `kaizen.l3.context.types`)
- 8+ test files importing `DataClassification`

**Root cause (5-Why)**:

1. Why is there a local `DataClassification`? Because kaizen-agents was built before kailash.trust had the equivalent type.
2. Why wasn't it replaced when kailash.trust added `ConfidentialityLevel`? Because the two types have different member names (C1_INTERNAL vs RESTRICTED).
3. Why do the member names differ? Because kailash.trust uses CARE terminology (PUBLIC/RESTRICTED/CONFIDENTIAL/SECRET/TOP_SECRET) while kaizen-agents used ISO 27001-style labels (C0-C4).
4. Why does it matter? Because `isinstance()` checks, pattern matching, and serialized values will break if the types are mixed.
5. Why fix now? Because issue #64 (PactEngine) needs a unified type system across all packages.

**Migration plan**:

1. Create a compatibility layer: `DataClassification` as an alias or adapter to `ConfidentialityLevel`
2. Update all comparison logic (IntEnum `<=` to custom `__le__`)
3. Update all `C0_PUBLIC` references to `PUBLIC`, `C1_INTERNAL` to `RESTRICTED`, etc.
4. Update `_PREFILTER_PATTERNS` list type annotations
5. Update `_CLEARANCE_MAP` in supervisor.py
6. Update all test assertions

**Estimated effort**: 2-3 hours (moderate refactor across many files with test updates).

---

#### Issue #59 -- Import ConstraintEnvelopeConfig from kailash-pact

| Dimension        | Score                      | Rationale                                                                                                                                                 |
| ---------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Complexity**   | Significant                | Structural type replacement with fundamentally different data model                                                                                       |
| **Risk**         | Major                      | Local `ConstraintEnvelope` is a frozen dataclass with dict fields; PACT's `ConstraintEnvelopeConfig` is a Pydantic BaseModel with nested typed sub-models |
| **Blast radius** | 20+ files in kaizen-agents | Every file that uses `ConstraintEnvelope` from `kaizen_agents.types`                                                                                      |

**Source evidence -- the type mismatch**:

1. **Local type** (`kaizen_agents.types.ConstraintEnvelope`): Frozen `@dataclass` with 5 `dict[str, Any]` fields (`financial`, `operational`, `temporal`, `data_access`, `communication`). Financial limit accessed as `env.financial.get("limit", 0.0)`. No validation beyond NaN check on `financial.limit` and `temporal.limit_seconds`.

2. **PACT type** (`pact.governance.config.ConstraintEnvelopeConfig`): Pydantic `BaseModel` (frozen) with typed sub-models (`FinancialConstraintConfig`, `OperationalConstraintConfig`, etc.). Financial limit accessed as `env.financial.max_spend_usd`. Full Pydantic validation. Has `id`, `description`, `confidentiality_clearance` fields not present in the local type.

**Critical differences**:

- Access patterns: `env.financial["limit"]` vs `env.financial.max_spend_usd`
- The local type stores raw dicts; the PACT type uses structured Pydantic sub-models
- The PACT type has `id`, `description`, `confidentiality_clearance`, `max_delegation_depth` -- fields the local type lacks
- The PACT type serializes via `.model_dump()` not `to_dict()`
- The local type allows arbitrary keys in dimension dicts; PACT type does not

**Affected files** (from grep): `types.py`, `supervisor.py`, `envelope_allocator.py`, `_message_transport.py`, `_sdk_compat.py`, `_agent_lifecycle.py`, `decomposer.py`, `designer.py`, `composer.py`, `monitor.py`, `delegation.py`, plus 10+ test files.

**This is NOT a simple import swap.** Every access pattern changes. The `_envelope_to_dict()` helper in `supervisor.py` (line 671-679) and every place that constructs `ConstraintEnvelope(financial={"limit": ...})` must be rewritten to use `ConstraintEnvelopeConfig(financial=FinancialConstraintConfig(max_spend_usd=...))`.

**Migration strategy options**:

1. **Big bang**: Replace all at once. High risk, high reward.
2. **Adapter pattern**: Create `ConstraintEnvelope` as a thin adapter over `ConstraintEnvelopeConfig`. Lower risk but adds a layer.
3. **Progressive**: Replace in stages, starting with supervisor.py, then orchestration, then tests.

**Recommended**: Option 3 (progressive). Start with a compatibility function `local_to_pact_envelope()` and `pact_to_local_envelope()`, then progressively eliminate the local type.

**Estimated effort**: 4-6 hours (significant refactor).

---

### Group C: Feature Additions (kaizen-agents)

#### Issue #61 -- External HELD mechanism for GovernedSupervisor

| Dimension        | Score                                    | Rationale                                                                                 |
| ---------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Complexity**   | Moderate                                 | New async coordination mechanism (pause/resume) in execution loop                         |
| **Risk**         | Significant                              | Affects the core execution loop; incorrect implementation can deadlock or lose plan state |
| **Blast radius** | supervisor.py + new hold_resolver module | `run()` method, `run_plan()` method, plan execution loop                                  |

**Source evidence**: The `run()` method (lines 249-417) currently checks budget exhaustion for HELD state (line 321) but has NO mechanism for external holds (human-in-the-loop approval, external system gates). When a node is HELD, it simply `continue`s to the next node. There is no way to resume a held node.

**What's needed**:

1. A `resolve_hold(node_id, decision)` method on GovernedSupervisor
2. An async wait mechanism in the execution loop (when a node is HELD, the loop should await resolution rather than skip)
3. A `HoldResolution` type (APPROVE / REJECT / MODIFY)
4. Integration with the `PlanGradient.after_retry_exhaustion` which already specifies `GradientZone.HELD`
5. Timeout handling per `PlanGradient.resolution_timeout`

**Risk factors**:

- The current execution loop is sequential (for-loop over ready nodes). HELD nodes need async waiting without blocking other ready nodes.
- Plan state must be persisted through the hold period (currently all in-memory).
- The `_ReadOnlyView` pattern means external callers cannot mutate the supervisor -- the resolution API must be on the supervisor itself, not the subsystem views.

**Estimated effort**: 3-4 hours.

---

#### Issue #66 -- LLM token cost model for BudgetTracker

| Dimension        | Score                                                   | Rationale                                                                          |
| ---------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Complexity**   | Moderate                                                | New cost model module + integration points in supervisor and loop                  |
| **Risk**         | Minor                                                   | Additive feature; existing budget tracking is unaffected if cost model is optional |
| **Blast radius** | budget.py + supervisor.py + loop.py + new cost_model.py | 3-4 files modified, 1 new file                                                     |

**Source evidence**: `BudgetTracker` (budget.py) tracks raw `float` amounts. The `AgentLoop` (loop.py) uses `UsageTracker` for token counts but has NO cost calculation. The `GovernedSupervisor.run()` accepts `cost` from the executor callback (line 342) but there's no bridge from token usage to dollar cost.

**What's needed**:

1. A `CostModel` class that maps (model_name, prompt_tokens, completion_tokens) -> cost_usd
2. Integration in `GovernedSupervisor.run()` to auto-compute cost from token usage when no explicit cost is provided
3. Integration in `AgentLoop` (loop.py) to report cost after each LLM call
4. A registry of model pricing (configurable, with sensible defaults for major models)

**Risk factors**:

- Model pricing changes frequently -- must be configurable, not hardcoded
- The cost model must handle NaN/Inf (per pact-governance.md rule 6)
- Must not break the existing `cost` field in executor callback (backward compatible)

**Estimated effort**: 2-3 hours.

---

### Group D: Structural Refactor

#### Issue #63 -- Move governance files to src/kailash/trust/pact/

| Dimension        | Score                               | Rationale                                                                     |
| ---------------- | ----------------------------------- | ----------------------------------------------------------------------------- |
| **Complexity**   | Major                               | 33 Python files, 200+ import statements, re-export layer, version bump, tests |
| **Risk**         | Critical                            | Every downstream consumer of `pact.governance` breaks if re-exports are wrong |
| **Blast radius** | ENTIRE pact package + all importers | 33 source files move, 200+ imports change, kailash-pact **init**.py rewrite   |

**Source evidence**: `packages/kailash-pact/src/pact/governance/` contains 33 Python files (including `api/` subdirectory with 6 files, `stores/` subdirectory with 3 files). These files are imported by:

- All `pact.governance.*` test files
- `kaizen-agents` (via `pact.governance.config.ConstraintEnvelopeConfig` in engine.py)
- Any external consumer of `kailash-pact`

**The move**: `packages/kailash-pact/src/pact/governance/*.py` -> `src/kailash/trust/pact/*.py`

**Why this is the hardest issue**:

1. **33 files to move** with internal cross-imports (e.g., `from pact.governance.config import ConstraintEnvelopeConfig` appears in engine.py, envelopes.py, etc.)
2. **All internal imports change**: `from pact.governance.X import Y` becomes `from kailash.trust.pact.X import Y`
3. **Re-export layer required**: `pact.governance` must re-export everything from `kailash.trust.pact` for backward compatibility
4. **Package boundary change**: These files move from the `kailash-pact` package to the `kailash` core package
5. **pyproject.toml changes**: Both `kailash` and `kailash-pact` pyproject.toml files need updating
6. **`src/kailash/trust/pact/` does not exist yet** (confirmed by glob -- no results)
7. **Test imports**: All pact governance tests need updating

**Risk factors**:

- **Circular dependency risk**: `kailash.trust.pact.config` imports from `kailash.trust` (ConfidentialityLevel, TrustPosture). If `kailash.trust.__init__` tries to import from `kailash.trust.pact`, circular import.
- **Package installation order**: After the move, `kailash-pact` depends on `kailash[trust]` for the governance primitives. This is the intended direction but must be validated.
- **Version coordination**: kailash core gets a minor bump; kailash-pact gets a MAJOR bump (v0.4.0) since the public API location changes.

**5-Why root cause**:

1. Why move? Because governance primitives (envelopes, addressing, clearance) belong in the trust layer, not the pact package.
2. Why now? Because #64 (PactEngine) needs a clean separation between primitives (trust layer) and engine (pact package).
3. Why is it risky? Because every import path changes and the re-export layer is the sole backward-compatibility mechanism.
4. Why not just add aliases? Because the goal is to make kailash core self-sufficient for governance primitives without requiring kailash-pact.
5. Why does sequencing matter? Because #59, #60, and #64 all depend on where these types live.

**Estimated effort**: 6-10 hours (one full autonomous session, possibly two).

---

### Group E: New Package (PactEngine)

#### Issue #64 -- Build PactEngine facade

| Dimension        | Score                                                               | Rationale                                                                       |
| ---------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Complexity**   | Major                                                               | New facade bridging Trust Plane and Execution Plane; progressive disclosure API |
| **Risk**         | Significant                                                         | Architectural centerpiece -- wrong design forces refactor of everything above   |
| **Blast radius** | New module + integration with GovernedSupervisor + GovernanceEngine | kailash-pact v0.4.0                                                             |

**Depends on**: #59 (type alignment), #60 (ConfidentialityLevel), #61 (HELD mechanism), #63 (file migration).

**What PactEngine must do**:

1. Bridge `GovernanceEngine` (pact) with `GovernedSupervisor` (kaizen-agents)
2. Provide Layer 1/2/3 progressive disclosure (like GovernedSupervisor does for L3)
3. Translate between PACT's Pydantic-based `ConstraintEnvelopeConfig` and kaizen-agents' dataclass-based `ConstraintEnvelope`
4. Unify `DataClassification` (kaizen) with `ConfidentialityLevel` (trust)
5. Wire HELD mechanism to GovernanceEngine's `verify_action()` HELD verdicts

**This issue cannot start until #63 completes** because PactEngine needs to import from the new `kailash.trust.pact` location.

**Estimated effort**: 6-8 hours.

---

### Group F: Stub Removal

#### Issue #65 -- /plan and /compact stubs

| Dimension        | Score                                | Rationale                                                                                  |
| ---------------- | ------------------------------------ | ------------------------------------------------------------------------------------------ |
| **Complexity**   | Moderate                             | Two command handlers need real implementations, not just stub removal                      |
| **Risk**         | Minor                                | Stubs are user-visible (CLI commands return "not yet connected") but not security-critical |
| **Blast radius** | builtins.py + new integration points | 2 handlers + wiring to PlanMonitor and context compaction                                  |

**Source evidence**:

- `_plan_handler` (line 172-177): Returns `"Plan mode not yet connected. Objective received: {args}"`. This is a textbook stub violating `rules/no-stubs.md`.
- `_compact_handler` (line 180-195): Returns `"Context compaction not yet connected."` after computing token estimates. Partial implementation (token counting works, compaction does not).

**What's needed for /plan**:

- Wire to `PlanMonitor` or `GovernedSupervisor` for plan decomposition
- This couples to issue #61 (HELD mechanism) if plans can be held

**What's needed for /compact**:

- Implement context compaction (summarize old messages, keep system prompt + recent)
- This is a standalone feature within the `AgentLoop` / `Conversation` class

**Estimated effort**: 3-4 hours (2h for /compact which is self-contained, 1-2h for /plan which depends on orchestration layer).

---

## 2. Risk Register

| ID  | Issue | Risk                                                                                | Likelihood | Impact      | Mitigation                                                                                                                                            |
| --- | ----- | ----------------------------------------------------------------------------------- | ---------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | #63   | Circular imports between `kailash.trust` and `kailash.trust.pact`                   | High       | Critical    | Design import graph BEFORE moving files; `kailash.trust.pact.config` imports from `kailash.trust.reasoning.traces`, NOT from `kailash.trust.__init__` |
| R2  | #63   | Broken re-exports in `pact.governance.__init__`                                     | High       | Critical    | Automated test: `from pact.governance import X` must work for every symbol in current `__all__`                                                       |
| R3  | #59   | Access pattern breakage (`env.financial["limit"]` vs `env.financial.max_spend_usd`) | Certain    | Major       | Grep for ALL dict-style accesses before migration; create adapter functions                                                                           |
| R4  | #60   | `DataClassification.C1_INTERNAL` has no equivalent in `ConfidentialityLevel`        | Certain    | Major       | Map C1_INTERNAL -> RESTRICTED with explicit documentation; audit all code paths                                                                       |
| R5  | #64   | PactEngine design wrong, forcing rework of #59/#60                                  | Medium     | Major       | Write PactEngine interface spec BEFORE implementing #59/#60 so type decisions align                                                                   |
| R6  | #61   | HELD mechanism deadlocks execution loop                                             | Medium     | Significant | Use `asyncio.Event` or `asyncio.Queue` for hold resolution; add timeout                                                                               |
| R7  | #67   | Fixing clearance mapping before #60 creates a fix that gets overwritten             | Low        | Minor       | Sequence #60 before #67, or accept the double-touch                                                                                                   |
| R8  | #68   | `os.chmod` on Windows raises errors                                                 | Low        | Minor       | Guard with platform check                                                                                                                             |
| R9  | #65   | /plan stub removal requires orchestration layer not yet built                       | Medium     | Significant | Implement /compact first (standalone); defer /plan until #61 is done                                                                                  |
| R10 | #66   | Hardcoded model pricing becomes stale                                               | Low        | Minor       | Use configurable cost table with sane defaults; document update process                                                                               |

---

## 3. Dependency Analysis

### True Dependencies (must be sequenced)

```
#63 (file migration) -----> #64 (PactEngine)
                              ^
                              |
#59 (ConstraintEnvelope) ----+
#60 (ConfidentialityLevel) --+
#61 (HELD mechanism) --------+
```

**#64 is the terminal node** with four hard dependencies.

### Soft Dependencies (beneficial but not required)

```
#60 (ConfidentialityLevel) --soft--> #67 (clearance mapping)
    If #60 is done first, #67 is resolved automatically.

#61 (HELD mechanism) --soft--> #65 (/plan command)
    /plan needs HELD support for governance-aware planning.

#66 (cost model) --soft--> #61 (HELD mechanism)
    HELD-on-budget-exhaustion benefits from accurate cost tracking.
```

### Fully Independent (can run in parallel)

```
[Stream 1] #68 (session chmod)     -- no dependencies
[Stream 2] #66 (cost model)        -- no hard dependencies
[Stream 3] #65 /compact portion    -- no dependencies
```

---

## 4. Reordering and Parallelization

### Optimal Execution Order

**Phase 1 -- Parallel Quick Fixes** (30 minutes total)

| Stream | Issue                                      | Time      |
| ------ | ------------------------------------------ | --------- |
| A      | #68 (session chmod)                        | 15 min    |
| B      | #66 (cost model -- can start, no blockers) | 2-3 hours |
| C      | #65 /compact only                          | 2 hours   |

**Phase 2 -- Type Alignment** (4-6 hours, sequential)

1. **#60** first (ConfidentialityLevel) -- resolves #67 as side effect
2. **#59** second (ConstraintEnvelopeConfig) -- benefits from #60 being done
3. Verify #67 is resolved; if not, apply the one-line fix

**Rationale for #60 before #59**: The ConfidentialityLevel migration is simpler (enum swap with name changes) and informs the ConstraintEnvelope migration (which needs to know what ConfidentialityLevel looks like in the new world).

**Phase 3 -- Feature: HELD Mechanism** (3-4 hours)

4. **#61** (external HELD) -- requires #59/#60 for type consistency but could start with local types

**Phase 4 -- Structural Migration** (6-10 hours)

5. **#63** (governance file migration) -- the big move

**Phase 5 -- PactEngine** (6-8 hours)

6. **#64** (PactEngine facade) -- depends on everything above
7. **#65** /plan portion -- can be wired once PactEngine exists

### What Can Be Deferred

| Issue            | Can Defer? | Rationale                                                   |
| ---------------- | ---------- | ----------------------------------------------------------- |
| #64 (PactEngine) | Yes        | It's the v0.4.0 deliverable. If #63 isn't ready, #64 waits. |
| #65 /plan        | Yes        | Depends on orchestration; /compact can ship independently   |
| #66 (cost model) | Yes        | Additive feature, no blocker for other issues               |

### What CANNOT Be Deferred

| Issue                   | Why Not                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| #68 (session chmod)     | Active security defect -- session files with API data are world-readable |
| #67 (clearance mapping) | Semantic governance defect -- agents get wrong clearance level           |
| #63 (file migration)    | Blocks the entire v0.4.0 milestone (#64)                                 |

---

## 5. Session Feasibility Assessment

### Can all 9 be done in one autonomous session?

**No.** Here is the breakdown:

| Group          | Issues   | Estimated Effort | Parallelizable       |
| -------------- | -------- | ---------------- | -------------------- |
| Quick fixes    | #68, #67 | 20 min           | Yes                  |
| Type alignment | #60, #59 | 6-9 hours        | Sequential           |
| Features       | #61, #66 | 5-7 hours        | Parallel             |
| Structural     | #63      | 6-10 hours       | Blocks #64           |
| PactEngine     | #64      | 6-8 hours        | Sequential after #63 |
| Stubs          | #65      | 3-4 hours        | Partial parallel     |

**Total sequential estimate**: ~28-38 hours of work.
**With parallelization**: ~18-24 hours.
**One autonomous session**: ~4-8 hours of focused execution.

### Realistic Session Plan

**Session 1** (achievable): #68 + #67 + #60 + #59 + partial #66

- Quick fixes (20 min)
- Type alignment (6-9 hours)
- Start cost model if time permits

**Session 2**: #61 + #65 (/compact) + #66 completion

- HELD mechanism (3-4 hours)
- Stub removal /compact (2 hours)
- Cost model completion (1-2 hours)

**Session 3**: #63

- Governance file migration (6-10 hours)
- This is a full session by itself

**Session 4**: #64 + #65 (/plan)

- PactEngine build (6-8 hours)
- /plan wiring (1-2 hours)

---

## 6. Critical Path

```
#68 (15m) ─┐
#67 (5m)  ─┤
           ├──> #60 (3h) ──> #59 (5h) ──> #61 (4h) ──> #63 (8h) ──> #64 (7h)
#66 (3h)  ─┘                                                           │
#65/compact (2h) ────────────────────────────────────────── #65/plan ──┘
```

**Bottleneck**: #63 (governance file migration). It sits on the critical path between type alignment (#59/#60) and the v0.4.0 deliverable (#64). Every hour saved on #63 directly accelerates the milestone.

**Second bottleneck**: #59 (ConstraintEnvelope migration). At 4-6 hours, it is the longest single-issue effort before #63.

---

## 7. Cross-Reference Audit

### Documents Affected by These Issues

| File                                    | Issues Touching It      | Conflict Risk                                        |
| --------------------------------------- | ----------------------- | ---------------------------------------------------- |
| `kaizen_agents/supervisor.py`           | #67, #60, #59, #61, #66 | HIGH -- five issues modify the same file             |
| `kaizen_agents/types.py`                | #59                     | Medium -- large type replacement                     |
| `kaizen_agents/governance/clearance.py` | #60                     | Medium -- enum replacement                           |
| `kaizen_agents/delegate/builtins.py`    | #65                     | Low -- isolated handlers                             |
| `kaizen_agents/delegate/session.py`     | #68                     | Low -- isolated chmod addition                       |
| `kaizen_agents/delegate/loop.py`        | #66                     | Low -- additive cost integration                     |
| `pact/governance/__init__.py`           | #63                     | HIGH -- complete rewrite for re-exports              |
| `pact/governance/engine.py`             | #63, #64                | HIGH -- import path changes + PactEngine integration |
| `pact/governance/config.py`             | #63, #59, #60           | HIGH -- moves AND type consumers change              |
| `src/kailash/trust/__init__.py`         | #63                     | Medium -- new `pact` subpackage export               |

### Inconsistencies Found

1. **Three competing classification systems**: `DataClassification` (kaizen-agents IntEnum), `ConfidentialityLevel` from `kailash.trust.reasoning.traces` (str Enum), and `ConfidentialityLevel` from `pact.governance.config` (imported from kailash.trust). Issues #60 is meant to unify the first two; the third is already aligned.

2. **Two ConstraintEnvelope types**: Local dataclass in `kaizen_agents.types` (dict-based dimensions) vs Pydantic BaseModel in `pact.governance.config` (typed sub-models). Issue #59 is meant to unify these.

3. **\_scope_bridge.py uses a THIRD DataClassification**: `from kaizen.l3.context.types import DataClassification` -- this is neither the local IntEnum nor the trust ConfidentialityLevel. This file needs attention during #60 but is not mentioned in the issue.

---

## 8. Decision Points Requiring Stakeholder Input

1. **#60 -- What maps to C1_INTERNAL?** The local `DataClassification` has `C1_INTERNAL` which has no direct equivalent in `ConfidentialityLevel` (which uses `RESTRICTED`). Is the mapping `C1_INTERNAL -> RESTRICTED` acceptable, or should a new level be added to `ConfidentialityLevel`?

2. **#59 -- Adapter or big-bang migration?** The `ConstraintEnvelope` -> `ConstraintEnvelopeConfig` migration can use an adapter pattern (safer, slower) or big-bang replacement (faster, riskier). Which approach for the 20+ affected files?

3. **#63 -- Backward compatibility window**: After the governance file migration, how long must `from pact.governance import X` continue to work? Should the re-export layer emit deprecation warnings?

4. **#64 -- PactEngine scope**: Should PactEngine in v0.4.0 be a minimal bridge (GovernanceEngine + GovernedSupervisor integration) or the full progressive-disclosure facade described in the issue?

5. **#65 -- /plan implementation depth**: Should `/plan` in this round be a real multi-agent decomposition (requires significant LLM integration) or a simpler "show the plan DAG for review" command?

6. **Session strategy**: Given 4 autonomous sessions needed, should we optimize for shipping quick fixes + type alignment first (user-visible improvements) or prioritize #63 (unblocks the v0.4.0 milestone)?

---

## 9. Success Criteria

| Issue | Measurable Outcome                                                                                                                              |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| #68   | `stat -f %Lp` on session files returns `600`; directory returns `700`                                                                           |
| #67   | `GovernedSupervisor(data_clearance="restricted").clearance_level` returns `C2_CONFIDENTIAL` (or `RESTRICTED` after #60)                         |
| #60   | Zero imports of `DataClassification` from `kaizen_agents.governance.clearance` in production code; all tests pass with `ConfidentialityLevel`   |
| #59   | Zero imports of `ConstraintEnvelope` from `kaizen_agents.types` in production code; all tests pass with `ConstraintEnvelopeConfig`              |
| #61   | `supervisor.resolve_hold(node_id, "approve")` resumes a held node; timeout triggers escalation                                                  |
| #66   | `cost_model.compute("claude-sonnet-4-6", prompt=1000, completion=500)` returns a finite float                                                   |
| #63   | `from kailash.trust.pact import ConstraintEnvelopeConfig` works; `from pact.governance import ConstraintEnvelopeConfig` still works (re-export) |
| #64   | `PactEngine(org=my_org, model="claude-sonnet-4-6", budget_usd=10.0)` creates a governed supervisor with PACT envelope enforcement               |
| #65   | `/plan "analyze codebase"` returns a plan DAG; `/compact` reduces message count                                                                 |
