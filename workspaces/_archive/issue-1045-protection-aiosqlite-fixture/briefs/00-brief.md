# Issue #1045 — Protection-test async-fixture migration + middleware deprecation fix

## Value-anchor (re-pickup gate per value-prioritization MUST-2/3)

zero-tolerance Rule 1: pre-existing aiosqlite `ResourceWarning` (test side) +
production `DeprecationWarning` (`protection_middleware.py:41`) MUST be resolved.
**Hard deadline:** `LocalRuntime.execute()` without context manager becomes a
runtime error in v0.12.0 — the production security-middleware hot path breaks
then, not just warns. Deferred at session 2026-05-17 only because root fix
exceeds single-shard budget; user re-validated + approved decomposition
2026-05-17 (this session's transcript — source d).

## Decomposition (2 shards, per issue author's own framing)

- **Shard A** — `protection_middleware.py` `ProtectedDataFlowRuntime.execute()`
  context-manager fix. Production security middleware. dataflow-specialist +
  reviewer + security-reviewer gate. Sibling PR.
- **Shard B** — 3-class async-fixture migration in
  `test_protection_system_critical_gaps.py` + `:memory:`→file-backed SQLite
  resolution (lineage #998/#1043) + no-ResourceWarning regression test.

## Acceptance criteria (from #1045)

- [ ] 3 protection-test classes use standardized async DataFlow fixture
- [ ] `pytest tests/unit/test_protection_system_critical_gaps.py -W error::ResourceWarning` exits 0
- [ ] `protection_middleware.py` uses context-manager protocol (security-reviewer signoff)
- [ ] Regression test pins no-ResourceWarning on the protection path

## Lineage

#1002, #1010 (closed); surfaced by #1026 / PR #1044.
