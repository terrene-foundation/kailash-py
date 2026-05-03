# Todos Red Team -- Validation Report

**Date**: 2026-04-08
**Scope**: 12 todo files (01 through 12), 450+ tasks
**Validator**: analyst (red team)
**Status**: GO WITH CHANGES

## Summary

27 findings: 3 critical, 8 important, 16 minor.

The todo plan is exceptionally thorough. Every SPEC has detailed Build/Wire pair discipline, every security subsection has a corresponding test task, and every phase has a cross-SDK issue filing task. The three critical findings are all about **missing dependencies and ordering hazards** that could cause cascading rework if not fixed. The important findings are gaps where a SPEC section has no task or where a task depends on work in a later phase. The plan is implementable after the changes below.

## Findings

### RT-001: SPEC-08 depends on SPEC-06, both in Phase 5, but dependency graph has a cycle risk

**Severity**: Critical
**Location**: `09-phase5-coresdk.md` TASK-08-09 (`SqliteAuditStore`) and `08-phase5-nexus.md` TASK-06-20 (Nexus audit consumes AuditStore)
**Issue**: The overview says Phase 5 runs SPEC-06 and SPEC-08 in parallel ("independent worktree"). But TASK-06-09 BUILDS `SqliteAuditStore` inside the Nexus todo file (08-phase5-nexus.md), while TASK-08-04 ALSO builds `SqliteAuditStore` inside the Core SDK todo file (09-phase5-coresdk.md). Both tasks create the same class at the same path (`src/kailash/trust/audit_store.py`). If two worktrees build the same file, merge conflicts are guaranteed.

Additionally, TASK-06-20 says "Nexus audit consumes AuditStore" which requires TASK-08-02 (AuditStore protocol) to be done first. R2 finding dependency ordering verification says "SPEC-08 depends on SPEC-06 (both Phase 5) which is acceptable since they can run sequentially within the phase." But the overview says they run "in parallel" -- this is a contradiction.

**Fix**: (a) Assign `SqliteAuditStore` and `AuditStore` protocol to exactly ONE todo file -- recommend SPEC-08 since it is the Core SDK consolidation spec. (b) Make SPEC-06 Phase 5b (wire tasks 06-15 through 06-22) depend on SPEC-08 TASK-08-02 through TASK-08-04 being complete. (c) Update the overview to show Phase 5 as "SPEC-08 (5a) then SPEC-06 (5b)" not "parallel."

---

### RT-002: TASK-R2-003 stacking order resolution is a BLOCKING prerequisite for Phase 3 and Phase 4, but has no enforcement

**Severity**: Critical
**Location**: `11-r2-followups.md` TASK-R2-003; `04-phase3-wrappers.md` all tasks; `06-phase4-delegate.md` TASK-05-03
**Issue**: TASK-R2-003 resolves the wrapper stacking order contradiction (Option A: governance inside cost, or Option B: governance outside cost). This decision affects: (a) TASK-03-70+ stacking tests, (b) SPEC-05 TASK-05-03/04/05/06 Delegate internal stack, (c) every stacking example in SPEC-03 and SPEC-10. The task says "When: Before TASK-03-\*" but there is no hard dependency edge in the Phase 3 task DAG. If an implementer starts TASK-03-20 (MonitoredAgent) or TASK-03-30 (L3GovernedAgent) before R2-003 is resolved, they will build to the wrong stacking order and need a rewrite.

**Fix**: Add an explicit dependency: TASK-03-03 (WrapperBase) depends on TASK-R2-003. Add TASK-R2-003 to the Phase 3 dependency graph as a root node. Same for TASK-05-03 depending on TASK-R2-003.

---

### RT-003: SPEC-06 "Wire Types" section is called out as missing by R2-005 but Nexus todo tasks do NOT wait for the spec fix

