# Platform Architecture Convergence — Next-Session Execution Plan

**Workspace**: `workspaces/platform-architecture-convergence/`
**Planner context date**: 2026-04-11
**Scope**: 202 unchecked `- [ ]` items across 6 active follow-up todo files + GH #416 (OPEN)
**Prior state**: Convergence SPEC-01..10 SHIPPED (v2.8.0 + v2.8.1). 33 of 34 tracked GH issues closed, 1 OPEN (#416).

---

## 0. Critical Reality Check (Read This First)

Before the next session executes anything, it MUST absorb this reconciliation:

| Category                                       | Claim (todo files)    | Reality (code + git)                                                                                                                                                                                                                                                                                                           |
| ---------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| R2-003 through R2-014 spec fixes               | Pending               | **Moot.** The target SPEC files under `workspaces/.../01-analysis/03-specs/` no longer exist; convergence already shipped. These todos exist only as spec-polish items for artifact preservation.                                                                                                                              |
| PACT-01..10 (14-pact-bugs-conformance.md)      | 48 unchecked AC items | **Code shipped** in commits `090c0e97` + `fca3b1fb`. All files (`knowledge.py`, `observation.py`, `suspension.py`, `audit.py`, `test_*.py`) exist. Only **checkbox hygiene** remains.                                                                                                                                          |
| ML-01..08 (15-ml-features.md)                  | 42 unchecked AC items | **All 8 engines shipped** in `090c0e97`. `metrics/`, `clustering.py`, `dim_reduction.py`, `anomaly_detection.py`, `text_engine.py` all present. Checkbox hygiene only.                                                                                                                                                         |
| ENH-02 #369 FabricIntegrityMiddleware          | 5 unchecked           | **Shipped** in `fca3b1fb`. Checkbox hygiene.                                                                                                                                                                                                                                                                                   |
| ENH-04 #365 Ollama embeddings                  | 5 unchecked           | **Shipped** in `fca3b1fb`. Checkbox hygiene.                                                                                                                                                                                                                                                                                   |
| ENH-05 #366 Ollama tool allowlist              | 4 unchecked           | **Shipped** in `fca3b1fb`. Checkbox hygiene.                                                                                                                                                                                                                                                                                   |
| ENH-07 #357 Gemini structured output           | 3 unchecked           | **Shipped** in `fca3b1fb`. Checkbox hygiene.                                                                                                                                                                                                                                                                                   |
| ENH-08 #360 kailash-trust shim                 | 4 unchecked           | **Shipped** as `packages/kailash-trust/` (not `kailash-trust-shim/`). Checkbox hygiene + path reconciliation.                                                                                                                                                                                                                  |
| ENH-09 #375 cross-SDK parity check             | 4 unchecked           | **Shipped** as `scripts/check-api-parity.sh` + `extract-api-surface.py`. Checkbox hygiene.                                                                                                                                                                                                                                     |
| ENH-11 #371 OntologyRegistry                   | 5 unchecked           | **Shipped** in `fca3b1fb`. Checkbox hygiene.                                                                                                                                                                                                                                                                                   |
| Wave 0 PACT-01..04 + TASK-W0-01..03            | 8 unchecked           | **Shipped** in `090c0e97`. Issues #363/#364/#367/#368/#373/#377 closed. Checkbox hygiene.                                                                                                                                                                                                                                      |
| **ENH-03 #370 EventLoopWatchdog**              | 5 unchecked           | **CLOSED BUT NOT DELIVERED.** No `watchdog.py` in `src/kailash/runtime/`, no `class EventLoopWatchdog` anywhere. Must be reopened and implemented.                                                                                                                                                                             |
| **ENH-06 #351 DriftMonitor API cleanup**       | 4 unchecked           | **CLOSED BUT NOT DELIVERED.** `drift_monitor.py` still uses `set_reference()` / `set_performance_baseline()` without rename or `DriftCallback` type. Must be reopened and implemented.                                                                                                                                         |
| **ENH-10 #374 ProgressUpdate**                 | 5 unchecked           | **CLOSED BUT NOT DELIVERED.** No `progress.py` in `src/kailash/runtime/`, no `class ProgressUpdate`. Must be reopened and implemented.                                                                                                                                                                                         |
| **GH #416 N4/N5/N6 byte-for-byte Rust parity** | OPEN                  | Python has own conformance vectors using `json.dumps(sort_keys=True)`. Rust spec requires ordered field serialization + PascalCase/snake_case mix + shared vectors from kailash-rs. Fresh work.                                                                                                                                |
| TASK-CC-01..10 (12-cross-cutting.md)           | 36 unchecked          | **Mixed.** Shims: already removed (see session notes: "All shims removed (95 files, ~1,600 lines)"). `docs/migration/v2-to-v3.md`: absent. `scripts/convergence-verify.py`: absent. `.test-baseline`: absent. `.github/ISSUE_TEMPLATE/cross-sdk-convergence.md`: **present**. Mix of checkbox hygiene + genuine residual work. |

**Net real work (not just checkbox hygiene): 3 issues + 1 open = 4 real implementation chunks + ~10 cross-cutting residual tasks.**

**BLOCKED phrases for this session:**

- "The issue is closed so the todo can be ticked without verification" — NO, three issues were wrongly closed.
- "This is checkbox hygiene, skip the evidence scan" — NO, evidence scan is the gating check.

---

## 1. Dependency Graph

```
Stream V (Verify)  →  spec-compliance scan per todo AC
                      produces verification-delta.json
                              |
                              v
Stream I (Implement)  →  4 worktrees in parallel
    I1: #370 EventLoopWatchdog
    I2: #374 ProgressUpdate
    I3: #351 DriftMonitor API cleanup
    I4: #416 PACT N4/N5/N6 byte-for-byte Rust parity

Stream C (Cross-cutting residuals)  →  parallel micro-agents
    C1: docs/migration/v2-to-v3.md (CC-04)
    C2: scripts/convergence-verify.py (CC-08)
    C3: .test-baseline refresh (CC-07)
    C4: CC-06 cross-sdk interop CI workflow [HUMAN AUTH]
    C5: CC-10 README/Sphinx doc pass
    C6: CC-09 release note cross-refs (verify only)

Stream R (R2 spec-polish residual)  →  architect solo agent
    R2-003..R2-014: target SPEC files deleted
    → mark DEFERRED-OBSOLETE + spot-check shipped code

Stream H (Hygiene)  →  serial after V+I+C+R
    checkbox flips driven by verification-delta.json
    move todos/active/*.md → todos/completed/

Exit (Wave D)  →  full regression + MUST-gate reviews + /wrapup
```

**Ordering**: `V → {I, C, R} → H → Exit`. Streams I/C/R fully parallel once V completes.

---

## 2. Execution Waves

### Wave A — Verification (kicks off the session; ~20 min with 10x multiplier)

- Agent `spec-compliance` + `testing-specialist` reads every unchecked `- [ ]` in files 11–16 and cross-references against code using Grep/Read.
- Output: `workspaces/platform-architecture-convergence/02-plans/verification-delta.json`:
  ```json
  [
    {
      "file": "14-pact-bugs-conformance.md",
      "line": 42,
      "task_id": "PACT-01",
      "ac_text": "...",
      "status": "shipped|missing|partial|obsolete",
      "evidence_path": "src/kailash/trust/pact/..."
    }
  ]
  ```
- Gate: no downstream work until delta is complete.

### Wave B — parallel across 6 streams

**B1 — #370 EventLoopWatchdog** (`core-sdk-specialist`, worktree)

- NEW: `src/kailash/runtime/watchdog.py` — class `EventLoopWatchdog`, heartbeat loop, stack-trace capture on stall, context-manager shutdown.
- NEW: `tests/unit/runtime/test_event_loop_watchdog.py`.
- Reopen #370 → push fix → close with commit ref.

**B2 — #374 ProgressUpdate** (`core-sdk-specialist`, worktree)

- NEW: `src/kailash/runtime/progress.py` — frozen `ProgressUpdate` dataclass, node yield contract, runtime callback registry.
- EDIT: `src/kailash/nodes/base.py` — thread progress callback through execution.
- NEW: `tests/unit/runtime/test_progress_update.py`.
- Reopen #374 → push → close.

**B3 — #351 DriftMonitor API cleanup** (`ml-specialist`, worktree)

- EDIT: `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py` — rename `set_reference()` → `set_reference_data()`, `set_performance_baseline()` → `set_reference_performance()`. Add `DriftCallback = Callable[[DriftResult], None]`. Deprecation shims per ADR-009 Layer 2. Module docstring.
- NEW: `packages/kailash-ml/tests/unit/test_drift_monitor_deprecation.py`.
- Reopen #351 → push → close.

**B4 — GH #416 PACT N4/N5/N6 byte-for-byte parity** (`pact-specialist` + `testing-specialist`, worktree)
⚠️ **Requires ADR-008 cross-SDK human pre-auth — see §5 Risk 1.**

- NEW: `src/kailash/trust/pact/audit_durability.py` — `DurabilityTier` enum (snake_case matching Rust), `TieredAuditEvent` dataclass with explicit field ordering `event_id, timestamp, role_address, posture, action, zone, reason, tier, tenant_id, signature`, `TieredAuditRouter` with fail-loud typed errors, InMemory/File/SQLite stores.
- EDIT: `src/kailash/trust/pact/observation.py` — `Evidence` dataclass with field order `schema, source, timestamp, gradient, action, payload` and `pact.governance.verdict.v1` / `.access.v1` defaults.
- VENDOR-IN: copy Rust vectors from `esperie-enterprise/kailash-rs:crates/kailash-pact/tests/conformance/vectors/*.json` → `tests/conformance/vectors/`.
- NEW: `tests/conformance/test_conformance_vectors.py` — byte-for-byte canonical JSON equality.
- NEW: `PACT_VECTORS.sha256` integrity file.
- Close #416 + ensure cross-SDK matched issue on kailash-rs acknowledges parity.

**B5 — Cross-cutting residuals** (`core-sdk-specialist` + `testing-specialist`, parallel micro-agents)

- C1: `docs/migration/v2-to-v3.md` (CC-04) — deprecated paths table + sed migration snippets.
- C2: `scripts/convergence-verify.py` (CC-08) — runs grep/import checks from overview §Convergence Verification.
- C3: Refresh `.test-baseline` via `uv run pytest -q --co` count capture → `workspaces/platform-architecture-convergence/.test-baseline`.
- C5: README + Sphinx doc pass per CC-10.

**B6 — R2 spec-polish residuals** (`architect-specialist`, solo)

- Read each R2-003..R2-014 finding → spot-check shipped code for the intended behavior → append DEFERRED-OBSOLETE (spec file consumed) or close with evidence.

### Wave C — Hygiene flip (sequential after Wave B converges, ~30 min)

- `todo-hygiene` micro-agent consumes `verification-delta.json` + Wave B outputs.
- Rewrites each of the 6 todo files with `- [x]` + one-line evidence link.
- Moves files from `todos/active/` to `todos/completed/`.

### Wave D — Close-out (serial, last step)

- Run `scripts/convergence-verify.py` (from C2).
- Run `uv run pytest tests/ packages/ -q --tb=no` full suite; compare to `.test-baseline`.
- `reviewer` + `security-reviewer` + `gold-standards-validator` MUST-gate (background parallel per `rules/agents.md` §Quality Gates).
- `/wrapup` → update `.session-notes`.
- Human approval gate for CC-06 cross-sdk interop CI workflow (optional; do NOT auto-create per `feedback_no_auto_cicd.md`).

---

## 3. Specialist Assignment

| Wave        | Task                      | Specialist                                                    | Notes                                      |
| ----------- | ------------------------- | ------------------------------------------------------------- | ------------------------------------------ |
| A           | Verification scan         | `spec-compliance` + `testing-specialist`                      | Shared worktree OK (read-only)             |
| B1          | #370 EventLoopWatchdog    | `core-sdk-specialist`                                         | worktree isolation                         |
| B2          | #374 ProgressUpdate       | `core-sdk-specialist`                                         | worktree                                   |
| B3          | #351 DriftMonitor         | `ml-specialist`                                               | worktree                                   |
| B4          | #416 N4/N5/N6             | `pact-specialist` + `testing-specialist`                      | worktree; requires kailash-rs vector fetch |
| B5-C1       | v2-to-v3 migration guide  | `core-sdk-specialist`                                         |                                            |
| B5-C2       | convergence-verify.py     | `core-sdk-specialist`                                         |                                            |
| B5-C3       | .test-baseline refresh    | `testing-specialist`                                          | Test-Once Protocol                         |
| B5-C5       | README/Sphinx             | `core-sdk-specialist`                                         |                                            |
| B6          | R2 residual spec-polish   | `analyst` (architect role)                                    | solo, no worktree                          |
| C (hygiene) | Todo checkbox flip        | `todo-manager`                                                | serial on delta input                      |
| D           | Full regression + reviews | `reviewer` + `security-reviewer` + `gold-standards-validator` | background parallel                        |

**Parallelism budget**: 4 implementation worktrees (B1–B4) + 4 single-agent tasks (B5-C1/C2/C3/C5) + 1 R2 agent = **9 concurrent agents at wave peak**, all `isolation: worktree` for anything that compiles or runs pytest.

---

## 4. GH Issue Cross-Reference Table

| Issue    | Title (truncated)                  | State                | Owning todo     | Status vs code             | Wave                  |
| -------- | ---------------------------------- | -------------------- | --------------- | -------------------------- | --------------------- |
| #341     | ml.metrics public module           | CLOSED               | 15-ml ML-01     | Shipped (090c0e97)         | C-hygiene             |
| #342     | probability metrics                | CLOSED               | 15-ml ML-02     | Shipped                    | C-hygiene             |
| #343     | cross_validate                     | CLOSED               | 15-ml ML-03     | Shipped                    | C-hygiene             |
| #344     | clustering engine                  | CLOSED               | 15-ml ML-04     | Shipped                    | C-hygiene             |
| #345     | dim reduction                      | CLOSED               | 15-ml ML-05     | Shipped                    | C-hygiene             |
| #346     | text features                      | CLOSED               | 15-ml ML-06     | Shipped                    | C-hygiene             |
| #347     | classification report              | CLOSED               | 15-ml ML-07     | Shipped                    | C-hygiene             |
| #348     | anomaly detection                  | CLOSED               | 15-ml ML-08     | Shipped                    | C-hygiene             |
| **#351** | DriftMonitor API cleanup           | **CLOSED (wrongly)** | 16-enh ENH-06   | **NOT delivered**          | **B3 (reopen)**       |
| #357     | Gemini structured output           | CLOSED               | 16-enh ENH-07   | Shipped (fca3b1fb)         | C-hygiene             |
| #360     | kailash-trust shim package         | CLOSED               | 16-enh ENH-08   | Shipped as `kailash-trust` | C-hygiene             |
| #363     | Ollama tool_call_id strip          | CLOSED               | 13-w0 W0-01     | Shipped                    | C-hygiene             |
| #364     | Ollama stream+tools                | CLOSED               | 13-w0 W0-01     | Shipped                    | C-hygiene             |
| #365     | Ollama embeddings                  | CLOSED               | 16-enh ENH-04   | Shipped                    | C-hygiene             |
| #366     | Ollama tool allowlist              | CLOSED               | 16-enh ENH-05   | Shipped                    | C-hygiene             |
| #367     | Ollama num_predict merge           | CLOSED               | 13-w0 W0-01     | Shipped                    | C-hygiene             |
| #368     | \_on_source_change crash           | CLOSED               | 13-w0 W0-01     | Shipped                    | C-hygiene             |
| #369     | FabricIntegrityMiddleware          | CLOSED               | 16-enh ENH-02   | Shipped                    | C-hygiene             |
| **#370** | EventLoopWatchdog                  | **CLOSED (wrongly)** | 16-enh ENH-03   | **NOT delivered**          | **B1 (reopen)**       |
| #371     | OntologyRegistry                   | CLOSED               | 16-enh ENH-11   | Shipped                    | C-hygiene             |
| #373     | BulkResult WARN                    | CLOSED               | 13-w0 W0-03     | Shipped                    | C-hygiene             |
| **#374** | ProgressUpdate                     | **CLOSED (wrongly)** | 16-enh ENH-10   | **NOT delivered**          | **B2 (reopen)**       |
| #375     | cross-SDK parity tooling           | CLOSED               | 16-enh ENH-09   | Shipped                    | C-hygiene             |
| #377     | sync SingleShot MCP loop           | CLOSED               | 13-w0 W0-02     | Shipped                    | C-hygiene             |
| #380     | PACT N1 KnowledgeFilter            | CLOSED               | 14-pact PACT-05 | Shipped                    | C-hygiene             |
| #381     | PACT N2 envelope cache             | CLOSED               | 14-pact PACT-06 | Shipped                    | C-hygiene             |
| #382     | PACT N3 plan re-entry              | CLOSED               | 14-pact PACT-09 | Shipped                    | C-hygiene             |
| #383     | PACT N4 audit tiers                | CLOSED               | 14-pact PACT-08 | Shipped (Py-native)        | C-hygiene + B4 parity |
| #384     | PACT N5 ObservationSink            | CLOSED               | 14-pact PACT-07 | Shipped (Py-native)        | C-hygiene + B4 parity |
| #385     | PACT N6 conformance                | CLOSED               | 14-pact PACT-10 | Shipped (Py-native)        | C-hygiene + B4 parity |
| #386     | AgentPosture alignment             | CLOSED               | 14-pact PACT-04 | Shipped                    | C-hygiene             |
| #388     | grant_clearance address            | CLOSED               | 14-pact PACT-02 | Shipped                    | C-hygiene             |
| #389     | get_node fallback                  | CLOSED               | 14-pact PACT-03 | Shipped                    | C-hygiene             |
| #390     | verify_action None crash           | CLOSED               | 14-pact PACT-01 | Shipped                    | C-hygiene             |
| **#416** | N4/N5/N6 byte-for-byte Rust parity | **OPEN**             | N/A (new)       | **Fresh work**             | **B4**                |

**Three wrongly-closed issues (#351, #370, #374) + one open (#416) = 4 real implementation targets.**

---

## 5. Risks / Blockers Requiring Human Authorization

Pre-approve or batch decide BEFORE session start:

### 1. ADR-008 cross-SDK lockstep (#416) — ENVELOPE WIRE FORMAT

Byte-for-byte parity with Rust requires Python to adopt Rust-driven field ordering and case conventions. HUMAN MUST confirm:

- (a) `TieredAuditEvent` field order: `event_id, timestamp, role_address, posture, action, zone, reason, tier, tenant_id, signature`.
- (b) `GradientZone` PascalCase + `TrustPostureLevel`/`DurabilityTier` snake_case.
- (c) Consuming shared vectors from kailash-rs is PERMITTED as a one-time vendor-in per `rules/artifact-flow.md`. ALTERNATIVE: vectors live in a third standards repo.

### 2. ADR-009 reopening closed issues (#351, #370, #374)

Reopening wrongly-closed issues is non-destructive but touches release hygiene. HUMAN should acknowledge: reopen, implement, push fix, close with new commit reference.

### 3. TASK-CC-06 cross-sdk interop CI workflow

Per `feedback_no_auto_cicd.md` memory: NEVER auto-create GitHub Actions workflows. HUMAN MUST explicitly approve creating `.github/workflows/cross-sdk-interop.yml`, or this task remains DEFERRED.

### 4. ENH-08 #360 naming drift

Shipped package is `kailash-trust/` (not `kailash-trust-shim/` as per todo). HUMAN should confirm this is intentional, or rename.

### 5. R2 SPEC file deletion

R2-003..R2-014 target spec files that no longer exist. HUMAN should confirm these can be marked DEFERRED-OBSOLETE rather than reconstructed.

### 6. Post-implementation release gate

B1/B2/B3/B4 may warrant patch bumps (`kailash 2.8.3`, `kailash-ml 0.8.2`, `kailash-pact` patch). HUMAN decides: batch release at end of session or defer.

**Execution gates (autonomous, no human):** Wave A verification convergence, Wave B code reviews, Wave C checkbox hygiene, Wave D regression comparison.

---

## 6. Test Plan

Per `rules/testing.md` Test-Once Protocol — run each suite exactly once at wave boundaries, never re-run in a loop looking for flakes.

| Suite                                                              | When      | Trigger                                                              |
| ------------------------------------------------------------------ | --------- | -------------------------------------------------------------------- |
| `tests/unit/runtime/test_event_loop_watchdog.py`                   | End of B1 | new file                                                             |
| `tests/unit/runtime/test_progress_update.py`                       | End of B2 | new file                                                             |
| `packages/kailash-ml/tests/unit/test_drift_monitor_deprecation.py` | End of B3 | new file                                                             |
| `packages/kailash-ml/tests/` (full ML suite)                       | End of B3 | regression on rename                                                 |
| `tests/conformance/test_conformance_vectors.py`                    | End of B4 | new file                                                             |
| `tests/trust/pact/` (full PACT suite)                              | End of B4 | regression on audit/observation edits                                |
| `tests/` root suite                                                | Wave D    | `.test-baseline` comparison                                          |
| `packages/*/tests/` (all)                                          | Wave D    | full cross-package regression                                        |
| `scripts/convergence-verify.py`                                    | Wave D    | architectural assertions                                             |
| `hypothesis` property tests                                        | SKIPPED   | hypothesis not installed (per `.session-notes` trap) — document skip |

**Packages touched in B-waves**: `kailash` (core, runtime), `kailash-ml`, `kailash-pact`, `kailash-trust`. DataFlow/Kaizen/Nexus not touched in B.

**Zero-regression gate** (Wave D):

```bash
uv run pytest tests/ packages/ -q --tb=no 2>&1 | tail -5
```

compared against baseline captured in B5-C3. Passing count MUST NOT drop.

**Python interpreter trap**: MUST use `uv run python3` or `.venv/bin/python3` — `python3` pyenv shim resolves to kailash-rs bindings.

---

## 7. Exit Criteria

Session is "done" only when ALL are true:

1. All 198 `- [ ]` items across files 11–16 are either `- [x]` or explicitly `- [x] DEFERRED-OBSOLETE (reason)`.
2. `02-plans/verification-delta.json` committed with per-AC evidence.
3. Three wrongly-closed issues (#351, #370, #374) reopened, implemented, and re-closed with new commit reference.
4. Issue #416 closed with `tests/conformance/test_conformance_vectors.py` green against shared Rust vectors.
5. `scripts/convergence-verify.py` exists and exits 0.
6. Full-suite pytest regression matches or exceeds `.test-baseline` (zero net regressions).
7. `reviewer` + `security-reviewer` + `gold-standards-validator` MUST-gate reviews converge with no unresolved findings.
8. `docs/migration/v2-to-v3.md` exists.
9. Six follow-up todo files moved from `todos/active/` to `todos/completed/`.
10. `.session-notes` updated via `/wrapup`.
11. HUMAN has authorized (or explicitly deferred) CC-06 cross-sdk interop CI workflow creation.
12. No new red-team findings from `/redteam` phase 04 on the session's diff.

**Zero open GH issues remaining from the scope `{#341..#390, #416}`.**

---

## 8. Estimated Scope in Autonomous Cycles

Per `rules/autonomous-execution.md` 10x multiplier:

| Work unit                                  | Cycles          | Rationale                                                                       |
| ------------------------------------------ | --------------- | ------------------------------------------------------------------------------- |
| Wave A verification scan                   | 0.3             | 198 items, grep/read-bound, parallel                                            |
| B1 EventLoopWatchdog                       | 0.4             | Greenfield core primitive + tests                                               |
| B2 ProgressUpdate                          | 0.4             | New module + Node base touch-up                                                 |
| B3 DriftMonitor rename                     | 0.2             | Rename + deprecation shim + tests                                               |
| B4 #416 N4/N5/N6 parity                    | 0.8             | Vector vendor-in + audit_durability.py + Evidence refactor + conformance runner |
| B5 cross-cutting residuals                 | 0.3             | Docs + script + baseline; fully parallel                                        |
| B6 R2 residuals                            | 0.1             | Spot-checks + defer notes                                                       |
| C checkbox hygiene                         | 0.1             | Mechanical                                                                      |
| D close-out (review + regression + wrapup) | 0.2             | Background review agents                                                        |
| **Total session**                          | **~1.2 cycles** | Fits in ONE session given 4–9 parallel agents                                   |

**Does NOT fit in one session only if:**

- Human blocks B4 on ADR-008 envelope decisions at session open.
- CC-06 requires live kailash-rs coordination exceeding single-session latency.
- Regression fails in Wave D triggering a root-cause investigation that forces a second session.

---

## 9. Critical Files for Implementation

- `src/kailash/runtime/watchdog.py` (NEW — B1)
- `src/kailash/runtime/progress.py` (NEW — B2)
- `src/kailash/nodes/base.py` (EDIT — B2, thread progress callback)
- `packages/kailash-ml/src/kailash_ml/engines/drift_monitor.py` (EDIT — B3)
- `src/kailash/trust/pact/audit.py` (EDIT — B4: `DurabilityTier` + `TieredAuditEvent` ordered serialization)
- `src/kailash/trust/pact/observation.py` (EDIT — B4: `Evidence` dataclass with ordered fields)
- `src/kailash/trust/pact/audit_durability.py` (NEW — B4)
- `tests/conformance/test_conformance_vectors.py` (NEW — B4)
- `tests/conformance/vectors/*.json` (VENDOR-IN from kailash-rs — B4)
- `PACT_VECTORS.sha256` (NEW — B4)
- `scripts/convergence-verify.py` (NEW — C2)
- `docs/migration/v2-to-v3.md` (NEW — C1)
- `workspaces/platform-architecture-convergence/02-plans/verification-delta.json` (NEW — Wave A)
- `workspaces/platform-architecture-convergence/.test-baseline` (NEW — C3)

---

## 10. 200-Word Summary

The plan reframes 202 "open" todos as primarily a **verification-then-hygiene** exercise. Evidence scan against git history shows 33 of 34 referenced GH issues are already closed and shipped in commits `090c0e97` and `fca3b1fb`; most checkbox items just need flipping with evidence links. Three issues (#351 DriftMonitor, #370 EventLoopWatchdog, #374 ProgressUpdate) were **wrongly closed** — no code was delivered — and must be reopened and implemented. Issue #416 (PACT N4/N5/N6 byte-for-byte Rust parity) is genuinely open and requires new `DurabilityTier`/`TieredAuditEvent`/`Evidence` types with Rust-mandated field ordering plus a shared conformance vector suite.

Execution runs in four waves: (A) verification scan producing `verification-delta.json`; (B) parallel implementation across 4 worktrees (B1-B4) plus cross-cutting residuals (B5) and R2 spec polish (B6); (C) mechanical checkbox hygiene; (D) regression + reviewer/security MUST-gates + wrapup. Total budget ≈1.2 autonomous cycles — fits one session. Human pre-authorization is flagged for ADR-008 wire-format adoption, CC-06 CI workflow creation, and reopening the three wrongly-closed issues. Specialists: core-sdk-specialist (B1/B2), ml-specialist (B3), pact-specialist (B4), documentation/testing for B5, architect for B6.
