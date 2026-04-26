# Wave 6 — Portfolio Spec Remediation Plan

**Author:** orchestrator (post-W5+W6.5)
**Date:** 2026-04-27
**Status:** approved by user
**Source-of-truth:** `04-validate/00-portfolio-summary.md` § "Wave 6 remediation plan" + commit `f21e9844` § Wave 6 follow-ups + `04-validate/W6.5-v2-draft-review.md` § "Wave 6 follow-ups surfaced"

## Why

Wave 5 audit landed 36 HIGH + 59 MED + 186 LOW + 2 KNOWN-BLOCKED across 71 of 72 specs (commit `1e9e7a01`, PR #638). Wave 4 hotfix (kailash 2.11.2, PR #637) closed the 3 CRITs and 2 of the HIGHs. Wave 6.5 (commit `f21e9844`) realigned the AutoML + FeatureStore specs to actual surface, addressing 13 HIGHs by spec re-derivation. Wave 6 remediates the remaining 23 actionable items by implementation rather than spec drift.

This is **post-/codify cleanup**, not feature work. Every todo either:

- Implements a previously-claimed-but-absent contract (orphan-detection §1 violation), OR
- Deletes the public-surface claim per orphan-detection §3 ("removed = deleted, not deprecated"), OR
- Aligns a code/spec divergence one direction or the other.

## Scope

### In scope (23 todos)

- **M1** — 5 quick wins (W6-001..005)
- **M2** — 11 architecture decisions, wire-or-delete (W6-006..016)
- **M3** — 1 cross-SDK invariant test (W6-017)
- **M4** — 6 Wave 6.5 follow-ups in ml package (W6-018..023)

Plus 1 disposition item: re-triage of issue #599 (`McpGovernanceEnforcer` IS shipped per F-F-16).

### Out of scope

- **Cross-SDK kailash-rs parity audit** — separate workstream, deferred to next `/sync` cycle.
- **AutoML/FeatureStore re-spec** — DONE in Wave 6.5 (commit `f21e9844`).
- **Wave 5 LOW backlog** — 186 LOW items, mostly version-stale spec headers, are addressed BULK by W6-005 (single PR for all four packages); residual non-version LOWs deferred to a future bulk doc-cleanup cycle.

## Capacity & Sharding

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget, every todo MUST fit in one shard:

- ≤500 LOC of load-bearing logic
- ≤5–10 simultaneous invariants
- ≤3–4 call-graph hops
- ≤15k LOC of relevant surface area
- describable in ≤3 sentences

Each W6-NNN todo is one shard. Parallelism is bounded by `rules/worktree-isolation.md` Rule 4 — **waves of ≤3 simultaneous Opus worktree agents**.

### Wave plan

| Wave | Todos                  | Specialists                                                       | Worktrees | Notes                                                  |
| ---- | ---------------------- | ----------------------------------------------------------------- | --------- | ------------------------------------------------------ |
| W1   | W6-001, W6-002, W6-003 | kaizen-specialist, mcp-specialist, dataflow-specialist            | 3         | M1 first-half                                          |
| W2   | W6-004, W6-005, W6-006 | ml-specialist, general-purpose, dataflow-specialist               | 3         | M1 second-half + M2 start                              |
| W3   | W6-007, W6-008, W6-009 | dataflow-specialist, nexus-specialist, nexus-specialist           | 3         | M2 dataflow + nexus                                    |
| W4   | W6-010, W6-011, W6-012 | nexus-specialist, kaizen-specialist, kaizen-specialist            | 3         | M2 nexus + kaizen                                      |
| W5   | W6-013, W6-014, W6-015 | ml-specialist, ml-specialist, ml-specialist                       | 3         | M2 ml — sequential per package, batched in single wave |
| W6   | W6-016, W6-017         | ml-specialist, dataflow-specialist                                | 2         | M2 align/rl + M3 cross-SDK                             |
| W7   | W6-018, W6-019, W6-020 | ml-specialist, ml-specialist, ml-specialist                       | 3         | M4 ml followups                                        |
| W8   | W6-021, W6-022, W6-023 | ml-specialist, ml-specialist, ml-specialist                       | 3         | M4 ml followups continued                              |
| W9   | /redteam               | reviewer + analyst + security-reviewer + gold-standards-validator | n/a       | background agents per `rules/agents.md`                |

**Total:** ~9 waves. Per-wave runtime ~1 session of agent activity. Pre-flight merge-base check before each wave per `rules/worktree-isolation.md` Rule 5.

### Wave 5 (M2 ml) coordination note

W6-013, W6-014, W6-015 all touch `packages/kailash-ml/`. Per `rules/agents.md` § "MUST: Parallel-Worktree Package Ownership Coordination" — the version-owner for the ml package's CHANGELOG bump in this batch is W6-015 (RLTrainingResult); siblings W6-013 (CatBoostTrainable) and W6-014 (LineageGraph) MUST NOT edit `pyproject.toml` / `__version__` / `CHANGELOG.md`. Orchestrator integrates at merge.

## Branch & PR strategy

Per `rules/git.md`:

- Planning PR: `audit/w6-planning` (this PR — plan + tracker + 23 todos)
- Implementation PRs: one per todo, branch `feat/w6-NNN-<slug>`
- Each implementation PR contains: implementation + Tier-1+Tier-2 tests + spec update if §6 deviation + journal entry if DECISION/TRADE-OFF

Admin-merge per session-notes convention. Pre-flight local CI per `rules/git.md` § "Pre-FIRST-Push CI Parity Discipline".

## Decision-required todos

7 of the 23 todos are explicit "wire OR delete" decisions. Default per `rules/orphan-detection.md` § 3: **DELETE** if no production consumer exists. Each todo's body documents the call-graph audit findings; the implementing specialist applies the default unless the audit finds a real consumer.

| Todo   | Class                                   | Default disposition                                                                      |
| ------ | --------------------------------------- | ---------------------------------------------------------------------------------------- |
| W6-006 | TenantTrustManager (dataflow)           | wire if a real call site exists; else delete                                             |
| W6-007 | ML event surface (dataflow)             | spec update wins (events are shipped, just absent from spec)                             |
| W6-008 | JWTValidator.from_nexus_config (nexus)  | delete from spec if no consumer; implement only if Nexus presets need it                 |
| W6-009 | nexus.register_service (nexus)          | reconcile to mount_ml_endpoints (the shipped path)                                       |
| W6-012 | MLAwareAgent + km.list_engines (kaizen) | wire if BaseAgent tool construction exists; else delete spec §2.4                        |
| W6-013 | CatBoostTrainable (ml)                  | implement (CatBoost is a first-class non-Torch family per spec) — small surface          |
| W6-014 | LineageGraph (ml)                       | explicit deferral to M2 with prose update — full implementation is larger than one shard |

## Acceptance for Wave 6 complete

Per `rules/zero-tolerance.md` Rule 1 (no deferred warnings/notices/findings) + `rules/agents.md` Quality Gates:

- [ ] All 23 todos either landed or explicitly deferred with tracking issue per `rules/zero-tolerance.md` Rule 1b
- [ ] Per-todo Tier-1 + Tier-2 tests; Tier-3 e2e where mandated by spec
- [ ] All spec edits trigger sibling re-derivation per `rules/specs-authority.md` § 5b
- [ ] `pytest --collect-only -q` exits 0 across every test directory per-package per `rules/orphan-detection.md` § 5
- [ ] Issue #599 re-triaged
- [ ] Reviewer + security-reviewer + gold-standards-validator find no gaps in Wave 6 cumulative diff
- [ ] CHANGELOG entries land in each affected sub-package (kaizen, dataflow, ml, nexus, mcp, pact)

## Deferral discipline

Per `rules/zero-tolerance.md` Rule 1b — every "deferred" disposition MUST have:

1. Runtime-safety proof inline in the PR body
2. Tracking issue filed
3. Release PR body links the tracking issue
4. release-specialist confirmation OR explicit user override

W6-014 (LineageGraph) is the only confirmed deferral candidate; remaining decisions resolve to wire-or-delete in the same shard.

## Origin

Wave 6 launched 2026-04-27 by user directive after PR #644 (W6.5 audit evidence) merged. Sequenced after Wave 5 (PR #638) and Wave 6.5 (commit `f21e9844`). Plan derived from `04-validate/00-portfolio-summary.md` § "Wave 6 remediation plan" + W6.5 follow-ups.