**Severity**: Critical
**Location**: `08-phase5-nexus.md` TASK-06-04 (JWT build); `11-r2-followups.md` TASK-R2-005
**Issue**: TASK-R2-005 says "Flesh out SPEC-06 wire types... When: Before TASK-06-\*". But TASK-06-04 (Build JWT validation at trust.auth.jwt) has no dependency on TASK-R2-005. The JWT claims structure (`sub`, `iss`, `aud`, `tenant_id`, `roles`, `scope`) does not exist in the spec yet. An implementer starting TASK-06-04 would need to invent the claims structure, which defeats the purpose of the spec. Same issue for TASK-06-26 (`_evaluate()` constraint check order) -- the order is not specified until R2-005 is resolved.

**Fix**: Add explicit dependency: TASK-06-01 (audit) depends on TASK-R2-005 completion. This gates the entire Nexus phase on the spec fix.

---

### RT-004: SPEC-04 §10.4 security test (extension point shadow hooks) has no explicit task

**Severity**: Important
**Location**: `05-phase3-baseagent.md` TASK-04-49 ("security tests §10.1-§10.5")
**Issue**: TASK-04-49 is a single task covering all 5 security subsections (§10.1 through §10.5). But SPEC-04 §10.4 "Extension Point Deprecation Shadow Hooks" requires testing that hooks on PSEUDO/TOOL posture agents raise instead of warn, and that `HookContext` exposes only `prompt_hash`, `model_name`, `call_id`. This is complex enough to warrant its own task. Lumping 5 distinct security surfaces into one "security tests" task risks incomplete coverage.

**Fix**: Split TASK-04-49 into 5 sub-tasks (04-49a through 04-49e), one per §10 subsection, with explicit acceptance criteria for each.

---

### RT-005: No task to update `src/kailash/mcp/__init__.py` (separate from `mcp_server`)

**Severity**: Important
**Location**: `01-phase1-mcp-package.md`; `12-cross-cutting.md` TASK-CC-01
**Issue**: The overview "Codebase Locations" table lists `src/kailash/mcp/` as a current MCP location. TASK-01-23 creates a shim at `src/kailash/mcp_server/__init__.py`. TASK-CC-01 mentions `src/kailash/mcp/__init__.py` as a shim target. But there is no explicit Build or Wire task in the Phase 1 todo file for `src/kailash/mcp/`. The platform server move (TASK-01-21) moves from `src/kailash/mcp/platform_server.py`, and TASK-01-28 handles `trust/plane/mcp_server.py`, but the `src/kailash/mcp/` directory itself (which may contain `__init__.py` and other files) has no explicit task for handling its contents and creating its shim.

**Fix**: Add a task in Phase 1 to audit `src/kailash/mcp/` contents (beyond `platform_server.py`), create shims at that import path, or confirm deletion. Currently it falls through the cracks between TASK-01-21 and TASK-CC-01.

---

### RT-006: Phase 2 SPEC-02 has no task for `kailash-mcp` pyproject.toml dependency update in the provider package

**Severity**: Important
**Location**: `02-phase2-providers.md`
**Issue**: SPEC-02 providers live in `packages/kailash-kaizen/`. Phase 1 TASK-01-03 adds `kailash-mcp` as a dependency of `kailash-kaizen`. But SPEC-02's providers need `kailash-mcp` for the `ToolRegistry` and `MCPClient` types used in TASK-02-38 and TASK-02-39. There is no explicit check that the Phase 1 pyproject.toml wiring is complete before Phase 2 starts. If Phase 1 is partially done, Phase 2 tasks will fail on import.

**Fix**: Add an explicit dependency in `02-phase2-providers.md` header: "Depends on: Phase 1 SPEC-01 TASK-01-03 (kailash-mcp registered as workspace dep)". Currently the dependency section says "parallel with Phase 2 SPEC-07" but does not gate on specific Phase 1 tasks.

---

### RT-007: SPEC-06 §6 (missing from spec template coverage) -- no Interop Test Vectors section

**Severity**: Important
**Location**: `08-phase5-nexus.md`; `11-r2-followups.md` TASK-R2-005
**Issue**: R2-005 calls out that SPEC-06 is missing an Interop Test Vectors section. The fix task (TASK-R2-005) adds it to the spec, but the Nexus todo file (`08-phase5-nexus.md`) has no task for implementing the JWT round-trip interop test vectors. The spec mapping table at the top of `08-phase5-nexus.md` has no entry for "Interop Test Vectors." Compare with SPEC-01 (TASK-01-44, TASK-01-45) and SPEC-07 (TASK-07-33, TASK-07-34) which both have explicit interop vector tasks.

