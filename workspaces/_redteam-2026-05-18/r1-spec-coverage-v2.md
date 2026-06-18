# Round 1 — Spec Compliance Audit (analyst, re-derived from scratch)

**Scope:** #1083 (#1050 follow-up — ProtectedDataFlow Tier-2 matrix), #1084 (#992 follow-up — B-1.5 Tier-2 mock-laden rewrite), #1085 (#979 follow-up — DataFlow unit suite triage OPTION-C′). All three issues closed 2026-05-18.

**Method:** AST/grep verification per `skills/spec-compliance/SKILL.md` — NOT trusting closure-parity self-reports in journals 0006/0008/0009. Re-derived from `specs/dataflow-protection.md` §1-3 (I1–I9), `specs/testing-tiers.md` § Tier-1+Tier-2, brief ACs, closure tables.

## Verdict

**Round 1 analyst verdict: 0 CRIT / 0 HIGH / 3 MED / 0 LOW**
**Convergence: YES**

## Per-spec assertion table

### `specs/dataflow-protection.md` §1-3 (I1–I9) — verifies #1083

| Assertion                                                                                     | Verification                                                                                                                                          | Status |
| --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| I1 single `check_operation` (Express+ProtectedNode honor `_express_protection_precheck_done`) | `grep -rn _express_protection_precheck_done` → 9 hits: protection_middleware.py:351 + 8 express setters (672, 863, 953, 1286, 1375, 1453, 1600, 1682) | PASS   |
| I2 pre-I/O at protection_middleware.py:431 before super().async_run at :456                   | comment block :318-339 cites I2                                                                                                                       | PASS   |
| I3 canonical operation string (no class-name parse on hot path)                               | protection_middleware.py:379 reads self.operation; class-name strip = defensive fallback only                                                         | PASS   |
| I4 model_name plumbed                                                                         | protection_middleware.py:386, 432-433                                                                                                                 | PASS   |
| I5 ProtectionViolation subclass of NodeExecutionError; survives execute_async re-wrap         | protection.py:165                                                                                                                                     | PASS   |
| I5b workflow-runtime test pins genuine PV at node boundary via **cause** walk                 | test_issue_1050_workflow_runtime_protection.py:169-229 \_assert_node_boundary_is_protection_violation                                                 | PASS   |
| I6 WARN logs, only BLOCK/AUDIT raise via \_handle_violation                                   | protection.py:368-432                                                                                                                                 | PASS   |
| I7 count→READ (was CUSTOM_QUERY fall-through pre-#1050)                                       | protection.py:327                                                                                                                                     | PASS   |
| I8 instance isolation (no global monkeypatch)                                                 | `grep -rn AsyncSQLProtectionWrapper packages/kailash-dataflow/src` = 0 .py hits                                                                       | PASS   |
| I9 auditor.log_violation before raise                                                         | protection.py:204-205, 414-425                                                                                                                        | PASS   |
| OperationType.UPSERT first-class (#1058 S3 closure)                                           | protection.py:37                                                                                                                                      | PASS   |
| Matrix ≥5 surfaces                                                                            | grep `_BLOCKED_MUTATIONS` → 8: create/update/delete/upsert/bulk\_{create,update,delete,upsert}                                                        | PASS   |
| LocalRuntime + AsyncLocalRuntime × sqlite_file + postgresql                                   | test file:92-97 (2×2 matrix per mutation)                                                                                                             | PASS   |
| Express precheck fires BEFORE \_validate_if_enabled                                           | express.py:279 precheck → :286 validate                                                                                                               | PASS   |

### `specs/testing-tiers.md` § Tier-2 Rule 1 — verifies #1084

| Assertion                                                                                 | Verification                                                                  | Status                           |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------- |
| Tier-2 Rule 1 verbatim "integration tests MUST exercise real infrastructure"              | testing-tiers.md:154-162                                                      | PASS                             |
| 10 originally-targeted #1084 files GONE from integration tier                             | per journal 0008 table; counterparts under tests/unit/                        | PASS                             |
| Conftest AST guard rejects new mock imports                                               | conftest.py:120-145 `_module_imports_unittest_mock`                           | PASS                             |
| "1 remaining import" = `fabric/test_fabric_integrity.py:22 from unittest.mock import ANY` | conftest carve-out (51-66): ANY = whitelisted sentinel, NOT mocking primitive | PASS — out of scope per contract |
| Other "mock" matches in integration = docstrings/conftest/sentinels                       | 10 files all docstring or sentinel-only                                       | PASS                             |

### `specs/testing-tiers.md` § Tier-1 Contract — verifies #1085

| Assertion                                                                | Verification                                      | Status |
| ------------------------------------------------------------------------ | ------------------------------------------------- | ------ |
| tests/unit/examples/ empty (S2a)                                         | per journal 0009 row S2a                          | PASS   |
| tests/unit/fabric/ empty (S3)                                            | per journal 0009 row S3                           | PASS   |
| Tier-1 conftest CLAUDE.md cites testing-tiers Rule 1                     | CLAUDE.md:102 citation resolves + content matches | PASS   |
| pytest-timeout pinned in `[dev]`                                         | pyproject.toml:134                                | PASS   |
| aiosqlite pinned in `[dev]`                                              | pyproject.toml:56,145                             | PASS   |
| S6 CI gate test-dataflow with paths filter + editable-root install FIRST | per PR #993 (`81b1a4b5a`) + release 2.9.6         | PASS   |
| DEFENSE-2 + DEFENSE-3 test files exist                                   | per journal 0009 row S6 (receipt-cited)           | PASS   |
| Brief traceability section maps each #979 layer to contract clause       | testing-tiers.md:228-238                          | PASS   |

### Cross-references + same-bug-class closures

| Assertion                                                                             | Verification                                           | Status              |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------- |
| Cross-SDK kailash-rs inspection deferred-to-user per `rules/repo-scope-discipline.md` | journal 0006:60 cites rule verbatim                    | CORRECT DISPOSITION |
| Same-bug-class follow-ups (#1058 S1-4) shipped                                        | PRs #1064/#1065, commits ff1477517/b466acf6f/c3fbf37fa | PASS                |
| CHANGELOG 2.9.14/2.9.15/2.9.16 covers S2+S3+sibling closures                          | per journal 0006                                       | PASS                |

## MED findings (codify candidates, none blocking)

**MED-1:** `tests/integration/test_issue_1050_protection_mutation_matrix.py:168-170` rebinds `_Doc.__name__` to uuid-suffixed string per parametrized test to dodge global node-registry collision. Surface as canonical pattern in `specs/testing-tiers.md § Tier-2 Rule 2` (3+ workspaces hit same).

**MED-2:** I1 consumer at `protection_middleware.py:351-352` uses `if ... True: pass` no-op skip-branch — lint-fragile (formatter could collapse). Recommend explicit early-return OR comment pinning load-bearing pass-branch semantics.

**MED-3:** Workflow-runtime test's **cause**-only walk avoids **context** — institutional knowledge lives only in test docstring. Lift contract to `specs/dataflow-protection.md §3` as explicit invariant I5b.

## Cross-spec consistency

- `specs/dataflow-protection.md` §1-3 fully aligned with protection.py + protection_middleware.py + features/express.py HEAD
- `specs/testing-tiers.md` § Tier-1 Rule 1 verbatim citation in `packages/kailash-dataflow/tests/unit/CLAUDE.md:102` resolves
- Tier-2 NO-MOCKING enforced mechanically by `tests/integration/conftest.py::_module_imports_unittest_mock`
- "Tier-2 Rule 1" referenced consistently across testing-tiers.md, brief, journal 0008, CLAUDE.md
