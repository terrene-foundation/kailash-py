# Test Verification Round 1 — Issues #490 #491 #492 #493 #496

Date: 2026-04-18
Auditor: testing-specialist (redteam Step 4)
Commits under audit: 7a4fd364 (#492 #496), 2dbb9107 (#493), prior 0a9da432 (#490), 36060c98 (#491)

Per `testing.md` § Audit Mode: re-derived all numbers from `pytest --collect-only` and direct test runs. `.test-results` NOT read.

---

## 1. Collect-Only Sweep

### Combined `pytest tests/ packages/*/tests/`

Exit: non-zero. Failure: `_pytest.pathlib.ImportPathMismatchError` in `packages/kailash-align/tests/conftest.py` (collides on module name `tests.conftest` with root `tests/conftest.py`).

**Disposition:** NOT a code orphan. This is a pytest module-path collision between the root `tests/` directory and each `packages/*/tests/` directory — both resolve to module name `tests.conftest`. It is a pre-existing pytest multi-root configuration issue, not a new regression introduced by commits 7a4fd364 / 2dbb9107. The individual collections all succeed (verified below), which is how CI actually runs them.

**Finding:** LOW — pytest multi-root config limitation. Not a merge blocker under the current CI topology; each package is collected separately.

### Per-directory collection (all exit 0)

| Directory                          | Tests collected | Time  |
| ---------------------------------- | --------------- | ----- |
| `tests/` (root SDK)                | 15959           | 6.48s |
| `packages/kailash-dataflow/tests/` | 5839            | 3.21s |
| `packages/kailash-align/tests/`    | 392             | 0.09s |
| `packages/kailash-kaizen/tests/`   | 11189           | 4.88s |
| `packages/kailash-mcp/tests/`      | 76              | 0.29s |
| `packages/kailash-ml/tests/`       | 926             | 1.69s |
| `packages/kailash-nexus/tests/`    | 2044            | 2.03s |
| `packages/kailash-pact/tests/`     | 1385            | 1.29s |
| `packages/kailash-trust/tests/`    | 0               | 0.06s |
| `packages/kaizen-agents/tests/`    | 3268            | 2.81s |
| **TOTAL**                          | **~41 078**     |       |

No `ERROR <path>` / `ModuleNotFoundError` / `ImportError` in any per-directory collection.

---

## 2. New-Module-to-Test Coverage Map

| Modified/New Module (commit)                                                                            | Importing/Exercising Tests                                                                                                                                                                                                                                                                    | Status                       |
| ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py` (7a4fd364)                                | `test_bulk_upsert_sql_injection.py` (18), `test_bulk_upsert_conflict_on.py` (13), `test_bulk_upsert_delegation_integration.py`, `test_bulk_upsert_node_integration.py`, `test_bulk_upsert_comprehensive.py`, `test_upsert_bulk_consistency.py`, `test_bulk_upsert_conflict_on_integration.py` | COVERED                      |
| `packages/kailash-dataflow/src/dataflow/core/nodes.py` — sanitizer (2dbb9107)                           | `test_connection_sql_injection_protection.py` (8, asserts STATEMENT_BLOCKED token-replace + "parameter type mismatch" raise on dict/list)                                                                                                                                                     | COVERED                      |
| `packages/kailash-dataflow/src/dataflow/core/engine.py` — ALTER TABLE identifier validation (7a4fd364)  | `test_issue_496_identifier_safety.py` lines 59–125 cover `ADD_COLUMN` / `DROP_COLUMN` / `MODIFY_COLUMN` raw-identifier rejection + happy-path quoting                                                                                                                                         | COVERED                      |
| `packages/kailash-dataflow/src/dataflow/migrations/sync_ddl_executor.py` — PRAGMA identifier (7a4fd364) | `test_issue_496_identifier_safety.py::test_sync_ddl_executor_pragma_rejects_invalid_identifiers` (parametrized)                                                                                                                                                                               | COVERED                      |
| `packages/kailash-dataflow/src/dataflow/classification/event_payload.py` (36060c98 / #491)              | `test_event_payload_classification.py` (10), `test_dataflow_events.py`                                                                                                                                                                                                                        | COVERED                      |
| `packages/kailash-dataflow/src/dataflow/features/express.py` — redaction (0a9da432 / #490)              | `test_classification_mutation_return.py`, `test_issue_490_mutation_return_redaction.py`, `test_express_dataflow_integration.py`, `test_event_payload_classification.py`                                                                                                                       | COVERED                      |
| `src/kailash/nodes/admin/schema_manager.py` — hardcoded list `_validate_identifier` (7a4fd364)          | `test_unified_admin_schema.py` imports `AdminSchemaManager` but does NOT exercise validator routing on the hardcoded lists. `test_issue_446_dlq_identifier_validation.py` covers the analogous pattern on `PersistentDLQ` but not on `schema_manager`.                                        | **PARTIAL — MEDIUM finding** |

### Finding M1 (MEDIUM) — schema_manager hardcoded-list validator routing is not tested

`src/kailash/nodes/admin/schema_manager.py` now routes every element of two hardcoded lists (`_drop_existing_schema`, `_get_table_row_counts`) through `_validate_identifier()` per `dataflow-identifier-safety.md` Rule 5. The DLQ pattern has a behavioral regression test at `tests/regression/test_issue_446_dlq_identifier_validation.py` that patches `_validate_identifier` to a spy and asserts every hardcoded name routed through it. The schema_manager change in commit 7a4fd364 has no equivalent spy-based regression test — a future refactor that drops the `_validate_identifier(table)` call on either list would ship with zero signal.

**Action (not in this audit's scope to implement, but flagged):** Add `tests/regression/test_schema_manager_hardcoded_identifier_validation.py` mirroring `test_issue_446_dlq_identifier_validation.py` — spy on `_validate_identifier`, invoke the schema_manager path, assert each of `{"users", "roles", "permissions", "role_permissions", "user_roles", "audit_log"}` (or the actual hardcoded set) was seen.

---

## 3. Regression Suite Execution

Command: single pytest invocation with `-x -q --timeout-method=thread --timeout=60` across all 6 files from session notes.

Result: **72 passed, 1 skipped, 8 warnings, 0 failed — 7.06s**

| File                                          | Collected | Verdict                        |
| --------------------------------------------- | --------- | ------------------------------ |
| `test_bulk_upsert_sql_injection.py`           | 18        | 18 pass                        |
| `test_issue_496_identifier_safety.py`         | 13        | 13 pass                        |
| `test_event_payload_classification.py`        | 10        | 10 pass                        |
| `test_connection_sql_injection_protection.py` | 8         | 8 pass                         |
| `test_unsafe_ddl_protection.py`               | 11        | 10 pass, 1 skipped             |
| `test_bulk_upsert_conflict_on.py`             | 13        | 13 pass                        |
| **TOTAL**                                     | **73**    | **72 pass, 1 skipped, 0 fail** |

Session-notes claim of "18 SQLi regression tests + 13 issue-496 regression + 10 event-payload + ... = all green" is verified.

---

## 4. Log / Warning Triage

5 unique warning classes from the regression run (8 occurrences total):

| #   | Class                                                                | Count | Location                                                                        | Disposition                                                                                                                                                                         |
| --- | -------------------------------------------------------------------- | ----- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `DeprecationWarning: LocalRuntime.execute() without context manager` | 8     | `test_connection_sql_injection_protection.py` lines 75, 134, 194, 249, 352, 402 | **Upstream — GH #478.** Expected per session notes. Not introduced by this session's commits. Planned migration to `with LocalRuntime() as r:` pattern at v0.12.0 is an open issue. |

No `ResourceWarning`, `RuntimeWarning`, `PytestCollectionWarning`, or `InsecureKeyLengthWarning` entries. No WARN+ entries in test output beyond #1 above.

`collection-only` sweep produced 4 unique `PytestCollectionWarning` entries (pre-existing helper classes with `__init__`) — all pre-existing, not introduced by issues #492/#493/#496. Per `testing.md` § "MUST: Test Helper Classes Without `__init__` Use Stub Naming" these are outstanding technical debt but not regressions from the audited commits.

---

## 5. Additional Observations

### Sanitizer contract coverage is minimal but present

Commit 2dbb9107 pinned the `sanitize_sql_input` contract (token-replace not quote-escape; type-confusion raises). Direct coverage lives only in `test_connection_sql_injection_protection.py` (integration tier) — there is NO dedicated unit test file for `sanitize_sql_input()` itself. The function is exercised indirectly by every DataFlow node validation.

**Finding L1 (LOW):** A targeted unit test file `packages/kailash-dataflow/tests/unit/core/test_sanitize_sql_input.py` covering every contract clause (str token-replace, dict/list/set/tuple raises, safe-type passthrough, JSON-column dict/list passthrough) would convert the integration-only coverage into grep-able unit-level regression bait. Current coverage is sufficient for sign-off but brittle under refactor.

### Bulk_upsert SQLi coverage strength

`test_bulk_upsert_sql_injection.py` (378 LOC, 18 tests) directly exercises: table-name injection, column-name injection, `conflict_on` injection, dialect-specific paths (PostgreSQL, MySQL, SQLite), and explicitly asserts the `no_quote_escape_in_source` source-level invariant. This is the strongest single regression artifact in the audited set.

### Known trap honored

`--timeout-method=thread` used throughout per session notes; no hangs observed on asyncio selector loops.

---

## Summary

- **Collect-only**: Per-directory pass (all exit 0). Combined-root fails on pytest multi-root module-name collision (pre-existing, not introduced, LOW).
- **Regression suite**: 72/73 pass, 1 skipped, 0 failed.
- **New-module coverage**: 6/7 new/modified surfaces fully covered; schema_manager hardcoded-list validation routing is not spy-tested (MEDIUM).
- **Warnings**: Only `DeprecationWarning: LocalRuntime.execute()` — upstream GH #478, acknowledged.

### HIGH findings: 0

### MEDIUM findings: 1 (M1 — schema_manager validator-routing spy test missing)

### LOW findings: 2 (pytest multi-root collision, sanitizer dedicated unit test missing)

Session-notes numerical claims verified. No merge blockers identified. M1 should be fixed before next release per `testing.md` § "MUST: Verify NEW modules have NEW tests" — the existing coverage proves the validator rejects bad input, but not that the schema_manager code path actually calls it.
