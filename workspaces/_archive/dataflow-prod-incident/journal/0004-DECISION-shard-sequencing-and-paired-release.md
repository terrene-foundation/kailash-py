# 0004 DECISION — Shard Sequencing and Paired Release

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /todos
**Type:** DECISION

## Decision

Three shards execute in this dependency order:

1. **Shards A + C in parallel** (both kailash-dataflow, different files in different worktrees)
2. **Shard B independently** (kailash core, separate package, separate specialist load)
3. **Shard D (cross-package integration)** runs once A + B + C all merge to main
4. **Shard E (release)** runs in two waves: kailash 2.12.0 first → wait → kailash-dataflow 2.4.0

## Rationale

Three forces shape the ordering:

1. **Per-package release coupling** — `kailash-dataflow`'s `kailash>=2.12.0` floor (DPI-D1) makes the bump dependent on kailash 2.12.0 being on PyPI. Per `rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable Versions" this MUST be sequential, never parallel.
2. **Worktree isolation discipline** — Shards A and C both edit `kailash-dataflow` but DIFFERENT files (`core/engine.py` for A; `engine.py` for C). Per `rules/worktree-isolation.md` § 4 (waves of ≤3) and § 5 (merge-base check) parallel is safe with explicit pre-flight verification.
3. **Specialist load** — Shard B requires both dataflow-specialist + infrastructure-specialist (the pool-registry pattern); A and C only need dataflow-specialist. Running B alongside A+C would double-load the dataflow-specialist context.

## Alternatives considered

**Alt 1: Single sequential cycle** — A → B → C → D → E. Cleaner mental model but loses the parallelism multiplier (3-5x per `rules/autonomous-execution.md` § 10x throughput). Rejected: too slow when shards are genuinely independent.

**Alt 2: All four shards parallel** — A + B + C in waves of 3. Rejected: B's pool-registry change is mechanism for D2's bridge test; if B lands AFTER A's regression test runs, the bridge gap is invisible. Sequencing B before D is structural.

**Alt 3: Single mega-PR** — Land all shards in one PR + one release. Rejected: violates `rules/autonomous-execution.md` § Per-Session Capacity Budget (the combined ~800 LOC + ~14 invariants exceeds shard threshold) AND would require waves of bridge fixes if any one shard regressed.

## Risks

The chosen ordering has one risk surfaced in `journal/0002 RISK` — kailash-dataflow PR opens BEFORE kailash 2.12.0 is on PyPI. Mitigation: DPI-D1 is gated by DPI-E1 + the 60 s PyPI cache lag wait in DPI-E4. The release-specialist owns this gate.

## Cross-SDK propagation

After all five issues close at kailash-py, file three cross-SDK issues at esperie/kailash-rs (DPI-E6). The Rust SDK is expected to have the same `EnterpriseConnectionPool` analog and the same `auto_migrate` lazy-creation pattern; verifying via reading kailash-rs source is the next workstream's first step. Per `rules/cross-sdk-inspection.md` § 4 — every closure includes the cross-SDK-checklist verification.

## What this decision affects

- DPI-D1, DPI-E1, DPI-E2, DPI-E4 are all sequenced behind DPI-B5 + DPI-A4 + DPI-C3 (per-shard regression tests)
- DPI-D2 (bridge test) is the structural defense against the multi-package release ordering risk
- The `release/v*` branch convention (per `rules/git.md`) auto-skips PR-gate CI on metadata-only release-prep PRs

## Related

- `journal/0001 DISCOVERY` — silent-fallback + no-lifecycle is one pattern (motivates Shard B's bundling)
- `journal/0002 RISK` — multi-package release blast radius
- `journal/0003 CONNECTION` — JourneyMate as canary for Azure-class deployments
- `rules/autonomous-execution.md` § Per-Session Capacity Budget
- `rules/deployment.md` § Multi-Package Release Tags Pushed Individually
