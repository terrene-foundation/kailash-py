# DECISION: 4+1 per-package sharding, largest first

**Date:** 2026-05-03
**Phase:** /todos
**Decision-makers:** orchestrator (autonomous), pending human approval at /todos gate

## Context

Architecture plan proposed 5+1 shards (per-package). Per-package hit counts measured against current main:

| Path                                                                   | Hits | Files |
| ---------------------------------------------------------------------- | ---: | ----: |
| `packages/kailash-dataflow/src/`                                       |   89 |    48 |
| `packages/kailash-kaizen/src/`                                         |   81 |    43 |
| `packages/kaizen-agents/src/`                                          |   71 |    18 |
| `src/kailash/`                                                         |   18 |     4 |
| `packages/kailash-nexus/src/`                                          |   16 |    12 |
| `packages/kailash-ml/`, `-align/`, `-pact/`, `-mcp/`, `-mcp-platform/` |    0 |     0 |

Sum 275 (wider regex). Five packages already at zero — their inclusion in S5 of the plan was speculative.

## Decision

**4+1 cleanup shards instead of 5+1:**

- T1 — `packages/kailash-dataflow/src/` (89)
- T2 — `packages/kailash-kaizen/src/` (81)
- T3 — `packages/kaizen-agents/src/` (71)
- T4 — `src/kailash/` + `packages/kailash-nexus/src/` (34, bundled because both small + non-overlapping)
- T5 — CI gate + regression test (closes the ratchet)
- T6 — Final audit + close #781

**Largest first ordering:** T1 ratifies the SHIPPED-vX.Y.Z convention's mechanics on the package with the largest hit count + most diverse class distribution. T2/T3/T4 inherit the ratified mechanics; can ship in parallel after T1 merges.

## Rationale

- Per-package keeps blast radius bounded to one importable surface per shard (`rules/autonomous-execution.md` MUST Rule 1).
- Bundling already-clean packages into a phantom S5 wastes one shard's worth of orchestration overhead.
- Largest first surfaces convention-application edge cases early; later shards get to copy the pattern.
- T5 ships AFTER cleanup so the gate can't block legitimate cleanup PRs.

## Effect on capacity

Each cleanup shard is comment-only (≤89 LOC text edits, ≤5 invariants, 0 call-graph hops). Sized 3–5x under the load-bearing-logic budget per `rules/autonomous-execution.md` § Per-Session Capacity Budget Rule 2 (boilerplate scales 5x further than logic).

T1+T2+T3+T4 can ship in roughly 2 sessions if T2/T3/T4 run in parallel after T1 merges. T5+T6 in one more session. Total: ~3 sessions for 6 todos.
