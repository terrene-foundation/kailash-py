# Redteam Round 1 — Reviewer Axis

Scope: #1050 protection chain, #992 B-1.5 mock rewrite, #979 OPTION-C′.
Method: 7 mechanical sweeps per `rules/agents.md` MUST § Reviewer Mechanical Sweeps, then targeted LLM judgment on protection wiring, BulkUpsert/Upsert hot path, and randomly-sampled Tier-1 moves.
Mode: read-only.

## Mechanical sweep results

| #   | Sweep                           | Result                           | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| --- | ------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Orphan check-paths grep         | CLEAN                            | `AsyncSQLProtectionWrapper` not present in any tracked `src/` file (only pycache binaries + `build/` artifacts which are gitignored). `check_operation` wired at `packages/kailash-dataflow/src/dataflow/core/protection_middleware.py:431` (single async-hot-path routing) + `packages/kailash-dataflow/src/dataflow/features/express.py:279` (dedup-guarded). `ProtectionViolation` raised at `protection.py:{372,385,426}` and caught at `express.py:{1537,2006,2023}` + middleware:437. |
| 2   | Mutation matrix parity          | CLEAN                            | `_BLOCKED_MUTATIONS` (`tests/integration/test_issue_1050_protection_mutation_matrix.py:132-141`) lists 8 names: create/update/delete/upsert/bulk_create/bulk_update/bulk_delete/bulk_upsert. Matches the 8 async mutation methods at `express.py:639/833/929/1252/1424/1491/1580/1621` exactly. Read-side coverage (read/list/count not blocked) explicit at lines 253/279/305.                                                                                                             |
| 3   | Mock-import scan on integration | CLEAN                            | Only the whitelisted non-primitives (`ANY`, `sentinel`, `call`) appear; no new `MagicMock/AsyncMock` imports past `fabric/test_fabric_integrity.py:22` (the known-allowed `ANY` import). `conftest.py:32+` is the AST gate itself; `test_conftest_no_mocking_hook.py` and `templates/saas_starter/*` references are inside docstrings/error strings, not active imports.                                                                                                                    |
| 4   | `pytest --collect-only`         | CLEAN with PYTHONPATH workaround | Integration: `1919/2059 tests collected (140 deselected) in 2.22s` exit 0. Unit: `3445 tests collected in 1.13s` exit 0. Verifier-reported stale-kailash issue confirmed; PYTHONPATH override unblocks. CI does this via the editable-install step.                                                                                                                                                                                                                                         |
| 5   | CI gate (#1085 S6)              | CLEAN                            | `unified-ci.yml:10-26` paths cover `src/**`, `packages/**`, `tests/**`, `pyproject.toml`, `uv.lock`, the workflow file (transitive-graph rule from `rules/ci-runners.md` § Rule 5 satisfied). Install at lines 231-232: `pip install -e "."` THEN `pip install -e "packages/kailash-dataflow[dev]"` (deployment-rule order correct). Pytest at line 256 (`pytest tests/unit/ --maxfail=10 -q --timeout=120`) — zero `-m` flags, per S1 CRIT-B.                                              |
| 6   | DEFENSE-2/3 wiring              | CLEAN                            | DEFENSE-2 (`tests/unit/security/test_sanitizer_public_api.py`) routes via `memory_dataflow.express._create_node(model, "Create")` — same construction path Express uses, NOT a direct import of the `nodes.py` nested closure. DEFENSE-3 (`test_fabric_smoke_invariants.py`) imports from public `dataflow.fabric.ssrf` and `dataflow.fabric.route_classifier` modules. Both files compile.                                                                                                 |
| 7   | CHANGELOG drift                 | CLEAN                            | Versions 2.9.1 → 2.9.18 all present at `CHANGELOG.md` lines 943/898/839/788/750/712/638/588/522/451/358/308/263/230/143/93/17/11/5. No version gap.                                                                                                                                                                                                                                                                                                                                         |

## LLM-judgment findings

### F1 — LOW: `bulk_update` empty-records list bypasses protection precheck

- **File:** `packages/kailash-dataflow/src/dataflow/features/express.py:1491-1539`
- **Evidence:** `grep -nE "_check_protection_if_enabled\(" express.py` shows entry points at lines 664/855/948/1283/1371/1449/1598/1678. `bulk_update` (1491-1539) has no upfront precheck call — protection fires per-record via `await self.update(...)` at line 1535. If `records=[]`, the for-loop body never executes, and the function returns `[]` without firing any `check_operation`. Sibling bulk methods (`bulk_create:1449`, `bulk_delete:1598`, `bulk_upsert:1678`) all precheck upfront, so an audit-only `read_only_global` config will produce ZERO audit entries for an empty-list `bulk_update` while producing one for the other three bulk surfaces.
- **Severity rationale:** LOW because (a) zero rows are written (no data integrity loss), and (b) `_check_append_only(model, "bulk_update")` at line 1516 still fires for append-only configs. The defect is observability: an empty `bulk_update` is undetectable in audit logs, asymmetric with sibling surfaces. The mutation matrix at `test_issue_1050_protection_mutation_matrix.py:212` only exercises the 1-record case, so this gap is not caught by the matrix.
- **Recommended fix:** Add a precheck at the top of `_bulk_update()` mirroring sibling pattern at line 1449: `await self._check_protection_if_enabled(model, "bulk_update", {"data": records})`. One line; same shard budget; closes observability gap.

### F2 — LOW: `upsert_advanced` (express.py:1337) precheck arg-shape divergence

- **File:** `packages/kailash-dataflow/src/dataflow/features/express.py:1369-1375`
- **Evidence:** `upsert_advanced` passes the full `data` dict as the context (line 1371-1374) where sibling `upsert` (line 1283) passes raw `data`. Both call sites work, but the context shape divergence makes future audit-record diffing across upsert paths inconsistent. No security/correctness impact today.
- **Severity rationale:** LOW — cosmetic consistency issue, not a hot-path defect.
- **Recommended fix:** Optional. Defer to next codify pass.

### F3 — No finding: BulkUpsert/Upsert enum closure verified

- Read `c3fbf37fa` diff + post-fix `protection.py:33-42` + `_operation_mapping:313-345`.
- `OperationType.UPSERT` first-class (line 37). `upsert` maps at line 344. All 8 mutation surfaces map to writeable enum types — no `CUSTOM_QUERY` fallback for any. Same-class branches (BulkUpsert routing through CUSTOM_QUERY default) structurally closed.
- The Shard-4 `except ProtectionViolation: raise` ahead of generic `except Exception` is present at both `import_file` branches (`express.py:2006-2014, 2023-2027`). Verified the I5 propagation discipline holds.

### F4 — No finding: ProtectionViolation taxonomy + workflow-runtime path

- `protection.py:166` confirms `class ProtectionViolation(NodeExecutionError):` rebasing. `test_issue_1050_workflow_runtime_protection.py:158-165` exercises BOTH `LocalRuntime.execute(workflow.build())` AND `AsyncLocalRuntime.execute_workflow_async(workflow.build(), {})` — both paths from the red-team CRITICAL. Re-wrap bug structurally closed.

### F5 — No finding: Tier-1 moved files retain Tier-1 mock idiom

- Sampled 2 of 10 moved files: `tests/unit/cache/test_cache_invalidation.py:21` (`from unittest.mock import AsyncMock, Mock, patch`) and `tests/unit/migrations/test_impact_reporter_unit.py:21,62-63` (MagicMock + AsyncMock). Both files reside under `tests/unit/` post-move; Tier-1 permits mocking (`rules/testing.md` § 3-Tier Testing). NO infrastructure dependency introduced. Move semantics correct.

### F6 — No finding: `AsyncSQLProtectionWrapper` fully removed

- `grep -rn "AsyncSQLProtectionWrapper" packages/kailash-dataflow/src specs/` returns zero hits in tracked source. CHANGELOG 2.9.15 entry documents the deletion. The `build/lib/` artifacts that surface in `grep` are gitignored (verified via `git check-ignore -v` returning `.gitignore:56: build/`). No PyPI-leak risk.

## Round 1 reviewer verdict

```
Round 1 reviewer verdict: 0 CRIT / 0 HIGH / 0 MED / 2 LOW
Convergence: YES (zero CRIT/HIGH)
```

The chain ships clean at the CRIT/HIGH bar. Both LOW findings are bounded:

- **F1** (empty-list bulk_update precheck) — one-line fix, fits inside the current shard budget, can ship in the next codify pass alongside any follow-up. Same-class as the bulk_create/bulk_upsert precheck pattern already established by #1058 Shard 2 — recommend fix-immediately per `rules/autonomous-execution.md` Rule 4 if the agent budget permits.
- **F2** (upsert_advanced context shape) — cosmetic; defer.

Mechanical sweeps 1-7 all clean. Mutation matrix is parity-complete (8 surfaces, 8 entries). DEFENSE-2/3 wired via public API (not nested closure). CHANGELOG covers 2.9.1 → 2.9.18 with no gap. CI gate paths follow the transitive-dep rule. Workflow-runtime regression exercises both `LocalRuntime` AND `AsyncLocalRuntime` per spec I5.

Word count: ~720.
