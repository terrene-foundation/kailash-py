---
type: DECISION
date: 2026-03-31
created_at: 2026-03-31T12:05:00+08:00
author: agent
session_id: session-10
session_turn: 2
project: kailash
topic: Sprint S12 todo structure — 14 todos across 5 milestones for PACT conformance
phase: todos
tags: [pact, sprint-planning, todos, spec-conformance]
---

# Sprint S12 Todo Structure — 14 Todos Across 5 Milestones

## Decision

Organized the 4 PACT spec-conformance issues (#199-#202) into 14 todos across 5 milestones, ordered by dependency graph:

| Milestone                            | Issue | Todos              | Dependency        |
| ------------------------------------ | ----- | ------------------ | ----------------- |
| M1: Write-time tightening + gradient | #200  | TODO-01 to TODO-04 | None              |
| M2: Compilation + bridges            | #201  | TODO-05 to TODO-08 | None              |
| M3: Vacancy interim                  | #202  | TODO-09, TODO-10   | M2 (vacant heads) |
| M4: EATP record emission             | #199  | TODO-11 to TODO-13 | None              |
| M5: Red team + close                 | All   | TODO-14            | M1, M2, M3, M4    |

M1, M2, M4 can execute in parallel. M3 depends on M2 only because the interim envelope computation for vacant roles requires those roles to exist in the compiled org (TODO-05).

## Alternatives Considered

1. **Issue-sequential** (do #199 first because CRITICAL) — rejected because #199 is additive and doesn't block other work. CRITICAL severity reflects spec importance, not implementation urgency.
2. **Single milestone** — rejected because 14 todos in one group hides the dependency structure.
3. **Splitting bridge consent (#201) from compilation (#201)** — kept together because they're sub-issues of the same GitHub issue and both touch engine.py.

## Rationale

- Dependency-ordered, not severity-ordered: M3 (MEDIUM) waits for M2 (HIGH) because of the vacant head dependency, not because of severity ranking
- M4 (CRITICAL) is independent and can run in any position — placed last in numbering but can execute in parallel
- TODO-14 is the convergence gate: all tests, red team, PR, issue closure

## For Discussion

1. The bridge bilateral consent (TODO-06) is a breaking change for callers — existing code that calls `create_bridge()` without `consent_bridge()` will fail. Should we add a `require_bilateral_consent: bool = False` parameter for backward compatibility, or enforce consent immediately?
2. If M1 and M4 can run in parallel, should they be executed in separate worktree agents to maximize throughput? The files they touch don't overlap (envelopes.py vs engine.py for the non-overlapping parts).
3. Given that the Rust SDK already implements all 4 features, should we reference Rust's test cases as behavioral specifications for the Python tests?
