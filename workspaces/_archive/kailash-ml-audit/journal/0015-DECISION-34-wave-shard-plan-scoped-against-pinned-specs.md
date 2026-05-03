# DECISION — 34-Wave Shard Plan Scoped Against Pinned Specs

**Date:** 2026-04-21
**Type:** DECISION
**Phase:** /todos
**Scope:** kailash-ml 1.0.0 + 7-package atomic wave release

## Decision

Draft a 34-wave shard implementation plan against the 21 canonical specs promoted in `/codify` (PR #608 merged 2026-04-21). Each shard scoped to ≤500 LOC load-bearing + ≤5–10 invariants + ≤3–4 call-graph hops per `rules/autonomous-execution.md` § Per-Session Capacity Budget.

## Structure

- **12 milestones** (M1-M12) — Foundations → Backends+Trainable → Tracking → Tracking Storage → Registry → MLEngine → Diagnostics+Autolog → Serving/Drift/AutoML/FeatureStore/Dashboard → RL → Integrations → km.\* + README → Release.
- **34 waves** mapped 1:1 to spec sections. Every spec has ≥1 primary wave; no orphan specs.
- **Parallelization:** W1-W6 serial (foundations); W7-W9 sequential; W10-W13 partial parallel after W10; W14-W15 serial; W19-W21 serial (MLEngine cross-method invariants); W22-W28 parallel across 3-4 specialists; W29-W30 serial cross-package; W31-W32 parallel across 3 packages each (with version-owner declared per `agents.md` parallel-worktree rule); W33 serial; W34 strictly serial.

## Rationale

1. **Spec-first convergence satisfied.** Round-8 SYNTHESIS certified spec-level readiness with 8/8 personas × 2+ consecutive clean rounds. The /todos phase translates that convergence into an implementable shard plan without re-litigating spec decisions.
2. **Shard size calibrated to capacity budget.** ≤500 LOC load-bearing × 34 waves ≈ 13.5k LOC fits within realistic autonomous-execution capacity. Waves exceeding budget were split at plan time (W19 vs W20 vs W21; W27 automl+fs as 2 sub-shards; W31 + W32 as 3 sub-shards each).
3. **Dependency ordering prevents orphan classes.** Every `db.*` / `app.* /km.*` facade added by a wave has a wiring test in the same wave per `rules/orphan-detection.md` + `rules/facade-manager-detection.md`. The 34-wave dependency graph ensures no manager-shape class lands before its hot-path caller.
4. **Version owners pre-declared for parallel cross-package waves.** W30 (kailash-ml + kailash-align), W31 (3 packages), W32 (3 packages) identify the per-package version+CHANGELOG owner in orchestrator prompts per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination".
5. **Atomic 7-package release preserves cross-package invariants.** W34 orchestrates single-session release for kailash 2.9.0 + dataflow 2.1.0 + nexus 2.2.0 + kaizen 2.12.0 + pact 0.10.0 + align 0.5.0 + ml 1.0.0. Release order respects reverse dependency graph; installability verified via clean venv per `rules/build-repo-release-discipline.md`.

## Non-Release-Blockers Identified

- **IT-1** — GPU CI self-hosted runner acquisition per Decision 7. CUDA stays non-blocking until this lands; does NOT block 1.0.0 ship.
- **IT-2** — kailash-rs#502 Rust variant overlays via `loom/.claude/variants/rs/specs/ml-*.md` post-`/sync`. Not in py 1.0.0 scope.
- **IT-3** — `SystemMetricsCollector` v1.1-deferred (DL-GAP-2). Documented in Round-8 SYNTHESIS.
- **IT-4** — PACT cross-tenant admin export (`ml-registry-pact.md`) v1.1-deferred per Decision 12. 1.0.0 raises `MultiTenantOpError`.

## Testing Policy Per Wave

Every wave MUST land: Tier 1 unit + Tier 2 integration (real PG + real SQLite) + regression tests for bug classes surfaced in Round 1-8 + invariant tests (`@pytest.mark.invariant`) for LOC-reducing refactors + wiring tests (`test_<name>_wiring.py`) for every manager-shape class.

## Approval Gate

This plan is pending human approval at the /todos structural gate. Approval releases /implement autonomous execution. Release authorization at W34 is the second structural gate.

## Artifacts

- `workspaces/kailash-ml-audit/02-plans/01-master-34-wave-plan.md` — the detailed plan
- `workspaces/kailash-ml-audit/todos/active/W01-errors-hierarchy.md` … `W34-release-wave.md` — 34 per-wave todos
- `workspaces/kailash-ml-audit/todos/active/IT1-gpu-ci-runner.md` — infra follow-up
