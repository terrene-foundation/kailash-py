# Closure Receipt — issue-891-hybridsearch-collision

Archived 2026-05-25 (during repo-wide `/sweep`). Upstream issue **#891 CLOSED 2026-05-18T19:41:00Z**
(`fix: HybridSearchNode name collision between kailash-dataflow and kailash-kaizen`).

## Why archived

All todos delivered before issue closure; each task carries a commit SHA. Per
`value-prioritization.md` MUST-3, the value-anchor (`specs/node-registry-naming.md`
collision guard) delivered — workspace migrates to `_archive/` rather than
lingering in `todos/active/`. Journal + analysis history preserved in place.

## Delivered todos → commits

| Todo                                                                      | Delivery | Commit      |
| ------------------------------------------------------------------------- | -------- | ----------- |
| T1 — rename HybridSearchNode (both packages) → `PgVectorHybridSearchNode` | done     | `fc6e36996` |
| T2 — BulkUpsertNode → `SQLBulkUpsertNode`                                 | done     | `d83734d2f` |
| T3b — AggregateNode → `MongoAggregateNode`                                | done     | `b00bf55e5` |
| T4 — core cross-module collision guard                                    | done     | `9f08ee2d3` |
| T5 — regression test `tests/regression/test_issue_891_*`                  | done     | `9a885861b` |
| T6 — CHANGELOG + version bumps (kailash 2.23.0)                           | done     | `ac699fcfa` |

## Value-anchor at archival

`specs/node-registry-naming.md` (renames table) — every row delivered; the core
guard crashes import on any un-renamed collision, so renames + guard + test
shipped as one atomic shard per the original todo framing.