**Fix**: Add a task after TASK-06-33 for JWT interop test vectors: sign a JWT with `kailash.trust.auth.jwt`, verify it round-trips through the Nexus auth middleware, and produce a fixture file for cross-SDK testing.

---

### RT-008: SPEC-08 backward compat section is called out as missing (R2-006) but TASK-08-14 ("re-exports") may not fully cover it

**Severity**: Important
**Location**: `09-phase5-coresdk.md` TASK-08-14; `11-r2-followups.md` TASK-R2-006
**Issue**: R2-006 says SPEC-08 is missing a Backward Compatibility section. TASK-R2-006 says "add backward compat section listing every re-export shim." The Core SDK todo file has TASK-08-14 ("re-exports") and TASK-08-15 ("delete old implementations"), but the spec mapping table does not explicitly map a "§Backward Compatibility" section to a task. After R2-006 adds the section to the spec, there should be a mapping entry.

**Fix**: After TASK-R2-006 executes, update the spec mapping table in `09-phase5-coresdk.md` to include the new backward compat section.

---

### RT-009: TASK-07-19 depends on `AuditStore` from SPEC-08 Phase 5, but it is in Phase 2

**Severity**: Important
**Location**: `03-phase2-envelope.md` TASK-07-19
**Issue**: TASK-07-19 ("Audit log sign/verify operations") says it uses "the existing `kailash.trust.audit_store.AuditStore`" and notes "(created in Phase 5 SPEC-08 consolidation; for now this task registers the emission point with a lightweight event hook so when SPEC-08 lands it just plugs in)." This is reasonable design, but the acceptance criteria say "Events visible via the existing AuditStore consumer contract." If Phase 5 has not landed yet, the "existing AuditStore" is the unconsolidated one. The task should explicitly state it works against the PRE-consolidation API and will be validated again in Phase 5.

**Fix**: Add a note to TASK-07-19 acceptance criteria: "AuditStore consumer contract is the pre-consolidation API; Phase 5 SPEC-08 landing will replace the backend, and TASK-08-08..08-13 will verify the hook still works."

---

### RT-010: SPEC-05 section numbering deviates from template (R2-004) -- todo tasks assume section numbers that may change

**Severity**: Important
**Location**: `06-phase4-delegate.md` throughout; `11-r2-followups.md` TASK-R2-004
**Issue**: TASK-R2-004 adds missing sections to SPEC-05 (Backward Compat, Semantics, Rust Parallel, Interop Test Vectors) and suggests renumbering. Every task in `06-phase4-delegate.md` references "§9 Security" for the current section number. After R2-004 adds sections, §9 might shift. All task references become stale.

**Fix**: Use section TITLES in task references (e.g., "SPEC-05 Security Considerations" not "SPEC-05 §9"). Apply this across all 12 todo files per R2-007's recommendation.

---

### RT-011: No explicit task to run the full test suite at phase boundaries

**Severity**: Important
**Location**: `12-cross-cutting.md` TASK-CC-07 and TASK-CC-08
**Issue**: TASK-CC-07 captures the baseline, and TASK-CC-08 creates a verification script. But there is no task in each phase's todo file that says "Run full test suite and compare against baseline." The overview says "Test count tracked in `.test-results` after each todo" and the testing rules say "runs full suite ONCE per todo." But there is no explicit phase-gate task that says "After all TASK-01-\* are done, run full suite and write `.test-results`." This is implied by process but should be explicit.

**Fix**: Add a final task to each phase todo file (TASK-01-49, TASK-02-41, TASK-07-42, etc.) titled "Phase gate: run full suite, write `.test-results`, compare against `.test-baseline`."

---

### RT-012: `tests/fixtures/cross-sdk/` and `tests/fixtures/envelope/` are separate directories with overlapping content

