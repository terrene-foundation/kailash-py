# Full Clearance Master Analysis

**Scope**: 34 GH issues + 8 convergence todo files (260 implementation tasks)
**Date**: 2026-04-10
**Red team**: R1 PASS WITH CONDITIONS — all conditions addressed in this revision
**Source analyses**: `05-clearance-bugs.md`, `06-clearance-pact.md`, `07-clearance-ml.md`, `08-clearance-enhancements.md`
**Red team report**: `11-redteam-clearance-r1.md`

## 1. Scope Summary

**Completed convergence phases** (4 of 12): SPEC-01 (MCP package), SPEC-07 (envelope), SPEC-03 (wrappers), SPEC-06 (Nexus). These are in `todos/completed/`.

| Stream                  | Issues                  | Conv Tasks | Effort (cycles)       | Status                           |
| ----------------------- | ----------------------- | ---------- | --------------------- | -------------------------------- |
| Bugs (kaizen/dataflow)  | 5 (#363-#368, #377)     | —          | 0.5                   | 4 fixed, close them; 1 remaining |
| PACT bugs (production)  | 3 (#388-#390)           | —          | 1                     | Cross-SDK matched, high priority |
| Convergence (remaining) | — (8 active todo files) | 260        | 9-10 (parallel)       | 4 phases done, 8 active          |
| PACT conformance        | 7 (#380-#386)           | —          | 5-6                   | N3/N4 depend on SPEC-08          |
| Platform enhancements   | 11 (#351-#375)          | —          | 4-6 (additive)        | 4 overlap convergence            |
| ML features             | 8 (#341-#348)           | —          | 1                     | Fully independent                |
| **Total**               | **34**                  | **260**    | **~15-17 wall-clock** |                                  |

**Note**: #367 is confirmed FIXED (all 3 sub-issues). Counted in bugs-to-close, not enhancements.

## 2. Key Findings

### 2.1 Five Bugs Already Fixed — Close Immediately

#363, #364, #367, #368 were resolved during convergence PR #387. #367 confirmed FIXED at specific line numbers with tests. These need GH issue closure with commit references — zero implementation effort.

### 2.2 Three PACT Production Bugs (#388-#390) — Higher Priority Than Conformance

These are active production bugs with cross-SDK matched issues (kailash-rs#93-95):

- **#388**: `grant_clearance()` doesn't resolve D/T/R addresses — direct Python callers bypass the endpoint band-aid
- **#389**: `get_node()` doesn't fall back to `get_node_by_role_id()` for non-head roles
- **#390**: `verify_action` crashes with `AttributeError` when `envelope.operational` is None — should treat None as unconstrained

These should run in Wave 0 alongside #377, before any convergence work.

### 2.3 Convergence Is the Critical Path

The 4 heavy convergence todo files (SPEC-02 providers, SPEC-04 BaseAgent, SPEC-05 Delegate, SPEC-10 multi-agent) form a strict dependency chain:

```
SPEC-02 (40 tasks, 2 cycles) ──> SPEC-04 (53 tasks, 3 cycles) ──> SPEC-05 (44 tasks, 2 cycles)
                                                                ──> SPEC-10 (48 tasks, 2 cycles) [parallel w/ SPEC-05]
```

Critical path: **7 cycles** for these alone. SPEC-08 (33 tasks) can start once SPEC-03 (wrappers, already complete) delivers MonitoredAgent — it does NOT need to wait for SPEC-04 to finish. This means SPEC-08 can overlap with SPEC-04, reducing wall-clock by ~1 cycle.

### 2.4 PACT N3/N4 Depend on SPEC-08

PACT N3 (plan re-entry) needs BudgetTracker exhaustion signals from SPEC-08. N4 (audit tiers) needs the canonical AuditStore from SPEC-08. These cannot start until Phase 5a completes. N5 (ObservationSink) is structurally independent — it can start any time.

### 2.5 Enhancement Overlap with Convergence

Four enhancements naturally fold into convergence phases:

- **#357** (Gemini structured output) → **bridge task** spanning SPEC-02 (provider capability detection) AND SPEC-04 (MCPMixin restructuring). Track separately, not absorbed by one phase.
- **#360** (trust shim package) → after SPEC-07 envelope unification (already complete, so can start in Wave 2)
- **#365/#366** (Ollama embeddings/allowlist) → SPEC-02 capability protocols (Phase 2)
- **#375** (cross-SDK parity tooling) → Phase 6 (SPEC-09)

### 2.6 ML Features Are Fully Independent

All 8 ML issues (#341-#348) are self-contained, require no convergence work, and are fully parallelizable. #341 (public metrics module) is the foundation the others build on. Realistic estimate: ~1 cycle (not 0.5, accounting for parallelization friction).

### 2.7 Three Posture Enums Need Unification

#386 reveals three separate posture enums: `TrustPosture`, `AgentPosture`, `TrustPostureLevel`. This is a wire-format concern that should land early. Since SPEC-07 is already complete, this can start immediately.

### 2.8 Completed Phases Reduce Scope

4 phases are already done: SPEC-01, SPEC-03, SPEC-06, SPEC-07. The convergence task count (260) reflects only remaining active todos.

## 3. Revised Execution Route

### Wave 0: Immediate Fixes (1 cycle)

- Close 5 fixed bugs (#363, #364, #367, #368) with commit refs — zero effort
- Fix #377 (sync SingleShotStrategy MCP loop) — port from async variant
- Fix #373 (BulkResult WARN on partial failure) — mandated by observability rules
- Fix #388 (PACT grant_clearance address resolution) — production bug, cross-SDK
- Fix #389 (PACT get_node non-head roles) — production bug, cross-SDK
- Fix #390 (PACT verify_action None crash) — production bug, cross-SDK
- Fix #386 (AgentPosture enum alignment) — wire-format, must land before convergence deepens

### Wave 1: Convergence Core (7 cycles, critical path)

Sequential chain with max internal parallelization:

| Phase | SPEC                | Tasks | Cycles             | Absorbs GH Issues |
| ----- | ------------------- | ----- | ------------------ | ----------------- |
| 2     | SPEC-02 Providers   | 40    | 2                  | #365, #366        |
| 3     | SPEC-04 BaseAgent   | 53    | 3                  | —                 |
| 4a    | SPEC-05 Delegate    | 44    | 2                  | —                 |
| 4b    | SPEC-10 Multi-agent | 48    | 2 (parallel w/ 4a) | —                 |

**#357** (Gemini structured output): Bridge task spanning SPEC-02 (provider capability detection) and SPEC-04 (MCPMixin restructuring). Tracked separately, implemented across both phases.

### Wave 2: Convergence Support (4 cycles, overlaps with Wave 1 from SPEC-04 start)

SPEC-08 depends on SPEC-03 (wrappers, already complete), NOT on SPEC-04. It can start as soon as Wave 1 begins SPEC-04, saving ~1 cycle on the critical path.

| Phase | SPEC             | Tasks          | Cycles | Absorbs GH Issues |
| ----- | ---------------- | -------------- | ------ | ----------------- |
| 5a    | SPEC-08 Core SDK | 33             | 2      | —                 |
| —     | R2 followups     | R2-004..R2-007 | 1      | —                 |
| —     | Cross-cutting    | CC-01..CC-10   | 2      | #360              |

**Note**: SPEC-06 (Nexus) is already complete (in `todos/completed/`).

### Wave 3: PACT Conformance (4-5 cycles, partially parallel with Wave 2)

#386 already done in Wave 0. N5 is independent (no dependency on N1/N2).

| Order         | Issue                     | Cycles | Dependency     |
| ------------- | ------------------------- | ------ | -------------- |
| Parallel      | #380 N1 KnowledgeFilter   | 1      | None           |
| Parallel      | #381 N2 Envelope Cache    | 0.5    | None           |
| Parallel      | #384 N5 ObservationSink   | 0.75   | None           |
| After SPEC-08 | #383 N4 Audit Tiers       | 1      | SPEC-08        |
| After SPEC-08 | #382 N3 Plan Re-Entry     | 1.5    | SPEC-08 budget |
| Last          | #385 N6 Conformance Suite | 1      | N1-N5 complete |

### Wave 4: ML Features + Independent Enhancements (parallel with Wave 2-3)

| Sub-wave     | Issues                                                                                   | Cycles |
| ------------ | ---------------------------------------------------------------------------------------- | ------ |
| ML batch     | #341-#348 (all 8, #341 first then rest parallel)                                         | 1      |
| Enhancements | #369 FabricIntegrity, #370 EventLoopWatchdog, #371 OntologyRegistry, #374 ProgressUpdate | 3-4    |

### Wave 5: Cross-SDK + Docs + Release (2 cycles)

| Item            | Issues                 | Cycles |
| --------------- | ---------------------- | ------ |
| Phase 6 SPEC-09 | 20 tasks + #375        | 2      |
| Docs            | #351 DriftMonitor docs | 0.5    |
| README + Sphinx | CC-10                  | 0.5    |

## 4. Dependency Graph

```
Wave 0 (1c) ───────────────────────────────────────────────────────>
  ├── #377, #373 fixes
  ├── #388, #389, #390 PACT bugs
  ├── #386 posture alignment
  └── Close 5 fixed bugs

Wave 1 (7c critical path) ─────────────────────────────────────────>
  SPEC-02 (2c) ──> SPEC-04 (3c) ──> SPEC-05 (2c) || SPEC-10 (2c)
     absorbs #365, #366       #357 bridges SPEC-02 + SPEC-04

Wave 2 (3c, starts when SPEC-04 begins — SPEC-08 needs SPEC-03 not SPEC-04)
  SPEC-08 (2c)
  R2 followups (1c)
  Cross-cutting + #360 (2c)

Wave 3 (4-5c, partially parallel with Wave 2) ─────────────────────>
  #380, #381, #384 (parallel, 1c) ──>
    [after SPEC-08] #383, #382 (1.5c) ──> #385 (1c)

Wave 4 (parallel with Waves 2-3) ──────────────────────────────────>
  ML features (1c) || Independent enhancements (3-4c)

Wave 5 (2c, after all) ────────────────────────────────────────────>
  SPEC-09 + #375 (2c) || #351 docs (0.5c) || README (0.5c)
```

## 5. Risk Register

| Risk                                                      | Likelihood | Impact            | Mitigation                                                    |
| --------------------------------------------------------- | ---------- | ----------------- | ------------------------------------------------------------- |
| Provider extraction (14 from 5K-line monolith) > 2 cycles | Medium     | High — blocks all | Max parallelization: 14 providers in worktrees after registry |
| BaseAgent slimming breaks 188 subclasses                  | High       | Critical          | TASK-04-01 audit first; line-count CI guard; family sweep     |
| Completed phases need rework after later phases           | Medium     | High              | Run convergence-verify.py after each phase                    |
| PACT N3 (plan re-entry) design complexity                 | Medium     | Medium            | Frozen suspension snapshots, not saga replay                  |
| Posture enum unification (#386) is wire-format change     | Medium     | High              | Backward-compat via `_missing_()`; land in Wave 0 early       |
| #357 bridge task falls between SPEC-02 and SPEC-04        | Medium     | Medium            | Explicit tracking as bridge; partial fix in each phase        |
| #374 ProgressUpdate has soft dep on SPEC-08 runtime       | Low        | Low               | Sequence after SPEC-08 or decouple                            |
| Cross-cutting shims > 20 deprecated paths                 | Certain    | Low               | Migration guide + sed commands; v3.0 removal timeline         |

## 6. Total Effort Estimate

| Metric                             | Cycles                                     |
| ---------------------------------- | ------------------------------------------ |
| Total nominal effort               | ~33                                        |
| With max parallelization           | ~15-17                                     |
| Critical path (sequential minimum) | ~11 (saved 1c by starting SPEC-08 earlier) |
| Convergence alone (critical path)  | ~7                                         |
| Non-convergence (parallel streams) | ~9-11                                      |

Wall-clock: **~12-15 autonomous execution cycles** with aggressive worktree parallelization across all streams.

## 7. Red Team Conditions Addressed

| Condition              | Resolution                                                                  |
| ---------------------- | --------------------------------------------------------------------------- |
| Add #341, #388-#390    | Added: #341 in ML batch, #388-#390 in Wave 0 as high-priority PACT bugs     |
| Fix task count 182→260 | Corrected to 260 in scope table; counted per-file (40+53+44+48+33+20+12+10) |
| #357 bridge tracking   | Tracked as bridge task across SPEC-02 and SPEC-04, not absorbed by one      |
| #367 dedup             | Confirmed FIXED, counted only in bugs-to-close                              |
| Wave 2 start condition | SPEC-08 starts after SPEC-03 (complete), not after SPEC-04; saves ~1 cycle  |
