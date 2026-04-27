---
id: W6-000
title: Wave 6 Portfolio Spec Remediation — Milestone Tracker (W6 + W7 CONVERGED + SHIPPED)
priority: P0
estimated_sessions: 9 W6 + 1 W7 (ALL CLOSED)
depends_on: []
blocks: []
status: w6_w7_converged_shipped
---

## Overview

Tracker for portfolio remediation. **Wave 6 is VERIFIED-CONVERGED and SHIPPED** as of 2026-04-27 (see `04-validate/W6-redteam-round3-verification.md`). Per session 2026-04-27 disposition: fold issue #657 (LineageGraph) + W6-007 LOW-2 carry-forward into **Wave 7** rather than creating a separate "Wave 6.5b" milestone.

**Wave 6 totals:** 23 atomic todos (W6-001..023) — all merged or explicitly disposed. PRs #644–#669; releases kailash 2.11.3, kailash-ml 1.4.2, kailash-align 0.7.0.

**Wave 7 totals:** 2 atomic todos (W7-001..002).

## Milestone map

| ID range          | Milestone                  | Todos | LOC est. | Wave     |
| ----------------- | -------------------------- | ----- | -------- | -------- |
| W6-001..005       | M1 — Quick wins            | 5     | ~600     | W1, W2   |
| W6-006..016       | M2 — Architecture decisions | 11    | ~2,500   | W2..W6   |
| W6-017            | M3 — Cross-SDK invariant   | 1     | ~150     | W6       |
| W6-018..023       | M4 — W6.5 follow-ups       | 6     | ~1,000   | W7, W8   |
|                   | /redteam                   | n/a   | n/a      | W9       |
|                   |                            | **23** | **~4,250** |          |

## Per-todo capacity check (recap)

Each todo is sized to fit a single shard per `rules/autonomous-execution.md` § Per-Session Capacity Budget:

- ≤500 LOC load-bearing
- ≤5–10 invariants
- ≤3–4 call-graph hops
- describable in ≤3 sentences

Quick wins (M1) and W6.5 follow-ups (M4) are well under cap. Architecture decisions (M2) are right at cap; if any audit reveals scope expansion, the implementing specialist MUST shard at /todos amend time per `rules/specs-authority.md` § 5c.

## Wave acceptance gates

| Wave | Gate                                                                                                |
| ---- | --------------------------------------------------------------------------------------------------- |
| W1   | 3 PRs merged; pytest --collect-only exit 0; reviewer background agent green per agents.md MUST gate |
| W2   | 3 PRs merged; ml-specialist + dataflow-specialist confirm no shared-surface conflict                |
| W3   | 3 PRs merged; nexus + dataflow specs re-derived per specs-authority.md § 5b                         |
| W4   | 3 PRs merged; kaizen specs re-derived; F-D-25 judges directory exists                               |
| W5   | 3 PRs merged; ml package version owner is W6-015; CHANGELOG single coherent entry                   |
| W6   | 2 PRs merged; M3 byte-vector tests pass against kailash-rs reference output                         |
| W7   | 3 PRs merged; ml package canonical surface = facade resolution                                      |
| W8   | 3 PRs merged; e2e Tier-3 test green; feature_store_wiring test exists per facade-manager-detection §1 |
| W9   | /redteam convergence — reviewer + security-reviewer + gold-standards-validator find no gaps         |

## Open items

- Issue #599 re-triage (pact-specialist) — separate from Wave 6 todos but tracked alongside.
- Wave 6 cumulative changelog: each sub-package gets its own CHANGELOG entry; orchestrator coordinates final release at end of W8.

## Status legend

| Status                | Meaning                                          |
| --------------------- | ------------------------------------------------ |
| pending               | not yet started                                  |
| in_progress           | shard agent launched, branch open                |
| review                | implementation done, reviewer + security pending |
| merged                | PR merged to main                                |
| deferred              | per zero-tolerance.md Rule 1b protocol            |

## Acceptance for Wave 6 milestone-complete — VERIFIED 2026-04-27

Per `02-plans/01-wave6-implementation-plan.md` § "Acceptance for Wave 6 complete":

- [x] All 23 todos either landed or explicitly deferred with tracking issue (W6-014 deferred → #657, folded into W7-001)
- [x] Per-todo Tier-1 + Tier-2 tests; Tier-3 e2e where mandated by spec
- [x] All spec edits trigger sibling re-derivation per `rules/specs-authority.md` § 5b
- [x] `pytest --collect-only -q` exits 0 across every test directory per-package (24,938 tests collected; 7 packages)
- [x] Issue #599 re-triaged + closed
- [x] Reviewer + security-reviewer + gold-standards-validator find no gaps (Round-3 verification PASS)
- [x] CHANGELOG entries in each affected sub-package

## Wave 7 — VERIFIED 2026-04-27 (SHIPPED)

| ID     | Title                                                  | Specialist          | PR    | Tag              | Status |
| ------ | ------------------------------------------------------ | ------------------- | ----- | ---------------- | ------ |
| W7-001 | LineageGraph implementation (closes #657)              | ml-specialist       | #677  | ml-v1.5.0        | merged |
| W7-002 | dataflow.ml emit_train_end structural sanitization     | dataflow-specialist | #678  | dataflow-v2.3.2  | merged |

W7 disposition decided 2026-04-27: bundled into single wave instead of separate "Wave 6.5b" — both single-shard fixes, no shared package surface, safe to run parallel worktrees per `rules/agents.md` § "Parallel-Worktree Package Ownership Coordination".

### Wave 7 Acceptance — VERIFIED

- [x] W7-001 + W7-002 both merged (PR #677 → `922a6e7b`, PR #678 → `64a1802d`)
- [x] Issue #657 closed via PR #677 body link (per `rules/git.md` § Issue Closure Discipline)
- [x] Tier-2 regression tests for both shards: 13 ml tests (10 wiring + 3 quickstart), 4 dataflow tests
- [x] Sibling specs re-derived per `rules/specs-authority.md` § 5b — ml-tracking, ml-engines-v2, ml-engines-v2-addendum (W7-001); dataflow-ml-integration, kailash-core-ml-integration (W7-002)
- [x] CHANGELOG entries: kailash-ml 1.5.0, kailash-dataflow 2.3.2
- [x] PyPI publication: ml-v1.5.0 + dataflow-v2.3.2 published; clean-venv install + import smoke test passed per `rules/build-repo-release-discipline.md` Rule 2
- [x] `deploy/deployment-config.md` current-versions table refreshed (commit `82a49305`)