**Severity**: Minor
**Location**: `03-phase2-envelope.md` TASK-07-20; `10-phase6-crosssdk.md` TASK-10-01, TASK-10-03
**Issue**: TASK-07-20 creates `tests/fixtures/envelope/` with 20 vectors. TASK-10-01 creates `tests/fixtures/cross-sdk/envelope/` as a separate directory. TASK-10-03 says it uses SPEC-07 vectors. Are these the same files or copies? If copies, they will diverge. If the same, the directory structure is confused.

**Fix**: Clarify: `tests/fixtures/envelope/` IS the canonical location; `tests/fixtures/cross-sdk/envelope/` should be a symlink or TASK-10-03 should reference `tests/fixtures/envelope/` directly. Do not duplicate vectors.

---

### RT-013: TASK-01-30 has a conditional outcome (MOVE or DELETE) that affects downstream tasks

**Severity**: Minor
**Location**: `01-phase1-mcp-package.md` TASK-01-30
**Issue**: TASK-01-30 says "Read both files. Determine production consumer count. Decision: MOVE or DELETE." The test section has two different test paths depending on the decision. This is fine operationally, but it means the task graph has a branch point that is not reflected in the dependency DAG. If the decision is MOVE, new downstream tasks appear (test the new location). If DELETE, different downstream tasks appear. The implementer needs to update the DAG at runtime.

**Fix**: Acceptable as-is given the documented structure. Note this in the DAG comments.

---

### RT-014: TASK-02-38 uses `config.execution_mode` branching which may conflict with agent-reasoning rules

