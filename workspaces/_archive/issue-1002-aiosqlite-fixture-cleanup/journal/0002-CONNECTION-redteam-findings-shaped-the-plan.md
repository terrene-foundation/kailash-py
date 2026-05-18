# 0002 CONNECTION — red-team findings shaped the architecture plan

Date: 2026-05-14
Phase: /analyze (post-red-team)

Background: analyst red-team of `02-plans/01-architecture-plan.md` (run after the initial draft) surfaced 8 findings. Three were HIGH and forced plan amendments before /todos.

## Findings → plan amendments

| Finding                                                                     | Class   | Disposition                                                                                                                                                         |
| --------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| HIGH-1 — Surface misses Redis/MySQL/Mongo async adapters                    | accept  | Brief Correction #5 added; Shard 2 surface explicitly extended to 8 cache + adapter test files                                                                      |
| HIGH-2 — `dataflow-test-fixtures.md` already lives in `testing-tiers.md` §2 | accept  | Brief Correction #4 added; "Specs update" rewritten to "already landed in testing-tiers.md §2 amendment"; new-spec creation removed                                 |
| HIGH-3 — Conftest-stub pattern (`testing.md`) not evaluated                 | accept  | Shard-0 entry decision added: pattern REJECTED with rationale (we want real DataFlow + cleanup, not stubbed init)                                                   |
| MED-1 — Shard 4 sequencing risk understated                                 | accept  | Shard 4 entry-gate explicitly requires local 120s pytest exit-clean run BEFORE editing CI                                                                           |
| MED-2 — `__del__` ResourceWarning regression tests must stay                | accept  | "Do-not-touch list" added between Shard-0 decision and Shard 1; covers `test_del_no_close.py`, `test_resource_warning.py`, any `pytest.warns(ResourceWarning)` site |
| MED-3 — Tempfile ordering risk under-listed                                 | accept  | Shard 1 cross-lists 3 tempfile-using files in `tests/unit/`; invariant 7 added: tempfile sites close DataFlow before unlink                                         |
| MED-4 — Shard 4 regression test design unverified                           | accept  | Shard 4 specifies subset (`tests/unit/cache/`), timeout (300s outer / 60s inner), location (`packages/kailash-dataflow/tests/regression/`), assertion shape         |
| LOW-1 — Value-anchors paraphrase brief AC                                   | accept  | All shard value-anchors rewritten to verbatim quotes from `briefs/00-brief.md:38-42` per `value-prioritization.md` MUST-6                                           |
| LOW-2 — Cross-SDK note recommends out-of-repo action                        | partial | Reworded to "informational; user decides" per `rules/repo-scope-discipline.md`                                                                                      |

Total: 9 amendments (8 findings + 1 LOW-2 partial). Each amendment is in-shard for `/analyze` per `autonomous-execution.md` MUST Rule 4 (fix-immediately when review surfaces same-class gap within shard budget).

## Mechanical evidence supporting findings

```bash
# HIGH-1 — non-DataFlow async resource constructions in tests/unit/
$ grep -rln "AsyncRedisCacheAdapter\|redis\.asyncio\|aiomysql\|motor\|aiomotor" \
    packages/kailash-dataflow/tests/unit/ --include="*.py" | wc -l
8

# MED-2 — files exercising __del__ ResourceWarning path (do-not-touch)
$ grep -rln "ResourceWarning\|test_del_\|_resource_warning" \
    packages/kailash-dataflow/tests/unit/ --include="*.py" | wc -l
8

# MED-3 — tempfile use in tests/unit/
$ grep -rln "tempfile\." packages/kailash-dataflow/tests/unit/ --include="*.py" | wc -l
3
```

## Why this connection matters

The original plan had ~270 inline `DataFlow(...)` as the unit of work. After red-team:

- The actual cleanup surface is `~270 DataFlow + ~8 Redis/MySQL/Mongo adapter` constructions across `~50+ files`, with `~8 do-not-touch sites` and `~3 tempfile-ordering sites`.
- The spec contract is already in place (`testing-tiers.md` §2); the work is enforcement, not documentation.
- The conftest-stub shortcut would actively harm the cleanup contract; per-test fixture adoption is the only correct path.

Without these amendments, Shard 1-3 would have shipped a partial fix that left the Redis/MySQL/Mongo leak class active, and Shard 4 would have removed the setsid wrapper while the post-summary hang still reproduced — re-introducing the exact failure mode #1002 exists to prevent.
