---
id: W6-000
title: Wave 6 Portfolio Spec Remediation — Milestone Tracker
priority: P0
estimated_sessions: 9 (across W1-W9)
depends_on: []
blocks: []
status: pending
---

## Overview

Tracker for Wave 6 portfolio remediation. Per `02-plans/01-wave6-implementation-plan.md`, work splits into 4 milestones (M1–M4) executed in 8 implementation waves (W1–W8) plus a final /redteam wave (W9).

**Total:** 23 atomic todos (W6-001..023) + 1 disposition + 1 tracker = 25 files.

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

## Acceptance for Wave 6 milestone-complete

Per `02-plans/01-wave6-implementation-plan.md` § "Acceptance for Wave 6 complete":

- [ ] All 23 todos either landed or explicitly deferred with tracking issue
- [ ] Per-todo Tier-1 + Tier-2 tests; Tier-3 e2e where mandated by spec
- [ ] All spec edits trigger sibling re-derivation per `rules/specs-authority.md` § 5b
- [ ] `pytest --collect-only -q` exits 0 across every test directory per-package
- [ ] Issue #599 re-triaged
- [ ] Reviewer + security-reviewer + gold-standards-validator find no gaps
- [ ] CHANGELOG entries in each affected sub-package