**Severity**: Minor
**Location**: `02-phase2-providers.md` TASK-02-38 code block
**Issue**: TASK-02-38 shows `if config.execution_mode == "streaming"` to select `get_streaming_provider` vs `get_llm_provider`. This is configuration branching (permitted exception #5 in agent-reasoning rules), but the code block uses string comparison on `execution_mode` which could be confused with content-based routing. The distinction should be explicit in the task description.

**Fix**: Add a note: "This is configuration branching per `rules/agent-reasoning.md` exception #5, not input-content routing."

---

### RT-015: TASK-04-03 duplicates TASK-03-02 (both create `kaizen/core/agent_loop.py`)

**Severity**: Minor
**Location**: `04-phase3-wrappers.md` TASK-03-02; `05-phase3-baseagent.md` TASK-04-03
**Issue**: TASK-03-02 moves `delegate/loop.py` to `kaizen/core/agent_loop.py`. TASK-04-03 also says "Create `kaizen/core/agent_loop.py` module." Both are in Phase 3. If both execute, the second will overwrite the first's work. The descriptions differ slightly -- 03-02 moves the existing loop, 04-03 extracts the TAOD loop from BaseAgent.

**Fix**: Merge into one task or make 04-03 explicitly depend on 03-02 and say "Extend the module created in TASK-03-02 with the TAOD extraction." Currently both claim to create the same file.

---

### RT-016: No task for `kailash-mcp` package `py.typed` marker

**Severity**: Minor
**Location**: `01-phase1-mcp-package.md` TASK-01-01
**Issue**: TASK-01-01 creates the package skeleton but does not mention a `py.typed` marker file. For PEP 561 compliance (typed packages), `packages/kailash-mcp/src/kailash_mcp/py.typed` should exist. Other packages in the monorepo likely have this.

**Fix**: Add `py.typed` to TASK-01-01 file list.

---

### RT-017: TASK-CC-03 references `from warnings import deprecated` which is Python 3.13+

**Severity**: Minor
**Location**: `12-cross-cutting.md` TASK-CC-03
**Issue**: The code example uses `from warnings import deprecated` which is only available in Python 3.13+. SPEC-01 §12 specifies Python >= 3.11. TASK-04-15 in the BaseAgent todos correctly creates a custom `@deprecated` decorator at `kailash._deprecation`. TASK-CC-03 should reference that custom decorator, not the stdlib one.

**Fix**: Update TASK-CC-03 code example to use `from kailash._deprecation import deprecated` instead of `from warnings import deprecated`.

---

### RT-018: Extension point names in TASK-CC-03 do not match SPEC-04

**Severity**: Minor
**Location**: `12-cross-cutting.md` TASK-CC-03
**Issue**: TASK-CC-03 lists extension points as `before_llm_call`, `after_llm_call`, `before_tool_call`, `after_tool_call`, `before_iteration`, `after_iteration`, `on_complete`. But SPEC-04 §2.3 lists them as `_default_signature`, `_default_strategy`, `_generate_system_prompt`, `_validate_signature_output`, `_pre_execution_hook`, `_post_execution_hook`, `_handle_error`. These are completely different names.

**Fix**: TASK-CC-03 must use the SPEC-04 names. The names in TASK-CC-03 appear to be invented rather than sourced from the spec.

---

### RT-019: SPEC-01 §5 security subsections (4 threats) are covered by a single task (TASK-01-42)

**Severity**: Minor
**Location**: `01-phase1-mcp-package.md` TASK-01-42
**Issue**: SPEC-01 §5 has 4 distinct security concerns (SSRF, subprocess, key handling, sandbox). TASK-01-42 covers all 4 in one task. This is less granular than Phases 3-5 which split security into per-subsection tasks. However, the acceptance criteria enumerate all 4 surfaces, so coverage is adequate.

**Fix**: Acceptable as-is. The acceptance criteria are specific enough.

---

### RT-020: Task numbering collision in Phase 6 todo file

**Severity**: Minor
**Location**: `10-phase6-crosssdk.md`
**Issue**: The spec mapping table references tasks as "TASK-10-02" through "TASK-10-19", which collides with the TASK-10-\* numbering in `07-phase4-multiagent.md` (TASK-10-01 through TASK-10-95). Both use the "10" prefix but in different todo files for different SPECs. `07-phase4-multiagent.md` is SPEC-10 tasks, `10-phase6-crosssdk.md` is SPEC-09 tasks. The numbering scheme breaks: SPEC-09 tasks should use prefix "09" not "10".

**Fix**: Rename all tasks in `10-phase6-crosssdk.md` from `TASK-10-*` to `TASK-09-*`. This eliminates the collision with SPEC-10 tasks.

---

### RT-021: TASK-03-05 partially duplicates TASK-07-08

**Severity**: Minor
**Location**: `04-phase3-wrappers.md` TASK-03-05; `03-phase2-envelope.md` TASK-07-08
**Issue**: TASK-03-05 adds `AgentPosture.fits_ceiling()` and `clamp_to_ceiling()`. TASK-07-08 also adds `AgentPosture.fits_ceiling()` as a classmethod. Both tasks target `trust/posture`. If Phase 2 (TASK-07-08) lands first, Phase 3 (TASK-03-05) should not recreate it.

**Fix**: TASK-03-05 should depend on TASK-07-08 and say "Verify TASK-07-08's `fits_ceiling` exists; add `clamp_to_ceiling` if not already present."

---

### RT-022: No explicit task for `kailash-mcp` `conftest.py` or test infrastructure

**Severity**: Minor
**Location**: `01-phase1-mcp-package.md`
**Issue**: TASK-01-01 creates test directories (`tests/unit/`, `tests/integration/`, `tests/e2e/`) but does not mention a `conftest.py` for the new package. Per `rules/env-models.md`, root `conftest.py` auto-loads `.env` for pytest. The new package needs its own `conftest.py` (or relies on the root one, which should be documented).

**Fix**: Add `packages/kailash-mcp/conftest.py` (or `tests/conftest.py`) to TASK-01-01 file list, with `.env` loading per rules.

---

### RT-023: SPEC-02 §2.2 (wire types) -- no explicit cross-SDK JSON shape verification task

**Severity**: Minor
**Location**: `02-phase2-providers.md` TASK-02-02
**Issue**: TASK-02-02 says "Field names match Rust `LlmRequest`/`LlmResponse` case-for-case" but there is no test that loads a cross-SDK fixture file and verifies Python output matches. TASK-02-40 files cross-SDK issues but the actual fixture-based round-trip test is not present. Compare with SPEC-07 which has TASK-07-33 for fixture-based interop testing.

**Fix**: Add a fixture-based interop test task after TASK-02-40 that loads `tests/fixtures/cross-sdk/provider-types/` vectors and verifies Python serialization matches.

---

### RT-024: TASK-06-07 through TASK-06-11 SSO provider numbering is ambiguous

**Severity**: Minor
**Location**: `08-phase5-nexus.md` dependency graph lines 68-72
**Issue**: The dependency graph lists `TASK-06-10 (SSO Google)`, `TASK-06-10 (SSO Azure)`, `TASK-06-10 (SSO GitHub)` -- all as TASK-06-10. These should be separate tasks with distinct IDs (e.g., TASK-06-10a/b/c or TASK-06-10, -10b, -10c).

**Fix**: Assign unique task IDs to each SSO provider (Google, Azure, GitHub are all "TASK-06-10" in the graph).

---

### RT-025: No task updates `deploy/deployment-config.md` during phases

**Severity**: Minor
**Location**: `12-cross-cutting.md` TASK-CC-09
**Issue**: TASK-CC-09 (release coordination) updates `deploy/deployment-config.md` at the end. But the overview's convergence verification checklist does not include this file. It is a post-completion task, which is fine, but should be in the verification checklist.

**Fix**: Add `deploy/deployment-config.md` updated to the convergence verification checklist in `00-overview.md`.

---

### RT-026: TASK-R2-012 (standardize section numbering) scheduled "post-codify" has no owner

**Severity**: Minor
**Location**: `11-r2-followups.md` TASK-R2-012
**Issue**: "When: After all spec fixes... Do NOT renumber during active implementation." Scheduled for post-codify, but there is no phase or todo file that owns it. It will be forgotten unless tracked.

**Fix**: Add TASK-R2-012 to the cross-cutting file (`12-cross-cutting.md`) with a dependency on all phases complete.

---

### RT-027: SPEC-02 §5 security subsection coverage -- `sanitize_provider_error` tested in TASK-02-36 but §5.1 (credential rotation) has no dedicated task

**Severity**: Minor
**Location**: `02-phase2-providers.md`; SPEC-02 §5
**Issue**: SPEC-02 §5 has subsections (§5.1 BYOK credential rotation, §5.2 error message sanitization, §5.3 provider module isolation). §5.2 is covered by TASK-02-36, §5.3 by TASK-02-37. But §5.1 (BYOK credential rotation -- cache TTL, per-tenant isolation) is only partially covered in TASK-02-14 (OpenAI BYOK test) without a dedicated security test. If another provider has a BYOK bug, it would not be caught.

**Fix**: Add a parametrized BYOK security test task covering all providers that declare BYOK capability, not just OpenAI.

---

## Spec Coverage Matrix

| SPEC | §1 Overview | §2 Wire Types                    | §3 Semantics   | §4 Backward Compat               | §Security               | §Migration     | §Test Migration | §Rust Parallel         | §Interop Vectors         |
| ---- | ----------- | -------------------------------- | -------------- | -------------------------------- | ----------------------- | -------------- | --------------- | ---------------------- | ------------------------ |
| 01   | TASK-01-02  | TASK-01-04,05                    | TASK-01-11     | TASK-01-23,24                    | TASK-01-42              | covered by DAG | TASK-01-36..40  | TASK-01-48             | TASK-01-44,45            |
| 02   | TASK-02-01  | TASK-02-02                       | TASK-02-11     | TASK-02-34,35                    | TASK-02-36,37           | covered by DAG | n/a (new)       | TASK-02-40             | **PARTIAL** (RT-023)     |
| 03   | TASK-03-03  | TASK-03-01                       | TASK-03-70+    | TASK-03-90                       | TASK-03-70..83          | covered by DAG | TASK-03-90+     | TASK-03-95             | n/a                      |
| 04   | TASK-04-01  | TASK-04-04                       | TASK-04-08..11 | TASK-04-20..27                   | TASK-04-49 (**RT-004**) | covered by DAG | TASK-04-41..47  | TASK-04-52             | TASK-04-53               |
| 05   | TASK-05-01  | TASK-05-02                       | TASK-05-03..06 | **MISSING** (**RT-010**, R2-004) | TASK-05-09..26          | covered by DAG | TASK-05-37      | TASK-05-43             | **MISSING** (R2-004)     |
| 06   | TASK-06-01  | **MISSING** (**RT-003**, R2-005) | n/a            | TASK-06-23                       | TASK-06-34..37          | covered by DAG | TASK-06-30..33  | TASK-06-38             | **MISSING** (**RT-007**) |
| 07   | TASK-07-01  | TASK-07-02..04                   | TASK-07-06..08 | TASK-07-21..23                   | TASK-07-31..39          | covered by DAG | existing suites | TASK-07-40             | TASK-07-33,34            |
| 08   | TASK-08-01  | **PARTIAL** (R2-006)             | TASK-08-03..05 | TASK-08-14 (**RT-008**)          | TASK-08-28..32          | TASK-08-25     | TASK-08-08..13  | TASK-08-33             | TASK-08-26,27            |
| 09   | TASK-09-01  | TASK-09-02..04                   | validated      | n/a                              | TASK-09-06..14          | n/a            | n/a             | n/a (IS the cross-SDK) | TASK-09-02..04           |
| 10   | TASK-10-01  | TASK-10-10..36                   | TASK-10-70+    | TASK-10-40,41                    | TASK-10-50..61          | covered by DAG | TASK-10-70..86  | TASK-10-95             | n/a                      |

**Legend**: Bold = gap identified in this report.

## Build/Wire Pair Audit

All 12 todo files have explicit Build/Wire pair tables. Verified pairs for each phase:

| Phase           | Verified                                          | Missing Pairs                                      |
| --------------- | ------------------------------------------------- | -------------------------------------------------- |
| 1 (MCP)         | 14 pairs documented                               | `src/kailash/mcp/` directory handling (**RT-005**) |
| 2 (Providers)   | 18 pairs documented                               | None found                                         |
| 2 (Envelope)    | 10 pairs documented                               | None found                                         |
| 3 (Wrappers)    | Events, AgentLoop, 5 wrappers, routing all paired | None found                                         |
| 3 (BaseAgent)   | 11 pairs documented                               | None found                                         |
| 4 (Delegate)    | 12+ pairs documented                              | None found                                         |
| 4 (Multi-agent) | 7 patterns documented                             | None found                                         |
| 5 (Nexus)       | 12 pairs documented                               | None found                                         |
| 5 (Core SDK)    | 8 pairs documented                                | None found                                         |
| 6 (Cross-SDK)   | Validation only                                   | n/a                                                |

## Dependency Graph Issues

1. **RT-001 (Critical)**: SPEC-06 and SPEC-08 both create `SqliteAuditStore` -- parallel execution will conflict
2. **RT-002 (Critical)**: TASK-R2-003 has no hard edge in the Phase 3 DAG
3. **RT-003 (Critical)**: TASK-R2-005 has no hard edge in the Phase 5 DAG
4. **RT-015 (Minor)**: TASK-03-02 and TASK-04-03 both create `kaizen/core/agent_loop.py`
5. **RT-021 (Minor)**: TASK-03-05 and TASK-07-08 both add `fits_ceiling` to AgentPosture
6. **RT-020 (Minor)**: TASK-10-\* numbering collision between Phase 4 and Phase 6

No circular dependencies found. Phase ordering is correct for all other edges.

## R2 Coverage Verification

| Finding | Severity  | Task                               | Status                                                 |
| ------- | --------- | ---------------------------------- | ------------------------------------------------------ |
| R2-001  | Critical  | RESOLVED (spec fixed)              | Covered                                                |
| R2-002  | Critical  | RESOLVED (security sections added) | Covered                                                |
| R2-003  | Important | TASK-R2-003                        | Covered -- but needs hard dependency edge (**RT-002**) |
| R2-004  | Important | TASK-R2-004                        | Covered                                                |
| R2-005  | Important | TASK-R2-005                        | Covered -- but needs hard dependency edge (**RT-003**) |
| R2-006  | Important | TASK-R2-006                        | Covered                                                |
| R2-007  | Important | TASK-R2-007                        | Covered                                                |
| R2-008  | Minor     | Absorbed into TASK-R2-003          | Covered                                                |
| R2-009  | Minor     | TASK-04-28, -29, -30, -31          | Covered                                                |
| R2-010  | Minor     | Phase 3 L3Gov Build tasks          | Covered                                                |
| R2-011  | Minor     | TASK-10-36                         | Covered                                                |
| R2-012  | Minor     | Post-codify (**RT-026**: no owner) | Needs tracking fix                                     |
| R2-013  | Minor     | TASK-07-08 (7 edge cases explicit) | Covered                                                |
| R2-014  | Minor     | TASK-09-10, -11                    | Covered                                                |

All 14 R2 findings accounted for. 12/14 fully covered; 2 need dependency enforcement.

## Risk Assessment

### Risk 1: Stacking Order Resolution (RT-002) -- HIGHEST RISK

**Likelihood**: High (the contradiction is real and unresolved)
**Impact**: High (affects Phase 3, Phase 4, and every integration test)
**Mitigation**: Resolve TASK-R2-003 BEFORE any Phase 3 implementation. The decision (Option A vs Option B) cascades through 50+ tasks.

### Risk 2: AuditStore Merge Conflict (RT-001)

**Likelihood**: High (two parallel worktrees building the same file)
**Impact**: Medium (merge conflict requires rework but is not architecturally wrong)
**Mitigation**: Sequence SPEC-08 before SPEC-06 within Phase 5, or assign AuditStore to exactly one todo file.

### Risk 3: SPEC-06 Wire Types Missing (RT-003)

**Likelihood**: Medium (implementer might invent JWT structure)
**Impact**: High (wrong JWT claims structure requires re-implementation across all auth consumers)
**Mitigation**: Gate Phase 5 on TASK-R2-005 completion.

### Risk 4: Task 03-02 / 04-03 File Collision (RT-015)

**Likelihood**: Medium (co-dependent Phase 3 tasks may be assigned to different agents)
**Impact**: Low (fixable with a merge, but wastes a cycle)
**Mitigation**: Merge tasks or add explicit dependency.

### Risk 5: Cross-SDK Fixture Directory Confusion (RT-012)

**Likelihood**: Medium (two directories with overlapping purpose)
**Impact**: Low (vectors diverge over time, causing false interop confidence)
**Mitigation**: Use symlinks or a single canonical directory.

## Verdict

**GO WITH CHANGES**

The plan is comprehensive and well-structured. The three critical findings (RT-001, RT-002, RT-003) are all dependency ordering issues that are straightforward to fix by adding hard edges to the dependency graphs. The important findings are spec coverage gaps that are already identified by R2 follow-ups but lack enforcement in the task DAGs. The minor findings are mostly documentation and naming issues.

**Required changes before `/implement`:**

1. **RT-001**: Resolve AuditStore ownership between SPEC-06 and SPEC-08. Sequence Phase 5.
2. **RT-002**: Add TASK-R2-003 as a root dependency in the Phase 3 DAG.
3. **RT-003**: Add TASK-R2-005 as a dependency for TASK-06-01 (gates Phase 5 Nexus).
4. **RT-020**: Rename TASK-10-_ in `10-phase6-crosssdk.md` to TASK-09-_ to eliminate numbering collision.

**Recommended changes (not blocking):**

5. RT-004: Split TASK-04-49 into per-subsection security tests.
6. RT-005: Add explicit task for `src/kailash/mcp/` directory handling.
7. RT-007: Add JWT interop test vector task to Nexus phase.
8. RT-011: Add phase-gate test suite tasks to each phase's todo file.
9. RT-015: Resolve TASK-03-02 / TASK-04-03 file collision.
10. RT-018: Fix extension point names in TASK-CC-03 to match SPEC-04.
